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
