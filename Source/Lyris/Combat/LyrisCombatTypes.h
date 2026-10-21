// Lyris combat: shared types. Spec: design/combat.md

#pragma once

#include "CoreMinimal.h"
#include "LyrisCombatTypes.generated.h"

class AActor;

/** The one attunement a character carries (changed only at a lit lamp, never mid-fight). */
UENUM(BlueprintType)
enum class ELyrisAttunement : uint8
{
	None,
	Lantern,  // light: cleanses mist
	Tide,     // water: soaks
	Gale,     // wind: gathers and lifts
	Ember     // fire: burns
};

/** One hit, from a weapon swing, an Art, a Surge or an enemy lunge. */
USTRUCT(BlueprintType)
struct FLyrisHit
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Combat")
	float Damage = 10.f;

	/** Poise damage. When an enemy's poise reaches zero it staggers. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Combat")
	float PoiseDamage = 10.f;

	/** World-space push applied to the target (cm/s). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Combat")
	FVector Knockback = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Combat")
	ELyrisAttunement Attunement = ELyrisAttunement::None;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Combat")
	TObjectPtr<AActor> Instigator = nullptr;
};

/** What a hit actually did. */
USTRUCT(BlueprintType)
struct FLyrisHitResult
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Combat")
	bool bLanded = false;

	UPROPERTY(BlueprintReadOnly, Category = "Combat")
	float DamageDealt = 0.f;

	/** Misted + Lantern: heavy damage, strips the mist. */
	UPROPERTY(BlueprintReadOnly, Category = "Combat")
	bool bDispel = false;

	UPROPERTY(BlueprintReadOnly, Category = "Combat")
	bool bStaggered = false;

	UPROPERTY(BlueprintReadOnly, Category = "Combat")
	bool bDefeated = false;

	/** The target dashed just before the hit: it misses and the target earns a Lull. */
	UPROPERTY(BlueprintReadOnly, Category = "Combat")
	bool bPerfectDodge = false;
};
