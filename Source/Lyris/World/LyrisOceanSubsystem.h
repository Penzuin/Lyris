// Lyris world: the one shared sea state. The boat (T18), the swimmer (T20) and the sea material (T19)
// all read these waves, so what you see is what floats you.
//
// The API, the MPC_Sea parameter names and the wave formula are fixed by World/OCEAN_CONTRACT.md.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "World/LyrisOceanSettings.h"
#include "LyrisOceanSubsystem.generated.h"

class UMaterialParameterCollection;

/**
 * One sea for the whole world: four summed Gerstner waves, flattened inside calm zones (lit harbors,
 * later lamps) and rolling at full size in open, unlit water.
 *
 * The sea is a pure function of (settings, calm zones, world time). Nothing is random or simulated, so
 * every machine that shares the same settings and the same synced clock sees the same surface. The clock
 * is the same one the wind uses: the game state's replicated server world time when there is one,
 * otherwise local world time, multiplied by TimeScale.
 *
 * Every tick it writes the waves, the clock and the four calm zones nearest the player into the
 * MPC_Sea Material Parameter Collection, so the sea material displaces with exactly the same numbers.
 *
 * Queries are cheap (a handful of sin/cos per wave, per-wave constants cached) and fine to call many
 * times per tick. Tuning lives in Project Settings > Game > Lyris Ocean (ULyrisOceanSettings).
 */
UCLASS()
class LYRIS_API ULyrisOceanSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	/** Convenience accessor for C++. Returns null if there is no world. */
	static ULyrisOceanSubsystem* Get(const UObject* WorldContext);

	//~ USubsystem
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	//~ FTickableGameObject
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;
	/** Also ticks in editor worlds, so the sea material moves in the level viewport. */
	virtual bool IsTickableInEditor() const override { return true; }

	/** World Z of the flat, still sea, in cm. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Ocean")
	float GetSeaLevel() const;

	/** The clock the waves run on, in seconds: synced world time * TimeScale. This is what MPC_Sea.OceanTime holds. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Ocean")
	float GetOceanTime() const;

	/** Absolute world Z of the water surface directly above (or below) this XY right now, in cm. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Ocean")
	float GetWaterHeightAt(FVector2D WorldXY) const;

	/** Unit normal of the water surface at this XY right now. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Ocean")
	FVector GetWaterNormalAt(FVector2D WorldXY) const;

	/** How fast the water surface at this XY is moving right now (the orbit of the wave), in cm/s. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Ocean")
	FVector GetWaterVelocityAt(FVector2D WorldXY) const;

	/** How rough the sea is here: 0 in the middle of a calm zone, 1 in open water. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Ocean")
	float GetRoughnessAt(FVector2D WorldXY) const;

	/**
	 * Adds (or moves, if Id is already registered) a circle of calm water. Lamps call this when they light.
	 * Fully calm inside Radius, fading back to open sea over Falloff (both in cm).
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Ocean")
	void RegisterCalmZone(FName Id, FVector2D Center, float Radius, float Falloff);

	/** Removes a calm zone added with RegisterCalmZone. Unknown ids are ignored. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Ocean")
	void UnregisterCalmZone(FName Id);

private:
	/** Per-wave constants, precomputed from settings so queries only do the trig. */
	struct FWaveCache
	{
		FVector2D Dir = FVector2D(1.0, 0.0); // unit travel direction D
		double K = 0.0;                      // wavenumber k = 2*pi / L
		double Omega = 0.0;                  // angular speed k * c, with c = sqrt(g / k)
		double Amplitude = 0.0;              // unscaled amplitude, cm
		double Q = 0.0;                      // Steepness / (k * Amplitude * N)
	};

	/** One summed evaluation of the waves at an undisplaced point p. */
	struct FSurfaceSample
	{
		FVector2D HorizontalOffset = FVector2D::ZeroVector; // sum Q A D cos(theta)
		double Height = 0.0;                                 // sum A sin(theta), relative to sea level
		FVector Normal = FVector::UpVector;
		FVector Velocity = FVector::ZeroVector;
	};

	/** Seconds on the synced clock (before TimeScale). Same source as the wind. */
	double GetClockSeconds() const;

	/** Rebuilds the per-wave cache if the settings changed since last time. */
	void EnsureCache() const;

	/** Roughness r(p) from every used calm zone (home + registered). */
	double ComputeRoughness(const FVector2D& P) const;

	/** Evaluates the summed Gerstner waves at undisplaced point P and ocean time T. */
	FSurfaceSample EvaluateAt(const FVector2D& P, double T, bool bWithNormalAndVelocity) const;

	/** Finds the undisplaced point whose displaced XY lands on WorldXY (3 fixed-point iterations, per the contract). */
	FVector2D InvertHorizontal(const FVector2D& WorldXY, double T) const;

	/** Writes the waves, clock and nearest calm zones into MPC_Sea, if it exists. */
	void WriteMaterialParameters();

	/** Where the player is, for picking which calm zones the material sees. */
	FVector2D GetPlayerXY() const;

	/** Lamp-registered calm zones by id. */
	TMap<FName, FLyrisCalmZone> RegisteredCalmZones;

	/** MPC_Sea, once loaded. Kept here so it is not garbage collected. */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialParameterCollection> SeaCollection;

	/** Settings revision the collection was last looked up for (so a missing asset is only tried once per settings change). */
	uint32 CollectionRevision = 0;

	/** True once we have logged that MPC_Sea is missing, so the log is not spammed. */
	bool bLoggedMissingCollection = false;

	mutable FWaveCache WaveCache[ULyrisOceanSettings::WaveCount];
	mutable uint32 CachedRevision = 0;
};
