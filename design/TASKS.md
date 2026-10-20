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

## Next

| ID | Task | Lane | Depends on | Status | Branch | Notes |
|---|---|---|---|---|---|---|
| T7 | Remove the unused template variants (Combat, Platforming, SideScrolling) | Lead | | in progress | lane/lead-T7-remove-template | |
| T9 | Open questions from the concept sheet: how seas and islands sit around the three regions; the central mystery | Design | | blocked | lane/design-T9-open-questions | Options merged in `design/lore/T9_open_questions.md` (PR #2); waiting for the user to pick |

## Proposed

Ideas or requests an agent ran into that are not scheduled yet.

| ID | Task | Lane | Raised by | Notes |
|---|---|---|---|---|

## Done

| ID | Task | Lane | Merged |
|---|---|---|---|
| T8 | Generated `Content/Lyris/` assets stay out of git and are rebuilt by script (see DECISIONS) | Lead | 2026-10-20 |
