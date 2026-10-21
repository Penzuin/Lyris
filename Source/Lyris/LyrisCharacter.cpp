// Copyright Epic Games, Inc. All Rights Reserved.

#include "LyrisCharacter.h"
#include "Engine/LocalPlayer.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "GameFramework/Controller.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "InputActionValue.h"
#include "Lyris.h"
#include "Player/LyrisSwimComponent.h"
#include "Player/LyrisCharacterMovementComponent.h"
#include "Player/LyrisMovementInput.h"
#include "Player/LyrisStaminaComponent.h"
#include "Player/Appearance/LyrisAppearanceComponent.h"
#include "Player/Appearance/LyrisCharacterSaveGame.h"

ALyrisCharacter::ALyrisCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer.SetDefaultSubobjectClass<ULyrisCharacterMovementComponent>(ACharacter::CharacterMovementComponentName))
{
	// Ticks only to keep the gamepad sprint toggle in step (T32)
	PrimaryActorTick.bCanEverTick = true;

	// Set size for collision capsule
	GetCapsuleComponent()->InitCapsuleSize(42.f, 96.0f);
		
	// Don't rotate when the controller rotates. Let that just affect the camera.
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;

	// Configure character movement
	GetCharacterMovement()->bOrientRotationToMovement = true;
	GetCharacterMovement()->RotationRate = FRotator(0.0f, 500.0f, 0.0f);

	// Note: For faster iteration times these variables, and many more, can be tweaked in the Character Blueprint
	// instead of recompiling to adjust them
	// Walk speed, jump height and air control come from Project Settings > Game > Lyris Movement (T32)
	GetCharacterMovement()->MinAnalogWalkSpeed = 20.f;
	GetCharacterMovement()->BrakingDecelerationWalking = 2000.f;
	GetCharacterMovement()->BrakingDecelerationFalling = 1500.0f;

	// Create a camera boom (pulls in towards the player if there is a collision)
	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 400.0f;
	CameraBoom->bUsePawnControlRotation = true;

	// Create a follow camera
	FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
	FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	FollowCamera->bUsePawnControlRotation = false;

	// Swimming (T20): floats, rides the waves and climbs out; see ULyrisSwimComponent
	SwimComponent = CreateDefaultSubobject<ULyrisSwimComponent>(TEXT("SwimComponent"));

	// Breath (T32): sprinting and climbing draw from it; swimming never does
	Stamina = CreateDefaultSubobject<ULyrisStaminaComponent>(TEXT("Stamina"));

	// Appearance (T23): applies the creator look to the Mesh (bones now, morphs once T25 lands)
	AppearanceComponent = CreateDefaultSubobject<ULyrisAppearanceComponent>(TEXT("AppearanceComponent"));

	// Note: The skeletal mesh and anim blueprint references on the Mesh component (inherited from Character) 
	// are set in the derived blueprint asset named ThirdPersonCharacter (to avoid direct content references in C++)
}

void ALyrisCharacter::BeginPlay()
{
	Super::BeginPlay();
	TryApplySavedAppearance();
}

void ALyrisCharacter::NotifyControllerChanged()
{
	Super::NotifyControllerChanged();
	// Respawned or late-possessed pawns get their controller after BeginPlay (server: PossessedBy; owning
	// client: OnRep_Controller); both end up here, so the saved look is applied then.
	TryApplySavedAppearance();
}

void ALyrisCharacter::TryApplySavedAppearance()
{
	// Only the player sitting at this machine loads their saved look, and only once per pawn. The component
	// then replicates it to the server and other players. T26 also applies the look when the creator
	// finishes; this covers "play again with my saved character".
	if (bSavedAppearanceApplied || !AppearanceComponent || !HasActorBegunPlay() || !IsLocallyControlled())
	{
		return;
	}
	bSavedAppearanceApplied = true;
	if (const ULyrisCharacterSaveGame* Save = ULyrisCharacterSaveGame::LoadCharacter())
	{
		AppearanceComponent->SetAppearance(Save->Profile.Appearance);
	}
}

void ALyrisCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	// Set up action bindings
	if (UEnhancedInputComponent* EnhancedInputComponent = Cast<UEnhancedInputComponent>(PlayerInputComponent)) {
		
		// Jumping
		EnhancedInputComponent->BindAction(JumpAction, ETriggerEvent::Started, this, &ACharacter::Jump);
		EnhancedInputComponent->BindAction(JumpAction, ETriggerEvent::Completed, this, &ACharacter::StopJumping);

		// Moving
		EnhancedInputComponent->BindAction(MoveAction, ETriggerEvent::Triggered, this, &ALyrisCharacter::Move);
		EnhancedInputComponent->BindAction(MouseLookAction, ETriggerEvent::Triggered, this, &ALyrisCharacter::Look);

		// Looking
		EnhancedInputComponent->BindAction(LookAction, ETriggerEvent::Triggered, this, &ALyrisCharacter::Look);

		// Sprinting (T32): actions are made in code unless set on the Blueprint
		if (!SprintAction)
		{
			SprintAction = FLyrisMovementInput::CreateSprintAction(this);
		}
		if (!SprintToggleAction)
		{
			SprintToggleAction = FLyrisMovementInput::CreateSprintToggleAction(this);
		}
		if (!MovementMappingContext)
		{
			MovementMappingContext = FLyrisMovementInput::CreateMappingContext(this, SprintAction, SprintToggleAction);
		}
		EnhancedInputComponent->BindAction(SprintAction, ETriggerEvent::Started, this, &ALyrisCharacter::SprintStarted);
		EnhancedInputComponent->BindAction(SprintAction, ETriggerEvent::Completed, this, &ALyrisCharacter::SprintCompleted);
		EnhancedInputComponent->BindAction(SprintToggleAction, ETriggerEvent::Started, this, &ALyrisCharacter::SprintToggled);
		FLyrisMovementInput::AddMappingContext(this, MovementMappingContext);
	}
	else
	{
		UE_LOG(LogLyris, Error, TEXT("'%s' Failed to find an Enhanced Input component! This template is built to use the Enhanced Input system. If you intend to use the legacy system, then you will need to update this C++ file."), *GetNameSafe(this));
	}
}

void ALyrisCharacter::Move(const FInputActionValue& Value)
{
	// input is a Vector2D
	FVector2D MovementVector = Value.Get<FVector2D>();

	// route the input
	DoMove(MovementVector.X, MovementVector.Y);
}

void ALyrisCharacter::Look(const FInputActionValue& Value)
{
	// input is a Vector2D
	FVector2D LookAxisVector = Value.Get<FVector2D>();

	// route the input
	DoLook(LookAxisVector.X, LookAxisVector.Y);
}

void ALyrisCharacter::DoMove(float Right, float Forward)
{
	if (GetController() != nullptr)
	{
		// find out which way is forward
		const FRotator Rotation = GetController()->GetControlRotation();
		const FRotator YawRotation(0, Rotation.Yaw, 0);

		// get forward vector
		const FVector ForwardDirection = FRotationMatrix(YawRotation).GetUnitAxis(EAxis::X);

		// get right vector 
		const FVector RightDirection = FRotationMatrix(YawRotation).GetUnitAxis(EAxis::Y);

		// add movement 
		AddMovementInput(ForwardDirection, Forward);
		AddMovementInput(RightDirection, Right);
	}
}

void ALyrisCharacter::DoLook(float Yaw, float Pitch)
{
	if (GetController() != nullptr)
	{
		// add yaw and pitch input to controller
		AddControllerYawInput(Yaw);
		AddControllerPitchInput(Pitch);
	}
}

void ALyrisCharacter::DoJumpStart()
{
	// signal the character to jump
	Jump();
}

void ALyrisCharacter::DoJumpEnd()
{
	// signal the character to stop jumping
	StopJumping();
}

void ALyrisCharacter::Jump()
{
	// in the water, Jump is a kick up or a climb onto the dock
	if (SwimComponent && SwimComponent->HandleJumpPressed())
	{
		return;
	}
	Super::Jump();

	// On land and on walls the Lyris movement component handles the jump: buffer, coyote time,
	// variable height, climb leap and wall kick (T32)
	if (ULyrisCharacterMovementComponent* Move = GetLyrisMovement())
	{
		Move->SetJumpInput(true);
	}
}

// ---- T32: Breath, sprint and the Lyris movement component ----

ULyrisCharacterMovementComponent* ALyrisCharacter::GetLyrisMovement() const
{
	return Cast<ULyrisCharacterMovementComponent>(GetCharacterMovement());
}

void ALyrisCharacter::StopJumping()
{
	Super::StopJumping();
	if (ULyrisCharacterMovementComponent* Move = GetLyrisMovement())
	{
		Move->SetJumpInput(false);
	}
}

void ALyrisCharacter::PawnClientRestart()
{
	Super::PawnClientRestart();

	// Coming back from the boat clears the input stack, so add the sprint mapping again
	FLyrisMovementInput::AddMappingContext(this, MovementMappingContext);
}

void ALyrisCharacter::SprintStarted(const FInputActionValue& Value)
{
	if (ULyrisCharacterMovementComponent* Move = GetLyrisMovement())
	{
		Move->SetSprintInput(true);
	}
}

void ALyrisCharacter::SprintCompleted(const FInputActionValue& Value)
{
	if (ULyrisCharacterMovementComponent* Move = GetLyrisMovement())
	{
		Move->SetSprintInput(bSprintToggled);
	}
}

void ALyrisCharacter::SprintToggled(const FInputActionValue& Value)
{
	bSprintToggled = !bSprintToggled;
	if (ULyrisCharacterMovementComponent* Move = GetLyrisMovement())
	{
		Move->SetSprintInput(bSprintToggled);
	}
}

void ALyrisCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	// The gamepad toggle switches off when you stop moving or run out of Breath
	if (bSprintToggled)
	{
		ULyrisCharacterMovementComponent* Move = GetLyrisMovement();
		const bool bStill = Move && Move->GetCurrentAcceleration().IsNearlyZero();
		const bool bWinded = Stamina && Stamina->IsWinded();
		if (bStill || bWinded)
		{
			bSprintToggled = false;
			if (Move)
			{
				Move->SetSprintInput(false);
			}
		}
	}
}
