// Lyris sailing prototype: a small sailboat the player can board at the dock and sail with the wind.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "Sailing/LyrisWindSubsystem.h"
#include "LyrisBoat.generated.h"

class UBoxComponent;
class UStaticMeshComponent;
class UStaticMesh;
class UMaterialInterface;
class USpringArmComponent;
class UCameraComponent;
class APlayerController;

/**
 * Controls while aboard:
 *   W / S  raise / lower the sail
 *   A / D  steer
 *   Mouse  look around
 *   E      step ashore (only near the dock)
 *
 * Speed depends on the sail and on the angle to the wind: sailing straight into the
 * wind barely moves, a beam reach (wind from the side) is fastest.
 *
 * The wind itself is shared by the whole world: every boat reads ULyrisWindSubsystem
 * (tuned in Project Settings > Game > Lyris Wind).
 *
 * The boat floats on the shared sea (ULyrisOceanSubsystem, T17): a few float points on the hull sample
 * the water height, the hull rides at their average plus FreeboardOffset, and pitch and roll come from a
 * plane fitted through them. Everything is smoothed by critically damped springs. The boat stays
 * kinematic (no physics simulation). Without an ocean subsystem it sits on the flat WaterHeight.
 *
 * Fell overboard? You swim (ULyrisSwimComponent, T20). Swim to the ladder on the port quarter, or
 * anywhere within BoardRadius, and press E to climb aboard.
 */
UCLASS()
class LYRIS_API ALyrisBoat : public APawn
{
	GENERATED_BODY()

public:
	ALyrisBoat();

	virtual void Tick(float DeltaSeconds) override;

	/** Top speed in cm/s with full sail on the best point of sail. */
	UPROPERTY(EditAnywhere, Category = "Sailing")
	float MaxSpeed = 900.f;

	/** Degrees per second at full rudder and good steerage. */
	UPROPERTY(EditAnywhere, Category = "Sailing")
	float TurnRate = 38.f;

	/** How fast the sail goes up or down (fraction per second). */
	UPROPERTY(EditAnywhere, Category = "Sailing")
	float SailChangeRate = 0.6f;

	/** Height of the flat sea, used only when there is no ocean subsystem (e.g. an editor preview). */
	UPROPERTY(EditAnywhere, Category = "Sailing")
	float WaterHeight = 0.f;

	// ---- Floating on the shared sea (T18) ----

	/**
	 * Float points in hull space (X forward, Y to starboard), in cm. The water height is sampled under
	 * each; the hull rides at their average and tilts with a plane fitted through them. Defaults: bow,
	 * stern, port, starboard. Needs at least 3 points that are not all in a line to tilt.
	 */
	UPROPERTY(EditAnywhere, Category = "Floating")
	TArray<FVector2D> FloatPoints;

	/** How far the actor origin sits above the mean water under the float points (cm). */
	UPROPERTY(EditAnywhere, Category = "Floating")
	float FreeboardOffset = 25.f;

	/** Spring speed for rising and falling with the swell (rad/s). Higher follows the water more tightly. */
	UPROPERTY(EditAnywhere, Category = "Floating", meta = (ClampMin = "0.1"))
	float HeaveFrequency = 2.4f;

	/** Spring speed for pitching and rolling with the swell (rad/s). */
	UPROPERTY(EditAnywhere, Category = "Floating", meta = (ClampMin = "0.1"))
	float TiltFrequency = 2.8f;

	/** Largest pitch the waves can give the hull (degrees). */
	UPROPERTY(EditAnywhere, Category = "Floating", meta = (ClampMin = "0.0"))
	float MaxWavePitch = 14.f;

	/** Largest roll the waves can give the hull, before wind heel (degrees). */
	UPROPERTY(EditAnywhere, Category = "Floating", meta = (ClampMin = "0.0"))
	float MaxWaveRoll = 12.f;

	/** Fraction of the surface's orbital velocity that moves the boat while the sail is down. */
	UPROPERTY(EditAnywhere, Category = "Floating", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float DriftScale = 0.3f;

	/** Speed lost at most when the bow is climbing a steep swell (0.2 = up to 20% slower). */
	UPROPERTY(EditAnywhere, Category = "Floating", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float SwellSlowdown = 0.2f;

	/** Bow-up pitch (degrees) at which the full SwellSlowdown applies. */
	UPROPERTY(EditAnywhere, Category = "Floating", meta = (ClampMin = "0.1"))
	float SwellSlowdownPitch = 8.f;

	// ---- Bow spray ----

	/** Below this speed (cm/s) there is no bow spray. */
	UPROPERTY(EditAnywhere, Category = "Spray")
	float SprayMinSpeed = 300.f;

	/** Where the bow spray comes from, in hull space (cm). */
	UPROPERTY(EditAnywhere, Category = "Spray")
	FVector SprayOffset = FVector(320.f, 0.f, -15.f);

	/** 0 = no spray, 1 = full spray. Updated every tick. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Transient, Category = "Spray")
	float BowSprayIntensity = 0.f;

	/**
	 * Hook for the bow spray effect (no particle asset exists yet). Called every tick while there is spray,
	 * and once more with Intensity 0 when it stops. A Blueprint child can spawn or drive a Niagara system
	 * here. Location and Direction are in world space; Direction points forward along the hull.
	 */
	UFUNCTION(BlueprintImplementableEvent, Category = "Spray")
	void OnBowSpray(float Intensity, FVector Location, FVector Direction);

	/** The lamps' reach: the mist turns you back beyond this distance from the island. */
	UPROPERTY(EditAnywhere, Category = "Sailing")
	float WorldRadius = 55000.f;

	/** How close the player must be to board (from the hull centre, cm). */
	UPROPERTY(EditAnywhere, Category = "Boarding")
	float BoardRadius = 750.f;

	/** A swimmer this close to the boarding ladder can always climb aboard (cm). */
	UPROPERTY(EditAnywhere, Category = "Boarding")
	float LadderRadius = 260.f;

	/** Where the player is placed when stepping ashore. */
	UPROPERTY(EditAnywhere, Category = "Boarding")
	FVector DockPoint = FVector(3000.f, 150.f, 170.f);

	/** How close the boat must be to the dock point to step ashore. */
	UPROPERTY(EditAnywhere, Category = "Boarding")
	float DockRadius = 1300.f;

private:
	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UBoxComponent> HullCollision;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USceneComponent> Visual;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USceneComponent> SailPivot;

	/** Boarding ladder on the port quarter, built from basic shapes. Rides with the hull. */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USceneComponent> BoardingLadder;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY()
	TObjectPtr<APawn> StoredWalker;

	float Sail = 0.f;
	float Speed = 0.f;
	float Rudder = 0.f;
	float CameraYaw = 0.f;
	float CameraPitch = -14.f;
	bool bInteractWasDown = false;

	/** This tick's reading of the shared world wind. */
	FLyrisWindSample Wind;

	// Floating springs (critically damped). Heave is the actor Z; pitch and roll tilt Visual.
	bool bFloatInitialized = false;
	float HeaveVelocity = 0.f;
	float WavePitch = 0.f;
	float WavePitchVelocity = 0.f;
	float HullRoll = 0.f;
	float HullRollVelocity = 0.f;
	FVector2D DriftVelocity = FVector2D::ZeroVector;

	UStaticMeshComponent* MakePart(FName Name, UStaticMesh* Mesh, USceneComponent* Parent, FVector Location,
		FVector Scale, UMaterialInterface* Material, FRotator Rotation = FRotator::ZeroRotator);

	/** Reads the shared world wind once per tick into Wind. */
	void RefreshWind();
	float GetWindYaw() const { return Wind.Yaw; }
	float GetWindStrength() const { return Wind.Strength; }
	float GetSailEfficiency(float RelativeWindDeg, FString& OutPointOfSail) const;

	void Board(APlayerController* PC, APawn* Walker);
	void StepAshore(APlayerController* PC);
	void UpdateSailing(float DeltaSeconds, APlayerController* PC);
	void UpdateFloating(float DeltaSeconds);
	void UpdateBowSpray();

	/** Water surface height at a world XY: the ocean if there is one, otherwise the flat WaterHeight. */
	float SampleWaterHeight(const FVector2D& WorldXY) const;

	/** 1 normally, down to 1 - SwellSlowdown while the bow climbs a steep swell. */
	float GetSwellSpeedFactor() const;

	/** True if Walker is close enough to the hull or the ladder to climb aboard. */
	bool CanBoardFrom(const APawn* Walker) const;
	void Hint(int32 Slot, const FString& Text, const FColor& Color = FColor(240, 233, 220)) const;
};
