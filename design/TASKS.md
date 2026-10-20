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
| T5 | One shared world wind (a single source all boats read), drifting slowly across the compass with gusts and calms; replaces the per-boat sine wobble in `ALyrisBoat::GetWindYaw` | Sailing | | in progress | lane/sailing-T5-world-wind | Today wind only swings ±25° around `BaseWindYaw` |
| T6 | Small HUD: wind direction, sail setting, time of day | UI | T1, T5 | todo | | |
| T10 | Interaction system: an interface any actor can implement and a component that finds the best target in front of the player, shows a prompt and calls Interact | Harvest | | in progress | lane/harvest-T10-interaction | |
| T11 | Items and inventory foundation: item definitions as data assets, an inventory component with stacks and change events | Harvest | | in progress | lane/harvest-T11-items | Collecting will extend this later |
| T12 | Gathering nodes: rocks to mine, trees to chop, plants to forage; data-driven yields, tool required, respawn on real-world time so they refill while you're away | Harvest | T10, T11 | in progress | lane/harvest-T12-gathering | |
| T13 | Farming plots: plant a seed, grow through stages on real-world time, harvest; nothing withers, watering speeds growth instead of being required | Harvest | T10, T11 | in progress | lane/harvest-T13-farming | Calm-by-default pillar |
| T14 | Give the player character the interaction and inventory components and an Interact input | Player | T10, T11 | todo | | Hand-off from Harvest. Input actions are `.uasset`s, which cloud agents can't author: create them in code or via an editor script |
| T15 | Place sample rocks, trees and a farming plot on the Harbor island; bump `BUILD_VERSION` | Environment | T12, T13 | todo | | Hand-off from Harvest |
| T16 | Interaction prompt and a simple inventory view | UI | T10, T11 | todo | | |
| T17 | Sea state: one shared wave field (a few summed Gerstner waves) with a `GetWaveHeight/Normal(XY, Time)` query every system reads, so boat, swimmer and visuals agree. Calm swell in lamp-lit waters, longer rolling swells out in unlit waters, room for storms later | World | | todo | | Added by the user on 2026-10-20: water like Sea of Thieves, fitted to our pillars. Same "one shared source" pattern as T5 wind |
| T18 | Boat buoyancy: replace the sine bob in `ALyrisBoat::UpdateFloating` with a few float points sampling T17, so the boat rides up and over swells, pitches into them and heels; spray at the bow at speed | Sailing | T17, T5 | todo | | Wait for T5 to merge, both edit `LyrisBoat.cpp` |
| T19 | Sea surface that matches T17: a finer sea mesh and a material that displaces with the same wave values, foam on crests and at the shoreline, painterly palette colours | Environment | T17 | todo | | Hand-off from World. Wave params must come from one place so visuals never drift from physics |
| T20 | Swimming: falling in means swimming, not a teleport. Bob on the waves, swim to shore, climb aboard by a ladder. No drowning and no stamina timer; the tide still carries you home if you drift too far | Player | T17 | todo | | Calm-by-default pillar; replaces the "Splash!" teleport in `LyrisBoat.cpp` (Sailing removes it in T18) |
| T21 | Rough water and the hull: in big swells or on rocks the boat takes on water and grows sluggish; bail with a bucket and patch with planks. Never sinks for good: a swamped boat drifts back to the nearest lit harbor | Sailing | T18 | todo | | The Sea of Thieves loop without the loss; needs the user's OK on "never sinks" before it starts |
| T22 | Character creator spec: the seven voyage steps, the full appearance option catalog (body, face sculpt, eyes, hair, skin, makeup, markings), style limits and curated palettes | Design | | in progress | lane/design-T22-creator-spec | `design/character_creator.md`. User asked for Black Desert / Where Winds Meet depth, kept storybook painterly |
| T23 | Appearance system: `FLyrisAppearance` and `FLyrisCharacterProfile`, a data-driven slider/part/colour catalog, a component that applies it to the character (bones now, morph targets once T25 lands), save game and share codes | Player | | in progress | lane/player-T23-appearance | Contract fixed by the lead in the T23/T24 briefs |
| T24 | Character creator screen: seven steps, deep appearance tabs, click-and-drag face sculpting, orbit/zoom camera, lighting previews, randomise with locks, undo/redo, symmetry, presets and share codes | UI | T23 | in progress | lane/ui-T24-character-creator | Built in C++ Slate, no `.uasset` needed |
| T25 | Stylized base character mesh with morph targets for the face and body sliders, two frames, generated by script in `Art/Character/` | Environment | T22 | todo | | Until then sliders drive bone scales on the template mannequin |
| T26 | Start new players in the character creator (dusk voyage stage), then drop them on the Harbor dock with their look applied | Lead | T23, T24 | todo | | |

## Next

| ID | Task | Lane | Depends on | Status | Branch | Notes |
|---|---|---|---|---|---|---|
| T7 | Remove the unused template variants (Combat, Platforming, SideScrolling) | Lead | | in progress | lane/lead-T7-remove-template | |
| T9 | Open questions from the concept sheet: how seas and islands sit around the three regions; the central mystery | Design | | blocked | lane/design-T9-open-questions | Options merged in `design/lore/T9_open_questions.md` (PR #2); waiting for the user to pick |

## Proposed

Ideas or requests an agent ran into that are not scheduled yet.

| ID | Task | Lane | Raised by | Notes |
|---|---|---|---|---|
| C1 | Combat design spec: solo Genshin-style action, attunements, world reactions, enemies, defeat (`design/combat.md`) | Design | user request (combat), Make a Game chat | PR open on `lane/design-C1-combat-spec`; direction approved by the user, logged in DECISIONS |
| C2 | Combat prototype: combo, charged and plunge attacks, dash with perfect-dodge Lull, stamina, Flare Art, Lighthouse Beam Surge, Dispel reaction, mist crawler, training ground | Combat *(new lane needed: `Source/Lyris/Combat/`, `Content/Lyris/Combat/`)* | user request (combat) | Written on `lane/combat-C2-prototype`, not compiled. Needs the lead to open a Combat lane. |
| C3 | Place an `ALyrisTrainingGround` on the island (meadow west of the path, e.g. around X -300, Y -350), `RespawnLocation` = the dock; bump `BUILD_VERSION` | Environment | C2 | Hand-off; keep it more than 25 m from the boat so E still boards |
| C4 | Enhanced Input actions for combat (attack, dash, Art, Surge, lock-on) plus gamepad; replace C2's direct key reads | Player | C2 | |
| C5 | Combat HUD: health, stamina, Art cooldown, Surge charge, enemy health and poise | UI | C2 | C2 shows a temporary on-screen readout |
| C6 | Real attack, dodge and hit animations, and an anim slot so montages play | Combat | C2 | C2 plays mannequin attacks on "DefaultSlot" if the anim blueprint has one |
| C7 | Defeat returns you to the last lamp you lit | Combat | C2, T3 | C2 returns you to the dock |

## Done

| ID | Task | Lane | Merged |
|---|---|---|---|
| T8 | Generated `Content/Lyris/` assets stay out of git and are rebuilt by script (see DECISIONS) | Lead | 2026-10-20 |
