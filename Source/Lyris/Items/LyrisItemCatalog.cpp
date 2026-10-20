// Lyris items: a small built-in set of starter items, defined in code so the prototype needs no assets.

#include "LyrisItemCatalog.h"

#define LOCTEXT_NAMESPACE "LyrisItemCatalog"

namespace LyrisItemCatalog
{
	const FName Tool_Pickaxe(TEXT("Pickaxe"));
	const FName Tool_Axe(TEXT("Axe"));
	const FName Tool_WateringCan(TEXT("WateringCan"));
	const FName Tool_Hoe(TEXT("Hoe"));

	static FLyrisItemRow MakeRow(const FText& Name, const FText& Description, ELyrisItemCategory Category,
		int32 MaxStack = 99, ELyrisItemRarity Rarity = ELyrisItemRarity::Common, FName ToolType = NAME_None)
	{
		FLyrisItemRow Row;
		Row.DisplayName = Name;
		Row.Description = Description;
		Row.Category = Category;
		Row.MaxStack = MaxStack;
		Row.Rarity = Rarity;
		Row.ToolType = ToolType;
		return Row;
	}

	const TMap<FName, FLyrisItemRow>& GetBuiltInItems()
	{
		static const TMap<FName, FLyrisItemRow> Items = []()
		{
			TMap<FName, FLyrisItemRow> Map;
			using C = ELyrisItemCategory;
			using R = ELyrisItemRarity;

			// Tools
			Map.Add(TEXT("tool_pickaxe"), MakeRow(LOCTEXT("Pickaxe", "Pickaxe"),
				LOCTEXT("PickaxeDesc", "For rocks, ore veins and crystal."), C::Tool, 1, R::Common, Tool_Pickaxe));
			Map.Add(TEXT("tool_axe"), MakeRow(LOCTEXT("Axe", "Axe"),
				LOCTEXT("AxeDesc", "For trees and driftwood."), C::Tool, 1, R::Common, Tool_Axe));
			Map.Add(TEXT("tool_watering_can"), MakeRow(LOCTEXT("WateringCan", "Watering Can"),
				LOCTEXT("WateringCanDesc", "Water helps a plant along. It never needs it."), C::Tool, 1, R::Common, Tool_WateringCan));
			Map.Add(TEXT("tool_hoe"), MakeRow(LOCTEXT("Hoe", "Hoe"),
				LOCTEXT("HoeDesc", "Turns a patch of ground into soil ready for seeds."), C::Tool, 1, R::Common, Tool_Hoe));

			// Materials from gathering
			Map.Add(TEXT("stone"), MakeRow(LOCTEXT("Stone", "Stone"),
				LOCTEXT("StoneDesc", "Plain island stone."), C::Material));
			Map.Add(TEXT("copper_ore"), MakeRow(LOCTEXT("CopperOre", "Copper Ore"),
				LOCTEXT("CopperOreDesc", "Green-streaked ore from the harbor cliffs."), C::Material));
			Map.Add(TEXT("star_crystal"), MakeRow(LOCTEXT("StarCrystal", "Star Crystal Shard"),
				LOCTEXT("StarCrystalDesc", "It hums faintly, like the song under the sea."), C::Material, 99, R::Uncommon));
			Map.Add(TEXT("wood"), MakeRow(LOCTEXT("Wood", "Wood"),
				LOCTEXT("WoodDesc", "Good, dry timber."), C::Material));
			Map.Add(TEXT("sea_herb"), MakeRow(LOCTEXT("SeaHerb", "Sea Herb"),
				LOCTEXT("SeaHerbDesc", "A salty, fragrant herb that grows near the shore."), C::Food));

			// Seeds and crops
			Map.Add(TEXT("seed_moonbell"), MakeRow(LOCTEXT("MoonbellSeed", "Moonbell Seed"),
				LOCTEXT("MoonbellSeedDesc", "Plant it in a farm plot."), C::Seed));
			Map.Add(TEXT("moonbell"), MakeRow(LOCTEXT("Moonbell", "Moonbell"),
				LOCTEXT("MoonbellDesc", "A pale bell-shaped flower that glows softly after dusk."), C::Collectible));
			Map.Add(TEXT("seed_mistberry"), MakeRow(LOCTEXT("MistberrySeed", "Mistberry Seeds"),
				LOCTEXT("MistberrySeedDesc", "Plant them in tilled soil. The bush keeps fruiting after harvest."), C::Seed));
			Map.Add(TEXT("mistberry"), MakeRow(LOCTEXT("Mistberry", "Mistberry"),
				LOCTEXT("MistberryDesc", "A cool, silvery berry that tastes faintly of rain."), C::Food));
			Map.Add(TEXT("seed_harbor_turnip"), MakeRow(LOCTEXT("TurnipSeed", "Harbor Turnip Seed"),
				LOCTEXT("TurnipSeedDesc", "Plant it in a farm plot."), C::Seed));
			Map.Add(TEXT("harbor_turnip"), MakeRow(LOCTEXT("Turnip", "Harbor Turnip"),
				LOCTEXT("TurnipDesc", "Crisp and a little sweet."), C::Food));

			return Map;
		}();
		return Items;
	}
}

#undef LOCTEXT_NAMESPACE
