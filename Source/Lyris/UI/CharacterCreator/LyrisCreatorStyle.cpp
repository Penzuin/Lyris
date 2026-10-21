// Lyris character creator: style values. Retune the creator's look here.

#include "UI/CharacterCreator/LyrisCreatorStyle.h"

#include "Brushes/SlateColorBrush.h"
#include "Brushes/SlateNoResource.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Styling/CoreStyle.h"

FLinearColor FLyrisCreatorStyle::Hex(const TCHAR* InHex)
{
	// FColor is sRGB; converting to FLinearColor linearises it, which is what Slate expects.
	return FLinearColor(FColor::FromHex(FString(InHex)));
}

const FLyrisCreatorStyle& FLyrisCreatorStyle::Get()
{
	// Built lazily on first use, after Slate and FCoreStyle exist.
	static FLyrisCreatorStyle Instance;
	return Instance;
}

FLyrisCreatorStyle::FLyrisCreatorStyle()
{
	// ---------------------------------------------------------------- Palette
	Sail       = Hex(TEXT("F7EEDC"));
	Sand       = Hex(TEXT("F1E9DC"));
	Clay       = Hex(TEXT("36221A"));
	DarkWood   = Hex(TEXT("4A2A1C"));
	Wood       = Hex(TEXT("8B5A3A"));
	Gold       = Hex(TEXT("E3AE45"));
	Terracotta = Hex(TEXT("C8643A"));
	RedBand    = Hex(TEXT("C8443A"));
	Leaf       = Hex(TEXT("6E8A3A"));
	Shallows   = Hex(TEXT("7FD0D6"));
	Moonglass  = Hex(TEXT("7AC0E6"));

	// ---------------------------------------------------------------- Fonts
	// TODO(UI): replace Roboto with a storybook serif (e.g. a Garamond-like face) imported as a
	// font asset under Content/Lyris/UI/Fonts, then load it here with FSlateFontInfo(Font, Size).
	TitleFont   = FCoreStyle::GetDefaultFontStyle("Bold", 26);
	HeadingFont = FCoreStyle::GetDefaultFontStyle("Bold", 17);
	BodyFont    = FCoreStyle::GetDefaultFontStyle("Regular", 13);
	SmallFont   = FCoreStyle::GetDefaultFontStyle("Italic", 11);
	ValueFont   = FCoreStyle::GetDefaultFontStyle("Bold", 12);
	ButtonFont  = FCoreStyle::GetDefaultFontStyle("Bold", 13);

	// ---------------------------------------------------------------- Brushes
	const FLinearColor Clear(0.f, 0.f, 0.f, 0.f);
	const FLinearColor SailPanel = Sail.CopyWithNewOpacity(PanelOpacity);
	const FLinearColor SandPanel = Sand.CopyWithNewOpacity(FMath::Min(1.f, PanelOpacity + 0.05f));

	PanelBrush          = FSlateRoundedBoxBrush(SailPanel, CornerRadius, Wood, 2.f);
	SubPanelBrush       = FSlateRoundedBoxBrush(SandPanel, SmallRadius, Wood.CopyWithNewOpacity(0.45f), 1.f);
	TileBrush           = FSlateRoundedBoxBrush(Sand, SmallRadius, Wood.CopyWithNewOpacity(0.55f), 1.f);
	TileSelectedBrush   = FSlateRoundedBoxBrush(Gold, SmallRadius, DarkWood, 2.f);
	HoverOverlayBrush   = FSlateRoundedBoxBrush(Sand, SmallRadius, Terracotta, 2.f);
	PressedOverlayBrush = FSlateRoundedBoxBrush(Gold.CopyWithNewOpacity(0.6f), SmallRadius, Terracotta, 2.f);
	NoBrush             = FSlateNoResource();
	InkLineBrush        = FSlateColorBrush(Wood.CopyWithNewOpacity(0.5f));

	// White so SImage::ColorAndOpacity can tint it to the swatch colour.
	SwatchBrush     = FSlateRoundedBoxBrush(FLinearColor::White, SwatchSize * 0.5f, DarkWood.CopyWithNewOpacity(0.6f), 1.f, FVector2f(SwatchSize, SwatchSize));
	SwatchRingBrush = FSlateRoundedBoxBrush(Clear, (SwatchSize + 8.f) * 0.5f, Gold, 3.f, FVector2f(SwatchSize + 8.f, SwatchSize + 8.f));

	const FVector2f MarkerSize(LanternMarkerSize, LanternMarkerSize);
	LanternUnlitBrush   = FSlateRoundedBoxBrush(Sand, LanternMarkerSize * 0.5f, Wood, 2.f, MarkerSize);
	LanternLitBrush     = FSlateRoundedBoxBrush(Gold.CopyWithNewOpacity(0.7f), LanternMarkerSize * 0.5f, Wood, 2.f, MarkerSize);
	LanternCurrentBrush = FSlateRoundedBoxBrush(Gold, LanternMarkerSize * 0.5f, Terracotta, 3.f, MarkerSize);

	SculptRingBrush = FSlateRoundedBoxBrush(Gold.CopyWithNewOpacity(0.18f), SculptRingSize * 0.5f, Gold, 2.f, FVector2f(SculptRingSize, SculptRingSize));

	MistChipBrush         = FSlateRoundedBoxBrush(Moonglass.CopyWithNewOpacity(0.55f), SmallRadius, Wood.CopyWithNewOpacity(0.55f), 1.f);
	MistChipSelectedBrush = FSlateRoundedBoxBrush(Moonglass, SmallRadius, DarkWood, 2.f);
	FocusRowBrush         = FSlateRoundedBoxBrush(Sand, SmallRadius, Gold, 2.f);
	BigSwatchBrush        = FSlateRoundedBoxBrush(FLinearColor::White, 40.f, DarkWood, 2.f, FVector2f(80.f, 80.f));

	// ---------------------------------------------------------------- Buttons
	ButtonStyle = FButtonStyle()
		.SetNormal(TileBrush)
		.SetHovered(HoverOverlayBrush)
		.SetPressed(PressedOverlayBrush)
		.SetDisabled(FSlateRoundedBoxBrush(Sand.CopyWithNewOpacity(0.5f), SmallRadius, Wood.CopyWithNewOpacity(0.25f), 1.f))
		.SetNormalForeground(FSlateColor(DarkWood))
		.SetHoveredForeground(FSlateColor(DarkWood))
		.SetPressedForeground(FSlateColor(DarkWood))
		.SetDisabledForeground(FSlateColor(Wood.CopyWithNewOpacity(0.5f)))
		.SetNormalPadding(FMargin(12.f, 7.f))
		.SetPressedPadding(FMargin(12.f, 8.f, 12.f, 6.f));

	// Transparent until hovered or pressed; the tile inside draws its own (selected) fill, so the
	// hover wash shows as a Terracotta outline around it.
	OverlayButtonStyle = FButtonStyle(ButtonStyle)
		.SetNormal(NoBrush)
		.SetHovered(FSlateRoundedBoxBrush(Clear, SmallRadius, Terracotta, 2.f))
		.SetPressed(FSlateRoundedBoxBrush(Gold.CopyWithNewOpacity(0.25f), SmallRadius, Terracotta, 2.f))
		.SetNormalPadding(FMargin(2.f))
		.SetPressedPadding(FMargin(2.f));

	LinkButtonStyle = FButtonStyle(OverlayButtonStyle)
		.SetHovered(FSlateRoundedBoxBrush(Terracotta.CopyWithNewOpacity(0.15f), SmallRadius))
		.SetPressed(FSlateRoundedBoxBrush(Gold.CopyWithNewOpacity(0.3f), SmallRadius))
		.SetNormalPadding(FMargin(6.f, 2.f))
		.SetPressedPadding(FMargin(6.f, 2.f));

	// ---------------------------------------------------------------- Slider
	const FSlateBrush BarBrush   = FSlateRoundedBoxBrush(Wood.CopyWithNewOpacity(0.45f), 3.f);
	const FSlateBrush BarHover   = FSlateRoundedBoxBrush(Terracotta.CopyWithNewOpacity(0.6f), 3.f);
	const FSlateBrush ThumbBrush = FSlateRoundedBoxBrush(Gold, 9.f, DarkWood, 2.f, FVector2f(18.f, 18.f));
	const FSlateBrush ThumbHover = FSlateRoundedBoxBrush(Gold, 9.f, Terracotta, 2.f, FVector2f(18.f, 18.f));
	SliderStyle = FSliderStyle()
		.SetNormalBarImage(BarBrush)
		.SetHoveredBarImage(BarHover)
		.SetDisabledBarImage(BarBrush)
		.SetNormalThumbImage(ThumbBrush)
		.SetHoveredThumbImage(ThumbHover)
		.SetDisabledThumbImage(ThumbBrush)
		.SetBarThickness(5.f);

	// ---------------------------------------------------------------- Toggle (symmetry, locks)
	ToggleStyle = FCheckBoxStyle()
		.SetCheckBoxType(ESlateCheckBoxType::ToggleButton)
		.SetUncheckedImage(TileBrush)
		.SetUncheckedHoveredImage(HoverOverlayBrush)
		.SetUncheckedPressedImage(PressedOverlayBrush)
		.SetCheckedImage(TileSelectedBrush)
		.SetCheckedHoveredImage(FSlateRoundedBoxBrush(Gold, SmallRadius, Terracotta, 2.f))
		.SetCheckedPressedImage(PressedOverlayBrush)
		.SetPadding(FMargin(10.f, 6.f));

	// ---------------------------------------------------------------- Text box (name, share code)
	TextBoxStyle = FCoreStyle::Get().GetWidgetStyle<FEditableTextBoxStyle>("NormalEditableTextBox");
	TextBoxStyle
		.SetBackgroundImageNormal(TileBrush)
		.SetBackgroundImageHovered(HoverOverlayBrush)
		.SetBackgroundImageFocused(FSlateRoundedBoxBrush(Sail, SmallRadius, Gold, 2.f))
		.SetBackgroundImageReadOnly(SubPanelBrush)
		.SetForegroundColor(FSlateColor(DarkWood))
		.SetPadding(FMargin(10.f, 8.f));
}
