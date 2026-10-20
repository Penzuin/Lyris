// Lyris items: the definition of one kind of item (not an instance in a bag).

#include "LyrisItemDefinition.h"

#include "Engine/Texture2D.h"
#include "UObject/Package.h"

const FPrimaryAssetType ULyrisItemDefinition::PrimaryAssetType(TEXT("LyrisItem"));

void ULyrisItemDefinition::InitFromRow(FName InItemId, const FLyrisItemRow& Row)
{
	ItemId = InItemId;
	DisplayName = Row.DisplayName.IsEmpty() ? FText::FromName(InItemId) : Row.DisplayName;
	Description = Row.Description;
	Icon = Row.Icon;
	MaxStack = FMath::Max(1, Row.MaxStack);
	Category = Row.Category;
	Rarity = Row.Rarity;
	ToolType = Row.ToolType;
}

ULyrisItemDefinition* ULyrisItemDefinition::CreateFromRow(UObject* Outer, FName InItemId, const FLyrisItemRow& Row)
{
	ULyrisItemDefinition* Definition = NewObject<ULyrisItemDefinition>(Outer ? Outer : GetTransientPackage(), NAME_None, RF_Transient);
	Definition->InitFromRow(InItemId, Row);
	return Definition;
}

FPrimaryAssetId ULyrisItemDefinition::GetPrimaryAssetId() const
{
	// Name by ItemId when set so ids, not asset names, are what saves and data refer to.
	return FPrimaryAssetId(PrimaryAssetType, ItemId.IsNone() ? GetFName() : ItemId);
}
