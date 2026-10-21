// Lyris player: swimming in the shared sea (T20). Calm by default: no drowning, no stamina, no damage.

#include "Player/LyrisSwimComponent.h"

#include "Camera/PlayerCameraManager.h"
#include "CollisionQueryParams.h"
#include "Components/CapsuleComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Lyris.h"
#include "LyrisBoat.h"
#include "World/LyrisOceanSubsystem.h"

namespace LyrisSwim
{
	/** Spring integration step; keeps the buoyancy stable at low frame rates. */
	static constexpr float MaxSubstep = 1.f / 60.f;

	/** How often (s) the "far from home" distance check runs. */
	static constexpr float FarCheckInterval = 0.5f;

	/** How often (s) we look for a ledge in front while pushing toward it. */
	static constexpr float ClimbCheckInterval = 0.1f;

	/** Only static and movable scenery count as ground or ledges: never pawns (boats, other players). */
	static FCollisionObjectQueryParams SceneryObjects()
	{
		FCollisionObjectQueryParams Objects;
		Objects.AddObjectTypesToQuery(ECC_WorldStatic);
		Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
		return Objects;
	}

	static float SmoothStep01(float X)
	{
		X = FMath::Clamp(X, 0.f, 1.f);
		return X * X * (3.f - 2.f * X);
	}
}

ULyrisSwimComponent::ULyrisSwimComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;

	// Last-resort defaults (the retired Harbor map); BeginPlay replaces them with tagged actors.
	HomeAnchors.Add(FVector::ZeroVector);
	HomeAnchors.Add(ReturnPoint);
}

void ULyrisSwimComponent::BeginPlay()
{
	Super::BeginPlay();

	Character = Cast<ACharacter>(GetOwner());
	Movement = Character ? Character->GetCharacterMovement() : nullptr;
	if (!Character || !Movement)
	{
		SetComponentTickEnabled(false);
		return;
	}

	// We set the vertical position before the movement component does its horizontal move each frame.
	Movement->AddTickPrerequisiteComponent(this);

	FindTideHome();
}

void ULyrisSwimComponent::FindTideHome()
{
	TArray<AActor*> Homes;
	UGameplayStatics::GetAllActorsWithTag(this, TideHomeTag, Homes);
	if (Homes.Num() == 0)
	{
		UGameplayStatics::GetAllActorsWithTag(this, DockPointTag, Homes);
	}
	if (Homes.Num() == 0)
	{
		UE_LOG(LogLyris, Warning, TEXT("LyrisSwimComponent: no actor tagged %s or %s; the tide uses the default ReturnPoint %s."),
			*TideHomeTag.ToString(), *DockPointTag.ToString(), *ReturnPoint.ToString());
		return;
	}

	// Every tagged point counts as home; the tide returns you to the nearest one to where you start.
	const FVector Start = Character->GetActorLocation();
	HomeAnchors.Reset();
	float BestDistSq = TNumericLimits<float>::Max();
	for (const AActor* Home : Homes)
	{
		const FVector HomeLocation = Home->GetActorLocation();
		HomeAnchors.Add(HomeLocation);
		const float DistSq = FVector::DistSquared(Start, HomeLocation);
		if (DistSq < BestDistSq)
		{
			BestDistSq = DistSq;
			ReturnPoint = HomeLocation;
		}
	}

	// The tagged point sits at standing height on the deck; settle onto whatever is below it in case it was
	// placed higher, keeping the capsule's half height above the surface.
	if (const UCapsuleComponent* Capsule = Character->GetCapsuleComponent())
	{
		FHitResult Hit;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(LyrisTideHome), false, Character);
		const FVector TraceStart = ReturnPoint + FVector(0.f, 0.f, 200.f);
		const FVector TraceEnd = ReturnPoint - FVector(0.f, 0.f, 1000.f);
		if (GetWorld()->LineTraceSingleByChannel(Hit, TraceStart, TraceEnd, ECC_Visibility, Params))
		{
			ReturnPoint.Z = Hit.ImpactPoint.Z + Capsule->GetScaledCapsuleHalfHeight() + 2.f;
		}
	}
}

void ULyrisSwimComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (bSwimming && Movement)
	{
		Movement->MaxFlySpeed = SavedMaxFlySpeed;
		Movement->BrakingDecelerationFlying = SavedBrakingFlying;
	}
	Super::EndPlay(EndPlayReason);
}

// ----------------------------------------------------------------------------- ocean queries

ULyrisOceanSubsystem* ULyrisSwimComponent::GetOcean() const
{
	return ULyrisOceanSubsystem::Get(this);
}

float ULyrisSwimComponent::GetWaterHeight(const FVector& Location) const
{
	if (const ULyrisOceanSubsystem* Ocean = GetOcean())
	{
		return Ocean->GetWaterHeightAt(FVector2D(Location.X, Location.Y));
	}
	return 0.f;
}

FVector ULyrisSwimComponent::GetWaterVelocity(const FVector& Location) const
{
	if (const ULyrisOceanSubsystem* Ocean = GetOcean())
	{
		return Ocean->GetWaterVelocityAt(FVector2D(Location.X, Location.Y));
	}
	return FVector::ZeroVector;
}

float ULyrisSwimComponent::ProbeWaterDepth(const FVector& Location, float WaterZ, float MaxDepth, FHitResult* OutGround) const
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return MaxDepth;
	}

	FCollisionQueryParams Params(SCENE_QUERY_STAT(LyrisSwimDepth), false, GetOwner());
	const FVector Start(Location.X, Location.Y, FMath::Max(static_cast<float>(Location.Z), WaterZ));
	const FVector End(Location.X, Location.Y, WaterZ - MaxDepth);

	FHitResult Hit;
	if (World->LineTraceSingleByObjectType(Hit, Start, End, LyrisSwim::SceneryObjects(), Params))
	{
		if (OutGround)
		{
			*OutGround = Hit;
		}
		return FMath::Max(0.f, WaterZ - static_cast<float>(Hit.ImpactPoint.Z));
	}
	return MaxDepth;
}

// ----------------------------------------------------------------------------- tick

bool ULyrisSwimComponent::IsAboardOrDisabled() const
{
	// ALyrisBoat::Board hides the walker, turns off its collision and possesses the boat.
	return !Character->GetController() || Character->IsHidden() || !Character->GetActorEnableCollision();
}

void ULyrisSwimComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (!Character || !Movement || DeltaTime <= 0.f)
	{
		return;
	}

	UpdateReturn(DeltaTime);

	if (IsAboardOrDisabled())
	{
		// Boarded the boat (or unpossessed). Drop the swim state quietly; whoever moves us next sets the mode.
		if (bSwimming)
		{
			Movement->MaxFlySpeed = SavedMaxFlySpeed;
			Movement->BrakingDecelerationFlying = SavedBrakingFlying;
			bSwimming = false;
			bClimbing = false;
		}
		FarTime = 0.f;
		bIsFar = false;
		return;
	}

	StateTime += DeltaTime;
	KickCooldownLeft = FMath::Max(0.f, KickCooldownLeft - DeltaTime);

	const FVector Loc = Character->GetActorLocation();
	const float WaterZ = GetWaterHeight(Loc);
	const float HalfHeight = Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();

	if (!bSwimming)
	{
		FarTime = 0.f;
		bIsFar = false;

		const EMovementMode Mode = Movement->MovementMode;
		const bool bCanEnter = Mode == MOVE_Walking || Mode == MOVE_NavWalking || Mode == MOVE_Falling;
		const float FeetZ = static_cast<float>(Loc.Z) - HalfHeight;
		if (bCanEnter && FeetZ < WaterZ && StateTime >= MinStateTime)
		{
			// Deep enough to swim? Standing in the surf stays walking.
			if (ProbeWaterDepth(Loc, WaterZ, EnterDepth + 1.f) > EnterDepth)
			{
				StartSwimming();
			}
		}
		return;
	}

	// Something else changed our mode (a teleport, a cutscene): let it win.
	if (!bClimbing && Movement->MovementMode != MOVE_Flying)
	{
		Movement->MaxFlySpeed = SavedMaxFlySpeed;
		Movement->BrakingDecelerationFlying = SavedBrakingFlying;
		bSwimming = false;
		return;
	}

	if (bClimbing)
	{
		UpdateClimb(DeltaTime);
		return;
	}

	// Reached the shallows: stand up and walk out.
	if (StateTime >= MinStateTime)
	{
		FHitResult Ground;
		const float Depth = ProbeWaterDepth(Loc, WaterZ, ExitDepth + 1.f, &Ground);
		if (Depth < ExitDepth && Ground.bBlockingHit && Movement->IsWalkable(Ground))
		{
			StopSwimming(MOVE_Walking);
			return;
		}
	}

	// Pushing toward a dock or low ledge: climb out onto it.
	const FVector Input = Character->GetLastMovementInputVector();
	const FVector2D InputDir2D(Input.X, Input.Y);
	ClimbCheckTimer -= DeltaTime;
	if (InputDir2D.SizeSquared() > 0.25f && ClimbCheckTimer <= 0.f)
	{
		ClimbCheckTimer = LyrisSwim::ClimbCheckInterval;
		if (TryStartClimb(InputDir2D.GetSafeNormal(), WaterZ))
		{
			return;
		}
	}

	UpdateFloating(DeltaTime, WaterZ);
	UpdateTide(DeltaTime);
}

// ----------------------------------------------------------------------------- swim state

void ULyrisSwimComponent::StartSwimming()
{
	bSwimming = true;
	bClimbing = false;
	StateTime = 0.f;
	FarTime = 0.f;
	bIsFar = false;

	// Keep the fall's momentum for a short dip, then the water holds you up.
	VerticalSpeed = FMath::Max(static_cast<float>(Movement->Velocity.Z), -MaxEntrySinkSpeed);

	SavedMaxFlySpeed = Movement->MaxFlySpeed;
	SavedBrakingFlying = Movement->BrakingDecelerationFlying;
	Movement->MaxFlySpeed = SwimSpeed;
	Movement->BrakingDecelerationFlying = SwimBraking;

	// Flying = input-driven movement with collision and no gravity. We own the vertical axis.
	Movement->SetMovementMode(MOVE_Flying);
	Movement->Velocity.Z = 0.f;
}

void ULyrisSwimComponent::StopSwimming(EMovementMode NewMode)
{
	Movement->MaxFlySpeed = SavedMaxFlySpeed;
	Movement->BrakingDecelerationFlying = SavedBrakingFlying;

	bSwimming = false;
	bClimbing = false;
	StateTime = 0.f;
	VerticalSpeed = 0.f;
	FarTime = 0.f;
	bIsFar = false;

	Movement->Velocity.Z = 0.f;
	Movement->SetMovementMode(NewMode);
}

bool ULyrisSwimComponent::HandleJumpPressed()
{
	if (!bSwimming || !Character || !Movement)
	{
		return false;
	}
	if (bClimbing)
	{
		return true;
	}

	// Jump next to a ledge climbs out; otherwise it's a little kick up out of the water.
	const float WaterZ = GetWaterHeight(Character->GetActorLocation());
	const FVector Forward = Character->GetActorForwardVector();
	if (TryStartClimb(FVector2D(Forward.X, Forward.Y).GetSafeNormal(), WaterZ))
	{
		return true;
	}

	if (KickCooldownLeft <= 0.f)
	{
		VerticalSpeed = KickSpeed;
		KickCooldownLeft = KickCooldown;
	}
	return true;
}

// ----------------------------------------------------------------------------- floating

void ULyrisSwimComponent::UpdateFloating(float DeltaTime, float WaterZ)
{
	// Keep the horizontal move to the movement component (flying); never let it add vertical speed.
	Movement->Velocity.Z = 0.f;

	// Damped spring toward "FloatDepth below the wave surface". Substepped so it is stable at any frame rate.
	const float Omega = BuoyancyFrequency;
	const float TargetZ = WaterZ - FloatDepth;
	float Z = static_cast<float>(Character->GetActorLocation().Z);
	const float StartZ = Z;
	float Remaining = FMath::Min(DeltaTime, 0.1f);
	while (Remaining > KINDA_SMALL_NUMBER)
	{
		const float Step = FMath::Min(Remaining, LyrisSwim::MaxSubstep);
		const float Accel = Omega * Omega * (TargetZ - Z) - 2.f * BuoyancyDamping * Omega * VerticalSpeed;
		VerticalSpeed += Accel * Step;
		Z += VerticalSpeed * Step;
		Remaining -= Step;
	}

	// The swell nudges you along a little.
	const FVector Current = GetWaterVelocity(Character->GetActorLocation()) * DriftScale;

	const FVector Delta(Current.X * DeltaTime, Current.Y * DeltaTime, Z - StartZ);
	if (Delta.IsNearlyZero())
	{
		return;
	}

	FHitResult Hit;
	Movement->SafeMoveUpdatedComponent(Delta, Movement->UpdatedComponent->GetComponentQuat(), true, Hit);
	if (Hit.bBlockingHit)
	{
		// Bumped the seabed or the underside of the dock: stop pushing into it.
		if ((VerticalSpeed < 0.f && Hit.Normal.Z > 0.f) || (VerticalSpeed > 0.f && Hit.Normal.Z < 0.f))
		{
			VerticalSpeed = 0.f;
		}
		UMovementComponent* BaseMovement = Movement.Get(); // SlideAlongSurface is public on the base class
		BaseMovement->SlideAlongSurface(Delta, 1.f - Hit.Time, Hit.Normal, Hit, true);
	}
}

// ----------------------------------------------------------------------------- climbing out

bool ULyrisSwimComponent::TryStartClimb(const FVector2D& Direction, float WaterZ)
{
	UWorld* World = GetWorld();
	if (!World || Direction.IsNearlyZero())
	{
		return false;
	}

	UCapsuleComponent* Capsule = Character->GetCapsuleComponent();
	const float Radius = Capsule->GetScaledCapsuleRadius();
	const float HalfHeight = Capsule->GetScaledCapsuleHalfHeight();
	const FVector Loc = Character->GetActorLocation();
	const FVector Dir(Direction.X, Direction.Y, 0.f);

	FCollisionQueryParams Params(SCENE_QUERY_STAT(LyrisSwimClimb), false, Character.Get());

	// Look down onto whatever is just in front, from above the highest ledge we can reach.
	const FVector Ahead = Loc + Dir * (Radius + 50.f);
	const FVector Start(Ahead.X, Ahead.Y, WaterZ + ClimbMaxHeight + 10.f);
	const FVector End(Ahead.X, Ahead.Y, WaterZ + ClimbMinHeight - 1.f);
	FHitResult Top;
	if (!World->LineTraceSingleByObjectType(Top, Start, End, LyrisSwim::SceneryObjects(), Params))
	{
		return false;
	}
	if (Top.bStartPenetrating || !Movement->IsWalkable(Top))
	{
		return false;
	}
	// Only a lip that stands out of the water: gentle beaches are handled by standing up in the shallows.
	const float TopZ = static_cast<float>(Top.ImpactPoint.Z);
	if (TopZ > WaterZ + ClimbMaxHeight || TopZ < WaterZ + ClimbMinHeight)
	{
		return false;
	}

	// Stand a little way onto the ledge, and make sure there is room: straight up first, then across.
	const FVector Dest(Top.ImpactPoint.X + Dir.X * 10.f, Top.ImpactPoint.Y + Dir.Y * 10.f, TopZ + HalfHeight + 2.f);
	const FVector Rise(Loc.X, Loc.Y, FMath::Max(Dest.Z, Loc.Z));
	const FCollisionShape Shape = FCollisionShape::MakeCapsule(Radius, HalfHeight);
	const ECollisionChannel Channel = Capsule->GetCollisionObjectType();
	FCollisionResponseParams Responses;
	Capsule->InitSweepCollisionParams(Params, Responses);

	if (World->OverlapBlockingTestByChannel(Dest, FQuat::Identity, Channel, Shape, Params, Responses))
	{
		return false;
	}
	FHitResult Blocked;
	if (World->SweepSingleByChannel(Blocked, Loc, Rise, FQuat::Identity, Channel, Shape, Params, Responses) ||
		World->SweepSingleByChannel(Blocked, Rise, Dest, FQuat::Identity, Channel, Shape, Params, Responses))
	{
		return false;
	}

	ClimbFrom = Loc;
	ClimbTo = Dest;
	ClimbAlpha = 0.f;
	bClimbing = true;
	VerticalSpeed = 0.f;

	// Hold still while the climb plays; UpdateClimb moves us.
	Movement->StopMovementImmediately();
	Movement->DisableMovement();
	Character->SetActorRotation(FRotator(0.f, Dir.Rotation().Yaw, 0.f));
	return true;
}

void ULyrisSwimComponent::UpdateClimb(float DeltaTime)
{
	ClimbAlpha = FMath::Min(1.f, ClimbAlpha + DeltaTime / ClimbDuration);

	// Rise first (ease out), then step forward onto the ledge (ease in).
	const float Up = LyrisSwim::SmoothStep01(ClimbAlpha / 0.6f);
	const float Across = LyrisSwim::SmoothStep01((ClimbAlpha - 0.35f) / 0.65f);
	const FVector Pos(
		FMath::Lerp(ClimbFrom.X, ClimbTo.X, static_cast<double>(Across)),
		FMath::Lerp(ClimbFrom.Y, ClimbTo.Y, static_cast<double>(Across)),
		FMath::Lerp(ClimbFrom.Z, ClimbTo.Z, static_cast<double>(Up)));
	Character->SetActorLocation(Pos, false, nullptr, ETeleportType::None);

	if (ClimbAlpha >= 1.f)
	{
		StopSwimming(MOVE_Walking);
	}
}

// ----------------------------------------------------------------------------- the tide brings you home

bool ULyrisSwimComponent::IsFarFromHome() const
{
	const FVector Loc = Character->GetActorLocation();
	const float FarSq = FarDistance * FarDistance;

	for (const FVector& Anchor : HomeAnchors)
	{
		if (FVector::DistSquared2D(Loc, Anchor) < FarSq)
		{
			return false;
		}
	}
	for (TActorIterator<ALyrisBoat> It(GetWorld()); It; ++It)
	{
		if (FVector::DistSquared2D(Loc, It->GetActorLocation()) < FarSq)
		{
			return false;
		}
	}
	return true;
}

void ULyrisSwimComponent::UpdateTide(float DeltaTime)
{
	if (ReturnPhase != EReturnPhase::None)
	{
		return;
	}

	FarCheckTimer -= DeltaTime;
	if (FarCheckTimer <= 0.f)
	{
		FarCheckTimer = LyrisSwim::FarCheckInterval;
		bIsFar = IsFarFromHome();
	}

	if (!bIsFar)
	{
		FarTime = FMath::Max(0.f, FarTime - DeltaTime * 2.f);
		return;
	}

	FarTime += DeltaTime;
	if (FarTime >= FarReturnTime)
	{
		ReturnPhase = EReturnPhase::FadingOut;
		ReturnTimer = ReturnFadeTime;
		// Remember the controller: if the player boards the boat mid-fade it stops being ours, and the
		// fade back in must still run on its camera.
		FadeController = Cast<APlayerController>(Character->GetController());
		if (APlayerController* PC = FadeController.Get())
		{
			if (PC->PlayerCameraManager)
			{
				PC->PlayerCameraManager->StartCameraFade(0.f, 1.f, ReturnFadeTime, FLinearColor::Black, false, true);
			}
		}
	}
	else if (FarTime >= FarWarnTime)
	{
		Hint(1, TEXT("The current is drawing you out to sea. Swim back toward the island or your boat."));
	}
}

void ULyrisSwimComponent::UpdateReturn(float DeltaTime)
{
	if (ReturnPhase == EReturnPhase::None)
	{
		return;
	}

	ReturnTimer -= DeltaTime;
	if (ReturnTimer > 0.f)
	{
		return;
	}

	APlayerController* PC = FadeController.Get();

	if (ReturnPhase == EReturnPhase::FadingOut)
	{
		// Only bring them home if they are still adrift; boarding or reaching shore meanwhile cancels it.
		if (bSwimming && !bClimbing && !IsAboardOrDisabled())
		{
			StopSwimming(MOVE_Walking);
			Character->SetActorLocationAndRotation(ReturnPoint, FRotator(0.f, ReturnYaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
			Movement->StopMovementImmediately();
			if (PC && PC->GetPawn() == Character)
			{
				PC->SetControlRotation(FRotator(-10.f, ReturnYaw, 0.f));
			}
			Hint(1, TEXT("The tide carried you gently back to the dock."), 5.f);
		}

		if (PC && PC->PlayerCameraManager)
		{
			PC->PlayerCameraManager->StartCameraFade(1.f, 0.f, ReturnFadeTime, FLinearColor::Black, false, false);
		}
		ReturnPhase = EReturnPhase::FadingIn;
		ReturnTimer = ReturnFadeTime;
		return;
	}

	ReturnPhase = EReturnPhase::None;
	FadeController.Reset();
}

void ULyrisSwimComponent::Hint(int32 Slot, const FString& Text, float Seconds) const
{
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(static_cast<uint64>(72000 + Slot), Seconds, FColor(122, 192, 230), Text);
	}
}
