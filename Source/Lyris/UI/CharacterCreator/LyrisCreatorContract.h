// Lyris character creator: the single place where the UI touches the Player lane's appearance API.
//
// The appearance types, catalog, library, save game and component are written by the Player lane
// (T23, Source/Lyris/Player/Appearance/) against the shared creator contract. The UI was written
// at the same time, so every name the UI relies on beyond the contract is kept in this file. The lead
// checked them against T23 (PR #26). If the Player lane renames something later, fix it here and the
// rest of the creator follows.

#pragma once

#include "CoreMinimal.h"
#include "Math/RandomStream.h"

#include "Player/Appearance/LyrisAppearanceTypes.h"
#include "Player/Appearance/LyrisAppearanceCatalog.h"
#include "Player/Appearance/LyrisAppearanceComponent.h"
#include "Player/Appearance/LyrisAppearanceLibrary.h"
#include "Player/Appearance/LyrisCharacterSaveGame.h"

namespace LyrisCreator
{
	/** Save slot and user index, owned by the save game class (T23). */
	inline const TCHAR* SaveSlotName() { return ULyrisCharacterSaveGame::SlotName; }
	inline int32 SaveUserIndex() { return ULyrisCharacterSaveGame::UserIndex; }

	/** ASSUMPTION: the save game keeps its FLyrisCharacterProfile in a member called Profile. */
	inline FLyrisCharacterProfile& SaveProfile(ULyrisCharacterSaveGame& Save) { return Save.Profile; }

	/** The catalog the component uses (its Catalog property, else the default catalog).
	 *  T23 renames GetDefault() to GetDefaultCatalog() and keeps a deprecated forwarder. */
	inline ULyrisAppearanceCatalog* CatalogFor(const ULyrisAppearanceComponent* Component)
	{
		// Works whether Catalog is a TObjectPtr or a raw pointer.
		if (Component)
		{
			if (ULyrisAppearanceCatalog* Assigned = Component->Catalog)
			{
				return Assigned;
			}
		}
		return ULyrisAppearanceCatalog::GetDefaultCatalog();
	}

	/** The part a slot shows: the look's choice, else the slot's DefaultPart (T23). */
	inline FName EffectivePart(const ULyrisAppearanceCatalog* Catalog, const FLyrisAppearance& Look, FName Slot)
	{
		return ULyrisAppearanceLibrary::GetEffectivePart(Catalog, Look, Slot);
	}

	/** Named presets per People (T23, spec 9.8). */
	inline int32 PresetCount() { return ULyrisAppearanceLibrary::GetPresetCount(); }
	inline FLyrisAppearance MakePreset(FName People, int32 Index) { return ULyrisAppearanceLibrary::MakePreset(People, Index); }
	inline FText PresetName(FName People, int32 Index) { return ULyrisAppearanceLibrary::GetPresetName(People, Index); }

	/** Section a colour channel is shown in, from the catalog (None when it has no entry). */
	inline FName ChannelSection(const ULyrisAppearanceCatalog& Catalog, FName Channel)
	{
		const FName* Found = Catalog.ChannelSections.Find(Channel);
		return Found ? *Found : NAME_None;
	}

	// The contract does not say whether GetSlidersIn / GetPartsForSlot return defs by value or by
	// pointer. These overloads let the creator accept either and copy the def into its own storage.
	inline const FLyrisSliderDef* AsDef(const FLyrisSliderDef& Def) { return &Def; }
	inline const FLyrisSliderDef* AsDef(const FLyrisSliderDef* Def) { return Def; }
	inline const FLyrisPartDef* AsDef(const FLyrisPartDef& Def) { return &Def; }
	inline const FLyrisPartDef* AsDef(const FLyrisPartDef* Def) { return Def; }

	/** Sliders for one section, copied out of the catalog. */
	inline TArray<FLyrisSliderDef> SlidersIn(ULyrisAppearanceCatalog& Catalog, FName Category, FName Section, FName People)
	{
		TArray<FLyrisSliderDef> Out;
		for (const auto& Item : Catalog.GetSlidersIn(Category, Section, People))
		{
			if (const FLyrisSliderDef* Def = AsDef(Item))
			{
				Out.Add(*Def);
			}
		}
		return Out;
	}

	/** Parts for one slot, copied out of the catalog. */
	inline TArray<FLyrisPartDef> PartsForSlot(ULyrisAppearanceCatalog& Catalog, FName Slot, FName People)
	{
		TArray<FLyrisPartDef> Out;
		for (const auto& Item : Catalog.GetPartsForSlot(Slot, People))
		{
			if (const FLyrisPartDef* Def = AsDef(Item))
			{
				Out.Add(*Def);
			}
		}
		return Out;
	}

	/** Categories and sections, copied into plain name arrays. */
	inline TArray<FName> Categories(ULyrisAppearanceCatalog& Catalog)
	{
		TArray<FName> Out;
		for (const auto& Name : Catalog.GetCategories())
		{
			Out.Add(FName(Name));
		}
		return Out;
	}

	inline TArray<FName> Sections(ULyrisAppearanceCatalog& Catalog, FName Category)
	{
		TArray<FName> Out;
		for (const auto& Name : Catalog.GetSections(Category))
		{
			Out.Add(FName(Name));
		}
		return Out;
	}

	/** ASSUMPTION: RandomizeAppearance takes the catalog as a pointer (the contract writes "Catalog"). */
	inline void Randomize(ULyrisAppearanceCatalog* Catalog, FLyrisAppearance& InOut, FRandomStream& Stream,
		const TSet<FName>& LockedCategories, float Wildness)
	{
		ULyrisAppearanceLibrary::RandomizeAppearance(Catalog, InOut, Stream, LockedCategories, Wildness);
	}

	/** True when an option's People list allows this People (empty list = everyone). */
	inline bool AllowsPeople(const TArray<FName>& PeopleList, FName People)
	{
		return PeopleList.Num() == 0 || PeopleList.Contains(People);
	}
}
