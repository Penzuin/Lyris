// Lyris world: tuning for the one shared sea state.

#include "World/LyrisOceanSettings.h"

#include "Materials/MaterialParameterCollection.h"

ULyrisOceanSettings::ULyrisOceanSettings()
{
	CategoryName = TEXT("Game");
	SectionName = TEXT("Lyris Ocean");

	// Default waves from the ocean contract: a calm storybook swell. One long roll, three smaller crossing waves.
	Waves[0] = FLyrisOceanWave(30.f, 6000.f, 45.f, 0.35f);
	Waves[1] = FLyrisOceanWave(75.f, 3100.f, 22.f, 0.30f);
	Waves[2] = FLyrisOceanWave(-20.f, 1700.f, 10.f, 0.25f);
	Waves[3] = FLyrisOceanWave(120.f, 900.f, 4.f, 0.20f);

	// The home harbor at the world origin is always calm.
	HomeCalmZones.Add(FLyrisCalmZone(FVector2D(0.f, 0.f), 6000.f, 4000.f));

	SeaParameterCollection = TSoftObjectPtr<UMaterialParameterCollection>(FSoftObjectPath(TEXT("/Game/Lyris/Materials/MPC_Sea.MPC_Sea")));
}

void ULyrisOceanSettings::PostReloadConfig(FProperty* PropertyThatWasLoaded)
{
	Super::PostReloadConfig(PropertyThatWasLoaded);
	++Revision;
}

#if WITH_EDITOR
void ULyrisOceanSettings::PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent)
{
	Super::PostEditChangeProperty(PropertyChangedEvent);
	++Revision;
}
#endif
