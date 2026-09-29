// Clean synchronized evidence: the ego image is a policy input; exo is review only.
#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "Async/Async.h"
#include "Camera/CameraComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "ImageUtils.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"

using namespace HomeJson;

void AHomeActionsCharacter::CaptureResearchViews()
{
    const double Now = FPlatformTime::Seconds();
    if (Now < ResearchNextCapture || BridgeDir.IsEmpty() ||
        (ResearchCaptureWrite.IsValid() && !ResearchCaptureWrite.IsReady())) return;
    ResearchNextCapture = Now + .5; // Two evidence pairs/second, independent of game FPS.
    const FDateTime Lease = IFileManager::Get().GetTimeStamp(*(BridgeDir / TEXT("research.enabled")));
    if (Lease == FDateTime::MinValue() || (FDateTime::UtcNow() - Lease).GetTotalSeconds() > 8) return;

    constexpr int32 Width = 960, Height = 540;
    if (!ResearchEgo)
    {
        // The independent observer must not inherit the wearer's OwnerNoSee rules.
        ResearchObserver = GetWorld()->SpawnActor<AActor>();
        if (!ResearchObserver) return;
        ResearchEgo = NewObject<USceneCaptureComponent2D>(this);
        ResearchExo = NewObject<USceneCaptureComponent2D>(ResearchObserver);
        ResearchEgoTarget = NewObject<UTextureRenderTarget2D>(this);
        ResearchExoTarget = NewObject<UTextureRenderTarget2D>(this);
        ResearchEgoTarget->InitCustomFormat(Width, Height, PF_B8G8R8A8, false);
        ResearchExoTarget->InitCustomFormat(Width, Height, PF_B8G8R8A8, false);
        for (auto* Capture : {ResearchEgo.Get(), ResearchExo.Get()})
        {
            Capture->bCaptureEveryFrame = false;
            Capture->bCaptureOnMovement = false;
            Capture->bAlwaysPersistRenderingState = true;
            Capture->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
            Capture->FOVAngle = 78;
            Capture->ShowFlags.SetTemporalAA(true);
            // UE disables Lumen in scene captures by default. Keep the same
            // lighting method as the playable view; otherwise evidence images
            // have unoccluded skylight, washed-out clothes and missing reflections.
            Capture->PostProcessSettings.bOverride_DynamicGlobalIlluminationMethod = true;
            Capture->PostProcessSettings.DynamicGlobalIlluminationMethod = EDynamicGlobalIlluminationMethod::Lumen;
            Capture->PostProcessSettings.bOverride_ReflectionMethod = true;
            Capture->PostProcessSettings.ReflectionMethod = EReflectionMethod::Lumen;
            Capture->RegisterComponent();
        }
        ResearchEgo->TextureTarget = ResearchEgoTarget;
        ResearchExo->TextureTarget = ResearchExoTarget;
        ResearchEgo->HideComponent(GetMesh());
        ResearchExo->HideComponent(OwnerBody);
    }

    ResearchEgo->SetWorldLocationAndRotation(ReviewCamera->GetComponentLocation(), GetControlRotation());
    ResearchExo->SetWorldLocationAndRotation(FollowCamera->GetComponentLocation(), FollowCamera->GetComponentRotation());
    // In third-person review the headless first-person body is otherwise hidden.
    const bool BodyVisible = OwnerBody && OwnerBody->IsVisible();
    if (OwnerBody) OwnerBody->SetVisibility(true);
    ResearchEgo->CaptureScene();
    TArray<FColor> EgoPixels, ExoPixels;
    const bool EgoOK = ResearchEgoTarget->GameThread_GetRenderTargetResource()->ReadPixels(EgoPixels);
    if (OwnerBody) OwnerBody->SetVisibility(BodyVisible);
    ResearchExo->CaptureScene();
    const bool ExoOK = ResearchExoTarget->GameThread_GetRenderTargetResource()->ReadPixels(ExoPixels);
    if (!EgoOK || !ExoOK || EgoPixels.Num() != Width * Height || ExoPixels.Num() != Width * Height) return;

    const FString Folder = BridgeDir / TEXT("research_frames");
    IFileManager::Get().MakeDirectory(*Folder, true);
    // A bounded ring. Consumers archive verified bytes, never references to mutable slots.
    const uint64 Serial = ++ResearchCaptureSerial;
    const FString EgoFile = FString::Printf(TEXT("ego_%02llu.png"), Serial % 16);
    const FString ExoFile = FString::Printf(TEXT("exo_%02llu.png"), Serial % 16);
    auto Pair = MakeShared<FJsonObject>();
    Pair->SetStringField(TEXT("schema"), TEXT("vista.research-capture/v1"));
    Pair->SetStringField(TEXT("session_id"), SessionId);
    Pair->SetNumberField(TEXT("scene_epoch"), SceneEpoch);
    Pair->SetNumberField(TEXT("clock_s"), SceneClock);
    Pair->SetStringField(TEXT("capture_id"), FString::Printf(TEXT("%s_%d_%llu"), *SessionId, SceneEpoch, Serial));
    Pair->SetNumberField(TEXT("engine_frame"), GFrameCounter);
    Pair->SetNumberField(TEXT("width"), Width);
    Pair->SetNumberField(TEXT("height"), Height);
    Pair->SetStringField(TEXT("ego_file"), EgoFile);
    Pair->SetStringField(TEXT("exo_file"), ExoFile);
    Pair->SetNumberField(TEXT("readback_ms"), (FPlatformTime::Seconds() - Now) * 1000);
    // Compression and disk I/O must not stall walking/animation on the game thread.
    const FString Manifest = Encode(Pair);
    ResearchCaptureWrite = Async(EAsyncExecution::ThreadPool,
        [Folder, EgoFile, ExoFile, Manifest, Ego = MoveTemp(EgoPixels), Exo = MoveTemp(ExoPixels)]()
        {
            TArray64<uint8> EgoPNG, ExoPNG;
            FImageUtils::PNGCompressImageArray(Width, Height, Ego, EgoPNG);
            FImageUtils::PNGCompressImageArray(Width, Height, Exo, ExoPNG);
            if (!FFileHelper::SaveArrayToFile(EgoPNG, *(Folder / (EgoFile + TEXT(".tmp")))) ||
                !FFileHelper::SaveArrayToFile(ExoPNG, *(Folder / (ExoFile + TEXT(".tmp"))))) return;
            if (!IFileManager::Get().Move(*(Folder / EgoFile), *(Folder / (EgoFile + TEXT(".tmp"))), true) ||
                !IFileManager::Get().Move(*(Folder / ExoFile), *(Folder / (ExoFile + TEXT(".tmp"))), true)) return;
            AtomicSave(Folder / TEXT("latest.json"), Manifest);
        });
}
