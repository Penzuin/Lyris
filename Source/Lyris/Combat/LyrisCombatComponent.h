// Lyris combat: the player's moveset (design/combat.md section 3).
//
// One character, no swapping. Left click: 4-hit combo (hold for a charged attack, press
// while falling for a plunge). Right click / Shift: dash, with a perfect-dodge "Lull".
// E: Art (Flare). Q: Surge (Lighthouse Beam). Attunement: Lantern, so it Dispels Misted foes.
//
// Until task C4 adds Enhanced Input actions, this reads keys directly, and only while a foe
// is near (weapons stay sheathed otherwise, so E still boards the boat at the dock).

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "LyrisCombatTypes.h"
#include "LyrisCombatComponent.generated.h"

class ACharacter;
class APlayerController;
class UAnimSequenceBase;
class ULyrisHealthComponent;

UCLASS(ClassGroup = (Lyris), meta = (BlueprintSpawnableComponent))
class LYRIS_API ULyrisCombatComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	ULyrisCombatComponent();

	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Where defeat sends you (the dock until lamps exist, task C7). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Combat")
	FVector RespawnLocation = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Combat")
	ELyrisAttunement Attunement = ELyrisAttunement::Lantern;

	// ---- tuning
	UPROPERTY(EditAnywhere, Category = "Combat|Stamina")
	float MaxStamina = 100.f;

	UPROPERTY(EditAnywhere, Category = "Combat|Stamina")
	float StaminaRegen = 30.f;

	UPROPERTY(EditAnywhere, Category = "Combat|Stamina")
	float DashCost = 18.f;

	UPROPERTY(EditAnywhere, Category = "Combat|Stamina")
	float ChargedCost = 25.f;

	UPROPERTY(EditAnywhere, Category = "Combat|Art")
	float ArtCooldown = 6.f;

	UPROPERTY(EditAnywhere, Category = "Combat|Surge")
	float SurgeEnergyPerHit = 7.f;

	/** Weapons are drawn only when a foe is this close. */
	UPROPERTY(EditAnywhere, Category = "Combat")
	float EngageRange = 2500.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Combat")
	float Stamina = 100.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Combat")
	float SurgeEnergy = 0.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Combat")
	float ArtReadyIn = 0.f;

	UFUNCTION(BlueprintPure, Category = "Combat")
	ULyrisHealthComponent* GetHealth() const { return Health; }

private:
	struct FComboStep
	{
		float Damage;
		float Poise;
		float Knockback;
		float Reach;      // cm in front of the character
		float Radius;     // cm
		float HitDelay;   // seconds from the start of the swing to the hit
		float Duration;   // seconds the swing lasts
		int32 AnimIndex;
	};

	enum class EAction : uint8 { None, Attack, Charged, Plunge, Dash, Art, Surge };

	UPROPERTY()
	TObjectPtr<ULyrisHealthComponent> Health;

	UPROPERTY()
	TArray<TObjectPtr<UAnimSequenceBase>> AttackAnims;

	UPROPERTY()
	TObjectPtr<UAnimSequenceBase> ChargedAnim;

	TArray<FComboStep> Combo;

	EAction Action = EAction::None;
	float ActionTime = 0.f;
	bool bActionHitDone = false;
	int32 ComboIndex = -1;
	float SinceComboStep = 100.f;
	bool bComboQueued = false;
	float AttackHeldFor = 0.f;
	float SinceStaminaUse = 100.f;
	bool bWasFalling = false;
	bool bEngaged = false;

	// Hit-stop and Lull use real time so they work while time itself is slowed.
	double HitStopEndReal = 0.0;
	double LullEndReal = 0.0;
	TArray<TWeakObjectPtr<AActor>> HitStopped;

	ACharacter* OwnerCharacter() const;
	APlayerController* PlayerController() const;
	double RealNow() const;

	void ReadInput(APlayerController* PC, float DeltaTime);
	void TickAction(float DeltaTime);

	void StartComboStep();
	void StartCharged();
	void StartPlunge();
	void StartDash();
	void StartArt();
	void StartSurge();

	AActor* FindSoftTarget(float Range, float ConeDegrees) const;
	void FaceTarget(AActor* Target);
	bool AnyFoeWithin(float Range) const;

	/** Hits every foe in a sphere; returns how many were struck. */
	int32 HitArea(const FVector& Centre, float Radius, const FLyrisHit& Template, bool bKnockOutward);
	void OnHitLanded(AActor* Target, const FLyrisHitResult& Result);
	void StartHitStop(AActor* Target, float Seconds);
	void UpdateTimeEffects();

	void PlayAnim(UAnimSequenceBase* Anim, float Rate = 1.f);

	UFUNCTION()
	void HandleHitTaken(const FLyrisHit& Hit, const FLyrisHitResult& Result);

	UFUNCTION()
	void HandleDefeated();

	void ShowStatus() const;
};
