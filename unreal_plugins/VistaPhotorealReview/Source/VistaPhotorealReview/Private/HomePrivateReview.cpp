// Isolated director/human control. Never exposed to the assistant observation.
#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "VistaCompanion.h"
#include "VistaPathSteering.h"
#include "Camera/CameraComponent.h"
#include "Components/AudioComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "GameFramework/PlayerController.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "Misc/Base64.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Sound/SoundWaveProcedural.h"

using namespace HomeJson;

void AHomeActionsCharacter::ActionView(FVector& Eye,FRotator& View) const
{
    GetActorEyesViewPoint(Eye,View);
    if (const auto* PC=Cast<APlayerController>(Controller)) PC->GetPlayerViewPoint(Eye,View);
    if ((FParse::Param(FCommandLine::Get(),TEXT("VistaPrivateReview")) || !DirectorOwner.IsEmpty()) &&
        FParse::Param(FCommandLine::Get(),TEXT("VistaEgoSensor")))
    {Eye=ReviewCamera->GetComponentLocation();View=GetControlRotation();}
}

void AHomeActionsCharacter::PrivateDialogue(const FString& Role,const FString& Code)
{
    if (!FParse::Param(FCommandLine::Get(),TEXT("VistaPrivateReview")) || !bStreamingEnabled) return;
    if (Code.IsEmpty() || Code.Len()>64) return;
    for (TCHAR C:Code) if (!FChar::IsAlnum(C) && C!=TCHAR('_')) return;
    if (Role!=TEXT("human") && Role!=TEXT("assistant") && Role!=TEXT("phone")) return;
    FString Text;
    if (!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("VISTA/Concurrent/Speech")/(Code+TEXT(".json"))))) return;
    const auto D=Decode(Text);TArray<uint8> PCM;
    if (!D || String(D,TEXT("role"))!=Role || String(D,TEXT("language"))!=TEXT("en") ||
        !FBase64::Decode(String(D,TEXT("pcm_b64")),PCM)) return;
    const int32 Rate=Number(D,TEXT("sample_rate"));
    if (Rate<8000 || Rate>48000 || PCM.Num()<2 || PCM.Num()>Rate*2*30 || PCM.Num()%2) return;
    if (Role==TEXT("assistant"))
    {
        if (auto* C=FindComponentByClass<UVistaCompanionComponent>();C && C->Companion)
        {C->Stop();C->Reply=String(D,TEXT("text"));C->NoticeUntil=GetWorld()->GetTimeSeconds()+PCM.Num()/(2.f*Rate);C->Companion->Speak(D);}
    }
    else
    {
        if (!HumanVoice)
        {
            HumanVoice=NewObject<UAudioComponent>(this);HumanVoice->SetupAttachment(GetMesh(),TEXT("head"));
            HumanVoice->bAutoActivate=false;HumanVoice->RegisterComponent();
        }
        HumanVoice->Stop();HumanWave=NewObject<USoundWaveProcedural>(this);HumanWave->SetSampleRate(Rate);
        HumanWave->NumChannels=1;HumanWave->Duration=PCM.Num()/(2.f*Rate);HumanWave->SoundGroup=SOUNDGROUP_Voice;
        HumanWave->QueueAudio(PCM.GetData(),PCM.Num());HumanAudioBytes=PCM.Num();HumanAudioRate=Rate;HumanMouth.Empty();
        bPrivateHumanLipSync=Role==TEXT("human");
        const TArray<TSharedPtr<FJsonValue>>* Mouth;
        if (D->TryGetArrayField(TEXT("mouth"),Mouth))
            for (const auto& V:*Mouth) if (V->AsArray().Num()==3) HumanMouth.Add(V->AsArray()[0]->AsNumber());
        HumanVoice->SetSound(HumanWave);HumanVoice->Play();
    }
    if (auto* C=FindComponentByClass<UVistaCompanionComponent>())
    {
        const FString Label=Role==TEXT("human")?TEXT("You: "):(Role==TEXT("phone")?TEXT("Phone: "):TEXT("Assistant: "));
        C->Reply=Label+String(D,TEXT("text"));C->NoticeUntil=GetWorld()->GetTimeSeconds()+PCM.Num()/(2.f*Rate);
    }
    auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("schema"),TEXT("vista.in-world-dialogue/v1"));
    R->SetStringField(TEXT("role"),Role);R->SetStringField(TEXT("code"),Code);R->SetStringField(TEXT("text"),String(D,TEXT("text")));
    R->SetStringField(TEXT("source"),TEXT("authored_cached_synthetic_speech"));R->SetNumberField(TEXT("clock_s"),SceneClock);
    R->SetNumberField(TEXT("duration_s"),PCM.Num()/(2.f*Rate));AppendReceipt(R);
}

void AHomeActionsCharacter::PollPrivateReview()
{
    if (!FParse::Param(FCommandLine::Get(),TEXT("VistaPrivateReview"))) return;
    const FString Dir=BridgeDir/TEXT("review_requests");TArray<FString> Files;
    IFileManager::Get().MakeDirectory(*Dir,true);IFileManager::Get().FindFiles(Files,*(Dir/TEXT("*.json")),true,false);Files.Sort();
    for (const FString& File:Files)
    {
        const FString Tag=TEXT("private/")+File;if (ProcessedRequests.Contains(Tag)) continue;
        ProcessedRequests.Add(Tag);if (IFileManager::Get().FileSize(*(Dir/File))>4096) continue;
        FString Text;if (!FFileHelper::LoadFileToString(Text,*(Dir/File))) continue;
        const auto D=Decode(Text);if (!D || String(D,TEXT("schema"))!=TEXT("vista.private-review/v1") ||
            String(D,TEXT("session_id"))!=SessionId) continue;
        const FString Op=String(D,TEXT("op"));FString Code=TEXT("REVIEW_REJECTED");
        if (Op==TEXT("look") || Op==TEXT("walk") || Op==TEXT("path"))
        {
            const double Yaw=Number(D,TEXT("yaw")),Pitch=Number(D,TEXT("pitch"),-8);
            FVector Target=Vector(D,TEXT("target_cm"));TArray<FVector> Points;bool ValidPath=true;
            if (Op==TEXT("path"))
            {
                const TArray<TSharedPtr<FJsonValue>>* Rows;
                ValidPath=D->TryGetArrayField(TEXT("points_cm"),Rows) && Rows->Num()>0 && Rows->Num()<=96;
                if (ValidPath) for (const auto& V:*Rows)
                {
                    const auto* A=V->Type==EJson::Array?&V->AsArray():nullptr;
                    if (!A || A->Num()!=3 || (*A)[0]->Type!=EJson::Number || (*A)[1]->Type!=EJson::Number || (*A)[2]->Type!=EJson::Number) {ValidPath=false;break;}
                    const FVector P((*A)[0]->AsNumber(),(*A)[1]->AsNumber(),(*A)[2]->AsNumber());
                    if (P.ContainsNaN() || P.Size()>100000) {ValidPath=false;break;} Points.Add(P);
                }
                if (ValidPath) {Target=Points[0];Points.RemoveAt(0);}
            }
            if (FMath::IsFinite(Yaw) && FMath::IsFinite(Pitch) && FMath::Abs(Yaw)<=360 && FMath::Abs(Pitch)<=85 &&
                !Target.ContainsNaN() && Target.Size()<100000 && ActiveId.IsEmpty() && ValidPath)
            {
                PrivatePath=Points;PrivateLook=FRotator(Pitch,Yaw,0);bPrivateLooking=true;bPrivateMoving=Op!=TEXT("look");
                PrivateTarget=Target;PrivatePrevious=GetActorLocation();PrivateStall=PrivateMoveClock=0;
                PrivatePreviewCm=0;PrivateCornerFrames=0;
                PrivateMotion=bPrivateMoving?TEXT("walking"):TEXT("looking");Code=TEXT("REVIEW_ACCEPTED");
            }
        }
        else if (Op==TEXT("event_add")) {StartEvent(String(D,TEXT("event_id")),Code,false);LastCode=Code;}
        else if (Op==TEXT("phone")) {HomePhone(Bool(D,TEXT("enabled")));Code=LastCode;}
        else if (Op==TEXT("dialogue")) {PrivateDialogue(String(D,TEXT("role")),String(D,TEXT("code")));Code=TEXT("DIALOGUE_REQUESTED");}
        else if (Op==TEXT("stop")) {PrivatePath.Empty();bPrivateMoving=bPrivateLooking=false;PrivateMotion=TEXT("stopped");GetCharacterMovement()->StopMovementImmediately();Code=TEXT("REVIEW_STOPPED");}
        // No resets, room teleports, arbitrary console commands or camera switching.
        auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("schema"),TEXT("vista.private-review-reply/v1"));
        R->SetStringField(TEXT("op"),Op);R->SetStringField(TEXT("code"),Code);R->SetNumberField(TEXT("clock_s"),SceneClock);
        R->SetStringField(TEXT("session_id"),SessionId);
        const FString ReplyDir=BridgeDir/TEXT("review_responses");IFileManager::Get().MakeDirectory(*ReplyDir,true);
        AtomicSave(ReplyDir/File,Encode(R));
    }
}

void AHomeActionsCharacter::TickPrivateReview(float Dt)
{
    if (!DirectorOwner.IsEmpty())
    {
        if (FPlatformTime::Seconds()>DirectorUntil) {StopDirector();PrivateMotion=TEXT("lease_expired");}
        else if (bThirdPerson!=bDirectorThird) EmbodiedView(bDirectorThird?1:0);
    }
    if ((!FParse::Param(FCommandLine::Get(),TEXT("VistaPrivateReview")) && DirectorOwner.IsEmpty()) || !Controller) return;
    if (!bPrivateLooking && !bPrivateMoving) return;
    FRotator Look=Controller->GetControlRotation();FVector Delta=PrivateTarget-GetActorLocation();Delta.Z=0;
    if (bPrivateMoving && PrivatePath.Num())
    {
        const FVector Exit=(PrivatePath[0]-PrivateTarget).GetSafeNormal2D();
        FVector Next=PrivatePath[0];Next.Z=GetActorLocation().Z;
        const bool ClearNext=VistaPathSteering::ClearFloorChord(this,Next);
        const float Progress=FVector::DotProduct(-Delta,Exit);
        const float Lateral=(-Delta-Exit*Progress).Size2D();
        const bool Passed=Delta.Size()<85 && Progress>2 && (ClearNext || Lateral<4);
        if (Delta.Size()<3 || (Delta.Size()<12 && ClearNext) || Passed)
        {PrivateTarget=PrivatePath[0];PrivatePath.RemoveAt(0);Delta=PrivateTarget-GetActorLocation();Delta.Z=0;PrivateMoveClock=0;}
    }
    FVector Goal=PrivateTarget;Goal.Z=GetActorLocation().Z;
    if (bPrivateMoving && PrivatePath.Num()) Goal=VistaPathSteering::PreviewCorner(this,PrivateTarget,PrivatePath[0],
        FMath::Clamp(GetVelocity().Size2D()*.65f+20,45.f,95.f));
    PrivatePreviewCm=FVector::Dist2D(Goal,PrivateTarget);
    if (PrivatePreviewCm>4) ++PrivateCornerFrames;
    const FVector Direction=(Goal-GetActorLocation()).GetSafeNormal2D();
    const float Desired=bPrivateMoving?Direction.Rotation().Yaw:PrivateLook.Yaw;
    // Camera looks into the bend while the capsule is still approaching it.
    Look.Yaw=FMath::FixedTurn(Look.Yaw,Desired,95*Dt);
    Look.Pitch=FMath::FInterpTo(Look.Pitch,PrivateLook.Pitch,Dt,4);Controller->SetControlRotation(Look);
    if (bPrivateMoving)
    {
        PrivateMoveClock+=Dt;
        const float Moved=FVector::Dist2D(PrivatePrevious,GetActorLocation());PrivatePrevious=GetActorLocation();
        const float Error=FMath::Abs(FMath::FindDeltaAngleDegrees(Look.Yaw,Desired));
        const float Clearance=VistaPathSteering::ForwardClearance(this,Direction,95);
        // Decelerate before contact, but let CharacterMovement resolve a close
        // tangential door-frame pass using its original full collision capsule.
        const float Brake=FMath::Clamp(Clearance/60.f,.22f,1.f);
        PrivateClearance=Clearance;
        const float Input=FMath::Clamp((85-Error)/45.f,0.f,1.f)*Brake*
            (PrivatePath.Num()?1.f:FMath::Clamp(Delta.Size()/38.f,.18f,1.f));
        if (ActiveId.IsEmpty()) AddMovementInput(Direction,Input,true);
        PrivateStall=ActiveId.IsEmpty() && Moved<.01f?PrivateStall+Dt:0;
        const bool Arrived=PrivatePath.IsEmpty() && Delta.Size()<3;
        if (Arrived || PrivateStall>5 || PrivateMoveClock>45)
        {
            PrivateMotion=Arrived?TEXT("arrived"):TEXT("blocked");
            bPrivateMoving=bPrivateLooking=false;GetCharacterMovement()->StopMovementImmediately();
        }
    }
    else if (FMath::Abs(FMath::FindDeltaAngleDegrees(Look.Yaw,Desired))<.5f && FMath::Abs(Look.Pitch-PrivateLook.Pitch)<.5f)
    {bPrivateLooking=false;PrivateMotion=TEXT("arrived");}
}
