from __future__ import annotations

import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
EXECUTOR_H = PLUGIN / "Public/VistaActionExecutorComponent.h"
EXECUTOR_CPP = PLUGIN / "Private/VistaActionExecutorSemantic.cpp"
CORE_CPP = PLUGIN / "Private/VistaActionExecutorComponent.cpp"
CHARACTER_CPP = PLUGIN / "Private/VistaPlayableHomeCharacter.cpp"
NPC_CPP = PLUGIN / "Private/VistaHomeNpcController.cpp"
RUNTIME_CPP = PLUGIN / "Private/VistaPlayableHomeRuntimeSubsystem.cpp"


def _source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def test_open_close_and_inspect_use_one_animation_gated_executor_contract() -> None:
    header = _source(EXECUTOR_H)
    source = _source(EXECUTOR_CPP)

    assert "FVistaSemanticActionRequest" in header
    assert "BeginSemanticInteraction" in header
    assert "ActiveAction.IsSet() || ActiveSemanticAction.IsSet()" in header
    assert "EVistaAffordance::Open" in source
    assert "EVistaAffordance::Close" in source
    assert "EVistaAffordance::Inspect" in source
    assert "vista.semantic-command/v2" in source
    assert "HasApprovedMutationAnimation" in source
    assert 'FName(TEXT("VistaDoorHandleTarget"))' in source
    assert "ACTION_CONTACT_TARGET_AMBIGUOUS" in source


def test_world_state_mutates_only_after_typed_contact_and_rolls_back_on_failure() -> None:
    source = _source(EXECUTOR_CPP)
    animation = source.split(
        "void UVistaActionExecutorComponent::AdvanceSemanticAnimation", 1
    )[1].split(
        "bool UVistaActionExecutorComponent::CommitSemanticContact", 1
    )[0]
    commit = source.split(
        "bool UVistaActionExecutorComponent::CommitSemanticContact", 1
    )[1].split(
        "void UVistaActionExecutorComponent::CompleteSemanticSuccess", 1
    )[0]
    failure = source.split(
        "void UVistaActionExecutorComponent::FinishSemanticFailure", 1
    )[1].split(
        "bool UVistaActionExecutorComponent::TransitionSemantic", 1
    )[0]

    assert animation.index("ConsumeContactSignal") < animation.index(
        "CommitSemanticContact"
    )
    assert "Execute_VistaInteract(Target, Interaction)" in commit
    assert "bContactMutationAttempted = true" in commit
    assert "StateMatchesSemanticEffect" in commit
    assert "Execute_VistaApplyRuntimeState" in failure
    assert "RuntimeStatesEquivalent" in failure
    assert "ACTION_ROLLBACK_FAILED" in failure


def test_only_terminal_success_records_vista_interaction_once() -> None:
    source = _source(EXECUTOR_CPP)
    complete = source.split(
        "void UVistaActionExecutorComponent::CompleteSemanticSuccess", 1
    )[1].split(
        "void UVistaActionExecutorComponent::FinishSemanticFailure", 1
    )[0]
    failure = source.split(
        "void UVistaActionExecutorComponent::FinishSemanticFailure", 1
    )[1].split(
        "bool UVistaActionExecutorComponent::TransitionSemantic", 1
    )[0]

    assert complete.count("RecordSuccessfulInteraction(") == 1
    assert complete.index("FinalizeSemantic(&FinalRecord)") < complete.index(
        "RecordSuccessfulInteraction("
    )
    assert "RecordSuccessfulInteraction(" not in failure


def test_player_npc_and_tcp_route_open_close_through_shared_executor() -> None:
    character = _source(CHARACTER_CPP)
    npc = _source(NPC_CPP)
    runtime = _source(RUNTIME_CPP)

    assert "BeginSemanticInteraction(Target, Affordance)" in character
    assert "Action.Type == EVistaNpcActionType::OpenDoor" in npc
    assert "ActionExecutorComponent->BeginSemanticInteraction" in npc
    assert "bAnimatedSemantic" in runtime
    assert "Executor->BeginSemanticInteraction" in runtime
    assert "CanonicalSemanticRequestHex" in runtime


def test_physical_and_semantic_transactions_are_mutually_exclusive() -> None:
    header = _source(EXECUTOR_H)
    core = _source(CORE_CPP)
    semantic = _source(EXECUTOR_CPP)

    assert "return ActiveAction.IsSet() || ActiveSemanticAction.IsSet();" in header
    assert "if (HasActiveAction())" in core
    assert "if (HasActiveAction())" in semantic
    assert "if (ActiveSemanticAction.IsSet())" in core
