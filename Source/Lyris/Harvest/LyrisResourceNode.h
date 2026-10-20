// Lyris harvest: a rock, ore vein, crystal, tree or herb patch the player gathers from.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Interaction/LyrisInteractable.h"
#include "LyrisResourceNodeTypes.h"
#include "LyrisResourceNode.generated.h"

class UDataTable;
class UStaticMeshComponent;
class ALyrisResourceNode;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FLyrisResourceNodeHit, ALyrisResourceNode*, Node, int32, HitsRemaining);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FLyrisResourceNodeStateChanged, ALyrisResourceNode*, Node);

/**
 * One gatherable thing in the world. What it is comes from data (NodeType looked up in NodeTable
 * or in the built-in catalog), so a copper vein and a tree are the same class with different rows.
 *
 * Place one in a level (Environment lane, T15), set NodeType, and it works with the player's
 * ULyrisInteractionComponent and ULyrisInventoryComponent.
 *
 * Calm by default: refill is stamped in real-world UTC (DepletedAtUtc + RespawnHours), so a node
 * gathered yesterday is full again when you log back in, whether or not anyone was online. Hit
 * progress is kept, never decays.
 *
 * Multiplayer later: all state is three plain replicated fields (HitsTaken, bDepleted,
 * DepletedAtUtcTicks); Interact should run on the server only.
 */
UCLASS(Blueprintable)
class LYRIS_API ALyrisResourceNode : public AActor, public ILyrisInteractable
{
	GENERATED_BODY()

public:
	ALyrisResourceNode();

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	// ILyrisInteractable
	virtual bool CanInteract_Implementation(AActor* InteractingActor) const override;
	virtual FText GetInteractPrompt_Implementation(AActor* InteractingActor) const override;
	virtual void Interact_Implementation(AActor* InteractingActor) override;

	/** Which kind of node this is: a row name in NodeTable, or a built-in id ("rock", "copper_vein", "star_crystal", "tree", "sea_herb"). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Resource")
	FName NodeType = TEXT("rock");

	/** Optional table of FLyrisResourceNodeData rows. Falls back to the built-in catalog when empty or missing the row. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Resource", meta = (RequiredAssetDataTags = "RowStructure=/Script/Lyris.LyrisResourceNodeData"))
	TObjectPtr<UDataTable> NodeTable;

	/** Use these values instead of a table row (handy for one-off nodes in a Blueprint). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Resource")
	bool bUseCustomData = false;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Resource", meta = (EditCondition = "bUseCustomData"))
	FLyrisResourceNodeData CustomData;

	/** Resolved data for this node (table row, custom data or built-in). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Resource")
	FLyrisResourceNodeData GetNodeData() const { return Data; }

	UFUNCTION(BlueprintPure, Category = "Lyris|Resource")
	bool IsDepleted() const { return bDepleted; }

	UFUNCTION(BlueprintPure, Category = "Lyris|Resource")
	int32 GetHitsRemaining() const { return FMath::Max(0, Data.HitsToGather - HitsTaken); }

	/** When it refills, in UTC. Only meaningful while depleted. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Resource")
	FDateTime GetRespawnAtUtc() const;

	/** Seconds of real time until it refills (0 if ready). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Resource")
	float GetSecondsUntilRespawn() const;

	/** Refill now (debug, events, or a save loader restoring state). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Resource")
	void Replenish();

	/** For a save system: restore a depleted node with its original UTC stamp. Refills at once if already due. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Resource")
	void RestoreDepleted(FDateTime DepletedAtUtc);

	/** Each successful hit that didn't finish the node. */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Resource")
	FLyrisResourceNodeHit OnHit;

	/** Gathered (now depleted). */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Resource")
	FLyrisResourceNodeStateChanged OnGathered;

	/** The last hit landed but the gatherer's bag was full; the node stays as it was. For a HUD hint. */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Resource")
	FLyrisResourceNodeStateChanged OnBagFull;

	/** Full again. */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Resource")
	FLyrisResourceNodeStateChanged OnReplenished;

protected:
	/**
	 * Visual swap hook. The default swaps the mesh between ReadyMesh and DepletedMesh (or hides it).
	 * Override in a Blueprint for particles, crumble animations, falling trees.
	 */
	UFUNCTION(BlueprintNativeEvent, Category = "Lyris|Resource")
	void UpdateVisuals(bool bIsDepleted);

	/** Pulls the data row, applies visuals. */
	void ResolveData();

	/** Rolls and hands out yields. Returns false (giving nothing) if they wouldn't all fit. */
	bool GiveYields(AActor* Gatherer);

	void SetDepleted(const FDateTime& AtUtc);
	void ScheduleRespawnCheck();
	void CheckRespawn();

	UFUNCTION()
	void OnRep_State();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(Transient)
	FLyrisResourceNodeData Data;

	UPROPERTY(VisibleInstanceOnly, ReplicatedUsing = OnRep_State, Category = "Lyris|Resource")
	int32 HitsTaken = 0;

	UPROPERTY(VisibleInstanceOnly, ReplicatedUsing = OnRep_State, Category = "Lyris|Resource")
	bool bDepleted = false;

	/** FDateTime ticks (UTC) of when it was gathered. int64 so it replicates and saves trivially. */
	UPROPERTY(VisibleInstanceOnly, Replicated, Category = "Lyris|Resource")
	int64 DepletedAtUtcTicks = 0;

	FTimerHandle RespawnTimer;
};
