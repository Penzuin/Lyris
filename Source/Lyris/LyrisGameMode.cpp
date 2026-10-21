// Copyright Epic Games, Inc. All Rights Reserved.

#include "LyrisGameMode.h"

#include "EngineUtils.h"
#include "Engine/LocalPlayer.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "TimerManager.h"

#include "Player/Appearance/LyrisAppearanceComponent.h"
#include "Player/Appearance/LyrisCharacterSaveGame.h"
#include "UI/CharacterCreator/LyrisCharacterCreatorSubsystem.h"
#include "UI/CharacterCreator/LyrisCreatorStage.h"

namespace LyrisGameModePrivate
{
	/** The save slot the creator writes and the character reads (see ULyrisCharacterSaveGame). */
	static const TCHAR* CharacterSlot = TEXT("LyrisCharacter_0");

	static TAutoConsoleVariable<int32> CVarForceCreator(
		TEXT("Lyris.ForceCreator"),
		0,
		TEXT("1 = always open the character creator when play starts, even with a saved character."),
		ECVF_Default);

	static FAutoConsoleCommand CmdResetCharacter(
		TEXT("Lyris.ResetCharacter"),
		TEXT("Delete the saved character so the next start opens the character creator."),
		FConsoleCommandDelegate::CreateLambda([]()
		{
			if (UGameplayStatics::DoesSaveGameExist(CharacterSlot, 0))
			{
				UGameplayStatics::DeleteGameInSlot(CharacterSlot, 0);
			}
		}));
}

ALyrisGameMode::ALyrisGameMode()
{
}

void ALyrisGameMode::HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer)
{
	Super::HandleStartingNewPlayer_Implementation(NewPlayer);

	// Only players on this machine get the creator here. A remote client opens its own creator
	// on its own machine (Multiplayer lane, later).
	if (!NewPlayer || !NewPlayer->IsLocalController())
	{
		return;
	}

	const bool bForce = LyrisGameModePrivate::CVarForceCreator.GetValueOnGameThread() != 0;
	const bool bHasCharacter = UGameplayStatics::DoesSaveGameExist(LyrisGameModePrivate::CharacterSlot, 0);
	if (!bForce && (!bOpenCreatorForNewPlayers || bHasCharacter))
	{
		return;
	}

	// Wait one tick so the pawn is possessed and the camera manager is running before the
	// creator stage takes over the view.
	GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateUObject(
		this, &ALyrisGameMode::OpenCreatorFor, TWeakObjectPtr<APlayerController>(NewPlayer)));
}

void ALyrisGameMode::OpenCreatorFor(TWeakObjectPtr<APlayerController> PlayerController)
{
	APlayerController* PC = PlayerController.Get();
	ULocalPlayer* LocalPlayer = PC ? PC->GetLocalPlayer() : nullptr;
	ULyrisCharacterCreatorSubsystem* Creator = LocalPlayer ? LocalPlayer->GetSubsystem<ULyrisCharacterCreatorSubsystem>() : nullptr;
	if (!Creator || Creator->IsCreatorOpen())
	{
		return;
	}

	// Prefer the stage tagged as the voyage deck, then any stage; with none, the creator spawns one.
	ALyrisCreatorStage* Stage = nullptr;
	for (TActorIterator<ALyrisCreatorStage> It(GetWorld()); It; ++It)
	{
		if (!Stage || It->ActorHasTag(CreatorStageTag))
		{
			Stage = *It;
		}
		if (Stage && Stage->ActorHasTag(CreatorStageTag))
		{
			break;
		}
	}

	CreatorPlayer = PC;
	Creator->OnCreatorClosed.AddUniqueDynamic(this, &ALyrisGameMode::HandleCreatorClosed);
	Creator->OpenCreator(Stage);
}

void ALyrisGameMode::HandleCreatorClosed()
{
	APlayerController* PC = CreatorPlayer.Get();
	CreatorPlayer.Reset();
	if (!PC)
	{
		return;
	}

	if (ULocalPlayer* LocalPlayer = PC->GetLocalPlayer())
	{
		if (ULyrisCharacterCreatorSubsystem* Creator = LocalPlayer->GetSubsystem<ULyrisCharacterCreatorSubsystem>())
		{
			Creator->OnCreatorClosed.RemoveDynamic(this, &ALyrisGameMode::HandleCreatorClosed);
		}
	}

	APawn* Pawn = PC->GetPawn();
	if (!Pawn)
	{
		return;
	}

	// Apply the look the creator just saved. The character also loads it on BeginPlay, but that
	// already ran before the creator opened. If the player closed without saving, there is no
	// save and they keep the default look; the creator opens again next time.
	if (UGameplayStatics::DoesSaveGameExist(LyrisGameModePrivate::CharacterSlot, 0))
	{
		if (const ULyrisCharacterSaveGame* Save = Cast<ULyrisCharacterSaveGame>(
				UGameplayStatics::LoadGameFromSlot(LyrisGameModePrivate::CharacterSlot, 0)))
		{
			if (ULyrisAppearanceComponent* Appearance = Pawn->FindComponentByClass<ULyrisAppearanceComponent>())
			{
				Appearance->SetAppearance(Save->Profile.Appearance);
			}
		}
	}

	// Arrive on the dock.
	if (ArrivalTag.IsNone())
	{
		return;
	}
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(ArrivalTag))
		{
			const FRotator Facing(0.f, It->GetActorRotation().Yaw, 0.f);
			Pawn->TeleportTo(It->GetActorLocation(), Facing);
			PC->SetControlRotation(Facing);
			break;
		}
	}
}
