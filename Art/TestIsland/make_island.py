"""Generates the Lyris test island: Sea of Remnants-style landforms, Genshin-style surfaces.

Look: lush green tops, dramatic sea cliffs in layered warm-stone ledges, a sheltered
sandy cove on the east where the dock lands, a gentle green slope up from the beach,
a rocky south-west headland for the lighthouse with a natural arch beyond it, and
sea stacks standing offshore. Painted textures: warm highlights, cool shadows.

Surfaces follow how Genshin Impact dresses its terrain (miHoYo, GDC 2021, and what the game
shows): smooth ground with softly blended texture layers plus a large-scale colour tone;
faceted rock clusters along cliffs with grass on their upward faces; dense swaying grass
blades tinted to the ground; soft round tree canopies that never go too dark.

Cozy, not forced: soft low-contrast textures (paint_textures.py), a worn footpath from the
dock up to the blossom tree and a bench beneath it looking over the cove, and wildflowers
that gather in a few loose patches.

Outputs (next to this script):
  test_island.glb        island mesh (terrain, rocks, arch, trees, bushes, bench), imported by
                         Content/Python/lyris_build_harbor.py (open in Blender to edit)
  test_island_grass.glb  grass blades and wildflowers (no collision)
  island_meta.json       height grid, bounds and dock shoreline for the Unreal script
  textures/*.png         painted tiles, flowers.png (atlas) and splat.png (R sand, G rock,
                         B path, A tone) covering the whole island
  preview.png, preview_close.png   quick renders for review

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



def png_bytes(arr):
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, "PNG")
    return buf.getvalue()



import paint_textures as pt  # noqa: E402  (soft seamless textures, flower atlas)

# A worn footpath from the dock landing up the cove to the blossom tree and its bench.
PATH_POINTS = [(2450, 150), (2000, 170), (1550, 240), (1100, 330), (700, 360), (420, 330)]
PATH_HALF_WIDTH = 70.0
BENCH = (470.0, 330.0, 0.0)  # x, y, facing yaw (0 = looking east over the cove)
SPLAT_PX = 1024


def path_polyline(samples_per_seg=12):
    pts = [np.array(p, dtype=float) for p in PATH_POINTS]
    out = []
    for k in range(len(pts) - 1):  # Catmull-Rom through the points
        p0 = pts[max(k - 1, 0)]
        p1, p2 = pts[k], pts[k + 1]
        p3 = pts[min(k + 2, len(pts) - 1)]
        for t in np.linspace(0, 1, samples_per_seg, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-1])
    return np.array(out)


def path_distance(X, Y):
    line = path_polyline()
    best = np.full(X.shape, 1e9)
    for a, b in zip(line[:-1], line[1:]):
        ab = b - a
        t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / (ab @ ab), 0, 1)
        d = np.hypot(X - (a[0] + t * ab[0]), Y - (a[1] + t * ab[1]))
        best = np.minimum(best, d)
    return best


def surface_weights(h, nrm_z, X, Y, noise):
    """Sand / rock / worn path / large-scale tone, with soft painterly breakup.
    Shared by the splat map, the vertex colours and the preview."""
    breakup = noise.fbm(X / 180.0 + 11.0, Y / 180.0 + 5.0) - 0.5
    rock = smoothstep(0.80, 0.58, nrm_z + 0.12 * breakup)
    sand = (1.0 - smoothstep(70.0, 150.0, h + 90.0 * breakup)) * (1.0 - rock)
    wobble = noise.fbm(X / 90.0 + 2.0, Y / 90.0 + 8.0) - 0.5
    path = (1.0 - smoothstep(PATH_HALF_WIDTH * 0.55, PATH_HALF_WIDTH * 1.25, path_distance(X, Y) + 45.0 * wobble))
    path = path * (1.0 - rock) * (1.0 - smoothstep(60.0, 20.0, h))
    tone = np.clip(noise.fbm(X / 1400.0 + 21.0, Y / 1400.0 + 9.0) * 1.6 - 0.3, 0.0, 1.0)
    return sand, rock, path, tone


def make_splat(coords, h, noise):
    """RGBA island-wide paint layer: R sand, G rock, B worn path, A warm(0)->cool(1) tone.
    Pixel (row, col) covers world (Y, X); the material samples it with UV = (X, Y)."""
    px = (np.arange(SPLAT_PX) + 0.5) / SPLAT_PX * (2 * EXTENT) - EXTENT
    X, Y = np.meshgrid(px, px, indexing="xy")  # rows follow Y, columns follow X
    fi = (X - coords[0]) / RES
    fj = (Y - coords[0]) / RES
    i0 = np.clip(np.floor(fi).astype(int), 0, len(coords) - 2)
    j0 = np.clip(np.floor(fj).astype(int), 0, len(coords) - 2)
    tx, ty = fi - i0, fj - j0
    hh = ((h[i0, j0] * (1 - tx) + h[i0 + 1, j0] * tx) * (1 - ty)
          + (h[i0, j0 + 1] * (1 - tx) + h[i0 + 1, j0 + 1] * tx) * ty)
    gy, gx = np.gradient(hh, 2 * EXTENT / SPLAT_PX)
    nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
    sand, rock, path, tone = surface_weights(hh, nz, X, Y, noise)
    rgba = np.stack([sand, rock, path, tone], axis=-1)
    return (np.clip(rgba, 0, 1) * 255).astype(np.uint8)


# ----------------------------------------------------------------------------- mesh building

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
        """A flat-shaded triangle facing `outward` (faceted rocks, trunks, bench)."""
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

    def box(self, material, centre, size, yaw_deg):
        cx, cy, cz = centre
        sx, sy, sz = (v / 2 for v in size)
        c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))

        def p(x, y, z):
            return (cx + x * c - y * s, cy + x * s + y * c, cz + z)

        corners = {(i, j, k): p(i * sx, j * sy, k * sz) for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)}
        quads = [((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)), ((-1, -1, -1), (-1, 1, -1), (-1, 1, 1), (-1, -1, 1)),
                 ((-1, 1, -1), (1, 1, -1), (1, 1, 1), (-1, 1, 1)), ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)),
                 ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)), ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1))]
        centre_v = np.array(centre, dtype=float)
        for q in quads:
            pts = [np.array(corners[k]) for k in q]
            out = np.mean(pts, axis=0) - centre_v
            self.flat_tri(material, pts[0], pts[1], pts[2], out)
            self.flat_tri(material, pts[0], pts[2], pts[3], out)


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


def build_terrain(mesh, coords, h, noise):
    n = len(coords)
    X, Y = np.meshgrid(coords, coords, indexing="ij")
    nrm = grid_normals(h)
    sand, rock, path, tone = surface_weights(h, nrm[..., 2], X, Y, noise)
    part = mesh.part("terrain")
    ids = -np.ones((n, n), dtype=int)

    def vid(i, j):
        if ids[i, j] < 0:
            ids[i, j] = part.vert((coords[i], coords[j], h[i, j]), nrm[i, j],
                                  (coords[i] / TILE_CM, coords[j] / TILE_CM),
                                  (sand[i, j], rock[i, j], path[i, j], tone[i, j]))
        return ids[i, j]

    for i in range(n - 1):
        for j in range(n - 1):
            if max(h[i, j], h[i + 1, j], h[i + 1, j + 1], h[i, j + 1]) < -120.0:
                continue
            a, b, c, d = vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)
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
        return (float(np.clip(smoothstep(0.72, 0.92, n[2] + up_bias), 0, 1)), 0.0, 0.0, 1.0)

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
        if x > 1100 and abs(y - 150) < 750:  # keep the cove, beach and dock clear
            continue
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
        return (float(np.clip(smoothstep(0.72, 0.92, n[2]), 0, 1)), 0.0, 0.0, 1.0)

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




def place_cliff_rocks(mesh, coords, h, nrm, rng):
    """Clusters of faceted rocks along the steep cliffs and around the sea stacks."""
    placed = []
    n = len(coords)
    cells = [(i, j) for i in range(1, n - 1) for j in range(1, n - 1)
             if nrm[i, j, 2] < 0.62 and h[i, j] > -80]
    rng.shuffle(cells)
    for i, j in cells:
        x, y, z = coords[i], coords[j], h[i, j]
        if x > 1100 and abs(y - 150) < 750:  # keep the cove, beach and dock clear
            continue
        if any((x - px) ** 2 + (y - py) ** 2 < 190.0 ** 2 for px, py in placed):
            continue
        placed.append((x, y))
        out = np.array([nrm[i, j, 0], nrm[i, j, 1]])
        out = out / (np.linalg.norm(out) or 1.0)
        r = rng.uniform(150, 300)
        tall = rng.uniform(1.0, 1.7)
        cx, cy = x + out[0] * r * 0.25, y + out[1] * r * 0.25
        rock_chunk(mesh, (cx, cy, z - r * 0.15), (r, r * rng.uniform(0.8, 1.1), r * tall), rng)
        if rng.random() < 0.45:
            r2 = r * rng.uniform(0.45, 0.65)
            rock_chunk(mesh, (cx + rng.uniform(-r, r), cy + rng.uniform(-r, r), z + r * 0.3), (r2, r2, r2 * 0.9), rng)
        if len(placed) >= 460:
            break
    return len(placed)


# ----------------------------------------------------------------------------- trees

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


def cloud_canopy(mesh, material, centre, radius, rng, puffs=7, squash=0.72):
    """A canopy built as one soft cloud: several overlapping puffs whose normals all point
    away from the canopy's centre, so light wraps the whole mass as one round shape
    (the trick stylized games use for anime-soft trees)."""
    centre = np.array(centre, dtype=float)
    verts, faces = icosphere(2)
    part = mesh.part(material)
    puff_list = [(np.array([0.0, 0.0, 0.35]), 0.62)]  # crown
    for k in range(puffs - 1):
        ang = 2 * math.pi * k / (puffs - 1) + rng.uniform(-0.3, 0.3)
        out = rng.uniform(0.42, 0.58)
        up = rng.uniform(-0.15, 0.2)
        puff_list.append((np.array([math.cos(ang) * out, math.sin(ang) * out, up]), rng.uniform(0.42, 0.56)))
    for offset, size in puff_list:
        pc = centre + offset * radius * np.array([1, 1, squash])
        ids = []
        for v in verts:
            wob = 1 + 0.07 * math.sin(v[0] * 6 + v[1] * 4 + offset[0] * 9) + rng.uniform(-0.025, 0.025)
            p = pc + v * radius * size * np.array([1, 1, 0.85]) * wob
            mass_n = (p - centre) / (radius * np.array([1, 1, squash]))
            n = 0.75 * mass_n / (np.linalg.norm(mass_n) or 1) + 0.25 * v
            n = n / np.linalg.norm(n)
            ids.append(part.vert(p, n, (p[0] / 150.0, p[1] / 150.0)))
        for a, b, c in faces:
            pa, pb, pc_ = (np.array(part.pos[k]) for k in (ids[a], ids[b], ids[c]))
            outward = (pa + pb + pc_) / 3 - pc
            if np.dot(np.cross(pb - pa, pc_ - pa), outward) >= 0:
                part.tri(ids[a], ids[b], ids[c])
            else:
                part.tri(ids[a], ids[c], ids[b])


def tapered_limb(mesh, points, radii, sides=8):
    """A smooth tapering trunk or branch through `points` with matching `radii`."""
    rings = []
    for k, (p, r) in enumerate(zip(points, radii)):
        p = np.array(p, dtype=float)
        d = np.array(points[min(k + 1, len(points) - 1)], dtype=float) - np.array(points[max(k - 1, 0)], dtype=float)
        d = d / (np.linalg.norm(d) or 1)
        side = np.cross(d, [0, 0, 1.0]) if abs(d[2]) < 0.95 else np.array([1.0, 0, 0])
        side /= np.linalg.norm(side)
        up = np.cross(side, d)
        rings.append([(p + (side * math.cos(a) + up * math.sin(a)) * r,
                       side * math.cos(a) + up * math.sin(a))
                      for a in np.linspace(0, 2 * math.pi, sides, endpoint=False)])
    part = mesh.part("bark")
    for k in range(len(rings) - 1):
        for s in range(sides):
            s1 = (s + 1) % sides
            (p00, n00), (p01, n01) = rings[k][s], rings[k][s1]
            (p10, n10), (p11, n11) = rings[k + 1][s], rings[k + 1][s1]
            ids = [part.vert(p, n, (s / sides, (k + j) * 0.5)) for (p, n), j in
                   (((p00, n00), 0), ((p01, n01), 0), ((p11, n11), 1), ((p10, n10), 1))]
            outward = (n00 + n01 + n10 + n11) / 4
            a, b, c, d = ids
            pa, pb, pc_ = (np.array(part.pos[x]) for x in (a, b, c))
            if np.dot(np.cross(pb - pa, pc_ - pa), outward) >= 0:
                part.tri(a, b, c)
                part.tri(a, c, d)
            else:
                part.tri(a, c, b)
                part.tri(a, d, c)


def sample_height(coords, h, x, y):
    fx, fy = (x - coords[0]) / RES, (y - coords[0]) / RES
    i, j = int(math.floor(fx)), int(math.floor(fy))
    if not (0 <= i < len(coords) - 1 and 0 <= j < len(coords) - 1):
        return SEABED
    tx, ty = fx - i, fy - j
    return float((h[i, j] * (1 - tx) + h[i + 1, j] * tx) * (1 - ty)
                 + (h[i, j + 1] * (1 - tx) + h[i + 1, j + 1] * tx) * ty)


# (x, y, size): broadleaf trees around the meadow, kept off the path.
TREES = [(300, -700, 1.25), (-150, -1050, 1.05), (560, 760, 1.15), (-1150, -150, 1.35),
         (-350, 1000, 1.0), (-900, 700, 1.2), (950, -350, 0.95), (-600, -450, 1.1), (1300, 700, 0.9)]
BLOSSOM_TREE = (180, 230, 1.45)
BUSHES = [(1750, 560, 0.9), (1650, -180, 0.8), (900, 120, 0.7), (-200, 650, 0.85), (650, -1000, 0.9),
          (-1300, 300, 1.0), (1250, -800, 0.8), (-700, 1300, 0.9), (300, 520, 0.6), (2100, 480, 0.7)]


def build_tree(mesh, coords, h, rng, x, y, s, foliage):
    g = sample_height(coords, h, x, y)
    if g < 100:
        return
    lean = np.array([rng.uniform(-50, 50), rng.uniform(-50, 50), 0.0]) * s
    height = 360 * s
    # Trunk: wide flared root, gentle taper and a slight curve.
    pts = [np.array([x, y, g - 25]) + lean * (k / 4) ** 1.6 + np.array([0, 0, height * k / 4]) for k in range(5)]
    radii = [44 * s, 30 * s, 24 * s, 20 * s, 16 * s]
    tapered_limb(mesh, pts, radii)
    top = pts[-1]
    canopy_c = top + np.array([0, 0, 120 * s])
    # Two or three branches reaching up into the canopy.
    for k in range(rng.integers(2, 4)):
        ang = rng.uniform(0, 2 * math.pi)
        start = pts[2] + np.array([0, 0, rng.uniform(0, 40) * s])
        end = canopy_c + np.array([math.cos(ang) * 120 * s, math.sin(ang) * 120 * s, rng.uniform(-30, 20) * s])
        midp = (start + end) / 2 + np.array([0, 0, 30 * s])
        tapered_limb(mesh, [start, midp, end], [13 * s, 10 * s, 7 * s], sides=6)
    cloud_canopy(mesh, foliage, canopy_c, 250 * s, rng, puffs=int(rng.integers(6, 9)))


def build_bush(mesh, coords, h, rng, x, y, s):
    g = sample_height(coords, h, x, y)
    if g < 60:
        return
    cloud_canopy(mesh, "leaf", (x, y, g + 55 * s), 130 * s, rng, puffs=5, squash=0.6)


def build_bench(mesh, coords, h):
    x, y, yaw = BENCH
    g = sample_height(coords, h, x, y)
    seat_z = g + 45
    mesh.box("wood", (x, y, seat_z), (48, 150, 7), yaw)                      # seat
    mesh.box("wood", (x - 26, y, seat_z + 35), (6, 150, 34), yaw)            # backrest (behind, looking east)
    for dy in (-62, 62):
        mesh.box("wood", (x, y + dy, g + 20), (40, 8, 50), yaw)              # legs
        mesh.box("wood", (x - 26, y + dy, g + 50), (6, 8, 70), yaw)          # back posts


# ----------------------------------------------------------------------------- grass and flowers

def build_grass(coords, h, nrm, noise, rng):
    """Dense tapered grass blades in mixed clumps, plus little patches of wildflowers.
    Blade UV v runs 0 at the root to 1 at the tip (the material uses it for colour and wind)."""
    meadow = Mesh()
    blades = meadow.part("grass")
    flowers = meadow.part("flower")
    X, Y = np.meshgrid(coords, coords, indexing="ij")
    sand, rock, path, _ = surface_weights(h, nrm[..., 2], X, Y, noise)
    grassy = (1 - sand) * (1 - rock) * (1 - path)
    avoid = ([(tx, ty, 110 * ts) for tx, ty, ts in TREES] + [(BLOSSOM_TREE[0], BLOSSOM_TREE[1], 140),
             (LIGHTHOUSE[0], LIGHTHOUSE[1], 420), (BENCH[0], BENCH[1], 120)])

    def spot_ok(x, y):
        fi, fj = int((x - coords[0]) / RES), int((y - coords[0]) / RES)
        if not (0 <= fi < len(coords) and 0 <= fj < len(coords)):
            return None
        if h[fi, fj] < 110 or nrm[fi, fj, 2] < 0.82 or grassy[fi, fj] < 0.55:
            return None
        if any((x - ax) ** 2 + (y - ay) ** 2 < r * r for ax, ay, r in avoid):
            return None
        return fi, fj

    clumps = tries = 0
    while clumps < 5200 and tries < 80000:
        tries += 1
        x, y = rng.uniform(-EXTENT, EXTENT), rng.uniform(-EXTENT, EXTENT)
        cell = spot_ok(x, y)
        if cell is None:
            continue
        g = sample_height(coords, h, x, y)
        ground_n = nrm[cell]
        height = rng.uniform(28, 60) * (0.75 + 0.55 * noise.fbm(x / 500.0, y / 500.0))
        for _ in range(rng.integers(4, 8)):
            bx, by = x + rng.uniform(-14, 14), y + rng.uniform(-14, 14)
            yaw = rng.uniform(0, 2 * math.pi)
            lean = rng.uniform(-0.35, 0.35)
            hh = height * rng.uniform(0.7, 1.15)
            w = rng.uniform(5, 8)
            dx, dy = math.cos(yaw) * w / 2, math.sin(yaw) * w / 2
            lx, ly = -math.sin(yaw) * lean * hh, math.cos(yaw) * lean * hh
            mz = g + hh * 0.5
            v0 = blades.vert((bx - dx, by - dy, g - 3), ground_n, (0, 0))
            v1 = blades.vert((bx + dx, by + dy, g - 3), ground_n, (1, 0))
            v2 = blades.vert((bx + dx * 0.6 + lx * 0.4, by + dy * 0.6 + ly * 0.4, mz), ground_n, (1, 0.5))
            v3 = blades.vert((bx - dx * 0.6 + lx * 0.4, by - dy * 0.6 + ly * 0.4, mz), ground_n, (0, 0.5))
            v4 = blades.vert((bx + lx, by + ly, g + hh), ground_n, (0.5, 1))
            blades.tri(v0, v1, v2)
            blades.tri(v0, v2, v3)
            blades.tri(v3, v2, v4)
        clumps += 1

    # Wildflowers gather in a few soft patches rather than sprinkled evenly.
    patches = [(rng.uniform(-1300, 1500), rng.uniform(-1200, 1200), rng.uniform(220, 420), int(rng.integers(0, 4)))
               for _ in range(16)]
    n_flowers = 0
    for px, py, pr, kind in patches:
        for _ in range(70):
            a, r = rng.uniform(0, 2 * math.pi), pr * math.sqrt(rng.random())
            x, y = px + math.cos(a) * r, py + math.sin(a) * r
            cell = spot_ok(x, y)
            if cell is None:
                continue
            g = sample_height(coords, h, x, y)
            k = kind if rng.random() < 0.8 else int(rng.integers(0, 4))
            u0, v0 = (k % 2) * 0.5, (k // 2) * 0.5
            size = rng.uniform(22, 34)
            z0 = g + rng.uniform(8, 18)
            yaw = rng.uniform(0, math.pi)
            for ang in (yaw, yaw + math.pi / 2):  # two crossed cards
                dx, dy = math.cos(ang) * size / 2, math.sin(ang) * size / 2
                n = nrm[cell]
                q = [flowers.vert((x - dx, y - dy, z0), n, (u0, v0 + 0.5)),
                     flowers.vert((x + dx, y + dy, z0), n, (u0 + 0.5, v0 + 0.5)),
                     flowers.vert((x + dx, y + dy, z0 + size), n, (u0 + 0.5, v0)),
                     flowers.vert((x - dx, y - dy, z0 + size), n, (u0, v0))]
                flowers.tri(q[0], q[1], q[2])
                flowers.tri(q[0], q[2], q[3])
            n_flowers += 1
    return meadow, clumps, n_flowers


# ----------------------------------------------------------------------------- glTF

def to_gltf(v):  # Unreal cm (left-handed, Z up) -> glTF metres (right-handed, Y up)
    return (v[0] / 100.0, v[2] / 100.0, v[1] / 100.0)


def write_glb(path, mesh, mesh_name, upward_parts=()):
    """Textures are imported separately by the Unreal script, so none are embedded.
    Parts in `upward_parts` keep their winding (thin cards and blades, drawn two-sided)."""
    blob = bytearray()
    views, accessors, materials, primitives = [], [], [], []

    def add_view(data, target=None):
        while len(blob) % 4:
            blob.append(0)
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            view["target"] = target
        blob.extend(data)
        views.append(view)
        return len(views) - 1

    for name, part in sorted(mesh.parts.items()):
        if not part.idx:
            continue
        pos = np.array([to_gltf(v) for v in part.pos], dtype=np.float32)
        nrm = np.array([to_gltf(v) for v in part.nrm], dtype=np.float32)
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
        uv = np.array(part.uv, dtype=np.float32)
        col = np.array(part.col, dtype=np.float32)
        tris = np.array(part.idx, dtype=np.uint32).reshape(-1, 3)
        if name not in upward_parts:
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
        materials.append({"name": f"M_Island_{name}", "pbrMetallicRoughness": {"metallicFactor": 0.0,
                                                                                "roughnessFactor": 0.9}})
        primitives.append({"attributes": {"POSITION": a, "NORMAL": a + 1, "TEXCOORD_0": a + 2, "COLOR_0": a + 3},
                           "indices": a + 4, "material": len(materials) - 1})

    doc = {"asset": {"version": "2.0", "generator": "Lyris make_island.py"},
           "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": mesh_name, "mesh": 0}],
           "meshes": [{"name": mesh_name, "primitives": primitives}], "materials": materials,
           "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    blob += b"\0" * (-len(blob) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))


# ----------------------------------------------------------------------------- preview

def render_preview(out_path, meshes, textures, elev=24, azim=-122, zoom=1.0, centre=(0, 0, 0)):
    """Rough software preview that mimics the Unreal materials (splat blend, soft canopies)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    avg = {k: v[..., :3].reshape(-1, 3).mean(0) / 255.0 for k, v in textures.items()}
    light = np.array([0.5, -0.4, 0.75])
    light /= np.linalg.norm(light)
    warm, cool = np.array([1.05, 1.02, 0.94]), np.array([0.95, 0.99, 1.05])
    leaf_dark, leaf_sun = np.array([0.36, 0.50, 0.36]), np.array([0.78, 0.86, 0.50])
    pink_dark, pink_sun = np.array([0.80, 0.52, 0.56]), np.array([1.0, 0.84, 0.78])
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
                lit = 0.55 + 0.45 * max(0.0, float(np.dot(n, light)))
                if name == "terrain":
                    sand, rock, path, tone = c
                    base = avg["grass"] * (1 - sand) + avg["sand"] * sand
                    base = base * (1 - path) + avg["path"] * path
                    base = base * (1 - rock) + avg["cliff"] * rock
                    base = base * (warm * (1 - tone) + cool * tone)
                elif name == "rock":
                    g = float(np.clip((n[2] - 0.72) / 0.2, 0, 1))
                    base = avg["cliff"] * (1 - g) + avg["grass"] * g
                elif name in ("leaf", "blossom"):
                    up = float(np.clip(n[2] * 0.5 + 0.5, 0, 1))
                    lo, hi = (leaf_dark, leaf_sun) if name == "leaf" else (pink_dark, pink_sun)
                    base = lo * (1 - up) + hi * up
                    lit = 1.0
                elif name == "grass":
                    base = np.array([0.62, 0.72, 0.36])
                elif name == "flower":
                    base = np.array([0.98, 0.90, 0.92])
                    lit = 1.0
                else:
                    base = avg["bark"] if name == "bark" else avg["path"]
                shade = base * lit + np.array([0.10, 0.08, 0.16]) * (1 - lit)
                polys.append(tri)
                colours.append(np.clip(shade, 0, 1))
    fig = plt.figure(figsize=(13, 8.5), dpi=110)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor((0.43, 0.78, 0.82))
    fig.patch.set_facecolor((0.43, 0.78, 0.82))
    ax.add_collection3d(Poly3DCollection(polys, facecolors=colours, edgecolors="none"))
    r = 3000 / zoom
    ax.set_xlim(centre[0] - r, centre[0] + r)
    ax.set_ylim(centre[1] - r, centre[1] + r)
    ax.set_zlim(centre[2], centre[2] + 2400 / zoom)
    ax.set_box_aspect((1, 1, 0.42))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    plt.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


# ----------------------------------------------------------------------------- main

def main():
    rng = random.Random(SEED)
    nrng = np.random.default_rng(SEED)
    noise = ValueNoise(SEED + 1)
    coords, h = height_field()

    textures = pt.paint_all()
    textures["flowers"] = pt.flower_atlas()
    textures["splat"] = make_splat(coords, h, noise)
    os.makedirs(os.path.join(HERE, "textures"), exist_ok=True)
    for old in os.listdir(os.path.join(HERE, "textures")):
        os.remove(os.path.join(HERE, "textures", old))
    for name, arr in textures.items():
        pt.save(arr, os.path.join(HERE, "textures", f"{name}.png"))

    island = Mesh()
    nrm = build_terrain(island, coords, h, noise)
    n_rocks = place_cliff_rocks(island, coords, h, nrm, rng)
    build_arch(island, **ARCH)
    for x, y, s in TREES:
        build_tree(island, coords, h, nrng, x, y, s, "leaf")
    build_tree(island, coords, h, nrng, *BLOSSOM_TREE, "blossom")
    for x, y, s in BUSHES:
        build_bush(island, coords, h, nrng, x, y, s)
    build_bench(island, coords, h)
    meadow, n_clumps, n_flowers = build_grass(coords, h, nrm, noise, nrng)

    write_glb(os.path.join(HERE, "test_island.glb"), island, "SM_TestIsland")
    write_glb(os.path.join(HERE, "test_island_grass.glb"), meadow, "SM_TestIslandGrass",
              upward_parts=("grass", "flower"))
    old_preview = os.path.join(HERE, "preview.png")
    render_preview(old_preview, [(island, 1), (meadow, 6)], textures)
    render_preview(os.path.join(HERE, "preview_close.png"), [(island, 1), (meadow, 2)], textures,
                   elev=20, azim=15, zoom=2.4, centre=(900, 250, 0))

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
        "splat_extent": EXTENT,
    }
    with open(os.path.join(HERE, "island_meta.json"), "w") as f:
        json.dump(meta, f)

    def count(m):
        return sum(len(p.idx) for p in m.parts.values()) // 3

    print(f"island triangles {count(island)} ({sorted(island.parts)})  rock clusters {n_rocks}")
    print(f"grass clumps {n_clumps}  flowers {n_flowers}  meadow triangles {count(meadow)}")
    print("dock shore x", shore, " lighthouse ground", round(sample_height(coords, h, *LIGHTHOUSE)))
    print("bounds origin", [round(v) for v in meta["bounds_origin"]], "extent",
          [round(v) for v in meta["bounds_extent"]])


if __name__ == "__main__":
    main()
