#include "VistaLiquidReceiverActor.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "HAL/PlatformMemory.h"
#include "Net/UnrealNetwork.h"
#include "VistaActionExecutorComponent.h"
#include "VistaPickupActor.h"

namespace
{
const FName PourableKey(TEXT("pourable"));
const FName FilledKey(TEXT("filled"));
const FName LiquidTypeKey(TEXT("liquid_type"));
const FName LiquidCapacityKey(TEXT("liquid_capacity_ml"));
const FName LiquidAmountKey(TEXT("liquid_amount_ml"));
const FName LiquidLevelKey(TEXT("liquid_level"));
constexpr float LiquidToleranceMilliliters = 0.01f;

template <typename T>
bool ScalarBitsEqual(const T& Left, const T& Right)
{
    return FPlatformMemory::Memcmp(&Left, &Right, sizeof(T)) == 0;
}

bool VectorBitsEqual(const FVector& Left, const FVector& Right)
{
    return ScalarBitsEqual(Left.X, Right.X) &&
        ScalarBitsEqual(Left.Y, Right.Y) &&
        ScalarBitsEqual(Left.Z, Right.Z);
}

bool TransformBitsEqual(const FTransform& Left, const FTransform& Right)
{
    const FVector LeftTranslation = Left.GetTranslation();
    const FVector RightTranslation = Right.GetTranslation();
    const FVector LeftScale = Left.GetScale3D();
    const FVector RightScale = Right.GetScale3D();
    const FQuat LeftRotation = Left.GetRotation();
    const FQuat RightRotation = Right.GetRotation();
    return VectorBitsEqual(LeftTranslation, RightTranslation) &&
        VectorBitsEqual(LeftScale, RightScale) &&
        ScalarBitsEqual(LeftRotation.X, RightRotation.X) &&
        ScalarBitsEqual(LeftRotation.Y, RightRotation.Y) &&
        ScalarBitsEqual(LeftRotation.Z, RightRotation.Z) &&
        ScalarBitsEqual(LeftRotation.W, RightRotation.W);
}

bool PhysicalSnapshotsBitExact(
    const FVistaPickupPhysicalStateSnapshot& Left,
    const FVistaPickupPhysicalStateSnapshot& Right)
{
    return TransformBitsEqual(Left.WorldTransform, Right.WorldTransform) &&
        Left.bSimulatePhysics == Right.bSimulatePhysics &&
        Left.CollisionEnabled == Right.CollisionEnabled &&
        Left.CollisionProfileName == Right.CollisionProfileName &&
        VectorBitsEqual(Left.LinearVelocity, Right.LinearVelocity) &&
        VectorBitsEqual(
            Left.AngularVelocityDegrees, Right.AngularVelocityDegrees) &&
        Left.bHasAttachmentParent == Right.bHasAttachmentParent &&
        Left.AttachmentParentOwnerSemanticId ==
            Right.AttachmentParentOwnerSemanticId &&
        Left.AttachmentParentComponentName ==
            Right.AttachmentParentComponentName &&
        Left.AttachmentSocketName == Right.AttachmentSocketName &&
        TransformBitsEqual(
            Left.AttachmentRelativeTransform,
            Right.AttachmentRelativeTransform) &&
        Left.bHeld == Right.bHeld &&
        Left.CarrierSemanticId == Right.CarrierSemanticId &&
        Left.InventoryCarrierSemanticId ==
            Right.InventoryCarrierSemanticId &&
        Left.bInventorySlotOccupied == Right.bInventorySlotOccupied &&
        Left.InventoryItemSemanticId == Right.InventoryItemSemanticId &&
        Left.PlacedAtSemanticId == Right.PlacedAtSemanticId;
}

bool LiquidStatesBitExact(
    const FVistaLiquidStateSnapshot& Left,
    const FVistaLiquidStateSnapshot& Right)
{
    return Left.bPourable == Right.bPourable &&
        Left.LiquidType == Right.LiquidType &&
        ScalarBitsEqual(
            Left.CapacityMilliliters, Right.CapacityMilliliters) &&
        ScalarBitsEqual(Left.AmountMilliliters, Right.AmountMilliliters);
}

bool IsClosedName(const FName Value)
{
    const FString Text = Value.ToString();
    if (Text.IsEmpty() || Text.Len() > 64)
    {
        return false;
    }
    for (const TCHAR Character : Text)
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

bool ParseStrictBoolean(const FString& Value, bool& OutValue)
{
    if (Value == TEXT("true"))
    {
        OutValue = true;
        return true;
    }
    if (Value == TEXT("false"))
    {
        OutValue = false;
        return true;
    }
    return false;
}

bool ParseFiniteFloat(const FString& Value, float& OutValue)
{
    return LexTryParseString(OutValue, *Value) && FMath::IsFinite(OutValue);
}
} // namespace

AVistaLiquidReceiverActor::AVistaLiquidReceiverActor()
{
    Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ReceiverMesh"));
    SetRootComponent(Mesh);
    Mesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));

    PourTarget = CreateDefaultSubobject<USceneComponent>(TEXT("PourTarget"));
    PourTarget->SetupAttachment(Mesh);
    PourTarget->ComponentTags.Add(TEXT("VistaInteractionTarget"));

    AllowedAffordances = {
        EVistaAffordance::Inspect,
        EVistaAffordance::Pour};
    LiquidState.bPourable = false;
    LiquidState.LiquidType = InitialLiquidType;
    LiquidState.CapacityMilliliters = CapacityMilliliters;
    LiquidState.AmountMilliliters =
        CapacityMilliliters * InitialLiquidLevel;
}

void AVistaLiquidReceiverActor::BeginPlay()
{
    Super::BeginPlay();
    if (HasAuthority())
    {
        FVistaLiquidStateSnapshot Fallback;
        Fallback.bPourable = false;
        Fallback.LiquidType = InitialLiquidType;
        Fallback.CapacityMilliliters = CapacityMilliliters;
        Fallback.AmountMilliliters =
            CapacityMilliliters * InitialLiquidLevel;
        FVistaLiquidStateSnapshot InitialState;
        FName Code;
        const FVistaEntityRuntimeState Authored =
            Super::VistaGetRuntimeState_Implementation();
        if (!ReadLiquidState(Authored, Fallback, InitialState, Code) ||
            !ValidateReceiverState(InitialState, Code))
        {
            InitialState = Fallback;
            if (!ValidateReceiverState(InitialState, Code))
            {
                InitialState = FVistaLiquidStateSnapshot();
                InitialState.CapacityMilliliters = 250.0f;
            }
        }
        SetLiquidState(InitialState);
    }
    else
    {
        SyncRuntimeLiquidValues();
    }
}

void AVistaLiquidReceiverActor::EndPlay(
    const EEndPlayReason::Type EndPlayReason)
{
    if (HasAuthority())
    {
        UVistaActionExecutorComponent* Executor =
            ActiveTransactionExecutor.Get();
        const FName CommandId = ActiveTransactionCommandId;
        AVistaPickupActor* Source = ReservedSource.Get();
        if (Executor != nullptr && !CommandId.IsNone() &&
            Source != nullptr &&
            IsReceiverReservationOwnedBy(Executor, CommandId, Source))
        {
            Source->ReleasePourReservationForReceiverEndPlay(
                this, Executor, CommandId);
            ClearReceiverReservationIfOwned(
                Executor, CommandId, Source, false);
        }

        ActiveTransactionExecutor.Reset();
        ActiveTransactionCommandId = NAME_None;
        ReservedRequester.Reset();
        ReservedSource.Reset();
    }
    Super::EndPlay(EndPlayReason);
}

void AVistaLiquidReceiverActor::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaLiquidReceiverActor, LiquidState);
}

bool AVistaLiquidReceiverActor::ValidateReceiverState(
    const FVistaLiquidStateSnapshot& State,
    FName& OutCode)
{
    if (State.bPourable || !FMath::IsFinite(State.CapacityMilliliters) ||
        State.CapacityMilliliters < 1.0f ||
        State.CapacityMilliliters > 100000.0f ||
        !FMath::IsFinite(State.AmountMilliliters) ||
        State.AmountMilliliters < 0.0f ||
        State.AmountMilliliters > State.CapacityMilliliters)
    {
        OutCode = TEXT("LIQUID_RECEIVER_CAPACITY_OR_AMOUNT_INVALID");
        return false;
    }
    if (State.IsFilled() && !IsClosedName(State.LiquidType))
    {
        OutCode = TEXT("LIQUID_RECEIVER_TYPE_REQUIRED");
        return false;
    }
    if (!State.LiquidType.IsNone() && !IsClosedName(State.LiquidType))
    {
        OutCode = TEXT("LIQUID_RECEIVER_TYPE_INVALID");
        return false;
    }
    OutCode = TEXT("LIQUID_RECEIVER_STATE_VALID");
    return true;
}

bool AVistaLiquidReceiverActor::ReadLiquidState(
    const FVistaEntityRuntimeState& State,
    const FVistaLiquidStateSnapshot& Fallback,
    FVistaLiquidStateSnapshot& OutState,
    FName& OutCode) const
{
    OutState = Fallback;
    if (const FString* PourableValue = State.Values.Find(PourableKey))
    {
        if (!ParseStrictBoolean(*PourableValue, OutState.bPourable))
        {
            OutCode = TEXT("LIQUID_RECEIVER_POURABLE_INVALID");
            return false;
        }
    }
    if (const FString* TypeValue = State.Values.Find(LiquidTypeKey))
    {
        OutState.LiquidType = TypeValue->IsEmpty()
            ? NAME_None : FName(**TypeValue);
    }
    if (const FString* CapacityValue = State.Values.Find(LiquidCapacityKey))
    {
        if (!ParseFiniteFloat(
                *CapacityValue, OutState.CapacityMilliliters))
        {
            OutCode = TEXT("LIQUID_RECEIVER_CAPACITY_INVALID");
            return false;
        }
    }
    bool bAmountPresent = false;
    if (const FString* AmountValue = State.Values.Find(LiquidAmountKey))
    {
        bAmountPresent = true;
        if (!ParseFiniteFloat(*AmountValue, OutState.AmountMilliliters))
        {
            OutCode = TEXT("LIQUID_RECEIVER_AMOUNT_INVALID");
            return false;
        }
    }
    bool bLevelPresent = false;
    float Level = 0.0f;
    if (const FString* LevelValue = State.Values.Find(LiquidLevelKey))
    {
        bLevelPresent = true;
        if (!ParseFiniteFloat(*LevelValue, Level) ||
            Level < 0.0f || Level > 1.0f)
        {
            OutCode = TEXT("LIQUID_RECEIVER_LEVEL_INVALID");
            return false;
        }
        const float LevelAmount = OutState.CapacityMilliliters * Level;
        if (bAmountPresent &&
            !FMath::IsNearlyEqual(
                OutState.AmountMilliliters,
                LevelAmount,
                LiquidToleranceMilliliters))
        {
            OutCode = TEXT("LIQUID_RECEIVER_AMOUNT_LEVEL_MISMATCH");
            return false;
        }
        OutState.AmountMilliliters = LevelAmount;
    }
    if (const FString* FilledValue = State.Values.Find(FilledKey))
    {
        bool bFilled = false;
        if (!ParseStrictBoolean(*FilledValue, bFilled))
        {
            OutCode = TEXT("LIQUID_RECEIVER_FILLED_INVALID");
            return false;
        }
        if (!bAmountPresent && !bLevelPresent)
        {
            OutState.AmountMilliliters =
                bFilled ? OutState.CapacityMilliliters : 0.0f;
        }
        else if (bFilled != OutState.IsFilled())
        {
            OutCode = TEXT("LIQUID_RECEIVER_FILLED_LEVEL_MISMATCH");
            return false;
        }
    }
    return ValidateReceiverState(OutState, OutCode);
}

void AVistaLiquidReceiverActor::SyncRuntimeLiquidValues()
{
    RuntimeStateValues.Add(PourableKey, TEXT("false"));
    RuntimeStateValues.Add(
        FilledKey, LiquidState.IsFilled() ? TEXT("true") : TEXT("false"));
    RuntimeStateValues.Add(LiquidTypeKey, LiquidState.LiquidType.ToString());
    RuntimeStateValues.Add(
        LiquidCapacityKey,
        FString::SanitizeFloat(LiquidState.CapacityMilliliters));
    RuntimeStateValues.Add(
        LiquidAmountKey,
        FString::SanitizeFloat(LiquidState.AmountMilliliters));
    RuntimeStateValues.Add(
        LiquidLevelKey,
        FString::SanitizeFloat(LiquidState.GetLiquidLevel()));
}

void AVistaLiquidReceiverActor::SetLiquidState(
    const FVistaLiquidStateSnapshot& State)
{
    LiquidState = State;
    SyncRuntimeLiquidValues();
    if (HasAuthority())
    {
        ForceNetUpdate();
    }
}

void AVistaLiquidReceiverActor::OnRep_LiquidState()
{
    FName Code;
    if (!ValidateReceiverState(LiquidState, Code))
    {
        UE_LOG(
            LogTemp,
            Error,
            TEXT("VISTA_LIQUID_RECEIVER_STATE_REJECTED semantic_id=%s code=%s"),
            *SemanticId,
            *Code.ToString());
        return;
    }
    SyncRuntimeLiquidValues();
}

FVistaEntityRuntimeState
AVistaLiquidReceiverActor::VistaGetRuntimeState_Implementation() const
{
    FVistaEntityRuntimeState State =
        Super::VistaGetRuntimeState_Implementation();
    State.Values.Add(TEXT("receiver_kind"), ReceiverKind.ToString());
    State.Values.Add(
        TEXT("accepted_liquid_type"), AcceptedLiquidType.ToString());
    State.Values.Add(PourableKey, TEXT("false"));
    State.Values.Add(
        FilledKey, LiquidState.IsFilled() ? TEXT("true") : TEXT("false"));
    State.Values.Add(LiquidTypeKey, LiquidState.LiquidType.ToString());
    State.Values.Add(
        LiquidCapacityKey,
        FString::SanitizeFloat(LiquidState.CapacityMilliliters));
    State.Values.Add(
        LiquidAmountKey,
        FString::SanitizeFloat(LiquidState.AmountMilliliters));
    State.Values.Add(
        LiquidLevelKey,
        FString::SanitizeFloat(LiquidState.GetLiquidLevel()));
    return State;
}

FVistaInteractionResult
AVistaLiquidReceiverActor::VistaApplyRuntimeState_Implementation(
    const FVistaEntityRuntimeState& State)
{
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("AUTHORITY_REQUIRED"),
            SemanticId);
    }
    if (ActiveTransactionExecutor.IsValid() ||
        !ActiveTransactionCommandId.IsNone())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Busy,
            TEXT("LIQUID_RECEIVER_RESERVED"),
            SemanticId);
    }
    FVistaLiquidStateSnapshot NewState;
    FName Code;
    if (!ReadLiquidState(State, LiquidState, NewState, Code) ||
        !ScalarBitsEqual(
            NewState.CapacityMilliliters,
            LiquidState.CapacityMilliliters) ||
        NewState.bPourable)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            Code == TEXT("LIQUID_RECEIVER_STATE_VALID")
                ? FName(TEXT("LIQUID_RECEIVER_AUTHORITY_PATCH_REJECTED"))
                : Code,
            SemanticId);
    }
    if (NewState.IsFilled() && NewState.LiquidType != AcceptedLiquidType)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("LIQUID_RECEIVER_TYPE_MISMATCH"),
            SemanticId);
    }
    const FVistaInteractionResult BaseResult =
        Super::VistaApplyRuntimeState_Implementation(State);
    if (!BaseResult.IsSuccess())
    {
        return BaseResult;
    }
    SetLiquidState(NewState);
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("LIQUID_RECEIVER_STATE_APPLIED"));
}

FVistaInteractionResult AVistaLiquidReceiverActor::VistaInteract_Implementation(
    const FVistaInteractionRequest& Request)
{
    const FVistaInteractionResult Validation = ValidateRequest(Request);
    if (!Validation.IsSuccess())
    {
        return Validation;
    }
    if (Request.Affordance == EVistaAffordance::Pour)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("ACTION_EXECUTOR_REQUIRED"),
            SemanticId);
    }
    return Super::VistaInteract_Implementation(Request);
}

bool AVistaLiquidReceiverActor::PlanPourTransition(
    const FVistaLiquidStateSnapshot& SourceBefore,
    const FVistaLiquidStateSnapshot& ReceiverBefore,
    FName AcceptedType,
    FVistaLiquidStateSnapshot& OutSourceAfter,
    FVistaLiquidStateSnapshot& OutReceiverAfter,
    float& OutTransferMilliliters,
    FName& OutCode)
{
    OutSourceAfter = SourceBefore;
    OutReceiverAfter = ReceiverBefore;
    OutTransferMilliliters = 0.0f;
    FName ValidationCode;
    if (!AVistaPickupActor::ValidateLiquidState(
            SourceBefore, ValidationCode) || !SourceBefore.bPourable)
    {
        OutCode = SourceBefore.bPourable
            ? ValidationCode : FName(TEXT("POUR_SOURCE_NOT_POURABLE"));
        return false;
    }
    if (!ValidateReceiverState(ReceiverBefore, ValidationCode) ||
        !IsClosedName(AcceptedType))
    {
        OutCode = IsClosedName(AcceptedType)
            ? ValidationCode : FName(TEXT("LIQUID_RECEIVER_TYPE_INVALID"));
        return false;
    }
    if (!SourceBefore.IsFilled())
    {
        OutCode = TEXT("POUR_SOURCE_EMPTY");
        return false;
    }
    if (SourceBefore.LiquidType != AcceptedType ||
        (ReceiverBefore.IsFilled() &&
         ReceiverBefore.LiquidType != SourceBefore.LiquidType))
    {
        OutCode = TEXT("LIQUID_RECEIVER_TYPE_MISMATCH");
        return false;
    }
    const float Available =
        ReceiverBefore.CapacityMilliliters - ReceiverBefore.AmountMilliliters;
    if (Available <= KINDA_SMALL_NUMBER)
    {
        OutCode = TEXT("LIQUID_RECEIVER_FULL");
        return false;
    }
    OutTransferMilliliters =
        FMath::Min(SourceBefore.AmountMilliliters, Available);
    if (OutTransferMilliliters <= KINDA_SMALL_NUMBER)
    {
        OutCode = TEXT("POUR_TRANSFER_EMPTY");
        return false;
    }
    OutSourceAfter.AmountMilliliters =
        SourceBefore.AmountMilliliters - OutTransferMilliliters;
    OutReceiverAfter.AmountMilliliters =
        ReceiverBefore.AmountMilliliters + OutTransferMilliliters;
    OutReceiverAfter.LiquidType = SourceBefore.LiquidType;
    if (!AVistaPickupActor::ValidateLiquidState(
            OutSourceAfter, ValidationCode) ||
        !ValidateReceiverState(OutReceiverAfter, ValidationCode))
    {
        OutCode = ValidationCode;
        return false;
    }
    OutCode = TEXT("POUR_TRANSITION_PLANNED");
    return true;
}

bool AVistaLiquidReceiverActor::StateMatchesTransition(
    const FVistaLiquidStateSnapshot& SourceBefore,
    const FVistaLiquidStateSnapshot& ReceiverBefore,
    const FVistaLiquidStateSnapshot& SourceAfter,
    const FVistaLiquidStateSnapshot& ReceiverAfter) const
{
    FVistaLiquidStateSnapshot ExpectedSource;
    FVistaLiquidStateSnapshot ExpectedReceiver;
    float Transfer = 0.0f;
    FName Code;
    return PlanPourTransition(
               SourceBefore,
               ReceiverBefore,
               AcceptedLiquidType,
               ExpectedSource,
               ExpectedReceiver,
               Transfer,
               Code) &&
        LiquidStatesBitExact(ExpectedSource, SourceAfter) &&
        LiquidStatesBitExact(ExpectedReceiver, ReceiverAfter);
}

bool AVistaLiquidReceiverActor::CanReceive(
    const FVistaLiquidStateSnapshot& Source,
    FName& OutCode) const
{
    FVistaLiquidStateSnapshot SourceAfter;
    FVistaLiquidStateSnapshot ReceiverAfter;
    float Transfer = 0.0f;
    return PlanPourTransition(
        Source,
        LiquidState,
        AcceptedLiquidType,
        SourceAfter,
        ReceiverAfter,
        Transfer,
        OutCode);
}

bool AVistaLiquidReceiverActor::IsTransactionReservedBy(
    const UVistaActionExecutorComponent* Executor,
    FName CommandId,
    const AVistaPickupActor* Source) const
{
    return IsReceiverReservationOwnedBy(Executor, CommandId, Source) &&
        Source->IsPourTransactionReservedBy(
            Executor, CommandId, this);
}

bool AVistaLiquidReceiverActor::IsReceiverReservationOwnedBy(
    const UVistaActionExecutorComponent* Executor,
    FName CommandId,
    const AVistaPickupActor* Source) const
{
    return Executor != nullptr && !CommandId.IsNone() && Source != nullptr &&
        ActiveTransactionExecutor.Get() == Executor &&
        ActiveTransactionCommandId == CommandId &&
        ReservedSource.Get() == Source;
}

bool AVistaLiquidReceiverActor::WasTransactionReleasedBy(
    const UVistaActionExecutorComponent* Executor,
    FName CommandId,
    const AVistaPickupActor* Source) const
{
    return Executor != nullptr && !CommandId.IsNone() && Source != nullptr &&
        LastReleasedExecutor.Get() == Executor &&
        LastReleasedCommandId == CommandId &&
        LastReleasedSource.Get() == Source;
}

bool AVistaLiquidReceiverActor::ClearReceiverReservationIfOwned(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    AVistaPickupActor* Source,
    bool bRecordRelease)
{
    if (!IsReceiverReservationOwnedBy(Executor, CommandId, Source))
    {
        return false;
    }
    if (bRecordRelease)
    {
        LastReleasedExecutor = Executor;
        LastReleasedCommandId = CommandId;
        LastReleasedSource = Source;
    }
    ActiveTransactionExecutor.Reset();
    ActiveTransactionCommandId = NAME_None;
    ReservedRequester.Reset();
    ReservedSource.Reset();
    return !IsReserved();
}

bool AVistaLiquidReceiverActor::ReleaseReservationForSourceEndPlay(
    AVistaPickupActor* Source,
    UVistaActionExecutorComponent* Executor,
    FName CommandId)
{
    return HasAuthority() &&
        ClearReceiverReservationIfOwned(
            Executor, CommandId, Source, false);
}

bool AVistaLiquidReceiverActor::TryReservePourTransaction(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    AActor* Requester,
    AVistaPickupActor* Source,
    FName& OutCode)
{
    if (!IsValid(Executor) || CommandId.IsNone() || !IsValid(Requester) ||
        !IsValid(Source) || static_cast<AActor*>(Source) == this)
    {
        OutCode = TEXT("POUR_RESERVATION_INPUT_INVALID");
        return false;
    }
    if (IsReserved())
    {
        OutCode = TEXT("LIQUID_RECEIVER_RESERVED");
        return false;
    }
    FVistaLiquidStateSnapshot SourceLiquid;
    FVistaPickupPhysicalStateSnapshot SourcePhysical;
    if (!Source->CapturePourTransactionState(
            Requester, SourceLiquid, SourcePhysical, OutCode) ||
        !CanReceive(SourceLiquid, OutCode))
    {
        return false;
    }
    if (!Source->TryReservePourTransaction(
            Executor, CommandId, this))
    {
        OutCode = TEXT("POUR_SOURCE_RESERVED");
        return false;
    }
    ActiveTransactionExecutor = Executor;
    ActiveTransactionCommandId = CommandId;
    ReservedRequester = Requester;
    ReservedSource = Source;
    if (!IsTransactionReservedBy(Executor, CommandId, Source))
    {
        Source->ReleasePourTransactionReservation(
            Executor, CommandId, this);
        ClearReceiverReservationIfOwned(
            Executor, CommandId, Source, false);
        OutCode = TEXT("POUR_RESERVATION_BIND_FAILED");
        return false;
    }
    OutCode = TEXT("POUR_TARGETS_RESERVED");
    return true;
}

bool AVistaLiquidReceiverActor::ReleasePourTransaction(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    AVistaPickupActor* Source,
    FName& OutCode)
{
    if (!IsReceiverReservationOwnedBy(Executor, CommandId, Source))
    {
        if (!IsReserved() &&
            WasTransactionReleasedBy(Executor, CommandId, Source) &&
            Source != nullptr && Source->IsTransactionUnreserved())
        {
            OutCode = TEXT("POUR_TARGETS_ALREADY_RELEASED");
            return true;
        }
        OutCode = TEXT("POUR_RESERVATION_NOT_OWNED");
        return false;
    }

    if (Source->IsPourTransactionReservedBy(
            Executor, CommandId, this))
    {
        if (!Source->ReleasePourTransactionReservation(
                Executor, CommandId, this))
        {
            OutCode = TEXT("POUR_SOURCE_RESERVATION_RELEASE_FAILED");
            return false;
        }
    }
    else if (!Source->IsTransactionUnreserved())
    {
        OutCode = TEXT("POUR_SOURCE_RESERVATION_DRIFT");
        return false;
    }
    if (!Source->IsTransactionUnreserved())
    {
        OutCode = TEXT("POUR_SOURCE_RESERVATION_RELEASE_FAILED");
        return false;
    }

#if WITH_DEV_AUTOMATION_TESTS
    if (bFailNextReleaseFinalize)
    {
        bFailNextReleaseFinalize = false;
        OutCode = TEXT("POUR_RECEIVER_RELEASE_FINALIZE_INJECTED_FAILURE");
        return false;
    }
#endif
    if (!ClearReceiverReservationIfOwned(
            Executor, CommandId, Source, true))
    {
        OutCode = TEXT("POUR_RECEIVER_RESERVATION_RELEASE_FAILED");
        return false;
    }
    OutCode = TEXT("POUR_TARGETS_RELEASED");
    return true;
}

bool AVistaLiquidReceiverActor::ApplyLiquidStateForTransaction(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    AVistaPickupActor* Source,
    const FVistaLiquidStateSnapshot& ExpectedBefore,
    const FVistaLiquidStateSnapshot& After,
    FName& OutCode)
{
    if (!IsTransactionReservedBy(Executor, CommandId, Source))
    {
        OutCode = TEXT("TRANSACTION_RESERVATION_REQUIRED");
        return false;
    }
    if (!HasAuthority())
    {
        OutCode = TEXT("AUTHORITY_REQUIRED");
        return false;
    }
    if (!LiquidStatesBitExact(LiquidState, ExpectedBefore))
    {
        OutCode = TEXT("LIQUID_RECEIVER_STATE_DRIFT");
        return false;
    }
    if (!ValidateReceiverState(After, OutCode))
    {
        return false;
    }
    if (After.IsFilled() && After.LiquidType != AcceptedLiquidType)
    {
        OutCode = TEXT("LIQUID_RECEIVER_TYPE_MISMATCH");
        return false;
    }
#if WITH_DEV_AUTOMATION_TESTS
    if (bFailNextReceiveCommit)
    {
        bFailNextReceiveCommit = false;
        OutCode = TEXT("POUR_RECEIVER_COMMIT_INJECTED_FAILURE");
        return false;
    }
#endif
    SetLiquidState(After);
    OutCode = TEXT("POUR_RECEIVER_CREDITED");
    return true;
}

FVistaInteractionResult
AVistaLiquidReceiverActor::RestoreTransactionalState(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    const FVistaLiquidStateSnapshot& State)
{
    if (!IsValid(Executor) || CommandId.IsNone() ||
        ActiveTransactionExecutor.Get() != Executor ||
        ActiveTransactionCommandId != CommandId)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("TRANSACTION_RESERVATION_REQUIRED"),
            SemanticId);
    }
    FName Code;
    if (!HasAuthority() || !ValidateReceiverState(State, Code))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            HasAuthority() ? Code : FName(TEXT("AUTHORITY_REQUIRED")),
            SemanticId);
    }
    SetLiquidState(State);
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("POUR_RECEIVER_STATE_RESTORED"));
}

FVistaPourTransactionResult
AVistaLiquidReceiverActor::CommitPourTransaction(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    AActor* Requester,
    AVistaPickupActor* Source)
{
    FVistaPourTransactionResult Result;
    Result.SourceSemanticId = IsValid(Source) ? Source->SemanticId : FString();
    Result.ReceiverSemanticId = SemanticId;
    if (!IsTransactionReservedBy(Executor, CommandId, Source) ||
        ReservedRequester.Get() != Requester)
    {
        Result.Code = TEXT("TRANSACTION_RESERVATION_REQUIRED");
        return Result;
    }
    FName Code;
    if (!Source->CapturePourTransactionState(
            Requester,
            Result.SourceBefore,
            Result.SourcePhysicalBefore,
            Code))
    {
        Result.Code = Code;
        return Result;
    }
    Result.ReceiverBefore = LiquidState;
    FVistaLiquidStateSnapshot PlannedSourceAfter;
    FVistaLiquidStateSnapshot PlannedReceiverAfter;
    if (!PlanPourTransition(
            Result.SourceBefore,
            Result.ReceiverBefore,
            AcceptedLiquidType,
            PlannedSourceAfter,
            PlannedReceiverAfter,
            Result.TransferMilliliters,
            Code))
    {
        Result.Code = Code;
        return Result;
    }

    const FVistaInteractionResult SourceCommit = Source->CommitPourOut(
        Executor,
        CommandId,
        Result.SourceBefore,
        Result.TransferMilliliters);
    if (!SourceCommit.IsSuccess())
    {
        Result.Code = SourceCommit.Code;
        return Result;
    }
    Result.bSourceMutationCommitted = true;

    if (!ApplyLiquidStateForTransaction(
            Executor,
            CommandId,
            Source,
            Result.ReceiverBefore,
            PlannedReceiverAfter,
            Code))
    {
        Result.bCompensationAttempted = true;
        const FVistaInteractionResult ReceiverRestore =
            RestoreTransactionalState(
                Executor, CommandId, Result.ReceiverBefore);
        const FVistaInteractionResult SourceRestore =
            Source->RestorePourLiquidState(
                Executor, CommandId, Result.SourceBefore);
        Result.bCompensated = ReceiverRestore.IsSuccess() &&
            SourceRestore.IsSuccess() &&
            LiquidStatesBitExact(LiquidState, Result.ReceiverBefore) &&
            Source->PourStateMatches(
                Result.SourceBefore, Result.SourcePhysicalBefore);
        Result.SourceAfter = Source->LiquidState;
        Result.ReceiverAfter = LiquidState;
        USceneComponent* Parent = nullptr;
        AActor* Carrier = nullptr;
        EVistaPickupDisposition Disposition = EVistaPickupDisposition::Free;
        Source->CapturePhysicalState(
            Result.SourcePhysicalAfter, Parent, Carrier, Disposition);
        Result.Code = Result.bCompensated
            ? FName(TEXT("POUR_SECOND_MUTATION_FAILED_ROLLED_BACK"))
            : FName(TEXT("POUR_COMPENSATION_FAILED"));
        return Result;
    }
    Result.bReceiverMutationCommitted = true;
    Result.SourceAfter = Source->LiquidState;
    Result.ReceiverAfter = LiquidState;
    USceneComponent* Parent = nullptr;
    AActor* Carrier = nullptr;
    EVistaPickupDisposition Disposition = EVistaPickupDisposition::Free;
    const bool bPhysicalCaptured = Source->CapturePhysicalState(
        Result.SourcePhysicalAfter, Parent, Carrier, Disposition);
    const bool bPostcondition = bPhysicalCaptured &&
        PhysicalSnapshotsBitExact(
            Result.SourcePhysicalBefore, Result.SourcePhysicalAfter) &&
        Source->PourStateMatches(
            PlannedSourceAfter, Result.SourcePhysicalBefore) &&
        StateMatchesTransition(
            Result.SourceBefore,
            Result.ReceiverBefore,
            Result.SourceAfter,
            Result.ReceiverAfter);
    if (!bPostcondition)
    {
        Result.bCompensationAttempted = true;
        const FVistaInteractionResult ReceiverRestore =
            RestoreTransactionalState(
                Executor, CommandId, Result.ReceiverBefore);
        const FVistaInteractionResult SourceRestore =
            Source->RestorePourLiquidState(
                Executor, CommandId, Result.SourceBefore);
        Result.bCompensated = ReceiverRestore.IsSuccess() &&
            SourceRestore.IsSuccess() &&
            LiquidStatesBitExact(LiquidState, Result.ReceiverBefore) &&
            Source->PourStateMatches(
                Result.SourceBefore, Result.SourcePhysicalBefore);
        Result.SourceAfter = Source->LiquidState;
        Result.ReceiverAfter = LiquidState;
        Source->CapturePhysicalState(
            Result.SourcePhysicalAfter, Parent, Carrier, Disposition);
        Result.Code = Result.bCompensated
            ? FName(TEXT("POUR_POSTCONDITION_FAILED_ROLLED_BACK"))
            : FName(TEXT("POUR_COMPENSATION_FAILED"));
        return Result;
    }

    Result.bSucceeded = true;
    Result.Code = TEXT("POUR_COMMITTED");
    return Result;
}

#if WITH_DEV_AUTOMATION_TESTS
bool AVistaLiquidReceiverActor::ConfigureLiquidStateForDevAutomation(
    const FVistaLiquidStateSnapshot& State,
    FName& OutCode)
{
    if (!HasAuthority() || ActiveTransactionExecutor.IsValid() ||
        !ActiveTransactionCommandId.IsNone() ||
        !ValidateReceiverState(State, OutCode) ||
        (State.IsFilled() && State.LiquidType != AcceptedLiquidType))
    {
        if (!HasAuthority())
        {
            OutCode = TEXT("AUTHORITY_REQUIRED");
        }
        else if (ActiveTransactionExecutor.IsValid() ||
                 !ActiveTransactionCommandId.IsNone())
        {
            OutCode = TEXT("LIQUID_RECEIVER_RESERVED");
        }
        else if (State.IsFilled() && State.LiquidType != AcceptedLiquidType)
        {
            OutCode = TEXT("LIQUID_RECEIVER_TYPE_MISMATCH");
        }
        return false;
    }
    SetLiquidState(State);
    OutCode = TEXT("LIQUID_RECEIVER_CONFIGURED_FOR_TEST");
    return true;
}

bool AVistaLiquidReceiverActor::TryReservePourForDevAutomation(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    AActor* Requester,
    AVistaPickupActor* Source,
    FName& OutCode)
{
    return TryReservePourTransaction(
        Executor, CommandId, Requester, Source, OutCode);
}

bool AVistaLiquidReceiverActor::ReleasePourForDevAutomation(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    AVistaPickupActor* Source,
    FName& OutCode)
{
    return ReleasePourTransaction(Executor, CommandId, Source, OutCode);
}

FVistaPourTransactionResult
AVistaLiquidReceiverActor::CommitPourForDevAutomation(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    AActor* Requester,
    AVistaPickupActor* Source)
{
    return CommitPourTransaction(Executor, CommandId, Requester, Source);
}

bool AVistaLiquidReceiverActor::IsReservedForDevAutomation(
    const UVistaActionExecutorComponent* Executor,
    FName CommandId) const
{
    return IsValid(Executor) && !CommandId.IsNone() &&
        ActiveTransactionExecutor.Get() == Executor &&
        ActiveTransactionCommandId == CommandId;
}

void AVistaLiquidReceiverActor::FailNextReceiveCommitForDevAutomation()
{
    bFailNextReceiveCommit = true;
}

void AVistaLiquidReceiverActor::FailNextReleaseFinalizeForDevAutomation()
{
    bFailNextReleaseFinalize = true;
}
#endif
