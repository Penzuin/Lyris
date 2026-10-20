# Character creator

Spec for task T22. Owner: Design lane. Readers: Player lane (T23, appearance system), UI lane
(T24, creator screen), Environment lane (T25, base mesh), Lead (T26, new-player start).

The shared code contract (`FLyrisAppearance`, `FLyrisSliderDef`, `FLyrisPartDef`,
`FLyrisColorChannelDef`, `FLyrisCharacterProfile`, share codes, randomise) was fixed by the lead and
is not repeated here. This document fills it with content: every id, range, part and swatch the
default catalog (`ULyrisAppearanceCatalog::GetDefault()`) should contain, plus the flow and the
quality-of-life rules the UI follows.

Settled by `design/DECISIONS.md` (2026-10-20): creation is deep, in the spirit of Black Desert and
Where Winds Meet, but stays storybook painterly. Slider ranges keep stylized proportions and colours
come from curated, hue-shiftable swatch bands. No stats. Looks are never locked.

The user's answers to the open questions (2026-10-20) are logged in `design/DECISIONS.md` and applied
here: Peoples differ in look only, the colours are approved, faith is not chosen in the creator, and
the creator has six steps.

---

## 1. Ids and conventions

| Thing | Rule | Example |
|---|---|---|
| People ids | `Human`, `MoonlitElf`, `Deepkin` | `People = "MoonlitElf"` |
| Frame ids | `FrameA` (display "Willow": narrower, lighter) and `FrameB` (display "Oak": broader, sturdier). Cosmetic only, not gendered. Every option works on both frames. | `Frame = "FrameB"` |
| Category ids | `Body`, `Face`, `Eyes`, `Hair`, `Skin`, `Makeup`, `Outfit`, `Voice`. Plus `Lantern`, which holds the lantern shapes and glass channel and is shown only at step 5, never as an Appearance tab. | |
| Section ids | PascalCase, listed per category below | `Face` > `Nose` |
| Slider ids | `<Area>.<Name>`, PascalCase, no spaces or underscores. The area prefix is a body area, not always the category: always read the slider's `Category` field. Left/right pairs end in `L` / `R`. | `Face.JawWidth`, `Eyes.SizeL` |
| Part ids | `<Slot>.<Name>` | `Hair.RopeBraid` |
| Empty part | No key in `Parts`, or the part id `None`. Slots marked *optional* allow it. | |
| Part scalar keys | `<Slot>.<Name>`, and makeup uses `Makeup.<Slot>.<Name>` (as in the contract) | `Freckles.Opacity`, `Makeup.Eyeliner.Opacity` |
| Colour channel ids | `<Category>.<Name>` | `Hair.Root` |
| Morph names (T25) | `Area_Name` with `_L` / `_R` for sides; listed in the tables. Two-way sliders use `<Name>_Pos` / `<Name>_Neg` if the mesh has them. | `Jaw_Width`, `Eye_Size_L` |

**Mirrored space.** Every left/right pair is defined so that the *same value on both sides gives a
symmetric face*. Positive `Eyes.TiltL` and positive `Eyes.TiltR` both lift the outer corner. The
Player lane flips axes in the targets so this holds. Symmetry mode then simply copies the value to
`MirrorOf`.

**Range column.** The slider range the UI shows (`Min..Max`, usually `-1..1`; one-sided sliders are
`0..1`). Default is `0` for every slider.

**Limit column.** What the slider does at its ends, which sets each target's `Weight`. These limits
*are* the style guardrail; see section 5 for why.

**Sculpt column.** `Region / H` or `Region / V`: the face region and drag axis for click-and-drag
sculpting (`SculptAxis` 0 = H, 1 = V). Each region has at most one slider per axis. `-` means not
sculptable (use the slider).

**People column.** Empty = all Peoples.

---

## 2. The flow: a dusk voyage to Moonharbor

The player is a passenger on a small sloop sailing toward Moonharbor at dusk, answering the
Lamp-Heir's call. Each step is a moment on that voyage. The sun sinks across the steps, the
lighthouse beam starts sweeping and the mist begins to rise at step 5, and the player lights
their lantern on the dock after step 6 (T26 then drops them on the Harbor dock).

The boat never stops: gentle swell, creaking ropes, gulls, wind in the sail. The character stands on
deck the whole time so the player always sees their choices in dusk light.

| # | Step | Moment on the voyage | What the screen shows | Default framing | Required? |
|---|---|---|---|---|---|
| 1 | People | The sloop leaves the last waystone. The skipper (an old Reach sailor) asks "Where do you hail from, friend?" | Three cards (Human, Moonlit elf, Deepkin) with a painted portrait and two lines of flavour. Peoples differ in look only. Picking one swaps the deck character live and loads that People's first preset. Frame toggle (Willow / Oak) sits under the cards. | Full body | Yes |
| 2 | Appearance | Aft deck under the hanging stern lamp, a brass ship's mirror lashed to the mast. "Let's get a look at you before we make port." | The deep editor: category tabs down the left (Body, Face, Eyes, Hair, Skin, Makeup, Outfit, Voice), sections and sliders on the right, toolbar on top (undo, redo, symmetry, randomise, presets, share code, compare, lighting, expression, pose). Orbit and zoom on the character. | Changes per category (table below) | Yes (a preset is a valid answer) |
| 3 | Path | Your sea chest is open on deck. | Seven path cards, each with its starting item laid in the chest (spyglass, staff and pack, trowel and seed pouch, tool roll, notebook, ledger and scales, lamp and pick), the branches it leads to, and the line "A head start, not a fence." The character holds the chosen item. | Upper body, item in hand | Yes |
| 4 | Backstory | A keepsake from the chest: a letter, a charm, a recipe card. The skipper asks what brought you here. | Backstories for the chosen path (section 8.2) as letters, plus **Keep it to myself** (no backstory). One line per backstory on what it adds (flavour dialogue and a personal quest). | Upper body, keepsake in hand | No |
| 5 | Lantern | Ilwen's Lighthouse beam sweeps over the deck, Moonharbor's lights come into view and the mist starts curling off the water. | Lantern shapes on a rail, then a glass colour band with hue/value shift, previewed lit in the mist. "Your first treasure." | Lantern close-up: chest up, lantern held in both hands | Yes |
| 6 | Name | The sloop ties up. The harbourmaster opens the ledger by lamplight. | The ledger page with your name being written in ink as you type, and a summary of the character (People, path, backstory, lantern). Confirm, then the cut to lighting the lantern on the dock. | Upper body at the ledger, then full body on the dock | Yes |

Steps can be revisited from a small ship's-log strip along the top (six knots on a rope). Going
back never resets later steps unless the choice is invalid (for example a backstory from another
path, which is cleared with a note).

### 2.1 Camera framing per category and section

Four framings plus the lantern shot. The camera eases between them (0.6 s). The player can always
orbit (yaw 360, pitch -15 to 30 degrees) and zoom within the framing's range; picking a new section
re-frames.

| Framing id | Shows | Typical distance | Used for |
|---|---|---|---|
| `Full` | Whole body, head to feet, with a little deck | 260 cm | Step 1; Body: Frame, Proportions, Build, Posture; Outfit: all; Voice: Voice |
| `Upper` | Waist up | 130 cm | Steps 3, 4, 6; Body: Hands & feet (character raises hands, then looks down at feet when a foot slider is touched); Hair: Style, Accessories; Skin: Markings on neck/shoulders; Voice: Expression |
| `Face` | Head and neck, slightly from below eye line | 55 cm | Face: Shape, Forehead, Nose, Mouth, Ears (turns to profile when an ear or nose-projection slider is dragged); Hair: Colour, Brows, Facial hair; Skin: Tone, Details; Makeup: Lips, Cheeks, Face paint |
| `Eyes` | Both eyes and brows, extreme close-up | 25 cm | Face: Eyes, Brows; Eyes: all; Makeup: Eyes |
| `Lantern` | Chest up, lantern held at chest height | 80 cm | Step 5 |

---

## 3. Appearance catalog: sliders

Totals: **Body 32, Face 94, Eyes 6, Skin 5, Voice 1 = 138 sliders** (36 of them in 18 left/right
pairs, 24 sculptable). Plus 25 part scalars (section 3.7). All ranges are `-1..1` unless shown otherwise.

### 3.1 Body

Body sliders drive UE5 mannequin bones today (`BoneScale`, `BoneOffset`, `BoneRotation`) and add
morphs once T25 lands. None are sculptable; body editing is slider-only.

**Section `Frame` (Frame & height)**

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Targets |
|---|---|---|---|---|---|---|
| `Body.Height` | Height | -1..1 | shorter / taller | ±8% overall | | pelvis scale (uniform) |
| `Body.TorsoLength` | Torso length | -1..1 | short / long torso | ±8% | | spine_02..04 scale Z |

**Section `Proportions`**

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Targets |
|---|---|---|---|---|---|---|
| `Body.HeadSize` | Head size | -1..1 | smaller / larger head | ±8% (see adult guard, 5.2) | | head scale |
| `Body.NeckLength` | Neck length | -1..1 | short / long | ±15% | | neck_01 scale Z |
| `Body.NeckThickness` | Neck thickness | -1..1 | slender / thick | ±15% | | neck_01 scale XY |
| `Body.ShoulderWidth` | Shoulder width | -1..1 | narrow / broad | ±3 cm per side | | clavicle_l/r offset Y |
| `Body.ShoulderSlope` | Shoulder slope | -1..1 | sloped / square | ±8° | | clavicle_l/r rotation roll |
| `Body.ChestWidth` | Chest width | -1..1 | narrow / wide | ±10% | | spine_04 scale Y |
| `Body.ChestDepth` | Chest depth | -1..1 | flat / deep | ±10% | | spine_04 scale X |
| `Body.ChestShape` | Chest shape | -1..1 | flatter / fuller chest | ±12%, morph | | spine_05 scale X; morph `Chest_Full` |
| `Body.WaistWidth` | Waist width | -1..1 | narrow / wide | ±12% | | spine_01 scale XY |
| `Body.HipWidth` | Hip width | -1..1 | narrow / wide | ±12% | | pelvis scale Y; thigh_l/r offset Y ±1.5 cm |
| `Body.ArmLength` | Arm length | -1..1 | short / long | ±8% | | upperarm_l/r, lowerarm_l/r scale X |
| `Body.UpperArmThickness` | Upper arm | -1..1 | slim / thick | ±15% | | upperarm_l/r scale YZ |
| `Body.ForearmThickness` | Forearm | -1..1 | slim / thick | ±15% | | lowerarm_l/r scale YZ |
| `Body.LegLength` | Leg length | -1..1 | short / long | ±8% | | thigh_l/r, calf_l/r scale X |
| `Body.ThighThickness` | Thigh | -1..1 | slim / thick | ±15% | | thigh_l/r scale YZ |
| `Body.CalfThickness` | Calf | -1..1 | slim / thick | ±15% | | calf_l/r scale YZ |

**Section `Build`**

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Targets |
|---|---|---|---|---|---|---|
| `Body.MuscleTone` | Muscle tone | -1..1 | soft / defined | morph weight 1; painted shape only, no veins | | morph `Muscle_Tone`; material `MuscleDefinition` |
| `Body.Softness` | Softness | -1..1 | lean / soft and round | morph weight 1 | | morph `Body_Soft`; spine_01..03 scale XY ±10% |
| `Body.Belly` | Belly | -1..1 | flat / round | morph weight 1 | | morph `Belly`; spine_01 scale X ±10% |
| `Body.BackWidth` | Back width | -1..1 | narrow / broad back | ±10% | | spine_03 scale Y |
| `Body.ShoulderBulk` | Shoulder bulk | -1..1 | slight / heavy shoulders | ±12% | | upperarm_l/r scale YZ near joint; morph `Shoulder_Bulk` |
| `Body.HipShape` | Hip shape | -1..1 | straight / curved | morph weight 1 | | morph `Hip_Curve` |

**Section `HandsFeet` (Hands & feet)**

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Targets |
|---|---|---|---|---|---|---|
| `Body.HandSize` | Hand size | -1..1 | small / large | ±12% | | hand_l/r scale |
| `Body.FingerLength` | Finger length | -1..1 | short / long | ±10% | | morph `Finger_Length` (bones when the mesh has finger bones) |
| `Body.FootSize` | Foot size | -1..1 | small / large | ±12% | | foot_l/r scale |
| `Body.NailLength` | Nails | 0..1 | short / longer, rounded | morph weight 1 | | morph `Nail_Length` |

**Section `Posture`**

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Targets |
|---|---|---|---|---|---|---|
| `Body.Lean` | Lean | -1..1 | slouched / upright | ±6° | | spine_02 rotation pitch |
| `Body.HeadCarriage` | Head carriage | -1..1 | chin down / chin up | ±5° | | neck_01 rotation pitch |
| `Body.ShoulderSet` | Shoulder set | -1..1 | rounded / pulled back | ±5° | | clavicle_l/r rotation yaw |
| `Body.StanceWidth` | Stance width | -1..1 | narrow / wide feet | ±4° | | thigh_l/r rotation roll |

The idle stance itself is a part (slot `Stance`, section 4.1). Posture sliders are offsets on top of
it.

### 3.2 Face

Every face slider lists the T25 morph target name. Until T25 lands, a few also drive head-bone
offsets so the jaw and chin respond on the mannequin; the Player lane decides which.

**Section `Shape`**

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Sculpt | Morph |
|---|---|---|---|---|---|---|---|
| `Face.Width` | Face width | -1..1 | narrow / wide | morph 1 (≈ ±8%) | | - | `Face_Width` |
| `Face.Length` | Face length | -1..1 | short / long | morph 1 (≈ ±7%) | | `Chin / V` | `Face_Length` |
| `Face.Roundness` | Roundness | -1..1 | angular / round | morph 1 | | - | `Face_Round` |
| `Face.TempleWidth` | Temples | -1..1 | narrow / wide | morph 0.8 | | `Forehead / H` | `Temple_Width` |
| `Face.CheekFullness` | Cheek fullness | -1..1 | slim / full | morph 1 | | `Cheeks / V` | `Cheek_Full` |
| `Face.CheekboneHeight` | Cheekbone height | -1..1 | low / high | morph 1 | | - | `Cheekbone_Height` |
| `Face.CheekboneWidth` | Cheekbone width | -1..1 | narrow / wide | morph 1 | | `Cheeks / H` | `Cheekbone_Width` |
| `Face.CheekboneProminence` | Cheekbones | -1..1 | soft / defined | morph 0.8 | | - | `Cheekbone_Prom` |
| `Face.CheekHollow` | Cheek hollow | 0..1 | none / slight hollow | morph 0.5 (never gaunt) | | - | `Cheek_Hollow` |
| `Face.JawWidth` | Jaw width | -1..1 | narrow / wide | morph 1 | | `Jaw / H` | `Jaw_Width` |
| `Face.JawAngle` | Jaw angle | -1..1 | soft / squared corner | morph 1 | | - | `Jaw_Angle` |
| `Face.JawHeight` | Jaw corner height | -1..1 | low / high corner | morph 1 | | `Jaw / V` | `Jaw_Height` |
| `Face.JawDepth` | Jaw depth | -1..1 | set back / forward | morph 0.8 | | - | `Jaw_Depth` |
| `Face.ChinWidth` | Chin width | -1..1 | narrow / wide | morph 1 | | `Chin / H` | `Chin_Width` |
| `Face.ChinLength` | Chin length | -1..1 | short / long | morph 1 | | - | `Chin_Length` |
| `Face.ChinDepth` | Chin depth | -1..1 | receding / forward | morph 0.8 | | - | `Chin_Depth` |
| `Face.ChinPoint` | Chin shape | -1..1 | round / pointed | morph 1 | | - | `Chin_Point` |
| `Face.ChinCleft` | Chin cleft | 0..1 | none / soft dimple | morph 0.6 | | - | `Chin_Cleft` |
| `Face.CheekDimples` | Dimples | 0..1 | none / dimples when smiling | morph 1 (only visible in smile expressions) | | - | `Cheek_Dimple` |

**Section `Forehead` (Forehead & brow ridge)**

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Sculpt | Morph |
|---|---|---|---|---|---|---|---|
| `Forehead.Height` | Forehead height | -1..1 | low / high | morph 1 | | `Forehead / V` | `Forehead_Height` |
| `Forehead.Width` | Forehead width | -1..1 | narrow / wide | morph 0.8 | | - | `Forehead_Width` |
| `Forehead.Slope` | Forehead slope | -1..1 | upright / sloped | morph 0.8 | | - | `Forehead_Slope` |
| `Forehead.Roundness` | Forehead roundness | -1..1 | flat / rounded | morph 0.8 | | - | `Forehead_Round` |
| `Forehead.BrowRidge` | Brow ridge | -1..1 | smooth / pronounced | morph 0.7 | | - | `BrowRidge_Prom` |

**Section `Eyes`** (shape; colour is the Eyes category)

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Sculpt | Morph |
|---|---|---|---|---|---|---|---|
| `Eyes.SizeL` | Eye size, left | -1..1 | smaller / larger | morph 1 (≈ -10% / +15%) | `Eyes.SizeR` | `EyeL / V` | `Eye_Size_L` |
| `Eyes.SizeR` | Eye size, right | -1..1 | smaller / larger | as left | `Eyes.SizeL` | `EyeR / V` | `Eye_Size_R` |
| `Eyes.Spacing` | Eye spacing | -1..1 | close / wide | morph 1 (≈ ±4 mm per eye) | | - | `Eye_Spacing` |
| `Eyes.HeightL` | Eye height, left | -1..1 | lower / higher | morph 1 | `Eyes.HeightR` | - | `Eye_Height_L` |
| `Eyes.HeightR` | Eye height, right | -1..1 | lower / higher | morph 1 | `Eyes.HeightL` | - | `Eye_Height_R` |
| `Eyes.TiltL` | Eye tilt, left | -1..1 | outer corner down / up | morph 1 (≈ ±12°) | `Eyes.TiltR` | - | `Eye_Tilt_L` |
| `Eyes.TiltR` | Eye tilt, right | -1..1 | outer corner down / up | as left | `Eyes.TiltL` | - | `Eye_Tilt_R` |
| `Eyes.Depth` | Eye depth | -1..1 | prominent / deep-set | morph 0.8 | | - | `Eye_Depth` |
| `Eyes.Roundness` | Eye shape | -1..1 | almond / round | morph 1 | | - | `Eye_Round` |
| `Eyes.UpperLidL` | Upper lid, left | -1..1 | heavy / open | morph 1 | `Eyes.UpperLidR` | - | `Lid_Upper_L` |
| `Eyes.UpperLidR` | Upper lid, right | -1..1 | heavy / open | morph 1 | `Eyes.UpperLidL` | - | `Lid_Upper_R` |
| `Eyes.LidCrease` | Lid crease | -1..1 | monolid / deep double lid | morph 1 | | - | `Lid_Crease` |
| `Eyes.LowerLidL` | Lower lid, left | -1..1 | low curve / high, straight | morph 1 | `Eyes.LowerLidR` | - | `Lid_Lower_L` |
| `Eyes.LowerLidR` | Lower lid, right | -1..1 | low curve / high, straight | morph 1 | `Eyes.LowerLidL` | - | `Lid_Lower_R` |
| `Eyes.InnerCornerL` | Inner corner, left | -1..1 | rounded, low / pointed, high | morph 1 | `Eyes.InnerCornerR` | - | `Eye_Inner_L` |
| `Eyes.InnerCornerR` | Inner corner, right | -1..1 | rounded, low / pointed, high | morph 1 | `Eyes.InnerCornerL` | - | `Eye_Inner_R` |
| `Eyes.OuterCornerL` | Outer corner, left | -1..1 | rounded / sharp, extended | morph 1 | `Eyes.OuterCornerR` | `EyeL / H` | `Eye_Outer_L` |
| `Eyes.OuterCornerR` | Outer corner, right | -1..1 | rounded / sharp, extended | morph 1 | `Eyes.OuterCornerL` | `EyeR / H` | `Eye_Outer_R` |
| `Eyes.UnderEyeFullness` | Under-eye fullness | 0..1 | flat / soft pillow under the eye | morph 0.7 | | - | `UnderEye_Full` |
| `Eyes.IrisSize` | Iris size | -1..1 | smaller / larger | material ±12% | | - | material `IrisScale` |
| `Eyes.PupilSize` | Pupil size | -1..1 | small / large | material ±25% | | - | material `PupilScale` |

**Section `Brows`** (placement and shape on the face; the brow *part* and colour are in Hair)

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Sculpt | Morph |
|---|---|---|---|---|---|---|---|
| `Brows.HeightL` | Brow height, left | -1..1 | low / high | morph 1 | `Brows.HeightR` | `BrowL / V` | `Brow_Height_L` |
| `Brows.HeightR` | Brow height, right | -1..1 | low / high | morph 1 | `Brows.HeightL` | `BrowR / V` | `Brow_Height_R` |
| `Brows.TiltL` | Brow tilt, left | -1..1 | outer end down / up | morph 1 (≈ ±10°) | `Brows.TiltR` | `BrowL / H` | `Brow_Tilt_L` |
| `Brows.TiltR` | Brow tilt, right | -1..1 | outer end down / up | as left | `Brows.TiltL` | `BrowR / H` | `Brow_Tilt_R` |
| `Brows.ArchL` | Brow arch, left | -1..1 | flat / high arch | morph 1 | `Brows.ArchR` | - | `Brow_Arch_L` |
| `Brows.ArchR` | Brow arch, right | -1..1 | flat / high arch | morph 1 | `Brows.ArchL` | - | `Brow_Arch_R` |
| `Brows.Thickness` | Brow thickness | -1..1 | fine / thick | material ±40% mask width | | - | material `BrowThickness` |
| `Brows.Spacing` | Brow spacing | -1..1 | close / far apart | morph 0.8 | | - | `Brow_Spacing` |
| `Brows.Length` | Brow length | -1..1 | short / long tail | material ±25% | | - | material `BrowLength` |

**Section `Nose`**

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Sculpt | Morph |
|---|---|---|---|---|---|---|---|
| `Nose.BridgeHeight` | Bridge height | -1..1 | low, flat / high | morph 1 | | - | `NoseBridge_Height` |
| `Nose.BridgeWidth` | Bridge width | -1..1 | narrow / wide | morph 1 | | `Nose / H` | `NoseBridge_Width` |
| `Nose.BridgeCurve` | Bridge profile | -1..1 | scooped / arched | morph 0.8 | | - | `NoseBridge_Curve` |
| `Nose.Length` | Nose length | -1..1 | short / long | morph 1 | | - | `Nose_Length` |
| `Nose.Height` | Nose position | -1..1 | lower / higher | morph 0.8 | | `Nose / V` | `Nose_Height` |
| `Nose.Projection` | Projection | -1..1 | flat / prominent | morph 0.8 | | - | `Nose_Projection` |
| `Nose.TipSize` | Tip size | -1..1 | small / large | morph 1 | | - | `NoseTip_Size` |
| `Nose.TipLift` | Tip lift | -1..1 | down-turned / up-turned | morph 1 | | - | `NoseTip_Lift` |
| `Nose.TipShape` | Tip shape | -1..1 | round, button / defined, pointed | morph 1 | | - | `NoseTip_Shape` |
| `Nose.NostrilWidth` | Nostril width | -1..1 | narrow / wide | morph 1 | | - | `Nostril_Width` |
| `Nose.NostrilFlare` | Nostril flare | -1..1 | tucked / flared | morph 0.8 | | - | `Nostril_Flare` |
| `Nose.NostrilHeight` | Nostril height | -1..1 | low / high wings | morph 0.7 | | - | `Nostril_Height` |
| `Nose.Bend` | Bend | -1..1 | bends left / right | morph 0.4 (a hint, never broken) | | - | `Nose_Bend` |

**Section `Mouth`**

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Sculpt | Morph |
|---|---|---|---|---|---|---|---|
| `Mouth.Width` | Mouth width | -1..1 | narrow / wide | morph 1 | | `Mouth / H` | `Mouth_Width` |
| `Mouth.Height` | Mouth position | -1..1 | lower / higher | morph 0.8 | | `Mouth / V` | `Mouth_Height` |
| `Mouth.Depth` | Mouth depth | -1..1 | set back / forward | morph 0.7 | | - | `Mouth_Depth` |
| `Mouth.UpperLipFullness` | Upper lip | -1..1 | thin / full | morph 1 | | - | `LipUpper_Full` |
| `Mouth.LowerLipFullness` | Lower lip | -1..1 | thin / full | morph 1 | | - | `LipLower_Full` |
| `Mouth.CupidsBow` | Cupid's bow | -1..1 | soft / sharp | morph 1 | | - | `Lip_CupidsBow` |
| `Mouth.LipOffset` | Bite | -1..1 | lower lip forward / upper lip forward | morph 0.5 | | - | `Lip_Offset` |
| `Mouth.CornerLiftL` | Corner, left | -1..1 | down / up | morph 1 (a resting hint, not a grin) | `Mouth.CornerLiftR` | - | `MouthCorner_L` |
| `Mouth.CornerLiftR` | Corner, right | -1..1 | down / up | as left | `Mouth.CornerLiftL` | - | `MouthCorner_R` |
| `Mouth.PhiltrumDepth` | Philtrum | -1..1 | flat / defined groove | morph 0.7 | | - | `Philtrum_Depth` |
| `Mouth.PhiltrumLength` | Philtrum length | -1..1 | short / long | morph 0.8 | | - | `Philtrum_Length` |

**Section `Ears`**

| Id | Name | Range | Does (low / high) | Limit at ends | Mirror | Sculpt | People | Morph |
|---|---|---|---|---|---|---|---|---|
| `Ears.SizeL` | Ear size, left | -1..1 | small / large | morph 1 (≈ ±15%) | `Ears.SizeR` | `EarL / V` | | `Ear_Size_L` |
| `Ears.SizeR` | Ear size, right | -1..1 | small / large | as left | `Ears.SizeL` | `EarR / V` | | `Ear_Size_R` |
| `Ears.AngleL` | Ear angle, left | -1..1 | flat to head / stick out | morph 1 | `Ears.AngleR` | `EarL / H` | | `Ear_Angle_L` |
| `Ears.AngleR` | Ear angle, right | -1..1 | flat to head / stick out | as left | `Ears.AngleL` | `EarR / H` | | `Ear_Angle_R` |
| `Ears.Height` | Ear height | -1..1 | low / high on head | morph 0.7 | | - | | `Ear_Height` |
| `Ears.Lobe` | Ear lobe | -1..1 | attached, small / free, large | morph 1 | | - | | `Ear_Lobe` |
| `Ears.TipL` | Ear tip, left | 0..1 | round / slight point | morph 1 | `Ears.TipR` | - | | `Ear_Tip_L` |
| `Ears.TipR` | Ear tip, right | 0..1 | round / slight point | as left | `Ears.TipL` | - | | `Ear_Tip_R` |
| `Ears.PointL` | Point length, left | 0..1 | short / long point | morph 1 (up to +6 cm tip) | `Ears.PointR` | - | MoonlitElf, Deepkin | `Ear_Point_L` |
| `Ears.PointR` | Point length, right | 0..1 | short / long point | as left | `Ears.PointL` | - | MoonlitElf, Deepkin | `Ear_Point_R` |
| `Ears.PointAngleL` | Point angle, left | -1..1 | swept back / upright | morph 1 (≈ ±25°) | `Ears.PointAngleR` | - | MoonlitElf, Deepkin | `Ear_PointAngle_L` |
| `Ears.PointAngleR` | Point angle, right | -1..1 | swept back / upright | as left | `Ears.PointAngleL` | - | MoonlitElf, Deepkin | `Ear_PointAngle_R` |
| `Ears.DroopL` | Droop, left | 0..1 | none / tip droops | morph 0.6 | `Ears.DroopR` | - | MoonlitElf | `Ear_Droop_L` |
| `Ears.DroopR` | Droop, right | 0..1 | none / tip droops | as left | `Ears.DroopL` | - | MoonlitElf | `Ear_Droop_R` |
| `Ears.FinSpreadL` | Fin spread, left | 0..1 | folded / fanned fin-ear | morph 1 | `Ears.FinSpreadR` | - | Deepkin | `Ear_Fin_L` |
| `Ears.FinSpreadR` | Fin spread, right | 0..1 | folded / fanned fin-ear | as left | `Ears.FinSpreadL` | - | Deepkin | `Ear_Fin_R` |

### 3.3 Eyes (colour and detail)

| Id | Name | Section | Range | Does (low / high) | Limit | People | Target |
|---|---|---|---|---|---|---|---|
| `Lashes.Length` | Lash length | `Detail` | -1..1 | short / long | morph 1 on the lash card | | morph `Lash_Length` |
| `Lashes.Curl` | Lash curl | `Detail` | -1..1 | straight / curled | morph 1 | | morph `Lash_Curl` |
| `Iris.LimbalRing` | Iris ring | `Detail` | 0..1 | none / dark ring round the iris | material 0.8 | | material `LimbalRing` |
| `Iris.Catchlight` | Catchlight | `Detail` | 0..1 | small / large painted highlight | material 1 | | material `Catchlight` |
| `Eyes.GlowStrength` | Eye glow | `Detail` | 0..1 | none / soft moonlit glow | material 1, never blooms past the eye | MoonlitElf | material `EyeGlow` |
| `Eyes.ShineStrength` | Night shine | `Detail` | 0..1 | none / eyes catch the light in the dark | material 1 | Deepkin | material `EyeShine` |

Iris colour, sclera tint, pupil shape, iris pattern and lash part are in sections 4 and 5. The
**heterochromia toggle** is stored as part scalar `Eyes.Heterochromia` (0 or 1). When it is 0, the
UI writes the left iris pick into `Eyes.IrisR` too, and the right iris swatch row is hidden.

### 3.4 Skin

| Id | Name | Section | Range | Does (low / high) | Limit | People | Target |
|---|---|---|---|---|---|---|---|
| `Skin.Undertone` | Undertone | `Tone` | -1..1 | cooler / warmer | shifts hue ±0.02 inside the band | | material `SkinUndertone` |
| `Skin.Rosiness` | Rosiness | `Tone` | 0..1 | none / rosy cheeks, nose tip, knuckles | material 0.8 | | material `Rosiness` |
| `Skin.Sheen` | Sheen | `Tone` | -1..1 | matte / soft dewy highlight | material 0.6 | | material `SkinSheen` |
| `Skin.AgeLines` | Age lines | `Details` | 0..1 | none / soft painted lines (laugh lines, crow's feet, brow) | material 0.6 | | material `AgeLines` |
| `Skin.Moonglow` | Moonglow | `Tone` | 0..1 | none / skin softly luminous in moonlight and mist | material 0.5, night and mist only | MoonlitElf | material `SkinMoonglow` |

### 3.5 Voice

| Id | Name | Section | Range | Does | Limit | Target |
|---|---|---|---|---|---|---|
| `Voice.Pitch` | Voice pitch | `Voice` | -1..1 | lower / higher | ±2 semitones on the chosen voice | material-free; read by the audio system (`MaterialScalar` placeholder, name `VoicePitch`) |

### 3.6 Hair, Makeup and Outfit

These categories have no sliders: their amounts depend on the chosen part, so they are part scalars
(section 3.7).

### 3.7 Part scalars

Stored in `FLyrisAppearance.PartScalars`. Missing key means the default.

| Key | Range | Default | What it does |
|---|---|---|---|
| `Hair.Length` | -1..1 | 0 | Shorter / longer, within what the style allows (morph on the hair mesh) |
| `Hair.Volume` | -1..1 | 0 | Flatter / fuller |
| `Hair.GradientStart` | 0..1 | 0.7 | Where the root colour starts fading to the tip colour (1 = no gradient) |
| `Hair.GradientSoftness` | 0..1 | 0.5 | Hard dip-dye line / soft blend |
| `Hair.HighlightAmount` | 0..1 | 0 | How many painted highlight streaks |
| `Hair.Shine` | 0..1 | 0.5 | Painted shine band strength (matte to glossy storybook ribbon) |
| `Brows.MatchHair` | 0 or 1 | 1 | Brows follow `Hair.Root`; when 0, `Hair.Brows` is used |
| `Brows.Density` | 0..1 | 0.7 | Sparse / dense brow |
| `FacialHair.Length` | -1..1 | 0 | Shorter / longer |
| `FacialHair.MatchHair` | 0 or 1 | 1 | Facial hair follows `Hair.Root` |
| `Eyes.Heterochromia` | 0 or 1 | 0 | Different iris colour per eye |
| `Freckles.Density` | 0..1 | 0.5 | How many freckles in the chosen set |
| `Freckles.Opacity` | 0..1 | 0.6 | How strong they read |
| `Moles.Opacity` | 0..1 | 0.8 | |
| `Scars.Opacity` | 0..1 | 0.6 | Max 0.8 in the UI: scars are healed and soft |
| `Markings.Opacity` | 0..1 | 0.8 | |
| `Markings.Glow` | 0..1 | 0.5 | MoonlitElf sigils glow at night and in mist |
| `Markings.Shimmer` | 0..1 | 0.5 | Deepkin scale patches shimmer, more when wet |
| `Makeup.Eyeshadow.Opacity` | 0..1 | 0.6 | |
| `Makeup.Eyeliner.Opacity` | 0..1 | 0.8 | |
| `Makeup.Lips.Opacity` | 0..1 | 0.5 | |
| `Makeup.Lips.Gloss` | 0..1 | 0.2 | Matte / glossy painted highlight |
| `Makeup.Blush.Opacity` | 0..1 | 0.5 | |
| `Makeup.FacePaint.Opacity` | 0..1 | 0.9 | |
| `Outfit.Wear` | 0..1 | 0.3 | Crisp and new / well-travelled (patches, faded hems) |

That is 25 part scalars.

### 3.8 Slider totals

| Category | Sections | Sliders |
|---|---|---|
| Body | Frame 2, Proportions 16, Build 6, HandsFeet 4, Posture 4 | 32 |
| Face | Shape 19, Forehead 5, Eyes 21, Brows 9, Nose 13, Mouth 11, Ears 16 | 94 |
| Eyes | Detail 6 | 6 |
| Skin | Tone 4, Details 1 | 5 |
| Voice | Voice 1 | 1 |
| **Total** | | **138** |

Left/right pairs: Eyes 7, Brows 3, Mouth 1, Ears 7 = 18 pairs (36 sliders). Sculptable sliders: 24
across 12 regions.

---

## 4. Appearance catalog: parts

Every part works on both frames. `People` restrictions are listed; empty means all. Parts marked
"(mask)" are decal-style and use `FLyrisPartDef.Mask` on the skin or eye material rather than a
mesh.

### 4.1 Slots

| Slot | Category / section | Optional? | Default | Attach | Count |
|---|---|---|---|---|---|
| `Stance` | Body / Posture | no | `Stance.Easy` | anim pose | 7 |
| `Hair` | Hair / Style | no (`Hair.Bare` is a part) | People preset | skeletal, leader pose | 27 |
| `HairAccessory` | Hair / Accessories | yes | none | socket `head` | 10 |
| `Brows` | Hair / Brows | yes | `Brows.Natural` | mask | 12 |
| `FacialHair` | Hair / FacialHair | yes | none | skeletal + mask (stubble) | 10 |
| `Lashes` | Eyes / Detail | yes | `Lashes.Natural` | skeletal (lash cards) | 6 |
| `PupilShape` | Eyes / Colour | no | `PupilShape.Round` | mask | 6 |
| `IrisPattern` | Eyes / Colour | no | `IrisPattern.Painted` | mask | 8 |
| `Freckles` | Skin / Details | yes | none | mask | 8 |
| `Moles` | Skin / Details | yes | none | mask | 6 |
| `Scars` | Skin / Details | yes | none | mask | 8 |
| `Markings` | Skin / Markings | yes | none | mask (+ emissive / shimmer mask) | 16 |
| `Eyeshadow` | Makeup / Eyes | yes | none | mask | 7 |
| `Eyeliner` | Makeup / Eyes | yes | none | mask | 7 |
| `Lips` | Makeup / Lips | yes | none (natural lips) | mask | 5 |
| `Blush` | Makeup / Cheeks | yes | none | mask | 5 |
| `FacePaint` | Makeup / FacePaint | yes | none | mask | 9 |
| `Outfit` | Outfit / Outfit | no | the chosen path's outfit | skeletal, leader pose | 8 |
| `Layer` | Outfit / Layer | yes | none | skeletal, leader pose | 7 |
| `Voice` | Voice / Voice | no | `Voice.Warm1` | audio set | 8 |
| `Expression` | Voice / Expression | no | `Expression.Calm` | anim pose (face) | 6 |
| `Lantern` | Lantern (step 5) | no | `Lantern.Ships` | static mesh, socket `hand_r` | 9 |

**Total: 22 slots, 195 parts** (counting each listed part, not counting `None`).

### 4.2 Hair (27)

| Id | Name | Length | Notes | People |
|---|---|---|---|---|
| `Hair.DeckhandCrop` | Deckhand crop | short | Neat short cut, tapered sides | |
| `Hair.WindTossed` | Wind-tossed | short | Messy, swept by sea wind | |
| `Hair.HarborUndercut` | Harbor undercut | short | Shaved sides, longer top falling to one side | |
| `Hair.Sparrow` | Sparrow | short | Soft pixie cut with wispy fringe | |
| `Hair.TideCurls` | Tide curls | short | Short tight curls | |
| `Hair.CoilCrown` | Coil crown | short-medium | Rounded crown of coils (afro-textured) | |
| `Hair.CloseShave` | Close shave | very short | Buzz cut, painted texture | |
| `Hair.Bare` | Bare | none | No hair | |
| `Hair.Crest` | Crest | short | Upswept central crest, sides short | |
| `Hair.LamplighterBob` | Lamplighter bob | chin | Straight blunt bob | |
| `Hair.WaveBob` | Wave bob | chin | Wavy bob, side part | |
| `Hair.CurtainFringe` | Curtain fringe | medium | Parted fringe, layers to the jaw | |
| `Hair.Shoreline` | Shoreline | shoulder | Loose, shoulder length, slight wave | |
| `Hair.HalfMoon` | Half-moon | shoulder | Half up, half down, tied back | |
| `Hair.BellTopknot` | Bell-tower topknot | tied | Topknot with loose sides | |
| `Hair.ScholarsBun` | Scholar's bun | tied | Low messy bun (pairs with the pencil accessory) | |
| `Hair.TwinMoons` | Twin moons | tied | Two buns | |
| `Hair.SailorsTail` | Sailor's tail | long, tied | Low ponytail with a wrapped tie | |
| `Hair.GullTail` | Gull tail | long, tied | High ponytail | |
| `Hair.RopeBraid` | Rope braid | long, tied | One thick braid over the shoulder | |
| `Hair.GarlandCrown` | Garland crown | tied | Braid wrapped round the head | |
| `Hair.NetMenderBraids` | Net-mender's braids | long | Many thin braids, tied loosely back | |
| `Hair.DriftwoodLocs` | Driftwood locs | long | Locs, can be gathered | |
| `Hair.FallingWater` | Falling water | very long | Long, straight, loose | |
| `Hair.RollingSwell` | Rolling swell | very long | Long, big soft waves | |
| `Hair.Moonfall` | Moonfall | very long | Long fine hair with a thin plait framing each ear, cut to show long ears | MoonlitElf |
| `Hair.KelpTresses` | Kelp tresses | long | Ribbon-like, softly flat strands with gaps for fin-ears; look slightly wet | Deepkin |

That is 27 hairstyles listed; `Hair.Bare` plus 26 styles with hair. Every style is available to
every People except the two marked; long-ear Peoples get ear cut-outs on all styles (mesh variant
chosen automatically, not a separate part).

### 4.3 Hair accessories (10)

`HairAccessory.Ribbon` (ribbon tie), `.Bandana` (sailor's bandana), `.Pencil` (pencil through the bun),
`.ShellClips` (shell clips), `.GullFeather` (feather tucked behind the ear), `.FlowerCrown` (meadow
flower crown), `.WoodComb` (carved comb), `.BeadStrings` (bead strings in braids), `.LampPin`
(tiny brass lamp hairpin), `.SeaGlassBand` (circlet of sea glass). Colour: `Hair.Accessory`.

### 4.4 Brows (12)

`Brows.Natural`, `.Straight`, `.SoftArch`, `.HighArch`, `.Thick`, `.Feathered`, `.Fine`, `.Bushy`,
`.Rounded`, `.Split` (with a small scar gap), `.MoonWisp` (long, tapering upward, **MoonlitElf**),
`.ScaleRidge` (a line of tiny scales instead of hair, **Deepkin**).

### 4.5 Facial hair (10)

Available on both frames and every People.

`FacialHair.Stubble` (painted shadow), `.ShortBeard`, `.FullBeard`, `.BraidedBeard`, `.Moustache`,
`.Goatee`, `.Chinstrap` (sailor's chinstrap), `.MuttonChops`, `.ArchivistBeard` (long, tied with a
ring), `.Barbels` (two soft whisker-tendrils from the upper lip, **Deepkin**).

### 4.6 Eyes: lashes, pupils, iris patterns

| Slot | Parts | People |
|---|---|---|
| `Lashes` (6) | `Lashes.Soft`, `.Natural`, `.Full`, `.Fluttery`, `.Storybook` (few bold painted lashes), `.LowerAccent` | |
| `PupilShape` (6) | `PupilShape.Round`, `.SoftOval` | all |
| | `PupilShape.Crescent`, `.Starpoint` (a tiny four-point star) | MoonlitElf |
| | `PupilShape.Slit`, `.Cuttle` (soft W-shape, like a cuttlefish) | Deepkin |
| `IrisPattern` (8) | `IrisPattern.Painted` (flat painterly), `.Sunburst`, `.Ringed`, `.Flecked`, `.TwoTone` (inner/outer), `.Starfield` | all |
| | `IrisPattern.Moonstone` (milky crystal sheen) | MoonlitElf |
| | `IrisPattern.Tidal` (swirled, like moving water) | Deepkin |

### 4.7 Skin: freckles, moles, scars (masks)

| Slot | Parts |
|---|---|
| `Freckles` (8) | `Freckles.NoseDust` (light dusting on the nose), `.SunKissed` (cheeks and nose), `.FullFace`, `.FaceShoulders`, `.Sparse` (a few), `.Constellation` (freckles in star patterns), `.Speckled` (larger soft speckles), `.Hands` (backs of hands and forearms) |
| `Moles` (6) | `Moles.BeautyMark` (upper cheek), `.UnderEye`, `.LipCorner`, `.Chin`, `.Neck`, `.Scattered` (three or four small ones) |
| `Scars` (8) | `Scars.BrowNick`, `.CheekLine`, `.LipSplit`, `.NoseBridge`, `.JawLine`, `.EarNotch`, `.AcrossEye` (faded line over the eye; the eye itself is unharmed), `.RopeBurn` (palm and wrist) |

Freckle colour: `Skin.Freckles`. Moles and scars are tinted from the skin tone automatically (no
channel).

### 4.8 Markings (16, People-specific)

| Id | Name | People | Look |
|---|---|---|---|
| `Markings.CrescentBrow` | Crescent brow | MoonlitElf | A thin crescent above one brow |
| `Markings.WaningCheeks` | Waning cheeks | MoonlitElf | Moon phases under each eye |
| `Markings.StarTrail` | Star trail | MoonlitElf | Dots from temple down the cheek |
| `Markings.FullMoon` | Full moon | MoonlitElf | A pale circle on the forehead |
| `Markings.PhaseChain` | Phase chain | MoonlitElf | Moon phases along the collarbone |
| `Markings.SilverVeins` | Silver veins | MoonlitElf | Fine silver lines on the backs of the hands |
| `Markings.TempleScales` | Temple scales | Deepkin | Scale patch at the temples |
| `Markings.CheekScales` | Cheek scales | Deepkin | Scales along the cheekbones |
| `Markings.GillLines` | Gill lines | Deepkin | Three soft lines on each side of the neck |
| `Markings.ShoulderScales` | Shoulder scales | Deepkin | Scales over the shoulders |
| `Markings.SpineRidge` | Spine ridge | Deepkin | Scale line down the back of the neck |
| `Markings.FinEdge` | Fin edge | Deepkin | Shimmering edge on the ears and forearms |
| `Markings.RopeInk` | Rope ink | Human | Rope tattoo around a wrist |
| `Markings.CompassInk` | Compass ink | Human | Compass rose on the back of a hand |
| `Markings.WaveInk` | Wave ink | Human | Wave line across the collarbone |
| `Markings.LampInk` | Lamp ink | Human | Small lamp behind the ear |

Colour: `Skin.Markings` (and `Skin.MarkingShimmer` for Deepkin). Humans' ink ignores `Markings.Glow`
and `Markings.Shimmer`.

### 4.9 Makeup (masks)

All makeup is painted, flat and soft-edged, like a storybook illustration.

| Slot | Parts | Colour channel |
|---|---|---|
| `Eyeshadow` (7) | `Eyeshadow.Wash` (lid), `.Smoky`, `.WingShadow`, `.UnderGlow` (lower lid), `.InnerShine`, `.TwoTone`, `.Crease` | `Makeup.Eyeshadow` |
| `Eyeliner` (7) | `Eyeliner.Tightline`, `.ClassicWing`, `.CatFlick`, `.LowerLine`, `.Kohl`, `.Dotted` (painted dots), `.DoubleWing` | `Makeup.Eyeliner` |
| `Lips` (5) | `Lips.Tint`, `.Full`, `.Ombre`, `.CentreStain`, `.TwoTone` | `Makeup.Lips` |
| `Blush` (5) | `Blush.Apples`, `.Sweep`, `.SunAcrossNose`, `.UnderEye`, `.Temple` | `Makeup.Blush` |
| `FacePaint` (9) | `FacePaint.LamplighterStripe` (a gold stripe across the nose), `.TideDots`, `.FestivalSun`, `.MoonCrescent`, `.LeafVine`, `.Constellation`, `.MaskBand` (band across the eyes), `.SeaFoam` (white freckle-dots), `.BeaconLines` (lines from the eye corners) | `Makeup.FacePaint` |

### 4.10 Outfits (8) and layers (7)

Each path has a starting outfit, picked by default at step 3 when the player has not chosen one;
any outfit can be worn with any path.

| Id | Name | Default for path | Look |
|---|---|---|---|
| `Outfit.DeckhandCoat` | Deckhand's coat | Seafarer | Short wool coat, rolled sleeves, sea boots |
| `Outfit.WandererLayers` | Wanderer's layers | Wanderer | Tunic, wrapped leggings, belted pouches |
| `Outfit.GrowerSmock` | Grower's smock | Grower | Smock with deep pockets, rolled trousers, clogs |
| `Outfit.MakerApron` | Maker's apron | Maker | Shirt, leather apron with tool loops |
| `Outfit.ScholarCoat` | Scholar's coat | Scholar | Long coat with many pockets, a satchel |
| `Outfit.TraderWaistcoat` | Trader's waistcoat | Trader | Waistcoat, neat shirt, coin purse |
| `Outfit.DelverLeathers` | Delver's leathers | Delver | Padded jacket, knee pads, lamp hook on the belt |
| `Outfit.PlainTraveller` | Plain traveller | none | Simple shirt and trousers, a blank canvas |

Layers: `Layer.WoolScarf`, `.RainCloak`, `.ShortCape`, `.Shawl`, `.HoodedCloak`, `.Neckerchief`,
`.Poncho`. Colour: `Outfit.Layer`.

### 4.11 Stance (7), voice (8), expression (6)

- **Stance:** `Stance.Easy`, `.Upright`, `.ArmsFolded`, `.HandOnHip`, `.Shy` (weight on one foot,
  hands together), `.SeaLegs` (wide, rolling), `.Bookish` (one hand holding a satchel strap).
- **Voice** (placeholder ids until voice sets exist): `Voice.Bright1`, `.Bright2`, `.Warm1`,
  `.Warm2`, `.Low1`, `.Low2`, `.Soft1`, `.Soft2`. Not tied to frame.
- **Expression** (resting face in the world): `Expression.Calm`, `.Bright`, `.Wry`, `.Shy`,
  `.Dreamy`, `.Determined`.

### 4.12 Lanterns (9)

The lantern shape is `FLyrisCharacterProfile.LanternShape` and its glass is `LanternGlass`. The
shapes also live in the catalog as parts in slot `Lantern` so they have meshes.

| Id | Name | Look |
|---|---|---|
| `Lantern.Ships` | Ship's lantern | Classic brass and glass, ring handle |
| `Lantern.StormHex` | Storm lantern | Six-sided, caged glass |
| `Lantern.MoonGlobe` | Moon globe | Round glass globe in a thin frame |
| `Lantern.HangingBell` | Hanging bell | Bell-shaped, rings softly when swung |
| `Lantern.Lighthouse` | Little lighthouse | A tiny lighthouse with a turning shade |
| `Lantern.Shell` | Shell lantern | Glass set in a large spiral shell |
| `Lantern.BrassStar` | Brass star | Star-pierced brass, throws star dots |
| `Lantern.Reading` | Reading lantern | Tall, narrow, with a hood to aim the light |
| `Lantern.Seedpod` | Seedpod | Woven-reed pod round a glass heart |

---

## 5. Appearance catalog: colour channels

Every colour is a swatch from a curated band, plus a limited hue shift and value shift
(`FLyrisColorPick`). Hue shift is a fraction of the colour wheel; value shift is a fraction of
brightness. `ULyrisAppearanceLibrary::ResolveColor` clamps both.

Where a swatch matches a colour in the Harbor `PALETTE` it is named after it. The rest are new
character colours, chosen to sit with that palette: warm, saturated, never neon, never grey-dead.
These new character colours are approved (see `design/DECISIONS.md`).

### 5.1 Channel list

| Id | Category | Display name | Swatches | Max hue shift | Max value shift | Material param | People |
|---|---|---|---|---|---|---|---|
| `Skin.ToneHuman` | Skin | Skin tone | 12 | 0.03 | 0.10 | `SkinTone` | Human |
| `Skin.ToneElf` | Skin | Skin tone | 11 | 0.04 | 0.10 | `SkinTone` | MoonlitElf |
| `Skin.ToneDeepkin` | Skin | Skin tone | 11 | 0.05 | 0.10 | `SkinTone` | Deepkin |
| `Skin.Rosiness` | Skin | Rosiness | 6 | 0.04 | 0.10 | `RosinessColor` | |
| `Skin.Freckles` | Skin | Freckles | 8 | 0.04 | 0.15 | `FreckleColor` | |
| `Skin.Markings` | Skin | Markings | 10 | 0.06 | 0.15 | `MarkingColor` | |
| `Skin.MarkingShimmer` | Skin | Shimmer | 6 | 0.08 | 0.10 | `MarkingShimmerColor` | Deepkin |
| `Eyes.IrisL` | Eyes | Iris (left) | 18 | 0.08 | 0.20 | `IrisColorL` | |
| `Eyes.IrisR` | Eyes | Iris (right) | 18 | 0.08 | 0.20 | `IrisColorR` | |
| `Eyes.Sclera` | Eyes | Eye whites | 4 | 0.02 | 0.08 | `ScleraColor` | Human, MoonlitElf |
| `Eyes.ScleraDeepkin` | Eyes | Eye whites | 5 | 0.03 | 0.10 | `ScleraColor` | Deepkin |
| `Eyes.Glow` | Eyes | Eye glow | 5 | 0.06 | 0.10 | `EyeGlowColor` | MoonlitElf |
| `Eyes.Shine` | Eyes | Night shine | 4 | 0.06 | 0.10 | `EyeShineColor` | Deepkin |
| `Hair.Root` | Hair | Hair colour | 20 | 0.06 | 0.20 | `HairRoot` | |
| `Hair.Tip` | Hair | Tip colour | 20 | 0.06 | 0.20 | `HairTip` | |
| `Hair.Highlight` | Hair | Highlights | 20 | 0.06 | 0.20 | `HairHighlight` | |
| `Hair.Brows` | Hair | Brow colour | 20 | 0.06 | 0.20 | `BrowColor` | |
| `Hair.FacialHair` | Hair | Facial hair colour | 20 | 0.06 | 0.20 | `FacialHairColor` | |
| `Hair.Accessory` | Hair | Accessory | 12 | 0.05 | 0.15 | `AccessoryColor` | |
| `Makeup.Eyeshadow` | Makeup | Eyeshadow | 16 | 0.06 | 0.20 | `EyeshadowColor` | |
| `Makeup.Eyeliner` | Makeup | Eyeliner | 8 | 0.05 | 0.20 | `EyelinerColor` | |
| `Makeup.Lips` | Makeup | Lips | 12 | 0.05 | 0.20 | `LipColor` | |
| `Makeup.Blush` | Makeup | Blush | 8 | 0.04 | 0.15 | `BlushColor` | |
| `Makeup.FacePaint` | Makeup | Face paint | 12 | 0.06 | 0.15 | `FacePaintColor` | |
| `Outfit.Primary` | Outfit | Main cloth | 18 | 0.04 | 0.15 | `ClothPrimary` | |
| `Outfit.Secondary` | Outfit | Second cloth | 18 | 0.04 | 0.15 | `ClothSecondary` | |
| `Outfit.Trim` | Outfit | Trim | 10 | 0.03 | 0.10 | `ClothTrim` | |
| `Outfit.Layer` | Outfit | Cloak or scarf | 18 | 0.04 | 0.15 | `LayerColor` | |
| `Lantern.Glass` | Lantern | Lantern glass | 9 | 0.08 | 0.15 | `LanternGlass` | |

**Total: 29 channels, 359 swatches.** The three skin tone channels write the same material param; the UI shows only
the one for the current People, and changing People keeps each People's own pick so switching back
restores it. `Eyes.Sclera` and `Eyes.ScleraDeepkin` work the same way.

Channels that share a band (all hair channels; the three cloth channels and the layer) use the same
swatch list so the UI can offer "match hair" and "match main cloth" shortcuts.

### 5.2 Swatch bands

**Human skin (`Skin.ToneHuman`)**: very fair to very deep, all warm-leaning, slightly saturated.

| # | Name | Hex | # | Name | Hex |
|---|---|---|---|---|---|
| 0 | Shell | F6E3D3 | 6 | Amber | C98F62 |
| 1 | Porcelain | F1D5BF | 7 | Copper | B8784E |
| 2 | Peach | EDC6A8 | 8 | Chestnut | A0633F |
| 3 | Honey | E2B48C | 9 | Cocoa | 85502F |
| 4 | Sand-gold | D7A276 | 10 | Umber | 6E4128 |
| 5 | Wheat-brown | CF9A6E | 11 | Night oak | 4E2C1E |

**Moonlit elf skin (`Skin.ToneElf`)**: pale to dusk blue-lavender.

| # | Name | Hex | # | Name | Hex |
|---|---|---|---|---|---|
| 0 | Moonmilk | F2EEF4 | 6 | Dusk blue | A9B4DA |
| 1 | Pearl | E6E3F0 | 7 | Twilight | 9A9CCB |
| 2 | Rose moon | E8D2DC | 8 | Heather | 8E82B5 |
| 3 | Frost | D9DDF0 | 9 | Evening | 77709F |
| 4 | Lilac dawn | D4C8E6 | 10 | Nightfall | 5F5A87 |
| 5 | Wisteria | BFB0DA | | | |

**Deepkin skin (`Skin.ToneDeepkin`)**: sea-green to slate.

| # | Name | Hex | # | Name | Hex |
|---|---|---|---|---|---|
| 0 | Seafoam | CFE5DA | 6 | Deep teal | 4D7F7E |
| 1 | Pale shallows | B5DCD3 | 7 | Slate-green | 5C7472 |
| 2 | Kelp light | 9CC7B5 | 8 | Slate | 667385 |
| 3 | Sea glass | 86B8AA | 9 | Storm | 56616F |
| 4 | Tidepool | 6FA39A | 10 | Abyss | 3F4A5A |
| 5 | Verdigris | 5E9488 | | | |

**Rosiness (`Skin.Rosiness`)**: Peach E9A88A, Rose D98A7A, Berry B85A6A, Lavender rose C99AC4,
Coral E39A7E, Tide flush 5FA8A0.

**Freckles (`Skin.Freckles`)**: Sun brown A0633F, Rust B8784E, Deep brown 6E4128, Ginger C8643A
(Terracotta), Starlight E6E3F0, Moonglass 7AC0E6, Deep teal 4D7F7E, Slate 56616F.

**Markings (`Skin.Markings`)**: Moonglass 7AC0E6, Silver DDE3EC, Pearl E6E3F0, Gold E3AE45, Lilac
B49CD6, Shallows 7FD0D6, Verdigris 5E9488, Nacre E8E6DC, Ink blue 2F4E6B, Red ochre C8443A
(RedBand).

**Marking shimmer (`Skin.MarkingShimmer`)**: Shallows 7FD0D6, Pearl pink E8C8D4, Gold E3AE45,
Lilac B49CD6, Sea green 6FB3A0, Silver DDE3EC.

**Iris (`Eyes.IrisL`, `Eyes.IrisR`)**

| # | Name | Hex | # | Name | Hex | # | Name | Hex |
|---|---|---|---|---|---|---|---|---|
| 0 | Brown | 7A4A2A | 6 | Sea | 3F9A93 | 12 | Violet | 7D62B5 |
| 1 | Dark brown | 4A2A1C (DarkWood) | 7 | Shallows | 7FD0D6 | 13 | Rose | D07A8A |
| 2 | Honey | C98A3A | 8 | Moonglass | 7AC0E6 | 14 | Silver | C9D3DE |
| 3 | Amber | E3AE45 (Gold) | 9 | Cornflower | 5A86C8 | 15 | Pale gold | F0D58A |
| 4 | Hazel | 9A7A3E | 10 | Storm | 5F6E86 | 16 | Abyss teal | 2E6F73 |
| 5 | Leaf | 6E8A3A (Leaf) | 11 | Grey | 8C9096 | 17 | Ember | C8643A (Terracotta) |

**Eye whites (`Eyes.Sclera`)**: Warm white F7EEDC (Sail), Cream F1E9DC (Sand), Cool white EEF2F5,
Moon blue DCE6F2.
**Deepkin eye whites (`Eyes.ScleraDeepkin`)**: Cream F1E9DC, Pale green DDEBE2, Sea grey C3D1CF,
Dusk teal 4D6B6E, Deep slate 3A4552.

**Eye glow (`Eyes.Glow`)**: Moonglass 7AC0E6, Pale silver DDE8F5, Lilac C4B4F0, Starlight gold
F3DC8C, Mint B5F0DA.
**Night shine (`Eyes.Shine`)**: Shallows 7FD0D6, Green-gold C8D86A, Pearl E8E6DC, Amber E3AE45.

**Hair (all hair channels)**: 13 natural, 7 storybook.

| # | Name | Hex | # | Name | Hex |
|---|---|---|---|---|---|
| 0 | Flax | F2DFA7 | 10 | Ash | A7A2A0 |
| 1 | Wheat | E3C27E | 11 | Silver | D9D8DC |
| 2 | Honey blond | D4A55A | 12 | Snow | F3F0EA |
| 3 | Strawberry | D9895A | 13 | Moonglass | 7AC0E6 |
| 4 | Copper | B85A30 | 14 | Lavender | B49CD6 |
| 5 | Auburn | 8E3B26 | 15 | Rose | D88FA6 |
| 6 | Chestnut | 6F4128 | 16 | Sea green | 6FB3A0 |
| 7 | Brown | 553322 | 17 | Dusk violet | 5D4E8C |
| 8 | Dark brown | 3B2419 | 18 | Ember | C8443A (RedBand) |
| 9 | Ink | 231A1A | 19 | Deep sea | 2F4E6B |

Brows and lashes darken the hair pick by 0.1 value automatically so they read on the face.

**Hair accessory (`Hair.Accessory`)**: Brass B8893A, Silver C9CDD2, Copper B0683E, Wood 8B5A3A,
DarkWood 4A2A1C, Sail F7EEDC, RedBand C8443A, Gold E3AE45, Leaf 6E8A3A, Shallows 7FD0D6,
Moonglass 7AC0E6, Dusk plum 5D4E8C.

**Eyeshadow (`Makeup.Eyeshadow`)**: Champagne E9D3B0, Peach E9A88A, Terracotta C8643A, Copper
B0683E, Rose D88FA6, Plum 7A4A6E, Dusk plum 5D4E8C, Lilac B49CD6, Moonglass 7AC0E6, Shallows
7FD0D6, Sea green 6FB3A0, Leaf 6E8A3A, Gold E3AE45, Bronze 8E6A3A, Brown 553322, Slate 56616F.

**Eyeliner (`Makeup.Eyeliner`)**: Ink 231A1A, Brown 553322, Deep sea 2F4E6B, Plum 5D4E8C, Forest
3F5A33, Ember C8443A, Gold E3AE45, Silver C9CDD2.

**Lips (`Makeup.Lips`)**: Nude peach D9A28A, Rose D98A7A, Berry B85A6A, Red C8443A (RedBand), Coral
E3805E, Terracotta C8643A, Plum 7A4A6E, Mauve A67A8E, Brown 7A4A3A, Lilac B49CD6, Tide 4D7F7E,
Moonglass 7AC0E6.

**Blush (`Makeup.Blush`)**: Peach E9A88A, Rose D98A7A, Coral E39A7E, Berry B85A6A, Apricot E8A66A,
Lavender C99AC4, Bronze B07A4E, Tide flush 5FA8A0.

**Face paint (`Makeup.FacePaint`)**: Sail F7EEDC, Gold E3AE45, RedBand C8443A, Terracotta C8643A,
Leaf 6E8A3A, Shallows 7FD0D6, Moonglass 7AC0E6, Lilac B49CD6, Deep sea 2F4E6B, Ink 231A1A, Clay
36221A, Silver C9CDD2.

**Cloth (`Outfit.Primary`, `Outfit.Secondary`, `Outfit.Layer`)**

| # | Name | Hex | # | Name | Hex |
|---|---|---|---|---|---|
| 0 | Sail | F7EEDC | 9 | Leaf | 6E8A3A |
| 1 | Sand | F1E9DC | 10 | Grass | 8A9A48 |
| 2 | Oat | D9C7A5 | 11 | Shallows | 7FD0D6 |
| 3 | Wood | 8B5A3A | 12 | Moonglass | 7AC0E6 |
| 4 | DarkWood | 4A2A1C | 13 | Deep sea | 2F4E6B |
| 5 | Clay | 36221A | 14 | Dusk plum | 5D4E8C |
| 6 | Terracotta | C8643A | 15 | Heather | 9C8AB0 |
| 7 | RedBand | C8443A | 16 | Stone | 9C9488 |
| 8 | Gold | E3AE45 | 17 | Ink | 2A2730 |

**Trim (`Outfit.Trim`)**: Brass B8893A, Silver C9CDD2, Copper B0683E, Gold E3AE45, Sail F7EEDC,
DarkWood 4A2A1C, RedBand C8443A, Leaf 6E8A3A, Moonglass 7AC0E6, Ink 2A2730.

**Lantern glass (`Lantern.Glass`)**: Amber E3AE45 (Gold), Warm white F7EEDC (Sail), Moonglass
7AC0E6, Shallows 7FD0D6, Rose D88FA6, Ember C8643A (Terracotta), Violet 9A82D0, Leaf-gold C9D86A,
Pearl E8E6DC.

---

## 6. Style guardrails

### 6.1 Why the ranges stop where they do

The goal is BDO/WWM *granularity* (many small, independent controls) without BDO's *extremes*. Each
slider is narrow, but there are many of them, so faces still differ a lot.

| Range | Why it is clamped there |
|---|---|
| Height ±8%, limb lengths ±8% | Larger changes break animation (feet slide, hands miss the wheel and ropes) and make shared props like doors, beds and the ship's wheel look wrong. ±8% across two frames still gives a clear short-to-tall spread. |
| Head size ±8% | Below -8% the face gets too small to read at sailing camera distance; above +8% reads chibi, which is a different style. |
| Thickness sliders ±15%, width sliders ±10 to 12% | Enough for slim to sturdy and soft to strong builds. Beyond this, outfits clip and the painterly silhouette turns into caricature. |
| Muscle tone, softness, belly at full morph weight | A clearly strong build and a clearly soft, round build are both inside the range. Bodies are shaped with painted forms, not anatomy: no veins, striations or skin folds. |
| Eye size -10% / +15% | Stylized faces carry slightly large eyes; past +15% it becomes anime-doll and the eyelids stop closing cleanly over the eyeball in blinks and expressions. |
| Eye and brow tilt ±10 to 12°, mouth corners "a resting hint" | The face must still animate. Expressions add to these; at extreme rest values, smiles and frowns look broken. |
| Iris ±12%, pupil ±25% | Larger reads as a creature rather than a person; smaller loses the painted highlight that gives eyes life. |
| Cheek hollow 0.5, nose bend 0.4, scars max 0.8 opacity | These add character but turn grim or sickly past this point. Lyris is warm. |
| Age lines 0.6 | Lines are painted strokes, enough for a weathered sailor or a kind grandparent; not wrinkle maps. |
| Ear point up to +6 cm | Long elf and Deepkin ears; longer clips through hoods, hats and the camera at close framing. |
| Hue shift 0.02 to 0.08, value shift 0.08 to 0.20 | Lets the player make "their" shade of a swatch without leaving the band. A full colour wheel would allow neon and grey-dead colours that break the lighting and the palette. |
| Skin bands per People | Each People's band is wide (very fair to very deep for Humans) but stays inside its look, and every swatch is tuned to look warm under both dusk and lamp light. |

### 6.2 Adult proportions guard

Every player character is an adult. The UI and `RandomizeAppearance` enforce one cross-slider rule
the per-slider clamps cannot:

- If `Body.Height` < -0.5, `Body.HeadSize` is capped at +0.3.
- If `Body.Height` < -0.5 and `Body.HeadSize` > 0, `Eyes.SizeL/R` are capped at +0.6.

This keeps a short character with a large head and large eyes from reading as a child. It is a
**need from the Player lane** (apply in `SetSlider` and in `FromShareCode`, so share codes obey it
too).

### 6.3 What we deliberately do not offer

| Not offered | Why |
|---|---|
| Photoreal skin: pores, subsurface detail maps, wrinkle normal maps, skin blemishes, peach fuzz | Breaks the painterly style; skin is flat painted colour with soft gradients, rosiness and painted lines. |
| Extreme proportions (BDO-style giant chests, wasp waists, tiny heads, huge muscles) | Caricature; breaks clothing, animation and the storybook look. |
| Body hair simulation, anatomical detail, nudity | Out of style and not needed for a cozy game; bodies are always clothed by an outfit. |
| Gore: open wounds, missing eyes, bloodied scars | Lyris is calm by default. Scars are healed, soft lines that suggest a story. |
| Free colour pickers (full RGB wheel) | Off-palette colours, neon, and pure black/white break lighting and the world palette. |
| Real-world symbols: religious marks, flags, brand logos, text tattoos, real cultural or sacred markings | Avoids real-world meaning and harm; all markings and face paint come from Lyris. |
| Child-like adult bodies | See 6.2. |
| Gender-locked options or a gender selector | Frames are body shapes only. Beards, makeup, hairstyles and outfits work on both. |
| Stat effects from any look, or People perks | No stats in Lyris. Peoples differ in look only. |

---

## 7. Peoples

Each People has its own skin band and a few unique parts and slider ranges. Peoples differ in look
only: **no flavour perks and no stat or gameplay advantage.**

| | Humans | Moonlit elves | Deepkin |
|---|---|---|---|
| Skin band | `Skin.ToneHuman`: warm, very fair to very deep | `Skin.ToneElf`: moonmilk to nightfall blue-lavender | `Skin.ToneDeepkin`: seafoam to abyss slate |
| Ears | Round; `Ears.TipL/R` for a slight point | Long points (`Ears.PointL/R`, `PointAngleL/R`, `DroopL/R`) | Long points plus fin-ears (`Ears.FinSpreadL/R`) |
| Eyes | Full iris band; standard whites | Eye glow (`Eyes.GlowStrength`, `Eyes.Glow`), Crescent and Starpoint pupils, Moonstone iris | Night shine (`Eyes.ShineStrength`, `Eyes.Shine`), dark eye whites, Slit and Cuttle pupils, Tidal iris |
| Markings | Harbour ink tattoos (4) | Moon sigils (6), glow at night and in mist | Scale patches (6), shimmer, more when wet |
| Unique parts | | `Hair.Moonfall`, `Brows.MoonWisp` | `Hair.KelpTresses`, `Brows.ScaleRidge`, `FacialHair.Barbels` |
| Unique sliders | | `Skin.Moonglow` | |

Presets per People (section 9.8) give each People six ready faces.

---

## 8. Paths, backstories, lanterns and faiths

From the RPG and Paths tabs of `design/Game_Concept.xlsx`. A path is a head start, not a fence: any
path can reach any branch, and the path perk can be swapped later at an academy mentor or your home
lantern.

### 8.1 Paths (step 3)

| Id | Path | Starting item | Branches into later | Default outfit |
|---|---|---|---|---|
| `Seafarer` | Seafarer | Spyglass | Sailor, Fisher, Shipwright, Navigator | `Outfit.DeckhandCoat` |
| `Wanderer` | Wanderer | Walking staff and pack | Wayfarer, Drover, Hunter, Castaway | `Outfit.WandererLayers` |
| `Grower` | Grower | Trowel and seed pouch | Gardener, Herbalist, Cultivator of strange plants | `Outfit.GrowerSmock` |
| `Maker` | Maker | Tool roll | Artisan, Builder, Clockmaker, Shipwright | `Outfit.MakerApron` |
| `Scholar` | Scholar | Notebook | Cartographer, Archivist, Name-keeper, Alchemist | `Outfit.ScholarCoat` |
| `Trader` | Trader | Ledger and scales | Merchant, Cook, Innkeeper | `Outfit.TraderWaistcoat` |
| `Delver` | Delver | Lamp and pick | Miner, Relic hunter, Diver | `Outfit.DelverLeathers` |

### 8.2 Backstories (step 4, optional)

Each adds flavour dialogue and a personal quest. `None` is always allowed.

| Id | Backstory | Path |
|---|---|---|
| `OldShoreCastaway` | Old Shore castaway | Seafarer |
| `HerringRoadDrover` | Drover of the Herring Road | Wanderer |
| `OldHuntHunter` | Hunter of the Old Hunt | Wanderer |
| `Wayfarer` | Wayfarer | Wanderer |
| `Herbalist` | Herbalist | Grower |
| `ClockmakerApprentice` | Clockmaker's apprentice | Maker |
| `Musician` | Musician | Maker |
| `AlembicDescendant` | Alembic descendant | Scholar |
| `AshenLedgerNameKeeper` | Name-keeper of the Ashen Ledger | Scholar |
| `CookFamilyRecipes` | Cook's family recipes | Trader |
| `DeepkinMiner` | Deepkin miner | Delver |

Grower, Trader and Seafarer have only one backstory each; more can come later.

### 8.3 Lanterns (step 5)

Nine shapes (section 4.12) and the `Lantern.Glass` band (section 5.2). The lantern is the player's
first collectible; more shapes and glass colours are found and made later.

### 8.4 Faiths (not part of the creator)

Faith is not chosen in the character creator. Players join a faith when they find it through a quest
in the world. The faiths named in the concept sheet are Tide Mother, Green Hearth, Wayfarers and
Bright Cask, with more in the lore. `FLyrisCharacterProfile.Faith` stays `None` when a character is
created.

---

## 9. Quality-of-life features

### 9.1 Click-and-drag face sculpting

In the `Face` and `Eyes` framings the player can hover the face: the region under the cursor glows
softly (a painted outline, not a wireframe) and shows its name. Dragging changes that region's
sliders: horizontal drag drives the slider with `SculptAxis` H, vertical drag drives the one with V.
Sensitivity: the full slider range over 300 px. The matching sliders move in the panel as you drag.
Right-click on a region resets it. Controller: select a region with the stick, then hold A and use
the left stick.

| Region | H drag | V drag |
|---|---|---|
| `Forehead` | `Face.TempleWidth` | `Forehead.Height` |
| `BrowL` / `BrowR` | `Brows.TiltL` / `R` | `Brows.HeightL` / `R` |
| `EyeL` / `EyeR` | `Eyes.OuterCornerL` / `R` (drag outward to lengthen) | `Eyes.SizeL` / `R` |
| `Nose` | `Nose.BridgeWidth` | `Nose.Height` |
| `Cheeks` | `Face.CheekboneWidth` | `Face.CheekFullness` |
| `Mouth` | `Mouth.Width` | `Mouth.Height` |
| `Jaw` | `Face.JawWidth` | `Face.JawHeight` |
| `Chin` | `Face.ChinWidth` | `Face.Length` |
| `EarL` / `EarR` | `Ears.AngleL` / `R` | `Ears.SizeL` / `R` |

Every sculptable slider belongs to exactly one region and axis, matching the contract's single
`SculptRegion` / `SculptAxis` per slider. Sliders not in this map (for example `Eyes.Spacing`,
`Face.Width`) are edited with the slider only.

### 9.2 Symmetry toggle

On by default. While on, changing any slider with a `MirrorOf` sets its mirror to the same value
(mirrored space, section 1), and sculpt drags on one side move both. Turning it off lets you make the
face asymmetric; turning it back on asks "Copy left to right / right to left / keep as is".

### 9.3 Randomise, locks and wildness

A dice button randomises everything not locked. Each category tab has a small padlock; locked
categories are passed as `LockedCategories`. A **Wildness** slider (0 to 1, default 0.35) controls
how far it goes:

| Wildness | Sliders | Colours | Parts |
|---|---|---|---|
| 0 | Within ±0.25 of the People preset | Common swatches (natural hair, People skin band middle), no shifts | Common parts only, no face paint |
| 0.35 | Normal spread (most values within ±0.5) | Any swatch, half the max shifts | Any part; makeup and markings sometimes |
| 1 | Full range | Any swatch, full shifts, storybook hair colours more likely | Any part, more accessories and face paint |

Rules so random faces stay coherent:
- Mirror pairs get the same value plus a small difference (up to 0.1 x wildness).
- Brows and facial hair follow `Hair.Root` (the `MatchHair` scalars stay 1) unless wildness > 0.7,
  and then only 20% of the time.
- People-restricted entries are only picked for the current People.
- The adult proportions guard (6.2) always applies.
- Lantern, name, path and backstory are never randomised by the dice in step 2. Steps 3 to 5
  each have their own small "surprise me" button.

### 9.4 Undo and redo

Ctrl+Z / Ctrl+Y (controller: LB / RB in the editor). History keeps the last 100 `FLyrisAppearance`
snapshots. A slider drag, a sculpt drag or a colour shift drag is one entry (recorded on release).
Randomise, preset load and share-code import are one entry each, so they can always be undone.
History lasts for the creator session (and for one visit to the mirror, barber or tailor).

### 9.5 Lighting previews

A lamp icon cycles four light rigs. They only change the preview, not the character.

| Id | Name | Look |
|---|---|---|
| `DuskDeck` | Dusk deck (default) | Low warm sun from behind the sail, peach sky, soft lavender shadows |
| `LampLit` | Lamp-lit | Night, warm Gold lamp (E3AE45) from above-front, deep blue surroundings |
| `Midday` | Midday | High sun, clear sky, the brightest and most neutral |
| `Mist` | Mist | Cold Moonglass light (7AC0E6), fog around the deck; elf glow and Deepkin shine show best here |

### 9.6 Expression and pose previews

- **Expressions** (face only, loop once then hold): Calm, Bright smile, Laugh, Wry, Shy, Surprised,
  Sleepy, Determined. Used to check that the face still works when it moves; the resting expression
  the player keeps is the `Expression` part.
- **Poses** (body): Idle (chosen stance), Wave, Hold lantern, Sit on a crate, Lean on the rail,
  Windy (cloak and hair blowing), Walk cycle.

### 9.7 Compare before and after

Hold Tab (controller: hold View) to show the snapshot taken when you entered the current category.
"Pin" saves the current look as the comparison snapshot instead. A split view option shows both side
by side in the same lighting.

### 9.8 Presets per People

Six presets per People, built as complete `FLyrisAppearance` values (and so also valid share codes).
Picking a People in step 1 loads its first preset. Names (approved):

- **Humans:** Harbor Hand, Lamplighter, Old Salt, Orchard Keeper, Clerk of Moonharbor, Drover.
- **Moonlit elves:** Moonwatcher, Star Archivist, Night Gardener, Pale Sail, Lantern Bearer,
  Dusk Wanderer.
- **Deepkin:** Tidewalker, Reef Diver, Hollowdeep Miner, Kelp Singer, Bay Keeper, Storm Pilot.

Players can also save up to 10 of their own presets locally (named, with a portrait thumbnail).

### 9.9 Share codes

"Copy code" puts `LYR1:` plus Base64 compact JSON of the current `FLyrisAppearance` on the
clipboard. "Paste code" imports one. A share code carries looks only, never name, path, backstory,
faith or lantern. On import:

- Unknown ids are ignored (codes from newer versions still mostly work).
- Values are clamped to the current ranges and swatch counts.
- Entries restricted to another People are dropped, with a note ("Some Deepkin-only options were
  left out").
- If the code's People differs from the current one, the player is asked "Switch to Moonlit elf to
  use this look?".
- The adult proportions guard applies.

### 9.10 Changing looks later

Looks are never locked. All three places open the same editor with the same tools, in world lighting
with the same four previews:

| Place | Where | What you can change |
|---|---|---|
| Barber | Moonharbor (and later other ports) | Hair category, Makeup category, Facial hair |
| Tailor | Moonharbor | Outfit category, and the outfit sets you have collected |
| Mirror | Your home, and the dormitory at the Academy | Everything: Body, Face, Eyes, Hair, Skin, Makeup, Outfit, Voice, Frame |

Changes are free (calm-by-default). A character's People can also be changed after creation; where
that happens (mirror, academy or elsewhere) is still to be decided. When it changes, the look is kept
as close as possible: sliders and parts that exist for both Peoples are kept, and the skin pick falls
back to the new People's matching band position.

---

## 10. Needs from other lanes

- **Player (T23):** the default catalog in code with the ids, ranges, weights, mirrors, sculpt
  regions and People lists above; the adult proportions guard (6.2) in `SetSlider`, randomise and
  share-code import; mirrored-space axis flipping for L/R sliders; part scalars `Brows.MatchHair`, `FacialHair.MatchHair` and `Eyes.Heterochromia` behaving as
  described; the `Lantern` category being excluded from `GetCategories()` results the Appearance tabs
  use (or the UI filtering it).
- **UI (T24):** the framings in 2.1, sculpt map in 9.1, the wildness table in 9.3, lighting rigs in
  9.5 and the import notes in 9.9.
- **Environment (T25):** morph target names as listed in section 3 tables, two frames (Willow and Oak),
  and ear cut-out variants for long-ear Peoples.
- **Lead (T26):** none beyond the flow in section 2 (the voyage stage and lighting the lantern on the
  dock).
