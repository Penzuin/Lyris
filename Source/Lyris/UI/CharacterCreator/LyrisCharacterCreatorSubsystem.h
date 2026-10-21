// Lyris character creator: opens and closes the creator screen for a local player.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/LocalPlayerSubsystem.h"
#include "LyrisCharacterCreatorSubsystem.generated.h"

class ALyrisCreatorStage;
class APlayerController;
class SLyrisCharacterCreator;
class SWidget;

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnLyrisCreatorClosed);

/**
 * One per local player. Puts the character creator on screen over a ALyrisCreatorStage, switches input
 * to game-and-UI (so the stage can be dragged), and puts everything back on close.
 *
 * Test it in any level: play, open the console (`) and type `Lyris.OpenCreator`. If no stage is in the
 * level, one is spawned a few metres in front of the player. `Lyris.CloseCreator` closes it.
 */
UCLASS()
class ULyrisCharacterCreatorSubsystem : public ULocalPlayerSubsystem
{
	GENERATED_BODY()

public:
	/** Open the creator on Stage (or on a stage found or spawned near the player when Stage is null). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void OpenCreator(ALyrisCreatorStage* Stage);

	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void CloseCreator();

	UFUNCTION(BlueprintPure, Category = "Lyris|Creator")
	bool IsCreatorOpen() const { return CreatorWidget.IsValid(); }

	/** Fires after the creator closes (saved or cancelled). T26 hooks the dock arrival here. */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Creator")
	FOnLyrisCreatorClosed OnCreatorClosed;

	virtual void Deinitialize() override;

private:
	APlayerController* GetPlayerController() const;
	ALyrisCreatorStage* FindOrSpawnStage(APlayerController* PC);

	TSharedPtr<SLyrisCharacterCreator> CreatorWidget;
	TSharedPtr<SWidget> ViewportContent;

	UPROPERTY(Transient)
	TObjectPtr<ALyrisCreatorStage> ActiveStage;

	/** True when this subsystem spawned the stage (then it is destroyed on close). */
	bool bSpawnedStage = false;

	/** Player state to restore on close. */
	bool bPrevShowMouseCursor = false;
	bool bHidPawn = false;
};
