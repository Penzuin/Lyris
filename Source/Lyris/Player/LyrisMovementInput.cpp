// Lyris player: the Sprint input, built in code.

#include "Player/LyrisMovementInput.h"
#include "EnhancedInputSubsystems.h"
#include "Engine/LocalPlayer.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "InputAction.h"
#include "InputCoreTypes.h"
#include "InputMappingContext.h"

UInputAction* FLyrisMovementInput::CreateSprintAction(UObject* Outer)
{
	UInputAction* Action = NewObject<UInputAction>(Outer, TEXT("IA_Sprint_Runtime"));
	Action->ValueType = EInputActionValueType::Boolean;
	return Action;
}

UInputAction* FLyrisMovementInput::CreateSprintToggleAction(UObject* Outer)
{
	UInputAction* Action = NewObject<UInputAction>(Outer, TEXT("IA_SprintToggle_Runtime"));
	Action->ValueType = EInputActionValueType::Boolean;
	return Action;
}

UInputMappingContext* FLyrisMovementInput::CreateMappingContext(UObject* Outer, const UInputAction* SprintAction, const UInputAction* SprintToggleAction)
{
	UInputMappingContext* Context = NewObject<UInputMappingContext>(Outer, TEXT("IMC_Movement_Runtime"));
	if (SprintAction)
	{
		Context->MapKey(SprintAction, EKeys::LeftShift);
	}
	if (SprintToggleAction)
	{
		Context->MapKey(SprintToggleAction, EKeys::Gamepad_LeftThumbstick);
	}
	return Context;
}

void FLyrisMovementInput::AddMappingContext(const APawn* Pawn, const UInputMappingContext* Context)
{
	if (!Pawn || !Context)
	{
		return;
	}
	const APlayerController* PC = Cast<APlayerController>(Pawn->GetController());
	if (!PC || !PC->IsLocalController())
	{
		return;
	}
	if (UEnhancedInputLocalPlayerSubsystem* Subsystem = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
	{
		if (!Subsystem->HasMappingContext(Context))
		{
			Subsystem->AddMappingContext(Context, MappingPriority);
		}
	}
}
