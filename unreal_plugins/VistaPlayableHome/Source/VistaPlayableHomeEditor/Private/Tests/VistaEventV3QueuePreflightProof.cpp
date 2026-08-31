#if WITH_DEV_AUTOMATION_TESTS

#include "Components/ActorTestSpawner.h"
#include "Misc/AutomationTest.h"
#include "VistaEventDefinitionActor.h"
#include "VistaEventSubsystem.h"
#include "VistaHomeNpcCharacter.h"
#include "VistaHomeNpcController.h"
#include "VistaInteractable.h"
#include "VistaPlayableHomeRuntimeSubsystem.h"
#include "VistaSemanticPropActor.h"

namespace {
const FName ProofRevision(TEXT("vista_playable_home_r1"));
const FName ProofEventId(TEXT("mmg_001"));
const FString ProofNpcId(TEXT("home.r1/room.living/entity.resident.01"));
const FString ProofTargetId(TEXT("home.r1/room.living/entity.proof_object.01"));

bool RuntimeStatesExactlyMatch(const FVistaEntityRuntimeState &Left,
                               const FVistaEntityRuntimeState &Right) {
  if (Left.SemanticId != Right.SemanticId ||
      !Left.Transform.Equals(Right.Transform, 0.0f) ||
      Left.bHidden != Right.bHidden || Left.bPortable != Right.bPortable ||
      Left.Values.Num() != Right.Values.Num()) {
    return false;
  }
  for (const TPair<FName, FString> &Pair : Left.Values) {
    const FString *Value = Right.Values.Find(Pair.Key);
    if (Value == nullptr || *Value != Pair.Value) {
      return false;
    }
  }
  return true;
}

bool ActionResultsExactlyMatch(const FVistaNpcActionResult &Left,
                               const FVistaNpcActionResult &Right) {
  return Left.ActionId == Right.ActionId && Left.Status == Right.Status &&
         Left.Code == Right.Code &&
         Left.TargetSemanticId == Right.TargetSemanticId;
}

struct FReadOnlySnapshot final {
  FName WorldRevision = NAME_None;
  int32 SessionGeneration = 0;
  FName ActiveEventId = NAME_None;
  EVistaEventStatus EventStatus = EVistaEventStatus::Inactive;
  FString PublicGoal;
  FName TerminalConditionId = NAME_None;
  int32 QueuedActionCount = 0;
  FVistaNpcActionResult CurrentAction;
  FString NpcRoomId;
  FVistaEntityRuntimeState TargetState;
};

FReadOnlySnapshot Snapshot(const UVistaEventSubsystem &Events,
                           const AVistaHomeNpcController &Controller,
                           const AVistaHomeNpcCharacter &Npc,
                           AVistaSemanticPropActor &Target) {
  FReadOnlySnapshot Result;
  Result.WorldRevision = Events.GetWorldRevision();
  Result.SessionGeneration = Events.GetSessionGeneration();
  Result.ActiveEventId = Events.GetActiveEventId();
  Result.EventStatus = Events.GetEventStatus();
  Result.PublicGoal = Events.GetPublicGoal();
  Result.TerminalConditionId = Events.GetTerminalConditionId();
  Result.QueuedActionCount = Controller.GetQueuedActionCount();
  Result.CurrentAction = Controller.GetCurrentActionResult();
  Result.NpcRoomId = Npc.CurrentRoomId;
  Result.TargetState =
      IVistaInteractable::Execute_VistaGetRuntimeState(&Target);
  return Result;
}

bool SnapshotsExactlyMatch(const FReadOnlySnapshot &Left,
                           const FReadOnlySnapshot &Right) {
  return Left.WorldRevision == Right.WorldRevision &&
         Left.SessionGeneration == Right.SessionGeneration &&
         Left.ActiveEventId == Right.ActiveEventId &&
         Left.EventStatus == Right.EventStatus &&
         Left.PublicGoal == Right.PublicGoal &&
         Left.TerminalConditionId == Right.TerminalConditionId &&
         Left.QueuedActionCount == Right.QueuedActionCount &&
         ActionResultsExactlyMatch(Left.CurrentAction, Right.CurrentAction) &&
         Left.NpcRoomId == Right.NpcRoomId &&
         RuntimeStatesExactlyMatch(Left.TargetState, Right.TargetState);
}

FVistaNpcAction InspectAction(const FName ActionId, const FString &TargetId) {
  FVistaNpcAction Action;
  Action.ActionId = ActionId;
  Action.Type = EVistaNpcActionType::Inspect;
  Action.TargetSemanticId = TargetId;
  Action.TimeoutSeconds = 20.0f;
  return Action;
}

FVistaLiveNpcQueuePreflightCommand
PreflightCommand(const FName CommandId, const int32 Generation,
                 const TArray<FVistaNpcAction> &Actions) {
  FVistaLiveNpcQueuePreflightCommand Command;
  Command.Envelope.CommandId = CommandId;
  Command.Envelope.ExpectedRevision = ProofRevision;
  Command.Envelope.SessionGeneration = Generation;
  Command.EventId = ProofEventId;
  Command.EventContentDigest = FString::ChrN(64, TEXT('a'));
  Command.SidecarContentDigest = FString::ChrN(64, TEXT('b'));
  Command.QueueId = TEXT("op.04");
  Command.NpcSemanticId = ProofNpcId;
  Command.bReplace = true;
  Command.Actions = Actions;
  return Command;
}

FVistaLiveNpcQueueCommand
CommitCommand(const FName CommandId, const int32 Generation,
              const TArray<FVistaNpcAction> &Actions) {
  FVistaLiveNpcQueueCommand Command;
  Command.Envelope.CommandId = CommandId;
  Command.Envelope.ExpectedRevision = ProofRevision;
  Command.Envelope.SessionGeneration = Generation;
  Command.NpcSemanticId = ProofNpcId;
  Command.bReplace = true;
  Command.Actions = Actions;
  return Command;
}
} // namespace

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FVistaEventV3QueuePreflightProof,
    "VISTA.PlayableHome.EventV3.QueuePreflightReadOnly",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FVistaEventV3QueuePreflightProof::RunTest(const FString &Parameters) {
  static_cast<void>(Parameters);
  FActorTestSpawner Spawner;
  UWorld &World = Spawner.GetWorld();
  UVistaEventSubsystem *Events = World.GetSubsystem<UVistaEventSubsystem>();
  UVistaPlayableHomeRuntimeSubsystem *Runtime =
      World.GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>();
  if (!IsValid(Events) || !IsValid(Runtime)) {
    AddError(TEXT("transient world did not create required subsystems"));
    return false;
  }
  Events->InitializeWorldRevision(ProofRevision);

  FVistaEventDefinition Definition;
  Definition.EventId = ProofEventId;
  Definition.CompatibleRevision = ProofRevision;
  Definition.PublicTitle = TEXT("Queue preflight proof");
  Definition.PublicGoal = TEXT("Prove read-only queue feasibility");
  Definition.TimeoutSeconds = 300.0f;
  FVistaEventCondition Success;
  Success.ConditionId = TEXT("proof_elapsed");
  Success.Type = EVistaEventConditionType::Elapsed;
  Success.Operator = EVistaEventConditionOperator::Gte;
  Success.Seconds = 299.0f;
  Definition.SuccessConditions.Add(Success);
  FName RegistrationCode;
  TArray<FVistaEventDefinition> ProofDefinitions;
  ProofDefinitions.Add(Definition);
  TestTrue(
      TEXT("proof event registers in the runtime subsystem"),
      Events->RegisterEventDefinitions(ProofDefinitions, RegistrationCode));
  TestEqual(TEXT("proof event registration is typed"), RegistrationCode,
            FName(TEXT("EVENTS_REGISTERED")));
  AVistaEventDefinitionActor &DefinitionActor =
      Spawner.SpawnActor<AVistaEventDefinitionActor>();
  DefinitionActor.Definitions.Add(Definition);

  AVistaHomeNpcCharacter &Npc = Spawner.SpawnActor<AVistaHomeNpcCharacter>();
  Npc.SemanticId = ProofNpcId;
  Npc.CurrentRoomId = TEXT("home.r1/room.living");
  Npc.Tags.AddUnique(FName(*ProofNpcId));
  Npc.Tags.AddUnique(FName(*(FString(TEXT("VistaSemanticId=")) + ProofNpcId)));
  if (!IsValid(Npc.GetController())) {
    Npc.SpawnDefaultController();
  }
  if (!IsValid(Npc.GetController())) {
    AVistaHomeNpcController &SpawnedController =
        Spawner.SpawnActor<AVistaHomeNpcController>();
    SpawnedController.Possess(&Npc);
  }
  AVistaHomeNpcController *Controller =
      Cast<AVistaHomeNpcController>(Npc.GetController());
  if (!IsValid(Controller)) {
    AddError(TEXT("proof NPC did not acquire its typed controller"));
    return false;
  }

  AVistaSemanticPropActor &Target =
      Spawner.SpawnActor<AVistaSemanticPropActor>();
  Target.SemanticId = ProofTargetId;
  Target.Tags.AddUnique(FName(*ProofTargetId));
  Target.Tags.AddUnique(
      FName(*(FString(TEXT("VistaSemanticId=")) + ProofTargetId)));

  const TArray<FVistaNpcAction> ValidActions = {
      InspectAction(TEXT("mmg001.inspect.01"), ProofTargetId)};
  const FReadOnlySnapshot Initial = Snapshot(*Events, *Controller, Npc, Target);

  FVistaLiveNpcQueuePreflightCommand UnknownEvent =
      PreflightCommand(TEXT("vwc-000000000000000000000001"), 0, ValidActions);
  UnknownEvent.EventId = TEXT("mmg_999");
  const FVistaLiveNpcQueuePreflightResult UnknownEventResult =
      Runtime->PreflightNpcQueue(UnknownEvent);
  TestFalse(TEXT("unknown event fails closed"), UnknownEventResult.bSucceeded);
  TestEqual(TEXT("unknown event has typed code"), UnknownEventResult.Code,
            FName(TEXT("EVENT_NOT_REGISTERED")));
  TestTrue(TEXT("unknown-event failure is exactly read-only"),
           SnapshotsExactlyMatch(Initial,
                                 Snapshot(*Events, *Controller, Npc, Target)));

  FVistaLiveNpcQueuePreflightCommand BadDigest =
      PreflightCommand(TEXT("vwc-000000000000000000000002"), 0, ValidActions);
  BadDigest.SidecarContentDigest = FString::ChrN(63, TEXT('b'));
  const FVistaLiveNpcQueuePreflightResult BadDigestResult =
      Runtime->PreflightNpcQueue(BadDigest);
  TestFalse(TEXT("malformed sidecar digest fails closed"),
            BadDigestResult.bSucceeded);
  TestEqual(TEXT("malformed sidecar digest has typed code"),
            BadDigestResult.Code,
            FName(TEXT("SIDECAR_CONTENT_DIGEST_INVALID")));
  TestTrue(TEXT("digest failure is exactly read-only"),
           SnapshotsExactlyMatch(Initial,
                                 Snapshot(*Events, *Controller, Npc, Target)));

  const TArray<FVistaNpcAction> MissingTargetActions = {
      InspectAction(TEXT("mmg001.inspect.missing"),
                    TEXT("home.r1/room.living/entity.absent.01"))};
  const FVistaLiveNpcQueuePreflightResult MissingTargetResult =
      Runtime->PreflightNpcQueue(PreflightCommand(
          TEXT("vwc-000000000000000000000003"), 0, MissingTargetActions));
  TestFalse(TEXT("missing target fails closed"),
            MissingTargetResult.bSucceeded);
  TestEqual(TEXT("missing target has typed code"), MissingTargetResult.Code,
            FName(TEXT("TARGET_NOT_FOUND_OR_AMBIGUOUS")));
  TestTrue(TEXT("missing-target failure is exactly read-only"),
           SnapshotsExactlyMatch(Initial,
                                 Snapshot(*Events, *Controller, Npc, Target)));

  TArray<FVistaNpcAction> DuplicateActions = ValidActions;
  DuplicateActions.Add(ValidActions[0]);
  const FVistaLiveNpcQueuePreflightResult DuplicateResult =
      Runtime->PreflightNpcQueue(PreflightCommand(
          TEXT("vwc-000000000000000000000004"), 0, DuplicateActions));
  TestFalse(TEXT("duplicate action id fails closed"),
            DuplicateResult.bSucceeded);
  TestEqual(TEXT("duplicate action has typed code"), DuplicateResult.Code,
            FName(TEXT("DUPLICATE_ACTION_ID")));
  TestTrue(TEXT("duplicate failure is exactly read-only"),
           SnapshotsExactlyMatch(Initial,
                                 Snapshot(*Events, *Controller, Npc, Target)));

  const FVistaLiveNpcQueuePreflightCommand ValidPreflight =
      PreflightCommand(TEXT("vwc-000000000000000000000005"), 0, ValidActions);
  const FVistaLiveNpcQueuePreflightResult SuccessResult =
      Runtime->PreflightNpcQueue(ValidPreflight);
  TestTrue(TEXT("valid queue preflight succeeds"), SuccessResult.bSucceeded);
  TestEqual(TEXT("preflight success code is exact"), SuccessResult.Code,
            FName(TEXT("QUEUE_PREFLIGHT_OK")));
  TestEqual(TEXT("preflight preserves generation"),
            SuccessResult.SessionGeneration, 0);
  TestEqual(TEXT("preflight echoes exact queue id"), SuccessResult.QueueId,
            FString(TEXT("op.04")));
  TestEqual(TEXT("preflight echoes exact NPC"), SuccessResult.TargetSemanticId,
            ProofNpcId);
  TestEqual(TEXT("preflight action receipt has one id"),
            SuccessResult.ActionIds.Num(), 1);
  TestEqual(TEXT("preflight action receipt preserves order"),
            SuccessResult.ActionIds[0], ValidActions[0].ActionId);
  TestTrue(TEXT("successful preflight is exactly read-only"),
           SnapshotsExactlyMatch(Initial,
                                 Snapshot(*Events, *Controller, Npc, Target)));

  const FVistaLiveNpcQueuePreflightResult ReplayWithoutClaim =
      Runtime->PreflightNpcQueue(ValidPreflight);
  TestTrue(TEXT("same preflight command id is re-evaluated without a claim"),
           ReplayWithoutClaim.bSucceeded);
  TestTrue(TEXT("repeated preflight remains exactly read-only"),
           SnapshotsExactlyMatch(Initial,
                                 Snapshot(*Events, *Controller, Npc, Target)));

  const FVistaLiveCommandResult CommitResult = Runtime->ExecuteNpcQueue(
      CommitCommand(TEXT("vwc-000000000000000000000006"), 0, ValidActions));
  TestTrue(TEXT("unchanged preflight-approved queue is accepted by commit"),
           CommitResult.bSucceeded);
  TestEqual(TEXT("queue commit has exact code"), CommitResult.Code,
            FName(TEXT("QUEUE_REPLACED")));
  TestEqual(TEXT("queue commit advances once"), CommitResult.SessionGeneration,
            1);
  TestEqual(TEXT("queue commit installs one action"),
            Controller->GetQueuedActionCount(), 1);

  Controller->CancelActionQueue(TEXT("PROOF_CLEANUP"));
  const FReadOnlySnapshot BeforeDriftPreflight =
      Snapshot(*Events, *Controller, Npc, Target);
  const FVistaLiveNpcQueuePreflightResult BeforeDriftResult =
      Runtime->PreflightNpcQueue(PreflightCommand(
          TEXT("vwc-000000000000000000000007"), 1, ValidActions));
  TestTrue(TEXT("second-generation preflight succeeds"),
           BeforeDriftResult.bSucceeded);
  TestTrue(TEXT("second-generation preflight is read-only"),
           SnapshotsExactlyMatch(BeforeDriftPreflight,
                                 Snapshot(*Events, *Controller, Npc, Target)));

  int32 DriftedGeneration = 0;
  TestTrue(TEXT("proof advances generation to model external state drift"),
           Events->CommitCommandGeneration(1, DriftedGeneration));
  TestEqual(TEXT("state drift advances to generation two"), DriftedGeneration,
            2);
  const FVistaLiveCommandResult DriftedCommit = Runtime->ExecuteNpcQueue(
      CommitCommand(TEXT("vwc-000000000000000000000008"), 1, ValidActions));
  TestFalse(TEXT("commit may reject after generation drift"),
            DriftedCommit.bSucceeded);
  TestEqual(TEXT("drifted commit has typed code"), DriftedCommit.Code,
            FName(TEXT("SESSION_GENERATION_MISMATCH")));
  TestEqual(TEXT("drifted commit reports authoritative generation"),
            DriftedCommit.SessionGeneration, 2);
  TestEqual(TEXT("drifted commit does not install a queue"),
            Controller->GetQueuedActionCount(), 0);
  return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
