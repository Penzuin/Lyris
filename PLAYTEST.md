# Playtest build: `test/playtest-1`

A test-only branch. **Never merge it into `main`.** It is `main` plus the open pull requests,
plus a small kit in `Source/Lyris/Playtest/` that stands in for hand-offs not built yet.
Other agents keep working on their own branches; nothing here touches them.

## What's in it (as of 2026-10-20)

| From | What you can try |
|---|---|
| `main` | Island, boat, shared wind (T5), Gerstner ocean (T17 World), swimming (T20) |
| PR #13 (T10) | Interaction: face something and press F |
| PR #14 (T11) | Items and the bag |
| PR #15 (T12) | Rocks, copper vein, tree, sea herb, star crystal that refill on real time |
| PR #16 (T13) | Farm plot: till, plant, water, tend, harvest; nothing withers |
| PR #6 (C2) | Hand-to-hand combat against mist crawlers at a training ground |

**Left out:** PR #11 (T33 Breath ring) needs the Player lane's stamina component (T32),
which isn't pushed yet, so it can't compile. Design-only PRs (#5, #7) have no code to test.

## The test kit (`Source/Lyris/Playtest/`)

- Gives your walking character a bag and the interaction component, plus a hoe, watering
  can, pickaxe, axe and seeds (stands in for T14).
- Spawns a 4 × 4 farm plot ahead of you, one of each resource node to your right, and the
  combat training ground about 30 m behind you, unless the map already has them (T15, C3).
- Draws the prompt and your bag in the top-left corner (stands in for T16).
- Runs timers about **300× faster**: turnips ripen in ~36 s, mistberries in ~72 s,
  moonbells in ~2.5 min, watering lasts ~48 s, nodes refill in seconds to minutes.

## Build and play

1. In GitHub Desktop: **Fetch origin**, then switch to branch `test/playtest-1`.
2. Double-click `Open Lyris.bat` (or right-click `Lyris.uproject` > Generate Visual Studio
   project files, then build). Let it compile.
3. Press **Play**.

## Controls

| Key | Does |
|---|---|
| **F** | Interact (E is the boat's step-ashore key) |
| **1-9** | Pick a bag slot (the selected seed is what you plant) |
| **I** | Show or hide the bag |
| **LMB** tap / hold / in air | Combo / roundhouse kick / stomp |
| **RMB** or **Shift** | Dash (dodge right before a lunge for slow-mo) |

Console (` key): `lyris.Playtest.Fast 0` for real-world timings, `lyris.Playtest 0` to turn the kit off.

## What to check

- **Farming:** face the plot, F to till, F to plant (slot 5 is turnip seeds), F to water
  (soil darkens), F to tend. Watch it grow, then F to harvest. Leave a crop unwatered: it
  still ripens, just slower.
- **Gathering:** F on the rock three times, then wait for it to come back.
- **Combat:** walk to the training ground, fight, and let them beat you once (you return to start).

## If it doesn't compile

Every PR here is marked "not compiled". Copy the first error from the Output Log into the
"Make a Game" chat; the fix goes to the PR that owns that file, then this branch is rebuilt.
