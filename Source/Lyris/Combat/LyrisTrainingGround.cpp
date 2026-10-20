#include "Combat/LyrisTrainingGround.h"

#include "Combat/LyrisCombatComponent.h"
#include "Combat/LyrisHealthComponent.h"
#include "Combat/LyrisMistCrawler.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"

ALyrisTrainingGround::ALyrisTrainingGround()
{
	PrimaryActorTick.bCanEverTick = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	CrawlerClass = ALyrisMistCrawler::StaticClass();
}

void ALyrisTrainingGround::EquipPlayer(APawn* Pawn)
{
	// Only characters (the walker), never the boat.
	if (!Cast<ACharacter>(Pawn) || Pawn->FindComponentByClass<ULyrisCombatComponent>())
	{
		return;
	}
	ULyrisCombatComponent* Combat = NewObject<ULyrisCombatComponent>(Pawn, TEXT("LyrisCombat"));
	Combat->RespawnLocation = RespawnLocation.IsZero() ? Pawn->GetActorLocation() : RespawnLocation;
	Combat->RegisterComponent();  // BeginPlay runs now and adds the health component
}

void ALyrisTrainingGround::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	const APlayerController* PC = GetWorld()->GetFirstPlayerController();
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	if (Pawn)
	{
		EquipPlayer(Pawn);  // again after stepping off the boat (cheap if already equipped)
	}

	Crawlers.RemoveAll([](const TObjectPtr<ALyrisMistCrawler>& Crawler) { return !IsValid(Crawler); });

	const bool bPlayerNear = Pawn && Cast<ACharacter>(Pawn)
		&& FVector::Dist2D(Pawn->GetActorLocation(), GetActorLocation()) < WakeRadius;
	if (!bPlayerNear)
	{
		UntilNextSpawn = FMath::Min(UntilNextSpawn, 1.f);
		return;
	}
	UntilNextSpawn -= DeltaSeconds;
	if (Crawlers.Num() < MaxCrawlers && UntilNextSpawn <= 0.f)
	{
		SpawnCrawler();
		UntilNextSpawn = RespawnDelay;
	}
}

void ALyrisTrainingGround::SpawnCrawler()
{
	UWorld* World = GetWorld();
	const float Angle = FMath::FRandRange(0.f, 2.f * PI);
	const FVector Ring = GetActorLocation() + FVector(FMath::Cos(Angle), FMath::Sin(Angle), 0.f) * SpawnRadius;

	// Find the ground under the spawn point (the island is uneven).
	FHitResult Ground;
	const FVector Start = Ring + FVector(0.f, 0.f, 1500.f);
	const FVector End = Ring - FVector(0.f, 0.f, 3000.f);
	FCollisionQueryParams Params(SCENE_QUERY_STAT(LyrisTrainingGround), false, this);
	FVector Where = Ring;
	if (World->LineTraceSingleByChannel(Ground, Start, End, ECC_Visibility, Params))
	{
		Where = Ground.ImpactPoint + FVector(0.f, 0.f, 50.f);
	}
	if (Where.Z < 5.f)
	{
		return;  // that spot is in the sea; try again next time
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButDontSpawnIfColliding;
	const FRotator Facing(0.f, (GetActorLocation() - Where).Rotation().Yaw, 0.f);
	if (ALyrisMistCrawler* Crawler = World->SpawnActor<ALyrisMistCrawler>(CrawlerClass, Where, Facing, SpawnParams))
	{
		Crawlers.Add(Crawler);
	}
}
