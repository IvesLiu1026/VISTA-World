#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "PhysicsEngine/PhysicsHandleComponent.h"

using namespace HomeJson;

TSharedRef<FJsonObject> AHomeActionsCharacter::MakeState() const
{
    auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),TEXT("vista.home-runtime-state/v1"));
    O->SetStringField(TEXT("audience"),TEXT("privileged_runtime_review_only"));O->SetStringField(TEXT("session_id"),SessionId);
    O->SetStringField(TEXT("revision"),Revision);O->SetNumberField(TEXT("generation"),Generation);
    O->SetNumberField(TEXT("clock_s"),SceneClock);O->SetNumberField(TEXT("frame_time_s"),GetWorld()->GetDeltaSeconds());
    O->SetBoolField(TEXT("ready"),bSceneReady);O->SetBoolField(TEXT("third_person"),bThirdPerson);
    O->SetBoolField(TEXT("clean_observation"),bCleanObservation);
    O->SetStringField(TEXT("active_command"),ActiveId);O->SetStringField(TEXT("action"),ActiveId.IsEmpty()?TEXT(""):ActionId);
    O->SetStringField(TEXT("held_id"),HeldId);O->SetStringField(TEXT("seat_id"),SeatId);
    O->SetStringField(TEXT("standing_on"),StandingOn);
    O->SetStringField(TEXT("focus_id"),FocusId);O->SetStringField(TEXT("last_code"),LastCode);
    O->SetStringField(TEXT("event_id"),EventId);O->SetStringField(TEXT("event_status"),EventStatus);
    O->SetStringField(TEXT("terminal_condition"),TerminalCondition);O->SetNumberField(TEXT("event_time_s"),EventTime);
    O->SetArrayField(TEXT("player_cm"),Values(GetActorLocation()));O->SetArrayField(TEXT("velocity_cm_s"),Values(GetVelocity()));
    O->SetStringField(TEXT("player_room"),RoomAt(GetActorLocation()));
    O->SetStringField(TEXT("contact_measurement"),TEXT("post_animation_wrist"));
    if (FineContactSnapshot) O->SetObjectField(TEXT("fine_contact"),FineContactSnapshot);
    if (ReachAlpha>.95f) O->SetNumberField(TEXT("right_contact_error_cm"),RightContactError);
    else O->SetField(TEXT("right_contact_error_cm"),MakeShared<FJsonValueNull>());
    if (LeftReachAlpha>.95f) O->SetNumberField(TEXT("left_contact_error_cm"),LeftContactError);
    else O->SetField(TEXT("left_contact_error_cm"),MakeShared<FJsonValueNull>());
    O->SetNumberField(TEXT("seated_alpha"),SeatedAlpha);O->SetNumberField(TEXT("crouch_alpha"),CrouchAlpha);O->SetNumberField(TEXT("fall_alpha"),FallAlpha);
    O->SetBoolField(TEXT("physics_grip"),GripHandle->GrabbedComponent!=nullptr);
    TArray<TSharedPtr<FJsonValue>> A;for (const auto& S:AvailableActions()) A.Add(MakeShared<FJsonValueString>(S));
    O->SetArrayField(TEXT("available_actions"),A);A.Empty();
    TArray<FString> Ids;Entities.GetKeys(Ids);Ids.Sort();
    for (const auto& Id:Ids)
    {
        const auto& E=Entities[Id];auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("id"),Id);
        Row->SetStringField(TEXT("short_id"),E.ShortId);Row->SetStringField(TEXT("kind"),E.Kind);Row->SetObjectField(TEXT("state"),Copy(E.State));
        Row->SetNumberField(TEXT("aperture"),E.Aperture);Row->SetArrayField(TEXT("control_cm"),Values(ControlPoint(E)));
        if (E.Actor.IsValid())
        {
            Row->SetArrayField(TEXT("position_cm"),Values(E.Actor->GetActorLocation()));
            const auto R=E.Actor->GetActorRotation();Row->SetArrayField(TEXT("rotation_deg"),Values(FVector(R.Pitch,R.Yaw,R.Roll)));
            Row->SetBoolField(TEXT("simulated"),E.Mesh->IsSimulatingPhysics());Row->SetStringField(TEXT("room"),RoomAt(E.Actor->GetActorLocation()));
            Row->SetArrayField(TEXT("velocity_cm_s"),Values(E.Mesh->GetPhysicsLinearVelocity()));
        }
        A.Add(MakeShared<FJsonValueObject>(Row));
    }
    O->SetArrayField(TEXT("entities"),A);return O;
}

void AHomeActionsCharacter::PublishState()
{
    if (!bSceneReady) return;
    AtomicSave(BridgeDir/TEXT("state.json"),Encode(MakeState()));
}

void AHomeActionsCharacter::AppendReceipt(const TSharedPtr<FJsonObject>& Record)
{
    const FString Text=Encode(Record);
    FFileHelper::SaveStringToFile(Text+TEXT("\n"),*(BridgeDir/TEXT("receipts.jsonl")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,&IFileManager::Get(),FILEWRITE_Append);
    UE_LOG(LogTemp,Display,TEXT("HOME_RECEIPT %s"),*Text);
    const FString Id=String(Record,TEXT("command_id"));
    if (!Id.IsEmpty())
    {
        IFileManager::Get().MakeDirectory(*(BridgeDir/TEXT("responses")),true);
        AtomicSave(BridgeDir/TEXT("responses")/(Id+TEXT(".json")),Text);
    }
}

void AHomeActionsCharacter::Reply(const TSharedPtr<FJsonObject>& Request,const FString& Code)
{
    auto R=MakeShared<FJsonObject>();const FString Id=String(Request,TEXT("command_id"));
    R->SetStringField(TEXT("schema"),TEXT("vista.home-command-reply/v1"));R->SetStringField(TEXT("command_id"),Id);
    R->SetStringField(TEXT("operation"),String(Request,TEXT("operation")));R->SetStringField(TEXT("code"),Code);
    R->SetStringField(TEXT("signature"),RequestSignature(Request));R->SetNumberField(TEXT("generation_after"),Generation);
    R->SetStringField(TEXT("session_id"),SessionId);
    R->SetStringField(TEXT("status"),Code==TEXT("EVENT_STARTED") || Code==TEXT("SCENE_RESET") || Code==TEXT("OBSERVED")?TEXT("succeeded"):TEXT("rejected"));
    if (!Ledger.Contains(Id)) Ledger.Add(Id,R);AppendReceipt(R);
}

void AHomeActionsCharacter::PollBridge()
{
    const FString Directory=BridgeDir/TEXT("requests");TArray<FString> Files;
    IFileManager::Get().MakeDirectory(*Directory,true);IFileManager::Get().FindFiles(Files,*(Directory/TEXT("*.json")),true,false);Files.Sort();
    for (const FString& File:Files)
    {
        if (ProcessedRequests.Contains(File)) continue;ProcessedRequests.Add(File);
        if (IFileManager::Get().FileSize(*(Directory/File))>16384) continue;
        FString Text;if (!FFileHelper::LoadFileToString(Text,*(Directory/File))) continue;
        auto R=Decode(Text);if (!R) continue;
        const FString Id=String(R,TEXT("command_id"));
        bool Valid=!Id.IsEmpty() && Id.Len()<=80;
        for (TCHAR C:Id) Valid&=FChar::IsAlnum(C) || C==TCHAR('-') || C==TCHAR('_');
        if (!Valid) continue; // Untrusted filenames/ids never become output paths.
        if (String(R,TEXT("schema"))!=TEXT("vista.home-command/v1")) {Reply(R,TEXT("SCHEMA_MISMATCH"));continue;}
        const TSet<FString> Allowed={TEXT("schema"),TEXT("command_id"),TEXT("session_id"),TEXT("revision"),TEXT("expected_generation"),
            TEXT("operation"),TEXT("action"),TEXT("target_id"),TEXT("secondary_target_id"),TEXT("event_id"),TEXT("active_command_id")};
        bool Shape=true;
        for (const auto& Field:R->Values)
            Shape&=Allowed.Contains(Field.Key) && Field.Value->Type==(Field.Key==TEXT("expected_generation")?EJson::Number:EJson::String);
        const double Expected=Number(R,TEXT("expected_generation"),-1);
        Shape&=FMath::IsFinite(Expected) && Expected>=0 && Expected<=MAX_int32 && FMath::FloorToDouble(Expected)==Expected;
        if (!Shape)
        {
            if (Ledger.Contains(Id))
            {
                auto Invalid=MakeShared<FJsonObject>();Invalid->SetStringField(TEXT("command_id"),Id);
                Invalid->SetStringField(TEXT("status"),TEXT("rejected"));Invalid->SetStringField(TEXT("code"),TEXT("INVALID_COMMAND_SHAPE"));AppendReceipt(Invalid);
            }
            else Reply(R,TEXT("INVALID_COMMAND_SHAPE"));
            continue;
        }
        if (auto* Previous=Ledger.Find(Id))
        {
            if (String(*Previous,TEXT("signature"))==RequestSignature(R))
            {
                // Replay returns the cached result without publishing a second
                // terminal observation into the episode ledger.
                const FString Path=BridgeDir/TEXT("responses")/(Id+TEXT(".json"));
                AtomicSave(Path,Encode(*Previous));
            }
            else
            {
                auto Conflict=MakeShared<FJsonObject>();Conflict->SetStringField(TEXT("command_id"),Id);
                Conflict->SetStringField(TEXT("status"),TEXT("rejected"));Conflict->SetStringField(TEXT("code"),TEXT("COMMAND_ID_CONFLICT"));AppendReceipt(Conflict);
            }
            continue;
        }

        if (String(R,TEXT("session_id"))!=SessionId || String(R,TEXT("revision"))!=Revision) {Reply(R,TEXT("SESSION_OR_REVISION_MISMATCH"));continue;}
        if (Number(R,TEXT("expected_generation"),-1)!=Generation) {Reply(R,TEXT("GENERATION_MISMATCH"));continue;}
        const FString Op=String(R,TEXT("operation"));FString Code;
        if (Op==TEXT("action"))
        {
            const FString Target=String(R,TEXT("target_id")),Secondary=String(R,TEXT("secondary_target_id"));
            if ((!Target.IsEmpty() && !Entities.Contains(Target)) || (!Secondary.IsEmpty() && !Entities.Contains(Secondary)))
            {Reply(R,TEXT("EXACT_TARGET_ID_REQUIRED"));continue;}
            const bool Started=BeginAction(Id,String(R,TEXT("action")),Target,Secondary,Code);
            if (auto* L=Ledger.Find(Id)) (*L)->SetStringField(TEXT("signature"),RequestSignature(R));
            else if (!Started) Reply(R,Code);
        }
        else if (Op==TEXT("event_start"))
        {if (!ActiveId.IsEmpty()) Code=TEXT("BUSY");else StartEvent(String(R,TEXT("event_id")),Code);Reply(R,Code);}
        else if (Op==TEXT("reset")) {ResetScene(Code);Reply(R,Code);}
        else if (Op==TEXT("cancel"))
        {
            if (ActiveId.IsEmpty() || ActiveId!=String(R,TEXT("active_command_id"))) Reply(R,TEXT("ACTIVE_COMMAND_MISMATCH"));
            else {HomeCancel();Reply(R,TEXT("OBSERVED"));}
        }
        else if (Op==TEXT("observe")) Reply(R,TEXT("OBSERVED"));
        else Reply(R,TEXT("OPERATION_NOT_SUPPORTED"));
    }
}
