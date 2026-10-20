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

## Proposed

Ideas or requests an agent ran into that are not scheduled yet.

| ID | Task | Lane | Raised by | Notes |
|---|---|---|---|---|

## Done

| ID | Task | Lane | Merged |
|---|---|---|---|
