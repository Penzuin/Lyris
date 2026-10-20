// Lyris interaction: anything in the world the player can use (a rock, a plot, a door, a lamp).

#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "LyrisInteractable.generated.h"

UINTERFACE(MinimalAPI, BlueprintType)
class ULyrisInteractable : public UInterface
{
	GENERATED_BODY()
};

/**
 * Implement on any actor (in C++ or in a Blueprint's Class Settings) to make it usable.
 * ULyrisInteractionComponent on the player finds the best interactable in front of it,
 * shows GetInteractPrompt and calls Interact when the player presses the Interact input.
 *
 * Always call these through the generated Execute_ wrappers so Blueprint implementations work:
 *   ILyrisInteractable::Execute_CanInteract(Actor, Player)
 *
 * The parameter is called InteractingActor rather than Instigator because AActor already
 * has an Instigator member and UHT rejects parameters that shadow it.
 */
class LYRIS_API ILyrisInteractable
{
	GENERATED_BODY()

public:
	/** Can InteractingActor use this right now? Return false to hide the prompt entirely. */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Lyris|Interaction")
	bool CanInteract(AActor* InteractingActor) const;

	/** Short verb phrase for the HUD, e.g. "Mine Copper Vein" or "Water Moonbell". */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Lyris|Interaction")
	FText GetInteractPrompt(AActor* InteractingActor) const;

	/** Do the thing. Only called after CanInteract returned true. */
	UFUNCTION(BlueprintNativeEvent, BlueprintCallable, Category = "Lyris|Interaction")
	void Interact(AActor* InteractingActor);

	// Defaults (in LyrisInteractable.cpp) so an implementer only overrides what it needs.
	virtual bool CanInteract_Implementation(AActor* InteractingActor) const;
	virtual FText GetInteractPrompt_Implementation(AActor* InteractingActor) const;
	virtual void Interact_Implementation(AActor* InteractingActor);
};
