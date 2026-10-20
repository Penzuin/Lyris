// Lyris interaction: finds the best thing to use in front of the player and uses it.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "LyrisInteractionComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FLyrisInteractionTargetChanged, AActor*, NewTarget, FText, Prompt);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FLyrisInteracted, AActor*, Target);

/**
 * Put this on the player character (Player lane, T14) and bind the Interact input to TryInteract().
 *
 * A few times a second it looks for actors implementing ILyrisInteractable within Range of
 * the owner, inside a cone in front of the view direction, that report CanInteract == true.
 * The closest, most centred one wins. When the target (or its prompt) changes, OnTargetChanged
 * fires so the HUD (UI lane, T16) can show or hide the prompt.
 *
 * Multiplayer later: the scan is purely local and cosmetic. TryInteract should become a
 * Server RPC that re-validates the target; nothing here stores state that would need replicating.
 */
UCLASS(ClassGroup = (Lyris), meta = (BlueprintSpawnableComponent))
class LYRIS_API ULyrisInteractionComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	ULyrisInteractionComponent();

	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** How far from the owner things can be used, in cm. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Interaction", meta = (ClampMin = "50"))
	float Range = 250.f;

	/** Half-angle of the cone in front of the view direction, in degrees. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Interaction", meta = (ClampMin = "5", ClampMax = "180"))
	float MaxAngleDegrees = 60.f;

	/** Seconds between scans. The scan is cheap but there's no need to run it every frame. */
	UPROPERTY(EditAnywhere, Category = "Lyris|Interaction", meta = (ClampMin = "0"))
	float ScanInterval = 0.1f;

	/** Ignore targets hidden behind walls (a visibility trace from the eyes to the target). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Interaction")
	bool bRequireLineOfSight = true;

	/** How far in front of the owner GetAimLocation points, in cm (about one soil cell ahead). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Interaction", meta = (ClampMin = "0"))
	float AimDistance = 110.f;

	/**
	 * The ground point the player is facing, AimDistance ahead along the view direction.
	 * Targets that cover an area (a farm plot) use it to pick which cell is meant.
	 */
	UFUNCTION(BlueprintPure, Category = "Lyris|Interaction")
	FVector GetAimLocation() const;

	/** Turn scanning off (e.g. while sailing or in a menu). Clears the current target. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Interaction")
	void SetScanningEnabled(bool bEnabled);

	/** Uses the current target if it still allows it. Returns true if something was used. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Interaction")
	bool TryInteract();

	/** Re-run the scan now, e.g. right after an interaction changed the target's state. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Interaction")
	void RefreshTarget();

	UFUNCTION(BlueprintPure, Category = "Lyris|Interaction")
	AActor* GetCurrentTarget() const { return CurrentTarget.Get(); }

	UFUNCTION(BlueprintPure, Category = "Lyris|Interaction")
	FText GetCurrentPrompt() const { return CurrentPrompt; }

	UFUNCTION(BlueprintPure, Category = "Lyris|Interaction")
	bool HasTarget() const { return CurrentTarget.IsValid(); }

	/** Fires when the target changes or its prompt text changes. NewTarget is null when nothing is in reach. */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Interaction")
	FLyrisInteractionTargetChanged OnTargetChanged;

	/** Fires after a successful TryInteract (for sounds, animations, journal hooks). */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Interaction")
	FLyrisInteracted OnInteracted;

protected:
	/** Where the player is looking from and toward. Uses the controller's view if there is one. */
	void GetViewPoint(FVector& OutLocation, FVector& OutDirection) const;

	/** Returns the best usable actor in reach, or null. */
	AActor* FindBestTarget() const;

	void SetTarget(AActor* NewTarget);

private:
	TWeakObjectPtr<AActor> CurrentTarget;
	FText CurrentPrompt;
	bool bScanningEnabled = true;
};
