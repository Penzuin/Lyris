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
| T10 | Interaction system: an interface any actor can implement and a component that finds the best target in front of the player, shows a prompt and calls Interact | Harvest | | in progress | lane/harvest-T10-interaction | |
| T11 | Items and inventory foundation: item definitions as data assets, an inventory component with stacks and change events | Harvest | | in progress | lane/harvest-T11-items | Collecting will extend this later |
| T12 | Gathering nodes: rocks to mine, trees to chop, plants to forage; data-driven yields, tool required, respawn on real-world time so they refill while you're away | Harvest | T10, T11 | in progress | lane/harvest-T12-gathering | |
| T13 | Farming plots: plant a seed, grow through stages on real-world time, harvest; nothing withers, watering speeds growth instead of being required | Harvest | T10, T11 | in progress | lane/harvest-T13-farming | Build to `design/farming.md` (sections 1 to 5 and 9): timestamp growth, water bonus, fertilizer, daily care, quality |
| T14 | Give the player character the interaction and inventory components and an Interact input | Player | T10, T11 | todo | | Hand-off from Harvest. Input actions are `.uasset`s, which cloud agents can't author: create them in code or via an editor script. The boat already uses E to step ashore at the dock, so pick a key that doesn't clash, or make E context-aware |
| T15 | Place sample rocks, trees and a farming plot on the Harbor island; bump `BUILD_VERSION` | Environment | T12, T13 | todo | | Hand-off from Harvest |
| T16 | Interaction prompt and a simple inventory view | UI | T10, T11 | todo | | |
| T17 | Sea state: one shared wave field (a few summed Gerstner waves) with a `GetWaveHeight/Normal(XY, Time)` query every system reads, so boat, swimmer and visuals agree. Calm swell in lamp-lit waters, longer rolling swells out in unlit waters, room for storms later | World | | in progress | lane/world-T17-sea-state | Added by the user on 2026-10-20: water like Sea of Thieves, fitted to our pillars. Same "one shared source" pattern as T5 wind |
| T18 | Boat buoyancy: replace the sine bob in `ALyrisBoat::UpdateFloating` with a few float points sampling T17, so the boat rides up and over swells, pitches into them and heels; spray at the bow at speed | Sailing | T17, T5 | todo | | Wait for T5 to merge, both edit `LyrisBoat.cpp` |
| T19 | Sea surface that matches T17: a finer sea mesh and a material that displaces with the same wave values, foam on crests and at the shoreline, painterly palette colours | Environment | T17 | in progress | lane/environment-T19-sea-surface | Hand-off from World. Reads wave params from `MPC_Sea` written by T17, so visuals never drift from physics |
| T20 | Swimming: falling in means swimming, not a teleport. Bob on the waves, swim to shore, climb aboard by a ladder. No drowning and no stamina timer; the tide still carries you home if you drift too far | Player | T17 | in progress | lane/player-T20-swimming | Calm-by-default pillar; replaces the "Splash!" teleport in `LyrisBoat.cpp` (Sailing removes it in T18) |
| T21 | Rough water and the hull: in big swells or on rocks the boat takes on water and grows sluggish; bail with a bucket and patch with planks. Never sinks for good: a swamped boat drifts back to the nearest lit harbor | Sailing | T18 | todo | | The Sea of Thieves loop without the loss (see DECISIONS) |
| T22 | Character creator spec: the seven voyage steps, the full appearance option catalog (body, face sculpt, eyes, hair, skin, makeup, markings), style limits and curated palettes | Design | | in progress | lane/design-T22-creator-spec | `design/character_creator.md`. User asked for Black Desert / Where Winds Meet depth, kept storybook painterly |
| T23 | Appearance system: `FLyrisAppearance` and `FLyrisCharacterProfile`, a data-driven slider/part/colour catalog, a component that applies it to the character (bones now, morph targets once T25 lands), save game and share codes | Player | | in progress | lane/player-T23-appearance | Contract fixed by the lead in the T23/T24 briefs |
| T24 | Character creator screen: seven steps, deep appearance tabs, click-and-drag face sculpting, orbit/zoom camera, lighting previews, randomise with locks, undo/redo, symmetry, presets and share codes | UI | T23 | in progress | lane/ui-T24-character-creator | Built in C++ Slate, no `.uasset` needed |
| T25 | Stylized base character mesh with morph targets for the face and body sliders, two frames, generated by script in `Art/Character/` | Environment | T22 | todo | | Until then sliders drive bone scales on the template mannequin |
| T26 | Start new players in the character creator (dusk voyage stage), then drop them on the Harbor dock with their look applied | Lead | T23, T24 | todo | | |

## Next

| ID | Task | Lane | Depends on | Status | Branch | Notes |
|---|---|---|---|---|---|---|
| T27 | Write the chosen geography (Inner Sea) and mystery (Forgetting Sea) into `Game_Concept.xlsx` and a short canon note in `design/lore/`, flagging anything new for the user's OK | Design | | todo | | Follows T9 |
| T7 | Remove the unused template variants (Combat, Platforming, SideScrolling) | Lead | | needs compile | lane/lead-T7-remove-template | |

## Proposed

Ideas or requests an agent ran into that are not scheduled yet.

| ID | Task | Lane | Raised by | Notes |
|---|---|---|---|---|
| P1 | Charged tools: hoe and watering can that work on 3×3, then 5×5 cells | Harvest | Design (T28) | `design/farming.md` §7 step 2 |
| P2 | Irrigation runes: placeable stones that keep the watering bonus on in a radius | Harvest | Design (T28) | §7 step 4 |
| P3 | Seasons in the real-time calendar, plus rain that waters crops | World | Design (T28) | Farming reads them for dormancy and in-season bonus (§6) |
| P4 | Special soils and glasshouses | Harvest | Design (T28) | §7 step 5; soils found on far islands |
| P5 | Scarecrow constructs that harvest, replant and care in a radius | Harvest | Design (T28) | §7 step 6; objects, not creatures |
| P6 | Crop hover tooltip: stage, time to ripe, active bonuses | UI | Design (T28) | Shows that tending helps without nagging |

## Done

| ID | Task | Lane | Merged |
|---|---|---|---|
| T28 | Farming spec: Stardew-style farming in 3D with bonuses only, never punishment (`design/farming.md`, approved by the user) | Design | 2026-10-20 (PR #4) |
| T9 | Options for geography and the central mystery; user chose the Inner Sea and the Forgetting Sea | Design | 2026-10-20 (PR #2) |
| T8 | Generated `Content/Lyris/` assets stay out of git and are rebuilt by script (see DECISIONS) | Lead | 2026-10-20 |
