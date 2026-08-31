#!/usr/bin/env python3
"""Plan or execute an isolated UE 5.7 import of the sealed CC0 R15 actions.

Planning is read-only.  Execution is append-only, CPU/NullRHI-only, network
isolated, and requires both a literal acknowledgement and explicit pins for a
fresh BuildPlugin package containing the R15 closed editor bridge.  The fixed
source attempt, worker receipt, R3 character project, engine, and bubblewrap
binary are all byte-pinned.  No command here launches a renderer or service.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.ue.vista_playable_home import build_home
from tools.ue.vista_playable_home import (
    makehuman_cc0_detail_actions_r15_contract as commandlet_contract,
)


PLAN_SCHEMA = "vista.makehuman-cc0-r15-ue57-dev-import-plan/v1"
HOST_SCHEMA = "vista.makehuman-cc0-r15-ue57-dev-import-host/v1"
COMPLETE_STATUS = "r15_detail_action_dev_import_complete_unaccepted_nonpromotable"
BLOCKED_STATUS = "blocked_pending_fresh_compiled_plugin_authority"
ACKNOWLEDGEMENT = commandlet_contract.EXECUTION_ACKNOWLEDGEMENT

RUN_PARENT = Path("/data/sysx/vista-world/runs/vista-action-world-r1")
SOURCE_ROOT = (
    RUN_PARENT / "makehuman-cc0-detail-actions-r15-source-r1-20260901b"
)
SOURCE_RECEIPT = SOURCE_ROOT / "evidence/worker-receipt.json"
SOURCE_RECEIPT_SHA256 = commandlet_contract.SOURCE_RECEIPT_SHA256
SOURCE_RECEIPT_SIZE = commandlet_contract.SOURCE_RECEIPT_SIZE
SOURCE_CONTENT_DIGEST = commandlet_contract.SOURCE_CONTENT_DIGEST

R3_ROOT = RUN_PARENT / "makehuman-cc0-ue-import-r3-20260829"
R3_PROJECT_ROOT = R3_ROOT / "project"
R3_RECEIPT = R3_ROOT / "makehuman-cc0-import-host-receipt.json"
R3_RECEIPT_SHA256 = (
    "ef7c198ed1726b9c1857fd63c2a8ba93e7fce0e5f82f2b566152890c76d852d7"
)
R3_RECEIPT_SIZE = 48_560
R3_RECEIPT_CONTENT_DIGEST = (
    "f5a09afe52e7e97792b99e08f2b38a78bfcbfb99fe9f0bee6627b468acbf9a46"
)
R3_PROJECT_PROJECTION = {
    "sha256": "b8a116993c3f1d7a9cae6fb93f1fe247e973c92d2ab90e564993cb406d7f40f0",
    "file_count": 24,
    "directory_count": 11,
    "total_bytes": 43_545_997,
}

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
COMMANDLET = Path(__file__).with_name(
    "makehuman_cc0_detail_actions_r15_commandlet.py"
)

ATTEMPT_RE = re.compile(
    r"^makehuman-cc0-detail-actions-r15-ue57-dev-r1-[a-z0-9]"
    r"(?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROJECT_FILE_NAME = "VistaMakeHumanCC0Import.uproject"
RESULT_NAME = "r15-detail-action-import-result.json"
RECEIPT_NAME = "r15-detail-action-import-receipt.json"
HOST_NAME = "r15-detail-action-dev-import-host-manifest.json"
STDOUT_NAME = "r15-detail-action-ue-stdout.log"
STDERR_NAME = "r15-detail-action-ue-stderr.log"
ENGINE_LOG_NAME = "r15-detail-action-ue-engine.log"
MAX_JSON_BYTES = 4 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 3_600
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600

DEV_CLAIMS = {
    "accepted_research_evidence": False,
    "ai_or_vlm_data_pipeline_authorized": False,
    "dataset_or_database_authorized": False,
    "dedicated_server_two_client_verified": False,
    "gta_level_quality": False,
    "human_motion_quality_accepted": False,
    "human_operated_development_only": True,
    "nonpromotable": True,
    "photoreal_character_accepted": False,
    "production_authority": False,
    "runtime_interaction_verified": False,
}


class DetailActionImportError(RuntimeError):
    """A closed input, plugin authority, or append-only operation failed."""


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
class PluginAuthority:
    root: Path
    tree_sha256: str
    file_count: int
    total_bytes: int


@dataclasses.dataclass(frozen=True)
class Config:
    run_parent: Path = RUN_PARENT
    source_root: Path = SOURCE_ROOT
    source_receipt: Path = SOURCE_RECEIPT
    r3_project_root: Path = R3_PROJECT_ROOT
    r3_receipt: Path = R3_RECEIPT
    engine_root: Path = ENGINE_ROOT
    unreal_editor_cmd: Path = UNREAL_EDITOR_CMD
    bwrap: Path = BWRAP
    commandlet: Path = COMMANDLET


PRODUCTION_CONFIG = Config()


@dataclasses.dataclass(frozen=True)
class ImportPlan:
    attempt_name: str
    attempt_root: Path
    report: dict[str, Any]
    source_receipt: dict[str, Any]
    source_receipt_seal: FileSeal
    source_fbx: tuple[tuple[dict[str, Any], FileSeal], ...]
    r3_receipt: dict[str, Any]
    r3_tree: build_home.TreeSnapshot
    engine: FileSeal
    bwrap: FileSeal
    commandlet: FileSeal
    plugin_authority: PluginAuthority | None
    plugin_tree: build_home.TreeSnapshot | None
    config: Config


def require(condition: Any, message: str) -> None:
    if not condition:
        raise DetailActionImportError(message)


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
        raise DetailActionImportError("value is not finite canonical JSON") from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def strict_json(
    raw: bytes, label: str, *, require_canonical: bool = True
) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, label + " contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError("non-finite JSON number: " + token)
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise DetailActionImportError(label + " is not strict JSON") from exc
    require(type(value) is dict, label + " root is not an object")
    if require_canonical:
        require(raw == canonical_json(value), label + " is not canonical JSON")
    return value


def read_file(
    path: Path, label: str, *, maximum: int | None = None
) -> tuple[bytes, FileSeal]:
    require(path.is_absolute(), label + " path is not absolute")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise DetailActionImportError(label + " is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), label + " is not a regular file")
        if maximum is not None:
            require(before.st_size <= maximum, label + " exceeds size policy")
        chunks: list[bytes] = []
        digest = hashlib.sha256()
        size = 0
        while True:
            block = os.read(descriptor, CHUNK_BYTES)
            if not block:
                break
            chunks.append(block)
            digest.update(block)
            size += len(block)
        after = os.fstat(descriptor)
        require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and size == before.st_size,
            label + " changed while reading",
        )
        raw = b"".join(chunks)
        return raw, FileSeal(path.resolve(), digest.hexdigest(), size)
    finally:
        os.close(descriptor)


def validate_tool(path: Path, pin: tuple[str, int], label: str) -> FileSeal:
    _, seal = read_file(path, label)
    require((seal.sha256, seal.size_bytes) == pin, label + " seal differs")
    require(os.access(path, os.X_OK), label + " is not executable")
    return seal


def validate_source(config: Config) -> tuple[
    dict[str, Any], FileSeal, tuple[tuple[dict[str, Any], FileSeal], ...]
]:
    raw, receipt_seal = read_file(
        config.source_receipt, "R15 worker receipt", maximum=MAX_JSON_BYTES
    )
    require(
        (receipt_seal.sha256, receipt_seal.size_bytes)
        == (SOURCE_RECEIPT_SHA256, SOURCE_RECEIPT_SIZE),
        "R15 worker receipt seal differs",
    )
    receipt = strict_json(raw, "R15 worker receipt")
    require(
        receipt.get("schema_version") == commandlet_contract.SOURCE_RECEIPT_SCHEMA
        and receipt.get("status")
        == "fresh_cc0_r15_detail_actions_roundtrip_verified_source_only"
        and receipt.get("acceptance")
        == {
            "accepted": False,
            "human_reviewed": False,
            "runtime_execution_authorized": False,
        }
        and receipt.get("content_digest") == SOURCE_CONTENT_DIGEST
        and receipt.get("content_digest") == content_digest(receipt)
        and receipt.get("plan_content_digest")
        == commandlet_contract.SOURCE_PLAN_CONTENT_DIGEST
        and receipt.get("profile_content_digest")
        == commandlet_contract.SOURCE_PROFILE_CONTENT_DIGEST
        and receipt.get("gates", {}).get("fbx_roundtrip_verified") is True
        and receipt.get("gates", {}).get("exact_53_bone_contract") is True
        and receipt.get("gates", {}).get("nine_distinct_numeric_actions") is True
        and receipt.get("gates", {}).get("root_motion_absent") is True
        and receipt.get("gates", {}).get("loop_seam_verified") is True
        and receipt.get("gates", {}).get("existing_r8_or_r14_bytes_reused") is False
        and receipt.get("claims", {}).get("ue_animation_imported") is False
        and receipt.get("claims", {}).get("typed_notifies_authored_in_ue") is False
        and receipt.get("claims", {}).get("runtime_interaction_verified") is False
        and receipt.get("claims", {}).get("human_motion_quality_accepted") is False,
        "R15 worker receipt contract differs",
    )
    artifacts = {
        item.get("relative_path"): item
        for item in receipt.get("artifacts", [])
        if type(item) is dict
    }
    sources: list[tuple[dict[str, Any], FileSeal]] = []
    for spec in commandlet_contract.CLIP_SPECS:
        relative = "fbx/" + spec["source_name"]
        item = artifacts.get(relative)
        require(
            item
            == {
                "relative_path": relative,
                "sha256": spec["source_sha256"],
                "size_bytes": spec["source_size_bytes"],
            },
            "R15 worker artifact record differs: " + relative,
        )
        path = config.source_root / "artifacts" / relative
        _, seal = read_file(path, "R15 FBX " + spec["clip_id"])
        require(
            (seal.sha256, seal.size_bytes)
            == (spec["source_sha256"], spec["source_size_bytes"]),
            "R15 FBX seal differs: " + spec["clip_id"],
        )
        sources.append((copy.deepcopy(spec), seal))
    return receipt, receipt_seal, tuple(sources)


def validate_r3(config: Config) -> tuple[dict[str, Any], build_home.TreeSnapshot]:
    raw, seal = read_file(config.r3_receipt, "R3 host receipt", maximum=MAX_JSON_BYTES)
    require(
        (seal.sha256, seal.size_bytes) == (R3_RECEIPT_SHA256, R3_RECEIPT_SIZE),
        "R3 host receipt seal differs",
    )
    receipt = strict_json(raw, "R3 host receipt", require_canonical=False)
    require(
        receipt.get("schema_version")
        == "vista.makehuman-cc0-ue57-import-host-receipt/v1"
        and receipt.get("status") == "cc0_skeletal_import_post_exit_project_sealed"
        and receipt.get("accepted") is False
        and receipt.get("content_digest") == R3_RECEIPT_CONTENT_DIGEST
        and receipt.get("output_project_projection") == R3_PROJECT_PROJECTION
        and receipt.get("claims", {}).get("ue_skeletal_imported") is True
        and receipt.get("claims", {}).get("exact_53_bones_verified") is True,
        "R3 host receipt contract differs",
    )
    tree = build_home.snapshot_tree(config.r3_project_root, "R3 character project")
    require(
        tree.file_count == R3_PROJECT_PROJECTION["file_count"]
        and tree.total_bytes == R3_PROJECT_PROJECTION["total_bytes"],
        "R3 project size projection differs",
    )
    by_relative = {relative: (size, digest) for relative, _, size, digest in tree.records}
    for item in receipt.get("package_inventory", []):
        relative = item.get("project_relative_path")
        require(
            by_relative.get(relative) == (item.get("size_bytes"), item.get("sha256")),
            "R3 package differs: " + str(relative),
        )
    return receipt, tree


def validate_plugin(
    authority: PluginAuthority, config: Config,
) -> build_home.TreeSnapshot:
    root = authority.root.resolve()
    require(root.is_dir(), "compiled plugin root is unavailable")
    require(
        str(root).startswith(str(config.run_parent.resolve()) + os.sep)
        and "VISTA-World-worktrees" not in str(root),
        "compiled plugin must be an external append-only run artifact",
    )
    tree = build_home.snapshot_tree(root, "fresh compiled R15 plugin")
    require(
        (tree.sha256, tree.file_count, tree.total_bytes)
        == (
            authority.tree_sha256,
            authority.file_count,
            authority.total_bytes,
        ),
        "compiled plugin tree authority differs",
    )
    required = {
        "VistaPlayableHome.uplugin",
        "Binaries/Linux/UnrealEditor.modules",
        "Binaries/Linux/libUnrealEditor-VistaPlayableHome.so",
        "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so",
    }
    paths = {item[0] for item in tree.records}
    require(required <= paths, "compiled plugin editor closure is incomplete")
    modules_raw, _ = read_file(
        root / "Binaries/Linux/UnrealEditor.modules",
        "compiled plugin module manifest",
        maximum=64 * 1024,
    )
    try:
        modules = json.loads(modules_raw.decode("utf-8", "strict"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise DetailActionImportError("compiled plugin module manifest is invalid") from exc
    require(
        set(modules.get("Modules", {}))
        >= {"VistaPlayableHome", "VistaPlayableHomeEditor"},
        "compiled plugin module identities differ",
    )
    return tree


def plugin_authority_from_values(
    root: str | None,
    tree_sha256: str | None,
    file_count: int | None,
    total_bytes: int | None,
) -> PluginAuthority | None:
    values = (root, tree_sha256, file_count, total_bytes)
    if all(value is None for value in values):
        return None
    require(all(value is not None for value in values), "all plugin pins are required")
    require(
        SHA256_RE.fullmatch(str(tree_sha256)) is not None
        and type(file_count) is int
        and file_count > 0
        and type(total_bytes) is int
        and total_bytes > 0,
        "compiled plugin pins are invalid",
    )
    path = Path(str(root))
    require(path.is_absolute(), "compiled plugin root must be absolute")
    return PluginAuthority(path, str(tree_sha256), file_count, total_bytes)


def build_plan(
    attempt_name: str,
    *,
    plugin_authority: PluginAuthority | None = None,
    config: Config = PRODUCTION_CONFIG,
) -> ImportPlan:
    require(ATTEMPT_RE.fullmatch(attempt_name) is not None, "attempt name is invalid")
    attempt_root = (config.run_parent / attempt_name).resolve()
    require(attempt_root.parent == config.run_parent.resolve(), "attempt path escaped")
    source_receipt, source_seal, sources = validate_source(config)
    r3_receipt, r3_tree = validate_r3(config)
    engine = validate_tool(
        config.unreal_editor_cmd, UNREAL_EDITOR_CMD_PIN, "UE 5.7 commandlet"
    )
    bwrap = validate_tool(config.bwrap, BWRAP_PIN, "bubblewrap")
    _, commandlet = read_file(config.commandlet, "R15 import commandlet")
    plugin_tree = (
        validate_plugin(plugin_authority, config)
        if plugin_authority is not None
        else None
    )
    ready = plugin_tree is not None
    report = seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "mode": "dry_run_zero_writes",
            "status": "ready_for_cpu_only_dev_import" if ready else BLOCKED_STATUS,
            "accepted": False,
            "attempt_name": attempt_name,
            "attempt_root": str(attempt_root),
            "writes_performed": False,
            "will_run_unreal": False,
            "gpu_allowed": False,
            "network_allowed": False,
            "interactive_renderer_allowed": False,
            "source": {
                "attempt_root": str(config.source_root),
                "worker_receipt": source_seal.public(),
                "worker_receipt_content_digest": source_receipt["content_digest"],
                "fbx": [seal.public() for _, seal in sources],
            },
            "r3_character_project": {
                "root": str(config.r3_project_root),
                "tree_sha256": r3_tree.sha256,
                "file_count": r3_tree.file_count,
                "total_bytes": r3_tree.total_bytes,
                "receipt_content_digest": r3_receipt["content_digest"],
            },
            "compiled_plugin": (
                None
                if plugin_tree is None
                else {
                    "root": str(plugin_authority.root),
                    "tree_sha256": plugin_tree.sha256,
                    "file_count": plugin_tree.file_count,
                    "total_bytes": plugin_tree.total_bytes,
                }
            ),
            "engine": engine.public(),
            "bubblewrap": bwrap.public(),
            "commandlet": commandlet.public(),
            "content_namespace": commandlet_contract.CONTENT_NAMESPACE,
            "expected_inventory": copy.deepcopy(
                list(commandlet_contract.EXPECTED_INVENTORY)
            ),
            "remaining_gates": (
                []
                if ready
                else [
                    "native BuildPlugin after R15 editor bridge compile",
                    "independently record exact plugin tree pins",
                ]
            ),
            "claims": copy.deepcopy(DEV_CLAIMS),
        }
    )
    return ImportPlan(
        attempt_name,
        attempt_root,
        report,
        source_receipt,
        source_seal,
        sources,
        r3_receipt,
        r3_tree,
        engine,
        bwrap,
        commandlet,
        plugin_authority,
        plugin_tree,
        config,
    )


def copy_file(source: Path, destination: Path, label: str) -> FileSeal:
    require(not destination.exists(), label + " destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as reader, destination.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=CHUNK_BYTES)
    except OSError as exc:
        raise DetailActionImportError(label + " copy failed") from exc
    os.chmod(destination, PRIVATE_FILE_MODE)
    _, seal = read_file(destination, label + " copy")
    return seal


def write_exclusive(path: Path, value: Mapping[str, Any]) -> FileSeal:
    raw = canonical_json(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            PRIVATE_FILE_MODE,
        )
    except OSError as exc:
        raise DetailActionImportError("output already exists: " + str(path)) from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    _, seal = read_file(path, "written JSON")
    return seal


def commandlet_execution(
    project_descriptor: FileSeal,
    source_receipt: FileSeal,
    source_fbx: Sequence[tuple[dict[str, Any], FileSeal]],
    commandlet: FileSeal,
) -> dict[str, Any]:
    return seal_document(
        {
            "schema_version": commandlet_contract.EXECUTION_SCHEMA,
            "mode": "apply",
            "execution_acknowledgement": ACKNOWLEDGEMENT,
            "attempt_root": "/vista/work",
            "project_root": "/vista/work/project",
            "project_file": "/vista/work/project/" + PROJECT_FILE_NAME,
            "project_sha256": project_descriptor.sha256,
            "content_namespace": commandlet_contract.CONTENT_NAMESPACE,
            "skeleton_object_path": commandlet_contract.SKELETON_OBJECT_PATH,
            "mesh_object_path": commandlet_contract.MESH_OBJECT_PATH,
            "source_worker_receipt": {
                **source_receipt.public(path="/vista/input/source-worker-receipt.json"),
                "content_digest": SOURCE_CONTENT_DIGEST,
            },
            "source_fbx": [
                {
                    "clip_id": spec["clip_id"],
                    "path": "/vista/input/fbx/" + spec["source_name"],
                    "sha256": seal.sha256,
                    "size_bytes": seal.size_bytes,
                }
                for spec, seal in source_fbx
            ],
            "clip_specs": [
                {
                    key: copy.deepcopy(value)
                    for key, value in spec.items()
                    if key not in {"source_sha256", "source_size_bytes"}
                }
                for spec, _ in source_fbx
            ],
            "expected_inventory": copy.deepcopy(
                list(commandlet_contract.EXPECTED_INVENTORY)
            ),
            "commandlet": commandlet.public(path="/vista/input/commandlet.py"),
            "import_receipt": "/vista/work/" + RECEIPT_NAME,
            "import_result": "/vista/work/" + RESULT_NAME,
            "claims": copy.deepcopy(commandlet_contract.NEGATIVE_CLAIMS),
        }
    )


def bwrap_command(plan: ImportPlan, input_root: Path, execution_sha: str) -> list[str]:
    config = plan.config
    return [
        str(config.bwrap), "--die-with-parent", "--new-session", "--unshare-net",
        "--unshare-pid", "--clearenv", "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64", "--symlink", "usr/sbin", "/sbin",
        "--ro-bind", "/etc", "/etc", "--ro-bind", "/sys", "/sys",
        "--tmpfs", "/home", "--tmpfs", "/root", "--tmpfs", "/run",
        "--tmpfs", "/tmp", "--dir", "/var", "--tmpfs", "/var/tmp",
        "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/vista",
        "--dir", "/vista/engine", "--dir", "/vista/input", "--dir", "/vista/work",
        "--ro-bind", str(config.engine_root), "/vista/engine",
        "--ro-bind", str(input_root), "/vista/input",
        "--bind", str(plan.attempt_root), "/vista/work",
        "--tmpfs", "/vista/work/control", "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "HOME", "/vista/work/runtime/home", "--setenv", "TMPDIR", "/tmp",
        "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONNOUSERSITE", "1",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--setenv", commandlet_contract.EXECUTION_ENV, "/vista/input/execution.json",
        "--setenv", commandlet_contract.EXECUTION_SHA_ENV, execution_sha,
        "--chdir", "/vista/work", "--",
        "/vista/engine/Engine/Binaries/Linux/UnrealEditor-Cmd",
        "/vista/work/project/" + PROJECT_FILE_NAME,
        "-nullrhi", "-nosound", "-unattended", "-nop4", "-nosplash",
        "-NoAssetRegistryCache", "-NoHotReloadFromIDE", "-NoEngineChanges",
        "-DDC-ForceMemoryCache", "-EnablePlugins=VistaPlayableHome",
        "-ExecutePythonScript=/vista/input/commandlet.py",
        "-AbsLog=/vista/work/" + ENGINE_LOG_NAME,
        "-stdout", "-FullStdOutLogOutput",
    ]


def run_process(argv: Sequence[str], stdout: Path, stderr: Path) -> int:
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
            return process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                process.wait()
            raise DetailActionImportError("UE R15 import timed out") from exc


def execute_import(plan: ImportPlan, acknowledgement: str) -> dict[str, Any]:
    require(acknowledgement == ACKNOWLEDGEMENT, "exact acknowledgement is required")
    require(plan.plugin_tree is not None, "compiled plugin authority is required")
    require(plan.plugin_authority is not None, "compiled plugin binding is required")
    require(not plan.attempt_root.exists(), "attempt root already exists")
    # Revalidate every mutable host input before the first append-only write.
    validate_source(plan.config)
    validate_r3(plan.config)
    validate_tool(
        plan.config.unreal_editor_cmd,
        UNREAL_EDITOR_CMD_PIN,
        "UE 5.7 commandlet",
    )
    validate_tool(plan.config.bwrap, BWRAP_PIN, "bubblewrap")
    _, current_commandlet = read_file(
        plan.config.commandlet, "R15 import commandlet"
    )
    require(
        (current_commandlet.sha256, current_commandlet.size_bytes)
        == (plan.commandlet.sha256, plan.commandlet.size_bytes),
        "R15 import commandlet changed after planning",
    )
    validate_plugin(plan.plugin_authority, plan.config)
    plan.attempt_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    project = plan.attempt_root / "project"
    try:
        shutil.copytree(plan.config.r3_project_root, project, symlinks=False)
    except (OSError, shutil.Error) as exc:
        raise DetailActionImportError("R3 project copy failed") from exc
    copied_r3 = build_home.snapshot_tree(project, "copied R3 project")
    require(
        (copied_r3.sha256, copied_r3.file_count, copied_r3.total_bytes)
        == (plan.r3_tree.sha256, plan.r3_tree.file_count, plan.r3_tree.total_bytes),
        "copied R3 project differs",
    )
    try:
        shutil.copytree(
            plan.plugin_authority.root,
            project / "Plugins/VistaPlayableHome",
            symlinks=False,
        )
    except (OSError, shutil.Error) as exc:
        raise DetailActionImportError("compiled plugin copy failed") from exc
    copied_plugin = build_home.snapshot_tree(
        project / "Plugins/VistaPlayableHome", "copied compiled R15 plugin"
    )
    require(
        (
            copied_plugin.sha256,
            copied_plugin.file_count,
            copied_plugin.total_bytes,
        )
        == (
            plan.plugin_tree.sha256,
            plan.plugin_tree.file_count,
            plan.plugin_tree.total_bytes,
        ),
        "copied compiled plugin differs",
    )
    input_root = plan.attempt_root / "control/input"
    (input_root / "fbx").mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE)
    source_receipt = copy_file(
        plan.source_receipt_seal.path,
        input_root / "source-worker-receipt.json",
        "source worker receipt",
    )
    require(
        (source_receipt.sha256, source_receipt.size_bytes)
        == (plan.source_receipt_seal.sha256, plan.source_receipt_seal.size_bytes),
        "copied source worker receipt differs",
    )
    commandlet = copy_file(
        plan.commandlet.path, input_root / "commandlet.py", "R15 commandlet"
    )
    require(
        (commandlet.sha256, commandlet.size_bytes)
        == (plan.commandlet.sha256, plan.commandlet.size_bytes),
        "copied R15 commandlet differs",
    )
    copied_sources: list[tuple[dict[str, Any], FileSeal]] = []
    for spec, seal in plan.source_fbx:
        copied = copy_file(
            seal.path, input_root / "fbx" / spec["source_name"], spec["clip_id"]
        )
        require(
            (copied.sha256, copied.size_bytes) == (seal.sha256, seal.size_bytes),
            "copied FBX differs",
        )
        copied_sources.append((spec, copied))
    _, descriptor = read_file(project / PROJECT_FILE_NAME, "copied project descriptor")
    execution = commandlet_execution(
        descriptor, source_receipt, copied_sources, commandlet
    )
    execution_seal = write_exclusive(input_root / "execution.json", execution)
    for current, directories, files in os.walk(input_root, topdown=False):
        for name in files:
            os.chmod(Path(current) / name, 0o400)
        for name in directories:
            os.chmod(Path(current) / name, 0o500)
    os.chmod(input_root, 0o500)
    argv = bwrap_command(plan, input_root, execution_seal.sha256)
    return_code = run_process(
        argv, plan.attempt_root / STDOUT_NAME, plan.attempt_root / STDERR_NAME
    )
    require(return_code == 0, "UE R15 import exited nonzero")
    result_raw, result_seal = read_file(
        plan.attempt_root / RESULT_NAME, "R15 commandlet result", maximum=MAX_JSON_BYTES
    )
    receipt_raw, receipt_seal = read_file(
        plan.attempt_root / RECEIPT_NAME,
        "R15 commandlet receipt",
        maximum=MAX_JSON_BYTES,
    )
    result = strict_json(result_raw, "R15 commandlet result")
    receipt = strict_json(receipt_raw, "R15 commandlet receipt")
    require(
        result.get("schema_version") == commandlet_contract.RESULT_SCHEMA
        and result.get("status") == commandlet_contract.SUCCESS_STATUS
        and result.get("receipt_sha256") == receipt_seal.sha256
        and receipt.get("schema_version") == commandlet_contract.RECEIPT_SCHEMA
        and receipt.get("status") == commandlet_contract.SUCCESS_STATUS
        and receipt.get("accepted") is False
        and receipt.get("content_digest") == content_digest(receipt)
        and len(receipt.get("package_inventory", [])) == 18
        and receipt.get("claims", {}).get("ue_animation_imported") is True
        and receipt.get("claims", {}).get("runtime_interaction_verified") is False,
        "R15 commandlet terminal evidence differs",
    )
    host = seal_document(
        {
            "schema_version": HOST_SCHEMA,
            "status": COMPLETE_STATUS,
            "accepted": False,
            "attempt_name": plan.attempt_name,
            "attempt_root": str(plan.attempt_root),
            "project_root": str(project),
            "bindings": {
                "plan_content_digest": plan.report["content_digest"],
                "source_worker_receipt": source_receipt.public(),
                "compiled_plugin_tree_sha256": plan.plugin_tree.sha256,
                "execution": execution_seal.public(),
                "commandlet": commandlet.public(),
                "commandlet_result": result_seal.public(),
                "commandlet_receipt": receipt_seal.public(),
                "engine": plan.engine.public(),
            },
            "package_inventory": receipt["package_inventory"],
            "interactive_renderer_launched": False,
            "gpu_used": False,
            "network_available": False,
            "service_changed": False,
            "claims": copy.deepcopy(DEV_CLAIMS),
        }
    )
    write_exclusive(plan.attempt_root / HOST_NAME, host)
    return host


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("plan", "execute"):
        child = commands.add_parser(name)
        child.add_argument("--attempt-name", required=True)
        child.add_argument("--plugin-root")
        child.add_argument("--plugin-tree-sha256")
        child.add_argument("--plugin-file-count", type=int)
        child.add_argument("--plugin-total-bytes", type=int)
        if name == "execute":
            child.add_argument("--acknowledgement", required=True)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        authority = plugin_authority_from_values(
            arguments.plugin_root,
            arguments.plugin_tree_sha256,
            arguments.plugin_file_count,
            arguments.plugin_total_bytes,
        )
        plan = build_plan(arguments.attempt_name, plugin_authority=authority)
        result = (
            plan.report
            if arguments.command == "plan"
            else execute_import(plan, arguments.acknowledgement)
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except DetailActionImportError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
