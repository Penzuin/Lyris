"""Offline look-dev previews of the world foliage (T51): a few close views and the world density map.

    pip install numba                              # only this script needs it
    python Art/World/foliage/render_previews.py    # after scatter.py; a few minutes

A small software renderer (z-buffer rasteriser in numba, shadow map, alpha-tested cards) that imitates the
Unreal materials in lyris_world_foliage.py: canopy gradient from the shaded underside to the sunlit top,
dark inside, rim light, light through leaves, painted terrain from the baked paint layers, the landscape
grass types scattered near the camera, aerial perspective. It is a look check, not the game's lighting.

Writes previews/*.jpg (each under ~400 KB).
"""

import argparse
import math
import os
import struct
import sys
import time

import numpy as np
from numba import njit
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import palette  # noqa: E402
import scatter as sc  # noqa: E402
import species as sp  # noqa: E402
import textures as tx  # noqa: E402

LAYER_LOOK = {  # lyris_build_world.LAYER_LOOK colours (first, second)
    "Grass": ("9DB872", "6E9061"), "Forest": ("6E9061", "4F7558"), "Sand": ("EFE2C4", "F1E9DC"),
    "Rock": ("8E7680", "D6BC9F"), "Snow": ("F7EEDC", "EEF3FF"), "Badlands": ("C8643A", "C8443A"),
    "Salt": ("F1E9DC", "F7EEDC"), "Volcanic": ("36221A", "4A2A1C"),
}
SKY_TOP, SKY_HORIZON = np.array(palette.rgb("7AC0E6")), np.array(palette.rgb("EEF3FF"))
SEA = np.array(palette.rgb("2E8A9C"))
SHALLOWS = np.array(palette.rgb("7FD0D6"))


def hexv(h):
    return np.array(palette.rgb(h))


# ----------------------------------------------------------------------------- raster

@njit(cache=True)
def _raster(sx, sy, close, iw, tris, alpha_tex, uv, atlas, W, H, depth, ids, b1, b2):
    n_tex, AH, AW = atlas.shape
    for t in range(tris.shape[0]):
        i0, i1, i2 = tris[t, 0], tris[t, 1], tris[t, 2]
        if iw[i0] <= 0 or iw[i1] <= 0 or iw[i2] <= 0:
            continue
        x0, y0, x1, y1, x2, y2 = sx[i0], sy[i0], sx[i1], sy[i1], sx[i2], sy[i2]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        xmin = max(int(math.floor(min(x0, min(x1, x2)))), 0)
        xmax = min(int(math.ceil(max(x0, max(x1, x2)))), W - 1)
        ymin = max(int(math.floor(min(y0, min(y1, y2)))), 0)
        ymax = min(int(math.ceil(max(y0, max(y1, y2)))), H - 1)
        if xmin > xmax or ymin > ymax:
            continue
        if (xmax - xmin) * (ymax - ymin) > 4000000:
            continue
        at = alpha_tex[t]
        inv = 1.0 / area
        for py in range(ymin, ymax + 1):
            pyc = py + 0.5
            for px in range(xmin, xmax + 1):
                pxc = px + 0.5
                w0 = ((x1 - pxc) * (y2 - pyc) - (x2 - pxc) * (y1 - pyc)) * inv
                w1 = ((x2 - pxc) * (y0 - pyc) - (x0 - pxc) * (y2 - pyc)) * inv
                w2 = 1.0 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                c = w0 * close[i0] + w1 * close[i1] + w2 * close[i2]
                if c <= depth[py, px]:
                    continue
                q = w0 * iw[i0] + w1 * iw[i1] + w2 * iw[i2]
                p1 = w1 * iw[i1] / q
                p2 = w2 * iw[i2] / q
                if at >= 0:
                    p0 = 1.0 - p1 - p2
                    u = p0 * uv[i0, 0] + p1 * uv[i1, 0] + p2 * uv[i2, 0]
                    v = p0 * uv[i0, 1] + p1 * uv[i1, 1] + p2 * uv[i2, 1]
                    ix = min(max(int(u * AW), 0), AW - 1)
                    iy = min(max(int(v * AH), 0), AH - 1)
                    if atlas[at, iy, ix] < 128:
                        continue
                depth[py, px] = c
                ids[py, px] = t
                b1[py, px] = p1
                b2[py, px] = p2


# ----------------------------------------------------------------------------- scene

class Batch:
    """Triangles with attributes: pos (V,3) cm, nrm, uv, uv1, uv2, col, tris (T,3), tri material ids."""

    def __init__(self):
        self.parts = []

    def add(self, pos, nrm, uv, uv1, uv2, col, tris, mat):
        self.parts.append((pos.astype(np.float32), nrm.astype(np.float32), uv.astype(np.float32),
                           uv1.astype(np.float32), uv2.astype(np.float32), col.astype(np.float32),
                           tris.astype(np.int64), np.full(len(tris), mat, np.int32)))

    def merged(self):
        off = 0
        cols = [[] for _ in range(8)]
        for p in self.parts:
            for k in range(6):
                cols[k].append(p[k])
            cols[6].append(p[6] + off)
            cols[7].append(p[7])
            off += len(p[0])
        return [np.concatenate(c) for c in cols]


def rot_matrix(yaw, pitch, roll):
    """Unreal FRotationMatrix (rows = local X, Y, Z axes in world), degrees, vectorised."""
    Y, P, R = (np.radians(a) for a in (yaw, pitch, roll))
    CP, SP, CY, SY, CR, SR = np.cos(P), np.sin(P), np.cos(Y), np.sin(Y), np.cos(R), np.sin(R)
    X = np.stack([CP * CY, CP * SY, SP], -1)
    Yv = np.stack([SR * SP * CY - CR * SY, SR * SP * SY + CR * CY, -SR * CP], -1)
    Z = np.stack([-(CR * SP * CY + SR * SY), CY * SR - CR * SP * SY, CR * CP], -1)
    return np.stack([X, Yv, Z], -2)  # (N, 3, 3): world = local @ M


class Materials:
    """Material table: name -> id, with how to shade it."""

    def __init__(self):
        self.names, self.index = [], {}

    def id(self, name):
        if name not in self.index:
            self.index[name] = len(self.names)
            self.names.append(name)
        return self.index[name]


ATLAS_OF = {"cards_": "world_leaves", "plant": "world_plants", "moss": "world_plants", "wheat": "world_plants",
            "flower": "flowers"}
ATLAS_NAMES = ["world_leaves", "world_plants", "flowers"]


def atlas_of(part):
    for k, v in ATLAS_OF.items():
        if part.startswith(k):
            return ATLAS_NAMES.index(v)
    return -1


class MeshCache:
    def __init__(self):
        self.cache = {}

    def get(self, species, k, lod):
        key = (species, k, lod)
        if key not in self.cache:
            n_lods = sp.SPECIES[species].get("lods", 4)
            m = sp.build(species, k, min(lod, n_lods - 1))
            parts = {}
            for name, p in m.parts.items():
                if not p.idx:
                    continue
                parts[name] = (np.array(p.pos, np.float32), np.array(p.nrm, np.float32), np.array(p.uv, np.float32),
                               np.array(p.uv1, np.float32), np.array(p.uv2, np.float32), np.array(p.col, np.float32),
                               np.array(p.idx, np.int64).reshape(-1, 3))
            self.cache[key] = parts
        return self.cache[key]


def variant_index(name):
    stem = name[3:]
    species, letter = stem.rsplit("_", 1)
    return species.lower(), sp.VARIANT_LETTERS.index(letter)


def read_cells(cells_dir, x0, y0, x1, y1):
    """Instances (UE cm) in a box from the scatter's cell files: {variant: (N, 7)}."""
    out = {}
    c = sc.CELL_M * 100
    for ix in range(int(math.floor(x0 / c)), int(math.floor(x1 / c)) + 1):
        for iy in range(int(math.floor(y0 / c)), int(math.floor(y1 / c)) + 1):
            path = os.path.join(cells_dir, f"c_{ix}_{iy}.bin")
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                data = f.read()
            n = struct.unpack_from("<I", data, 16)[0]
            off = 20
            for _ in range(n):
                ln = struct.unpack_from("<H", data, off)[0]
                name = data[off + 2:off + 2 + ln].decode()
                cnt = struct.unpack_from("<I", data, off + 2 + ln)[0]
                off += 6 + ln
                arr = np.frombuffer(data, "<f4", cnt * 7, off).reshape(cnt, 7)
                off += cnt * 28
                m = (arr[:, 0] >= x0) & (arr[:, 0] < x1) & (arr[:, 1] >= y0) & (arr[:, 1] < y1)
                if m.any():
                    out.setdefault(name, []).append(arr[m])
    return {k: np.concatenate(v) for k, v in out.items()}


def lineup_instances(T, view):
    """Every variant of the listed species in rows across the view, for judging the designs."""
    e, tg = view.eye, view.target
    fwd = (tg - e)[:2] / np.linalg.norm((tg - e)[:2])
    side = np.array([-fwd[1], fwd[0]])
    out = {}
    rows = view.lineup
    for r, row in enumerate(rows):
        names = [sp.variant_name(s, k) for s in row for k in range(len(sp.SPECIES[s]["variants"]))]
        spacing = 900.0 if sp.SPECIES[row[0]]["group"] == "trees" else 260.0
        for i, name in enumerate(names):
            off = (i - (len(names) - 1) / 2) * spacing
            p = tg[:2] + side * off + fwd * r * (1100.0 if spacing > 500 else 380.0)
            z = T.exact_height(np.array([p[0] / 100]), np.array([p[1] / 100]))[0] * 100 - 10
            out[name] = np.array([[p[0], p[1], z, 30.0 * i, 0, 0, 1.0]], np.float32)
    return out


def add_instances(batch, mats, cache, species, k, lod, inst):
    parts = cache.get(species, k, lod)
    M = rot_matrix(inst[:, 3], inst[:, 4], inst[:, 5]) * inst[:, 6][:, None, None]
    for name, (pos, nrm, uv, uv1, uv2, col, tris) in parts.items():
        n_i, n_v = len(inst), len(pos)
        P = np.einsum("vj,njk->nvk", pos, M) + inst[:, None, :3]
        N = np.einsum("vj,njk->nvk", nrm, M)
        T = (tris[None] + (np.arange(n_i) * n_v)[:, None, None]).reshape(-1, 3)
        rep = lambda a: np.broadcast_to(a, (n_i,) + a.shape).reshape(-1, a.shape[-1])  # noqa: E731
        u2 = rep(uv2).copy()
        u2[:, 0] = (u2[:, 0] + np.repeat(np.arange(n_i) * 0.37, n_v)) % 1.0
        batch.add(P.reshape(-1, 3), N.reshape(-1, 3), rep(uv), rep(uv1), u2, rep(col), T,
                  mats.id(f"{species}|{name}"))


# ----------------------------------------------------------------------------- views

class View:
    def __init__(self, name, eye, target, fov=55.0, far_m=900.0, grass_m=70.0, sun=(-0.45, 0.35, 0.72), title="",
                 lineup=None):
        self.name, self.eye, self.target = name, np.array(eye, float), np.array(target, float)
        self.fov, self.far, self.grass_m = fov, far_m * 100, grass_m * 100
        s = np.array(sun, float)
        self.sun = s / np.linalg.norm(s)
        self.title = title
        self.lineup = lineup  # list of species to stand in a row at the target instead of the scatter


def build_scene(T, view, cells_dir, cache, mats, rng):
    """Terrain grid + instances + near-camera grass, inside the view's reach."""
    batch = Batch()
    e, tg = view.eye, view.target
    fwd = tg - e
    fwd[2] = 0
    fwd /= np.linalg.norm(fwd)
    reach = view.far
    # A box around the camera wedge (cm).
    cx, cy = e[0] + fwd[0] * reach * 0.5, e[1] + fwd[1] * reach * 0.5
    half = reach * 0.55 + 3000
    x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half

    # Terrain: a finer grid near the camera, coarser further out.
    for r0, r1, step in ((0, 15000, 120.0), (15000, 45000, 300.0), (45000, reach * 1.2, 900.0)):
        gx = np.arange(x0, x1 + step, step)
        gy = np.arange(y0, y1 + step, step)
        X, Y = np.meshgrid(gx, gy)
        d = np.hypot(X - e[0], Y - e[1])
        ahead = ((X - e[0]) * fwd[0] + (Y - e[1]) * fwd[1]) > -3000
        keep_q = (d >= r0 - step * 2) & (d <= r1 + step * 2) & ahead
        xm, ym = X / 100.0, Y / 100.0
        h = T.exact_height(xm.ravel(), ym.ravel()).reshape(X.shape)
        h = h + (sc.fbm(xm, ym, 9.0, 2, 7) - 0.5) * 0.5 * (step < 200)
        Z = h * 100.0
        gyv, gxv = np.gradient(Z, step)
        nrm = np.stack([-gxv, -gyv, np.ones_like(Z)], -1)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        ny, nx = X.shape
        idx = np.arange(nx * ny).reshape(ny, nx)
        q = keep_q[:-1, :-1] & keep_q[1:, 1:]
        a, b, c, dd = idx[:-1, :-1][q], idx[:-1, 1:][q], idx[1:, 1:][q], idx[1:, :-1][q]
        tris = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, dd], 1)])
        pos = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
        n = len(pos)
        batch.add(pos, nrm.reshape(-1, 3), np.zeros((n, 2)), np.zeros((n, 2)), np.zeros((n, 2)),
                  np.ones((n, 4)), tris, mats.id("terrain"))
    # Sea plane.
    sea = np.array([[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]], float)
    batch.add(sea, np.tile([0, 0, 1.0], (4, 1)), np.zeros((4, 2)), np.zeros((4, 2)), np.zeros((4, 2)),
              np.ones((4, 4)), np.array([[0, 1, 2], [0, 2, 3]]), mats.id("water"))

    # Instances.
    inst = read_cells(cells_dir, x0, y0, x1, y1) if not view.lineup else lineup_instances(T, view)
    n_inst = 0
    for name, arr in inst.items():
        species, k = variant_index(name)
        d = np.hypot(arr[:, 0] - e[0], arr[:, 1] - e[1])
        ahead = ((arr[:, 0] - e[0]) * fwd[0] + (arr[:, 1] - e[1]) * fwd[1]) > -1500
        spec = sp.SPECIES[species]
        cull = spec.get("cull", (5000, 5000))[1] * 100
        reach_s = reach if spec["group"] == "trees" else min(reach, cull)
        ok = ahead & (d < reach_s)
        for lod, (lo, hi) in enumerate(((0, 4000), (4000, 9000), (9000, 25000), (25000, 1e12))):
            m = ok & (d >= lo) & (d < hi)
            if m.any():
                add_instances(batch, mats, cache, species, k, lod, arr[m])
                n_inst += int(m.sum())

    # Landscape grass types near the camera (GT_Meadow, GT_Forest, GT_Dune), as the engine would spawn them.
    gr = view.grass_m
    n_try = int((gr / 100) ** 2 * 3.2)
    ang = rng.uniform(-1.1, 1.1, n_try) + math.atan2(fwd[1], fwd[0])
    rad = np.sqrt(rng.random(n_try)) * gr
    gx, gy = e[0] + np.cos(ang) * rad, e[1] + np.sin(ang) * rad
    xm, ym = gx / 100, gy / 100
    f = {n: sc.sample(T.W[n], xm, ym) for n in sc.LAYERS}
    h = T.exact_height(xm, ym)
    patch = sc.fbm(xm, ym, 40.0, 2, 55)
    dry = np.clip(f["Badlands"] * 0.8, 0, 1)
    pick = rng.random(n_try)
    land = h > 0.5
    harsh = f["Badlands"] + f["Salt"] + f["Volcanic"]
    meadow = land & (pick < (f["Grass"] + f["Forest"] * 0.25) * 1.25) & (f["Sand"] < 0.4) & (f["Snow"] < 0.5) & (harsh < 0.3)
    forest_floor = land & (pick < f["Forest"] * 0.4) & (harsh < 0.3)
    dune = land & (pick < f["Sand"] * 0.4) & (h < 8)
    choices = []
    sel = meadow & ~forest_floor
    kind = rng.random(n_try)
    flowers = sel & (patch > 0.6) & (kind < 0.35) & (dry < 0.4)
    choices.append(("grass", 0, sel & ~flowers & (kind < 0.65)))
    choices.append(("grass", 1, sel & ~flowers & (kind >= 0.65)))
    for c in range(4):
        choices.append(("flower", c, flowers & (rng.random(n_try) < 0.25)))
    choices.append(("groundfern", 0, forest_floor & (kind < 0.35)))
    choices.append(("clover", 0, forest_floor & (kind >= 0.35) & (kind < 0.8)))
    choices.append(("grass", 0, forest_floor & (kind >= 0.8)))
    choices.append(("dune", 0, dune & (kind < 0.5) & ~meadow))
    choices.append(("dune", 1, dune & (kind >= 0.5) & ~meadow))
    for species, k, m in choices:
        if not m.any():
            continue
        cnt = int(m.sum())
        arr = np.stack([gx[m], gy[m], h[m] * 100, rng.uniform(0, 360, cnt), np.zeros(cnt), np.zeros(cnt),
                        rng.uniform(0.8, 1.25, cnt)], 1)
        dist = np.hypot(arr[:, 0] - e[0], arr[:, 1] - e[1])
        for lod in (0, 1):
            mm = (dist < 2500) if lod == 0 else (dist >= 2500)
            if mm.any():
                add_instances(batch, mats, cache, species, k, lod, arr[mm])
    return batch, n_inst


# ----------------------------------------------------------------------------- shading

def material_info(mats, species_json):
    pal = species_json["palette"]
    info = []
    for name in mats.names:
        if "|" not in name:
            info.append(("special", name))
            continue
        species, part = name.split("|", 1)
        info.append((species, part))
    return info, pal


def shade(view, batch_arrays, mats, textures, species_json, W, H, shadow):
    pos, nrm, uv, uv1, uv2, col, tris, tmat = batch_arrays
    info, pal = material_info(mats, species_json)
    e = view.eye
    fwd = view.target - e
    fwd /= np.linalg.norm(fwd)
    right = np.cross([0, 0, 1.0], fwd)
    right /= np.linalg.norm(right)
    up = np.cross(fwd, right)
    f = 0.5 * W / math.tan(math.radians(view.fov) / 2)
    rel = pos - e
    zc = rel @ fwd
    iw = np.where(zc > 10.0, 1.0 / np.maximum(zc, 10.0), -1.0)
    sx = (W * 0.5 + (rel @ right) * f * iw).astype(np.float64)
    sy = (H * 0.5 - (rel @ up) * f * iw).astype(np.float64)
    far = zc > view.far * 1.3
    iw[far] = -1
    alpha_tex = np.array([atlas_of(info[m][1]) if info[m][0] != "special" else -1 for m in range(len(info))])[tmat]
    atl = np.stack([np.asarray(Image.fromarray(textures[n][..., 3]).resize((1024, 512), Image.NEAREST))
                    for n in ATLAS_NAMES])
    depth = np.full((H, W), -1.0)
    ids = np.full((H, W), -1, np.int64)
    b1 = np.zeros((H, W))
    b2 = np.zeros((H, W))
    _raster(sx, sy, iw.astype(np.float64), iw.astype(np.float64), tris, alpha_tex.astype(np.int64), uv.astype(np.float64),
            atl, W, H, depth, ids, b1, b2)

    hit = ids >= 0
    t = ids[hit]
    p1, p2 = b1[hit], b2[hit]
    p0 = 1 - p1 - p2
    tri = tris[t]

    def interp(a):
        return a[tri[:, 0]] * p0[:, None] + a[tri[:, 1]] * p1[:, None] + a[tri[:, 2]] * p2[:, None]

    P = interp(pos)
    Nn = interp(nrm)
    Nn /= np.linalg.norm(Nn, axis=1, keepdims=True) + 1e-9
    UV, UV1, UV2, COL = interp(uv), interp(uv1), interp(uv2), interp(col)
    M = tmat[t]
    L = view.sun
    sh = shadow(P) if shadow else np.ones(len(P))
    ndl = Nn @ L
    sun_col = hexv("FFF6E8") * 1.05
    sky_amb = hexv("EEF3FF") * 0.42
    ground_amb = hexv("CDAE86") * 0.12
    up_n = np.clip(Nn[:, 2] * 0.5 + 0.5, 0, 1)
    amb = sky_amb[None] * up_n[:, None] + ground_amb[None] * (1 - up_n[:, None])
    out = np.zeros((len(P), 3))
    view_dir = P - e
    view_dir /= np.linalg.norm(view_dir, axis=1, keepdims=True)
    fres = np.clip(1 - np.abs((Nn * -view_dir).sum(1)), 0, 1) ** 3

    for mid, (species, part) in enumerate(info):
        m = M == mid
        if not m.any():
            continue
        n_ = Nn[m]
        lam = np.clip(ndl[m], 0, 1)[:, None] * sh[m][:, None]
        if species == "special" and part == "terrain":
            c = terrain_colour(P[m] / 100.0, n_)
            out[m] = c * (amb[m] + sun_col * lam)
        elif species == "special" and part == "water":
            d = np.clip(-sc.Terrain.exact_height(_T, P[m][:, 0] / 100, P[m][:, 1] / 100) / 6.0, 0, 1)[:, None]
            c = SHALLOWS * (1 - d) + SEA * d
            out[m] = c * (0.75 + 0.35 * sh[m][:, None]) + fres[m][:, None] * 0.25
        elif part.startswith(("shell_", "cards_")):
            key = part.split("_", 1)[1]
            lo, hi = (hexv(h) for h in pal["canopy"][key])
            grad = np.clip(0.6 * up_n[m] + 0.55 * UV1[m][:, 1], 0, 1)[:, None]
            base = lo * (1 - grad) + hi * grad
            depthf = (0.6 + 0.4 * np.clip(UV1[m][:, 0], 0, 1))[:, None]
            vary = (0.94 + 0.12 * UV2[m][:, 0])[:, None]
            base = base * depthf * vary
            if key in ("snowpine", "frostshrub"):
                snow = np.clip((n_[:, 2] - 0.55) * 3.0, 0, 1)[:, None] * np.clip((UV1[m][:, 1] - 0.4) * 2.0, 0, 1)[:, None]
                base = base * (1 - snow) + hexv(pal["snow"]) * snow
            wrap = (np.clip(ndl[m] * 0.5 + 0.5, 0, 1) ** 1.5)[:, None] * (0.35 + 0.65 * sh[m][:, None])
            trans = np.clip(-(view_dir[m] @ -L), 0, 1)[:, None] ** 4 * 0.25 * hexv(pal["canopy"][key][1])
            rim = fres[m][:, None] * 0.22 * hexv(pal["canopy"][key][1])
            out[m] = base * (amb[m] * 0.9 + sun_col * wrap * 0.85 + 0.18) + rim + trans
        elif part.endswith("bark"):
            tex_name, tint = pal["bark"][part]
            tex = textures[tex_name]
            c = tex[..., :3].reshape(-1, 3).mean(0) / 255.0
            if tint:
                c = c * hexv(tint) * 1.25
            stripe = (0.9 + 0.2 * sc.vnoise(P[m][:, 2] / 20.0, (P[m][:, 0] + P[m][:, 1]) / 15.0, 1.0, 3))[:, None]
            out[m] = c * stripe * (amb[m] + sun_col * lam)
        elif part in ("rock", "vent_rock"):
            if part == "rock":
                g = np.clip((n_[:, 2] - 0.72) / 0.2, 0, 1)[:, None]
                c = hexv("8E7680") * (1 - up_n[m][:, None]) + hexv("D6BC9F") * up_n[m][:, None]
                c = c * (1 - g) + hexv("9DB872") * g
            else:
                c = hexv("36221A") * 1.2
            out[m] = c * (amb[m] + sun_col * lam)
        elif part == "crystal":
            c = hexv("F1E9DC") * 0.9 + hexv("EEF3FF") * 0.1
            out[m] = c * (amb[m] * 1.3 + sun_col * lam * 0.7 + 0.2) + fres[m][:, None] * 0.35
        elif part == "mushroom":
            cap = np.clip(n_[:, 2] * 2 - 0.4, 0, 1)[:, None]
            c = hexv("F4E8D2") * (1 - cap) + hexv("D2714E") * cap
            out[m] = c * (amb[m] + sun_col * lam) + c * 0.12
        elif part == "berry":
            out[m] = hexv("B04A6E") * (amb[m] + sun_col * lam) * 1.1
        elif part == "grass":
            v = np.clip(UV[m][:, 1], 0, 1)[:, None]
            c = terrain_colour(P[m] / 100.0, np.tile([0, 0, 1.0], (int(m.sum()), 1)), grass_only=True)
            c = c * (0.8 + 0.35 * v)
            out[m] = c * (amb[m] + sun_col * (0.55 + 0.45 * sh[m][:, None])) + c * 0.12
        else:  # cut-out atlas plants, flowers, moss, wheat
            at = textures[ATLAS_NAMES[atlas_of(part)]]
            ah, aw = at.shape[:2]
            iu = np.clip((UV[m][:, 0] * aw).astype(int), 0, aw - 1)
            iv = np.clip((UV[m][:, 1] * ah).astype(int), 0, ah - 1)
            c = at[iv, iu, :3] / 255.0
            glow = 0.6 if part == "moss" else 0.0
            out[m] = c * (amb[m] + sun_col * (0.5 + 0.5 * sh[m][:, None])) + c * (0.15 + glow)

    # Aerial perspective and sky.
    dist = np.linalg.norm(P - e, axis=1) / 100.0
    fog = (1 - np.exp(-dist / 1800.0))[:, None] * 0.85
    horizon = SKY_HORIZON * 0.97
    out = out * (1 - fog) + horizon * fog
    img = np.zeros((H, W, 3))
    yy = np.linspace(0, 1, H)[:, None, None]
    img[:] = SKY_TOP * (1 - yy) * 0.9 + SKY_HORIZON * yy
    img[hit] = out
    return img, hit.mean()


_T = None


def terrain_colour(pm, n, grass_only=False):
    """The T50-style painted ground: paint-layer colours, large soft second-colour patches, rock on steep."""
    x, y = pm[:, 0], pm[:, 1]
    w = {k: sc.sample(_T.W[k], x, y) for k in sc.LAYERS}
    patch = sc.fbm(x, y, 28.0, 3, 91)[:, None]
    c = np.zeros((len(x), 3))
    tot = np.zeros((len(x), 1))
    for k, (a, b) in LAYER_LOOK.items():
        if grass_only and k in ("Rock",):
            continue
        ww = w[k][:, None]
        col = hexv(a) * (1 - patch * 0.6) + hexv(b) * patch * 0.6
        c += col * ww
        tot += ww
    c /= np.maximum(tot, 1e-6)
    if not grass_only:
        steep = np.clip((0.82 - n[:, 2]) / 0.12, 0, 1)[:, None]
        up = np.clip(n[:, 2] * 0.5 + 0.5, 0, 1)[:, None]
        rock = hexv("8E7680") * (1 - up) + hexv("D6BC9F") * up
        c = c * (1 - steep) + rock * steep
    detail = 0.9 + 0.2 * sc.fbm(x, y, 3.0, 2, 92)[:, None]
    return c * detail


def make_shadow(view, arrays, mats, textures, species_json, res=3072):
    pos, nrm, uv, uv1, uv2, col, tris, tmat = arrays
    info, _ = material_info(mats, species_json)
    L = view.sun
    upv = np.array([0, 0, 1.0])
    r = np.cross(upv, L)
    r /= np.linalg.norm(r)
    u = np.cross(L, r)
    centre = view.eye + (view.target - view.eye) / np.linalg.norm(view.target - view.eye) * min(view.far, 60000) * 0.5
    extent = min(view.far, 60000) * 0.6
    rel = pos - centre
    sx = (rel @ r / extent * 0.5 + 0.5) * res
    sy = (0.5 - rel @ u / extent * 0.5) * res
    close = rel @ L
    alpha_tex = np.array([atlas_of(info[m][1]) if info[m][0] != "special" else -1 for m in range(len(info))])[tmat]
    no_cast = [mats.index.get("water", -9)] + [i for i, n in enumerate(mats.names)
                                               if n.split("|")[0] in ("grass", "flower", "clover", "groundfern", "dune", "wheat")]
    terrain_or_water = np.isin(tmat, no_cast)
    atl = np.stack([np.asarray(Image.fromarray(textures[n][..., 3]).resize((1024, 512), Image.NEAREST))
                    for n in ATLAS_NAMES])
    depth = np.full((res, res), -1e12)
    ids = np.full((res, res), -1, np.int64)
    b1 = np.zeros((res, res))
    b2 = np.zeros((res, res))
    keep = ~terrain_or_water
    _raster(sx.astype(np.float64), sy.astype(np.float64), close.astype(np.float64), np.ones(len(pos)),
            tris[keep], alpha_tex[keep].astype(np.int64), uv.astype(np.float64), atl, res, res, depth, ids, b1, b2)

    def lookup(P):
        rp = P - centre
        ix = ((rp @ r / extent * 0.5 + 0.5) * res).astype(int)
        iy = ((0.5 - rp @ u / extent * 0.5) * res).astype(int)
        inside = (ix >= 0) & (ix < res) & (iy >= 0) & (iy < res)
        ix, iy = np.clip(ix, 0, res - 1), np.clip(iy, 0, res - 1)
        occ = depth[iy, ix] > (rp @ L) + 40.0
        s = np.where(inside & occ, 0.0, 1.0)
        return s

    return lookup


def render(view, T, cells_dir, species_json, textures, out_path, W=1600, H=900, ss=2, seed=3):
    global _T
    _T = T
    t0 = time.time()
    mats = Materials()
    cache = MeshCache()
    batch, n_inst = build_scene(T, view, cells_dir, cache, mats, np.random.default_rng(seed))
    arrays = batch.merged()
    shadow = make_shadow(view, arrays, mats, textures, species_json)
    img, cover = shade(view, arrays, mats, textures, species_json, W * ss, H * ss, shadow)
    im = Image.fromarray((np.clip(img, 0, 1) ** (1 / 1.0) * 255).astype(np.uint8)).resize((W, H), Image.LANCZOS)
    for q in (88, 80, 72):
        im.save(out_path, quality=q, optimize=True)
        if os.path.getsize(out_path) < 420_000:
            break
    print(f"[Lyris] {view.name}: {n_inst} instances, {len(arrays[6])} triangles, {time.time() - t0:.0f}s -> {out_path}",
          flush=True)


# ----------------------------------------------------------------------------- picking spots

def find_spot(T, M, pred, rng, tries=400000, box=None):
    """A random land point (MC metres) where pred(fields) holds."""
    x0, z0, x1, z1 = box or (-11000, -11000, 11000, 11000)
    x = rng.uniform(x0, x1, tries)
    z = rng.uniform(z0, z1, tries)
    f = {n: sc.sample(T.W[n], x, z) for n in sc.LAYERS}
    f["h"] = sc.sample(T.H, x, z)
    for k in ("slope", "forest_s", "dist_sea", "dist_water", "convex"):
        f[k] = sc.sample(M[k], x, z)
    f["biome"] = sc.lookup(M["bidx"], x, z)
    f["region"] = sc.lookup(np.asarray(Image.open(os.path.join(sc.WORLD, "atlas", "regions.png"))), x, z)
    ok = pred(f)
    idx = np.flatnonzero(ok)
    if not len(idx):
        return None
    i = idx[0]
    return float(x[i]), float(z[i])


def look_toward(T, M, spot, rng, toward=None, back=55.0, eye_h=2.2, look_up=0.0, **kw):
    """Camera `back` m from spot (away from `toward` or at a random bearing), looking at it."""
    sx, sz = spot
    if toward is None:
        a = rng.uniform(0, 2 * math.pi)
    else:
        a = math.atan2(sz - toward[1], sx - toward[0])
    ex, ez = sx + math.cos(a) * back, sz + math.sin(a) * back
    gh = float(T.exact_height(np.array([ex]), np.array([ez]))[0])
    th = float(T.exact_height(np.array([sx]), np.array([sz]))[0])
    eye = (ex * 100, ez * 100, (max(gh, 0.5) + eye_h) * 100)
    target = (sx * 100, sz * 100, (max(th, 0.5) + eye_h * 0.8 + look_up) * 100)
    return eye, target


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated preview names")
    ap.add_argument("--width", type=int, default=1600)
    args = ap.parse_args(argv)
    import json
    with open(os.path.join(HERE, "species.json")) as f:
        species_json = json.load(f)
    tex = tx.all_textures()
    T = sc.Terrain(os.path.join(sc.WORLD, "tiles"))
    M = sc.world_masks(T, lambda m: None)
    rng = np.random.default_rng(11)
    out_dir = os.path.join(HERE, "previews")
    os.makedirs(out_dir, exist_ok=True)
    cells = os.path.join(HERE, "scatter", "cells")
    B = sc.B

    def spot(pred, box=None):
        return find_spot(T, M, pred, np.random.default_rng(len(views) + 5), box=box)

    views = []
    # 1 Forest edge in the Quiet Reach heartland: stand in the meadow, look at the trees.
    s = spot(lambda f: (np.abs(f["forest_s"] - 0.55) < 0.06) & (f["slope"] < 6) & np.isin(f["region"], [0, 6])
             & (f["h"] > 15) & (f["h"] < 110) & (f["dist_water"] > 60), box=(-4000, -4500, 3000, 0))
    if s:
        eye, tgt = look_toward(T, M, s, rng, back=45.0, look_up=2.5)
        views.append(View("forest_edge", eye, tgt, far_m=1100, title="Forest edge, Quiet Reach"))
    # 2 Meadow with lone trees and flowers.
    s = spot(lambda f: (f["forest_s"] < 0.08) & (f["Grass"] > 0.5) & (f["slope"] < 7) & (f["h"] > 10)
             & np.isin(f["region"], [1, 2, 0]) & (f["dist_water"] > 80) & (f["convex"] < -1))
    if s:
        eye, tgt = look_toward(T, M, s, rng, back=10.0, eye_h=1.7, look_up=1.0)
        views.append(View("meadow", eye, tgt, far_m=1500, grass_m=80, title="Meadow, Quiet Reach"))
    # 3 Saltreach badlands scrub.
    s = spot(lambda f: (f["Badlands"] > 0.5) & (f["slope"] < 12) & np.isin(f["region"], [8, 9]) & (f["h"] > 20))
    if s:
        eye, tgt = look_toward(T, M, s, rng, back=35.0, eye_h=2.0, look_up=3.0)
        views.append(View("saltreach_scrub", eye, tgt, far_m=1500, sun=(-0.3, 0.5, 0.6), title="Saltreach badlands"))
    # 4 Snowy pine wood in the north.
    s = spot(lambda f: (f["Snow"] > 0.4) & (f["slope"] < 14) & (f["h"] > 20) & (f["forest_s"] > 0.2), box=(-6000, -7000, 9000, -3000))
    if s is None:
        s = spot(lambda f: (f["Snow"] > 0.4) & (f["slope"] < 14) & (f["h"] > 20))
    if s:
        eye, tgt = look_toward(T, M, s, rng, back=40.0, eye_h=2.0, look_up=3.0)
        views.append(View("snowy_pines", eye, tgt, far_m=1200, sun=(0.3, 0.5, 0.55), title="Snowy north"))
    # 5 Greengrace cherry grove.
    s = spot(lambda f: np.isin(f["region"], [7]) & (f["forest_s"] > 0.45) & (f["slope"] < 10) & (f["h"] > 8),
             box=(-2600, 2500, -700, 4200))
    if s:
        eye, tgt = look_toward(T, M, s, rng, back=40.0, eye_h=2.0, look_up=3.0)
        views.append(View("greengrace", eye, tgt, far_m=1200, title="Greengrace"))
    # 6 Sunreach: dark forest and olive plains.
    s = spot(lambda f: (f["biome"] == B["dark forest"]) & (f["slope"] < 10) & (f["forest_s"] > 0.4), box=(0, 0, 11000, 11000))
    if s:
        eye, tgt = look_toward(T, M, s, rng, back=50.0, eye_h=2.0, look_up=4.0)
        views.append(View("sunreach_darkwood", eye, tgt, far_m=1200, title="Sunreach dark forest"))
    s = spot(lambda f: np.isin(f["region"], [10, 11, 12]) & np.isin(f["biome"], [B["savanna"], B["plains"]])
             & (f["slope"] < 8) & (f["forest_s"] < 0.15))
    if s:
        eye, tgt = look_toward(T, M, s, rng, back=25.0, eye_h=1.8, look_up=2.0)
        views.append(View("sunreach_plains", eye, tgt, far_m=1500, title="Sunreach plains"))
    # Line-ups of every species variant, to judge the designs side by side.
    s = spot(lambda f: (f["forest_s"] < 0.05) & (f["Grass"] > 0.6) & (f["slope"] < 3) & (f["h"] > 10)
             & (f["dist_water"] > 150), box=(-2000, -3000, 6000, 0))
    if s:
        eye, tgt = look_toward(T, M, s, rng, toward=(s[0], s[1] + 100), back=26.0, eye_h=7.0, look_up=-2.0)
        views.append(View("lineup_trees", eye, tgt, fov=62, far_m=400, grass_m=30, title="Tree species",
                          lineup=[["oak", "birch", "pine", "blossom"], ["cherry", "snowpine", "cypress"],
                                  ["darkwood", "olive", "deadtree"]]))
        eye, tgt = look_toward(T, M, s, rng, toward=(s[0], s[1] + 100), back=9.0, eye_h=3.0, look_up=-1.5)
        views.append(View("lineup_understory", eye, tgt, fov=62, far_m=300, grass_m=20, title="Understory",
                          lineup=[["bush", "frostshrub", "scrub", "sage"], ["lavender", "reeds", "fern", "mushrooms", "ventmoss"],
                                  ["rock", "boulder", "crystals", "pebbles"]]))
    # 7 High view over a forested valley (reads groves, clearings and edges).
    s = spot(lambda f: (f["forest_s"] > 0.5) & np.isin(f["region"], [6]) & (f["h"] > 20) & (f["h"] < 80))
    if s:
        eye, tgt = look_toward(T, M, s, rng, back=420.0, eye_h=140.0, look_up=-60.0)
        views.append(View("valley_aerial", eye, tgt, fov=60, far_m=2200, grass_m=0, title="Aerial over the Reach"))

    wanted = set(args.only.split(",")) if args.only else None
    for v in views:
        if wanted and v.name not in wanted:
            continue
        print(f"[Lyris] {v.name} eye MC ({v.eye[0] / 100:.0f}, {v.eye[1] / 100:.0f}) h {v.eye[2] / 100:.0f} m", flush=True)
        render(v, T, cells, species_json, tex, os.path.join(out_dir, f"{v.name}.jpg"), W=args.width,
               H=int(args.width * 9 / 16))
    dens = os.path.join(HERE, "scatter", "density.jpg")
    if os.path.exists(dens) and not wanted:
        Image.open(dens).resize((1400, 1400), Image.LANCZOS).save(os.path.join(out_dir, "world_density.jpg"), quality=85)
    return 0


if __name__ == "__main__":
    sys.exit(main())
