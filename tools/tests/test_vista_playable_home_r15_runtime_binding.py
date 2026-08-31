from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = (
    ROOT
    / "unreal_plugins"
    / "VistaPlayableHome"
    / "Source"
    / "VistaPlayableHome"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_r15_runtime_binding_keeps_the_nine_clip_authority_closed() -> None:
    profile = json.loads(
        _text(
            ROOT
            / "world_packs/vista_playable_home_r1/animation_profiles/"
            "makehuman_cc0_detail_actions_r15.json"
        )
    )
    clips = {clip["clip_id"]: clip for clip in profile["clips"]}
    assert tuple(clips) == (
        "rotary_turn_on_right",
        "rotary_turn_off_right",
        "button_press_right",
        "cabinet_drawer_open_right",
        "cabinet_drawer_close_right",
        "sit_down_chair",
        "seated_idle_loop",
        "stand_up_chair",
        "pour_right",
    )
    assert all(
        clip["runtime_binding"]["runtime_execution_authorized"] is False
        for clip in clips.values()
    )

    animation = _text(RUNTIME / "Private/VistaAnimationComponent.cpp")
    for montage in (
        "AM_VistaCC0RotaryTurnOnRight_R15",
        "AM_VistaCC0RotaryTurnOffRight_R15",
        "AM_VistaCC0ButtonPressRight_R15",
        "AM_VistaCC0CabinetDrawerOpenRight_R15",
        "AM_VistaCC0CabinetDrawerCloseRight_R15",
    ):
        assert montage in animation
    assert "/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/" in animation
    assert "Cast<AVistaStatefulApplianceActor>(Target)" in animation
    assert "ANIMATION_TARGET_PREFLIGHT_DEFERRED" in animation
    assert "Appliance->ControlStyle == EVistaApplianceControlStyle::Button" in animation
    assert "Type == EVistaNpcActionType::Toggle && Appliance->IsActive()" in animation


def test_appliance_and_container_targets_are_authored_not_wire_supplied() -> None:
    appliance_h = _text(RUNTIME / "Public/VistaStatefulApplianceActor.h")
    appliance_cpp = _text(RUNTIME / "Private/VistaStatefulApplianceActor.cpp")
    container_h = _text(RUNTIME / "Public/VistaContainerActor.h")
    container_cpp = _text(RUNTIME / "Private/VistaContainerActor.cpp")
    composer = _text(ROOT / "tools/ue/vista_playable_home/compose_home_commandlet.py")

    assert "EVistaApplianceControlStyle" in appliance_h
    assert "TObjectPtr<USceneComponent> ControlTarget" in appliance_h
    assert 'TEXT("VistaInteractionTarget")' in appliance_cpp
    assert "TObjectPtr<USceneComponent> HandleTarget" in container_h
    assert 'TEXT("VistaInteractionTarget")' in container_cpp
    assert '"control_style": "button"' in composer
    assert '"control_style": "rotary"' in composer
    assert 'actor.get_editor_property("control_target")' in composer
    assert 'actor.get_editor_property("handle_target")' in composer


def test_container_mutation_uses_the_shared_transaction_and_rollback() -> None:
    executor = _text(RUNTIME / "Private/VistaActionExecutorSemantic.cpp")
    container = _text(RUNTIME / "Private/VistaContainerActor.cpp")

    assert "Container->TryReserveTransaction" in executor
    assert "Container->CommitTransactionalInteraction" in executor
    assert "Container->RestoreTransactionalState" in executor
    assert "Container->ReleaseTransaction" in executor
    assert 'TEXT("ACTION_EXECUTOR_REQUIRED")' in container
    assert 'TEXT("CONTAINER_TARGET_RESERVED")' in container
    assert 'TEXT("CONTAINER_STATE_RESTORED")' in container


def test_vista_event_semantics_are_not_rewritten_to_match_the_gesture() -> None:
    expected = {
        "mmg_001": ("turn_off", "entity.stove.01"),
        "mmg_021": ("turn_off", "entity.faucet.01"),
        "mmg_070": ("turn_on", "entity.washer.01"),
    }
    for event_id, (action, target_suffix) in expected.items():
        event = json.loads(
            _text(
                ROOT
                / "world_packs/vista_playable_home_r1/events_v3"
                / f"{event_id}.json"
            )
        )
        queue = event["npc_action_queues"][0]["actions"]
        assert any(
            item["action"] == action
            and item["target_id"].endswith(target_suffix)
            for item in queue
        )

    animation = _text(RUNTIME / "Private/VistaAnimationComponent.cpp")
    assert "MakeHumanCc0ButtonPressMontage" in animation
    assert 'ExpectedCompletionSignal = TEXT("vista_appliance_press_completed")' in animation
    executor = _text(RUNTIME / "Private/VistaActionExecutorSemantic.cpp")
    assert "Events->RecordSuccessfulInteraction(" in executor
    assert "FinalRecord.Affordance" in executor

    npc = _text(RUNTIME / "Private/VistaHomeNpcController.cpp")
    preflight = npc.split("bool AVistaHomeNpcController::ValidateActionTargetReadOnly", 1)[1]
    assert "Animation->HasApprovedMutationAnimation(" in preflight
    assert "Action.Type, Target, OutCode" in preflight
