// Lyris character creator: the see-through layer over the 3D stage that turns mouse input into camera
// orbit, zoom and BDO-style click-and-drag face sculpting.

#pragma once

#include "CoreMinimal.h"
#include "Widgets/SLeafWidget.h"

class ALyrisCreatorStage;
class APlayerController;

/** Region grabbed, plus drag in slate units since the last event. HorizontalSign is +1 when dragging
 *  right moves "outward" from the face centre for the grabbed point, -1 when outward is to the left. */
DECLARE_DELEGATE_FourParams(FOnLyrisSculptDrag, FName /*Region*/, float /*DeltaX*/, float /*DeltaY*/, float /*HorizontalSign*/);
DECLARE_DELEGATE_OneParam(FOnLyrisSculptRegion, FName /*Region*/);
DECLARE_DELEGATE_RetVal_OneParam(bool, FIsLyrisSculptRegion, FName /*Region*/);

/**
 * Full-screen layer drawn under the creator panels.
 *
 * - Dragging empty space orbits the stage camera; the mouse wheel zooms.
 * - While sculpting is enabled (Face category), the stage's face anchors are projected to the screen
 *   every frame. The nearest one within FLyrisCreatorStyle::SculptPickRadius is the hovered region: it
 *   gets a soft gold ring and its name. Left-drag on it reports drags (OnSculptDrag) between
 *   OnSculptBegin / OnSculptEnd; right-click reports OnSculptReset.
 */
class SLyrisCreatorViewport : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SLyrisCreatorViewport) {}
		SLATE_ARGUMENT(TWeakObjectPtr<ALyrisCreatorStage>, Stage)
		SLATE_ARGUMENT(TWeakObjectPtr<APlayerController>, PlayerController)
		/** True while face sculpting should be offered. */
		SLATE_ATTRIBUTE(bool, SculptEnabled)
		/** Filters anchors to regions that have sliders for the current People. */
		SLATE_EVENT(FIsLyrisSculptRegion, IsRegionSculptable)
		SLATE_EVENT(FOnLyrisSculptRegion, OnSculptBegin)
		SLATE_EVENT(FOnLyrisSculptDrag, OnSculptDrag)
		SLATE_EVENT(FSimpleDelegate, OnSculptEnd)
		SLATE_EVENT(FOnLyrisSculptRegion, OnSculptReset)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	// SWidget
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override;
	virtual FReply OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseWheel(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual void OnMouseLeave(const FPointerEvent& MouseEvent) override;
	virtual void OnMouseCaptureLost(const FCaptureLostEvent& CaptureLostEvent) override;
	virtual FCursorReply OnCursorQuery(const FGeometry& MyGeometry, const FPointerEvent& CursorEvent) const override;

	/** Widget that takes keyboard focus when the viewport is clicked (the creator, so Tab and Ctrl+Z
	 *  keep working after you turn the camera). */
	void SetFocusTarget(const TSharedPtr<SWidget>& InTarget) { FocusTarget = InTarget; }

	/** Human-friendly name for a sculpt region id ("EyeL" -> "Left eye"). */
	static FText RegionDisplayName(FName Region);

private:
	struct FProjectedAnchor
	{
		FName Region;
		FVector2D Local;
	};

	enum class EDragMode : uint8 { None, Orbit, Sculpt };

	void ProjectAnchors(const FGeometry& Geometry);
	void UpdateHover();
	void EndDrag();

	TWeakObjectPtr<ALyrisCreatorStage> Stage;
	TWeakObjectPtr<APlayerController> PlayerController;
	TAttribute<bool> SculptEnabled;
	FIsLyrisSculptRegion IsRegionSculptable;
	FOnLyrisSculptRegion OnSculptBegin;
	FOnLyrisSculptDrag OnSculptDrag;
	FSimpleDelegate OnSculptEnd;
	FOnLyrisSculptRegion OnSculptReset;

	TWeakPtr<SWidget> FocusTarget;

	TArray<FProjectedAnchor> Anchors;   // this frame's projected anchors, local space
	FVector2D FaceCentre = FVector2D::ZeroVector;
	FVector2D MouseLocal = FVector2D::ZeroVector;
	bool bMouseInside = false;

	int32 HoveredAnchor = INDEX_NONE;   // index into Anchors
	FName HoveredRegion;
	FName DragRegion;
	float DragHorizontalSign = 1.f;
	EDragMode DragMode = EDragMode::None;
};
