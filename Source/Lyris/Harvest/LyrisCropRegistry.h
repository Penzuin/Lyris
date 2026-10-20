// Lyris farming: looks up crops by id or by the seed that plants them.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "LyrisCropDefinition.h"
#include "LyrisCropRegistry.generated.h"

class UDataTable;

/**
 * Every crop in the game, by CropId and by SeedItemId.
 *
 * Filled at startup, later sources overriding earlier ones with the same id:
 *   1. Built-in starter crops (mistberry, moonbell, harbor_turnip) so the prototype needs no assets.
 *   2. DataTables of FLyrisCropData under /Game/Lyris/Harvest/Crops (row name = crop id).
 *   3. ULyrisCropDefinition data assets under /Game/Lyris/Harvest/Crops.
 *
 * Cultivation lane: new varieties made by combining plants can be registered at runtime with
 * RegisterCrop; cells only store the id, so a cultivated crop behaves like any other.
 */
UCLASS()
class LYRIS_API ULyrisCropRegistry : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	static const TCHAR* CropContentPath;

	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	static ULyrisCropRegistry* Get(const UObject* WorldContextObject);

	UFUNCTION(BlueprintPure, Category = "Lyris|Farming")
	ULyrisCropDefinition* FindCrop(FName CropId) const;

	/** The crop a seed item plants, or null if the item isn't a known seed. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Farming")
	ULyrisCropDefinition* FindCropForSeed(FName SeedItemId) const;

	UFUNCTION(BlueprintCallable, Category = "Lyris|Farming")
	void RegisterCrop(ULyrisCropDefinition* Crop);

	UFUNCTION(BlueprintCallable, Category = "Lyris|Farming")
	int32 RegisterDataTable(UDataTable* Table);

	ULyrisCropDefinition* RegisterData(FName CropId, const FLyrisCropData& Data);

private:
	void RegisterBuiltIns();
	void LoadContentFolder();

	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<ULyrisCropDefinition>> Crops;

	/** Seed item id -> crop id. */
	TMap<FName, FName> SeedToCrop;
};
