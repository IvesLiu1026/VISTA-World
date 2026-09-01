#if WITH_DEV_AUTOMATION_TESTS

#include "Components/ActorTestSpawner.h"
#include "Misc/AutomationTest.h"
#include "Tests/VistaR5MultiClientProofActors.h"
#include "VistaActionExecutorComponent.h"
#include "VistaContainerActor.h"
#include "VistaInteractable.h"
#include "VistaItemCarrier.h"
#include "VistaPickupActor.h"

namespace
{
const FName ProofRevision(TEXT("vista_playable_home_r1"));
const FString CarrierSemanticId(
    TEXT("home.r19/room.kitchen/entity.storage_carrier"));
const FString SecondCarrierSemanticId(
    TEXT("home.r19/room.kitchen/entity.storage_carrier_02"));
const FString ItemSemanticId(
    TEXT("home.r19/room.kitchen/entity.storage_item"));
const FString SecondItemSemanticId(
    TEXT("home.r19/room.kitchen/entity.storage_item_02"));
const FString ContainerSemanticId(
    TEXT("home.r19/room.kitchen/entity.fridge"));
const FString SecondContainerSemanticId(
    TEXT("home.r19/room.kitchen/entity.cabinet"));

void ConfigurePickup(
    AVistaPickupActor& Item,
    const FString& SemanticId,
    const FVector& Location)
{
    Item.SemanticId = SemanticId;
    Item.WorldRevision = ProofRevision;
    Item.Tags.AddUnique(FName(*SemanticId));
    Item.Tags.AddUnique(FName(*(
        FString(TEXT("VistaSemanticId=")) + SemanticId)));
    Item.Mesh->SetEnableGravity(false);
    Item.SetActorLocation(Location);
}

void ConfigureContainer(
    AVistaContainerActor& Container,
    const FString& SemanticId = ContainerSemanticId)
{
    Container.SemanticId = SemanticId;
    Container.WorldRevision = ProofRevision;
    Container.Tags.AddUnique(FName(*SemanticId));
    Container.Tags.AddUnique(FName(*(
        FString(TEXT("VistaSemanticId=")) + SemanticId)));
    Container.SetActorLocation(FVector(120.0f, 0.0f, 0.0f));
}

bool SetContainerOpen(AVistaContainerActor& Container, const bool bOpen)
{
    FVistaEntityRuntimeState State =
        IVistaInteractable::Execute_VistaGetRuntimeState(&Container);
    State.Values.Add(TEXT("open"), bOpen ? TEXT("true") : TEXT("false"));
    return IVistaInteractable::Execute_VistaApplyRuntimeState(
               &Container,
               State)
        .IsSuccess();
}

FVistaPhysicalActionRequest PickupRequest(
    const FName CommandId,
    AVistaR5ProofCarrier& Carrier,
    AVistaPickupActor& Item)
{
    FVistaPhysicalActionRequest Request;
    Request.CommandId = CommandId;
    Request.Requester = &Carrier;
    Request.Target = &Item;
    Request.RequesterSemanticId = Carrier.SemanticId;
    Request.TargetSemanticId = Item.SemanticId;
    Request.Affordance = EVistaAffordance::PickUp;
    Request.ExpectedRevision = ProofRevision;
    Request.TimeoutSeconds = 10.0f;
    return Request;
}

FVistaSemanticActionRequest ContainerRequest(
    const FName CommandId,
    AVistaR5ProofCarrier& Carrier,
    AVistaContainerActor& Container,
    const EVistaAffordance Affordance)
{
    FVistaSemanticActionRequest Request;
    Request.CommandId = CommandId;
    Request.Requester = &Carrier;
    Request.Target = &Container;
    Request.RequesterSemanticId = Carrier.SemanticId;
    Request.TargetSemanticId = Container.SemanticId;
    Request.Affordance = Affordance;
    Request.ExpectedRevision = ProofRevision;
    Request.TimeoutSeconds = 10.0f;
    return Request;
}

FVistaSemanticActionRequest StorageRequest(
    const FName CommandId,
    AVistaR5ProofCarrier& Carrier,
    AVistaPickupActor& Item,
    AVistaContainerActor& Container,
    const EVistaAffordance Affordance)
{
    FVistaSemanticActionRequest Request;
    Request.CommandId = CommandId;
    Request.Requester = &Carrier;
    Request.Target = &Item;
    Request.SecondaryTarget = &Container;
    Request.RequesterSemanticId = Carrier.SemanticId;
    Request.TargetSemanticId = Item.SemanticId;
    Request.SecondaryTargetSemanticId = Container.SemanticId;
    Request.Affordance = Affordance;
    Request.ExpectedRevision = ProofRevision;
    Request.TimeoutSeconds = 10.0f;
    return Request;
}

bool DriveSemantic(
    UVistaActionExecutorComponent& Executor,
    const FVistaSemanticActionRequest& Request,
    const bool bFailAfterContact,
    FVistaActionTransactionRecord& OutRecord)
{
    FVistaActionTransactionRecord Begin;
    return Executor.BeginSemanticInteractionForDevAutomation(Request, Begin) &&
        Executor.DriveSemanticInteractionForDevAutomation(
            bFailAfterContact,
            OutRecord);
}

bool IsHeldBy(
    AVistaPickupActor& Item,
    AVistaR5ProofCarrier& Carrier)
{
    return Item.GetPhysicalDisposition() == EVistaPickupDisposition::Held &&
        Item.GetCarrier() == &Carrier &&
        IVistaItemCarrier::Execute_VistaGetHeldItem(&Carrier) == &Item &&
        Item.GetContainedInSemanticId().IsEmpty();
}

bool IsContainedBy(
    AVistaPickupActor& Item,
    AVistaContainerActor& Container,
    AVistaR5ProofCarrier& Carrier)
{
    return Item.GetPhysicalDisposition() ==
               EVistaPickupDisposition::Contained &&
        Item.IsContainedIn(&Container) &&
        Container.GetContainedItemSemanticId() == Item.SemanticId &&
        !IsValid(IVistaItemCarrier::Execute_VistaGetHeldItem(&Carrier));
}
} // namespace

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FVistaContainerTransactionR19Proof,
    "VISTA.PlayableHome.ContainerTransactionsR19.AtomicInsertRemove",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FVistaContainerTransactionR19Proof::RunTest(
    const FString& Parameters)
{
    static_cast<void>(Parameters);
    FActorTestSpawner Spawner;

    AVistaR5ProofCarrier& Carrier =
        Spawner.SpawnActor<AVistaR5ProofCarrier>();
    Carrier.ConfigureProofIdentity(CarrierSemanticId);
    Carrier.WorldRevision = ProofRevision;
    Carrier.SetActorLocation(FVector::ZeroVector);

    AVistaR5ProofCarrier& SecondCarrier =
        Spawner.SpawnActor<AVistaR5ProofCarrier>();
    SecondCarrier.ConfigureProofIdentity(SecondCarrierSemanticId);
    SecondCarrier.WorldRevision = ProofRevision;
    SecondCarrier.SetActorLocation(FVector(0.0f, 40.0f, 0.0f));

    AVistaPickupActor& Item = Spawner.SpawnActor<AVistaPickupActor>();
    ConfigurePickup(Item, ItemSemanticId, FVector(40.0f, 0.0f, 0.0f));
    AVistaPickupActor& SecondItem =
        Spawner.SpawnActor<AVistaPickupActor>();
    ConfigurePickup(
        SecondItem,
        SecondItemSemanticId,
        FVector(45.0f, 30.0f, 0.0f));

    AVistaContainerActor& Container =
        Spawner.SpawnActor<AVistaContainerActor>();
    ConfigureContainer(Container);
    TestTrue(TEXT("container opens for the chain"),
             SetContainerOpen(Container, true));

    UVistaActionExecutorComponent* Executor = Carrier.GetProofExecutor();
    UVistaActionExecutorComponent* SecondExecutor =
        SecondCarrier.GetProofExecutor();
    if (!IsValid(Executor) || !IsValid(SecondExecutor))
    {
        AddError(TEXT("proof carriers did not create action executors"));
        return false;
    }

    FVistaActionTransactionRecord Begin;
    FVistaActionTransactionRecord Pickup;
    TestTrue(
        TEXT("exact item pickup begins"),
        Executor->BeginPhysicalInteractionForDevAutomation(
            PickupRequest(TEXT("r19-pickup-item"), Carrier, Item), Begin));
    TestTrue(
        TEXT("exact item pickup commits"),
        Executor->DrivePhysicalInteractionForDevAutomation(false, Pickup));
    TestTrue(TEXT("item is exactly held"), IsHeldBy(Item, Carrier));

    const FVistaSemanticActionRequest Insert = StorageRequest(
        TEXT("r19-insert-success"),
        Carrier,
        Item,
        Container,
        EVistaAffordance::Insert);
    const FVistaSemanticActionRequest WrongContainerIdentity = [&]()
    {
        FVistaSemanticActionRequest Request = Insert;
        Request.SecondaryTargetSemanticId =
            TEXT("home.r19/room.kitchen/entity.wrong_container");
        return Request;
    }();
    TestNotEqual(
        TEXT("exact container identity changes the canonical command"),
        UVistaActionExecutorComponent::CanonicalSemanticRequestHex(Insert),
        UVistaActionExecutorComponent::CanonicalSemanticRequestHex(
            WrongContainerIdentity));

    FVistaActionTransactionRecord InsertSuccess;
    TestTrue(
        TEXT("insert runs through the shared semantic executor"),
        DriveSemantic(*Executor, Insert, false, InsertSuccess));
    TestTrue(
        TEXT("insert commits one physical and two semantic states"),
        InsertSuccess.Status == EVistaActionTransactionStatus::Succeeded &&
            InsertSuccess.StateMutationCount == 2 &&
            InsertSuccess.PhysicalMutationCount == 1 &&
            InsertSuccess.bTargetReservationReleased &&
            InsertSuccess.bSecondaryTargetReservationReleased &&
            InsertSuccess.TargetSemanticId == ItemSemanticId &&
            InsertSuccess.SecondaryTargetSemanticId == ContainerSemanticId &&
            IsContainedBy(Item, Container, Carrier));

    FVistaActionTransactionRecord Close;
    TestTrue(
        TEXT("chain closes the same container"),
        DriveSemantic(
            *Executor,
            ContainerRequest(
                TEXT("r19-close"),
                Carrier,
                Container,
                EVistaAffordance::Close),
            false,
            Close));
    TestFalse(TEXT("container is closed"), Container.IsOpen());
    FVistaActionTransactionRecord Open;
    TestTrue(
        TEXT("chain reopens the same container"),
        DriveSemantic(
            *Executor,
            ContainerRequest(
                TEXT("r19-open"),
                Carrier,
                Container,
                EVistaAffordance::Open),
            false,
            Open));
    TestTrue(TEXT("container is open"), Container.IsOpen());

    FVistaActionTransactionRecord RemoveSuccess;
    TestTrue(
        TEXT("remove runs through the same executor"),
        DriveSemantic(
            *Executor,
            StorageRequest(
                TEXT("r19-remove-success"),
                Carrier,
                Item,
                Container,
                EVistaAffordance::Remove),
            false,
            RemoveSuccess));
    TestTrue(
        TEXT("remove restores exact carrier ownership"),
        RemoveSuccess.Status == EVistaActionTransactionStatus::Succeeded &&
            RemoveSuccess.StateMutationCount == 2 &&
            RemoveSuccess.PhysicalMutationCount == 1 &&
            RemoveSuccess.bTargetReservationReleased &&
            RemoveSuccess.bSecondaryTargetReservationReleased &&
            Container.GetContainedItemSemanticId().IsEmpty() &&
            IsHeldBy(Item, Carrier));

    FVistaActionTransactionRecord InsertRollback;
    TestTrue(
        TEXT("forced post-contact insert failure rolls back"),
        DriveSemantic(
            *Executor,
            StorageRequest(
                TEXT("r19-insert-rollback"),
                Carrier,
                Item,
                Container,
                EVistaAffordance::Insert),
            true,
            InsertRollback));
    TestTrue(
        TEXT("insert rollback restores item, inventory and container"),
        InsertRollback.Status == EVistaActionTransactionStatus::Failed &&
            InsertRollback.bRollbackAttempted &&
            InsertRollback.bRolledBack &&
            InsertRollback.RollbackCode == TEXT("STORAGE_STATES_RESTORED") &&
            InsertRollback.bTargetReservationReleased &&
            InsertRollback.bSecondaryTargetReservationReleased &&
            Container.GetContainedItemSemanticId().IsEmpty() &&
            IsHeldBy(Item, Carrier));

    FVistaActionTransactionRecord InsertAgain;
    TestTrue(
        TEXT("item inserts again for remove rollback"),
        DriveSemantic(
            *Executor,
            StorageRequest(
                TEXT("r19-insert-before-remove-rollback"),
                Carrier,
                Item,
                Container,
                EVistaAffordance::Insert),
            false,
            InsertAgain));
    FVistaActionTransactionRecord RemoveRollback;
    TestTrue(
        TEXT("forced post-contact remove failure rolls back"),
        DriveSemantic(
            *Executor,
            StorageRequest(
                TEXT("r19-remove-rollback"),
                Carrier,
                Item,
                Container,
                EVistaAffordance::Remove),
            true,
            RemoveRollback));
    TestTrue(
        TEXT("remove rollback restores contained attachment and empty inventory"),
        RemoveRollback.Status == EVistaActionTransactionStatus::Failed &&
            RemoveRollback.bRollbackAttempted &&
            RemoveRollback.bRolledBack &&
            RemoveRollback.RollbackCode == TEXT("STORAGE_STATES_RESTORED") &&
            IsContainedBy(Item, Container, Carrier));

    FVistaActionTransactionRecord BusyBegin;
    TestTrue(
        TEXT("first remove reserves exact item and container"),
        Executor->BeginSemanticInteractionForDevAutomation(
            StorageRequest(
                TEXT("r19-remove-reserved"),
                Carrier,
                Item,
                Container,
                EVistaAffordance::Remove),
            BusyBegin));
    FVistaActionTransactionRecord BusyRejected;
    TestFalse(
        TEXT("second executor cannot reserve the same tuple"),
        SecondExecutor->BeginSemanticInteractionForDevAutomation(
            StorageRequest(
                TEXT("r19-remove-reservation-conflict"),
                SecondCarrier,
                Item,
                Container,
                EVistaAffordance::Remove),
            BusyRejected));
    TestEqual(
        TEXT("reservation conflict is typed"),
        BusyRejected.Code,
        FName(TEXT("CONTAINER_TARGET_BUSY")));
    FName ReleaseCode;
    Container.FailNextStorageReleaseForDevAutomation();
    TestFalse(
        TEXT("release failure retains the exact reservation tuple"),
        Container.ReleaseStorageForDevAutomation(
            Executor,
            FName(TEXT("r19-remove-reserved")),
            &Item,
            ReleaseCode));
    TestEqual(
        TEXT("release failure is typed"),
        ReleaseCode,
        FName(TEXT("STORAGE_RELEASE_FORCED_FAILURE")));
    TestTrue(
        TEXT("both reservation halves remain retryable"),
        Container.IsStorageReservedForDevAutomation(
            Executor,
            FName(TEXT("r19-remove-reserved")),
            &Item) &&
            Item.IsReservedForDevAutomation(
                Executor,
                FName(TEXT("r19-remove-reserved"))));
    TestTrue(
        TEXT("release retry clears both halves atomically"),
        Container.ReleaseStorageForDevAutomation(
            Executor,
            FName(TEXT("r19-remove-reserved")),
            &Item,
            ReleaseCode) &&
            ReleaseCode == TEXT("STORAGE_TARGETS_RELEASED") &&
            !Container.IsStorageReservedForDevAutomation(
                Executor,
                FName(TEXT("r19-remove-reserved")),
                &Item) &&
            !Item.IsReservedForDevAutomation(
                Executor,
                FName(TEXT("r19-remove-reserved"))));
    TestTrue(
        TEXT("executor cancellation converges after external release retry"),
        Executor->CancelActiveAction(TEXT("R19_PROOF_CANCEL")));

    FVistaActionTransactionRecord FinalRemove;
    TestTrue(
        TEXT("item removes for closed and allowlist gates"),
        DriveSemantic(
            *Executor,
            StorageRequest(
                TEXT("r19-remove-final"),
                Carrier,
                Item,
                Container,
                EVistaAffordance::Remove),
            false,
            FinalRemove));
    TestTrue(TEXT("container closes for rejection proof"),
             SetContainerOpen(Container, false));
    FVistaActionTransactionRecord ClosedRejected;
    TestFalse(
        TEXT("closed container rejects before mutation"),
        Executor->BeginSemanticInteractionForDevAutomation(
            StorageRequest(
                TEXT("r19-insert-closed"),
                Carrier,
                Item,
                Container,
                EVistaAffordance::Insert),
            ClosedRejected));
    TestEqual(
        TEXT("closed rejection is typed"),
        ClosedRejected.Code,
        FName(TEXT("CONTAINER_CLOSED")));

    TestTrue(TEXT("container reopens for allowlist proof"),
             SetContainerOpen(Container, true));
    Container.AllowedItemSemanticIds = {SecondItemSemanticId};
    FVistaActionTransactionRecord WrongItemRejected;
    TestFalse(
        TEXT("wrong item rejects before mutation"),
        Executor->BeginSemanticInteractionForDevAutomation(
            StorageRequest(
                TEXT("r19-insert-wrong-item"),
                Carrier,
                Item,
                Container,
                EVistaAffordance::Insert),
            WrongItemRejected));
    TestEqual(
        TEXT("wrong-item rejection is typed"),
        WrongItemRejected.Code,
        FName(TEXT("CONTAINER_ITEM_NOT_ALLOWED")));

    Container.AllowedItemSemanticIds.Reset();
    FVistaActionTransactionRecord FillContainer;
    TestTrue(
        TEXT("first item fills the one-slot container"),
        DriveSemantic(
            *Executor,
            StorageRequest(
                TEXT("r19-insert-fill"),
                Carrier,
                Item,
                Container,
                EVistaAffordance::Insert),
            false,
            FillContainer));
    FVistaActionTransactionRecord SecondPickup;
    TestTrue(
        TEXT("second item pickup begins"),
        Executor->BeginPhysicalInteractionForDevAutomation(
            PickupRequest(
                TEXT("r19-pickup-second-item"),
                Carrier,
                SecondItem),
            Begin));
    TestTrue(
        TEXT("second item pickup commits"),
        Executor->DrivePhysicalInteractionForDevAutomation(
            false,
            SecondPickup));
    FVistaActionTransactionRecord FullRejected;
    TestFalse(
        TEXT("full container rejects second exact held item"),
        Executor->BeginSemanticInteractionForDevAutomation(
            StorageRequest(
                TEXT("r19-insert-full"),
                Carrier,
                SecondItem,
                Container,
                EVistaAffordance::Insert),
            FullRejected));
    TestEqual(
        TEXT("full rejection is typed"),
        FullRejected.Code,
        FName(TEXT("CONTAINER_FULL")));

    const FName ContainerEndPlayCommand(TEXT("r19-container-endplay"));
    FVistaActionTransactionRecord ContainerEndPlayBegin;
    TestTrue(
        TEXT("container EndPlay proof reserves the exact stored item"),
        SecondExecutor->BeginSemanticInteractionForDevAutomation(
            StorageRequest(
                ContainerEndPlayCommand,
                SecondCarrier,
                Item,
                Container,
                EVistaAffordance::Remove),
            ContainerEndPlayBegin));
    TestTrue(TEXT("container destruction begins"), Container.Destroy());
    Container.ReleaseStorageReservationForEndPlayForDevAutomation();
    TestFalse(
        TEXT("container EndPlay releases the item half"),
        Item.IsReservedForDevAutomation(
            SecondExecutor,
            ContainerEndPlayCommand));
    TestTrue(
        TEXT("container EndPlay action can terminate without a leaked tuple"),
        SecondExecutor->CancelActiveAction(TEXT("R19_CONTAINER_ENDPLAY")));

    AVistaContainerActor& SecondContainer =
        Spawner.SpawnActor<AVistaContainerActor>();
    ConfigureContainer(SecondContainer, SecondContainerSemanticId);
    TestTrue(TEXT("second container opens for item EndPlay proof"),
             SetContainerOpen(SecondContainer, true));
    const FName ItemEndPlayCommand(TEXT("r19-item-endplay"));
    FVistaActionTransactionRecord ItemEndPlayBegin;
    TestTrue(
        TEXT("item EndPlay proof reserves the exact open container"),
        Executor->BeginSemanticInteractionForDevAutomation(
            StorageRequest(
                ItemEndPlayCommand,
                Carrier,
                SecondItem,
                SecondContainer,
                EVistaAffordance::Insert),
            ItemEndPlayBegin));
    TestTrue(TEXT("item destruction begins"), SecondItem.Destroy());
    SecondItem.ReleaseStorageReservationForEndPlayForDevAutomation();
    TestFalse(
        TEXT("item EndPlay releases the container half"),
        SecondContainer.IsStorageReserved());
    TestTrue(
        TEXT("item EndPlay action can terminate without a leaked tuple"),
        Executor->CancelActiveAction(TEXT("R19_ITEM_ENDPLAY")));
    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
