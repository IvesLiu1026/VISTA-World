#include "VistaVillaPourProof.h"
#include "VistaVillaCharacter.h"
#include "HomeActionsJson.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"
#if WITH_EDITOR
#include "ShaderCompiler.h"
#endif

using namespace HomeJson;
namespace
{
struct FCase {const TCHAR* Name;double MugMl,StopAfter;};
const FCase Cases[]={
    {TEXT("risk_no_stop"),160,-1}, {TEXT("risk_timely"),160,1.7},
    {TEXT("risk_late"),160,3.6}, {TEXT("benign_no_stop"),0,-1},
    {TEXT("benign_timely"),0,1.7}, {TEXT("risk_timely_repeat"),160,1.7}};
}

// Privileged scripted engineering probe. The stop request goes through the same
// public controller as P; it is not a model prediction or a tested human warning.
struct FVillaPourProof
{
    int32 Case=-1,Stage=0,PickupsBefore=0,PlacementsBefore=0;
    double Since=0,CaseClock=0,HeldSince=0;
    bool Pending=false,Done=false,StopSent=false,FirstShot=false,ReturnShot=false;
    bool Third=false;
    FString Dir,Shot;
    TWeakObjectPtr<ACameraActor> Camera;
    TArray<TSharedPtr<FJsonValue>> Frames,Captures,Outcomes;

    void Finish(bool Success)
    {
        auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),TEXT("vista.pour-interruption-proof/v1"));
        O->SetStringField(TEXT("status"),Success?TEXT("captured_pending_validation"):TEXT("failed"));
        O->SetStringField(TEXT("audience"),TEXT("privileged_runtime_review_only"));
        O->SetStringField(TEXT("purpose"),TEXT("scripted motor interruption engineering check; not model evaluation or human efficacy"));
        O->SetStringField(TEXT("volume_model"),TEXT("conservative reservoir/flight ledger; not Niagara measured mass"));
        O->SetArrayField(TEXT("frames"),Frames);O->SetArrayField(TEXT("captures"),Captures);O->SetArrayField(TEXT("outcomes"),Outcomes);
        if (!AtomicSave(Dir/TEXT("proof.json"),Encode(O))) UE_LOG(LogTemp,Error,TEXT("VILLA_POUR_PROOF_WRITE_FAILED"));
        Done=true;FGenericPlatformMisc::RequestExit(false);
    }
    void Aim(AVistaVillaCharacter* C,FVector At)
    {
        FVector Eye;FRotator Look;Cast<APlayerController>(C->Controller)->GetPlayerViewPoint(Eye,Look);
        C->Controller->SetControlRotation((At-Eye).Rotation());
    }
    void View(AVistaVillaCharacter* C,bool Side)
    {
        Third=Side;C->EmbodiedView(Side?1:0);
        Cast<APlayerController>(C->Controller)->SetViewTarget(Side?static_cast<AActor*>(Camera.Get()):static_cast<AActor*>(C));
    }
    void Tick(AVistaVillaCharacter* C,float Dt)
    {
        if (Done || C->Clock<5) return;
#if WITH_EDITOR
        if (Case<0 && GShaderCompilingManager && GShaderCompilingManager->IsCompiling()) return;
#endif
        if (Case<0)
        {
            Dir=FPaths::ProjectSavedDir()/TEXT("VillaPourProof");
            if (IFileManager::Get().DirectoryExists(*Dir))
            {UE_LOG(LogTemp,Error,TEXT("VILLA_POUR_PROOF_REUSED"));Done=true;FGenericPlatformMisc::RequestExit(false);return;}
            IFileManager::Get().MakeDirectory(*Dir,true);
            Camera=C->GetWorld()->SpawnActor<ACameraActor>();Camera->GetCameraComponent()->SetFieldOfView(62);
            const FVector Eye(1430,-1130,200),At(1210,-942,126);
            Camera->SetActorLocation(Eye);Camera->SetActorRotation((At-Eye).Rotation());
            Case=0;Stage=0;
        }
        Since+=Dt;CaseClock+=Dt;
        if (Stage==0)
        {
            C->InitialJugMl=600;C->InitialMugMl=Cases[Case].MugMl;C->EmbodiedReset();
            C->GetCharacterMovement()->StopMovementImmediately();
            C->SetActorLocationAndRotation(FVector(1210,-967,83),FRotator(0,90,0),false,nullptr,ETeleportType::TeleportPhysics);
            C->Controller->SetControlRotation(FRotator(-15,90,0));C->bFeetReady=false;
            View(C,false);Since=CaseClock=HeldSince=0;Stage=1;
            StopSent=FirstShot=ReturnShot=false;
            PickupsBefore=C->CompletedPickups;PlacementsBefore=C->CompletedPlacements;
        }
        else if (Stage==1)
        {
            Aim(C,C->Jug->GetActorLocation()+FVector(0,0,13));
            if (Since>1) {C->EmbodiedInteract();Stage=2;Since=0;}
        }
        else if (Stage==2)
        {
            if (C->Phase==EEmbodiedPhase::Held)
            {
                HeldSince+=Dt;
                if (HeldSince>.6)
                {Shot=TEXT("grasp_first_person");C->VillaPour();Stage=3;Since=0;}
            }
        }
        else if (Stage==3)
        {
            if (!Third) Aim(C,C->Mug->GetActorLocation()+FVector(0,-3,13));
            if (!FirstShot && C->PourControl.Elapsed>=1.4)
            {Shot=TEXT("pour_first_person");FirstShot=true;}
            // View changes are identical across conditions and do not issue actions.
            if (!Third && C->PourControl.Elapsed>=1.55) View(C,true);
            if (Cases[Case].StopAfter>=0 && !StopSent && C->PourControl.Elapsed>=Cases[Case].StopAfter)
            {
                C->VillaPour(); // P toggle, followed by duplicate idempotent stop requests.
                C->VillaStopPour();C->VillaStopPour();StopSent=true;
            }
            if (!ReturnShot && C->PourControl.ReturnElapsed>=.3)
            {Shot=TEXT("uprighting_third_person");ReturnShot=true;}
            if (!C->bPouring && Since>1)
            {Shot=TEXT("returned_third_person");Stage=4;Since=0;}
        }
        else if (Stage==4 && Since>.5)
        {
            View(C,false);Aim(C,FVector(1200,-917,96));
            if (Since>.9) {C->EmbodiedPlace();Stage=5;Since=0;}
        }
        else if (Stage==5 && C->Phase==EEmbodiedPhase::Idle && Since>1 && C->Liquid.Airborne()==0)
        {
            auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("case"),Cases[Case].Name);
            O->SetNumberField(TEXT("action_id"),C->PourActionId);
            O->SetNumberField(TEXT("initial_mug_ml"),Cases[Case].MugMl);O->SetNumberField(TEXT("stop_after_s"),Cases[Case].StopAfter);
            O->SetNumberField(TEXT("source_ml"),C->Liquid.Source);O->SetNumberField(TEXT("receiver_ml"),C->Liquid.Receiver);
            O->SetNumberField(TEXT("spill_ml"),C->Liquid.Spill);O->SetNumberField(TEXT("airborne_ml"),C->Liquid.Airborne());
            O->SetNumberField(TEXT("mass_residual_ml"),C->Liquid.Residual());
            O->SetNumberField(TEXT("pickups"),C->CompletedPickups-PickupsBefore);
            O->SetNumberField(TEXT("placements"),C->CompletedPlacements-PlacementsBefore);
            O->SetNumberField(TEXT("duration_s"),CaseClock);Outcomes.Add(MakeShared<FJsonValueObject>(O));
            C->RecordPourEvent(TEXT("proof_outcome"));Shot=TEXT("placed_first_person");Stage=6;Since=0;
        }
        else if (Stage==6 && Since>.2)
        {
            if (++Case==UE_ARRAY_COUNT(Cases)) {Finish(true);return;}
            Stage=0;Since=0;
        }
        if (Since>12)
        {UE_LOG(LogTemp,Error,TEXT("VILLA_POUR_PROOF_TIMEOUT case=%d stage=%d"),Case,Stage);Finish(false);return;}
        Pending=true;
    }
    void Capture(AVistaVillaCharacter* C)
    {
        if (!Pending || Done) return;Pending=false;
        auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("case"),Cases[Case].Name);
        O->SetNumberField(TEXT("case_time_s"),CaseClock);O->SetNumberField(TEXT("dt_s"),C->LastFrameDt);
        O->SetNumberField(TEXT("stage"),Stage);O->SetNumberField(TEXT("action_time_s"),C->PourControl.Elapsed);
        O->SetNumberField(TEXT("return_time_s"),C->PourControl.ReturnElapsed);
        O->SetNumberField(TEXT("pour_phase"),int32(C->PourControl.State));
        O->SetNumberField(TEXT("source_ml"),C->Liquid.Source);O->SetNumberField(TEXT("receiver_ml"),C->Liquid.Receiver);
        O->SetNumberField(TEXT("spill_ml"),C->Liquid.Spill);O->SetNumberField(TEXT("airborne_ml"),C->Liquid.Airborne());
        O->SetNumberField(TEXT("mass_residual_ml"),C->Liquid.Residual());
        O->SetNumberField(TEXT("jug_surface_ml"),C->JugRenderedMl);O->SetNumberField(TEXT("mug_surface_ml"),C->MugRenderedMl);
        O->SetBoolField(TEXT("pouring"),C->bPouring);O->SetBoolField(TEXT("third_person"),Third);
        O->SetStringField(TEXT("sample_phase"),TEXT("after bone transforms finalized; liquid ledger at most recent character tick"));
        O->SetArrayField(TEXT("jug_cm"),Values(C->Jug->GetActorLocation()));O->SetArrayField(TEXT("jug_up"),Values(C->Jug->GetActorUpVector()));
        O->SetArrayField(TEXT("mug_cm"),Values(C->Mug->GetActorLocation()));O->SetArrayField(TEXT("actor_cm"),Values(C->GetActorLocation()));
        O->SetArrayField(TEXT("hand_goal_cm"),Values(C->LastHandGoal.GetLocation()));
        auto J=MakeShared<FJsonObject>();
        for (const TCHAR* Bone:{TEXT("upperarm_r"),TEXT("lowerarm_r"),TEXT("hand_r"),TEXT("foot_l"),TEXT("foot_r")})
            J->SetArrayField(Bone,Values(C->GetMesh()->GetSocketLocation(Bone)));
        O->SetObjectField(TEXT("joints"),J);
        Frames.Add(MakeShared<FJsonValueObject>(O));
        if (!Shot.IsEmpty())
        {
            const FString Name=FString(Cases[Case].Name)+TEXT("_")+Shot;
            auto R=Copy(O);R->SetStringField(TEXT("name"),Name);Captures.Add(MakeShared<FJsonValueObject>(R));
            FScreenshotRequest::RequestScreenshot(Dir/(Name+TEXT(".png")),false,false);Shot.Empty();
        }
    }
};

namespace {TUniquePtr<FVillaPourProof> Proof;TWeakObjectPtr<AVistaVillaCharacter> Owner;}
void TickVillaPourProof(AVistaVillaCharacter* C,float Dt)
{
    if (!FParse::Param(FCommandLine::Get(),TEXT("VistaPourProof"))) return;
    if (Owner.Get()!=C) {Proof=MakeUnique<FVillaPourProof>();Owner=C;}
    Proof->Tick(C,Dt);
}
void CaptureVillaPourProof(AVistaVillaCharacter* C)
{if (Proof && Owner.Get()==C) Proof->Capture(C);}
