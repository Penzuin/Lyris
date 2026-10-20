// Lyris farming: a patch of ground split into 100 cm soil cells (design/farming.md).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Interaction/LyrisInteractable.h"
#include "Items/LyrisInventoryComponent.h"
#include "LyrisSoilCell.h"
#include "LyrisFarmPlot.generated.h"

class UBoxComponent;
class UInstancedStaticMeshComponent;
class UMaterialInterface;
class UStaticMesh;
class UStaticMeshComponent;
class ULyrisCropDefinition;
class ALyrisFarmPlot;

/** What interacting with a cell would do right now. */
UENUM(BlueprintType)
enum class ELyrisFarmAction : uint8
{
	None,
	Till,
	Plant,
	Water,
	Care,
	Harvest
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FLyrisFarmCellEvent, ALyrisFarmPlot*, Plot, int32, CellIndex, ELyrisFarmAction, Action);

/**
 * A farm plot: a GridSize grid of soil cells, each traced to the ground so the plot follows
 * slopes. Place it on flat-ish ground (Environment lane, T15) and walk onto it.
 *
 * The one rule (design/farming.md section 1): nothing is lost by not tending; tending only adds.
 * A planted crop grows at its base rate on real-world UTC time, online or not, and never wilts,
 * dies or loses a stage. Watering and daily care are pure bonuses.
 *
 * Growth is timestamp maths (section 3), evaluated when someone looks or interacts. A slow timer
 * (VisualRefreshSeconds) only checks whether any cell's stage changed so the mesh can swap.
 *
 * One Interact does the right thing for the cell the player faces: till (hoe) -> plant (a seed)
 * -> water (watering can) -> tend (daily care) -> harvest when ripe.
 *
 * Hooks for later tasks, deliberately not built:
 *   P1 charged tools   - GetCellsInArea(Center, Radius) for 3x3 / 5x5; actions take a cell index.
 *   P2 irrigation      - IsCellIrrigated.
 *   P3 seasons, rain   - GetSeasonFactor, IsRaining.
 *   P4 special soils   - SoilBaseRate, GetCellBaseRate.
 *   P5 scarecrows      - ModifyHarvest; actions are public so a construct can call them.
 *   Fertilizer         - FLyrisSoilCell::FertilizerId is reserved.
 *   Cultivation lane   - ChooseCropForSeed (pick a hybrid from neighbours), ModifyHarvest,
 *                        GetNeighbourCells, and ULyrisCropRegistry::RegisterCrop for new varieties.
 *
 * Multiplayer later: Cells is replicated; switch it to an FFastArraySerializer once plots grow
 * large, and route Interact through the server (it already returns early without authority).
 */
UCLASS(Blueprintable)
class LYRIS_API ALyrisFarmPlot : public AActor, public ILyrisInteractable
{
	GENERATED_BODY()

public:
	ALyrisFarmPlot();

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	// ILyrisInteractable
	virtual bool CanInteract_Implementation(AActor* InteractingActor) const override;
	virtual FText GetInteractPrompt_Implementation(AActor* InteractingActor) const override;
	virtual void Interact_Implementation(AActor* InteractingActor) override;

	// ---- Layout ----

	/** Cells along X and Y. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm", meta = (ClampMin = "1", ClampMax = "32"))
	FIntPoint GridSize = FIntPoint(4, 4);

	/** Cell edge in cm. The spec fixes this at 100. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm", meta = (ClampMin = "25"))
	float CellSize = 100.f;

	/** Start with every cell tilled (handy for testing or a ready-made starter plot). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm")
	bool bStartTilled = false;

	// ---- Tending (bonuses only) ----

	/** Watering bonus: growth runs this much faster while watered (0.5 = +50%). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm", meta = (ClampMin = "0"))
	float WaterBonus = 0.5f;

	/** Real-world hours one watering lasts. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm", meta = (ClampMin = "0.1"))
	float WaterHours = 4.f;

	/** Base growth rate of this plot's soil (P4: special soils raise it). Never below 1. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm", meta = (ClampMin = "1"))
	float SoilBaseRate = 1.f;

	/** Tool types (see LyrisItemCatalog). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm")
	FName HoeToolType = TEXT("Hoe");

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm")
	FName WateringToolType = TEXT("WateringCan");

	// ---- Visuals ----

	/** Mesh for a tilled cell (scaled to the cell). Defaults to a flattened engine cube. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm|Visual")
	TSoftObjectPtr<UStaticMesh> TilledMesh;

	/** Scale of TilledMesh per cell. The default cube is 100 cm, so (0.95, 0.95, 0.06) is a soil bed. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm|Visual")
	FVector TilledMeshScale = FVector(0.95f, 0.95f, 0.06f);

	/** Material for tilled soil. Colours belong to the Environment lane's palette. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm|Visual")
	TSoftObjectPtr<UMaterialInterface> TilledMaterial;

	/** Material for tilled soil while its crop is watered. Optional. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm|Visual")
	TSoftObjectPtr<UMaterialInterface> WateredMaterial;

	/** Seconds between checks for stage changes (visual only; growth itself is never ticked). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Farm|Visual", meta = (ClampMin = "1"))
	float VisualRefreshSeconds = 5.f;

	// ---- Queries ----

	UFUNCTION(BlueprintPure, Category = "Lyris|Farm")
	int32 GetCellCount() const { return GridSize.X * GridSize.Y; }

	/** Cell under a world location, or INDEX_NONE if outside the grid. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Farm")
	int32 GetCellAtLocation(const FVector& WorldLocation) const;

	/** World position of a cell's centre on the ground. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Farm")
	FVector GetCellWorldLocation(int32 CellIndex) const;

	/** The cell an actor is facing (uses its ULyrisInteractionComponent aim when it has one). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Farm")
	int32 GetCellForActor(const AActor* InteractingActor) const;

	/** Cells within Radius cells of Center (0 = just Center, 1 = 3x3, 2 = 5x5). For charged tools (P1). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Farm")
	TArray<int32> GetCellsInArea(int32 CenterIndex, int32 Radius) const;

	/** The up to 8 cells around a cell. For Cultivation (cross-breeding neighbours) and giant crops. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Farm")
	TArray<int32> GetNeighbourCells(int32 CellIndex) const;

	UFUNCTION(BlueprintPure, Category = "Lyris|Farm")
	FLyrisSoilCell GetCell(int32 CellIndex) const;

	/** Stage, time to ripe and active bonuses, for a hover tooltip (P6). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Farm")
	FLyrisCropStatus GetCropStatus(int32 CellIndex) const;

	/** Effective growth seconds of a cell (section 3), capped at ripe. */
	double GetGrowthSeconds(int32 CellIndex, const FDateTime& NowUtc) const;

	/** What Interact would do on this cell for this actor. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Farm")
	ELyrisFarmAction GetActionFor(int32 CellIndex, const AActor* InteractingActor) const;

	// ---- Actions (public so tools, constructs and tests can drive them). Each returns true on success. ----

	UFUNCTION(BlueprintCallable, Category = "Lyris|Farm")
	bool TillCell(int32 CellIndex);

	/** Plants a seed item, taking one from Inventory when given. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Farm")
	bool PlantCell(int32 CellIndex, FName SeedItemId, ULyrisInventoryComponent* Inventory);

	UFUNCTION(BlueprintCallable, Category = "Lyris|Farm")
	bool WaterCell(int32 CellIndex);

	/** Daily care (talk, prune, sing): once per crop per real-world UTC day. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Farm")
	bool CareForCell(int32 CellIndex);

	/** Harvests a ripe crop into Inventory. Fails, changing nothing, if the yield doesn't fit. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Farm")
	bool HarvestCell(int32 CellIndex, ULyrisInventoryComponent* Inventory);

	/** Shows the cell highlight on a cell (INDEX_NONE hides it). For the UI / Player lane to drive from the aim. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Farm")
	void SetHighlightedCell(int32 CellIndex);

	// ---- Save / load ----

	UFUNCTION(BlueprintPure, Category = "Lyris|Farm")
	TArray<FLyrisSoilCell> GetCells() const { return Cells; }

	/** Restores saved cells. Timestamps are absolute UTC, so crops have kept growing while saved. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Farm")
	void RestoreCells(const TArray<FLyrisSoilCell>& SavedCells);

	// ---- Events ----

	UPROPERTY(BlueprintAssignable, Category = "Lyris|Farm")
	FLyrisFarmCellEvent OnCellChanged;

	/** A harvest didn't fit in the bag; the crop stays ripe and waits. For a HUD hint. */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Farm")
	FLyrisFarmCellEvent OnBagFull;

	// ---- Hooks for later tasks ----

	/**
	 * P3: 1 until the World lane ships seasons; then 1.25 in season and 0 (dormant) out of season.
	 * IMPORTANT for P3: the section 3 formula multiplies all elapsed time by this factor, so a
	 * factor that changes over a crop's life must be handled by banking growth into BonusSeconds
	 * and resetting PlantedAtTicks at each season change (as WaterCell does for watering windows).
	 * Otherwise a ripe crop would look unripe when it goes dormant, which breaks the one rule.
	 */
	virtual float GetSeasonFactor(const ULyrisCropDefinition* Crop) const { return 1.f; }

	/** P3: rain counts as watering. */
	virtual bool IsRaining() const { return false; }

	/** P2: an irrigation rune keeps this cell watered permanently. */
	virtual bool IsCellIrrigated(int32 CellIndex) const { return false; }

	/** P4: base rate for a cell (soil type). Must never return less than 1. */
	virtual float GetCellBaseRate(int32 CellIndex) const { return FMath::Max(1.f, SoilBaseRate); }

	/** Cultivation: which crop a seed becomes in this cell. Default: the seed's own crop. */
	UFUNCTION(BlueprintNativeEvent, Category = "Lyris|Farm")
	FName ChooseCropForSeed(FName SeedItemId, int32 CellIndex) const;

	/** P5 / Cultivation / fertilizer: adjust what a harvest gives before it's handed out. Can only add. */
	virtual void ModifyHarvest(int32 CellIndex, const ULyrisCropDefinition* Crop, TArray<FLyrisItemStack>& InOutItems) const {}

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> Root;

	/** Covers the grid so the interaction scan finds the plot. Query only, blocks nothing. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UBoxComponent> InteractVolume;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UInstancedStaticMeshComponent> SoilInstances;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UInstancedStaticMeshComponent> WateredSoilInstances;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UStaticMeshComponent> Highlight;

	/** Visual hook: rebuilds soil and crop instances. Override in Blueprint for effects. */
	UFUNCTION(BlueprintNativeEvent, Category = "Lyris|Farm")
	void RebuildVisuals();

	bool IsValidCell(int32 CellIndex) const { return Cells.IsValidIndex(CellIndex); }
	FIntPoint IndexToCoord(int32 CellIndex) const { return FIntPoint(CellIndex % GridSize.X, CellIndex / GridSize.X); }
	int32 CoordToIndex(int32 X, int32 Y) const;
	FVector GetCellLocalLocation(int32 CellIndex) const;

	ULyrisCropDefinition* FindCrop(FName CropId) const;
	bool IsWateredNow(int32 CellIndex, const FDateTime& NowUtc) const;
	bool IsRipe(int32 CellIndex, const FDateTime& NowUtc) const;
	int32 GetStage(int32 CellIndex, const FDateTime& NowUtc) const;

	/** The seed the actor would plant: the active hotbar item if it's a plantable seed, else the first plantable seed. */
	FName FindSeedToPlant(const ULyrisInventoryComponent* Inventory) const;

	ELyrisItemQuality RollQuality(const FLyrisSoilCell& Cell) const;

	void EnsureCells();
	void TraceCellHeights();
	void CheckStagesChanged();
	void NotifyCellChanged(int32 CellIndex, ELyrisFarmAction Action);

	static int32 GetUtcDayNumber(const FDateTime& NowUtc);
	double GetWaterSeconds() const { return static_cast<double>(WaterHours) * 3600.0; }

	UFUNCTION()
	void OnRep_Cells();

	UPROPERTY(VisibleInstanceOnly, ReplicatedUsing = OnRep_Cells, Category = "Lyris|Farm")
	TArray<FLyrisSoilCell> Cells;

	/** Ground height of each cell relative to the actor, from the ground trace. */
	UPROPERTY(Transient)
	TArray<float> CellGroundZ;

	/** One instanced mesh component per crop-stage mesh, created on demand. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UInstancedStaticMeshComponent>> CropInstances;

	UInstancedStaticMeshComponent* GetCropInstances(UStaticMesh* StageMesh);

	/** Stage each cell showed at the last rebuild, to spot changes cheaply. */
	TArray<int32> ShownStages;

	FTimerHandle VisualTimer;
};
