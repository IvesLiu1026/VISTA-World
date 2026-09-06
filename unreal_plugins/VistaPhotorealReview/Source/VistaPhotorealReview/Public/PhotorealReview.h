#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/HUD.h"
#include "PhotorealReview.generated.h"

class UCameraComponent;

UCLASS()
class VISTAPHOTOREALREVIEW_API APhotorealReviewCharacter : public ACharacter
{
    GENERATED_BODY()
public:
    APhotorealReviewCharacter();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
    UFUNCTION(Exec) void ReviewPortal(int32 Index);
    virtual void ReviewSnapshot();
protected:
    UPROPERTY() TObjectPtr<UCameraComponent> ReviewCamera;
    bool bFridgeOpen = false;
    bool bFreeFlight = false;
    bool bWholeHome = false;
    int32 CurrentRoom = 1;
    float DoorProgress = 0.f;
    void Forward(float Value);
    void Right(float Value);
    void Turn(float Value);
    void Look(float Value);
    void Rise(float Value);
    void ToggleFridge();
    void ToggleFlight();
    void ToggleCursor();
    void ViewOne();
    void ViewTwo();
    void ViewThree();
    void ViewFour();
    void ViewFive();
    void ViewSix();
    void ViewSeven();
    void ViewEight();
    void ViewNine();
    void AlternateView();
    void SetView(FVector Position, FRotator Rotation);
};

UCLASS()
class VISTAPHOTOREALREVIEW_API APhotorealReviewHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API APhotorealReviewGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    APhotorealReviewGameMode();
};
