#include "VistaAlpineProof.h"
#include "VistaVillaCharacter.h"
#include "HomeActionsJson.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"
#if WITH_EDITOR
#include "ShaderCompiler.h"
#endif
using namespace HomeJson;

struct FAlpineProof
{
    int32 Stage=-1,Shot=0;float Time=0;bool Done=false,Pending=false,Jumped=false,Opened=false;
    FString Dir;TWeakObjectPtr<ACameraActor> Camera;
    TArray<TWeakObjectPtr<ACameraActor>> Views;
    TArray<TSharedPtr<FJsonValue>> Frames,Captures;
    void Tick(AVistaVillaCharacter* C,float Dt)
    {
        if (Done || C->Clock<5) return;
#if WITH_EDITOR
        if (Stage<0 && GShaderCompilingManager && GShaderCompilingManager->IsCompiling()) return;
#endif
        auto* PC=Cast<APlayerController>(C->Controller);Time+=Dt;
        if (Stage<0)
        {
            Stage=0;Time=0;Dir=FPaths::ProjectSavedDir()/TEXT("AlpineProof");
            check(!IFileManager::Get().DirectoryExists(*Dir));IFileManager::Get().MakeDirectory(*Dir,true);
            Camera=C->GetWorld()->SpawnActor<ACameraActor>();Camera->GetCameraComponent()->SetFieldOfView(65);
            for (TActorIterator<ACameraActor> It(C->GetWorld());It;++It) if (It->ActorHasTag(TEXT("AlpineView"))) Views.Add(*It);
            Views.Sort([](const auto& A,const auto& B){return A->GetName()<B->GetName();});
            // One initial placement inside the dining room. All subsequent
            // door/terrace/run/jump movement uses the character's collision.
            C->SetActorLocationAndRotation(FVector(439.5,-1110,83),FRotator(0,-90,0),false,nullptr,ETeleportType::TeleportPhysics);
            C->GetCharacterMovement()->StopMovementImmediately();C->bFeetReady=false;
            C->EmbodiedView(1);C->EmbodiedCamera(-10,-90);PC->SetViewTarget(Camera.Get());
        }
        const float Duration=Stage==0?2.f:Stage==1?5.f:Stage==2?7.f:Stage==3?2.f:Stage==4?2.f:2.f;
        if (Time>Duration)
        {
            ++Stage;Time=0;Shot=0;
            if (Stage==2) C->StartRunning();
            if (Stage==3) {C->StopRunning();C->GetCharacterMovement()->StopMovementImmediately();C->EmbodiedView(0);C->EmbodiedCamera(-83,C->GetActorRotation().Yaw);PC->SetViewTarget(C);}
            if (Stage==4) C->EmbodiedCamera(-65,C->GetActorRotation().Yaw-80);
            if (Stage>=5)
            {
                const int32 I=Stage-5;
                if (!Views.IsValidIndex(I))
                {
                    auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),TEXT("vista.alpine-proof/v1"));
                    O->SetArrayField(TEXT("frames"),Frames);O->SetArrayField(TEXT("captures"),Captures);
                    O->SetBoolField(TEXT("door_interaction_accepted"),Opened);O->SetBoolField(TEXT("jump_requested"),Jumped);
                    O->SetStringField(TEXT("status"),TEXT("captured_pending_validation"));
                    FFileHelper::SaveStringToFile(Encode(O),*(Dir/TEXT("proof.json")));Done=true;FGenericPlatformMisc::RequestExit(false);return;
                }
                PC->SetViewTarget(Views[I].Get());
            }
        }
        if (Stage==0 && Time>.5f && !Opened) {Opened=C->TryGardenDoor();}
        if (Stage==1) C->AddMovementInput(FVector(0,-1,0),1);
        if (Stage==2)
        {
            const FVector Direction=FVector(-1,-.3f,0).GetSafeNormal();C->AddMovementInput(Direction,1);
            C->Controller->SetControlRotation(FRotator(-12,Direction.Rotation().Yaw,0));
            if (Time>1.8f && !Jumped) {C->StartAlpineJump();Jumped=true;}
            if (Time>2.05f) C->StopJumping();
        }
        if (Stage<3)
        {
            const FVector At=C->GetActorLocation(),Eye=At+FVector(235,265,90);
            Camera->SetActorLocation(Eye);Camera->SetActorRotation((At+FVector(0,0,-8)-Eye).Rotation());
        }
        Pending=true;
    }
    void Capture(AVistaVillaCharacter* C)
    {
        if (!Pending || Done) return;Pending=false;
        auto O=MakeShared<FJsonObject>();O->SetNumberField(TEXT("stage"),Stage);O->SetNumberField(TEXT("time_s"),C->Clock);
        O->SetNumberField(TEXT("stage_time_s"),Time);O->SetArrayField(TEXT("position_cm"),Values(C->GetActorLocation()));
        O->SetArrayField(TEXT("velocity_cm_s"),Values(C->GetVelocity()));O->SetStringField(TEXT("clip"),C->AlpineMotionName);
        O->SetBoolField(TEXT("falling"),C->GetCharacterMovement()->IsFalling());O->SetBoolField(TEXT("ground_ik"),C->UsesGroundFootIK());
        O->SetNumberField(TEXT("door_alpha"),C->GardenAlpha);O->SetNumberField(TEXT("ready_hands"),C->FirstPersonRestAlpha);
        auto Joints=MakeShared<FJsonObject>();
        for (const TCHAR* N:{TEXT("pelvis"),TEXT("upperarm_l"),TEXT("lowerarm_l"),TEXT("hand_l"),TEXT("upperarm_r"),TEXT("lowerarm_r"),TEXT("hand_r"),TEXT("thigh_l"),TEXT("calf_l"),TEXT("foot_l"),TEXT("thigh_r"),TEXT("calf_r"),TEXT("foot_r")})
            Joints->SetArrayField(N,Values(C->GetMesh()->GetSocketLocation(N)));
        O->SetObjectField(TEXT("joints"),Joints);Frames.Add(MakeShared<FJsonValueObject>(O));
        const bool Air=C->GetCharacterMovement()->IsFalling();
        if ((Shot==0 && Time>.8f) || (Stage==2 && ((Shot==1 && Air) || (Shot==2 && !Air && Time>2.8f))))
        {
            const FString Name=FString::Printf(TEXT("%02d_%02d"),Stage,Shot++);auto R=MakeShared<FJsonObject>();
            R->SetStringField(TEXT("file"),Name+TEXT(".png"));R->SetNumberField(TEXT("stage"),Stage);R->SetNumberField(TEXT("time_s"),C->Clock);
            Captures.Add(MakeShared<FJsonValueObject>(R));FScreenshotRequest::RequestScreenshot(Dir/(Name+TEXT(".png")),false,false);
        }
    }
};
namespace {TUniquePtr<FAlpineProof> AlpineProof;}
void TickAlpineProof(AVistaVillaCharacter* C,float Dt)
{
    if (!FParse::Param(FCommandLine::Get(),TEXT("VistaAlpineProof"))) return;
    if (!AlpineProof) AlpineProof=MakeUnique<FAlpineProof>();AlpineProof->Tick(C,Dt);
}
void CaptureAlpineProof(AVistaVillaCharacter* C) {if (AlpineProof) AlpineProof->Capture(C);}
