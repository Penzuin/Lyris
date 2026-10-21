// Lyris items: shows the selected hotbar item in the character's hand.

#include "Items/LyrisHeldItemComponent.h"

#include "Items/LyrisInventoryComponent.h"
#include "Items/LyrisItemDefinition.h"

#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

namespace LyrisHeldItem
{
	static bool bGripOverride = false;
	static FRotator GripRotationOverride = FRotator::ZeroRotator;
	static FVector GripOffsetOverride = FVector::ZeroVector;

	static FAutoConsoleCommand GripCommand(
		TEXT("lyris.HeldItem.Grip"),
		TEXT("Tunes how held items sit in the hand: lyris.HeldItem.Grip <pitch> <yaw> <roll> <x> <y> <z>. No arguments resets."),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& Args)
		{
			if (Args.Num() < 6)
			{
				bGripOverride = false;
				UE_LOG(LogTemp, Log, TEXT("lyris.HeldItem.Grip: back to each component's GripRotation / GripOffset."));
				return;
			}
			GripRotationOverride = FRotator(FCString::Atof(*Args[0]), FCString::Atof(*Args[1]), FCString::Atof(*Args[2]));
			GripOffsetOverride = FVector(FCString::Atof(*Args[3]), FCString::Atof(*Args[4]), FCString::Atof(*Args[5]));
			bGripOverride = true;
			UE_LOG(LogTemp, Log, TEXT("lyris.HeldItem.Grip: rotation %s offset %s"), *GripRotationOverride.ToString(),
				*GripOffsetOverride.ToString());
		}));

	// Colours.
	static const FLinearColor WoodColour(0.42f, 0.25f, 0.14f);
	static const FLinearColor IronColour(0.56f, 0.6f, 0.65f);
	static const FLinearColor TealColour(0.2f, 0.52f, 0.5f);
	static const FLinearColor StoneColour(0.48f, 0.45f, 0.43f);
	static const FLinearColor CopperColour(0.75f, 0.38f, 0.17f);
	static const FLinearColor VerdigrisColour(0.22f, 0.6f, 0.45f);
	static const FLinearColor CrystalColour(0.72f, 0.7f, 1.f);
	static const FLinearColor LeafColour(0.35f, 0.6f, 0.28f);
	static const FLinearColor BurlapColour(0.72f, 0.58f, 0.38f);
	static const FLinearColor TieColour(0.62f, 0.26f, 0.2f);
	static const FLinearColor BerryColour(0.36f, 0.42f, 0.85f);
	static const FLinearColor BellColour(0.98f, 0.95f, 0.82f);
	static const FLinearColor TurnipColour(0.95f, 0.92f, 0.95f);
	static const FLinearColor TurnipTopColour(0.6f, 0.38f, 0.7f);

	static FLyrisHeldPart Part(FName Shape, FVector Location, FVector Size, FLinearColor Colour, FRotator Rotation = FRotator::ZeroRotator)
	{
		FLyrisHeldPart P;
		P.Shape = Shape;
		P.Location = Location;
		P.Size = Size;
		P.Colour = Colour;
		P.Rotation = Rotation;
		return P;
	}

	static const FName Cube(TEXT("Cube"));
	static const FName Cylinder(TEXT("Cylinder"));
	static const FName Sphere(TEXT("Sphere"));
	static const FName Cone(TEXT("Cone"));
	// Cones point along +Z; these turn them to point forward (+X) or back (-X).
	static const FRotator PointForward(-90.f, 0.f, 0.f);
	static const FRotator PointBack(90.f, 0.f, 0.f);

	/** A wooden handle from just below the fist up to Length cm. */
	static FLyrisHeldPart Handle(float Length)
	{
		return Part(Cylinder, FVector(0.f, 0.f, Length * 0.5f - 10.f), FVector(3.2f, 3.2f, Length), WoodColour);
	}
}

ULyrisHeldItemComponent::ULyrisHeldItemComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PostUpdateWork;  // after animation, so the hand is where it'll be drawn
	SetUsingAbsoluteLocation(true);
	SetUsingAbsoluteRotation(true);
	SetUsingAbsoluteScale(true);
}

void ULyrisHeldItemComponent::BeginPlay()
{
	Super::BeginPlay();
	Inventory = GetOwner() ? GetOwner()->FindComponentByClass<ULyrisInventoryComponent>() : nullptr;
	BaseMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
}

void ULyrisHeldItemComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	ClearParts();
	Super::EndPlay(EndPlayReason);
}

void ULyrisHeldItemComponent::SetHeldHidden(bool bHidden)
{
	if (bHeldHidden == bHidden)
	{
		return;
	}
	bHeldHidden = bHidden;
	for (UStaticMeshComponent* PartComponent : Parts)
	{
		if (PartComponent)
		{
			PartComponent->SetHiddenInGame(bHidden);
		}
	}
}

void ULyrisHeldItemComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (!Inventory.IsValid() && GetOwner())
	{
		Inventory = GetOwner()->FindComponentByClass<ULyrisInventoryComponent>();  // added after us
	}
	const ULyrisItemDefinition* Active = Inventory.IsValid() ? Inventory->GetActiveItem() : nullptr;
	const FName Wanted = Active ? Active->ItemId : NAME_None;
	if (Wanted != ShownItemId)
	{
		Rebuild(Wanted);
	}
	if (Parts.Num() > 0)
	{
		UpdatePlacement();
	}
}

void ULyrisHeldItemComponent::UpdatePlacement()
{
	const AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}
	FVector Hand = Owner->GetActorLocation();
	const ACharacter* Character = Cast<ACharacter>(Owner);
	const USkeletalMeshComponent* Mesh = Character ? Character->GetMesh() : nullptr;
	if (Mesh && Mesh->DoesSocketExist(HandSocket))
	{
		Hand = Mesh->GetSocketLocation(HandSocket);
	}
	const FRotator GripRot = LyrisHeldItem::bGripOverride ? LyrisHeldItem::GripRotationOverride : GripRotation;
	const FVector GripOff = LyrisHeldItem::bGripOverride ? LyrisHeldItem::GripOffsetOverride : GripOffset;
	const FQuat Facing = FRotator(0.f, Owner->GetActorRotation().Yaw, 0.f).Quaternion();
	SetWorldLocationAndRotation(Hand + Facing.RotateVector(GripOff), Facing * GripRot.Quaternion());
}

void ULyrisHeldItemComponent::ClearParts()
{
	for (UStaticMeshComponent* PartComponent : Parts)
	{
		if (PartComponent)
		{
			PartComponent->DestroyComponent();
		}
	}
	Parts.Reset();
}

void ULyrisHeldItemComponent::Rebuild(FName ItemId)
{
	ClearParts();
	ShownItemId = ItemId;
	AActor* Owner = GetOwner();
	if (ItemId.IsNone() || !Owner)
	{
		return;
	}
	const ULyrisItemDefinition* Def = Inventory.IsValid() ? Inventory->GetActiveItem() : nullptr;
	const TArray<FLyrisHeldPart> Model = BuildModel(ItemId, Def ? static_cast<uint8>(Def->Category) : 0);

	for (const FLyrisHeldPart& Spec : Model)
	{
		const FString Path = FString::Printf(TEXT("/Engine/BasicShapes/%s.%s"), *Spec.Shape.ToString(), *Spec.Shape.ToString());
		UStaticMesh* ShapeMesh = LoadObject<UStaticMesh>(nullptr, *Path);
		if (!ShapeMesh)
		{
			continue;
		}
		UStaticMeshComponent* PartComponent = NewObject<UStaticMeshComponent>(Owner);
		PartComponent->SetStaticMesh(ShapeMesh);
		PartComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		PartComponent->SetCanEverAffectNavigation(false);
		PartComponent->SetGenerateOverlapEvents(false);
		PartComponent->SetupAttachment(this);
		PartComponent->RegisterComponent();
		PartComponent->SetRelativeLocationAndRotation(Spec.Location, Spec.Rotation);
		PartComponent->SetRelativeScale3D(Spec.Size / 100.f);  // basic shapes are 100 cm across
		if (BaseMaterial)
		{
			UMaterialInstanceDynamic* Tinted = UMaterialInstanceDynamic::Create(BaseMaterial, PartComponent);
			Tinted->SetVectorParameterValue(TEXT("Color"), Spec.Colour);
			PartComponent->SetMaterial(0, Tinted);
		}
		PartComponent->SetHiddenInGame(bHeldHidden);
		Parts.Add(PartComponent);
	}
	UpdatePlacement();
}

TArray<FLyrisHeldPart> ULyrisHeldItemComponent::BuildModel(FName ItemId, uint8 Category)
{
	using namespace LyrisHeldItem;
	TArray<FLyrisHeldPart> M;
	const FString Id = ItemId.ToString();

	if (Id == TEXT("tool_pickaxe"))
	{
		M.Add(Handle(68.f));
		M.Add(Part(Cube, FVector(0.f, 0.f, 56.f), FVector(30.f, 4.5f, 5.5f), IronColour));
		M.Add(Part(Cone, FVector(20.f, 0.f, 55.f), FVector(5.f, 4.5f, 12.f), IronColour, PointForward));
		M.Add(Part(Cone, FVector(-20.f, 0.f, 55.f), FVector(5.f, 4.5f, 12.f), IronColour, PointBack));
	}
	else if (Id == TEXT("tool_axe"))
	{
		M.Add(Handle(64.f));
		M.Add(Part(Cube, FVector(9.f, 0.f, 50.f), FVector(15.f, 2.2f, 17.f), IronColour));
		M.Add(Part(Cube, FVector(-2.f, 0.f, 50.f), FVector(7.f, 5.f, 7.f), IronColour));
	}
	else if (Id == TEXT("tool_hoe"))
	{
		M.Add(Handle(82.f));
		M.Add(Part(Cube, FVector(7.f, 0.f, 70.f), FVector(13.f, 12.f, 2.2f), IronColour, FRotator(-15.f, 0.f, 0.f)));
		M.Add(Part(Cube, FVector(0.5f, 0.f, 70.f), FVector(3.f, 5.f, 6.f), IronColour));
	}
	else if (Id == TEXT("tool_watering_can"))
	{
		M.Add(Part(Cube, FVector(0.f, 0.f, 2.f), FVector(3.f, 3.f, 10.f), TealColour));             // handle in the fist
		M.Add(Part(Cylinder, FVector(6.f, 0.f, -14.f), FVector(20.f, 20.f, 20.f), TealColour));     // body
		M.Add(Part(Cylinder, FVector(20.f, 0.f, -9.f), FVector(3.5f, 3.5f, 22.f), TealColour, FRotator(-50.f, 0.f, 0.f)));
		M.Add(Part(Sphere, FVector(28.f, 0.f, -2.f), FVector(7.f, 7.f, 7.f), FLinearColor(0.55f, 0.8f, 0.75f)));
		M.Add(Part(Cylinder, FVector(6.f, 0.f, -3.f), FVector(21.f, 21.f, 2.5f), WoodColour));      // rim band
	}
	else if (Id == TEXT("stone"))
	{
		M.Add(Part(Sphere, FVector(6.f, 0.f, 0.f), FVector(11.f, 10.f, 8.5f), StoneColour, FRotator(10.f, 30.f, 0.f)));
	}
	else if (Id == TEXT("copper_ore"))
	{
		M.Add(Part(Sphere, FVector(6.f, 0.f, 0.f), FVector(11.f, 10.f, 9.f), StoneColour, FRotator(10.f, 30.f, 0.f)));
		M.Add(Part(Cube, FVector(9.f, 3.f, 3.f), FVector(4.f, 4.f, 4.f), CopperColour, FRotator(20.f, 45.f, 10.f)));
		M.Add(Part(Cube, FVector(4.f, -4.f, 3.f), FVector(3.5f, 3.5f, 3.5f), VerdigrisColour, FRotator(-15.f, 20.f, 30.f)));
	}
	else if (Id == TEXT("star_crystal"))
	{
		M.Add(Part(Cone, FVector(6.f, 0.f, 4.f), FVector(5.5f, 5.5f, 15.f), CrystalColour));
		M.Add(Part(Cone, FVector(9.f, 3.f, 1.f), FVector(3.5f, 3.5f, 9.f), FLinearColor(0.7f, 0.9f, 1.f), FRotator(0.f, 0.f, 20.f)));
	}
	else if (Id == TEXT("wood"))
	{
		M.Add(Part(Cylinder, FVector(6.f, 0.f, 0.f), FVector(7.5f, 7.5f, 28.f), WoodColour, FRotator(0.f, 0.f, 90.f)));
	}
	else if (Id == TEXT("sea_herb"))
	{
		M.Add(Part(Cylinder, FVector(5.f, 0.f, 8.f), FVector(1.f, 1.f, 22.f), LeafColour));
		for (int32 k = 0; k < 3; ++k)
		{
			M.Add(Part(Sphere, FVector(5.f + (k % 2 ? 3.f : -3.f), 0.f, 6.f + k * 6.f), FVector(6.f, 2.f, 3.f), LeafColour,
				FRotator(0.f, 0.f, k % 2 ? 30.f : -30.f)));
		}
	}
	else if (Id == TEXT("mistberry"))
	{
		M.Add(Part(Sphere, FVector(6.f, -2.f, 0.f), FVector(5.f), BerryColour));
		M.Add(Part(Sphere, FVector(6.f, 3.f, 0.f), FVector(5.f), BerryColour));
		M.Add(Part(Sphere, FVector(7.f, 0.5f, 4.f), FVector(5.f), BerryColour));
		M.Add(Part(Sphere, FVector(6.f, 0.f, 8.f), FVector(6.f, 2.f, 3.f), LeafColour));
	}
	else if (Id == TEXT("moonbell"))
	{
		M.Add(Part(Cylinder, FVector(5.f, 0.f, 6.f), FVector(1.f, 1.f, 18.f), LeafColour));
		M.Add(Part(Cone, FVector(5.f, 0.f, 16.f), FVector(9.f, 9.f, 10.f), BellColour, FRotator(180.f, 0.f, 0.f)));
	}
	else if (Id == TEXT("harbor_turnip"))
	{
		M.Add(Part(Sphere, FVector(6.f, 0.f, 0.f), FVector(10.f, 10.f, 11.f), TurnipColour));
		M.Add(Part(Sphere, FVector(6.f, 0.f, 3.5f), FVector(10.5f, 10.5f, 5.f), TurnipTopColour));
		M.Add(Part(Cone, FVector(6.f, 0.f, 10.f), FVector(4.f, 4.f, 10.f), LeafColour));
	}
	else if (Id.StartsWith(TEXT("seed_")))
	{
		FLinearColor Mark = LeafColour;
		if (Id.Contains(TEXT("mistberry")))
		{
			Mark = BerryColour;
		}
		else if (Id.Contains(TEXT("moonbell")))
		{
			Mark = BellColour;
		}
		else if (Id.Contains(TEXT("turnip")))
		{
			Mark = TurnipTopColour;
		}
		M.Add(Part(Sphere, FVector(6.f, 0.f, 0.f), FVector(9.f, 9.f, 10.f), BurlapColour));
		M.Add(Part(Cylinder, FVector(6.f, 0.f, 5.f), FVector(5.5f, 5.5f, 1.8f), TieColour));
		M.Add(Part(Sphere, FVector(6.f, 0.f, 7.f), FVector(4.f, 4.f, 3.f), Mark));
	}
	else
	{
		// Anything without its own model: something that fits its category.
		switch (static_cast<ELyrisItemCategory>(Category))
		{
		case ELyrisItemCategory::Tool:
			M.Add(Handle(60.f));
			M.Add(Part(Cube, FVector(4.f, 0.f, 50.f), FVector(12.f, 4.f, 8.f), IronColour));
			break;
		case ELyrisItemCategory::Seed:
			M.Add(Part(Sphere, FVector(6.f, 0.f, 0.f), FVector(9.f, 9.f, 10.f), BurlapColour));
			break;
		case ELyrisItemCategory::Food:
		case ELyrisItemCategory::Collectible:
			M.Add(Part(Sphere, FVector(6.f, 0.f, 0.f), FVector(8.f), LeafColour));
			break;
		default:
			M.Add(Part(Cube, FVector(6.f, 0.f, 0.f), FVector(8.f), StoneColour, FRotator(10.f, 25.f, 5.f)));
			break;
		}
	}
	return M;
}
