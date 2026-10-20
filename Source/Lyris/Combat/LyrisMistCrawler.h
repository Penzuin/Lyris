// Lyris combat: the mist crawler, the first enemy (design/combat.md section 6).
// Climbs out of the mist, scuttles in, glows before it lunges (the tell), and is Misted:
// a Lantern hit Dispels it. Placeholder body built from basic shapes.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "LyrisCombatTypes.h"
#include "LyrisMistCrawler.generated.h"

class ULyrisHealthComponent;
class UStaticMeshComponent;
class UPointLightComponent;
class UMaterialInstanceDynamic;

UCLASS()
class LYRIS_API ALyrisMistCrawler : public ACharacter
{
	GENERATED_BODY()

public:
	ALyrisMistCrawler();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Combat")
	TObjectPtr<ULyrisHealthComponent> Health;

	UPROPERTY(EditAnywhere, Category = "Combat")
	float SightRange = 1600.f;

	UPROPERTY(EditAnywhere, Category = "Combat")
	float LungeRange = 330.f;

	UPROPERTY(EditAnywhere, Category = "Combat")
	float TellTime = 0.65f;

	UPROPERTY(EditAnywhere, Category = "Combat")
	float LungeDamage = 14.f;

	/** Seconds spent climbing out of the ground when spawned. */
	UPROPERTY(EditAnywhere, Category = "Combat")
	float EmergeTime = 0.9f;

private:
	enum class EState : uint8 { Emerging, Idle, Approach, Tell, Lunge, Recover, Staggered, Dissolving };

	UPROPERTY(VisibleAnywhere, Category = "Body")
	TObjectPtr<USceneComponent> Body;

	UPROPERTY(VisibleAnywhere, Category = "Body")
	TObjectPtr<UStaticMeshComponent> Shell;

	UPROPERTY(VisibleAnywhere, Category = "Body")
	TObjectPtr<UStaticMeshComponent> MistCloak;

	UPROPERTY(VisibleAnywhere, Category = "Body")
	TObjectPtr<UStaticMeshComponent> EyeLeft;

	UPROPERTY(VisibleAnywhere, Category = "Body")
	TObjectPtr<UStaticMeshComponent> EyeRight;

	UPROPERTY(VisibleAnywhere, Category = "Body")
	TArray<TObjectPtr<UStaticMeshComponent>> Legs;

	UPROPERTY(VisibleAnywhere, Category = "Body")
	TObjectPtr<UPointLightComponent> EyeGlow;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> ShellMat;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> CloakMat;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> EyeMat;

	EState State = EState::Emerging;
	float StateTime = 0.f;
	bool bLungeHitDone = false;
	float Clock = 0.f;

	UStaticMeshComponent* MakePart(FName Name, class UStaticMesh* Mesh, FVector Location, FVector Scale);
	APawn* FindPlayer() const;
	void SetState(EState NewState);
	void UpdateLooks(float DeltaSeconds);

	UFUNCTION()
	void HandleHitTaken(const FLyrisHit& Hit, const FLyrisHitResult& Result);

	UFUNCTION()
	void HandleDefeated();
};
