// Lyris UI: hotbar, satchel screen and pickup notes for the local player's inventory (T16).

#include "UI/LyrisInventoryUISubsystem.h"

#include "UI/SLyrisInventoryView.h"
#include "Interaction/LyrisInteractionComponent.h"
#include "Items/LyrisInventoryComponent.h"
#include "Items/LyrisItemDefinition.h"
#include "Items/LyrisItemRegistry.h"

#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "ImageUtils.h"
#include "InputCoreTypes.h"
#include "Misc/Paths.h"
#include "Styling/SlateBrush.h"
#include "Widgets/SWeakWidget.h"

namespace LyrisInventoryUI
{
	/** Above the Breath ring (-5), below menus. */
	static constexpr int32 ZOrder = 8;
	static constexpr int32 MaxHotbar = 9;
	static const TCHAR* IconFolder = TEXT("Art/Icons");

	static FString KindText(const ULyrisItemDefinition* Def)
	{
		if (!Def)
		{
			return FString();
		}
		const UEnum* Enum = StaticEnum<ELyrisItemCategory>();
		FString Kind = Enum ? Enum->GetDisplayNameTextByValue(static_cast<int64>(Def->Category)).ToString() : FString();
		if (Def->IsTool())
		{
			Kind += FString(TEXT("  \u00B7  ")) + FName::NameToDisplayString(Def->ToolType.ToString(), false);
		}
		return Kind;
	}
}

void ULyrisInventoryUISubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	bActive = true;
}

void ULyrisInventoryUISubsystem::Deinitialize()
{
	bActive = false;
	Detach();
	View.Reset();
	IconBrushes.Empty();
	IconTextures.Empty();
	Super::Deinitialize();
}

ETickableTickType ULyrisInventoryUISubsystem::GetTickableTickType() const
{
	return IsTemplate() ? ETickableTickType::Never : ETickableTickType::Conditional;
}

bool ULyrisInventoryUISubsystem::IsTickable() const
{
	return bActive && !IsTemplate() && GetLocalPlayer() != nullptr;
}

TStatId ULyrisInventoryUISubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(ULyrisInventoryUISubsystem, STATGROUP_Tickables);
}

UWorld* ULyrisInventoryUISubsystem::GetTickableGameObjectWorld() const
{
	const ULocalPlayer* LocalPlayer = GetLocalPlayer();
	return LocalPlayer ? LocalPlayer->GetWorld() : nullptr;
}

void ULyrisInventoryUISubsystem::Tick(float DeltaTime)
{
	ULocalPlayer* LocalPlayer = GetLocalPlayer();
	UWorld* World = LocalPlayer ? LocalPlayer->GetWorld() : nullptr;
	APlayerController* PC = (LocalPlayer && World) ? LocalPlayer->GetPlayerController(World) : nullptr;
	UGameViewportClient* Viewport = World ? World->GetGameViewport() : nullptr;
	if (!PC || !Viewport || !World->IsGameWorld())
	{
		Detach();
		return;
	}

	// Only while on foot: aboard the boat the pawn is the boat, which has no bag.
	ULyrisInventoryComponent* Inventory = PC->GetPawn() ? PC->GetPawn()->FindComponentByClass<ULyrisInventoryComponent>() : nullptr;
	if (!Inventory)
	{
		Detach();
		return;
	}
	if (Inventory != AttachedInventory.Get() || Viewport != AttachedViewport.Get() || !AddedWidget.IsValid())
	{
		Detach();
		Attach(Inventory, Viewport);
	}
	HandleKeys(PC);

	// The interaction prompt (T10) above the hotbar. F is the playtest key until T14 adds an
	// input action (the boat uses E).
	const ULyrisInteractionComponent* Interaction = PC->GetPawn()->FindComponentByClass<ULyrisInteractionComponent>();
	const FString PromptText = (Interaction && Interaction->HasTarget()) ? Interaction->GetCurrentPrompt().ToString() : FString();
	if (View.IsValid())
	{
		View->SetPrompt(PromptText, TEXT("F"));
	}
}

void ULyrisInventoryUISubsystem::Attach(ULyrisInventoryComponent* Inventory, UGameViewportClient* Viewport)
{
	ULocalPlayer* LocalPlayer = GetLocalPlayer();
	if (!Inventory || !Viewport || !LocalPlayer)
	{
		return;
	}
	if (!View.IsValid())
	{
		View = SNew(SLyrisInventoryView);
		TWeakObjectPtr<ULyrisInventoryUISubsystem> WeakThis(this);
		View->OnSlotClicked = [WeakThis](int32 SlotIndex)
		{
			if (WeakThis.IsValid())
			{
				WeakThis->HandleSlotClicked(SlotIndex);
			}
		};
		View->OnMoveRequested = [WeakThis](int32 From, int32 To)
		{
			if (WeakThis.IsValid())
			{
				WeakThis->HandleMoveRequested(From, To);
			}
		};
		View->OnCloseRequested = [WeakThis]()
		{
			if (WeakThis.IsValid())
			{
				WeakThis->SetSatchelOpen(false);
			}
		};
	}
	TSharedRef<SWidget> Wrapper = SNew(SWeakWidget).PossiblyNullContent(View);
	Viewport->AddViewportWidgetForPlayer(LocalPlayer, Wrapper, LyrisInventoryUI::ZOrder);
	AddedWidget = Wrapper;
	AttachedViewport = Viewport;
	AttachedInventory = Inventory;
	Inventory->OnInventoryChanged.AddUniqueDynamic(this, &ULyrisInventoryUISubsystem::HandleInventoryChanged);
	bHaveCounts = false;
	Refresh();
}

void ULyrisInventoryUISubsystem::Detach()
{
	if (View.IsValid() && View->IsOpen())
	{
		SetSatchelOpen(false);
	}
	if (ULyrisInventoryComponent* Inventory = AttachedInventory.Get())
	{
		Inventory->OnInventoryChanged.RemoveDynamic(this, &ULyrisInventoryUISubsystem::HandleInventoryChanged);
	}
	UGameViewportClient* Viewport = AttachedViewport.Get();
	ULocalPlayer* LocalPlayer = GetLocalPlayer();
	if (TSharedPtr<SWidget> Added = AddedWidget.Pin(); Added.IsValid() && Viewport && LocalPlayer)
	{
		Viewport->RemoveViewportWidgetForPlayer(LocalPlayer, Added.ToSharedRef());
	}
	AddedWidget.Reset();
	AttachedViewport.Reset();
	AttachedInventory.Reset();
}

void ULyrisInventoryUISubsystem::HandleInventoryChanged()
{
	Refresh();
}

const FSlateBrush* ULyrisInventoryUISubsystem::GetIconBrush(FName ItemId)
{
	if (ItemId.IsNone() || MissingIcons.Contains(ItemId))
	{
		return nullptr;
	}
	if (const TSharedPtr<FSlateBrush>* Found = IconBrushes.Find(ItemId))
	{
		return Found->Get();
	}

	UTexture2D* Texture = nullptr;
	const ULyrisItemDefinition* Def = ULyrisItemRegistry::FindItem(GetLocalPlayer(), ItemId);
	if (Def && !Def->Icon.IsNull())
	{
		Texture = Def->Icon.LoadSynchronous();
	}
	if (!Texture)
	{
		const FString Path = FPaths::Combine(FPaths::ProjectDir(), LyrisInventoryUI::IconFolder, ItemId.ToString() + TEXT(".png"));
		if (FPaths::FileExists(Path))
		{
			Texture = FImageUtils::ImportFileAsTexture2D(Path);
		}
	}
	if (!Texture)
	{
		MissingIcons.Add(ItemId);
		return nullptr;
	}
	IconTextures.Add(ItemId, Texture);
	TSharedPtr<FSlateBrush> Brush = MakeShared<FSlateBrush>();
	Brush->SetResourceObject(Texture);
	Brush->ImageSize = FVector2f(128.f, 128.f);
	Brush->DrawAs = ESlateBrushDrawType::Image;
	IconBrushes.Add(ItemId, Brush);
	return Brush.Get();
}

void ULyrisInventoryUISubsystem::Refresh()
{
	ULyrisInventoryComponent* Inventory = AttachedInventory.Get();
	if (!Inventory || !View.IsValid())
	{
		return;
	}
	const TArray<FLyrisInventorySlot> InvSlots = Inventory->GetSlots();
	TArray<FLyrisSlotView> Views;
	Views.SetNum(InvSlots.Num());
	TMap<FName, int32> Counts;
	TMap<FName, FString> Names;
	for (int32 i = 0; i < InvSlots.Num(); ++i)
	{
		const FLyrisInventorySlot& Slot = InvSlots[i];
		FLyrisSlotView& V = Views[i];
		if (Slot.IsEmpty())
		{
			continue;
		}
		const ULyrisItemDefinition* Def = Slot.Definition ? Slot.Definition.Get() : ULyrisItemRegistry::FindItem(GetLocalPlayer(), Slot.ItemId);
		V.bEmpty = false;
		V.ItemId = Slot.ItemId;
		V.Name = Def ? Def->DisplayName.ToString() : Slot.ItemId.ToString();
		V.Description = Def ? Def->Description.ToString() : FString();
		V.Kind = LyrisInventoryUI::KindText(Def);
		V.Quality = static_cast<uint8>(Slot.Quality);
		V.Count = Slot.Count;
		V.MaxStack = Def ? FMath::Max(1, Def->MaxStack) : 1;
		V.Icon = GetIconBrush(Slot.ItemId);
		Counts.FindOrAdd(Slot.ItemId) += Slot.Count;
		Names.Add(Slot.ItemId, V.Name);
	}

	// "+3 Stone" notes for anything that just arrived.
	if (bHaveCounts)
	{
		for (const TPair<FName, int32>& Pair : Counts)
		{
			const int32 Before = LastCounts.FindRef(Pair.Key);
			if (Pair.Value > Before)
			{
				View->AddToast(FString::Printf(TEXT("+%d  %s"), Pair.Value - Before, *Names.FindRef(Pair.Key)), GetIconBrush(Pair.Key));
			}
		}
	}
	LastCounts = MoveTemp(Counts);
	bHaveCounts = true;

	const int32 Active = Inventory->GetActiveSlot();
	View->SetSlots(Views, Active, FMath::Min(LyrisInventoryUI::MaxHotbar, InvSlots.Num()));
	if (Active != LastActiveSlot)
	{
		LastActiveSlot = Active;
		View->FlashSelection();
	}
}

void ULyrisInventoryUISubsystem::HandleKeys(APlayerController* PC)
{
	ULyrisInventoryComponent* Inventory = AttachedInventory.Get();
	if (!Inventory || !View.IsValid())
	{
		return;
	}
	if (PC->WasInputKeyJustPressed(EKeys::I) || PC->WasInputKeyJustPressed(EKeys::Tab))
	{
		SetSatchelOpen(!View->IsOpen());
		return;
	}
	if (View->IsOpen())
	{
		return;  // the satchel handles its own clicks and keys
	}

	const int32 Hotbar = FMath::Min(LyrisInventoryUI::MaxHotbar, Inventory->SlotCount);
	static const FKey Digits[] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five,
		EKeys::Six, EKeys::Seven, EKeys::Eight, EKeys::Nine };
	for (int32 k = 0; k < Hotbar && k < static_cast<int32>(UE_ARRAY_COUNT(Digits)); ++k)
	{
		if (PC->WasInputKeyJustPressed(Digits[k]))
		{
			Inventory->SetActiveSlot(k);
			View->FlashSelection();
			return;
		}
	}
	const bool bUp = PC->WasInputKeyJustPressed(EKeys::MouseScrollUp);
	const bool bDown = PC->WasInputKeyJustPressed(EKeys::MouseScrollDown);
	if ((bUp || bDown) && Hotbar > 0)
	{
		const int32 Current = Inventory->GetActiveSlot();
		const int32 Start = (Current >= 0 && Current < Hotbar) ? Current : 0;
		Inventory->SetActiveSlot((Start + (bDown ? 1 : Hotbar - 1)) % Hotbar);
		View->FlashSelection();
	}
}

void ULyrisInventoryUISubsystem::SetSatchelOpen(bool bOpen)
{
	if (!View.IsValid() || View->IsOpen() == bOpen)
	{
		return;
	}
	View->SetOpen(bOpen);
	ULocalPlayer* LocalPlayer = GetLocalPlayer();
	UWorld* World = LocalPlayer ? LocalPlayer->GetWorld() : nullptr;
	APlayerController* PC = (LocalPlayer && World) ? LocalPlayer->GetPlayerController(World) : nullptr;
	if (!PC)
	{
		return;
	}
	if (bOpen)
	{
		FInputModeGameAndUI Mode;
		Mode.SetWidgetToFocus(View);
		Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		Mode.SetHideCursorDuringCapture(false);
		PC->SetInputMode(Mode);
		PC->SetShowMouseCursor(true);
		PC->SetIgnoreLookInput(true);
	}
	else
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->SetShowMouseCursor(false);
		PC->ResetIgnoreLookInput();
	}
}

bool ULyrisInventoryUISubsystem::IsSatchelOpen() const
{
	return View.IsValid() && View->IsOpen();
}

void ULyrisInventoryUISubsystem::HandleSlotClicked(int32 SlotIndex)
{
	ULyrisInventoryComponent* Inventory = AttachedInventory.Get();
	if (!Inventory || !View.IsValid())
	{
		return;
	}
	const int32 Carried = View->GetCarried();
	if (Carried == INDEX_NONE)
	{
		const TArray<FLyrisInventorySlot> InvSlots = Inventory->GetSlots();
		if (InvSlots.IsValidIndex(SlotIndex) && !InvSlots[SlotIndex].IsEmpty())
		{
			View->SetCarried(SlotIndex);
		}
		return;
	}
	View->SetCarried(INDEX_NONE);
	if (Carried != SlotIndex)
	{
		Inventory->MoveSlot(Carried, SlotIndex);  // fires OnInventoryChanged, which refreshes the view
	}
}

void ULyrisInventoryUISubsystem::HandleMoveRequested(int32 From, int32 To)
{
	if (ULyrisInventoryComponent* Inventory = AttachedInventory.Get())
	{
		Inventory->MoveSlot(From, To);
	}
}
