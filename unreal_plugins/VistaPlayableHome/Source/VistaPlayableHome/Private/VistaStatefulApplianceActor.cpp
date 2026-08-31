#include "VistaStatefulApplianceActor.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Net/UnrealNetwork.h"
#include "VistaActionExecutorComponent.h"

namespace
{
const FName PoweredKey(TEXT("powered"));
const FName ActiveKey(TEXT("active"));
const FName LegacyOnKey(TEXT("on"));
const FName StatusKey(TEXT("status"));

bool IsApplianceStateKey(const FName Key)
{
    return Key == PoweredKey || Key == ActiveKey || Key == LegacyOnKey ||
        Key == StatusKey;
}

bool StatesMatchOutsideApplianceFields(
    const FVistaEntityRuntimeState& Before,
    const FVistaEntityRuntimeState& After)
{
    if (Before.SemanticId != After.SemanticId ||
        !Before.Transform.Equals(After.Transform, 0.01f) ||
        Before.bHidden != After.bHidden || Before.bPortable != After.bPortable)
    {
        return false;
    }
    for (const TPair<FName, FString>& Pair : Before.Values)
    {
        if (IsApplianceStateKey(Pair.Key))
        {
            continue;
        }
        const FString* Other = After.Values.Find(Pair.Key);
        if (Other == nullptr || *Other != Pair.Value)
        {
            return false;
        }
    }
    for (const TPair<FName, FString>& Pair : After.Values)
    {
        if (!IsApplianceStateKey(Pair.Key) &&
            !Before.Values.Contains(Pair.Key))
        {
            return false;
        }
    }
    return true;
}
} // namespace

AVistaStatefulApplianceActor::AVistaStatefulApplianceActor()
{
    Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ApplianceMesh"));
    SetRootComponent(Mesh);
    Mesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));

    ControlTarget =
        CreateDefaultSubobject<USceneComponent>(TEXT("ControlTarget"));
    ControlTarget->SetupAttachment(Mesh);
    ControlTarget->ComponentTags.Add(TEXT("VistaInteractionTarget"));
    AllowedAffordances = {
        EVistaAffordance::Inspect,
        EVistaAffordance::Toggle,
        EVistaAffordance::Press,
        EVistaAffordance::TurnOn,
        EVistaAffordance::TurnOff};
}

void AVistaStatefulApplianceActor::BeginPlay()
{
    Super::BeginPlay();
    if (HasAuthority())
    {
        FVistaApplianceState Fallback;
        Fallback.bPowered = bInitiallyPowered;
        Fallback.bActive = bInitiallyOn;
        Fallback.Status = bInitiallyPowered
            ? InitialStatus : FName(TEXT("off"));
        const FVistaEntityRuntimeState AuthoredState =
            Super::VistaGetRuntimeState_Implementation();
        FVistaApplianceState InitialState;
        FName Code;
        if (!ReadClosedState(AuthoredState, Fallback, InitialState, Code))
        {
            InitialState = Fallback;
            if (!InitialState.bPowered)
            {
                InitialState.bActive = false;
                InitialState.Status = TEXT("off");
            }
        }
        SetClosedApplianceState(InitialState);
    }
    else
    {
        SyncRuntimeStateValues();
        OnApplianceStateChanged(bActive);
        OnApplianceRuntimeStateChanged(bPowered, bActive, Status);
    }
}

void AVistaStatefulApplianceActor::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaStatefulApplianceActor, bPowered);
    DOREPLIFETIME(AVistaStatefulApplianceActor, bActive);
    DOREPLIFETIME(AVistaStatefulApplianceActor, Status);
}

bool AVistaStatefulApplianceActor::IsTransactionalApplianceAffordance(
    const EVistaAffordance Affordance)
{
    return Affordance == EVistaAffordance::Toggle ||
        Affordance == EVistaAffordance::Press ||
        Affordance == EVistaAffordance::TurnOn ||
        Affordance == EVistaAffordance::TurnOff;
}

bool AVistaStatefulApplianceActor::PlanInteractionTransition(
    const FVistaApplianceState& Before,
    const EVistaAffordance Affordance,
    const FVistaApplianceActivityProfile& InActivityProfile,
    const FVistaAppliancePressProfile& InPressProfile,
    FVistaApplianceState& OutAfter,
    bool& bOutMutated,
    FName& OutCode)
{
    OutAfter = Before;
    bOutMutated = false;
    if ((!Before.bPowered && Before.bActive) || Before.Status.IsNone())
    {
        OutCode = TEXT("APPLIANCE_STATE_INVALID");
        return false;
    }

    switch (Affordance)
    {
    case EVistaAffordance::TurnOn:
        if (!Before.bPowered)
        {
            OutCode = TEXT("APPLIANCE_POWER_REQUIRED");
            return false;
        }
        if (Before.bActive)
        {
            OutCode = TEXT("APPLIANCE_ALREADY_ACTIVE");
            return true;
        }
        if (InActivityProfile.ActiveStatus.IsNone())
        {
            OutCode = TEXT("APPLIANCE_ACTIVITY_PROFILE_INVALID");
            return false;
        }
        OutAfter.bActive = true;
        OutAfter.Status = InActivityProfile.ActiveStatus;
        OutCode = TEXT("APPLIANCE_TURNED_ON");
        break;
    case EVistaAffordance::TurnOff:
        if (!Before.bActive)
        {
            OutCode = TEXT("APPLIANCE_ALREADY_INACTIVE");
            return true;
        }
        if (InActivityProfile.InactiveStatus.IsNone())
        {
            OutCode = TEXT("APPLIANCE_ACTIVITY_PROFILE_INVALID");
            return false;
        }
        OutAfter.bActive = false;
        OutAfter.Status = InActivityProfile.InactiveStatus;
        OutCode = TEXT("APPLIANCE_TURNED_OFF");
        break;
    case EVistaAffordance::Toggle:
        if (!Before.bPowered)
        {
            OutCode = TEXT("APPLIANCE_POWER_REQUIRED");
            return false;
        }
        // Toggle owns exactly active. Power and status remain separate authorities.
        OutAfter.bActive = !Before.bActive;
        OutCode = OutAfter.bActive
            ? FName(TEXT("APPLIANCE_ACTIVE"))
            : FName(TEXT("APPLIANCE_INACTIVE"));
        break;
    case EVistaAffordance::Press:
        // P0 controls are never operable without external power. This is not
        // author-overridable: a non-activating press must fail closed too.
        if (!Before.bPowered)
        {
            OutCode = TEXT("APPLIANCE_POWER_REQUIRED");
            return false;
        }
        if (InPressProfile.ControlId.IsNone() ||
            InPressProfile.ResultStatus.IsNone())
        {
            OutCode = TEXT("APPLIANCE_PRESS_PROFILE_INVALID");
            return false;
        }
        OutAfter.bActive = InPressProfile.bResultActive;
        OutAfter.Status = InPressProfile.ResultStatus;
        OutCode = OutAfter == Before
            ? FName(TEXT("APPLIANCE_PRESS_ALREADY_APPLIED"))
            : FName(TEXT("APPLIANCE_CONTROL_PRESSED"));
        break;
    default:
        OutCode = TEXT("APPLIANCE_AFFORDANCE_REQUIRED");
        return false;
    }

    bOutMutated = !(OutAfter == Before);
    return true;
}

FVistaEntityRuntimeState
AVistaStatefulApplianceActor::VistaGetRuntimeState_Implementation() const
{
    FVistaEntityRuntimeState State =
        Super::VistaGetRuntimeState_Implementation();
    State.Values.Add(PoweredKey, bPowered ? TEXT("true") : TEXT("false"));
    State.Values.Add(ActiveKey, bActive ? TEXT("true") : TEXT("false"));
    // Legacy presentation only: on aliases active, never powered.
    State.Values.Add(LegacyOnKey, bActive ? TEXT("true") : TEXT("false"));
    State.Values.Add(StatusKey, Status.ToString());
    State.Values.Add(TEXT("appliance_kind"), ApplianceKind.ToString());
    State.Values.Add(TEXT("press_control"), PressProfile.ControlId.ToString());
    State.Values.Add(
        TEXT("control_style"),
        ControlStyle == EVistaApplianceControlStyle::Button
            ? TEXT("button") : TEXT("rotary"));
    return State;
}

bool AVistaStatefulApplianceActor::ReadBooleanValue(
    const TMap<FName, FString>& Values,
    const FName Key,
    bool& OutValue,
    bool& bOutPresent)
{
    const FString* Value = Values.Find(Key);
    bOutPresent = Value != nullptr;
    if (!bOutPresent)
    {
        return true;
    }
    if (Value->Equals(TEXT("true"), ESearchCase::CaseSensitive))
    {
        OutValue = true;
        return true;
    }
    if (Value->Equals(TEXT("false"), ESearchCase::CaseSensitive))
    {
        OutValue = false;
        return true;
    }
    return false;
}

bool AVistaStatefulApplianceActor::ReadClosedState(
    const FVistaEntityRuntimeState& State,
    const FVistaApplianceState& Fallback,
    FVistaApplianceState& OutState,
    FName& OutCode)
{
    OutState = Fallback;
    bool bPoweredPresent = false;
    bool bActivePresent = false;
    bool bLegacyOnPresent = false;
    bool bLegacyOn = false;
    if (!ReadBooleanValue(
            State.Values, PoweredKey, OutState.bPowered, bPoweredPresent) ||
        !ReadBooleanValue(
            State.Values, ActiveKey, OutState.bActive, bActivePresent) ||
        !ReadBooleanValue(
            State.Values, LegacyOnKey, bLegacyOn, bLegacyOnPresent))
    {
        OutCode = TEXT("APPLIANCE_BOOLEAN_STATE_INVALID");
        return false;
    }
    if (!bActivePresent && bLegacyOnPresent)
    {
        OutState.bActive = bLegacyOn;
    }
    else if (bActivePresent && bLegacyOnPresent &&
             OutState.bActive != bLegacyOn)
    {
        OutCode = TEXT("APPLIANCE_ACTIVE_ALIAS_MISMATCH");
        return false;
    }
    if (const FString* StatusValue = State.Values.Find(StatusKey))
    {
        if (StatusValue->IsEmpty() || StatusValue->Len() > 64)
        {
            OutCode = TEXT("APPLIANCE_STATUS_INVALID");
            return false;
        }
        OutState.Status = FName(**StatusValue);
    }
    if (!OutState.bPowered && OutState.bActive)
    {
        OutCode = TEXT("APPLIANCE_ACTIVE_WITHOUT_POWER");
        return false;
    }
    if (OutState.Status.IsNone())
    {
        OutCode = TEXT("APPLIANCE_STATUS_INVALID");
        return false;
    }
    OutCode = TEXT("APPLIANCE_STATE_VALID");
    return true;
}

FVistaInteractionResult
AVistaStatefulApplianceActor::ApplyApplianceRuntimeState(
    const FVistaEntityRuntimeState& State,
    const FName SuccessCode)
{
    FVistaApplianceState NewState;
    FName ValidationCode;
    if (!ReadClosedState(
            State, GetClosedApplianceState(), NewState, ValidationCode))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            ValidationCode,
            SemanticId);
    }
    const FVistaInteractionResult BaseResult =
        Super::VistaApplyRuntimeState_Implementation(State);
    if (!BaseResult.IsSuccess())
    {
        return BaseResult;
    }
    SetClosedApplianceState(NewState);
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        SuccessCode);
}

FVistaInteractionResult
AVistaStatefulApplianceActor::VistaApplyRuntimeState_Implementation(
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
            TEXT("APPLIANCE_TARGET_RESERVED"),
            SemanticId);
    }
    return ApplyApplianceRuntimeState(State, TEXT("APPLIANCE_STATE_APPLIED"));
}

FVistaInteractionResult AVistaStatefulApplianceActor::VistaInteract_Implementation(
    const FVistaInteractionRequest& Request)
{
    const FVistaInteractionResult Validation = ValidateRequest(Request);
    if (!Validation.IsSuccess())
    {
        return Validation;
    }
    if (IsTransactionalApplianceAffordance(Request.Affordance))
    {
        // Mutating appliance affordances are reachable only through the shared
        // animation-gated executor at its contact commit point.
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("ACTION_EXECUTOR_REQUIRED"),
            SemanticId);
    }
    return Super::VistaInteract_Implementation(Request);
}

bool AVistaStatefulApplianceActor::TryReserveTransaction(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId)
{
    if (!IsValid(Executor) || CommandId.IsNone())
    {
        return false;
    }
    if (ActiveTransactionExecutor.IsValid() ||
        !ActiveTransactionCommandId.IsNone())
    {
        return false;
    }
    ActiveTransactionExecutor = Executor;
    ActiveTransactionCommandId = CommandId;
    return true;
}

bool AVistaStatefulApplianceActor::ReleaseTransaction(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId)
{
    if (ActiveTransactionExecutor.Get() == Executor &&
        ActiveTransactionCommandId == CommandId)
    {
        ActiveTransactionExecutor.Reset();
        ActiveTransactionCommandId = NAME_None;
        return true;
    }
    return false;
}

FVistaInteractionResult
AVistaStatefulApplianceActor::CommitTransactionalInteraction(
    UVistaActionExecutorComponent* Executor,
    const FVistaInteractionRequest& Request,
    const FName CommitCommandId)
{
    if (!IsValid(Executor) || CommitCommandId.IsNone() ||
        ActiveTransactionExecutor.Get() != Executor ||
        ActiveTransactionCommandId != CommitCommandId)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("TRANSACTION_RESERVATION_REQUIRED"),
            SemanticId);
    }
    const FVistaInteractionResult Validation = ValidateRequest(Request);
    if (!Validation.IsSuccess())
    {
        return Validation;
    }
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("AUTHORITY_REQUIRED"),
            SemanticId);
    }

    FVistaApplianceState After;
    bool bMutated = false;
    FName Code;
    if (!PlanInteractionTransition(
            GetClosedApplianceState(),
            Request.Affordance,
            ActivityProfile,
            PressProfile,
            After,
            bMutated,
            Code))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            Code,
            SemanticId);
    }
    if (bMutated)
    {
        SetClosedApplianceState(After);
        ForceNetUpdate();
    }
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        Code);
}

FVistaInteractionResult
AVistaStatefulApplianceActor::RestoreTransactionalState(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    const FVistaEntityRuntimeState& State)
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
    return ApplyApplianceRuntimeState(
        State, TEXT("APPLIANCE_TRANSACTION_STATE_RESTORED"));
}

bool AVistaStatefulApplianceActor::StateMatchesTransition(
    const FVistaEntityRuntimeState& Before,
    const FVistaEntityRuntimeState& After,
    const EVistaAffordance Affordance) const
{
    FVistaApplianceState BeforeState;
    FVistaApplianceState AfterState;
    FName Code;
    if (!ReadClosedState(
            Before, GetClosedApplianceState(), BeforeState, Code) ||
        !ReadClosedState(
            After, GetClosedApplianceState(), AfterState, Code) ||
        !StatesMatchOutsideApplianceFields(Before, After))
    {
        return false;
    }
    FVistaApplianceState Expected;
    bool bMutated = false;
    if (!PlanInteractionTransition(
            BeforeState,
            Affordance,
            ActivityProfile,
            PressProfile,
            Expected,
            bMutated,
            Code))
    {
        return false;
    }
    return Expected == AfterState;
}

FVistaApplianceState
AVistaStatefulApplianceActor::GetClosedApplianceState() const
{
    FVistaApplianceState State;
    State.bPowered = bPowered;
    State.bActive = bActive;
    State.Status = Status;
    return State;
}

void AVistaStatefulApplianceActor::SetClosedApplianceState(
    const FVistaApplianceState& NewState)
{
    bPowered = NewState.bPowered;
    bActive = NewState.bActive;
    Status = NewState.Status;
    SyncRuntimeStateValues();
    OnApplianceStateChanged(bActive);
    OnApplianceRuntimeStateChanged(bPowered, bActive, Status);
}

void AVistaStatefulApplianceActor::SyncRuntimeStateValues()
{
    RuntimeStateValues.Add(PoweredKey, bPowered ? TEXT("true") : TEXT("false"));
    RuntimeStateValues.Add(ActiveKey, bActive ? TEXT("true") : TEXT("false"));
    RuntimeStateValues.Add(LegacyOnKey, bActive ? TEXT("true") : TEXT("false"));
    RuntimeStateValues.Add(StatusKey, Status.ToString());
    RuntimeStateValues.Add(TEXT("appliance_kind"), ApplianceKind.ToString());
    RuntimeStateValues.Add(TEXT("press_control"), PressProfile.ControlId.ToString());
}

void AVistaStatefulApplianceActor::OnRep_ApplianceState()
{
    SyncRuntimeStateValues();
    OnApplianceStateChanged(bActive);
    OnApplianceRuntimeStateChanged(bPowered, bActive, Status);
}
