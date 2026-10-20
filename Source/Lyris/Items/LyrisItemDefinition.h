// Lyris items: the definition of one kind of item (not an instance in a bag).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "LyrisItemTypes.h"
#include "LyrisItemDefinition.generated.h"

class UTexture2D;

/**
 * Describes one kind of item: copper ore, a moonbell seed, a pickaxe.
 *
 * Make one in the editor with Content Browser > Miscellaneous > Data Asset > LyrisItemDefinition,
 * or define items as FLyrisItemRow rows in a DataTable. Either way, ULyrisItemRegistry looks
 * them up by ItemId at runtime, which is what resource nodes and farm plots reference.
 */
UCLASS(BlueprintType)
class LYRIS_API ULyrisItemDefinition : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	/** Primary asset type, for the Asset Manager. */
	static const FPrimaryAssetType PrimaryAssetType;

	/** Stable id used in saves, data and the registry, e.g. "copper_ore". Never rename once shipped. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item")
	FName ItemId;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item")
	FText DisplayName;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item", meta = (MultiLine = "true"))
	FText Description;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item")
	TSoftObjectPtr<UTexture2D> Icon;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item", meta = (ClampMin = "1"))
	int32 MaxStack = 99;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item")
	ELyrisItemCategory Category = ELyrisItemCategory::Material;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item")
	ELyrisItemRarity Rarity = ELyrisItemRarity::Common;

	/** For tools, e.g. "Pickaxe". See FLyrisItemRow::ToolType. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item")
	FName ToolType;

	UFUNCTION(BlueprintPure, Category = "Lyris|Items")
	bool IsTool() const { return Category == ELyrisItemCategory::Tool && !ToolType.IsNone(); }

	/** Copies a DataTable row into this definition. */
	void InitFromRow(FName InItemId, const FLyrisItemRow& Row);

	/** Makes a transient definition from a row (used by the registry for DataTable items). */
	static ULyrisItemDefinition* CreateFromRow(UObject* Outer, FName InItemId, const FLyrisItemRow& Row);

	virtual FPrimaryAssetId GetPrimaryAssetId() const override;
};
