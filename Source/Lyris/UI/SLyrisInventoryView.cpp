// Lyris UI: the hotbar and the satchel (bag) screen (T16).

#include "UI/SLyrisInventoryView.h"

#include "Brushes/SlateRoundedBoxBrush.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "InputCoreTypes.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"

namespace LyrisInventoryStyle
{
// ---- Colours (storybook journal: parchment, ink, leather, a little gold) ----
	static const FLinearColor Ink = FLinearColor(FColor(58, 40, 38));
	static const FLinearColor InkSoft = FLinearColor(FColor(110, 86, 74));
	static const FLinearColor Parchment = FLinearColor(FColor(246, 234, 207));
	static const FLinearColor ParchmentShade = FLinearColor(FColor(229, 210, 172));
	static const FLinearColor Socket = FLinearColor(FColor(214, 192, 152));
	static const FLinearColor Leather = FLinearColor(FColor(110, 72, 54));
	static const FLinearColor LeatherDark = FLinearColor(FColor(66, 42, 34));
	static const FLinearColor Gold = FLinearColor(FColor(242, 193, 78));
	static const FLinearColor GoldSoft = FLinearColor(FColor(255, 226, 150));
	static const FLinearColor Night = FLinearColor(FColor(20, 16, 34));
	static const FLinearColor Cream = FLinearColor(FColor(255, 246, 226));
	static const FLinearColor QualityColour[4] = {
		FLinearColor(FColor(0, 0, 0, 0)),
		FLinearColor(FColor(205, 218, 232)),  // Fine: silver
		FLinearColor(FColor(242, 193, 78)),   // Splendid: gold
		FLinearColor(FColor(127, 224, 208)),  // Radiant: sea-glass teal
	};
	static const TCHAR* QualityName[4] = { TEXT("Normal"), TEXT("Fine"), TEXT("Splendid"), TEXT("Radiant") };

// ---- Layout (Slate units, scaled by the viewport's DPI) ----
	static constexpr float HotbarSlot = 60.f;
	static constexpr float HotbarGap = 8.f;
	static constexpr float HotbarBottom = 30.f;
	static constexpr float BagSlot = 56.f;
	static constexpr float BagGap = 9.f;
	static constexpr float PageMargin = 36.f;
	static constexpr float DetailWidth = 330.f;

// ---- Timing ----
	static constexpr float SelectionShow = 1.3f;
	static constexpr float SelectionFade = 0.45f;
	static constexpr float ToastLife = 3.0f;
	static constexpr int32 MaxToasts = 4;

	// Brushes: white fills and white outlines at a few radii; colour comes from the tint.
	struct FBrushes
	{
		FSlateRoundedBoxBrush Fill6 = FSlateRoundedBoxBrush(FLinearColor::White, 6.f);
		FSlateRoundedBoxBrush Fill10 = FSlateRoundedBoxBrush(FLinearColor::White, 10.f);
		FSlateRoundedBoxBrush Fill14 = FSlateRoundedBoxBrush(FLinearColor::White, 14.f);
		FSlateRoundedBoxBrush Fill22 = FSlateRoundedBoxBrush(FLinearColor::White, 22.f);
		FSlateRoundedBoxBrush Line10 = FSlateRoundedBoxBrush(FLinearColor::Transparent, 10.f, FLinearColor::White, 2.f);
		FSlateRoundedBoxBrush Line10Thick = FSlateRoundedBoxBrush(FLinearColor::Transparent, 10.f, FLinearColor::White, 3.f);
		FSlateRoundedBoxBrush Line14 = FSlateRoundedBoxBrush(FLinearColor::Transparent, 14.f, FLinearColor::White, 3.f);
		FSlateRoundedBoxBrush Line22 = FSlateRoundedBoxBrush(FLinearColor::Transparent, 22.f, FLinearColor::White, 4.f);
		FSlateRoundedBoxBrush Dot = FSlateRoundedBoxBrush(FLinearColor::White, 6.f, FLinearColor::White, 0.f);
	};

	static const FBrushes& Brushes()
	{
		static const FBrushes Instance;
		return Instance;
	}

	static const FSlateBrush* White()
	{
		return FCoreStyle::Get().GetBrush(TEXT("WhiteBrush"));
	}

	static FLinearColor WithAlpha(FLinearColor Colour, float Alpha)
	{
		Colour.A *= Alpha;
		return Colour;
	}

	static FSlateFontInfo Font(int32 Size, bool bBold = true)
	{
		return FCoreStyle::GetDefaultFontStyle(bBold ? TEXT("Bold") : TEXT("Regular"), Size);
	}

	static FVector2f Measure(const FString& Text, const FSlateFontInfo& FontInfo)
	{
		const TSharedRef<FSlateFontMeasure> Measurer = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		// Direct-init: compiles whether Measure returns FVector2D, FVector2f or FDeprecateVector2DResult.
		const FVector2f Size(Measurer->Measure(Text, FontInfo));
		return Size;
	}

	static void Box(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FVector2f& Pos,
		const FVector2f& Size, const FSlateBrush* Brush, const FLinearColor& Tint)
	{
		FSlateDrawElement::MakeBox(Out, Layer, Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), Brush,
			ESlateDrawEffect::None, Tint);
	}

	static void Text(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FVector2f& Pos,
		const FString& String, const FSlateFontInfo& FontInfo, const FLinearColor& Tint, bool bShadow = false)
	{
		const FVector2f Size = Measure(String, FontInfo);
		if (bShadow)
		{
			FSlateDrawElement::MakeText(Out, Layer, Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos + FVector2f(1.f, 1.5f))),
				String, FontInfo, ESlateDrawEffect::None, FLinearColor(0.f, 0.f, 0.f, 0.65f * Tint.A));
		}
		FSlateDrawElement::MakeText(Out, Layer + 1, Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), String, FontInfo,
			ESlateDrawEffect::None, Tint);
	}

	/** Greedy word wrap to Width; returns the lines. */
	static TArray<FString> Wrap(const FString& String, const FSlateFontInfo& FontInfo, float Width)
	{
		TArray<FString> Words;
		String.ParseIntoArrayWS(Words);
		TArray<FString> Lines;
		FString Line;
		for (const FString& Word : Words)
		{
			const FString Try = Line.IsEmpty() ? Word : Line + TEXT(" ") + Word;
			if (!Line.IsEmpty() && Measure(Try, FontInfo).X > Width)
			{
				Lines.Add(Line);
				Line = Word;
			}
			else
			{
				Line = Try;
			}
		}
		if (!Line.IsEmpty())
		{
			Lines.Add(Line);
		}
		return Lines;
	}
}

void SLyrisInventoryView::Construct(const FArguments& InArgs)
{
	using namespace LyrisInventoryStyle;
	SetVisibility(EVisibility::HitTestInvisible);
	SetCanTick(true);
}

FVector2D SLyrisInventoryView::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	using namespace LyrisInventoryStyle;
	return FVector2D(1280.0, 720.0);  // fills the viewport slot it lives in
}

void SLyrisInventoryView::SetSlots(const TArray<FLyrisSlotView>& InSlots, int32 InActiveSlot, int32 InHotbarCount)
{
	using namespace LyrisInventoryStyle;
	if (InActiveSlot != ActiveSlot)
	{
		LiftAlpha = 0.f;
	}
	Slots = InSlots;
	ActiveSlot = InActiveSlot;
	HotbarCount = FMath::Clamp(InHotbarCount, 1, 12);
	if (!Slots.IsValidIndex(Carried) || Slots[Carried].bEmpty)
	{
		Carried = INDEX_NONE;
	}
	Invalidate(EInvalidateWidgetReason::Paint);
}

void SLyrisInventoryView::SetOpen(bool bInOpen)
{
	using namespace LyrisInventoryStyle;
	if (bOpen == bInOpen)
	{
		return;
	}
	bOpen = bInOpen;
	Carried = INDEX_NONE;
	Hovered = INDEX_NONE;
	SetVisibility(bOpen ? EVisibility::Visible : EVisibility::HitTestInvisible);
	Invalidate(EInvalidateWidgetReason::Paint);
}

void SLyrisInventoryView::AddToast(const FString& Text, const FSlateBrush* Icon)
{
	using namespace LyrisInventoryStyle;
	FLyrisPickupToast Toast;
	Toast.Text = Text;
	Toast.Icon = Icon;
	Toasts.Insert(Toast, 0);
	if (Toasts.Num() > MaxToasts)
	{
		Toasts.SetNum(MaxToasts);
	}
}

void SLyrisInventoryView::SetPrompt(const FString& InPrompt, const FString& InKey)
{
	if (!InPrompt.IsEmpty())
	{
		Prompt = InPrompt;  // keep the last text while it fades out
		PromptKey = InKey;
	}
	else if (Prompt.IsEmpty())
	{
		PromptAlpha = 0.f;
	}
	bPromptWanted = !InPrompt.IsEmpty();
}

void SLyrisInventoryView::FlashSelection()
{
	using namespace LyrisInventoryStyle;
	SelectionTimer = SelectionShow + SelectionFade;
}

void SLyrisInventoryView::Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime)
{
	using namespace LyrisInventoryStyle;
	const float Dt = FMath::Min(InDeltaTime, 0.1f);
	OpenAlpha = FMath::FInterpConstantTo(OpenAlpha, bOpen ? 1.f : 0.f, Dt, 7.f);
	LiftAlpha = FMath::FInterpConstantTo(LiftAlpha, 1.f, Dt, 6.f);
	SelectionTimer = FMath::Max(0.f, SelectionTimer - Dt);
	PromptAlpha = FMath::FInterpConstantTo(PromptAlpha, (bPromptWanted && !bOpen) ? 1.f : 0.f, Dt, 8.f);
	for (FLyrisPickupToast& Toast : Toasts)
	{
		Toast.Age += Dt;
	}
	Toasts.RemoveAll([](const FLyrisPickupToast& Toast) { return Toast.Age > ToastLife; });
	Invalidate(EInvalidateWidgetReason::Paint);
}

SLyrisInventoryView::FLayout SLyrisInventoryView::ComputeLayout(const FVector2f& Size) const
{
	using namespace LyrisInventoryStyle;
	FLayout L;
	const int32 Count = Slots.Num();
	L.SlotPos.SetNum(Count);
	L.HotbarPos.SetNum(FMath::Min(HotbarCount, Count));

	// On-foot hotbar, bottom centre.
	L.HotbarSize = HotbarSlot;
	const float HotbarWidth = HotbarCount * HotbarSlot + (HotbarCount - 1) * HotbarGap;
	const FVector2f HotbarOrigin((Size.X - HotbarWidth) * 0.5f, Size.Y - HotbarSlot - HotbarBottom);
	for (int32 i = 0; i < L.HotbarPos.Num(); ++i)
	{
		L.HotbarPos[i] = HotbarOrigin + FVector2f(i * (HotbarSlot + HotbarGap), 0.f);
	}

	// Satchel: pack grid (HotbarCount wide) above the hotbar row, on the left page.
	L.SlotSize = BagSlot;
	const int32 Columns = HotbarCount;
	const int32 PackCount = FMath::Max(0, Count - HotbarCount);
	const int32 PackRows = FMath::Max(1, FMath::DivideAndRoundUp(PackCount, Columns));
	const float GridWidth = Columns * BagSlot + (Columns - 1) * BagGap;
	const float LeftWidth = GridWidth + PageMargin * 2.f;
	const float PackTop = 96.f;
	const float PackHeight = PackRows * BagSlot + (PackRows - 1) * BagGap;
	const float HotbarTop = PackTop + PackHeight + 56.f;
	const float PanelHeight = HotbarTop + BagSlot + 70.f;
	L.PanelSize = FVector2f(LeftWidth + DetailWidth, FMath::Max(PanelHeight, 420.f));
	L.Panel = FVector2f((Size.X - L.PanelSize.X) * 0.5f, (Size.Y - L.PanelSize.Y) * 0.5f - 20.f);
	for (int32 i = 0; i < Count; ++i)
	{
		if (i < HotbarCount)
		{
			L.SlotPos[i] = L.Panel + FVector2f(PageMargin + i * (BagSlot + BagGap), HotbarTop);
		}
		else
		{
			const int32 k = i - HotbarCount;
			L.SlotPos[i] = L.Panel + FVector2f(PageMargin + (k % Columns) * (BagSlot + BagGap),
				PackTop + (k / Columns) * (BagSlot + BagGap));
		}
	}
	L.DetailPos = L.Panel + FVector2f(LeftWidth, 0.f);
	L.DetailSize = FVector2f(DetailWidth, L.PanelSize.Y);
	return L;
}

int32 SLyrisInventoryView::HitSlot(const FLayout& Layout, const FVector2f& Local) const
{
	using namespace LyrisInventoryStyle;
	for (int32 i = 0; i < Layout.SlotPos.Num(); ++i)
	{
		const FVector2f& P = Layout.SlotPos[i];
		if (Local.X >= P.X && Local.Y >= P.Y && Local.X <= P.X + Layout.SlotSize && Local.Y <= P.Y + Layout.SlotSize)
		{
			return i;
		}
	}
	return INDEX_NONE;
}

// ----------------------------------------------------------------------------- input

FReply SLyrisInventoryView::OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	using namespace LyrisInventoryStyle;
	if (!bOpen)
	{
		return FReply::Unhandled();
	}
	const FVector2D Local = MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition());
	Cursor = FVector2f(static_cast<float>(Local.X), static_cast<float>(Local.Y));
	const FVector2D LocalSize = MyGeometry.GetLocalSize();
	Hovered = HitSlot(ComputeLayout(FVector2f(static_cast<float>(LocalSize.X), static_cast<float>(LocalSize.Y))), Cursor);
	return FReply::Handled();
}

FReply SLyrisInventoryView::OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	using namespace LyrisInventoryStyle;
	if (!bOpen)
	{
		return FReply::Unhandled();
	}
	const FVector2D Local = MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition());
	Cursor = FVector2f(static_cast<float>(Local.X), static_cast<float>(Local.Y));
	const FVector2D LocalSize = MyGeometry.GetLocalSize();
	const FLayout Layout = ComputeLayout(FVector2f(static_cast<float>(LocalSize.X), static_cast<float>(LocalSize.Y)));
	const int32 Hit = HitSlot(Layout, Cursor);

	if (MouseEvent.GetEffectingButton() == EKeys::RightMouseButton)
	{
		Carried = INDEX_NONE;  // put the stack back where it came from
		return FReply::Handled();
	}
	if (Hit != INDEX_NONE)
	{
		if (OnSlotClicked)
		{
			OnSlotClicked(Hit);
		}
		return FReply::Handled();
	}
	const bool bInsidePanel = Cursor.X >= Layout.Panel.X && Cursor.Y >= Layout.Panel.Y
		&& Cursor.X <= Layout.Panel.X + Layout.PanelSize.X && Cursor.Y <= Layout.Panel.Y + Layout.PanelSize.Y;
	if (!bInsidePanel)
	{
		if (Carried != INDEX_NONE)
		{
			Carried = INDEX_NONE;
		}
		else if (OnCloseRequested)
		{
			OnCloseRequested();
		}
	}
	return FReply::Handled();
}

FReply SLyrisInventoryView::OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	using namespace LyrisInventoryStyle;
	const FKey Key = InKeyEvent.GetKey();
	if (bOpen && (Key == EKeys::I || Key == EKeys::Tab || Key == EKeys::Escape))
	{
		if (OnCloseRequested)
		{
			OnCloseRequested();
		}
		return FReply::Handled();
	}
	static const FKey Digits[] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five,
		EKeys::Six, EKeys::Seven, EKeys::Eight, EKeys::Nine };
	if (bOpen)
	{
		for (int32 k = 0; k < static_cast<int32>(UE_ARRAY_COUNT(Digits)) && k < HotbarCount; ++k)
		{
			if (Key == Digits[k])
			{
				if (Slots.IsValidIndex(Hovered) && !Slots[Hovered].bEmpty && Hovered != k && OnMoveRequested)
				{
					OnMoveRequested(Hovered, k);
				}
				return FReply::Handled();
			}
		}
	}
	return FReply::Unhandled();
}

// ----------------------------------------------------------------------------- painting

void SLyrisInventoryView::PaintSlot(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FVector2f& Pos,
	float Size, const FLyrisSlotView& View, int32 Index, bool bActive, bool bHover, bool bDimmed, float Opacity,
	bool bShowNumber) const
{
	using namespace LyrisInventoryStyle;
	const FBrushes& B = Brushes();
	const FVector2f Sz(Size, Size);
	FVector2f P = Pos;
	if (bActive)
	{
		P.Y -= 6.f * FMath::InterpEaseOut(0.f, 1.f, LiftAlpha, 2.f);
		Box(Geo, Out, Layer, P - FVector2f(5.f, 5.f), Sz + FVector2f(10.f, 10.f), &B.Fill14, WithAlpha(Gold, 0.28f * Opacity));
	}
	// Drop shadow, tile, lower shade band, outline.
	Box(Geo, Out, Layer, P + FVector2f(0.f, 3.f), Sz, &B.Fill10, WithAlpha(Night, 0.35f * Opacity));
	const FLinearColor Fill = View.bEmpty ? Socket : (bHover ? FLinearColor::LerpUsingHSV(Parchment, GoldSoft, 0.35f) : Parchment);
	Box(Geo, Out, Layer + 1, P, Sz, &B.Fill10, WithAlpha(Fill, (View.bEmpty ? 0.72f : 1.f) * Opacity));
	if (!View.bEmpty)
	{
		Box(Geo, Out, Layer + 2, P + FVector2f(3.f, Size * 0.58f), FVector2f(Size - 6.f, Size * 0.42f - 3.f), &B.Fill6,
			WithAlpha(ParchmentShade, 0.55f * Opacity));
	}
	const FSlateBrush* Outline = bActive ? &B.Line10Thick : &B.Line10;
	const FLinearColor OutlineColour = bActive ? Gold : (bHover ? Leather : WithAlpha(Ink, View.bEmpty ? 0.35f : 0.75f));
	Box(Geo, Out, Layer + 6, P, Sz, Outline, WithAlpha(OutlineColour, Opacity));

	if (!View.bEmpty)
	{
		const float Inset = Size * 0.12f;
		const float Alpha = (bDimmed ? 0.3f : 1.f) * Opacity;
		if (View.Icon)
		{
			Box(Geo, Out, Layer + 3, P + FVector2f(Inset, Inset), Sz - FVector2f(Inset * 2.f, Inset * 2.f), View.Icon,
				FLinearColor(1.f, 1.f, 1.f, Alpha));
		}
		else
		{
			// No icon yet: a lettered tile in leather.
			Box(Geo, Out, Layer + 3, P + FVector2f(Inset, Inset), Sz - FVector2f(Inset * 2.f, Inset * 2.f), &B.Fill6,
				WithAlpha(Leather, Alpha));
			const FString Letter = View.Name.Left(1).ToUpper();
			const FSlateFontInfo F = Font(FMath::RoundToInt(Size * 0.36f));
			const FVector2f M = Measure(Letter, F);
			Text(Geo, Out, Layer + 4, P + (Sz - M) * 0.5f, Letter, F, WithAlpha(Cream, Alpha));
		}
		if (View.Count > 1)
		{
			const FString CountText = FString::FromInt(View.Count);
			const FSlateFontInfo F = Font(Size > 58.f ? 12 : 11);
			const FVector2f M = Measure(CountText, F);
			Text(Geo, Out, Layer + 7, P + FVector2f(Size - M.X - 6.f, Size - M.Y - 2.f), CountText, F, WithAlpha(Cream, Alpha), true);
		}
		if (View.Quality > 0 && View.Quality < 4)
		{
			const FVector2f DotPos = P + FVector2f(Size - 15.f, 5.f);
			Box(Geo, Out, Layer + 7, DotPos - FVector2f(1.5f, 1.5f), FVector2f(13.f, 13.f), &B.Dot, WithAlpha(Ink, 0.8f * Opacity));
			Box(Geo, Out, Layer + 8, DotPos, FVector2f(10.f, 10.f), &B.Dot, WithAlpha(QualityColour[View.Quality], Opacity));
		}
	}
	if (bShowNumber && Index < 9)
	{
		const FSlateFontInfo F = Font(9);
		Text(Geo, Out, Layer + 7, P + FVector2f(6.f, 3.f), FString::FromInt(Index + 1), F,
			WithAlpha(bActive ? Leather : InkSoft, 0.9f * Opacity));
	}
}

void SLyrisInventoryView::PaintHotbar(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FLayout& L) const
{
	using namespace LyrisInventoryStyle;
	const float Opacity = 1.f - OpenAlpha;
	if (Opacity <= 0.01f || L.HotbarPos.Num() == 0)
	{
		return;
	}
	const FBrushes& B = Brushes();
	// A soft night-blue strip behind the slots.
	const FVector2f First = L.HotbarPos[0];
	const FVector2f Last = L.HotbarPos.Last();
	const FVector2f StripPos = First - FVector2f(12.f, 10.f);
	const FVector2f StripSize(Last.X + L.HotbarSize - First.X + 24.f, L.HotbarSize + 20.f);
	Box(Geo, Out, Layer, StripPos, StripSize, &B.Fill22, WithAlpha(Night, 0.42f * Opacity));
	Box(Geo, Out, Layer + 1, StripPos, StripSize, &B.Line22, WithAlpha(GoldSoft, 0.18f * Opacity));

	for (int32 i = 0; i < L.HotbarPos.Num(); ++i)
	{
		PaintSlot(Geo, Out, Layer + 2, L.HotbarPos[i], L.HotbarSize, Slots[i], i, i == ActiveSlot, false, false, Opacity, true);
	}

	// Selected item's name, fading above the bar.
	if (SelectionTimer > 0.f && Slots.IsValidIndex(ActiveSlot) && ActiveSlot < L.HotbarPos.Num() && !Slots[ActiveSlot].bEmpty)
	{
		const float A = FMath::Clamp(SelectionTimer / SelectionFade, 0.f, 1.f) * Opacity;
		const FString& Name = Slots[ActiveSlot].Name;
		const FSlateFontInfo F = Font(14);
		const FVector2f M = Measure(Name, F);
		const FVector2f Centre = L.HotbarPos[ActiveSlot] + FVector2f(L.HotbarSize * 0.5f, -24.f);
		const FVector2f TagPos(FMath::Clamp(Centre.X - M.X * 0.5f - 12.f, StripPos.X, StripPos.X + StripSize.X - M.X - 24.f), Centre.Y - M.Y);
		Box(Geo, Out, Layer + 20, TagPos, M + FVector2f(24.f, 8.f), &B.Fill10, WithAlpha(Night, 0.6f * A));
		Text(Geo, Out, Layer + 21, TagPos + FVector2f(12.f, 4.f), Name, F, WithAlpha(Cream, A));
	}
}

void SLyrisInventoryView::PaintPrompt(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FLayout& L) const
{
	using namespace LyrisInventoryStyle;
	if (PromptAlpha <= 0.01f || Prompt.IsEmpty() || L.HotbarPos.Num() == 0)
	{
		return;
	}
	const FBrushes& B = Brushes();
	const float A = PromptAlpha;
	const FSlateFontInfo F = Font(13);
	const FSlateFontInfo KeyFont = Font(12);
	const FVector2f M = Measure(Prompt, F);
	const FVector2f K = Measure(PromptKey, KeyFont);
	const float KeyW = FMath::Max(K.X + 14.f, 26.f);
	const FVector2f Size(KeyW + M.X + 34.f, 36.f);
	const float Centre = (L.HotbarPos[0].X + L.HotbarPos.Last().X + L.HotbarSize) * 0.5f;
	const FVector2f Pos(Centre - Size.X * 0.5f, L.HotbarPos[0].Y - 92.f + (1.f - A) * 8.f);
	Box(Geo, Out, Layer, Pos, Size, &B.Fill14, WithAlpha(Night, 0.62f * A));
	Box(Geo, Out, Layer + 1, Pos, Size, &B.Line14, WithAlpha(GoldSoft, 0.25f * A));
	const FVector2f KeyPos = Pos + FVector2f(8.f, 6.f);
	Box(Geo, Out, Layer + 2, KeyPos, FVector2f(KeyW, 24.f), &B.Fill6, WithAlpha(Parchment, A));
	Box(Geo, Out, Layer + 3, KeyPos + FVector2f(0.f, 20.f), FVector2f(KeyW, 4.f), &B.Fill6, WithAlpha(ParchmentShade, A));
	Text(Geo, Out, Layer + 4, KeyPos + FVector2f((KeyW - K.X) * 0.5f, (22.f - K.Y) * 0.5f), PromptKey, KeyFont, WithAlpha(Ink, A));
	Text(Geo, Out, Layer + 4, Pos + FVector2f(KeyW + 20.f, (Size.Y - M.Y) * 0.5f), Prompt, F, WithAlpha(Cream, A), true);
}

void SLyrisInventoryView::PaintToasts(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FLayout& L) const
{
	using namespace LyrisInventoryStyle;
	if (Toasts.Num() == 0 || L.HotbarPos.Num() == 0)
	{
		return;
	}
	const FBrushes& B = Brushes();
	const FSlateFontInfo F = Font(12);
	const float Right = L.HotbarPos.Last().X + L.HotbarSize + 36.f;
	float Y = L.HotbarPos[0].Y + L.HotbarSize - 34.f;
	for (const FLyrisPickupToast& Toast : Toasts)
	{
		const float In = FMath::Clamp(Toast.Age / 0.18f, 0.f, 1.f);
		const float OutA = FMath::Clamp((ToastLife - Toast.Age) / 0.5f, 0.f, 1.f);
		const float A = In * OutA;
		const float Rise = (1.f - In) * 10.f;
		const FVector2f M = Measure(Toast.Text, F);
		const FVector2f Pos(Right, Y + Rise);
		const FVector2f Size(M.X + (Toast.Icon ? 46.f : 20.f), 32.f);
		Box(Geo, Out, Layer, Pos, Size, &B.Fill14, WithAlpha(Night, 0.55f * A));
		if (Toast.Icon)
		{
			Box(Geo, Out, Layer + 1, Pos + FVector2f(6.f, 3.f), FVector2f(26.f, 26.f), Toast.Icon, FLinearColor(1.f, 1.f, 1.f, A));
		}
		Text(Geo, Out, Layer + 2, Pos + FVector2f(Toast.Icon ? 38.f : 10.f, (32.f - M.Y) * 0.5f), Toast.Text, F, WithAlpha(Cream, A));
		Y -= 38.f;
	}
}

void SLyrisInventoryView::PaintSatchel(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FLayout& L) const
{
	using namespace LyrisInventoryStyle;
	const float A = OpenAlpha;
	if (A <= 0.01f)
	{
		return;
	}
	const FBrushes& B = Brushes();
	const FVector2D LocalSizeD = Geo.GetLocalSize();
	const FVector2f Full(static_cast<float>(LocalSizeD.X), static_cast<float>(LocalSizeD.Y));

	// Dim the world behind the book.
	Box(Geo, Out, Layer, FVector2f::ZeroVector, Full, White(), WithAlpha(Night, 0.5f * A));

	// Leather cover, then the parchment pages.
	const float Drop = (1.f - A) * 18.f;
	const FVector2f Panel = L.Panel + FVector2f(0.f, Drop);
	Box(Geo, Out, Layer + 1, Panel + FVector2f(0.f, 8.f), L.PanelSize, &B.Fill22, WithAlpha(Night, 0.5f * A));
	Box(Geo, Out, Layer + 2, Panel - FVector2f(10.f, 10.f), L.PanelSize + FVector2f(20.f, 20.f), &B.Fill22, WithAlpha(Leather, A));
	Box(Geo, Out, Layer + 3, Panel - FVector2f(10.f, 10.f), L.PanelSize + FVector2f(20.f, 20.f), &B.Line22, WithAlpha(LeatherDark, A));
	const float LeftWidth = L.DetailPos.X - L.Panel.X;
	Box(Geo, Out, Layer + 4, Panel, FVector2f(LeftWidth - 4.f, L.PanelSize.Y), &B.Fill14, WithAlpha(Parchment, A));
	Box(Geo, Out, Layer + 4, Panel + FVector2f(LeftWidth + 4.f, 0.f), FVector2f(L.DetailSize.X - 4.f, L.PanelSize.Y), &B.Fill14,
		WithAlpha(Parchment, A));
	// The fold between the pages.
	Box(Geo, Out, Layer + 5, Panel + FVector2f(LeftWidth - 10.f, 0.f), FVector2f(20.f, L.PanelSize.Y), White(),
		WithAlpha(ParchmentShade, 0.7f * A));
	Box(Geo, Out, Layer + 5, Panel + FVector2f(LeftWidth - 1.f, 0.f), FVector2f(2.f, L.PanelSize.Y), White(),
		WithAlpha(InkSoft, 0.35f * A));

	// Headings.
	Text(Geo, Out, Layer + 6, Panel + FVector2f(PageMargin, 24.f), TEXT("Satchel"), Font(22), WithAlpha(Ink, A));
	Text(Geo, Out, Layer + 6, Panel + FVector2f(PageMargin, 68.f), TEXT("PACK"), Font(10), WithAlpha(InkSoft, A));
	const float HotbarLabelY = (Slots.IsValidIndex(0) ? L.SlotPos[0].Y : L.Panel.Y + 300.f) - 24.f;
	Text(Geo, Out, Layer + 6, FVector2f(Panel.X + PageMargin, HotbarLabelY + Drop), TEXT("HOTBAR  (keys 1-9)"), Font(10), WithAlpha(InkSoft, A));
	const FString Hint = TEXT("Click to pick up, click again to place.  Hover + 1-9 sends to the hotbar.  I or Tab closes.");
	Text(Geo, Out, Layer + 6, Panel + FVector2f(PageMargin, L.PanelSize.Y - 30.f), Hint, Font(9, false), WithAlpha(InkSoft, A));

	// Empty sockets that complete the pack grid's last row.
	const int32 Columns = HotbarCount;
	const int32 PackCount = FMath::Max(0, Slots.Num() - HotbarCount);
	const int32 Cells = FMath::DivideAndRoundUp(PackCount, Columns) * Columns;
	for (int32 k = PackCount; k < Cells; ++k)
	{
		const FVector2f Pos = Panel + FVector2f(PageMargin + (k % Columns) * (BagSlot + BagGap), 96.f + (k / Columns) * (BagSlot + BagGap));
		Box(Geo, Out, Layer + 6, Pos, FVector2f(BagSlot, BagSlot), &B.Line10, WithAlpha(Ink, 0.12f * A));
	}

	for (int32 i = 0; i < Slots.Num(); ++i)
	{
		const FVector2f Pos = L.SlotPos[i] + FVector2f(0.f, Drop);
		PaintSlot(Geo, Out, Layer + 7, Pos, L.SlotSize, Slots[i], i, i == ActiveSlot, i == Hovered, i == Carried, A, i < HotbarCount);
	}

	PaintDetails(Geo, Out, Layer + 20, L);

	// The carried stack follows the cursor.
	if (Slots.IsValidIndex(Carried))
	{
		PaintSlot(Geo, Out, Layer + 40, Cursor - FVector2f(L.SlotSize * 0.5f, L.SlotSize * 0.5f), L.SlotSize, Slots[Carried], Carried,
			false, true, false, A, false);
	}
}

void SLyrisInventoryView::PaintDetails(const FGeometry& Geo, FSlateWindowElementList& Out, int32 Layer, const FLayout& L) const
{
	using namespace LyrisInventoryStyle;
	const float A = OpenAlpha;
	const FBrushes& B = Brushes();
	const float Drop = (1.f - A) * 18.f;
	const FVector2f Page = L.DetailPos + FVector2f(0.f, Drop);
	const float Width = L.DetailSize.X;

	int32 Shown = Slots.IsValidIndex(Carried) ? Carried : Hovered;
	if (!Slots.IsValidIndex(Shown) || Slots[Shown].bEmpty)
	{
		Shown = (Slots.IsValidIndex(ActiveSlot) && !Slots[ActiveSlot].bEmpty) ? ActiveSlot : INDEX_NONE;
	}
	if (Shown == INDEX_NONE)
	{
		const FString Empty = TEXT("Hover over something to read about it.");
		const FSlateFontInfo F = Font(11, false);
		const FVector2f M = Measure(Empty, F);
		Text(Geo, Out, Layer, Page + FVector2f((Width - M.X) * 0.5f, L.DetailSize.Y * 0.45f), Empty, F, WithAlpha(InkSoft, A));
		return;
	}
	const FLyrisSlotView& View = Slots[Shown];

	// Picture in a soft vignette.
	const float IconSize = 120.f;
	const FVector2f IconPos = Page + FVector2f((Width - IconSize) * 0.5f, 40.f);
	Box(Geo, Out, Layer, IconPos - FVector2f(16.f, 16.f), FVector2f(IconSize + 32.f, IconSize + 32.f), &B.Fill22,
		WithAlpha(ParchmentShade, 0.6f * A));
	if (View.Icon)
	{
		Box(Geo, Out, Layer + 1, IconPos, FVector2f(IconSize, IconSize), View.Icon, FLinearColor(1.f, 1.f, 1.f, A));
	}

	float Y = IconPos.Y + IconSize + 28.f;
	const FSlateFontInfo NameFont = Font(17);
	for (const FString& Line : Wrap(View.Name, NameFont, Width - 40.f))
	{
		const FVector2f M = Measure(Line, NameFont);
		Text(Geo, Out, Layer + 2, FVector2f(Page.X + (Width - M.X) * 0.5f, Y), Line, NameFont, WithAlpha(Ink, A));
		Y += M.Y + 2.f;
	}

	// Kind, and quality when it isn't Normal.
	FString Meta = View.Kind;
	if (View.Quality > 0 && View.Quality < 4)
	{
		Meta += FString::Printf(TEXT("   %s"), QualityName[View.Quality]);
	}
	const FSlateFontInfo MetaFont = Font(10);
	const FVector2f MetaSize = Measure(Meta, MetaFont);
	Y += 4.f;
	Text(Geo, Out, Layer + 2, FVector2f(Page.X + (Width - MetaSize.X) * 0.5f, Y), Meta, MetaFont,
		WithAlpha(View.Quality > 0 ? Leather : InkSoft, A));
	Y += MetaSize.Y + 14.f;

	// Divider with a little diamond.
	Box(Geo, Out, Layer + 2, FVector2f(Page.X + 40.f, Y), FVector2f(Width - 80.f, 1.5f), White(), WithAlpha(InkSoft, 0.4f * A));
	Box(Geo, Out, Layer + 3, FVector2f(Page.X + Width * 0.5f - 4.f, Y - 3.f), FVector2f(8.f, 8.f), &B.Dot, WithAlpha(Gold, A));
	Y += 18.f;

	const FSlateFontInfo BodyFont = Font(11, false);
	for (const FString& Line : Wrap(View.Description, BodyFont, Width - 56.f))
	{
		const FVector2f M = Measure(Line, BodyFont);
		Text(Geo, Out, Layer + 2, FVector2f(Page.X + (Width - M.X) * 0.5f, Y), Line, BodyFont, WithAlpha(Ink, A));
		Y += M.Y + 3.f;
	}

	const FString Stack = View.MaxStack > 1 ? FString::Printf(TEXT("%d carried  (stacks to %d)"), View.Count, View.MaxStack)
		: FString(TEXT("One of a kind in a slot"));
	const FSlateFontInfo StackFont = Font(9, false);
	const FVector2f StackSize = Measure(Stack, StackFont);
	Text(Geo, Out, Layer + 2, FVector2f(Page.X + (Width - StackSize.X) * 0.5f, Page.Y + L.DetailSize.Y - 34.f), Stack, StackFont,
		WithAlpha(InkSoft, A));
}

int32 SLyrisInventoryView::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	using namespace LyrisInventoryStyle;
	if (Slots.Num() == 0)
	{
		return LayerId;
	}
	const FVector2D LocalSize = AllottedGeometry.GetLocalSize();
	const FLayout Layout = ComputeLayout(FVector2f(static_cast<float>(LocalSize.X), static_cast<float>(LocalSize.Y)));
	PaintHotbar(AllottedGeometry, OutDrawElements, LayerId, Layout);
	PaintPrompt(AllottedGeometry, OutDrawElements, LayerId + 25, Layout);
	PaintToasts(AllottedGeometry, OutDrawElements, LayerId + 30, Layout);
	PaintSatchel(AllottedGeometry, OutDrawElements, LayerId + 40, Layout);
	return LayerId + 100;
}
