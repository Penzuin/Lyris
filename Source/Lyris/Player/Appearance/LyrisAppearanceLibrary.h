// Lyris appearance system: stateless helpers (Player lane, task T23).
//
// Colour resolving, share codes, randomise, the per-People presets, and the rules that keep a look
// valid (ranges, People restrictions, the adult proportions guard). ULyrisAppearanceComponent and the
// creator UI (T24) both call these, so the rules live in exactly one place.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Math/RandomStream.h"
#include "Player/Appearance/LyrisAppearanceTypes.h"
#include "LyrisAppearanceLibrary.generated.h"

class ULyrisAppearanceCatalog;
struct FLyrisSliderDef;

/** Well-known ids the rules below depend on (spec character_creator.md sections 3.3, 3.7, 6.2). */
namespace LyrisAppearanceIds
{
	extern LYRIS_API const FName BodyHeight;          // "Body.Height"
	extern LYRIS_API const FName BodyHeadSize;        // "Body.HeadSize"
	extern LYRIS_API const FName EyesSizeL;           // "Eyes.SizeL"
	extern LYRIS_API const FName EyesSizeR;           // "Eyes.SizeR"
	extern LYRIS_API const FName BrowsMatchHair;      // "Brows.MatchHair" (part scalar, 0/1)
	extern LYRIS_API const FName FacialHairMatchHair; // "FacialHair.MatchHair" (part scalar, 0/1)
	extern LYRIS_API const FName EyesHeterochromia;   // "Eyes.Heterochromia" (part scalar, 0/1)
	extern LYRIS_API const FName ChannelHairRoot;     // "Hair.Root"
	extern LYRIS_API const FName ChannelHairBrows;    // "Hair.Brows"
	extern LYRIS_API const FName ChannelHairFacial;   // "Hair.FacialHair"
	extern LYRIS_API const FName ChannelIrisL;        // "Eyes.IrisL"
	extern LYRIS_API const FName ChannelIrisR;        // "Eyes.IrisR"
	extern LYRIS_API const FName CategoryLantern;     // "Lantern" (creator step 5, not an Appearance tab)
}

UCLASS()
class LYRIS_API ULyrisAppearanceLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	// ---------------------------------------------------------------- Contract

	/**
	 * The colour a pick stands for: the chosen swatch, hue-shifted and value-shifted. Shifts are clamped to
	 * the channel's MaxHueShift / MaxValueShift and the swatch index to the band. The shift happens in sRGB
	 * HSV (perceptual), the result is linear like the swatches. Empty band -> white.
	 */
	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance")
	static FLinearColor ResolveColor(const FLyrisColorChannelDef& Channel, const FLyrisColorPick& Pick);

	/** "LYR1:" + Base64(compact JSON) of a look. Keys are sorted, floats rounded to 3 decimals. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance")
	static FString ToShareCode(const FLyrisAppearance& Appearance);

	/**
	 * Parses a share code. Unknown ids are ignored, values are clamped, entries restricted to another People
	 * are dropped and the adult proportions guard is applied (all via SanitizeAppearance with the default
	 * catalog). Returns false (and leaves Out untouched) when the code is not a valid LYR1 code.
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	static bool FromShareCode(const FString& Code, FLyrisAppearance& Out);

	/**
	 * Randomises everything whose category is not locked, inside slider ranges and curated swatches (spec 9.3).
	 * Wildness 0 = close to the People's first preset, common swatches and parts; 0.35 = normal spread; 1 = full
	 * range, full shifts, storybook hair colours more likely. Keeps People and Frame. Never touches Lantern.
	 * Mirror pairs get the same value plus a small difference (up to 0.1 x wildness). Adult guard always applies.
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	static void RandomizeAppearance(const ULyrisAppearanceCatalog* Catalog, UPARAM(ref) FLyrisAppearance& InOut, UPARAM(ref) FRandomStream& Stream,
		const TSet<FName>& LockedCategories, float Wildness = 0.35f);

	/** One of the six named presets per People (spec 9.8). Index wraps. Unknown People -> Human. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance")
	static FLyrisAppearance MakePreset(FName People, int32 Index);

	// ---------------------------------------------------------------- Extra helpers

	/** Number of presets per People (6). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance")
	static int32 GetPresetCount() { return 6; }

	/** Display name of a preset, e.g. "Harbor Hand". */
	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance")
	static FText GetPresetName(FName People, int32 Index);

	/**
	 * Makes a look valid for its catalog and People: clamps values, drops unknown ids and entries not offered to
	 * the look's People (per-People skin and eye-white picks are kept so switching back restores them), fills a
	 * missing skin / eye-white pick from the other People's pick at the matching band position, copies the left
	 * iris to the right one when heterochromia is off, rounds 0/1 toggles, and applies the adult guard.
	 * Null catalog = default catalog.
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	static void SanitizeAppearance(const ULyrisAppearanceCatalog* Catalog, UPARAM(ref) FLyrisAppearance& InOut);

	/**
	 * Changes the People and re-validates the look against it (spec 9.10: keep the look as close as possible).
	 * The new People's skin and eye-white picks come from the old People's picks at the matching band position,
	 * unless the look already remembers a pick for the new People.
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	static void ChangePeople(const ULyrisAppearanceCatalog* Catalog, UPARAM(ref) FLyrisAppearance& InOut, FName NewPeople);

	/**
	 * Adult proportions guard (spec 6.2): if Body.Height < -0.5, Body.HeadSize is capped at +0.3; if additionally
	 * Body.HeadSize > 0, Eyes.SizeL/R are capped at +0.6. Returns true if anything changed.
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	static bool ApplyAdultGuard(UPARAM(ref) FLyrisAppearance& InOut);

	/** Effective slider value: Sliders, then PartScalars, then the def's default; default if not offered to the People; clamped. */
	static float GetSliderValue(const FLyrisAppearance& Appearance, const FLyrisSliderDef& Def);

	/** Effective part-scalar value: PartScalars, then Sliders, then default (same rules as GetSliderValue). */
	static float GetPartScalarValue(const ULyrisAppearanceCatalog* Catalog, const FLyrisAppearance& Appearance, FName Key);

	/** Effective part in a slot: the look's choice, else the slot's DefaultPart. None = empty. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance")
	static FName GetEffectivePart(const ULyrisAppearanceCatalog* Catalog, const FLyrisAppearance& Appearance, FName Slot);

	/** Effective pick in a channel (the look's pick or the default pick {0,0,0}). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance")
	static FLyrisColorPick GetEffectivePick(const FLyrisAppearance& Appearance, FName Channel);

	/** True for the 0/1 toggle part scalars (Brows.MatchHair, FacialHair.MatchHair, Eyes.Heterochromia). */
	static bool IsToggleKey(FName Key);
};
