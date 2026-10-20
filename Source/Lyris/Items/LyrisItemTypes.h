// Lyris items: shared enums and the DataTable row that describes an item.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataTable.h"
#include "LyrisItemTypes.generated.h"

class UTexture2D;

/** What kind of thing an item is. Drives sorting, inventory tabs and what can be planted or used. */
UENUM(BlueprintType)
enum class ELyrisItemCategory : uint8
{
	Material,
	Seed,
	Tool,
	Food,
	Collectible,
	Misc
};

/** Placeholder rarity tiers. The Collecting lane owns what these mean and may replace them. */
UENUM(BlueprintType)
enum class ELyrisItemRarity : uint8
{
	Common,
	Uncommon,
	Rare,
	Mythic
};

/**
 * Quality of a harvested or crafted item (design/farming.md section 5). Every crop reaches at
 * least Normal with zero care; care only raises the odds of the higher tiers.
 */
UENUM(BlueprintType)
enum class ELyrisItemQuality : uint8
{
	Normal,
	Fine,
	Splendid,
	Radiant
};

/**
 * "Between Min and Max of this item", used for anything that hands out items:
 * gathering node yields, harvest yields, later loot and quest rewards.
 */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisItemYield
{
	GENERATED_BODY()

	/** Item id, resolved through ULyrisItemRegistry. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item")
	FName ItemId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item", meta = (ClampMin = "0"))
	int32 MinCount = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item", meta = (ClampMin = "0"))
	int32 MaxCount = 1;

	/** 0..1. Lets rare extras ("sometimes a star crystal shard") live in the same list. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item", meta = (ClampMin = "0", ClampMax = "1"))
	float Chance = 1.f;

	FLyrisItemYield() = default;
	FLyrisItemYield(FName InItemId, int32 InMin, int32 InMax, float InChance = 1.f)
		: ItemId(InItemId), MinCount(InMin), MaxCount(InMax), Chance(InChance) {}

	/** Rolls how many to give (0 if the chance roll fails). */
	int32 Roll() const
	{
		if (ItemId.IsNone() || FMath::FRand() > Chance)
		{
			return 0;
		}
		const int32 Low = FMath::Max(0, FMath::Min(MinCount, MaxCount));
		const int32 High = FMath::Max(Low, FMath::Max(MinCount, MaxCount));
		return FMath::RandRange(Low, High);
	}
};

/**
 * One item, as a DataTable row. The row name is the item id (e.g. "copper_ore").
 *
 * This exists so items can be authored without binary assets: import a CSV/JSON into a
 * DataTable with this row struct and register the table with ULyrisItemRegistry, or let an
 * editor script turn rows into ULyrisItemDefinition assets. ULyrisItemDefinition has the same
 * fields and can be created from a row with ULyrisItemDefinition::InitFromRow.
 */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisItemRow : public FTableRowBase
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item")
	FText DisplayName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item", meta = (MultiLine = "true"))
	FText Description;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item")
	TSoftObjectPtr<UTexture2D> Icon;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item", meta = (ClampMin = "1"))
	int32 MaxStack = 99;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item")
	ELyrisItemCategory Category = ELyrisItemCategory::Material;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item")
	ELyrisItemRarity Rarity = ELyrisItemRarity::Common;

	/**
	 * For tools: what kind of tool this is, e.g. "Pickaxe", "Axe", "WateringCan".
	 * Resource nodes and plots ask the inventory HasTool(ToolType). None for non-tools.
	 * (A plain FName for now; could become a GameplayTag once that module is added.)
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Item")
	FName ToolType;
};
