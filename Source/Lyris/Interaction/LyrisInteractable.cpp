// Lyris interaction: anything in the world the player can use (a rock, a plot, a door, a lamp).

#include "LyrisInteractable.h"

// Default implementations so an actor only has to override what it needs.

bool ILyrisInteractable::CanInteract_Implementation(AActor* InteractingActor) const
{
	return true;
}

FText ILyrisInteractable::GetInteractPrompt_Implementation(AActor* InteractingActor) const
{
	return NSLOCTEXT("Lyris", "InteractDefault", "Interact");
}

void ILyrisInteractable::Interact_Implementation(AActor* InteractingActor)
{
}
