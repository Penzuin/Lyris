"""Stitches the 8 x 8 baked height tiles into one 16-bit heightmap for a single-file landscape import.

    python Art/World/stitch_heightmap.py          # writes Art/World/tiles/World_Height_full.png (about 1 min)

Why: in UE 5.8 the tiled World Partition import (World_Height_x<x>_y<y>.png) repeated the first tile across
the whole landscape on the user's PC (playtest 1, 2026-10-21): every square kilometre became the same open
seabed, about 48 m below sea level. Importing one 16384 x 16384 file avoids that bug. Same location, scale
and component settings as the tiled import (see the printed import steps).
"""

import json
import os

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # the full heightmap is 16384 x 16384

HERE = os.path.dirname(os.path.abspath(__file__))
TILES = os.path.join(HERE, "tiles")


def main():
    with open(os.path.join(TILES, "terrain_manifest.json")) as f:
        man = json.load(f)
    nx, ny, res = man["tiles_x"], man["tiles_y"], man["tile_resolution"]
    full = np.zeros((ny * res, nx * res), np.uint16)
    for ty in range(ny):
        for tx in range(nx):
            path = os.path.join(TILES, man["heightmap_pattern"].format(X=tx, Y=ty))
            tile = np.asarray(Image.open(path)).astype(np.uint16)
            if tile.shape != (res, res):
                raise SystemExit(f"{path}: expected {res}x{res}, got {tile.shape}")
            full[ty * res:(ty + 1) * res, tx * res:(tx + 1) * res] = tile
    out = os.path.join(TILES, "World_Height_full.png")
    Image.fromarray(full).save(out)  # 16-bit greyscale PNG (mode I;16)
    print(f"[Lyris] {out}: {full.shape[1]} x {full.shape[0]}, values {int(full.min())}..{int(full.max())}, "
          f"{os.path.getsize(out) / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
