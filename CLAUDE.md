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

## While you work

- **Stay in your lane.** If your task needs a change in a path another lane owns (a new
  actor placed in the Harbor map, a new input action, a line in `Lyris.Build.cs`), do not
  make it. Write it in your PR under "Needs from other lanes" and add a task to the board.
- **One task, one branch.** Name it `lane/<lane>-<task-id>-<short-name>`, e.g.
  `lane/world-T1-day-night`. Never commit to `main`.
- **Binary assets are never shared.** `.uasset` and `.umap` files cannot be merged. Only
  the owning lane edits them, and if file locking is ever turned on, locked files are off limits.
- **The Harbor map is generated.** `/Game/Lyris/Maps/Harbor` is rebuilt by
  `Content/Python/lyris_build_harbor.py` whenever `BUILD_VERSION` changes. Hand edits to
  the map are lost. Only the Environment lane edits that script.
- **New C++ goes in your lane's folder** under `Source/Lyris/<Lane>/`, with class names
  prefixed `Lyris` (e.g. `ALyrisMistVolume`).
- **Storybook painterly palette.** Colors come from the `PALETTE` in the Harbor build
  script. Do not invent new hex values for world art; ask the Environment lane.

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
- `Variant_Combat`, `Variant_Platforming` and `Variant_SideScrolling` are leftover
  Unreal template code. Do not build on them.
