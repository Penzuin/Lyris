# How Genshin designs its towns and buildings (research note)

Background for `design/moonharbor_town_plan.md`. Gathered 2026-10-22 from public sources (list at the end).
miHoYo has published little in detail: the GDC 2021 talk *Crafting an Anime Style Open World* covers the
game's origins, style, stage design and pipeline, but no written summary of it exists. So each point says where
it comes from: **developers**, **outside analysis**, or **observed** (how the game plays, not a published source).

## 1. Real places are a starting point, then rebuilt (developers)

The developers say they wanted a completely fictional fantasy world, not a realistic one. Real references are
taken apart and recreated, not copied. Each city mixes several sources. Mondstadt is widely read as German and
Swiss (Bern), with a cathedral likened to Regensburg's. Liyue's gate comes from karst arches in southwest China,
a marsh from Guilin and Yangshuo, and an inn from Lingnan stilt houses.

**For Lyris:** Moonharbor already has its own canon from the server builds. Use real towns (Cornish and
Breton harbour towns, Mont-Saint-Michel's climb to the abbey) for *feel*, never as a copy.

## 2. Terrain decides the shape of the town (developers, outside analysis)

Mondstadt sits on flat plains and forest, so it has little vertical layout. Inazuma City sits at the south of its
island, with the Grand Narukami Shrine on the peaks above it. Sumeru City is built on a giant tree. The pattern:
the city grows out of one strong landform, and the most important building takes the highest ground.

## 3. Designed at three scales, boxed out first (developers, outside analysis)

Concept art is made at three levels: the region's geography, then landmarks and points of interest, then single
buildings and plants. There are mood boards for each time of day and weather. Liyue took about a year from
white-box testing to finished art and scenes.

## 4. One silhouette and one palette per region (outside analysis)

Regions are told apart by shape before detail: Liyue by curved rooflines, Inazuma by torii and shrines, Sumeru by
huge canopies and vines. Fontaine's Renaissance buildings are ornate but simplified to stay readable. Distant
temples are built to look detailed from far away even when they are simple meshes. Each region has a controlled
palette so scenes stay readable.

## 5. Landmarks replace map markers (outside analysis)

Big structures pull players toward them because players want to know what they are, so they guide without UI.
The tools are:
- **Scale:** the player feels small.
- **Framing:** control the first view.
- **Long-range visibility:** a clear silhouette from far away.
- **Contrast:** a glow or colour the land around it lacks.

One analysis also suggests revealing a landmark in stages, partly hidden by fog or rock at first.

## 6. Outsides are the playable space (outside analysis, observed)

An academic critique notes that most Genshin buildings are obstacles to climb or walk around, not rooms to
enter. Interiors are separate loaded spaces with no outside. Players experience a town mostly by walking its
streets and climbing its walls and roofs.

## 7. How Genshin towns play (observed)

- **Scaled down.** A capital is a few hundred metres across and takes about a minute to cross.
- **Chunky details.** Doors, windows, railings and props are oversized so they read at third-person camera
  distance.
- **Everything is climbable.** Roofs form a second network of paths, and tall landmarks have ledges to rest on.
- **One hub plaza** with a statue or fountain, ringed by shops and quest NPCs.
- **Harbour cities work in tiers.** Liyue Harbor runs docks, then a market terrace, then the seat of power at the
  top, joined by stairs and lifts, with the sea in view almost everywhere.
- **Lamps are planned in.** Towns read as clusters of lights at night, and dusk is when they look best.

## Sources

- [GDC 2021: Making Genshin Impact's open world](https://www.gdconf.com/news/learn-about-making-genshin-impacts-open-world-gdc-2021)
- [Genshin Impact a "completely fictional fantasy world", say devs (Yahoo)](https://sg.news.yahoo.com/genshin-impact-completely-fictional-fantasy-world-not-realistic-154715370.html)
- [Mondstadt (Wikipedia)](https://en.wikipedia.org/wiki/Mondstadt)
- [Locations of Genshin Impact (Wikipedia)](https://en.wikipedia.org/wiki/Locations_of_Genshin_Impact)
- [Genshin Impact concept art (Youngbow)](https://youngbow.com/genshin-impact-concept-art-how-mihoyo-creates-some-of-gamings-most-stunning-visuals/)
- [The visuals of Genshin Impact (VANAS)](https://www.vanas.ca/en/blog/the-incredible-visuals-of-genshin-impact)
- [How Genshin uses massive structures to drive curiosity (Medium)](https://medium.com/@ashgamedesign/how-genshin-impact-uses-massive-structures-to-drive-player-curiosity-66bb69db4d7b)
- [Inside and outside in Genshin's architecture (MediaCommons)](https://mediacommons.org/imr/node/16495)
- [Dragonspine behind the scenes (Siliconera)](https://www.siliconera.com/mihoyo-talks-about-building-genshin-impact-dragonspine/)
