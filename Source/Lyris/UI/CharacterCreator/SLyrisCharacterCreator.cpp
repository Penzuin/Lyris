// Lyris character creator: the full-screen Slate screen.
//
// Reading guide:
//   1. Construct / Tick / keys
//   2. Reading the look (always from the appearance component)
//   3. Changing the look (always through the component's Set* functions)
//   4. Undo / redo
//   5. Tools: randomise, presets, reset, share codes, symmetry, compare, lighting, previews
//   6. Face sculpting
//   7. Steps and navigation
//   8. Widget builders

#include "UI/CharacterCreator/SLyrisCharacterCreator.h"

#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Kismet/GameplayStatics.h"
#include "Math/RandomStream.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/Layout/SUniformGridPanel.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SNullWidget.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

#include "UI/CharacterCreator/LyrisCreatorStyle.h"
#include "UI/CharacterCreator/SLyrisCreatorViewport.h"

#define LOCTEXT_NAMESPACE "LyrisCreator"

namespace
{
	/** How many looks undo remembers (spec 9.4). */
	constexpr int32 MaxHistory = 100;

	/** Repeated small changes to the same control within this many seconds are one undo entry. */
	constexpr double CoalesceSeconds = 0.75;

	/** Sculpt sensitivity: the full slider range over this many slate units of drag (spec 9.1). */
	constexpr float SculptFullRangeUnits = 300.f;

	/** Slider value label: -100..100 for two-way sliders, 0..100 for one-way. */
	FText FormatValue(float Value, float Min)
	{
		const int32 Percent = FMath::RoundToInt(Value * 100.f);
		if (Min < 0.f && Percent > 0)
		{
			return FText::FromString(FString::Printf(TEXT("+%d"), Percent));
		}
		return FText::FromString(FString::Printf(TEXT("%d"), Percent));
	}

	FText NameOr(const FText& Text, FName Fallback)
	{
		return Text.IsEmpty() ? FText::FromName(Fallback) : Text;
	}

	const FLyrisCreatorCard* FindCard(const TArray<FLyrisCreatorCard>& Cards, FName Id)
	{
		return Cards.FindByPredicate([Id](const FLyrisCreatorCard& Card) { return Card.Id == Id; });
	}

	/** True for an id that names the left side of a mirrored pair ("Eyes.SizeL"). */
	bool IsLeftId(FName Id)
	{
		const FString S = Id.ToString();
		return S.Len() > 1 && S.EndsWith(TEXT("L"), ESearchCase::CaseSensitive);
	}

	/** Regions whose vertical drag should grow the value when dragged DOWN (the chin drags the face longer). */
	bool IsDownPositiveRegion(FName Region)
	{
		return Region == TEXT("Chin");
	}
}

// =====================================================================================================
// 1. Construct / Tick / keys
// =====================================================================================================

void SLyrisCharacterCreator::Construct(const FArguments& InArgs)
{
	Stage = InArgs._Stage;
	PlayerController = InArgs._PlayerController;
	OnRequestClose = InArgs._OnRequestClose;

	CatalogPtr.Reset(LyrisCreator::CatalogFor(Comp()));

	// Sensible starting choices for the non-appearance parts of the profile.
	Profile.LanternShape = TEXT("Lantern.Ships");
	Profile.LanternGlass = FLyrisColorPick();

	// Resume a saved character if there is one (handy while testing, and later for the mirror).
	if (UGameplayStatics::DoesSaveGameExist(LyrisCreator::SaveSlotName(), LyrisCreator::SaveUserIndex()))
	{
		if (ULyrisCharacterSaveGame* Save = Cast<ULyrisCharacterSaveGame>(
			UGameplayStatics::LoadGameFromSlot(LyrisCreator::SaveSlotName(), LyrisCreator::SaveUserIndex())))
		{
			Profile = LyrisCreator::SaveProfile(*Save);
			NameDraft = Profile.Name;
			bPlayerPickedOutfit = true;
			if (ULyrisAppearanceComponent* Appearance = Comp())
			{
				Appearance->SetAppearance(Profile.Appearance);
			}
			if (Profile.LanternShape.IsNone())
			{
				Profile.LanternShape = TEXT("Lantern.Ships");
			}
		}
	}

	CachedPeople = CurrentPeople();
	const TArray<FName> CategoryList = GetCategoryList();
	Category = CategoryList.Num() > 0 ? CategoryList[0] : NAME_None;
	const TArray<FName> SectionList = GetSectionList(Category);
	Section = SectionList.Num() > 0 ? SectionList[0] : NAME_None;
	CompareSnapshot = CurrentLook();

	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();

	ChildSlot
	[
		SNew(SOverlay)

		// The 3D stage shows through; this layer turns mouse input into orbit, zoom and sculpting.
		+ SOverlay::Slot()
		[
			SAssignNew(Viewport, SLyrisCreatorViewport)
			.Stage(Stage)
			.PlayerController(PlayerController)
			.SculptEnabled_Lambda([this]()
			{
				return CurrentStep() == ELyrisCreatorStep::Appearance && Category == TEXT("Face") && !bComparing;
			})
			.IsRegionSculptable(FIsLyrisSculptRegion::CreateSP(this, &SLyrisCharacterCreator::IsRegionSculptable))
			.OnSculptBegin(FOnLyrisSculptRegion::CreateSP(this, &SLyrisCharacterCreator::OnSculptBegin))
			.OnSculptDrag(FOnLyrisSculptDrag::CreateSP(this, &SLyrisCharacterCreator::OnSculptDrag))
			.OnSculptEnd(FSimpleDelegate::CreateSP(this, &SLyrisCharacterCreator::OnSculptEnd))
			.OnSculptReset(FOnLyrisSculptRegion::CreateSP(this, &SLyrisCharacterCreator::OnSculptReset))
		]

		// Panels. Layout boxes let clicks fall through to the viewport where there is no panel.
		+ SOverlay::Slot()
		.Padding(Style.ScreenPadding)
		[
			SNew(SVerticalBox)
			.Visibility(EVisibility::SelfHitTestInvisible)

			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			[
				SAssignNew(RouteBox, SBox)
				.Visibility(EVisibility::SelfHitTestInvisible)
			]

			+ SVerticalBox::Slot()
			.FillHeight(1.f)
			.Padding(0.f, Style.Gap * 1.5f)
			[
				SNew(SHorizontalBox)
				.Visibility(EVisibility::SelfHitTestInvisible)

				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SAssignNew(LeftBox, SBox)
					.WidthOverride(Style.LeftColumnWidth)
					.Visibility(EVisibility::SelfHitTestInvisible)
				]

				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				[
					SNew(SSpacer)
					.Visibility(EVisibility::HitTestInvisible)
				]

				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SAssignNew(RightBox, SBox)
					.WidthOverride(Style.RightPanelWidth)
					.Visibility(EVisibility::SelfHitTestInvisible)
				]
			]

			// Status line ("Share code copied", warnings).
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			.Padding(0.f, 0.f, 0.f, Style.Gap)
			[
				SNew(SBorder)
				.BorderImage(&Style.SubPanelBrush)
				.Padding(FMargin(14.f, 6.f))
				.Visibility_Lambda([this]()
				{
					return FPlatformTime::Seconds() < StatusUntil ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
				})
				[
					SNew(STextBlock)
					.Font(Style.BodyFont)
					.Text_Lambda([this]() { return StatusText; })
					.ColorAndOpacity_Lambda([this]()
					{
						const FLyrisCreatorStyle& S = FLyrisCreatorStyle::Get();
						return FSlateColor(bStatusWarning ? S.RedBand : S.DarkWood);
					})
				]
			]

			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SAssignNew(BottomBox, SBox)
				.Visibility(EVisibility::SelfHitTestInvisible)
			]
		]

		// Questions ("Switch to Moonlit elf to use this look?").
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Center)
		[
			SAssignNew(PromptBox, SBox)
			.Visibility(EVisibility::Collapsed)
		]
	];

	Viewport->SetFocusTarget(SharedThis(this));
	RebuildAll();

	if (ALyrisCreatorStage* StagePtr = Stage.Get())
	{
		StagePtr->SetLightingPreset(Lighting);
	}
	UpdateCameraShot();
}

void SLyrisCharacterCreator::Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime)
{
	SCompoundWidget::Tick(AllottedGeometry, InCurrentTime, InDeltaTime);

	// Undo, a preset or a share code can change the People; People-specific options then differ.
	const FName People = CurrentPeople();
	if (People != CachedPeople)
	{
		CachedPeople = People;
		RequestRebuild();
	}

	if (bNeedsRebuild)
	{
		RebuildAll();
	}
}

FReply SLyrisCharacterCreator::OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	const FKey Key = InKeyEvent.GetKey();
	const bool bCtrl = InKeyEvent.IsControlDown() || InKeyEvent.IsCommandDown();

	if (Key == EKeys::Escape)
	{
		if (PromptBox.IsValid() && PromptBox->GetVisibility() != EVisibility::Collapsed)
		{
			ClearPrompt();
			return FReply::Handled();
		}
		ShowPrompt(LOCTEXT("LeaveQ", "Leave the creator? Your character has not been written in the ledger yet."), {
			{ LOCTEXT("Leave", "Leave"), [this]() { OnRequestClose.ExecuteIfBound(); } },
			{ LOCTEXT("Stay", "Stay"), []() {} },
		});
		return FReply::Handled();
	}

	// Undo / redo (keyboard and gamepad shoulders).
	if ((bCtrl && Key == EKeys::Z && !InKeyEvent.IsShiftDown()) || Key == EKeys::Gamepad_LeftShoulder)
	{
		Undo();
		return FReply::Handled();
	}
	if ((bCtrl && (Key == EKeys::Y || (Key == EKeys::Z && InKeyEvent.IsShiftDown()))) || Key == EKeys::Gamepad_RightShoulder)
	{
		Redo();
		return FReply::Handled();
	}

	// Category tabs (keyboard Tab / Shift+Tab, gamepad triggers).
	if (CurrentStep() == ELyrisCreatorStep::Appearance)
	{
		if (Key == EKeys::Tab)
		{
			CycleCategory(InKeyEvent.IsShiftDown() ? -1 : 1);
			return FReply::Handled();
		}
		if (Key == EKeys::Gamepad_LeftTrigger)
		{
			CycleCategory(-1);
			return FReply::Handled();
		}
		if (Key == EKeys::Gamepad_RightTrigger)
		{
			CycleCategory(1);
			return FReply::Handled();
		}
	}

	// Left / Right on a focused slider are handled by SSlider itself before this (StepSize,
	// RequiresControllerLock off); Up / Down fall through to Slate navigation and move between rows.
	return SCompoundWidget::OnKeyDown(MyGeometry, InKeyEvent);
}

// =====================================================================================================
// 2. Reading the look
// =====================================================================================================

ULyrisAppearanceComponent* SLyrisCharacterCreator::Comp() const
{
	// Hundreds of attribute lambdas ask for this every frame, so remember it.
	if (ULyrisAppearanceComponent* Cached = CachedComponent.Get())
	{
		return Cached;
	}
	ALyrisCreatorStage* StagePtr = Stage.Get();
	ULyrisAppearanceComponent* Found = StagePtr ? StagePtr->GetAppearanceComponent() : nullptr;
	CachedComponent = Found;
	return Found;
}

const FLyrisAppearance& SLyrisCharacterCreator::CurrentLook() const
{
	if (const ULyrisAppearanceComponent* Appearance = Comp())
	{
		return Appearance->GetAppearance();
	}
	static const FLyrisAppearance Empty;
	return Empty;
}

FName SLyrisCharacterCreator::CurrentPeople() const
{
	return CurrentLook().People;
}

float SLyrisCharacterCreator::GetSliderValue(const FLyrisSliderDef& Def) const
{
	return GetSliderValueById(Def.Id, Def.Default);
}

float SLyrisCharacterCreator::GetSliderValueById(FName Id, float Default) const
{
	const float* Found = CurrentLook().Sliders.Find(Id);
	return Found ? *Found : Default;
}

float SLyrisCharacterCreator::GetScalar(FName Key) const
{
	if (const float* Found = CurrentLook().PartScalars.Find(Key))
	{
		return *Found;
	}
	const FLyrisCreatorScalarInfo* Info = LyrisCreatorData::FindScalar(Key);
	return Info ? Info->Default : 0.f;
}

FName SLyrisCharacterCreator::GetPart(FName Slot) const
{
	const FName* Found = CurrentLook().Parts.Find(Slot);
	return Found ? *Found : NAME_None;
}

FLyrisColorPick SLyrisCharacterCreator::GetColor(FName Channel) const
{
	const FLyrisColorPick* Found = CurrentLook().Colors.Find(Channel);
	return Found ? *Found : FLyrisColorPick();
}

const FLyrisSliderDef* SLyrisCharacterCreator::FindSliderDef(FName Id) const
{
	if (!Catalog() || Id.IsNone())
	{
		return nullptr;
	}
	return Catalog()->Sliders.FindByPredicate([Id](const FLyrisSliderDef& Def) { return Def.Id == Id; });
}

const FLyrisColorChannelDef* SLyrisCharacterCreator::FindChannelDef(FName Id) const
{
	if (!Catalog())
	{
		return nullptr;
	}
	return Catalog()->ColorChannels.FindByPredicate([Id](const FLyrisColorChannelDef& Def) { return Def.Id == Id; });
}

bool SLyrisCharacterCreator::IsRegionSculptable(FName Region) const
{
	if (!Catalog())
	{
		return false;
	}
	const FName People = CurrentPeople();
	return Catalog()->Sliders.ContainsByPredicate([Region, People](const FLyrisSliderDef& Def)
	{
		return Def.SculptRegion == Region && LyrisCreator::AllowsPeople(Def.People, People);
	});
}

// =====================================================================================================
// 3. Changing the look (history is recorded by the caller, see section 4)
// =====================================================================================================

void SLyrisCharacterCreator::SetSliderValue(const FLyrisSliderDef& Def, float Value)
{
	ULyrisAppearanceComponent* Appearance = Comp();
	if (!Appearance)
	{
		return;
	}
	const float Clamped = FMath::Clamp(Value, Def.Min, Def.Max);
	Appearance->SetSlider(Def.Id, Clamped);

	// Symmetry: pairs are defined in mirrored space, so the same value on both sides is symmetric.
	if (bSymmetry && !Def.MirrorOf.IsNone())
	{
		const FLyrisSliderDef* Mirror = FindSliderDef(Def.MirrorOf);
		const float MirrorValue = Mirror ? FMath::Clamp(Clamped, Mirror->Min, Mirror->Max) : Clamped;
		Appearance->SetSlider(Def.MirrorOf, MirrorValue);
	}
}

void SLyrisCharacterCreator::SetScalarValue(FName Key, float Value)
{
	ULyrisAppearanceComponent* Appearance = Comp();
	if (!Appearance)
	{
		return;
	}
	Appearance->SetPartScalar(Key, Value);

	// Turning heterochromia off makes both eyes match again (spec 3.3).
	if (Key == LyrisCreatorData::Scalar_Heterochromia && Value < 0.5f)
	{
		Appearance->SetColor(LyrisCreatorData::Channel_IrisR, GetColor(LyrisCreatorData::Channel_IrisL));
	}
}

void SLyrisCharacterCreator::SetPartValue(FName Slot, FName PartId)
{
	if (ULyrisAppearanceComponent* Appearance = Comp())
	{
		Appearance->SetPart(Slot, PartId);
	}
	if (Slot == LyrisCreatorData::Slot_Outfit)
	{
		bPlayerPickedOutfit = true;
	}
	if (Slot == LyrisCreatorData::Slot_Expression)
	{
		if (ALyrisCreatorStage* StagePtr = Stage.Get())
		{
			StagePtr->PreviewExpression(PartId);
		}
	}
}

void SLyrisCharacterCreator::SetColorValue(FName Channel, const FLyrisColorPick& Pick)
{
	ULyrisAppearanceComponent* Appearance = Comp();
	if (!Appearance)
	{
		return;
	}
	Appearance->SetColor(Channel, Pick);

	// Without heterochromia the right iris always follows the left (spec 3.3).
	if (Channel == LyrisCreatorData::Channel_IrisL && GetScalar(LyrisCreatorData::Scalar_Heterochromia) < 0.5f)
	{
		Appearance->SetColor(LyrisCreatorData::Channel_IrisR, Pick);
	}
}

void SLyrisCharacterCreator::ApplyWholeLook(const FLyrisAppearance& Look, bool bRecordHistory)
{
	ULyrisAppearanceComponent* Appearance = Comp();
	if (!Appearance)
	{
		return;
	}
	if (bRecordHistory)
	{
		PushUndo(CurrentLook());
	}
	Appearance->SetAppearance(Look);
	LastChangeKey = NAME_None;
}

void SLyrisCharacterCreator::SetPeople(FName People)
{
	if (People == CurrentPeople())
	{
		return;
	}
	// Picking a People swaps the deck character live and loads that People's first preset (spec 2).
	ApplyPreset(0, People);
	RequestRebuild();
}

void SLyrisCharacterCreator::SetFrame(FName Frame)
{
	if (Frame == CurrentLook().Frame)
	{
		return;
	}
	FLyrisAppearance Look = CurrentLook();
	Look.Frame = Frame;
	ApplyWholeLook(Look, true);
}

// =====================================================================================================
// 4. Undo / redo
// =====================================================================================================

void SLyrisCharacterCreator::PushUndo(const FLyrisAppearance& Look)
{
	UndoStack.Add(Look);
	if (UndoStack.Num() > MaxHistory)
	{
		UndoStack.RemoveAt(0);
	}
	RedoStack.Reset();
}

void SLyrisCharacterCreator::RecordChange(FName CoalesceKey)
{
	if (bDragging || bComparing)
	{
		return; // the drag already took its snapshot on grab
	}
	const double Now = FPlatformTime::Seconds();
	const bool bSameAsLast = !CoalesceKey.IsNone() && CoalesceKey == LastChangeKey && (Now - LastChangeTime) < CoalesceSeconds;
	if (!bSameAsLast)
	{
		PushUndo(CurrentLook());
	}
	LastChangeKey = CoalesceKey;
	LastChangeTime = Now;
}

void SLyrisCharacterCreator::BeginDrag()
{
	if (!bDragging && !bComparing)
	{
		PushUndo(CurrentLook());
		bDragging = true;
		LastChangeKey = NAME_None;
	}
}

void SLyrisCharacterCreator::EndDrag()
{
	bDragging = false;
}

void SLyrisCharacterCreator::Undo()
{
	ULyrisAppearanceComponent* Appearance = Comp();
	if (!Appearance || UndoStack.Num() == 0 || bComparing)
	{
		return;
	}
	RedoStack.Add(CurrentLook());
	const FLyrisAppearance Previous = UndoStack.Pop();
	Appearance->SetAppearance(Previous);
	LastChangeKey = NAME_None;
}

void SLyrisCharacterCreator::Redo()
{
	ULyrisAppearanceComponent* Appearance = Comp();
	if (!Appearance || RedoStack.Num() == 0 || bComparing)
	{
		return;
	}
	UndoStack.Add(CurrentLook());
	const FLyrisAppearance Next = RedoStack.Pop();
	Appearance->SetAppearance(Next);
	LastChangeKey = NAME_None;
}

// =====================================================================================================
// 5. Tools
// =====================================================================================================

void SLyrisCharacterCreator::Randomise()
{
	if (!Catalog())
	{
		return;
	}
	// People and frame stay as chosen; everything not locked is rolled (spec 9.3). The library keeps
	// values inside ranges and curated swatches and applies the adult proportions guard.
	FLyrisAppearance Look = CurrentLook();
	const FName People = Look.People;
	const FName Frame = Look.Frame;
	FRandomStream Stream(static_cast<int32>(FPlatformTime::Cycles()));
	LyrisCreator::Randomize(Catalog(), Look, Stream, LockedCategories, Wildness);
	Look.People = People;
	Look.Frame = Frame;
	ApplyWholeLook(Look, true);
	ShowStatus(LOCTEXT("Rolled", "The dice have spoken. Ctrl+Z to undo."));
}

void SLyrisCharacterCreator::ApplyPreset(int32 Index, FName People)
{
	if (!Catalog())
	{
		return;
	}
	// TODO(Player T23): the spec (9.8) wants six hand-made presets per People. The contract has no
	// preset API yet, so until there is one a preset is a calm, seeded roll for that People: the same
	// name always gives the same face.
	FLyrisAppearance Look;
	Look.People = People.IsNone() ? CurrentPeople() : People;
	Look.Frame = CurrentLook().Frame;
	FRandomStream Stream(static_cast<int32>(GetTypeHash(Look.People)) ^ (Index * 7919 + 17));
	LyrisCreator::Randomize(Catalog(), Look, Stream, TSet<FName>(), 0.2f);
	Look.People = People.IsNone() ? CurrentPeople() : People;

	// Keep the outfit the player chose (or their path's), presets are about the face and body.
	if (const FName* Outfit = CurrentLook().Parts.Find(LyrisCreatorData::Slot_Outfit))
	{
		Look.Parts.Add(LyrisCreatorData::Slot_Outfit, *Outfit);
	}
	ApplyWholeLook(Look, true);

	const TArray<FText>& Names = LyrisCreatorData::PresetNames(Look.People);
	if (Names.IsValidIndex(Index))
	{
		ShowStatus(FText::Format(LOCTEXT("PresetLoaded", "Preset: {0}"), Names[Index]));
	}
}

void SLyrisCharacterCreator::ResetSection()
{
	ULyrisAppearanceComponent* Appearance = Comp();
	if (!Appearance || !Catalog())
	{
		return;
	}
	RecordChange(NAME_None);

	// Sliders and amounts back to their defaults; colours keep their swatch but lose their shifts.
	// Parts are left alone (there is no "default part" in the contract, and a hairstyle is a choice).
	for (const FLyrisSliderDef& Def : LyrisCreator::SlidersIn(*Catalog(), Category, Section, CurrentPeople()))
	{
		Appearance->SetSlider(Def.Id, Def.Default);
	}
	for (const FLyrisCreatorScalarInfo& Info : LyrisCreatorData::Scalars())
	{
		if (Info.Category == Category && Info.Section == Section && !Info.bToggle)
		{
			Appearance->SetPartScalar(Info.Key, Info.Default);
		}
	}
	for (const FLyrisColorChannelDef& Channel : Catalog()->ColorChannels)
	{
		if (Channel.Category == Category && LyrisCreatorData::SectionForChannel(Channel.Id) == Section)
		{
			FLyrisColorPick Pick = GetColor(Channel.Id);
			Pick.HueShift = 0.f;
			Pick.ValueShift = 0.f;
			Appearance->SetColor(Channel.Id, Pick);
		}
	}
	ShowStatus(FText::Format(LOCTEXT("SectionReset", "{0} reset."), LyrisCreatorData::SectionName(Category, Section)));
}

void SLyrisCharacterCreator::CopyShareCode()
{
	const FString Code = ULyrisAppearanceLibrary::ToShareCode(CurrentLook());
	FPlatformApplicationMisc::ClipboardCopy(*Code);
	ShowStatus(LOCTEXT("Copied", "Share code copied. It carries your looks only, never your name or path."));
}

void SLyrisCharacterCreator::PasteShareCode()
{
	FString Text;
	FPlatformApplicationMisc::ClipboardPaste(Text);
	Text.TrimStartAndEndInline();

	FLyrisAppearance Imported;
	if (Text.IsEmpty() || !ULyrisAppearanceLibrary::FromShareCode(Text, Imported))
	{
		ShowStatus(LOCTEXT("BadCode", "That doesn't look like a Lyris share code (they start with LYR1:)."), true);
		return;
	}

	const FName People = CurrentPeople();
	if (Imported.People != People)
	{
		// Spec 9.9: ask before switching People.
		const FLyrisCreatorCard* Card = FindCard(LyrisCreatorData::Peoples(), Imported.People);
		const FText PeopleName = Card ? Card->Title : FText::FromName(Imported.People);
		ShowPrompt(FText::Format(LOCTEXT("SwitchQ", "This look belongs to a {0}. Switch to {0} to use it?"), PeopleName), {
			{ FText::Format(LOCTEXT("SwitchYes", "Switch to {0}"), PeopleName), [this, Imported]()
				{
					ApplyWholeLook(Imported, true);
					ShowStatus(LOCTEXT("Imported", "Look imported."));
				} },
			{ LOCTEXT("SwitchNo", "Keep my People"), [this, Imported, People]()
				{
					FLyrisAppearance Kept = Imported;
					Kept.People = People;
					ApplyWholeLook(Kept, true);
					ShowStatus(LOCTEXT("ImportedKept", "Look imported. Options only another People can wear were left out."));
				} },
		});
		return;
	}
	ApplyWholeLook(Imported, true);
	ShowStatus(LOCTEXT("Imported2", "Look imported. Ctrl+Z to undo."));
}

void SLyrisCharacterCreator::SetSymmetry(bool bOn)
{
	if (bOn == bSymmetry)
	{
		return;
	}
	bSymmetry = bOn;
	if (bOn)
	{
		// Spec 9.2: turning symmetry back on asks how to reconcile the two sides.
		ShowPrompt(LOCTEXT("SymQ", "Make both sides match?"), {
			{ LOCTEXT("SymLR", "Copy left to right"), [this]() { MirrorAll(true); } },
			{ LOCTEXT("SymRL", "Copy right to left"), [this]() { MirrorAll(false); } },
			{ LOCTEXT("SymKeep", "Keep as is"), []() {} },
		});
	}
}

void SLyrisCharacterCreator::MirrorAll(bool bLeftToRight)
{
	ULyrisAppearanceComponent* Appearance = Comp();
	if (!Appearance || !Catalog())
	{
		return;
	}
	RecordChange(NAME_None);
	for (const FLyrisSliderDef& Def : Catalog()->Sliders)
	{
		if (Def.MirrorOf.IsNone() || IsLeftId(Def.Id) != bLeftToRight)
		{
			continue;
		}
		const FLyrisSliderDef* Mirror = FindSliderDef(Def.MirrorOf);
		const float Value = GetSliderValue(Def);
		Appearance->SetSlider(Def.MirrorOf, Mirror ? FMath::Clamp(Value, Mirror->Min, Mirror->Max) : Value);
	}
}

void SLyrisCharacterCreator::BeginCompare()
{
	ULyrisAppearanceComponent* Appearance = Comp();
	if (!Appearance || bComparing)
	{
		return;
	}
	// Show the look from when you entered this category, without touching history.
	LookBeforeCompare = CurrentLook();
	bComparing = true;
	Appearance->SetAppearance(CompareSnapshot);
}

void SLyrisCharacterCreator::EndCompare()
{
	ULyrisAppearanceComponent* Appearance = Comp();
	if (!bComparing)
	{
		return;
	}
	bComparing = false;
	if (Appearance)
	{
		Appearance->SetAppearance(LookBeforeCompare);
	}
}

void SLyrisCharacterCreator::SetLighting(ELyrisCreatorLighting InLighting)
{
	Lighting = InLighting;
	if (ALyrisCreatorStage* StagePtr = Stage.Get())
	{
		StagePtr->SetLightingPreset(Lighting);
	}
}

void SLyrisCharacterCreator::CycleExpression()
{
	const TArray<TPair<FName, FText>>& List = LyrisCreatorData::Expressions();
	ExpressionIndex = (ExpressionIndex + 1) % List.Num();
	if (ALyrisCreatorStage* StagePtr = Stage.Get())
	{
		StagePtr->PreviewExpression(List[ExpressionIndex].Key);
	}
	ShowStatus(FText::Format(LOCTEXT("ExprNow", "Expression: {0}"), List[ExpressionIndex].Value));
}

void SLyrisCharacterCreator::CyclePose()
{
	const TArray<TPair<FName, FText>>& List = LyrisCreatorData::Poses();
	PoseIndex = (PoseIndex + 1) % List.Num();
	if (ALyrisCreatorStage* StagePtr = Stage.Get())
	{
		StagePtr->PreviewPose(List[PoseIndex].Key);
	}
	ShowStatus(FText::Format(LOCTEXT("PoseNow", "Pose: {0}"), List[PoseIndex].Value));
}

// =====================================================================================================
// 6. Face sculpting
// =====================================================================================================

void SLyrisCharacterCreator::OnSculptBegin(FName Region)
{
	BeginDrag();
	SculptValues.Reset();
}

void SLyrisCharacterCreator::OnSculptDrag(FName Region, float DeltaX, float DeltaY, float HorizontalSign)
{
	if (!Catalog())
	{
		return;
	}
	const FName People = CurrentPeople();
	for (const FLyrisSliderDef& Def : Catalog()->Sliders)
	{
		if (Def.SculptRegion != Region || !LyrisCreator::AllowsPeople(Def.People, People))
		{
			continue;
		}

		// SculptAxis 0 = horizontal drag (outward from the face centre grows the value),
		// 1 = vertical drag (up grows the value, except regions like the chin where down does).
		float Delta = 0.f;
		if (Def.SculptAxis == 0)
		{
			Delta = DeltaX * HorizontalSign;
		}
		else
		{
			Delta = IsDownPositiveRegion(Region) ? DeltaY : -DeltaY;
		}
		if (FMath::IsNearlyZero(Delta))
		{
			continue;
		}

		// Accumulate in our own copy so tiny deltas never get lost to rounding in the component.
		float& Running = SculptValues.FindOrAdd(Def.Id, GetSliderValue(Def));
		Running = FMath::Clamp(Running + Delta * (Def.Max - Def.Min) / SculptFullRangeUnits, Def.Min, Def.Max);
		SetSliderValue(Def, Running);
	}
}

void SLyrisCharacterCreator::OnSculptEnd()
{
	EndDrag();
	SculptValues.Reset();
}

void SLyrisCharacterCreator::OnSculptReset(FName Region)
{
	if (!Catalog())
	{
		return;
	}
	RecordChange(NAME_None);
	for (const FLyrisSliderDef& Def : Catalog()->Sliders)
	{
		if (Def.SculptRegion == Region)
		{
			SetSliderValue(Def, Def.Default);
		}
	}
	ShowStatus(FText::Format(LOCTEXT("RegionReset", "{0} reset."), SLyrisCreatorViewport::RegionDisplayName(Region)));
}

// =====================================================================================================
// 7. Steps and navigation
// =====================================================================================================

TArray<FName> SLyrisCharacterCreator::GetCategoryList() const
{
	// Our display order first, then anything new the catalog has (except Lantern, which is step 5 only).
	TArray<FName> Out = LyrisCreatorData::Categories();
	if (Catalog())
	{
		for (const FName& Extra : LyrisCreator::Categories(*Catalog()))
		{
			if (Extra != LyrisCreatorData::Category_Lantern && !Out.Contains(Extra))
			{
				Out.Add(Extra);
			}
		}
	}
	return Out;
}

TArray<FName> SLyrisCharacterCreator::GetSectionList(FName InCategory) const
{
	TArray<FName> Out;
	for (const FLyrisCreatorSectionInfo& Info : LyrisCreatorData::Sections())
	{
		if (Info.Category == InCategory)
		{
			Out.Add(Info.Section);
		}
	}
	if (Catalog())
	{
		for (const FName& Extra : LyrisCreator::Sections(*Catalog(), InCategory))
		{
			Out.AddUnique(Extra);
		}
	}
	return Out;
}

void SLyrisCharacterCreator::SetCategory(FName InCategory)
{
	if (bComparing)
	{
		EndCompare();
	}
	Category = InCategory;
	const TArray<FName> SectionList = GetSectionList(Category);
	Section = SectionList.Num() > 0 ? SectionList[0] : NAME_None;
	// The "before" for before / after is the look as you entered this category (spec 9.7).
	CompareSnapshot = CurrentLook();
	UpdateCameraShot();
	RequestRebuild();
}

void SLyrisCharacterCreator::SetSection(FName InSection)
{
	Section = InSection;
	UpdateCameraShot();
	RequestRebuild();
}

void SLyrisCharacterCreator::CycleCategory(int32 Direction)
{
	const TArray<FName> List = GetCategoryList();
	if (List.Num() == 0)
	{
		return;
	}
	const int32 Current = FMath::Max(0, List.IndexOfByKey(Category));
	SetCategory(List[(Current + Direction + List.Num()) % List.Num()]);
}

void SLyrisCharacterCreator::UpdateCameraShot()
{
	ALyrisCreatorStage* StagePtr = Stage.Get();
	if (!StagePtr)
	{
		return;
	}
	ELyrisCreatorShot Shot = LyrisCreatorData::StepShot(CurrentStep());
	if (CurrentStep() == ELyrisCreatorStep::Appearance)
	{
		if (const FLyrisCreatorSectionInfo* Info = LyrisCreatorData::FindSection(Category, Section))
		{
			Shot = Info->Shot;
		}
	}
	StagePtr->SetShot(Shot);
}

bool SLyrisCharacterCreator::CanLeaveStep() const
{
	switch (CurrentStep())
	{
	case ELyrisCreatorStep::Path:    return !Profile.Path.IsNone();
	case ELyrisCreatorStep::Lantern: return !Profile.LanternShape.IsNone();
	case ELyrisCreatorStep::Name:    return false; // the step ends with "Light your lantern"
	default:                         return true;
	}
}

void SLyrisCharacterCreator::GoToStep(int32 NewStep)
{
	NewStep = FMath::Clamp(NewStep, 0, LyrisCreatorData::NumSteps() - 1);
	if (NewStep == StepIndex)
	{
		return;
	}
	// Forward only one step past the furthest reached, and only when this step is answered.
	if (NewStep > StepIndex && (NewStep > FurthestStep + 1 || (NewStep > FurthestStep && !CanLeaveStep())))
	{
		return;
	}
	if (bComparing)
	{
		EndCompare();
	}
	if (PromptBox.IsValid())
	{
		ClearPrompt();
	}

	StepIndex = NewStep;
	FurthestStep = FMath::Max(FurthestStep, StepIndex);

	if (ALyrisCreatorStage* StagePtr = Stage.Get())
	{
		// Small story beats: hold the lantern at the lantern step, otherwise stand easy.
		StagePtr->PreviewPose(CurrentStep() == ELyrisCreatorStep::Lantern ? FName(TEXT("HoldLantern")) : FName(TEXT("Idle")));
	}
	UpdateCameraShot();
	RequestRebuild();
}

void SLyrisCharacterCreator::PickPath(FName PathId)
{
	Profile.Path = PathId;

	// Each path has a starting outfit, worn by default until the player picks one themselves.
	if (!bPlayerPickedOutfit)
	{
		if (const FLyrisCreatorCard* Card = FindCard(LyrisCreatorData::Paths(), PathId))
		{
			if (!Card->DefaultPart.IsNone())
			{
				RecordChange(NAME_None);
				if (ULyrisAppearanceComponent* Appearance = Comp())
				{
					Appearance->SetPart(LyrisCreatorData::Slot_Outfit, Card->DefaultPart);
				}
			}
		}
	}

	// A backstory from another path no longer fits (spec 2: cleared with a note).
	if (!Profile.Backstory.IsNone())
	{
		const FLyrisCreatorCard* Back = FindCard(LyrisCreatorData::Backstories(), Profile.Backstory);
		if (!Back || Back->ForPath != PathId)
		{
			Profile.Backstory = NAME_None;
			ShowStatus(LOCTEXT("BackCleared", "Your backstory belonged to another path, so it was set aside."));
		}
	}
}

void SLyrisCharacterCreator::PickLantern(FName LanternId)
{
	Profile.LanternShape = LanternId;
	// TODO(Player): show the chosen lantern in the preview's hand. The lantern is not part of
	// FLyrisAppearance (share codes must not carry it), so it needs its own preview hook.
}

void SLyrisCharacterCreator::SetLanternGlass(const FLyrisColorPick& Pick)
{
	Profile.LanternGlass = Pick;
}

void SLyrisCharacterCreator::LightYourLantern()
{
	const FString Name = NameDraft.TrimStartAndEnd();
	NameError = LyrisCreatorData::ValidateName(Name);
	if (!NameError.IsEmpty())
	{
		return;
	}
	if (bComparing)
	{
		EndCompare();
	}

	Profile.Name = Name;
	Profile.Appearance = CurrentLook();

	ULyrisCharacterSaveGame* Save = Cast<ULyrisCharacterSaveGame>(
		UGameplayStatics::CreateSaveGameObject(ULyrisCharacterSaveGame::StaticClass()));
	if (!Save)
	{
		ShowStatus(LOCTEXT("SaveFail", "The ledger would not take the ink (could not create the save)."), true);
		return;
	}
	LyrisCreator::SaveProfile(*Save) = Profile;
	if (!UGameplayStatics::SaveGameToSlot(Save, LyrisCreator::SaveSlotName(), LyrisCreator::SaveUserIndex()))
	{
		ShowStatus(LOCTEXT("SaveFail2", "The ledger would not take the ink (saving failed)."), true);
		return;
	}

	// TODO(Lead T26): play the dock cut (lighting the lantern) and drop the player on the Harbor dock.
	OnRequestClose.ExecuteIfBound();
}

// =====================================================================================================
// Messages and prompts
// =====================================================================================================

void SLyrisCharacterCreator::ShowStatus(const FText& Text, bool bWarning)
{
	StatusText = Text;
	bStatusWarning = bWarning;
	StatusUntil = FPlatformTime::Seconds() + 3.5;
}

void SLyrisCharacterCreator::ShowPrompt(const FText& Question, TArray<FPromptAction> Actions)
{
	if (!PromptBox.IsValid())
	{
		return;
	}
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();

	TSharedRef<SHorizontalBox> Buttons = SNew(SHorizontalBox);
	for (const FPromptAction& Action : Actions)
	{
		TFunction<void()> Run = Action.Action;
		Buttons->AddSlot()
			.AutoWidth()
			.Padding(Style.Gap * 0.5f, 0.f)
			[
				MakeButton(Action.Label, [this, Run]()
				{
					// Copy the action out first, then clear: clearing releases this button (and the
					// lambda we are running in), and the action may open a new prompt.
					TFunction<void()> RunNow = Run;
					ClearPrompt();
					if (RunNow)
					{
						RunNow();
					}
				}, FText::GetEmpty())
			];
	}

	PromptBox->SetContent(
		SNew(SBorder)
		.BorderImage(&Style.PanelBrush)
		.Padding(FMargin(28.f, 22.f))
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			[
				SNew(SBox)
				.MaxDesiredWidth(520.f)
				[
					SNew(STextBlock)
					.Text(Question)
					.Font(Style.HeadingFont)
					.ColorAndOpacity(Style.DarkWood)
					.AutoWrapText(true)
					.Justification(ETextJustify::Center)
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			.Padding(0.f, Style.Gap * 1.5f, 0.f, 0.f)
			[
				Buttons
			]
		]);
	PromptBox->SetVisibility(EVisibility::Visible);
}

void SLyrisCharacterCreator::ClearPrompt()
{
	if (PromptBox.IsValid())
	{
		PromptBox->SetContent(SNullWidget::NullWidget);
		PromptBox->SetVisibility(EVisibility::Collapsed);
	}
}

// =====================================================================================================
// 8. Widget builders
// =====================================================================================================

void SLyrisCharacterCreator::RebuildAll()
{
	bNeedsRebuild = false;
	if (RouteBox.IsValid())
	{
		RouteBox->SetContent(BuildRoute());
	}
	if (LeftBox.IsValid())
	{
		LeftBox->SetContent(BuildLeftColumn());
	}
	if (RightBox.IsValid())
	{
		RightBox->SetContent(BuildRightPanel());
	}
	if (BottomBox.IsValid())
	{
		BottomBox->SetContent(BuildBottomBar());
	}
}

TSharedRef<SWidget> SLyrisCharacterCreator::MakeHeading(const FText& Text) const
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	return SNew(STextBlock)
		.Text(Text)
		.Font(Style.HeadingFont)
		.ColorAndOpacity(Style.DarkWood);
}

TSharedRef<SWidget> SLyrisCharacterCreator::MakeNote(const FText& Text) const
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	return SNew(STextBlock)
		.Text(Text)
		.Font(Style.SmallFont)
		.ColorAndOpacity(Style.Wood)
		.AutoWrapText(true);
}

TSharedRef<SWidget> SLyrisCharacterCreator::MakeButton(const FText& Label, TFunction<void()> OnClick, const FText& Tooltip,
	TAttribute<bool> IsEnabled)
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	return SNew(SButton)
		.ButtonStyle(&Style.ButtonStyle)
		.ToolTipText(Tooltip)
		.IsEnabled(IsEnabled)
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Center)
		.OnClicked_Lambda([OnClick]()
		{
			if (OnClick)
			{
				OnClick();
			}
			return FReply::Handled();
		})
		[
			SNew(STextBlock)
			.Text(Label)
			.Font(Style.ButtonFont)
		];
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildTile(const FText& Label, TFunction<bool()> IsSelected, TFunction<void()> OnPick,
	const FText& Tooltip)
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	return SNew(SButton)
		.ButtonStyle(&Style.OverlayButtonStyle)
		.ToolTipText(Tooltip)
		.OnClicked_Lambda([OnPick]()
		{
			if (OnPick)
			{
				OnPick();
			}
			return FReply::Handled();
		})
		[
			SNew(SBorder)
			.BorderImage_Lambda([IsSelected]()
			{
				const FLyrisCreatorStyle& S = FLyrisCreatorStyle::Get();
				return (IsSelected && IsSelected()) ? &S.TileSelectedBrush : &S.TileBrush;
			})
			.Padding(FMargin(8.f, 4.f))
			.HAlign(HAlign_Center)
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.MinDesiredHeight(Style.TileHeight)
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text(Label)
					.Font(Style.BodyFont)
					.ColorAndOpacity(Style.DarkWood)
					.AutoWrapText(true)
					.Justification(ETextJustify::Center)
				]
			]
		];
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildCard(const FText& Title, const FText& Line1, const FText& Line2,
	TFunction<bool()> IsSelected, TFunction<void()> OnPick)
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	TSharedRef<SVerticalBox> Lines = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(Title)
			.Font(Style.HeadingFont)
			.ColorAndOpacity(Style.DarkWood)
		];
	if (!Line1.IsEmpty())
	{
		Lines->AddSlot()
			.AutoHeight()
			.Padding(0.f, 4.f, 0.f, 0.f)
			[
				SNew(STextBlock)
				.Text(Line1)
				.Font(Style.BodyFont)
				.ColorAndOpacity(Style.DarkWood)
				.AutoWrapText(true)
			];
	}
	if (!Line2.IsEmpty())
	{
		Lines->AddSlot()
			.AutoHeight()
			.Padding(0.f, 2.f, 0.f, 0.f)
			[
				SNew(STextBlock)
				.Text(Line2)
				.Font(Style.SmallFont)
				.ColorAndOpacity(Style.Wood)
				.AutoWrapText(true)
			];
	}

	return SNew(SButton)
		.ButtonStyle(&Style.OverlayButtonStyle)
		.OnClicked_Lambda([OnPick]()
		{
			if (OnPick)
			{
				OnPick();
			}
			return FReply::Handled();
		})
		[
			SNew(SBorder)
			.BorderImage_Lambda([IsSelected]()
			{
				const FLyrisCreatorStyle& S = FLyrisCreatorStyle::Get();
				return (IsSelected && IsSelected()) ? &S.TileSelectedBrush : &S.TileBrush;
			})
			.Padding(FMargin(14.f, 10.f))
			[
				Lines
			]
		];
}

// ------------------------------------------------------------------------------------- Route (top bar)

TSharedRef<SWidget> SLyrisCharacterCreator::BuildRoute()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	TSharedRef<SHorizontalBox> Route = SNew(SHorizontalBox);

	for (int32 Index = 0; Index < LyrisCreatorData::NumSteps(); ++Index)
	{
		const ELyrisCreatorStep Step = static_cast<ELyrisCreatorStep>(Index);

		// Dotted rope between the lanterns.
		if (Index > 0)
		{
			Route->AddSlot()
				.AutoWidth()
				.VAlign(VAlign_Top)
				.Padding(2.f, Style.LanternMarkerSize * 0.5f - 9.f, 2.f, 0.f)
				[
					SNew(STextBlock)
					.Text(FText::FromString(TEXT("· · · ·")))
					.Font(Style.HeadingFont)
					.ColorAndOpacity_Lambda([this, Index]()
					{
						const FLyrisCreatorStyle& S = FLyrisCreatorStyle::Get();
						return FSlateColor(Index <= FurthestStep ? S.Gold : S.Wood.CopyWithNewOpacity(0.6f));
					})
				];
		}

		Route->AddSlot()
			.AutoWidth()
			[
				SNew(SButton)
				.ButtonStyle(&Style.LinkButtonStyle)
				.ToolTipText(LyrisCreatorData::StepMoment(Step))
				.IsEnabled_Lambda([this, Index]()
				{
					return Index <= FurthestStep || (Index == FurthestStep + 1 && Index == StepIndex + 1 && CanLeaveStep());
				})
				.OnClicked_Lambda([this, Index]()
				{
					GoToStep(Index);
					return FReply::Handled();
				})
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					[
						// The lantern marker: unlit ahead of you, lit where you have been, bright where you are.
						SNew(SImage)
						.Image_Lambda([this, Index]()
						{
							const FLyrisCreatorStyle& S = FLyrisCreatorStyle::Get();
							if (Index == StepIndex)
							{
								return &S.LanternCurrentBrush;
							}
							return Index <= FurthestStep ? &S.LanternLitBrush : &S.LanternUnlitBrush;
						})
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					.Padding(0.f, 3.f, 0.f, 0.f)
					[
						SNew(STextBlock)
						.Text(LyrisCreatorData::StepName(Step))
						.Font(Style.BodyFont)
						.ColorAndOpacity_Lambda([this, Index]()
						{
							const FLyrisCreatorStyle& S = FLyrisCreatorStyle::Get();
							return FSlateColor(Index == StepIndex ? S.Clay : S.Wood);
						})
					]
				]
			];
	}

	return SNew(SBorder)
		.BorderImage(&Style.PanelBrush)
		.Padding(FMargin(22.f, 10.f))
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			[
				Route
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			.Padding(0.f, 8.f, 0.f, 0.f)
			[
				SNew(STextBlock)
				.Text(LyrisCreatorData::StepName(CurrentStep()))
				.Font(Style.TitleFont)
				.ColorAndOpacity(Style.DarkWood)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			[
				SNew(STextBlock)
				.Text(LyrisCreatorData::StepMoment(CurrentStep()))
				.Font(Style.SmallFont)
				.ColorAndOpacity(Style.Wood)
			]
		];
}

// ------------------------------------------------------------------------------------- Left column

TSharedRef<SWidget> SLyrisCharacterCreator::BuildLeftColumn()
{
	if (CurrentStep() != ELyrisCreatorStep::Appearance)
	{
		return SNullWidget::NullWidget;
	}
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();

	TSharedRef<SVerticalBox> Tabs = SNew(SVerticalBox);
	for (const FName& Cat : GetCategoryList())
	{
		Tabs->AddSlot()
			.AutoHeight()
			.Padding(0.f, 2.f)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				[
					BuildTile(LyrisCreatorData::CategoryName(Cat),
						[this, Cat]() { return Category == Cat; },
						[this, Cat]() { SetCategory(Cat); },
						LOCTEXT("TabTip", "Tab / Shift+Tab to move between categories"))
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(6.f, 0.f, 0.f, 0.f)
				[
					// Padlock for randomise (spec 9.3).
					SNew(SCheckBox)
					.Style(&Style.ToggleStyle)
					.ToolTipText(LOCTEXT("LockTip", "Lock: Randomise leaves this category alone"))
					.IsChecked_Lambda([this, Cat]()
					{
						return LockedCategories.Contains(Cat) ? ECheckBoxState::Checked : ECheckBoxState::Unchecked;
					})
					.OnCheckStateChanged_Lambda([this, Cat](ECheckBoxState NewState)
					{
						if (NewState == ECheckBoxState::Checked)
						{
							LockedCategories.Add(Cat);
						}
						else
						{
							LockedCategories.Remove(Cat);
						}
					})
					[
						SNew(STextBlock)
						.Text_Lambda([this, Cat]()
						{
							return LockedCategories.Contains(Cat) ? LOCTEXT("Locked", "Locked") : LOCTEXT("Lock", "Lock");
						})
						.Font(Style.SmallFont)
						.ColorAndOpacity(Style.DarkWood)
					]
				]
			];
	}

	TSharedRef<SVerticalBox> Sections = SNew(SVerticalBox);
	for (const FName& Sec : GetSectionList(Category))
	{
		Sections->AddSlot()
			.AutoHeight()
			.Padding(0.f, 2.f)
			[
				BuildTile(LyrisCreatorData::SectionName(Category, Sec),
					[this, Sec]() { return Section == Sec; },
					[this, Sec]() { SetSection(Sec); },
					FText::GetEmpty())
			];
	}

	return SNew(SBorder)
		.BorderImage(&Style.PanelBrush)
		.Padding(Style.PanelPadding)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()[ MakeHeading(LOCTEXT("Looks", "Looks")) ]
				+ SVerticalBox::Slot().AutoHeight().Padding(0.f, Style.Gap * 0.5f)[ Tabs ]
				+ SVerticalBox::Slot().AutoHeight().Padding(0.f, Style.Gap, 0.f, 4.f)
				[
					// Thin ink rule between the tabs and the sections.
					SNew(SBox)
					.HeightOverride(1.f)
					[
						SNew(SImage)
						.Image(&Style.InkLineBrush)
					]
				]
				+ SVerticalBox::Slot().AutoHeight()[ MakeHeading(LyrisCreatorData::CategoryName(Category)) ]
				+ SVerticalBox::Slot().AutoHeight().Padding(0.f, Style.Gap * 0.5f)[ Sections ]
				+ SVerticalBox::Slot().AutoHeight().Padding(0.f, Style.Gap)
				[
					MakeNote(Category == TEXT("Face")
						? LOCTEXT("SculptHint", "Hover the face and drag to sculpt. Right-click a feature to reset it. Drag elsewhere to turn, scroll to zoom.")
						: LOCTEXT("OrbitHint", "Drag the view to turn, scroll to zoom."))
				]
			]
		];
}

// ------------------------------------------------------------------------------------- Right panel

TSharedRef<SWidget> SLyrisCharacterCreator::BuildRightPanel()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();

	TSharedRef<SWidget> Content = SNullWidget::NullWidget;
	switch (CurrentStep())
	{
	case ELyrisCreatorStep::People:     Content = BuildPeopleStep(); break;
	case ELyrisCreatorStep::Appearance: Content = BuildAppearanceSection(); break;
	case ELyrisCreatorStep::Path:       Content = BuildPathStep(); break;
	case ELyrisCreatorStep::Backstory:  Content = BuildBackstoryStep(); break;
	case ELyrisCreatorStep::Lantern:    Content = BuildLanternStep(); break;
	case ELyrisCreatorStep::Name:       Content = BuildNameStep(); break;
	default: break;
	}

	return SNew(SBorder)
		.BorderImage(&Style.PanelBrush)
		.Padding(Style.PanelPadding)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				Content
			]
		];
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildPresetRow()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	TSharedRef<SUniformGridPanel> Grid = SNew(SUniformGridPanel).SlotPadding(FMargin(3.f));
	const TArray<FText>& Names = LyrisCreatorData::PresetNames(CurrentPeople());
	for (int32 Index = 0; Index < Names.Num(); ++Index)
	{
		Grid->AddSlot(Index % Style.TileColumns, Index / Style.TileColumns)
		[
			BuildTile(Names[Index], []() { return false; }, [this, Index]() { ApplyPreset(Index); },
				LOCTEXT("PresetTip", "Load this ready-made look (Ctrl+Z to undo)"))
		];
	}

	return SNew(SBox)
		.Visibility_Lambda([this]() { return bShowPresets ? EVisibility::Visible : EVisibility::Collapsed; })
		.Padding(FMargin(0.f, 0.f, 0.f, Style.Gap))
		[
			SNew(SBorder)
			.BorderImage(&Style.SubPanelBrush)
			.Padding(FMargin(10.f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()[ MakeHeading(LOCTEXT("Presets", "Presets")) ]
				+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 6.f, 0.f, 0.f)[ Grid ]
			]
		];
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildAppearanceSection()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	const FName People = CurrentPeople();
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	int32 Rows = 0;

	Box->AddSlot().AutoHeight()[ BuildPresetRow() ];
	Box->AddSlot()
		.AutoHeight()
		.Padding(0.f, 0.f, 0.f, Style.Gap)
		[
			MakeHeading(FText::Format(LOCTEXT("SecHeading", "{0}: {1}"),
				LyrisCreatorData::CategoryName(Category), LyrisCreatorData::SectionName(Category, Section)))
		];

	// Body frame: two cosmetic body shapes, not gendered (spec section 1).
	if (Category == TEXT("Body") && Section == TEXT("Frame"))
	{
		Box->AddSlot()
			.AutoHeight()
			.Padding(0.f, 0.f, 0.f, Style.Gap)
			[
				SNew(SUniformGridPanel)
				.SlotPadding(FMargin(3.f))
				+ SUniformGridPanel::Slot(0, 0)
				[
					BuildTile(LOCTEXT("Willow", "Willow: narrower, lighter"),
						[this]() { return CurrentLook().Frame == LyrisCreatorData::Frame_A; },
						[this]() { SetFrame(LyrisCreatorData::Frame_A); }, FText::GetEmpty())
				]
				+ SUniformGridPanel::Slot(1, 0)
				[
					BuildTile(LOCTEXT("Oak", "Oak: broader, sturdier"),
						[this]() { return CurrentLook().Frame == LyrisCreatorData::Frame_B; },
						[this]() { SetFrame(LyrisCreatorData::Frame_B); }, FText::GetEmpty())
				]
			];
		++Rows;
	}

	// 1. Sliders from the catalog.
	if (Catalog())
	{
		for (const FLyrisSliderDef& Def : LyrisCreator::SlidersIn(*Catalog(), Category, Section, People))
		{
			Box->AddSlot().AutoHeight().Padding(0.f, 2.f)[ BuildSliderRow(Def) ];
			++Rows;
		}
	}

	// 2. Part grids for the slots that live here.
	for (const FLyrisCreatorSlotInfo& Slot : LyrisCreatorData::Slots())
	{
		if (Slot.Category == Category && Slot.Section == Section)
		{
			Box->AddSlot().AutoHeight().Padding(0.f, Style.Gap * 0.5f)[ BuildPartGrid(Slot) ];
			++Rows;
		}
	}

	// 3. Part amounts and toggles (heterochromia, match hair).
	for (const FLyrisCreatorScalarInfo& Info : LyrisCreatorData::Scalars())
	{
		if (Info.Category == Category && Info.Section == Section && LyrisCreator::AllowsPeople(Info.People, People))
		{
			Box->AddSlot().AutoHeight().Padding(0.f, 2.f)[ BuildScalarRow(Info) ];
			++Rows;
		}
	}

	// 4. Colour channels. Channels the layout table does not know go to this category's first section.
	if (Catalog())
	{
		const TArray<FName> SectionList = GetSectionList(Category);
		const FName FirstSection = SectionList.Num() > 0 ? SectionList[0] : NAME_None;
		for (const FLyrisColorChannelDef& Channel : Catalog()->ColorChannels)
		{
			if (Channel.Category != Category || !LyrisCreator::AllowsPeople(Channel.People, People))
			{
				continue;
			}
			FName ChannelSection = LyrisCreatorData::SectionForChannel(Channel.Id);
			if (ChannelSection.IsNone())
			{
				ChannelSection = FirstSection;
			}
			if (ChannelSection != Section)
			{
				continue;
			}

			const FName Id = Channel.Id;
			Box->AddSlot()
				.AutoHeight()
				.Padding(0.f, Style.Gap * 0.5f)
				[
					SNew(SBox)
					.Visibility_Lambda([this, Id]()
					{
						// Hidden while another control decides this colour (spec 3.3 and 3.7).
						if (Id == LyrisCreatorData::Channel_IrisR && GetScalar(LyrisCreatorData::Scalar_Heterochromia) < 0.5f)
						{
							return EVisibility::Collapsed;
						}
						if (Id == LyrisCreatorData::Channel_HairBrows && GetScalar(LyrisCreatorData::Scalar_BrowsMatchHair) >= 0.5f)
						{
							return EVisibility::Collapsed;
						}
						if (Id == LyrisCreatorData::Channel_HairFacialHair && GetScalar(LyrisCreatorData::Scalar_FacialHairMatchHair) >= 0.5f)
						{
							return EVisibility::Collapsed;
						}
						return EVisibility::Visible;
					})
					[
						BuildColorChannel(Channel,
							[this, Id]() { return GetColor(Id); },
							[this, Id](const FLyrisColorPick& Pick) { SetColorValue(Id, Pick); },
							/*bHistory*/ true)
					]
				];
			++Rows;
		}
	}

	if (Rows == 0)
	{
		Box->AddSlot().AutoHeight()[ MakeNote(LOCTEXT("Empty", "Nothing to adjust here yet.")) ];
	}
	return Box;
}

TSharedRef<SWidget> SLyrisCharacterCreator::MakeValueRow(const FText& Label, const FText& Tooltip, float Min, float Max,
	TFunction<float()> Get, TFunction<void(float)> Set, FName HistoryKey, TFunction<void()> OnGrab)
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();

	TSharedRef<SSlider> Slider = SNew(SSlider)
		.Style(&Style.SliderStyle)
		.MinValue(Min)
		.MaxValue(Max)
		.StepSize((Max - Min) / 40.f)
		.MouseUsesStep(false)
		.IsFocusable(true)
		// Left / Right adjust a focused slider straight away (no "press A to grab" first).
		.RequiresControllerLock(false)
		.Value_Lambda([Get]() { return Get ? Get() : 0.f; })
		.OnMouseCaptureBegin_Lambda([this, HistoryKey, OnGrab]()
		{
			if (!HistoryKey.IsNone())
			{
				BeginDrag();
			}
			if (OnGrab)
			{
				OnGrab();
			}
		})
		.OnMouseCaptureEnd_Lambda([this]() { EndDrag(); })
		.OnControllerCaptureBegin_Lambda([this, HistoryKey]()
		{
			if (!HistoryKey.IsNone())
			{
				BeginDrag();
			}
		})
		.OnControllerCaptureEnd_Lambda([this]() { EndDrag(); })
		.OnValueChanged_Lambda([this, Set, HistoryKey](float NewValue)
		{
			// Keyboard nudges arrive without a capture: coalesce them per control.
			if (!HistoryKey.IsNone())
			{
				RecordChange(HistoryKey);
			}
			if (Set)
			{
				Set(NewValue);
			}
		});

	const TWeakPtr<SSlider> WeakSlider = Slider;
	return SNew(SBorder)
		.BorderImage_Lambda([WeakSlider]()
		{
			// The row the arrow keys are adjusting gets a gold outline.
			const FLyrisCreatorStyle& S = FLyrisCreatorStyle::Get();
			const TSharedPtr<SSlider> Pinned = WeakSlider.Pin();
			return (Pinned.IsValid() && Pinned->HasKeyboardFocus()) ? &S.FocusRowBrush : &S.NoBrush;
		})
		.Padding(FMargin(8.f, 4.f))
		.ToolTipText(Tooltip)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text(Label)
					.Font(Style.BodyFont)
					.ColorAndOpacity(Style.DarkWood)
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					SNew(SBox)
					.MinDesiredWidth(40.f)
					.HAlign(HAlign_Right)
					[
						SNew(STextBlock)
						.Text_Lambda([Get, Min]() { return FormatValue(Get ? Get() : 0.f, Min); })
						.Font(Style.ValueFont)
						.ColorAndOpacity(Style.Wood)
					]
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(0.f, 2.f, 0.f, 0.f)
			[
				Slider
			]
		];
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildSliderRow(const FLyrisSliderDef& Def)
{
	// Tooltip: the contract's FLyrisSliderDef has no description field, so we describe what we know.
	FString Tip = NameOr(Def.DisplayName, Def.Id).ToString();
	if (!Def.SculptRegion.IsNone())
	{
		Tip += FString::Printf(TEXT("\nSculpt it on the face: drag the %s %s."),
			*SLyrisCreatorViewport::RegionDisplayName(Def.SculptRegion).ToString().ToLower(),
			Def.SculptAxis == 0 ? TEXT("sideways") : TEXT("up or down"));
	}
	if (!Def.MirrorOf.IsNone())
	{
		const FLyrisSliderDef* Mirror = FindSliderDef(Def.MirrorOf);
		Tip += FString::Printf(TEXT("\nWith Symmetry on, %s moves with it."),
			Mirror ? *NameOr(Mirror->DisplayName, Mirror->Id).ToString() : *Def.MirrorOf.ToString());
	}

	// Ears and nose projection read best from the side (spec 2.1).
	const FString IdString = Def.Id.ToString();
	const bool bProfile = IdString.StartsWith(TEXT("Ears.")) || Def.Id == TEXT("Nose.Projection");

	const FLyrisSliderDef DefCopy = Def;
	return MakeValueRow(NameOr(Def.DisplayName, Def.Id), FText::FromString(Tip), Def.Min, Def.Max,
		[this, DefCopy]() { return GetSliderValue(DefCopy); },
		[this, DefCopy](float Value) { SetSliderValue(DefCopy, Value); },
		Def.Id,
		[this, bProfile]()
		{
			if (bProfile)
			{
				if (ALyrisCreatorStage* StagePtr = Stage.Get())
				{
					StagePtr->LookAtProfile();
				}
			}
		});
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildScalarRow(const FLyrisCreatorScalarInfo& Info)
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	const FName Key = Info.Key;

	if (Info.bToggle)
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(8.f, 4.f)
			[
				SNew(SCheckBox)
				.Style(&Style.ToggleStyle)
				.ToolTipText(Info.Tooltip)
				.IsChecked_Lambda([this, Key]()
				{
					return GetScalar(Key) >= 0.5f ? ECheckBoxState::Checked : ECheckBoxState::Unchecked;
				})
				.OnCheckStateChanged_Lambda([this, Key](ECheckBoxState NewState)
				{
					RecordChange(NAME_None);
					SetScalarValue(Key, NewState == ECheckBoxState::Checked ? 1.f : 0.f);
				})
				[
					SNew(STextBlock)
					.Text(Info.DisplayName)
					.Font(Style.BodyFont)
					.ColorAndOpacity(Style.DarkWood)
				]
			];
	}

	return MakeValueRow(Info.DisplayName, Info.Tooltip, Info.Min, Info.Max,
		[this, Key]() { return GetScalar(Key); },
		[this, Key](float Value) { SetScalarValue(Key, Value); },
		Key, nullptr);
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildPartGrid(const FLyrisCreatorSlotInfo& SlotInfo)
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	const FName Slot = SlotInfo.Slot;

	TArray<FLyrisPartDef> Parts;
	if (Catalog())
	{
		Parts = LyrisCreator::PartsForSlot(*Catalog(), Slot, CurrentPeople());
	}
	if (Parts.Num() == 0)
	{
		return SNullWidget::NullWidget;
	}

	TSharedRef<SUniformGridPanel> Grid = SNew(SUniformGridPanel).SlotPadding(FMargin(3.f));
	int32 Index = 0;
	if (SlotInfo.bOptional)
	{
		Grid->AddSlot(0, 0)
		[
			BuildTile(LOCTEXT("NonePart", "None"),
				[this, Slot]() { const FName Current = GetPart(Slot); return Current.IsNone() || Current == TEXT("None"); },
				[this, Slot]() { RecordChange(NAME_None); SetPartValue(Slot, NAME_None); },
				FText::GetEmpty())
		];
		++Index;
	}
	for (const FLyrisPartDef& Part : Parts)
	{
		const FName PartId = Part.Id;
		Grid->AddSlot(Index % Style.TileColumns, Index / Style.TileColumns)
		[
			BuildTile(NameOr(Part.DisplayName, Part.Id),
				[this, Slot, PartId]() { return GetPart(Slot) == PartId; },
				[this, Slot, PartId]() { RecordChange(NAME_None); SetPartValue(Slot, PartId); },
				NameOr(Part.DisplayName, Part.Id))
		];
		++Index;
	}

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(0.f, 0.f, 0.f, 4.f)
		[
			SNew(STextBlock)
			.Text(SlotInfo.DisplayName)
			.Font(Style.ButtonFont)
			.ColorAndOpacity(Style.DarkWood)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			Grid
		];
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildMiniSlider(const FText& Label, float Min, float Max, TFunction<float()> Get,
	TFunction<void(float)> Set, const FText& Tooltip, FName HistoryKey)
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	return SNew(SHorizontalBox)
		.ToolTipText(Tooltip)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(0.f, 0.f, 6.f, 0.f)
		[
			SNew(SBox)
			.MinDesiredWidth(56.f)
			[
				SNew(STextBlock)
				.Text(Label)
				.Font(Style.SmallFont)
				.ColorAndOpacity(Style.Wood)
			]
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.f)
		.VAlign(VAlign_Center)
		[
			SNew(SSlider)
			.Style(&Style.SliderStyle)
			.MinValue(Min)
			.MaxValue(Max)
			.StepSize((Max - Min) / 20.f)
			.MouseUsesStep(false)
			.Value_Lambda([Get]() { return Get ? Get() : 0.f; })
			.OnMouseCaptureBegin_Lambda([this, HistoryKey]() { if (!HistoryKey.IsNone()) { BeginDrag(); } })
			.OnMouseCaptureEnd_Lambda([this]() { EndDrag(); })
			.OnControllerCaptureBegin_Lambda([this, HistoryKey]() { if (!HistoryKey.IsNone()) { BeginDrag(); } })
			.OnControllerCaptureEnd_Lambda([this]() { EndDrag(); })
			.OnValueChanged_Lambda([this, Set, HistoryKey](float NewValue)
			{
				if (!HistoryKey.IsNone())
				{
					RecordChange(HistoryKey);
				}
				if (Set)
				{
					Set(NewValue);
				}
			})
		];
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildColorChannel(const FLyrisColorChannelDef& Channel,
	TFunction<FLyrisColorPick()> GetPick, TFunction<void(const FLyrisColorPick&)> SetPick, bool bHistory)
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	const FLyrisColorChannelDef ChannelCopy = Channel;
	const FName HistoryKey = bHistory ? Channel.Id : NAME_None;

	// Swatch row: the curated band for this channel.
	TSharedRef<SUniformGridPanel> Swatches = SNew(SUniformGridPanel).SlotPadding(FMargin(2.f));
	for (int32 Index = 0; Index < Channel.Swatches.Num(); ++Index)
	{
		const FLyrisSwatch& Swatch = Channel.Swatches[Index];
		const float RingSize = Style.SwatchSize + 8.f;
		Swatches->AddSlot(Index % Style.SwatchColumns, Index / Style.SwatchColumns)
		[
			SNew(SButton)
			.ButtonStyle(&Style.OverlayButtonStyle)
			.ToolTipText(Swatch.DisplayName)
			.ContentPadding(FMargin(0.f))
			.OnClicked_Lambda([this, GetPick, SetPick, Index, HistoryKey]()
			{
				if (!HistoryKey.IsNone())
				{
					RecordChange(HistoryKey); // clicking through a row of swatches is one undo step
				}
				FLyrisColorPick Pick = GetPick ? GetPick() : FLyrisColorPick();
				Pick.Swatch = Index;
				if (SetPick)
				{
					SetPick(Pick);
				}
				return FReply::Handled();
			})
			[
				SNew(SBox)
				.WidthOverride(RingSize)
				.HeightOverride(RingSize)
				[
					SNew(SOverlay)
					+ SOverlay::Slot()
					.HAlign(HAlign_Center)
					.VAlign(VAlign_Center)
					[
						SNew(SImage)
						.Image(&Style.SwatchBrush)
						.ColorAndOpacity(FSlateColor(Swatch.Color))
					]
					+ SOverlay::Slot()
					.HAlign(HAlign_Center)
					.VAlign(VAlign_Center)
					[
						SNew(SImage)
						.Image(&Style.SwatchRingBrush)
						.Visibility_Lambda([GetPick, Index]()
						{
							return (GetPick && GetPick().Swatch == Index) ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
						})
					]
				]
			]
		];
	}

	return SNew(SBorder)
		.BorderImage(&Style.SubPanelBrush)
		.Padding(FMargin(10.f, 8.f))
		[
			SNew(SVerticalBox)

			// Name, the chosen swatch's name and the resolved colour.
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text(NameOr(Channel.DisplayName, Channel.Id))
					.Font(Style.ButtonFont)
					.ColorAndOpacity(Style.DarkWood)
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(0.f, 0.f, 8.f, 0.f)
				[
					SNew(STextBlock)
					.Font(Style.SmallFont)
					.ColorAndOpacity(Style.Wood)
					.Text_Lambda([ChannelCopy, GetPick]()
					{
						const int32 Index = GetPick ? GetPick().Swatch : 0;
						return ChannelCopy.Swatches.IsValidIndex(Index) ? ChannelCopy.Swatches[Index].DisplayName : FText::GetEmpty();
					})
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					SNew(SImage)
					.Image(&Style.SwatchBrush)
					.ColorAndOpacity_Lambda([ChannelCopy, GetPick]()
					{
						return FSlateColor(ULyrisAppearanceLibrary::ResolveColor(ChannelCopy, GetPick ? GetPick() : FLyrisColorPick()));
					})
				]
			]

			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(0.f, 6.f)
			[
				Swatches
			]

			// Small shifts inside the band (the concept's "hue-shifted palettes").
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				BuildMiniSlider(LOCTEXT("Hue", "Hue"), -Channel.MaxHueShift, Channel.MaxHueShift,
					[GetPick]() { return GetPick ? GetPick().HueShift : 0.f; },
					[GetPick, SetPick](float Value)
					{
						FLyrisColorPick Pick = GetPick ? GetPick() : FLyrisColorPick();
						Pick.HueShift = Value;
						if (SetPick)
						{
							SetPick(Pick);
						}
					},
					LOCTEXT("HueTip", "Nudge the hue a little, staying inside this palette"), HistoryKey)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(0.f, 2.f, 0.f, 0.f)
			[
				BuildMiniSlider(LOCTEXT("Light", "Light"), -Channel.MaxValueShift, Channel.MaxValueShift,
					[GetPick]() { return GetPick ? GetPick().ValueShift : 0.f; },
					[GetPick, SetPick](float Value)
					{
						FLyrisColorPick Pick = GetPick ? GetPick() : FLyrisColorPick();
						Pick.ValueShift = Value;
						if (SetPick)
						{
							SetPick(Pick);
						}
					},
					LOCTEXT("LightTip", "Make it a little darker or lighter"), HistoryKey)
			]
		];
}

// ------------------------------------------------------------------------------------- Picker steps

TSharedRef<SWidget> SLyrisCharacterCreator::BuildPeopleStep()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	Box->AddSlot().AutoHeight()[ MakeHeading(LOCTEXT("HailFrom", "Where do you hail from?")) ];
	Box->AddSlot().AutoHeight().Padding(0.f, 4.f, 0.f, Style.Gap)
	[
		MakeNote(LOCTEXT("PeopleNote", "Peoples differ in look only. Every option works on both frames."))
	];

	for (const FLyrisCreatorCard& Card : LyrisCreatorData::Peoples())
	{
		const FName Id = Card.Id;
		Box->AddSlot()
			.AutoHeight()
			.Padding(0.f, 3.f)
			[
				BuildCard(Card.Title, Card.Line1, Card.Line2,
					[this, Id]() { return CurrentPeople() == Id; },
					[this, Id]() { SetPeople(Id); })
			];
	}

	Box->AddSlot().AutoHeight().Padding(0.f, Style.Gap * 1.5f, 0.f, 4.f)[ MakeHeading(LOCTEXT("Frame", "Frame")) ];
	Box->AddSlot()
		.AutoHeight()
		[
			SNew(SUniformGridPanel)
			.SlotPadding(FMargin(3.f))
			+ SUniformGridPanel::Slot(0, 0)
			[
				BuildTile(LOCTEXT("Willow2", "Willow: narrower, lighter"),
					[this]() { return CurrentLook().Frame == LyrisCreatorData::Frame_A; },
					[this]() { SetFrame(LyrisCreatorData::Frame_A); }, FText::GetEmpty())
			]
			+ SUniformGridPanel::Slot(1, 0)
			[
				BuildTile(LOCTEXT("Oak2", "Oak: broader, sturdier"),
					[this]() { return CurrentLook().Frame == LyrisCreatorData::Frame_B; },
					[this]() { SetFrame(LyrisCreatorData::Frame_B); }, FText::GetEmpty())
			]
		];
	Box->AddSlot().AutoHeight().Padding(0.f, Style.Gap)
	[
		MakeNote(LOCTEXT("NeverLocked", "Looks are never locked: the barber, the tailor and your mirror can change them later."))
	];
	return Box;
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildPathStep()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	Box->AddSlot().AutoHeight()[ MakeHeading(LOCTEXT("PathQ", "What's in your sea chest?")) ];
	Box->AddSlot().AutoHeight().Padding(0.f, 4.f, 0.f, Style.Gap)
	[
		MakeNote(LOCTEXT("PathNote", "A head start, not a fence: any path can reach any branch, and you can swap later."))
	];
	for (const FLyrisCreatorCard& Card : LyrisCreatorData::Paths())
	{
		const FName Id = Card.Id;
		Box->AddSlot()
			.AutoHeight()
			.Padding(0.f, 3.f)
			[
				BuildCard(Card.Title, Card.Line1,
					FText::Format(LOCTEXT("LeadsTo", "Leads to: {0}"), Card.Line2),
					[this, Id]() { return Profile.Path == Id; },
					[this, Id]() { PickPath(Id); })
			];
	}
	return Box;
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildBackstoryStep()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	Box->AddSlot().AutoHeight()[ MakeHeading(LOCTEXT("BackQ", "What brought you here?")) ];
	Box->AddSlot().AutoHeight().Padding(0.f, 4.f, 0.f, Style.Gap)
	[
		MakeNote(LOCTEXT("BackNote", "Optional. A backstory adds flavour dialogue and a personal quest."))
	];
	for (const FLyrisCreatorCard& Card : LyrisCreatorData::Backstories())
	{
		if (Card.ForPath != Profile.Path)
		{
			continue;
		}
		const FName Id = Card.Id;
		Box->AddSlot()
			.AutoHeight()
			.Padding(0.f, 3.f)
			[
				BuildCard(Card.Title, Card.Line1, FText::GetEmpty(),
					[this, Id]() { return Profile.Backstory == Id; },
					[this, Id]() { Profile.Backstory = Id; })
			];
	}
	Box->AddSlot()
		.AutoHeight()
		.Padding(0.f, 3.f)
		[
			BuildCard(LOCTEXT("KeepIt", "Keep it to myself"), LOCTEXT("KeepIt1", "No backstory. You can still find your own story."),
				FText::GetEmpty(),
				[this]() { return Profile.Backstory.IsNone(); },
				[this]() { Profile.Backstory = NAME_None; })
		];
	return Box;
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildLanternStep()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	Box->AddSlot().AutoHeight()[ MakeHeading(LOCTEXT("LanternQ", "Your lantern")) ];
	Box->AddSlot().AutoHeight().Padding(0.f, 4.f, 0.f, Style.Gap)
	[
		MakeNote(LOCTEXT("LanternNote", "Your first treasure. More shapes and glass are found and made later."))
	];

	TSharedRef<SUniformGridPanel> Grid = SNew(SUniformGridPanel).SlotPadding(FMargin(3.f));
	int32 Index = 0;
	for (const FLyrisCreatorCard& Card : LyrisCreatorData::Lanterns())
	{
		const FName Id = Card.Id;
		Grid->AddSlot(Index % Style.TileColumns, Index / Style.TileColumns)
		[
			BuildTile(Card.Title, [this, Id]() { return Profile.LanternShape == Id; }, [this, Id]() { PickLantern(Id); }, Card.Line1)
		];
		++Index;
	}
	Box->AddSlot().AutoHeight()[ Grid ];

	// Glass colour: the catalog's Lantern.Glass channel, or the spec's band if the catalog has none.
	const FLyrisColorChannelDef* Found = FindChannelDef(LyrisCreatorData::Channel_LanternGlass);
	const FLyrisColorChannelDef Glass = Found ? *Found : LyrisCreatorData::FallbackLanternGlass();

	Box->AddSlot()
		.AutoHeight()
		.Padding(0.f, Style.Gap * 1.5f, 0.f, 0.f)
		[
			BuildColorChannel(Glass,
				[this]() { return Profile.LanternGlass; },
				[this](const FLyrisColorPick& Pick) { SetLanternGlass(Pick); },
				/*bHistory*/ false)
		];

	// Lit preview of the glass.
	Box->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(0.f, Style.Gap * 1.5f)
		[
			SNew(SImage)
			.Image(&Style.BigSwatchBrush)
			.ColorAndOpacity_Lambda([this, Glass]()
			{
				return FSlateColor(ULyrisAppearanceLibrary::ResolveColor(Glass, Profile.LanternGlass));
			})
		];
	return Box;
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildSummary()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();

	auto Title = [](const TArray<FLyrisCreatorCard>& Cards, FName Id, const FText& IfNone)
	{
		const FLyrisCreatorCard* Card = FindCard(Cards, Id);
		return Card ? Card->Title : IfNone;
	};
	const FText None = LOCTEXT("SumNone", "None");

	TSharedRef<SVerticalBox> Lines = SNew(SVerticalBox);
	auto AddLine = [&Lines, &Style](const FText& Label, const FText& Value)
	{
		Lines->AddSlot()
			.AutoHeight()
			.Padding(0.f, 2.f)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SBox)
					.MinDesiredWidth(110.f)
					[
						SNew(STextBlock).Text(Label).Font(Style.SmallFont).ColorAndOpacity(Style.Wood)
					]
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				[
					SNew(STextBlock).Text(Value).Font(Style.BodyFont).ColorAndOpacity(Style.DarkWood)
				]
			];
	};
	AddLine(LOCTEXT("SumPeople", "People"), Title(LyrisCreatorData::Peoples(), CurrentPeople(), None));
	AddLine(LOCTEXT("SumPath", "Path"), Title(LyrisCreatorData::Paths(), Profile.Path, None));
	AddLine(LOCTEXT("SumBack", "Backstory"), Title(LyrisCreatorData::Backstories(), Profile.Backstory, LOCTEXT("SumKept", "Kept to yourself")));
	AddLine(LOCTEXT("SumLantern", "Lantern"), Title(LyrisCreatorData::Lanterns(), Profile.LanternShape, None));

	return SNew(SBorder)
		.BorderImage(&Style.SubPanelBrush)
		.Padding(FMargin(12.f, 10.f))
		[
			Lines
		];
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildNameStep()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	NameError = LyrisCreatorData::ValidateName(NameDraft);

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot().AutoHeight()[ MakeHeading(LOCTEXT("LedgerQ", "The harbourmaster's ledger")) ]
		+ SVerticalBox::Slot().AutoHeight().Padding(0.f, 4.f, 0.f, Style.Gap)
		[
			MakeNote(LOCTEXT("LedgerNote", "\"And what name shall I write, traveller?\""))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SEditableTextBox)
			.Style(&Style.TextBoxStyle)
			.Font(Style.HeadingFont)
			.HintText(LOCTEXT("NameHint", "Your name"))
			.Text_Lambda([this]() { return FText::FromString(NameDraft); })
			.OnTextChanged_Lambda([this](const FText& NewText)
			{
				NameDraft = NewText.ToString();
				NameError = LyrisCreatorData::ValidateName(NameDraft);
			})
			.OnTextCommitted_Lambda([this](const FText& NewText, ETextCommit::Type CommitType)
			{
				NameDraft = NewText.ToString();
				NameError = LyrisCreatorData::ValidateName(NameDraft);
				if (CommitType == ETextCommit::OnEnter && NameError.IsEmpty())
				{
					LightYourLantern();
				}
			})
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(0.f, 4.f)
		[
			SNew(STextBlock)
			.Font(Style.SmallFont)
			.ColorAndOpacity(Style.RedBand)
			.AutoWrapText(true)
			.Text_Lambda([this]() { return NameDraft.IsEmpty() ? FText::GetEmpty() : NameError; })
		]
		+ SVerticalBox::Slot().AutoHeight().Padding(0.f, Style.Gap)[ BuildSummary() ]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(0.f, Style.Gap)
		[
			MakeButton(LOCTEXT("LightLantern", "Light your lantern"), [this]() { LightYourLantern(); },
				LOCTEXT("LightLanternTip", "Sign the ledger and step onto the dock"),
				TAttribute<bool>::CreateLambda([this]() { return LyrisCreatorData::ValidateName(NameDraft).IsEmpty(); }))
		];
}

// ------------------------------------------------------------------------------------- Bottom bar

TSharedRef<SWidget> SLyrisCharacterCreator::MakeLightingChip(ELyrisCreatorLighting Preset, const FText& Label, const FText& Tooltip)
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	return SNew(SButton)
		.ButtonStyle(&Style.OverlayButtonStyle)
		.ToolTipText(Tooltip)
		.OnClicked_Lambda([this, Preset]()
		{
			SetLighting(Preset);
			return FReply::Handled();
		})
		[
			SNew(SBorder)
			.BorderImage_Lambda([this, Preset]()
			{
				const FLyrisCreatorStyle& S = FLyrisCreatorStyle::Get();
				const bool bSelected = Lighting == Preset;
				if (Preset == ELyrisCreatorLighting::Mist)
				{
					return bSelected ? &S.MistChipSelectedBrush : &S.MistChipBrush;
				}
				return bSelected ? &S.TileSelectedBrush : &S.TileBrush;
			})
			.Padding(FMargin(10.f, 6.f))
			[
				SNew(STextBlock)
				.Text(Label)
				.Font(Style.SmallFont)
				.ColorAndOpacity(Style.DarkWood)
			]
		];
}

TSharedRef<SWidget> SLyrisCharacterCreator::BuildBottomBar()
{
	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	const bool bAppearance = CurrentStep() == ELyrisCreatorStep::Appearance;
	const bool bLooks = bAppearance || CurrentStep() == ELyrisCreatorStep::People;

	TSharedRef<SWrapBox> Tools = SNew(SWrapBox).UseAllottedSize(true);
	auto Add = [&Tools](TSharedRef<SWidget> Widget)
	{
		Tools->AddSlot()
			.Padding(4.f)
			.VAlign(VAlign_Center)
			[
				Widget
			];
	};

	if (bAppearance)
	{
		Add(MakeButton(LOCTEXT("Randomise", "Randomise"), [this]() { Randomise(); },
			LOCTEXT("RandomiseTip", "Roll a new look for every category that is not locked")));
		Add(SNew(SBox)
			.WidthOverride(170.f)
			[
				BuildMiniSlider(LOCTEXT("Wild", "Wildness"), 0.f, 1.f,
					[this]() { return Wildness; },
					[this](float Value) { Wildness = Value; },
					LOCTEXT("WildTip", "How far Randomise strays: calm and natural on the left, storybook-bold on the right"),
					NAME_None)
			]);
	}
	if (bLooks)
	{
		Add(MakeButton(LOCTEXT("Undo", "Undo"), [this]() { Undo(); }, LOCTEXT("UndoTip", "Ctrl+Z"),
			TAttribute<bool>::CreateLambda([this]() { return UndoStack.Num() > 0; })));
		Add(MakeButton(LOCTEXT("Redo", "Redo"), [this]() { Redo(); }, LOCTEXT("RedoTip", "Ctrl+Y"),
			TAttribute<bool>::CreateLambda([this]() { return RedoStack.Num() > 0; })));
	}
	if (bAppearance)
	{
		Add(SNew(SCheckBox)
			.Style(&Style.ToggleStyle)
			.ToolTipText(LOCTEXT("SymTip", "Moving a left or right slider moves its partner too"))
			.IsChecked_Lambda([this]() { return bSymmetry ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; })
			.OnCheckStateChanged_Lambda([this](ECheckBoxState NewState) { SetSymmetry(NewState == ECheckBoxState::Checked); })
			[
				SNew(STextBlock).Text(LOCTEXT("Symmetry", "Symmetry")).Font(Style.ButtonFont).ColorAndOpacity(Style.DarkWood)
			]);
		Add(MakeButton(LOCTEXT("ResetSection", "Reset section"), [this]() { ResetSection(); },
			LOCTEXT("ResetTip", "Put this section's sliders back to their defaults")));

		// Before / after: hold to see the look from when you entered this category.
		Add(SNew(SButton)
			.ButtonStyle(&Style.ButtonStyle)
			.ToolTipText(LOCTEXT("CompareTip", "Hold to see how you looked when you opened this category"))
			.OnPressed_Lambda([this]() { BeginCompare(); })
			.OnReleased_Lambda([this]() { EndCompare(); })
			[
				SNew(STextBlock).Text(LOCTEXT("Compare", "Hold: before")).Font(Style.ButtonFont)
			]);
		Add(SNew(SCheckBox)
			.Style(&Style.ToggleStyle)
			.ToolTipText(LOCTEXT("PresetsTip", "Ready-made looks for your People"))
			.IsChecked_Lambda([this]() { return bShowPresets ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; })
			.OnCheckStateChanged_Lambda([this](ECheckBoxState NewState) { bShowPresets = NewState == ECheckBoxState::Checked; })
			[
				SNew(STextBlock).Text(LOCTEXT("PresetsBtn", "Presets")).Font(Style.ButtonFont).ColorAndOpacity(Style.DarkWood)
			]);
		Add(MakeButton(LOCTEXT("CopyCode", "Copy code"), [this]() { CopyShareCode(); },
			LOCTEXT("CopyTip", "Copy a share code for this look to the clipboard")));
		Add(MakeButton(LOCTEXT("PasteCode", "Paste code"), [this]() { PasteShareCode(); },
			LOCTEXT("PasteTip", "Wear a look from a share code on the clipboard")));
	}

	Add(MakeButton(LOCTEXT("Expression", "Expression"), [this]() { CycleExpression(); },
		LOCTEXT("ExprTip", "Try an expression to check the face still works when it moves")));
	Add(MakeButton(LOCTEXT("Pose", "Pose"), [this]() { CyclePose(); }, LOCTEXT("PoseTip", "Try a pose")));

	Add(MakeLightingChip(ELyrisCreatorLighting::DuskDeck, LOCTEXT("LDusk", "Dusk deck"), LOCTEXT("LDuskTip", "Low warm sun behind the sail")));
	Add(MakeLightingChip(ELyrisCreatorLighting::LampLit, LOCTEXT("LLamp", "Lamp-lit"), LOCTEXT("LLampTip", "Night, under a warm lamp")));
	Add(MakeLightingChip(ELyrisCreatorLighting::Midday, LOCTEXT("LMidday", "Midday"), LOCTEXT("LMiddayTip", "High sun, the most neutral light")));
	Add(MakeLightingChip(ELyrisCreatorLighting::Mist, LOCTEXT("LMist", "Mist"), LOCTEXT("LMistTip", "Cold Moonglass light in the mist")));

	const bool bLastStep = CurrentStep() == ELyrisCreatorStep::Name;

	return SNew(SBorder)
		.BorderImage(&Style.PanelBrush)
		.Padding(FMargin(14.f, 8.f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			.VAlign(VAlign_Center)
			[
				Tools
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(Style.Gap, 0.f, 4.f, 0.f)
			[
				MakeButton(LOCTEXT("Back", "Back"), [this]() { GoToStep(StepIndex - 1); }, FText::GetEmpty(),
					TAttribute<bool>::CreateLambda([this]() { return StepIndex > 0; }))
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(4.f, 0.f, 0.f, 0.f)
			[
				SNew(SBox)
				.Visibility(bLastStep ? EVisibility::Collapsed : EVisibility::Visible)
				[
					MakeButton(LOCTEXT("Next", "Next"), [this]() { GoToStep(StepIndex + 1); },
						LOCTEXT("NextTip", "On to the next moment of the voyage"),
						TAttribute<bool>::CreateLambda([this]() { return CanLeaveStep(); }))
				]
			]
		];
}

#undef LOCTEXT_NAMESPACE
