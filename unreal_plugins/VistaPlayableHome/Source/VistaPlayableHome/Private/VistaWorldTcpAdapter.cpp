#include "VistaWorldTcpAdapter.h"

#include "Async/Async.h"
#include "Common/TcpListener.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "Interfaces/IPv4/IPv4Endpoint.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "SocketSubsystem.h"
#include "Sockets.h"
#include "VistaPlayableHomeRuntimeSubsystem.h"

namespace
{
constexpr int32 MaxRequestBytes = 64 * 1024;
constexpr int32 MaxResponseBytes = 64 * 1024;
constexpr double ReadTimeoutSeconds = 2.0;
constexpr uint32 DispatchTimeoutMilliseconds = 10 * 1000;

struct FDispatchState final
{
    FDispatchState() : Completed(FPlatformProcess::GetSynchEventFromPool(true)) {}
    ~FDispatchState() { FPlatformProcess::ReturnSynchEventToPool(Completed); }

    FEvent* Completed = nullptr;
    FCriticalSection Mutex;
    bool bCanceled = false;
    FString Response;
};

TSet<FString> KeySet(std::initializer_list<const TCHAR*> Values)
{
    TSet<FString> Result;
    for (const TCHAR* Value : Values)
    {
        Result.Add(Value);
    }
    return Result;
}

bool ExactKeys(const TSharedPtr<FJsonObject>& Object,
               const TSet<FString>& Required,
               const TSet<FString>& Optional)
{
    if (!Object.IsValid())
    {
        return false;
    }
    for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : Object->Values)
    {
        if (!Required.Contains(Pair.Key) && !Optional.Contains(Pair.Key))
        {
            return false;
        }
    }
    for (const FString& Key : Required)
    {
        if (!Object->Values.Contains(Key))
        {
            return false;
        }
    }
    return Object->Values.Num() >= Required.Num() &&
           Object->Values.Num() <= Required.Num() + Optional.Num();
}

bool IsCommandId(const FString& Value)
{
    if (Value.Len() != 28 || !Value.StartsWith(TEXT("vwc-")))
    {
        return false;
    }
    for (int32 Index = 4; Index < Value.Len(); ++Index)
    {
        if (!FChar::IsHexDigit(Value[Index]) || FChar::IsUpper(Value[Index]))
        {
            return false;
        }
    }
    return true;
}

bool IsRevision(const FString& Value)
{
    if (Value.IsEmpty() || Value.Len() > 80)
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        if (!((Character >= TEXT('a') && Character <= TEXT('z')) ||
              (Character >= TEXT('0') && Character <= TEXT('9')) ||
              Character == TEXT('.') || Character == TEXT('_') || Character == TEXT('-')))
        {
            return false;
        }
    }
    return true;
}

bool IsAsciiAlnum(const TCHAR Character)
{
    return (Character >= TEXT('A') && Character <= TEXT('Z')) ||
           (Character >= TEXT('a') && Character <= TEXT('z')) ||
           (Character >= TEXT('0') && Character <= TEXT('9'));
}

bool IsActionId(const FString& Value)
{
    if (Value.IsEmpty() || Value.Len() > 80 || !IsAsciiAlnum(Value[0]))
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        if (!(IsAsciiAlnum(Character) || Character == TEXT('.') ||
              Character == TEXT('_') || Character == TEXT('-')))
        {
            return false;
        }
    }
    return true;
}

bool IsSemanticId(const FString& Value)
{
    if (Value.IsEmpty() || Value.Len() > 240 || !IsAsciiAlnum(Value[0]))
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        if (!(IsAsciiAlnum(Character) || Character == TEXT('.') ||
              Character == TEXT('_') || Character == TEXT('/') || Character == TEXT('-')))
        {
            return false;
        }
    }
    return true;
}

bool IsPlacementAnchorId(const FString& Value)
{
    if (Value.IsEmpty() || Value.Len() > 96 ||
        Value[0] < TEXT('a') || Value[0] > TEXT('z'))
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        if (!((Character >= TEXT('a') && Character <= TEXT('z')) ||
              (Character >= TEXT('0') && Character <= TEXT('9')) ||
              Character == TEXT('_')))
        {
            return false;
        }
    }
    return true;
}

bool ReadString(const TSharedPtr<FJsonObject>& Object,
                const TCHAR* Field,
                FString& Output)
{
    return Object->TryGetStringField(Field, Output);
}

bool ReadGeneration(const TSharedPtr<FJsonObject>& Object, int32& Output)
{
    double Number = 0.0;
    if (!Object->TryGetNumberField(TEXT("session_generation"), Number) ||
        !FMath::IsFinite(Number) || Number < 0.0 || Number > MAX_int32 ||
        FMath::FloorToDouble(Number) != Number)
    {
        return false;
    }
    Output = static_cast<int32>(Number);
    return true;
}

FString SerializeObject(const TSharedRef<FJsonObject>& Object)
{
    FString Output;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
    FJsonSerializer::Serialize(Object, Writer);
    return Output;
}

FString ErrorResponse(const FString& CommandId, const TCHAR* Code)
{
    const TSharedRef<FJsonObject> Response = MakeShared<FJsonObject>();
    Response->SetStringField(TEXT("command_id"), CommandId);
    Response->SetStringField(TEXT("status"), TEXT("error"));
    Response->SetStringField(TEXT("code"), Code);
    return SerializeObject(Response);
}

TSharedRef<FJsonObject> TransformJson(const FTransform& Value)
{
    const TSharedRef<FJsonObject> Transform = MakeShared<FJsonObject>();
    const FVector Location = Value.GetLocation();
    const FRotator Rotation = Value.Rotator();
    const FVector Scale = Value.GetScale3D();
    Transform->SetArrayField(TEXT("location_cm"), {
        MakeShared<FJsonValueNumber>(Location.X),
        MakeShared<FJsonValueNumber>(Location.Y),
        MakeShared<FJsonValueNumber>(Location.Z)});
    Transform->SetArrayField(TEXT("rotation_deg"), {
        // The public HouseSpec/World API contract is XYZ Euler. FRotator names
        // those same axis rotations Roll(X), Pitch(Y), and Yaw(Z).
        MakeShared<FJsonValueNumber>(Rotation.Roll),
        MakeShared<FJsonValueNumber>(Rotation.Pitch),
        MakeShared<FJsonValueNumber>(Rotation.Yaw)});
    Transform->SetArrayField(TEXT("scale"), {
        MakeShared<FJsonValueNumber>(Scale.X),
        MakeShared<FJsonValueNumber>(Scale.Y),
        MakeShared<FJsonValueNumber>(Scale.Z)});
    return Transform;
}

TSharedRef<FJsonObject> RuntimeStateJson(const FVistaEntityRuntimeState& State)
{
    const TSharedRef<FJsonObject> Output = MakeShared<FJsonObject>();
    Output->SetStringField(TEXT("semantic_id"), State.SemanticId);
    Output->SetBoolField(TEXT("hidden"), State.bHidden);
    Output->SetBoolField(TEXT("portable"), State.bPortable);
    Output->SetObjectField(TEXT("transform"), TransformJson(State.Transform));
    const TSharedRef<FJsonObject> Values = MakeShared<FJsonObject>();
    for (const TPair<FName, FString>& Pair : State.Values)
    {
        // FName preserves the casing of the first process-local registration,
        // so Editor and packaged builds can otherwise emit different wire keys.
        Values->SetStringField(Pair.Key.ToString().ToLower(), Pair.Value);
    }
    Output->SetObjectField(TEXT("values"), Values);
    return Output;
}

TSharedRef<FJsonObject> PhysicalStateJson(
    const FVistaPickupPhysicalStateSnapshot& State)
{
    const TSharedRef<FJsonObject> Output = MakeShared<FJsonObject>();
    Output->SetObjectField(TEXT("world_transform"), TransformJson(State.WorldTransform));
    Output->SetBoolField(TEXT("simulate_physics"), State.bSimulatePhysics);
    Output->SetNumberField(TEXT("collision_enabled"), State.CollisionEnabled);
    Output->SetStringField(
        TEXT("collision_profile"), State.CollisionProfileName.ToString());
    Output->SetArrayField(TEXT("linear_velocity_cm_s"), {
        MakeShared<FJsonValueNumber>(State.LinearVelocity.X),
        MakeShared<FJsonValueNumber>(State.LinearVelocity.Y),
        MakeShared<FJsonValueNumber>(State.LinearVelocity.Z)});
    Output->SetArrayField(TEXT("angular_velocity_deg_s"), {
        MakeShared<FJsonValueNumber>(State.AngularVelocityDegrees.X),
        MakeShared<FJsonValueNumber>(State.AngularVelocityDegrees.Y),
        MakeShared<FJsonValueNumber>(State.AngularVelocityDegrees.Z)});
    Output->SetBoolField(
        TEXT("has_attachment_parent"), State.bHasAttachmentParent);
    Output->SetStringField(
        TEXT("attachment_parent_owner_semantic_id"),
        State.AttachmentParentOwnerSemanticId);
    Output->SetStringField(
        TEXT("attachment_parent_component"),
        State.AttachmentParentComponentName.ToString());
    Output->SetStringField(
        TEXT("attachment_socket"), State.AttachmentSocketName.ToString());
    Output->SetObjectField(
        TEXT("attachment_relative_transform"),
        TransformJson(State.AttachmentRelativeTransform));
    Output->SetBoolField(TEXT("held"), State.bHeld);
    Output->SetStringField(TEXT("carrier_semantic_id"), State.CarrierSemanticId);
    Output->SetStringField(
        TEXT("inventory_carrier_semantic_id"),
        State.InventoryCarrierSemanticId);
    Output->SetBoolField(
        TEXT("inventory_slot_occupied"), State.bInventorySlotOccupied);
    Output->SetStringField(
        TEXT("inventory_item_semantic_id"),
        State.InventoryItemSemanticId);
    Output->SetStringField(
        TEXT("placed_at_semantic_id"), State.PlacedAtSemanticId);
    return Output;
}

const TCHAR* ActionPhaseText(EVistaActionPhase Phase)
{
    switch (Phase)
    {
    case EVistaActionPhase::Approach: return TEXT("approach");
    case EVistaActionPhase::Align: return TEXT("align");
    case EVistaActionPhase::Animate: return TEXT("animate");
    case EVistaActionPhase::ContactCommit: return TEXT("contact_commit");
    case EVistaActionPhase::Complete: return TEXT("complete");
    case EVistaActionPhase::RollingBack: return TEXT("rolling_back");
    case EVistaActionPhase::Failed: return TEXT("failed");
    default: return TEXT("idle");
    }
}

const TCHAR* AffordanceText(const EVistaAffordance Affordance)
{
    switch (Affordance)
    {
    case EVistaAffordance::Open: return TEXT("open");
    case EVistaAffordance::Close: return TEXT("close");
    case EVistaAffordance::PickUp: return TEXT("pick_up");
    case EVistaAffordance::Drop: return TEXT("drop");
    case EVistaAffordance::Place: return TEXT("place");
    case EVistaAffordance::Toggle: return TEXT("toggle");
    case EVistaAffordance::Sit: return TEXT("sit");
    case EVistaAffordance::Press: return TEXT("press");
    case EVistaAffordance::TurnOn: return TEXT("turn_on");
    case EVistaAffordance::TurnOff: return TEXT("turn_off");
    case EVistaAffordance::Pour: return TEXT("pour");
    case EVistaAffordance::Stand:
        return TEXT("stand");
    default: return TEXT("inspect");
    }
}

const TCHAR* ActionTransactionStatusText(EVistaActionTransactionStatus Status)
{
    switch (Status)
    {
    case EVistaActionTransactionStatus::Running: return TEXT("running");
    case EVistaActionTransactionStatus::Succeeded: return TEXT("succeeded");
    case EVistaActionTransactionStatus::Failed: return TEXT("failed");
    case EVistaActionTransactionStatus::TimedOut: return TEXT("timed_out");
    case EVistaActionTransactionStatus::Canceled: return TEXT("canceled");
    default: return TEXT("idle");
    }
}

TSharedRef<FJsonObject> ActionTransactionJson(
    const FVistaActionTransactionRecord& Transaction)
{
    const TSharedRef<FJsonObject> Output = MakeShared<FJsonObject>();
    Output->SetStringField(TEXT("phase"), ActionPhaseText(Transaction.Phase));
    Output->SetStringField(
        TEXT("transaction_status"),
        ActionTransactionStatusText(Transaction.Status));
    Output->SetStringField(TEXT("code"), Transaction.Code.ToString());
    Output->SetStringField(
        TEXT("affordance"), AffordanceText(Transaction.Affordance));
    Output->SetStringField(
        TEXT("requester_semantic_id"), Transaction.RequesterSemanticId);
    Output->SetStringField(TEXT("target_semantic_id"), Transaction.TargetSemanticId);
    if (Transaction.SecondaryTargetSemanticId.IsEmpty())
    {
        Output->SetField(
            TEXT("secondary_target_semantic_id"),
            MakeShared<FJsonValueNull>());
    }
    else
    {
        Output->SetStringField(
            TEXT("secondary_target_semantic_id"),
            Transaction.SecondaryTargetSemanticId);
    }
    if (Transaction.PlacementAnchorSemanticId.IsEmpty())
    {
        Output->SetField(
            TEXT("placement_anchor_semantic_id"), MakeShared<FJsonValueNull>());
    }
    else
    {
        Output->SetStringField(
            TEXT("placement_anchor_semantic_id"),
            Transaction.PlacementAnchorSemanticId);
    }
    TArray<TSharedPtr<FJsonValue>> PhaseHistory;
    for (EVistaActionPhase Phase : Transaction.PhaseHistory)
    {
        PhaseHistory.Add(MakeShared<FJsonValueString>(ActionPhaseText(Phase)));
    }
    Output->SetArrayField(TEXT("phase_history"), PhaseHistory);
    Output->SetBoolField(
        TEXT("contact_mutation_attempted"),
        Transaction.bContactMutationAttempted);
    Output->SetBoolField(TEXT("contact_committed"), Transaction.bContactCommitted);
    Output->SetNumberField(
        TEXT("physical_mutation_count"), Transaction.PhysicalMutationCount);
    Output->SetNumberField(
        TEXT("state_mutation_count"), Transaction.StateMutationCount);
    Output->SetNumberField(
        TEXT("liquid_transfer_ml"), Transaction.LiquidTransferMilliliters);
    Output->SetBoolField(
        TEXT("target_reservation_acquired"),
        Transaction.bTargetReservationAcquired);
    Output->SetBoolField(
        TEXT("target_reservation_released"),
        Transaction.bTargetReservationReleased);
    Output->SetBoolField(
        TEXT("secondary_target_reservation_acquired"),
        Transaction.bSecondaryTargetReservationAcquired);
    Output->SetBoolField(
        TEXT("secondary_target_reservation_released"),
        Transaction.bSecondaryTargetReservationReleased);
    Output->SetBoolField(TEXT("rollback_attempted"), Transaction.bRollbackAttempted);
    Output->SetBoolField(TEXT("rolled_back"), Transaction.bRolledBack);
    Output->SetBoolField(
        TEXT("requester_transform_restored"),
        Transaction.bRequesterTransformRestored);
    Output->SetObjectField(
        TEXT("requester_before_transform"),
        TransformJson(Transaction.RequesterBeforeTransform));
    Output->SetObjectField(
        TEXT("requester_contact_transform"),
        TransformJson(Transaction.RequesterContactTransform));
    Output->SetObjectField(
        TEXT("requester_after_transform"),
        TransformJson(Transaction.RequesterAfterTransform));
    if (Transaction.RollbackCode.IsNone())
    {
        Output->SetField(TEXT("rollback_code"), MakeShared<FJsonValueNull>());
    }
    else
    {
        Output->SetStringField(
            TEXT("rollback_code"), Transaction.RollbackCode.ToString());
    }
    if (Transaction.bHasBeforeState)
    {
        Output->SetObjectField(
            TEXT("before_state"), RuntimeStateJson(Transaction.BeforeState));
    }
    else
    {
        Output->SetField(TEXT("before_state"), MakeShared<FJsonValueNull>());
    }
    if (Transaction.bHasContactState)
    {
        Output->SetObjectField(
            TEXT("contact_state"), RuntimeStateJson(Transaction.ContactState));
    }
    else
    {
        Output->SetField(TEXT("contact_state"), MakeShared<FJsonValueNull>());
    }
    if (Transaction.bHasAfterState)
    {
        Output->SetObjectField(
            TEXT("after_state"), RuntimeStateJson(Transaction.AfterState));
    }
    else
    {
        Output->SetField(TEXT("after_state"), MakeShared<FJsonValueNull>());
    }
    if (Transaction.bHasBeforeSecondaryState)
    {
        Output->SetObjectField(
            TEXT("before_secondary_state"),
            RuntimeStateJson(Transaction.BeforeSecondaryState));
    }
    else
    {
        Output->SetField(
            TEXT("before_secondary_state"), MakeShared<FJsonValueNull>());
    }
    if (Transaction.bHasContactSecondaryState)
    {
        Output->SetObjectField(
            TEXT("contact_secondary_state"),
            RuntimeStateJson(Transaction.ContactSecondaryState));
    }
    else
    {
        Output->SetField(
            TEXT("contact_secondary_state"), MakeShared<FJsonValueNull>());
    }
    if (Transaction.bHasAfterSecondaryState)
    {
        Output->SetObjectField(
            TEXT("after_secondary_state"),
            RuntimeStateJson(Transaction.AfterSecondaryState));
    }
    else
    {
        Output->SetField(
            TEXT("after_secondary_state"), MakeShared<FJsonValueNull>());
    }
    if (Transaction.bHasBeforePhysicalState)
    {
        Output->SetObjectField(
            TEXT("before_physical_state"),
            PhysicalStateJson(Transaction.BeforePhysicalState));
    }
    else
    {
        Output->SetField(
            TEXT("before_physical_state"), MakeShared<FJsonValueNull>());
    }
    if (Transaction.bHasContactPhysicalState)
    {
        Output->SetObjectField(
            TEXT("contact_physical_state"),
            PhysicalStateJson(Transaction.ContactPhysicalState));
    }
    else
    {
        Output->SetField(
            TEXT("contact_physical_state"), MakeShared<FJsonValueNull>());
    }
    if (Transaction.bHasAfterPhysicalState)
    {
        Output->SetObjectField(
            TEXT("after_physical_state"),
            PhysicalStateJson(Transaction.AfterPhysicalState));
    }
    else
    {
        Output->SetField(
            TEXT("after_physical_state"), MakeShared<FJsonValueNull>());
    }
    return Output;
}

FString ResultResponse(const FVistaLiveCommandResult& Result,
                       bool bIncludeAuthoritativeStatus = false)
{
    const TSharedRef<FJsonObject> Response = MakeShared<FJsonObject>();
    Response->SetStringField(TEXT("command_id"), Result.CommandId.ToString());
    Response->SetStringField(TEXT("status"), Result.bSucceeded ? TEXT("success") : TEXT("error"));
    Response->SetStringField(TEXT("code"), Result.Code.ToString());
    Response->SetNumberField(TEXT("session_generation"), Result.SessionGeneration);
    if (bIncludeAuthoritativeStatus)
    {
        Response->SetStringField(TEXT("world_revision"), Result.WorldRevision.ToString());
        const TCHAR* EventStatus = TEXT("inactive");
        switch (Result.EventStatus)
        {
        case EVistaEventStatus::Applying: EventStatus = TEXT("applying"); break;
        case EVistaEventStatus::Active: EventStatus = TEXT("active"); break;
        case EVistaEventStatus::Succeeded: EventStatus = TEXT("succeeded"); break;
        case EVistaEventStatus::Failed: EventStatus = TEXT("failed"); break;
        case EVistaEventStatus::TimedOut: EventStatus = TEXT("timed_out"); break;
        case EVistaEventStatus::Resetting: EventStatus = TEXT("resetting"); break;
        default: break;
        }
        Response->SetStringField(TEXT("event_status"), EventStatus);
        if (Result.ActiveEventId.IsNone())
        {
            Response->SetField(TEXT("active_event"), MakeShared<FJsonValueNull>());
        }
        else
        {
            Response->SetStringField(TEXT("active_event"), Result.ActiveEventId.ToString());
        }
    }
    if (!Result.TargetSemanticId.IsEmpty())
    {
        Response->SetStringField(TEXT("target_semantic_id"), Result.TargetSemanticId);
    }
    if (!Result.State.SemanticId.IsEmpty())
    {
        Response->SetObjectField(TEXT("state"), RuntimeStateJson(Result.State));
    }
    if (Result.bHasActionTransaction)
    {
        Response->SetObjectField(
            TEXT("action_transaction"),
            ActionTransactionJson(Result.ActionTransaction));
    }
    if (Result.QueuedActionCount >= 0)
    {
        const TSharedRef<FJsonObject> Npc = MakeShared<FJsonObject>();
        Npc->SetStringField(TEXT("action_id"), Result.NpcActionResult.ActionId.ToString());
        Npc->SetStringField(TEXT("code"), Result.NpcActionResult.Code.ToString());
        const TCHAR* ActionStatus = TEXT("idle");
        switch (Result.NpcActionResult.Status)
        {
        case EVistaNpcActionStatus::Queued: ActionStatus = TEXT("queued"); break;
        case EVistaNpcActionStatus::Running: ActionStatus = TEXT("running"); break;
        case EVistaNpcActionStatus::Succeeded: ActionStatus = TEXT("succeeded"); break;
        case EVistaNpcActionStatus::Failed: ActionStatus = TEXT("failed"); break;
        case EVistaNpcActionStatus::TimedOut: ActionStatus = TEXT("timed_out"); break;
        case EVistaNpcActionStatus::Blocked: ActionStatus = TEXT("blocked"); break;
        case EVistaNpcActionStatus::Canceled: ActionStatus = TEXT("canceled"); break;
        default: break;
        }
        Npc->SetStringField(TEXT("status"), ActionStatus);
        Npc->SetStringField(
            TEXT("target_semantic_id"), Result.NpcActionResult.TargetSemanticId);
        if (Result.NpcActionResult.SecondaryTargetSemanticId.IsEmpty())
        {
            Npc->SetField(
                TEXT("secondary_target_semantic_id"),
                MakeShared<FJsonValueNull>());
        }
        else
        {
            Npc->SetStringField(
                TEXT("secondary_target_semantic_id"),
                Result.NpcActionResult.SecondaryTargetSemanticId);
        }
        Npc->SetNumberField(TEXT("queued_action_count"), Result.QueuedActionCount);
        Npc->SetStringField(TEXT("current_room_id"), Result.NpcCurrentRoomId);

        if (Result.bHasLastCompletedNpcActionResult)
        {
            const FVistaNpcActionResult& Last = Result.LastCompletedNpcActionResult;
            const TSharedRef<FJsonObject> LastJson = MakeShared<FJsonObject>();
            LastJson->SetStringField(TEXT("action_id"), Last.ActionId.ToString());
            LastJson->SetStringField(TEXT("code"), Last.Code.ToString());
            const TCHAR* LastStatus = TEXT("idle");
            switch (Last.Status)
            {
            case EVistaNpcActionStatus::Queued: LastStatus = TEXT("queued"); break;
            case EVistaNpcActionStatus::Running: LastStatus = TEXT("running"); break;
            case EVistaNpcActionStatus::Succeeded: LastStatus = TEXT("succeeded"); break;
            case EVistaNpcActionStatus::Failed: LastStatus = TEXT("failed"); break;
            case EVistaNpcActionStatus::TimedOut: LastStatus = TEXT("timed_out"); break;
            case EVistaNpcActionStatus::Blocked: LastStatus = TEXT("blocked"); break;
            case EVistaNpcActionStatus::Canceled: LastStatus = TEXT("canceled"); break;
            default: break;
            }
            LastJson->SetStringField(TEXT("status"), LastStatus);
            LastJson->SetStringField(
                TEXT("target_semantic_id"), Last.TargetSemanticId);
            if (Last.SecondaryTargetSemanticId.IsEmpty())
            {
                LastJson->SetField(
                    TEXT("secondary_target_semantic_id"),
                    MakeShared<FJsonValueNull>());
            }
            else
            {
                LastJson->SetStringField(
                    TEXT("secondary_target_semantic_id"),
                    Last.SecondaryTargetSemanticId);
            }
            LastJson->SetStringField(
                TEXT("completed_room_id"), Result.LastCompletedNpcRoomId);
            Npc->SetObjectField(TEXT("last_completed_action"), LastJson);
        }
        else
        {
            Npc->SetField(
                TEXT("last_completed_action"), MakeShared<FJsonValueNull>());
        }

        const TSharedRef<FJsonObject> Animation = MakeShared<FJsonObject>();
        Animation->SetStringField(TEXT("action_id"), Result.AnimationResult.ActionId.ToString());
        Animation->SetStringField(TEXT("code"), Result.AnimationResult.Code.ToString());
        Animation->SetStringField(
            TEXT("completion_signal"), Result.AnimationResult.CompletionSignal.ToString());
        Animation->SetBoolField(
            TEXT("contact_observed"), Result.AnimationResult.bContactObserved);
        Animation->SetNumberField(TEXT("elapsed_sec"), Result.AnimationResult.ElapsedSeconds);
        const TCHAR* AnimationStatus = TEXT("idle");
        switch (Result.AnimationResult.Status)
        {
        case EVistaAnimationPlaybackStatus::Running: AnimationStatus = TEXT("running"); break;
        case EVistaAnimationPlaybackStatus::Succeeded: AnimationStatus = TEXT("succeeded"); break;
        case EVistaAnimationPlaybackStatus::Failed: AnimationStatus = TEXT("failed"); break;
        case EVistaAnimationPlaybackStatus::TimedOut: AnimationStatus = TEXT("timed_out"); break;
        case EVistaAnimationPlaybackStatus::Stopped: AnimationStatus = TEXT("stopped"); break;
        default: break;
        }
        Animation->SetStringField(TEXT("status"), AnimationStatus);
        Npc->SetObjectField(TEXT("animation"), Animation);
        Response->SetObjectField(TEXT("npc"), Npc);
    }
    return SerializeObject(Response);
}

FString NpcQueuePreflightResponse(
    const FVistaLiveNpcQueuePreflightResult& Result)
{
    const TSharedRef<FJsonObject> Response = MakeShared<FJsonObject>();
    Response->SetStringField(TEXT("command_id"), Result.CommandId.ToString());
    Response->SetStringField(
        TEXT("status"), Result.bSucceeded ? TEXT("success") : TEXT("error"));
    Response->SetStringField(TEXT("code"), Result.Code.ToString());
    Response->SetNumberField(
        TEXT("session_generation"), Result.SessionGeneration);
    Response->SetStringField(TEXT("queue_id"), Result.QueueId);
    Response->SetStringField(
        TEXT("target_semantic_id"), Result.TargetSemanticId);
    TArray<TSharedPtr<FJsonValue>> ActionIds;
    for (const FName ActionId : Result.ActionIds)
    {
        ActionIds.Add(MakeShared<FJsonValueString>(ActionId.ToString()));
    }
    Response->SetArrayField(TEXT("action_ids"), ActionIds);
    return SerializeObject(Response);
}

FString NpcQueuePreflightParseErrorResponse(
    UVistaPlayableHomeRuntimeSubsystem* Runtime,
    const FString& CommandId,
    FName Code)
{
    const TSharedRef<FJsonObject> Response = MakeShared<FJsonObject>();
    Response->SetStringField(TEXT("command_id"), CommandId);
    Response->SetStringField(TEXT("status"), TEXT("error"));
    Response->SetStringField(TEXT("code"), Code.ToString());
    const FVistaLiveCommandResult Status = IsValid(Runtime)
        ? Runtime->GetStatus(FName(*CommandId)) : FVistaLiveCommandResult();
    Response->SetNumberField(TEXT("session_generation"), Status.SessionGeneration);
    return SerializeObject(Response);
}

FString RendererStatusResponse(const FVistaRendererStatusResult& Result)
{
    if (!Result.bSucceeded)
    {
        return ErrorResponse(Result.CommandId.ToString(), *Result.Code.ToString());
    }
    const TSharedRef<FJsonObject> Response = MakeShared<FJsonObject>();
    Response->SetStringField(TEXT("command_id"), Result.CommandId.ToString());
    Response->SetStringField(TEXT("status"), TEXT("success"));
    Response->SetStringField(TEXT("code"), Result.Code.ToString());
    Response->SetStringField(
        TEXT("schema_version"),
        TEXT("simworld.vista.playable-home-renderer-status/v1"));
    Response->SetStringField(
        TEXT("unreal_engine_version"),
        Result.Observation.UnrealEngineVersion);
    Response->SetStringField(TEXT("rhi"), Result.Observation.Rhi);
    Response->SetStringField(TEXT("feature_level"), Result.Observation.FeatureLevel);
    Response->SetStringField(TEXT("shader_platform"), Result.Observation.ShaderPlatform);
    const TSharedRef<FJsonObject> CVars = MakeShared<FJsonObject>();
    for (const TPair<FString, double>& Pair :
         Result.Observation.ConsoleVariables)
    {
        CVars->SetNumberField(Pair.Key, Pair.Value);
    }
    Response->SetObjectField(TEXT("cvars"), CVars);
    return SerializeObject(Response);
}

UVistaPlayableHomeRuntimeSubsystem* FindRuntimeSubsystem()
{
    if (!GEngine)
    {
        return nullptr;
    }
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
    {
        UWorld* World = Context.World();
        if (IsValid(World) &&
            (World->WorldType == EWorldType::Game ||
             World->WorldType == EWorldType::PIE ||
             World->WorldType == EWorldType::GamePreview))
        {
            if (UVistaPlayableHomeRuntimeSubsystem* Runtime =
                    World->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>())
            {
                return Runtime;
            }
        }
    }
    return nullptr;
}

bool ReadEnvelope(const TSharedPtr<FJsonObject>& Params,
                  FVistaLiveCommandEnvelope& Envelope,
                  FString& CommandId)
{
    FString Revision;
    if (!ReadString(Params, TEXT("command_id"), CommandId) || !IsCommandId(CommandId) ||
        !ReadString(Params, TEXT("expected_revision"), Revision) || !IsRevision(Revision) ||
        !ReadGeneration(Params, Envelope.SessionGeneration))
    {
        return false;
    }
    Envelope.CommandId = FName(*CommandId);
    Envelope.ExpectedRevision = FName(*Revision);
    return true;
}

TOptional<EVistaAffordance> ParseAffordance(const FString& Value)
{
    if (Value == TEXT("open")) return EVistaAffordance::Open;
    if (Value == TEXT("close")) return EVistaAffordance::Close;
    if (Value == TEXT("pick_up")) return EVistaAffordance::PickUp;
    if (Value == TEXT("drop")) return EVistaAffordance::Drop;
    if (Value == TEXT("place")) return EVistaAffordance::Place;
    if (Value == TEXT("toggle")) return EVistaAffordance::Toggle;
    if (Value == TEXT("sit")) return EVistaAffordance::Sit;
    if (Value == TEXT("inspect")) return EVistaAffordance::Inspect;
    if (Value == TEXT("press")) return EVistaAffordance::Press;
    if (Value == TEXT("turn_on")) return EVistaAffordance::TurnOn;
    if (Value == TEXT("turn_off")) return EVistaAffordance::TurnOff;
    if (Value == TEXT("pour")) return EVistaAffordance::Pour;
    if (Value == TEXT("stand")) return EVistaAffordance::Stand;
    return {};
}

TOptional<EVistaNpcActionType> ParseNpcAction(const FString& Value)
{
    if (Value == TEXT("navigate_to")) return EVistaNpcActionType::NavigateTo;
    if (Value == TEXT("look_at")) return EVistaNpcActionType::LookAt;
    if (Value == TEXT("pick_up")) return EVistaNpcActionType::PickUp;
    if (Value == TEXT("place")) return EVistaNpcActionType::Place;
    if (Value == TEXT("drop")) return EVistaNpcActionType::Drop;
    if (Value == TEXT("open_door")) return EVistaNpcActionType::OpenDoor;
    if (Value == TEXT("close_door")) return EVistaNpcActionType::CloseDoor;
    if (Value == TEXT("inspect")) return EVistaNpcActionType::Inspect;
    if (Value == TEXT("toggle")) return EVistaNpcActionType::Toggle;
    if (Value == TEXT("press")) return EVistaNpcActionType::Press;
    if (Value == TEXT("turn_on")) return EVistaNpcActionType::TurnOn;
    if (Value == TEXT("turn_off")) return EVistaNpcActionType::TurnOff;
    if (Value == TEXT("pour")) return EVistaNpcActionType::Pour;
    if (Value == TEXT("sit")) return EVistaNpcActionType::Sit;
    if (Value == TEXT("stand")) return EVistaNpcActionType::StandUp;
    if (Value == TEXT("wait")) return EVistaNpcActionType::Wait;
    if (Value == TEXT("speak")) return EVistaNpcActionType::Speak;
    if (Value == TEXT("brace")) return EVistaNpcActionType::Brace;
    if (Value == TEXT("drag")) return EVistaNpcActionType::Drag;
    if (Value == TEXT("lift_foot")) return EVistaNpcActionType::LiftFoot;
    if (Value == TEXT("pause")) return EVistaNpcActionType::Pause;
    if (Value == TEXT("fall")) return EVistaNpcActionType::Fall;
    if (Value == TEXT("recover")) return EVistaNpcActionType::Recover;
    return {};
}

bool IsLowerHexDigest(const FString& Value)
{
    if (Value.Len() != 64)
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        if (!((Character >= TEXT('0') && Character <= TEXT('9')) ||
              (Character >= TEXT('a') && Character <= TEXT('f'))))
        {
            return false;
        }
    }
    return true;
}

bool IsEventV3RuntimeAction(EVistaNpcActionType Type)
{
    return Type == EVistaNpcActionType::NavigateTo ||
        Type == EVistaNpcActionType::Inspect ||
        Type == EVistaNpcActionType::PickUp ||
        Type == EVistaNpcActionType::Place ||
        Type == EVistaNpcActionType::Drop ||
        Type == EVistaNpcActionType::OpenDoor ||
        Type == EVistaNpcActionType::CloseDoor ||
        Type == EVistaNpcActionType::Toggle ||
        Type == EVistaNpcActionType::Press ||
        Type == EVistaNpcActionType::TurnOn ||
        Type == EVistaNpcActionType::TurnOff;
}

struct FParsedNpcQueueRequest final
{
    FVistaLiveNpcQueueCommand Command;
    FName EventId = NAME_None;
    FString EventContentDigest;
    FString SidecarContentDigest;
    FString QueueId;
};

bool ReadNpcQueueAction(
    const TSharedPtr<FJsonObject>& Object,
    bool bEventV3Preflight,
    FVistaNpcAction& OutAction,
    FName& OutCode)
{
    FString ActionId;
    FString Type;
    if (!Object.IsValid() ||
        !ReadString(Object, TEXT("action_id"), ActionId) ||
        !IsActionId(ActionId) || !ReadString(Object, TEXT("type"), Type))
    {
        OutCode = TEXT("NPC_ACTION_VALUE_INVALID");
        return false;
    }
    const TOptional<EVistaNpcActionType> Parsed = ParseNpcAction(Type);
    if (!Parsed.IsSet() ||
        (bEventV3Preflight && !IsEventV3RuntimeAction(Parsed.GetValue())))
    {
        OutCode = TEXT("NPC_ACTION_UNSUPPORTED");
        return false;
    }

    if (bEventV3Preflight)
    {
        TSet<FString> Required =
            KeySet({TEXT("action_id"), TEXT("type"), TEXT("timeout_sec")});
        if (Parsed.GetValue() != EVistaNpcActionType::Drop)
        {
            Required.Add(TEXT("target_semantic_id"));
        }
        if (Parsed.GetValue() == EVistaNpcActionType::Place)
        {
            Required.Add(TEXT("placement_anchor_id"));
        }
        if (!ExactKeys(Object, Required, TSet<FString>()))
        {
            OutCode = TEXT("NPC_ACTION_SHAPE_INVALID");
            return false;
        }
    }
    else if (!ExactKeys(
        Object,
        KeySet({TEXT("action_id"), TEXT("type")}),
        KeySet({TEXT("target_semantic_id"), TEXT("target_location_cm"),
                TEXT("secondary_target_semantic_id"),
                TEXT("placement_anchor_id"), TEXT("duration_sec"),
                TEXT("timeout_sec"), TEXT("speech"), TEXT("distance_cm"),
                TEXT("height_cm"), TEXT("hand"), TEXT("foot"),
                TEXT("direction")})))
    {
        OutCode = TEXT("NPC_ACTION_SHAPE_INVALID");
        return false;
    }

    OutAction = FVistaNpcAction();
    OutAction.ActionId = FName(*ActionId);
    OutAction.Type = Parsed.GetValue();
    if (Object->HasField(TEXT("target_semantic_id")) &&
        (!ReadString(
             Object, TEXT("target_semantic_id"), OutAction.TargetSemanticId) ||
         !IsSemanticId(OutAction.TargetSemanticId)))
    {
        OutCode = TEXT("NPC_TARGET_INVALID");
        return false;
    }
    if (Object->HasField(TEXT("secondary_target_semantic_id")) &&
        (!ReadString(
             Object,
             TEXT("secondary_target_semantic_id"),
             OutAction.SecondaryTargetSemanticId) ||
         !IsSemanticId(OutAction.SecondaryTargetSemanticId)))
    {
        OutCode = TEXT("NPC_SECONDARY_TARGET_INVALID");
        return false;
    }
    if (OutAction.Type == EVistaNpcActionType::Pour &&
        OutAction.SecondaryTargetSemanticId.IsEmpty())
    {
        OutCode = TEXT("NPC_SECONDARY_TARGET_REQUIRED");
        return false;
    }
    if (OutAction.Type == EVistaNpcActionType::Pour &&
        OutAction.SecondaryTargetSemanticId == OutAction.TargetSemanticId)
    {
        OutCode = TEXT("NPC_POUR_TARGETS_MUST_DIFFER");
        return false;
    }
    if (OutAction.Type == EVistaNpcActionType::Pour &&
        Object->HasField(TEXT("target_location_cm")))
    {
        OutCode = TEXT("NPC_POUR_LOCATION_UNEXPECTED");
        return false;
    }
    if (OutAction.Type != EVistaNpcActionType::Pour &&
        !OutAction.SecondaryTargetSemanticId.IsEmpty())
    {
        OutCode = TEXT("NPC_SECONDARY_TARGET_UNEXPECTED");
        return false;
    }
    if (Object->HasField(TEXT("placement_anchor_id")) &&
        (!ReadString(
             Object, TEXT("placement_anchor_id"), OutAction.PlacementAnchorId) ||
         !IsPlacementAnchorId(OutAction.PlacementAnchorId)))
    {
        OutCode = TEXT("NPC_PLACEMENT_ANCHOR_INVALID");
        return false;
    }
    if (OutAction.Type == EVistaNpcActionType::Place &&
        OutAction.PlacementAnchorId.IsEmpty())
    {
        OutCode = TEXT("NPC_PLACEMENT_ANCHOR_REQUIRED");
        return false;
    }
    if (OutAction.Type != EVistaNpcActionType::Place &&
        !OutAction.PlacementAnchorId.IsEmpty())
    {
        OutCode = TEXT("NPC_PLACEMENT_ANCHOR_UNEXPECTED");
        return false;
    }
    if (OutAction.Type == EVistaNpcActionType::Drop &&
        (!OutAction.TargetSemanticId.IsEmpty() ||
         Object->HasField(TEXT("target_location_cm"))))
    {
        OutCode = TEXT("NPC_DROP_TARGET_UNEXPECTED");
        return false;
    }

    const TArray<TSharedPtr<FJsonValue>>* Location = nullptr;
    if (Object->HasField(TEXT("target_location_cm")))
    {
        if (!Object->TryGetArrayField(TEXT("target_location_cm"), Location) ||
            Location == nullptr || Location->Num() != 3)
        {
            OutCode = TEXT("NPC_LOCATION_INVALID");
            return false;
        }
        double Components[3];
        for (int32 Index = 0; Index < 3; ++Index)
        {
            if (!(*Location)[Index]->TryGetNumber(Components[Index]) ||
                !FMath::IsFinite(Components[Index]) ||
                FMath::Abs(Components[Index]) > 10000000.0)
            {
                OutCode = TEXT("NPC_LOCATION_INVALID");
                return false;
            }
        }
        OutAction.TargetLocation =
            FVector(Components[0], Components[1], Components[2]);
    }

    double Number = 0.0;
    if (Object->HasField(TEXT("duration_sec")))
    {
        if (!Object->TryGetNumberField(TEXT("duration_sec"), Number) ||
            !FMath::IsFinite(Number) || Number < 0.0 || Number > 300.0)
        {
            OutCode = TEXT("NPC_DURATION_INVALID");
            return false;
        }
        OutAction.DurationSeconds = static_cast<float>(Number);
    }
    if (Object->HasField(TEXT("timeout_sec")))
    {
        if (!Object->TryGetNumberField(TEXT("timeout_sec"), Number) ||
            !FMath::IsFinite(Number) ||
            (bEventV3Preflight ? Number <= 0.0 : Number < 0.0) ||
            Number > 300.0)
        {
            OutCode = TEXT("NPC_TIMEOUT_INVALID");
            return false;
        }
        OutAction.TimeoutSeconds = static_cast<float>(Number);
    }
    if (Object->HasField(TEXT("distance_cm")))
    {
        if (!Object->TryGetNumberField(TEXT("distance_cm"), Number) ||
            !FMath::IsFinite(Number) || Number < 0.0 || Number > 1000.0)
        {
            OutCode = TEXT("NPC_DISTANCE_INVALID");
            return false;
        }
        OutAction.DistanceCm = static_cast<float>(Number);
    }
    if (Object->HasField(TEXT("height_cm")))
    {
        if (!Object->TryGetNumberField(TEXT("height_cm"), Number) ||
            !FMath::IsFinite(Number) || Number < 0.0 || Number > 300.0)
        {
            OutCode = TEXT("NPC_HEIGHT_INVALID");
            return false;
        }
        OutAction.HeightCm = static_cast<float>(Number);
    }

    FString EnumValue;
    if (Object->HasField(TEXT("hand")))
    {
        if (!ReadString(Object, TEXT("hand"), EnumValue))
        {
            OutCode = TEXT("NPC_HAND_INVALID");
            return false;
        }
        if (EnumValue == TEXT("left")) OutAction.Hand = EVistaAnimationHand::Left;
        else if (EnumValue == TEXT("right")) OutAction.Hand = EVistaAnimationHand::Right;
        else if (EnumValue == TEXT("both")) OutAction.Hand = EVistaAnimationHand::Both;
        else
        {
            OutCode = TEXT("NPC_HAND_INVALID");
            return false;
        }
    }
    if (Object->HasField(TEXT("foot")))
    {
        if (!ReadString(Object, TEXT("foot"), EnumValue))
        {
            OutCode = TEXT("NPC_FOOT_INVALID");
            return false;
        }
        if (EnumValue == TEXT("left")) OutAction.Foot = EVistaAnimationFoot::Left;
        else if (EnumValue == TEXT("right")) OutAction.Foot = EVistaAnimationFoot::Right;
        else
        {
            OutCode = TEXT("NPC_FOOT_INVALID");
            return false;
        }
    }
    if (Object->HasField(TEXT("direction")))
    {
        if (!ReadString(Object, TEXT("direction"), EnumValue) ||
            EnumValue != TEXT("forward"))
        {
            OutCode = TEXT("NPC_DIRECTION_INVALID");
            return false;
        }
        OutAction.Direction = EVistaAnimationDirection::Forward;
    }
    if (Object->HasField(TEXT("speech")) &&
        (!ReadString(Object, TEXT("speech"), OutAction.Speech) ||
         OutAction.Speech.Len() > 500))
    {
        OutCode = TEXT("NPC_SPEECH_INVALID");
        return false;
    }
    OutCode = TEXT("NPC_ACTION_PARSED");
    return true;
}

bool ReadNpcQueueRequest(
    const TSharedPtr<FJsonObject>& Params,
    bool bEventV3Preflight,
    FParsedNpcQueueRequest& OutRequest,
    FString& OutCommandId,
    FName& OutCode)
{
    TSet<FString> Required = KeySet({
        TEXT("operation"), TEXT("command_id"), TEXT("expected_revision"),
        TEXT("session_generation"), TEXT("npc_semantic_id"), TEXT("replace"),
        TEXT("actions")});
    if (bEventV3Preflight)
    {
        Required.Add(TEXT("event_id"));
        Required.Add(TEXT("event_content_digest"));
        Required.Add(TEXT("sidecar_content_digest"));
        Required.Add(TEXT("queue_id"));
    }
    if (!ExactKeys(Params, Required, TSet<FString>()))
    {
        ReadString(Params, TEXT("command_id"), OutCommandId);
        OutCode = bEventV3Preflight
            ? FName(TEXT("NPC_QUEUE_PREFLIGHT_SHAPE_INVALID"))
            : FName(TEXT("NPC_QUEUE_SHAPE_INVALID"));
        return false;
    }

    OutRequest = FParsedNpcQueueRequest();
    if (!ReadEnvelope(Params, OutRequest.Command.Envelope, OutCommandId) ||
        !ReadString(
            Params, TEXT("npc_semantic_id"), OutRequest.Command.NpcSemanticId) ||
        !IsSemanticId(OutRequest.Command.NpcSemanticId) ||
        !Params->TryGetBoolField(TEXT("replace"), OutRequest.Command.bReplace) ||
        !OutRequest.Command.bReplace)
    {
        OutCode = bEventV3Preflight
            ? FName(TEXT("NPC_QUEUE_PREFLIGHT_VALUE_INVALID"))
            : FName(TEXT("NPC_QUEUE_VALUE_INVALID"));
        return false;
    }
    if (bEventV3Preflight)
    {
        FString EventId;
        if (!ReadString(Params, TEXT("event_id"), EventId) ||
            !IsRevision(EventId) ||
            !ReadString(Params, TEXT("event_content_digest"),
                        OutRequest.EventContentDigest) ||
            !IsLowerHexDigest(OutRequest.EventContentDigest) ||
            !ReadString(Params, TEXT("sidecar_content_digest"),
                        OutRequest.SidecarContentDigest) ||
            !IsLowerHexDigest(OutRequest.SidecarContentDigest) ||
            !ReadString(Params, TEXT("queue_id"), OutRequest.QueueId) ||
            !IsActionId(OutRequest.QueueId))
        {
            OutCode = TEXT("NPC_QUEUE_PREFLIGHT_IDENTITY_INVALID");
            return false;
        }
        OutRequest.EventId = FName(*EventId);
    }

    const TArray<TSharedPtr<FJsonValue>>* Actions = nullptr;
    if (!Params->TryGetArrayField(TEXT("actions"), Actions) ||
        Actions == nullptr || Actions->IsEmpty() || Actions->Num() > 32)
    {
        OutCode = TEXT("NPC_ACTIONS_INVALID");
        return false;
    }
    TSet<FName> ActionIds;
    for (const TSharedPtr<FJsonValue>& Value : *Actions)
    {
        const TSharedPtr<FJsonObject>* Object = nullptr;
        if (!Value.IsValid() || !Value->TryGetObject(Object) || Object == nullptr)
        {
            OutCode = TEXT("NPC_ACTION_SHAPE_INVALID");
            return false;
        }
        FVistaNpcAction Action;
        if (!ReadNpcQueueAction(*Object, bEventV3Preflight, Action, OutCode))
        {
            return false;
        }
        if (ActionIds.Contains(Action.ActionId))
        {
            OutCode = TEXT("NPC_ACTION_DUPLICATE");
            return false;
        }
        ActionIds.Add(Action.ActionId);
        OutRequest.Command.Actions.Add(MoveTemp(Action));
    }
    OutCode = TEXT("NPC_QUEUE_PARSED");
    return true;
}

FString DispatchTyped(const TSharedPtr<FJsonObject>& Params)
{
    FString Operation;
    FString CommandId;
    if (!ReadString(Params, TEXT("operation"), Operation))
    {
        return ErrorResponse(TEXT(""), TEXT("OPERATION_REQUIRED"));
    }

    UVistaPlayableHomeRuntimeSubsystem* Runtime = FindRuntimeSubsystem();
    if (!IsValid(Runtime))
    {
        ReadString(Params, TEXT("command_id"), CommandId);
        return ErrorResponse(CommandId, TEXT("RUNTIME_UNAVAILABLE"));
    }

    if (Operation == TEXT("status") || Operation == TEXT("health"))
    {
        if (!ExactKeys(Params,
                       KeySet({TEXT("operation"), TEXT("command_id")}),
                       TSet<FString>()) ||
            !ReadString(Params, TEXT("command_id"), CommandId) ||
            !IsCommandId(CommandId))
        {
            return ErrorResponse(CommandId, TEXT("STATUS_SHAPE_INVALID"));
        }
        return ResultResponse(Runtime->GetStatus(FName(*CommandId)), true);
    }

    if (Operation == TEXT("renderer_status"))
    {
        if (!ExactKeys(Params,
                       KeySet({TEXT("operation"), TEXT("command_id")}),
                       TSet<FString>()) ||
            !ReadString(Params, TEXT("command_id"), CommandId) ||
            !IsCommandId(CommandId))
        {
            return ErrorResponse(CommandId, TEXT("RENDERER_STATUS_SHAPE_INVALID"));
        }
        return RendererStatusResponse(
            Runtime->GetRendererStatus(FName(*CommandId)));
    }

    if (Operation == TEXT("npc_status"))
    {
        if (!ExactKeys(
                Params,
                KeySet({TEXT("operation"), TEXT("command_id"), TEXT("npc_semantic_id")}),
                TSet<FString>()))
        {
            return ErrorResponse(TEXT(""), TEXT("NPC_STATUS_SHAPE_INVALID"));
        }
        FString NpcSemanticId;
        if (!ReadString(Params, TEXT("command_id"), CommandId) || !IsCommandId(CommandId) ||
            !ReadString(Params, TEXT("npc_semantic_id"), NpcSemanticId) ||
            !IsSemanticId(NpcSemanticId))
        {
            return ErrorResponse(CommandId, TEXT("NPC_STATUS_VALUE_INVALID"));
        }
        return ResultResponse(
            Runtime->GetNpcStatus(FName(*CommandId), NpcSemanticId), true);
    }

    if (Operation == TEXT("interaction"))
    {
        const TSet<FString> Required = KeySet({
            TEXT("operation"), TEXT("command_id"), TEXT("expected_revision"),
            TEXT("session_generation"), TEXT("requester_semantic_id"),
            TEXT("target_semantic_id"), TEXT("affordance")});
        const TSet<FString> Optional = KeySet({
            TEXT("placement_anchor_semantic_id"),
            TEXT("secondary_target_semantic_id")});
        if (!ExactKeys(Params, Required, Optional))
        {
            return ErrorResponse(TEXT(""), TEXT("INTERACTION_SHAPE_INVALID"));
        }
        FVistaLiveInteractionCommand Command;
        FString Affordance;
        if (!ReadEnvelope(Params, Command.Envelope, CommandId) ||
            !ReadString(Params, TEXT("requester_semantic_id"), Command.RequesterSemanticId) ||
            !IsSemanticId(Command.RequesterSemanticId) ||
            !ReadString(Params, TEXT("target_semantic_id"), Command.TargetSemanticId) ||
            !IsSemanticId(Command.TargetSemanticId) ||
            !ReadString(Params, TEXT("affordance"), Affordance))
        {
            return ErrorResponse(CommandId, TEXT("INTERACTION_VALUE_INVALID"));
        }
        const TOptional<EVistaAffordance> Parsed = ParseAffordance(Affordance);
        if (!Parsed.IsSet())
        {
            return ErrorResponse(CommandId, TEXT("AFFORDANCE_UNSUPPORTED"));
        }
        Command.Affordance = Parsed.GetValue();
        if (Params->HasField(TEXT("secondary_target_semantic_id")) &&
            (!ReadString(
                 Params,
                 TEXT("secondary_target_semantic_id"),
                 Command.SecondaryTargetSemanticId) ||
             !IsSemanticId(Command.SecondaryTargetSemanticId)))
        {
            return ErrorResponse(
                CommandId, TEXT("SECONDARY_TARGET_INVALID"));
        }
        if (Command.Affordance == EVistaAffordance::Pour &&
            Command.SecondaryTargetSemanticId.IsEmpty())
        {
            return ErrorResponse(
                CommandId, TEXT("POUR_RECEIVER_REQUIRED"));
        }
        if (Command.Affordance == EVistaAffordance::Pour &&
            Command.SecondaryTargetSemanticId == Command.TargetSemanticId)
        {
            return ErrorResponse(
                CommandId, TEXT("POUR_TARGETS_MUST_DIFFER"));
        }
        if (Command.Affordance != EVistaAffordance::Pour &&
            !Command.SecondaryTargetSemanticId.IsEmpty())
        {
            return ErrorResponse(
                CommandId, TEXT("SECONDARY_TARGET_UNEXPECTED"));
        }
        if (Params->HasField(TEXT("placement_anchor_semantic_id")) &&
            (!ReadString(Params, TEXT("placement_anchor_semantic_id"),
                         Command.PlacementAnchorSemanticId) ||
             !IsSemanticId(Command.PlacementAnchorSemanticId)))
        {
            return ErrorResponse(CommandId, TEXT("PLACEMENT_ANCHOR_INVALID"));
        }
        if (Command.Affordance == EVistaAffordance::Place &&
            Command.PlacementAnchorSemanticId.IsEmpty())
        {
            return ErrorResponse(CommandId, TEXT("PLACEMENT_ANCHOR_REQUIRED"));
        }
        if (Command.Affordance != EVistaAffordance::Place &&
            !Command.PlacementAnchorSemanticId.IsEmpty())
        {
            return ErrorResponse(CommandId, TEXT("PLACEMENT_ANCHOR_UNEXPECTED"));
        }
        return ResultResponse(Runtime->ExecuteInteraction(Command));
    }

    if (Operation == TEXT("npc_cancel"))
    {
        const TSet<FString> Required = KeySet({
            TEXT("operation"), TEXT("command_id"), TEXT("expected_revision"),
            TEXT("session_generation"), TEXT("npc_semantic_id")});
        if (!ExactKeys(Params, Required, TSet<FString>()))
        {
            return ErrorResponse(TEXT(""), TEXT("NPC_CANCEL_SHAPE_INVALID"));
        }
        FVistaLiveNpcCancelCommand Command;
        if (!ReadEnvelope(Params, Command.Envelope, CommandId) ||
            !ReadString(Params, TEXT("npc_semantic_id"), Command.NpcSemanticId) ||
            !IsSemanticId(Command.NpcSemanticId))
        {
            return ErrorResponse(CommandId, TEXT("NPC_CANCEL_VALUE_INVALID"));
        }
        return ResultResponse(Runtime->ExecuteNpcCancel(Command));
    }

    if (Operation == TEXT("npc_queue_preflight") ||
        Operation == TEXT("npc_queue"))
    {
        const bool bPreflight = Operation == TEXT("npc_queue_preflight");
        FParsedNpcQueueRequest Parsed;
        FName ParseCode;
        if (!ReadNpcQueueRequest(
                Params, bPreflight, Parsed, CommandId, ParseCode))
        {
            return bPreflight
                ? NpcQueuePreflightParseErrorResponse(
                      Runtime, CommandId, ParseCode)
                : ErrorResponse(CommandId, *ParseCode.ToString());
        }
        if (!bPreflight)
        {
            return ResultResponse(Runtime->ExecuteNpcQueue(Parsed.Command));
        }

        FVistaLiveNpcQueuePreflightCommand Command;
        Command.Envelope = Parsed.Command.Envelope;
        Command.EventId = Parsed.EventId;
        Command.EventContentDigest = Parsed.EventContentDigest;
        Command.SidecarContentDigest = Parsed.SidecarContentDigest;
        Command.QueueId = Parsed.QueueId;
        Command.NpcSemanticId = Parsed.Command.NpcSemanticId;
        Command.bReplace = Parsed.Command.bReplace;
        Command.Actions = MoveTemp(Parsed.Command.Actions);
        return NpcQueuePreflightResponse(Runtime->PreflightNpcQueue(Command));
    }

    if (Operation == TEXT("event"))
    {
        const TSet<FString> Required = KeySet({
            TEXT("operation"), TEXT("command_id"), TEXT("expected_revision"),
            TEXT("session_generation"), TEXT("event_operation")});
        const TSet<FString> Optional = KeySet({TEXT("event_id")});
        if (!ExactKeys(Params, Required, Optional))
        {
            return ErrorResponse(TEXT(""), TEXT("EVENT_SHAPE_INVALID"));
        }
        FVistaLiveEventCommand Command;
        FString EventOperation;
        if (!ReadEnvelope(Params, Command.Envelope, CommandId) ||
            !ReadString(Params, TEXT("event_operation"), EventOperation))
        {
            return ErrorResponse(CommandId, TEXT("EVENT_VALUE_INVALID"));
        }
        if (EventOperation == TEXT("start_event"))
        {
            FString EventId;
            if (!ReadString(Params, TEXT("event_id"), EventId) || !IsRevision(EventId))
            {
                return ErrorResponse(CommandId, TEXT("EVENT_ID_INVALID"));
            }
            Command.Operation = EVistaLiveEventOperation::StartEvent;
            Command.EventId = FName(*EventId);
        }
        else if (EventOperation == TEXT("reset_event") &&
                 !Params->HasField(TEXT("event_id")))
        {
            Command.Operation = EVistaLiveEventOperation::ResetEvent;
        }
        else
        {
            return ErrorResponse(CommandId, TEXT("EVENT_OPERATION_UNSUPPORTED"));
        }
        return ResultResponse(Runtime->ExecuteEvent(Command));
    }

    ReadString(Params, TEXT("command_id"), CommandId);
    return ErrorResponse(CommandId, TEXT("OPERATION_UNSUPPORTED"));
}
} // namespace

FVistaWorldTcpAdapter::FVistaWorldTcpAdapter(uint16 InPort) : Port(InPort) {}

FVistaWorldTcpAdapter::~FVistaWorldTcpAdapter()
{
    Stop();
}

bool FVistaWorldTcpAdapter::Start()
{
    if (Listener)
    {
        return false;
    }
    const FIPv4Endpoint Endpoint(FIPv4Address::InternalLoopback, Port);
    Listener = MakeUnique<FTcpListener>(Endpoint, FTimespan::FromMilliseconds(10));
    if (!Listener || !Listener->IsActive())
    {
        Listener.Reset();
        return false;
    }
    Listener->OnConnectionAccepted().BindRaw(this, &FVistaWorldTcpAdapter::HandleConnection);
    UE_LOG(LogTemp, Display, TEXT("VISTA World fixed adapter listening on 127.0.0.1:%u"), Port);
    return true;
}

void FVistaWorldTcpAdapter::Stop()
{
    if (Listener)
    {
        Listener->Stop();
        Listener.Reset();
    }
}

bool FVistaWorldTcpAdapter::HandleConnection(
    FSocket* Socket,
    const FIPv4Endpoint& RemoteEndpoint)
{
    if (!Socket)
    {
        return false;
    }
    FString Response;
    if (RemoteEndpoint.Address != FIPv4Address::InternalLoopback)
    {
        Response = ErrorResponse(TEXT(""), TEXT("LOOPBACK_REQUIRED"));
    }
    else
    {
        Socket->SetNonBlocking(false);
        int32 ActualBufferSize = 0;
        Socket->SetReceiveBufferSize(MaxRequestBytes, ActualBufferSize);
        TArray<uint8> Buffer;
        Buffer.Reserve(MaxRequestBytes);
        const double Deadline = FPlatformTime::Seconds() + ReadTimeoutSeconds;
        bool bComplete = false;
        while (FPlatformTime::Seconds() < Deadline && Buffer.Num() < MaxRequestBytes)
        {
            if (!Socket->Wait(ESocketWaitConditions::WaitForRead,
                              FTimespan::FromMilliseconds(100)))
            {
                continue;
            }
            uint8 Chunk[4096];
            int32 Read = 0;
            if (!Socket->Recv(Chunk, UE_ARRAY_COUNT(Chunk), Read) || Read <= 0)
            {
                break;
            }
            for (int32 Index = 0; Index < Read; ++Index)
            {
                if (Chunk[Index] == '\n')
                {
                    bComplete = true;
                    break;
                }
                Buffer.Add(Chunk[Index]);
                if (Buffer.Num() >= MaxRequestBytes)
                {
                    break;
                }
            }
            if (bComplete)
            {
                break;
            }
        }
        if (!bComplete || Buffer.IsEmpty())
        {
            Response = ErrorResponse(TEXT(""),
                Buffer.Num() >= MaxRequestBytes ? TEXT("REQUEST_TOO_LARGE")
                                                : TEXT("REQUEST_FRAME_INCOMPLETE"));
        }
        else
        {
            Buffer.Add(0);
            const FString Frame = UTF8_TO_TCHAR(reinterpret_cast<const char*>(Buffer.GetData()));
            Response = DispatchFrame(Frame);
        }
    }

    FTCHARToUTF8 Encoded(*Response);
    if (Encoded.Length() > MaxResponseBytes)
    {
        Response = ErrorResponse(TEXT(""), TEXT("RESPONSE_TOO_LARGE"));
    }
    FTCHARToUTF8 FinalBytes(*Response);
    int32 Offset = 0;
    while (Offset < FinalBytes.Length())
    {
        int32 Sent = 0;
        if (!Socket->Send(
                reinterpret_cast<const uint8*>(FinalBytes.Get()) + Offset,
                FinalBytes.Length() - Offset,
                Sent) || Sent <= 0)
        {
            break;
        }
        Offset += Sent;
    }
    Socket->Close();
    ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Socket);
    return true;
}

FString FVistaWorldTcpAdapter::DispatchFrame(const FString& Frame)
{
    TSharedPtr<FJsonObject> Root;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Frame);
    if (!FJsonSerializer::Deserialize(Reader, Root) ||
        !ExactKeys(Root, KeySet({TEXT("type"), TEXT("params")}), TSet<FString>()))
    {
        return ErrorResponse(TEXT(""), TEXT("REQUEST_JSON_INVALID"));
    }
    FString Type;
    const TSharedPtr<FJsonObject>* Params = nullptr;
    if (!ReadString(Root, TEXT("type"), Type) || Type != TEXT("vista_world_action") ||
        !Root->TryGetObjectField(TEXT("params"), Params) || Params == nullptr)
    {
        return ErrorResponse(TEXT(""), TEXT("TOOL_UNSUPPORTED"));
    }

    const TSharedRef<FDispatchState, ESPMode::ThreadSafe> State =
        MakeShared<FDispatchState, ESPMode::ThreadSafe>();
    const TSharedPtr<FJsonObject> TypedParams = *Params;
    AsyncTask(ENamedThreads::GameThread, [State, TypedParams]()
    {
        {
            FScopeLock Lock(&State->Mutex);
            if (State->bCanceled)
            {
                State->Completed->Trigger();
                return;
            }
        }
        const FString Response = DispatchTyped(TypedParams);
        {
            FScopeLock Lock(&State->Mutex);
            if (!State->bCanceled)
            {
                State->Response = Response;
            }
        }
        State->Completed->Trigger();
    });
    if (!State->Completed->Wait(DispatchTimeoutMilliseconds))
    {
        FScopeLock Lock(&State->Mutex);
        State->bCanceled = true;
        FString CommandId;
        ReadString(TypedParams, TEXT("command_id"), CommandId);
        return ErrorResponse(CommandId, TEXT("DISPATCH_TIMEOUT"));
    }
    FScopeLock Lock(&State->Mutex);
    return State->Response.IsEmpty()
        ? ErrorResponse(TEXT(""), TEXT("DISPATCH_FAILED"))
        : State->Response;
}
