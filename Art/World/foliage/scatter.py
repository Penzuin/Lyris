"""Scatters the world foliage over the baked Lyris terrain (T51). Deterministic (seeded).

    python Art/World/foliage/scatter.py                # after bake_terrain.py and make_species.py

Needs numpy, scipy and Pillow (the same as the bake). About 2 to 4 minutes on the full bake.

Reads   Art/World/tiles/   heights, the eight paint-layer weights, terrain_manifest.json (lakes, rivers)
        Art/World/atlas/   bidx.png (Minecraft biome per 25 m), regions.png (Reach / Greengrace / Saltreach /
                           Sunreach), so each region gets its own trees
        Art/World/landmarks.json   canon sites kept clear
        species.json       the species catalogue (variant names, sizes)
Writes  scatter/cells/c_<ix>_<iy>.bin   one file per 256 m World Partition cell with foliage
        scatter/summary.json            counts per species and group, per-cell maxima, budget figures
        scatter/grass_tint.png          world-space tint for the landscape grass (RGB tint, A dryness)
        scatter/density.png             whole-world density map (also copied to previews/)

How the forest is laid out
  * Tree density comes from the Forest paint layer (itself from the Minecraft forest biomes), blurred so
    forests have soft edges, then shaped by two octaves of low-frequency noise: groves, clearings and
    ragged edges instead of an even carpet.
  * Hard limits: no trees on water, beaches (the Sand layer, or within 22 m of the sea), slopes above
    35 degrees (fading out from 28), or above the treeline (245 m; snow pines from 170 m). Badlands,
    salt flats and desert get scrub, sage and crystals instead.
  * Extra trees: lone trees on hilltops in open meadow, avenues 6 to 16 m back from river banks.
  * Understory: bushes along forest edges and in meadow clumps; ferns and mushrooms in the shade under
    canopy; reeds on lake and river margins; lavender in loose meadow patches; rocks on steep ground and
    boulders on hillsides; crystals on salt; charred trees and glowing vent moss on volcanic ground.
  * Clearings: Moonharbor's town (600 m round the Moonwell) and every canon landmark from
    landmarks.json (its parts' footprints plus a margin, so the North Road stays a clear lane).
  * Poisson-like spacing: jittered-grid candidates, thinned by the density, then any pair closer than
    the species' spacing loses its lower-priority member.

Cell file format (little-endian): b"LYF1", u32 scatter version, i32 cell x, i32 cell y, u32 entry count;
then per entry: u16 name length, name (variant mesh name, e.g. SM_Oak_A), u32 instance count, and
count x 7 float32 (x, y, z in UE cm, yaw, pitch, roll in degrees, uniform scale).
Cell (ix, iy) covers UE X ix*25600 .. (ix+1)*25600 and Y iy*25600 .. (iy+1)*25600 (cm).
"""

import argparse
import json
import math
import os
import struct
import sys
import time

import numpy as np
from PIL import Image
from scipy import ndimage as nd
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import palette  # noqa: E402

SCATTER_VERSION = 1
SEED = 5150
CELL_M = 256.0                  # World Partition runtime grid cell (lyris_build_world WP_CELL_M)
WORLD_MIN, WORLD_SIZE = -12500.0, 25000.0
FIELD_N = 4096                  # whole-world working fields: 6.1 m per pixel
LAYERS = ["Grass", "Forest", "Sand", "Rock", "Snow", "Badlands", "Salt", "Volcanic"]

TREELINE_M = 245.0
SNOWPINE_FROM_M = 170.0
TREE_SLOPE = (28.0, 35.0)       # degrees: fade, none
COAST_CLEAR_M = 22.0            # no trees this close to the sea
MOONHARBOR = (200.0, -2300.0, 520.0, 650.0)  # MC x, z, clear radius, feathered out to (m)

# Densities are instances per hectare (10 000 m2) where their driver is 1.
TREE_DENSITY_HA = 190.0         # dense grove core: one tree per ~53 m2 (canopies touch)
MEADOW_TREE_HA = 2.0            # stray trees in open meadow
HILL_TREE_HA = 10.0             # lone trees on hilltops in meadow
RIVER_TREE_HA = 45.0            # avenues along river banks

# Regions (regions.png ids, see design/world_map.md)
REGION_GREENGRACE = (7,)
REGION_SALTREACH = (8, 9, 19)
REGION_SUNREACH = (10, 11, 12, 17, 18)

# Minecraft biome (bidx.png) -> tree species weights. Missing biomes fall back by paint layer.
B = {n: i for i, n in enumerate(json.load(open(os.path.join(WORLD, "atlas", "biome_names.json")))["biomes"])}
TREES_BY_BIOME = {
    "plains": {"oak": 6, "birch": 3, "blossom": 1},
    "sunflower plains": {"oak": 5, "birch": 4, "blossom": 1},
    "meadow": {"oak": 4, "birch": 4, "blossom": 2},
    "forest": {"oak": 6, "birch": 3, "pine": 1},
    "flower forest": {"oak": 4, "birch": 3, "blossom": 1, "cherry": 2},
    "birch forest": {"birch": 9, "oak": 1},
    "old growth birch forest": {"birch": 9, "oak": 1},
    "dark forest": {"darkwood": 7, "cypress": 2, "oak": 1},
    "old growth spruce taiga": {"pine": 9, "birch": 1},
    "old growth pine taiga": {"pine": 10},
    "taiga": {"pine": 8, "birch": 2},
    "snowy taiga": {"snowpine": 10},
    "grove": {"snowpine": 7, "pine": 3},
    "snowy slopes": {"snowpine": 10},
    "snowy plains": {"snowpine": 10},
    "ice spikes": {"snowpine": 10},
    "frozen peaks": {"snowpine": 10},
    "windswept hills": {"pine": 7, "oak": 3},
    "windswept forest": {"pine": 7, "birch": 3},
    "windswept gravelly hills": {"pine": 10},
    "stony peaks": {"pine": 10},
    "jagged peaks": {"snowpine": 10},
    "cherry grove": {"cherry": 9, "birch": 1},
    "savanna": {"olive": 9, "oak": 1},
    "savanna plateau": {"olive": 10},
    "windswept savanna": {"olive": 10},
    "wooded badlands": {"olive": 6, "deadtree": 4},
    "swamp": {"darkwood": 5, "cypress": 5},
    "mangrove swamp": {"cypress": 6, "darkwood": 4},
    "jungle": {"darkwood": 5, "oak": 3, "cypress": 2},
    "sparse jungle": {"oak": 5, "darkwood": 3, "olive": 2},
    "bamboo jungle": {"cypress": 6, "darkwood": 4},
    "mushroom fields": {"darkwood": 10},
    "pale garden": {"birch": 7, "darkwood": 3},
    "river": {"birch": 5, "oak": 5},
}
# Regional flavour: Greengrace has cherry groves among its trees; Sunreach's open ground is olive country.
# Open biomes the Forest layer misses still get their own light woods (trees per hectare at a grove peak).
BIOME_BASE_HA = {"snowy plains": 14, "snowy slopes": 8, "ice spikes": 5, "snowy beach": 0, "savanna": 10,
                 "savanna plateau": 10, "windswept savanna": 6, "meadow": 5, "plains": 3, "sunflower plains": 3,
                 "cherry grove": 70, "windswept hills": 12, "stony peaks": 4, "grove": 40, "pale garden": 60,
                 "sparse jungle": 30, "mushroom fields": 4}
COPSE_HA = 38.0                 # small copses dotted through open meadow
REGION_TREE_MIX = {"greengrace": {"cherry": 0.22}, "sunreach_open": {"olive": 0.6}}

SPACING_M = {  # minimum distance between two instances of the same group (m)
    "tree": 4.6, "bush": 2.4, "fern": 1.6, "rock": 2.5, "boulder": 9.0, "reeds": 1.6, "small": 1.4,
}
SCALE_JITTER = {"tree": (0.95, 1.45), "bush": (0.8, 1.2), "small": (0.75, 1.25), "rock": (0.6, 1.5),
                "boulder": (0.7, 1.3)}


# ----------------------------------------------------------------------------- helpers

def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _hash(ix, iz, salt):
    h = (ix.astype(np.int64) * 374761393 + iz.astype(np.int64) * 668265263 + salt * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / float(0xFFFFFF)


def vnoise(x, z, scale, salt):
    """Smooth value noise in 0..1 at world metres (pure function of position)."""
    fx, fz = x / scale, z / scale
    ix, iz = np.floor(fx), np.floor(fz)
    tx, tz = fx - ix, fz - iz
    tx, tz = tx * tx * (3 - 2 * tx), tz * tz * (3 - 2 * tz)
    ix, iz = ix.astype(np.int64), iz.astype(np.int64)
    a, b = _hash(ix, iz, salt), _hash(ix + 1, iz, salt)
    c, d = _hash(ix, iz + 1, salt), _hash(ix + 1, iz + 1, salt)
    return (a + (b - a) * tx) + ((c + (d - c) * tx) - (a + (b - a) * tx)) * tz


def fbm(x, z, scale, octaves, salt):
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total = total + vnoise(x, z, scale / 2 ** o, salt + o * 17) * amp
        norm += amp
        amp *= 0.5
    return total / norm


def to_px(x, z, n):
    return (x - WORLD_MIN) / WORLD_SIZE * n - 0.5, (z - WORLD_MIN) / WORLD_SIZE * n - 0.5


def sample(field, x, z, order=1):
    """Bilinear lookup of a whole-world field (rows = MC Z / UE Y, cols = MC X / UE X) at world metres."""
    n = field.shape[0]
    px, pz = to_px(x, z, n)
    return nd.map_coordinates(field, [pz, px], order=order, mode="nearest")


def lookup(img, x, z):
    """Nearest lookup of an atlas index image (1000 px over the world)."""
    n = img.shape[0]
    i = np.clip(((z - WORLD_MIN) / WORLD_SIZE * n).astype(int), 0, n - 1)
    j = np.clip(((x - WORLD_MIN) / WORLD_SIZE * n).astype(int), 0, n - 1)
    return img[i, j]


# ----------------------------------------------------------------------------- terrain input

class Terrain:
    """Whole-world working fields at FIELD_N plus exact heights from the native-resolution tiles."""

    def __init__(self, tiles_dir):
        with open(os.path.join(tiles_dir, "terrain_manifest.json")) as f:
            self.man = json.load(f)
        self.dir = tiles_dir
        self.nt = self.man["tiles_x"]
        self.tpx = self.man["tile_resolution"]
        self.total = self.man["total_resolution"]
        enc = self.man["height_encoding"]
        self.h_min, self.h_span = enc["min_m"], enc["max_m"] - enc["min_m"]
        self.step = WORLD_SIZE / (self.total - 1)  # metres per landscape vertex
        self._tile_cache = {}
        self._load_fields()

    def _tile(self, name, tx, ty):
        return np.asarray(Image.open(os.path.join(self.dir, f"World_{name}_x{tx}_y{ty}.png")))

    def height_tile(self, tx, ty):
        key = (tx, ty)
        if key not in self._tile_cache:
            if len(self._tile_cache) > 6:
                self._tile_cache.pop(next(iter(self._tile_cache)))
            raw = self._tile("Height", tx, ty).astype(np.float32)
            self._tile_cache[key] = self.h_min + raw / 65535.0 * self.h_span
        return self._tile_cache[key]

    def _load_fields(self):
        per = FIELD_N // self.nt
        self.H = np.zeros((FIELD_N, FIELD_N), np.float32)
        self.W = {n: np.zeros((FIELD_N, FIELD_N), np.float32) for n in LAYERS}
        for ty in range(self.nt):
            for tx in range(self.nt):
                sl = (slice(ty * per, (ty + 1) * per), slice(tx * per, (tx + 1) * per))
                h = self.height_tile(tx, ty)
                self.H[sl] = np.asarray(Image.fromarray(h).resize((per, per), Image.BILINEAR))
                for n in LAYERS:
                    w = Image.fromarray(self._tile(n, tx, ty)).resize((per, per), Image.BILINEAR)
                    self.W[n][sl] = np.asarray(w, np.float32) / 255.0
        self.px_m = WORLD_SIZE / FIELD_N

    def exact_height(self, x, z):
        """Bilinear height on the landscape's own vertices (matches the imported landscape)."""
        gx = (x - WORLD_MIN) / self.step
        gz = (z - WORLD_MIN) / self.step
        out = np.zeros_like(x)
        tx = np.clip((gx // self.tpx).astype(int), 0, self.nt - 1)
        ty = np.clip((gz // self.tpx).astype(int), 0, self.nt - 1)
        for key in set(zip(tx.tolist(), ty.tolist())):
            m = (tx == key[0]) & (ty == key[1])
            h = self.height_tile(*key)
            lx = np.clip(gx[m] - key[0] * self.tpx, 0, self.tpx - 1)
            lz = np.clip(gz[m] - key[1] * self.tpx, 0, self.tpx - 1)
            out[m] = nd.map_coordinates(h, [lz, lx], order=1, mode="nearest")
        return out


def world_masks(T, log):
    """Water, distances, slope, smoothed forest and convexity on the working grid."""
    n, px = FIELD_N, T.px_m
    H = T.H
    gy, gx = np.gradient(H, px)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    sea = H < 0.15
    # Lakes: their outline polygons from the manifest, under the lake's level.
    lake_img = Image.new("L", (n, n), 0)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(lake_img)
    for lake in T.man.get("lakes", []):
        pts = [((u / 100.0 - WORLD_MIN) / WORLD_SIZE * n, (v / 100.0 - WORLD_MIN) / WORLD_SIZE * n)
               for u, v in lake["outline_ue"]]
        if len(pts) >= 3:
            draw.polygon(pts, fill=255)
    lake_poly = np.asarray(lake_img) > 0
    lake_poly = nd.binary_dilation(lake_poly, iterations=2)
    lake_level = np.full((n, n), -1e9, np.float32)
    lake_lab, nlab = nd.label(lake_poly)
    levels = {}
    for lake in T.man.get("lakes", []):
        cx, cz = lake["centre_mc"]
        i, j = int((cz - WORLD_MIN) / WORLD_SIZE * n), int((cx - WORLD_MIN) / WORLD_SIZE * n)
        if 0 <= i < n and 0 <= j < n and lake_lab[i, j]:
            levels[lake_lab[i, j]] = max(levels.get(lake_lab[i, j], -1e9), lake["level_m"])
    for lab, lv in levels.items():
        lake_level[lake_lab == lab] = lv
    lake = lake_poly & (H < lake_level + 0.4)
    # Rivers: thick polylines from the manifest.
    river_img = Image.new("L", (n, n), 0)
    draw = ImageDraw.Draw(river_img)
    for r in T.man.get("rivers", []):
        pts = [((p[0] / 100.0 - WORLD_MIN) / WORLD_SIZE * n, (p[1] / 100.0 - WORLD_MIN) / WORLD_SIZE * n)
               for p in r["points_ue"]]
        w = max(1, int(round(r.get("width_m", 20) / px)))
        draw.line(pts, fill=255, width=w)
    river = np.asarray(river_img) > 0
    # The Minecraft river biome traces the lowland rivers the manifest does not list.
    bidx = np.asarray(Image.open(os.path.join(WORLD, "atlas", "bidx.png")))
    if bidx.ndim == 3:
        bidx = bidx[..., 0]
    river_b = np.isin(bidx, [B["river"], B["frozen river"]])
    river_b = np.asarray(Image.fromarray(river_b.astype(np.uint8) * 255).resize((n, n), Image.NEAREST)) > 0
    river |= river_b & (H < 6.0) & (slope < 8)
    water = sea | lake | river
    log(f"water: sea {sea.mean() * 100:.1f}%, lakes {lake.sum() * px * px / 1e6:.1f} km2, "
        f"rivers {river.sum() * px * px / 1e6:.1f} km2")
    dist_water = nd.distance_transform_edt(~water) * px
    dist_sea = nd.distance_transform_edt(~sea) * px
    dist_fresh = nd.distance_transform_edt(~(lake | river)) * px
    dist_river = nd.distance_transform_edt(~river) * px
    forest_s = nd.gaussian_filter(T.W["Forest"], 18.0 / px)
    convex = H - nd.gaussian_filter(H, 90.0 / px)
    return dict(slope=slope.astype(np.float32), water=water, dist_water=dist_water.astype(np.float32),
                dist_sea=dist_sea.astype(np.float32), dist_fresh=dist_fresh.astype(np.float32),
                dist_river=dist_river.astype(np.float32), forest_s=forest_s.astype(np.float32),
                convex=convex.astype(np.float32), bidx=bidx)


# ----------------------------------------------------------------------------- clearings

class Clearings:
    """Moonharbor's town disk plus every canon landmark's parts (footprint + margin)."""

    def __init__(self, path):
        pts, rad = [], []
        with open(path) as f:
            data = json.load(f)
        for lm in data["landmarks"]:
            canon = lm.get("status") == "canon" or lm.get("kind") in ("waystones", "ruin", "gate") \
                or str(lm.get("id", "")).startswith("C-ring")
            if not canon:
                continue
            for p in lm.get("parts", []):
                c = p.get("c")
                if not c:
                    continue
                size = p.get("size") or [4, 4, 4]
                pts.append((c[0], c[1]))
                rad.append(min(60.0, 0.5 * math.hypot(size[0], size[1])) + 7.0)
        self.tree = cKDTree(np.array(pts)) if pts else None
        self.rad = np.array(rad)
        self.max_r = float(self.rad.max()) if rad else 0.0
        self.count = len(pts)

    def factor(self, x, z, extra=0.0):
        """0 inside a clearing .. 1 well outside it; `extra` widens (m) the clear zone (trees)."""
        mx, mz, r0, r1 = MOONHARBOR
        d = np.hypot(x - mx, z - mz)
        f = smoothstep(d, r0, r1)
        if self.tree is not None:
            dist, idx = self.tree.query(np.stack([x, z], 1), k=6, distance_upper_bound=self.max_r + extra + 20)
            for k in range(dist.shape[1]):
                ok = np.isfinite(dist[:, k])
                r = np.zeros_like(x)
                r[ok] = self.rad[idx[ok, k]] + extra
                f = f * np.where(ok, smoothstep(dist[:, k], r, r + 10.0), 1.0)
        return f


# ----------------------------------------------------------------------------- scatter

class Out:
    def __init__(self, catalogue, rng):
        self.cat = catalogue
        self.rng = rng
        self.items = {}  # variant name -> list of (N, 7) arrays

    def add(self, species, x, z, y_m, yaw, pitch, roll, scale):
        if len(x) == 0:
            return
        variants = self.cat[species]["variants"]
        pick = self.rng.integers(0, len(variants), len(x))
        for k, v in enumerate(variants):
            m = pick == k
            if m.any():
                arr = np.stack([x[m] * 100, z[m] * 100, y_m[m] * 100, yaw[m], pitch[m], roll[m], scale[m]], 1)
                self.items.setdefault(v["name"], []).append(arr.astype(np.float32))

    def species_of(self, name):
        for s, spec in self.cat.items():
            if any(v["name"] == name for v in spec["variants"]):
                return s
        return None


def candidates(rng, x0, z0, x1, z1, spacing):
    """Jittered grid: one candidate per spacing x spacing square, with a random priority."""
    xs = np.arange(x0, x1, spacing)
    zs = np.arange(z0, z1, spacing)
    gx, gz = np.meshgrid(xs, zs)
    gx = gx.ravel() + rng.uniform(0, spacing, gx.size)
    gz = gz.ravel() + rng.uniform(0, spacing, gz.size)
    return gx, gz


def thin_pairs(x, z, prio, radius):
    """Drops the lower-priority member of every pair closer than `radius` (one pass)."""
    if len(x) < 2:
        return np.ones(len(x), bool)
    pairs = cKDTree(np.stack([x, z], 1)).query_pairs(radius, output_type="ndarray")
    keep = np.ones(len(x), bool)
    if len(pairs):
        lose = np.where(prio[pairs[:, 0]] < prio[pairs[:, 1]], pairs[:, 0], pairs[:, 1])
        keep[lose] = False
    return keep


def choose(rng, weights_list):
    """Per-candidate weighted choice. weights_list: dict species -> (N,) weights."""
    names = list(weights_list)
    w = np.stack([weights_list[n] for n in names], 1)
    total = w.sum(1)
    r = rng.random(len(total)) * total
    idx = (np.cumsum(w, 1) < r[:, None]).sum(1)
    idx = np.clip(idx, 0, len(names) - 1)
    return np.array(names)[idx], total > 0


class Scatter:
    def __init__(self, T, M, clear, catalogue, seed, log):
        self.T, self.M, self.clear, self.log = T, M, clear, log
        self.rng = np.random.default_rng(seed)
        self.out = Out(catalogue, np.random.default_rng(seed + 1))
        self.region = np.asarray(Image.open(os.path.join(WORLD, "atlas", "regions.png")))
        self.islands = T.man.get("islands", [])

    # fields at points -----------------------------------------------------------------
    def fields(self, x, z):
        T, M = self.T, self.M
        f = {n: sample(T.W[n], x, z) for n in LAYERS}
        f["h"] = sample(T.H, x, z)
        for k in ("slope", "dist_water", "dist_sea", "dist_fresh", "dist_river", "forest_s", "convex"):
            f[k] = sample(M[k], x, z)
        # Biome lookups jittered by up to 35 m, so biome borders interleave instead of cutting straight.
        jx = x + self.rng.uniform(-35, 35, len(x))
        jz = z + self.rng.uniform(-35, 35, len(z))
        f["biome"] = lookup(M["bidx"], jx, jz)
        f["region"] = lookup(self.region, jx, jz)
        f["clear"] = self.clear.factor(x, z)
        f["clear_tree"] = self.clear.factor(x, z, extra=6.0)
        f["grove"] = fbm(x, z, 420.0, 3, 101)          # groves and clearings inside forests
        f["patch"] = fbm(x, z, 140.0, 2, 202)          # smaller patches (flowers, lavender, bushes)
        f["copse"] = fbm(x, z, 230.0, 2, 303)          # independent noise for meadow copses
        f["edge"] = f["forest_s"] * (1 - f["forest_s"]) * 4  # 1 at the forest edge, 0 deep inside or out
        return f

    def ok_ground(self, f):
        return (f["h"] > 0.6) & (f["dist_water"] > 1.5)

    # trees ----------------------------------------------------------------------------
    def tree_density(self, f):
        """Trees per hectare."""
        forest = np.clip(f["forest_s"] * 1.6, 0, 1)
        grove = smoothstep(f["grove"], 0.30, 0.62)          # ~30% of forest area becomes clearings / thin
        core = TREE_DENSITY_HA * forest ** 1.4 * (0.12 + 0.88 * grove)
        open_ground = (1 - forest) * f["Grass"]
        meadow = MEADOW_TREE_HA * open_ground * smoothstep(f["patch"], 0.55, 0.8)
        hill = HILL_TREE_HA * open_ground * smoothstep(f["convex"], 2.5, 8.0)
        river = RIVER_TREE_HA * smoothstep(f["dist_river"], 4.0, 7.0) * (1 - smoothstep(f["dist_river"], 12.0, 18.0)) \
            * (1 - forest) * (f["h"] < 120)
        copse = COPSE_HA * open_ground * smoothstep(f["copse"], 0.70, 0.82)
        base = np.zeros_like(core)
        for bname, ha in BIOME_BASE_HA.items():
            base = base + ha * (f["biome"] == B[bname])
        base = base * smoothstep(f["grove"], 0.35, 0.65)
        d = core + meadow + hill + river + copse + base
        # Greengrace's crater forest is canon "lush within 1.4 km of (-1650, 3330)".
        g = 1 - smoothstep(np.hypot(f["x"] + 1650, f["z"] - 3330), 900, 1400)
        d = np.maximum(d, TREE_DENSITY_HA * 0.75 * g * (0.4 + 0.6 * grove) * (f["Forest"] + f["Grass"] > 0.5))
        # Hard limits.
        d *= 1 - smoothstep(f["slope"], *TREE_SLOPE)
        d *= 1 - smoothstep(f["h"], TREELINE_M - 25, TREELINE_M)
        d *= smoothstep(f["dist_sea"], COAST_CLEAR_M, COAST_CLEAR_M + 18)
        d *= smoothstep(f["dist_water"], 2.5, 5.0)
        d *= 1 - smoothstep(f["Sand"], 0.25, 0.45)
        d *= 1 - smoothstep(f["Salt"] + f["Badlands"] * 0.85, 0.3, 0.5)
        d *= 1 - smoothstep(f["Rock"], 0.45, 0.7)
        d *= f["clear_tree"]
        # Volcanic ground keeps a few charred trees.
        d = np.maximum(d, 10.0 * smoothstep(f["Volcanic"], 0.3, 0.6) * smoothstep(f["grove"], 0.45, 0.7)
                       * (1 - smoothstep(f["slope"], *TREE_SLOPE)) * f["clear_tree"])
        # Badlands get the odd lone dead tree or olive.
        d = np.maximum(d, 1.2 * smoothstep(f["Badlands"], 0.4, 0.7) * (f["slope"] < 25) * f["clear_tree"])
        return d * self.ok_ground(f)

    def tree_species(self, f):
        n = len(f["h"])
        names = {}
        biome_names = list(B)
        for bname, mix in TREES_BY_BIOME.items():
            m = f["biome"] == B[bname]
            for sp, w in mix.items():
                names.setdefault(sp, np.zeros(n))
                names[sp][m] += w
        unknown = sum(names.values()) == 0
        # Fallbacks (new islands, ocean-tagged land): by island character and paint layer.
        names.setdefault("oak", np.zeros(n))
        names.setdefault("pine", np.zeros(n))
        names.setdefault("birch", np.zeros(n))
        names["oak"][unknown] += 5
        names["pine"][unknown] += 3
        names["birch"][unknown] += 2
        isl = self.island_of(f["x"], f["z"])
        for iid, sp in (("B", {"pine": 9, "birch": 1}), ("G", {"birch": 6, "oak": 4}), ("H", {"darkwood": 6, "deadtree": 2, "olive": 2}),
                        ("F", {"snowpine": 10}), ("C", {"oak": 7, "blossom": 3})):
            m = isl == iid
            if m.any():
                for k in names:
                    names[k][m] = 0
                for s, w in sp.items():
                    names.setdefault(s, np.zeros(n))
                    names[s][m] = w
        # Regional flavour.
        gg = np.isin(f["region"], REGION_GREENGRACE)
        tot = sum(names.values())
        names.setdefault("cherry", np.zeros(n))
        cherry_patch = smoothstep(f["patch"], 0.5, 0.7)
        names["cherry"] += gg * tot * REGION_TREE_MIX["greengrace"]["cherry"] * (0.3 + 2.0 * cherry_patch)
        sun_open = np.isin(f["region"], REGION_SUNREACH) & (f["forest_s"] < 0.35)
        names.setdefault("olive", np.zeros(n))
        names["olive"] += sun_open * tot * REGION_TREE_MIX["sunreach_open"]["olive"]
        # Height and ground override: snow pines up high and on snow; dead trees on volcanic ground.
        snowy = (f["Snow"] > 0.35) | (f["h"] > SNOWPINE_FROM_M + 20 * (f["grove"] - 0.5))
        conifer = np.zeros(n)
        for k in ("pine", "oak", "birch", "darkwood", "cypress", "olive"):
            if k in names:
                conifer += names[k] * snowy
                names[k] = names[k] * ~snowy
        names.setdefault("snowpine", np.zeros(n))
        names["snowpine"] += conifer
        volcanic = f["Volcanic"] > 0.35
        names.setdefault("deadtree", np.zeros(n))
        for k in list(names):
            if k != "deadtree":
                names[k] = names[k] * ~volcanic
        names["deadtree"] += volcanic * 1.0
        bad = (f["Badlands"] > 0.4) & ~volcanic
        for k in list(names):
            if k not in ("deadtree", "olive"):
                names[k] = names[k] * ~bad
        names["olive"] += bad * 0.5
        names["deadtree"] += bad * 0.5
        _ = biome_names
        return choose(self.rng, names)

    def island_of(self, x, z):
        out = np.full(len(x), "", dtype="<U2")
        for c in self.islands:
            for i in c["islets"]:
                cx, cz = i["centre_mc"]
                rx, rz = i["radius_m"]
                m = ((x - cx) / (rx + 40)) ** 2 + ((z - cz) / (rz + 40)) ** 2 < 1
                out[m] = c["id"]
        return out

    def trees(self, box):
        rng = self.rng
        x, z = candidates(rng, *box, 4.0)
        f = self.fields(x, z)
        f["x"], f["z"] = x, z
        dens = self.tree_density(f)
        keep = rng.random(len(x)) < dens * 16.0 / 10000.0  # spacing 4 m: 16 m2 per candidate
        x, z = x[keep], z[keep]
        f = {k: (v[keep] if isinstance(v, np.ndarray) and v.shape == keep.shape else v) for k, v in f.items()}
        if not len(x):
            return
        prio = rng.random(len(x))
        k2 = thin_pairs(x, z, prio, SPACING_M["tree"])
        x, z = x[k2], z[k2]
        f = {k: v[k2] for k, v in f.items()}
        sp, ok = self.tree_species(f)
        # Lone hilltop trees and the rare blossom grow a little bigger.
        lone = (f["forest_s"] < 0.2)
        scale = rng.uniform(*SCALE_JITTER["tree"], len(x)) * np.where(lone, 1.15, 1.0)
        tilt = rng.normal(0, 1.5, (len(x), 2))
        for s in np.unique(sp[ok]):
            m = ok & (sp == s)
            self.place(s, x[m], z[m], scale[m], tilt[m], sink=0.12)

    # understory ------------------------------------------------------------------------
    def understory(self, box):
        rng = self.rng
        x, z = candidates(rng, *box, 2.0)
        f = self.fields(x, z)
        f["x"], f["z"] = x, z
        ground = self.ok_ground(f) & (f["clear"] > 0.5)
        flat = 1 - smoothstep(f["slope"], 30, 40)
        open_g = (1 - np.clip(f["forest_s"] * 1.25, 0, 1))
        canopy = np.clip(f["forest_s"] * 1.25, 0, 1) * smoothstep(f["grove"], 0.3, 0.6)
        reach_meadow = np.isin(f["region"], (0, 1, 2, 3, 4, 5, 6, 7, 13, 14, 16, 17)) | (f["region"] == 255)
        per_ha = {
            # bushes: forest edges, meadow clumps
            "bush": (70 * f["edge"] + 10 * open_g * smoothstep(f["patch"], 0.6, 0.8) + 25 * canopy)
            * flat * (f["Snow"] < 0.35) * (f["Badlands"] + f["Salt"] < 0.4) * (f["Volcanic"] < 0.3)
            * (f["Sand"] < 0.4) * (f["h"] < TREELINE_M),
            "frostshrub": 60 * smoothstep(f["Snow"], 0.3, 0.6) * flat * smoothstep(f["patch"], 0.35, 0.6)
            * (f["slope"] < 30),
            "fern": 130 * canopy * flat * (f["Snow"] < 0.3) * (f["Volcanic"] < 0.3) * (f["Badlands"] < 0.3),
            "mushrooms": 30 * canopy * smoothstep(f["patch"], 0.55, 0.75)
            + 160 * (f["biome"] == B["mushroom fields"]),
            "reeds": 700 * (1 - smoothstep(f["dist_fresh"], 3.0, 12.0)) * (f["slope"] < 14) * (f["h"] < 200)
            * smoothstep(f["patch"], 0.25, 0.5) + 120 * (1 - smoothstep(f["dist_sea"], 4, 14)) * (f["slope"] < 10)
            * (f["Sand"] < 0.5) * smoothstep(f["patch"], 0.6, 0.8),
            "lavender": 220 * open_g * f["Grass"] * smoothstep(f["patch"], 0.68, 0.82) * smoothstep(f["grove"], 0.4, 0.7)
            * reach_meadow * (f["slope"] < 22) * (f["Snow"] < 0.2) * (f["Sand"] < 0.3),
            "scrub": 200 * smoothstep(f["Badlands"], 0.25, 0.55) * smoothstep(f["patch"], 0.3, 0.7)
            + 25 * smoothstep(f["Sand"], 0.5, 0.8) * (f["dist_sea"] > 60) * (f["biome"] == B["desert"]),
            "sage": 90 * (f["biome"] == B["desert"]) * smoothstep(f["patch"], 0.3, 0.6)
            + 30 * smoothstep(f["Badlands"], 0.2, 0.5)
            + 25 * np.isin(f["biome"], [B["savanna"], B["savanna plateau"], B["windswept savanna"]])
            * smoothstep(f["patch"], 0.5, 0.7),
            "crystals": 70 * smoothstep(f["Salt"], 0.35, 0.65) * smoothstep(f["patch"], 0.45, 0.75),
            "ventmoss": 60 * smoothstep(f["Volcanic"], 0.35, 0.7) * smoothstep(f["patch"], 0.4, 0.7),
            "rock": (30 * smoothstep(f["slope"], 18, 32) * (1 - smoothstep(f["slope"], 48, 60))
                     + 18 * smoothstep(f["Rock"], 0.3, 0.6) + 2.5 * open_g * smoothstep(f["patch"], 0.7, 0.85)
                     + 8 * smoothstep(f["Badlands"], 0.3, 0.6)),
            "pebbles": 25 * (1 - smoothstep(f["dist_water"], 2.0, 8.0)) * (f["slope"] < 15)
            + 6 * smoothstep(f["Rock"], 0.3, 0.6),
        }
        prio = rng.random(len(x))
        roll = rng.random(len(x))
        # One draw per candidate: species compete for the same 4 m2 so totals stay predictable.
        cum = np.zeros(len(x))
        chosen = np.full(len(x), "", dtype="<U12")
        for name, d in per_ha.items():
            d = d * ground
            if name in ("bush", "fern", "lavender", "reeds", "mushrooms", "frostshrub"):
                d = d * (f["clear"] > 0.9)
            p = d * 4.0 / 10000.0
            hit = (roll >= cum) & (roll < cum + p) & (chosen == "")
            chosen[hit] = name
            cum = cum + p
        for name in per_ha:
            m = chosen == name
            if not m.any():
                continue
            xs, zs = x[m], z[m]
            group = {"bush": "bush", "frostshrub": "bush", "scrub": "bush", "sage": "bush", "rock": "rock",
                     "fern": "fern", "reeds": "reeds"}.get(name, "small")
            k2 = thin_pairs(xs, zs, prio[m], SPACING_M[group] * 0.8)
            xs, zs = xs[k2], zs[k2]
            jit = SCALE_JITTER.get(group, SCALE_JITTER["small"])
            scale = rng.uniform(*jit, len(xs))
            tilt = rng.normal(0, 3.0, (len(xs), 2))
            self.place(name, xs, zs, scale, tilt, align=0.6 if group in ("rock", "small") else 0.35,
                       sink=0.05 if group != "rock" else 0.25)

    def boulders(self, box):
        rng = self.rng
        x, z = candidates(rng, *box, 8.0)
        f = self.fields(x, z)
        f["x"], f["z"] = x, z
        d = (6.0 * smoothstep(f["slope"], 12, 28) * (1 - smoothstep(f["slope"], 45, 55))
             + 3.0 * smoothstep(f["Rock"], 0.25, 0.6) + 0.6 * smoothstep(f["convex"], 3, 10)
             + 1.5 * smoothstep(f["Badlands"], 0.3, 0.6)) * smoothstep(f["grove"], 0.35, 0.65)
        d *= self.ok_ground(f) * f["clear_tree"] * (f["dist_sea"] > 6) * (f["Salt"] < 0.4)
        keep = rng.random(len(x)) < d * 64.0 / 10000.0
        x, z = x[keep], z[keep]
        if not len(x):
            return
        k2 = thin_pairs(x, z, rng.random(len(x)), SPACING_M["boulder"])
        x, z = x[k2], z[k2]
        self.place("boulder", x, z, rng.uniform(*SCALE_JITTER["boulder"], len(x)),
                   rng.normal(0, 4.0, (len(x), 2)), align=0.7, sink=0.6)

    # placement -------------------------------------------------------------------------
    def place(self, species, x, z, scale, tilt, align=0.0, sink=0.1):
        """Exact ground height, yaw, slope-aligned tilt; z sunk by `sink` m (more on slopes)."""
        if not len(x):
            return
        y = self.T.exact_height(x, z)
        e = 0.8
        hx = (self.T.exact_height(x + e, z) - self.T.exact_height(x - e, z)) / (2 * e)
        hz = (self.T.exact_height(x, z + e) - self.T.exact_height(x, z - e)) / (2 * e)
        steep = np.hypot(hx, hz)
        y = y - sink - steep * 0.35 * scale
        # Up vector leans with the ground normal by `align`; solve Unreal pitch/roll for it after the yaw
        # (FRotationMatrix: Z axis = (-CR*SP, SR, CR*CP) in the yawed frame).
        yaw = self.rng.uniform(0, 360, len(x))
        nx, ny = -hx * align, -hz * align
        inv = 1.0 / np.sqrt(nx * nx + ny * ny + 1.0)
        nx, ny, nz = nx * inv, ny * inv, inv
        cy, sy = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
        lx, ly = cy * nx + sy * ny, -sy * nx + cy * ny
        roll = np.degrees(np.arcsin(np.clip(ly, -1, 1))) + tilt[:, 1]
        pitch = np.degrees(np.arctan2(-lx, nz)) + tilt[:, 0]
        self.out.add(species, x, z, y, yaw, pitch, roll, scale)


# ----------------------------------------------------------------------------- output

def write_cells(out, out_dir, log):
    cells_dir = os.path.join(out_dir, "cells")
    os.makedirs(cells_dir, exist_ok=True)
    for old in os.listdir(cells_dir):
        os.remove(os.path.join(cells_dir, old))
    per_cell = {}
    counts = {}
    for name, chunks in out.items.items():
        arr = np.concatenate(chunks)
        counts[name] = len(arr)
        ix = np.floor(arr[:, 0] / (CELL_M * 100)).astype(int)
        iy = np.floor(arr[:, 1] / (CELL_M * 100)).astype(int)
        key = ix * 1000 + iy
        order = np.argsort(key, kind="stable")
        arr, key, ix, iy = arr[order], key[order], ix[order], iy[order]
        bounds = np.flatnonzero(np.diff(key)) + 1
        for s, e in zip(np.r_[0, bounds], np.r_[bounds, len(key)]):
            per_cell.setdefault((int(ix[s]), int(iy[s])), {})[name] = arr[s:e]
    for (ix, iy), entries in per_cell.items():
        with open(os.path.join(cells_dir, f"c_{ix}_{iy}.bin"), "wb") as fh:
            fh.write(b"LYF1" + struct.pack("<IiiI", SCATTER_VERSION, ix, iy, len(entries)))
            for name in sorted(entries):
                a = np.ascontiguousarray(entries[name], dtype="<f4")
                nb = name.encode()
                fh.write(struct.pack("<H", len(nb)) + nb + struct.pack("<I", len(a)))
                fh.write(a.tobytes())
    log(f"wrote {len(per_cell)} cell files to {cells_dir}")
    return per_cell, counts


def grass_tint(T, M, path):
    """World tint for landscape grass blades: lush green by default, wheat gold on Sunreach's open
    plains and savanna, dusty in the badlands, frosted near snow. Alpha is dryness (0 lush .. 1 dry):
    the wheat tufts show only where it is high, the wildflowers only where it is low."""
    n = 1024
    xs = (np.arange(n) + 0.5) / n * WORLD_SIZE + WORLD_MIN
    gx, gz = np.meshgrid(xs, xs)
    x, z = gx.ravel(), gz.ravel()
    w = {k: sample(T.W[k], x, z) for k in LAYERS}
    bidx = lookup(M["bidx"], x, z)
    region = lookup(np.asarray(Image.open(os.path.join(WORLD, "atlas", "regions.png"))), x, z)
    savanna = np.isin(bidx, [B["savanna"], B["savanna plateau"], B["windswept savanna"], B["desert"],
                             B["wooded badlands"], B["sparse jungle"]]).astype(float)
    sun_open = (np.isin(region, REGION_SUNREACH) * (sample(M["forest_s"], x, z) < 0.3)).astype(float)
    dry = np.clip(np.maximum(savanna, 0.75 * sun_open) + w["Badlands"] * 0.8, 0, 1)
    dry = nd.gaussian_filter(dry.reshape(n, n), 2.0).ravel()
    dusty = np.clip(w["Badlands"] + w["Salt"] + w["Volcanic"] * 0.5, 0, 1)
    frost = smoothstep(w["Snow"], 0.15, 0.5)
    forest = np.clip(w["Forest"] * 1.3, 0, 1)
    rgb = lambda k: np.array(palette.rgb(palette.GRASS_TINT[k]))  # noqa: E731
    base = rgb("meadow")[None] * (1 - forest[:, None]) + rgb("forest")[None] * forest[:, None]
    base = base * (1 - dry[:, None]) + rgb("dry")[None] * dry[:, None]
    base = base * (1 - dusty[:, None] * 0.6) + rgb("dusty")[None] * dusty[:, None] * 0.6
    base = base * (1 - frost[:, None]) + rgb("frost")[None] * frost[:, None]
    # Stored relative to the meadow colour (the grass material multiplies its own meadow colour by 2x this).
    rel = np.clip(base / rgb("meadow")[None] * 0.5, 0, 1)
    img = np.concatenate([rel, dry[:, None]], 1).reshape(n, n, 4)
    Image.fromarray((img * 255).round().astype(np.uint8), "RGBA").save(path)


def density_map(T, out, path, catalogue):
    """Whole-world map: terrain in muted tones, trees as dark green density, understory as warm dots."""
    n = 2048
    H = np.asarray(Image.fromarray(T.H).resize((n, n), Image.BILINEAR))
    land = H > 0
    img = np.zeros((n, n, 3))
    img[:] = np.array(palette.rgb("2E8A9C"))
    shade = np.clip(0.75 + np.gradient(H, axis=1) * 0.04 - np.gradient(H, axis=0) * 0.04, 0.5, 1.1)
    ground = np.array(palette.rgb("EFE2C4")) * shade[..., None]
    img[land] = ground[land]
    trees = np.zeros((n, n))
    under = np.zeros((n, n))
    group_of = {}
    for s, spec in catalogue.items():
        for v in spec["variants"]:
            group_of[v["name"]] = spec["group"]
    for name, chunks in out.items.items():
        arr = np.concatenate(chunks)
        i = np.clip(((arr[:, 1] / 100 - WORLD_MIN) / WORLD_SIZE * n).astype(int), 0, n - 1)
        j = np.clip(((arr[:, 0] / 100 - WORLD_MIN) / WORLD_SIZE * n).astype(int), 0, n - 1)
        target = trees if group_of.get(name) == "trees" else under
        np.add.at(target, (i, j), 1)
    px_ha = (WORLD_SIZE / n) ** 2 / 10000.0
    t = np.clip(nd.gaussian_filter(trees, 1.0) / px_ha / 90.0, 0, 1) ** 0.7
    u = np.clip(nd.gaussian_filter(under, 1.0) / px_ha / 300.0, 0, 1)
    green = np.array(palette.rgb("9DB872"))
    img = img * (1 - u[..., None] * 0.5) + green * shade[..., None] * u[..., None] * 0.5
    dark = np.array(palette.rgb("36584F"))
    img = img * (1 - t[..., None] * 0.92) + dark * shade[..., None] * t[..., None] * 0.92
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path, quality=88)


# ----------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tiles", default=os.path.join(WORLD, "tiles"))
    ap.add_argument("--out", default=os.path.join(HERE, "scatter"))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--box", help="only this MC box x0,z0,x1,z1 (for previews and tests)")
    args = ap.parse_args(argv)
    t0 = time.time()

    def log(msg):
        print(f"[Lyris] {msg}  ({time.time() - t0:.0f}s)", flush=True)

    with open(os.path.join(HERE, "species.json")) as f:
        catalogue = json.load(f)["species"]
    T = Terrain(args.tiles)
    log(f"terrain: bake v{T.man['bake_version']}, {T.total} px, {T.step:.2f} m per vertex"
        + ("  (preview bake: fine for a look, rerun after the full bake)" if T.man.get("preview") else ""))
    M = world_masks(T, log)
    clear = Clearings(os.path.join(WORLD, "landmarks.json"))
    log(f"clearings: Moonharbor plus {clear.count} canon landmark parts")
    S = Scatter(T, M, clear, catalogue, args.seed, log)

    # Work in 1 km blocks over the land's bounding box (keeps memory small, results deterministic).
    land = T.H > 0
    rows, cols = np.nonzero(land)
    x_lo = WORLD_MIN + cols.min() * T.px_m - 50
    x_hi = WORLD_MIN + (cols.max() + 1) * T.px_m + 50
    z_lo = WORLD_MIN + rows.min() * T.px_m - 50
    z_hi = WORLD_MIN + (rows.max() + 1) * T.px_m + 50
    if args.box:
        x_lo, z_lo, x_hi, z_hi = (float(v) for v in args.box.split(","))
    block = 1024.0
    blocks = [(bx, bz) for bz in np.arange(math.floor(z_lo / block) * block, z_hi, block)
              for bx in np.arange(math.floor(x_lo / block) * block, x_hi, block)]
    for k, (bx, bz) in enumerate(blocks):
        i0, i1 = to_px(np.array([bx, bx + block]), np.array([bz, bz + block]), FIELD_N)
        sub = land[max(0, int(i1[0])):max(0, int(i1[1]) + 1), max(0, int(i0[0])):max(0, int(i0[1]) + 1)]
        if not sub.any():
            continue
        box = (bx, bz, bx + block, bz + block)
        S.trees(box)
        S.boulders(box)
        S.understory(box)
        if k % 25 == 0:
            n_now = sum(len(c) for v in S.out.items.values() for c in v)
            log(f"block {k + 1}/{len(blocks)}")
            _ = n_now
    per_cell, counts = write_cells(S.out, args.out, log)

    # Summary and budget.
    group_of, species_of = {}, {}
    for s, spec in catalogue.items():
        for v in spec["variants"]:
            group_of[v["name"]], species_of[v["name"]] = spec["group"], s
    by_species, by_group = {}, {}
    for name, c in counts.items():
        by_species[species_of[name]] = by_species.get(species_of[name], 0) + c
        by_group[group_of[name]] = by_group.get(group_of[name], 0) + c
    cell_trees = [sum(len(a) for nme, a in e.items() if group_of[nme] == "trees") for e in per_cell.values()]
    cell_all = [sum(len(a) for a in e.values()) for e in per_cell.values()]
    cell_comps = [len(e) for e in per_cell.values()]
    land_km2 = float(land.mean() * WORLD_SIZE * WORLD_SIZE / 1e6)
    summary = {
        "scatter_version": SCATTER_VERSION, "seed": args.seed, "bake_version": T.man["bake_version"],
        "preview_bake": bool(T.man.get("preview")), "cell_m": CELL_M, "land_km2": round(land_km2, 1),
        "total": int(sum(counts.values())), "by_group": by_group, "by_species": dict(sorted(by_species.items())),
        "by_variant": dict(sorted(counts.items())), "cells": len(per_cell),
        "per_cell": {"max_trees": int(max(cell_trees or [0])), "mean_trees": round(float(np.mean(cell_trees or [0])), 1),
                     "max_instances": int(max(cell_all or [0])), "mean_instances": round(float(np.mean(cell_all or [0])), 1),
                     "max_components": int(max(cell_comps or [0])), "mean_components": round(float(np.mean(cell_comps or [0])), 1)},
        "trees_per_km2_land": round(by_group.get("trees", 0) / max(land_km2, 1e-6)),
        "file_bytes": int(sum(os.path.getsize(os.path.join(args.out, "cells", f))
                              for f in os.listdir(os.path.join(args.out, "cells")))),
    }
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    grass_tint(T, M, os.path.join(args.out, "grass_tint.png"))
    os.makedirs(os.path.join(HERE, "previews"), exist_ok=True)
    density_map(T, S.out, os.path.join(args.out, "density.jpg"), catalogue)
    log(f"done: {summary['total']} instances ({by_group}) in {len(per_cell)} cells; "
        f"{summary['trees_per_km2_land']} trees per km2 of land; per cell max {summary['per_cell']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
