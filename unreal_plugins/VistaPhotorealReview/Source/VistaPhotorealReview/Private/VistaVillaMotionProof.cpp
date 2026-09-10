#include "VistaVillaMotionProof.h"
#include "VistaVillaCharacter.h"
#include "HomeActionsJson.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
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
namespace
{
TSharedRef<FJsonObject> Transform(const FTransform& T)
{
    auto O=MakeShared<FJsonObject>();O->SetArrayField(TEXT("translation_cm"),Values(T.GetTranslation()));
    O->SetArrayField(TEXT("scale"),Values(T.GetScale3D()));const auto Q=T.GetRotation();
    TArray<TSharedPtr<FJsonValue>> R;for (double V:{Q.X,Q.Y,Q.Z,Q.W}) R.Add(MakeShared<FJsonValueNumber>(V));
    O->SetArrayField(TEXT("rotation_xyzw"),R);return O;
}
struct FCase {const TCHAR* Name;float Pitch,Yaw,Duration;bool Third;FVector Move;};
const FCase Cases[]={
 {TEXT("idle_side"),0,0,1.5,true,FVector::ZeroVector},
 {TEXT("ego_level"),0,0,1.3,false,FVector::ZeroVector},
 {TEXT("ego_left"),-65,-80,1.3,false,FVector::ZeroVector},
 {TEXT("ego_right"),-65,80,1.3,false,FVector::ZeroVector},
 {TEXT("ego_down"),-83,0,1.3,false,FVector::ZeroVector},
 {TEXT("walk_side"),-15,0,2.9,true,FVector(1,0,0)},
 {TEXT("stop_side"),-15,0,1.7,true,FVector::ZeroVector},
 {TEXT("walk_ego"),-35,0,2.9,false,FVector(1,0,0)},
 {TEXT("backward"),-15,0,2.3,true,FVector(-1,0,0)},
 {TEXT("sidestep"),-15,0,2.1,true,FVector(0,-1,0)},
 {TEXT("ego_turn_limit"),-40,130,1.4,false,FVector::ZeroVector},
 {TEXT("idle_after_toggle"),0,0,1.4,true,FVector::ZeroVector}};
}

struct FVillaMotionProof
{
    int32 Case=-1,Sequence=0;float Since=0,LastShot=-1;
    bool Pending=false,Done=false;FString Dir;
    TWeakObjectPtr<ACameraActor> Camera;
    TArray<TSharedPtr<FJsonValue>> Frames,Captures;
    void Tick(AVistaVillaCharacter* C,float Dt)
    {
        if (Done || C->Clock<5) return;
#if WITH_EDITOR
        // Wait before the sequence, then record every simulation tick even if
        // a newly visible material schedules more shader work mid-sequence.
        if (Case<0 && GShaderCompilingManager && GShaderCompilingManager->IsCompiling()) return;
#endif
        Since+=Dt;
        if (Case<0 || Since>Cases[Case].Duration)
        {
            ++Case;Since=0;LastShot=-1;
            if (Case==UE_ARRAY_COUNT(Cases))
            {
                auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),TEXT("vista.villa-motion-proof/v1"));
                O->SetStringField(TEXT("status"),TEXT("captured_pending_visual_review"));
                O->SetArrayField(TEXT("frames"),Frames);O->SetArrayField(TEXT("captures"),Captures);
                FFileHelper::SaveStringToFile(Encode(O),*(Dir/TEXT("motion.json")));
                Done=true;FGenericPlatformMisc::RequestExit(false);return;
            }
            if (Case==0)
            {
                Dir=FPaths::ProjectSavedDir()/TEXT("VillaMotionProof");
                check(!IFileManager::Get().DirectoryExists(*Dir));IFileManager::Get().MakeDirectory(*Dir,true);
                Camera=C->GetWorld()->SpawnActor<ACameraActor>();Camera->GetCameraComponent()->SetFieldOfView(66);
            }
            if (Case!=6)
            {
                C->GetCharacterMovement()->StopMovementImmediately();
                const FVector Start=Case==5 || Case==7?FVector(800,-450,83):FVector(1140,-450,83);
                C->SetActorLocationAndRotation(Start,FRotator::ZeroRotator,false,nullptr,ETeleportType::TeleportPhysics);
                C->bFeetReady=false;
            }
            const auto& S=Cases[Case];C->EmbodiedView(S.Third?1:0);C->EmbodiedCamera(S.Pitch,S.Yaw);
            // Test strafing and reverse movement without the third-person
            // movement component rotating the character into forward motion.
            C->GetCharacterMovement()->bOrientRotationToMovement=false;
            Cast<APlayerController>(C->Controller)->SetViewTarget(S.Third?static_cast<AActor*>(Camera.Get()):static_cast<AActor*>(C));
        }
        const auto& S=Cases[Case];
        if (!S.Move.IsNearlyZero()) C->AddMovementInput(S.Move,1);
        if (S.Third)
        {
            const FVector At=C->GetActorLocation();
            const FVector Eye=At+FVector(0,-285,70);
            Camera->SetActorLocation(Eye);Camera->SetActorRotation((At+FVector(0,0,-6)-Eye).Rotation());
        }
        Pending=true;
    }
    void Capture(AVistaVillaCharacter* C)
    {
        if (!Pending || Done) return;Pending=false;
        auto O=MakeShared<FJsonObject>();const auto& S=Cases[Case];
        O->SetStringField(TEXT("case"),S.Name);O->SetNumberField(TEXT("time_s"),C->Clock);
        O->SetNumberField(TEXT("case_time_s"),Since);O->SetNumberField(TEXT("speed_cm_s"),C->GetVelocity().Size2D());
        O->SetNumberField(TEXT("phase"),C->StepClock);O->SetNumberField(TEXT("motion_weight"),C->MotionWeight);
        O->SetNumberField(TEXT("rest_alpha"),C->FirstPersonRestAlpha);
        O->SetNumberField(TEXT("body_yaw"),C->GetActorRotation().Yaw);
        O->SetNumberField(TEXT("look_yaw"),C->Controller->GetControlRotation().Yaw);
        O->SetArrayField(TEXT("actor_cm"),Values(C->GetActorLocation()));
        auto Joints=MakeShared<FJsonObject>();
        for (const TCHAR* Name:{TEXT("pelvis"),TEXT("upperarm_l"),TEXT("lowerarm_l"),TEXT("hand_l"),
             TEXT("upperarm_r"),TEXT("lowerarm_r"),TEXT("hand_r"),TEXT("thigh_l"),TEXT("calf_l"),TEXT("foot_l"),
             TEXT("ball_l"),TEXT("thigh_r"),TEXT("calf_r"),TEXT("foot_r"),TEXT("ball_r")})
            Joints->SetArrayField(Name,Values(C->GetMesh()->GetSocketLocation(Name)));
        O->SetObjectField(TEXT("joints"),Joints);
        for (int32 Side=0;Side<2;++Side)
        {
            O->SetBoolField(Side?TEXT("right_locked"):TEXT("left_locked"),C->FootLocked[Side]);
            O->SetNumberField(Side?TEXT("right_contact"):TEXT("left_contact"),C->ContactWeight[Side]);
        }
        Frames.Add(MakeShared<FJsonValueObject>(O));
        const bool Walk=!S.Move.IsNearlyZero();
        if (Since<.55f || (LastShot>=0 && (!Walk || Since-LastShot<.22f))) return;
        LastShot=Since;auto R=MakeShared<FJsonObject>();
        const FString Name=FString::Printf(TEXT("%02d_%s_%03d"),Case,S.Name,Sequence++);
        R->SetStringField(TEXT("name"),Name);R->SetStringField(TEXT("case"),S.Name);
        R->SetNumberField(TEXT("time_s"),C->Clock);R->SetNumberField(TEXT("pitch"),S.Pitch);
        R->SetBoolField(TEXT("third_person"),S.Third);R->SetObjectField(TEXT("mesh_world"),Transform(C->GetMesh()->GetComponentTransform()));
        FVector Eye;FRotator View;Cast<APlayerController>(C->Controller)->GetPlayerViewPoint(Eye,View);
        R->SetObjectField(TEXT("camera_mesh_space"),Transform(FTransform(View,Eye).GetRelativeTransform(C->GetMesh()->GetComponentTransform())));
        R->SetNumberField(TEXT("horizontal_fov"),S.Third?66:C->ReviewCamera->FieldOfView);
        TArray<TSharedPtr<FJsonValue>> Bones;
        for (int32 I=0;I<C->Parents.Num();++I)
        {
            const FName N=C->Poses->BoneNames[I];auto B=MakeShared<FJsonObject>();
            B->SetStringField(TEXT("name"),N.ToString());B->SetNumberField(TEXT("parent"),C->Parents[I]);
            B->SetObjectField(TEXT("pose"),Transform(C->GetMesh()->GetSocketTransform(N,RTS_Component)));
            B->SetObjectField(TEXT("reference"),Transform(C->ReferenceGlobal[I]));Bones.Add(MakeShared<FJsonValueObject>(B));
        }
        R->SetArrayField(TEXT("bones"),Bones);Captures.Add(MakeShared<FJsonValueObject>(R));
        FScreenshotRequest::RequestScreenshot(Dir/(Name+TEXT(".png")),false,false);
    }
};

namespace {TUniquePtr<FVillaMotionProof> Proof;}
void TickVillaMotionProof(AVistaVillaCharacter* C,float Dt)
{
    if (!FParse::Param(FCommandLine::Get(),TEXT("VistaVillaMotionProof"))) return;
    if (!Proof) Proof=MakeUnique<FVillaMotionProof>();Proof->Tick(C,Dt);
}
void CaptureVillaMotionProof(AVistaVillaCharacter* C) {if (Proof) Proof->Capture(C);}
