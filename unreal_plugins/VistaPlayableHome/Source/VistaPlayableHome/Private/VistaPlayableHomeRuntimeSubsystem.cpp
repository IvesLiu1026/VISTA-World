#include "VistaPlayableHomeRuntimeSubsystem.h"

// Modified in VISTA-World on 2026-08-22: report successful typed interactions.

#include "EngineUtils.h"
#include "DynamicRHI.h"
#include "HAL/IConsoleManager.h"
#include "Misc/EngineVersion.h"
#include "Misc/Guid.h"
#include "GameFramework/Controller.h"
#include "GameFramework/Pawn.h"
#include "RHI.h"
#include "RHIShaderPlatform.h"
#include "RHIStrings.h"
#include "VistaAnimationComponent.h"
#include "VistaActionExecutorComponent.h"
#include "VistaEventDefinitionActor.h"
#include "VistaEventSubsystem.h"
#include "VistaHomeNpcCharacter.h"
#include "VistaHomeNpcController.h"
#include "VistaInteractable.h"
#include "VistaPickupActor.h"
#include "VistaPlayableHomeGameMode.h"

namespace
{
constexpr const TCHAR* RendererCVarNames[] = {
    TEXT("r.DynamicGlobalIlluminationMethod"),
    TEXT("r.ReflectionMethod"),
    TEXT("r.Shadow.Virtual.Enable"),
    TEXT("r.AntiAliasingMethod"),
    TEXT("r.Nanite"),
    TEXT("r.GenerateMeshDistanceFields"),
    TEXT("r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange"),
    TEXT("r.EyeAdaptation.PreExposureOverride"),
    TEXT("r.RayTracing"),
    TEXT("r.Lumen.HardwareRayTracing"),
    TEXT("r.ScreenPercentage"),
    TEXT("r.Streaming.PoolSize"),
    TEXT("sg.ViewDistanceQuality"),
    TEXT("sg.AntiAliasingQuality"),
    TEXT("sg.ShadowQuality"),
    TEXT("sg.GlobalIlluminationQuality"),
    TEXT("sg.ReflectionQuality"),
    TEXT("sg.PostProcessQuality"),
    TEXT("sg.TextureQuality"),
    TEXT("sg.EffectsQuality"),
    TEXT("sg.FoliageQuality"),
    TEXT("sg.ShadingQuality"),
};

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

bool IsClosedIdentifier(const FString& Value)
{
    if (Value.IsEmpty() || Value.Len() > 80)
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        if (!((Character >= TEXT('a') && Character <= TEXT('z')) ||
              (Character >= TEXT('0') && Character <= TEXT('9')) ||
              Character == TEXT('.') || Character == TEXT('_') ||
              Character == TEXT('-')))
        {
            return false;
        }
    }
    return true;
}

bool IsClosedActionId(const FString& Value)
{
    const auto IsAsciiAlnum = [](TCHAR Character)
    {
        return (Character >= TEXT('A') && Character <= TEXT('Z')) ||
               (Character >= TEXT('a') && Character <= TEXT('z')) ||
               (Character >= TEXT('0') && Character <= TEXT('9'));
    };
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
} // namespace

EVistaPhysicalCommandClaimOutcome
UVistaPlayableHomeRuntimeSubsystem::TryReplayPhysicalCommand(
    FName CommandId,
    const FString& CanonicalRequestHex,
    FVistaActionTransactionRecord& OutRecord) const
{
    check(IsInGameThread());
    const FPhysicalCommandLedgerEntry* Existing =
        PhysicalCommandLedger.Find(CommandId);
    if (Existing == nullptr)
    {
        return EVistaPhysicalCommandClaimOutcome::Unknown;
    }
    if (Existing->CanonicalRequestHex != CanonicalRequestHex)
    {
        return EVistaPhysicalCommandClaimOutcome::Collision;
    }
    OutRecord = Existing->Record;
    return EVistaPhysicalCommandClaimOutcome::Replay;
}

EVistaPhysicalCommandClaimOutcome
UVistaPlayableHomeRuntimeSubsystem::ClaimPhysicalCommand(
    FName CommandId,
    const FString& CanonicalRequestHex,
    UVistaActionExecutorComponent* Owner,
    const FVistaActionTransactionRecord& InitialRecord,
    FVistaActionTransactionRecord& OutRecord)
{
    check(IsInGameThread());
    const EVistaPhysicalCommandClaimOutcome Existing =
        TryReplayPhysicalCommand(CommandId, CanonicalRequestHex, OutRecord);
    if (Existing != EVistaPhysicalCommandClaimOutcome::Unknown)
    {
        return Existing;
    }
    if (CommandId.IsNone() || CanonicalRequestHex.IsEmpty() || !IsValid(Owner))
    {
        return EVistaPhysicalCommandClaimOutcome::CapacityExceeded;
    }
    while (PhysicalCommandLedger.Num() >= MaxPhysicalCommandLedgerEntries)
    {
        if (!EvictOldestTerminalPhysicalCommand())
        {
            return EVistaPhysicalCommandClaimOutcome::CapacityExceeded;
        }
    }
    FPhysicalCommandLedgerEntry Entry;
    Entry.CanonicalRequestHex = CanonicalRequestHex;
    Entry.Record = InitialRecord;
    Entry.Owner = Owner;
    Entry.bTerminal = false;
    PhysicalCommandLedger.Add(CommandId, MoveTemp(Entry));
    PhysicalCommandOrder.Add(CommandId);
    OutRecord = InitialRecord;
    return EVistaPhysicalCommandClaimOutcome::Claimed;
}

bool UVistaPlayableHomeRuntimeSubsystem::PublishPhysicalCommand(
    FName CommandId,
    const FString& CanonicalRequestHex,
    UVistaActionExecutorComponent* Owner,
    const FVistaActionTransactionRecord& Record,
    bool bTerminal)
{
    check(IsInGameThread());
    FPhysicalCommandLedgerEntry* Entry = PhysicalCommandLedger.Find(CommandId);
    if (Entry == nullptr || Entry->CanonicalRequestHex != CanonicalRequestHex ||
        Entry->Owner.Get() != Owner || Entry->bTerminal)
    {
        return false;
    }
    Entry->Record = Record;
    Entry->bTerminal = bTerminal;
    if (bTerminal)
    {
        Entry->Owner.Reset();
    }
    return true;
}

bool UVistaPlayableHomeRuntimeSubsystem::FinalizePhysicalCommand(
    const FName CommandId,
    const FString& CanonicalRequestHex,
    UVistaActionExecutorComponent* Owner,
    FVistaActionTransactionRecord& InOutRecord,
    const bool bCommitSessionGeneration,
    const int32 ExpectedGeneration,
    TFunctionRef<bool()> ReleaseReservations,
    FName& OutCode)
{
    check(IsInGameThread());
    FPhysicalCommandLedgerEntry* Entry = PhysicalCommandLedger.Find(CommandId);
    if (Entry == nullptr ||
        Entry->CanonicalRequestHex != CanonicalRequestHex ||
        Entry->Owner.Get() != Owner ||
        Entry->bTerminal)
    {
        OutCode = TEXT("ACTION_LEDGER_TERMINAL_PRECONDITION_FAILED");
        return false;
    }

    UVistaEventSubsystem* Events = GetWorld()
        ? GetWorld()->GetSubsystem<UVistaEventSubsystem>()
        : nullptr;
    if (bCommitSessionGeneration &&
        (!IsValid(Events) || Events->GetSessionGeneration() != ExpectedGeneration))
    {
        OutCode = TEXT("SESSION_GENERATION_COMMIT_FAILED");
        return false;
    }
    if (!ReleaseReservations())
    {
        OutCode = TEXT("TARGET_RESERVATION_RELEASE_FAILED");
        return false;
    }

    if (bCommitSessionGeneration)
    {
        int32 CommittedGeneration = ExpectedGeneration;
        const bool bCommitted = Events->CommitCommandGeneration(
            ExpectedGeneration,
            CommittedGeneration);
        checkf(
            bCommitted,
            TEXT("VISTA generation changed during non-reentrant terminal finalize"));
        InOutRecord.SessionGeneration = CommittedGeneration;
    }
    Entry->Record = InOutRecord;
    Entry->bTerminal = true;
    Entry->Owner.Reset();
    OutCode = TEXT("ACTION_TERMINAL_PUBLISHED");
    return true;
}

bool UVistaPlayableHomeRuntimeSubsystem::GetPhysicalCommandRecord(
    FName CommandId,
    FVistaActionTransactionRecord& OutRecord) const
{
    check(IsInGameThread());
    const FPhysicalCommandLedgerEntry* Entry =
        PhysicalCommandLedger.Find(CommandId);
    if (Entry == nullptr)
    {
        return false;
    }
    OutRecord = Entry->Record;
    return true;
}

bool UVistaPlayableHomeRuntimeSubsystem::EvictOldestTerminalPhysicalCommand()
{
    check(IsInGameThread());
    for (int32 Index = 0; Index < PhysicalCommandOrder.Num(); ++Index)
    {
        const FName Candidate = PhysicalCommandOrder[Index];
        const FPhysicalCommandLedgerEntry* Entry =
            PhysicalCommandLedger.Find(Candidate);
        if (Entry != nullptr && Entry->bTerminal)
        {
            PhysicalCommandOrder.RemoveAt(Index);
            PhysicalCommandLedger.Remove(Candidate);
            return true;
        }
    }
    return false;
}

FName UVistaPlayableHomeRuntimeSubsystem::AllocatePhysicalActionCommandId()
{
    check(IsInGameThread());
    if (!PhysicalActionTicketNonce.IsValid())
    {
        PhysicalActionTicketNonce = FGuid::NewGuid();
    }
    if (PhysicalActionTicketSequence == MAX_uint64)
    {
        return NAME_None;
    }
    ++PhysicalActionTicketSequence;
    return FName(*FString::Printf(
        TEXT("world-physical-%s-%016llx"),
        *PhysicalActionTicketNonce.ToString(EGuidFormats::Digits),
        static_cast<unsigned long long>(PhysicalActionTicketSequence)));
}

FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::GetStatus(
    FName CommandId) const
{
    FVistaLiveCommandResult Output;
    Output.CommandId = CommandId;
    const UVistaEventSubsystem* Events = GetWorld()->GetSubsystem<UVistaEventSubsystem>();
    if (!IsValid(Events))
    {
        Output.Code = TEXT("EVENT_SUBSYSTEM_UNAVAILABLE");
        return Output;
    }
    Output.WorldRevision = Events->GetWorldRevision();
    Output.SessionGeneration = Events->GetSessionGeneration();
    Output.EventStatus = Events->GetEventStatus();
    Output.ActiveEventId = Events->GetActiveEventId();
    Output.bSucceeded = !Output.WorldRevision.IsNone();
    Output.Code = Output.bSucceeded ? FName(TEXT("READY"))
                                   : FName(TEXT("WORLD_NOT_INITIALIZED"));
    return Output;
}

FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::GetNpcStatus(
    FName CommandId,
    const FString& NpcSemanticId) const
{
    FVistaLiveCommandResult Output = GetStatus(CommandId);
    Output.TargetSemanticId = NpcSemanticId;
    if (!Output.bSucceeded)
    {
        return Output;
    }
    AVistaHomeNpcCharacter* Npc =
        Cast<AVistaHomeNpcCharacter>(ResolveSemanticActor(NpcSemanticId));
    AVistaHomeNpcController* Controller = IsValid(Npc)
        ? Cast<AVistaHomeNpcController>(Npc->GetController()) : nullptr;
    if (!IsValid(Controller))
    {
        Output.bSucceeded = false;
        Output.Code = TEXT("NPC_CONTROLLER_NOT_FOUND");
        return Output;
    }
    Output.NpcActionResult = Controller->GetCurrentActionResult();
    Output.bHasLastCompletedNpcActionResult =
        Controller->HasLastCompletedActionResult();
    if (Output.bHasLastCompletedNpcActionResult)
    {
        Output.LastCompletedNpcActionResult =
            Controller->GetLastCompletedActionResult();
        Output.LastCompletedNpcRoomId =
            Controller->GetLastCompletedRoomId();
    }
    Output.NpcCurrentRoomId = Npc->CurrentRoomId;
    Output.QueuedActionCount = Controller->GetQueuedActionCount();
    if (UVistaAnimationComponent* Animation =
            Npc->FindComponentByClass<UVistaAnimationComponent>())
    {
        Output.AnimationResult = Animation->GetPlaybackResult();
    }
    if (IsValid(Controller->ActionExecutorComponent))
    {
        if (!Output.NpcActionResult.ActionId.IsNone())
        {
            Output.bHasActionTransaction =
                Controller->ActionExecutorComponent->GetTransaction(
                    Output.NpcActionResult.ActionId,
                    Output.ActionTransaction);
        }
        if (!Output.bHasActionTransaction &&
            Output.bHasLastCompletedNpcActionResult &&
            !Output.LastCompletedNpcActionResult.ActionId.IsNone())
        {
            Output.bHasActionTransaction =
                Controller->ActionExecutorComponent->GetTransaction(
                    Output.LastCompletedNpcActionResult.ActionId,
                    Output.ActionTransaction);
        }
    }
    Output.Code = TEXT("NPC_STATUS_OBSERVED");
    return Output;
}

FVistaRendererStatusResult
UVistaPlayableHomeRuntimeSubsystem::GetRendererStatus(FName CommandId) const
{
    FVistaRendererStatusResult Output;
    Output.CommandId = CommandId;
    if (CommandId.IsNone())
    {
        Output.Code = TEXT("COMMAND_ID_REQUIRED");
        return Output;
    }

    Output.Observation.UnrealEngineVersion = FEngineVersion::Current().ToString();
    Output.Observation.Rhi = GDynamicRHI ? FString(GDynamicRHI->GetName()) : FString();
    GetFeatureLevelName(
        GMaxRHIFeatureLevel, Output.Observation.FeatureLevel);
    Output.Observation.ShaderPlatform =
        LegacyShaderPlatformToShaderFormat(GMaxRHIShaderPlatform).ToString();
    if (Output.Observation.UnrealEngineVersion.IsEmpty() ||
        Output.Observation.Rhi.IsEmpty() ||
        Output.Observation.FeatureLevel.IsEmpty() ||
        Output.Observation.ShaderPlatform.IsEmpty())
    {
        Output.Code = TEXT("RENDERER_IDENTITY_UNAVAILABLE");
        return Output;
    }

    for (const TCHAR* Name : RendererCVarNames)
    {
        const IConsoleVariable* Variable =
            IConsoleManager::Get().FindConsoleVariable(Name);
        if (Variable == nullptr)
        {
            Output.Code = TEXT("RENDERER_CVAR_UNAVAILABLE");
            Output.Observation.ConsoleVariables.Reset();
            return Output;
        }
        const double Value = static_cast<double>(Variable->GetFloat());
        if (!FMath::IsFinite(Value))
        {
            Output.Code = TEXT("RENDERER_CVAR_NONFINITE");
            Output.Observation.ConsoleVariables.Reset();
            return Output;
        }
        Output.Observation.ConsoleVariables.Add(Name, Value);
    }

    Output.bSucceeded = true;
    Output.Code = TEXT("RENDERER_STATUS_OBSERVED");
    return Output;
}

bool UVistaPlayableHomeRuntimeSubsystem::ValidateEnvelope(
    const FVistaLiveCommandEnvelope& Envelope,
    FVistaLiveCommandResult& OutResult) const
{
    OutResult.CommandId = Envelope.CommandId;
    if (Envelope.CommandId.IsNone())
    {
        OutResult.Code = TEXT("COMMAND_ID_REQUIRED");
        return false;
    }
    const UVistaEventSubsystem* Events = GetWorld()->GetSubsystem<UVistaEventSubsystem>();
    if (!IsValid(Events))
    {
        OutResult.Code = TEXT("EVENT_SUBSYSTEM_UNAVAILABLE");
        return false;
    }
    OutResult.SessionGeneration = Events->GetSessionGeneration();
    OutResult.EventStatus = Events->GetEventStatus();
    OutResult.WorldRevision = Events->GetWorldRevision();
    OutResult.ActiveEventId = Events->GetActiveEventId();
    if (Envelope.ExpectedRevision.IsNone() ||
        Envelope.ExpectedRevision != Events->GetWorldRevision())
    {
        OutResult.Code = TEXT("REVISION_MISMATCH");
        return false;
    }
    if (Envelope.SessionGeneration != Events->GetSessionGeneration())
    {
        OutResult.Code = TEXT("SESSION_GENERATION_MISMATCH");
        return false;
    }
    return true;
}

FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::ExecuteInteraction(
    const FVistaLiveInteractionCommand& Command)
{
    FVistaLiveCommandResult Output;
    Output.TargetSemanticId = Command.TargetSemanticId;
    const bool bPhysical =
        UVistaActionExecutorComponent::IsPhysicalAffordance(Command.Affordance);
    const bool bAnimatedSemantic =
        UVistaActionExecutorComponent::IsAnimatedSemanticAffordance(
            Command.Affordance);
    const bool bTransactional = bPhysical || bAnimatedSemantic;
    FVistaPhysicalActionRequest PhysicalRequest;
    FVistaSemanticActionRequest SemanticRequest;
    if (bTransactional)
    {
        FString CanonicalRequest;
        if (bPhysical)
        {
            PhysicalRequest.CommandId = Command.Envelope.CommandId;
            PhysicalRequest.RequesterSemanticId = Command.RequesterSemanticId;
            PhysicalRequest.TargetSemanticId = Command.TargetSemanticId;
            PhysicalRequest.PlacementAnchorSemanticId =
                Command.PlacementAnchorSemanticId;
            PhysicalRequest.Affordance = Command.Affordance;
            PhysicalRequest.ExpectedRevision = Command.Envelope.ExpectedRevision;
            PhysicalRequest.SessionGeneration = Command.Envelope.SessionGeneration;
            PhysicalRequest.bCommitSessionGenerationOnSuccess = true;
            CanonicalRequest =
                UVistaActionExecutorComponent::CanonicalRequestHex(
                    PhysicalRequest);
        }
        else
        {
            SemanticRequest.CommandId = Command.Envelope.CommandId;
            SemanticRequest.RequesterSemanticId = Command.RequesterSemanticId;
            SemanticRequest.TargetSemanticId = Command.TargetSemanticId;
            SemanticRequest.Affordance = Command.Affordance;
            SemanticRequest.ExpectedRevision = Command.Envelope.ExpectedRevision;
            SemanticRequest.SessionGeneration = Command.Envelope.SessionGeneration;
            SemanticRequest.bCommitSessionGenerationOnSuccess = true;
            CanonicalRequest =
                UVistaActionExecutorComponent::CanonicalSemanticRequestHex(
                    SemanticRequest);
        }
        FVistaActionTransactionRecord Replay;
        const EVistaPhysicalCommandClaimOutcome ReplayOutcome =
            TryReplayPhysicalCommand(
                Command.Envelope.CommandId,
                CanonicalRequest,
                Replay);
        if (ReplayOutcome == EVistaPhysicalCommandClaimOutcome::Replay)
        {
            ApplyTransactionResult(Replay, Output);
            return Output;
        }
        if (ReplayOutcome == EVistaPhysicalCommandClaimOutcome::Collision)
        {
            Output.CommandId = Command.Envelope.CommandId;
            Output.SessionGeneration = Command.Envelope.SessionGeneration;
            Output.Code = TEXT("COMMAND_ID_COLLISION");
            return Output;
        }
    }

    if (!ValidateEnvelope(Command.Envelope, Output))
    {
        return Output;
    }
    AActor* Requester = ResolveSemanticActor(Command.RequesterSemanticId);
    if (!IsValid(Requester))
    {
        Output.Code = TEXT("REQUESTER_NOT_FOUND");
        return Output;
    }
    UVistaActionExecutorComponent* Executor = bTransactional
        ? ResolveActionExecutor(Requester) : nullptr;
    AActor* Target = ResolveSemanticActor(Command.TargetSemanticId);
    if (!IsValid(Target) ||
        !Target->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        Output.Code = TEXT("TARGET_NOT_INTERACTABLE");
        return Output;
    }

    USceneComponent* PlacementAnchor = nullptr;
    if (!Command.PlacementAnchorSemanticId.IsEmpty())
    {
        AActor* AnchorActor = ResolveSemanticActor(Command.PlacementAnchorSemanticId);
        if (!IsValid(AnchorActor))
        {
            Output.Code = TEXT("PLACEMENT_ANCHOR_NOT_FOUND");
            return Output;
        }
        PlacementAnchor = AnchorActor->GetRootComponent();
    }

    if (bPhysical)
    {
        if (!IsValid(Executor))
        {
            Output.Code = TEXT("ACTION_EXECUTOR_NOT_FOUND");
            return Output;
        }
        if (!IsValid(Cast<AVistaPickupActor>(Target)))
        {
            Output.Code = TEXT("PHYSICAL_TARGET_NOT_PICKUP");
            return Output;
        }
        if (Command.Affordance == EVistaAffordance::Place &&
            !IsValid(PlacementAnchor))
        {
            Output.Code = TEXT("PLACEMENT_TARGET_POINT_REQUIRED");
            return Output;
        }
        PhysicalRequest.Requester = Requester;
        PhysicalRequest.Target = Target;
        PhysicalRequest.PlacementAnchor = PlacementAnchor;
        PhysicalRequest.TimeoutSeconds = 10.0f;
        FVistaActionTransactionRecord Transaction;
        Executor->BeginPhysicalInteraction(PhysicalRequest, Transaction);
        ApplyTransactionResult(Transaction, Output);
        return Output;
    }

    if (bAnimatedSemantic)
    {
        if (!IsValid(Executor))
        {
            Output.Code = TEXT("ACTION_EXECUTOR_NOT_FOUND");
            return Output;
        }
        if (!Command.PlacementAnchorSemanticId.IsEmpty())
        {
            Output.Code = TEXT("PLACEMENT_ANCHOR_UNEXPECTED");
            return Output;
        }
        SemanticRequest.Requester = Requester;
        SemanticRequest.Target = Target;
        SemanticRequest.TimeoutSeconds = 10.0f;
        FVistaActionTransactionRecord Transaction;
        Executor->BeginSemanticInteraction(SemanticRequest, Transaction);
        ApplyTransactionResult(Transaction, Output);
        return Output;
    }

    FVistaInteractionRequest Request;
    Request.Requester = Requester;
    Request.Affordance = Command.Affordance;
    Request.PlacementAnchor = PlacementAnchor;
    Request.ExpectedRevision = Command.Envelope.ExpectedRevision;
    Request.SessionGeneration = Command.Envelope.SessionGeneration;
    const FVistaInteractionResult Result =
        IVistaInteractable::Execute_VistaInteract(Target, Request);
    Output.bSucceeded = Result.IsSuccess();
    Output.Code = Result.Code;
    Output.State = Result.State;
    if (Output.bSucceeded)
    {
        UVistaEventSubsystem* Events = GetWorld()->GetSubsystem<UVistaEventSubsystem>();
        if (!Events->CommitCommandGeneration(
                Command.Envelope.SessionGeneration, Output.SessionGeneration))
        {
            Output.bSucceeded = false;
            Output.Code = TEXT("SESSION_GENERATION_COMMIT_FAILED");
        }
        else
        {
            Events->RecordSuccessfulInteraction(
                Command.TargetSemanticId, Command.Affordance);
            Output.EventStatus = Events->GetEventStatus();
            Output.ActiveEventId = Events->GetActiveEventId();
        }
    }
    return Output;
}

void UVistaPlayableHomeRuntimeSubsystem::ApplyTransactionResult(
    const FVistaActionTransactionRecord& Transaction,
    FVistaLiveCommandResult& OutResult)
{
    OutResult.CommandId = Transaction.CommandId;
    OutResult.TargetSemanticId = Transaction.TargetSemanticId;
    OutResult.SessionGeneration = Transaction.SessionGeneration;
    OutResult.Code = Transaction.Code;
    OutResult.bHasActionTransaction = true;
    OutResult.ActionTransaction = Transaction;
    OutResult.State = Transaction.bHasAfterState
        ? Transaction.AfterState
        : Transaction.bHasContactState
            ? Transaction.ContactState
            : Transaction.BeforeState;
    OutResult.bSucceeded =
        Transaction.Status == EVistaActionTransactionStatus::Running ||
        Transaction.Status == EVistaActionTransactionStatus::Succeeded;
}

FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::ExecuteNpcQueue(
    const FVistaLiveNpcQueueCommand& Command)
{
    FVistaLiveCommandResult Output;
    Output.TargetSemanticId = Command.NpcSemanticId;
    if (!ValidateEnvelope(Command.Envelope, Output))
    {
        return Output;
    }
    AVistaHomeNpcCharacter* Npc =
        Cast<AVistaHomeNpcCharacter>(ResolveSemanticActor(Command.NpcSemanticId));
    AVistaHomeNpcController* Controller = IsValid(Npc)
        ? Cast<AVistaHomeNpcController>(Npc->GetController())
        : nullptr;
    if (!IsValid(Controller))
    {
        Output.Code = TEXT("NPC_CONTROLLER_NOT_FOUND");
        return Output;
    }
    if (!Command.bReplace)
    {
        Output.Code = TEXT("QUEUE_REPLACE_REQUIRED");
        return Output;
    }
    FName Code;
    Output.bSucceeded = Controller->ReplaceActionQueue(Command.Actions, Code);
    Output.Code = Code;
    if (Output.bSucceeded)
    {
        UVistaEventSubsystem* Events = GetWorld()->GetSubsystem<UVistaEventSubsystem>();
        if (!Events->CommitCommandGeneration(
                Command.Envelope.SessionGeneration, Output.SessionGeneration))
        {
            Output.bSucceeded = false;
            Output.Code = TEXT("SESSION_GENERATION_COMMIT_FAILED");
        }
    }
    return Output;
}

FVistaLiveNpcQueuePreflightResult
UVistaPlayableHomeRuntimeSubsystem::PreflightNpcQueue(
    const FVistaLiveNpcQueuePreflightCommand& Command) const
{
    check(IsInGameThread());
    FVistaLiveNpcQueuePreflightResult Output;
    Output.CommandId = Command.Envelope.CommandId;
    Output.QueueId = Command.QueueId;
    Output.TargetSemanticId = Command.NpcSemanticId;
    for (const FVistaNpcAction& Action : Command.Actions)
    {
        Output.ActionIds.Add(Action.ActionId);
    }

    FVistaLiveCommandResult EnvelopeResult;
    if (!ValidateEnvelope(Command.Envelope, EnvelopeResult))
    {
        Output.SessionGeneration = EnvelopeResult.SessionGeneration;
        Output.Code = EnvelopeResult.Code;
        return Output;
    }
    Output.SessionGeneration = EnvelopeResult.SessionGeneration;

    const UVistaEventSubsystem* Events =
        GetWorld()->GetSubsystem<UVistaEventSubsystem>();
    if (!IsValid(Events) ||
        Events->GetEventStatus() != EVistaEventStatus::Inactive ||
        !Events->GetActiveEventId().IsNone())
    {
        Output.Code = TEXT("RUNTIME_NOT_IDLE");
        return Output;
    }
    if (!IsClosedIdentifier(Command.EventId.ToString()))
    {
        Output.Code = TEXT("EVENT_ID_INVALID");
        return Output;
    }
    if (!IsLowerHexDigest(Command.EventContentDigest))
    {
        Output.Code = TEXT("EVENT_CONTENT_DIGEST_INVALID");
        return Output;
    }
    if (!IsLowerHexDigest(Command.SidecarContentDigest))
    {
        Output.Code = TEXT("SIDECAR_CONTENT_DIGEST_INVALID");
        return Output;
    }
    if (!IsClosedIdentifier(Command.QueueId))
    {
        Output.Code = TEXT("QUEUE_ID_INVALID");
        return Output;
    }
    if (!Command.bReplace)
    {
        Output.Code = TEXT("QUEUE_REPLACE_REQUIRED");
        return Output;
    }
    if (Command.Actions.IsEmpty() || Command.Actions.Num() > 32)
    {
        Output.Code = Command.Actions.IsEmpty()
            ? FName(TEXT("QUEUE_EMPTY"))
            : FName(TEXT("QUEUE_DEPTH_EXCEEDED"));
        return Output;
    }
    TSet<FName> ActionIds;
    for (const FVistaNpcAction& Action : Command.Actions)
    {
        if (!IsClosedActionId(Action.ActionId.ToString()))
        {
            Output.Code = TEXT("ACTION_ID_INVALID");
            return Output;
        }
        if (ActionIds.Contains(Action.ActionId))
        {
            Output.Code = TEXT("DUPLICATE_ACTION_ID");
            return Output;
        }
        ActionIds.Add(Action.ActionId);
    }

    FName EventCode;
    if (!IsKnownEventForRevision(
            Command.EventId, Command.Envelope.ExpectedRevision, EventCode))
    {
        Output.Code = EventCode;
        return Output;
    }

    AVistaHomeNpcCharacter* Npc =
        Cast<AVistaHomeNpcCharacter>(ResolveSemanticActor(Command.NpcSemanticId));
    AVistaHomeNpcController* Controller = IsValid(Npc)
        ? Cast<AVistaHomeNpcController>(Npc->GetController())
        : nullptr;
    if (!IsValid(Controller))
    {
        Output.Code = TEXT("NPC_CONTROLLER_NOT_FOUND");
        return Output;
    }
    FName QueueCode;
    if (!Controller->PreflightActionQueue(Command.Actions, QueueCode))
    {
        Output.Code = QueueCode.IsNone()
            ? FName(TEXT("QUEUE_PREFLIGHT_REJECTED")) : QueueCode;
        return Output;
    }

    // Loaded map actors currently carry no independent EventSpec or sidecar
    // content digests. These caller-bound identities are validated but never
    // echoed or promoted to authorization; the dispatcher must keep
    // runtime_execution_authorized=false.
    Output.bSucceeded = true;
    Output.Code = TEXT("QUEUE_PREFLIGHT_OK");
    return Output;
}

bool UVistaPlayableHomeRuntimeSubsystem::IsKnownEventForRevision(
    FName EventId,
    FName Revision,
    FName& OutCode) const
{
    if (EventId.IsNone() || Revision.IsNone() || !GetWorld())
    {
        OutCode = TEXT("EVENT_IDENTITY_INVALID");
        return false;
    }
    int32 MatchCount = 0;
    bool bRevisionMatches = true;
    const auto ObserveDefinitions =
        [EventId, Revision, &MatchCount, &bRevisionMatches](
            const TArray<FVistaEventDefinition>& Definitions)
        {
            for (const FVistaEventDefinition& Definition : Definitions)
            {
                if (Definition.EventId == EventId)
                {
                    ++MatchCount;
                    bRevisionMatches = bRevisionMatches &&
                        Definition.CompatibleRevision == Revision;
                }
            }
        };
    if (const AVistaPlayableHomeGameMode* GameMode =
            GetWorld()->GetAuthGameMode<AVistaPlayableHomeGameMode>())
    {
        ObserveDefinitions(GameMode->EventDefinitions);
    }
    for (TActorIterator<AVistaEventDefinitionActor> It(GetWorld()); It; ++It)
    {
        ObserveDefinitions(It->Definitions);
    }
    if (MatchCount == 0)
    {
        OutCode = TEXT("EVENT_NOT_REGISTERED");
        return false;
    }
    if (MatchCount != 1)
    {
        OutCode = TEXT("EVENT_IDENTITY_AMBIGUOUS");
        return false;
    }
    if (!bRevisionMatches)
    {
        OutCode = TEXT("EVENT_REVISION_INCOMPATIBLE");
        return false;
    }
    OutCode = TEXT("EVENT_IDENTITY_KNOWN");
    return true;
}

FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::ExecuteNpcCancel(
    const FVistaLiveNpcCancelCommand& Command)
{
    FVistaLiveCommandResult Output;
    Output.TargetSemanticId = Command.NpcSemanticId;
    if (!ValidateEnvelope(Command.Envelope, Output))
    {
        return Output;
    }
    AVistaHomeNpcCharacter* Npc =
        Cast<AVistaHomeNpcCharacter>(ResolveSemanticActor(Command.NpcSemanticId));
    AVistaHomeNpcController* Controller = IsValid(Npc)
        ? Cast<AVistaHomeNpcController>(Npc->GetController())
        : nullptr;
    if (!IsValid(Controller))
    {
        Output.Code = TEXT("NPC_CONTROLLER_NOT_FOUND");
        return Output;
    }

    const FVistaNpcActionResult BeforeCancel =
        Controller->GetCurrentActionResult();
    const bool bHadPendingWork = Controller->GetQueuedActionCount() > 0 ||
        BeforeCancel.Status == EVistaNpcActionStatus::Queued ||
        BeforeCancel.Status == EVistaNpcActionStatus::Running;
    Controller->CancelActionQueue(TEXT("NPC_QUEUE_CANCELED"));
    UVistaEventSubsystem* Events = GetWorld()->GetSubsystem<UVistaEventSubsystem>();
    if (!Events->CommitCommandGeneration(
            Command.Envelope.SessionGeneration, Output.SessionGeneration))
    {
        Output.Code = TEXT("SESSION_GENERATION_COMMIT_FAILED");
        return Output;
    }

    Output = GetNpcStatus(Command.Envelope.CommandId, Command.NpcSemanticId);
    Output.Code = bHadPendingWork
        ? FName(TEXT("NPC_QUEUE_CANCELED"))
        : FName(TEXT("NPC_ALREADY_IDLE"));
    return Output;
}

FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::ExecuteEvent(
    const FVistaLiveEventCommand& Command)
{
    FVistaLiveCommandResult Output;
    if (!ValidateEnvelope(Command.Envelope, Output))
    {
        return Output;
    }
    UVistaEventSubsystem* Events = GetWorld()->GetSubsystem<UVistaEventSubsystem>();
    FName Code;
    if (Command.Operation == EVistaLiveEventOperation::StartEvent)
    {
        if (Command.EventId.IsNone())
        {
            Output.Code = TEXT("EVENT_ID_REQUIRED");
            return Output;
        }
        Output.bSucceeded = Events->StartEvent(
            Command.EventId, Command.Envelope.ExpectedRevision,
            Command.Envelope.SessionGeneration, Code);
    }
    else
    {
        Output.bSucceeded = Events->ResetEvent(
            Command.Envelope.ExpectedRevision,
            Command.Envelope.SessionGeneration, Code);
    }
    Output.Code = Code;
    Output.EventStatus = Events->GetEventStatus();
    Output.ActiveEventId = Events->GetActiveEventId();
    if (Output.bSucceeded && !Events->CommitCommandGeneration(
            Command.Envelope.SessionGeneration, Output.SessionGeneration))
    {
        Output.bSucceeded = false;
        Output.Code = TEXT("SESSION_GENERATION_COMMIT_FAILED");
    }
    else if (!Output.bSucceeded)
    {
        Output.SessionGeneration = Events->GetSessionGeneration();
    }
    return Output;
}

AActor* UVistaPlayableHomeRuntimeSubsystem::ResolveSemanticActor(
    const FString& SemanticId) const
{
    if (SemanticId.IsEmpty() || !GetWorld())
    {
        return nullptr;
    }
    const FName Tag(*SemanticId);
    const FName StableTag(*(FString(TEXT("VistaSemanticId=")) + SemanticId));
    AActor* Match = nullptr;
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        if (It->ActorHasTag(Tag) || It->ActorHasTag(StableTag))
        {
            if (Match != nullptr)
            {
                return nullptr;
            }
            Match = *It;
        }
    }
    if (IsValid(Match) &&
        Match->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()) &&
        IVistaInteractable::Execute_VistaGetSemanticId(Match) != SemanticId)
    {
        return nullptr;
    }
    return Match;
}

UVistaActionExecutorComponent*
UVistaPlayableHomeRuntimeSubsystem::ResolveActionExecutor(AActor* Requester) const
{
    if (!IsValid(Requester))
    {
        return nullptr;
    }
    if (UVistaActionExecutorComponent* Executor =
            Requester->FindComponentByClass<UVistaActionExecutorComponent>())
    {
        return Executor;
    }
    const APawn* Pawn = Cast<APawn>(Requester);
    return IsValid(Pawn) && IsValid(Pawn->GetController())
        ? Pawn->GetController()->FindComponentByClass<UVistaActionExecutorComponent>()
        : nullptr;
}
