#include "Combat/LyrisCombatFx.h"

#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

ALyrisCombatFx::ALyrisCombatFx()
{
	PrimaryActorTick.bCanEverTick = true;
	SetCanBeDamaged(false);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereFinder(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderFinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	RingMesh = CylinderFinder.Succeeded() ? CylinderFinder.Object : nullptr;
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MatFinder(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));

	Shape = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Shape"));
	RootComponent = Shape;
	Shape->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Shape->SetCastShadow(false);
	if (SphereFinder.Succeeded())
	{
		Shape->SetStaticMesh(SphereFinder.Object);
	}
	if (MatFinder.Succeeded())
	{
		Shape->SetMaterial(0, MatFinder.Object);
	}

	Light = CreateDefaultSubobject<UPointLightComponent>(TEXT("Light"));
	Light->SetupAttachment(Shape);
	Light->SetCastShadows(false);
	Light->SetAttenuationRadius(900.f);
}

ALyrisCombatFx* ALyrisCombatFx::Burst(UWorld* World, const FVector& Location, const FLinearColor& InColour,
	float InStartRadius, float InEndRadius, float InLifetime, float LightIntensity, bool bGroundRing)
{
	if (!World)
	{
		return nullptr;
	}
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ALyrisCombatFx* Fx = World->SpawnActor<ALyrisCombatFx>(Location, FRotator::ZeroRotator, Params);
	if (!Fx)
	{
		return nullptr;
	}
	Fx->Colour = InColour;
	Fx->StartRadius = InStartRadius;
	Fx->EndRadius = InEndRadius;
	Fx->Lifetime = FMath::Max(0.05f, InLifetime);
	Fx->PeakLight = LightIntensity;
	Fx->bRing = bGroundRing && Fx->RingMesh;
	if (Fx->bRing)
	{
		Fx->Shape->SetStaticMesh(Fx->RingMesh);
		Fx->Light->SetRelativeLocation(FVector(0.f, 0.f, 6000.f));  // scaled by the flat disc: ~1 m up
	}
	Fx->Material = Fx->Shape->CreateAndSetMaterialInstanceDynamic(0);
	if (Fx->Material)
	{
		Fx->Material->SetVectorParameterValue(TEXT("Color"), InColour);
	}
	Fx->Light->SetLightColor(InColour);
	Fx->Light->SetIntensity(LightIntensity);
	Fx->SetActorScale3D(Fx->ScaleFor(InStartRadius));
	return Fx;
}

FVector ALyrisCombatFx::ScaleFor(float Radius) const
{
	// Basic shapes are 100 units across. A ring is a disc 2 cm thick lying on the ground.
	return bRing ? FVector(Radius / 50.f, Radius / 50.f, 0.02f) : FVector(Radius / 50.f);
}

void ALyrisCombatFx::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Age += DeltaSeconds;
	const float T = FMath::Clamp(Age / Lifetime, 0.f, 1.f);
	const float Ease = 1.f - FMath::Square(1.f - T);  // fast out, slow settle
	SetActorScale3D(ScaleFor(FMath::Lerp(StartRadius, EndRadius, Ease)));
	Light->SetIntensity(PeakLight * (1.f - T));
	if (Material)
	{
		// The basic shape material is opaque, so fade the colour toward dark instead of alpha.
		Material->SetVectorParameterValue(TEXT("Color"), Colour * (1.f - 0.85f * T));
	}
	if (Age >= Lifetime)
	{
		Destroy();
	}
}
