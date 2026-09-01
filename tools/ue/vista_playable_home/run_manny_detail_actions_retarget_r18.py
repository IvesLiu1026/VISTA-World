#!/usr/bin/env python3
"""Plan or execute the external-only R18 CC0-to-Manny retarget authority.

Dry-run is read-only. Execution creates one append-only project below the
external run root, copies the exact sealed R14 project, overlays the exact R8
pickup/place packages, sealed R15 packages, and pinned Manny content, then runs
author and cold-verify
in separate network-isolated UnrealEditor-Cmd processes. No service, renderer,
GPU allocation, or Git-tracked binary is touched.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
from typing import Any, Mapping, Sequence

from tools.ue.vista_playable_home import build_home
from tools.ue.vista_playable_home import (
    manny_detail_actions_retarget_r18_contract as contract,
)


RUN_PARENT = Path("/data/sysx/vista-world/runs/vista-action-world-r1")
R14_ROOT = RUN_PARENT / "makehuman-cc0-detail-actions-r14-ue57-dev-r1-20260901a"
R15_ROOT = RUN_PARENT / "makehuman-cc0-detail-actions-r15-ue57-dev-r1-20260901b"
R8_ROOT = RUN_PARENT / "makehuman-cc0-animation-ue57-dev-r1-20260901g"
R14_PROJECT = R14_ROOT / "project"
R15_PROJECT = R15_ROOT / "project"
R8_PROJECT = R8_ROOT / "project"
R14_RECEIPT = R14_ROOT / "r14-detail-action-import-receipt.json"
R15_RECEIPT = R15_ROOT / "r15-detail-action-import-receipt.json"
R8_RECEIPT = R8_ROOT / "makehuman-cc0-animation-runtime-receipt.json"
R8_RECEIPT_PIN = (
    "805846cff714165178a9ff182c3c236fc36006d0c2d1d68321a875bb30762e06",
    22_271,
)
R8_RECEIPT_CONTENT_DIGEST = (
    "c4bcfb5a73aceec12ea178e11987b2feb238113e5740be48fac092bd97b51943"
)
R14_RECEIPT_PIN = (
    "2b06f69f6364c4ef50e252312a02e244cb2ee903b5db6875bc33f4453c388004",
    12_879,
)
R15_RECEIPT_PIN = (
    "edd4c1fb700dc65eb4b06f471cf4d18d4afc3630f09cf9051d4816751553df07",
    33_193,
)
R14_RECEIPT_CONTENT_DIGEST = (
    "dc264e8a603a6c50e62c3f77d598a5b2561bd069ed276df32b239f802cfd29bc"
)
R15_RECEIPT_CONTENT_DIGEST = (
    "fe64a325c38b4ec20634487185d73f4af3ca7314a5f21e71f97045805a382087"
)
R14_PROJECT_TREE = (
    "69bc16508e6cbca3186789a44f0c6be0641721d53d1218b5cdaf93fe5c0d138c",
    298,
    100_965_392,
)

MANNY_PROJECT = RUN_PARENT / "hssd-r2-citysample-live-r6-human-fit-20260831a/project"
MANNY_CONTENT = MANNY_PROJECT / "Content/Characters/Mannequins"
MANNY_TREE = (
    "ceef2f97c64b94f888be35713aa73801090214ecd4ab367348c172e3c7502550",
    124,
    405_884_566,
)

ENGINE_ROOT = Path("/mnt/NAS2/yhliu/UE_5.7.3_prebuilt")
UNREAL_EDITOR_CMD = ENGINE_ROOT / "Engine/Binaries/Linux/UnrealEditor-Cmd"
UNREAL_EDITOR_CMD_PIN = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674",
    459_320,
)
BWRAP = Path("/usr/bin/bwrap")
BWRAP_PIN = (
    "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca",
    72_160,
)
WORKER = Path(__file__).with_name("author_manny_detail_actions_retarget_r18.py")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

PROJECT_FILE_NAME = "VistaMakeHumanCC0Import.uproject"
AUTHOR_RECEIPT_NAME = "manny-r18-author-worker.json"
VERIFY_RECEIPT_NAME = "manny-r18-verify-worker.json"
HOST_RECEIPT_NAME = "manny-r18-retarget-host-receipt.json"
EXECUTION_NAME = "manny-r18-retarget-execution.json"
ATTEMPT_RE = re.compile(
    r"^manny-detail-actions-retarget-r18-[a-z0-9]"
    r"(?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
MAX_JSON_BYTES = 4 * 1024 * 1024
TIMEOUT_SECONDS = 3_600

SOURCE_MESH_PIN = (
    "744ebd9afb133f4a6684ce325322133552eee8b4519810ac43d6d404fd8ed832",
    17_892_025,
)
SOURCE_SKELETON_PIN = (
    "7317e28752c20987cb809ba451c50fce2733b080c978ee2e7ddb73426789a5b8",
    66_544,
)
TARGET_MESH_PIN = (
    "f1df1a6b3db170cd80f14c40653fbc9a692af00f7abd575872d9cd8a707e05c6",
    34_534_883,
)
TARGET_SKELETON_PIN = (
    "cd1d96c248d3c4f6b0c086735ee45a441012a1c2fdc1d90e91599d92402e8e58",
    191_340,
)


class RunnerError(RuntimeError):
    """A pinned input, append-only output, or cold verification failed."""


@dataclasses.dataclass(frozen=True)
class FileSeal:
    path: Path
    sha256: str
    size_bytes: int

    def public(self, *, path: str | None = None) -> dict[str, Any]:
        return {
            "path": str(self.path) if path is None else path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclasses.dataclass(frozen=True)
class Config:
    run_parent: Path = RUN_PARENT
    r8_project: Path = R8_PROJECT
    r14_project: Path = R14_PROJECT
    r15_project: Path = R15_PROJECT
    r8_receipt: Path = R8_RECEIPT
    r14_receipt: Path = R14_RECEIPT
    r15_receipt: Path = R15_RECEIPT
    manny_content: Path = MANNY_CONTENT
    engine_root: Path = ENGINE_ROOT
    unreal_editor_cmd: Path = UNREAL_EDITOR_CMD
    bwrap: Path = BWRAP
    repository_root: Path = REPOSITORY_ROOT
    worker: Path = WORKER


@dataclasses.dataclass(frozen=True)
class Plan:
    attempt_name: str
    attempt_root: Path
    config: Config
    r8_receipt: dict[str, Any]
    r14_receipt: dict[str, Any]
    r15_receipt: dict[str, Any]
    r8_seal: FileSeal
    r14_seal: FileSeal
    r15_seal: FileSeal
    r14_tree: build_home.TreeSnapshot
    manny_tree: build_home.TreeSnapshot
    engine: FileSeal
    bwrap: FileSeal
    worker: FileSeal
    report: dict[str, Any]


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RunnerError(message)


def canonical_json(value: Any) -> bytes:
    try:
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
    except (TypeError, ValueError, UnicodeError) as exc:
        raise RunnerError("value is not finite canonical JSON") from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def sha256_file(path: Path) -> FileSeal:
    require(
        path.is_absolute() and path.is_file() and not path.is_symlink(),
        f"invalid regular file: {path}",
    )
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return FileSeal(path, digest.hexdigest(), size)


def require_pin(seal: FileSeal, pin: tuple[str, int], label: str) -> None:
    require((seal.sha256, seal.size_bytes) == pin, f"{label} pin differs")


def strict_json(path: Path, label: str) -> tuple[dict[str, Any], FileSeal]:
    seal = sha256_file(path)
    require(0 < seal.size_bytes <= MAX_JSON_BYTES, f"{label} size differs")
    raw = path.read_bytes()

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
                ValueError(f"non-finite number: {token}")
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise RunnerError(f"{label} is not strict JSON") from exc
    require(
        type(value) is dict and raw == canonical_json(value),
        f"{label} is not canonical JSON",
    )
    return value, seal


def package_path(project: Path, object_path: str) -> Path:
    package = object_path.split(".", 1)[0]
    require(package.startswith("/Game/"), "object path is outside /Game")
    path = project / "Content" / (package.removeprefix("/Game/") + ".uasset")
    require(
        path.resolve().is_relative_to((project / "Content").resolve()),
        "package escaped Content",
    )
    return path


def expected_source_paths(revision: str) -> set[str]:
    return {
        str(spec[key])
        for spec in contract.CLIP_SPECS
        if spec["source_revision"] == revision
        for key in ("source_sequence_object_path", "source_montage_object_path")
    }


def validate_r8_receipt(
    path: Path,
    project: Path,
) -> tuple[dict[str, Any], FileSeal]:
    receipt, seal = strict_json(path, "R8 runtime receipt")
    require_pin(seal, R8_RECEIPT_PIN, "R8 runtime receipt")
    gates = receipt.get("gates", {})
    claims = receipt.get("claims", {})
    bindings = receipt.get("runtime_authoring_result", {})
    require(
        receipt.get("schema_version")
        == "vista.makehuman-cc0-ue57-animation-runtime-receipt/v1"
        and receipt.get("status")
        == "cc0_animation_runtime_assets_saved_reloaded_pending_runtime"
        and receipt.get("accepted") is False
        and receipt.get("error") is None
        and receipt.get("content_digest") == R8_RECEIPT_CONTENT_DIGEST
        and receipt.get("content_digest") == content_digest(receipt)
        and gates.get("packages_saved_reloaded") is True
        and gates.get("pickup_place_montages_authored") is True
        and gates.get("typed_notify_frames_and_signals_verified") is True
        and gates.get("existing_r6_skeleton_bound") is True
        and claims.get("runtime_assets_authored") is True
        and claims.get("runtime_interaction_verified") is False
        and bindings.get("status") == "success"
        and bindings.get("accepted") is False,
        "R8 runtime receipt authority differs",
    )
    expected = expected_source_paths("R8")
    inventory = receipt.get("package_inventory")
    require(type(inventory) is list, "R8 package inventory is unavailable")
    selected = {
        str(item.get("object_path")): item
        for item in inventory
        if str(item.get("object_path")) in expected
    }
    require(set(selected) == expected, "R8 pickup/place package closure differs")
    for object_path, item in selected.items():
        require(
            type(item) is dict
            and set(item)
            == {
                "class_path",
                "object_path",
                "package_name",
                "project_relative_path",
                "sha256",
                "size_bytes",
            },
            "R8 pickup/place package inventory shape differs",
        )
        expected_class = (
            "/Script/Engine.AnimSequence"
            if "/Sequences/" in object_path
            else "/Script/Engine.AnimMontage"
        )
        source = project / str(item["project_relative_path"])
        source_seal = sha256_file(source)
        require(
            item["class_path"] == expected_class
            and source == package_path(project, object_path)
            and (source_seal.sha256, source_seal.size_bytes)
            == (item["sha256"], item["size_bytes"]),
            f"R8 source package differs: {object_path}",
        )
    expected_sequences = {
        str(spec["source_sequence_object_path"])
        for spec in contract.CLIP_SPECS
        if spec["source_revision"] == "R8"
    }
    inspections = {
        str(item.get("object_path")): item
        for item in receipt.get("sequence_inspection", [])
        if str(item.get("object_path")) in expected_sequences
    }
    require(set(inspections) == expected_sequences, "R8 sequence inspection differs")
    require(
        all(
            item.get("frame_count") == 60
            and item.get("sample_rate") == {"denominator": 1, "numerator": 30}
            and item.get("loop_contract") is False
            and item.get("force_root_lock") is True
            and item.get("root_motion_enabled") is False
            and item.get("root_motion_lock_type") == "REF_POSE"
            and item.get("skeleton") == contract.SOURCE_SKELETON_OBJECT_PATH
            for item in inspections.values()
        ),
        "R8 pickup/place sequence authority differs",
    )
    return receipt, seal


def validate_import_receipt(
    path: Path,
    project: Path,
    revision: str,
    pin: tuple[str, int],
    receipt_digest: str,
) -> tuple[dict[str, Any], FileSeal]:
    receipt, seal = strict_json(path, f"{revision} import receipt")
    require_pin(seal, pin, f"{revision} import receipt")
    expected_schema = (
        "vista.makehuman-cc0-r14-ue57-import-receipt/v1"
        if revision == "R14"
        else "vista.makehuman-cc0-r15-ue57-import-receipt/v1"
    )
    expected_status = (
        "r14_detail_actions_saved_reloaded_pending_runtime_review"
        if revision == "R14"
        else "r15_detail_actions_saved_reloaded_pending_runtime_review"
    )
    require(
        receipt.get("schema_version") == expected_schema
        and receipt.get("status") == expected_status
        and receipt.get("accepted") is False
        and receipt.get("error") is None
        and receipt.get("content_digest") == receipt_digest
        and receipt.get("content_digest") == content_digest(receipt)
        and receipt.get("gates", {}).get("packages_saved_reloaded") is True
        and receipt.get("gates", {}).get("typed_notify_frames_and_signals_verified")
        is True
        and receipt.get("gates", {}).get("existing_r6_53_bone_skeleton_bound") is True
        and receipt.get("claims", {}).get("runtime_assets_authored") is True
        and receipt.get("claims", {}).get("runtime_interaction_verified") is False,
        f"{revision} import receipt authority differs",
    )
    inventory = receipt.get("package_inventory")
    require(type(inventory) is list, f"{revision} package inventory is unavailable")
    observed = {str(item.get("object_path")) for item in inventory}
    require(
        observed == expected_source_paths(revision),
        f"{revision} package inventory closure differs",
    )
    for item in inventory:
        require(
            type(item) is dict
            and set(item)
            == {
                "class_path",
                "object_path",
                "package_name",
                "project_relative_path",
                "sha256",
                "size_bytes",
            },
            f"{revision} package inventory shape differs",
        )
        source = project / str(item["project_relative_path"])
        source_seal = sha256_file(source)
        require(
            (source_seal.sha256, source_seal.size_bytes)
            == (item["sha256"], item["size_bytes"])
            and source == package_path(project, str(item["object_path"])),
            f"{revision} source package differs: {item['object_path']}",
        )
    return receipt, seal


def validate_tree(
    root: Path, expected: tuple[str, int, int], label: str
) -> build_home.TreeSnapshot:
    snapshot = build_home.snapshot_tree(root, label)
    require(
        (snapshot.sha256, snapshot.file_count, snapshot.total_bytes) == expected,
        f"{label} tree pin differs",
    )
    return snapshot


def validate_attempt_name(name: str) -> None:
    require(
        ATTEMPT_RE.fullmatch(name) is not None,
        "attempt name differs from the closed R18 namespace",
    )


def build_plan(attempt_name: str, config: Config = Config()) -> Plan:
    validate_attempt_name(attempt_name)
    require(
        config.run_parent.is_absolute() and config.run_parent.is_dir(),
        "run parent is unavailable",
    )
    attempt_root = config.run_parent / attempt_name
    require(
        attempt_root.parent == config.run_parent and not attempt_root.exists(),
        "attempt root already exists",
    )
    r8_receipt, r8_seal = validate_r8_receipt(
        config.r8_receipt,
        config.r8_project,
    )
    r14_receipt, r14_seal = validate_import_receipt(
        config.r14_receipt,
        config.r14_project,
        "R14",
        R14_RECEIPT_PIN,
        R14_RECEIPT_CONTENT_DIGEST,
    )
    r15_receipt, r15_seal = validate_import_receipt(
        config.r15_receipt,
        config.r15_project,
        "R15",
        R15_RECEIPT_PIN,
        R15_RECEIPT_CONTENT_DIGEST,
    )
    r14_tree = validate_tree(config.r14_project, R14_PROJECT_TREE, "R14 base project")
    manny_tree = validate_tree(config.manny_content, MANNY_TREE, "Manny content")
    source_mesh = sha256_file(
        package_path(config.r14_project, contract.SOURCE_MESH_OBJECT_PATH)
    )
    source_skeleton = sha256_file(
        package_path(config.r14_project, contract.SOURCE_SKELETON_OBJECT_PATH)
    )
    target_mesh = sha256_file(
        package_path(config.manny_content.parents[2], contract.TARGET_MESH_OBJECT_PATH)
    )
    target_skeleton = sha256_file(
        package_path(
            config.manny_content.parents[2], contract.TARGET_SKELETON_OBJECT_PATH
        )
    )
    require_pin(source_mesh, SOURCE_MESH_PIN, "source CC0 mesh")
    require_pin(source_skeleton, SOURCE_SKELETON_PIN, "source CC0 skeleton")
    require_pin(target_mesh, TARGET_MESH_PIN, "target Manny mesh")
    require_pin(target_skeleton, TARGET_SKELETON_PIN, "target Manny skeleton")
    engine = sha256_file(config.unreal_editor_cmd)
    bwrap = sha256_file(config.bwrap)
    worker = sha256_file(config.worker)
    require_pin(engine, UNREAL_EDITOR_CMD_PIN, "UnrealEditor-Cmd")
    require_pin(bwrap, BWRAP_PIN, "bubblewrap")
    require(
        config.repository_root.is_absolute()
        and config.worker.is_relative_to(config.repository_root),
        "worker repository binding differs",
    )
    report = seal_document(
        {
            "accepted": False,
            "attempt_name": attempt_name,
            "claims": contract.NEGATIVE_CLAIMS,
            "inputs": {
                "manny_content_tree": {
                    "file_count": manny_tree.file_count,
                    "sha256": manny_tree.sha256,
                    "total_bytes": manny_tree.total_bytes,
                },
                "r14_base_project_tree": {
                    "file_count": r14_tree.file_count,
                    "sha256": r14_tree.sha256,
                    "total_bytes": r14_tree.total_bytes,
                },
                "r8_receipt": r8_seal.public(),
                "r14_receipt": r14_seal.public(),
                "r15_receipt": r15_seal.public(),
                "source_mesh": source_mesh.public(),
                "source_skeleton": source_skeleton.public(),
                "target_mesh": target_mesh.public(),
                "target_skeleton": target_skeleton.public(),
                "worker": worker.public(),
            },
            "legal_scope": contract.LEGAL_SCOPE,
            "output": {
                "asset_count": len(contract.EXPECTED_INVENTORY),
                "content_namespace": contract.CONTENT_NAMESPACE,
                "external_only": True,
                "root": str(attempt_root),
            },
            "schema_version": contract.PLAN_SCHEMA,
            "status": "dry_run_validated_zero_write",
            "tools": {
                "bubblewrap": bwrap.public(),
                "unreal_editor_cmd": engine.public(),
            },
            "writes_performed": False,
        }
    )
    return Plan(
        attempt_name,
        attempt_root,
        config,
        r8_receipt,
        r14_receipt,
        r15_receipt,
        r8_seal,
        r14_seal,
        r15_seal,
        r14_tree,
        manny_tree,
        engine,
        bwrap,
        worker,
        report,
    )


def copy_file(source: Path, destination: Path) -> FileSeal:
    require(
        not destination.exists() and not destination.is_symlink(),
        f"copy destination exists: {destination}",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination, follow_symlinks=False)
    source_seal = sha256_file(source)
    destination_seal = sha256_file(destination)
    require(
        (source_seal.sha256, source_seal.size_bytes)
        == (destination_seal.sha256, destination_seal.size_bytes),
        "copied file differs",
    )
    return destination_seal


def overlay_receipt_packages(
    receipt: Mapping[str, Any],
    source_project: Path,
    project: Path,
    *,
    object_paths: set[str] | None = None,
) -> None:
    for item in receipt["package_inventory"]:
        if object_paths is not None and str(item["object_path"]) not in object_paths:
            continue
        source = source_project / str(item["project_relative_path"])
        destination = project / str(item["project_relative_path"])
        copied = copy_file(source, destination)
        require(
            (copied.sha256, copied.size_bytes) == (item["sha256"], item["size_bytes"]),
            "overlaid source package differs",
        )


def records(snapshot: build_home.TreeSnapshot) -> dict[str, tuple[int, int, str]]:
    return {path: (mode, size, sha256) for path, mode, size, sha256 in snapshot.records}


def expected_added_paths() -> set[str]:
    return {
        item["object_path"].split(".", 1)[0].removeprefix("/Game/") + ".uasset"
        for item in contract.EXPECTED_INVENTORY
    }


def validate_content_delta(
    before: build_home.TreeSnapshot, after: build_home.TreeSnapshot
) -> None:
    before_records = records(before)
    after_records = records(after)
    added = set(after_records) - set(before_records)
    require(
        added == expected_added_paths()
        and not (set(before_records) - set(after_records))
        and all(after_records[path] == value for path, value in before_records.items()),
        "project Content changed outside the exact R18 package delta",
    )
    require(
        not any("VISTA_R18_RETARGET_TMP_" in path for path in after_records),
        "temporary retarget package remains on disk",
    )


def source_asset_seals(project: Path, *, sandbox_paths: bool) -> list[dict[str, Any]]:
    result = []
    for spec in contract.CLIP_SPECS:
        for key in ("source_sequence_object_path", "source_montage_object_path"):
            object_path = str(spec[key])
            path = package_path(project, object_path)
            seal = sha256_file(path)
            exposed_path = (
                "/vista/work/project/"
                + str(path.relative_to(project)).replace(os.sep, "/")
                if sandbox_paths
                else str(path)
            )
            result.append(
                {
                    "object_path": object_path,
                    **seal.public(path=exposed_path),
                }
            )
    return sorted(result, key=lambda item: item["object_path"])


def validate_copied_authority(
    project: Path, expected_sources: list[dict[str, Any]]
) -> None:
    observed = source_asset_seals(project, sandbox_paths=True)
    require(
        observed == expected_sources,
        "one or more copied source animation packages changed",
    )
    require_pin(
        sha256_file(package_path(project, contract.SOURCE_MESH_OBJECT_PATH)),
        SOURCE_MESH_PIN,
        "copied source mesh",
    )
    require_pin(
        sha256_file(package_path(project, contract.SOURCE_SKELETON_OBJECT_PATH)),
        SOURCE_SKELETON_PIN,
        "copied source skeleton",
    )
    require_pin(
        sha256_file(package_path(project, contract.TARGET_MESH_OBJECT_PATH)),
        TARGET_MESH_PIN,
        "copied target mesh",
    )
    require_pin(
        sha256_file(package_path(project, contract.TARGET_SKELETON_OBJECT_PATH)),
        TARGET_SKELETON_PIN,
        "copied target skeleton",
    )


def write_exclusive(path: Path, value: Mapping[str, Any]) -> FileSeal:
    require(
        path.is_absolute() and path.parent.is_dir() and not path.exists(),
        f"exclusive output exists: {path}",
    )
    raw = canonical_json(value)
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return sha256_file(path)


def bwrap_command(plan: Plan, execution_sha: str, mode: str) -> list[str]:
    log_name = f"manny-r18-{mode}-engine.log"
    worker_relative = plan.config.worker.relative_to(plan.config.repository_root)
    return [
        str(plan.config.bwrap),
        "--die-with-parent",
        "--new-session",
        "--unshare-net",
        "--unshare-pid",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--symlink",
        "usr/sbin",
        "/sbin",
        "--ro-bind",
        "/etc",
        "/etc",
        "--ro-bind",
        "/sys",
        "/sys",
        "--tmpfs",
        "/home",
        "--tmpfs",
        "/root",
        "--tmpfs",
        "/run",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/var",
        "--tmpfs",
        "/var/tmp",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/vista",
        "--dir",
        "/vista/engine",
        "--dir",
        "/vista/source",
        "--dir",
        "/vista/work",
        "--ro-bind",
        str(plan.config.engine_root),
        "/vista/engine",
        "--ro-bind",
        str(plan.config.repository_root),
        "/vista/source",
        "--bind",
        str(plan.attempt_root),
        "/vista/work",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/vista/work/runtime/home",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "PYTHONNOUSERSITE",
        "1",
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--setenv",
        contract.EXECUTION_ENV,
        "/vista/work/inputs/" + EXECUTION_NAME,
        "--setenv",
        contract.EXECUTION_SHA_ENV,
        execution_sha,
        "--setenv",
        contract.MODE_ENV,
        mode,
        "--chdir",
        "/vista/work",
        "--",
        "/vista/engine/Engine/Binaries/Linux/UnrealEditor-Cmd",
        "/vista/work/project/" + PROJECT_FILE_NAME,
        "-nullrhi",
        "-nosound",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-NoAssetRegistryCache",
        "-NoHotReloadFromIDE",
        "-NoEngineChanges",
        "-ddc=InstalledNoZenLocalFallback",
        "-EnablePlugins=VistaPlayableHome",
        "-ExecutePythonScript=/vista/source/" + str(worker_relative),
        "-AbsLog=/vista/work/evidence/" + log_name,
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def run_process(argv: Sequence[str], stdout: Path, stderr: Path) -> None:
    with stdout.open("xb") as stdout_stream, stderr.open("xb") as stderr_stream:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=stdout_stream,
            stderr=stderr_stream,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise RunnerError("UE R18 retarget process timed out") from exc
    require(code == 0, f"UE R18 retarget process exited {code}")


def validate_worker_receipt(
    path: Path, mode: str, execution_sha: str
) -> tuple[dict[str, Any], FileSeal]:
    receipt, seal = strict_json(path, f"{mode} worker receipt")
    require(
        receipt.get("schema_version") == contract.WORKER_SCHEMA
        and receipt.get("mode") == mode
        and receipt.get("accepted") is False
        and receipt.get("error") is None
        and receipt.get("execution_sha256") == execution_sha
        and receipt.get("content_digest") == content_digest(receipt)
        and receipt.get("claims") == contract.NEGATIVE_CLAIMS
        and receipt.get("legal_scope") == contract.LEGAL_SCOPE
        and len(receipt.get("inspection", {}).get("asset_inventory", []))
        == len(contract.EXPECTED_INVENTORY)
        and receipt.get("inspection", {}).get("temporary_assets_absent") is True,
        f"{mode} worker receipt differs",
    )
    return receipt, seal


def package_inventory(project: Path) -> list[dict[str, Any]]:
    result = []
    for item in sorted(
        contract.EXPECTED_INVENTORY, key=lambda value: value["object_path"]
    ):
        path = package_path(project, item["object_path"])
        seal = sha256_file(path)
        result.append(
            {
                **item,
                "project_relative_path": str(path.relative_to(project)).replace(
                    os.sep, "/"
                ),
                "sha256": seal.sha256,
                "size_bytes": seal.size_bytes,
            }
        )
    return result


def execute(plan: Plan, acknowledgement: str) -> dict[str, Any]:
    require(
        acknowledgement == contract.ACKNOWLEDGEMENT, "exact acknowledgement is required"
    )
    require(not plan.attempt_root.exists(), "attempt root already exists")
    # Revalidate all mutable authorities before the first append-only write.
    build_plan(plan.attempt_name, plan.config)
    plan.attempt_root.mkdir(mode=0o700)
    project = plan.attempt_root / "project"
    evidence = plan.attempt_root / "evidence"
    inputs = plan.attempt_root / "inputs"
    runtime = plan.attempt_root / "runtime"
    evidence.mkdir(mode=0o700)
    inputs.mkdir(mode=0o700)
    runtime.mkdir(mode=0o700)
    (runtime / "home").mkdir(mode=0o700)
    shutil.copytree(plan.config.r14_project, project, symlinks=False)
    overlay_receipt_packages(
        plan.r8_receipt,
        plan.config.r8_project,
        project,
        object_paths=expected_source_paths("R8"),
    )
    overlay_receipt_packages(plan.r15_receipt, plan.config.r15_project, project)
    manny_destination = project / "Content/Characters/Mannequins"
    require(not manny_destination.exists(), "Manny overlay destination already exists")
    shutil.copytree(plan.config.manny_content, manny_destination, symlinks=False)
    copied_sources = source_asset_seals(project, sandbox_paths=True)
    validate_copied_authority(project, copied_sources)
    before = build_home.snapshot_tree(project / "Content", "prepared R18 Content")
    worker_sandbox_path = "/vista/source/" + str(
        plan.config.worker.relative_to(plan.config.repository_root)
    )
    execution_document = {
        "acknowledgement": contract.ACKNOWLEDGEMENT,
        "author_output": "/vista/work/evidence/" + AUTHOR_RECEIPT_NAME,
        "clip_count": len(contract.CLIP_SPECS),
        "content_namespace": contract.CONTENT_NAMESPACE,
        "engine_version": "5.7.3-50162420+++UE5+Release-5.7",
        "mode_outputs": [contract.AUTHOR_MODE, contract.VERIFY_MODE],
        "project_file": "/vista/work/project/" + PROJECT_FILE_NAME,
        "schema_version": contract.EXECUTION_SCHEMA,
        "source_asset_seals": copied_sources,
        "source_mesh_object_path": contract.SOURCE_MESH_OBJECT_PATH,
        "target_mesh_object_path": contract.TARGET_MESH_OBJECT_PATH,
        "verify_output": "/vista/work/evidence/" + VERIFY_RECEIPT_NAME,
        "worker_script": plan.worker.public(path=worker_sandbox_path),
    }
    execution_seal = write_exclusive(inputs / EXECUTION_NAME, execution_document)
    run_process(
        bwrap_command(plan, execution_seal.sha256, contract.AUTHOR_MODE),
        evidence / "manny-r18-author-stdout.log",
        evidence / "manny-r18-author-stderr.log",
    )
    author_receipt, author_seal = validate_worker_receipt(
        evidence / AUTHOR_RECEIPT_NAME, contract.AUTHOR_MODE, execution_seal.sha256
    )
    validate_copied_authority(project, copied_sources)
    run_process(
        bwrap_command(plan, execution_seal.sha256, contract.VERIFY_MODE),
        evidence / "manny-r18-verify-stdout.log",
        evidence / "manny-r18-verify-stderr.log",
    )
    verify_receipt, verify_seal = validate_worker_receipt(
        evidence / VERIFY_RECEIPT_NAME, contract.VERIFY_MODE, execution_seal.sha256
    )
    validate_copied_authority(project, copied_sources)
    require(
        author_receipt["inspection"] == verify_receipt["inspection"],
        "cold verification inspection differs from author inspection",
    )
    after = build_home.snapshot_tree(project / "Content", "completed R18 Content")
    validate_content_delta(before, after)
    receipt = seal_document(
        {
            "accepted": False,
            "attempt_name": plan.attempt_name,
            "claims": contract.NEGATIVE_CLAIMS,
            "content_delta": {
                "added_paths": sorted(expected_added_paths()),
                "existing_files_byte_identical": True,
                "temporary_assets_absent": True,
            },
            "content_namespace": contract.CONTENT_NAMESPACE,
            "evidence": {
                "author_worker": author_seal.public(),
                "execution": execution_seal.public(),
                "verify_worker": verify_seal.public(),
            },
            "legal_scope": contract.LEGAL_SCOPE,
            "package_inventory": package_inventory(project),
            "schema_version": contract.HOST_RECEIPT_SCHEMA,
            "source_assets_byte_identical_after_author_and_verify": True,
            "status": contract.SUCCESS_STATUS,
        }
    )
    write_exclusive(plan.attempt_root / HOST_RECEIPT_NAME, receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--attempt-name", required=True)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--acknowledgement", default="")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    plan = build_plan(args.attempt_name)
    output = execute(plan, args.acknowledgement) if args.execute else plan.report
    print(canonical_json(output).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
