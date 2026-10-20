// Lyris harvest: data describing a kind of resource node (a rock, an ore vein, a tree, a herb patch).

#include "LyrisResourceNodeTypes.h"

#include "Items/LyrisItemCatalog.h"
#include "Engine/StaticMesh.h"

#define LOCTEXT_NAMESPACE "LyrisResourceCatalog"

namespace LyrisResourceCatalog
{
	// Placeholder engine shapes until the Environment lane provides real meshes.
	static const TCHAR* SphereMesh = TEXT("/Engine/BasicShapes/Sphere.Sphere");
	static const TCHAR* ConeMesh = TEXT("/Engine/BasicShapes/Cone.Cone");
	static const TCHAR* CylinderMesh = TEXT("/Engine/BasicShapes/Cylinder.Cylinder");

	static FLyrisResourceNodeData MakeNode(const FText& Name, const FText& Verb, ELyrisResourceKind Kind, FName Tool,
		int32 Hits, float RespawnHours, TArray<FLyrisItemYield> Yields, const TCHAR* Mesh, FVector Scale)
	{
		FLyrisResourceNodeData Data;
		Data.DisplayName = Name;
		Data.Verb = Verb;
		Data.Kind = Kind;
		Data.RequiredToolType = Tool;
		Data.HitsToGather = Hits;
		Data.RespawnHours = RespawnHours;
		Data.Yields = MoveTemp(Yields);
		Data.ReadyMesh = TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(Mesh));
		Data.ReadyMeshScale = Scale;
		return Data;
	}

	static const TMap<FName, FLyrisResourceNodeData>& GetAll()
	{
		static const TMap<FName, FLyrisResourceNodeData> Nodes = []()
		{
			TMap<FName, FLyrisResourceNodeData> Map;
			using K = ELyrisResourceKind;
			const FText Mine = LOCTEXT("Mine", "Mine");

			Map.Add(TEXT("rock"), MakeNode(LOCTEXT("Rock", "Rock"), Mine, K::Rock, LyrisItemCatalog::Tool_Pickaxe, 3, 4.f,
				{ FLyrisItemYield(TEXT("stone"), 2, 4), FLyrisItemYield(TEXT("copper_ore"), 1, 1, 0.15f) },
				SphereMesh, FVector(1.2f, 1.f, 0.7f)));

			Map.Add(TEXT("copper_vein"), MakeNode(LOCTEXT("CopperVein", "Copper Vein"), Mine, K::Ore, LyrisItemCatalog::Tool_Pickaxe, 4, 8.f,
				{ FLyrisItemYield(TEXT("copper_ore"), 1, 3), FLyrisItemYield(TEXT("stone"), 1, 2) },
				SphereMesh, FVector(1.4f, 1.2f, 0.9f)));

			Map.Add(TEXT("star_crystal"), MakeNode(LOCTEXT("StarCrystal", "Star Crystal"), Mine, K::Crystal, LyrisItemCatalog::Tool_Pickaxe, 5, 24.f,
				{ FLyrisItemYield(TEXT("star_crystal"), 1, 2) },
				ConeMesh, FVector(0.5f, 0.5f, 1.2f)));

			FLyrisResourceNodeData Tree = MakeNode(LOCTEXT("Tree", "Tree"), LOCTEXT("Chop", "Chop"), K::Tree, LyrisItemCatalog::Tool_Axe, 4, 12.f,
				{ FLyrisItemYield(TEXT("wood"), 3, 5) },
				ConeMesh, FVector(1.5f, 1.5f, 4.f));
			Tree.DepletedMesh = TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(CylinderMesh));
			Tree.DepletedMeshScale = FVector(0.6f, 0.6f, 0.3f);
			Map.Add(TEXT("tree"), Tree);

			Map.Add(TEXT("sea_herb"), MakeNode(LOCTEXT("SeaHerb", "Sea Herb"), LOCTEXT("Gather", "Gather"), K::Forage, NAME_None, 1, 6.f,
				{ FLyrisItemYield(TEXT("sea_herb"), 1, 2), FLyrisItemYield(TEXT("seed_moonbell"), 1, 1, 0.2f) },
				SphereMesh, FVector(0.5f, 0.5f, 0.3f)));

			return Map;
		}();
		return Nodes;
	}

	const FLyrisResourceNodeData* FindBuiltIn(FName NodeType)
	{
		return GetAll().Find(NodeType);
	}

	TArray<FName> GetBuiltInIds()
	{
		TArray<FName> Ids;
		GetAll().GetKeys(Ids);
		return Ids;
	}
}

#undef LOCTEXT_NAMESPACE
