// Lyris UI: the Breath ring, the stamina ring that floats beside the player's head (T33).
// Look ported from the approved reference page design/reference/wayfarers_breath.html (drawRing()).

#pragma once

#include "CoreMinimal.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SLeafWidget.h"

/** One frame of stamina state, read from ULyrisStaminaComponent by ULyrisBreathRingSubsystem. */
struct FLyrisBreathSample
{
	float Current = 100.f;
	float Max = 100.f;
	/** Bonus Breath from food and drink (lantern tea), spent before the main pool. */
	float Bonus = 0.f;
	/** Breath at which Winded clears, in the same units as Current. */
	float WindedThreshold = 35.f;
	float TimeSinceLastSpend = 100.f;
	/** Cost of the action that would happen next (e.g. a climb leap). 0 means nothing to preview. */
	float PreviewCost = 0.f;
	bool bCanAffordPreview = true;
	bool bWinded = false;
};

/**
 * Pure Slate widget that draws the Breath ring. It is meant to fill the player's viewport layer;
 * the ring is painted around an anchor point (the head, projected to screen) given each frame.
 *
 * All drawing is one antialiased custom-vertex mesh built in OnPaint (feathered edges one
 * physical pixel wide), so the ring stays crisp at any DPI scale and costs a single draw call.
 * Animation state lives here and is advanced by Advance(); OnPaint only reads it.
 */
class LYRIS_API SLyrisBreathRing : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SLyrisBreathRing)
		: _RingRadius(24.f)
		, _ReducedMotion(false)
	{}
		/** Radius of the main arc in Slate units (scaled by DPI like the rest of the UI). */
		SLATE_ARGUMENT(float, RingRadius)
		/** Turns off shake, sparks, ripples and pulses. No project setting exists yet; see T33 PR. */
		SLATE_ARGUMENT(bool, ReducedMotion)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	/**
	 * Where the head is, in this widget's local Slate units. The ring sits just to the right of
	 * and above this point. bOnScreen = false (e.g. head behind the camera) fades the ring out.
	 */
	void SetHeadAnchor(const FVector2D& InHeadLocal, bool bOnScreen);

	/** Advances animation by DeltaSeconds using the latest stamina sample. Call once per frame. */
	void Advance(float DeltaSeconds, const FLyrisBreathSample& Sample);

	/** Something was just spent (from OnStaminaSpent). Kicks the spark at the arc head. */
	void NotifySpent(float Amount);

	/** Forget all animation state (new pawn). The ring starts hidden and snaps to the next sample. */
	void ResetState();

	void SetReducedMotion(bool bInReducedMotion) { bReducedMotion = bInReducedMotion; }

	// SWidget
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

private:
	struct FSpark
	{
		/** Local Slate units (not ring units), so sparks stay where they were born as the head moves. */
		FVector2f Pos = FVector2f::ZeroVector;
		FVector2f Vel = FVector2f::ZeroVector;
		float Life = 0.f;
		FColor Color = FColor::White;
	};

	/** Ring-space (reference units, main radius 17) point of the arc head. */
	FVector2f ArcHead(float Ratio) const;
	/** Local Slate position of the ring centre, kept inside a widget of LocalSize. */
	FVector2f RingCentreLocal(const FVector2f& LocalSize) const;
	/** Size this widget was last painted at, in local Slate units. */
	FVector2f LastLocalSize() const;
	void Burst(int32 Count, const FColor& Color);

	float RingRadius = 24.f;
	bool bReducedMotion = false;

	// Latest sample (Current clamped to 0..Max, Max >= 1).
	FLyrisBreathSample State;
	bool bHasSample = false;

	FVector2f HeadTarget = FVector2f::ZeroVector;
	FVector2f HeadSmoothed = FVector2f::ZeroVector;
	bool bHeadOnScreen = false;
	bool bHeadEverSet = false;

	float Time = 0.f;
	float Ghost = 100.f;
	float Alpha = 0.f;
	float Shake = 0.f;
	FVector2f ShakeOffset = FVector2f::ZeroVector;
	float TimeSinceFull = 100.f;
	bool bWasFull = true;
	/** 1 -> 0: the gold ripple when Breath refills to full or Winded clears. */
	float RipplePulse = 0.f;
	/** Seconds since NotifySpent, for the arc-head spark. */
	float TimeSinceSpentEvent = 100.f;

	TArray<FSpark> Sparks;
};
