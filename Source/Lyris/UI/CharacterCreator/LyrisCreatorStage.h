// Lyris character creator: the little stage the creator runs on (preview character, camera rig, lights).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "LyrisCreatorStage.generated.h"

class APawn;
class APlayerController;
class USceneComponent;
class UCameraComponent;
class USpotLightComponent;
class UPointLightComponent;
class USkeletalMeshComponent;
class ULyrisAppearanceComponent;

/** Camera framings the creator eases between (design/character_creator.md, section 2.1). */
UENUM(BlueprintType)
enum class ELyrisCreatorShot : uint8
{
	Full,     // whole body, head to feet (260 cm)
	Upper,    // waist up (130 cm)
	Face,     // head and neck, slightly below eye line (55 cm)
	Eyes,     // both eyes and brows, extreme close-up (25 cm)
	Lantern   // chest up, lantern held at chest height (80 cm), step 5 (Lantern)
};

/** Lighting previews (spec 9.5). They only change the preview, never the character. Dusk deck is the
 *  default: creation is framed as sailing into Moonharbor at dusk. */
UENUM(BlueprintType)
enum class ELyrisCreatorLighting : uint8
{
	DuskDeck,
	LampLit,
	Midday,
	Mist
};

/** One camera framing. The camera orbits a point on the preview character. */
USTRUCT(BlueprintType)
struct FLyrisCreatorShotDef
{
	GENERATED_BODY()

	/** Bone the camera looks at. Falls back to the actor location plus FocusOffset when the bone is missing. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Shot")
	FName FocusBone;

	/** Extra offset from the focus point in the preview's frame (X forward, Y right, Z up), cm. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Shot")
	FVector FocusOffset = FVector::ZeroVector;

	/** Camera distance from the focus point, cm, before the player's zoom. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Shot")
	float Distance = 260.f;

	/** Degrees above the focus point (positive looks down on the character, negative from below). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Shot")
	float Pitch = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Shot")
	float FieldOfView = 30.f;

	/** Height above the actor's location used when FocusBone is missing on the preview mesh, cm. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Shot")
	float FallbackHeight = 0.f;
};

/**
 * A point on the face for click-and-drag sculpting. Region is the catalog's FLyrisSliderDef::SculptRegion
 * (spec 9.1: Forehead, BrowL, BrowR, EyeL, EyeR, Nose, Cheeks, Mouth, Jaw, Chin, EarL, EarR). A region
 * may have several anchors (both cheeks, both jaw corners); the nearest one on screen wins.
 */
USTRUCT(BlueprintType)
struct FLyrisSculptAnchor
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sculpt")
	FName Region;

	/** Offset from the head bone in the preview's frame (X forward, Y = character's right, Z up), cm. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Sculpt")
	FVector Offset = FVector::ZeroVector;
};

/** One lighting mood: a key light, a fill and a rim, plus a light grade on the stage camera. */
USTRUCT(BlueprintType)
struct FLyrisCreatorLightingDef
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lighting")
	FLinearColor KeyColor = FLinearColor::White;

	/** Candelas. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lighting")
	float KeyIntensity = 800.f;

	/** Where the key light sits around the character, relative to its facing: yaw 0 = in front of the
	 *  character (camera side), 90 = the character's right, 180 = behind; pitch > 0 = above, so a low
	 *  pitch is a low sun. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lighting")
	FRotator KeyRotation = FRotator(25.f, 35.f, 0.f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lighting")
	FLinearColor FillColor = FLinearColor::White;

	/** Candelas. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lighting")
	float FillIntensity = 150.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lighting")
	FLinearColor RimColor = FLinearColor::White;

	/** Candelas. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lighting")
	float RimIntensity = 600.f;

	/** Camera white balance, Kelvin. 6500 is neutral; with UE's white balance a lower value gives a
	 *  cooler (bluer) image and a higher value a warmer one. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lighting")
	float WhiteTemp = 6500.f;

	/** Camera saturation multiplier (applied to all channels). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lighting")
	float Saturation = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Lighting")
	float Vignette = 0.4f;
};

/**
 * The stage the character creator runs on.
 *
 * Holds a preview character (spawned from PreviewCharacterClass, by default the game mode's default
 * pawn, or an existing pawn you assign), a camera on an orbit rig that eases between framings, and a
 * small three-light rig with lighting presets. Place one in a level (the dusk deck of the voyage), or let
 * the `Lyris.OpenCreator` console command spawn one near the player.
 *
 * The stage never edits the character's look itself: the UI talks to the preview's
 * ULyrisAppearanceComponent (see GetAppearanceComponent).
 */
UCLASS(Blueprintable)
class ALyrisCreatorStage : public AActor
{
	GENERATED_BODY()

public:
	ALyrisCreatorStage();

	// ------------------------------------------------------------------ Session

	/** Spawn the preview if needed, take over the player's camera and start ticking. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void BeginCreator(APlayerController* PlayerController);

	/** Give the camera back and, if the stage spawned the preview, remove it. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void EndCreator();

	/** The character being dressed. Spawns it on first call. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	APawn* GetPreviewCharacter();

	/** The preview's appearance component (added at runtime if its class has none). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	ULyrisAppearanceComponent* GetAppearanceComponent();

	// ------------------------------------------------------------------ Camera

	/** Ease to a framing. Resets the player's zoom and vertical orbit, keeps the turn. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void SetShot(ELyrisCreatorShot Shot);

	UFUNCTION(BlueprintPure, Category = "Lyris|Creator")
	ELyrisCreatorShot GetShot() const { return CurrentShot; }

	/** Orbit, degrees. Positive yaw swings the camera to the right around the character. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void AddOrbit(float YawDegrees, float PitchDegrees);

	/** Zoom in (positive steps) or out (negative). One wheel notch = one step. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void AddZoom(float Steps);

	/** Turn the camera to look at the face in profile (spec 2.1: when an ear or nose slider is dragged). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void LookAtProfile();

	// ------------------------------------------------------------------ Lighting

	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void SetLightingPreset(ELyrisCreatorLighting Preset);

	UFUNCTION(BlueprintPure, Category = "Lyris|Creator")
	ELyrisCreatorLighting GetLightingPreset() const { return CurrentLighting; }

	// ------------------------------------------------------------------ Preview hooks (stubs for now)

	/**
	 * Ask the preview to play an expression (spec 9.6: Calm, Bright, Laugh, Wry, Shy, Surprised, Sleepy,
	 * Determined) or a pose (Idle, Wave, HoldLantern, Sit, LeanRail, Windy, Walk).
	 * Calls a UFUNCTION named `LyrisPreviewExpression` / `LyrisPreviewPose` taking one FName on the
	 * preview character if it has one (a C++ UFUNCTION or a Blueprint custom event), then fires the
	 * Blueprint events below. Does nothing harmful if neither exists.
	 */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void PreviewExpression(FName ExpressionId);

	UFUNCTION(BlueprintCallable, Category = "Lyris|Creator")
	void PreviewPose(FName PoseId);

	UFUNCTION(BlueprintImplementableEvent, Category = "Lyris|Creator")
	void OnPreviewExpression(FName ExpressionId);

	UFUNCTION(BlueprintImplementableEvent, Category = "Lyris|Creator")
	void OnPreviewPose(FName PoseId);

	// ------------------------------------------------------------------ Face sculpting

	/** World positions of every sculpt anchor, paired with its region, for the UI to project to the screen. */
	void GetSculptAnchorsWorld(TArray<TPair<FName, FVector>>& OutAnchors) const;

	/** The camera the creator looks through (for projecting points to the screen). */
	UCameraComponent* GetCreatorCamera() const;

	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	// ------------------------------------------------------------------ Settings

	/** Class to spawn as the preview. Empty = the game mode's default pawn class. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator")
	TSubclassOf<APawn> PreviewCharacterClass;

	/** Use this pawn instead of spawning one (e.g. a mannequin already placed on the deck). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator")
	TObjectPtr<APawn> PreviewCharacter;

	/** Bone that face anchors and face shots are measured from. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator")
	FName HeadBone = TEXT("head");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator|Camera")
	TMap<ELyrisCreatorShot, FLyrisCreatorShotDef> Shots;

	/** Seconds the camera takes to ease between framings (spec: 0.6 s). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator|Camera")
	float ShotBlendTime = 0.6f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator|Camera")
	float MinZoom = 0.6f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator|Camera")
	float MaxZoom = 1.8f;

	/** Orbit pitch limits, degrees (spec: -15 to 30). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator|Camera")
	float MinPitch = -15.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator|Camera")
	float MaxPitch = 30.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator|Lighting")
	TMap<ELyrisCreatorLighting, FLyrisCreatorLightingDef> LightingPresets;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Creator|Sculpt")
	TArray<FLyrisSculptAnchor> SculptAnchors;

	// ------------------------------------------------------------------ Components

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> StageRoot;

	/** The creator camera. Placed in world space every tick by the orbit rig. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UCameraComponent> Camera;

	/** Lights are placed around the preview character every tick, so they follow it if it moves. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USpotLightComponent> KeyLight;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UPointLightComponent> FillLight;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USpotLightComponent> RimLight;

private:
	void SpawnPreviewIfNeeded();
	USkeletalMeshComponent* GetPreviewMesh() const;
	FVector ComputeFocus(const FLyrisCreatorShotDef& Shot) const;
	void UpdateCamera(float DeltaSeconds, bool bSnap);
	void CallPreviewFunction(FName FunctionName, FName Arg);
	void BuildDefaultPresets();
	void PlaceLights();
	void PlaceLightAround(USceneComponent* Light, float RelYaw, float Pitch, float Distance) const;

	UPROPERTY(Transient)
	TObjectPtr<APlayerController> ActivePlayer;

	UPROPERTY(Transient)
	TObjectPtr<AActor> PreviousViewTarget;

	bool bSpawnedPreview = false;
	bool bActive = false;

	ELyrisCreatorShot CurrentShot = ELyrisCreatorShot::Full;
	ELyrisCreatorLighting CurrentLighting = ELyrisCreatorLighting::DuskDeck;

	// Orbit state. User* values are what input asked for; Current* values ease toward the target.
	float UserYaw = 0.f;    // degrees around the character, 0 = in front of it
	float UserPitch = 0.f;  // added to the shot's pitch
	float Zoom = 1.f;       // distance multiplier
	float CurrentYaw = 0.f;
	float CurrentPitch = 5.f;
	float CurrentDistance = 260.f;
	float CurrentFov = 30.f;
	FVector CurrentFocus = FVector::ZeroVector;
};
