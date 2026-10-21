// Lyris sailing (T21): rough water and the hull.

#include "Sailing/LyrisHullComponent.h"

#include "Lyris.h"
#include "LyrisBoat.h"
#include "Components/StaticMeshComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Items/LyrisInventoryComponent.h"
#include "Items/LyrisItemDefinition.h"
#include "Items/LyrisItemRegistry.h"
#include "Items/LyrisItemTypes.h"
#include "Materials/MaterialInterface.h"
#include "Sailing/LyrisHarborMooring.h"
#include "UObject/ConstructorHelpers.h"
#include "World/LyrisOceanSubsystem.h"

#define LOCTEXT_NAMESPACE "LyrisHull"

namespace LyrisHull
{
	// On-screen hint slots. The boat uses 71001..71004; the hull uses 71005..71007 in the same style.
	static constexpr int32 SlotStatus = 5;
	static constexpr int32 SlotEvent = 6;
	static constexpr int32 SlotSwamp = 7;

	static const FColor Cream(240, 233, 220);
	static const FColor SeaBlue(122, 192, 230);
	static const FColor Amber(227, 174, 69);
	static const FColor Coral(232, 160, 120);
	static const FColor Mist(170, 200, 230);

	/** Default item id for planks. */
	static const FName PlankId(TEXT("plank"));
}

ULyrisHullComponent::ULyrisHullComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;

	BailKey = EKeys::Q;
	PatchKey = EKeys::R;
	PlankItemId = LyrisHull::PlankId;

	// Same prototype materials as the boat itself (made by the Harbor build script).
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeFinder(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> DarkWoodFinder(TEXT("/Game/Lyris/Materials/Prototype/M_DarkWood.M_DarkWood"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> WoodFinder(TEXT("/Game/Lyris/Materials/Prototype/M_Wood.M_Wood"));
	SpotMesh = CubeFinder.Object;
	BreachMaterial = DarkWoodFinder.Object;
	PlankMaterial = WoodFinder.Object;
}

void ULyrisHullComponent::BeginPlay()
{
	Super::BeginPlay();

	AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}

	// Spots ride on the boat's "Visual" root so they pitch and roll with the hull.
	TArray<USceneComponent*> SceneComponents;
	Owner->GetComponents<USceneComponent>(SceneComponents);
	for (USceneComponent* Component : SceneComponents)
	{
		if (Component && Component->GetFName() == TEXT("Visual"))
		{
			VisualRoot = Component;
			break;
		}
	}
	if (!VisualRoot)
	{
		VisualRoot = Owner->GetRootComponent();
	}

	HomeMooringLocation = Owner->GetActorLocation();
	HomeMooringRotation = FRotator(0.f, Owner->GetActorRotation().Yaw, 0.f);

	Owner->OnActorHit.AddDynamic(this, &ULyrisHullComponent::HandleOwnerHit);

	EnsurePlankItem();
}

void ULyrisHullComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (AActor* Owner = GetOwner())
	{
		Owner->OnActorHit.RemoveDynamic(this, &ULyrisHullComponent::HandleOwnerHit);
	}
	Super::EndPlay(EndPlayReason);
}

// ---- Reading ------------------------------------------------------------------------------------

float ULyrisHullComponent::GetSpeedMultiplier() const
{
	if (State != EHullState::Afloat)
	{
		return 0.f;
	}
	const float Alpha = FMath::Clamp((WaterLevel - SluggishStart) / FMath::Max(0.01f, 1.f - SluggishStart), 0.f, 1.f);
	return FMath::Lerp(1.f, MinSpeedMultiplier, Alpha);
}

float ULyrisHullComponent::GetTurnMultiplier() const
{
	if (State != EHullState::Afloat)
	{
		return 0.f;
	}
	const float Alpha = FMath::Clamp((WaterLevel - SluggishStart) / FMath::Max(0.01f, 1.f - SluggishStart), 0.f, 1.f);
	return FMath::Lerp(1.f, MinTurnMultiplier, Alpha);
}

float ULyrisHullComponent::GetSinkOffset() const
{
	// Full while swamped and fading out; once home (emptied) she rises again as the screen clears.
	const bool bFull = State == EHullState::Swamped || State == EHullState::FadingOut;
	return MaxSinkOffset * (bFull ? 1.f : FMath::Clamp(WaterLevel, 0.f, 1.f));
}

// ---- Tick ---------------------------------------------------------------------------------------

void ULyrisHullComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (DeltaTime <= 0.f)
	{
		return;
	}

	UpdateMotion(DeltaTime);

	APlayerController* PC = GetAboardController();
	const bool bAboard = PC != nullptr;

	if (State == EHullState::Afloat)
	{
		UpdateWaterIn(DeltaTime, bAboard);
		if (bAboard)
		{
			UpdateWaveBreaches(DeltaTime);
			UpdateInput(PC);
		}
		if (WaterLevel >= 1.f)
		{
			BeginSwamp();
		}
	}
	else
	{
		UpdateSwamp(DeltaTime, PC);
	}

	ShowHints(bAboard);
}

APlayerController* ULyrisHullComponent::GetAboardController() const
{
	const APawn* Boat = Cast<APawn>(GetOwner());
	APlayerController* PC = Boat ? Boat->GetController<APlayerController>() : nullptr;
	return (PC && PC->IsLocalController()) ? PC : nullptr;
}

void ULyrisHullComponent::UpdateMotion(float DeltaTime)
{
	const AActor* Owner = GetOwner();
	const FVector Location = Owner->GetActorLocation();
	if (bHasPreviousLocation)
	{
		const FVector Delta = Location - PreviousLocation;
		LastVelocity = FVector(Delta.X, Delta.Y, 0.f) / DeltaTime;
		// A jump far faster than any boat sails is a teleport (the mist boundary, a harbor return), not speed.
		if (LastVelocity.SizeSquared() > FMath::Square(4.0 * ReferenceSpeed))
		{
			LastVelocity = FVector::ZeroVector;
		}
	}
	PreviousLocation = Location;
	bHasPreviousLocation = true;

	const ULyrisOceanSubsystem* Ocean = ULyrisOceanSubsystem::Get(this);
	CurrentRoughness = Ocean ? Ocean->GetRoughnessAt(FVector2D(Location.X, Location.Y)) : 0.f;
}

void ULyrisHullComponent::UpdateWaterIn(float DeltaTime, bool bAboard)
{
	// A boat left at a mooring never fills up on its own: leaks only work while someone is sailing her.
	if (!bAboard)
	{
		return;
	}

	float Rate = LeakRatePerBreach * Breaches.Num();

	// Spray over the bow: rough water and way on. Lit (calm) water stays dry.
	const float RoughAlpha = FMath::Clamp((CurrentRoughness - SprayRoughnessThreshold) / FMath::Max(0.01f, 1.f - SprayRoughnessThreshold), 0.f, 1.f);
	const float SpeedAlpha = FMath::Clamp(static_cast<float>(LastVelocity.Size()) / ReferenceSpeed, 0.f, 1.f);
	const float Spray = SprayRate * RoughAlpha * SpeedAlpha;
	if (Spray > SprayRate * 0.25f)
	{
		const double Now = GetWorld()->GetTimeSeconds();
		// Mention it once in a while, not every frame.
		if (Now - LastSprayHintTime > 45.0)
		{
			LastSprayHintTime = Now;
			SprayHintUntil = Now + 4.0;
		}
	}
	Rate += Spray;

	WaterLevel = FMath::Clamp(WaterLevel + Rate * DeltaTime, 0.f, 1.f);
}

void ULyrisHullComponent::UpdateWaveBreaches(float DeltaTime)
{
	if (WaveBreachesPerMinute <= 0.f || CurrentRoughness <= WaveBreachRoughnessThreshold || Breaches.Num() >= MaxBreaches)
	{
		return;
	}

	// Rare: a Poisson chance per tick, strongest in the roughest water and when driving hard into it.
	const float RoughAlpha = (CurrentRoughness - WaveBreachRoughnessThreshold) / FMath::Max(0.01f, 1.f - WaveBreachRoughnessThreshold);
	const float SpeedAlpha = FMath::Clamp(static_cast<float>(LastVelocity.Size()) / ReferenceSpeed, 0.f, 1.f);
	const float PerSecond = WaveBreachesPerMinute / 60.f * RoughAlpha * (0.25f + 0.75f * SpeedAlpha);
	if (FMath::FRand() < PerSecond * DeltaTime)
	{
		// A big sea knocks a seam loose somewhere along the forward half of the hull.
		const AActor* Owner = GetOwner();
		const float Side = FMath::RandBool() ? 1.f : -1.f;
		const float HalfX = static_cast<float>(HullHalfExtent.X);
		const float HalfY = static_cast<float>(HullHalfExtent.Y);
		const FVector Local(FMath::FRandRange(0.f, HalfX * 0.8f), Side * HalfY, 10.f);
		const FVector World = VisualRoot ? VisualRoot->GetComponentTransform().TransformPosition(Local)
			: Owner->GetActorTransform().TransformPosition(Local);
		AddBreach(World);
		ShowMessage(LyrisHull::SlotEvent, TEXT("A big wave slams the hull and a seam springs a leak. R to patch, Q to bail."),
			LyrisHull::Coral, 5.f);
	}
}

void ULyrisHullComponent::UpdateInput(APlayerController* PC)
{
	// Bail: hold the key to keep scooping at the bucket's pace.
	if (BailKey.IsValid() && PC->IsInputKeyDown(BailKey))
	{
		Bail();
	}

	// Patch: one press, one plank.
	const bool bPatchDown = PatchKey.IsValid() && PC->IsInputKeyDown(PatchKey);
	if (bPatchDown && !bPatchKeyWasDown)
	{
		if (Breaches.Num() > 0)
		{
			PatchBreach();
		}
		else
		{
			ShowMessage(LyrisHull::SlotEvent, TEXT("The hull is sound. No leaks to patch."), LyrisHull::Cream, 2.f);
		}
	}
	bPatchKeyWasDown = bPatchDown;
}

// ---- Impacts ------------------------------------------------------------------------------------

void ULyrisHullComponent::HandleOwnerHit(AActor* SelfActor, AActor* OtherActor, FVector NormalImpulse, const FHitResult& Hit)
{
	if (State != EHullState::Afloat || !Hit.bBlockingHit)
	{
		return;
	}
	// Bumping into a person (on the dock, in the water) never breaks anything.
	if (Cast<APawn>(OtherActor))
	{
		return;
	}

	// Only the part of our speed that goes into the obstacle counts: glancing scrapes are harmless.
	const FVector Normal2D = FVector(Hit.ImpactNormal.X, Hit.ImpactNormal.Y, 0.f).GetSafeNormal();
	const float Closing = Normal2D.IsNearlyZero() ? 0.f : static_cast<float>(-FVector::DotProduct(LastVelocity, Normal2D));
	if (Closing < ImpactBreachSpeed)
	{
		return;
	}

	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - LastBreachTime < ImpactBreachCooldown)
	{
		return;
	}

	const int32 Before = Breaches.Num();
	AddBreach(Hit.ImpactPoint);
	if (Breaches.Num() > Before)
	{
		ShowMessage(LyrisHull::SlotEvent, TEXT("Crunch! The rocks opened a leak in the hull. R to patch it, Q to bail."),
			LyrisHull::Coral, 5.f);
	}
}

// ---- Breaches, bailing, patching ----------------------------------------------------------------

void ULyrisHullComponent::AddBreach(FVector WorldLocation)
{
	if (State != EHullState::Afloat || Breaches.Num() >= MaxBreaches)
	{
		return;
	}

	const FTransform RootTransform = VisualRoot ? VisualRoot->GetComponentTransform() : GetOwner()->GetActorTransform();
	const FVector Local = PlaceOnHullSide(RootTransform.InverseTransformPosition(WorldLocation));

	FLyrisHullBreach Breach;
	Breach.LocalPosition = Local;
	Breach.Spot = MakeSpot(Local, BreachMaterial, FVector(0.32f, 0.03f, 0.2f));
	Breaches.Add(Breach);

	LastBreachTime = GetWorld()->GetTimeSeconds();
	OnBreached.Broadcast(Breaches.Num());
}

bool ULyrisHullComponent::Bail()
{
	if (State != EHullState::Afloat || WaterLevel <= 0.f)
	{
		return false;
	}

	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - LastBailTime < BailCooldown)
	{
		return false;
	}

	// Optional bucket: off by default (BailToolType None). HasTool(None) is always true.
	if (!BailToolType.IsNone())
	{
		if (const ULyrisInventoryComponent* Inventory = FindPlayerInventory())
		{
			if (!Inventory->HasTool(BailToolType))
			{
				ShowMessage(LyrisHull::SlotEvent, TEXT("You'll need a bucket to bail."), LyrisHull::Cream, 2.f);
				LastBailTime = Now;
				return false;
			}
		}
	}

	LastBailTime = Now;
	WaterLevel = FMath::Max(0.f, WaterLevel - BailAmount);
	return true;
}

bool ULyrisHullComponent::PatchBreach()
{
	if (State != EHullState::Afloat || Breaches.Num() == 0)
	{
		return false;
	}

	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - LastPatchTime < PatchCooldown)
	{
		return false;
	}

	if (ULyrisInventoryComponent* Inventory = FindPlayerInventory())
	{
		if (!Inventory->RemoveItemById(PlankItemId, 1))
		{
			ShowMessage(LyrisHull::SlotEvent, TEXT("No planks to patch with. Keep bailing (Q) and head for a lit harbor."),
				LyrisHull::Cream, 3.f);
			LastPatchTime = Now;
			return false;
		}
	}
	else if (!bLoggedFreePatch)
	{
		// TODO(T14): the player has no inventory yet, so patching is free. Once T14 gives the player a
		// ULyrisInventoryComponent, this branch stops running and each patch uses one plank.
		UE_LOG(LogLyris, Log, TEXT("Hull: no player inventory found, patching for free (TODO: needs T14)"));
		bLoggedFreePatch = true;
	}

	LastPatchTime = Now;
	PatchBreachAt(0);
	ShowMessage(LyrisHull::SlotEvent, Breaches.Num() > 0
		? FString::Printf(TEXT("Patched! %d more leak%s to go."), Breaches.Num(), Breaches.Num() == 1 ? TEXT("") : TEXT("s"))
		: FString(TEXT("Patched! The hull is sound again. Bail out what's left.")),
		LyrisHull::SeaBlue, 3.f);
	return true;
}

void ULyrisHullComponent::PatchBreachAt(int32 Index)
{
	if (!Breaches.IsValidIndex(Index))
	{
		return;
	}
	const FLyrisHullBreach Breach = Breaches[Index];
	Breaches.RemoveAt(Index);

	if (Breach.Spot)
	{
		Breach.Spot->DestroyComponent();
	}
	// A plank nailed over the hole, slightly proud of the hull, stays as a little scar of the voyage.
	const float Side = Breach.LocalPosition.Y >= 0.f ? 1.f : -1.f;
	if (UStaticMeshComponent* Plank = MakeSpot(Breach.LocalPosition + FVector(0.f, Side * 1.5f, 0.f), PlankMaterial,
		FVector(0.5f, 0.04f, 0.13f)))
	{
		// A slight, hand-nailed tilt within the hull side (pitch turns it about the side's normal, Y).
		Plank->SetRelativeRotation(FRotator(FMath::FRandRange(-8.f, 8.f), 0.f, 0.f));
		Planks.Add(Plank);
	}
	TrimPlanks();
}

void ULyrisHullComponent::RepairFully()
{
	while (Breaches.Num() > 0)
	{
		PatchBreachAt(0);
	}
	WaterLevel = 0.f;
}

// ---- Swamped, never sunk ------------------------------------------------------------------------

void ULyrisHullComponent::BeginSwamp()
{
	WaterLevel = 1.f;
	State = EHullState::Swamped;
	StateTime = 0.f;
	OnSwamped.Broadcast();
	ShowMessage(LyrisHull::SlotSwamp,
		TEXT("She's swamped and won't answer the helm. Hold on: the current will carry you home to a lit harbor."),
		LyrisHull::Mist, SwampedPause + FadeOutTime + 0.5f);
}

void ULyrisHullComponent::UpdateSwamp(float DeltaTime, APlayerController* PC)
{
	StateTime += DeltaTime;
	if (PC && State == EHullState::Swamped)
	{
		FadingController = PC;
	}
	APlayerController* FadePC = FadingController.Get();
	APlayerCameraManager* Camera = FadePC ? FadePC->PlayerCameraManager.Get() : nullptr;

	switch (State)
	{
	case EHullState::Swamped:
		if (StateTime >= SwampedPause)
		{
			State = EHullState::FadingOut;
			StateTime = 0.f;
			if (Camera)
			{
				Camera->StartCameraFade(0.f, 1.f, FadeOutTime, FadeColor, false, true);
			}
		}
		break;

	case EHullState::FadingOut:
		if (StateTime >= FadeOutTime)
		{
			ReturnToHarbor();
			State = EHullState::FadingIn;
			StateTime = 0.f;
			if (Camera)
			{
				Camera->StartCameraFade(1.f, 0.f, FadeInTime, FadeColor, false, false);
			}
		}
		break;

	case EHullState::FadingIn:
		if (StateTime >= FadeInTime)
		{
			State = EHullState::Afloat;
			StateTime = 0.f;
			FadingController.Reset();
			ShowMessage(LyrisHull::SlotSwamp,
				FString::Printf(TEXT("Safe in %s. The harbor folk bailed her out and patched the hull. Nothing was lost."),
					*LastHarborName.ToString()),
				LyrisHull::SeaBlue, 6.f);
			OnReturnedHome.Broadcast();
		}
		break;

	default:
		break;
	}
}

void ULyrisHullComponent::ReturnToHarbor()
{
	AActor* Owner = GetOwner();
	FVector Location;
	FRotator Rotation;
	FindHarbor(Location, Rotation, LastHarborName);

	// The player is aboard (the boat is their pawn), so they come home with her. No items, no harm.
	Owner->SetActorLocationAndRotation(Location, Rotation, false, nullptr, ETeleportType::TeleportPhysics);
	bHasPreviousLocation = false;
	LastVelocity = FVector::ZeroVector;

	RepairFully();
}

void ULyrisHullComponent::FindHarbor(FVector& OutLocation, FRotator& OutRotation, FText& OutName) const
{
	const AActor* Owner = GetOwner();
	const FVector From = Owner->GetActorLocation();
	const ULyrisOceanSubsystem* Ocean = ULyrisOceanSubsystem::Get(this);

	// 1. The nearest placed harbor mooring whose water is lit (calm).
	const ALyrisHarborMooring* Best = nullptr;
	double BestDistSq = TNumericLimits<double>::Max();
	for (TActorIterator<ALyrisHarborMooring> It(GetWorld()); It; ++It)
	{
		const ALyrisHarborMooring* Mooring = *It;
		if (!Mooring || !Mooring->bEnabled)
		{
			continue;
		}
		const FVector MooringLocation = Mooring->GetActorLocation();
		if (Ocean && Ocean->GetRoughnessAt(FVector2D(MooringLocation.X, MooringLocation.Y)) > LitHarborMaxRoughness)
		{
			continue; // its lamp is out: not a lit harbor right now
		}
		const double DistSq = FVector::DistSquared2D(From, MooringLocation);
		if (DistSq < BestDistSq)
		{
			BestDistSq = DistSq;
			Best = Mooring;
		}
	}
	if (Best)
	{
		OutLocation = Best->GetActorLocation();
		OutRotation = FRotator(0.f, Best->GetActorRotation().Yaw, 0.f);
		OutName = Best->HarborName.IsEmpty() ? LOCTEXT("HarborFallbackName", "the harbor") : Best->HarborName;
		return;
	}

	// 2. Where this boat was moored when the level began (beside the home dock, inside the home calm zone).
	OutLocation = HomeMooringLocation;
	OutRotation = HomeMooringRotation;
	OutName = LOCTEXT("HomeHarborName", "the home harbor");
}

// ---- Items --------------------------------------------------------------------------------------

ULyrisInventoryComponent* ULyrisHullComponent::FindPlayerInventory() const
{
	// While sailing, the walking character is stored (hidden) by the boat; their bag is on them.
	if (const ALyrisBoat* Boat = Cast<ALyrisBoat>(GetOwner()))
	{
		if (ULyrisInventoryComponent* Inventory = ULyrisInventoryComponent::FindInventory(Boat->GetStoredWalker()))
		{
			return Inventory;
		}
	}
	// Otherwise the boat itself or its controller (FindInventory checks both).
	return ULyrisInventoryComponent::FindInventory(GetOwner());
}

void ULyrisHullComponent::EnsurePlankItem()
{
	ULyrisItemRegistry* Registry = ULyrisItemRegistry::Get(this);
	if (!Registry || PlankItemId.IsNone() || Registry->FindDefinition(PlankItemId))
	{
		return;
	}

	// T11 supports code-defined items. Harvest can move this row into LyrisItemCatalog (same id) later;
	// a DataTable or data asset with this id already wins, because we only add it when it is missing.
	FLyrisItemRow Row;
	Row.DisplayName = LOCTEXT("PlankName", "Plank");
	Row.Description = LOCTEXT("PlankDesc", "A sturdy board. Nail one over a leak in the hull.");
	Row.Category = ELyrisItemCategory::Material;
	Row.MaxStack = 99;
	Row.Rarity = ELyrisItemRarity::Common;
	Registry->RegisterRow(PlankItemId, Row);
}

// ---- Looks --------------------------------------------------------------------------------------

FVector ULyrisHullComponent::PlaceOnHullSide(const FVector& LocalPoint) const
{
	const float Side = FMath::Abs(LocalPoint.Y) > 1.f ? FMath::Sign(static_cast<float>(LocalPoint.Y)) : (FMath::RandBool() ? 1.f : -1.f);
	const float Margin = 35.f;
	const float HalfX = static_cast<float>(HullHalfExtent.X);
	const float HalfY = static_cast<float>(HullHalfExtent.Y);
	const float HalfZ = static_cast<float>(HullHalfExtent.Z);
	float X = FMath::Clamp(static_cast<float>(LocalPoint.X), -HalfX + Margin, HalfX - Margin);
	// Keep the spots above the waterline (which sits about FreeboardOffset = 25 cm below the boat's origin) so they show.
	const float Z = FMath::Clamp(static_cast<float>(LocalPoint.Z), -12.f, FMath::Max(-12.f, HalfZ - 15.f));

	const float LadderX = static_cast<float>(LadderKeepOutCenter.X);
	auto IsBlocked = [this, Side, LadderX](float CandidateX)
	{
		// The boarding ladder hangs on the port quarter (T18): never put a leak or a plank under it.
		if (Side < 0.f && FMath::Abs(CandidateX - LadderX) < LadderKeepOutHalfLength)
		{
			return true;
		}
		for (const FLyrisHullBreach& Other : Breaches)
		{
			if (FMath::Sign(static_cast<float>(Other.LocalPosition.Y)) == Side
				&& FMath::Abs(static_cast<float>(Other.LocalPosition.X) - CandidateX) < 45.f)
			{
				return true;
			}
		}
		return false;
	};

	// Slide forward or aft along the hull until the spot is clear.
	if (IsBlocked(X))
	{
		for (int32 Step = 1; Step <= 12; ++Step)
		{
			const float Offset = 50.f * ((Step + 1) / 2) * ((Step % 2) ? 1.f : -1.f);
			const float Candidate = X + Offset;
			if (Candidate > -HalfX + Margin && Candidate < HalfX - Margin && !IsBlocked(Candidate))
			{
				X = Candidate;
				break;
			}
		}
	}

	return FVector(X, Side * (HalfY + 1.f), Z);
}

UStaticMeshComponent* ULyrisHullComponent::MakeSpot(const FVector& LocalPosition, UMaterialInterface* Material, const FVector& Scale)
{
	AActor* Owner = GetOwner();
	if (!Owner || !SpotMesh || !VisualRoot)
	{
		return nullptr;
	}

	UStaticMeshComponent* Spot = NewObject<UStaticMeshComponent>(Owner);
	Spot->SetStaticMesh(SpotMesh);
	if (Material)
	{
		Spot->SetMaterial(0, Material);
	}
	Spot->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Spot->SetCanEverAffectNavigation(false);
	Spot->SetCastShadow(false);
	Spot->SetupAttachment(VisualRoot);
	Spot->SetRelativeLocation(LocalPosition);
	Spot->SetRelativeScale3D(Scale);
	Spot->RegisterComponent();
	return Spot;
}

void ULyrisHullComponent::TrimPlanks()
{
	Planks.RemoveAll([](const TObjectPtr<UStaticMeshComponent>& Plank) { return Plank == nullptr; });
	while (Planks.Num() > MaxVisiblePlanks)
	{
		if (Planks[0])
		{
			Planks[0]->DestroyComponent();
		}
		Planks.RemoveAt(0);
	}
}

// ---- Hints --------------------------------------------------------------------------------------

void ULyrisHullComponent::ShowHints(bool bAboard) const
{
	if (!bAboard || State != EHullState::Afloat)
	{
		return;
	}
	if (WaterLevel < 0.02f && Breaches.Num() == 0)
	{
		return;
	}

	const int32 Percent = FMath::RoundToInt(WaterLevel * 100.f);
	FString Text = FString::Printf(TEXT("Water aboard %d%%"), Percent);
	if (Breaches.Num() > 0)
	{
		Text += FString::Printf(TEXT("   |   %d leak%s (R patch)"), Breaches.Num(), Breaches.Num() == 1 ? TEXT("") : TEXT("s"));
	}
	Text += TEXT("   |   Q bail");
	if (GetWorld()->GetTimeSeconds() < SprayHintUntil)
	{
		Text += TEXT("   |   spray is coming over the bow");
	}
	if (WaterLevel > SluggishStart)
	{
		Text += WaterLevel > 0.75f ? TEXT("   |   she's low and heavy, bail!") : TEXT("   |   she's growing sluggish");
	}

	const FColor Color = WaterLevel > 0.75f ? LyrisHull::Coral : (WaterLevel > 0.4f ? LyrisHull::Amber : LyrisHull::SeaBlue);
	ShowMessage(LyrisHull::SlotStatus, Text, Color);
}

void ULyrisHullComponent::ShowMessage(int32 Slot, const FString& Text, const FColor& Color, float Seconds)
{
	// Same on-screen style as ALyrisBoat::Hint (keys 71000 + slot), until the UI lane has a HUD for it.
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(static_cast<uint64>(71000 + Slot), Seconds, Color, Text);
	}
}

#undef LOCTEXT_NAMESPACE
