# Lyris world terrain (T35)

The game world is the Lyris Minecraft map at full size: 1 block = 1 m, 25 x 25 km
(coordinates in `design/world_map.md`). Two scripts turn the atlas into an Unreal map.

| What | Where |
|---|---|
| Source atlas (from `lyris-companion/atlas`) | `atlas/` (`hmap.png`, `bidx.png`, `lakes.png`, `regions.png`, `biomes.png`, `painted.jpg`, `relief.jpg`, plus `lake_levels.json` and `biome_names.json` taken from the atlas page) |
| Offline bake (plain Python) | `bake_terrain.py` |
| Bake output, not in git | `tiles/` (64 height tiles, 8 x 64 weight tiles, `terrain_manifest.json`) |
| Editor build | `Content/Python/lyris_build_world.py` |
| Preview of the last bake | `preview_hillshade.jpg` |

## 1. Bake the terrain (about 1 hour, once per change)

Needs Python 3.9+ with `pip install numpy scipy pillow`. From the project folder:

    python Art/World/bake_terrain.py --workers 2

Each worker needs about 2 GB of RAM; with 16 GB use `--workers 4`. For a quick look first,
`--preview` bakes the same world at 12 m per vertex in under a minute (do not import that one).
The bake is seeded, so every PC gets identical tiles.

Layout: **8 x 8 tiles of 2048 x 2048** = 16384 x 16384 vertices, **1.526 m per vertex**,
129 x 129 components of 127 x 127 quads (1 section each). Height is 16-bit over -128..+384 m
(Scale Z 100), so sea level is Z 0. Paint layers: Grass, Forest, Sand, Rock, Snow, Badlands, Salt,
Volcanic.

What the bake adds on top of the map: smooth bicubic upsampling of the 25 m heights (with the
Minecraft ravines and single-block spikes filtered out), warped ridged noise on mountains, gentle
rolling ground on plains, terraced mesas in Saltreach's badlands, level salt flats, beaches with a
soft shelf, a sloping seabed, river channels and lake basins at each lake's own water level, the
West Volcano cone and crater on Saltreach's spine and the bowl of Sunreach's crater. Moonharbor,
Keep Elariel, the Observatory summit, the Delvers' Gate and Oruth's pit keep the map's exact
ground. Coastlines stay where the map has them (the bake prints the agreement, about 99.8%).

## 2. Build the map in the editor

1. Open the project. In the Output Log, Python:
   `import lyris_build_world as w; w.build()`
   This creates `/Game/Lyris/Maps/Lyris` (World Partition), the terrain material and layer infos,
   sky and golden-hour light, the ocean, lakes and rivers, world edges and the Moonharbor
   PlayerStart, then prints the landscape import steps.
2. Do the printed import (Landscape mode > Manage > New > Import from File, first tile
   `World_Height_x0_y0.png`, the eight weight tiles, location, scale and component counts from
   the log). `w.import_steps()` prints them again.
3. Run `w.build()` once more: it applies the material and settings to the landscape and saves.
4. Build > Build HLODs, then Build > Build Minimap.

Changing the terrain: rebake, delete the Landscape in the map, re-import, `w.build()`.
Changing anything else the script places: bump `BUILD_VERSION` and run `w.build()`; the
landscape is kept.
