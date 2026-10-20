// Lyris combat: health, poise and states (Misted) for anything that can be hit.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "LyrisCombatTypes.h"
#include "LyrisHealthComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FLyrisHitTakenSignature, const FLyrisHit&, Hit, const FLyrisHitResult&, Result);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FLyrisDefeatedSignature);

UCLASS(ClassGroup = (Lyris), meta = (BlueprintSpawnableComponent))
class LYRIS_API ULyrisHealthComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	ULyrisHealthComponent();

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Applies a hit, works out reactions, stagger and defeat. */
	UFUNCTION(BlueprintCallable, Category = "Combat")
	FLyrisHitResult ApplyHit(const FLyrisHit& Hit);

	UFUNCTION(BlueprintCallable, Category = "Combat")
	void RestoreFull();

	UFUNCTION(BlueprintPure, Category = "Combat")
	bool IsDefeated() const { return bDefeated; }

	UFUNCTION(BlueprintPure, Category = "Combat")
	bool IsMisted() const { return bMisted && MistReturnIn <= 0.f; }

	/** Player side: the dash's invulnerability window. Hits inside it miss. */
	void SetInvulnerableFor(float Seconds, bool bFromDodge);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	float MaxHealth = 100.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Combat")
	float Health = 100.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	float MaxPoise = 50.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Combat")
	float Poise = 50.f;

	/** Poise comes back this fast (per second) a moment after the last hit. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	float PoiseRegen = 20.f;

	/** Mist creatures are Misted: Lantern hits Dispel them. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	bool bMisted = false;

	/** After a Dispel, the mist creeps back over this many seconds. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	float MistReturnTime = 6.f;

	/** Seconds a stagger lasts. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	float StaggerTime = 1.4f;

	/** How light the owner is when knocked back (1 = full knockback). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Combat")
	float KnockbackScale = 1.f;

	UPROPERTY(BlueprintAssignable, Category = "Combat")
	FLyrisHitTakenSignature OnHitTaken;

	UPROPERTY(BlueprintAssignable, Category = "Combat")
	FLyrisDefeatedSignature OnDefeated;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Combat")
	float StaggeredFor = 0.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Combat")
	float MistReturnIn = 0.f;

private:
	float InvulnerableFor = 0.f;
	bool bInvulnerableFromDodge = false;
	float SinceLastHit = 100.f;
	bool bDefeated = false;
};
