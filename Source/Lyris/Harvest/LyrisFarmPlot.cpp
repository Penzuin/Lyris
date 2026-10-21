// Lyris farming: a patch of ground split into 100 cm soil cells (design/farming.md).

#include "LyrisFarmPlot.h"

#include "LyrisCropDefinition.h"
#include "LyrisCropRegistry.h"
#include "Interaction/LyrisInteractionComponent.h"
#include "Items/LyrisItemDefinition.h"
#include "Items/LyrisItemRegistry.h"
#include "Components/BoxComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInterface.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"
#include "UObject/ConstructorHelpers.h"

#define LOCTEXT_NAMESPACE "LyrisFarmPlot"

namespace LyrisFarmPlot
{
	static FText FormatDuration(double Seconds)
	{
		const int32 TotalMinutes = FMath::Max(1, FMath::CeilToInt(Seconds / 60.0));
		const int32 Hours = TotalMinutes / 60;
		const int32 Minutes = TotalMinutes % 60;
		if (Hours >= 48)
		{
			return FText::Format(LOCTEXT("Days", "{0}d {1}h"), Hours / 24, Hours % 24);
		}
		if (Hours > 0)
		{
			return FText::Format(LOCTEXT("HoursMinutes", "{0}h {1}m"), Hours, Minutes);
		}
		return FText::Format(LOCTEXT("Minutes", "{0}m"), Minutes);
	}

	/** Seconds of overlap between [A0, A1] and [B0, B1]. */
	static double Overlap(int64 A0, int64 A1, int64 B0, int64 B1)
	{
		const int64 Start = FMath::Max(A0, B0);
		const int64 End = FMath::Min(A1, B1);
		return End > Start ? FTimespan(End - Start).GetTotalSeconds() : 0.0;
	}
}

ALyrisFarmPlot::ALyrisFarmPlot()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	InteractVolume = CreateDefaultSubobject<UBoxComponent>(TEXT("InteractVolume"));
	InteractVolume->SetupAttachment(Root);
	InteractVolume->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	InteractVolume->SetCollisionObjectType(ECC_WorldDynamic);
	InteractVolume->SetCollisionResponseToAllChannels(ECR_Ignore);
	InteractVolume->SetCollisionResponseToChannel(ECC_Pawn, ECR_Overlap);
	InteractVolume->SetGenerateOverlapEvents(false);
	InteractVolume->SetCanEverAffectNavigation(false);

	SoilInstances = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("SoilInstances"));
	SoilInstances->SetupAttachment(Root);
	SoilInstances->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SoilInstances->SetCanEverAffectNavigation(false);

	WateredSoilInstances = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("WateredSoilInstances"));
	WateredSoilInstances->SetupAttachment(Root);
	WateredSoilInstances->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	WateredSoilInstances->SetCanEverAffectNavigation(false);

	Highlight = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Highlight"));
	Highlight->SetupAttachment(Root);
	Highlight->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Highlight->SetCanEverAffectNavigation(false);
	Highlight->SetHiddenInGame(true);
	Highlight->SetVisibility(false);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> PlaneFinder(TEXT("/Engine/BasicShapes/Plane.Plane"));
	if (PlaneFinder.Succeeded())
	{
		Highlight->SetStaticMesh(PlaneFinder.Object);
	}

	TilledMesh = TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(TEXT("/Engine/BasicShapes/Cube.Cube")));
}

// ---------------------------------------------------------------------------------------------
// Lifecycle

void ALyrisFarmPlot::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);

	EnsureCells();

	const FVector Extent(GridSize.X * CellSize * 0.5f, GridSize.Y * CellSize * 0.5f, 100.f);
	InteractVolume->SetBoxExtent(Extent);
	InteractVolume->SetRelativeLocation(FVector(0.f, 0.f, Extent.Z * 0.5f));

	TraceCellHeights();
	RebuildVisuals();
}

void ALyrisFarmPlot::BeginPlay()
{
	Super::BeginPlay();

	EnsureCells();
	TraceCellHeights();
	RebuildVisuals();

	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().SetTimer(VisualTimer, this, &ALyrisFarmPlot::CheckStagesChanged, VisualRefreshSeconds, true);
	}
}

void ALyrisFarmPlot::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(VisualTimer);
	}
	Super::EndPlay(EndPlayReason);
}

void ALyrisFarmPlot::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ALyrisFarmPlot, Cells);
}

void ALyrisFarmPlot::EnsureCells()
{
	GridSize.X = FMath::Clamp(GridSize.X, 1, 32);
	GridSize.Y = FMath::Clamp(GridSize.Y, 1, 32);
	const int32 Count = GetCellCount();
	if (Cells.Num() != Count)
	{
		const int32 OldCount = Cells.Num();
		Cells.SetNum(Count);
		if (bStartTilled)
		{
			for (int32 Index = OldCount; Index < Count; ++Index)
			{
				Cells[Index].State = ELyrisSoilState::Tilled;
			}
		}
	}
	if (bStartTilled)
	{
		for (FLyrisSoilCell& Cell : Cells)
		{
			if (Cell.State == ELyrisSoilState::Untilled)
			{
				Cell.State = ELyrisSoilState::Tilled;
			}
		}
	}
}

void ALyrisFarmPlot::TraceCellHeights()
{
	const int32 Count = GetCellCount();
	CellGroundZ.Init(0.f, Count);

	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	FCollisionQueryParams Params(SCENE_QUERY_STAT(LyrisFarmGround), false, this);
	const FCollisionObjectQueryParams Objects(ECC_WorldStatic);
	const FTransform& ActorTransform = GetActorTransform();

	for (int32 Index = 0; Index < Count; ++Index)
	{
		const FVector Local = GetCellLocalLocation(Index);
		const FVector WorldTop = ActorTransform.TransformPosition(FVector(Local.X, Local.Y, 300.f));
		const FVector WorldBottom = ActorTransform.TransformPosition(FVector(Local.X, Local.Y, -600.f));
		FHitResult Hit;
		if (World->LineTraceSingleByObjectType(Hit, WorldTop, WorldBottom, Objects, Params))
		{
			CellGroundZ[Index] = ActorTransform.InverseTransformPosition(Hit.ImpactPoint).Z;
		}
	}
}

// ---------------------------------------------------------------------------------------------
// Grid maths

int32 ALyrisFarmPlot::CoordToIndex(int32 X, int32 Y) const
{
	if (X < 0 || Y < 0 || X >= GridSize.X || Y >= GridSize.Y)
	{
		return INDEX_NONE;
	}
	return Y * GridSize.X + X;
}

FVector ALyrisFarmPlot::GetCellLocalLocation(int32 CellIndex) const
{
	const FIntPoint Coord = IndexToCoord(CellIndex);
	const float X = (Coord.X + 0.5f) * CellSize - GridSize.X * CellSize * 0.5f;
	const float Y = (Coord.Y + 0.5f) * CellSize - GridSize.Y * CellSize * 0.5f;
	const float Z = CellGroundZ.IsValidIndex(CellIndex) ? CellGroundZ[CellIndex] : 0.f;
	return FVector(X, Y, Z);
}

FVector ALyrisFarmPlot::GetCellWorldLocation(int32 CellIndex) const
{
	return GetActorTransform().TransformPosition(GetCellLocalLocation(CellIndex));
}

int32 ALyrisFarmPlot::GetCellAtLocation(const FVector& WorldLocation) const
{
	const FVector Local = GetActorTransform().InverseTransformPosition(WorldLocation);
	const int32 X = FMath::FloorToInt((Local.X + GridSize.X * CellSize * 0.5f) / CellSize);
	const int32 Y = FMath::FloorToInt((Local.Y + GridSize.Y * CellSize * 0.5f) / CellSize);
	return CoordToIndex(X, Y);
}

int32 ALyrisFarmPlot::GetCellForActor(const AActor* InteractingActor) const
{
	if (!InteractingActor)
	{
		return INDEX_NONE;
	}
	if (const ULyrisInteractionComponent* Interaction = InteractingActor->FindComponentByClass<ULyrisInteractionComponent>())
	{
		const int32 Aimed = GetCellAtLocation(Interaction->GetAimLocation());
		if (Aimed != INDEX_NONE)
		{
			return Aimed;
		}
	}
	// No aim, or aiming just off the edge: the cell ahead, else the cell underfoot.
	const int32 Ahead = GetCellAtLocation(InteractingActor->GetActorLocation() + InteractingActor->GetActorForwardVector() * CellSize);
	return Ahead != INDEX_NONE ? Ahead : GetCellAtLocation(InteractingActor->GetActorLocation());
}

TArray<int32> ALyrisFarmPlot::GetCellsInArea(int32 CenterIndex, int32 Radius) const
{
	TArray<int32> Result;
	if (!IsValidCell(CenterIndex))
	{
		return Result;
	}
	const FIntPoint Center = IndexToCoord(CenterIndex);
	for (int32 DY = -Radius; DY <= Radius; ++DY)
	{
		for (int32 DX = -Radius; DX <= Radius; ++DX)
		{
			const int32 Index = CoordToIndex(Center.X + DX, Center.Y + DY);
			if (Index != INDEX_NONE)
			{
				Result.Add(Index);
			}
		}
	}
	return Result;
}

TArray<int32> ALyrisFarmPlot::GetNeighbourCells(int32 CellIndex) const
{
	TArray<int32> Result = GetCellsInArea(CellIndex, 1);
	Result.Remove(CellIndex);
	return Result;
}

FLyrisSoilCell ALyrisFarmPlot::GetCell(int32 CellIndex) const
{
	return IsValidCell(CellIndex) ? Cells[CellIndex] : FLyrisSoilCell();
}

// ---------------------------------------------------------------------------------------------
// Growth (design/farming.md section 3)

ULyrisCropDefinition* ALyrisFarmPlot::FindCrop(FName CropId) const
{
	const ULyrisCropRegistry* Registry = ULyrisCropRegistry::Get(this);
	return Registry ? Registry->FindCrop(CropId) : nullptr;
}

int32 ALyrisFarmPlot::GetUtcDayNumber(const FDateTime& NowUtc)
{
	return static_cast<int32>(NowUtc.GetTicks() / ETimespan::TicksPerDay);
}

double ALyrisFarmPlot::GetGrowthSeconds(int32 CellIndex, const FDateTime& NowUtc) const
{
	if (!IsValidCell(CellIndex))
	{
		return 0.0;
	}
	const FLyrisSoilCell& Cell = Cells[CellIndex];
	const ULyrisCropDefinition* Crop = Cell.IsPlanted() ? FindCrop(Cell.CropId) : nullptr;
	if (!Crop)
	{
		return 0.0;
	}

	const int64 Now = NowUtc.GetTicks();
	const int64 Planted = FMath::Min(Cell.PlantedAtTicks, Now);
	const double Elapsed = FTimespan(Now - Planted).GetTotalSeconds();
	const double Rate = static_cast<double>(GetCellBaseRate(CellIndex)) * static_cast<double>(GetSeasonFactor(Crop));

	// Watering window: [WateredUntil - WaterHours, WateredUntil], counted only after planting.
	// Irrigation (P2) and rain (P3) count as watered the whole time.
	double WateredSeconds = 0.0;
	if (IsCellIrrigated(CellIndex) || IsRaining())
	{
		WateredSeconds = Elapsed;
	}
	else if (Cell.WateredUntilTicks > 0)
	{
		const int64 WindowStart = Cell.WateredUntilTicks - FTimespan::FromSeconds(GetWaterSeconds()).GetTicks();
		WateredSeconds = LyrisFarmPlot::Overlap(Planted, Now, WindowStart, Cell.WateredUntilTicks);
	}

	const double Growth = Elapsed * Rate + Cell.BonusSeconds + WateredSeconds * WaterBonus * Rate;
	return FMath::Clamp(Growth, 0.0, Crop->GetRipeSeconds());
}

int32 ALyrisFarmPlot::GetStage(int32 CellIndex, const FDateTime& NowUtc) const
{
	if (!IsValidCell(CellIndex))
	{
		return INDEX_NONE;
	}
	const FLyrisSoilCell& Cell = Cells[CellIndex];
	const ULyrisCropDefinition* Crop = Cell.IsPlanted() ? FindCrop(Cell.CropId) : nullptr;
	return Crop ? Crop->GetStageForGrowth(GetGrowthSeconds(CellIndex, NowUtc)) : INDEX_NONE;
}

bool ALyrisFarmPlot::IsRipe(int32 CellIndex, const FDateTime& NowUtc) const
{
	if (!IsValidCell(CellIndex))
	{
		return false;
	}
	const FLyrisSoilCell& Cell = Cells[CellIndex];
	const ULyrisCropDefinition* Crop = Cell.IsPlanted() ? FindCrop(Cell.CropId) : nullptr;
	return Crop && GetGrowthSeconds(CellIndex, NowUtc) >= Crop->GetRipeSeconds();
}

bool ALyrisFarmPlot::IsWateredNow(int32 CellIndex, const FDateTime& NowUtc) const
{
	if (!IsValidCell(CellIndex))
	{
		return false;
	}
	return IsCellIrrigated(CellIndex) || IsRaining() || Cells[CellIndex].WateredUntilTicks > NowUtc.GetTicks();
}

FLyrisCropStatus ALyrisFarmPlot::GetCropStatus(int32 CellIndex) const
{
	FLyrisCropStatus Status;
	if (!IsValidCell(CellIndex))
	{
		return Status;
	}

	const FLyrisSoilCell& Cell = Cells[CellIndex];
	const FDateTime Now = FDateTime::UtcNow();
	Status.State = Cell.State;
	Status.CropId = Cell.CropId;
	Status.QualityPoints = Cell.QualityPoints;
	Status.bCaredToday = Cell.CaredDay == GetUtcDayNumber(Now);
	Status.bWatered = IsWateredNow(CellIndex, Now);
	Status.WateredSecondsLeft = Cell.WateredUntilTicks > Now.GetTicks()
		? static_cast<float>(FTimespan(Cell.WateredUntilTicks - Now.GetTicks()).GetTotalSeconds()) : 0.f;

	const ULyrisCropDefinition* Crop = Cell.IsPlanted() ? FindCrop(Cell.CropId) : nullptr;
	if (!Crop)
	{
		return Status;
	}

	const double Growth = GetGrowthSeconds(CellIndex, Now);
	const double Ripe = Crop->GetRipeSeconds();
	Status.CropName = Crop->Data.DisplayName;
	Status.StageCount = Crop->GetStageCount();
	Status.Stage = Crop->GetStageForGrowth(Growth);
	Status.bRipe = Growth >= Ripe;
	Status.GrowthFraction = static_cast<float>(Growth / Ripe);

	// Time to ripe at the current pace, assuming any active watering runs out on schedule.
	const double Rate = static_cast<double>(GetCellBaseRate(CellIndex)) * static_cast<double>(GetSeasonFactor(Crop));
	if (Status.bRipe)
	{
		Status.SecondsToRipe = 0.f;
	}
	else if (Rate <= 0.0)
	{
		Status.SecondsToRipe = -1.f; // dormant
	}
	else
	{
		double Remaining = Ripe - Growth;
		double Seconds = 0.0;
		const double WetLeft = (IsCellIrrigated(CellIndex) || IsRaining()) ? TNumericLimits<double>::Max() : Status.WateredSecondsLeft;
		const double WetRate = Rate * (1.0 + WaterBonus);
		const double WetGrowth = FMath::Min(Remaining, WetLeft * WetRate);
		Seconds += WetGrowth / WetRate;
		Remaining -= WetGrowth;
		Seconds += Remaining / Rate;
		Status.SecondsToRipe = static_cast<float>(Seconds);
	}
	return Status;
}

// ---------------------------------------------------------------------------------------------
// Interaction

FName ALyrisFarmPlot::FindSeedToPlant(const ULyrisInventoryComponent* Inventory) const
{
	const ULyrisCropRegistry* Registry = ULyrisCropRegistry::Get(this);
	if (!Inventory || !Registry)
	{
		return NAME_None;
	}

	if (const ULyrisItemDefinition* Active = Inventory->GetActiveItem())
	{
		if (Active->Category == ELyrisItemCategory::Seed && Registry->FindCropForSeed(Active->ItemId))
		{
			return Active->ItemId;
		}
	}
	for (const FLyrisInventorySlot& Slot : Inventory->GetSlots())
	{
		if (!Slot.IsEmpty() && Registry->FindCropForSeed(Slot.ItemId))
		{
			return Slot.ItemId;
		}
	}
	return NAME_None;
}

ELyrisFarmAction ALyrisFarmPlot::GetActionFor(int32 CellIndex, const AActor* InteractingActor) const
{
	if (!IsValidCell(CellIndex))
	{
		return ELyrisFarmAction::None;
	}

	const ULyrisInventoryComponent* Inventory = ULyrisInventoryComponent::FindInventory(InteractingActor);
	const FLyrisSoilCell& Cell = Cells[CellIndex];
	const FDateTime Now = FDateTime::UtcNow();

	switch (Cell.State)
	{
	case ELyrisSoilState::Untilled:
		return (Inventory && Inventory->HasTool(HoeToolType)) ? ELyrisFarmAction::Till : ELyrisFarmAction::None;

	case ELyrisSoilState::Tilled:
		return FindSeedToPlant(Inventory).IsNone() ? ELyrisFarmAction::None : ELyrisFarmAction::Plant;

	case ELyrisSoilState::Planted:
		if (IsRipe(CellIndex, Now))
		{
			return ELyrisFarmAction::Harvest;
		}
		if (!IsWateredNow(CellIndex, Now) && Inventory && Inventory->HasTool(WateringToolType))
		{
			return ELyrisFarmAction::Water;
		}
		if (Cell.CaredDay != GetUtcDayNumber(Now))
		{
			return ELyrisFarmAction::Care;
		}
		return ELyrisFarmAction::None;
	}
	return ELyrisFarmAction::None;
}

bool ALyrisFarmPlot::CanInteract_Implementation(AActor* InteractingActor) const
{
	// Any cell in front counts, so the prompt can also show a crop's status or what's needed.
	return IsValidCell(GetCellForActor(InteractingActor));
}

FText ALyrisFarmPlot::GetInteractPrompt_Implementation(AActor* InteractingActor) const
{
	const int32 CellIndex = GetCellForActor(InteractingActor);
	if (!IsValidCell(CellIndex))
	{
		return FText::GetEmpty();
	}

	const FLyrisSoilCell& Cell = Cells[CellIndex];
	const ULyrisCropDefinition* Crop = Cell.IsPlanted() ? FindCrop(Cell.CropId) : nullptr;
	const FText CropName = Crop ? Crop->Data.DisplayName : FText::GetEmpty();

	switch (GetActionFor(CellIndex, InteractingActor))
	{
	case ELyrisFarmAction::Till:
		return LOCTEXT("Till", "Till soil");

	case ELyrisFarmAction::Plant:
	{
		const FName SeedId = FindSeedToPlant(ULyrisInventoryComponent::FindInventory(InteractingActor));
		const ULyrisItemDefinition* Seed = ULyrisItemRegistry::FindItem(this, SeedId);
		return FText::Format(LOCTEXT("Plant", "Plant {0}"), Seed ? Seed->DisplayName : FText::FromName(SeedId));
	}

	case ELyrisFarmAction::Water:
		return FText::Format(LOCTEXT("Water", "Water {0}"), CropName);

	case ELyrisFarmAction::Care:
		return FText::Format(LOCTEXT("Care", "Tend {0}"), CropName);

	case ELyrisFarmAction::Harvest:
		return FText::Format(LOCTEXT("Harvest", "Harvest {0}"), CropName);

	case ELyrisFarmAction::None:
	default:
		break;
	}

	// Nothing to do: describe the cell instead. Never a warning, never urgent.
	switch (Cell.State)
	{
	case ELyrisSoilState::Untilled:
		return LOCTEXT("NeedsHoe", "Untilled ground: a hoe would turn it");
	case ELyrisSoilState::Tilled:
		return LOCTEXT("NeedsSeed", "Tilled soil, ready for a seed");
	case ELyrisSoilState::Planted:
	{
		const FLyrisCropStatus Status = GetCropStatus(CellIndex);
		if (Status.SecondsToRipe < 0.f)
		{
			return FText::Format(LOCTEXT("Dormant", "{0}: resting until its season"), CropName);
		}
		return FText::Format(LOCTEXT("Growing", "{0}: ripe in {1}"), CropName, LyrisFarmPlot::FormatDuration(Status.SecondsToRipe));
	}
	}
	return FText::GetEmpty();
}

void ALyrisFarmPlot::Interact_Implementation(AActor* InteractingActor)
{
	if (!HasAuthority())
	{
		return;
	}

	const int32 CellIndex = GetCellForActor(InteractingActor);
	ULyrisInventoryComponent* Inventory = ULyrisInventoryComponent::FindInventory(InteractingActor);

	switch (GetActionFor(CellIndex, InteractingActor))
	{
	case ELyrisFarmAction::Till:
		TillCell(CellIndex);
		break;
	case ELyrisFarmAction::Plant:
		PlantCell(CellIndex, FindSeedToPlant(Inventory), Inventory);
		break;
	case ELyrisFarmAction::Water:
		WaterCell(CellIndex);
		break;
	case ELyrisFarmAction::Care:
		CareForCell(CellIndex);
		break;
	case ELyrisFarmAction::Harvest:
		HarvestCell(CellIndex, Inventory);
		break;
	case ELyrisFarmAction::None:
	default:
		break;
	}
}

// ---------------------------------------------------------------------------------------------
// Actions

bool ALyrisFarmPlot::TillCell(int32 CellIndex)
{
	if (!IsValidCell(CellIndex) || Cells[CellIndex].State != ELyrisSoilState::Untilled)
	{
		return false;
	}
	Cells[CellIndex].State = ELyrisSoilState::Tilled;
	NotifyCellChanged(CellIndex, ELyrisFarmAction::Till);
	return true;
}

FName ALyrisFarmPlot::ChooseCropForSeed_Implementation(FName SeedItemId, int32 CellIndex) const
{
	const ULyrisCropRegistry* Registry = ULyrisCropRegistry::Get(this);
	const ULyrisCropDefinition* Crop = Registry ? Registry->FindCropForSeed(SeedItemId) : nullptr;
	return Crop ? Crop->CropId : NAME_None;
}

bool ALyrisFarmPlot::PlantCell(int32 CellIndex, FName SeedItemId, ULyrisInventoryComponent* Inventory)
{
	if (!IsValidCell(CellIndex) || Cells[CellIndex].State != ELyrisSoilState::Tilled || SeedItemId.IsNone())
	{
		return false;
	}

	const FName CropId = ChooseCropForSeed(SeedItemId, CellIndex);
	if (CropId.IsNone() || !FindCrop(CropId))
	{
		return false;
	}
	if (Inventory && !Inventory->RemoveItemById(SeedItemId, 1))
	{
		return false;
	}

	FLyrisSoilCell& Cell = Cells[CellIndex];
	Cell.ClearCrop();
	Cell.State = ELyrisSoilState::Planted;
	Cell.CropId = CropId;
	Cell.PlantedAtTicks = FDateTime::UtcNow().GetTicks();
	NotifyCellChanged(CellIndex, ELyrisFarmAction::Plant);
	return true;
}

bool ALyrisFarmPlot::WaterCell(int32 CellIndex)
{
	if (!IsValidCell(CellIndex) || !Cells[CellIndex].IsPlanted())
	{
		return false;
	}

	FLyrisSoilCell& Cell = Cells[CellIndex];
	const FDateTime Now = FDateTime::UtcNow();
	const ULyrisCropDefinition* Crop = FindCrop(Cell.CropId);

	// Bank what the previous watering window already earned, so a new window never erases it.
	if (Crop && Cell.WateredUntilTicks > 0)
	{
		const int64 WindowStart = Cell.WateredUntilTicks - FTimespan::FromSeconds(GetWaterSeconds()).GetTicks();
		const double Earned = LyrisFarmPlot::Overlap(Cell.PlantedAtTicks, Now.GetTicks(), WindowStart, Cell.WateredUntilTicks);
		const double Rate = static_cast<double>(GetCellBaseRate(CellIndex)) * static_cast<double>(GetSeasonFactor(Crop));
		Cell.BonusSeconds += Earned * WaterBonus * Rate;
	}

	Cell.WateredUntilTicks = (Now + FTimespan::FromSeconds(GetWaterSeconds())).GetTicks();
	NotifyCellChanged(CellIndex, ELyrisFarmAction::Water);
	return true;
}

bool ALyrisFarmPlot::CareForCell(int32 CellIndex)
{
	if (!IsValidCell(CellIndex) || !Cells[CellIndex].IsPlanted())
	{
		return false;
	}
	FLyrisSoilCell& Cell = Cells[CellIndex];
	const int32 Today = GetUtcDayNumber(FDateTime::UtcNow());
	if (Cell.CaredDay == Today)
	{
		return false;
	}
	Cell.CaredDay = Today;
	++Cell.QualityPoints;
	NotifyCellChanged(CellIndex, ELyrisFarmAction::Care);
	return true;
}

ELyrisItemQuality ALyrisFarmPlot::RollQuality(const FLyrisSoilCell& Cell) const
{
	// Normal is always reachable with zero care; each day of care raises the odds of better tiers.
	const float Points = static_cast<float>(FMath::Max(0, Cell.QualityPoints));
	const float Roll = FMath::FRand();
	const float RadiantChance = FMath::Min(0.02f * Points, 0.15f);
	const float SplendidChance = FMath::Min(0.05f * Points, 0.30f);
	const float FineChance = FMath::Min(0.10f * Points, 0.40f);

	if (Roll < RadiantChance)
	{
		return ELyrisItemQuality::Radiant;
	}
	if (Roll < RadiantChance + SplendidChance)
	{
		return ELyrisItemQuality::Splendid;
	}
	if (Roll < RadiantChance + SplendidChance + FineChance)
	{
		return ELyrisItemQuality::Fine;
	}
	return ELyrisItemQuality::Normal;
}

bool ALyrisFarmPlot::HarvestCell(int32 CellIndex, ULyrisInventoryComponent* Inventory)
{
	if (!IsValidCell(CellIndex) || !Inventory)
	{
		return false;
	}

	FLyrisSoilCell& Cell = Cells[CellIndex];
	const FDateTime Now = FDateTime::UtcNow();
	const ULyrisCropDefinition* Crop = Cell.IsPlanted() ? FindCrop(Cell.CropId) : nullptr;
	if (!Crop || !IsRipe(CellIndex, Now))
	{
		return false;
	}

	TArray<FLyrisItemStack> Items;
	const int32 Count = FMath::Max(1, Crop->Data.Yield.Roll());
	Items.Emplace(Crop->Data.Yield.ItemId, Count, RollQuality(Cell));
	if (Cell.QualityPoints > 0 && !Crop->Data.SeedItemId.IsNone() && FMath::FRand() < Crop->Data.BonusSeedChance)
	{
		Items.Emplace(Crop->Data.SeedItemId, 1);
	}
	ModifyHarvest(CellIndex, Crop, Items);

	// Nothing is lost to a full bag: the crop stays ripe until there's room.
	if (!Inventory->AddAll(Items))
	{
		OnBagFull.Broadcast(this, CellIndex, ELyrisFarmAction::Harvest);
		return false;
	}

	if (Crop->Data.bRegrows)
	{
		// Back to the stage that is RegrowHours from ripe. Watering and care carry on as they were.
		const double RegrowSeconds = FMath::Clamp(static_cast<double>(Crop->Data.RegrowHours) * 3600.0, 1.0, Crop->GetRipeSeconds());
		Cell.PlantedAtTicks = Now.GetTicks();
		Cell.BonusSeconds = Crop->GetRipeSeconds() - RegrowSeconds;
		Cell.QualityPoints = 0;
	}
	else
	{
		Cell.ClearCrop();
	}

	NotifyCellChanged(CellIndex, ELyrisFarmAction::Harvest);
	return true;
}

void ALyrisFarmPlot::RestoreCells(const TArray<FLyrisSoilCell>& SavedCells)
{
	Cells = SavedCells;
	EnsureCells();
	RebuildVisuals();
}

void ALyrisFarmPlot::NotifyCellChanged(int32 CellIndex, ELyrisFarmAction Action)
{
	RebuildVisuals();
	OnCellChanged.Broadcast(this, CellIndex, Action);
}

void ALyrisFarmPlot::OnRep_Cells()
{
	RebuildVisuals();
}

// ---------------------------------------------------------------------------------------------
// Visuals

void ALyrisFarmPlot::SetHighlightedCell(int32 CellIndex)
{
	if (!Highlight)
	{
		return;
	}
	if (!IsValidCell(CellIndex))
	{
		Highlight->SetVisibility(false);
		Highlight->SetHiddenInGame(true);
		return;
	}
	// The engine plane is 100 cm; lift it a touch above the soil.
	Highlight->SetRelativeLocation(GetCellLocalLocation(CellIndex) + FVector(0.f, 0.f, 8.f));
	Highlight->SetRelativeScale3D(FVector(CellSize / 100.f, CellSize / 100.f, 1.f));
	Highlight->SetHiddenInGame(false);
	Highlight->SetVisibility(true);
}

void ALyrisFarmPlot::CheckStagesChanged()
{
	const FDateTime Now = FDateTime::UtcNow();
	bool bChanged = ShownStages.Num() != Cells.Num();
	for (int32 Index = 0; !bChanged && Index < Cells.Num(); ++Index)
	{
		const int32 Stage = GetStage(Index, Now);
		// Encode watered as a high bit so the soil darkens / lightens when a window ends.
		const int32 Key = Stage + (IsWateredNow(Index, Now) ? 1000 : 0);
		bChanged = ShownStages[Index] != Key;
	}
	if (bChanged)
	{
		RebuildVisuals();
	}
}

UInstancedStaticMeshComponent* ALyrisFarmPlot::GetCropInstances(UStaticMesh* StageMesh)
{
	for (UInstancedStaticMeshComponent* Existing : CropInstances)
	{
		if (Existing && Existing->GetStaticMesh() == StageMesh)
		{
			return Existing;
		}
	}

	UInstancedStaticMeshComponent* Component = NewObject<UInstancedStaticMeshComponent>(this, NAME_None, RF_Transient);
	Component->SetupAttachment(Root);
	Component->SetStaticMesh(StageMesh);
	Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Component->SetCanEverAffectNavigation(false);
	Component->RegisterComponent();
	CropInstances.Add(Component);
	return Component;
}

void ALyrisFarmPlot::RebuildVisuals_Implementation()
{
	const FDateTime Now = FDateTime::UtcNow();
	UStaticMesh* SoilMesh = TilledMesh.IsNull() ? nullptr : TilledMesh.LoadSynchronous();
	UMaterialInterface* SoilMaterial = TilledMaterial.IsNull() ? nullptr : TilledMaterial.LoadSynchronous();
	UMaterialInterface* WetMaterial = WateredMaterial.IsNull() ? SoilMaterial : WateredMaterial.LoadSynchronous();

	SoilInstances->ClearInstances();
	WateredSoilInstances->ClearInstances();
	SoilInstances->SetStaticMesh(SoilMesh);
	WateredSoilInstances->SetStaticMesh(SoilMesh);
	if (SoilMaterial)
	{
		SoilInstances->SetMaterial(0, SoilMaterial);
	}
	if (WetMaterial)
	{
		WateredSoilInstances->SetMaterial(0, WetMaterial);
	}

	// Crop instance components are only made at runtime (not in the editor construction script).
	const bool bShowCrops = GetWorld() && GetWorld()->IsGameWorld();
	for (UInstancedStaticMeshComponent* Component : CropInstances)
	{
		if (Component)
		{
			Component->ClearInstances();
		}
	}

	ShownStages.SetNum(Cells.Num());
	for (int32 Index = 0; Index < Cells.Num(); ++Index)
	{
		const FLyrisSoilCell& Cell = Cells[Index];
		const int32 Stage = GetStage(Index, Now);
		const bool bWet = IsWateredNow(Index, Now);
		ShownStages[Index] = Stage + (bWet ? 1000 : 0);

		if (Cell.State == ELyrisSoilState::Untilled)
		{
			continue;
		}

		const FVector Local = GetCellLocalLocation(Index);
		if (SoilMesh)
		{
			// Engine cube pivots at its centre: sit the bed on the ground.
			const FVector SoilScale = TilledMeshScale * (CellSize / 100.f);
			const FTransform SoilTransform(FRotator::ZeroRotator, Local + FVector(0.f, 0.f, SoilScale.Z * 50.f), SoilScale);
			(bWet && Cell.IsPlanted() ? WateredSoilInstances : SoilInstances)->AddInstance(SoilTransform, false);
		}

		if (!bShowCrops || Stage == INDEX_NONE)
		{
			continue;
		}
		const ULyrisCropDefinition* Crop = FindCrop(Cell.CropId);
		if (!Crop || !Crop->Data.Stages.IsValidIndex(Stage))
		{
			continue;
		}
		const FLyrisCropStage& StageData = Crop->Data.Stages[Stage];
		UStaticMesh* StageMesh = StageData.Mesh.IsNull() ? nullptr : StageData.Mesh.LoadSynchronous();
		if (!StageMesh)
		{
			continue;
		}

		UInstancedStaticMeshComponent* Component = GetCropInstances(StageMesh);

		// Small stable per-cell yaw so a field doesn't look stamped.
		const float Yaw = static_cast<float>((Index * 7919) % 360);
		const float SoilTop = SoilMesh ? TilledMeshScale.Z * (CellSize / 100.f) * 100.f : 0.f;
		const FTransform CropTransform(FRotator(0.f, Yaw, 0.f), Local + FVector(0.f, 0.f, SoilTop + StageData.Scale.Z * 50.f), StageData.Scale);
		Component->AddInstance(CropTransform, false);
	}
}

#undef LOCTEXT_NAMESPACE
