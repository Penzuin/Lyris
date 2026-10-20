// Lyris combat: the player's moveset, hand-to-hand for now (design/combat.md section 10).
//
// One character, no swapping, no abilities yet. Left click: jab, cross, hook, front kick
// (a 4-hit combo). Hold left click: spinning roundhouse kick. Left click in the air: stomp
// kick. Right click / Shift: dash, with a perfect-dodge "Lull".
//
// Until task C4 adds Enhanced Input actions, this reads keys directly, and only while a foe
// is near (fists stay down otherwise).

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

	// ---- tuning
	UPROPERTY(EditAnywhere, Category = "Combat|Stamina")
	float MaxStamina = 100.f;

	UPROPERTY(EditAnywhere, Category = "Combat|Stamina")
	float StaminaRegen = 30.f;

	UPROPERTY(EditAnywhere, Category = "Combat|Stamina")
	float DashCost = 18.f;

	UPROPERTY(EditAnywhere, Category = "Combat|Stamina")
	float ChargedCost = 25.f;

	/** Fists come up only when a foe is this close. */
	UPROPERTY(EditAnywhere, Category = "Combat")
	float EngageRange = 2500.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Combat")
	float Stamina = 100.f;

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

	enum class EAction : uint8 { None, Attack, Charged, Plunge, Dash };

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
