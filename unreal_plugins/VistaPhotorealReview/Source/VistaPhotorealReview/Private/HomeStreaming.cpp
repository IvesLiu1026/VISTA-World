#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "VistaCompanion.h"
#include "Components/AudioComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Misc/FileHelper.h"
#include "Misc/Base64.h"
#include "Misc/Paths.h"
#include "Sound/SoundWaveProcedural.h"

using namespace HomeJson;

void AHomeActionsCharacter::HomeEventAdd(const FString& Id)
{FString Code;StartEvent(Id,Code,false);LastCode=Code;FeedbackMessage(Code);PublishState();}

void AHomeActionsCharacter::UpdateConcurrentEvents(float Dt)
{
    for (auto& Pair:ConcurrentEvents)
    {
        auto& E=Pair.Value;if (E.Status!=TEXT("running")) continue;
        E.Elapsed+=Dt;
        // Provisional object manipulation must not complete an event. Other
        // events keep their clocks and may complete while this hand is occupied.
        bool Pending=false;
        for (const FString Field:{TEXT("success_conditions"),TEXT("failure_conditions")})
            for (const auto& V:E.Definition->GetArrayField(Field))
            {
                const FString Target=String(V->AsObject(),TEXT("target_id"));
                Pending|=!ActiveId.IsEmpty() && !Target.IsEmpty() && (Target==TargetId || Target==SecondaryId);
            }
        if (Pending) continue;
        for (const auto& V:E.Definition->GetArrayField(TEXT("failure_conditions")))
            if (EvaluateCondition(V->AsObject(),&E))
            {E.Status=TEXT("failed");E.Terminal=String(V->AsObject(),TEXT("condition_id"));break;}
        if (E.Status==TEXT("running"))
        {
            const auto& Goals=E.Definition->GetArrayField(TEXT("success_conditions"));bool All=Goals.Num()>0;
            for (const auto& V:Goals) All&=EvaluateCondition(V->AsObject(),&E);
            if (All) {E.Status=TEXT("succeeded");E.Terminal=String(Goals[0]->AsObject(),TEXT("condition_id"));}
        }
        if (E.Status==TEXT("running") && E.Elapsed>=Number(E.Definition,TEXT("timeout_s")))
        {E.Status=TEXT("failed");E.Terminal=TEXT("event_timeout");}
        if (E.Status!=TEXT("running"))
        {
            auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("schema"),TEXT("vista.concurrent-event-outcome/v1"));
            R->SetStringField(TEXT("event_id"),E.TemplateId);R->SetStringField(TEXT("instance_id"),Pair.Key);R->SetStringField(TEXT("status"),E.Status);
            R->SetStringField(TEXT("condition_id"),E.Terminal);R->SetNumberField(TEXT("elapsed_s"),E.Elapsed);
            R->SetNumberField(TEXT("started_at_s"),E.Started);R->SetNumberField(TEXT("clock_s"),SceneClock);AppendReceipt(R);
        }
    }
}
TArray<TSharedPtr<FJsonValue>> AHomeActionsCharacter::ConcurrentEventState() const
{
    TArray<FString> Ids;ConcurrentEvents.GetKeys(Ids);Ids.Sort();TArray<TSharedPtr<FJsonValue>> Out;
    for (const FString& Id:Ids)
    {
        const auto& E=ConcurrentEvents[Id];auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("event_id"),E.TemplateId);R->SetStringField(TEXT("instance_id"),Id);
        R->SetStringField(TEXT("status"),E.Status);R->SetStringField(TEXT("condition_id"),E.Terminal);
        R->SetNumberField(TEXT("started_at_s"),E.Started);R->SetNumberField(TEXT("elapsed_s"),E.Elapsed);
        Out.Add(MakeShared<FJsonValueObject>(R));
    }
    return Out;
}

void AHomeActionsCharacter::HomePhone(bool Enabled)
{
    if (!bStreamingEnabled) return;
    const auto* Held=Resolve(HeldId);
    if (Enabled && (!Held || Held->ShortId!=TEXT("phone") || !ActiveId.IsEmpty()))
    {LastCode=TEXT("PICK_UP_PHONE_FIRST");FeedbackMessage(LastCode);return;}
    FString Text;
    if (FFileHelper::LoadFileToString(Text,*(FPaths::ProjectConfigDir()/TEXT("VistaStreaming.json"))))
    {
        const auto D=Decode(Text);
        if (D)
        {
            const FVector R=Vector(D,TEXT("phone_rotation_deg"),FVector(0,0,-90));
            PhoneRotation=FRotator(R.X,R.Y,R.Z).Quaternion();
            PhoneEarOffset=Vector(D,TEXT("phone_ear_offset_cm"),FVector(6,10,0)).GetClampedToMaxSize(24);
        }
    }
    bPhoneCall=Enabled;LastCode=Enabled?TEXT("PHONE_CALL_STARTED"):TEXT("PHONE_CALL_ENDED");PublishState();
}

void AHomeActionsCharacter::UpdateDailyMotion(float Dt)
{
    DailyClock+=Dt;
    const auto* Held=Resolve(HeldId);
    if (!Held || Held->ShortId!=TEXT("phone")) bPhoneCall=false;
    PhoneBlend=FMath::FInterpConstantTo(PhoneBlend,bPhoneCall?1.f:0.f,Dt,1.25f);
    if (HumanFaceMorphs.IsEmpty())
    {
        FString Text;const TSharedPtr<FJsonObject>* Morphs;
        if (FFileHelper::LoadFileToString(Text,*(FPaths::ProjectConfigDir()/TEXT("VistaCompanion.json"))))
        {
            const auto D=Decode(Text);
            if (D && D->TryGetObjectField(TEXT("face_morphs"),Morphs))
                for (const auto& Pair:(*Morphs)->Values)
                    for (const auto& V:Pair.Value->AsArray())
                        if (GetMesh()->GetSkeletalMeshAsset()->FindMorphTarget(FName(V->AsString())))
                            HumanFaceMorphs.FindOrAdd(FName(Pair.Key)).Add(FName(V->AsString()));
        }
    }
    const float Cycle=FMath::Fmod(DailyClock,4.7f);
    const float Blink=Cycle<.18f?FMath::Sin(Cycle/.18f*PI)*.85f:0.f;
    if (const auto* Names=HumanFaceMorphs.Find(TEXT("Blink")))
        for (FName Name:*Names) GetMesh()->SetMorphTarget(Name,Blink);
    float Mouth=0;
    if (HumanVoice && HumanVoice->IsPlaying() && HumanWave)
    {
        const float Clock=(HumanAudioBytes-HumanWave->GetAvailableAudioByteCount())/(2.f*HumanAudioRate);
        const int32 Frame=FMath::FloorToInt(Clock*50);
        if (HumanMouth.IsValidIndex(Frame)) Mouth=HumanMouth[Frame];
        if (Clock>=HumanWave->Duration-.02f) HumanVoice->Stop();
    }
    HumanMouthOpen=FMath::FInterpTo(HumanMouthOpen,Mouth,Dt,18);
    if (const auto* Names=HumanFaceMorphs.Find(TEXT("JawOpen")))
        for (FName Name:*Names) GetMesh()->SetMorphTarget(Name,HumanMouthOpen);
}

void AHomeActionsCharacter::HomeHumanSay(const FString& Code)
{
    if (!bStreamingEnabled || (Code!=TEXT("human_call") && Code!=TEXT("human_request"))) return;
    FString Text;if (!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("VISTA/Streaming/Speech")/(Code+TEXT(".json"))))) return;
    const auto D=Decode(Text);TArray<uint8> PCM;
    if (!D || !FBase64::Decode(String(D,TEXT("pcm_b64")),PCM)) return;
    const int32 Rate=Number(D,TEXT("sample_rate"));
    if (Rate<8000 || Rate>48000 || PCM.Num()<2 || PCM.Num()>Rate*2*30) return;
    if (!HumanVoice)
    {
        HumanVoice=NewObject<UAudioComponent>(this);HumanVoice->SetupAttachment(GetMesh(),TEXT("head"));
        HumanVoice->bAutoActivate=false;HumanVoice->RegisterComponent();
    }
    HumanVoice->Stop();HumanWave=NewObject<USoundWaveProcedural>(this);HumanWave->SetSampleRate(Rate);
    HumanWave->NumChannels=1;HumanWave->Duration=PCM.Num()/(2.f*Rate);HumanWave->SoundGroup=SOUNDGROUP_Voice;
    HumanWave->QueueAudio(PCM.GetData(),PCM.Num());HumanAudioBytes=PCM.Num();HumanAudioRate=Rate;HumanMouth.Empty();
    for (const auto& V:D->GetArrayField(TEXT("mouth"))) if (V->AsArray().Num()==3) HumanMouth.Add(V->AsArray()[0]->AsNumber());
    HumanVoice->SetSound(HumanWave);HumanVoice->Play();
    if (auto* C=FindComponentByClass<UVistaCompanionComponent>())
    {C->Reply=TEXT("人物：")+String(D,TEXT("text"));C->NoticeUntil=GetWorld()->GetTimeSeconds()+HumanWave->Duration;}
    auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("schema"),TEXT("vista.authored-human-utterance/v1"));
    R->SetStringField(TEXT("text"),String(D,TEXT("text")));R->SetStringField(TEXT("source"),TEXT("authored_transcript_not_ASR"));
    R->SetNumberField(TEXT("clock_s"),SceneClock);R->SetNumberField(TEXT("duration_s"),HumanWave->Duration);AppendReceipt(R);
}

TSharedPtr<FJsonObject> AHomeActionsCharacter::StreamingObservation() const
{
    auto D=CompanionObservation();D->RemoveField(TEXT("public_goal"));
    D->SetStringField(TEXT("schema"),TEXT("vista.streaming-observation/v1"));
    D->SetStringField(TEXT("source"),TEXT("engine_visible_metadata_not_vlm"));
    D->SetStringField(TEXT("wearer_role"),TEXT("human_needing_assistance"));
    D->SetStringField(TEXT("view"),bThirdPerson?TEXT("third_person_review"):TEXT("human_ego"));
    D->SetNumberField(TEXT("clock_s"),SceneClock);
    FVector Eye;FRotator View;GetActorEyesViewPoint(Eye,View);
    if (const auto* PC=Cast<APlayerController>(Controller)) PC->GetPlayerViewPoint(Eye,View);
    auto Visible=[&](AStaticMeshActor* A)
    {
        if (!A || A->IsHidden() || !A->GetStaticMeshComponent()->IsVisible()) return false;
        const FVector Center=A->GetStaticMeshComponent()->Bounds.Origin,Delta=Center-Eye;
        if (Delta.Size()>650 || FVector::DotProduct(Delta.GetSafeNormal(),View.Vector())<.6f) return false;
        FCollisionQueryParams Q(SCENE_QUERY_STAT(StreamingCue),false,this);FHitResult Hit;
        return !GetWorld()->LineTraceSingleByChannel(Hit,Eye,Center,ECC_Visibility,Q) || Hit.GetActor()==A || FVector::Distance(Hit.ImpactPoint,Center)<8;
    };
    TArray<TSharedPtr<FJsonValue>> Cues;
    auto Cue=[&](const TCHAR* Text){Cues.Add(MakeShared<FJsonValueString>(Text));};
    if (Visible(Effects.FindRef(TEXT("flame_0")))) Cue(TEXT("visible_stove_flame"));
    if (Visible(Effects.FindRef(TEXT("bath_stream")))) Cue(TEXT("visible_running_bath_tap"));
    if (Visible(Effects.FindRef(TEXT("bath_water"))))
    {
        // Only coarse rendered water height, never the exact hidden ledger.
        const float Level=Number(Resolve(TEXT("bathtub"))->State,TEXT("liquid_level"));
        if (Level>.83f) Cue(TEXT("visible_water_near_rim"));
    }
    if (Visible(Effects.FindRef(TEXT("overflow")))) Cue(TEXT("visible_water_on_floor"));
    if (const auto* E=Resolve(TEXT("stove"));E && Visible(E->Actor.Get()))
        Cue(Bool(E->State,TEXT("active"))?TEXT("visible_stove_on_control"):TEXT("visible_stove_off"));
    if (const auto* E=Resolve(TEXT("faucet"));E && Visible(E->Actor.Get()) && !Bool(E->State,TEXT("active"))) Cue(TEXT("visible_bath_tap_off"));
    if (const auto* E=Resolve(TEXT("keys"));E && Visible(E->Actor.Get())) Cue(TEXT("visible_keys"));
    // Wearer's own hand activity is proprioception, explicitly separate from vision.
    D->SetStringField(TEXT("human_activity"),bPhoneCall && PhoneBlend>.8f?TEXT("phone_at_ear"):TEXT("unspecified"));
    D->SetArrayField(TEXT("cues"),Cues);return D;
}

void AHomeActionsCharacter::HomeNotice(const FString& Code)
{
    if (!bStreamingEnabled) return;
    const TMap<FString,FString> Lines={
        {TEXT("water"),TEXT("浴缸水位快到邊緣了，請先把水關掉。")},
        {TEXT("stove"),TEXT("剛才看到爐具還開著；離開前請先確認。")},
        {TEXT("keys"),TEXT("你剛才要找的鑰匙，我在客廳茶几看到了。")},
        {TEXT("resume"),TEXT("水已經關好了，稍後可以繼續剛才的事情。")},
        {TEXT("quiet"),TEXT("助手觀察中，暫不打擾。")}};
    if (!Lines.Contains(Code)) return;
    if (auto* C=FindComponentByClass<UVistaCompanionComponent>())
    {
        C->Stop();C->Reply=Lines[Code];C->Status=TEXT("規則基線提醒");C->NoticeUntil=GetWorld()->GetTimeSeconds()+7;
        FString Text;
        if (Code!=TEXT("quiet") && C->Companion && FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("VISTA/Streaming/Speech")/(Code+TEXT(".json")))))
        {
            const auto Audio=Decode(Text);if (Audio && String(Audio,TEXT("text"))==Lines[Code]) C->Companion->Speak(Audio);
        }
    }
}
