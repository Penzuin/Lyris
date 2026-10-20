// Lyris farming: what a crop is (design/farming.md section 4).

#include "LyrisCropDefinition.h"

#include "Engine/StaticMesh.h"
#include "UObject/Package.h"

const FPrimaryAssetType ULyrisCropDefinition::PrimaryAssetType(TEXT("LyrisCrop"));

double ULyrisCropDefinition::GetStageStartSeconds(int32 StageIndex) const
{
	const int32 Count = GetStageCount();
	if (StageIndex <= 0)
	{
		return 0.0;
	}
	if (StageIndex >= Count - 1)
	{
		return GetRipeSeconds();
	}

	double Fraction = static_cast<double>(StageIndex) / static_cast<double>(Count - 1);
	if (Data.Stages.IsValidIndex(StageIndex) && Data.Stages[StageIndex].StartFraction >= 0.f)
	{
		Fraction = FMath::Clamp(static_cast<double>(Data.Stages[StageIndex].StartFraction), 0.0, 1.0);
	}
	return Fraction * GetRipeSeconds();
}

int32 ULyrisCropDefinition::GetStageForGrowth(double GrowthSeconds) const
{
	const int32 Ripe = GetRipeStage();
	if (GrowthSeconds >= GetRipeSeconds())
	{
		return Ripe;
	}
	for (int32 Stage = Ripe - 1; Stage > 0; --Stage)
	{
		if (GrowthSeconds >= GetStageStartSeconds(Stage))
		{
			return Stage;
		}
	}
	return 0;
}

ULyrisCropDefinition* ULyrisCropDefinition::CreateFromData(UObject* Outer, FName InCropId, const FLyrisCropData& InData)
{
	ULyrisCropDefinition* Definition = NewObject<ULyrisCropDefinition>(Outer ? Outer : GetTransientPackage(), NAME_None, RF_Transient);
	Definition->CropId = InCropId;
	Definition->Data = InData;
	if (Definition->Data.DisplayName.IsEmpty())
	{
		Definition->Data.DisplayName = FText::FromName(InCropId);
	}
	return Definition;
}

FPrimaryAssetId ULyrisCropDefinition::GetPrimaryAssetId() const
{
	return FPrimaryAssetId(PrimaryAssetType, CropId.IsNone() ? GetFName() : CropId);
}
