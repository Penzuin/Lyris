// Lyris items: a bag of item stacks.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "LyrisItemTypes.h"
#include "LyrisInventoryComponent.generated.h"

class ULyrisItemDefinition;

/** One stack in an inventory. ItemId is the source of truth; Definition is a resolved cache. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisInventorySlot
{
	GENERATED_BODY()

	/** Which item, by id. This is what saves and replication carry. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Inventory")
	FName ItemId;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Inventory")
	int32 Count = 0;

	/** Stacks only merge with the same item at the same quality. Most items stay Normal. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Inventory")
	ELyrisItemQuality Quality = ELyrisItemQuality::Normal;

	/** Looked up from ItemId through ULyrisItemRegistry. Not replicated: each machine resolves its own. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, NotReplicated, Transient, Category = "Inventory")
	TObjectPtr<ULyrisItemDefinition> Definition = nullptr;

	bool IsEmpty() const { return ItemId.IsNone() || Count <= 0; }
};

/** A plain "this many of this item at this quality", for handing out several items at once. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisItemStack
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Inventory")
	FName ItemId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Inventory")
	int32 Count = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Inventory")
	ELyrisItemQuality Quality = ELyrisItemQuality::Normal;

	FLyrisItemStack() = default;
	FLyrisItemStack(FName InItemId, int32 InCount, ELyrisItemQuality InQuality = ELyrisItemQuality::Normal)
		: ItemId(InItemId), Count(InCount), Quality(InQuality) {}
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FLyrisInventoryChanged);

/**
 * A fixed number of slots, each holding a stack of one item up to its MaxStack.
 *
 * Put it on the player (Player lane, T14). Gathering nodes and farm plots look for it on the
 * interacting actor. The Collecting lane will build sets, the collection book and the museum on
 * top of this; keep this class about stacks only.
 *
 * Calm by default: AddItem never destroys anything silently. It returns what didn't fit so the
 * caller can leave it in the world instead.
 *
 * Multiplayer later: Slots is already marked Replicated (owner only) and holds ids, not object
 * pointers, so it can replicate as-is. Mutations should then happen only on the server.
 */
UCLASS(ClassGroup = (Lyris), meta = (BlueprintSpawnableComponent))
class LYRIS_API ULyrisInventoryComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	ULyrisInventoryComponent();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Number of slots. Changing it at runtime is not supported yet. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Lyris|Inventory", meta = (ClampMin = "1"))
	int32 SlotCount = 24;

	/** Fires after any change to the contents. */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Inventory")
	FLyrisInventoryChanged OnInventoryChanged;

	/** Adds up to Count of Item, topping up existing stacks first. Returns how many did NOT fit (0 = all added). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Inventory")
	int32 AddItem(ULyrisItemDefinition* Item, int32 Count = 1, ELyrisItemQuality Quality = ELyrisItemQuality::Normal);

	/** AddItem by id, resolving through ULyrisItemRegistry. Returns how many did NOT fit. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Inventory")
	int32 AddItemById(FName ItemId, int32 Count = 1, ELyrisItemQuality Quality = ELyrisItemQuality::Normal);

	/** How many of Count would fit right now, without changing anything. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Inventory")
	int32 GetRoomFor(ULyrisItemDefinition* Item, int32 Count = 1, ELyrisItemQuality Quality = ELyrisItemQuality::Normal) const;

	/**
	 * Would all of these fit at once (they compete for the same empty slots)? Lets world actors
	 * check before handing out several items, so nothing is ever lost to a full bag: the node or
	 * crop simply waits until there's room.
	 */
	bool CanAddAll(const TArray<FLyrisItemStack>& Items) const;

	/** Adds every stack. Returns false (and adds nothing) if CanAddAll is false. */
	bool AddAll(const TArray<FLyrisItemStack>& Items);

	/**
	 * Removes Count of Item, of any quality (lowest quality first, so seeds and materials used as
	 * ingredients never eat your best produce). All or nothing: returns false and changes nothing
	 * if there aren't enough. Counts below also ignore quality.
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Inventory")
	bool RemoveItem(ULyrisItemDefinition* Item, int32 Count = 1);

	UFUNCTION(BlueprintCallable, Category = "Lyris|Inventory")
	bool RemoveItemById(FName ItemId, int32 Count = 1);

	UFUNCTION(BlueprintPure, Category = "Lyris|Inventory")
	int32 CountOf(ULyrisItemDefinition* Item) const;

	UFUNCTION(BlueprintPure, Category = "Lyris|Inventory")
	int32 CountOfId(FName ItemId) const;

	/** True if any carried item is a tool of this type (e.g. "Pickaxe"). None always returns true. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Inventory")
	bool HasTool(FName ToolType) const;

	/** All slots, including empty ones, in order. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Inventory")
	TArray<FLyrisInventorySlot> GetSlots() const { return Slots; }

	/** First carried item of a category, e.g. the first seed. Null if none. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Inventory")
	ULyrisItemDefinition* FindFirstOfCategory(ELyrisItemCategory Category) const;

	/**
	 * The slot the player has selected on a hotbar (-1 = none). World interactions use it to pick
	 * which seed to plant when several are carried; they fall back to the first matching item.
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Inventory")
	void SetActiveSlot(int32 SlotIndex);

	UFUNCTION(BlueprintPure, Category = "Lyris|Inventory")
	int32 GetActiveSlot() const { return ActiveSlot; }

	/** Item in the active slot, or null. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Inventory")
	ULyrisItemDefinition* GetActiveItem() const;

	/**
	 * Moves the stack in From onto To (inventory screens, T16): into an empty slot it moves; onto
	 * the same item at the same quality it merges up to the stack limit (the rest stays in From);
	 * onto anything else the two swap. Nothing is ever lost. The active hotbar slot keeps its
	 * index. Returns false if nothing changed.
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Inventory")
	bool MoveSlot(int32 From, int32 To);

	/** Finds the inventory on an actor (or its controller's pawn / the pawn's controller). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Inventory")
	static ULyrisInventoryComponent* FindInventory(const AActor* Actor);

protected:
	virtual void BeginPlay() override;

	UFUNCTION()
	void OnRep_Slots();

private:
	ULyrisItemDefinition* ResolveDefinition(FLyrisInventorySlot& Slot) const;
	ULyrisItemDefinition* ResolveId(FName ItemId) const;
	void EnsureSlotCount();

	UPROPERTY(VisibleAnywhere, ReplicatedUsing = OnRep_Slots, Category = "Lyris|Inventory")
	TArray<FLyrisInventorySlot> Slots;

	UPROPERTY(VisibleAnywhere, Replicated, Category = "Lyris|Inventory")
	int32 ActiveSlot = INDEX_NONE;
};
