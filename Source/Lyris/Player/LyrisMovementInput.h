// Lyris player: the Sprint input, built in code because cloud agents can't author .uasset input
// actions. Hold Left Shift to sprint; click the left stick on a gamepad to toggle sprint (it stops
// when you let go of the stick or run out of Breath).
//
// If someone later makes IA_Sprint / IMC_Movement assets in the editor, set them on the character
// Blueprint (SprintAction, SprintToggleAction, MovementMappingContext) and these are skipped.

#pragma once

#include "CoreMinimal.h"

class APawn;
class UInputAction;
class UInputMappingContext;

struct LYRIS_API FLyrisMovementInput
{
	/** Priority the movement context is added at (above the template's IMC_Default at 0). */
	static constexpr int32 MappingPriority = 1;

	/** A boolean action for hold-to-sprint (Left Shift). */
	static UInputAction* CreateSprintAction(UObject* Outer);

	/** A boolean action for toggle sprint (gamepad left stick click). */
	static UInputAction* CreateSprintToggleAction(UObject* Outer);

	/** A mapping context with Left Shift -> SprintAction and Gamepad left stick click -> SprintToggleAction. */
	static UInputMappingContext* CreateMappingContext(UObject* Outer, const UInputAction* SprintAction, const UInputAction* SprintToggleAction);

	/** Adds the context to the pawn's local player, if it has one. Safe to call more than once. */
	static void AddMappingContext(const APawn* Pawn, const UInputMappingContext* Context);
};
