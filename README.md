# Lyris

A cozy, real-time archipelago game set in the world of Lyris. Sail between mysterious islands, uncover their secrets, grow a strange and beautiful home, collect treasures, and build together with friends and neighbors, as calm or as adventurous as you want.

Built in **Unreal Engine 5.8**.

## The world

Lyris is a land of three great regions where a fallen star still sings under the sea and a mist rises from the dark every night. Lit lamps hold the mist back. The Lamp-Heir of Moonharbor is asking settlers to take a lantern, head back out into the Reach and light it again.

- **Lit waters are calm.** Home islands and lamp-lit harbors are cozy and safe.
- **Unlit waters are the adventure.** The farther you sail, the deeper the mist and the mysteries.

## Design pillars

1. **Calm by default.** Real-time days and seasons, no punishment for being away, nothing dies while you're gone.
2. **Knowledge is progression.** You get further because you understand more, not because you leveled up.
3. **The ship is how you explore.** Hands-on sailing: wind, sails, charts, storms, crews.
4. **Build anything, in the world's style.** Freeform building with pieces gathered from each island.
5. **Everything is worth collecting.** Themed sets, rare relics, seasonal items, a museum.
6. **A shared world.** Players settle, trade, crew ships and build towns together.

## Systems

| System | Summary |
|---|---|
| Sailing | Manual sails, wind, charting, storms, crewed and player-built ships |
| Exploration | Island mysteries, tools and artifacts, ship upgrades; no XP grind |
| Cultivation | Strange plants, fungi, coral and crystals that combine into new varieties |
| Building | Block grid plus detailed pieces; palettes unlock as you explore |
| Collecting | Sets, rarity tiers, seasonal items, collection book, museum, trading |
| Life skills | Fishing, trading, cooking, sailing and more |
| Neighbors | Characters who move into player towns |
| Academy | A dark academia college at the Observatory; research, societies, roleplay |
| RPG | Backgrounds, disciplines of study, skills by doing, quests, reputation |
| Multiplayer | Shared servers of roughly 20 to 60 players, home islands, port towns, events |

Wildlife is observed and documented, never owned or raised.

The full concept lives in [`design/Game_Concept.xlsx`](design/Game_Concept.xlsx).

## First prototype

One island, one boat, sailing in the wind, a day/night cycle, and a dock lamp that holds back the mist at night.
It is played in the full-size Lyris world: you start in Moonharbor on Lantern Pier, beside the boat and the dock lamp.

## Play the prototype

The world map is generated on your PC, so the first time takes a while (mostly the terrain bake).
Do these in order; after the first time, steps 1 and 3 are usually all you need.

1. **Pull** the latest `main` (GitHub Desktop: Fetch origin, then Pull).
2. **Bake the terrain** (about 1 hour; only again when `Art/World/` changes). Once: install Python 3.9+ and run
   `pip install numpy scipy pillow`. Then, in a terminal in the project folder:

       python Art/World/bake_terrain.py --workers 2

   Use `--workers 4` with 16 GB of RAM or more.
3. **Open the project** (`Open Lyris.bat`, or double-click `Lyris.uproject`). If Unreal asks to rebuild the
   Lyris module, say Yes. When the editor has loaded, the world script builds `/Game/Lyris/Maps/Lyris` by
   itself. Open **Window > Output Log** and type `Lyris` in its search box to follow it.
4. **Import the landscape (once).** The log ends with `LANDSCAPE IMPORT`: numbered steps with the exact file,
   location, scale and component values. In short: Selection Mode > Landscape, Manage > New > Import from File,
   pick the first height tile (answer Yes to "tiled image"), the material, the eight paint layers with their
   weight tiles, the location and scale from the log, World Partition grid size 4, then Import (several minutes).
   To see the steps again, switch the Output Log's input from Cmd to Python and run
   `import lyris_build_world as w; w.import_steps()`.
5. **Finish the map:** in the same Python input run `import lyris_build_world as w; w.build()`. It applies the
   terrain material and saves.
6. **Restart the editor once**, so the boat finds the materials the first build made.
7. Optional, for the far view: Build > Build HLODs, then Build > Build Minimap.
8. **Press Play.** You start on Lantern Pier in Moonharbor's harbour, facing north along the pier. The boat is
   moored a few steps ahead on the pier's east side, the moonglass dock lamp beside it. Walk up and press **E**
   to board; **W/S** raise and lower the sail, **A/D** steer. Sail back to the berth and press **E** to step ashore.

Known gap until the Player lane picks it up: if you swim more than 80 m from every boat for 20 seconds, the tide
still carries you to the old Harbor map's dock, which in this world is inland. Stay near the boat when swimming.

The old Harbor test map is retired. If you built it before, you can delete `Content/Lyris/Maps/Harbor` and the
`TestIsland*`, `Island_v8` and `Sea_v9` folders under `Content/Lyris/` (they are not in git). Keep
`Content/Lyris/Materials/Prototype`: the boat uses it.

## Getting started

1. Install **Unreal Engine 5.8** from the Epic Games Launcher.
2. Install **Git LFS** (git-lfs.com). Large files such as `.uasset` and `.umap` are stored with LFS, as set in `.gitattributes`.
3. Clone this repo with GitHub Desktop or `git clone`.
4. Create the Unreal project, close the editor, then copy the project's contents (`Config/`, `Content/`, the `.uproject` file, and `Source/` if it has one) into the root of this repo.
5. Commit and push. Generated folders like `Binaries/`, `Intermediate/` and `Saved/` are ignored.

## Repo layout

```
Lyris/
├─ design/            Game concept and design documents
├─ Config/            Unreal config (after the project is added)
├─ Content/           Unreal assets (stored with Git LFS)
└─ Lyris.uproject     The Unreal project file
```
