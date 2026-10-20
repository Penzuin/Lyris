// Lyris UI: shows the Breath ring beside the local player's head (T33).

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/LocalPlayerSubsystem.h"
#include "Tickable.h"
#include "LyrisBreathRingSubsystem.generated.h"

class APawn;
class SLyrisBreathRing;
class SWidget;
class UGameViewportClient;
class ULyrisStaminaComponent;

/**
 * One per local player. Whenever that player's pawn has a ULyrisStaminaComponent, this puts an
 * SLyrisBreathRing on the player's part of the game viewport, projects the head to the screen each
 * frame and feeds the ring the stamina state. It follows possession changes, late possession, map
 * travel and split screen by itself; nothing else has to call it.
 *
 * The ring hides with the HUD (AHUD::bShowHUD), so cinematics that hide the HUD hide it too.
 */
UCLASS()
class LYRIS_API ULyrisBreathRingSubsystem : public ULocalPlayerSubsystem, public FTickableGameObject
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	// FTickableGameObject
	virtual void Tick(float DeltaTime) override;
	virtual ETickableTickType GetTickableTickType() const override;
	virtual bool IsTickable() const override;
	virtual TStatId GetStatId() const override;
	virtual UWorld* GetTickableGameObjectWorld() const override;

	/** Turns off shake, sparks and pulses. Hook this to an accessibility option once one exists. */
	void SetReducedMotion(bool bInReducedMotion);

private:
	/** Starts showing the ring for this pawn's stamina component. */
	void Attach(APawn* Pawn, ULyrisStaminaComponent* Stamina, UGameViewportClient* Viewport);
	/** Removes the ring from the viewport and unbinds from the stamina component. */
	void Detach();

	/** Head position in world space: the `head` socket if the mesh has one, else top of the capsule. */
	static FVector GetHeadLocation(const APawn* Pawn);

	UFUNCTION()
	void HandleStaminaSpent(float Amount);

	TSharedPtr<SLyrisBreathRing> Ring;

	TWeakObjectPtr<APawn> AttachedPawn;
	TWeakObjectPtr<ULyrisStaminaComponent> AttachedStamina;
	TWeakObjectPtr<UGameViewportClient> AttachedViewport;
	/** The ring was put on this viewport layer; map travel clears viewport widgets, so we re-add. */
	TWeakPtr<SWidget> AddedWidget;

	bool bActive = false;
	bool bReducedMotion = false;
};
