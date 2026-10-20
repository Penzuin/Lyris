# Task board

The live list of work. Agents update their own row in their PR. Only the lead moves tasks
between sections or assigns them.

Status: `todo` · `in progress` · `in review` (PR open) · `needs compile` (merged, waiting for
a build on the user's PC) · `done` · `blocked`

## Now: first prototype

Goal (from `README.md`): one island, one boat sailing in the wind, a day/night cycle, and a
dock lamp that holds back the mist at night.

| ID | Task | Lane | Depends on | Status | Branch | Notes |
|---|---|---|---|---|---|---|
| T1 | Day/night cycle: a clock actor that drives sun angle, sky and light colour; time speed adjustable for testing | World | | todo | | Sun and sky are currently placed by the Harbor script |
| T2 | Nightly mist that rises after dusk and clears at dawn | World | T1 | todo | | |
| T3 | Lamps hold back the mist: a lit lamp clears a radius around it; the dock lamp is the first one | World | T2 | todo | | Dock lamp is spawned by the Harbor script |
| T4 | Place the day/night actor, mist and lamp component in the Harbor map; bump `BUILD_VERSION` | Environment | T1, T2, T3 | todo | | Hand-off task |
| T5 | One shared world wind (a single source all boats read), drifting slowly across the compass with gusts and calms; replaces the per-boat sine wobble in `ALyrisBoat::GetWindYaw` | Sailing | | todo | | Today wind only swings ±25° around `BaseWindYaw` |
| T6 | Small HUD: wind direction, sail setting, time of day | UI | T1, T5 | todo | | |

## Next

| ID | Task | Lane | Depends on | Status | Branch | Notes |
|---|---|---|---|---|---|---|
| T7 | Decide whether to delete the unused template variants (Combat, Platforming, SideScrolling) | Lead | user decision | todo | | |
| T8 | Decide whether generated `Content/Lyris/` assets are committed or rebuilt on each PC | Lead | user decision | todo | | Right now they are rebuilt by the script |
| T9 | Open questions from the concept sheet: how seas and islands sit around the three regions; the central mystery | Design | | todo | | |

## Combat (spec: `design/combat.md`)

| ID | Task | Lane | Depends on | Status | Branch | Notes |
|---|---|---|---|---|---|---|
| C1 | Combat design spec: solo Genshin-style action, attunements, world reactions, enemies, defeat | Design | | in review | `lane/design-C1-combat-spec` | |
| C2 | Combat prototype: combo, charged attack, dash with perfect-dodge Lull, stamina, soft target, hit-stop; Lantern attunement (Flare Art, Lighthouse Beam Surge); Dispel reaction; mist crawler enemy; training ground actor | Combat | C1 | todo | | Reads keys directly until C4 lands |
| C3 | Place the combat training ground on the island in the Harbor map; bump `BUILD_VERSION` | Environment | C2 | todo | | Hand-off task |
| C4 | Enhanced Input actions for combat (attack, dash, Art, Surge, lock-on) and gamepad mapping; replace C2's direct key reads | Player | C2 | todo | | |
| C5 | Combat HUD: health, stamina, Art cooldown, Surge charge, enemy health and poise | UI | C2 | todo | | |
| C6 | Real attack, dodge and hit animations (montages) instead of mannequin placeholders | Combat | C2 | todo | | Needs animation assets |
| C7 | Defeat returns you to the last lamp you lit | Combat | C2, T3 | todo | | Prototype uses the dock |

## Proposed

Ideas or requests an agent ran into that are not scheduled yet.

| ID | Task | Lane | Raised by | Notes |
|---|---|---|---|---|

## Done

| ID | Task | Lane | Merged |
|---|---|---|---|
