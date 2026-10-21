// Lyris appearance system: the option catalog and its default content (Player lane, task T23).
//
// Every id, range, weight, mirror pair, sculpt region, part and swatch below comes from
// design/character_creator.md (T22). If you change content, change the spec first (Design lane owns it),
// then mirror it here. The builder is split into one function per creator tab (BuildBody, BuildFace, ...).
//
// Totals (match spec section 3.8 / 4.1 / 5.1): 138 sliders, 25 part scalars, 22 slots / 195 parts,
// 29 colour channels / 359 swatches.

#include "Player/Appearance/LyrisAppearanceCatalog.h"
#include "Misc/ConfigCacheIni.h"
#include "UObject/Package.h"
#include "UObject/SoftObjectPath.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"

// =====================================================================================================
// Lookups
// =====================================================================================================

void ULyrisAppearanceCatalog::RebuildIndex() const
{
	SliderIndex.Reset();
	PartIndex.Reset();
	ChannelIndex.Reset();
	PartScalarIndex.Reset();
	for (int32 i = 0; i < Sliders.Num(); ++i)        { SliderIndex.Add(Sliders[i].Id, i); }
	for (int32 i = 0; i < Parts.Num(); ++i)          { PartIndex.Add(Parts[i].Id, i); }
	for (int32 i = 0; i < ColorChannels.Num(); ++i)  { ChannelIndex.Add(ColorChannels[i].Id, i); }
	for (int32 i = 0; i < PartScalarDefs.Num(); ++i) { PartScalarIndex.Add(PartScalarDefs[i].Id, i); }
	IndexedCounts[0] = Sliders.Num();
	IndexedCounts[1] = Parts.Num();
	IndexedCounts[2] = ColorChannels.Num();
	IndexedCounts[3] = PartScalarDefs.Num();
}

// The index is rebuilt whenever an array's size changed (cheap guard against edits in a data asset).
#define LYRIS_ENSURE_INDEX() \
	if (IndexedCounts[0] != Sliders.Num() || IndexedCounts[1] != Parts.Num() || \
		IndexedCounts[2] != ColorChannels.Num() || IndexedCounts[3] != PartScalarDefs.Num()) { RebuildIndex(); }

const FLyrisSliderDef* ULyrisAppearanceCatalog::FindSlider(FName Id) const
{
	LYRIS_ENSURE_INDEX();
	const int32* Found = SliderIndex.Find(Id);
	return (Found && Sliders.IsValidIndex(*Found) && Sliders[*Found].Id == Id) ? &Sliders[*Found] : nullptr;
}

const FLyrisPartDef* ULyrisAppearanceCatalog::FindPart(FName Id) const
{
	LYRIS_ENSURE_INDEX();
	const int32* Found = PartIndex.Find(Id);
	return (Found && Parts.IsValidIndex(*Found) && Parts[*Found].Id == Id) ? &Parts[*Found] : nullptr;
}

const FLyrisColorChannelDef* ULyrisAppearanceCatalog::FindChannel(FName Id) const
{
	LYRIS_ENSURE_INDEX();
	const int32* Found = ChannelIndex.Find(Id);
	return (Found && ColorChannels.IsValidIndex(*Found) && ColorChannels[*Found].Id == Id) ? &ColorChannels[*Found] : nullptr;
}

const FLyrisSliderDef* ULyrisAppearanceCatalog::FindPartScalar(FName Key) const
{
	LYRIS_ENSURE_INDEX();
	const int32* Found = PartScalarIndex.Find(Key);
	return (Found && PartScalarDefs.IsValidIndex(*Found) && PartScalarDefs[*Found].Id == Key) ? &PartScalarDefs[*Found] : nullptr;
}

#undef LYRIS_ENSURE_INDEX

const FLyrisPartSlotDef* ULyrisAppearanceCatalog::FindSlot(FName Slot) const
{
	return Slots.FindByPredicate([Slot](const FLyrisPartSlotDef& S) { return S.Slot == Slot; });
}

const FLyrisSectionDef* ULyrisAppearanceCatalog::FindSection(FName Category, FName Section) const
{
	return Sections.FindByPredicate([Category, Section](const FLyrisSectionDef& S) { return S.Category == Category && S.Section == Section; });
}

int32 ULyrisAppearanceCatalog::GetPartIndexInSlot(FName PartId) const
{
	const FLyrisPartDef* Part = FindPart(PartId);
	if (!Part)
	{
		return INDEX_NONE;
	}
	int32 Index = 0;
	for (const FLyrisPartDef& P : Parts)
	{
		if (P.Slot == Part->Slot)
		{
			if (P.Id == PartId)
			{
				return Index;
			}
			++Index;
		}
	}
	return INDEX_NONE;
}

TArray<FName> ULyrisAppearanceCatalog::GetCategories() const
{
	static const FName LanternCategory(TEXT("Lantern"));
	TArray<FName> Result;
	for (const FLyrisSectionDef& S : Sections)
	{
		if (S.Category != LanternCategory)
		{
			Result.AddUnique(S.Category);
		}
	}
	return Result;
}

TArray<FName> ULyrisAppearanceCatalog::GetSections(FName Category) const
{
	TArray<FName> Result;
	for (const FLyrisSectionDef& S : Sections)
	{
		if (S.Category == Category)
		{
			Result.AddUnique(S.Section);
		}
	}
	return Result;
}

TArray<FLyrisSliderDef> ULyrisAppearanceCatalog::GetSlidersIn(FName Category, FName Section, FName People) const
{
	TArray<FLyrisSliderDef> Result;
	for (const FLyrisSliderDef& S : Sliders)
	{
		if (S.Category == Category && (Section.IsNone() || S.Section == Section) && S.AllowsPeople(People))
		{
			Result.Add(S);
		}
	}
	return Result;
}

TArray<FLyrisPartDef> ULyrisAppearanceCatalog::GetPartsForSlot(FName Slot, FName People) const
{
	TArray<FLyrisPartDef> Result;
	for (const FLyrisPartDef& P : Parts)
	{
		if (P.Slot == Slot && P.AllowsPeople(People))
		{
			Result.Add(P);
		}
	}
	return Result;
}

TArray<FLyrisSliderDef> ULyrisAppearanceCatalog::GetPartScalarsIn(FName Category, FName Section, FName People) const
{
	TArray<FLyrisSliderDef> Result;
	for (const FLyrisSliderDef& S : PartScalarDefs)
	{
		if (S.Category == Category && (Section.IsNone() || S.Section == Section) && S.AllowsPeople(People))
		{
			Result.Add(S);
		}
	}
	return Result;
}

TArray<FLyrisPartSlotDef> ULyrisAppearanceCatalog::GetSlotsIn(FName Category, FName Section) const
{
	TArray<FLyrisPartSlotDef> Result;
	for (const FLyrisPartSlotDef& S : Slots)
	{
		if (S.Category == Category && (Section.IsNone() || S.Section == Section))
		{
			Result.Add(S);
		}
	}
	return Result;
}

TArray<FLyrisColorChannelDef> ULyrisAppearanceCatalog::GetChannelsIn(FName Category, FName People) const
{
	TArray<FLyrisColorChannelDef> Result;
	for (const FLyrisColorChannelDef& C : ColorChannels)
	{
		if (C.Category == Category && C.AllowsPeople(People))
		{
			Result.Add(C);
		}
	}
	return Result;
}

FName ULyrisAppearanceCatalog::GetSkinChannelFor(FName People)
{
	static const FName Elf(TEXT("Skin.ToneElf"));
	static const FName Deep(TEXT("Skin.ToneDeepkin"));
	static const FName Human(TEXT("Skin.ToneHuman"));
	if (People == LyrisPeople::MoonlitElf) { return Elf; }
	if (People == LyrisPeople::Deepkin)    { return Deep; }
	return Human;
}

FName ULyrisAppearanceCatalog::GetScleraChannelFor(FName People)
{
	static const FName Deep(TEXT("Eyes.ScleraDeepkin"));
	static const FName Normal(TEXT("Eyes.Sclera"));
	return People == LyrisPeople::Deepkin ? Deep : Normal;
}

ULyrisAppearanceCatalog* ULyrisAppearanceCatalog::GetDefault()
{
	// Kept alive with AddToRoot for the whole session; built on first use.
	static ULyrisAppearanceCatalog* Cached = nullptr;
	if (Cached && IsValid(Cached))
	{
		return Cached;
	}

	// 1) A designer-authored catalog asset, if one is configured.
	FString AssetPath;
	if (GConfig && GConfig->GetString(TEXT("/Script/Lyris.LyrisAppearanceCatalog"), TEXT("DefaultCatalogAsset"), AssetPath, GGameIni) && !AssetPath.IsEmpty())
	{
		if (ULyrisAppearanceCatalog* Loaded = Cast<ULyrisAppearanceCatalog>(FSoftObjectPath(AssetPath).TryLoad()))
		{
			Loaded->AddToRoot();
			Cached = Loaded;
			return Cached;
		}
	}

	// 2) The built-in default, constructed in code.
	ULyrisAppearanceCatalog* Built = NewObject<ULyrisAppearanceCatalog>(GetTransientPackage(), TEXT("LyrisDefaultAppearanceCatalog"), RF_Transient);
	Built->AddToRoot();
	Built->BuildDefaultContent();
	Cached = Built;
	return Cached;
}

// =====================================================================================================
// Builder helpers (file-local)
// =====================================================================================================

namespace LyrisCatalogBuild
{
	using EKind = ELyrisAppearanceTargetKind;

	// ---- UE5 mannequin bone-axis assumptions ------------------------------------------------------
	// Every body target uses these constants, so if a slider moves the wrong way in the editor, fix it
	// here once. They are NOT verified in an editor build (cloud agents cannot open one).
	//  - Chain bones (pelvis, spine_01..05, neck_01, head, clavicle, upperarm, lowerarm, thigh, calf):
	//    local X runs from the bone towards its child ("along the bone").
	//  - Centre bones (pelvis, spine, neck, head): Z is the left/right axis, Y is front/back.
	//  - Limb bones: Y and Z are the two cross axes (their thickness), Y is taken as front/back.
	//  - root is identity with Z up, so a pelvis offset in Z lifts the whole body.
	const FVector AlongBone(1.f, 0.f, 0.f);
	const FVector CentreSide(0.f, 0.f, 1.f);
	const FVector CentreFront(0.f, 1.f, 0.f);
	const FVector Cross(0.f, 1.f, 1.f);
	const FVector Uniform(1.f, 1.f, 1.f);
	const FVector Up(0.f, 0.f, 1.f);
	// Rotation axes are (pitch, yaw, roll) = rotation about local (Y, Z, X), in degrees.
	const FVector RotAboutFront(1.f, 0.f, 0.f);   // pitch: about Y (front/back axis) -> raises/lowers, spreads legs
	const FVector RotAboutSide(0.f, 1.f, 0.f);    // yaw: about Z (side axis on centre bones) -> bends forward/back

	// ---- Mirrored space (spec section 1) ----------------------------------------------------------
	// The same slider value on _l and _r must give a symmetric result, so the _r target's axis is the
	// mirror of the _l one. Assumed mannequin convention (UE4/UE5 Manny/Quinn): a right-side bone frame is
	// the mirror image of the left one with its X axis reversed, (rx, ry, rz) = (-S*lx, S*ly, S*lz), where
	// S is the reflection across the body's mid plane. Working that through:
	//  - BoneScale: same axis on both sides (scale has no direction).
	//  - BoneRotation (pitch about Y, yaw about Z, roll about X): reflecting a rotation keeps the
	//    roll and negates pitch and yaw -> right = (-pitch, -yaw, +roll).
	//  - BoneOffset: our offsets are only used on bones whose PARENT is a centre bone (thigh under pelvis,
	//    clavicle under spine_05), so the offset is in the centre parent's frame, and mirroring negates its
	//    left/right (CentreSide) component.
	// If a pair moves asymmetrically in the editor, the convention above is wrong for that rig: fix it
	// here once (RightRotationFlip) rather than in the slider list.
	const FVector RightRotationFlip(-1.f, -1.f, 1.f);

	inline FVector MirrorAxis(EKind Kind, const FVector& Axis)
	{
		switch (Kind)
		{
		case EKind::BoneOffset:
			return Axis - 2.f * CentreSide * FVector::DotProduct(Axis, CentreSide);
		case EKind::BoneRotation:
			return Axis * RightRotationFlip;
		default:
			return Axis;
		}
	}

	inline FText Txt(const TCHAR* S) { return FText::FromString(S); }
	inline FText Txt(const FString& S) { return FText::FromString(S); }

	inline FLinearColor Hex(const TCHAR* HexCode)
	{
		// Spec hex values are sRGB; FLinearColor(FColor) converts sRGB -> linear.
		return FLinearColor(FColor::FromHex(FString(HexCode)));
	}

	/** Adds a slider and returns it. Do not hold the reference across another Add (array may grow). */
	inline FLyrisSliderDef& AddSlider(TArray<FLyrisSliderDef>& Arr, FName Cat, FName Sec, const FString& Id, const FString& Name,
		float Min = -1.f, float Max = 1.f, float Default = 0.f)
	{
		FLyrisSliderDef& D = Arr.AddDefaulted_GetRef();
		D.Id = FName(*Id);
		D.Category = Cat;
		D.Section = Sec;
		D.DisplayName = Txt(Name);
		D.Min = Min;
		D.Max = Max;
		D.Default = Default;
		return D;
	}

	inline void Morph(FLyrisSliderDef& D, const FString& MorphName, float Weight = 1.f)
	{
		D.Targets.Add(FLyrisSliderTarget(EKind::MorphTarget, FName(*MorphName), FVector::ZeroVector, Weight));
	}

	inline void Mat(FLyrisSliderDef& D, const TCHAR* Param, float Weight = 1.f)
	{
		D.Targets.Add(FLyrisSliderTarget(EKind::MaterialScalar, FName(Param), FVector::ZeroVector, Weight));
	}

	inline void Bone(FLyrisSliderDef& D, EKind Kind, const TCHAR* BoneName, const FVector& Axis, float Weight)
	{
		D.Targets.Add(FLyrisSliderTarget(Kind, FName(BoneName), Axis, Weight));
	}

	/** Adds "<Base>_l" and "<Base>_r" targets, with the right side mirrored (see MirrorAxis). */
	inline void BonePair(FLyrisSliderDef& D, EKind Kind, const FString& Base, const FVector& Axis, float Weight)
	{
		D.Targets.Add(FLyrisSliderTarget(Kind, FName(*(Base + TEXT("_l"))), Axis, Weight));
		D.Targets.Add(FLyrisSliderTarget(Kind, FName(*(Base + TEXT("_r"))), MirrorAxis(Kind, Axis), Weight));
	}

	inline void Sculpt(FLyrisSliderDef& D, const TCHAR* Region, uint8 Axis /*0 = H, 1 = V*/)
	{
		D.SculptRegion = FName(Region);
		D.SculptAxis = Axis;
	}

	inline void ForPeople(FLyrisSliderDef& D, std::initializer_list<FName> InPeople)
	{
		for (const FName& P : InPeople) { D.People.Add(P); }
	}

	/** One side of a left/right morph pair. */
	struct FPairSpec
	{
		const TCHAR* IdBase;      // "Eyes.Size" -> "Eyes.SizeL" / "Eyes.SizeR"
		const TCHAR* Name;        // "Eye size" -> "Eye size, left" / "Eye size, right"
		const TCHAR* MorphBase;   // "Eye_Size" -> "Eye_Size_L" / "Eye_Size_R"
		float Weight = 1.f;
		float Min = -1.f;
		float Max = 1.f;
		const TCHAR* SculptRegionBase = nullptr; // "Eye" -> "EyeL" / "EyeR"
		uint8 SculptAxis = 0;
	};

	/** Adds a mirrored L/R pair of morph sliders (same value on both sides = symmetric face). */
	inline void AddPair(TArray<FLyrisSliderDef>& Arr, FName Cat, FName Sec, const FPairSpec& P, std::initializer_list<FName> People = {})
	{
		const FString IdL = FString(P.IdBase) + TEXT("L");
		const FString IdR = FString(P.IdBase) + TEXT("R");
		for (int32 Side = 0; Side < 2; ++Side)
		{
			const bool bLeft = (Side == 0);
			FLyrisSliderDef& D = AddSlider(Arr, Cat, Sec, bLeft ? IdL : IdR,
				FString::Printf(TEXT("%s, %s"), P.Name, bLeft ? TEXT("left") : TEXT("right")), P.Min, P.Max);
			Morph(D, FString::Printf(TEXT("%s_%s"), P.MorphBase, bLeft ? TEXT("L") : TEXT("R")), P.Weight);
			D.MirrorOf = FName(*(bLeft ? IdR : IdL));
			if (P.SculptRegionBase)
			{
				const FString Region = FString(P.SculptRegionBase) + (bLeft ? TEXT("L") : TEXT("R"));
				D.SculptRegion = FName(*Region);
				D.SculptAxis = P.SculptAxis;
			}
			ForPeople(D, People);
		}
	}

	/** Single centre morph slider. */
	inline FLyrisSliderDef& AddMorph(TArray<FLyrisSliderDef>& Arr, FName Cat, FName Sec, const TCHAR* Id, const TCHAR* Name,
		const TCHAR* MorphName, float Weight = 1.f, float Min = -1.f, float Max = 1.f)
	{
		FLyrisSliderDef& D = AddSlider(Arr, Cat, Sec, Id, Name, Min, Max);
		Morph(D, MorphName, Weight);
		return D;
	}

	struct FSw { const TCHAR* Name; const TCHAR* HexCode; };

	inline TArray<FLyrisSwatch> Band(std::initializer_list<FSw> In)
	{
		TArray<FLyrisSwatch> Out;
		Out.Reserve(static_cast<int32>(In.size()));
		for (const FSw& S : In)
		{
			FLyrisSwatch& W = Out.AddDefaulted_GetRef();
			W.DisplayName = Txt(S.Name);
			W.Color = Hex(S.HexCode);
		}
		return Out;
	}

	struct FPt
	{
		const TCHAR* Name;        // id suffix: "RopeBraid" -> "Hair.RopeBraid"
		const TCHAR* Display;
		FName People = NAME_None; // restricted to one People, or None for all
	};

// Adds one slot and its parts. Not a member to keep the header small.
void AddSlotWithParts(ULyrisAppearanceCatalog& C, const TCHAR* Slot, const TCHAR* Cat, const TCHAR* Sec, const TCHAR* Display,
	bool bOptional, const TCHAR* DefaultPartSuffix, bool bMask, const TCHAR* AttachSocket, std::initializer_list<FPt> InParts)
{
	FLyrisPartSlotDef& S = C.Slots.AddDefaulted_GetRef();
	S.Slot = FName(Slot);
	S.Category = FName(Cat);
	S.Section = FName(Sec);
	S.DisplayName = Txt(Display);
	S.bOptional = bOptional;
	S.bMask = bMask;
	S.DefaultPart = DefaultPartSuffix ? FName(*FString::Printf(TEXT("%s.%s"), Slot, DefaultPartSuffix)) : NAME_None;

	for (const FPt& P : InParts)
	{
		FLyrisPartDef& D = C.Parts.AddDefaulted_GetRef();
		D.Id = FName(*FString::Printf(TEXT("%s.%s"), Slot, P.Name));
		D.Slot = FName(Slot);
		D.DisplayName = Txt(P.Display);
		D.AttachSocket = AttachSocket ? FName(AttachSocket) : NAME_None;
		// Meshes and masks stay empty soft pointers until art exists (T25 and later). Ids are still
		// selectable and saved; the component simply spawns nothing for an empty part.
		if (!P.People.IsNone())
		{
			D.People.Add(P.People);
		}
	}
}

void AddChannel(ULyrisAppearanceCatalog& C, const TCHAR* Id, const TCHAR* Cat, const TCHAR* Sec, const TCHAR* Display,
	float MaxHue, float MaxValue, const TCHAR* Param, std::initializer_list<FName> People, TArray<FLyrisSwatch> Swatches)
{
	FLyrisColorChannelDef& D = C.ColorChannels.AddDefaulted_GetRef();
	D.Id = FName(Id);
	D.Category = FName(Cat);
	D.DisplayName = Txt(Display);
	D.Swatches = MoveTemp(Swatches);
	D.MaxHueShift = MaxHue;
	D.MaxValueShift = MaxValue;
	D.MaterialParam = FName(Param);
	for (const FName& P : People) { D.People.Add(P); }
	C.ChannelSections.Add(D.Id, FName(Sec));
}

/** Part scalar (spec 3.7): material param "<Key with . replaced by _>" plus optional morph. */
FLyrisSliderDef& AddPartScalar(ULyrisAppearanceCatalog& C, const TCHAR* Key, const TCHAR* Cat, const TCHAR* Sec, const TCHAR* Display,
	float Min, float Max, float Default, const TCHAR* MorphName = nullptr)
{
	FLyrisSliderDef& D = AddSlider(C.PartScalarDefs, FName(Cat), FName(Sec), Key, Display, Min, Max, Default);
	const FString Param = FString(Key).Replace(TEXT("."), TEXT("_"));
	D.Targets.Add(FLyrisSliderTarget(ELyrisAppearanceTargetKind::MaterialScalar, FName(*Param), FVector::ZeroVector, 1.f));
	if (MorphName)
	{
		Morph(D, MorphName, 1.f);
	}
	return D;
}

/**
 * Tooltips: the "Does (low / high)" column of the spec tables (sections 3.1 to 3.7), keyed by slider or
 * part-scalar id. Generated from design/character_creator.md; regenerate when the spec changes.
 */
void ApplyDefaultDescriptions(ULyrisAppearanceCatalog& C)
{
	struct FDesc { const TCHAR* Id; const TCHAR* Text; };
	static const FDesc Table[] = {
		{ TEXT("Body.Height"), TEXT("shorter / taller") },
		{ TEXT("Body.TorsoLength"), TEXT("short / long torso") },
		{ TEXT("Body.HeadSize"), TEXT("smaller / larger head") },
		{ TEXT("Body.NeckLength"), TEXT("short / long") },
		{ TEXT("Body.NeckThickness"), TEXT("slender / thick") },
		{ TEXT("Body.ShoulderWidth"), TEXT("narrow / broad") },
		{ TEXT("Body.ShoulderSlope"), TEXT("sloped / square") },
		{ TEXT("Body.ChestWidth"), TEXT("narrow / wide") },
		{ TEXT("Body.ChestDepth"), TEXT("flat / deep") },
		{ TEXT("Body.ChestShape"), TEXT("flatter / fuller chest") },
		{ TEXT("Body.WaistWidth"), TEXT("narrow / wide") },
		{ TEXT("Body.HipWidth"), TEXT("narrow / wide") },
		{ TEXT("Body.ArmLength"), TEXT("short / long") },
		{ TEXT("Body.UpperArmThickness"), TEXT("slim / thick") },
		{ TEXT("Body.ForearmThickness"), TEXT("slim / thick") },
		{ TEXT("Body.LegLength"), TEXT("short / long") },
		{ TEXT("Body.ThighThickness"), TEXT("slim / thick") },
		{ TEXT("Body.CalfThickness"), TEXT("slim / thick") },
		{ TEXT("Body.MuscleTone"), TEXT("soft / defined") },
		{ TEXT("Body.Softness"), TEXT("lean / soft and round") },
		{ TEXT("Body.Belly"), TEXT("flat / round") },
		{ TEXT("Body.BackWidth"), TEXT("narrow / broad back") },
		{ TEXT("Body.ShoulderBulk"), TEXT("slight / heavy shoulders") },
		{ TEXT("Body.HipShape"), TEXT("straight / curved") },
		{ TEXT("Body.HandSize"), TEXT("small / large") },
		{ TEXT("Body.FingerLength"), TEXT("short / long") },
		{ TEXT("Body.FootSize"), TEXT("small / large") },
		{ TEXT("Body.NailLength"), TEXT("short / longer, rounded") },
		{ TEXT("Body.Lean"), TEXT("slouched / upright") },
		{ TEXT("Body.HeadCarriage"), TEXT("chin down / chin up") },
		{ TEXT("Body.ShoulderSet"), TEXT("rounded / pulled back") },
		{ TEXT("Body.StanceWidth"), TEXT("narrow / wide feet") },
		{ TEXT("Face.Width"), TEXT("narrow / wide") },
		{ TEXT("Face.Length"), TEXT("short / long") },
		{ TEXT("Face.Roundness"), TEXT("angular / round") },
		{ TEXT("Face.TempleWidth"), TEXT("narrow / wide") },
		{ TEXT("Face.CheekFullness"), TEXT("slim / full") },
		{ TEXT("Face.CheekboneHeight"), TEXT("low / high") },
		{ TEXT("Face.CheekboneWidth"), TEXT("narrow / wide") },
		{ TEXT("Face.CheekboneProminence"), TEXT("soft / defined") },
		{ TEXT("Face.CheekHollow"), TEXT("none / slight hollow") },
		{ TEXT("Face.JawWidth"), TEXT("narrow / wide") },
		{ TEXT("Face.JawAngle"), TEXT("soft / squared corner") },
		{ TEXT("Face.JawHeight"), TEXT("low / high corner") },
		{ TEXT("Face.JawDepth"), TEXT("set back / forward") },
		{ TEXT("Face.ChinWidth"), TEXT("narrow / wide") },
		{ TEXT("Face.ChinLength"), TEXT("short / long") },
		{ TEXT("Face.ChinDepth"), TEXT("receding / forward") },
		{ TEXT("Face.ChinPoint"), TEXT("round / pointed") },
		{ TEXT("Face.ChinCleft"), TEXT("none / soft dimple") },
		{ TEXT("Face.CheekDimples"), TEXT("none / dimples when smiling") },
		{ TEXT("Forehead.Height"), TEXT("low / high") },
		{ TEXT("Forehead.Width"), TEXT("narrow / wide") },
		{ TEXT("Forehead.Slope"), TEXT("upright / sloped") },
		{ TEXT("Forehead.Roundness"), TEXT("flat / rounded") },
		{ TEXT("Forehead.BrowRidge"), TEXT("smooth / pronounced") },
		{ TEXT("Eyes.SizeL"), TEXT("smaller / larger") },
		{ TEXT("Eyes.SizeR"), TEXT("smaller / larger") },
		{ TEXT("Eyes.Spacing"), TEXT("close / wide") },
		{ TEXT("Eyes.HeightL"), TEXT("lower / higher") },
		{ TEXT("Eyes.HeightR"), TEXT("lower / higher") },
		{ TEXT("Eyes.TiltL"), TEXT("outer corner down / up") },
		{ TEXT("Eyes.TiltR"), TEXT("outer corner down / up") },
		{ TEXT("Eyes.Depth"), TEXT("prominent / deep-set") },
		{ TEXT("Eyes.Roundness"), TEXT("almond / round") },
		{ TEXT("Eyes.UpperLidL"), TEXT("heavy / open") },
		{ TEXT("Eyes.UpperLidR"), TEXT("heavy / open") },
		{ TEXT("Eyes.LidCrease"), TEXT("monolid / deep double lid") },
		{ TEXT("Eyes.LowerLidL"), TEXT("low curve / high, straight") },
		{ TEXT("Eyes.LowerLidR"), TEXT("low curve / high, straight") },
		{ TEXT("Eyes.InnerCornerL"), TEXT("rounded, low / pointed, high") },
		{ TEXT("Eyes.InnerCornerR"), TEXT("rounded, low / pointed, high") },
		{ TEXT("Eyes.OuterCornerL"), TEXT("rounded / sharp, extended") },
		{ TEXT("Eyes.OuterCornerR"), TEXT("rounded / sharp, extended") },
		{ TEXT("Eyes.UnderEyeFullness"), TEXT("flat / soft pillow under the eye") },
		{ TEXT("Eyes.IrisSize"), TEXT("smaller / larger") },
		{ TEXT("Eyes.PupilSize"), TEXT("small / large") },
		{ TEXT("Brows.HeightL"), TEXT("low / high") },
		{ TEXT("Brows.HeightR"), TEXT("low / high") },
		{ TEXT("Brows.TiltL"), TEXT("outer end down / up") },
		{ TEXT("Brows.TiltR"), TEXT("outer end down / up") },
		{ TEXT("Brows.ArchL"), TEXT("flat / high arch") },
		{ TEXT("Brows.ArchR"), TEXT("flat / high arch") },
		{ TEXT("Brows.Thickness"), TEXT("fine / thick") },
		{ TEXT("Brows.Spacing"), TEXT("close / far apart") },
		{ TEXT("Brows.Length"), TEXT("short / long tail") },
		{ TEXT("Nose.BridgeHeight"), TEXT("low, flat / high") },
		{ TEXT("Nose.BridgeWidth"), TEXT("narrow / wide") },
		{ TEXT("Nose.BridgeCurve"), TEXT("scooped / arched") },
		{ TEXT("Nose.Length"), TEXT("short / long") },
		{ TEXT("Nose.Height"), TEXT("lower / higher") },
		{ TEXT("Nose.Projection"), TEXT("flat / prominent") },
		{ TEXT("Nose.TipSize"), TEXT("small / large") },
		{ TEXT("Nose.TipLift"), TEXT("down-turned / up-turned") },
		{ TEXT("Nose.TipShape"), TEXT("round, button / defined, pointed") },
		{ TEXT("Nose.NostrilWidth"), TEXT("narrow / wide") },
		{ TEXT("Nose.NostrilFlare"), TEXT("tucked / flared") },
		{ TEXT("Nose.NostrilHeight"), TEXT("low / high wings") },
		{ TEXT("Nose.Bend"), TEXT("bends left / right") },
		{ TEXT("Mouth.Width"), TEXT("narrow / wide") },
		{ TEXT("Mouth.Height"), TEXT("lower / higher") },
		{ TEXT("Mouth.Depth"), TEXT("set back / forward") },
		{ TEXT("Mouth.UpperLipFullness"), TEXT("thin / full") },
		{ TEXT("Mouth.LowerLipFullness"), TEXT("thin / full") },
		{ TEXT("Mouth.CupidsBow"), TEXT("soft / sharp") },
		{ TEXT("Mouth.LipOffset"), TEXT("lower lip forward / upper lip forward") },
		{ TEXT("Mouth.CornerLiftL"), TEXT("down / up") },
		{ TEXT("Mouth.CornerLiftR"), TEXT("down / up") },
		{ TEXT("Mouth.PhiltrumDepth"), TEXT("flat / defined groove") },
		{ TEXT("Mouth.PhiltrumLength"), TEXT("short / long") },
		{ TEXT("Ears.SizeL"), TEXT("small / large") },
		{ TEXT("Ears.SizeR"), TEXT("small / large") },
		{ TEXT("Ears.AngleL"), TEXT("flat to head / stick out") },
		{ TEXT("Ears.AngleR"), TEXT("flat to head / stick out") },
		{ TEXT("Ears.Height"), TEXT("low / high on head") },
		{ TEXT("Ears.Lobe"), TEXT("attached, small / free, large") },
		{ TEXT("Ears.TipL"), TEXT("round / slight point") },
		{ TEXT("Ears.TipR"), TEXT("round / slight point") },
		{ TEXT("Ears.PointL"), TEXT("short / long point") },
		{ TEXT("Ears.PointR"), TEXT("short / long point") },
		{ TEXT("Ears.PointAngleL"), TEXT("swept back / upright") },
		{ TEXT("Ears.PointAngleR"), TEXT("swept back / upright") },
		{ TEXT("Ears.DroopL"), TEXT("none / tip droops") },
		{ TEXT("Ears.DroopR"), TEXT("none / tip droops") },
		{ TEXT("Ears.FinSpreadL"), TEXT("folded / fanned fin-ear") },
		{ TEXT("Ears.FinSpreadR"), TEXT("folded / fanned fin-ear") },
		{ TEXT("Lashes.Length"), TEXT("short / long") },
		{ TEXT("Lashes.Curl"), TEXT("straight / curled") },
		{ TEXT("Iris.LimbalRing"), TEXT("none / dark ring round the iris") },
		{ TEXT("Iris.Catchlight"), TEXT("small / large painted highlight") },
		{ TEXT("Eyes.GlowStrength"), TEXT("none / soft moonlit glow") },
		{ TEXT("Eyes.ShineStrength"), TEXT("none / eyes catch the light in the dark") },
		{ TEXT("Skin.Undertone"), TEXT("cooler / warmer") },
		{ TEXT("Skin.Rosiness"), TEXT("none / rosy cheeks, nose tip, knuckles") },
		{ TEXT("Skin.Sheen"), TEXT("matte / soft dewy highlight") },
		{ TEXT("Skin.AgeLines"), TEXT("none / soft painted lines (laugh lines, crow's feet, brow)") },
		{ TEXT("Skin.Moonglow"), TEXT("none / skin softly luminous in moonlight and mist") },
		{ TEXT("Voice.Pitch"), TEXT("lower / higher") },
		{ TEXT("Hair.Length"), TEXT("Shorter / longer, within what the style allows (morph on the hair mesh)") },
		{ TEXT("Hair.Volume"), TEXT("Flatter / fuller") },
		{ TEXT("Hair.GradientStart"), TEXT("Where the root colour starts fading to the tip colour (1 = no gradient)") },
		{ TEXT("Hair.GradientSoftness"), TEXT("Hard dip-dye line / soft blend") },
		{ TEXT("Hair.HighlightAmount"), TEXT("How many painted highlight streaks") },
		{ TEXT("Hair.Shine"), TEXT("Painted shine band strength (matte to glossy storybook ribbon)") },
		{ TEXT("Brows.MatchHair"), TEXT("Brows follow Hair.Root; when 0, Hair.Brows is used") },
		{ TEXT("Brows.Density"), TEXT("Sparse / dense brow") },
		{ TEXT("FacialHair.Length"), TEXT("Shorter / longer") },
		{ TEXT("FacialHair.MatchHair"), TEXT("Facial hair follows Hair.Root") },
		{ TEXT("Eyes.Heterochromia"), TEXT("Different iris colour per eye") },
		{ TEXT("Freckles.Density"), TEXT("How many freckles in the chosen set") },
		{ TEXT("Freckles.Opacity"), TEXT("How strong they read") },
		{ TEXT("Scars.Opacity"), TEXT("Max 0.8 in the UI: scars are healed and soft") },
		{ TEXT("Markings.Glow"), TEXT("MoonlitElf sigils glow at night and in mist") },
		{ TEXT("Markings.Shimmer"), TEXT("Deepkin scale patches shimmer, more when wet") },
		{ TEXT("Makeup.Lips.Gloss"), TEXT("Matte / glossy painted highlight") },
		{ TEXT("Outfit.Wear"), TEXT("Crisp and new / well-travelled (patches, faded hems)") },
	};
	TMap<FName, const TCHAR*> ById;
	for (const FDesc& D : Table)
	{
		ById.Add(FName(D.Id), D.Text);
	}
	for (TArray<FLyrisSliderDef>* Arr : { &C.Sliders, &C.PartScalarDefs })
	{
		for (FLyrisSliderDef& S : *Arr)
		{
			if (const TCHAR* const* Text = ById.Find(S.Id))
			{
				S.Description = FText::FromString(*Text);
			}
		}
	}
}

} // namespace LyrisCatalogBuild

// =====================================================================================================
// Default content
// =====================================================================================================

void ULyrisAppearanceCatalog::BuildDefaultContent()
{
	using namespace LyrisCatalogBuild;
	Sliders.Reset();
	Parts.Reset();
	ColorChannels.Reset();
	PartScalarDefs.Reset();
	Slots.Reset();
	Sections.Reset();
	ChannelSections.Reset();
	FrameMeshes.Reset();

	Peoples = { LyrisPeople::Human, LyrisPeople::MoonlitElf, LyrisPeople::Deepkin };
	Frames  = { LyrisFrames::FrameA, LyrisFrames::FrameB };

	BuildSections();
	BuildBody();
	BuildFace();
	BuildEyes();
	BuildHair();
	BuildSkin();
	BuildMakeup();
	BuildOutfit();
	BuildVoice();
	BuildLantern();

	RebuildIndex();
	ApplyDefaultDescriptions(*this);
}

void ULyrisAppearanceCatalog::BuildSections()
{
	using namespace LyrisCatalogBuild;
	struct FSec { const TCHAR* Cat; const TCHAR* Sec; const TCHAR* Display; const TCHAR* Framing; };
	const FSec List[] = {
		{ TEXT("Body"),    TEXT("Frame"),       TEXT("Frame & height"),        TEXT("Full") },
		{ TEXT("Body"),    TEXT("Proportions"), TEXT("Proportions"),           TEXT("Full") },
		{ TEXT("Body"),    TEXT("Build"),       TEXT("Build"),                 TEXT("Full") },
		{ TEXT("Body"),    TEXT("HandsFeet"),   TEXT("Hands & feet"),          TEXT("Upper") },
		{ TEXT("Body"),    TEXT("Posture"),     TEXT("Posture"),               TEXT("Full") },
		{ TEXT("Face"),    TEXT("Shape"),       TEXT("Shape"),                 TEXT("Face") },
		{ TEXT("Face"),    TEXT("Forehead"),    TEXT("Forehead & brow ridge"), TEXT("Face") },
		{ TEXT("Face"),    TEXT("Eyes"),        TEXT("Eyes"),                  TEXT("Eyes") },
		{ TEXT("Face"),    TEXT("Brows"),       TEXT("Brows"),                 TEXT("Eyes") },
		{ TEXT("Face"),    TEXT("Nose"),        TEXT("Nose"),                  TEXT("Face") },
		{ TEXT("Face"),    TEXT("Mouth"),       TEXT("Mouth"),                 TEXT("Face") },
		{ TEXT("Face"),    TEXT("Ears"),        TEXT("Ears"),                  TEXT("Face") },
		{ TEXT("Eyes"),    TEXT("Colour"),      TEXT("Colour"),                TEXT("Eyes") },
		{ TEXT("Eyes"),    TEXT("Detail"),      TEXT("Detail"),                TEXT("Eyes") },
		{ TEXT("Hair"),    TEXT("Style"),       TEXT("Style"),                 TEXT("Upper") },
		{ TEXT("Hair"),    TEXT("Colour"),      TEXT("Colour"),                TEXT("Face") },
		{ TEXT("Hair"),    TEXT("Brows"),       TEXT("Brows"),                 TEXT("Face") },
		{ TEXT("Hair"),    TEXT("FacialHair"),  TEXT("Facial hair"),           TEXT("Face") },
		{ TEXT("Hair"),    TEXT("Accessories"), TEXT("Accessories"),           TEXT("Upper") },
		{ TEXT("Skin"),    TEXT("Tone"),        TEXT("Tone"),                  TEXT("Face") },
		{ TEXT("Skin"),    TEXT("Details"),     TEXT("Details"),               TEXT("Face") },
		{ TEXT("Skin"),    TEXT("Markings"),    TEXT("Markings"),              TEXT("Upper") },
		{ TEXT("Makeup"),  TEXT("Eyes"),        TEXT("Eyes"),                  TEXT("Eyes") },
		{ TEXT("Makeup"),  TEXT("Lips"),        TEXT("Lips"),                  TEXT("Face") },
		{ TEXT("Makeup"),  TEXT("Cheeks"),      TEXT("Cheeks"),                TEXT("Face") },
		{ TEXT("Makeup"),  TEXT("FacePaint"),   TEXT("Face paint"),            TEXT("Face") },
		{ TEXT("Outfit"),  TEXT("Outfit"),      TEXT("Outfit"),                TEXT("Full") },
		{ TEXT("Outfit"),  TEXT("Layer"),       TEXT("Cloak & scarf"),         TEXT("Full") },
		{ TEXT("Voice"),   TEXT("Voice"),       TEXT("Voice"),                 TEXT("Full") },
		{ TEXT("Voice"),   TEXT("Expression"),  TEXT("Expression"),            TEXT("Upper") },
		// Step 5 only, never an Appearance tab (GetCategories() leaves it out).
		{ TEXT("Lantern"), TEXT("Lantern"),     TEXT("Lantern"),               TEXT("Lantern") },
	};
	for (const FSec& S : List)
	{
		FLyrisSectionDef& D = Sections.AddDefaulted_GetRef();
		D.Category = FName(S.Cat);
		D.Section = FName(S.Sec);
		D.DisplayName = Txt(S.Display);
		D.Framing = FName(S.Framing);
	}
}

// -----------------------------------------------------------------------------------------------------
// Body (32 sliders, slot Stance). Bone targets work on the template mannequin today; morphs wait for T25.
// BoneScale rule (see ULyrisAppearanceAnimInstance): a UNIFORM scale scales the bone and everything below
// it; a NON-UNIFORM scale only scales that bone's own segment (children follow its new length but keep
// their size). So "Height" is a uniform root scale, limb lengths/thickness are non-uniform.
// -----------------------------------------------------------------------------------------------------
void ULyrisAppearanceCatalog::BuildBody()
{
	using namespace LyrisCatalogBuild;
	const FName Cat(TEXT("Body"));
	const FName Frame(TEXT("Frame")), Prop(TEXT("Proportions")), Build(TEXT("Build")), Hands(TEXT("HandsFeet")), Posture(TEXT("Posture"));
	TArray<FLyrisSliderDef>& A = Sliders;

	// Frame & height
	{
		// Spec lists pelvis; root is used instead so the whole body grows from the floor (a pelvis
		// scale would push the feet through the ground).
		FLyrisSliderDef& D = AddSlider(A, Cat, Frame, TEXT("Body.Height"), TEXT("Height"));
		Bone(D, EKind::BoneScale, TEXT("root"), Uniform, 0.08f);
		Morph(D, TEXT("Body_Height"));
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Frame, TEXT("Body.TorsoLength"), TEXT("Torso length"));
		Bone(D, EKind::BoneScale, TEXT("spine_02"), AlongBone, 0.08f);
		Bone(D, EKind::BoneScale, TEXT("spine_03"), AlongBone, 0.08f);
		Bone(D, EKind::BoneScale, TEXT("spine_04"), AlongBone, 0.08f);
	}

	// Proportions (16)
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.HeadSize"), TEXT("Head size"));
		Bone(D, EKind::BoneScale, TEXT("head"), Uniform, 0.08f); // adult guard caps it, see ApplyAdultGuard
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.NeckLength"), TEXT("Neck length"));
		Bone(D, EKind::BoneScale, TEXT("neck_01"), AlongBone, 0.15f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.NeckThickness"), TEXT("Neck thickness"));
		Bone(D, EKind::BoneScale, TEXT("neck_01"), Cross, 0.15f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.ShoulderWidth"), TEXT("Shoulder width"));
		BonePair(D, EKind::BoneOffset, TEXT("clavicle"), CentreSide, 3.f); // +-3 cm per side
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.ShoulderSlope"), TEXT("Shoulder slope"));
		BonePair(D, EKind::BoneRotation, TEXT("clavicle"), RotAboutFront, 8.f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.ChestWidth"), TEXT("Chest width"));
		Bone(D, EKind::BoneScale, TEXT("spine_04"), CentreSide, 0.10f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.ChestDepth"), TEXT("Chest depth"));
		Bone(D, EKind::BoneScale, TEXT("spine_04"), CentreFront, 0.10f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.ChestShape"), TEXT("Chest shape"));
		Bone(D, EKind::BoneScale, TEXT("spine_05"), CentreFront, 0.12f);
		Morph(D, TEXT("Chest_Full"));
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.WaistWidth"), TEXT("Waist width"));
		Bone(D, EKind::BoneScale, TEXT("spine_01"), Cross, 0.12f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.HipWidth"), TEXT("Hip width"));
		Bone(D, EKind::BoneScale, TEXT("pelvis"), CentreSide, 0.12f);
		BonePair(D, EKind::BoneOffset, TEXT("thigh"), CentreSide, 1.5f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.ArmLength"), TEXT("Arm length"));
		BonePair(D, EKind::BoneScale, TEXT("upperarm"), AlongBone, 0.08f);
		BonePair(D, EKind::BoneScale, TEXT("lowerarm"), AlongBone, 0.08f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.UpperArmThickness"), TEXT("Upper arm"));
		BonePair(D, EKind::BoneScale, TEXT("upperarm"), Cross, 0.15f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.ForearmThickness"), TEXT("Forearm"));
		BonePair(D, EKind::BoneScale, TEXT("lowerarm"), Cross, 0.15f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.LegLength"), TEXT("Leg length"));
		BonePair(D, EKind::BoneScale, TEXT("thigh"), AlongBone, 0.08f);
		BonePair(D, EKind::BoneScale, TEXT("calf"), AlongBone, 0.08f);
		// Longer legs would push the feet into the ground: lift the pelvis by 8% of thigh+calf (~85 cm).
		Bone(D, EKind::BoneOffset, TEXT("pelvis"), Up, 6.8f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.ThighThickness"), TEXT("Thigh"));
		BonePair(D, EKind::BoneScale, TEXT("thigh"), Cross, 0.15f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Prop, TEXT("Body.CalfThickness"), TEXT("Calf"));
		BonePair(D, EKind::BoneScale, TEXT("calf"), Cross, 0.15f);
	}

	// Build (6). Painted shapes only: no veins, striations or skin folds.
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Build, TEXT("Body.MuscleTone"), TEXT("Muscle tone"));
		Morph(D, TEXT("Muscle_Tone"));
		Mat(D, TEXT("MuscleDefinition"), 1.f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Build, TEXT("Body.Softness"), TEXT("Softness"));
		Morph(D, TEXT("Body_Soft"));
		Bone(D, EKind::BoneScale, TEXT("spine_01"), Cross, 0.10f);
		Bone(D, EKind::BoneScale, TEXT("spine_02"), Cross, 0.10f);
		Bone(D, EKind::BoneScale, TEXT("spine_03"), Cross, 0.10f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Build, TEXT("Body.Belly"), TEXT("Belly"));
		Morph(D, TEXT("Belly"));
		Bone(D, EKind::BoneScale, TEXT("spine_01"), CentreFront, 0.10f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Build, TEXT("Body.BackWidth"), TEXT("Back width"));
		Bone(D, EKind::BoneScale, TEXT("spine_03"), CentreSide, 0.10f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Build, TEXT("Body.ShoulderBulk"), TEXT("Shoulder bulk"));
		BonePair(D, EKind::BoneScale, TEXT("upperarm"), Cross, 0.12f);
		Morph(D, TEXT("Shoulder_Bulk"));
	}
	AddMorph(A, Cat, Build, TEXT("Body.HipShape"), TEXT("Hip shape"), TEXT("Hip_Curve"));

	// Hands & feet (4)
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Hands, TEXT("Body.HandSize"), TEXT("Hand size"));
		BonePair(D, EKind::BoneScale, TEXT("hand"), Uniform, 0.12f);
	}
	AddMorph(A, Cat, Hands, TEXT("Body.FingerLength"), TEXT("Finger length"), TEXT("Finger_Length"));
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Hands, TEXT("Body.FootSize"), TEXT("Foot size"));
		BonePair(D, EKind::BoneScale, TEXT("foot"), Uniform, 0.12f);
	}
	AddMorph(A, Cat, Hands, TEXT("Body.NailLength"), TEXT("Nails"), TEXT("Nail_Length"), 1.f, 0.f, 1.f);

	// Posture (4): offsets on top of the Stance part
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Posture, TEXT("Body.Lean"), TEXT("Lean"));
		Bone(D, EKind::BoneRotation, TEXT("spine_02"), RotAboutSide, 6.f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Posture, TEXT("Body.HeadCarriage"), TEXT("Head carriage"));
		Bone(D, EKind::BoneRotation, TEXT("neck_01"), RotAboutSide, 5.f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Posture, TEXT("Body.ShoulderSet"), TEXT("Shoulder set"));
		BonePair(D, EKind::BoneRotation, TEXT("clavicle"), FVector(0.f, 1.f, 0.f) /*yaw*/, 5.f);
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Posture, TEXT("Body.StanceWidth"), TEXT("Stance width"));
		BonePair(D, EKind::BoneRotation, TEXT("thigh"), RotAboutFront, 4.f);
	}

	AddSlotWithParts(*this, TEXT("Stance"), TEXT("Body"), TEXT("Posture"), TEXT("Idle stance"), false, TEXT("Easy"), false, nullptr, {
		{ TEXT("Easy"), TEXT("Easy") }, { TEXT("Upright"), TEXT("Upright") }, { TEXT("ArmsFolded"), TEXT("Arms folded") },
		{ TEXT("HandOnHip"), TEXT("Hand on hip") }, { TEXT("Shy"), TEXT("Shy") }, { TEXT("SeaLegs"), TEXT("Sea legs") },
		{ TEXT("Bookish"), TEXT("Bookish") },
	});
}

// -----------------------------------------------------------------------------------------------------
// Face (94 sliders): morph names for the T25 mesh. The template mannequin has no face bones, so only a
// few sliders also nudge the head bone (Face.Width, Face.Length, Face.Roundness) to show something today.
// -----------------------------------------------------------------------------------------------------
void ULyrisAppearanceCatalog::BuildFace()
{
	using namespace LyrisCatalogBuild;
	const FName Cat(TEXT("Face"));
	const FName Shape(TEXT("Shape")), Fore(TEXT("Forehead")), Eyes(TEXT("Eyes")), Brows(TEXT("Brows")),
		Nose(TEXT("Nose")), Mouth(TEXT("Mouth")), Ears(TEXT("Ears"));
	TArray<FLyrisSliderDef>& A = Sliders;
	const uint8 H = 0, V = 1;

	// Shape (19)
	{
		FLyrisSliderDef& D = AddMorph(A, Cat, Shape, TEXT("Face.Width"), TEXT("Face width"), TEXT("Face_Width"));
		Bone(D, EKind::BoneScale, TEXT("head"), CentreSide, 0.04f);
	}
	{
		FLyrisSliderDef& D = AddMorph(A, Cat, Shape, TEXT("Face.Length"), TEXT("Face length"), TEXT("Face_Length"));
		Bone(D, EKind::BoneScale, TEXT("head"), AlongBone, 0.04f);
		Sculpt(D, TEXT("Chin"), V);
	}
	{
		FLyrisSliderDef& D = AddMorph(A, Cat, Shape, TEXT("Face.Roundness"), TEXT("Roundness"), TEXT("Face_Round"));
		Bone(D, EKind::BoneScale, TEXT("head"), CentreFront, 0.03f);
	}
	Sculpt(AddMorph(A, Cat, Shape, TEXT("Face.TempleWidth"), TEXT("Temples"), TEXT("Temple_Width"), 0.8f), TEXT("Forehead"), H);
	Sculpt(AddMorph(A, Cat, Shape, TEXT("Face.CheekFullness"), TEXT("Cheek fullness"), TEXT("Cheek_Full")), TEXT("Cheeks"), V);
	AddMorph(A, Cat, Shape, TEXT("Face.CheekboneHeight"), TEXT("Cheekbone height"), TEXT("Cheekbone_Height"));
	Sculpt(AddMorph(A, Cat, Shape, TEXT("Face.CheekboneWidth"), TEXT("Cheekbone width"), TEXT("Cheekbone_Width")), TEXT("Cheeks"), H);
	AddMorph(A, Cat, Shape, TEXT("Face.CheekboneProminence"), TEXT("Cheekbones"), TEXT("Cheekbone_Prom"), 0.8f);
	AddMorph(A, Cat, Shape, TEXT("Face.CheekHollow"), TEXT("Cheek hollow"), TEXT("Cheek_Hollow"), 0.5f, 0.f, 1.f); // never gaunt
	Sculpt(AddMorph(A, Cat, Shape, TEXT("Face.JawWidth"), TEXT("Jaw width"), TEXT("Jaw_Width")), TEXT("Jaw"), H);
	AddMorph(A, Cat, Shape, TEXT("Face.JawAngle"), TEXT("Jaw angle"), TEXT("Jaw_Angle"));
	Sculpt(AddMorph(A, Cat, Shape, TEXT("Face.JawHeight"), TEXT("Jaw corner height"), TEXT("Jaw_Height")), TEXT("Jaw"), V);
	AddMorph(A, Cat, Shape, TEXT("Face.JawDepth"), TEXT("Jaw depth"), TEXT("Jaw_Depth"), 0.8f);
	Sculpt(AddMorph(A, Cat, Shape, TEXT("Face.ChinWidth"), TEXT("Chin width"), TEXT("Chin_Width")), TEXT("Chin"), H);
	AddMorph(A, Cat, Shape, TEXT("Face.ChinLength"), TEXT("Chin length"), TEXT("Chin_Length"));
	AddMorph(A, Cat, Shape, TEXT("Face.ChinDepth"), TEXT("Chin depth"), TEXT("Chin_Depth"), 0.8f);
	AddMorph(A, Cat, Shape, TEXT("Face.ChinPoint"), TEXT("Chin shape"), TEXT("Chin_Point"));
	AddMorph(A, Cat, Shape, TEXT("Face.ChinCleft"), TEXT("Chin cleft"), TEXT("Chin_Cleft"), 0.6f, 0.f, 1.f);
	AddMorph(A, Cat, Shape, TEXT("Face.CheekDimples"), TEXT("Dimples"), TEXT("Cheek_Dimple"), 1.f, 0.f, 1.f);

	// Forehead & brow ridge (5)
	Sculpt(AddMorph(A, Cat, Fore, TEXT("Forehead.Height"), TEXT("Forehead height"), TEXT("Forehead_Height")), TEXT("Forehead"), V);
	AddMorph(A, Cat, Fore, TEXT("Forehead.Width"), TEXT("Forehead width"), TEXT("Forehead_Width"), 0.8f);
	AddMorph(A, Cat, Fore, TEXT("Forehead.Slope"), TEXT("Forehead slope"), TEXT("Forehead_Slope"), 0.8f);
	AddMorph(A, Cat, Fore, TEXT("Forehead.Roundness"), TEXT("Forehead roundness"), TEXT("Forehead_Round"), 0.8f);
	AddMorph(A, Cat, Fore, TEXT("Forehead.BrowRidge"), TEXT("Brow ridge"), TEXT("BrowRidge_Prom"), 0.7f);

	// Eyes, shape (21). Colour lives in the Eyes category.
	AddPair(A, Cat, Eyes, { TEXT("Eyes.Size"), TEXT("Eye size"), TEXT("Eye_Size"), 1.f, -1.f, 1.f, TEXT("Eye"), V });
	AddMorph(A, Cat, Eyes, TEXT("Eyes.Spacing"), TEXT("Eye spacing"), TEXT("Eye_Spacing"));
	AddPair(A, Cat, Eyes, { TEXT("Eyes.Height"), TEXT("Eye height"), TEXT("Eye_Height") });
	AddPair(A, Cat, Eyes, { TEXT("Eyes.Tilt"), TEXT("Eye tilt"), TEXT("Eye_Tilt") });
	AddMorph(A, Cat, Eyes, TEXT("Eyes.Depth"), TEXT("Eye depth"), TEXT("Eye_Depth"), 0.8f);
	AddMorph(A, Cat, Eyes, TEXT("Eyes.Roundness"), TEXT("Eye shape"), TEXT("Eye_Round"));
	AddPair(A, Cat, Eyes, { TEXT("Eyes.UpperLid"), TEXT("Upper lid"), TEXT("Lid_Upper") });
	AddMorph(A, Cat, Eyes, TEXT("Eyes.LidCrease"), TEXT("Lid crease"), TEXT("Lid_Crease"));
	AddPair(A, Cat, Eyes, { TEXT("Eyes.LowerLid"), TEXT("Lower lid"), TEXT("Lid_Lower") });
	AddPair(A, Cat, Eyes, { TEXT("Eyes.InnerCorner"), TEXT("Inner corner"), TEXT("Eye_Inner") });
	AddPair(A, Cat, Eyes, { TEXT("Eyes.OuterCorner"), TEXT("Outer corner"), TEXT("Eye_Outer"), 1.f, -1.f, 1.f, TEXT("Eye"), H });
	AddMorph(A, Cat, Eyes, TEXT("Eyes.UnderEyeFullness"), TEXT("Under-eye fullness"), TEXT("UnderEye_Full"), 0.7f, 0.f, 1.f);
	Mat(AddSlider(A, Cat, Eyes, TEXT("Eyes.IrisSize"), TEXT("Iris size")), TEXT("IrisScale"), 0.12f);
	Mat(AddSlider(A, Cat, Eyes, TEXT("Eyes.PupilSize"), TEXT("Pupil size")), TEXT("PupilScale"), 0.25f);

	// Brows, placement (9). The brow part and colour are in Hair.
	AddPair(A, Cat, Brows, { TEXT("Brows.Height"), TEXT("Brow height"), TEXT("Brow_Height"), 1.f, -1.f, 1.f, TEXT("Brow"), V });
	AddPair(A, Cat, Brows, { TEXT("Brows.Tilt"), TEXT("Brow tilt"), TEXT("Brow_Tilt"), 1.f, -1.f, 1.f, TEXT("Brow"), H });
	AddPair(A, Cat, Brows, { TEXT("Brows.Arch"), TEXT("Brow arch"), TEXT("Brow_Arch") });
	Mat(AddSlider(A, Cat, Brows, TEXT("Brows.Thickness"), TEXT("Brow thickness")), TEXT("BrowThickness"), 0.4f);
	AddMorph(A, Cat, Brows, TEXT("Brows.Spacing"), TEXT("Brow spacing"), TEXT("Brow_Spacing"), 0.8f);
	Mat(AddSlider(A, Cat, Brows, TEXT("Brows.Length"), TEXT("Brow length")), TEXT("BrowLength"), 0.25f);

	// Nose (13)
	AddMorph(A, Cat, Nose, TEXT("Nose.BridgeHeight"), TEXT("Bridge height"), TEXT("NoseBridge_Height"));
	Sculpt(AddMorph(A, Cat, Nose, TEXT("Nose.BridgeWidth"), TEXT("Bridge width"), TEXT("NoseBridge_Width")), TEXT("Nose"), H);
	AddMorph(A, Cat, Nose, TEXT("Nose.BridgeCurve"), TEXT("Bridge profile"), TEXT("NoseBridge_Curve"), 0.8f);
	AddMorph(A, Cat, Nose, TEXT("Nose.Length"), TEXT("Nose length"), TEXT("Nose_Length"));
	Sculpt(AddMorph(A, Cat, Nose, TEXT("Nose.Height"), TEXT("Nose position"), TEXT("Nose_Height"), 0.8f), TEXT("Nose"), V);
	AddMorph(A, Cat, Nose, TEXT("Nose.Projection"), TEXT("Projection"), TEXT("Nose_Projection"), 0.8f);
	AddMorph(A, Cat, Nose, TEXT("Nose.TipSize"), TEXT("Tip size"), TEXT("NoseTip_Size"));
	AddMorph(A, Cat, Nose, TEXT("Nose.TipLift"), TEXT("Tip lift"), TEXT("NoseTip_Lift"));
	AddMorph(A, Cat, Nose, TEXT("Nose.TipShape"), TEXT("Tip shape"), TEXT("NoseTip_Shape"));
	AddMorph(A, Cat, Nose, TEXT("Nose.NostrilWidth"), TEXT("Nostril width"), TEXT("Nostril_Width"));
	AddMorph(A, Cat, Nose, TEXT("Nose.NostrilFlare"), TEXT("Nostril flare"), TEXT("Nostril_Flare"), 0.8f);
	AddMorph(A, Cat, Nose, TEXT("Nose.NostrilHeight"), TEXT("Nostril height"), TEXT("Nostril_Height"), 0.7f);
	AddMorph(A, Cat, Nose, TEXT("Nose.Bend"), TEXT("Bend"), TEXT("Nose_Bend"), 0.4f); // a hint, never broken

	// Mouth (11)
	Sculpt(AddMorph(A, Cat, Mouth, TEXT("Mouth.Width"), TEXT("Mouth width"), TEXT("Mouth_Width")), TEXT("Mouth"), H);
	Sculpt(AddMorph(A, Cat, Mouth, TEXT("Mouth.Height"), TEXT("Mouth position"), TEXT("Mouth_Height"), 0.8f), TEXT("Mouth"), V);
	AddMorph(A, Cat, Mouth, TEXT("Mouth.Depth"), TEXT("Mouth depth"), TEXT("Mouth_Depth"), 0.7f);
	AddMorph(A, Cat, Mouth, TEXT("Mouth.UpperLipFullness"), TEXT("Upper lip"), TEXT("LipUpper_Full"));
	AddMorph(A, Cat, Mouth, TEXT("Mouth.LowerLipFullness"), TEXT("Lower lip"), TEXT("LipLower_Full"));
	AddMorph(A, Cat, Mouth, TEXT("Mouth.CupidsBow"), TEXT("Cupid's bow"), TEXT("Lip_CupidsBow"));
	AddMorph(A, Cat, Mouth, TEXT("Mouth.LipOffset"), TEXT("Bite"), TEXT("Lip_Offset"), 0.5f);
	// Corner lift: spec morph names are MouthCorner_L/_R (no "Lift" in the morph), so build the pair by hand.
	for (int32 Side = 0; Side < 2; ++Side)
	{
		const bool bLeft = (Side == 0);
		FLyrisSliderDef& D = AddSlider(A, Cat, Mouth, bLeft ? TEXT("Mouth.CornerLiftL") : TEXT("Mouth.CornerLiftR"),
			bLeft ? TEXT("Corner, left") : TEXT("Corner, right"));
		Morph(D, bLeft ? TEXT("MouthCorner_L") : TEXT("MouthCorner_R")); // a resting hint, not a grin
		D.MirrorOf = FName(bLeft ? TEXT("Mouth.CornerLiftR") : TEXT("Mouth.CornerLiftL"));
	}
	AddMorph(A, Cat, Mouth, TEXT("Mouth.PhiltrumDepth"), TEXT("Philtrum"), TEXT("Philtrum_Depth"), 0.7f);
	AddMorph(A, Cat, Mouth, TEXT("Mouth.PhiltrumLength"), TEXT("Philtrum length"), TEXT("Philtrum_Length"), 0.8f);

	// Ears (16). Long points for Moonlit elves and Deepkin, droop for elves, fin-ears for Deepkin.
	AddPair(A, Cat, Ears, { TEXT("Ears.Size"), TEXT("Ear size"), TEXT("Ear_Size"), 1.f, -1.f, 1.f, TEXT("Ear"), V });
	AddPair(A, Cat, Ears, { TEXT("Ears.Angle"), TEXT("Ear angle"), TEXT("Ear_Angle"), 1.f, -1.f, 1.f, TEXT("Ear"), H });
	AddMorph(A, Cat, Ears, TEXT("Ears.Height"), TEXT("Ear height"), TEXT("Ear_Height"), 0.7f);
	AddMorph(A, Cat, Ears, TEXT("Ears.Lobe"), TEXT("Ear lobe"), TEXT("Ear_Lobe"));
	AddPair(A, Cat, Ears, { TEXT("Ears.Tip"), TEXT("Ear tip"), TEXT("Ear_Tip"), 1.f, 0.f, 1.f });
	AddPair(A, Cat, Ears, { TEXT("Ears.Point"), TEXT("Point length"), TEXT("Ear_Point"), 1.f, 0.f, 1.f }, { LyrisPeople::MoonlitElf, LyrisPeople::Deepkin });
	AddPair(A, Cat, Ears, { TEXT("Ears.PointAngle"), TEXT("Point angle"), TEXT("Ear_PointAngle") }, { LyrisPeople::MoonlitElf, LyrisPeople::Deepkin });
	AddPair(A, Cat, Ears, { TEXT("Ears.Droop"), TEXT("Droop"), TEXT("Ear_Droop"), 0.6f, 0.f, 1.f }, { LyrisPeople::MoonlitElf });
	AddPair(A, Cat, Ears, { TEXT("Ears.FinSpread"), TEXT("Fin spread"), TEXT("Ear_Fin"), 1.f, 0.f, 1.f }, { LyrisPeople::Deepkin });
}

// -----------------------------------------------------------------------------------------------------
// Eyes category: colour and detail (6 sliders, 1 part scalar, slots Lashes/PupilShape/IrisPattern,
// channels Iris L/R, Sclera, ScleraDeepkin, Glow, Shine)
// -----------------------------------------------------------------------------------------------------
void ULyrisAppearanceCatalog::BuildEyes()
{
	using namespace LyrisCatalogBuild;
	const FName Cat(TEXT("Eyes"));
	const FName Detail(TEXT("Detail"));
	TArray<FLyrisSliderDef>& A = Sliders;

	AddMorph(A, Cat, Detail, TEXT("Lashes.Length"), TEXT("Lash length"), TEXT("Lash_Length"));
	AddMorph(A, Cat, Detail, TEXT("Lashes.Curl"), TEXT("Lash curl"), TEXT("Lash_Curl"));
	Mat(AddSlider(A, Cat, Detail, TEXT("Iris.LimbalRing"), TEXT("Iris ring"), 0.f, 1.f), TEXT("LimbalRing"), 0.8f);
	Mat(AddSlider(A, Cat, Detail, TEXT("Iris.Catchlight"), TEXT("Catchlight"), 0.f, 1.f), TEXT("Catchlight"), 1.f);
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Detail, TEXT("Eyes.GlowStrength"), TEXT("Eye glow"), 0.f, 1.f);
		Mat(D, TEXT("EyeGlow"), 1.f);
		ForPeople(D, { LyrisPeople::MoonlitElf });
	}
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Detail, TEXT("Eyes.ShineStrength"), TEXT("Night shine"), 0.f, 1.f);
		Mat(D, TEXT("EyeShine"), 1.f);
		ForPeople(D, { LyrisPeople::Deepkin });
	}

	// Heterochromia toggle: 0 = both eyes use Eyes.IrisL, 1 = Eyes.IrisR is separate.
	AddPartScalar(*this, TEXT("Eyes.Heterochromia"), TEXT("Eyes"), TEXT("Colour"), TEXT("Different eye colours"), 0.f, 1.f, 0.f);

	AddSlotWithParts(*this, TEXT("Lashes"), TEXT("Eyes"), TEXT("Detail"), TEXT("Lashes"), true, TEXT("Natural"), false, nullptr, {
		{ TEXT("Soft"), TEXT("Soft") }, { TEXT("Natural"), TEXT("Natural") }, { TEXT("Full"), TEXT("Full") },
		{ TEXT("Fluttery"), TEXT("Fluttery") }, { TEXT("Storybook"), TEXT("Storybook") }, { TEXT("LowerAccent"), TEXT("Lower accent") },
	});
	AddSlotWithParts(*this, TEXT("PupilShape"), TEXT("Eyes"), TEXT("Colour"), TEXT("Pupil shape"), false, TEXT("Round"), true, nullptr, {
		{ TEXT("Round"), TEXT("Round") }, { TEXT("SoftOval"), TEXT("Soft oval") },
		{ TEXT("Crescent"), TEXT("Crescent"), LyrisPeople::MoonlitElf }, { TEXT("Starpoint"), TEXT("Starpoint"), LyrisPeople::MoonlitElf },
		{ TEXT("Slit"), TEXT("Slit"), LyrisPeople::Deepkin }, { TEXT("Cuttle"), TEXT("Cuttle"), LyrisPeople::Deepkin },
	});
	AddSlotWithParts(*this, TEXT("IrisPattern"), TEXT("Eyes"), TEXT("Colour"), TEXT("Iris pattern"), false, TEXT("Painted"), true, nullptr, {
		{ TEXT("Painted"), TEXT("Painted") }, { TEXT("Sunburst"), TEXT("Sunburst") }, { TEXT("Ringed"), TEXT("Ringed") },
		{ TEXT("Flecked"), TEXT("Flecked") }, { TEXT("TwoTone"), TEXT("Two-tone") }, { TEXT("Starfield"), TEXT("Starfield") },
		{ TEXT("Moonstone"), TEXT("Moonstone"), LyrisPeople::MoonlitElf }, { TEXT("Tidal"), TEXT("Tidal"), LyrisPeople::Deepkin },
	});

	const TArray<FLyrisSwatch> Iris = Band({
		{ TEXT("Brown"), TEXT("7A4A2A") }, { TEXT("Dark brown"), TEXT("4A2A1C") }, { TEXT("Honey"), TEXT("C98A3A") },
		{ TEXT("Amber"), TEXT("E3AE45") }, { TEXT("Hazel"), TEXT("9A7A3E") }, { TEXT("Leaf"), TEXT("6E8A3A") },
		{ TEXT("Sea"), TEXT("3F9A93") }, { TEXT("Shallows"), TEXT("7FD0D6") }, { TEXT("Moonglass"), TEXT("7AC0E6") },
		{ TEXT("Cornflower"), TEXT("5A86C8") }, { TEXT("Storm"), TEXT("5F6E86") }, { TEXT("Grey"), TEXT("8C9096") },
		{ TEXT("Violet"), TEXT("7D62B5") }, { TEXT("Rose"), TEXT("D07A8A") }, { TEXT("Silver"), TEXT("C9D3DE") },
		{ TEXT("Pale gold"), TEXT("F0D58A") }, { TEXT("Abyss teal"), TEXT("2E6F73") }, { TEXT("Ember"), TEXT("C8643A") },
	});
	AddChannel(*this, TEXT("Eyes.IrisL"), TEXT("Eyes"), TEXT("Colour"), TEXT("Iris (left)"), 0.08f, 0.20f, TEXT("IrisColorL"), {}, Iris);
	AddChannel(*this, TEXT("Eyes.IrisR"), TEXT("Eyes"), TEXT("Colour"), TEXT("Iris (right)"), 0.08f, 0.20f, TEXT("IrisColorR"), {}, Iris);
	AddChannel(*this, TEXT("Eyes.Sclera"), TEXT("Eyes"), TEXT("Colour"), TEXT("Eye whites"), 0.02f, 0.08f, TEXT("ScleraColor"),
		{ LyrisPeople::Human, LyrisPeople::MoonlitElf }, Band({
		{ TEXT("Warm white"), TEXT("F7EEDC") }, { TEXT("Cream"), TEXT("F1E9DC") }, { TEXT("Cool white"), TEXT("EEF2F5") }, { TEXT("Moon blue"), TEXT("DCE6F2") },
	}));
	AddChannel(*this, TEXT("Eyes.ScleraDeepkin"), TEXT("Eyes"), TEXT("Colour"), TEXT("Eye whites"), 0.03f, 0.10f, TEXT("ScleraColor"),
		{ LyrisPeople::Deepkin }, Band({
		{ TEXT("Cream"), TEXT("F1E9DC") }, { TEXT("Pale green"), TEXT("DDEBE2") }, { TEXT("Sea grey"), TEXT("C3D1CF") },
		{ TEXT("Dusk teal"), TEXT("4D6B6E") }, { TEXT("Deep slate"), TEXT("3A4552") },
	}));
	AddChannel(*this, TEXT("Eyes.Glow"), TEXT("Eyes"), TEXT("Colour"), TEXT("Eye glow"), 0.06f, 0.10f, TEXT("EyeGlowColor"),
		{ LyrisPeople::MoonlitElf }, Band({
		{ TEXT("Moonglass"), TEXT("7AC0E6") }, { TEXT("Pale silver"), TEXT("DDE8F5") }, { TEXT("Lilac"), TEXT("C4B4F0") },
		{ TEXT("Starlight gold"), TEXT("F3DC8C") }, { TEXT("Mint"), TEXT("B5F0DA") },
	}));
	AddChannel(*this, TEXT("Eyes.Shine"), TEXT("Eyes"), TEXT("Colour"), TEXT("Night shine"), 0.06f, 0.10f, TEXT("EyeShineColor"),
		{ LyrisPeople::Deepkin }, Band({
		{ TEXT("Shallows"), TEXT("7FD0D6") }, { TEXT("Green-gold"), TEXT("C8D86A") }, { TEXT("Pearl"), TEXT("E8E6DC") }, { TEXT("Amber"), TEXT("E3AE45") },
	}));
}

// -----------------------------------------------------------------------------------------------------
// Hair: no sliders (amounts are part scalars), slots Hair/HairAccessory/Brows/FacialHair, 6 channels
// -----------------------------------------------------------------------------------------------------
void ULyrisAppearanceCatalog::BuildHair()
{
	using namespace LyrisCatalogBuild;
	AddPartScalar(*this, TEXT("Hair.Length"), TEXT("Hair"), TEXT("Style"), TEXT("Length"), -1.f, 1.f, 0.f, TEXT("Hair_Length"));
	AddPartScalar(*this, TEXT("Hair.Volume"), TEXT("Hair"), TEXT("Style"), TEXT("Volume"), -1.f, 1.f, 0.f, TEXT("Hair_Volume"));
	AddPartScalar(*this, TEXT("Hair.GradientStart"), TEXT("Hair"), TEXT("Colour"), TEXT("Gradient start"), 0.f, 1.f, 0.7f);
	AddPartScalar(*this, TEXT("Hair.GradientSoftness"), TEXT("Hair"), TEXT("Colour"), TEXT("Gradient softness"), 0.f, 1.f, 0.5f);
	AddPartScalar(*this, TEXT("Hair.HighlightAmount"), TEXT("Hair"), TEXT("Colour"), TEXT("Highlights"), 0.f, 1.f, 0.f);
	AddPartScalar(*this, TEXT("Hair.Shine"), TEXT("Hair"), TEXT("Colour"), TEXT("Shine"), 0.f, 1.f, 0.5f);
	// Toggle: 1 = brows follow Hair.Root (darkened a little), 0 = Hair.Brows is used.
	AddPartScalar(*this, TEXT("Brows.MatchHair"), TEXT("Hair"), TEXT("Brows"), TEXT("Match hair colour"), 0.f, 1.f, 1.f);
	AddPartScalar(*this, TEXT("Brows.Density"), TEXT("Hair"), TEXT("Brows"), TEXT("Density"), 0.f, 1.f, 0.7f);
	AddPartScalar(*this, TEXT("FacialHair.Length"), TEXT("Hair"), TEXT("FacialHair"), TEXT("Length"), -1.f, 1.f, 0.f, TEXT("FacialHair_Length"));
	// Toggle: 1 = facial hair follows Hair.Root, 0 = Hair.FacialHair is used.
	AddPartScalar(*this, TEXT("FacialHair.MatchHair"), TEXT("Hair"), TEXT("FacialHair"), TEXT("Match hair colour"), 0.f, 1.f, 1.f);

	AddSlotWithParts(*this, TEXT("Hair"), TEXT("Hair"), TEXT("Style"), TEXT("Hairstyle"), false, TEXT("Shoreline"), false, nullptr, {
		{ TEXT("DeckhandCrop"), TEXT("Deckhand crop") }, { TEXT("WindTossed"), TEXT("Wind-tossed") },
		{ TEXT("HarborUndercut"), TEXT("Harbor undercut") }, { TEXT("Sparrow"), TEXT("Sparrow") },
		{ TEXT("TideCurls"), TEXT("Tide curls") }, { TEXT("CoilCrown"), TEXT("Coil crown") },
		{ TEXT("CloseShave"), TEXT("Close shave") }, { TEXT("Bare"), TEXT("Bare") }, { TEXT("Crest"), TEXT("Crest") },
		{ TEXT("LamplighterBob"), TEXT("Lamplighter bob") }, { TEXT("WaveBob"), TEXT("Wave bob") },
		{ TEXT("CurtainFringe"), TEXT("Curtain fringe") }, { TEXT("Shoreline"), TEXT("Shoreline") },
		{ TEXT("HalfMoon"), TEXT("Half-moon") }, { TEXT("BellTopknot"), TEXT("Bell-tower topknot") },
		{ TEXT("ScholarsBun"), TEXT("Scholar's bun") }, { TEXT("TwinMoons"), TEXT("Twin moons") },
		{ TEXT("SailorsTail"), TEXT("Sailor's tail") }, { TEXT("GullTail"), TEXT("Gull tail") },
		{ TEXT("RopeBraid"), TEXT("Rope braid") }, { TEXT("GarlandCrown"), TEXT("Garland crown") },
		{ TEXT("NetMenderBraids"), TEXT("Net-mender's braids") }, { TEXT("DriftwoodLocs"), TEXT("Driftwood locs") },
		{ TEXT("FallingWater"), TEXT("Falling water") }, { TEXT("RollingSwell"), TEXT("Rolling swell") },
		{ TEXT("Moonfall"), TEXT("Moonfall"), LyrisPeople::MoonlitElf },
		{ TEXT("KelpTresses"), TEXT("Kelp tresses"), LyrisPeople::Deepkin },
	});
	AddSlotWithParts(*this, TEXT("HairAccessory"), TEXT("Hair"), TEXT("Accessories"), TEXT("Hair accessory"), true, nullptr, false, TEXT("head"), {
		{ TEXT("Ribbon"), TEXT("Ribbon tie") }, { TEXT("Bandana"), TEXT("Sailor's bandana") }, { TEXT("Pencil"), TEXT("Pencil") },
		{ TEXT("ShellClips"), TEXT("Shell clips") }, { TEXT("GullFeather"), TEXT("Gull feather") }, { TEXT("FlowerCrown"), TEXT("Flower crown") },
		{ TEXT("WoodComb"), TEXT("Carved comb") }, { TEXT("BeadStrings"), TEXT("Bead strings") }, { TEXT("LampPin"), TEXT("Lamp hairpin") },
		{ TEXT("SeaGlassBand"), TEXT("Sea-glass circlet") },
	});
	AddSlotWithParts(*this, TEXT("Brows"), TEXT("Hair"), TEXT("Brows"), TEXT("Brows"), true, TEXT("Natural"), true, nullptr, {
		{ TEXT("Natural"), TEXT("Natural") }, { TEXT("Straight"), TEXT("Straight") }, { TEXT("SoftArch"), TEXT("Soft arch") },
		{ TEXT("HighArch"), TEXT("High arch") }, { TEXT("Thick"), TEXT("Thick") }, { TEXT("Feathered"), TEXT("Feathered") },
		{ TEXT("Fine"), TEXT("Fine") }, { TEXT("Bushy"), TEXT("Bushy") }, { TEXT("Rounded"), TEXT("Rounded") }, { TEXT("Split"), TEXT("Split") },
		{ TEXT("MoonWisp"), TEXT("Moon wisp"), LyrisPeople::MoonlitElf }, { TEXT("ScaleRidge"), TEXT("Scale ridge"), LyrisPeople::Deepkin },
	});
	AddSlotWithParts(*this, TEXT("FacialHair"), TEXT("Hair"), TEXT("FacialHair"), TEXT("Facial hair"), true, nullptr, false, nullptr, {
		{ TEXT("Stubble"), TEXT("Stubble") }, { TEXT("ShortBeard"), TEXT("Short beard") }, { TEXT("FullBeard"), TEXT("Full beard") },
		{ TEXT("BraidedBeard"), TEXT("Braided beard") }, { TEXT("Moustache"), TEXT("Moustache") }, { TEXT("Goatee"), TEXT("Goatee") },
		{ TEXT("Chinstrap"), TEXT("Sailor's chinstrap") }, { TEXT("MuttonChops"), TEXT("Mutton chops") },
		{ TEXT("ArchivistBeard"), TEXT("Archivist's beard") }, { TEXT("Barbels"), TEXT("Barbels"), LyrisPeople::Deepkin },
	});

	// All hair channels share one band so the UI can offer "match hair": 13 natural, 7 storybook.
	const TArray<FLyrisSwatch> HairBand = Band({
		{ TEXT("Flax"), TEXT("F2DFA7") }, { TEXT("Wheat"), TEXT("E3C27E") }, { TEXT("Honey blond"), TEXT("D4A55A") },
		{ TEXT("Strawberry"), TEXT("D9895A") }, { TEXT("Copper"), TEXT("B85A30") }, { TEXT("Auburn"), TEXT("8E3B26") },
		{ TEXT("Chestnut"), TEXT("6F4128") }, { TEXT("Brown"), TEXT("553322") }, { TEXT("Dark brown"), TEXT("3B2419") },
		{ TEXT("Ink"), TEXT("231A1A") }, { TEXT("Ash"), TEXT("A7A2A0") }, { TEXT("Silver"), TEXT("D9D8DC") },
		{ TEXT("Snow"), TEXT("F3F0EA") }, { TEXT("Moonglass"), TEXT("7AC0E6") }, { TEXT("Lavender"), TEXT("B49CD6") },
		{ TEXT("Rose"), TEXT("D88FA6") }, { TEXT("Sea green"), TEXT("6FB3A0") }, { TEXT("Dusk violet"), TEXT("5D4E8C") },
		{ TEXT("Ember"), TEXT("C8443A") }, { TEXT("Deep sea"), TEXT("2F4E6B") },
	});
	AddChannel(*this, TEXT("Hair.Root"), TEXT("Hair"), TEXT("Colour"), TEXT("Hair colour"), 0.06f, 0.20f, TEXT("HairRoot"), {}, HairBand);
	AddChannel(*this, TEXT("Hair.Tip"), TEXT("Hair"), TEXT("Colour"), TEXT("Tip colour"), 0.06f, 0.20f, TEXT("HairTip"), {}, HairBand);
	AddChannel(*this, TEXT("Hair.Highlight"), TEXT("Hair"), TEXT("Colour"), TEXT("Highlights"), 0.06f, 0.20f, TEXT("HairHighlight"), {}, HairBand);
	AddChannel(*this, TEXT("Hair.Brows"), TEXT("Hair"), TEXT("Brows"), TEXT("Brow colour"), 0.06f, 0.20f, TEXT("BrowColor"), {}, HairBand);
	AddChannel(*this, TEXT("Hair.FacialHair"), TEXT("Hair"), TEXT("FacialHair"), TEXT("Facial hair colour"), 0.06f, 0.20f, TEXT("FacialHairColor"), {}, HairBand);
	AddChannel(*this, TEXT("Hair.Accessory"), TEXT("Hair"), TEXT("Accessories"), TEXT("Accessory"), 0.05f, 0.15f, TEXT("AccessoryColor"), {}, Band({
		{ TEXT("Brass"), TEXT("B8893A") }, { TEXT("Silver"), TEXT("C9CDD2") }, { TEXT("Copper"), TEXT("B0683E") },
		{ TEXT("Wood"), TEXT("8B5A3A") }, { TEXT("DarkWood"), TEXT("4A2A1C") }, { TEXT("Sail"), TEXT("F7EEDC") },
		{ TEXT("RedBand"), TEXT("C8443A") }, { TEXT("Gold"), TEXT("E3AE45") }, { TEXT("Leaf"), TEXT("6E8A3A") },
		{ TEXT("Shallows"), TEXT("7FD0D6") }, { TEXT("Moonglass"), TEXT("7AC0E6") }, { TEXT("Dusk plum"), TEXT("5D4E8C") },
	}));
}

// -----------------------------------------------------------------------------------------------------
// Skin: 5 sliders, part scalars for details/markings, slots Freckles/Moles/Scars/Markings, 7 channels
// -----------------------------------------------------------------------------------------------------
void ULyrisAppearanceCatalog::BuildSkin()
{
	using namespace LyrisCatalogBuild;
	const FName Cat(TEXT("Skin"));
	const FName Tone(TEXT("Tone")), Details(TEXT("Details"));
	TArray<FLyrisSliderDef>& A = Sliders;

	Mat(AddSlider(A, Cat, Tone, TEXT("Skin.Undertone"), TEXT("Undertone")), TEXT("SkinUndertone"), 1.f); // material shifts hue +-0.02
	Mat(AddSlider(A, Cat, Tone, TEXT("Skin.Rosiness"), TEXT("Rosiness"), 0.f, 1.f), TEXT("Rosiness"), 0.8f);
	Mat(AddSlider(A, Cat, Tone, TEXT("Skin.Sheen"), TEXT("Sheen")), TEXT("SkinSheen"), 0.6f);
	Mat(AddSlider(A, Cat, Details, TEXT("Skin.AgeLines"), TEXT("Age lines"), 0.f, 1.f), TEXT("AgeLines"), 0.6f);
	{
		FLyrisSliderDef& D = AddSlider(A, Cat, Tone, TEXT("Skin.Moonglow"), TEXT("Moonglow"), 0.f, 1.f);
		Mat(D, TEXT("SkinMoonglow"), 0.5f);
		ForPeople(D, { LyrisPeople::MoonlitElf });
	}

	AddPartScalar(*this, TEXT("Freckles.Density"), TEXT("Skin"), TEXT("Details"), TEXT("Freckle density"), 0.f, 1.f, 0.5f);
	AddPartScalar(*this, TEXT("Freckles.Opacity"), TEXT("Skin"), TEXT("Details"), TEXT("Freckle strength"), 0.f, 1.f, 0.6f);
	AddPartScalar(*this, TEXT("Moles.Opacity"), TEXT("Skin"), TEXT("Details"), TEXT("Mole strength"), 0.f, 1.f, 0.8f);
	AddPartScalar(*this, TEXT("Scars.Opacity"), TEXT("Skin"), TEXT("Details"), TEXT("Scar strength"), 0.f, 0.8f, 0.6f); // healed, soft
	AddPartScalar(*this, TEXT("Markings.Opacity"), TEXT("Skin"), TEXT("Markings"), TEXT("Marking strength"), 0.f, 1.f, 0.8f);
	ForPeople(AddPartScalar(*this, TEXT("Markings.Glow"), TEXT("Skin"), TEXT("Markings"), TEXT("Sigil glow"), 0.f, 1.f, 0.5f), { LyrisPeople::MoonlitElf });
	ForPeople(AddPartScalar(*this, TEXT("Markings.Shimmer"), TEXT("Skin"), TEXT("Markings"), TEXT("Scale shimmer"), 0.f, 1.f, 0.5f), { LyrisPeople::Deepkin });

	AddSlotWithParts(*this, TEXT("Freckles"), TEXT("Skin"), TEXT("Details"), TEXT("Freckles"), true, nullptr, true, nullptr, {
		{ TEXT("NoseDust"), TEXT("Nose dust") }, { TEXT("SunKissed"), TEXT("Sun-kissed") }, { TEXT("FullFace"), TEXT("Full face") },
		{ TEXT("FaceShoulders"), TEXT("Face & shoulders") }, { TEXT("Sparse"), TEXT("Sparse") }, { TEXT("Constellation"), TEXT("Constellation") },
		{ TEXT("Speckled"), TEXT("Speckled") }, { TEXT("Hands"), TEXT("Hands & forearms") },
	});
	AddSlotWithParts(*this, TEXT("Moles"), TEXT("Skin"), TEXT("Details"), TEXT("Moles"), true, nullptr, true, nullptr, {
		{ TEXT("BeautyMark"), TEXT("Beauty mark") }, { TEXT("UnderEye"), TEXT("Under the eye") }, { TEXT("LipCorner"), TEXT("Lip corner") },
		{ TEXT("Chin"), TEXT("Chin") }, { TEXT("Neck"), TEXT("Neck") }, { TEXT("Scattered"), TEXT("Scattered") },
	});
	AddSlotWithParts(*this, TEXT("Scars"), TEXT("Skin"), TEXT("Details"), TEXT("Scars"), true, nullptr, true, nullptr, {
		{ TEXT("BrowNick"), TEXT("Brow nick") }, { TEXT("CheekLine"), TEXT("Cheek line") }, { TEXT("LipSplit"), TEXT("Lip split") },
		{ TEXT("NoseBridge"), TEXT("Nose bridge") }, { TEXT("JawLine"), TEXT("Jaw line") }, { TEXT("EarNotch"), TEXT("Ear notch") },
		{ TEXT("AcrossEye"), TEXT("Across the eye") }, { TEXT("RopeBurn"), TEXT("Rope burn") },
	});
	AddSlotWithParts(*this, TEXT("Markings"), TEXT("Skin"), TEXT("Markings"), TEXT("Markings"), true, nullptr, true, nullptr, {
		{ TEXT("CrescentBrow"), TEXT("Crescent brow"), LyrisPeople::MoonlitElf }, { TEXT("WaningCheeks"), TEXT("Waning cheeks"), LyrisPeople::MoonlitElf },
		{ TEXT("StarTrail"), TEXT("Star trail"), LyrisPeople::MoonlitElf }, { TEXT("FullMoon"), TEXT("Full moon"), LyrisPeople::MoonlitElf },
		{ TEXT("PhaseChain"), TEXT("Phase chain"), LyrisPeople::MoonlitElf }, { TEXT("SilverVeins"), TEXT("Silver veins"), LyrisPeople::MoonlitElf },
		{ TEXT("TempleScales"), TEXT("Temple scales"), LyrisPeople::Deepkin }, { TEXT("CheekScales"), TEXT("Cheek scales"), LyrisPeople::Deepkin },
		{ TEXT("GillLines"), TEXT("Gill lines"), LyrisPeople::Deepkin }, { TEXT("ShoulderScales"), TEXT("Shoulder scales"), LyrisPeople::Deepkin },
		{ TEXT("SpineRidge"), TEXT("Spine ridge"), LyrisPeople::Deepkin }, { TEXT("FinEdge"), TEXT("Fin edge"), LyrisPeople::Deepkin },
		{ TEXT("RopeInk"), TEXT("Rope ink"), LyrisPeople::Human }, { TEXT("CompassInk"), TEXT("Compass ink"), LyrisPeople::Human },
		{ TEXT("WaveInk"), TEXT("Wave ink"), LyrisPeople::Human }, { TEXT("LampInk"), TEXT("Lamp ink"), LyrisPeople::Human },
	});

	// Skin bands per People (spec 5.2). All three write the same "SkinTone" param; only the current
	// People's channel is applied, and each People's own pick is kept so switching back restores it.
	AddChannel(*this, TEXT("Skin.ToneHuman"), TEXT("Skin"), TEXT("Tone"), TEXT("Skin tone"), 0.03f, 0.10f, TEXT("SkinTone"), { LyrisPeople::Human }, Band({
		{ TEXT("Shell"), TEXT("F6E3D3") }, { TEXT("Porcelain"), TEXT("F1D5BF") }, { TEXT("Peach"), TEXT("EDC6A8") },
		{ TEXT("Honey"), TEXT("E2B48C") }, { TEXT("Sand-gold"), TEXT("D7A276") }, { TEXT("Wheat-brown"), TEXT("CF9A6E") },
		{ TEXT("Amber"), TEXT("C98F62") }, { TEXT("Copper"), TEXT("B8784E") }, { TEXT("Chestnut"), TEXT("A0633F") },
		{ TEXT("Cocoa"), TEXT("85502F") }, { TEXT("Umber"), TEXT("6E4128") }, { TEXT("Night oak"), TEXT("4E2C1E") },
	}));
	AddChannel(*this, TEXT("Skin.ToneElf"), TEXT("Skin"), TEXT("Tone"), TEXT("Skin tone"), 0.04f, 0.10f, TEXT("SkinTone"), { LyrisPeople::MoonlitElf }, Band({
		{ TEXT("Moonmilk"), TEXT("F2EEF4") }, { TEXT("Pearl"), TEXT("E6E3F0") }, { TEXT("Rose moon"), TEXT("E8D2DC") },
		{ TEXT("Frost"), TEXT("D9DDF0") }, { TEXT("Lilac dawn"), TEXT("D4C8E6") }, { TEXT("Wisteria"), TEXT("BFB0DA") },
		{ TEXT("Dusk blue"), TEXT("A9B4DA") }, { TEXT("Twilight"), TEXT("9A9CCB") }, { TEXT("Heather"), TEXT("8E82B5") },
		{ TEXT("Evening"), TEXT("77709F") }, { TEXT("Nightfall"), TEXT("5F5A87") },
	}));
	AddChannel(*this, TEXT("Skin.ToneDeepkin"), TEXT("Skin"), TEXT("Tone"), TEXT("Skin tone"), 0.05f, 0.10f, TEXT("SkinTone"), { LyrisPeople::Deepkin }, Band({
		{ TEXT("Seafoam"), TEXT("CFE5DA") }, { TEXT("Pale shallows"), TEXT("B5DCD3") }, { TEXT("Kelp light"), TEXT("9CC7B5") },
		{ TEXT("Sea glass"), TEXT("86B8AA") }, { TEXT("Tidepool"), TEXT("6FA39A") }, { TEXT("Verdigris"), TEXT("5E9488") },
		{ TEXT("Deep teal"), TEXT("4D7F7E") }, { TEXT("Slate-green"), TEXT("5C7472") }, { TEXT("Slate"), TEXT("667385") },
		{ TEXT("Storm"), TEXT("56616F") }, { TEXT("Abyss"), TEXT("3F4A5A") },
	}));
	AddChannel(*this, TEXT("Skin.Rosiness"), TEXT("Skin"), TEXT("Tone"), TEXT("Rosiness"), 0.04f, 0.10f, TEXT("RosinessColor"), {}, Band({
		{ TEXT("Peach"), TEXT("E9A88A") }, { TEXT("Rose"), TEXT("D98A7A") }, { TEXT("Berry"), TEXT("B85A6A") },
		{ TEXT("Lavender rose"), TEXT("C99AC4") }, { TEXT("Coral"), TEXT("E39A7E") }, { TEXT("Tide flush"), TEXT("5FA8A0") },
	}));
	AddChannel(*this, TEXT("Skin.Freckles"), TEXT("Skin"), TEXT("Details"), TEXT("Freckles"), 0.04f, 0.15f, TEXT("FreckleColor"), {}, Band({
		{ TEXT("Sun brown"), TEXT("A0633F") }, { TEXT("Rust"), TEXT("B8784E") }, { TEXT("Deep brown"), TEXT("6E4128") },
		{ TEXT("Ginger"), TEXT("C8643A") }, { TEXT("Starlight"), TEXT("E6E3F0") }, { TEXT("Moonglass"), TEXT("7AC0E6") },
		{ TEXT("Deep teal"), TEXT("4D7F7E") }, { TEXT("Slate"), TEXT("56616F") },
	}));
	AddChannel(*this, TEXT("Skin.Markings"), TEXT("Skin"), TEXT("Markings"), TEXT("Markings"), 0.06f, 0.15f, TEXT("MarkingColor"), {}, Band({
		{ TEXT("Moonglass"), TEXT("7AC0E6") }, { TEXT("Silver"), TEXT("DDE3EC") }, { TEXT("Pearl"), TEXT("E6E3F0") },
		{ TEXT("Gold"), TEXT("E3AE45") }, { TEXT("Lilac"), TEXT("B49CD6") }, { TEXT("Shallows"), TEXT("7FD0D6") },
		{ TEXT("Verdigris"), TEXT("5E9488") }, { TEXT("Nacre"), TEXT("E8E6DC") }, { TEXT("Ink blue"), TEXT("2F4E6B") },
		{ TEXT("Red ochre"), TEXT("C8443A") },
	}));
	AddChannel(*this, TEXT("Skin.MarkingShimmer"), TEXT("Skin"), TEXT("Markings"), TEXT("Shimmer"), 0.08f, 0.10f, TEXT("MarkingShimmerColor"), { LyrisPeople::Deepkin }, Band({
		{ TEXT("Shallows"), TEXT("7FD0D6") }, { TEXT("Pearl pink"), TEXT("E8C8D4") }, { TEXT("Gold"), TEXT("E3AE45") },
		{ TEXT("Lilac"), TEXT("B49CD6") }, { TEXT("Sea green"), TEXT("6FB3A0") }, { TEXT("Silver"), TEXT("DDE3EC") },
	}));
}

// -----------------------------------------------------------------------------------------------------
// Makeup: part scalars for opacity/gloss, five mask slots, five channels. All painted, flat, soft-edged.
// -----------------------------------------------------------------------------------------------------
void ULyrisAppearanceCatalog::BuildMakeup()
{
	using namespace LyrisCatalogBuild;
	AddPartScalar(*this, TEXT("Makeup.Eyeshadow.Opacity"), TEXT("Makeup"), TEXT("Eyes"), TEXT("Eyeshadow strength"), 0.f, 1.f, 0.6f);
	AddPartScalar(*this, TEXT("Makeup.Eyeliner.Opacity"), TEXT("Makeup"), TEXT("Eyes"), TEXT("Eyeliner strength"), 0.f, 1.f, 0.8f);
	AddPartScalar(*this, TEXT("Makeup.Lips.Opacity"), TEXT("Makeup"), TEXT("Lips"), TEXT("Lip colour strength"), 0.f, 1.f, 0.5f);
	AddPartScalar(*this, TEXT("Makeup.Lips.Gloss"), TEXT("Makeup"), TEXT("Lips"), TEXT("Gloss"), 0.f, 1.f, 0.2f);
	AddPartScalar(*this, TEXT("Makeup.Blush.Opacity"), TEXT("Makeup"), TEXT("Cheeks"), TEXT("Blush strength"), 0.f, 1.f, 0.5f);
	AddPartScalar(*this, TEXT("Makeup.FacePaint.Opacity"), TEXT("Makeup"), TEXT("FacePaint"), TEXT("Face paint strength"), 0.f, 1.f, 0.9f);

	AddSlotWithParts(*this, TEXT("Eyeshadow"), TEXT("Makeup"), TEXT("Eyes"), TEXT("Eyeshadow"), true, nullptr, true, nullptr, {
		{ TEXT("Wash"), TEXT("Wash") }, { TEXT("Smoky"), TEXT("Smoky") }, { TEXT("WingShadow"), TEXT("Wing shadow") },
		{ TEXT("UnderGlow"), TEXT("Under-glow") }, { TEXT("InnerShine"), TEXT("Inner shine") }, { TEXT("TwoTone"), TEXT("Two-tone") },
		{ TEXT("Crease"), TEXT("Crease") },
	});
	AddSlotWithParts(*this, TEXT("Eyeliner"), TEXT("Makeup"), TEXT("Eyes"), TEXT("Eyeliner"), true, nullptr, true, nullptr, {
		{ TEXT("Tightline"), TEXT("Tightline") }, { TEXT("ClassicWing"), TEXT("Classic wing") }, { TEXT("CatFlick"), TEXT("Cat flick") },
		{ TEXT("LowerLine"), TEXT("Lower line") }, { TEXT("Kohl"), TEXT("Kohl") }, { TEXT("Dotted"), TEXT("Dotted") },
		{ TEXT("DoubleWing"), TEXT("Double wing") },
	});
	AddSlotWithParts(*this, TEXT("Lips"), TEXT("Makeup"), TEXT("Lips"), TEXT("Lips"), true, nullptr, true, nullptr, {
		{ TEXT("Tint"), TEXT("Tint") }, { TEXT("Full"), TEXT("Full") }, { TEXT("Ombre"), TEXT("Ombre") },
		{ TEXT("CentreStain"), TEXT("Centre stain") }, { TEXT("TwoTone"), TEXT("Two-tone") },
	});
	AddSlotWithParts(*this, TEXT("Blush"), TEXT("Makeup"), TEXT("Cheeks"), TEXT("Blush"), true, nullptr, true, nullptr, {
		{ TEXT("Apples"), TEXT("Apples") }, { TEXT("Sweep"), TEXT("Sweep") }, { TEXT("SunAcrossNose"), TEXT("Sun across the nose") },
		{ TEXT("UnderEye"), TEXT("Under the eye") }, { TEXT("Temple"), TEXT("Temple") },
	});
	AddSlotWithParts(*this, TEXT("FacePaint"), TEXT("Makeup"), TEXT("FacePaint"), TEXT("Face paint"), true, nullptr, true, nullptr, {
		{ TEXT("LamplighterStripe"), TEXT("Lamplighter stripe") }, { TEXT("TideDots"), TEXT("Tide dots") },
		{ TEXT("FestivalSun"), TEXT("Festival sun") }, { TEXT("MoonCrescent"), TEXT("Moon crescent") }, { TEXT("LeafVine"), TEXT("Leaf vine") },
		{ TEXT("Constellation"), TEXT("Constellation") }, { TEXT("MaskBand"), TEXT("Mask band") }, { TEXT("SeaFoam"), TEXT("Sea foam") },
		{ TEXT("BeaconLines"), TEXT("Beacon lines") },
	});

	AddChannel(*this, TEXT("Makeup.Eyeshadow"), TEXT("Makeup"), TEXT("Eyes"), TEXT("Eyeshadow"), 0.06f, 0.20f, TEXT("EyeshadowColor"), {}, Band({
		{ TEXT("Champagne"), TEXT("E9D3B0") }, { TEXT("Peach"), TEXT("E9A88A") }, { TEXT("Terracotta"), TEXT("C8643A") },
		{ TEXT("Copper"), TEXT("B0683E") }, { TEXT("Rose"), TEXT("D88FA6") }, { TEXT("Plum"), TEXT("7A4A6E") },
		{ TEXT("Dusk plum"), TEXT("5D4E8C") }, { TEXT("Lilac"), TEXT("B49CD6") }, { TEXT("Moonglass"), TEXT("7AC0E6") },
		{ TEXT("Shallows"), TEXT("7FD0D6") }, { TEXT("Sea green"), TEXT("6FB3A0") }, { TEXT("Leaf"), TEXT("6E8A3A") },
		{ TEXT("Gold"), TEXT("E3AE45") }, { TEXT("Bronze"), TEXT("8E6A3A") }, { TEXT("Brown"), TEXT("553322") },
		{ TEXT("Slate"), TEXT("56616F") },
	}));
	AddChannel(*this, TEXT("Makeup.Eyeliner"), TEXT("Makeup"), TEXT("Eyes"), TEXT("Eyeliner"), 0.05f, 0.20f, TEXT("EyelinerColor"), {}, Band({
		{ TEXT("Ink"), TEXT("231A1A") }, { TEXT("Brown"), TEXT("553322") }, { TEXT("Deep sea"), TEXT("2F4E6B") },
		{ TEXT("Plum"), TEXT("5D4E8C") }, { TEXT("Forest"), TEXT("3F5A33") }, { TEXT("Ember"), TEXT("C8443A") },
		{ TEXT("Gold"), TEXT("E3AE45") }, { TEXT("Silver"), TEXT("C9CDD2") },
	}));
	AddChannel(*this, TEXT("Makeup.Lips"), TEXT("Makeup"), TEXT("Lips"), TEXT("Lips"), 0.05f, 0.20f, TEXT("LipColor"), {}, Band({
		{ TEXT("Nude peach"), TEXT("D9A28A") }, { TEXT("Rose"), TEXT("D98A7A") }, { TEXT("Berry"), TEXT("B85A6A") },
		{ TEXT("Red"), TEXT("C8443A") }, { TEXT("Coral"), TEXT("E3805E") }, { TEXT("Terracotta"), TEXT("C8643A") },
		{ TEXT("Plum"), TEXT("7A4A6E") }, { TEXT("Mauve"), TEXT("A67A8E") }, { TEXT("Brown"), TEXT("7A4A3A") },
		{ TEXT("Lilac"), TEXT("B49CD6") }, { TEXT("Tide"), TEXT("4D7F7E") }, { TEXT("Moonglass"), TEXT("7AC0E6") },
	}));
	AddChannel(*this, TEXT("Makeup.Blush"), TEXT("Makeup"), TEXT("Cheeks"), TEXT("Blush"), 0.04f, 0.15f, TEXT("BlushColor"), {}, Band({
		{ TEXT("Peach"), TEXT("E9A88A") }, { TEXT("Rose"), TEXT("D98A7A") }, { TEXT("Coral"), TEXT("E39A7E") },
		{ TEXT("Berry"), TEXT("B85A6A") }, { TEXT("Apricot"), TEXT("E8A66A") }, { TEXT("Lavender"), TEXT("C99AC4") },
		{ TEXT("Bronze"), TEXT("B07A4E") }, { TEXT("Tide flush"), TEXT("5FA8A0") },
	}));
	AddChannel(*this, TEXT("Makeup.FacePaint"), TEXT("Makeup"), TEXT("FacePaint"), TEXT("Face paint"), 0.06f, 0.15f, TEXT("FacePaintColor"), {}, Band({
		{ TEXT("Sail"), TEXT("F7EEDC") }, { TEXT("Gold"), TEXT("E3AE45") }, { TEXT("RedBand"), TEXT("C8443A") },
		{ TEXT("Terracotta"), TEXT("C8643A") }, { TEXT("Leaf"), TEXT("6E8A3A") }, { TEXT("Shallows"), TEXT("7FD0D6") },
		{ TEXT("Moonglass"), TEXT("7AC0E6") }, { TEXT("Lilac"), TEXT("B49CD6") }, { TEXT("Deep sea"), TEXT("2F4E6B") },
		{ TEXT("Ink"), TEXT("231A1A") }, { TEXT("Clay"), TEXT("36221A") }, { TEXT("Silver"), TEXT("C9CDD2") },
	}));
}

// -----------------------------------------------------------------------------------------------------
// Outfit: 1 part scalar, slots Outfit/Layer, four cloth channels sharing one band (trim has its own)
// -----------------------------------------------------------------------------------------------------
void ULyrisAppearanceCatalog::BuildOutfit()
{
	using namespace LyrisCatalogBuild;
	AddPartScalar(*this, TEXT("Outfit.Wear"), TEXT("Outfit"), TEXT("Outfit"), TEXT("Wear"), 0.f, 1.f, 0.3f);

	// Default is the plain outfit; the creator picks the chosen path's outfit at step 3 (spec 8.1).
	AddSlotWithParts(*this, TEXT("Outfit"), TEXT("Outfit"), TEXT("Outfit"), TEXT("Outfit"), false, TEXT("PlainTraveller"), false, nullptr, {
		{ TEXT("DeckhandCoat"), TEXT("Deckhand's coat") }, { TEXT("WandererLayers"), TEXT("Wanderer's layers") },
		{ TEXT("GrowerSmock"), TEXT("Grower's smock") }, { TEXT("MakerApron"), TEXT("Maker's apron") },
		{ TEXT("ScholarCoat"), TEXT("Scholar's coat") }, { TEXT("TraderWaistcoat"), TEXT("Trader's waistcoat") },
		{ TEXT("DelverLeathers"), TEXT("Delver's leathers") }, { TEXT("PlainTraveller"), TEXT("Plain traveller") },
	});
	AddSlotWithParts(*this, TEXT("Layer"), TEXT("Outfit"), TEXT("Layer"), TEXT("Cloak or scarf"), true, nullptr, false, nullptr, {
		{ TEXT("WoolScarf"), TEXT("Wool scarf") }, { TEXT("RainCloak"), TEXT("Rain cloak") }, { TEXT("ShortCape"), TEXT("Short cape") },
		{ TEXT("Shawl"), TEXT("Shawl") }, { TEXT("HoodedCloak"), TEXT("Hooded cloak") }, { TEXT("Neckerchief"), TEXT("Neckerchief") },
		{ TEXT("Poncho"), TEXT("Poncho") },
	});

	const TArray<FLyrisSwatch> Cloth = Band({
		{ TEXT("Sail"), TEXT("F7EEDC") }, { TEXT("Sand"), TEXT("F1E9DC") }, { TEXT("Oat"), TEXT("D9C7A5") },
		{ TEXT("Wood"), TEXT("8B5A3A") }, { TEXT("DarkWood"), TEXT("4A2A1C") }, { TEXT("Clay"), TEXT("36221A") },
		{ TEXT("Terracotta"), TEXT("C8643A") }, { TEXT("RedBand"), TEXT("C8443A") }, { TEXT("Gold"), TEXT("E3AE45") },
		{ TEXT("Leaf"), TEXT("6E8A3A") }, { TEXT("Grass"), TEXT("8A9A48") }, { TEXT("Shallows"), TEXT("7FD0D6") },
		{ TEXT("Moonglass"), TEXT("7AC0E6") }, { TEXT("Deep sea"), TEXT("2F4E6B") }, { TEXT("Dusk plum"), TEXT("5D4E8C") },
		{ TEXT("Heather"), TEXT("9C8AB0") }, { TEXT("Stone"), TEXT("9C9488") }, { TEXT("Ink"), TEXT("2A2730") },
	});
	AddChannel(*this, TEXT("Outfit.Primary"), TEXT("Outfit"), TEXT("Outfit"), TEXT("Main cloth"), 0.04f, 0.15f, TEXT("ClothPrimary"), {}, Cloth);
	AddChannel(*this, TEXT("Outfit.Secondary"), TEXT("Outfit"), TEXT("Outfit"), TEXT("Second cloth"), 0.04f, 0.15f, TEXT("ClothSecondary"), {}, Cloth);
	AddChannel(*this, TEXT("Outfit.Trim"), TEXT("Outfit"), TEXT("Outfit"), TEXT("Trim"), 0.03f, 0.10f, TEXT("ClothTrim"), {}, Band({
		{ TEXT("Brass"), TEXT("B8893A") }, { TEXT("Silver"), TEXT("C9CDD2") }, { TEXT("Copper"), TEXT("B0683E") },
		{ TEXT("Gold"), TEXT("E3AE45") }, { TEXT("Sail"), TEXT("F7EEDC") }, { TEXT("DarkWood"), TEXT("4A2A1C") },
		{ TEXT("RedBand"), TEXT("C8443A") }, { TEXT("Leaf"), TEXT("6E8A3A") }, { TEXT("Moonglass"), TEXT("7AC0E6") },
		{ TEXT("Ink"), TEXT("2A2730") },
	}));
	AddChannel(*this, TEXT("Outfit.Layer"), TEXT("Outfit"), TEXT("Layer"), TEXT("Cloak or scarf"), 0.04f, 0.15f, TEXT("LayerColor"), {}, Cloth);
}

// -----------------------------------------------------------------------------------------------------
// Voice & expression: 1 slider (read by audio later), slots Voice/Expression (placeholder ids)
// -----------------------------------------------------------------------------------------------------
void ULyrisAppearanceCatalog::BuildVoice()
{
	using namespace LyrisCatalogBuild;
	// MaterialScalar is a placeholder target: the audio system reads Sliders["Voice.Pitch"] (+-2 semitones).
	Mat(AddSlider(Sliders, FName(TEXT("Voice")), FName(TEXT("Voice")), TEXT("Voice.Pitch"), TEXT("Voice pitch")), TEXT("VoicePitch"), 1.f);

	AddSlotWithParts(*this, TEXT("Voice"), TEXT("Voice"), TEXT("Voice"), TEXT("Voice"), false, TEXT("Warm1"), false, nullptr, {
		{ TEXT("Bright1"), TEXT("Bright I") }, { TEXT("Bright2"), TEXT("Bright II") }, { TEXT("Warm1"), TEXT("Warm I") },
		{ TEXT("Warm2"), TEXT("Warm II") }, { TEXT("Low1"), TEXT("Low I") }, { TEXT("Low2"), TEXT("Low II") },
		{ TEXT("Soft1"), TEXT("Soft I") }, { TEXT("Soft2"), TEXT("Soft II") },
	});
	AddSlotWithParts(*this, TEXT("Expression"), TEXT("Voice"), TEXT("Expression"), TEXT("Resting expression"), false, TEXT("Calm"), false, nullptr, {
		{ TEXT("Calm"), TEXT("Calm") }, { TEXT("Bright"), TEXT("Bright") }, { TEXT("Wry"), TEXT("Wry") },
		{ TEXT("Shy"), TEXT("Shy") }, { TEXT("Dreamy"), TEXT("Dreamy") }, { TEXT("Determined"), TEXT("Determined") },
	});
}

// -----------------------------------------------------------------------------------------------------
// Lantern (creator step 5): shapes as parts so they have meshes, plus the glass channel. These belong to
// FLyrisCharacterProfile (LanternShape, LanternGlass), not to FLyrisAppearance.
// -----------------------------------------------------------------------------------------------------
void ULyrisAppearanceCatalog::BuildLantern()
{
	using namespace LyrisCatalogBuild;
	AddSlotWithParts(*this, TEXT("Lantern"), TEXT("Lantern"), TEXT("Lantern"), TEXT("Lantern"), false, TEXT("Ships"), false, TEXT("hand_r"), {
		{ TEXT("Ships"), TEXT("Ship's lantern") }, { TEXT("StormHex"), TEXT("Storm lantern") }, { TEXT("MoonGlobe"), TEXT("Moon globe") },
		{ TEXT("HangingBell"), TEXT("Hanging bell") }, { TEXT("Lighthouse"), TEXT("Little lighthouse") }, { TEXT("Shell"), TEXT("Shell lantern") },
		{ TEXT("BrassStar"), TEXT("Brass star") }, { TEXT("Reading"), TEXT("Reading lantern") }, { TEXT("Seedpod"), TEXT("Seedpod") },
	});
	AddChannel(*this, TEXT("Lantern.Glass"), TEXT("Lantern"), TEXT("Lantern"), TEXT("Lantern glass"), 0.08f, 0.15f, TEXT("LanternGlass"), {}, Band({
		{ TEXT("Amber"), TEXT("E3AE45") }, { TEXT("Warm white"), TEXT("F7EEDC") }, { TEXT("Moonglass"), TEXT("7AC0E6") },
		{ TEXT("Shallows"), TEXT("7FD0D6") }, { TEXT("Rose"), TEXT("D88FA6") }, { TEXT("Ember"), TEXT("C8643A") },
		{ TEXT("Violet"), TEXT("9A82D0") }, { TEXT("Leaf-gold"), TEXT("C9D86A") }, { TEXT("Pearl"), TEXT("E8E6DC") },
	}));
}
