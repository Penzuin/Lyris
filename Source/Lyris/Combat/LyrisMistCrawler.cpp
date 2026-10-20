#include "Combat/LyrisMistCrawler.h"

#include "AIController.h"
#include "Combat/LyrisCombatFx.h"
#include "Combat/LyrisHealthComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

namespace LyrisCrawler
{
	// Lyris house palette: ink-violet shell, mist grey cloak, cold moonglass eyes.
	static const FLinearColor Shell(0.035f, 0.02f, 0.06f);
	static const FLinearColor Cloak(0.20f, 0.22f, 0.30f);
	static const FLinearColor EyeCalm(0.19f, 0.52f, 0.79f);
	static const FLinearColor EyeTell(0.95f, 0.98f, 1.0f);
}

ALyrisMistCrawler::ALyrisMistCrawler()
{
	PrimaryActorTick.bCanEverTick = true;
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
	AIControllerClass = AAIController::StaticClass();

	GetCapsuleComponent()->InitCapsuleSize(48.f, 42.f);
	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->MaxWalkSpeed = 380.f;
	Move->bOrientRotationToMovement = true;
	Move->RotationRate = FRotator(0.f, 540.f, 0.f);
	Move->GroundFriction = 6.f;
	bUseControllerRotationYaw = false;

	Health = CreateDefaultSubobject<ULyrisHealthComponent>(TEXT("Health"));
	Health->MaxHealth = 110.f;
	Health->MaxPoise = 40.f;
	Health->bMisted = true;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereFinder(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderFinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	UStaticMesh* Sphere = SphereFinder.Object;
	UStaticMesh* Cylinder = CylinderFinder.Object;

	Body = CreateDefaultSubobject<USceneComponent>(TEXT("Body"));
	Body->SetupAttachment(GetCapsuleComponent());
	Body->SetRelativeLocation(FVector(0.f, 0.f, -20.f));

	// A low, wide carapace, a ragged mist cloak around it, two glowing eyes and six legs.
	Shell = MakePart(TEXT("Shell"), Sphere, FVector(0.f, 0.f, 6.f), FVector(1.05f, 0.85f, 0.45f));
	MistCloak = MakePart(TEXT("MistCloak"), Sphere, FVector(-6.f, 0.f, 4.f), FVector(1.25f, 1.05f, 0.5f));
	EyeLeft = MakePart(TEXT("EyeLeft"), Sphere, FVector(44.f, -13.f, 14.f), FVector(0.11f));
	EyeRight = MakePart(TEXT("EyeRight"), Sphere, FVector(44.f, 13.f, 14.f), FVector(0.11f));
	for (int32 i = 0; i < 6; ++i)
	{
		const float Side = i < 3 ? -1.f : 1.f;
		const float X = -22.f + (i % 3) * 22.f;
		UStaticMeshComponent* Leg = MakePart(*FString::Printf(TEXT("Leg%d"), i), Cylinder,
			FVector(X, Side * 44.f, -12.f), FVector(0.06f, 0.06f, 0.42f));
		Leg->SetRelativeRotation(FRotator(0.f, 0.f, Side * 50.f));
		Legs.Add(Leg);
	}

	EyeGlow = CreateDefaultSubobject<UPointLightComponent>(TEXT("EyeGlow"));
	EyeGlow->SetupAttachment(Body);
	EyeGlow->SetRelativeLocation(FVector(50.f, 0.f, 14.f));
	EyeGlow->SetCastShadows(false);
	EyeGlow->SetAttenuationRadius(350.f);
	EyeGlow->SetIntensity(800.f);
	EyeGlow->SetLightColor(LyrisCrawler::EyeCalm);
}

UStaticMeshComponent* ALyrisMistCrawler::MakePart(FName Name, UStaticMesh* Mesh, FVector Location, FVector Scale)
{
	UStaticMeshComponent* Part = CreateDefaultSubobject<UStaticMeshComponent>(Name);
	Part->SetupAttachment(Body);
	if (Mesh)
	{
		Part->SetStaticMesh(Mesh);
	}
	Part->SetRelativeLocation(Location);
	Part->SetRelativeScale3D(Scale);
	Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Part->SetCanEverAffectNavigation(false);
	return Part;
}

void ALyrisMistCrawler::BeginPlay()
{
	Super::BeginPlay();

	ShellMat = Shell->CreateAndSetMaterialInstanceDynamic(0);
	CloakMat = MistCloak->CreateAndSetMaterialInstanceDynamic(0);
	EyeMat = EyeLeft->CreateAndSetMaterialInstanceDynamic(0);
	EyeRight->SetMaterial(0, EyeMat);
	if (ShellMat) { ShellMat->SetVectorParameterValue(TEXT("Color"), LyrisCrawler::Shell); }
	if (CloakMat) { CloakMat->SetVectorParameterValue(TEXT("Color"), LyrisCrawler::Cloak); }
	if (EyeMat) { EyeMat->SetVectorParameterValue(TEXT("Color"), LyrisCrawler::EyeCalm); }
	for (UStaticMeshComponent* Leg : Legs)
	{
		Leg->SetMaterial(0, ShellMat);
	}

	Health->OnHitTaken.AddDynamic(this, &ALyrisMistCrawler::HandleHitTaken);
	Health->OnDefeated.AddDynamic(this, &ALyrisMistCrawler::HandleDefeated);
	SetState(EState::Emerging);
}

APawn* ALyrisMistCrawler::FindPlayer() const
{
	const APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	// Only the walking player: a sailor out on the boat is left alone.
	return (Pawn && Pawn->FindComponentByClass<ULyrisHealthComponent>()) ? Pawn : nullptr;
}

void ALyrisMistCrawler::SetState(EState NewState)
{
	State = NewState;
	StateTime = 0.f;
	bLungeHitDone = false;
}

void ALyrisMistCrawler::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	StateTime += DeltaSeconds;
	Clock += DeltaSeconds;

	APawn* Player = FindPlayer();
	const FVector Me = GetActorLocation();
	const float Dist = Player ? FVector::Dist2D(Player->GetActorLocation(), Me) : 1e9f;
	const FVector ToPlayer = Player ? (Player->GetActorLocation() - Me).GetSafeNormal2D() : GetActorForwardVector();

	if (Health->StaggeredFor > 0.f && State != EState::Dissolving)
	{
		if (State != EState::Staggered)
		{
			SetState(EState::Staggered);
		}
	}

	switch (State)
	{
	case EState::Emerging:
		if (StateTime >= EmergeTime)
		{
			SetState(EState::Idle);
		}
		break;
	case EState::Idle:
		if (Dist < SightRange)
		{
			SetState(EState::Approach);
		}
		break;
	case EState::Approach:
		if (Dist > SightRange * 1.3f)
		{
			SetState(EState::Idle);
		}
		else if (Dist < LungeRange)
		{
			SetState(EState::Tell);
			GetCharacterMovement()->StopMovementImmediately();
		}
		else
		{
			// Scuttle in with a slight zig-zag, like a crab.
			const FVector Side = FVector::CrossProduct(ToPlayer, FVector::UpVector) * FMath::Sin(Clock * 5.f) * 0.35f;
			AddMovementInput((ToPlayer + Side).GetSafeNormal());
		}
		break;
	case EState::Tell:
		// Face the player and glow brighter: this is the moment to dodge.
		SetActorRotation(FRotator(0.f, ToPlayer.Rotation().Yaw, 0.f));
		if (StateTime >= TellTime)
		{
			SetState(EState::Lunge);
			LaunchCharacter(ToPlayer * 1100.f + FVector(0.f, 0.f, 220.f), true, true);
		}
		break;
	case EState::Lunge:
		if (!bLungeHitDone && StateTime > 0.08f && Player && FVector::Dist(Player->GetActorLocation(), Me) < 140.f)
		{
			bLungeHitDone = true;
			if (ULyrisHealthComponent* PlayerHealth = Player->FindComponentByClass<ULyrisHealthComponent>())
			{
				FLyrisHit Hit;
				Hit.Damage = LungeDamage;
				Hit.PoiseDamage = 30.f;
				Hit.Knockback = ToPlayer * 500.f;
				Hit.Instigator = this;
				PlayerHealth->ApplyHit(Hit);
			}
		}
		if (StateTime >= 0.4f)
		{
			SetState(EState::Recover);
		}
		break;
	case EState::Recover:
		if (StateTime >= 0.9f)
		{
			SetState(EState::Approach);
		}
		break;
	case EState::Staggered:
		if (Health->StaggeredFor <= 0.f)
		{
			SetState(EState::Approach);
		}
		break;
	case EState::Dissolving:
		if (StateTime >= 0.6f)
		{
			Destroy();
			return;
		}
		break;
	}
	UpdateLooks(DeltaSeconds);
}

void ALyrisMistCrawler::UpdateLooks(float DeltaSeconds)
{
	// Emerging: rises out of the ground. Dissolving: sinks and shrinks into motes.
	float Rise = 0.f;
	float Scale = 1.f;
	if (State == EState::Emerging)
	{
		const float T = FMath::Clamp(StateTime / EmergeTime, 0.f, 1.f);
		Rise = (1.f - T) * -70.f;
	}
	else if (State == EState::Dissolving)
	{
		const float T = FMath::Clamp(StateTime / 0.6f, 0.f, 1.f);
		Scale = 1.f - T;
		Rise = -T * 20.f;
	}
	const float Squash = State == EState::Staggered ? 0.7f : 1.f;
	const float Bob = (State == EState::Approach) ? FMath::Sin(Clock * 18.f) * 3.f : 0.f;
	Body->SetRelativeLocation(FVector(0.f, 0.f, -20.f + Rise + Bob));
	Body->SetRelativeScale3D(FVector(Scale, Scale, Scale * Squash));

	// Legs skitter while it moves.
	for (int32 i = 0; i < Legs.Num(); ++i)
	{
		const float Side = i < 3 ? -1.f : 1.f;
		const float Swing = State == EState::Approach ? FMath::Sin(Clock * 22.f + i * 1.7f) * 18.f : 0.f;
		Legs[i]->SetRelativeRotation(FRotator(Swing, 0.f, Side * 50.f));
	}

	// The mist cloak shows only while Misted; Dispel strips it until the mist creeps back.
	MistCloak->SetVisibility(Health->IsMisted());

	const bool bTell = State == EState::Tell;
	const float Pulse = bTell ? (0.5f + 0.5f * FMath::Sin(StateTime * 30.f)) : 0.f;
	const FLinearColor Eye = FLinearColor::LerpUsingHSV(LyrisCrawler::EyeCalm, LyrisCrawler::EyeTell, bTell ? 0.5f + 0.5f * Pulse : 0.f);
	if (EyeMat)
	{
		EyeMat->SetVectorParameterValue(TEXT("Color"), Eye * (bTell ? 4.f : 1.5f));
	}
	EyeGlow->SetLightColor(Eye);
	EyeGlow->SetIntensity(bTell ? 6000.f * (0.6f + 0.4f * Pulse) : 800.f);
}

void ALyrisMistCrawler::HandleHitTaken(const FLyrisHit& Hit, const FLyrisHitResult& Result)
{
	if (Result.bLanded && State == EState::Tell)
	{
		// Interrupted mid-tell: hits knock it out of its lunge.
		SetState(EState::Recover);
	}
}

void ALyrisMistCrawler::HandleDefeated()
{
	SetState(EState::Dissolving);
	GetCharacterMovement()->StopMovementImmediately();
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	ALyrisCombatFx::Burst(GetWorld(), GetActorLocation(), LyrisCrawler::EyeCalm, 30.f, 160.f, 0.6f, 5000.f);
}
