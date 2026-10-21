// Lyris player: Breath, the one stamina pool that sprinting and climbing draw from.
// Walking, jumping and swimming are free. Running dry leaves you Winded (no sprint, no climb,
// you let go of walls) until Breath refills to the Winded threshold. Never hurts you.
// Tuning lives in Project Settings > Game > Lyris Movement (ULyrisMovementSettings).

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "LyrisStaminaComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_FourParams(FLyrisStaminaChanged, float, Current, float, Max, float, Bonus, bool, bWinded);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FLyrisStaminaSpent, float, Amount);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FLyrisStaminaDenied, float, Amount);

/**
 * Server-authoritative Breath pool. Current, Max, Bonus and bWinded replicate; on clients the
 * OnRep fires OnStaminaChanged. The owning client also runs the same drain and refill locally
 * (driven by ULyrisCharacterMovementComponent) so its ring reacts at once; the server value wins
 * whenever it arrives.
 *
 * Bonus Breath (food, tea) sits on top of the main pool and is always spent first.
 */
UCLASS(ClassGroup = (Lyris), meta = (BlueprintSpawnableComponent))
class LYRIS_API ULyrisStaminaComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	ULyrisStaminaComponent();

	// ---- Reading ----

	/** Breath in the main pool, 0 to Max. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Breath")
	float GetCurrent() const { return Current; }

	/** Size of the main pool (100 to start, upgradeable). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Breath")
	float GetMax() const { return Max; }

	/** Bonus Breath from food or tea, spent before the main pool. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Breath")
	float GetBonus() const { return Bonus; }

	/** True after running dry, until Breath refills to GetWindedThreshold(). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Breath")
	bool IsWinded() const { return bWinded; }

	/** Breath at which Winded clears (35 with default tuning). */
	UFUNCTION(BlueprintPure, Category = "Lyris|Breath")
	float GetWindedThreshold() const;

	/** Seconds since Breath was last spent or drained. Refill starts after the recovery delay. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Breath")
	float GetTimeSinceLastSpend() const;

	/** Breath the next action would cost, for the HUD preview: the climb leap cost while climbing, else 0. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Breath")
	float GetPreviewCost() const { return PreviewCost; }

	/** True if not Winded and main pool + bonus covers Amount. */
	UFUNCTION(BlueprintPure, Category = "Lyris|Breath")
	bool CanAfford(float Amount) const;

	// ---- Changing ----

	/** All-or-nothing spend for one-off actions (leap, wall kick, sprint jump). Returns false and spends nothing if it can't afford it. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Breath")
	bool TrySpend(float Amount);

	/** Continuous drain (sprint, climb). Takes what is there, clamps at 0 and may leave you Winded. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Breath")
	void Drain(float Amount);

	/** Adds bonus Breath (food, tea), capped by MaxBonusBreath. Also starts refilling at once. Call on the server. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Breath")
	void AddBonus(float Amount);

	/** Sets the HUD preview cost (the movement component does this when you grab or leave a wall). */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Breath")
	void SetPreviewCost(float Cost);

	/** Upgrades the pool size (clamped to MaxBreathCap). Call on the server. */
	UFUNCTION(BlueprintCallable, Category = "Lyris|Breath")
	void SetMax(float NewMax, bool bRefill = true);

	// ---- Events ----

	/** Fires whenever Current, Max, Bonus or Winded change (also on clients via replication). */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Breath")
	FLyrisStaminaChanged OnStaminaChanged;

	/** Fires on every spend: once for TrySpend, every frame with a small amount for Drain. */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Breath")
	FLyrisStaminaSpent OnStaminaSpent;

	/** Fires when TrySpend is refused (not enough Breath, or Winded). Lets the HUD flash. */
	UPROPERTY(BlueprintAssignable, Category = "Lyris|Breath")
	FLyrisStaminaDenied OnStaminaDenied;

	// ---- UActorComponent ----
	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:
	UPROPERTY(ReplicatedUsing = OnRep_Current, VisibleInstanceOnly, Category = "Lyris|Breath")
	float Current = 100.f;

	UPROPERTY(ReplicatedUsing = OnRep_Breath, VisibleInstanceOnly, Category = "Lyris|Breath")
	float Max = 100.f;

	UPROPERTY(ReplicatedUsing = OnRep_Breath, VisibleInstanceOnly, Category = "Lyris|Breath")
	float Bonus = 0.f;

	UPROPERTY(ReplicatedUsing = OnRep_Breath, VisibleInstanceOnly, Category = "Lyris|Breath")
	bool bWinded = false;

	UFUNCTION()
	void OnRep_Current(float OldCurrent);

	UFUNCTION()
	void OnRep_Breath();

private:
	/** World time of the last spend. Starts far in the past so a fresh pool counts as rested. */
	double LastSpendTime = -1000.0;

	float PreviewCost = 0.f;

	double Now() const;
	void SpendInternal(float Amount);
	void BroadcastChanged();
};
