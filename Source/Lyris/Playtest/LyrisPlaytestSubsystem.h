// Lyris playtest kit. TEST BRANCH ONLY: never merge this folder to main.
//
// Stands in for the hand-off tasks that aren't built yet, so the work in flight can be played:
//   - T14 (Player): gives the walking character an inventory, an interaction component, a
//     starter kit and keys.
//   - T15 / C3 (Environment): spawns a farm plot, resource nodes and the combat training ground
//     near where you start, unless the map already has them.
//   - T16 (UI): an on-screen readout of the interaction prompt (the bag has its own screen now).
// It also speeds up real-time timers (crops, watering, node refills) so a test takes minutes.
//
// Console: lyris.Playtest 0 turns it all off; lyris.Playtest.Fast 0 keeps real-world timings.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "LyrisPlaytestSubsystem.generated.h"

class ACharacter;
class APlayerController;
class ALyrisFarmPlot;
class ULyrisInteractionComponent;
class ULyrisInventoryComponent;
class UCanvas;

UCLASS()
class LYRIS_API ULyrisPlaytestSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

protected:
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:
	void SpeedUpCrops();
	void SetUpCharacter(ACharacter* Character);
	void SpawnSamples(ACharacter* Character);
	void HandleInput(APlayerController* PC, ACharacter* Character);
	void DrawReadout(UCanvas* Canvas, APlayerController* PC);

	/** Finds walkable ground near Location (within MaxRise of BaseZ). */
	bool FindGround(const FVector& Location, float BaseZ, float MaxRise, FVector& OutGround, const AActor* Ignore) const;

	TWeakObjectPtr<ACharacter> SetUpFor;
	TWeakObjectPtr<ULyrisInteractionComponent> Interaction;
	TWeakObjectPtr<ULyrisInventoryComponent> Inventory;
	TWeakObjectPtr<ALyrisFarmPlot> HighlightedPlot;

	FDelegateHandle DrawHandle;
	bool bCropsSpedUp = false;
	bool bSpawnedSamples = false;
};
