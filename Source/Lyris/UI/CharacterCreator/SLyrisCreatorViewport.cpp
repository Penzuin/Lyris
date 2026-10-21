// Lyris character creator: viewport input layer (orbit, zoom, face sculpting).

#include "UI/CharacterCreator/SLyrisCreatorViewport.h"

#include "Blueprint/WidgetLayoutLibrary.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerController.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"

#include "UI/CharacterCreator/LyrisCreatorStage.h"
#include "UI/CharacterCreator/LyrisCreatorStyle.h"

#define LOCTEXT_NAMESPACE "LyrisCreator"

namespace
{
	/** Degrees of orbit per slate unit dragged. */
	constexpr float OrbitDegreesPerUnit = 0.35f;
}

void SLyrisCreatorViewport::Construct(const FArguments& InArgs)
{
	Stage = InArgs._Stage;
	PlayerController = InArgs._PlayerController;
	SculptEnabled = InArgs._SculptEnabled;
	IsRegionSculptable = InArgs._IsRegionSculptable;
	OnSculptBegin = InArgs._OnSculptBegin;
	OnSculptDrag = InArgs._OnSculptDrag;
	OnSculptEnd = InArgs._OnSculptEnd;
	OnSculptReset = InArgs._OnSculptReset;

	// The layer must be hit-testable so empty space receives drags.
	SetVisibility(EVisibility::Visible);
}

FVector2D SLyrisCreatorViewport::ComputeDesiredSize(float) const
{
	// Fills whatever slot it is given.
	return FVector2D(1.f, 1.f);
}

FText SLyrisCreatorViewport::RegionDisplayName(FName Region)
{
	if (Region == TEXT("Forehead")) { return LOCTEXT("RForehead", "Forehead"); }
	if (Region == TEXT("BrowL"))    { return LOCTEXT("RBrowL", "Left brow"); }
	if (Region == TEXT("BrowR"))    { return LOCTEXT("RBrowR", "Right brow"); }
	if (Region == TEXT("EyeL"))     { return LOCTEXT("REyeL", "Left eye"); }
	if (Region == TEXT("EyeR"))     { return LOCTEXT("REyeR", "Right eye"); }
	if (Region == TEXT("Nose"))     { return LOCTEXT("RNose", "Nose"); }
	if (Region == TEXT("Cheeks"))   { return LOCTEXT("RCheeks", "Cheeks"); }
	if (Region == TEXT("Mouth"))    { return LOCTEXT("RMouth", "Mouth"); }
	if (Region == TEXT("Jaw"))      { return LOCTEXT("RJaw", "Jaw"); }
	if (Region == TEXT("Chin"))     { return LOCTEXT("RChin", "Chin"); }
	if (Region == TEXT("EarL"))     { return LOCTEXT("REarL", "Left ear"); }
	if (Region == TEXT("EarR"))     { return LOCTEXT("REarR", "Right ear"); }
	return FText::FromName(Region);
}

// ---------------------------------------------------------------------------------------- Projection

void SLyrisCreatorViewport::ProjectAnchors(const FGeometry& Geometry)
{
	Anchors.Reset();
	ALyrisCreatorStage* StagePtr = Stage.Get();
	APlayerController* PC = PlayerController.Get();
	if (!StagePtr || !PC || !SculptEnabled.Get(false))
	{
		return;
	}

	TArray<TPair<FName, FVector>> World;
	StagePtr->GetSculptAnchorsWorld(World);

	FVector2D Sum = FVector2D::ZeroVector;
	int32 Count = 0;
	for (const TPair<FName, FVector>& Anchor : World)
	{
		FVector2D ViewportPos;
		// Returns the position in DPI-scaled viewport space. This layer is added to the game
		// viewport at (0,0) filling it, so viewport space is our local space.
		if (!UWidgetLayoutLibrary::ProjectWorldLocationToWidgetPosition(PC, Anchor.Value, ViewportPos, /*bPlayerViewportRelative*/ true))
		{
			continue;
		}
		Sum += ViewportPos;
		++Count;

		if (IsRegionSculptable.IsBound() && !IsRegionSculptable.Execute(Anchor.Key))
		{
			continue;
		}
		FProjectedAnchor& Projected = Anchors.AddDefaulted_GetRef();
		Projected.Region = Anchor.Key;
		Projected.Local = ViewportPos;
	}
	// GetLocalSize() is FVector2f in UE5; convert so both ternary arms are FVector2D.
	FaceCentre = Count > 0 ? Sum / Count : FVector2D(Geometry.GetLocalSize()) * 0.5;
}

void SLyrisCreatorViewport::UpdateHover()
{
	HoveredAnchor = INDEX_NONE;
	HoveredRegion = NAME_None;
	if (!bMouseInside || DragMode == EDragMode::Orbit)
	{
		return;
	}

	const float Radius = FLyrisCreatorStyle::Get().SculptPickRadius;
	float BestDistSq = Radius * Radius;
	for (int32 Index = 0; Index < Anchors.Num(); ++Index)
	{
		const float DistSq = FVector2D::DistSquared(Anchors[Index].Local, MouseLocal);
		if (DistSq < BestDistSq)
		{
			BestDistSq = DistSq;
			HoveredAnchor = Index;
		}
	}
	if (HoveredAnchor != INDEX_NONE)
	{
		HoveredRegion = Anchors[HoveredAnchor].Region;
	}
}

void SLyrisCreatorViewport::Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime)
{
	// The camera moves every frame (easing, orbit), so re-project every frame.
	ProjectAnchors(AllottedGeometry);
	if (DragMode == EDragMode::Sculpt)
	{
		// Keep the ring on the grabbed region while dragging, even if the mouse drifts off it.
		HoveredAnchor = Anchors.IndexOfByPredicate([this](const FProjectedAnchor& A) { return A.Region == DragRegion; });
		HoveredRegion = DragRegion;
	}
	else
	{
		UpdateHover();
	}
}

// ---------------------------------------------------------------------------------------- Paint

int32 SLyrisCreatorViewport::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	if (HoveredRegion.IsNone() || !SculptEnabled.Get(false))
	{
		return LayerId;
	}

	const FLyrisCreatorStyle& Style = FLyrisCreatorStyle::Get();
	const float Ring = Style.SculptRingSize;

	// A soft painted ring on every anchor of the hovered region (both cheeks light up together).
	FVector2D LabelAt = FVector2D::ZeroVector;
	bool bHasLabel = false;
	for (const FProjectedAnchor& Anchor : Anchors)
	{
		if (Anchor.Region != HoveredRegion)
		{
			continue;
		}
		const FVector2D TopLeft = Anchor.Local - FVector2D(Ring, Ring) * 0.5f;
		FSlateDrawElement::MakeBox(OutDrawElements, LayerId,
			AllottedGeometry.ToPaintGeometry(FVector2D(Ring, Ring), FSlateLayoutTransform(TopLeft)),
			&Style.SculptRingBrush, ESlateDrawEffect::None, FLinearColor::White);
		if (!bHasLabel || Anchor.Local.Y < LabelAt.Y)
		{
			LabelAt = Anchor.Local;
			bHasLabel = true;
		}
	}

	// The region's name in a small parchment tag above the ring.
	if (bHasLabel)
	{
		const FText Label = RegionDisplayName(HoveredRegion);
		const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		const FVector2D TextSize = FVector2D(Measure->Measure(Label, Style.BodyFont));
		const FVector2D Pad(10.f, 4.f);
		const FVector2D TagSize = TextSize + Pad * 2.f;
		const FVector2D TagPos = LabelAt - FVector2D(TagSize.X * 0.5f, Ring * 0.5f + TagSize.Y + 6.f);

		FSlateDrawElement::MakeBox(OutDrawElements, LayerId + 1,
			AllottedGeometry.ToPaintGeometry(TagSize, FSlateLayoutTransform(TagPos)),
			&Style.SubPanelBrush, ESlateDrawEffect::None, FLinearColor::White);
		FSlateDrawElement::MakeText(OutDrawElements, LayerId + 2,
			AllottedGeometry.ToPaintGeometry(TextSize, FSlateLayoutTransform(TagPos + Pad)),
			Label, Style.BodyFont, ESlateDrawEffect::None, Style.DarkWood);
	}
	return LayerId + 2;
}

// ---------------------------------------------------------------------------------------- Mouse

FReply SLyrisCreatorViewport::OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	MouseLocal = MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition());
	bMouseInside = true;
	UpdateHover();

	if (MouseEvent.GetEffectingButton() == EKeys::RightMouseButton && !HoveredRegion.IsNone())
	{
		// Right-click on a region resets its sliders (spec 9.1).
		OnSculptReset.ExecuteIfBound(HoveredRegion);
		return FReply::Handled();
	}

	if (MouseEvent.GetEffectingButton() == EKeys::LeftMouseButton || MouseEvent.GetEffectingButton() == EKeys::RightMouseButton)
	{
		if (MouseEvent.GetEffectingButton() == EKeys::LeftMouseButton && !HoveredRegion.IsNone())
		{
			DragMode = EDragMode::Sculpt;
			DragRegion = HoveredRegion;
			// Dragging away from the face centre counts as "outward" for horizontal sliders, so the
			// left eye's outer corner grows when dragged left and the right one when dragged right.
			const FVector2D Grabbed = Anchors.IsValidIndex(HoveredAnchor) ? Anchors[HoveredAnchor].Local : MouseLocal;
			DragHorizontalSign = (Grabbed.X < FaceCentre.X - 2.f) ? -1.f : 1.f;
			OnSculptBegin.ExecuteIfBound(DragRegion);
		}
		else
		{
			DragMode = EDragMode::Orbit;
		}
		FReply Reply = FReply::Handled().CaptureMouse(SharedThis(this));
		if (const TSharedPtr<SWidget> Target = FocusTarget.Pin())
		{
			Reply.SetUserFocus(Target.ToSharedRef(), EFocusCause::Mouse);
		}
		return Reply;
	}
	return FReply::Unhandled();
}

FReply SLyrisCreatorViewport::OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	if (DragMode != EDragMode::None)
	{
		EndDrag();
		return FReply::Handled().ReleaseMouseCapture();
	}
	return FReply::Unhandled();
}

FReply SLyrisCreatorViewport::OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	MouseLocal = MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition());
	bMouseInside = true;

	// Cursor delta is in screen pixels; convert to slate units so sensitivity ignores DPI.
	const float Scale = FMath::Max(MyGeometry.Scale, KINDA_SMALL_NUMBER);
	const FVector2D Delta = FVector2D(MouseEvent.GetCursorDelta()) / Scale;

	if (DragMode == EDragMode::Orbit)
	{
		if (ALyrisCreatorStage* StagePtr = Stage.Get())
		{
			// Drag right swings the camera left around the character, so the character appears to turn
			// to follow the mouse, like turning a figure on a plinth.
			StagePtr->AddOrbit(-Delta.X * OrbitDegreesPerUnit, Delta.Y * OrbitDegreesPerUnit);
		}
		return FReply::Handled();
	}
	if (DragMode == EDragMode::Sculpt)
	{
		OnSculptDrag.ExecuteIfBound(DragRegion, Delta.X, Delta.Y, DragHorizontalSign);
		return FReply::Handled();
	}
	return FReply::Unhandled();
}

FReply SLyrisCreatorViewport::OnMouseWheel(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	if (ALyrisCreatorStage* StagePtr = Stage.Get())
	{
		StagePtr->AddZoom(MouseEvent.GetWheelDelta());
		return FReply::Handled();
	}
	return FReply::Unhandled();
}

void SLyrisCreatorViewport::OnMouseLeave(const FPointerEvent& MouseEvent)
{
	SLeafWidget::OnMouseLeave(MouseEvent);
	if (DragMode == EDragMode::None)
	{
		bMouseInside = false;
		HoveredAnchor = INDEX_NONE;
		HoveredRegion = NAME_None;
	}
}

void SLyrisCreatorViewport::OnMouseCaptureLost(const FCaptureLostEvent& CaptureLostEvent)
{
	EndDrag();
}

void SLyrisCreatorViewport::EndDrag()
{
	if (DragMode == EDragMode::Sculpt)
	{
		OnSculptEnd.ExecuteIfBound();
	}
	DragMode = EDragMode::None;
	DragRegion = NAME_None;
}

FCursorReply SLyrisCreatorViewport::OnCursorQuery(const FGeometry& MyGeometry, const FPointerEvent& CursorEvent) const
{
	if (DragMode == EDragMode::Orbit)
	{
		return FCursorReply::Cursor(EMouseCursor::GrabHandClosed);
	}
	if (DragMode == EDragMode::Sculpt || !HoveredRegion.IsNone())
	{
		return FCursorReply::Cursor(EMouseCursor::CardinalCross);
	}
	return FCursorReply::Cursor(EMouseCursor::GrabHand);
}

#undef LOCTEXT_NAMESPACE
