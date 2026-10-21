"""Genshin-style stylized foliage for the Lyris test island.

Technique (from stylized-foliage breakdowns of the Genshin look):
  * Each canopy is a soft core covered in leaf PUFFS (rounded clumps), joined with a smooth union
    into one clumpy outer shell, over a small opaque inner shell (so the trunk never shows
    through), with LEAF CARDS from a painted leaf-clump atlas sitting on the clumps as a fringe.
  * Every shell vertex and every card uses normals projected from the canopy's centre, so light
    wraps the whole canopy as one soft round form.
  * Extra data for the materials, in spare UV channels:
        UV1 = (depth, height)   depth 0 = innermost shell .. 1 = outer cards; height 0..1 up the canopy
        UV2 = (random, shade)   a per-card / per-shell random value; clump shade 0 = dark crease
                                between clumps .. 1 = sunlit top of a clump
    The materials use depth to darken the inside (fake occlusion), height for a top-lit gradient,
    clump shade so every clump reads on its own, and the random value for colour variation.

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


SUN = np.array([0.35, -0.30, 0.89]) / np.linalg.norm([0.35, -0.30, 0.89])


def smax(a, b, k):
    """Smooth maximum: like max(a, b) but with a soft fillet of width k where they meet."""
    h = np.clip(0.5 + 0.5 * (a - b) / k, 0.0, 1.0)
    return a * h + b * (1 - h) + k * h * (1 - h)


def _ray_ellipsoid(origin, dirs, centre, radii):
    """Far hit distance of rays from `origin` along unit `dirs` (N, 3); -1e6 where they miss."""
    o = (origin - centre) / radii
    d = dirs / radii
    a = (d * d).sum(1)
    b = 2 * (d @ o)
    c = float(o @ o) - 1.0
    disc = b * b - 4 * a * c
    t = (-b + np.sqrt(np.maximum(disc, 0.0))) / (2 * a)
    return np.where(disc >= 0, t, -1e6)


class Canopy:
    """One canopy volume: a soft core (centre, radii, optional pine taper) covered in leaf PUFFS.

    The visible surface is the smooth union of the core and the puffs, so the silhouette is a
    cluster of rounded clumps instead of one smooth blob. Each point also knows which puff it
    belongs to, so every clump can be lit on its own top with darker creases between clumps.
    """

    def __init__(self, centre, radii, pointy=0.0):
        self.centre = np.array(centre, dtype=float)
        self.radii = np.array(radii, dtype=float)
        self.pointy = pointy  # 0 = round, >0 = narrower toward the top (pine tiers)
        self.puffs = []       # (centre, radii)
        self.zrange = None    # (bottom, top) of the whole crown, so lower clumps sit in shade
        self.depth = 0.8      # UV1.x of the outer shell; lower for clumps deep inside a crown
        self.crown = None     # (centre, radii) of the whole tree's crown: lit as ONE soft form

    @property
    def size(self):
        return float(self.radii.mean())

    def surface(self, v, scale=1.0, lump=0.0):
        """Point on the core ellipsoid along unit direction v."""
        r = self.radii * scale
        taper = 1.0 - self.pointy * max(0.0, v[2]) * 0.85
        p = np.array([v[0] * r[0] * taper, v[1] * r[1] * taper, v[2] * r[2]])
        return self.centre + p * (1.0 + lump)

    def normal(self, p):
        """The soft, canopy-wide normal: from the whole crown when there is one, so every clump
        of a tree shares one smooth light gradient instead of being lit like its own ball."""
        centre, radii = self.crown if self.crown is not None else (self.centre, self.radii)
        d = (p - centre) / radii
        n = d / (np.linalg.norm(d) or 1.0)
        return 0.8 * n + 0.2 * np.array([0, 0, 1.0])

    def height01(self, p):
        if self.zrange:
            lo, hi = self.zrange
            return float(np.clip((p[2] - lo) / max(hi - lo, 1.0), 0, 1))
        return float(np.clip((p[2] - (self.centre[2] - self.radii[2])) / (2 * self.radii[2]), 0, 1))

    def add_puffs(self, rng, count, size=0.42, flat=1.0, underside=0.15):
        """Scatters `count` round leaf clumps over the core, mostly on the top and sides."""
        golden = math.pi * (3 - math.sqrt(5))
        offset = rng.uniform(0, 2 * math.pi)
        n = max(count, 1)
        for k in range(n):
            z = 1 - 2 * (k + 0.5) / n
            ring = math.sqrt(max(0.0, 1 - z * z))
            a = offset + golden * k
            v = np.array([math.cos(a) * ring, math.sin(a) * ring, z]) + rng.normal(size=3) * 0.18
            v /= np.linalg.norm(v)
            if v[2] < -0.35 and rng.random() > underside:
                continue  # few clumps underneath, where nobody looks
            r = self.size * size * rng.uniform(0.8, 1.18) * (1.0 - 0.35 * self.pointy * max(0.0, v[2]))
            c = self.surface(v, rng.uniform(0.62, 0.74))
            self.puffs.append((c, np.array([r, r, r * flat])))

    def evaluate(self, dirs):
        """Surface points, normals and clump shading (0 dark crease .. 1 sunlit clump top)
        along unit directions `dirs` (N, 3) from the canopy centre."""
        dirs = np.asarray(dirs, dtype=float)
        core = np.array([np.linalg.norm(self.surface(v, 0.8) - self.centre) for v in dirs])
        hits = [core] + [_ray_ellipsoid(self.centre, dirs, c, r) for c, r in self.puffs]
        hits = np.stack(hits, 1)  # (N, 1 + puffs)
        blend = 0.2 * self.size
        t = hits[:, 0].copy()
        for j in range(1, hits.shape[1]):
            t = smax(t, hits[:, j], blend)
        order = np.argsort(-hits, axis=1)
        best, second = order[:, 0], order[:, 1] if hits.shape[1] > 1 else order[:, 0]
        rows = np.arange(len(dirs))
        gap = hits[rows, best] - hits[rows, second]
        crease = 1.0 - np.clip(gap / (0.3 * self.size), 0, 1)
        pts = self.centre + dirs * t[:, None]
        nrm, shade = [], []
        for i, p in enumerate(pts):
            big = self.normal(p)
            big /= np.linalg.norm(big)
            if best[i] == 0:
                own, lit_scale = big, 0.9  # bare core between clumps: a little shaded
            else:
                c, r = self.puffs[best[i] - 1]
                own = (p - c) / (r * r)
                own /= np.linalg.norm(own) or 1.0
                lit_scale = 1.0
            # Mostly the crown's normal, with just enough of the clump's own to keep it lumpy.
            k = 0.8 if self.crown is not None else 0.5
            n = k * big + (1 - k) * own
            n /= np.linalg.norm(n)
            lit = 0.5 + 0.5 * float(n @ SUN)
            nrm.append(n)
            shade.append(np.clip((0.45 + 0.55 * lit) * lit_scale * (1 - 0.3 * crease[i]), 0, 1))
        return pts, np.array(nrm), np.array(shade)


def canopy_shells(mesh, material, canopy, rng, detail=3):
    """An opaque dark inner shell (so the trunk never shows through) and the clumpy outer shell.

    UV1 = (depth, height), UV2 = (random, clump shade). See the module notes.
    """
    if not canopy.puffs:
        canopy.add_puffs(rng, 7)
    part = mesh.part(material)
    rand = rng.random()
    # Inner shell: small and simple (small clumps don't need one).
    verts, faces = icosphere(1) if canopy.size > 55 else ([], [])
    ids = []
    for v in verts:
        p = canopy.surface(v, 0.7)
        n = canopy.normal(p)
        ids.append(part.vert(p, n / np.linalg.norm(n), (p[0] / 150.0, p[2] / 150.0),
                             uv1=(0.0, canopy.height01(p)), uv2=(rand, 0.25)))
    for f in faces:
        _add_tri_outward(part, [ids[k] for k in f], np.array(part.pos[ids[f[0]]]) - canopy.centre)
    # Outer shell: the smooth union of the core and its leaf puffs.
    verts, faces = icosphere(detail)
    pts, nrms, shade = canopy.evaluate(np.array(verts))
    ids = [part.vert(p, n, (p[0] / 150.0, p[2] / 150.0), uv1=(canopy.depth, canopy.height01(p)),
                     uv2=(rand, float(s)))
           for p, n, s in zip(pts, nrms, shade)]
    for f in faces:
        _add_tri_outward(part, [ids[k] for k in f], np.array(part.pos[ids[f[0]]]) - canopy.centre)


def canopy_cards(mesh, material, canopy, rng, count, size, cell, droop=0.0):
    """Leaf-clump cards sitting on the clumps, leaning out as a soft fringe on the silhouette."""
    part = mesh.part(material)
    u0, v0 = _cell_uv(cell)
    if not canopy.puffs:
        canopy.add_puffs(rng, 7)
    weights = np.array([r[0] ** 2 for _, r in canopy.puffs])
    weights /= weights.sum()
    up = np.array([0, 0, 1.0])
    dirs = []
    crown_c = canopy.crown[0] if canopy.crown is not None else canopy.centre
    for _ in range(count):
        c, r = canopy.puffs[rng.choice(len(canopy.puffs), p=weights)]
        out = 0.5 * (c - canopy.centre) / (np.linalg.norm(c - canopy.centre) or 1.0) \
            + (c - crown_c) / (np.linalg.norm(c - crown_c) or 1.0)
        out /= np.linalg.norm(out) or 1.0
        d = rng.normal(size=3) + 1.3 * out + 0.4 * up  # the outward, upper side of a clump
        d /= np.linalg.norm(d)
        q = c + d * r - canopy.centre
        dirs.append(q / (np.linalg.norm(q) or 1.0))
    pts, nrms, shade = canopy.evaluate(np.array(dirs))
    for p, n, sh in zip(pts, nrms, shade):
        p = canopy.centre + (p - canopy.centre) * rng.uniform(0.97, 1.01)  # sit on the surface
        s = size * rng.uniform(0.75, 1.25)
        # Card plane: tangent to the surface, randomly spun, optionally drooping (pine tufts).
        t = np.cross(n, up)
        if np.linalg.norm(t) < 1e-3:
            t = np.array([1.0, 0, 0])
        t /= np.linalg.norm(t)
        b = np.cross(n, t)
        spin = rng.uniform(0, 2 * math.pi)
        t, b = t * math.cos(spin) + b * math.sin(spin), -t * math.sin(spin) + b * math.cos(spin)
        tilt = n * 0.42 + np.array([0, 0, -droop])  # lean only a little: a soft fringe, not spikes
        corners = [p + (-t - b) * s / 2 - tilt * s * 0.2, p + (t - b) * s / 2 - tilt * s * 0.2,
                   p + (t + b) * s / 2 + tilt * s * 0.2, p + (-t + b) * s / 2 + tilt * s * 0.2]
        uvs = [(u0, v0 + 0.5), (u0 + 0.5, v0 + 0.5), (u0 + 0.5, v0), (u0, v0)]
        rand = rng.random()
        ids = [part.vert(c, n, uv, uv1=(1.0, canopy.height01(c)), uv2=(rand, float(sh)))
               for c, uv in zip(corners, uvs)]
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


# ----------------------------------------------------------------------------- branch growth

def grow_branches(rng, base, trunk_top, attractors, step, influence, kill, up_bias=0.0, max_iter=120):
    """Space colonization (Runions et al. 2007): branches grow toward attraction points that
    fill the crown, and a point is used up once a branch reaches it. Returns node positions and
    each node's parent (-1 for the root). The trunk is a straight run from `base` to `trunk_top`."""
    from scipy.spatial import cKDTree

    base, trunk_top = np.asarray(base, float), np.asarray(trunk_top, float)
    n_trunk = max(2, int(np.linalg.norm(trunk_top - base) / step) + 1)
    nodes = [base + (trunk_top - base) * k / (n_trunk - 1) for k in range(n_trunk)]
    parent = [-1] + list(range(n_trunk - 1))
    pts = np.asarray(attractors, float)
    up = np.array([0, 0, 1.0])
    for _ in range(max_iter):
        if len(pts) == 0:
            break
        arr = np.array(nodes)
        dist, near = cKDTree(arr).query(pts, distance_upper_bound=influence)
        ok = np.isfinite(dist)
        if not ok.any():
            break
        grow = {}
        for p, n in zip(pts[ok], near[ok]):
            d = p - arr[n]
            grow.setdefault(n, []).append(d / (np.linalg.norm(d) or 1.0))
        added = 0
        for n, dirs in grow.items():
            d = np.sum(dirs, 0)
            d = d / (np.linalg.norm(d) or 1.0) + up * up_bias
            d /= np.linalg.norm(d) or 1.0
            new = arr[n] + d * step
            nodes.append(new)
            parent.append(n)
            added += 1
        if not added:
            break
        dist, _ = cKDTree(np.array(nodes)).query(pts)
        pts = pts[dist > kill]
    return np.array(nodes), np.array(parent), n_trunk


def _children(parent):
    kids = [[] for _ in parent]
    for i, p in enumerate(parent):
        if p >= 0:
            kids[p].append(i)
    return kids


def pipe_radii(parent, tip_radius, exponent=2.4):
    """Pipe model: a parent branch is as thick as its children together (r^n = sum r_i^n)."""
    acc = np.zeros(len(parent))
    kids = _children(parent)
    for i in range(len(parent) - 1, -1, -1):
        acc[i] = tip_radius ** exponent if not kids[i] else sum(acc[c] for c in kids[i])
    return acc ** (1.0 / exponent)


def smooth_skeleton(nodes, parent, passes=2):
    """Softens kinks: every node moves a little toward the midpoint of its parent and child."""
    kids = _children(parent)
    nodes = nodes.copy()
    for _ in range(passes):
        out = nodes.copy()
        for i, p in enumerate(parent):
            if p >= 0 and len(kids[i]) == 1:
                out[i] = 0.5 * nodes[i] + 0.25 * (nodes[p] + nodes[kids[i][0]])
        nodes = out
    return nodes


def branch_meshes(trunks, branches, material, nodes, parent, radii, n_trunk, min_radius, flare_z=None):
    """Turns the skeleton into tapered limbs. The trunk goes in `trunks` (it collides); the
    branches up in the crown go in `branches` (no collision). Twigs thinner than `min_radius`
    are left out: they would sit inside the leaf clumps anyway."""
    kids = _children(parent)
    stack = [0]
    while stack:
        start = stack.pop()
        chain = [parent[start]] if parent[start] >= 0 else []
        i = start
        while True:
            chain.append(i)
            live = [c for c in kids[i] if radii[c] >= min_radius]
            if not live:
                break
            live.sort(key=lambda c: -radii[c])
            stack.extend(live[1:])
            i = live[0]
        if len(chain) < 2:
            continue
        pts = [nodes[k] for k in chain]
        rs = [radii[k] for k in chain]
        if flare_z is not None and chain[0] == 0:
            rs = [r * (1.0 + 0.7 * max(0.0, 1.0 - (p[2] - pts[0][2]) / flare_z) ** 2) for p, r in zip(pts, rs)]
        sides = 9 if rs[0] > 14 else (6 if rs[0] > 5 else 4)
        split = next((j for j, k in enumerate(chain) if k >= n_trunk), len(chain))
        if split >= 2:  # the trunk part collides; the limb carrying on from it doesn't
            tapered_limb(trunks, material, pts[:split], rs[:split], sides=sides)
        if split < len(chain):
            j = max(split - 1, 0)
            if len(chain) - j >= 2:
                tapered_limb(branches, material, pts[j:], rs[j:], sides=sides if j == 0 else 7)


def _kmeans(points, k, rng, iters=12):
    k = max(1, min(k, len(points)))
    centres = points[rng.choice(len(points), k, replace=False)]
    for _ in range(iters):
        label = np.argmin(((points[:, None] - centres[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if (label == j).any():
                centres[j] = points[label == j].mean(0)
    return centres, label


def leaf_clumps(leaves, species, nodes, parent, rng, count, size, flat=0.8, puffs=5, cards=1.0,
                card_size=80.0, droop=0.0, min_z=None):
    """Clouds of leaves at the ends of the branches: the branch tips are grouped into a FEW big
    overlapping masses (Genshin-style: 4-7 per tree), each a cluster of smaller puffs, so the
    crown reads as one soft canopy with a lumpy outline rather than a bunch of separate balls.
    Tips below `min_z` (twigs along the trunk) are left bare."""
    kids = _children(parent)
    tips = np.array([nodes[i] for i in range(len(nodes)) if not kids[i]])
    if min_z is not None and len(tips):
        high = tips[tips[:, 2] >= min_z]
        tips = high if len(high) >= count else tips
    if len(tips) == 0:
        return []
    centres, label = _kmeans(tips, count, rng)
    crown_c = tips.mean(0)
    crown_r = np.linalg.norm(tips[:, :2] - crown_c[:2], axis=1).max() + 1.0
    clumps = []
    for j, c in enumerate(centres):
        group = tips[label == j]
        spread = np.linalg.norm(group - c, axis=1).mean() if len(group) > 1 else 0.0
        r = float(np.clip(size * rng.uniform(0.85, 1.15) + 0.35 * spread, size * 0.8, size * 1.35))
        clump = Canopy(c + np.array([0, 0, r * 0.15]), (r, r * rng.uniform(0.85, 1.1), r * flat))
        clump.add_puffs(rng, puffs, 0.4, flat=min(0.9, flat + 0.05), underside=0.05)
        outward = np.linalg.norm(c[:2] - crown_c[:2]) / crown_r
        clump.depth = 0.45 + 0.4 * min(1.0, outward + max(0.0, (c[2] - crown_c[2]) / (crown_r + 1)))
        clumps.append(clump)
    lo = min(k.centre[2] - k.radii[2] for k in clumps)
    hi = max(k.centre[2] + k.radii[2] for k in clumps)
    crown = _crown_of(clumps)
    for clump in clumps:
        clump.zrange = (lo, hi)
        clump.crown = crown
        canopy_shells(leaves, f"shell_{species}", clump, rng, detail=3 if clump.size > 75 else 2)
        n = int(cards * (5 + 9 * (clump.size / 100.0) ** 2))
        canopy_cards(leaves, f"cards_{species}", clump, rng, n, card_size, ATLAS_CELL[species], droop=droop)
    return clumps


def _crown_of(clumps):
    """One ellipsoid around a tree's clumps: the shape the whole canopy is lit as."""
    lo = np.min([k.centre - k.radii for k in clumps], 0)
    hi = np.max([k.centre + k.radii for k in clumps], 0)
    return (lo + hi) / 2, np.maximum((hi - lo) / 2, 1.0)


def _blob_points(rng, n, spheres, floor_z):
    """Attraction points filling a crown made of a few overlapping squashed spheres."""
    out = []
    while len(out) < n:
        c, r = spheres[rng.integers(len(spheres))]
        v = rng.normal(size=3)
        v /= np.linalg.norm(v)
        p = c + v * r * rng.random() ** (1 / 3)
        if p[2] > floor_z:
            out.append(p)
    return np.array(out)


# ----------------------------------------------------------------------------- species

def oak(trunks, leaves, ground, x, y, s, rng, species="oak"):
    """Broadleaf: a short sturdy trunk splitting into a few big limbs, crown of 12-16 clumps.
    The blossom tree is the same build with a wider, flatter, more spreading crown."""
    blossom = species == "blossom"
    base = np.array([x, y, ground - 25])
    lean = np.array([rng.uniform(-40, 40), rng.uniform(-40, 40), 0]) * s
    trunk_top = base + lean + np.array([0, 0, (215 if blossom else 210) * s])
    crown_z = trunk_top[2] + (150 if blossom else 175) * s
    spheres = []
    for k in range(int(rng.integers(3, 5))):  # an asymmetric crown made of a few masses
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(40, 200 if blossom else 160) * s
        c = np.array([x + lean[0] + math.cos(a) * d, y + lean[1] + math.sin(a) * d,
                      crown_z + rng.uniform(-40, 70) * s])
        r = rng.uniform(150, 200) * s
        spheres.append((c, np.array([r, r, r * (0.68 if blossom else 0.95)])))
    pts = _blob_points(rng, 420, spheres, trunk_top[2] + 20 * s)
    nodes, parent, n_trunk = grow_branches(rng, base, trunk_top, pts, 34 * s, 230 * s, 60 * s,
                                           up_bias=0.15 if blossom else 0.3)
    nodes = smooth_skeleton(nodes, parent)
    radii = pipe_radii(parent, 1.1 * s)
    radii *= 30 * s / max(radii[0], 1e-6)  # trunk about 60 cm across
    branch_meshes(trunks, leaves, "bark", nodes, parent, radii, n_trunk, 2.5 * s, flare_z=70 * s)
    leaf_clumps(leaves, species, nodes, parent, rng, 7 if blossom else 6, (118 if blossom else 125) * s,
                flat=0.8 if blossom else 0.92, puffs=9, cards=1.1, card_size=66 * s,
                min_z=trunk_top[2] + 40 * s)


def birch(trunks, leaves, ground, x, y, s, rng):
    """Tall slim white trunk; a narrow, airy crown of many small clumps with sky between them."""
    base = np.array([x, y, ground - 20])
    lean = np.array([rng.uniform(-60, 60), rng.uniform(-60, 60), 0]) * s
    trunk_top = base + lean + np.array([0, 0, 300 * s])
    c = trunk_top + np.array([0, 0, 220 * s])
    spheres = [(c, np.array([150, 150, 170]) * s),
               (c + np.array([rng.uniform(-50, 50), rng.uniform(-50, 50), 110]) * s, np.array([110, 110, 120]) * s)]
    pts = _blob_points(rng, 300, spheres, trunk_top[2] + 40 * s)
    nodes, parent, n_trunk = grow_branches(rng, base, trunk_top, pts, 28 * s, 120 * s, 40 * s, up_bias=0.3)
    nodes = smooth_skeleton(nodes, parent)
    radii = pipe_radii(parent, 0.8 * s, exponent=2.8)
    radii *= 17 * s / max(radii[0], 1e-6)
    branch_meshes(trunks, leaves, "birch_bark", nodes, parent, radii, n_trunk, 2.2 * s, flare_z=40 * s)
    leaf_clumps(leaves, "birch", nodes, parent, rng, 6, 78 * s, flat=0.75, puffs=7, cards=1.2,
                card_size=40 * s, min_z=trunk_top[2] + 70 * s)


def pine(trunks, leaves, ground, x, y, s, rng):
    """Straight trunk with whorls of drooping branches; each branch ends in a flat needle pad,
    so the tree reads as layered tiers with gaps between them, narrowing to a point."""
    height = 640 * s
    pts = trunk(trunks, "pine_bark", (x, y, ground - 20), height, 24 * s, 5 * s, (0, 0), segments=7)
    base = np.array(pts[0])
    pads = []
    whorls = 6
    for k in range(whorls):
        f = k / (whorls - 1)
        z = (170 + f * (height / s - 230)) * s
        reach = (230 - f * 170) * s
        n_branch = int(rng.integers(5, 7)) - (1 if f > 0.6 else 0)
        a0 = rng.uniform(0, 2 * math.pi)
        for b in range(n_branch):
            a = a0 + 2 * math.pi * b / n_branch + rng.uniform(-0.25, 0.25)
            d = np.array([math.cos(a), math.sin(a), 0.0])
            start = base + np.array([0, 0, z])
            tip = start + d * reach * rng.uniform(0.85, 1.05) + np.array([0, 0, -reach * 0.28])
            mid = (start + tip) / 2 + np.array([0, 0, reach * 0.12])
            tapered_limb(leaves, "pine_bark", [start, mid, tip], [6 * s, 4 * s, 2.5 * s], sides=4)
            # Several small sprays along the branch (bigger toward the tip) instead of one pad.
            stops = (0.5, 0.78, 1.0) if reach > 140 * s else ((0.65, 1.0) if reach > 90 * s else (1.0,))
            for t in stops:
                p = start + (tip - start) * t + np.cross(d, [0, 0, 1.0]) * rng.uniform(-12, 12) * s
                r = (28 + reach / s * 0.15) * s * (0.6 + 0.45 * t) * rng.uniform(0.85, 1.15)
                pads.append((p + np.array([0, 0, 8 * s]), r))
    pads.append((base + np.array([0, 0, height + 25 * s]), 36 * s))  # the point at the top
    lo = min(p[2] - r * 0.5 for p, r in pads)
    hi = max(p[2] + r for p, r in pads)
    centre = base + np.array([0, 0, height * 0.55])
    crown = (np.array([base[0], base[1], (lo + hi) / 2]), np.array([200 * s, 200 * s, (hi - lo) / 2]))
    for p, r in pads:
        pad = Canopy(p, (r, r, r * 0.55), pointy=0.3)
        pad.crown = crown
        pad.add_puffs(rng, 3, 0.55, flat=0.7, underside=0.0)
        pad.zrange = (lo, hi)
        pad.depth = 0.5 + 0.35 * min(1.0, np.linalg.norm(p[:2] - centre[:2]) / (180 * s))
        canopy_shells(leaves, "shell_pine", pad, rng, detail=2)
        canopy_cards(leaves, "cards_pine", pad, rng, int(3 + 6 * (r / (50 * s)) ** 2), 70 * s,
                     ATLAS_CELL["pine"], droop=0.35)


def bush(leaves, ground, x, y, s, rng, berries=False):
    """A low mound of 3-5 overlapping clumps instead of one smooth dome."""
    clumps = []
    n = int(rng.integers(3, 6))
    for k in range(n):
        a = 2 * math.pi * k / n + rng.uniform(-0.4, 0.4)
        d = (0 if k == 0 else rng.uniform(45, 75)) * s
        r = (68 if k == 0 else rng.uniform(42, 58)) * s
        c = np.array([x + math.cos(a) * d, y + math.sin(a) * d, ground + r * 0.55 + (12 * s if k == 0 else 0)])
        clump = Canopy(c, (r, r * rng.uniform(0.85, 1.1), r * 0.8))
        clump.add_puffs(rng, 4, 0.55, flat=0.9, underside=0.0)
        clumps.append(clump)
    lo, hi = ground, max(k.centre[2] + k.radii[2] for k in clumps)
    crown = _crown_of(clumps)
    for clump in clumps:
        clump.zrange = (lo, hi)
        clump.crown = crown
        clump.depth = 0.7
        canopy_shells(leaves, "shell_bush", clump, rng, detail=2)
        canopy_cards(leaves, "cards_bush", clump, rng, int(5 + 8 * (clump.size / (60 * s)) ** 2), 42 * s,
                     ATLAS_CELL["bush"])
    if berries:  # a few soft red-violet berries peeking out (an original valberry-like touch)
        part = leaves.part("berry")
        verts, faces = icosphere(1)
        for _ in range(int(rng.integers(6, 11))):
            c = clumps[int(rng.integers(len(clumps)))]
            v = rng.normal(size=3)
            v[2] = abs(v[2]) * 0.6
            v /= np.linalg.norm(v)
            centre = c.centre + (c.evaluate([v])[0][0] - c.centre) * 1.01  # on the clumps
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
