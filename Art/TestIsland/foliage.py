"""Genshin-style stylized foliage for the Lyris test island.

Technique (from stylized-foliage breakdowns of the Genshin look):
  * Canopies are a few inflated SHELLS (inner ones smaller, simpler and opaque, so the trunk never
    shows through) wrapped in LEAF CARDS cut from a painted leaf-clump atlas for a fluffy edge.
  * Every shell vertex and every card uses normals projected from the canopy's centre, so light
    wraps the whole canopy as one soft round form.
  * Extra data for the materials, in spare UV channels:
        UV1 = (depth, height)   depth 0 = innermost shell .. 1 = outer cards; height 0..1 up the canopy
        UV2 = (random, kind)    a per-card / per-shell random value; kind 0 = shell, 1 = card
    The materials use depth to darken the inside (fake occlusion), height for a top-lit gradient,
    the random value for gentle per-card colour variation and wind phase.

Species are original designs in the spirit of a breezy, Mondstadt-like meadow:
  oak (round broadleaf), birch (white trunk, light airy canopy), pine (tiered, on high ground),
  blossom (the accent tree), bush. Ground plants: ferns, dune grass, dandelions, flower spikes,
  mushroom clusters.
"""

import math

import numpy as np

ATLAS_CELL = {"oak": 0, "bush": 0, "birch": 1, "pine": 2, "blossom": 3}
PLANT_CELL = {"fern": 0, "dune": 1, "dandelion": 2, "spike": 3}


def _cell_uv(cell):
    u0, v0 = (cell % 2) * 0.5, (cell // 2) * 0.5
    return u0, v0


def icosphere(subdiv):
    t = (1 + 5 ** 0.5) / 2
    verts = [np.array(v, dtype=float) for v in
             [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
              (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]]
    verts = [v / np.linalg.norm(v) for v in verts]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
             (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(subdiv):
        cache, sub = {}, []

        def mid(a, b):
            key = (min(a, b), max(a, b))
            if key not in cache:
                m = verts[a] + verts[b]
                verts.append(m / np.linalg.norm(m))
                cache[key] = len(verts) - 1
            return cache[key]

        for a, b, c in faces:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            sub += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = sub
    return verts, faces


def _add_tri_outward(part, ids, outward):
    a, b, c = ids
    pa, pb, pc = (np.array(part.pos[k]) for k in ids)
    if np.dot(np.cross(pb - pa, pc - pa), outward) >= 0:
        part.tri(a, b, c)
    else:
        part.tri(a, c, b)


class Canopy:
    """Describes one canopy volume: centre, radii (x, y, z) and an optional tier shape."""

    def __init__(self, centre, radii, pointy=0.0):
        self.centre = np.array(centre, dtype=float)
        self.radii = np.array(radii, dtype=float)
        self.pointy = pointy  # 0 = round, >0 = narrower toward the top (pine tiers)

    def surface(self, v, scale=1.0, lump=0.0):
        """Point on the canopy surface along unit direction v."""
        r = self.radii * scale
        taper = 1.0 - self.pointy * max(0.0, v[2]) * 0.85
        p = np.array([v[0] * r[0] * taper, v[1] * r[1] * taper, v[2] * r[2]])
        return self.centre + p * (1.0 + lump)

    def normal(self, p):
        d = (p - self.centre) / self.radii
        n = d / (np.linalg.norm(d) or 1.0)
        return 0.8 * n + 0.2 * np.array([0, 0, 1.0])

    def height01(self, p):
        return float(np.clip((p[2] - (self.centre[2] - self.radii[2])) / (2 * self.radii[2]), 0, 1))


def canopy_shells(mesh, material, canopy, rng, layers=3):
    """Inflated shells, inner ones smaller and simpler; normals from the canopy centre."""
    part = mesh.part(material)
    seed = rng.uniform(0, 100)
    for layer in range(layers):
        depth = layer / max(layers - 1, 1)
        scale = 0.62 + 0.38 * depth
        verts, faces = icosphere(1 if layer < layers - 1 else 2)
        rand = rng.random()
        ids = []
        for v in verts:
            lump = 0.10 * math.sin(v[0] * 5 + seed) * math.cos(v[1] * 4 + seed) + 0.06 * math.sin(v[2] * 7 + seed)
            p = canopy.surface(v, scale, lump)
            n = canopy.normal(p)
            n = n / np.linalg.norm(n)
            ids.append(part.vert(p, n, (p[0] / 150.0, p[2] / 150.0 + p[1] / 300.0),
                                 uv1=(depth * 0.8, canopy.height01(p)), uv2=(rand, 0.0)))
        for f in faces:
            pa = np.array(part.pos[ids[f[0]]])
            _add_tri_outward(part, [ids[k] for k in f], pa - canopy.centre)


def canopy_cards(mesh, material, canopy, rng, count, size, cell, droop=0.0):
    """Leaf-clump cards scattered over the outside, facing outward with the canopy's soft normal."""
    part = mesh.part(material)
    u0, v0 = _cell_uv(cell)
    for _ in range(count):
        # Bias toward the upper and side surfaces; few cards underneath.
        while True:
            v = rng.normal(size=3)
            v /= np.linalg.norm(v)
            if v[2] > -0.45 or rng.random() < 0.25:
                break
        p = canopy.surface(v, rng.uniform(0.92, 1.08))
        n = canopy.normal(p)
        n /= np.linalg.norm(n)
        s = size * rng.uniform(0.75, 1.25)
        # Card plane: tangent to the canopy, randomly spun, optionally drooping (pine tufts).
        t = np.cross(n, [0, 0, 1.0])
        if np.linalg.norm(t) < 1e-3:
            t = np.array([1.0, 0, 0])
        t /= np.linalg.norm(t)
        b = np.cross(n, t)
        spin = rng.uniform(0, 2 * math.pi)
        t, b = t * math.cos(spin) + b * math.sin(spin), -t * math.sin(spin) + b * math.cos(spin)
        tilt = n * 0.35 + np.array([0, 0, -droop])  # lean the card a little out from the surface
        corners = [p + (-t - b) * s / 2 - tilt * s * 0.2, p + (t - b) * s / 2 - tilt * s * 0.2,
                   p + (t + b) * s / 2 + tilt * s * 0.2, p + (-t + b) * s / 2 + tilt * s * 0.2]
        uvs = [(u0, v0 + 0.5), (u0 + 0.5, v0 + 0.5), (u0 + 0.5, v0), (u0, v0)]
        rand = rng.random()
        ids = [part.vert(c, n, uv, uv1=(1.0, canopy.height01(c)), uv2=(rand, 1.0)) for c, uv in zip(corners, uvs)]
        part.tri(ids[0], ids[1], ids[2])
        part.tri(ids[0], ids[2], ids[3])


# ----------------------------------------------------------------------------- trunks

def tapered_limb(mesh, material, points, radii, sides=8):
    rings = []
    for k, (p, r) in enumerate(zip(points, radii)):
        p = np.array(p, dtype=float)
        d = np.array(points[min(k + 1, len(points) - 1)], dtype=float) - np.array(points[max(k - 1, 0)], dtype=float)
        d = d / (np.linalg.norm(d) or 1)
        side = np.cross(d, [0, 0, 1.0]) if abs(d[2]) < 0.95 else np.array([1.0, 0, 0])
        side /= np.linalg.norm(side)
        up = np.cross(side, d)
        rings.append([(p + (side * math.cos(a) + up * math.sin(a)) * r, side * math.cos(a) + up * math.sin(a))
                      for a in np.linspace(0, 2 * math.pi, sides, endpoint=False)])
    part = mesh.part(material)
    for k in range(len(rings) - 1):
        for s in range(sides):
            s1 = (s + 1) % sides
            quad = [rings[k][s], rings[k][s1], rings[k + 1][s1], rings[k + 1][s]]
            ids = [part.vert(p, n, (s / sides, (k + (j >= 2)) * 0.5)) for j, (p, n) in enumerate(quad)]
            outward = sum(n for _, n in quad) / 4
            _add_tri_outward(part, [ids[0], ids[1], ids[2]], outward)
            _add_tri_outward(part, [ids[0], ids[2], ids[3]], outward)


def trunk(mesh, material, base, height, r_base, r_top, lean, curve=0.0, segments=5):
    base = np.array(base, dtype=float)
    pts, radii = [], []
    for k in range(segments):
        f = k / (segments - 1)
        offset = np.array([lean[0] * f ** 1.6, lean[1] * f ** 1.6, height * f])
        offset[0] += curve * math.sin(f * math.pi) * 0.5
        pts.append(base + offset)
        flare = 1.0 + 0.6 * max(0.0, 1.0 - f * 4.0) ** 2  # flared roots
        radii.append((r_base + (r_top - r_base) * f) * flare)
    tapered_limb(mesh, material, pts, radii)
    return pts


# ----------------------------------------------------------------------------- species

def oak(trunks, leaves, ground, x, y, s, rng, species="oak"):
    pts = trunk(trunks, "bark", (x, y, ground - 25), 340 * s, 34 * s, 16 * s,
                (rng.uniform(-45, 45) * s, rng.uniform(-45, 45) * s), curve=rng.uniform(-30, 30) * s)
    top = pts[-1]
    main = Canopy(top + np.array([0, 0, 120 * s]), (230 * s, 220 * s, 165 * s))
    lobes = [main]
    for k in range(int(rng.integers(2, 4))):  # asymmetric side lobes
        a = rng.uniform(0, 2 * math.pi)
        c = main.centre + np.array([math.cos(a) * 170 * s, math.sin(a) * 170 * s, rng.uniform(-60, 30) * s])
        lobes.append(Canopy(c, np.array([130, 125, 100]) * s * rng.uniform(0.85, 1.1)))
        start = pts[2] + np.array([0, 0, rng.uniform(0, 40) * s])
        mid = (start + c) / 2 + np.array([0, 0, 40 * s])
        tapered_limb(trunks, "bark", [start, mid, c - np.array([0, 0, 40 * s])], [13 * s, 9 * s, 6 * s], sides=6)
    for lobe in lobes:
        canopy_shells(leaves, f"shell_{species}", lobe, rng)
        area = lobe.radii[0] * lobe.radii[2] / (200 * 150)
        canopy_cards(leaves, f"cards_{species}", lobe, rng, int(46 * area * s) + 10, 120 * s, ATLAS_CELL[species])


def birch(trunks, leaves, ground, x, y, s, rng):
    pts = trunk(trunks, "birch_bark", (x, y, ground - 20), 470 * s, 18 * s, 9 * s,
                (rng.uniform(-60, 60) * s, rng.uniform(-60, 60) * s), curve=rng.uniform(-40, 40) * s)
    top = pts[-1]
    for k in range(3):  # light, airy, stacked canopy
        c = top + np.array([rng.uniform(-50, 50) * s, rng.uniform(-50, 50) * s, (-150 + k * 95) * s])
        lobe = Canopy(c, np.array([120, 115, 95]) * s * (1.1 - k * 0.18))
        canopy_shells(leaves, "shell_birch", lobe, rng, layers=2)
        canopy_cards(leaves, "cards_birch", lobe, rng, int(26 * s) + 8, 90 * s, ATLAS_CELL["birch"])


def pine(trunks, leaves, ground, x, y, s, rng):
    pts = trunk(trunks, "pine_bark", (x, y, ground - 20), 620 * s, 24 * s, 7 * s, (0, 0), segments=6)
    base = np.array(pts[0])
    for k in range(4):  # tiers, wide at the bottom, pointed at the top
        f = k / 3
        c = base + np.array([0, 0, (170 + f * 400) * s])
        r = (190 - f * 120) * s
        tier = Canopy(c, (r, r, (95 - f * 25) * s), pointy=0.8)
        canopy_shells(leaves, "shell_pine", tier, rng, layers=2)
        canopy_cards(leaves, "cards_pine", tier, rng, int(30 * (1.2 - f * 0.6) * s) + 6, 110 * s,
                     ATLAS_CELL["pine"], droop=0.35)


def bush(leaves, ground, x, y, s, rng, berries=False):
    c = Canopy((x, y, ground + 50 * s), np.array([120, 110, 70]) * s)
    canopy_shells(leaves, "shell_bush", c, rng, layers=2)
    canopy_cards(leaves, "cards_bush", c, rng, int(22 * s) + 6, 75 * s, ATLAS_CELL["bush"])
    if berries:  # a few soft red-violet berries peeking out (an original valberry-like touch)
        part = leaves.part("berry")
        verts, faces = icosphere(1)
        for _ in range(int(rng.integers(6, 11))):
            v = rng.normal(size=3)
            v[2] = abs(v[2]) * 0.6
            v /= np.linalg.norm(v)
            centre = c.surface(v, 1.02)
            ids = [part.vert(centre + w * 6.5 * s, w, (0, 0)) for w in verts]
            for f in faces:
                _add_tri_outward(part, [ids[k] for k in f], np.array(part.pos[ids[f[0]]]) - centre)


def mushrooms(props, ground_at, x, y, rng, count=5):
    """A little cluster of mushrooms (stem + cap) for shady spots under trees."""
    part = props.part("mushroom")
    verts, faces = icosphere(1)
    for _ in range(count):
        mx, my = x + rng.uniform(-45, 45), y + rng.uniform(-45, 45)
        g = ground_at(mx, my)
        h = rng.uniform(10, 22)
        r = rng.uniform(5, 10)
        stem_r = r * 0.32
        for k in range(6):  # stem
            a0, a1 = 2 * math.pi * k / 6, 2 * math.pi * (k + 1) / 6
            d0 = np.array([math.cos(a0), math.sin(a0), 0])
            d1 = np.array([math.cos(a1), math.sin(a1), 0])
            p = [np.array([mx, my, g - 2]) + d0 * stem_r, np.array([mx, my, g - 2]) + d1 * stem_r,
                 np.array([mx, my, g + h]) + d1 * stem_r * 0.8, np.array([mx, my, g + h]) + d0 * stem_r * 0.8]
            ids = [part.vert(q, (d0 + d1) / 2, (0, 0)) for q in p]
            _add_tri_outward(part, ids[:3], d0 + d1)
            _add_tri_outward(part, [ids[0], ids[2], ids[3]], d0 + d1)
        centre = np.array([mx, my, g + h])
        ids = []
        for w in verts:  # cap: a dome, flattened underneath
            q = np.array([w[0] * r, w[1] * r, (w[2] * r * 0.7) if w[2] > 0 else w[2] * r * 0.15])
            ids.append(part.vert(centre + q, w, (0, 0)))
        for f in faces:
            _add_tri_outward(part, [ids[k] for k in f], np.array(part.pos[ids[f[0]]]) - centre)


def plant_cards(part, x, y, g, kind, size, rng, normal=(0, 0, 1)):
    """Two crossed upright cards showing one ground plant from the plant atlas."""
    u0, v0 = _cell_uv(PLANT_CELL[kind])
    yaw = rng.uniform(0, math.pi)
    for ang in (yaw, yaw + math.pi / 2):
        dx, dy = math.cos(ang) * size / 2, math.sin(ang) * size / 2
        q = [part.vert((x - dx, y - dy, g - 3), normal, (u0, v0 + 0.5)),
             part.vert((x + dx, y + dy, g - 3), normal, (u0 + 0.5, v0 + 0.5)),
             part.vert((x + dx, y + dy, g + size), normal, (u0 + 0.5, v0)),
             part.vert((x - dx, y - dy, g + size), normal, (u0, v0))]
        part.tri(q[0], q[1], q[2])
        part.tri(q[0], q[2], q[3])
