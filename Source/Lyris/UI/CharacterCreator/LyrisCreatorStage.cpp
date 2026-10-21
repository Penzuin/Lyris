// Lyris character creator: stage actor (preview character, orbit camera, lighting previews).

#include "UI/CharacterCreator/LyrisCreatorStage.h"

#include "Camera/CameraComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/SpotLightComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "UObject/UnrealType.h"

#include "Player/Appearance/LyrisAppearanceComponent.h"

ALyrisCreatorStage::ALyrisCreatorStage()
{
	// Ticks only while the creator is open (camera easing and light placement).
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;
	// The creator may run while the game is paused (e.g. from a pause menu mirror later).
	PrimaryActorTick.bTickEvenWhenPaused = true;

	StageRoot = CreateDefaultSubobject<USceneComponent>(TEXT("StageRoot"));
	SetRootComponent(StageRoot);

	// Camera and lights are positioned in world space every tick around the preview character, so they
	// use absolute transforms and ignore where the stage actor itself sits.
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("CreatorCamera"));
	Camera->SetupAttachment(StageRoot);
	Camera->SetUsingAbsoluteLocation(true);
	Camera->SetUsingAbsoluteRotation(true);
	Camera->SetFieldOfView(35.f);
	Camera->bConstrainAspectRatio = false;
	Camera->PostProcessBlendWeight = 1.f;

	KeyLight = CreateDefaultSubobject<USpotLightComponent>(TEXT("KeyLight"));
	KeyLight->SetupAttachment(StageRoot);
	KeyLight->SetUsingAbsoluteLocation(true);
	KeyLight->SetUsingAbsoluteRotation(true);
	// In a constructor we set the properties directly (the Set* functions dirty render state).
	KeyLight->IntensityUnits = ELightUnits::Candelas;
	KeyLight->AttenuationRadius = 1200.f;
	KeyLight->OuterConeAngle = 40.f;
	KeyLight->InnerConeAngle = 20.f;
	KeyLight->CastShadows = true;
	KeyLight->SetVisibility(false);

	FillLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("FillLight"));
	FillLight->SetupAttachment(StageRoot);
	FillLight->SetUsingAbsoluteLocation(true);
	FillLight->IntensityUnits = ELightUnits::Candelas;
	FillLight->AttenuationRadius = 900.f;
	FillLight->CastShadows = false;
	FillLight->SetVisibility(false);

	RimLight = CreateDefaultSubobject<USpotLightComponent>(TEXT("RimLight"));
	RimLight->SetupAttachment(StageRoot);
	RimLight->SetUsingAbsoluteLocation(true);
	RimLight->SetUsingAbsoluteRotation(true);
	RimLight->IntensityUnits = ELightUnits::Candelas;
	RimLight->AttenuationRadius = 1200.f;
	RimLight->OuterConeAngle = 35.f;
	RimLight->InnerConeAngle = 15.f;
	RimLight->CastShadows = false;
	RimLight->SetVisibility(false);

	BuildDefaultPresets();
}

void ALyrisCreatorStage::BuildDefaultPresets()
{
	// ------------------------------------------------------------------ Framings (spec 2.1)
	// Bones are UE5 mannequin names. Offsets are in the character's frame (X forward, Z up).
	// FallbackHeight is used when the preview has no such bone (measured from the capsule centre).
	auto MakeShot = [](FName Bone, FVector Offset, float Distance, float Pitch, float Fov, float FallbackHeight)
	{
		FLyrisCreatorShotDef Shot;
		Shot.FocusBone = Bone;
		Shot.FocusOffset = Offset;
		Shot.Distance = Distance;
		Shot.Pitch = Pitch;
		Shot.FieldOfView = Fov;
		Shot.FallbackHeight = FallbackHeight;
		return Shot;
	};
	Shots.Add(ELyrisCreatorShot::Full,    MakeShot(TEXT("pelvis"),   FVector(0.f, 0.f, -5.f), 260.f,  4.f, 42.f,   0.f));
	Shots.Add(ELyrisCreatorShot::Upper,   MakeShot(TEXT("spine_03"), FVector(0.f, 0.f, 10.f), 130.f,  5.f, 35.f,  45.f));
	Shots.Add(ELyrisCreatorShot::Face,    MakeShot(TEXT("head"),     FVector(4.f, 0.f,  7.f),  55.f, -5.f, 30.f,  72.f));
	Shots.Add(ELyrisCreatorShot::Eyes,    MakeShot(TEXT("head"),     FVector(9.f, 0.f, 10.f),  25.f,  0.f, 30.f,  75.f));
	Shots.Add(ELyrisCreatorShot::Lantern, MakeShot(TEXT("spine_04"), FVector(15.f, 0.f, 5.f),  80.f,  6.f, 35.f,  40.f));

	// ------------------------------------------------------------------ Face sculpt anchors (spec 9.1)
	// Rough positions on the UE5 mannequin head, offset from the head bone in the character's frame
	// (X forward, Y = character's right, so the character's left is negative Y). Tune per mesh on the
	// actor; T25's stylized head will want its own numbers.
	auto Anchor = [this](const TCHAR* Region, float X, float Y, float Z)
	{
		FLyrisSculptAnchor A;
		A.Region = FName(Region);
		A.Offset = FVector(X, Y, Z);
		SculptAnchors.Add(A);
	};
	Anchor(TEXT("Forehead"), 10.0f,  0.0f, 16.0f);
	Anchor(TEXT("BrowL"),    11.0f, -3.4f, 12.0f);
	Anchor(TEXT("BrowR"),    11.0f,  3.4f, 12.0f);
	Anchor(TEXT("EyeL"),     10.0f, -3.2f,  9.5f);
	Anchor(TEXT("EyeR"),     10.0f,  3.2f,  9.5f);
	Anchor(TEXT("Nose"),     12.5f,  0.0f,  6.0f);
	Anchor(TEXT("Cheeks"),    8.5f, -5.5f,  5.0f);
	Anchor(TEXT("Cheeks"),    8.5f,  5.5f,  5.0f);
	Anchor(TEXT("Mouth"),    10.5f,  0.0f,  1.5f);
	Anchor(TEXT("Jaw"),       4.5f, -6.0f,  0.0f);
	Anchor(TEXT("Jaw"),       4.5f,  6.0f,  0.0f);
	Anchor(TEXT("Chin"),      9.5f,  0.0f, -3.0f);
	Anchor(TEXT("EarL"),      0.0f, -8.0f,  8.0f);
	Anchor(TEXT("EarR"),      0.0f,  8.0f,  8.0f);

	// ------------------------------------------------------------------ Lighting previews (spec 9.5)
	const FLinearColor Gold      = FLinearColor(FColor::FromHex(TEXT("E3AE45")));
	const FLinearColor Moonglass = FLinearColor(FColor::FromHex(TEXT("7AC0E6")));

	// Dusk deck (default): low warm sun from behind the sail, peach sky, soft lavender shadows.
	FLyrisCreatorLightingDef Dusk;
	Dusk.KeyColor = FLinearColor(1.0f, 0.60f, 0.34f);
	Dusk.KeyIntensity = 900.f;
	Dusk.KeyRotation = FRotator(12.f, 55.f, 0.f);
	Dusk.FillColor = FLinearColor(0.62f, 0.55f, 0.88f);
	Dusk.FillIntensity = 140.f;
	Dusk.RimColor = FLinearColor(1.0f, 0.52f, 0.30f);
	Dusk.RimIntensity = 700.f;
	Dusk.WhiteTemp = 7000.f;
	Dusk.Saturation = 1.08f;
	Dusk.Vignette = 0.45f;
	LightingPresets.Add(ELyrisCreatorLighting::DuskDeck, Dusk);

	// Lamp-lit: night, warm Gold lamp from above-front, deep blue surroundings.
	FLyrisCreatorLightingDef Lamp;
	Lamp.KeyColor = Gold;
	Lamp.KeyIntensity = 700.f;
	Lamp.KeyRotation = FRotator(45.f, 15.f, 0.f);
	Lamp.FillColor = FLinearColor(0.18f, 0.26f, 0.55f);
	Lamp.FillIntensity = 80.f;
	Lamp.RimColor = FLinearColor(0.30f, 0.42f, 0.80f);
	Lamp.RimIntensity = 350.f;
	Lamp.WhiteTemp = 6600.f;
	Lamp.Saturation = 1.0f;
	Lamp.Vignette = 0.6f;
	LightingPresets.Add(ELyrisCreatorLighting::LampLit, Lamp);

	// Midday: high sun, clear sky, the brightest and most neutral.
	FLyrisCreatorLightingDef Midday;
	Midday.KeyColor = FLinearColor(1.0f, 0.97f, 0.92f);
	Midday.KeyIntensity = 1400.f;
	Midday.KeyRotation = FRotator(65.f, 30.f, 0.f);
	Midday.FillColor = FLinearColor(0.80f, 0.88f, 1.0f);
	Midday.FillIntensity = 300.f;
	Midday.RimColor = FLinearColor(1.0f, 1.0f, 1.0f);
	Midday.RimIntensity = 400.f;
	Midday.WhiteTemp = 6500.f;
	Midday.Saturation = 1.0f;
	Midday.Vignette = 0.25f;
	LightingPresets.Add(ELyrisCreatorLighting::Midday, Midday);

	// Mist: cold Moonglass light; elf glow and Deepkin shine show best here.
	FLyrisCreatorLightingDef Mist;
	Mist.KeyColor = Moonglass;
	Mist.KeyIntensity = 600.f;
	Mist.KeyRotation = FRotator(30.f, -40.f, 0.f);
	Mist.FillColor = Moonglass * 0.8f;
	Mist.FillIntensity = 160.f;
	Mist.RimColor = Moonglass;
	Mist.RimIntensity = 500.f;
	Mist.WhiteTemp = 6000.f;
	Mist.Saturation = 0.85f;
	Mist.Vignette = 0.55f;
	LightingPresets.Add(ELyrisCreatorLighting::Mist, Mist);
}

// ---------------------------------------------------------------------------------------- Session

void ALyrisCreatorStage::BeginCreator(APlayerController* PlayerController)
{
	SpawnPreviewIfNeeded();
	GetAppearanceComponent(); // make sure there is one before the UI asks

	ActivePlayer = PlayerController;
	if (ActivePlayer)
	{
		PreviousViewTarget = ActivePlayer->GetViewTarget();
		// AActor::CalcCamera uses this actor's camera component when it is the view target.
		ActivePlayer->SetViewTarget(this);
	}

	bActive = true;
	KeyLight->SetVisibility(true);
	FillLight->SetVisibility(true);
	RimLight->SetVisibility(true);
	SetLightingPreset(CurrentLighting);

	UserYaw = 0.f;
	UserPitch = 0.f;
	Zoom = 1.f;
	UpdateCamera(0.f, /*bSnap*/ true);
	PlaceLights();
	SetActorTickEnabled(true);
}

void ALyrisCreatorStage::EndCreator()
{
	if (!bActive)
	{
		return;
	}
	bActive = false;
	SetActorTickEnabled(false);

	KeyLight->SetVisibility(false);
	FillLight->SetVisibility(false);
	RimLight->SetVisibility(false);

	if (ActivePlayer)
	{
		AActor* Back = PreviousViewTarget ? PreviousViewTarget.Get() : ActivePlayer->GetPawn();
		if (Back)
		{
			ActivePlayer->SetViewTarget(Back);
		}
	}
	ActivePlayer = nullptr;
	PreviousViewTarget = nullptr;

	if (bSpawnedPreview && PreviewCharacter)
	{
		PreviewCharacter->Destroy();
		PreviewCharacter = nullptr;
		bSpawnedPreview = false;
	}
}

void ALyrisCreatorStage::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	EndCreator();
	Super::EndPlay(EndPlayReason);
}

void ALyrisCreatorStage::SpawnPreviewIfNeeded()
{
	if (PreviewCharacter || !GetWorld())
	{
		return;
	}

	TSubclassOf<APawn> ClassToSpawn = PreviewCharacterClass;
	if (!ClassToSpawn)
	{
		if (const AGameModeBase* GameMode = GetWorld()->GetAuthGameMode())
		{
			ClassToSpawn = GameMode->DefaultPawnClass;
		}
	}
	if (!ClassToSpawn)
	{
		ClassToSpawn = ACharacter::StaticClass();
	}

	FActorSpawnParameters Params;
	Params.Owner = this;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;

	// The preview stands on the stage, facing the stage's forward. Nobody possesses it, so it does not
	// take input or move (CharacterMovement does not simulate without a controller).
	PreviewCharacter = GetWorld()->SpawnActor<APawn>(ClassToSpawn, GetActorLocation(), GetActorRotation(), Params);
	bSpawnedPreview = PreviewCharacter != nullptr;
}

APawn* ALyrisCreatorStage::GetPreviewCharacter()
{
	SpawnPreviewIfNeeded();
	return PreviewCharacter;
}

ULyrisAppearanceComponent* ALyrisCreatorStage::GetAppearanceComponent()
{
	APawn* Pawn = GetPreviewCharacter();
	if (!Pawn)
	{
		return nullptr;
	}

	ULyrisAppearanceComponent* Appearance = Pawn->FindComponentByClass<ULyrisAppearanceComponent>();
	if (!Appearance)
	{
		// The preview class has no appearance component yet (T14/T26 will add it to the player
		// character); add one at runtime so the creator still works.
		Appearance = NewObject<ULyrisAppearanceComponent>(Pawn, TEXT("LyrisCreatorAppearance"));
		Pawn->AddInstanceComponent(Appearance);
		Appearance->RegisterComponent();
	}
	return Appearance;
}

USkeletalMeshComponent* ALyrisCreatorStage::GetPreviewMesh() const
{
	if (!PreviewCharacter)
	{
		return nullptr;
	}
	if (const ACharacter* Character = Cast<ACharacter>(PreviewCharacter))
	{
		return Character->GetMesh();
	}
	return PreviewCharacter->FindComponentByClass<USkeletalMeshComponent>();
}

// ---------------------------------------------------------------------------------------- Camera

void ALyrisCreatorStage::SetShot(ELyrisCreatorShot Shot)
{
	if (Shot != CurrentShot)
	{
		Zoom = 1.f;
		UserPitch = 0.f;
	}
	CurrentShot = Shot;
}

void ALyrisCreatorStage::AddOrbit(float YawDegrees, float PitchDegrees)
{
	UserYaw = FRotator::NormalizeAxis(UserYaw + YawDegrees);
	const FLyrisCreatorShotDef* Shot = Shots.Find(CurrentShot);
	const float BasePitch = Shot ? Shot->Pitch : 0.f;
	// Clamp the final pitch (shot pitch + user pitch) to the spec's -15..30 degrees.
	UserPitch = FMath::Clamp(BasePitch + UserPitch + PitchDegrees, MinPitch, MaxPitch) - BasePitch;
}

void ALyrisCreatorStage::AddZoom(float Steps)
{
	// Each step brings the camera 10% closer (positive) or further (negative).
	Zoom = FMath::Clamp(Zoom * FMath::Pow(0.9f, Steps), MinZoom, MaxZoom);
}

void ALyrisCreatorStage::LookAtProfile()
{
	// 90 degrees shows the character's right side.
	UserYaw = 90.f;
}

FVector ALyrisCreatorStage::ComputeFocus(const FLyrisCreatorShotDef& Shot) const
{
	if (!PreviewCharacter)
	{
		return GetActorLocation() + FVector(0.f, 0.f, Shot.FallbackHeight);
	}

	const FRotator Facing(0.f, PreviewCharacter->GetActorRotation().Yaw, 0.f);
	const FVector Offset = Facing.RotateVector(Shot.FocusOffset);

	const USkeletalMeshComponent* Mesh = GetPreviewMesh();
	if (Mesh && !Shot.FocusBone.IsNone() && Mesh->DoesSocketExist(Shot.FocusBone))
	{
		return Mesh->GetSocketLocation(Shot.FocusBone) + Offset;
	}
	return PreviewCharacter->GetActorLocation() + FVector(0.f, 0.f, Shot.FallbackHeight) + Offset;
}

void ALyrisCreatorStage::UpdateCamera(float DeltaSeconds, bool bSnap)
{
	const FLyrisCreatorShotDef* ShotPtr = Shots.Find(CurrentShot);
	const FLyrisCreatorShotDef Shot = ShotPtr ? *ShotPtr : FLyrisCreatorShotDef();

	const float FacingYaw = PreviewCharacter ? PreviewCharacter->GetActorRotation().Yaw : GetActorRotation().Yaw;
	const float TargetYaw = FacingYaw + UserYaw;
	const float TargetPitch = FMath::Clamp(Shot.Pitch + UserPitch, MinPitch, MaxPitch);
	const float TargetDistance = Shot.Distance * Zoom;
	const float TargetFov = Shot.FieldOfView;
	const FVector TargetFocus = ComputeFocus(Shot);

	// Exponential ease that covers ~99% of the gap in ShotBlendTime seconds.
	const float Alpha = bSnap ? 1.f : 1.f - FMath::Exp(-DeltaSeconds * 4.6f / FMath::Max(ShotBlendTime, 0.05f));

	CurrentYaw = FRotator::NormalizeAxis(CurrentYaw + FMath::FindDeltaAngleDegrees(CurrentYaw, TargetYaw) * Alpha);
	CurrentPitch = FMath::Lerp(CurrentPitch, TargetPitch, Alpha);
	CurrentDistance = FMath::Lerp(CurrentDistance, TargetDistance, Alpha);
	CurrentFov = FMath::Lerp(CurrentFov, TargetFov, Alpha);
	CurrentFocus = FMath::Lerp(CurrentFocus, TargetFocus, Alpha);

	// The camera sits on a sphere around the focus point: yaw 0 = in front of the character, positive
	// pitch = above it, looking back at the focus.
	const FVector Direction = FRotator(CurrentPitch, CurrentYaw, 0.f).Vector();
	const FVector CameraLocation = CurrentFocus + Direction * CurrentDistance;
	Camera->SetWorldLocationAndRotation(CameraLocation, (CurrentFocus - CameraLocation).Rotation());
	Camera->SetFieldOfView(CurrentFov);
}

void ALyrisCreatorStage::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bActive)
	{
		UpdateCamera(DeltaSeconds, /*bSnap*/ false);
		PlaceLights();
	}
}

// ---------------------------------------------------------------------------------------- Lighting

void ALyrisCreatorStage::SetLightingPreset(ELyrisCreatorLighting Preset)
{
	CurrentLighting = Preset;
	const FLyrisCreatorLightingDef* Def = LightingPresets.Find(Preset);
	if (!Def)
	{
		return;
	}

	KeyLight->SetLightColor(Def->KeyColor);
	KeyLight->SetIntensity(Def->KeyIntensity);
	FillLight->SetLightColor(Def->FillColor);
	FillLight->SetIntensity(Def->FillIntensity);
	RimLight->SetLightColor(Def->RimColor);
	RimLight->SetIntensity(Def->RimIntensity);

	// A light grade on the creator camera so each mood reads at a glance.
	FPostProcessSettings& PP = Camera->PostProcessSettings;
	PP.bOverride_WhiteTemp = true;
	PP.WhiteTemp = Def->WhiteTemp;
	PP.bOverride_ColorSaturation = true;
	PP.ColorSaturation = FVector4(Def->Saturation, Def->Saturation, Def->Saturation, 1.f);
	PP.bOverride_VignetteIntensity = true;
	PP.VignetteIntensity = Def->Vignette;

	PlaceLights();
}

void ALyrisCreatorStage::PlaceLightAround(USceneComponent* Light, float RelYaw, float Pitch, float Distance) const
{
	if (!Light)
	{
		return;
	}
	const FVector Pivot = PreviewCharacter
		? PreviewCharacter->GetActorLocation() + FVector(0.f, 0.f, 50.f)  // about chest height
		: GetActorLocation() + FVector(0.f, 0.f, 140.f);
	const float FacingYaw = PreviewCharacter ? PreviewCharacter->GetActorRotation().Yaw : GetActorRotation().Yaw;

	const FVector Location = Pivot + FRotator(Pitch, FacingYaw + RelYaw, 0.f).Vector() * Distance;
	Light->SetWorldLocationAndRotation(Location, (Pivot - Location).Rotation());
}

void ALyrisCreatorStage::PlaceLights()
{
	const FLyrisCreatorLightingDef* Def = LightingPresets.Find(CurrentLighting);
	const FRotator KeyRot = Def ? Def->KeyRotation : FRotator(25.f, 35.f, 0.f);

	// Key where the preset says; fill opposite it, low and in front; rim behind on the key's side.
	PlaceLightAround(KeyLight, KeyRot.Yaw, KeyRot.Pitch, 320.f);
	PlaceLightAround(FillLight, -KeyRot.Yaw * 0.8f, 10.f, 220.f);
	PlaceLightAround(RimLight, 180.f - KeyRot.Yaw * 0.5f, 30.f, 300.f);
}

// ---------------------------------------------------------------------------------------- Previews

void ALyrisCreatorStage::CallPreviewFunction(FName FunctionName, FName Arg)
{
	if (!PreviewCharacter)
	{
		return;
	}
	UFunction* Function = PreviewCharacter->FindFunction(FunctionName);
	if (!Function || Function->NumParms != 1 || Function->ParmsSize != sizeof(FName))
	{
		return;
	}
	// Only call it if the single parameter really is an FName (and not a return value).
	const FNameProperty* Param = CastField<FNameProperty>(Function->PropertyLink);
	if (!Param || Param->HasAnyPropertyFlags(CPF_ReturnParm | CPF_OutParm))
	{
		return;
	}
	FName ParamValue = Arg;
	PreviewCharacter->ProcessEvent(Function, &ParamValue);
}

void ALyrisCreatorStage::PreviewExpression(FName ExpressionId)
{
	// TODO(T25/Player): real facial expression clips. Until then the preview character can implement
	// LyrisPreviewExpression(FName) itself, or a Blueprint subclass of the stage can use the event.
	CallPreviewFunction(TEXT("LyrisPreviewExpression"), ExpressionId);
	OnPreviewExpression(ExpressionId);
}

void ALyrisCreatorStage::PreviewPose(FName PoseId)
{
	// TODO(Player): pose montages (wave, hold lantern, sit on a crate, lean on the rail, windy, walk).
	CallPreviewFunction(TEXT("LyrisPreviewPose"), PoseId);
	OnPreviewPose(PoseId);
}

// ---------------------------------------------------------------------------------------- Sculpt

UCameraComponent* ALyrisCreatorStage::GetCreatorCamera() const
{
	return Camera;
}

void ALyrisCreatorStage::GetSculptAnchorsWorld(TArray<TPair<FName, FVector>>& OutAnchors) const
{
	OutAnchors.Reset();
	if (!PreviewCharacter)
	{
		return;
	}

	FVector Head = PreviewCharacter->GetActorLocation() + FVector(0.f, 0.f, 65.f);
	const USkeletalMeshComponent* Mesh = GetPreviewMesh();
	if (Mesh && Mesh->DoesSocketExist(HeadBone))
	{
		Head = Mesh->GetSocketLocation(HeadBone);
	}
	const FRotator Facing(0.f, PreviewCharacter->GetActorRotation().Yaw, 0.f);

	for (const FLyrisSculptAnchor& Anchor : SculptAnchors)
	{
		OutAnchors.Emplace(Anchor.Region, Head + Facing.RotateVector(Anchor.Offset));
	}
}
