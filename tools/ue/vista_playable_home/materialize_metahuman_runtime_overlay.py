#!/usr/bin/env python3
"""Overlay one assembled Vivian candidate onto the exact YCB R7 project.

The default operation is a read-only dry run. ``--apply`` copies the pinned
YCB R7 project and one verified, successfully authored Vivian payload into a
fresh private append-only attempt. Neither source is changed and no Unreal,
GPU, network, authentication, packaging, or visual-review process is started.

The resulting project is only a runtime *candidate*. Its receipt deliberately
keeps entitlement, package, runtime, player-eye, interaction, photoreal-human,
and visual-acceptance claims false. Epic binary payloads remain external to Git.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from tools.ue.vista_playable_home import materialize_hybrid_camera_overlay as tree_io
from tools.ue.vista_playable_home import materialize_metahuman_provider as authoring


PLAN_SCHEMA = "simworld.vista.metahuman-runtime-overlay-plan/v1"
HOST_RECEIPT_SCHEMA = "simworld.vista.metahuman-runtime-overlay-host-receipt/v1"
DRY_RUN_STATUS = "validated_zero_write_metahuman_runtime_overlay_plan"
APPLY_PLAN_STATUS = "validated_apply_metahuman_runtime_overlay_plan_no_write"
SUCCESS_STATUS = "diagnostic_nonpromotable_vivian_payload_overlaid"
FAILURE_STATUS = "diagnostic_nonpromotable_vivian_overlay_quarantined"

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
RUN_PARENT = pathlib.Path("/data/sysx/vista-world/runs/vista-action-world-r1")
YCB_R7_ROOT = RUN_PARENT / "ycb-hybrid-camera-r7-20260828"
YCB_R7_PROJECT_ROOT = YCB_R7_ROOT / "project"
YCB_R7_HOST_RECEIPT = YCB_R7_ROOT / "ycb-scene-host-receipt.json"
YCB_R7_HOST_RECEIPT_SHA256 = (
    "1ac0e2092640202026e14e51f433b823abfdbf90f633dece00ef5fc82fff7c0b"
)
YCB_R7_HOST_STATUS = "ycb_visual_only_scene_composed_saved_reloaded"
YCB_R7_PROJECT_PIN = tree_io.TreePin(
    sha256="1f77402db57f7c671254ed8e9e340855039e74387b978a71bfca1c7bcc824f96",
    file_count=1007,
    directory_count=347,
    total_bytes=2_647_098_992,
)

META_CONTENT_PREFIX = pathlib.PurePosixPath("Content/VISTA/Characters/MetaHumans")
META_CONTENT_RELATIVE = pathlib.PurePosixPath(
    "project/Content/VISTA/Characters/MetaHumans"
)
PROJECT_RELATIVE = pathlib.PurePosixPath("project")
AUTHORING_RESULT_NAME = authoring.RESULT_NAME
AUTHORING_REQUEST_NAME = authoring.REQUEST_NAME
PROVIDER_SPEC_NAME = authoring.PROVIDER_COPY_NAME
AUTHOR_SCRIPT_NAME = authoring.AUTHOR_SCRIPT_NAME
PROJECT_NAME = authoring.PROJECT_NAME
EXPECTED_BLUEPRINT = authoring.EXPECTED_BLUEPRINT
EXPECTED_BLUEPRINT_CLASS = authoring.EXPECTED_BLUEPRINT_CLASS
EXPECTED_BLUEPRINT_PACKAGE = EXPECTED_BLUEPRINT.rsplit(".", 1)[0]
ASSEMBLY_ROOT = authoring.ASSEMBLY_ROOT
EXPECTED_AUTHORING_PROJECT_RAW = authoring.canonical_json(
    authoring._project_descriptor(), newline=True
)
EXPECTED_AUTHORING_PROJECT_SHA256 = hashlib.sha256(
    EXPECTED_AUTHORING_PROJECT_RAW
).hexdigest()

OUTPUT_ATTEMPT_RE = re.compile(r"^ycb-r7-vivian-[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
AUTHORING_ATTEMPT_RE = re.compile(
    r"^metahuman-vivian-r[0-9]+-[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UNREAL_PACKAGE_SUFFIXES = frozenset({".uasset", ".uexp", ".ubulk", ".uptnl"})
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_METAHUMAN_BYTES = 64 * 1024 * 1024 * 1024
MAX_OUTPUT_BYTES = YCB_R7_PROJECT_PIN.total_bytes + MAX_METAHUMAN_BYTES
METAHUMAN_EXCLUDED_DATA_USES = (
    "vista_dataset_inclusion",
    "ai_training",
    "ai_testing",
    "ai_evaluation",
    "ai_review",
    "vlm_training",
    "vlm_testing",
    "vlm_evaluation",
    "vlm_review",
    "database_creation_or_population",
)
HOST_RECEIPT_NAME = "metahuman-runtime-overlay-host-receipt.json"
HOST_RECEIPT_PROVISIONAL_NAME = "metahuman-runtime-overlay-host-receipt.provisional"
HOST_FAILURE_NAME = "metahuman-runtime-overlay-host-failure.json"
PARENT_FAILURE_SUFFIX = ".metahuman-runtime-overlay-host-failure.json"

SUCCESS_RESULT_KEYS = frozenset(
    {
        "schema_version",
        "provider_id",
        "provider_spec_content_digest",
        "accepted",
        "status",
        "authoring_succeeded",
        "assembly_completed",
        "assembled_component_digests_complete",
        "entitlement_receipt_complete",
        "engine_version",
        "provider_spec_sha256",
        "plugin_descriptor_sha256",
        "preset_sha256",
        "pipeline_sha256",
        "source_object_path",
        "assembly_pipeline",
        "assembly_quality",
        "pipeline_object_path",
        "rig_type",
        "has_high_resolution_textures",
        "expected_blueprint",
        "expected_blueprint_class",
        "asset_inventory",
        "account_tokens_recorded",
        "package_validation_complete",
        "runtime_visual_acceptance_complete",
        "content_digest",
    }
)


OverlayError = tree_io.OverlayError


@dataclasses.dataclass(frozen=True)
class OverlayConfig:
    repository_root: pathlib.Path
    run_parent: pathlib.Path
    ycb_root: pathlib.Path
    ycb_project_root: pathlib.Path
    ycb_host_receipt: pathlib.Path
    ycb_host_receipt_sha256: str
    ycb_host_status: str
    ycb_project_pin: tree_io.TreePin


@dataclasses.dataclass(frozen=True)
class SealedFile:
    path: pathlib.Path
    raw: bytes
    sha256: str
    size_bytes: int
    identity: tuple[int, int, int, int, int, int]


@dataclasses.dataclass(frozen=True)
class TreeEntryIdentity:
    relative_path: str
    kind: str
    device: int
    inode: int
    size_bytes: int
    mtime_ns: int
    ctime_ns: int
    mode: int
    link_count: int


@dataclasses.dataclass(frozen=True)
class TreeIdentitySeal:
    root: pathlib.Path
    entries: tuple[TreeEntryIdentity, ...]


@dataclasses.dataclass(frozen=True)
class AuthoringCandidate:
    attempt_root: pathlib.Path
    project_root: pathlib.Path
    content_root: pathlib.Path
    result: Mapping[str, Any]
    result_seal: SealedFile
    request: Mapping[str, Any]
    request_seal: SealedFile
    provider_seal: SealedFile
    script_seal: SealedFile
    project_seal: SealedFile
    content: tree_io.TreeSnapshot
    content_identity: TreeIdentitySeal


@dataclasses.dataclass(frozen=True)
class PreparedOverlay:
    config: OverlayConfig
    output_root: pathlib.Path
    apply_requested: bool
    epic_license_acknowledged: bool
    external_binary_policy_acknowledged: bool
    visual_demo_only_acknowledged: bool
    ycb_receipt: Mapping[str, Any]
    ycb_receipt_seal: SealedFile
    ycb_project: tree_io.TreeSnapshot
    ycb_project_identity: TreeIdentitySeal
    candidate: AuthoringCandidate
    output_projection: tree_io.Projection
    report: Mapping[str, Any]
    run_parent_identity: tuple[int, int]


def production_config() -> OverlayConfig:
    """Return the closed R7 configuration; the CLI cannot redirect it."""

    return OverlayConfig(
        repository_root=REPOSITORY_ROOT,
        run_parent=RUN_PARENT,
        ycb_root=YCB_R7_ROOT,
        ycb_project_root=YCB_R7_PROJECT_ROOT,
        ycb_host_receipt=YCB_R7_HOST_RECEIPT,
        ycb_host_receipt_sha256=YCB_R7_HOST_RECEIPT_SHA256,
        ycb_host_status=YCB_R7_HOST_STATUS,
        ycb_project_pin=YCB_R7_PROJECT_PIN,
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OverlayError(message)


def _canonical_json(value: Any) -> bytes:
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
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise OverlayError("value is not finite canonical UTF-8 JSON") from exc


def _content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_json(body)).hexdigest()


def _seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_digest"] = _content_digest(result)
    return result


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IMODE(metadata.st_mode),
    )


def _read_sealed_file(
    path: pathlib.Path,
    label: str,
    *,
    max_bytes: int = MAX_JSON_BYTES,
    require_private: bool = True,
    allowed_link_counts: frozenset[int] = frozenset({1}),
) -> SealedFile:
    candidate = tree_io._absolute_normalized(path, label)
    tree_io._reject_symlink_components(candidate, label)
    try:
        before_path = os.lstat(candidate)
    except OSError as exc:
        raise OverlayError(f"{label} is missing") from exc
    _require(stat.S_ISREG(before_path.st_mode), f"{label} is not regular")
    _require(before_path.st_size <= max_bytes, f"{label} exceeds size policy")
    if require_private:
        _require(
            before_path.st_uid == os.geteuid()
            and before_path.st_nlink in allowed_link_counts
            and stat.S_IMODE(before_path.st_mode) == PRIVATE_FILE_MODE,
            f"{label} metadata is not private or has an unexpected link count",
        )

    descriptor = -1
    try:
        descriptor = os.open(
            candidate,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        before = os.fstat(descriptor)
        _require(
            _identity(before) == _identity(before_path),
            f"{label} changed while opening",
        )
        raw = bytearray()
        digest = hashlib.sha256()
        while len(raw) <= max_bytes:
            block = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
            digest.update(block)
        after = os.fstat(descriptor)
        after_path = os.lstat(candidate)
        _require(len(raw) <= max_bytes, f"{label} exceeds size policy")
        _require(
            _identity(before) == _identity(after) == _identity(after_path)
            and len(raw) == before.st_size,
            f"{label} changed while reading",
        )
        return SealedFile(
            path=candidate,
            raw=bytes(raw),
            sha256=digest.hexdigest(),
            size_bytes=len(raw),
            identity=_identity(before),
        )
    except OverlayError:
        raise
    except OSError as exc:
        raise OverlayError(f"{label} cannot be read safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _strict_json(seal: SealedFile, label: str) -> dict[str, Any]:
    return tree_io._strict_json(seal.raw, label)


def _tree_pin(snapshot: tree_io.TreeSnapshot) -> tree_io.TreePin:
    return tree_io.TreePin(
        snapshot.normalized_sha256,
        len(snapshot.files),
        len(snapshot.directories),
        snapshot.total_bytes,
    )


def _projection_pin(projection: tree_io.Projection) -> tree_io.TreePin:
    return tree_io.TreePin(
        projection.sha256,
        len(projection.files),
        len(projection.directories),
        projection.total_bytes,
    )


def _seal_tree_identity(snapshot: tree_io.TreeSnapshot, label: str) -> TreeIdentitySeal:
    records = {record.relative_path: record for record in snapshot.files}
    entries: list[TreeEntryIdentity] = []
    for relative in snapshot.directories:
        path = snapshot.root if relative == "." else snapshot.root / relative
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise OverlayError(f"{label} directory identity is unavailable") from exc
        _require(
            stat.S_ISDIR(metadata.st_mode),
            f"{label} directory identity changed: {relative}",
        )
        entries.append(
            TreeEntryIdentity(
                relative_path=relative,
                kind="directory",
                device=metadata.st_dev,
                inode=metadata.st_ino,
                size_bytes=metadata.st_size,
                mtime_ns=metadata.st_mtime_ns,
                ctime_ns=metadata.st_ctime_ns,
                mode=stat.S_IMODE(metadata.st_mode),
                link_count=metadata.st_nlink,
            )
        )
    for relative, record in sorted(records.items()):
        try:
            metadata = os.lstat(record.source)
        except OSError as exc:
            raise OverlayError(f"{label} file identity is unavailable") from exc
        _require(
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_dev == record.device
            and metadata.st_ino == record.inode
            and metadata.st_size == record.size_bytes
            and metadata.st_mtime_ns == record.mtime_ns
            and stat.S_IMODE(metadata.st_mode) == record.source_mode,
            f"{label} file identity changed: {relative}",
        )
        entries.append(
            TreeEntryIdentity(
                relative_path=relative,
                kind="file",
                device=metadata.st_dev,
                inode=metadata.st_ino,
                size_bytes=metadata.st_size,
                mtime_ns=metadata.st_mtime_ns,
                ctime_ns=metadata.st_ctime_ns,
                mode=stat.S_IMODE(metadata.st_mode),
                link_count=metadata.st_nlink,
            )
        )
    return TreeIdentitySeal(
        root=snapshot.root,
        entries=tuple(
            sorted(entries, key=lambda item: (item.relative_path, item.kind))
        ),
    )


def _validate_ycb_receipt(receipt: Mapping[str, Any], config: OverlayConfig) -> None:
    projection = receipt.get("post_project_projection")
    claims = receipt.get("claims")
    _require(
        receipt.get("schema_version")
        == "simworld.vista.playable-home-ycb-scene-host-receipt/v1"
        and receipt.get("status") == config.ycb_host_status
        and receipt.get("attempt_root") == str(config.ycb_root)
        and receipt.get("project_root") == str(config.ycb_project_root)
        and projection == dataclasses.asdict(config.ycb_project_pin),
        "YCB R7 receipt does not bind the exact source project",
    )
    _require(
        receipt.get("content_digest") == _content_digest(receipt),
        "YCB R7 receipt content digest differs",
    )
    _require(
        receipt.get("accepted_as_visual_evidence") is False
        and receipt.get("promotable") is False
        and receipt.get("diagnostic_only") is True,
        "YCB R7 receipt disposition differs",
    )
    _require(
        type(claims) is dict
        and claims.get("ycb_visuals_composed") is True
        and claims.get("gta_level") is False
        and claims.get("real_human_present") is False
        and claims.get("player_eye_reviewed") is False
        and claims.get("visual_acceptance") is False,
        "YCB R7 receipt contains unsupported claims",
    )


def _validate_authoring_result(result: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    _require(
        set(result) == SUCCESS_RESULT_KEYS,
        "MetaHuman authoring result is not the exact success shape",
    )
    _require(
        result.get("content_digest") == _content_digest(result),
        "MetaHuman authoring result content digest differs",
    )
    authoring._scan_prohibited_credentials(result)
    fixed = {
        "schema_version": authoring.RESULT_SCHEMA,
        "provider_id": authoring.PROVIDER_ID,
        "provider_spec_content_digest": authoring.PINNED_PROVIDER_CONTENT_DIGEST,
        "accepted": False,
        "status": "assembled_candidate_requires_package_validation",
        "authoring_succeeded": True,
        "assembly_completed": True,
        "assembled_component_digests_complete": False,
        "entitlement_receipt_complete": False,
        "engine_version": authoring.PINNED_ENGINE_VERSION,
        "provider_spec_sha256": authoring.PINNED_PROVIDER_SHA256,
        "plugin_descriptor_sha256": authoring.PINNED_PLUGIN_DESCRIPTOR_SHA256,
        "preset_sha256": authoring.PINNED_PRESET_SHA256,
        "pipeline_sha256": authoring.PINNED_PIPELINE_SHA256,
        "source_object_path": authoring.SOURCE_OBJECT_PATH,
        "assembly_pipeline": "optimized",
        "assembly_quality": "high",
        "pipeline_object_path": authoring.PIPELINE_OBJECT_PATH,
        "rig_type": "joints_and_blend_shapes",
        "has_high_resolution_textures": True,
        "expected_blueprint": EXPECTED_BLUEPRINT,
        "expected_blueprint_class": EXPECTED_BLUEPRINT_CLASS,
        "account_tokens_recorded": False,
        "package_validation_complete": False,
        "runtime_visual_acceptance_complete": False,
    }
    _require(
        all(result.get(key) == expected for key, expected in fixed.items()),
        "MetaHuman authoring result identity or gate differs",
    )
    inventory = result.get("asset_inventory")
    _require(
        type(inventory) is list and 8 <= len(inventory) <= tree_io.MAX_FILES,
        "MetaHuman asset inventory is incomplete or exceeds policy",
    )
    packages: set[str] = set()
    objects: set[str] = set()
    validated: list[dict[str, Any]] = []
    for item in inventory:
        _require(
            type(item) is dict
            and set(item) == {"class_path", "object_path", "package_name"}
            and all(type(item[key]) is str for key in item),
            "MetaHuman asset inventory entry is malformed",
        )
        package = item["package_name"]
        object_path = item["object_path"]
        class_path = item["class_path"]
        _require(
            package.startswith(ASSEMBLY_ROOT + "/")
            and object_path.startswith(package + ".")
            and class_path.startswith("/Script/"),
            "MetaHuman asset inventory entry escaped the fixed assembly root",
        )
        _require(
            package not in packages and object_path not in objects,
            "MetaHuman asset inventory contains duplicates",
        )
        packages.add(package)
        objects.add(object_path)
        validated.append(dict(item))
    _require(
        EXPECTED_BLUEPRINT_PACKAGE in packages and EXPECTED_BLUEPRINT in objects,
        "MetaHuman asset inventory omits the expected Vivian Blueprint",
    )
    return tuple(validated)


def _validate_provider_spec(
    provider: Mapping[str, Any], provider_seal: SealedFile
) -> None:
    _require(
        provider_seal.sha256 == authoring.PINNED_PROVIDER_SHA256
        and provider_seal.size_bytes == authoring.PINNED_PROVIDER_SIZE_BYTES
        and provider.get("provider_id") == authoring.PROVIDER_ID
        and provider.get("content_digest") == authoring.PINNED_PROVIDER_CONTENT_DIGEST,
        "MetaHuman provider spec identity differs",
    )
    try:
        authoring.provider_contract.validate_provider(provider)
    except authoring.provider_contract.CharacterProviderContractError as exc:
        raise OverlayError(
            "MetaHuman provider spec contract validation failed"
        ) from exc


def _validate_authoring_project(
    project: Mapping[str, Any], project_seal: SealedFile
) -> None:
    _require(
        project_seal.raw == EXPECTED_AUTHORING_PROJECT_RAW
        and project_seal.sha256 == EXPECTED_AUTHORING_PROJECT_SHA256
        and project == authoring._project_descriptor(),
        "MetaHuman project descriptor bytes or semantics differ",
    )


def _validate_authoring_request(
    request: Mapping[str, Any],
    *,
    attempt_root: pathlib.Path,
    provider: SealedFile,
    script: SealedFile,
    project: SealedFile,
) -> None:
    expected_keys = {
        "schema_version",
        "provider_id",
        "provider_spec_path",
        "provider_spec_sha256",
        "provider_spec_content_digest",
        "attempt_root",
        "project_file",
        "project_sha256",
        "script_sha256",
        "engine_version",
        "plugin_descriptor_sha256",
        "preset_sha256",
        "pipeline_sha256",
        "source_object_path",
        "assembly_root",
        "common_root",
        "expected_blueprint",
        "authorization",
        "policy",
        "content_digest",
    }
    _require(
        set(request) == expected_keys
        and request.get("content_digest") == _content_digest(request),
        "MetaHuman authoring request shape or digest differs",
    )
    fixed = {
        "schema_version": authoring.REQUEST_SCHEMA,
        "provider_id": authoring.PROVIDER_ID,
        "provider_spec_path": str(attempt_root / PROVIDER_SPEC_NAME),
        "provider_spec_sha256": authoring.PINNED_PROVIDER_SHA256,
        "provider_spec_content_digest": authoring.PINNED_PROVIDER_CONTENT_DIGEST,
        "attempt_root": str(attempt_root),
        "project_file": str(attempt_root / PROJECT_RELATIVE / PROJECT_NAME),
        "project_sha256": EXPECTED_AUTHORING_PROJECT_SHA256,
        "script_sha256": script.sha256,
        "engine_version": authoring.PINNED_ENGINE_VERSION,
        "plugin_descriptor_sha256": authoring.PINNED_PLUGIN_DESCRIPTOR_SHA256,
        "preset_sha256": authoring.PINNED_PRESET_SHA256,
        "pipeline_sha256": authoring.PINNED_PIPELINE_SHA256,
        "source_object_path": authoring.SOURCE_OBJECT_PATH,
        "assembly_root": ASSEMBLY_ROOT,
        "common_root": authoring.COMMON_ROOT,
        "expected_blueprint": EXPECTED_BLUEPRINT,
        "authorization": {
            "cloud_requests_authorized": True,
            "interactive_epic_sign_in_allowed": True,
            "store_account_tokens_in_receipt": False,
        },
        "policy": {
            "append_only_project": True,
            "binary_payload_in_git": False,
            "fail_closed_without_entitlement": True,
            "private_research_only": True,
            "replace_existing": False,
        },
    }
    _require(
        all(request.get(key) == expected for key, expected in fixed.items()),
        "MetaHuman authoring request identity differs",
    )
    _require(
        provider.sha256 == authoring.PINNED_PROVIDER_SHA256
        and provider.size_bytes == authoring.PINNED_PROVIDER_SIZE_BYTES
        and script.sha256 == authoring.PINNED_AUTHOR_SCRIPT_SHA256,
        "MetaHuman fixed authoring inputs differ",
    )
    _require(
        project.raw == EXPECTED_AUTHORING_PROJECT_RAW
        and project.sha256 == EXPECTED_AUTHORING_PROJECT_SHA256,
        "MetaHuman authoring request references a non-fixed project descriptor",
    )


def _package_relative_path(package: str) -> str:
    prefix = ASSEMBLY_ROOT + "/"
    _require(package.startswith(prefix), "MetaHuman package escaped assembly root")
    tail = package[len(prefix) :]
    pure = pathlib.PurePosixPath(tail)
    _require(
        bool(tail)
        and not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in pure.parts),
        "MetaHuman package has an unsafe path",
    )
    return pure.as_posix() + ".uasset"


def _validate_content_inventory(
    content: tree_io.TreeSnapshot,
    inventory: Sequence[Mapping[str, Any]],
) -> None:
    _require(
        content.total_bytes <= MAX_METAHUMAN_BYTES,
        "MetaHuman payload exceeds external binary policy",
    )
    file_paths = {record.relative_path for record in content.files}
    _require(
        all(
            pathlib.PurePosixPath(path).suffix in UNREAL_PACKAGE_SUFFIXES
            for path in file_paths
        ),
        "MetaHuman payload contains a non-package file",
    )
    required_uassets = {
        _package_relative_path(str(item["package_name"])) for item in inventory
    }
    observed_uassets = {
        path for path in file_paths if pathlib.PurePosixPath(path).suffix == ".uasset"
    }
    _require(
        observed_uassets == required_uassets,
        "MetaHuman inventory and payload package set differ",
    )

    for path in sorted(file_paths - observed_uassets):
        suffix = pathlib.PurePosixPath(path).suffix
        stem = path[: -len(suffix)]
        candidates = [stem + ".uasset"]
        if suffix in {".ubulk", ".uptnl"} and stem.endswith((".m", ".o")):
            candidates.append(stem[:-2] + ".uasset")
        owners = [
            candidate for candidate in candidates if candidate in observed_uassets
        ]
        _require(
            len(owners) == 1 and owners[0] in required_uassets,
            "MetaHuman payload contains an orphan or unlisted package sidecar",
        )
    blueprint_relative = _package_relative_path(EXPECTED_BLUEPRINT_PACKAGE)
    _require(
        blueprint_relative in file_paths,
        "MetaHuman payload omits the expected Vivian Blueprint package",
    )


def _validate_candidate(
    config: OverlayConfig, attempt_root: pathlib.Path
) -> AuthoringCandidate:
    attempt, attempt_metadata = tree_io._existing_directory(
        attempt_root, "MetaHuman authoring attempt"
    )
    _require(
        attempt.parent == config.run_parent
        and AUTHORING_ATTEMPT_RE.fullmatch(attempt.name) is not None,
        "MetaHuman authoring attempt is not a permitted direct run child",
    )
    _require(
        attempt_metadata.st_uid == os.geteuid()
        and stat.S_IMODE(attempt_metadata.st_mode) == PRIVATE_DIRECTORY_MODE,
        "MetaHuman authoring attempt root is not private",
    )
    project_root, project_metadata = tree_io._existing_directory(
        attempt / PROJECT_RELATIVE, "MetaHuman authoring project"
    )
    _require(
        project_root.parent == attempt
        and project_metadata.st_uid == os.geteuid()
        and stat.S_IMODE(project_metadata.st_mode) == PRIVATE_DIRECTORY_MODE,
        "MetaHuman authoring project is not the fixed private child",
    )
    content_root, _ = tree_io._existing_directory(
        attempt.joinpath(*META_CONTENT_RELATIVE.parts),
        "MetaHuman assembled content",
    )

    result_seal = _read_sealed_file(
        attempt / AUTHORING_RESULT_NAME, "MetaHuman authoring result"
    )
    request_seal = _read_sealed_file(
        attempt / AUTHORING_REQUEST_NAME, "MetaHuman authoring request"
    )
    provider_seal = _read_sealed_file(
        attempt / PROVIDER_SPEC_NAME, "MetaHuman provider spec"
    )
    script_seal = _read_sealed_file(
        attempt / AUTHOR_SCRIPT_NAME, "MetaHuman authoring script"
    )
    project_seal = _read_sealed_file(
        project_root / PROJECT_NAME, "MetaHuman project descriptor"
    )
    result = _strict_json(result_seal, "MetaHuman authoring result")
    request = _strict_json(request_seal, "MetaHuman authoring request")
    provider = _strict_json(provider_seal, "MetaHuman provider spec")
    project = _strict_json(project_seal, "MetaHuman project descriptor")
    _validate_provider_spec(provider, provider_seal)
    _validate_authoring_project(project, project_seal)
    inventory = _validate_authoring_result(result)
    _validate_authoring_request(
        request,
        attempt_root=attempt,
        provider=provider_seal,
        script=script_seal,
        project=project_seal,
    )
    content = tree_io.snapshot_tree(content_root, "MetaHuman assembled content")
    _validate_content_inventory(content, inventory)
    content_identity = _seal_tree_identity(content, "MetaHuman assembled content")
    return AuthoringCandidate(
        attempt_root=attempt,
        project_root=project_root,
        content_root=content_root,
        result=result,
        result_seal=result_seal,
        request=request,
        request_seal=request_seal,
        provider_seal=provider_seal,
        script_seal=script_seal,
        project_seal=project_seal,
        content=content,
        content_identity=content_identity,
    )


def _prefix_ancestors(prefix: pathlib.PurePosixPath) -> set[str]:
    result: set[str] = set()
    current = pathlib.PurePosixPath()
    for part in prefix.parts:
        current = current / part
        result.add(current.as_posix())
    return result


def _derive_output_projection(
    ycb_project: tree_io.TreeSnapshot,
    metahuman_content: tree_io.TreeSnapshot,
) -> tree_io.Projection:
    prefix = META_CONTENT_PREFIX.as_posix()
    _require(
        all(
            relative != prefix and not relative.startswith(prefix + "/")
            for relative in ycb_project.directories
        )
        and all(
            record.relative_path != prefix
            and not record.relative_path.startswith(prefix + "/")
            for record in ycb_project.files
        ),
        "YCB R7 already contains a MetaHuman payload conflict",
    )
    meta_directories = {
        prefix if relative == "." else prefix + "/" + relative
        for relative in metahuman_content.directories
    }
    meta_directories.update(_prefix_ancestors(META_CONTENT_PREFIX))
    meta_files = tuple(
        dataclasses.replace(record, relative_path=prefix + "/" + record.relative_path)
        for record in metahuman_content.files
    )
    directories = tuple(sorted(set(ycb_project.directories) | meta_directories))
    files = tuple(
        sorted(
            (*ycb_project.files, *meta_files), key=lambda record: record.relative_path
        )
    )
    tree_io._reject_case_collisions(directories, files, "Vivian overlay projection")
    total_bytes = sum(record.size_bytes for record in files)
    _require(
        len(files) <= tree_io.MAX_FILES and total_bytes <= MAX_OUTPUT_BYTES,
        "Vivian overlay output exceeds file or byte policy",
    )
    return tree_io.Projection(
        directories=directories,
        files=files,
        sha256=tree_io._normalized_tree_digest(directories, files),
        total_bytes=total_bytes,
    )


def _validate_paths(
    config: OverlayConfig,
    metahuman_attempt: pathlib.Path,
    output_root: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path, tuple[int, int]]:
    repository, _ = tree_io._existing_directory(
        config.repository_root, "repository root"
    )
    run_parent, parent_metadata = tree_io._existing_directory(
        config.run_parent, "run parent"
    )
    ycb_root, _ = tree_io._existing_directory(config.ycb_root, "YCB R7 root")
    ycb_project, _ = tree_io._existing_directory(
        config.ycb_project_root, "YCB R7 project"
    )
    _require(ycb_root.parent == run_parent, "YCB R7 root was redirected")
    _require(
        ycb_project == ycb_root / PROJECT_RELATIVE,
        "YCB R7 project path was redirected",
    )
    _require(
        config.ycb_host_receipt == ycb_root / "ycb-scene-host-receipt.json",
        "YCB R7 receipt path was redirected",
    )
    _require(
        not tree_io._path_is_within(run_parent, repository),
        "external run parent must stay outside Git",
    )

    candidate = tree_io._absolute_normalized(
        metahuman_attempt, "MetaHuman authoring attempt"
    )
    _require(
        candidate.parent == run_parent
        and AUTHORING_ATTEMPT_RE.fullmatch(candidate.name) is not None,
        "MetaHuman authoring attempt must be a permitted direct run child",
    )
    _require(
        not tree_io._path_is_within(candidate, repository),
        "MetaHuman payload must stay outside Git",
    )

    output = tree_io._absolute_normalized(output_root, "overlay output root")
    _require(
        output.parent == run_parent
        and OUTPUT_ATTEMPT_RE.fullmatch(output.name) is not None,
        "overlay output must be a permitted direct run child",
    )
    _require(
        output not in {candidate, ycb_root}
        and not tree_io._path_is_within(output, repository),
        "overlay output aliases an input or Git checkout",
    )
    tree_io._reject_symlink_components(
        output, "overlay output root", allow_missing_tail=True
    )
    _require(not os.path.lexists(output), "overlay output already exists")
    return candidate, output, (parent_metadata.st_dev, parent_metadata.st_ino)


def build_plan(
    config: OverlayConfig,
    metahuman_attempt: pathlib.Path,
    output_root: pathlib.Path,
    *,
    apply: bool = False,
    allow_epic_private_research_license: bool = False,
    allow_external_binaries_never_git: bool = False,
    ack_metahuman_visual_demo_only_not_ai_training_testing: bool = False,
) -> PreparedOverlay:
    """Validate all inputs and return a deterministic zero-write plan."""

    if apply:
        _require(
            allow_epic_private_research_license,
            "apply requires the Epic private-research license acknowledgement",
        )
        _require(
            allow_external_binaries_never_git,
            "apply requires the external-binaries-never-Git acknowledgement",
        )
        _require(
            ack_metahuman_visual_demo_only_not_ai_training_testing,
            "apply requires the MetaHuman visual-demo-only acknowledgement",
        )
    candidate_path, output, parent_identity = _validate_paths(
        config, metahuman_attempt, output_root
    )

    ycb_receipt_seal = _read_sealed_file(
        config.ycb_host_receipt,
        "YCB R7 host receipt",
        allowed_link_counts=frozenset({2}),
    )
    _require(
        ycb_receipt_seal.sha256 == config.ycb_host_receipt_sha256,
        "YCB R7 host receipt SHA-256 differs",
    )
    ycb_receipt = _strict_json(ycb_receipt_seal, "YCB R7 host receipt")
    _validate_ycb_receipt(ycb_receipt, config)
    ycb_project = tree_io.snapshot_tree(
        config.ycb_project_root, "YCB R7 project", require_private_modes=True
    )
    tree_io._assert_tree_pin(ycb_project, config.ycb_project_pin, "YCB R7 project")
    ycb_project_identity = _seal_tree_identity(ycb_project, "YCB R7 project")

    candidate = _validate_candidate(config, candidate_path)
    output_projection = _derive_output_projection(ycb_project, candidate.content)
    output_pin = _projection_pin(output_projection)
    claims = {
        "vivian_payload_overlaid": False,
        "assembled_candidate_source_verified": True,
        "entitlement_receipt_complete": False,
        "package_validation_complete": False,
        "runtime_executed": False,
        "runtime_provider_ready": False,
        "gta_level": False,
        "real_human_present": False,
        "photoreal_character_accepted": False,
        "player_eye_reviewed": False,
        "interaction_proven": False,
        "visual_acceptance": False,
    }
    report = _seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "status": APPLY_PLAN_STATUS if apply else DRY_RUN_STATUS,
            "mode": "apply_requested" if apply else "dry_run",
            "metahuman_attempt_root": str(candidate.attempt_root),
            "output_root": str(output),
            "will_write": apply,
            "will_execute_unreal": False,
            "will_use_gpu": False,
            "will_access_network": False,
            "inputs": {
                "ycb_r7": {
                    "attempt_root": str(config.ycb_root),
                    "host_receipt_sha256": config.ycb_host_receipt_sha256,
                    "host_status": config.ycb_host_status,
                    "project_projection": dataclasses.asdict(config.ycb_project_pin),
                },
                "metahuman_vivian": {
                    "attempt_root": str(candidate.attempt_root),
                    "provider_id": authoring.PROVIDER_ID,
                    "authoring_result_sha256": candidate.result_seal.sha256,
                    "authoring_request_sha256": candidate.request_seal.sha256,
                    "provider_spec_sha256": candidate.provider_seal.sha256,
                    "author_script_sha256": candidate.script_seal.sha256,
                    "project_descriptor_sha256": candidate.project_seal.sha256,
                    "content_projection": dataclasses.asdict(
                        _tree_pin(candidate.content)
                    ),
                },
            },
            "output": {
                "project_root": str(output / PROJECT_RELATIVE),
                "project_projection": dataclasses.asdict(output_pin),
                "added_subtree": META_CONTENT_PREFIX.as_posix(),
                "ycb_r7_source_mutation": False,
                "metahuman_source_mutation": False,
            },
            "acknowledgements": {
                "epic_private_noncommercial_research": (
                    allow_epic_private_research_license
                ),
                "external_binaries_never_git": (allow_external_binaries_never_git),
                "metahuman_visual_demo_only_not_ai_training_testing": (
                    ack_metahuman_visual_demo_only_not_ai_training_testing
                ),
            },
            "policy": {
                "append_only": True,
                "replace_existing": False,
                "epic_payload_external_only": True,
                "binary_payload_in_git": False,
                "subprocess_used": False,
                "promotable": False,
                "diagnostic_only": True,
                "metahuman_usage_scope": {
                    "human_operated_visual_demo_only": True,
                    "excluded_data_uses": list(METAHUMAN_EXCLUDED_DATA_USES),
                },
            },
            "claims": claims,
        }
    )
    return PreparedOverlay(
        config=config,
        output_root=output,
        apply_requested=apply,
        epic_license_acknowledged=allow_epic_private_research_license,
        external_binary_policy_acknowledged=allow_external_binaries_never_git,
        visual_demo_only_acknowledged=(
            ack_metahuman_visual_demo_only_not_ai_training_testing
        ),
        ycb_receipt=ycb_receipt,
        ycb_receipt_seal=ycb_receipt_seal,
        ycb_project=ycb_project,
        ycb_project_identity=ycb_project_identity,
        candidate=candidate,
        output_projection=output_projection,
        report=report,
        run_parent_identity=parent_identity,
    )


def _same_plan(left: PreparedOverlay, right: PreparedOverlay) -> bool:
    return (
        left.report == right.report
        and left.run_parent_identity == right.run_parent_identity
        and left.ycb_receipt_seal == right.ycb_receipt_seal
        and left.ycb_project == right.ycb_project
        and left.ycb_project_identity == right.ycb_project_identity
        and left.candidate.result_seal == right.candidate.result_seal
        and left.candidate.request_seal == right.candidate.request_seal
        and left.candidate.provider_seal == right.candidate.provider_seal
        and left.candidate.script_seal == right.candidate.script_seal
        and left.candidate.project_seal == right.candidate.project_seal
        and left.candidate.content == right.candidate.content
        and left.candidate.content_identity == right.candidate.content_identity
        and _projection_pin(left.output_projection)
        == _projection_pin(right.output_projection)
    )


def _revalidate_source_evidence(
    prepared: PreparedOverlay,
    *,
    final_ycb: tree_io.TreeSnapshot,
    final_meta: tree_io.TreeSnapshot,
) -> None:
    final_ycb_identity = _seal_tree_identity(final_ycb, "post-copy YCB R7 project")
    final_meta_identity = _seal_tree_identity(final_meta, "post-copy MetaHuman content")
    _require(
        final_ycb == prepared.ycb_project
        and final_ycb_identity == prepared.ycb_project_identity
        and final_meta == prepared.candidate.content
        and final_meta_identity == prepared.candidate.content_identity,
        "an overlay source tree seal changed during copy",
    )

    final_result = _read_sealed_file(
        prepared.candidate.result_seal.path,
        "post-copy MetaHuman authoring result",
    )
    final_request = _read_sealed_file(
        prepared.candidate.request_seal.path,
        "post-copy MetaHuman authoring request",
    )
    final_provider = _read_sealed_file(
        prepared.candidate.provider_seal.path,
        "post-copy MetaHuman provider spec",
    )
    final_script = _read_sealed_file(
        prepared.candidate.script_seal.path,
        "post-copy MetaHuman authoring script",
    )
    final_project = _read_sealed_file(
        prepared.candidate.project_seal.path,
        "post-copy MetaHuman project descriptor",
    )
    final_ycb_receipt = _read_sealed_file(
        prepared.ycb_receipt_seal.path,
        "post-copy YCB R7 host receipt",
        allowed_link_counts=frozenset({2}),
    )
    _require(
        final_result == prepared.candidate.result_seal
        and final_request == prepared.candidate.request_seal
        and final_provider == prepared.candidate.provider_seal
        and final_script == prepared.candidate.script_seal
        and final_project == prepared.candidate.project_seal
        and final_ycb_receipt == prepared.ycb_receipt_seal,
        "a source evidence seal changed during copy",
    )

    result = _strict_json(final_result, "post-copy MetaHuman authoring result")
    request = _strict_json(final_request, "post-copy MetaHuman authoring request")
    provider = _strict_json(final_provider, "post-copy MetaHuman provider spec")
    project = _strict_json(final_project, "post-copy MetaHuman project descriptor")
    ycb_receipt = _strict_json(final_ycb_receipt, "post-copy YCB R7 host receipt")
    inventory = _validate_authoring_result(result)
    _validate_provider_spec(provider, final_provider)
    _validate_authoring_project(project, final_project)
    _validate_authoring_request(
        request,
        attempt_root=prepared.candidate.attempt_root,
        provider=final_provider,
        script=final_script,
        project=final_project,
    )
    _validate_ycb_receipt(ycb_receipt, prepared.config)
    _validate_content_inventory(final_meta, inventory)


def _assert_path_binding(path: pathlib.Path, descriptor: int, label: str) -> None:
    current = os.lstat(path)
    opened = os.fstat(descriptor)
    _require(
        stat.S_ISDIR(current.st_mode)
        and (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino),
        f"{label} path binding changed",
    )


def _success_receipt(prepared: PreparedOverlay) -> dict[str, Any]:
    return _seal_document(
        {
            "schema_version": HOST_RECEIPT_SCHEMA,
            "status": SUCCESS_STATUS,
            "attempt_root": str(prepared.output_root),
            "project_root": str(prepared.output_root / PROJECT_RELATIVE),
            "plan_content_digest": prepared.report["content_digest"],
            "source_ycb_r7": {
                "attempt_root": str(prepared.config.ycb_root),
                "host_receipt_sha256": prepared.config.ycb_host_receipt_sha256,
                "project_projection": dataclasses.asdict(
                    prepared.config.ycb_project_pin
                ),
            },
            "source_metahuman_vivian": {
                "attempt_root": str(prepared.candidate.attempt_root),
                "provider_id": authoring.PROVIDER_ID,
                "authoring_result_sha256": prepared.candidate.result_seal.sha256,
                "authoring_request_sha256": prepared.candidate.request_seal.sha256,
                "provider_spec_sha256": prepared.candidate.provider_seal.sha256,
                "author_script_sha256": prepared.candidate.script_seal.sha256,
                "content_projection": dataclasses.asdict(
                    _tree_pin(prepared.candidate.content)
                ),
            },
            "output_project_projection": dataclasses.asdict(
                _projection_pin(prepared.output_projection)
            ),
            "added_subtree": META_CONTENT_PREFIX.as_posix(),
            "acknowledgements": {
                "epic_private_noncommercial_research": True,
                "external_binaries_never_git": True,
                "metahuman_visual_demo_only_not_ai_training_testing": True,
            },
            "metahuman_usage_scope": {
                "human_operated_visual_demo_only": True,
                "vista_dataset_inclusion": False,
                "ai_training": False,
                "ai_testing": False,
                "ai_evaluation": False,
                "ai_review": False,
                "vlm_training": False,
                "vlm_testing": False,
                "vlm_evaluation": False,
                "vlm_review": False,
                "database_creation_or_population": False,
            },
            "accepted_as_visual_evidence": False,
            "promotable": False,
            "diagnostic_only": True,
            "runtime_executed": False,
            "claims": {
                "vivian_payload_overlaid": True,
                "assembled_candidate_source_verified": True,
                "entitlement_receipt_complete": False,
                "package_validation_complete": False,
                "runtime_provider_ready": False,
                "gta_level": False,
                "real_human_present": False,
                "photoreal_character_accepted": False,
                "player_eye_reviewed": False,
                "interaction_proven": False,
                "visual_acceptance": False,
            },
        }
    )


def apply_plan(prepared: PreparedOverlay) -> dict[str, Any]:
    """Copy the reviewed projection into one fresh append-only attempt."""

    _require(prepared.apply_requested, "apply_plan requires an apply-requested plan")
    _require(
        prepared.epic_license_acknowledged
        and prepared.external_binary_policy_acknowledged,
        "apply acknowledgements are incomplete",
    )
    _require(
        prepared.visual_demo_only_acknowledged,
        "apply MetaHuman use must remain a human-operated visual demo only",
    )
    fresh = build_plan(
        prepared.config,
        prepared.candidate.attempt_root,
        prepared.output_root,
        apply=True,
        allow_epic_private_research_license=True,
        allow_external_binaries_never_git=True,
        ack_metahuman_visual_demo_only_not_ai_training_testing=True,
    )
    _require(_same_plan(prepared, fresh), "overlay inputs drifted after plan review")

    parent_fd = tree_io._open_directory_fd(prepared.config.run_parent)
    output_fd = -1
    project_fd = -1
    output_created = False
    success_published = False
    expected_receipt_raw: bytes | None = None
    try:
        parent_metadata = os.fstat(parent_fd)
        _require(
            (parent_metadata.st_dev, parent_metadata.st_ino)
            == prepared.run_parent_identity,
            "run parent binding changed",
        )
        try:
            os.mkdir(
                prepared.output_root.name,
                PRIVATE_DIRECTORY_MODE,
                dir_fd=parent_fd,
            )
        except FileExistsError as exc:
            raise OverlayError("overlay output collision") from exc
        output_created = True
        output_fd = os.open(
            prepared.output_root.name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        os.fchmod(output_fd, PRIVATE_DIRECTORY_MODE)
        _assert_path_binding(prepared.output_root, output_fd, "overlay output")
        os.mkdir("project", PRIVATE_DIRECTORY_MODE, dir_fd=output_fd)
        project_fd = os.open(
            "project",
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=output_fd,
        )
        os.fchmod(project_fd, PRIVATE_DIRECTORY_MODE)

        tree_io._mkdir_projection(project_fd, fresh.output_projection.directories)
        for record in fresh.output_projection.files:
            tree_io._copy_record(project_fd, record)
        os.fsync(project_fd)

        _assert_path_binding(
            prepared.output_root / PROJECT_RELATIVE,
            project_fd,
            "materialized overlay project",
        )
        observed = tree_io.snapshot_tree(
            prepared.output_root / PROJECT_RELATIVE,
            "materialized overlay project",
            require_private_modes=True,
        )
        tree_io._assert_tree_pin(
            observed,
            _projection_pin(prepared.output_projection),
            "materialized overlay project",
        )

        # Re-hash both sources after copying. Individual copies also validate
        # inode, size, mtime, mode, and digest before publishing each file.
        final_ycb = tree_io.snapshot_tree(
            prepared.config.ycb_project_root,
            "post-copy YCB R7 project",
            require_private_modes=True,
        )
        final_meta = tree_io.snapshot_tree(
            prepared.candidate.content_root,
            "post-copy MetaHuman content",
        )
        _revalidate_source_evidence(
            prepared,
            final_ycb=final_ycb,
            final_meta=final_meta,
        )

        receipt = _success_receipt(prepared)
        expected_receipt_raw = _canonical_json(receipt)
        tree_io._publish_exclusive_at(
            output_fd,
            HOST_RECEIPT_PROVISIONAL_NAME,
            HOST_RECEIPT_NAME,
            expected_receipt_raw,
        )
        success_published = True
        return receipt
    except BaseException as exc:
        if (
            not success_published
            and output_fd >= 0
            and expected_receipt_raw is not None
        ):
            success_published = tree_io._published_receipt_matches(
                output_fd,
                HOST_RECEIPT_PROVISIONAL_NAME,
                HOST_RECEIPT_NAME,
                expected_receipt_raw,
            )
        quarantine_fd = output_fd
        quarantine_fd_owned = False
        if quarantine_fd < 0 and output_created:
            try:
                quarantine_fd = os.open(
                    prepared.output_root.name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=parent_fd,
                )
                quarantine_fd_owned = True
            except OSError:
                quarantine_fd = -1
        if output_created and not success_published:
            failure = _seal_document(
                {
                    "schema_version": HOST_RECEIPT_SCHEMA,
                    "status": FAILURE_STATUS,
                    "attempt_root": str(prepared.output_root),
                    "accepted_as_visual_evidence": False,
                    "promotable": False,
                    "diagnostic_only": True,
                    "runtime_executed": False,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc)[:512],
                    },
                }
            )
            try:
                if quarantine_fd >= 0:
                    tree_io._write_exclusive_at(
                        quarantine_fd,
                        HOST_FAILURE_NAME,
                        _canonical_json(failure),
                    )
                else:
                    tree_io._write_exclusive_at(
                        parent_fd,
                        prepared.output_root.name + PARENT_FAILURE_SUFFIX,
                        _canonical_json(failure),
                    )
            except BaseException as quarantine_error:  # noqa: BLE001
                print(
                    "MetaHuman overlay could not publish quarantine receipt: "
                    + str(quarantine_error)[:512],
                    file=sys.stderr,
                )
            finally:
                if quarantine_fd_owned and quarantine_fd >= 0:
                    os.close(quarantine_fd)
        raise
    finally:
        if project_fd >= 0:
            os.close(project_fd)
        if output_fd >= 0:
            os.close(output_fd)
        os.close(parent_fd)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metahuman-attempt",
        required=True,
        type=pathlib.Path,
        help="successful fixed Vivian authoring attempt under the closed run parent",
    )
    parser.add_argument(
        "--attempt-root",
        required=True,
        type=pathlib.Path,
        help="fresh ycb-r7-vivian-* direct child of the closed run parent",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-epic-private-research-license",
        action="store_true",
        help="acknowledge private noncommercial Unreal-only Epic content use",
    )
    parser.add_argument(
        "--allow-external-binaries-never-git",
        action="store_true",
        help="acknowledge that all MetaHuman binary payloads remain outside Git",
    )
    parser.add_argument(
        "--ack-metahuman-visual-demo-only-not-ai-training-testing",
        action="store_true",
        help=(
            "acknowledge Vivian is only for a human-operated visual demo and is "
            "excluded from datasets, AI/VLM training, testing, evaluation, review, "
            "and database creation"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    prepared = build_plan(
        production_config(),
        arguments.metahuman_attempt,
        arguments.attempt_root,
        apply=arguments.apply,
        allow_epic_private_research_license=(
            arguments.allow_epic_private_research_license
        ),
        allow_external_binaries_never_git=(arguments.allow_external_binaries_never_git),
        ack_metahuman_visual_demo_only_not_ai_training_testing=(
            arguments.ack_metahuman_visual_demo_only_not_ai_training_testing
        ),
    )
    result = apply_plan(prepared) if arguments.apply else prepared.report
    print(_canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OverlayError, OSError) as error:
        print(f"MetaHuman runtime overlay refused: {error}", file=sys.stderr)
        raise SystemExit(2) from error
