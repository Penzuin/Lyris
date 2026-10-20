# Lanes: who owns what

Each lane owns a set of paths. Only that lane's agent edits them. Paths marked *(new)* do
not exist yet; the lane creates them when it first needs them. If two lanes need the same
file, the lead edits it.

| Lane | Owns | Covers |
|---|---|---|
| **Lead** | `CLAUDE.md`, `design/LANES.md`, `design/TASKS.md`, `Config/`, `Lyris.uproject`, `Source/Lyris/Lyris.Build.cs`, `Source/Lyris/Lyris.*`, `Source/Lyris/LyrisGameMode.*`, `Source/*.Target.cs`, `.gitattributes`, `.gitignore`, `README.md` | Assigning work, reviewing and merging PRs, project settings, module dependencies, plugin list |
| **Design** | `design/Game_Concept.xlsx`, `design/*.md` other than the Lead's files, `design/lore/` *(new)* | Concept, lore, system specs, open questions |
| **Sailing** | `Source/Lyris/LyrisBoat.*`, `Source/Lyris/Sailing/` *(new)*, `Content/Lyris/Sailing/` *(new)* | Boat, wind, sails, charts, storms, crews |
| **World** | `Source/Lyris/World/` *(new)*, `Content/Lyris/World/` *(new)* | Real-time clock, day/night, seasons, weather, the nightly mist, lamps that hold it back |
| **Player** | `Source/Lyris/LyrisCharacter.*`, `Source/Lyris/LyrisPlayerController.*`, `Source/Lyris/Player/` *(new)*, `Content/Input/`, `Config/DefaultInput.ini` *(shared with Lead: Player proposes, Lead merges)* | Walking, boarding, camera, input actions |
| **Environment** | `Art/`, `Content/Python/` (Harbor build script and `init_unreal.py`), `Content/Lyris/Maps/` *(generated)*, `Content/Lyris/Materials/` *(generated)* | Islands, terrain, foliage, materials, palette, placing actors in maps |
| **Harvest** | `Source/Lyris/Interaction/` *(new)*, `Source/Lyris/Items/` *(new)*, `Source/Lyris/Harvest/` *(new)*, `Content/Lyris/Items/` *(new)*, `Content/Lyris/Harvest/` *(new)* | Interacting with things in the world, items and inventory, mining, harvesting and foraging nodes, farming plots |
| **UI** | `Source/Lyris/UI/` *(new)*, `Content/Lyris/UI/` *(new)* | HUD, menus, collection book, journal |

## Reserved lanes (no owner yet)

Opened when their first task is scheduled: **Cultivation** (combining strange plants into new varieties; builds on Harvest's farming plots), **Building**, **Collecting** (sets, rarity, museum; builds on Harvest's items),
**Life skills**, **Neighbors**, **Academy**, **RPG**, **Multiplayer**. Each will own
`Source/Lyris/<Lane>/` and `Content/Lyris/<Lane>/`.

## Hand-offs between lanes

The common one: a lane makes a new actor class (say World's mist volume) that has to appear
in the Harbor map. World builds the class; Environment adds it to the build script and
bumps `BUILD_VERSION`. World writes that request in its PR and adds a task for Environment.

## Leftovers

`Content/ThirdPerson`, `Content/LevelPrototyping`
and `Content/Characters/Mannequins` came with the Unreal template. Lead owns them until
they are kept or removed.
