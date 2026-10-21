// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "LyrisGameMode.generated.h"

class APlayerController;

/**
 *  Lyris game mode.
 *
 *  New players start in the character creator (T26): a local player with no saved character
 *  (save slot "LyrisCharacter_0") gets the creator on their first frame. When it closes, their
 *  look is applied and they are moved to the arrival point (an actor tagged ArrivalTag, for
 *  example a PlayerStart on the dock), the "light your lantern on the dock" moment.
 *
 *  Console helpers for testing:
 *    Lyris.ForceCreator 1   always open the creator on start, even with a saved character
 *    Lyris.ResetCharacter   delete the saved character, so the next start is a new player
 */
UCLASS(abstract)
class ALyrisGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:

	/** Constructor */
	ALyrisGameMode();

	/** Open the character creator for local players who have no saved character yet. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Creator")
	bool bOpenCreatorForNewPlayers = true;

	/** Actor tag of the spot new players arrive at once the creator closes (e.g. a PlayerStart on
	 *  the dock). If no actor has this tag, the player stays where the game started them. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Creator")
	FName ArrivalTag = TEXT("DockArrival");

	/** Actor tag that picks which ALyrisCreatorStage to use when a level has several (the dusk
	 *  deck). With no tagged stage the first stage found is used, and with none at all the
	 *  creator spawns one in front of the player. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Creator")
	FName CreatorStageTag = TEXT("VoyageDeck");

protected:

	virtual void HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer) override;

private:

	/** Opens the creator for this player (run one tick after they start, once pawn and camera exist). */
	void OpenCreatorFor(TWeakObjectPtr<APlayerController> PlayerController);

	/** The creator closed: apply the saved look and move the player to the arrival point. */
	UFUNCTION()
	void HandleCreatorClosed();

	/** The player whose creator is open. Local split-screen would need one per player; Lyris has
	 *  one local player, and remote players run the creator on their own machine. */
	TWeakObjectPtr<APlayerController> CreatorPlayer;
};
