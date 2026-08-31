#!/usr/bin/env python3
"""Seal a dev-only portable HSSD visual-binding execution without launching UE.

The caller supplies a fresh isolated project copied from a *completed* HSSD
articulated-fridge derivative.  This planner proves that copied source map
against the fridge receipt, copies only Git metadata/evidence into a new
append-only attempt, and emits the sole manifest accepted by the fixed UE
commandlet.  It never launches Unreal and never resolves external HSSD files.
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
    from . import hssd_portable_visual_binding_contract as binding_contract
except ImportError:  # Direct script execution from this directory.
    import hssd_portable_visual_binding_contract as binding_contract


EXECUTION_SCHEMA = "vista.playable-hssd-portable-visual-binding-dev-execution/v1"
SOURCE_RECEIPT_SCHEMA = "vista.playable-articulated-fridge-dev-scene-receipt/v1"
SOURCE_SUCCESS_STATUS = "dev_derivative_composed_pending_runtime_and_human_review"
EXPECTED_ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
SOURCE_MAP_ROOT = "/Game/VISTA/Dev/ArticulatedFridge/"
DERIVATIVE_ROOT = "/Game/VISTA/Dev/PortableVisualBindings/"
EXECUTION_NAME = "hssd-portable-visual-binding-execution.json"
RECEIPT_NAME = "hssd-portable-visual-binding-scene-receipt.json"
RESULT_NAME = "hssd-portable-visual-binding-scene-result.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PortableVisualBindingPlanError(RuntimeError):
    """The isolated project or completed fridge source evidence is invalid."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise PortableVisualBindingPlanError(message)


def _duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise PortableVisualBindingPlanError(f"non-finite JSON constant: {value}")


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
        raise PortableVisualBindingPlanError(
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
    except PortableVisualBindingPlanError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PortableVisualBindingPlanError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    _require(type(value) is dict, f"{label} root must be one object")
    return value


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
        isinstance(object_path, str)
        and object_path.startswith("/Game/")
        and "." not in object_path,
        "map object path must be one /Game package path",
    )
    relative = PurePosixPath(object_path.removeprefix("/Game/") + ".umap")
    _require(".." not in relative.parts, "map object path escapes Content")
    return project_file.parent / "Content" / Path(*relative.parts)


def _strict_binding_rows(value: Any) -> list[dict[str, Any]]:
    _require(isinstance(value, list) and len(value) == 2, "binding inventory differs")
    result = copy.deepcopy(value)
    _require(
        tuple(row.get("shell_disposition") for row in result)
        == binding_contract.EXPECTED_SHELL_DISPOSITIONS,
        "binding shell-disposition inventory differs",
    )
    for index, row in enumerate(result):
        _require(type(row) is dict, f"binding {index} is not an object")
        for field in ("shell_world_transform_cm", "pickup_world_transform_cm"):
            transform = row.get(field)
            _require(
                type(transform) is dict
                and set(transform) == {"location_cm", "rotation_deg", "scale"},
                f"binding {index} {field} shape differs",
            )
            for key in ("location_cm", "rotation_deg", "scale"):
                vector = transform[key]
                _require(
                    isinstance(vector, list)
                    and len(vector) == 3
                    and all(
                        type(item) in (int, float) and math.isfinite(item)
                        for item in vector
                    ),
                    f"binding {index} {field}.{key} differs",
                )
    return result


def _source_projection(receipt: Mapping[str, Any]) -> dict[str, Any]:
    _require(_valid_content_digest(receipt), "source fridge receipt digest differs")
    _require(
        receipt.get("schema_version") == SOURCE_RECEIPT_SCHEMA
        and receipt.get("status") == SOURCE_SUCCESS_STATUS
        and receipt.get("error") is None
        and receipt.get("accepted") is False
        and receipt.get("ue_imported") is True
        and receipt.get("runtime_verified") is False
        and receipt.get("human_reviewed") is False
        and receipt.get("promotable") is False
        and receipt.get("diagnostic_only") is True,
        "source fridge receipt disposition differs",
    )
    base = receipt.get("base_map")
    derivative = receipt.get("derivative_map")
    gates = receipt.get("gates")
    claims = receipt.get("claims")
    _require(
        isinstance(base, Mapping)
        and base.get("unchanged") is True
        and isinstance(derivative, Mapping)
        and isinstance(gates, Mapping)
        and isinstance(claims, Mapping),
        "source fridge receipt evidence closure differs",
    )
    _require(
        gates.get("exact_legacy_shell_and_proxy_validated_before_delete") is True
        and gates.get("legacy_shell_and_proxy_removed_only_in_derivative") is True
        and gates.get("fresh_derivative_map_created") is True
        and gates.get("base_map_package_unchanged") is True
        and gates.get("map_saved") is True
        and gates.get("map_cold_reloaded") is True
        and gates.get("one_visible_semantic_authority") is True
        and gates.get("quarantined") is False,
        "source fridge success gates are incomplete",
    )
    _require(
        claims.get("r6_touched") is False
        and claims.get("production_promoted") is False
        and claims.get("ue_runtime_launched") is False,
        "source fridge claims differ",
    )
    object_path = derivative.get("object_path")
    sha = derivative.get("package_sha256")
    size = derivative.get("package_size_bytes")
    _require(
        isinstance(object_path, str)
        and object_path.startswith(SOURCE_MAP_ROOT)
        and SHA256.fullmatch(str(sha or "")) is not None
        and type(size) is int
        and size > 0,
        "source fridge derivative-map artifact differs",
    )
    return {
        "object_path": object_path,
        "package_sha256": sha,
        "package_size_bytes": size,
        "source_receipt_content_digest": receipt["content_digest"],
    }


def plan_execution(
    *,
    attempt_root: Path,
    project_file: Path,
    source_fridge_scene_receipt_path: Path,
    derivative_map_path: str,
    contract_path: Path = binding_contract.CONTRACT_PATH,
    commandlet_path: Path | None = None,
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
    contract_source = _regular_absolute(contract_path, "portable binding contract")
    contract_document = binding_contract.load_contract(contract_source)
    binding_contract.validate_contract(contract_document)
    commandlet_source = _regular_absolute(
        commandlet_path
        or Path(__file__).with_name(
            "compose_hssd_portable_visual_binding_commandlet.py"
        ),
        "fixed commandlet",
    )
    source_receipt_source = _regular_absolute(
        source_fridge_scene_receipt_path, "source fridge scene receipt"
    )
    source_receipt = _load_json(source_receipt_source, "source fridge scene receipt")
    source_map = _source_projection(source_receipt)
    source_package = _beneath(
        _regular_absolute(
            _map_package_file(project, source_map["object_path"]),
            "copied source fridge derivative map",
        ),
        attempt,
        "copied source fridge derivative map",
    )
    _require(
        source_package.stat().st_size == source_map["package_size_bytes"]
        and _sha256(source_package) == source_map["package_sha256"],
        "copied source map bytes differ from completed fridge receipt",
    )
    _require(
        isinstance(derivative_map_path, str)
        and derivative_map_path.startswith(DERIVATIVE_ROOT)
        and derivative_map_path != source_map["object_path"]
        and "." not in derivative_map_path,
        "derivative map is not a fresh portable-binding dev package",
    )
    derivative_package = _map_package_file(project, derivative_map_path)
    _require(
        not derivative_package.exists() and not derivative_package.is_symlink(),
        "portable-binding derivative map already exists",
    )
    execution_path = attempt / EXECUTION_NAME
    receipt_path = attempt / RECEIPT_NAME
    result_path = attempt / RESULT_NAME
    _require(
        not execution_path.exists()
        and not execution_path.is_symlink()
        and not receipt_path.exists()
        and not receipt_path.is_symlink()
        and not result_path.exists()
        and not result_path.is_symlink(),
        "attempt already contains a terminal execution/output",
    )
    inputs = attempt / "inputs"
    _require(
        not inputs.exists() and not inputs.is_symlink(),
        "attempt input directory already exists",
    )
    inputs.mkdir(mode=0o700)
    contract_copy = _copy_exclusive(
        contract_source, inputs / "hssd-portable-visual-binding-contract.json"
    )
    source_receipt_copy = _copy_exclusive(
        source_receipt_source, inputs / "source-articulated-fridge-scene-receipt.json"
    )
    execution = _seal(
        {
            "schema_version": EXECUTION_SCHEMA,
            "mode": "dev_only_fresh_derivative_from_completed_fridge",
            "engine_version": EXPECTED_ENGINE_VERSION,
            "attempt_root": str(attempt),
            "project": {"path": str(project), "sha256": _sha256(project)},
            "source_map": {
                **source_map,
                "package_file": str(source_package),
            },
            "derivative_map": {
                "object_path": derivative_map_path,
                "package_file": str(derivative_package),
            },
            "contract": {
                **contract_copy,
                "contract_id": contract_document["contract_id"],
                "content_digest": contract_document["content_digest"],
            },
            "source_fridge_receipt": {
                **source_receipt_copy,
                "schema_version": source_receipt["schema_version"],
                "content_digest": source_receipt["content_digest"],
            },
            "bindings": _strict_binding_rows(contract_document["bindings"]),
            "commandlet": {
                "path": str(commandlet_source),
                "sha256": _sha256(commandlet_source),
            },
            "outputs": {
                "scene_receipt": str(receipt_path),
                "scene_result": str(result_path),
            },
            "policy": {
                "append_only_attempt": True,
                "isolated_project_required": True,
                "source_map_read_only": True,
                "fresh_derivative_map_required": True,
                "new_level_from_template_required": True,
                "asset_import_or_replacement_forbidden": True,
                "exact_identity_before_delete_required": True,
                "only_visual_shells_may_be_deleted": True,
                "declared_absent_shell_must_be_proved": True,
                "exact_one_visual_shell_may_be_deleted": True,
                "pickup_authority_must_be_preserved": True,
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
    parser.add_argument("--source-fridge-scene-receipt", type=Path, required=True)
    parser.add_argument("--derivative-map", required=True)
    parser.add_argument("--contract", type=Path, default=binding_contract.CONTRACT_PATH)
    parser.add_argument(
        "--commandlet",
        type=Path,
        default=Path(__file__).with_name(
            "compose_hssd_portable_visual_binding_commandlet.py"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        execution = plan_execution(
            attempt_root=args.attempt_root,
            project_file=args.project_file,
            source_fridge_scene_receipt_path=args.source_fridge_scene_receipt,
            derivative_map_path=args.derivative_map,
            contract_path=args.contract,
            commandlet_path=args.commandlet,
        )
    except (
        PortableVisualBindingPlanError,
        binding_contract.PortableVisualBindingContractError,
        OSError,
    ) as exc:
        print(f"VISTA_HSSD_PORTABLE_BINDING_PLAN_FAILED: {exc}")
        return 1
    print(
        "VISTA_HSSD_PORTABLE_BINDING_PLAN_RESULT:"
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
