// Lyris world: tuning for the one shared sea state. Edit in Project Settings > Game > Lyris Ocean
// (saved to Config/DefaultGame.ini under [/Script/Lyris.LyrisOceanSettings]).
//
// The API and the wave formula are fixed by the ocean contract (World/OCEAN_CONTRACT.md); the boat (T18),
// the sea material (T19) and swimming (T20) all read the same values, so do not rename anything here
// without telling the lead.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "LyrisOceanSettings.generated.h"

class UMaterialParameterCollection;

/** One Gerstner wave in the sum. The sea is always exactly four of these (MPC_Sea Wave0..Wave3). */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisOceanWave
{
	GENERATED_BODY()

	FLyrisOceanWave() = default;
	FLyrisOceanWave(float InYawDeg, float InWavelengthCm, float InAmplitudeCm, float InSteepness)
		: DirectionYawDeg(InYawDeg), WavelengthCm(InWavelengthCm), AmplitudeCm(InAmplitudeCm), Steepness(InSteepness)
	{
	}

	/** Direction the wave travels toward, in degrees of world yaw (0 = +X, 90 = +Y). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Wave")
	float DirectionYawDeg = 0.f;

	/** Crest-to-crest distance in cm. Longer waves also travel faster (deep-water speed). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Wave", meta = (ClampMin = "10.0", UIMin = "100.0", UIMax = "20000.0"))
	float WavelengthCm = 1000.f;

	/** Height of a crest above sea level in open (rough) water, in cm. Calm zones scale this down. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Wave", meta = (ClampMin = "0.0", UIMin = "0.0", UIMax = "500.0"))
	float AmplitudeCm = 0.f;

	/** 0 = round sine swell, 1 = sharp crests. The four steepnesses together should stay at or below 1 to avoid loops. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Wave", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float Steepness = 0.f;
};

/** A circle of calm water (a lit harbor, later a lamp). Full calm inside Radius, easing to open sea over Falloff. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisCalmZone
{
	GENERATED_BODY()

	FLyrisCalmZone() = default;
	FLyrisCalmZone(const FVector2D& InCenter, float InRadius, float InFalloff)
		: Center(InCenter), Radius(InRadius), Falloff(InFalloff)
	{
	}

	/** World XY of the zone's middle, in cm. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Calm Zone")
	FVector2D Center = FVector2D::ZeroVector;

	/** Fully calm out to this distance, in cm. A radius of 0 means the zone is unused. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Calm Zone", meta = (ClampMin = "0.0"))
	float Radius = 0.f;

	/** Distance over which the calm fades back into open sea, in cm. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Calm Zone", meta = (ClampMin = "0.0"))
	float Falloff = 0.f;
};

/**
 * How the sea behaves. The surface is a pure function of (settings, calm zones, world time): nothing is
 * random and nothing is simulated, so every machine with the same settings and the same synced clock
 * sees the same waves, and the material draws exactly what physics feels.
 *
 * Calm by default: lit waters (the home calm zones, later every lamp) flatten the swell down to
 * CalmAmplitudeScale; open, unlit water gets the full rolling swell.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Lyris Ocean"))
class LYRIS_API ULyrisOceanSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	ULyrisOceanSettings();

	static const ULyrisOceanSettings* Get() { return GetDefault<ULyrisOceanSettings>(); }

	/** Bumped whenever a value changes (editor edits, config reloads), so the ocean subsystem knows to rebuild its cache. */
	uint32 GetRevision() const { return Revision; }

	/** World Z of the flat, still sea, in cm. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Sea")
	float SeaLevel = 0.f;

	/** Speeds the waves up for testing (1 = normal, 10 = ten times faster). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Sea", meta = (ClampMin = "0.0", UIMin = "0.0", UIMax = "20.0"))
	float TimeScale = 1.f;

	/**
	 * The four summed Gerstner waves, at full open-sea size. Default: a calm storybook swell, one long
	 * rolling wave with three smaller ones crossing it.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Waves")
	FLyrisOceanWave Waves[4];

	/** Number of summed waves. Fixed at four: the material reads exactly Wave0..Wave3. */
	static constexpr int32 WaveCount = 4;

	/** Most calm zones the material sees at once (MPC_Sea CalmZone0..CalmZone3). C++ queries use every zone. */
	static constexpr int32 MaxMaterialCalmZones = 4;

	/** How much of the wave height is left in the middle of a calm zone (0 = glassy, 1 = no calming). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Calm Waters", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float CalmAmplitudeScale = 0.25f;

	/** Calm zones that always exist (home harbors). Lamps add more at runtime through ULyrisOceanSubsystem::RegisterCalmZone. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Calm Waters")
	TArray<FLyrisCalmZone> HomeCalmZones;

	/** Material Parameter Collection the subsystem writes every tick for the sea material. Made by the Harbor build script. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Rendering")
	TSoftObjectPtr<UMaterialParameterCollection> SeaParameterCollection;

	//~ UObject
	virtual void PostReloadConfig(FProperty* PropertyThatWasLoaded) override;
#if WITH_EDITOR
	virtual void PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent) override;
#endif

private:
	uint32 Revision = 1;
};
