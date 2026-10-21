"""Bakes the Lyris world terrain from the Minecraft atlas into Unreal landscape tiles.

    python Art/World/bake_terrain.py                 # full size: 8 x 8 tiles of 2048 px
    python Art/World/bake_terrain.py --preview       # quick check: 8 x 8 tiles of 256 px
    python Art/World/bake_terrain.py --workers 4     # bake tiles in parallel (about 2 GB RAM each)

Needs Python 3.9+ with numpy, scipy and Pillow (pip install numpy scipy pillow).

Input  Art/World/atlas/  hmap.png (25 m/px heights, MC Y = value * 1.5 - 64), bidx.png (biome
       index), lakes.png (lake ids), regions.png, lake_levels.json, biome_names.json.
Output Art/World/tiles/  (not in git; rebuilt by this script)
       World_Height_x{X}_y{Y}.png        16-bit heightmap tiles, tiled-import ready
       World_<Layer>_x{X}_y{Y}.png       8-bit weight tiles, one set per paint layer
       terrain_manifest.json             scale, location, layers, lakes, rivers, spawn ...
       preview_hillshade.jpg             a small shaded relief of the result

Coordinates follow design/world_map.md: 1 block = 1 m = 100 uu, MC X -> UE X (east +X),
MC Z -> UE Y (south +Y), UE Z = (MC Y - 63) * 100, so Z = 0 is sea level. The world covers
MC X and Z -12500..12500, which is UE -1 250 000..1 250 000 on X and Y.

Every value is a pure function of world position (plus a few whole-map fields computed once),
so tiles join without seams and the result is the same on every PC for the same seed.
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image
from scipy import ndimage as nd

BAKE_VERSION = 1
SEED = 1729
HERE = os.path.dirname(os.path.abspath(__file__))
ATLAS = os.path.join(HERE, "atlas")

WORLD_MIN, WORLD_SIZE = -12500.0, 25000.0  # MC blocks = metres
SRC_N = 1000                                # atlas lookup images are 1000 px (25 m/px)
SRC_PX = WORLD_SIZE / SRC_N
MID_N = 4000                                # whole-map fields are kept at 6.25 m/px

# 16-bit height encoding: 0..65535 covers -128 m .. +384 m (UE Scale Z 100, 7.8 mm steps).
H_MIN, H_SPAN = -128.0, 512.0

# Tile layout. 8 x 8 tiles of 2048 px abut to 16384 x 16384 vertices = 129 x 129 components
# of 127 quads (1 section each), the largest UE-recommended size that fits 25 km at ~1.5 m.
FULL_TILES, FULL_TILE_PX = 8, 2048
PREVIEW_TILES, PREVIEW_TILE_PX = 8, 256
QUADS_PER_COMPONENT = 127

LAYERS = ["Grass", "Forest", "Sand", "Rock", "Snow", "Badlands", "Salt", "Volcanic"]

# Biome index (bidx.png, names in biome_names.json) -> soft source masks.
BIOMES_FOREST = [17, 18, 19, 20, 21, 22, 23, 24, 25, 31, 34, 41, 42, 43, 44, 45, 46, 48, 49]
BIOMES_SNOW = [10, 12, 24, 26, 27, 32, 33]
BIOMES_ROCK = [13, 27, 28, 29, 50]
BIOMES_MOUNTAIN = [25, 26, 27, 28, 29, 30, 31, 37, 50]
BIOMES_BADLANDS = [39, 40, 41]
BIOMES_BEACH = [11, 12]
BIOMES_DESERT = [38]
BIOMES_RIVER = [9, 10]
SALTREACH_REGIONS = [8, 9]  # regions.png ids on the western side of the west continent

# Places whose ground must match the server builds: no added detail there, no shelf.
# (MC x0, z0, x1, z1, feather m). From design/world_map.md.
CANON_BOXES = [
    (100, -2565, 620, -2120, 120),    # Moonharbor town core, quay and Keep Elariel
    (-370, -2860, 130, -2360, 80),    # Oruth's pit under the bay (keep the deep water)
    (1346, -3105, 1466, -2985, 60),   # Grand Observatory summit
    (1590, -4010, 1710, -3890, 60),   # The Delvers' Gate
]

# Volcanoes: (name, MC x, MC z, cone radius m, rim height m (None: keep the map's own summit,
# no new cone), crater radius m, crater depth m). The West Volcano (Cinderhorn, Carapotl) is
# canon on Saltreach's snowy spine (DECISIONS 2026-10-20): its highest spine peak becomes a cone.
# Sunreach's summit already has a crater on the map; it only gets the bowl and volcanic ground.
VOLCANOES = [
    ("West Volcano", -5650.0, 3975.0, 1150.0, 200.0, 190.0, 60.0),  # rim at Y 263, the spine's top
    ("Sunreach Volcano", 4150.0, 5050.0, 900.0, None, 170.0, 35.0),
]

SPAWN_MC = (200.5, 65.0, -2287.5)  # Quiet Reach spawn on the server, Moonharbor


# ----------------------------------------------------------------------------- small helpers

def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def load_gray(name):
    return np.array(Image.open(os.path.join(ATLAS, name)).convert("L"))


def mc_to_ue(x, z, h=0.0):
    return [round(x * 100.0, 1), round(z * 100.0, 1), round(h * 100.0, 1)]


# ----------------------------------------------------------------------------- noise

class Noise:
    """Seeded 2D gradient noise with fBm, ridged and domain-warp helpers (world metres in)."""

    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        self.perm = np.concatenate([rng.permutation(256)] * 2).astype(np.int32)
        ang = rng.uniform(0, 2 * np.pi, 256)
        self.gx, self.gy = np.cos(ang).astype(np.float32), np.sin(ang).astype(np.float32)
        self.offsets = rng.uniform(-5000, 5000, size=(32, 2))

    def perlin(self, x, y):
        xi, yi = np.floor(x), np.floor(y)
        xf, yf = (x - xi).astype(np.float32), (y - yi).astype(np.float32)
        xi, yi = xi.astype(np.int64) & 255, yi.astype(np.int64) & 255
        p = self.perm

        def grad(ix, iy, dx, dy):
            h = p[p[ix] + iy]
            return self.gx[h] * dx + self.gy[h] * dy

        u = xf * xf * xf * (xf * (xf * 6 - 15) + 10)
        v = yf * yf * yf * (yf * (yf * 6 - 15) + 10)
        n00 = grad(xi, yi, xf, yf)
        n10 = grad((xi + 1) & 255, yi, xf - 1, yf)
        n01 = grad(xi, (yi + 1) & 255, xf, yf - 1)
        n11 = grad((xi + 1) & 255, (yi + 1) & 255, xf - 1, yf - 1)
        return (lerp(lerp(n00, n10, u), lerp(n01, n11, u), v) * 1.41).astype(np.float32)  # ~[-1, 1]

    def fbm(self, x, y, wavelength, octaves, salt=0, gain=0.5):
        total = np.zeros(np.shape(x), np.float32)
        amp, freq, norm = 1.0, 1.0 / wavelength, 0.0
        for o in range(octaves):
            ox, oy = self.offsets[(salt * 7 + o) % 32]
            total += amp * self.perlin(x * freq + ox, y * freq + oy)
            norm += amp
            amp *= gain
            freq *= 2.03
        return total / norm

    def ridged(self, x, y, wavelength, octaves, salt=0):
        """Sharp crests (1) and soft valleys (0), each octave weighted by the one before."""
        total = np.zeros(np.shape(x), np.float32)
        weight = np.ones(np.shape(x), np.float32)
        amp, freq, norm = 1.0, 1.0 / wavelength, 0.0
        for o in range(octaves):
            ox, oy = self.offsets[(salt * 5 + o + 11) % 32]
            r = 1.0 - np.abs(self.perlin(x * freq + ox, y * freq + oy))
            r = r * r * weight
            weight = np.clip(r * 1.6, 0.0, 1.0)
            total += amp * r
            norm += amp
            amp *= 0.5
            freq *= 2.1
        return total / norm

    def warp(self, x, y, wavelength, strength, salt=0):
        wx = self.fbm(x, y, wavelength, 3, salt=salt + 3)
        wy = self.fbm(x + 913.0, y - 377.0, wavelength, 3, salt=salt + 4)
        return x + wx * strength, y + wy * strength


# ----------------------------------------------------------------------------- whole-map fields

def zhang_suen(mask):
    """Thins a binary mask to one-pixel lines (rivers -> centre lines)."""
    img = np.pad(mask.astype(np.uint8), 1)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p2, p3, p4 = img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:]
            p5, p6, p7 = img[2:, 2:], img[2:, 1:-1], img[2:, :-2]
            p8, p9 = img[1:-1, :-2], img[:-2, :-2]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9]
            b = sum(n.astype(np.int32) for n in nb)
            seq = nb + [p2]
            a = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.int32) for i in range(8))
            if step == 0:
                c = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                c = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            core = img[1:-1, 1:-1]
            kill = (core == 1) & (b >= 2) & (b <= 6) & (a == 1) & c
            if kill.any():
                core[kill] = 0
                changed = True
    return img[1:-1, 1:-1].astype(bool)


def trace_skeleton(skel):
    """Splits a one-pixel skeleton into polylines between end points and junctions."""
    pts = set(zip(*np.nonzero(skel)))
    nbrs = {}
    for (j, i) in pts:
        nbrs[(j, i)] = [(j + dj, i + di) for dj in (-1, 0, 1) for di in (-1, 0, 1)
                        if (dj or di) and (j + dj, i + di) in pts]
    nodes = {p for p, n in nbrs.items() if len(n) != 2}
    seen, lines = set(), []

    def walk(start, nxt):
        line, prev, cur = [start, nxt], start, nxt
        while cur not in nodes:
            step = [n for n in nbrs[cur] if n != prev and (cur, n) not in seen]
            if not step:
                break
            seen.add((cur, step[0]))
            seen.add((step[0], cur))
            prev, cur = cur, step[0]
            line.append(cur)
            if cur == start:
                break
        return line

    for node in nodes:
        for n in nbrs[node]:
            if (node, n) in seen:
                continue
            seen.add((node, n))
            seen.add((n, node))
            lines.append(walk(node, n))
    for p in pts:  # closed loops with no nodes
        if p not in nodes and nbrs[p] and (p, nbrs[p][0]) not in seen:
            seen.add((p, nbrs[p][0]))
            lines.append(walk(p, nbrs[p][0]))
    return lines


def rdp(points, eps):
    """Ramer-Douglas-Peucker simplification of an (N, 2) array."""
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    ab = b - a
    n = np.hypot(*ab)
    if n < 1e-9:
        d = np.hypot(*(points - a).T)
    else:
        d = np.abs(ab[0] * (points[:, 1] - a[1]) - ab[1] * (points[:, 0] - a[0])) / n
    k = int(np.argmax(d))
    if d[k] > eps:
        left = rdp(points[:k + 1], eps)
        return np.vstack([left[:-1], rdp(points[k:], eps)])
    return np.array([a, b])


def trace_outline(mask):
    """Outer boundary pixels of a binary blob, in order (Moore neighbour tracing)."""
    m = np.pad(mask.astype(bool), 1)
    js, is_ = np.nonzero(m)
    k = np.lexsort((is_, js))[0]
    start = (int(js[k]), int(is_[k]))
    ring = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]  # clockwise from N
    cur, back = start, (start[0], start[1] - 1)  # we arrived from the west (background)
    out = [start]
    for _ in range(4 * m.size):
        d0 = ring.index((back[0] - cur[0], back[1] - cur[1]))
        prev = back
        for t in range(1, 9):
            dj, di = ring[(d0 + t) % 8]
            cand = (cur[0] + dj, cur[1] + di)
            if m[cand]:
                cur, back = cand, prev
                break
            prev = cand
        else:
            break  # single pixel
        if cur == start:
            break
        out.append(cur)
    return np.array(out, float) - 1.0


class Fields:
    """Whole-map data computed once and sampled by every tile."""

    def __init__(self, log=print):
        t0 = time.time()
        raw = load_gray("hmap.png").astype(np.float32)
        self.biome = load_gray("bidx.png")
        self.lake_id = load_gray("lakes.png")
        self.h_src = self._despike(raw * 1.5 - 127.0, log)  # metres above sea level (MC Y - 63)
        self.region = load_gray("regions.png")
        with open(os.path.join(ATLAS, "lake_levels.json")) as f:
            levels = {int(k): float(v) - 63.0 for k, v in json.load(f)["levels"].items()}
        self.lake_levels = levels

        # Base height: soften the 1.5 m Minecraft steps, then a cubic spline up to 6.25 m/px.
        soft = nd.gaussian_filter(self.h_src, 0.7)
        soft = np.where(self.h_src > 0, np.maximum(soft, 0.4), np.minimum(soft, -0.4))  # keep coasts
        self.base_mid = self._upsample(soft, order=3)
        self.base_coef = nd.spline_filter(self.base_mid, order=3, output=np.float32)
        sea_soft = nd.gaussian_filter(self.h_src, 2.0)
        self.sea_mid = self._upsample(sea_soft, order=1)
        log(f"  base height {time.time() - t0:.1f}s")

        mpx = WORLD_SIZE / MID_N
        land = self.base_mid > 0
        self.coast_sd = ((nd.distance_transform_edt(land) - nd.distance_transform_edt(~land)) * mpx).astype(np.float32)
        log(f"  coast distance {time.time() - t0:.1f}s")

        self._lakes(log, mpx)
        log(f"  lakes {time.time() - t0:.1f}s")
        self._rivers(log, mpx)
        log(f"  rivers {time.time() - t0:.1f}s")
        self._masks()
        log(f"  biome masks {time.time() - t0:.1f}s")

    def _despike(self, h, log):
        """The 25 m lookup samples single blocks, so Minecraft ravines and lone pillars show up as
        one-pixel slots and spikes (worst along Saltreach's spine). Inland, replace any pixel far
        from its neighbourhood median with that median; coasts, lakes and rivers are untouched."""
        med = nd.median_filter(h, size=5)
        inland = (nd.minimum_filter(h, size=7) > 1.5) & (self.lake_id == 0) & ~np.isin(self.biome, BIOMES_RIVER)
        bad = inland & (np.abs(h - med) > 22.0 + 0.12 * np.abs(med))
        bad = nd.binary_dilation(bad) & inland
        out = np.where(bad, med, h)
        # Long straight cuts one or two pixels wide (a trench along Saltreach's spine) survive a
        # median, so fill anything much lower than a small morphological closing of the ground.
        closed = nd.grey_closing(out, size=(5, 5))
        slot = inland & (closed - out > 18.0)
        slot = nd.binary_dilation(slot) & inland & (out < closed)
        out = np.where(slot, closed, out)
        # River biome painted along a ravine: the water would sit at the ravine floor. Lift river
        # pixels far below the surrounding non-river ground to just under that ground.
        river = np.isin(self.biome, BIOMES_RIVER) & (self.lake_id == 0)
        nr = (~river & (out > 0)).astype(np.float32)
        ground = nd.uniform_filter(out * nr, 9) / np.maximum(nd.uniform_filter(nr, 9), 1e-3)
        gully = river & (out > 0) & (ground - out > 10.0) & (nd.uniform_filter(nr, 9) > 0.2)
        out = np.where(gully, ground - 1.5, out)
        bad |= gully
        bad |= slot
        log(f"  despiked {int(bad.sum())} atlas pixels (ravines and pillars)")
        return out.astype(np.float32)

    @staticmethod
    def _upsample(src, order):
        c = (np.arange(MID_N, dtype=np.float32) + 0.5) * (SRC_N / MID_N) - 0.5
        jj, ii = np.meshgrid(c, c, indexing="ij")
        return nd.map_coordinates(src.astype(np.float32), [jj, ii], order=order, mode="nearest").astype(np.float32)

    def _lakes(self, log, mpx):
        lake = self.lake_id > 0
        soft = nd.gaussian_filter(self._upsample(lake.astype(np.float32), 1), 3.0)  # round off 25 m steps
        inside = soft > 0.5
        self.lake_sd = ((nd.distance_transform_edt(inside) - nd.distance_transform_edt(~inside)) * mpx).astype(np.float32)
        # Each mid pixel takes the level of the nearest lake pixel in the atlas.
        level_src = np.zeros(lake.shape, np.float32)
        for lid, lv in self.lake_levels.items():
            level_src[self.lake_id == lid] = lv
        idx = nd.distance_transform_edt(~lake, return_distances=False, return_indices=True)
        level_src = level_src[idx[0], idx[1]]
        self.lake_level = self._upsample(level_src, 0)
        # Outlines for the editor's lake water bodies.
        labels, n = nd.label(inside)
        self.lakes = []
        for k, sl in enumerate(nd.find_objects(labels), start=1):
            blob = labels[sl] == k
            area = blob.sum() * mpx * mpx
            if area < 2500:  # under 50 x 50 m: too small to bother with a water body
                continue
            ring = trace_outline(blob)
            ring = rdp(np.vstack([ring, ring[:1]]), 1.2)[:-1]
            if len(ring) < 3:
                continue
            j0, i0 = sl[0].start, sl[1].start
            cj, ci = nd.center_of_mass(blob)
            level = float(np.median(self.lake_level[sl][blob]))
            pts = [[WORLD_MIN + (i0 + p[1] + 0.5) * mpx, WORLD_MIN + (j0 + p[0] + 0.5) * mpx] for p in ring]
            cx, cz = WORLD_MIN + (i0 + ci + 0.5) * mpx, WORLD_MIN + (j0 + cj + 0.5) * mpx
            self.lakes.append({"level_m": round(level, 2), "area_m2": round(float(area)),
                               "centre_mc": [round(cx, 1), round(cz, 1)],
                               "outline_ue": [mc_to_ue(x, z, level)[:2] for x, z in pts]})
        log(f"  {len(self.lakes)} lakes with outlines")

    def _rivers(self, log, mpx):
        river = np.isin(self.biome, BIOMES_RIVER) & (self.lake_id == 0) & (self.h_src > -6)
        lab, n = nd.label(river, np.ones((3, 3)))
        sizes = np.bincount(lab.ravel())
        river &= sizes[lab] >= 8  # drop stray river-biome specks (under 200 m of river)
        skel = zhang_suen(river)
        half = nd.distance_transform_edt(river) * SRC_PX
        floor = nd.grey_erosion(self.h_src, size=(3, 3))
        surface = np.where(floor < 1.0, 0.0, floor - 0.3).astype(np.float32)  # sea-level or above
        width = np.clip(half * 0.55, 6.0, 40.0).astype(np.float32)
        # Mid-res centre lines: mark the upsampled skeleton pixels, distance to the nearest one.
        centre = np.zeros((MID_N, MID_N), bool)
        k = MID_N // SRC_N
        # Draw the centre lines between neighbouring skeleton pixels at mid resolution.
        for line in trace_skeleton(skel):
            arr = np.array(line, float)
            for a, b in zip(arr[:-1], arr[1:]):
                for t in np.linspace(0, 1, k + 1):
                    p = (a + (b - a) * t + 0.5) * k - 0.5
                    centre[int(round(p[0])), int(round(p[1]))] = True
        dist, idx = nd.distance_transform_edt(~centre, return_indices=True)
        self.river_dist = (dist * mpx).astype(np.float32)
        src_j = np.clip(((idx[0] + 0.5) / k - 0.5).round().astype(int), 0, SRC_N - 1)
        src_i = np.clip(((idx[1] + 0.5) / k - 0.5).round().astype(int), 0, SRC_N - 1)
        # nearest skeleton pixel in the source grid for width and surface
        sk_idx = nd.distance_transform_edt(~skel, return_distances=False, return_indices=True)
        nj, ni = sk_idx[0][src_j, src_i], sk_idx[1][src_j, src_i]
        self.river_level = surface[nj, ni]
        self.river_half = width[nj, ni]
        del dist, idx, sk_idx, nj, ni, src_j, src_i
        # Polylines for rivers that run above sea level (sea-level rivers are filled by the ocean).
        self.rivers = []
        for line in trace_skeleton(skel):
            if len(line) < 6:
                continue
            arr = np.array(line)
            lv = surface[arr[:, 0], arr[:, 1]]
            if np.median(lv) < 0.8:
                continue
            keep = list(range(0, len(arr), 2))
            if keep[-1] != len(arr) - 1:
                keep.append(len(arr) - 1)
            pts = []
            for n in keep:
                j, i = arr[n]
                x, z = WORLD_MIN + (i + 0.5) * SRC_PX, WORLD_MIN + (j + 0.5) * SRC_PX
                pts.append(mc_to_ue(x, z, float(lv[n])))
            self.rivers.append({"width_m": round(float(np.median(width[arr[:, 0], arr[:, 1]])) * 2, 1),
                                "points_ue": pts})
        log(f"  {len(self.rivers)} river reaches above sea level")

    def _masks(self):
        b, r = self.biome, self.region

        def soft(mask, sigma=1.0):
            return nd.gaussian_filter(mask.astype(np.float32), sigma)

        saltreach = np.isin(r, SALTREACH_REGIONS)
        self.src_masks = {
            "forest": soft(np.isin(b, BIOMES_FOREST)),
            "snow": soft(np.isin(b, BIOMES_SNOW)),
            "rock": soft(np.isin(b, BIOMES_ROCK)),
            "beach": soft(np.isin(b, BIOMES_BEACH)),
            "badlands": soft(np.isin(b, BIOMES_BADLANDS), 1.5),
            "salt": soft(np.isin(b, BIOMES_DESERT) & saltreach, 1.5),
            "desert": soft(np.isin(b, BIOMES_DESERT) & ~saltreach, 1.5),
            "mountain": np.maximum(soft(np.isin(b, BIOMES_MOUNTAIN), 2.0),
                                   smoothstep(nd.gaussian_filter(self.h_src, 2.0), 50.0, 150.0)),
        }

    # -- sampling helpers (world MC coordinates in metres)

    @staticmethod
    def _mid_coords(x, z):
        return (z - WORLD_MIN) / WORLD_SIZE * MID_N - 0.5, (x - WORLD_MIN) / WORLD_SIZE * MID_N - 0.5

    @staticmethod
    def _src_coords(x, z):
        return (z - WORLD_MIN) / SRC_PX - 0.5, (x - WORLD_MIN) / SRC_PX - 0.5

    def base(self, x, z):
        j, i = self._mid_coords(x, z)
        return nd.map_coordinates(self.base_coef, [j, i], order=3, mode="nearest", prefilter=False)

    def mid(self, name, x, z, order=1):
        j, i = self._mid_coords(x, z)
        return nd.map_coordinates(getattr(self, name), [j, i], order=order, mode="nearest")

    def src_mask(self, name, x, z):
        j, i = self._src_coords(x, z)
        return nd.map_coordinates(self.src_masks[name], [j, i], order=1, mode="nearest")


# ----------------------------------------------------------------------------- the terrain function

def canon_keep(x, z):
    keep = np.zeros(np.shape(x), np.float32)
    for x0, z0, x1, z1, f in CANON_BOXES:
        dx = np.maximum(np.maximum(x0 - x, x - x1), 0.0)
        dz = np.maximum(np.maximum(z0 - z, z - z1), 0.0)
        keep = np.maximum(keep, 1.0 - smoothstep(np.hypot(dx, dz), 0.0, f))
    return keep


def volcanoes(F, x, z, h, base, noise):
    """Returns (new height, volcanic weight)."""
    volc = np.zeros(np.shape(x), np.float32)
    for _name, vx, vz, radius, rim, crater_r, crater_d in VOLCANOES:
        dx, dz = x - vx, z - vz
        if np.min(np.abs(dx)) > radius * 1.3 or np.min(np.abs(dz)) > radius * 1.3:
            continue
        ang = np.arctan2(dz, dx)
        wob = 1.0 + 0.08 * noise.fbm(np.cos(ang) * 300.0 + vx, np.sin(ang) * 300.0 + vz, 250.0, 3, salt=9)
        r = np.hypot(dx, dz) / wob
        top = rim if rim is not None else base_at(vx, vz, F.base)
        # Concave cone rising out of the existing ground: steep near the rim, a wide skirt below.
        tc = np.clip((r - crater_r) / (radius - crater_r), 0.0, 1.0)  # 0 at the rim
        rise = (1.0 - tc) ** 1.7
        gully = noise.ridged(*noise.warp(x, z, 400.0, 120.0, salt=13), 160.0, 3, salt=13)
        land = smoothstep(base, 4.0, 45.0)  # never touches the coast
        if rim is not None:
            smooth_cone = base + (top - base) * rise - gully * 12.0 * np.sin(np.pi * tc)
            # The upper cone replaces the mountain noise so the shape reads from afar; the skirt
            # only lifts the ground and keeps the spine's own ridges.
            own = 1.0 - smoothstep(tc, 0.35, 0.8)
            raised = lerp(np.maximum(h, smooth_cone), smooth_cone, own)
            raised = np.where(r < radius, raised, h)
        else:
            raised = h
        h = lerp(h, raised, land)
        # Crater: a bowl inside the rim with a narrow lip.
        rim_h = np.where(r < crater_r * 1.6, h, 0.0)
        bowl_t = np.clip(r / crater_r, 0.0, 1.0)
        bowl = top + 4.0 - crater_d * (1.0 - bowl_t ** 2.2)
        lip = smoothstep(r, crater_r * 0.85, crater_r * 1.25)
        crater_h = lerp(np.minimum(rim_h, bowl), h, lip)
        h = np.where(r < crater_r * 1.25, crater_h, h)
        volc = np.maximum(volc, (1.0 - smoothstep(r, radius * 0.45, radius * 0.75)) * land)
    return h, volc


_BASE_CACHE = {}


def base_at(x, z, base_fn):
    key = (x, z)
    if key not in _BASE_CACHE:
        _BASE_CACHE[key] = float(base_fn(np.array([x]), np.array([z]))[0])
    return _BASE_CACHE[key]


def terrain(F, noise, x, z):
    """Height (m above sea) and layer weights for arrays of world positions."""
    b = F.base(x, z)
    sd = F.mid("coast_sd", x, z)
    keep = canon_keep(x, z)
    free = 1.0 - keep
    land_w = smoothstep(b, 0.3, 10.0) * free
    mtn = F.src_mask("mountain", x, z)

    # Mountains: domain-warped ridged noise, scaled with height so peaks get the drama.
    wx, wz = noise.warp(x, z, 1800.0, 650.0, salt=1)
    ridges = noise.ridged(wx, wz, 1100.0, 5, salt=1)
    mountain_detail = (ridges - 0.32) * (8.0 + 0.24 * np.clip(b, 0, 260)) * mtn
    # Plains and hills: gentle rolling ground, plus small bumps everywhere on land.
    rolling = (noise.fbm(x, z, 900.0, 3, salt=2) * 4.0 + noise.fbm(x, z, 230.0, 3, salt=3) * 1.2) * (1.0 - mtn)
    micro = noise.fbm(x, z, 45.0, 2, salt=4) * 0.35
    h = b + (mountain_detail + rolling + micro) * land_w

    # Saltreach badlands: terraced mesas with crisp steps and soft treads.
    bad = F.src_mask("badlands", x, z) * smoothstep(b, 6.0, 25.0) * free
    step = 9.0 + noise.fbm(x, z, 700.0, 2, salt=5) * 2.5
    q = h / step
    tread = np.floor(q)
    frac = q - tread
    terraced = (tread + smoothstep(frac, 0.72, 0.96)) * step
    h = lerp(h, terraced + noise.fbm(x, z, 60.0, 2, salt=6) * 0.6, bad * 0.9)

    # Salt flats: smooth and nearly level, a hair above the sea.
    salt = F.src_mask("salt", x, z) * smoothstep(b, 0.5, 3.0)
    salt_ground = np.maximum(b, 0.8) + noise.fbm(x, z, 300.0, 2, salt=7) * 0.15
    h = lerp(h, salt_ground, np.clip(salt * 1.4, 0, 1) * free)

    # Volcanoes (canon: West Volcano on Saltreach's spine; Sunreach's crater).
    h, volc = volcanoes(F, x, z, h, b, noise)

    # Rivers: carve a channel under the river surface, softly banked.
    rd = F.mid("river_dist", x, z)
    near_river = rd < 120.0
    river_bed = np.zeros_like(h)
    water = np.where(F.mid("coast_sd", x, z) < 0, 0.0, -1e4).astype(np.float32)  # sea surface
    if near_river.any():
        rl = F.mid("river_level", x, z, order=0)
        hw = F.mid("river_half", x, z)
        depth = 1.2 + hw * 0.08
        inner = rl - depth * (1.0 - np.clip(rd / hw, 0, 1) ** 2)
        bank = rl + np.maximum(rd - hw, 0.0) * 0.18
        profile = np.where(rd < hw, inner, bank)
        carve = (1.0 - smoothstep(rd, hw + 25.0, hw + 90.0)) * (b > -3.0) * np.maximum(free, 0.3)
        h = np.where(near_river, lerp(h, np.minimum(h, profile), carve), h)
        river_bed = (1.0 - smoothstep(rd, hw, hw + 8.0)) * (b > -1.0)
        water = np.where(near_river & (rd < hw), np.maximum(water, rl), water)

    # Lakes: smooth basins below each lake's own water level, with a lip so water stays in.
    lsd = F.mid("lake_sd", x, z)
    near_lake = lsd > -60.0
    lake_shore = np.zeros_like(h)
    if near_lake.any():
        lv = F.mid("lake_level", x, z, order=0)
        floor = lv - 0.5 - 6.0 * smoothstep(lsd, 0.0, 90.0)
        h = np.where(lsd > 0, np.minimum(h, lerp(h, floor, smoothstep(lsd, -2.0, 12.0))), h)
        lip = lv + 0.25 + np.maximum(-lsd - 8.0, 0.0) * 0.05
        lip_w = smoothstep(lsd, -40.0, -20.0) * (lsd <= 0)
        h = lerp(h, np.maximum(h, np.minimum(lip, h + 1.5)), lip_w)
        lake_shore = (1.0 - smoothstep(lsd, -10.0, -3.0)) * (lsd > -10.0) * (lsd < 6.0)
        water = np.where(lsd > 0, np.maximum(water, lv), water)

    # Beaches: a soft shelf where the map has sand.
    beach = np.maximum(F.src_mask("beach", x, z), F.src_mask("desert", x, z) * 0.5) * (1.0 - mtn)
    shelf_land = 0.12 + np.maximum(sd, 0.0) * 0.035
    beach_w = beach * (1.0 - smoothstep(sd, 70.0, 160.0)) * (sd > 0) * free
    h = lerp(h, np.minimum(h, shelf_land), beach_w)

    # Under the sea: a smoother seabed, a gentle slope off the beach, small sand ripples.
    sea = F.mid("sea_mid", x, z)
    seabed = np.minimum(sea, -0.6) + noise.fbm(x, z, 260.0, 3, salt=8) * 1.4
    shelf = -0.25 + sd * 0.045  # sd < 0 at sea
    shelf_w = (1.0 - smoothstep(-sd, 50.0, 220.0)) * free
    seabed = lerp(seabed, np.maximum(seabed, shelf), shelf_w)
    seabed = np.minimum(seabed, -0.25)
    under = 1.0 - smoothstep(sd, -12.0, 0.0)
    h = np.where(sd < 0, lerp(np.minimum(h, -0.25), seabed, under), h)
    # Keep every coastline where the map has it: land stays above the sea unless a lake or a
    # sea-level river was carved there on purpose.
    carved = (river_bed > 0.3) | (lake_shore > 0.3) | (lsd > 0)
    h = np.where((sd > 0) & ~carved, np.maximum(h, 0.1), h)
    h = np.clip(h, H_MIN + 1.0, H_MIN + H_SPAN - 1.0)

    masks = {
        "forest": F.src_mask("forest", x, z), "snow": F.src_mask("snow", x, z),
        "rock": F.src_mask("rock", x, z), "badlands": bad, "salt": salt, "volcanic": volc,
        "beach": np.maximum(beach_w, (sd < 25.0) * (h < 2.5) * (1.0 - mtn)),
        "river": river_bed, "lake_shore": lake_shore, "sea": (h < -0.4).astype(np.float32),
        "desert": F.src_mask("desert", x, z), "water": np.maximum(water, 0.0) * (water > h),
    }
    return h.astype(np.float32), masks


def weights(h, masks, noise, x, z, metres_per_px):
    """Paint layer weights (0..1, summing to 1) from height, slope and the biome masks."""
    gy, gx = np.gradient(h, metres_per_px)
    slope = np.hypot(gx, gy)  # rise over run
    steep = smoothstep(slope, 0.55, 0.95)  # ~29 to ~44 degrees
    jitter = noise.fbm(x, z, 120.0, 2, salt=20) * 0.25

    w = {name: np.zeros_like(h) for name in LAYERS}
    w["Grass"] += 0.35
    w["Forest"] += np.clip(masks["forest"] * 1.3 + jitter, 0, 1)
    w["Sand"] += np.clip(np.maximum.reduce([masks["beach"], masks["desert"], masks["river"], masks["lake_shore"],
                                            masks["sea"]]) * 1.5, 0, 1.5)
    w["Badlands"] += np.clip(masks["badlands"] * 1.6, 0, 1.6)
    w["Salt"] += np.clip(masks["salt"] * 1.8 - steep, 0, 1.8)
    w["Volcanic"] += np.clip(masks["volcanic"] * 1.8, 0, 1.8)
    snowline = smoothstep(h, 165.0 + jitter * 60.0, 200.0)
    w["Snow"] += np.clip(np.maximum(masks["snow"], snowline) * 1.4 * (1.0 - steep * 0.75), 0, 1.4)
    rock = np.maximum(masks["rock"] * 0.9, steep) * (1.0 - masks["badlands"]) * (1.0 - masks["volcanic"] * 0.8)
    w["Rock"] += np.clip(rock * 2.2, 0, 2.2) * (1.0 - masks["sea"])
    for name in LAYERS:
        if name not in ("Sand", "Rock"):
            w[name] *= 1.0 - masks["sea"]
    total = sum(w.values()) + 1e-6
    return {k: v / total for k, v in w.items()}, slope


def to_u8_weights(wts):
    """Quantises weights to bytes that sum to exactly 255 per pixel."""
    stack = np.stack([wts[n] for n in LAYERS])
    q = np.floor(stack * 255.0).astype(np.int32)
    short = 255 - q.sum(axis=0)
    top = np.argmax(stack, axis=0)
    np.put_along_axis(q, top[None], np.take_along_axis(q, top[None], 0) + short[None], 0)
    return {n: q[k].astype(np.uint8) for k, n in enumerate(LAYERS)}


# ----------------------------------------------------------------------------- tiles

_F = None
_NOISE = None


def _init_worker(fields, seed):
    global _F, _NOISE
    _F, _NOISE = fields, Noise(seed)


def bake_tile(args):
    tx, ty, tile_px, total_px, out_dir, preview_px = args
    step = WORLD_SIZE / (total_px - 1)
    gx = np.arange(tx * tile_px - 1, (tx + 1) * tile_px + 1, dtype=np.float64)
    gy = np.arange(ty * tile_px - 1, (ty + 1) * tile_px + 1, dtype=np.float64)
    zz, xx = np.meshgrid(WORLD_MIN + gy * step, WORLD_MIN + gx * step, indexing="ij")
    h, masks = terrain(_F, _NOISE, xx, zz)
    wts, slope = weights(h, masks, _NOISE, xx, zz, step)
    c = (slice(1, -1), slice(1, -1))
    h = h[c]
    enc = np.clip(np.round((h - H_MIN) / H_SPAN * 65535.0), 0, 65535).astype(np.uint16)
    Image.fromarray(enc).save(os.path.join(out_dir, f"World_Height_x{tx}_y{ty}.png"))
    for name, arr in to_u8_weights({k: v[c] for k, v in wts.items()}).items():
        Image.fromarray(arr).save(os.path.join(out_dir, f"World_{name}_x{tx}_y{ty}.png"))
    # small copies for the preview
    k = tile_px // preview_px
    small_h = h[k // 2::k, k // 2::k][:preview_px, :preview_px]
    wl = np.where(masks["water"][c] > 0, masks["water"][c], np.where(h < 0, 0.0, -1e4))
    small_water = wl[k // 2::k, k // 2::k][:preview_px, :preview_px]
    small_w = np.stack([wts[n][c][k // 2::k, k // 2::k][:preview_px, :preview_px] for n in LAYERS])
    stats = (float(h.min()), float(h.max()), float((h > 0).mean()), float(np.percentile(slope[c], 99)))
    return tx, ty, small_h, small_w, small_water, stats


PREVIEW_COLOURS = {  # house palette (Harbor PALETTE / ISLAND_PALETTE)
    "Grass": "9DB872", "Forest": "6E9061", "Sand": "EFE2C4", "Rock": "D6BC9F",
    "Snow": "F7EEDC", "Badlands": "C8643A", "Salt": "F1E9DC", "Volcanic": "36221A",
}


def hex_rgb(hex_str):
    return np.array([int(hex_str[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0


def save_preview(h, w, water_level, metres_per_px, path, max_bytes=1_000_000):
    """Coloured shaded relief, warm light from the north-west; sea tinted by depth."""
    gy, gx = np.gradient(h * 2.0, metres_per_px)
    nx, ny, nz = -gx, -gy, np.ones_like(h)
    n = np.sqrt(nx * nx + ny * ny + 1.0)
    light = np.array([-0.55, -0.55, 0.63])
    shade = np.clip((nx * light[0] + ny * light[1] + nz * light[2]) / n, 0, 1)
    colour = sum(w[k][..., None] * hex_rgb(PREVIEW_COLOURS[name]) for k, name in enumerate(LAYERS))
    colour = colour * (0.35 + 0.85 * shade[..., None])
    deep, shallow = hex_rgb("2E8A9C"), hex_rgb("7FD0D6")
    t = np.clip(0.25 + (water_level - h) / 40.0, 0, 1)[..., None]
    water = shallow * (1 - t) + deep * t
    water = water * (0.85 + 0.15 * shade[..., None])
    rgb = np.where((water_level > h)[..., None], water, colour)
    img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
    for q in (88, 80, 70, 60, 50):
        img.save(path, quality=q, optimize=True)
        if os.path.getsize(path) <= max_bytes:
            break
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", action="store_true", help="8 x 8 tiles of 256 px (fast check, not for import)")
    ap.add_argument("--tiles", type=int, help="tiles per side (default 8)")
    ap.add_argument("--tile-size", type=int, help="pixels per tile side (default 2048)")
    ap.add_argument("--out", default=os.path.join(HERE, "tiles"), help="output folder")
    ap.add_argument("--workers", type=int, default=1, help="tiles baked in parallel")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--only", help="bake one tile, e.g. 3,2 (for testing)")
    args = ap.parse_args(argv)

    tiles = args.tiles or (PREVIEW_TILES if args.preview else FULL_TILES)
    tile_px = args.tile_size or (PREVIEW_TILE_PX if args.preview else FULL_TILE_PX)
    total = tiles * tile_px
    valid = (total - 1) % QUADS_PER_COMPONENT == 0
    os.makedirs(args.out, exist_ok=True)
    print(f"[Lyris] terrain bake v{BAKE_VERSION}, seed {args.seed}: {tiles} x {tiles} tiles of {tile_px} px "
          f"= {total} px, {WORLD_SIZE / (total - 1):.3f} m per vertex")
    if not valid:
        print(f"[Lyris] note: {total} - 1 is not a multiple of {QUADS_PER_COMPONENT}; fine for a preview, "
              "but UE will pad or crop it on import")

    t0 = time.time()
    print("[Lyris] whole-map fields ...")
    fields = Fields()
    _init_worker(fields, args.seed)

    preview_px = max(1, min(tile_px, 2048 // tiles))
    jobs = [(tx, ty, tile_px, total, args.out, preview_px) for ty in range(tiles) for tx in range(tiles)]
    if args.only:
        ox, oy = (int(v) for v in args.only.split(","))
        jobs = [j for j in jobs if j[0] == ox and j[1] == oy]
    big_h = np.zeros((tiles * preview_px, tiles * preview_px), np.float32)
    big_w = np.zeros((len(LAYERS), tiles * preview_px, tiles * preview_px), np.float32)
    lo, hi, land = 1e9, -1e9, []
    if args.workers > 1 and len(jobs) > 1:
        pool = ProcessPoolExecutor(args.workers, initializer=_init_worker, initargs=(fields, args.seed))
        results = pool.map(bake_tile, jobs)
    else:
        pool, results = None, map(bake_tile, jobs)
    big_water = np.zeros_like(big_h)
    for n, (tx, ty, sh, sw, swl, stats) in enumerate(results, start=1):
        sl = (slice(ty * preview_px, (ty + 1) * preview_px), slice(tx * preview_px, (tx + 1) * preview_px))
        big_h[sl] = sh
        big_water[sl] = swl
        big_w[(slice(None),) + sl] = sw
        lo, hi = min(lo, stats[0]), max(hi, stats[1])
        land.append(stats[2])
        print(f"[Lyris] tile x{tx} y{ty}  {n}/{len(jobs)}  {stats[0]:7.1f} .. {stats[1]:6.1f} m  "
              f"land {stats[2] * 100:4.1f}%  ({time.time() - t0:.0f}s)", flush=True)
    if pool:
        pool.shutdown()

    step_m = WORLD_SIZE / (total - 1)
    scale_xy = step_m * 100.0
    sx, sy, sz = SPAWN_MC
    spawn_h, _ = terrain(fields, Noise(args.seed), np.array([sx]), np.array([sz]))
    manifest = {
        "bake_version": BAKE_VERSION, "seed": args.seed, "preview": not valid or args.preview,
        "coordinates": "MC X -> UE X, MC Z -> UE Y, UE Z = (MC Y - 63) * 100; 1 m = 100 uu",
        "tiles_x": tiles, "tiles_y": tiles, "tile_resolution": tile_px, "total_resolution": total,
        "quads_per_section": QUADS_PER_COMPONENT, "sections_per_component": 1,
        "components_x": (total - 1) // QUADS_PER_COMPONENT if valid else None,
        "metres_per_vertex": round(step_m, 5),
        "scale": [round(scale_xy, 5), round(scale_xy, 5), 100.0],
        "location_corner": [WORLD_MIN * 100.0, WORLD_MIN * 100.0, (H_MIN + H_SPAN / 2) * 100.0],
        "location_centre": [0.0, 0.0, (H_MIN + H_SPAN / 2) * 100.0],
        "height_encoding": {"min_m": H_MIN, "max_m": H_MIN + H_SPAN, "sea_level_value": round(-H_MIN / H_SPAN * 65535)},
        "height_range_m": [round(lo, 2), round(hi, 2)],
        "heightmap_pattern": "World_Height_x{X}_y{Y}.png",
        "first_heightmap": "World_Height_x0_y0.png",
        "layers": [{"name": n, "pattern": f"World_{n}_x{{X}}_y{{Y}}.png", "first": f"World_{n}_x0_y0.png"}
                   for n in LAYERS],
        "tiles": [f"x{tx}_y{ty}" for ty in range(tiles) for tx in range(tiles)],
        "world_bounds_ue": [WORLD_MIN * 100.0, -WORLD_MIN * 100.0],
        "sea_level_z": 0.0,
        "spawn": {"mc": list(SPAWN_MC), "ue": mc_to_ue(sx, sz, float(spawn_h[0]) + 1.0), "yaw": -90.0,
                  "ground_m": round(float(spawn_h[0]), 2)},
        "volcanoes": [{"name": v[0], "ue": mc_to_ue(v[1], v[2]), "crater_radius_m": v[5]} for v in VOLCANOES],
        "lakes": fields.lakes,
        "rivers": fields.rivers,
    }
    with open(os.path.join(args.out, "terrain_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    norm = big_w / np.maximum(big_w.sum(axis=0, keepdims=True), 1e-6)
    prev = save_preview(big_h, norm, big_water, WORLD_SIZE / big_h.shape[0], os.path.join(args.out, "preview_hillshade.jpg"))

    # Coastline check against the atlas: land/sea agreement on the 25 m grid.
    c = (np.arange(SRC_N) + 0.5) / SRC_N * big_h.shape[0] - 0.5
    jj, ii = np.meshgrid(c, c, indexing="ij")
    ours = nd.map_coordinates(big_h, [jj, ii], order=1) > 0
    atlas = fields.h_src > 0
    agree = (ours == atlas).mean() * 100
    print(f"[Lyris] done in {time.time() - t0:.0f}s: {len(jobs)} tiles, heights {lo:.1f} .. {hi:.1f} m, "
          f"land {ours.mean() * 100:.1f}% (atlas {atlas.mean() * 100:.1f}%), coast agreement {agree:.2f}%, "
          f"{len(fields.lakes)} lakes, {len(fields.rivers)} upland river reaches, spawn ground "
          f"{float(spawn_h[0]):.1f} m")
    print(f"[Lyris] scale {scale_xy:.4f} x {scale_xy:.4f} x 100, preview {prev}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
