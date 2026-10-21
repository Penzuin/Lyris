// Lyris interaction: finds the best thing to use in front of the player and uses it.

#include "LyrisInteractionComponent.h"

#include "LyrisInteractable.h"
#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "Engine/EngineTypes.h"
#include "Engine/OverlapResult.h"
#include "Engine/World.h"
#include "Components/PrimitiveComponent.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Controller.h"
#include "GameFramework/Pawn.h"

ULyrisInteractionComponent::ULyrisInteractionComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
}

void ULyrisInteractionComponent::BeginPlay()
{
	Super::BeginPlay();
	SetComponentTickInterval(ScanInterval);
}

void ULyrisInteractionComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (bScanningEnabled)
	{
		RefreshTarget();
	}
}

void ULyrisInteractionComponent::SetScanningEnabled(bool bEnabled)
{
	bScanningEnabled = bEnabled;
	if (!bScanningEnabled)
	{
		SetTarget(nullptr);
	}
}

void ULyrisInteractionComponent::RefreshTarget()
{
	SetTarget(bScanningEnabled ? FindBestTarget() : nullptr);
}

bool ULyrisInteractionComponent::TryInteract()
{
	AActor* Target = CurrentTarget.Get();
	AActor* Owner = GetOwner();
	if (!Target || !Owner || !Target->GetClass()->ImplementsInterface(ULyrisInteractable::StaticClass()))
	{
		return false;
	}

	// The world may have changed since the last scan (someone else gathered the node).
	if (!ILyrisInteractable::Execute_CanInteract(Target, Owner))
	{
		RefreshTarget();
		return false;
	}

	ILyrisInteractable::Execute_Interact(Target, Owner);
	OnInteracted.Broadcast(Target);

	// Interacting usually changes the prompt ("Plant" -> "Water"), so rescan straight away.
	RefreshTarget();
	return true;
}

void ULyrisInteractionComponent::GetViewPoint(FVector& OutLocation, FVector& OutDirection) const
{
	const AActor* Owner = GetOwner();
	OutLocation = Owner ? Owner->GetActorLocation() : FVector::ZeroVector;
	OutDirection = Owner ? Owner->GetActorForwardVector() : FVector::ForwardVector;

	if (const APawn* Pawn = Cast<APawn>(Owner))
	{
		if (const AController* Controller = Pawn->GetController())
		{
			FRotator ViewRotation;
			Controller->GetPlayerViewPoint(OutLocation, ViewRotation);
			OutDirection = ViewRotation.Vector();
		}
	}
}

FVector ULyrisInteractionComponent::GetAimLocation() const
{
	const AActor* Owner = GetOwner();
	UWorld* World = GetWorld();
	if (!Owner)
	{
		return FVector::ZeroVector;
	}

	FVector ViewLocation;
	FVector ViewDirection;
	GetViewPoint(ViewLocation, ViewDirection);
	FVector FlatView = FVector(ViewDirection.X, ViewDirection.Y, 0.f).GetSafeNormal();
	if (FlatView.IsNearlyZero())
	{
		FlatView = Owner->GetActorForwardVector().GetSafeNormal2D();
	}

	const FVector Ahead = Owner->GetActorLocation() + FlatView * AimDistance;
	if (!World)
	{
		return Ahead;
	}

	// Drop straight down from a little above the owner's head to find the ground.
	FCollisionQueryParams TraceParams(SCENE_QUERY_STAT(LyrisInteractionAim), false, Owner);
	FHitResult Hit;
	const FVector Start = Ahead + FVector(0.f, 0.f, 200.f);
	const FVector End = Ahead - FVector(0.f, 0.f, 400.f);
	if (World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, TraceParams))
	{
		return Hit.ImpactPoint;
	}
	return Ahead;
}

AActor* ULyrisInteractionComponent::FindBestTarget() const
{
	AActor* Owner = GetOwner();
	UWorld* World = GetWorld();
	if (!Owner || !World)
	{
		return nullptr;
	}

	FVector ViewLocation;
	FVector ViewDirection;
	GetViewPoint(ViewLocation, ViewDirection);

	// Judge "in front" on the ground plane so looking up or down at a rock doesn't lose it.
	FVector FlatView = FVector(ViewDirection.X, ViewDirection.Y, 0.f).GetSafeNormal();
	if (FlatView.IsNearlyZero())
	{
		FlatView = Owner->GetActorForwardVector().GetSafeNormal2D();
	}

	const FVector Origin = Owner->GetActorLocation();
	const float MinDot = FMath::Cos(FMath::DegreesToRadians(MaxAngleDegrees));

	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(LyrisInteractionScan), false, Owner);
	TArray<FOverlapResult> Overlaps;
	World->OverlapMultiByObjectType(
		Overlaps,
		Origin,
		FQuat::Identity,
		FCollisionObjectQueryParams(FCollisionObjectQueryParams::InitType::AllObjects),
		FCollisionShape::MakeSphere(Range),
		QueryParams);

	AActor* Best = nullptr;
	float BestScore = -FLT_MAX;
	TSet<AActor*> Seen;

	for (const FOverlapResult& Overlap : Overlaps)
	{
		AActor* Candidate = Overlap.GetActor();
		if (!Candidate || Candidate == Owner || Seen.Contains(Candidate))
		{
			continue;
		}
		Seen.Add(Candidate);

		if (!Candidate->GetClass()->ImplementsInterface(ULyrisInteractable::StaticClass()))
		{
			continue;
		}

		// Measure to the nearest point of what we overlapped, so big actors (a farm plot, a
		// tree) count from their edge, not their centre. Fall back to the bounds centre.
		FVector TargetPoint;
		const UPrimitiveComponent* Primitive = Overlap.GetComponent();
		if (!Primitive || Primitive->GetClosestPointOnCollision(Origin, TargetPoint) < 0.f)
		{
			FVector BoundsExtent;
			Candidate->GetActorBounds(true, TargetPoint, BoundsExtent);
		}

		const FVector ToTarget = TargetPoint - Origin;
		const FVector FlatToTarget = FVector(ToTarget.X, ToTarget.Y, 0.f);
		const float FlatDistance = FlatToTarget.Size();

		// Standing on top of / inside something counts as facing it.
		const float Dot = FlatDistance < KINDA_SMALL_NUMBER ? 1.f : FVector::DotProduct(FlatView, FlatToTarget / FlatDistance);
		if (Dot < MinDot)
		{
			continue;
		}

		if (!ILyrisInteractable::Execute_CanInteract(Candidate, Owner))
		{
			continue;
		}

		if (bRequireLineOfSight)
		{
			FCollisionQueryParams TraceParams(SCENE_QUERY_STAT(LyrisInteractionSight), false, Owner);
			FHitResult Hit;
			const bool bBlocked = World->LineTraceSingleByChannel(Hit, ViewLocation, TargetPoint, ECC_Visibility, TraceParams);
			if (bBlocked && Hit.GetActor() != Candidate)
			{
				continue;
			}
		}

		// Prefer what's centred in view, then what's close. Both terms are 0..1.
		const float Closeness = 1.f - FMath::Clamp(static_cast<float>(ToTarget.Size()) / FMath::Max(Range, 1.f), 0.f, 1.f);
		const float Score = Dot * 2.f + Closeness;
		if (Score > BestScore)
		{
			BestScore = Score;
			Best = Candidate;
		}
	}

	return Best;
}

void ULyrisInteractionComponent::SetTarget(AActor* NewTarget)
{
	FText NewPrompt = FText::GetEmpty();
	if (NewTarget && GetOwner())
	{
		NewPrompt = ILyrisInteractable::Execute_GetInteractPrompt(NewTarget, GetOwner());
	}

	const bool bTargetChanged = CurrentTarget.Get() != NewTarget;
	const bool bPromptChanged = !NewPrompt.EqualTo(CurrentPrompt);
	if (!bTargetChanged && !bPromptChanged)
	{
		return;
	}

	CurrentTarget = NewTarget;
	CurrentPrompt = NewPrompt;
	OnTargetChanged.Broadcast(NewTarget, NewPrompt);
}
