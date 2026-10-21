# Lyris: rules for every agent

You are one of several Claude agents working on this game. These rules keep you from
overwriting each other's work. Read them before you change anything.

## Before you start

1. Read `design/TASKS.md`. Work only on a task that is assigned to you or that the lead
   tells you to take. If you were asked to do something that is not on the board, add it
   under **Proposed** and tell the user, instead of starting it.
2. Read `design/LANES.md` and find your lane. You may only edit the paths your lane owns.
3. Read `design/DECISIONS.md`. Do not contradict a decision there. If you think one is
   wrong, say so to the user; do not quietly work around it.
4. For game content, the full concept is `design/Game_Concept.xlsx` and the pitch and
   pillars are in `README.md`.

## New task IDs

Several sessions add tasks at once, so IDs collide unless claimed first. To add a task:
`git pull` on `main`, take the next unused `T` number (or your lane's own prefix, like `C`
for Combat), and push that board row to `main` at once, before you start the branch. Only
a lead pushes to `main`; if you are not the lead, put the row under **Proposed** in your PR
with the ID `?` and the lead numbers it when merging.

## While you work

- **Stay in your lane.** If your task needs a change in a path another lane owns (a new
  actor placed in the Lyris world, a new input action, a line in `Lyris.Build.cs`), do not
  make it. Write it in your PR under "Needs from other lanes" and add a task to the board.
- **One task, one branch.** Name it `lane/<lane>-<task-id>-<short-name>`, e.g.
  `lane/world-T1-day-night`. Never commit to `main`.
- **Binary assets are never shared.** `.uasset` and `.umap` files cannot be merged. Only
  the owning lane edits them, and if file locking is ever turned on, locked files are off limits.
- **The Lyris world is generated.** `/Game/Lyris/Maps/Lyris` (the only map) is built by
  `Content/Python/lyris_build_world.py` and `lyris_build_landmarks.py` from `Art/World/`, and
  rebuilt whenever `BUILD_VERSION` in `lyris_build_world.py` changes. Hand edits to the
  actors it places are lost; the imported landscape is kept. Only the Environment lane edits
  those scripts, except the Lead for startup glue (`init_unreal.py`, the map in `Config/`).
- **Find placed actors by tag, not position.** The boat, dock point, tide home, mooring and
  dock lamp carry tags (`LyrisPlayerBoat`, `LyrisDockPoint`, `LyrisTideHome`,
  `LyrisHarborMooring`, `LyrisDockLamp`); see the notes at the top of `lyris_build_world.py`.
- **New C++ goes in your lane's folder** under `Source/Lyris/<Lane>/`, with class names
  prefixed `Lyris` (e.g. `ALyrisMistVolume`).
- **Storybook painterly palette.** Colors come from `PALETTE` and `ISLAND_PALETTE` in
  `lyris_build_world.py`. Do not invent new hex values for world art; ask the Environment lane.

## When you finish

- Rebase on `main`, then open a PR to `main`. The lead (the "Make a Game" Project chat)
  reviews and merges. Do not merge your own PR.
- The PR description has four short parts: **What changed**, **How to test in the
  editor**, **Compiled?** (yes, or "not compiled: written without an Unreal build"),
  **Needs from other lanes**.
- Update your task's row in `design/TASKS.md` in the same PR (status, branch, notes).
- If you made a design decision the user approved, add a line to `design/DECISIONS.md`.

## Engine notes

- Unreal Engine 5.8, C++ module `Lyris`, Git LFS for binaries (see `.gitattributes`).
- Cloud agents cannot run the editor or compile. Say so honestly in the PR; the user
  compiles on their PC.
