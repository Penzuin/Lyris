"""Packs the eight terrain paint layers into two world-space biome maps the terrain material reads.

    python Art/World/bake_biome_maps.py            # after bake_terrain.py; about 30 s

Why: the landscape's own paint layers need a manual, multi-step import in the editor (and the
weightmap import is fiddly in UE 5.8). The terrain material instead samples these two textures by
world position, so the whole world is textured as soon as the material is on the landscape.

Input   Art/World/tiles/World_<Layer>_x{X}_y{Y}.png   (8-bit weight tiles from bake_terrain.py)
Output  Art/World/biome/T_LyrisBiomeA.png   R Grass   G Forest  B Sand  A Rock
        Art/World/biome/T_LyrisBiomeB.png   R Snow    G Badlands B Salt A Volcanic
        Art/World/biome/biome_maps.json     size, world bounds and channel layout
Each map is RES x RES pixels over the whole 25 km world (4096: about 6.1 m per pixel). The
material breaks up the edges with painted noise, so the pixel size never shows as steps.
"""

import argparse
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TILES = os.path.join(HERE, "tiles")
OUT = os.path.join(HERE, "biome")
MAP_A = ("Grass", "Forest", "Sand", "Rock")
MAP_B = ("Snow", "Badlands", "Salt", "Volcanic")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--res", type=int, default=4096, help="output size in pixels (default 4096)")
    args = ap.parse_args()

    with open(os.path.join(TILES, "terrain_manifest.json")) as f:
        man = json.load(f)
    nx, ny = man["tiles_x"], man["tiles_y"]
    if args.res % nx or args.res % ny:
        raise SystemExit(f"--res must be a multiple of the tile count ({nx})")
    per = args.res // nx
    os.makedirs(OUT, exist_ok=True)

    def layer(name):
        full = np.zeros((args.res, args.res), np.float32)
        for ty in range(ny):
            for tx in range(nx):
                path = os.path.join(TILES, f"World_{name}_x{tx}_y{ty}.png")
                im = Image.open(path).convert("L").resize((per, per), Image.BOX)
                full[ty * per:(ty + 1) * per, tx * per:(tx + 1) * per] = np.asarray(im, np.float32)
        return full

    layers = {n: layer(n) for n in MAP_A + MAP_B}
    # Normalise so the eight weights sum to 255 wherever any layer is painted (they should already).
    total = sum(layers.values())
    painted = total > 0.5
    for n in layers:
        layers[n] = np.where(painted, layers[n] * 255.0 / np.maximum(total, 1e-3), 0.0)
    for fname, names in (("T_LyrisBiomeA.png", MAP_A), ("T_LyrisBiomeB.png", MAP_B)):
        rgba = np.stack([layers[n] for n in names], axis=-1).round().clip(0, 255).astype(np.uint8)
        Image.fromarray(rgba, "RGBA").save(os.path.join(OUT, fname), optimize=True)

    lo, hi = man["world_bounds_ue"]
    meta = {
        "res": args.res,
        "world_min_ue": lo,
        "world_size_ue": hi - lo,
        "maps": {"T_LyrisBiomeA": list(MAP_A), "T_LyrisBiomeB": list(MAP_B)},
        "row_axis": "UE Y (row 0 = min Y)", "col_axis": "UE X (col 0 = min X)",
        "bake_version": man.get("bake_version"),
    }
    with open(os.path.join(OUT, "biome_maps.json"), "w") as f:
        json.dump(meta, f, indent=1)
    cover = {n: round(float((layers[n] > 127).mean()) * 100, 2) for n in layers}
    print(f"[Lyris] biome maps {args.res}x{args.res} written to {OUT}; painted {painted.mean() * 100:.1f}% "
          f"of the world; dominant share per layer (%): {cover}")


if __name__ == "__main__":
    main()
