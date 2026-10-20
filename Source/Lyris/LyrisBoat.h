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

	/** Height of the sea surface. */
	UPROPERTY(EditAnywhere, Category = "Sailing")
	float WaterHeight = 0.f;

	/** The lamps' reach: the mist turns you back beyond this distance from the island. */
	UPROPERTY(EditAnywhere, Category = "Sailing")
	float WorldRadius = 55000.f;

	/** How close the player must stand to board. */
	UPROPERTY(EditAnywhere, Category = "Boarding")
	float BoardRadius = 750.f;

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

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY()
	TObjectPtr<APawn> StoredWalker;

	float Sail = 0.f;
	float Speed = 0.f;
	float Rudder = 0.f;
	float Clock = 0.f;
	float CameraYaw = 0.f;
	float CameraPitch = -14.f;
	bool bInteractWasDown = false;

	/** This tick's reading of the shared world wind. */
	FLyrisWindSample Wind;

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
	void Hint(int32 Slot, const FString& Text, const FColor& Color = FColor(240, 233, 220)) const;
};
