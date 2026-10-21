// Lyris appearance system: native post-process anim instance that applies body sliders to bones
// (Player lane, task T23). No AnimBP asset is needed.
//
// How it works
//   ULyrisAppearanceComponent calls Mesh->SetOverridePostProcessAnimBP(ULyrisAppearanceAnimInstance::StaticClass()).
//   The skeletal mesh then creates this instance as its post-process instance and, every frame, runs it
//   after the main AnimBP (ABP_Unarmed on the template mannequin):
//     1. Before evaluating a post-process instance, USkeletalMeshComponent pushes the main instance's pose
//        into the instance's "linked input pose" node (UAnimInstance::GetLinkedInputPoseNode()). An AnimBP
//        gets that node from its graph; a native class has none, so our proxy owns one and registers it as
//        FAnimInstanceProxy::DefaultLinkedInstanceInputNode in Initialize().
//     2. FLyrisAppearanceAnimInstanceProxy::Evaluate copies that input pose and applies the accumulated bone
//        modifiers (scale / offset / rotation) in local (parent) space.
//   The component hands new modifiers to the game-thread instance with SetBoneMods(); the proxy copies them
//   in PreUpdate (game thread), so the worker-thread evaluation never touches game-thread data.
//
// Not verified in an editor build. The one engine detail this relies on is that the mesh fills the input node
// returned by GetLinkedInputPoseNode() and that the base class reads it from DefaultLinkedInstanceInputNode for
// a class without an anim graph. If the log says "no input pose from the main anim instance", use the FALLBACK:
//   1. In the editor make an Animation Blueprint for SK_Mannequin with parent class LyrisAppearanceAnimInstance.
//   2. Its AnimGraph is only "Input Pose -> Output Pose". Save it (e.g. /Game/Lyris/Player/ABP_LyrisAppearance).
//   3. Set ULyrisAppearanceComponent::PostProcessClass to it (on the character Blueprint or in C++).
//   (The native and the fallback path are told apart at runtime: the graph is only used when our own input
//   node received nothing.)
//   The proxy then evaluates that graph to get the input pose and still adds the bone mods (same code path).
//
// Scale rule (keeps limbs from ballooning):
//   - UniformScale scales the bone AND everything under it (e.g. Body.Height on root, Body.HandSize on hand_l).
//   - ShapeScale (non-uniform) scales only the bone's own segment: its direct children get the inverse scale,
//     so they follow the new length (their translation is scaled) but keep their own size.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNode_LinkedInputPose.h"
#include "LyrisAppearanceAnimInstance.generated.h"

/** Accumulated change for one bone. Plain C++ (not reflected); identity by default. */
struct LYRIS_API FLyrisBoneMod
{
	/** Product of uniform BoneScale targets; propagates to children. */
	float UniformScale = 1.f;
	/** Product of non-uniform BoneScale targets; children are compensated, so it does not propagate. */
	FVector ShapeScale = FVector::OneVector;
	/** Sum of BoneOffset targets, cm, added to the bone's local (parent-space) translation. */
	FVector Offset = FVector::ZeroVector;
	/** Sum of BoneRotation targets, applied in the bone's own space after the animated rotation. */
	FRotator Rotation = FRotator::ZeroRotator;

	bool IsIdentity() const
	{
		return FMath::IsNearlyEqual(UniformScale, 1.f) && ShapeScale.Equals(FVector::OneVector) && Offset.IsNearlyZero() && Rotation.IsNearlyZero();
	}
};

/** Proxy: owns the input pose node and does the worker-thread evaluation. */
struct LYRIS_API FLyrisAppearanceAnimInstanceProxy : public FAnimInstanceProxy
{
	FLyrisAppearanceAnimInstanceProxy() = default;
	explicit FLyrisAppearanceAnimInstanceProxy(UAnimInstance* InAnimInstance) : FAnimInstanceProxy(InAnimInstance) {}

protected:
	virtual void Initialize(UAnimInstance* InAnimInstance) override;
	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	/** The base Evaluate_WithRoot forwards here, so this one override covers both entry points. */
	virtual bool Evaluate(FPoseContext& Output) override;

private:
	/** Takes the pose from the main instance (or from GraphRoot, see fallback) and applies BoneMods. */
	void EvaluateAppearance(FPoseContext& Output, FAnimNode_Base* GraphRoot);

	/** Receives the main instance's pose (filled by USkeletalMeshComponent before we evaluate). */
	FAnimNode_LinkedInputPose InputPoseNode;

	/** Copy of the game-thread modifiers, refreshed in PreUpdate when they change. */
	TMap<FName, FLyrisBoneMod> BoneMods;
	uint32 BoneModsSerial = 0;

public:
	/** Written by the worker-thread evaluation, read on the game thread through GetProxyOnGameThread (which waits). */
	int32 GoodEvaluations = 0;
	int32 MissedEvaluations = 0;
};

/**
 * Native post-process anim instance. Assign it with Mesh->SetOverridePostProcessAnimBP(StaticClass()).
 * Notes:
 *  - This REPLACES any post-process AnimBP the mesh asset has (the template mannequin has none).
 *  - Bones that the current LOD does not need are skipped silently.
 *  - Blueprintable only for the documented AnimBP fallback (graph = Input Pose -> Output Pose).
 */
UCLASS(Blueprintable)
class LYRIS_API ULyrisAppearanceAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	/** Replaces all bone modifiers. Game thread only. */
	void SetBoneMods(const TMap<FName, FLyrisBoneMod>& InMods);

	const TMap<FName, FLyrisBoneMod>& GetBoneMods() const { return BoneMods; }
	uint32 GetBoneModsSerial() const { return BoneModsSerial; }

	/** Number of evaluations that received a real pose from the main instance (capped at 1000). Game thread. */
	int32 GetEvaluationCount();

	/**
	 * Number of evaluations that got no pose (native input route did not work and this is not the AnimBP
	 * fallback; capped at 1000). If this grows while GetEvaluationCount() stays 0, ULyrisAppearanceComponent
	 * removes the post-process override so the character keeps animating, and logs how to enable the fallback.
	 */
	int32 GetMissedEvaluationCount();

protected:
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;

private:
	TMap<FName, FLyrisBoneMod> BoneMods;
	uint32 BoneModsSerial = 1;
};
