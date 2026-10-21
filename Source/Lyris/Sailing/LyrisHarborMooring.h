// Lyris sailing (T21): a spot in a lit harbor where a swamped boat is brought home.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "LyrisHarborMooring.generated.h"

class UArrowComponent;

/**
 * Place one of these on the water beside each harbor dock, facing the way a boat should lie.
 *
 * When a boat swamps (ULyrisHullComponent), it is returned, emptied and patched, to the nearest enabled
 * mooring whose water is lit (calm). With no mooring placed, the boat goes back to where it started the
 * level. Nothing here ticks; it is only a marked point.
 */
UCLASS()
class LYRIS_API ALyrisHarborMooring : public AActor
{
	GENERATED_BODY()

public:
	ALyrisHarborMooring();

	/** Shown in the "Safe in ..." message, e.g. "Moonharbor". */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Harbor")
	FText HarborName;

	/** Turn off to keep boats from being sent here (e.g. a harbor not yet found). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Harbor")
	bool bEnabled = true;

private:
#if WITH_EDITORONLY_DATA
	/** Which way the boat's bow will point. Editor only. */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UArrowComponent> Arrow;
#endif
};
