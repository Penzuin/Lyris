// Lyris character creator: hard-coded step cards and layout tables (from design/character_creator.md).

#include "UI/CharacterCreator/LyrisCreatorData.h"

#define LOCTEXT_NAMESPACE "LyrisCreator"

namespace LyrisCreatorData
{
	const FName People_Human(TEXT("Human"));
	const FName People_MoonlitElf(TEXT("MoonlitElf"));
	const FName People_Deepkin(TEXT("Deepkin"));
	const FName Frame_A(TEXT("FrameA"));
	const FName Frame_B(TEXT("FrameB"));
	const FName Slot_Outfit(TEXT("Outfit"));
	const FName Slot_Lantern(TEXT("Lantern"));
	const FName Slot_Expression(TEXT("Expression"));
	const FName Channel_IrisL(TEXT("Eyes.IrisL"));
	const FName Channel_IrisR(TEXT("Eyes.IrisR"));
	const FName Channel_HairBrows(TEXT("Hair.Brows"));
	const FName Channel_HairFacialHair(TEXT("Hair.FacialHair"));
	const FName Channel_LanternGlass(TEXT("Lantern.Glass"));
	const FName Scalar_Heterochromia(TEXT("Eyes.Heterochromia"));
	const FName Scalar_BrowsMatchHair(TEXT("Brows.MatchHair"));
	const FName Scalar_FacialHairMatchHair(TEXT("FacialHair.MatchHair"));
	const FName Category_Lantern(TEXT("Lantern"));

	// ------------------------------------------------------------------------------------ Steps

	int32 NumSteps()
	{
		return static_cast<int32>(ELyrisCreatorStep::Count);
	}

	FText StepName(ELyrisCreatorStep Step)
	{
		switch (Step)
		{
		case ELyrisCreatorStep::People:     return LOCTEXT("StepPeople", "People");
		case ELyrisCreatorStep::Appearance: return LOCTEXT("StepAppearance", "Appearance");
		case ELyrisCreatorStep::Path:       return LOCTEXT("StepPath", "Path");
		case ELyrisCreatorStep::Backstory:  return LOCTEXT("StepBackstory", "Backstory");
		case ELyrisCreatorStep::Lantern:    return LOCTEXT("StepLantern", "Lantern");
		case ELyrisCreatorStep::Name:       return LOCTEXT("StepName", "Name");
		default:                            return FText::GetEmpty();
		}
	}

	FText StepMoment(ELyrisCreatorStep Step)
	{
		switch (Step)
		{
		case ELyrisCreatorStep::People:
			return LOCTEXT("MomentPeople", "The sloop leaves the last waystone. \"Where do you hail from, friend?\"");
		case ELyrisCreatorStep::Appearance:
			return LOCTEXT("MomentAppearance", "Under the stern lamp, by the ship's mirror. \"Let's get a look at you before we make port.\"");
		case ELyrisCreatorStep::Path:
			return LOCTEXT("MomentPath", "Your sea chest lies open on deck. A head start, not a fence.");
		case ELyrisCreatorStep::Backstory:
			return LOCTEXT("MomentBackstory", "A keepsake from the chest. \"So what brings you out here?\"");
		case ELyrisCreatorStep::Lantern:
			return LOCTEXT("MomentLantern", "Moonharbor's lights come into view, and the mist begins to curl off the water.");
		case ELyrisCreatorStep::Name:
			return LOCTEXT("MomentName", "The sloop ties up. The harbourmaster opens the ledger by lamplight.");
		default:
			return FText::GetEmpty();
		}
	}

	ELyrisCreatorShot StepShot(ELyrisCreatorStep Step)
	{
		switch (Step)
		{
		case ELyrisCreatorStep::People:     return ELyrisCreatorShot::Full;
		case ELyrisCreatorStep::Appearance: return ELyrisCreatorShot::Full; // then per section
		case ELyrisCreatorStep::Lantern:    return ELyrisCreatorShot::Lantern;
		default:                            return ELyrisCreatorShot::Upper;
		}
	}

	// ------------------------------------------------------------------------------------ Cards

	/** An (id, display name) pair, for the small lookup tables below. */
	static TPair<FName, FText> Opt(const TCHAR* Id, const FText& Name)
	{
		return TPair<FName, FText>(FName(Id), Name);
	}

	static FLyrisCreatorCard Card(const TCHAR* Id, const FText& Title, const FText& Line1, const FText& Line2 = FText::GetEmpty(),
		const TCHAR* ForPath = nullptr, const TCHAR* DefaultPart = nullptr)
	{
		FLyrisCreatorCard C;
		C.Id = FName(Id);
		C.Title = Title;
		C.Line1 = Line1;
		C.Line2 = Line2;
		C.ForPath = ForPath ? FName(ForPath) : NAME_None;
		C.DefaultPart = DefaultPart ? FName(DefaultPart) : NAME_None;
		return C;
	}

	const TArray<FLyrisCreatorCard>& Peoples()
	{
		// Peoples differ in look only (DECISIONS): no perk text on these cards, just what they look like.
		static const TArray<FLyrisCreatorCard> List = {
			Card(TEXT("Human"), LOCTEXT("PHuman", "Human"),
				LOCTEXT("PHuman1", "Warm skin from very fair to very deep, round ears."),
				LOCTEXT("PHuman2", "Harbour ink tattoos.")),
			Card(TEXT("MoonlitElf"), LOCTEXT("PElf", "Moonlit elf"),
				LOCTEXT("PElf1", "Moonmilk to nightfall blue-lavender skin, long pointed ears."),
				LOCTEXT("PElf2", "Moon sigils and eyes that glow softly in mist.")),
			Card(TEXT("Deepkin"), LOCTEXT("PDeep", "Deepkin"),
				LOCTEXT("PDeep1", "Sea-green to slate skin, long ears and fin-ears."),
				LOCTEXT("PDeep2", "Shimmering scale patches and eyes that catch the light.")),
		};
		return List;
	}

	const TArray<FLyrisCreatorCard>& Paths()
	{
		static const TArray<FLyrisCreatorCard> List = {
			Card(TEXT("Seafarer"), LOCTEXT("Seafarer", "Seafarer"), LOCTEXT("Seafarer1", "Starts with a spyglass"),
				LOCTEXT("Seafarer2", "Sailor, Fisher, Shipwright, Navigator"), nullptr, TEXT("Outfit.DeckhandCoat")),
			Card(TEXT("Wanderer"), LOCTEXT("Wanderer", "Wanderer"), LOCTEXT("Wanderer1", "Starts with a walking staff and pack"),
				LOCTEXT("Wanderer2", "Wayfarer, Drover, Hunter, Castaway"), nullptr, TEXT("Outfit.WandererLayers")),
			Card(TEXT("Grower"), LOCTEXT("Grower", "Grower"), LOCTEXT("Grower1", "Starts with a trowel and seed pouch"),
				LOCTEXT("Grower2", "Gardener, Herbalist, Cultivator of strange plants"), nullptr, TEXT("Outfit.GrowerSmock")),
			Card(TEXT("Maker"), LOCTEXT("Maker", "Maker"), LOCTEXT("Maker1", "Starts with a tool roll"),
				LOCTEXT("Maker2", "Artisan, Builder, Clockmaker, Shipwright"), nullptr, TEXT("Outfit.MakerApron")),
			Card(TEXT("Scholar"), LOCTEXT("Scholar", "Scholar"), LOCTEXT("Scholar1", "Starts with a notebook"),
				LOCTEXT("Scholar2", "Cartographer, Archivist, Name-keeper, Alchemist"), nullptr, TEXT("Outfit.ScholarCoat")),
			Card(TEXT("Trader"), LOCTEXT("Trader", "Trader"), LOCTEXT("Trader1", "Starts with a ledger and scales"),
				LOCTEXT("Trader2", "Merchant, Cook, Innkeeper"), nullptr, TEXT("Outfit.TraderWaistcoat")),
			Card(TEXT("Delver"), LOCTEXT("Delver", "Delver"), LOCTEXT("Delver1", "Starts with a lamp and pick"),
				LOCTEXT("Delver2", "Miner, Relic hunter, Diver"), nullptr, TEXT("Outfit.DelverLeathers")),
		};
		return List;
	}

	const TArray<FLyrisCreatorCard>& Backstories()
	{
		static const FText Adds = LOCTEXT("BackAdds", "Adds flavour dialogue and a personal quest.");
		static const TArray<FLyrisCreatorCard> List = {
			Card(TEXT("OldShoreCastaway"), LOCTEXT("B1", "Old Shore castaway"), Adds, FText::GetEmpty(), TEXT("Seafarer")),
			Card(TEXT("HerringRoadDrover"), LOCTEXT("B2", "Drover of the Herring Road"), Adds, FText::GetEmpty(), TEXT("Wanderer")),
			Card(TEXT("OldHuntHunter"), LOCTEXT("B3", "Hunter of the Old Hunt"), Adds, FText::GetEmpty(), TEXT("Wanderer")),
			Card(TEXT("Wayfarer"), LOCTEXT("B4", "Wayfarer"), Adds, FText::GetEmpty(), TEXT("Wanderer")),
			Card(TEXT("Herbalist"), LOCTEXT("B5", "Herbalist"), Adds, FText::GetEmpty(), TEXT("Grower")),
			Card(TEXT("ClockmakerApprentice"), LOCTEXT("B6", "Clockmaker's apprentice"), Adds, FText::GetEmpty(), TEXT("Maker")),
			Card(TEXT("Musician"), LOCTEXT("B7", "Musician"), Adds, FText::GetEmpty(), TEXT("Maker")),
			Card(TEXT("AlembicDescendant"), LOCTEXT("B8", "Alembic descendant"), Adds, FText::GetEmpty(), TEXT("Scholar")),
			Card(TEXT("AshenLedgerNameKeeper"), LOCTEXT("B9", "Name-keeper of the Ashen Ledger"), Adds, FText::GetEmpty(), TEXT("Scholar")),
			Card(TEXT("CookFamilyRecipes"), LOCTEXT("B10", "Cook's family recipes"), Adds, FText::GetEmpty(), TEXT("Trader")),
			Card(TEXT("DeepkinMiner"), LOCTEXT("B11", "Deepkin miner"), Adds, FText::GetEmpty(), TEXT("Delver")),
		};
		return List;
	}

	const TArray<FLyrisCreatorCard>& Lanterns()
	{
		static const TArray<FLyrisCreatorCard> List = {
			Card(TEXT("Lantern.Ships"), LOCTEXT("L1", "Ship's lantern"), LOCTEXT("L1a", "Classic brass and glass, ring handle")),
			Card(TEXT("Lantern.StormHex"), LOCTEXT("L2", "Storm lantern"), LOCTEXT("L2a", "Six-sided, caged glass")),
			Card(TEXT("Lantern.MoonGlobe"), LOCTEXT("L3", "Moon globe"), LOCTEXT("L3a", "Round glass globe in a thin frame")),
			Card(TEXT("Lantern.HangingBell"), LOCTEXT("L4", "Hanging bell"), LOCTEXT("L4a", "Bell-shaped, rings softly when swung")),
			Card(TEXT("Lantern.Lighthouse"), LOCTEXT("L5", "Little lighthouse"), LOCTEXT("L5a", "A tiny lighthouse with a turning shade")),
			Card(TEXT("Lantern.Shell"), LOCTEXT("L6", "Shell lantern"), LOCTEXT("L6a", "Glass set in a large spiral shell")),
			Card(TEXT("Lantern.BrassStar"), LOCTEXT("L7", "Brass star"), LOCTEXT("L7a", "Star-pierced brass, throws star dots")),
			Card(TEXT("Lantern.Reading"), LOCTEXT("L8", "Reading lantern"), LOCTEXT("L8a", "Tall and narrow, with a hood to aim the light")),
			Card(TEXT("Lantern.Seedpod"), LOCTEXT("L9", "Seedpod"), LOCTEXT("L9a", "Woven-reed pod round a glass heart")),
		};
		return List;
	}

	// ------------------------------------------------------------------------------------ Appearance layout

	const TArray<FName>& Categories()
	{
		static const TArray<FName> List = {
			TEXT("Body"), TEXT("Face"), TEXT("Eyes"), TEXT("Hair"), TEXT("Skin"), TEXT("Makeup"), TEXT("Outfit"), TEXT("Voice")
		};
		return List;
	}

	FText CategoryName(FName Category)
	{
		static const TArray<TPair<FName, FText>> Names = {
			Opt(TEXT("Body"),   LOCTEXT("CBody", "Body")),
			Opt(TEXT("Face"),   LOCTEXT("CFace", "Face")),
			Opt(TEXT("Eyes"),   LOCTEXT("CEyes", "Eyes")),
			Opt(TEXT("Hair"),   LOCTEXT("CHair", "Hair")),
			Opt(TEXT("Skin"),   LOCTEXT("CSkin", "Skin")),
			Opt(TEXT("Makeup"), LOCTEXT("CMakeup", "Makeup")),
			Opt(TEXT("Outfit"), LOCTEXT("COutfit", "Outfit")),
			Opt(TEXT("Voice"),  LOCTEXT("CVoice", "Voice")),
		};
		for (const TPair<FName, FText>& Entry : Names)
		{
			if (Entry.Key == Category)
			{
				return Entry.Value;
			}
		}
		return FText::FromName(Category);
	}

	static FLyrisCreatorSectionInfo Sec(const TCHAR* Category, const TCHAR* Section, const FText& Name, ELyrisCreatorShot Shot)
	{
		FLyrisCreatorSectionInfo S;
		S.Category = FName(Category);
		S.Section = FName(Section);
		S.DisplayName = Name;
		S.Shot = Shot;
		return S;
	}

	const TArray<FLyrisCreatorSectionInfo>& Sections()
	{
		using S = ELyrisCreatorShot;
		// Order = display order. Framings from spec 2.1.
		static const TArray<FLyrisCreatorSectionInfo> List = {
			Sec(TEXT("Body"), TEXT("Frame"),       LOCTEXT("SFrame", "Frame & height"), S::Full),
			Sec(TEXT("Body"), TEXT("Proportions"), LOCTEXT("SProp", "Proportions"), S::Full),
			Sec(TEXT("Body"), TEXT("Build"),       LOCTEXT("SBuild", "Build"), S::Full),
			Sec(TEXT("Body"), TEXT("HandsFeet"),   LOCTEXT("SHands", "Hands & feet"), S::Upper),
			Sec(TEXT("Body"), TEXT("Posture"),     LOCTEXT("SPosture", "Posture"), S::Full),

			Sec(TEXT("Face"), TEXT("Shape"),    LOCTEXT("SShape", "Shape"), S::Face),
			Sec(TEXT("Face"), TEXT("Forehead"), LOCTEXT("SForehead", "Forehead & brow ridge"), S::Face),
			Sec(TEXT("Face"), TEXT("Eyes"),     LOCTEXT("SEyesShape", "Eyes"), S::Eyes),
			Sec(TEXT("Face"), TEXT("Brows"),    LOCTEXT("SBrowsShape", "Brows"), S::Eyes),
			Sec(TEXT("Face"), TEXT("Nose"),     LOCTEXT("SNose", "Nose"), S::Face),
			Sec(TEXT("Face"), TEXT("Mouth"),    LOCTEXT("SMouth", "Mouth"), S::Face),
			Sec(TEXT("Face"), TEXT("Ears"),     LOCTEXT("SEars", "Ears"), S::Face),

			Sec(TEXT("Eyes"), TEXT("Colour"), LOCTEXT("SEyeColour", "Colour"), S::Eyes),
			Sec(TEXT("Eyes"), TEXT("Detail"), LOCTEXT("SEyeDetail", "Detail"), S::Eyes),

			Sec(TEXT("Hair"), TEXT("Style"),       LOCTEXT("SHairStyle", "Style"), S::Upper),
			Sec(TEXT("Hair"), TEXT("Colour"),      LOCTEXT("SHairColour", "Colour"), S::Face),
			Sec(TEXT("Hair"), TEXT("Brows"),       LOCTEXT("SHairBrows", "Brows"), S::Face),
			Sec(TEXT("Hair"), TEXT("FacialHair"),  LOCTEXT("SFacialHair", "Facial hair"), S::Face),
			Sec(TEXT("Hair"), TEXT("Accessories"), LOCTEXT("SAccessories", "Accessories"), S::Upper),

			Sec(TEXT("Skin"), TEXT("Tone"),     LOCTEXT("STone", "Tone"), S::Face),
			Sec(TEXT("Skin"), TEXT("Details"),  LOCTEXT("SDetails", "Freckles, moles & scars"), S::Face),
			Sec(TEXT("Skin"), TEXT("Markings"), LOCTEXT("SMarkings", "Markings"), S::Upper),

			Sec(TEXT("Makeup"), TEXT("Eyes"),      LOCTEXT("SMEyes", "Eyes"), S::Eyes),
			Sec(TEXT("Makeup"), TEXT("Lips"),      LOCTEXT("SMLips", "Lips"), S::Face),
			Sec(TEXT("Makeup"), TEXT("Cheeks"),    LOCTEXT("SMCheeks", "Cheeks"), S::Face),
			Sec(TEXT("Makeup"), TEXT("FacePaint"), LOCTEXT("SMPaint", "Face paint"), S::Face),

			Sec(TEXT("Outfit"), TEXT("Outfit"), LOCTEXT("SOutfit", "Outfit"), S::Full),
			Sec(TEXT("Outfit"), TEXT("Layer"),  LOCTEXT("SLayer", "Cloak & scarf"), S::Full),
			Sec(TEXT("Outfit"), TEXT("Colour"), LOCTEXT("SOutfitColour", "Cloth colours"), S::Full),

			Sec(TEXT("Voice"), TEXT("Voice"),      LOCTEXT("SVoice", "Voice"), S::Full),
			Sec(TEXT("Voice"), TEXT("Expression"), LOCTEXT("SExpression", "Expression"), S::Upper),
		};
		return List;
	}

	const FLyrisCreatorSectionInfo* FindSection(FName Category, FName Section)
	{
		return Sections().FindByPredicate([Category, Section](const FLyrisCreatorSectionInfo& S)
		{
			return S.Category == Category && S.Section == Section;
		});
	}

	FText SectionName(FName Category, FName Section)
	{
		if (const FLyrisCreatorSectionInfo* Info = FindSection(Category, Section))
		{
			return Info->DisplayName;
		}
		return FText::FromName(Section);
	}

	static FLyrisCreatorSlotInfo SlotInfo(const TCHAR* Slot, const TCHAR* Category, const TCHAR* Section, const FText& Name, bool bOptional)
	{
		FLyrisCreatorSlotInfo S;
		S.Slot = FName(Slot);
		S.Category = FName(Category);
		S.Section = FName(Section);
		S.DisplayName = Name;
		S.bOptional = bOptional;
		return S;
	}

	const TArray<FLyrisCreatorSlotInfo>& Slots()
	{
		// Spec 4.1. Lantern is not here: it is shown at the Lantern step only.
		static const TArray<FLyrisCreatorSlotInfo> List = {
			SlotInfo(TEXT("Stance"),        TEXT("Body"),   TEXT("Posture"),     LOCTEXT("TStance", "Idle stance"), false),
			SlotInfo(TEXT("Hair"),          TEXT("Hair"),   TEXT("Style"),       LOCTEXT("THair", "Hairstyle"), false),
			SlotInfo(TEXT("HairAccessory"), TEXT("Hair"),   TEXT("Accessories"), LOCTEXT("THairAcc", "Hair accessory"), true),
			SlotInfo(TEXT("Brows"),         TEXT("Hair"),   TEXT("Brows"),       LOCTEXT("TBrows", "Brows"), true),
			SlotInfo(TEXT("FacialHair"),    TEXT("Hair"),   TEXT("FacialHair"),  LOCTEXT("TFacialHair", "Facial hair"), true),
			SlotInfo(TEXT("Lashes"),        TEXT("Eyes"),   TEXT("Detail"),      LOCTEXT("TLashes", "Lashes"), true),
			SlotInfo(TEXT("PupilShape"),    TEXT("Eyes"),   TEXT("Colour"),      LOCTEXT("TPupil", "Pupil shape"), false),
			SlotInfo(TEXT("IrisPattern"),   TEXT("Eyes"),   TEXT("Colour"),      LOCTEXT("TIris", "Iris pattern"), false),
			SlotInfo(TEXT("Freckles"),      TEXT("Skin"),   TEXT("Details"),     LOCTEXT("TFreckles", "Freckles"), true),
			SlotInfo(TEXT("Moles"),         TEXT("Skin"),   TEXT("Details"),     LOCTEXT("TMoles", "Moles"), true),
			SlotInfo(TEXT("Scars"),         TEXT("Skin"),   TEXT("Details"),     LOCTEXT("TScars", "Scars"), true),
			SlotInfo(TEXT("Markings"),      TEXT("Skin"),   TEXT("Markings"),    LOCTEXT("TMarkings", "Markings"), true),
			SlotInfo(TEXT("Eyeshadow"),     TEXT("Makeup"), TEXT("Eyes"),        LOCTEXT("TEyeshadow", "Eyeshadow"), true),
			SlotInfo(TEXT("Eyeliner"),      TEXT("Makeup"), TEXT("Eyes"),        LOCTEXT("TEyeliner", "Eyeliner"), true),
			SlotInfo(TEXT("Lips"),          TEXT("Makeup"), TEXT("Lips"),        LOCTEXT("TLips", "Lips"), true),
			SlotInfo(TEXT("Blush"),         TEXT("Makeup"), TEXT("Cheeks"),      LOCTEXT("TBlush", "Blush"), true),
			SlotInfo(TEXT("FacePaint"),     TEXT("Makeup"), TEXT("FacePaint"),   LOCTEXT("TFacePaint", "Face paint"), true),
			SlotInfo(TEXT("Outfit"),        TEXT("Outfit"), TEXT("Outfit"),      LOCTEXT("TOutfit", "Outfit"), false),
			SlotInfo(TEXT("Layer"),         TEXT("Outfit"), TEXT("Layer"),       LOCTEXT("TLayer", "Cloak or scarf"), true),
			SlotInfo(TEXT("Voice"),         TEXT("Voice"),  TEXT("Voice"),       LOCTEXT("TVoice", "Voice"), false),
			SlotInfo(TEXT("Expression"),    TEXT("Voice"),  TEXT("Expression"),  LOCTEXT("TExpression", "Resting expression"), false),
		};
		return List;
	}

	static FLyrisCreatorScalarInfo Scalar(const TCHAR* Key, const TCHAR* Category, const TCHAR* Section, const FText& Name, const FText& Tip,
		float Min, float Max, float Default, bool bToggle = false, TArray<FName> People = {})
	{
		FLyrisCreatorScalarInfo S;
		S.Key = FName(Key);
		S.Category = FName(Category);
		S.Section = FName(Section);
		S.DisplayName = Name;
		S.Tooltip = Tip;
		S.Min = Min;
		S.Max = Max;
		S.Default = Default;
		S.bToggle = bToggle;
		S.People = MoveTemp(People);
		return S;
	}

	const TArray<FLyrisCreatorScalarInfo>& Scalars()
	{
		// Spec 3.7. Toggles are stored as 0 / 1 (Player lane reads them).
		static const TArray<FLyrisCreatorScalarInfo> List = {
			Scalar(TEXT("Hair.Length"), TEXT("Hair"), TEXT("Style"), LOCTEXT("KHairLen", "Length"), LOCTEXT("KHairLenT", "Shorter or longer, within what the style allows."), -1.f, 1.f, 0.f),
			Scalar(TEXT("Hair.Volume"), TEXT("Hair"), TEXT("Style"), LOCTEXT("KHairVol", "Volume"), LOCTEXT("KHairVolT", "Flatter or fuller."), -1.f, 1.f, 0.f),
			Scalar(TEXT("Hair.GradientStart"), TEXT("Hair"), TEXT("Colour"), LOCTEXT("KGradStart", "Tip fade starts"), LOCTEXT("KGradStartT", "Where the root colour starts fading to the tip colour (1 = no gradient)."), 0.f, 1.f, 0.7f),
			Scalar(TEXT("Hair.GradientSoftness"), TEXT("Hair"), TEXT("Colour"), LOCTEXT("KGradSoft", "Fade softness"), LOCTEXT("KGradSoftT", "A hard dip-dye line or a soft blend."), 0.f, 1.f, 0.5f),
			Scalar(TEXT("Hair.HighlightAmount"), TEXT("Hair"), TEXT("Colour"), LOCTEXT("KHigh", "Highlights"), LOCTEXT("KHighT", "How many painted highlight streaks."), 0.f, 1.f, 0.f),
			Scalar(TEXT("Hair.Shine"), TEXT("Hair"), TEXT("Colour"), LOCTEXT("KShine", "Shine"), LOCTEXT("KShineT", "Painted shine band, matte to glossy storybook ribbon."), 0.f, 1.f, 0.5f),
			Scalar(TEXT("Brows.MatchHair"), TEXT("Hair"), TEXT("Brows"), LOCTEXT("KBrowMatch", "Match hair"), LOCTEXT("KBrowMatchT", "Brows follow your hair colour."), 0.f, 1.f, 1.f, true),
			Scalar(TEXT("Brows.Density"), TEXT("Hair"), TEXT("Brows"), LOCTEXT("KBrowDens", "Density"), LOCTEXT("KBrowDensT", "Sparse or dense brows."), 0.f, 1.f, 0.7f),
			Scalar(TEXT("FacialHair.MatchHair"), TEXT("Hair"), TEXT("FacialHair"), LOCTEXT("KFHMatch", "Match hair"), LOCTEXT("KFHMatchT", "Facial hair follows your hair colour."), 0.f, 1.f, 1.f, true),
			Scalar(TEXT("FacialHair.Length"), TEXT("Hair"), TEXT("FacialHair"), LOCTEXT("KFHLen", "Length"), LOCTEXT("KFHLenT", "Shorter or longer."), -1.f, 1.f, 0.f),
			Scalar(TEXT("Eyes.Heterochromia"), TEXT("Eyes"), TEXT("Colour"), LOCTEXT("KHetero", "Different eye colours"), LOCTEXT("KHeteroT", "Pick a separate colour for each eye."), 0.f, 1.f, 0.f, true),
			Scalar(TEXT("Freckles.Density"), TEXT("Skin"), TEXT("Details"), LOCTEXT("KFreckDens", "Freckle density"), LOCTEXT("KFreckDensT", "How many freckles in the chosen set."), 0.f, 1.f, 0.5f),
			Scalar(TEXT("Freckles.Opacity"), TEXT("Skin"), TEXT("Details"), LOCTEXT("KFreckOp", "Freckle strength"), LOCTEXT("KFreckOpT", "How strongly the freckles read."), 0.f, 1.f, 0.6f),
			Scalar(TEXT("Moles.Opacity"), TEXT("Skin"), TEXT("Details"), LOCTEXT("KMoles", "Mole strength"), LOCTEXT("KMolesT", "How strongly moles read."), 0.f, 1.f, 0.8f),
			Scalar(TEXT("Scars.Opacity"), TEXT("Skin"), TEXT("Details"), LOCTEXT("KScars", "Scar strength"), LOCTEXT("KScarsT", "Scars are healed and soft."), 0.f, 0.8f, 0.6f),
			Scalar(TEXT("Markings.Opacity"), TEXT("Skin"), TEXT("Markings"), LOCTEXT("KMark", "Marking strength"), LOCTEXT("KMarkT", "How strongly the markings read."), 0.f, 1.f, 0.8f),
			Scalar(TEXT("Markings.Glow"), TEXT("Skin"), TEXT("Markings"), LOCTEXT("KMarkGlow", "Sigil glow"), LOCTEXT("KMarkGlowT", "Moon sigils glow at night and in mist."), 0.f, 1.f, 0.5f, false, { TEXT("MoonlitElf") }),
			Scalar(TEXT("Markings.Shimmer"), TEXT("Skin"), TEXT("Markings"), LOCTEXT("KMarkShim", "Scale shimmer"), LOCTEXT("KMarkShimT", "Scale patches shimmer, more when wet."), 0.f, 1.f, 0.5f, false, { TEXT("Deepkin") }),
			Scalar(TEXT("Makeup.Eyeshadow.Opacity"), TEXT("Makeup"), TEXT("Eyes"), LOCTEXT("KShadow", "Eyeshadow strength"), LOCTEXT("KShadowT", "How strong the eyeshadow is."), 0.f, 1.f, 0.6f),
			Scalar(TEXT("Makeup.Eyeliner.Opacity"), TEXT("Makeup"), TEXT("Eyes"), LOCTEXT("KLiner", "Eyeliner strength"), LOCTEXT("KLinerT", "How strong the eyeliner is."), 0.f, 1.f, 0.8f),
			Scalar(TEXT("Makeup.Lips.Opacity"), TEXT("Makeup"), TEXT("Lips"), LOCTEXT("KLips", "Lip colour strength"), LOCTEXT("KLipsT", "How strong the lip colour is."), 0.f, 1.f, 0.5f),
			Scalar(TEXT("Makeup.Lips.Gloss"), TEXT("Makeup"), TEXT("Lips"), LOCTEXT("KGloss", "Gloss"), LOCTEXT("KGlossT", "Matte or glossy painted highlight."), 0.f, 1.f, 0.2f),
			Scalar(TEXT("Makeup.Blush.Opacity"), TEXT("Makeup"), TEXT("Cheeks"), LOCTEXT("KBlush", "Blush strength"), LOCTEXT("KBlushT", "How strong the blush is."), 0.f, 1.f, 0.5f),
			Scalar(TEXT("Makeup.FacePaint.Opacity"), TEXT("Makeup"), TEXT("FacePaint"), LOCTEXT("KPaint", "Paint strength"), LOCTEXT("KPaintT", "How strong the face paint is."), 0.f, 1.f, 0.9f),
			Scalar(TEXT("Outfit.Wear"), TEXT("Outfit"), TEXT("Outfit"), LOCTEXT("KWear", "Wear"), LOCTEXT("KWearT", "Crisp and new, or well-travelled with patches and faded hems."), 0.f, 1.f, 0.3f),
		};
		return List;
	}

	const FLyrisCreatorScalarInfo* FindScalar(FName Key)
	{
		return Scalars().FindByPredicate([Key](const FLyrisCreatorScalarInfo& S) { return S.Key == Key; });
	}

	FName ExpressionPreviewId(FName ExpressionPartOrId)
	{
		// Catalog part ids are "<Slot>.<Name>" ("Expression.Calm"); the stage wants just "Calm".
		const FString Id = ExpressionPartOrId.ToString();
		int32 Dot = INDEX_NONE;
		if (Id.FindChar(TEXT('.'), Dot))
		{
			return FName(*Id.Mid(Dot + 1));
		}
		return ExpressionPartOrId;
	}

	const TArray<TPair<FName, FText>>& Expressions()
	{
		// Preview only: cycling these never changes the saved resting expression (the Expression part).
		static const TArray<TPair<FName, FText>> List = {
			Opt(TEXT("Calm"), LOCTEXT("ExCalm", "Calm")), Opt(TEXT("Bright"), LOCTEXT("ExBright", "Bright smile")),
			Opt(TEXT("Laugh"), LOCTEXT("ExLaugh", "Laugh")), Opt(TEXT("Wry"), LOCTEXT("ExWry", "Wry")),
			Opt(TEXT("Shy"), LOCTEXT("ExShy", "Shy")), Opt(TEXT("Surprised"), LOCTEXT("ExSurprised", "Surprised")),
			Opt(TEXT("Sleepy"), LOCTEXT("ExSleepy", "Sleepy")), Opt(TEXT("Determined"), LOCTEXT("ExDetermined", "Determined")),
		};
		return List;
	}

	const TArray<TPair<FName, FText>>& Poses()
	{
		static const TArray<TPair<FName, FText>> List = {
			Opt(TEXT("Idle"), LOCTEXT("PoIdle", "Idle")), Opt(TEXT("Wave"), LOCTEXT("PoWave", "Wave")),
			Opt(TEXT("HoldLantern"), LOCTEXT("PoLantern", "Hold lantern")), Opt(TEXT("Sit"), LOCTEXT("PoSit", "Sit on a crate")),
			Opt(TEXT("LeanRail"), LOCTEXT("PoLean", "Lean on the rail")), Opt(TEXT("Windy"), LOCTEXT("PoWindy", "Windy")),
			Opt(TEXT("Walk"), LOCTEXT("PoWalk", "Walk")),
		};
		return List;
	}

	const FLyrisColorChannelDef& FallbackLanternGlass()
	{
		static const FLyrisColorChannelDef Channel = []()
		{
			FLyrisColorChannelDef C;
			C.Id = Channel_LanternGlass;
			C.Category = Category_Lantern;
			C.DisplayName = LOCTEXT("LanternGlass", "Lantern glass");
			C.MaxHueShift = 0.08f;
			C.MaxValueShift = 0.15f;
			C.MaterialParam = TEXT("LanternGlass");
			auto Add = [&C](const FText& Name, const TCHAR* Hex)
			{
				FLyrisSwatch S;
				S.DisplayName = Name;
				S.Color = FLinearColor(FColor::FromHex(FString(Hex)));
				C.Swatches.Add(S);
			};
			Add(LOCTEXT("G1", "Amber"), TEXT("E3AE45"));
			Add(LOCTEXT("G2", "Warm white"), TEXT("F7EEDC"));
			Add(LOCTEXT("G3", "Moonglass"), TEXT("7AC0E6"));
			Add(LOCTEXT("G4", "Shallows"), TEXT("7FD0D6"));
			Add(LOCTEXT("G5", "Rose"), TEXT("D88FA6"));
			Add(LOCTEXT("G6", "Ember"), TEXT("C8643A"));
			Add(LOCTEXT("G7", "Violet"), TEXT("9A82D0"));
			Add(LOCTEXT("G8", "Leaf-gold"), TEXT("C9D86A"));
			Add(LOCTEXT("G9", "Pearl"), TEXT("E8E6DC"));
			return C;
		}();
		return Channel;
	}

	FText ValidateName(const FString& InName)
	{
		const FString Name = InName.TrimStartAndEnd();
		if (Name.Len() < 2)
		{
			return LOCTEXT("NameShort", "The harbourmaster needs at least two letters.");
		}
		if (Name.Len() > 20)
		{
			return LOCTEXT("NameLong", "That won't fit on one line of the ledger (20 letters at most).");
		}
		if (!FChar::IsAlpha(Name[0]))
		{
			return LOCTEXT("NameStart", "A name starts with a letter.");
		}
		TCHAR Prev = 0;
		for (const TCHAR Ch : Name)
		{
			const bool bAllowed = FChar::IsAlpha(Ch) || Ch == TEXT(' ') || Ch == TEXT('\'') || Ch == TEXT('-');
			if (!bAllowed)
			{
				return LOCTEXT("NameChars", "Only letters, spaces, apostrophes and hyphens, please.");
			}
			const bool bMark = Ch == TEXT(' ') || Ch == TEXT('\'') || Ch == TEXT('-');
			const bool bPrevMark = Prev == TEXT(' ') || Prev == TEXT('\'') || Prev == TEXT('-');
			if (bMark && bPrevMark)
			{
				return LOCTEXT("NameDouble", "No two spaces or marks in a row.");
			}
			Prev = Ch;
		}
		// TODO(UI): a gentle word filter and a check against names already in the ledger (online).
		return FText::GetEmpty();
	}
}

#undef LOCTEXT_NAMESPACE
