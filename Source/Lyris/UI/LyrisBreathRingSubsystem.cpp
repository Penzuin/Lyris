// Lyris UI: shows the Breath ring beside the local player's head (T33).

#include "UI/LyrisBreathRingSubsystem.h"

#include "UI/SLyrisBreathRing.h"
#include "Player/LyrisStaminaComponent.h"

#include "Blueprint/WidgetLayoutLibrary.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/HUD.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Widgets/SWeakWidget.h"

namespace LyrisBreathRingLayout
{
	/** Main arc radius in Slate units, before DPI scale. Reference was 17 px on a 960 px stage. */
	static constexpr float RingRadius = 24.f;
	/** Below most HUD and every menu. */
	static constexpr int32 ZOrder = -5;
	static const FName HeadSocket(TEXT("head"));
}

void ULyrisBreathRingSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	bActive = true;
}

void ULyrisBreathRingSubsystem::Deinitialize()
{
	bActive = false;
	Detach();
	Ring.Reset();
	Super::Deinitialize();
}

ETickableTickType ULyrisBreathRingSubsystem::GetTickableTickType() const
{
	return IsTemplate() ? ETickableTickType::Never : ETickableTickType::Conditional;
}

bool ULyrisBreathRingSubsystem::IsTickable() const
{
	return bActive && !IsTemplate() && GetLocalPlayer() != nullptr;
}

TStatId ULyrisBreathRingSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(ULyrisBreathRingSubsystem, STATGROUP_Tickables);
}

UWorld* ULyrisBreathRingSubsystem::GetTickableGameObjectWorld() const
{
	const ULocalPlayer* LocalPlayer = GetLocalPlayer();
	return LocalPlayer ? LocalPlayer->GetWorld() : nullptr;
}

void ULyrisBreathRingSubsystem::SetReducedMotion(bool bInReducedMotion)
{
	bReducedMotion = bInReducedMotion;
	if (Ring.IsValid())
	{
		Ring->SetReducedMotion(bReducedMotion);
	}
}

void ULyrisBreathRingSubsystem::Tick(float DeltaTime)
{
	ULocalPlayer* LocalPlayer = GetLocalPlayer();
	UWorld* World = LocalPlayer ? LocalPlayer->GetWorld() : nullptr;
	APlayerController* PC = (LocalPlayer && World) ? LocalPlayer->GetPlayerController(World) : nullptr;
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	ULyrisStaminaComponent* Stamina = Pawn ? Pawn->FindComponentByClass<ULyrisStaminaComponent>() : nullptr;
	UGameViewportClient* Viewport = World ? World->GetGameViewport() : nullptr;

	if (!Stamina || !Viewport)
	{
		Detach();
		return;
	}

	// New pawn, new component, new viewport, or the viewport dropped our widget (map travel).
	const bool bWidgetGone = !AddedWidget.IsValid();
	if (Pawn != AttachedPawn.Get() || Stamina != AttachedStamina.Get() || Viewport != AttachedViewport.Get() || bWidgetGone)
	{
		Detach();
		Attach(Pawn, Stamina, Viewport);
	}
	if (!Ring.IsValid())
	{
		return;
	}

	// Project the head into the ring's local space. The ring is on this player's viewport layer, so
	// player-relative widget coordinates (already divided by DPI scale) are its local coordinates.
	FVector2D HeadOnWidget = FVector2D::ZeroVector;
	bool bOnScreen = UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition(PC, GetHeadLocation(Pawn), HeadOnWidget, true);

	const AHUD* HUD = PC->GetHUD();
	if (HUD && !HUD->bShowHUD)
	{
		bOnScreen = false;
	}
	if (Pawn->IsHidden())
	{
		bOnScreen = false;
	}
	Ring->SetHeadAnchor(HeadOnWidget, bOnScreen);

	FLyrisBreathSample Sample;
	Sample.Current = Stamina->GetCurrent();
	Sample.Max = Stamina->GetMax();
	Sample.Bonus = Stamina->GetBonus();
	Sample.bWinded = Stamina->IsWinded();
	Sample.WindedThreshold = Stamina->GetWindedThreshold();
	Sample.TimeSinceLastSpend = Stamina->GetTimeSinceLastSpend();
	Sample.PreviewCost = Stamina->GetPreviewCost();
	Sample.bCanAffordPreview = Sample.PreviewCost <= 0.f || Stamina->CanAfford(Sample.PreviewCost);
	Ring->Advance(DeltaTime, Sample);
}

void ULyrisBreathRingSubsystem::Attach(APawn* Pawn, ULyrisStaminaComponent* Stamina, UGameViewportClient* Viewport)
{
	ULocalPlayer* LocalPlayer = GetLocalPlayer();
	if (!Pawn || !Stamina || !Viewport || !LocalPlayer)
	{
		return;
	}

	if (!Ring.IsValid())
	{
		Ring = SNew(SLyrisBreathRing)
			.RingRadius(LyrisBreathRingLayout::RingRadius)
			.ReducedMotion(bReducedMotion);
	}
	Ring->ResetState();

	// A weak wrapper, so the viewport never keeps the ring alive past this subsystem.
	TSharedRef<SWidget> Wrapper = SNew(SWeakWidget).PossiblyNullContent(Ring);
	Viewport->AddViewportWidgetForPlayer(LocalPlayer, Wrapper, LyrisBreathRingLayout::ZOrder);
	AddedWidget = Wrapper;

	Stamina->OnStaminaSpent.AddDynamic(this, &ULyrisBreathRingSubsystem::HandleStaminaSpent);

	AttachedPawn = Pawn;
	AttachedStamina = Stamina;
	AttachedViewport = Viewport;
}

void ULyrisBreathRingSubsystem::Detach()
{
	if (ULyrisStaminaComponent* Stamina = AttachedStamina.Get())
	{
		Stamina->OnStaminaSpent.RemoveDynamic(this, &ULyrisBreathRingSubsystem::HandleStaminaSpent);
	}

	TSharedPtr<SWidget> Widget = AddedWidget.Pin();
	UGameViewportClient* Viewport = AttachedViewport.Get();
	ULocalPlayer* LocalPlayer = GetLocalPlayer();
	if (Widget.IsValid() && Viewport && LocalPlayer)
	{
		Viewport->RemoveViewportWidgetForPlayer(LocalPlayer, Widget.ToSharedRef());
	}

	AddedWidget.Reset();
	AttachedPawn.Reset();
	AttachedStamina.Reset();
	AttachedViewport.Reset();
}

FVector ULyrisBreathRingSubsystem::GetHeadLocation(const APawn* Pawn)
{
	if (!Pawn)
	{
		return FVector::ZeroVector;
	}

	if (const ACharacter* Character = Cast<ACharacter>(Pawn))
	{
		const USkeletalMeshComponent* Mesh = Character->GetMesh();
		if (Mesh && Mesh->DoesSocketExist(LyrisBreathRingLayout::HeadSocket))
		{
			return Mesh->GetSocketLocation(LyrisBreathRingLayout::HeadSocket);
		}
		if (const UCapsuleComponent* Capsule = Character->GetCapsuleComponent())
		{
			return Character->GetActorLocation() + FVector(0.f, 0.f, Capsule->GetScaledCapsuleHalfHeight());
		}
	}

	if (const USkeletalMeshComponent* Mesh = Pawn->FindComponentByClass<USkeletalMeshComponent>())
	{
		if (Mesh->DoesSocketExist(LyrisBreathRingLayout::HeadSocket))
		{
			return Mesh->GetSocketLocation(LyrisBreathRingLayout::HeadSocket);
		}
	}

	FVector Origin;
	FVector Extent;
	Pawn->GetActorBounds(true, Origin, Extent);
	return FVector(Origin.X, Origin.Y, Origin.Z + Extent.Z);
}

void ULyrisBreathRingSubsystem::HandleStaminaSpent(float Amount)
{
	if (Ring.IsValid())
	{
		Ring->NotifySpent(Amount);
	}
}
