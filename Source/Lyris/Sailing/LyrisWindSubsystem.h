// Lyris sailing: the one shared world wind every boat (and later the HUD) reads.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "LyrisWindSubsystem.generated.h"

class ULyrisWindSettings;

/** One reading of the wind at a moment in time. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisWindSample
{
	GENERATED_BODY()

	/** Direction the wind blows toward, in degrees of world yaw, normalized to -180..180. */
	UPROPERTY(BlueprintReadOnly, Category = "Wind")
	float Yaw = 0.f;

	/** Unit vector (flat, Z = 0) the wind blows toward. */
	UPROPERTY(BlueprintReadOnly, Category = "Wind")
	FVector Direction = FVector::ForwardVector;

	/** Wind strength, 0 to 1. Never below the configured minimum. */
	UPROPERTY(BlueprintReadOnly, Category = "Wind")
	float Strength = 0.f;

	/** How much of a gust is blowing right now, 0 to 1. */
	UPROPERTY(BlueprintReadOnly, Category = "Wind")
	float GustAlpha = 0.f;

	/** How deep into a calm spell the wind is right now, 0 to 1. */
	UPROPERTY(BlueprintReadOnly, Category = "Wind")
	float CalmAlpha = 0.f;
};

/**
 * One wind for the whole world. Direction veers slowly around the compass over minutes and wanders
 * back and forth; strength swells gently, with occasional gusts and calm spells, but never dies out.
 *
 * The wind is a pure function of (settings, seed, world time) built from smooth noise: nothing is
 * random per frame and nothing is stored, so every machine in a multiplayer session that shares the
 * same settings and the same synced clock computes the same wind. World time comes from the game
 * state's server world time when there is one, which is already replicated to clients.
 *
 * Tuning lives in Project Settings > Game > Lyris Wind (ULyrisWindSettings).
 */
UCLASS()
class LYRIS_API ULyrisWindSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	/** Convenience accessor for C++. Returns null if there is no world. */
	static ULyrisWindSubsystem* Get(const UObject* WorldContextObject);

	/** Direction the wind blows toward, in degrees of world yaw (-180..180). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Wind")
	float GetWindYaw() const;

	/** Flat unit vector the wind blows toward. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Wind")
	FVector GetWindDirection() const;

	/** Wind strength, 0 to 1. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Wind")
	float GetWindStrength() const;

	/** Everything about the wind right now in one go (yaw, direction, strength, gust and calm amounts). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Wind")
	FLyrisWindSample GetWindSample() const;

	/** The wind at any world time (seconds), e.g. to preview it ahead for a forecast. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Wind")
	FLyrisWindSample GetWindSampleAtTime(float WorldTimeSeconds) const;

	/** The clock the wind runs on: synced server world time when available, otherwise local world time. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Wind")
	float GetWindClockSeconds() const;

	/**
	 * The deterministic wind function itself. Same settings + same time = same result anywhere.
	 * Static so tools and tests can call it without a world.
	 */
	static FLyrisWindSample EvaluateWind(const ULyrisWindSettings& Settings, double WorldTimeSeconds);
};
