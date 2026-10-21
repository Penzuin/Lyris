// Lyris appearance system: the option catalog (Player lane, task T23).
//
// The catalog lists every option the character creator offers. Content (ids, ranges, swatches) comes
// from design/character_creator.md (Design lane, T22). Cloud agents cannot author .uasset data assets,
// so GetDefaultCatalog() builds the whole default catalog in code (LyrisAppearanceCatalog.cpp). A designer can
// later make a data asset of this class and point the config at it (see GetDefaultCatalog()).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Player/Appearance/LyrisAppearanceTypes.h"
#include "LyrisAppearanceCatalog.generated.h"

/**
 * One section (group of options) inside a creator tab, in display order.
 * Extra helper beyond the contract: gives the UI section display names and camera framing.
 */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisSectionDef
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Category;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Section;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FText DisplayName;

	/** Camera framing id from the spec (section 2.1): "Full", "Upper", "Face", "Eyes", "Lantern". */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Framing;
};

/**
 * Metadata for one part slot (Hair, Freckles, Outfit, ...). Extra helper beyond the contract:
 * FLyrisPartDef only knows its slot, so this says which tab/section the slot lives in, whether it may
 * be empty, and what it falls back to when a look has no entry for it.
 */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisPartSlotDef
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Slot;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Category;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Section;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FText DisplayName;

	/** Optional slots may be empty (no key in Parts, or the part id None). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	bool bOptional = true;

	/** Part used when a look has no entry for this slot. None = empty (optional slots only). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName DefaultPart;

	/**
	 * Decal-style slot: parts are masks on the skin/eye material instead of meshes. The component sets
	 * texture param "<Slot>Mask", scalar "<Slot>Enabled" (0/1) and scalar "<Slot>Index" (index of the part
	 * inside the slot, so a material can pick from an atlas or texture array before real masks exist).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	bool bMask = false;
};

/**
 * The full set of appearance options. UI reads this; ULyrisAppearanceComponent applies looks with it.
 * All lookups are linear scans or small maps; the catalog is a few hundred entries, so that is fine
 * for UI use. Do not call the lookups thousands of times per frame.
 */
UCLASS(BlueprintType)
class LYRIS_API ULyrisAppearanceCatalog : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	// ---- Contract fields ----

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Appearance")
	TArray<FLyrisSliderDef> Sliders;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Appearance")
	TArray<FLyrisPartDef> Parts;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Appearance")
	TArray<FLyrisColorChannelDef> ColorChannels;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Appearance")
	TArray<FName> Peoples;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Appearance")
	TArray<FName> Frames;

	// ---- Extra helpers (additions, not part of the fixed contract) ----

	/**
	 * Part scalars (spec section 3.7): per-part amounts stored in FLyrisAppearance::PartScalars, such as
	 * "Freckles.Opacity" or the 0/1 toggles "Brows.MatchHair", "FacialHair.MatchHair", "Eyes.Heterochromia".
	 * Described with FLyrisSliderDef so the UI gets ranges, defaults, display names and sections for free.
	 * These are NOT in Sliders (the spec counts them separately).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Appearance")
	TArray<FLyrisSliderDef> PartScalarDefs;

	/** Slot metadata (tab, section, optional, default). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Appearance")
	TArray<FLyrisPartSlotDef> Slots;

	/** Sections in display order, with display names and camera framing. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Appearance")
	TArray<FLyrisSectionDef> Sections;

	/** Colour channel id -> section it is shown in (channels have a Category but no Section in the contract). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Appearance")
	TMap<FName, FName> ChannelSections;

	/** Optional body mesh per frame ("FrameA", "FrameB"). Empty until T25 lands; then the component swaps meshes. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Appearance")
	TMap<FName, TSoftObjectPtr<USkeletalMesh>> FrameMeshes;

	// ---- Contract lookups ----

	const FLyrisSliderDef* FindSlider(FName Id) const;
	const FLyrisPartDef* FindPart(FName Id) const;
	const FLyrisColorChannelDef* FindChannel(FName Id) const;

	/** Appearance tabs in display order: Body, Face, Eyes, Hair, Skin, Makeup, Outfit, Voice. Never includes "Lantern" (step 5 only). */
	UFUNCTION(BlueprintPure, Category = "Appearance")
	TArray<FName> GetCategories() const;

	/** Section ids of a category in display order. */
	UFUNCTION(BlueprintPure, Category = "Appearance")
	TArray<FName> GetSections(FName Category) const;

	/** Sliders in a category/section that are offered to People (None = any People). */
	UFUNCTION(BlueprintPure, Category = "Appearance")
	TArray<FLyrisSliderDef> GetSlidersIn(FName Category, FName Section, FName People) const;

	/** Parts of a slot that are offered to People (None = any People). */
	UFUNCTION(BlueprintPure, Category = "Appearance")
	TArray<FLyrisPartDef> GetPartsForSlot(FName Slot, FName People) const;

	/**
	 * The default catalog. If config key [/Script/Lyris.LyrisAppearanceCatalog] DefaultCatalogAsset in
	 * DefaultGame.ini names a catalog asset (soft object path), that asset is loaded and used. Otherwise
	 * the full catalog is built in code once and kept alive for the rest of the session. Game thread only.
	 */
	UFUNCTION(BlueprintPure, Category = "Appearance", meta = (DisplayName = "Get Default Appearance Catalog"))
	static ULyrisAppearanceCatalog* GetDefaultCatalog();

	/**
	 * Old name from the creator contract. It hides UObject's GetDefault<T>() inside this class, so it is
	 * deprecated: call GetDefaultCatalog(). Kept (not a UFUNCTION) so existing callers still compile.
	 */
	UE_DEPRECATED(5.8, "Use ULyrisAppearanceCatalog::GetDefaultCatalog() instead.")
	static ULyrisAppearanceCatalog* GetDefault() { return GetDefaultCatalog(); }

	// ---- Extra lookups ----

	const FLyrisSliderDef* FindPartScalar(FName Key) const;
	const FLyrisPartSlotDef* FindSlot(FName Slot) const;
	const FLyrisSectionDef* FindSection(FName Category, FName Section) const;

	/** Index of a part inside its slot's full list (not filtered by People), or INDEX_NONE. */
	int32 GetPartIndexInSlot(FName PartId) const;

	/** Part scalars in a category/section offered to People. */
	UFUNCTION(BlueprintPure, Category = "Appearance")
	TArray<FLyrisSliderDef> GetPartScalarsIn(FName Category, FName Section, FName People) const;

	/** Slots shown in a category/section. */
	UFUNCTION(BlueprintPure, Category = "Appearance")
	TArray<FLyrisPartSlotDef> GetSlotsIn(FName Category, FName Section) const;

	/** Colour channels in a category offered to People. */
	UFUNCTION(BlueprintPure, Category = "Appearance")
	TArray<FLyrisColorChannelDef> GetChannelsIn(FName Category, FName People) const;

	/** The skin tone channel for a People ("Skin.ToneHuman", "Skin.ToneElf", "Skin.ToneDeepkin"). */
	UFUNCTION(BlueprintPure, Category = "Appearance")
	static FName GetSkinChannelFor(FName People);

	/** The eye-white channel for a People ("Eyes.Sclera" or "Eyes.ScleraDeepkin"). */
	UFUNCTION(BlueprintPure, Category = "Appearance")
	static FName GetScleraChannelFor(FName People);

	/** Fills this catalog with the full default content (clears it first). Public so tools/tests can rebuild it. */
	void BuildDefaultContent();

private:
	// One builder per category so the content stays readable. See the .cpp.
	void BuildSections();
	void BuildBody();
	void BuildFace();
	void BuildEyes();
	void BuildHair();
	void BuildSkin();
	void BuildMakeup();
	void BuildOutfit();
	void BuildVoice();
	void BuildLantern();

	/** Rebuilds the id -> index maps after content changes. Called lazily by the lookups. */
	void RebuildIndex() const;

	mutable TMap<FName, int32> SliderIndex;
	mutable TMap<FName, int32> PartIndex;
	mutable TMap<FName, int32> ChannelIndex;
	mutable TMap<FName, int32> PartScalarIndex;
	mutable int32 IndexedCounts[4] = { -1, -1, -1, -1 };
};
