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

BAKE_VERSION = 3  # 2: new island chains A to H (T36); 3: natural wonders and map biomes (T49)
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

# Ground pads for canon builds the 25 m atlas is too coarse to hold (thin headlands, quays, a
# statue islet, flat build platforms). Levels are MC Y. mode "raise" only lifts ground (never
# digs), "set" flattens to the level. Shapes: ("circle", x, z, r), ("box", x0, z0, x1, z1),
# ("line", x0, z0, x1, z1, width, y at the far end). Each fades out over `feather` metres.
CANON_PADS = [  # (name, shape, MC Y, feather m, mode)
    ("Ilwen's headland", ("circle", 127, -2343, 20), 69.0, 18.0, "raise"),
    ("Harbour promenade and Chapel of Lamps", ("box", 112, -2357, 250, -2300), 64.5, 12.0, "raise"),
    ("East quay", ("box", 266, -2527, 310, -2360), 64.0, 8.0, "raise"),
    ("Syrena's islet", ("circle", 247, -2462, 9), 64.0, 6.0, "raise"),
    ("Keep Elariel bailey", ("box", 466, -2568, 580, -2524), 138.0, 20.0, "set"),
    ("Observatory platform", ("circle", 1326, -2980, 34), 263.0, 30.0, "set"),
    ("Delvers' court", ("circle", 1800, -3955, 18), 155.0, 10.0, "set"),
    ("Delvers' cleft", ("line", 1660, -3950, 1785, -3955, 10, 155.0), 136.0, 8.0, "set"),
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

# New island chains A to H (design/world_map.md section 4, approved 2026-10-20). Each islet is an
# ellipse: (MC x, MC z, radius x m, radius z m, rotation deg, peak m above sea, profile). Profiles:
#   skerry   low rough rock dome          hill     rounded wooded hills
#   plateau  flat top, soft low cliffs    dune     low sand dunes
#   stack    sheer sea stack, flat top    ice      snow dome with icy cliffs
#   pale     smooth, washed-out rolling   rocky    ridged rocky hills, no cone
# Biome weights feed the paint layers (forest, rock, snow, sand, pale = the Salt layer's cream).
# "beach" (0..1) is how much soft sand shelf the coast gets; cliff profiles get none.
# Every islet keeps at least 250 m of open water from the existing coasts (checked at bake start).
ISLANDS = [
    {"id": "A", "name": "Lampwick Skerries", "beach": 0.2,
     "biome": {"rock": 0.75, "forest": 0.0},
     "islets": [(-3250, -4700, 70, 45, 20, 12.0, "skerry"), (-2950, -4615, 50, 35, 10, 8.0, "skerry"),
                (-2650, -4520, 60, 40, 15, 11.0, "skerry"), (-2350, -4430, 45, 32, 0, 7.0, "skerry"),
                (-2050, -4400, 75, 50, -10, 14.0, "skerry"), (-1750, -4440, 55, 38, -20, 9.0, "skerry")]},
    {"id": "B", "name": "Hushed Isles", "beach": 0.35,
     "biome": {"forest": 1.0, "rock": 0.15},
     "islets": [(-7900, -4950, 340, 290, 30, 42.0, "hill"), (-7350, -4650, 270, 220, -15, 34.0, "hill"),
                (-8150, -4430, 210, 170, 60, 28.0, "hill"), (-7520, -5320, 160, 130, 0, 22.0, "hill"),
                (-7020, -5050, 115, 95, 40, 16.0, "hill")]},
    {"id": "C", "name": "Wickstones", "beach": 0.5,
     "biome": {"forest": 0.15},
     "islets": [(7850, 1900, 260, 230, 10, 10.0, "plateau", "clearing"), (8260, 1680, 175, 140, -25, 9.0, "plateau"),
                (7700, 2350, 150, 120, 35, 8.0, "plateau"), (8220, 2220, 120, 100, 0, 7.0, "plateau")]},
    {"id": "D", "name": "Tallow Banks", "beach": 1.0,
     "biome": {"sand": 0.85, "forest": 0.0},
     "islets": [(10200, -1000, 310, 160, 25, 7.0, "dune"), (10650, -640, 240, 130, 40, 6.0, "dune"),
                (9850, -650, 200, 110, 10, 5.0, "dune"), (10560, -1270, 170, 100, 30, 4.5, "dune")]},
    {"id": "E", "name": "Southing Stones", "beach": 0.25,
     "biome": {"rock": 0.6, "forest": 0.0},
     "islets": [(0, 6900, 280, 220, 15, 22.0, "hill"), (420, 6680, 75, 65, 0, 60.0, "stack"),
                (390, 7120, 95, 80, 30, 48.0, "stack")]},
    {"id": "F", "name": "Rime Skerries", "beach": 0.0,
     "biome": {"snow": 1.0, "rock": 0.3},
     "islets": [(-300, -10100, 480, 400, 20, 52.0, "ice"), (620, -9740, 380, 320, -30, 44.0, "ice"),
                (820, -10430, 300, 260, 10, 36.0, "ice"), (-260, -9290, 250, 200, 45, 28.0, "ice")]},
    {"id": "G", "name": "Unremembered Isles", "beach": 0.6,
     "biome": {"pale": 0.45, "forest": 0.7, "rock": 0.1},  # washed-out, half-drawn green
     "islets": [(-100, 10500, 640, 560, 20, 68.0, "pale"), (1450, 10200, 520, 470, -20, 56.0, "pale"),
                (1000, 11300, 440, 400, 50, 46.0, "pale")]},
    {"id": "H", "name": "Ember Isle", "beach": 0.15,
     "biome": {"forest": 0.85, "rock": 0.45},
     "islets": [(-7800, 8900, 850, 700, 25, 95.0, "rocky"), (-6600, 9500, 210, 170, 0, 30.0, "rocky")]},
]
ISLAND_SHELF = {"skerry": 0.08, "hill": 0.05, "plateau": 0.12, "dune": 0.03, "stack": 0.45, "ice": 0.12,
                "pale": 0.05, "rocky": 0.08}  # underwater slope off the coast (m down per m out)
ISLAND_CLEARING_R = (38.0, 70.0)  # Wickstones ring clearing: flat and treeless inside, blended out to here


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
        self._ref_masks(log)
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

    def _ref_masks(self, log):
        """Snow, dark forest and pale grey rock read off the user's labelled map (T49), on the 25 m grid."""
        self.ref_masks = None
        if not os.path.exists(REFERENCE_MAP):
            log(f"  [Lyris] WARNING reference map not found ({REFERENCE_MAP}); biomes follow the atlas only")
            return
        img = Image.open(REFERENCE_MAP).convert("RGB")
        k = 2
        img = img.resize((img.width // k, img.height // k), Image.BOX)
        a = nd.gaussian_filter(np.asarray(img).astype(np.float32), (1.3, 1.3, 0))
        ax, bx, az, bz = REFERENCE_FIT
        c = (np.arange(SRC_N) + 0.5) * SRC_PX + WORLD_MIN
        zz, xx = np.meshgrid(c, c, indexing="ij")
        px, py = (ax + bx * xx) / k - 0.5, (az + bz * zz) / k - 0.5
        R, G, B = (nd.map_coordinates(a[..., i], [py, px], order=1, mode="nearest") for i in range(3))
        chroma = np.maximum(np.maximum(R, G), B) - np.minimum(np.minimum(R, G), B)
        lum = (R + G + B) / 3.0
        land = self.h_src > 0
        north = zz < -2500
        snow = land & north & (((chroma < 16) & (lum > 150)) | ((chroma < 11) & (lum > 105) & (zz < -3500)))
        snow = nd.binary_closing(snow, iterations=2) & land
        forest = land & (G > R + 10) & (G > B + 25) & (lum < 168)
        grey = land & (chroma < 26) & (G - B < 26) & (lum > 150) & (zz > 2500) & (xx > -500) & (xx < 2600)
        grey &= ~np.isin(self.region, [7, 8, 9])  # Sunreach only: Greengrace's pale tip is not the Curtain
        grey = nd.binary_closing(nd.binary_opening(grey, iterations=1), iterations=3) & land
        self.ref_masks = {n: nd.gaussian_filter(m.astype(np.float32), s)
                          for n, m, s in (("snow", snow, 1.2), ("forest", forest, 1.0), ("grey", grey, 1.5))}
        log(f"  reference map masks: snow {snow.sum() * 625 / 1e6:.1f} km2, forest {forest.sum() * 625 / 1e6:.1f} km2, "
            f"grey rock {grey.sum() * 625 / 1e6:.1f} km2")

    def ref(self, name, x, z):
        if self.ref_masks is None:
            return np.zeros(np.shape(x), np.float32)
        j, i = self._src_coords(x, z)
        return nd.map_coordinates(self.ref_masks[name], [j, i], order=1, mode="nearest")

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


def _islet_frame(islet, x, z):
    """Normalised radius (0 centre, 1 mean coast) of points in an islet's rotated ellipse."""
    cx, cz, rx, rz, rot = islet[:5]
    a = np.radians(rot)
    dx, dz = x - cx, z - cz
    u = (dx * np.cos(a) + dz * np.sin(a)) / rx
    v = (-dx * np.sin(a) + dz * np.cos(a)) / rz
    return np.hypot(u, v)


def _islet_profile(kind, t, x, z, noise, salt):
    """Land shape 0..1 (1 = peak) for t in 0..1."""
    tl = np.clip(t, 0.0, 1.0)
    if kind == "skerry":
        rough = noise.ridged(x, z, 45.0, 3, salt=salt)
        return (1.0 - tl ** 2) ** 0.8 * (0.7 + 0.5 * rough)
    if kind == "hill":
        lumps = noise.fbm(x, z, 140.0, 3, salt=salt)
        return np.clip((1.0 - tl ** 1.8) ** 1.4 * (0.8 + 0.35 * lumps), 0, None)
    if kind == "plateau":
        return (1.0 - smoothstep(tl, 0.72, 1.0)) * (0.92 + 0.08 * noise.fbm(x, z, 90.0, 2, salt=salt))
    if kind == "dune":
        wx, wz = noise.warp(x, z, 160.0, 40.0, salt=salt)
        ripples = noise.ridged(wx, wz * 0.45, 70.0, 2, salt=salt + 1)  # long dune crests
        return (1.0 - tl ** 2) ** 1.2 * (0.55 + 0.45 * ripples)
    if kind == "stack":
        return (1.0 - smoothstep(tl, 0.8, 1.0)) * (0.94 + 0.06 * noise.fbm(x, z, 30.0, 2, salt=salt))
    if kind == "ice":
        return (1.0 - tl ** 2.6) ** 1.1 * (0.85 + 0.2 * noise.fbm(x, z, 160.0, 3, salt=salt))
    if kind == "pale":
        return (1.0 - tl ** 2) ** 1.6 * (0.9 + 0.12 * noise.fbm(x, z, 300.0, 2, salt=salt))
    if kind == "rocky":
        wx, wz = noise.warp(x, z, 500.0, 160.0, salt=salt)
        ridges = noise.ridged(wx, wz, 380.0, 4, salt=salt)
        return np.clip((1.0 - tl ** 1.6) ** 1.3 * (0.55 + 0.6 * ridges), 0, None)
    raise ValueError(f"unknown islet profile {kind}")


def _islet_reach(islet):
    """How far (m) from the centre the islet's shape and shelf can matter."""
    return max(islet[2], islet[3]) * 1.5 + 650.0


def islands(x, z, h, noise):
    """Sculpts the new island chains into the sea. Returns (height, masks dict, island land 0..1)."""
    out = {k: np.zeros(np.shape(x), np.float32) for k in ("forest", "rock", "snow", "sand", "pale", "clearing")}
    land_all = np.zeros(np.shape(x), np.float32)
    for ci, chain in enumerate(ISLANDS):
        for k, islet in enumerate(chain["islets"]):
            cx, cz, rx, rz, _rot, peak, kind = islet[:7]
            reach = _islet_reach(islet)
            sel = (np.abs(x - cx) < reach) & (np.abs(z - cz) < reach)
            if not sel.any():
                continue
            salt = 40 + ci * 8 + k
            xs, zs = x[sel], z[sel]
            # Natural coastline: warp the ellipse with noise scaled to the islet's size.
            size = (rx + rz) * 0.5
            wx, wz = noise.warp(xs, zs, max(size * 0.7, 40.0), size * 0.3, salt=salt)
            t = _islet_frame(islet, wx, wz)
            t = t / (1.0 + 0.22 * noise.fbm(xs, zs, max(size * 0.3, 25.0), 4, salt=salt + 2))
            # Headlands and coves: a few lobes around the outline, so no islet reads as a blob.
            ang = np.arctan2(zs - cz, xs - cx)
            lobes = noise.fbm(np.cos(ang) * 900.0 + cx, np.sin(ang) * 900.0 + cz, 520.0, 3, salt=salt + 6)
            t = t / (1.0 + 0.32 * lobes * smoothstep(t, 0.3, 0.8))
            f = _islet_profile(kind, t, xs, zs, noise, salt)
            land = np.maximum(peak * f, 0.15 + (1.0 - np.clip(t, 0, 1)) * size * 0.02)
            if chain["beach"] > 0 and kind not in ("stack", "skerry"):
                from_coast = (1.0 - np.clip(t, 0, 1)) * size
                shelf_land = 0.12 + from_coast * 0.035
                bw = chain["beach"] * (1.0 - smoothstep(from_coast, 18.0, 45.0))
                land = lerp(land, np.minimum(land, shelf_land), bw)
            clear_w = np.zeros_like(xs, dtype=np.float32)
            if "clearing" in islet[7:]:
                d = np.hypot(xs - cx, zs - cz)
                clear_w = (1.0 - smoothstep(d, *ISLAND_CLEARING_R)).astype(np.float32)
                land = lerp(land, np.float32(peak), clear_w)
            # The shelf slopes off the coast, then drops well below the seabed long before the edge of
            # the sampled box, so the open seabed takes over without a seam.
            out_m = np.maximum(t - 1.0, 0.0) * size
            under = (-0.3 - out_m * ISLAND_SHELF[kind] - smoothstep(out_m, 120.0, 420.0) * 80.0
                     + noise.fbm(xs, zs, 120.0, 2, salt=salt + 3) * 0.6)
            # Hard guarantee, by true distance: nothing of this islet reaches the sampling box edge.
            edge = np.maximum(np.abs(xs - cx), np.abs(zs - cz))
            under = under - smoothstep(edge, reach * 0.6, reach * 0.85) * 300.0
            field = np.where(t < 1.0, land, np.minimum(under, -0.3))
            hs = h[sel]
            h[sel] = np.maximum(hs, field)
            lw = smoothstep(field, 0.0, 1.0) * (t < 1.15)
            land_all[sel] = np.maximum(land_all[sel], lw)
            for name, w in chain["biome"].items():
                v = lw * w
                if name == "forest":
                    v = np.clip(v * (1.0 - clear_w) + noise.fbm(xs, zs, 90.0, 2, salt=salt + 5) * 0.2 * lw * w, 0, 1)
                out[name][sel] = np.maximum(out[name][sel], v)
            out["clearing"][sel] = np.maximum(out["clearing"][sel], clear_w * lw)
    return h, out, land_all


def island_footprint(x, z):
    """True where a new island (with a little margin) lies: excluded from the coastline check."""
    m = np.zeros(np.shape(x), bool)
    for chain in ISLANDS:
        for islet in chain["islets"]:
            m |= _islet_frame(islet, x, z) < 1.6
    return m


def island_clearance(F, log=print):
    """Closest existing coast to each islet's outline (with its coastline wobble margin)."""
    worst = 1e9
    for chain in ISLANDS:
        for k, islet in enumerate(chain["islets"]):
            cx, cz, rx, rz, rot = islet[:5]
            a = np.radians(rot)
            ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)
            u, v = np.cos(ang) * rx * 1.2, np.sin(ang) * rz * 1.2
            px = cx + u * np.cos(a) - v * np.sin(a)
            pz = cz + u * np.sin(a) + v * np.cos(a)
            gap = float(-F.mid("coast_sd", px, pz).max())
            worst = min(worst, gap)
            if gap < 250.0:
                log(f"[Lyris] WARNING island {chain['id']}{k + 1} ({chain['name']}) is only {gap:.0f} m from an existing coast")
        # islets of one chain must not merge
        isl = chain["islets"]
        for i in range(len(isl)):
            for j in range(i + 1, len(isl)):
                d = np.hypot(isl[i][0] - isl[j][0], isl[i][1] - isl[j][1])
                if d < (sum(isl[i][2:4]) + sum(isl[j][2:4])) * 0.5 * 1.1:
                    log(f"[Lyris] WARNING islets {chain['id']}{i + 1} and {chain['id']}{j + 1} may touch ({d:.0f} m apart)")
    log(f"[Lyris] new islands: {sum(len(c['islets']) for c in ISLANDS)} islets in {len(ISLANDS)} chains, "
        f"nearest existing coast {worst:.0f} m away")


def canon_pads(x, z, h):
    """Applies CANON_PADS (heights in m above sea)."""
    for _name, shape, level_y, feather, mode in CANON_PADS:
        kind = shape[0]
        level = np.full(np.shape(x), level_y - 63.0, np.float32)
        if kind == "circle":
            _, cx, cz, r = shape
            d = np.maximum(np.hypot(x - cx, z - cz) - r, 0.0)
        elif kind == "box":
            _, x0, z0, x1, z1 = shape
            d = np.hypot(np.maximum(np.maximum(x0 - x, x - x1), 0.0), np.maximum(np.maximum(z0 - z, z - z1), 0.0))
        elif kind == "line":
            _, x0, z0, x1, z1, width, y_end = shape
            dx, dz = x1 - x0, z1 - z0
            t = np.clip(((x - x0) * dx + (z - z0) * dz) / (dx * dx + dz * dz), 0.0, 1.0)
            d = np.maximum(np.hypot(x - x0 - t * dx, z - z0 - t * dz) - width * 0.5, 0.0)
            level = (lerp(level_y, y_end, t) - 63.0).astype(np.float32)
        else:
            raise ValueError(kind)
        w = 1.0 - smoothstep(d, 0.0, feather)
        if not np.any(w > 0):
            continue
        target = np.maximum(h, level) if mode == "raise" else level
        h = lerp(h, target, w)
    return h


# ----------------------------------------------------------------------------- natural wonders (T49)
#
# Every wonder is described in wonders.json (id, name, MC x/z, kind, params) and designed in
# design/natural_wonders.md. Each kind has one sculpt function below. They run in two passes:
#   "land"  after the mountains, mesas, salt flats and volcanoes, before rivers, lakes and beaches,
#           so rivers still carve their gorges through whatever a wonder raises;
#   "sea"   after the seabed and the island chains, for everything that rises out of the water.
# Every function is a pure function of world position, like the rest of the bake, so tiles join.

WONDERS_PATH = os.path.join(HERE, "wonders.json")
REFERENCE_MAP = os.path.join(HERE, os.pardir, os.pardir, "design", "reference", "lyris_map_wonders.jpg")
# Pixel fit of the reference map's 1000-block grid: px = a + b * X, py = c + d * Z (max error 1 px = 5 m).
REFERENCE_FIT = (2626.43, 0.195146, 2038.37, 0.195357)
PAINT_KEYS = ("w_rock", "w_snow", "w_sand", "w_salt", "w_volcanic", "w_forest", "w_grass", "w_badlands", "no_forest")


def load_wonders(path=WONDERS_PATH):
    with open(path) as f:
        return json.load(f)["wonders"]


WONDERS = load_wonders()


def hash01(a, b, salt=0):
    """Deterministic 0..1 from integer arrays (cell ids)."""
    a = np.asarray(a, np.int64)
    b = np.asarray(b, np.int64)
    h = (a * 73856093) ^ (b * 19349663) ^ np.int64(salt * 83492791 + 12345)
    h = h & 0xFFFFFFFF
    h = h ^ (h >> 13)
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    h = h ^ (h >> 15)
    return (h & 0xFFFFFF).astype(np.float32) / float(0x1000000)


def _uv(x, z, cx, cz, rot_deg):
    """Local frame: u along the rotation direction (degrees from +X toward +Z), v across it."""
    a = np.radians(rot_deg)
    dx, dz = x - cx, z - cz
    return dx * np.cos(a) + dz * np.sin(a), -dx * np.sin(a) + dz * np.cos(a)


def _polyline(x, z, pts):
    """Distance to a polyline, arc length at the nearest point, signed side (+ = left of travel)."""
    pts = np.asarray(pts, np.float64)
    best = np.full(np.shape(x), 1e12)
    s_best = np.zeros(np.shape(x))
    side = np.ones(np.shape(x))
    s0 = 0.0
    for (ax, az), (bx, bz) in zip(pts[:-1], pts[1:]):
        dx, dz = bx - ax, bz - az
        ln2 = dx * dx + dz * dz
        t = np.clip(((x - ax) * dx + (z - az) * dz) / ln2, 0.0, 1.0)
        px, pz = ax + t * dx, az + t * dz
        d = np.hypot(x - px, z - pz)
        closer = d < best
        best = np.where(closer, d, best)
        s_best = np.where(closer, s0 + t * np.sqrt(ln2), s_best)
        cross = dx * (z - az) - dz * (x - ax)
        side = np.where(closer, np.where(cross >= 0, 1.0, -1.0), side)
        s0 += np.sqrt(ln2)
    return best, s_best, side, s0


def _wobble(noise, x, z, cx, cz, scale, amount, salt):
    """Radius multiplier that varies around a centre, so round things never read as circles."""
    ang = np.arctan2(z - cz, x - cx)
    return 1.0 + amount * noise.fbm(np.cos(ang) * scale + cx, np.sin(ang) * scale + cz, scale * 0.55, 3, salt=salt)


def _hex(x, z, size):
    """Pointy-top hex cells: (q, r) ids and 0..1 distance from the cell centre to its edge."""
    q = (np.sqrt(3.0) / 3.0 * x - z / 3.0) / size
    r = (2.0 / 3.0 * z) / size
    cx_, cz_ = q, r
    cy_ = -cx_ - cz_
    rx, rz, ry = np.round(cx_), np.round(cz_), np.round(cy_)
    dx, dz, dy = np.abs(rx - cx_), np.abs(rz - cz_), np.abs(ry - cy_)
    fix_x = (dx > dz) & (dx > dy)
    fix_z = ~fix_x & (dz > dy)
    rx = np.where(fix_x, -rz - ry, rx)
    rz = np.where(fix_z, -rx - ry, rz)
    px = size * np.sqrt(3.0) * (rx + rz / 2.0)
    pz = size * 1.5 * rz
    ox, oz = x - px, z - pz
    n = [(np.cos(np.radians(a)), np.sin(np.radians(a))) for a in (30.0, 90.0, 150.0)]
    d = np.maximum.reduce([np.abs(ox * c + oz * s) for c, s in n]) / (size * np.sqrt(3.0) / 2.0)
    return rx.astype(np.int64), rz.astype(np.int64), d


def _voronoi(x, z, cell, salt):
    """Jittered-grid Voronoi: (cell ids i, j) of the nearest seed and the gap F2 - F1 in metres."""
    gi, gj = np.floor(x / cell).astype(np.int64), np.floor(z / cell).astype(np.int64)
    f1 = np.full(np.shape(x), 1e9)
    f2 = np.full(np.shape(x), 1e9)
    bi, bj = gi.copy(), gj.copy()
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            ci, cj = gi + di, gj + dj
            sx = (ci + 0.1 + 0.8 * hash01(ci, cj, salt)) * cell
            sz = (cj + 0.1 + 0.8 * hash01(ci, cj, salt + 1)) * cell
            d = np.hypot(x - sx, z - sz)
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            f1 = np.where(closer, d, f1)
            bi, bj = np.where(closer, ci, bi), np.where(closer, cj, bj)
    return bi, bj, f2 - f1


def _scatter(rng, cx, cz, radius, count, gap, ok=None, tries=4000):
    """Seeded blue-noise points in a disc (denser toward the middle), optionally filtered by ok(x, z)."""
    pts = []
    for _ in range(tries):
        if len(pts) >= count:
            break
        r = radius * np.sqrt(rng.uniform()) ** 1.15
        a = rng.uniform(0, 2 * np.pi)
        px, pz = cx + r * np.cos(a), cz + r * np.sin(a)
        if any((px - qx) ** 2 + (pz - qz) ** 2 < gap * gap for qx, qz in pts):
            continue
        if ok is not None and not ok(px, pz):
            continue
        pts.append((px, pz))
    return pts


class WonderCtx:
    """What a sculpt function may read and write for one batch of points."""

    def __init__(self, F, noise, x, z, b, sd):
        self.F, self.noise, self.x, self.z, self.b, self.sd = F, noise, x, z, b, sd
        self.paint = {k: np.zeros(np.shape(x), np.float32) for k in PAINT_KEYS}
        self.water = np.full(np.shape(x), -1e4, np.float32)   # wonder lakes and pools (m)
        self.carve = np.zeros(np.shape(x), bool)              # deliberately below sea on old land
        self.newland = np.zeros(np.shape(x), np.float32)      # wonder land rising out of the sea
        self.no_lake = np.zeros(np.shape(x), np.float32)      # atlas lakes switched off under a wonder
        self._rd = self._lsd = None
        self.box = (float(np.min(x)), float(np.max(x)), float(np.min(z)), float(np.max(z)))

    @property
    def rd(self):
        if self._rd is None:
            self._rd = self.F.mid("river_dist", self.x, self.z)
        return self._rd

    @property
    def lsd(self):
        if self._lsd is None:
            self._lsd = self.F.mid("lake_sd", self.x, self.z)
        return self._lsd

    def near(self, cx, cz, reach):
        x0, x1, z0, z1 = self.box
        if cx + reach < x0 or cx - reach > x1 or cz + reach < z0 or cz - reach > z1:
            return None
        sel = (np.abs(self.x - cx) < reach) & (np.abs(self.z - cz) < reach)
        return sel if sel.any() else None

    def put(self, key, sel, w):
        self.paint[key][sel] = np.maximum(self.paint[key][sel], np.clip(w, 0, 1))


_WCACHE = {}


def _cached(key, fn):
    if key not in _WCACHE:
        _WCACHE[key] = fn()
    return _WCACHE[key]


def _ground(F, x, z):
    return float(F.base(np.array([float(x)]), np.array([float(z)]))[0])


def _coast_snap(F, x, z, search=160.0):
    """Nearest coast point (coast_sd = 0) to a seed, and the inland direction there."""
    c = np.arange(-search, search + 1, 4.0)
    zz, xx = np.meshgrid(z + c, x + c, indexing="ij")
    sd = F.mid("coast_sd", xx, zz)
    k = np.argmin(np.abs(sd) + 0.02 * np.hypot(xx - x, zz - z))
    px, pz = float(xx.flat[k]), float(zz.flat[k])
    e = 12.0
    gx = F.mid("coast_sd", np.array([px + e]), np.array([pz]))[0] - F.mid("coast_sd", np.array([px - e]), np.array([pz]))[0]
    gz = F.mid("coast_sd", np.array([px]), np.array([pz + e]))[0] - F.mid("coast_sd", np.array([px]), np.array([pz - e]))[0]
    return px, pz, float(np.degrees(np.arctan2(gz, gx)))


def _pillars(C, sel, h, pillars, style, salt, ground_mode="base"):
    """Raises pillars (x, z, r, height above ground, ground) into h[sel]. Returns the cover weight."""
    xs, zs = C.x[sel], C.z[sel]
    hs = h[sel]
    cover = np.zeros_like(hs)
    top_w = np.zeros_like(hs)
    for k, (px, pz, r, hh, g0) in enumerate(pillars):
        m = (np.abs(xs - px) < r * 2.8) & (np.abs(zs - pz) < r * 2.8)
        if not m.any():
            continue
        xm, zm = xs[m], zs[m]
        wob = _wobble(C.noise, xm, zm, px, pz, max(r * 3.0, 30.0), 0.17, salt + k % 7)
        wob = wob * (1.0 + 0.05 * C.noise.fbm(xm, zm, 9.0, 2, salt=salt + 1))
        t = np.hypot(xm - px, zm - pz) / (r * wob)
        top = g0 + hh
        if style == "needle":
            core = np.clip(1.0 - t, 0.0, 1.0) ** 0.55
            col = g0 + hh * core
            edge = core
        else:  # flat-topped stone-forest pillar with a soft cap for trees
            core = 1.0 - smoothstep(t, 0.84, 1.0)
            ledge = 1.0 - 0.06 * smoothstep(t, 0.55, 0.84)  # a slight shoulder below the rim
            col = (top + 2.2 * np.clip(1.0 - t * t, 0, 1)) * ledge + g0 * (1.0 - ledge)
            edge = core
        sk = (1.0 - smoothstep(t, 1.0, 1.9)) ** 2
        skirt = np.maximum(hs[m], lerp(hs[m], g0 + hh * 0.12, sk))  # scree only lifts, never squares off
        new = np.maximum(np.where(edge > 0.02, lerp(skirt, col, edge), skirt), hs[m])
        hs[m] = new
        cover[m] = np.maximum(cover[m], smoothstep(1.4 - t, 0.0, 0.4))
        top_w[m] = np.maximum(top_w[m], (t < 0.8) * 1.0)
    h[sel] = hs
    return cover, top_w


# -- the sculpt functions: (wonder dict, ctx, stage, h) -> h -----------------------------------

def w_sea_stack(W, C, stage, h):
    if stage != "sea":
        return h
    p, cx, cz = W["params"], W["mc_x"], W["mc_z"]
    sel = C.near(cx, cz, p["shoal_radius"] + 60)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    d = np.hypot(xs - cx, zs - cz)
    shoal = lerp(np.float32(p["shoal_depth"]), hs, smoothstep(d, p["radius"], p["shoal_radius"]))
    hs = np.where(C.sd[sel] < 0, np.maximum(hs, shoal), hs)
    wob = _wobble(C.noise, xs, zs, cx, cz, 120.0, 0.16, 61)
    t = d / (p["radius"] * wob)
    stack = p["height"] * (1.0 - smoothstep(t, 0.86, 1.0)) + 3.0 * np.clip(1 - t * t, 0, 1)
    stack = stack - 1.2 * (np.sin(stack / 7.0 * np.pi) > 0.95)  # faint ledges
    u, v = _uv(xs, zs, cx, cz, p["cleft_rot"])
    cleft = (np.abs(v) < p["cleft_width"] * 0.5 * (1.0 + 0.3 * C.noise.fbm(xs, zs, 20.0, 2, salt=62)))
    stack = np.where(cleft & (t < 1.05), -3.0, stack)
    hs = np.where(t < 1.0, np.maximum(hs, stack), hs)
    h[sel] = hs
    land = (t < 1.0) & (stack > 0)
    C.newland[sel] = np.maximum(C.newland[sel], land)
    C.put("w_snow", sel, (t < 0.75) * land * 0.9)
    C.put("w_rock", sel, land * 1.0)
    return h


def w_ice_cliffs(W, C, stage, h):
    p, cx, cz = W["params"], W["mc_x"], W["mc_z"]
    R = p["radius"]
    sel = C.near(cx, cz, R + 80)
    if sel is None:
        return h
    xs, zs, hs, sds = C.x[sel], C.z[sel], h[sel], C.sd[sel]
    d = np.hypot(xs - cx, zs - cz)
    fall = 1.0 - smoothstep(d, R * 0.55, R)
    if stage == "land":
        top = p["cliff_top"] * (0.85 + 0.3 * C.noise.fbm(xs, zs, 220.0, 3, salt=71))
        cliff = top * smoothstep(sds, 0.0, 6.0) + C.noise.ridged(xs, zs, 60.0, 3, salt=72) * 6.0
        w = fall * (1.0 - smoothstep(sds, p["band"], p["band"] + 160.0)) * (sds > 0)
        hs = np.maximum(hs, lerp(hs, cliff, w))
        # Ice spikes on the clifftop.
        F = C.F
        spikes = _cached(("rime_spikes", W["id"]), lambda: [
            (x, z, r, hh, _ground(F, x, z) + 0.0) for (x, z), r, hh in zip(
                _scatter(np.random.default_rng(SEED + 73), cx, cz, R * 0.75, p["spikes"], 40.0,
                         ok=lambda x, z: 25.0 < float(F.mid("coast_sd", np.array([x]), np.array([z]))[0]) < 140.0),
                np.random.default_rng(SEED + 74).uniform(5.0, 10.0, 64), np.random.default_rng(SEED + 75).uniform(10.0, 24.0, 64))])
        spikes = [(x, z, r, hh, p["cliff_top"] * 0.9) for x, z, r, hh, _g in spikes]
        h[sel] = hs
        _pillars(C, sel, h, spikes, "needle", 76)
        hs = h[sel]
        # Clefts: narrow cave mouths cut into the cliff face, down to the sea.
        clefts = _cached(("rime_clefts", W["id"]), lambda: [(*_coast_snap(C.F, c[0], c[1]), c[2], c[3]) for c in p["clefts"]])
        cut = np.zeros_like(hs, dtype=bool)
        for (mx, mz, inland, width, length) in clefts:
            u, v = _uv(xs, zs, mx, mz, inland)
            taper = 1.0 - 0.55 * np.clip(u / length, 0, 1)
            inside = (u > -30.0) & (u < length) & (np.abs(v) < width * 0.5 * taper * (1.0 + 0.25 * C.noise.fbm(xs, zs, 12.0, 2, salt=77)))
            hs = np.where(inside, np.minimum(hs, -3.5 + np.clip(u, 0, None) * 0.02), hs)
            cut |= inside & (sds > 0)
        h[sel] = hs
        C.carve[sel] |= cut
        C.put("w_snow", sel, w * (sds > 8) * 0.95)
        return h
    # sea: the cliffs plunge into deep water, with ice-capped stacks and an arch's two feet off the tip
    deep = lerp(np.float32(p["plunge"]), hs, smoothstep(-sds, 40.0, 170.0))
    hs = np.where(sds < 0, lerp(hs, np.minimum(hs, deep), fall), hs)
    h[sel] = hs
    stacks = [(x, z, r, hh, float(p["plunge"])) for x, z, r, hh in p.get("stacks", [])]
    cover, top_w = _pillars(C, sel, h, stacks, "pillar", 78)
    C.newland[sel] = np.maximum(C.newland[sel], cover)
    C.put("w_snow", sel, top_w * 1.0)
    C.put("w_rock", sel, cover * 0.6)
    return h


def w_fjord(W, C, stage, h):
    p = W["params"]
    cx, cz = p["centre"]
    R = p["radius"]
    sel = C.near(cx, cz, R + 60)
    if sel is None:
        return h
    xs, zs, hs, sds = C.x[sel], C.z[sel], h[sel], C.sd[sel]
    d = np.hypot(xs - cx, zs - cz)
    fall = (1.0 - smoothstep(d, R * 0.65, R)) * smoothstep(zs, p["north_limit"] - 40.0, p["north_limit"] + 120.0)
    if stage == "land":
        top = p["wall_top"] * (0.78 + 0.4 * C.noise.fbm(xs, zs, 350.0, 3, salt=81))
        wall = top * smoothstep(sds, 0.0, 8.0) + C.noise.ridged(xs, zs, 90.0, 3, salt=82) * 10.0
        w = fall * (1.0 - smoothstep(sds, p["wall_band"], p["wall_band"] * 2.6)) * (sds > 0)
        hs = np.maximum(hs, lerp(hs, wall, w))
        h[sel] = hs
        C.put("w_snow", sel, w * smoothstep(hs, 25.0, 50.0))
        return h
    deep = np.maximum(np.float32(p["depth"]), -6.0 + sds * 1.1)  # sd < 0 at sea
    hs = np.where(sds < 0, lerp(hs, np.minimum(hs, deep), fall), hs)
    h[sel] = hs
    sisters = [(x, z, r, hh, -8.0) for x, z, r, hh in p["sisters"]]
    cover, top_w = _pillars(C, sel, h, sisters, "pillar", 83)
    C.newland[sel] = np.maximum(C.newland[sel], cover)
    C.put("w_snow", sel, top_w * 0.9)
    return h


def w_icefall(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    (tx, tz), (fx, fz) = p["top"], p["foot"]
    L = float(np.hypot(fx - tx, fz - tz))
    rot = float(np.degrees(np.arctan2(fz - tz, fx - tx)))
    reach = L + p["width"] + 120
    sel = C.near((tx + fx) / 2, (tz + fz) / 2, reach)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    wx, wz = C.noise.warp(xs, zs, 160.0, 26.0, salt=90)
    u, v = _uv(wx, wz, tx, tz, rot)
    top_h = _cached(("icefall_top", W["id"]), lambda: _ground(C.F, tx, tz)) - 10.0
    n = p["tiers"]
    # Uneven treads and ragged lips: each fall breaks at a slightly different place across the ice.
    q = np.clip(u / L + 0.07 * C.noise.fbm(v * 2.0, u * 0.3, 45.0, 3, salt=92), 0.0, 1.0) * n
    k = np.floor(np.minimum(q, n - 1e-3))
    frac = q - k
    drop = (top_h - 2.0) / n
    tier = top_h - (k + smoothstep(frac, 0.8, 0.96)) * drop - 2.0 * np.sin(np.pi * np.clip(frac / 0.8, 0, 1))
    half = p["width"] * 0.5 * (1.25 - 0.55 * np.clip(u / L, 0, 1)) * (1.0 + 0.25 * C.noise.fbm(xs, zs, 70.0, 2, salt=91))
    along = smoothstep(u, -40.0, 10.0) * (1.0 - smoothstep(u, L, L + 30.0))
    w_in = (1.0 - smoothstep(np.abs(v), half, half + 18.0)) * along
    walls = (smoothstep(np.abs(v), half, half + 10.0) * (1.0 - smoothstep(np.abs(v), half + 20.0, half + 90.0))) * along
    seracs = 8.0 * C.noise.ridged(xs, zs, 24.0, 3, salt=94) * C.noise.fbm(xs, zs, 90.0, 2, salt=96).clip(0, 1)
    hs = np.maximum(hs, lerp(hs, tier + 4.0 + seracs, walls * 0.6))
    tier = tier + 1.4 * C.noise.ridged(xs, zs, 14.0, 2, salt=95)
    hs = lerp(hs, tier, w_in)
    # A cirque at the head, where the ice gathers before the first fall.
    dc = np.hypot(xs - tx, zs - tz) / _wobble(C.noise, xs, zs, tx, tz, 150.0, 0.18, 93)
    bowl = top_h + 2.0 - 16.0 * np.clip(1.0 - (dc / p["cirque_radius"]) ** 2, 0, 1)
    hs = np.where(dc < p["cirque_radius"], np.minimum(hs, lerp(hs, bowl, 1.0 - smoothstep(dc, p["cirque_radius"] * 0.6, p["cirque_radius"]))), hs)
    h[sel] = hs
    C.put("w_snow", sel, np.maximum(w_in, walls) * 1.0 + (dc < p["cirque_radius"]))
    return h


def _stone_forest_pillars(W, C):
    p = W["params"]
    F = C.F
    cx, cz = p["centre"]

    def ok(x, z):
        X, Z = np.array([x]), np.array([z])
        return (F.base(X, Z)[0] > 4.0 and F.mid("coast_sd", X, Z)[0] > 45.0
                and F.mid("river_dist", X, Z)[0] > 140.0 and F.mid("lake_sd", X, Z)[0] < -45.0)

    rng = np.random.default_rng(SEED + p["salt"])
    pts = _scatter(rng, cx, cz, p["radius"], p["count"], p["min_gap"] + p["r_max"], ok=ok)
    out = []
    for k, (x, z) in enumerate(pts):
        centre_bias = 1.0 - 0.45 * np.hypot(x - cx, z - cz) / p["radius"]
        r = rng.uniform(p["r_min"], p["r_max"])
        hh = p["h_min"] + (p["h_max"] - p["h_min"]) * np.clip(rng.uniform(0.15, 1.0) * centre_bias + 0.1, 0, 1)
        out.append((x, z, r, hh, _ground(F, x, z) - 2.0))
    return out


def w_stone_forest(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    cx, cz = p["centre"]
    sel = C.near(cx, cz, p["radius"] + p["r_max"] * 2 + 10)
    if sel is None:
        return h
    pillars = _cached(("pillars", W["id"]), lambda: _stone_forest_pillars(W, C))
    cover, top_w = _pillars(C, sel, h, pillars, p["style"], p["salt"])
    C.put("w_rock", sel, cover * (0.9 if p["style"] == "needle" else 0.6))
    if p["style"] == "pillar":
        C.put("w_forest", sel, top_w * 0.9)
    else:
        C.put("w_salt", sel, cover * 0.35)  # pale starglass
        C.put("no_forest", sel, cover)
    return h


def _ladder_lakes(W):
    p = W["params"]
    out = []
    for i, (x, z, rx, rz, rot) in enumerate(p["lakes"]):
        out.append((x, z, rx, rz, rot, p["top_level"] - i * p["step"]))
    return out


def w_lake_ladder(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    lakes = _ladder_lakes(W)
    xs_c = [l[0] for l in lakes]
    zs_c = [l[1] for l in lakes]
    reach = p["band"] + p["blend"] + 200
    sel = C.near(float(np.mean(xs_c)), float(np.mean(zs_c)), reach + 450)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    dch, _s, _side, _L = _polyline(xs, zs, list(zip(xs_c, zs_c)))
    # Each point takes the level of the lake it is "in front of" (nearest in ellipse terms).
    best_t = np.full(xs.shape, 1e9, np.float32)
    level = np.zeros_like(hs)
    ts = []
    for (x, z, rx, rz, rot, lv) in lakes:
        u, v = _uv(xs, zs, x, z, rot)
        wob = _wobble(C.noise, xs, zs, x, z, 80.0, 0.12, 101)
        t = np.hypot(u / rx, v / rz) / wob
        ts.append((t, lv))
        closer = t < best_t
        best_t = np.where(closer, t, best_t)
        level = np.where(closer, lv, level)
    # Along the chain: the lake levels as steps (a dam halfway between lakes) and as a smooth slope.
    _d, s_ax, _sd2, _L2 = _polyline(xs, zs, list(zip(xs_c, zs_c)))
    cum = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xs_c), np.diff(zs_c)))])
    lv = np.array([l[5] for l in lakes])
    smooth_lv = np.interp(s_ax, cum, lv)
    mids = (cum[:-1] + cum[1:]) / 2.0
    step_lv = lv[np.searchsorted(mids, s_ax)]
    near_axis = 1.0 - smoothstep(dch, 70.0, p["band"])
    level = np.where(best_t < 1.25, level, lerp(smooth_lv, step_lv, near_axis))
    tread = level + 1.3 + C.noise.fbm(xs, zs, 50.0, 2, salt=102) * 0.5
    w = 1.0 - smoothstep(dch, p["band"], p["band"] + p["blend"])
    hs = lerp(hs, tread, w)
    water = np.full(xs.shape, -1e4, np.float32)
    rim = np.zeros_like(hs)
    for t, lv in ts:
        floor = lv - 0.4 - p["depth"] * np.sqrt(np.clip(1.0 - t * t, 0, 1))
        hs = np.where(t < 1.0, np.minimum(hs, floor), hs)
        water = np.where(t < 1.0, np.maximum(water, lv), water)
        rim = np.maximum(rim, (t >= 1.0) * (1.0 - smoothstep(t, 1.0, 1.2)))
    h[sel] = hs
    C.water[sel] = np.maximum(C.water[sel], water)
    C.no_lake[sel] = np.maximum(C.no_lake[sel], 1.0 - smoothstep(dch, p["band"] * 0.8, p["band"] + 60.0))
    C.put("w_salt", sel, rim * 0.8)          # pale travertine dams between the steps
    C.put("w_forest", sel, w * (rim < 0.1) * (best_t > 1.35) * 0.8)
    return h


def w_knoll(W, C, stage, h):
    if stage != "land":
        return h
    p, cx, cz = W["params"], W["mc_x"], W["mc_z"]
    R = p["radius"]
    sel = C.near(cx, cz, R + 20)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    d = np.hypot(xs - cx, zs - cz) / _wobble(C.noise, xs, zs, cx, cz, 500.0, 0.1, 111)
    dome = p["rise"] * np.clip(1.0 - (d / R) ** 2, 0, 1) ** 1.6
    crown = p["rise"] * np.clip(1.0 - (p["crown_radius"] / R) ** 2, 0, 1) ** 1.6
    dome = np.where(d < p["crown_radius"], crown + 0.6 * (1.0 - d / p["crown_radius"]), dome)
    ang = np.arctan2(zs - cz, xs - cx)
    roots = np.zeros_like(hs)
    for k in range(p["roots"]):
        a = 2 * np.pi * k / p["roots"] + 0.35 * np.sin(k * 2.3)
        bend = 0.25 * C.noise.fbm(d * 0.5 + k * 400.0, k * 77.0, 160.0, 2, salt=112)  # roots wander
        da = np.angle(np.exp(1j * (ang - a - bend)))
        perp = np.abs(da) * d
        ridge = p["root_height"] * np.exp(-(perp / (16.0 + 0.04 * d)) ** 2) * (0.7 + 0.5 * hash01(k, 1, 113))
        ridge *= smoothstep(d, p["crown_radius"] * 0.7, p["crown_radius"] * 1.2) * (1.0 - smoothstep(d, R * 0.25, R * (0.45 + 0.2 * hash01(k, 2, 114))))
        roots = np.maximum(roots, ridge)
    land = smoothstep(C.sd[sel], 5.0, 60.0)
    hs = hs + (dome + roots) * land
    cw = 0.85 * (1.0 - smoothstep(d, p["crown_radius"] * 0.6, p["crown_radius"] * 1.4))
    hs = lerp(hs, np.float32(_cached(("knoll_g", W["id"]), lambda: _ground(C.F, cx, cz))) + crown, cw)
    h[sel] = hs
    C.put("no_forest", sel, 1.0 - smoothstep(d, p["crown_radius"], p["crown_radius"] + 40))
    C.put("w_grass", sel, 1.0 - smoothstep(d, p["crown_radius"], p["crown_radius"] + 30))
    C.put("w_forest", sel, smoothstep(d, R * 0.35, R * 0.5) * (1.0 - smoothstep(d, R * 0.85, R)) * 0.7)
    return h


def w_sea_cliffs(W, C, stage, h):
    p = W["params"]
    a, b = p["from"], p["to"]
    cx, cz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    L = float(np.hypot(b[0] - a[0], b[1] - a[1]))
    sel = C.near(cx, cz, L / 2 + p["reach"] + 100)
    if sel is None:
        return h
    xs, zs, hs, sds = C.x[sel], C.z[sel], h[sel], C.sd[sel]
    d, s, _side, _ = _polyline(xs, zs, [a, b])
    fall = (1.0 - smoothstep(d, p["reach"] * 0.6, p["reach"])) * smoothstep(s, 0.0, 180.0) * (1.0 - smoothstep(s, L - 180.0, L))
    if stage == "land":
        top = p["top"] * (0.86 + 0.26 * C.noise.fbm(xs, zs, 260.0, 3, salt=121))
        wall = top * smoothstep(sds, 0.0, 7.0) + C.noise.ridged(xs, zs, 70.0, 3, salt=122) * 5.0
        # Gullies notch the top edge every so often, so the wall reads as rock, not a dam.
        gully = np.exp(-(((s + 37.0 * C.noise.fbm(xs, zs, 200.0, 2, salt=123)) % 170.0 - 85.0) / 9.0) ** 2)
        wall = wall - gully * 14.0 * (1.0 - smoothstep(sds, 0.0, 90.0))
        w = fall * (1.0 - smoothstep(sds, p["band"], p["band"] + 230.0)) * (sds > 0)
        hs = np.maximum(hs, lerp(hs, wall, w))
        h[sel] = hs
        C.put("w_rock", sel, w * (1.0 - smoothstep(sds, 0.0, 40.0)) * 0.8)
        return h
    deep = lerp(np.float32(p["plunge"]), hs, smoothstep(-sds, 50.0, 220.0))
    hs = np.where(sds < 0, lerp(hs, np.minimum(hs, deep), fall), hs)
    h[sel] = hs
    rng = np.random.default_rng(SEED + 124)
    hmin, hmax = p["stack_h"]
    stacks = _cached(("stacks", W["id"]), lambda: [
        (x, z, r * p["stack_scale"], hmin + (hmax - hmin) * np.clip((r - 10) / 25.0, 0, 1) * rng.uniform(0.75, 1.1), -14.0)
        for x, z, r in p["stacks"]])
    cover, top_w = _pillars(C, sel, h, stacks, "pillar", 125)
    C.newland[sel] = np.maximum(C.newland[sel], cover)
    C.put("w_rock", sel, cover * 0.9)
    C.put("w_grass", sel, top_w * 0.8)
    return h


def w_sinkhole(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    cx, cz = p["centre"]
    R = p["radius"]
    sel = C.near(cx, cz, R + 60)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    g0 = _cached(("sink_g", W["id"]), lambda: _ground(C.F, cx, cz))
    wob = _wobble(C.noise, xs, zs, cx, cz, 110.0, 0.2, 131)
    d = np.hypot(xs - cx, zs - cz) / wob
    ang = (np.degrees(np.arctan2(zs - cz, xs - cx)) + 360.0) % 360.0
    # A cenote: the pool is groundwater at sea level, so the pit may go below the sea (carved).
    pool_lv = 0.6
    floor_lv = pool_lv - 2.5
    p = dict(p, depth=g0 - floor_lv)
    pool = np.where(d < p["pool_radius"], pool_lv - 0.4 - 3.0 * np.clip(1 - (d / p["pool_radius"]) ** 2, 0, 1), pool_lv + 0.8)
    # The ledge path spirals down the south-east wall: from the rim at 20 deg to the pool at 230 deg.
    led = np.clip((ang - 20.0) / 210.0, 0, 1)
    ledge_h = g0 - 4.0 - led * (p["depth"] - 6.0)
    on_ledge = (d > R - 13.0) & (d < R) & (ang > 20.0) & (ang < 230.0)
    inside = np.where(on_ledge, ledge_h, pool)
    lip = g0 + p["lip"] * np.clip(1.0 - (d - R) / 28.0, 0, 1) ** 1.5 * (1.0 + 0.3 * C.noise.fbm(xs, zs, 15.0, 2, salt=132))
    pool = np.where(d < p["pool_radius"], pool_lv - 0.4 - 7.0 * np.clip(1 - (d / p["pool_radius"]) ** 2, 0, 1), pool_lv + 0.8)
    inside = np.where(on_ledge, ledge_h, pool)
    hs = np.where(d < R, inside, np.maximum(hs, lerp(hs, lip, 1.0 - smoothstep(d, R, R + 40.0))))
    h[sel] = hs
    C.carve[sel] |= d < R
    C.water[sel] = np.maximum(C.water[sel], np.where(d < p["pool_radius"], pool_lv, -1e4))
    C.put("w_forest", sel, on_ledge * 0.9 + (d > R) * (1.0 - smoothstep(d, R, R + 25)) * 0.8)  # moss
    C.put("w_rock", sel, (d < R) * (~on_ledge) * 0.7)
    return h


def w_falls_lip(W, C, stage, h):
    p = W["params"]
    lx, lz = p["lip"]
    sel = C.near(lx, lz, p["amphi_radius"] * 2.5 + p["channel_len"])
    if sel is None:
        return h
    xs, zs, hs, sds = C.x[sel], C.z[sel], h[sel], C.sd[sel]
    u, v = _uv(xs, zs, lx, lz, p["facing"])  # u > 0 toward the sea
    d = np.hypot(xs - lx, zs - lz)
    if stage == "land":
        fall = 1.0 - smoothstep(d, p["amphi_radius"] * 1.5, p["amphi_radius"] * 2.5)
        top = p["lip_top"] + 3.0 * C.noise.fbm(xs, zs, 120.0, 2, salt=141)
        cliff = top * smoothstep(sds, 0.0, 6.0)
        w = fall * (1.0 - smoothstep(sds, 220.0, 380.0)) * (sds > 0)
        hs = np.maximum(hs, lerp(hs, cliff, w))
        # Amphitheatre: a half bowl bitten out of the cliff below the lip, open to the sea.
        ar = p["amphi_radius"] * 0.55
        fx, fz = lx + np.cos(np.radians(p["facing"])) * ar, lz + np.sin(np.radians(p["facing"])) * ar
        da = np.hypot(xs - fx, zs - fz) / _wobble(C.noise, xs, zs, fx, fz, 80.0, 0.12, 142)
        cove = da < ar
        hs = np.where(cove, np.minimum(hs, -6.0 - 8.0 * np.clip(1 - da / ar, 0, 1)), hs)
        C.carve[sel] |= cove & (sds > 0)
        # The stream channel that feeds the veil: wide and shallow at the lip, narrowing inland.
        lipd = np.clip((-u - ar * 0.9) / 60.0, 0, 1)  # 0 at the lip, 1 from 60 m inland
        half = lerp(p["lip_width"] * 0.5, 9.0, smoothstep(lipd, 0.0, 1.0))
        vm = v - 30.0 * C.noise.fbm(u * 1.0, 11.0, 170.0, 2, salt=143) * lipd
        chan = (u < -ar * 0.9 + 4.0) & (u > -p["channel_len"]) & (np.abs(vm) < half)
        v = vm
        dip = p["channel_depth"] * np.clip(1.0 - (v / np.maximum(half, 1.0)) ** 2, 0, 1) * lerp(0.5, 1.0, lipd)
        hs = np.where(chan, np.minimum(hs, top - dip + np.clip(-u, 0, None) * 0.015), hs)
        h[sel] = hs
        C.water[sel] = np.maximum(C.water[sel], np.where(chan & (dip > 0.6), top - 0.6 + np.clip(-u, 0, None) * 0.015, -1e4))
        C.put("w_rock", sel, w * (1.0 - smoothstep(sds, 0.0, 30.0)))
        C.put("w_forest", sel, chan * 0.0 + (np.abs(v) < half + 25) * (u < -ar) * (u > -p["channel_len"]) * 0.6)
        return h
    px, pz, pr, pf = p["pool"]
    dp = np.hypot(xs - px, zs - pz)
    hs = np.where(sds < 30, np.minimum(hs, lerp(np.float32(pf), hs, smoothstep(dp, pr * 0.6, pr * 1.6))), hs)
    h[sel] = hs
    return h


def w_mesa(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    cx, cz = p["centre"]
    rx, rz, rot = p["rx"], p["rz"], p["rot"]
    reach = max(rx, rz) + p["forest_ring"] + 120
    sel = C.near(cx, cz, reach)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    u, v = _uv(xs, zs, cx, cz, rot)
    wob = _wobble(C.noise, xs, zs, cx, cz, 600.0, 0.1, 151) * (1.0 + 0.045 * C.noise.fbm(xs, zs, 70.0, 3, salt=152))
    wob = wob * (1.0 + 0.03 * C.noise.ridged(xs, zs, 30.0, 2, salt=156))
    t = np.hypot(u / rx, v / rz) / wob
    top = p["top"] + 2.0 * C.noise.fbm(xs, zs, 260.0, 3, salt=153) - 7.0 * (u / rx)  # tilts to the east end
    core = 1.0 - smoothstep(t, 0.975, 1.0)
    rmean = (rx + rz) * 0.5
    tt = (t - 1.0) * rmean
    talus = hs + (top - hs) * 0.32 * (1.0 - smoothstep(tt, 0.0, p["talus"])) ** 2
    mesa = np.where(t < 1.0, lerp(talus, top, core), np.maximum(hs, talus))
    # The stream across the top, falling off the east end into the pool.
    mx, mz = C.noise.warp(xs, zs, 160.0, 30.0, salt=157)
    ds, _s, _side, _ = _polyline(mx, mz, p["stream"])
    chan = (ds < 9.0) & (t < 1.0)
    mesa = np.where(chan, mesa - 2.6 * np.clip(1.0 - (ds / 9.0) ** 2, 0, 1), mesa)
    hs = np.where(t < 1.0, mesa, np.maximum(hs, mesa))
    px, pz, pr, plv = p["pool"]
    if plv is None:
        plv = _cached(("mesa_pool", W["id"]), lambda: _ground(C.F, px, pz) - 2.5)
    dp = np.hypot(xs - px, zs - pz) / _wobble(C.noise, xs, zs, px, pz, 60.0, 0.12, 154)
    basin = plv - 0.4 - 5.0 * np.clip(1 - (dp / pr) ** 2, 0, 1)
    hs = np.where(dp < pr, np.minimum(hs, basin), np.where(dp < pr * 1.35, np.maximum(np.minimum(hs, plv + 2.0 + (dp - pr)), plv + 0.6), hs))
    h[sel] = hs
    C.water[sel] = np.maximum(C.water[sel], np.where(dp < pr, plv, np.where(chan, mesa - 0.5, -1e4)))
    C.no_lake[sel] = np.maximum(C.no_lake[sel], 1.0 - smoothstep(t, 1.0, 1.25))
    C.put("w_grass", sel, (t < 0.97) * 0.8)
    C.put("w_rock", sel, (t < 1.0) * (0.35 + 0.35 * (C.noise.fbm(xs, zs, 80.0, 2, salt=155) > 0.1)))
    ring = (t > 1.0) * (1.0 - smoothstep(tt, p["forest_ring"] * 0.6, p["forest_ring"]))
    C.put("w_forest", sel, ring * 1.0)
    C.put("no_forest", sel, (t < 1.0) * 0.6)
    return h


def w_travertine(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    cx, cz = p["centre"]
    R = p["radius"]
    sel = C.near(cx, cz, R + 120)
    if sel is None:
        return h
    xs, zs, hs, sds = C.x[sel], C.z[sel], h[sel], C.sd[sel]
    g0 = _cached(("trav_g", W["id"]), lambda: _ground(C.F, cx, cz))
    ang = np.arctan2(zs - cz, xs - cx)
    d = np.hypot(xs - cx, zs - cz) / _wobble(C.noise, xs, zs, cx, cz, 300.0, 0.1, 161)
    n = p["terraces"]
    # Scalloped rims: each terrace edge bulges into lobes, like the rim pools of Pamukkale.
    # Terraces are contours of a lumpy mound, so their rims wander and pinch like real travertine.
    wx, wz = C.noise.warp(xs, zs, 110.0, 34.0, salt=162)
    lump = 0.16 * C.noise.fbm(wx, wz, 130.0, 3, salt=164) + 0.05 * C.noise.ridged(wx, wz, 35.0, 2, salt=165)
    q = np.clip(1.0 - d / R + lump * smoothstep(d, R * 0.2, R * 0.5), 0.0, 1.0) * n
    k = np.floor(np.minimum(q, n - 1e-3))
    frac = q - k
    step = p["rise"] / n
    tread = g0 + (k + smoothstep(frac, 0.0, 0.06)) * step - 0.35 * np.sin(np.pi * np.clip(frac, 0, 1)) ** 0.5
    rim = 0.55 * np.exp(-((frac - 0.06) / 0.04) ** 2)
    mound = tread + rim
    w = (1.0 - smoothstep(d, R, R + 90.0)) * smoothstep(sds, 2.0, 12.0)
    hs = lerp(hs, np.maximum(mound, g0 - 1.0 + 0.0 * hs), w)
    top_lv = g0 + p["rise"]
    dc = d
    hs = np.where(dc < p["pool_radius"], top_lv - 0.3 - 3.0 * np.clip(1 - (dc / p["pool_radius"]) ** 2, 0, 1), hs)
    water = np.where(dc < p["pool_radius"], top_lv - 0.1, -1e4)
    for k2, (px, pz, pr) in enumerate(p["pools"]):
        dp = np.hypot(xs - px, zs - pz) / _wobble(C.noise, xs, zs, px, pz, 40.0, 0.15, 163 + k2)
        lv = _cached(("trav_pool", W["id"], k2), lambda px=px, pz=pz: float(
            g0 + np.floor(np.clip(1.0 - np.hypot(px - cx, pz - cz) / R, 0, 1) * n) * step - 0.1))
        hs = np.where(dp < pr, np.minimum(hs, lv - 0.3 - 2.0 * np.clip(1 - (dp / pr) ** 2, 0, 1)), hs)
        hs = np.where((dp >= pr) & (dp < pr * 1.3), np.maximum(hs, lv + 0.5), hs)
        water = np.where(dp < pr, np.maximum(water, lv), water)
    h[sel] = hs
    C.water[sel] = np.maximum(C.water[sel], water)
    C.no_lake[sel] = np.maximum(C.no_lake[sel], 1.0 - smoothstep(d, R, R + 60.0))
    C.put("w_salt", sel, w * 1.0)
    C.put("w_badlands", sel, w * (np.clip(rim / 0.55, 0, 1) * 0.55 + (1.0 - smoothstep(np.abs(d - R * 0.95), 0, 40)) * 0.6))
    C.put("no_forest", sel, w)
    return h


def w_sea_arch(W, C, stage, h):
    if stage != "sea":
        return h
    p = W["params"]
    a, b = p["from"], p["to"]
    L = float(np.hypot(b[0] - a[0], b[1] - a[1]))
    sel = C.near((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, L / 2 + 120)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    d, s, _side, _ = _polyline(xs, zs, [a, b])
    f = np.clip(s / L, 0, 1)
    half = p["width"] * 0.5 * (1.0 - 0.3 * f) * (1.0 + 0.15 * C.noise.fbm(xs, zs, 25.0, 2, salt=171))
    H = lerp(np.float32(p["height"]), np.float32(p["end_height"]), f) + 3.0 * C.noise.ridged(xs, zs, 30.0, 2, salt=172)
    fin = H * (1.0 - smoothstep(d / half, 0.7, 1.0)) + (1.0 - smoothstep(d, half, half + 35.0)) * -1.0 * 0.0
    end_round = 1.0 - smoothstep(s, L - 25.0, L + 5.0)
    fin = fin * np.maximum(end_round, 0.0)
    plinth = lerp(np.float32(-2.0), hs, smoothstep(d, half, half + 60.0))
    hs = np.where(C.sd[sel] < 0, np.maximum(hs, plinth), hs)
    hs = np.maximum(hs, np.where(d < half, fin, -1e4))
    d0, d1 = p["door"]
    door = (f > d0) & (f < d1) & (d < half * 1.6)
    hs = np.where(door, np.minimum(hs, p["door_floor"]), hs)
    h[sel] = hs
    land = (d < half) & ~door & (fin > 0)
    C.newland[sel] = np.maximum(C.newland[sel], land)
    C.put("w_rock", sel, land * 1.0)
    C.put("w_grass", sel, land * (fin > H * 0.9) * 0.5)
    return h


def w_islet_field(W, C, stage, h):
    if stage != "sea":
        return h
    p = W["params"]
    isl = p["islets"]
    xs_all = [i[0] for i in isl]
    zs_all = [i[1] for i in isl]
    cx, cz = (min(xs_all) + max(xs_all)) / 2, (min(zs_all) + max(zs_all)) / 2
    reach = max(max(xs_all) - min(xs_all), max(zs_all) - min(zs_all)) / 2 + 200
    sel = C.near(cx, cz, reach)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    sea = C.sd[sel] < 0
    cover = np.zeros_like(hs)
    lx, lz, lr = p["lagoon"]
    for k, (ix, iz, r) in enumerate(isl):
        r = r * p["scale"]
        lagoon = np.hypot(ix - lx, iz - lz) < 10
        if lagoon:
            r = lr
        m = (np.abs(xs - ix) < r * 2.6 + 30) & (np.abs(zs - iz) < r * 2.6 + 30)
        if not m.any():
            continue
        xm, zm = xs[m], zs[m]
        H = p["h_min"] + (p["h_max"] - p["h_min"]) * np.clip((r - 8.0) / 32.0, 0, 1) * (0.7 + 0.5 * hash01(k, 7, 181))
        if r > p["tall_over"]:
            H += 8.0
        wob = _wobble(C.noise, xm, zm, ix, iz, max(r * 2.5, 25.0), 0.22, 182 + k % 5)
        t = np.hypot(xm - ix, zm - iz) / (r * wob)
        rough = C.noise.ridged(xm, zm, max(r * 0.8, 10.0), 3, salt=183)
        prof = np.clip(1.0 - t ** 2, 0, 1) ** 0.6 * (0.7 + 0.45 * rough)
        if lagoon:  # a ring of rock round a sheltered pool, open to the sea on the south side
            ang = np.degrees(np.arctan2(zm - iz, xm - ix))
            ring = smoothstep(t, 0.45, 0.6) * np.clip(1.0 - t ** 2, 0, 1) ** 0.6 * 1.6
            gap = np.abs(((ang - 95.0) + 180) % 360 - 180) < 12.0
            prof = np.where(gap, -1.0, ring * (0.75 + 0.35 * rough))
            prof = np.where(t < 0.45, -0.3, prof)
        top = H * prof
        shelf = -0.6 - np.maximum(t - 1.0, 0) * r * 0.35
        isle = np.where(t < 1.0, np.where(prof > 0, np.maximum(top, 0.4), top), shelf)
        hs[m] = np.where(sea[m], np.maximum(hs[m], isle), hs[m])
        if lagoon:
            hs[m] = np.where(sea[m] & (t < 0.45), np.minimum(hs[m], -2.5), hs[m])
        cover[m] = np.maximum(cover[m], (t < 1.0) * (isle > 0))
    h[sel] = hs
    C.newland[sel] = np.maximum(C.newland[sel], cover)
    C.put("w_rock", sel, cover * 0.85)
    C.put("w_volcanic", sel, cover * 0.4)
    C.put("no_forest", sel, cover)
    return h


def w_dune_field(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    cx, cz = p["centre"]
    sel = C.near(cx, cz, max(p["rx"], p["rz"]) + 60)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    u, v = _uv(xs, zs, cx, cz, p["rot"])
    t = np.hypot(u / p["rx"], v / p["rz"]) / _wobble(C.noise, xs, zs, cx, cz, 700.0, 0.14, 191)
    w = (1.0 - smoothstep(t, 0.72, 1.0)) * smoothstep(C.sd[sel], 10.0, 60.0)
    b = np.radians(p["crest_bearing"])  # crests run this many degrees east of north
    across = xs * np.cos(b) + zs * np.sin(b)
    along = -xs * np.sin(b) + zs * np.cos(b)
    across = across + 55.0 * C.noise.fbm(along * 0.6, across * 0.1, 380.0, 3, salt=192) \
        + 18.0 * C.noise.fbm(along, across, 120.0, 2, salt=195) + 60.0 * C.noise.fbm(xs, zs, 900.0, 2, salt=196)
    ph = across / p["wavelength"]
    # Crescents: each crest bows downwind between horns.
    ph = ph + 0.18 * np.sin(along / 210.0 + np.floor(ph) * 1.7) ** 2
    frac = ph - np.floor(ph)
    # Stoss slope up from the west, steep slip face down to the east, a flat glassy pan between.
    rise = np.where(frac < 0.62, smoothstep(frac, 0.18, 0.62) ** 1.25, 1.0 - smoothstep(frac, 0.62, 0.76))
    amp = np.clip(0.35 + 0.9 * (C.noise.fbm(along, np.floor(ph) * 37.0, 230.0, 2, salt=193) * 0.5 + 0.5), 0.2, 1.2)
    dune = p["height"] * rise * amp
    target = p["pan_level"] + dune + 0.15 * C.noise.fbm(xs, zs, 30.0, 2, salt=194)
    hs = lerp(hs, target, w)
    h[sel] = hs
    C.put("w_salt", sel, w * 1.0)
    C.put("w_sand", sel, w * smoothstep(rise, 0.55, 0.9) * 0.45)
    C.put("no_forest", sel, w)
    return h


def w_hex_causeway(W, C, stage, h):
    if stage != "sea":
        return h
    p = W["params"]
    allp = [pt for path in p["paths"] for pt in path]
    xs_c, zs_c = [q[0] for q in allp], [q[1] for q in allp]
    cx, cz = (min(xs_c) + max(xs_c)) / 2, (min(zs_c) + max(zs_c)) / 2
    reach = max(max(xs_c) - min(xs_c), max(zs_c) - min(zs_c)) / 2 + p["shallows"] + 60
    sel = C.near(cx, cz, reach)
    if sel is None:
        return h
    xs, zs, hs, sds = C.x[sel], C.z[sel], h[sel], C.sd[sel]
    dmin = np.full(xs.shape, 1e9)
    for path in p["paths"]:
        d, _s, _side, _ = _polyline(xs, zs, path)
        dmin = np.minimum(dmin, d)
    shallow = lerp(np.float32(-1.6), hs, smoothstep(dmin, p["width"] * 0.5, p["shallows"]))
    hs = np.where(sds < 0, np.maximum(hs, shallow), hs)
    q, r, he = _hex(xs, zs, p["cell"])
    lo, hi = p["top"]
    near_land = 1.0 - smoothstep(np.abs(sds), 0.0, 120.0)
    col = lo + (hi - lo) * (0.35 * hash01(q, r, 201) + 0.65 * near_land * hash01(q, r, 202) ** 0.7)
    col = np.round(col / 0.6) * 0.6 - 0.35 * smoothstep(he, 0.86, 1.0)  # cracks between columns
    ragged = p["width"] * 0.5 * (1.0 + 0.35 * C.noise.fbm(xs, zs, 40.0, 2, salt=203))
    groups = C.noise.fbm(xs, zs, 70.0, 2, salt=205) + 0.55 * (1.0 - smoothstep(np.abs(sds), 0.0, 90.0))
    keep = (dmin < ragged) & (hash01(q, r, 204) > 0.06) & (groups > -0.12)
    onshore = keep & (sds > 0) & (sds < 70)
    hs = np.where(keep & (sds <= 0), np.maximum(hs, col), hs)
    hs = np.where(onshore, np.maximum(hs, hs + col * 0.5), hs)
    h[sel] = hs
    C.newland[sel] = np.maximum(C.newland[sel], keep & (sds <= 0))
    C.put("w_volcanic", sel, keep * 1.0)
    C.put("no_forest", sel, keep * 1.0)
    return h


def w_crater_chain(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    pits = p["pits"]
    out = h
    for k, (px, pz, hl, hw, rot, depth) in enumerate(pits):
        sel = C.near(px, pz, hl * 1.5 + 40)
        if sel is None:
            continue
        xs, zs, hs = C.x[sel], C.z[sel], out[sel]
        u, v = _uv(xs, zs, px, pz, rot)
        wob = 1.0 + 0.08 * C.noise.fbm(xs, zs, 90.0, 3, salt=211 + k)
        t = (np.abs(u / hl) ** 2.4 + np.abs(v / hw) ** 2.0) ** (1.0 / 2.2) / wob
        g = _cached(("pit_g", W["id"], k), lambda px=px, pz=pz: _ground(C.F, px, pz))
        # Deeper toward the south-east end: the fragment was still ploughing when it hit.
        floor = g - depth - 0.15 * depth * np.clip(u / hl, -1, 1) + 1.2 * C.noise.fbm(xs, zs, 40.0, 2, salt=212)
        wall = floor + (hs - floor) * np.clip(t, 0, 1) ** 5
        rim = p["rim"] * (1.0 + 0.25 * k / len(pits)) * np.clip(1.0 - (t - 1.0) / 0.45, 0, 1) ** 2 * (t >= 0.97)
        hs = np.where(t < 1.0, np.minimum(hs, wall), hs + rim)
        # Starglass crystals: small knots of rock on the floor (the crystals themselves are props).
        n = p["crystals"] if k == len(pits) - 1 else p["crystals"] // 6
        cr = _cached(("pit_cr", W["id"], k), lambda px=px, pz=pz, hl=hl, hw=hw, rot=rot, n=n: [
            (px + a * np.cos(np.radians(rot)) - b_ * np.sin(np.radians(rot)), pz + a * np.sin(np.radians(rot)) + b_ * np.cos(np.radians(rot)),
             rr, hh) for a, b_, rr, hh in zip(np.random.default_rng(SEED + 213 + k).uniform(-hl * 0.75, hl * 0.75, n),
                                              np.random.default_rng(SEED + 223 + k).uniform(-hw * 0.6, hw * 0.6, n),
                                              np.random.default_rng(SEED + 233 + k).uniform(3.0, 8.0, n),
                                              np.random.default_rng(SEED + 243 + k).uniform(2.0, 7.0, n))])
        for cx_, cz_, rr, hh in cr:
            dd = np.hypot(xs - cx_, zs - cz_)
            hs = np.where((dd < rr) & (t < 0.9), hs + hh * np.clip(1 - dd / rr, 0, 1) ** 0.7, hs)
        out[sel] = hs
        C.put("w_volcanic", sel, (1.0 - smoothstep(t, 1.0, 1.6)) * 1.0)
        C.put("no_forest", sel, 1.0 - smoothstep(t, 1.0, 1.8))
    return out


def w_karst_plateau(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    F = C.F
    if getattr(F, "ref_masks", None) is None:
        return h
    x0, x1, z0, z1 = C.box
    if x1 < -600 or x0 > 2900 or z1 < 2500 or z0 > 5400:
        return h
    sel = (C.x > -600) & (C.x < 2900) & (C.z > 2500) & (C.z < 5400)
    if not sel.any():
        return h
    xs, zs, hs, sds = C.x[sel], C.z[sel], h[sel], C.sd[sel]
    g = F.ref("grey", xs, zs)
    wp = smoothstep(g, 0.35, 0.65) * smoothstep(sds, 6.0, 30.0)
    rd = C.rd[sel]
    wp = wp * smoothstep(rd, 25.0, 110.0) * smoothstep(-C.lsd[sel], 15.0, 80.0)
    # Leviathan's Rest lies in a hollow of the plateau.
    for L in WONDERS:
        if L["kind"] == "spine_ridge":
            dsp, *_ = _polyline(xs, zs, L["params"]["path"])
            wp = wp * smoothstep(dsp, 140.0, 380.0)
    wx, wz = C.noise.warp(xs, zs, 140.0, 22.0, salt=251)
    ci, cj, gap = _voronoi(wx, wz, p["cell"], 252)
    clint = 3.0 * hash01(ci, cj, 253) * smoothstep(wp, 0.4, 0.9)
    grike = 3.5 * (1.0 - smoothstep(gap, 0.8, 2.6)) * smoothstep(wp, 0.5, 0.95)
    plateau = hs + (p["rise"] + clint - grike) * wp
    # The Curtain: a sheer escarpment along the west bank of the lake outlet.
    ds, s, side, L = _polyline(xs, zs, p["scarp"])
    west = side  # the path runs north to south, so points west of it are on its left (+1)
    along = smoothstep(s, 0.0, 60.0) * (1.0 - smoothstep(s, L - 60.0, L))
    sc = (west > 0) * (1.0 - smoothstep(ds, 140.0, 320.0)) * along * smoothstep(rd, 14.0, 26.0) * smoothstep(sds, 2.0, 8.0)
    plateau = np.maximum(plateau, lerp(plateau, p["scarp_top"] + clint - grike * 0.5, sc))
    hs = plateau
    h[sel] = hs
    pale = np.maximum(wp, sc)
    C.put("w_rock", sel, pale * 0.85)
    C.put("w_salt", sel, pale * 0.45)
    C.put("no_forest", sel, pale * 0.55)
    return h


def _spine_parts(W):
    p = W["params"]
    path = np.array(p["path"], float)
    seg = np.hypot(*np.diff(path, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    L = cum[-1]
    n = p["vertebrae"]
    out_v, out_r = [], []
    for k in range(n):
        s = L * (k + 0.5) / n
        i = min(np.searchsorted(cum, s) - 1, len(seg) - 1)
        f = (s - cum[i]) / seg[i]
        pt = path[i] + (path[i + 1] - path[i]) * f
        tang = (path[i + 1] - path[i]) / seg[i]
        nrm = np.array([-tang[1], tang[0]])
        a = k / (n - 1)
        H = lerp(p["height"][0], p["height"][1], a) * (0.85 + 0.3 * hash01(k, 3, 261))
        rad = lerp(17.0, 8.0, a)
        out_v.append((pt[0], pt[1], rad, H))
        if k % 2 == 0 and a < 0.85:
            rl = lerp(p["rib_len"][0], p["rib_len"][1], a)
            for sgn in (-1, 1):
                pts = [pt + nrm * sgn * rl * c + tang * (-0.3 * rl * c * c) for c in np.linspace(0.15, 1.0, 9)]
                out_r.append((np.array(pts), H * 0.42))
    return out_v, out_r


def w_spine_ridge(W, C, stage, h):
    if stage != "sea":
        return h
    p = W["params"]
    path = p["path"]
    cx, cz = float(np.mean([q[0] for q in path])), float(np.mean([q[1] for q in path]))
    sel = C.near(cx, cz, 900)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    verts, ribs = _cached(("spine", W["id"]), lambda: _spine_parts(W))
    bump = np.zeros_like(hs)
    for vx, vz, rad, H in verts:
        d = np.hypot(xs - vx, zs - vz) / (1.0 + 0.1 * C.noise.fbm(xs, zs, 12.0, 2, salt=262))
        bump = np.maximum(bump, H * np.clip(1.0 - (d / rad) ** 2, 0, 1) ** 0.75)
    for pts, H in ribs:
        d, s, _side, L = _polyline(xs, zs, pts)
        f = np.clip(s / L, 0, 1)
        width = lerp(5.5, 2.5, f)
        hh = H * (1.0 - f) ** 0.6 + 1.5
        bump = np.maximum(bump, hh * np.clip(1.0 - (d / width) ** 2, 0, 1) ** 0.6)
    kx, kz, kr, kh = p["skull"]
    path0 = np.array(path[0], float)
    head_dir = np.degrees(np.arctan2(kz - path0[1], kx - path0[0]))
    u, v = _uv(xs, zs, kx, kz, head_dir)
    ts = np.hypot(u / kr, v / (kr * 0.62))
    skull = kh * np.clip(1.0 - ts ** 2, 0, 1) ** 0.55
    for side in (-1, 1):  # eye hollows
        de = np.hypot(u + kr * 0.15, v - side * kr * 0.3)
        skull = skull - 7.0 * np.clip(1.0 - (de / 11.0) ** 2, 0, 1)
    jaw = (u > kr * 0.35) & (np.abs(v) < kr * 0.12)
    skull = np.where(jaw, skull * 0.45, skull)
    bump = np.maximum(bump, skull)
    hs = hs + bump
    h[sel] = hs
    bone = smoothstep(bump, 0.8, 3.0)
    C.newland[sel] = np.maximum(C.newland[sel], bone * (C.sd[sel] < 0))
    C.put("w_salt", sel, bone * 0.9)
    C.put("w_rock", sel, bone * 0.45)
    C.put("no_forest", sel, bone)
    return h


def w_terraces(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    cx, cz = p["centre"]
    sel = C.near(cx, cz, max(p["rx"], p["rz"]) + 40)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    u, v = _uv(xs, zs, cx, cz, p["rot"])
    t = np.hypot(u / p["rx"], v / p["rz"]) / _wobble(C.noise, xs, zs, cx, cz, 500.0, 0.12, 271)
    w = (1.0 - smoothstep(t, 0.72, 1.0)) * smoothstep(hs, p["min_h"], p["min_h"] + 6.0) * (1.0 - smoothstep(hs, p["max_h"] - 10.0, p["max_h"]))
    w = w * smoothstep(C.sd[sel], 20.0, 60.0)
    st = p["step"]
    hsm = hs - 0.0
    qv = hsm / st
    k = np.floor(qv)
    frac = qv - k
    terr = (k + smoothstep(frac, 0.84, 0.97)) * st - 0.25 * (frac < 0.84)  # flat paddy, short steep riser
    ds, _s, _side, _ = _polyline(xs, zs, p["stair"])
    stair = ds < 4.0
    terr = np.where(stair, np.round(hsm / 0.6) * 0.6, terr)
    hs = lerp(hs, terr, w)
    h[sel] = hs
    C.put("w_grass", sel, w * (frac < 0.84) * 0.9)
    C.put("no_forest", sel, w * 0.85)
    C.put("w_rock", sel, w * stair * 0.9)
    return h


def w_sea_hole(W, C, stage, h):
    if stage != "sea":
        return h
    p, cx, cz = W["params"], W["mc_x"], W["mc_z"]
    R = p["ring_outer"]
    sel = C.near(cx, cz, R + 240)
    if sel is None:
        return h
    xs, zs, hs = C.x[sel], C.z[sel], h[sel]
    d = np.hypot(xs - cx, zs - cz) / _wobble(C.noise, xs, zs, cx, cz, 400.0, 0.05, 281)
    lag = lerp(np.float32(p["lagoon_floor"]), np.float32(p["lagoon_floor"] + 4.0), smoothstep(d, p["hole_radius"], p["lagoon_radius"]))
    ring_mid = (p["lagoon_radius"] + R) * 0.5
    ring = p["ring_level"] + 0.9 * (1.0 - smoothstep(np.abs(d - ring_mid), 0.0, (R - p["lagoon_radius"]) * 0.5)) \
        + 0.3 * C.noise.fbm(xs, zs, 40.0, 2, salt=282)
    prof = np.where(d < p["lagoon_radius"], lag, np.where(d < R, lerp(lag * 0 + p["lagoon_floor"] + 4.0, ring,
                                                                       smoothstep(d, p["lagoon_radius"], p["lagoon_radius"] + 40.0)), ring))
    hole = p["hole_floor"] + 3.0 * np.clip(d / p["hole_radius"], 0, 1) ** 4
    prof = np.where(d < p["hole_radius"], hole, prof)
    prof = lerp(prof, hs, smoothstep(d, R, R + 220.0))
    prof = np.minimum(prof, -0.4)
    hs = np.where(C.sd[sel] < 0, prof, hs)
    # Reef rocks just breaking the surface on the ring.
    rocks = [(cx + ring_mid * np.cos(a), cz + ring_mid * np.sin(a), 6.0 + 8.0 * hash01(k, 1, 283), 1.0 + 2.5 * hash01(k, 2, 284))
             for k, a in enumerate(np.linspace(0, 2 * np.pi, p["reef_rocks"], endpoint=False) + 0.4)]
    cover = np.zeros_like(hs)
    for rx_, rz_, rr, hh in rocks:
        dd = np.hypot(xs - rx_, zs - rz_)
        bump = hh * np.clip(1 - (dd / rr) ** 2, 0, 1) ** 0.6
        hs = np.where(dd < rr, np.maximum(hs, bump), hs)
        cover = np.maximum(cover, (dd < rr) * (bump > 0))
    h[sel] = hs
    C.newland[sel] = np.maximum(C.newland[sel], cover)
    C.put("w_rock", sel, cover)
    C.put("w_sand", sel, (d > p["lagoon_radius"]) * (d < R) * 1.0)
    return h


def w_bowl_island(W, C, stage, h):
    if stage != "land":
        return h
    p = W["params"]
    cx, cz = p["centre"]
    sel = C.near(cx, cz, p["radius"] + 80)
    if sel is None:
        return h
    xs, zs, hs, sds = C.x[sel], C.z[sel], h[sel], C.sd[sel]
    ang = np.arctan2(zs - cz, xs - cx)
    passes = 1.0 - 0.75 * np.exp(-((np.angle(np.exp(1j * (ang - 2.4)))) / 0.12) ** 2)  # one low pass to the west cove
    rim_h = p["rim"] * (0.85 + 0.3 * C.noise.fbm(xs, zs, 120.0, 2, salt=291)) * passes
    band = p["band"]
    prof = lerp(np.float32(p["floor"]), rim_h, 1.0 - smoothstep(sds, band * 0.7, band * 2.0)) * smoothstep(sds, 0.0, 22.0)
    prof = prof + 1.2 * C.noise.fbm(xs, zs, 45.0, 3, salt=292)
    w = (sds > 0) * (1.0 - smoothstep(np.hypot(xs - cx, zs - cz), p["radius"] * 0.9, p["radius"] + 60))
    hs = lerp(hs, prof, w)
    h[sel] = hs
    C.put("w_salt", sel, w * 0.35)
    C.put("w_forest", sel, w * smoothstep(sds, band * 0.8, band * 1.8) * 0.9)
    return h


WONDER_KINDS = {
    "sea_stack": w_sea_stack, "ice_cliffs": w_ice_cliffs, "fjord": w_fjord, "icefall": w_icefall,
    "stone_forest": w_stone_forest, "lake_ladder": w_lake_ladder, "knoll": w_knoll, "sea_cliffs": w_sea_cliffs,
    "sinkhole": w_sinkhole, "falls_lip": w_falls_lip, "mesa": w_mesa, "travertine": w_travertine,
    "sea_arch": w_sea_arch, "islet_field": w_islet_field, "dune_field": w_dune_field, "hex_causeway": w_hex_causeway,
    "crater_chain": w_crater_chain, "karst_plateau": w_karst_plateau, "spine_ridge": w_spine_ridge,
    "terraces": w_terraces, "sea_hole": w_sea_hole, "bowl_island": w_bowl_island,
}


def wonders_pass(C, stage, h):
    for W in WONDERS:
        h = WONDER_KINDS[W["kind"]](W, C, stage, h)
    return h


def wonder_footprint(x, z):
    """Where wonders put land in the sea or the sea into land on purpose (excluded from the coast check)."""
    m = np.zeros(np.shape(x), bool)
    for W in WONDERS:
        p = W["params"]
        k = W["kind"]
        if k == "islet_field":
            for ix, iz, r in p["islets"]:
                m |= np.hypot(x - ix, z - iz) < r * 2.0 + 30
        elif k == "sea_cliffs":
            for ix, iz, r in p["stacks"]:
                m |= np.hypot(x - ix, z - iz) < r * 2.0 + 30
        elif k in ("sea_stack", "sea_hole", "spine_ridge"):
            m |= np.hypot(x - W["mc_x"], z - W["mc_z"]) < {"sea_stack": 80, "sea_hole": 600, "spine_ridge": 650}[k]
        elif k == "sea_arch":
            d, *_ = _polyline(x, z, [p["from"], p["to"]])
            m |= d < 80
        elif k == "hex_causeway":
            for path in p["paths"]:
                d, *_ = _polyline(x, z, path)
                m |= d < 80
        elif k in ("ice_cliffs", "falls_lip"):
            m |= np.hypot(x - W["mc_x"], z - W["mc_z"]) < 260
            for sx, sz, r, _hh in p.get("stacks", []):
                m |= np.hypot(x - sx, z - sz) < r * 2 + 40
        elif k == "fjord":
            for sx, sz, r, _hh in p["sisters"]:
                m |= np.hypot(x - sx, z - sz) < r * 2 + 40
    return m


def wonder_manifest(F):
    """Wonder lakes and pools (added to the manifest's lakes) and one record per wonder."""
    lakes, records = [], []

    def ellipse_lake(wid, x, z, rx, rz, rot, level, n=28):
        a = np.radians(rot)
        out = []
        for t in np.linspace(0, 2 * np.pi, n, endpoint=False):
            u, v = np.cos(t) * rx * 0.98, np.sin(t) * rz * 0.98
            out.append(mc_to_ue(x + u * np.cos(a) - v * np.sin(a), z + u * np.sin(a) + v * np.cos(a))[:2])
        lakes.append({"level_m": round(float(level), 2), "area_m2": round(float(np.pi * rx * rz)),
                      "centre_mc": [round(x, 1), round(z, 1)], "outline_ue": out, "wonder": wid})

    for W in WONDERS:
        p, k = W["params"], W["kind"]
        rec = {"id": W["id"], "name": W["name"], "kind": k, "region": W["region"], "canon": W["canon"],
               "mc": [W["mc_x"], W["mc_z"]], "ue": mc_to_ue(W["mc_x"], W["mc_z"])[:2]}
        if k == "lake_ladder":
            for (x, z, rx, rz, rot, lv) in _ladder_lakes(W):
                ellipse_lake(W["id"], x, z, rx, rz, rot, lv)
            rec["waterfalls"] = "small cascades over each travertine dam, top lake to bottom lake"
        elif k == "sinkhole":
            cx, cz = p["centre"]
            g0 = _ground(F, cx, cz)
            ellipse_lake(W["id"], cx, cz, p["pool_radius"], p["pool_radius"], 0, g0 - p["depth"] + 2.5, 20)
            rec["needs"] = "overhang lip and cave mouth meshes, glowing moss and the Glowmere light"
        elif k == "travertine":
            cx, cz = p["centre"]
            g0 = _ground(F, cx, cz)
            ellipse_lake(W["id"], cx, cz, p["pool_radius"], p["pool_radius"], 0, g0 + p["rise"] - 0.1, 20)
            n, step, R = p["terraces"], p["rise"] / p["terraces"], p["radius"]
            for px, pz, pr in p["pools"]:
                lv = g0 + np.floor(np.clip(1.0 - np.hypot(px - cx, pz - cz) / R, 0, 1) * n) * step - 0.1
                ellipse_lake(W["id"], px, pz, pr, pr, 0, lv, 16)
            rec["needs"] = "steam and hot-spring water material (warm, milky blue)"
        elif k == "mesa":
            px, pz, pr, plv = p["pool"]
            plv = _ground(F, px, pz) - 2.5 if plv is None else plv
            ellipse_lake(W["id"], px, pz, pr, pr, 0, plv, 20)
            rec["waterfalls"] = [{"lip_mc": p["stream"][-1], "pool_mc": [px, pz], "note": "the stream off the Table's east end"}]
        elif k == "falls_lip":
            rec["waterfalls"] = [{"lip_mc": p["lip"], "width_m": p["lip_width"], "top_m": p["lip_top"],
                                  "facing_deg": p["facing"], "note": "wide curtain fall into the sea cove"}]
        elif k == "sea_arch":
            a, b = np.array(p["from"]), np.array(p["to"])
            d0, d1 = p["door"]
            rec["needs"] = {"arch_lintel": {"from_mc": list(map(float, a + (b - a) * d0)), "to_mc": list(map(float, a + (b - a) * d1)),
                                            "underside_m": 22.0, "note": "a heightmap cannot overhang: the span is a rock mesh"}}
        elif k == "ice_cliffs":
            rec["needs"] = "ice cave meshes in each cleft, ice material on the cliff faces"
        elif k == "icefall":
            rec["needs"] = "frozen waterfall meshes on each riser"
        elif k == "karst_plateau":
            rec["waterfalls"] = [{"line_mc": p["scarp"], "top_m": p["scarp_top"], "note": "the Thunder Curtain: water over the escarpment"}]
        records.append(rec)
    return lakes, records


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

    # Natural wonders, land pass (T49): before rivers and lakes, so rivers still carve through them.
    C = WonderCtx(F, noise, x, z, b, sd)
    h = wonders_pass(C, "land", h)

    # Rivers: carve a channel under the river surface, softly banked.
    rd = C.rd
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
    lsd = C.lsd
    near_lake = lsd > -60.0
    lake_shore = np.zeros_like(h)
    lake_on = 1.0 - C.no_lake  # wonders that replace the ground (the High Table) switch atlas lakes off
    if near_lake.any():
        lv = F.mid("lake_level", x, z, order=0)
        floor = lv - 0.5 - 6.0 * smoothstep(lsd, 0.0, 90.0)
        h = np.where(lsd > 0, np.minimum(h, lerp(h, floor, smoothstep(lsd, -2.0, 12.0) * lake_on)), h)
        lip = lv + 0.25 + np.maximum(-lsd - 8.0, 0.0) * 0.05
        lip_w = smoothstep(lsd, -40.0, -20.0) * (lsd <= 0) * lake_on
        h = lerp(h, np.maximum(h, np.minimum(lip, h + 1.5)), lip_w)
        lake_shore = (1.0 - smoothstep(lsd, -10.0, -3.0)) * (lsd > -10.0) * (lsd < 6.0) * lake_on
        water = np.where((lsd > 0) & (lake_on > 0.5), np.maximum(water, lv), water)

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
    # New island chains A to H rise out of that seabed (only where the sea is; never on old land).
    h_sea = h
    h, isl, isl_land = islands(x, z, h.copy(), noise)
    h = np.where(sd < 0, h, h_sea)
    isl_land = isl_land * (sd < 0)
    # Natural wonders, sea pass: islets, stacks, the causeway, the Blue Eye, deep fjords.
    h = wonders_pass(C, "sea", h)
    h = canon_pads(x, z, h)
    # Keep every coastline where the map has it: land stays above the sea unless a lake or a
    # sea-level river was carved there on purpose.
    carved = (river_bed > 0.3) | (lake_shore > 0.3) | ((lsd > 0) & (lake_on > 0.5)) | C.carve
    h = np.where((sd > 0) & ~carved, np.maximum(h, 0.1), h)
    h = np.clip(h, H_MIN + 1.0, H_MIN + H_SPAN - 1.0)

    on_isl = isl_land > 0.01
    isl_beach = isl["sand"] + (h < 2.0) * isl_land * (1.0 - isl["snow"]) * (1.0 - isl["clearing"])
    # Biomes repainted to match the user's map (T49): its white north, its dark Sunreach forests.
    ref_snow, ref_forest = F.ref("snow", x, z), F.ref("forest", x, z)
    south = smoothstep(z, 900.0, 1600.0)
    table = (1.0 - smoothstep(np.hypot((x - 6434.0) / 1.6, z + 1333.0), 500.0, 800.0))
    src_forest = np.maximum(F.src_mask("forest", x, z), ref_forest * np.maximum(south, table))
    # The map is white north of about the Delvers' Gate (Z -3950) west of the Skyshoals taiga, and on
    # the mountain spine from the Frozen Cascade down past the Observatory.
    north_white = smoothstep(-z, 3750.0, 4250.0) * (1.0 - smoothstep(x, 2600.0, 3300.0)) * (x > -4000.0)
    spine_white = smoothstep(h, 110.0, 150.0) * smoothstep(-z, 2500.0, 2800.0) * (x > -600.0) * (x < 3200.0)
    src_snow = np.maximum.reduce([F.src_mask("snow", x, z), ref_snow, north_white, spine_white])
    masks = {
        "forest": np.where(on_isl, isl["forest"], src_forest),
        "snow": np.where(on_isl, isl["snow"], src_snow),
        "rock": np.where(on_isl, isl["rock"], F.src_mask("rock", x, z)), "badlands": bad,
        "salt": np.maximum(salt, isl["pale"]), "volcanic": volc,
        "beach": np.maximum.reduce([beach_w, (sd < 25.0) * (h < 2.5) * (1.0 - mtn),
                                    np.clip(isl_beach, 0, 1)]),
        "river": river_bed, "lake_shore": lake_shore, "sea": (h < -0.4).astype(np.float32),
        "desert": F.src_mask("desert", x, z),
        "water": np.maximum(np.maximum(water, C.water), 0.0) * (np.maximum(water, C.water) > h),
        "newland": C.newland,
    }
    masks.update(C.paint)
    return h.astype(np.float32), masks


def weights(h, masks, noise, x, z, metres_per_px):
    """Paint layer weights (0..1, summing to 1) from height, slope and the biome masks."""
    gy, gx = np.gradient(h, metres_per_px)
    slope = np.hypot(gx, gy)  # rise over run
    steep = smoothstep(slope, 0.55, 0.95)  # ~29 to ~44 degrees
    jitter = noise.fbm(x, z, 120.0, 2, salt=20) * 0.25

    w = {name: np.zeros_like(h) for name in LAYERS}
    w["Grass"] += 0.35
    w["Forest"] += np.clip(masks["forest"] * 1.3 + jitter, 0, 1) * (1.0 - masks["no_forest"])
    w["Forest"] += masks["w_forest"] * 1.4
    w["Grass"] += masks["w_grass"] * 1.2
    w["Sand"] += np.clip(np.maximum.reduce([masks["beach"], masks["desert"], masks["river"], masks["lake_shore"],
                                            masks["sea"]]) * 1.5, 0, 1.5)
    w["Badlands"] += np.clip(masks["badlands"] * 1.6, 0, 1.6)
    w["Salt"] += np.clip(masks["salt"] * 1.8 - steep, 0, 1.8)
    w["Volcanic"] += np.clip(masks["volcanic"] * 1.8, 0, 1.8)
    # Snowline: 165 m in the south, falling to 45 m on the far north coast (the map's white north).
    line = 165.0 - 120.0 * smoothstep(-z, 3600.0, 5600.0)
    snowline = smoothstep(h, line + jitter * 60.0, line + 35.0)
    w["Snow"] += np.clip(np.maximum(masks["snow"], snowline) * 1.4 * (1.0 - steep * 0.75), 0, 1.4)
    w["Snow"] += masks["w_snow"] * 2.0 * (1.0 - steep * 0.6)
    w["Salt"] += masks["w_salt"] * 2.2 * (1.0 - steep * 0.5)
    w["Volcanic"] += masks["w_volcanic"] * 2.6
    w["Badlands"] += masks["w_badlands"] * 2.0
    w["Sand"] += masks["w_sand"] * 1.8
    rock = np.maximum(masks["rock"] * 0.9, steep) * (1.0 - masks["badlands"]) * (1.0 - masks["volcanic"] * 0.8)
    w["Rock"] += np.clip(rock * 2.2, 0, 2.2) * (1.0 - masks["sea"])
    w["Rock"] += masks["w_rock"] * 2.2
    # Where the map is white, snow wins: snowy forest keeps some Forest (for the trees), grass goes.
    snowy = np.clip(np.maximum(masks["snow"], masks["w_snow"]), 0, 1) * (1.0 - steep * 0.5)
    w["Snow"] += snowy * 1.2
    w["Grass"] *= 1.0 - 0.9 * snowy
    w["Forest"] *= 1.0 - 0.6 * snowy
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
    """Bakes one tile in bands of rows, so a tile needs a fraction of the memory. Every value is a pure
    function of position and the bands overlap by the one row the slope needs, so the result is the
    same as baking the tile in one go."""
    tx, ty, tile_px, total_px, out_dir, preview_px = args[:6]
    band = args[6] if len(args) > 6 else 256
    step = WORLD_SIZE / (total_px - 1)
    gx = np.arange(tx * tile_px - 1, (tx + 1) * tile_px + 1, dtype=np.float64)
    gy = np.arange(ty * tile_px - 1, (ty + 1) * tile_px + 1, dtype=np.float64)
    xs_world = WORLD_MIN + gx * step
    h_all = np.zeros((tile_px, tile_px), np.float32)
    water_all = np.zeros((tile_px, tile_px), np.float32)
    w_u8 = {n: np.zeros((tile_px, tile_px), np.uint8) for n in LAYERS}
    k = tile_px // preview_px
    slopes = []
    for r0 in range(0, tile_px, band):
        r1 = min(r0 + band, tile_px)
        zz, xx = np.meshgrid(WORLD_MIN + gy[r0:r1 + 2] * step, xs_world, indexing="ij")
        h, masks = terrain(_F, _NOISE, xx, zz)
        wts, slope = weights(h, masks, _NOISE, xx, zz, step)
        c = (slice(1, -1), slice(1, -1))
        h_all[r0:r1] = h[c]
        wl = np.where(masks["water"][c] > 0, masks["water"][c], np.where(h[c] < 0, 0.0, -1e4))
        water_all[r0:r1] = wl
        for name, arr in to_u8_weights({n: v[c] for n, v in wts.items()}).items():
            w_u8[name][r0:r1] = arr
        slopes.append(slope[c][::4, ::4].ravel())
        del h, masks, wts, slope, zz, xx
    enc = np.clip(np.round((h_all - H_MIN) / H_SPAN * 65535.0), 0, 65535).astype(np.uint16)
    Image.fromarray(enc).save(os.path.join(out_dir, f"World_Height_x{tx}_y{ty}.png"))
    for name, arr in w_u8.items():
        Image.fromarray(arr).save(os.path.join(out_dir, f"World_{name}_x{tx}_y{ty}.png"))
    # small copies for the preview
    small_h = h_all[k // 2::k, k // 2::k][:preview_px, :preview_px]
    small_water = water_all[k // 2::k, k // 2::k][:preview_px, :preview_px]
    small_w = np.stack([w_u8[n][k // 2::k, k // 2::k][:preview_px, :preview_px].astype(np.float32) / 255.0 for n in LAYERS])
    stats = (float(h_all.min()), float(h_all.max()), float((h_all > 0).mean()), float(np.percentile(np.concatenate(slopes), 99)))
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


def render_closeup(F, noise, cx, cz, half, n=360, light_az=315.0):
    """Shaded, painted close-up of the baked terrain around one spot (for the wonders sheet)."""
    c = np.linspace(-half, half, n)
    zz, xx = np.meshgrid(cz + c, cx + c, indexing="ij")
    h, masks = terrain(F, noise, xx, zz)
    step = 2.0 * half / (n - 1)
    wts, _slope = weights(h, masks, noise, xx, zz, step)
    w = np.stack([wts[k] for k in LAYERS])
    gy, gx = np.gradient(h, step)
    a = np.radians(light_az)
    lx, lz, ly = np.cos(a) * 0.62, np.sin(a) * 0.62, 0.48
    nrm = np.sqrt(gx * gx + gy * gy + 1.0)
    shade = np.clip((-gx * lx - gy * lz + ly) / nrm / 0.78, 0, 1.25)
    colour = sum(w[k][..., None] * hex_rgb(PREVIEW_COLOURS[name]) for k, name in enumerate(LAYERS))
    colour = colour * (0.3 + 0.8 * shade[..., None])
    water_lv = np.where(masks["water"] > 0, masks["water"], np.where(h < 0, 0.0, -1e4))
    deep, shallow = hex_rgb("2E8A9C"), hex_rgb("7FD0D6")
    t = np.clip(0.2 + (water_lv - h) / 30.0, 0, 1)[..., None]
    water = (shallow * (1 - t) + deep * t) * (0.88 + 0.12 * np.clip(shade, 0, 1)[..., None])
    rgb = np.where((water_lv > h)[..., None], water, colour)
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)), h


def wonder_views():
    """(id, name, centre x, centre z, half size m) for each close-up on the sheet."""
    views = []
    for W in WONDERS:
        p = W["params"]
        cx, cz = W["mc_x"], W["mc_z"]
        half = {"sea_stack": 160, "ice_cliffs": 520, "fjord": 900, "icefall": 420, "stone_forest": 520,
                "lake_ladder": 620, "knoll": 700, "sea_cliffs": 820, "sinkhole": 160, "falls_lip": 330,
                "mesa": 820, "travertine": 380, "sea_arch": 300, "islet_field": 1150, "dune_field": 820,
                "hex_causeway": 520, "crater_chain": 1650, "karst_plateau": 1300, "spine_ridge": 600,
                "terraces": 700, "sea_hole": 680, "bowl_island": 650}[W["kind"]]
        if "centre" in p:
            cx, cz = p["centre"]
        if W["kind"] == "stone_forest" and p["style"] == "needle":
            half = 380
        if W["kind"] == "crater_chain":
            cx, cz = -6050.0, 3420.0
        if W["kind"] == "karst_plateau":
            cx, cz = 1200.0, 4050.0
        if W["kind"] == "spine_ridge":
            cx, cz = 1000.0, 4680.0
        if W["kind"] == "icefall":
            cx, cz = 2120.0, -5470.0
        if W["kind"] == "islet_field":
            cx, cz = 5550.0, 1250.0
        if W["kind"] == "hex_causeway":
            cx, cz = -8600.0, 2120.0
        views.append((W["id"], W["name"], float(cx), float(cz), float(half)))
    return views


def make_sheet(fields, seed, path, tile=380, cols=5, max_bytes=2_000_000, only=None):
    from PIL import ImageDraw
    noise = Noise(seed)
    views = [v for v in wonder_views() if only is None or v[0] in only]
    rows = (len(views) + cols - 1) // cols
    label_h = 22
    sheet = Image.new("RGB", (cols * tile, rows * (tile + label_h)), (244, 236, 220))
    d = ImageDraw.Draw(sheet)
    for k, (wid, name, cx, cz, half) in enumerate(views):
        t0 = time.time()
        img, h = render_closeup(fields, noise, cx, cz, half, n=tile)
        r, c = divmod(k, cols)
        sheet.paste(img, (c * tile, r * (tile + label_h) + label_h))
        d.text((c * tile + 6, r * (tile + label_h) + 5), f"{name}  ({cx:.0f}, {cz:.0f})  {2 * half / 1000:.1f} km  "
               f"{h.min():.0f}..{h.max():.0f} m", fill=(60, 40, 30))
        print(f"[Lyris] sheet {wid}: {time.time() - t0:.1f}s, heights {h.min():.1f} .. {h.max():.1f} m", flush=True)
    for q in (88, 82, 76, 70, 62):
        sheet.save(path, quality=q, optimize=True)
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
    ap.add_argument("--band-rows", type=int, default=256, help="rows per band inside a tile (less = less memory)")
    ap.add_argument("--fields-cache", help="reuse the whole-map fields from this file (made on the first run; "
                    "delete it when the atlas changes)")
    ap.add_argument("--sheet", help="only render the natural-wonders contact sheet to this .jpg path")
    ap.add_argument("--sheet-only", help="comma-separated wonder ids for the sheet (default: all)")
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
    if args.fields_cache and os.path.exists(args.fields_cache):
        import pickle
        with open(args.fields_cache, "rb") as f:
            fields = pickle.load(f)
        print(f"[Lyris] whole-map fields from {args.fields_cache}")
        fields._ref_masks(print)
    else:
        fields = Fields()
        if args.fields_cache:
            import pickle
            with open(args.fields_cache, "wb") as f:
                pickle.dump(fields, f, protocol=5)
    _init_worker(fields, args.seed)
    if args.sheet:
        only = set(args.sheet_only.split(",")) if args.sheet_only else None
        print(f"[Lyris] wonders sheet {make_sheet(fields, args.seed, args.sheet, only=only)} ({time.time() - t0:.0f}s)")
        return 0
    island_clearance(fields)
    print(f"[Lyris] natural wonders: {len(WONDERS)} from {os.path.relpath(WONDERS_PATH, HERE)}")

    preview_px = max(1, min(tile_px, 2048 // tiles))
    jobs = [(tx, ty, tile_px, total, args.out, preview_px, args.band_rows) for ty in range(tiles) for tx in range(tiles)]
    if args.only:
        ox, oy = (int(v) for v in args.only.split(","))
        jobs = [j for j in jobs if j[0] == ox and j[1] == oy]
    big_h = np.zeros((tiles * preview_px, tiles * preview_px), np.float32)
    big_w = np.zeros((len(LAYERS), tiles * preview_px, tiles * preview_px), np.float32)
    lo, hi, land = 1e9, -1e9, []
    if args.workers > 1 and len(jobs) > 1:
        import multiprocessing as mp
        if "fork" in mp.get_all_start_methods():
            # Workers inherit the fields copy-on-write instead of each unpickling its own copy.
            pool = ProcessPoolExecutor(args.workers, mp_context=mp.get_context("fork"))
        else:
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
    wonder_lakes, wonder_records = wonder_manifest(fields)
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
        "islands": [{"id": c["id"], "name": c["name"],
                     "islets": [{"centre_mc": [i[0], i[1]], "centre_ue": mc_to_ue(i[0], i[1], i[5]),
                                 "radius_m": [i[2], i[3]], "rotation_deg": i[4], "peak_m": i[5], "profile": i[6]}
                                for i in c["islets"]]} for c in ISLANDS],
        "lakes": fields.lakes + wonder_lakes,
        "rivers": fields.rivers,
        "wonders": wonder_records,
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
    cc = (np.arange(SRC_N) + 0.5) * SRC_PX + WORLD_MIN
    zz_, xx_ = np.meshgrid(cc, cc, indexing="ij")
    old = ~(island_footprint(xx_, zz_) | wonder_footprint(xx_, zz_))  # new islands and wonders are on purpose
    agree = (ours == atlas)[old].mean() * 100
    new_land = (ours & ~old).sum() * SRC_PX * SRC_PX / 1e6
    print(f"[Lyris] done in {time.time() - t0:.0f}s: {len(jobs)} tiles, heights {lo:.1f} .. {hi:.1f} m, "
          f"land {ours.mean() * 100:.1f}% (atlas {atlas.mean() * 100:.1f}%), coast agreement {agree:.2f}%, "
          f"new islands and wonders {new_land:.2f} km2, {len(fields.lakes)} + {len(wonder_lakes)} wonder lakes, {len(fields.rivers)} upland river reaches, spawn ground "
          f"{float(spawn_h[0]):.1f} m")
    print(f"[Lyris] scale {scale_xy:.4f} x {scale_xy:.4f} x 100, preview {prev}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
