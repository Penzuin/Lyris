# Ocean contract (fixed by the lead for T17, T19, T20)

All three tasks code against this. Do not change names or the formula without telling the lead.

## C++ (World lane, T17) — Source/Lyris/World/
- `ULyrisOceanSettings : UDeveloperSettings` — Project Settings > Game > "Lyris Ocean", Config=Game, DefaultConfig. Mirrors the style of `ULyrisWindSettings` on branch lane/sailing-T5-world-wind.
  Fields: SeaLevel (0), TimeScale (1), Waves[4] {DirectionYawDeg, WavelengthCm, AmplitudeCm, Steepness 0..1},
  CalmAmplitudeScale (0.25), HomeCalmZones[] {FVector2D Center, Radius, Falloff} (default one zone at Moonharbor bay -20000,-266000 radius 55000 falloff 40000, as `Config/DefaultGame.ini` sets it; T37),
  SeaParameterCollection soft path (default `/Game/Lyris/Materials/MPC_Sea.MPC_Sea`).
- `ULyrisOceanSubsystem : UTickableWorldSubsystem`, header `World/LyrisOceanSubsystem.h`. BlueprintCallable, const:
  - `float GetSeaLevel() const`
  - `float GetOceanTime() const` — world time seconds * TimeScale (same clock source the wind uses)
  - `float GetWaterHeightAt(FVector2D WorldXY) const` — absolute Z of the surface above that XY right now (invert the Gerstner horizontal offset with 3 fixed-point iterations)
  - `FVector GetWaterNormalAt(FVector2D WorldXY) const`
  - `FVector GetWaterVelocityAt(FVector2D WorldXY) const` — surface orbital velocity, cm/s
  - `float GetRoughnessAt(FVector2D WorldXY) const` — 0 calm .. 1 rough
  - `void RegisterCalmZone(FName Id, FVector2D Center, float Radius, float Falloff)` / `void UnregisterCalmZone(FName Id)` — lamps (T3) will call these later
  - `static ULyrisOceanSubsystem* Get(const UObject* WorldContext)`
  Each tick it writes the Material Parameter Collection below (if the asset exists; silently skip if not). At most 4 calm zones go to the MPC: home zones first, then registered ones, nearest to the player.

## Material Parameter Collection (Environment lane, T19) — `/Game/Lyris/Materials/MPC_Sea`, created by `Content/Python/lyris_build_world.py`
- Scalar `OceanTime`, Scalar `SeaLevel`, Scalar `CalmAmplitudeScale`
- Vector `Wave0`..`Wave3` = (DirX, DirY, WavelengthCm, AmplitudeCm)   (DirX/DirY unit vector from DirectionYawDeg)
- Vector `WaveSteepness` = (S0, S1, S2, S3)
- Vector `CalmZone0`..`CalmZone3` = (CenterX, CenterY, Radius, Falloff); Radius 0 = unused

## The formula (C++ and the material must match exactly)
For a point p = (x, y), time t, with g = 980 cm/s^2 and N = 4:
- Roughness r(p) = 1 - max over used zones of (1 - smoothstep(Radius, Radius + Falloff, |p - Center|)); with no zones r = 1.
- AmplitudeScale m(p) = lerp(CalmAmplitudeScale, 1, r(p))
- For each wave i: k = 2*pi/L, c = sqrt(g / k), A = Amplitude * m(p), theta = k * (D . p) - k * c * t,
  Q = Steepness / (k * Amplitude * N)   (uses unscaled Amplitude so Q stays bounded)
- Displaced position: XY = p + sum_i( Q_i * A_i * D_i * cos(theta_i) ),  Z = SeaLevel + sum_i( A_i * sin(theta_i) )
- Normal: standard Gerstner normal from the same terms.
Default waves (calm, storybook): (yaw 30, L 6000, A 45, S 0.35), (yaw 75, L 3100, A 22, S 0.3), (yaw -20, L 1700, A 10, S 0.25), (yaw 120, L 900, A 4, S 0.2).
