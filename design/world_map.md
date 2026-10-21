# T34: The Lyris world map, gazetteer and new islands

The game world is the real Lyris Minecraft map at full size (decision of 2026-10-20). This page is the reference for building it in Unreal: how block coordinates turn into Unreal units, where every canon place sits, which new island chains we propose, and how long it takes to sail between them.

Overview picture: `design/world_map_overview.jpg` (numbered pins match the gazetteer, lettered dashed rings are the proposed islands, the box on the main map is the inset of the bay).

**How to read the marks**
- **Canon**: the place, its name and its coordinate come from the Lyris server or atlas.
- **Placed by us**: canon names the place but never says where it is. We picked a spot that fits the lore. *Needs the user's OK.*
- **New**: not in canon at all. *New, needs the user's OK.*

---

## 1. From the Minecraft map to Unreal

| Thing | Rule |
|---|---|
| Scale | 1 block = 1 m = 100 Unreal units (uu) |
| East-west | MC **X** → UE **X** (east is +X) |
| North-south | MC **Z** → UE **Y** (south is +Y, so **north is −Y**) |
| Height | MC **Y − 63** → metres above sea level; UE **Z = (Y − 63) × 100** |
| Handedness | Minecraft is right-handed and Unreal is left-handed; swapping the Y and Z axes as above takes care of that, so nothing is mirrored |
| Origin | MC (0, 63, 0) = UE (0, 0, 0). Moonharbor is then at about UE (20 000, −230 000, 200), 2.3 km from the origin. Large World Coordinates handle the 12.5 km edge without trouble |
| World bounds | X and Z from −12 500 to +12 500: a 25 × 25 km square (625 km²), UE −1 250 000 to +1 250 000 on X and Y |
| Land | about **121.5 km²** above sea level (measured from `hmap.png`) |
| Sea level | MC Y 63 (UE Z 0). Rivers and the open sea are at sea level; inland lakes sit higher (the great lake at Y 71, so 8 m up) |
| Highest ground | Y 318 (255 m) on the northern glacier ridge at about (2110, −5360) |
| Deepest water | Y −40 (103 m deep) in the pit under Moonharbor's bay, where the star lies. Most open sea floor is Y 20 to 35 (30 to 45 m deep); the inshore straits are Y 45 to 58 (5 to 18 m deep) |

**Atlas files** (in `lyris-companion/atlas/`, to be copied into `Art/World/atlas/` by T35):

| File | Size | What it holds |
|---|---|---|
| `hmap.png` | 1000 px, 25 m per pixel | Height: MC Y = value × 1.5 − 64 |
| `bidx.png` | 1000 px | Biome index per pixel (list of 51 biome names is the `BIOMES` array in `index.html`) |
| `lakes.png` | 1000 px | Lake ids; each lake's surface Y is in `LAKE_LEVEL` in `index.html` |
| `regions.png` | 1000 px | Region ids (0 to 19, 255 = none) |
| `biomes.png`, `relief.jpg`, `painted.jpg` | 3000 px, 8.3 m per pixel | Painted and shaded maps for reference |

Pixel to block: `block = pixel × (25000 / width) − 12500`. Block to pixel: `pixel = (block + 12500) × width / 25000`.

---

## 2. The lay of the land

- **The Quiet Reach** (north): one big landmass, 66.7 km², from about X −5200 to +8600 and Z −6300 to +2100. Green heartland and river country in the middle, a snowy north coast with the glacier ridge, grey mountains in the west (summits up to Y 280 around (−2300, 0) and (−3900, −2000)), and a pale garden forest round the great lake. Moonharbor sits on a small round bay on the **north** coast, so its home waters open onto the northern sea, not onto the strait.
- **The west continent** (south-west), 25.7 km²: **Saltreach** on its western side (badlands, mesas, desert, a snowy spine up to Y 262) and **Greengrace** on its eastern side (meadow, forest, the crater lake).
- **Sunreach** (south-east), 19.0 km²: savanna and jungle plains, a dark forest in the west, a volcano-like summit (Y 200) in the south.
- **The strait** is the S-shaped channel between the Reach and the two southern lands, about 0.5 to 1.5 km wide and shallow (Y 45 to 58).

## 3. Gazetteer

Coordinates are MC block X, Z (and Y where known). Pin numbers match `world_map_overview.jpg`. "±50 m" means read off `painted.jpg` or the heightmap, not from a build file.

### Moonharbor and the bay

| # | Place | Region | X, Z (Y) | Source | Canon in one line | Needs in game |
|---|---|---|---|---|---|---|
| 1 | **Moonharbor** (town and spawn) | Quiet Reach | 200, −2300 (ground Y 65); spawn 200.5, 65, −2287.5 | atlas `index.html` PLACES; `regions/config.yml` | The last lit harbour on the coast, built over a drowned city and a sleeping star | Town blockout; the boat, dock and dock lamp move here (T37). Town core box is X 100 to 620, Z −2565 to −2120 |
| 1a | Market Square and the Moonwell | Quiet Reach | square X 140 to 246, Z −2353 to −2256; Moonwell pool 200.5, −2299.5 (water Y 65.9) | `builds/moonharbor2/plan.py`; `builds/moonwell/moonwell.py` | Town Hall, Museum, clock tower and the elvish moonlight fountain | Plaza blockout, fountain landmark |
| 1b | The Harbour (seawall, promenade, piers, Net Lane) | Quiet Reach | X 112 to 300, Z −2440 to −2353 | `moonharbor2/plan.py` | Old Harbour families say "the Stair was here first" | Quay where the player boat docks |
| 1c | Moonwell Square, Main Street and the Bright Cask | Quiet Reach | Main Street X 289 to 301, Z −2405 to −2333; Festival Green X 274 to 318, Z −2332 to −2306 | `builds/mainstreet/doc.md` | The shopping street (hatter, dressmaker, bakery, apothecary, library) with the tavern at its head | Street blockout, shop plots |
| 1d | Moonmarket and the Constabulary | Quiet Reach | X 282 to 324, Z −2300 to −2248 | `moonharbor2/plan.py` | Where the Lamp Seller sells the first lamp oil | Market landmark |
| 1e | Grand Library | Quiet Reach | X 330 to 394, Z −2372 to −2322 | `moonharbor2/plan.py` | The town's great library | Landmark building |
| 1f | Miners' Guild and its drift mouth | Quiet Reach | Guild X 390 to 420, Z −2412 to −2382; drift X 412 to 424, Z −2432 to −2412 | `moonharbor2/plan.py` | Deepkin miners; their deep chapel lies under the Guild | Building plus a mine entrance |
| 1g | Carriage Station | Quiet Reach | X 498 to 546, Z −2244 to −2196 | `moonharbor2/plan.py` | Where the roads leave town; the Wayfarers' shrine stands by it | Landmark; start of the North Road |
| 1h | Boatyard at the Point | Quiet Reach | X 148 to 182, Z −2158 to −2127 | `moonharbor2/plan.py` | The shore building at the Point | Shipwright, boat crafting |
| 1i | Districts | Quiet Reach | Heights: Z < −2318, X < 455. Rise: Z < −2250, X ≥ 455. Market: X 250 to 395, Z < −2250. Lamplight: X ≥ 395, Z < −2250. Point: X < 250, Z ≥ −2256. Plus Yards, Weavers and Wayside to the south | `moonharbor2/mplots.py` | Canon names Market, Harbour, the Point, Lamplight, the Rise and the Heights; each quarter was once a village somewhere else | Each district gets its own building style |
| 2 | **Keep Elariel** and the Moon Window | Quiet Reach | walls X 470 to 576, Z −2565 to −2527; gate 501, 138, −2526 | `moonharbor2/plan.py`; `builds/keepfront/README.md` | Seat of the Moonlit queens, high above town; Syrena keeps the moon window lit in its garden; Sir Cog kneels there | Castle blockout on the hill (gate 73 m above the sea); Keep Road from (326, −2378) climbs to the gate |
| 3 | **The Seawall Stair** (the 41 notches) | Quiet Reach | stair X 200 to 208, top step (XLI) at Z −2357; Stair Towers at 193, −2363 and 215, −2363; wall top Y 78 | `builds/seawall/gen.py` | Syrena held it alone on the first mist night and notched the top step 41 times | Landmark stair; the notched top step must never be "repaired" |
| 4 | **Syrena's statue** and the Hung Star | Quiet Reach (in the bay) | islet centre 247, 64, −2462; sword tip 245.5, 139.5, −2510.5 | `builds/syrena/export_live.py`; `builds/hungstar/build.py` | The statue on its islet, sword pointing north; the false star Syrena keeps for Corin hangs at the tip | Statue landmark on a small islet; a fixed star light at the sword tip |
| 5 | **Ilwen's Lighthouse** on the Mistwater headland | Quiet Reach | tower 127, −2343; terrace floor Y 70 | `builds/lighthouse/ilwen.py` | The only fixed light on the whole coast; every ship steers by it | Lighthouse landmark with a sweeping beam over the bay (the mist "lit water" anchor) |
| 5a | Chapel of Lamps | Quiet Reach | between the town and the lighthouse, about 160, −2350 *(placed by us, ±50 m)* | `lore.json` (no coordinate) | Home of the Lantern Covenant, with the Lamp Tree over the altar | Small chapel |
| 6 | **Oruth, the Fallen Star** (Chamber of the Hollow Star) | Quiet Reach (under the bay) | dome centre −119.5, −2611.5; chamber floor Y −39 | `builds/oruth/gen_dp.py`; atlas | The singing star, a breathing crystal heart in a glass dome on the sea bed | Underwater dome and glowing crystal at the bottom of the bay pit |
| 7 | **Aurenhal, the Brass City** | Quiet Reach (under the bay) | the whole bay bowl: X −725 to 325, Z −3100 to −2225, sea bed down to Y −40 (pin at 40, −2470) | bay outline from `hmap.png`; lore says it is built "in tiers down a sea-cliff bowl facing the bay" | The drowned Aurenn city; the Hollowdeep's levels were once its districts | Drowned terraces down the bay walls, readable from a boat on calm days. Interior is the Hollowdeep (later) |
| 8 | **Lantern Pier** and the Tide Mother shrine | Quiet Reach | pier end about 136, 66.6, −2418 | `builds/hungstar/build.py` | Driftwood shrine under whale-rib arches at the end of the pier | Pier and shrine; Keeper Edric's training dig trench is under it |
| - | Old Gnash's waters | Quiet Reach | the bay (no fixed spot) | `bestiary.json` | A sea turtle the size of a chapel who guards the bay | A wandering bay creature, never owned |

### The North Road, the Observatory and the Hollowdeep

| # | Place | Region | X, Z (Y) | Source | Canon in one line | Needs in game |
|---|---|---|---|---|---|---|
| 9 | **The Grand Observatory** (and the academy) | Quiet Reach | 1326, 264, −2980; refractor trunnion 1326.5, 284, −2968.5 | `builds/observatory/README.md` | Elven oracle-temple on an Aurenn star platform, half ruined, where the Unbottled Night began | The academy hub: big landmark on a summit 201 m above the sea, in sight of the bay. Temple of the Sleeping Moon and Hoarfeather's perch nearby |
| 10 | **The North Road** (lantern V) | Quiet Reach | lantern V at 980, −2905; the road runs from the Carriage Station north past the Observatory spur to the Gate | atlas note in `index.html` | Tobin Marsh vanished on it; pilgrims light its cairns | A lamp-lined road, about 2.5 km, with cairns and road lanterns |
| 11 | **The Delvers' Gate** | Quiet Reach | 1650, −3950 (about Y 136); the Great Door at 1820, 155, −3955 | atlas PLACES and note | A cleft to a sunken court and a round brass door: THE STAR SLEEPS UNDER THE WATER | Dungeon entrance: cleft, court, Remnant's rubble wall, the Lodge with the Delvers' Roll |
| 11a | **The Hollowdeep** | Quiet Reach (below) | under the Gate, running down toward the bay | `lore.json` | Six strata: Drowned Halls, Clockwork Vaults, Rootworks, Ember Forges, Mistlands Below, the Starwound | Dungeon (later lane); not part of the overworld terrain |

### Elsewhere in the Quiet Reach

| # | Place | Region | X, Z (Y) | Source | Canon in one line | Needs in game |
|---|---|---|---|---|---|---|
| 12 | **The Teeth** | Quiet Reach | reef at about 150, −3550 *(placed by us)* | `lore.json` names it, gives no spot | A reef off the bay; Syrena swims there at dawn and once lured a corsair fleet onto it | Rocks breaking the surface in the channel north of the bay mouth (sea Y 56 there). Fits the keeper's log of a ship going "north along the reef" |
| 13 | **The great lake** | Quiet Reach | centre −1800, −1480; 1.5 km², from Z −3540 to +60; surface Y 71 | `lakes.png` lake 1, `LAKE_LEVEL` | Canon calls it "a great round lake" | Lake surface at Y 71. ⚠ On the real map it is long and narrow (about 3.5 km north to south), not round |
| 14 | **Hollowmere** and the Herring Road | Quiet Reach | Hollowmere at about −675, −950 on the main river *(placed by us)*; the road runs from the coves near town south-west along the river | `lore.json` (no coordinate) | A droving village burned on the third mist night; "no Hollowmere either" by dawn | Burnt village ruin with a bridge (the herring-a-barrel toll), singing-stone waymarks along the road, the Lamp and Ladle inn and Hale's mill at a crossing |
| 15 | **The Under-Halls** | Quiet Reach | grey mountains, about −3150, −950 (Y 200) *(placed by us)* | `lore.json` (no coordinate) | The Deepkin mine-holds that shut at dusk and never lost a soul | A carved mountain gate; the Deepkin send ore down to the coast twice a year |
| 16 | **Waystone rings** (five proposed sites) | Quiet Reach | 725, −2650 (Y 128); 1400, −3650 (Y 134); 5725, −2200 (Y 119); 7225, −1275 (Y 128); −100, −4675 (Y 138) *(placed by us)* | sites picked from `hmap.png` + `bidx.png`: flat upland, Y 110 to 190 | Tuned Aurenn stones that carried the song inland; THE STAR SLEEPS UNDER THE WATER cut on each centre stone | Stone ring landmarks; nearby, Order survey camps and black-glass craters with violet crystal |
| 22 | The glacier ridge (highest point) | Quiet Reach | 2112, −5363 (Y 318) | `hmap.png` | "A snowy north coast and a glacier ridge" | Snow peak, visible from the bay |
| 23 | The walled town that "still answers with bells" | Quiet Reach | north coast at about −400, −5700 (Y 107) *(placed by us, rumour only)* | `lore.json` tavern rumour | A walled town far north that still rings its bells | Keep as a sound and a far silhouette at first; may move to the Rime Skerries (F) instead |
| - | Old Coast Road and the Mistwater Bridge | Quiet Reach | leaves the lighthouse headland westward *(no coordinate)* | `lore.json` | The Wayfarers keep a fallen lamp post lit on it | Road west from the lighthouse |
| - | The Pale Stag statue, Old Hunt antler shrine, Veiled shrine | Quiet Reach | no coordinates in canon | `lore.json` | Wilds shrines | Place later with the faiths |

### The southern lands

| # | Place | Region | X, Z (Y) | Source | Canon in one line | Needs in game |
|---|---|---|---|---|---|---|
| 17 | **Saltreach landing** | Saltreach | −2660, 2280 (the server searches outward for dry ground) | `regions/config.yml` | "A wild landing: no town yet" | A beach landing spot; no capital in canon yet |
| 18 | **Sunreach landing** | Sunreach | 2660, 2150 | `regions/config.yml` | "A wild landing: no town yet" | A beach landing spot; no capital in canon yet |
| 19 | **Greengrace crater lake** | Saltreach (Greengrace side) | rim centre about −1217, 3227, outer radius about 545 m; surface about 0.44 km² | `builds/grove/README.md`; `lakes.png` lake 2 | A great ringed crater lake inside forest | Crater rim landmark; lush forest within 1.4 km of (−1650, 3330), thinning outward |
| 20 | Sunreach's volcano crater | Sunreach | summit 4162, 5062 (Y 200), ±50 m | `hmap.png`; `lore.json` "a volcano crater in the south" | A sleeping volcano | Probably the bestiary's "East Volcano": black sand and warm reefs on its coast |
| 21 | Saltreach's snowy spine | Saltreach | high point −5638, 3987 (Y 262) | `hmap.png` | "Orange badlands and mesas with a snowy spine" | Mountain landmark |

### Natural wonders (T49)

From the user's labelled map (`design/reference/lyris_map_wonders.jpg`), measured to ±10 m on its 1000-block grid. Full
designs, sculpt details and open questions: `design/natural_wonders.md`; data: `Art/World/wonders.json`.

| # | Wonder | Region | X, Z | In one line |
|---|---|---|---|---|
| W1 | The Rimeglass Caves | Quiet Reach | −2500, −6100 | Ice cliffs at the peninsula's west tip, four sea-cave clefts, two stacks of a fallen arch *(arch new)* |
| W2 | The Sisterfjord | Quiet Reach | −1650, −5850 | Two deep fjord arms with sheer walls; two stacks, the Sisters, stand in the east arm *(Sisters new)* |
| W3 | The Frozen Cascade | Quiet Reach | 2100, −5375 | A six-tier frozen fall from the highest summit down to the north sea |
| W4 | Skyshoals | Quiet Reach | 4400, −4300 | A stone forest: 46 pillars, 40 to 110 m tall, trees on their tops |
| W5 | The Ladder Lakes | Quiet Reach | −3600, −3200 | Seven turquoise lakes stepping down a forest valley behind travertine dams |
| W6 | The Mistwall Cliffs | Quiet Reach | −5100, −2600 | A 1.5 km, 80 to 110 m sea-cliff wall and 16 sea stacks |
| W7 | Veil Falls | Quiet Reach | −4550, −1600 | A 120 m wide curtain fall off the west-coast cliff into a round cove |
| W8 | The Glowmere Grotto | Quiet Reach | 3200, −2600 (pit 3075, −2560) | A cenote by the river, a ledge path down to a glowing pool |
| W9 | Elderheart | Quiet Reach | 5200, −2900 | A broad knoll crowned by a giant tree, its roots as ridges in the grass |
| W10 | The Steaming Fields | Quiet Reach | 3600, −800 | Travertine terraces of milky hot pools stepping down to the strait |
| W11 | The High Table | Quiet Reach | 6400, −1300 | A 1.2 x 0.7 km mesa, 60 to 70 m sheer, a stream falling off its east end |
| W12 | The Long Door | Quiet Reach | 8600, 400 | A rock fin off the east cape with a sea door through it (lintel is a mesh) |
| W13 | The Lantern Isles | East strait | 5700, 1500 | 87 dark islets, one lantern each; one ring isle with a pool |
| W14 | The Glass Dunes | Saltreach | −4100, 1900 | Pale salt-glass crescent dunes with mirror pans between |
| W15 | The Hexstone Causeway | Saltreach | −8700, 2300 | Basalt columns stepping from the west cape to the Western Spruces (O9) |
| W16 | The Starglass Spires | Greengrace | −700, 3200 | Thirty needle spires on the crater's east rim, threaded with ringing star-glass |
| W17 | The Skyfall Scar | Saltreach | −5600, 3800 | Five black-glass craters down the spine; the last breaks open the West Volcano *(breach new)* |
| W18 | The Thunder Curtain | Sunreach | 2150, 4200 | Pale karst plateau of the west lobe; its east escarpment roars in the rains |
| W19 | Leviathan's Rest | Sunreach | 1100, 4800 | Vertebrae, ribs and a skull of a hill-sized sea-beast in the mangroves *(bones new)* |
| W20 | The Sunstair Terraces | Sunreach | 3300, 4300 | Contour terraces up the volcano ridge with one straight stair |
| W21 | The Blue Eye | Sunreach (sea) | 6900, 4600 | A −62 m sea hole in a lagoon inside a ring of sand shallows |
| W22 | Glowcap Hollow | Far south-west (O8) | −10750, 5800 | The mushroom isle as a bowl of hills round a glowing hollow |
| W23 | The Bellstack | Quiet Reach (sea) | −1200, −6650 | *New, needs the user's OK*: a lone stack that booms like a bell (the map's unlabelled ✦) |

### Rivers

| River | Course | Length | Notes |
|---|---|---|---|
| Moonharbor's river | Rises near (1525, −600), runs past (975, −1000), (−150, −1125) and (−675, −950), turns north past (−1375, −1225) to the great lake at (−1875, −2075); a branch reaches the town edge at about (300, −2000) | about 9 km of river biome | The Herring Road follows it (placed by us) |
| Northern river | From the glacier foothills at (4700, −4600) south-west to (2875, −3000) | about 6 km | Joins the river country east of the Observatory |
| Greengrace river | Around (−3675, 3150) to (−2850, 2900), near the Saltreach and Greengrace seam | about 2.6 km | |
| Sunreach east river | (6625, 125) to (6075, 1000) | about 1 km | |

The painted map shows more streams than the river biome does; T35 should trace rivers from the heightmap as well, not only from `bidx.png`.

### Islands already on the map

Their names are working names *(new, need the user's OK)*. "Region" is the one the server's border map gives them.

| Pin | Working name | Centre X, Z | Size | Highest | Biome | Region |
|---|---|---|---|---|---|---|
| O1 | Westwatch | −9360, −2546 | 2.1 km² (biggest outer island) | Y 144 | windswept hills, old spruce, a small lake | Saltreach |
| O2 | The Birchholms (two) | −6316, −1058 and −6616, −1908 | 1.2 + 0.3 km² | Y 90 | birch and flower forest | Saltreach / Quiet Reach |
| O3 | Snowcap and its islet | −4666, −5410 and −3837, −6183 | 1.0 + 0.1 km² | Y 86 | snowy taiga | Quiet Reach |
| O4 | The Flowerholms (three) | 10522, −4479; 9576, −5552; 9628, −4793 | 0.9 + 0.2 + 0.1 km² | Y 83 | flower and old birch forest | Quiet Reach |
| O5 | The East Pair | 11089, −2920 and 10060, −2699 | 0.4 + 0.2 km² | Y 77 | plains, flower forest | Quiet Reach |
| O6 | Blossom Isle | 9429, 3610 | 1.8 km² | Y 126 | meadow and cherry grove, a small lake | Quiet Reach (by distance, though it lies off Sunreach) |
| O7 | The Bamboo Isles (three) | 7882, 5681; 9352, 5256; 9013, 6114 | 0.6 + 0.1 + 0.1 km² | Y 118 | bamboo jungle | Sunreach |
| O8 | Mushroom Isle (Glowcap Hollow, W22) | −10717, 5862 | 0.6 km² | Y 82 | mushroom fields | Saltreach |
| O9 | The Western Spruces (Hexstone Causeway, W15) | −8616, 1895 and −9145, 2073 | 0.3 + 0.1 km² | Y 82 | old spruce taiga | Saltreach |

---

## 4. New island chains (proposal)

**Every island in this section is *new, needs the user's OK*.** The user approved "real map, plus islands"; these are suggestions for where and why. All of them keep at least 290 m of open water from any existing coast (checked against `hmap.png`), and none touches a canon place. Sizes are rough totals of land.

They follow the three intensity zones: **home waters** (Moonharbor's bay and inside the lighthouse's reach), **middle seas** (the straits and the waters round the continents) and **far deep** (open ocean beyond the outer islands, where the charts stop and the Forgetting Sea is strongest).

| Mark | Name | Centre X, Z | Spread and size | Sea floor | Zone | Mood and biome | Purpose |
|---|---|---|---|---|---|---|---|
| **A** | **The Lampwick Skerries** | −2400, −4450 | six islets in a line, 60 to 120 m across each, about 0.15 km², in the sheltered gulf west of the bay mouth | Y 47 to 54 (shallow) | Home waters | Grey rock, sea pinks, herring coves, one dark lamp post on each islet | The first sail and the first lamps a new player relights. Each lit islet visibly brightens the gulf: the Forgetting Sea in miniature, safe and close (4 km, 7 min) |
| **B** | **The Hushed Isles** | −7700, −4800 | five isles, 120 to 350 m, about 1.0 km², north-west of Westwatch | Y 30 to 42 | Middle seas | Fog-bound spruce, silent bell towers, shingle beaches with no footprints | The first islands that *fade*: with no lamp kept, their edges blur and paths vanish from the chart; relighting brings them back for everyone. Straddles the Reach and Saltreach border, so check the mist rule (see notes) |
| **C** | **The Wickstones** | 7850, 1850 | four isles, 120 to 250 m, about 0.5 km², in the eastern mouth of the strait | Y 41 to 47 | Middle seas | Warm meadow, standing stones, a waystone ring that rings in the wind | Waystone isle: a ring that answers the rings on the Reach uplands. Also the halfway stop between the Reach and Sunreach for trade |
| **D** | **The Tallow Banks** | 10300, −850 | four low isles, 150 to 300 m, about 0.7 km², east of the Reach | Y 29 to 42 | Middle seas | Low dunes, drying racks, rendering sheds, glowing water at night | Lanterneel grounds (canon: Moonharbor buys lanterneel oil). The lamp oil economy and night fishing |
| **E** | **The Southing Stones** | 270, 6850 | three sea stacks and isles, 150 to 250 m, about 0.4 km², south of the gap between Greengrace and Sunreach | Y 36 to 39 | Middle seas, edge of the far deep | Tall sea stacks, seabirds, a cairn of navigators' stones | The last landfall before the southern deep. A cairn note hints that the *Saltwren* passed this way (Corin's ship; the hint itself is new) |
| **F** | **The Rime Skerries** | 200, −10000 | four isles, 250 to 500 m, about 1.9 km², 3 km north of the Reach's ice coast | Y 21 to 23 | Far deep (north) | Ice, bergs, frozen wrecks, bells heard in fog | Polar waters for the Bergmaw (canon creature, "polar and cold seas"). A possible home for the town that answers with bells |
| **G** | **The Unremembered Isles** | 800, 10500 | three large isles, 450 to 700 m, about 3.0 km², 4 km south of the southern coasts | Y 18 to 21 | Far deep (south) | Pale, colour-drained, half-drawn: trees like sketches, ruins with no names | The heart of the Forgetting Sea. They begin almost blank and gain detail as the server reaches shared milestones (lamps lit, stars charted, stories learned). Toward the starless Hollow in the southern sky that Corin sailed to chart |
| **H** | **Ember Isle** (the West Volcano) | −7800, 8900 | one volcanic island about 800 m across plus an islet, about 2.1 km², south-west of Saltreach | Y 23 | Far deep (south-west) | Black sand, warm reefs, ash cliffs, a smoking cone | A home for canon creatures that have none on the map: the Cinderhorn ("cliffs and peaks of the West Volcano") and the Carapotl ("warm reefs of the West and East Volcanoes") |

---

## 5. Sailing distances

At prototype boat speed, **1 km takes about 100 seconds**. Distances follow open water around the coasts (shortest water path on the 25 m heightmap grid), not straight lines, so they are what a player actually sails.

From **Moonharbor's quay** (150, −2440):

| To | Distance | Time |
|---|---|---|
| Oruth's dome (over the bay pit) | 0.3 km | 30 s |
| The Teeth | 1.2 km | 2 min |
| A Lampwick Skerries | 4.1 km | 7 min |
| O3 Snowcap | 7.3 km | 12 min |
| B Hushed Isles | 9.2 km | 15 min |
| F Rime Skerries | 10.3 km | 17 min |
| O1 Westwatch | 12.9 km | 21 min |
| Saltreach landing | 13.6 km | 23 min |
| Sunreach landing | 18.3 km | 30 min |
| O4 Flowerholms | 19.5 km | 33 min |
| O8 Mushroom Isle | 19.7 km | 33 min |
| Greengrace south coast | 20.0 km | 33 min |
| D Tallow Banks | 20.7 km | 35 min |
| E Southing Stones | 20.8 km | 35 min |
| H Ember Isle | 21.1 km | 35 min |
| C Wickstones | 23.2 km | 39 min |
| O6 Blossom Isle | 24.9 km | 42 min |
| G Unremembered Isles | 25.0 km | 42 min |

Between the southern landings:

| From → To | Distance | Time |
|---|---|---|
| Saltreach landing → Sunreach landing | 5.2 km | 9 min |
| Saltreach landing → E Southing Stones | 7.7 km | 13 min |
| Saltreach landing → G Unremembered Isles | 11.9 km | 20 min |
| Saltreach landing → H Ember Isle | 14.5 km | 24 min |
| Sunreach landing → C Wickstones | 7.2 km | 12 min |
| Sunreach landing → E Southing Stones | 6.5 km | 11 min |
| Sunreach landing → O6 Blossom Isle | 10.3 km | 17 min |
| Sunreach landing → D Tallow Banks | 10.5 km | 18 min |

**What the numbers say.** Moonharbor's bay opens north, so the strait and the southern regions are a long sail round the west of the Reach (Saltreach is only 5.5 km away in a straight line but 13.6 km by sea). The home waters are the northern gulf and coast. A full lap of the known world is well over an hour at prototype speed, so the design will want faster boats later, lit harbours to hop between, or both.

---

## 6. Canon conflicts and open questions

1. **The "great round lake"** in `lore.json` is long and narrow on the real map (1.5 km², about 3.5 km north to south). Either the lore line changes to "a great long lake", or the round bay is what was meant.
2. **Moonharbor faces north, not the strait.** Canon says the Reach "runs from the strait up to the northern ice" and the T9 Inner Sea option put Moonharbor on the strait; the newer decision (real map) puts it on the north coast. Lines like "Corin sailed south" still work, but it is a long way round.
3. **The West Volcano has no place on the map.** Two canon creatures live there. Proposal H gives it one; otherwise Saltreach's snowy spine would need to become volcanic.
4. **The mist and the sea.** The server keeps the mist to the Quiet Reach and its seas (`night/reach_only/`), and Saltreach and Sunreach have never seen it. Proposals B (on the border), E, G and H lie outside Reach waters. The Forgetting Sea works through unkept light rather than mist, so this can hold, but the user should decide whether the far deep has mist.
5. **No capitals yet** for Saltreach or Sunreach: canon has "wild landings" only.
6. **Places with no coordinate in canon**: the Teeth, Hollowmere, the Herring Road, the Under-Halls, waystone rings, the Chapel of Lamps, the Old Coast Road, the walled town of bells, the Temple of the Sleeping Moon, the Old Hunt and Veiled shrines. Spots above marked *placed by us* need the user's OK.
7. **The Old Shore** stays unplaced: canon never says which way it lies.
8. Server housekeeping (not lore, for the user's information): `dig/config.yml` still has Moonharbor's no-dig zone at (−100, −400), which was the old town site; the town is now at (200, −2300).

## 7. For T35 and T36 (Environment)

- Build terrain from `hmap.png` at 25 m per pixel, then add Genshin-style detail; the 3000 px painted map gives 8.3 m per pixel for coastline shapes.
- Keep the bay pit to Y −40 (103 m deep) at (−120, −2612): the star's chamber sits at its floor.
- Start blockouts in this order: Moonharbor core with the quay, seawall stair, lighthouse, statue islet and keep; then the Observatory and North Road; then the Delvers' Gate.
- Proposed islands (A to H) wait for the user's OK before T36 builds them.
