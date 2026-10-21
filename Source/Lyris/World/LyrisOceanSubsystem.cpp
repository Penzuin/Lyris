// Lyris world: the one shared sea state. See World/OCEAN_CONTRACT.md for the formula the material must match.

#include "World/LyrisOceanSubsystem.h"

#include "Camera/PlayerCameraManager.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/KismetMaterialLibrary.h"
#include "Materials/MaterialParameterCollection.h"
#include "World/LyrisOceanSettings.h"

DEFINE_LOG_CATEGORY_STATIC(LogLyrisOcean, Log, All);

namespace LyrisOcean
{
	/** Gravity in cm/s^2, as fixed by the contract (deep-water wave speed c = sqrt(g / k)). */
	static constexpr double Gravity = 980.0;

	/** Fixed-point iterations used to undo the horizontal Gerstner drift when asking "how high is the water at this XY". */
	static constexpr int32 InvertIterations = 3;

	/** Shortest wavelength we accept, so k never blows up. */
	static constexpr double MinWavelengthCm = 1.0;

	// MPC_Sea parameter names. Must match the contract and lyris_build_world.py exactly.
	static const FName OceanTimeName(TEXT("OceanTime"));
	static const FName SeaLevelName(TEXT("SeaLevel"));
	static const FName CalmAmplitudeScaleName(TEXT("CalmAmplitudeScale"));
	static const FName WaveSteepnessName(TEXT("WaveSteepness"));
	static const FName WaveNames[ULyrisOceanSettings::WaveCount] = {
		FName(TEXT("Wave0")), FName(TEXT("Wave1")), FName(TEXT("Wave2")), FName(TEXT("Wave3")) };
	static const FName CalmZoneNames[ULyrisOceanSettings::MaxMaterialCalmZones] = {
		FName(TEXT("CalmZone0")), FName(TEXT("CalmZone1")), FName(TEXT("CalmZone2")), FName(TEXT("CalmZone3")) };

	/** Unit direction for a yaw in degrees (0 = +X, 90 = +Y). The material receives exactly this as (DirX, DirY). */
	static FVector2D YawToDir(float YawDeg)
	{
		const double Rad = FMath::DegreesToRadians(static_cast<double>(YawDeg));
		return FVector2D(FMath::Cos(Rad), FMath::Sin(Rad));
	}

	/** Calm contribution of one zone at P: 1 inside Radius, easing to 0 at Radius + Falloff (1 - smoothstep). */
	static double ZoneCalm(const FLyrisCalmZone& Zone, const FVector2D& P)
	{
		const double Distance = FVector2D::Distance(P, Zone.Center);
		const double Inner = static_cast<double>(Zone.Radius);
		const double Outer = Inner + FMath::Max(0.0, static_cast<double>(Zone.Falloff));
		// FMath::SmoothStep returns 0 below Inner and 1 at or above Outer, so Falloff 0 is a hard edge (no divide by zero).
		return 1.0 - FMath::SmoothStep(Inner, Outer, Distance);
	}

	/** How far P is from the zone's calm edge, for picking the zones the material sees (0 when inside). */
	static double DistanceToZone(const FLyrisCalmZone& Zone, const FVector2D& P)
	{
		return FMath::Max(0.0, FVector2D::Distance(P, Zone.Center) - static_cast<double>(Zone.Radius));
	}
}

ULyrisOceanSubsystem* ULyrisOceanSubsystem::Get(const UObject* WorldContext)
{
	if (!WorldContext || !GEngine)
	{
		return nullptr;
	}
	UWorld* World = GEngine->GetWorldFromContextObject(WorldContext, EGetWorldErrorMode::ReturnNull);
	return World ? World->GetSubsystem<ULyrisOceanSubsystem>() : nullptr;
}

void ULyrisOceanSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	CachedRevision = 0;
	CollectionRevision = 0;
	EnsureCache();
}

void ULyrisOceanSubsystem::Deinitialize()
{
	RegisteredCalmZones.Reset();
	SeaCollection = nullptr;
	Super::Deinitialize();
}

TStatId ULyrisOceanSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(ULyrisOceanSubsystem, STATGROUP_Tickables);
}

void ULyrisOceanSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	EnsureCache();
	WriteMaterialParameters();
}

// ---- Clock -------------------------------------------------------------------------------------

double ULyrisOceanSubsystem::GetClockSeconds() const
{
	const UWorld* World = GetWorld();
	if (!World)
	{
		return 0.0;
	}
	// Same clock as the wind: server world time is replicated through the game state, so clients agree with the host.
	if (const AGameStateBase* GameState = World->GetGameState())
	{
		return GameState->GetServerWorldTimeSeconds();
	}
	return World->GetTimeSeconds();
}

float ULyrisOceanSubsystem::GetOceanTime() const
{
	const ULyrisOceanSettings* Settings = ULyrisOceanSettings::Get();
	return static_cast<float>(GetClockSeconds() * FMath::Max(0.0, static_cast<double>(Settings->TimeScale)));
}

float ULyrisOceanSubsystem::GetSeaLevel() const
{
	return ULyrisOceanSettings::Get()->SeaLevel;
}

// ---- Wave cache --------------------------------------------------------------------------------

void ULyrisOceanSubsystem::EnsureCache() const
{
	const ULyrisOceanSettings* Settings = ULyrisOceanSettings::Get();
	if (CachedRevision == Settings->GetRevision())
	{
		return;
	}
	CachedRevision = Settings->GetRevision();

	const double N = static_cast<double>(ULyrisOceanSettings::WaveCount);
	for (int32 i = 0; i < ULyrisOceanSettings::WaveCount; ++i)
	{
		const FLyrisOceanWave& Wave = Settings->Waves[i];
		FWaveCache& Cache = WaveCache[i];

		const double L = FMath::Max(LyrisOcean::MinWavelengthCm, static_cast<double>(Wave.WavelengthCm));
		Cache.Dir = LyrisOcean::YawToDir(Wave.DirectionYawDeg);
		Cache.K = 2.0 * UE_DOUBLE_PI / L;
		const double C = FMath::Sqrt(LyrisOcean::Gravity / Cache.K);
		Cache.Omega = Cache.K * C;
		Cache.Amplitude = FMath::Max(0.0, static_cast<double>(Wave.AmplitudeCm));
		// Q uses the unscaled amplitude so it stays bounded; a flat wave has no horizontal motion at all.
		const double Steepness = FMath::Clamp(static_cast<double>(Wave.Steepness), 0.0, 1.0);
		Cache.Q = Cache.Amplitude > UE_DOUBLE_SMALL_NUMBER ? Steepness / (Cache.K * Cache.Amplitude * N) : 0.0;
	}
}

// ---- Roughness ---------------------------------------------------------------------------------

double ULyrisOceanSubsystem::ComputeRoughness(const FVector2D& P) const
{
	// r(p) = 1 - max over used zones of (1 - smoothstep(Radius, Radius + Falloff, |p - Center|)); no zones = 1.
	double MaxCalm = 0.0;
	for (const FLyrisCalmZone& Zone : ULyrisOceanSettings::Get()->HomeCalmZones)
	{
		if (Zone.Radius > 0.f)
		{
			MaxCalm = FMath::Max(MaxCalm, LyrisOcean::ZoneCalm(Zone, P));
		}
	}
	for (const TPair<FName, FLyrisCalmZone>& Pair : RegisteredCalmZones)
	{
		if (Pair.Value.Radius > 0.f)
		{
			MaxCalm = FMath::Max(MaxCalm, LyrisOcean::ZoneCalm(Pair.Value, P));
		}
	}
	return 1.0 - MaxCalm;
}

float ULyrisOceanSubsystem::GetRoughnessAt(FVector2D WorldXY) const
{
	return static_cast<float>(ComputeRoughness(WorldXY));
}

void ULyrisOceanSubsystem::RegisterCalmZone(FName Id, FVector2D Center, float Radius, float Falloff)
{
	if (Id.IsNone())
	{
		UE_LOG(LogLyrisOcean, Warning, TEXT("RegisterCalmZone called with no Id; ignored."));
		return;
	}
	RegisteredCalmZones.Add(Id, FLyrisCalmZone(Center, FMath::Max(0.f, Radius), FMath::Max(0.f, Falloff)));
}

void ULyrisOceanSubsystem::UnregisterCalmZone(FName Id)
{
	RegisteredCalmZones.Remove(Id);
}

// ---- Gerstner evaluation -----------------------------------------------------------------------

ULyrisOceanSubsystem::FSurfaceSample ULyrisOceanSubsystem::EvaluateAt(const FVector2D& P, double T, bool bWithNormalAndVelocity) const
{
	EnsureCache();
	const ULyrisOceanSettings* Settings = ULyrisOceanSettings::Get();

	// m(p) = lerp(CalmAmplitudeScale, 1, r(p)), evaluated at the undisplaced point like the material does.
	const double Roughness = ComputeRoughness(P);
	const double AmplitudeScale = FMath::Lerp(FMath::Clamp(static_cast<double>(Settings->CalmAmplitudeScale), 0.0, 1.0), 1.0, Roughness);

	FSurfaceSample Out;
	double NormalX = 0.0;
	double NormalY = 0.0;
	double NormalZ = 1.0;

	for (int32 i = 0; i < ULyrisOceanSettings::WaveCount; ++i)
	{
		const FWaveCache& W = WaveCache[i];
		const double A = W.Amplitude * AmplitudeScale;
		if (A <= 0.0)
		{
			continue;
		}

		// theta = k * (D . p) - k * c * t
		const double Theta = W.K * FVector2D::DotProduct(W.Dir, P) - W.Omega * T;
		double SinTheta = 0.0;
		double CosTheta = 0.0;
		FMath::SinCos(&SinTheta, &CosTheta, Theta);

		const double QA = W.Q * A;
		Out.HorizontalOffset += W.Dir * (QA * CosTheta);
		Out.Height += A * SinTheta;

		if (bWithNormalAndVelocity)
		{
			// Standard Gerstner normal (GPU Gems 1, ch. 1): N = (-sum D.x*kA*cos, -sum D.y*kA*cos, 1 - sum Q*kA*sin).
			const double KA = W.K * A;
			NormalX -= W.Dir.X * KA * CosTheta;
			NormalY -= W.Dir.Y * KA * CosTheta;
			NormalZ -= W.Q * KA * SinTheta;

			// Orbital velocity is the time derivative of the displaced position (d theta / dt = -omega).
			Out.Velocity.X += W.Dir.X * QA * W.Omega * SinTheta;
			Out.Velocity.Y += W.Dir.Y * QA * W.Omega * SinTheta;
			Out.Velocity.Z -= A * W.Omega * CosTheta;
		}
	}

	if (bWithNormalAndVelocity)
	{
		Out.Normal = FVector(NormalX, NormalY, NormalZ).GetSafeNormal(UE_SMALL_NUMBER, FVector::UpVector);
	}
	return Out;
}

FVector2D ULyrisOceanSubsystem::InvertHorizontal(const FVector2D& WorldXY, double T) const
{
	// The surface point that ends up above WorldXY started somewhere else (Gerstner waves push water sideways).
	// Solve p + offset(p) = WorldXY by fixed-point iteration: p <- WorldXY - offset(p). Three steps, as the contract fixes.
	FVector2D P = WorldXY;
	for (int32 Iter = 0; Iter < LyrisOcean::InvertIterations; ++Iter)
	{
		P = WorldXY - EvaluateAt(P, T, false).HorizontalOffset;
	}
	return P;
}

float ULyrisOceanSubsystem::GetWaterHeightAt(FVector2D WorldXY) const
{
	const double T = GetOceanTime();
	const FVector2D P = InvertHorizontal(WorldXY, T);
	return static_cast<float>(ULyrisOceanSettings::Get()->SeaLevel + EvaluateAt(P, T, false).Height);
}

FVector ULyrisOceanSubsystem::GetWaterNormalAt(FVector2D WorldXY) const
{
	const double T = GetOceanTime();
	return EvaluateAt(InvertHorizontal(WorldXY, T), T, true).Normal;
}

FVector ULyrisOceanSubsystem::GetWaterVelocityAt(FVector2D WorldXY) const
{
	const double T = GetOceanTime();
	// cm/s of ocean time; scale by TimeScale so a sped-up sea also moves faster in real seconds.
	const double TimeScale = FMath::Max(0.0, static_cast<double>(ULyrisOceanSettings::Get()->TimeScale));
	return EvaluateAt(InvertHorizontal(WorldXY, T), T, true).Velocity * TimeScale;
}

// ---- Material Parameter Collection -------------------------------------------------------------

FVector2D ULyrisOceanSubsystem::GetPlayerXY() const
{
	const UWorld* World = GetWorld();
	if (!World)
	{
		return FVector2D::ZeroVector;
	}
	// On a client this is the local player's controller, which is the one whose screen draws the sea.
	if (const APlayerController* PC = World->GetFirstPlayerController())
	{
		if (PC->PlayerCameraManager)
		{
			return FVector2D(PC->PlayerCameraManager->GetCameraLocation());
		}
		if (const APawn* Pawn = PC->GetPawn())
		{
			return FVector2D(Pawn->GetActorLocation());
		}
	}
	// No player (editor viewport, dedicated server): measure from the world origin.
	return FVector2D::ZeroVector;
}

void ULyrisOceanSubsystem::WriteMaterialParameters()
{
	UWorld* World = GetWorld();
	const ULyrisOceanSettings* Settings = ULyrisOceanSettings::Get();
	if (!World || World->IsNetMode(NM_DedicatedServer))
	{
		return;
	}

	// Load MPC_Sea once per settings change. If it is missing (lyris_build_world.py has not made it yet), skip quietly.
	if (CollectionRevision != Settings->GetRevision())
	{
		CollectionRevision = Settings->GetRevision();
		SeaCollection = Settings->SeaParameterCollection.IsNull() ? nullptr : Settings->SeaParameterCollection.LoadSynchronous();
		if (SeaCollection)
		{
			bLoggedMissingCollection = false;
		}
		else if (!bLoggedMissingCollection)
		{
			bLoggedMissingCollection = true;
			UE_LOG(LogLyrisOcean, Log, TEXT("Sea Material Parameter Collection '%s' not found; the sea material will not get wave values until it exists."),
				*Settings->SeaParameterCollection.ToString());
		}
	}
	if (!SeaCollection)
	{
		return;
	}

	using namespace LyrisOcean;

	UKismetMaterialLibrary::SetScalarParameterValue(World, SeaCollection, OceanTimeName, GetOceanTime());
	UKismetMaterialLibrary::SetScalarParameterValue(World, SeaCollection, SeaLevelName, Settings->SeaLevel);
	UKismetMaterialLibrary::SetScalarParameterValue(World, SeaCollection, CalmAmplitudeScaleName, Settings->CalmAmplitudeScale);

	// Wave0..Wave3 = (DirX, DirY, WavelengthCm, AmplitudeCm); WaveSteepness = (S0, S1, S2, S3).
	// Raw settings values: the material derives k, c and Q itself with the same formula.
	float Steepness[ULyrisOceanSettings::WaveCount];
	for (int32 i = 0; i < ULyrisOceanSettings::WaveCount; ++i)
	{
		const FLyrisOceanWave& Wave = Settings->Waves[i];
		const FVector2D Dir = YawToDir(Wave.DirectionYawDeg);
		UKismetMaterialLibrary::SetVectorParameterValue(World, SeaCollection, WaveNames[i],
			FLinearColor(static_cast<float>(Dir.X), static_cast<float>(Dir.Y),
				FMath::Max(static_cast<float>(MinWavelengthCm), Wave.WavelengthCm), FMath::Max(0.f, Wave.AmplitudeCm)));
		Steepness[i] = FMath::Clamp(Wave.Steepness, 0.f, 1.f);
	}
	UKismetMaterialLibrary::SetVectorParameterValue(World, SeaCollection, WaveSteepnessName,
		FLinearColor(Steepness[0], Steepness[1], Steepness[2], Steepness[3]));

	// CalmZone0..CalmZone3 = (CenterX, CenterY, Radius, Falloff); Radius 0 = unused.
	// Home zones first, then lamp zones, each group nearest to the player first.
	const FVector2D PlayerXY = GetPlayerXY();
	auto ByDistance = [&PlayerXY](const FLyrisCalmZone& A, const FLyrisCalmZone& B)
	{
		return DistanceToZone(A, PlayerXY) < DistanceToZone(B, PlayerXY);
	};

	TArray<FLyrisCalmZone, TInlineAllocator<8>> HomeZones;
	for (const FLyrisCalmZone& Zone : Settings->HomeCalmZones)
	{
		if (Zone.Radius > 0.f)
		{
			HomeZones.Add(Zone);
		}
	}
	HomeZones.Sort(ByDistance);

	TArray<FLyrisCalmZone, TInlineAllocator<16>> LampZones;
	for (const TPair<FName, FLyrisCalmZone>& Pair : RegisteredCalmZones)
	{
		if (Pair.Value.Radius > 0.f)
		{
			LampZones.Add(Pair.Value);
		}
	}
	LampZones.Sort(ByDistance);

	int32 Slot = 0;
	for (const FLyrisCalmZone& Zone : HomeZones)
	{
		if (Slot >= ULyrisOceanSettings::MaxMaterialCalmZones)
		{
			break;
		}
		UKismetMaterialLibrary::SetVectorParameterValue(World, SeaCollection, CalmZoneNames[Slot++],
			FLinearColor(static_cast<float>(Zone.Center.X), static_cast<float>(Zone.Center.Y), Zone.Radius, Zone.Falloff));
	}
	for (const FLyrisCalmZone& Zone : LampZones)
	{
		if (Slot >= ULyrisOceanSettings::MaxMaterialCalmZones)
		{
			break;
		}
		UKismetMaterialLibrary::SetVectorParameterValue(World, SeaCollection, CalmZoneNames[Slot++],
			FLinearColor(static_cast<float>(Zone.Center.X), static_cast<float>(Zone.Center.Y), Zone.Radius, Zone.Falloff));
	}
	for (; Slot < ULyrisOceanSettings::MaxMaterialCalmZones; ++Slot)
	{
		UKismetMaterialLibrary::SetVectorParameterValue(World, SeaCollection, CalmZoneNames[Slot], FLinearColor(0.f, 0.f, 0.f, 0.f));
	}
}
