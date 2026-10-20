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
