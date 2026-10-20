// Lyris harvest: a rock, ore vein, crystal, tree or herb patch the player gathers from.

#include "LyrisResourceNode.h"

#include "Lyris.h"
#include "Items/LyrisInventoryComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/DataTable.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"

#define LOCTEXT_NAMESPACE "LyrisResourceNode"

namespace LyrisResourceNode
{
	/** Re-check at least this often, so a long respawn still lands on time if the game clock was paused. */
	static constexpr float MaxCheckInterval = 60.f;
}

ALyrisResourceNode::ALyrisResourceNode()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
	RootComponent = Mesh;
}

void ALyrisResourceNode::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ResolveData();
}

void ALyrisResourceNode::BeginPlay()
{
	Super::BeginPlay();
	ResolveData();

	if (bDepleted)
	{
		CheckRespawn();
	}
}

void ALyrisResourceNode::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ALyrisResourceNode, HitsTaken);
	DOREPLIFETIME(ALyrisResourceNode, bDepleted);
	DOREPLIFETIME(ALyrisResourceNode, DepletedAtUtcTicks);
}

void ALyrisResourceNode::ResolveData()
{
	const FLyrisResourceNodeData* Found = nullptr;
	if (bUseCustomData)
	{
		Found = &CustomData;
	}
	else
	{
		if (NodeTable && NodeTable->GetRowStruct() == FLyrisResourceNodeData::StaticStruct())
		{
			Found = NodeTable->FindRow<FLyrisResourceNodeData>(NodeType, TEXT("ALyrisResourceNode"), false);
		}
		if (!Found)
		{
			Found = LyrisResourceCatalog::FindBuiltIn(NodeType);
		}
	}

	if (Found)
	{
		Data = *Found;
	}
	else
	{
		UE_LOG(LogLyris, Warning, TEXT("%s: no resource node data for type '%s'"), *GetName(), *NodeType.ToString());
		Data = FLyrisResourceNodeData();
	}
	Data.HitsToGather = FMath::Max(1, Data.HitsToGather);

	UpdateVisuals(bDepleted);
}

void ALyrisResourceNode::UpdateVisuals_Implementation(bool bIsDepleted)
{
	if (!Mesh)
	{
		return;
	}

	const TSoftObjectPtr<UStaticMesh>& Wanted = bIsDepleted ? Data.DepletedMesh : Data.ReadyMesh;
	UStaticMesh* NewMesh = Wanted.IsNull() ? nullptr : Wanted.LoadSynchronous();

	if (bIsDepleted && !NewMesh)
	{
		// Nothing to show: hide and let the player walk through until it refills.
		Mesh->SetVisibility(false);
		Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		return;
	}

	Mesh->SetStaticMesh(NewMesh);
	Mesh->SetRelativeScale3D(bIsDepleted ? Data.DepletedMeshScale : Data.ReadyMeshScale);
	Mesh->SetVisibility(true);
	Mesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
}

bool ALyrisResourceNode::CanInteract_Implementation(AActor* InteractingActor) const
{
	if (bDepleted)
	{
		return false;
	}
	// Always show the prompt for a ready node, even without the tool, so the player learns
	// what's needed ("Needs a Pickaxe"). Interact itself checks the tool.
	return true;
}

FText ALyrisResourceNode::GetInteractPrompt_Implementation(AActor* InteractingActor) const
{
	const ULyrisInventoryComponent* Inventory = ULyrisInventoryComponent::FindInventory(InteractingActor);
	if (!Data.RequiredToolType.IsNone() && (!Inventory || !Inventory->HasTool(Data.RequiredToolType)))
	{
		return FText::Format(LOCTEXT("NeedsTool", "{0}: needs a {1}"), Data.DisplayName, FText::FromName(Data.RequiredToolType));
	}

	const FText Verb = Data.Verb.IsEmpty() ? LOCTEXT("DefaultVerb", "Gather") : Data.Verb;
	if (Data.HitsToGather > 1 && HitsTaken > 0)
	{
		return FText::Format(LOCTEXT("PromptProgress", "{0} {1} ({2}/{3})"), Verb, Data.DisplayName, HitsTaken, Data.HitsToGather);
	}
	return FText::Format(LOCTEXT("Prompt", "{0} {1}"), Verb, Data.DisplayName);
}

void ALyrisResourceNode::Interact_Implementation(AActor* InteractingActor)
{
	if (bDepleted || !HasAuthority())
	{
		return;
	}

	ULyrisInventoryComponent* Inventory = ULyrisInventoryComponent::FindInventory(InteractingActor);
	if (!Inventory)
	{
		return;
	}
	if (!Inventory->HasTool(Data.RequiredToolType))
	{
		return;
	}

	if (HitsTaken + 1 < Data.HitsToGather)
	{
		++HitsTaken;
		OnHit.Broadcast(this, GetHitsRemaining());
		return;
	}

	// Last hit. Nothing is ever lost to a full bag: if the yield doesn't fit, the node stays
	// full (keeping its progress) until the player makes room.
	if (!GiveYields(InteractingActor))
	{
		OnBagFull.Broadcast(this);
		return;
	}
	SetDepleted(FDateTime::UtcNow());
}

bool ALyrisResourceNode::GiveYields(AActor* Gatherer)
{
	ULyrisInventoryComponent* Inventory = ULyrisInventoryComponent::FindInventory(Gatherer);
	if (!Inventory)
	{
		return false;
	}

	TArray<FLyrisItemStack> Rolled;
	for (const FLyrisItemYield& Yield : Data.Yields)
	{
		const int32 Count = Yield.Roll();
		if (Count > 0)
		{
			Rolled.Emplace(Yield.ItemId, Count);
		}
	}
	return Inventory->AddAll(Rolled);
}

void ALyrisResourceNode::SetDepleted(const FDateTime& AtUtc)
{
	bDepleted = true;
	HitsTaken = 0;
	DepletedAtUtcTicks = AtUtc.GetTicks();
	UpdateVisuals(true);
	OnGathered.Broadcast(this);
	ScheduleRespawnCheck();
}

FDateTime ALyrisResourceNode::GetRespawnAtUtc() const
{
	return FDateTime(DepletedAtUtcTicks) + FTimespan::FromHours(FMath::Max(0.f, Data.RespawnHours));
}

float ALyrisResourceNode::GetSecondsUntilRespawn() const
{
	if (!bDepleted)
	{
		return 0.f;
	}
	return FMath::Max(0.f, static_cast<float>((GetRespawnAtUtc() - FDateTime::UtcNow()).GetTotalSeconds()));
}

void ALyrisResourceNode::ScheduleRespawnCheck()
{
	UWorld* World = GetWorld();
	if (!World || !bDepleted || !HasAuthority())
	{
		return;
	}
	const float Delay = FMath::Clamp(GetSecondsUntilRespawn(), 0.5f, LyrisResourceNode::MaxCheckInterval);
	World->GetTimerManager().SetTimer(RespawnTimer, this, &ALyrisResourceNode::CheckRespawn, Delay, false);
}

void ALyrisResourceNode::CheckRespawn()
{
	if (!bDepleted)
	{
		return;
	}
	if (FDateTime::UtcNow() >= GetRespawnAtUtc())
	{
		Replenish();
	}
	else
	{
		ScheduleRespawnCheck();
	}
}

void ALyrisResourceNode::Replenish()
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(RespawnTimer);
	}
	const bool bWasDepleted = bDepleted;
	bDepleted = false;
	HitsTaken = 0;
	DepletedAtUtcTicks = 0;
	UpdateVisuals(false);
	if (bWasDepleted)
	{
		OnReplenished.Broadcast(this);
	}
}

void ALyrisResourceNode::RestoreDepleted(FDateTime DepletedAtUtc)
{
	bDepleted = true;
	HitsTaken = 0;
	DepletedAtUtcTicks = DepletedAtUtc.GetTicks();
	UpdateVisuals(true);
	CheckRespawn();
}

void ALyrisResourceNode::OnRep_State()
{
	UpdateVisuals(bDepleted);
}

#undef LOCTEXT_NAMESPACE
