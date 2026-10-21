// Lyris appearance system: stateless helpers (Player lane, task T23). See the header.

#include "Player/Appearance/LyrisAppearanceLibrary.h"
#include "Player/Appearance/LyrisAppearanceCatalog.h"
#include "Misc/Base64.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Containers/StringConv.h"
#include "Misc/FileHelper.h"

namespace LyrisAppearanceIds
{
	const FName BodyHeight(TEXT("Body.Height"));
	const FName BodyHeadSize(TEXT("Body.HeadSize"));
	const FName EyesSizeL(TEXT("Eyes.SizeL"));
	const FName EyesSizeR(TEXT("Eyes.SizeR"));
	const FName BrowsMatchHair(TEXT("Brows.MatchHair"));
	const FName FacialHairMatchHair(TEXT("FacialHair.MatchHair"));
	const FName EyesHeterochromia(TEXT("Eyes.Heterochromia"));
	const FName ChannelHairRoot(TEXT("Hair.Root"));
	const FName ChannelHairBrows(TEXT("Hair.Brows"));
	const FName ChannelHairFacial(TEXT("Hair.FacialHair"));
	const FName ChannelIrisL(TEXT("Eyes.IrisL"));
	const FName ChannelIrisR(TEXT("Eyes.IrisR"));
	const FName CategoryLantern(TEXT("Lantern"));
}

namespace
{
	const TCHAR* const ShareCodePrefix = TEXT("LYR1:");

	// Share codes store floats as integers in thousandths: short, exact and locale-proof.
	constexpr double ShareScale = 1000.0;

	const ULyrisAppearanceCatalog* CatalogOrDefault(const ULyrisAppearanceCatalog* Catalog)
	{
		return Catalog ? Catalog : ULyrisAppearanceCatalog::GetDefault();
	}

	bool IsSkinChannel(FName Id)
	{
		return Id == ULyrisAppearanceCatalog::GetSkinChannelFor(LyrisPeople::Human)
			|| Id == ULyrisAppearanceCatalog::GetSkinChannelFor(LyrisPeople::MoonlitElf)
			|| Id == ULyrisAppearanceCatalog::GetSkinChannelFor(LyrisPeople::Deepkin);
	}

	bool IsScleraChannel(FName Id)
	{
		return Id == ULyrisAppearanceCatalog::GetScleraChannelFor(LyrisPeople::Human)
			|| Id == ULyrisAppearanceCatalog::GetScleraChannelFor(LyrisPeople::Deepkin);
	}

	/** Same relative position in another band (spec 9.10: "matching band position"). */
	FLyrisColorPick MapPickToBand(const FLyrisColorPick& From, int32 FromCount, const FLyrisColorChannelDef& To)
	{
		FLyrisColorPick Out = From;
		const int32 ToCount = To.Swatches.Num();
		if (FromCount > 1 && ToCount > 0)
		{
			const float T = FMath::Clamp(static_cast<float>(From.Swatch) / static_cast<float>(FromCount - 1), 0.f, 1.f);
			Out.Swatch = FMath::RoundToInt(T * static_cast<float>(ToCount - 1));
		}
		Out.Swatch = FMath::Clamp(Out.Swatch, 0, FMath::Max(ToCount - 1, 0));
		Out.HueShift = FMath::Clamp(Out.HueShift, -To.MaxHueShift, To.MaxHueShift);
		Out.ValueShift = FMath::Clamp(Out.ValueShift, -To.MaxValueShift, To.MaxValueShift);
		return Out;
	}

	/**
	 * If the look has no pick for People's channel in a per-People family (skin tone or eye whites), fill it
	 * from another People's pick at the matching band position. PreferFrom is tried first.
	 */
	void FillPerPeoplePick(const ULyrisAppearanceCatalog& Catalog, FLyrisAppearance& A, FName (*ChannelFor)(FName), FName PreferFrom)
	{
		const FName Target = ChannelFor(A.People);
		if (A.Colors.Contains(Target))
		{
			return;
		}
		const FLyrisColorChannelDef* TargetDef = Catalog.FindChannel(Target);
		if (!TargetDef)
		{
			return;
		}
		TArray<FName> Order;
		if (!PreferFrom.IsNone())
		{
			Order.Add(PreferFrom);
		}
		Order.Append({ LyrisPeople::Human, LyrisPeople::MoonlitElf, LyrisPeople::Deepkin });
		for (const FName& Other : Order)
		{
			const FName Source = ChannelFor(Other);
			if (Source == Target)
			{
				continue;
			}
			const FLyrisColorPick* Pick = A.Colors.Find(Source);
			const FLyrisColorChannelDef* SourceDef = Catalog.FindChannel(Source);
			if (Pick && SourceDef)
			{
				A.Colors.Add(Target, MapPickToBand(*Pick, SourceDef->Swatches.Num(), *TargetDef));
				return;
			}
		}
	}

	int32 ToMilli(float V) { return static_cast<int32>(FMath::RoundToDouble(static_cast<double>(V) * ShareScale)); }
	float FromMilli(double V) { return static_cast<float>(V / ShareScale); }

	template <typename ValueType>
	TArray<FName> SortedKeys(const TMap<FName, ValueType>& Map)
	{
		TArray<FName> Keys;
		Map.GetKeys(Keys);
		Keys.Sort([](const FName& A, const FName& B) { return A.LexicalLess(B); });
		return Keys;
	}
}

// =====================================================================================================
// Colours
// =====================================================================================================

FLinearColor ULyrisAppearanceLibrary::ResolveColor(const FLyrisColorChannelDef& Channel, const FLyrisColorPick& Pick)
{
	if (Channel.Swatches.Num() == 0)
	{
		return FLinearColor::White;
	}
	const int32 Index = FMath::Clamp(Pick.Swatch, 0, Channel.Swatches.Num() - 1);
	const FLinearColor Base = Channel.Swatches[Index].Color;

	const float MaxHue = FMath::Clamp(Channel.MaxHueShift, 0.f, 0.5f);
	const float MaxValue = FMath::Clamp(Channel.MaxValueShift, 0.f, 1.f);
	const float Hue = FMath::Clamp(Pick.HueShift, -MaxHue, MaxHue);
	const float Value = FMath::Clamp(Pick.ValueShift, -MaxValue, MaxValue);
	if (FMath::IsNearlyZero(Hue) && FMath::IsNearlyZero(Value))
	{
		return Base;
	}

	// Shift in sRGB HSV so a value step looks even across the band, then go back to linear.
	const FColor Srgb = Base.ToFColor(/*bSRGB*/ true);
	const FLinearColor SrgbFloat(Srgb.R / 255.f, Srgb.G / 255.f, Srgb.B / 255.f, 1.f);
	FLinearColor Hsv = SrgbFloat.LinearRGBToHSV(); // R = hue in degrees, G = saturation, B = value
	Hsv.R = FMath::Fmod(Hsv.R + Hue * 360.f + 360.f, 360.f);
	Hsv.B = FMath::Clamp(Hsv.B + Value, 0.f, 1.f);
	const FLinearColor ShiftedSrgb = Hsv.HSVToLinearRGB();
	const FColor Quantized = ShiftedSrgb.ToFColor(/*bSRGB*/ false); // plain quantize, values are already sRGB
	FLinearColor Result(Quantized); // FColor -> FLinearColor converts sRGB to linear
	Result.A = Base.A;
	return Result;
}

FLyrisColorPick ULyrisAppearanceLibrary::GetEffectivePick(const FLyrisAppearance& Appearance, FName Channel)
{
	const FLyrisColorPick* Pick = Appearance.Colors.Find(Channel);
	return Pick ? *Pick : FLyrisColorPick();
}

// =====================================================================================================
// Effective values
// =====================================================================================================

float ULyrisAppearanceLibrary::GetSliderValue(const FLyrisAppearance& Appearance, const FLyrisSliderDef& Def)
{
	if (!Def.AllowsPeople(Appearance.People))
	{
		return Def.ClampValue(Def.Default);
	}
	if (const float* V = Appearance.Sliders.Find(Def.Id))
	{
		return Def.ClampValue(*V);
	}
	if (const float* V = Appearance.PartScalars.Find(Def.Id))
	{
		return Def.ClampValue(*V);
	}
	return Def.ClampValue(Def.Default);
}

float ULyrisAppearanceLibrary::GetPartScalarValue(const ULyrisAppearanceCatalog* Catalog, const FLyrisAppearance& Appearance, FName Key)
{
	const ULyrisAppearanceCatalog* C = CatalogOrDefault(Catalog);
	const FLyrisSliderDef* Def = C ? C->FindPartScalar(Key) : nullptr;
	if (!Def)
	{
		const float* V = Appearance.PartScalars.Find(Key);
		return V ? *V : 0.f;
	}
	if (!Def->AllowsPeople(Appearance.People))
	{
		return Def->ClampValue(Def->Default);
	}
	if (const float* V = Appearance.PartScalars.Find(Key))
	{
		return Def->ClampValue(*V);
	}
	if (const float* V = Appearance.Sliders.Find(Key))
	{
		return Def->ClampValue(*V);
	}
	return Def->ClampValue(Def->Default);
}

FName ULyrisAppearanceLibrary::GetEffectivePart(const ULyrisAppearanceCatalog* Catalog, const FLyrisAppearance& Appearance, FName Slot)
{
	if (const FName* Part = Appearance.Parts.Find(Slot))
	{
		return *Part;
	}
	const ULyrisAppearanceCatalog* C = CatalogOrDefault(Catalog);
	const FLyrisPartSlotDef* SlotDef = C ? C->FindSlot(Slot) : nullptr;
	return SlotDef ? SlotDef->DefaultPart : NAME_None;
}

bool ULyrisAppearanceLibrary::IsToggleKey(FName Key)
{
	return Key == LyrisAppearanceIds::BrowsMatchHair || Key == LyrisAppearanceIds::FacialHairMatchHair || Key == LyrisAppearanceIds::EyesHeterochromia;
}

// =====================================================================================================
// Rules: adult guard, sanitize, change People
// =====================================================================================================

bool ULyrisAppearanceLibrary::ApplyAdultGuard(FLyrisAppearance& InOut)
{
	using namespace LyrisAppearanceIds;
	const float Height = InOut.Sliders.FindRef(BodyHeight); // missing = default 0
	if (Height >= -0.5f)
	{
		return false;
	}
	bool bChanged = false;
	float* Head = InOut.Sliders.Find(BodyHeadSize);
	if (Head && *Head > 0.3f)
	{
		*Head = 0.3f;
		bChanged = true;
	}
	if (Head && *Head > 0.f)
	{
		for (const FName& EyeId : { EyesSizeL, EyesSizeR })
		{
			float* Eye = InOut.Sliders.Find(EyeId);
			if (Eye && *Eye > 0.6f)
			{
				*Eye = 0.6f;
				bChanged = true;
			}
		}
	}
	return bChanged;
}

void ULyrisAppearanceLibrary::SanitizeAppearance(const ULyrisAppearanceCatalog* Catalog, FLyrisAppearance& A)
{
	const ULyrisAppearanceCatalog* C = CatalogOrDefault(Catalog);
	if (!C)
	{
		ApplyAdultGuard(A);
		return;
	}

	if (!C->Peoples.Contains(A.People))
	{
		A.People = LyrisPeople::Human;
	}
	if (!C->Frames.Contains(A.Frame))
	{
		A.Frame = LyrisFrames::FrameA;
	}
	A.Version = FMath::Max(A.Version, 1);

	// Sliders: keep known, offered, clamped. Part-scalar keys written into Sliders move to PartScalars.
	{
		TMap<FName, float> Clean;
		for (const TPair<FName, float>& KV : A.Sliders)
		{
			if (const FLyrisSliderDef* Def = C->FindSlider(KV.Key))
			{
				if (Def->AllowsPeople(A.People))
				{
					Clean.Add(KV.Key, Def->ClampValue(KV.Value));
				}
			}
			else if (C->FindPartScalar(KV.Key) && !A.PartScalars.Contains(KV.Key))
			{
				A.PartScalars.Add(KV.Key, KV.Value);
			}
		}
		A.Sliders = MoveTemp(Clean);
	}

	// Part scalars: keep known, offered, clamped; toggles become exactly 0 or 1.
	{
		TMap<FName, float> Clean;
		for (const TPair<FName, float>& KV : A.PartScalars)
		{
			const FLyrisSliderDef* Def = C->FindPartScalar(KV.Key);
			if (!Def || !Def->AllowsPeople(A.People))
			{
				continue;
			}
			float V = Def->ClampValue(KV.Value);
			if (IsToggleKey(KV.Key))
			{
				V = V >= 0.5f ? 1.f : 0.f;
			}
			Clean.Add(KV.Key, V);
		}
		A.PartScalars = MoveTemp(Clean);
	}

	// Parts: slot must exist, part must belong to it and be offered to this People. None only in optional slots.
	{
		TMap<FName, FName> Clean;
		for (const TPair<FName, FName>& KV : A.Parts)
		{
			const FLyrisPartSlotDef* SlotDef = C->FindSlot(KV.Key);
			if (!SlotDef || SlotDef->Category == LyrisAppearanceIds::CategoryLantern)
			{
				continue; // the lantern lives in FLyrisCharacterProfile, not in the look
			}
			if (KV.Value.IsNone())
			{
				if (SlotDef->bOptional)
				{
					Clean.Add(KV.Key, NAME_None);
				}
				continue;
			}
			const FLyrisPartDef* Part = C->FindPart(KV.Value);
			if (Part && Part->Slot == KV.Key && Part->AllowsPeople(A.People))
			{
				Clean.Add(KV.Key, KV.Value);
			}
		}
		A.Parts = MoveTemp(Clean);
	}

	// Colours: channel must exist; clamp swatch and shifts. Per-People families (skin tone, eye whites)
	// keep the picks of other Peoples so switching back restores them; they are only applied for the
	// current People. Every other People-restricted channel is dropped.
	{
		TMap<FName, FLyrisColorPick> Clean;
		for (const TPair<FName, FLyrisColorPick>& KV : A.Colors)
		{
			const FLyrisColorChannelDef* Ch = C->FindChannel(KV.Key);
			if (!Ch || Ch->Category == LyrisAppearanceIds::CategoryLantern)
			{
				continue;
			}
			if (!Ch->AllowsPeople(A.People) && !IsSkinChannel(KV.Key) && !IsScleraChannel(KV.Key))
			{
				continue;
			}
			FLyrisColorPick P = KV.Value;
			P.Swatch = FMath::Clamp(P.Swatch, 0, FMath::Max(Ch->Swatches.Num() - 1, 0));
			P.HueShift = FMath::Clamp(P.HueShift, -Ch->MaxHueShift, Ch->MaxHueShift);
			P.ValueShift = FMath::Clamp(P.ValueShift, -Ch->MaxValueShift, Ch->MaxValueShift);
			Clean.Add(KV.Key, P);
		}
		A.Colors = MoveTemp(Clean);
	}
	FillPerPeoplePick(*C, A, &ULyrisAppearanceCatalog::GetSkinChannelFor, NAME_None);
	FillPerPeoplePick(*C, A, &ULyrisAppearanceCatalog::GetScleraChannelFor, NAME_None);

	// Heterochromia off: the right eye always follows the left (spec 3.3).
	if (GetPartScalarValue(C, A, LyrisAppearanceIds::EyesHeterochromia) < 0.5f)
	{
		if (const FLyrisColorPick* Left = A.Colors.Find(LyrisAppearanceIds::ChannelIrisL))
		{
			const FLyrisColorPick Copy = *Left;
			A.Colors.Add(LyrisAppearanceIds::ChannelIrisR, Copy);
		}
		else
		{
			A.Colors.Remove(LyrisAppearanceIds::ChannelIrisR);
		}
	}

	ApplyAdultGuard(A);
}

void ULyrisAppearanceLibrary::ChangePeople(const ULyrisAppearanceCatalog* Catalog, FLyrisAppearance& InOut, FName NewPeople)
{
	const ULyrisAppearanceCatalog* C = CatalogOrDefault(Catalog);
	const FName OldPeople = InOut.People;
	InOut.People = NewPeople;
	if (C && OldPeople != NewPeople)
	{
		// Prefer the People we came from when mapping the skin and eye-white picks.
		FillPerPeoplePick(*C, InOut, &ULyrisAppearanceCatalog::GetSkinChannelFor, OldPeople);
		FillPerPeoplePick(*C, InOut, &ULyrisAppearanceCatalog::GetScleraChannelFor, OldPeople);
	}
	SanitizeAppearance(C, InOut);
}

// =====================================================================================================
// Share codes: "LYR1:" + Base64(UTF-8 compact JSON)
// JSON: {"v":1,"p":"Human","f":"FrameA","s":{id:milli},"pt":{slot:part},"c":{ch:[swatch,hueMilli,valueMilli]},"ps":{key:milli}}
// =====================================================================================================

FString ULyrisAppearanceLibrary::ToShareCode(const FLyrisAppearance& A)
{
	FString Json;
	TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Json);
	Writer->WriteObjectStart();
	Writer->WriteValue(TEXT("v"), A.Version);
	Writer->WriteValue(TEXT("p"), A.People.ToString());
	Writer->WriteValue(TEXT("f"), A.Frame.ToString());

	Writer->WriteObjectStart(TEXT("s"));
	for (const FName& Key : SortedKeys(A.Sliders))
	{
		Writer->WriteValue(Key.ToString(), ToMilli(A.Sliders[Key]));
	}
	Writer->WriteObjectEnd();

	Writer->WriteObjectStart(TEXT("pt"));
	for (const FName& Key : SortedKeys(A.Parts))
	{
		Writer->WriteValue(Key.ToString(), A.Parts[Key].ToString());
	}
	Writer->WriteObjectEnd();

	Writer->WriteObjectStart(TEXT("c"));
	for (const FName& Key : SortedKeys(A.Colors))
	{
		const FLyrisColorPick& P = A.Colors[Key];
		Writer->WriteArrayStart(Key.ToString());
		Writer->WriteValue(P.Swatch);
		Writer->WriteValue(ToMilli(P.HueShift));
		Writer->WriteValue(ToMilli(P.ValueShift));
		Writer->WriteArrayEnd();
	}
	Writer->WriteObjectEnd();

	Writer->WriteObjectStart(TEXT("ps"));
	for (const FName& Key : SortedKeys(A.PartScalars))
	{
		Writer->WriteValue(Key.ToString(), ToMilli(A.PartScalars[Key]));
	}
	Writer->WriteObjectEnd();

	Writer->WriteObjectEnd();
	Writer->Close();

	const FTCHARToUTF8 Utf8(*Json);
	return FString(ShareCodePrefix) + FBase64::Encode(reinterpret_cast<const uint8*>(Utf8.Get()), static_cast<uint32>(Utf8.Length()));
}

bool ULyrisAppearanceLibrary::FromShareCode(const FString& Code, FLyrisAppearance& Out)
{
	FString Trimmed = Code.TrimStartAndEnd();
	if (!Trimmed.StartsWith(ShareCodePrefix, ESearchCase::CaseSensitive))
	{
		return false;
	}
	Trimmed = Trimmed.RightChop(FCString::Strlen(ShareCodePrefix));

	TArray<uint8> Bytes;
	if (!FBase64::Decode(Trimmed, Bytes) || Bytes.Num() == 0)
	{
		return false;
	}
	// BufferToString decodes UTF-8 (the codes are plain ASCII in practice).
	FString Json;
	FFileHelper::BufferToString(Json, Bytes.GetData(), Bytes.Num());

	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<TCHAR>> Reader = TJsonReaderFactory<TCHAR>::Create(Json);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		return false;
	}

	FLyrisAppearance A;
	int32 Version = 1;
	Root->TryGetNumberField(TEXT("v"), Version);
	A.Version = FMath::Max(1, Version);
	FString Str;
	if (Root->TryGetStringField(TEXT("p"), Str)) { A.People = FName(*Str); }
	if (Root->TryGetStringField(TEXT("f"), Str)) { A.Frame = FName(*Str); }

	const TSharedPtr<FJsonObject>* Obj = nullptr;
	if (Root->TryGetObjectField(TEXT("s"), Obj) && Obj && Obj->IsValid())
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& KV : (*Obj)->Values)
		{
			double D = 0.0;
			if (KV.Value.IsValid() && KV.Value->TryGetNumber(D)) { A.Sliders.Add(FName(*KV.Key), FromMilli(D)); }
		}
	}
	if (Root->TryGetObjectField(TEXT("pt"), Obj) && Obj && Obj->IsValid())
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& KV : (*Obj)->Values)
		{
			FString PartId;
			if (KV.Value.IsValid() && KV.Value->TryGetString(PartId)) { A.Parts.Add(FName(*KV.Key), FName(*PartId)); }
		}
	}
	if (Root->TryGetObjectField(TEXT("c"), Obj) && Obj && Obj->IsValid())
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& KV : (*Obj)->Values)
		{
			const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
			if (!KV.Value.IsValid() || !KV.Value->TryGetArray(Arr) || !Arr || Arr->Num() < 1)
			{
				continue;
			}
			FLyrisColorPick P;
			double D = 0.0;
			if ((*Arr)[0].IsValid() && (*Arr)[0]->TryGetNumber(D)) { P.Swatch = static_cast<int32>(D); }
			if (Arr->Num() > 1 && (*Arr)[1].IsValid() && (*Arr)[1]->TryGetNumber(D)) { P.HueShift = FromMilli(D); }
			if (Arr->Num() > 2 && (*Arr)[2].IsValid() && (*Arr)[2]->TryGetNumber(D)) { P.ValueShift = FromMilli(D); }
			A.Colors.Add(FName(*KV.Key), P);
		}
	}
	if (Root->TryGetObjectField(TEXT("ps"), Obj) && Obj && Obj->IsValid())
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& KV : (*Obj)->Values)
		{
			double D = 0.0;
			if (KV.Value.IsValid() && KV.Value->TryGetNumber(D)) { A.PartScalars.Add(FName(*KV.Key), FromMilli(D)); }
		}
	}

	// Unknown ids, other-People entries, out-of-range values and the adult guard (spec 9.9).
	SanitizeAppearance(nullptr, A);
	Out = MoveTemp(A);
	return true;
}

// =====================================================================================================
// Randomise (spec 9.3)
// =====================================================================================================

namespace
{
	/** Chance that an optional slot gets a part at a given wildness. */
	float FillChance(FName Slot, FName People, float W)
	{
		const FString S = Slot.ToString();
		if (S == TEXT("Brows"))         { return 0.97f; }
		if (S == TEXT("Lashes"))        { return 0.9f; }
		if (S == TEXT("FacialHair"))    { return 0.2f + 0.2f * W; }
		if (S == TEXT("HairAccessory")) { return 0.1f + 0.4f * W; }
		if (S == TEXT("Freckles"))      { return 0.35f; }
		if (S == TEXT("Moles"))         { return 0.25f; }
		if (S == TEXT("Scars"))         { return 0.05f + 0.25f * W; }
		if (S == TEXT("Markings"))      { return People == LyrisPeople::Human ? 0.1f + 0.2f * W : 0.4f + 0.4f * W; }
		if (S == TEXT("FacePaint"))     { return W < 0.2f ? 0.f : 0.05f + 0.4f * W; }
		if (S == TEXT("Layer"))         { return 0.4f; }
		// Eyeshadow, Eyeliner, Lips, Blush: "sometimes" at normal wildness.
		return W < 0.15f ? 0.05f : 0.1f + 0.5f * W;
	}
}

void ULyrisAppearanceLibrary::RandomizeAppearance(const ULyrisAppearanceCatalog* Catalog, FLyrisAppearance& InOut, FRandomStream& Stream,
	const TSet<FName>& LockedCategories, float Wildness)
{
	const ULyrisAppearanceCatalog* C = CatalogOrDefault(Catalog);
	if (!C)
	{
		return;
	}
	const float W = FMath::Clamp(Wildness, 0.f, 1.f);
	const FName People = InOut.People;
	auto IsLocked = [&LockedCategories](FName Category)
	{
		return Category == LyrisAppearanceIds::CategoryLantern || LockedCategories.Contains(Category);
	};

	// Centre of the spread: one of this People's presets.
	const FLyrisAppearance Base = MakePreset(People, Stream.RandRange(0, GetPresetCount() - 1));

	// Sliders and part scalars. Spread grows with wildness: +-0.25 at 0, about +-0.5 at 0.35, full at 1.
	const float Spread = 0.25f + 0.75f * W;
	auto RollValue = [&](const FLyrisSliderDef& Def, float Centre)
	{
		const float HalfRange = 0.5f * FMath::Abs(Def.Max - Def.Min);
		return Def.ClampValue(Centre + Stream.FRandRange(-Spread, Spread) * HalfRange);
	};

	TSet<FName> Done;
	for (const FLyrisSliderDef& Def : C->Sliders)
	{
		if (IsLocked(Def.Category) || !Def.AllowsPeople(People) || Done.Contains(Def.Id))
		{
			continue;
		}
		const float V = RollValue(Def, GetSliderValue(Base, Def));
		InOut.Sliders.Add(Def.Id, V);
		Done.Add(Def.Id);
		// Mirror pairs: same value plus a small difference (spec 9.3).
		if (!Def.MirrorOf.IsNone())
		{
			if (const FLyrisSliderDef* Mirror = C->FindSlider(Def.MirrorOf))
			{
				if (Mirror->AllowsPeople(People) && !Done.Contains(Mirror->Id))
				{
					const float Diff = Stream.FRandRange(-0.1f, 0.1f) * W;
					InOut.Sliders.Add(Mirror->Id, Mirror->ClampValue(V + Diff));
					Done.Add(Mirror->Id);
				}
			}
		}
	}

	for (const FLyrisSliderDef& Def : C->PartScalarDefs)
	{
		if (IsLocked(Def.Category) || !Def.AllowsPeople(People))
		{
			continue;
		}
		float V;
		if (Def.Id == LyrisAppearanceIds::BrowsMatchHair || Def.Id == LyrisAppearanceIds::FacialHairMatchHair)
		{
			V = (W > 0.7f && Stream.FRand() < 0.2f) ? 0.f : 1.f;
		}
		else if (Def.Id == LyrisAppearanceIds::EyesHeterochromia)
		{
			V = (W > 0.5f && Stream.FRand() < 0.15f * W) ? 1.f : 0.f;
		}
		else
		{
			V = RollValue(Def, GetPartScalarValue(C, Base, Def.Id));
		}
		InOut.PartScalars.Add(Def.Id, V);
	}

	// Parts
	for (const FLyrisPartSlotDef& Slot : C->Slots)
	{
		if (IsLocked(Slot.Category))
		{
			continue;
		}
		const TArray<FLyrisPartDef> Options = C->GetPartsForSlot(Slot.Slot, People);
		if (Options.Num() == 0)
		{
			continue;
		}
		if (Slot.bOptional && Stream.FRand() >= FillChance(Slot.Slot, People, W))
		{
			InOut.Parts.Add(Slot.Slot, NAME_None);
			continue;
		}
		if (W < 0.15f)
		{
			// Common parts only: the preset's (or slot default) choice when it is available.
			const FName Preferred = GetEffectivePart(C, Base, Slot.Slot);
			if (!Preferred.IsNone() && Options.ContainsByPredicate([Preferred](const FLyrisPartDef& P) { return P.Id == Preferred; }))
			{
				InOut.Parts.Add(Slot.Slot, Preferred);
				continue;
			}
		}
		InOut.Parts.Add(Slot.Slot, Options[Stream.RandRange(0, Options.Num() - 1)].Id);
	}

	// Colours. No shifts at wildness ~0, half the max shift at 0.35, full at 1.
	const float ShiftScale = W < 0.15f ? 0.f : FMath::Clamp(W * 1.4f, 0.f, 1.f);
	for (const FLyrisColorChannelDef& Ch : C->ColorChannels)
	{
		if (IsLocked(Ch.Category) || !Ch.AllowsPeople(People) || Ch.Swatches.Num() == 0)
		{
			continue;
		}
		const int32 N = Ch.Swatches.Num();
		FLyrisColorPick P;
		const bool bHair = Ch.Id.ToString().StartsWith(TEXT("Hair.")) && Ch.Id != FName(TEXT("Hair.Accessory"));
		if (W < 0.2f)
		{
			if (bHair)
			{
				P.Swatch = Stream.RandRange(0, FMath::Min(12, N - 1)); // natural hair colours
			}
			else if (IsSkinChannel(Ch.Id))
			{
				P.Swatch = Stream.RandRange(N / 4, FMath::Max(N / 4, (3 * N) / 4)); // middle of the People's band
			}
			else
			{
				P.Swatch = GetEffectivePick(Base, Ch.Id).Swatch;
			}
		}
		else if (bHair && N > 13)
		{
			const bool bStorybook = Stream.FRand() < 0.1f + 0.4f * W;
			P.Swatch = bStorybook ? Stream.RandRange(13, N - 1) : Stream.RandRange(0, 12);
		}
		else
		{
			P.Swatch = Stream.RandRange(0, N - 1);
		}
		P.Swatch = FMath::Clamp(P.Swatch, 0, N - 1);
		P.HueShift = Stream.FRandRange(-1.f, 1.f) * Ch.MaxHueShift * ShiftScale;
		P.ValueShift = Stream.FRandRange(-1.f, 1.f) * Ch.MaxValueShift * ShiftScale;
		InOut.Colors.Add(Ch.Id, P);
	}

	// Ranges, People rules, heterochromia copy and the adult guard (always applies).
	SanitizeAppearance(C, InOut);
}

// =====================================================================================================
// Presets (spec 9.8). Names approved by the user. Each is a complete look and a valid share code.
// =====================================================================================================

namespace
{
	struct FPreset
	{
		FLyrisAppearance A;

		explicit FPreset(FName People, FName Frame) { A.People = People; A.Frame = Frame; }

		FPreset& S(const TCHAR* Id, float V) { A.Sliders.Add(FName(Id), V); return *this; }
		/** Both sides of a mirror pair: Pair("Ears.Point", 0.6) sets Ears.PointL and Ears.PointR. */
		FPreset& Pair(const TCHAR* IdBase, float V)
		{
			A.Sliders.Add(FName(*(FString(IdBase) + TEXT("L"))), V);
			A.Sliders.Add(FName(*(FString(IdBase) + TEXT("R"))), V);
			return *this;
		}
		FPreset& P(const TCHAR* Slot, const TCHAR* Part) { A.Parts.Add(FName(Slot), FName(*FString::Printf(TEXT("%s.%s"), Slot, Part))); return *this; }
		FPreset& C(FName Channel, int32 Swatch, float Hue = 0.f, float Value = 0.f)
		{
			FLyrisColorPick Pick;
			Pick.Swatch = Swatch;
			Pick.HueShift = Hue;
			Pick.ValueShift = Value;
			A.Colors.Add(Channel, Pick);
			return *this;
		}
		FPreset& C(const TCHAR* Channel, int32 Swatch, float Hue = 0.f, float Value = 0.f) { return C(FName(Channel), Swatch, Hue, Value); }
		FPreset& Skin(int32 Swatch, float Hue = 0.f, float Value = 0.f) { return C(ULyrisAppearanceCatalog::GetSkinChannelFor(A.People), Swatch, Hue, Value); }
		FPreset& PS(const TCHAR* Key, float V) { A.PartScalars.Add(FName(Key), V); return *this; }
	};

	const TCHAR* const HumanNames[] = { TEXT("Harbor Hand"), TEXT("Lamplighter"), TEXT("Old Salt"), TEXT("Orchard Keeper"), TEXT("Clerk of Moonharbor"), TEXT("Drover") };
	const TCHAR* const ElfNames[]   = { TEXT("Moonwatcher"), TEXT("Star Archivist"), TEXT("Night Gardener"), TEXT("Pale Sail"), TEXT("Lantern Bearer"), TEXT("Dusk Wanderer") };
	const TCHAR* const DeepNames[]  = { TEXT("Tidewalker"), TEXT("Reef Diver"), TEXT("Hollowdeep Miner"), TEXT("Kelp Singer"), TEXT("Bay Keeper"), TEXT("Storm Pilot") };

	// Swatch indices refer to the spec 5.2 bands, e.g. hair 7 = Brown, iris 8 = Moonglass, cloth 13 = Deep sea.
	FLyrisAppearance BuildHumanPreset(int32 I)
	{
		const FName H = LyrisPeople::Human;
		switch (I)
		{
		default:
		case 0: // Harbor Hand: wind-tossed deckhand, sun-kissed
			return FPreset(H, LyrisFrames::FrameB).Skin(4).C(TEXT("Hair.Root"), 7).C(TEXT("Eyes.IrisL"), 0)
				.P(TEXT("Hair"), TEXT("WindTossed")).P(TEXT("Outfit"), TEXT("DeckhandCoat")).P(TEXT("Freckles"), TEXT("SunKissed"))
				.P(TEXT("Stance"), TEXT("SeaLegs")).P(TEXT("Expression"), TEXT("Bright")).P(TEXT("Voice"), TEXT("Warm1"))
				.C(TEXT("Outfit.Primary"), 13).C(TEXT("Outfit.Secondary"), 1).C(TEXT("Outfit.Trim"), 0)
				.S(TEXT("Body.ShoulderWidth"), 0.3f).S(TEXT("Body.MuscleTone"), 0.3f).S(TEXT("Face.JawWidth"), 0.2f)
				.S(TEXT("Skin.Rosiness"), 0.4f).A;
		case 1: // Lamplighter: copper bob, amber eyes, gold neckerchief
			return FPreset(H, LyrisFrames::FrameA).Skin(1).C(TEXT("Hair.Root"), 4).C(TEXT("Eyes.IrisL"), 3)
				.P(TEXT("Hair"), TEXT("LamplighterBob")).P(TEXT("Outfit"), TEXT("PlainTraveller")).P(TEXT("Layer"), TEXT("Neckerchief"))
				.P(TEXT("Expression"), TEXT("Calm")).P(TEXT("Voice"), TEXT("Bright1")).P(TEXT("Freckles"), TEXT("NoseDust"))
				.C(TEXT("Outfit.Primary"), 3).C(TEXT("Outfit.Secondary"), 0).C(TEXT("Outfit.Layer"), 8)
				.Pair(TEXT("Eyes.Size"), 0.2f).S(TEXT("Face.Roundness"), 0.3f).S(TEXT("Nose.TipLift"), 0.3f).A;
		case 2: // Old Salt: silver crop, full beard, weathered
			return FPreset(H, LyrisFrames::FrameB).Skin(7).C(TEXT("Hair.Root"), 11).C(TEXT("Eyes.IrisL"), 10)
				.P(TEXT("Hair"), TEXT("CloseShave")).P(TEXT("FacialHair"), TEXT("FullBeard")).P(TEXT("Brows"), TEXT("Bushy"))
				.P(TEXT("Outfit"), TEXT("DeckhandCoat")).P(TEXT("Layer"), TEXT("WoolScarf")).P(TEXT("Expression"), TEXT("Wry"))
				.P(TEXT("Voice"), TEXT("Low1")).P(TEXT("Stance"), TEXT("SeaLegs"))
				.C(TEXT("Outfit.Primary"), 13).C(TEXT("Outfit.Layer"), 7)
				.S(TEXT("Skin.AgeLines"), 0.5f).S(TEXT("Body.Belly"), 0.3f).S(TEXT("Nose.Length"), 0.3f).S(TEXT("Body.Lean"), -0.3f).A;
		case 3: // Orchard Keeper: wheat braid, freckles, flower crown
			return FPreset(H, LyrisFrames::FrameA).Skin(3).C(TEXT("Hair.Root"), 1).C(TEXT("Eyes.IrisL"), 5)
				.P(TEXT("Hair"), TEXT("RopeBraid")).P(TEXT("Freckles"), TEXT("FullFace")).P(TEXT("Outfit"), TEXT("GrowerSmock"))
				.P(TEXT("HairAccessory"), TEXT("FlowerCrown")).P(TEXT("Expression"), TEXT("Bright")).P(TEXT("Voice"), TEXT("Soft1"))
				.C(TEXT("Outfit.Primary"), 9).C(TEXT("Outfit.Secondary"), 2)
				.S(TEXT("Skin.Rosiness"), 0.6f).S(TEXT("Body.Softness"), 0.3f).S(TEXT("Face.CheekFullness"), 0.3f).A;
		case 4: // Clerk of Moonharbor: ink bun with a pencil, neat and upright
			return FPreset(H, LyrisFrames::FrameA).Skin(10).C(TEXT("Hair.Root"), 9).C(TEXT("Eyes.IrisL"), 1)
				.P(TEXT("Hair"), TEXT("ScholarsBun")).P(TEXT("HairAccessory"), TEXT("Pencil")).P(TEXT("Outfit"), TEXT("TraderWaistcoat"))
				.P(TEXT("Eyeliner"), TEXT("Tightline")).P(TEXT("Expression"), TEXT("Determined")).P(TEXT("Stance"), TEXT("Upright"))
				.P(TEXT("Voice"), TEXT("Warm2")).C(TEXT("Makeup.Eyeliner"), 0)
				.C(TEXT("Outfit.Primary"), 14).C(TEXT("Outfit.Secondary"), 0).C(TEXT("Outfit.Trim"), 0)
				.S(TEXT("Body.Lean"), 0.4f).Pair(TEXT("Brows.Arch"), 0.3f).S(TEXT("Face.ChinPoint"), 0.2f).A;
		case 5: // Drover: locs, poncho, a scar from the road
			return FPreset(H, LyrisFrames::FrameB).Skin(9).C(TEXT("Hair.Root"), 8).C(TEXT("Eyes.IrisL"), 4)
				.P(TEXT("Hair"), TEXT("DriftwoodLocs")).P(TEXT("Outfit"), TEXT("WandererLayers")).P(TEXT("Layer"), TEXT("Poncho"))
				.P(TEXT("FacialHair"), TEXT("Stubble")).P(TEXT("Scars"), TEXT("CheekLine")).P(TEXT("Expression"), TEXT("Calm"))
				.P(TEXT("Voice"), TEXT("Low2")).P(TEXT("Stance"), TEXT("Easy"))
				.C(TEXT("Outfit.Primary"), 3).C(TEXT("Outfit.Layer"), 6)
				.S(TEXT("Body.Height"), 0.3f).S(TEXT("Body.LegLength"), 0.2f).S(TEXT("Face.JawAngle"), 0.3f).A;
		}
	}

	FLyrisAppearance BuildElfPreset(int32 I)
	{
		const FName E = LyrisPeople::MoonlitElf;
		switch (I)
		{
		default:
		case 0: // Moonwatcher: silver hair fading to moonglass, crescent sigil, soft glow
			return FPreset(E, LyrisFrames::FrameA).Skin(3).C(TEXT("Hair.Root"), 11).C(TEXT("Hair.Tip"), 13).C(TEXT("Eyes.IrisL"), 8)
				.C(TEXT("Eyes.Glow"), 0).C(TEXT("Skin.Markings"), 0)
				.P(TEXT("Hair"), TEXT("Moonfall")).P(TEXT("Markings"), TEXT("CrescentBrow")).P(TEXT("PupilShape"), TEXT("Crescent"))
				.P(TEXT("Outfit"), TEXT("ScholarCoat")).P(TEXT("Expression"), TEXT("Dreamy")).P(TEXT("Voice"), TEXT("Soft2"))
				.C(TEXT("Outfit.Primary"), 13).C(TEXT("Outfit.Trim"), 1)
				.S(TEXT("Eyes.GlowStrength"), 0.5f).Pair(TEXT("Ears.Point"), 0.6f).PS(TEXT("Hair.GradientStart"), 0.5f).A;
		case 1: // Star Archivist: snow-white half-up, starfield irises
			return FPreset(E, LyrisFrames::FrameB).Skin(6).C(TEXT("Hair.Root"), 12).C(TEXT("Eyes.IrisL"), 14).C(TEXT("Skin.Markings"), 1)
				.P(TEXT("Hair"), TEXT("HalfMoon")).P(TEXT("Markings"), TEXT("StarTrail")).P(TEXT("Brows"), TEXT("MoonWisp"))
				.P(TEXT("IrisPattern"), TEXT("Starfield")).P(TEXT("HairAccessory"), TEXT("LampPin")).P(TEXT("Outfit"), TEXT("ScholarCoat"))
				.P(TEXT("Expression"), TEXT("Calm")).P(TEXT("Voice"), TEXT("Warm1"))
				.C(TEXT("Outfit.Primary"), 14).C(TEXT("Outfit.Trim"), 3)
				.Pair(TEXT("Ears.Point"), 0.4f).S(TEXT("Face.Length"), 0.2f).A;
		case 2: // Night Gardener: lavender garland braid, flowers, drooping ear tips
			return FPreset(E, LyrisFrames::FrameA).Skin(4).C(TEXT("Hair.Root"), 14).C(TEXT("Eyes.IrisL"), 5).C(TEXT("Skin.Markings"), 1)
				.P(TEXT("Hair"), TEXT("GarlandCrown")).P(TEXT("HairAccessory"), TEXT("FlowerCrown")).P(TEXT("Markings"), TEXT("SilverVeins"))
				.P(TEXT("Outfit"), TEXT("GrowerSmock")).P(TEXT("Expression"), TEXT("Shy")).P(TEXT("Stance"), TEXT("Shy"))
				.P(TEXT("Voice"), TEXT("Soft1")).C(TEXT("Outfit.Primary"), 10).C(TEXT("Outfit.Secondary"), 15)
				.Pair(TEXT("Ears.Point"), 0.5f).Pair(TEXT("Ears.Droop"), 0.3f).S(TEXT("Skin.Rosiness"), 0.3f).A;
		case 3: // Pale Sail: long flax hair, rain cloak, swept-back ears
			return FPreset(E, LyrisFrames::FrameB).Skin(0).C(TEXT("Hair.Root"), 0).C(TEXT("Eyes.IrisL"), 7)
				.P(TEXT("Hair"), TEXT("FallingWater")).P(TEXT("Outfit"), TEXT("DeckhandCoat")).P(TEXT("Layer"), TEXT("RainCloak"))
				.P(TEXT("Expression"), TEXT("Bright")).P(TEXT("Voice"), TEXT("Bright2")).P(TEXT("Stance"), TEXT("SeaLegs"))
				.C(TEXT("Outfit.Primary"), 0).C(TEXT("Outfit.Layer"), 12)
				.Pair(TEXT("Ears.Point"), 0.7f).Pair(TEXT("Ears.PointAngle"), -0.3f).S(TEXT("Body.Height"), 0.2f).A;
		case 4: // Lantern Bearer: dusk-violet tail, full-moon sigil, bright glow
			return FPreset(E, LyrisFrames::FrameA).Skin(8).C(TEXT("Hair.Root"), 17).C(TEXT("Eyes.IrisL"), 15).C(TEXT("Eyes.Glow"), 3)
				.C(TEXT("Skin.Markings"), 3)
				.P(TEXT("Hair"), TEXT("SailorsTail")).P(TEXT("Markings"), TEXT("FullMoon")).P(TEXT("Outfit"), TEXT("DelverLeathers"))
				.P(TEXT("Expression"), TEXT("Determined")).P(TEXT("Voice"), TEXT("Warm2")).P(TEXT("Stance"), TEXT("Upright"))
				.C(TEXT("Outfit.Primary"), 4).C(TEXT("Outfit.Trim"), 3)
				.S(TEXT("Eyes.GlowStrength"), 0.7f).Pair(TEXT("Ears.Point"), 0.5f).S(TEXT("Body.Height"), 0.2f).A;
		case 5: // Dusk Wanderer: moonglass bob, hooded cloak, long ears
			return FPreset(E, LyrisFrames::FrameB).Skin(10).C(TEXT("Hair.Root"), 13).C(TEXT("Eyes.IrisL"), 12).C(TEXT("Skin.Markings"), 4)
				.P(TEXT("Hair"), TEXT("WaveBob")).P(TEXT("Markings"), TEXT("WaningCheeks")).P(TEXT("Outfit"), TEXT("WandererLayers"))
				.P(TEXT("Layer"), TEXT("HoodedCloak")).P(TEXT("Expression"), TEXT("Wry")).P(TEXT("Voice"), TEXT("Low1"))
				.C(TEXT("Outfit.Primary"), 16).C(TEXT("Outfit.Layer"), 14)
				.Pair(TEXT("Ears.Point"), 0.8f).Pair(TEXT("Eyes.Tilt"), 0.3f).A;
		}
	}

	FLyrisAppearance BuildDeepkinPreset(int32 I)
	{
		const FName D = LyrisPeople::Deepkin;
		switch (I)
		{
		default:
		case 0: // Tidewalker: kelp tresses, cheek scales, slit pupils
			return FPreset(D, LyrisFrames::FrameA).Skin(3).C(TEXT("Hair.Root"), 16).C(TEXT("Eyes.IrisL"), 16).C(TEXT("Skin.Markings"), 5)
				.C(TEXT("Skin.MarkingShimmer"), 0).C(TEXT("Eyes.ScleraDeepkin"), 1)
				.P(TEXT("Hair"), TEXT("KelpTresses")).P(TEXT("Markings"), TEXT("CheekScales")).P(TEXT("PupilShape"), TEXT("Slit"))
				.P(TEXT("Outfit"), TEXT("DeckhandCoat")).P(TEXT("Expression"), TEXT("Calm")).P(TEXT("Voice"), TEXT("Soft2"))
				.C(TEXT("Outfit.Primary"), 11).C(TEXT("Outfit.Secondary"), 1)
				.Pair(TEXT("Ears.FinSpread"), 0.5f).Pair(TEXT("Ears.Point"), 0.4f).A;
		case 1: // Reef Diver: short deep-sea crop, temple scales, night shine
			return FPreset(D, LyrisFrames::FrameB).Skin(1).C(TEXT("Hair.Root"), 19).C(TEXT("Eyes.IrisL"), 7).C(TEXT("Eyes.Shine"), 0)
				.C(TEXT("Skin.Markings"), 5).C(TEXT("Skin.MarkingShimmer"), 4)
				.P(TEXT("Hair"), TEXT("Sparrow")).P(TEXT("Markings"), TEXT("TempleScales")).P(TEXT("Outfit"), TEXT("WandererLayers"))
				.P(TEXT("Expression"), TEXT("Bright")).P(TEXT("Voice"), TEXT("Bright1"))
				.C(TEXT("Outfit.Primary"), 12)
				.Pair(TEXT("Ears.FinSpread"), 0.7f).S(TEXT("Eyes.ShineStrength"), 0.5f).A;
		case 2: // Hollowdeep Miner: broad, undercut, barbels, spine ridge
			return FPreset(D, LyrisFrames::FrameB).Skin(8).C(TEXT("Hair.Root"), 9).C(TEXT("Eyes.IrisL"), 15).C(TEXT("Eyes.Shine"), 3)
				.C(TEXT("Skin.Markings"), 6).C(TEXT("Eyes.ScleraDeepkin"), 3)
				.P(TEXT("Hair"), TEXT("HarborUndercut")).P(TEXT("Markings"), TEXT("SpineRidge")).P(TEXT("Scars"), TEXT("BrowNick"))
				.P(TEXT("FacialHair"), TEXT("Barbels")).P(TEXT("Outfit"), TEXT("DelverLeathers")).P(TEXT("Expression"), TEXT("Determined"))
				.P(TEXT("Voice"), TEXT("Low2")).P(TEXT("Stance"), TEXT("ArmsFolded"))
				.C(TEXT("Outfit.Primary"), 4).C(TEXT("Outfit.Trim"), 2)
				.S(TEXT("Body.ShoulderWidth"), 0.5f).S(TEXT("Body.MuscleTone"), 0.5f).S(TEXT("Eyes.ShineStrength"), 0.7f).A;
		case 3: // Kelp Singer: rose waves, gill lines, tidal irises
			return FPreset(D, LyrisFrames::FrameA).Skin(5).C(TEXT("Hair.Root"), 15).C(TEXT("Eyes.IrisL"), 6).C(TEXT("Skin.Markings"), 7)
				.C(TEXT("Skin.MarkingShimmer"), 1)
				.P(TEXT("Hair"), TEXT("RollingSwell")).P(TEXT("Markings"), TEXT("GillLines")).P(TEXT("IrisPattern"), TEXT("Tidal"))
				.P(TEXT("Outfit"), TEXT("PlainTraveller")).P(TEXT("Layer"), TEXT("Shawl")).P(TEXT("Expression"), TEXT("Dreamy"))
				.P(TEXT("Voice"), TEXT("Bright2")).C(TEXT("Outfit.Primary"), 1).C(TEXT("Outfit.Layer"), 11)
				.Pair(TEXT("Ears.FinSpread"), 0.6f).S(TEXT("Mouth.UpperLipFullness"), 0.3f).A;
		case 4: // Bay Keeper: silver curls, shoulder scales, calm and kind
			return FPreset(D, LyrisFrames::FrameB).Skin(6).C(TEXT("Hair.Root"), 11).C(TEXT("Eyes.IrisL"), 10).C(TEXT("Skin.Markings"), 7)
				.C(TEXT("Skin.MarkingShimmer"), 5)
				.P(TEXT("Hair"), TEXT("TideCurls")).P(TEXT("Markings"), TEXT("ShoulderScales")).P(TEXT("Outfit"), TEXT("TraderWaistcoat"))
				.P(TEXT("Expression"), TEXT("Calm")).P(TEXT("Voice"), TEXT("Warm1")).P(TEXT("Stance"), TEXT("HandOnHip"))
				.C(TEXT("Outfit.Primary"), 13).C(TEXT("Outfit.Trim"), 0)
				.S(TEXT("Skin.AgeLines"), 0.4f).S(TEXT("Body.Softness"), 0.3f).A;
		case 5: // Storm Pilot: ember high tail, fin edges, cuttle pupils
			return FPreset(D, LyrisFrames::FrameA).Skin(9).C(TEXT("Hair.Root"), 18).C(TEXT("Eyes.IrisL"), 17).C(TEXT("Skin.Markings"), 5)
				.C(TEXT("Skin.MarkingShimmer"), 2)
				.P(TEXT("Hair"), TEXT("GullTail")).P(TEXT("Markings"), TEXT("FinEdge")).P(TEXT("PupilShape"), TEXT("Cuttle"))
				.P(TEXT("Outfit"), TEXT("DeckhandCoat")).P(TEXT("Layer"), TEXT("RainCloak")).P(TEXT("Expression"), TEXT("Wry"))
				.P(TEXT("Voice"), TEXT("Low1")).C(TEXT("Outfit.Primary"), 7).C(TEXT("Outfit.Layer"), 13)
				.Pair(TEXT("Ears.FinSpread"), 0.8f).Pair(TEXT("Brows.Tilt"), 0.3f).A;
		}
	}

	int32 WrapPresetIndex(int32 Index)
	{
		const int32 N = ULyrisAppearanceLibrary::GetPresetCount();
		return ((Index % N) + N) % N;
	}
}

FLyrisAppearance ULyrisAppearanceLibrary::MakePreset(FName People, int32 Index)
{
	const int32 I = WrapPresetIndex(Index);
	FLyrisAppearance A;
	if (People == LyrisPeople::MoonlitElf)   { A = BuildElfPreset(I); }
	else if (People == LyrisPeople::Deepkin) { A = BuildDeepkinPreset(I); }
	else                                     { A = BuildHumanPreset(I); }
	SanitizeAppearance(nullptr, A);
	return A;
}

FText ULyrisAppearanceLibrary::GetPresetName(FName People, int32 Index)
{
	const int32 I = WrapPresetIndex(Index);
	if (People == LyrisPeople::MoonlitElf) { return FText::FromString(ElfNames[I]); }
	if (People == LyrisPeople::Deepkin)    { return FText::FromString(DeepNames[I]); }
	return FText::FromString(HumanNames[I]);
}
