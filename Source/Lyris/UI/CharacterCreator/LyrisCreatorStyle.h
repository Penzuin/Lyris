// Lyris character creator: one place for every colour, size and font the creator uses.

#pragma once

#include "CoreMinimal.h"
#include "Styling/SlateTypes.h"
#include "Styling/SlateBrush.h"
#include "Fonts/SlateFontInfo.h"
#include "Layout/Margin.h"

/**
 * Look of the character creator: parchment and dusk, not sci-fi.
 *
 * Every colour, size and font used by SLyrisCharacterCreator and SLyrisCreatorViewport lives
 * here so the whole screen can be retuned in one file. Colours come from the PALETTE in
 * Content/Python/lyris_build_harbor.py (see design/character_creator contract); do not add new
 * hex values here without asking the Environment lane.
 *
 * Brushes are stored as plain FSlateBrush values (built from FSlateRoundedBoxBrush), so widgets
 * can point at them for the lifetime of the program. Use FLyrisCreatorStyle::Get().
 */
struct FLyrisCreatorStyle
{
	FLyrisCreatorStyle();

	/** The shared instance. Built on first use (Slate must be initialised by then). */
	static const FLyrisCreatorStyle& Get();

	// ---------------------------------------------------------------- Palette (Harbor PALETTE)
	FLinearColor Sail;        // F7EEDC  panel parchment
	FLinearColor Sand;        // F1E9DC  tiles, sub panels
	FLinearColor Clay;        // 36221A  deepest ink
	FLinearColor DarkWood;    // 4A2A1C  body text
	FLinearColor Wood;        // 8B5A3A  borders, secondary text
	FLinearColor Gold;        // E3AE45  selected / active
	FLinearColor Terracotta;  // C8643A  hover accents
	FLinearColor RedBand;     // C8443A  errors
	FLinearColor Leaf;        // 6E8A3A  "ok" accents
	FLinearColor Shallows;    // 7FD0D6
	FLinearColor Moonglass;   // 7AC0E6  mist lighting chip, cold lamp light

	// ---------------------------------------------------------------- Sizes
	float PanelOpacity = 0.90f;      // parchment panels are slightly see-through
	float CornerRadius = 14.f;       // panels
	float SmallRadius = 8.f;         // buttons, tiles
	FMargin ScreenPadding = FMargin(28.f, 20.f);
	FMargin PanelPadding = FMargin(18.f, 16.f);
	float Gap = 10.f;                // generic spacing between rows
	float LeftColumnWidth = 300.f;
	float RightPanelWidth = 450.f;
	float TileHeight = 54.f;
	int32 TileColumns = 3;
	float SwatchSize = 32.f;
	int32 SwatchColumns = 8;
	float LanternMarkerSize = 22.f;
	float SculptPickRadius = 70.f;   // slate units around a projected face anchor
	float SculptRingSize = 46.f;

	// ---------------------------------------------------------------- Fonts
	// TODO(UI): swap these for a storybook serif font asset once one exists (Content/Lyris/UI/Fonts).
	// Until then we use the engine's Roboto, larger and bolder for headings.
	FSlateFontInfo TitleFont;    // step title
	FSlateFontInfo HeadingFont;  // panel headings
	FSlateFontInfo BodyFont;     // labels
	FSlateFontInfo SmallFont;    // hints, tooltips
	FSlateFontInfo ValueFont;    // slider value labels
	FSlateFontInfo ButtonFont;

	// ---------------------------------------------------------------- Brushes
	FSlateBrush PanelBrush;          // Sail, translucent, Wood border
	FSlateBrush SubPanelBrush;       // Sand
	FSlateBrush TileBrush;           // unselected tile / tab
	FSlateBrush TileSelectedBrush;   // Gold
	FSlateBrush HoverOverlayBrush;   // Terracotta wash drawn over a tile on hover
	FSlateBrush PressedOverlayBrush;
	FSlateBrush NoBrush;
	FSlateBrush InkLineBrush;        // thin separators
	FSlateBrush SwatchBrush;         // white rounded square, tinted by the swatch colour
	FSlateBrush SwatchRingBrush;     // Gold ring around the chosen swatch
	FSlateBrush LanternUnlitBrush;   // route markers in the top bar
	FSlateBrush LanternLitBrush;
	FSlateBrush LanternCurrentBrush;
	FSlateBrush SculptRingBrush;     // ring drawn around a hovered face region
	FSlateBrush MistChipBrush;       // Moonglass chip for the Mist lighting preset
	FSlateBrush MistChipSelectedBrush;
	FSlateBrush FocusRowBrush;       // slider row that arrow keys currently adjust
	FSlateBrush BigSwatchBrush;      // lantern glass preview

	// ---------------------------------------------------------------- Widget styles
	FButtonStyle ButtonStyle;        // regular parchment button
	FButtonStyle OverlayButtonStyle; // transparent button used inside tiles (tile draws its own fill)
	FButtonStyle LinkButtonStyle;    // no fill until hovered (voyage route markers)
	FSliderStyle SliderStyle;
	FCheckBoxStyle ToggleStyle;      // toggle-button look (symmetry, locks)
	FEditableTextBoxStyle TextBoxStyle;

	// ---------------------------------------------------------------- Helpers
	static FLinearColor Hex(const TCHAR* InHex);
};
