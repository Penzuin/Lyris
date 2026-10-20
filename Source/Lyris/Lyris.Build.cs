// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class Lyris : ModuleRules
{
	public Lyris(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] {
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"AIModule",
			"StateTreeModule",
			"GameplayStateTreeModule",
			"UMG",
			"Slate"
		});

		PrivateDependencyModuleNames.AddRange(new string[] { });

		PublicIncludePaths.AddRange(new string[] {
			"Lyris",
			"Lyris/Variant_Platforming",
			"Lyris/Variant_Platforming/Animation",
			"Lyris/Variant_Combat",
			"Lyris/Variant_Combat/AI",
			"Lyris/Variant_Combat/Animation",
			"Lyris/Variant_Combat/Gameplay",
			"Lyris/Variant_Combat/Interfaces",
			"Lyris/Variant_Combat/UI",
			"Lyris/Variant_SideScrolling",
			"Lyris/Variant_SideScrolling/AI",
			"Lyris/Variant_SideScrolling/Gameplay",
			"Lyris/Variant_SideScrolling/Interfaces",
			"Lyris/Variant_SideScrolling/UI"
		});

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });

		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
