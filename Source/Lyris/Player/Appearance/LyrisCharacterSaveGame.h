// Lyris appearance system: the local character save (Player lane, task T23).
//
// The creator (T24) writes the finished profile here; ALyrisCharacter loads it on BeginPlay for the locally
// controlled player. Slot "LyrisCharacter_0", user index 0.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SaveGame.h"
#include "Player/Appearance/LyrisAppearanceTypes.h"
#include "LyrisCharacterSaveGame.generated.h"

UCLASS(BlueprintType)
class LYRIS_API ULyrisCharacterSaveGame : public USaveGame
{
	GENERATED_BODY()

public:
	/** The slot the creator writes and the character reads. */
	static const TCHAR* const SlotName;   // "LyrisCharacter_0"
	static constexpr int32 UserIndex = 0;

	/** Bumped when the save layout changes in a way that needs migrating. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, SaveGame, Category = "Lyris")
	int32 SaveVersion = 1;

	/** Everything the creator produced (look, path, backstory, lantern, name; faith stays None until a quest). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Lyris")
	FLyrisCharacterProfile Profile;

	/** Loads slot LyrisCharacter_0. Returns null if there is no save (or it is not ours). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	static ULyrisCharacterSaveGame* LoadCharacter();

	/** Writes Profile to slot LyrisCharacter_0. Returns true on success. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	static bool SaveCharacter(const FLyrisCharacterProfile& InProfile);

	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance")
	static bool HasSavedCharacter();

	/** SlotName as an FString, for Blueprints and UGameplayStatics calls. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance")
	static FString GetSlotName() { return FString(SlotName); }
};
