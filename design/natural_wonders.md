# T49: The natural wonders of Lyris

The user's labelled map (`design/reference/lyris_map_wonders.jpg`) marks 22 natural wonders with a ✦, plus one
unlabelled ✦ hidden under the title cartouche. This page fixes where each one is, what it is in the game, and how the
terrain bake sculpts it. The machine-readable version is `Art/World/wonders.json`; the sculpting is the WONDERS stage
of `Art/World/bake_terrain.py`. A shaded close-up of every wonder is on `design/natural_wonders_sheet.jpg`.

**How to read the marks** (as in `design/world_map.md`)
- **Map**: the name and the spot come from the user's map. The *design* (what it looks like, how it plays) is ours,
  done with the creative liberty the user asked for.
- **Lore**: also tied to a line of canon in `lore.json`.
- ***New, needs the user's OK***: an invention beyond the map (a new name, a new story hook, a change to a canon place).

## 1. How the spots were measured

The map's edges carry the 1000-block grid. I found every grid line in the sea by its faint darker colour (24 vertical,
16 horizontal lines) and fitted a straight line to each axis:

    px = 2626.43 + 0.195146 * X        py = 2038.37 + 0.195357 * Z        (5252 x 3925 px PNG)

The largest residual is 1.2 px on X and 4 px on Z (where labels sit on the grid line), so about 5 m per pixel. Checks:
the atlas coastline drawn through this fit lies exactly on the map's coastline round Moonharbor's bay, the Greengrace
crater and Sunreach's volcano; Oruth's star icon lands 40 m from Oruth's dome (the icon's centre is not its point).

Every ✦ is drawn in one flat colour (RGB 160, 110, 40), so I found all of them by colour and took each icon's centre
(about 17 px across). The centres come out within 5 to 10 blocks of round numbers (2095, -5373; 4397, -4304 ...), so
the map's author placed them on a 50-block grid; the table gives those rounded values. **Error: ±10 m for the
marker itself**; where a wonder is a drawn shape (the High Table's oval, the Ladder Lakes, the Lantern Isles, the
Skyfall pits, the Blue Eye's rings, the dune field) the shape was traced from the map colours, ±10 to 25 m.

## 2. The wonders

| # | Wonder | Region | MC X, Z | Kind | Marks |
|---|---|---|---|---|---|
| 1 | The Rimeglass Caves | Quiet Reach, Sisterfjord peninsula (west tip) | −2500, −6100 | ice cliffs, cave clefts, ice stacks | map; the fallen arch is *new* |
| 2 | The Sisterfjord | Quiet Reach, north peninsula | −1650, −5850 | deep fjord arms, sheer walls, two stacks | map; the two Sisters are *new* |
| 3 | The Frozen Cascade | Quiet Reach, glacier ridge (highest summit) | 2100, −5375 | six-tier icefall to the sea | map |
| 4 | Skyshoals | Quiet Reach, north-east taiga | 4400, −4300 | stone forest of 46 pillars | map |
| 5 | The Ladder Lakes | Quiet Reach, western dark forest | −3600, −3200 | seven stepped lakes with travertine dams | map |
| 6 | The Mistwall Cliffs | Quiet Reach, west coast | −5100, −2600 | 1.5 km sea-cliff wall and 16 stacks | map |
| 7 | Veil Falls | Quiet Reach, west coast | −4550, −1600 | plateau lip, curtain fall into a sea cove | map |
| 8 | The Glowmere Grotto | Quiet Reach, river country | 3200, −2600 (pit at 3075, −2560) | cenote with a ledge path | map |
| 9 | Elderheart | Quiet Reach, eastern plains | 5200, −2900 | broad knoll for a giant tree, root ridges | map |
| 10 | The Steaming Fields | Quiet Reach, south coast | 3600, −800 | travertine terraces and hot pools | map |
| 11 | The High Table | Quiet Reach, eastern uplands | 6400, −1300 (oval centre 6434, −1333) | flat-topped mesa, stream and falls | map |
| 12 | The Long Door | Quiet Reach, east cape | 8600, 400 | rock fin with a sea door (arch) | map |
| 13 | The Lantern Isles | east strait | 5700, 1500 (field 4170..6660, 420..2410) | 87 rocky islets, one ring isle | map |
| 14 | The Glass Dunes | Saltreach, north-east coast | −4100, 1900 | crescent salt dunes with glassy pans | map |
| 15 | The Hexstone Causeway | Saltreach, west cape and the Western Spruces | −8700, 2300 | basalt columns across the shallows | map |
| 16 | The Starglass Spires | Greengrace, crater lake's east rim | −700, 3200 | 30 needle spires | map, lore (star glass) |
| 17 | The Skyfall Scar | Saltreach, the spine | −5600, 3800 (pits from −6850, 2440 to −5070, 4710) | chain of five black-glass craters | map, lore; the breach of the West Volcano is *new* |
| 18 | The Thunder Curtain | Sunreach, western lobe | 2150, 4200 | pale karst plateau, escarpment fall | map |
| 19 | Leviathan's Rest | Sunreach, mangrove coast | 1100, 4800 | ridge of vertebrae, ribs and a skull | map; the bones are *new* |
| 20 | The Sunstair Terraces | Sunreach, the volcano ridge's north-west flank | 3300, 4300 | contour terraces with a stair | map |
| 21 | The Blue Eye | Sunreach, east sea | 6900, 4600 | sea hole in a sandy atoll ring | map |
| 22 | Glowcap Hollow | far south-west isle (the mushroom isle, O8) | −10750, 5800 | bowl island | map |
| 23 | The Bellstack | Quiet Reach, north sea | −1200, −6650 | lone sea stack split by a cleft | *new, needs the user's OK* (the ✦ is on the map, its label is hidden under the title) |

## 3. Designs and how each is sculpted

Heights are metres above sea level (MC Y − 63). "Climbable" follows the Breath rules (`design/movement_stamina.md`):
anything can be climbed, but sheer faces over about 40 m cost a full Breath ring and need a ledge or a rest.

### 1. The Rimeglass Caves (−2500, −6100)
The peninsula's west tip ends in a wall of blue-white ice over black rock, and the sea has cut caves into it. From a
boat you see four dark clefts in the ice, each a cave mouth you can row into at low swell; inside, the caves glow a cold
blue (the "rimeglass"). Two ice-capped stacks stand offshore as the feet of an arch that fell long ago, so the gap
between them reads as a doorway *(new)*. Think Dragonspine's frozen cliffs meeting Inazuma's sea caves.
**Sculpt:** within 620 m of the marker the coastal band (150 m) is lifted into cliffs of 48 to 64 m that rise within
6 m of the waterline; ridged noise roughens the top; 14 ice spikes (5 to 10 m wide, 10 to 24 m tall) stand on the
clifftop. Four clefts, 16 to 22 m wide and 70 to 110 m long, are cut down to the sea where the seeds snap onto the coast
(the sea fills them). The sea at the foot drops to −14 m. Four ice stacks (13 to 22 m wide, 30 to 50 m tall) stand
offshore. Not climbable from the water except up the clefts; the cave interiors are meshes (see "needs").

### 2. The Sisterfjord (−1650, −5850)
Two narrow arms of the sea bite north into the peninsula's head from its southern bay, one on each side of a white
massif: the Sisters. Their walls stand sheer and the water between them is black-blue and deep. Two tall rock stacks
stand in the eastern arm like two women looking out to sea *(the two Sisters are new)*. A Sea of Remnants / Norwegian
fjord feeling: the boat feels small.
**Sculpt:** within 950 m of (−1950, −5500), south of Z −6150: land within 110 m of the water rises to walls of 75 to
115 m (sheer in the first 8 m), blending back into the massif over 290 m. The water in the arms deepens fast to −52 m.
The two Sisters are pillars 24 and 20 m wide, 74 and 64 m tall, standing on the −8 m floor at (−1530, −5600) and
(−1462, −5655), snow-capped.

### 3. The Frozen Cascade (2100, −5375)
From the highest summit in Lyris (Y 318) a frozen waterfall steps down the glacier's north face to the sea in six
falls, each a curtain of blue ice over a ledge of snow. In summer it creaks and drips; in winter it is silent. At the
top a cirque gathers the snow. The whole thing is visible from the north sea as a white staircase.
**Sculpt:** a channel about 120 m wide at the head, narrowing to 65 m at the sea, runs 310 m from (2120, −5330) to the
coast at (2130, −5640). Its floor drops from about 245 m to 2 m in six tiers: flat, slightly dished treads with ragged
lips and near-vertical risers of about 40 m. Serac-roughened ice walls frame it. A cirque bowl (120 m, 16 m deep) sits
at the head. The coordinates are domain-warped so the lips and edges wander. Painted snow; risers turn rock by slope
(the frozen falls themselves are meshes). Each tread is a resting ledge between climbs.

### 4. Skyshoals (4400, −4300)
A stone forest: forty-six pillars of grey rock, 40 to 110 m tall and only 20 to 60 m across, rising out of the taiga on
the west bank of the inlet, each with trees on its flat top. The name is the sailors': from the sea at dusk the pillar
tops look like shoals in the sky. This is Liyue's Jueyun Karst and Zhangjiajie, set in a northern pine wood: the
place to glide from pillar to pillar.
**Sculpt:** 46 pillars scattered (seeded, blue-noise) within 560 m of (4230, −4280), only on dry ground at least 45 m
from the coast, 140 m from any river and 45 m from any lake. Radius 11 to 30 m, height 38 to 112 m above their base
(taller toward the middle), sheer sides, a 2 m soft cap for trees, a scree skirt. Tops painted Forest.

### 5. The Ladder Lakes (−3600, −3200)
Seven turquoise lakes step down a forest valley one after another, each held back by a pale travertine dam, and the
water spills from one to the next in little falls: Plitvice in the Reach's dark forest. A path can run along the dams.
**Sculpt:** the seven lakes are the seven turquoise shapes traced from the map (ellipses up to 145 x 55 m, rotated as
drawn) on a 900 m chain from (−3954, −3605) north-west to (−3340, −2867) south-east. Water levels step down 3.2 m a
lake, 49 m to 29.8 m. Along the chain a 190 m valley floor is flattened to each lake's level + 1.3 m, stepped at a dam
halfway between lakes near the axis and smooth away from it, blending into the forest over 260 m. Each lake bowl is 5
m deep. Dams are painted pale (Salt). Atlas lakes inside the valley are switched off. The seven lakes go into the
terrain manifest as water bodies.

### 6. The Mistwall Cliffs (−5100, −2600)
A sheer wall of grey-green rock runs 1.5 km along the west coast, 80 to 110 m high, with gullies notched into its top
and sixteen sea stacks standing off it in the surf: the stacks drawn on the map. Sea mist pours over the top on cold
mornings (the mist is the sky lane's). The Reach's western edge, the place you see the sun set into the sea.
**Sculpt:** along the line X −4980, Z −3450..−1980 (420 m reach), the coastal band (230 m) is raised to 79 to 116 m,
rising within 7 m of the waterline, with a gully notch every ~170 m. The sea at the foot drops to −16 m. The 16 stacks
are the dots traced from the map (×1.15 radius), 34 to 72 m tall, grass on top. Climbable only up the gullies.

### 7. Veil Falls (−4550, −1600)
A stream crosses the plateau and pours off the cliff lip in a broad, thin curtain, 120 m wide, into a round sea cove
below: Fontaine's falls as the Reach's west coast. You can walk behind the veil on the cove's ledge (a mesh later).
**Sculpt:** the coastal cliff around (−4520, −1610) is lifted to 74 m. A half bowl 93 m across is bitten out of the
cliff below the lip, down to −6 to −14 m (sea; on purpose). The stream channel runs 380 m inland, meandering, 18 m wide,
widening to 120 m and shallowing at the lip. Plunge pool −18 m. The fall itself is water (the manifest lists it).

### 8. The Glowmere Grotto (3200, −2600)
A round sinkhole in the river meadows, 160 m across and about 25 m deep, with a ring of moss and a glowing pool at the
bottom: glowmere. A ledge path spirals down the south-east wall. Inazuma's Byakuyakoku feeling, small and secret.
**Sculpt:** centred on the west bank at (3075, −2560), 150 m from the marker, so it does not swallow the river (the
marker sits on the river). Radius 80 m, wobbled outline; a raised lip of 3.5 m; walls fall to a cenote pool at sea
level (0.6 m; groundwater) 52 m across and 7 m deep, with a narrow shore. The ledge path descends from the rim at 20°
round to 230°. The "overhang" look is the raised lip; real overhangs and the glow are meshes.

### 9. Elderheart (5200, −2900)
A huge low knoll in the eastern plains, crowned by a single giant tree whose roots you can see in the ground as long
low ridges running out across the grass. Genshin's Irminsul / Sumeru's great trees, as a landmark you see from
anywhere in the east.
**Sculpt:** a dome 620 m in radius rising 34 m (slopes under 12%, walkable everywhere), a flat crown 75 m across for the
tree (no forest painted there), and seven wandering root ridges, about 5 m high and 30 to 60 m wide, out to a third of
the radius. Forest paint rings the knoll's middle slopes. The tree is a mesh.

### 10. The Steaming Fields (3600, −800)
A mound of cream-white travertine terraces, each terrace a shallow rim pool of milky blue water, steps down from a
central hot spring to the strait, with four more springs on its slopes and a rust-orange crust on the rims (the orange
ring on the map). Pamukkale, in Natlan's colours. Steam hangs over it on cold days.
**Sculpt:** a 300 m mound rising 16 m above the ground in seven terraces. The rims are contours of a lumpy,
domain-warped mound, so they wander and pinch; each rim has a 0.55 m raised lip and each tread is dished. A central
pool 124 m across, four outer pools 60 m across at the four spots traced from the map. Painted Salt (cream) with
Badlands on the rims and the outer ring. Pools go into the manifest as water. Where the mound meets the sea inlet it
steps straight down to the water.

### 11. The High Table (6400, −1300)
A great flat-topped mesa, 1.2 km by 0.7 km, standing 60 to 70 m sheer above a ring of dark forest. A stream crosses its
grassy top and falls off the east end into a pool. Nobody has found a path up; the climb is the quest (Breath!). The
grey oval on the map.
**Sculpt:** the oval traced from the map: centre (6434, −1333), semi-axes 600 x 360 m, rotated 19°, its outline
wobbled with lobes and small bays. Top at 108 m ±2, tilting 7 m down toward the east end; the sides are vertical within
2.5% of the radius; a scree skirt (32% of the height) falls over 70 m. The stream is a meandering 18 m channel, 2.6 m
deep, from (6080, −1420) to the east lip; the plunge pool (62 m) is at (7065, −1061). Atlas lakes under the Table are
switched off. Forest paint in a 420 m ring.

### 12. The Long Door (8600, 400)
A fin of rock runs out to sea from the east cape, 50 m high, and the sea has cut a door clean through it: a tall gate
the boat can sail through. Inazuma's sea arches at the eastern edge of the world.
**Sculpt:** a fin 255 m long from (8575, 325) to (8830, 430), 70 m wide tapering to 49 m, 52 m tall falling to 34 m at
its end. A 43 m door is cut through from 55% to 72% of its length down to −6 m. A heightmap cannot make the lintel, so
the span over the door is a rock mesh (manifest: `wonders[].needs.arch_lintel`).

### 13. The Lantern Isles (5700, 1500)
Eighty-seven dark little islets scattered across the eastern strait in two drifts, each with room for one lantern:
lit, they make a field of lights on the water; dark, they are a maze of rocks. One isle is a ring around a sheltered
pool. The lights are the lamp-relighting loop of the Forgetting Sea (see `world_map.md`).
**Sculpt:** every islet is one traced from the map: 87 positions and sizes. Radius ×0.9 (8 to 70 m), heights 4 to 26
m (+8 m for the largest), rough ridged tops, a steep shelf. The ring isle (4888, 899) is 52 m across with a pool
inside and a 24° gap to the south. Painted dark rock (Rock + Volcanic), no forest.

### 14. The Glass Dunes (−4100, 1900)
Pale blue-white dunes of salt and glass sand, in long crescents, with flat glassy pans between them that hold a skin of
water after rain and mirror the sky (the blue stripes on the map). Sumeru's desert, gone cold and bright.
**Sculpt:** an ellipse 1.5 x 0.86 km rotated 32° (traced from the map), on top of the salt flats. Crests run 8° east
of north, about 95 m apart, sinuous and bowed into crescents, up to 11 m tall: a gentle stoss slope up from the west
and a steep slip face to the east, then a flat pan at 2.2 m. Painted Salt everywhere, a little Sand on the crests.
The beach shelf softens them near the coast.

### 15. The Hexstone Causeway (−8700, 2300)
Thousands of black hexagonal basalt columns step out from Saltreach's west cape across the shallows to the three
spruce islets: the Giant's Causeway, walkable at low tide in places and a hop-and-glide in others.
**Sculpt:** three paths (cape → small islet → each big islet) 66 m wide with ragged edges. Hex cells 9 m across, each
column a random height from 0.6 to 5.5 m (taller near the shores), stepped in 0.6 m, with cracks between. Columns break
into groups (stepping stones with water between). The sea within 140 m is raised to −1.6 m shallows. Painted Volcanic.

### 16. The Starglass Spires (−700, 3200)
A cluster of thin needle spires on the crater lake's east rim, 40 to 125 m tall, threaded with violet star-glass that
rings in the wind (canon: the star's pieces left "black-glass craters lined with violet crystal that rings in the
wind"; the Greengrace crater is one of them). Liyue's needles with a star-crystal shimmer.
**Sculpt:** 30 needles within 330 m of (−640, 3230), on dry ground, radius 5 to 15 m, 42 to 125 m tall, tapering to a
point. Painted Rock with pale Salt; the crystals are props.

### 17. The Skyfall Scar (−5600, 3800)
A chain of five long craters gouged down Saltreach's spine where a piece of the falling star skipped along the ridge:
black glass floors, raised rims, violet crystal knots. The fifth and biggest tore open the West Volcano's south-east
flank *(new: canon puts the West Volcano on the spine; here the Skyfall breached it, which is why it sleeps)*.
**Sculpt:** five pits traced from the map along a 51.5° line: half-lengths 165 to 400 m, half-widths 58 to 190 m,
22 to 44 m deep (deeper at their south-east ends), super-elliptical with near-vertical walls, rims raised up to 12 m.
Pit 5 runs from the West Volcano's crater to (−5070, 4710). Crystal knots (3 to 8 m) on the floors (60 in pit 5).
Painted Volcanic. The Minecraft map has a straight ravine here too; the bake had filled it, and now carves this.

### 18. The Thunder Curtain (2150, 4200)
Sunreach's western lobe is a pale grey limestone plateau, broken into blocks and fissures, and on its east side it ends
in a long sheer escarpment over the lake's outlet. In the rains every stream on the plateau pours over that edge at once:
a curtain of water hundreds of metres wide with a roar you hear from the volcano. The grey region of the map.
**Sculpt:** the grey area is read off the map's colours (Sunreach regions only). It is raised 24 m, with warped Voronoi
blocks 38 m across (clints up to 3 m) and fissures 3.5 m deep between them, cliffs at its edges, and softened round
rivers and lakes so they sit in gorges. The escarpment follows (2170, 3900) → (2120, 4200) → (2150, 4520) on the
channel's west bank at 30 m. Painted pale (Rock + Salt), sparse trees.

### 19. Leviathan's Rest (1100, 4800)
In the mangroves where the plateau meets the sea, a ridge of rounded knolls and arched ribs runs out of the water: the
spine of a sea-beast the size of a hill, its skull resting on the shore, its eye sockets full of rainwater. Is it bone
or stone? Nobody agrees *(new)*. Inazuma's Orobashi skeleton, in Sunreach's mangroves.
**Sculpt:** a 1.1 km S-curved spine from (1380, 4960) to (560, 4380) with 24 vertebrae (24 m tall at the head to 9 m at
the tail), paired ribs every other vertebra (130 m long at the head to 50 m, curving tailward), and a 140 m skull at
(1450, 5000) with eye hollows and a jaw notch. Bones rise from the water where the mangrove channels cross. The plateau
dips into a hollow around it. Painted Salt (bone) and Rock.

### 20. The Sunstair Terraces (3300, 4300)
Hundreds of narrow terraces follow the contours of the volcano ridge's north-west flank like the lines of a hand, with
one straight stair running up through them all: Natlan / Bali rice terraces, golden at sunset.
**Sculpt:** within an ellipse 1240 x 960 m centred at (3480, 4400), between 12 and 110 m, the ground is quantised into
4.2 m terraces: flat treads and steep 0.5 m-wide risers, so they follow the real contours. A stair (0.6 m steps) runs
from (3150, 4380) to (3800, 4430). Treads painted Grass, no forest.

### 21. The Blue Eye (6900, 4600)
A ring of pale sand shallows in the open sea with a sapphire lagoon inside it and, in the middle, a hole that drops
straight down into the dark: the Great Blue Hole. Divers' treasure, and the deep home of something.
**Sculpt:** rings read off the map colours: the hole (95 m radius) drops with sheer walls to −62 m; the lagoon floor is
−11 to −7 m out to 370 m; the sand ring is −1.4 to −0.5 m out to 530 m, blending to the seabed over 220 m. Nine reef
rocks break the surface on the ring.

### 22. Glowcap Hollow (−10750, 5800)
The pink mushroom isle in the far south-west is a bowl: a rim of hills round a sheltered hollow full of giant glowing
mushrooms, with one low pass to the west cove.
**Sculpt:** within 520 m of (−10720, 5780), the island's coastal band (60 m) is a rim of 19 to 26 m and the inside
falls to 4 m; one pass on the west side drops the rim to a quarter. Painted Forest and pale Salt; the pink is the
material lane's (see needs).

### 23. The Bellstack (−1200, −6650) *new, needs the user's OK*
The map's 23rd ✦ sits in the open sea north of the Sisterfjord, with its label hidden by the title. I made it a lone
sea stack, 70 m tall, split by a narrow cleft: in a north swell the sea booms inside it like a great bell. Sailors
hear it long before they see it, so it may be the true source of the tavern rumour of a northern town "that still
answers with bells" (`lore.json`). If the user meant something else here, it is one entry in `wonders.json`.
**Sculpt:** a stack 44 m in radius, 70 m tall, wobbled outline, a 7 m cleft through it to −3 m, snow on its top, a
shoal of −4 m round it to 160 m.

## 4. Biomes repainted to the map

The bake now reads the map's colours too (`Fields._ref_masks`):
- **Snow:** the map's white (9.3 km² read off the map), plus all land north of about the Delvers' Gate (Z −3950) west of the
  Skyshoals taiga, plus the mountain spine above 110 to 150 m from the Frozen Cascade down past the Observatory. The
  snowline falls from 165 m in the south to 45 m on the north coast. Where it is white, snow outweighs grass and forest
  (snowy forest keeps some Forest for its trees).
- **Dark forest:** the map's dark green in the southern lands (Sunreach's east and south blocks) and round the High
  Table.
- **Thunder Curtain:** the map's pale grey in Sunreach's west lobe (2.4 km²), raised and painted pale rock.
- Saltreach's badlands and Greengrace's green are unchanged.

## 5. Needs from other lanes

- **Water** (in `terrain_manifest.json`): 14 new lakes and pools (the Ladder Lakes, the Glowmere pool, the Steaming
  Fields' five pools, the High Table's plunge pool) are appended to `lakes` with a `wonder` field; the editor build
  places them like any lake. Waterfalls (Veil Falls, the High Table, the Thunder Curtain, the Ladder Lakes' dams) are
  listed in `wonders[].waterfalls` for whoever builds falls.
- **Meshes** (a heightmap cannot overhang): the Long Door's lintel, the Rimeglass caves, the Glowmere overhang, the
  Frozen Cascade's ice curtains, Elderheart's tree.
- **Material (T50):** a pink tint for Glowcap Hollow; ice and glass looks for Rimeglass and the Glass Dunes; hot-spring
  water for the Steaming Fields.
- **Foliage (T51):** tree tops on the Skyshoals pillars; no trees on the Sunstair treads, dunes, causeway or bones.

## 6. Open questions for the user

1. The 23rd marker (under the title): is the Bellstack right, or did you mean something else there?
2. The Skyfall Scar breaching the West Volcano: the map draws the scar over the canon volcano, so I let the scar tear
   its flank open. OK, or should the volcano stand whole and the scar stop short?
3. The two Sisters, the fallen Rimeglass arch and the Leviathan's bones are inventions on top of the map names.
