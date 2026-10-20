// Lyris combat: a training ground where mist crawlers keep climbing out of the ground.
//
// Place one in a map (task C3 does this for the Harbor island). It gives the walking player
// a health and combat component at runtime, so no player code needs to change, and keeps a
// few crawlers coming while the player is near.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "LyrisTrainingGround.generated.h"

class ALyrisMistCrawler;

UCLASS()
class LYRIS_API ALyrisTrainingGround : public AActor
{
	GENERATED_BODY()

public:
	ALyrisTrainingGround();

	virtual void Tick(float DeltaSeconds) override;

	/** Crawlers emerge on a ring this far from the centre. */
	UPROPERTY(EditAnywhere, Category = "Training")
	float SpawnRadius = 650.f;

	/** The ground wakes when the player comes this close. */
	UPROPERTY(EditAnywhere, Category = "Training")
	float WakeRadius = 1800.f;

	UPROPERTY(EditAnywhere, Category = "Training")
	int32 MaxCrawlers = 3;

	/** Seconds before a defeated crawler is replaced. */
	UPROPERTY(EditAnywhere, Category = "Training")
	float RespawnDelay = 5.f;

	/** Where defeat sends the player (the Harbor script sets this to the dock). */
	UPROPERTY(EditAnywhere, Category = "Training")
	FVector RespawnLocation = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, Category = "Training")
	TSubclassOf<ALyrisMistCrawler> CrawlerClass;

private:
	UPROPERTY()
	TArray<TObjectPtr<ALyrisMistCrawler>> Crawlers;

	float UntilNextSpawn = 0.f;

	void EquipPlayer(APawn* Pawn);
	void SpawnCrawler();
};
