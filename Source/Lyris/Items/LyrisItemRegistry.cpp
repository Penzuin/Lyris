// Lyris items: looks up item definitions by id, whether they come from assets, DataTables or code.

#include "LyrisItemRegistry.h"

#include "Lyris.h"
#include "LyrisItemCatalog.h"
#include "LyrisItemDefinition.h"
#include "Engine/DataTable.h"
#include "Engine/GameInstance.h"
#include "Engine/ObjectLibrary.h"
#include "Engine/World.h"

const TCHAR* ULyrisItemRegistry::ItemContentPath = TEXT("/Game/Lyris/Items");

void ULyrisItemRegistry::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	for (const TPair<FName, FLyrisItemRow>& Entry : LyrisItemCatalog::GetBuiltInItems())
	{
		RegisterRow(Entry.Key, Entry.Value);
	}

	LoadContentFolder();

	UE_LOG(LogLyris, Log, TEXT("Item registry: %d items"), Definitions.Num());
}

ULyrisItemRegistry* ULyrisItemRegistry::Get(const UObject* WorldContextObject)
{
	const UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
	return GameInstance ? GameInstance->GetSubsystem<ULyrisItemRegistry>() : nullptr;
}

ULyrisItemDefinition* ULyrisItemRegistry::FindItem(const UObject* WorldContextObject, FName ItemId)
{
	const ULyrisItemRegistry* Registry = Get(WorldContextObject);
	return Registry ? Registry->FindDefinition(ItemId) : nullptr;
}

ULyrisItemDefinition* ULyrisItemRegistry::FindDefinition(FName ItemId) const
{
	const TObjectPtr<ULyrisItemDefinition>* Found = Definitions.Find(ItemId);
	return Found ? Found->Get() : nullptr;
}

void ULyrisItemRegistry::RegisterDefinition(ULyrisItemDefinition* Definition)
{
	if (!Definition)
	{
		return;
	}
	if (Definition->ItemId.IsNone())
	{
		UE_LOG(LogLyris, Warning, TEXT("Item definition %s has no ItemId; skipped"), *GetNameSafe(Definition));
		return;
	}
	Definitions.Add(Definition->ItemId, Definition);
}

int32 ULyrisItemRegistry::RegisterDataTable(UDataTable* Table)
{
	if (!Table || Table->GetRowStruct() != FLyrisItemRow::StaticStruct())
	{
		return 0;
	}

	int32 Added = 0;
	for (const TPair<FName, uint8*>& Pair : Table->GetRowMap())
	{
		if (const FLyrisItemRow* Row = reinterpret_cast<const FLyrisItemRow*>(Pair.Value))
		{
			RegisterRow(Pair.Key, *Row);
			++Added;
		}
	}
	return Added;
}

ULyrisItemDefinition* ULyrisItemRegistry::RegisterRow(FName ItemId, const FLyrisItemRow& Row)
{
	if (ItemId.IsNone())
	{
		return nullptr;
	}
	ULyrisItemDefinition* Definition = ULyrisItemDefinition::CreateFromRow(this, ItemId, Row);
	Definitions.Add(ItemId, Definition);
	return Definition;
}

TArray<ULyrisItemDefinition*> ULyrisItemRegistry::GetAllDefinitions() const
{
	TArray<ULyrisItemDefinition*> Result;
	Result.Reserve(Definitions.Num());
	for (const TPair<FName, TObjectPtr<ULyrisItemDefinition>>& Pair : Definitions)
	{
		Result.Add(Pair.Value.Get());
	}
	return Result;
}

void ULyrisItemRegistry::LoadContentFolder()
{
	// DataTables first, then data assets, so a hand-made asset wins over a table row with the same id.
	UObjectLibrary* TableLibrary = UObjectLibrary::CreateLibrary(UDataTable::StaticClass(), false, GIsEditor);
	TableLibrary->LoadAssetDataFromPath(ItemContentPath);
	TableLibrary->LoadAssetsFromAssetData();
	TArray<UDataTable*> Tables;
	TableLibrary->GetObjects<UDataTable>(Tables);
	for (UDataTable* Table : Tables)
	{
		RegisterDataTable(Table);
	}

	UObjectLibrary* ItemLibrary = UObjectLibrary::CreateLibrary(ULyrisItemDefinition::StaticClass(), false, GIsEditor);
	ItemLibrary->LoadAssetDataFromPath(ItemContentPath);
	ItemLibrary->LoadAssetsFromAssetData();
	TArray<ULyrisItemDefinition*> Assets;
	ItemLibrary->GetObjects<ULyrisItemDefinition>(Assets);
	for (ULyrisItemDefinition* Asset : Assets)
	{
		RegisterDefinition(Asset);
	}
}
