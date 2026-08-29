#!/usr/bin/env python3
"""Plan and verify the human-only PSO capture/package receipt chain.

Planning is zero-write and zero-subprocess. Receipt loading is read-only and
closes every source -> seed -> human capture -> expand -> final-cook edge,
including fixed paths, exact argv, tool pins, logs, and artifact bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tools.ue.vista_playable_home import human_visual_package_receipt as package_lane


PLAN_SCHEMA = "simworld.vista.human-visual-pso-seed-plan/v2"
CHAIN_SCHEMA = "simworld.vista.human-visual-pso-receipt-chain/v1"
SEED_RECEIPT_SCHEMA = "simworld.vista.human-visual-pso-seed-cook-receipt/v1"
CAPTURE_RECEIPT_SCHEMA = "simworld.vista.human-visual-pso-capture-receipt/v1"
EXPAND_RECEIPT_SCHEMA = "simworld.vista.human-visual-pso-expand-receipt/v1"
FINAL_COOK_RECEIPT_SCHEMA = "simworld.vista.human-visual-pso-final-cook-receipt/v1"
DISPLAY, GPU, WIDTH, HEIGHT = ":118", 0, 1920, 1080
TARGET_FPS, SCREEN_PERCENTAGE = 60, 100
STABLE_CACHE_NAME = "VistaPlayableHome_SF_VULKAN_SM6.spc"
MAX_RECEIPT_BYTES = 4 * 1024 * 1024
MAX_LOG_BYTES = 256 * 1024 * 1024
MAX_STAGE_ARTIFACTS = 4096
BAKED_CACHE_BASENAME = "VistaPlayableHome_SF_VULKAN_SM6.stable.upipelinecache"
BAKED_CACHE_RELATIVE = (
    Path("final-cook/cooked/Linux/VistaPlayableHome/Content/PipelineCaches/Linux")
    / BAKED_CACHE_BASENAME
)

STAGE_IDS = ("seed_cook", "human_capture", "expand", "final_cook")
STAGE_SCHEMA = {
    "seed_cook": SEED_RECEIPT_SCHEMA,
    "human_capture": CAPTURE_RECEIPT_SCHEMA,
    "expand": EXPAND_RECEIPT_SCHEMA,
    "final_cook": FINAL_COOK_RECEIPT_SCHEMA,
}
STAGE_STATUS = {
    "seed_cook": "sealed_pso_seed_cook",
    "human_capture": "sealed_human_pso_capture",
    "expand": "sealed_expanded_stable_cache",
    "final_cook": "sealed_pso_final_cook",
}
STAGE_RECEIPT_RELATIVE = {
    "seed_cook": Path("seed-cook/pso-seed-cook-receipt.json"),
    "human_capture": Path("pso-capture/pso-human-capture-receipt.json"),
    "expand": Path("expand/pso-expand-receipt.json"),
    "final_cook": Path("final-cook/pso-final-cook-receipt.json"),
}
STAGE_LOG_RELATIVE = {
    "seed_cook": Path("seed-cook/runuat.log"),
    "human_capture": Path("pso-capture/capture.log"),
    "expand": Path("expand/expand.log"),
    "final_cook": Path("final-cook/runuat.log"),
}
STAGE_PARENT_IDS = {
    "seed_cook": ("sealed_r3_source",),
    "human_capture": ("seed_cook",),
    "expand": ("seed_cook", "human_capture"),
    "final_cook": ("expand",),
}
RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "stage",
        "attempt_root",
        "source",
        "parents",
        "toolchain",
        "command",
        "artifacts",
        "legal_scope",
        "claims",
        "content_digest",
    }
)
SOURCE_KEYS = frozenset(
    {"combined_receipt", "combined_receipt_sha256", "combined_content_digest"}
)
TOOLCHAIN_KEYS = frozenset(
    {
        "engine_version",
        "engine_changelist",
        "run_uat",
        "editor_cmd",
        "build_version",
        "network_wrapper",
    }
)
TOOL_RECORD_KEYS = frozenset({"path", "sha256", "size_bytes", "mode"})
COMMAND_KEYS = frozenset({"argv", "argv_sha256", "shell", "returncode", "log"})
COVERAGE_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "rooms",
        "interactions",
        "human_operator_attested",
        "agent_adapter_used",
        "ai_vlm_pixel_review_used",
        "content_digest",
    }
)
COVERAGE_ROOMS = ("entry", "living_room", "kitchen", "office", "bedroom", "bathroom")
COVERAGE_INTERACTIONS = ("walk", "sprint", "jump", "crouch", "pickup", "drop")
ARTIFACT_KEYS = {
    "seed_cook": frozenset(
        {
            "archive",
            "launcher",
            "project_descriptor",
            "source_projection_manifest",
            "stable_keys",
        }
    ),
    "human_capture": frozenset(
        {"recorded_psos", "coverage_ledger", "seed_projection_manifest"}
    ),
    "expand": frozenset({"stable_cache"}),
    "final_cook": frozenset(
        {
            "archive",
            "launcher",
            "executable",
            "pak",
            "project_descriptor",
            "stable_cache_input",
            "baked_pipeline_caches",
        }
    ),
}


class HumanVisualPsoError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class StageReceiptBinding:
    stage: str
    receipt: package_lane.FileSeal
    payload: Mapping[str, Any]
    log: package_lane.FileSeal
    artifact_sha256s: tuple[str, ...]


@dataclass(frozen=True)
class ReceiptChainBinding:
    schema_version: str
    attempt_root: Path
    seed_cook: StageReceiptBinding
    human_capture: StageReceiptBinding
    expand: StageReceiptBinding
    final_cook: StageReceiptBinding


def _fail(code: str, message: str) -> None:
    raise HumanVisualPsoError(code, message)


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
        ).encode()
    except (TypeError, ValueError) as exc:
        raise HumanVisualPsoError("JSON_INVALID", "not finite canonical JSON") from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def _exact(value: Any, keys: frozenset[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail("SCHEMA_CLOSED", f"{label} has a non-closed key inventory")
    return value


def _command_sha256(argv: list[str]) -> str:
    return hashlib.sha256(canonical_json(argv)).hexdigest()


def capture_command(inputs: package_lane.PackagePlanInputs) -> list[str]:
    attempt = inputs.config.attempt_root
    return [
        str(inputs.network_wrapper.path),
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
        str(attempt / "seed-cook/archive/Linux/VistaPlayableHome.sh"),
        "-game",
        "-Windowed",
        "-ForceRes",
        "-ResX=1920",
        "-ResY=1080",
        "-graphicsadapter=0",
        f"-UserDir={attempt / 'pso-capture/user'}",
        f"-LocalDataCachePath={attempt / 'pso-capture/ddc'}",
        "-SaveToUserDir",
        "-NoSplash",
        "-NOSOUND",
        "-NoAnalytics",
        "-NoVSync",
        "-notraceserver",
        "-logpso",
        (
            "-ExecCmds=t.MaxFPS 60,r.ScreenPercentage 100,"
            "r.ShaderPipelineCache.Enabled 1,r.ShaderPipelineCache.LogPSO 1,"
            "r.ShaderPipelineCache.SaveBoundPSOLog 1,r.PSOPrecaching 1,"
            "r.PSOPrecache.Validation 2"
        ),
        "-UDPMESSAGING_TRANSPORT_ENABLE=0",
        "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
        "-VistaCameraProfile=realistic_interior_r2",
        "-VistaCharacterProvider=citysample_crowd_visual_demo_v1",
        "-VistaHumanOperatedVisualDemo",
    ]


def expand_command(inputs: package_lane.PackagePlanInputs) -> list[str]:
    attempt = inputs.config.attempt_root
    return [
        str(inputs.editor_cmd.path),
        str(attempt / package_lane.SEED_PROJECT_RELATIVE / package_lane.PROJECT_NAME),
        "-run=ShaderPipelineCacheTools",
        "Expand",
        str(attempt / "pso-capture/user/Saved/CollectedPSOs/*.rec.upipelinecache"),
        str(
            attempt / "seed-cook/cooked/Linux/VistaPlayableHome/Metadata/"
            "PipelineCaches/*.shk"
        ),
        str(attempt / "expand" / STABLE_CACHE_NAME),
        "-nop4",
        "-unattended",
        "-NoSplash",
        "-NoSound",
        "-NoAnalytics",
        "-nullrhi",
        "-utf8output",
    ]


def expected_command(inputs: package_lane.PackagePlanInputs, stage: str) -> list[str]:
    if stage == "seed_cook":
        return package_lane.build_uat_command(inputs, phase="seed_cook")
    if stage == "human_capture":
        return capture_command(inputs)
    if stage == "expand":
        return expand_command(inputs)
    if stage == "final_cook":
        return package_lane.build_uat_command(inputs, phase="final_cook")
    _fail("STAGE_INVALID", "stage is outside the closed vocabulary")


def _tool_record(seal: package_lane.FileSeal) -> dict[str, Any]:
    return {
        "path": str(seal.path),
        "sha256": seal.sha256,
        "size_bytes": seal.size_bytes,
        "mode": seal.mode,
    }


def toolchain_record(inputs: package_lane.PackagePlanInputs) -> dict[str, Any]:
    return {
        "engine_version": package_lane.PINNED_ENGINE_VERSION,
        "engine_changelist": package_lane.PINNED_ENGINE_CHANGELIST,
        "run_uat": _tool_record(inputs.run_uat),
        "editor_cmd": _tool_record(inputs.editor_cmd),
        "build_version": _tool_record(inputs.build_version),
        "network_wrapper": _tool_record(inputs.network_wrapper),
    }


def source_record(inputs: package_lane.PackagePlanInputs) -> dict[str, Any]:
    return {
        "combined_receipt": str(inputs.source.receipt),
        "combined_receipt_sha256": inputs.source.receipt_sha256,
        "combined_content_digest": inputs.source.receipt_content_digest,
    }


def _file_record(seal: package_lane.FileSeal, attempt: Path) -> dict[str, Any]:
    try:
        relative = seal.path.relative_to(attempt)
    except ValueError as exc:
        raise HumanVisualPsoError("ARTIFACT_PATH_INVALID", "outside attempt") from exc
    return {
        "relative_path": relative.as_posix(),
        "sha256": seal.sha256,
        "size_bytes": seal.size_bytes,
        "mode": seal.mode,
    }


def _sidecar(relative: Path) -> Path:
    return relative.with_name(relative.name + ".sha256")


def _load_canonical_receipt(inputs: package_lane.PackagePlanInputs, stage: str):
    relative = STAGE_RECEIPT_RELATIVE[stage]
    receipt = package_lane._fixed_attempt_file(
        inputs.config.attempt_root, relative, label=f"{stage} receipt"
    )
    raw = package_lane._read_after_seal(
        receipt, label=f"{stage} receipt", maximum=MAX_RECEIPT_BYTES
    )
    payload = package_lane._strict_json(raw, label=f"{stage} receipt")
    if raw != canonical_json(payload):
        _fail("RECEIPT_CANONICAL_INVALID", f"{stage} receipt is not canonical")
    sidecar = package_lane._fixed_attempt_file(
        inputs.config.attempt_root, _sidecar(relative), label=f"{stage} sidecar"
    )
    sidecar_raw = package_lane._read_after_seal(
        sidecar, label=f"{stage} sidecar", maximum=256
    )
    if sidecar_raw != f"{receipt.sha256}  {relative.name}\n".encode():
        _fail("RECEIPT_SIDECAR_INVALID", f"{stage} sidecar differs")
    return payload, receipt


def _validate_toolchain(payload: Any, inputs: package_lane.PackagePlanInputs) -> None:
    value = _exact(payload, TOOLCHAIN_KEYS, label="toolchain")
    for key in ("run_uat", "editor_cmd", "build_version", "network_wrapper"):
        _exact(value.get(key), TOOL_RECORD_KEYS, label=f"toolchain {key}")
    if value != toolchain_record(inputs):
        _fail("TOOLCHAIN_PIN_MISMATCH", "stage toolchain differs")


def expected_parents(inputs, stage: str, loaded: Mapping[str, StageReceiptBinding]):
    result = {}
    for parent in STAGE_PARENT_IDS[stage]:
        if parent == "sealed_r3_source":
            result[parent] = {
                "sha256": inputs.source.receipt_sha256,
                "content_digest": inputs.source.receipt_content_digest,
            }
        else:
            if parent not in loaded:
                _fail("RECEIPT_EDGE_INVALID", f"missing {stage} parent")
            result[parent] = _file_record(
                loaded[parent].receipt, inputs.config.attempt_root
            )
    return result


def _fixed_directory(attempt: Path, relative: Path, *, label: str) -> Path:
    candidate = attempt / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(attempt)
        metadata = os.lstat(candidate)
    except (OSError, ValueError) as exc:
        raise HumanVisualPsoError("ARTIFACT_PATH_INVALID", f"{label} escaped") from exc
    if (
        resolved != candidate
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        _fail("ARTIFACT_PATH_INVALID", f"{label} is not protected")
    return candidate


def _enumerate_files(
    attempt: Path, relative: Path, *, suffix: str, recursive: bool, label: str
):
    directory = _fixed_directory(attempt, relative, label=label)
    iterator = (
        directory.rglob(f"*{suffix}") if recursive else directory.glob(f"*{suffix}")
    )
    paths = sorted(iterator, key=lambda p: p.as_posix().encode())
    if not paths or len(paths) > MAX_STAGE_ARTIFACTS:
        _fail("ARTIFACT_INVENTORY_INVALID", f"{label} inventory invalid")
    seals = []
    for path in paths:
        if path.is_symlink():
            _fail("ARTIFACT_PATH_INVALID", f"{label} contains a symlink")
        seal = package_lane.seal_file(path, label=label)
        if seal.size_bytes <= 0:
            _fail("ARTIFACT_SIZE_INVALID", f"{label} contains empty bytes")
        seals.append(seal)
    return tuple(seals)


def _record_list(payload: Any, observed, *, attempt: Path, label: str):
    if not isinstance(payload, list):
        _fail("ARTIFACT_INVENTORY_INVALID", f"{label} must be a list")
    for item in payload:
        _exact(item, package_lane.ARTIFACT_KEYS, label=f"{label} record")
    expected = [_file_record(seal, attempt) for seal in observed]
    if payload != expected:
        _fail("ARTIFACT_PIN_MISMATCH", f"{label} inventory differs")
    return tuple(seal.sha256 for seal in observed)


def _archive(payload: Any, attempt: Path, relative: Path, *, label: str) -> str:
    observed = package_lane.compute_archive_tree(
        _fixed_directory(attempt, relative, label=label)
    )
    if payload != observed:
        _fail("ARCHIVE_PIN_MISMATCH", f"{label} differs")
    return str(observed["tree_sha256"])


def _coverage(seal: package_lane.FileSeal) -> None:
    raw = package_lane._read_after_seal(
        seal, label="coverage ledger", maximum=MAX_RECEIPT_BYTES
    )
    payload = package_lane._strict_json(raw, label="coverage ledger")
    value = _exact(payload, COVERAGE_KEYS, label="coverage ledger")
    if raw != canonical_json(value) or (
        value.get("schema_version")
        != "simworld.vista.human-visual-pso-coverage-ledger/v1"
        or value.get("status") != "human_traversal_attested"
        or value.get("rooms") != list(COVERAGE_ROOMS)
        or value.get("interactions") != list(COVERAGE_INTERACTIONS)
        or value.get("human_operator_attested") is not True
        or value.get("agent_adapter_used") is not False
        or value.get("ai_vlm_pixel_review_used") is not False
        or value.get("content_digest") != content_digest(value)
    ):
        _fail("COVERAGE_INVALID", "coverage ledger differs")


def _validate_command(payload: Any, inputs, stage: str):
    value = _exact(payload, COMMAND_KEYS, label=f"{stage} command")
    argv = expected_command(inputs, stage)
    if (
        value.get("argv") != argv
        or value.get("argv_sha256") != _command_sha256(argv)
        or value.get("shell") is not False
        or value.get("returncode") != 0
    ):
        _fail("COMMAND_INVALID", f"{stage} command differs")
    return package_lane._validate_file_record(
        value.get("log"),
        attempt_root=inputs.config.attempt_root,
        expected_relative=STAGE_LOG_RELATIVE[stage],
        label=f"{stage} log",
    )


def _log_text(seal: package_lane.FileSeal, *, stage: str) -> str:
    raw = package_lane._read_after_seal(
        seal, label=f"{stage} log", maximum=MAX_LOG_BYTES
    )
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HumanVisualPsoError(
            "STAGE_LOG_INVALID", f"{stage} log is not UTF-8"
        ) from exc


def _require_stage_log_semantics(
    stage: str, log: package_lane.FileSeal, inputs: package_lane.PackagePlanInputs
) -> None:
    text = _log_text(log, stage=stage)
    failure = (
        r"BUILD FAILED|Cook (?:has )?failed|"
        r"completed with errors|"
        r"AutomationTool exiting with ExitCode=(?!0\b)|"
        r"(?:exit code|ExitCode|return code|return status)[ :=]+[1-9][0-9]*|"
        r"(?:exited|exiting|returned|returning)(?: with)? (?:code|status)[ :=]+"
        r"[1-9][0-9]*|segmentation fault|segfault|SIGSEGV|signal 11|"
        r"core dumped|assertion failed|"
        r"fatal(?: error)?(?:\s|:)|(?:^|\n).*?Error:|"
        r"\b(?:zero|0)\s+(?:PSOs?|stable\s+keys?|outputs?|artifacts?|caches?)\s+"
        r"(?:saved|written|created|found|matched)\b|"
        r"\bmissing\s+(?:PSOs?|stable\s+keys?|outputs?|artifacts?|caches?|packages?)\b|"
        r"\b(?:PSOs?|stable\s+keys?|outputs?|artifacts?|caches?|packages?)\s+"
        r"(?:(?:was|were)\s+)?not\s+(?:saved|written|created|found)\b"
    )
    if re.search(failure, text, flags=re.IGNORECASE):
        _fail("STAGE_LOG_FAILURE", f"{stage} log contains a failure signature")
    if stage in {"seed_cook", "final_cook"}:
        uat_contradiction = (
            r"\bNo\s+(?:PSOs?|stable\s+keys?|outputs?|artifacts?|caches?|packages?)"
            r"\s+(?:(?:was|were)\s+)?"
            r"(?:saved|written|created|found|matched)\b"
        )
        if re.search(uat_contradiction, text, flags=re.IGNORECASE):
            _fail(
                "STAGE_LOG_FAILURE",
                f"{stage} UAT log contains a contradictory zero-output summary",
            )
        terminal_success = (
            r"(?m)^BUILD SUCCESSFUL[ \t]*\r?\n"
            r"AutomationTool exiting with ExitCode=0 \(Success\)"
            r"[ \t]*(?:\r?\n)?\Z"
        )
        if re.search(terminal_success, text) is None:
            _fail("STAGE_LOG_SUCCESS_MISSING", f"{stage} UAT success is absent")
        return
    if stage == "human_capture":
        capture_rejected = (
            r"\breject(?:ed|ing|ion|ions|s)?\b|\bdiscard(?:ed|ing)?\b|"
            r"\bnot[ _-]?saved\b|\bfailed to save\b|\bsave failed\b|"
            r"\bSaved\s+0+\s+PSOs\b|\bNo\s+PSOs?\s+(?:were\s+)?saved\b|"
            r"\bzero\s+PSOs?\b|\bmissing\s+PSOs?\b|"
            r"\bPSOs?\s+(?:were\s+)?not\s+written\b|"
            r"\bNo\s+PSOs?\s+(?:were\s+)?written\b"
        )
        if (
            re.search(capture_rejected, text, flags=re.IGNORECASE)
            or re.search(r"(?<![A-Za-z])Saved\s+[1-9]\d*\s+PSOs\b", text) is None
            or re.search(r"LogExit: Exiting\.\s*\Z", text) is None
        ):
            _fail("CAPTURE_LOG_REJECTED", "capture completion is absent or rejected")
        return
    forbidden = (
        r"did not match anything|No shk found|all empty|Nothing to do|"
        r"No PSOs were created|No stable keys found|Could not load|"
        r"failed to load|error loading|"
        r"Bad PSO found discarding|obsolete|"
        r"\bzero\s+(?:stable\s+keys|PSOs?)\b|"
        r"\bmissing\s+(?:stable\s+keys|PSOs?)\b|"
        r"\b(?:stable\s+keys|PSOs?|output|cache)\s+(?:were\s+)?not\s+written\b|"
        r"\bNo\s+(?:stable\s+keys|PSOs?|output|cache)\s+"
        r"(?:were\s+)?written\b|"
        r"\breject(?:ed|ing|ion|ions|s)?\b"
    )
    if re.search(forbidden, text, flags=re.IGNORECASE):
        _fail("EXPAND_LOG_REJECTED", "expand log contains rejected or empty input")
    recorded_glob = (
        inputs.config.attempt_root
        / "pso-capture/user/Saved/CollectedPSOs/*.rec.upipelinecache"
    )
    stable_glob = (
        inputs.config.attempt_root
        / "seed-cook/cooked/Linux/VistaPlayableHome/Metadata/PipelineCaches/*.shk"
    )

    def input_counts(path: Path) -> list[int]:
        return [
            int(value)
            for value in re.findall(
                rf"^.*Expanding matched\s+([0-9]+) files: "
                rf"{re.escape(str(path))}\s*$",
                text,
                flags=re.MULTILINE,
            )
        ]

    recorded_counts = input_counts(recorded_glob)
    stable_counts = input_counts(stable_glob)
    stable_match = re.search(
        r"Loaded\s+([0-9]+) unique shader info lines total\.", text
    )
    pso_match = re.search(r"Loaded\s+([0-9]+) PSOs total\b", text)
    output = inputs.config.attempt_root / "expand" / STABLE_CACHE_NAME
    wrote_match = re.search(
        rf"(?m)^.*?Wrote\s+([0-9]+) binary PSOs .*? to "
        rf"{re.escape(str(output))}[ \t]*(?:\r?\n)?\Z",
        text,
    )
    if (
        len(recorded_counts) != 1
        or recorded_counts[0] <= 0
        or len(stable_counts) != 1
        or stable_counts[0] <= 0
        or stable_match is None
        or int(stable_match.group(1)) <= 0
        or pso_match is None
        or int(pso_match.group(1)) <= 0
        or wrote_match is None
        or int(wrote_match.group(1)) <= 0
    ):
        _fail(
            "STAGE_LOG_SUCCESS_MISSING",
            "expand requires nonzero matches, stable keys, PSOs, and exact output",
        )


def _validate_artifacts(
    payload: Any,
    inputs,
    stage: str,
    seed_projection: package_lane.ProjectionManifestBinding | None = None,
):
    attempt = inputs.config.attempt_root
    value = _exact(payload, ARTIFACT_KEYS[stage], label=f"{stage} artifacts")
    digests = []
    if stage == "seed_cook":
        if seed_projection is None:
            _fail("PROJECTION_EDGE_INVALID", "seed projection binding is absent")
        projection = package_lane._validate_file_record(
            value.get("source_projection_manifest"),
            attempt_root=attempt,
            expected_relative=package_lane.SEED_PROJECTION_MANIFEST_RELATIVE,
            label="seed source projection manifest",
        )
        if projection != seed_projection.receipt:
            _fail("PROJECTION_EDGE_INVALID", "seed projection receipt edge differs")
        digests.append(projection.sha256)
        digests.append(
            _archive(
                value.get("archive"),
                attempt,
                Path("seed-cook/archive"),
                label="seed archive",
            )
        )
        launcher = package_lane._validate_file_record(
            value.get("launcher"),
            attempt_root=attempt,
            expected_relative=Path("seed-cook/archive/Linux/VistaPlayableHome.sh"),
            label="seed launcher",
            executable=True,
        )
        digests.append(launcher.sha256)
        descriptor = package_lane._validate_file_record(
            value.get("project_descriptor"),
            attempt_root=attempt,
            expected_relative=package_lane.SEED_PROJECT_RELATIVE
            / package_lane.PROJECT_NAME,
            label="seed project descriptor",
        )
        if package_lane._read_after_seal(
            descriptor,
            label="seed project descriptor",
            maximum=package_lane.MAX_JSON_BYTES,
        ) != package_lane.canonical_json(package_lane.package_project_descriptor()):
            _fail("PROJECT_DESCRIPTOR_INVALID", "seed descriptor bytes differ")
        digests.append(descriptor.sha256)
        files = _enumerate_files(
            attempt,
            Path("seed-cook/cooked/Linux/VistaPlayableHome/Metadata/PipelineCaches"),
            suffix=".shk",
            recursive=False,
            label="stable keys",
        )
        digests.extend(
            _record_list(
                value.get("stable_keys"), files, attempt=attempt, label="stable keys"
            )
        )
    elif stage == "human_capture":
        if seed_projection is None:
            _fail("PROJECTION_EDGE_INVALID", "capture seed projection is absent")
        projection = package_lane._validate_file_record(
            value.get("seed_projection_manifest"),
            attempt_root=attempt,
            expected_relative=package_lane.SEED_PROJECTION_MANIFEST_RELATIVE,
            label="capture seed projection manifest",
        )
        if projection != seed_projection.receipt:
            _fail(
                "PROJECTION_EDGE_INVALID",
                "capture seed projection receipt edge differs",
            )
        digests.append(projection.sha256)
        files = _enumerate_files(
            attempt,
            Path("pso-capture/user/Saved/CollectedPSOs"),
            suffix=".rec.upipelinecache",
            recursive=False,
            label="recorded PSOs",
        )
        digests.extend(
            _record_list(
                value.get("recorded_psos"),
                files,
                attempt=attempt,
                label="recorded PSOs",
            )
        )
        ledger = package_lane._validate_file_record(
            value.get("coverage_ledger"),
            attempt_root=attempt,
            expected_relative=Path("pso-capture/human-coverage-ledger.json"),
            label="coverage ledger",
        )
        _coverage(ledger)
        digests.append(ledger.sha256)
    elif stage == "expand":
        stable = package_lane._validate_file_record(
            value.get("stable_cache"),
            attempt_root=attempt,
            expected_relative=Path("expand") / STABLE_CACHE_NAME,
            label="expanded stable cache",
        )
        digests.append(stable.sha256)
    elif stage == "final_cook":
        digests.append(
            _archive(
                value.get("archive"),
                attempt,
                Path("final-cook/archive"),
                label="final archive",
            )
        )
        fixed = {
            "launcher": (Path("final-cook/archive/Linux/VistaPlayableHome.sh"), True),
            "executable": (
                Path(
                    "final-cook/archive/Linux/VistaPlayableHome/Binaries/"
                    "Linux/VistaPlayableHome"
                ),
                True,
            ),
            "pak": (
                Path(
                    "final-cook/archive/Linux/VistaPlayableHome/Content/Paks/"
                    "VistaPlayableHome-Linux.pak"
                ),
                False,
            ),
        }
        for key, (relative, executable) in fixed.items():
            seal = package_lane._validate_file_record(
                value.get(key),
                attempt_root=attempt,
                expected_relative=relative,
                label=f"final {key}",
                executable=executable,
            )
            digests.append(seal.sha256)
        descriptor = package_lane._validate_file_record(
            value.get("project_descriptor"),
            attempt_root=attempt,
            expected_relative=package_lane.MATERIALIZED_DESCRIPTOR_RELATIVE,
            label="final project descriptor",
        )
        if package_lane._read_after_seal(
            descriptor,
            label="final project descriptor",
            maximum=package_lane.MAX_JSON_BYTES,
        ) != package_lane.canonical_json(package_lane.package_project_descriptor()):
            _fail("PROJECT_DESCRIPTOR_INVALID", "final descriptor bytes differ")
        digests.append(descriptor.sha256)
        stable_input = package_lane._validate_file_record(
            value.get("stable_cache_input"),
            attempt_root=attempt,
            expected_relative=(
                package_lane.FINAL_PROJECT_RELATIVE
                / "Build/Linux/PipelineCaches"
                / STABLE_CACHE_NAME
            ),
            label="final stable cache input",
        )
        digests.append(stable_input.sha256)
        files = _enumerate_files(
            attempt,
            BAKED_CACHE_RELATIVE.parent,
            suffix=".stable.upipelinecache",
            recursive=False,
            label="baked pipeline caches",
        )
        if len(files) != 1 or files[0].path != attempt / BAKED_CACHE_RELATIVE:
            _fail(
                "BAKED_CACHE_NAME_INVALID",
                "final cook must contain exactly the canonical baked cache basename",
            )
        digests.extend(
            _record_list(
                value.get("baked_pipeline_caches"),
                files,
                attempt=attempt,
                label="baked pipeline caches",
            )
        )
    return tuple(digests)


def load_stage_receipt(inputs, stage: str, loaded: Mapping[str, StageReceiptBinding]):
    if stage not in STAGE_IDS:
        _fail("STAGE_INVALID", "stage is outside the closed vocabulary")
    seed_projection = None
    if stage in {"seed_cook", "human_capture"}:
        try:
            seed_projection = package_lane.load_source_projection_manifest(
                inputs.config.attempt_root,
                inputs.source,
                stage="seed_cook",
            )
        except package_lane.HumanVisualPackageError as exc:
            raise HumanVisualPsoError(
                "SEED_PROJECTION_INVALID",
                f"{stage} refused the sealed R3 seed projection",
            ) from exc
    payload, receipt = _load_canonical_receipt(inputs, stage)
    value = _exact(payload, RECEIPT_KEYS, label=f"{stage} receipt")
    if (
        value.get("schema_version") != STAGE_SCHEMA[stage]
        or value.get("status") != STAGE_STATUS[stage]
        or value.get("stage") != stage
        or value.get("attempt_root") != str(inputs.config.attempt_root)
        or value.get("source") != source_record(inputs)
        or value.get("legal_scope") != package_lane.HUMAN_ONLY_LEGAL_BOUNDARY
        or value.get("claims") != package_lane.CLAIMS
        or value.get("content_digest") != content_digest(value)
    ):
        _fail("RECEIPT_STATE_INVALID", f"{stage} receipt state differs")
    if value.get("parents") != expected_parents(inputs, stage, loaded):
        _fail("RECEIPT_EDGE_INVALID", f"{stage} parents differ")
    _validate_toolchain(value.get("toolchain"), inputs)
    log = _validate_command(value.get("command"), inputs, stage)
    _require_stage_log_semantics(stage, log, inputs)
    artifacts = _validate_artifacts(
        value.get("artifacts"), inputs, stage, seed_projection
    )
    if stage == "final_cook":
        expanded = loaded.get("expand")
        final_artifacts = value.get("artifacts")
        stable_input_sha = (
            final_artifacts.get("stable_cache_input", {}).get("sha256")
            if isinstance(final_artifacts, dict)
            else None
        )
        if (
            expanded is None
            or len(expanded.artifact_sha256s) != 1
            or stable_input_sha != expanded.artifact_sha256s[0]
        ):
            _fail("RECEIPT_EDGE_INVALID", "final stable cache input differs")
    return StageReceiptBinding(stage, receipt, value, log, artifacts)


def load_receipt_chain(inputs: package_lane.PackagePlanInputs) -> ReceiptChainBinding:
    loaded = {}
    for stage in STAGE_IDS:
        loaded[stage] = load_stage_receipt(inputs, stage, loaded)
    return ReceiptChainBinding(
        CHAIN_SCHEMA,
        inputs.config.attempt_root,
        loaded["seed_cook"],
        loaded["human_capture"],
        loaded["expand"],
        loaded["final_cook"],
    )


def receipt_dag(inputs) -> dict[str, Any]:
    return {
        "schema_version": CHAIN_SCHEMA,
        "source": {"id": "sealed_r3_source", **source_record(inputs)},
        "nodes": [
            {
                "id": stage,
                "schema_version": STAGE_SCHEMA[stage],
                "terminal_status": STAGE_STATUS[stage],
                "receipt": str(
                    inputs.config.attempt_root / STAGE_RECEIPT_RELATIVE[stage]
                ),
                "sidecar": str(
                    inputs.config.attempt_root / _sidecar(STAGE_RECEIPT_RELATIVE[stage])
                ),
                "closed_fields": sorted(RECEIPT_KEYS),
                "depends_on": list(STAGE_PARENT_IDS[stage]),
                "exact_command_argv": expected_command(inputs, stage),
                "exact_command_argv_sha256": _command_sha256(
                    expected_command(inputs, stage)
                ),
                "fixed_log": str(
                    inputs.config.attempt_root / STAGE_LOG_RELATIVE[stage]
                ),
                "artifact_fields": sorted(ARTIFACT_KEYS[stage]),
            }
            for stage in STAGE_IDS
        ],
        "terminal_order": list(STAGE_IDS),
        "promotion_requires_every_node": True,
    }


def acceptance_gates() -> dict[str, Any]:
    return {
        "legal": {
            "exact_human_only_boundary": dict(package_lane.HUMAN_ONLY_LEGAL_BOUNDARY),
            "agent_adapter_absent": True,
            "ai_vlm_pixel_review_absent": True,
            "vista_dataset_or_database_write_absent": True,
        },
        "package": {
            "exact_enabled_plugins": list(package_lane.ENABLED_PLUGIN_ALLOWLIST),
            "disable_engine_plugins_by_default": True,
            "resolved_plugin_closure_required": True,
            "unknown_plugins_refused": True,
            "linux_development": True,
            "archive_rehashed_before_and_after_smoke": True,
        },
        "pso": {
            "stable_keys_nonempty": True,
            "recorded_psos_nonempty": True,
            "expanded_spc_nonempty": True,
            "final_stable_upipelinecache_nonempty": True,
            "all_receipt_edges_sha256_bound": True,
            "no_new_pso_hitches_after_warmup": True,
        },
        "runtime": {
            "display": DISPLAY,
            "gpu": GPU,
            "width": WIDTH,
            "height": HEIGHT,
            "target_fps": TARGET_FPS,
            "screen_percentage": SCREEN_PERCENTAGE,
            "median_fps_minimum": 55,
            "one_percent_low_fps_minimum": 30,
            "frame_time_p95_ms_maximum": 25,
            "stall_over_one_second_count_maximum": 0,
        },
        "human_acceptance": {
            "visual_acceptance_required": True,
            "interaction_acceptance_required": True,
            "claims_remain_false_until_signed": dict(package_lane.CLAIMS),
        },
    }


def build_plan(inputs) -> dict[str, Any]:
    package_plan = package_lane.build_package_plan(inputs)
    return {
        "schema_version": PLAN_SCHEMA,
        "status": "dry_run_validated",
        "execution": "not_authorized_plan_only",
        "source_package_plan_sha256": hashlib.sha256(
            canonical_json(package_plan)
        ).hexdigest(),
        "source_package_plan": package_plan,
        "receipt_dag": receipt_dag(inputs),
        "acceptance_gates": acceptance_gates(),
        "legal_scope": dict(package_lane.HUMAN_ONLY_LEGAL_BOUNDARY),
        "claims": dict(package_lane.CLAIMS),
        "security": {
            "default_zero_write": True,
            "default_zero_subprocess": True,
            "ue_uat_gpu_executed": False,
            "pixels_inspected": False,
            "external_attempt_written": False,
            "network_wrapper_rehashed": True,
            "network_wrapper": _tool_record(inputs.network_wrapper),
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--combined-receipt", required=True, type=Path)
    result.add_argument(
        "--combined-receipt-sha256", default=package_lane.PINNED_SOURCE_RECEIPT_SHA256
    )
    result.add_argument("--run-uat", required=True, type=Path)
    result.add_argument("--run-uat-sha256", default=package_lane.PINNED_RUN_UAT_SHA256)
    result.add_argument("--editor-cmd", required=True, type=Path)
    result.add_argument(
        "--editor-cmd-sha256", default=package_lane.PINNED_EDITOR_CMD_SHA256
    )
    result.add_argument("--attempt-root", required=True, type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        inputs = package_lane.validate_plan_inputs(
            package_lane.PackagePlanConfig(
                args.combined_receipt,
                args.combined_receipt_sha256,
                args.run_uat,
                args.run_uat_sha256,
                args.editor_cmd,
                args.editor_cmd_sha256,
                args.attempt_root,
            )
        )
        print(canonical_json(build_plan(inputs)).decode(), end="")
        return 0
    except (package_lane.HumanVisualPackageError, HumanVisualPsoError) as exc:
        print(f"human visual PSO plan refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
