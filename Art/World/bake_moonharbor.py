"""Bakes Moonharbor, the 1.0 release area (T55), as its own small, high-detail map.

    python Art/World/bake_moonharbor.py                # full bake: ~1 m per vertex (about 6 to 10 minutes)
    python Art/World/bake_moonharbor.py --preview      # 4 m per vertex, about 1 minute (do not import)
    python Art/World/bake_moonharbor.py --previews-only  # re-render the preview images from the last bake

Needs Python 3.9+ with numpy, scipy and Pillow, like bake_terrain.py. Uses bake_terrain.py's own terrain
function (the whole-world bake) and adds Moonharbor's Genshin-style detail on top, so tags, coordinates
and landmarks line up 1:1 with the world (design/world_map.md: MC X -> UE X, MC Z -> UE Y,
UE Z = (MC Y - 63) * 100).

What it makes (Art/World/moonharbor/, not in git; rebuilt by this script):
  Moonharbor_Height.png    4033 x 4033, 16-bit, 1 m per vertex: X -1450..2582, Z -4650..-618. All 1.0 land
                           (town, Keep Hill, Wayside Fields, Mistwater Shore), Starfall Bay, the Teeth, and the
                           Observatory and the Delvers' Gate (1.1) for the view. 32 x 32 components of 2 x 2
                           sections of 63 quads (1024 components).
  Lampwick_Height.png      1009 x 505, 16-bit, 2 m per vertex: X -3466..-1450, Z -5000..-3992. The Lampwick
                           Gulf west of the main square and the six Lampwick Skerries (walkable land).
                           16 x 8 components of 63 quads.
  backdrop.glb             the whole 25 km world as one low-detail mesh (25 m, painted vertex colours),
                           with a hole under the two landscapes: the horizon shows the Observatory, the
                           white north and the far shores, never a cliff edge.
  biome/T_LyrisBiomeA/B.png, biome_maps.json   the T50 material's biome maps over Moonharbor (1.5 m)
  Moonharbor_SeaGround.png the ground under the sea for the T19 sea's shallows and shore foam (3 m)
  frame_height.npy, frame_extra.png             for foliage/scatter_moonharbor.py (heights, fields, hedges, paths)
  moonharbor_manifest.json landscapes (files, location, scale, components), lakes, rivers, spawn, the 1.0
                           landmark ids, bridges, bounds, calm zone; read by Content/Python/lyris_build_moonharbor.py
Previews (in git): Art/World/preview_mh_overview.jpg, preview_mh_bay.jpg, preview_mh_keephill.jpg,
preview_mh_fields.jpg, preview_mh_skerries.jpg, preview_mh_shore.jpg.

Moonharbor's detail (every value is a pure function of position, seeded, like the world bake):
  * Coasts follow a smoothed version of the map's coastline (the 25 m atlas made staircase shores).
  * Starfall Bay: the drowned Aurenhal terraces step down the bowl walls (treads, risers, low parapets,
    collapsed stretches, radial stair streets), a clean sand beach and shelf in the bay's south lobe, and
    Oruth's pit with a flat floor at exactly Y -40.
  * Keep Hill: a layered cliff face toward the bay, the switchback Keep Road from (326, -2378) up to the
    gate (Y 138), the flat waystone upland at (725, -2650), Y 128.
  * Wayside Fields: flat field terraces (farm plots, T13/T15) with low banks and hedgerow lines between them,
    a ford on the river branch.
  * Mistwater Shore: a rocky coast of low cliffs and sand coves, the Old Coast Road on the cliff tops from
    Ilwen's Lighthouse round the bay, and a bridge span over the Mistwater's mouth.
  * The Teeth: a reef shelf and rocks breaking the surface. The Lampwick Skerries: sand coves and tors.
Canon heights are kept: the town core is restored to the world bake's ground and the canon pads (quay,
promenade, lighthouse terrace Y 70, Syrena's islet, Keep bailey Y 138) are re-applied last.
"""

import argparse
import json
import math
import os
import pickle
import struct
import sys
import time

import numpy as np
from PIL import Image
from scipy import ndimage as nd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import bake_terrain as bt  # noqa: E402
from bake_terrain import lerp, smoothstep  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

MH_VERSION = 1
OUT = os.path.join(HERE, "moonharbor")
CHUNKS_PNG = os.path.join(ROOT, "design", "world_chunks", "chunks.png")
LANDMARKS_JSON = os.path.join(HERE, "landmarks.json")

# The two landscapes (MC metres; heightmap row 0 = north = smallest Z, column 0 = west = smallest X).
LANDSCAPES = [
    {"name": "Moonharbor", "file": "Moonharbor_Height.png", "x0": -1450.0, "z0": -4650.0, "nx": 4033, "nz": 4033,
     "step": 1.0, "quads_per_section": 63, "sections_per_component": 2},   # 32 x 32 components (1024)
    {"name": "Lampwick", "file": "Lampwick_Height.png", "x0": -3466.0, "z0": -5000.0, "nx": 1009, "nz": 505,
     "step": 2.0, "quads_per_section": 63, "sections_per_component": 1},   # 16 x 8 components (128)
]
PREVIEW_STEP = 4.0

# One square frame over both landscapes for the biome maps, the sea ground map, the scatter and the
# precomputed regional fields (x0, z0, size in m; x0 and z0 differ).
FRAME = (-3552.0, -5100.0, 6144.0)
REGION_STEP = 2.0
BIOME_RES = 4096           # 1.5 m per pixel
SEA_GROUND_RES = 2048      # 3 m per pixel
BACKDROP_STEP = 25.0       # the whole world at the atlas's own resolution: 1001 x 1001 vertices
BACKDROP_SINK = 6.0        # backdrop vertices under a landscape drop this far, out of sight
BACKDROP_HOLE_INSET = 30.0  # backdrop triangles this far inside a landscape are left out

WAVE_1_0 = {1, 2, 3, 4, 100, 101}   # chunk ids of 1.0 (design/world_chunks.md)
TOWN_CORE = (100.0, -2565.0, 620.0, -2120.0)
BOUNDS_MC = (-3600.0, -5500.0, 2700.0, -500.0)   # invisible walls (x0, z0, x1, z1): the 1.0 waters and land
CALM_ZONE_UE = (-20000.0, -266000.0, 55000.0, 40000.0)   # same as lyris_build_world / DefaultGame.ini

# Starfall Bay
BAY_CENTRE = (-170.0, -2660.0)
ORUTH = (-120.0, -2612.0, -103.0)   # pit centre and floor (m): MC Y -40
TERRACE_LEVELS = [2.5, 6.0, 10.0, 15.0, 21.0, 28.0, 36.0, 45.0, 55.0, 66.0, 78.0, 91.0]  # m below the sea
LOBE = (-120.0, -2235.0, 250.0, 125.0)   # the bay's south lobe (beach and shelf): centre, half sizes (m)

# Keep Hill
KEEP_ROAD = [(326, -2378), (330, -2420), (388, -2512), (388, -2425), (420, -2512), (500, -2440), (501, -2526)]
KEEP_ROAD_Y = (77.2, 138.0)   # MC Y at the start (canon, the Heights) and at the gate
WAYSTONE = (725.0, -2650.0, 128.0)
CLIFF_Z = (-2965.0, -2700.0)   # Keep Hill's bay-facing cliff runs between these Z (fading out before the town)

# Wayside Fields: a patchwork of field terraces (rotated grid)
FIELDS = {"origin": (300.0, -2000.0), "angle": 28.0, "cell": (52.0, 74.0), "box": (-260.0, -2170.0, 2015.0, -935.0),
          "max_slope": 0.075, "share": 0.78}
FORD_NEAR = (430.0, -1890.0)

# Mistwater Shore: the Old Coast Road (waypoints snapped to the cliff tops unless marked fixed)
COAST_ROAD = [(127, -2343, "fixed"), (175, -2318, "fixed"), (196, -2280, "fixed"), (198, -2180, "fixed"),
              (196, -2122, "fixed"), (110, -2114, "fixed"), (62, -2072, "fixed"), (40, -1995, "fixed"),
              (-60, -1950, "fixed"), (-170, -1955, "fixed"),
              (-260, -2020, "fixed"), (-330, -2120, "fixed"), (-450, -2240), (-560, -2330), (-680, -2450),
              (-740, -2600), (-730, -2760), (-660, -2900), (-540, -3000), (-420, -3100), (-360, -3260),
              (-370, -3450), (-430, -3640), (-560, -3800), (-760, -3880), (-960, -3900), (-1100, -3890)]
COAST_ROAD_INLAND_M = 16.0

# The Teeth: extra reef rocks between the T36 blockout rocks (12 in landmarks.json)
TEETH_LINE = [(60.0, -3550.0), (150.0, -3530.0), (235.0, -3555.0)]

FIELD_KEYS = ("path", "beach", "field", "hedge", "rock", "ford")


# ----------------------------------------------------------------------------- small helpers

def mc_to_ue(x, z, h=0.0):
    return [round(x * 100.0, 1), round(z * 100.0, 1), round(h * 100.0, 1)]


def chaikin(pts, rounds=2, fixed_ends=True):
    pts = [tuple(p) for p in pts]
    for _ in range(rounds):
        out = [pts[0]] if fixed_ends else []
        for a, b in zip(pts[:-1], pts[1:]):
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        if fixed_ends:
            out.append(pts[-1])
        pts = out
    return pts


def round_corners(pts, radius, n=8):
    """Polyline with each inner corner replaced by a circular arc (switchback hairpins keep their length)."""
    pts = [np.array(p, float) for p in pts]
    out = [tuple(pts[0])]
    for k in range(1, len(pts) - 1):
        a, b, c = pts[k - 1], pts[k], pts[k + 1]
        u, v = a - b, c - b
        lu, lv = np.linalg.norm(u), np.linalg.norm(v)
        u, v = u / lu, v / lv
        ang = math.acos(float(np.clip(np.dot(u, v), -1, 1)))
        if ang > math.pi - 1e-3:
            out.append(tuple(b))
            continue
        t = min(radius / math.tan(ang / 2), 0.45 * lu, 0.45 * lv)
        p0, p1 = b + u * t, b + v * t
        # quadratic Bezier through the corner as a close stand-in for the arc
        for s in np.linspace(0, 1, n):
            q = (1 - s) ** 2 * p0 + 2 * (1 - s) * s * b + s * s * p1
            out.append(tuple(q))
    out.append(tuple(pts[-1]))
    return out


def densify(pts, step):
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / step)))
        for k in range(1, n + 1):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def bump(t, a, b, soft):
    return smoothstep(t, a - soft, a) * (1.0 - smoothstep(t, b, b + soft))


def in_box(x, z, box, inset=0.0):
    x0, z0, x1, z1 = box
    return (x >= x0 + inset) & (x <= x1 - inset) & (z >= z0 + inset) & (z <= z1 - inset)


def landscape_box(L):
    return (L["x0"], L["z0"], L["x0"] + (L["nx"] - 1) * L["step"], L["z0"] + (L["nz"] - 1) * L["step"])


# ----------------------------------------------------------------------------- regional fields

def prepare_fields(F):
    """At 1 m the 6.25 m lake and river fields show their pixel steps: soften them, in this process only
    (the world bake is not touched). Idempotent."""
    if getattr(F, "_moonharbor_soft", False):
        return
    F.lake_sd = nd.gaussian_filter(F.lake_sd, 1.4).astype(np.float32)
    up = F.river_level > 0.5
    soft = nd.gaussian_filter(F.river_level, 2.0)
    F.river_level = np.where(up, np.maximum(soft, 0.6), F.river_level).astype(np.float32)
    F.river_half = nd.gaussian_filter(F.river_half, 2.0).astype(np.float32)
    F._moonharbor_soft = True



class Region:
    """Fields precomputed once on a 2 m grid over FRAME: the smoothed coastline and chunk masks."""

    def __init__(self, F, noise, log=print):
        t0 = time.time()
        fx, fz, size = FRAME
        n = int(size / REGION_STEP)
        self.n = n
        c = (np.arange(n) + 0.5) * REGION_STEP
        zz, xx = np.meshgrid(fz + c, fx + c, indexing="ij")
        # The atlas coastline is drawn on a 25 m grid: blur its signed distance so shores run in curves.
        sd = F.mid("coast_sd", xx, zz)
        self.sd = nd.gaussian_filter(sd, 18.0 / REGION_STEP).astype(np.float32)
        # Sea-level river channels are narrow: they get a lighter blur, enough to round the 25 m steps.
        sd_fine = nd.gaussian_filter(sd, 7.0 / REGION_STEP)
        rd = F.mid("river_dist", xx, zz)
        self.sd = lerp(sd_fine, self.sd, smoothstep(rd, 40.0, 90.0)).astype(np.float32)
        del sd, sd_fine, rd
        chunks = np.asarray(Image.open(CHUNKS_PNG))
        pi = np.clip(((xx + 12500.0) / 25.0).astype(np.int32), 0, chunks.shape[1] - 1)
        pj = np.clip(((zz + 12500.0) / 25.0).astype(np.int32), 0, chunks.shape[0] - 1)
        self.chunk = chunks[pj, pi]
        del pi, pj, xx, zz

        def soft(mask, sigma_m, lo, hi):
            g = nd.gaussian_filter(mask.astype(np.float32), sigma_m / REGION_STEP)
            return smoothstep(g, lo, hi).astype(np.float32)
        self.m = {
            "M3": soft(self.chunk == 3, 30.0, 0.3, 0.7),
            "M4": soft(self.chunk == 4, 40.0, 0.04, 0.35),   # reaches ~60 m into the sea for the coast work
            "H1": soft(self.chunk == 100, 30.0, 0.2, 0.6),
            "wave": soft(np.isin(self.chunk, list(WAVE_1_0)), 20.0, 0.3, 0.7),
        }
        log(f"[Lyris] regional fields {n} x {n} at {REGION_STEP:.0f} m ({time.time() - t0:.0f}s)")

    def coords(self, x, z):
        fx, fz, _ = FRAME
        return (z - fz) / REGION_STEP - 0.5, (x - fx) / REGION_STEP - 0.5

    def sample(self, arr, x, z, order=1):
        j, i = self.coords(x, z)
        return nd.map_coordinates(arr, [j, i], order=order, mode="nearest")

    def coast(self, noise, x, z):
        """Smoothed signed distance to the sea coast (m, + on land), with a gentle natural wobble."""
        wx = x + 6.0 * noise.fbm(x, z, 90.0, 2, salt=81)
        wz = z + 6.0 * noise.fbm(x + 517.0, z - 291.0, 90.0, 2, salt=82)
        return self.sample(self.sd, wx, wz)

    def mask(self, name, x, z):
        return self.sample(self.m[name], x, z)


# ----------------------------------------------------------------------------- the detail plan

class Detail:
    """Moonharbor's sculpt on top of bake_terrain.terrain(). Precomputes what needs whole-area knowledge
    (field planes, road profiles, rock lists), then apply() works on any batch of points."""

    def __init__(self, F, noise, R, log=print):
        self.F, self.noise, self.R, self.log = F, noise, R, log
        self.rng = np.random.default_rng(bt.SEED + 55)
        prepare_fields(F)
        self._m4_coves()
        self._keep_road()
        self._fields()
        self._ford()
        self._teeth()
        self._skerries()
        self._coast_road()
        self._find_bridges()

    # -- helpers ------------------------------------------------------------------------------
    def ground(self, x, z):
        h, _ = bt.terrain(self.F, self.noise, np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(z, float)))
        return h

    # -- Keep Road ----------------------------------------------------------------------------
    def _keep_road(self):
        pts = densify(round_corners(KEEP_ROAD, 7.0), 2.0)
        self.kr_pts = np.array(pts)
        seg = np.hypot(*np.diff(self.kr_pts, axis=0).T)
        self.kr_s = np.concatenate([[0.0], np.cumsum(seg)])
        self.kr_len = float(self.kr_s[-1])
        y0, y1 = (v - 63.0 for v in KEEP_ROAD_Y)
        # Level for the first 6 m and the last 8 m (the gate threshold), a steady grade between.
        s = self.kr_s
        t = np.clip((s - 6.0) / (self.kr_len - 14.0), 0, 1)
        self.kr_h = (y0 + (y1 - y0) * t).astype(np.float32)
        # Legs between the original waypoints, so each switchback leg cuts its own bench.
        leg_idx = []
        for k, (wx, wz) in enumerate(KEEP_ROAD):
            leg_idx.append(int(np.argmin(np.hypot(self.kr_pts[:, 0] - wx, self.kr_pts[:, 1] - wz))))
        self.kr_legs = [(leg_idx[k], leg_idx[k + 1]) for k in range(len(leg_idx) - 1)]
        x0, z0 = self.kr_pts.min(axis=0) - 45.0
        x1, z1 = self.kr_pts.max(axis=0) + 45.0
        self.kr_box = (x0, z0, x1, z1)
        self.log(f"[Lyris] Keep Road: {self.kr_len:.0f} m, {len(KEEP_ROAD) - 2} switchbacks, "
                 f"grade {100 * (y1 - y0) / (self.kr_len - 14):.1f}%")

    def _road_near(self, x, z, pts, s_arr, h_arr):
        """Distance, arc length and road height at the nearest point of a dense polyline (vectorised by
        nearest vertex, refined on the two segments next to it)."""
        from scipy.spatial import cKDTree
        tree = cKDTree(pts)
        d, k = tree.query(np.stack([x.ravel(), z.ravel()], 1))
        best_d = d.copy()
        best_s = s_arr[k].astype(np.float64)
        best_h = h_arr[k].astype(np.float64)
        for off in (-1, 0):
            a = np.clip(k + off, 0, len(pts) - 2)
            ax, az = pts[a, 0], pts[a, 1]
            bx, bz = pts[a + 1, 0], pts[a + 1, 1]
            dx, dz = bx - ax, bz - az
            ln2 = np.maximum(dx * dx + dz * dz, 1e-9)
            t = np.clip(((x.ravel() - ax) * dx + (z.ravel() - az) * dz) / ln2, 0, 1)
            dd = np.hypot(x.ravel() - ax - t * dx, z.ravel() - az - t * dz)
            closer = dd < best_d
            best_d = np.where(closer, dd, best_d)
            best_s = np.where(closer, s_arr[a] + t * (s_arr[a + 1] - s_arr[a]), best_s)
            best_h = np.where(closer, h_arr[a] + t * (h_arr[a + 1] - h_arr[a]), best_h)
        return best_d.reshape(x.shape), best_s.reshape(x.shape), best_h.reshape(x.shape)

    def keep_road(self, x, z, h, out):
        sel = in_box(x, z, self.kr_box)
        if not sel.any():
            return h
        xs, zs, hs = x[sel], z[sel], h[sel].astype(np.float64)
        path = np.zeros_like(hs)
        near = np.full(hs.shape, 1e9)
        for a, b in self.kr_legs:
            pts = self.kr_pts[a:b + 1]
            d, _s, r = self._road_near(xs, zs, pts, self.kr_s[a:b + 1], self.kr_h[a:b + 1])
            w = 1.0 - smoothstep(d, 34.0, 44.0)
            cut = r - 1.25 * np.maximum(d - 3.2, 0.0)    # cut bank above the road ~51 degrees
            fill = r + 0.9 * np.maximum(d - 3.2, 0.0)    # fill bank below ~42 degrees
            bench = np.clip(hs, cut, fill)
            bench = np.where(d < 3.2, r, bench)
            hs = lerp(hs, bench, w)
            path = np.maximum(path, 1.0 - smoothstep(d, 2.6, 3.6))
            near = np.minimum(near, d)
        h = h.copy()
        h[sel] = hs.astype(np.float32)
        out["path"][sel] = np.maximum(out["path"][sel], path)
        out["_road_near"][sel] = np.minimum(out["_road_near"][sel], near)
        return h

    # -- Wayside Fields -----------------------------------------------------------------------
    def _field_uv(self, x, z):
        ox, oz = FIELDS["origin"]
        a = math.radians(FIELDS["angle"])
        dx, dz = x - ox, z - oz
        u = dx * math.cos(a) + dz * math.sin(a)
        v = -dx * math.sin(a) + dz * math.cos(a)
        u = u + 7.0 * self.noise.fbm(x, z, 260.0, 2, salt=91)
        v = v + 7.0 * self.noise.fbm(x - 333.0, z + 177.0, 260.0, 2, salt=92)
        return u, v

    def _fields(self):
        t0 = time.time()
        x0, z0, x1, z1 = FIELDS["box"]
        step = 4.0
        xs = np.arange(x0, x1, step)
        zs = np.arange(z0, z1, step)
        zz, xx = np.meshgrid(zs, xs, indexing="ij")
        h, masks = bt.terrain(self.F, self.noise, xx, zz)
        u, v = self._field_uv(xx, zz)
        W, H = FIELDS["cell"]
        ci, cj = np.floor(u / W).astype(np.int64), np.floor(v / H).astype(np.int64)
        fu, fv = u / W - ci, v / H - cj
        edge = np.minimum(np.minimum(fu, 1 - fu) * W, np.minimum(fv, 1 - fv) * H)
        rd = self.F.mid("river_dist", xx, zz)
        hw = self.F.mid("river_half", xx, zz)
        lsd = self.F.mid("lake_sd", xx, zz)
        m3 = self.R.mask("M3", xx, zz)
        town = in_box(xx, zz, TOWN_CORE, inset=-40.0)
        key = ci * 100003 + cj
        order = np.argsort(key.ravel(), kind="stable")
        ks = key.ravel()[order]
        bounds = np.flatnonzero(np.diff(ks)) + 1
        self.cells = {}
        for s, e in zip(np.r_[0, bounds], np.r_[bounds, len(ks)]):
            idx = order[s:e]
            i_, j_ = int(ci.ravel()[idx[0]]), int(cj.ravel()[idx[0]])
            inner = idx[edge.ravel()[idx] > 4.0]
            if len(inner) < 40:
                continue
            hh = h.ravel()[inner]
            ok = (hh.min() > 1.2 and hh.max() < 60.0 and (rd.ravel()[idx] > hw.ravel()[idx] + 16.0).all()
                  and (lsd.ravel()[idx] < -12.0).all() and m3.ravel()[inner].min() > 0.55
                  and not town.ravel()[idx].any())
            if not ok:
                continue
            uu, vv = u.ravel()[inner], v.ravel()[inner]
            A = np.stack([np.ones_like(uu), uu - uu.mean(), vv - vv.mean()], 1)
            coef, *_ = np.linalg.lstsq(A, hh, rcond=None)
            slope = math.hypot(coef[1], coef[2])
            resid = float(np.abs(A @ coef - hh).max())
            if slope > FIELDS["max_slope"] or resid > 3.5:
                continue
            if bt.hash01(np.array([i_]), np.array([j_]), 777)[0] > FIELDS["share"]:
                continue
            # Field terraces are flatter than the ground: the slope is taken up by the banks between them.
            self.cells[(i_, j_)] = (float(coef[0]), float(coef[1]) * 0.55, float(coef[2]) * 0.55,
                                    float(uu.mean()), float(vv.mean()))
        self.log(f"[Lyris] Wayside Fields: {len(self.cells)} field terraces of {W:.0f} x {H:.0f} m "
                 f"({len(self.cells) * W * H / 1e4:.0f} ha) ({time.time() - t0:.0f}s)")

    def fields(self, x, z, h, out):
        x0, z0, x1, z1 = FIELDS["box"]
        sel = in_box(x, z, (x0 - 10, z0 - 10, x1 + 10, z1 + 10))
        if not sel.any() or not self.cells:
            return h
        xs, zs = x[sel], z[sel]
        u, v = self._field_uv(xs, zs)
        W, H = FIELDS["cell"]
        ci, cj = np.floor(u / W).astype(np.int64), np.floor(v / H).astype(np.int64)
        fu, fv = u / W - ci, v / H - cj
        eu = np.minimum(fu, 1 - fu) * W
        ev = np.minimum(fv, 1 - fv) * H
        edge = np.minimum(eu, ev)
        plane = np.zeros_like(u)
        active = np.zeros_like(u)
        keys = ci * 100003 + cj
        for k in np.unique(keys):
            m = keys == k
            i_, j_ = int(ci[m][0]), int(cj[m][0])
            c = self.cells.get((i_, j_))
            if c is None:
                continue
            a, bu, bv, uc, vc = c
            plane[m] = a + bu * (u[m] - uc) + bv * (v[m] - vc)
            active[m] = 1.0
        w = active * smoothstep(edge, 1.0, 4.5)
        hs = h[sel]
        hs = lerp(hs, plane, w * 0.94)
        # Hedgerows along some field edges: a low planted bank (the scatter puts bushes and trees on it).
        nb_u = np.where(fu > 0.5, ci + 1, ci)
        nb_v = np.where(fv > 0.5, cj + 1, cj)
        flag_u = bt.hash01(nb_u, cj, 778) < 0.62
        flag_v = bt.hash01(ci, nb_v, 779) < 0.5
        hedge = np.maximum((1 - smoothstep(eu, 0.6, 2.2)) * flag_u, (1 - smoothstep(ev, 0.6, 2.2)) * flag_v)
        hedge = hedge * active   # on the field's own side of the edge
        hs = hs + 0.55 * hedge
        h = h.copy()
        h[sel] = hs
        out["field"][sel] = np.maximum(out["field"][sel], w * (hedge < 0.2))
        out["hedge"][sel] = np.maximum(out["hedge"][sel], hedge)
        return h

    # -- the ford -------------------------------------------------------------------------------
    def _ford(self):
        c = np.arange(-70.0, 70.0, 1.0)
        zz, xx = np.meshgrid(FORD_NEAR[1] + c, FORD_NEAR[0] + c, indexing="ij")
        rd = self.F.mid("river_dist", xx, zz)
        k = np.argmin(rd)
        fx, fz = float(xx.flat[k]), float(zz.flat[k])
        near = rd < 4.0
        pts = np.stack([xx[near] - fx, zz[near] - fz], 1)
        pts = pts[np.hypot(pts[:, 0], pts[:, 1]) < 45.0]
        _u, _s, vt = np.linalg.svd(pts - pts.mean(0), full_matrices=False)
        tx, tz = vt[0]
        self.ford = {"x": fx, "z": fz, "along": (float(tx), float(tz)),
                     "half": float(self.F.mid("river_half", np.array([fx]), np.array([fz]))[0]),
                     "level": float(self.F.mid("river_level", np.array([fx]), np.array([fz]), order=0)[0])}
        self.log(f"[Lyris] ford at ({fx:.0f}, {fz:.0f}), river {2 * self.ford['half']:.0f} m wide, "
                 f"water {self.ford['level']:.1f} m")

    def ford_apply(self, x, z, h, out):
        f = self.ford
        reach = f["half"] + 45.0
        sel = (np.abs(x - f["x"]) < reach) & (np.abs(z - f["z"]) < reach)
        if not sel.any():
            return h
        xs, zs = x[sel] - f["x"], z[sel] - f["z"]
        tx, tz = f["along"]
        b = xs * tx + zs * tz          # along the river
        a = -xs * tz + zs * tx         # across the river (the crossing)
        target = f["level"] - 0.35 + np.maximum(np.abs(a) - (f["half"] - 3.0), 0.0) * 0.11
        w = (1 - smoothstep(np.abs(b), 5.0, 10.0)) * (1 - smoothstep(np.abs(a), f["half"] + 24.0, f["half"] + 40.0))
        h = h.copy()
        h[sel] = lerp(h[sel], target, w)
        out["ford"][sel] = np.maximum(out["ford"][sel], w * (np.abs(a) < f["half"] + 12.0))
        out["path"][sel] = np.maximum(out["path"][sel], w * (1 - smoothstep(np.abs(b), 2.0, 3.5)))
        return h

    # -- the Teeth ------------------------------------------------------------------------------
    def _teeth(self):
        rng = np.random.default_rng(bt.SEED + 12)
        pts = densify(TEETH_LINE, 4.0)
        rocks = []
        for k in range(16):
            px, pz = pts[int(rng.integers(0, len(pts)))]
            px += rng.uniform(-14, 14)
            pz += rng.uniform(-22, 22)
            rocks.append((px, pz, rng.uniform(4.0, 11.0), rng.uniform(0.8, 5.5), int(rng.integers(0, 7))))
        self.teeth_rocks = rocks

    def teeth(self, x, z, h, out):
        sel = (x > 0) & (x < 300) & (z > -3640) & (z < -3460)
        if not sel.any():
            return h
        xs, zs, hs = x[sel], z[sel], h[sel]
        d, _s, _side, _ = bt._polyline(xs, zs, TEETH_LINE)
        reef = -3.0 - 0.07 * d + 0.9 * self.noise.ridged(xs, zs, 30.0, 2, salt=121)
        hs = np.maximum(hs, np.where(d < 70.0, reef, hs))
        rockw = np.zeros_like(hs)
        for k, (px, pz, r, top, salt) in enumerate(self.teeth_rocks):
            m = (np.abs(xs - px) < r * 1.6) & (np.abs(zs - pz) < r * 1.6)
            if not m.any():
                continue
            wob = bt._wobble(self.noise, xs[m], zs[m], px, pz, 25.0, 0.25, 120 + salt)
            t = np.hypot(xs[m] - px, zs[m] - pz) / (r * wob)
            jag = 0.75 + 0.5 * self.noise.ridged(xs[m] * 1.7, zs[m] * 1.7, 9.0, 2, salt=122 + salt)
            prof = (top + 3.0) * np.clip(1.0 - t, 0, 1) ** 0.6 * jag - 3.0
            hs[m] = np.maximum(hs[m], prof)
            rockw[m] = np.maximum(rockw[m], (t < 1.0) * 1.0)
        h = h.copy()
        h[sel] = hs
        out["rock"][sel] = np.maximum(out["rock"][sel], np.maximum(rockw, (d < 60) * 0.6))
        return h

    # -- the Lampwick Skerries ------------------------------------------------------------------
    def _skerries(self):
        chain = next(c for c in bt.ISLANDS if c["id"] == "A")
        rng = np.random.default_rng(bt.SEED + 1)
        self.coves, self.tors = [], []
        for k, islet in enumerate(chain["islets"]):
            cx, cz, rx, rz, rot = islet[:5]
            for c in range(2):
                ang = rng.uniform(0, 2 * np.pi) if c == 0 else self.coves[-1][4] + rng.uniform(2.2, 4.0)
                # walk out from the centre to the real (noise-warped) coastline
                ray = np.linspace(0, max(rx, rz) * 1.6, 120)
                gx, gz = cx + np.cos(ang) * ray, cz + np.sin(ang) * ray
                hh = self.ground(gx, gz)
                land = np.nonzero(hh > 0.3)[0]
                if not len(land):
                    continue
                edge = ray[land[-1]]
                rc = 0.32 * min(rx, rz) + 6.0
                ex, ez = cx + np.cos(ang) * (edge - rc * 0.35), cz + np.sin(ang) * (edge - rc * 0.35)
                self.coves.append((ex, ez, rc, k, ang))
            for t in range(3):
                for _ in range(20):
                    a, rr = rng.uniform(0, 2 * np.pi), rng.uniform(0.3, 0.6)
                    px, pz = cx + np.cos(a) * rx * rr, cz + np.sin(a) * rz * rr
                    if math.hypot(px - cx, pz - cz) > 12.0 and all(math.hypot(px - q[0], pz - q[1]) > rc + 6 for q in self.coves if q[3] == k):
                        self.tors.append((px, pz, rng.uniform(4.5, 8.0), rng.uniform(2.5, 5.0), t))
                        break
        self.log(f"[Lyris] Lampwick Skerries: {len(self.coves)} coves, {len(self.tors)} tors")

    def skerries(self, x, z, h, out):
        sel = (x < -1600) & (x > -3400) & (z > -4800) & (z < -4300)
        if not sel.any():
            return h
        xs, zs, hs = x[sel], z[sel], h[sel]
        beach, rock = out["beach"][sel], out["rock"][sel]
        for (px, pz, rc, _k, _a) in self.coves:
            m = (np.abs(xs - px) < rc * 1.5) & (np.abs(zs - pz) < rc * 1.5)
            if not m.any():
                continue
            wob = bt._wobble(self.noise, xs[m], zs[m], px, pz, 18.0, 0.18, 130)
            t = np.hypot(xs[m] - px, zs[m] - pz) / (rc * wob)
            bowl = -1.4 + 2.6 * t * t
            w = 1 - smoothstep(t, 0.95, 1.35)
            new = lerp(hs[m], np.minimum(hs[m], bowl), w)
            beach[m] = np.maximum(beach[m], w * (new > -0.6) * (new < 1.6))
            hs[m] = new
        for (px, pz, r, top, salt) in self.tors:
            m = (np.abs(xs - px) < r * 1.6) & (np.abs(zs - pz) < r * 1.6)
            if not m.any():
                continue
            wob = bt._wobble(self.noise, xs[m], zs[m], px, pz, 14.0, 0.25, 140 + salt)
            t = np.hypot(xs[m] - px, zs[m] - pz) / (r * wob)
            tor = top * np.clip(1 - t * t, 0, 1) ** 0.7 * (0.8 + 0.4 * self.noise.ridged(xs[m], zs[m], 7.0, 2, salt=141))
            hs[m] = hs[m] + tor * (hs[m] > 0.5)
            rock[m] = np.maximum(rock[m], (t < 0.9) * 1.0)
        h = h.copy()
        h[sel] = hs
        out["beach"][sel] = beach
        out["rock"][sel] = rock
        return h

    # -- the Old Coast Road ---------------------------------------------------------------------
    def _coast_road(self):
        pts, fixed = [], []
        for wp in COAST_ROAD:
            x, z = float(wp[0]), float(wp[1])
            if len(wp) < 3:
                c = np.arange(-150.0, 151.0, 2.0)
                zz, xx = np.meshgrid(z + c, x + c, indexing="ij")
                sd = self.coast_eff(xx, zz)
                cost = np.abs(sd - COAST_ROAD_INLAND_M) + 0.02 * np.hypot(xx - x, zz - z)
                k = int(np.argmin(cost))
                x, z = float(xx.flat[k]), float(zz.flat[k])
            pts.append((x, z))
            fixed.append(len(wp) > 2)
        last_fixed = max(k for k, f in enumerate(fixed) if f)
        head = densify(chaikin(pts[:last_fixed + 1], rounds=3), 3.0)
        tail = densify(chaikin(pts[last_fixed:], rounds=3), 3.0)
        # Hug the cliff tops: every point of the free part slides along the coast's normal to COAST_ROAD_INLAND_M
        # from the shore, then the line is smoothed so it never zigzags.
        tail = np.array(tail)
        e = 3.0
        for _ in range(4):
            x, z = tail[:, 0], tail[:, 1]
            sd = self.coast_eff(x, z)
            gx = (self.coast_eff(x + e, z) - self.coast_eff(x - e, z)) / (2 * e)
            gz = (self.coast_eff(x, z + e) - self.coast_eff(x, z - e)) / (2 * e)
            g = np.maximum(np.hypot(gx, gz), 0.3)
            move = np.clip((COAST_ROAD_INLAND_M - sd) / g, -25.0, 25.0)
            ramp = np.clip(np.arange(len(tail)) / 25.0, 0, 1)          # leave the joint with the fixed part alone
            tail = tail + np.stack([gx / g * move * ramp, gz / g * move * ramp], 1)
            sm = np.stack([nd.uniform_filter1d(tail[:, k], 5, mode="nearest") for k in range(2)], 1)
            sm[0] = tail[0]
            tail = sm
        # Round each cove on its landward side, never across its mouth.
        for (cx, cz, r) in self.m4_coves:
            e = 4.0
            gx = float(self.R.coast(self.noise, np.array([cx + e]), np.array([cz]))[0] - self.R.coast(self.noise, np.array([cx - e]), np.array([cz]))[0])
            gz = float(self.R.coast(self.noise, np.array([cx]), np.array([cz + e]))[0] - self.R.coast(self.noise, np.array([cx]), np.array([cz - e]))[0])
            g = math.hypot(gx, gz) or 1.0
            nx, nz = gx / g, gz / g
            keep_r = r * 1.25 + 14.0
            vx, vz = tail[:, 0] - cx, tail[:, 1] - cz
            dist = np.hypot(vx, vz)
            near = dist < keep_r
            if not near.any():
                continue
            dot = vx * nx + vz * nz
            sea_side = near & (dot < 0)
            vx = np.where(sea_side, vx - 2 * dot * nx, vx)
            vz = np.where(sea_side, vz - 2 * dot * nz, vz)
            dist = np.maximum(np.hypot(vx, vz), 1e-3)
            tail[near, 0] = cx + vx[near] / dist[near] * keep_r
            tail[near, 1] = cz + vz[near] / dist[near] * keep_r
        tail[1:-1] = (tail[:-2] + 2 * tail[1:-1] + tail[2:]) / 4.0
        pts = head + [tuple(p) for p in tail[1:]]
        self.cr_pts = np.array(densify(pts, 3.0))
        seg = np.hypot(*np.diff(self.cr_pts, axis=0).T)
        self.cr_s = np.concatenate([[0.0], np.cumsum(seg)])
        # Bridges are found once the whole plan exists, from the finished ground (_find_bridges).
        self.bridges = []
        self.cr_wet = np.zeros(len(self.cr_pts), bool)
        self.cr_h = np.zeros(len(self.cr_pts), np.float32)
        x0, z0 = self.cr_pts.min(axis=0) - 30.0
        x1, z1 = self.cr_pts.max(axis=0) + 30.0
        self.cr_box = (x0, z0, x1, z1)

    def _find_bridges(self):
        """Bridge spans where the finished ground under the Old Coast Road is water (the Mistwater's mouth)."""
        px, pz = self.cr_pts[:, 0], self.cr_pts[:, 1]
        h, _m, _o = mh_terrain(self.F, self.noise, self, px[None, :], pz[None, :])
        h = h[0]
        wet = h < 0.0
        lab, n = nd.label(wet)
        for k in range(1, n + 1):
            idx = np.nonzero(lab == k)[0]
            a, b = max(idx[0] - 2, 0), min(idx[-1] + 2, len(px) - 1)
            span = float(self.cr_s[b] - self.cr_s[a])
            if span < 4.0:
                continue
            deck = max(float(h[a]), float(h[b]), 2.2) + 0.5
            self.bridges.append({"name": "Mistwater Bridge" if not self.bridges else f"Coast Road span {len(self.bridges) + 1}",
                                 "from_mc": [round(float(px[a]), 1), round(float(pz[a]), 1)],
                                 "to_mc": [round(float(px[b]), 1), round(float(pz[b]), 1)],
                                 "deck_m": round(deck, 2), "length_m": round(span, 1), "width_m": 4.0})
        self.cr_wet = wet
        self.log(f"[Lyris] Old Coast Road: {self.cr_s[-1] / 1000:.2f} km, {len(self.bridges)} bridge span(s): "
                 + ", ".join(f"{b['name']} {b['length_m']:.0f} m at ({b['from_mc'][0]:.0f}, {b['from_mc'][1]:.0f})"
                             for b in self.bridges))

    def _m4_coves(self):
        """Horseshoe coves spread along Mistwater Shore's coast (not in the bay's beach lobe or the town)."""
        R = self.R
        coast = (np.abs(R.sd) < 2.0) & (R.m["M4"] > 0.6)
        j, i = np.nonzero(coast)
        fx, fz, _ = FRAME
        xs = fx + (i + 0.5) * REGION_STEP
        zs = fz + (j + 0.5) * REGION_STEP
        lx, lz, ax, az = LOBE
        ok = (np.hypot((xs - lx) / ax, (zs - lz) / az) > 1.5) & ~in_box(xs, zs, TOWN_CORE, inset=-120.0)
        xs, zs = xs[ok], zs[ok]
        rng = np.random.default_rng(bt.SEED + 4)
        order = rng.permutation(len(xs))
        self.m4_coves = []
        for k in order:
            px, pz = float(xs[k]), float(zs[k])
            if all(math.hypot(px - q[0], pz - q[1]) > 200.0 for q in self.m4_coves):
                r = float(rng.uniform(30.0, 52.0))
                # Centre a little inland, so the horseshoe opens to the sea.
                e = 4.0
                gx = float(R.sample(R.sd, np.array([px + e]), np.array([pz]))[0] - R.sample(R.sd, np.array([px - e]), np.array([pz]))[0])
                gz = float(R.sample(R.sd, np.array([px]), np.array([pz + e]))[0] - R.sample(R.sd, np.array([px]), np.array([pz - e]))[0])
                g = math.hypot(gx, gz) or 1.0
                self.m4_coves.append((px + gx / g * r * 0.5, pz + gz / g * r * 0.5, r))
            if len(self.m4_coves) >= 14:
                break
        self.log(f"[Lyris] Mistwater Shore: {len(self.m4_coves)} coves")

    def cove_dist(self, x, z):
        """Distance (m) from the nearest Mistwater cove's rim (negative inside), and that cove's t = r / radius."""
        best = np.full(np.shape(x), 1e9, np.float32)
        t_best = np.full(np.shape(x), 9.0, np.float32)
        for (cx, cz, r) in self.m4_coves:
            m = (np.abs(x - cx) < r * 2.5) & (np.abs(z - cz) < r * 2.5)
            if not np.any(m):
                continue
            wob = bt._wobble(self.noise, x[m], z[m], cx, cz, 30.0, 0.16, 75)
            d = np.hypot(x[m] - cx, z[m] - cz) / wob
            t = d / r
            closer = (d - r) < best[m]
            best[m] = np.where(closer, d - r, best[m])
            t_best[m] = np.where(closer, t, t_best[m])
        return best, t_best

    def coast_eff(self, x, z):
        """The coastline after the coves: the road keeps to dry ground round each cove (with room to spare)."""
        sd = self.R.coast(self.noise, x, z)
        d, _t = self.cove_dist(x, z)
        return np.minimum(sd, np.where(d < 1e8, d - 10.0, sd))

    def coast_road(self, x, z, h, out):
        sel = in_box(x, z, self.cr_box)
        if not sel.any():
            return h
        xs, zs = x[sel], z[sel]
        d, s, _rh = self._road_near(xs, zs, self.cr_pts, self.cr_s, self.cr_h)
        dry = np.interp(s, self.cr_s, (~self.cr_wet).astype(np.float32)) > 0.5
        # A trodden path on the cliff tops: painted, the ground itself left as the cliffs made it.
        p = (1.0 - smoothstep(d, 1.4, 2.4)) * dry
        h = h.copy()
        out["path"][sel] = np.maximum(out["path"][sel], p)
        # Bridge abutments: small level pads at each end of a span.
        for b in self.bridges:
            for end in ("from_mc", "to_mc"):
                bx, bz = b[end]
                m = (np.abs(x - bx) < 12) & (np.abs(z - bz) < 12)
                if m.any():
                    r = np.hypot(x[m] - bx, z[m] - bz)
                    h[m] = lerp(h[m], np.float32(b["deck_m"] - 0.4), 1 - smoothstep(r, 3.5, 8.0))
        return h

    # -- the big shapes -------------------------------------------------------------------------
    def coast_snap(self, x, z, h, sd, keep, out):
        isl = bt.island_footprint(x, z).astype(np.float32)
        rd = self.F.mid("river_dist", x, z)
        lsd = self.F.mid("lake_sd", x, z)
        # Upland rivers carve their own beds; sea-level channels follow the (lightly) smoothed coast.
        upland = self.F.mid("river_level", x, z, order=0) > 0.5
        w = (1 - keep) * (1 - isl) * np.where(upland, smoothstep(rd, 30.0, 60.0), 1.0) * smoothstep(-lsd, 10.0, 30.0)
        lift = np.maximum(h, 0.2 + 0.06 * sd)
        sink = np.minimum(h, -0.35 + 0.08 * sd)
        target = np.where(sd >= 0, lerp(h, lift, 1 - smoothstep(sd, 30.0, 45.0)),
                          lerp(h, sink, 1 - smoothstep(-sd, 35.0, 50.0)))
        return lerp(h, target, w)

    def bay(self, x, z, h, sd, keep_town, out):
        h1 = self.R.mask("H1", x, z)
        if not np.any(h1 > 0):
            return h
        # South lobe: a clean sand beach and a shallow shelf before the terraces.
        lx, lz, ax, az = LOBE
        lobe = (1 - smoothstep(np.hypot((x - lx) / ax, (z - lz) / az), 0.85, 1.25)) * (1 - keep_town)
        lobe = lobe * (x < 70.0)
        beach_land = 0.25 + 0.045 * np.maximum(sd, 0)
        shelf = -0.3 + 0.032 * np.minimum(sd, 0)
        target = np.where(sd >= 0, beach_land, np.maximum(shelf, np.minimum(h, -2.4)))
        wb = lobe * np.where(sd >= 0, 1 - smoothstep(sd, 26.0, 52.0), 1 - smoothstep(-sd, 60.0, 85.0))
        h = lerp(h, target, wb)
        out["beach"] = np.maximum(out["beach"], lobe * (sd > -3) * (1 - smoothstep(sd, 24.0, 34.0)))
        # Aurenhal's terraces down the bowl walls.
        depth = -h
        lv = np.array(TERRACE_LEVELS)
        k = np.searchsorted(lv, depth, side="right") - 1
        ok = (k >= 0) & (k < len(lv) - 1)
        kk = np.clip(k, 0, len(lv) - 2)
        L0, L1 = lv[kk], lv[kk + 1]
        q = np.clip((depth - L0) / (L1 - L0), 0, 1)
        riser = smoothstep(q, 0.8, 0.97)
        d_t = L0 + (L1 - L0) * riser + 0.7 * q * (1 - riser)        # treads lean a little outward
        intact = smoothstep(self.noise.fbm(x, z, 110.0, 3, salt=101), -0.28, 0.08)
        parapet = 1.2 * bump(q, 0.62, 0.7, 0.03) * intact
        terr = -d_t + parapet
        cx, cz = BAY_CENTRE
        r = np.hypot(x - cx, z - cz)
        theta = np.arctan2(z - cz, x - cx)
        sector = (theta * 9.0 / (2 * np.pi)) % 1.0
        arc = np.abs(sector - 0.5) * (2 * np.pi / 9.0) * r
        street = 1 - smoothstep(arc, 3.5, 6.5)
        pit_r = np.hypot(x - ORUTH[0], z - ORUTH[1])
        wt = (h1 * ok * smoothstep(depth, 1.6, 2.6) * (1 - smoothstep(depth, 88.0, 94.0)) * smoothstep(pit_r, 70.0, 110.0)
              * (1 - lobe * 0.85) * (1 - keep_town))
        wt = wt * (0.3 + 0.7 * intact) * (1 - street * 0.9)
        h = lerp(h, terr, wt)
        out["rock"] = np.maximum(out["rock"], wt * bump(q, 0.78, 0.98, 0.04))
        # Oruth's pit: a flat floor at exactly Y -40.
        pit = ORUTH[2] + (h - ORUTH[2]) * smoothstep(pit_r, 24.0, 58.0)
        h = np.where(pit_r < 70.0, np.minimum(h, pit), h)
        return h

    def keep_cliff(self, x, z, h, sd, keep_town, out):
        sel = (z > CLIFF_Z[0] - 50) & (z < CLIFF_Z[1] + 50) & (x > 150) & (x < 640) & (sd > -30) & (sd < 190)
        if not sel.any():
            return h
        xs, zs, hs, sds = x[sel], z[sel], h[sel], sd[sel]
        cx, cz = BAY_CENTRE
        nx, nz = xs - cx, zs - cz
        nn = np.hypot(nx, nz)
        nx, nz = nx / nn, nz / nn
        S = 170.0
        shifted = self.ground(xs + S * nx, zs + S * nz).astype(np.float32)
        wz = smoothstep(zs, CLIFF_Z[0] - 40, CLIFF_Z[0] + 20) * (1 - smoothstep(zs, CLIFF_Z[1] - 30, CLIFF_Z[1] + 30))
        w = wz * (1 - keep_town[sel])
        top = lerp(shifted, hs, smoothstep(sds, S * 0.55, S * 1.45))
        foot = 2.0 + 2.5 * self.noise.fbm(xs, zs, 28.0, 2, salt=151)
        face = smoothstep(sds, foot, foot + 7.0)
        tiers = np.floor(face * 3.0) / 3.0 + smoothstep(face * 3.0 % 1.0, 0.55, 1.0) / 3.0
        face = lerp(face, tiers, 0.55)
        land = np.maximum(hs, top * face)
        under = np.minimum(hs, -3.0 + 0.45 * sds)
        target = np.where(sds >= 0, land, lerp(under, hs, smoothstep(-sds, 18.0, 30.0)))
        h = h.copy()
        h[sel] = lerp(hs, target, w)
        tmp = out["rock"][sel]
        out["rock"][sel] = np.maximum(tmp, w * (sds > -6) * (1 - smoothstep(sds, foot + 6.0, foot + 9.0)))
        return h

    def waystone(self, x, z, h, out):
        wx, wz, wy = WAYSTONE
        r = np.hypot(x - wx, z - wz)
        sel = r < 160.0
        if not sel.any():
            return h
        lvl = wy - 63.0
        h = h.copy()
        h[sel] = lvl + (h[sel] - lvl) * smoothstep(r[sel], 30.0, 150.0)
        return h

    def mistwater_coast(self, x, z, h, sd, keep, out):
        m4 = self.R.mask("M4", x, z) * (1 - keep)
        if not np.any(m4 > 0):
            return h
        lx, lz, ax, az = LOBE
        m4 = m4 * smoothstep(np.hypot((x - lx) / ax, (z - lz) / az), 1.1, 1.5)
        band = 1 - smoothstep(np.abs(sd), 60.0, 85.0)
        # Low sea cliffs: a near-vertical face with a ledge or two, a flat grassy top, a rocky foot.
        Hc = 7.0 + 9.0 * (0.5 + 0.5 * self.noise.fbm(x, z, 320.0, 2, salt=72))
        foot = 1.5 + 2.5 * self.noise.fbm(x, z, 24.0, 2, salt=73)
        face = smoothstep(sd, foot, foot + 4.0)
        face = lerp(face, np.floor(face * 3.0) / 3.0 + smoothstep(face * 3.0 % 1.0, 0.6, 1.0) / 3.0, 0.4)
        land = lerp(np.maximum(h, Hc * face), h, smoothstep(sd, 40.0, 75.0))
        under = lerp(np.minimum(h, -1.5 + 0.35 * sd), h, smoothstep(-sd, 22.0, 40.0))
        cliff_t = np.where(sd >= 0, land, under)
        h = lerp(h, cliff_t, m4 * band)
        # Coves: a horseshoe of cliffs round a pocket beach of sand, open to the sea.
        dc, tc = self.cove_dist(x, z)
        cove_t = -2.4 + 3.6 * smoothstep(tc, 0.3, 1.0)
        wc = m4 * (1 - smoothstep(tc, 0.92, 1.3))
        h = lerp(h, np.minimum(h, cove_t), wc)
        out["beach"] = np.maximum(out["beach"], wc * (h > -0.8) * (tc < 1.05))
        out["rock"] = np.maximum(out["rock"], m4 * (1 - wc) * (sd > -8) * (1 - smoothstep(sd, foot + 4.0, foot + 7.0)))
        return h

    # -- everything, in order -------------------------------------------------------------------
    def apply(self, x, z, h, masks):
        out = {k: np.zeros(np.shape(x), np.float32) for k in FIELD_KEYS}
        out["_road_near"] = np.full(np.shape(x), 1e9, np.float32)
        h0 = h.copy()
        R = self.R
        sd = R.coast(self.noise, x, z)
        x0, z0, x1, z1 = TOWN_CORE
        town = (1 - smoothstep(np.hypot(np.maximum(np.maximum(x0 - x, x - x1), 0),
                                        np.maximum(np.maximum(z0 - z, z - z1), 0)), 0.0, 60.0)).astype(np.float32)
        keep_land = np.maximum(town, bt.canon_keep(x, z) * in_box(x, z, (1300, -4100, 1900, -2900)))
        h = self.coast_snap(x, z, h, sd, keep_land, out)
        h = self.bay(x, z, h, sd, town, out)
        h = self.mistwater_coast(x, z, h, sd, np.maximum(town, keep_land), out)
        h = self.keep_cliff(x, z, h, sd, town, out)
        h = self.waystone(x, z, h, out)
        h = self.fields(x, z, h, out)
        h = self.ford_apply(x, z, h, out)
        h = self.teeth(x, z, h, out)
        h = self.skerries(x, z, h, out)
        h = self.coast_road(x, z, h, out)
        h = self.keep_road(x, z, h, out)
        # Canon: the town core keeps the world bake's ground (except the Keep Road's bench), then the pads.
        road = 1 - smoothstep(out["_road_near"], 36.0, 46.0)
        restore = town * (1 - road)
        h = lerp(h, h0, restore)
        h = bt.canon_pads(x, z, h)
        h = np.clip(h, bt.H_MIN + 1.0, bt.H_MIN + bt.H_SPAN - 1.0).astype(np.float32)
        for k in ("path", "beach", "field", "hedge", "rock", "ford"):
            out[k] = out[k] * (1 - restore * (k not in ("path",)))
        # Paint: paths, beaches and the ford in sand (the material turns sand on land toward the path
        # colour), cliffs and reef in rock, fields and paths free of forest.
        masks = dict(masks)
        masks["w_sand"] = np.maximum.reduce([masks["w_sand"], out["path"] * 0.75, out["beach"], out["ford"] * 0.8])
        masks["w_rock"] = np.maximum(masks["w_rock"], out["rock"] * 0.8)
        masks["no_forest"] = np.maximum.reduce([masks["no_forest"], out["field"], out["path"], out["beach"]])
        masks["w_grass"] = np.maximum(masks["w_grass"], out["field"] * 0.6)
        masks["sea"] = (h < -0.4).astype(np.float32)
        masks["beach"] = np.maximum(masks["beach"], out["beach"])
        return h, masks, out


def mh_terrain(F, noise, D, x, z):
    h, masks = bt.terrain(F, noise, x, z)
    return D.apply(x, z, h, masks)


# ----------------------------------------------------------------------------- baking

def bake_landscape(F, noise, D, L, step, log):
    """Heights (float32), 8 weights (uint8), water level (float32, NaN for none) and extras for one landscape."""
    nx = int(round((L["nx"] - 1) * L["step"] / step)) + 1
    nz = int(round((L["nz"] - 1) * L["step"] / step)) + 1
    xs = L["x0"] + np.arange(nx) * step
    zs_all = L["z0"] + np.arange(nz) * step
    H = np.zeros((nz, nx), np.float32)
    WAT = np.full((nz, nx), np.nan, np.float32)
    WTS = np.zeros((len(bt.LAYERS), nz, nx), np.uint8)
    EXT = np.zeros((4, nz, nx), np.uint8)   # field, hedge, path, beach
    band = max(16, int(600000 // nx))
    t0 = time.time()
    for r0 in range(0, nz, band):
        r1 = min(r0 + band, nz)
        zs = np.concatenate([[zs_all[r0] - step], zs_all[r0:r1], [zs_all[r1 - 1] + step]])
        zz, xx = np.meshgrid(zs, np.concatenate([[xs[0] - step], xs, [xs[-1] + step]]), indexing="ij")
        h, masks, out = mh_terrain(F, noise, D, xx, zz)
        wts, _slope = bt.weights(h, masks, noise, xx, zz, step)
        c = (slice(1, -1), slice(1, -1))
        H[r0:r1] = h[c]
        wl = masks["water"][c]
        WAT[r0:r1] = np.where(wl > h[c], wl, np.nan)
        for k, arr in enumerate(bt.to_u8_weights({n: v[c] for n, v in wts.items()}).values()):
            WTS[k, r0:r1] = arr
        for k, key in enumerate(("field", "hedge", "path", "beach")):
            EXT[k, r0:r1] = (np.clip(out[key][c], 0, 1) * 255).astype(np.uint8)
        if (r0 // band) % 4 == 0 or r1 == nz:
            log(f"[Lyris] {L['name']}: rows {r1}/{nz}  ({time.time() - t0:.0f}s)")
    return {"h": H, "water": WAT, "w": WTS, "ext": EXT, "x0": L["x0"], "z0": L["z0"], "step": step}


def bake_backdrop(F, noise, log):
    t0 = time.time()
    n = int(bt.WORLD_SIZE / BACKDROP_STEP) + 1
    c = bt.WORLD_MIN + np.arange(n) * BACKDROP_STEP
    H = np.zeros((n, n), np.float32)
    COL = np.zeros((n, n, 3), np.float32)
    WTS = np.zeros((len(bt.LAYERS), n, n), np.uint8)
    WAT = np.full((n, n), np.nan, np.float32)
    band = 100
    for r0 in range(0, n, band):
        r1 = min(r0 + band, n)
        zz, xx = np.meshgrid(c[max(r0 - 1, 0):min(r1 + 1, n)], c, indexing="ij")
        h, masks = bt.terrain(F, noise, xx, zz)
        wts, _ = bt.weights(h, masks, noise, xx, zz, BACKDROP_STEP)
        off = 1 if r0 > 0 else 0
        sl = slice(off, off + (r1 - r0))
        H[r0:r1] = h[sl]
        wl = masks["water"][sl]
        WAT[r0:r1] = np.where((wl > h[sl]) & (wl > 0.3), wl, np.nan)   # lakes and upland rivers (sea: NaN)
        col = sum(wts[name][sl][..., None] * bt.hex_rgb(bt.PREVIEW_COLOURS[name]) for name in bt.LAYERS)
        COL[r0:r1] = col
        for k, arr in enumerate(bt.to_u8_weights({nm: v[sl] for nm, v in wts.items()}).values()):
            WTS[k, r0:r1] = arr
    log(f"[Lyris] backdrop {n} x {n} at {BACKDROP_STEP:.0f} m ({time.time() - t0:.0f}s)")
    return {"h": H, "col": COL, "w": WTS, "water": WAT, "x0": bt.WORLD_MIN, "z0": bt.WORLD_MIN, "step": BACKDROP_STEP}


def backdrop_probes(B):
    """Three high spots whose mirror images (in X or in Z) are much lower: the editor traces them to check
    that the imported backdrop is not mirrored. [x, z, ground m] in MC metres."""
    def at(x, z):
        return float(nd.map_coordinates(B["h"], [[(z - B["z0"]) / B["step"]], [(x - B["x0"]) / B["step"]]], order=1)[0])
    out = []
    for x, z in ((2112.0, -5363.0), (-5650.0, 3975.0), (4150.0, 5050.0), (-2300.0, 0.0), (-3900.0, -2000.0)):
        h = at(x, z)
        if min(h - at(-x, z), h - at(x, -z), h - at(-x, -z)) > 25.0:
            out.append([x, z, round(h, 1)])
    return out[:3]


def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def write_backdrop_glb(B, path, holes):
    """The backdrop as a glTF binary (metres, Y up; UE imports X east, Y south via -Z), vertex colours
    linear, a hole where the landscapes are."""
    h = B["h"].copy()
    n = h.shape[0]
    c = B["x0"] + np.arange(n) * B["step"]
    zz, xx = np.meshgrid(c, c, indexing="ij")
    under = np.zeros_like(h, bool)
    drop = np.zeros_like(h, bool)
    for box in holes:
        under |= in_box(xx, zz, box)
        drop |= in_box(xx, zz, box, inset=BACKDROP_HOLE_INSET)
    h[under] -= BACKDROP_SINK
    gy, gx = np.gradient(h, B["step"])
    nrm = np.stack([-gx, np.ones_like(h), -gy], -1)   # glTF: x east, y up, z = MC Z (south)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    # Same convention as lyris_build_world's sea mesh: UE (x, y, z) -> glTF (x, z, y). Swapping two axes is
    # the right- to left-handed change, so nothing should be mirrored; the editor script still checks it by
    # tracing three probe points and flips the actor's scale if the importer did something else.
    pos = np.stack([xx, h, zz], -1).astype(np.float32).reshape(-1, 3)
    nrm = nrm.astype(np.float32).reshape(-1, 3)
    col = srgb_to_linear(np.clip(B["col"], 0, 1)).reshape(-1, 3)
    col4 = np.concatenate([col, np.ones((len(col), 1))], 1)
    col_u8 = (np.clip(col4, 0, 1) * 255).round().astype(np.uint8)
    ii, jj = np.meshgrid(np.arange(n - 1), np.arange(n - 1), indexing="ij")
    a = (ii * n + jj).ravel()
    keep = ~(drop[:-1, :-1] & drop[1:, :-1] & drop[:-1, 1:] & drop[1:, 1:]).ravel()
    a = a[keep]
    # Two triangles per cell, wound counter-clockwise seen from above in glTF's right-handed frame.
    tris = np.stack([a, a + n, a + 1, a + 1, a + n, a + n + 1], 1).astype(np.uint32).ravel()
    blobs = [pos.tobytes(), nrm.tobytes(), col_u8.tobytes(), tris.tobytes()]
    views, offset = [], 0
    for i, data in enumerate(blobs):
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": 34963 if i == 3 else 34962})
        offset += len(data)
        offset += (-offset) % 4
    doc = {"asset": {"version": "2.0", "generator": "Lyris bake_moonharbor.py"},
           "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": "SM_MoonharborBackdrop", "mesh": 0}],
           "meshes": [{"name": "SM_MoonharborBackdrop", "primitives": [{
               "attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2}, "indices": 3, "material": 0}]}],
           "materials": [{"name": "M_Backdrop", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.95}}],
           "accessors": [
               {"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3",
                "min": pos.min(0).tolist(), "max": pos.max(0).tolist()},
               {"bufferView": 1, "componentType": 5126, "count": len(nrm), "type": "VEC3"},
               {"bufferView": 2, "componentType": 5121, "normalized": True, "count": len(col_u8), "type": "VEC4"},
               {"bufferView": 3, "componentType": 5125, "count": len(tris), "type": "SCALAR"}],
           "bufferViews": views, "buffers": [{"byteLength": offset}]}
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    blob = b"".join(d + b"\0" * (-len(d) % 4) for d in blobs)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + blob)
    return len(pos), len(tris) // 3


def frame_sample(bakes, backdrop, res, what):
    """Composite of the landscapes (and the backdrop outside them) on the FRAME grid at res x res."""
    fx, fz, size = FRAME
    px = size / res
    c = (np.arange(res) + 0.5) * px
    out = None
    zz, xx = np.meshgrid(fz + c, fx + c, indexing="ij")
    filled = np.zeros((res, res), bool)
    for B in bakes:
        nz, nx = B["h"].shape
        j = (zz - B["z0"]) / B["step"]
        i = (xx - B["x0"]) / B["step"]
        inside = (i >= 0) & (j >= 0) & (i <= nx - 1) & (j <= nz - 1) & ~filled
        if not inside.any():
            continue
        vals = what(B, j[inside], i[inside])
        if out is None:
            out = np.zeros((res, res) + vals.shape[1:], vals.dtype)
        out[inside] = vals
        filled |= inside
    if backdrop is not None and (~filled).any():
        j = (zz[~filled] - backdrop["z0"]) / backdrop["step"]
        i = (xx[~filled] - backdrop["x0"]) / backdrop["step"]
        out[~filled] = what(backdrop, j, i)
    return out, filled


def write_outputs(bakes, backdrop, D, args, log):
    os.makedirs(os.path.join(OUT, "biome"), exist_ok=True)
    enc = lambda h: np.clip(np.round((h - bt.H_MIN) / bt.H_SPAN * 65535.0), 0, 65535).astype(np.uint16)  # noqa: E731
    for L, B in zip(LANDSCAPES, bakes):
        if not args.preview:
            Image.fromarray(enc(B["h"])).save(os.path.join(OUT, L["file"]))
    # Biome maps on the frame (the material reads them by world position).
    def weights_at(B, j, i):
        if "w" in B:
            return np.stack([nd.map_coordinates(B["w"][k].astype(np.float32), [j, i], order=1, mode="nearest")
                             for k in range(len(bt.LAYERS))], -1)
        return np.zeros(j.shape + (len(bt.LAYERS),), np.float32)
    w, inside = frame_sample(bakes, backdrop, BIOME_RES, weights_at)
    total = w.sum(-1, keepdims=True)
    w = np.where(total > 1, w * 255.0 / np.maximum(total, 1e-3), 0)
    A = w[..., :4].round().clip(0, 255).astype(np.uint8)
    Bm = w[..., 4:].round().clip(0, 255).astype(np.uint8)
    Image.fromarray(A, "RGBA").save(os.path.join(OUT, "biome", "T_LyrisBiomeA.png"), optimize=True)
    Image.fromarray(Bm, "RGBA").save(os.path.join(OUT, "biome", "T_LyrisBiomeB.png"), optimize=True)
    fx, fz, size = FRAME
    with open(os.path.join(OUT, "biome", "biome_maps.json"), "w") as f:
        json.dump({"res": BIOME_RES, "world_min_ue": fz * 100.0, "world_min_ue_xy": [fx * 100.0, fz * 100.0],
                   "world_size_ue": size * 100.0,
                   "maps": {"T_LyrisBiomeA": ["Grass", "Forest", "Sand", "Rock"],
                            "T_LyrisBiomeB": ["Snow", "Badlands", "Salt", "Volcanic"]},
                   "row_axis": "UE Y (row 0 = min Y)", "col_axis": "UE X (col 0 = min X)",
                   "note": "Moonharbor frame (T55): X and Y start at different values (world_min_ue_xy)",
                   "moonharbor_version": MH_VERSION}, f, indent=1)

    def height_at(B, j, i):
        return nd.map_coordinates(B["h"], [j, i], order=1, mode="nearest")
    hf, _ = frame_sample(bakes, backdrop, BIOME_RES, height_at)
    np.save(os.path.join(OUT, "frame_height.npy"), hf.astype(np.float32))
    sg, _ = frame_sample(bakes, backdrop, SEA_GROUND_RES, height_at)
    Image.fromarray(enc(sg)).save(os.path.join(OUT, "Moonharbor_SeaGround.png"))

    def ext_at(B, j, i):
        if "ext" in B:
            return np.stack([nd.map_coordinates(B["ext"][k].astype(np.float32), [j, i], order=1, mode="nearest")
                             for k in range(4)], -1)
        return np.zeros(j.shape + (4,), np.float32)
    ex, _ = frame_sample(bakes, None, BIOME_RES, ext_at)
    Image.fromarray(ex.round().clip(0, 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, "frame_extra.png"))
    log(f"[Lyris] biome maps, sea ground and scatter frame written ({BIOME_RES} px over {size:.0f} m)")


def chunk_of(x, z):
    chunks = np.asarray(Image.open(CHUNKS_PNG))
    i = int(np.clip((x + 12500.0) / 25.0, 0, chunks.shape[1] - 1))
    j = int(np.clip((z + 12500.0) / 25.0, 0, chunks.shape[0] - 1))
    return int(chunks[j, i])


def landmark_ids_1_0():
    """Landmarks whose parts mostly lie in 1.0 chunks (the town, the bay, Keep Hill, the Teeth, the
    Lampwick Skerries' lamps, the first waystone ring)."""
    with open(LANDMARKS_JSON) as f:
        data = json.load(f)
    ids = []
    for lm in data["landmarks"]:
        pts = [p["c"] for p in lm.get("parts", []) if p.get("c")]
        if not pts:
            continue
        inside = sum(chunk_of(x, z) in WAVE_1_0 for x, z in pts)
        if inside >= 0.6 * len(pts):
            ids.append(lm["id"])
    return ids


def write_manifest(F, noise, D, bakes, args, backdrop_info, log):
    lakes, rivers = [], []
    wonder_lakes, _ = bt.wonder_manifest(F)
    boxes = [landscape_box(L) for L in LANDSCAPES]
    near_box = (-9000.0, -9500.0, 8000.0, 2500.0)
    for lake in F.lakes + wonder_lakes:
        cx, cz = lake["centre_mc"]
        on_land = any(in_box(np.array(cx), np.array(cz), b) for b in boxes)
        big = lake["area_m2"] >= 150000 and in_box(np.array(cx), np.array(cz), near_box)
        if on_land or big:
            lakes.append(lake)
    for river in F.rivers:
        pts = np.array(river["points_ue"]) / 100.0
        if any(in_box(pts[:, 0], pts[:, 1], b).any() for b in boxes):
            rivers.append(river)
    sx, sy, sz = bt.SPAWN_MC
    sh, _m, _o = mh_terrain(F, noise, D, np.array([[sx]]), np.array([[sz]]))
    land = []
    for L, B in zip(LANDSCAPES, bakes):
        quads = L["quads_per_section"] * L["sections_per_component"]
        cxm = L["x0"] + (L["nx"] - 1) * L["step"] / 2.0
        czm = L["z0"] + (L["nz"] - 1) * L["step"] / 2.0
        land.append({
            "name": L["name"], "file": L["file"], "resolution": [L["nx"], L["nz"]], "metres_per_vertex": L["step"],
            "corner_mc": [L["x0"], L["z0"]], "location_corner": [L["x0"] * 100.0, L["z0"] * 100.0,
                                                                 (bt.H_MIN + bt.H_SPAN / 2) * 100.0],
            "location_centre": [cxm * 100.0, czm * 100.0, (bt.H_MIN + bt.H_SPAN / 2) * 100.0],
            "scale": [L["step"] * 100.0, L["step"] * 100.0, 100.0],
            "quads_per_section": L["quads_per_section"], "sections_per_component": L["sections_per_component"],
            "components": [(L["nx"] - 1) // quads, (L["nz"] - 1) // quads],
            "height_range_m": [round(float(B["h"].min()), 2), round(float(B["h"].max()), 2)],
        })
    checks = {}
    for name, (x, z) in {"gate": (501, -2526), "lighthouse_terrace": (127, -2343), "syrena_islet": (247, -2462),
                         "moonwell": (200.5, -2299.5), "oruth_floor": (-120, -2612), "waystone": (725, -2650),
                         "keep_road_start": (326, -2378), "seawall_stair_top": (204, -2357)}.items():
        hh, _m, _o = mh_terrain(F, noise, D, np.array([[float(x)]]), np.array([[float(z)]]))
        checks[name] = {"mc": [x, z], "ground_m": round(float(hh[0, 0]), 2), "ground_mc_y": round(float(hh[0, 0]) + 63.0, 2)}
    fx, fz, size = FRAME
    man = {
        "moonharbor_version": MH_VERSION, "bake_version": bt.BAKE_VERSION, "seed": bt.SEED, "preview": bool(args.preview),
        "coordinates": "MC X -> UE X, MC Z -> UE Y, UE Z = (MC Y - 63) * 100; 1 m = 100 uu",
        "height_encoding": {"min_m": bt.H_MIN, "max_m": bt.H_MIN + bt.H_SPAN, "sea_level_value": round(-bt.H_MIN / bt.H_SPAN * 65535)},
        "landscapes": land,
        "backdrop": backdrop_info,
        "frame_mc": {"x0": fx, "z0": fz, "size": size},
        "sea_ground": {"file": "Moonharbor_SeaGround.png", "min_ue": [fx * 100.0, fz * 100.0], "size_ue": size * 100.0,
                       "scale_m": bt.H_SPAN, "offset_m": bt.H_MIN},
        "bounds_ue": [BOUNDS_MC[0] * 100.0, BOUNDS_MC[1] * 100.0, BOUNDS_MC[2] * 100.0, BOUNDS_MC[3] * 100.0],
        "calm_zone_ue": list(CALM_ZONE_UE),
        "spawn": {"mc": list(bt.SPAWN_MC), "ue": mc_to_ue(sx, sz, float(sh[0, 0]) + 1.0), "yaw": -90.0,
                  "ground_m": round(float(sh[0, 0]), 2)},
        "landmarks_1_0": landmark_ids_1_0(),
        "bridges": D.bridges,
        "ford_mc": [round(D.ford["x"], 1), round(D.ford["z"], 1)],
        "keep_road_mc": [[round(float(x), 1), round(float(z), 1)] for x, z in D.kr_pts[::6]],
        "coast_road_mc": [[round(float(x), 1), round(float(z), 1)] for x, z in D.cr_pts[::4]],
        "field_terraces": len(D.cells),
        "lakes": lakes, "rivers": rivers, "canon_checks": checks,
        # the scatter and lyris_build_world's step functions read these names
        "world_bounds_ue": [BOUNDS_MC[0] * 100.0, BOUNDS_MC[2] * 100.0],
    }
    with open(os.path.join(OUT, "moonharbor_manifest.json"), "w") as f:
        json.dump(man, f, indent=1)
    log("[Lyris] canon checks (MC Y): " + ", ".join(f"{k} {v['ground_mc_y']}" for k, v in checks.items()))
    log(f"[Lyris] manifest: {len(lakes)} lakes, {len(rivers)} upland river reaches, {len(man['landmarks_1_0'])} landmarks in 1.0")
    return man


# ----------------------------------------------------------------------------- previews

def render_previews(bakes, backdrop, log, only=None):
    import preview_terrain_look as P
    look = P.Look(biome_dir=os.path.join(OUT, "biome"))
    main, gulf = bakes

    def region(B, x0, z0, w_m, h_m, res):
        nxp, nzp = int(w_m / res), int(h_m / res)
        xs = x0 + (np.arange(nxp) + 0.5) * res
        zs = z0 + (np.arange(nzp) + 0.5) * res
        zz, xx = np.meshgrid(zs, xs, indexing="ij")
        hh = np.full(zz.shape, np.nan, np.float32)
        ww = np.full(zz.shape, np.nan, np.float32)
        for Bx in (B if isinstance(B, (list, tuple)) else [B]):
            nz, nx = Bx["h"].shape
            j = (zz - Bx["z0"]) / Bx["step"]
            i = (xx - Bx["x0"]) / Bx["step"]
            ins = (i >= 0) & (j >= 0) & (i <= nx - 1) & (j <= nz - 1) & np.isnan(hh)
            hh[ins] = nd.map_coordinates(Bx["h"], [j[ins], i[ins]], order=1)
            ww[ins] = nd.map_coordinates(np.nan_to_num(Bx["water"], nan=-1e4), [j[ins], i[ins]], order=0)
        if backdrop is not None and np.isnan(hh).any():
            m = np.isnan(hh)
            j = (zz[m] - backdrop["z0"]) / backdrop["step"]
            i = (xx[m] - backdrop["x0"]) / backdrop["step"]
            hh[m] = nd.map_coordinates(backdrop["h"], [j, i], order=3, mode="nearest")
            ww[m] = nd.map_coordinates(np.nan_to_num(backdrop["water"], nan=-1e4), [j, i], order=0, mode="nearest")
        hh = np.where(np.isnan(hh), -30.0, hh)
        ww = np.where(ww < -1e3, np.nan, ww)
        return hh, ww

    def lit(h, water, x0, z0, res, sun, clear_water=False):
        if clear_water:
            # "Readable from a boat on a calm day": the seabed in its sand colour (no depth darkening), lit
            # by a high sun so the terraces cast shade, under a thin wash of sea colour.
            alb, _ = P.evaluate(look, np.maximum(h, -1.0), x0, z0, res, view_cm=130000.0)
            N = P.normals(h, res)
            dry = np.full_like(h, -1e4)
            rad, surf = P.shade(alb, h, N, res, P.sun_vector(250.0, 38.0), dry)
            depth = np.clip(-h, 0, None)
            wet = h < 0
            shallows, sea = P.lin("7FD0D6"), P.lin("2E8A9C")
            wcol = P.mix(shallows, sea, P.sat(depth / 30.0)) * 0.85
            a = (0.3 + 0.38 * P.sat(depth / 60.0))[..., None]
            rad = np.where(wet[..., None], P.mix(rad, wcol, a), rad)
            surf = np.maximum(h, 0.0)
        else:
            alb, N = P.evaluate(look, h, x0, z0, res, view_cm=130000.0)
            rad, surf = P.shade(alb, h, N, res, sun, water)
        return rad, surf

    def save(img, path, label):
        from PIL import ImageDraw
        ImageDraw.Draw(img).text((16, 14), label, fill=(250, 244, 232))
        for q in (88, 82, 76):
            img.save(path, quality=q, optimize=True)
            if os.path.getsize(path) < 900_000:
                break
        log(f"[Lyris] preview {os.path.relpath(path, ROOT)}")

    t0 = time.time()
    # Overview: the whole 1.0 area from above, map light from the north-west.
    if only is None or "overview" in only:
        res = 4.0
        x0, z0, w_m, h_m = -3460.0, -5000.0, 6040.0, 4380.0
        h, wat = region([main, gulf], x0, z0, w_m, h_m, res)
        rad, _ = lit(h, wat, x0, z0, res, P.sun_vector(45.0, 35.0))
        img = Image.fromarray(P.finish(rad, 0.9)).resize((1510, 1095), Image.LANCZOS)
        save(img, os.path.join(HERE, "preview_mh_overview.jpg"),
             "Moonharbor 1.0 from above (6 x 4.4 km; north up; preview of the bake + T50 material)")

    views = [
        ("preview_mh_bay.jpg", main, (-200.0, -2620.0), 1500.0, 600.0, 1.0, 140.0, True, 190.0, 760.0,
         "Starfall Bay: the drowned Aurenhal terraces, the beach and Oruth's pit (water shown clear)"),
        ("preview_mh_keephill.jpg", main, (420.0, -2640.0), 1200.0, 500.0, 1.0, 10.0, False, 170.0, 700.0,
         "Keep Hill: the cliff toward the bay, the switchback Keep Road, the waystone upland"),
        ("preview_mh_fields.jpg", main, (700.0, -1700.0), 1600.0, 600.0, 1.0, -70.0, False, 200.0, 800.0,
         "Wayside Fields: field terraces, hedgerow banks, the river branch and the ford"),
        ("preview_mh_shore.jpg", main, (-560.0, -3150.0), 1600.0, 600.0, 1.0, 160.0, False, 230.0, 850.0,
         "Mistwater Shore: low cliffs, sand coves and the Old Coast Road"),
        ("preview_mh_skerries.jpg", gulf, (-2500.0, -4560.0), 1900.0, 500.0, 2.0, -20.0, False, 200.0, 900.0,
         "The Lampwick Skerries: six grey-rock islets with coves"),
    ]
    for name, B, (cx, cz), size, pad, res, heading, clear, height, back, label in views:
        if only is not None and name[len("preview_mh_"):-4] not in only:
            continue
        span = size + 2 * pad
        x0, z0 = cx - span / 2, cz - span / 2
        h, wat = region([main, gulf] if B is main else [gulf, main], x0, z0, span, span, res)
        rad, surf = lit(h, wat, x0, z0, res, P.sun_vector(*P.GAME_SUN), clear_water=clear)
        view = P.oblique(rad, surf, x0, z0, res, (cx, cz), heading, back_m=back, height_m=height)
        img = Image.fromarray(P.finish(view))
        p = int(pad / res)
        k = int(size / res)
        top = P.finish(rad[p:p + k, p:p + k])
        inset = Image.fromarray(top).resize((300, 300), Image.LANCZOS)
        frame = Image.new("RGB", (306, 306), (247, 238, 220))
        frame.paste(inset, (3, 3))
        img.paste(frame, (img.width - 318, img.height - 318))
        save(img, os.path.join(HERE, name), label)
    log(f"[Lyris] previews done ({time.time() - t0:.0f}s)")


# ----------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", action="store_true", help=f"bake at {PREVIEW_STEP:.0f} m per vertex (fast look, not for import)")
    ap.add_argument("--fields-cache", help="reuse bake_terrain's whole-map fields from this pickle (made on the first run)")
    ap.add_argument("--previews-only", action="store_true", help="re-render the preview images from the saved bake")
    ap.add_argument("--only", help="with --previews-only: some of overview,bay,keephill,fields,shore,skerries")
    ap.add_argument("--no-previews", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()

    def log(msg):
        print(msg, flush=True)

    os.makedirs(OUT, exist_ok=True)
    cache_bakes = os.path.join(OUT, "bake_arrays.pkl")
    if args.previews_only:
        with open(cache_bakes, "rb") as f:
            bakes, back = pickle.load(f)
        render_previews(bakes, back, log, only=args.only.split(",") if args.only else None)
        return 0

    log(f"[Lyris] Moonharbor bake v{MH_VERSION} (world bake v{bt.BAKE_VERSION}, seed {bt.SEED})"
        + ("  PREVIEW" if args.preview else ""))
    if args.fields_cache and os.path.exists(args.fields_cache):
        with open(args.fields_cache, "rb") as f:
            F = pickle.load(f)
        F._ref_masks(log)
        log(f"[Lyris] whole-map fields from {args.fields_cache}")
    else:
        F = bt.Fields(log)
        if args.fields_cache:
            with open(args.fields_cache, "wb") as f:
                pickle.dump(F, f, protocol=5)
    noise = bt.Noise(bt.SEED)
    R = Region(F, noise, log)
    D = Detail(F, noise, R, log)

    bakes = []
    for L in LANDSCAPES:
        step = max(PREVIEW_STEP, L["step"]) if args.preview else L["step"]
        bakes.append(bake_landscape(F, noise, D, L, step, log))
    backdrop = bake_backdrop(F, noise, log)
    holes = [landscape_box(L) for L in LANDSCAPES]
    nv, nt = write_backdrop_glb(backdrop, os.path.join(OUT, "backdrop.glb"), holes)
    backdrop_info = {"file": "backdrop.glb", "vertices": nv, "triangles": nt, "step_m": BACKDROP_STEP,
                     "sink_m": BACKDROP_SINK, "units": "metres, glTF Y up; positions are world MC metres",
                     "hole_mc": holes, "probes_mc": backdrop_probes(backdrop)}
    log(f"[Lyris] backdrop mesh: {nv} vertices, {nt} triangles")
    write_outputs(bakes, backdrop, D, args, log)
    write_manifest(F, noise, D, bakes, args, backdrop_info, log)
    slim = [{k: v for k, v in B.items() if k != "w"} for B in bakes]
    back = {k: backdrop[k] for k in ("h", "water", "x0", "z0", "step")}
    with open(cache_bakes, "wb") as f:
        pickle.dump((slim, back), f, protocol=5)
    if not args.no_previews:
        render_previews(slim, back, log)
    for L, B in zip(LANDSCAPES, bakes):
        land = (B["h"] > 0).mean() * 100
        log(f"[Lyris] {L['name']}: {B['h'].shape[1]} x {B['h'].shape[0]} at {B['step']:.0f} m, "
            f"heights {B['h'].min():.1f} .. {B['h'].max():.1f} m, land {land:.1f}%")
    log(f"[Lyris] done in {time.time() - t0:.0f}s -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
