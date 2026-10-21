// Lyris appearance system: applies a look to a character (Player lane, task T23). See the header.

#include "Player/Appearance/LyrisAppearanceComponent.h"
#include "Player/Appearance/LyrisAppearanceCatalog.h"
#include "Player/Appearance/LyrisAppearanceLibrary.h"
#include "Player/Appearance/LyrisAppearanceAnimInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Animation/MorphTarget.h"
#include "Net/UnrealNetwork.h"
#include "Lyris.h"

namespace
{
	/** Share codes are a few KB at most; anything bigger from a client is rejected. */
	constexpr int32 MaxShareCodeLength = 32 * 1024;

	bool IsGameWorld(const UActorComponent* C)
	{
		const UWorld* World = C ? C->GetWorld() : nullptr;
		return World && World->IsGameWorld();
	}
}

ULyrisAppearanceComponent::ULyrisAppearanceComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
	PrimaryComponentTick.TickGroup = TG_PrePhysics;
	bTickInEditor = true; // so looks edited in the details panel show in the editor viewport
	SetIsReplicatedByDefault(true);
	PostProcessClass = ULyrisAppearanceAnimInstance::StaticClass();
}

// =====================================================================================================
// Setters (contract)
// =====================================================================================================

ULyrisAppearanceCatalog* ULyrisAppearanceComponent::GetCatalog() const
{
	return Catalog ? Catalog.Get() : ULyrisAppearanceCatalog::GetDefaultCatalog();
}

void ULyrisAppearanceComponent::SetAppearance(const FLyrisAppearance& NewAppearance)
{
	Appearance = NewAppearance;
	SanitizeInPlace();
	bPublishPending = true;
	MarkDirty();
}

void ULyrisAppearanceComponent::SetSlider(FName SliderId, float Value)
{
	const ULyrisAppearanceCatalog* C = GetCatalog();
	if (!C)
	{
		return;
	}
	if (const FLyrisSliderDef* Def = C->FindSlider(SliderId))
	{
		if (!Def->AllowsPeople(Appearance.People))
		{
			return;
		}
		Appearance.Sliders.Add(SliderId, Def->ClampValue(Value));
		ULyrisAppearanceLibrary::ApplyAdultGuard(Appearance); // spec 6.2
		bPublishPending = true;
		MarkDirty();
	}
	else if (C->FindPartScalar(SliderId))
	{
		SetPartScalar(SliderId, Value);
	}
}

void ULyrisAppearanceComponent::SetPart(FName Slot, FName PartId)
{
	const ULyrisAppearanceCatalog* C = GetCatalog();
	const FLyrisPartSlotDef* SlotDef = C ? C->FindSlot(Slot) : nullptr;
	if (!SlotDef)
	{
		return;
	}
	if (PartId.IsNone())
	{
		if (!SlotDef->bOptional)
		{
			return;
		}
	}
	else
	{
		const FLyrisPartDef* Part = C->FindPart(PartId);
		if (!Part || Part->Slot != Slot || !Part->AllowsPeople(Appearance.People))
		{
			return;
		}
	}
	Appearance.Parts.Add(Slot, PartId);
	bPublishPending = true;
	MarkDirty();
}

void ULyrisAppearanceComponent::SetColor(FName Channel, const FLyrisColorPick& Pick)
{
	const ULyrisAppearanceCatalog* C = GetCatalog();
	const FLyrisColorChannelDef* Ch = C ? C->FindChannel(Channel) : nullptr;
	if (!Ch || !Ch->AllowsPeople(Appearance.People))
	{
		return;
	}
	FLyrisColorPick Clean = Pick;
	Clean.Swatch = FMath::Clamp(Clean.Swatch, 0, FMath::Max(Ch->Swatches.Num() - 1, 0));
	Clean.HueShift = FMath::Clamp(Clean.HueShift, -Ch->MaxHueShift, Ch->MaxHueShift);
	Clean.ValueShift = FMath::Clamp(Clean.ValueShift, -Ch->MaxValueShift, Ch->MaxValueShift);
	Appearance.Colors.Add(Channel, Clean);

	// Heterochromia off: the right iris follows the left one (spec 3.3).
	if (Channel == LyrisAppearanceIds::ChannelIrisL &&
		ULyrisAppearanceLibrary::GetPartScalarValue(C, Appearance, LyrisAppearanceIds::EyesHeterochromia) < 0.5f)
	{
		Appearance.Colors.Add(LyrisAppearanceIds::ChannelIrisR, Clean);
	}
	bPublishPending = true;
	MarkDirty();
}

void ULyrisAppearanceComponent::SetPartScalar(FName Key, float Value)
{
	const ULyrisAppearanceCatalog* C = GetCatalog();
	if (!C)
	{
		return;
	}
	const FLyrisSliderDef* Def = C->FindPartScalar(Key);
	if (!Def)
	{
		if (C->FindSlider(Key))
		{
			SetSlider(Key, Value);
		}
		return;
	}
	if (!Def->AllowsPeople(Appearance.People))
	{
		return;
	}
	float V = Def->ClampValue(Value);
	if (ULyrisAppearanceLibrary::IsToggleKey(Key))
	{
		V = V >= 0.5f ? 1.f : 0.f;
	}
	Appearance.PartScalars.Add(Key, V);

	if (Key == LyrisAppearanceIds::EyesHeterochromia && V < 0.5f)
	{
		if (const FLyrisColorPick* Left = Appearance.Colors.Find(LyrisAppearanceIds::ChannelIrisL))
		{
			const FLyrisColorPick Copy = *Left;
			Appearance.Colors.Add(LyrisAppearanceIds::ChannelIrisR, Copy);
		}
	}
	bPublishPending = true;
	MarkDirty();
}

void ULyrisAppearanceComponent::SetPeople(FName People)
{
	if (People == Appearance.People)
	{
		return;
	}
	ULyrisAppearanceLibrary::ChangePeople(GetCatalog(), Appearance, People);
	bPublishPending = true;
	MarkDirty();
}

void ULyrisAppearanceComponent::SetFrame(FName Frame)
{
	const ULyrisAppearanceCatalog* C = GetCatalog();
	if (C && C->Frames.Contains(Frame) && Frame != Appearance.Frame)
	{
		Appearance.Frame = Frame;
		bPublishPending = true;
		MarkDirty();
	}
}

void ULyrisAppearanceComponent::SanitizeInPlace()
{
	ULyrisAppearanceLibrary::SanitizeAppearance(GetCatalog(), Appearance);
}

void ULyrisAppearanceComponent::MarkDirty()
{
	bDirty = true;
}

void ULyrisAppearanceComponent::ApplyNow()
{
	ApplyPending();
}

// =====================================================================================================
// Lifecycle
// =====================================================================================================

void ULyrisAppearanceComponent::OnRegister()
{
	Super::OnRegister();
	// The server publishes its starting look (e.g. one set in the details panel) so clients see it too.
	if (IsGameWorld(this) && GetOwner() && GetOwner()->HasAuthority())
	{
		bPublishPending = true;
	}
	// Apply straight away so editor previews (and the first frame in game) show the look. The owner's mesh
	// may register after us, so stay dirty and apply once more on the first tick.
	ApplyPending();
	bDirty = true;
}

void ULyrisAppearanceComponent::OnUnregister()
{
	DestroyParts();
	Super::OnUnregister();
}

void ULyrisAppearanceComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (bDirty)
	{
		ApplyPending();
	}
	else if (bBonesPending)
	{
		TryPushBoneMods(ResolveMesh());
	}

	// Safety net for the native post-process route (not verified in an editor build): if the instance reports
	// that it never received the main instance's pose, remove it so the character keeps animating, and say how
	// to enable the AnimBP fallback. The counters are read through GetProxyOnGameThread, which waits for the
	// parallel anim task, so this runs only during a short window (MaxPostProcessChecks ticks with an instance)
	// and then stops for good.
	if (bDriveBones && !bPostProcessVerified)
	{
		if (USkeletalMeshComponent* Body = ResolveMesh())
		{
			if (ULyrisAppearanceAnimInstance* Instance = Cast<ULyrisAppearanceAnimInstance>(Body->GetPostProcessInstance()))
			{
				if (++PostProcessChecks >= MaxPostProcessChecks)
				{
					bPostProcessVerified = true; // window over: stop paying for the wait
				}
				// Give up only after many evaluations without a single good one (the first frames, or a LOD
				// switch, may legitimately miss once).
				if (Instance->GetEvaluationCount() == 0 && Instance->GetMissedEvaluationCount() >= 30)
				{
					UE_LOG(LogLyris, Warning, TEXT("LyrisAppearance: the native post-process anim instance got no input pose on %s. Bone sliders are off; see the AnimBP fallback in LyrisAppearanceAnimInstance.h."), *GetNameSafe(GetOwner()));
					bDriveBones = false;
					Body->SetOverridePostProcessAnimBP(TSubclassOf<UAnimInstance>());
				}
				else if (Instance->GetEvaluationCount() >= 10)
				{
					bPostProcessVerified = true; // it has really evaluated with a pose; stop checking
				}
			}
		}
	}
}

#if WITH_EDITOR
void ULyrisAppearanceComponent::PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent)
{
	Super::PostEditChangeProperty(PropertyChangedEvent);
	SanitizeInPlace();
	MarkDirty();
}
#endif

// =====================================================================================================
// Replication
// =====================================================================================================

void ULyrisAppearanceComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ULyrisAppearanceComponent, ReplicatedAppearanceCode);
}

void ULyrisAppearanceComponent::OnRep_Appearance()
{
	FLyrisAppearance Incoming;
	if (ULyrisAppearanceLibrary::FromShareCode(ReplicatedAppearanceCode, Incoming))
	{
		Appearance = Incoming;
		SanitizeInPlace();
		MarkDirty(); // not bPublishPending: this came from the server
	}
}

void ULyrisAppearanceComponent::ServerSetAppearanceCode_Implementation(const FString& Code)
{
	if (Code.Len() > MaxShareCodeLength)
	{
		return;
	}
	FLyrisAppearance Incoming;
	if (ULyrisAppearanceLibrary::FromShareCode(Code, Incoming)) // validates and applies the adult guard
	{
		SetAppearance(Incoming);
	}
}

void ULyrisAppearanceComponent::PublishChange()
{
	bPublishPending = false;
	AActor* Owner = GetOwner();
	if (!Owner || !IsGameWorld(this))
	{
		return;
	}
	const FString Code = ULyrisAppearanceLibrary::ToShareCode(Appearance);
	if (Owner->HasAuthority())
	{
		ReplicatedAppearanceCode = Code;
	}
	else if (Owner->GetLocalRole() == ROLE_AutonomousProxy)
	{
		// Owning client: at most one RPC per frame because publishing happens in ApplyPending.
		ServerSetAppearanceCode(Code);
	}
}

// =====================================================================================================
// Applying
// =====================================================================================================

USkeletalMeshComponent* ULyrisAppearanceComponent::ResolveMesh() const
{
	if (TargetMesh)
	{
		return TargetMesh;
	}
	const AActor* Owner = GetOwner();
	if (!Owner)
	{
		return nullptr;
	}
	if (const ACharacter* Character = Cast<ACharacter>(Owner))
	{
		return Character->GetMesh();
	}
	// Any skeletal mesh that is not one of our own part components.
	TInlineComponentArray<USkeletalMeshComponent*> Meshes(Owner);
	for (USkeletalMeshComponent* Mesh : Meshes)
	{
		bool bIsPart = false;
		for (const TPair<FName, TObjectPtr<USceneComponent>>& KV : PartComponents)
		{
			bIsPart |= (KV.Value.Get() == Mesh);
		}
		if (!bIsPart)
		{
			return Mesh;
		}
	}
	return nullptr;
}

void ULyrisAppearanceComponent::ApplyPending()
{
	if (IsTemplate() || (GetOwner() && GetOwner()->IsTemplate()))
	{
		return; // never spawn parts or material instances into Blueprint defaults
	}
	USkeletalMeshComponent* Body = ResolveMesh();
	if (!Body || !GetCatalog())
	{
		return; // stay dirty; try again next tick
	}
	bDirty = false;

	if (AppliedMesh.Get() != Body)
	{
		DestroyParts();
		AppliedMesh = Body;
	}

	ApplyFrameMesh(Body);
	ApplyParts(Body);
	ApplyBonesMorphsAndMaterials(Body);

	if (bPublishPending)
	{
		PublishChange();
	}
	OnAppearanceChanged.Broadcast(Appearance);
}

void ULyrisAppearanceComponent::ApplyFrameMesh(USkeletalMeshComponent* Body)
{
	const ULyrisAppearanceCatalog* C = GetCatalog();
	const TSoftObjectPtr<USkeletalMesh>* Soft = C->FrameMeshes.Find(Appearance.Frame);
	if (!Soft || Soft->IsNull())
	{
		return; // keep whatever mesh the character Blueprint set (the template mannequin until T25)
	}
	USkeletalMesh* Mesh = Soft->LoadSynchronous();
	if (Mesh && Body->GetSkeletalMeshAsset() != Mesh)
	{
		Body->SetSkeletalMeshAsset(Mesh);
	}
}

void ULyrisAppearanceComponent::DestroyParts()
{
	for (TPair<FName, TObjectPtr<USceneComponent>>& KV : PartComponents)
	{
		if (USceneComponent* Comp = KV.Value.Get())
		{
			if (IsValid(Comp))
			{
				Comp->DestroyComponent();
			}
		}
	}
	PartComponents.Reset();
	AppliedParts.Reset();
}

void ULyrisAppearanceComponent::ApplyParts(USkeletalMeshComponent* Body)
{
	const ULyrisAppearanceCatalog* C = GetCatalog();
	AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}

	for (const FLyrisPartSlotDef& Slot : C->Slots)
	{
		if (Slot.bMask || Slot.Category == LyrisAppearanceIds::CategoryLantern)
		{
			continue; // masks go to materials; the lantern is spawned by gameplay, not by the look
		}
		const FName PartId = ULyrisAppearanceLibrary::GetEffectivePart(C, Appearance, Slot.Slot);
		const FName* Current = AppliedParts.Find(Slot.Slot);
		if (Current && *Current == PartId)
		{
			continue;
		}

		// Remove the old part of this slot.
		if (TObjectPtr<USceneComponent>* Old = PartComponents.Find(Slot.Slot))
		{
			if (USceneComponent* OldComp = Old->Get())
			{
				if (IsValid(OldComp))
				{
					OldComp->DestroyComponent();
				}
			}
			PartComponents.Remove(Slot.Slot);
		}
		AppliedParts.Add(Slot.Slot, PartId);

		const FLyrisPartDef* Part = PartId.IsNone() ? nullptr : C->FindPart(PartId);
		if (!Part)
		{
			continue;
		}

		if (!Part->SkeletalMesh.IsNull())
		{
			if (USkeletalMesh* Mesh = Part->SkeletalMesh.LoadSynchronous())
			{
				USkeletalMeshComponent* Comp = NewObject<USkeletalMeshComponent>(Owner, NAME_None, RF_Transient);
				Comp->SetupAttachment(Body);
				Comp->SetSkeletalMeshAsset(Mesh);
				Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				Comp->RegisterComponent();
				Comp->SetLeaderPoseComponent(Body); // follows the body's (appearance-adjusted) pose
				PartComponents.Add(Slot.Slot, Comp);
			}
		}
		else if (!Part->StaticMesh.IsNull())
		{
			if (UStaticMesh* Mesh = Part->StaticMesh.LoadSynchronous())
			{
				UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(Owner, NAME_None, RF_Transient);
				Comp->SetupAttachment(Body, Part->AttachSocket);
				Comp->SetStaticMesh(Mesh);
				Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				Comp->RegisterComponent();
				PartComponents.Add(Slot.Slot, Comp);
			}
		}
		// No art yet: nothing spawns, but the choice stays in the look and is saved.
	}
}

void ULyrisAppearanceComponent::GatherMeshes(USkeletalMeshComponent* Body, TArray<UMeshComponent*>& Out) const
{
	Out.Add(Body);
	for (const TPair<FName, TObjectPtr<USceneComponent>>& KV : PartComponents)
	{
		if (UMeshComponent* Mesh = Cast<UMeshComponent>(KV.Value.Get()))
		{
			Out.Add(Mesh);
		}
	}
}

bool ULyrisAppearanceComponent::TryPushBoneMods(USkeletalMeshComponent* Body)
{
	if (!Body)
	{
		return false;
	}
	if (ULyrisAppearanceAnimInstance* Instance = Cast<ULyrisAppearanceAnimInstance>(Body->GetPostProcessInstance()))
	{
		Instance->SetBoneMods(PendingBoneMods);
		bBonesPending = false;
		return true;
	}
	// The mesh creates the post-process instance when it initialises its anim (needs a skeletal mesh asset).
	bBonesPending = bDriveBones && Body->GetSkeletalMeshAsset() != nullptr;
	return false;
}

void ULyrisAppearanceComponent::ApplyBonesMorphsAndMaterials(USkeletalMeshComponent* Body)
{
	const ULyrisAppearanceCatalog* C = GetCatalog();
	using EKind = ELyrisAppearanceTargetKind;

	TMap<FName, FLyrisBoneMod> Bones;
	TMap<FName, float> Morphs;
	TMap<FName, float> Scalars;

	// --- 1. Accumulate slider and part-scalar targets ------------------------------------------------
	auto Accumulate = [&](const FLyrisSliderDef& Def, float V)
	{
		for (const FLyrisSliderTarget& T : Def.Targets)
		{
			const float VW = V * T.Weight;
			switch (T.Kind)
			{
			case EKind::MorphTarget:
				Morphs.FindOrAdd(T.Name) += VW;
				break;
			case EKind::MaterialScalar:
				Scalars.FindOrAdd(T.Name) += VW;
				break;
			case EKind::BoneScale:
			{
				if (FMath::IsNearlyZero(VW))
				{
					break;
				}
				FLyrisBoneMod& M = Bones.FindOrAdd(T.Name);
				const bool bUniform = FMath::IsNearlyEqual(T.Axis.X, T.Axis.Y) && FMath::IsNearlyEqual(T.Axis.Y, T.Axis.Z);
				if (bUniform)
				{
					M.UniformScale *= 1.f + T.Axis.X * VW;
				}
				else
				{
					M.ShapeScale *= FVector::OneVector + T.Axis * VW;
				}
				break;
			}
			case EKind::BoneOffset:
				if (!FMath::IsNearlyZero(VW))
				{
					Bones.FindOrAdd(T.Name).Offset += T.Axis * VW;
				}
				break;
			case EKind::BoneRotation:
				if (!FMath::IsNearlyZero(VW))
				{
					Bones.FindOrAdd(T.Name).Rotation += FRotator(T.Axis.X * VW, T.Axis.Y * VW, T.Axis.Z * VW);
				}
				break;
			default:
				break;
			}
		}
	};

	for (const FLyrisSliderDef& Def : C->Sliders)
	{
		Accumulate(Def, ULyrisAppearanceLibrary::GetSliderValue(Appearance, Def));
	}
	for (const FLyrisSliderDef& Def : C->PartScalarDefs)
	{
		Accumulate(Def, ULyrisAppearanceLibrary::GetPartScalarValue(C, Appearance, Def.Id));
	}
	// Part scalars the catalog does not describe: param named after the key ('.' -> '_').
	for (const TPair<FName, float>& KV : Appearance.PartScalars)
	{
		if (!C->FindPartScalar(KV.Key) && !C->FindSlider(KV.Key))
		{
			Scalars.FindOrAdd(FName(*KV.Key.ToString().Replace(TEXT("."), TEXT("_")))) = KV.Value;
		}
	}

	// --- 2. Bones: hand to the post-process anim instance --------------------------------------------
	if (bDriveBones)
	{
		UClass* Wanted = PostProcessClass ? PostProcessClass.Get() : ULyrisAppearanceAnimInstance::StaticClass();
		if (Body->GetPostProcessAnimBPClassToBeUsed().Get() != Wanted)
		{
			// Replaces any post-process AnimBP on the mesh asset (the template mannequin has none).
			Body->SetOverridePostProcessAnimBP(Wanted);
		}
		PendingBoneMods = MoveTemp(Bones);
		TryPushBoneMods(Body);
	}

	// --- 3. Mask slots: enabled / index / texture ------------------------------------------------------
	TMap<FName, UTexture*> Textures;
	for (const FLyrisPartSlotDef& Slot : C->Slots)
	{
		if (!Slot.bMask)
		{
			continue;
		}
		const FName PartId = ULyrisAppearanceLibrary::GetEffectivePart(C, Appearance, Slot.Slot);
		const FLyrisPartDef* Part = PartId.IsNone() ? nullptr : C->FindPart(PartId);
		const FString S = Slot.Slot.ToString();
		Scalars.Add(FName(*(S + TEXT("Enabled"))), Part ? 1.f : 0.f);
		Scalars.Add(FName(*(S + TEXT("Index"))), Part ? static_cast<float>(C->GetPartIndexInSlot(PartId)) : -1.f);
		if (Part && !Part->Mask.IsNull())
		{
			if (UTexture2D* Tex = Part->Mask.LoadSynchronous())
			{
				Textures.Add(FName(*(S + TEXT("Mask"))), Tex);
			}
		}
	}

	// --- 4. Colours -------------------------------------------------------------------------------------
	TMap<FName, FLinearColor> Vectors;
	const FName SkinChannel = ULyrisAppearanceCatalog::GetSkinChannelFor(Appearance.People);
	const FName ScleraChannel = ULyrisAppearanceCatalog::GetScleraChannelFor(Appearance.People);
	for (const FLyrisColorChannelDef& Ch : C->ColorChannels)
	{
		if (Ch.Category == LyrisAppearanceIds::CategoryLantern || !Ch.AllowsPeople(Appearance.People))
		{
			continue;
		}
		// Only the current People's skin / eye-white channel writes the shared param.
		const bool bSkinFamily = Ch.MaterialParam == FName(TEXT("SkinTone"));
		const bool bScleraFamily = Ch.MaterialParam == FName(TEXT("ScleraColor"));
		if ((bSkinFamily && Ch.Id != SkinChannel) || (bScleraFamily && Ch.Id != ScleraChannel))
		{
			continue;
		}
		Vectors.Add(Ch.MaterialParam, ULyrisAppearanceLibrary::ResolveColor(Ch, ULyrisAppearanceLibrary::GetEffectivePick(Appearance, Ch.Id)));
	}
	// Match-hair toggles (spec 3.7 / 5.2): brows follow the hair root darkened by 0.1 value; facial hair follows it.
	if (const FLyrisColorChannelDef* Root = C->FindChannel(LyrisAppearanceIds::ChannelHairRoot))
	{
		const FLyrisColorPick RootPick = ULyrisAppearanceLibrary::GetEffectivePick(Appearance, Root->Id);
		if (ULyrisAppearanceLibrary::GetPartScalarValue(C, Appearance, LyrisAppearanceIds::BrowsMatchHair) >= 0.5f)
		{
			if (const FLyrisColorChannelDef* Brows = C->FindChannel(LyrisAppearanceIds::ChannelHairBrows))
			{
				FLyrisColorChannelDef Wide = *Root;
				Wide.MaxValueShift = 1.f;
				FLyrisColorPick Darker = RootPick;
				Darker.ValueShift = RootPick.ValueShift - 0.1f;
				Vectors.Add(Brows->MaterialParam, ULyrisAppearanceLibrary::ResolveColor(Wide, Darker));
			}
		}
		if (ULyrisAppearanceLibrary::GetPartScalarValue(C, Appearance, LyrisAppearanceIds::FacialHairMatchHair) >= 0.5f)
		{
			if (const FLyrisColorChannelDef* Facial = C->FindChannel(LyrisAppearanceIds::ChannelHairFacial))
			{
				Vectors.Add(Facial->MaterialParam, ULyrisAppearanceLibrary::ResolveColor(*Root, RootPick));
			}
		}
	}
	// Heterochromia off: right iris = left iris.
	if (ULyrisAppearanceLibrary::GetPartScalarValue(C, Appearance, LyrisAppearanceIds::EyesHeterochromia) < 0.5f)
	{
		const FLyrisColorChannelDef* L = C->FindChannel(LyrisAppearanceIds::ChannelIrisL);
		const FLyrisColorChannelDef* R = C->FindChannel(LyrisAppearanceIds::ChannelIrisR);
		if (L && R)
		{
			Vectors.Add(R->MaterialParam, ULyrisAppearanceLibrary::ResolveColor(*L, ULyrisAppearanceLibrary::GetEffectivePick(Appearance, L->Id)));
		}
	}

	// --- 5. Push morphs and material params to the body and every part ---------------------------------
	TArray<UMeshComponent*> Meshes;
	GatherMeshes(Body, Meshes);
	const bool bGameWorld = IsGameWorld(this);
	for (UMeshComponent* MeshComp : Meshes)
	{
		if (USkeletalMeshComponent* Skel = Cast<USkeletalMeshComponent>(MeshComp))
		{
			if (const USkeletalMesh* Asset = Skel->GetSkeletalMeshAsset())
			{
				// Only clears weights set from code (SetMorphTarget); animation-curve morphs are unaffected.
				Skel->ClearMorphTargets();
				for (const TPair<FName, float>& KV : Morphs)
				{
					const FString Base = KV.Key.ToString();
					const FName PosName(*(Base + TEXT("_Pos")));
					const FName NegName(*(Base + TEXT("_Neg")));
					if (Asset->FindMorphTarget(PosName) || Asset->FindMorphTarget(NegName))
					{
						Skel->SetMorphTarget(PosName, FMath::Clamp(KV.Value, 0.f, 1.f));
						Skel->SetMorphTarget(NegName, FMath::Clamp(-KV.Value, 0.f, 1.f));
					}
					else if (Asset->FindMorphTarget(KV.Key))
					{
						Skel->SetMorphTarget(KV.Key, FMath::Clamp(KV.Value, -1.f, 1.f));
					}
				}
			}
		}

		const int32 NumMaterials = MeshComp->GetNumMaterials();
		for (int32 Index = 0; Index < NumMaterials; ++Index)
		{
			if (!MeshComp->GetMaterial(Index))
			{
				continue;
			}
			// Reuses the MID if the slot already has one of ours.
			UMaterialInstanceDynamic* MID = MeshComp->CreateDynamicMaterialInstance(Index);
			if (!MID)
			{
				continue;
			}
			if (!bGameWorld)
			{
				MID->SetFlags(RF_Transient); // editor preview: never save these into a level
			}
			// Params the material does not have are ignored by the engine.
			for (const TPair<FName, FLinearColor>& KV : Vectors) { MID->SetVectorParameterValue(KV.Key, KV.Value); }
			for (const TPair<FName, float>& KV : Scalars)        { MID->SetScalarParameterValue(KV.Key, KV.Value); }
			for (const TPair<FName, UTexture*>& KV : Textures)   { MID->SetTextureParameterValue(KV.Key, KV.Value); }
		}
	}
}
