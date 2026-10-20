// Lyris sailing: tuning for the one shared world wind. Edit in Project Settings > Game > Lyris Wind
// (saved to Config/DefaultGame.ini under [/Script/Lyris.LyrisWindSettings]).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "LyrisWindSettings.generated.h"

/**
 * How the world wind behaves. Every value here feeds a deterministic function of (seed, world time),
 * so two machines with the same settings and the same clock compute the same wind.
 *
 * The wind is calm by default: strength sits around BaseStrength, rises in short gusts, eases into
 * occasional calm spells, and never drops below MinStrength.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Lyris Wind"))
class LYRIS_API ULyrisWindSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	ULyrisWindSettings();

	static const ULyrisWindSettings* Get() { return GetDefault<ULyrisWindSettings>(); }

	/** Same seed + same world time = same wind, on every machine. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Wind")
	int32 Seed = 1729;

	/** Speeds the whole wind up for testing (1 = normal, 10 = ten times faster). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Wind", meta = (ClampMin = "0.0", UIMin = "0.0", UIMax = "20.0"))
	float TimeScale = 1.f;

	// ---- Direction ----

	/** Direction the wind blows toward at time zero, in degrees of world yaw. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Direction")
	float BaseYaw = 90.f;

	/** Steady veer around the compass, in degrees per minute (6 = a full circle every hour). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Direction", meta = (UIMin = "-30.0", UIMax = "30.0"))
	float DriftDegreesPerMinute = 4.f;

	/** How far the wind wanders back and forth on top of the steady veer, in degrees either way. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Direction", meta = (ClampMin = "0.0", UIMin = "0.0", UIMax = "360.0"))
	float WanderDegrees = 120.f;

	/** Roughly how long one wander swing takes, in seconds. Bigger = slower, lazier shifts. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Direction", meta = (ClampMin = "10.0", UIMin = "30.0", UIMax = "1200.0"))
	float WanderPeriodSeconds = 300.f;

	// ---- Strength ----

	/** Usual strength of the breeze, 0 to 1. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Strength", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float BaseStrength = 0.8f;

	/** Slow swell of the breeze above and below BaseStrength. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Strength", meta = (ClampMin = "0.0", ClampMax = "0.5"))
	float BreezeVariation = 0.1f;

	/** How long a slow breeze swell takes, in seconds. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Strength", meta = (ClampMin = "5.0", UIMin = "10.0", UIMax = "600.0"))
	float BreezePeriodSeconds = 90.f;

	/** Extra strength a full gust adds on top of the breeze. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Gusts", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float GustStrength = 0.2f;

	/** Roughly what share of the time a gust is blowing, 0 to 1. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Gusts", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float GustFrequency = 0.25f;

	/** Roughly how long a gust cycle lasts, in seconds. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Gusts", meta = (ClampMin = "1.0", UIMin = "3.0", UIMax = "60.0"))
	float GustPeriodSeconds = 12.f;

	/** Roughly what share of the time the wind is in a calm spell, 0 to 1. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Calms", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float CalmFrequency = 0.15f;

	/** Strength the wind eases down to in the middle of a calm spell. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Calms", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float CalmStrength = 0.4f;

	/** Roughly how long a calm cycle lasts, in seconds (a calm spell is a fraction of this). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Calms", meta = (ClampMin = "10.0", UIMin = "30.0", UIMax = "1200.0"))
	float CalmPeriodSeconds = 120.f;

	/** The wind never drops below this, so boats are never left dead in the water. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Strength", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float MinStrength = 0.35f;
};
