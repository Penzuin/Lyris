// Lyris appearance system: shared data types (Player lane, task T23).
//
// This header is the CONTRACT between the Player lane (which applies an appearance to the
// character) and the UI lane (the character creator screen, T24). Names and shapes here are
// fixed by the lead's creator contract; add helpers freely, but do not rename or reshape
// existing fields without the lead.
//
// Overview
//   - A catalog (ULyrisAppearanceCatalog) lists every option: sliders, parts and colour channels.
//   - A look (FLyrisAppearance) is just a set of choices keyed by catalog ids. Missing keys mean
//     "use the catalog default", so old saves keep working when the catalog grows.
//   - ULyrisAppearanceComponent applies a look to a character's skeletal mesh.

#pragma once

#include "CoreMinimal.h"
#include "UObject/SoftObjectPtr.h"
#include "LyrisAppearanceTypes.generated.h"

class USkeletalMesh;
class UStaticMesh;
class UTexture2D;

/** Well-known People ids (step 1 of the creator). */
namespace LyrisPeople
{
	extern LYRIS_API const FName Human;       // "Human"
	extern LYRIS_API const FName MoonlitElf;  // "MoonlitElf"
	extern LYRIS_API const FName Deepkin;     // "Deepkin"
}

/** Well-known body frame ids. Frames are cosmetic and never gender-locked. */
namespace LyrisFrames
{
	extern LYRIS_API const FName FrameA;      // "FrameA" (display "Willow")
	extern LYRIS_API const FName FrameB;      // "FrameB" (display "Oak")
}

/** What a slider drives on the character. */
UENUM(BlueprintType)
enum class ELyrisAppearanceTargetKind : uint8
{
	/** A morph target (blend shape) on the body mesh. */
	MorphTarget     UMETA(DisplayName = "Morph target"),
	/** Scales a bone: scale = 1 + Axis * v * Weight (per axis, bone-local axes). */
	BoneScale       UMETA(DisplayName = "Bone scale"),
	/** Moves a bone: offset = Axis * v * Weight in cm, added to the bone's local translation. */
	BoneOffset      UMETA(DisplayName = "Bone offset"),
	/** Rotates a bone: Axis holds (pitch, yaw, roll) in degrees, times v * Weight, in bone space. */
	BoneRotation    UMETA(DisplayName = "Bone rotation"),
	/** Sets a scalar material parameter on every material of the body and its parts: v * Weight. */
	MaterialScalar  UMETA(DisplayName = "Material scalar")
};

/**
 * One thing a slider drives. A slider can drive several targets at once (e.g. "Leg length"
 * scales thighs and calves and lifts the pelvis so the feet stay on the ground).
 *
 * Value v (the slider value, usually in [-1, 1]) maps to:
 *  - MorphTarget:    weight = clamp(v * Weight). If the mesh has "<Name>_Pos" / "<Name>_Neg"
 *                    morphs, positive values drive _Pos and negative values drive _Neg (with a
 *                    positive weight). Otherwise "<Name>" gets v * Weight directly.
 *                    Several sliders hitting the same morph are summed before clamping.
 *  - BoneScale:      scale = 1 + Axis * v * Weight.
 *  - BoneOffset:     offset = Axis * v * Weight (cm), in the bone's local translation space,
 *                    i.e. the same space as the "Translation" field in the Skeleton editor.
 *  - BoneRotation:   rotation = Axis (pitch, yaw, roll in degrees) * v * Weight, in bone space.
 *  - MaterialScalar: param = v * Weight. Sliders hitting the same param are summed.
 */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisSliderTarget
{
	GENERATED_BODY()

	FLyrisSliderTarget() {}
	FLyrisSliderTarget(ELyrisAppearanceTargetKind InKind, FName InName, const FVector& InAxis, float InWeight)
		: Kind(InKind), Name(InName), Axis(InAxis), Weight(InWeight) {}

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	ELyrisAppearanceTargetKind Kind = ELyrisAppearanceTargetKind::MorphTarget;

	/** Morph target name, bone name or material parameter name, depending on Kind. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Name;

	/** For bone kinds: per-axis factor (scale/offset) or (pitch, yaw, roll) for rotation. Ignored otherwise. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FVector Axis = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	float Weight = 1.f;
};

/** One slider in the creator. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisSliderDef
{
	GENERATED_BODY()

	/** Unique id, e.g. "Face.JawWidth", "Face.EyeSize.L", "Freckles.Opacity". Saved in looks. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Id;

	/** Creator tab, e.g. "Body", "Face", "Skin". */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Category;

	/** Group inside the tab, e.g. "Proportions", "Nose". See ULyrisAppearanceCatalog::Sections for display names. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Section;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FText DisplayName;

	/** Extra (not in the fixed contract): tooltip, "low / high" wording from the spec, e.g. "narrow / wide". May be empty. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FText Description;

	/** Clamped stylized range. Values outside it are never stored by the component. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	float Min = -1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	float Max = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	float Default = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	TArray<FLyrisSliderTarget> Targets;

	/** Slider id on the other side, for symmetry editing (e.g. "Face.EyeSize.L" <-> "Face.EyeSize.R"). None if unpaired. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName MirrorOf;

	/** Face region for click-drag sculpting (e.g. "Jaw", "Eye_L"); None if not sculptable. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName SculptRegion;

	/** 0 = driven by horizontal drag, 1 = driven by vertical drag. Each region has at most one slider per axis. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance", meta = (ClampMin = "0", ClampMax = "1"))
	uint8 SculptAxis = 0;

	/** Peoples this slider is offered to. Empty = all. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	TArray<FName> People;

	bool AllowsPeople(FName InPeople) const { return People.Num() == 0 || InPeople.IsNone() || People.Contains(InPeople); }
	float ClampValue(float V) const { return FMath::Clamp(V, FMath::Min(Min, Max), FMath::Max(Min, Max)); }
};

/** One selectable part (hair style, outfit, freckle pattern, voice, ...). */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisPartDef
{
	GENERATED_BODY()

	/** Unique id, "<Slot>.<Name>", e.g. "Hair.SeaWindBob". Saved in looks. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Id;

	/** Slot this part fills, e.g. "Hair", "Freckles", "Outfit". One part per slot. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Slot;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FText DisplayName;

	/** Skinned part: spawned as a child skeletal mesh following the body (leader pose). May be empty until art exists. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	TSoftObjectPtr<USkeletalMesh> SkeletalMesh;

	/** Rigid part: spawned as a static mesh on AttachSocket. May be empty until art exists. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	TSoftObjectPtr<UStaticMesh> StaticMesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName AttachSocket;

	/** For decal-style parts (freckles, markings, scars, makeup): mask set as texture param "<Slot>Mask" on body materials. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	TSoftObjectPtr<UTexture2D> Mask;

	/** Peoples this part is offered to. Empty = all. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	TArray<FName> People;

	bool AllowsPeople(FName InPeople) const { return People.Num() == 0 || InPeople.IsNone() || People.Contains(InPeople); }
};

/** One curated colour in a channel's band. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisSwatch
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FText DisplayName;

	/** Linear colour (built from sRGB hex in the default catalog). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FLinearColor Color = FLinearColor::White;
};

/** A colour channel (skin tone, hair root, iris left, outfit trim, ...). */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisColorChannelDef
{
	GENERATED_BODY()

	/** Unique id, e.g. "Hair.Root", "Skin.Tone.Human". Saved in looks. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Id;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName Category;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FText DisplayName;

	/** The curated band. Players pick one swatch and may shift it a little (see below). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	TArray<FLyrisSwatch> Swatches;

	/** Max hue shift either way, as a fraction of the colour wheel (0..0.5). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance", meta = (ClampMin = "0", ClampMax = "0.5"))
	float MaxHueShift = 0.06f;

	/** Max value (brightness) shift either way (0..1). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance", meta = (ClampMin = "0", ClampMax = "1"))
	float MaxValueShift = 0.15f;

	/** Vector material parameter that receives the resolved colour, e.g. "SkinTone", "HairRoot". */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	FName MaterialParam;

	/** Peoples this channel is offered to. Empty = all. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Appearance")
	TArray<FName> People;

	bool AllowsPeople(FName InPeople) const { return People.Num() == 0 || InPeople.IsNone() || People.Contains(InPeople); }
};

/** A player's choice in one colour channel: a swatch plus a small shift. Resolve with ULyrisAppearanceLibrary::ResolveColor. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisColorPick
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Appearance")
	int32 Swatch = 0;

	/** Fraction of the colour wheel (not -1..1), clamped to +-MaxHueShift of the channel. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Appearance")
	float HueShift = 0.f;

	/** Clamped to +-MaxValueShift of the channel. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Appearance")
	float ValueShift = 0.f;

	bool operator==(const FLyrisColorPick& Other) const
	{
		return Swatch == Other.Swatch && HueShift == Other.HueShift && ValueShift == Other.ValueShift;
	}
	bool operator!=(const FLyrisColorPick& Other) const { return !(*this == Other); }
};

/**
 * A complete look. Everything is keyed by catalog ids; a missing key means "catalog default".
 * Note: TMaps do not replicate in Unreal, so ULyrisAppearanceComponent replicates this as a
 * compact share code string (see ULyrisAppearanceLibrary::ToShareCode).
 */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisAppearance
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Appearance")
	int32 Version = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Appearance")
	FName People = FName(TEXT("Human"));

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Appearance")
	FName Frame = FName(TEXT("FrameA"));

	/** Slider id -> value. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Appearance")
	TMap<FName, float> Sliders;

	/** Slot -> part id. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Appearance")
	TMap<FName, FName> Parts;

	/** Channel id -> pick. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Appearance")
	TMap<FName, FLyrisColorPick> Colors;

	/**
	 * Extra per-part values, e.g. "Freckles.Opacity", "Makeup.Eyeliner.Opacity".
	 * The default catalog also exposes these keys as sliders (same ids), so the UI may write them
	 * either here (SetPartScalar) or into Sliders (SetSlider); the component reads Sliders first,
	 * then PartScalars, then the catalog default. A key with no matching slider is applied as a
	 * scalar material parameter named after the key with '.' replaced by '_'.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Appearance")
	TMap<FName, float> PartScalars;
};

/** Everything the creator produces: the look plus the other six voyage steps. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisCharacterProfile
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Profile")
	FLyrisAppearance Appearance;

	/** Starting path (one of seven broad paths). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Profile")
	FName Path;

	/** Optional backstory id. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Profile")
	FName Backstory;

	/** Optional faith id (Tide Mother, Green Hearth, Wayfarers, Bright Cask, ...), None for no faith. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Profile")
	FName Faith;

	/** Lantern shape part id (default catalog slot "LanternShape", e.g. "LanternShape.Round"). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Profile")
	FName LanternShape;

	/** Lantern glass colour; the default catalog channel is "Lantern.Glass". */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Profile")
	FLyrisColorPick LanternGlass;

	/** Name written into the harbourmaster's ledger. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Profile")
	FString Name;
};
