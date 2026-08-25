"""Author the closed VISTA playable-home V1 montage set inside UE 5.7.3.

Run this with UnrealEditor-Cmd ``-ExecutePythonScript`` rather than the Python
commandlet: IKRetargetBatchOperation presents editor progress UI in UE 5.7.3.
Binary outputs belong to a disposable project and must never be committed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import traceback

import unreal


SCHEMA = "vista.ue-animation-authoring-receipt/v1"
AUTHORING_MODES = ("full", "montages_only")
OUTPUT_ROOT = "/Game/VISTA/Animations/V1"
TARGET_SKELETON = (
    "/Game/Characters/Mannequins/Meshes/SK_Mannequin.SK_Mannequin"
)
SOURCE_MESH = (
    "/Game/Human_Avatar/DefaultCharacter/Characters/Mannequins/Meshes/"
    "SKM_Manny"
)
TARGET_MESH = "/Game/Characters/Mannequins/Meshes/SKM_Manny"
RETARGETER = (
    "/Game/Human_Avatar/DefaultCharacter/Characters/Mannequin_UE4/Rigs/"
    "RTG_UE4Manny_UE5Manny"
)

# (source sequence, output sequence, output montage, interaction contact fraction or None)
ACTION_SPECS = {
    "look_at": (
        "/Game/Human_Avatar/Animation/LiftSet/Lightweight/01/R/"
        "A_Lift_Light_Look_Center_01_R",
        "AS_VistaLookAt",
        "AM_VistaLookAt",
        None,
    ),
    "pickup": (
        "/Game/Human_Avatar/Animation/LiftSet/Lightweight/01/R/"
        "A_Lift_Light_PickUp_50cm_01_R",
        "AS_VistaPickup",
        "AM_VistaPickup",
        0.55,
    ),
    "drop": (
        "/Game/Human_Avatar/Animation/LiftSet/Lightweight/01/R/"
        "A_Lift_Light_PutAside_50cm_01_R",
        "AS_VistaDrop",
        "AM_VistaDrop",
        0.55,
    ),
    "door": (
        "/Game/Human_Avatar/Animation/LiftSet/Lightweight/01/R/"
        "A_Lift_Light_PickUp_100cm_01_R",
        "AS_VistaDoor",
        "AM_VistaDoor",
        0.50,
    ),
    "brace": (
        "/Game/Human_Avatar/Animation/LiftSet/Heavyweight/02/R/"
        "A_Lift_Heavy_PickUp_0cm_02_R",
        "AS_VistaBrace",
        "AM_VistaBrace",
        None,
    ),
    "drag": (
        "/Game/Human_Avatar/Animation/Deliver/AnimSeq_CarrierFrame_Jog_Forward",
        "AS_VistaDrag",
        "AM_VistaDrag",
        None,
    ),
    "lift_foot": (
        "/Game/Characters/Mannequins/Animations/Manny/MM_Jump",
        "AS_VistaLiftFoot",
        "AM_VistaLiftFoot",
        None,
    ),
    "pause": (
        "/Game/Characters/Mannequins/Animations/Manny/MM_Idle",
        "AS_VistaPause",
        "AM_VistaPause",
        None,
    ),
    "fall": (
        "/Game/Characters/Mannequins/Animations/Manny/MM_Fall_Loop",
        "AS_VistaFall",
        "AM_VistaFall",
        None,
    ),
    "recover": (
        "/Game/Characters/Mannequins/Animations/Manny/MM_Land",
        "AS_VistaRecover",
        "AM_VistaRecover",
        None,
    ),
}

CONTACT_SIGNALS = {
    "pickup": "vista_pickup_contact",
    "drop": "vista_drop_release",
    "door": "vista_door_handle_contact",
}

COMPLETION_SIGNALS = {
    "look_at": "vista_look_at_completed",
    "pickup": "vista_pickup_completed",
    "drop": "vista_drop_completed",
    "door": "vista_door_completed",
    "brace": "vista_brace_contact_verified",
    "drag": "vista_drag_distance_reached",
    "lift_foot": "vista_lift_foot_contact_verified",
    "pause": "vista_pause_completed",
    "fall": "vista_fall_landed",
    "recover": "vista_recover_aligned",
}


def _package_path(asset: object) -> str:
    return asset.get_path_name().split(".", 1)[0]


def _load(path: str, expected_class: str) -> object:
    asset = unreal.load_asset(path)
    if asset is None:
        raise RuntimeError(f"asset did not load: {path}")
    actual_class = asset.get_class().get_name()
    if actual_class != expected_class:
        raise RuntimeError(
            f"asset class mismatch for {path}: {actual_class} != {expected_class}"
        )
    return asset


def _delete_if_present(path: str) -> None:
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        if not unreal.EditorAssetLibrary.delete_asset(path):
            raise RuntimeError(f"could not delete prior output: {path}")


def _retarget(source_path: str, output_path: str) -> object:
    source = unreal.EditorAssetLibrary.find_asset_data(source_path)
    if not source.is_valid():
        raise RuntimeError(f"source asset data missing: {source_path}")
    source_mesh = _load(SOURCE_MESH, "SkeletalMesh")
    target_mesh = _load(TARGET_MESH, "SkeletalMesh")
    retargeter = _load(RETARGETER, "IKRetargeter")
    created = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
        [source],
        source_mesh,
        target_mesh,
        retargeter,
        prefix="VISTA_T12_",
        include_referenced_assets=False,
        overwrite_existing_files=True,
    )
    if len(created) != 1:
        raise RuntimeError(
            f"retarget expected one output for {source_path}, got {len(created)}"
        )
    temporary_path = _package_path(created[0].get_asset())
    _delete_if_present(output_path)
    if not unreal.EditorAssetLibrary.rename_asset(temporary_path, output_path):
        raise RuntimeError(f"retarget output move failed: {temporary_path}")
    return _load(output_path, "AnimSequence")


def _copy_target_sequence(source_path: str, output_path: str) -> object:
    _load(source_path, "AnimSequence")
    _delete_if_present(output_path)
    if not unreal.EditorAssetLibrary.duplicate_asset(source_path, output_path):
        raise RuntimeError(f"target sequence duplication failed: {source_path}")
    if not unreal.EditorAssetLibrary.save_asset(
        output_path, only_if_is_dirty=False
    ):
        raise RuntimeError(f"target sequence save failed: {output_path}")
    return _load(output_path, "AnimSequence")


def _create_montage(
    action: str,
    sequence_path: str,
    montage_path: str,
    contact_fraction: float | None,
) -> dict[str, object]:
    _delete_if_present(montage_path)
    native_result = json.loads(
        unreal.VistaPlayableHomeAnimationLibrary.create_montage_from_sequence(
            sequence_path, montage_path, 0.12, 0.12
        )
    )
    if native_result.get("status") != "success":
        raise RuntimeError(f"native montage authoring failed: {native_result}")
    montage = _load(montage_path, "AnimMontage")
    play_length = float(montage.get_play_length())
    contact_signal = CONTACT_SIGNALS.get(action)
    completion_signal = COMPLETION_SIGNALS.get(action)
    if completion_signal is None:
        raise RuntimeError(f"completion signal contract missing for {action}")
    if (contact_fraction is None) != (contact_signal is None):
        raise RuntimeError(f"contact signal contract mismatch for {action}")
    notify_specs = []
    if contact_signal is not None and contact_fraction is not None:
        notify_specs.append((contact_signal, play_length * contact_fraction))
    notify_specs.append((completion_signal, max(0.001, play_length - 0.05)))
    for signal, time_seconds in notify_specs:
        notify = unreal.AnimationLibrary.add_animation_notify_event(
            montage,
            "1",
            min(max(0.001, time_seconds), play_length - 0.001),
            unreal.VistaAnimationSignalNotify,
        )
        if notify is None:
            raise RuntimeError(f"could not add {signal} notify to {montage_path}")
        notify.set_editor_property("signal_name", signal)
    if not unreal.EditorAssetLibrary.save_asset(
        montage_path, only_if_is_dirty=False
    ):
        raise RuntimeError(f"montage save failed after notifies: {montage_path}")
    montage = _load(montage_path, "AnimMontage")
    signals = sorted(
        str(event.get_editor_property("notify").get_editor_property("signal_name"))
        for event in unreal.AnimationLibrary.get_animation_notify_events(montage)
        if event.get_editor_property("notify").get_class().get_name()
        == "VistaAnimationSignalNotify"
    )
    expected = sorted(signal for signal, _ in notify_specs)
    skeleton = montage.get_editor_property("skeleton").get_path_name()
    if signals != expected or skeleton != TARGET_SKELETON:
        raise RuntimeError(
            f"montage validation failed for {montage_path}: "
            f"signals={signals}, skeleton={skeleton}"
        )
    return {
        "montage": montage_path,
        "play_length_seconds": play_length,
        "sequence": sequence_path,
        "skeleton": skeleton,
        "typed_notify_signals": signals,
    }


def main() -> None:
    report_path_text = os.environ.get("VISTA_ANIMATION_REPORT", "")
    if not report_path_text:
        raise RuntimeError("VISTA_ANIMATION_REPORT is required")
    authoring_mode = os.environ.get("VISTA_ANIMATION_AUTHORING_MODE", "full")
    if authoring_mode not in AUTHORING_MODES:
        raise RuntimeError(
            f"unsupported VISTA_ANIMATION_AUTHORING_MODE: {authoring_mode}"
        )
    report_path = Path(report_path_text)
    receipt: dict[str, object] = {
        "schema": SCHEMA,
        "accepted": False,
        "authoring_mode": authoring_mode,
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "output_root": OUTPUT_ROOT,
        "actions": [],
        "error": None,
    }
    try:
        results = []
        for action in sorted(ACTION_SPECS):
            source, sequence_name, montage_name, contact_fraction = ACTION_SPECS[action]
            sequence_path = f"{OUTPUT_ROOT}/Sequences/{sequence_name}"
            montage_path = f"{OUTPUT_ROOT}/Montages/{montage_name}"
            source_kind = (
                "simworld_retargeted"
                if source.startswith("/Game/Human_Avatar/")
                else "ue_manny_project_owned"
            )
            if authoring_mode == "montages_only":
                sequence = _load(sequence_path, "AnimSequence")
            elif source_kind == "simworld_retargeted":
                sequence = _retarget(source, sequence_path)
            else:
                sequence = _copy_target_sequence(source, sequence_path)
            skeleton = sequence.get_editor_property("skeleton").get_path_name()
            if skeleton != TARGET_SKELETON:
                raise RuntimeError(
                    f"target sequence skeleton mismatch for {action}: {skeleton}"
                )
            result = _create_montage(
                action, sequence_path, montage_path, contact_fraction
            )
            result.update(
                {
                    "action": action,
                    "source": source,
                    "source_kind": source_kind,
                }
            )
            results.append(result)
        receipt["actions"] = results
        receipt["accepted"] = len(results) == len(ACTION_SPECS)
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["traceback"] = traceback.format_exc()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    unreal.log("VISTA_ANIMATION_AUTHORING=" + json.dumps(receipt, sort_keys=True))


main()
