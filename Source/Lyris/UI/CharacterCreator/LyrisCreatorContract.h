// Lyris character creator: the single place where the UI touches the Player lane's appearance API.
//
// The appearance types, catalog, library, save game and component are written by the Player lane
// (T23, Source/Lyris/Player/Appearance/) against the shared creator contract. The UI was written
// at the same time without seeing that code, so every assumption about names that the contract
// does not spell out exactly (header paths of the library and save game, the save game's member
// name, how lookups return their results) is kept in this file. If T23 landed with a different
// name, fix it here and the rest of the creator follows.

#pragma once

#include "CoreMinimal.h"
#include "Math/RandomStream.h"

#include "Player/Appearance/LyrisAppearanceTypes.h"
#include "Player/Appearance/LyrisAppearanceCatalog.h"
#include "Player/Appearance/LyrisAppearanceComponent.h"
// ASSUMPTION: the contract names these classes but not their headers.
#include "Player/Appearance/LyrisAppearanceLibrary.h"
#include "Player/Appearance/LyrisCharacterSaveGame.h"

namespace LyrisCreator
{
	/** Save slot from the contract. */
	inline const TCHAR* SaveSlotName() { return TEXT("LyrisCharacter_0"); }
	inline int32 SaveUserIndex() { return 0; }

	/** ASSUMPTION: the save game keeps its FLyrisCharacterProfile in a member called Profile. */
	inline FLyrisCharacterProfile& SaveProfile(ULyrisCharacterSaveGame& Save) { return Save.Profile; }

	/** The catalog the component uses (contract: Catalog property, falls back to GetDefault()). */
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
		return ULyrisAppearanceCatalog::GetDefault();
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
