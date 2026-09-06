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
    GetCharacterMovement()->StopMovementImmediately();
    SetActorLocation(P, false, nullptr, ETeleportType::TeleportPhysics);
    if (Controller) Controller->SetControlRotation(R);
}
void APhotorealReviewCharacter::ViewOne() { SetView(FVector(-210.f, 125.f, 90.f), FRotator(-5.f, -36.f, 0.f)); }
void APhotorealReviewCharacter::ViewTwo() { SetView(FVector(-205.f, 100.f, 90.f), FRotator(-15.f, -85.f, 0.f)); }
void APhotorealReviewCharacter::ViewThree() { SetView(FVector(-45.f, -70.f, 90.f), FRotator(-32.f, -82.f, 0.f)); }
void APhotorealReviewCharacter::ViewFour() { SetView(FVector(15.f, 160.f, 90.f), FRotator(-42.f, -153.f, 0.f)); }

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
    DrawRect(FLinearColor(0.025f, .04f, .03f, .78f), 22.f, 20.f, 630.f, 68.f);
    DrawText(TEXT("PHOTOREAL KITCHEN"), FLinearColor(.94f, .94f, .86f), 38.f, 29.f, nullptr, 1.5f);
    DrawText(TEXT("WASD + mouse  |  F fridge  |  1-4 views  |  C fly, Q/E down/up  |  Esc cursor"), FLinearColor(.85f, .87f, .82f), 38.f, 59.f, nullptr, 1.f);
}

APhotorealReviewGameMode::APhotorealReviewGameMode()
{
    DefaultPawnClass = APhotorealReviewCharacter::StaticClass();
    HUDClass = APhotorealReviewHUD::StaticClass();
}
