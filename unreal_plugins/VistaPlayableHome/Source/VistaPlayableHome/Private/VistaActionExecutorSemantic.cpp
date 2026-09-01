#include "VistaActionExecutorComponent.h"

#include "Containers/StringConv.h"
#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "HAL/PlatformMemory.h"
#include "VistaAnimationComponent.h"
#include "VistaContainerActor.h"
#include "VistaEventSubsystem.h"
#include "VistaInteractable.h"
#include "VistaItemCarrier.h"
#include "VistaLiquidReceiverActor.h"
#include "VistaPickupActor.h"
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

bool RuntimeStateValuesEquivalent(
    const FVistaEntityRuntimeState& Left,
    const FVistaEntityRuntimeState& Right)
{
    if (Left.SemanticId != Right.SemanticId ||
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

bool LiquidStatesEquivalent(
    const FVistaLiquidStateSnapshot& Left,
    const FVistaLiquidStateSnapshot& Right)
{
    return Left.bPourable == Right.bPourable &&
        Left.LiquidType == Right.LiquidType &&
        FPlatformMemory::Memcmp(
            &Left.CapacityMilliliters,
            &Right.CapacityMilliliters,
            sizeof(float)) == 0 &&
        FPlatformMemory::Memcmp(
            &Left.AmountMilliliters,
            &Right.AmountMilliliters,
            sizeof(float)) == 0;
}

bool HeldPhysicalStateStableAcrossAlignment(
    const FVistaPickupPhysicalStateSnapshot& Before,
    const FVistaPickupPhysicalStateSnapshot& Aligned)
{
    return Before.bSimulatePhysics == Aligned.bSimulatePhysics &&
        Before.CollisionEnabled == Aligned.CollisionEnabled &&
        Before.CollisionProfileName == Aligned.CollisionProfileName &&
        Before.LinearVelocity == Aligned.LinearVelocity &&
        Before.AngularVelocityDegrees == Aligned.AngularVelocityDegrees &&
        Before.bHasAttachmentParent == Aligned.bHasAttachmentParent &&
        Before.AttachmentParentOwnerSemanticId ==
            Aligned.AttachmentParentOwnerSemanticId &&
        Before.AttachmentParentComponentName ==
            Aligned.AttachmentParentComponentName &&
        Before.AttachmentSocketName == Aligned.AttachmentSocketName &&
        Before.AttachmentRelativeTransform.Equals(
            Aligned.AttachmentRelativeTransform, 0.0f) &&
        Before.bHeld == Aligned.bHeld &&
        Before.CarrierSemanticId == Aligned.CarrierSemanticId &&
        Before.InventoryCarrierSemanticId ==
            Aligned.InventoryCarrierSemanticId &&
        Before.bInventorySlotOccupied ==
            Aligned.bInventorySlotOccupied &&
        Before.InventoryItemSemanticId ==
            Aligned.InventoryItemSemanticId &&
        Before.PlacedAtSemanticId == Aligned.PlacedAtSemanticId &&
        Before.ContainedInSemanticId == Aligned.ContainedInSemanticId;
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
    case EVistaAffordance::Pour:
        return EVistaNpcActionType::Pour;
    case EVistaAffordance::Insert:
        return EVistaNpcActionType::Insert;
    case EVistaAffordance::Remove:
        return EVistaNpcActionType::Remove;
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
    if (Affordance == EVistaAffordance::Insert ||
        Affordance == EVistaAffordance::Remove)
    {
        const FString* BeforeHeld = Before.Values.Find(TEXT("held"));
        const FString* BeforeHeldBy = Before.Values.Find(TEXT("held_by"));
        const FString* BeforeContained = Before.Values.Find(TEXT("contained_in"));
        const FString* AfterHeld = After.Values.Find(TEXT("held"));
        const FString* AfterHeldBy = After.Values.Find(TEXT("held_by"));
        const FString* AfterContained = After.Values.Find(TEXT("contained_in"));
        if (BeforeHeld == nullptr || BeforeHeldBy == nullptr ||
            AfterHeld == nullptr || AfterHeldBy == nullptr ||
            RequesterSemanticId.IsEmpty())
        {
            return false;
        }
        if (Affordance == EVistaAffordance::Insert)
        {
            return BeforeHeld->Equals(
                       TEXT("true"), ESearchCase::CaseSensitive) &&
                *BeforeHeldBy == RequesterSemanticId &&
                (BeforeContained == nullptr || BeforeContained->IsEmpty()) &&
                AfterHeld->Equals(
                    TEXT("false"), ESearchCase::CaseSensitive) &&
                AfterHeldBy->IsEmpty() && AfterContained != nullptr &&
                !AfterContained->IsEmpty();
        }
        return BeforeHeld->Equals(
                   TEXT("false"), ESearchCase::CaseSensitive) &&
            BeforeHeldBy->IsEmpty() && BeforeContained != nullptr &&
            !BeforeContained->IsEmpty() &&
            AfterHeld->Equals(
                TEXT("true"), ESearchCase::CaseSensitive) &&
            *AfterHeldBy == RequesterSemanticId &&
            (AfterContained == nullptr || AfterContained->IsEmpty());
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

bool ResolveContactLocation(
    const AActor* Target,
    const EVistaAffordance Affordance,
    FVector& OutLocation)
{
    if (!IsValid(Target))
    {
        return false;
    }
    TArray<USceneComponent*> Components;
    Target->GetComponents<USceneComponent>(Components);
    USceneComponent* TaggedContact = nullptr;
    const bool bStorageTransfer = Affordance == EVistaAffordance::Insert ||
        Affordance == EVistaAffordance::Remove;
    for (USceneComponent* Component : Components)
    {
        const bool bMatches = IsValid(Component) &&
            (bStorageTransfer
                ? Component->ComponentHasTag(
                      FName(TEXT("VistaContainerContentsTarget")))
                : Component->ComponentHasTag(
                      FName(TEXT("VistaDoorHandleTarget"))) ||
                    Component->ComponentHasTag(
                        FName(TEXT("VistaInteractionTarget"))) ||
                    Component->ComponentHasTag(
                        FName(TEXT("VistaSeatTarget"))));
        if (!bMatches)
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
        Affordance == EVistaAffordance::Pour ||
        Affordance == EVistaAffordance::Insert ||
        Affordance == EVistaAffordance::Remove ||
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
    const FString SecondaryTargetId =
        Request.SecondaryTargetSemanticId.IsEmpty()
        ? SemanticIdForActor(Request.SecondaryTarget)
        : Request.SecondaryTargetSemanticId;
    TArray<uint8> Bytes;
    Bytes.Reserve(256);
    AppendUtf8(Bytes, TEXT("vista.semantic-command/v2"));
    AppendUtf8(Bytes, RequesterId);
    AppendUtf8(Bytes, TargetId);
    AppendUtf8(Bytes, SecondaryTargetId);
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
    OutRecord.SecondaryTargetSemanticId =
        Request.SecondaryTargetSemanticId.IsEmpty()
        ? SemanticIdForActor(Request.SecondaryTarget)
        : Request.SecondaryTargetSemanticId;
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
    AActor* SecondaryTarget = InputRequest.SecondaryTarget;
    const bool bPourMutation =
        InputRequest.Affordance == EVistaAffordance::Pour;
    const bool bStorageMutation =
        InputRequest.Affordance == EVistaAffordance::Insert ||
        InputRequest.Affordance == EVistaAffordance::Remove;
    const bool bTwoTargetMutation = bPourMutation || bStorageMutation;
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
    AVistaPickupActor* PourSource = bPourMutation
        ? Cast<AVistaPickupActor>(Target) : nullptr;
    AVistaLiquidReceiverActor* PourReceiver = bPourMutation
        ? Cast<AVistaLiquidReceiverActor>(SecondaryTarget) : nullptr;
    AVistaPickupActor* StorageItem = bStorageMutation
        ? Cast<AVistaPickupActor>(Target) : nullptr;
    AVistaContainerActor* StorageContainer = bStorageMutation
        ? Cast<AVistaContainerActor>(SecondaryTarget) : nullptr;
    if (bPourMutation &&
        (!IsValid(PourSource) || !IsValid(PourReceiver) ||
         Target == SecondaryTarget ||
         !SecondaryTarget->GetClass()->ImplementsInterface(
             UVistaInteractable::StaticClass())))
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            !IsValid(PourSource)
                ? FName(TEXT("POUR_SOURCE_REQUIRED"))
                : FName(TEXT("POUR_RECEIVER_REQUIRED")),
            OutRecord);
    }
    if (bStorageMutation &&
        (!IsValid(StorageItem) || !IsValid(StorageContainer) ||
         Target == SecondaryTarget ||
         !SecondaryTarget->GetClass()->ImplementsInterface(
             UVistaInteractable::StaticClass())))
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            !IsValid(StorageItem)
                ? FName(TEXT("STORAGE_ITEM_REQUIRED"))
                : FName(TEXT("STORAGE_CONTAINER_REQUIRED")),
            OutRecord);
    }
    if (!bTwoTargetMutation &&
        (InputRequest.SecondaryTarget != nullptr ||
         !InputRequest.SecondaryTargetSemanticId.IsEmpty()))
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("SECONDARY_TARGET_FORBIDDEN"),
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
        Target->GetWorld() != GetWorld() ||
        (bTwoTargetMutation &&
         SecondaryTarget->GetWorld() != GetWorld()))
    {
        return RejectSemanticRequest(
            InputRequest,
            CanonicalRequest,
            TEXT("ACTION_WORLD_MISMATCH"),
            OutRecord);
    }
    if (!Requester->HasAuthority() || !Target->HasAuthority() ||
        (bTwoTargetMutation && !SecondaryTarget->HasAuthority()))
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
    if (bPourMutation)
    {
        const TArray<EVistaAffordance> SecondaryAffordances =
            IVistaInteractable::Execute_VistaGetAffordances(SecondaryTarget);
        if (!SecondaryAffordances.Contains(EVistaAffordance::Pour))
        {
            return RejectSemanticRequest(
                InputRequest,
                CanonicalRequest,
                TEXT("POUR_RECEIVER_UNSUPPORTED"),
                OutRecord);
        }
    }
    else if (bStorageMutation)
    {
        const TArray<EVistaAffordance> SecondaryAffordances =
            IVistaInteractable::Execute_VistaGetAffordances(SecondaryTarget);
        if (!SecondaryAffordances.Contains(InputRequest.Affordance))
        {
            return RejectSemanticRequest(
                InputRequest,
                CanonicalRequest,
                TEXT("STORAGE_CONTAINER_UNSUPPORTED"),
                OutRecord);
        }
    }

    FVistaSemanticActionRequest Request = InputRequest;
    Request.RequesterSemanticId = SemanticIdForActor(Requester);
    Request.TargetSemanticId = SemanticIdForActor(Target);
    Request.SecondaryTargetSemanticId = bTwoTargetMutation
        ? SemanticIdForActor(SecondaryTarget) : FString();
    if (Request.RequesterSemanticId.IsEmpty() ||
        Request.TargetSemanticId.IsEmpty() ||
        (bTwoTargetMutation &&
         Request.SecondaryTargetSemanticId.IsEmpty()) ||
        (!InputRequest.RequesterSemanticId.IsEmpty() &&
         InputRequest.RequesterSemanticId != Request.RequesterSemanticId) ||
        (!InputRequest.TargetSemanticId.IsEmpty() &&
         InputRequest.TargetSemanticId != Request.TargetSemanticId) ||
        (!InputRequest.SecondaryTargetSemanticId.IsEmpty() &&
         InputRequest.SecondaryTargetSemanticId !=
             Request.SecondaryTargetSemanticId))
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
    AActor* AnimationTarget = bTwoTargetMutation
        ? SecondaryTarget : Target;
    bool bAnimationReady = false;
    if (IsValid(Animation) &&
        !UVistaAnimationComponent::SupportsAction(AnimationType))
    {
        // HasApprovedMutationAnimation intentionally validates source/provider
        // policy, not enum routing.  Require an explicit animation route as a
        // separate production gate so a newly appended action cannot reserve
        // or mutate merely because it falls through the provider policy.
        AnimationCode = TEXT("ANIMATION_ACTION_UNSUPPORTED");
    }
    else if (IsValid(Animation))
    {
        bAnimationReady = Animation->HasApprovedMutationAnimation(
            AnimationType, AnimationTarget, AnimationCode);
    }
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
    Active.SecondaryTarget = SecondaryTarget;
    Active.PourSource = PourSource;
    Active.PourReceiver = PourReceiver;
    Active.StorageItem = StorageItem;
    Active.StorageContainer = StorageContainer;
    Active.Animation = Animation;
    Active.Posture = Posture;
    Active.StartedAtSeconds = GetWorld()->GetTimeSeconds();
    Active.Record.CommandId = Request.CommandId;
    Active.Record.Affordance = Request.Affordance;
    Active.Record.RequesterSemanticId = Request.RequesterSemanticId;
    Active.Record.TargetSemanticId = Request.TargetSemanticId;
    Active.Record.SecondaryTargetSemanticId =
        Request.SecondaryTargetSemanticId;
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
    if (bPourMutation)
    {
        Active.Record.BeforeSecondaryState =
            IVistaInteractable::Execute_VistaGetRuntimeState(SecondaryTarget);
        Active.Record.bHasBeforeSecondaryState = true;
        FName PourCode;
        if (Active.Record.BeforeSecondaryState.SemanticId !=
                Request.SecondaryTargetSemanticId ||
            Active.Record.BeforeSecondaryState.Transform.ContainsNaN() ||
            !PourSource->CapturePourTransactionState(
                Requester,
                Active.PourSourceBefore,
                Active.Record.BeforePhysicalState,
                PourCode))
        {
            return RejectSemanticRequest(
                InputRequest,
                CanonicalRequest,
                PourCode.IsNone()
                    ? FName(TEXT("POUR_BEFORE_STATE_INVALID")) : PourCode,
                OutRecord);
        }
        Active.PourReceiverBefore = PourReceiver->GetLiquidState();
        Active.bHasPourSnapshots = true;
        Active.Record.bHasBeforePhysicalState = true;
        if (!PourReceiver->TryReservePourTransaction(
                this,
                Request.CommandId,
                Requester,
                PourSource,
                PourCode))
        {
            return RejectSemanticRequest(
                InputRequest,
                CanonicalRequest,
                PourCode.IsNone()
                    ? FName(TEXT("POUR_TARGETS_BUSY")) : PourCode,
                OutRecord);
        }
        Active.bTargetReserved = true;
        Active.bSecondaryTargetReserved = true;
        Active.Record.bTargetReservationAcquired = true;
        Active.Record.bSecondaryTargetReservationAcquired = true;
    }
    else if (bStorageMutation)
    {
        Active.Record.BeforeSecondaryState =
            IVistaInteractable::Execute_VistaGetRuntimeState(
                SecondaryTarget);
        Active.Record.bHasBeforeSecondaryState = true;
        Active.StorageBeforeAttachmentParent =
            StorageItem->GetRootComponent()
                ? StorageItem->GetRootComponent()->GetAttachParent()
                : nullptr;
        Active.StorageBeforeCarrier = StorageItem->GetCarrier();
        Active.StorageBeforeRequesterInventoryItem =
            Requester->GetClass()->ImplementsInterface(
                UVistaItemCarrier::StaticClass())
                ? IVistaItemCarrier::Execute_VistaGetHeldItem(Requester)
                : nullptr;
        Active.Record.bHasBeforePhysicalState =
            CapturePickupPhysicalState(
                StorageItem,
                Requester,
                Active.Record.BeforePhysicalState);
        FName StorageCode;
        if (Active.Record.BeforeSecondaryState.SemanticId !=
                Request.SecondaryTargetSemanticId ||
            Active.Record.BeforeSecondaryState.Transform.ContainsNaN() ||
            !Active.Record.bHasBeforePhysicalState ||
            !StorageItem->CaptureStorageTransactionState(
                Requester,
                StorageContainer,
                Request.Affordance,
                Active.Record.BeforePhysicalState,
                StorageCode))
        {
            return RejectSemanticRequest(
                InputRequest,
                CanonicalRequest,
                StorageCode.IsNone()
                    ? FName(TEXT("STORAGE_BEFORE_STATE_INVALID"))
                    : StorageCode,
                OutRecord);
        }
        if (!StorageContainer->TryReserveStorageTransaction(
                this,
                Request.CommandId,
                Requester,
                StorageItem,
                Request.Affordance,
                StorageCode))
        {
            return RejectSemanticRequest(
                InputRequest,
                CanonicalRequest,
                StorageCode.IsNone()
                    ? FName(TEXT("STORAGE_TARGETS_BUSY"))
                    : StorageCode,
                OutRecord);
        }
        Active.bHasStorageSnapshots = true;
        Active.bTargetReserved = true;
        Active.bSecondaryTargetReserved = true;
        Active.Record.bTargetReservationAcquired = true;
        Active.Record.bSecondaryTargetReservationAcquired = true;
    }
    else if (bApplianceMutation)
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
            OutRecord.bTargetReservationReleased &&
            ((OutRecord.Affordance != EVistaAffordance::Pour &&
              OutRecord.Affordance != EVistaAffordance::Insert &&
              OutRecord.Affordance != EVistaAffordance::Remove) ||
             OutRecord.bSecondaryTargetReservationReleased)
        : OutRecord.Status == EVistaActionTransactionStatus::Succeeded &&
            OutRecord.bTargetReservationReleased &&
            ((OutRecord.Affordance != EVistaAffordance::Pour &&
              OutRecord.Affordance != EVistaAffordance::Insert &&
              OutRecord.Affordance != EVistaAffordance::Remove) ||
             OutRecord.bSecondaryTargetReservationReleased);
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
    const EVistaAffordance Affordance =
        ActiveSemanticAction->Request.Affordance;
    const bool bTwoTarget = Affordance == EVistaAffordance::Pour ||
        Affordance == EVistaAffordance::Insert ||
        Affordance == EVistaAffordance::Remove;
    AActor* InteractionTarget = bTwoTarget
        ? ActiveSemanticAction->SecondaryTarget.Get()
        : ActiveSemanticAction->Target.Get();
    if (!IsValid(Requester) || !IsValid(InteractionTarget))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_PARTICIPANT_LOST"));
        return;
    }
    FVector ContactLocation;
    if (!ResolveContactLocation(
            InteractionTarget,
            ActiveSemanticAction->Request.Affordance,
            ContactLocation))
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
    const EVistaAffordance Affordance =
        ActiveSemanticAction->Request.Affordance;
    const bool bTwoTarget = Affordance == EVistaAffordance::Pour ||
        Affordance == EVistaAffordance::Insert ||
        Affordance == EVistaAffordance::Remove;
    AActor* InteractionTarget = bTwoTarget
        ? ActiveSemanticAction->SecondaryTarget.Get() : Target;
    if (!IsValid(Requester) || !IsValid(Target) ||
        !IsValid(InteractionTarget))
    {
        FinishSemanticFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_ALIGNMENT_TARGET_LOST"));
        return;
    }
    FVector ContactLocation;
    if (!ResolveContactLocation(
            InteractionTarget,
            ActiveSemanticAction->Request.Affordance,
            ContactLocation))
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
        if (ActiveSemanticAction->Request.Affordance ==
            EVistaAffordance::Pour)
        {
            AVistaPickupActor* Source =
                ActiveSemanticAction->PourSource.Get();
            FVistaLiquidStateSnapshot AlignedLiquid;
            FVistaPickupPhysicalStateSnapshot AlignedPhysical;
            FName PourCode;
            if (!IsValid(Source) ||
                !Source->CapturePourTransactionState(
                    Requester,
                    AlignedLiquid,
                    AlignedPhysical,
                    PourCode) ||
                !LiquidStatesEquivalent(
                    AlignedLiquid,
                    ActiveSemanticAction->PourSourceBefore) ||
                !HeldPhysicalStateStableAcrossAlignment(
                    ActiveSemanticAction->Record.BeforePhysicalState,
                    AlignedPhysical))
            {
                FinishSemanticFailure(
                    EVistaActionTransactionStatus::Failed,
                    PourCode.IsNone()
                        ? FName(TEXT("POUR_ALIGNMENT_SOURCE_DRIFT"))
                        : PourCode);
                return;
            }
            ActiveSemanticAction->PourSourceAlignedPhysical =
                AlignedPhysical;
            ActiveSemanticAction->bHasPourAlignedPhysical = true;
        }
        else if (Affordance == EVistaAffordance::Insert ||
                 Affordance == EVistaAffordance::Remove)
        {
            AVistaPickupActor* Item =
                ActiveSemanticAction->StorageItem.Get();
            AVistaContainerActor* Container =
                ActiveSemanticAction->StorageContainer.Get();
            FVistaPickupPhysicalStateSnapshot AlignedPhysical;
            FName StorageCode;
            const FVistaEntityRuntimeState ContainerState =
                IsValid(Container)
                    ? IVistaInteractable::Execute_VistaGetRuntimeState(
                          Container)
                    : FVistaEntityRuntimeState();
            if (!IsValid(Item) || !IsValid(Container) ||
                !Item->CaptureStorageTransactionState(
                    Requester,
                    Container,
                    Affordance,
                    AlignedPhysical,
                    StorageCode) ||
                !HeldPhysicalStateStableAcrossAlignment(
                    ActiveSemanticAction->Record.BeforePhysicalState,
                    AlignedPhysical) ||
                !RuntimeStatesEquivalent(
                    ActiveSemanticAction->Record.BeforeSecondaryState,
                    ContainerState))
            {
                FinishSemanticFailure(
                    EVistaActionTransactionStatus::Failed,
                    StorageCode.IsNone()
                        ? FName(TEXT("STORAGE_ALIGNMENT_STATE_DRIFT"))
                        : StorageCode);
                return;
            }
            ActiveSemanticAction->StorageAlignedPhysical =
                AlignedPhysical;
            ActiveSemanticAction->bHasStorageAlignedPhysical = true;
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
    const EVistaAffordance Affordance =
        ActiveSemanticAction->Request.Affordance;
    const bool bTwoTarget = Affordance == EVistaAffordance::Pour ||
        Affordance == EVistaAffordance::Insert ||
        Affordance == EVistaAffordance::Remove;
    AActor* AnimationTarget = bTwoTarget
        ? ActiveSemanticAction->SecondaryTarget.Get()
        : ActiveSemanticAction->Target.Get();
    if (!IsValid(Animation) || !IsValid(AnimationTarget))
    {
        OutCode = TEXT("ANIMATION_COMPONENT_OR_TARGET_UNAVAILABLE");
        return false;
    }
    FVistaNpcAction Action;
    Action.ActionId = ActiveSemanticAction->Record.CommandId;
    Action.Type = AnimationTypeFor(ActiveSemanticAction->Request.Affordance);
    Action.TargetSemanticId = ActiveSemanticAction->Record.TargetSemanticId;
    Action.SecondaryTargetSemanticId =
        ActiveSemanticAction->Record.SecondaryTargetSemanticId;
    Action.Hand = EVistaAnimationHand::Right;
    Action.TimeoutSeconds = ActiveSemanticAction->Request.TimeoutSeconds;
    return Animation->StartNpcAction(Action, AnimationTarget, OutCode);
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
    const bool bPourMutation =
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Pour;
    const bool bStorageMutation =
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Insert ||
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Remove;
    AActor* InteractionTarget = bPourMutation || bStorageMutation
        ? ActiveSemanticAction->SecondaryTarget.Get() : Target;
    FVector ContactLocation;
    if (!IsValid(Requester) || !IsValid(Target) ||
        !IsValid(InteractionTarget) ||
        !ResolveContactLocation(
            InteractionTarget,
            ActiveSemanticAction->Request.Affordance,
            ContactLocation) ||
        FVector::Dist(Requester->GetActorLocation(), ContactLocation) >
            MaximumSemanticContactDistanceCm)
    {
        OutCode = TEXT("ACTION_CONTACT_OUT_OF_RANGE");
        return false;
    }
    FVistaInteractionRequest Interaction;
    Interaction.Requester = Requester;
    Interaction.SecondaryTarget = ActiveSemanticAction->SecondaryTarget.Get();
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
    if (bPourMutation)
    {
        AVistaPickupActor* Source = ActiveSemanticAction->PourSource.Get();
        AVistaLiquidReceiverActor* Receiver =
            ActiveSemanticAction->PourReceiver.Get();
        if (!IsValid(Source) || !IsValid(Receiver) ||
            !ActiveSemanticAction->bHasPourSnapshots ||
            !ActiveSemanticAction->bHasPourAlignedPhysical ||
            !Source->PourStateMatches(
                ActiveSemanticAction->PourSourceBefore,
                ActiveSemanticAction->PourSourceAlignedPhysical) ||
            !LiquidStatesEquivalent(
                Receiver->GetLiquidState(),
                ActiveSemanticAction->PourReceiverBefore))
        {
            OutCode = TEXT("POUR_CONTACT_STATE_DRIFT");
            return false;
        }
        const FVistaPourTransactionResult PourResult =
            Receiver->CommitPourTransaction(
                this,
                ActiveSemanticAction->Record.CommandId,
                Requester,
                Source);
        if (!PourResult.bSucceeded)
        {
            OutCode = PourResult.Code.IsNone()
                ? FName(TEXT("POUR_CONTACT_FAILED")) : PourResult.Code;
            return false;
        }

        const FVistaEntityRuntimeState SourceContact =
            IVistaInteractable::Execute_VistaGetRuntimeState(Source);
        const FVistaEntityRuntimeState ReceiverContact =
            IVistaInteractable::Execute_VistaGetRuntimeState(Receiver);
        const bool bEvidenceValid =
            PourResult.SourceSemanticId ==
                ActiveSemanticAction->Record.TargetSemanticId &&
            PourResult.ReceiverSemanticId ==
                ActiveSemanticAction->Record.SecondaryTargetSemanticId &&
            PourResult.bSourceMutationCommitted &&
            PourResult.bReceiverMutationCommitted &&
            FMath::IsFinite(PourResult.TransferMilliliters) &&
            PourResult.TransferMilliliters > 0.0f &&
            LiquidStatesEquivalent(
                PourResult.SourceBefore,
                ActiveSemanticAction->PourSourceBefore) &&
            LiquidStatesEquivalent(
                PourResult.ReceiverBefore,
                ActiveSemanticAction->PourReceiverBefore) &&
            PhysicalSnapshotsEquivalent(
                PourResult.SourcePhysicalBefore,
                ActiveSemanticAction->PourSourceAlignedPhysical) &&
            PhysicalSnapshotsEquivalent(
                PourResult.SourcePhysicalAfter,
                ActiveSemanticAction->PourSourceAlignedPhysical) &&
            Receiver->StateMatchesTransition(
                ActiveSemanticAction->PourSourceBefore,
                ActiveSemanticAction->PourReceiverBefore,
                PourResult.SourceAfter,
                PourResult.ReceiverAfter) &&
            Source->PourStateMatches(
                PourResult.SourceAfter,
                ActiveSemanticAction->PourSourceAlignedPhysical) &&
            LiquidStatesEquivalent(
                Receiver->GetLiquidState(),
                PourResult.ReceiverAfter) &&
            SourceContact.SemanticId ==
                ActiveSemanticAction->Record.TargetSemanticId &&
            ReceiverContact.SemanticId ==
                ActiveSemanticAction->Record.SecondaryTargetSemanticId &&
            !RuntimeStatesEquivalent(
                ActiveSemanticAction->Record.BeforeState,
                SourceContact) &&
            !RuntimeStatesEquivalent(
                ActiveSemanticAction->Record.BeforeSecondaryState,
                ReceiverContact);
        if (!bEvidenceValid)
        {
            OutCode = TEXT("POUR_CONTACT_EVIDENCE_INVALID");
            return false;
        }
        ActiveSemanticAction->Record.ContactState = SourceContact;
        ActiveSemanticAction->Record.ContactSecondaryState = ReceiverContact;
        ActiveSemanticAction->Record.ContactPhysicalState =
            PourResult.SourcePhysicalAfter;
        ActiveSemanticAction->Record.bHasContactState = true;
        ActiveSemanticAction->Record.bHasContactSecondaryState = true;
        ActiveSemanticAction->Record.bHasContactPhysicalState = true;
        ActiveSemanticAction->Record.StateMutationCount = 2;
        ActiveSemanticAction->Record.PhysicalMutationCount = 0;
        ActiveSemanticAction->Record.LiquidTransferMilliliters =
            PourResult.TransferMilliliters;
        ActiveSemanticAction->Record.bContactCommitted = true;
        ActiveSemanticAction->Record.RequesterContactTransform =
            Requester->GetActorTransform();
        ActiveSemanticAction->ContactResultCode = PourResult.Code;
        if (!PublishSemanticRecord(false))
        {
            OutCode = TEXT("ACTION_LEDGER_PUBLISH_FAILED");
            return false;
        }
        OutCode = PourResult.Code;
        return true;
    }
    if (bStorageMutation)
    {
        AVistaPickupActor* Item =
            ActiveSemanticAction->StorageItem.Get();
        AVistaContainerActor* Container =
            ActiveSemanticAction->StorageContainer.Get();
        if (!IsValid(Item) || !IsValid(Container) ||
            !ActiveSemanticAction->bHasStorageSnapshots ||
            !ActiveSemanticAction->bHasStorageAlignedPhysical)
        {
            OutCode = TEXT("STORAGE_CONTACT_STATE_INVALID");
            return false;
        }
        FVistaPickupPhysicalStateSnapshot ContactBefore;
        FName StorageCode;
        if (!Item->CaptureStorageTransactionState(
                Requester,
                Container,
                ActiveSemanticAction->Request.Affordance,
                ContactBefore,
                StorageCode) ||
            !PhysicalSnapshotsEquivalent(
                ContactBefore,
                ActiveSemanticAction->StorageAlignedPhysical) ||
            !RuntimeStatesEquivalent(
                ActiveSemanticAction->Record.BeforeSecondaryState,
                IVistaInteractable::Execute_VistaGetRuntimeState(
                    Container)))
        {
            OutCode = StorageCode.IsNone()
                ? FName(TEXT("STORAGE_CONTACT_STATE_DRIFT"))
                : StorageCode;
            return false;
        }
        const FVistaContainerTransferResult Transfer =
            Container->CommitStorageTransaction(
                this,
                ActiveSemanticAction->Record.CommandId,
                Requester,
                Item,
                ActiveSemanticAction->Request.Affordance);
        const FVistaEntityRuntimeState ItemContact =
            IVistaInteractable::Execute_VistaGetRuntimeState(Item);
        const FVistaEntityRuntimeState ContainerContact =
            IVistaInteractable::Execute_VistaGetRuntimeState(Container);
        FVistaPickupPhysicalStateSnapshot ItemContactPhysical;
        const bool bPhysicalCaptured = CapturePickupPhysicalState(
            Item,
            Requester,
            ItemContactPhysical);
        const FString* ContainerOpen =
            ContainerContact.Values.Find(TEXT("open"));
        const FString* ContainedItem =
            ContainerContact.Values.Find(TEXT("contained_item"));
        const bool bExpectedContainerEffect =
            ContainerOpen != nullptr &&
            ContainerOpen->Equals(
                TEXT("true"), ESearchCase::CaseSensitive) &&
            ContainedItem != nullptr &&
            (ActiveSemanticAction->Request.Affordance ==
                     EVistaAffordance::Insert
                 ? *ContainedItem == Item->SemanticId
                 : ContainedItem->IsEmpty());
        const bool bEvidenceValid = Transfer.bSucceeded &&
            Transfer.ItemSemanticId ==
                ActiveSemanticAction->Record.TargetSemanticId &&
            Transfer.ContainerSemanticId ==
                ActiveSemanticAction->Record.SecondaryTargetSemanticId &&
            Transfer.bItemMutationCommitted &&
            Transfer.bContainerMutationCommitted && bPhysicalCaptured &&
            RuntimeStateValuesEquivalent(
                Transfer.ItemBefore,
                ActiveSemanticAction->Record.BeforeState) &&
            RuntimeStatesEquivalent(
                Transfer.ContainerBefore,
                ActiveSemanticAction->Record.BeforeSecondaryState) &&
            RuntimeStatesEquivalent(Transfer.ItemAfter, ItemContact) &&
            RuntimeStatesEquivalent(
                Transfer.ContainerAfter,
                ContainerContact) &&
            PhysicalSnapshotsEquivalent(
                Transfer.ItemPhysicalBefore,
                ActiveSemanticAction->StorageAlignedPhysical) &&
            PhysicalSnapshotsEquivalent(
                Transfer.ItemPhysicalAfter,
                ItemContactPhysical) &&
            StateMatchesSemanticEffect(
                ActiveSemanticAction->Record.BeforeState,
                ItemContact,
                ActiveSemanticAction->Request.Affordance,
                Item,
                Requester,
                ActiveSemanticAction->Request.RequesterSemanticId) &&
            bExpectedContainerEffect;
        if (!bEvidenceValid)
        {
            OutCode = Transfer.Code.IsNone()
                ? FName(TEXT("STORAGE_CONTACT_EVIDENCE_INVALID"))
                : Transfer.Code;
            return false;
        }
        ActiveSemanticAction->Record.ContactState = ItemContact;
        ActiveSemanticAction->Record.ContactSecondaryState =
            ContainerContact;
        ActiveSemanticAction->Record.ContactPhysicalState =
            ItemContactPhysical;
        ActiveSemanticAction->Record.bHasContactState = true;
        ActiveSemanticAction->Record.bHasContactSecondaryState = true;
        ActiveSemanticAction->Record.bHasContactPhysicalState = true;
        ActiveSemanticAction->Record.StateMutationCount = 2;
        ActiveSemanticAction->Record.PhysicalMutationCount = 1;
        ActiveSemanticAction->Record.bContactCommitted = true;
        ActiveSemanticAction->Record.RequesterContactTransform =
            Requester->GetActorTransform();
        ActiveSemanticAction->ContactResultCode = Transfer.Code;
        if (!PublishSemanticRecord(false))
        {
            OutCode = TEXT("ACTION_LEDGER_PUBLISH_FAILED");
            return false;
        }
        OutCode = Transfer.Code;
        return true;
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
    const bool bPourMutation =
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Pour;
    const bool bStorageMutation =
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Insert ||
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Remove;
    AVistaPickupActor* PourSource = ActiveSemanticAction->PourSource.Get();
    AVistaLiquidReceiverActor* PourReceiver =
        ActiveSemanticAction->PourReceiver.Get();
    if (!IsValid(Target) ||
        (bPourMutation &&
         (!IsValid(PourSource) || !IsValid(PourReceiver))) ||
        (bStorageMutation &&
         (!ActiveSemanticAction->StorageItem.IsValid() ||
          !ActiveSemanticAction->StorageContainer.IsValid())) ||
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
    bool bAfterStateValid = false;
    if (bPourMutation)
    {
        ActiveSemanticAction->Record.AfterSecondaryState =
            IVistaInteractable::Execute_VistaGetRuntimeState(PourReceiver);
        ActiveSemanticAction->Record.bHasAfterSecondaryState = true;
        ActiveSemanticAction->Record.bHasAfterPhysicalState =
            CapturePickupPhysicalState(
                PourSource,
                ActiveSemanticAction->Requester.Get(),
                ActiveSemanticAction->Record.AfterPhysicalState);
        const FVistaLiquidStateSnapshot SourceAfter =
            PourSource->GetLiquidState();
        const FVistaLiquidStateSnapshot ReceiverAfter =
            PourReceiver->GetLiquidState();
        bAfterStateValid =
            ActiveSemanticAction->bHasPourSnapshots &&
            ActiveSemanticAction->bHasPourAlignedPhysical &&
            ActiveSemanticAction->Record.StateMutationCount == 2 &&
            ActiveSemanticAction->Record.PhysicalMutationCount == 0 &&
            ActiveSemanticAction->Record.LiquidTransferMilliliters > 0.0f &&
            ActiveSemanticAction->Record.bHasAfterPhysicalState &&
            RuntimeStatesEquivalent(
                ActiveSemanticAction->Record.ContactState,
                ActiveSemanticAction->Record.AfterState) &&
            RuntimeStatesEquivalent(
                ActiveSemanticAction->Record.ContactSecondaryState,
                ActiveSemanticAction->Record.AfterSecondaryState) &&
            PhysicalSnapshotsEquivalent(
                ActiveSemanticAction->PourSourceAlignedPhysical,
                ActiveSemanticAction->Record.AfterPhysicalState) &&
            PourSource->PourStateMatches(
                SourceAfter,
                ActiveSemanticAction->PourSourceAlignedPhysical) &&
            PourReceiver->StateMatchesTransition(
                ActiveSemanticAction->PourSourceBefore,
                ActiveSemanticAction->PourReceiverBefore,
                SourceAfter,
                ReceiverAfter);
    }
    else if (bStorageMutation)
    {
        AVistaPickupActor* Item =
            ActiveSemanticAction->StorageItem.Get();
        AVistaContainerActor* Container =
            ActiveSemanticAction->StorageContainer.Get();
        ActiveSemanticAction->Record.AfterSecondaryState =
            IVistaInteractable::Execute_VistaGetRuntimeState(Container);
        ActiveSemanticAction->Record.bHasAfterSecondaryState = true;
        ActiveSemanticAction->Record.bHasAfterPhysicalState =
            CapturePickupPhysicalState(
                Item,
                ActiveSemanticAction->Requester.Get(),
                ActiveSemanticAction->Record.AfterPhysicalState);
        bAfterStateValid =
            ActiveSemanticAction->bHasStorageSnapshots &&
            ActiveSemanticAction->bHasStorageAlignedPhysical &&
            ActiveSemanticAction->Record.StateMutationCount == 2 &&
            ActiveSemanticAction->Record.PhysicalMutationCount == 1 &&
            ActiveSemanticAction->Record.bHasAfterPhysicalState &&
            RuntimeStatesEquivalent(
                ActiveSemanticAction->Record.ContactState,
                ActiveSemanticAction->Record.AfterState) &&
            RuntimeStatesEquivalent(
                ActiveSemanticAction->Record.ContactSecondaryState,
                ActiveSemanticAction->Record.AfterSecondaryState) &&
            PhysicalSnapshotsEquivalent(
                ActiveSemanticAction->Record.ContactPhysicalState,
                ActiveSemanticAction->Record.AfterPhysicalState) &&
            StateMatchesSemanticEffect(
                ActiveSemanticAction->Record.BeforeState,
                ActiveSemanticAction->Record.AfterState,
                ActiveSemanticAction->Request.Affordance,
                Item,
                ActiveSemanticAction->Requester.Get(),
                ActiveSemanticAction->Request.RequesterSemanticId) &&
            (ActiveSemanticAction->Request.Affordance ==
                     EVistaAffordance::Insert
                 ? Item->IsContainedIn(Container) &&
                    Container->GetContainedItemSemanticId() ==
                        Item->SemanticId
                 : Item->GetCarrier() ==
                       ActiveSemanticAction->Requester.Get() &&
                    Container->GetContainedItemSemanticId().IsEmpty());
    }
    else
    {
        bAfterStateValid = StateMatchesSemanticEffect(
                ActiveSemanticAction->Record.BeforeState,
                ActiveSemanticAction->Record.AfterState,
                ActiveSemanticAction->Request.Affordance,
                Target,
                ActiveSemanticAction->Requester.Get(),
                ActiveSemanticAction->Request.RequesterSemanticId) &&
            RuntimeStatesEquivalent(
                ActiveSemanticAction->Record.ContactState,
                ActiveSemanticAction->Record.AfterState);
    }
    if (!bAfterStateValid)
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
            (FinalRecord.Affordance == EVistaAffordance::Pour ||
             FinalRecord.Affordance == EVistaAffordance::Insert ||
             FinalRecord.Affordance == EVistaAffordance::Remove)
                ? FinalRecord.SecondaryTargetSemanticId
                : FinalRecord.TargetSemanticId,
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
    const bool bPourMutation =
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Pour;
    const bool bStorageMutation =
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Insert ||
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Remove;
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
    if (ActiveSemanticAction->Record.bContactMutationAttempted && bPourMutation)
    {
        AVistaPickupActor* Source = ActiveSemanticAction->PourSource.Get();
        AVistaLiquidReceiverActor* Receiver =
            ActiveSemanticAction->PourReceiver.Get();
        const FVistaInteractionResult ReceiverRestore =
            IsValid(Receiver) && ActiveSemanticAction->bHasPourSnapshots
            ? Receiver->RestoreTransactionalState(
                this,
                ActiveSemanticAction->Record.CommandId,
                ActiveSemanticAction->PourReceiverBefore)
            : FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("POUR_ROLLBACK_RECEIVER_LOST"));
        const FVistaInteractionResult SourceRestore =
            IsValid(Source) && ActiveSemanticAction->bHasPourSnapshots
            ? Source->RestorePourLiquidState(
                this,
                ActiveSemanticAction->Record.CommandId,
                ActiveSemanticAction->PourSourceBefore)
            : FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("POUR_ROLLBACK_SOURCE_LOST"));
        const FVistaEntityRuntimeState SourceRestoredState = IsValid(Source)
            ? IVistaInteractable::Execute_VistaGetRuntimeState(Source)
            : FVistaEntityRuntimeState();
        const FVistaEntityRuntimeState ReceiverRestoredState = IsValid(Receiver)
            ? IVistaInteractable::Execute_VistaGetRuntimeState(Receiver)
            : FVistaEntityRuntimeState();
        FVistaPickupPhysicalStateSnapshot RestoredPhysical;
        const bool bPhysicalCaptured = CapturePickupPhysicalState(
            Source,
            ActiveSemanticAction->Requester.Get(),
            RestoredPhysical);
        const bool bPourRestored =
            ReceiverRestore.IsSuccess() && SourceRestore.IsSuccess() &&
            bPhysicalCaptured &&
            Source->PourStateMatches(
                ActiveSemanticAction->PourSourceBefore,
                ActiveSemanticAction->Record.BeforePhysicalState) &&
            LiquidStatesEquivalent(
                Receiver->GetLiquidState(),
                ActiveSemanticAction->PourReceiverBefore) &&
            PhysicalSnapshotsEquivalent(
                RestoredPhysical,
                ActiveSemanticAction->Record.BeforePhysicalState) &&
            RuntimeStatesEquivalent(
                SourceRestoredState,
                ActiveSemanticAction->Record.BeforeState) &&
            RuntimeStatesEquivalent(
                ReceiverRestoredState,
                ActiveSemanticAction->Record.BeforeSecondaryState);
        ActiveSemanticAction->Record.AfterState = SourceRestoredState;
        ActiveSemanticAction->Record.AfterSecondaryState =
            ReceiverRestoredState;
        ActiveSemanticAction->Record.AfterPhysicalState = RestoredPhysical;
        ActiveSemanticAction->Record.bHasAfterState = IsValid(Source);
        ActiveSemanticAction->Record.bHasAfterSecondaryState =
            IsValid(Receiver);
        ActiveSemanticAction->Record.bHasAfterPhysicalState = bPhysicalCaptured;
        ActiveSemanticAction->Record.RollbackCode = bPourRestored
            ? FName(TEXT("POUR_STATES_RESTORED"))
            : FName(TEXT("POUR_STATE_RESTORE_FAILED"));
        bRollbackSucceeded = bRollbackSucceeded && bPourRestored;
    }
    if (ActiveSemanticAction->Record.bContactMutationAttempted &&
        bStorageMutation)
    {
        FName StorageRollbackCode;
        const bool bStorageRestored =
            RestoreAndVerifyStorageBeforeState(StorageRollbackCode);
        ActiveSemanticAction->Record.RollbackCode =
            StorageRollbackCode.IsNone()
                ? FName(TEXT("STORAGE_STATE_RESTORE_FAILED"))
                : StorageRollbackCode;
        bRollbackSucceeded = bRollbackSucceeded && bStorageRestored;
    }
    if (ActiveSemanticAction->Record.bContactMutationAttempted &&
        !bPostureMutation && !bPourMutation && !bStorageMutation)
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

bool UVistaActionExecutorComponent::RestoreAndVerifyStorageBeforeState(
    FName& OutCode)
{
    if (!ActiveSemanticAction.IsSet() ||
        !ActiveSemanticAction->bHasStorageSnapshots ||
        !ActiveSemanticAction->Record.bHasBeforeState ||
        !ActiveSemanticAction->Record.bHasBeforeSecondaryState ||
        !ActiveSemanticAction->Record.bHasBeforePhysicalState)
    {
        OutCode = TEXT("STORAGE_ROLLBACK_SNAPSHOT_MISSING");
        return false;
    }
    AVistaPickupActor* Item = ActiveSemanticAction->StorageItem.Get();
    AVistaContainerActor* Container =
        ActiveSemanticAction->StorageContainer.Get();
    AActor* Requester = ActiveSemanticAction->Requester.Get();
    if (!IsValid(Item) || !IsValid(Container) || !IsValid(Requester))
    {
        OutCode = TEXT("STORAGE_ROLLBACK_PARTICIPANT_LOST");
        return false;
    }

    // R14 requires container contents to be restored before the item body and
    // carrier inventory so no released reservation can expose a false pairing.
    const FVistaInteractionResult ContainerRestore =
        Container->RestoreTransactionalState(
            this,
            ActiveSemanticAction->Record.CommandId,
            ActiveSemanticAction->Record.BeforeSecondaryState);
    if (!ContainerRestore.IsSuccess())
    {
        OutCode = ContainerRestore.Code.IsNone()
            ? FName(TEXT("STORAGE_CONTAINER_RESTORE_FAILED"))
            : ContainerRestore.Code;
        return false;
    }

    const FVistaTrustedPhysicalRestoreToken RestoreToken;
    const FVistaInteractionResult ItemRestore =
        Item->RestorePhysicalStateTrusted(
            ActiveSemanticAction->Record.BeforeState,
            &ActiveSemanticAction->Record.BeforePhysicalState,
            ActiveSemanticAction->StorageBeforeAttachmentParent.Get(),
            ActiveSemanticAction->StorageBeforeCarrier.Get(),
            RestoreToken);
    if (!ItemRestore.IsSuccess())
    {
        OutCode = ItemRestore.Code.IsNone()
            ? FName(TEXT("STORAGE_ITEM_RESTORE_FAILED"))
            : ItemRestore.Code;
        return false;
    }

    ActiveSemanticAction->Record.AfterState =
        IVistaInteractable::Execute_VistaGetRuntimeState(Item);
    ActiveSemanticAction->Record.AfterSecondaryState =
        IVistaInteractable::Execute_VistaGetRuntimeState(Container);
    ActiveSemanticAction->Record.bHasAfterState = true;
    ActiveSemanticAction->Record.bHasAfterSecondaryState = true;
    ActiveSemanticAction->Record.bHasAfterPhysicalState =
        CapturePickupPhysicalState(
            Item,
            Requester,
            ActiveSemanticAction->Record.AfterPhysicalState);

    const FVistaPickupPhysicalStateSnapshot& Before =
        ActiveSemanticAction->Record.BeforePhysicalState;
    const EVistaPickupDisposition ExpectedDisposition = Before.bHeld
        ? EVistaPickupDisposition::Held
        : !Before.ContainedInSemanticId.IsEmpty()
            ? EVistaPickupDisposition::Contained
            : !Before.PlacedAtSemanticId.IsEmpty()
                ? EVistaPickupDisposition::Placed
                : EVistaPickupDisposition::Free;
    USceneComponent* CurrentParent = Item->GetRootComponent()
        ? Item->GetRootComponent()->GetAttachParent() : nullptr;
    AActor* CurrentInventoryItem =
        Requester->GetClass()->ImplementsInterface(
            UVistaItemCarrier::StaticClass())
        ? IVistaItemCarrier::Execute_VistaGetHeldItem(Requester)
        : nullptr;
    const bool bExact =
        ActiveSemanticAction->Record.bHasAfterPhysicalState &&
        Item->GetPhysicalDisposition() == ExpectedDisposition &&
        CurrentParent ==
            ActiveSemanticAction->StorageBeforeAttachmentParent.Get() &&
        Item->GetCarrier() ==
            ActiveSemanticAction->StorageBeforeCarrier.Get() &&
        CurrentInventoryItem ==
            ActiveSemanticAction->StorageBeforeRequesterInventoryItem.Get() &&
        RuntimeStatesEquivalent(
            ActiveSemanticAction->Record.AfterState,
            ActiveSemanticAction->Record.BeforeState) &&
        RuntimeStatesEquivalent(
            ActiveSemanticAction->Record.AfterSecondaryState,
            ActiveSemanticAction->Record.BeforeSecondaryState) &&
        PhysicalSnapshotsEquivalent(
            ActiveSemanticAction->Record.AfterPhysicalState,
            ActiveSemanticAction->Record.BeforePhysicalState);
    OutCode = bExact
        ? FName(TEXT("STORAGE_STATES_RESTORED"))
        : FName(TEXT("STORAGE_STATE_RESTORE_FAILED"));
    return bExact;
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
        (!ActiveSemanticAction->bTargetReserved &&
         !ActiveSemanticAction->bSecondaryTargetReserved))
    {
        return true;
    }
    if (ActiveSemanticAction->Request.Affordance == EVistaAffordance::Pour)
    {
        AVistaPickupActor* Source = ActiveSemanticAction->PourSource.Get();
        AVistaLiquidReceiverActor* Receiver =
            ActiveSemanticAction->PourReceiver.Get();
        FName ReleaseCode;
        if (!IsValid(Source) || !IsValid(Receiver) ||
            !Receiver->ReleasePourTransaction(
                this,
                ActiveSemanticAction->Record.CommandId,
                Source,
                ReleaseCode))
        {
            return false;
        }
        ActiveSemanticAction->bTargetReserved = false;
        ActiveSemanticAction->bSecondaryTargetReserved = false;
        ActiveSemanticAction->Record.bTargetReservationReleased = true;
        ActiveSemanticAction->Record.bSecondaryTargetReservationReleased =
            true;
        return true;
    }
    if (ActiveSemanticAction->Request.Affordance == EVistaAffordance::Insert ||
        ActiveSemanticAction->Request.Affordance == EVistaAffordance::Remove)
    {
        AVistaPickupActor* Item =
            ActiveSemanticAction->StorageItem.Get();
        AVistaContainerActor* Container =
            ActiveSemanticAction->StorageContainer.Get();
        FName ReleaseCode;
        const bool bParticipantsAlreadyReleased =
            (!IsValid(Item) || Item->IsTransactionUnreserved()) &&
            (!IsValid(Container) || !Container->IsStorageReserved());
        if (!bParticipantsAlreadyReleased &&
            (!IsValid(Item) || !IsValid(Container) ||
             !Container->ReleaseStorageTransaction(
                 this,
                 ActiveSemanticAction->Record.CommandId,
                 Item,
                 ReleaseCode)))
        {
            return false;
        }
        ActiveSemanticAction->bTargetReserved = false;
        ActiveSemanticAction->bSecondaryTargetReserved = false;
        ActiveSemanticAction->Record.bTargetReservationReleased = true;
        ActiveSemanticAction->Record.bSecondaryTargetReservationReleased =
            true;
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
