"""Painted atlases for the world foliage, in the starter island's soft, low-contrast style.

Reuses the island painters (Art/TestIsland/paint_textures.py) and adds two 4 x 2 atlases:

  world_leaves.png  leaf-clump cards (RGBA), 256 px cells:
      0 broadleaf clump  1 birch leaves   2 pine tuft     3 blossom petals
      4 cypress sprays   5 olive leaves   6 thorny twigs  7 frosted pine tuft
  world_plants.png  ground plants for crossed cards (RGBA), each standing on its cell's bottom edge:
      0 fern             1 dune grass     2 reeds         3 lavender
      4 wheat grass      5 desert sage    6 clover + leaf litter  7 glow moss tufts
  char_bark.png     charred bark for dead trees (seamless)

Leaf atlases only give shapes and light/dark detail: the materials take every colour from the
palette (FOLIAGE_COLOURS in Content/Python/lyris_world_foliage.py), so the cards melt into the shells.
Ground-plant atlases are drawn in their final colours.
"""

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "TestIsland"))
import paint_textures as pt  # noqa: E402

COLS, ROWS = 4, 2
LEAF_CELL = {"broadleaf": 0, "birch": 1, "pine": 2, "blossom": 3, "cypress": 4, "olive": 5, "thorn": 6,
             "frost": 7}
PLANT_CELL = {"fern": 0, "dune": 1, "reed": 2, "lavender": 3, "wheat": 4, "sage": 5, "clover": 6, "moss": 7}


def cell_uv(cell):
    """(u0, v0, du, dv) of an atlas cell; v0 is the top of the cell."""
    return (cell % COLS) / COLS, (cell // COLS) / ROWS, 1.0 / COLS, 1.0 / ROWS


def _blank(cell):
    return np.zeros((cell, cell, 4))


def _stamp(tile, mask, col):
    tile[..., :3] = tile[..., :3] * (1 - mask[..., None]) + np.asarray(col, float) * mask[..., None]
    tile[..., 3] = np.maximum(tile[..., 3], mask)


def _stroke(tile, xx, yy, x0, y0, x1, y1, width, col, taper=0.7):
    d = np.array([x1 - x0, y1 - y0], dtype=float)
    L = np.hypot(*d) or 1.0
    t = np.clip(((xx - x0) * d[0] + (yy - y0) * d[1]) / (L * L), 0, 1)
    dist = np.hypot(xx - (x0 + t * d[0]), yy - (y0 + t * d[1]))
    w = width * (1 - taper * t)
    _stamp(tile, np.clip((w - dist) / 1.2, 0, 1), col)


def _leaf_clump(rng, cell, ramp, n, length, width, pointed, radial=False, spread=0.34):
    yy, xx = np.mgrid[0:cell, 0:cell].astype(float)
    tile = _blank(cell)
    cols = [pt.hexc(c) for c in ramp]
    for _ in range(n):
        ang = rng.uniform(0, 2 * math.pi)
        dist = cell * spread * math.sqrt(rng.random())
        cx, cy = cell / 2 + math.cos(ang) * dist, cell / 2 + math.sin(ang) * dist
        ln, wd = rng.uniform(*length), rng.uniform(*width)
        angle = ang if radial else ang + rng.uniform(-0.6, 0.6)
        mask, t = pt._leaf_shape(xx, yy, cx, cy, ln, wd, angle, pointed)
        outer = dist / (cell * spread)
        base = cols[min(len(cols) - 1, int(rng.integers(0, 2) + outer * 2))]
        shade = (1.05 - 0.18 * np.clip(-t, 0, 1))[..., None]
        tile[..., :3] = tile[..., :3] * (1 - mask[..., None]) + base * shade * mask[..., None]
        tile[..., 3] = np.maximum(tile[..., 3], mask)
    return tile


def world_leaves(seed=71, cell=256):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:cell, 0:cell].astype(float)
    tiles = []
    # 0..3: the island's four clumps, redrawn at this cell size so all eight share one atlas.
    tiles.append(_leaf_clump(rng, cell, ["#D9E894", "#B6D072", "#93B45E", "#749656"], 58, (24, 38), (10, 15), True))
    tiles.append(_leaf_clump(rng, cell, ["#ECF2A8", "#D2E38A", "#B4CC72", "#97B262"], 72, (14, 20), (10, 14), False))
    tiles.append(_leaf_clump(rng, cell, ["#9FC08E", "#7FA47A", "#62886A", "#4C6E5E"], 90, (30, 46), (2.2, 3.2),
                             True, radial=True))
    tiles.append(_leaf_clump(rng, cell, ["#FFF1EA", "#FFD7C9", "#F8B9AA", "#EA9C98"], 70, (14, 20), (11, 15), False))
    # 4 cypress: flat fan-like sprays of tiny scale leaves, pointing up.
    tile = _blank(cell)
    greens = [pt.hexc(c) for c in ("#8DAE7E", "#6E9061", "#557A5A", "#4F7558")]
    for _ in range(9):
        x0, y0 = cell / 2 + rng.uniform(-60, 60), cell - rng.uniform(10, 60)
        ang = math.radians(-90 + rng.uniform(-35, 35))
        ln = rng.uniform(110, 190)
        for s in range(12):
            f = s / 12
            px, py = x0 + math.cos(ang) * ln * f, y0 + math.sin(ang) * ln * f
            for side in (-1, 1):
                la = ang + side * 0.9
                sl = (1 - f) * 26 + 8
                _stroke(tile, xx, yy, px, py, px + math.cos(la) * sl, py + math.sin(la) * sl, 6.5,
                        greens[(s + (side > 0)) % 4], taper=0.4)
    tiles.append(tile)
    # 5 olive: narrow silvery leaves, two-toned.
    tiles.append(_leaf_clump(rng, cell, ["#E3E8C2", "#C9D3A6", "#A9B98E", "#8C9E7C"], 95, (20, 30), (4.5, 6.5), True))
    # 6 thorny twigs: dark crooked stems with tiny spines and a few small leaves.
    tile = _blank(cell)
    stem = pt.hexc("#5E4644")
    for _ in range(7):
        x, y = cell / 2 + rng.uniform(-30, 30), cell - 4
        ang = math.radians(-90 + rng.uniform(-60, 60))
        for s in range(9):
            ang += rng.uniform(-0.45, 0.45)
            nx_, ny_ = x + math.cos(ang) * 22, y + math.sin(ang) * 22
            _stroke(tile, xx, yy, x, y, nx_, ny_, 3.2, stem, taper=0.2)
            for side in (-1, 1):
                if rng.random() < 0.6:
                    sa = ang + side * 1.0
                    _stroke(tile, xx, yy, nx_, ny_, nx_ + math.cos(sa) * 9, ny_ + math.sin(sa) * 9, 1.6, stem, 0.9)
            if rng.random() < 0.45:
                m, _ = pt._leaf_shape(xx, yy, nx_, ny_, 9, 4, ang + rng.uniform(-1, 1), True)
                _stamp(tile, m, pt.hexc(["#A9B98E", "#8C9E7C"][s % 2]))
            x, y = nx_, ny_
    tiles.append(tile)
    # 7 frosted pine tuft: the pine tuft with snow-white needle tips.
    tile = _leaf_clump(rng, cell, ["#9FC08E", "#7FA47A", "#62886A", "#4C6E5E"], 80, (30, 46), (2.2, 3.2), True,
                       radial=True)
    frost = np.clip((np.hypot(xx - cell / 2, yy - cell / 2) / (cell * 0.36) - 0.55) * 2.2, 0, 1)
    frost *= (yy < cell * 0.62)  # snow sits on the upper side of the tuft
    tile[..., :3] = tile[..., :3] * (1 - frost[..., None] * 0.85) + pt.hexc("#F7EEDC") * frost[..., None] * 0.85
    tiles.append(tile)
    return _pack(tiles, cell)


def world_plants(seed=83, cell=256):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:cell, 0:cell].astype(float)
    tiles = []
    # 0 fern (as on the island).
    tile = _blank(cell)
    greens = [pt.hexc(c) for c in ("#83A050", "#6E9061", "#557A5A")]  # forest-floor greens, not meadow-bright
    for _ in range(6):
        ang = math.radians(-90 + rng.uniform(-55, 55))
        x, y = cell / 2 + rng.uniform(-10, 10), cell - 4
        length, steps = rng.uniform(140, 210), 14
        for s in range(steps):
            a = ang + (s / steps) * (0.9 if math.cos(ang) > 0 else -0.9)
            nx_, ny_ = x + math.cos(a) * length / steps, y + math.sin(a) * length / steps
            _stroke(tile, xx, yy, x, y, nx_, ny_, 2.4, greens[2])
            leaf = (1 - s / steps) * 26 + 6
            for side in (-1, 1):
                la = a + side * 1.2
                _stroke(tile, xx, yy, nx_, ny_, nx_ + math.cos(la) * leaf, ny_ + math.sin(la) * leaf, 5.5,
                        greens[s % 2])
            x, y = nx_, ny_
    tiles.append(tile)
    # 1 dune grass.
    tile = _blank(cell)
    for b in range(26):
        x0, h, bend = cell / 2 + rng.uniform(-50, 50), rng.uniform(110, 220), rng.uniform(-60, 60)
        _stroke(tile, xx, yy, x0, cell - 2, x0 + bend, cell - h, 4.5, pt.hexc(["#E6DFA4", "#D2CF8C", "#B9C27E"][b % 3]))
    tiles.append(tile)
    # 2 reeds: tall straight blades and a few brown cattail heads.
    tile = _blank(cell)
    for b in range(18):
        x0, h = cell / 2 + rng.uniform(-60, 60), rng.uniform(150, 245)
        _stroke(tile, xx, yy, x0, cell - 2, x0 + rng.uniform(-18, 18), cell - h, 3.6,
                pt.hexc(["#A9C878", "#8DB066", "#B9C27E"][b % 3]), taper=0.85)
    for _ in range(4):
        x0, top = cell / 2 + rng.uniform(-45, 45), rng.uniform(25, 60)
        _stroke(tile, xx, yy, x0, cell - 2, x0, top, 2.0, pt.hexc("#86A866"), taper=0.2)
        _stroke(tile, xx, yy, x0, top + 6, x0, top + 40, 6.0, pt.hexc("#8A6A5A"), taper=0.0)
    tiles.append(tile)
    # 3 lavender: many slim stems topped with violet bead spikes.
    tile = _blank(cell)
    for _ in range(11):
        x0 = cell / 2 + rng.uniform(-55, 55)
        top = rng.uniform(30, 80)
        lean = rng.uniform(-25, 25)
        _stroke(tile, xx, yy, x0, cell - 2, x0 + lean, top, 2.2, pt.hexc("#86A866"), taper=0.3)
        for k in range(12):
            f = k / 12
            bx, by = x0 + lean * (1 - (top + k * 5 - top) / (cell - top)) , top + k * 5
            m = np.clip((4.6 - np.hypot(xx - bx - rng.uniform(-3, 3), yy - by)) / 1.2, 0, 1)
            _stamp(tile, m, pt.hexc(["#B9A8E8", "#A598DE", "#CBBEF0", "#9C8CD4"][k % 4]))
    tiles.append(tile)
    # 4 wheat grass: golden blades with seed heads.
    tile = _blank(cell)
    for b in range(22):
        x0, h, bend = cell / 2 + rng.uniform(-60, 60), rng.uniform(120, 230), rng.uniform(-40, 40)
        tx, ty = x0 + bend, cell - h
        _stroke(tile, xx, yy, x0, cell - 2, tx, ty, 3.4, pt.hexc(["#E8D49A", "#D9C07E", "#E3AE45"][b % 3]), 0.6)
        if b % 2 == 0:
            m, _ = pt._leaf_shape(xx, yy, tx, ty + 12, 16, 4.5, math.atan2(-h, bend), True)
            _stamp(tile, m, pt.hexc("#E3AE45"))
    tiles.append(tile)
    # 5 desert sage: grey-green round sprig cluster.
    tile = _blank(cell)
    sage = [pt.hexc(c) for c in ("#C9D3A6", "#A9B98E", "#8C9E7C")]
    for _ in range(140):
        a = rng.uniform(math.pi, 2 * math.pi)
        r = cell * 0.4 * math.sqrt(rng.random())
        cx, cy = cell / 2 + math.cos(a) * r, cell - 6 + math.sin(a) * r * 0.9
        m, _ = pt._leaf_shape(xx, yy, cx, cy, rng.uniform(7, 12), rng.uniform(3, 5), rng.uniform(0, 6.3), False)
        _stamp(tile, m, sage[int(rng.integers(0, 3))])
    tiles.append(tile)
    # 6 clover and leaf litter for the forest floor.
    tile = _blank(cell)
    for _ in range(26):
        cx, cy = rng.uniform(30, cell - 30), rng.uniform(cell * 0.45, cell - 10)
        _stroke(tile, xx, yy, cx, cell - 2, cx + rng.uniform(-6, 6), cy, 1.8, pt.hexc("#73985A"), 0.2)
        col = pt.hexc(["#8DB066", "#A9C878", "#73985A"][int(rng.integers(0, 3))])
        for k in range(3):
            a = k * 2 * math.pi / 3 + rng.uniform(-0.2, 0.2)
            m = np.clip((7.5 - np.hypot(xx - cx - math.cos(a) * 7, yy - cy - math.sin(a) * 7)) / 1.2, 0, 1)
            _stamp(tile, m, col)
    for _ in range(10):  # a few fallen leaves in warm palette tones
        cx, cy = rng.uniform(20, cell - 20), rng.uniform(cell * 0.8, cell - 6)
        m, _ = pt._leaf_shape(xx, yy, cx, cy, 11, 5, rng.uniform(-0.6, 0.6), True)
        _stamp(tile, m, pt.hexc(["#CDAE86", "#C8643A", "#E3AE45"][int(rng.integers(0, 3))]))
    tiles.append(tile)
    # 7 glow moss tufts (the material makes them glow; drawn pale so the glow reads).
    tile = _blank(cell)
    for _ in range(60):
        cx, cy = rng.uniform(20, cell - 20), rng.uniform(cell * 0.55, cell - 4)
        h = rng.uniform(12, 40)
        _stroke(tile, xx, yy, cx, cell - 2, cx + rng.uniform(-8, 8), cell - h, 3.0, pt.hexc("#9DB872"), 0.5)
        m = np.clip((5.5 - np.hypot(xx - cx, yy - (cell - h))) / 1.5, 0, 1)
        _stamp(tile, m, pt.hexc(["#E3AE45", "#F8E08A", "#7AC0E6"][int(rng.integers(0, 3))]))
    tiles.append(tile)
    return _pack(tiles, cell)


def _pack(tiles, cell):
    img = np.zeros((ROWS * cell, COLS * cell, 4))
    for k, tile in enumerate(tiles):
        ox, oy = (k % COLS) * cell, (k // COLS) * cell
        img[oy:oy + cell, ox:ox + cell] = tile
    img[..., 3] *= 255
    return np.clip(img, 0, 255).astype(np.uint8)


def char_bark(seed=97):
    """Charred bark: near-black warm wood with ember-orange cracks (Volcanic palette)."""
    rng = np.random.default_rng(seed)
    base = pt.ramp_map(0.45 + 0.4 * pt.fbm(rng, 6), ["#5E4644", "#4A2A1C", "#36221A", "#2A1A16", "#1E1412"])
    y = np.arange(pt.SIZE)[:, None] / pt.SIZE
    x = np.arange(pt.SIZE)[None, :] / pt.SIZE
    cracks = np.abs(np.sin(2 * math.pi * (x * 7 + 0.6 * pt.fbm(rng, 3)))) < 0.05
    cracks &= pt.fbm(rng, 8) > 0.5
    base[cracks] = base[cracks] * 0.3 + pt.hexc("#C8643A") * 0.7
    _ = y
    return np.clip(base, 0, 255).astype(np.uint8)


def all_textures():
    """Every texture the world foliage materials use: the island set plus the new atlases."""
    tex = {}
    tex.update(pt.paint_all())
    tex.update(pt.paint_extra())
    tex["flowers"] = pt.flower_atlas()
    tex["world_leaves"] = world_leaves()
    tex["world_plants"] = world_plants()
    tex["char_bark"] = char_bark()
    return tex


def texture_luma(arr):
    rgb = arr[..., :3].astype(float) / 255.0
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    if arr.shape[-1] == 4:
        a = arr[..., 3] > 128
        return float(lum[a].mean()) if a.any() else 0.6
    return float(lum.mean())


def write_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    tex = all_textures()
    for name, arr in tex.items():
        pt.save(arr, os.path.join(out_dir, f"{name}.png"))
    return tex
