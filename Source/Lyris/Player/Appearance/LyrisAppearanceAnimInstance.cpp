// Lyris appearance system: native post-process anim instance (Player lane, task T23). See the header.

#include "Player/Appearance/LyrisAppearanceAnimInstance.h"
#include "Animation/AnimNodeBase.h"
#include "BoneContainer.h"
#include "BonePose.h"

// ------------------------------------------------------------------------------------------- Instance

void ULyrisAppearanceAnimInstance::SetBoneMods(const TMap<FName, FLyrisBoneMod>& InMods)
{
	BoneMods = InMods;
	++BoneModsSerial;
}

int32 ULyrisAppearanceAnimInstance::GetEvaluationCount()
{
	// GetProxyOnGameThread waits for any in-flight parallel animation work before returning.
	return GetProxyOnGameThread<FLyrisAppearanceAnimInstanceProxy>().GoodEvaluations;
}

int32 ULyrisAppearanceAnimInstance::GetMissedEvaluationCount()
{
	return GetProxyOnGameThread<FLyrisAppearanceAnimInstanceProxy>().MissedEvaluations;
}

FAnimInstanceProxy* ULyrisAppearanceAnimInstance::CreateAnimInstanceProxy()
{
	return new FLyrisAppearanceAnimInstanceProxy(this);
}

void ULyrisAppearanceAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy)
{
	delete static_cast<FLyrisAppearanceAnimInstanceProxy*>(InProxy);
}

// ------------------------------------------------------------------------------------------- Proxy

void FLyrisAppearanceAnimInstanceProxy::Initialize(UAnimInstance* InAnimInstance)
{
	FAnimInstanceProxy::Initialize(InAnimInstance);

	// A native class has no anim graph, so it has no "Input Pose" node of its own. Register ours as the
	// default one: UAnimInstance::GetLinkedInputPoseNode() returns it, and USkeletalMeshComponent copies the
	// main instance's pose into it before evaluating this post-process instance. An AnimBP child (fallback)
	// already has a graph input node, which is left alone.
	if (DefaultLinkedInstanceInputNode == nullptr)
	{
		DefaultLinkedInstanceInputNode = &InputPoseNode;
	}
}

void FLyrisAppearanceAnimInstanceProxy::PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds)
{
	FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);

	// Re-assert our input node every frame in case engine re-initialisation cleared it (native class only;
	// an AnimBP child keeps its graph's node). Cheap (one pointer).
	if (DefaultLinkedInstanceInputNode == nullptr)
	{
		DefaultLinkedInstanceInputNode = &InputPoseNode;
	}

	// Game thread: pick up new modifiers (only when they changed).
	if (const ULyrisAppearanceAnimInstance* Instance = Cast<ULyrisAppearanceAnimInstance>(InAnimInstance))
	{
		if (Instance->GetBoneModsSerial() != BoneModsSerial)
		{
			BoneMods = Instance->GetBoneMods();
			BoneModsSerial = Instance->GetBoneModsSerial();
		}
	}
}

bool FLyrisAppearanceAnimInstanceProxy::Evaluate(FPoseContext& Output)
{
	// GetRootNode() is null for the native class and the AnimGraph root for the AnimBP fallback.
	EvaluateAppearance(Output, GetRootNode());
	return true; // handled
}

void FLyrisAppearanceAnimInstanceProxy::EvaluateAppearance(FPoseContext& Output, FAnimNode_Base* GraphRoot)
{
	// 1) Start from the pose the main instance produced.
	const FCompactHeapPose& Input = InputPoseNode.CachedInputPose;
	if (Input.IsValid() && Input.GetNumBones() == Output.Pose.GetNumBones())
	{
		// Native path: the engine filled our own input node.
		Output.Pose.CopyBonesFrom(Input);
		Output.Curve.CopyFrom(InputPoseNode.CachedInputCurve);
	}
	else if (GraphRoot)
	{
		// Fallback path: this instance is an AnimBP child of ULyrisAppearanceAnimInstance whose graph is just
		// "Input Pose -> Output Pose" (see header). Let the graph produce the input pose, then add our mods.
		EvaluateAnimationNode_WithRoot(Output, GraphRoot);
	}
	else
	{
		// Neither path delivered a pose: draw the reference pose this frame and count it. The component removes
		// the override if this keeps happening, so the character keeps animating (bone sliders off).
		MissedEvaluations = FMath::Min(MissedEvaluations + 1, 1000);
		Output.ResetToRefPose();
		return;
	}
	GoodEvaluations = FMath::Min(GoodEvaluations + 1, 1000);

	if (BoneMods.Num() == 0)
	{
		return;
	}

	// 2) Resolve bone names for the current LOD and apply.
	const FBoneContainer& Bones = Output.Pose.GetBoneContainer();
	TMap<int32, FVector> ShapeByBone; // compact bone index -> non-uniform scale to compensate on children

	for (const TPair<FName, FLyrisBoneMod>& KV : BoneMods)
	{
		const int32 MeshIndex = Bones.GetPoseBoneIndexForBoneName(KV.Key);
		if (MeshIndex == INDEX_NONE)
		{
			continue;
		}
		const FCompactPoseBoneIndex Index = Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(MeshIndex));
		if (!Index.IsValid())
		{
			continue; // not required at this LOD
		}

		const FLyrisBoneMod& Mod = KV.Value;
		FTransform& Local = Output.Pose[Index];

		if (!Mod.Rotation.IsNearlyZero())
		{
			// Bone space: apply after the animated rotation.
			Local.SetRotation((Local.GetRotation() * Mod.Rotation.Quaternion()).GetNormalized());
		}
		if (!Mod.Offset.IsNearlyZero())
		{
			Local.AddToTranslation(Mod.Offset);
		}
		const FVector Shape = Mod.ShapeScale.ComponentMax(FVector(0.5f)).ComponentMin(FVector(1.5f));
		const float Uniform = FMath::Clamp(Mod.UniformScale, 0.5f, 1.5f);
		const FVector Total = Shape * Uniform;
		if (!Total.Equals(FVector::OneVector))
		{
			Local.SetScale3D(Local.GetScale3D() * Total);
		}
		if (!Shape.Equals(FVector::OneVector))
		{
			ShapeByBone.Add(Index.GetInt(), Shape);
		}
	}

	// 3) Non-uniform scale does not propagate: undo it on direct children. FTransform composes scale
	//    component-wise, so dividing the child's local scale cancels it, while the child's translation (in
	//    the parent's scaled frame) still follows the new segment length. This is exact when the child's axes
	//    line up with the parent's (true along the mannequin's limb and spine chains) and a close
	//    approximation otherwise, which is fine for these small (<=15%) stylized ranges.
	if (ShapeByBone.Num() > 0)
	{
		for (FCompactPoseBoneIndex Child : Output.Pose.ForEachBoneIndex())
		{
			const FCompactPoseBoneIndex Parent = Output.Pose.GetParentBoneIndex(Child);
			if (!Parent.IsValid())
			{
				continue;
			}
			if (const FVector* ParentShape = ShapeByBone.Find(Parent.GetInt()))
			{
				FTransform& Local = Output.Pose[Child];
				Local.SetScale3D(Local.GetScale3D() / *ParentShape);
			}
		}
	}
}
