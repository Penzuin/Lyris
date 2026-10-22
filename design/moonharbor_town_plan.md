# Moonharbor town plan (1.0, chunk M1, with the Keep Hill edge of M2)

How Moonharbor is laid out, built and dressed so it plays like a Genshin town, using the canon positions from
the server builds. Background: `design/genshin_town_design_research.md`. Diagram: `design/moonharbor/town_plan.png`,
made by `python design/moonharbor/render_town_plan.py` (needs matplotlib). It is not committed: run the script to
make it.

**What is canon and what is new.** Every position, footprint and height below comes from
`design/world_map.md` section 3 and `Art/World/landmarks.json`, and does not move. Everything about *treatment*
is new and marked *(new, needs the user's OK)* where it adds something to the world: tiers, sightlines, routes,
which buildings open, climbing rules, shape language and the arrival sequence. Coordinates are MC block X, Z
(Y = height; sea level is Y 63). North is more negative Z, and the bay lies north and west of the quay.

---

## 1. The big idea: a town that climbs from the water to the keep

Moonharbor already has the shape of a Genshin harbour city. The ground rises about 75 m from the quay (Y 64) to
Keep Elariel's gate (Y 138) in roughly 400 m. So the plan is **Liyue Harbor's tiers in a storybook northern
harbour**: water, then a hub plaza, then terraced houses, then the keep crowning the hill. The sea is in view
from almost every street.

| Tier | Ground | What is on it | Job in play |
|---|---|---|---|
| **Waterline** | Y 63 to 70 | The Harbour promenade and piers, Lantern Pier (arrival berth, dock lamp, Tide Mother shrine), the Seawall Stair, Ilwen's Lighthouse headland, the Chapel of Lamps, the Point and the Boatyard | Arrival, boats, the first lamp. The calm, busy, lit edge |
| **Square** | Y 65 to 80 | Market Square and the Moonwell (Town Hall, Museum, clock tower), Main Street and the Bright Cask, Festival Green, Moonmarket and the Constabulary, the Market district, Yards and Weavers | The hub: shops, quest givers, the Lamp Seller. Everything a new player needs within 40 seconds of the boat |
| **Terraces** | Y 80 to 100 | The Heights, the Grand Library, Lamplight, Wayside and the Carriage Station | Quieter streets, stairs, views back over the bay. The North Road and the fields start here |
| **Crown** | Y 100 to 140+ | The Rise, the Miners' Guild and its drift mouth, the Keep Road, Keep Elariel and the Moon Window | The first "go up there" goal. The best view in 1.0 |

Ground heights per tier are the landmark heights in `landmarks.json`, so they are close but not surveyed. The
Environment lane should check them against the T55 sculpt.

## 2. Landmark hierarchy (what the player navigates by)

Genshin guides with silhouettes, not markers. Moonharbor gets three tiers of landmark *(new, needs the user's OK)*:

**A. Hero landmarks.** Visible from the whole town and from the boat, each with its own silhouette and its own
light at night:
1. **Keep Elariel** on the crown (gate Y 138, walls 43.5 m tall). By day it's a pale stone mass on the hill. By
   night the **Moon Window** is the one MOONGLASS light high above town.
2. **Ilwen's Lighthouse** on the west headland (gallery Y 127). A slender calcite shaft with the warm
   LighthouseGlow beam sweeping the bay, the only warm moving light on the coast.
3. **Syrena's statue and the Hung Star** on the islet in the bay (84 m to the sword tip). Its silhouette breaks
   the sea horizon, and the fixed false star sits at the tip.

Together these make a triangle around the bay. A player who is lost looks up and finds one of the three.

**B. District anchors.** Each is visible down its own streets: the **clock tower** in Market Square, the **Grand
Library** dome or roof (25.85 m), the **Miners' Guild** and its drift mouth, the **Carriage Station**, the
**Boatyard** sheds and the **Chapel of Lamps**. Rule: from any street end in the Square tier, the clock tower or
the keep is in view.

**C. Street-level signs.** Shop signs, awnings, lamp posts at every junction and bunting over Main Street. These
are props, not landmarks.

## 3. Arrival: the first five minutes *(new, needs the user's OK)*

New players come from the creator's dusk voyage (T26, T47), so Moonharbor's first view is **at dusk, from the sea**.
Reveal it in stages, as Genshin frames its landmarks:

1. **Out on the water:** the lighthouse beam is the first thing seen, a warm sweep through the haze.
2. **Rounding into the bay:** Syrena's silhouette and the Hung Star appear against the sky.
3. **Inside the bay:** the town's lamps come up tier by tier, waterline first and keep last. The Moon Window
   lights high above everything.
4. **At the berth on Lantern Pier:** the player steps off beside the dock lamp, the first lamp they will tend.

From the berth (136, −2418), the plan keeps three sightlines open: to the keep gate, to the lighthouse and to
Syrena's islet. Nothing taller than the Stair Towers stands on those lines. The Environment lane checks these
when it places buildings.

## 4. Routes

**The golden path, pier to keep (about 570 m):** Lantern Pier → promenade → top of the Seawall Stair → Moonwell →
Festival Green → foot of the Keep Road (326, −2378) → switchbacks up the hill → keep gate (501, −2526). At walking
pace (4.5 m/s) the flat part, pier to Moonwell, takes about **40 seconds**. The whole climb takes about **2 to
2.5 minutes**.

- **The Keep Road climbs about 66 m** (Y 72 to 138) on a canon line whose middle is ours. That is far too steep to
  walk straight, so it **switchbacks** across the hill, with a viewpoint terrace at each turn facing the bay.
  These are the Genshin "stop and look" spots.

**Second route, Festival Green to the Carriage Station (about 270 m):** Main Street → Moonmarket → Lamplight →
Carriage Station, where the North Road leaves town. This is the way to Wayside Fields (M3) and, later, the
Observatory.

**Short cuts** *(new, needs the user's OK)*:
- **Stair lanes** run straight up between terraces wherever a street would switchback.
- **Rooftop lines** cross the Market and the Heights, with roofs close enough to hop (gaps of 1.5 m or less, an easy
  walking jump).
- **The Seawall itself** can be walked along its top (Y 78) from the Stair Towers to the Point.

**Lanes:** canon gives 5 m streets and 3 m lanes. At 3 m the third-person camera clips walls in tight turns. So
lanes stay 3 m between walls, but upper storeys don't overhang lanes, and Environment adds camera-blocking
volumes only where needed. Widening lanes would change canon, so it isn't proposed.

## 5. Climbing and the Breath budget

Breath (`design/movement_stamina.md`) gives about **22 m of steady climbing from full** (2.2 m/s at 10 Breath/s,
100 Breath), and nothing refills on the wall. Building heights are set around that *(new, needs the user's OK)*:

| Height | Rule | Examples |
|---|---|---|
| Up to 12 m | Climb freely; every house in the Market, Point, Yards, Weavers and Wayside | Two-storey houses (4 m storeys), shops, sheds |
| 12 to 20 m | One climb from full Breath. Give a ledge or balcony halfway | Town Hall, the Bright Cask, the Library walls, the Carriage Station |
| Over 20 m | **A standing ledge at least every 15 m of height**, where Breath refills | Keep walls (43.5 m), Stair Towers (35 m), clock tower (31 m), lighthouse shaft (to Y 127): its keeper's hall roof and gallery are the ledges |

Any wall at least 1.33 m tall counts as climbable, so low garden walls and terrace edges are mantled.

## 6. Building scale and shape

**Proportions.** These keep canon footprints but read well at camera distance:
- Storeys 4 m.
- Doors 3 m tall, 1.6 m wide.
- Windows 1.4 × 2 m, deep-set.
- Roofs pitched 45 to 55° with deep eaves.
- Chimneys oversized.
- One chunky detail per facade (a sign, a balcony, a lamp bracket) instead of many small ones.

**Shape and colour by district.** Each quarter "was once a village somewhere else" (canon), so each keeps its own
look. Wall and roof pairs are the ones `landmarks.json` already uses. All colours are names from `PALETTE` and
`ISLAND_PALETTE`, with no new hex values. The silhouette motifs are *(new, needs the user's OK)*.

| District | Walls / roofs | Silhouette motif | Signature props |
|---|---|---|---|
| **Market** | Sail / Terracotta | Gabled shopfronts facing the street, deep awnings | Striped awnings, bunting, crates, hanging signs |
| **The Point** | Wood / DarkWood | Low houses on stilts and slipways, boat-shed roofs | Net racks, upturned hulls, rope coils, the Boatyard cranes |
| **The Heights** | Stone / Clay | Tall and narrow, stepped gables, scholars' turrets | Book carts, stair rails, window boxes, the Library court |
| **Lamplight** | Salt / DarkWood | Steep roofs, lamp lanterns on every door | MOONGLASS lamp brackets, the most lamps per street in town |
| **The Rise** | Stone / RedBand | Terraced houses with walled gardens, stepping up the hill | Garden walls (climbable), viewing benches, Keep Road arches |
| **Yards** | Wood / Terracotta | Long workshop halls, open sides, hoists | Timber stacks, workbenches, a crane over the yard |
| **Weavers** | Sail / RedBand | Narrow houses with wide upper windows | Cloth drying on lines across the lanes, dye vats |
| **Wayside** | Salt / Wood | Low, wide inns and stables, fenced yards | Hay carts, fences, the Wayfarers' shrine by the station |

**Big buildings** each get one silhouette nobody else in town has:
- Keep: four front towers and the cathedral spire.
- Lighthouse: slender tapering shaft.
- Library: a dome or a long pitched hall with a lantern.
- Town Hall: the clock tower.
- Miners' Guild: a squat Deepkin hall with a headframe over the drift.
- Carriage Station: an arched coach hall.

**Where to look for feel:** Cornish and Breton harbour towns for the waterline, Mont-Saint-Michel for the climb
to the keep. These are mood references only.

## 7. What opens, and how *(new, needs the user's OK)*

Genshin keeps most buildings shut and puts interiors in separate loaded spaces. Moonharbor is small, so it can do
better. Small spaces are **seamless**: no loading screen, built in the same map. Large ones become **their own
spaces later**.

| Building | 1.0 | Why |
|---|---|---|
| Lamp Seller's stall (Moonmarket) | Open-air | First lamp oil; no interior needed |
| The Bright Cask | Seamless interior, ground floor | Social hub, quests, rumours |
| Two or three Main Street shops (bakery, apothecary) | Seamless interior, one room each | Buying and selling; the other shops are facades |
| Chapel of Lamps | Seamless interior | Lantern Covenant, the Lamp Tree |
| Boatyard | Open-sided shed | Boat crafting (T21 planks) |
| Town Hall | Ground-floor hall | Notice board, town quests |
| Grand Library | **Later**, its own space | Too big for 1.0. The doors are a "closed for cataloguing" hook |
| Miners' Guild and its deep chapel | **Later** | Leads to the Hollowdeep |
| Keep Elariel | **Courtyard and the Moon Window garden only** in 1.0 | The climb is the reward; halls come later |
| Houses | Facades | Player homes are a separate, open question |

## 8. Night and lamps

Lyris is about keeping lights lit, so Moonharbor is designed to look its best at dusk and night, like Genshin
towns:
- **A lamp post at every street junction and stair landing**, in MOONGLASS, so the town reads at night as lit
  tiers rising to the Moon Window.
- **The waterline is the brightest tier** (the dock lamp, the promenade, the lighthouse), so the town lights the
  bay.
- **Lamplight is the brightest district by design.** It's the quarter that keeps the lamps.
- **A few lamps start dark** on the edges of town (Wayside, the Point's far end) for the player to relight as
  first tasks *(new, needs the user's OK)*. This ties to T3 (lamps hold back the mist).

## 9. Build order for the Environment lane (T55)

Each step is boxes and planes only, so the plan can be tested before any art:

1. **Ground:** the tier levels and the Keep Road switchbacks in the sculpt; check heights against section 1.
2. **Hero blockouts:** keep, lighthouse, statue. Check the three sightlines from the berth (section 3).
3. **Streets and plazas:** canon street widths, Market Square, Festival Green, Moonmarket.
4. **Anchor buildings:** clock tower, Library, Guild, Carriage Station, Boatyard, Chapel.
5. **District houses:** box houses at 4 m storeys in each district's wall and roof pair.
6. **Climb pass:** ledges on everything over 20 m (section 5), rooftop gaps of 1.5 m or less on the
   shortcut lines.
7. **Lamps:** posts at junctions and landings.
8. **Walk test on the user's PC:** pier to Moonwell in about 40 s, pier to keep gate in about 2.5 min.

## 10. Open questions for the user

1. **Tiers and heroes:** is the four-tier climb, with the keep, lighthouse and statue as the three hero landmarks,
   the Moonharbor you have in mind?
2. **Arrival at dusk from the sea:** keep the staged reveal (section 3)?
3. **Interiors:** OK to make small interiors seamless and leave the Library, Guild and keep halls for later
   (section 7)?
4. **Dark lamps on the town edge** as first tasks?
5. **Player homes:** in town (which district?), on the edge of Wayside Fields, or not in 1.0?

## 11. Needs from other lanes

- **Environment (T55):** build to sections 1, 4 to 7 and 9. Placement is theirs, in their scripts.
- **World (T3):** the dock lamp, a lighthouse beam, the Moon Window light and junction lamps, some placed dark.
- **UI:** none yet. The design avoids map markers inside town on purpose.
