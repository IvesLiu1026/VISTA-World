#include "VistaVillaCharacter.h"
#include "HomeActionsJson.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Controller.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

using namespace HomeJson;
namespace
{
TArray<TSharedPtr<FJsonValue>> Row(const FTransform& T)
{
    auto R=Values(T.GetTranslation());const FQuat Q=T.GetRotation();
    for (double V:{Q.X,Q.Y,Q.Z,Q.W}) R.Add(MakeShared<FJsonValueNumber>(V));
    return R;
}
}

void AVistaVillaCharacter::CaptureCharacterMotionProof()
{
    // Explicit, private engineering trace. Never emitted as an agent observation.
    if (!bReady || TraceRemaining<=0 || !FParse::Param(FCommandLine::Get(),TEXT("VistaPrivateReview"))) return;
    FString Dir;if (!FParse::Value(FCommandLine::Get(),TEXT("VistaCharacterMotionProof="),Dir)) return;
    if (!IFileManager::Get().DirectoryExists(*Dir)) return;
    if (!bCharacterMotionMetadata)
    {
        auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),TEXT("vista.character-rig/v1"));
        TArray<TSharedPtr<FJsonValue>> Bones;const auto& Ref=GetMesh()->GetSkeletalMeshAsset()->GetRefSkeleton();
        const auto& Inv=GetMesh()->GetSkeletalMeshAsset()->GetRefBasesInvMatrix();
        for (int32 I=0;I<Parents.Num();++I)
        {
            auto B=MakeShared<FJsonObject>();B->SetStringField(TEXT("name"),Poses->BoneNames[I].ToString());
            B->SetNumberField(TEXT("parent"),Parents[I]);B->SetNumberField(TEXT("mesh_parent"),Ref.GetParentIndex(I));
            B->SetArrayField(TEXT("reference_cs"),Row(ReferenceGlobal[I]));
            B->SetArrayField(TEXT("skin_bind_cs"),Row(FTransform(FMatrix(Inv[I].Inverse()))));
            B->SetArrayField(TEXT("relaxed_local"),Row(Poses->Relaxed[I]));
            Bones.Add(MakeShared<FJsonValueObject>(B));
        }
        O->SetArrayField(TEXT("bones"),Bones);
        FFileHelper::SaveStringToFile(Encode(O),*(Dir/TEXT("rig.json")));
        bCharacterMotionMetadata=true;
    }
    auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),TEXT("vista.character-motion-frame/v1"));
    O->SetStringField(TEXT("snapshot_phase"),TEXT("after bone transforms finalized"));
    O->SetNumberField(TEXT("time_s"),Clock);O->SetNumberField(TEXT("dt"),GetWorld()->GetDeltaSeconds());
    O->SetNumberField(TEXT("body_yaw"),GetActorRotation().Yaw);
    O->SetNumberField(TEXT("look_yaw"),Controller?Controller->GetControlRotation().Yaw:0);
    O->SetNumberField(TEXT("look_pitch"),Controller?Controller->GetControlRotation().Pitch:0);
    O->SetBoolField(TEXT("third_person"),bThirdPerson);O->SetBoolField(TEXT("busy"),bSceneActionBusy);
    O->SetArrayField(TEXT("velocity_cm_s"),Values(GetVelocity()));
    O->SetNumberField(TEXT("phase"),StepClock);O->SetNumberField(TEXT("motion_weight"),MotionWeight);
    O->SetStringField(TEXT("motion"),AlpineMotionName);O->SetNumberField(TEXT("run_blend"),RunBlend);
    O->SetArrayField(TEXT("mesh_world"),Row(GetMesh()->GetComponentTransform()));
    auto Final=MakeShared<FJsonObject>();auto FK=MakeShared<FJsonObject>();TArray<FTransform> Global;
    for (int32 I=0;I<MotionBlend.Num();++I) Global.Add(Parents[I]>=0?MotionBlend[I]*Global[Parents[I]]:MotionBlend[I]);
    for (const TCHAR* Name:{TEXT("root"),TEXT("pelvis"),TEXT("spine_01"),TEXT("spine_02"),TEXT("spine_03"),
        TEXT("neck_01"),TEXT("head"),TEXT("clavicle_l"),TEXT("clavicle_r"),TEXT("upperarm_l"),TEXT("lowerarm_l"),
        TEXT("hand_l"),TEXT("upperarm_r"),TEXT("lowerarm_r"),TEXT("hand_r"),TEXT("thigh_l"),TEXT("calf_l"),
        TEXT("foot_l"),TEXT("ball_l"),TEXT("thigh_r"),TEXT("calf_r"),TEXT("foot_r"),TEXT("ball_r")})
    {
        const int32* I=BoneIndex.Find(FName(Name));if (!I) continue;
        Final->SetArrayField(Name,Row(GetMesh()->GetSocketTransform(Name,RTS_Component)));
        if (Global.IsValidIndex(*I)) FK->SetArrayField(Name,Row(Global[*I]));
    }
    O->SetObjectField(TEXT("final_cs"),Final);O->SetObjectField(TEXT("motion_cs"),FK);
    for (int32 S=0;S<2;++S)
    {
        O->SetNumberField(S?TEXT("right_contact"):TEXT("left_contact"),ContactWeight[S]);
        O->SetArrayField(S?TEXT("right_anchor"):TEXT("left_anchor"),Values(FootAnchor[S]));
    }
    FFileHelper::SaveStringToFile(Encode(O)+TEXT("\n"),*(Dir/TEXT("frames.jsonl")),
        FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,&IFileManager::Get(),FILEWRITE_Append);
}
