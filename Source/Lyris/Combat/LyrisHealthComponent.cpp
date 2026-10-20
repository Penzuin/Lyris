#include "Combat/LyrisHealthComponent.h"

#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"

namespace LyrisCombat
{
	static constexpr float DispelMultiplier = 2.5f;
	static constexpr float DispelBonus = 30.f;
	static constexpr float PoiseRegenDelay = 1.5f;
}

ULyrisHealthComponent::ULyrisHealthComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
}

void ULyrisHealthComponent::RestoreFull()
{
	Health = MaxHealth;
	Poise = MaxPoise;
	StaggeredFor = 0.f;
	MistReturnIn = 0.f;
	bDefeated = false;
}

void ULyrisHealthComponent::SetInvulnerableFor(float Seconds, bool bFromDodge)
{
	InvulnerableFor = FMath::Max(InvulnerableFor, Seconds);
	bInvulnerableFromDodge = bFromDodge;
}

FLyrisHitResult ULyrisHealthComponent::ApplyHit(const FLyrisHit& Hit)
{
	FLyrisHitResult Result;
	if (bDefeated)
	{
		return Result;
	}
	if (InvulnerableFor > 0.f)
	{
		// The hit misses. If it slipped past a dash, that's a perfect dodge: tell the owner.
		Result.bPerfectDodge = bInvulnerableFromDodge;
		if (Result.bPerfectDodge)
		{
			OnHitTaken.Broadcast(Hit, Result);
		}
		return Result;
	}

	float Damage = Hit.Damage;
	float PoiseDamage = Hit.PoiseDamage;

	// Reaction: Misted + Lantern = Dispel.
	if (Hit.Attunement == ELyrisAttunement::Lantern && IsMisted())
	{
		Result.bDispel = true;
		Damage = Damage * LyrisCombat::DispelMultiplier + LyrisCombat::DispelBonus;
		PoiseDamage = MaxPoise;  // the mist armour breaks
		MistReturnIn = MistReturnTime;
	}

	Health = FMath::Max(0.f, Health - Damage);
	Result.bLanded = true;
	Result.DamageDealt = Damage;
	SinceLastHit = 0.f;

	if (StaggeredFor <= 0.f)
	{
		Poise -= PoiseDamage;
		if (Poise <= 0.f)
		{
			Poise = 0.f;
			StaggeredFor = StaggerTime;
			Result.bStaggered = true;
		}
	}

	if (ACharacter* Character = Cast<ACharacter>(GetOwner()))
	{
		const FVector Push = Hit.Knockback * KnockbackScale * (Result.bStaggered ? 1.4f : 1.f);
		if (!Push.IsNearlyZero())
		{
			Character->LaunchCharacter(Push + FVector(0.f, 0.f, 120.f * KnockbackScale), true, false);
		}
	}

	if (Health <= 0.f)
	{
		bDefeated = true;
		Result.bDefeated = true;
	}

	OnHitTaken.Broadcast(Hit, Result);
	if (Result.bDefeated)
	{
		OnDefeated.Broadcast();
	}
	return Result;
}

void ULyrisHealthComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	InvulnerableFor = FMath::Max(0.f, InvulnerableFor - DeltaTime);
	SinceLastHit += DeltaTime;

	if (StaggeredFor > 0.f)
	{
		StaggeredFor -= DeltaTime;
		if (StaggeredFor <= 0.f)
		{
			Poise = MaxPoise;  // back on its feet with full poise
		}
	}
	else if (SinceLastHit > LyrisCombat::PoiseRegenDelay)
	{
		Poise = FMath::Min(MaxPoise, Poise + PoiseRegen * DeltaTime);
	}

	if (MistReturnIn > 0.f)
	{
		MistReturnIn = FMath::Max(0.f, MistReturnIn - DeltaTime);
	}
}
