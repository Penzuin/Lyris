// Lyris appearance system: the local character save (Player lane, task T23). See the header.

#include "Player/Appearance/LyrisCharacterSaveGame.h"
#include "Kismet/GameplayStatics.h"

const TCHAR* const ULyrisCharacterSaveGame::SlotName = TEXT("LyrisCharacter_0");

ULyrisCharacterSaveGame* ULyrisCharacterSaveGame::LoadCharacter()
{
	if (!UGameplayStatics::DoesSaveGameExist(SlotName, UserIndex))
	{
		return nullptr;
	}
	return Cast<ULyrisCharacterSaveGame>(UGameplayStatics::LoadGameFromSlot(SlotName, UserIndex));
}

bool ULyrisCharacterSaveGame::SaveCharacter(const FLyrisCharacterProfile& InProfile)
{
	ULyrisCharacterSaveGame* Save = Cast<ULyrisCharacterSaveGame>(UGameplayStatics::CreateSaveGameObject(ULyrisCharacterSaveGame::StaticClass()));
	if (!Save)
	{
		return false;
	}
	Save->Profile = InProfile;
	return UGameplayStatics::SaveGameToSlot(Save, SlotName, UserIndex);
}

bool ULyrisCharacterSaveGame::HasSavedCharacter()
{
	return UGameplayStatics::DoesSaveGameExist(SlotName, UserIndex);
}
