// Lyris harvest: data describing a kind of resource node (a rock, an ore vein, a tree, a herb patch).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataTable.h"
#include "Items/LyrisItemTypes.h"
#include "LyrisResourceNodeTypes.generated.h"

class UStaticMesh;

/** Broad family of a node. Used for sounds, animations and journal entries, not for behaviour. */
UENUM(BlueprintType)
enum class ELyrisResourceKind : uint8
{
	Rock,
	Ore,
	Crystal,
	Tree,
	Forage
};

/**
 * Everything that makes a copper vein different from a tree. A DataTable row: the row name is
 * the node type id (e.g. "copper_vein"). New kinds of node are new rows, not new classes.
 */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisResourceNodeData : public FTableRowBase
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Node")
	FText DisplayName;

	/** Verb for the prompt: "Mine", "Chop", "Gather". */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Node")
	FText Verb;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Node")
	ELyrisResourceKind Kind = ELyrisResourceKind::Rock;

	/** Tool type the player must carry, e.g. "Pickaxe" or "Axe" (see LyrisItemCatalog). None = bare hands. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Node")
	FName RequiredToolType;

	/** Interactions needed to gather. Progress is never lost if you walk away halfway. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Node", meta = (ClampMin = "1"))
	int32 HitsToGather = 1;

	/** Everything handed out when the node is gathered. Each entry rolls on its own. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Node")
	TArray<FLyrisItemYield> Yields;

	/** Real-world hours until a gathered node is full again. Keeps counting while nobody is playing. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Node", meta = (ClampMin = "0"))
	float RespawnHours = 6.f;

	/** Mesh while the node can be gathered. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Visual")
	TSoftObjectPtr<UStaticMesh> ReadyMesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Visual")
	FVector ReadyMeshScale = FVector::OneVector;

	/** Mesh once gathered (a stump, rubble). None = hide the node until it refills. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Visual")
	TSoftObjectPtr<UStaticMesh> DepletedMesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Visual")
	FVector DepletedMeshScale = FVector::OneVector;
};

/**
 * Built-in node types so the prototype works without any assets. A row with the same name in a
 * node's NodeTable overrides these. Ids: "rock", "copper_vein", "star_crystal", "tree", "sea_herb".
 */
namespace LyrisResourceCatalog
{
	LYRIS_API const FLyrisResourceNodeData* FindBuiltIn(FName NodeType);
	LYRIS_API TArray<FName> GetBuiltInIds();
}
