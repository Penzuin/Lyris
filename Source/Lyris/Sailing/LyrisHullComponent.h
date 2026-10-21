// Lyris sailing (T21): rough water and the hull. Water comes aboard, the boat grows sluggish, you bail and
// patch; a swamped boat never sinks for good, it drifts home to the nearest lit harbor.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "InputCoreTypes.h"
#include "LyrisHullComponent.generated.h"

class APlayerController;
class UMaterialInterface;
class USceneComponent;
class UStaticMesh;
class UStaticMeshComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FLyrisHullBreached, int32, BreachCount);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FLyrisHullSwamped);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FLyrisHullReturnedHome);

/** One hole in the hull and the dark spot that shows it. */
USTRUCT()
struct FLyrisHullBreach
{
	GENERATED_BODY()

	/** Where the hole is, relative to the boat's visual root. */
	UPROPERTY()
	FVector LocalPosition = FVector::ZeroVector;

	/** The visible leak spot (an engine cube, made in code). */
	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Spot = nullptr;
};

/**
 * Water aboard a boat, 0 (dry) .. 1 (swamped).
 *
 * In:  each breach leaks LeakRatePerBreach per second (stacking up to MaxBreaches), and in rough, unlit
 *      water a little spray comes over the bow at speed (scaled by ULyrisOceanSubsystem::GetRoughnessAt).
 *      Breaches come from hitting rocks or terrain hard, and rarely from big waves in rough water.
 *      Calm, lamp-lit water (roughness 0) never breaches the hull on its own.
 * Out: bail (Q while aboard, hold to keep scooping) and patch the oldest open leak (R, uses one plank).
 * Leaks pause while nobody is aboard, so a boat left at a mooring never fills up on its own.
 *
 * More water means a lower top speed, slower turning and a boat that sits lower. At 1 the boat is
 * swamped: it stops, the screen fades, and it is returned (with you aboard) to the nearest lit harbor,
 * emptied and patched. Nothing is lost and nobody is hurt.
 *
 * The boat reads GetSpeedMultiplier / GetTurnMultiplier in UpdateSailing and subtracts GetSinkOffset from
 * its FreeboardOffset in UpdateFloating (see the "T21 hook" comments in LyrisBoat.cpp).
 *
 * Harbors: the boat is returned to the nearest ALyrisHarborMooring whose water is lit (calm), or, if there
 * is none, to where it started the level (its home mooring beside the dock).
 */
UCLASS(ClassGroup = (Lyris), meta = (BlueprintSpawnableComponent))
class LYRIS_API ULyrisHullComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	ULyrisHullComponent();

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	// ---- Reading the hull ---------------------------------------------------------------------------

	/** Water aboard, 0 dry .. 1 swamped. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Hull")
	float GetWaterLevel() const { return WaterLevel; }

	/** Open (unpatched) breaches. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Hull")
	int32 GetBreachCount() const { return Breaches.Num(); }

	/** True from the moment the boat swamps until it is back afloat in a harbor. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Hull")
	bool IsSwamped() const { return State != EHullState::Afloat; }

	/** Multiply the boat's target speed by this: 1 when dry, MinSpeedMultiplier when nearly swamped, 0 when swamped. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Hull")
	float GetSpeedMultiplier() const;

	/** Multiply the boat's turn rate by this: 1 when dry, MinTurnMultiplier when nearly swamped, 0 when swamped. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Hull")
	float GetTurnMultiplier() const;

	/** How much lower the boat should sit in the water right now, in cm (for T18's buoyancy / freeboard). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Hull")
	float GetSinkOffset() const;

	// ---- Doing things to the hull -------------------------------------------------------------------

	/** One scoop of the bucket. Returns true if water was removed (false while on cooldown or dry). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Hull")
	bool Bail();

	/** Patches the oldest open breach. Uses one plank when the player carries an inventory; free until then. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Hull")
	bool PatchBreach();

	/** Opens a breach at a point on the hull (world space). Ignored at MaxBreaches or while swamped. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Hull")
	void AddBreach(FVector WorldLocation);

	/** Empties and patches the hull at once (a harbor's shipwright, a debug key). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Hull")
	void RepairFully();

	UPROPERTY(BlueprintAssignable, Category = "Lyris|Hull")
	FLyrisHullBreached OnBreached;

	UPROPERTY(BlueprintAssignable, Category = "Lyris|Hull")
	FLyrisHullSwamped OnSwamped;

	UPROPERTY(BlueprintAssignable, Category = "Lyris|Hull")
	FLyrisHullReturnedHome OnReturnedHome;

	// ---- Tuning: water coming in --------------------------------------------------------------------

	/** Water per second from each open breach (0.012 = one leak alone swamps an empty boat in about 80 s). */
	UPROPERTY(EditAnywhere, Category = "Hull|Leaks", meta = (ClampMin = "0"))
	float LeakRatePerBreach = 0.012f;

	/** Most breaches open at once; further impacts don't add more. */
	UPROPERTY(EditAnywhere, Category = "Hull|Leaks", meta = (ClampMin = "1", ClampMax = "12"))
	int32 MaxBreaches = 4;

	/** Spray over the bow per second at full roughness and ReferenceSpeed. */
	UPROPERTY(EditAnywhere, Category = "Hull|Spray", meta = (ClampMin = "0"))
	float SprayRate = 0.006f;

	/** No spray below this roughness (lit waters stay dry). */
	UPROPERTY(EditAnywhere, Category = "Hull|Spray", meta = (ClampMin = "0", ClampMax = "1"))
	float SprayRoughnessThreshold = 0.4f;

	/** Speed (cm/s) at which spray and wave breaches reach full strength. Matches the boat's default MaxSpeed. */
	UPROPERTY(EditAnywhere, Category = "Hull|Spray", meta = (ClampMin = "1"))
	float ReferenceSpeed = 900.f;

	/** Speed straight into a rock or the shore (cm/s) above which the hull is breached. 900 = full sail. */
	UPROPERTY(EditAnywhere, Category = "Hull|Impacts", meta = (ClampMin = "0"))
	float ImpactBreachSpeed = 350.f;

	/** Seconds after a breach before another impact can breach again (one crash = one hole). */
	UPROPERTY(EditAnywhere, Category = "Hull|Impacts", meta = (ClampMin = "0"))
	float ImpactBreachCooldown = 2.f;

	/** Big waves only breach above this roughness, so lamp-lit and nearby waters never do. */
	UPROPERTY(EditAnywhere, Category = "Hull|Waves", meta = (ClampMin = "0", ClampMax = "1"))
	float WaveBreachRoughnessThreshold = 0.75f;

	/** Average wave breaches per minute at full roughness while under way at ReferenceSpeed. Rare. */
	UPROPERTY(EditAnywhere, Category = "Hull|Waves", meta = (ClampMin = "0"))
	float WaveBreachesPerMinute = 0.4f;

	// ---- Tuning: effects ----------------------------------------------------------------------------

	/** Below this water level the boat handles normally. */
	UPROPERTY(EditAnywhere, Category = "Hull|Effects", meta = (ClampMin = "0", ClampMax = "1"))
	float SluggishStart = 0.1f;

	/** Top speed multiplier just before swamping. */
	UPROPERTY(EditAnywhere, Category = "Hull|Effects", meta = (ClampMin = "0", ClampMax = "1"))
	float MinSpeedMultiplier = 0.45f;

	/** Turn rate multiplier just before swamping. */
	UPROPERTY(EditAnywhere, Category = "Hull|Effects", meta = (ClampMin = "0", ClampMax = "1"))
	float MinTurnMultiplier = 0.55f;

	/** How much lower the boat sits when full of water, in cm. */
	UPROPERTY(EditAnywhere, Category = "Hull|Effects", meta = (ClampMin = "0"))
	float MaxSinkOffset = 35.f;

	// ---- Tuning: bailing and patching ---------------------------------------------------------------

	/** Water removed by one scoop. */
	UPROPERTY(EditAnywhere, Category = "Hull|Bailing", meta = (ClampMin = "0", ClampMax = "1"))
	float BailAmount = 0.06f;

	/** Seconds between scoops (holding the key keeps bailing at this pace). */
	UPROPERTY(EditAnywhere, Category = "Hull|Bailing", meta = (ClampMin = "0.05"))
	float BailCooldown = 0.6f;

	/** Bail key while aboard. The boat reads its other keys the same way (no input asset needed). */
	UPROPERTY(EditAnywhere, Category = "Hull|Bailing")
	FKey BailKey;

	/** Tool type required to bail, e.g. "Bucket". None = no bucket needed (the default for now). */
	UPROPERTY(EditAnywhere, Category = "Hull|Bailing")
	FName BailToolType;

	/** Patch key while aboard. */
	UPROPERTY(EditAnywhere, Category = "Hull|Patching")
	FKey PatchKey;

	/** Item one patch uses. Registered as a built-in item at BeginPlay if no other source defines it. */
	UPROPERTY(EditAnywhere, Category = "Hull|Patching")
	FName PlankItemId;

	/** Seconds a patch takes before the next one (keeps it from being a single key-mash). */
	UPROPERTY(EditAnywhere, Category = "Hull|Patching", meta = (ClampMin = "0"))
	float PatchCooldown = 0.8f;

	// ---- Tuning: swamped ----------------------------------------------------------------------------

	/** Seconds the swamped boat wallows (with a gentle message) before the screen fades. */
	UPROPERTY(EditAnywhere, Category = "Hull|Swamped", meta = (ClampMin = "0"))
	float SwampedPause = 2.5f;

	UPROPERTY(EditAnywhere, Category = "Hull|Swamped", meta = (ClampMin = "0.05"))
	float FadeOutTime = 1.5f;

	UPROPERTY(EditAnywhere, Category = "Hull|Swamped", meta = (ClampMin = "0.05"))
	float FadeInTime = 1.5f;

	UPROPERTY(EditAnywhere, Category = "Hull|Swamped")
	FLinearColor FadeColor = FLinearColor(0.02f, 0.03f, 0.06f);

	/** A harbor mooring only counts as lit if the sea there is at most this rough. */
	UPROPERTY(EditAnywhere, Category = "Hull|Swamped", meta = (ClampMin = "0", ClampMax = "1"))
	float LitHarborMaxRoughness = 0.35f;

	// ---- Looks --------------------------------------------------------------------------------------

	UPROPERTY(EditAnywhere, Category = "Hull|Looks")
	TObjectPtr<UStaticMesh> SpotMesh;

	/** The dark hole of an open breach. */
	UPROPERTY(EditAnywhere, Category = "Hull|Looks")
	TObjectPtr<UMaterialInterface> BreachMaterial;

	/** A plank nailed over a patched breach. */
	UPROPERTY(EditAnywhere, Category = "Hull|Looks")
	TObjectPtr<UMaterialInterface> PlankMaterial;

	/** Half-size of the hull box the spots sit on, relative to the visual root (the boat's Hull cube is 550 x 180 x 90 cm). */
	UPROPERTY(EditAnywhere, Category = "Hull|Looks")
	FVector HullHalfExtent = FVector(275.f, 90.f, 45.f);

	/** Spots never go here (hull space, cm): the boarding ladder on the port quarter. */
	UPROPERTY(EditAnywhere, Category = "Hull|Looks")
	FVector LadderKeepOutCenter = FVector(-180.f, -90.f, 0.f);

	/** Half-length along the hull of the ladder keep-out, in cm. */
	UPROPERTY(EditAnywhere, Category = "Hull|Looks", meta = (ClampMin = "0"))
	float LadderKeepOutHalfLength = 75.f;

	/** Most patched planks kept on the hull; the oldest are tidied away past this. */
	UPROPERTY(EditAnywhere, Category = "Hull|Looks", meta = (ClampMin = "0"))
	int32 MaxVisiblePlanks = 8;

private:
	enum class EHullState : uint8
	{
		Afloat,
		Swamped,    // wallowing, message shown
		FadingOut,  // screen going dark
		FadingIn    // back home, screen clearing
	};

	UFUNCTION()
	void HandleOwnerHit(AActor* SelfActor, AActor* OtherActor, FVector NormalImpulse, const FHitResult& Hit);

	/** The local player controlling the boat, or null when nobody is aboard. */
	APlayerController* GetAboardController() const;

	void UpdateMotion(float DeltaTime);
	void UpdateWaveBreaches(float DeltaTime);
	void UpdateWaterIn(float DeltaTime, bool bAboard);
	void UpdateInput(APlayerController* PC);
	void UpdateSwamp(float DeltaTime, APlayerController* PC);
	void ShowHints(bool bAboard) const;

	void BeginSwamp();
	void ReturnToHarbor();

	/** Finds the nearest lit harbor mooring. Always succeeds: the boat's own home mooring is the fallback. */
	void FindHarbor(FVector& OutLocation, FRotator& OutRotation, FText& OutName) const;

	/** Where the player's planks are: the walker stored by the boat, then the boat / its controller. */
	class ULyrisInventoryComponent* FindPlayerInventory() const;

	/** Makes sure PlankItemId resolves through ULyrisItemRegistry (registers a built-in row if not). */
	void EnsurePlankItem();

	UStaticMeshComponent* MakeSpot(const FVector& LocalPosition, UMaterialInterface* Material, const FVector& Scale);
	/** Projects a hull-space point onto the port or starboard side of the hull, clear of the ladder and other spots. */
	FVector PlaceOnHullSide(const FVector& LocalPoint) const;
	void PatchBreachAt(int32 Index);
	void TrimPlanks();

	static void ShowMessage(int32 Slot, const FString& Text, const FColor& Color, float Seconds = 0.15f);

	UPROPERTY(Transient)
	TArray<FLyrisHullBreach> Breaches;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> Planks;

	/** The boat's "Visual" root (pitches and rolls with the swell); spots attach here. */
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> VisualRoot;

	float WaterLevel = 0.f;
	EHullState State = EHullState::Afloat;
	float StateTime = 0.f;

	/** Measured from movement each tick (the boat's own speed is private), cm/s, horizontal. */
	FVector LastVelocity = FVector::ZeroVector;
	FVector PreviousLocation = FVector::ZeroVector;
	bool bHasPreviousLocation = false;
	float CurrentRoughness = 0.f;

	double LastBreachTime = -1000.0;
	double LastBailTime = -1000.0;
	double LastPatchTime = -1000.0;
	bool bPatchKeyWasDown = false;
	bool bLoggedFreePatch = false;
	double SprayHintUntil = -1000.0;
	double LastSprayHintTime = -1000.0;

	/** Where the boat started (beside the home dock): the harbor of last resort. */
	FVector HomeMooringLocation = FVector::ZeroVector;
	FRotator HomeMooringRotation = FRotator::ZeroRotator;

	/** Whose screen we faded, so it is always cleared again (even if they stepped ashore mid-fade). */
	TWeakObjectPtr<APlayerController> FadingController;

	/** For the "back home" message after the fade. */
	FText LastHarborName;
};
