# Farming spec

Owner: Design (T28). Built by: Harvest (T13 and follow-ups). Status: approved by the user 2026-10-20.

Stardew Valley's farming loop (till, plant, tend, harvest, scale up), rebuilt for a 3D,
real-time, shared world, with one hard rule from pillar 1:

> **Nothing is ever lost by not tending. Tending only adds.**

## 1. The one rule

A planted crop always grows at its **base rate**, on real-world time, whether the player
is online or not. It never wilts, dies, rots, gets eaten, loses a stage or loses quality.
A player who leaves for a month comes back to a ripe field.

Everything the player does on top of that is a **bonus**: faster growth, better quality,
bigger harvests, rare finds. Removing a bonus only returns the crop to its base rate.

If a proposed feature would make an untended crop worse off than "base rate", it breaks
this spec.

## 2. The grid

- Soil is a grid of cells, **100 cm** per cell, owned by a plot actor. The grid follows the
  terrain (each cell is traced to the ground), so plots work on slopes and terraces.
- The player aims with the interaction target from T10; tools highlight the cell under it.
  Upgraded tools highlight an area (3×3, then 5×5).
- A cell is one of: `Untilled`, `Tilled`, `Planted`. Tilled soil never reverts on its own.
- Weeds may sprout on empty tilled cells for flavour. They never spread onto crops, never
  slow anything and never block planting; pulling one gives fibre or a forage item.

## 3. Growth model

Growth is calculated from timestamps, never ticked per frame. A cell stores:

| Field | Meaning |
|---|---|
| `Crop` | The crop definition (data asset) |
| `PlantedAt` | Real-world UTC time the seed went in, or the last regrow |
| `BonusSeconds` | Extra growth earned from tending, already banked |
| `WateredUntil` | Real-world UTC time the watering bonus ends |
| `QualityPoints` | Accumulated care toward a better harvest |
| `CaredToday` | Last real-world day the crop got its daily care |

Effective growth time:

```
growth = (now - PlantedAt) * BaseRate * SeasonFactor
       + BonusSeconds
       + overlap(PlantedAt..now, watering window) * WaterBonus
```

The current stage is the last stage whose threshold `growth` has passed. Growth stops
counting at maturity. Because it is pure maths on timestamps, offline growth costs
nothing and a server only evaluates a cell when someone looks at it or interacts.

## 4. Crop definitions (data assets)

Each crop is a `ULyrisCropDefinition` data asset:

| Field | Example (Mistberry) | Notes |
|---|---|---|
| Stage meshes | 5 meshes | Seed, sprout, young, budding, ripe |
| Base time to ripe | 6 h real time | Starting values below; tune in playtests |
| Seasons | Spring, Summer | Empty = any season |
| Regrows | yes, every 2 h | After harvest, back to a set stage |
| Yield | 2 to 4 berries | Item from T11 |
| Seed item | Mistberry Seeds | |
| Giant chance | 2% | 3×3 of the same ripe crop may merge into a giant crop |
| Footprint | 1×1 | Trellis crops can be walked under |

Starting pace: quick crops ripen in about 3 h real time, standard crops 6 to 12 h, slow
and valuable crops 1 to 3 days. Tune freely; the spec only fixes the rule, not numbers.

## 5. Tending: bonuses only

| Action | Bonus | Lasts | Without it |
|---|---|---|---|
| **Water** | Growth runs at **+50%** speed | 4 h real time, rain counts | Base rate |
| **Fertilize** (one per planting) | One of: +25% speed, +1 quality tier chance, +1 yield | Until harvest | Base rate |
| **Daily care** (talk, prune, sing: one small interaction) | +1 `QualityPoints`, small chance of a rare variant or bonus seeds | Once per crop per real day | Normal quality |
| **Scarecrow / ward stone** in range | +10% yield, small chance of a rare drop | While placed | Normal yield |
| **Weeding** | Fibre, herbs | Instant | Weeds just sit there |

Quality: Normal, Fine, Splendid, Radiant. Every crop can reach at least Normal with zero
care. Care and fertilizer raise the odds of the higher tiers.

## 6. Seasons

Seasons come from the World lane's real-time calendar (T1 and its follow-ups).

- An **in-season** crop gets `SeasonFactor = 1.25` and a small quality bonus.
- An **out-of-season** crop goes **dormant**: `SeasonFactor = 0`, growth paused, nothing
  lost. It wakes up when its season returns, and it can always be harvested if it was
  already ripe.
- Glasshouses and some special soils count every season as in season.

Until World ships seasons, every crop is treated as in season.

## 7. Progression: knowledge, not levels

Pillar 2: no farming XP and no levels. Farming gets better because the player knows and
owns more, and every upgrade buys **more bonus for less effort**, never escape from a chore.

| Step | What the player gains | How they get it |
|---|---|---|
| 1. Hands | Hoe, watering can, a small home plot | Start of game |
| 2. Better tools | Charged hoe and can (3×3, then 5×5) | Crafting with gathered materials |
| 3. Know your crops | Recipes for fertilizers, care techniques that raise quality odds | Academy herbology classes, books found while exploring, neighbours |
| 4. Irrigation runes | Placeable stones that keep the watering bonus on permanently in a radius (2, 4, then 12 cells) | Crafted from materials found in unlit waters |
| 5. Soils and glasshouses | Volcanic, riverbank and mist-fed soils raise the **base** rate or allow other seasons; glasshouses ignore seasons | Discovered on far islands, carried home |
| 6. Constructs | Enchanted scarecrow constructs that harvest, replant and give daily care in a radius | Late crafting; objects, not creatures (no creature raising) |
| 7. Processing | Kitchen and alchemy stations turn crops into goods worth more | Recipes from exploration and the academy |
| Later | Combining strange plants into new varieties | Cultivation lane |

## 8. Multiplayer

- A plot belongs to a player's home island; friends can be given permission to tend.
  Their care counts the same as the owner's.
- Cell state is small and replicated in a fast array; the timestamps make it identical on
  every machine without ticking.
- A harvest is decided on the server.

## 9. Building it (Harvest lane)

- `ULyrisCropDefinition` (data asset), `ALyrisFarmPlot` (owns the grid, instanced static
  mesh per stage for performance), `FLyrisSoilCell` (the record above), all in
  `Source/Lyris/Harvest/`.
- The plot implements the T10 interaction interface; seeds and produce are T11 items.
- Tools and their area come later; the first version can till, plant, water and harvest
  one cell at a time.
- Hand-offs: World (seasons, rain), Environment (placing a plot on Harbor: T15),
  UI (stage and bonus tooltip on hover).
