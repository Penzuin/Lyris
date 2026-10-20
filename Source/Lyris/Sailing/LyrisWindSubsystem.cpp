// Lyris sailing: the one shared world wind every boat (and later the HUD) reads.

#include "Sailing/LyrisWindSubsystem.h"

#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "Sailing/LyrisWindSettings.h"

namespace LyrisWind
{
	// Separate noise channels so direction, breeze, gusts and calms never move in lockstep.
	enum class EChannel : uint32
	{
		Wander = 1,
		WanderDetail = 2,
		Breeze = 3,
		Gust = 4,
		Calm = 5,
	};

	/** Integer hash (lowbias32 style) of a lattice cell, seed and channel. Pure integer math: identical on every platform. */
	static uint32 Hash(int64 Cell, int32 Seed, EChannel Channel)
	{
		uint32 H = static_cast<uint32>(Cell) ^ (static_cast<uint32>(Cell >> 32) * 0x9E3779B9u);
		H ^= static_cast<uint32>(Seed) * 0x85EBCA6Bu;
		H ^= static_cast<uint32>(Channel) * 0xC2B2AE35u;
		H ^= H >> 16;
		H *= 0x7FEB352Du;
		H ^= H >> 15;
		H *= 0x846CA68Bu;
		H ^= H >> 16;
		return H;
	}

	/** Lattice value in [-1, 1]. */
	static double LatticeValue(int64 Cell, int32 Seed, EChannel Channel)
	{
		return static_cast<double>(Hash(Cell, Seed, Channel)) / 4294967295.0 * 2.0 - 1.0;
	}

	/** Smooth 1D value noise in [-1, 1]: quintic fade between hashed lattice values, so no kinks and no per-frame randomness. */
	static double Noise1D(double X, int32 Seed, EChannel Channel)
	{
		const double Cell = FMath::FloorToDouble(X);
		const double F = X - Cell;
		const double U = F * F * F * (F * (F * 6.0 - 15.0) + 10.0);
		const int64 I = static_cast<int64>(Cell);
		return FMath::Lerp(LatticeValue(I, Seed, Channel), LatticeValue(I + 1, Seed, Channel), U);
	}

	/** Same noise remapped to [0, 1]. */
	static double Noise01(double X, int32 Seed, EChannel Channel)
	{
		return 0.5 + 0.5 * Noise1D(X, Seed, Channel);
	}

	/**
	 * Turns a 0..1 noise value into a 0..1 "spell" amount that is on for roughly Frequency of the time,
	 * with soft edges so gusts and calms ease in and out instead of switching.
	 */
	static double Spell(double Noise, double Frequency)
	{
		if (Frequency <= 0.0)
		{
			return 0.0;
		}
		if (Frequency >= 1.0)
		{
			return 1.0;
		}
		const double Threshold = 1.0 - Frequency;
		return FMath::SmoothStep(Threshold - 0.08, Threshold + 0.08, Noise);
	}
}

ULyrisWindSubsystem* ULyrisWindSubsystem::Get(const UObject* WorldContextObject)
{
	if (!WorldContextObject || !GEngine)
	{
		return nullptr;
	}
	UWorld* World = GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull);
	return World ? World->GetSubsystem<ULyrisWindSubsystem>() : nullptr;
}

float ULyrisWindSubsystem::GetWindClockSeconds() const
{
	const UWorld* World = GetWorld();
	if (!World)
	{
		return 0.f;
	}
	// Server world time is replicated through the game state, so clients agree with the host.
	if (const AGameStateBase* GameState = World->GetGameState())
	{
		return static_cast<float>(GameState->GetServerWorldTimeSeconds());
	}
	return static_cast<float>(World->GetTimeSeconds());
}

FLyrisWindSample ULyrisWindSubsystem::GetWindSampleAtTime(float WorldTimeSeconds) const
{
	return EvaluateWind(*ULyrisWindSettings::Get(), static_cast<double>(WorldTimeSeconds));
}

FLyrisWindSample ULyrisWindSubsystem::GetWindSample() const
{
	return GetWindSampleAtTime(GetWindClockSeconds());
}

float ULyrisWindSubsystem::GetWindYaw() const
{
	return GetWindSample().Yaw;
}

FVector ULyrisWindSubsystem::GetWindDirection() const
{
	return GetWindSample().Direction;
}

float ULyrisWindSubsystem::GetWindStrength() const
{
	return GetWindSample().Strength;
}

FLyrisWindSample ULyrisWindSubsystem::EvaluateWind(const ULyrisWindSettings& Settings, double WorldTimeSeconds)
{
	using namespace LyrisWind;

	const double T = WorldTimeSeconds * FMath::Max(0.0, static_cast<double>(Settings.TimeScale));
	const int32 Seed = Settings.Seed;

	// Direction: a steady veer around the compass plus a slow, lazy wander back and forth.
	const double WanderX = T / FMath::Max(1.0, static_cast<double>(Settings.WanderPeriodSeconds));
	const double Wander = 0.75 * Noise1D(WanderX, Seed, EChannel::Wander)
		+ 0.25 * Noise1D(WanderX * 2.7 + 17.3, Seed, EChannel::WanderDetail);
	const double Yaw = Settings.BaseYaw
		+ Settings.DriftDegreesPerMinute * (T / 60.0)
		+ Settings.WanderDegrees * Wander;

	// Strength: a gentle breeze, eased down in calm spells and lifted by gusts.
	const double BreezeX = T / FMath::Max(1.0, static_cast<double>(Settings.BreezePeriodSeconds));
	double Strength = Settings.BaseStrength + Settings.BreezeVariation * Noise1D(BreezeX, Seed, EChannel::Breeze);

	const double CalmX = T / FMath::Max(1.0, static_cast<double>(Settings.CalmPeriodSeconds));
	const double CalmAlpha = Spell(Noise01(CalmX, Seed, EChannel::Calm), Settings.CalmFrequency);
	Strength = FMath::Lerp(Strength, FMath::Min(Strength, static_cast<double>(Settings.CalmStrength)), CalmAlpha);

	const double GustX = T / FMath::Max(1.0, static_cast<double>(Settings.GustPeriodSeconds));
	const double GustAlpha = Spell(Noise01(GustX, Seed, EChannel::Gust), Settings.GustFrequency) * (1.0 - CalmAlpha);
	Strength += Settings.GustStrength * GustAlpha;

	const double MinStrength = FMath::Clamp(static_cast<double>(Settings.MinStrength), 0.0, 1.0);
	Strength = FMath::Clamp(Strength, MinStrength, 1.0);

	FLyrisWindSample Sample;
	Sample.Yaw = static_cast<float>(FRotator::NormalizeAxis(FMath::Fmod(Yaw, 360.0)));
	const double YawRad = FMath::DegreesToRadians(static_cast<double>(Sample.Yaw));
	Sample.Direction = FVector(FMath::Cos(YawRad), FMath::Sin(YawRad), 0.0);
	Sample.Strength = static_cast<float>(Strength);
	Sample.GustAlpha = static_cast<float>(GustAlpha);
	Sample.CalmAlpha = static_cast<float>(CalmAlpha);
	return Sample;
}
