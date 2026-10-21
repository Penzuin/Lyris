// Lyris player: swimming in the shared sea (T20). Calm by default: no drowning, no stamina, no damage.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/EngineTypes.h"
#include "LyrisSwimComponent.generated.h"

class ACharacter;
class UCharacterMovementComponent;
class ULyrisOceanSubsystem;
class APlayerController;

/**
 * Lets the owning character swim in the sea that ULyrisOceanSubsystem describes.
 *
 * How it works (no water physics volume needed):
 *  - In deep water the character switches to MOVE_Flying. Flying gives normal input-driven horizontal
 *    movement with collision and step-up, and no gravity. This component then owns the vertical axis:
 *    a damped spring keeps the body at FloatDepth below the wave surface, so the swimmer rides the swell.
 *  - Jump while swimming is a short kick up (the spring brings you back down).
 *  - Swim into a low ledge (dock, rock, shore lip) and you climb out onto it; swim into shallows and you
 *    simply stand up and walk.
 *  - Drift too far from home for too long and the screen fades and the tide brings you back to the dock.
 *
 * The component ticks before the character movement component each frame.
 */
UCLASS(ClassGroup = (Lyris), meta = (BlueprintSpawnableComponent))
class LYRIS_API ULyrisSwimComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	ULyrisSwimComponent();

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** True while floating in the sea (including while climbing out). */
	UFUNCTION(BlueprintPure, Category = "Swimming")
	bool IsSwimming() const { return bSwimming; }

	/** True during the short climb-out onto a dock or ledge. Handy for the anim blueprint later. */
	UFUNCTION(BlueprintPure, Category = "Swimming")
	bool IsClimbingOut() const { return bClimbing; }

	/**
	 * Called by the character's Jump. While swimming: climb out if a ledge is right in front, otherwise
	 * kick up briefly. Returns true if the jump was used for swimming (so the normal jump is skipped).
	 */
	UFUNCTION(BlueprintCallable, Category = "Swimming")
	bool HandleJumpPressed();

	// ---- Floating ----

	/** How far the character's centre sits below the surface while floating (cm). Head and shoulders stay above. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Floating")
	float FloatDepth = 45.f;

	/** How tightly the body follows the waves (spring frequency, 1/s). Higher = stiffer. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Floating", meta = (ClampMin = "0.5"))
	float BuoyancyFrequency = 6.f;

	/** Spring damping ratio. 1 = no overshoot, lower = bouncier. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Floating", meta = (ClampMin = "0.1", ClampMax = "2.0"))
	float BuoyancyDamping = 0.8f;

	/** Fraction of the surface's orbital velocity that pushes the swimmer sideways. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Floating", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float DriftScale = 0.25f;

	/** Fastest downward speed kept when splashing in (cm/s), so a fall becomes a short dip. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Floating")
	float MaxEntrySinkSpeed = 250.f;

	// ---- Swimming ----

	/** Gentle swim speed (cm/s). Walking is 500. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Movement")
	float SwimSpeed = 280.f;

	/** How quickly you glide to a stop when you let go (cm/s^2). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Movement")
	float SwimBraking = 500.f;

	/** Upward speed of a kick (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Movement")
	float KickSpeed = 600.f;

	/** Seconds between kicks. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Movement")
	float KickCooldown = 0.6f;

	// ---- Entering and leaving the water ----

	/** Start swimming when the water under you is deeper than this (cm). The character is about 190 cm tall. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Shore")
	float EnterDepth = 155.f;

	/** Stand up and walk when the water under you is shallower than this (cm). Keep below EnterDepth. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Shore")
	float ExitDepth = 135.f;

	/** Minimum seconds between switching swim <-> walk, so a passing wave can't make it flicker. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Shore")
	float MinStateTime = 0.5f;

	/** Highest ledge above the water you can climb out onto (cm). The dock top is about 72 cm. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Shore")
	float ClimbMaxHeight = 150.f;

	/** Lowest ledge above the water that counts as climbable (cm). Anything lower you just wade out onto. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Shore")
	float ClimbMinHeight = 15.f;

	/** How long the climb-out takes (s). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Shore", meta = (ClampMin = "0.1"))
	float ClimbDuration = 0.6f;

	// ---- The tide brings you home ----

	/**
	 * Points that count as "near home". At BeginPlay these are replaced by every actor tagged TideHomeTag
	 * (or DockPointTag); the defaults are only kept, with a warning, if the level has none. Boats count too.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Tide")
	TArray<FVector> HomeAnchors;

	/** Swimming further than this from every home anchor and every boat counts as far out (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Tide")
	float FarDistance = 8000.f;

	/** Seconds far out before a gentle nudge appears. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Tide")
	float FarWarnTime = 8.f;

	/** Seconds far out before the tide carries you home. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Tide")
	float FarReturnTime = 20.f;

	/**
	 * Where the tide puts you (standing height on the dock). At BeginPlay this becomes the nearest actor tagged
	 * TideHomeTag (lyris_build_world.py puts that TargetPoint on Lantern Pier's deck at standing height),
	 * or DockPointTag. The default is the retired Harbor map's dock and is only a last resort.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Tide")
	FVector ReturnPoint = FVector(3000.f, 150.f, 170.f);

	/** Actor tag for tide-home points (see lyris_build_world.py). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Tide")
	FName TideHomeTag = TEXT("LyrisTideHome");

	/** Fallback actor tag if no tide-home point is tagged: the dock's step-ashore point. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Tide")
	FName DockPointTag = TEXT("LyrisDockPoint");

	/** Facing after the tide brings you home (world yaw, degrees). 180 looks back along the dock to the island. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Tide")
	float ReturnYaw = 180.f;

	/** Seconds for the fade out, and again for the fade in. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Swimming|Tide")
	float ReturnFadeTime = 1.2f;

protected:
	virtual void BeginPlay() override;

	/** Replaces ReturnPoint and HomeAnchors with the tagged tide-home actors in the level, if any. */
	void FindTideHome();
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	enum class EReturnPhase : uint8 { None, FadingOut, FadingIn };

	UPROPERTY(Transient)
	TObjectPtr<ACharacter> Character;

	UPROPERTY(Transient)
	TObjectPtr<UCharacterMovementComponent> Movement;

	bool bSwimming = false;
	bool bClimbing = false;
	float VerticalSpeed = 0.f;
	float StateTime = 0.f;
	float KickCooldownLeft = 0.f;

	FVector ClimbFrom = FVector::ZeroVector;
	FVector ClimbTo = FVector::ZeroVector;
	float ClimbAlpha = 0.f;

	float FarTime = 0.f;
	float FarCheckTimer = 0.f;
	float ClimbCheckTimer = 0.f;
	bool bIsFar = false;
	EReturnPhase ReturnPhase = EReturnPhase::None;
	float ReturnTimer = 0.f;
	TWeakObjectPtr<APlayerController> FadeController;

	// Movement settings we change while swimming, restored when we stop.
	float SavedMaxFlySpeed = 0.f;
	float SavedBrakingFlying = 0.f;

	ULyrisOceanSubsystem* GetOcean() const;
	float GetWaterHeight(const FVector& Location) const;
	FVector GetWaterVelocity(const FVector& Location) const;

	/** Depth of water below the surface at Location, down to MaxDepth. Returns MaxDepth if no ground was found. */
	float ProbeWaterDepth(const FVector& Location, float WaterZ, float MaxDepth, FHitResult* OutGround = nullptr) const;

	void StartSwimming();
	void StopSwimming(EMovementMode NewMode);
	void UpdateFloating(float DeltaTime, float WaterZ);
	bool TryStartClimb(const FVector2D& Direction, float WaterZ);
	void UpdateClimb(float DeltaTime);
	void UpdateTide(float DeltaTime);
	void UpdateReturn(float DeltaTime);
	bool IsFarFromHome() const;
	bool IsAboardOrDisabled() const;
	void Hint(int32 Slot, const FString& Text, float Seconds = 0.15f) const;
};
