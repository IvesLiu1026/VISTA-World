#!/usr/bin/env python3
"""Plan or supervise the provenance-closed R5 multi-client UE proof.

Dry-run is the default and performs no writes. The proof does not accept a
caller-selected Unreal binary, project, plugin tree, or prebuilt proof module.
It binds one Git-tracked source projection read-only, builds that projection
with a pinned UE 5.7.3 UBT toolchain, and then runs one dedicated-server PIE
world plus two real client PIE worlds under ``-nullrhi``.

Success requires a zero runtime exit and an atomically closed receipt that is
cross-bound to the trusted Git commit, source projection, input manifest,
launch plan, and UBT build provenance. Process log text is never proof.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


PLAN_SCHEMA = "vista.r5-multiclient-proof-plan/v3"
INPUT_SCHEMA = "vista.r5-multiclient-proof-input/v2"
BUILD_SCHEMA = "vista.r5-multiclient-proof-build/v2"
PROJECTION_SCHEMA = "vista.r5-multiclient-trusted-projection/v2"
RECEIPT_SCHEMA = "vista.r5-multiclient-proof-receipt/v3"
ENGINE_MANIFEST_SCHEMA = "vista.r5-immutable-engine-tree/v1"
ACCEPTANCE_SCHEMA = "vista.r5-multiclient-proof-acceptance/v1"
HARNESS_NAME = "ue-cqtest-pie-dedicated-server-two-clients"
AUTOMATION_TEST = (
    "VISTA.R5.VistaR5MultiClientProof.ReplicatesTransactionalPhysicalState"
)
TRUSTED_REPO_ROOT = Path(__file__).resolve().parents[3]
TRUSTED_ENGINE_ROOT = Path("/data/vista-authorities/ue-5.7.3-r1/engine")
TRUSTED_ENGINE_MANIFEST = Path(
    "/data/vista-authorities/ue-5.7.3-r1/engine-full-tree-manifest.json"
)
# Root must provision the authority, run the checked-in admin audit, then pin
# both digests here. Unprovisioned values intentionally stop even dry-run.
ENGINE_MANIFEST_SHA256 = "IMMUTABLE_ENGINE_AUTHORITY_REQUIRED"
ENGINE_TREE_ROOT_DIGEST = "IMMUTABLE_ENGINE_AUTHORITY_REQUIRED"
TRUSTED_PROJECT_RELATIVE = Path("tools/runtime/vista_playable_home/r5_trusted_project")
TRUSTED_PROJECTION_RELATIVE = Path(
    "tools/runtime/vista_playable_home/r5_trusted_projection.json"
)
SUPERVISOR_RELATIVE = Path("tools/runtime/vista_playable_home/r5_multiclient_proof.py")
RUNTIME_WRAPPER_RELATIVE = Path(
    "tools/runtime/vista_playable_home/r5_runtime_capture.py"
)
ENGINE_ADMIN_RELATIVE = Path(
    "tools/runtime/vista_playable_home/r5_engine_authority_admin.py"
)
ENGINE_PROVISION_RELATIVE = Path(
    "tools/runtime/vista_playable_home/provision_immutable_engine_authority.sh"
)
PLUGIN_RELATIVE = Path("unreal_plugins/VistaPlayableHome")
PLUGIN_DESCRIPTOR_RELATIVE = PLUGIN_RELATIVE / "VistaPlayableHome.uplugin"
PLUGIN_SOURCE_RELATIVE = PLUGIN_RELATIVE / "Source"
PLUGIN_CONFIG_RELATIVE = PLUGIN_RELATIVE / "Config"
BWRAP_PATH = Path("/usr/bin/bwrap")
BWRAP_SHA256 = "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
BWRAP_BYTES = 72_160
TRUSTED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ATTEMPT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{14,94})[a-z0-9]$")
HEX_BITS_RE = re.compile(r"^(?:[0-9a-f]{8}|[0-9a-f]{16})$")
HEX_40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_RECEIPT_BYTES = 512 * 1024
LAUNCH_DIGEST_PLACEHOLDER = "__VISTA_LAUNCH_DIGEST__"
BUILD_DIGEST_PLACEHOLDER = "__VISTA_BUILD_DIGEST__"
RUNTIME_ENVELOPE_SCHEMA = "vista.r5-private-runtime-envelope/v1"
RUNTIME_ENVELOPE_MARKER = "VISTA_R5_PRIVATE_ENVELOPE_V1:"
MAX_RUNTIME_STDOUT_BYTES = 8 * 1024 * 1024
MAX_AUTOMATION_REPORT_BYTES = 4 * 1024 * 1024
AUTHORITY_STAT = os.stat
AUTHORITY_LSTAT = os.lstat
AUTHORITY_ACCESS = os.access
CALLER_UID = os.geteuid()
SOURCE_FD_PREFIX = "__VISTA_SOURCE_FD_"
BUILD_OUTPUT_FD_PREFIX = "__VISTA_BUILD_OUTPUT_FD_"

CHECKPOINT_NAMES = (
    "initial_free",
    "held_after_pickup",
    "held_after_rollback",
    "placed",
    "held_again",
    "free_after_drop",
)
CHECKPOINT_DISPOSITIONS = ("free", "held", "held", "placed", "held", "free")
CARRIER_A = "home.r5/entity.proof_carrier_a"
PICKUP = "home.r5/entity.proof_cup"
PLACEMENT_ANCHOR = "home.r5/entity.proof_table/anchor.cup"

BUILD_OUTPUT_LAYOUT = (
    (
        "project_module",
        "project_binaries",
        Path("Linux/libUnrealEditor-VistaR5Proof.so"),
        True,
    ),
    (
        "plugin_runtime_module",
        "plugin_binaries",
        Path("Linux/libUnrealEditor-VistaPlayableHome.so"),
        True,
    ),
    (
        "plugin_editor_module",
        "plugin_binaries",
        Path("Linux/libUnrealEditor-VistaPlayableHomeEditor.so"),
        True,
    ),
    ("project_modules", "project_binaries", Path("Linux/UnrealEditor.modules"), False),
    ("plugin_modules", "plugin_binaries", Path("Linux/UnrealEditor.modules"), False),
)

TOP_KEYS = frozenset(
    {
        "schema",
        "status",
        "attempt_id",
        "engine_version",
        "harness",
        "client_count",
        "worlds_per_checkpoint",
        "trusted_git_commit",
        "trusted_projection_digest",
        "input_manifest_digest",
        "launch_plan_digest",
        "build_provenance_digest",
        "checkpoints",
        "transactions",
    }
)
CHECKPOINT_KEYS = frozenset({"name", "worlds"})
WORLD_KEYS = frozenset(
    {
        "checkpoint",
        "role",
        "client_index",
        "net_mode",
        "net_driver_is_server",
        "pickup_has_authority",
        "carrier_has_authority",
        "disposition",
        "carrier_semantic_id",
        "inventory_item_semantic_id",
        "placement_anchor_semantic_id",
        "simulate_physics",
        "collision_enabled",
        "collision_profile",
        "attachment_parent_name",
        "attachment_socket",
        "world_transform_bits",
        "attachment_relative_transform_bits",
        "linear_velocity_bits",
        "angular_velocity_bits",
        "actual_simulate_physics",
        "actual_collision_enabled",
        "actual_collision_profile",
        "actual_world_transform_bits",
        "actual_relative_transform_bits",
        "actual_linear_velocity_bits",
        "actual_angular_velocity_bits",
    }
)
TRANSACTION_KEYS = frozenset(
    {
        "command_id",
        "status",
        "code",
        "physical_mutation_count",
        "contact_mutation_attempted",
        "contact_committed",
        "rollback_attempted",
        "rolled_back",
        "before_disposition",
        "contact_disposition",
        "after_disposition",
    }
)
TRANSACTIONS_KEYS = frozenset(
    {
        "event_reset_while_active",
        "pickup",
        "exact_retry",
        "command_id_collision",
        "failed_place_rollback",
        "place",
        "pickup_again",
        "drop",
    }
)
RESET_KEYS = frozenset(
    {
        "claim",
        "accepted",
        "code",
        "has_active_action_after_rejection",
        "before_event",
        "after_rejection_event",
        "active_transaction",
    }
)
EVENT_STATE_KEYS = frozenset(
    {
        "active_event_id",
        "event_status",
        "session_generation",
        "public_goal",
        "terminal_condition_id",
    }
)
AUTOMATION_REPORT_KEYS = frozenset(
    {
        "devices",
        "reportCreatedOn",
        "succeeded",
        "succeededWithWarnings",
        "failed",
        "notRun",
        "inProcess",
        "totalDuration",
        "comparisonExported",
        "comparisonExportDirectory",
        "tests",
    }
)
AUTOMATION_TEST_KEYS = frozenset(
    {
        "testDisplayName",
        "fullTestPath",
        "tags",
        "state",
        "deviceInstance",
        "duration",
        "dateTime",
        "entries",
        "warnings",
        "errors",
        "artifacts",
    }
)


@dataclass(frozen=True)
class ToolPin:
    label: str
    relative: Path
    sha256: str
    size_bytes: int
    executable: bool = False

    def as_json(self) -> dict[str, object]:
        return {
            "label": self.label,
            "path": self.relative.as_posix(),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "executable": self.executable,
        }


# Supplemental critical-file expectations. These are not the engine closure;
# closure comes from the root-owned full-tree authority and pinned tree digest.
CRITICAL_ENGINE_EXPECTATIONS: tuple[ToolPin, ...] = (
    ToolPin(
        "unreal_editor_cmd",
        Path("Engine/Binaries/Linux/UnrealEditor-Cmd"),
        "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674",
        459_320,
        True,
    ),
    ToolPin(
        "build_version",
        Path("Engine/Build/Build.version"),
        "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef",
        215,
    ),
    ToolPin(
        "installed_build_marker",
        Path("Engine/Build/InstalledBuild.txt"),
        "54c76dab44960cadb4719b2b0e59a32ff3a768ac199663b4de40a0c75dce781d",
        6,
    ),
    ToolPin(
        "cqtest_primary_source",
        Path(
            "Engine/Source/Developer/CQTest/Private/Components/PIENetworkComponent.cpp"
        ),
        "1b993a876c25279cf3985dab6ed5dee9978d3f1a0d50d781a751d15fe929a987",
        8_853,
    ),
    ToolPin(
        "cqtest_binary",
        Path("Engine/Binaries/Linux/libUnrealEditor-CQTest.so"),
        "b3817858bc3a5164772a2609b0be292a8359ad74dd974e366cc112437ab2b170",
        217_240,
    ),
    ToolPin(
        "unreal_core_binary",
        Path("Engine/Binaries/Linux/libUnrealEditor-Core.so"),
        "1baae28f56ca22e79a6bb68f113baa2bc37ae2090422b4ad95596d8c13978dd1",
        23_275_872,
    ),
    ToolPin(
        "unreal_core_uobject_binary",
        Path("Engine/Binaries/Linux/libUnrealEditor-CoreUObject.so"),
        "0e95132f0ba5948e7dc4907d752d62b9fde085c94cfd742e2e58fdc714634c56",
        12_963_608,
    ),
    ToolPin(
        "unreal_engine_binary",
        Path("Engine/Binaries/Linux/libUnrealEditor-Engine.so"),
        "b91ed49d859792101e2002d53ab6445b3dac75fd35603f0fd55db29998a9df1b",
        92_508_824,
    ),
    ToolPin(
        "unreal_editor_module_binary",
        Path("Engine/Binaries/Linux/libUnrealEditor-UnrealEd.so"),
        "a267c9519f3c3ffcce75d125e561eef4bab46f15f018a8fac09585c160eeda32",
        43_113_776,
    ),
    ToolPin(
        "unreal_json_binary",
        Path("Engine/Binaries/Linux/libUnrealEditor-Json.so"),
        "1da7c31e25a0e8c6a6a402501131013ff1811d125fb397812095f5f2feea2b02",
        1_097_568,
    ),
    ToolPin(
        "unreal_editor_modules",
        Path("Engine/Binaries/Linux/UnrealEditor.modules"),
        "e100b80b47e8a11a68c9d082f2e199642c2b7f0cb5fbbe99072a2e6fec606e6a",
        29_678,
    ),
    ToolPin(
        "run_ubt",
        Path("Engine/Build/BatchFiles/RunUBT.sh"),
        "1ec2bef59f75d03fdb28c4a56c72a52eb646fff625c0c8988f814b85bb5db2c9",
        1_429,
        True,
    ),
    ToolPin(
        "ubt_linux_environment",
        Path("Engine/Build/BatchFiles/Linux/SetupEnvironment.sh"),
        "4c5ca84d5b296ef57f868b4a34d181740df5efb860591001f6109bbd0ceca331",
        795,
        True,
    ),
    ToolPin(
        "ubt_binary",
        Path("Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll"),
        "9fdba0a5d367148218233314f12e2d27640504c77497c7911bfb915d4c9889e2",
        3_030_528,
    ),
    ToolPin(
        "ubt_deps",
        Path("Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.deps.json"),
        "66d2d54593443dd8d4bdba0005d6d9822b6a237d774fd48b4e76e44a76018a78",
        86_059,
    ),
    ToolPin(
        "ubt_runtimeconfig",
        Path(
            "Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.runtimeconfig.json"
        ),
        "d3531540a412f186faa17ea00491a3ea870f4fe4ea6669a3be0e254fda098606",
        691,
    ),
    ToolPin(
        "bundled_dotnet",
        Path("Engine/Binaries/ThirdParty/DotNet/8.0.412/linux-x64/dotnet"),
        "16248f01cb85154458b2cbbf8ce78a160e5e5e3f0befa6c34023dcb07ba1e2f6",
        68_264,
        True,
    ),
)


class ProofError(RuntimeError):
    """A closed proof contract failed."""


@dataclass(frozen=True)
class FileSeal:
    path: Path
    sha256: str
    size_bytes: int

    def as_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class ReceiptExpectation:
    attempt_id: str
    trusted_git_commit: str
    trusted_projection_digest: str
    input_manifest_digest: str
    launch_plan_digest: str
    build_provenance_digest: str


@dataclass(frozen=True)
class ProofInputs:
    repo_root: Path
    git_commit: str
    projection_document: Mapping[str, Any]
    projection_digest: str
    source_seals: tuple[FileSeal, ...]
    engine_manifest_document: Mapping[str, Any]
    engine_manifest_digest: str
    engine_tree_root_digest: str
    toolchain_seals: tuple[FileSeal, ...]
    bwrap: FileSeal
    attempt_root: Path
    output_root: Path
    attempt_id: str
    timeout_seconds: float
    input_document: Mapping[str, Any]
    input_digest: str


@dataclass(frozen=True)
class ProofPlan:
    inputs: ProofInputs
    build_command: tuple[str, ...]
    runtime_command_template: tuple[str, ...]
    launch_document: Mapping[str, Any]
    launch_digest: str

    def as_json(self) -> Mapping[str, Any]:
        return self.launch_document


@dataclass(frozen=True)
class BuildProvenance:
    document: Mapping[str, Any]
    digest: str
    output_seals: tuple[FileSeal, ...]


@dataclass(frozen=True)
class ImmutableInputSnapshot:
    """Anonymous sealed files substituted into a bubblewrap command."""

    token_fds: Mapping[str, int]

    @property
    def pass_fds(self) -> tuple[int, ...]:
        return tuple(self.token_fds.values())


def _fail(message: str) -> None:
    raise ProofError(message)


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _seal_document(payload: Mapping[str, Any]) -> dict[str, Any]:
    if "content_digest" in payload:
        _fail("unsealed payload must not contain content_digest")
    digest = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    return {**payload, "content_digest": digest}


def _validate_sealed_document(value: Mapping[str, Any], schema: str, label: str) -> str:
    if value.get("schema") != schema:
        _fail(f"{label} schema differs")
    digest = value.get("content_digest")
    if not isinstance(digest, str) or not HEX_64_RE.fullmatch(digest):
        _fail(f"{label} content_digest is invalid")
    payload = dict(value)
    del payload["content_digest"]
    if hashlib.sha256(_canonical_json_bytes(payload)).hexdigest() != digest:
        _fail(f"{label} content_digest differs")
    return digest


def _canonical_existing(path: Path, label: str, *, directory: bool) -> Path:
    if not path.is_absolute() or path.is_symlink():
        _fail(f"{label} must be an absolute non-symlink path")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ProofError(f"{label} does not exist") from exc
    if resolved != path:
        _fail(f"{label} must already be canonical")
    if directory and not path.is_dir():
        _fail(f"{label} must be a directory")
    if not directory and not path.is_file():
        _fail(f"{label} must be a file")
    return path


def _seal(path: Path, label: str, *, executable: bool = False) -> FileSeal:
    canonical = _canonical_existing(path, label, directory=False)
    mode = canonical.stat().st_mode
    if not stat.S_ISREG(mode):
        _fail(f"{label} must be a regular file")
    if executable and mode & 0o111 == 0:
        _fail(f"{label} must be executable")
    digest = hashlib.sha256()
    with canonical.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return FileSeal(canonical, digest.hexdigest(), canonical.stat().st_size)


def _same_seal(left: FileSeal, right: FileSeal) -> bool:
    return left == right


def _json_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProofError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    return value


def _git_bytes(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        _fail("trusted projection is not available as exact Git blobs")
    return completed.stdout


def _expected_bound_source_paths(repo: Path) -> tuple[Path, ...]:
    roots = (
        repo / PLUGIN_SOURCE_RELATIVE,
        repo / PLUGIN_CONFIG_RELATIVE,
        repo / TRUSTED_PROJECT_RELATIVE,
    )
    paths = {
        PLUGIN_DESCRIPTOR_RELATIVE,
        SUPERVISOR_RELATIVE,
        RUNTIME_WRAPPER_RELATIVE,
        ENGINE_ADMIN_RELATIVE,
        ENGINE_PROVISION_RELATIVE,
    }
    for root in roots:
        _canonical_existing(root, f"trusted source root {root}", directory=True)
        for path in root.rglob("*"):
            if path.is_symlink():
                _fail("trusted source projection must not contain symlinks")
            if path.is_file():
                paths.add(path.relative_to(repo))
    return tuple(sorted(paths, key=lambda item: item.as_posix()))


def _expected_toolchain_json() -> dict[str, Any]:
    return {
        "engine_root": str(TRUSTED_ENGINE_ROOT),
        "engine_manifest": str(TRUSTED_ENGINE_MANIFEST),
        "engine_manifest_sha256": ENGINE_MANIFEST_SHA256,
        "engine_tree_root_digest": ENGINE_TREE_ROOT_DIGEST,
        "critical_file_expectations": [
            pin.as_json() for pin in CRITICAL_ENGINE_EXPECTATIONS
        ],
        "bwrap": {
            "path": str(BWRAP_PATH),
            "sha256": BWRAP_SHA256,
            "size_bytes": BWRAP_BYTES,
        },
    }


def _load_trusted_projection(
    repo_root: Path,
) -> tuple[str, Mapping[str, Any], str, tuple[FileSeal, ...]]:
    repo = _canonical_existing(repo_root, "trusted repository", directory=True)
    top = _git_bytes(repo, "rev-parse", "--show-toplevel").decode().strip()
    if Path(top) != repo:
        _fail("trusted repository root differs from Git toplevel")
    commit = _git_bytes(repo, "rev-parse", "HEAD^{commit}").decode().strip()
    if not HEX_40_RE.fullmatch(commit):
        _fail("trusted Git commit is not canonical SHA-1")

    manifest_path = _canonical_existing(
        repo / TRUSTED_PROJECTION_RELATIVE,
        "trusted projection manifest",
        directory=False,
    )
    manifest_bytes = manifest_path.read_bytes()
    manifest_blob = _git_bytes(
        repo, "show", f"{commit}:{TRUSTED_PROJECTION_RELATIVE.as_posix()}"
    )
    if manifest_blob != manifest_bytes:
        _fail("trusted projection manifest differs from its HEAD blob")
    manifest = _json_object(manifest_path, "trusted projection manifest")
    if frozenset(manifest) != frozenset(
        {"schema", "source_files", "toolchain", "content_digest"}
    ):
        _fail("trusted projection manifest fields differ")
    projection_digest = _validate_sealed_document(
        manifest, PROJECTION_SCHEMA, "trusted projection manifest"
    )
    if manifest.get("toolchain") != _expected_toolchain_json():
        _fail("trusted projection toolchain pins differ from supervisor authority")

    entries = manifest.get("source_files")
    if not isinstance(entries, list):
        _fail("trusted projection source_files must be an array")
    expected_paths = _expected_bound_source_paths(repo)
    actual_paths: list[Path] = []
    seals: list[FileSeal] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or frozenset(entry) != frozenset(
            {"path", "sha256", "size_bytes"}
        ):
            _fail(f"trusted projection source_files[{index}] is not closed")
        relative_text = entry.get("path")
        digest = entry.get("sha256")
        size = entry.get("size_bytes")
        if not isinstance(relative_text, str) or not relative_text:
            _fail("trusted projection source path is invalid")
        relative = Path(relative_text)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != relative_text
        ):
            _fail("trusted projection source path is not canonical relative POSIX")
        if not isinstance(digest, str) or not HEX_64_RE.fullmatch(digest):
            _fail("trusted projection source digest is invalid")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            _fail("trusted projection source size is invalid")
        path = repo / relative
        seal = _seal(path, f"trusted source {relative_text}")
        if seal.sha256 != digest or seal.size_bytes != size:
            _fail(f"trusted source {relative_text} differs from projection manifest")
        if _git_bytes(repo, "show", f"{commit}:{relative_text}") != path.read_bytes():
            _fail(f"trusted source {relative_text} differs from its HEAD blob")
        actual_paths.append(relative)
        seals.append(seal)
    if tuple(actual_paths) != expected_paths or len(set(actual_paths)) != len(
        actual_paths
    ):
        _fail("trusted projection bound-source inventory differs")
    return commit, manifest, projection_digest, tuple(seals)


def _engine_authority_fail(message: str) -> None:
    _fail(f"IMMUTABLE_ENGINE_AUTHORITY_REQUIRED: {message}")


def _authority_chain(path: Path, label: str) -> None:
    if not path.is_absolute():
        _engine_authority_fail(f"{label} path is not absolute")
    chain = [path, *path.parents]
    for candidate in reversed(chain):
        try:
            info = AUTHORITY_LSTAT(candidate)
        except OSError:
            _engine_authority_fail(f"{label} path is missing: {candidate}")
        if stat.S_ISLNK(info.st_mode):
            _engine_authority_fail(f"{label} path chain contains a symlink")
        if info.st_uid != 0 or info.st_uid == CALLER_UID:
            _engine_authority_fail(f"{label} path is not root-admin owned")
        if stat.S_IMODE(info.st_mode) & 0o022:
            _engine_authority_fail(f"{label} path is group/world writable")
        try:
            writable = AUTHORITY_ACCESS(candidate, os.W_OK, effective_ids=True)
        except TypeError:
            writable = AUTHORITY_ACCESS(candidate, os.W_OK)
        if writable:
            _engine_authority_fail(f"{label} path is writable by the caller")


def _engine_inventory(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in sorted(directory_names):
            candidate = base / name
            if candidate.is_symlink():
                _engine_authority_fail("engine tree contains a symlink")
            paths.append(candidate)
        for name in sorted(file_names):
            candidate = base / name
            if candidate.is_symlink():
                _engine_authority_fail("engine tree contains a symlink")
            paths.append(candidate)
    return tuple(sorted(paths, key=lambda item: item.relative_to(root).as_posix()))


def _validate_engine_manifest_entry(root: Path, entry: Any, index: int) -> Path:
    if not isinstance(entry, dict) or frozenset(entry) != frozenset(
        {"path", "type", "mode", "uid", "gid", "size_bytes", "sha256"}
    ):
        _engine_authority_fail(f"engine manifest entry[{index}] is not closed")
    relative_text = entry.get("path")
    if not isinstance(relative_text, str) or not relative_text:
        _engine_authority_fail("engine manifest contains an invalid path")
    relative = Path(relative_text)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != relative_text
    ):
        _engine_authority_fail("engine manifest path is not canonical relative POSIX")
    kind = entry.get("type")
    mode = entry.get("mode")
    uid = entry.get("uid")
    gid = entry.get("gid")
    size = entry.get("size_bytes")
    digest = entry.get("sha256")
    if kind not in {"directory", "file"}:
        _engine_authority_fail("engine manifest entry type differs")
    for value, label in ((mode, "mode"), (uid, "uid"), (gid, "gid"), (size, "size")):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            _engine_authority_fail(f"engine manifest {label} is invalid")
    if (
        not isinstance(digest, str)
        or (kind == "file" and not HEX_64_RE.fullmatch(digest))
        or (kind == "directory" and digest != "")
    ):
        _engine_authority_fail("engine manifest digest is invalid")

    path = root / relative
    try:
        info = AUTHORITY_LSTAT(path)
    except OSError:
        _engine_authority_fail(f"engine manifest path is missing: {relative_text}")
    actual_kind = (
        "directory"
        if stat.S_ISDIR(info.st_mode)
        else "file"
        if stat.S_ISREG(info.st_mode)
        else "unsupported"
    )
    if actual_kind != kind:
        _engine_authority_fail(f"engine manifest type differs: {relative_text}")
    expected_size = 0 if kind == "directory" else info.st_size
    if (
        stat.S_IMODE(info.st_mode) != mode
        or info.st_uid != uid
        or info.st_gid != gid
        or expected_size != size
    ):
        _engine_authority_fail(f"engine manifest metadata differs: {relative_text}")
    if info.st_uid != 0 or info.st_uid == CALLER_UID:
        _engine_authority_fail(f"engine entry is not root-admin owned: {relative_text}")
    if stat.S_IMODE(info.st_mode) & 0o022:
        _engine_authority_fail(f"engine entry is group/world writable: {relative_text}")
    try:
        writable = AUTHORITY_ACCESS(path, os.W_OK, effective_ids=True)
    except TypeError:
        writable = AUTHORITY_ACCESS(path, os.W_OK)
    if writable:
        _engine_authority_fail(f"engine entry is writable by caller: {relative_text}")
    return path


def _validate_engine_authority() -> tuple[
    Mapping[str, Any], str, str, tuple[FileSeal, ...], FileSeal
]:
    if not HEX_64_RE.fullmatch(ENGINE_MANIFEST_SHA256) or not HEX_64_RE.fullmatch(
        ENGINE_TREE_ROOT_DIGEST
    ):
        _engine_authority_fail("full-tree manifest digests are not provisioned")
    try:
        root = _canonical_existing(
            TRUSTED_ENGINE_ROOT, "immutable UE root", directory=True
        )
        manifest_path = _canonical_existing(
            TRUSTED_ENGINE_MANIFEST,
            "immutable UE full-tree manifest",
            directory=False,
        )
    except ProofError as exc:
        _engine_authority_fail(str(exc))
    _authority_chain(root, "immutable UE root")
    _authority_chain(manifest_path, "immutable UE manifest")
    manifest_seal = _seal(manifest_path, "immutable UE full-tree manifest")
    if manifest_seal.sha256 != ENGINE_MANIFEST_SHA256:
        _engine_authority_fail("full-tree manifest file digest differs")
    manifest = _json_object(manifest_path, "immutable UE full-tree manifest")
    if frozenset(manifest) != frozenset(
        {"schema", "engine_root", "entries", "tree_root_digest", "content_digest"}
    ):
        _engine_authority_fail("full-tree manifest fields differ")
    manifest_digest = _validate_sealed_document(
        manifest, ENGINE_MANIFEST_SCHEMA, "immutable UE full-tree manifest"
    )
    if manifest.get("engine_root") != str(root):
        _engine_authority_fail("full-tree manifest engine_root differs")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        _engine_authority_fail("full-tree manifest entries must be an array")
    content_entries = [
        {
            "path": entry.get("path"),
            "type": entry.get("type"),
            "size_bytes": entry.get("size_bytes"),
            "sha256": entry.get("sha256"),
        }
        for entry in entries
        if isinstance(entry, dict)
    ]
    if len(content_entries) != len(entries):
        _engine_authority_fail("full-tree manifest contains a non-object entry")
    tree_digest = hashlib.sha256(
        _canonical_json_bytes({"entries": content_entries})
    ).hexdigest()
    if (
        manifest.get("tree_root_digest") != tree_digest
        or tree_digest != ENGINE_TREE_ROOT_DIGEST
    ):
        _engine_authority_fail("full-tree root digest differs")
    manifest_paths = tuple(
        _validate_engine_manifest_entry(root, entry, index)
        for index, entry in enumerate(entries)
    )
    actual_paths = _engine_inventory(root)
    if manifest_paths != actual_paths or len(set(manifest_paths)) != len(
        manifest_paths
    ):
        _engine_authority_fail("full-tree inventory differs")

    seals: list[FileSeal] = []
    for pin in CRITICAL_ENGINE_EXPECTATIONS:
        seal = _seal(root / pin.relative, pin.label, executable=pin.executable)
        if seal.sha256 != pin.sha256 or seal.size_bytes != pin.size_bytes:
            _engine_authority_fail(f"critical engine file {pin.label} differs")
        seals.append(seal)
    build_version = _json_object(
        root / Path("Engine/Build/Build.version"), "UE Build.version"
    )
    expected_version = {
        "MajorVersion": 5,
        "MinorVersion": 7,
        "PatchVersion": 3,
        "BranchName": "++UE5+Release-5.7",
    }
    for key, value in expected_version.items():
        if build_version.get(key) != value:
            _engine_authority_fail(f"UE Build.version {key} differs")
    bwrap = _seal(BWRAP_PATH, "bubblewrap", executable=True)
    if bwrap.sha256 != BWRAP_SHA256 or bwrap.size_bytes != BWRAP_BYTES:
        _fail("bubblewrap differs from the private-namespace pin")
    return manifest, manifest_digest, tree_digest, tuple(seals), bwrap


def _source_manifest_entries(
    repo: Path, source_seals: Sequence[FileSeal]
) -> list[dict[str, object]]:
    return [
        {
            "path": seal.path.relative_to(repo).as_posix(),
            "sha256": seal.sha256,
            "size_bytes": seal.size_bytes,
        }
        for seal in source_seals
    ]


def _toolchain_manifest_entries(
    toolchain_seals: Sequence[FileSeal], bwrap: FileSeal
) -> list[dict[str, object]]:
    entries = []
    for pin, seal in zip(CRITICAL_ENGINE_EXPECTATIONS, toolchain_seals, strict=True):
        entries.append(
            {
                "label": pin.label,
                "path": str(seal.path),
                "sha256": seal.sha256,
                "size_bytes": seal.size_bytes,
            }
        )
    entries.append(
        {
            "label": "bubblewrap",
            "path": str(bwrap.path),
            "sha256": bwrap.sha256,
            "size_bytes": bwrap.size_bytes,
        }
    )
    return entries


def prepare_inputs(
    *, attempt_root: Path, attempt_id: str, timeout_seconds: float
) -> ProofInputs:
    if not ATTEMPT_ID_RE.fullmatch(attempt_id):
        _fail("attempt id must be 16-96 lowercase alphanumeric/hyphen characters")
    if not (30.0 <= timeout_seconds <= 3600.0):
        _fail("timeout seconds must be in [30, 3600]")
    attempt = _canonical_existing(attempt_root, "attempt root", directory=True)
    if any(attempt.iterdir()):
        _fail("attempt root must be a fresh empty output directory")
    repo = _canonical_existing(TRUSTED_REPO_ROOT, "trusted repository", directory=True)
    commit, projection, projection_digest, source_seals = _load_trusted_projection(repo)
    (
        engine_manifest,
        engine_manifest_digest,
        engine_tree_root_digest,
        toolchain_seals,
        bwrap,
    ) = _validate_engine_authority()
    input_document = _seal_document(
        {
            "schema": INPUT_SCHEMA,
            "attempt_id": attempt_id,
            "trusted_git_commit": commit,
            "trusted_projection_digest": projection_digest,
            "source_files": _source_manifest_entries(repo, source_seals),
            "engine_authority": {
                "root": str(TRUSTED_ENGINE_ROOT),
                "manifest": str(TRUSTED_ENGINE_MANIFEST),
                "manifest_content_digest": engine_manifest_digest,
                "tree_root_digest": engine_tree_root_digest,
            },
            "toolchain_files": _toolchain_manifest_entries(toolchain_seals, bwrap),
        }
    )
    return ProofInputs(
        repo_root=repo,
        git_commit=commit,
        projection_document=projection,
        projection_digest=projection_digest,
        source_seals=source_seals,
        engine_manifest_document=engine_manifest,
        engine_manifest_digest=engine_manifest_digest,
        engine_tree_root_digest=engine_tree_root_digest,
        toolchain_seals=toolchain_seals,
        bwrap=bwrap,
        attempt_root=attempt,
        output_root=attempt / "proof-output",
        attempt_id=attempt_id,
        timeout_seconds=timeout_seconds,
        input_document=input_document,
        input_digest=str(input_document["content_digest"]),
    )


def _output_directories(output: Path) -> dict[str, Path]:
    return {
        "project_binaries": output / "build/project-binaries",
        "project_intermediate": output / "build/project-intermediate",
        "plugin_binaries": output / "build/plugin-binaries",
        "plugin_intermediate": output / "build/plugin-intermediate",
        "project_saved": output / "runtime/project-saved",
        "home": output / "runtime/home",
        "xdg_cache": output / "runtime/xdg-cache",
        "xdg_config": output / "runtime/xdg-config",
        "evidence": output / "evidence",
        "automation_report": output / "evidence/automation-report",
    }


def _fd_token(prefix: str, index: int) -> str:
    return f"{prefix}{index:04d}__"


def _project_destination(relative: Path) -> Path | None:
    if relative == RUNTIME_WRAPPER_RELATIVE:
        return Path("/vista-runtime-capture.py")
    if relative.is_relative_to(TRUSTED_PROJECT_RELATIVE):
        return Path("/vista-project") / relative.relative_to(TRUSTED_PROJECT_RELATIVE)
    if relative.is_relative_to(PLUGIN_RELATIVE):
        return Path("/vista-project/Plugins/VistaPlayableHome") / relative.relative_to(
            PLUGIN_RELATIVE
        )
    return None


def _source_fd_bindings(inputs: ProofInputs) -> tuple[tuple[str, Path], ...]:
    bindings = []
    for index, seal in enumerate(inputs.source_seals):
        relative = seal.path.relative_to(inputs.repo_root)
        destination = _project_destination(relative)
        if destination is not None:
            bindings.append((_fd_token(SOURCE_FD_PREFIX, index), destination))
    return tuple(bindings)


def _build_output_destination(key: str, relative: Path) -> Path:
    base = {
        "project_binaries": Path("/vista-project/Binaries"),
        "plugin_binaries": Path("/vista-project/Plugins/VistaPlayableHome/Binaries"),
    }.get(key)
    if base is None:
        _fail("controlled build output layout is invalid")
    return base / relative


def _build_output_fd_bindings() -> tuple[tuple[str, Path, bool], ...]:
    return tuple(
        (
            _fd_token(BUILD_OUTPUT_FD_PREFIX, index),
            _build_output_destination(key, relative),
            executable,
        )
        for index, (_, key, relative, executable) in enumerate(BUILD_OUTPUT_LAYOUT)
    )


def _append_directories(command: list[str], paths: Sequence[Path]) -> None:
    directories: set[Path] = set()
    for path in paths:
        parent = path.parent
        while parent != Path("/vista-project") and parent.is_relative_to(
            Path("/vista-project")
        ):
            directories.add(parent)
            parent = parent.parent
    for directory in sorted(
        directories, key=lambda item: (len(item.parts), item.as_posix())
    ):
        command.extend(("--dir", directory.as_posix()))


def _sandbox_prefix(inputs: ProofInputs, *, build: bool) -> list[str]:
    output = _output_directories(inputs.output_root)
    command = [
        str(inputs.bwrap.path),
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/etc",
        "/etc",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/sbin",
        "/sbin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--dir",
        "/data",
        "--dir",
        "/data/vista-authorities",
        "--dir",
        "/data/vista-authorities/ue-5.7.3-r1",
        "--ro-bind",
        str(TRUSTED_ENGINE_ROOT),
        str(TRUSTED_ENGINE_ROOT),
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/vista-project",
    ]
    if not build:
        command.extend(("--tmpfs", "/vista-private"))
    source_bindings = _source_fd_bindings(inputs)
    runtime_output_bindings = () if build else _build_output_fd_bindings()
    _append_directories(
        command,
        [destination for _, destination in source_bindings]
        + [destination for _, destination, _ in runtime_output_bindings],
    )
    for token, destination in source_bindings:
        command.extend(
            ("--perms", "0400", "--ro-bind-data", token, destination.as_posix())
        )
    if build:
        for key, destination in (
            ("project_binaries", "/vista-project/Binaries"),
            ("project_intermediate", "/vista-project/Intermediate"),
            (
                "plugin_binaries",
                "/vista-project/Plugins/VistaPlayableHome/Binaries",
            ),
            (
                "plugin_intermediate",
                "/vista-project/Plugins/VistaPlayableHome/Intermediate",
            ),
        ):
            command.extend(("--bind", str(output[key]), destination))
    else:
        for token, destination, executable in runtime_output_bindings:
            command.extend(
                (
                    "--perms",
                    "0500" if executable else "0400",
                    "--ro-bind-data",
                    token,
                    destination.as_posix(),
                )
            )
    command.extend(
        (
            "--bind",
            str(output["project_saved"]),
            "/vista-project/Saved",
            "--bind",
            str(output["home"]),
            "/vista-home",
            "--bind",
            str(output["xdg_cache"]),
            "/vista-xdg-cache",
            "--bind",
            str(output["xdg_config"]),
            "/vista-xdg-config",
        )
    )
    command.extend(
        (
            "--remount-ro",
            "/vista-project",
            "--setenv",
            "PATH",
            TRUSTED_PATH,
            "--setenv",
            "HOME",
            "/vista-home",
            "--setenv",
            "TMPDIR",
            "/tmp",
            "--setenv",
            "XDG_CACHE_HOME",
            "/vista-xdg-cache",
            "--setenv",
            "XDG_CONFIG_HOME",
            "/vista-xdg-config",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--chdir",
            "/vista-project",
        )
    )
    return command


def build_plan(inputs: ProofInputs) -> ProofPlan:
    build_command = tuple(
        _sandbox_prefix(inputs, build=True)
        + [
            str(TRUSTED_ENGINE_ROOT / "Engine/Build/BatchFiles/RunUBT.sh"),
            "VistaR5ProofEditor",
            "Linux",
            "Development",
            "-Project=/vista-project/VistaR5Proof.uproject",
            "-NoHotReloadFromIDE",
            "-NoEngineChanges",
            "-NoUBA",
            "-SkipUBTBuild",
        ]
    )
    runtime_command_template = tuple(
        _sandbox_prefix(inputs, build=False)
        + [
            "/usr/bin/python3",
            "/vista-runtime-capture.py",
            "--",
            str(TRUSTED_ENGINE_ROOT / "Engine/Binaries/Linux/UnrealEditor-Cmd"),
            "/vista-project/VistaR5Proof.uproject",
            "-nullrhi",
            "-nosound",
            "-unattended",
            "-nop4",
            "-nosplash",
            "-NoAssetRegistryCache",
            "-stdout",
            "-FullStdOutLogOutput",
            f"-ExecCmds=Automation RunTests {AUTOMATION_TEST}",
            "-TestExit=Automation Test Queue Empty",
            "-ReportExportPath=/vista-private/automation-report",
            f"-VistaR5ProofAttemptId={inputs.attempt_id}",
            "-VistaR5ProofReceipt=/vista-private/r5-multiclient-proof-receipt.json",
            f"-VistaR5ProofGitCommit={inputs.git_commit}",
            f"-VistaR5ProofProjectionDigest={inputs.projection_digest}",
            f"-VistaR5ProofInputDigest={inputs.input_digest}",
            f"-VistaR5ProofLaunchDigest={LAUNCH_DIGEST_PLACEHOLDER}",
            f"-VistaR5ProofBuildDigest={BUILD_DIGEST_PLACEHOLDER}",
        ]
    )
    launch_document = _seal_document(
        {
            "schema": PLAN_SCHEMA,
            "mode": "pinned_ubt_then_runtime",
            "attempt_id": inputs.attempt_id,
            "attempt_root": str(inputs.attempt_root),
            "output_root": str(inputs.output_root),
            "trusted_git_commit": inputs.git_commit,
            "trusted_projection_digest": inputs.projection_digest,
            "input_manifest_digest": inputs.input_digest,
            "build_command": list(build_command),
            "runtime_command_template": list(runtime_command_template),
            "sandbox": {
                "private_network_namespace": True,
                "gpu_devices_exposed": False,
                "trusted_inputs_read_only": True,
                "source_and_build_inputs_are_sealed_memfd_snapshots": True,
                "engine_is_admin_owned_full_tree_authority": True,
                "runtime_receipt_and_report_use_private_tmpfs": True,
                "host_root_is_not_bound": True,
                "persistent_writes_only_under_output": True,
            },
            "pie": {
                "server": "dedicated_server",
                "clients": 2,
                "run_under_one_process": True,
                "real_replication_worlds": 3,
            },
            "success_authority": {
                "process_exit_zero": True,
                "closed_receipt": RECEIPT_SCHEMA,
                "private_runtime_envelope": RUNTIME_ENVELOPE_SCHEMA,
                "exact_automation_test_success": AUTOMATION_TEST,
                "log_substring_is_proof": False,
            },
        }
    )
    return ProofPlan(
        inputs=inputs,
        build_command=build_command,
        runtime_command_template=runtime_command_template,
        launch_document=launch_document,
        launch_digest=str(launch_document["content_digest"]),
    )


def _verify_inputs(inputs: ProofInputs) -> None:
    commit, projection, digest, source_seals = _load_trusted_projection(
        inputs.repo_root
    )
    (
        engine_manifest,
        engine_manifest_digest,
        engine_tree_root_digest,
        toolchain_seals,
        bwrap,
    ) = _validate_engine_authority()
    if commit != inputs.git_commit or digest != inputs.projection_digest:
        _fail("trusted Git projection changed after planning")
    if _canonical_json_bytes(projection) != _canonical_json_bytes(
        inputs.projection_document
    ):
        _fail("trusted projection document changed after planning")
    if len(source_seals) != len(inputs.source_seals) or any(
        not _same_seal(current, expected)
        for current, expected in zip(source_seals, inputs.source_seals, strict=True)
    ):
        _fail("trusted source changed after planning")
    if (
        engine_manifest_digest != inputs.engine_manifest_digest
        or engine_tree_root_digest != inputs.engine_tree_root_digest
        or _canonical_json_bytes(engine_manifest)
        != _canonical_json_bytes(inputs.engine_manifest_document)
    ):
        _fail("immutable engine authority changed after planning")
    if len(toolchain_seals) != len(inputs.toolchain_seals) or any(
        not _same_seal(current, expected)
        for current, expected in zip(
            toolchain_seals, inputs.toolchain_seals, strict=True
        )
    ):
        _fail("pinned toolchain changed after planning")
    if not _same_seal(bwrap, inputs.bwrap):
        _fail("pinned bubblewrap changed after planning")
    rebuilt = _seal_document(
        {
            "schema": INPUT_SCHEMA,
            "attempt_id": inputs.attempt_id,
            "trusted_git_commit": commit,
            "trusted_projection_digest": digest,
            "source_files": _source_manifest_entries(inputs.repo_root, source_seals),
            "engine_authority": {
                "root": str(TRUSTED_ENGINE_ROOT),
                "manifest": str(TRUSTED_ENGINE_MANIFEST),
                "manifest_content_digest": engine_manifest_digest,
                "tree_root_digest": engine_tree_root_digest,
            },
            "toolchain_files": _toolchain_manifest_entries(toolchain_seals, bwrap),
        }
    )
    if _canonical_json_bytes(rebuilt) != _canonical_json_bytes(inputs.input_document):
        _fail("input manifest changed after planning")


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        _fail(
            f"{label} keys differ: missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )


def _require_type(value: Any, kind: type, label: str) -> Any:
    if kind is int and isinstance(value, bool):
        _fail(f"{label} must be int, not bool")
    if not isinstance(value, kind):
        _fail(f"{label} must be {kind.__name__}")
    return value


def _validate_bits(value: Any, length: int, label: str) -> tuple[str, ...]:
    array = _require_type(value, list, label)
    if len(array) != length:
        _fail(f"{label} must contain {length} exact bit strings")
    result = tuple(_require_type(item, str, f"{label}[]") for item in array)
    if any(not HEX_BITS_RE.fullmatch(item) for item in result):
        _fail(f"{label} contains a non-canonical bit string")
    if len({len(item) for item in result}) != 1:
        _fail(f"{label} mixes scalar widths")
    return result


def _double_bits(value: float) -> str:
    bits = struct.unpack("=Q", struct.pack("=d", value))[0]
    return f"{bits:016x}"


def _scalar_from_bits(value: str) -> float:
    raw = bytes.fromhex(value)
    if len(raw) == 8:
        return struct.unpack("=d", raw[::-1] if sys.byteorder == "little" else raw)[0]
    if len(raw) == 4:
        return struct.unpack("=f", raw[::-1] if sys.byteorder == "little" else raw)[0]
    _fail("physical scalar bit width is unsupported")


def _require_finite_bits(values: tuple[str, ...], label: str) -> None:
    if any(not math.isfinite(_scalar_from_bits(value)) for value in values):
        _fail(f"{label} contains a non-finite physical scalar")


def _validate_world(
    world: Mapping[str, Any], *, checkpoint: str, index: int, disposition: str
) -> dict[str, tuple[str, ...]]:
    _exact_keys(world, WORLD_KEYS, f"{checkpoint}.world[{index}]")
    if world.get("checkpoint") != checkpoint:
        _fail(f"{checkpoint}.world[{index}] checkpoint identity differs")
    expected_role = "server" if index == 0 else "client"
    expected_client_index = -1 if index == 0 else index - 1
    expected_mode = "dedicated_server" if index == 0 else "client"
    expected_authority = index == 0
    exact = {
        "role": expected_role,
        "client_index": expected_client_index,
        "net_mode": expected_mode,
        "net_driver_is_server": expected_authority,
        "pickup_has_authority": expected_authority,
        "carrier_has_authority": expected_authority,
        "disposition": disposition,
    }
    for key, expected in exact.items():
        if world.get(key) != expected:
            _fail(f"{checkpoint}.world[{index}].{key} differs")
    for key in ("role", "net_mode", "disposition"):
        _require_type(world.get(key), str, f"{checkpoint}.world[{index}].{key}")
    _require_type(
        world.get("client_index"), int, f"{checkpoint}.world[{index}].client_index"
    )
    for key in (
        "net_driver_is_server",
        "pickup_has_authority",
        "carrier_has_authority",
        "simulate_physics",
        "actual_simulate_physics",
    ):
        _require_type(world.get(key), bool, f"{checkpoint}.world[{index}].{key}")
    _require_type(
        world.get("collision_enabled"),
        int,
        f"{checkpoint}.world[{index}].collision_enabled",
    )
    _require_type(
        world.get("actual_collision_enabled"),
        int,
        f"{checkpoint}.world[{index}].actual_collision_enabled",
    )
    held = disposition == "held"
    placed = disposition == "placed"
    if world.get("carrier_semantic_id") != (CARRIER_A if held else ""):
        _fail(f"{checkpoint}.world[{index}] carrier identity differs")
    if world.get("inventory_item_semantic_id") != (PICKUP if held else ""):
        _fail(f"{checkpoint}.world[{index}] inventory identity differs")
    if world.get("placement_anchor_semantic_id") != (
        PLACEMENT_ANCHOR if placed else ""
    ):
        _fail(f"{checkpoint}.world[{index}] placement identity differs")
    if world.get("simulate_physics") is not (disposition == "free"):
        _fail(f"{checkpoint}.world[{index}] physics disposition differs")
    if world.get("collision_enabled") != (0 if held else 3):
        _fail(f"{checkpoint}.world[{index}] collision mode differs")
    if world.get("collision_profile") != "PhysicsActor":
        _fail(f"{checkpoint}.world[{index}] collision profile differs")
    for key in (
        "carrier_semantic_id",
        "inventory_item_semantic_id",
        "placement_anchor_semantic_id",
        "collision_profile",
        "attachment_parent_name",
        "attachment_socket",
        "actual_collision_profile",
    ):
        _require_type(world.get(key), str, f"{checkpoint}.world[{index}].{key}")
    expected_parent = "ProofCarryAnchor" if held else ""
    if world.get("attachment_parent_name") != expected_parent:
        _fail(f"{checkpoint}.world[{index}] attachment parent differs")
    if world.get("attachment_socket") != "":
        _fail(f"{checkpoint}.world[{index}] attachment socket differs")
    bits = {
        "world": _validate_bits(
            world.get("world_transform_bits"),
            10,
            f"{checkpoint}.world[{index}].world_transform_bits",
        ),
        "relative": _validate_bits(
            world.get("attachment_relative_transform_bits"),
            10,
            f"{checkpoint}.world[{index}].attachment_relative_transform_bits",
        ),
        "linear": _validate_bits(
            world.get("linear_velocity_bits"),
            3,
            f"{checkpoint}.world[{index}].linear_velocity_bits",
        ),
        "angular": _validate_bits(
            world.get("angular_velocity_bits"),
            3,
            f"{checkpoint}.world[{index}].angular_velocity_bits",
        ),
        "actual_world": _validate_bits(
            world.get("actual_world_transform_bits"),
            10,
            f"{checkpoint}.world[{index}].actual_world_transform_bits",
        ),
        "actual_relative": _validate_bits(
            world.get("actual_relative_transform_bits"),
            10,
            f"{checkpoint}.world[{index}].actual_relative_transform_bits",
        ),
        "actual_linear": _validate_bits(
            world.get("actual_linear_velocity_bits"),
            3,
            f"{checkpoint}.world[{index}].actual_linear_velocity_bits",
        ),
        "actual_angular": _validate_bits(
            world.get("actual_angular_velocity_bits"),
            3,
            f"{checkpoint}.world[{index}].actual_angular_velocity_bits",
        ),
    }
    for field, values in bits.items():
        _require_finite_bits(values, f"{checkpoint}.world[{index}].{field}")
    if world.get("actual_simulate_physics") is not world.get("simulate_physics"):
        _fail(f"{checkpoint}.world[{index}] live physics flag differs")
    if world.get("actual_collision_enabled") != world.get("collision_enabled"):
        _fail(f"{checkpoint}.world[{index}] live collision mode differs")
    if world.get("actual_collision_profile") != world.get("collision_profile"):
        _fail(f"{checkpoint}.world[{index}] live collision profile differs")
    if bits["actual_linear"] != bits["linear"]:
        _fail(f"{checkpoint}.world[{index}] live linear velocity differs")
    if bits["actual_angular"] != bits["angular"]:
        _fail(f"{checkpoint}.world[{index}] live angular velocity differs")
    if checkpoint == "free_after_drop":
        expected_drop = tuple(_double_bits(value) for value in (37.0, -11.0, 23.0))
        if bits["linear"] != expected_drop:
            _fail(f"{checkpoint}.world[{index}] release velocity bits differ")
    if disposition in {"held", "placed"}:
        zero = tuple(_double_bits(0.0) for _ in range(3))
        if bits["linear"] != zero or bits["angular"] != zero:
            _fail(f"{checkpoint}.world[{index}] expected zero velocities")
    identity = tuple(
        _double_bits(value)
        for value in (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0)
    )
    if bits["relative"] != identity:
        _fail(f"{checkpoint}.world[{index}] relative transform differs")
    if held and bits["actual_relative"] != bits["relative"]:
        _fail(f"{checkpoint}.world[{index}] live held transform differs")
    if not held and bits["actual_relative"] != bits["actual_world"]:
        _fail(f"{checkpoint}.world[{index}] detached root transform differs")
    if (
        checkpoint in {"initial_free", "placed"}
        and bits["actual_world"] != bits["world"]
    ):
        _fail(f"{checkpoint}.world[{index}] live world transform differs")
    if disposition == "placed":
        placed_transform = tuple(
            _double_bits(value)
            for value in (120.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0)
        )
        if bits["world"] != placed_transform:
            _fail(f"{checkpoint}.world[{index}] target transform differs")
    return bits


def _validate_transaction(
    value: Any,
    label: str,
    *,
    status: str,
    mutations: int,
    attempted: bool,
    committed: bool,
    rollback: bool,
    command_id: str,
    code: str,
    before: str | None = None,
    contact: str | None = None,
    after: str | None = None,
) -> Mapping[str, Any]:
    transaction = _require_type(value, dict, label)
    _exact_keys(transaction, TRANSACTION_KEYS, label)
    expected = {
        "status": status,
        "physical_mutation_count": mutations,
        "contact_mutation_attempted": attempted,
        "contact_committed": committed,
        "rollback_attempted": rollback,
        "rolled_back": rollback,
    }
    for key, expected_value in expected.items():
        if transaction.get(key) != expected_value:
            _fail(f"{label}.{key} differs")
    for key in (
        "contact_mutation_attempted",
        "contact_committed",
        "rollback_attempted",
        "rolled_back",
    ):
        _require_type(transaction.get(key), bool, f"{label}.{key}")
    _require_type(
        transaction.get("physical_mutation_count"),
        int,
        f"{label}.physical_mutation_count",
    )
    if transaction.get("command_id") != command_id:
        _fail(f"{label}.command_id differs")
    if transaction.get("code") != code:
        _fail(f"{label}.code differs")
    for key in ("status", "command_id", "code"):
        _require_type(transaction.get(key), str, f"{label}.{key}")
    for key, expected_value in (
        ("before_disposition", before),
        ("contact_disposition", contact),
        ("after_disposition", after),
    ):
        actual = _require_type(transaction.get(key), str, f"{label}.{key}")
        if expected_value is not None and actual != expected_value:
            _fail(f"{label}.{key} differs")
    return transaction


def _validate_reset_event_state(value: Any, label: str) -> None:
    state = _require_type(value, dict, label)
    _exact_keys(state, EVENT_STATE_KEYS, label)
    expected = {
        "active_event_id": "r5-proof-event",
        "event_status": "active",
        "session_generation": 0,
        "public_goal": "Remain active during proof",
        "terminal_condition_id": "",
    }
    for key, expected_value in expected.items():
        if state.get(key) != expected_value:
            _fail(f"{label}.{key} differs")
    for key in (
        "active_event_id",
        "event_status",
        "public_goal",
        "terminal_condition_id",
    ):
        _require_type(state.get(key), str, f"{label}.{key}")
    _require_type(state.get("session_generation"), int, f"{label}.session_generation")


def validate_automation_report_bytes(raw: bytes) -> Mapping[str, Any]:
    if not (0 < len(raw) <= MAX_AUTOMATION_REPORT_BYTES):
        _fail("Automation report size is outside the accepted range")
    try:
        report = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProofError("Automation report is not valid UTF-8 JSON") from exc
    if not isinstance(report, dict):
        _fail("Automation report must be a JSON object")
    _exact_keys(report, AUTOMATION_REPORT_KEYS, "Automation report")
    for key, expected in (
        ("succeeded", 1),
        ("succeededWithWarnings", 0),
        ("failed", 0),
        ("notRun", 0),
        ("inProcess", 0),
    ):
        _require_type(report.get(key), int, f"Automation report {key}")
        if report.get(key) != expected:
            _fail(f"Automation report {key} differs")
    tests = _require_type(report.get("tests"), list, "Automation report tests")
    if len(tests) != 1:
        _fail("Automation report must contain exactly the requested test")
    result = _require_type(tests[0], dict, "Automation report test[0]")
    _exact_keys(result, AUTOMATION_TEST_KEYS, "Automation report test[0]")
    if (
        result.get("fullTestPath") != AUTOMATION_TEST
        or result.get("state") != "Success"
        or result.get("warnings") != 0
        or result.get("errors") != 0
    ):
        _fail("requested Automation test did not succeed without errors")
    _require_type(result.get("fullTestPath"), str, "Automation test fullTestPath")
    _require_type(result.get("state"), str, "Automation test state")
    _require_type(result.get("warnings"), int, "Automation test warnings")
    _require_type(result.get("errors"), int, "Automation test errors")
    return report


def _decode_exact_base64(encoded: str, label: str) -> bytes:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ProofError(f"{label} is malformed") from exc
    if base64.b64encode(raw).decode("ascii") != encoded:
        _fail(f"{label} is not canonical base64")
    return raw


def parse_private_runtime_envelope(
    stdout: bytes,
) -> tuple[Mapping[str, Any], bytes, bytes]:
    if not (0 < len(stdout) <= MAX_RUNTIME_STDOUT_BYTES):
        _fail("private runtime stdout size is outside the accepted range")
    try:
        text = stdout.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProofError("private runtime stdout is not ASCII") from exc
    prefix = RUNTIME_ENVELOPE_MARKER
    if (
        not text.endswith("\n")
        or text.count(prefix) != 1
        or not text.startswith(prefix)
    ):
        _fail("private runtime stdout does not contain exactly one sealed marker")
    encoded = text[len(prefix) : -1]
    if not encoded or "\n" in encoded or "\r" in encoded:
        _fail("private runtime envelope marker is malformed")
    try:
        raw_envelope = _decode_exact_base64(encoded, "private runtime envelope base64")
        envelope = json.loads(raw_envelope.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProofError("private runtime envelope is malformed") from exc
    if not isinstance(envelope, dict) or raw_envelope != _canonical_json_bytes(
        envelope
    ):
        _fail("private runtime envelope is not canonical JSON")
    _exact_keys(
        envelope,
        frozenset(
            {
                "schema",
                "automation_test",
                "runtime_exit_code",
                "receipt_base64",
                "receipt_sha256",
                "automation_report_base64",
                "automation_report_sha256",
            }
        ),
        "private runtime envelope",
    )
    if (
        envelope.get("schema") != RUNTIME_ENVELOPE_SCHEMA
        or envelope.get("automation_test") != AUTOMATION_TEST
        or envelope.get("runtime_exit_code") != 0
    ):
        _fail("private runtime envelope authority differs")
    _require_type(envelope.get("runtime_exit_code"), int, "runtime exit code")
    receipt_raw = _decode_exact_base64(
        _require_type(envelope.get("receipt_base64"), str, "receipt_base64"),
        "private runtime receipt_base64",
    )
    report_raw = _decode_exact_base64(
        _require_type(
            envelope.get("automation_report_base64"),
            str,
            "automation_report_base64",
        ),
        "private runtime automation_report_base64",
    )
    for raw, field in (
        (receipt_raw, "receipt_sha256"),
        (report_raw, "automation_report_sha256"),
    ):
        digest = _require_type(envelope.get(field), str, field)
        if not HEX_64_RE.fullmatch(digest) or hashlib.sha256(raw).hexdigest() != digest:
            _fail(f"private runtime {field} differs")
    return envelope, receipt_raw, report_raw


def validate_closed_receipt_bytes(
    raw: bytes, expectation: ReceiptExpectation
) -> Mapping[str, Any]:
    if not (0 < len(raw) <= MAX_RECEIPT_BYTES):
        _fail("closed receipt size is outside the accepted range")
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProofError("closed receipt is not valid UTF-8 JSON") from exc
    if not isinstance(receipt, dict):
        _fail("closed receipt must be a JSON object")
    _exact_keys(receipt, TOP_KEYS, "closed receipt")
    exact_top = {
        "schema": RECEIPT_SCHEMA,
        "status": "passed",
        "attempt_id": expectation.attempt_id,
        "harness": HARNESS_NAME,
        "client_count": 2,
        "worlds_per_checkpoint": 3,
        "trusted_git_commit": expectation.trusted_git_commit,
        "trusted_projection_digest": expectation.trusted_projection_digest,
        "input_manifest_digest": expectation.input_manifest_digest,
        "launch_plan_digest": expectation.launch_plan_digest,
        "build_provenance_digest": expectation.build_provenance_digest,
    }
    for key, expected in exact_top.items():
        if receipt.get(key) != expected:
            _fail(f"closed receipt {key} differs")
    for key in (
        "schema",
        "status",
        "attempt_id",
        "harness",
        "trusted_git_commit",
        "trusted_projection_digest",
        "input_manifest_digest",
        "launch_plan_digest",
        "build_provenance_digest",
    ):
        _require_type(receipt.get(key), str, f"closed receipt {key}")
    for key in ("client_count", "worlds_per_checkpoint"):
        _require_type(receipt.get(key), int, f"closed receipt {key}")
    engine_version = _require_type(
        receipt.get("engine_version"), str, "closed receipt engine_version"
    )
    if not engine_version.startswith("5.7.3-"):
        _fail("closed receipt engine version is not UE 5.7.3")

    checkpoints = _require_type(receipt.get("checkpoints"), list, "checkpoints")
    if len(checkpoints) != len(CHECKPOINT_NAMES):
        _fail("closed receipt checkpoint count differs")
    checkpoint_bits: dict[str, list[dict[str, tuple[str, ...]]]] = {}
    for checkpoint_index, (name, disposition) in enumerate(
        zip(CHECKPOINT_NAMES, CHECKPOINT_DISPOSITIONS, strict=True)
    ):
        checkpoint = _require_type(
            checkpoints[checkpoint_index], dict, f"checkpoint[{checkpoint_index}]"
        )
        _exact_keys(checkpoint, CHECKPOINT_KEYS, f"checkpoint[{checkpoint_index}]")
        if checkpoint.get("name") != name:
            _fail(f"checkpoint[{checkpoint_index}] order/name differs")
        worlds = _require_type(checkpoint.get("worlds"), list, f"{name}.worlds")
        if len(worlds) != 3:
            _fail(f"{name} must report one server and two clients")
        checkpoint_bits[name] = [
            _validate_world(
                _require_type(world, dict, f"{name}.world[{index}]"),
                checkpoint=name,
                index=index,
                disposition=disposition,
            )
            for index, world in enumerate(worlds)
        ]
    for name in CHECKPOINT_NAMES:
        payloads = checkpoint_bits[name]
        for field in ("world", "relative", "linear", "angular"):
            if len({payload[field] for payload in payloads}) != 1:
                _fail(f"{name} {field} payload differs across server + two clients")

    transactions = _require_type(receipt.get("transactions"), dict, "transactions")
    _exact_keys(transactions, TRANSACTIONS_KEYS, "transactions")
    reset = _require_type(
        transactions.get("event_reset_while_active"),
        dict,
        "transactions.event_reset_while_active",
    )
    _exact_keys(reset, RESET_KEYS, "transactions.event_reset_while_active")
    if (
        reset.get("claim") != "active_action_reset_rejection_only"
        or reset.get("has_active_action_after_rejection") is not True
        or reset.get("accepted") is not False
        or reset.get("code") != "EVENT_RESET_ACTION_ACTIVE"
    ):
        _fail("active Event reset did not fail closed")
    _require_type(
        reset.get("claim"), str, "transactions.event_reset_while_active.claim"
    )
    _require_type(
        reset.get("accepted"), bool, "transactions.event_reset_while_active.accepted"
    )
    _require_type(
        reset.get("has_active_action_after_rejection"),
        bool,
        "transactions.event_reset_while_active.has_active_action_after_rejection",
    )
    _require_type(reset.get("code"), str, "transactions.event_reset_while_active.code")
    _validate_reset_event_state(
        reset.get("before_event"),
        "transactions.event_reset_while_active.before_event",
    )
    _validate_reset_event_state(
        reset.get("after_rejection_event"),
        "transactions.event_reset_while_active.after_rejection_event",
    )
    _validate_transaction(
        reset.get("active_transaction"),
        "transactions.event_reset_while_active.active_transaction",
        status="canceled",
        mutations=0,
        attempted=False,
        committed=False,
        rollback=False,
        command_id="r5-event-reset-active",
        code="R5_PROOF_ACTIVE_RESET_CLEANUP",
        before="free",
        contact="missing",
        after="free",
    )
    pickup = _validate_transaction(
        transactions.get("pickup"),
        "transactions.pickup",
        status="succeeded",
        mutations=1,
        attempted=True,
        committed=True,
        rollback=False,
        command_id="r5-pickup-once",
        code="ITEM_PICKED_UP",
        before="free",
        contact="held",
        after="held",
    )
    retry = _validate_transaction(
        transactions.get("exact_retry"),
        "transactions.exact_retry",
        status="succeeded",
        mutations=1,
        attempted=True,
        committed=True,
        rollback=False,
        command_id="r5-pickup-once",
        code="ITEM_PICKED_UP",
        before="free",
        contact="held",
        after="held",
    )
    if retry.get("command_id") != pickup.get("command_id"):
        _fail("exact retry did not replay the same world-global command")
    _validate_transaction(
        transactions.get("command_id_collision"),
        "transactions.command_id_collision",
        status="failed",
        mutations=0,
        attempted=False,
        committed=False,
        rollback=False,
        command_id="r5-pickup-once",
        code="COMMAND_ID_COLLISION",
        before="missing",
        contact="missing",
        after="missing",
    )
    _validate_transaction(
        transactions.get("failed_place_rollback"),
        "transactions.failed_place_rollback",
        status="failed",
        mutations=1,
        attempted=True,
        committed=True,
        rollback=True,
        command_id="r5-place-forced-failure",
        code="DEV_AUTOMATION_FORCED_POST_CONTACT_FAILURE",
        before="held",
        contact="placed",
        after="held",
    )
    _validate_transaction(
        transactions.get("place"),
        "transactions.place",
        status="succeeded",
        mutations=1,
        attempted=True,
        committed=True,
        rollback=False,
        command_id="r5-place-success",
        code="ITEM_PLACED",
        before="held",
        contact="placed",
        after="placed",
    )
    _validate_transaction(
        transactions.get("pickup_again"),
        "transactions.pickup_again",
        status="succeeded",
        mutations=1,
        attempted=True,
        committed=True,
        rollback=False,
        command_id="r5-pickup-again",
        code="ITEM_PICKED_UP",
        before="placed",
        contact="held",
        after="held",
    )
    _validate_transaction(
        transactions.get("drop"),
        "transactions.drop",
        status="succeeded",
        mutations=1,
        attempted=True,
        committed=True,
        rollback=False,
        command_id="r5-drop-success",
        code="ITEM_DROPPED",
        before="held",
        contact="free",
        after="free",
    )
    return receipt


def _write_new_json(path: Path, document: Mapping[str, Any]) -> None:
    raw = _canonical_json_bytes(document)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
    path.chmod(0o600)


def _write_new_bytes(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
    path.chmod(0o600)


def _prepare_output(inputs: ProofInputs) -> None:
    if inputs.output_root.exists() or any(inputs.attempt_root.iterdir()):
        _fail("proof output is not fresh")
    inputs.output_root.mkdir(mode=0o700)
    for path in _output_directories(inputs.output_root).values():
        path.mkdir(mode=0o700, parents=True, exist_ok=True)


def _memfd_from_bytes(label: str, raw: bytes, expected: FileSeal) -> int:
    if (
        hashlib.sha256(raw).hexdigest() != expected.sha256
        or len(raw) != expected.size_bytes
    ):
        _fail(f"immutable snapshot source {label} differs from its trusted seal")
    fd = os.memfd_create(f"vista-r5-{label}", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                _fail(f"immutable snapshot source {label} could not be copied")
            view = view[written:]
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(
            fd,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE,
        )
        return fd
    except BaseException:
        os.close(fd)
        raise


def _memfd_from_file(label: str, expected: FileSeal) -> int:
    canonical = _canonical_existing(expected.path, label, directory=False)
    digest = hashlib.sha256()
    size = 0
    fd = os.memfd_create(f"vista-r5-{label}", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        with canonical.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        _fail(f"immutable snapshot file {label} could not be copied")
                    view = view[written:]
        if digest.hexdigest() != expected.sha256 or size != expected.size_bytes:
            _fail(f"immutable snapshot file {label} differs from its trusted seal")
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(
            fd,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE,
        )
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextlib.contextmanager
def _immutable_input_snapshot(
    inputs: ProofInputs, provenance: BuildProvenance | None = None
) -> Iterator[ImmutableInputSnapshot]:
    token_fds: dict[str, int] = {}
    try:
        for index, seal in enumerate(inputs.source_seals):
            relative = seal.path.relative_to(inputs.repo_root).as_posix()
            if _project_destination(Path(relative)) is None:
                continue
            raw = _git_bytes(
                inputs.repo_root, "show", f"{inputs.git_commit}:{relative}"
            )
            token_fds[_fd_token(SOURCE_FD_PREFIX, index)] = _memfd_from_bytes(
                f"source-{index}", raw, seal
            )
        if provenance is not None:
            if len(provenance.output_seals) != len(BUILD_OUTPUT_LAYOUT):
                _fail("controlled build output inventory differs")
            for index, seal in enumerate(provenance.output_seals):
                token_fds[_fd_token(BUILD_OUTPUT_FD_PREFIX, index)] = _memfd_from_file(
                    f"build-output-{index}", seal
                )
        yield ImmutableInputSnapshot(token_fds=dict(token_fds))
    finally:
        for fd in token_fds.values():
            os.close(fd)


def _instantiate_fd_tokens(
    command: Sequence[str], snapshot: ImmutableInputSnapshot
) -> tuple[str, ...]:
    result = tuple(str(snapshot.token_fds.get(token, token)) for token in command)
    prefixes = (SOURCE_FD_PREFIX, BUILD_OUTPUT_FD_PREFIX)
    if any(any(prefix in token for prefix in prefixes) for token in result):
        _fail("sandbox command contains an unresolved immutable-input descriptor")
    return result


def _run_logged(
    command: Sequence[str],
    log_path: Path,
    timeout: float,
    *,
    pass_fds: Sequence[int],
) -> int:
    try:
        with log_path.open("x", encoding="utf-8") as log_handle:
            completed = subprocess.run(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
                start_new_session=True,
                pass_fds=tuple(pass_fds),
            )
    except subprocess.TimeoutExpired as exc:
        raise ProofError(f"proof process timed out: {log_path.name}") from exc
    return completed.returncode


def _run_runtime_captured(
    command: Sequence[str],
    log_path: Path,
    timeout: float,
    *,
    pass_fds: Sequence[int],
) -> tuple[int, bytes]:
    try:
        with log_path.open("xb") as log_handle:
            completed = subprocess.run(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=log_handle,
                timeout=timeout,
                check=False,
                start_new_session=True,
                pass_fds=tuple(pass_fds),
            )
        log_path.chmod(0o600)
    except subprocess.TimeoutExpired as exc:
        raise ProofError("private Unreal runtime timed out") from exc
    stdout = completed.stdout
    if not isinstance(stdout, bytes):
        _fail("private runtime stdout capture type differs")
    return completed.returncode, stdout


def _engine_build_id() -> str:
    modules_path = TRUSTED_ENGINE_ROOT / "Engine/Binaries/Linux/UnrealEditor.modules"
    modules = _json_object(modules_path, "pinned UnrealEditor.modules")
    build_id = modules.get("BuildId")
    if not isinstance(build_id, str) or not build_id.isdigit():
        _fail("pinned engine BuildId is invalid")
    return build_id


def _validate_modules_file(
    path: Path, expected_modules: Mapping[str, str], engine_build_id: str
) -> FileSeal:
    document = _json_object(path, path.name)
    if frozenset(document) != frozenset({"BuildId", "Modules"}):
        _fail(f"{path.name} fields differ")
    if document.get("BuildId") != engine_build_id:
        _fail(f"{path.name} BuildId differs from pinned engine")
    if document.get("Modules") != dict(expected_modules):
        _fail(f"{path.name} module projection differs")
    return _seal(path, path.name)


def _require_elf(path: Path, label: str) -> FileSeal:
    seal = _seal(path, label)
    with path.open("rb") as handle:
        magic = handle.read(4)
    if seal.size_bytes < 4 or magic != b"\x7fELF":
        _fail(f"{label} is not an ELF output from the controlled UBT build")
    return seal


def _capture_build_provenance(plan: ProofPlan) -> BuildProvenance:
    output = _output_directories(plan.inputs.output_root)
    engine_build_id = _engine_build_id()
    binaries = BUILD_OUTPUT_LAYOUT[:3]
    output_seals = tuple(
        _require_elf(output[key] / relative, label)
        for label, key, relative, _ in binaries
    )
    project_modules = _validate_modules_file(
        output["project_binaries"] / "Linux/UnrealEditor.modules",
        {"VistaR5Proof": "libUnrealEditor-VistaR5Proof.so"},
        engine_build_id,
    )
    plugin_modules = _validate_modules_file(
        output["plugin_binaries"] / "Linux/UnrealEditor.modules",
        {
            "VistaPlayableHome": "libUnrealEditor-VistaPlayableHome.so",
            "VistaPlayableHomeEditor": "libUnrealEditor-VistaPlayableHomeEditor.so",
        },
        engine_build_id,
    )
    all_seals = (*output_seals, project_modules, plugin_modules)
    document = _seal_document(
        {
            "schema": BUILD_SCHEMA,
            "attempt_id": plan.inputs.attempt_id,
            "trusted_git_commit": plan.inputs.git_commit,
            "trusted_projection_digest": plan.inputs.projection_digest,
            "input_manifest_digest": plan.inputs.input_digest,
            "launch_plan_digest": plan.launch_digest,
            "engine_manifest_content_digest": plan.inputs.engine_manifest_digest,
            "engine_tree_root_digest": plan.inputs.engine_tree_root_digest,
            "engine_build_id": engine_build_id,
            "controlled_ubt_command_digest": hashlib.sha256(
                _canonical_json_bytes({"command": list(plan.build_command)})
            ).hexdigest(),
            "outputs": [
                {
                    "path": seal.path.relative_to(plan.inputs.output_root).as_posix(),
                    "sha256": seal.sha256,
                    "size_bytes": seal.size_bytes,
                }
                for seal in all_seals
            ],
        }
    )
    return BuildProvenance(
        document=document,
        digest=str(document["content_digest"]),
        output_seals=tuple(all_seals),
    )


def _verify_build_provenance(plan: ProofPlan, provenance: BuildProvenance) -> None:
    current = _capture_build_provenance(plan)
    if current.digest != provenance.digest or _canonical_json_bytes(
        current.document
    ) != _canonical_json_bytes(provenance.document):
        _fail("controlled UBT outputs changed after provenance closure")
    if len(current.output_seals) != len(provenance.output_seals) or any(
        not _same_seal(left, right)
        for left, right in zip(
            current.output_seals, provenance.output_seals, strict=True
        )
    ):
        _fail("controlled UBT binary/module seals changed")


def _runtime_command(plan: ProofPlan, build_digest: str) -> tuple[str, ...]:
    command = tuple(
        token.replace(LAUNCH_DIGEST_PLACEHOLDER, plan.launch_digest).replace(
            BUILD_DIGEST_PLACEHOLDER, build_digest
        )
        for token in plan.runtime_command_template
    )
    if any(
        LAUNCH_DIGEST_PLACEHOLDER in token or BUILD_DIGEST_PLACEHOLDER in token
        for token in command
    ):
        _fail("runtime command provenance placeholders were not closed")
    return command


def execute_plan(plan: ProofPlan) -> Mapping[str, Any]:
    inputs = plan.inputs
    _verify_inputs(inputs)
    _prepare_output(inputs)
    _write_new_json(inputs.output_root / "input-manifest.json", inputs.input_document)
    _write_new_json(inputs.output_root / "launch-plan.json", plan.launch_document)

    build_log = inputs.output_root / "build.log"
    with _immutable_input_snapshot(inputs) as snapshot:
        build_command = _instantiate_fd_tokens(plan.build_command, snapshot)
        if (
            _run_logged(
                build_command,
                build_log,
                inputs.timeout_seconds,
                pass_fds=snapshot.pass_fds,
            )
            != 0
        ):
            _fail("controlled pinned UBT build failed")
    _verify_inputs(inputs)
    provenance = _capture_build_provenance(plan)
    _write_new_json(inputs.output_root / "build-provenance.json", provenance.document)
    _verify_inputs(inputs)
    _verify_build_provenance(plan, provenance)

    runtime_command = _runtime_command(plan, provenance.digest)
    runtime_log = inputs.output_root / "runtime.log"
    runtime_stdout = b""
    with _immutable_input_snapshot(inputs, provenance) as snapshot:
        instantiated_runtime = _instantiate_fd_tokens(runtime_command, snapshot)
        runtime_return_code, runtime_stdout = _run_runtime_captured(
            instantiated_runtime,
            runtime_log,
            inputs.timeout_seconds,
            pass_fds=snapshot.pass_fds,
        )
        if runtime_return_code != 0:
            _fail("pinned Unreal multi-client proof runtime failed")
    _verify_inputs(inputs)
    _verify_build_provenance(plan, provenance)

    envelope, receipt_raw, report_raw = parse_private_runtime_envelope(runtime_stdout)
    validate_automation_report_bytes(report_raw)
    receipt = validate_closed_receipt_bytes(
        receipt_raw,
        ReceiptExpectation(
            attempt_id=inputs.attempt_id,
            trusted_git_commit=inputs.git_commit,
            trusted_projection_digest=inputs.projection_digest,
            input_manifest_digest=inputs.input_digest,
            launch_plan_digest=plan.launch_digest,
            build_provenance_digest=provenance.digest,
        ),
    )
    evidence = _output_directories(inputs.output_root)["evidence"]
    _write_new_bytes(evidence / "r5-multiclient-proof-receipt.json", receipt_raw)
    _write_new_bytes(
        _output_directories(inputs.output_root)["automation_report"] / "index.json",
        report_raw,
    )
    acceptance = _seal_document(
        {
            "schema": ACCEPTANCE_SCHEMA,
            "attempt_id": inputs.attempt_id,
            "trusted_git_commit": inputs.git_commit,
            "input_manifest_digest": inputs.input_digest,
            "launch_plan_digest": plan.launch_digest,
            "build_provenance_digest": provenance.digest,
            "private_runtime_envelope_sha256": hashlib.sha256(
                _canonical_json_bytes(envelope)
            ).hexdigest(),
            "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
            "automation_report_sha256": hashlib.sha256(report_raw).hexdigest(),
            "claim": "active_action_reset_rejection_and_r5_transaction_replication",
        }
    )
    _write_new_json(evidence / "proof-acceptance.json", acceptance)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run pinned UBT then UE; default is a zero-write dry-run",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        inputs = prepare_inputs(
            attempt_root=args.attempt_root,
            attempt_id=args.attempt_id,
            timeout_seconds=args.timeout_seconds,
        )
        plan = build_plan(inputs)
        if not args.execute:
            print(json.dumps(plan.as_json(), sort_keys=True, indent=2))
            return 0
        receipt = execute_plan(plan)
        print(json.dumps(receipt, sort_keys=True, indent=2))
        return 0
    except ProofError as exc:
        print(f"R5_MULTICLIENT_PROOF_FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
