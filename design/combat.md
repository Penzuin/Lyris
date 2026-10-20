# Combat

**Status:** design spec, approved direction (2026-10-20): Genshin-style action, played by one
character. No party and no character swapping.

Combat in Lyris is real-time and responsive like Genshin Impact, but it serves the game's
pillars: it is **optional**, it lives **where the mist and the deep are**, and it never costs
you anything you love. Home waters by day stay peaceful.

## 1. Pillars for combat

1. **Feels great in the hands.** Snappy combos, readable enemies, satisfying hits (hit-stop,
   knockback, stagger), dodges with real timing.
2. **One character, many answers.** Instead of swapping characters, you combine your own
   skills with the world: the sea, rain, wind, lamplight and the mist.
3. **Light is the heart of it.** Lyris's lore is lamps against the mist. Your light is both
   weapon and lifeline.
4. **No grind, no loss.** No XP and no stats to allocate. Defeat sends you home safely.
5. **Never against the gentle.** Wildlife, including legendary animals, is never an enemy.
   Neither are mist moths or the Pale Stag.

## 2. Where combat happens

| Place | Intensity |
|---|---|
| Home waters and lit towns by day | None. Weapons stay sheathed. |
| Unlit land and sea at night, inside the mist | Light skirmishes: mist crawlers, lamp-thieves |
| Ruins, wrecks, the far deep | Encounters and mini-bosses |
| The Hollowdeep (six strata) | Full combat, puzzle-bosses, endgame |

Distance from the lamps sets intensity, exactly like the rest of the world.

## 3. The moveset (keyboard and mouse; controller mirrors Genshin)

| Input | Action | Notes |
|---|---|---|
| Left click | **Normal attack** | 4-hit combo. Each hit opens a short window for the next; the 4th hit staggers. |
| Hold left click | **Charged attack** | Costs stamina. Weapon-specific (spin, lunge, aimed shot, light beam). |
| Left click while falling | **Plunging attack** | Shockwave on landing; pairs with gliding. |
| Right click or Shift | **Dash** | Costs stamina, brief invulnerability. |
| Dash just before a hit lands | **Perfect dodge, "Lull"** | Time slows briefly and the stamina is refunded. The skill-expression moment. |
| E | **Art** (skill) | Short cooldown. Applies your attunement. Tap and hold variants. |
| Q | **Surge** (burst) | Charged by landing hits. Big area attack, brief invulnerability. |
| Middle click | **Lock on** | Optional. Normal targeting is a soft aim-assist cone, like Genshin. |

**Stamina** is shared with sprinting, climbing, gliding and swimming, so fights and traversal
feel like one system.

**Hit feel:** a 50 to 80 ms hit-stop on solid hits, small camera shake on heavy hits,
knockback by weight, and a **poise** bar: break it and the enemy staggers.

## 4. Attunements: elements without a party

You carry **one attunement** at a time. You change it at any lit lamp, never mid-fight, so
there is no swapping. Your Art and Surge use it.

| Attunement | Feel | Art examples |
|---|---|---|
| **Lantern** (light) | Cleanses mist, reveals, blinds | Flare that bursts the mist off nearby foes |
| **Tide** (water) | Soaks, flows, heals a little | A wave that sweeps foes and leaves them Wet |
| **Gale** (wind) | Gathers, lifts, carries | A gust that pulls foes together or lifts you |
| **Ember** (fire) | Burns, ignites gas and brush | A hearth-flame slash that sets foes Burning |

### Reactions come from the world

Genshin's reactions need two elements. With one character, the second comes from the world:

| States | Where the second one comes from | Reaction |
|---|---|---|
| **Misted** + Lantern | Every mist creature at night | **Dispel**: heavy damage, strips their mist armour. The core loop. |
| **Wet** + Ember | Sea spray, rain, tidecrabs, Tide-soaked foes | **Steam**: burst of damage, a short screen of fog |
| **Wet** + Gale | Same | **Squall**: pulls foes in and knocks them down |
| **Wet** + Lantern | Same | **Prism**: light refracts and hits several foes |
| **Burning** + Gale | Braziers, Ember-attuned hits, the Ember Forges' gas | **Flare-up**: fire spreads to neighbours |

Weather and place change your best attunement: rain favours Ember and Gale, the mist favours
Lantern. That gives solo combat its variety.

## 5. Weapons

Anyone can use any weapon; you swap at home or at a camp, not mid-fight. Weapons hint at
paths but never lock them.

| Weapon | Style | Charged attack | Path flavour |
|---|---|---|---|
| **Cutlass** | Fast combos | Spinning cut | Seafarer |
| **Oar-maul** | Slow, breaks poise | Overhead slam | Maker, Delver |
| **Harpoon** | Reach, pulls foes | Lunge and pull | Seafarer, Wanderer |
| **Bow** | Ranged, weak points | Aimed shot | Wanderer, Grower |
| **Lantern** | Catalyst, light orbs | Focused beam | Scholar |

## 6. Enemies (from Lyris canon)

| Enemy | Where | How it fights | Lesson it teaches |
|---|---|---|---|
| **Mist crawler** | Shores and roads in the mist (Seawall Stair lore) | Scuttles in, lunges with a clear glow tell | Basics: combo, dodge, Dispel |
| **Tidecrab** | Tide lines at night | Armoured, always Wet; shell must be staggered | Poise and Wet reactions |
| **Lamp-thief** | Deep mist | Cowardly; goes for your lantern, flees | Protect your light; the fight is about your lamp |
| **Wisp-lure ambush** | Following a wisp too far | A pack of lamp-thieves | Crowd control (Gale, Squall) |
| **Drowned** and the **bellringer** | Hollowdeep I | Hum a lullaby; the bellringer buffs them | Target priority |
| **Brass Wardens** | Hollowdeep II | Count hits; levers shut down turrets | Puzzle-bosses |
| **Root wyrms** | Hollowdeep III | Burrow; spores | Ember shines here |
| **Golems** in gas | Hollowdeep IV | Open flame ignites the air | Ember is dangerous here; use a safety lamp |
| **Light-only foes** | Hollowdeep V | Exist only inside your lantern light | Light as sight |
| **Choir acolytes**, **crystal crawlers** | Hollowdeep VI | Dim your lantern; reflect arrows | Adapting your attunement |

Never enemies: all wildlife (Old Tusk, the Ashen Elk, Thornback, Old Gnash...), mist moths,
the Pale Stag, the Watcher.

## 7. Defeat and safety

- Defeat: "the tide carries you home." You wake at the last lamp you lit, healed.
- Nothing is lost. At most, a mist cache you were carrying drops where you fell, and stays
  until you collect it.
- Fleeing always works: run into lamplight and mist creatures will not follow.

## 8. Getting stronger, without XP

- **Weapon tempering** with materials found by exploring (star iron, brass, Aurenn glass).
- **Mastery by doing:** using an attunement unlocks variants (a longer Gale, a healing Tide).
- **Lamp blessings:** relighting lamps across the Reach raises your stamina and lantern oil.
- Gear and skill only; no levels, no stat points.

## 9. Accessibility and options

- Difficulty: *Gentle* (enemies telegraph longer, hit softer), *Standard*, *Deep*.
- Assists: hold to keep comboing; optional auto-dodge on Gentle; colour-blind-safe tells.
- Co-op later: each player brings their own one character; reactions combine naturally.

## 10. First prototype (what gets built first)

1. Player combat: 4-hit combo, charged attack, dash with i-frames and perfect-dodge Lull,
   stamina, soft target, hit-stop and knockback.
2. One attunement, **Lantern**: Art = Flare (burst that applies Lantern), Surge = Lighthouse
   Beam (big area burst).
3. One reaction: **Dispel** (Misted + Lantern).
4. One enemy: the **mist crawler** (health, poise, glowing tell, lunge, stagger, Misted).
5. A small training ground on the island where crawlers keep coming out of the mist.
6. Defeat sends you back to the dock lamp.

Placeholder art: Unreal mannequin animations and basic shapes until real assets exist.
