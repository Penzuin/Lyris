// Lyris UI: the hotbar and the satchel (bag) screen (T16).

#pragma once

#include "CoreMinimal.h"
#include "Widgets/SLeafWidget.h"

struct FSlateBrush;

/** What one inventory slot shows. Filled in by ULyrisInventoryUISubsystem from the inventory. */
struct FLyrisSlotView
{
	bool bEmpty = true;
	FName ItemId;
	FString Name;
	FString Description;
	/** e.g. "Tool - Pickaxe" or "Seed". */
	FString Kind;
	/** 0 Normal, 1 Fine, 2 Splendid, 3 Radiant (ELyrisItemQuality). */
	uint8 Quality = 0;
	int32 Count = 0;
	int32 MaxStack = 1;
	/** Painted icon, or null for a lettered fallback tile. Owned by the subsystem. */
	const FSlateBrush* Icon = nullptr;
};

/** A short "+3 Stone" note that floats up beside the hotbar when something new goes in the bag. */
struct FLyrisPickupToast
{
	FString Text;
	const FSlateBrush* Icon = nullptr;
	float Age = 0.f;
};

/**
 * One full-viewport leaf widget that paints the whole inventory HUD:
 *   - Hotbar (always, while on foot): slots 1-9 along the bottom, the selected one lifted with a
 *     gold ring; the item's name fades in above it when the selection changes; pickup notes.
 *   - Satchel (I or Tab): a parchment journal page with the pack (slots 10+) and the hotbar row on
 *     the left, and the hovered item's picture, name, kind, quality and description on the right.
 *     Click a slot to pick its stack up, click another to put it there (merge, move or swap).
 *
 * All drawing is done in OnPaint with rounded boxes and text, so it needs no .uasset widgets.
 * Colours are named constants at the top of the .cpp.
 */
class LYRIS_API SLyrisInventoryView : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SLyrisInventoryView) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	/** Called with the slot index when a slot is clicked in the satchel. */
	TFunction<void(int32)> OnSlotClicked;
	/** Called with (from, to) when the player hovers a slot and presses 1-9 to send it to the hotbar. */
	TFunction<void(int32, int32)> OnMoveRequested;
	/** Called when the player presses I, Tab or Escape (or clicks outside) while the satchel is open. */
	TFunction<void()> OnCloseRequested;

	void SetSlots(const TArray<FLyrisSlotView>& InSlots, int32 InActiveSlot, int32 InHotbarCount);
	void SetOpen(bool bInOpen);
	bool IsOpen() const { return bOpen; }
	/** The slot whose stack is "in hand" on the cursor (INDEX_NONE for none). */
	void SetCarried(int32 SlotIndex) { Carried = SlotIndex; }
	int32 GetCarried() const { return Carried; }
	void AddToast(const FString& Text, const FSlateBrush* Icon);
	/** The interaction prompt ("Till soil") shown above the hotbar with its key; empty hides it. */
	void SetPrompt(const FString& InPrompt, const FString& InKey);
	/** Shows the selected item's name above the hotbar for a moment. */
	void FlashSelection();

	// SWidget
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override;
	virtual FReply OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;
	virtual bool SupportsKeyboardFocus() const override { return bOpen; }

protected:
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

private:
	struct FLayout
	{
		FVector2f Panel;      // satchel panel top-left
		FVector2f PanelSize;
		TArray<FVector2f> SlotPos;  // satchel slot top-left, by inventory index
		TArray<FVector2f> HotbarPos; // on-foot hotbar slot top-left, by inventory index (0..HotbarCount-1)
		float SlotSize = 64.f;
		float HotbarSize = 60.f;
		FVector2f DetailPos;   // right page
		FVector2f DetailSize;
	};

	FLayout ComputeLayout(const FVector2f& Size) const;
	int32 HitSlot(const FLayout& Layout, const FVector2f& Local) const;

	void PaintSlot(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FVector2f& Pos, float Size,
		const FLyrisSlotView& View, int32 Index, bool bActive, bool bHover, bool bDimmed, float Opacity, bool bShowNumber) const;
	void PaintHotbar(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FLayout& Layout) const;
	void PaintSatchel(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FLayout& Layout) const;
	void PaintDetails(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FLayout& Layout) const;
	void PaintPrompt(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FLayout& Layout) const;
	void PaintToasts(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FLayout& Layout) const;

	TArray<FLyrisSlotView> Slots;
	int32 ActiveSlot = INDEX_NONE;
	int32 HotbarCount = 9;
	int32 Hovered = INDEX_NONE;
	int32 Carried = INDEX_NONE;
	bool bOpen = false;

	FVector2f Cursor = FVector2f::ZeroVector;
	float OpenAlpha = 0.f;       // satchel fade
	float LiftAlpha = 1.f;       // active-slot lift animation
	float SelectionTimer = 0.f;  // name label above the hotbar
	TArray<FLyrisPickupToast> Toasts;
	FString Prompt;
	FString PromptKey;
	float PromptAlpha = 0.f;
	bool bPromptWanted = false;
};
