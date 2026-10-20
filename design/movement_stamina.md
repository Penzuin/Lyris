# Movement and stamina spec

Owner: Design (T31). Built by: Player (T32) and UI (T33). Status: approved by the user
2026-10-20 (playable reference: `design/reference/wayfarers_breath.html`).

Walking, sprinting, jumping and climbing, and the one stamina pool they share, **Breath**.
The reference page is the source of truth for feel: open it in a browser and play it. This
doc writes down what that prototype actually does, in Unreal terms. Where the two disagree,
this doc says so.

> **Walking and jumping are free. Sprinting and climbing cost Breath. Running dry leaves
> you Winded, never hurt.**

Units: 1 m = 100 Unreal units (uu). Every value is a starting point for playtests; the
rules are fixed, the numbers are not.

## 1. Breath

| Field | Value | Notes |
|---|---|---|
| `Max` | 100 | Grows by **+20** per step to **200**, through Academy training. No levels or XP (pillar 2) |
| `Current` | 0 to `Max` | Refills on its own (§4) |
| `Bonus` | 0 to 50 | From food and drink (§6). Spent before `Current` |
| `LastSpendTime` | time | Any spend resets the refill delay |
| `bWinded` | bool | §5 |

- One pool for everything. There is no separate climb stamina.
- **Swimming never uses Breath** (T20, DECISIONS). Swimming is not a spend, so Breath
  refills normally in the water. Boarding ladders (T20) are not climbing and are free.
- **There is no health system yet. Falling never hurts**, from any height. The reference
  page mentions "no fall damage under 6 m"; that line predates this spec and is void.
- A spend can be fractional (drain per second × frame time). The displayed number rounds up.

## 2. Actions and costs

| Action | Speed / force | m | uu | Breath cost | Notes |
|---|---|---|---|---|---|
| Walk | ground speed | 4.5 m/s | 450 uu/s | 0 | Default pace. Breath refills while walking |
| Sprint | ground speed | 7.2 m/s | 720 uu/s | **18 / s** | Drains only while moving **on the ground**. About 5.5 s from full at Max 100 |
| Jump | apex | ≈ 1.2 m | ≈ 120 uu | 0 | Free, also while Winded. Variable height (§3) |
| Sprint jump | keeps sprint speed in the air | 7.2 m/s | 720 uu/s | **5** | Charged once at take-off if sprint is held |
| Climb, moving | up or down the wall | 2.2 m/s | 220 uu/s | **10 / s** | Rain or ice: ×1.5 (15 / s) |
| Climb, holding still | 0 | 0 | 0 | **3 / s** | Rain or ice: ×1.5 (4.5 / s). Lets players stop and look around |
| Climb leap | burst up the wall | ≈ 1.5 m | ≈ 150 uu | **20** | Jump while climbing. Stays on the wall. See §3 on scale |
| Wall kick | push off and up | 6.3 m/s away, 6.2 m/s up | 630 / 620 uu/s | **12** | Jump while holding away from the wall. Leaves the wall |
| Mantle | auto at the ledge | | | 0 | Always succeeds, even at 1 Breath or Winded mid-climb |

### Sprint

- Sprint needs: sprint held, a movement input, not Winded, and `Current + Bonus > 0`.
- In the air, sprint speed is kept as the target speed but nothing drains. Landing while
  still sprinting resumes the drain.
- The sprint-jump cost is not checked first: it can spend the last Breath and make you
  Winded on take-off. The jump still happens.

### Climbing

- **Grab:** walk or fall into a climbable surface while pushing toward it. On the ground
  you must also push up (forward/up in 3D) to start climbing; in the air, pushing into
  the wall is enough. Can't grab while Winded or at 0 Breath.
- **What is climbable** (prototype): any wall at least **80 px** tall (1.33 m, 133 uu, at its
  horizontal scale). Shorter
  blocks are jumped onto, not climbed. The 3D rule is an open question (§11).
- **Leap:** jump while climbing and not pushing away. A short burst up the wall
  (prototype: 0.22 s); no hold drain during the burst.
- **Wall kick:** jump while pushing away from the wall. Lets go, launches away and up, and
  blocks re-grabbing for **0.3 s** so you don't stick straight back.
- **Not enough Breath for a leap or kick:** nothing happens, you stay on the wall, and the
  ring flashes the cost preview red for **0.5 s** (§8).
- **Mantle:** when the ledge is below 45% of the character's height from the feet (55% of
  the body is above the top), the character pulls up onto the top. Free and certain.
- **Bottom of a wall:** pushing down at the bottom lets go.

## 3. Jump and air feel

| Helper | Value | Meaning |
|---|---|---|
| Coyote time | **0.12 s** | Can still jump this long after walking off a ledge |
| Jump buffer | **0.15 s** | A jump pressed this long before landing fires on landing |
| Variable jump | **0.5** cut | Releasing jump while rising multiplies upward speed by 0.5 |
| Air control | **60%** | Air acceleration is 60% of ground acceleration |
| Ground acceleration | 43 m/s² (4330 uu/s²) | Reaches walk speed in about 0.1 s |
| Air acceleration | 26 m/s² (2600 uu/s²) | 60% of ground |

Jump arc in Unreal: `JumpZVelocity` **740 uu/s** (7.4 m/s) with gravity **2300 uu/s²**
(23 m/s², `GravityScale` ≈ 2.35) gives a **1.19 m** apex in **0.32 s**: snappy, not
floaty. Terminal fall speed **1400 uu/s** (14 m/s).

**Prototype scale.** The page's tuning says 60 px = 1 m, and that holds for horizontal
speeds (walk, sprint, climb, acceleration, wall kick push). Its vertical numbers do not
fit it: at 60 px/m its jump would peak at about 2 m, not the 1.2 m the page's own table
states. This spec keeps the stated 1.2 m and the prototype's timing, which works out to
reading vertical prototype values as uu (jump 740, gravity 2300, kick 620, fall 1400).
Read the same way, the prototype's leap (440 px/s for 0.22 s) is about 1 m, against the
table's ≈ 1.5 m. Build the leap to **1.5 m** (about 680 uu/s for 0.22 s) and tune in play.

## 4. Recovery

- Refill waits **0.8 s** after the last spend.
- Then ramps linearly from **20 / s** to **50 / s** over **1.5 s**, and stays at 50 / s.
- Near-empty to full at Max 100 takes about **3.3 s** (0.8 s wait + 1.5 s ramp + ~1 s at
  50/s); about 3.6 s from fully empty, because the first stretch is Winded.
- **No refill while climbing (moving or still) or while sprinting on the ground.**
- **Refill is allowed in the air**, while walking, standing and swimming.
- Refill only fills `Current`. `Bonus` never refills on its own.

## 5. Winded

- `Current` reaching 0 makes you **Winded**.
- While Winded: **no sprint, no climbing, no grabbing**. Walking and jumping work as normal.
- **Winded on a wall: you slide off** (let go with a small downward push) and can't
  re-grab for **0.6 s**. Falling never hurts.
- Refill runs at **×0.7** while Winded (14 → 35 / s). From empty, Winded clears about
  2.3 s after the last spend.
- **Winded clears at 35% of Max** (35 at Max 100). A small gold flourish marks it.
- The prototype uses an absolute 35; at Max 100 the two are the same. See §11.

## 6. Bonus Breath (food and drink)

- Food and drink grant **Bonus** Breath. The prototype item is lantern **tea: +50**.
- Bonus is **spent first**, so the main ring stays honest.
- Drinking sets `Bonus` to the item's amount (it does not stack past it) and restarts
  refill at once (the 0.8 s delay is skipped).
- Bonus does not decay over time and does not refill. It does not stop Winded from
  triggering: Winded only happens once Bonus is gone and `Current` hits 0.
- The prototype has a 6 s cooldown between drinks so tea can't be chained.

## 7. Growth

- Academy training raises `Max` by **+20** per step: 100, 120, 140, 160, 180, 200.
- The ring never gets bigger on screen. Each step adds an extra tick on the ring instead.
- Costs and rates stay the same, so a bigger pool simply means longer sprints and climbs
  (sprint from full: 5.5 s at 100, 11 s at 200).

## 8. The Breath ring (HUD)

A ring beside the character's head (screen-projected from a head socket, offset to the
side and slightly above). It starts at 12 o'clock and fills clockwise. It answers five
questions at a glance instead of one.

| Part | Behaviour | Colour (reference) |
|---|---|---|
| **Main arc** | `Current / Max` | Ramp below |
| **Colour ramp** | Above 50%: amber → gold. 20–50%: ember → amber. Below 20%: ember | Gold `#F2C14E`, amber `#F0923E`, ember `#EF6B4F` |
| **Winded** | Whole ring turns slate; ring shakes for 0.35 s on going Winded | Slate `#8A93B8` |
| **Drain trail (ghost)** | A pale arc stays where Breath just was, holds 0.45 s, then catches up at 70 Breath / s. Shows what the last leap cost | `#FFF2CF` at 75% |
| **Vial** | Glass vial in the centre; water level and ripples match `Current / Max`. **Cracks when Winded** and goes slate | Water `#9FD0F0` → `#3B6FAE`; Winded `#8A93B8` → `#4A5378` |
| **Leap cost preview** | Only while climbing: a dashed outline just outside the ring over the slice a leap (20) would spend, after Bonus. **Red and pulsing if unaffordable** (drawn 0 → cost), and for 0.5 s after a failed leap | White; red `#EF6B4F` |
| **Tea halo** | Thin glowing outer ring, length `Bonus / item amount`; shrinks as Bonus is spent | `#7FE0D0` |
| **Recovery notch** | Only while Winded: a gold dot at 35% showing when sprint and climbing return | `#F2C14E` |
| **Quarter notches** | Dark ticks at 25%, 50%, 75% | Ink at 85% |
| **Growth ticks** | One extra tick per +20 Max step (§7) | |
| **Low-breath glow** | Below 25% (and not Winded): a soft ember glow that breathes slowly, never a harsh flash | `#EF6B4F` |
| **Head spark** | A small bright dot at the arc's end for 0.08 s after each spend; motes drift off it while draining | |
| **Hide when full** | Shown while `Current < Max`, Bonus > 0, Winded, or within **1.2 s** of the last spend. Fades in fast and out slowly, scaling from 70% to 100% as it appears | |

- Bursts of motes: gold on a leap or wall kick and when Winded clears, teal on drinking tea.
- Reduced motion: no shake, no motes, the low-breath glow holds steady.
- Reference size on a 960 × 520 view: radius 17 px, arc thickness 5 px. Scale with the UI.
- The hex values come from the reference page. Colours live in a curve asset so the UI
  lane can tune them by eye toward the storybook palette.

## 9. Building it

### Player lane (T32)

- `ULyrisStaminaComponent` on the character: `Current`, `Max`, `Bonus`, `LastSpendTime`,
  `bWinded`. Exposes `TrySpend()`, `CanAfford()`, `AddBonus()` and an `OnStaminaChanged`
  delegate (current, max, bonus, winded, ghost data not needed: UI keeps its own).
- Sprint and jump stay in `UCharacterMovementComponent`. Coyote time, the jump buffer and
  the 0.5 jump cut are added on top (Unreal's `JumpMaxHoldTime` is a different model).
- Climbing is a `MOVE_Custom` mode: wall-normal traces to stick, a ledge trace for the
  mantle, and the leap and wall kick as impulses.
- Tuning in **Project Settings > Game > Lyris Movement** (a `UDeveloperSettings`, the same
  pattern as T5's wind), as the board says. The reference page suggests a data asset;
  the board wins.
- Server-authoritative Breath, with client prediction for sprint drain.
- Swimming (T20) also edits `LyrisCharacter`: coordinate, and keep swimming out of Breath.

### UI lane (T33)

- One widget, one material: main arc, ghost arc, preview arc, halo and vial driven by
  scalar parameters. C++ Slate like T24, no `.uasset` needed if the material is built by
  script.
- Projected beside the head socket. Binds to `OnStaminaChanged`; animation (ghost, fade,
  glow) runs in the widget, game logic does not.

## 10. Unreal values at a glance

| Setting | Value |
|---|---|
| `MaxWalkSpeed` (walk) | 450 uu/s |
| Sprint speed | 720 uu/s |
| `MaxAcceleration` | 4330 uu/s² |
| `AirControl` | 0.6 |
| `JumpZVelocity` | 740 uu/s |
| `GravityScale` | ≈ 2.35 (2300 uu/s²) |
| Terminal fall speed | 1400 uu/s |
| Climb speed | 220 uu/s |
| Leap | ≈ 150 uu (≈ 680 uu/s for 0.22 s) |
| Wall kick | 630 uu/s away, 620 uu/s up |
| Re-grab lockout | 0.3 s after a kick, 0.6 s after a Winded slide |
| Minimum climbable height | prototype: 80 px (1.33 m at its horizontal scale); 3D rule in §11 |

## 11. Open questions

1. **What counts as climbable in 3D?** Proposal: any surface steeper than about **60°**,
   unless tagged `NoClimb` (for invisible walls, glass, story-locked places). Surfaces
   shallower than 60° are walked.
2. **Winded threshold with a bigger pool:** 35% of Max (spec, so 70 at Max 200) or an
   absolute 35 (prototype, so upgrades also shorten Winded)?
3. **Rain and ice:** the ×1.5 climb cost needs World's weather (P3) and a surface tag for
   ice. Not in the prototype.
4. **Gliding later?** If added, does it drain Breath like holding still on a wall (3 / s),
   or is it free like walking?
5. **Bonus Breath:** should it ever fade (say over a few minutes), and do different foods
   give different amounts, or only one at a time?
6. **Climbing while carrying** heavy items (T11 inventory): allowed, or blocked?
7. **A future health system** must keep "falling never hurts" unless the user changes the
   decision.
