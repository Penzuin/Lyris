// Lyris items: a small built-in set of starter items, defined in code so the prototype needs no assets.

#pragma once

#include "CoreMinimal.h"
#include "LyrisItemTypes.h"

/**
 * Starter items registered by ULyrisItemRegistry before any content is loaded. A DataTable or
 * data asset under /Game/Lyris/Items with the same id overrides the entry here, so these are
 * placeholders that real content can replace one by one.
 *
 * Tool types used by the Harvest lane: "Pickaxe", "Axe", "WateringCan", "Hoe". Foraging needs no tool.
 */
namespace LyrisItemCatalog
{
	/** Tool type names, so code and data agree on spelling. */
	extern LYRIS_API const FName Tool_Pickaxe;
	extern LYRIS_API const FName Tool_Axe;
	extern LYRIS_API const FName Tool_WateringCan;
	extern LYRIS_API const FName Tool_Hoe;

	/** id -> row for every built-in item. */
	LYRIS_API const TMap<FName, FLyrisItemRow>& GetBuiltInItems();
}
