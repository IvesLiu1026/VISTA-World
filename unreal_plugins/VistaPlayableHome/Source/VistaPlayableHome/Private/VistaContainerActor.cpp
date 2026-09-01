#include "VistaContainerActor.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "EngineUtils.h"
#include "Net/UnrealNetwork.h"
#include "VistaActionExecutorComponent.h"
#include "VistaInteractable.h"
#include "VistaItemCarrier.h"
#include "VistaPickupActor.h"

AVistaContainerActor::AVistaContainerActor()
{
    Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ContainerMesh"));
    SetRootComponent(Mesh);
    Mesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));

    HandleTarget =
        CreateDefaultSubobject<USceneComponent>(TEXT("HandleTarget"));
    HandleTarget->SetupAttachment(Mesh);
    HandleTarget->ComponentTags.Add(TEXT("VistaInteractionTarget"));

    ContentsAnchor =
        CreateDefaultSubobject<USceneComponent>(TEXT("ContentsAnchor"));
    ContentsAnchor->SetupAttachment(Mesh);
    ContentsAnchor->ComponentTags.Add(TEXT("VistaContainerContentsTarget"));
    AllowedAffordances = {
        EVistaAffordance::Inspect,
        EVistaAffordance::Open,
        EVistaAffordance::Close,
        EVistaAffordance::Insert,
        EVistaAffordance::Remove};
}

void AVistaContainerActor::BeginPlay()
{
    Super::BeginPlay();
    if (HasAuthority())
    {
        bOpen = bInitiallyOpen;
    }
    OnContainerStateChanged(bOpen);
    OnContainerContentsChanged(ContainedItemSemanticId);
}

void AVistaContainerActor::EndPlay(
    const EEndPlayReason::Type EndPlayReason)
{
    ReleaseActiveStorageReservationForEndPlay();
    Super::EndPlay(EndPlayReason);
}

void AVistaContainerActor::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaContainerActor, bOpen);
    DOREPLIFETIME(AVistaContainerActor, ContainedItemSemanticId);
}

FVistaEntityRuntimeState AVistaContainerActor::VistaGetRuntimeState_Implementation() const
{
    FVistaEntityRuntimeState State = Super::VistaGetRuntimeState_Implementation();
    State.Values.Add(TEXT("open"), bOpen ? TEXT("true") : TEXT("false"));
    State.Values.Add(TEXT("storage_capacity"), TEXT("1"));
    State.Values.Add(
        TEXT("contents_count"),
        ContainedItemSemanticId.IsEmpty() ? TEXT("0") : TEXT("1"));
    State.Values.Add(TEXT("contained_item"), ContainedItemSemanticId);
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
    const FVistaEntityRuntimeState Current =
        VistaGetRuntimeState_Implementation();
    for (const FName Key : {
             FName(TEXT("storage_capacity")),
             FName(TEXT("contents_count")),
             FName(TEXT("contained_item"))})
    {
        const FString* Requested = State.Values.Find(Key);
        const FString* Existing = Current.Values.Find(Key);
        if (Requested != nullptr &&
            (Existing == nullptr || *Requested != *Existing))
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::Rejected,
                TEXT("CONTAINER_CONTENTS_PATCH_REJECTED"),
                SemanticId);
        }
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
        Request.Affordance != EVistaAffordance::Close &&
        Request.Affordance != EVistaAffordance::Insert &&
        Request.Affordance != EVistaAffordance::Remove)
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

void AVistaContainerActor::OnRep_ContentsState()
{
    OnContainerContentsChanged(ContainedItemSemanticId);
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
        ActiveTransactionCommandId != CommandId ||
        ActiveStorageItem.IsValid())
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
    const FString* Stored = State.Values.Find(TEXT("contained_item"));
    const FString* Count = State.Values.Find(TEXT("contents_count"));
    const FString* Capacity = State.Values.Find(TEXT("storage_capacity"));
    if (Stored == nullptr || Count == nullptr || Capacity == nullptr ||
        *Capacity != TEXT("1") ||
        (*Count != TEXT("0") && *Count != TEXT("1")) ||
        ((*Count == TEXT("0")) != Stored->IsEmpty()))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("CONTAINER_CONTENTS_STATE_INVALID"),
            SemanticId);
    }
    const FVistaInteractionResult BaseResult =
        AVistaSemanticActor::VistaApplyRuntimeState_Implementation(State);
    if (!BaseResult.IsSuccess())
    {
        return BaseResult;
    }
    bOpen = Open->Equals(TEXT("true"), ESearchCase::CaseSensitive);
    ContainedItemSemanticId = *Stored;
    ContainedItem = ActiveStorageItem.IsValid() &&
            ActiveStorageItem->SemanticId == ContainedItemSemanticId
        ? ActiveStorageItem.Get() : nullptr;
    OnContainerStateChanged(bOpen);
    OnContainerContentsChanged(ContainedItemSemanticId);
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("CONTAINER_STATE_RESTORED"));
}

bool AVistaContainerActor::IsItemAllowed(
    const AVistaPickupActor* Item) const
{
    return IsValid(Item) && !Item->SemanticId.IsEmpty() &&
        (AllowedItemSemanticIds.IsEmpty() ||
         AllowedItemSemanticIds.Contains(Item->SemanticId));
}

bool AVistaContainerActor::ValidateStorageTransferReadOnly(
    const EVistaAffordance Affordance,
    const AActor* Requester,
    const AVistaPickupActor* Item,
    FName& OutCode) const
{
    if (Affordance != EVistaAffordance::Insert &&
        Affordance != EVistaAffordance::Remove)
    {
        OutCode = TEXT("STORAGE_AFFORDANCE_REQUIRED");
        return false;
    }
    if (!HasAuthority() || !IsValid(Requester) || !IsValid(Item) ||
        !IsValid(ContentsAnchor) || Requester->GetWorld() != GetWorld() ||
        Item->GetWorld() != GetWorld() || SemanticId.IsEmpty() ||
        Item->SemanticId.IsEmpty())
    {
        OutCode = !HasAuthority()
            ? FName(TEXT("AUTHORITY_REQUIRED"))
            : FName(TEXT("STORAGE_PARTICIPANT_INVALID"));
        return false;
    }
    if (IsStorageReserved())
    {
        OutCode = TEXT("CONTAINER_TARGET_BUSY");
        return false;
    }
    if (!bOpen)
    {
        OutCode = TEXT("CONTAINER_CLOSED");
        return false;
    }
    if (!IsItemAllowed(Item))
    {
        OutCode = TEXT("CONTAINER_ITEM_NOT_ALLOWED");
        return false;
    }
    if (!Requester->GetClass()->ImplementsInterface(
            UVistaItemCarrier::StaticClass()))
    {
        OutCode = TEXT("CARRIER_REQUIRED");
        return false;
    }
    AActor* InventoryItem = IVistaItemCarrier::Execute_VistaGetHeldItem(
        const_cast<AActor*>(Requester));
    if (Affordance == EVistaAffordance::Insert)
    {
        if (!ContainedItemSemanticId.IsEmpty())
        {
            OutCode = TEXT("CONTAINER_FULL");
            return false;
        }
        if (InventoryItem != Item ||
            Item->GetCarrier() != Requester ||
            Item->GetPhysicalDisposition() != EVistaPickupDisposition::Held)
        {
            OutCode = TEXT("INSERT_ITEM_NOT_EXACTLY_HELD");
            return false;
        }
        OutCode = TEXT("INSERT_TRANSFER_READY");
        return true;
    }
    if (IsValid(InventoryItem))
    {
        OutCode = TEXT("CARRIER_SLOT_UNAVAILABLE");
        return false;
    }
    if (ContainedItemSemanticId != Item->SemanticId ||
        !Item->IsContainedIn(this) ||
        (ContainedItem.IsValid() && ContainedItem.Get() != Item))
    {
        OutCode = TEXT("REMOVE_ITEM_NOT_IN_EXACT_CONTAINER");
        return false;
    }
    OutCode = TEXT("REMOVE_TRANSFER_READY");
    return true;
}

bool AVistaContainerActor::StorageReservationMatches(
    const UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    const AVistaPickupActor* Item,
    const EVistaAffordance Affordance) const
{
    return IsValid(Executor) && !CommandId.IsNone() && IsValid(Item) &&
        (Affordance == EVistaAffordance::Insert ||
         Affordance == EVistaAffordance::Remove) &&
        ActiveTransactionExecutor.Get() == Executor &&
        ActiveTransactionCommandId == CommandId &&
        ActiveStorageItem.Get() == Item &&
        ActiveStorageAffordance == Affordance &&
        Item->IsStorageTransactionReservedBy(
            Executor, CommandId, this);
}

bool AVistaContainerActor::TryReserveStorageTransaction(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    AActor* Requester,
    AVistaPickupActor* Item,
    const EVistaAffordance Affordance,
    FName& OutCode)
{
    if (!ValidateStorageTransferReadOnly(
            Affordance, Requester, Item, OutCode))
    {
        return false;
    }
    if (!TryReserveTransaction(Executor, CommandId))
    {
        OutCode = TEXT("CONTAINER_TARGET_BUSY");
        return false;
    }
    if (!Item->TryReserveStorageTransaction(
            Executor, CommandId, this))
    {
        ActiveTransactionExecutor.Reset();
        ActiveTransactionCommandId = NAME_None;
        OutCode = TEXT("STORAGE_ITEM_BUSY");
        return false;
    }
    ActiveStorageItem = Item;
    ActiveStorageAffordance = Affordance;
    if (!StorageReservationMatches(
            Executor, CommandId, Item, Affordance))
    {
        Item->ReleaseStorageTransactionReservation(
            Executor, CommandId, this);
        ActiveStorageItem.Reset();
        ActiveStorageAffordance = EVistaAffordance::Inspect;
        ActiveTransactionExecutor.Reset();
        ActiveTransactionCommandId = NAME_None;
        OutCode = TEXT("STORAGE_RESERVATION_DIVERGED");
        return false;
    }
    OutCode = TEXT("STORAGE_TARGETS_RESERVED");
    return true;
}

bool AVistaContainerActor::ReleaseStorageTransaction(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    AVistaPickupActor* Item,
    FName& OutCode)
{
    if (!StorageReservationMatches(
            Executor,
            CommandId,
            Item,
            ActiveStorageAffordance))
    {
        OutCode = TEXT("STORAGE_RESERVATION_REQUIRED");
        return false;
    }
#if WITH_DEV_AUTOMATION_TESTS
    if (bFailNextStorageRelease)
    {
        bFailNextStorageRelease = false;
        OutCode = TEXT("STORAGE_RELEASE_FORCED_FAILURE");
        return false;
    }
#endif
    if (!Item->ReleaseStorageTransactionReservation(
            Executor, CommandId, this))
    {
        OutCode = TEXT("STORAGE_ITEM_RELEASE_FAILED");
        return false;
    }
    ActiveStorageItem.Reset();
    ActiveStorageAffordance = EVistaAffordance::Inspect;
    ActiveTransactionExecutor.Reset();
    ActiveTransactionCommandId = NAME_None;
    OutCode = TEXT("STORAGE_TARGETS_RELEASED");
    return true;
}

bool AVistaContainerActor::ReleaseReservationForItemEndPlay(
    AVistaPickupActor* Item,
    UVistaActionExecutorComponent* Executor,
    const FName CommandId)
{
    if (!HasAuthority() || Item == nullptr || Executor == nullptr ||
        CommandId.IsNone() || ActiveTransactionExecutor.Get() != Executor ||
        ActiveTransactionCommandId != CommandId ||
        ActiveStorageItem.Get(true) != Item)
    {
        return false;
    }
    ActiveStorageItem.Reset();
    ActiveStorageAffordance = EVistaAffordance::Inspect;
    ActiveTransactionExecutor.Reset();
    ActiveTransactionCommandId = NAME_None;
    return true;
}

FVistaContainerTransferResult AVistaContainerActor::CommitStorageTransaction(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    AActor* Requester,
    AVistaPickupActor* Item,
    const EVistaAffordance Affordance)
{
    FVistaContainerTransferResult Result;
    Result.Affordance = Affordance;
    Result.ItemSemanticId = IsValid(Item) ? Item->SemanticId : FString();
    Result.ContainerSemanticId = SemanticId;
    if (!StorageReservationMatches(
            Executor, CommandId, Item, Affordance) ||
        !HasAuthority() || !IsValid(Requester) || !IsValid(ContentsAnchor))
    {
        Result.Code = TEXT("STORAGE_RESERVATION_REQUIRED");
        return Result;
    }
    Result.ItemBefore =
        IVistaInteractable::Execute_VistaGetRuntimeState(Item);
    Result.ContainerBefore = VistaGetRuntimeState_Implementation();
    FName ItemCode;
    if (!Item->CaptureStorageTransactionState(
            Requester,
            this,
            Affordance,
            Result.ItemPhysicalBefore,
            ItemCode))
    {
        Result.Code = ItemCode.IsNone()
            ? FName(TEXT("STORAGE_CONTACT_STATE_DRIFT")) : ItemCode;
        return Result;
    }

    if (Affordance == EVistaAffordance::Insert)
    {
        if (!ContainedItemSemanticId.IsEmpty())
        {
            Result.Code = TEXT("CONTAINER_FULL");
            return Result;
        }
        const FVistaInteractionResult ItemCommit =
            Item->CommitStorageInsert(
                Executor,
                CommandId,
                Requester,
                this,
                ContentsAnchor);
        if (!ItemCommit.IsSuccess())
        {
            Result.Code = ItemCommit.Code;
            return Result;
        }
        Result.bItemMutationCommitted = true;
        ContainedItemSemanticId = Item->SemanticId;
        ContainedItem = Item;
        Result.bContainerMutationCommitted = true;
        OnContainerContentsChanged(ContainedItemSemanticId);
        ForceNetUpdate();
    }
    else if (Affordance == EVistaAffordance::Remove)
    {
        if (ContainedItemSemanticId != Item->SemanticId ||
            !Item->IsContainedIn(this))
        {
            Result.Code = TEXT("REMOVE_ITEM_NOT_IN_EXACT_CONTAINER");
            return Result;
        }
        const FString PreviousItemSemanticId = ContainedItemSemanticId;
        TWeakObjectPtr<AVistaPickupActor> PreviousItem = ContainedItem;
        ContainedItemSemanticId.Reset();
        ContainedItem.Reset();
        Result.bContainerMutationCommitted = true;
        OnContainerContentsChanged(ContainedItemSemanticId);
        ForceNetUpdate();
        const FVistaInteractionResult ItemCommit =
            Item->CommitStorageRemove(
                Executor, CommandId, Requester, this);
        if (!ItemCommit.IsSuccess())
        {
            ContainedItemSemanticId = PreviousItemSemanticId;
            ContainedItem = PreviousItem.IsValid()
                ? PreviousItem.Get() : Item;
            Result.bContainerMutationCommitted = false;
            OnContainerContentsChanged(ContainedItemSemanticId);
            ForceNetUpdate();
            Result.Code = ItemCommit.Code;
            return Result;
        }
        Result.bItemMutationCommitted = true;
    }
    else
    {
        Result.Code = TEXT("STORAGE_AFFORDANCE_REQUIRED");
        return Result;
    }

    Result.ItemAfter =
        IVistaInteractable::Execute_VistaGetRuntimeState(Item);
    Result.ContainerAfter = VistaGetRuntimeState_Implementation();
    FName AfterCode;
    if (!Item->CaptureStorageTransactionState(
            Requester,
            this,
            Affordance == EVistaAffordance::Insert
                ? EVistaAffordance::Remove
                : EVistaAffordance::Insert,
            Result.ItemPhysicalAfter,
            AfterCode))
    {
        Result.Code = TEXT("STORAGE_CONTACT_EVIDENCE_INVALID");
        return Result;
    }
    const bool bEffectMatches = Affordance == EVistaAffordance::Insert
        ? ContainedItemSemanticId == Item->SemanticId &&
            Item->IsContainedIn(this)
        : ContainedItemSemanticId.IsEmpty() &&
            Item->GetCarrier() == Requester &&
            Item->GetPhysicalDisposition() == EVistaPickupDisposition::Held;
    if (!Result.bItemMutationCommitted ||
        !Result.bContainerMutationCommitted || !bEffectMatches)
    {
        Result.Code = TEXT("STORAGE_CONTACT_EVIDENCE_INVALID");
        return Result;
    }
    Result.bSucceeded = true;
    Result.Code = Affordance == EVistaAffordance::Insert
        ? FName(TEXT("ITEM_INSERTED"))
        : FName(TEXT("ITEM_REMOVED"));
    return Result;
}

void AVistaContainerActor::ReleaseActiveStorageReservationForEndPlay()
{
    if (!HasAuthority())
    {
        return;
    }
    UVistaActionExecutorComponent* Executor =
        ActiveTransactionExecutor.Get();
    const FName CommandId = ActiveTransactionCommandId;
    AVistaPickupActor* Item = ActiveStorageItem.Get();
    if (Executor != nullptr && !CommandId.IsNone() && Item != nullptr &&
        Item->IsStorageTransactionReservedBy(Executor, CommandId, this))
    {
        Item->ReleaseStorageReservationForContainerEndPlay(
            this, Executor, CommandId);
    }
    if (ActiveTransactionExecutor.Get() == Executor &&
        ActiveTransactionCommandId == CommandId)
    {
        ActiveStorageItem.Reset();
        ActiveStorageAffordance = EVistaAffordance::Inspect;
        ActiveTransactionExecutor.Reset();
        ActiveTransactionCommandId = NAME_None;
    }
}

FVistaInteractionResult AVistaContainerActor::RestoreBaselineStateForEvent(
    const FVistaEntityRuntimeState& State)
{
    if (!HasAuthority() || IsStorageReserved() ||
        (!State.SemanticId.IsEmpty() && State.SemanticId != SemanticId))
    {
        return FVistaInteractionResult::Failure(
            IsStorageReserved()
                ? EVistaInteractionStatus::Busy
                : EVistaInteractionStatus::Rejected,
            IsStorageReserved()
                ? FName(TEXT("CONTAINER_TARGET_RESERVED"))
                : FName(TEXT("CONTAINER_BASELINE_INVALID")),
            SemanticId);
    }
    const FString* Open = State.Values.Find(TEXT("open"));
    const FString* Stored = State.Values.Find(TEXT("contained_item"));
    const FString* Count = State.Values.Find(TEXT("contents_count"));
    const FString* Capacity = State.Values.Find(TEXT("storage_capacity"));
    if (Open == nullptr || Stored == nullptr || Count == nullptr ||
        Capacity == nullptr ||
        (!Open->Equals(TEXT("true"), ESearchCase::CaseSensitive) &&
         !Open->Equals(TEXT("false"), ESearchCase::CaseSensitive)) ||
        *Capacity != TEXT("1") ||
        (*Count != TEXT("0") && *Count != TEXT("1")) ||
        ((*Count == TEXT("0")) != Stored->IsEmpty()))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("CONTAINER_BASELINE_CONTENTS_INVALID"),
            SemanticId);
    }
    AVistaPickupActor* ResolvedItem = nullptr;
    if (!Stored->IsEmpty())
    {
        for (TActorIterator<AVistaPickupActor> It(GetWorld()); It; ++It)
        {
            if (It->SemanticId != *Stored)
            {
                continue;
            }
            if (ResolvedItem != nullptr)
            {
                return FVistaInteractionResult::Failure(
                    EVistaInteractionStatus::InvalidState,
                    TEXT("CONTAINER_BASELINE_ITEM_AMBIGUOUS"),
                    SemanticId);
            }
            ResolvedItem = *It;
        }
        if (ResolvedItem == nullptr)
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("CONTAINER_BASELINE_ITEM_NOT_FOUND"),
            SemanticId);
        }
    }
    const FVistaInteractionResult Base =
        AVistaSemanticActor::VistaApplyRuntimeState_Implementation(State);
    if (!Base.IsSuccess())
    {
        return Base;
    }
    bOpen = Open->Equals(TEXT("true"), ESearchCase::CaseSensitive);
    ContainedItemSemanticId = *Stored;
    ContainedItem = ResolvedItem;
    OnContainerStateChanged(bOpen);
    OnContainerContentsChanged(ContainedItemSemanticId);
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("CONTAINER_BASELINE_RESTORED"));
}

#if WITH_DEV_AUTOMATION_TESTS
bool AVistaContainerActor::IsStorageReservedForDevAutomation(
    const UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    const AVistaPickupActor* Item) const
{
    return StorageReservationMatches(
        Executor, CommandId, Item, ActiveStorageAffordance);
}

void AVistaContainerActor::FailNextStorageReleaseForDevAutomation()
{
    bFailNextStorageRelease = true;
}

bool AVistaContainerActor::ReleaseStorageForDevAutomation(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    AVistaPickupActor* Item,
    FName& OutCode)
{
    return ReleaseStorageTransaction(
        Executor, CommandId, Item, OutCode);
}

void AVistaContainerActor::
    ReleaseStorageReservationForEndPlayForDevAutomation()
{
    ReleaseActiveStorageReservationForEndPlay();
}
#endif
