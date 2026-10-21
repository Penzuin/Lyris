// Lyris player: walking, sprint, jump and climbing, with Breath (ULyrisStaminaComponent) paying
// for sprint and climb. Tuning lives in Project Settings > Game > Lyris Movement.
//
// - Walk is free; sprint is a max-speed swap that drains Breath only while moving on the ground.
// - Jump is free (a sprint jump costs a little), with coyote time, a jump buffer and variable
//   height (let go early and upward speed is cut).
// - Climbing is a custom movement mode. Walk into a climbable wall while airborne, or keep pushing
//   into one while on the ground, to grab it. Move along it with the stick; jump to leap up, or
//   jump with the stick pulled away from the wall to kick off. Reaching the top pulls you up for free.
//   Running out of Breath on a wall makes you let go. Anything tagged NoClimb can't be climbed.
// - Swimming (T20, ULyrisSwimComponent in MOVE_Flying) never touches Breath.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "LyrisCharacterMovementComponent.generated.h"

class ULyrisStaminaComponent;
class ULyrisMovementSettings;

/** Lyris custom movement modes (used with MOVE_Custom). */
UENUM(BlueprintType)
enum class ELyrisMovementMode : uint8
{
	None = 0 UMETA(Hidden),
	Climbing = 1,
};

UCLASS(ClassGroup = (Lyris))
class LYRIS_API ULyrisCharacterMovementComponent : public UCharacterMovementComponent
{
	GENERATED_BODY()

public:
	ULyrisCharacterMovementComponent();

	// ---- Input (set by ALyrisCharacter; also carried in saved moves so the server agrees) ----

	/** Sprint button state (hold or toggle, already combined by the character). */
	void SetSprintInput(bool bPressed) { bSprintInput = bPressed; }
	bool GetSprintInput() const { return bSprintInput; }

	/** Jump button state. A press starts the jump buffer; a release while rising cuts the jump short. */
	void SetJumpInput(bool bPressed) { bJumpInput = bPressed; }
	bool GetJumpInput() const { return bJumpInput; }

	// ---- State ----

	UFUNCTION(BlueprintPure, Category = "Lyris|Movement")
	bool IsClimbing() const;

	/** True while pulling up over the top of a wall. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Movement")
	bool IsMantling() const { return IsClimbing() && bMantling; }

	/** True while actually sprinting: button held, Breath left, moving on the ground. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Movement")
	bool IsSprinting() const;

	/** Outward normal of the wall being climbed (zero when not climbing). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Movement")
	FVector GetClimbNormal() const { return IsClimbing() ? ClimbNormal : FVector::ZeroVector; }

	/** The Breath pool on the owning character, if any. Without one, movement costs nothing. */
	ULyrisStaminaComponent* GetStamina() const;

	// ---- UCharacterMovementComponent ----
	virtual void BeginPlay() override;
	virtual float GetMaxSpeed() const override;
	virtual bool CanAttemptJump() const override;
	virtual void PhysicsRotation(float DeltaTime) override;
	virtual void UpdateCharacterStateBeforeMovement(float DeltaSeconds) override;
	virtual FNetworkPredictionData_Client* GetPredictionData_Client() const override;

protected:
	virtual void PhysCustom(float deltaTime, int32 Iterations) override;
	virtual void OnMovementModeChanged(EMovementMode PreviousMovementMode, uint8 PreviousCustomMode) override;
	virtual void OnMovementUpdated(float DeltaSeconds, const FVector& OldLocation, const FVector& OldVelocity) override;
	virtual void UpdateFromCompressedFlags(uint8 Flags) override;

private:
	// Inputs
	bool bSprintInput = false;
	bool bJumpInput = false;
	bool bJumpInputLastFrame = false;

	// Jump feel
	float JumpBufferRemaining = 0.f;
	float CoyoteRemaining = 0.f;
	bool bJumpCutAvailable = false;

	// Climbing
	FVector ClimbNormal = FVector::ZeroVector;
	float LeapTimeRemaining = 0.f;
	float RegrabCooldown = 0.f;
	float GroundPushTime = 0.f;

	// Mantle (the free pull-up at the top of a wall)
	bool bMantling = false;
	float MantleElapsed = 0.f;
	FVector MantleStart = FVector::ZeroVector;
	FVector MantleTarget = FVector::ZeroVector;

	mutable TWeakObjectPtr<ULyrisStaminaComponent> CachedStamina;

	/** Pushes Project Settings values onto the base component (walk speed, air control, jump speed). */
	void ApplySettings();

	/** Stick input as a world vector, length 0 to 1. */
	FVector GetInputVector() const;

	/** True if the button is held and there is Breath for it (ignores whether you are moving). */
	bool WantsToSprint() const;

	/** Breath helpers. They respect client replays and simulated proxies, so Breath is never spent twice. */
	bool ShouldApplyBreath() const;
	bool HasBreathToClimb() const;
	bool TrySpendBreath(float Amount);
	void DrainBreath(float Amount);

	// Jump
	void TickJump(float DeltaSeconds);
	void DoLyrisJump();

	// Climb
	void TryGrabWall(float DeltaSeconds);
	bool TraceClimbWall(const FVector& From, const FVector& Direction, float Length, FHitResult& OutHit) const;
	bool IsClimbableSurface(const FHitResult& Hit) const;
	void StartClimbing(const FHitResult& WallHit);
	void StopClimbing(EMovementMode NewMode);
	void PhysClimbing(float deltaTime, int32 Iterations);
	bool TryStartMantle();
	void PhysMantle(float deltaTime, int32 Iterations);
	FVector GetClimbNormalFlat() const;
	FQuat GetClimbRotation() const;
};
