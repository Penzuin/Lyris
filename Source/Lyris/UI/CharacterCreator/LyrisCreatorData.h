// Lyris character creator: the small hard-coded tables the screen needs that the appearance catalog
// does not carry (step cards, which section each slot / colour channel / part scalar lives in, camera
// framing per section). Content comes from design/character_creator.md (T22) and the user's later
// decisions in design/DECISIONS.md (no Faith step; Peoples differ in look only).

#pragma once

#include "CoreMinimal.h"
#include "UI/CharacterCreator/LyrisCreatorStage.h"
#include "Player/Appearance/LyrisAppearanceTypes.h"

/** The six moments of the voyage (Faith is chosen later in the game through a quest, not here). */
enum class ELyrisCreatorStep : uint8
{
	People,
	Appearance,
	Path,
	Backstory,
	Lantern,
	Name,
	Count
};

/** A card on a picker step (People, Path, Backstory, Lantern). */
struct FLyrisCreatorCard
{
	FName Id;
	FText Title;
	FText Line1;       // e.g. starting item, or a look line
	FText Line2;       // e.g. branches
	FName ForPath;     // backstories only: the path they belong to
	FName DefaultPart; // paths: default outfit part; lanterns: their catalog part id (same as Id)
};

/** One section of an Appearance category, as the left column lists it. */
struct FLyrisCreatorSectionInfo
{
	FName Category;
	FName Section;
	FText DisplayName;
	ELyrisCreatorShot Shot = ELyrisCreatorShot::Face;
};

/** Where a part slot is edited. */
struct FLyrisCreatorSlotInfo
{
	FName Slot;
	FName Category;
	FName Section;
	FText DisplayName;
	bool bOptional = true; // shows a "None" tile
};

/** A part scalar (FLyrisAppearance::PartScalars) shown as a slider or a toggle. */
struct FLyrisCreatorScalarInfo
{
	FName Key;
	FName Category;
	FName Section;
	FText DisplayName;
	FText Tooltip;
	float Min = 0.f;
	float Max = 1.f;
	float Default = 0.f;
	bool bToggle = false;          // stored as 0 / 1
	TArray<FName> People;          // empty = all
};

namespace LyrisCreatorData
{
	// Ids shared with the Player lane (spec section 1 and 3.7).
	extern const FName People_Human;
	extern const FName People_MoonlitElf;
	extern const FName People_Deepkin;
	extern const FName Frame_A;
	extern const FName Frame_B;
	extern const FName Slot_Outfit;
	extern const FName Slot_Lantern;
	extern const FName Slot_Expression;
	extern const FName Channel_IrisL;
	extern const FName Channel_IrisR;
	extern const FName Channel_HairBrows;
	extern const FName Channel_HairFacialHair;
	extern const FName Channel_LanternGlass;
	extern const FName Scalar_Heterochromia;
	extern const FName Scalar_BrowsMatchHair;
	extern const FName Scalar_FacialHairMatchHair;
	extern const FName Category_Lantern;

	int32 NumSteps();
	FText StepName(ELyrisCreatorStep Step);
	/** One line shown under the step title: the moment on the voyage. */
	FText StepMoment(ELyrisCreatorStep Step);
	ELyrisCreatorShot StepShot(ELyrisCreatorStep Step);

	const TArray<FLyrisCreatorCard>& Peoples();
	const TArray<FLyrisCreatorCard>& Paths();
	const TArray<FLyrisCreatorCard>& Backstories();
	const TArray<FLyrisCreatorCard>& Lanterns();

	/** Appearance tabs in display order (Lantern is never a tab). */
	const TArray<FName>& Categories();
	FText CategoryName(FName Category);

	const TArray<FLyrisCreatorSectionInfo>& Sections();
	const FLyrisCreatorSectionInfo* FindSection(FName Category, FName Section);
	FText SectionName(FName Category, FName Section);

	const TArray<FLyrisCreatorSlotInfo>& Slots();

	const TArray<FLyrisCreatorScalarInfo>& Scalars();
	const FLyrisCreatorScalarInfo* FindScalar(FName Key);

	/**
	 * Expression previews (spec 9.6), as bare ids ("Calm", "Laugh"). The resting-expression parts in the
	 * catalog are "Expression.<Id>"; the stage always gets the bare id (see ExpressionPreviewId).
	 * Laugh, Surprised and Sleepy are preview-only and never stored in the look.
	 */
	const TArray<TPair<FName, FText>>& Expressions();

	/** "Expression.Calm" -> "Calm"; a bare id is returned unchanged. */
	FName ExpressionPreviewId(FName ExpressionPartOrId);
	const TArray<TPair<FName, FText>>& Poses();

	/** Lantern glass band (spec 5.2), used only if the catalog has no Lantern.Glass channel. */
	const FLyrisColorChannelDef& FallbackLanternGlass();

	/** Name rules for the harbourmaster's ledger. Returns empty text when the name is fine. */
	FText ValidateName(const FString& Name);
}
