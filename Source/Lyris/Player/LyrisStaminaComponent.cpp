// Lyris player: Breath, the one stamina pool that sprinting and climbing draw from.

#include "Player/LyrisStaminaComponent.h"
#include "Player/LyrisMovementSettings.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Net/UnrealNetwork.h"

ULyrisStaminaComponent::ULyrisStaminaComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
	SetIsReplicatedByDefault(true);
}

void ULyrisStaminaComponent::BeginPlay()
{
	Super::BeginPlay();

	// Clients keep whatever the server already sent.
	const AActor* Owner = GetOwner();
	if (Owner && !Owner->HasAuthority())
	{
		BroadcastChanged();
		return;
	}

	const ULyrisMovementSettings* S = ULyrisMovementSettings::Get();
	Max = FMath::Clamp(S->MaxBreath, 1.f, FMath::Max(1.f, S->MaxBreathCap));
	Current = Max;
	Bonus = 0.f;
	bWinded = false;
	LastSpendTime = -1000.0;
	BroadcastChanged();
}

void ULyrisStaminaComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(ULyrisStaminaComponent, Current);
	DOREPLIFETIME(ULyrisStaminaComponent, Max);
	DOREPLIFETIME(ULyrisStaminaComponent, Bonus);
	DOREPLIFETIME(ULyrisStaminaComponent, bWinded);
}

double ULyrisStaminaComponent::Now() const
{
	const UWorld* World = GetWorld();
	return World ? World->GetTimeSeconds() : 0.0;
}

float ULyrisStaminaComponent::GetWindedThreshold() const
{
	return Max * ULyrisMovementSettings::Get()->WindedClearsAtFraction;
}

float ULyrisStaminaComponent::GetTimeSinceLastSpend() const
{
	return static_cast<float>(Now() - LastSpendTime);
}

bool ULyrisStaminaComponent::CanAfford(float Amount) const
{
	return !bWinded && (Current + Bonus) >= Amount;
}

bool ULyrisStaminaComponent::TrySpend(float Amount)
{
	if (Amount <= 0.f)
	{
		return true;
	}
	if (!CanAfford(Amount))
	{
		OnStaminaDenied.Broadcast(Amount);
		return false;
	}
	SpendInternal(Amount);
	return true;
}

void ULyrisStaminaComponent::Drain(float Amount)
{
	if (Amount <= 0.f)
	{
		return;
	}
	SpendInternal(Amount);
}

void ULyrisStaminaComponent::SpendInternal(float Amount)
{
	const float FromBonus = FMath::Min(Bonus, Amount);
	Bonus -= FromBonus;
	Current = FMath::Max(0.f, Current - (Amount - FromBonus));
	LastSpendTime = Now();

	if (Current <= 0.f && !bWinded)
	{
		bWinded = true;
	}

	OnStaminaSpent.Broadcast(Amount);
	BroadcastChanged();
}

void ULyrisStaminaComponent::AddBonus(float Amount)
{
	if (Amount <= 0.f)
	{
		return;
	}
	const ULyrisMovementSettings* S = ULyrisMovementSettings::Get();
	Bonus = FMath::Min(S->MaxBonusBreath, Bonus + Amount);
	// Like a cup of tea in the prototype: refill starts right away instead of waiting out the delay.
	LastSpendTime = FMath::Min(LastSpendTime, Now() - S->RecoveryDelay);
	BroadcastChanged();
}

void ULyrisStaminaComponent::SetPreviewCost(float Cost)
{
	PreviewCost = FMath::Max(0.f, Cost);
}

void ULyrisStaminaComponent::SetMax(float NewMax, bool bRefill)
{
	const ULyrisMovementSettings* S = ULyrisMovementSettings::Get();
	Max = FMath::Clamp(NewMax, 1.f, FMath::Max(1.f, S->MaxBreathCap));
	Current = bRefill ? Max : FMath::Min(Current, Max);
	BroadcastChanged();
}

void ULyrisStaminaComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	// Other players' characters just show what the server sends.
	if (GetOwnerRole() == ROLE_SimulatedProxy)
	{
		return;
	}

	const ULyrisMovementSettings* S = ULyrisMovementSettings::Get();
	const bool bWasWinded = bWinded;
	const float OldCurrent = Current;

	// Sprinting and climbing drain every frame, which keeps resetting the delay: so no refill while
	// doing either, but refill in the air is fine.
	const float Since = GetTimeSinceLastSpend();
	if (Since > S->RecoveryDelay && Current < Max)
	{
		const float RampAlpha = S->RecoveryRampTime > UE_KINDA_SMALL_NUMBER
			? FMath::Clamp((Since - S->RecoveryDelay) / S->RecoveryRampTime, 0.f, 1.f)
			: 1.f;
		float Rate = FMath::Lerp(S->RecoveryRateStart, S->RecoveryRateFull, RampAlpha);
		if (bWinded)
		{
			Rate *= S->WindedRecoveryScale;
		}
		Current = FMath::Min(Max, Current + Rate * DeltaTime);
	}

	if (bWinded && Current >= GetWindedThreshold())
	{
		bWinded = false;
	}

	if (Current != OldCurrent || bWinded != bWasWinded)
	{
		BroadcastChanged();
	}
}

void ULyrisStaminaComponent::OnRep_Current(float OldCurrent)
{
	// Lets other players' rings (and a client that didn't predict) know when Breath was spent.
	if (Current < OldCurrent)
	{
		LastSpendTime = FMath::Max(LastSpendTime, Now());
	}
	BroadcastChanged();
}

void ULyrisStaminaComponent::OnRep_Breath()
{
	BroadcastChanged();
}

void ULyrisStaminaComponent::BroadcastChanged()
{
	OnStaminaChanged.Broadcast(Current, Max, Bonus, bWinded);
}
