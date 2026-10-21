// Lyris UI: the Breath ring (T33). See SLyrisBreathRing.h.

#include "UI/SLyrisBreathRing.h"

#include "Framework/Application/SlateApplication.h"
#include "Layout/Geometry.h"
#include "Rendering/DrawElements.h"
#include "Rendering/RenderingCommon.h"
#include "Rendering/SlateRenderer.h"
#include "Brushes/SlateColorBrush.h"
#include "Styling/WidgetStyle.h"

/**
 * Breath ring colours, approved by the user in the reference page (wayfarers_breath.html).
 * These are UI colours, not world art, so they live here rather than in PALETTE (lyris_build_world.py).
 * Every colour the ring draws comes from this block; alpha is set per use.
 */
namespace LyrisBreathRingDetail
{
// ---- Colours ----
	static const FColor Gold(242, 193, 78);         // Breath above 50%
	static const FColor Amber(240, 146, 62);        // around 50%
	static const FColor Ember(239, 107, 79);        // 20% and below, low glow, unaffordable preview
	static const FColor WindedSlate(138, 147, 184);       // Winded
	static const FColor GhostCream(255, 242, 207);  // drain trail (75%)
	static const FColor Tea(127, 224, 208);         // tea halo (bonus Breath)
	static const FColor Backing(8, 10, 22);         // dark ring behind the arc (72%), notches (85%)
	static const FColor Groove(255, 240, 210);      // faint track (10%), vial rim (35%)
	static const FColor ArcHighlight(255, 255, 240);// thin bright line on the arc (45%)
	static const FColor VialGlass(12, 16, 34);      // vial background (85%)
	static const FColor WaterTop(159, 208, 240);    // #9fd0f0
	static const FColor WaterBottom(59, 111, 174);  // #3b6fae
	static const FColor WindedWaterTop(138, 147, 184);   // #8a93b8
	static const FColor WindedWaterBottom(74, 83, 120);  // #4a5378
	static const FColor Crack(240, 240, 255);       // vial cracks while Winded (80%)
	static const FColor SparkCore(255, 248, 224);   // #fff8e0, arc-head spark
	static const FColor PreviewOk(255, 255, 255);   // leap-cost outline (90%)

// ---- Tuning ----
	// Geometry is authored in the reference page's units (main radius 17) and scaled to RingRadius.
	static constexpr float RefRadius = 17.f;
	static constexpr float RefThickness = 5.f;
	static constexpr float QuarterTurn = 1.57079633f;
	static constexpr float FullTurn = 6.28318531f;
	static constexpr float StartAngle = -QuarterTurn; // 12 o'clock, clockwise on screen (Slate Y is down)

	static constexpr float GhostWait = 0.45f;     // s after the last spend before the trail catches up
	static constexpr float GhostSpeed = 70.f;     // Breath per second
	static constexpr float ShowAfterSpend = 1.2f; // s the ring stays after any spend
	static constexpr float HideAfterFull = 1.2f;  // s the ring lingers once full
	static constexpr float WindedShake = 0.35f;   // s
	static constexpr float LowGlowBelow = 0.25f;  // ratio
	static constexpr float TeaFullBonus = 50.f;   // halo is a full circle at this much bonus
	static constexpr float SparkWindow = 0.08f;   // s after a spend the arc head glints
	static constexpr float SparkRate = 30.f;      // drain sparks per second while spending
	static constexpr float HeadFollowRate = 22.f; // 1/s, smooths the projected head position

// ---- Paint helpers ----

	FColor WithAlpha(FColor C, float A)
	{
		C.A = (uint8)FMath::Clamp(FMath::RoundToInt(A * 255.f), 0, 255);
		return C;
	}

	FColor MixColor(const FColor& A, const FColor& B, float T)
	{
		T = FMath::Clamp(T, 0.f, 1.f);
		return FColor(
			(uint8)FMath::RoundToInt(A.R + (B.R - A.R) * T),
			(uint8)FMath::RoundToInt(A.G + (B.G - A.G) * T),
			(uint8)FMath::RoundToInt(A.B + (B.B - A.B) * T),
			(uint8)FMath::RoundToInt(A.A + (B.A - A.A) * T));
	}

	/** colorFor() from the reference: gold -> amber below 50%, amber -> ember below 20%, slate while Winded. */
	FColor RingColorFor(float Ratio, bool bWinded)
	{
		if (bWinded)
		{
			return WindedSlate;
		}
		if (Ratio > 0.5f)
		{
			return MixColor(Amber, Gold, (Ratio - 0.5f) / 0.5f);
		}
		return MixColor(Ember, Amber, FMath::Max(0.f, (Ratio - 0.2f) / 0.3f));
	}

	FVector2f Polar(float Radius, float Angle)
	{
		return FVector2f(FMath::Cos(Angle) * Radius, FMath::Sin(Angle) * Radius);
	}

	/**
	 * Builds one antialiased triangle mesh. Shapes are given in "ring units" (the reference page's
	 * pixels) around Centre and mapped to local Slate units by Scale. Every edge gets a feather about
	 * one physical pixel wide that fades to transparent, which is what makes the ring look smooth.
	 */
	struct FBreathMesh
	{
		FBreathMesh(const FSlateRenderTransform& InTransform, TArray<FSlateVertex>& InVerts, TArray<SlateIndex>& InIndices)
			: Transform(InTransform), Verts(InVerts), Indices(InIndices)
		{}

		const FSlateRenderTransform& Transform;
		TArray<FSlateVertex>& Verts;
		TArray<SlateIndex>& Indices;

		FVector2f Centre = FVector2f::ZeroVector;
		float Scale = 1.f;      // local units per ring unit
		float PixelScale = 1.f; // physical pixels per local unit
		float Opacity = 1.f;

		void SetFrame(const FVector2f& InCentre, float InScale, float InPixelScale, float InOpacity)
		{
			Centre = InCentre;
			Scale = FMath::Max(InScale, KINDA_SMALL_NUMBER);
			PixelScale = FMath::Max(InPixelScale, KINDA_SMALL_NUMBER);
			Opacity = InOpacity;
		}

		/** One physical pixel, in ring units. */
		float Feather() const { return 1.f / (Scale * PixelScale); }
		float PixelsPerUnit() const { return Scale * PixelScale; }

		int32 AddVert(const FVector2f& RingPos, const FColor& Color)
		{
			const FColor C = WithAlpha(Color, (Color.A / 255.f) * Opacity);
			const int32 Index = Verts.Num();
			Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(
				Transform, Centre + RingPos * Scale, FVector2f(0.5f, 0.5f), C, C));
			return Index;
		}

		void AddTri(int32 A, int32 B, int32 C)
		{
			Indices.Add((SlateIndex)A);
			Indices.Add((SlateIndex)B);
			Indices.Add((SlateIndex)C);
		}

		void AddQuad(int32 A, int32 B, int32 C, int32 D)
		{
			AddTri(A, B, C);
			AddTri(A, C, D);
		}

		int32 SegmentsFor(float Radius, float Sweep) const
		{
			const float ArcPixels = FMath::Abs(Sweep) * Radius * PixelsPerUnit();
			return FMath::Clamp(FMath::CeilToInt(ArcPixels / 2.5f), 2, 256);
		}

		/**
		 * Concentric rings around Origin between angles A0 and A1. Radii[k] carries Colors[k];
		 * consecutive rings are joined with quads, so colour and alpha blend between them.
		 */
		void AddRadialStrip(const FVector2f& Origin, const float* Radii, const FColor* Colors, int32 NumRings, float A0, float A1)
		{
			if (NumRings < 2 || FMath::IsNearlyEqual(A0, A1))
			{
				return;
			}
			float MaxRadius = 0.f;
			for (int32 K = 0; K < NumRings; ++K)
			{
				MaxRadius = FMath::Max(MaxRadius, Radii[K]);
			}
			const int32 Segments = SegmentsFor(MaxRadius, A1 - A0);
			const int32 First = Verts.Num();
			for (int32 S = 0; S <= Segments; ++S)
			{
				const float Angle = FMath::Lerp(A0, A1, (float)S / (float)Segments);
				const FVector2f Dir(FMath::Cos(Angle), FMath::Sin(Angle));
				for (int32 K = 0; K < NumRings; ++K)
				{
					AddVert(Origin + Dir * Radii[K], Colors[K]);
				}
			}
			for (int32 S = 0; S < Segments; ++S)
			{
				const int32 Row0 = First + S * NumRings;
				const int32 Row1 = Row0 + NumRings;
				for (int32 K = 0; K + 1 < NumRings; ++K)
				{
					AddQuad(Row0 + K, Row1 + K, Row1 + K + 1, Row0 + K + 1);
				}
			}
		}

		/** Like canvas arc() + stroke(): a band of Width centred on Radius. */
		void AddArc(float Radius, float Width, float A0, float A1, const FColor& Color, bool bRoundCaps = false, float ExtraFeather = 0.f)
		{
			if (A1 - A0 <= 0.f)
			{
				return;
			}
			const float F = Feather() + ExtraFeather;
			const float CoreHalf = FMath::Max(0.f, Width * 0.5f - F * 0.5f);
			const float EdgeHalf = Width * 0.5f + F * 0.5f;
			// Lines thinner than the feather fade instead of vanishing.
			const float Coverage = FMath::Min(1.f, Width / FMath::Max(F, KINDA_SMALL_NUMBER));
			const FColor Solid = WithAlpha(Color, (Color.A / 255.f) * Coverage);
			const FColor Clear = WithAlpha(Color, 0.f);
			const float Radii[4] = { FMath::Max(0.f, Radius - EdgeHalf), Radius - CoreHalf, Radius + CoreHalf, Radius + EdgeHalf };
			const FColor Colors[4] = { Clear, Solid, Solid, Clear };
			AddRadialStrip(FVector2f::ZeroVector, Radii, Colors, 4, A0, A1);

			if (bRoundCaps)
			{
				// Half discs facing away from the arc, so translucent arcs do not double up.
				const float CapRadius = Width * 0.5f;
				AddCap(Polar(Radius, A0), A0 - QuarterTurn, CapRadius, Solid, F);
				AddCap(Polar(Radius, A1), A1 + QuarterTurn, CapRadius, Solid, F);
			}
		}

		void AddCap(const FVector2f& At, float FacingAngle, float Radius, const FColor& Color, float F)
		{
			const float Radii[3] = { 0.f, FMath::Max(0.f, Radius - F * 0.5f), Radius + F * 0.5f };
			const FColor Colors[3] = { Color, Color, WithAlpha(Color, 0.f) };
			AddRadialStrip(At, Radii, Colors, 3, FacingAngle - QuarterTurn, FacingAngle + QuarterTurn);
		}

		void AddDisc(const FVector2f& At, float Radius, const FColor& Color)
		{
			const float F = Feather();
			const float Radii[3] = { 0.f, FMath::Max(0.f, Radius - F * 0.5f), Radius + F * 0.5f };
			const FColor Colors[3] = { Color, Color, WithAlpha(Color, 0.f) };
			AddRadialStrip(At, Radii, Colors, 3, 0.f, FullTurn);
		}

		/** Soft round glow: solid to InnerRadius, fading to clear at OuterRadius (canvas radial gradient). */
		void AddGlow(const FVector2f& At, float InnerRadius, float OuterRadius, const FColor& Color)
		{
			const float Radii[3] = { 0.f, InnerRadius, OuterRadius };
			const FColor Colors[3] = { Color, Color, WithAlpha(Color, 0.f) };
			AddRadialStrip(At, Radii, Colors, 3, 0.f, FullTurn);
		}

		/** Rotated ellipse with a feathered rim. */
		void AddEllipse(const FVector2f& At, float RadiusX, float RadiusY, float Rotation, const FColor& Color)
		{
			const float F = Feather();
			const int32 Segments = SegmentsFor(FMath::Max(RadiusX, RadiusY), FullTurn);
			const float CosR = FMath::Cos(Rotation);
			const float SinR = FMath::Sin(Rotation);
			auto Point = [&](float Angle, float Grow)
			{
				const FVector2f P(FMath::Cos(Angle) * (RadiusX + Grow), FMath::Sin(Angle) * (RadiusY + Grow));
				return At + FVector2f(P.X * CosR - P.Y * SinR, P.X * SinR + P.Y * CosR);
			};
			const int32 Hub = AddVert(At, Color);
			const int32 First = Verts.Num();
			for (int32 S = 0; S <= Segments; ++S)
			{
				const float Angle = FullTurn * (float)S / (float)Segments;
				AddVert(Point(Angle, -F * 0.5f), Color);
				AddVert(Point(Angle, F * 0.5f), WithAlpha(Color, 0.f));
			}
			for (int32 S = 0; S < Segments; ++S)
			{
				const int32 In0 = First + S * 2;
				const int32 In1 = In0 + 2;
				AddTri(Hub, In0, In1);
				AddQuad(In0, In1, In1 + 1, In0 + 1);
			}
		}

		/** Straight line with butt ends and feathered sides. */
		void AddLine(const FVector2f& P0, const FVector2f& P1, float Width, const FColor& Color)
		{
			const FVector2f Along = P1 - P0;
			const float Length = Along.Size();
			if (Length <= KINDA_SMALL_NUMBER)
			{
				return;
			}
			const FVector2f N = FVector2f(-Along.Y, Along.X) / Length;
			const float F = Feather();
			const float CoreHalf = FMath::Max(0.f, Width * 0.5f - F * 0.5f);
			const float EdgeHalf = Width * 0.5f + F * 0.5f;
			const float Coverage = FMath::Min(1.f, Width / FMath::Max(F, KINDA_SMALL_NUMBER));
			const FColor Solid = WithAlpha(Color, (Color.A / 255.f) * Coverage);
			const FColor Clear = WithAlpha(Color, 0.f);
			const float Offsets[4] = { -EdgeHalf, -CoreHalf, CoreHalf, EdgeHalf };
			const FColor Colors[4] = { Clear, Solid, Solid, Clear };
			const int32 First = Verts.Num();
			for (int32 K = 0; K < 4; ++K)
			{
				AddVert(P0 + N * Offsets[K], Colors[K]);
				AddVert(P1 + N * Offsets[K], Colors[K]);
			}
			for (int32 K = 0; K < 3; ++K)
			{
				const int32 A = First + K * 2;
				AddQuad(A, A + 1, A + 3, A + 2);
			}
		}

		/** Polyline through Points (open), joined segment by segment. */
		void AddPolyline(const TArray<FVector2f>& Points, float Width, const FColor& Color)
		{
			for (int32 K = 0; K + 1 < Points.Num(); ++K)
			{
				AddLine(Points[K], Points[K + 1], Width, Color);
			}
		}
	};
} // namespace LyrisBreathRingDetail

void SLyrisBreathRing::Construct(const FArguments& InArgs)
{
	RingRadius = FMath::Max(4.f, InArgs._RingRadius);
	bReducedMotion = InArgs._ReducedMotion;
	SetVisibility(EVisibility::HitTestInvisible);
	SetCanTick(false);
	ResetState();
}

void SLyrisBreathRing::ResetState()
{
	State = FLyrisBreathSample();
	bHasSample = false;
	bHeadEverSet = false;
	bHeadOnScreen = false;
	Ghost = State.Current;
	Alpha = 0.f;
	Shake = 0.f;
	ShakeOffset = FVector2f::ZeroVector;
	TimeSinceFull = 100.f;
	bWasFull = true;
	RipplePulse = 0.f;
	TimeSinceSpentEvent = 100.f;
	Sparks.Reset();
}

void SLyrisBreathRing::SetHeadAnchor(const FVector2D& InHeadLocal, bool bOnScreen)
{
	HeadTarget = FVector2f((float)InHeadLocal.X, (float)InHeadLocal.Y);
	bHeadOnScreen = bOnScreen;
	if (bOnScreen && !bHeadEverSet)
	{
		HeadSmoothed = HeadTarget;
		bHeadEverSet = true;
	}
}

void SLyrisBreathRing::NotifySpent(float Amount)
{
	using namespace LyrisBreathRingDetail;

	TimeSinceSpentEvent = 0.f;
	// A leap or wall kick is a big single spend: a small gold burst, like the reference.
	if (Amount >= 10.f && State.Bonus <= 0.f)
	{
		Burst(6, Gold);
	}
}

FVector2f SLyrisBreathRing::LastLocalSize() const
{
	const FVector2D Size = GetPaintSpaceGeometry().GetLocalSize();
	return FVector2f((float)Size.X, (float)Size.Y);
}

FVector2f SLyrisBreathRing::RingCentreLocal(const FVector2f& Size) const
{
	using namespace LyrisBreathRingDetail;

	// Reference: the ring sits ~29.5 px right of and ~12 px above the head centre, at radius 17.
	const float K = RingRadius / RefRadius;
	FVector2f Centre = HeadSmoothed + FVector2f(29.5f * K, -12.f * K);

	// Keep the whole ring, halo included, inside the viewport.
	const float Margin = RingRadius * 1.7f;
	if (Size.X > Margin * 2.f && Size.Y > Margin * 2.f)
	{
		Centre.X = FMath::Clamp(Centre.X, Margin, Size.X - Margin);
		Centre.Y = FMath::Clamp(Centre.Y, Margin, Size.Y - Margin);
	}
	return Centre;
}

FVector2f SLyrisBreathRing::ArcHead(float Ratio) const
{
	using namespace LyrisBreathRingDetail;

	return Polar(RefRadius, StartAngle + FullTurn * Ratio);
}

void SLyrisBreathRing::Burst(int32 Count, const FColor& Color)
{
	using namespace LyrisBreathRingDetail;

	if (bReducedMotion)
	{
		return;
	}
	const float K = RingRadius / RefRadius;
	const FVector2f Centre = RingCentreLocal(LastLocalSize());
	for (int32 N = 0; N < Count; ++N)
	{
		const float Angle = FMath::FRandRange(0.f, FullTurn);
		const float Speed = FMath::FRandRange(40.f, 120.f);
		const FVector2f Dir(FMath::Cos(Angle), FMath::Sin(Angle));
		FSpark& Spark = Sparks.AddDefaulted_GetRef();
		Spark.Pos = Centre + Dir * (18.f * K);
		Spark.Vel = Dir * (Speed * K);
		Spark.Life = 0.7f;
		Spark.Color = Color;
	}
}

void SLyrisBreathRing::Advance(float DeltaSeconds, const FLyrisBreathSample& InSample)
{
	using namespace LyrisBreathRingDetail;

	const float Dt = FMath::Clamp(DeltaSeconds, 0.f, 1.f / 15.f);
	Time += Dt;
	TimeSinceSpentEvent += Dt;

	FLyrisBreathSample Sample = InSample;
	Sample.Max = FMath::Max(1.f, Sample.Max);
	Sample.Current = FMath::Clamp(Sample.Current, 0.f, Sample.Max);
	Sample.Bonus = FMath::Max(0.f, Sample.Bonus);

	if (!bHasSample)
	{
		Ghost = Sample.Current;
		bWasFull = Sample.Current >= Sample.Max - 0.01f;
	}
	else
	{
		if (Sample.bWinded && !State.bWinded)
		{
			Shake = WindedShake;
		}
		if (!Sample.bWinded && State.bWinded)
		{
			Burst(10, Gold);
		}
		if (Sample.Bonus > State.Bonus + 1.f)
		{
			Burst(14, Tea);
		}
	}

	const bool bFull = Sample.Current >= Sample.Max - 0.01f;
	if (bFull && !bWasFull && bHasSample)
	{
		RipplePulse = 1.f;
	}
	TimeSinceFull = bFull ? TimeSinceFull + Dt : 0.f;
	if (bFull && !bWasFull)
	{
		TimeSinceFull = 0.f;
	}
	bWasFull = bFull;

	State = Sample;
	bHasSample = true;

	// Ghost / drain trail (reference step()).
	if (Ghost < State.Current)
	{
		Ghost = State.Current;
	}
	else if (State.TimeSinceLastSpend > GhostWait)
	{
		Ghost = FMath::Max(State.Current, Ghost - GhostSpeed * Dt);
	}

	// Visibility.
	const bool bShow = bHeadOnScreen && (!bFull
		|| State.Bonus > 0.f
		|| State.bWinded
		|| State.PreviewCost > 0.f
		|| State.TimeSinceLastSpend < ShowAfterSpend
		|| TimeSinceFull < HideAfterFull);
	Alpha += ((bShow ? 1.f : 0.f) - Alpha) * FMath::Min(1.f, Dt * (bShow ? 10.f : 3.f));
	if (Alpha < 0.002f && !bShow)
	{
		Alpha = 0.f;
	}

	// Follow the head smoothly so animation jitter in the head bone does not shake the ring.
	if (bHeadOnScreen)
	{
		const FVector2f Delta = HeadTarget - HeadSmoothed;
		if (!bHeadEverSet || Delta.SizeSquared() > FMath::Square(RingRadius * 12.f))
		{
			HeadSmoothed = HeadTarget; // teleport or camera cut
			bHeadEverSet = true;
		}
		else
		{
			HeadSmoothed += Delta * FMath::Min(1.f, Dt * HeadFollowRate);
		}
	}

	// Winded shake.
	Shake = FMath::Max(0.f, Shake - Dt);
	if (Shake > 0.f && !bReducedMotion)
	{
		const float Amp = 2.f * Shake / WindedShake;
		ShakeOffset = FVector2f(FMath::FRandRange(-Amp, Amp), FMath::FRandRange(-Amp, Amp));
	}
	else
	{
		ShakeOffset = FVector2f::ZeroVector;
	}

	RipplePulse = FMath::Max(0.f, RipplePulse - Dt / 0.6f);

	// Sparks shed from the arc head while Breath is draining.
	const float Ratio = State.Current / State.Max;
	if (!bReducedMotion && Alpha > 0.2f && State.TimeSinceLastSpend < 0.05f && Ratio > 0.f)
	{
		if (FMath::FRand() < SparkRate * Dt)
		{
			const float K = RingRadius / RefRadius;
			const float Scale = K * (0.7f + 0.3f * Alpha);
			FSpark& Spark = Sparks.AddDefaulted_GetRef();
			Spark.Pos = RingCentreLocal(LastLocalSize()) + ArcHead(Ratio) * Scale;
			Spark.Vel = FVector2f(FMath::FRandRange(-20.f, 20.f), -20.f - FMath::FRandRange(0.f, 40.f)) * K;
			Spark.Life = 0.6f;
			Spark.Color = RingColorFor(Ratio, State.bWinded);
		}
	}
	const float Gravity = 60.f * (RingRadius / RefRadius);
	for (FSpark& Spark : Sparks)
	{
		Spark.Pos += Spark.Vel * Dt;
		Spark.Vel.Y += Gravity * Dt;
		Spark.Life -= Dt;
	}
	Sparks.RemoveAll([](const FSpark& Spark) { return Spark.Life <= 0.f; });
}

FVector2D SLyrisBreathRing::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	// Fills the viewport overlay slot; it has no size of its own.
	return FVector2D(RingRadius * 3.4f, RingRadius * 3.4f);
}

int32 SLyrisBreathRing::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	using namespace LyrisBreathRingDetail;

	const float WidgetOpacity = InWidgetStyle.GetColorAndOpacityTint().A;
	if (!bHasSample || (Alpha < 0.01f && Sparks.Num() == 0) || WidgetOpacity <= 0.f)
	{
		return LayerId;
	}

	const FSlateRenderTransform& PaintTransform = AllottedGeometry.GetAccumulatedRenderTransform();
	const float PixelScale = AllottedGeometry.Scale;

	TArray<FSlateVertex> Verts;
	TArray<SlateIndex> Indices;
	Verts.Reserve(4096);
	Indices.Reserve(8192);
	FBreathMesh Mesh(PaintTransform, Verts, Indices);

	const float MaxBreath = State.Max;
	const float Ratio = State.Current / MaxBreath;
	const bool bWinded = State.bWinded;
	const FColor ArcColor = RingColorFor(Ratio, bWinded);
	const float Motion = bReducedMotion ? 0.f : 1.f;

	const float R0 = RefRadius;
	const float TH = RefThickness;
	const float A0 = StartAngle;

	if (Alpha >= 0.01f)
	{
		const float K = RingRadius / RefRadius;
		const float PopScale = 0.7f + 0.3f * Alpha;
		const FVector2D PaintSize = AllottedGeometry.GetLocalSize();
		const FVector2f Centre = RingCentreLocal(FVector2f((float)PaintSize.X, (float)PaintSize.Y)) + ShakeOffset * K;
		Mesh.SetFrame(Centre, K * PopScale, PixelScale, Alpha * WidgetOpacity);

		// Low-Breath glow: a slow breathing ember halo instead of a harsh flash.
		if (!bWinded && Ratio < LowGlowBelow)
		{
			const float Pulse = bReducedMotion ? 0.5f : 0.5f + 0.5f * FMath::Sin(Time * 5.f);
			Mesh.AddGlow(FVector2f::ZeroVector, 8.f, 34.f, WithAlpha(Ember, 0.35f * Pulse));
		}

		// Backing ring and faint groove.
		Mesh.AddArc(R0, TH + 4.f, 0.f, FullTurn, WithAlpha(Backing, 0.72f));
		Mesh.AddArc(R0, TH, 0.f, FullTurn, WithAlpha(Groove, 0.10f));

		// Centre vial.
		const float Rv = R0 - TH - 1.f;
		Mesh.AddDisc(FVector2f::ZeroVector, Rv, WithAlpha(VialGlass, 0.85f));
		{
			const FColor Top = bWinded ? WindedWaterTop : WaterTop;
			const FColor Bottom = bWinded ? WindedWaterBottom : WaterBottom;
			auto WaterColorAt = [&](float Y) { return MixColor(Top, Bottom, (Y + Rv) / (2.f * Rv)); };

			const float Level = Rv - 2.f * Rv * Ratio;
			const float F = Mesh.Feather();
			const int32 Columns = FMath::Clamp(FMath::CeilToInt(2.f * Rv * Mesh.PixelsPerUnit() / 1.5f), 8, 96);
			int32 PrevBase = INDEX_NONE;
			for (int32 Col = 0; Col <= Columns; ++Col)
			{
				// Columns stop just inside the rim; the rim stroke covers the seam.
				const float X = FMath::Lerp(-Rv, Rv, (float)Col / (float)Columns);
				const float Half = FMath::Sqrt(FMath::Max(0.f, Rv * Rv - X * X));
				const float Wave = Level + FMath::Sin(X * 0.6f + Time * 5.f * Motion) * 1.2f;
				const float TopY = FMath::Clamp(Wave, -Half, Half);
				const float FeatherY = FMath::Max(-Half, TopY - F);
				const int32 Base = Verts.Num();
				Mesh.AddVert(FVector2f(X, FeatherY), WithAlpha(WaterColorAt(FeatherY), 0.f));
				Mesh.AddVert(FVector2f(X, TopY), WaterColorAt(TopY));
				Mesh.AddVert(FVector2f(X, Half), WaterColorAt(Half));
				if (PrevBase != INDEX_NONE)
				{
					for (int32 Row = 0; Row < 2; ++Row)
					{
						const int32 P = PrevBase + Row;
						const int32 C = Base + Row;
						Mesh.AddQuad(P, C, C + 1, P + 1);
					}
				}
				PrevBase = Base;
			}

			// Glass glint.
			Mesh.AddEllipse(FVector2f(-4.f, -5.f), 2.2f, 4.f, -0.5f, WithAlpha(FColor::White, 0.35f));

			// Cracks while Winded.
			if (bWinded)
			{
				const FColor CrackColor = WithAlpha(Crack, 0.8f);
				const TArray<FVector2f> Crack1 = { FVector2f(-6.f, -8.f), FVector2f(-1.f, -2.f), FVector2f(-4.f, 2.f), FVector2f(2.f, 8.f) };
				const TArray<FVector2f> Crack2 = { FVector2f(-1.f, -2.f), FVector2f(5.f, -4.f) };
				Mesh.AddPolyline(Crack1, 1.f, CrackColor);
				Mesh.AddPolyline(Crack2, 1.f, CrackColor);
			}
		}
		Mesh.AddArc(Rv, 1.f, 0.f, FullTurn, WithAlpha(Groove, 0.35f));

		// Ghost / drain trail.
		if (Ghost > State.Current + 0.3f)
		{
			Mesh.AddArc(R0, TH, A0 + FullTurn * Ratio, A0 + FullTurn * FMath::Min(1.f, Ghost / MaxBreath), WithAlpha(GhostCream, 0.75f));
		}

		// Main arc with its bright highlight line.
		if (Ratio > 0.001f)
		{
			const float A1 = A0 + FullTurn * Ratio;
			Mesh.AddArc(R0, TH, A0, A1, ArcColor, true);
			Mesh.AddArc(R0 - 1.2f, 1.4f, A0, A1, WithAlpha(ArcHighlight, 0.45f), true);
		}

		// Quarter notches.
		for (int32 Q = 1; Q < 4; ++Q)
		{
			const float A = A0 + FullTurn * (float)Q / 4.f;
			Mesh.AddLine(Polar(R0 - TH * 0.5f - 1.f, A), Polar(R0 + TH * 0.5f + 1.f, A), 1.6f, WithAlpha(Backing, 0.85f));
		}

		// Recovery notch: where Winded clears.
		if (bWinded)
		{
			const float A = A0 + FullTurn * FMath::Clamp(State.WindedThreshold / MaxBreath, 0.f, 1.f);
			Mesh.AddDisc(Polar(R0 + TH * 0.5f + 3.f, A), 2.2f, Gold);
		}

		// Leap-cost preview: dashed outline over the slice the next action would take.
		if (State.PreviewCost > 0.f)
		{
			const float Cost = State.PreviewCost;
			const bool bOk = State.bCanAffordPreview;
			const float Have = State.Current;
			const float From = bOk ? FMath::Max(0.f, Have - FMath::Max(0.f, Cost - State.Bonus)) : 0.f;
			const float To = FMath::Min(MaxBreath, bOk ? Have : Cost);
			const FColor DashColor = bOk
				? WithAlpha(PreviewOk, 0.9f)
				: WithAlpha(Ember, bReducedMotion ? 0.9f : 0.6f + 0.4f * FMath::Sin(Time * 14.f));

			const float Rp = R0 + TH * 0.5f + 1.5f;
			const float StartA = A0 + FullTurn * From / MaxBreath;
			const float EndA = A0 + FullTurn * FMath::Max(To, From + 0.5f) / MaxBreath;
			const float DashA = 2.5f / Rp;
			const float GapA = 2.f / Rp;
			for (float A = StartA; A < EndA; A += DashA + GapA)
			{
				Mesh.AddArc(Rp, 1.2f, A, FMath::Min(A + DashA, EndA), DashColor);
			}
		}

		// Tea halo: bonus Breath as a thin glowing outer arc.
		if (State.Bonus > 0.01f)
		{
			const float Rt = R0 + TH + 3.f;
			const float A1 = A0 + FullTurn * FMath::Min(1.f, State.Bonus / TeaFullBonus);
			Mesh.AddArc(Rt, 2.4f, A0, A1, WithAlpha(Tea, 0.30f), true, 6.f); // soft glow (canvas shadowBlur 8)
			Mesh.AddArc(Rt, 2.4f, A0, A1, Tea, true);
		}

		// Spark at the arc head right after a spend.
		const float SinceSpend = FMath::Min(State.TimeSinceLastSpend, TimeSinceSpentEvent);
		if (SinceSpend < SparkWindow && Ratio > 0.f && State.Bonus <= 0.f)
		{
			const FVector2f Head = ArcHead(Ratio);
			Mesh.AddGlow(Head, 1.5f, 7.f, WithAlpha(ArcColor, 0.6f));
			Mesh.AddDisc(Head, 2.4f, SparkCore);
		}

		// Ripple when Breath tops back up: one soft gold ring that swells and fades.
		if (RipplePulse > 0.f && !bReducedMotion)
		{
			const float Grow = (1.f - RipplePulse);
			Mesh.AddArc(R0 + 1.f + Grow * 8.f, 2.f, 0.f, FullTurn, WithAlpha(Gold, 0.5f * RipplePulse), false, 1.5f);
		}
	}

	// Loose sparks, in widget space so they trail as the head moves.
	if (Sparks.Num() > 0)
	{
		const float K = RingRadius / RefRadius;
		Mesh.SetFrame(FVector2f::ZeroVector, 1.f, PixelScale, WidgetOpacity);
		for (const FSpark& Spark : Sparks)
		{
			Mesh.AddDisc(Spark.Pos, 1.8f * K, WithAlpha(Spark.Color, FMath::Clamp(Spark.Life / 0.7f, 0.f, 1.f)));
		}
	}

	// SlateIndex may be 16-bit; the ring uses a few thousand vertices, far below the limit.
	if (Verts.Num() > 0 && Indices.Num() > 0 && Verts.Num() < (int32)TNumericLimits<SlateIndex>::Max())
	{
		// A solid colour brush has no texture, so each vertex shows exactly its own colour
		// (an atlased image brush would need its UVs remapped into the atlas).
		static const FSlateColorBrush WhiteBrush(FLinearColor::White);
		FSlateRenderer* Renderer = FSlateApplication::IsInitialized() ? FSlateApplication::Get().GetRenderer() : nullptr;
		const FSlateResourceHandle Handle = Renderer ? Renderer->GetResourceHandle(WhiteBrush) : FSlateResourceHandle();
		FSlateDrawElement::MakeCustomVerts(OutDrawElements, LayerId, Handle, Verts, Indices,
			nullptr, 0, 0, ESlateDrawEffect::None, ESlateBatchDrawFlag::None);
	}
	return LayerId + 1;
}
