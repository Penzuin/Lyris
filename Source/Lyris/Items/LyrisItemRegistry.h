// Lyris items: looks up item definitions by id, whether they come from assets, DataTables or code.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "LyrisItemTypes.h"
#include "LyrisItemRegistry.generated.h"

class UDataTable;
class ULyrisItemDefinition;

/**
 * Every item definition in the game, by ItemId.
 *
 * Filled at startup, later sources overriding earlier ones with the same id:
 *   1. The built-in starter items in LyrisItemCatalog.cpp (so the prototype works with no assets).
 *   2. Any DataTable under /Game/Lyris/Items whose row struct is FLyrisItemRow (row name = id).
 *   3. Any ULyrisItemDefinition data asset under /Game/Lyris/Items.
 * More can be added at runtime with RegisterDefinition / RegisterDataTable.
 *
 * Resource nodes, farm plots and seeds refer to items by FName id and resolve them here, so data
 * never needs a hard reference to a binary asset.
 */
UCLASS()
class LYRIS_API ULyrisItemRegistry : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	/** Folder scanned for item assets and DataTables at startup. */
	static const TCHAR* ItemContentPath;

	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	/** Convenience getter from anything with a world. May return null very early or in editor-only contexts. */
	static ULyrisItemRegistry* Get(const UObject* WorldContextObject);

	/** Static lookup for code that only has a world context. */
	static ULyrisItemDefinition* FindItem(const UObject* WorldContextObject, FName ItemId);

	UFUNCTION(BlueprintPure, Category = "Lyris|Items")
	ULyrisItemDefinition* FindDefinition(FName ItemId) const;

	UFUNCTION(BlueprintCallable, Category = "Lyris|Items")
	void RegisterDefinition(ULyrisItemDefinition* Definition);

	/** Adds every row of a DataTable whose row struct is FLyrisItemRow. Returns how many were added. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Items")
	int32 RegisterDataTable(UDataTable* Table);

	/** Adds or replaces one item from row data (also how the built-in catalog is registered). */
	ULyrisItemDefinition* RegisterRow(FName ItemId, const FLyrisItemRow& Row);

	UFUNCTION(BlueprintPure, Category = "Lyris|Items")
	TArray<ULyrisItemDefinition*> GetAllDefinitions() const;

private:
	void LoadContentFolder();

	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<ULyrisItemDefinition>> Definitions;
};
