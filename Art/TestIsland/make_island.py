"""Generates the Lyris test island: Sea of Remnants-style landforms, Genshin-style surfaces.

Look: lush green tops, dramatic sea cliffs in layered warm-stone ledges, a sheltered
sandy cove on the east where the dock lands, a gentle green slope up from the beach,
a rocky south-west headland for the lighthouse with a natural arch beyond it, and
sea stacks standing offshore. Painted textures: warm highlights, cool shadows.

Surfaces follow how Genshin Impact dresses its terrain (miHoYo, GDC 2021, and what the game
shows): smooth ground with softly blended texture layers plus a large-scale colour tone;
faceted rock clusters along cliffs with grass on their upward faces; dense swaying grass
blades tinted to the ground; soft round tree canopies that never go too dark.

Outputs (next to this script):
  test_island.glb       island mesh (terrain, rocks, arch, trees), imported by
                        Content/Python/lyris_build_harbor.py (open in Blender to edit)
  test_island_grass.glb grass blades (no collision)
  island_meta.json      height grid, bounds and dock shoreline for the Unreal script
  textures/*.png        painted textures
  preview.png           quick render for review

Coordinates are Unreal's (cm, X forward/east, Y right/south, Z up, sea level Z = 0).
The dock runs east along Y = 150.

Run:  python3 make_island.py
"""

import io
import json
import math
import os
import random
import struct

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 11
RES = 50.0                 # grid spacing (cm)
EXTENT = 3200.0            # grid covers -EXTENT..EXTENT on X and Y
SEABED = -350.0
TEX_PX = 256
TILE_CM = 400.0            # one texture tile covers 4 m
CLIFF_NZ = 0.70            # steeper than ~45 degrees is cliff rock
LIGHTHOUSE = (-1550.0, -1350.0)
ARCH = dict(centre=(-2350.0, -1950.0), span=380.0, thickness=230.0, depth=300.0, base_z=-150.0, yaw_deg=40.0)


# ----------------------------------------------------------------------------- noise

class ValueNoise:
    def __init__(self, seed):
        self.grid = np.random.default_rng(seed).random((256, 256))

    def __call__(self, x, y):
        xi, yi = np.floor(x).astype(int), np.floor(y).astype(int)
        xf, yf = x - xi, y - yi
        u, v = xf * xf * (3 - 2 * xf), yf * yf * (3 - 2 * yf)
        g = self.grid
        a, b = g[xi % 256, yi % 256], g[(xi + 1) % 256, yi % 256]
        c, d = g[xi % 256, (yi + 1) % 256], g[(xi + 1) % 256, (yi + 1) % 256]
        return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v

    def fbm(self, x, y, octaves=4):
        total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
        for _ in range(octaves):
            total = total + amp * self(x * freq, y * freq)
            norm += amp
            amp *= 0.5
            freq *= 2.0
        return total / norm


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def terrace(h, band, sharp=0.75):
    """Stylized cliff ledges: flat shelves joined by steep risers."""
    t = h / band
    f = t - np.floor(t)
    return (np.floor(t) + smoothstep(sharp, 1.0, f)) * band


# ----------------------------------------------------------------------------- terrain

def height_field():
    noise = ValueNoise(SEED)
    coords = np.arange(-EXTENT, EXTENT + RES / 2, RES)
    X, Y = np.meshgrid(coords, coords, indexing="ij")
    theta = np.arctan2(Y, X)
    wobble = noise.fbm(X / 900.0 + 3.1, Y / 900.0 + 7.7) - 0.5

    radius = 2000 + 260 * np.sin(3 * theta + 0.7) + 160 * np.sin(5 * theta + 2.1) + 300 * wobble
    d = np.hypot(X / 1.08, Y) / radius

    # East side faces the cove: a long gentle slope. Elsewhere: sea cliffs.
    east = np.clip(np.cos(theta), 0.0, 1.0) ** 3 * smoothstep(-0.2, 0.6, 1.0 - np.abs(Y) / 1500.0)
    plateau = 820.0 + 160.0 * (noise.fbm(X / 600.0, Y / 600.0) - 0.5)
    cliff_edge = 1.0 - smoothstep(0.80, 0.93, d)
    slope_edge = 1.0 - smoothstep(0.12, 1.05, d)
    land = cliff_edge * (1 - east) + slope_edge * east
    h = plateau * land

    # Hill to the north-west.
    hill = np.exp(-((X + 500) ** 2 + (Y - 500) ** 2) / (2 * 650.0 ** 2))
    h = h + 520.0 * hill * cliff_edge

    # South-west headland for the lighthouse.
    hd = np.hypot((X - LIGHTHOUSE[0]) / 1.15, Y - LIGHTHOUSE[1]) / 720.0
    headland = 1.0 - smoothstep(0.72, 0.95, hd)
    h = np.maximum(h, (1050.0 + 120.0 * (noise.fbm(X / 300.0, Y / 300.0) - 0.5)) * headland)

    # Ledged cliffs everywhere except the gentle cove slope.
    # Ledges only on the coastal cliffs (and the headland); the meadow and hill stay smooth.
    coast = np.maximum(smoothstep(0.62, 0.80, d), headland)
    h = terrace(h, 230.0) * (1 - east) * coast + h * (1 - (1 - east) * coast)

    # Sandy cove: a shelf just above the water where the east slope meets the sea.
    beach_band = east * smoothstep(0.84, 0.90, d) * (1 - smoothstep(0.98, 1.12, d))
    h = np.where(beach_band > 0.3, np.minimum(h, 30.0 + 120.0 * (1.05 - d)), h)

    # Sea floor slopes down away from the island.
    seabed = SEABED + 220.0 * np.exp(-np.maximum(d - 1.0, 0) * 3.0)
    h = np.where(h > 1.0, h, np.minimum(seabed, -40.0))

    # Sea stacks: tall ledged pillars offshore, each with a green cap.
    stacks = [(-2650, 650, 230, 1900), (-2350, 1500, 170, 1350), (1100, -2550, 280, 2300), (2500, 1900, 150, 1100)]
    for sx, sy, r, top in stacks:
        sd = np.hypot(X - sx, Y - sy) / r
        mask = 1.0 - smoothstep(0.70, 1.0, sd + 0.15 * (noise.fbm(X / 120.0, Y / 120.0) - 0.5))
        stack = terrace(top * mask, 260.0, 0.65) - 1.0 + mask
        h = np.where(mask > 0.02, np.maximum(h, stack), h)

    # Flat landing where the dock meets the cove (dock deck top is 72).
    # A ramp of about 24 degrees eases down to it so the slope stays walkable.
    ramp = 60.0 + np.maximum(0.0, 2150.0 - X) * 0.45
    band = 1.0 - smoothstep(220.0, 380.0, np.abs(Y - 150.0))
    eased = h - (h - np.minimum(h, ramp)) * band
    h = np.where((band > 0) & (h > 0), np.maximum(eased, np.minimum(h, 30.0)), h)
    return coords, h


# ----------------------------------------------------------------------------- textures

def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


PALETTE = {  # light -> dark, warm highlights, cool/violet shadows
    "grass":   ["#C9D774", "#A7BD55", "#86A043", "#62803D", "#4A6046"],
    "cliff":   ["#F0C995", "#D9A877", "#B9805A", "#8E5C4A", "#6A4458"],
    "sand":    ["#FFF6E3", "#F6E7CB", "#EAD3AA", "#D8BC92", "#BFA28A"],
    "seabed":  ["#E6D9B8", "#CDBE9A", "#B3A386", "#958A7E", "#7A7480"],
    "bark":    ["#9A6A46", "#7A4E34", "#5C3828", "#43282C"],
    "leaf":    ["#C2D86C", "#9CBA4E", "#7A9A3E", "#5A7840", "#42584A"],
    "blossom": ["#FFD9C8", "#F5A98C", "#E5816A", "#C8643A", "#9E4A52"],
}


def paint(name, rng, strata=False, strokes=900, stroke_len=(6, 18), vertical=False):
    ramp = [hexc(c) for c in PALETTE[name]]
    dark = len(ramp) - 1
    img = np.zeros((TEX_PX, TEX_PX, 3)) + ramp[2]
    if strata:  # horizontal rock strata with darker separations
        y = 0
        while y < TEX_PX:
            band = rng.randint(14, 34)
            img[y:y + band] = ramp[rng.choice([1, 2, 2, 3])]
            img[min(TEX_PX - 1, y + band - 2):y + band] = ramp[dark]
            y += band
    for _ in range(strokes):
        x, y = rng.randrange(TEX_PX), rng.randrange(TEX_PX)
        length = rng.randint(*stroke_len)
        width = rng.randint(2, 4)
        tone = ramp[rng.choice([0, 1, 1, dark - 1, dark - 1, dark])]
        angle = math.pi / 2 if vertical else (rng.uniform(-0.25, 0.25) if strata else rng.uniform(0, math.pi))
        for t in range(length):
            px = int(x + math.cos(angle) * t) % TEX_PX
            py = int(y + math.sin(angle) * t) % TEX_PX
            img[py:py + width, px:px + width] = img[py:py + width, px:px + width] * 0.4 + tone * 0.6
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
    return np.array(out.filter(ImageFilter.GaussianBlur(0.8)))


def paint_textures(rng):
    return {
        "grass": paint("grass", rng, strokes=1400, stroke_len=(5, 12)),
        "cliff": paint("cliff", rng, strata=True, strokes=700, stroke_len=(10, 30)),
        "sand": paint("sand", rng, strokes=700, stroke_len=(3, 8)),
        "seabed": paint("seabed", rng, strokes=500, stroke_len=(4, 10)),
        "bark": paint("bark", rng, strokes=600, stroke_len=(10, 30), vertical=True),
        "leaf": paint("leaf", rng, strokes=1500, stroke_len=(4, 10)),
        "blossom": paint("blossom", rng, strokes=1500, stroke_len=(4, 10)),
    }


def png_bytes(arr):
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, "PNG")
    return buf.getvalue()


# ----------------------------------------------------------------------------- mesh building
#
# Genshin-style shading set-up (see README notes in the docstring at the top):
#   terrain   smooth normals, one material; vertex colour R/G/B = grass/sand/rock weights,
#             A = large-scale colour tone (warm <-> cool), so layers blend softly.
#   rock      faceted rock clusters along the cliffs; vertex colour R = grass on upward faces.
#   leaf/...  soft round canopies with normals pointing out from the canopy centre.
#   grass     separate mesh of tapered blades; vertex colour R = height up the blade (wind),
#             G = per-clump tint variation. Normals follow the ground so grass blends in.


class Part:
    def __init__(self):
        self.pos, self.nrm, self.uv, self.col, self.idx = [], [], [], [], []

    def vert(self, p, n, uv, col=(1.0, 1.0, 1.0, 1.0)):
        self.pos.append(tuple(float(v) for v in p))
        self.nrm.append(tuple(float(v) for v in n))
        self.uv.append(tuple(float(v) for v in uv))
        self.col.append(tuple(float(v) for v in col))
        return len(self.pos) - 1

    def tri(self, a, b, c):
        self.idx.extend([a, b, c])


class Mesh:
    def __init__(self):
        self.parts = {}

    def part(self, name):
        return self.parts.setdefault(name, Part())

    def flat_tri(self, material, a, b, c, outward, col_fn=None):
        """A flat-shaded triangle facing `outward` (faceted rocks, trunks)."""
        a, b, c = (np.asarray(p, dtype=float) for p in (a, b, c))
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            return
        n /= ln
        if np.dot(n, outward) < 0:
            b, c, n = c, b, -n
        col = col_fn(n) if col_fn else (1.0, 1.0, 1.0, 1.0)
        part = self.part(material)
        ids = [part.vert(p, n, uv_for(p, n), col) for p in (a, b, c)]
        part.tri(*ids)


def uv_for(p, n):
    if abs(n[2]) >= 0.6:
        return (p[0] / TILE_CM, p[1] / TILE_CM)
    along = p[1] if abs(n[0]) > abs(n[1]) else p[0]
    return (along / TILE_CM, -p[2] / TILE_CM)


def grid_normals(h):
    gx = np.gradient(h, RES, axis=0)
    gy = np.gradient(h, RES, axis=1)
    n = np.stack([-gx, -gy, np.ones_like(h)], axis=-1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def terrain_weights(h, nrm, noise, X, Y):
    """Soft grass/sand/rock weights plus a large-scale tone, with painterly breakup."""
    breakup = noise.fbm(X / 180.0 + 11.0, Y / 180.0 + 5.0) - 0.5
    nz = nrm[..., 2]
    rock = smoothstep(0.80, 0.58, nz + 0.12 * breakup)
    sand = (1.0 - smoothstep(70.0, 150.0, h + 90.0 * breakup)) * (1.0 - rock)
    grass = np.clip(1.0 - rock - sand, 0.0, 1.0)
    total = rock + sand + grass + 1e-6
    tone = np.clip(noise.fbm(X / 1400.0 + 21.0, Y / 1400.0 + 9.0) * 1.6 - 0.3, 0.0, 1.0)
    return grass / total, sand / total, rock / total, tone


def build_terrain(mesh, coords, h, noise):
    n = len(coords)
    X, Y = np.meshgrid(coords, coords, indexing="ij")
    nrm = grid_normals(h)
    wg, ws, wr, tone = terrain_weights(h, nrm, noise, X, Y)
    part = mesh.part("terrain")
    ids = -np.ones((n, n), dtype=int)

    def vid(i, j):
        if ids[i, j] < 0:
            ids[i, j] = part.vert((coords[i], coords[j], h[i, j]), nrm[i, j],
                                  (coords[i] / TILE_CM, coords[j] / TILE_CM),
                                  (wg[i, j], ws[i, j], wr[i, j], tone[i, j]))
        return ids[i, j]

    for i in range(n - 1):
        for j in range(n - 1):
            if max(h[i, j], h[i + 1, j], h[i + 1, j + 1], h[i, j + 1]) < -120.0:
                continue
            a, b, c, d = vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)
            # Front faces up: (a, b, c) is clockwise seen from above in Unreal's left-handed space,
            # write_glb fixes winding for glTF.
            part.tri(a, c, b)
            part.tri(a, d, c)
    return nrm


def rock_chunk(mesh, centre, size, rng, up_bias=0.0):
    """A faceted Genshin-style rock: a jittered, squashed icosahedron, grass on upward facets."""
    t = (1 + 5 ** 0.5) / 2
    base = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
            (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
             (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    yaw = rng.uniform(0, 2 * math.pi)
    cy, sy = math.cos(yaw), math.sin(yaw)
    centre = np.array(centre, dtype=float)
    pts = []
    for v in base:
        v = np.array(v, dtype=float) / math.sqrt(1 + t * t)
        v = v * (1 + rng.uniform(-0.22, 0.22))
        v = np.array([v[0] * cy - v[1] * sy, v[0] * sy + v[1] * cy, v[2]])
        if v[2] > 0.35:  # flatten the top a little, like a weathered slab
            v[2] = 0.35 + (v[2] - 0.35) * 0.4
        pts.append(centre + v * np.array(size))

    def grass_on_top(n):
        return (float(np.clip(smoothstep(0.55, 0.85, n[2] + up_bias), 0, 1)), 0.0, 0.0, 1.0)

    for a, b, c in faces:
        mesh.flat_tri("rock", pts[a], pts[b], pts[c], (pts[a] + pts[b] + pts[c]) / 3 - centre, grass_on_top)


def place_cliff_rocks(mesh, coords, h, nrm, rng):
    """Clusters of faceted rocks along the steep cliffs and around the sea stacks."""
    placed = []
    n = len(coords)
    cells = [(i, j) for i in range(1, n - 1) for j in range(1, n - 1)
             if nrm[i, j, 2] < 0.62 and h[i, j] > -80]
    rng.shuffle(cells)
    for i, j in cells:
        x, y, z = coords[i], coords[j], h[i, j]
        if any((x - px) ** 2 + (y - py) ** 2 < 190.0 ** 2 for px, py in placed):
            continue
        placed.append((x, y))
        out = np.array([nrm[i, j, 0], nrm[i, j, 1]])
        out = out / (np.linalg.norm(out) or 1.0)
        r = rng.uniform(150, 300)
        tall = rng.uniform(1.0, 1.7)
        cx, cy = x + out[0] * r * 0.25, y + out[1] * r * 0.25
        rock_chunk(mesh, (cx, cy, z - r * 0.15), (r, r * rng.uniform(0.8, 1.1), r * tall), rng)
        if rng.random() < 0.45:  # a smaller companion to break up the silhouette
            r2 = r * rng.uniform(0.45, 0.65)
            rock_chunk(mesh, (cx + rng.uniform(-r, r), cy + rng.uniform(-r, r), z + r * 0.3), (r2, r2, r2 * 0.9), rng)
        if len(placed) >= 460:
            break
    return len(placed)


def build_arch(mesh, centre, span, thickness, depth, base_z, yaw_deg):
    """A natural rock arch standing in the water: a lumpy half-ring with grass on its crest."""
    cx, cy = centre
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    segs = 18

    def world(u, v, w):  # u along the span, v up, w across the depth
        return np.array([cx + u * c - w * s, cy + u * s + w * c, base_z + v])

    def grass_on_top(n):
        return (float(np.clip(smoothstep(0.55, 0.85, n[2]), 0, 1)), 0.0, 0.0, 1.0)

    ring = []
    for k in range(segs + 1):
        a = math.pi * k / segs
        lumpy = 1.0 + 0.08 * math.sin(5 * a)
        ring.append((a, span * lumpy, (span + thickness) * lumpy))
    across = np.array([-s, c, 0.0])
    for k in range(segs):
        (a0, ri0, ro0), (a1, ri1, ro1) = ring[k], ring[k + 1]
        am = (a0 + a1) / 2
        radial = np.array([math.cos(am) * c, math.cos(am) * s, math.sin(am)])
        w0, w1 = -depth / 2, depth / 2
        faces = [
            ([(ro0, a0, w0), (ro1, a1, w0), (ro1, a1, w1), (ro0, a0, w1)], radial),
            ([(ri0, a0, w0), (ri1, a1, w0), (ri1, a1, w1), (ri0, a0, w1)], -radial),
            ([(ri0, a0, w0), (ro0, a0, w0), (ro1, a1, w0), (ri1, a1, w0)], -across),
            ([(ri0, a0, w1), (ro0, a0, w1), (ro1, a1, w1), (ri1, a1, w1)], across),
        ]
        for quad, out in faces:
            q = [world(r * math.cos(a), r * math.sin(a), w) for r, a, w in quad]
            mesh.flat_tri("rock", q[0], q[1], q[2], out, grass_on_top)
            mesh.flat_tri("rock", q[0], q[2], q[3], out, grass_on_top)


def canopy(mesh, material, centre, radius, squash, rng):
    """A soft round canopy: icosphere with normals pointing out from the centre (anime-soft shading)."""
    t = (1 + 5 ** 0.5) / 2
    verts = [np.array(v, dtype=float) for v in
             [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
              (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]]
    verts = [v / np.linalg.norm(v) for v in verts]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
             (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(2):
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
    centre = np.array(centre, dtype=float)
    scale = np.array([1.0, 1.0, squash]) * radius
    part = mesh.part(material)
    ids = []
    for v in verts:
        bump = 1 + 0.10 * math.sin(v[0] * 7 + v[1] * 5) + rng.uniform(-0.03, 0.03)
        p = centre + v * scale * bump
        ids.append(part.vert(p, v, (p[0] / TILE_CM, p[1] / TILE_CM)))
    for a, b, c in faces:
        pa, pb, pc = (np.array(part.pos[k]) for k in (ids[a], ids[b], ids[c]))
        if np.dot(np.cross(pb - pa, pc - pa), (pa + pb + pc) / 3 - centre) < 0:
            part.tri(ids[a], ids[b], ids[c])
        else:
            part.tri(ids[a], ids[c], ids[b])


def trunk(mesh, base, top, r0, r1, sides=7):
    base, top = np.array(base, dtype=float), np.array(top, dtype=float)
    for k in range(sides):
        a0, a1 = 2 * math.pi * k / sides, 2 * math.pi * (k + 1) / sides
        d0 = np.array([math.cos(a0), math.sin(a0), 0.0])
        d1 = np.array([math.cos(a1), math.sin(a1), 0.0])
        p = [base + d0 * r0, base + d1 * r0, top + d1 * r1, top + d0 * r1]
        mesh.flat_tri("bark", p[0], p[1], p[2], d0 + d1)
        mesh.flat_tri("bark", p[0], p[2], p[3], d0 + d1)


def sample_height(coords, h, x, y):
    fx, fy = (x - coords[0]) / RES, (y - coords[0]) / RES
    i, j = int(math.floor(fx)), int(math.floor(fy))
    if not (0 <= i < len(coords) - 1 and 0 <= j < len(coords) - 1):
        return SEABED
    tx, ty = fx - i, fy - j
    return float((h[i, j] * (1 - tx) + h[i + 1, j] * tx) * (1 - ty)
                 + (h[i, j + 1] * (1 - tx) + h[i + 1, j + 1] * tx) * ty)


TREES = [(300, -700, 1.3), (-150, -1050, 1.1), (560, 650, 1.2), (-1150, -150, 1.4),
         (-350, 1000, 1.0), (-900, 700, 1.2), (900, -300, 1.0)]
BLOSSOM_TREE = (150, 250, 1.6)


def build_trees(mesh, coords, h, rng):
    for (x, y, s), foliage in [(t, "leaf") for t in TREES] + [(BLOSSOM_TREE, "blossom")]:
        g = sample_height(coords, h, x, y)
        if g < 100:
            continue
        lean = (rng.uniform(-40, 40) * s, rng.uniform(-40, 40) * s)
        top = (x + lean[0], y + lean[1], g + 380 * s)
        trunk(mesh, (x, y, g - 20), top, 26 * s, 15 * s)
        # One oversized soft canopy plus two smaller offset ones (asymmetric).
        canopy(mesh, foliage, (top[0], top[1], top[2] + 60 * s), 200 * s, 0.75, rng)
        canopy(mesh, foliage, (top[0] + 130 * s, top[1] - 60 * s, top[2] + 10 * s), 125 * s, 0.8, rng)
        canopy(mesh, foliage, (top[0] - 95 * s, top[1] + 95 * s, top[2] + 150 * s), 105 * s, 0.85, rng)


def build_grass(coords, h, nrm, noise, rng):
    """Dense tapered grass blades on the meadow, in clumps of mixed height."""
    grass = Mesh()
    part = grass.part("grass")
    X, Y = np.meshgrid(coords, coords, indexing="ij")
    wg, _, _, _ = terrain_weights(h, nrm, noise, X, Y)
    avoid = [(x, y, 120 * s) for x, y, s in TREES] + [(BLOSSOM_TREE[0], BLOSSOM_TREE[1], 150), (LIGHTHOUSE[0],
                                                                                              LIGHTHOUSE[1], 420)]
    clumps = 0
    tries = 0
    while clumps < 5200 and tries < 60000:
        tries += 1
        x, y = rng.uniform(-EXTENT, EXTENT), rng.uniform(-EXTENT, EXTENT)
        fi, fj = int((x - coords[0]) / RES), int((y - coords[0]) / RES)
        if not (0 <= fi < len(coords) and 0 <= fj < len(coords)):
            continue
        if h[fi, fj] < 110 or nrm[fi, fj, 2] < 0.82 or wg[fi, fj] < 0.6:
            continue
        if abs(y - 150) < 380 and x > 1200:  # keep the path to the dock clear
            continue
        if any((x - ax) ** 2 + (y - ay) ** 2 < r * r for ax, ay, r in avoid):
            continue
        g = sample_height(coords, h, x, y)
        ground_n = nrm[fi, fj]
        tint = rng.random()
        height = rng.uniform(28, 62) * (0.8 + 0.5 * noise.fbm(x / 500.0, y / 500.0))
        for _ in range(rng.randint(4, 7)):
            bx, by = x + rng.uniform(-14, 14), y + rng.uniform(-14, 14)
            yaw = rng.uniform(0, 2 * math.pi)
            lean = rng.uniform(-0.35, 0.35)
            hh = height * rng.uniform(0.7, 1.15)
            w = rng.uniform(5, 8)
            dx, dy = math.cos(yaw) * w / 2, math.sin(yaw) * w / 2
            lx, ly = -math.sin(yaw) * lean * hh, math.cos(yaw) * lean * hh
            mid_z = g + hh * 0.5
            v0 = part.vert((bx - dx, by - dy, g - 3), ground_n, (0, 0), (0.0, tint, 0, 1))
            v1 = part.vert((bx + dx, by + dy, g - 3), ground_n, (1, 0), (0.0, tint, 0, 1))
            v2 = part.vert((bx + dx * 0.6 + lx * 0.4, by + dy * 0.6 + ly * 0.4, mid_z), ground_n, (1, 0.5),
                           (0.5, tint, 0, 1))
            v3 = part.vert((bx - dx * 0.6 + lx * 0.4, by - dy * 0.6 + ly * 0.4, mid_z), ground_n, (0, 0.5),
                           (0.5, tint, 0, 1))
            v4 = part.vert((bx + lx, by + ly, g + hh), ground_n, (0.5, 1), (1.0, tint, 0, 1))
            part.tri(v0, v1, v2)
            part.tri(v0, v2, v3)
            part.tri(v3, v2, v4)
        clumps += 1
    return grass, clumps


# ----------------------------------------------------------------------------- glTF

def to_gltf(v):  # Unreal cm (left-handed, Z up) -> glTF metres (right-handed, Y up)
    return (v[0] / 100.0, v[2] / 100.0, v[1] / 100.0)


def write_glb(path, mesh, mesh_name, texture_for):
    """texture_for: material name -> texture array embedded for that material (or None)."""
    blob = bytearray()
    views, accessors, materials, images, gltf_textures, primitives = [], [], [], [], [], []

    def add_view(data, target=None):
        while len(blob) % 4:
            blob.append(0)
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            view["target"] = target
        blob.extend(data)
        views.append(view)
        return len(views) - 1

    for mat_index, (name, part) in enumerate(sorted(mesh.parts.items())):
        if not part.idx:
            continue
        pos = np.array([to_gltf(v) for v in part.pos], dtype=np.float32)
        nrm = np.array([to_gltf(v) for v in part.nrm], dtype=np.float32)
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
        uv = np.array(part.uv, dtype=np.float32)
        col = np.array(part.col, dtype=np.float32)
        tris = np.array(part.idx, dtype=np.uint32).reshape(-1, 3)
        # Make every triangle face along its vertex normals in glTF's right-handed space.
        p0, p1, p2 = pos[tris[:, 0]], pos[tris[:, 1]], pos[tris[:, 2]]
        face_n = np.cross(p1 - p0, p2 - p0)
        avg_n = nrm[tris[:, 0]] + nrm[tris[:, 1]] + nrm[tris[:, 2]]
        flip = (face_n * avg_n).sum(1) < 0
        tris[flip] = tris[flip][:, [0, 2, 1]]
        idx = tris.reshape(-1)
        a = len(accessors)
        accessors.append({"bufferView": add_view(pos.tobytes(), 34962), "componentType": 5126, "count": len(pos),
                          "type": "VEC3", "min": pos.min(0).tolist(), "max": pos.max(0).tolist()})
        accessors.append({"bufferView": add_view(nrm.tobytes(), 34962), "componentType": 5126, "count": len(nrm),
                          "type": "VEC3"})
        accessors.append({"bufferView": add_view(uv.tobytes(), 34962), "componentType": 5126, "count": len(uv),
                          "type": "VEC2"})
        accessors.append({"bufferView": add_view(col.tobytes(), 34962), "componentType": 5126, "count": len(col),
                          "type": "VEC4"})
        accessors.append({"bufferView": add_view(idx.tobytes(), 34963), "componentType": 5125, "count": len(idx),
                          "type": "SCALAR"})
        material = {"name": f"M_Island_{name}", "pbrMetallicRoughness": {"metallicFactor": 0.0,
                                                                         "roughnessFactor": 0.92}}
        tex = texture_for.get(name)
        if tex is not None:
            images.append({"name": name, "mimeType": "image/png", "bufferView": add_view(png_bytes(tex))})
            gltf_textures.append({"sampler": 0, "source": len(images) - 1})
            material["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(gltf_textures) - 1}
        materials.append(material)
        primitives.append({"attributes": {"POSITION": a, "NORMAL": a + 1, "TEXCOORD_0": a + 2, "COLOR_0": a + 3},
                           "indices": a + 4, "material": len(materials) - 1})

    doc = {
        "asset": {"version": "2.0", "generator": "Lyris make_island.py"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": mesh_name, "mesh": 0}],
        "meshes": [{"name": mesh_name, "primitives": primitives}],
        "materials": materials, "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    if images:
        doc.update({"textures": gltf_textures, "images": images,
                    "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]})
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    blob += b"\0" * (-len(blob) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))


# ----------------------------------------------------------------------------- preview

def render_preview(path, meshes, textures, elev=24, azim=-122):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    avg = {k: v.reshape(-1, 3).mean(0) / 255.0 for k, v in textures.items()}
    light = np.array([0.5, -0.4, 0.75])
    light /= np.linalg.norm(light)
    warm, cool = np.array([1.06, 1.02, 0.92]), np.array([0.92, 0.98, 1.06])
    grass_lo, grass_hi = np.array([0.40, 0.52, 0.25]), np.array([0.74, 0.80, 0.42])
    polys, colours = [], []
    for mesh, stride in meshes:
        for name, part in mesh.parts.items():
            pos, nrm, col = np.array(part.pos), np.array(part.nrm), np.array(part.col)
            tris = np.array(part.idx).reshape(-1, 3)[::stride]
            for t in tris:
                tri = [(x, y, max(z, 0.0)) for (x, y, z) in pos[t]]
                if max(z for _, _, z in tri) <= 0.0:
                    continue
                c = col[t].mean(0)
                n = nrm[t].mean(0)
                n /= np.linalg.norm(n) or 1.0
                if name == "terrain":
                    base = (avg["grass"] * c[0] + avg["sand"] * c[1] + avg["cliff"] * c[2]) * (warm * (1 - c[3]) + cool * c[3])
                elif name == "rock":
                    base = avg["cliff"] * (1 - c[0]) + avg["grass"] * c[0]
                elif name == "grass":
                    base = grass_lo * (1 - c[0]) + grass_hi * c[0]
                else:
                    base = avg[name]
                lit = 0.5 + 0.5 * max(0.0, float(np.dot(n, light)))
                if name in ("leaf", "blossom"):
                    lit = max(lit, 0.78)  # minimum light on canopies, Genshin-style
                shade = base * lit + np.array([0.08, 0.06, 0.16]) * (1 - lit)  # shadows tinted blue-violet
                polys.append(tri)
                colours.append(np.clip(shade, 0, 1))
    fig = plt.figure(figsize=(13, 8.5), dpi=110)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor((0.36, 0.76, 0.80))
    fig.patch.set_facecolor((0.36, 0.76, 0.80))
    ax.add_collection3d(Poly3DCollection(polys, facecolors=colours, edgecolors="none"))
    ax.set_xlim(-3000, 3000)
    ax.set_ylim(-3000, 3000)
    ax.set_zlim(0, 2400)
    ax.set_box_aspect((1, 1, 0.42))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    plt.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ----------------------------------------------------------------------------- main

def main():
    rng = random.Random(SEED)
    noise = ValueNoise(SEED + 1)
    textures = paint_textures(rng)
    coords, h = height_field()

    island = Mesh()
    nrm = build_terrain(island, coords, h, noise)
    n_rocks = place_cliff_rocks(island, coords, h, nrm, rng)
    build_arch(island, **ARCH)
    build_trees(island, coords, h, rng)
    grass, n_clumps = build_grass(coords, h, nrm, noise, rng)

    os.makedirs(os.path.join(HERE, "textures"), exist_ok=True)
    for name, arr in textures.items():
        Image.fromarray(arr, "RGB").save(os.path.join(HERE, "textures", f"{name}.png"))
    write_glb(os.path.join(HERE, "test_island.glb"), island, "SM_TestIsland",
              {"terrain": textures["grass"], "rock": textures["cliff"], "bark": textures["bark"],
               "leaf": textures["leaf"], "blossom": textures["blossom"]})
    write_glb(os.path.join(HERE, "test_island_grass.glb"), grass, "SM_TestIslandGrass", {})

    allpos = np.array([p for part in island.parts.values() for p in part.pos])
    lo, hi = allpos.min(0), allpos.max(0)
    j_dock = int(round((150 - coords[0]) / RES))
    shore = max(coords[i] for i in range(len(coords)) if h[i, j_dock] > 0)
    meta = {
        "grid_origin": float(coords[0]), "grid_step": RES, "grid_size": len(coords),
        "heights": [int(round(v)) for v in h.flatten()],  # index = i * size + j (i along X)
        "bounds_min": lo.tolist(), "bounds_max": hi.tolist(),
        "bounds_origin": ((lo + hi) / 2).tolist(), "bounds_extent": ((hi - lo) / 2).tolist(),
        "dock_shore_x": float(shore),
        "lighthouse": list(LIGHTHOUSE),
    }
    with open(os.path.join(HERE, "island_meta.json"), "w") as f:
        json.dump(meta, f)
    render_preview(os.path.join(HERE, "preview.png"), [(island, 1), (grass, 4)], textures)

    def count(m):
        return sum(len(p.idx) for p in m.parts.values()) // 3

    print(f"island triangles {count(island)} ({sorted(island.parts)})  rock clusters {n_rocks}")
    print(f"grass clumps {n_clumps}  grass triangles {count(grass)}")
    print("dock shore x", shore, " lighthouse ground", round(sample_height(coords, h, *LIGHTHOUSE)))
    print("bounds origin", [round(v) for v in meta["bounds_origin"]], "extent",
          [round(v) for v in meta["bounds_extent"]])


if __name__ == "__main__":
    main()
