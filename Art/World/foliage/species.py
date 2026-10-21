"""World foliage species, built the way the starter island's trees are (Art/TestIsland/foliage.py):

  * canopies are a few overlapping inflated SHELLS (inner ones smaller and darker) wrapped in cut-out
    LEAF-CLUMP CARDS, all with normals projected from the canopy centre so light wraps the canopy as
    one soft round form;
  * UV1 = (depth, height up the canopy), UV2 = (random, kind) feed the materials: dark inside,
    top-to-bottom gradient, per-card colour variation and wind phase;
  * trunks taper, flare at the root and curve.

Every builder takes a plan seed and a LOD (0..3). The plan (trunk path, canopy lobes) comes from its
own random stream, so every LOD of a variant has the same silhouette; only the detail thins out:

  LOD0  3 shell layers, fine outer shell, all cards, 8-sided trunk (close up)
  LOD1  2 layers, coarser shells, ~45% of the cards
  LOD2  one shell per lobe, ~15% of the cards, slightly inflated to keep the outline
  LOD3  one 20-triangle shell per lobe, no cards, 4-sided trunk: the HLOD / far-distance look

Coordinates are Unreal's (cm, Z up), pivot on the ground at the trunk root.
"""

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "TestIsland"))
import foliage as fo  # noqa: E402  island technique: Canopy, icosphere, outward winding
from make_island import Mesh, smoothstep  # noqa: E402
from textures import LEAF_CELL, PLANT_CELL, cell_uv  # noqa: E402

LODS = [
    dict(layers=3, sub_outer=2, sub_inner=1, cards=1.0, sides=8, inflate=1.0, limbs=True),
    dict(layers=2, sub_outer=1, sub_inner=1, cards=0.45, sides=6, inflate=1.03, limbs=True),
    dict(layers=1, sub_outer=1, sub_inner=1, cards=0.15, sides=5, inflate=1.07, limbs=True),
    dict(layers=1, sub_outer=0, sub_inner=0, cards=0.0, sides=4, inflate=1.10, limbs=False),
]
_ICO = {k: fo.icosphere(k) for k in range(3)}


def rngs(seed):
    """(plan stream, detail stream): the plan is identical for every LOD."""
    return np.random.default_rng(seed), np.random.default_rng(seed + 7919)


# ----------------------------------------------------------------------------- canopy

def shells(mesh, mat, canopy, lod, lump_seed, max_layers=3, kind=0.0):
    """Inflated shells (fo.canopy_shells with LOD control). Lower LODs keep only the outer shell."""
    L = LODS[lod]
    part = mesh.part(mat)
    layers = max(1, min(L["layers"], max_layers))
    for layer in range(layers):
        depth = layer / (layers - 1) if layers > 1 else 0.85
        scale = (0.62 + 0.38 * depth) if layers > 1 else L["inflate"]
        verts, faces = _ICO[L["sub_outer"] if layer == layers - 1 else L["sub_inner"]]
        rand = (lump_seed * 0.618 + layer * 0.37) % 1.0
        ids = []
        for v in verts:
            lump = 0.10 * math.sin(v[0] * 5 + lump_seed) * math.cos(v[1] * 4 + lump_seed) \
                + 0.06 * math.sin(v[2] * 7 + lump_seed)
            p = canopy.surface(v, scale, lump)
            n = canopy.normal(p)
            n = n / np.linalg.norm(n)
            ids.append(part.vert(p, n, (p[0] / 150.0, p[2] / 150.0 + p[1] / 300.0),
                                 uv1=(depth * 0.8, canopy.height01(p)), uv2=(rand, kind)))
        for f in faces:
            fo._add_tri_outward(part, [ids[k] for k in f], np.array(part.pos[ids[f[0]]]) - canopy.centre)


def cards(mesh, mat, canopy, D, lod, count, size, cell, droop=0.0, under=0.25):
    """Leaf-clump cards over the canopy (fo.canopy_cards with LOD control and the 4 x 2 atlas)."""
    n_cards = int(round(count * LODS[lod]["cards"]))
    if n_cards <= 0:
        return
    if lod > 0:
        size *= 1.0 + 0.25 * lod  # fewer, bigger cards keep the fringe readable at a distance
    part = mesh.part(mat)
    u0, v0, du, dv = cell_uv(cell)
    for _ in range(n_cards):
        while True:
            v = D.normal(size=3)
            v /= np.linalg.norm(v)
            if v[2] > -0.45 or D.random() < under:
                break
        p = canopy.surface(v, D.uniform(1.0, 1.12))
        n = canopy.normal(p)
        n /= np.linalg.norm(n)
        s = size * D.uniform(0.75, 1.25)
        t = np.cross(n, [0, 0, 1.0])
        if np.linalg.norm(t) < 1e-3:
            t = np.array([1.0, 0, 0])
        t /= np.linalg.norm(t)
        b = np.cross(n, t)
        spin = D.uniform(0, 2 * math.pi)
        t, b = t * math.cos(spin) + b * math.sin(spin), -t * math.sin(spin) + b * math.cos(spin)
        tilt = n * 0.75 + np.array([0, 0, -droop])
        corners = [p + (-t - b) * s / 2 - tilt * s * 0.2, p + (t - b) * s / 2 - tilt * s * 0.2,
                   p + (t + b) * s / 2 + tilt * s * 0.2, p + (-t + b) * s / 2 + tilt * s * 0.2]
        uvs = [(u0, v0 + dv), (u0 + du, v0 + dv), (u0 + du, v0), (u0, v0)]
        rand = D.random()
        ids = [part.vert(c, n, uv, uv1=(1.0, canopy.height01(c)), uv2=(rand, 1.0)) for c, uv in zip(corners, uvs)]
        part.tri(ids[0], ids[1], ids[2])
        part.tri(ids[0], ids[2], ids[3])


def canopy(mesh, species, lobe, D, lod, lump_seed, card_count, card_size, cell, max_layers=3, droop=0.0):
    shells(mesh, f"shell_{species}", lobe, lod, lump_seed, max_layers)
    cards(mesh, f"cards_{species}", lobe, D, lod, card_count, card_size, cell, droop)


# ----------------------------------------------------------------------------- trunks

def limb(mesh, mat, points, radii, sides):
    """Tapered tube along points (fo.tapered_limb with a side count)."""
    rings = []
    for k, (p, r) in enumerate(zip(points, radii)):
        p = np.array(p, dtype=float)
        d = np.array(points[min(k + 1, len(points) - 1)], float) - np.array(points[max(k - 1, 0)], float)
        d = d / (np.linalg.norm(d) or 1)
        side = np.cross(d, [0, 0, 1.0]) if abs(d[2]) < 0.95 else np.array([1.0, 0, 0])
        side /= np.linalg.norm(side)
        up = np.cross(side, d)
        rings.append([(p + (side * math.cos(a) + up * math.sin(a)) * r, side * math.cos(a) + up * math.sin(a))
                      for a in np.linspace(0, 2 * math.pi, sides, endpoint=False)])
    part = mesh.part(mat)
    for k in range(len(rings) - 1):
        for s in range(sides):
            s1 = (s + 1) % sides
            quad = [rings[k][s], rings[k][s1], rings[k + 1][s1], rings[k + 1][s]]
            ids = [part.vert(p, n, (s / sides, (k + (j >= 2)) * 0.5)) for j, (p, n) in enumerate(quad)]
            outward = sum(n for _, n in quad) / 4
            fo._add_tri_outward(part, [ids[0], ids[1], ids[2]], outward)
            fo._add_tri_outward(part, [ids[0], ids[2], ids[3]], outward)


def trunk_path(height, lean, curve, segments=5, sink=25.0, wobble=0.0, P=None):
    """Points of a curving trunk from the root (sunk `sink` cm) to the crown."""
    pts = []
    for k in range(segments):
        f = k / (segments - 1)
        off = np.array([lean[0] * f ** 1.6, lean[1] * f ** 1.6, height * f - sink])
        off[0] += curve * math.sin(f * math.pi) * 0.5
        if wobble and P is not None and 0 < k < segments - 1:
            off[:2] += P.uniform(-wobble, wobble, 2)
        pts.append(off)
    return pts


def draw_trunk(mesh, mat, pts, r_base, r_top, lod, flare=0.6):
    """Draws a planned trunk; low LODs drop every other ring."""
    if lod >= 2 and len(pts) > 3:
        pts = [pts[0], pts[len(pts) // 2], pts[-1]]
    radii = []
    for k in range(len(pts)):
        f = k / (len(pts) - 1)
        radii.append((r_base + (r_top - r_base) * f) * (1.0 + flare * max(0.0, 1.0 - f * 4.0) ** 2))
    limb(mesh, mat, pts, radii, LODS[lod]["sides"])


def card_count(lobe, k, s):
    area = lobe.radii[0] * lobe.radii[2] / (200 * 150)
    return int(k * area * s) + 8


# ----------------------------------------------------------------------------- broadleaf trees

def oak(seed, lod, s=1.0, species="oak", lobes=(2, 4), height=340, spread=170, cell="broadleaf",
        bark="bark", flat=1.0):
    """The island oak: curved trunk, a round main canopy and asymmetric side lobes on limbs."""
    P, D = rngs(seed)
    m = Mesh()
    pts = trunk_path(height * s, (P.uniform(-45, 45) * s, P.uniform(-45, 45) * s), P.uniform(-30, 30) * s)
    main = fo.Canopy(pts[-1] + np.array([0, 0, 120 * s]), np.array([230, 220, 165 * flat]) * s)
    plan = [(main, None)]
    for _ in range(int(P.integers(*lobes))):
        a = P.uniform(0, 2 * math.pi)
        c = main.centre + np.array([math.cos(a) * spread * s, math.sin(a) * spread * s, P.uniform(-60, 30) * s])
        lobe = fo.Canopy(c, np.array([130, 125, 100 * flat]) * s * P.uniform(0.85, 1.1))
        start = pts[2] + np.array([0, 0, P.uniform(0, 40) * s])
        plan.append((lobe, start))
    draw_trunk(m, bark, pts, 34 * s, 16 * s, lod)
    for k, (lobe, start) in enumerate(plan):
        if start is not None and LODS[lod]["limbs"]:
            c = lobe.centre
            mid = (start + c) / 2 + np.array([0, 0, 40 * s])
            limb(m, bark, [start, mid, c - np.array([0, 0, 40 * s])], [13 * s, 9 * s, 6 * s],
                 max(4, LODS[lod]["sides"] - 2))
        canopy(m, species, lobe, D, lod, seed * 0.13 + k, card_count(lobe, 46, s), 120 * s, LEAF_CELL[cell])
    return m


def birch(seed, lod, s=1.0):
    P, D = rngs(seed)
    m = Mesh()
    pts = trunk_path(470 * s, (P.uniform(-60, 60) * s, P.uniform(-60, 60) * s), P.uniform(-40, 40) * s, sink=20)
    draw_trunk(m, "birch_bark", pts, 18 * s, 9 * s, lod, flare=0.4)
    lobes = []
    for k in range(int(P.integers(3, 5))):
        c = pts[-1] + np.array([P.uniform(-50, 50) * s, P.uniform(-50, 50) * s, (-170 + k * 90) * s])
        lobes.append(fo.Canopy(c, np.array([120, 115, 95]) * s * (1.12 - k * 0.16)))
    for k, lobe in enumerate(lobes):
        canopy(m, "birch", lobe, D, lod, seed * 0.17 + k, int(26 * s) + 8, 90 * s, LEAF_CELL["birch"], max_layers=2)
    return m


def cherry(seed, lod, s=1.0):
    """Greengrace cherry: low, wide, leaning crown of blossom lobes on a dark twisting trunk."""
    return oak(seed, lod, s, species="cherry", lobes=(3, 5), height=260, spread=200, cell="blossom", flat=0.8)


def blossom(seed, lod, s=1.3):
    """The island's accent tree (the one over the bench): an oak form in blossom."""
    return oak(seed, lod, s, species="blossom", cell="blossom")


def olive(seed, lod, s=1.0):
    """Sunreach plains: short gnarled split trunk, flattened silvery lobes."""
    P, D = rngs(seed)
    m = Mesh()
    lobes = []
    for k in range(2):  # two leaders twisting apart
        a = P.uniform(0, 2 * math.pi)
        lean = (math.cos(a) * 90 * s, math.sin(a) * 90 * s)
        pts = trunk_path(230 * s, lean, P.uniform(-40, 40) * s, segments=5, sink=20, wobble=18 * s, P=P)
        draw_trunk(m, "olive_bark", pts, (26 if k == 0 else 20) * s, 9 * s, lod, flare=0.8)
        top = pts[-1]
        lobes.append(fo.Canopy(top + np.array([0, 0, 60 * s]), np.array([170, 160, 85]) * s * P.uniform(0.9, 1.1)))
        for j in range(int(P.integers(1, 3))):
            b = P.uniform(0, 2 * math.pi)
            lobes.append(fo.Canopy(top + np.array([math.cos(b) * 110 * s, math.sin(b) * 110 * s,
                                                   P.uniform(-10, 50) * s]),
                                   np.array([110, 105, 60]) * s))
    for k, lobe in enumerate(lobes):
        canopy(m, "olive", lobe, D, lod, seed * 0.11 + k, card_count(lobe, 40, s), 90 * s, LEAF_CELL["olive"])
    return m


def darkwood(seed, lod, s=1.0):
    """Sunreach's dark forest: tall twisted sycamore-like tree, big limbs, dark crown held high."""
    P, D = rngs(seed)
    m = Mesh()
    pts = trunk_path(720 * s, (P.uniform(-90, 90) * s, P.uniform(-90, 90) * s), P.uniform(-90, 90) * s,
                     segments=7, sink=30, wobble=25 * s, P=P)
    draw_trunk(m, "dark_bark", pts, 46 * s, 18 * s, lod, flare=0.9)
    lobes = [fo.Canopy(pts[-1] + np.array([0, 0, 110 * s]), np.array([250, 240, 150]) * s)]
    limbs = []
    for k in range(int(P.integers(3, 5))):
        a = P.uniform(0, 2 * math.pi) + k * 1.7
        start = pts[int(P.integers(3, 5))]
        c = start + np.array([math.cos(a) * 260 * s, math.sin(a) * 260 * s, P.uniform(120, 260) * s])
        lobes.append(fo.Canopy(c, np.array([160, 150, 110]) * s * P.uniform(0.85, 1.15)))
        limbs.append((start, c))
    if LODS[lod]["limbs"]:
        for start, c in limbs:
            mid = start * 0.45 + c * 0.55 + np.array([0, 0, -40 * s])
            limb(m, "dark_bark", [start, mid, c - np.array([0, 0, 50 * s])], [17 * s, 11 * s, 6 * s],
                 max(4, LODS[lod]["sides"] - 2))
    for k, lobe in enumerate(lobes):
        canopy(m, "darkwood", lobe, D, lod, seed * 0.19 + k, card_count(lobe, 44, s), 130 * s,
               LEAF_CELL["broadleaf"])
    return m


def cypress(seed, lod, s=1.0):
    """Tall columnar cypress for the dark forest's edges: a gently twisting flame of stacked lobes."""
    P, D = rngs(seed)
    m = Mesh()
    height = 900 * s
    pts = trunk_path(height * 0.55, (P.uniform(-30, 30) * s, P.uniform(-30, 30) * s), P.uniform(-30, 30) * s,
                     segments=5, sink=20)
    draw_trunk(m, "dark_bark", pts, 24 * s, 10 * s, lod, flare=0.5)
    n = int(P.integers(5, 7))
    twist = P.uniform(-1, 1)
    for k in range(n):
        f = k / (n - 1)
        r = (125 - 75 * f) * s
        c = np.array([math.sin(f * 3.0 + twist) * 30 * s, math.cos(f * 2.3 + twist) * 30 * s,
                      190 * s + f * (height - 300 * s)])
        lobe = fo.Canopy(c, (r, r, (150 - 30 * f) * s), pointy=0.35 if k == n - 1 else 0.0)
        canopy(m, "cypress", lobe, D, lod, seed * 0.23 + k, int(30 * (1.2 - f * 0.5) * s) + 6, 100 * s,
               LEAF_CELL["cypress"], max_layers=2)
    return m


# ----------------------------------------------------------------------------- conifers

def pine(seed, lod, s=1.0, species="pine", tiers=5, cell="pine"):
    """Tiered conifer: overlapping drooping tiers, wide at the bottom, a pointed tip over the trunk."""
    P, D = rngs(seed)
    m = Mesh()
    height = 620 * s * (0.85 + 0.06 * tiers)
    pts = trunk_path(height * 0.9, (P.uniform(-20, 20) * s, P.uniform(-20, 20) * s), 0.0, segments=6, sink=20)
    draw_trunk(m, "pine_bark", pts, 24 * s, 7 * s, lod, flare=0.5)
    z0, z1 = 160 * s, height * 0.86
    for k in range(tiers):
        f = k / (tiers - 1)
        c = np.array([P.uniform(-12, 12) * s, P.uniform(-12, 12) * s, z0 + f * (z1 - z0)])
        r = (205 - f * 150) * s * P.uniform(0.85, 1.15)
        tier = fo.Canopy(c, (r * P.uniform(0.9, 1.1), r * P.uniform(0.9, 1.1), (145 - f * 50) * s),
                         pointy=0.9 if k == tiers - 1 else 0.6)
        canopy(m, species, tier, D, lod, seed * 0.29 + k, int(46 * (1.2 - f * 0.6) * s) + 8, 105 * s,
               LEAF_CELL[cell], max_layers=2, droop=0.5)
    return m


def snowpine(seed, lod, s=1.0, tiers=6):
    """Snowy north: the island pine with frost-tipped tufts; its shell material dusts the tops white."""
    return pine(seed, lod, s, species="snowpine", tiers=tiers, cell="frost")


# ----------------------------------------------------------------------------- dead and burnt

def deadtree(seed, lod, s=1.0):
    """Volcanic ground: a charred trunk with crooked bare branches (no canopy)."""
    P, _ = rngs(seed)
    m = Mesh()
    pts = trunk_path(520 * s, (P.uniform(-70, 70) * s, P.uniform(-70, 70) * s), P.uniform(-60, 60) * s,
                     segments=6, sink=25, wobble=20 * s, P=P)
    draw_trunk(m, "char_bark", pts, 30 * s, 6 * s, lod, flare=0.7)
    sides = max(3, LODS[lod]["sides"] - 3)

    def branch(start, direction, length, radius, depth):
        path = [start]
        d = direction / np.linalg.norm(direction)
        for _ in range(3):
            d = d + P.normal(size=3) * 0.25 + np.array([0, 0, 0.12])
            d /= np.linalg.norm(d)
            path.append(path[-1] + d * length / 3)
        if depth <= lod_depth:
            limb(m, "char_bark", path, [radius, radius * 0.6, radius * 0.35, radius * 0.15], sides)
        if depth < 2:
            for _ in range(2):
                b = P.normal(size=3)
                b[2] = abs(b[2]) * 0.6
                branch(path[2], d + b * 0.8, length * 0.55, radius * 0.5, depth + 1)

    lod_depth = 2 - min(lod, 2)  # far LODs keep only the main limbs
    for k in range(int(P.integers(3, 5))):
        a = P.uniform(0, 2 * math.pi)
        start = pts[int(P.integers(2, 5))]
        branch(start, np.array([math.cos(a), math.sin(a), P.uniform(0.3, 0.9)]), P.uniform(160, 260) * s, 10 * s, 0)
    return m


# ----------------------------------------------------------------------------- shrubs

def bush(seed, lod, s=1.0, species="bush", cell="broadleaf", berries=False, wide=1.0, n_lobes=1):
    P, D = rngs(seed)
    m = Mesh()
    lobes = []
    for k in range(n_lobes):
        a = P.uniform(0, 2 * math.pi)
        off = np.array([math.cos(a), math.sin(a), 0]) * (70 * s * (k > 0))
        lobes.append(fo.Canopy(np.array([0, 0, 50 * s]) + off, np.array([120 * wide, 110, 70]) * s * P.uniform(0.8, 1.0)))
    for k, lobe in enumerate(lobes):
        canopy(m, species, lobe, D, min(lod, 3), seed * 0.31 + k, int(22 * s * wide) + 6, 75 * s, LEAF_CELL[cell],
               max_layers=2)
    if berries and lod < 2:
        part = m.part("berry")
        verts, faces = _ICO[1 if lod == 0 else 0]
        for _ in range(int(P.integers(6, 11))):
            v = P.normal(size=3)
            v[2] = abs(v[2]) * 0.6
            v /= np.linalg.norm(v)
            centre = lobes[0].surface(v, 1.02)
            ids = [part.vert(centre + np.array(w) * 6.5 * s, w, (0, 0)) for w in verts]
            for f in faces:
                fo._add_tri_outward(part, [ids[k] for k in f], np.array(part.pos[ids[f[0]]]) - centre)
    return m


def frostshrub(seed, lod, s=1.0):
    return bush(seed, lod, s, species="frostshrub", cell="frost", wide=1.15, n_lobes=2)


def scrub(seed, lod, s=1.0):
    """Saltreach badlands: low thorny scrub, a few dusty leaf puffs in a spray of thorny twig cards."""
    P, D = rngs(seed)
    m = Mesh()
    for k in range(int(P.integers(2, 4))):
        a = P.uniform(0, 2 * math.pi)
        c = np.array([math.cos(a) * 45 * s, math.sin(a) * 45 * s, (35 + 20 * k) * s])
        lobe = fo.Canopy(c, np.array([70, 65, 45]) * s)
        shells(m, "shell_scrub", lobe, min(lod + 1, 3), seed * 0.37 + k, max_layers=1)
        cards(m, "cards_scrub", fo.Canopy(c, np.array([110, 105, 70]) * s), D, lod, 18, 85 * s, LEAF_CELL["thorn"],
              under=0.5)
    return m


def sage(seed, lod, s=1.0):
    """Desert shrub: a small round grey-green sage."""
    return bush(seed, lod, s * 0.7, species="sage", cell="olive", wide=1.0)


def plant_clump(seed, lod, s, kind, mat, n_cards=8, size=80.0, radius=35.0, splay=0.25):
    """A clump of upright crossed cards from the plant atlas (lavender, reeds, ferns, moss)."""
    P, _ = rngs(seed)
    m = Mesh()
    part = m.part(mat)
    u0, v0, du, dv = cell_uv(PLANT_CELL[kind])
    n_cards = max(2, int(round(n_cards * (1.0, 0.6, 0.35, 0.25)[lod])))
    for _ in range(n_cards):
        a, r = P.uniform(0, 2 * math.pi), radius * s * math.sqrt(P.random())
        x, y = math.cos(a) * r, math.sin(a) * r
        h = size * s * P.uniform(0.75, 1.2)
        yaw = P.uniform(0, math.pi)
        lean = np.array([math.cos(a), math.sin(a), 0]) * h * splay * (r / (radius * s + 1e-6))
        dx, dy = math.cos(yaw) * h / 2, math.sin(yaw) * h / 2
        up = (0, 0, 1)
        q = [part.vert((x - dx, y - dy, -3), up, (u0, v0 + dv), uv1=(0, 0)),
             part.vert((x + dx, y + dy, -3), up, (u0 + du, v0 + dv), uv1=(0, 0)),
             part.vert((x + dx + lean[0], y + dy + lean[1], h), up, (u0 + du, v0), uv1=(0, 1)),
             part.vert((x - dx + lean[0], y - dy + lean[1], h), up, (u0, v0), uv1=(0, 1))]
        part.tri(q[0], q[1], q[2])
        part.tri(q[0], q[2], q[3])
    return m


def lavender(seed, lod, s=1.0):
    return plant_clump(seed, lod, s, "lavender", "plant", n_cards=16, size=70, radius=45)


def reeds(seed, lod, s=1.0):
    return plant_clump(seed, lod, s, "reed", "plant", n_cards=9, size=190, radius=55, splay=0.12)


def fern(seed, lod, s=1.0):
    return plant_clump(seed, lod, s, "fern", "plant", n_cards=7, size=85, radius=30, splay=0.45)


def mushrooms(seed, lod, s=1.0):
    """The island's mushroom cluster (stem + cap), for shady forest floor."""
    P, _ = rngs(seed)
    m = Mesh()
    part = m.part("mushroom")
    verts, faces = _ICO[1 if lod == 0 else 0]
    sides = 6 if lod == 0 else 4
    for _ in range(int(P.integers(3, 7))):
        mx, my = P.uniform(-45, 45) * s, P.uniform(-45, 45) * s
        h, r = P.uniform(10, 22) * s, P.uniform(5, 10) * s
        stem_r = r * 0.32
        for k in range(sides):
            a0, a1 = 2 * math.pi * k / sides, 2 * math.pi * (k + 1) / sides
            d0 = np.array([math.cos(a0), math.sin(a0), 0])
            d1 = np.array([math.cos(a1), math.sin(a1), 0])
            p = [np.array([mx, my, -2]) + d0 * stem_r, np.array([mx, my, -2]) + d1 * stem_r,
                 np.array([mx, my, h]) + d1 * stem_r * 0.8, np.array([mx, my, h]) + d0 * stem_r * 0.8]
            ids = [part.vert(q, (d0 + d1) / 2, (0, 0)) for q in p]
            fo._add_tri_outward(part, ids[:3], d0 + d1)
            fo._add_tri_outward(part, [ids[0], ids[2], ids[3]], d0 + d1)
        centre = np.array([mx, my, h])
        ids = []
        for w in verts:
            q = np.array([w[0] * r, w[1] * r, (w[2] * r * 0.7) if w[2] > 0 else w[2] * r * 0.15])
            ids.append(part.vert(centre + q, w, (0, 0)))
        for f in faces:
            fo._add_tri_outward(part, [ids[k] for k in f], np.array(part.pos[ids[f[0]]]) - centre)
    return m


# ----------------------------------------------------------------------------- minerals

def _faceted(m, mat, centre, size, P, flatten=0.35, col_fn=None):
    """A faceted Genshin-style rock chunk (make_island.rock_chunk with a seeded stream)."""
    t = (1 + 5 ** 0.5) / 2
    base = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
            (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    faces = _ICO[0][1]
    yaw = P.uniform(0, 2 * math.pi)
    cy, sy = math.cos(yaw), math.sin(yaw)
    pts = []
    for v in base:
        v = np.array(v, dtype=float) / math.sqrt(1 + t * t)
        v = v * (1 + P.uniform(-0.22, 0.22))
        v = np.array([v[0] * cy - v[1] * sy, v[0] * sy + v[1] * cy, v[2]])
        if v[2] > flatten:
            v[2] = flatten + (v[2] - flatten) * 0.4
        pts.append(np.array(centre, float) + v * np.array(size))
    for a, b, c in faces:
        m.flat_tri(mat, pts[a], pts[b], pts[c], (pts[a] + pts[b] + pts[c]) / 3 - np.array(centre, float), col_fn)


def _grass_top(n):
    return (float(np.clip(smoothstep(0.72, 0.92, n[2]), 0, 1)), 0.0, 0.0, 1.0)


def rock(seed, lod, s=1.0):
    """A 1-2 m faceted rock, sunk a little, grass on its flat top."""
    P, _ = rngs(seed)
    m = Mesh()
    r = 90 * s
    _faceted(m, "rock", (0, 0, r * 0.15), (r, r * P.uniform(0.75, 1.0), r * P.uniform(0.5, 0.75)), P, col_fn=_grass_top)
    return m


def boulder(seed, lod, s=1.0):
    """A 3-6 m boulder cluster: one big chunk leaning on one or two smaller ones."""
    P, _ = rngs(seed)
    m = Mesh()
    r = 260 * s
    _faceted(m, "rock", (0, 0, r * 0.2), (r, r * P.uniform(0.7, 0.95), r * P.uniform(0.55, 0.8)), P, col_fn=_grass_top)
    for _ in range(int(P.integers(1, 3)) if lod < 3 else 0):
        a = P.uniform(0, 2 * math.pi)
        rr = r * P.uniform(0.35, 0.55)
        _faceted(m, "rock", (math.cos(a) * r * 0.9, math.sin(a) * r * 0.9, rr * 0.1),
                 (rr, rr * 0.9, rr * 0.7), P, col_fn=_grass_top)
    return m


def pebbles(seed, lod, s=1.0):
    P, _ = rngs(seed)
    m = Mesh()
    for _ in range(int(P.integers(4, 8)) if lod == 0 else 3):
        a, d = P.uniform(0, 2 * math.pi), P.uniform(0, 60) * s
        r = P.uniform(8, 22) * s
        _faceted(m, "rock", (math.cos(a) * d, math.sin(a) * d, r * 0.1), (r, r * 0.9, r * 0.6), P, col_fn=_grass_top)
    return m


def crystals(seed, lod, s=1.0):
    """Salt flats and the Glass Dunes: a cluster of salt-white hexagonal crystals, pointed tips."""
    P, _ = rngs(seed)
    m = Mesh()
    n = int(P.integers(4, 9)) if lod < 2 else 3
    for k in range(n):
        h = P.uniform(40, 150) * s * (1.3 if k == 0 else 1.0)
        r = h * P.uniform(0.12, 0.2)
        a = P.uniform(0, 2 * math.pi)
        base = np.array([math.cos(a), math.sin(a), 0]) * P.uniform(0, 50) * s * (k > 0) + np.array([0, 0, -10.0])
        axis = np.array([P.uniform(-0.45, 0.45), P.uniform(-0.45, 0.45), 1.0])
        axis /= np.linalg.norm(axis)
        side = np.cross(axis, [0, 1.0, 0])
        side /= np.linalg.norm(side)
        up = np.cross(side, axis)
        ring = [base + (side * math.cos(t) + up * math.sin(t)) * r for t in np.linspace(0, 2 * math.pi, 6, endpoint=False)]
        top = [p + axis * h * 0.75 for p in ring]
        tip = base + axis * h
        for i in range(6):
            j = (i + 1) % 6
            for tri in ((ring[i], ring[j], top[j]), (ring[i], top[j], top[i]), (top[i], top[j], tip)):
                m.flat_tri("crystal", *tri, (tri[0] + tri[1] + tri[2]) / 3 - (base + axis * h * 0.5))
    return m


def ventmoss(seed, lod, s=1.0):
    """Volcanic vents: a low dark mound with tufts of softly glowing moss."""
    P, _ = rngs(seed)
    m = Mesh()
    _faceted(m, "vent_rock", (0, 0, -15 * s), (110 * s, 100 * s, 35 * s), P, flatten=0.2)
    clump = plant_clump(seed + 1, lod, s, "moss", "moss", n_cards=8, size=40, radius=80, splay=0.3)
    m.parts["moss"] = clump.parts["moss"]
    return m


# ----------------------------------------------------------------------------- grass-type meshes

def grass_clump(seed, lod, s=1.0, blades=7, height=(20, 42)):
    """Island-style tapered grass blades (UV v: 0 root .. 1 tip), for the landscape grass types."""
    P, _ = rngs(seed)
    m = Mesh()
    part = m.part("grass")
    blades = max(3, int(blades * (1.0, 0.6, 0.4, 0.3)[lod]))
    base_h = P.uniform(*height) * s
    up = (0, 0, 1)
    for _ in range(blades):
        bx, by = P.uniform(-14, 14) * s, P.uniform(-14, 14) * s
        yaw, lean = P.uniform(0, 2 * math.pi), P.uniform(-0.35, 0.35)
        hh, w = base_h * P.uniform(0.7, 1.15), P.uniform(5, 8) * s
        dx, dy = math.cos(yaw) * w / 2, math.sin(yaw) * w / 2
        lx, ly = -math.sin(yaw) * lean * hh, math.cos(yaw) * lean * hh
        v0 = part.vert((bx - dx, by - dy, -3), up, (0, 0))
        v1 = part.vert((bx + dx, by + dy, -3), up, (1, 0))
        if lod == 0:
            v2 = part.vert((bx + dx * 0.6 + lx * 0.4, by + dy * 0.6 + ly * 0.4, hh * 0.5), up, (1, 0.5))
            v3 = part.vert((bx - dx * 0.6 + lx * 0.4, by - dy * 0.6 + ly * 0.4, hh * 0.5), up, (0, 0.5))
            v4 = part.vert((bx + lx, by + ly, hh), up, (0.5, 1))
            part.tri(v0, v1, v2)
            part.tri(v0, v2, v3)
            part.tri(v3, v2, v4)
        else:
            v4 = part.vert((bx + lx, by + ly, hh), up, (0.5, 1))
            part.tri(v0, v1, v4)
    return m


def flower_clump(seed, lod, s=1.0, colour=0):
    """A loose clump of 3-5 wildflowers (flowers.png: 0 cream, 1 pink, 2 butter, 3 lavender)."""
    P, _ = rngs(seed)
    m = Mesh()
    part = m.part("flower")
    u0, v0 = (colour % 2) * 0.5, (colour // 2) * 0.5
    for _ in range(int(P.integers(3, 6)) if lod == 0 else 2):
        x, y = P.uniform(-30, 30) * s, P.uniform(-30, 30) * s
        size = P.uniform(22, 34) * s
        z0 = P.uniform(8, 18) * s
        yaw = P.uniform(0, math.pi)
        for ang in ((yaw, yaw + math.pi / 2) if lod == 0 else (yaw,)):
            dx, dy = math.cos(ang) * size / 2, math.sin(ang) * size / 2
            q = [part.vert((x - dx, y - dy, z0), (0, 0, 1), (u0, v0 + 0.5)),
                 part.vert((x + dx, y + dy, z0), (0, 0, 1), (u0 + 0.5, v0 + 0.5)),
                 part.vert((x + dx, y + dy, z0 + size), (0, 0, 1), (u0 + 0.5, v0)),
                 part.vert((x - dx, y - dy, z0 + size), (0, 0, 1), (u0, v0))]
            part.tri(q[0], q[1], q[2])
            part.tri(q[0], q[2], q[3])
    return m


def tuft(seed, lod, s=1.0, kind="dune", mat="plant", size=60):
    return plant_clump(seed, lod, s, kind, mat, n_cards=3, size=size, radius=12, splay=0.3)


# ----------------------------------------------------------------------------- the catalogue
# group: "trees" (big, kept in the far HLOD), "understory" (no HLOD), "grass" (landscape grass types).
# cull: (start fade, end) in metres. nanite: opaque, no wind (rocks, crystals, dead trees).
# collision: "trunk" (bark sections only), "complex" (the whole mesh), None.

SPECIES = {
    "oak":        dict(fn=oak, group="trees", variants=[(11, 1.0), (12, 1.15), (13, 0.85)], cull=(3800, 4200), collision="trunk"),
    "birch":      dict(fn=birch, group="trees", variants=[(21, 1.0), (22, 1.1), (23, 0.85)], cull=(3800, 4200), collision="trunk"),
    "pine":       dict(fn=pine, group="trees", variants=[(31, 1.0), (32, 1.15), (33, 0.85)], cull=(3800, 4200), collision="trunk"),
    "blossom":    dict(fn=blossom, group="trees", variants=[(41, 1.3), (42, 1.1)], cull=(3800, 4200), collision="trunk"),
    "cherry":     dict(fn=cherry, group="trees", variants=[(51, 1.0), (52, 0.9), (53, 1.1)], cull=(3800, 4200), collision="trunk"),
    "snowpine":   dict(fn=snowpine, group="trees", variants=[(61, 1.0), (62, 1.2), (63, 0.8)], cull=(3800, 4200), collision="trunk"),
    "cypress":    dict(fn=cypress, group="trees", variants=[(71, 1.0), (72, 1.15), (73, 0.85)], cull=(3800, 4200), collision="trunk"),
    "darkwood":   dict(fn=darkwood, group="trees", variants=[(81, 1.0), (82, 1.12), (83, 0.9)], cull=(3800, 4200), collision="trunk"),
    "olive":      dict(fn=olive, group="trees", variants=[(91, 1.0), (92, 1.1), (93, 0.85)], cull=(3800, 4200), collision="trunk"),
    "deadtree":   dict(fn=deadtree, group="trees", variants=[(101, 1.0), (102, 1.2), (103, 0.8)], cull=(3800, 4200), collision="trunk", nanite=True),
    "boulder":    dict(fn=boulder, group="trees", variants=[(111, 1.0), (112, 1.4), (113, 0.8)], cull=(3800, 4200), collision="complex", nanite=True),
    "bush":       dict(fn=bush, group="understory", variants=[(121, 1.0), (122, 0.85), (123, 1.15)], cull=(260, 320), collision=None,
                       kwargs=[{}, {"berries": True}, {"wide": 1.3, "n_lobes": 2}]),
    "frostshrub": dict(fn=frostshrub, group="understory", variants=[(131, 1.0), (132, 0.8)], cull=(260, 320), collision=None),
    "scrub":      dict(fn=scrub, group="understory", variants=[(141, 1.0), (142, 0.8), (143, 1.2)], cull=(260, 320), collision=None),
    "sage":       dict(fn=sage, group="understory", variants=[(151, 1.0), (152, 0.8)], cull=(200, 250), collision=None),
    "lavender":   dict(fn=lavender, group="understory", variants=[(161, 1.0), (162, 0.85)], cull=(150, 190), collision=None),
    "reeds":      dict(fn=reeds, group="understory", variants=[(171, 1.0), (172, 0.8)], cull=(180, 220), collision=None),
    "fern":       dict(fn=fern, group="understory", variants=[(181, 1.0), (182, 1.25)], cull=(120, 150), collision=None),
    "mushrooms":  dict(fn=mushrooms, group="understory", variants=[(191, 1.0), (192, 1.4)], cull=(70, 90), collision=None),
    "rock":       dict(fn=rock, group="understory", variants=[(201, 1.0), (202, 0.7), (203, 1.3)], cull=(400, 500), collision="complex", nanite=True),
    "pebbles":    dict(fn=pebbles, group="understory", variants=[(211, 1.0), (212, 1.3)], cull=(90, 120), collision=None, nanite=True),
    "crystals":   dict(fn=crystals, group="understory", variants=[(221, 1.0), (222, 1.3), (223, 0.75)], cull=(400, 500), collision="complex", nanite=True),
    "ventmoss":   dict(fn=ventmoss, group="understory", variants=[(231, 1.0), (232, 1.3)], cull=(250, 300), collision=None),
    # Landscape grass type meshes (GT_Meadow, GT_Forest, GT_Dune); cull distances live on the grass types.
    "grass":      dict(fn=grass_clump, group="grass", variants=[(301, 1.0), (302, 1.35)], lods=2),
    "wheat":      dict(fn=tuft, group="grass", variants=[(311, 1.0)], lods=2, kwargs=[{"kind": "wheat", "mat": "wheat", "size": 75}]),
    "flower":     dict(fn=flower_clump, group="grass", variants=[(321, 1.0), (322, 1.0), (323, 1.0), (324, 1.0)], lods=2,
                       kwargs=[{"colour": 0}, {"colour": 1}, {"colour": 2}, {"colour": 3}]),
    "dune":       dict(fn=tuft, group="grass", variants=[(331, 1.0), (332, 1.2)], lods=2, kwargs=[{"kind": "dune", "size": 65}] * 2),
    "groundfern": dict(fn=tuft, group="grass", variants=[(341, 1.0)], lods=2, kwargs=[{"kind": "fern", "size": 55}]),
    "clover":     dict(fn=tuft, group="grass", variants=[(351, 1.0)], lods=2, kwargs=[{"kind": "clover", "size": 30}]),
}
VARIANT_LETTERS = "ABCD"


def variant_name(species, k):
    return f"SM_{species.capitalize()}_{VARIANT_LETTERS[k]}"


def build(species, k, lod):
    spec = SPECIES[species]
    seed, scale = spec["variants"][k]
    kwargs = (spec.get("kwargs") or [{}] * len(spec["variants"]))[k]
    return spec["fn"](seed, lod, scale, **kwargs)
