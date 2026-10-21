// Lyris combat: placeholder effects built from basic shapes until real VFX exist.
// A burst is an expanding, fading sphere with a short flash of light.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "LyrisCombatFx.generated.h"

class UStaticMeshComponent;
class UStaticMesh;
class UPointLightComponent;
class UMaterialInstanceDynamic;

UCLASS()
class LYRIS_API ALyrisCombatFx : public AActor
{
	GENERATED_BODY()

public:
	ALyrisCombatFx();

	virtual void Tick(float DeltaSeconds) override;

	/** Spawns a burst: grows from InStartRadius to InEndRadius over InLifetime while fading.
	 *  bGroundRing: a flat shockwave disc at Location (for area attacks), else a small spark. */
	static ALyrisCombatFx* Burst(UWorld* World, const FVector& Location, const FLinearColor& InColour,
		float InStartRadius, float InEndRadius, float InLifetime, float LightIntensity = 6000.f, bool bGroundRing = false);

private:
	UPROPERTY(VisibleAnywhere, Category = "Fx")
	TObjectPtr<UStaticMeshComponent> Shape;

	UPROPERTY()
	TObjectPtr<UStaticMesh> RingMesh;

	UPROPERTY(VisibleAnywhere, Category = "Fx")
	TObjectPtr<UPointLightComponent> Light;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> Material;

	FLinearColor Colour = FLinearColor::White;
	float StartRadius = 50.f;
	float EndRadius = 300.f;
	float Lifetime = 0.4f;
	float Age = 0.f;
	float PeakLight = 6000.f;
	bool bRing = false;

	FVector ScaleFor(float Radius) const;
};
