#!/usr/bin/env python3
"""Seal a dev-only articulated-fridge UE execution without launching Unreal.

The attempt root and isolated project must already exist.  This planner proves
that the project, base map, transported three-link payload and legacy Phase-2
scene evidence are exact.  It copies the two evidence JSON inputs into the
attempt root and emits one exclusive execution manifest for the fixed UE
commandlet.  The production/R6 project is never accepted as an execution path.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

try:
    from . import hssd_articulated_fridge_contract as fridge_contract
except ImportError:  # Direct script execution from this directory.
    import hssd_articulated_fridge_contract as fridge_contract


EXECUTION_SCHEMA = "vista.playable-articulated-fridge-dev-execution/v1"
TRANSPORT_SCHEMA = "vista.playable-articulated-fridge-transport-receipt/v1"
EXPECTED_ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
INSTANCE_ID = "hssd.r1/kitchen_dining.fridge.01"
SEMANTIC_ID = "home.r1/room.kitchen_dining/entity.fridge.01"
LEGACY_SHELL_CLASS = "/Script/Engine.StaticMeshActor"
LEGACY_PROXY_CLASS = "/Script/VistaPlayableHome.VistaContainerActor"
ACTOR_CLASS = "/Script/VistaPlayableHome.VistaArticulatedFridgeActor"
DERIVATIVE_ROOT = "/Game/VISTA/Dev/ArticulatedFridge/"
EXECUTION_NAME = "articulated-fridge-execution.json"
RECEIPT_NAME = "articulated-fridge-scene-receipt.json"
RESULT_NAME = "articulated-fridge-scene-result.json"
OUTPUT_ROLES = ("body", "primary_door", "secondary_door")
ROLE_ASSET_NAMES = {
    "body": "SM_HssdFridgeBody",
    "primary_door": "SM_HssdFridgePrimaryDoor",
    "secondary_door": "SM_HssdFridgeSecondaryDoor",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ArticulatedFridgePlanError(RuntimeError):
    """The isolated project or one of the pinned evidence inputs is invalid."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise ArticulatedFridgePlanError(message)


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ArticulatedFridgePlanError(f"non-finite JSON constant: {value}")


def _canonical_json(value: Any, *, newline: bool = True) -> bytes:
    try:
        raw = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ArticulatedFridgePlanError(
            "execution is not finite canonical JSON"
        ) from exc
    return raw + (b"\n" if newline else b"")


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ArticulatedFridgePlanError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArticulatedFridgePlanError(f"{label} is not strict UTF-8 JSON") from exc
    _require(type(value) is dict, f"{label} root must be one object")
    return value


def _valid_content_digest(value: Mapping[str, Any]) -> bool:
    expected = value.get("content_digest")
    if not isinstance(expected, str) or SHA256.fullmatch(expected) is None:
        return False
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return expected in {
        hashlib.sha256(_canonical_json(body, newline=True)).hexdigest(),
        hashlib.sha256(_canonical_json(body, newline=False)).hexdigest(),
    }


def _regular_absolute(path: Path, label: str) -> Path:
    _require(path.is_absolute(), f"{label} must be absolute")
    _require(
        path.exists() and not path.is_symlink(), f"{label} is missing or symlinked"
    )
    resolved = path.resolve(strict=True)
    _require(resolved.is_file(), f"{label} must be a regular file")
    return resolved


def _directory_absolute(path: Path, label: str) -> Path:
    _require(path.is_absolute(), f"{label} must be absolute")
    _require(
        path.exists() and not path.is_symlink(), f"{label} is missing or symlinked"
    )
    resolved = path.resolve(strict=True)
    _require(resolved.is_dir(), f"{label} must be a directory")
    return resolved


def _beneath(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    _require(resolved.is_relative_to(root), f"{label} escapes the attempt root")
    return resolved


def _write_exclusive(path: Path, raw: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def _copy_exclusive(source: Path, destination: Path) -> dict[str, Any]:
    raw = source.read_bytes()
    _write_exclusive(destination, raw)
    return {
        "path": str(destination),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _map_package_file(project_file: Path, object_path: str) -> Path:
    _require(
        object_path.startswith("/Game/") and "." not in object_path,
        "map object path must be one /Game package path",
    )
    relative = PurePosixPath(object_path.removeprefix("/Game/") + ".umap")
    _require(".." not in relative.parts, "map object path escapes Content")
    return project_file.parent / "Content" / Path(*relative.parts)


def _strict_world_transform(value: Any, label: str) -> dict[str, list[float]]:
    _require(
        type(value) is dict and set(value) == {"location_cm", "rotation_deg", "scale"},
        f"{label} transform shape differs",
    )
    result: dict[str, list[float]] = {}
    for key in ("location_cm", "rotation_deg", "scale"):
        vector = value[key]
        _require(
            isinstance(vector, list)
            and len(vector) == 3
            and all(
                type(item) in (int, float) and math.isfinite(item) for item in vector
            ),
            f"{label} {key} is invalid",
        )
        result[key] = [float(item) for item in vector]
    _require(
        all(abs(item) > 1e-8 for item in result["scale"]), f"{label} scale is singular"
    )
    return result


def _legacy_projection(scene: Mapping[str, Any]) -> dict[str, Any]:
    _require(
        _valid_content_digest(scene), "legacy scene receipt content digest differs"
    )
    _require(
        scene.get("accepted_as_ue_runtime") is False
        and scene.get("diagnostic_only") is True
        and isinstance(scene.get("map_path"), str),
        "legacy scene receipt disposition differs",
    )
    actors = scene.get("actors")
    proxies = scene.get("semantic_proxies")
    _require(
        isinstance(actors, list) and isinstance(proxies, list),
        "legacy scene actor inventories are unavailable",
    )
    shells = [
        item
        for item in actors
        if isinstance(item, Mapping) and item.get("instance_id") == INSTANCE_ID
    ]
    matches = [
        item
        for item in proxies
        if isinstance(item, Mapping) and item.get("semantic_target_id") == SEMANTIC_ID
    ]
    _require(
        len(shells) == 1 and len(matches) == 1,
        "legacy fridge shell/proxy identity is not unique",
    )
    shell = shells[0]
    proxy = matches[0].get("reloaded")
    _require(
        isinstance(proxy, Mapping), "legacy fridge proxy reload evidence is absent"
    )

    shell_tags = shell.get("tags")
    _require(
        shell.get("semantic_target_id") == SEMANTIC_ID
        and shell.get("source_asset_id") == "hssd.static.fridge"
        and shell.get("actor_class_path") == LEGACY_SHELL_CLASS
        and shell.get("actor_hidden_in_game") is False
        and shell.get("actor_collision_enabled") is False
        and shell.get("collision_enabled") is False
        and shell.get("mesh_path", shell.get("object_path")) is not None
        and isinstance(shell_tags, list)
        and "VistaRole=hssd_visual_shell" in shell_tags
        and "VistaHssdInstanceId=" + INSTANCE_ID in shell_tags
        and "VistaHssdSemanticTargetId=" + SEMANTIC_ID in shell_tags,
        "legacy fridge visual shell evidence differs",
    )
    proxy_tags = proxy.get("tags")
    components = proxy.get("components")
    _require(
        proxy.get("semantic_target_id") == SEMANTIC_ID
        and proxy.get("actor_class_path") == LEGACY_PROXY_CLASS
        and proxy.get("actor_hidden_in_game") is True
        and proxy.get("actor_collision_enabled") is True
        and isinstance(proxy_tags, list)
        and "VistaSemanticId=" + SEMANTIC_ID in proxy_tags
        and isinstance(components, list)
        and len(components) == 1
        and components[0].get("mesh_path")
        and components[0].get("collision_mode") == "QueryOnly"
        and components[0].get("collision_enabled") is True
        and components[0].get("simulate_physics") is False
        and components[0].get("visible") is False,
        "legacy fridge hidden proxy evidence differs",
    )
    return {
        "base_map_path": scene["map_path"],
        "shell": {
            "instance_id": INSTANCE_ID,
            "semantic_target_id": SEMANTIC_ID,
            "actor_path": shell["actor_path"],
            "actor_label": shell["actor_label"],
            "actor_class_path": shell["actor_class_path"],
            "actor_hidden_in_game": False,
            "actor_collision_enabled": False,
            "tags": sorted(shell_tags),
            "world_transform_cm": _strict_world_transform(
                shell["world_transform_cm"], "legacy shell"
            ),
            "mesh_path": shell.get("mesh_path", shell.get("object_path")),
            "collision_profile": shell["collision_profile"],
            "collision_enabled": False,
        },
        "proxy": {
            "semantic_target_id": SEMANTIC_ID,
            "actor_path": proxy["actor_path"],
            "actor_label": proxy["actor_label"],
            "actor_class_path": proxy["actor_class_path"],
            "actor_hidden_in_game": True,
            "actor_collision_enabled": True,
            "tags": sorted(proxy_tags),
            "world_transform_cm": _strict_world_transform(
                proxy["world_transform_cm"], "legacy proxy"
            ),
            "component_count": 1,
            "component_mesh_path": components[0]["mesh_path"],
            "component_collision_profile": components[0]["collision_profile"],
            "component_collision_mode": "QueryOnly",
            "component_visible": False,
        },
    }


def _transport_projection(
    receipt_path: Path, document: Mapping[str, Any]
) -> dict[str, Any]:
    _require(
        document.get("schema_version") == TRANSPORT_SCHEMA
        and document.get("status")
        == "transported_pending_ue_import_runtime_and_human_review"
        and document.get("accepted") is False
        and document.get("ue_imported") is False
        and _valid_content_digest(document),
        "transport receipt disposition or content digest differs",
    )
    outputs = document.get("outputs")
    _require(
        isinstance(outputs, list)
        and [item.get("role") for item in outputs] == list(OUTPUT_ROLES),
        "transport output role inventory differs",
    )
    projection = []
    for item in outputs:
        derivative = item.get("derivative")
        validation = item.get("validation")
        bounds = item.get("mesh_bounds")
        _require(
            isinstance(derivative, Mapping)
            and isinstance(validation, Mapping)
            and isinstance(bounds, Mapping)
            and validation.get("self_contained") is True
            and validation.get("single_mesh") is True
            and validation.get("embedded_png_images_valid") is True,
            "transported link validation differs",
        )
        relative = PurePosixPath(str(derivative.get("relative_path", "")))
        _require(
            not relative.is_absolute() and ".." not in relative.parts,
            "transported link path is unsafe",
        )
        path = receipt_path.parent.joinpath(*relative.parts)
        path = _regular_absolute(path, "transported link")
        _require(
            path.stat().st_size == derivative.get("size_bytes")
            and _sha256(path) == derivative.get("sha256"),
            "transported link bytes differ from receipt",
        )
        projection.append(
            {
                "role": item["role"],
                "source_path": str(path),
                "source_sha256": derivative["sha256"],
                "source_size_bytes": derivative["size_bytes"],
                "mesh_bounds": copy.deepcopy(bounds),
            }
        )
    return {
        "receipt_path": str(receipt_path),
        "receipt_sha256": _sha256(receipt_path),
        "receipt_content_digest": document["content_digest"],
        "outputs": projection,
    }


def _rotate_xyz_rpy(vector: Sequence[float], rpy: Sequence[float]) -> list[float]:
    x, y, z = (float(item) for item in vector)
    roll, pitch, yaw = (float(item) for item in rpy)
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return [
        (cy * cp) * x + (cy * sp * sr - sy * cr) * y + (cy * sp * cr + sy * sr) * z,
        (sy * cp) * x + (sy * sp * sr + cy * cr) * y + (sy * sp * cr - cy * sr) * z,
        (-sp) * x + (cp * sr) * y + (cp * cr) * z,
    ]


def _actor_binding(
    document: Mapping[str, Any],
    legacy: Mapping[str, Any],
    transported_outputs: Sequence[Mapping[str, Any]],
    namespace: str,
) -> dict[str, Any]:
    root_rpy = document["root_transform"]["rpy_rad"]
    root_rotation_deg = [math.degrees(float(item)) for item in root_rpy]
    joints = {item["child"]: item for item in document["joints"]}
    assets = []
    for item in transported_outputs:
        name = ROLE_ASSET_NAMES[item["role"]]
        assets.append(
            {
                **copy.deepcopy(dict(item)),
                "object_path": f"{namespace}/Assets/{name}.{name}",
            }
        )
    primary_bounds = next(
        item["mesh_bounds"]
        for item in transported_outputs
        if item["role"] == "primary_door"
    )
    lower = primary_bounds["min_m"]
    upper = primary_bounds["max_m"]
    handle_local_cm = [
        (float(upper[0]) - 0.04 * (float(upper[0]) - float(lower[0]))) * 100.0,
        float(lower[1]) * 100.0,
        (float(lower[2]) + float(upper[2])) * 50.0,
    ]

    def hinge(child: str) -> dict[str, Any]:
        item = joints[child]
        location = [
            value * 100.0 for value in _rotate_xyz_rpy(item["origin_xyz_m"], root_rpy)
        ]
        return {
            "location_cm": location,
            "rotation_deg": root_rotation_deg,
            "axis": copy.deepcopy(item["axis"]),
        }

    return {
        "actor_class_path": ACTOR_CLASS,
        "actor_label": "VISTA_HSSD_ARTICULATED_FRIDGE_R1",
        "semantic_id": SEMANTIC_ID,
        "world_transform_cm": copy.deepcopy(legacy["shell"]["world_transform_cm"]),
        "tags": sorted(
            [
                "VistaRole=articulated_fridge",
                "VistaSemanticId=" + SEMANTIC_ID,
                "VistaHssdInstanceId=" + INSTANCE_ID,
                "VistaHssdContractId=" + document["contract_id"],
                "VistaDevDerivative=true",
                "VistaAccepted=false",
            ]
        ),
        "body_relative_transform": {
            "location_cm": [0.0, 0.0, 0.0],
            "rotation_deg": root_rotation_deg,
            "scale": [1.0, 1.0, 1.0],
        },
        "primary_hinge": hinge("fridge0014_door01"),
        "secondary_hinge": hinge("fridge0014_door02"),
        "door_relative_transform": {
            "location_cm": [0.0, 0.0, 0.0],
            "rotation_deg": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        },
        "handle_relative_location_cm": handle_local_cm,
        "open_angle_deg": document["runtime_binding"]["primary_open_angle_deg"],
        "angular_speed_deg_s": document["runtime_binding"]["angular_speed_deg_s"],
        "receptacle_count": len(document["receptacles"]),
        "assets": assets,
    }


def plan_execution(
    *,
    attempt_root: Path,
    project_file: Path,
    contract_path: Path,
    transport_receipt_path: Path,
    legacy_scene_receipt_path: Path,
    derivative_map_path: str,
    content_namespace: str,
    commandlet_path: Path,
) -> dict[str, Any]:
    attempt = _directory_absolute(attempt_root, "attempt root")
    _require(
        "production" not in {part.casefold() for part in attempt.parts}
        and "release" not in {part.casefold() for part in attempt.parts},
        "attempt root uses a protected production/release path",
    )
    project = _beneath(
        _regular_absolute(project_file, "isolated project"), attempt, "isolated project"
    )
    _require(
        project.suffix == ".uproject" and project.parent.name == "project",
        "isolated project must be attempt-root/project/*.uproject",
    )
    commandlet = _regular_absolute(commandlet_path, "fixed commandlet")
    manifest = _regular_absolute(contract_path, "articulated fridge contract")
    contract_document = fridge_contract.load_contract(manifest)
    fridge_contract.validate_contract(contract_document)
    _require(
        contract_document["semantic_target_id"] == SEMANTIC_ID,
        "contract semantic target differs",
    )

    transport_path = _regular_absolute(transport_receipt_path, "transport receipt")
    _require(
        transport_path.is_relative_to(attempt),
        "transport receipt must be inside the attempt root",
    )
    transport_document = _load_json(transport_path, "transport receipt")
    _require(
        transport_document.get("contract", {}).get("sha256") == _sha256(manifest)
        and transport_document.get("contract", {}).get("content_digest")
        == contract_document["content_digest"],
        "transport receipt contract pin differs",
    )
    transport = _transport_projection(transport_path, transport_document)

    legacy_source = _regular_absolute(legacy_scene_receipt_path, "legacy scene receipt")
    legacy_document = _load_json(legacy_source, "legacy scene receipt")
    legacy = _legacy_projection(legacy_document)
    base_map_path = legacy["base_map_path"]
    _require(
        derivative_map_path.startswith(DERIVATIVE_ROOT)
        and derivative_map_path != base_map_path
        and content_namespace.startswith(DERIVATIVE_ROOT)
        and content_namespace not in derivative_map_path
        and "." not in derivative_map_path
        and "." not in content_namespace,
        "derivative map/namespace is not a fresh dev-only package path",
    )
    base_package = _beneath(
        _regular_absolute(
            _map_package_file(project, base_map_path), "base map package"
        ),
        attempt,
        "base map package",
    )
    derivative_package = _map_package_file(project, derivative_map_path)
    _require(
        not derivative_package.exists() and not derivative_package.is_symlink(),
        "derivative map package already exists",
    )

    inputs = attempt / "inputs"
    _require(
        not inputs.exists() and not inputs.is_symlink(),
        "attempt input directory already exists",
    )
    inputs.mkdir(mode=0o700)
    contract_copy = _copy_exclusive(
        manifest, inputs / "articulated-fridge-contract.json"
    )
    scene_copy = _copy_exclusive(legacy_source, inputs / "legacy-scene-receipt.json")

    execution_path = attempt / EXECUTION_NAME
    _require(not execution_path.exists(), "execution manifest already exists")
    actor_binding = _actor_binding(
        contract_document,
        legacy,
        transport["outputs"],
        content_namespace,
    )
    execution = _seal(
        {
            "schema_version": EXECUTION_SCHEMA,
            "mode": "dev_only_fresh_derivative",
            "engine_version": EXPECTED_ENGINE_VERSION,
            "attempt_root": str(attempt),
            "project_file": str(project),
            "project_sha256": _sha256(project),
            "base_map": {
                "object_path": base_map_path,
                "package_file": str(base_package),
                "package_sha256": _sha256(base_package),
                "package_size_bytes": base_package.stat().st_size,
            },
            "derivative_map": {
                "object_path": derivative_map_path,
                "package_file": str(derivative_package),
                "content_namespace": content_namespace,
            },
            "contract": {
                **contract_copy,
                "content_digest": contract_document["content_digest"],
                "contract_id": contract_document["contract_id"],
            },
            "transport": transport,
            "legacy_scene": {
                **scene_copy,
                "content_digest": legacy_document["content_digest"],
                "schema_version": legacy_document["schema_version"],
            },
            "legacy": legacy,
            "actor_binding": actor_binding,
            "commandlet": {
                "path": str(commandlet),
                "sha256": _sha256(commandlet),
            },
            "outputs": {
                "scene_receipt": str(attempt / RECEIPT_NAME),
                "scene_result": str(attempt / RESULT_NAME),
            },
            "policy": {
                "append_only_attempt": True,
                "isolated_project_required": True,
                "base_map_read_only": True,
                "fresh_derivative_map_required": True,
                "fresh_asset_namespace_required": True,
                "replace_existing": False,
                "legacy_identity_must_be_exact_before_delete": True,
                "save_reload_required": True,
                "quarantine_on_failure": True,
                "accepted": False,
                "launch_ue": False,
            },
        }
    )
    _write_exclusive(execution_path, _canonical_json(execution))
    return execution


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--project-file", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=fridge_contract.CONTRACT_PATH)
    parser.add_argument("--transport-receipt", type=Path, required=True)
    parser.add_argument("--legacy-scene-receipt", type=Path, required=True)
    parser.add_argument("--derivative-map", required=True)
    parser.add_argument("--content-namespace", required=True)
    parser.add_argument(
        "--commandlet",
        type=Path,
        default=Path(__file__).with_name(
            "compose_hssd_articulated_fridge_commandlet.py"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        execution = plan_execution(
            attempt_root=args.attempt_root,
            project_file=args.project_file,
            contract_path=args.contract,
            transport_receipt_path=args.transport_receipt,
            legacy_scene_receipt_path=args.legacy_scene_receipt,
            derivative_map_path=args.derivative_map,
            content_namespace=args.content_namespace,
            commandlet_path=args.commandlet,
        )
    except (
        ArticulatedFridgePlanError,
        fridge_contract.ArticulatedFridgeContractError,
        OSError,
    ) as exc:
        print(f"VISTA_ARTICULATED_FRIDGE_PLAN_FAILED: {exc}")
        return 1
    print(
        "VISTA_ARTICULATED_FRIDGE_PLAN_RESULT:"
        + json.dumps(
            {
                "status": "planned_not_executed",
                "execution": str(args.attempt_root / EXECUTION_NAME),
                "content_digest": execution["content_digest"],
                "launch_ue": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
