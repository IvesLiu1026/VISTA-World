#include "PhotorealReview.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Engine/Canvas.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Modules/ModuleManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "TimerManager.h"
#include "UnrealClient.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, VistaPhotorealReview)

APhotorealReviewCharacter::APhotorealReviewCharacter()
{
    PrimaryActorTick.bCanEverTick = true;
    GetCapsuleComponent()->InitCapsuleSize(30.f, 88.f);
    GetCharacterMovement()->MaxWalkSpeed = 175.f;
    GetCharacterMovement()->MaxFlySpeed = 165.f;
    GetCharacterMovement()->BrakingDecelerationWalking = 1200.f;
    GetCharacterMovement()->MaxStepHeight = 22.f;
    GetCharacterMovement()->JumpZVelocity = 280.f;
    bUseControllerRotationYaw = true;
    ReviewCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("ReviewCamera"));
    ReviewCamera->SetupAttachment(GetCapsuleComponent());
    ReviewCamera->SetRelativeLocation(FVector(0.f, 0.f, 70.f));
    ReviewCamera->bUsePawnControlRotation = true;
    ReviewCamera->SetFieldOfView(73.f);
}

void APhotorealReviewCharacter::BeginPlay()
{
    Super::BeginPlay();
    bWholeHome = FParse::Param(FCommandLine::Get(), TEXT("VistaWholeHome"));
    if (APlayerController* PC = Cast<APlayerController>(GetController()))
    {
        PC->SetInputMode(FInputModeGameOnly());
        PC->bShowMouseCursor = false;
    }
    FTimerHandle InitialView;
    GetWorldTimerManager().SetTimer(InitialView, this, &APhotorealReviewCharacter::ViewOne, .75f, false);
}

void APhotorealReviewCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    Input->BindAxis(TEXT("MoveForward"), this, &APhotorealReviewCharacter::Forward);
    Input->BindAxis(TEXT("MoveRight"), this, &APhotorealReviewCharacter::Right);
    Input->BindAxis(TEXT("Turn"), this, &APhotorealReviewCharacter::Turn);
    Input->BindAxis(TEXT("LookUp"), this, &APhotorealReviewCharacter::Look);
    Input->BindAxis(TEXT("Rise"), this, &APhotorealReviewCharacter::Rise);
    Input->BindKey(EKeys::F, IE_Pressed, this, &APhotorealReviewCharacter::ToggleFridge);
    Input->BindKey(EKeys::C, IE_Pressed, this, &APhotorealReviewCharacter::ToggleFlight);
    Input->BindKey(EKeys::Escape, IE_Pressed, this, &APhotorealReviewCharacter::ToggleCursor);
    Input->BindKey(EKeys::One, IE_Pressed, this, &APhotorealReviewCharacter::ViewOne);
    Input->BindKey(EKeys::Two, IE_Pressed, this, &APhotorealReviewCharacter::ViewTwo);
    Input->BindKey(EKeys::Three, IE_Pressed, this, &APhotorealReviewCharacter::ViewThree);
    Input->BindKey(EKeys::Four, IE_Pressed, this, &APhotorealReviewCharacter::ViewFour);
    Input->BindKey(EKeys::Five, IE_Pressed, this, &APhotorealReviewCharacter::ViewFive);
    Input->BindKey(EKeys::Six, IE_Pressed, this, &APhotorealReviewCharacter::ViewSix);
    Input->BindKey(EKeys::Seven, IE_Pressed, this, &APhotorealReviewCharacter::ViewSeven);
    Input->BindKey(EKeys::Eight, IE_Pressed, this, &APhotorealReviewCharacter::ViewEight);
    Input->BindKey(EKeys::Nine, IE_Pressed, this, &APhotorealReviewCharacter::ViewNine);
    Input->BindKey(EKeys::V, IE_Pressed, this, &APhotorealReviewCharacter::AlternateView);
    Input->BindKey(EKeys::F8, IE_Pressed, this, &APhotorealReviewCharacter::ReviewSnapshot);
}

void APhotorealReviewCharacter::Forward(float V)
{
    if (Controller && V != 0.f)
    {
        const FRotator R(0.f, Controller->GetControlRotation().Yaw, 0.f);
        AddMovementInput(FRotationMatrix(R).GetUnitAxis(EAxis::X), V);
    }
}
void APhotorealReviewCharacter::Right(float V)
{
    if (Controller && V != 0.f)
    {
        const FRotator R(0.f, Controller->GetControlRotation().Yaw, 0.f);
        AddMovementInput(FRotationMatrix(R).GetUnitAxis(EAxis::Y), V);
    }
}
void APhotorealReviewCharacter::Turn(float V) { AddControllerYawInput(V * .65f); }
void APhotorealReviewCharacter::Look(float V) { AddControllerPitchInput(V * .65f); }
void APhotorealReviewCharacter::Rise(float V)
{
    if (bFreeFlight) AddMovementInput(FVector::UpVector, V);
}
void APhotorealReviewCharacter::ToggleFridge() { bFridgeOpen = !bFridgeOpen; }
void APhotorealReviewCharacter::ToggleFlight()
{
    bFreeFlight = !bFreeFlight;
    GetCharacterMovement()->SetMovementMode(bFreeFlight ? MOVE_Flying : MOVE_Walking);
}
void APhotorealReviewCharacter::ToggleCursor()
{
    if (APlayerController* PC = Cast<APlayerController>(Controller))
    {
        PC->bShowMouseCursor = !PC->bShowMouseCursor;
        if (PC->bShowMouseCursor) PC->SetInputMode(FInputModeGameAndUI());
        else PC->SetInputMode(FInputModeGameOnly());
    }
}
void APhotorealReviewCharacter::SetView(FVector P, FRotator R)
{
    ReviewCamera->SetFieldOfView(73.f);
    GetCharacterMovement()->StopMovementImmediately();
    SetActorLocation(P, false, nullptr, ETeleportType::TeleportPhysics);
    if (Controller) Controller->SetControlRotation(R);
}
void APhotorealReviewCharacter::ViewOne()
{
    CurrentRoom = 1;
    if (bWholeHome) SetView(FVector(0.f, 350.f, 90.f), FRotator(-2.f, -90.f, 0.f));
    else SetView(FVector(-210.f, 125.f, 90.f), FRotator(-5.f, -36.f, 0.f));
}
void APhotorealReviewCharacter::ViewTwo()
{
    CurrentRoom = 2;
    if (bWholeHome) SetView(FVector(-198.f, 295.f, 90.f), FRotator(-9.f, -140.f, 0.f));
    else SetView(FVector(-205.f, 100.f, 90.f), FRotator(-15.f, -85.f, 0.f));
}
void APhotorealReviewCharacter::ViewThree()
{
    CurrentRoom = 3;
    if (bWholeHome) SetView(FVector(212.f, 368.f, 90.f), FRotator(-8.f, -53.f, 0.f));
    else SetView(FVector(-45.f, -70.f, 90.f), FRotator(-32.f, -82.f, 0.f));
}
void APhotorealReviewCharacter::ViewFour()
{
    CurrentRoom = 4;
    if (bWholeHome) SetView(FVector(-199.f, -139.f, 90.f), FRotator(-11.f, -155.f, 0.f));
    else SetView(FVector(15.f, 160.f, 90.f), FRotator(-42.f, -153.f, 0.f));
}
void APhotorealReviewCharacter::ViewFive()
{
    CurrentRoom = 5;
    if (bWholeHome)
    {
        SetView(FVector(208.f, -88.f, 90.f), FRotator(-9.f, -40.f, 0.f));
        ReviewCamera->SetFieldOfView(79.f);
    }
}
void APhotorealReviewCharacter::ViewSix()
{
    CurrentRoom = 6;
    if (bWholeHome)
    {
        SetView(FVector(18.f, -448.f, 90.f), FRotator(-9.f, -96.f, 0.f));
        ReviewCamera->SetFieldOfView(83.f);
    }
}
void APhotorealReviewCharacter::ViewSeven()
{
    if (bWholeHome) SetView(FVector(395.f, 230.f, 90.f), FRotator(-15.f, -139.5f, 0.f));
}
void APhotorealReviewCharacter::ViewEight()
{
    if (bWholeHome) SetView(FVector(347.5f, 137.5f, 90.f), FRotator(-32.f, -82.f, 0.f));
}
void APhotorealReviewCharacter::ViewNine()
{
    if (bWholeHome) SetView(FVector(415.f, 360.f, 90.f), FRotator(-42.f, -153.f, 0.f));
}
void APhotorealReviewCharacter::AlternateView()
{
    if (!bWholeHome) return;
    switch (CurrentRoom)
    {
        case 1: SetView(FVector(-68.f, 195.f, 90.f), FRotator(-14.f, 48.f, 0.f)); break;
        case 2: SetView(FVector(-585.f, 125.f, 90.f), FRotator(-12.f, 40.f, 0.f)); break;
        case 3: SetView(FVector(535.f, 330.f, 90.f), FRotator(-12.f, -150.f, 0.f)); break;
        case 4: SetView(FVector(-580.f, -294.f, 90.f), FRotator(-10.f, 55.f, 0.f)); break;
        case 5: SetView(FVector(557.f, -304.f, 90.f), FRotator(-12.f, 150.f, 0.f)); break;
        case 6: SetView(FVector(10.f, -735.f, 90.f), FRotator(-14.f, 93.f, 0.f)); ReviewCamera->SetFieldOfView(83.f); break;
        default: break;
    }
}
void APhotorealReviewCharacter::ReviewPortal(int32 Index)
{
    if (!bWholeHome) return;
    // Place the capsule on the hall side, then exercise real CharacterMovement
    // through the doorway with W. Bookmarks alone do not validate traversal.
    bFreeFlight = false;
    GetCharacterMovement()->SetMovementMode(MOVE_Walking);
    if (Index == 1) SetView(FVector(-65.f, 200.f, 90.f), FRotator(0.f, 180.f, 0.f));
    if (Index == 2) SetView(FVector(65.f, 200.f, 90.f), FRotator(0.f, 0.f, 0.f));
    if (Index == 3) SetView(FVector(-65.f, -200.f, 90.f), FRotator(0.f, 180.f, 0.f));
    if (Index == 4) SetView(FVector(65.f, -200.f, 90.f), FRotator(0.f, 0.f, 0.f));
    if (Index == 5) SetView(FVector(0.f, -315.f, 90.f), FRotator(0.f, -90.f, 0.f));
    if (Index == 6) SetView(FVector(0.f, 335.f, 90.f), FRotator(0.f, -90.f, 0.f));
}

void APhotorealReviewCharacter::ReviewSnapshot()
{
    UE_LOG(LogTemp, Display, TEXT("PR_REVIEW_STATE location=%s rotation=%s movement=%d door_progress=%.3f"),
        *GetActorLocation().ToString(), *GetControlRotation().ToString(),
        int32(GetCharacterMovement()->MovementMode), DoorProgress);
    FScreenshotRequest::RequestScreenshot(TEXT("PhotorealReview"), true, true);
}

void APhotorealReviewCharacter::Tick(float Dt)
{
    Super::Tick(Dt);
    DoorProgress = FMath::FInterpConstantTo(DoorProgress, bFridgeOpen ? 1.f : 0.f, Dt, .65f);
    const float Smooth = DoorProgress * DoorProgress * (3.f - 2.f * DoorProgress);
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        if (It->ActorHasTag(TEXT("PR_FridgeDoor_R"))) It->SetActorRotation(FRotator(0.f, -100.f * Smooth, 0.f));
        if (It->ActorHasTag(TEXT("PR_FridgeDoor_L"))) It->SetActorRotation(FRotator(0.f, 100.f * Smooth, 0.f));
    }
}

void APhotorealReviewHUD::DrawHUD()
{
    Super::DrawHUD();
    if (!Canvas) return;
    const bool Home = FParse::Param(FCommandLine::Get(), TEXT("VistaWholeHome"));
    DrawRect(FLinearColor(0.025f, .04f, .03f, .78f), 22.f, 20.f, Home ? 770.f : 630.f, Home ? 91.f : 68.f);
    DrawText(Home ? TEXT("VISTA  /  PHOTOREAL HOME") : TEXT("PHOTOREAL KITCHEN"), FLinearColor(.94f, .94f, .86f), 38.f, 29.f, nullptr, 1.5f);
    DrawText(Home ? TEXT("1 Entry   2 Living   3 Kitchen   4 Bedroom   5 Office   6 Bathroom") : TEXT("WASD + mouse  |  F fridge  |  1-4 views  |  C fly, Q/E down/up  |  Esc cursor"), FLinearColor(.85f, .87f, .82f), 38.f, 59.f, nullptr, 1.f);
    if (Home) DrawText(TEXT("WASD + mouse | V other angle | F fridge | 7-9 objects | C fly, Q/E down/up | Esc cursor"), FLinearColor(.77f, .80f, .74f), 38.f, 82.f, nullptr, 1.f);
}

APhotorealReviewGameMode::APhotorealReviewGameMode()
{
    DefaultPawnClass = APhotorealReviewCharacter::StaticClass();
    HUDClass = APhotorealReviewHUD::StaticClass();
}
