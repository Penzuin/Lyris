"""Soft, seamless painted textures for the Lyris test island.

Cozy rather than busy: low contrast, large soft colour patches, a few gentle dabs,
warm lights and cool lavender-leaning darks. Every tile wraps seamlessly.
"""

import math

import numpy as np
from PIL import Image

SIZE = 512


def hexc(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


# light -> dark. Warm lights, cool lavender-leaning darks, gentle steps between tones.
RAMPS = {
    "grass":   ["#D3DE8A", "#B9CC6E", "#9DB75A", "#83A050", "#6C8650"],
    "sand":    ["#FBF1DE", "#F3E5C8", "#EAD8B6", "#DDC8A5", "#CDB89C"],
    "cliff":   ["#EDCFA8", "#DDB78F", "#C99D7C", "#AE8474", "#8E7076"],
    "path":    ["#E2C79E", "#D2B38A", "#BF9D78", "#A78770", "#8D7470"],
    "bark":    ["#A7806A", "#8C6656", "#735248", "#5E4644"],
    "leaf":    ["#CFE08E", "#B0CB72", "#93B360", "#789A58", "#5E7D58"],
    "blossom": ["#FFE4DA", "#FBC8B8", "#F2A898", "#E08A86", "#C27682"],
}


def periodic_noise(rng, cells, size=SIZE):
    """Smooth noise that tiles perfectly: random low frequencies, built in Fourier space."""
    kx = np.fft.fftfreq(size) * size
    ky = np.fft.rfftfreq(size) * size
    k = np.hypot(kx[:, None], ky[None, :])
    keep = (k > 0) & (k <= cells)
    spectrum = (rng.standard_normal(k.shape) + 1j * rng.standard_normal(k.shape)) * keep / (1.0 + k)
    noise = np.fft.irfft2(spectrum, s=(size, size))
    return (noise - noise.min()) / (noise.max() - noise.min() + 1e-9)


def fbm(rng, base_cells, octaves=4, size=SIZE):
    total = np.zeros((size, size))
    amp, norm = 1.0, 0.0
    cells = base_cells
    for _ in range(octaves):
        total += amp * periodic_noise(rng, cells, size)
        norm += amp
        amp *= 0.5
        cells *= 2
    total /= norm
    return (total - total.min()) / (total.max() - total.min() + 1e-9)


def ramp_map(values, ramp):
    """Maps 0..1 to a colour ramp (0 = darkest end, 1 = lightest)."""
    cols = [hexc(c) for c in reversed(ramp)]
    pos = np.clip(values, 0, 1) * (len(cols) - 1)
    lo = np.floor(pos).astype(int)
    hi = np.minimum(lo + 1, len(cols) - 1)
    t = (pos - lo)[..., None]
    cols = np.array(cols)
    return cols[lo] * (1 - t) + cols[hi] * t


def soft_dabs(img, rng, ramp, count, radius, strength=0.35, stretch=1.0, angle=0.0):
    """Gentle painterly dabs: soft ellipses blended in, wrapping at the edges."""
    size = img.shape[0]
    yy, xx = np.mgrid[0:size, 0:size]
    cols = [hexc(c) for c in ramp]
    for _ in range(count):
        cx, cy = rng.random() * size, rng.random() * size
        r = radius * rng.uniform(0.6, 1.4)
        col = cols[rng.integers(0, len(cols))]
        dx = (xx - cx + size / 2) % size - size / 2
        dy = (yy - cy + size / 2) % size - size / 2
        ca, sa = math.cos(angle), math.sin(angle)
        u, v = dx * ca + dy * sa, -dx * sa + dy * ca
        d = (u / (r * stretch)) ** 2 + (v / r) ** 2
        m = np.clip(1 - d, 0, 1) ** 2 * strength
        img[:] = img * (1 - m[..., None]) + col * m[..., None]


def paint(name, rng):
    ramp = RAMPS[name]
    if name == "grass":
        v = 0.55 * fbm(rng, 4) + 0.45 * fbm(rng, 16, 3)
        img = ramp_map(0.25 + 0.6 * v, ramp)
        soft_dabs(img, rng, ramp[:3], 70, 14, 0.25, 1.8, 0.4)
    elif name == "sand":
        v = 0.6 * fbm(rng, 4) + 0.4 * fbm(rng, 32, 2)
        img = ramp_map(0.35 + 0.5 * v, ramp)
        soft_dabs(img, rng, ramp[2:], 40, 5, 0.3)
    elif name == "cliff":
        size = SIZE
        y = np.arange(size)[:, None] / size
        strata = 0.5 + 0.5 * np.sin(2 * math.pi * (y * 6 + 0.35 * fbm(rng, 4)))
        v = 0.5 * strata + 0.5 * fbm(rng, 8, 3)
        img = ramp_map(0.15 + 0.75 * v, ramp)
        soft_dabs(img, rng, ramp, 60, 18, 0.2, 2.5, 0.0)
    elif name == "path":
        v = 0.6 * fbm(rng, 6) + 0.4 * fbm(rng, 24, 2)
        img = ramp_map(0.3 + 0.55 * v, ramp)
        soft_dabs(img, rng, ramp[2:], 90, 6, 0.45)  # little pebbles
        soft_dabs(img, rng, ramp[:1], 40, 4, 0.4)
    elif name == "bark":
        x = np.arange(SIZE)[None, :] / SIZE
        streaks = 0.5 + 0.5 * np.sin(2 * math.pi * (x * 10 + 0.5 * fbm(rng, 4)))
        v = 0.55 * streaks + 0.45 * fbm(rng, 8, 3)
        img = ramp_map(0.15 + 0.75 * v, ramp)
    else:  # leaf / blossom: soft clusters, the shading comes from the material
        v = 0.5 * fbm(rng, 8) + 0.5 * fbm(rng, 24, 2)
        img = ramp_map(0.3 + 0.6 * v, ramp)
        soft_dabs(img, rng, ramp[:2], 80, 8, 0.35)
    return np.clip(img, 0, 255).astype(np.uint8)


def paint_all(seed=5):
    rng = np.random.default_rng(seed)
    return {name: paint(name, rng) for name in RAMPS}


def flower_atlas(seed=9, size=256):
    """2x2 atlas of little wildflowers on transparent backgrounds (RGBA):
    cream daisy, pale pink, soft butter-yellow, lavender."""
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size, 4), dtype=float)
    cell = size // 2
    flowers = [("#FFF8EC", "#F2C14E"), ("#F9C9D2", "#F6E3A8"), ("#F8E08A", "#E9A84B"), ("#CDB8EC", "#F6E3A8")]
    yy, xx = np.mgrid[0:cell, 0:cell]
    for k, (petal, centre) in enumerate(flowers):
        ox, oy = (k % 2) * cell, (k // 2) * cell
        tile = np.zeros((cell, cell, 4))
        for _ in range(3):  # three small blooms per cell, like a tiny clump
            cx, cy = rng.uniform(cell * 0.3, cell * 0.7), rng.uniform(cell * 0.3, cell * 0.7)
            r = rng.uniform(cell * 0.12, cell * 0.18)
            petals = 5
            ang = np.arctan2(yy - cy, xx - cx)
            dist = np.hypot(xx - cx, yy - cy)
            shape = r * (0.75 + 0.25 * np.cos(petals * ang + rng.uniform(0, 6)))
            petal_mask = np.clip((shape - dist) / 2.0, 0, 1)
            centre_mask = np.clip((r * 0.32 - dist) / 1.5, 0, 1)
            col = hexc(petal) * (1 - centre_mask[..., None]) + hexc(centre) * centre_mask[..., None]
            shade = 1 - 0.18 * np.clip(dist / r, 0, 1)[..., None]
            a = np.maximum(petal_mask, centre_mask)
            tile[..., :3] = tile[..., :3] * (1 - a[..., None]) + col * shade * a[..., None]
            tile[..., 3] = np.maximum(tile[..., 3], a)
        img[oy:oy + cell, ox:ox + cell] = tile
    img[..., 3] *= 255
    return np.clip(img, 0, 255).astype(np.uint8)


def save(arr, path):
    mode = "RGBA" if arr.shape[-1] == 4 else "RGB"
    Image.fromarray(arr, mode).save(path)


# ----------------------------------------------------------------------------- foliage atlases

def _leaf_shape(xx, yy, cx, cy, length, width, angle, pointed=True):
    """Soft-edged leaf mask: an ellipse, optionally pinched to a point at the tip."""
    ca, sa = math.cos(angle), math.sin(angle)
    u = (xx - cx) * ca + (yy - cy) * sa
    v = -(xx - cx) * sa + (yy - cy) * ca
    t = np.clip(u / length, -1, 1)
    half = width * np.sqrt(np.clip(1 - t * t, 0, 1))
    if pointed:
        half = half * np.clip(1.15 - 0.55 * np.clip(t, 0, 1), 0, 1)
    inside = np.clip((half - np.abs(v)) / 1.4, 0, 1) * (np.abs(u) <= length)
    return inside, t


def leaf_atlas(seed=21, size=512):
    """2x2 atlas of leaf clumps for canopy cards (RGBA):
    0 broadleaf clump, 1 small round birch leaves, 2 pine needle tuft, 3 blossom petals."""
    rng = np.random.default_rng(seed)
    cell = size // 2
    img = np.zeros((size, size, 4))
    yy, xx = np.mgrid[0:cell, 0:cell].astype(float)
    specs = [
        dict(ramp=["#D9E894", "#B6D072", "#93B45E", "#749656"], n=58, length=(24, 38), width=(10, 15), pointed=True),
        dict(ramp=["#ECF2A8", "#D2E38A", "#B4CC72", "#97B262"], n=72, length=(14, 20), width=(10, 14), pointed=False),
        dict(ramp=["#9FC08E", "#7FA47A", "#62886A", "#4C6E5E"], n=90, length=(30, 46), width=(2.2, 3.2), pointed=True),
        dict(ramp=["#FFF1EA", "#FFD7C9", "#F8B9AA", "#EA9C98"], n=70, length=(14, 20), width=(11, 15), pointed=False),
    ]
    for k, spec in enumerate(specs):
        tile = np.zeros((cell, cell, 4))
        cols = [hexc(c) for c in spec["ramp"]]
        for _ in range(spec["n"]):
            ang = rng.uniform(0, 2 * math.pi)
            dist = cell * 0.34 * math.sqrt(rng.random())
            cx, cy = cell / 2 + math.cos(ang) * dist, cell / 2 + math.sin(ang) * dist
            length = rng.uniform(*spec["length"])
            width = rng.uniform(*spec["width"])
            angle = ang + rng.uniform(-0.6, 0.6) if k != 2 else ang
            mask, t = _leaf_shape(xx, yy, cx, cy, length, width, angle, spec["pointed"])
            outer = dist / (cell * 0.34)
            base = cols[min(3, int(rng.integers(0, 2) + outer * 2))]
            shade = (1.05 - 0.18 * np.clip(-t, 0, 1))[..., None]  # lighter toward the leaf tip
            vein = np.clip(1 - np.abs((-(xx - cx) * math.sin(angle) + (yy - cy) * math.cos(angle))) / 1.2, 0, 1)
            col = base * shade * (1 - 0.08 * vein[..., None])
            a = mask[..., None]
            tile[..., :3] = tile[..., :3] * (1 - a) + col * a
            tile[..., 3] = np.maximum(tile[..., 3], mask)
        ox, oy = (k % 2) * cell, (k // 2) * cell
        img[oy:oy + cell, ox:ox + cell] = tile
    img[..., 3] *= 255
    return np.clip(img, 0, 255).astype(np.uint8)


def plant_atlas(seed=33, size=512):
    """2x2 atlas of ground plants for crossed cards (RGBA):
    0 fern frond, 1 dune grass tuft, 2 dandelion puff, 3 lavender-blue flower spike.
    Each plant stands on the bottom edge of its cell."""
    rng = np.random.default_rng(seed)
    cell = size // 2
    img = np.zeros((size, size, 4))
    yy, xx = np.mgrid[0:cell, 0:cell].astype(float)

    def stroke(tile, x0, y0, x1, y1, width, col):
        d = np.array([x1 - x0, y1 - y0], dtype=float)
        L = np.hypot(*d) or 1.0
        t = np.clip(((xx - x0) * d[0] + (yy - y0) * d[1]) / (L * L), 0, 1)
        dist = np.hypot(xx - (x0 + t * d[0]), yy - (y0 + t * d[1]))
        w = width * (1 - 0.7 * t)
        m = np.clip((w - dist) / 1.2, 0, 1)
        tile[..., :3] = tile[..., :3] * (1 - m[..., None]) + np.array(col) * m[..., None]
        tile[..., 3] = np.maximum(tile[..., 3], m)

    cells = []
    # 0 fern: arching fronds with paired leaflets.
    tile = np.zeros((cell, cell, 4))
    greens = [hexc(c) for c in ("#A9C878", "#8DB066", "#73985A")]
    for f in range(6):
        ang = math.radians(-90 + rng.uniform(-55, 55))
        x, y = cell / 2 + rng.uniform(-10, 10), cell - 4
        length = rng.uniform(140, 210)
        steps = 14
        for s in range(steps):
            a = ang + (s / steps) * (0.9 if math.cos(ang) > 0 else -0.9)
            nx_, ny_ = x + math.cos(a) * length / steps, y + math.sin(a) * length / steps
            stroke(tile, x, y, nx_, ny_, 2.4, greens[2])
            leaf = (1 - s / steps) * 26 + 6
            for side in (-1, 1):
                la = a + side * 1.2
                stroke(tile, nx_, ny_, nx_ + math.cos(la) * leaf, ny_ + math.sin(la) * leaf, 5.5, greens[s % 2])
            x, y = nx_, ny_
    cells.append(tile)
    # 1 dune grass: pale, wind-bent blades.
    tile = np.zeros((cell, cell, 4))
    for b in range(26):
        x0 = cell / 2 + rng.uniform(-50, 50)
        h = rng.uniform(110, 220)
        bend = rng.uniform(-60, 60)
        col = hexc(["#E6DFA4", "#D2CF8C", "#B9C27E"][b % 3])
        stroke(tile, x0, cell - 2, x0 + bend, cell - h, 4.5, col)
    cells.append(tile)
    # 2 dandelion puff: thin stem with a soft white seed head.
    tile = np.zeros((cell, cell, 4))
    stroke(tile, cell / 2, cell - 2, cell / 2 + 6, cell * 0.38, 3.0, hexc("#8FAE62"))
    cx, cy = cell / 2 + 6, cell * 0.3
    puff = np.clip((34 - np.hypot(xx - cx, yy - cy)) / 10, 0, 1) * 0.8
    tile[..., :3] = tile[..., :3] * (1 - puff[..., None]) + hexc("#FFFDF6") * puff[..., None]
    tile[..., 3] = np.maximum(tile[..., 3], puff)
    for _ in range(110):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(26, 40)
        stroke(tile, cx, cy, cx + math.cos(a) * r, cy + math.sin(a) * r, 2.2, hexc("#FFFDF6"))
    centre = np.clip((10 - np.hypot(xx - cx, yy - cy)) / 2, 0, 1)
    tile[..., :3] = tile[..., :3] * (1 - centre[..., None]) + hexc("#E8E0C8") * centre[..., None]
    tile[..., 3] = np.maximum(tile[..., 3], centre)
    cells.append(tile)
    # 3 flower spike: a few stems of tiny lavender-blue blooms.
    tile = np.zeros((cell, cell, 4))
    for st in range(4):
        x0 = cell / 2 + rng.uniform(-40, 40)
        top = rng.uniform(40, 90)
        stroke(tile, x0, cell - 2, x0 + rng.uniform(-10, 10), top, 2.6, hexc("#86A866"))
        for k in range(16):
            by = top + k * 6 + rng.uniform(-2, 2)
            bx = x0 + rng.uniform(-6, 6)
            m = np.clip((5.5 - np.hypot(xx - bx, yy - by)) / 1.2, 0, 1)
            col = hexc(["#B9A8E8", "#A598DE", "#CBBEF0"][k % 3])
            tile[..., :3] = tile[..., :3] * (1 - m[..., None]) + col * m[..., None]
            tile[..., 3] = np.maximum(tile[..., 3], m)
    cells.append(tile)
    for k, tile in enumerate(cells):
        ox, oy = (k % 2) * cell, (k // 2) * cell
        img[oy:oy + cell, ox:ox + cell] = tile
    img[..., 3] *= 255
    return np.clip(img, 0, 255).astype(np.uint8)


def paint_extra(seed=44):
    """Extra tiles for the foliage: birch bark and pine needles (seamless)."""
    rng = np.random.default_rng(seed)
    out = {}
    # Birch: creamy white bark with soft grey-violet horizontal marks.
    base = ramp_map(0.55 + 0.35 * fbm(rng, 6), ["#FFFBF2", "#F3EEE4", "#E3DDD4", "#C9C3C4", "#8E8794"])
    marks = fbm(rng, 10, 2)
    y = np.arange(SIZE)[:, None] / SIZE
    bands = (np.sin(2 * math.pi * (y * 9 + 0.4 * fbm(rng, 4))) > 0.82) & (marks > 0.45)
    base[bands] = base[bands] * 0.55 + hexc("#6E6574") * 0.45
    out["birch_bark"] = np.clip(base, 0, 255).astype(np.uint8)
    # Pine needles: deep cool green with fine directional streaks.
    v = 0.5 * fbm(rng, 8) + 0.5 * fbm(rng, 32, 2)
    img = ramp_map(0.25 + 0.6 * v, ["#A7C493", "#86A97C", "#6A8E6C", "#55765E", "#43604F"])
    soft_dabs(img, rng, ["#A7C493", "#55765E"], 120, 9, 0.35, 3.0, 1.1)
    out["needles"] = np.clip(img, 0, 255).astype(np.uint8)
    return out
