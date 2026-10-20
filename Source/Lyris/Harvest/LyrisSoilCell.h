// Lyris farming: the record for one 100 cm cell of soil (design/farming.md sections 2 and 3).

#pragma once

#include "CoreMinimal.h"
#include "LyrisSoilCell.generated.h"

UENUM(BlueprintType)
enum class ELyrisSoilState : uint8
{
	/** Plain ground. Till it with a hoe. */
	Untilled,
	/** Ready for a seed. Never reverts on its own. */
	Tilled,
	/** Has a crop growing (or ripe) in it. */
	Planted
};

/**
 * One cell. Everything about growth is derived from these fields and the current UTC time;
 * nothing here changes while nobody interacts, so offline growth is free and every machine
 * computes the same stage from the same replicated values.
 *
 * Times are FDateTime ticks (UTC) in int64 so they replicate and save without conversion.
 */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisSoilCell
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Soil")
	ELyrisSoilState State = ELyrisSoilState::Untilled;

	/** Crop id (ULyrisCropRegistry). None unless Planted. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Soil")
	FName CropId;

	/** UTC ticks when the seed went in, or the last regrow. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Soil")
	int64 PlantedAtTicks = 0;

	/** Growth seconds already banked: tending bonuses, and the head start a regrowing crop keeps. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Soil")
	double BonusSeconds = 0.0;

	/** UTC ticks when the current watering bonus ends. 0 = never watered. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Soil")
	int64 WateredUntilTicks = 0;

	/** Care banked toward a better harvest. Only ever goes up until harvest. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Soil")
	int32 QualityPoints = 0;

	/** Real-world day number (days since 0001-01-01 UTC) of the last daily care. 0 = never. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Soil")
	int32 CaredDay = 0;

	/** Reserved for fertilizer (one per planting, design/farming.md section 5). Not used yet. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Soil")
	FName FertilizerId;

	bool IsPlanted() const { return State == ELyrisSoilState::Planted && !CropId.IsNone(); }

	/** Back to empty tilled soil (after a non-regrowing harvest). */
	void ClearCrop()
	{
		State = ELyrisSoilState::Tilled;
		CropId = NAME_None;
		PlantedAtTicks = 0;
		BonusSeconds = 0.0;
		WateredUntilTicks = 0;
		QualityPoints = 0;
		CaredDay = 0;
		FertilizerId = NAME_None;
	}
};

/** A read-only summary of a cell for HUD tooltips (P6) and debugging. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisCropStatus
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	ELyrisSoilState State = ELyrisSoilState::Untilled;

	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	FName CropId;

	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	FText CropName;

	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	int32 Stage = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	int32 StageCount = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	bool bRipe = false;

	/** 0..1 of the way to ripe. */
	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	float GrowthFraction = 0.f;

	/** Real seconds until ripe at the current pace. 0 if ripe, -1 if dormant. */
	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	float SecondsToRipe = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	bool bWatered = false;

	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	float WateredSecondsLeft = 0.f;

	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	bool bCaredToday = false;

	UPROPERTY(BlueprintReadOnly, Category = "Soil")
	int32 QualityPoints = 0;
};
