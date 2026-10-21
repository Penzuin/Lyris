// Lyris player: walking, sprint, jump and climbing, with Breath paying for sprint and climb.
// Behaviour ported from the approved prototype (wayfarers_breath.html, step()).

#include "Player/LyrisCharacterMovementComponent.h"
#include "Player/LyrisMovementSettings.h"
#include "Player/LyrisStaminaComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/Pawn.h"
#include "CollisionQueryParams.h"

// ---------------------------------------------------------------------------------------------
// Network prediction: sprint and jump-held ride along in each saved move so the server runs the
// same movement as the client.
// ---------------------------------------------------------------------------------------------

class FLyrisSavedMove : public FSavedMove_Character
{
public:
	typedef FSavedMove_Character Super;

	uint8 bSavedSprintInput : 1;
	uint8 bSavedJumpInput : 1;

	FLyrisSavedMove()
		: bSavedSprintInput(0)
		, bSavedJumpInput(0)
	{
	}

	virtual void Clear() override
	{
		Super::Clear();
		bSavedSprintInput = 0;
		bSavedJumpInput = 0;
	}

	virtual uint8 GetCompressedFlags() const override
	{
		uint8 Result = Super::GetCompressedFlags();
		if (bSavedSprintInput)
		{
			Result |= FLAG_Custom_0;
		}
		if (bSavedJumpInput)
		{
			Result |= FLAG_Custom_1;
		}
		return Result;
	}

	virtual bool CanCombineWith(const FSavedMovePtr& NewMove, ACharacter* InCharacter, float MaxDelta) const override
	{
		const FLyrisSavedMove* Other = static_cast<const FLyrisSavedMove*>(NewMove.Get());
		if (!Other || Other->bSavedSprintInput != bSavedSprintInput || Other->bSavedJumpInput != bSavedJumpInput)
		{
			return false;
		}
		return Super::CanCombineWith(NewMove, InCharacter, MaxDelta);
	}

	virtual void SetMoveFor(ACharacter* C, float InDeltaTime, FVector const& NewAccel, FNetworkPredictionData_Client_Character& ClientData) override
	{
		Super::SetMoveFor(C, InDeltaTime, NewAccel, ClientData);
		if (const ULyrisCharacterMovementComponent* Move = C ? Cast<ULyrisCharacterMovementComponent>(C->GetCharacterMovement()) : nullptr)
		{
			bSavedSprintInput = Move->GetSprintInput();
			bSavedJumpInput = Move->GetJumpInput();
		}
	}

	virtual void PrepMoveFor(ACharacter* C) override
	{
		Super::PrepMoveFor(C);
		if (ULyrisCharacterMovementComponent* Move = C ? Cast<ULyrisCharacterMovementComponent>(C->GetCharacterMovement()) : nullptr)
		{
			Move->SetSprintInput(bSavedSprintInput != 0);
			Move->SetJumpInput(bSavedJumpInput != 0);
		}
	}
};

class FLyrisNetworkPredictionData_Client : public FNetworkPredictionData_Client_Character
{
public:
	typedef FNetworkPredictionData_Client_Character Super;

	explicit FLyrisNetworkPredictionData_Client(const UCharacterMovementComponent& ClientMovement)
		: Super(ClientMovement)
	{
	}

	virtual FSavedMovePtr AllocateNewMove() override
	{
		return FSavedMovePtr(new FLyrisSavedMove());
	}
};

// ---------------------------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------------------------

namespace LyrisMovement
{
	static const ULyrisMovementSettings& Settings()
	{
		return *ULyrisMovementSettings::Get();
	}

	static FVector Flat(const FVector& V)
	{
		return FVector(V.X, V.Y, 0.f).GetSafeNormal();
	}

	/** Below this stick length, input counts as "not pushing". */
	static constexpr float InputDeadZone = 0.1f;
}

ULyrisCharacterMovementComponent::ULyrisCharacterMovementComponent()
{
	// Matching defaults so the Blueprint editor shows sensible values; the live numbers come from
	// Project Settings > Game > Lyris Movement (ApplySettings) once play starts.
	MaxWalkSpeed = 450.f;
	AirControl = 0.6f;
	MaxCustomMovementSpeed = 220.f;
}

void ULyrisCharacterMovementComponent::BeginPlay()
{
	Super::BeginPlay();
	ApplySettings();
	CachedStamina = nullptr;
}

void ULyrisCharacterMovementComponent::ApplySettings()
{
	const ULyrisMovementSettings& S = LyrisMovement::Settings();
	MaxWalkSpeed = S.WalkSpeed;
	AirControl = S.AirControl;
	MaxCustomMovementSpeed = S.ClimbSpeed;

	// Launch speed for the wanted apex under the current gravity: v = sqrt(2 g h).
	float Gravity = FMath::Abs(GetGravityZ());
	if (Gravity < 1.f)
	{
		Gravity = 980.f;
	}
	JumpZVelocity = FMath::Sqrt(2.f * Gravity * FMath::Max(0.f, S.JumpApexHeight));
}

FNetworkPredictionData_Client* ULyrisCharacterMovementComponent::GetPredictionData_Client() const
{
	if (ClientPredictionData == nullptr)
	{
		ULyrisCharacterMovementComponent* MutableThis = const_cast<ULyrisCharacterMovementComponent*>(this);
		MutableThis->ClientPredictionData = new FLyrisNetworkPredictionData_Client(*this);
	}
	return ClientPredictionData;
}

void ULyrisCharacterMovementComponent::UpdateFromCompressedFlags(uint8 Flags)
{
	Super::UpdateFromCompressedFlags(Flags);
	bSprintInput = (Flags & FSavedMove_Character::FLAG_Custom_0) != 0;
	bJumpInput = (Flags & FSavedMove_Character::FLAG_Custom_1) != 0;
}

// ---------------------------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------------------------

ULyrisStaminaComponent* ULyrisCharacterMovementComponent::GetStamina() const
{
	if (!CachedStamina.IsValid())
	{
		if (const AActor* Owner = GetOwner())
		{
			CachedStamina = Owner->FindComponentByClass<ULyrisStaminaComponent>();
		}
	}
	return CachedStamina.Get();
}

bool ULyrisCharacterMovementComponent::IsClimbing() const
{
	return MovementMode == MOVE_Custom && CustomMovementMode == static_cast<uint8>(ELyrisMovementMode::Climbing);
}

bool ULyrisCharacterMovementComponent::WantsToSprint() const
{
	if (!bSprintInput || IsCrouching())
	{
		return false;
	}
	const ULyrisStaminaComponent* Stamina = GetStamina();
	return !Stamina || (!Stamina->IsWinded() && Stamina->GetCurrent() + Stamina->GetBonus() > 0.f);
}

bool ULyrisCharacterMovementComponent::IsSprinting() const
{
	return WantsToSprint() && IsMovingOnGround() && !Acceleration.IsNearlyZero() && Velocity.SizeSquared2D() > FMath::Square(10.f);
}

FVector ULyrisCharacterMovementComponent::GetInputVector() const
{
	const float MaxAccel = GetMaxAcceleration();
	if (MaxAccel <= UE_KINDA_SMALL_NUMBER)
	{
		return FVector::ZeroVector;
	}
	return (Acceleration / MaxAccel).GetClampedToMaxSize(1.f);
}

float ULyrisCharacterMovementComponent::GetMaxSpeed() const
{
	if (IsClimbing())
	{
		return LyrisMovement::Settings().ClimbSpeed;
	}
	if ((MovementMode == MOVE_Walking || MovementMode == MOVE_NavWalking || MovementMode == MOVE_Falling) && !IsCrouching())
	{
		// Sprint keeps its speed through a jump, but only drains Breath on the ground.
		const ULyrisMovementSettings& S = LyrisMovement::Settings();
		return WantsToSprint() ? S.SprintSpeed : S.WalkSpeed;
	}
	return Super::GetMaxSpeed();
}

bool ULyrisCharacterMovementComponent::CanAttemptJump() const
{
	// On land and on walls, jumping is handled here (buffer, coyote time, leap, kick) instead of by
	// ACharacter. In water ALyrisCharacter::Jump hands the press to ULyrisSwimComponent first (T20).
	if (IsSwimming())
	{
		return Super::CanAttemptJump();
	}
	return false;
}

void ULyrisCharacterMovementComponent::PhysicsRotation(float DeltaTime)
{
	// On a wall you face the wall, whatever the stick says.
	if (IsClimbing())
	{
		return;
	}
	Super::PhysicsRotation(DeltaTime);
}

// ---------------------------------------------------------------------------------------------
// Breath
// ---------------------------------------------------------------------------------------------

bool ULyrisCharacterMovementComponent::ShouldApplyBreath() const
{
	// Not while the client replays old moves after a correction (it was already spent), and not on
	// other players' copies (the server tells us their Breath).
	return CharacterOwner && !CharacterOwner->bClientUpdating && CharacterOwner->GetLocalRole() > ROLE_SimulatedProxy;
}

bool ULyrisCharacterMovementComponent::HasBreathToClimb() const
{
	const ULyrisStaminaComponent* Stamina = GetStamina();
	return !Stamina || (!Stamina->IsWinded() && Stamina->GetCurrent() + Stamina->GetBonus() > 0.f);
}

bool ULyrisCharacterMovementComponent::TrySpendBreath(float Amount)
{
	ULyrisStaminaComponent* Stamina = GetStamina();
	if (!Stamina)
	{
		return true;
	}
	return ShouldApplyBreath() ? Stamina->TrySpend(Amount) : Stamina->CanAfford(Amount);
}

void ULyrisCharacterMovementComponent::DrainBreath(float Amount)
{
	if (ULyrisStaminaComponent* Stamina = GetStamina())
	{
		if (ShouldApplyBreath())
		{
			Stamina->Drain(Amount);
		}
	}
}

// ---------------------------------------------------------------------------------------------
// Per-move update: jump, grabbing walls, sprint drain
// ---------------------------------------------------------------------------------------------

void ULyrisCharacterMovementComponent::UpdateCharacterStateBeforeMovement(float DeltaSeconds)
{
	Super::UpdateCharacterStateBeforeMovement(DeltaSeconds);

	ApplySettings();

	// A jump press is remembered for a moment (buffer), so pressing just before landing still jumps.
	const bool bJumpPressedThisMove = bJumpInput && !bJumpInputLastFrame;
	bJumpInputLastFrame = bJumpInput;
	if (bJumpPressedThisMove)
	{
		JumpBufferRemaining = LyrisMovement::Settings().JumpBufferTime;
	}
	else
	{
		JumpBufferRemaining = FMath::Max(0.f, JumpBufferRemaining - DeltaSeconds);
	}
	RegrabCooldown = FMath::Max(0.f, RegrabCooldown - DeltaSeconds);

	if (IsSwimming() || MovementMode == MOVE_None || MovementMode == MOVE_Flying)
	{
		// Swimming never uses Breath, and none of the land rules apply. ULyrisSwimComponent (T20) swims
		// in MOVE_Flying and parks the character in MOVE_None for its climb-out; aboard the boat is MOVE_None too.
		JumpBufferRemaining = 0.f;
		CoyoteRemaining = 0.f;
		bJumpCutAvailable = false;
		GroundPushTime = 0.f;
		return;
	}

	if (IsClimbing())
	{
		// Leap, kick, drain and letting go are handled in PhysClimbing.
		return;
	}

	TickJump(DeltaSeconds);
	TryGrabWall(DeltaSeconds);
}

void ULyrisCharacterMovementComponent::TickJump(float DeltaSeconds)
{
	const ULyrisMovementSettings& S = LyrisMovement::Settings();

	// Coyote time: a jump still works for a moment after walking off a ledge.
	if (IsMovingOnGround())
	{
		CoyoteRemaining = S.CoyoteTime;
	}
	else
	{
		CoyoteRemaining = FMath::Max(0.f, CoyoteRemaining - DeltaSeconds);
	}

	if (JumpBufferRemaining > 0.f && CoyoteRemaining > 0.f && (IsMovingOnGround() || IsFalling()))
	{
		DoLyrisJump();
	}

	// Variable height: let go while still rising and the jump is cut short.
	if (bJumpCutAvailable && IsFalling())
	{
		if (Velocity.Z <= 0.f)
		{
			bJumpCutAvailable = false;
		}
		else if (!bJumpInput)
		{
			Velocity.Z *= S.JumpReleaseVelocityScale;
			bJumpCutAvailable = false;
		}
	}
}

void ULyrisCharacterMovementComponent::DoLyrisJump()
{
	const ULyrisMovementSettings& S = LyrisMovement::Settings();

	JumpBufferRemaining = 0.f;
	CoyoteRemaining = 0.f;

	// Walking and jumping are free; a sprint jump costs a little.
	if (WantsToSprint() && !Acceleration.IsNearlyZero())
	{
		DrainBreath(S.SprintJumpBreath);
	}

	Velocity.Z = FMath::Max<FVector::FReal>(Velocity.Z, JumpZVelocity);
	SetMovementMode(MOVE_Falling);
	bJumpCutAvailable = true;

	if (CharacterOwner && !CharacterOwner->bClientUpdating)
	{
		CharacterOwner->OnJumped();
	}
}

void ULyrisCharacterMovementComponent::OnMovementUpdated(float DeltaSeconds, const FVector& OldLocation, const FVector& OldVelocity)
{
	Super::OnMovementUpdated(DeltaSeconds, OldLocation, OldVelocity);

	// Sprint drains only while actually moving on the ground; in the air and in water it's free.
	if (IsSprinting())
	{
		DrainBreath(LyrisMovement::Settings().SprintBreathPerSecond * DeltaSeconds);
	}
}

void ULyrisCharacterMovementComponent::OnMovementModeChanged(EMovementMode PreviousMovementMode, uint8 PreviousCustomMode)
{
	Super::OnMovementModeChanged(PreviousMovementMode, PreviousCustomMode);

	const bool bWasClimbing = PreviousMovementMode == MOVE_Custom && PreviousCustomMode == static_cast<uint8>(ELyrisMovementMode::Climbing);

	if (IsClimbing())
	{
		bJumpCutAvailable = false;
		CoyoteRemaining = 0.f;
		if (ULyrisStaminaComponent* Stamina = GetStamina())
		{
			Stamina->SetPreviewCost(LyrisMovement::Settings().ClimbLeapBreath);
		}
	}
	else if (bWasClimbing)
	{
		bMantling = false;
		LeapTimeRemaining = 0.f;
		ClimbNormal = FVector::ZeroVector;
		if (ULyrisStaminaComponent* Stamina = GetStamina())
		{
			Stamina->SetPreviewCost(0.f);
		}
	}

	if (MovementMode == MOVE_None)
	{
		// Boarding the boat (or anything else that parks the character) drops held buttons.
		bSprintInput = false;
		bJumpInput = false;
		bJumpInputLastFrame = false;
		JumpBufferRemaining = 0.f;
	}
}

// ---------------------------------------------------------------------------------------------
// Climbing
// ---------------------------------------------------------------------------------------------

bool ULyrisCharacterMovementComponent::IsClimbableSurface(const FHitResult& Hit) const
{
	if (!Hit.bBlockingHit || Hit.bStartPenetrating)
	{
		return false;
	}

	const ULyrisMovementSettings& S = LyrisMovement::Settings();
	const AActor* HitActor = Hit.GetActor();
	const UPrimitiveComponent* HitComponent = Hit.GetComponent();

	// Never other characters or the boat (pawns), never loose physics props, never NoClimb.
	if (HitActor && (HitActor->IsA<APawn>() || HitActor->ActorHasTag(S.NoClimbTag)))
	{
		return false;
	}
	if (HitComponent && (HitComponent->ComponentHasTag(S.NoClimbTag) || HitComponent->IsSimulatingPhysics()))
	{
		return false;
	}

	// Steep enough to be a wall (not a walkable slope), not so overhanging it's a ceiling.
	const double NormalZ = Hit.ImpactNormal.Z;
	const float MaxNormalZ = FMath::Cos(FMath::DegreesToRadians(S.ClimbMinSurfaceAngle));
	const float MinNormalZ = FMath::Cos(FMath::DegreesToRadians(90.f + S.ClimbMaxOverhangAngle));
	return NormalZ <= MaxNormalZ && NormalZ >= MinNormalZ && NormalZ < GetWalkableFloorZ();
}

bool ULyrisCharacterMovementComponent::TraceClimbWall(const FVector& From, const FVector& Direction, float Length, FHitResult& OutHit) const
{
	const UWorld* World = GetWorld();
	if (!World || !UpdatedComponent)
	{
		return false;
	}

	FCollisionQueryParams Params(SCENE_QUERY_STAT(LyrisClimbTrace), false, GetCharacterOwner());
	FCollisionResponseParams ResponseParams;
	InitCollisionParams(Params, ResponseParams);

	const bool bHit = World->LineTraceSingleByChannel(OutHit, From, From + Direction * Length,
		UpdatedComponent->GetCollisionObjectType(), Params, ResponseParams);
	return bHit && IsClimbableSurface(OutHit);
}

FVector ULyrisCharacterMovementComponent::GetClimbNormalFlat() const
{
	const FVector Flat = LyrisMovement::Flat(ClimbNormal);
	return Flat.IsNearlyZero() ? -UpdatedComponent->GetForwardVector() : Flat;
}

FQuat ULyrisCharacterMovementComponent::GetClimbRotation() const
{
	return (-GetClimbNormalFlat()).ToOrientationQuat();
}

void ULyrisCharacterMovementComponent::TryGrabWall(float DeltaSeconds)
{
	if (!CharacterOwner || !UpdatedComponent || !(IsFalling() || IsMovingOnGround()))
	{
		GroundPushTime = 0.f;
		return;
	}

	const ULyrisMovementSettings& S = LyrisMovement::Settings();
	const FVector Input = GetInputVector();
	if (RegrabCooldown > 0.f || !HasBreathToClimb() || Input.Size2D() < LyrisMovement::InputDeadZone)
	{
		GroundPushTime = 0.f;
		return;
	}

	// No climb button: push into a climbable wall and you grab it.
	const FVector InputDir = LyrisMovement::Flat(Input);
	const float Radius = CharacterOwner->GetCapsuleComponent()->GetScaledCapsuleRadius();
	FHitResult WallHit;
	const bool bWall = TraceClimbWall(UpdatedComponent->GetComponentLocation(), InputDir, Radius + S.ClimbReach, WallHit)
		&& FVector::DotProduct(InputDir, -LyrisMovement::Flat(WallHit.ImpactNormal)) >= S.ClimbGrabInputThreshold;
	if (!bWall)
	{
		GroundPushTime = 0.f;
		return;
	}

	if (IsFalling())
	{
		StartClimbing(WallHit);
		return;
	}

	// On the ground, keep pushing for a moment so brushing past a wall doesn't stick you to it.
	GroundPushTime += DeltaSeconds;
	if (GroundPushTime >= S.GroundGrabDelay)
	{
		StartClimbing(WallHit);
	}
}

void ULyrisCharacterMovementComponent::StartClimbing(const FHitResult& WallHit)
{
	ClimbNormal = WallHit.ImpactNormal;
	Velocity = FVector::ZeroVector;
	LeapTimeRemaining = 0.f;
	GroundPushTime = 0.f;
	bMantling = false;
	SetMovementMode(MOVE_Custom, static_cast<uint8>(ELyrisMovementMode::Climbing));
}

void ULyrisCharacterMovementComponent::StopClimbing(EMovementMode NewMode)
{
	bMantling = false;
	LeapTimeRemaining = 0.f;
	SetMovementMode(NewMode);
}

void ULyrisCharacterMovementComponent::PhysCustom(float deltaTime, int32 Iterations)
{
	if (CustomMovementMode == static_cast<uint8>(ELyrisMovementMode::Climbing))
	{
		PhysClimbing(deltaTime, Iterations);
		return;
	}
	Super::PhysCustom(deltaTime, Iterations);
}

void ULyrisCharacterMovementComponent::PhysClimbing(float deltaTime, int32 Iterations)
{
	if (deltaTime < MIN_TICK_TIME || !CharacterOwner || !UpdatedComponent)
	{
		return;
	}

	if (bMantling)
	{
		PhysMantle(deltaTime, Iterations);
		return;
	}

	const ULyrisMovementSettings& S = LyrisMovement::Settings();
	const UCapsuleComponent* Capsule = CharacterOwner->GetCapsuleComponent();
	const float Radius = Capsule->GetScaledCapsuleRadius();

	// Out of Breath: you let go and slide off.
	const ULyrisStaminaComponent* Stamina = GetStamina();
	if (Stamina && Stamina->IsWinded())
	{
		const FVector Out = GetClimbNormalFlat();
		StopClimbing(MOVE_Falling);
		Velocity = Out * 50.f + FVector(0.f, 0.f, -100.f);
		RegrabCooldown = S.WindedRegrabDelay;
		StartNewPhysics(deltaTime, Iterations);
		return;
	}

	const FVector Normal = GetClimbNormalFlat();
	const FVector IntoWall = -Normal;
	FVector WallUp = FVector::VectorPlaneProject(FVector::UpVector, ClimbNormal).GetSafeNormal();
	if (WallUp.IsNearlyZero())
	{
		WallUp = FVector::UpVector;
	}
	const FVector WallRight = FVector::CrossProduct(Normal, FVector::UpVector).GetSafeNormal();

	// Stick in wall space: pushing toward the wall climbs up, pulling back climbs down.
	const FVector Input = GetInputVector();
	FVector2D Stick(FVector::DotProduct(Input, WallRight), FVector::DotProduct(Input, IntoWall));
	if (Stick.Size() < LyrisMovement::InputDeadZone)
	{
		Stick = FVector2D::ZeroVector;
	}
	else if (Stick.Size() > 1.f)
	{
		Stick.Normalize();
	}

	// Jump on a wall: a leap up, or a kick off if the stick points away from the wall.
	if (JumpBufferRemaining > 0.f && LeapTimeRemaining <= 0.f)
	{
		JumpBufferRemaining = 0.f;
		const FVector InputFlat = LyrisMovement::Flat(Input);
		const bool bKick = Input.Size2D() >= LyrisMovement::InputDeadZone
			&& FVector::DotProduct(InputFlat, Normal) >= S.WallKickInputThreshold;
		const float Cost = bKick ? S.WallKickBreath : S.ClimbLeapBreath;
		if (TrySpendBreath(Cost))
		{
			if (bKick)
			{
				StopClimbing(MOVE_Falling);
				Velocity = Normal * S.WallKickOutSpeed + FVector(0.f, 0.f, S.WallKickUpSpeed);
				RegrabCooldown = S.WallKickRegrabDelay;
				CoyoteRemaining = 0.f;
				bJumpCutAvailable = false;
				StartNewPhysics(deltaTime, Iterations);
				return;
			}
			LeapTimeRemaining = S.ClimbLeapDuration;
		}
	}

	// Let go at the bottom: pulling down with ground underfoot puts you back on your feet.
	if (Stick.Y < -LyrisMovement::InputDeadZone && LeapTimeRemaining <= 0.f)
	{
		FFindFloorResult Floor;
		FindFloor(UpdatedComponent->GetComponentLocation(), Floor, false);
		if (Floor.IsWalkableFloor() && Floor.GetDistanceToFloor() <= 15.f)
		{
			StopClimbing(MOVE_Walking);
			RegrabCooldown = 0.3f;
			StartNewPhysics(deltaTime, Iterations);
			return;
		}
	}

	FVector ClimbVelocity;
	if (LeapTimeRemaining > 0.f)
	{
		// The leap is already paid for; no drain while lunging.
		LeapTimeRemaining -= deltaTime;
		ClimbVelocity = WallUp * (S.ClimbLeapHeight / FMath::Max(S.ClimbLeapDuration, 0.05f));
	}
	else
	{
		ClimbVelocity = (WallRight * Stick.X + WallUp * Stick.Y) * S.ClimbSpeed;
		const bool bMoving = !Stick.IsZero();
		DrainBreath((bMoving ? S.ClimbBreathPerSecond : S.HangBreathPerSecond) * deltaTime);
	}

	// Move along the wall.
	const FVector OldLocation = UpdatedComponent->GetComponentLocation();
	const FQuat ClimbRotation = GetClimbRotation();
	const FVector Delta = ClimbVelocity * deltaTime;
	FHitResult Hit(1.f);
	SafeMoveUpdatedComponent(Delta, ClimbRotation, true, Hit);
	if (Hit.IsValidBlockingHit())
	{
		SlideAlongSurface(Delta, 1.f - Hit.Time, Hit.Normal, Hit, true);
	}

	// Stay on the wall: follow its normal (round towers, bumpy cliffs) and keep a small gap.
	const float WallTraceLength = Radius + S.ClimbWallGap + S.ClimbReach;
	FHitResult WallHit;
	if (TraceClimbWall(UpdatedComponent->GetComponentLocation(), IntoWall, WallTraceLength, WallHit))
	{
		ClimbNormal = WallHit.ImpactNormal;
		const FVector NewInto = -GetClimbNormalFlat();
		const float Correction = WallHit.Distance - (Radius + S.ClimbWallGap);
		if (FMath::Abs(Correction) > 0.5f)
		{
			FHitResult SnapHit;
			SafeMoveUpdatedComponent(NewInto * Correction, GetClimbRotation(), true, SnapHit);
		}
	}
	else if (FVector::DotProduct(Delta, WallUp) > 0.f && TryStartMantle())
	{
		// Over the top: the pull-up runs from next frame.
	}
	else
	{
		// Ran off the side of the wall, or the top has no room to stand: step back onto the wall.
		FHitResult BackHit;
		SafeMoveUpdatedComponent(OldLocation - UpdatedComponent->GetComponentLocation(), ClimbRotation, true, BackHit);
		LeapTimeRemaining = 0.f;
	}

	if (!bJustTeleported)
	{
		Velocity = (UpdatedComponent->GetComponentLocation() - OldLocation) / deltaTime;
	}
}

bool ULyrisCharacterMovementComponent::TryStartMantle()
{
	const UWorld* World = GetWorld();
	if (!World || !CharacterOwner || !UpdatedComponent)
	{
		return false;
	}

	const ULyrisMovementSettings& S = LyrisMovement::Settings();
	const UCapsuleComponent* Capsule = CharacterOwner->GetCapsuleComponent();
	const float Radius = Capsule->GetScaledCapsuleRadius();
	const float HalfHeight = Capsule->GetScaledCapsuleHalfHeight();
	const FVector Center = UpdatedComponent->GetComponentLocation();
	const FVector IntoWall = -GetClimbNormalFlat();

	// Look down onto the top of the wall, one capsule-width past its face.
	const FVector Ahead = Center + IntoWall * (Radius + S.ClimbWallGap + Radius + 4.f);
	const FVector TraceStart = Ahead + FVector(0.f, 0.f, HalfHeight);
	const FVector TraceEnd = Ahead - FVector(0.f, 0.f, HalfHeight);

	FCollisionQueryParams Params(SCENE_QUERY_STAT(LyrisMantleTrace), false, GetCharacterOwner());
	FCollisionResponseParams ResponseParams;
	InitCollisionParams(Params, ResponseParams);
	const ECollisionChannel Channel = UpdatedComponent->GetCollisionObjectType();

	FHitResult FloorHit;
	if (!World->LineTraceSingleByChannel(FloorHit, TraceStart, TraceEnd, Channel, Params, ResponseParams)
		|| FloorHit.bStartPenetrating
		|| FloorHit.ImpactNormal.Z < GetWalkableFloorZ())
	{
		return false;
	}

	// Make sure there is room to stand up there.
	const FVector Target(Ahead.X, Ahead.Y, FloorHit.ImpactPoint.Z + HalfHeight + 2.f);
	const FCollisionShape StandShape = FCollisionShape::MakeCapsule(FMath::Max(1.f, Radius - 1.f), FMath::Max(1.f, HalfHeight - 1.f));
	if (World->OverlapBlockingTestByChannel(Target, FQuat::Identity, Channel, StandShape, Params, ResponseParams))
	{
		return false;
	}

	// Free, and always finishes.
	bMantling = true;
	MantleElapsed = 0.f;
	MantleStart = Center;
	MantleTarget = Target;
	LeapTimeRemaining = 0.f;
	return true;
}

void ULyrisCharacterMovementComponent::PhysMantle(float deltaTime, int32 Iterations)
{
	const ULyrisMovementSettings& S = LyrisMovement::Settings();

	MantleElapsed += deltaTime;
	const float Alpha = FMath::Clamp(MantleElapsed / FMath::Max(S.MantleDuration, 0.05f), 0.f, 1.f);

	// Rise first, then step in over the edge.
	const float RiseAlpha = FMath::Clamp(Alpha / 0.5f, 0.f, 1.f);
	const float StepAlpha = FMath::Clamp((Alpha - 0.5f) / 0.5f, 0.f, 1.f);
	const FVector Desired(
		FMath::Lerp(MantleStart.X, MantleTarget.X, static_cast<double>(StepAlpha)),
		FMath::Lerp(MantleStart.Y, MantleTarget.Y, static_cast<double>(StepAlpha)),
		FMath::Lerp(MantleStart.Z, MantleTarget.Z, static_cast<double>(RiseAlpha)));

	// The target was checked for room in TryStartMantle, so the pull-up moves without sweeping.
	const FVector OldLocation = UpdatedComponent->GetComponentLocation();
	MoveUpdatedComponent(Desired - OldLocation, GetClimbRotation(), false);
	Velocity = (Desired - OldLocation) / deltaTime;

	if (Alpha >= 1.f)
	{
		Velocity = FVector::ZeroVector;
		StopClimbing(MOVE_Walking);
	}
}
