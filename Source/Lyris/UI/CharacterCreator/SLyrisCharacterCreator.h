// Lyris character creator: the full-screen Slate screen (six voyage steps, deep appearance editor).

#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "UObject/StrongObjectPtr.h"

#include "UI/CharacterCreator/LyrisCreatorContract.h"
#include "UI/CharacterCreator/LyrisCreatorData.h"
#include "UI/CharacterCreator/LyrisCreatorStage.h"

class APlayerController;
class SBox;
class SLyrisCreatorViewport;

/**
 * The character creator screen, built entirely in Slate.
 *
 * Layout (in the spirit of Black Desert / Where Winds Meet, dressed as parchment at dusk):
 *  - top: the voyage route, six lantern markers joined by a dotted line (People, Appearance, Path,
 *    Backstory, Lantern, Name), with the current step's title and its moment on the voyage;
 *  - left (Appearance step): category tabs with lock toggles, then the sections of that category;
 *  - right: the editor for the chosen section (sliders from the catalog, part tiles, colour swatch
 *    rows with hue / light shifts, part scalars and toggles), or the cards of a picker step;
 *  - bottom: randomise with wildness, undo / redo, symmetry, reset section, before / after, presets,
 *    share code copy / paste, expression and pose previews, lighting previews, back / next;
 *  - behind it all: the 3D stage, with orbit, zoom and click-and-drag face sculpting.
 *
 * Every change goes through ULyrisAppearanceComponent's Set* functions; the screen never touches meshes.
 * Values on screen are read back from the component every frame (Slate attributes), so undo, presets,
 * sculpting and the component's own clamps (e.g. the adult proportions guard) always show correctly.
 *
 * Keys: Tab / Shift+Tab change category; Left / Right adjust the focused slider (Up / Down move between
 * them); Ctrl+Z undo, Ctrl+Y or Ctrl+Shift+Z redo; Esc closes. Gamepad: LB / RB undo / redo,
 * LT / RT change category.
 */
class SLyrisCharacterCreator : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SLyrisCharacterCreator) {}
		SLATE_ARGUMENT(TWeakObjectPtr<ALyrisCreatorStage>, Stage)
		SLATE_ARGUMENT(TWeakObjectPtr<APlayerController>, PlayerController)
		/** Called when the player closes the creator (Esc) or after the character is saved. */
		SLATE_EVENT(FSimpleDelegate, OnRequestClose)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	// SWidget
	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;
	virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override;

private:
	// ------------------------------------------------------------------ Reading the current look
	ULyrisAppearanceComponent* Comp() const;
	ULyrisAppearanceCatalog* Catalog() const { return CatalogPtr.Get(); }
	/** The component's current look (or an empty default when there is no stage). */
	const FLyrisAppearance& CurrentLook() const;
	FName CurrentPeople() const;
	float GetSliderValue(const FLyrisSliderDef& Def) const;
	float GetSliderValueById(FName Id, float Default) const;
	float GetScalar(FName Key) const;
	FName GetPart(FName Slot) const;
	FLyrisColorPick GetColor(FName Channel) const;
	const FLyrisSliderDef* FindSliderDef(FName Id) const;
	const FLyrisColorChannelDef* FindChannelDef(FName Id) const;
	bool IsRegionSculptable(FName Region) const;

	// ------------------------------------------------------------------ Changing it (always via the component)
	void SetSliderValue(const FLyrisSliderDef& Def, float Value);
	void SetScalarValue(FName Key, float Value);
	void SetPartValue(FName Slot, FName PartId);
	void SetColorValue(FName Channel, const FLyrisColorPick& Pick);
	void ApplyWholeLook(const FLyrisAppearance& Look, bool bRecordHistory);
	void SetPeople(FName People);
	void SetFrame(FName Frame);

	// ------------------------------------------------------------------ History (undo / redo)
	/** Records the look before a discrete change. Changes with the same key within a short time are
	 *  coalesced into one entry (keyboard nudges on one slider, a swatch row being clicked through). */
	void RecordChange(FName CoalesceKey);
	/** A slider, colour shift or sculpt drag is one entry: snapshot on grab, nothing while moving. */
	void BeginDrag();
	void EndDrag();
	void PushUndo(const FLyrisAppearance& Look);
	void Undo();
	void Redo();

	// ------------------------------------------------------------------ Tools
	void Randomise();
	/** Loads preset Index for People (None = the current People). */
	void ApplyPreset(int32 Index, FName People = NAME_None);
	void ResetSection();
	void CopyShareCode();
	void PasteShareCode();
	void SetSymmetry(bool bOn);
	/** Copies every left slider to its right mirror (or right to left). */
	void MirrorAll(bool bLeftToRight);
	void OnSculptBegin(FName Region);
	void OnSculptDrag(FName Region, float DeltaX, float DeltaY, float HorizontalSign);
	void OnSculptEnd();
	void OnSculptReset(FName Region);
	void BeginCompare();
	void EndCompare();
	void SetLighting(ELyrisCreatorLighting Lighting);
	void CycleExpression();
	void CyclePose();

	// ------------------------------------------------------------------ Navigation
	ELyrisCreatorStep CurrentStep() const { return static_cast<ELyrisCreatorStep>(StepIndex); }
	void GoToStep(int32 NewStep);
	bool CanLeaveStep() const;
	void SetCategory(FName Category);
	void SetSection(FName Section);
	void CycleCategory(int32 Direction);
	void UpdateCameraShot();
	TArray<FName> GetCategoryList() const;
	TArray<FName> GetSectionList(FName Category) const;
	void PickPath(FName PathId);
	void PickLantern(FName LanternId);
	void SetLanternGlass(const FLyrisColorPick& Pick);
	void LightYourLantern();

	// ------------------------------------------------------------------ Messages and prompts
	void ShowStatus(const FText& Text, bool bWarning = false);
	struct FPromptAction
	{
		FText Label;
		TFunction<void()> Action;
	};
	void ShowPrompt(const FText& Question, TArray<FPromptAction> Actions);
	void ClearPrompt();

	// ------------------------------------------------------------------ Building widgets
	void RequestRebuild() { bNeedsRebuild = true; }
	void RebuildAll();
	TSharedRef<SWidget> BuildRoute();
	TSharedRef<SWidget> BuildLeftColumn();
	TSharedRef<SWidget> BuildRightPanel();
	TSharedRef<SWidget> BuildBottomBar();
	TSharedRef<SWidget> BuildAppearanceSection();
	TSharedRef<SWidget> BuildPeopleStep();
	TSharedRef<SWidget> BuildPathStep();
	TSharedRef<SWidget> BuildBackstoryStep();
	TSharedRef<SWidget> BuildLanternStep();
	TSharedRef<SWidget> BuildNameStep();

	TSharedRef<SWidget> BuildSliderRow(const FLyrisSliderDef& Def);
	TSharedRef<SWidget> BuildScalarRow(const FLyrisCreatorScalarInfo& Info);
	/** Shared look of a labelled slider row with a value label; used by sliders and part scalars. */
	TSharedRef<SWidget> MakeValueRow(const FText& Label, const FText& Tooltip, float Min, float Max,
		TFunction<float()> Get, TFunction<void(float)> Set, FName CoalesceKey, TFunction<void()> OnGrab);
	TSharedRef<SWidget> BuildPresetRow();
	TSharedRef<SWidget> BuildSummary();
	TSharedRef<SWidget> MakeLightingChip(ELyrisCreatorLighting Preset, const FText& Label, const FText& Tooltip);
	TSharedRef<SWidget> BuildPartGrid(const FLyrisCreatorSlotInfo& Slot);
	/** Swatch row plus hue / light shift sliders. bHistory = false for the lantern glass, which is not
	 *  part of FLyrisAppearance and so not in the look's undo history. */
	TSharedRef<SWidget> BuildColorChannel(const FLyrisColorChannelDef& Channel,
		TFunction<FLyrisColorPick()> GetPick, TFunction<void(const FLyrisColorPick&)> SetPick, bool bHistory);
	TSharedRef<SWidget> BuildCard(const FText& Title, const FText& Line1, const FText& Line2,
		TFunction<bool()> IsSelected, TFunction<void()> OnPick);
	TSharedRef<SWidget> BuildTile(const FText& Label, TFunction<bool()> IsSelected, TFunction<void()> OnPick, const FText& Tooltip);
	/** Small labelled slider. HistoryKey None = not recorded in undo history (e.g. the wildness slider). */
	TSharedRef<SWidget> BuildMiniSlider(const FText& Label, float Min, float Max, TFunction<float()> Get, TFunction<void(float)> Set,
		const FText& Tooltip, FName HistoryKey);

	TSharedRef<SWidget> MakeButton(const FText& Label, TFunction<void()> OnClick, const FText& Tooltip,
		TAttribute<bool> IsEnabled = true);
	TSharedRef<SWidget> MakeHeading(const FText& Text) const;
	TSharedRef<SWidget> MakeNote(const FText& Text) const;

	// ------------------------------------------------------------------ State
	TWeakObjectPtr<ALyrisCreatorStage> Stage;
	TWeakObjectPtr<APlayerController> PlayerController;
	TStrongObjectPtr<ULyrisAppearanceCatalog> CatalogPtr;
	mutable TWeakObjectPtr<ULyrisAppearanceComponent> CachedComponent;
	FSimpleDelegate OnRequestClose;

	/** Path, backstory, lantern and name. The appearance lives in the component and is copied in on save. */
	FLyrisCharacterProfile Profile;
	bool bPlayerPickedOutfit = false;

	/** People last time we built the panels; when it changes the People-specific options are rebuilt. */
	FName CachedPeople;

	int32 StepIndex = 0;
	int32 FurthestStep = 0;
	FName Category;
	FName Section;

	bool bSymmetry = true;
	bool bShowPresets = false;
	TSet<FName> LockedCategories;
	float Wildness = 0.35f;
	ELyrisCreatorLighting Lighting = ELyrisCreatorLighting::DuskDeck;
	int32 ExpressionIndex = 0;
	int32 PoseIndex = 0;

	TArray<FLyrisAppearance> UndoStack;
	TArray<FLyrisAppearance> RedoStack;
	bool bDragging = false;
	FName LastChangeKey;
	double LastChangeTime = 0.0;

	/** Running values during a sculpt drag, so many small deltas add up exactly. */
	TMap<FName, float> SculptValues;

	/** "Before" look for the before / after button: taken when entering a category. */
	FLyrisAppearance CompareSnapshot;
	FLyrisAppearance LookBeforeCompare;
	bool bComparing = false;

	FText StatusText;
	bool bStatusWarning = false;
	double StatusUntil = 0.0;

	FString NameDraft;
	FText NameError;

	bool bNeedsRebuild = false;

	TSharedPtr<SBox> RouteBox;
	TSharedPtr<SBox> LeftBox;
	TSharedPtr<SBox> RightBox;
	TSharedPtr<SBox> BottomBox;
	TSharedPtr<SBox> PromptBox;
	TSharedPtr<SLyrisCreatorViewport> Viewport;
};
