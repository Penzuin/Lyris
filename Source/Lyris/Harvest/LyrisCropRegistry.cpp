// Lyris farming: looks up crops by id or by the seed that plants them.

#include "LyrisCropRegistry.h"

#include "Lyris.h"
#include "Engine/DataTable.h"
#include "Engine/GameInstance.h"
#include "Engine/ObjectLibrary.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"

#define LOCTEXT_NAMESPACE "LyrisCropRegistry"

const TCHAR* ULyrisCropRegistry::CropContentPath = TEXT("/Game/Lyris/Harvest/Crops");

namespace LyrisCropRegistry
{
	/** Placeholder stage looks from engine shapes until real crop meshes exist: a growing cone, then a sphere for ripe. */
	static TArray<FLyrisCropStage> PlaceholderStages(int32 Count)
	{
		const FSoftObjectPath Cone(TEXT("/Engine/BasicShapes/Cone.Cone"));
		const FSoftObjectPath Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
		TArray<FLyrisCropStage> Stages;
		for (int32 Index = 0; Index < Count; ++Index)
		{
			FLyrisCropStage Stage;
			const bool bRipe = Index == Count - 1;
			const float T = Count > 1 ? static_cast<float>(Index) / static_cast<float>(Count - 1) : 1.f;
			Stage.Mesh = TSoftObjectPtr<UStaticMesh>(bRipe ? Sphere : Cone);
			Stage.Scale = bRipe ? FVector(0.45f) : FVector(0.12f + 0.25f * T, 0.12f + 0.25f * T, 0.1f + 0.5f * T);
			Stages.Add(Stage);
		}
		return Stages;
	}
}

void ULyrisCropRegistry::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	RegisterBuiltIns();
	LoadContentFolder();
	UE_LOG(LogLyris, Log, TEXT("Crop registry: %d crops"), Crops.Num());
}

void ULyrisCropRegistry::RegisterBuiltIns()
{
	// Starting values from design/farming.md section 4; tune freely in playtests.
	{
		FLyrisCropData Data;
		Data.DisplayName = LOCTEXT("Mistberry", "Mistberry");
		Data.SeedItemId = TEXT("seed_mistberry");
		Data.Stages = LyrisCropRegistry::PlaceholderStages(5);
		Data.BaseHoursToRipe = 6.f;
		Data.Seasons = { TEXT("Spring"), TEXT("Summer") };
		Data.bRegrows = true;
		Data.RegrowHours = 2.f;
		Data.Yield = FLyrisItemYield(TEXT("mistberry"), 2, 4);
		Data.GiantChance = 0.02f;
		RegisterData(TEXT("mistberry"), Data);
	}
	{
		FLyrisCropData Data;
		Data.DisplayName = LOCTEXT("Moonbell", "Moonbell");
		Data.SeedItemId = TEXT("seed_moonbell");
		Data.Stages = LyrisCropRegistry::PlaceholderStages(4);
		Data.BaseHoursToRipe = 12.f;
		Data.Yield = FLyrisItemYield(TEXT("moonbell"), 1, 1);
		Data.BonusSeedChance = 0.2f;
		RegisterData(TEXT("moonbell"), Data);
	}
	{
		FLyrisCropData Data;
		Data.DisplayName = LOCTEXT("HarborTurnip", "Harbor Turnip");
		Data.SeedItemId = TEXT("seed_harbor_turnip");
		Data.Stages = LyrisCropRegistry::PlaceholderStages(4);
		Data.BaseHoursToRipe = 3.f;
		Data.Yield = FLyrisItemYield(TEXT("harbor_turnip"), 1, 2);
		RegisterData(TEXT("harbor_turnip"), Data);
	}
}

ULyrisCropRegistry* ULyrisCropRegistry::Get(const UObject* WorldContextObject)
{
	const UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
	return GameInstance ? GameInstance->GetSubsystem<ULyrisCropRegistry>() : nullptr;
}

ULyrisCropDefinition* ULyrisCropRegistry::FindCrop(FName CropId) const
{
	const TObjectPtr<ULyrisCropDefinition>* Found = Crops.Find(CropId);
	return Found ? Found->Get() : nullptr;
}

ULyrisCropDefinition* ULyrisCropRegistry::FindCropForSeed(FName SeedItemId) const
{
	const FName* CropId = SeedToCrop.Find(SeedItemId);
	return CropId ? FindCrop(*CropId) : nullptr;
}

void ULyrisCropRegistry::RegisterCrop(ULyrisCropDefinition* Crop)
{
	if (!Crop || Crop->CropId.IsNone())
	{
		UE_LOG(LogLyris, Warning, TEXT("Crop %s has no CropId; skipped"), *GetNameSafe(Crop));
		return;
	}
	Crops.Add(Crop->CropId, Crop);
	if (!Crop->Data.SeedItemId.IsNone())
	{
		SeedToCrop.Add(Crop->Data.SeedItemId, Crop->CropId);
	}
}

ULyrisCropDefinition* ULyrisCropRegistry::RegisterData(FName CropId, const FLyrisCropData& Data)
{
	if (CropId.IsNone())
	{
		return nullptr;
	}
	ULyrisCropDefinition* Crop = ULyrisCropDefinition::CreateFromData(this, CropId, Data);
	RegisterCrop(Crop);
	return Crop;
}

int32 ULyrisCropRegistry::RegisterDataTable(UDataTable* Table)
{
	if (!Table || Table->GetRowStruct() != FLyrisCropData::StaticStruct())
	{
		return 0;
	}
	int32 Added = 0;
	for (const TPair<FName, uint8*>& Pair : Table->GetRowMap())
	{
		if (const FLyrisCropData* Row = reinterpret_cast<const FLyrisCropData*>(Pair.Value))
		{
			RegisterData(Pair.Key, *Row);
			++Added;
		}
	}
	return Added;
}

void ULyrisCropRegistry::LoadContentFolder()
{
	UObjectLibrary* TableLibrary = UObjectLibrary::CreateLibrary(UDataTable::StaticClass(), false, GIsEditor);
	TableLibrary->LoadAssetDataFromPath(CropContentPath);
	TableLibrary->LoadAssetsFromAssetData();
	TArray<UDataTable*> Tables;
	TableLibrary->GetObjects<UDataTable>(Tables);
	for (UDataTable* Table : Tables)
	{
		RegisterDataTable(Table);
	}

	UObjectLibrary* CropLibrary = UObjectLibrary::CreateLibrary(ULyrisCropDefinition::StaticClass(), false, GIsEditor);
	CropLibrary->LoadAssetDataFromPath(CropContentPath);
	CropLibrary->LoadAssetsFromAssetData();
	TArray<ULyrisCropDefinition*> Assets;
	CropLibrary->GetObjects<ULyrisCropDefinition>(Assets);
	for (ULyrisCropDefinition* Asset : Assets)
	{
		RegisterCrop(Asset);
	}
}

#undef LOCTEXT_NAMESPACE
