// Lyris appearance system: applies a look to a character (Player lane, task T23).
//
// The UI (character creator, barber, tailor, mirror) only talks to this component; it never touches meshes.
//
// What gets applied, to the owner's main USkeletalMeshComponent (ACharacter::GetMesh(), or TargetMesh):
//  - Body mesh per frame, if the catalog has FrameMeshes (empty until T25; the mannequin is kept).
//  - Bone scale / offset / rotation via ULyrisAppearanceAnimInstance, installed as the mesh's post-process
//    anim instance with SetOverridePostProcessAnimBP (no AnimBP asset needed).
//  - Morph targets via SetMorphTarget on the body and every part mesh (only morphs the mesh has; "_Pos/_Neg"
//    split when present). Nothing happens on the mannequin, which has no morphs; T25's mesh will.
//  - Material parameters on dynamic material instances of every section of the body and part meshes:
//    colour channels (vector "SkinTone", "HairRoot", ...), MaterialScalar sliders and part scalars
//    (scalar "Freckles_Opacity", ...), and mask slots (texture "<Slot>Mask", scalars "<Slot>Enabled", "<Slot>Index").
//  - Parts: skeletal parts as child meshes following the body with SetLeaderPoseComponent, static parts on
//    their socket. Parts without art yet spawn nothing but stay selected and saved.
//
// Changes are batched: setters only mark the component dirty, and it applies once on its next tick (also in
// the editor). OnAppearanceChanged fires after each apply.
//
// Multiplayer: TMaps do not replicate, so the look replicates as its compact share code
// (ReplicatedAppearanceCode, ReplicatedUsing = OnRep_Appearance). An owning client that changes its look
// sends it to the server (ServerSetAppearanceCode), which validates it and replicates it to everyone.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Templates/SubclassOf.h"
#include "Player/Appearance/LyrisAppearanceTypes.h"
#include "Player/Appearance/LyrisAppearanceAnimInstance.h"
#include "LyrisAppearanceComponent.generated.h"

class ULyrisAppearanceCatalog;
class USkeletalMeshComponent;
class USceneComponent;
class UMeshComponent;
class UMaterialInstanceDynamic;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnLyrisAppearanceChanged, const FLyrisAppearance&, Appearance);

UCLASS(ClassGroup = (Lyris), meta = (BlueprintSpawnableComponent))
class LYRIS_API ULyrisAppearanceComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	ULyrisAppearanceComponent();

	// ---------------------------------------------------------------- Contract API

	/** Replaces the whole look (sanitized against the catalog: ranges, People rules, adult guard). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	void SetAppearance(const FLyrisAppearance& NewAppearance);

	/** The current look (C++; Blueprints use "Get Appearance", which returns a copy). */
	const FLyrisAppearance& GetAppearance() const { return Appearance; }

	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance", meta = (DisplayName = "Get Appearance"))
	FLyrisAppearance K2_GetAppearance() const { return Appearance; }

	/**
	 * Sets one slider, clamped to its range, with the adult proportions guard applied. A part-scalar key
	 * (e.g. "Freckles.Opacity") is accepted too and stored in PartScalars. Unknown or not-offered ids are ignored.
	 * Symmetry is the UI's job: set the MirrorOf slider too if you want both sides.
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	void SetSlider(FName SliderId, float Value);

	/** Picks a part for a slot. PartId None empties an optional slot. Parts of another slot or People are ignored. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	void SetPart(FName Slot, FName PartId);

	/** Sets a colour pick (swatch index and shifts are clamped to the channel). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	void SetColor(FName Channel, const FLyrisColorPick& Pick);

	/** Sets a part scalar such as "Freckles.Opacity" or a 0/1 toggle such as "Brows.MatchHair". */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	void SetPartScalar(FName Key, float Value);

	/** Fires once per applied batch of changes (also after replication). */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Appearance")
	FOnLyrisAppearanceChanged OnAppearanceChanged;

	/** Catalog to use. Null = ULyrisAppearanceCatalog::GetDefaultCatalog(). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Appearance")
	TObjectPtr<ULyrisAppearanceCatalog> Catalog;

	// ---------------------------------------------------------------- Extra API

	/** Changes People, re-validating skin, eye-white, marking and other People-restricted picks (spec 9.10). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	void SetPeople(FName People);

	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	void SetFrame(FName Frame);

	/** The catalog actually in use (Catalog or the default). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Appearance")
	ULyrisAppearanceCatalog* GetCatalog() const;

	/** Applies pending changes right now instead of on the next tick. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Appearance")
	void ApplyNow();

	/** Mesh to drive. If unset, the owner's ACharacter mesh (or its first skeletal mesh component) is used. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Appearance")
	TObjectPtr<USkeletalMeshComponent> TargetMesh;

	/** Install ULyrisAppearanceAnimInstance as the mesh's post-process instance (needed for bone sliders). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Appearance")
	bool bDriveBones = true;

	/**
	 * Post-process class to install. Default: the native ULyrisAppearanceAnimInstance. Set it to an AnimBP child of
	 * that class only if the native path logs "no input pose" (fallback in LyrisAppearanceAnimInstance.h).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lyris|Appearance", meta = (EditCondition = "bDriveBones"))
	TSubclassOf<ULyrisAppearanceAnimInstance> PostProcessClass;

	// UActorComponent
	virtual void OnRegister() override;
	virtual void OnUnregister() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
#if WITH_EDITOR
	virtual void PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent) override;
#endif

protected:
	/** The look. Editable in the details panel for previews; changes there apply in the editor viewport. */
	UPROPERTY(EditAnywhere, Category = "Lyris|Appearance")
	FLyrisAppearance Appearance;

	/** Replicated form of Appearance (share code). Only the server writes it. */
	UPROPERTY(ReplicatedUsing = OnRep_Appearance)
	FString ReplicatedAppearanceCode;

	UFUNCTION()
	void OnRep_Appearance();

	UFUNCTION(Server, Reliable)
	void ServerSetAppearanceCode(const FString& Code);

private:
	void MarkDirty();
	/** After a local change: push to the server or to the replicated property. */
	void PublishChange();
	void ApplyPending();

	USkeletalMeshComponent* ResolveMesh() const;
	void ApplyFrameMesh(USkeletalMeshComponent* Body);
	void ApplyParts(USkeletalMeshComponent* Body);
	void ApplyBonesMorphsAndMaterials(USkeletalMeshComponent* Body);
	void DestroyParts();

	/** All mesh components that get morphs and material params: body plus parts. */
	void GatherMeshes(USkeletalMeshComponent* Body, TArray<UMeshComponent*>& Out) const;

	/** Validates a look in place and applies the 0/1 toggles' side effects (heterochromia copy). */
	void SanitizeInPlace();

	bool bDirty = true;
	/** A local change (not a replicated one) is waiting to be sent to the server / replicated property. */
	bool bPublishPending = false;

	/** Bone mods computed but not yet delivered (the post-process instance may not exist yet). */
	TMap<FName, FLyrisBoneMod> PendingBoneMods;
	bool bBonesPending = false;
	bool TryPushBoneMods(USkeletalMeshComponent* Body);

	/** Safety net for the post-process route; see TickComponent. Stops after MaxPostProcessChecks ticks. */
	bool bPostProcessVerified = false;
	int32 PostProcessChecks = 0;
	static constexpr int32 MaxPostProcessChecks = 120;

	/** Spawned part components per slot, and the part id each one shows. Transient, never saved. */
	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<USceneComponent>> PartComponents;
	TMap<FName, FName> AppliedParts;

	UPROPERTY(Transient)
	TObjectPtr<USkeletalMeshComponent> AppliedMesh;
};
