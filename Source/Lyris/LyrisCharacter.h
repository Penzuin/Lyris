// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "Logging/LogMacros.h"
#include "LyrisCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;
class ULyrisSwimComponent;
class UInputAction;
class UInputMappingContext;
class ULyrisStaminaComponent;
class ULyrisCharacterMovementComponent;
struct FInputActionValue;

DECLARE_LOG_CATEGORY_EXTERN(LogTemplateCharacter, Log, All);

/**
 *  A simple player-controllable third person character
 *  Implements a controllable orbiting camera
 */
UCLASS(abstract)
class ALyrisCharacter : public ACharacter
{
	GENERATED_BODY()

	/** Camera boom positioning the camera behind the character */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components", meta = (AllowPrivateAccess = "true"))
	USpringArmComponent* CameraBoom;

	/** Follow camera */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components", meta = (AllowPrivateAccess = "true"))
	UCameraComponent* FollowCamera;

	/** Floating and swimming in the sea (T20) */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components", meta = (AllowPrivateAccess = "true"))
	TObjectPtr<ULyrisSwimComponent> SwimComponent;

	/** Breath: the stamina pool sprinting and climbing draw from (T32) */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components", meta = (AllowPrivateAccess = "true"))
	TObjectPtr<ULyrisStaminaComponent> Stamina;
	
protected:

	/** Jump Input Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* JumpAction;

	/** Move Input Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* MoveAction;

	/** Look Input Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* LookAction;

	/** Mouse Look Input Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* MouseLookAction;

	/** Hold to sprint. Left empty, a Left Shift action is made at runtime (T32) */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* SprintAction;

	/** Toggle sprint (gamepad left stick click). Left empty, one is made at runtime (T32) */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* SprintToggleAction;

	/** Mapping for the sprint actions. Left empty, one is made at runtime (T32) */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputMappingContext* MovementMappingContext;

public:

	/** Constructor: swaps in the Lyris movement component (sprint, jump feel, climbing; T32) */
	ALyrisCharacter(const FObjectInitializer& ObjectInitializer);	

protected:

	/** Initialize input action bindings */
	virtual void SetupPlayerInputComponent(class UInputComponent* PlayerInputComponent) override;

protected:

	/** Called for movement input */
	void Move(const FInputActionValue& Value);

	/** Called for looking input */
	void Look(const FInputActionValue& Value);

public:

	/** Handles move inputs from either controls or UI interfaces */
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoMove(float Right, float Forward);

	/** Handles look inputs from either controls or UI interfaces */
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoLook(float Yaw, float Pitch);

	/** Handles jump pressed inputs from either controls or UI interfaces */
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoJumpStart();

	/** Handles jump pressed inputs from either controls or UI interfaces */
	UFUNCTION(BlueprintCallable, Category="Input")
	virtual void DoJumpEnd();

public:

	/** Returns CameraBoom subobject **/
	FORCEINLINE class USpringArmComponent* GetCameraBoom() const { return CameraBoom; }

	/** Returns FollowCamera subobject **/
	FORCEINLINE class UCameraComponent* GetFollowCamera() const { return FollowCamera; }

	/** Returns the swim component **/
	FORCEINLINE ULyrisSwimComponent* GetSwimComponent() const { return SwimComponent; }

	/** While swimming, Jump kicks up or climbs out instead of jumping */
	virtual void Jump() override;

	/** Releasing jump cuts a jump short (T32) */
	virtual void StopJumping() override;

	/** Coming back from the boat: add the sprint mapping again (T32) */
	virtual void PawnClientRestart() override;

	/** Switches the gamepad sprint toggle off when you stop or run out of Breath (T32) */
	virtual void Tick(float DeltaSeconds) override;

	/** Returns the Breath stamina pool **/
	FORCEINLINE ULyrisStaminaComponent* GetStamina() const { return Stamina; }

	/** Returns the Lyris movement component **/
	ULyrisCharacterMovementComponent* GetLyrisMovement() const;

protected:

	/** Sprint input handlers (T32) */
	void SprintStarted(const FInputActionValue& Value);
	void SprintCompleted(const FInputActionValue& Value);
	void SprintToggled(const FInputActionValue& Value);

	/** True while the gamepad sprint toggle is on; cleared when you stop moving or run out of Breath */
	bool bSprintToggled = false;
};

