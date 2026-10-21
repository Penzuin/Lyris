// Lyris items: shows the selected hotbar item in the character's hand.

#pragma once

#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "LyrisHeldItemComponent.generated.h"

class UMaterialInterface;
class UStaticMesh;
class UStaticMeshComponent;
class ULyrisInventoryComponent;

/** One simple shape of a held-item model: an engine basic shape, placed in grip space and tinted. */
USTRUCT(BlueprintType)
struct LYRIS_API FLyrisHeldPart
{
	GENERATED_BODY()

	/** "Cube", "Cylinder", "Sphere" or "Cone" (the /Engine/BasicShapes meshes, 100 cm across). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Held Item")
	FName Shape = TEXT("Cube");

	/** In grip space (cm): origin at the fist, +Z along the handle away from the hand, +X where the tool head points. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Held Item")
	FVector Location = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Held Item")
	FRotator Rotation = FRotator::ZeroRotator;

	/** Size in cm. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Held Item")
	FVector Size = FVector(10.f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Held Item")
	FLinearColor Colour = FLinearColor::White;
};

/**
 * Put this on the character next to its ULyrisInventoryComponent. Whenever the active hotbar item
 * changes, it builds a small model of that item and holds it in the right hand: tools in the fist
 * with the head forward, seeds, crops and materials resting in the palm.
 *
 * Until items have real meshes, each model is a few engine basic shapes in the item's colours
 * (see BuildModel in the .cpp; an item without its own model gets one for its category). When an
 * item asset gains a mesh, swap BuildModel for that mesh.
 *
 * Placement follows the hand's position every frame and turns with the character, so the item is
 * always held upright and readable whatever the hand bone's axes are. Tune the grip with
 * GripOffset / GripRotation, or live with the console:
 *   lyris.HeldItem.Grip <pitch> <yaw> <roll> <x> <y> <z>
 */
UCLASS(ClassGroup = (Lyris), meta = (BlueprintSpawnableComponent))
class LYRIS_API ULyrisHeldItemComponent : public USceneComponent
{
	GENERATED_BODY()

public:
	ULyrisHeldItemComponent();

	/** The skeletal mesh socket or bone the item sits at. UE5 mannequins have hand_r. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Held Item")
	FName HandSocket = TEXT("hand_r");

	/** Grip-space offset from the hand, in the character's frame (cm): +X forward, +Y right, +Z up. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Held Item")
	FVector GripOffset = FVector(6.f, 2.f, -2.f);

	/** How a tool is tilted in the hand, relative to the character (pitch tips the head forward). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Held Item")
	FRotator GripRotation = FRotator(-20.f, 0.f, 0.f);

	/** Hide the held item (while swimming, sailing, in cutscenes). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Held Item")
	void SetHeldHidden(bool bHidden);

	UFUNCTION(BlueprintPure, Category = "Lyris|Held Item")
	FName GetHeldItemId() const { return ShownItemId; }

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	void Rebuild(FName ItemId);
	void ClearParts();
	void UpdatePlacement();
	static TArray<FLyrisHeldPart> BuildModel(FName ItemId, uint8 Category);

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> Parts;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> BaseMaterial;

	TWeakObjectPtr<ULyrisInventoryComponent> Inventory;
	FName ShownItemId;
	bool bHeldHidden = false;
};
