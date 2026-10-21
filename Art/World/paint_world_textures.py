"""Painted detail textures for the world terrain (T50), in the starter island's style.

    python Art/World/paint_world_textures.py        # a few seconds; numpy + pillow

The starter island's terrain took all its colour from one palette and used its painted textures only
for light and dark detail (their luminance around their own mean). The world material does the same,
so this script:

1. paints the biomes the island lacks, in the island's soft style (Art/TestIsland/paint_textures.py:
   low contrast, big soft patches, a few gentle dabs, warm lights and cool lavender-leaning darks),
   every tile seamless:  snow, strata (badlands), salt (crust), basalt (volcanic), seabed (ripples)
   -> Art/World/textures/<name>.png   (colour references; only their luminance reaches the game)
2. packs the luminance detail of eight textures into two RGBA maps, so the material reads eight
   detail patterns with one sample per map and scale:
   T_LyrisDetailA.png  R grass  G sand   B cliff  A seabed      (grass, sand, cliff from the island)
   T_LyrisDetailB.png  R snow   G strata B salt   A basalt
   Each channel stores 0.5 * (linear luminance / its mean), so the material gets the island's
   "detail centred on 1.0" as 2 * sample.
3. paints T_LyrisWorldNoise.png: four independent seamless soft noises (RGBA) for biome-edge breakup,
   large meadow / dry-hill / lush-valley patches and the warm-to-cool drift.
4. writes world_textures.json (channel layout and the luminance means).

Seeded: every PC gets identical textures. The outputs are small and live in git.
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ISLAND = os.path.join(HERE, "..", "TestIsland")
OUT = os.path.join(HERE, "textures")
sys.path.insert(0, ISLAND)
import paint_textures as pt  # noqa: E402  (the island's painting helpers: fbm, ramp_map, soft_dabs)

SIZE = pt.SIZE  # 512, like the island's textures

# light -> dark, the island's way: warm lights, cool lavender-leaning darks, gentle steps.
# Only luminance reaches the material (colours come from the palette there), so these ramps exist to
# make the reference PNGs read right and to give the right light/dark rhythm.
RAMPS = {
    "snow":   ["#FFFCF4", "#F6F2EA", "#EAE7EE", "#DCDAE8", "#CBC8DC"],
    "strata": ["#EBC29A", "#DC9A6E", "#C8643A", "#AE5340", "#8E4A48"],
    "salt":   ["#FFFBF2", "#F7EEDC", "#EEE3CE", "#E0D4C0", "#CFC2B2"],
    "basalt": ["#7E6862", "#665450", "#524240", "#403234", "#30262A"],
    "seabed": ["#F6EAD0", "#EAD9B8", "#DCC8A6", "#CBB696", "#B6A48C"],
}


def _wrap_dist(a, b):
    d = np.abs(a - b)
    return np.minimum(d, SIZE - d)


def _cells(rng, count):
    """Seamless Voronoi: distance to nearest and second-nearest of `count` wrapped points."""
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    # Poisson-ish: no two points closer than about half the mean spacing (no sliver cells).
    min_d = 0.55 * SIZE / math.sqrt(count)
    pts = []
    while len(pts) < count:
        p = rng.random(2) * SIZE
        if all(math.hypot(min(abs(p[0] - q[0]), SIZE - abs(p[0] - q[0])),
                          min(abs(p[1] - q[1]), SIZE - abs(p[1] - q[1]))) >= min_d for q in pts):
            pts.append(p)
    d1 = np.full((SIZE, SIZE), 1e9, np.float32)
    d2 = np.full((SIZE, SIZE), 1e9, np.float32)
    for px, py in pts:
        d = np.hypot(_wrap_dist(xx, px), _wrap_dist(yy, py))
        d2 = np.where(d < d1, d1, np.minimum(d2, d))
        d1 = np.minimum(d1, d)
    return d1, d2


def paint(name, rng):
    ramp = RAMPS[name]
    y = np.arange(SIZE)[:, None] / SIZE
    if name == "snow":
        # Wind-smoothed drifts: long soft ripples and big gentle patches, very low contrast.
        drift = 0.5 + 0.5 * np.sin(2 * math.pi * (y * 3 + 0.6 * pt.fbm(rng, 3)))
        v = 0.45 * pt.fbm(rng, 3) + 0.35 * drift + 0.2 * pt.fbm(rng, 24, 2)
        img = pt.ramp_map(0.3 + 0.6 * v, ramp)
        pt.soft_dabs(img, rng, ramp[:2], 40, 16, 0.3, 2.2, 0.2)
    elif name == "strata":
        # Layered sandstone: bands of uneven thickness that wander a little, soft dabs along them.
        warp = 0.25 * pt.fbm(rng, 4)
        layers = (y * 10 + warp) % 1.0                # 10 bands: a multiple of 5, so the tile wraps
        t = y * 10 + warp
        tones = rng.random(10)                                         # one tone per band; 10 wraps
        i = np.floor(t).astype(int)
        f = np.clip((t % 1.0 - 0.85) / 0.15, 0, 1)                     # soft step into the next band
        bands = tones[i % 10] * (1 - f) + tones[(i + 1) % 10] * f
        v = 0.45 * bands + 0.25 * (0.5 + 0.5 * np.cos(2 * math.pi * layers)) + 0.3 * pt.fbm(rng, 12, 3)
        img = pt.ramp_map(0.15 + 0.75 * v, ramp)
        pt.soft_dabs(img, rng, ramp, 70, 14, 0.2, 3.0, 0.0)
    elif name == "salt":
        # Dry salt crust: soft polygons with slightly raised, lighter rims and a darker hairline.
        d1, d2 = _cells(rng, 36)
        crack = 1 - np.clip((d2 - d1 - 1.0) / 2.5, 0, 1)   # soft hairline where two cells meet
        dome = np.clip(d1 / 40.0, 0, 1)                    # cell middles a touch lighter, edges lift
        v = 0.62 - 0.1 * dome - 0.3 * crack + 0.3 * (pt.fbm(rng, 6, 3) - 0.5)
        img = pt.ramp_map(v, ramp)
        pt.soft_dabs(img, rng, ramp[2:], 50, 6, 0.25)
    elif name == "basalt":
        # Cooled lava: rounded column tops with soft dark joints and a few warm glints.
        d1, d2 = _cells(rng, 48)
        edge = np.clip((d2 - d1) / 14.0, 0, 1)
        dome = np.clip(1 - d1 / 30.0, 0, 1)
        v = 0.45 + 0.25 * edge ** 0.6 + 0.12 * dome + 0.15 * (pt.fbm(rng, 8, 3) - 0.5)
        img = pt.ramp_map(v, ramp)
        pt.soft_dabs(img, rng, ramp[:2], 30, 5, 0.3)
    elif name == "seabed":
        # Sand ripples under water: wavy crests, wide soft troughs.
        x = np.arange(SIZE)[None, :] / SIZE
        phase = 2 * math.pi * (y * 7 + 0.08 * np.sin(2 * math.pi * x * 2) + 0.35 * pt.fbm(rng, 3))
        ripple = (0.5 + 0.5 * np.sin(phase)) ** 2.2
        v = 0.4 * ripple + 0.4 * pt.fbm(rng, 4) + 0.2 * pt.fbm(rng, 32, 2)
        img = pt.ramp_map(0.25 + 0.6 * v, ramp)
        pt.soft_dabs(img, rng, ramp[2:], 40, 4, 0.35)  # shells and pebbles
    else:
        raise ValueError(name)
    return np.clip(img, 0, 255).astype(np.uint8)


def linear_luma(rgb8):
    c = rgb8[..., :3].astype(np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def world_noise(seed=77):
    rng = np.random.default_rng(seed)
    chans = [pt.fbm(rng, 3, 3), pt.fbm(rng, 3, 3), pt.fbm(rng, 4, 3), pt.fbm(rng, 2, 3)]  # big soft blobs
    out = []
    for c in chans:  # even out the histogram a little so every channel spans 0..1 with soft mid tones
        r = np.argsort(np.argsort(c.ravel())).reshape(c.shape) / (c.size - 1)
        out.append(0.5 * c + 0.5 * r)
    return (np.clip(np.stack(out, -1), 0, 1) * 255).round().astype(np.uint8)


def main():
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(50)
    painted = {}
    for name in RAMPS:
        painted[name] = paint(name, rng)
        Image.fromarray(painted[name], "RGB").save(os.path.join(OUT, name + ".png"), optimize=True)
    island = {n: np.asarray(Image.open(os.path.join(ISLAND, "textures", n + ".png")).convert("RGB"))
              for n in ("grass", "sand", "cliff")}
    src = {**island, **painted}

    packs = {"T_LyrisDetailA": ("grass", "sand", "cliff", "seabed"),
             "T_LyrisDetailB": ("snow", "strata", "salt", "basalt")}
    means = {}
    for pack, names in packs.items():
        chans = []
        for n in names:
            lum = linear_luma(src[n])
            means[n] = float(lum.mean())
            chans.append(np.clip(0.5 * lum / means[n], 0, 1))
        rgba = (np.stack(chans, -1) * 255).round().astype(np.uint8)
        Image.fromarray(rgba, "RGBA").save(os.path.join(OUT, pack + ".png"), optimize=True)
    Image.fromarray(world_noise(), "RGBA").save(os.path.join(OUT, "T_LyrisWorldNoise.png"), optimize=True)

    meta = {
        "packs": {k: list(v) for k, v in packs.items()},
        "encoding": "each channel = 0.5 * linear luminance / mean (detail centred on 1.0 = sample * 2)",
        "linear_luma_mean": {k: round(v, 4) for k, v in means.items()},
        "noise": "T_LyrisWorldNoise: four independent seamless soft noises, R G B A",
    }
    with open(os.path.join(OUT, "world_textures.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(f"[Lyris] painted {', '.join(RAMPS)}; packed detail maps and world noise in {OUT}")


if __name__ == "__main__":
    main()
