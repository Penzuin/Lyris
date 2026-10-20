// Lyris farming: what a crop is (design/farming.md section 4).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Engine/DataTable.h"
#include "Items/LyrisItemTypes.h"
#include "LyrisCropDefinition.generated.h"

class UStaticMesh;

/** One growth stage's look: seed, sprout, young, budding, ripe. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisCropStage
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop")
	TSoftObjectPtr<UStaticMesh> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop")
	FVector Scale = FVector::OneVector;

	/**
	 * Where this stage starts, as a fraction (0..1) of the time to ripe. Leave all stages at -1
	 * to space them evenly. The last stage is always "ripe" and starts at 1.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop", meta = (ClampMin = "-1", ClampMax = "1"))
	float StartFraction = -1.f;
};

/**
 * Everything about a crop. Lives inside ULyrisCropDefinition, and is also a DataTable row so
 * crops can be authored without binary assets (row name = crop id).
 */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisCropData : public FTableRowBase
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop")
	FText DisplayName;

	/** Seed item (T11 id) that plants this crop, e.g. "seed_mistberry". */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop")
	FName SeedItemId;

	/** Stage looks in order; the last one is ripe. Five is typical. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop")
	TArray<FLyrisCropStage> Stages;

	/** Real-world hours from planting to ripe at the base rate. Quick ~3, standard 6-12, slow 24-72. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop", meta = (ClampMin = "0.01"))
	float BaseHoursToRipe = 6.f;

	/**
	 * Seasons this crop grows in ("Spring", "Summer", "Autumn", "Winter"). Empty = any season.
	 * Not used until the World lane ships the calendar (P3); every crop is in season until then.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop")
	TArray<FName> Seasons;

	/** After harvest, stays planted and fruits again. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop")
	bool bRegrows = false;

	/** Real-world hours from a harvest to ripe again, at the base rate. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop", meta = (EditCondition = "bRegrows", ClampMin = "0.01"))
	float RegrowHours = 2.f;

	/** What a harvest gives. Quality is rolled separately from care. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop")
	FLyrisItemYield Yield;

	/** Chance that daily care also finds a bonus seed at harvest. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop", meta = (ClampMin = "0", ClampMax = "1"))
	float BonusSeedChance = 0.1f;

	/** Chance a 3x3 of this ripe crop merges into a giant crop. Stored for later; not used yet. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop", meta = (ClampMin = "0", ClampMax = "1"))
	float GiantChance = 0.f;

	/** Cells covered. Only 1x1 is supported for now (trellis crops later). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Crop")
	FIntPoint Footprint = FIntPoint(1, 1);
};

/**
 * A crop as a data asset: Content Browser > Miscellaneous > Data Asset > LyrisCropDefinition,
 * saved under /Game/Lyris/Harvest/Crops so ULyrisCropRegistry finds it. Cells store the CropId,
 * so saves and replication never hold a pointer.
 */
UCLASS(BlueprintType)
class LYRIS_API ULyrisCropDefinition : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	static const FPrimaryAssetType PrimaryAssetType;

	/** Stable id, e.g. "mistberry". Never rename once shipped. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crop")
	FName CropId;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crop", meta = (ShowOnlyInnerProperties))
	FLyrisCropData Data;

	UFUNCTION(BlueprintPure, Category = "Lyris|Farming")
	int32 GetStageCount() const { return FMath::Max(1, Data.Stages.Num()); }

	UFUNCTION(BlueprintPure, Category = "Lyris|Farming")
	int32 GetRipeStage() const { return GetStageCount() - 1; }

	/** Growth seconds needed to be ripe. */
	double GetRipeSeconds() const { return FMath::Max(1.0, static_cast<double>(Data.BaseHoursToRipe) * 3600.0); }

	/** Growth seconds at which a stage begins. */
	double GetStageStartSeconds(int32 StageIndex) const;

	/** Which stage a given amount of growth has reached. */
	int32 GetStageForGrowth(double GrowthSeconds) const;

	static ULyrisCropDefinition* CreateFromData(UObject* Outer, FName InCropId, const FLyrisCropData& InData);

	virtual FPrimaryAssetId GetPrimaryAssetId() const override;
};
