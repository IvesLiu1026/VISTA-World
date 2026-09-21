// Typed live execution adapter. The authoring side is never policy evidence.
#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "VistaCompanion.h"
#include "Components/AudioComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Misc/Base64.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Sound/SoundWaveProcedural.h"

using namespace HomeJson;
namespace { FString LiveLayoutDiagnostic; }

bool AHomeActionsCharacter::CommitCompanionOff(const FString& Target,AActor* Helper,const FVector& Finger,FString& Code)
{
    auto* E=Resolve(Target);
    if (!FParse::Param(FCommandLine::Get(),TEXT("VistaLiveAssistant")) || !Helper || !E ||
        (Target!=TEXT("stove") && Target!=TEXT("faucet")) || !E->Actor.IsValid() ||
        TargetId==E->Id || !Bool(E->State,TEXT("active"))) {Code=TEXT("ASSIST_STATE_REJECTED");return false;}
    const FVector Contact=ControlPoint(*E);
    if (FVector::Distance(Contact,Finger)>3 || FVector::Dist2D(Helper->GetActorLocation(),Contact)>85)
    {Code=TEXT("ASSIST_CONTACT_REJECTED");return false;}
    FHitResult Hit;FCollisionQueryParams Q(SCENE_QUERY_STAT(CompanionContact),false,Helper);
    if (GetWorld()->LineTraceSingleByChannel(Hit,Finger,Contact,ECC_Visibility,Q) &&
        Hit.GetActor()!=E->Actor.Get() && FVector::Distance(Hit.ImpactPoint,Contact)>3)
    {Code=TEXT("ASSIST_OCCLUDED_REJECTED");return false;}
    E->State->SetBoolField(TEXT("active"),false);E->State->SetStringField(TEXT("status"),TEXT("idle"));
    Interactions.Add(E->Id+TEXT("#turn_off"));
    for (auto& Pair:ConcurrentEvents) if (Pair.Value.Status==TEXT("running")) Pair.Value.Interactions.Add(E->Id+TEXT("#turn_off"));
    auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("schema"),TEXT("vista.companion-action/v1"));
    R->SetStringField(TEXT("target"),Target);R->SetStringField(TEXT("actor"),TEXT("companion"));
    R->SetStringField(TEXT("action"),TEXT("turn_off"));R->SetStringField(TEXT("status"),TEXT("committed"));
    R->SetNumberField(TEXT("finger_error_cm"),FVector::Distance(Contact,Finger));
    R->SetStringField(TEXT("contact_model"),TEXT("kinematic_finger_proximity_not_force_simulation"));
    R->SetNumberField(TEXT("clock_s"),SceneClock);AppendReceipt(R);Code=TEXT("ASSIST_COMMITTED");return true;
}

bool AHomeActionsCharacter::ApplyLiveScene(const FString& Layout,int32 Room,FString& Code)
{
    LiveLayoutDiagnostic.Empty();
    if ((Layout!=TEXT("everyday") && Layout!=TEXT("workday") && Layout!=TEXT("evening")) || Room<1 || Room>6)
    {Code=TEXT("SCENE_REJECTED");return false;}
    // Reviewed support anchors, not arbitrary model coordinates. Existing base
    // plants/furniture stay; workday adds books, evening also lights the lamp.
    UStaticMesh* Book=nullptr;
    TArray<FVector> Points;
    if (Layout!=TEXT("everyday"))
    {
        Book=LoadObject<UStaticMesh>(nullptr,TEXT("/Game/VISTA/StreamingR2/book/book/StaticMeshes/book.book"));
        if (!Book) {Code=TEXT("SCENE_ASSET_REJECTED");return false;}
        // The office book is a flat, measured support. The kitchen recipe book
        // is tilted and cannot safely support this mesh's complete cover.
        for (const FString Surface:{TEXT("daily_11")})
        {
            auto* E=Resolve(Surface);bool Found=false;
            if (!E || !E->Actor.IsValid()) {Code=TEXT("SCENE_SUPPORT_REJECTED");return false;}
            for (const FVector Offset:{FVector::ZeroVector})
            {
                const FVector Anchor=E->Mesh->Bounds.Origin+FVector(0,0,E->Mesh->Bounds.BoxExtent.Z)+Offset;
                FCollisionQueryParams Q(SCENE_QUERY_STAT(LiveSupport),true,this);
                for (const auto& A:LiveDressing) if (A) Q.AddIgnoredActor(A.Get());
                FHitResult Support;
                const bool Hit=GetWorld()->LineTraceSingleByChannel(Support,Anchor+FVector(0,0,12),Anchor-FVector(0,0,5),ECC_Visibility,Q);
                LiveLayoutDiagnostic+=FString::Printf(TEXT("%s %s support=%s normal=%s; "),*Surface,*Anchor.ToString(),*GetNameSafe(Support.GetActor()),*Support.ImpactNormal.ToString());
                if (!Hit || Support.GetActor()!=E->Actor.Get() || Support.ImpactNormal.Z<.95f) continue;
                const FVector P=Support.ImpactPoint+FVector(0,0,.3);const FBox B=Book->GetBoundingBox();
                bool Supported=true;
                for (int32 X:{-1,1}) for (int32 Y:{-1,1})
                {
                    const FVector Corner=P+FVector(X*B.GetExtent().X*.65f,Y*B.GetExtent().Y*.65f,0);FHitResult H;
                    if (!GetWorld()->LineTraceSingleByChannel(H,Corner+FVector(0,0,3),Corner-FVector(0,0,3),ECC_Visibility,Q) ||
                        H.GetActor()!=E->Actor.Get() || H.ImpactNormal.Z<.95f) Supported=false;
                }
                if (!Supported) {LiveLayoutDiagnostic+=TEXT("unsupported footprint; ");continue;}
                Q.AddIgnoredActor(E->Actor.Get());Q.bTraceComplex=false;
                const FVector Origin=P-FVector(B.GetCenter().X,B.GetCenter().Y,B.Min.Z);
                if (GetWorld()->OverlapBlockingTestByChannel(Origin+B.GetCenter(),FQuat::Identity,ECC_Visibility,
                    FCollisionShape::MakeBox(B.GetExtent()+FVector(.2,.2,.1)),Q)) {LiveLayoutDiagnostic+=TEXT("occupied volume; ");continue;}
                Points.Add(Origin);Found=true;break;
            }
            if (!Found) {Code=TEXT("SCENE_SUPPORT_REJECTED");return false;}
        }
    }
    if (auto* C=FindComponentByClass<UVistaCompanionComponent>();C && C->Companion) {C->Companion->CancelAssist();C->Companion->StopSpeech();}
    if (!ResetScene(Code)) return false;
    for (const auto& A:LiveDressing) if (A) A->Destroy();LiveDressing.Empty();
    for (const FVector P:Points)
    {
        auto* A=GetWorld()->SpawnActor<AStaticMeshActor>(P,FRotator::ZeroRotator);
        A->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
        A->GetStaticMeshComponent()->SetStaticMesh(Book);A->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        A->GetStaticMeshComponent()->SetCollisionResponseToAllChannels(ECR_Block);LiveDressing.Add(A);
    }
    if (Layout==TEXT("evening")) if (auto* Lamp=Resolve(TEXT("floor_lamp"))) Lamp->State->SetBoolField(TEXT("active"),true);
    HomeRoom(Room);PublishState();Code=TEXT("SCENE_APPLIED");return true;
}

void AHomeActionsCharacter::PollLiveCommands()
{
    if (!FParse::Param(FCommandLine::Get(),TEXT("VistaLiveAssistant"))) return;
    const FString Dir=BridgeDir/TEXT("live_requests");TArray<FString> Files;
    IFileManager::Get().MakeDirectory(*Dir,true);IFileManager::Get().FindFiles(Files,*(Dir/TEXT("*.json")),true,false);Files.Sort();
    for (const FString& File:Files)
    {
        const FString Tag=TEXT("live/")+File;if (ProcessedRequests.Contains(Tag)) continue;ProcessedRequests.Add(Tag);
        if (IFileManager::Get().FileSize(*(Dir/File))>2100000) continue;
        FString Text;if (!FFileHelper::LoadFileToString(Text,*(Dir/File))) continue;const auto D=Decode(Text);
        if (!D || String(D,TEXT("schema"))!=TEXT("vista.live-command/v1")) continue;
        FString Code=TEXT("LIVE_REJECTED");const FString Op=String(D,TEXT("op"));
        auto* C=FindComponentByClass<UVistaCompanionComponent>();
        // Actor lease stays valid across its own completed action generations,
        // but can never survive a scene reset. Object actions still check reach,
        // current state and transaction preconditions in BeginAction.
        if (String(D,TEXT("session_id"))!=SessionId ||
            (Op==TEXT("actor")?Number(D,TEXT("scene_epoch"),-1)!=SceneEpoch:Number(D,TEXT("generation"),-1)!=Generation) ||
            Number(D,TEXT("expires_clock_s"),-1)<SceneClock || Number(D,TEXT("expires_clock_s"))>SceneClock+15)
            Code=TEXT("STALE_LIVE_REJECTED");
        else if (Op==TEXT("speech") && C && C->Companion)
        {
            const TSharedPtr<FJsonObject>* Speech;
            if (D->TryGetObjectField(TEXT("speech"),Speech))
            {
                const auto S=*Speech;const FString Role=String(S,TEXT("role"));TArray<uint8> PCM;
                const int32 Rate=Number(S,TEXT("sample_rate"));const TArray<TSharedPtr<FJsonValue>>* Mouth;
                if ((Role==TEXT("human") || Role==TEXT("assistant") || Role==TEXT("phone")) && String(S,TEXT("language"))==TEXT("en") &&
                    Rate>=8000 && Rate<=48000 && S->TryGetArrayField(TEXT("mouth"),Mouth) &&
                    FBase64::Decode(String(S,TEXT("pcm_b64")),PCM) && PCM.Num()>2 && PCM.Num()<=Rate*2*30 && PCM.Num()%2==0)
                {
                    C->Companion->StopSpeech();
                    if (HumanVoice) HumanVoice->Stop();
                    if (Role==TEXT("assistant"))
                    {
                        if (String(D,TEXT("cause"))==TEXT("jev:notice_water") && C->Companion->AssistTarget==TEXT("stove")) C->Companion->CancelAssist();
                        C->Companion->Speak(S);
                    }
                    else
                    {
                        if (!HumanVoice) {HumanVoice=NewObject<UAudioComponent>(this);HumanVoice->SetupAttachment(GetMesh(),TEXT("head"));HumanVoice->bAutoActivate=false;HumanVoice->RegisterComponent();}
                        HumanWave=NewObject<USoundWaveProcedural>(this);HumanWave->SetSampleRate(Rate);HumanWave->NumChannels=1;
                        HumanWave->Duration=PCM.Num()/(2.f*Rate);HumanWave->SoundGroup=SOUNDGROUP_Voice;HumanWave->QueueAudio(PCM.GetData(),PCM.Num());
                        HumanAudioBytes=PCM.Num();HumanAudioRate=Rate;HumanMouth.Empty();bPrivateHumanLipSync=Role==TEXT("human");
                        for (const auto& V:*Mouth) if (V->AsArray().Num()==3) HumanMouth.Add(V->AsArray()[0]->AsNumber());
                        HumanVoice->SetSound(HumanWave);HumanVoice->Play();
                    }
                    C->Reply=(Role==TEXT("assistant")?TEXT("Assistant: "):(Role==TEXT("human")?TEXT("You: "):TEXT("Phone: ")))+String(S,TEXT("text"));
                    C->Status=TEXT("Live · Jev");C->NoticeUntil=GetWorld()->GetTimeSeconds()+PCM.Num()/(2.f*Rate);Code=TEXT("SPEECH_STARTED");
                }
            }
        }
        else if (Op==TEXT("caption") && C && C->Companion)
        {
            const FString Line=String(D,TEXT("text"));
            if (!Line.IsEmpty() && Line.Len()<=320)
            {C->Reply=TEXT("Assistant: ")+Line;C->NoticeUntil=GetWorld()->GetTimeSeconds()+25;Code=TEXT("CAPTION_SET");}
        }
        else if (Op==TEXT("stop_speech") && C && C->Companion)
        {C->Companion->StopSpeech();if (HumanVoice) HumanVoice->Stop();C->NoticeUntil=0;Code=TEXT("SPEECH_STOPPED");}
        else if (Op==TEXT("stop") && C && C->Companion)
        {C->Companion->StopSpeech();C->Companion->CancelAssist();if (HumanVoice) HumanVoice->Stop();C->NoticeUntil=0;Code=TEXT("LIVE_STOPPED");}
        else if (Op==TEXT("follow") && C) {C->Follow(Bool(D,TEXT("enabled")));Code=TEXT("FOLLOW_SET");}
        else if (Op==TEXT("assist") && C && C->Companion)
        {
            const FString Target=String(D,TEXT("target"));auto* E=Resolve(Target);
            if (E && (Target==TEXT("stove") || Target==TEXT("faucet")) && Bool(E->State,TEXT("active")) &&
                C->Companion->BeginAssist(Target,E->Actor.Get(),ControlPoint(*E))) Code=TEXT("ASSIST_ACCEPTED");
            else Code=TEXT("ASSIST_APPROACH_REJECTED");
        }
        else if (Op==TEXT("event"))
        {
            const FString Id=String(D,TEXT("event_id"));
            if (Id==TEXT("mmg_001") || Id==TEXT("mmg_021") || Id==TEXT("mmg_044")) StartEvent(Id,Code,false);
        }
        else if (Op==TEXT("actor")) DirectorCommand(D,Code);
        else if (Op==TEXT("scene")) ApplyLiveScene(String(D,TEXT("layout")),Number(D,TEXT("room")),Code);
        else if (Op==TEXT("micro_scene"))
        {
            const TSharedPtr<FJsonObject>* Recipe;
            if (D->TryGetObjectField(TEXT("recipe"),Recipe)) ApplyMicroScene(*Recipe,Code);
        }
        auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("schema"),TEXT("vista.live-reply/v1"));
        R->SetStringField(TEXT("op"),Op);R->SetStringField(TEXT("code"),Code);R->SetStringField(TEXT("session_id"),SessionId);
        R->SetNumberField(TEXT("generation"),Generation);R->SetNumberField(TEXT("clock_s"),SceneClock);
        if (Op==TEXT("scene")) {R->SetStringField(TEXT("placement_diagnostic"),LiveLayoutDiagnostic);R->SetNumberField(TEXT("new_props"),LiveDressing.Num());}
        if (Op==TEXT("micro_scene") && ForgeReceipt.IsValid()) R->SetObjectField(TEXT("assembly"),ForgeReceipt);
        AppendReceipt(R);PublishState();const FString ReplyDir=BridgeDir/TEXT("live_responses");IFileManager::Get().MakeDirectory(*ReplyDir,true);
        AtomicSave(ReplyDir/File,Encode(R));
    }
}
