#include "EmbodiedFirstPersonProof.h"
#include "EmbodiedReview.h"
#include "HomeActions.h"

#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"

namespace
{
TArray<TSharedPtr<FJsonValue>> V(FVector P)
{return {MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z)};}
TSharedRef<FJsonObject> TransformJson(const FTransform& T)
{
    auto O=MakeShared<FJsonObject>();const FQuat Q=T.GetRotation();
    O->SetArrayField(TEXT("translation_cm"),V(T.GetLocation()));
    O->SetArrayField(TEXT("rotation_xyzw"),{MakeShared<FJsonValueNumber>(Q.X),MakeShared<FJsonValueNumber>(Q.Y),
        MakeShared<FJsonValueNumber>(Q.Z),MakeShared<FJsonValueNumber>(Q.W)});
    O->SetArrayField(TEXT("scale"),V(T.GetScale3D()));return O;
}
struct FViewCase {const TCHAR* Name;float Pitch;int32 View;};
const FViewCase Cases[]={
    {TEXT("empty_level"),0,0},{TEXT("empty_down_20"),-20,0},
    {TEXT("abdomen_down_60"),-60,0},{TEXT("feet_down_89"),-89,0},
    {TEXT("third_person"),-15,1},{TEXT("first_after_toggle"),0,0},
    {TEXT("walking_empty"),0,0},{TEXT("near_wall"),0,0},{TEXT("clear_of_wall"),0,0},
    {TEXT("pickup_approach"),-35,0},{TEXT("holding_cup"),-35,0},{TEXT("empty_after_drop"),0,0}};
}

struct FEmbodiedFirstPersonProof
{
    bool Started=false,Done=false,Issued=false;
    int32 Case=-1;
    float Since=0;
    FString Directory;
    TArray<TSharedPtr<FJsonValue>> Captures,Frames;
    TWeakObjectPtr<AActor> Wall;

    void Finish(const FString& Error=TEXT(""))
    {
        auto O=MakeShared<FJsonObject>();
        O->SetStringField(TEXT("schema"),TEXT("vista.home-first-person-native-proof/v1"));
        O->SetStringField(TEXT("audience"),TEXT("privileged_runtime_review_only"));
        O->SetStringField(TEXT("status"),Error.IsEmpty()?TEXT("captured_pending_geometry_review"):TEXT("failed"));
        O->SetStringField(TEXT("error"),Error);O->SetStringField(TEXT("renderer"),TEXT("NullRHI"));
        O->SetBoolField(TEXT("native_rendered_screenshot"),false);
        O->SetArrayField(TEXT("captures"),Captures);O->SetArrayField(TEXT("frames"),Frames);
        FString Text;auto Writer=TJsonWriterFactory<>::Create(&Text);FJsonSerializer::Serialize(O,Writer);
        FFileHelper::SaveStringToFile(Text,*(Directory/TEXT("poses.json")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
        Done=true;UE_LOG(LogTemp,Display,TEXT("HOME_FIRST_PERSON_PROOF_DONE captures=%d error=%s"),Captures.Num(),*Error);
        FPlatformMisc::RequestExitWithStatus(false,Error.IsEmpty()?0:1);
    }

    void BeginCase(AEmbodiedReviewCharacter* C)
    {
        if (Wall.IsValid()) {Wall->Destroy();Wall.Reset();}
        ++Case;Since=0;Issued=false;
        if (Case>=UE_ARRAY_COUNT(Cases)) {Finish();return;}
        const auto& Spec=Cases[Case];
        if (Case<9) C->EmbodiedPosition(0,0,86,-90);
        if (Case==9) C->EmbodiedPosition(391,317,86,180);
        C->EmbodiedView(Spec.View);C->EmbodiedCamera(Spec.Pitch,Case<9?-90:180);
        if (Case==7)
        {
            AActor* Fixture=C->GetWorld()->SpawnActor<AActor>();
            UBoxComponent* Box=NewObject<UBoxComponent>(Fixture);
            Fixture->SetRootComponent(Box);Box->SetBoxExtent(FVector(4,60,80));
            Box->SetCollisionProfileName(TEXT("BlockAll"));Box->RegisterComponent();
            Fixture->SetActorLocationAndRotation(C->GetActorLocation()+C->GetActorForwardVector()*60.f,
                C->GetActorRotation());Wall=Fixture;
        }
        UE_LOG(LogTemp,Display,TEXT("HOME_FIRST_PERSON_PROOF_CASE %s"),Spec.Name);
    }

    void Capture(AEmbodiedReviewCharacter* C)
    {
        auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("name"),Cases[Case].Name);
        O->SetNumberField(TEXT("pitch"),Cases[Case].Pitch);O->SetBoolField(TEXT("third_person"),C->bThirdPerson);
        O->SetBoolField(TEXT("owner_visible"),C->OwnerBody->IsVisible());
        O->SetBoolField(TEXT("only_owner_see"),C->OwnerBody->bOnlyOwnerSee);
        O->SetBoolField(TEXT("world_owner_no_see"),C->GetMesh()->bOwnerNoSee);
        O->SetBoolField(TEXT("leader_pose_matches"),C->OwnerBody->LeaderPoseComponent.Get()==C->GetMesh());
        O->SetNumberField(TEXT("rest_alpha"),C->FirstPersonRestAlpha);
        O->SetBoolField(TEXT("rest_obstructed"),C->bFirstPersonRestObstructed);
        O->SetNumberField(TEXT("reach_alpha"),C->ReachAlpha);
        O->SetStringField(TEXT("phase"),StaticEnum<EEmbodiedPhase>()->GetNameStringByValue(int64(C->Phase)));
        const FTransform Mesh=C->GetMesh()->GetComponentTransform();
        O->SetObjectField(TEXT("mesh_world"),TransformJson(Mesh));
        UCameraComponent* Camera=C->bThirdPerson?C->FollowCamera.Get():C->ReviewCamera.Get();
        FMinimalViewInfo View;Camera->GetCameraView(0,View);
        O->SetObjectField(TEXT("camera_mesh_space"),TransformJson(FTransform(View.Rotation,View.Location).GetRelativeTransform(Mesh)));
        O->SetNumberField(TEXT("horizontal_fov"),View.FOV);
        O->SetNumberField(TEXT("owner_horizontal_fov"),C->ReviewCamera->FirstPersonFieldOfView);
        O->SetNumberField(TEXT("aspect_ratio"),16.f/9.f);
        O->SetStringField(TEXT("aspect_source"),TEXT("specified 1920x1080 proof viewport; CPU preview uses same aspect"));
        TArray<TSharedPtr<FJsonValue>> Bones;
        for (int32 I=0;I<C->Poses->BoneNames.Num();++I)
        {
            const FName Name=C->Poses->BoneNames[I];auto B=MakeShared<FJsonObject>();
            B->SetStringField(TEXT("name"),Name.ToString());B->SetNumberField(TEXT("parent"),C->Parents[I]);
            B->SetObjectField(TEXT("pose"),TransformJson(C->GetMesh()->GetSocketTransform(Name,RTS_Component)));
            B->SetObjectField(TEXT("reference"),TransformJson(C->ReferenceGlobal[I]));
            Bones.Add(MakeShared<FJsonValueObject>(B));
        }
        O->SetArrayField(TEXT("bones"),Bones);Captures.Add(MakeShared<FJsonValueObject>(O));
    }

    void Tick(AEmbodiedReviewCharacter* C,float Dt)
    {
        if (Done || C->Clock<2.5f) return;
        if (!Started)
        {
            Started=true;Directory=FPaths::ProjectSavedDir()/TEXT("FirstPersonProof");
            if (IFileManager::Get().DirectoryExists(*Directory))
            {Done=true;UE_LOG(LogTemp,Error,TEXT("HOME_FIRST_PERSON_PROOF_REQUIRES_FRESH_USER_DIR"));FPlatformMisc::RequestExitWithStatus(false,1);return;}
            IFileManager::Get().MakeDirectory(*Directory,true);BeginCase(C);return;
        }
        Since+=Dt;
        auto Frame=MakeShared<FJsonObject>();Frame->SetStringField(TEXT("case"),Cases[Case].Name);
        Frame->SetNumberField(TEXT("time_s"),Since);Frame->SetNumberField(TEXT("dt_s"),Dt);
        Frame->SetNumberField(TEXT("rest_alpha"),C->FirstPersonRestAlpha);
        Frame->SetArrayField(TEXT("left_cm"),V(C->GetMesh()->GetSocketTransform(TEXT("hand_l"),RTS_Component).GetLocation()));
        Frame->SetArrayField(TEXT("right_cm"),V(C->GetMesh()->GetSocketTransform(TEXT("hand_r"),RTS_Component).GetLocation()));
        Frames.Add(MakeShared<FJsonValueObject>(Frame));
        if (Case==6 && Since<1.1f) C->AddMovementInput(C->GetActorForwardVector(),.55f);
        if (auto* Home=Cast<AHomeActionsCharacter>(C))
        {
            if (Case==9 && Since<1.f) Home->HomeFocus(TEXT("coffee_cup"));
            if (Case==10 && !Issued) {Home->HomeAction(TEXT("pick_up"),TEXT("coffee_cup"));Issued=true;}
            if (Case==11 && !Issued) {Home->HomeAction(TEXT("drop"),TEXT("coffee_cup"));Issued=true;}
        }
        if (Since>18.f) {Finish(TEXT("Native interaction did not reach the requested phase"));return;}
        if (Since<1.6f) return;
        if (Case==10 && C->Phase!=EEmbodiedPhase::Held) return;
        if (Case==11 && C->Phase!=EEmbodiedPhase::Idle) return;
        Capture(C);BeginCase(C);
    }
};

void TickEmbodiedFirstPersonProof(AEmbodiedReviewCharacter* C,float Dt)
{
    static const bool Enabled=FParse::Param(FCommandLine::Get(),TEXT("VistaFirstPersonProof"));
    if (!Enabled) return;
    if (!FParse::Param(FCommandLine::Get(),TEXT("NullRHI")))
    {UE_LOG(LogTemp,Error,TEXT("First-person proof requires NullRHI"));FPlatformMisc::RequestExitWithStatus(false,1);return;}
    static FEmbodiedFirstPersonProof Proof;Proof.Tick(C,Dt);
}
