# Task board

The live list of work. Agents update their own row in their PR. Only the lead moves tasks
between sections or assigns them.

Status: `todo` · `in progress` · `in review` (PR open) · `needs compile` (merged, waiting for
a build on the user's PC) · `done` · `blocked`

## Now: first prototype

Goal (from `README.md`): one island, one boat sailing in the wind, a day/night cycle, and a
dock lamp that holds back the mist at night. Added by the user on 2026-10-20: mining,
harvesting, farming and interacting with the world (T10 to T16).

| ID | Task | Lane | Depends on | Status | Branch | Notes |
|---|---|---|---|---|---|---|
| T1 | Day/night cycle: a clock actor that drives sun angle, sky and light colour; time speed adjustable for testing | World | | todo | | Sun and sky are currently placed by the Harbor script |
| T2 | Nightly mist that rises after dusk and clears at dawn | World | T1 | todo | | |
| T3 | Lamps hold back the mist: a lit lamp clears a radius around it; the dock lamp is the first one | World | T2 | todo | | Dock lamp is spawned by the Harbor script |
| T4 | Place the day/night actor, mist and lamp component in the Harbor map; bump `BUILD_VERSION` | Environment | T1, T2, T3 | todo | | Hand-off task |
| T5 | One shared world wind (a single source all boats read), drifting slowly across the compass with gusts and calms; replaces the per-boat sine wobble in `ALyrisBoat::GetWindYaw` | Sailing | | needs compile | lane/sailing-T5-world-wind | `ULyrisWindSubsystem` (deterministic from seed + server world time), tuned in Project Settings > Game > Lyris Wind; `BaseWindYaw` removed from the boat. Not compiled |
| T6 | Small HUD: wind direction, sail setting, time of day | UI | T1, T5 | todo | | |
| T10 | Interaction system: an interface any actor can implement and a component that finds the best target in front of the player, shows a prompt and calls Interact | Harvest | | needs compile | lane/harvest-T10-interaction | `ILyrisInteractable` + `ULyrisInteractionComponent` in `Source/Lyris/Interaction/` |
| T11 | Items and inventory foundation: item definitions as data assets, an inventory component with stacks and change events | Harvest | | needs compile | lane/harvest-T11-items | Collecting will extend this later |
| T12 | Gathering nodes: rocks to mine, trees to chop, plants to forage; data-driven yields, tool required, respawn on real-world time so they refill while you're away | Harvest | T10, T11 | needs compile | lane/harvest-T12-gathering | |
| T13 | Farming plots: plant a seed, grow through stages on real-world time, harvest; nothing withers, watering speeds growth instead of being required | Harvest | T10, T11 | needs compile | lane/harvest-T13-farming | Built to `design/farming.md` first step: `ALyrisFarmPlot` (grid of 100 cm `FLyrisSoilCell`s traced to the ground), `ULyrisCropDefinition` + `ULyrisCropRegistry`; till, plant, water, daily care, harvest, regrow on UTC timestamp maths. Fertilizer, seasons and P1-P6 left as hooks |
| T14 | Give the player character the interaction and inventory components and an Interact input | Player | T10, T11 | todo | | Hand-off from Harvest. Input actions are `.uasset`s, which cloud agents can't author: create them in code or via an editor script. The boat already uses E to step ashore at the dock, so pick a key that doesn't clash, or make E context-aware |
| T15 | Place sample rocks, trees and a farming plot on the Harbor island; bump `BUILD_VERSION` | Environment | T12, T13 | todo | | Hand-off from Harvest |
| T16 | Interaction prompt and a simple inventory view | UI | T10, T11 | todo | | |
| T17 | Sea state: one shared wave field (a few summed Gerstner waves) with a `GetWaveHeight/Normal(XY, Time)` query every system reads, so boat, swimmer and visuals agree. Calm swell in lamp-lit waters, longer rolling swells out in unlit waters, room for storms later | World | | needs compile | lane/world-T17-sea-state | Added by the user on 2026-10-20: water like Sea of Thieves, fitted to our pillars. Same "one shared source" pattern as T5 wind. `ULyrisOceanSubsystem` + `ULyrisOceanSettings` per `Source/Lyris/World/OCEAN_CONTRACT.md`; writes `MPC_Sea` each tick. Not compiled |
| T18 | Boat buoyancy: replace the sine bob in `ALyrisBoat::UpdateFloating` with a few float points sampling T17, so the boat rides up and over swells, pitches into them and heels; spray at the bow at speed | Sailing | T17, T5 | needs compile | lane/sailing-T18-buoyancy | 4 float points (configurable) sample `GetWaterHeightAt`; plane fit gives heave, pitch, roll, smoothed by critically damped springs; wind/rudder heel on top; still kinematic. Drift from `GetWaterVelocityAt` with sail down, up to 20% slower climbing swells. Bow spray is a hook (`OnBowSpray` BlueprintImplementableEvent, no asset yet). "Splash!" teleport removed; boarding ladder (basic shapes) on the port quarter, board from the water within `BoardRadius` or `LadderRadius`. Flat `WaterHeight` fallback. Not compiled |
| T19 | Sea surface that matches T17: a finer sea mesh and a material that displaces with the same wave values, foam on crests and at the shoreline, painterly palette colours | Environment | T17 | needs compile | lane/environment-T19-sea-surface | Hand-off from World. Reads wave params from `MPC_Sea` written by T17, so visuals never drift from physics. Harbor v9: `MPC_Sea`, Gerstner `M_Sea_v9` (custom HLSL), camera-following clipmap mesh, shallows and shore foam from island ground height (replaces the flat Shallows disc). Not run in the editor yet |
| T20 | Swimming: falling in means swimming, not a teleport. Bob on the waves, swim to shore, climb aboard by a ladder. No drowning and no stamina timer; the tide still carries you home if you drift too far | Player | T17 | needs compile | lane/player-T20-swimming | `ULyrisSwimComponent` (Player/): flying-mode swim with own buoyancy on T17 waves, kick, climb out onto the dock, wade out at the shore, tide fades you home past 80 m. Merge after T17. Sailing removes the "Splash!" teleport in T18 and adds a ladder |
| T21 | Rough water and the hull: in big swells or on rocks the boat takes on water and grows sluggish; bail with a bucket and patch with planks. Never sinks for good: a swamped boat drifts back to the nearest lit harbor | Sailing | T18 | needs compile | lane/sailing-T21-hull | `ULyrisHullComponent` + `ALyrisHarborMooring` in `Sailing/`; 4 small hooks in `LyrisBoat` (PR lists them). Q bail, R patch (keys read like the boat's others). Planks: built-in `plank` item, free patching until T14 gives the player an inventory. Needs a mooring placed in Moonharbor (else the boat returns to its start point). Not compiled |
| T22 | Character creator spec: the seven voyage steps, the full appearance option catalog (body, face sculpt, eyes, hair, skin, makeup, markings), style limits and curated palettes | Design | | done | lane/design-T22-creator-spec | Merged #9. `design/character_creator.md`: 138 sliders, 195 parts in 22 slots, 29 colour channels. People perks, preset names and new swatch hexes need the user's OK |
| T23 | Appearance system: `FLyrisAppearance` and `FLyrisCharacterProfile`, a data-driven slider/part/colour catalog, a component that applies it to the character (bones now, morph targets once T25 lands), save game and share codes | Player | | in progress | lane/player-T23-appearance | Contract fixed by the lead in the T23/T24 briefs |
| T24 | Character creator screen: seven steps, deep appearance tabs, click-and-drag face sculpting, orbit/zoom camera, lighting previews, randomise with locks, undo/redo, symmetry, presets and share codes | UI | T23 | in progress | lane/ui-T24-character-creator | Built in C++ Slate, no `.uasset` needed |
| T25 | Stylized base character mesh with morph targets for the face and body sliders, two frames, generated by script in `Art/Character/` | Environment | T22 | in progress | lane/environment-T25-base-character | Until then sliders drive bone scales on the template mannequin. Skeleton must match the UE5 mannequin so existing animations work |
| T26 | Start new players in the character creator (dusk voyage stage), then drop them on the Harbor dock with their look applied | Lead | T23, T24 | todo | | |
| T32 | Breath stamina and movement: `ULyrisStaminaComponent`, sprint, variable jump with coyote time and buffer, climbing as a custom movement mode with leap, wall kick and mantle; tuning in Project Settings | Player | T31 | needs compile | lane/player-T32-breath-movement | Logic in `Source/Lyris/Player/` (stamina, `ULyrisCharacterMovementComponent`, settings at Project Settings > Game > Lyris Movement); `LyrisCharacter` edits kept small for the T20 merge. Swimming never drains or blocks Breath. Sprint input made in code. Not compiled |
| T33 | Breath ring HUD: the stamina ring beside the head (colour ramp, drain trail, vial, leap cost preview, tea halo, recovery notch, hides when full) | UI | T32 | needs compile | lane/ui-T33-breath-ring | Depends on T32 merging first. Pure C++ Slate (`SLyrisBreathRing` + `ULyrisBreathRingSubsystem`), no `.uasset` |
| T34 | World gazetteer: every canon place on the Lyris map with block coordinates (from the server builds and the atlas), plus a proposal for new island chains in the straits and open sea, each marked *new, needs the user's OK* | Design | | in review | `lane/design-T34-world-gazetteer` | `design/world_map.md` + `design/world_map_overview.jpg`. 8 proposed island chains (A to H) await the user's OK; canon conflicts listed in section 6. Feeds T35 to T37 |
| T35 | Lyris world terrain at full size: a World Partition map `/Game/Lyris/Maps/Lyris`, 25 x 25 km, generated by script from the atlas (heightmap, biomes, lakes, rivers) with Genshin-style detail on top; sea out to the horizon; painterly landscape material by biome | Environment | | in review | lane/environment-T35-world-terrain | New script, separate from the Harbor script. Atlas in `Art/World/atlas/`. `Art/World/bake_terrain.py` bakes 8 x 8 tiles of 2048 px (1.53 m/vertex, 129 x 129 components) plus 8 paint layers; `Content/Python/lyris_build_world.py` builds the map, water, light and spawn; landscape import is a logged manual step. West Volcano cone and crater on Saltreach's spine. Not run in Unreal |
| T36 | Place canon landmarks at their real spots (Moonharbor, Observatory, Ilwen's Lighthouse, Delvers' Gate, Oruth's bay, Keep Elariel and the rest) as blockout buildings, and the approved new islands | Environment | T34, T35 | todo | | |
| T37 | Retire the Harbor map: make Lyris the default map, move the boat, dock and dock lamp into Moonharbor, repoint T4, T15 and T19 at the Lyris map, and update CLAUDE.md | Lead | T35, T36 | todo | | User decision 2026-10-20 |

## Next

| ID | Task | Lane | Depends on | Status | Branch | Notes |
|---|---|---|---|---|---|---|
| T27 | Write the chosen geography (Inner Sea) and mystery (Forgetting Sea) into `Game_Concept.xlsx` and a short canon note in `design/lore/`, flagging anything new for the user's OK | Design | | todo | | Follows T9 |
| T7 | Remove the unused template variants (Combat, Platforming, SideScrolling) | Lead | | needs compile | lane/lead-T7-remove-template | |

## Proposed

Ideas or requests an agent ran into that are not scheduled yet.

| ID | Task | Lane | Raised by | Notes |
|---|---|---|---|---|
| T38 | Save and restore farm plots, resource nodes and inventories between sessions (hooks exist: `GetCells`/`RestoreCells`, `RestoreDepleted`) | Lead | Harvest (T13 PR) | Needed before farming is playable across restarts; owner to be set when the save system is designed |
| T39 | Fix `design/farming.md` §3 before seasons (P3): multiplying all elapsed time by the season factor would make a ripe crop look unripe again when it goes dormant. Bank growth at each season change, like watering | Design | Harvest (T13 PR) | Breaks the farming one rule if left; see the comment on `GetSeasonFactor` |
| T40 | A way to get Plank items (chop wood into planks at a workbench, or buy them at the dock) so hull patching works once T14 gives the player an inventory | Harvest | Sailing (T21 PR) | Until then patching is free; with an inventory and no planks you can still bail and be carried home |
| T41 | Place an `ALyrisHarborMooring` at the Harbor dock (and Moonharbor later) so swamped boats come home to the dock, not the level start | Environment | Sailing (T21 PR) | Harbor build script; bump `BUILD_VERSION` |
| T42 | Bow spray effect driven by `ALyrisBoat::OnBowSpray`: a Blueprint child with Niagara, or add `Niagara` to `Lyris.Build.cs` so Sailing spawns it in C++ | Lead / Sailing | Sailing (T18 PR) | Needs the editor or a module dependency |
| T43 | Swimming and bailing animations: tread water, swim stroke, kick, climb out, wade, bail, patch | Player | Player (T20 PR) | Anim blueprint reads `IsSwimming()` / `IsClimbingOut()` |
| T44 | Turn the boat's raw keys (E board, Q bail, R patch, W/S/A/D sail) into Enhanced Input actions | Player | Sailing (T21 PR) | After T14 |
| P1 | Charged tools: hoe and watering can that work on 3×3, then 5×5 cells | Harvest | Design (T28) | `design/farming.md` §7 step 2 |
| P2 | Irrigation runes: placeable stones that keep the watering bonus on in a radius | Harvest | Design (T28) | §7 step 4 |
| P3 | Seasons in the real-time calendar, plus rain that waters crops | World | Design (T28) | Farming reads them for dormancy and in-season bonus (§6) |
| P4 | Special soils and glasshouses | Harvest | Design (T28) | §7 step 5; soils found on far islands |
| P5 | Scarecrow constructs that harvest, replant and care in a radius | Harvest | Design (T28) | §7 step 6; objects, not creatures |
| P6 | Crop hover tooltip: stage, time to ripe, active bonuses | UI | Design (T28) | Shows that tending helps without nagging |

## Done

| ID | Task | Lane | Merged |
|---|---|---|---|
| T31 | Movement and stamina spec (Breath) | Design | 2026-10-20 (PR #7) |
| T28 | Farming spec: Stardew-style farming in 3D with bonuses only, never punishment (`design/farming.md`, approved by the user) | Design | 2026-10-20 (PR #4) |
| T9 | Options for geography and the central mystery; user chose the Inner Sea and the Forgetting Sea | Design | 2026-10-20 (PR #2) |
| T8 | Generated `Content/Lyris/` assets stay out of git and are rebuilt by script (see DECISIONS) | Lead | 2026-10-20 |
