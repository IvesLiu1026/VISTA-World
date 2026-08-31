#include "VistaContainerActor.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Net/UnrealNetwork.h"
#include "VistaActionExecutorComponent.h"

AVistaContainerActor::AVistaContainerActor()
{
    Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ContainerMesh"));
    SetRootComponent(Mesh);
    Mesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));

    HandleTarget =
        CreateDefaultSubobject<USceneComponent>(TEXT("HandleTarget"));
    HandleTarget->SetupAttachment(Mesh);
    HandleTarget->ComponentTags.Add(TEXT("VistaInteractionTarget"));
    AllowedAffordances = {
        EVistaAffordance::Inspect,
        EVistaAffordance::Open,
        EVistaAffordance::Close};
}

void AVistaContainerActor::BeginPlay()
{
    Super::BeginPlay();
    if (HasAuthority())
    {
        bOpen = bInitiallyOpen;
    }
    OnContainerStateChanged(bOpen);
}

void AVistaContainerActor::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaContainerActor, bOpen);
}

FVistaEntityRuntimeState AVistaContainerActor::VistaGetRuntimeState_Implementation() const
{
    FVistaEntityRuntimeState State = Super::VistaGetRuntimeState_Implementation();
    State.Values.Add(TEXT("open"), bOpen ? TEXT("true") : TEXT("false"));
    return State;
}

FVistaInteractionResult AVistaContainerActor::VistaApplyRuntimeState_Implementation(
    const FVistaEntityRuntimeState& State)
{
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected, TEXT("AUTHORITY_REQUIRED"), SemanticId);
    }
    if (ActiveTransactionExecutor.IsValid() ||
        !ActiveTransactionCommandId.IsNone())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Busy,
            TEXT("CONTAINER_TARGET_RESERVED"),
            SemanticId);
    }
    const FVistaInteractionResult BaseResult = Super::VistaApplyRuntimeState_Implementation(State);
    if (!BaseResult.IsSuccess())
    {
        return BaseResult;
    }
    const FString* Open = State.Values.Find(TEXT("open"));
    if (Open)
    {
        bOpen = Open->Equals(TEXT("true"), ESearchCase::CaseSensitive);
    }
    OnContainerStateChanged(bOpen);
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId, VistaGetRuntimeState_Implementation(), TEXT("CONTAINER_STATE_APPLIED"));
}

FVistaInteractionResult AVistaContainerActor::VistaInteract_Implementation(
    const FVistaInteractionRequest& Request)
{
    const FVistaInteractionResult Validation = ValidateRequest(Request);
    if (!Validation.IsSuccess())
    {
        return Validation;
    }
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected, TEXT("AUTHORITY_REQUIRED"), SemanticId);
    }
    if (Request.Affordance != EVistaAffordance::Open &&
        Request.Affordance != EVistaAffordance::Close)
    {
        return Super::VistaInteract_Implementation(Request);
    }
    return FVistaInteractionResult::Failure(
        EVistaInteractionStatus::Rejected,
        TEXT("ACTION_EXECUTOR_REQUIRED"),
        SemanticId);
}

void AVistaContainerActor::OnRep_OpenState()
{
    OnContainerStateChanged(bOpen);
}

bool AVistaContainerActor::TryReserveTransaction(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId)
{
    if (!IsValid(Executor) || CommandId.IsNone() ||
        ActiveTransactionExecutor.IsValid() ||
        !ActiveTransactionCommandId.IsNone())
    {
        return false;
    }
    ActiveTransactionExecutor = Executor;
    ActiveTransactionCommandId = CommandId;
    return true;
}

bool AVistaContainerActor::ReleaseTransaction(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId)
{
    if (ActiveTransactionExecutor.Get() != Executor ||
        ActiveTransactionCommandId != CommandId)
    {
        return false;
    }
    ActiveTransactionExecutor.Reset();
    ActiveTransactionCommandId = NAME_None;
    return true;
}

FVistaInteractionResult AVistaContainerActor::CommitTransactionalInteraction(
    UVistaActionExecutorComponent* Executor,
    const FVistaInteractionRequest& Request,
    const FName CommitCommandId)
{
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
    if (!IsValid(Executor) || CommitCommandId.IsNone() ||
        ActiveTransactionExecutor.Get() != Executor ||
        ActiveTransactionCommandId != CommitCommandId)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("CONTAINER_RESERVATION_REQUIRED"),
            SemanticId);
    }
    if (Request.Affordance != EVistaAffordance::Open &&
        Request.Affordance != EVistaAffordance::Close)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Unsupported,
            TEXT("CONTAINER_AFFORDANCE_REQUIRED"),
            SemanticId);
    }
    const bool bRequestedOpen = Request.Affordance == EVistaAffordance::Open;
    if (bRequestedOpen == bOpen)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            bOpen ? FName(TEXT("CONTAINER_ALREADY_OPEN"))
                  : FName(TEXT("CONTAINER_ALREADY_CLOSED")),
            SemanticId);
    }
    bOpen = bRequestedOpen;
    OnContainerStateChanged(bOpen);
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        bOpen ? TEXT("CONTAINER_OPENED") : TEXT("CONTAINER_CLOSED"));
}

FVistaInteractionResult AVistaContainerActor::RestoreTransactionalState(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    const FVistaEntityRuntimeState& State)
{
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("AUTHORITY_REQUIRED"),
            SemanticId);
    }
    if (!IsValid(Executor) || CommandId.IsNone() ||
        ActiveTransactionExecutor.Get() != Executor ||
        ActiveTransactionCommandId != CommandId)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("CONTAINER_RESERVATION_REQUIRED"),
            SemanticId);
    }
    if (!State.SemanticId.IsEmpty() && State.SemanticId != SemanticId)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::NotFound,
            TEXT("SEMANTIC_ID_MISMATCH"),
            SemanticId);
    }
    const FString* Open = State.Values.Find(TEXT("open"));
    if (Open == nullptr ||
        (!Open->Equals(TEXT("true"), ESearchCase::CaseSensitive) &&
         !Open->Equals(TEXT("false"), ESearchCase::CaseSensitive)))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("CONTAINER_OPEN_STATE_INVALID"),
            SemanticId);
    }
    const FVistaInteractionResult BaseResult =
        AVistaSemanticActor::VistaApplyRuntimeState_Implementation(State);
    if (!BaseResult.IsSuccess())
    {
        return BaseResult;
    }
    bOpen = Open->Equals(TEXT("true"), ESearchCase::CaseSensitive);
    OnContainerStateChanged(bOpen);
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("CONTAINER_STATE_RESTORED"));
}
