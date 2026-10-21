// Lyris character creator: subsystem that shows the screen, plus the Lyris.OpenCreator console command.

#include "UI/CharacterCreator/LyrisCharacterCreatorSubsystem.h"

#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "TimerManager.h"

#include "UI/CharacterCreator/LyrisCreatorStage.h"
#include "UI/CharacterCreator/SLyrisCharacterCreator.h"

DEFINE_LOG_CATEGORY_STATIC(LogLyrisCreator, Log, All);

namespace
{
	/** Draw the creator above the HUD and most other viewport widgets. */
	constexpr int32 CreatorZOrder = 50;

	/** Where a test stage is spawned: this far in front of the player, cm. */
	constexpr float TestStageDistance = 400.f;

	ULyrisCharacterCreatorSubsystem* FindSubsystem(UWorld* World)
	{
		if (!World)
		{
			return nullptr;
		}
		APlayerController* PC = World->GetFirstPlayerController();
		ULocalPlayer* LocalPlayer = PC ? PC->GetLocalPlayer() : nullptr;
		return LocalPlayer ? LocalPlayer->GetSubsystem<ULyrisCharacterCreatorSubsystem>() : nullptr;
	}

	// Console: Lyris.OpenCreator / Lyris.CloseCreator (works in any level while playing).
	FAutoConsoleCommandWithWorldAndArgs GOpenCreatorCommand(
		TEXT("Lyris.OpenCreator"),
		TEXT("Open the Lyris character creator. Uses a LyrisCreatorStage in the level, or spawns one in front of the player."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULyrisCharacterCreatorSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->OpenCreator(nullptr);
			}
			else
			{
				UE_LOG(LogLyrisCreator, Warning, TEXT("Lyris.OpenCreator: no local player (are you playing?)."));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs GCloseCreatorCommand(
		TEXT("Lyris.CloseCreator"),
		TEXT("Close the Lyris character creator without saving."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (ULyrisCharacterCreatorSubsystem* Subsystem = FindSubsystem(World))
			{
				Subsystem->CloseCreator();
			}
		}));
}

APlayerController* ULyrisCharacterCreatorSubsystem::GetPlayerController() const
{
	const ULocalPlayer* LocalPlayer = GetLocalPlayer();
	UWorld* World = LocalPlayer ? LocalPlayer->GetWorld() : nullptr;
	return (LocalPlayer && World) ? LocalPlayer->GetPlayerController(World) : nullptr;
}

ALyrisCreatorStage* ULyrisCharacterCreatorSubsystem::FindOrSpawnStage(APlayerController* PC)
{
	UWorld* World = PC ? PC->GetWorld() : nullptr;
	if (!World)
	{
		return nullptr;
	}

	// A stage placed in the level (the dusk deck) wins.
	for (TActorIterator<ALyrisCreatorStage> It(World); It; ++It)
	{
		bSpawnedStage = false;
		return *It;
	}

	// Otherwise spawn a test stage in front of the player, facing back toward them.
	FVector Location = FVector::ZeroVector;
	FRotator Facing = FRotator::ZeroRotator;
	if (const APawn* Pawn = PC->GetPawn())
	{
		const FRotator Yaw(0.f, Pawn->GetActorRotation().Yaw, 0.f);
		Location = Pawn->GetActorLocation() + Yaw.Vector() * TestStageDistance;
		Facing = FRotator(0.f, Yaw.Yaw + 180.f, 0.f);
	}
	else
	{
		FRotator ViewRotation;
		PC->GetPlayerViewPoint(Location, ViewRotation);
		const FRotator Yaw(0.f, ViewRotation.Yaw, 0.f);
		Location += Yaw.Vector() * TestStageDistance;
		Facing = FRotator(0.f, Yaw.Yaw + 180.f, 0.f);
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ALyrisCreatorStage* Stage = World->SpawnActor<ALyrisCreatorStage>(ALyrisCreatorStage::StaticClass(), Location, Facing, Params);
	bSpawnedStage = Stage != nullptr;
	return Stage;
}

void ULyrisCharacterCreatorSubsystem::OpenCreator(ALyrisCreatorStage* Stage)
{
	if (IsCreatorOpen())
	{
		return;
	}
	APlayerController* PC = GetPlayerController();
	if (!PC || !GEngine || !GEngine->GameViewport)
	{
		UE_LOG(LogLyrisCreator, Warning, TEXT("OpenCreator: no player controller or game viewport."));
		return;
	}

	bSpawnedStage = false;
	ActiveStage = Stage ? Stage : FindOrSpawnStage(PC);
	if (!ActiveStage)
	{
		UE_LOG(LogLyrisCreator, Warning, TEXT("OpenCreator: could not find or spawn a creator stage."));
		return;
	}

	// The player's own pawn would stand in the shot; hide it while the creator is open.
	if (APawn* Pawn = PC->GetPawn())
	{
		if (!Pawn->IsHidden())
		{
			Pawn->SetActorHiddenInGame(true);
			bHidPawn = true;
		}
	}

	ActiveStage->BeginCreator(PC);

	TWeakObjectPtr<ULyrisCharacterCreatorSubsystem> WeakThis(this);
	CreatorWidget = SNew(SLyrisCharacterCreator)
		.Stage(ActiveStage.Get())
		.PlayerController(PC)
		.OnRequestClose(FSimpleDelegate::CreateLambda([WeakThis]()
		{
			// Close on the next tick: the button that asked is still inside the widget being removed.
			if (WeakThis.IsValid() && GEngine && GEngine->GameViewport)
			{
				if (UWorld* World = WeakThis->GetLocalPlayer() ? WeakThis->GetLocalPlayer()->GetWorld() : nullptr)
				{
					World->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(WeakThis.Get(), [WeakThis]()
					{
						if (WeakThis.IsValid())
						{
							WeakThis->CloseCreator();
						}
					}));
				}
			}
		}));
	ViewportContent = CreatorWidget;
	GEngine->GameViewport->AddViewportWidgetContent(ViewportContent.ToSharedRef(), CreatorZOrder);

	// Game and UI: Slate gets the mouse for panels and drags, the game keeps running behind.
	bPrevShowMouseCursor = PC->bShowMouseCursor;
	FInputModeGameAndUI InputMode;
	InputMode.SetWidgetToFocus(CreatorWidget);
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	InputMode.SetHideCursorDuringCapture(false);
	PC->SetInputMode(InputMode);
	PC->SetShowMouseCursor(true);
	PC->SetIgnoreMoveInput(true);
	PC->SetIgnoreLookInput(true);

	FSlateApplication::Get().SetKeyboardFocus(CreatorWidget, EFocusCause::SetDirectly);
}

void ULyrisCharacterCreatorSubsystem::CloseCreator()
{
	if (!IsCreatorOpen())
	{
		return;
	}

	if (GEngine && GEngine->GameViewport && ViewportContent.IsValid())
	{
		GEngine->GameViewport->RemoveViewportWidgetContent(ViewportContent.ToSharedRef());
	}
	ViewportContent.Reset();
	CreatorWidget.Reset();

	APlayerController* PC = GetPlayerController();
	if (ActiveStage)
	{
		ActiveStage->EndCreator();
		if (bSpawnedStage)
		{
			ActiveStage->Destroy();
		}
	}
	ActiveStage = nullptr;
	bSpawnedStage = false;

	if (PC)
	{
		if (bHidPawn && PC->GetPawn())
		{
			PC->GetPawn()->SetActorHiddenInGame(false);
		}
		PC->SetInputMode(FInputModeGameOnly());
		PC->SetShowMouseCursor(bPrevShowMouseCursor);
		// SetIgnore*Input(true) counts up; one reset each puts them back.
		PC->SetIgnoreMoveInput(false);
		PC->SetIgnoreLookInput(false);
	}
	bHidPawn = false;

	OnCreatorClosed.Broadcast();
}

void ULyrisCharacterCreatorSubsystem::Deinitialize()
{
	CloseCreator();
	Super::Deinitialize();
}
