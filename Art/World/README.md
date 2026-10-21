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
3. Switch to **Selection Mode** (Shift+1, or the mode dropdown at the top left of the toolbar):
   the import leaves the editor in Landscape mode, and big edits there froze the editor in
   playtest 1. Then run `w.build()` once more: it applies the material and settings to the
   landscape, sets the streaming grid and saves.
4. Build > Build HLODs (see **HLODs** below), then Build > Build Minimap.

**Rebuilds are incremental.** The build is a list of steps (sky, sea, water zone, lakes, rivers,
world bounds, landmarks, player start, boat and dock, streaming), each with its own version in
`STEP_VERSIONS`, recorded on the map's marker actor (`LyrisWorld_v<BUILD_VERSION>`). `w.build()`
redoes only the steps whose version changed: it loads only that step's streamed actors, removes
them 100 at a time behind a progress bar with a Cancel button (the log shows each batch), places
them again and saves after each step. Everything else and the landscape stay as they are.

- Changing what one step places: bump that step in `STEP_VERSIONS` and `BUILD_VERSION`.
- `w.report()` says what is out of date and changes nothing. Opening the editor does the same:
  `init_unreal.py` never rebuilds by itself, it prints the line to run.
- `w.build(only=["sea"])` redoes just the named steps; `w.build(force=True)` redoes every step
  except the landmarks.
- Landmarks are redone only when their step version changes, or on purpose with
  `import lyris_build_landmarks as lm; lm.rebuild()` (one landmark at a time; `only=["8"]` for
  some). Do that once after the landscape import, with the landscape around them loaded, so they
  trace onto it.

Changing the terrain: rebake, delete the Landscape in the map, re-import, `w.build()`.
Bake v2 (T36) changes the terrain: a landscape imported from a v1 bake must be re-imported.

### Streaming (what you see in Play)

The main runtime grid should be **Cell Size 25600, Loading Range 153600** (256 m cells loaded out
to 1.5 km; HLODs show the world beyond). The build sets it from Python when the engine lets it and
checks it. If it cannot, every `w.build()` and every editor start prints a **STREAMING NOT SET**
block with the steps: Window > World Settings > World Partition Setup > Runtime Settings, then
either *Grids > Index [0]* or *Runtime Partitions > Index [0] > Main Layer*: Cell Size 25600,
Loading Range 153600; File > Save All; then `w.streaming_done()`. Until it is set, Play loads only
about 256 m around you (playtest 1: only Moonharbor's harbour showed).

1.5 km is right for the blockouts on an 8 GB card. When real art replaces them and Play gets close
to the memory limit, drop the Loading Range to 102400 (1 km) before lowering anything else.

### HLODs

Without HLODs nothing past the loading range is drawn at all. **Build > Build HLODs** makes
low-detail proxies for every cell (landscape and landmarks). Expect roughly **15 to 45 minutes**
on the playtest PC the first time, mostly CPU and system RAM (it loads the world cell by cell; close
other programs, 32 GB RAM is comfortable, 16 GB works but slowly). The 8 GB GPU is not the limit,
but do it from a freshly opened editor with nothing loaded in the World Partition window. If the
editor runs out of memory, build them from a terminal instead (no editor window open):

    "<UE 5.8>\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "<project>\Lyris.uproject" /Game/Lyris/Maps/Lyris -run=WorldPartitionBuilderCommandlet -Builder=WorldPartitionHLODsBuilder -AllowCommandletRendering

Rebuild HLODs after the landscape or the landmarks change. If the build makes nothing, set World
Settings > World Partition Setup > Default HLOD Layer to one of the engine's HLOD layers first.

## 3. Landmarks (T36)

`landmarks.json` holds every canon landmark and one lamp or beacon per new island chain as
**blockouts**: engine basic shapes (cube, cylinder, cone, sphere) in the house palette, placed at the
real spots from `design/world_map.md` and the server builds (`lyris-server/builds`). It is generated:

    python Art/World/make_landmarks.py        # about 30 s, same packages as the bake

`lyris_build_world.build()` places them as one of its steps (only when the landmarks step version
changes). To redo them on purpose, for example after importing the landscape so they snap onto it:
`import lyris_build_landmarks as lm; lm.rebuild()` (one landmark at a time, cancellable).

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

## 4. Terrain look (T50): the starter island's texturing over the whole world

The landscape is imported from the heightmap only, so its material cannot use paint layers.
`M_LyrisWorldTerrain_v2` (`Content/Python/lyris_world_terrain.py`) reads the biome of every point from
two world-space maps instead, and everything else from height, slope and painted noise, in the
starter island's style: one palette (`ISLAND_PALETTE` / `LAYER_LOOK`), painted textures only adding
light and dark detail at 4 m and ~15 m, warm stone with lavender shadows on anything steeper than
~37 degrees (textured from three sides), grass only on the flat tops of rock, sand shelves at the
waterline, a wet tide line, rippled seabed that darkens and cools with depth, sunny meadows, drier
hills and lush valleys over kilometres, the warm-to-cool drift, matte roughness (0.94).

**Once, after the terrain bake** (numpy + pillow, about 30 s):

    python Art/World/bake_biome_maps.py      # tiles/World_<Layer>_*.png -> biome/T_LyrisBiomeA/B.png

**In the editor**, with the Lyris map open (Output Log, Python):

    import lyris_world_terrain as t; t.build(); t.apply()

`build()` imports the two biome maps and the three painted packs from `textures/` and builds the
material; `apply()` puts it on the landscape and its loaded proxies (proxies that load later inherit
it from the landscape) and saves. `w.build()` runs both as its `terrain_look` step.
After a new terrain bake: rerun `bake_biome_maps.py`, then `t.build(reimport=True)`.
`t.build(force=True)` rebuilds the graph; bump `TERRAIN_LOOK_VERSION` when you change the look.

| File | What |
|---|---|
| `bake_biome_maps.py` -> `biome/` (not in git) | 4096² RGBA: A = Grass Forest Sand Rock, B = Snow Badlands Salt Volcanic; `biome_maps.json` has the world bounds and orientation |
| `paint_world_textures.py` -> `textures/` | snow, strata, salt, basalt and seabed painted in the island's style (`Art/TestIsland/paint_textures.py`), and the packs the material reads: `T_LyrisDetailA` (grass sand cliff seabed) and `T_LyrisDetailB` (snow strata salt basalt) hold each texture's luminance around its mean; `T_LyrisWorldNoise` holds four soft noises |
| `preview_terrain_look.py` | numpy twin of the material on the baked tiles: `preview_look.jpg` (whole world) and 2 km close-ups `preview_moonharbor.jpg`, `preview_saltreach.jpg`, `preview_north.jpg` |

**Grass (T51).** When `/Game/Lyris/World/Foliage/GT_Meadow`, `GT_Forest` and `GT_Dune` exist, `build()`
adds a Landscape Grass Output with those three entries (weights: meadow and rocky flats, forest floor,
sand above the shore; all on ground under ~25 degrees and clear of the sea). Before they exist the
material is built without it; run `t.build()` again afterwards and it is added. If the log says the
Grass Output could not be filled from Python, open the material, add a **Landscape Grass Output**
node with entries Meadow, Forest, Dune, pick the grass types and wire the `Meadow`, `Forest` and `Dune`
weights (the three Multiply nodes feeding nothing at the end of the graph).

**Cost** (8 GB GPUs): 12 texture samples from 5 small textures (biome maps BC-compressed, ~21 MB each
with mips; the rest 512²), one shared triplanar for rock, no paint layers.

**New colours.** None in the material: every hex is from `PALETTE`, `ISLAND_PALETTE` or `LAYER_LOOK`
(plus the island grass texture's highlight `D3DE8A`). The new biomes' textures (`textures/snow.png` ...)
use their own ramps, but only their luminance reaches the game.

## If the editor freezes or runs out of video memory

**Freezes during `w.build()`.** Rebuilds no longer delete everything at once, but:

- Build from **Selection Mode** (Shift+1). `w.build()` refuses to start while Landscape mode is
  open; if it wrongly thinks so, `w.build(check_mode=False)`.
- The progress bar has **Cancel**. Each finished step is already saved; run `w.build()` again to
  carry on. The Output Log shows `[Lyris] <step>: removed 300/1751` per batch, so a slow step is
  visibly moving, not frozen.
- If you had to kill the editor anyway: reopen, and `w.report()` shows what is left. Nothing is
  rebuilt on startup.

**"Video memory has been exhausted".** The project's editor defaults are set for an 8 GB card
(`Config/DefaultEditorSettings.ini`, `Config/DefaultDeviceProfiles.ini`,
`Config/DefaultEditorPerProjectUserSettings.ini`): High scalability in the viewport, a 1.5 GB
texture pool, a smaller shadow page pool, a capped viewport resolution, and the map opening without
last session's loaded regions. If the message still shows:

1. Viewport toolbar > Settings > Engine Scalability Settings: **High** (or console `scalability 2`).
   A choice you once made yourself is saved per user and wins over the project default.
2. In Window > World Partition, unload areas you are not working on; never "Load All" on this map.
3. Close other editor tabs and viewports (material editors and extra viewports each hold buffers),
   and other GPU-heavy programs (browsers with video, games).
4. Still over: console `r.Streaming.PoolSize 1000` for the session.

Hardware ray tracing (`r.RayTracing=True` in `Config/DefaultEngine.ini`) also costs video memory for
its acceleration structures, more once the 16384² landscape is in. Turning it off is a project-wide
look decision for the Lead, not an editor setting.

