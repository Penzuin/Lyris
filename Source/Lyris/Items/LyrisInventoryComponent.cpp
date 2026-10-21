// Lyris items: a bag of item stacks.

#include "LyrisInventoryComponent.h"

#include "LyrisItemDefinition.h"
#include "LyrisItemRegistry.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Controller.h"
#include "GameFramework/Pawn.h"
#include "Net/UnrealNetwork.h"

ULyrisInventoryComponent::ULyrisInventoryComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(true);
}

void ULyrisInventoryComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME_CONDITION(ULyrisInventoryComponent, Slots, COND_OwnerOnly);
	DOREPLIFETIME_CONDITION(ULyrisInventoryComponent, ActiveSlot, COND_OwnerOnly);
}

void ULyrisInventoryComponent::BeginPlay()
{
	Super::BeginPlay();
	EnsureSlotCount();
}

void ULyrisInventoryComponent::EnsureSlotCount()
{
	SlotCount = FMath::Max(1, SlotCount);
	if (Slots.Num() < SlotCount)
	{
		Slots.SetNum(SlotCount);
	}
}

ULyrisItemDefinition* ULyrisInventoryComponent::ResolveId(FName ItemId) const
{
	return ItemId.IsNone() ? nullptr : ULyrisItemRegistry::FindItem(this, ItemId);
}

ULyrisItemDefinition* ULyrisInventoryComponent::ResolveDefinition(FLyrisInventorySlot& Slot) const
{
	if (!Slot.Definition && !Slot.ItemId.IsNone())
	{
		Slot.Definition = ResolveId(Slot.ItemId);
	}
	return Slot.Definition;
}

int32 ULyrisInventoryComponent::GetRoomFor(ULyrisItemDefinition* Item, int32 Count, ELyrisItemQuality Quality) const
{
	if (!Item || Item->ItemId.IsNone() || Count <= 0)
	{
		return 0;
	}

	const int32 MaxStack = FMath::Max(1, Item->MaxStack);
	int32 Room = 0;
	for (int32 Index = 0; Index < SlotCount && Room < Count; ++Index)
	{
		if (!Slots.IsValidIndex(Index) || Slots[Index].IsEmpty())
		{
			Room += MaxStack;
		}
		else if (Slots[Index].ItemId == Item->ItemId && Slots[Index].Quality == Quality)
		{
			Room += FMath::Max(0, MaxStack - Slots[Index].Count);
		}
	}
	return FMath::Min(Room, Count);
}

int32 ULyrisInventoryComponent::AddItem(ULyrisItemDefinition* Item, int32 Count, ELyrisItemQuality Quality)
{
	if (!Item || Item->ItemId.IsNone() || Count <= 0)
	{
		return FMath::Max(0, Count);
	}

	EnsureSlotCount();
	const int32 MaxStack = FMath::Max(1, Item->MaxStack);
	int32 Remaining = Count;

	// Top up stacks of the same item first.
	for (FLyrisInventorySlot& Slot : Slots)
	{
		if (Remaining <= 0)
		{
			break;
		}
		if (!Slot.IsEmpty() && Slot.ItemId == Item->ItemId && Slot.Quality == Quality && Slot.Count < MaxStack)
		{
			const int32 Moved = FMath::Min(Remaining, MaxStack - Slot.Count);
			Slot.Count += Moved;
			Slot.Definition = Item;
			Remaining -= Moved;
		}
	}

	// Then fill empty slots.
	for (FLyrisInventorySlot& Slot : Slots)
	{
		if (Remaining <= 0)
		{
			break;
		}
		if (Slot.IsEmpty())
		{
			const int32 Moved = FMath::Min(Remaining, MaxStack);
			Slot.ItemId = Item->ItemId;
			Slot.Quality = Quality;
			Slot.Definition = Item;
			Slot.Count = Moved;
			Remaining -= Moved;
		}
	}

	if (Remaining != Count)
	{
		OnInventoryChanged.Broadcast();
	}
	return Remaining;
}

int32 ULyrisInventoryComponent::AddItemById(FName ItemId, int32 Count, ELyrisItemQuality Quality)
{
	ULyrisItemDefinition* Item = ResolveId(ItemId);
	return Item ? AddItem(Item, Count, Quality) : FMath::Max(0, Count);
}

bool ULyrisInventoryComponent::CanAddAll(const TArray<FLyrisItemStack>& Items) const
{
	// Simulate on a copy of the slots so stacks competing for the same empty slot are counted once.
	TArray<FLyrisInventorySlot> Sim = Slots;
	if (Sim.Num() < SlotCount)
	{
		Sim.SetNum(SlotCount);
	}

	for (const FLyrisItemStack& Stack : Items)
	{
		if (Stack.Count <= 0)
		{
			continue;
		}
		const ULyrisItemDefinition* Item = ResolveId(Stack.ItemId);
		if (!Item)
		{
			return false;
		}
		const int32 MaxStack = FMath::Max(1, Item->MaxStack);
		int32 Remaining = Stack.Count;

		for (FLyrisInventorySlot& Slot : Sim)
		{
			if (Remaining > 0 && !Slot.IsEmpty() && Slot.ItemId == Stack.ItemId && Slot.Quality == Stack.Quality && Slot.Count < MaxStack)
			{
				const int32 Moved = FMath::Min(Remaining, MaxStack - Slot.Count);
				Slot.Count += Moved;
				Remaining -= Moved;
			}
		}
		for (FLyrisInventorySlot& Slot : Sim)
		{
			if (Remaining > 0 && Slot.IsEmpty())
			{
				const int32 Moved = FMath::Min(Remaining, MaxStack);
				Slot.ItemId = Stack.ItemId;
				Slot.Quality = Stack.Quality;
				Slot.Count = Moved;
				Remaining -= Moved;
			}
		}
		if (Remaining > 0)
		{
			return false;
		}
	}
	return true;
}

bool ULyrisInventoryComponent::AddAll(const TArray<FLyrisItemStack>& Items)
{
	if (!CanAddAll(Items))
	{
		return false;
	}
	for (const FLyrisItemStack& Stack : Items)
	{
		if (Stack.Count > 0)
		{
			AddItemById(Stack.ItemId, Stack.Count, Stack.Quality);
		}
	}
	return true;
}

bool ULyrisInventoryComponent::RemoveItem(ULyrisItemDefinition* Item, int32 Count)
{
	return Item ? RemoveItemById(Item->ItemId, Count) : false;
}

bool ULyrisInventoryComponent::RemoveItemById(FName ItemId, int32 Count)
{
	if (ItemId.IsNone() || Count <= 0 || CountOfId(ItemId) < Count)
	{
		return false;
	}

	// Lowest quality first; within a quality, the last stacks first so the first slot keeps its place.
	int32 Remaining = Count;
	for (uint8 Q = static_cast<uint8>(ELyrisItemQuality::Normal); Q <= static_cast<uint8>(ELyrisItemQuality::Radiant) && Remaining > 0; ++Q)
	{
		const ELyrisItemQuality Quality = static_cast<ELyrisItemQuality>(Q);
		for (int32 Index = Slots.Num() - 1; Index >= 0 && Remaining > 0; --Index)
		{
			FLyrisInventorySlot& Slot = Slots[Index];
			if (Slot.IsEmpty() || Slot.ItemId != ItemId || Slot.Quality != Quality)
			{
				continue;
			}
			const int32 Taken = FMath::Min(Remaining, Slot.Count);
			Slot.Count -= Taken;
			Remaining -= Taken;
			if (Slot.Count <= 0)
			{
				Slot = FLyrisInventorySlot();
			}
		}
	}

	OnInventoryChanged.Broadcast();
	return true;
}

int32 ULyrisInventoryComponent::CountOf(ULyrisItemDefinition* Item) const
{
	return Item ? CountOfId(Item->ItemId) : 0;
}

int32 ULyrisInventoryComponent::CountOfId(FName ItemId) const
{
	if (ItemId.IsNone())
	{
		return 0;
	}
	int32 Total = 0;
	for (const FLyrisInventorySlot& Slot : Slots)
	{
		if (!Slot.IsEmpty() && Slot.ItemId == ItemId)
		{
			Total += Slot.Count;
		}
	}
	return Total;
}

bool ULyrisInventoryComponent::HasTool(FName ToolType) const
{
	if (ToolType.IsNone())
	{
		return true;
	}
	for (const FLyrisInventorySlot& Slot : Slots)
	{
		if (Slot.IsEmpty())
		{
			continue;
		}
		const ULyrisItemDefinition* Definition = Slot.Definition ? Slot.Definition.Get() : ResolveId(Slot.ItemId);
		if (Definition && Definition->IsTool() && Definition->ToolType == ToolType)
		{
			return true;
		}
	}
	return false;
}

ULyrisItemDefinition* ULyrisInventoryComponent::FindFirstOfCategory(ELyrisItemCategory Category) const
{
	for (const FLyrisInventorySlot& Slot : Slots)
	{
		if (Slot.IsEmpty())
		{
			continue;
		}
		ULyrisItemDefinition* Definition = Slot.Definition ? Slot.Definition.Get() : ResolveId(Slot.ItemId);
		if (Definition && Definition->Category == Category)
		{
			return Definition;
		}
	}
	return nullptr;
}

void ULyrisInventoryComponent::SetActiveSlot(int32 SlotIndex)
{
	const int32 NewSlot = Slots.IsValidIndex(SlotIndex) ? SlotIndex : INDEX_NONE;
	if (NewSlot != ActiveSlot)
	{
		ActiveSlot = NewSlot;
		OnInventoryChanged.Broadcast();
	}
}

bool ULyrisInventoryComponent::MoveSlot(int32 From, int32 To)
{
	EnsureSlotCount();
	if (From == To || !Slots.IsValidIndex(From) || !Slots.IsValidIndex(To) || Slots[From].IsEmpty())
	{
		return false;
	}
	FLyrisInventorySlot& Source = Slots[From];
	FLyrisInventorySlot& Target = Slots[To];
	if (!Target.IsEmpty() && Target.ItemId == Source.ItemId && Target.Quality == Source.Quality)
	{
		const ULyrisItemDefinition* Def = ResolveDefinition(Target);
		const int32 MaxStack = FMath::Max(1, Def ? Def->MaxStack : 99);
		const int32 Moved = FMath::Min(Source.Count, MaxStack - Target.Count);
		if (Moved <= 0)
		{
			Swap(Source, Target);  // the target stack is full: swap instead, so the click still does something
		}
		else
		{
			Target.Count += Moved;
			Source.Count -= Moved;
			if (Source.Count <= 0)
			{
				Source = FLyrisInventorySlot();
			}
		}
	}
	else
	{
		Swap(Source, Target);
	}
	OnInventoryChanged.Broadcast();
	return true;
}

ULyrisItemDefinition* ULyrisInventoryComponent::GetActiveItem() const
{
	if (!Slots.IsValidIndex(ActiveSlot) || Slots[ActiveSlot].IsEmpty())
	{
		return nullptr;
	}
	const FLyrisInventorySlot& Slot = Slots[ActiveSlot];
	return Slot.Definition ? Slot.Definition.Get() : ResolveId(Slot.ItemId);
}

ULyrisInventoryComponent* ULyrisInventoryComponent::FindInventory(const AActor* Actor)
{
	if (!Actor)
	{
		return nullptr;
	}
	if (ULyrisInventoryComponent* Found = Actor->FindComponentByClass<ULyrisInventoryComponent>())
	{
		return Found;
	}
	if (const APawn* Pawn = Cast<APawn>(Actor))
	{
		if (const AController* Controller = Pawn->GetController())
		{
			return Controller->FindComponentByClass<ULyrisInventoryComponent>();
		}
	}
	if (const AController* Controller = Cast<AController>(Actor))
	{
		if (const APawn* Pawn = Controller->GetPawn())
		{
			return Pawn->FindComponentByClass<ULyrisInventoryComponent>();
		}
	}
	return nullptr;
}

void ULyrisInventoryComponent::OnRep_Slots()
{
	for (FLyrisInventorySlot& Slot : Slots)
	{
		Slot.Definition = nullptr;
		ResolveDefinition(Slot);
	}
	OnInventoryChanged.Broadcast();
}
