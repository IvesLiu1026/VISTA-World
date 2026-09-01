"""Author or cold-verify the external-only R18 CC0-to-Manny animation set.

Invoke through ``UnrealEditor-Cmd -ExecutePythonScript``.  The host runner
provides a sealed execution document and runs author/verify in separate editor
processes.  Binary output is never written into the Git checkout.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any, Mapping

import unreal


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.ue.vista_playable_home import (  # noqa: E402
    manny_detail_actions_retarget_r18_contract as contract,
)


EXPECTED_ENGINE = "5.7.3-50162420+++UE5+Release-5.7"
TEMP_PREFIX = "VISTA_R18_RETARGET_TMP_"
MAX_EXECUTION_BYTES = 4 * 1024 * 1024
NOTIFY_TOLERANCE_SECONDS = 1.0 / 3000.0


class RetargetError(RuntimeError):
    """The sealed authoring or verification contract was not satisfied."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RetargetError(message)


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8", "strict")


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, f"{label} contains duplicate key {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {token}")
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise RetargetError(f"{label} is not strict JSON") from exc
    require(type(value) is dict, f"{label} root is not an object")
    require(raw == canonical_json(value), f"{label} is not canonical JSON")
    return value


def read_execution() -> tuple[dict[str, Any], str, str]:
    path_text = os.environ.get(contract.EXECUTION_ENV, "")
    expected_sha = os.environ.get(contract.EXECUTION_SHA_ENV, "")
    mode = os.environ.get(contract.MODE_ENV, "")
    require(mode in (contract.AUTHOR_MODE, contract.VERIFY_MODE), "mode differs")
    require(path_text and expected_sha, "sealed execution environment is missing")
    path = Path(path_text)
    require(
        path.is_absolute() and path.is_file() and not path.is_symlink(),
        "execution path is invalid",
    )
    raw = path.read_bytes()
    require(0 < len(raw) <= MAX_EXECUTION_BYTES, "execution size is invalid")
    actual_sha = hashlib.sha256(raw).hexdigest()
    require(actual_sha == expected_sha, "execution SHA-256 differs")
    execution = strict_json(raw, "execution")
    require(
        set(execution)
        == {
            "acknowledgement",
            "author_output",
            "clip_count",
            "content_namespace",
            "engine_version",
            "mode_outputs",
            "project_file",
            "schema_version",
            "source_asset_seals",
            "source_mesh_object_path",
            "target_mesh_object_path",
            "verify_output",
            "worker_script",
        },
        "execution fields differ",
    )
    require(
        execution["schema_version"] == contract.EXECUTION_SCHEMA
        and execution["acknowledgement"] == contract.ACKNOWLEDGEMENT
        and execution["engine_version"] == EXPECTED_ENGINE
        and execution["clip_count"] == len(contract.CLIP_SPECS)
        and execution["content_namespace"] == contract.CONTENT_NAMESPACE
        and execution["source_mesh_object_path"] == contract.SOURCE_MESH_OBJECT_PATH
        and execution["target_mesh_object_path"] == contract.TARGET_MESH_OBJECT_PATH,
        "execution contract differs",
    )
    project_file = Path(str(execution["project_file"]))
    require(
        project_file.is_absolute()
        and project_file.resolve()
        == Path(unreal.Paths.get_project_file_path()).resolve(),
        "loaded UE project differs",
    )
    script = execution["worker_script"]
    require(
        type(script) is dict and set(script) == {"path", "sha256", "size_bytes"},
        "worker script seal differs",
    )
    require(
        Path(str(script["path"])).resolve() == Path(__file__).resolve()
        and sha256_file(Path(str(script["path"])))
        == (script["sha256"], script["size_bytes"]),
        "executing worker script differs from sealed input",
    )
    require(
        str(unreal.SystemLibrary.get_engine_version()) == EXPECTED_ENGINE,
        "UE engine identity differs",
    )
    validate_source_seals(execution["source_asset_seals"])
    return execution, actual_sha, mode


def validate_source_seals(raw: Any) -> None:
    require(
        type(raw) is list and len(raw) == len(contract.CLIP_SPECS) * 2,
        "source asset seal count differs",
    )
    expected_paths = {
        str(spec[key])
        for spec in contract.CLIP_SPECS
        for key in ("source_sequence_object_path", "source_montage_object_path")
    }
    observed: set[str] = set()
    for item in raw:
        require(
            type(item) is dict
            and set(item) == {"object_path", "path", "sha256", "size_bytes"},
            "source asset seal shape differs",
        )
        object_path = str(item["object_path"])
        path = Path(str(item["path"]))
        require(
            object_path in expected_paths and object_path not in observed,
            "source asset identity differs",
        )
        require(
            path.is_absolute() and path.is_file() and not path.is_symlink(),
            "source package path is invalid",
        )
        require(
            sha256_file(path) == (item["sha256"], item["size_bytes"]),
            "source package bytes differ",
        )
        observed.add(object_path)
    require(observed == expected_paths, "source asset seal closure differs")


def class_path(value: Any) -> str:
    return str(value.get_class().get_path_name())


def property_or_none(value: Any, name: str) -> Any:
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def load_exact(path: str, expected_class_path: str) -> Any:
    value = unreal.load_asset(path)
    require(
        value is not None
        and str(value.get_path_name()) == path
        and class_path(value) == expected_class_path,
        f"asset identity differs: {path}",
    )
    return value


def skeletal_bone_names(mesh: Any) -> list[str]:
    component = unreal.new_object(unreal.SkeletalMeshComponent.static_class())
    require(component is not None, "transient skeletal component is unavailable")
    component.set_skeletal_mesh_asset(mesh)
    count = int(component.get_num_bones())
    require(count > 0, "skeletal mesh bone inventory is unavailable")
    return [str(component.get_bone_name(index)) for index in range(count)]


def validate_meshes() -> tuple[Any, Any, Any]:
    source_mesh = load_exact(
        contract.SOURCE_MESH_OBJECT_PATH, "/Script/Engine.SkeletalMesh"
    )
    source_skeleton = load_exact(
        contract.SOURCE_SKELETON_OBJECT_PATH, "/Script/Engine.Skeleton"
    )
    target_mesh = load_exact(
        contract.TARGET_MESH_OBJECT_PATH, "/Script/Engine.SkeletalMesh"
    )
    target_skeleton = load_exact(
        contract.TARGET_SKELETON_OBJECT_PATH, "/Script/Engine.Skeleton"
    )
    require(
        property_or_none(source_mesh, "skeleton") == source_skeleton
        and skeletal_bone_names(source_mesh) == list(contract.SOURCE_BONE_NAMES),
        "source mesh/skeleton/53-bone contract differs",
    )
    target_bones = set(skeletal_bone_names(target_mesh))
    required_target_bones = {
        bone for spec in contract.CHAIN_SPECS for bone in spec["target"]
    } | {"pelvis"}
    require(
        property_or_none(target_mesh, "skeleton") == target_skeleton
        and required_target_bones <= target_bones,
        "target Manny mesh/skeleton/chain-bone contract differs",
    )
    return source_mesh, target_mesh, target_skeleton


def create_ik_rig(name: str, mesh: Any, side: str) -> Any:
    rig = unreal.IKRigDefinitionFactory.create_new_ik_rig_asset(
        contract.RETARGET_NAMESPACE, name
    )
    expected_path = f"{contract.RETARGET_NAMESPACE}/{name}.{name}"
    require(
        rig is not None and str(rig.get_path_name()) == expected_path,
        f"{side} IK rig creation/path failed",
    )
    controller = unreal.IKRigController.get_controller(rig)
    require(
        controller is not None and controller.set_skeletal_mesh(mesh),
        f"{side} IK rig mesh binding failed",
    )
    require(controller.set_retarget_root("pelvis"), f"{side} IK rig pelvis root failed")
    for spec in contract.CHAIN_SPECS:
        start, end = spec[side]
        created = str(controller.add_retarget_chain(spec["name"], start, end, "None"))
        require(
            created == spec["name"], f"{side} IK chain creation differs: {spec['name']}"
        )
    validate_ik_rig(rig, mesh, side)
    require(
        unreal.EditorAssetLibrary.save_asset(
            str(rig.get_path_name()).split(".", 1)[0], only_if_is_dirty=False
        ),
        f"{side} IK rig save failed",
    )
    return rig


def validate_ik_rig(rig: Any, mesh: Any, side: str) -> dict[str, Any]:
    controller = unreal.IKRigController.get_controller(rig)
    require(controller is not None, f"{side} IK rig controller is unavailable")
    require(controller.get_skeletal_mesh() == mesh, f"{side} IK rig mesh differs")
    require(
        str(controller.get_retarget_root()) == "pelvis", f"{side} retarget root differs"
    )
    chains = list(controller.get_retarget_chains())
    require(len(chains) == len(contract.CHAIN_SPECS), f"{side} chain count differs")
    observed = []
    for spec in contract.CHAIN_SPECS:
        start, end = spec[side]
        require(
            str(controller.get_retarget_chain_start_bone(spec["name"])) == start
            and str(controller.get_retarget_chain_end_bone(spec["name"])) == end
            and str(controller.get_retarget_chain_goal(spec["name"])) == "None",
            f"{side} chain mapping differs: {spec['name']}",
        )
        observed.append({"name": spec["name"], "start": start, "end": end})
    return {
        "object_path": str(rig.get_path_name()),
        "mesh": str(mesh.get_path_name()),
        "retarget_root": "pelvis",
        "chains": observed,
    }


def create_retargeter(
    source_rig: Any, target_rig: Any, source_mesh: Any, target_mesh: Any
) -> Any:
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    retargeter = tools.create_asset(
        contract.RETARGETER_NAME,
        contract.RETARGET_NAMESPACE,
        unreal.IKRetargeter,
        unreal.IKRetargetFactory(),
    )
    require(
        retargeter is not None
        and str(retargeter.get_path_name()) == contract.RETARGETER_OBJECT_PATH,
        "IK retargeter creation/path failed",
    )
    controller = unreal.IKRetargeterController.get_controller(retargeter)
    require(controller is not None, "IK retargeter controller is unavailable")
    require(
        int(controller.get_num_retarget_ops()) == 6,
        "factory UE 5.7 default six-op retarget stack differs",
    )
    source_side = unreal.RetargetSourceOrTarget.SOURCE
    target_side = unreal.RetargetSourceOrTarget.TARGET
    controller.set_ik_rig(source_side, source_rig)
    controller.set_ik_rig(target_side, target_rig)
    controller.set_preview_mesh(source_side, source_mesh)
    controller.set_preview_mesh(target_side, target_mesh)
    controller.assign_ik_rig_to_all_ops(source_side, source_rig)
    controller.assign_ik_rig_to_all_ops(target_side, target_rig)
    controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    controller.auto_align_all_bones(
        target_side, unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN
    )
    validate_retargeter(retargeter, source_rig, target_rig, source_mesh, target_mesh)
    require(
        unreal.EditorAssetLibrary.save_asset(
            str(retargeter.get_path_name()).split(".", 1)[0],
            only_if_is_dirty=False,
        ),
        "IK retargeter save failed",
    )
    return retargeter


def validate_retargeter(
    retargeter: Any,
    source_rig: Any,
    target_rig: Any,
    source_mesh: Any,
    target_mesh: Any,
) -> dict[str, Any]:
    controller = unreal.IKRetargeterController.get_controller(retargeter)
    require(controller is not None, "IK retargeter controller is unavailable")
    source_side = unreal.RetargetSourceOrTarget.SOURCE
    target_side = unreal.RetargetSourceOrTarget.TARGET
    require(
        controller.get_ik_rig(source_side) == source_rig
        and controller.get_ik_rig(target_side) == target_rig
        and controller.get_preview_mesh(source_side) == source_mesh
        and controller.get_preview_mesh(target_side) == target_mesh,
        "IK retargeter source/target binding differs",
    )
    count = int(controller.get_num_retarget_ops())
    require(count == 6, "UE 5.7 default six-op retarget stack differs")
    require(
        all(controller.get_retarget_op_enabled(index) for index in range(count)),
        "one or more retarget ops are disabled",
    )
    mappings = []
    for spec in contract.CHAIN_SPECS:
        mapped = str(controller.get_source_chain(spec["name"]))
        require(
            mapped == spec["name"], f"retarget chain mapping differs: {spec['name']}"
        )
        mappings.append({"source": mapped, "target": spec["name"]})
    return {
        "object_path": str(retargeter.get_path_name()),
        "source_ik_rig": str(source_rig.get_path_name()),
        "target_ik_rig": str(target_rig.get_path_name()),
        "source_preview_mesh": str(source_mesh.get_path_name()),
        "target_preview_mesh": str(target_mesh.get_path_name()),
        "retarget_op_count": count,
        "chain_mappings": mappings,
    }


def source_assets() -> list[Any]:
    paths = [
        str(spec[key])
        for spec in contract.CLIP_SPECS
        for key in ("source_sequence_object_path", "source_montage_object_path")
    ]
    assets = [unreal.EditorAssetLibrary.find_asset_data(path) for path in paths]
    require(all(asset.is_valid() for asset in assets), "source asset data is missing")
    loaded_assets = [asset.get_asset() for asset in assets]
    observed_paths = [
        str(asset.get_path_name()) if asset is not None else ""
        for asset in loaded_assets
    ]
    require(
        all(loaded_assets)
        and len(set(observed_paths)) == len(paths)
        and set(observed_paths) == set(paths),
        "source sequence/montage asset data closure differs",
    )
    return assets


def retarget_assets(source_mesh: Any, target_mesh: Any, retargeter: Any) -> None:
    created = unreal.IKRetargetBatchOperation.duplicate_and_retarget(
        source_assets(),
        source_mesh,
        target_mesh,
        retargeter,
        prefix=TEMP_PREFIX,
        include_referenced_assets=False,
        overwrite_existing_files=False,
    )
    require(
        len(created) == len(contract.CLIP_SPECS) * 2, "retarget output count differs"
    )
    target_by_source_name: dict[str, str] = {}
    for spec in contract.CLIP_SPECS:
        for source_key, target_key in (
            ("source_sequence_object_path", "target_sequence_object_path"),
            ("source_montage_object_path", "target_montage_object_path"),
        ):
            source_name = str(spec[source_key]).rsplit("/", 1)[-1].split(".", 1)[0]
            target_by_source_name[source_name] = str(spec[target_key])
    observed: set[str] = set()
    for data in created:
        asset = data.get_asset()
        require(asset is not None, "retarget output asset cannot load")
        temporary_name = str(asset.get_name())
        require(temporary_name.startswith(TEMP_PREFIX), "retarget temp prefix differs")
        source_name = temporary_name.removeprefix(TEMP_PREFIX)
        require(
            source_name in target_by_source_name and source_name not in observed,
            "retarget source/output identity differs",
        )
        target_object_path = target_by_source_name[source_name]
        target_package = target_object_path.split(".", 1)[0]
        require(
            not unreal.EditorAssetLibrary.does_asset_exist(target_object_path)
            and unreal.EditorAssetLibrary.rename_asset(
                str(asset.get_path_name()).split(".", 1)[0], target_package
            ),
            f"retarget output move failed: {source_name}",
        )
        observed.add(source_name)
    require(observed == set(target_by_source_name), "retarget output closure differs")


def notify_time(event: Any) -> float:
    for name in ("trigger_time", "time"):
        value = property_or_none(event, name)
        if value is not None:
            return float(value)
    raise RetargetError("notify trigger time is unavailable through UE 5.7 Python")


def _transform_values(transform: Any) -> tuple[tuple[float, ...], tuple[float, ...]]:
    translation = transform.translation
    rotation = transform.rotation
    values = (
        float(translation.x),
        float(translation.y),
        float(translation.z),
        float(rotation.x),
        float(rotation.y),
        float(rotation.z),
        float(rotation.w),
    )
    require(
        all(value == value and abs(value) != float("inf") for value in values),
        "motion probe contains a non-finite transform",
    )
    return values[:3], values[3:]


def inspect_motion_probe(
    sequence: Any, spec: Mapping[str, Any], frame_count: int
) -> dict[str, Any]:
    clip_id = str(spec["clip_id"])
    if clip_id in {"sit_down_chair", "stand_up_chair"}:
        bones = ("pelvis", "spine_02", "thigh_l", "thigh_r")
    elif clip_id == "seated_idle_loop":
        bones = ("spine_02", "upperarm_r", "lowerarm_r")
    else:
        bones = ("upperarm_r", "lowerarm_r", "hand_r")
    sample_frames = sorted(
        {
            0,
            frame_count // 2,
            frame_count,
            *(int(item["frame"]) for item in spec["typed_notifies"]),
        }
    )
    maximum_translation_delta = 0.0
    maximum_rotation_delta = 0.0
    per_bone: dict[str, dict[str, float]] = {}
    for bone in bones:
        first_translation, first_rotation = _transform_values(
            unreal.AnimationLibrary.get_bone_pose_for_frame(
                sequence, bone, sample_frames[0], False
            )
        )
        bone_translation_delta = 0.0
        bone_rotation_delta = 0.0
        for frame in sample_frames[1:]:
            translation, rotation = _transform_values(
                unreal.AnimationLibrary.get_bone_pose_for_frame(
                    sequence, bone, frame, False
                )
            )
            bone_translation_delta = max(
                bone_translation_delta,
                sum(
                    (left - right) ** 2
                    for left, right in zip(first_translation, translation, strict=True)
                )
                ** 0.5,
            )
            dot = sum(
                left * right
                for left, right in zip(first_rotation, rotation, strict=True)
            )
            bone_rotation_delta = max(bone_rotation_delta, 1.0 - min(1.0, abs(dot)))
        per_bone[bone] = {
            "maximum_rotation_delta": bone_rotation_delta,
            "maximum_translation_delta_cm": bone_translation_delta,
        }
        maximum_translation_delta = max(
            maximum_translation_delta, bone_translation_delta
        )
        maximum_rotation_delta = max(maximum_rotation_delta, bone_rotation_delta)
    require(
        maximum_translation_delta > 0.001 or maximum_rotation_delta > 1.0e-6,
        f"retargeted motion is structurally static: {clip_id}",
    )
    return {
        "bones": per_bone,
        "maximum_rotation_delta": maximum_rotation_delta,
        "maximum_translation_delta_cm": maximum_translation_delta,
        "sample_frames": sample_frames,
        "structurally_nonzero": True,
    }


def inspect_sequence(
    sequence: Any, spec: Mapping[str, Any], target_mesh: Any, target_skeleton: Any
) -> dict[str, Any]:
    require(
        class_path(sequence) == "/Script/Engine.AnimSequence"
        and property_or_none(sequence, "skeleton") == target_skeleton,
        f"target sequence skeleton differs: {spec['clip_id']}",
    )
    model = property_or_none(sequence, "data_model_interface")
    if model is None:
        model = property_or_none(sequence, "data_model")
    require(model is not None, "target sequence data model is unavailable")
    rate = model.get_frame_rate()
    frame_count = int(unreal.AnimationLibrary.get_num_frames(sequence))
    expected_frames = int(spec["frame_end"]) - int(spec["frame_start"])
    require(
        (int(rate.numerator), int(rate.denominator)) == (30, 1)
        and frame_count == expected_frames
        and abs(float(sequence.get_play_length()) - expected_frames / 30.0)
        <= NOTIFY_TOLERANCE_SECONDS,
        f"target sequence frame contract differs: {spec['clip_id']}",
    )
    tracks = {
        str(name)
        for name in unreal.AnimationLibrary.get_animation_track_names(sequence)
    }
    expected_tracks = set(skeletal_bone_names(target_mesh))
    # FName identity is case-insensitive, while UE 5.7 serializes several Manny
    # corrective tracks with the lowercase spelling inherited from the retarget
    # output (for example correctiveRoot -> correctiveroot).  Close the exact
    # one-to-one FName inventory without treating spelling-case as a new bone.
    track_keys = {name.casefold() for name in tracks}
    expected_track_keys = {name.casefold() for name in expected_tracks}
    require(
        len(tracks) == len(track_keys)
        and len(expected_tracks) == len(expected_track_keys)
        and track_keys == expected_track_keys,
        f"target sequence exact Manny track closure differs: {spec['clip_id']}",
    )
    require(
        unreal.AnimationLibrary.is_root_motion_enabled(sequence) is False
        and unreal.AnimationLibrary.is_root_motion_lock_forced(sequence) is True
        and unreal.AnimationLibrary.get_root_motion_lock_type(sequence)
        == unreal.RootMotionRootLock.REF_POSE,
        f"target sequence root-motion lock policy differs: {spec['clip_id']}",
    )
    motion_probe = inspect_motion_probe(sequence, spec, frame_count)
    return {
        "clip_id": spec["clip_id"],
        "object_path": str(sequence.get_path_name()),
        "frame_count": frame_count,
        "sample_rate": {"numerator": 30, "denominator": 1},
        "play_length_seconds": float(sequence.get_play_length()),
        "skeleton": str(target_skeleton.get_path_name()),
        "exact_target_tracks": sorted(expected_tracks),
        "motion_probe": motion_probe,
        "root_motion_enabled": False,
        "root_motion_lock": "REF_POSE",
        "root_motion_lock_forced": True,
    }


def inspect_montage(
    montage: Any, sequence: Any, spec: Mapping[str, Any], target_skeleton: Any
) -> dict[str, Any]:
    require(
        class_path(montage) == "/Script/Engine.AnimMontage"
        and property_or_none(montage, "skeleton") == target_skeleton,
        f"target montage skeleton differs: {spec['clip_id']}",
    )
    # SlotAnimTracks is not exposed through get_editor_property in UE 5.7.
    # These public APIs close the serialized slot and first-reference identity
    # without weakening the author/cold-verify contract.
    slot_names = [
        str(name)
        for name in unreal.AnimationLibrary.get_montage_slot_names(montage)
    ]
    first_reference = montage.get_first_anim_reference()
    require(
        slot_names == ["DefaultSlot"] and first_reference == sequence,
        f"montage slot/target-sequence closure differs: {spec['clip_id']}",
    )
    events = sorted(
        unreal.AnimationLibrary.get_animation_notify_events(montage),
        key=notify_time,
    )
    expected = sorted(spec["typed_notifies"], key=lambda item: int(item["frame"]))
    require(
        len(events) == len(expected), f"typed notify count differs: {spec['clip_id']}"
    )
    observed = []
    for event, expected_notify in zip(events, expected, strict=True):
        notify = property_or_none(event, "notify")
        time_seconds = notify_time(event)
        require(
            notify is not None
            and class_path(notify)
            == "/Script/VistaPlayableHome.VistaAnimationSignalNotify"
            and str(property_or_none(notify, "signal_name"))
            == expected_notify["signal"]
            and abs(time_seconds - int(expected_notify["frame"]) / 30.0)
            <= NOTIFY_TOLERANCE_SECONDS,
            f"typed notify identity/frame differs: {spec['clip_id']}",
        )
        observed.append(
            {
                "frame": int(expected_notify["frame"]),
                "kind": expected_notify["kind"],
                "signal": expected_notify["signal"],
                "time_seconds": time_seconds,
            }
        )
    expected_frames = int(spec["frame_end"]) - int(spec["frame_start"])
    require(
        abs(float(montage.get_play_length()) - expected_frames / 30.0)
        <= NOTIFY_TOLERANCE_SECONDS,
        f"target montage length differs: {spec['clip_id']}",
    )
    return {
        "clip_id": spec["clip_id"],
        "object_path": str(montage.get_path_name()),
        "sequence": str(sequence.get_path_name()),
        "skeleton": str(target_skeleton.get_path_name()),
        "slot": "DefaultSlot",
        "looping_count": 1,
        "first_reference": str(first_reference.get_path_name()),
        "typed_notifies": observed,
    }


def inspect_all(
    source_mesh: Any, target_mesh: Any, target_skeleton: Any
) -> dict[str, Any]:
    source_rig = load_exact(
        contract.SOURCE_IK_RIG_OBJECT_PATH, "/Script/IKRig.IKRigDefinition"
    )
    target_rig = load_exact(
        contract.TARGET_IK_RIG_OBJECT_PATH, "/Script/IKRig.IKRigDefinition"
    )
    retargeter = load_exact(
        contract.RETARGETER_OBJECT_PATH, "/Script/IKRig.IKRetargeter"
    )
    result: dict[str, Any] = {
        "source_ik_rig": validate_ik_rig(source_rig, source_mesh, "source"),
        "target_ik_rig": validate_ik_rig(target_rig, target_mesh, "target"),
        "retargeter": validate_retargeter(
            retargeter, source_rig, target_rig, source_mesh, target_mesh
        ),
        "clips": [],
    }
    for spec in contract.CLIP_SPECS:
        sequence = load_exact(
            str(spec["target_sequence_object_path"]),
            "/Script/Engine.AnimSequence",
        )
        montage = load_exact(
            str(spec["target_montage_object_path"]),
            "/Script/Engine.AnimMontage",
        )
        result["clips"].append(
            {
                "sequence": inspect_sequence(
                    sequence, spec, target_mesh, target_skeleton
                ),
                "montage": inspect_montage(montage, sequence, spec, target_skeleton),
                "source_montage": spec["source_montage_object_path"],
                "source_revision": spec["source_revision"],
                "source_sequence": spec["source_sequence_object_path"],
            }
        )
    paths = sorted(
        str(path)
        for path in unreal.EditorAssetLibrary.list_assets(
            contract.CONTENT_NAMESPACE, recursive=True, include_folder=False
        )
    )
    observed = sorted(
        (
            {"class_path": class_path(unreal.load_asset(path)), "object_path": path}
            for path in paths
        ),
        key=lambda item: item["object_path"],
    )
    expected = sorted(contract.EXPECTED_INVENTORY, key=lambda item: item["object_path"])
    require(observed == expected, "R18 namespace exact asset inventory differs")
    temporary_assets = [
        str(path)
        for path in unreal.EditorAssetLibrary.list_assets(
            "/Game", recursive=True, include_folder=False
        )
        if TEMP_PREFIX in str(path)
    ]
    require(not temporary_assets, "temporary retarget assets remain in /Game")
    result["asset_inventory"] = observed
    result["temporary_assets_absent"] = True
    return result


def author() -> dict[str, Any]:
    require(
        not unreal.EditorAssetLibrary.does_directory_exist(contract.CONTENT_NAMESPACE),
        "R18 Manny detail namespace is not fresh",
    )
    source_mesh, target_mesh, target_skeleton = validate_meshes()
    require(
        unreal.EditorAssetLibrary.make_directory(contract.RETARGET_NAMESPACE),
        "retarget namespace creation failed",
    )
    require(
        unreal.EditorAssetLibrary.make_directory(contract.SEQUENCE_NAMESPACE),
        "sequence namespace creation failed",
    )
    require(
        unreal.EditorAssetLibrary.make_directory(contract.MONTAGE_NAMESPACE),
        "montage namespace creation failed",
    )
    source_rig = create_ik_rig(contract.SOURCE_IK_RIG_NAME, source_mesh, "source")
    target_rig = create_ik_rig(contract.TARGET_IK_RIG_NAME, target_mesh, "target")
    retargeter = create_retargeter(source_rig, target_rig, source_mesh, target_mesh)
    retarget_assets(source_mesh, target_mesh, retargeter)
    for item in contract.EXPECTED_INVENTORY:
        require(
            unreal.EditorAssetLibrary.save_asset(
                item["object_path"].split(".", 1)[0],
                only_if_is_dirty=False,
            ),
            f"generated package save failed: {item['object_path']}",
        )
    return inspect_all(source_mesh, target_mesh, target_skeleton)


def verify() -> dict[str, Any]:
    require(
        unreal.EditorAssetLibrary.does_directory_exist(contract.CONTENT_NAMESPACE),
        "R18 Manny detail namespace is missing during cold verification",
    )
    source_mesh, target_mesh, target_skeleton = validate_meshes()
    return inspect_all(source_mesh, target_mesh, target_skeleton)


def atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    require(path.is_absolute() and path.parent.is_dir(), "worker output parent differs")
    raw = canonical_json(value)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(not path.exists(), "worker output already exists")
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    execution: dict[str, Any] | None = None
    execution_sha = ""
    mode = os.environ.get(contract.MODE_ENV, "unknown")
    inspection: dict[str, Any] = {}
    error: dict[str, str] | None = None
    try:
        execution, execution_sha, mode = read_execution()
        inspection = author() if mode == contract.AUTHOR_MODE else verify()
    except Exception as exc:
        error = {
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "type": type(exc).__name__,
        }
    receipt: dict[str, Any] = {
        "accepted": False,
        "claims": contract.NEGATIVE_CLAIMS,
        "content_namespace": contract.CONTENT_NAMESPACE,
        "engine_version": str(unreal.SystemLibrary.get_engine_version()),
        "error": error,
        "execution_sha256": execution_sha,
        "inspection": inspection,
        "legal_scope": contract.LEGAL_SCOPE,
        "mode": mode,
        "schema_version": contract.WORKER_SCHEMA,
        "status": (
            f"{mode}_complete_pending_host_seal"
            if error is None
            else f"{mode}_failed_quarantined"
        ),
    }
    receipt["content_digest"] = content_digest(receipt)
    output_text = ""
    if execution is not None:
        output_text = str(
            execution["author_output"]
            if mode == contract.AUTHOR_MODE
            else execution["verify_output"]
        )
    if output_text:
        atomic_write(Path(output_text), receipt)
    unreal.log("VISTA_MANNY_DETAIL_RETARGET_R18=" + json.dumps(receipt, sort_keys=True))
    if error is not None:
        raise RetargetError(error["message"])


main()
