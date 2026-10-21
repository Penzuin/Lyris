# Lyris world terrain (T35), landmarks and new islands (T36)

The game world is the Lyris Minecraft map at full size: 1 block = 1 m, 25 x 25 km
(coordinates in `design/world_map.md`). Two scripts turn the atlas into an Unreal map.

| What | Where |
|---|---|
| Source atlas (from `lyris-companion/atlas`) | `atlas/` (`hmap.png`, `bidx.png`, `lakes.png`, `regions.png`, `biomes.png`, `painted.jpg`, `relief.jpg`, plus `lake_levels.json` and `biome_names.json` taken from the atlas page) |
| Offline bake (plain Python) | `bake_terrain.py` |
| Bake output, not in git | `tiles/` (64 height tiles, 8 x 64 weight tiles, `terrain_manifest.json`) |
| Editor build | `Content/Python/lyris_build_world.py` |
| Landmark blockouts: generator, data, editor script | `make_landmarks.py`, `landmarks.json`, `Content/Python/lyris_build_landmarks.py` |
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
Bake v2 (T36) changes the terrain: a landscape imported from a v1 bake must be re-imported.
Changing anything else the script places: bump `BUILD_VERSION` and run `w.build()`; the
landscape is kept.

## 3. Landmarks (T36)

`landmarks.json` holds every canon landmark and one lamp or beacon per new island chain as
**blockouts**: engine basic shapes (cube, cylinder, cone, sphere) in the house palette, placed at the
real spots from `design/world_map.md` and the server builds (`lyris-server/builds`). It is generated:

    python Art/World/make_landmarks.py        # about 30 s, same packages as the bake

`lyris_build_world.build()` places them as one of its steps (BUILD_VERSION 2). To redo only the
landmarks, for example after importing the landscape so they snap onto it:
`import lyris_build_landmarks as lm; lm.rebuild()`.

**Ground.** Each part carries the baked ground under it (`g`, MC Y) and how far its base sinks so it
never floats on a slope (`k`). In the editor the script traces straight down onto the landscape and
uses that if it is within 25 m of the bake; otherwise it uses `g`. Harbour works, the stair, the
lighthouse, the statue and Oruth use absolute heights from the builds (`"a": "abs"`, MC Y) or sea level.

**Organised for replacement.** Each landmark has its own outliner folder
(`Landmarks/<Region>/<Name>/<group>`) and every actor carries the tags `LyrisWorldBuild`,
`LyrisLandmark` and `LM_<id>`. To swap in real art: delete the landmark's entry in
`make_landmarks.py` (or filter it in `lyris_build_landmarks`), rerun, and place the art in its own lane-owned
script.

| Id | Landmark | Notes |
|---|---|---|
| 1 | Moonharbor streets and walls | 22 streets and lanes from `moonharbor2/plan.py`; Witch's Wall and quay curtain (canon); landward wall, towers and two gates (ours) |
| 1i-* | Eight districts | 350 house blocks along each district's own streets, each district in its own colours and roof style (Market, the Heights, Lamplight, the Rise, the Point, Yards, Weavers, Wayside) |
| 1a, 1c to 1h, 1j | Market Square and the Moonwell, Main Street and the Bright Cask, Moonmarket, Grand Library, Miners' Guild, Carriage Station, Boatyard, South Hall | in their kept zones |
| 1b | The Harbour | promenade, four finger piers, the east quay and Net Lane |
| 3 | The Seawall Stair | seven steps, landing, the red top step XLI (never repaired), the two Stair Towers |
| 8 | Lantern Pier | the Tide Mother shrine under whale ribs, and the **T37 dock spot** (below) |
| 5, 5a | Ilwen's Lighthouse (lit), Chapel of Lamps | |
| 4 | Syrena's statue and the Hung Star | sword due north at 40 degrees, the star lit at its tip |
| 2 | Keep Elariel and the Moon Window | curtain, towers, gate on the Keep Road, keep, cathedral, lit Moon Window, Sir Cog, Moon Chapel |
| 6 | Oruth | glass dome on the pit floor (Y -39) with the glowing star heart |
| 9 | The Grand Observatory | three terraces with the 12 meridian lines, drum, pointed dome with the south slit, peristyle, refractor, scaffold, Hoarfeather's perch |
| 10 | The North Road | about 2.1 km from the Carriage Station to the Gate, a lantern and a cairn every 250 m; lantern V is dark |
| 11 | The Delvers' Gate | cleft, rubble wall, court, brass door, the lantern still burning, the Lodge |
| 12, 14, 15 | The Teeth, Hollowmere ruins and bridge, the Under-Halls gate | spots placed by us (gazetteer) |
| 16a to 16e | Waystone rings | the five gazetteer sites |
| 17, 18 | Saltreach and Sunreach landings | jetty, cairn, lamp |
| A to H, C-ring | New island chains | a dark lamp post on each Lampwick islet; one per other chain, plus the Hushed bell tower, Wickstones ring, Tallow sheds and the Southing cairn |

**T37 dock spot.** On Lantern Pier's east side: a berth deck at (141.5, -2404), the dock lamp at
(139.5, 66.2, -2414), and TargetPoints `T37_BoatStart` (147, -2404, sea level, facing north),
`T37_DockLamp`, `T37_Mooring` and `T37_StepAshore` in `Landmarks/Moonharbor/LanternPier/Markers`.
