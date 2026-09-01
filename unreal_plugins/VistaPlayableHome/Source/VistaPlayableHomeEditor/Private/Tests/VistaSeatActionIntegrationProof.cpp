#if WITH_DEV_AUTOMATION_TESTS

#include "Components/ActorTestSpawner.h"
#include "GameFramework/Character.h"
#include "Misc/AutomationTest.h"
#include "VistaActionExecutorComponent.h"
#include "VistaEventSubsystem.h"
#include "VistaInteractable.h"
#include "VistaPlayableHomeRuntimeSubsystem.h"
#include "VistaPostureComponent.h"
#include "VistaSeatActor.h"

namespace
{
UVistaPostureComponent& AddPosture(
    AActor& Owner,
    const FString& SemanticId)
{
    UVistaPostureComponent* Posture =
        NewObject<UVistaPostureComponent>(&Owner, TEXT("ProofPosture"));
    Owner.AddInstanceComponent(Posture);
    Posture->OccupantSemanticId = SemanticId;
    Posture->RegisterComponent();
    return *Posture;
}

UVistaActionExecutorComponent& AddExecutor(AActor& Owner)
{
    UVistaActionExecutorComponent* Executor =
        NewObject<UVistaActionExecutorComponent>(&Owner, TEXT("ProofExecutor"));
    Owner.AddInstanceComponent(Executor);
    Executor->RegisterComponent();
    return *Executor;
}

FVistaSemanticActionRequest PostureRequest(
    const FName CommandId,
    AActor& Requester,
    AVistaSeatActor& Seat,
    const EVistaAffordance Affordance,
    const int32 SessionGeneration = 0,
    const bool bCommitSessionGeneration = false)
{
    FVistaSemanticActionRequest Request;
    Request.CommandId = CommandId;
    Request.Requester = &Requester;
    Request.Target = &Seat;
    Request.RequesterSemanticId = TEXT("home.r16/entity.proof_occupant");
    Request.TargetSemanticId = Seat.SemanticId;
    Request.Affordance = Affordance;
    Request.SessionGeneration = SessionGeneration;
    Request.bCommitSessionGenerationOnSuccess = bCommitSessionGeneration;
    Request.TimeoutSeconds = 10.0f;
    return Request;
}

bool StateValueEquals(
    const FVistaEntityRuntimeState& State,
    const FName Key,
    const FString& Expected)
{
    const FString* Value = State.Values.Find(Key);
    return Value != nullptr && *Value == Expected;
}
} // namespace

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FVistaSeatActionIntegrationProof,
    "VISTA.PlayableHome.SeatPosture.ActionExecutorIntegration",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FVistaSeatActionIntegrationProof::RunTest(const FString& Parameters)
{
    static_cast<void>(Parameters);
    FActorTestSpawner Spawner;
    UWorld& World = Spawner.GetWorld();
    if (!IsValid(World.GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>()))
    {
        AddError(TEXT("transient world did not initialize the action ledger"));
        return false;
    }

    AVistaSeatActor& Seat = Spawner.SpawnActor<AVistaSeatActor>();
    Seat.SemanticId = TEXT("home.r16/seat.proof_chair");
    Seat.SetActorLocation(FVector(120.0, 0.0, 0.0));

    ACharacter& Occupant = Spawner.SpawnActor<ACharacter>();
    Occupant.Tags.AddUnique(
        FName(TEXT("VistaSemanticId=home.r16/entity.proof_occupant")));
    Occupant.SetActorLocation(FVector::ZeroVector);
    const FTransform StandingTransform = Occupant.GetActorTransform();
    UVistaPostureComponent& Posture = AddPosture(
        Occupant,
        TEXT("home.r16/entity.proof_occupant"));
    UVistaActionExecutorComponent& Executor = AddExecutor(Occupant);

    FVistaActionTransactionRecord BeginRecord;
    TestTrue(
        TEXT("sit enters the shared semantic executor"),
        Executor.BeginSemanticInteractionForDevAutomation(
            PostureRequest(
                TEXT("r16-sit-success"),
                Occupant,
                Seat,
                EVistaAffordance::Sit),
            BeginRecord));
    TestFalse(
        TEXT("sit has no occupancy mutation before its typed completion"),
        Seat.IsOccupied());

    FVistaActionTransactionRecord SitRecord;
    TestTrue(
        TEXT("sit completion succeeds through the shared executor"),
        Executor.DriveSemanticInteractionForDevAutomation(false, SitRecord));
    TestTrue(
        TEXT("sit terminal receipt proves one contact mutation"),
        SitRecord.Status == EVistaActionTransactionStatus::Succeeded &&
            SitRecord.bContactCommitted &&
            SitRecord.StateMutationCount == 1 &&
            SitRecord.bTargetReservationAcquired &&
            SitRecord.bTargetReservationReleased);
    TestTrue(
        TEXT("sit terminal state owns occupancy and seated-loop authority"),
        Seat.IsOccupiedBy(
            &Occupant,
            TEXT("home.r16/entity.proof_occupant")) &&
            Posture.IsSeatedLoopAuthorized());
    TestTrue(
        TEXT("sit receipt observes occupied=true"),
        StateValueEquals(
            SitRecord.AfterState,
            TEXT("occupied"),
            TEXT("true")));

    TestTrue(
        TEXT("stand enters the same shared semantic executor"),
        Executor.BeginSemanticInteractionForDevAutomation(
            PostureRequest(
                TEXT("r16-stand-success"),
                Occupant,
                Seat,
                EVistaAffordance::Stand),
            BeginRecord));
    FVistaActionTransactionRecord StandRecord;
    TestTrue(
        TEXT("stand completion succeeds through the shared executor"),
        Executor.DriveSemanticInteractionForDevAutomation(false, StandRecord));
    TestTrue(
        TEXT("stand terminal receipt commits vacancy exactly once"),
        StandRecord.Status == EVistaActionTransactionStatus::Succeeded &&
            StandRecord.bContactCommitted &&
            StandRecord.StateMutationCount == 1 &&
            StandRecord.bTargetReservationReleased &&
            !Seat.IsOccupied() &&
            Posture.GetPostureState() == EVistaPostureState::Standing);
    TestTrue(
        TEXT("stand restores the exact pre-sit requester transform"),
        Occupant.GetActorTransform().Equals(StandingTransform, 0.01f));

    TestTrue(
        TEXT("rollback sit enters the shared semantic executor"),
        Executor.BeginSemanticInteractionForDevAutomation(
            PostureRequest(
                TEXT("r16-sit-rollback"),
                Occupant,
                Seat,
                EVistaAffordance::Sit),
            BeginRecord));
    FVistaActionTransactionRecord SitRollback;
    TestTrue(
        TEXT("post-contact sit failure compensates successfully"),
        Executor.DriveSemanticInteractionForDevAutomation(true, SitRollback));
    TestTrue(
        TEXT("sit compensation restores standing and vacancy"),
        SitRollback.Status == EVistaActionTransactionStatus::Failed &&
            SitRollback.bRollbackAttempted && SitRollback.bRolledBack &&
            SitRollback.bTargetReservationReleased &&
            !Seat.IsOccupied() &&
            Posture.GetPostureState() == EVistaPostureState::Standing &&
            Occupant.GetActorTransform().Equals(StandingTransform, 0.01f));

    TestTrue(
        TEXT("setup sit for stand rollback succeeds"),
        Executor.BeginSemanticInteractionForDevAutomation(
            PostureRequest(
                TEXT("r16-sit-before-stand-rollback"),
                Occupant,
                Seat,
                EVistaAffordance::Sit),
            BeginRecord));
    TestTrue(
        TEXT("setup sit reaches seated authority"),
        Executor.DriveSemanticInteractionForDevAutomation(false, SitRecord));
    const FTransform SeatedTransform = Occupant.GetActorTransform();
    TestTrue(
        TEXT("rollback stand enters the shared semantic executor"),
        Executor.BeginSemanticInteractionForDevAutomation(
            PostureRequest(
                TEXT("r16-stand-rollback"),
                Occupant,
                Seat,
                EVistaAffordance::Stand),
            BeginRecord));
    FVistaActionTransactionRecord StandRollback;
    TestTrue(
        TEXT("post-contact stand failure compensates successfully"),
        Executor.DriveSemanticInteractionForDevAutomation(
            true,
            StandRollback));
    TestTrue(
        TEXT("stand compensation restores occupancy and seated loop"),
        StandRollback.Status == EVistaActionTransactionStatus::Failed &&
            StandRollback.bRollbackAttempted && StandRollback.bRolledBack &&
            StandRollback.bTargetReservationReleased &&
            Seat.IsOccupiedBy(
                &Occupant,
                TEXT("home.r16/entity.proof_occupant")) &&
            Posture.IsSeatedLoopAuthorized() &&
            Occupant.GetActorTransform().Equals(SeatedTransform, 0.01f));

    UVistaEventSubsystem* Events = World.GetSubsystem<UVistaEventSubsystem>();
    TestNotNull(TEXT("event subsystem is available"), Events);
    if (IsValid(Events))
    {
        Events->InitializeWorldRevision(TEXT("r16-proof"));
        TestTrue(
            TEXT("atomic stand enters the shared semantic executor"),
            Executor.BeginSemanticInteractionForDevAutomation(
                PostureRequest(
                    TEXT("r16-stand-atomic-generation"),
                    Occupant,
                    Seat,
                    EVistaAffordance::Stand,
                    0,
                    true),
                BeginRecord));
        FVistaActionTransactionRecord AtomicStand;
        TestTrue(
            TEXT("terminal publication atomically commits stand and generation"),
            Executor.DriveSemanticInteractionForDevAutomation(
                false,
                AtomicStand));
        TestTrue(
            TEXT("atomic terminal receipt and event generation agree"),
            AtomicStand.Status == EVistaActionTransactionStatus::Succeeded &&
                AtomicStand.SessionGeneration == 1 &&
                Events->GetSessionGeneration() == 1 &&
                Posture.GetPostureState() == EVistaPostureState::Standing &&
                !Seat.IsOccupied());

        TestFalse(
            TEXT("stale generation terminal publication fails closed"),
            Executor.BeginSemanticInteractionForDevAutomation(
                PostureRequest(
                    TEXT("r16-sit-stale-generation"),
                    Occupant,
                    Seat,
                    EVistaAffordance::Sit,
                    0,
                    true),
                BeginRecord) &&
                Executor.DriveSemanticInteractionForDevAutomation(
                    false,
                    SitRollback));
        TestTrue(
            TEXT("stale terminal failure compensates posture without advancing generation"),
            SitRollback.Status == EVistaActionTransactionStatus::Failed &&
                SitRollback.Code ==
                    FName(TEXT("SESSION_GENERATION_COMMIT_FAILED")) &&
                SitRollback.bRollbackAttempted && SitRollback.bRolledBack &&
                SitRollback.bTargetReservationReleased &&
                Events->GetSessionGeneration() == 1 &&
                Posture.GetPostureState() == EVistaPostureState::Standing &&
                !Seat.IsOccupied() &&
                Occupant.GetActorTransform().Equals(
                    StandingTransform,
                    0.01f));
    }

    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
