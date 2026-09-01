#include "VistaActionExecutorComponent.h"

#include "Containers/StringConv.h"
#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "HAL/PlatformMemory.h"
#include "VistaAnimationComponent.h"
#include "VistaContainerActor.h"
#include "VistaEventSubsystem.h"
#include "VistaInteractable.h"
#include "VistaPlayableHomeRuntimeSubsystem.h"
#include "VistaPostureComponent.h"
#include "VistaSeatActor.h"
#include "VistaStatefulApplianceActor.h"

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
    case EVistaAffordance::Inspect: return EVistaNpcActionType::Inspect;
    case EVistaAffordance::Toggle: return EVistaNpcActionType::Toggle;
    case EVistaAffordance::Press: return EVistaNpcActionType::Press;
    case EVistaAffordance::TurnOn: return EVistaNpcActionType::TurnOn;
    case EVistaAffordance::TurnOff: return EVistaNpcActionType::TurnOff;
    case EVistaAffordance::Sit:
        return EVistaNpcActionType::Sit;
    case EVistaAffordance::Stand:
        return EVistaNpcActionType::StandUp;
    default: return EVistaNpcActionType::Wait;
    }
}

bool StateMatchesSemanticEffect(
    const FVistaEntityRuntimeState& Before,
    const FVistaEntityRuntimeState& After,
    const EVistaAffordance Affordance,
    const AActor* Target,
    const AActor* Requester,
    const FString& RequesterSemanticId)
{
    if (Affordance == EVistaAffordance::Inspect)
    {
        return RuntimeStatesEquivalent(Before, After);
    }
    if (Affordance == EVistaAffordance::Sit || Affordance == EVistaAffordance::Stand)
    {
        const AVistaSeatActor* Seat = Cast<AVistaSeatActor>(Target);
        const FString* BeforeOccupied = Before.Values.Find(TEXT("occupied"));
        const FString* BeforeOccupant = Before.Values.Find(TEXT("occupied_by"));
        const FString* AfterOccupied = After.Values.Find(TEXT("occupied"));
        const FString* AfterOccupant = After.Values.Find(TEXT("occupied_by"));
        if (!IsValid(Seat) ||
            !IsValid(Requester) ||
            RequesterSemanticId.IsEmpty() ||
            BeforeOccupied == nullptr ||
            BeforeOccupant == nullptr ||
            AfterOccupied == nullptr ||
            AfterOccupant == nullptr)
        {
            return false;
        }
        if (Affordance == EVistaAffordance::Sit)
        {
            return BeforeOccupied->Equals(TEXT("false"), ESearchCase::CaseSensitive) &&
                AfterOccupied->Equals(TEXT("true"), ESearchCase::CaseSensitive) &&
                AfterOccupant->Equals(RequesterSemanticId, ESearchCase::CaseSensitive) &&
                Seat->IsOccupiedBy(Requester, RequesterSemanticId);
        }
        return BeforeOccupied->Equals(TEXT("true"), ESearchCase::CaseSensitive) &&
            BeforeOccupant->Equals(RequesterSemanticId, ESearchCase::CaseSensitive) &&
            AfterOccupied->Equals(TEXT("false"), ESearchCase::CaseSensitive) &&
            AfterOccupant->IsEmpty() &&
            !Seat->IsOccupied();
    }
    if (AVistaStatefulApplianceActor::IsTransactionalApplianceAffordance(
            Affordance))
    {
        const AVistaStatefulApplianceActor* Appliance =
            Cast<AVistaStatefulApplianceActor>(Target);
        return IsValid(Appliance) &&
            Appliance->StateMatchesTransition(Before, After, Affordance);
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
            (!Component->ComponentHasTag(
                 FName(TEXT("VistaDoorHandleTarget"))) &&
             !Component->ComponentHasTag(
                 FName(TEXT("VistaInteractionTarget"))) &&
             !Component->ComponentHasTag(FName(TEXT("VistaSeatTarget")))))
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
        Affordance == EVistaAffordance::Inspect ||
        Affordance == EVistaAffordance::Sit ||
        Affordance == EVistaAffordance::Stand ||
        AVistaStatefulApplianceActor::IsTransactionalApplianceAffordance(
            Affordance);
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
    return BeginSemanticInteractionImpl(InputRequest, OutRecord, false);
}

#if WITH_DEV_AUTOMATION_TESTS
bool UVistaActionExecutorComponent::BeginSemanticInteractionForDevAutomation(
    const FVistaSemanticActionRequest& InputRequest,
    FVistaActionTransactionRecord& OutRecord)
{
    return BeginSemanticInteractionImpl(InputRequest, OutRecord, true);
}
#endif

bool UVistaActionExecutorComponent::BeginSemanticInteractionImpl(
    const FVistaSemanticActionRequest& InputRequest,
    FVistaActionTransactionRecord& OutRecord,
    const bool bDevAutomationBypassesAnimationReadiness)
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
    const bool bApplianceMutation =
        AVistaStatefulApplianceActor::IsTransactionalApplianceAffordance(
            InputRequest.Affordance);
    const bool bContainerMutation =
        (InputRequest.Affordance == EVistaAffordance::Open ||
         InputRequest.Affordance == EVistaAffordance::Close) &&
        IsValid(Cast<AVistaContainerActor>(Target));
    const bool bPostureMutation = InputRequest.Affordance == EVistaAffordance::Sit ||
        InputRequest.Affordance == EVistaAffordance::Stand;
    AVistaStatefulApplianceActor* Appliance =
        Cast<AVistaStatefulApplianceActor>(Target);
    if (bApplianceMutation && !IsValid(Appliance))
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("APPLIANCE_TARGET_REQUIRED"),
            OutRecord);
    }
    AVistaSeatActor* Seat = Cast<AVistaSeatActor>(Target);
    UVistaPostureComponent* Posture = Requester->FindComponentByClass<UVistaPostureComponent>();
    if (bPostureMutation && (!IsValid(Seat) || !IsValid(Posture)))
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            !IsValid(Seat)
                ? FName(TEXT("SEAT_TARGET_REQUIRED"))
                : FName(TEXT("POSTURE_COMPONENT_REQUIRED")),
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
    bool bAnimationReady = IsValid(Animation) &&
        Animation->HasApprovedMutationAnimation(
            AnimationType, Target, AnimationCode);
#if WITH_DEV_AUTOMATION_TESTS
    bAnimationReady = bAnimationReady ||
        bDevAutomationBypassesAnimationReadiness;
#else
    static_cast<void>(bDevAutomationBypassesAnimationReadiness);
#endif
    if (!bAnimationReady)
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
    Active.Posture = Posture;
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
    if (bApplianceMutation)
    {
        if (!Appliance->TryReserveTransaction(this, Request.CommandId))
        {
            return RejectSemanticRequest(
                InputRequest,
                CanonicalRequest,
                TEXT("APPLIANCE_TARGET_BUSY"),
                OutRecord);
        }
        Active.bTargetReserved = true;
        Active.Record.bTargetReservationAcquired = true;
    }
    else if (bContainerMutation)
    {
        AVistaContainerActor* Container = Cast<AVistaContainerActor>(Target);
        if (!IsValid(Container) ||
            !Container->TryReserveTransaction(this, Request.CommandId))
        {
            return RejectSemanticRequest(
                InputRequest,
                CanonicalRequest,
                TEXT("CONTAINER_TARGET_BUSY"),
                OutRecord);
        }
        Active.bTargetReserved = true;
        Active.Record.bTargetReservationAcquired = true;
    }
    ActiveSemanticAction = MoveTemp(Active);
    if (!TransitionSemantic(EVistaActionPhase::Approach, TEXT("ACTION_APPROACH")))
    {
        ActiveSemanticAction->Record.Status =
            EVistaActionTransactionStatus::Failed;
        ActiveSemanticAction->Record.Code = TEXT("ACTION_LEDGER_PUBLISH_FAILED");
        ReleaseSemanticTargetReservation();
        OutRecord = ActiveSemanticAction->Record;
        PublishSemanticRecord(true);
        AbandonSemanticAfterPublishFailure();
        return false;
    }
    OutRecord = ActiveSemanticAction->Record;
    return true;
}

#if WITH_DEV_AUTOMATION_TESTS
bool UVistaActionExecutorComponent::DriveSemanticInteractionForDevAutomation(
    const bool bFailAfterContact,
    FVistaActionTransactionRecord& OutRecord)
{
    check(IsInGameThread());
    if (!ActiveSemanticAction.IsSet())
    {
        OutRecord = FVistaActionTransactionRecord();
        OutRecord.Code = TEXT("DEV_AUTOMATION_SEMANTIC_ACTION_REQUIRED");
        OutRecord.Status = EVistaActionTransactionStatus::Failed;
        return false;
    }

    const FName CommandId = ActiveSemanticAction->Record.CommandId;
    AdvanceSemanticApproach();
    if (!ActiveSemanticAction.IsSet() ||
        ActiveSemanticAction->Record.Phase != EVistaActionPhase::Align)
    {
        return GetTransaction(CommandId, OutRecord) && OutRecord.IsTerminal();
    }
    AdvanceSemanticAlign();
    if (!ActiveSemanticAction.IsSet() ||
        ActiveSemanticAction->Record.Phase != EVistaActionPhase::Animate)
    {
        return GetTransaction(CommandId, OutRecord) && OutRecord.IsTerminal();
    }
    if (!TransitionSemantic(
            EVistaActionPhase::ContactCommit,
            TEXT("DEV_AUTOMATION_SEMANTIC_CONTACT_COMMIT")))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
        GetTransaction(CommandId, OutRecord);
        return false;
    }

    FName ContactCode;
    if (!CommitSemanticContact(ContactCode))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            ContactCode.IsNone()
                ? FName(TEXT("DEV_AUTOMATION_SEMANTIC_CONTACT_FAILED"))
                : ContactCode);
        GetTransaction(CommandId, OutRecord);
        return false;
    }
    if (bFailAfterContact)
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("DEV_AUTOMATION_FORCED_POST_CONTACT_FAILURE"));
    }
    else
    {
        CompleteSemanticSuccess();
    }
    if (!GetTransaction(CommandId, OutRecord))
    {
        OutRecord = FVistaActionTransactionRecord();
        OutRecord.CommandId = CommandId;
        OutRecord.Code = TEXT("DEV_AUTOMATION_LEDGER_RECORD_MISSING");
        OutRecord.Status = EVistaActionTransactionStatus::Failed;
        return false;
    }
    return bFailAfterContact
        ? OutRecord.Status == EVistaActionTransactionStatus::Failed &&
            OutRecord.bRollbackAttempted && OutRecord.bRolledBack &&
            OutRecord.bTargetReservationReleased
        : OutRecord.Status == EVistaActionTransactionStatus::Succeeded &&
            OutRecord.bTargetReservationReleased;
}
#endif

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
    ActiveSemanticAction->bAlignmentApplied = true;
    const bool bPostureMutation =
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Sit ||
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Stand;
    if (bPostureMutation)
    {
        UVistaPostureComponent* Posture = ActiveSemanticAction->Posture.Get();
        AVistaSeatActor* Seat = Cast<AVistaSeatActor>(Target);
        if (!IsValid(Posture) || !IsValid(Seat))
        {
            FinishSemanticFailure(EVistaActionTransactionStatus::Failed, TEXT("POSTURE_PARTICIPANT_LOST"));
            return;
        }
        const FVistaPostureTransitionResult PostureResult =
            ActiveSemanticAction->Request.Affordance == EVistaAffordance::Sit
                ? Posture->BeginSitTransition(Seat, ActiveSemanticAction->Record.CommandId)
                : Posture->BeginStandTransition(ActiveSemanticAction->Record.CommandId);
        if (!PostureResult.bSucceeded)
        {
            const bool bTransitionStillActive =
                Posture->GetPostureState() == EVistaPostureState::SittingTransition ||
                Posture->GetPostureState() == EVistaPostureState::StandingTransition ||
                Seat->IsReserved();
            if (bTransitionStillActive)
            {
                ActiveSemanticAction->bPostureTransitionStarted = true;
                ActiveSemanticAction->bTargetReserved = Seat->IsReserved();
                ActiveSemanticAction->Record.bTargetReservationAcquired = Seat->IsReserved();
            }
            FinishSemanticFailure(EVistaActionTransactionStatus::Failed, PostureResult.Code);
            return;
        }
        ActiveSemanticAction->bPostureTransitionStarted = true;
        ActiveSemanticAction->bTargetReserved = true;
        ActiveSemanticAction->Record.bTargetReservationAcquired = true;
        if (ActiveSemanticAction->Request.Affordance == EVistaAffordance::Stand)
        {
            if (UVistaAnimationComponent* Animation = ActiveSemanticAction->Animation.Get())
            {
                Animation->StopActiveAction(TEXT("POSTURE_STAND_REQUESTED"));
            }
        }
    }
    else
    {
        FVector Direction = ContactLocation - Requester->GetActorLocation();
        Direction.Z = 0.0f;
        if (!Direction.IsNearlyZero() &&
            !Requester->SetActorRotation(Direction.Rotation()))
        {
            FinishSemanticFailure(
                EVistaActionTransactionStatus::Failed,
                TEXT("ACTION_ALIGNMENT_FAILED"));
            return;
        }
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
    const bool bApplianceMutation =
        AVistaStatefulApplianceActor::IsTransactionalApplianceAffordance(
            ActiveSemanticAction->Request.Affordance);
    AVistaStatefulApplianceActor* Appliance =
        Cast<AVistaStatefulApplianceActor>(Target);
    const bool bContainerMutation =
        (ActiveSemanticAction->Request.Affordance == EVistaAffordance::Open ||
         ActiveSemanticAction->Request.Affordance == EVistaAffordance::Close) &&
        IsValid(Cast<AVistaContainerActor>(Target));
    AVistaContainerActor* Container = Cast<AVistaContainerActor>(Target);
    FVistaInteractionResult Result;
    if (ActiveSemanticAction->bPostureTransitionStarted)
    {
        UVistaPostureComponent* Posture = ActiveSemanticAction->Posture.Get();
        const FVistaPostureTransitionResult PostureResult =
            !IsValid(Posture) ? FVistaPostureTransitionResult()
            : ActiveSemanticAction->Request.Affordance == EVistaAffordance::Sit
                ? Posture->CommitSitAtCompletion(ActiveSemanticAction->Record.CommandId)
                : Posture->CommitStandAtCompletion(ActiveSemanticAction->Record.CommandId);
        Result = PostureResult.bSucceeded
                     ? FVistaInteractionResult::Success(ActiveSemanticAction->Record.TargetSemanticId,
                                                        IVistaInteractable::Execute_VistaGetRuntimeState(Target),
                                                        PostureResult.Code)
                     : FVistaInteractionResult::Failure(
                           EVistaInteractionStatus::InvalidState,
                           PostureResult.Code.IsNone() ? FName(TEXT("POSTURE_COMMIT_FAILED")) : PostureResult.Code,
                           ActiveSemanticAction->Record.TargetSemanticId);
    }
    else
    {
        Result = bApplianceMutation && IsValid(Appliance)
            ? Appliance->CommitTransactionalInteraction(
                this,
                Interaction,
                ActiveSemanticAction->Record.CommandId)
            : bContainerMutation && IsValid(Container)
                ? Container->CommitTransactionalInteraction(
                    this,
                    Interaction,
                    ActiveSemanticAction->Record.CommandId)
                : IVistaInteractable::Execute_VistaInteract(Target, Interaction);
    }
    if (!Result.IsSuccess())
    {
        OutCode = Result.Code.IsNone()
            ? FName(TEXT("SEMANTIC_CONTACT_FAILED"))
            : Result.Code;
        return false;
    }
    const FVistaEntityRuntimeState ContactState =
        IVistaInteractable::Execute_VistaGetRuntimeState(Target);
    ActiveSemanticAction->Record.StateMutationCount =
        RuntimeStatesEquivalent(
            ActiveSemanticAction->Record.BeforeState,
            ContactState)
        ? 0 : 1;
    if (ContactState.SemanticId !=
            ActiveSemanticAction->Record.TargetSemanticId ||
        ContactState.Transform.ContainsNaN() ||
        !StateMatchesSemanticEffect(
            ActiveSemanticAction->Record.BeforeState,
            ContactState,
            ActiveSemanticAction->Request.Affordance,
            Target,
            Requester,
            ActiveSemanticAction->Request.RequesterSemanticId))
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
            ActiveSemanticAction->Request.Affordance,
            Target,
            ActiveSemanticAction->Requester.Get(),
            ActiveSemanticAction->Request.RequesterSemanticId) ||
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
    const bool bStartSeatedIdle = ActiveSemanticAction->Request.Affordance == EVistaAffordance::Sit;
    TWeakObjectPtr<UVistaAnimationComponent> CompletedAnimation = ActiveSemanticAction->Animation;
    TWeakObjectPtr<UVistaPostureComponent> CompletedPosture = ActiveSemanticAction->Posture;
    TWeakObjectPtr<AActor> CompletedTarget = ActiveSemanticAction->Target;
    FVistaActionTransactionRecord FinalRecord;
    if (!FinalizeSemantic(&FinalRecord))
    {
        if (ActiveSemanticAction.IsSet())
        {
            FinishSemanticFailure(EVistaActionTransactionStatus::Failed,
                                  ActiveSemanticAction->Record.Code.IsNone()
                                      ? FName(TEXT("ACTION_LEDGER_TERMINAL_PUBLISH_FAILED"))
                                      : ActiveSemanticAction->Record.Code);
        }
        return;
    }
    if (bStartSeatedIdle && CompletedAnimation.IsValid() && CompletedPosture.IsValid() &&
        CompletedPosture->IsSeatedLoopAuthorized())
    {
        FVistaNpcAction IdleAction;
        IdleAction.ActionId = FName(*FString::Printf(
            TEXT("%s.seated_idle"),
            *FinalRecord.CommandId.ToString()));
        IdleAction.Type = EVistaNpcActionType::SeatedIdle;
        IdleAction.TargetSemanticId = FinalRecord.TargetSemanticId;
        IdleAction.TimeoutSeconds = 300.0f;
        FName IdleCode;
        if (!CompletedAnimation->StartNpcAction(IdleAction, CompletedTarget.Get(), IdleCode))
        {
            UE_LOG(LogTemp, Error, TEXT("VISTA_SEATED_IDLE_START_FAILED command=%s code=%s"),
                   *FinalRecord.CommandId.ToString(), *IdleCode.ToString());
        }
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
    const bool bPostureMutation = ActiveSemanticAction->bPostureTransitionStarted &&
                                  (ActiveSemanticAction->Request.Affordance == EVistaAffordance::Sit ||
                                   ActiveSemanticAction->Request.Affordance == EVistaAffordance::Stand);
    bool bRollbackSucceeded = true;
    if (bRollbackRequired)
    {
        TransitionSemantic(
            EVistaActionPhase::RollingBack,
            TEXT("ACTION_ROLLING_BACK"));
        ActiveSemanticAction->Record.bRollbackAttempted = true;
    }
    if (ActiveSemanticAction->bAlignmentApplied && !bPostureMutation)
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
    if (bPostureMutation)
    {
        UVistaPostureComponent* Posture = ActiveSemanticAction->Posture.Get();
        AVistaSeatActor* Seat = Cast<AVistaSeatActor>(ActiveSemanticAction->Target.Get());
        FVistaPostureTransitionResult Restore;
        if (!IsValid(Posture) || !IsValid(Seat))
        {
            Restore.Code = TEXT("POSTURE_ROLLBACK_PARTICIPANT_LOST");
        }
        else if (ActiveSemanticAction->Request.Affordance == EVistaAffordance::Sit)
        {
            if (Posture->GetPostureState() == EVistaPostureState::SittingTransition)
            {
                Restore = Posture->RollbackSitTransition(ActiveSemanticAction->Record.CommandId);
            }
            else if (Posture->GetPostureState() == EVistaPostureState::Seated)
            {
                const FVistaPostureTransitionResult BeginCompensation =
                    Posture->BeginStandTransition(ActiveSemanticAction->Record.CommandId);
                if (BeginCompensation.bSucceeded)
                {
                    const FVistaPostureTransitionResult CommitCompensation =
                        Posture->CommitStandAtCompletion(ActiveSemanticAction->Record.CommandId);
                    Restore = CommitCompensation.bSucceeded
                                  ? Posture->FinalizeCommittedStand(ActiveSemanticAction->Record.CommandId)
                                  : CommitCompensation;
                }
                else
                {
                    Restore = BeginCompensation;
                }
            }
            else
            {
                Restore.Code = TEXT("POSTURE_SIT_ROLLBACK_STATE_INVALID");
            }
        }
        else if (Posture->GetPostureState() == EVistaPostureState::StandingTransition)
        {
            Restore = Posture->RollbackStandTransition(ActiveSemanticAction->Record.CommandId);
        }
        else if (Posture->GetPostureState() == EVistaPostureState::Standing)
        {
            Restore = Posture->RollbackCommittedStand(ActiveSemanticAction->Record.CommandId);
        }
        else
        {
            Restore.Code = TEXT("POSTURE_STAND_ROLLBACK_STATE_INVALID");
        }

        AActor* Requester = ActiveSemanticAction->Requester.Get();
        const FVistaEntityRuntimeState RestoredState =
            IsValid(Seat) ? IVistaInteractable::Execute_VistaGetRuntimeState(Seat) : FVistaEntityRuntimeState();
        const bool bTargetRestored = Restore.bSucceeded && IsValid(Seat) &&
                                     RuntimeStatesEquivalent(ActiveSemanticAction->Record.BeforeState, RestoredState);
        ActiveSemanticAction->Record.bRequesterTransformRestored =
            IsValid(Requester) &&
            Requester->GetActorTransform().Equals(ActiveSemanticAction->Record.RequesterBeforeTransform, 0.01f);
        ActiveSemanticAction->Record.AfterState = RestoredState;
        ActiveSemanticAction->Record.bHasAfterState = IsValid(Seat);
        ActiveSemanticAction->Record.RollbackCode =
            bTargetRestored && ActiveSemanticAction->Record.bRequesterTransformRestored
            ? FName(TEXT("POSTURE_STATE_RESTORED"))
            : (Restore.Code.IsNone()
                ? FName(TEXT("POSTURE_STATE_RESTORE_FAILED"))
                : Restore.Code);
        bRollbackSucceeded =
            bRollbackSucceeded && bTargetRestored && ActiveSemanticAction->Record.bRequesterTransformRestored;
        if (IsValid(Seat) && !Seat->IsReserved())
        {
            ActiveSemanticAction->bTargetReserved = false;
            ActiveSemanticAction->Record.bTargetReservationReleased = true;
        }
    }
    if (ActiveSemanticAction->Record.bContactMutationAttempted && !bPostureMutation)
    {
        AActor* Target = ActiveSemanticAction->Target.Get();
        AVistaStatefulApplianceActor* Appliance =
            Cast<AVistaStatefulApplianceActor>(Target);
        AVistaContainerActor* Container =
            Cast<AVistaContainerActor>(Target);
        const bool bApplianceMutation =
            AVistaStatefulApplianceActor::IsTransactionalApplianceAffordance(
                ActiveSemanticAction->Request.Affordance);
        const bool bContainerMutation =
            (ActiveSemanticAction->Request.Affordance == EVistaAffordance::Open ||
             ActiveSemanticAction->Request.Affordance == EVistaAffordance::Close) &&
            IsValid(Container);
        const FVistaInteractionResult Restore = !IsValid(Target)
            ? FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("ROLLBACK_TARGET_LOST"))
            : bApplianceMutation && IsValid(Appliance)
                ? Appliance->RestoreTransactionalState(
                    this,
                    ActiveSemanticAction->Record.CommandId,
                    ActiveSemanticAction->Record.BeforeState)
                : bContainerMutation
                    ? Container->RestoreTransactionalState(
                        this,
                        ActiveSemanticAction->Record.CommandId,
                        ActiveSemanticAction->Record.BeforeState)
                    : IVistaInteractable::Execute_VistaApplyRuntimeState(
                        Target,
                        ActiveSemanticAction->Record.BeforeState);
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
        AbandonSemanticAfterPublishFailure();
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
    UVistaPlayableHomeRuntimeSubsystem* Runtime =
        IsValid(GetWorld()) ? GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>() : nullptr;
    FName FinalizeCode;
    const bool bTerminalPublished = IsValid(Runtime) &&
        Runtime->FinalizePhysicalCommand(
            ActiveSemanticAction->Record.CommandId,
            ActiveSemanticAction->CanonicalRequest,
            this,
            ActiveSemanticAction->Record,
            ActiveSemanticAction->Record.Status == EVistaActionTransactionStatus::Succeeded &&
                ActiveSemanticAction->Request.bCommitSessionGenerationOnSuccess,
            ActiveSemanticAction->Request.SessionGeneration,
            [this]() { return ReleaseSemanticTargetReservation(); },
            FinalizeCode);
    if (!bTerminalPublished)
    {
        ActiveSemanticAction->Record.Code = FinalizeCode.IsNone()
            ? FName(TEXT("ACTION_LEDGER_TERMINAL_PUBLISH_FAILED"))
            : FinalizeCode;
        if (OutFinalRecord != nullptr)
        {
            *OutFinalRecord = ActiveSemanticAction->Record;
        }
        return false;
    }
    if (OutFinalRecord != nullptr)
    {
        *OutFinalRecord = ActiveSemanticAction->Record;
    }
    ActiveSemanticAction.Reset();
    return true;
}

bool UVistaActionExecutorComponent::ReleaseSemanticTargetReservation()
{
    if (!ActiveSemanticAction.IsSet() ||
        !ActiveSemanticAction->bTargetReserved)
    {
        return true;
    }
    AVistaStatefulApplianceActor* Appliance =
        Cast<AVistaStatefulApplianceActor>(
            ActiveSemanticAction->Target.Get());
    AVistaContainerActor* Container = Cast<AVistaContainerActor>(
        ActiveSemanticAction->Target.Get());
    AVistaSeatActor* Seat = Cast<AVistaSeatActor>(ActiveSemanticAction->Target.Get());
    UVistaPostureComponent* Posture = ActiveSemanticAction->Posture.Get();
    const bool bReleased = IsValid(Appliance)
        ? Appliance->ReleaseTransaction(
            this,
            ActiveSemanticAction->Record.CommandId)
        : IsValid(Container)
            ? Container->ReleaseTransaction(
                this,
                ActiveSemanticAction->Record.CommandId)
        : ActiveSemanticAction->bPostureTransitionStarted
            ? ActiveSemanticAction->Request.Affordance == EVistaAffordance::Stand
                  ? IsValid(Posture) &&
                        Posture->FinalizeCommittedStand(ActiveSemanticAction->Record.CommandId).bSucceeded
                  : IsValid(Seat) && !Seat->IsReserved()
            : true;
    if (!bReleased)
    {
        return false;
    }
    ActiveSemanticAction->bTargetReserved = false;
    ActiveSemanticAction->Record.bTargetReservationReleased = true;
    return true;
}

void UVistaActionExecutorComponent::AbandonSemanticAfterPublishFailure()
{
    if (!ActiveSemanticAction.IsSet())
    {
        return;
    }
    if (UVistaAnimationComponent* Animation =
            ActiveSemanticAction->Animation.Get())
    {
        Animation->StopActiveAction(TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
    }
    ReleaseSemanticTargetReservation();
    ActiveSemanticAction.Reset();
}
