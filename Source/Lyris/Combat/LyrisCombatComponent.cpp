#include "Combat/LyrisCombatComponent.h"

#include "Animation/AnimInstance.h"
#include "Animation/AnimSequenceBase.h"
#include "Combat/LyrisCombatFx.h"
#include "Combat/LyrisHealthComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/OverlapResult.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "UObject/ConstructorHelpers.h"

namespace LyrisCombatTuning
{
	// Lyris house palette (moonglass light, warm gold, Lantern Star white).
	static const FLinearColor Moonglass(0.19f, 0.52f, 0.79f);
	static const FLinearColor Gold(0.77f, 0.42f, 0.06f);
	static const FLinearColor StarWhite(0.9f, 0.95f, 1.0f);

	static constexpr float ComboReset = 1.1f;      // seconds from one swing's start to keep the combo going
	static constexpr float ChargeHoldTime = 0.38f;
	static constexpr float DashSpeed = 1500.f;
	static constexpr float DashTime = 0.32f;
	static constexpr float DodgeIFrames = 0.3f;
	static constexpr float LullScale = 0.3f;
	static constexpr double LullSeconds = 1.0;
	static constexpr float HitStop = 0.06f;
	static constexpr float StaminaRegenDelay = 0.8f;
}

ULyrisCombatComponent::ULyrisCombatComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;

	// Placeholder animations from the Unreal mannequin (the template's shared Characters folder).
	static ConstructorHelpers::FObjectFinder<UAnimSequenceBase> A1(
		TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Attack/MM_Attack_01.MM_Attack_01"));
	static ConstructorHelpers::FObjectFinder<UAnimSequenceBase> A2(
		TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Attack/MM_Attack_02.MM_Attack_02"));
	static ConstructorHelpers::FObjectFinder<UAnimSequenceBase> A3(
		TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Attack/MM_Attack_03.MM_Attack_03"));
	static ConstructorHelpers::FObjectFinder<UAnimSequenceBase> AC(
		TEXT("/Game/Characters/Mannequins/Anims/Unarmed/Attack/MM_ChargedAttack.MM_ChargedAttack"));
	AttackAnims = { A1.Object, A2.Object, A3.Object };
	ChargedAnim = AC.Object;

	//                Damage Poise Knock Reach Radius HitDelay Duration Anim
	Combo.Add({ 18.f, 12.f, 250.f, 110.f, 110.f, 0.14f, 0.42f, 0 });
	Combo.Add({ 20.f, 12.f, 250.f, 110.f, 110.f, 0.14f, 0.42f, 1 });
	Combo.Add({ 22.f, 15.f, 300.f, 120.f, 120.f, 0.16f, 0.48f, 0 });
	Combo.Add({ 34.f, 45.f, 650.f, 130.f, 150.f, 0.22f, 0.62f, 2 });  // finisher: staggers
}

void ULyrisCombatComponent::BeginPlay()
{
	Super::BeginPlay();
	Stamina = MaxStamina;

	Health = GetOwner()->FindComponentByClass<ULyrisHealthComponent>();
	if (!Health)
	{
		Health = NewObject<ULyrisHealthComponent>(GetOwner(), TEXT("LyrisHealth"));
		Health->RegisterComponent();
	}
	Health->MaxHealth = 120.f;
	Health->MaxPoise = 100.f;
	Health->KnockbackScale = 0.5f;
	Health->RestoreFull();
	Health->OnHitTaken.AddDynamic(this, &ULyrisCombatComponent::HandleHitTaken);
	Health->OnDefeated.AddDynamic(this, &ULyrisCombatComponent::HandleDefeated);

	if (RespawnLocation.IsZero())
	{
		RespawnLocation = GetOwner()->GetActorLocation();
	}
}

ACharacter* ULyrisCombatComponent::OwnerCharacter() const
{
	return Cast<ACharacter>(GetOwner());
}

APlayerController* ULyrisCombatComponent::PlayerController() const
{
	const ACharacter* Character = OwnerCharacter();
	return Character ? Cast<APlayerController>(Character->GetController()) : nullptr;
}

double ULyrisCombatComponent::RealNow() const
{
	return GetWorld() ? GetWorld()->GetRealTimeSeconds() : 0.0;
}

void ULyrisCombatComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	UpdateTimeEffects();

	APlayerController* PC = PlayerController();
	if (!PC || !Health)
	{
		return;  // on the boat, or not controlled: nothing to do
	}

	SinceComboStep += DeltaTime;
	SinceStaminaUse += DeltaTime;
	ArtReadyIn = FMath::Max(0.f, ArtReadyIn - DeltaTime);
	if (SinceStaminaUse > LyrisCombatTuning::StaminaRegenDelay)
	{
		Stamina = FMath::Min(MaxStamina, Stamina + StaminaRegen * DeltaTime);
	}

	bEngaged = AnyFoeWithin(EngageRange);
	if (bEngaged)
	{
		ReadInput(PC, DeltaTime);
		ShowStatus();
	}
	TickAction(DeltaTime);
}

void ULyrisCombatComponent::ReadInput(APlayerController* PC, float DeltaTime)
{
	ACharacter* Character = OwnerCharacter();
	const bool bFalling = Character && Character->GetCharacterMovement()->IsFalling();

	// Attack: press starts a swing (or a plunge in the air); holding turns it into a charged attack.
	if (PC->WasInputKeyJustPressed(EKeys::LeftMouseButton))
	{
		AttackHeldFor = 0.f;
		if (bFalling && Action == EAction::None)
		{
			StartPlunge();
		}
		else if (Action == EAction::None)
		{
			StartComboStep();
		}
		else if (Action == EAction::Attack)
		{
			bComboQueued = true;  // buffered: continue as soon as this swing allows
		}
	}
	if (PC->IsInputKeyDown(EKeys::LeftMouseButton))
	{
		AttackHeldFor += DeltaTime;
		if (AttackHeldFor >= LyrisCombatTuning::ChargeHoldTime && Action == EAction::Attack && ComboIndex == 0
			&& Stamina >= ChargedCost)
		{
			StartCharged();
		}
	}

	if (PC->WasInputKeyJustPressed(EKeys::RightMouseButton) || PC->WasInputKeyJustPressed(EKeys::LeftShift))
	{
		StartDash();  // dashing cancels attacks, as in Genshin
	}
	if (PC->WasInputKeyJustPressed(EKeys::E))
	{
		StartArt();
	}
	if (PC->WasInputKeyJustPressed(EKeys::Q))
	{
		StartSurge();
	}
}

void ULyrisCombatComponent::TickAction(float DeltaTime)
{
	ACharacter* Character = OwnerCharacter();
	if (!Character || Action == EAction::None)
	{
		bWasFalling = Character && Character->GetCharacterMovement()->IsFalling();
		return;
	}
	ActionTime += DeltaTime;
	const FVector Forward = Character->GetActorForwardVector();
	const FVector Feet = Character->GetActorLocation() - FVector(0.f, 0.f, Character->GetSimpleCollisionHalfHeight());

	switch (Action)
	{
	case EAction::Attack:
	{
		const FComboStep& Step = Combo[ComboIndex];
		if (!bActionHitDone && ActionTime >= Step.HitDelay)
		{
			bActionHitDone = true;
			FLyrisHit Hit;
			Hit.Damage = Step.Damage;
			Hit.PoiseDamage = Step.Poise;
			Hit.Knockback = Forward * Step.Knockback;
			Hit.Instigator = Character;
			HitArea(Character->GetActorLocation() + Forward * Step.Reach, Step.Radius, Hit, false);
		}
		if (ActionTime >= Step.Duration)
		{
			Action = EAction::None;
			if (bComboQueued && ComboIndex < Combo.Num() - 1)
			{
				StartComboStep();
			}
		}
		break;
	}
	case EAction::Charged:
		if (!bActionHitDone && ActionTime >= 0.3f)
		{
			bActionHitDone = true;
			FLyrisHit Hit;
			Hit.Damage = 46.f;
			Hit.PoiseDamage = 60.f;
			Hit.Knockback = Forward * 700.f;
			Hit.Instigator = Character;
			HitArea(Character->GetActorLocation(), 230.f, Hit, true);  // a spinning cut around you
			ALyrisCombatFx::Burst(GetWorld(), Feet, LyrisCombatTuning::Gold, 60.f, 260.f, 0.3f, 3000.f, true);
		}
		if (ActionTime >= 0.75f)
		{
			Action = EAction::None;
		}
		break;
	case EAction::Plunge:
	{
		const bool bFalling = Character->GetCharacterMovement()->IsFalling();
		if (!bFalling && !bActionHitDone)
		{
			bActionHitDone = true;
			FLyrisHit Hit;
			Hit.Damage = 40.f;
			Hit.PoiseDamage = 50.f;
			Hit.Knockback = FVector::ZeroVector;
			Hit.Instigator = Character;
			HitArea(Character->GetActorLocation(), 300.f, Hit, true);
			ALyrisCombatFx::Burst(GetWorld(), Feet, LyrisCombatTuning::StarWhite, 80.f, 320.f, 0.35f, 4000.f, true);
		}
		if (bActionHitDone && ActionTime > 0.1f)
		{
			Action = EAction::None;
		}
		break;
	}
	case EAction::Dash:
		if (ActionTime >= LyrisCombatTuning::DashTime)
		{
			Action = EAction::None;
		}
		break;
	case EAction::Art:
		if (ActionTime >= 0.35f)
		{
			Action = EAction::None;
		}
		break;
	case EAction::Surge:
		if (!bActionHitDone && ActionTime >= 0.45f)
		{
			bActionHitDone = true;
			FLyrisHit Hit;
			Hit.Damage = 90.f;
			Hit.PoiseDamage = 120.f;
			Hit.Attunement = Attunement;
			Hit.Instigator = Character;
			HitArea(Character->GetActorLocation(), 900.f, Hit, true);
			ALyrisCombatFx::Burst(GetWorld(), Feet, LyrisCombatTuning::StarWhite, 100.f, 950.f, 0.7f, 40000.f, true);
		}
		if (ActionTime >= 0.9f)
		{
			Action = EAction::None;
		}
		break;
	default:
		Action = EAction::None;
		break;
	}
	bWasFalling = Character->GetCharacterMovement()->IsFalling();
}

void ULyrisCombatComponent::StartComboStep()
{
	ACharacter* Character = OwnerCharacter();
	if (!Character)
	{
		return;
	}
	// Continue the combo if the last swing started recently enough; otherwise start over.
	const bool bContinue = SinceComboStep <= LyrisCombatTuning::ComboReset && ComboIndex >= 0 && ComboIndex < Combo.Num() - 1;
	ComboIndex = bContinue ? ComboIndex + 1 : 0;
	SinceComboStep = 0.f;
	bComboQueued = false;
	Action = EAction::Attack;
	ActionTime = 0.f;
	bActionHitDone = false;

	FaceTarget(FindSoftTarget(600.f, 70.f));
	Character->GetCharacterMovement()->StopMovementImmediately();
	Character->LaunchCharacter(Character->GetActorForwardVector() * 320.f, true, false);  // a small step in
	const FComboStep& Step = Combo[ComboIndex];
	if (AttackAnims.IsValidIndex(Step.AnimIndex))
	{
		PlayAnim(AttackAnims[Step.AnimIndex], 1.35f);
	}
}

void ULyrisCombatComponent::StartCharged()
{
	Stamina -= ChargedCost;
	SinceStaminaUse = 0.f;
	Action = EAction::Charged;
	ActionTime = 0.f;
	bActionHitDone = false;
	ComboIndex = -1;
	PlayAnim(ChargedAnim, 1.2f);
}

void ULyrisCombatComponent::StartPlunge()
{
	ACharacter* Character = OwnerCharacter();
	Action = EAction::Plunge;
	ActionTime = 0.f;
	bActionHitDone = false;
	Character->LaunchCharacter(FVector(0.f, 0.f, -2200.f), false, true);
}

void ULyrisCombatComponent::StartDash()
{
	ACharacter* Character = OwnerCharacter();
	if (!Character || Stamina < DashCost || Action == EAction::Dash || Action == EAction::Surge)
	{
		return;
	}
	Stamina -= DashCost;
	SinceStaminaUse = 0.f;
	FVector Dir = Character->GetLastMovementInputVector().GetSafeNormal2D();
	if (Dir.IsNearlyZero())
	{
		Dir = -Character->GetActorForwardVector();  // no direction held: hop back, like Genshin
	}
	Character->LaunchCharacter(Dir * LyrisCombatTuning::DashSpeed, true, false);
	Health->SetInvulnerableFor(LyrisCombatTuning::DodgeIFrames, true);
	Action = EAction::Dash;
	ActionTime = 0.f;
	ComboIndex = -1;
}

void ULyrisCombatComponent::StartArt()
{
	ACharacter* Character = OwnerCharacter();
	if (!Character || ArtReadyIn > 0.f || Action == EAction::Surge)
	{
		return;
	}
	// Flare: a burst of lamplight that Dispels Misted foes around you.
	ArtReadyIn = ArtCooldown;
	Action = EAction::Art;
	ActionTime = 0.f;
	FLyrisHit Hit;
	Hit.Damage = 24.f;
	Hit.PoiseDamage = 25.f;
	Hit.Attunement = Attunement;
	Hit.Instigator = Character;
	HitArea(Character->GetActorLocation(), 450.f, Hit, true);
	const FVector Feet = Character->GetActorLocation() - FVector(0.f, 0.f, Character->GetSimpleCollisionHalfHeight());
	ALyrisCombatFx::Burst(GetWorld(), Feet, LyrisCombatTuning::Moonglass, 60.f, 470.f, 0.45f, 20000.f, true);
}

void ULyrisCombatComponent::StartSurge()
{
	ACharacter* Character = OwnerCharacter();
	if (!Character || SurgeEnergy < 100.f || Action == EAction::Surge)
	{
		return;
	}
	// Lighthouse Beam: a great sweep of light. You are untouchable while it gathers.
	SurgeEnergy = 0.f;
	Action = EAction::Surge;
	ActionTime = 0.f;
	bActionHitDone = false;
	Health->SetInvulnerableFor(1.0f, false);
	Character->GetCharacterMovement()->StopMovementImmediately();
	PlayAnim(ChargedAnim, 0.9f);
	ALyrisCombatFx::Burst(GetWorld(), Character->GetActorLocation(), LyrisCombatTuning::StarWhite, 20.f, 90.f, 0.45f, 30000.f);
}

AActor* ULyrisCombatComponent::FindSoftTarget(float Range, float ConeDegrees) const
{
	const ACharacter* Character = OwnerCharacter();
	const APlayerController* PC = PlayerController();
	if (!Character)
	{
		return nullptr;
	}
	// Aim where the camera looks (or where you're moving); prefer foes in that cone, then the nearest.
	FVector Aim = Character->GetLastMovementInputVector().GetSafeNormal2D();
	if (Aim.IsNearlyZero() && PC)
	{
		Aim = PC->GetControlRotation().Vector().GetSafeNormal2D();
	}
	const float CosCone = FMath::Cos(FMath::DegreesToRadians(ConeDegrees));
	AActor* Best = nullptr;
	float BestScore = TNumericLimits<float>::Max();
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		AActor* Other = *It;
		if (Other == Character)
		{
			continue;
		}
		const ULyrisHealthComponent* OtherHealth = Other->FindComponentByClass<ULyrisHealthComponent>();
		if (!OtherHealth || OtherHealth->IsDefeated())
		{
			continue;
		}
		const FVector To = Other->GetActorLocation() - Character->GetActorLocation();
		const float Dist = To.Size2D();
		if (Dist > Range)
		{
			continue;
		}
		const float Facing = Aim.IsNearlyZero() ? 1.f : FVector::DotProduct(Aim, To.GetSafeNormal2D());
		const float Score = Dist * (Facing >= CosCone ? 1.f : 2.5f);
		if (Score < BestScore)
		{
			BestScore = Score;
			Best = Other;
		}
	}
	return Best;
}

bool ULyrisCombatComponent::AnyFoeWithin(float Range) const
{
	const AActor* Me = GetOwner();
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (*It == Me)
		{
			continue;
		}
		const ULyrisHealthComponent* OtherHealth = It->FindComponentByClass<ULyrisHealthComponent>();
		if (OtherHealth && !OtherHealth->IsDefeated() && FVector::Dist(It->GetActorLocation(), Me->GetActorLocation()) < Range)
		{
			return true;
		}
	}
	return false;
}

void ULyrisCombatComponent::FaceTarget(AActor* Target)
{
	ACharacter* Character = OwnerCharacter();
	if (!Character || !Target)
	{
		return;
	}
	const FVector To = (Target->GetActorLocation() - Character->GetActorLocation()).GetSafeNormal2D();
	if (!To.IsNearlyZero())
	{
		Character->SetActorRotation(FRotator(0.f, To.Rotation().Yaw, 0.f));
	}
}

int32 ULyrisCombatComponent::HitArea(const FVector& Centre, float Radius, const FLyrisHit& Template, bool bKnockOutward)
{
	UWorld* World = GetWorld();
	AActor* Me = GetOwner();
	TArray<FOverlapResult> Overlaps;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(LyrisPlayerHit), false, Me);
	World->OverlapMultiByObjectType(Overlaps, Centre, FQuat::Identity, FCollisionObjectQueryParams(ECC_Pawn),
		FCollisionShape::MakeSphere(Radius), Params);

	TSet<AActor*> Struck;
	for (const FOverlapResult& Overlap : Overlaps)
	{
		AActor* Target = Overlap.GetActor();
		if (!Target || Target == Me || Struck.Contains(Target))
		{
			continue;
		}
		ULyrisHealthComponent* TargetHealth = Target->FindComponentByClass<ULyrisHealthComponent>();
		if (!TargetHealth || TargetHealth->IsDefeated())
		{
			continue;
		}
		Struck.Add(Target);
		FLyrisHit Hit = Template;
		if (bKnockOutward)
		{
			const float Strength = FMath::Max(Template.Knockback.Size(), 450.f);
			Hit.Knockback = (Target->GetActorLocation() - Me->GetActorLocation()).GetSafeNormal2D() * Strength;
		}
		OnHitLanded(Target, TargetHealth->ApplyHit(Hit));
	}
	return Struck.Num();
}

void ULyrisCombatComponent::OnHitLanded(AActor* Target, const FLyrisHitResult& Result)
{
	if (!Result.bLanded)
	{
		return;
	}
	SurgeEnergy = FMath::Min(100.f, SurgeEnergy + SurgeEnergyPerHit + (Result.bDispel ? 15.f : 0.f));
	const FVector Where = Target->GetActorLocation();
	if (Result.bDispel)
	{
		ALyrisCombatFx::Burst(GetWorld(), Where, LyrisCombatTuning::StarWhite, 20.f, 150.f, 0.35f, 12000.f);
		if (GEngine)
		{
			GEngine->AddOnScreenDebugMessage(static_cast<uint64>(72010), 1.2f, FColor(230, 240, 255), TEXT("Dispel!"));
		}
	}
	else
	{
		ALyrisCombatFx::Burst(GetWorld(), Where, LyrisCombatTuning::Gold, 10.f, 45.f, 0.15f, 1500.f);
	}
	StartHitStop(Target, Result.bStaggered || Result.bDispel ? LyrisCombatTuning::HitStop * 1.6f : LyrisCombatTuning::HitStop);
}

void ULyrisCombatComponent::StartHitStop(AActor* Target, float Seconds)
{
	// Freeze attacker and target for a few frames: the "weight" of a hit.
	AActor* Me = GetOwner();
	Me->CustomTimeDilation = 0.05f;
	Target->CustomTimeDilation = 0.05f;
	HitStopped.AddUnique(Me);
	HitStopped.AddUnique(Target);
	HitStopEndReal = FMath::Max(HitStopEndReal, RealNow() + Seconds);
}

void ULyrisCombatComponent::UpdateTimeEffects()
{
	const double Now = RealNow();
	if (HitStopped.Num() > 0 && Now >= HitStopEndReal)
	{
		for (const TWeakObjectPtr<AActor>& Actor : HitStopped)
		{
			if (Actor.IsValid())
			{
				Actor->CustomTimeDilation = 1.f;
			}
		}
		HitStopped.Reset();
	}
	if (LullEndReal > 0.0 && Now >= LullEndReal)
	{
		UGameplayStatics::SetGlobalTimeDilation(this, 1.f);
		LullEndReal = 0.0;
	}
}

void ULyrisCombatComponent::PlayAnim(UAnimSequenceBase* Anim, float Rate)
{
	ACharacter* Character = OwnerCharacter();
	if (!Anim || !Character || !Character->GetMesh())
	{
		return;
	}
	if (UAnimInstance* AnimInstance = Character->GetMesh()->GetAnimInstance())
	{
		// Needs a "DefaultSlot" in the character's animation blueprint; without one, nothing plays.
		AnimInstance->PlaySlotAnimationAsDynamicMontage(Anim, TEXT("DefaultSlot"), 0.05f, 0.15f, Rate);
	}
}

void ULyrisCombatComponent::HandleHitTaken(const FLyrisHit& Hit, const FLyrisHitResult& Result)
{
	if (Result.bPerfectDodge)
	{
		if (LullEndReal > 0.0)
		{
			return;  // one Lull at a time
		}
		// Lull: time slows for a moment and the dash is free.
		Stamina = FMath::Min(MaxStamina, Stamina + DashCost);
		UGameplayStatics::SetGlobalTimeDilation(this, LyrisCombatTuning::LullScale);
		LullEndReal = RealNow() + LyrisCombatTuning::LullSeconds;
		if (GEngine)
		{
			GEngine->AddOnScreenDebugMessage(static_cast<uint64>(72011), 1.0f, FColor(122, 192, 230), TEXT("Lull"));
		}
		return;
	}
	if (Result.bLanded)
	{
		Action = EAction::None;  // a hit interrupts your swing
		ComboIndex = -1;
	}
}

void ULyrisCombatComponent::HandleDefeated()
{
	// "The tide carries you home": back to safety, healed, nothing lost.
	ACharacter* Character = OwnerCharacter();
	if (Character)
	{
		Character->GetCharacterMovement()->StopMovementImmediately();
		Character->SetActorLocation(RespawnLocation, false, nullptr, ETeleportType::TeleportPhysics);
	}
	Health->RestoreFull();
	Stamina = MaxStamina;
	Action = EAction::None;
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(static_cast<uint64>(72012), 3.f, FColor(122, 192, 230),
			TEXT("The tide carries you home."));
	}
}

void ULyrisCombatComponent::ShowStatus() const
{
	if (!GEngine || !Health)
	{
		return;
	}
	// Temporary readout until the combat HUD (task C5).
	const FString Art = ArtReadyIn > 0.f ? FString::Printf(TEXT("%.1fs"), ArtReadyIn) : TEXT("ready");
	GEngine->AddOnScreenDebugMessage(static_cast<uint64>(72000), 0.0f, FColor(227, 174, 69),
		FString::Printf(TEXT("Health %d/%d   Stamina %d   Flare (E) %s   Surge (Q) %d%%"),
			FMath::RoundToInt(Health->Health), FMath::RoundToInt(Health->MaxHealth), FMath::RoundToInt(Stamina), *Art,
			FMath::RoundToInt(SurgeEnergy)));
	GEngine->AddOnScreenDebugMessage(static_cast<uint64>(72001), 0.0f, FColor(240, 233, 220),
		TEXT("LMB attack (hold: charged, in the air: plunge)   RMB/Shift dash   E Flare   Q Surge"));
}
