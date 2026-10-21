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
| 2026-10-20 | Character creation is deep, in the spirit of Black Desert and Where Winds Meet (many sliders, face sculpting, layered colours, presets), but stays in the storybook painterly style: slider ranges keep stylized proportions and colours come from curated, hue-shiftable palettes. Supersedes "simple, readable sliders" for the Appearance step. |
| 2026-10-20 | Water like Sea of Thieves, fitted to Lyris: rolling waves that boats ride and players swim in; calm in lamp-lit waters, rougher in unlit waters. No drowning. Boats take on water and can be bailed and patched, but never sink for good: a swamped boat drifts back to the nearest lit harbor. |
| 2026-10-20 | Geography: **the Inner Sea** (option A in `design/lore/T9_open_questions.md`). The strait between the three regions is a wide sea of islands; the Quiet Reach on the north shore, Saltreach and Sunreach on the south; Moonharbor's bay is home waters. |
| 2026-10-20 | Central mystery: **the Forgetting Sea** (option 2). Where no light is kept, the world is being forgotten; relighting lamps, charting stars and learning islands' stories brings lost islands back for everyone. No single ending; shared milestones over time. |
| 2026-10-20 | Farming: nothing is lost by not tending; tending only adds. Crops grow on real-world time (offline too) at a base rate and never wilt, die, get eaten or lose progress. Watering, fertilizer, daily care and scarecrows only add speed, quality or yield. Out-of-season crops go dormant instead of dying. Progression comes from knowledge and crafted upgrades (irrigation runes, soils, glasshouses, constructs), not farming levels. Spec: `design/farming.md`. |
| 2026-10-20 | Movement: walking and jumping are free; sprinting and climbing draw from one stamina pool, **Breath**, shown as a ring beside the character's head (spec: `design/movement_stamina.md`). Running dry leaves you Winded (no sprint or climb until 35%), never hurt. Swimming never uses Breath. |
| 2026-10-20 | Peoples (Humans, Moonlit elves, Deepkin) differ in look only: no flavour perks. |
| 2026-10-20 | Character creator colours: the new skin, hair, eye and makeup swatches in `design/character_creator.md` are approved, even where they fall outside the Harbor `PALETTE`. |
| 2026-10-20 | A character's People can be changed after creation; where (mirror, academy, elsewhere) is still open. |
| 2026-10-20 | Faith is not chosen in the character creator. Players join a faith when they find it through a quest. The creator has six steps: People, Appearance, Path, Backstory, Lantern, Name. |
| 2026-10-20 | Backstories stay as listed in the spec for now; the user will expand them later. Preset names in the spec are approved. |
| 2026-10-20 | **World map: the real Lyris map at full size.** The game world is the Lyris Minecraft world at 1 block = 1 m: 25 x 25 km, about 121 km² of land (atlas in `lyris-companion/atlas`). Coastlines, rivers, lakes and landmarks stay where the map has them; Moonharbor sits on its round northern bay. New island chains are added in the straits and open sea so there is plenty to sail to (each needs the user's OK). Supersedes the Inner Sea placement of Moonharbor on the south coast. |
| 2026-10-20 | The Harbor test map is retired. The Lyris world map replaces it as the only map; the boat, dock and lamp move into Moonharbor. |
| 2026-10-20 | New island chains A to H from `design/world_map.md` are approved (Lampwick Skerries, Hushed Isles, Wickstones, Tallow Banks, Southing Stones, Rime Skerries, Unremembered Isles, Ember Isle). The places marked *placed by us* in the gazetteer stand unless the user changes them. |
| 2026-10-20 | The canon West Volcano (Cinderhorn, Carapotl) is part of Saltreach's snowy mountain spine, not a separate island. Ember Isle (H) stays but needs a new purpose without the volcano. |
| 2026-10-20 | The mist stays in the Quiet Reach and its seas, as on the server. The far south and west are dangerous for other reasons (storms, reefs, distance), not mist. |
| 2026-10-20 | The world is pure landscape for now: landmark blockouts are hidden, not deleted. The user's labelled Lyris map (design/reference/lyris_map_wonders.jpg) is the reference: all 22 natural wonders and the Lantern Isles become real sculpted terrain (creative liberty, Genshin-style), islands A to H stay, and the world gets the starter island's look and its Genshin-style trees, bushes and grass, placed by terrain. |
