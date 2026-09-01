#if WITH_DEV_AUTOMATION_TESTS

#include "Components/ActorTestSpawner.h"
#include "Components/SceneComponent.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/AutomationTest.h"
#include "UObject/UObjectGlobals.h"
#include "VistaInteractable.h"
#include "VistaPostureComponent.h"
#include "VistaSeatActor.h"

namespace
{
UVistaPostureComponent& AddPosture(
    AActor& Owner,
    const TCHAR* ComponentName,
    const FString& SemanticId)
{
    UVistaPostureComponent* Posture =
        NewObject<UVistaPostureComponent>(&Owner, FName(ComponentName));
    Owner.AddInstanceComponent(Posture);
    Posture->OccupantSemanticId = SemanticId;
    Posture->RegisterComponent();
    return *Posture;
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
    FVistaSeatPostureCoreProof,
    "VISTA.PlayableHome.SeatPosture.CoreTransactions",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FVistaSeatPostureCoreProof::RunTest(const FString& Parameters)
{
    static_cast<void>(Parameters);
    FActorTestSpawner Spawner;

    AVistaSeatActor& Seat = Spawner.SpawnActor<AVistaSeatActor>();
    Seat.SemanticId = TEXT("home.r1/seat.proof_chair");
    Seat.SetActorLocation(FVector(400.0, 100.0, 45.0));
    Seat.SeatTarget->SetRelativeLocation(FVector(0.0, 0.0, 5.0));

    AActor& StandingParent = Spawner.SpawnActor<AActor>();
    USceneComponent* StandingParentRoot =
        NewObject<USceneComponent>(&StandingParent, TEXT("StandingParentRoot"));
    StandingParent.AddInstanceComponent(StandingParentRoot);
    TestTrue(
        TEXT("standing parent root is accepted"),
        StandingParent.SetRootComponent(StandingParentRoot));
    StandingParentRoot->RegisterComponent();
    StandingParent.SetActorTransform(FTransform(
        FRotator(0.0, 15.0, 0.0),
        FVector(100.0, -80.0, 0.0),
        FVector::OneVector));

    ACharacter& Occupant = Spawner.SpawnActor<ACharacter>();
    Occupant.SetActorTransform(FTransform(
        FRotator(0.0, 25.0, 0.0),
        FVector(160.0, -20.0, 90.0),
        FVector::OneVector));
    TestTrue(
        TEXT("standing attachment is authored before the transaction"),
        Occupant.GetRootComponent()->AttachToComponent(
            StandingParentRoot,
            FAttachmentTransformRules::KeepWorldTransform,
            TEXT("ProofStandingSocket")));
    UCharacterMovementComponent* Movement = Occupant.GetCharacterMovement();
    Movement->SetMovementMode(MOVE_Flying);
    Movement->Velocity = FVector(11.0, 22.0, 33.0);
    Movement->Activate(true);
    const FTransform OriginalWorld = Occupant.GetActorTransform();
    const FTransform OriginalRelative =
        Occupant.GetRootComponent()->GetRelativeTransform();

    UVistaPostureComponent& Posture = AddPosture(
        Occupant,
        TEXT("ProofPosture"),
        TEXT("home.r1/occupant.proof_player"));

    ACharacter& Competitor = Spawner.SpawnActor<ACharacter>();
    UVistaPostureComponent& CompetingPosture = AddPosture(
        Competitor,
        TEXT("CompetingPosture"),
        TEXT("home.r1/occupant.proof_competitor"));

    const FVistaPostureTransitionResult SitBegin =
        Posture.BeginSitTransition(&Seat, TEXT("proof-sit-1"));
    TestTrue(TEXT("sit begin reserves the authored target"), SitBegin.bSucceeded);
    TestEqual(
        TEXT("sit begin enters SittingTransition"),
        Posture.GetPostureState(),
        EVistaPostureState::SittingTransition);
    TestTrue(TEXT("seat is reserved before sit completion"), Seat.IsReserved());
    TestFalse(TEXT("reservation is not occupancy"), Seat.IsOccupied());
    TestFalse(
        TEXT("seated loop is forbidden during SittingTransition"),
        Posture.IsSeatedLoopAuthorized());
    TestFalse(
        TEXT("movement is disabled during sit alignment"),
        Movement->IsActive());
    TestTrue(
        TEXT("standing snapshot captures the attachment parent"),
        Posture.GetStandingSnapshot().bHasAttachmentParent &&
            Posture.GetStandingSnapshot().AttachmentParent == StandingParentRoot &&
            Posture.GetStandingSnapshot().AttachmentSocketName ==
                FName(TEXT("ProofStandingSocket")));
    TestTrue(
        TEXT("standing snapshot captures movement and transform"),
        Posture.GetStandingSnapshot().bMovementComponentActive &&
            Posture.GetStandingSnapshot().MovementVelocity.Equals(
                FVector(11.0, 22.0, 33.0)) &&
            Posture.GetStandingSnapshot().WorldTransform.Equals(OriginalWorld));

    const FVistaPostureTransitionResult CompetingBegin =
        CompetingPosture.BeginSitTransition(&Seat, TEXT("proof-sit-competing"));
    TestFalse(
        TEXT("a second occupant cannot steal a reservation"),
        CompetingBegin.bSucceeded);
    TestEqual(
        TEXT("reservation conflict has a typed code"),
        CompetingBegin.Code,
        FName(TEXT("SEAT_RESERVED")));

    const FVistaPostureTransitionResult WrongCompletion =
        Posture.CommitSitAtCompletion(TEXT("proof-wrong-command"));
    TestFalse(
        TEXT("wrong sit completion command fails closed"),
        WrongCompletion.bSucceeded);
    TestFalse(
        TEXT("wrong completion leaves occupancy uncommitted"),
        Seat.IsOccupied());

    const FVistaPostureTransitionResult SitCommit =
        Posture.CommitSitAtCompletion(TEXT("proof-sit-1"));
    TestTrue(
        TEXT("vista_sit_completed commits occupancy"),
        SitCommit.bSucceeded);
    TestEqual(
        TEXT("sit completion enters Seated"),
        Posture.GetPostureState(),
        EVistaPostureState::Seated);
    TestTrue(TEXT("seat is occupied only after completion"), Seat.IsOccupied());
    TestTrue(
        TEXT("occupied_by is authoritative"),
        Seat.IsOccupiedBy(&Occupant, Posture.OccupantSemanticId));
    TestFalse(TEXT("completed occupancy clears reservation"), Seat.IsReserved());
    TestTrue(
        TEXT("Seated posture authorizes the seated idle loop"),
        Posture.IsSeatedLoopAuthorized());
    TestTrue(
        TEXT("seated snapshot captures seat attachment and stopped movement"),
        Posture.GetSeatedSnapshot().AttachmentParent == Seat.SeatTarget &&
            !Posture.GetSeatedSnapshot().bMovementComponentActive);
    const FVistaEntityRuntimeState OccupiedState =
        IVistaInteractable::Execute_VistaGetRuntimeState(&Seat);
    TestTrue(
        TEXT("seat observation exposes occupied=true"),
        StateValueEquals(OccupiedState, TEXT("occupied"), TEXT("true")));
    TestTrue(
        TEXT("seat observation exposes occupied_by"),
        StateValueEquals(
            OccupiedState,
            TEXT("occupied_by"),
            Posture.OccupantSemanticId));

    const FVistaPostureTransitionResult StandBegin =
        Posture.BeginStandTransition(TEXT("proof-stand-rollback"));
    TestTrue(TEXT("stand begin reserves the occupied seat"), StandBegin.bSucceeded);
    TestEqual(
        TEXT("stand begin enters StandingTransition"),
        Posture.GetPostureState(),
        EVistaPostureState::StandingTransition);
    TestTrue(TEXT("seat stays occupied during stand animation"), Seat.IsOccupied());
    TestFalse(
        TEXT("seated loop stops during StandingTransition"),
        Posture.IsSeatedLoopAuthorized());

    Occupant.DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
    Occupant.SetActorLocation(FVector(-900.0, 700.0, 300.0));
    const FVistaPostureTransitionResult StandRollback =
        Posture.RollbackStandTransition(TEXT("proof-stand-rollback"));
    TestTrue(
        TEXT("failed stand restores the exact seated state"),
        StandRollback.bSucceeded && StandRollback.bRolledBack);
    TestEqual(
        TEXT("stand rollback returns to Seated"),
        Posture.GetPostureState(),
        EVistaPostureState::Seated);
    TestTrue(
        TEXT("stand rollback restores seat attachment"),
        Occupant.GetRootComponent()->GetAttachParent() == Seat.SeatTarget);
    TestTrue(
        TEXT("stand rollback preserves authoritative occupancy"),
        Seat.IsOccupiedBy(&Occupant, Posture.OccupantSemanticId));
    TestTrue(
        TEXT("stand rollback restores seated loop authority"),
        Posture.IsSeatedLoopAuthorized());

    TestTrue(
        TEXT("second stand transition begins"),
        Posture.BeginStandTransition(TEXT("proof-stand-success")).bSucceeded);
    const FVistaPostureTransitionResult StandCommit =
        Posture.CommitStandAtCompletion(TEXT("proof-stand-success"));
    TestTrue(
        TEXT("vista_stand_completed commits vacancy"),
        StandCommit.bSucceeded);
    TestEqual(
        TEXT("stand completion enters Standing"),
        Posture.GetPostureState(),
        EVistaPostureState::Standing);
    TestFalse(TEXT("stand completion vacates seat"), Seat.IsOccupied());
    TestFalse(TEXT("stand completion clears reservation"), Seat.IsReserved());
    TestTrue(
        TEXT("stand completion restores standing attachment"),
        Occupant.GetRootComponent()->GetAttachParent() == StandingParentRoot &&
            Occupant.GetRootComponent()->GetAttachSocketName() ==
                FName(TEXT("ProofStandingSocket")) &&
            Occupant.GetRootComponent()->GetRelativeTransform().Equals(
                OriginalRelative));
    TestTrue(
        TEXT("stand completion restores standing transform and movement"),
        Occupant.GetActorTransform().Equals(OriginalWorld) &&
            Movement->IsActive() && Movement->MovementMode == MOVE_Flying &&
            Movement->Velocity.Equals(FVector(11.0, 22.0, 33.0)));

    TestTrue(
        TEXT("stand retains exact seated evidence until terminal finalize"),
             Posture.HasCommittedStandForDevAutomation());
    TestTrue(TEXT("terminal finalize closes committed stand evidence"),
             Posture.FinalizeCommittedStandForDevAutomation(TEXT("proof-stand-success")).bSucceeded);

    TestTrue(TEXT("a fresh sit transition can begin after vacancy"),
        Posture.BeginSitTransition(&Seat, TEXT("proof-sit-rollback")).bSucceeded);
    Occupant.SetActorLocation(FVector(800.0, 800.0, 800.0));
    const FVistaPostureTransitionResult SitRollback =
        Posture.RollbackSitTransition(TEXT("proof-sit-rollback"));
    TestTrue(
        TEXT("sit cancellation restores the standing snapshot"),
        SitRollback.bSucceeded && SitRollback.bRolledBack);
    TestTrue(
        TEXT("sit cancellation restores exact standing physical state"),
        Occupant.GetActorTransform().Equals(OriginalWorld) &&
            Occupant.GetRootComponent()->GetAttachParent() == StandingParentRoot &&
            Movement->IsActive() &&
            Movement->Velocity.Equals(FVector(11.0, 22.0, 33.0)));
    TestFalse(TEXT("sit cancellation releases seat"), Seat.IsReserved());

    FVistaEntityRuntimeState ForgedOccupancy =
        IVistaInteractable::Execute_VistaGetRuntimeState(&Seat);
    ForgedOccupancy.Values.Add(TEXT("occupied"), TEXT("true"));
    ForgedOccupancy.Values.Add(
        TEXT("occupied_by"),
        TEXT("home.r1/occupant.forged"));
    const FVistaInteractionResult ForgedResult =
        IVistaInteractable::Execute_VistaApplyRuntimeState(
            &Seat,
            ForgedOccupancy);
    TestFalse(
        TEXT("out-of-band occupancy mutation fails closed"),
        ForgedResult.IsSuccess());
    TestEqual(
        TEXT("forged occupancy has a typed authority code"),
        ForgedResult.Code,
        FName(TEXT("SEAT_OCCUPANCY_AUTHORITY_REQUIRED")));
    TestFalse(TEXT("forged occupancy leaves seat free"), Seat.IsOccupied());

    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
