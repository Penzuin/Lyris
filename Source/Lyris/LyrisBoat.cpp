// Lyris sailing prototype: a small sailboat the player can board at the dock and sail with the wind.

#include "LyrisBoat.h"

#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputCoreTypes.h"
#include "Materials/MaterialInterface.h"
#include "Sailing/LyrisWindSettings.h"
#include "UObject/ConstructorHelpers.h"

namespace LyrisBoat
{
	static const float CmPerSecToKnots = 1.f / 51.444f;
}

ALyrisBoat::ALyrisBoat()
{
	PrimaryActorTick.bCanEverTick = true;
	AutoPossessPlayer = EAutoReceiveInput::Disabled;
	AutoPossessAI = EAutoPossessAI::Disabled;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeFinder(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderFinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> WoodFinder(TEXT("/Game/Lyris/Materials/Prototype/M_Wood.M_Wood"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> DarkWoodFinder(TEXT("/Game/Lyris/Materials/Prototype/M_DarkWood.M_DarkWood"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> SailFinder(TEXT("/Game/Lyris/Materials/Prototype/M_Sail.M_Sail"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> TerracottaFinder(TEXT("/Game/Lyris/Materials/Prototype/M_Terracotta.M_Terracotta"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> GoldFinder(TEXT("/Game/Lyris/Materials/Prototype/M_Gold.M_Gold"));

	UStaticMesh* Cube = CubeFinder.Object;
	UStaticMesh* Cylinder = CylinderFinder.Object;

	HullCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("HullCollision"));
	HullCollision->SetBoxExtent(FVector(300.f, 100.f, 60.f));
	HullCollision->SetCollisionProfileName(TEXT("Pawn"));
	HullCollision->SetCanEverAffectNavigation(false);
	RootComponent = HullCollision;

	Visual = CreateDefaultSubobject<USceneComponent>(TEXT("Visual"));
	Visual->SetupAttachment(HullCollision);

	// Hull, bow and trim (boat faces +X).
	MakePart(TEXT("Hull"), Cube, Visual, FVector(0.f, 0.f, 0.f), FVector(5.5f, 1.8f, 0.9f), WoodFinder.Object);
	MakePart(TEXT("Bow"), Cube, Visual, FVector(290.f, 0.f, 5.f), FVector(1.3f, 1.3f, 0.8f), WoodFinder.Object, FRotator(0.f, 45.f, 0.f));
	MakePart(TEXT("Trim"), Cube, Visual, FVector(0.f, 0.f, 46.f), FVector(5.6f, 1.85f, 0.08f), GoldFinder.Object);
	MakePart(TEXT("Mast"), Cylinder, Visual, FVector(40.f, 0.f, 370.f), FVector(0.15f, 0.15f, 6.5f), DarkWoodFinder.Object);
	MakePart(TEXT("Flag"), Cube, Visual, FVector(75.f, 0.f, 700.f), FVector(0.6f, 0.02f, 0.3f), TerracottaFinder.Object);

	// The sail swings around the mast to follow the wind and grows as it is raised.
	SailPivot = CreateDefaultSubobject<USceneComponent>(TEXT("SailPivot"));
	SailPivot->SetupAttachment(Visual);
	SailPivot->SetRelativeLocation(FVector(40.f, 0.f, 60.f));
	MakePart(TEXT("Boom"), Cylinder, SailPivot, FVector(-110.f, 0.f, 0.f), FVector(0.08f, 0.08f, 2.1f), DarkWoodFinder.Object, FRotator(90.f, 0.f, 0.f));
	MakePart(TEXT("Sail"), Cube, SailPivot, FVector(-110.f, 0.f, 240.f), FVector(2.0f, 0.04f, 4.6f), SailFinder.Object);
	MakePart(TEXT("SailStripe"), Cube, SailPivot, FVector(-110.f, 0.f, 290.f), FVector(2.02f, 0.05f, 0.7f), TerracottaFinder.Object);

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(HullCollision);
	CameraBoom->TargetArmLength = 1500.f;
	CameraBoom->SocketOffset = FVector(0.f, 0.f, 250.f);
	CameraBoom->bDoCollisionTest = false;
	CameraBoom->bEnableCameraLag = true;
	CameraBoom->CameraLagSpeed = 4.f;
	CameraBoom->bUsePawnControlRotation = false;
	CameraBoom->bInheritPitch = false;
	CameraBoom->bInheritYaw = false;
	CameraBoom->bInheritRoll = false;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	Camera->bUsePawnControlRotation = false;
}

UStaticMeshComponent* ALyrisBoat::MakePart(FName Name, UStaticMesh* Mesh, USceneComponent* Parent, FVector Location,
	FVector Scale, UMaterialInterface* Material, FRotator Rotation)
{
	UStaticMeshComponent* Part = CreateDefaultSubobject<UStaticMeshComponent>(Name);
	Part->SetupAttachment(Parent);
	if (Mesh)
	{
		Part->SetStaticMesh(Mesh);
	}
	if (Material)
	{
		Part->SetMaterial(0, Material);
	}
	Part->SetRelativeLocation(Location);
	Part->SetRelativeRotation(Rotation);
	Part->SetRelativeScale3D(Scale);
	Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Part->SetCanEverAffectNavigation(false);
	return Part;
}

void ALyrisBoat::RefreshWind()
{
	// One wind for the whole world: every boat reads the same shared source.
	if (const ULyrisWindSubsystem* WindSubsystem = ULyrisWindSubsystem::Get(this))
	{
		Wind = WindSubsystem->GetWindSample();
	}
	else
	{
		// No world subsystem (e.g. an editor preview): evaluate the same deterministic wind directly.
		const UWorld* World = GetWorld();
		Wind = ULyrisWindSubsystem::EvaluateWind(*ULyrisWindSettings::Get(), World ? World->GetTimeSeconds() : 0.0);
	}
}

float ALyrisBoat::GetSailEfficiency(float RelativeWindDeg, FString& OutPointOfSail) const
{
	// RelativeWindDeg: 0 = wind straight behind you, 90 = from the side, 180 = straight ahead.
	const float A = FMath::Abs(RelativeWindDeg);
	if (A >= 150.f)
	{
		OutPointOfSail = TEXT("In irons (into the wind)");
		return 0.05f;
	}
	if (A >= 120.f)
	{
		OutPointOfSail = TEXT("Close-hauled");
		return static_cast<float>(FMath::GetMappedRangeValueClamped(FVector2f(150.f, 120.f), FVector2f(0.05f, 0.75f), A));
	}
	if (A >= 60.f)
	{
		OutPointOfSail = TEXT("Beam reach (fastest)");
		return 1.f - FMath::Abs(A - 90.f) / 30.f * 0.25f;
	}
	OutPointOfSail = TEXT("Running downwind");
	return static_cast<float>(FMath::GetMappedRangeValueClamped(FVector2f(0.f, 60.f), FVector2f(0.65f, 0.75f), A));
}

void ALyrisBoat::Hint(int32 Slot, const FString& Text, const FColor& Color) const
{
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(static_cast<uint64>(71000 + Slot), 0.15f, Color, Text);
	}
}

void ALyrisBoat::Board(APlayerController* PC, APawn* Walker)
{
	StoredWalker = Walker;
	if (ACharacter* Character = Cast<ACharacter>(Walker))
	{
		Character->GetCharacterMovement()->DisableMovement();
	}
	Walker->SetActorHiddenInGame(true);
	Walker->SetActorEnableCollision(false);

	CameraYaw = 0.f;
	CameraPitch = -14.f;
	PC->Possess(this);
}

void ALyrisBoat::StepAshore(APlayerController* PC)
{
	APawn* Walker = StoredWalker;
	if (!Walker)
	{
		return;
	}

	Walker->SetActorLocation(DockPoint, false, nullptr, ETeleportType::TeleportPhysics);
	Walker->SetActorHiddenInGame(false);
	Walker->SetActorEnableCollision(true);
	if (ACharacter* Character = Cast<ACharacter>(Walker))
	{
		Character->GetCharacterMovement()->SetMovementMode(MOVE_Walking);
	}

	PC->Possess(Walker);
	PC->SetControlRotation(FRotator(-10.f, GetActorRotation().Yaw + 180.f, 0.f));
	StoredWalker = nullptr;
	Sail = 0.f;
}

void ALyrisBoat::UpdateSailing(float DeltaSeconds, APlayerController* PC)
{
	// Sail up / down.
	if (PC->IsInputKeyDown(EKeys::W) || PC->IsInputKeyDown(EKeys::Up))
	{
		Sail = FMath::Min(1.f, Sail + SailChangeRate * DeltaSeconds);
	}
	if (PC->IsInputKeyDown(EKeys::S) || PC->IsInputKeyDown(EKeys::Down))
	{
		Sail = FMath::Max(0.f, Sail - SailChangeRate * DeltaSeconds);
	}

	// Rudder eases toward the input so turns feel weighty.
	float Steer = 0.f;
	if (PC->IsInputKeyDown(EKeys::A) || PC->IsInputKeyDown(EKeys::Left))
	{
		Steer -= 1.f;
	}
	if (PC->IsInputKeyDown(EKeys::D) || PC->IsInputKeyDown(EKeys::Right))
	{
		Steer += 1.f;
	}
	Rudder = FMath::FInterpTo(Rudder, Steer, DeltaSeconds, 3.f);

	// Look around with the mouse.
	float MouseX = 0.f;
	float MouseY = 0.f;
	PC->GetInputMouseDelta(MouseX, MouseY);
	CameraYaw = FMath::Fmod(CameraYaw + MouseX * 1.5f, 360.f);
	CameraPitch = FMath::Clamp(CameraPitch + MouseY * 1.5f, -60.f, 10.f);

	// Wind and speed.
	const float BoatYaw = static_cast<float>(GetActorRotation().Yaw);
	const float WindYaw = GetWindYaw();
	const float Relative = FMath::FindDeltaAngleDegrees(BoatYaw, WindYaw);
	FString PointOfSail;
	const float Efficiency = GetSailEfficiency(Relative, PointOfSail);
	const float TargetSpeed = Sail * Efficiency * GetWindStrength() * MaxSpeed;
	Speed = FMath::FInterpTo(Speed, TargetSpeed, DeltaSeconds, 0.6f);

	// Steering works better with way on.
	const float Steerage = 0.3f + 0.7f * FMath::Clamp(Speed / (MaxSpeed * 0.5f), 0.f, 1.f);
	AddActorWorldRotation(FRotator(0.f, Rudder * TurnRate * Steerage * DeltaSeconds, 0.f));

	// Move, stopping against the island and the dock.
	FHitResult Hit;
	AddActorWorldOffset(GetActorForwardVector() * Speed * DeltaSeconds, true, &Hit);
	if (Hit.bBlockingHit)
	{
		Speed *= 0.2f;
		Hint(4, TEXT("Thud! You ran aground. Lower the sail (S) and steer away."), FColor(232, 160, 120));
	}

	// The lamps' light only reaches so far.
	const FVector Loc = GetActorLocation();
	const FVector2D Flat(Loc.X, Loc.Y);
	if (Flat.Size() > WorldRadius)
	{
		const FVector2D Back = Flat.GetSafeNormal() * WorldRadius;
		SetActorLocation(FVector(Back.X, Back.Y, Loc.Z));
		Speed *= 0.5f;
		Hint(4, TEXT("The mist beyond the lamps is too thick. Turn back toward the lighthouse."), FColor(170, 200, 230));
	}

	// Trim the sail across the wind and show how much is raised.
	SailPivot->SetRelativeRotation(FRotator(0.f, FMath::Clamp(Relative * 0.5f, -70.f, 70.f), 0.f));
	SailPivot->SetRelativeScale3D(FVector(1.f, 1.f, 0.25f + 0.75f * Sail));

	// Camera follows the boat's heading plus the mouse offset.
	CameraBoom->SetWorldRotation(FRotator(CameraPitch, BoatYaw + CameraYaw, 0.f));

	// On-screen readout.
	const float Knots = Speed * LyrisBoat::CmPerSecToKnots;
	const TCHAR* WindMood = Wind.CalmAlpha > 0.5f ? TEXT(" (calm)") : (Wind.GustAlpha > 0.5f ? TEXT(" (gusting)") : TEXT(""));
	Hint(1, FString::Printf(TEXT("Sail %d%%   |   Speed %.1f knots   |   %s   |   Wind %d%%%s"),
		FMath::RoundToInt(Sail * 100.f), Knots, *PointOfSail, FMath::RoundToInt(Wind.Strength * 100.f), WindMood),
		FColor(227, 174, 69));
	Hint(2, TEXT("W/S raise or lower sail   A/D steer   Mouse look   E step ashore at the dock"));
	if (FVector::Dist2D(Loc, DockPoint) < DockRadius)
	{
		Hint(3, TEXT("You're at the dock. Press E to step ashore."), FColor(122, 192, 230));
	}
}

void ALyrisBoat::UpdateFloating(float DeltaSeconds)
{
	// Gentle bobbing on the swell, plus heeling from the wind and the turn.
	const FVector Loc = GetActorLocation();
	const float Bob = 10.f * FMath::Sin(Clock * 1.3f);
	SetActorLocation(FVector(Loc.X, Loc.Y, WaterHeight + 25.f + Bob));

	const float Heel = -Rudder * 4.f + Sail * 5.f * FMath::Sin(FMath::DegreesToRadians(
		FMath::FindDeltaAngleDegrees(static_cast<float>(GetActorRotation().Yaw), GetWindYaw())));
	const float Roll = 2.5f * FMath::Sin(Clock * 0.9f) + Heel;
	const float Pitch = 1.5f * FMath::Sin(Clock * 1.1f);
	Visual->SetRelativeRotation(FRotator(Pitch, 0.f, Roll));

	if (!StoredWalker)
	{
		Speed = FMath::FInterpTo(Speed, 0.f, DeltaSeconds, 1.f);
		Rudder = FMath::FInterpTo(Rudder, 0.f, DeltaSeconds, 2.f);
	}
}

void ALyrisBoat::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Clock += DeltaSeconds;
	RefreshWind();

	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (PC)
	{
		const bool bInteractDown = PC->IsInputKeyDown(EKeys::E);
		const bool bInteractPressed = bInteractDown && !bInteractWasDown;
		bInteractWasDown = bInteractDown;

		APawn* Current = PC->GetPawn();
		if (Current == this)
		{
			UpdateSailing(DeltaSeconds, PC);
			if (bInteractPressed)
			{
				if (FVector::Dist2D(GetActorLocation(), DockPoint) < DockRadius)
				{
					StepAshore(PC);
				}
				else
				{
					Hint(3, TEXT("Sail back to the dock to step ashore."), FColor(122, 192, 230));
				}
			}
		}
		else if (Current)
		{
			// Fell into the sea? The tide carries you back to the dock.
			if (Current->GetActorLocation().Z < WaterHeight - 150.f)
			{
				Current->SetActorLocation(DockPoint, false, nullptr, ETeleportType::TeleportPhysics);
				if (ACharacter* Character = Cast<ACharacter>(Current))
				{
					Character->GetCharacterMovement()->StopMovementImmediately();
				}
				Hint(4, TEXT("Splash! The tide carried you back to the dock."), FColor(122, 192, 230));
			}

			if (FVector::Dist2D(Current->GetActorLocation(), GetActorLocation()) < BoardRadius)
			{
				Hint(3, TEXT("Press E to board the boat"), FColor(227, 174, 69));
				if (bInteractPressed)
				{
					Board(PC, Current);
				}
			}
			else
			{
				Hint(2, TEXT("Walk down the dock to the boat. WASD move, Space jump, Mouse look."));
			}
		}
	}

	UpdateFloating(DeltaSeconds);
}
