// Lyris UI: hotbar, satchel screen and pickup notes for the local player's inventory (T16).

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/LocalPlayerSubsystem.h"
#include "Tickable.h"
#include "LyrisInventoryUISubsystem.generated.h"

class APlayerController;
class SLyrisInventoryView;
class SWidget;
class UGameViewportClient;
class ULyrisInventoryComponent;
class UTexture2D;
struct FSlateBrush;

/**
 * One per local player. Whenever that player's pawn (or controller) has a ULyrisInventoryComponent,
 * this shows SLyrisInventoryView on the player's part of the viewport and keeps it in step with
 * the inventory. Nothing else has to call it.
 *
 * Keys (read here, so no input assets are needed yet):
 *   1-9 or the mouse wheel   choose the hotbar slot (what you hold)
 *   I or Tab                 open / close the satchel (the mouse cursor shows while it's open)
 * While the satchel is open: click a slot to pick it up and another to put it there; hover and
 * press 1-9 to send that stack to a hotbar slot; right click puts a picked-up stack back.
 *
 * Icons: ULyrisItemDefinition::Icon when set, otherwise Art/Icons/<item id>.png from the project
 * folder (painted by Art/Icons/paint_icons.py), loaded once and kept for the session.
 */
UCLASS()
class LYRIS_API ULyrisInventoryUISubsystem : public ULocalPlayerSubsystem, public FTickableGameObject
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	// FTickableGameObject
	virtual void Tick(float DeltaTime) override;
	virtual ETickableTickType GetTickableTickType() const override;
	virtual bool IsTickable() const override;
	virtual TStatId GetStatId() const override;
	virtual UWorld* GetTickableGameObjectWorld() const override;

	UFUNCTION(BlueprintCallable, Category = "Lyris|UI")
	void SetSatchelOpen(bool bOpen);

	UFUNCTION(BlueprintPure, Category = "Lyris|UI")
	bool IsSatchelOpen() const;

private:
	void Attach(ULyrisInventoryComponent* Inventory, UGameViewportClient* Viewport);
	void Detach();
	void Refresh();
	void HandleKeys(APlayerController* PC);
	void HandleSlotClicked(int32 SlotIndex);
	void HandleMoveRequested(int32 From, int32 To);

	UFUNCTION()
	void HandleInventoryChanged();

	/** The icon brush for an item id (null if there's no picture for it). */
	const FSlateBrush* GetIconBrush(FName ItemId);

	TSharedPtr<SLyrisInventoryView> View;
	TWeakPtr<SWidget> AddedWidget;
	TWeakObjectPtr<ULyrisInventoryComponent> AttachedInventory;
	TWeakObjectPtr<UGameViewportClient> AttachedViewport;

	/** Textures loaded for icons; kept alive here. */
	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<UTexture2D>> IconTextures;
	TMap<FName, TSharedPtr<FSlateBrush>> IconBrushes;
	TSet<FName> MissingIcons;

	/** Counts per item id at the last refresh, to spot pickups for the "+3 Stone" notes. */
	TMap<FName, int32> LastCounts;
	bool bHaveCounts = false;
	int32 LastActiveSlot = INDEX_NONE;

	bool bActive = false;
};
