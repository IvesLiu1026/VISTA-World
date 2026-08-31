#include "VistaActionExecutorComponent.h"

#include "Containers/StringConv.h"
#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "HAL/PlatformMemory.h"
#include "VistaAnimationComponent.h"
#include "VistaEventSubsystem.h"
#include "VistaInteractable.h"
#include "VistaPlayableHomeRuntimeSubsystem.h"

namespace
{
constexpr float MaximumSemanticContactDistanceCm = 300.0f;

void AppendUInt32(TArray<uint8>& Output, const uint32 Value)
{
    Output.Add(static_cast<uint8>((Value >> 24) & 0xff));
    Output.Add(static_cast<uint8>((Value >> 16) & 0xff));
    Output.Add(static_cast<uint8>((Value >> 8) & 0xff));
    Output.Add(static_cast<uint8>(Value & 0xff));
}

void AppendUtf8(TArray<uint8>& Output, const FString& Value)
{
    const FTCHARToUTF8 Converted(*Value);
    AppendUInt32(Output, static_cast<uint32>(Converted.Length()));
    Output.Append(
        reinterpret_cast<const uint8*>(Converted.Get()),
        Converted.Length());
}

FString LowerHex(const TArray<uint8>& Bytes)
{
    static constexpr TCHAR Digits[] = TEXT("0123456789abcdef");
    FString Result;
    Result.Reserve(Bytes.Num() * 2);
    for (const uint8 Byte : Bytes)
    {
        Result.AppendChar(Digits[(Byte >> 4) & 0x0f]);
        Result.AppendChar(Digits[Byte & 0x0f]);
    }
    return Result;
}

bool RuntimeStatesEquivalent(
    const FVistaEntityRuntimeState& Left,
    const FVistaEntityRuntimeState& Right)
{
    if (Left.SemanticId != Right.SemanticId ||
        !Left.Transform.Equals(Right.Transform, 0.01f) ||
        Left.bHidden != Right.bHidden || Left.bPortable != Right.bPortable ||
        Left.Values.Num() != Right.Values.Num())
    {
        return false;
    }
    for (const TPair<FName, FString>& Pair : Left.Values)
    {
        const FString* Other = Right.Values.Find(Pair.Key);
        if (Other == nullptr || *Other != Pair.Value)
        {
            return false;
        }
    }
    return true;
}

EVistaNpcActionType AnimationTypeFor(const EVistaAffordance Affordance)
{
    switch (Affordance)
    {
    case EVistaAffordance::Open: return EVistaNpcActionType::OpenDoor;
    case EVistaAffordance::Close: return EVistaNpcActionType::CloseDoor;
    case EVistaAffordance::Inspect: return EVistaNpcActionType::LookAt;
    default: return EVistaNpcActionType::Wait;
    }
}

bool StateMatchesSemanticEffect(
    const FVistaEntityRuntimeState& Before,
    const FVistaEntityRuntimeState& After,
    const EVistaAffordance Affordance)
{
    if (Affordance == EVistaAffordance::Inspect)
    {
        return RuntimeStatesEquivalent(Before, After);
    }
    const FString* Open = After.Values.Find(TEXT("open"));
    if (Open == nullptr)
    {
        return false;
    }
    return Affordance == EVistaAffordance::Open
        ? Open->Equals(TEXT("true"), ESearchCase::CaseSensitive)
        : Open->Equals(TEXT("false"), ESearchCase::CaseSensitive);
}

bool ResolveContactLocation(const AActor* Target, FVector& OutLocation)
{
    if (!IsValid(Target))
    {
        return false;
    }
    TArray<USceneComponent*> Components;
    Target->GetComponents<USceneComponent>(Components);
    USceneComponent* TaggedContact = nullptr;
    for (USceneComponent* Component : Components)
    {
        if (!IsValid(Component) ||
            !Component->ComponentHasTag(
                FName(TEXT("VistaDoorHandleTarget"))))
        {
            continue;
        }
        if (TaggedContact != nullptr)
        {
            return false;
        }
        TaggedContact = Component;
    }
    OutLocation = IsValid(TaggedContact)
        ? TaggedContact->GetComponentLocation()
        : Target->GetActorLocation();
    return !OutLocation.ContainsNaN();
}
} // namespace

bool UVistaActionExecutorComponent::IsAnimatedSemanticAffordance(
    const EVistaAffordance Affordance)
{
    return Affordance == EVistaAffordance::Open ||
        Affordance == EVistaAffordance::Close ||
        Affordance == EVistaAffordance::Inspect;
}

FString UVistaActionExecutorComponent::CanonicalSemanticRequestHex(
    const FVistaSemanticActionRequest& Request)
{
    const FString RequesterId = Request.RequesterSemanticId.IsEmpty()
        ? SemanticIdForActor(Request.Requester)
        : Request.RequesterSemanticId;
    const FString TargetId = Request.TargetSemanticId.IsEmpty()
        ? SemanticIdForActor(Request.Target)
        : Request.TargetSemanticId;
    TArray<uint8> Bytes;
    Bytes.Reserve(192);
    AppendUtf8(Bytes, TEXT("vista.semantic-command/v1"));
    AppendUtf8(Bytes, RequesterId);
    AppendUtf8(Bytes, TargetId);
    Bytes.Add(static_cast<uint8>(Request.Affordance));
    AppendUtf8(Bytes, Request.ExpectedRevision.ToString());
    AppendUInt32(Bytes, static_cast<uint32>(Request.SessionGeneration));
    uint32 TimeoutBits = 0;
    FPlatformMemory::Memcpy(
        &TimeoutBits, &Request.TimeoutSeconds, sizeof(TimeoutBits));
    AppendUInt32(Bytes, TimeoutBits);
    Bytes.Add(Request.bCommitSessionGenerationOnSuccess ? 1 : 0);
    return LowerHex(Bytes);
}

void UVistaActionExecutorComponent::SetRejectedSemanticRecord(
    const FVistaSemanticActionRequest& Request,
    const FName Code,
    FVistaActionTransactionRecord& OutRecord)
{
    OutRecord = FVistaActionTransactionRecord();
    OutRecord.CommandId = Request.CommandId;
    OutRecord.Affordance = Request.Affordance;
    OutRecord.RequesterSemanticId = Request.RequesterSemanticId.IsEmpty()
        ? SemanticIdForActor(Request.Requester)
        : Request.RequesterSemanticId;
    OutRecord.TargetSemanticId = Request.TargetSemanticId.IsEmpty()
        ? SemanticIdForActor(Request.Target)
        : Request.TargetSemanticId;
    OutRecord.Status = EVistaActionTransactionStatus::Failed;
    OutRecord.Phase = EVistaActionPhase::Idle;
    OutRecord.Code = Code;
    OutRecord.SessionGeneration = Request.SessionGeneration;
}

bool UVistaActionExecutorComponent::RejectSemanticRequest(
    const FVistaSemanticActionRequest& Request,
    const FString& CanonicalRequest,
    const FName Code,
    FVistaActionTransactionRecord& OutRecord)
{
    SetRejectedSemanticRecord(Request, Code, OutRecord);
    UVistaPlayableHomeRuntimeSubsystem* Runtime = IsValid(GetWorld())
        ? GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>()
        : nullptr;
    if (IsValid(Runtime))
    {
        Runtime->PublishPhysicalCommand(
            Request.CommandId,
            CanonicalRequest,
            this,
            OutRecord,
            true);
    }
    return false;
}

bool UVistaActionExecutorComponent::BeginSemanticInteraction(
    const FVistaSemanticActionRequest& InputRequest,
    FVistaActionTransactionRecord& OutRecord)
{
    check(IsInGameThread());
    if (InputRequest.CommandId.IsNone())
    {
        SetRejectedSemanticRecord(
            InputRequest, TEXT("COMMAND_ID_REQUIRED"), OutRecord);
        return false;
    }
    UVistaPlayableHomeRuntimeSubsystem* Runtime = IsValid(GetWorld())
        ? GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>()
        : nullptr;
    if (!IsValid(Runtime))
    {
        SetRejectedSemanticRecord(
            InputRequest, TEXT("ACTION_LEDGER_UNAVAILABLE"), OutRecord);
        return false;
    }

    const FString CanonicalRequest = CanonicalSemanticRequestHex(InputRequest);
    FVistaActionTransactionRecord ClaimedRecord;
    SetRejectedSemanticRecord(
        InputRequest, TEXT("ACTION_CLAIMED"), ClaimedRecord);
    ClaimedRecord.Status = EVistaActionTransactionStatus::Running;
    const EVistaPhysicalCommandClaimOutcome Claim = Runtime->ClaimPhysicalCommand(
        InputRequest.CommandId,
        CanonicalRequest,
        this,
        ClaimedRecord,
        OutRecord);
    if (Claim == EVistaPhysicalCommandClaimOutcome::Replay)
    {
        return true;
    }
    if (Claim == EVistaPhysicalCommandClaimOutcome::Collision)
    {
        SetRejectedSemanticRecord(
            InputRequest, TEXT("COMMAND_ID_COLLISION"), OutRecord);
        return false;
    }
    if (Claim != EVistaPhysicalCommandClaimOutcome::Claimed)
    {
        SetRejectedSemanticRecord(
            InputRequest, TEXT("COMMAND_LEDGER_CAPACITY"), OutRecord);
        return false;
    }
    if (HasActiveAction())
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("ACTION_EXECUTOR_BUSY"),
            OutRecord);
    }
    if (!IsAnimatedSemanticAffordance(InputRequest.Affordance))
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("SEMANTIC_AFFORDANCE_REQUIRED"),
            OutRecord);
    }
    AActor* Requester = InputRequest.Requester;
    AActor* Target = InputRequest.Target;
    if (!IsValid(Requester) || !IsValid(Target) ||
        !Target->GetClass()->ImplementsInterface(
            UVistaInteractable::StaticClass()))
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("SEMANTIC_PARTICIPANT_INVALID"),
            OutRecord);
    }
    if (!IsValid(GetWorld()) || Requester->GetWorld() != GetWorld() ||
        Target->GetWorld() != GetWorld())
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("ACTION_WORLD_MISMATCH"),
            OutRecord);
    }
    if (!Requester->HasAuthority() || !Target->HasAuthority())
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("AUTHORITY_REQUIRED"),
            OutRecord);
    }
    if (!FMath::IsFinite(InputRequest.TimeoutSeconds) ||
        InputRequest.TimeoutSeconds <= 0.0f ||
        InputRequest.TimeoutSeconds > 300.0f)
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("ACTION_TIMEOUT_INVALID"),
            OutRecord);
    }
    const TArray<EVistaAffordance> Affordances =
        IVistaInteractable::Execute_VistaGetAffordances(Target);
    if (!Affordances.Contains(InputRequest.Affordance))
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("AFFORDANCE_UNSUPPORTED"),
            OutRecord);
    }

    FVistaSemanticActionRequest Request = InputRequest;
    Request.RequesterSemanticId = SemanticIdForActor(Requester);
    Request.TargetSemanticId = SemanticIdForActor(Target);
    if (Request.RequesterSemanticId.IsEmpty() ||
        Request.TargetSemanticId.IsEmpty() ||
        (!InputRequest.RequesterSemanticId.IsEmpty() &&
         InputRequest.RequesterSemanticId != Request.RequesterSemanticId) ||
        (!InputRequest.TargetSemanticId.IsEmpty() &&
         InputRequest.TargetSemanticId != Request.TargetSemanticId))
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("SEMANTIC_ID_MISMATCH"),
            OutRecord);
    }

    UVistaAnimationComponent* Animation =
        Requester->FindComponentByClass<UVistaAnimationComponent>();
    FName AnimationCode = IsValid(Animation)
        ? FName(TEXT("ANIMATION_NOT_APPROVED"))
        : FName(TEXT("ANIMATION_COMPONENT_UNAVAILABLE"));
    const EVistaNpcActionType AnimationType =
        AnimationTypeFor(Request.Affordance);
    if (!IsValid(Animation) ||
        !Animation->HasApprovedMutationAnimation(AnimationType, AnimationCode))
    {
        return RejectSemanticRequest(
            InputRequest, CanonicalRequest, AnimationCode, OutRecord);
    }

    FActiveSemanticAction Active;
    Active.Request = Request;
    Active.CanonicalRequest = CanonicalRequest;
    Active.Requester = Requester;
    Active.Target = Target;
    Active.Animation = Animation;
    Active.StartedAtSeconds = GetWorld()->GetTimeSeconds();
    Active.Record.CommandId = Request.CommandId;
    Active.Record.Affordance = Request.Affordance;
    Active.Record.RequesterSemanticId = Request.RequesterSemanticId;
    Active.Record.TargetSemanticId = Request.TargetSemanticId;
    Active.Record.Status = EVistaActionTransactionStatus::Running;
    Active.Record.Code = TEXT("ACTION_ACCEPTED");
    Active.Record.SessionGeneration = Request.SessionGeneration;
    Active.Record.RequesterBeforeTransform = Requester->GetActorTransform();
    Active.Record.BeforeState =
        IVistaInteractable::Execute_VistaGetRuntimeState(Target);
    Active.Record.bHasBeforeState = true;
    if (Active.Record.BeforeState.SemanticId != Request.TargetSemanticId ||
        Active.Record.BeforeState.Transform.ContainsNaN())
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("BEFORE_STATE_INVALID"),
            OutRecord);
    }
    ActiveSemanticAction = MoveTemp(Active);
    if (!TransitionSemantic(EVistaActionPhase::Approach, TEXT("ACTION_APPROACH")))
    {
        ActiveSemanticAction->Record.Status =
            EVistaActionTransactionStatus::Failed;
        ActiveSemanticAction->Record.Code = TEXT("ACTION_LEDGER_PUBLISH_FAILED");
        OutRecord = ActiveSemanticAction->Record;
        PublishSemanticRecord(true);
        ActiveSemanticAction.Reset();
        return false;
    }
    OutRecord = ActiveSemanticAction->Record;
    return true;
}

void UVistaActionExecutorComponent::TickSemanticAction()
{
    if (!ActiveSemanticAction.IsSet())
    {
        return;
    }
    const double Elapsed = GetWorld()
        ? GetWorld()->GetTimeSeconds() - ActiveSemanticAction->StartedAtSeconds
        : 0.0;
    if (Elapsed > ActiveSemanticAction->Request.TimeoutSeconds)
    {
        if (UVistaAnimationComponent* Animation =
                ActiveSemanticAction->Animation.Get())
        {
            Animation->StopActiveAction(TEXT("ACTION_TIMED_OUT"));
        }
        FinishSemanticFailure(
            EVistaActionTransactionStatus::TimedOut,
            TEXT("ACTION_TIMED_OUT"));
        return;
    }
    switch (ActiveSemanticAction->Record.Phase)
    {
    case EVistaActionPhase::Approach: AdvanceSemanticApproach(); break;
    case EVistaActionPhase::Align: AdvanceSemanticAlign(); break;
    case EVistaActionPhase::Animate: AdvanceSemanticAnimation(); break;
    case EVistaActionPhase::ContactCommit: AdvanceSemanticAnimation(); break;
    default: break;
    }
}

void UVistaActionExecutorComponent::AdvanceSemanticApproach()
{
    AActor* Requester = ActiveSemanticAction->Requester.Get();
    AActor* Target = ActiveSemanticAction->Target.Get();
    if (!IsValid(Requester) || !IsValid(Target))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_PARTICIPANT_LOST"));
        return;
    }
    FVector ContactLocation;
    if (!ResolveContactLocation(Target, ContactLocation))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_CONTACT_TARGET_AMBIGUOUS"));
        return;
    }
    if (FVector::Dist(Requester->GetActorLocation(), ContactLocation) >
        MaximumSemanticContactDistanceCm)
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_APPROACH_REQUIRED"));
        return;
    }
    if (!TransitionSemantic(EVistaActionPhase::Align, TEXT("ACTION_ALIGN")))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
    }
}

void UVistaActionExecutorComponent::AdvanceSemanticAlign()
{
    AActor* Requester = ActiveSemanticAction->Requester.Get();
    AActor* Target = ActiveSemanticAction->Target.Get();
    if (!IsValid(Requester) || !IsValid(Target))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_ALIGNMENT_TARGET_LOST"));
        return;
    }
    FVector ContactLocation;
    if (!ResolveContactLocation(Target, ContactLocation))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_CONTACT_TARGET_AMBIGUOUS"));
        return;
    }
    FVector Direction = ContactLocation - Requester->GetActorLocation();
    Direction.Z = 0.0f;
    ActiveSemanticAction->bAlignmentApplied = true;
    if (!Direction.IsNearlyZero() &&
        !Requester->SetActorRotation(Direction.Rotation()))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_ALIGNMENT_FAILED"));
        return;
    }
    if (!TransitionSemantic(EVistaActionPhase::Animate, TEXT("ACTION_ANIMATE")))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
    }
}

bool UVistaActionExecutorComponent::StartSemanticAnimation(FName& OutCode)
{
    UVistaAnimationComponent* Animation =
        ActiveSemanticAction->Animation.Get();
    AActor* Target = ActiveSemanticAction->Target.Get();
    if (!IsValid(Animation) || !IsValid(Target))
    {
        OutCode = TEXT("ANIMATION_COMPONENT_OR_TARGET_UNAVAILABLE");
        return false;
    }
    FVistaNpcAction Action;
    Action.ActionId = ActiveSemanticAction->Record.CommandId;
    Action.Type = AnimationTypeFor(ActiveSemanticAction->Request.Affordance);
    Action.TargetSemanticId = ActiveSemanticAction->Record.TargetSemanticId;
    Action.Hand = EVistaAnimationHand::Right;
    Action.TimeoutSeconds = ActiveSemanticAction->Request.TimeoutSeconds;
    return Animation->StartNpcAction(Action, Target, OutCode);
}

void UVistaActionExecutorComponent::AdvanceSemanticAnimation()
{
    UVistaAnimationComponent* Animation =
        ActiveSemanticAction->Animation.Get();
    if (!ActiveSemanticAction->bAnimationStarted)
    {
        FName Code;
        if (!StartSemanticAnimation(Code))
        {
            FinishSemanticFailure(
                EVistaActionTransactionStatus::Failed,
                Code.IsNone() ? FName(TEXT("ANIMATION_NOT_READY")) : Code);
            return;
        }
        ActiveSemanticAction->bAnimationStarted = true;
        return;
    }
    if (!IsValid(Animation))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ANIMATION_COMPONENT_LOST"));
        return;
    }

    if (!ActiveSemanticAction->Record.bContactCommitted &&
        Animation->ConsumeContactSignal())
    {
        if (!TransitionSemantic(
                EVistaActionPhase::ContactCommit,
                TEXT("ACTION_CONTACT_COMMIT")))
        {
            Animation->StopActiveAction(TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
            FinishSemanticFailure(
                EVistaActionTransactionStatus::Failed,
                TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
            return;
        }
        FName Code;
        if (!CommitSemanticContact(Code))
        {
            Animation->StopActiveAction(Code);
            FinishSemanticFailure(
                EVistaActionTransactionStatus::Failed,
                Code);
            return;
        }
    }

    const FVistaAnimationPlaybackResult Playback =
        Animation->GetPlaybackResult();
    switch (Playback.Status)
    {
    case EVistaAnimationPlaybackStatus::Running:
        return;
    case EVistaAnimationPlaybackStatus::Succeeded:
        if (!ActiveSemanticAction->Record.bContactCommitted &&
            ActiveSemanticAction->Request.Affordance ==
                EVistaAffordance::Inspect)
        {
            if (!TransitionSemantic(
                    EVistaActionPhase::ContactCommit,
                    TEXT("ACTION_READ_ONLY_COMMIT")))
            {
                FinishSemanticFailure(
                    EVistaActionTransactionStatus::Failed,
                    TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
                return;
            }
            FName Code;
            if (!CommitSemanticContact(Code))
            {
                FinishSemanticFailure(
                    EVistaActionTransactionStatus::Failed,
                    Code);
                return;
            }
        }
        if (!ActiveSemanticAction->Record.bContactCommitted)
        {
            FinishSemanticFailure(
                EVistaActionTransactionStatus::Failed,
                TEXT("ANIMATION_CONTACT_NOTIFY_MISSING"));
            return;
        }
        CompleteSemanticSuccess();
        return;
    case EVistaAnimationPlaybackStatus::TimedOut:
        FinishSemanticFailure(
            EVistaActionTransactionStatus::TimedOut,
            Playback.Code);
        return;
    case EVistaAnimationPlaybackStatus::Failed:
    case EVistaAnimationPlaybackStatus::Stopped:
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            Playback.Code);
        return;
    default:
        return;
    }
}

bool UVistaActionExecutorComponent::CommitSemanticContact(FName& OutCode)
{
    if (ActiveSemanticAction->Record.bContactMutationAttempted ||
        ActiveSemanticAction->Record.bContactCommitted)
    {
        OutCode = TEXT("CONTACT_ALREADY_COMMITTED");
        return false;
    }
    AActor* Requester = ActiveSemanticAction->Requester.Get();
    AActor* Target = ActiveSemanticAction->Target.Get();
    FVector ContactLocation;
    if (!IsValid(Requester) || !IsValid(Target) ||
        !ResolveContactLocation(Target, ContactLocation) ||
        FVector::Dist(Requester->GetActorLocation(), ContactLocation) >
            MaximumSemanticContactDistanceCm)
    {
        OutCode = TEXT("ACTION_CONTACT_OUT_OF_RANGE");
        return false;
    }
    FVistaInteractionRequest Interaction;
    Interaction.Requester = Requester;
    Interaction.Affordance = ActiveSemanticAction->Request.Affordance;
    Interaction.ExpectedRevision =
        ActiveSemanticAction->Request.ExpectedRevision;
    Interaction.SessionGeneration =
        ActiveSemanticAction->Request.SessionGeneration;
    ActiveSemanticAction->Record.bContactMutationAttempted = true;
    if (!PublishSemanticRecord(false))
    {
        OutCode = TEXT("ACTION_LEDGER_PUBLISH_FAILED");
        return false;
    }
    const FVistaInteractionResult Result =
        IVistaInteractable::Execute_VistaInteract(Target, Interaction);
    if (!Result.IsSuccess())
    {
        OutCode = Result.Code.IsNone()
            ? FName(TEXT("SEMANTIC_CONTACT_FAILED"))
            : Result.Code;
        return false;
    }
    const FVistaEntityRuntimeState ContactState =
        IVistaInteractable::Execute_VistaGetRuntimeState(Target);
    if (ContactState.SemanticId !=
            ActiveSemanticAction->Record.TargetSemanticId ||
        ContactState.Transform.ContainsNaN() ||
        !StateMatchesSemanticEffect(
            ActiveSemanticAction->Record.BeforeState,
            ContactState,
            ActiveSemanticAction->Request.Affordance))
    {
        OutCode = ActiveSemanticAction->Request.Affordance ==
                EVistaAffordance::Inspect
            ? FName(TEXT("INSPECT_MUTATION_REJECTED"))
            : FName(TEXT("CONTACT_STATE_EFFECT_MISMATCH"));
        return false;
    }
    ActiveSemanticAction->Record.ContactState = ContactState;
    ActiveSemanticAction->Record.bHasContactState = true;
    ActiveSemanticAction->Record.bContactCommitted = true;
    ActiveSemanticAction->Record.RequesterContactTransform =
        Requester->GetActorTransform();
    ActiveSemanticAction->ContactResultCode = Result.Code;
    if (!PublishSemanticRecord(false))
    {
        OutCode = TEXT("ACTION_LEDGER_PUBLISH_FAILED");
        return false;
    }
    OutCode = Result.Code;
    return true;
}

void UVistaActionExecutorComponent::CompleteSemanticSuccess()
{
    AActor* Target = ActiveSemanticAction->Target.Get();
    if (!IsValid(Target) ||
        !ActiveSemanticAction->Record.bContactCommitted)
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("CONTACT_COMMIT_EVIDENCE_INVALID"));
        return;
    }
    ActiveSemanticAction->Record.AfterState =
        IVistaInteractable::Execute_VistaGetRuntimeState(Target);
    ActiveSemanticAction->Record.bHasAfterState = true;
    if (!StateMatchesSemanticEffect(
            ActiveSemanticAction->Record.BeforeState,
            ActiveSemanticAction->Record.AfterState,
            ActiveSemanticAction->Request.Affordance) ||
        !RuntimeStatesEquivalent(
            ActiveSemanticAction->Record.ContactState,
            ActiveSemanticAction->Record.AfterState))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("AFTER_STATE_EFFECT_MISMATCH"));
        return;
    }
    ActiveSemanticAction->Record.RequesterAfterTransform =
        ActiveSemanticAction->Requester.IsValid()
            ? ActiveSemanticAction->Requester->GetActorTransform()
            : ActiveSemanticAction->Record.RequesterContactTransform;
    if (ActiveSemanticAction->Request.bCommitSessionGenerationOnSuccess)
    {
        UVistaEventSubsystem* Events = GetWorld()
            ? GetWorld()->GetSubsystem<UVistaEventSubsystem>()
            : nullptr;
        int32 CommittedGeneration =
            ActiveSemanticAction->Request.SessionGeneration;
        if (!IsValid(Events) || !Events->CommitCommandGeneration(
                ActiveSemanticAction->Request.SessionGeneration,
                CommittedGeneration))
        {
            FinishSemanticFailure(
                EVistaActionTransactionStatus::Failed,
                TEXT("SESSION_GENERATION_COMMIT_FAILED"));
            return;
        }
        ActiveSemanticAction->Record.SessionGeneration = CommittedGeneration;
    }
    if (!TransitionSemantic(
            EVistaActionPhase::Complete,
            ActiveSemanticAction->ContactResultCode.IsNone()
                ? FName(TEXT("ACTION_COMPLETE"))
                : ActiveSemanticAction->ContactResultCode))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
        return;
    }
    ActiveSemanticAction->Record.Status =
        EVistaActionTransactionStatus::Succeeded;
    if (!TransitionSemantic(
            EVistaActionPhase::Idle,
            ActiveSemanticAction->Record.Code))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
        return;
    }
    FVistaActionTransactionRecord FinalRecord;
    if (!FinalizeSemantic(&FinalRecord))
    {
        ActiveSemanticAction.Reset();
        return;
    }
    if (UVistaEventSubsystem* Events = GetWorld()
            ? GetWorld()->GetSubsystem<UVistaEventSubsystem>()
            : nullptr)
    {
        Events->RecordSuccessfulInteraction(
            FinalRecord.TargetSemanticId,
            FinalRecord.Affordance);
    }
}

void UVistaActionExecutorComponent::FinishSemanticFailure(
    EVistaActionTransactionStatus Status,
    FName Code)
{
    if (!ActiveSemanticAction.IsSet())
    {
        return;
    }
    const bool bRollbackRequired =
        ActiveSemanticAction->bAlignmentApplied ||
        ActiveSemanticAction->Record.bContactMutationAttempted;
    bool bRollbackSucceeded = true;
    if (bRollbackRequired)
    {
        TransitionSemantic(
            EVistaActionPhase::RollingBack,
            TEXT("ACTION_ROLLING_BACK"));
        ActiveSemanticAction->Record.bRollbackAttempted = true;
    }
    if (ActiveSemanticAction->bAlignmentApplied)
    {
        AActor* Requester = ActiveSemanticAction->Requester.Get();
        const bool bRestored = IsValid(Requester) &&
            Requester->SetActorTransform(
                ActiveSemanticAction->Record.RequesterBeforeTransform,
                false,
                nullptr,
                ETeleportType::TeleportPhysics);
        ActiveSemanticAction->Record.bRequesterTransformRestored = bRestored &&
            Requester->GetActorTransform().Equals(
                ActiveSemanticAction->Record.RequesterBeforeTransform,
                0.01f);
        bRollbackSucceeded =
            ActiveSemanticAction->Record.bRequesterTransformRestored;
    }
    if (ActiveSemanticAction->Record.bContactMutationAttempted)
    {
        AActor* Target = ActiveSemanticAction->Target.Get();
        const FVistaInteractionResult Restore = IsValid(Target)
            ? IVistaInteractable::Execute_VistaApplyRuntimeState(
                Target,
                ActiveSemanticAction->Record.BeforeState)
            : FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("ROLLBACK_TARGET_LOST"));
        const FVistaEntityRuntimeState RestoredState = IsValid(Target)
            ? IVistaInteractable::Execute_VistaGetRuntimeState(Target)
            : FVistaEntityRuntimeState();
        const bool bTargetRestored = Restore.IsSuccess() &&
            RuntimeStatesEquivalent(
                ActiveSemanticAction->Record.BeforeState,
                RestoredState);
        ActiveSemanticAction->Record.RollbackCode = bTargetRestored
            ? FName(TEXT("SEMANTIC_STATE_RESTORED"))
            : FName(TEXT("SEMANTIC_STATE_RESTORE_FAILED"));
        bRollbackSucceeded = bRollbackSucceeded && bTargetRestored;
        ActiveSemanticAction->Record.AfterState = RestoredState;
        ActiveSemanticAction->Record.bHasAfterState = IsValid(Target);
    }
    ActiveSemanticAction->Record.bRolledBack =
        bRollbackRequired && bRollbackSucceeded;
    if (bRollbackRequired && !bRollbackSucceeded)
    {
        Status = EVistaActionTransactionStatus::Failed;
        Code = TEXT("ACTION_ROLLBACK_FAILED");
        ActiveSemanticAction->Record.RollbackCode =
            TEXT("ACTION_ROLLBACK_FAILED");
    }
    ActiveSemanticAction->Record.RequesterAfterTransform =
        ActiveSemanticAction->Requester.IsValid()
            ? ActiveSemanticAction->Requester->GetActorTransform()
            : ActiveSemanticAction->Record.RequesterBeforeTransform;
    TransitionSemantic(
        EVistaActionPhase::Failed,
        Code.IsNone() ? FName(TEXT("ACTION_FAILED")) : Code);
    ActiveSemanticAction->Record.Status = Status;
    TransitionSemantic(
        EVistaActionPhase::Idle,
        ActiveSemanticAction->Record.Code);
    if (!FinalizeSemantic())
    {
        ActiveSemanticAction.Reset();
    }
}

bool UVistaActionExecutorComponent::TransitionSemantic(
    const EVistaActionPhase Phase,
    const FName Code)
{
    check(ActiveSemanticAction.IsSet());
    check(IsInGameThread());
    ActiveSemanticAction->Record.Phase = Phase;
    ActiveSemanticAction->Record.Code = Code;
    ActiveSemanticAction->Record.PhaseHistory.Add(Phase);
    return PublishSemanticRecord(false);
}

bool UVistaActionExecutorComponent::PublishSemanticRecord(const bool bTerminal)
{
    if (!ActiveSemanticAction.IsSet() || !IsValid(GetWorld()))
    {
        return false;
    }
    UVistaPlayableHomeRuntimeSubsystem* Runtime =
        GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>();
    return IsValid(Runtime) && Runtime->PublishPhysicalCommand(
        ActiveSemanticAction->Record.CommandId,
        ActiveSemanticAction->CanonicalRequest,
        this,
        ActiveSemanticAction->Record,
        bTerminal);
}

bool UVistaActionExecutorComponent::FinalizeSemantic(
    FVistaActionTransactionRecord* OutFinalRecord)
{
    check(ActiveSemanticAction.IsSet());
    if (!PublishSemanticRecord(true))
    {
        return false;
    }
    if (OutFinalRecord != nullptr)
    {
        *OutFinalRecord = ActiveSemanticAction->Record;
    }
    ActiveSemanticAction.Reset();
    return true;
}
