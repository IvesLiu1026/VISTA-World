#!/usr/bin/env python3
"""Plan or materialize the append-only R6 phone/cup visual accessory upgrade.

Dry-run is the default and performs zero writes.  Apply requires every exact
legal acknowledgement, copies the sealed R4-C project into a fresh external
attempt, and permits Unreal to mutate only the copied map.  No render, GPU,
pixel capture, AI/VLM review, dataset ingestion, or source UAsset publication
is part of this lane.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import math
import os
import pathlib
import re
import stat
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from tools.runtime.vista_playable_home import human_visual_demo_launch as launcher
from tools.ue.vista_playable_home import materialize_combined_realism_r4 as r4


PLAN_SCHEMA = "simworld.vista.human-visual-demo-accessory-r6-plan/v1"
EXECUTION_SCHEMA = launcher.ACCESSORY_R6_EXECUTION_SCHEMA
RESULT_SCHEMA = launcher.ACCESSORY_R6_RESULT_SCHEMA
DRY_RUN_STATUS = "validated_zero_write_accessory_r6_plan"
APPLY_PLAN_STATUS = "validated_accessory_r6_apply_plan_no_write"
RESULT_STATUS = launcher.ACCESSORY_R6_UPGRADE_STATUS
FAILURE_STATUS = "accessory_r6_attempt_quarantined_no_reuse"
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
PROVIDER_ID = launcher.PROVIDER_ID
RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
SOURCE_ROOT = RUN_PARENT / "combined-realism-r4-human-demo-20260829c"
SOURCE_RECEIPT = SOURCE_ROOT / launcher.COMBINED_RECEIPT_NAME
SOURCE_RECEIPT_SHA256 = (
    "fb17a5a88fc1d78061c5de0ae70e79643d33141a532431ad12ee5ef44666b71b"
)
SOURCE_RECEIPT_BYTES = 6_374
SOURCE_PROJECT_TREE = {
    "algorithm": launcher.PROJECT_STATIC_TREE_ALGORITHM,
    "file_count": 2_444,
    "total_bytes": 9_152_756_331,
    "tree_sha256": "3b86c49090a8f60fd12ba70927b53925de7f3b0471ecf4e009445d6ea5ff4df0",
}
SOURCE_MAP_SHA256 = "a3a9a0d87957e6c454f12dc4805a1735ed903b19d64fb9948bb733577f59f76c"
SOURCE_MAP_BYTES = 466_557
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
UNREAL_EDITOR_CMD = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd"
)
UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
UNREAL_EDITOR_CMD_BYTES = 459_320
BUILD_VERSION = pathlib.Path(
    "/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/Build.version"
)
BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
BUILD_VERSION_BYTES = 215
NETWORK_NAMESPACE = launcher.NETWORK_NAMESPACE_EXECUTABLE
NETWORK_NAMESPACE_SHA256 = launcher.NETWORK_NAMESPACE_EXECUTABLE_SHA256
NETWORK_NAMESPACE_BYTES = launcher.NETWORK_NAMESPACE_EXECUTABLE_BYTES
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
MAP_RELATIVE_PATH = pathlib.PurePosixPath(
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
PROJECT_NAME = "VistaPlayableHome.uproject"
MATERIALIZER_NAME = "materialize_accessory_r6.py"
COMMANDLET_NAME = "compose_accessory_r6_commandlet.py"
R4_SUPPORT_NAME = "r4-commandlet-support.py"
EXECUTION_NAME = "accessory-r6-execution.json"
RESULT_NAME = "accessory-r6-result.json"
STDOUT_NAME = "unreal-accessory-r6-stdout.log"
ENGINE_LOG_NAME = "unreal-accessory-r6-engine.log"
FAILURE_NAME = "accessory-r6-host-failure.json"
EXECUTION_ENV = "VISTA_ACCESSORY_R6_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_ACCESSORY_R6_EXECUTION_SHA256"
RESULT_ENV = "VISTA_ACCESSORY_R6_RESULT"
RESULT_SIDECAR_ENV = "VISTA_ACCESSORY_R6_RESULT_SIDECAR"
RESULT_MARKER = "VISTA_ACCESSORY_R6_RESULT:"
ATTEMPT_RE = re.compile(r"^accessory-r6-[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
TRUSTED_PATH = r4.TRUSTED_PATH
TIMEOUT_SECONDS = 1_200
LEGAL_SCOPE = copy.deepcopy(launcher.LEGAL_SCOPE)
CLAIMS = copy.deepcopy(launcher.CLAIMS)
ACCEPTANCE = copy.deepcopy(launcher.ACCESSORY_R6_ACCEPTANCE)
ACKNOWLEDGEMENTS = copy.deepcopy(launcher.ACCESSORY_R6_ACKNOWLEDGEMENTS)


class AccessoryR6Error(RuntimeError):
    """Raised before any unsafe, drifting, or non-append-only R6 action."""


@dataclasses.dataclass(frozen=True)
class Config:
    repository_root: pathlib.Path
    run_parent: pathlib.Path
    source_receipt: pathlib.Path
    source_receipt_sha256: str
    source_receipt_bytes: int
    source_project_tree: Mapping[str, Any]
    source_map_sha256: str
    source_map_bytes: int
    materializer_source: pathlib.Path
    materializer_source_sha256: str
    materializer_source_bytes: int
    commandlet_source: pathlib.Path
    commandlet_source_sha256: str
    commandlet_source_bytes: int
    unreal_editor_cmd: pathlib.Path
    unreal_editor_cmd_sha256: str
    unreal_editor_cmd_bytes: int
    build_version: pathlib.Path
    build_version_sha256: str
    build_version_bytes: int
    network_namespace: pathlib.Path
    network_namespace_sha256: str
    network_namespace_bytes: int


@dataclasses.dataclass(frozen=True)
class PreparedPlan:
    config: Config
    attempt_root: pathlib.Path
    apply_requested: bool
    acknowledgements: Mapping[str, str | None]
    source_inputs: launcher.HumanVisualDemoInputs
    source_records: tuple[r4.StaticRecord, ...]
    tool_seals: Mapping[str, r4.FileSeal]
    script_seals: Mapping[str, r4.FileSeal]
    support_seal: r4.FileSeal
    asset_inventory: Mapping[str, Any]
    accessory_contract: Mapping[str, Any]
    report: Mapping[str, Any]
    run_parent_identity: tuple[int, int]


def production_config() -> Config:
    materializer_anchor = launcher.ACCESSORY_R6_TRUSTED_SCRIPTS["materializer"]
    commandlet_anchor = launcher.ACCESSORY_R6_TRUSTED_SCRIPTS["commandlet"]
    return Config(
        repository_root=REPOSITORY_ROOT,
        run_parent=RUN_PARENT,
        source_receipt=SOURCE_RECEIPT,
        source_receipt_sha256=SOURCE_RECEIPT_SHA256,
        source_receipt_bytes=SOURCE_RECEIPT_BYTES,
        source_project_tree=copy.deepcopy(SOURCE_PROJECT_TREE),
        source_map_sha256=SOURCE_MAP_SHA256,
        source_map_bytes=SOURCE_MAP_BYTES,
        materializer_source=pathlib.Path(materializer_anchor["path"]).resolve(
            strict=True
        ),
        materializer_source_sha256=materializer_anchor["sha256"],
        materializer_source_bytes=materializer_anchor["size_bytes"],
        commandlet_source=pathlib.Path(commandlet_anchor["path"]).resolve(strict=True),
        commandlet_source_sha256=commandlet_anchor["sha256"],
        commandlet_source_bytes=commandlet_anchor["size_bytes"],
        unreal_editor_cmd=UNREAL_EDITOR_CMD,
        unreal_editor_cmd_sha256=UNREAL_EDITOR_CMD_SHA256,
        unreal_editor_cmd_bytes=UNREAL_EDITOR_CMD_BYTES,
        build_version=BUILD_VERSION,
        build_version_sha256=BUILD_VERSION_SHA256,
        build_version_bytes=BUILD_VERSION_BYTES,
        network_namespace=NETWORK_NAMESPACE,
        network_namespace_sha256=NETWORK_NAMESPACE_SHA256,
        network_namespace_bytes=NETWORK_NAMESPACE_BYTES,
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AccessoryR6Error(message)


def _canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise AccessoryR6Error("value is not finite canonical JSON") from exc


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _pin_artifact(pin: launcher.ArtifactPin) -> dict[str, Any]:
    return {"path": str(pin.path), "sha256": pin.sha256, "size_bytes": pin.size_bytes}


def _validate_attempt(
    config: Config, attempt: pathlib.Path
) -> tuple[pathlib.Path, tuple[int, int]]:
    _require(
        attempt.is_absolute()
        and os.path.normpath(str(attempt)) == str(attempt)
        and attempt.parent == config.run_parent
        and ATTEMPT_RE.fullmatch(attempt.name),
        "attempt root is outside the fixed append-only R6 namespace",
    )
    parent = config.run_parent.resolve(strict=True)
    metadata = os.lstat(parent)
    _require(
        parent == config.run_parent
        and stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == os.geteuid()
        and not metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
        "run parent identity or permissions differ",
    )
    _require(not attempt.exists(), "attempt root already exists and cannot be reused")
    return attempt, (metadata.st_dev, metadata.st_ino)


def _trusted_script_seals(config: Config) -> dict[str, r4.FileSeal]:
    return {
        "materializer": r4._read_file_seal(
            config.materializer_source,
            "Git-tracked trusted R6 materializer",
            expected_sha256=config.materializer_source_sha256,
            expected_size=config.materializer_source_bytes,
        )[0],
        "commandlet": r4._read_file_seal(
            config.commandlet_source,
            "Git-tracked trusted R6 commandlet",
            expected_sha256=config.commandlet_source_sha256,
            expected_size=config.commandlet_source_bytes,
        )[0],
    }


def _source_state(config: Config):
    receipt_seal, _raw = r4._read_file_seal(
        config.source_receipt,
        "sealed R4-C combined receipt",
        expected_sha256=config.source_receipt_sha256,
        expected_size=config.source_receipt_bytes,
    )
    inputs = launcher.load_combined_receipt(config.source_receipt)
    _require(
        inputs.receipt_schema_version == launcher.COMBINED_RECEIPT_SCHEMA_V3
        and inputs.receipt_sha256 == receipt_seal.sha256
        and inputs.project_static_tree == config.source_project_tree
        and inputs.map_object_path == MAP_OBJECT_PATH
        and inputs.map_package.sha256 == config.source_map_sha256
        and inputs.map_package.size_bytes == config.source_map_bytes
        and inputs.realism_r4_upgrade is not None
        and inputs.accessory_r6_upgrade is None,
        "sealed R4-C parent binding differs",
    )
    records = r4._collect_static_records(inputs.project.path)
    _require(
        len(records) == config.source_project_tree["file_count"]
        and sum(record.size_bytes for record in records)
        == config.source_project_tree["total_bytes"],
        "sealed R4-C static inventory differs",
    )
    manifest_rows = {record.relative_path: record for record in records}
    targets = []
    dependency_records = []
    for semantic_id, expected in sorted(launcher.ACCESSORY_R6_TARGET_ASSETS.items()):
        record = manifest_rows.get(expected["relative_path"])
        _require(
            record is not None
            and record.size_bytes == expected["size_bytes"]
            and record.mode == expected["mode"],
            "R6 source UAsset size/mode pin differs: " + semantic_id,
        )
        seal, _ = r4._read_file_seal(
            record.source,
            "R6 source UAsset",
            expected_sha256=expected["sha256"],
            expected_size=expected["size_bytes"],
        )
        dependency = {
            "asset_class": expected["asset_class"],
            "object_path": expected["object_path"],
            "package_name": expected["package_name"],
        }
        dependency_records.append(dependency)
        targets.append(
            {
                "semantic_id": semantic_id,
                "actor_path": expected["actor_path"],
                "source_mesh_object_path": expected["source_mesh_object_path"],
                "asset": dependency,
                "uasset": {
                    "relative_path": expected["relative_path"],
                    "sha256": seal.sha256,
                    "size_bytes": seal.size_bytes,
                    "mode": seal.mode,
                },
                "fit_policy": launcher.ACCESSORY_R6_FIT_POLICY,
            }
        )
    dependency_records.sort(key=lambda row: row["object_path"])
    city_pin = inputs.source_provenance["citysample_result"]
    city_path = pathlib.Path(city_pin["path"])
    _city_seal, city_raw = r4._read_file_seal(
        city_path,
        "sealed City Sample inventory",
        expected_sha256=city_pin["sha256"],
        expected_size=city_pin["size_bytes"],
    )
    _require(city_raw is not None, "City Sample inventory exceeds document policy")
    city_result = r4._strict_json(city_raw, "City Sample inventory")
    city_gates = city_result.get("gates")
    _require(
        city_raw == _canonical_json(city_result)
        and city_result.get("content_digest") == _content_digest(city_result)
        and city_result.get("schema_version")
        == "vista.citysample-crowd-human-forward-load-result/v1"
        and city_result.get("status") == "forward_load_validated_private_research_only"
        and city_result.get("accepted") is False
        and city_result.get("runtime_visual_acceptance") is False
        and city_result.get("character_provider_published") is False
        and isinstance(city_gates, dict)
        and city_gates.get("asset_registry_dependency_closure_validated") is True
        and city_gates.get("source_uassets_remained_outside_git") is True
        and all(
            city_result.get("dependency_asset_records", []).count(row) == 1
            for row in dependency_records
        ),
        "City Sample inventory boundary or StaticMesh provenance differs",
    )
    asset_inventory = {
        "citysample_result": copy.deepcopy(city_pin),
        "dependency_asset_records": dependency_records,
    }
    contract = {
        "targets": targets,
        "pot_semantic_id": launcher.ACCESSORY_R6_POT_SEMANTIC_ID,
        "fit_policy": launcher.ACCESSORY_R6_FIT_POLICY,
    }
    tool_seals = {
        "unreal_editor_cmd": r4._read_file_seal(
            config.unreal_editor_cmd,
            "UnrealEditor-Cmd",
            expected_sha256=config.unreal_editor_cmd_sha256,
            expected_size=config.unreal_editor_cmd_bytes,
            executable=True,
        )[0],
        "build_version": r4._read_file_seal(
            config.build_version,
            "Build.version",
            expected_sha256=config.build_version_sha256,
            expected_size=config.build_version_bytes,
        )[0],
        "network_namespace": r4._read_file_seal(
            config.network_namespace,
            "private network namespace wrapper",
            expected_sha256=config.network_namespace_sha256,
            expected_size=config.network_namespace_bytes,
            executable=True,
        )[0],
    }
    script_seals = _trusted_script_seals(config)
    support_pin = inputs.realism_r4_upgrade["commandlet"]
    support_seal = r4._read_file_seal(
        pathlib.Path(support_pin["path"]),
        "sealed R4 commandlet support",
        expected_sha256=support_pin["sha256"],
        expected_size=support_pin["size_bytes"],
    )[0]
    return (
        inputs,
        records,
        tool_seals,
        script_seals,
        support_seal,
        asset_inventory,
        contract,
    )


def build_plan(
    attempt_root: pathlib.Path,
    *,
    apply: bool = False,
    acknowledgements: Mapping[str, str | None] | None = None,
    config: Config | None = None,
) -> PreparedPlan:
    selected = production_config() if config is None else config
    trusted_script_seals = _trusted_script_seals(selected)
    supplied = {key: None for key in ACKNOWLEDGEMENTS}
    if acknowledgements is not None:
        _require(
            set(acknowledgements) == set(ACKNOWLEDGEMENTS),
            "acknowledgement inventory differs",
        )
        supplied.update(acknowledgements)
    if apply:
        _require(
            supplied == ACKNOWLEDGEMENTS,
            "apply requires every exact R6 acknowledgement",
        )
    attempt, parent_identity = _validate_attempt(selected, attempt_root)
    (
        inputs,
        records,
        tool_seals,
        script_seals,
        support_seal,
        asset_inventory,
        contract,
    ) = _source_state(selected)
    _require(
        script_seals == trusted_script_seals,
        "R6 scripts changed while building the pre-execution plan",
    )
    report = _seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "status": APPLY_PLAN_STATUS if apply else DRY_RUN_STATUS,
            "mode": "apply_requested_no_write_yet" if apply else "dry_run_zero_writes",
            "will_write": apply,
            "will_execute_unreal": apply,
            "attempt_root": str(attempt),
            "source_combined_receipt": _pin_artifact(
                launcher.ArtifactPin(
                    inputs.receipt, inputs.receipt_sha256, selected.source_receipt_bytes
                )
            ),
            "source_project": {
                "descriptor": _pin_artifact(inputs.project),
                "static_tree": copy.deepcopy(inputs.project_static_tree),
                "map": {
                    "object_path": inputs.map_object_path,
                    "package": _pin_artifact(inputs.map_package),
                },
            },
            "asset_inventory": copy.deepcopy(asset_inventory),
            "accessory_contract": copy.deepcopy(contract),
            "toolchain": {
                key: r4._pin(value) for key, value in sorted(tool_seals.items())
            },
            "scripts": {
                **{key: r4._pin(value) for key, value in sorted(script_seals.items())},
                "r4_commandlet_support": r4._pin(support_seal),
            },
            "execution": {
                "unreal_editor_cmd": True,
                "null_rhi": True,
                "rendering": False,
                "gpu": None,
                "display": None,
                "network": False,
                "private_network_namespace": True,
                "shell": False,
                "map_only_static_mutation": True,
                "fresh_attempt_only": True,
                "source_mutation": False,
                "pixel_access": False,
                "ue_reflection_bounds_only": True,
            },
            "copy": {
                "static_file_count": len(records),
                "static_total_bytes": sum(record.size_bytes for record in records),
                "strategy": "ficlone_then_bounded_stream_copy_fallback",
                "mutable_source_directories_excluded": sorted(
                    launcher.MUTABLE_PROJECT_DIRECTORIES
                ),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(supplied),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )
    return PreparedPlan(
        config=selected,
        attempt_root=attempt,
        apply_requested=apply,
        acknowledgements=copy.deepcopy(supplied),
        source_inputs=inputs,
        source_records=records,
        tool_seals=copy.deepcopy(tool_seals),
        script_seals=copy.deepcopy(script_seals),
        support_seal=support_seal,
        asset_inventory=copy.deepcopy(asset_inventory),
        accessory_contract=copy.deepcopy(contract),
        report=report,
        run_parent_identity=parent_identity,
    )


def _same_plan(left: PreparedPlan, right: PreparedPlan) -> bool:
    return left == right


def _assert_prepared_sources(prepared: PreparedPlan) -> None:
    state = _source_state(prepared.config)
    _require(
        state
        == (
            prepared.source_inputs,
            prepared.source_records,
            prepared.tool_seals,
            prepared.script_seals,
            prepared.support_seal,
            prepared.asset_inventory,
            prepared.accessory_contract,
        ),
        "R6 source/tool/script state changed",
    )


def _execution_document(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    materializer: pathlib.Path,
    commandlet: pathlib.Path,
    support: pathlib.Path,
    source_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    attempt = prepared.attempt_root
    source_map = project.parent / pathlib.Path(MAP_RELATIVE_PATH)
    return _seal_document(
        {
            "schema_version": EXECUTION_SCHEMA,
            "status": launcher.ACCESSORY_R6_EXECUTION_STATUS,
            "attempt_root": str(attempt),
            "project": r4._artifact(project, "copied project descriptor"),
            "materializer": r4._artifact(materializer, "copied R6 materializer"),
            "commandlet": r4._artifact(commandlet, "copied R6 commandlet"),
            "r4_commandlet_support": r4._artifact(
                support, "copied R4 commandlet support"
            ),
            "result": {
                "path": str(attempt / RESULT_NAME),
                "sidecar_path": str(attempt / (RESULT_NAME + ".sha256")),
            },
            "engine": {
                "version": ENGINE_VERSION,
                "unreal_editor_cmd": r4._pin(prepared.tool_seals["unreal_editor_cmd"]),
                "build_version": r4._pin(prepared.tool_seals["build_version"]),
                "network_namespace": r4._pin(prepared.tool_seals["network_namespace"]),
                "null_rhi": True,
            },
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "relative_path": MAP_RELATIVE_PATH.as_posix(),
                "source_package": r4._artifact(source_map, "copied source map"),
            },
            "parent_combined_receipt": _pin_artifact(
                launcher.ArtifactPin(
                    prepared.source_inputs.receipt,
                    prepared.source_inputs.receipt_sha256,
                    prepared.config.source_receipt_bytes,
                )
            ),
            "source_project_static_tree": copy.deepcopy(
                prepared.source_inputs.project_static_tree
            ),
            "source_static_manifest": copy.deepcopy(dict(source_manifest)),
            "asset_inventory": copy.deepcopy(prepared.asset_inventory),
            "accessory_contract": copy.deepcopy(prepared.accessory_contract),
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "acknowledgements": copy.deepcopy(dict(prepared.acknowledgements)),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
        }
    )


def build_unreal_command(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    commandlet: pathlib.Path,
    private_root: pathlib.Path,
) -> list[str]:
    return [
        str(prepared.config.network_namespace),
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
        str(prepared.config.unreal_editor_cmd),
        str(project),
        "-run=pythonscript",
        f"-script={commandlet}",
        "-nullrhi",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-NOSOUND",
        "-NoAnalytics",
        "-UDPMESSAGING_TRANSPORT_ENABLE=0",
        "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
        "-notraceserver",
        "-ddc=InstalledNoZenLocalFallback",
        "-SaveToUserDir",
        f"-UserDir={private_root / 'user'}",
        f"-LocalDataCachePath={private_root / 'ddc'}",
        f"-abslog={prepared.attempt_root / ENGINE_LOG_NAME}",
        "-stdout",
        "-FullStdOutLogOutput",
    ]


def sanitized_environment(
    private_root: pathlib.Path,
    *,
    execution_path: pathlib.Path,
    execution_sha256: str,
    attempt: pathlib.Path,
) -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": TRUSTED_PATH,
        "HOME": str(private_root / "home"),
        "TMPDIR": str(private_root / "tmp"),
        "XDG_CACHE_HOME": str(private_root / "xdg-cache"),
        "XDG_CONFIG_HOME": str(private_root / "xdg-config"),
        "XDG_DATA_HOME": str(private_root / "xdg-data"),
        EXECUTION_ENV: str(execution_path),
        EXECUTION_SHA_ENV: execution_sha256,
        RESULT_ENV: str(attempt / RESULT_NAME),
        RESULT_SIDECAR_ENV: str(attempt / (RESULT_NAME + ".sha256")),
    }


def _run_unreal(
    prepared: PreparedPlan,
    *,
    project: pathlib.Path,
    commandlet: pathlib.Path,
    execution_path: pathlib.Path,
    execution_sha256: str,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    process_tree_waiter: Callable[..., int] = r4._wait_process_tree,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> tuple[pathlib.Path, pathlib.Path]:
    _require(
        isinstance(timeout_seconds, (int, float))
        and not isinstance(timeout_seconds, bool)
        and math.isfinite(float(timeout_seconds))
        and timeout_seconds > 0,
        "Unreal timeout must be positive and finite",
    )
    _require(
        not r4._snapshot_preexisting_descendants(),
        "R6 supervisor has a preexisting child or descendant",
    )
    attempt = prepared.attempt_root
    stdout_path = attempt / STDOUT_NAME
    engine_log = attempt / ENGINE_LOG_NAME
    descriptor = os.open(
        stdout_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        PRIVATE_FILE_MODE,
    )
    os.fchmod(descriptor, PRIVATE_FILE_MODE)
    previous_handlers: Mapping[int, Any] = {}
    previous_subreaper: bool | None = None
    try:
        with (
            os.fdopen(descriptor, "wb") as output,
            tempfile.TemporaryDirectory(prefix="vista-r6-nullrhi-") as raw_private,
        ):
            private_root = pathlib.Path(raw_private).resolve(strict=True)
            os.chmod(private_root, PRIVATE_DIRECTORY_MODE)
            for name in (
                "home",
                "tmp",
                "xdg-cache",
                "xdg-config",
                "xdg-data",
                "user",
                "ddc",
            ):
                (private_root / name).mkdir(mode=PRIVATE_DIRECTORY_MODE)
            environment = sanitized_environment(
                private_root,
                execution_path=execution_path,
                execution_sha256=execution_sha256,
                attempt=attempt,
            )
            command = build_unreal_command(
                prepared,
                project=project,
                commandlet=commandlet,
                private_root=private_root,
            )
            previous_handlers, _mask = r4._signal_handlers()
            try:
                floor = r4._process_start_floor()
                previous_subreaper = r4._set_child_subreaper(True)
                process = popen_factory(
                    command,
                    cwd=project.parent,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    start_new_session=True,
                    shell=False,
                    umask=0o077,
                )
                return_code = process_tree_waiter(
                    process, timeout=timeout_seconds, spawn_floor=floor
                )
            except subprocess.TimeoutExpired as exc:
                raise AccessoryR6Error("Unreal R6 upgrade timed out") from exc
            finally:
                r4._restore_handlers(previous_handlers)
            _require(return_code == 0, f"Unreal R6 upgrade exited {return_code}")
    finally:
        if previous_subreaper is not None:
            r4._set_child_subreaper(previous_subreaper)
        try:
            os.close(descriptor)
        except OSError:
            pass
    _require(engine_log.is_file(), "Unreal R6 engine log is absent")
    os.chmod(engine_log, PRIVATE_FILE_MODE, follow_symlinks=False)
    return stdout_path, engine_log


def _marker_payloads(stdout_path: pathlib.Path) -> list[dict[str, Any]]:
    payloads = []
    with stdout_path.open("r", encoding="utf-8", errors="replace") as source:
        for line in source:
            if RESULT_MARKER not in line:
                continue
            try:
                value = json.loads(line.split(RESULT_MARKER, 1)[1].strip())
            except json.JSONDecodeError as exc:
                raise AccessoryR6Error("R6 result marker is invalid") from exc
            _require(isinstance(value, dict), "R6 result marker is not an object")
            payloads.append(value)
    return payloads


def _validate_result(
    prepared: PreparedPlan,
    *,
    execution: Mapping[str, Any],
    execution_sha256: str,
    stdout_path: pathlib.Path,
) -> dict[str, Any]:
    result_path = prepared.attempt_root / RESULT_NAME
    seal, raw = r4._read_file_seal(result_path, "R6 result")
    _require(raw is not None and seal.sha256, "R6 result is unavailable")
    result = r4._strict_json(raw, "R6 result")
    _require(
        raw == _canonical_json(result)
        and result.get("content_digest") == _content_digest(result)
        and result.get("execution_sha256") == execution_sha256,
        "R6 result canonical identity differs",
    )
    map_pin = result.get("map_package")
    _require(isinstance(map_pin, dict), "R6 result map pin absent")
    map_package = launcher.ArtifactPin(
        pathlib.Path(map_pin["path"]), map_pin["sha256"], map_pin["size_bytes"]
    )
    validated, _observations = launcher._validate_r6_result(
        launcher.ArtifactPin(result_path, seal.sha256, seal.size_bytes),
        execution=execution,
        map_package=map_package,
        contract=prepared.accessory_contract,
    )
    _require(
        _marker_payloads(stdout_path)
        == [{"path": str(result_path), "sha256": seal.sha256}],
        "R6 result marker inventory differs",
    )
    return validated


def _assert_only_map_changed(before, after) -> None:
    r4._assert_only_map_changed(before, after)


def _publication_state(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    result: Mapping[str, Any],
    baseline_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    _assert_prepared_sources(prepared)
    attempt = prepared.attempt_root
    project = attempt / "project" / PROJECT_NAME
    tree, manifest = r4._project_manifest(project)
    _assert_only_map_changed(baseline_manifest, manifest)
    map_package = attempt / "project" / pathlib.Path(MAP_RELATIVE_PATH)
    _require(
        result["map_package"] == r4._artifact(map_package, "publication R6 map"),
        "publication map differs",
    )
    return {
        "project": r4._artifact(project, "publication project"),
        "project_static_tree": tree,
        "project_manifest": manifest,
        "map_package": r4._artifact(map_package, "publication map"),
        "execution": r4._artifact(execution_path, "publication execution"),
        "result": r4._artifact(attempt / RESULT_NAME, "publication result"),
        "materializer": r4._artifact(
            attempt / MATERIALIZER_NAME, "publication materializer"
        ),
        "commandlet": r4._artifact(attempt / COMMANDLET_NAME, "publication commandlet"),
        "r4_commandlet_support": r4._artifact(
            attempt / R4_SUPPORT_NAME, "publication R4 support"
        ),
        "parent_combined_receipt": _pin_artifact(
            launcher.ArtifactPin(
                prepared.source_inputs.receipt,
                prepared.source_inputs.receipt_sha256,
                prepared.config.source_receipt_bytes,
            )
        ),
        "source_map": _pin_artifact(prepared.source_inputs.map_package),
        "unreal_editor_cmd": r4._pin(prepared.tool_seals["unreal_editor_cmd"]),
        "build_version": r4._pin(prepared.tool_seals["build_version"]),
        "network_namespace": r4._pin(prepared.tool_seals["network_namespace"]),
        "asset_inventory": copy.deepcopy(prepared.asset_inventory),
        "observations": copy.deepcopy(launcher.ACCESSORY_R6_OBSERVATIONS),
    }


def _combined_receipt(
    prepared: PreparedPlan, state: Mapping[str, Any]
) -> dict[str, Any]:
    return _seal_document(
        {
            "schema_version": launcher.COMBINED_RECEIPT_SCHEMA_V4,
            "status": launcher.COMBINED_RECEIPT_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "project": copy.deepcopy(state["project"]),
            "project_static_tree": copy.deepcopy(state["project_static_tree"]),
            "source_provenance": copy.deepcopy(
                dict(prepared.source_inputs.source_provenance)
            ),
            "executable": _pin_artifact(prepared.source_inputs.executable),
            "map": {
                "object_path": MAP_OBJECT_PATH,
                "package": copy.deepcopy(state["map_package"]),
            },
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "accessory_r6_upgrade": {
                "schema_version": launcher.ACCESSORY_R6_UPGRADE_SCHEMA,
                "status": launcher.ACCESSORY_R6_UPGRADE_STATUS,
                "parent_combined_receipt": copy.deepcopy(
                    state["parent_combined_receipt"]
                ),
                "source_map": copy.deepcopy(state["source_map"]),
                "source_project_static_tree": copy.deepcopy(
                    dict(prepared.source_inputs.project_static_tree)
                ),
                "asset_inventory": copy.deepcopy(state["asset_inventory"]),
                "execution": copy.deepcopy(state["execution"]),
                "result": copy.deepcopy(state["result"]),
                "materializer": copy.deepcopy(state["materializer"]),
                "commandlet": copy.deepcopy(state["commandlet"]),
                "r4_commandlet_support": copy.deepcopy(state["r4_commandlet_support"]),
                "unreal_editor_cmd": copy.deepcopy(state["unreal_editor_cmd"]),
                "build_version": copy.deepcopy(state["build_version"]),
                "network_namespace": copy.deepcopy(state["network_namespace"]),
                "map_object_path": MAP_OBJECT_PATH,
                "output_project_static_tree": copy.deepcopy(
                    state["project_static_tree"]
                ),
                "observations": copy.deepcopy(state["observations"]),
                "acceptance": copy.deepcopy(ACCEPTANCE),
            },
        }
    )


def _state_without_manifest(state):
    result = copy.deepcopy(dict(state))
    result.pop("project_manifest", None)
    return result


def _publish_combined_receipt(
    prepared: PreparedPlan,
    *,
    execution_path: pathlib.Path,
    result: Mapping[str, Any],
    baseline_manifest: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    baseline = _publication_state(
        prepared,
        execution_path=execution_path,
        result=result,
        baseline_manifest=baseline_manifest,
    )
    receipt = _combined_receipt(prepared, baseline)
    final = _publication_state(
        prepared,
        execution_path=execution_path,
        result=result,
        baseline_manifest=baseline_manifest,
    )
    _require(
        _state_without_manifest(final) == _state_without_manifest(baseline)
        and final["project_manifest"] == baseline["project_manifest"],
        "R6 publication state changed during final seal window",
    )
    raw = _canonical_json(receipt)
    digest = r4._write_exclusive(
        prepared.attempt_root / launcher.COMBINED_RECEIPT_NAME, raw
    )
    r4._write_exclusive(
        prepared.attempt_root / launcher.COMBINED_RECEIPT_SIDECAR_NAME,
        f"{digest}  {launcher.COMBINED_RECEIPT_NAME}\n".encode("ascii"),
    )
    loaded = launcher.load_combined_receipt(
        prepared.attempt_root / launcher.COMBINED_RECEIPT_NAME
    )
    _require(
        loaded.receipt_schema_version == launcher.COMBINED_RECEIPT_SCHEMA_V4
        and loaded.receipt_sha256 == digest
        and loaded.accessory_r6_upgrade == receipt["accessory_r6_upgrade"]
        and loaded.realism_r4_upgrade == prepared.source_inputs.realism_r4_upgrade,
        "launcher self-validation of R6 v4 receipt differs",
    )
    return receipt


def apply_plan(
    prepared: PreparedPlan,
    *,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
) -> dict[str, Any]:
    _require(
        prepared.apply_requested
        and dict(prepared.acknowledgements) == ACKNOWLEDGEMENTS,
        "exactly acknowledged R6 apply plan required",
    )
    expected = build_plan(
        prepared.attempt_root,
        apply=True,
        acknowledgements=ACKNOWLEDGEMENTS,
        config=prepared.config,
    )
    _require(_same_plan(prepared, expected), "R6 apply plan changed")
    parent_metadata = os.lstat(prepared.config.run_parent)
    _require(
        (parent_metadata.st_dev, parent_metadata.st_ino)
        == prepared.run_parent_identity,
        "run parent changed before apply",
    )
    attempt = prepared.attempt_root
    attempt.mkdir(mode=PRIVATE_DIRECTORY_MODE)
    try:
        project_root = attempt / "project"
        project_root.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        project_fd = r4._open_directory(project_root)
        try:
            r4._mkdir_projection(project_fd, prepared.source_records)
            methods = [
                r4._copy_record(project_fd, record)
                for record in prepared.source_records
            ]
        finally:
            os.close(project_fd)
        _require(
            len(methods) == len(prepared.source_records),
            "project copy accounting differs",
        )
        project = project_root / PROJECT_NAME
        baseline_tree, baseline_manifest = r4._project_manifest(project)
        _require(
            baseline_tree == prepared.source_inputs.project_static_tree,
            "copied R4-C tree differs",
        )
        materializer = attempt / MATERIALIZER_NAME
        commandlet = attempt / COMMANDLET_NAME
        support = attempt / R4_SUPPORT_NAME
        r4._copy_sealed_file(prepared.script_seals["materializer"], materializer)
        r4._copy_sealed_file(prepared.script_seals["commandlet"], commandlet)
        r4._copy_sealed_file(prepared.support_seal, support)
        execution = _execution_document(
            prepared,
            project=project,
            materializer=materializer,
            commandlet=commandlet,
            support=support,
            source_manifest=baseline_manifest,
        )
        execution_path = attempt / EXECUTION_NAME
        execution_raw = _canonical_json(execution)
        execution_sha = r4._write_exclusive(execution_path, execution_raw)
        _assert_prepared_sources(prepared)
        _require(
            r4._project_manifest(project)[0] == baseline_tree,
            "copied project changed before UE",
        )
        stdout_path, _engine_log = _run_unreal(
            prepared,
            project=project,
            commandlet=commandlet,
            execution_path=execution_path,
            execution_sha256=execution_sha,
            popen_factory=popen_factory,
        )
        _assert_prepared_sources(prepared)
        result = _validate_result(
            prepared,
            execution=execution,
            execution_sha256=execution_sha,
            stdout_path=stdout_path,
        )
        output_tree, output_manifest = r4._project_manifest(project)
        _assert_only_map_changed(baseline_manifest, output_manifest)
        _require(output_tree != baseline_tree, "R6 output tree did not change")
        return _publish_combined_receipt(
            prepared,
            execution_path=execution_path,
            result=result,
            baseline_manifest=baseline_manifest,
        )
    except BaseException as exc:
        failure = _seal_document(
            {
                "schema_version": PLAN_SCHEMA,
                "status": FAILURE_STATUS,
                "attempt_root": str(attempt),
                "quarantined": True,
                "source_mutation": False,
                "human_operated_visual_demo_only": True,
                "prohibited_agent_adapter": True,
                "legal_scope": copy.deepcopy(LEGAL_SCOPE),
                "claims": copy.deepcopy(CLAIMS),
                "acceptance": copy.deepcopy(ACCEPTANCE),
                "error": {"type": type(exc).__name__, "message": str(exc)[:512]},
            }
        )
        try:
            r4._write_exclusive(attempt / FAILURE_NAME, _canonical_json(failure))
        except BaseException:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", required=True, type=pathlib.Path)
    parser.add_argument("--apply", action="store_true")
    for key in ACKNOWLEDGEMENTS:
        parser.add_argument("--ack-" + key.replace("_", "-"), action="store_true")
    return parser.parse_args(argv)


def _cli_acknowledgements(arguments: argparse.Namespace) -> dict[str, str | None]:
    return {
        key: ACKNOWLEDGEMENTS[key] if getattr(arguments, "ack_" + key) else None
        for key in ACKNOWLEDGEMENTS
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        prepared = build_plan(
            arguments.attempt_root,
            apply=arguments.apply,
            acknowledgements=_cli_acknowledgements(arguments),
        )
        result = apply_plan(prepared) if arguments.apply else prepared.report
        print(_canonical_json(result).decode("utf-8"), end="")
        return 0
    except (
        AccessoryR6Error,
        r4.CombinedRealismR4Error,
        launcher.HumanVisualDemoError,
    ) as exc:
        print(f"accessory R6 materializer refused: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
