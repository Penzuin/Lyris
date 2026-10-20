# Decisions log

Settled choices. Agents follow these; only the user changes them. Newest at the bottom.

| Date | Decision |
|---|---|
| 2026-10-20 | The game is set in the world of Lyris, keeping the other influences (Genshin, Stardew, Outer Wilds, Sea of Thieves, Minecraft, Animal Crossing, Slime Rancher, Miniplanet, Black Desert). |
| 2026-10-20 | No creature raising. Wildlife is observed and documented, never owned or raised. |
| 2026-10-20 | Engine: Unreal Engine 5.8. Binaries in Git LFS. Repo: Penzuin/Lyris. |
| 2026-10-20 | Art style: Storybook painterly (stylized, warm, saturated). Terrain should feel closer to Sea of Remnants, using Genshin-style terrain techniques. |
| 2026-10-20 | A dark academia academy at the Observatory is the roleplay hub; RPG with paths and skills by doing, no stats and no XP grind. |
| 2026-10-20 | First prototype: one island, one boat sailing in the wind, a day/night cycle, and a dock lamp that holds back the mist at night. |
| 2026-10-20 | Claude writes changes directly in code and files, rather than operating the user's screen. |
| 2026-10-20 | Multiple agents work in lanes (`design/LANES.md`), one branch per task, PRs merged by the lead. |
| 2026-10-20 | Generated content (`Content/Lyris/`, the Harbor map and its materials) stays out of git; each PC rebuilds it from the scripts in `Content/Python/`. |
| 2026-10-20 | The unused Unreal template variants (Combat, Platforming, SideScrolling) are removed. |
