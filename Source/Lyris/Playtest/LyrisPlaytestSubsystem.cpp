// Lyris playtest kit. TEST BRANCH ONLY: never merge this folder to main.

#include "LyrisPlaytestSubsystem.h"

#include "Debug/DebugDrawService.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "InputCoreTypes.h"

#include "Combat/LyrisTrainingGround.h"
#include "Harvest/LyrisCropDefinition.h"
#include "Harvest/LyrisCropRegistry.h"
#include "Harvest/LyrisFarmPlot.h"
#include "Harvest/LyrisResourceNode.h"
#include "Harvest/LyrisResourceNodeTypes.h"
#include "Interaction/LyrisInteractionComponent.h"
#include "Items/LyrisInventoryComponent.h"
#include "Items/LyrisItemDefinition.h"
#include "Items/LyrisItemRegistry.h"

namespace LyrisPlaytest
{
	static TAutoConsoleVariable<int32> CVarEnabled(
		TEXT("lyris.Playtest"), 1,
		TEXT("Playtest kit (test branch only): 1 = give the player tools and spawn samples, 0 = off."));

	static TAutoConsoleVariable<int32> CVarFast(
		TEXT("lyris.Playtest.Fast"), 1,
		TEXT("Playtest kit: 1 = crops, watering and node refills run about 300x faster, 0 = real-world timings."));

	/** Real hours divided by this: a 3 h turnip ripens in 36 s, a 6 h mistberry in 72 s. */
	static constexpr float SpeedUp = 300.f;

	struct FStarterItem { const TCHAR* Id; int32 Count; };
	static const FStarterItem StarterKit[] =
	{
		{ TEXT("tool_hoe"), 1 },
		{ TEXT("tool_watering_can"), 1 },
		{ TEXT("tool_pickaxe"), 1 },
		{ TEXT("tool_axe"), 1 },
		{ TEXT("seed_harbor_turnip"), 10 },
		{ TEXT("seed_mistberry"), 6 },
		{ TEXT("seed_moonbell"), 3 },
	};

	static const FKey SlotKeys[] =
	{
		EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five,
		EKeys::Six, EKeys::Seven, EKeys::Eight, EKeys::Nine,
	};

	template <typename T>
	T* FindOrAddComponent(AActor* Owner, const TCHAR* Name, bool& bOutAdded)
	{
		bOutAdded = false;
		if (T* Existing = Owner->FindComponentByClass<T>())
		{
			return Existing;
		}
		T* Added = NewObject<T>(Owner, T::StaticClass(), Name);
		Owner->AddInstanceComponent(Added);
		Added->RegisterComponent();  // owner has begun play, so this runs BeginPlay too
		bOutAdded = true;
		return Added;
	}

	static FString QualitySuffix(ELyrisItemQuality Quality)
	{
		if (Quality == ELyrisItemQuality::Normal)
		{
			return FString();
		}
		const UEnum* Enum = StaticEnum<ELyrisItemQuality>();
		return Enum ? FString::Printf(TEXT(" (%s)"), *Enum->GetDisplayNameTextByValue(static_cast<int64>(Quality)).ToString()) : FString();
	}
}

void ULyrisPlaytestSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	// The "Game" debug draw channel is on by default in PIE and development builds.
	DrawHandle = UDebugDrawService::Register(TEXT("Game"),
		FDebugDrawDelegate::CreateUObject(this, &ULyrisPlaytestSubsystem::DrawReadout));
}

void ULyrisPlaytestSubsystem::Deinitialize()
{
	if (DrawHandle.IsValid())
	{
		UDebugDrawService::Unregister(DrawHandle);
		DrawHandle.Reset();
	}
	Super::Deinitialize();
}

bool ULyrisPlaytestSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

TStatId ULyrisPlaytestSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(ULyrisPlaytestSubsystem, STATGROUP_Tickables);
}

void ULyrisPlaytestSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	if (LyrisPlaytest::CVarEnabled.GetValueOnGameThread() == 0)
	{
		return;
	}
	UWorld* World = GetWorld();
	if (!World || !World->HasBegunPlay())
	{
		return;
	}
	APlayerController* PC = World->GetFirstPlayerController();
	if (!PC || !PC->IsLocalController())
	{
		return;
	}

	if (!bCropsSpedUp)
	{
		SpeedUpCrops();
	}

	// Only the walking character gets the kit; while aboard the boat the pawn is the boat.
	ACharacter* Character = Cast<ACharacter>(PC->GetPawn());
	if (Character)
	{
		if (SetUpFor.Get() != Character)
		{
			SetUpCharacter(Character);
		}
		if (!bSpawnedSamples)
		{
			SpawnSamples(Character);
		}
	}

	HandleInput(PC, Character);
}

void ULyrisPlaytestSubsystem::SpeedUpCrops()
{
	bCropsSpedUp = true;
	if (LyrisPlaytest::CVarFast.GetValueOnGameThread() == 0)
	{
		return;
	}
	ULyrisCropRegistry* Registry = ULyrisCropRegistry::Get(GetWorld());
	if (!Registry)
	{
		return;
	}
	// The built-in crops are runtime objects, so this only lasts for this play session.
	for (const TCHAR* CropId : { TEXT("harbor_turnip"), TEXT("mistberry"), TEXT("moonbell") })
	{
		if (ULyrisCropDefinition* Crop = Registry->FindCrop(CropId))
		{
			Crop->Data.BaseHoursToRipe = FMath::Max(0.005f, Crop->Data.BaseHoursToRipe / LyrisPlaytest::SpeedUp);
			Crop->Data.RegrowHours = FMath::Max(0.002f, Crop->Data.RegrowHours / LyrisPlaytest::SpeedUp);
		}
	}
}

void ULyrisPlaytestSubsystem::SetUpCharacter(ACharacter* Character)
{
	SetUpFor = Character;

	bool bAddedInventory = false;
	bool bAddedInteraction = false;
	ULyrisInventoryComponent* Inv = LyrisPlaytest::FindOrAddComponent<ULyrisInventoryComponent>(
		Character, TEXT("PlaytestInventory"), bAddedInventory);
	ULyrisInteractionComponent* Interact = LyrisPlaytest::FindOrAddComponent<ULyrisInteractionComponent>(
		Character, TEXT("PlaytestInteraction"), bAddedInteraction);

	Inventory = Inv;
	Interaction = Interact;

	// Starter kit, once per character (stepping off the boat again keeps what you gathered).
	if (Inv && Inv->CountOfId(TEXT("tool_hoe")) == 0)
	{
		for (const LyrisPlaytest::FStarterItem& Item : LyrisPlaytest::StarterKit)
		{
			Inv->AddItemById(Item.Id, Item.Count);
		}
		Inv->SetActiveSlot(4);  // turnip seeds: the quickest crop
	}

	UE_LOG(LogTemp, Log, TEXT("Lyris playtest: kit ready on %s (inventory %s, interaction %s)."),
		*Character->GetName(),
		bAddedInventory ? TEXT("added") : TEXT("already there"),
		bAddedInteraction ? TEXT("added") : TEXT("already there"));
}

bool ULyrisPlaytestSubsystem::FindGround(const FVector& Location, float BaseZ, float MaxRise, FVector& OutGround, const AActor* Ignore) const
{
	UWorld* World = GetWorld();
	FCollisionQueryParams Params(SCENE_QUERY_STAT(LyrisPlaytestGround), false, Ignore);
	FHitResult Hit;
	const FVector Start(Location.X, Location.Y, BaseZ + 3000.f);
	const FVector End(Location.X, Location.Y, BaseZ - 3000.f);
	if (!World->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
	{
		return false;
	}
	if (FMath::Abs(Hit.ImpactPoint.Z - BaseZ) > MaxRise || Hit.ImpactNormal.Z < 0.7f)
	{
		return false;  // a cliff, a roof or the sea floor: try somewhere else
	}
	OutGround = Hit.ImpactPoint;
	return true;
}

void ULyrisPlaytestSubsystem::SpawnSamples(ACharacter* Character)
{
	bSpawnedSamples = true;
	UWorld* World = GetWorld();
	const bool bFast = LyrisPlaytest::CVarFast.GetValueOnGameThread() != 0;

	const FVector Base = Character->GetActorLocation();
	const float FeetZ = Base.Z - Character->GetSimpleCollisionHalfHeight();
	FVector Forward = Character->GetActorForwardVector().GetSafeNormal2D();
	if (Forward.IsNearlyZero())
	{
		Forward = FVector::ForwardVector;
	}
	const FVector Right = FVector::CrossProduct(FVector::UpVector, Forward);
	const FRotator Facing = Forward.Rotation();

	// Try the preferred spot, then turn around the player until one is on walkable ground.
	auto Place = [&](const FVector& Offset, float MaxRise, FVector& Out) -> bool
	{
		for (int32 Turn = 0; Turn < 8; ++Turn)
		{
			const FVector Rotated = Offset.RotateAngleAxis(45.f * Turn, FVector::UpVector);
			if (FindGround(Base + Rotated, FeetZ, MaxRise, Out, Character))
			{
				return true;
			}
		}
		return false;
	};

	// Farm plot, 4 x 4, about five metres ahead.
	bool bHasPlot = false;
	for (TActorIterator<ALyrisFarmPlot> It(World); It; ++It)
	{
		bHasPlot = true;
		if (bFast)
		{
			It->WaterHours = FMath::Max(0.01f, It->WaterHours / LyrisPlaytest::SpeedUp);
		}
	}
	FVector Ground;
	if (!bHasPlot && Place(Forward * 450.f - Right * 200.f, 250.f, Ground))
	{
		const FTransform At(Facing, Ground);
		if (ALyrisFarmPlot* Plot = World->SpawnActorDeferred<ALyrisFarmPlot>(ALyrisFarmPlot::StaticClass(), At))
		{
			Plot->GridSize = FIntPoint(4, 4);
			Plot->bStartTilled = false;
			if (bFast)
			{
				Plot->WaterHours = FMath::Max(0.01f, Plot->WaterHours / LyrisPlaytest::SpeedUp);  // 48 s
			}
			Plot->FinishSpawning(At);
		}
	}

	// One of each resource node in a row to the right.
	bool bHasNodes = false;
	for (TActorIterator<ALyrisResourceNode> It(World); It; ++It)
	{
		bHasNodes = true;
		break;
	}
	if (!bHasNodes)
	{
		const TCHAR* NodeTypes[] = { TEXT("rock"), TEXT("copper_vein"), TEXT("tree"), TEXT("sea_herb"), TEXT("star_crystal") };
		for (int32 Index = 0; Index < UE_ARRAY_COUNT(NodeTypes); ++Index)
		{
			const FVector Offset = Right * 450.f + Forward * (Index * 280.f - 280.f);
			if (!Place(Offset, 250.f, Ground))
			{
				continue;
			}
			const FTransform At(FRotator(0.f, FMath::FRandRange(0.f, 360.f), 0.f), Ground);
			if (ALyrisResourceNode* Node = World->SpawnActorDeferred<ALyrisResourceNode>(ALyrisResourceNode::StaticClass(), At))
			{
				Node->NodeType = NodeTypes[Index];
				if (bFast)
				{
					if (const FLyrisResourceNodeData* BuiltIn = LyrisResourceCatalog::FindBuiltIn(Node->NodeType))
					{
						Node->bUseCustomData = true;
						Node->CustomData = *BuiltIn;
						Node->CustomData.RespawnHours = FMath::Max(0.005f, BuiltIn->RespawnHours / LyrisPlaytest::SpeedUp);
					}
				}
				Node->FinishSpawning(At);
			}
		}
	}

	// Combat training ground well away from the farm (crawlers wake within about 18 m).
	bool bHasTraining = false;
	for (TActorIterator<ALyrisTrainingGround> It(World); It; ++It)
	{
		bHasTraining = true;
		break;
	}
	if (!bHasTraining)
	{
		bool bPlaced = false;
		for (const float Distance : { 3500.f, 2800.f, 2200.f })
		{
			if (Place(-Forward * Distance, 800.f, Ground))
			{
				bPlaced = true;
				break;
			}
		}
		if (bPlaced)
		{
			const FTransform At(Facing, Ground);
			if (ALyrisTrainingGround* Training = World->SpawnActorDeferred<ALyrisTrainingGround>(ALyrisTrainingGround::StaticClass(), At))
			{
				Training->RespawnLocation = Base;  // defeat brings you back to where you started
				Training->FinishSpawning(At);
			}
		}
		else
		{
			UE_LOG(LogTemp, Warning, TEXT("Lyris playtest: no flat ground 22-35 m away for the training ground; skipped."));
		}
	}
}

void ULyrisPlaytestSubsystem::HandleInput(APlayerController* PC, ACharacter* Character)
{
	if (PC->WasInputKeyJustPressed(EKeys::I))
	{
		bShowBag = !bShowBag;
	}
	if (!Character)
	{
		return;
	}

	ULyrisInventoryComponent* Inv = Inventory.Get();
	if (Inv)
	{
		for (int32 Index = 0; Index < UE_ARRAY_COUNT(LyrisPlaytest::SlotKeys); ++Index)
		{
			if (PC->WasInputKeyJustPressed(LyrisPlaytest::SlotKeys[Index]))
			{
				Inv->SetActiveSlot(Index);
			}
		}
	}

	ULyrisInteractionComponent* Interact = Interaction.Get();
	if (!Interact)
	{
		return;
	}

	// Show which soil cell you're about to work on (farming spec section 2).
	ALyrisFarmPlot* Plot = Cast<ALyrisFarmPlot>(Interact->GetCurrentTarget());
	if (HighlightedPlot.IsValid() && HighlightedPlot.Get() != Plot)
	{
		HighlightedPlot->SetHighlightedCell(INDEX_NONE);
	}
	if (Plot)
	{
		Plot->SetHighlightedCell(Plot->GetCellForActor(Character));
	}
	HighlightedPlot = Plot;

	// F, because the boat already uses E to step ashore.
	if (PC->WasInputKeyJustPressed(EKeys::F))
	{
		Interact->TryInteract();
	}
}

void ULyrisPlaytestSubsystem::DrawReadout(UCanvas* Canvas, APlayerController* PC)
{
	if (!Canvas || !GEngine || LyrisPlaytest::CVarEnabled.GetValueOnGameThread() == 0)
	{
		return;
	}
	UWorld* World = GetWorld();
	if (!PC || PC->GetWorld() != World || !PC->IsLocalController())
	{
		return;  // the debug channel is global: only draw for this subsystem's own world
	}

	const FColor Gold(255, 214, 140);
	const FColor Cream(245, 236, 214);
	const FColor Soft(200, 200, 186);

	TArray<TPair<FString, FColor>> Lines;
	Lines.Emplace(TEXT("LYRIS PLAYTEST     F interact     1-9 pick slot     I bag     LMB / RMB / Shift fight"), Gold);

	const ACharacter* Character = Cast<ACharacter>(PC->GetPawn());
	if (!Character)
	{
		Lines.Emplace(TEXT("(aboard the boat: step ashore to farm and gather)"), Soft);
	}
	else if (const ULyrisInteractionComponent* Interact = Interaction.Get())
	{
		const FString Prompt = Interact->GetCurrentPrompt().ToString();
		Lines.Emplace(Prompt.IsEmpty() ? FString(TEXT("   ...")) : FString::Printf(TEXT("   [F]  %s"), *Prompt), Cream);
	}

	if (const ULyrisInventoryComponent* Inv = Inventory.Get(); Inv && bShowBag)
	{
		Lines.Emplace(TEXT(" "), Soft);
		Lines.Emplace(TEXT("BAG"), Gold);
		const TArray<FLyrisInventorySlot> Slots = Inv->GetSlots();
		const int32 Active = Inv->GetActiveSlot();
		for (int32 Index = 0; Index < Slots.Num(); ++Index)
		{
			const FLyrisInventorySlot& Slot = Slots[Index];
			if (Slot.IsEmpty())
			{
				continue;
			}
			const ULyrisItemDefinition* Def = Slot.Definition ? Slot.Definition.Get()
				: ULyrisItemRegistry::FindItem(World, Slot.ItemId);
			const FString Name = Def ? Def->DisplayName.ToString() : Slot.ItemId.ToString();
			const bool bActive = Index == Active;
			const FString Label = Index < 9 ? FString::Printf(TEXT("%d"), Index + 1) : FString(TEXT(" "));
			Lines.Emplace(FString::Printf(TEXT("%s %s   %s  x%d%s"), bActive ? TEXT(">") : TEXT(" "), *Label, *Name,
				Slot.Count, *LyrisPlaytest::QualitySuffix(Slot.Quality)), bActive ? Gold : Soft);
		}
	}

	UFont* Font = GEngine->GetMediumFont();
	FFontRenderInfo Info;
	Info.bEnableShadow = true;
	float Y = 60.f;
	for (const TPair<FString, FColor>& Line : Lines)
	{
		Canvas->SetDrawColor(Line.Value);
		Y += Canvas->DrawText(Font, Line.Key, 24.f, Y, 1.f, 1.f, Info) + 2.f;
	}
}
