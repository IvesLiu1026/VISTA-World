#if WITH_DEV_AUTOMATION_TESTS

#include "Components/ActorTestSpawner.h"
#include "Components/SceneComponent.h"
#include "GameFramework/Actor.h"
#include "Misc/AutomationTest.h"
#include "UObject/UObjectGlobals.h"
#include "VistaActionExecutorComponent.h"
#include "VistaAnimationComponent.h"
#include "VistaInteractable.h"
#include "VistaPlayableHomeRuntimeSubsystem.h"
#include "VistaStatefulApplianceActor.h"

namespace
{
bool RuntimeStatesExactlyMatch(
    const FVistaEntityRuntimeState& Left,
    const FVistaEntityRuntimeState& Right)
{
    if (Left.SemanticId != Right.SemanticId ||
        !Left.Transform.Equals(Right.Transform, 0.0f) ||
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

bool StateValueEquals(
    const FVistaEntityRuntimeState& State,
    const FName Key,
    const FString& Expected)
{
    const FString* Value = State.Values.Find(Key);
    return Value != nullptr && *Value == Expected;
}

FVistaEntityRuntimeState PoweredIdleState(
    AVistaStatefulApplianceActor& Appliance)
{
    FVistaEntityRuntimeState State =
        IVistaInteractable::Execute_VistaGetRuntimeState(&Appliance);
    State.Values.Add(TEXT("powered"), TEXT("true"));
    State.Values.Add(TEXT("active"), TEXT("false"));
    State.Values.Add(TEXT("on"), TEXT("false"));
    State.Values.Add(TEXT("status"), TEXT("idle"));
    return State;
}

FVistaSemanticActionRequest PressRequest(
    const FName CommandId,
    AActor& Requester,
    AVistaStatefulApplianceActor& Appliance)
{
    FVistaSemanticActionRequest Request;
    Request.CommandId = CommandId;
    Request.Requester = &Requester;
    Request.Target = &Appliance;
    Request.RequesterSemanticId = TEXT("home.p0/entity.proof_requester");
    Request.TargetSemanticId = Appliance.SemanticId;
    Request.Affordance = EVistaAffordance::Press;
    Request.TimeoutSeconds = 10.0f;
    return Request;
}
} // namespace

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FVistaApplianceActionsP0TransitionProof,
    "VISTA.PlayableHome.ApplianceActionsP0.TransitionContract",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FVistaApplianceActionsP0TransitionProof::RunTest(
    const FString& Parameters)
{
    static_cast<void>(Parameters);
    const FVistaApplianceActivityProfile ActivityProfile;
    const FVistaAppliancePressProfile StartProfile;
    FVistaApplianceState After;
    bool bMutated = false;
    FName Code;

    FVistaApplianceState Off;
    Off.bPowered = false;
    Off.bActive = false;
    Off.Status = TEXT("off");
    TestFalse(
        TEXT("unpowered turn_on fails closed"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Off,
            EVistaAffordance::TurnOn,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("unpowered turn_on has zero mutation"), bMutated);
    TestTrue(TEXT("unpowered turn_on preserves state"), After == Off);
    TestEqual(
        TEXT("unpowered turn_on has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_POWER_REQUIRED")));

    FVistaApplianceState PoweredInactive;
    PoweredInactive.bPowered = true;
    PoweredInactive.bActive = false;
    PoweredInactive.Status = TEXT("idle");
    TestTrue(
        TEXT("turn_on succeeds with external power"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            PoweredInactive,
            EVistaAffordance::TurnOn,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestTrue(TEXT("turn_on mutates once"), bMutated);
    TestTrue(TEXT("turn_on preserves power"), After.bPowered);
    TestTrue(TEXT("turn_on starts activity"), After.bActive);
    TestEqual(
        TEXT("turn_on enters target active status"),
        After.Status,
        FName(TEXT("running")));

    const FVistaApplianceState Running = After;
    TestTrue(
        TEXT("repeated turn_on succeeds"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Running,
            EVistaAffordance::TurnOn,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("repeated turn_on is idempotent"), bMutated);
    TestTrue(TEXT("repeated turn_on preserves exact state"), After == Running);
    TestEqual(
        TEXT("repeated turn_on has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_ALREADY_ACTIVE")));

    TestTrue(
        TEXT("toggle succeeds with power"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            PoweredInactive,
            EVistaAffordance::Toggle,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestTrue(TEXT("toggle mutates active"), After.bActive);
    TestTrue(TEXT("toggle preserves power"), After.bPowered);
    TestEqual(TEXT("toggle preserves status"), After.Status, FName(TEXT("idle")));

    FVistaApplianceState Loaded = PoweredInactive;
    Loaded.Status = TEXT("loaded");
    TestTrue(
        TEXT("washer start press succeeds"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Loaded,
            EVistaAffordance::Press,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestTrue(TEXT("washer start becomes active"), After.bActive);
    TestTrue(TEXT("washer start preserves power"), After.bPowered);
    TestEqual(TEXT("washer start becomes running"), After.Status, FName(TEXT("running")));

    const FVistaApplianceState PressRunning = After;
    TestTrue(
        TEXT("repeated washer start succeeds"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            PressRunning,
            EVistaAffordance::Press,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("repeated washer start is idempotent"), bMutated);
    TestTrue(
        TEXT("repeated washer start preserves exact state"),
        After == PressRunning);
    TestEqual(
        TEXT("repeated press has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_PRESS_ALREADY_APPLIED")));

    TestFalse(
        TEXT("unpowered toggle fails closed"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Off,
            EVistaAffordance::Toggle,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("failed toggle has zero mutation"), bMutated);
    TestTrue(TEXT("failed toggle preserves state"), After == Off);
    TestEqual(
        TEXT("unpowered toggle has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_POWER_REQUIRED")));
    TestFalse(
        TEXT("unpowered washer press fails closed"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Off,
            EVistaAffordance::Press,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("failed press has zero mutation"), bMutated);
    TestTrue(TEXT("failed press preserves state"), After == Off);
    TestEqual(
        TEXT("unpowered washer press has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_POWER_REQUIRED")));

    FVistaAppliancePressProfile NonActivatingPress;
    NonActivatingPress.ControlId = TEXT("cycle_mode");
    NonActivatingPress.bResultActive = false;
    NonActivatingPress.ResultStatus = TEXT("idle");
    TestFalse(
        TEXT("unpowered non-activating press still fails closed"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Off,
            EVistaAffordance::Press,
            ActivityProfile,
            NonActivatingPress,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("unpowered non-activating press has zero mutation"), bMutated);
    TestTrue(
        TEXT("unpowered non-activating press preserves state"),
        After == Off);
    TestEqual(
        TEXT("unpowered non-activating press has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_POWER_REQUIRED")));

    TestTrue(
        TEXT("turn_off succeeds from running"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Running,
            EVistaAffordance::TurnOff,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestTrue(TEXT("turn_off preserves power"), After.bPowered);
    TestFalse(TEXT("turn_off stops activity"), After.bActive);
    TestEqual(TEXT("turn_off enters idle"), After.Status, FName(TEXT("idle")));

    const FVistaApplianceState PoweredOff = After;
    TestTrue(
        TEXT("repeated turn_off succeeds"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            PoweredOff,
            EVistaAffordance::TurnOff,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("repeated turn_off is idempotent"), bMutated);
    TestTrue(
        TEXT("repeated turn_off preserves exact state"),
        After == PoweredOff);
    TestEqual(
        TEXT("repeated turn_off has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_ALREADY_INACTIVE")));

    TestTrue(
        TEXT("unpowered inactive turn_off is idempotent"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Off,
            EVistaAffordance::TurnOff,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("unpowered inactive turn_off has zero mutation"), bMutated);
    TestTrue(TEXT("unpowered inactive turn_off preserves state"), After == Off);

    FVistaApplianceState Inconsistent = Off;
    Inconsistent.bActive = true;
    TestFalse(
        TEXT("active without power fails closed"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Inconsistent,
            EVistaAffordance::TurnOff,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("inconsistent state has zero mutation"), bMutated);
    TestEqual(
        TEXT("inconsistent state has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_STATE_INVALID")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FVistaApplianceActionsP0TransactionProof,
    "VISTA.PlayableHome.ApplianceActionsP0.TransactionReceipt",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FVistaApplianceActionsP0TransactionProof::RunTest(
    const FString& Parameters)
{
    static_cast<void>(Parameters);
    FActorTestSpawner Spawner;
    UWorld& World = Spawner.GetWorld();
    if (!IsValid(World.GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>()))
    {
        AddError(TEXT("transient world did not initialize the action ledger"));
        return false;
    }

    AActor& Requester = Spawner.SpawnActor<AActor>();
    Requester.Tags.AddUnique(
        FName(TEXT("VistaSemanticId=home.p0/entity.proof_requester")));
    USceneComponent* RequesterRoot =
        NewObject<USceneComponent>(&Requester, TEXT("ProofRoot"));
    Requester.AddInstanceComponent(RequesterRoot);
    const bool bRootAccepted = Requester.SetRootComponent(RequesterRoot);
    RequesterRoot->RegisterComponent();
    UVistaAnimationComponent* Animation =
        NewObject<UVistaAnimationComponent>(&Requester, TEXT("ProofAnimation"));
    Requester.AddInstanceComponent(Animation);
    Animation->RegisterComponent();
    UVistaActionExecutorComponent* Executor =
        NewObject<UVistaActionExecutorComponent>(&Requester, TEXT("ProofExecutor"));
    Requester.AddInstanceComponent(Executor);
    Executor->RegisterComponent();

    AVistaStatefulApplianceActor& Appliance =
        Spawner.SpawnActor<AVistaStatefulApplianceActor>();
    Appliance.SemanticId = TEXT("home.p0/entity.proof_washer");
    TestTrue(
        TEXT("proof requester root is registered"),
        bRootAccepted && IsValid(RequesterRoot) &&
            RequesterRoot->IsRegistered());
    TestTrue(
        TEXT("proof animation component is registered"),
        IsValid(Animation) && Animation->IsRegistered());
    TestTrue(
        TEXT("proof executor component is registered"),
        IsValid(Executor) && Executor->IsRegistered());

    const FVistaEntityRuntimeState AuthoredIdle = PoweredIdleState(Appliance);
    const FVistaInteractionResult InitialApply =
        IVistaInteractable::Execute_VistaApplyRuntimeState(
            &Appliance,
            AuthoredIdle);
    if (!InitialApply.IsSuccess())
    {
        AddError(FString::Printf(
            TEXT("could not author proof appliance state: %s"),
            *InitialApply.Code.ToString()));
        return false;
    }
    const FVistaEntityRuntimeState Baseline =
        IVistaInteractable::Execute_VistaGetRuntimeState(&Appliance);

    FVistaEntityRuntimeState AliasConflict = Baseline;
    AliasConflict.Values.Add(TEXT("active"), TEXT("true"));
    AliasConflict.Values.Add(TEXT("on"), TEXT("false"));
    const FVistaInteractionResult ConflictResult =
        IVistaInteractable::Execute_VistaApplyRuntimeState(
            &Appliance,
            AliasConflict);
    TestFalse(TEXT("conflicting active/on aliases fail closed"), ConflictResult.IsSuccess());
    TestEqual(
        TEXT("conflicting active/on aliases have typed code"),
        ConflictResult.Code,
        FName(TEXT("APPLIANCE_ACTIVE_ALIAS_MISMATCH")));
    TestTrue(
        TEXT("alias conflict preserves exact appliance state"),
        RuntimeStatesExactlyMatch(
            Baseline,
            IVistaInteractable::Execute_VistaGetRuntimeState(&Appliance)));

    FVistaActionTransactionRecord BeginRecord;
    TestTrue(
        TEXT("press transaction acquires target reservation"),
        Executor->BeginSemanticInteractionForDevAutomation(
            PressRequest(TEXT("p0-press-success"), Requester, Appliance),
            BeginRecord));
    TestTrue(
        TEXT("press begin receipt records reservation acquired"),
        BeginRecord.bTargetReservationAcquired);
    TestFalse(
        TEXT("press reservation is not released before terminal state"),
        BeginRecord.bTargetReservationReleased);
    TestEqual(
        TEXT("press has zero mutations before contact"),
        BeginRecord.StateMutationCount,
        0);
    TestTrue(
        TEXT("press begin captures exact before state"),
        RuntimeStatesExactlyMatch(Baseline, BeginRecord.BeforeState));
    TestTrue(
        TEXT("press begin does not mutate target"),
        RuntimeStatesExactlyMatch(
            Baseline,
            IVistaInteractable::Execute_VistaGetRuntimeState(&Appliance)));
    FVistaEntityRuntimeState ReservationProbe = Baseline;
    ReservationProbe.Values.Add(TEXT("status"), TEXT("loaded"));
    const FVistaInteractionResult ReservedApply =
        IVistaInteractable::Execute_VistaApplyRuntimeState(
            &Appliance,
            ReservationProbe);
    TestFalse(
        TEXT("press reservation blocks out-of-band mutation"),
        ReservedApply.IsSuccess());
    TestEqual(
        TEXT("reserved target has typed busy code"),
        ReservedApply.Code,
        FName(TEXT("APPLIANCE_TARGET_RESERVED")));
    TestTrue(
        TEXT("rejected out-of-band mutation preserves exact state"),
        RuntimeStatesExactlyMatch(
            Baseline,
            IVistaInteractable::Execute_VistaGetRuntimeState(&Appliance)));

    FVistaActionTransactionRecord SuccessRecord;
    TestTrue(
        TEXT("press reaches contact and succeeds"),
        Executor->DriveSemanticInteractionForDevAutomation(
            false,
            SuccessRecord));
    const FVistaEntityRuntimeState Running =
        IVistaInteractable::Execute_VistaGetRuntimeState(&Appliance);
    TestTrue(
        TEXT("successful press has terminal success status"),
        SuccessRecord.Status == EVistaActionTransactionStatus::Succeeded);
    TestTrue(TEXT("successful press commits contact"), SuccessRecord.bContactCommitted);
    TestEqual(
        TEXT("successful press mutates state exactly once"),
        SuccessRecord.StateMutationCount,
        1);
    TestTrue(
        TEXT("successful press releases target reservation"),
        SuccessRecord.bTargetReservationAcquired &&
            SuccessRecord.bTargetReservationReleased);
    TestTrue(
        TEXT("successful press contact and after states match runtime"),
        RuntimeStatesExactlyMatch(Running, SuccessRecord.ContactState) &&
            RuntimeStatesExactlyMatch(Running, SuccessRecord.AfterState));
    TestTrue(
        TEXT("washer press contact produces active running state"),
        StateValueEquals(Running, TEXT("powered"), TEXT("true")) &&
            StateValueEquals(Running, TEXT("active"), TEXT("true")) &&
            StateValueEquals(Running, TEXT("on"), TEXT("true")) &&
            StateValueEquals(Running, TEXT("status"), TEXT("running")));

    TestTrue(
        TEXT("idempotent press still acquires transaction"),
        Executor->BeginSemanticInteractionForDevAutomation(
            PressRequest(TEXT("p0-press-idempotent"), Requester, Appliance),
            BeginRecord));
    FVistaActionTransactionRecord IdempotentRecord;
    TestTrue(
        TEXT("idempotent press completes transaction"),
        Executor->DriveSemanticInteractionForDevAutomation(
            false,
            IdempotentRecord));
    TestEqual(
        TEXT("idempotent press has zero state mutations"),
        IdempotentRecord.StateMutationCount,
        0);
    TestTrue(
        TEXT("idempotent press preserves exact state"),
        RuntimeStatesExactlyMatch(
            Running,
            IVistaInteractable::Execute_VistaGetRuntimeState(&Appliance)) &&
            RuntimeStatesExactlyMatch(Running, IdempotentRecord.BeforeState) &&
            RuntimeStatesExactlyMatch(Running, IdempotentRecord.ContactState) &&
            RuntimeStatesExactlyMatch(Running, IdempotentRecord.AfterState));
    TestTrue(
        TEXT("idempotent press releases target reservation"),
        IdempotentRecord.bTargetReservationAcquired &&
            IdempotentRecord.bTargetReservationReleased);

    const FVistaInteractionResult ResetResult =
        IVistaInteractable::Execute_VistaApplyRuntimeState(
            &Appliance,
            Baseline);
    if (!ResetResult.IsSuccess())
    {
        AddError(FString::Printf(
            TEXT("could not reset appliance before rollback proof: %s"),
            *ResetResult.Code.ToString()));
        return false;
    }
    TestTrue(
        TEXT("rollback press acquires target reservation"),
        Executor->BeginSemanticInteractionForDevAutomation(
            PressRequest(TEXT("p0-press-rollback"), Requester, Appliance),
            BeginRecord));
    FVistaActionTransactionRecord RollbackRecord;
    TestTrue(
        TEXT("forced post-contact failure completes verified rollback"),
        Executor->DriveSemanticInteractionForDevAutomation(
            true,
            RollbackRecord));
    const FVistaEntityRuntimeState AfterRollback =
        IVistaInteractable::Execute_VistaGetRuntimeState(&Appliance);
    TestTrue(
        TEXT("forced post-contact receipt is failed"),
        RollbackRecord.Status == EVistaActionTransactionStatus::Failed);
    TestEqual(
        TEXT("forced post-contact receipt has exact code"),
        RollbackRecord.Code,
        FName(TEXT("DEV_AUTOMATION_FORCED_POST_CONTACT_FAILURE")));
    TestEqual(
        TEXT("rollback path records one contact mutation"),
        RollbackRecord.StateMutationCount,
        1);
    TestTrue(
        TEXT("rollback receipt proves restore and reservation release"),
        RollbackRecord.bTargetReservationAcquired &&
            RollbackRecord.bTargetReservationReleased &&
            RollbackRecord.bRollbackAttempted && RollbackRecord.bRolledBack);
    TestTrue(
        TEXT("rollback contact captured active running state"),
        StateValueEquals(
            RollbackRecord.ContactState,
            TEXT("active"),
            TEXT("true")) &&
            StateValueEquals(
                RollbackRecord.ContactState,
                TEXT("status"),
                TEXT("running")));
    TestTrue(
        TEXT("rollback restores exact before state"),
        RuntimeStatesExactlyMatch(Baseline, RollbackRecord.BeforeState) &&
            RuntimeStatesExactlyMatch(Baseline, RollbackRecord.AfterState) &&
            RuntimeStatesExactlyMatch(Baseline, AfterRollback));
    const FVistaInteractionResult PostRollbackApply =
        IVistaInteractable::Execute_VistaApplyRuntimeState(
            &Appliance,
            Baseline);
    TestTrue(
        TEXT("rollback release permits a new authoritative state apply"),
        PostRollbackApply.IsSuccess());
    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
