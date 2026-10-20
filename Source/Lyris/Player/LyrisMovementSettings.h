// Lyris player: tuning for walking, sprint, jump, climbing and the Breath stamina pool.
// Edit in Project Settings > Game > Lyris Movement (saved to Config/DefaultGame.ini under
// [/Script/Lyris.LyrisMovementSettings]). Values are read live, so changes apply during Play In Editor.
//
// Ported from the approved reference prototype (wayfarers_breath.html, tuning object `T`) and
// design/movement_stamina.md. Distances are Unreal units (1 m = 100 uu).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "LyrisMovementSettings.generated.h"

/**
 * Walking and jumping are free. Sprinting and climbing draw from one pool, Breath.
 * Running dry leaves you Winded (no sprint, no climb, you let go of walls) until Breath refills
 * to WindedClearsAtFraction. Swimming never uses Breath. There is no fall damage.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Lyris Movement"))
class LYRIS_API ULyrisMovementSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	ULyrisMovementSettings();

	static const ULyrisMovementSettings* Get() { return GetDefault<ULyrisMovementSettings>(); }

	// ---- Walk and sprint ----

	/** Walking speed, uu/s. Free. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Walk and Sprint", meta = (ClampMin = "0.0", UIMax = "1500.0"))
	float WalkSpeed = 450.f;

	/** Sprint speed, uu/s. Hold Left Shift or click the left stick. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Walk and Sprint", meta = (ClampMin = "0.0", UIMax = "2000.0"))
	float SprintSpeed = 720.f;

	/** Breath per second while sprinting and moving on the ground. Sprinting in the air is free. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Walk and Sprint", meta = (ClampMin = "0.0", UIMax = "100.0"))
	float SprintBreathPerSecond = 18.f;

	/** How much you can steer in the air, 0 to 1. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Walk and Sprint", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float AirControl = 0.6f;

	// ---- Jump ----

	/** Height of a full (held) jump, uu. The launch speed is worked out from gravity. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Jump", meta = (ClampMin = "0.0", UIMax = "500.0"))
	float JumpApexHeight = 120.f;

	/** Letting go of jump while still rising multiplies upward speed by this (short hop). 1 = no variable height. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Jump", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float JumpReleaseVelocityScale = 0.5f;

	/** Breath a jump costs while sprinting. A normal jump is free. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Jump", meta = (ClampMin = "0.0", UIMax = "50.0"))
	float SprintJumpBreath = 5.f;

	/** Seconds after walking off a ledge during which a jump still works. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Jump", meta = (ClampMin = "0.0", UIMax = "0.5"))
	float CoyoteTime = 0.12f;

	/** Seconds a jump press is remembered before landing (or grabbing a wall). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Jump", meta = (ClampMin = "0.0", UIMax = "0.5"))
	float JumpBufferTime = 0.15f;

	// ---- Climb ----

	/** Climbing speed along the wall, uu/s. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "1000.0"))
	float ClimbSpeed = 220.f;

	/** Breath per second while climbing and moving. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "100.0"))
	float ClimbBreathPerSecond = 10.f;

	/** Breath per second while holding still on a wall. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "100.0"))
	float HangBreathPerSecond = 3.f;

	/** Breath for a climb leap (jump while climbing): a short upward lunge. Also the HUD's leap cost preview. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "100.0"))
	float ClimbLeapBreath = 20.f;

	/** How far a climb leap carries you up the wall, uu. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "500.0"))
	float ClimbLeapHeight = 150.f;

	/** How long a climb leap lasts, seconds. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.05", UIMax = "1.0"))
	float ClimbLeapDuration = 0.22f;

	/** Breath for a wall kick (jump while climbing with the stick pulled away from the wall). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "100.0"))
	float WallKickBreath = 12.f;

	/** Speed a wall kick pushes you away from the wall, uu/s. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "2000.0"))
	float WallKickOutSpeed = 600.f;

	/** Upward speed of a wall kick, uu/s. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "2000.0"))
	float WallKickUpSpeed = 520.f;

	/** Seconds after a wall kick before you can grab a wall again. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "2.0"))
	float WallKickRegrabDelay = 0.3f;

	/** Seconds after letting go because you are Winded before you can grab again. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "2.0"))
	float WindedRegrabDelay = 0.6f;

	/** A surface is climbable if it is at least this many degrees away from flat ground (90 = sheer wall). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "30.0", ClampMax = "90.0"))
	float ClimbMinSurfaceAngle = 60.f;

	/** How far past vertical (an overhang) a wall can lean and still be climbable, degrees. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", ClampMax = "60.0"))
	float ClimbMaxOverhangAngle = 20.f;

	/** How far beyond the capsule edge a wall can be and still be grabbed, uu. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "1.0", UIMax = "200.0"))
	float ClimbReach = 30.f;

	/** Gap kept between the capsule and the wall while climbing, uu. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "30.0"))
	float ClimbWallGap = 4.f;

	/** Seconds you must push into a wall while standing on the ground before you start climbing it. In the air, grabbing is instant. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", UIMax = "1.0"))
	float GroundGrabDelay = 0.1f;

	/** How directly the stick must point into the wall to grab it (dot product, 0 to 1). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float ClimbGrabInputThreshold = 0.6f;

	/** How directly the stick must point away from the wall for jump to be a wall kick instead of a leap. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float WallKickInputThreshold = 0.5f;

	/** Seconds the free pull-up at the top of a wall takes. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb", meta = (ClampMin = "0.05", UIMax = "1.0"))
	float MantleDuration = 0.3f;

	/** Actors or components with this tag can never be climbed. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Climb")
	FName NoClimbTag = TEXT("NoClimb");

	// ---- Breath ----

	/** Breath a new character starts with. Upgrades can raise it up to MaxBreathCap. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Breath", meta = (ClampMin = "1.0", UIMax = "200.0"))
	float MaxBreath = 100.f;

	/** The most Breath upgrades can ever reach. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Breath", meta = (ClampMin = "1.0", UIMax = "400.0"))
	float MaxBreathCap = 200.f;

	/** The most bonus Breath (food, tea) you can hold at once. Bonus is spent before the main pool. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Breath", meta = (ClampMin = "0.0", UIMax = "200.0"))
	float MaxBonusBreath = 100.f;

	/** Seconds after the last spend before Breath starts to refill. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Breath", meta = (ClampMin = "0.0", UIMax = "5.0"))
	float RecoveryDelay = 0.8f;

	/** Refill rate when recovery starts, Breath per second. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Breath", meta = (ClampMin = "0.0", UIMax = "200.0"))
	float RecoveryRateStart = 20.f;

	/** Refill rate once fully ramped up, Breath per second. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Breath", meta = (ClampMin = "0.0", UIMax = "200.0"))
	float RecoveryRateFull = 50.f;

	/** Seconds to ramp from the start rate to the full rate. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Breath", meta = (ClampMin = "0.0", UIMax = "5.0"))
	float RecoveryRampTime = 1.5f;

	/** Refill rate multiplier while Winded. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Breath", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float WindedRecoveryScale = 0.7f;

	/** Winded clears once Breath refills to this share of max (0.35 = 35 of 100). */
	UPROPERTY(Config, EditAnywhere, BlueprintReadOnly, Category = "Breath", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float WindedClearsAtFraction = 0.35f;
};
