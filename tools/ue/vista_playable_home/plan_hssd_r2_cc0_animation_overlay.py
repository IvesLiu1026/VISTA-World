#!/usr/bin/env python3
"""Plan a sealed h -> MakeHuman CC0 R8 overlay without writing anything.

This module is deliberately a planner, not a materializer.  The production
configuration pins the accepted R9 ``h`` candidate and the R3 character import.
The future R8 animation publication and BuildPlugin authority intentionally
remain absent, so the current production result is a deterministic blocked
plan.  Tests may supply complete fake authorities through ``Config``; the CLI
does not expose any authority, path, provider, apply, or execute override.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

# The CLI is a zero-write verifier; importing the shared closed contract must
# not create a checkout-local ``__pycache__`` side effect.
sys.dont_write_bytecode = True

try:
    from tools.ue.vista_playable_home import (
        makehuman_cc0_animation_runtime_executor as r8_executor_contract,
    )
except ModuleNotFoundError:  # Direct script execution from this directory.
    import makehuman_cc0_animation_runtime_executor as r8_executor_contract


PLAN_SCHEMA = "simworld.vista.hssd-r2-cc0-animation-overlay-plan/v1"
BLOCKED_STATUS = "blocked_pending_animation_overlay_authorities"
READY_STATUS = "ready_for_future_materializer"
MODE = "dry_run_zero_writes"

H_COMPLETE_SCHEMA = "simworld.vista.hssd-r2-citysample-live-complete/v1"
H_COMPLETE_STATUS = "hssd_r2_citysample_live_publication_complete"
H_COMBINED_SCHEMA = "simworld.vista.human-visual-demo-combined-receipt/v5"
H_COMBINED_STATUS = "sealed_human_visual_demo_candidate"
H_HOST_SCHEMA = "simworld.vista.hssd-r2-citysample-live-host-receipt/v1"
H_HOST_STATUS = "hssd_r2_citysample_live_saved_cold_reloaded"
R3_SCHEMA = "vista.makehuman-cc0-ue57-import-host-receipt/v1"
R3_STATUS = "cc0_skeletal_import_post_exit_project_sealed"
R8_HOST_SCHEMA = "vista.r8-sealed-ue57-animation-host-receipt/v1"
R8_HOST_STATUS = "sealed_ue57_animation_import_pending_runtime_and_human_review"
R8_RUNTIME_SCHEMA = "vista.makehuman-cc0-ue57-animation-runtime-receipt/v1"
R8_RUNTIME_STATUS = "cc0_animation_runtime_assets_saved_reloaded_pending_runtime"
BUILDPLUGIN_MANIFEST_SCHEMA = "vista.r8-buildplugin-authority-manifest/v1"
BUILDPLUGIN_RECEIPT_SCHEMA = "vista.r8-buildplugin-authority-receipt/v2"
BUILDPLUGIN_ADMIN_RECEIPT_SCHEMA = "vista.r8-buildplugin-admin-install-receipt/v1"
BUILDPLUGIN_RECEIPT_STATUS = "root_published_immutable_buildplugin_authority"

SOURCE_PROVIDER = "citysample_crowd_visual_demo_v1"
TARGET_PROVIDER = "makehuman_cc0_r8"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
MAP_RELATIVE_PATH = (
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
PROJECT_DESCRIPTOR_NAME = "VistaPlayableHome.uproject"
PLUGIN_TARGET = "Plugins/VistaPlayableHome"
R3_NAMESPACE = "Content/VISTA/MakeHumanCC0/R6"
R8_NAMESPACE = "Content/VISTA/MakeHumanCC0/R8/Animations"

ATTEMPT_RE = re.compile(
    r"^hssd-r2-cc0-animation-overlay-r1-[a-z0-9]"
    r"(?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
R8_ATTEMPT_RE = re.compile(
    r"^makehuman-cc0-animation-ue57-r1-[a-z0-9]"
    r"(?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024

R8_RUNTIME_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "accepted",
        "error",
        "attempt_root",
        "project_root",
        "content_namespace",
        "bindings",
        "returned_object_paths",
        "pipeline_policies",
        "sequence_inspection",
        "runtime_authoring_result",
        "asset_inventory",
        "package_inventory",
        "project_content_delta",
        "gates",
        "claims",
        "content_digest",
    }
)
R8_HOST_KEYS = frozenset(
    {
        "schema",
        "status",
        "accepted",
        "attempt_name",
        "bindings",
        "project_projection",
        "added_project_relative_paths",
        "claims",
        "content_digest",
    }
)
R8_HOST_BINDING_KEYS = frozenset(
    {
        "root_policy_content_digest",
        "launch_plan_content_digest",
        "host_execution_content_digest",
        "commandlet_execution_content_digest",
        "engine_manifest_content_digest",
        "engine_tree_digest",
        "engine_build_id",
        "host_runtime_tree_digest",
        "r3_project_tree_digest",
        "r8_host_receipt_sha256",
        "buildplugin_tree_digest",
        "sandbox_archive_sha256",
        "commandlet_receipt_content_digest",
        "commandlet_result_receipt_sha256",
    }
)
R8_RUNTIME_BINDING_KEYS = frozenset(
    {
        "engine",
        "project",
        "execution_manifest",
        "execution_manifest_sha256",
        "source_host_receipt",
        "source_fbx",
        "commandlet",
        "skeleton_object_path",
        "mesh_object_path",
    }
)
BUILDPLUGIN_MANIFEST_KEYS = frozenset(
    {"schema_version", "source", "authority", "critical_files", "entries"}
)
BUILDPLUGIN_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "accepted",
        "status",
        "source",
        "authority",
        "publisher",
        "admin_publication",
        "policy",
        "claims",
        "content_digest",
    }
)
BUILDPLUGIN_POLICY = {
    "copy_from_held_source_descriptors_only": True,
    "all_source_file_descriptors_held": True,
    "source_namespace_revalidated_after_copy": True,
    "fresh_staging_only": True,
    "atomic_publish": "renameat2_noreplace",
    "output_directory_mode": "0555",
    "output_file_mode": "0444",
}
BUILDPLUGIN_NEGATIVE_CLAIMS = {
    "ue_plugin_loaded": False,
    "ue_commandlet_executed": False,
    "animation_runtime_verified": False,
    "pickup_place_verified": False,
    "two_client_verified": False,
    "human_motion_quality_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
    "private_epic_content_used": False,
}
BUILDPLUGIN_HELPER_PATH = Path(
    "/root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py"
)
BUILDPLUGIN_HELPER_SHA256 = (
    "e3a62276111da8f832d41145580f1dc79fe4c56ff04b44e8ba6ec2d4ee89b772"
)
BUILDPLUGIN_HELPER_SIZE_BYTES = 74_019
BUILDPLUGIN_INTERPRETER = {
    "path": "/usr/bin/python3.10",
    "mode": "0755",
    "sha256": "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86",
    "size_bytes": 5_917_224,
}
BUILDPLUGIN_ADMIN_AUTHORITY_ROOT = Path("/root/vista-r8-buildplugin-admin-r1")
BUILDPLUGIN_ADMIN_LAUNCHER = (
    BUILDPLUGIN_ADMIN_AUTHORITY_ROOT / "publish-reconcile-buildplugin"
)
BUILDPLUGIN_ADMIN_RECEIPT = BUILDPLUGIN_ADMIN_AUTHORITY_ROOT / "receipt.json"

LEGAL_SCOPE = {
    "epic_ue_only_content_entitlement_confirmed": True,
    "excluded_from_ai_vlm_training_testing_evaluation_or_review": True,
    "excluded_from_vista_dataset_or_database": True,
    "external_assets_outside_git": True,
    "metahuman_human_operated_visual_demo_only": True,
    "no_source_uasset_redistribution": True,
    "private_noncommercial_research_only": True,
}
PARENT_CLAIMS = {
    "gta_level_quality": False,
    "interaction_accepted": False,
    "photoreal_character_accepted": False,
    "runtime_visual_acceptance": False,
}
PLAN_CLAIMS = {
    "overlay_materialized": False,
    "ue_animation_imported_into_h_child": False,
    "runtime_provider_verified": False,
    "runtime_interaction_verified": False,
    "dedicated_server_two_client_verified": False,
    "human_motion_quality_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
}
R3_CLAIMS = {
    "active_65_canonical_face_morphs_verified": True,
    "animation_verified": False,
    "auxiliary_active_tongue_out_verified": True,
    "exact_53_bones_verified": True,
    "gta_level_quality": False,
    "interaction_verified": False,
    "manny_retarget_verified": False,
    "own_skeleton_imported": True,
    "photoreal_character_accepted": False,
    "physics_asset_imported": True,
    "project_post_exit_sealed": True,
    "runtime_verified": False,
    "semantic_67_control_contract_verified": True,
    "source_cc0_contract_verified": True,
    "ue_skeletal_imported": True,
    "zero_delta_neutral_and_base_tongue_source_contract_verified": True,
}

H_COMPLETE_KEYS = frozenset(
    {
        "attempt_root",
        "combined_receipt",
        "combined_receipt_sidecar",
        "content_digest",
        "current_state",
        "failure_absent",
        "host_receipt",
        "schema_version",
        "status",
    }
)
H_COMBINED_KEYS = frozenset(
    {
        "claims",
        "content_digest",
        "executable",
        "hssd_r2_citysample_live_r1_upgrade",
        "human_operated_visual_demo_only",
        "legal_scope",
        "map",
        "prohibited_agent_adapter",
        "project",
        "project_static_tree",
        "provider_id",
        "schema_version",
        "source_provenance",
        "status",
    }
)
H_HOST_KEYS = frozenset(
    {
        "acceptance",
        "claims",
        "containment",
        "content_digest",
        "current_byte_revalidation",
        "execution",
        "fixture_evidence_manifest",
        "gates",
        "human_operated_visual_demo_only",
        "legal_scope",
        "log_closure",
        "logs",
        "map",
        "prohibited_agent_adapter",
        "project",
        "project_static_tree",
        "provider_id",
        "result",
        "scene_receipt",
        "schema_version",
        "static_delta",
        "status",
    }
)
R3_KEYS = frozenset(
    {
        "accepted",
        "attempt_root",
        "claims",
        "content_digest",
        "execution_manifest",
        "import_receipt",
        "logs",
        "output_project_projection",
        "package_inventory",
        "project_root",
        "schema_version",
        "source",
        "status",
    }
)
PACKAGE_ROW_KEYS = frozenset(
    {
        "class_path",
        "object_path",
        "package_name",
        "project_relative_path",
        "sha256",
        "size_bytes",
    }
)

R3_PACKAGE_PATHS = (
    "Content/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6.uasset",
    "Content/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6_PhysicsAsset.uasset",
    "Content/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6_Skeleton.uasset",
    "Content/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_body.uasset",
    "Content/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_eyebrow001.uasset",
    "Content/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_eyelashes01.uasset",
    "Content/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_female_casualsuit01.uasset",
    "Content/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_high-poly.uasset",
    "Content/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_long01.uasset",
    "Content/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_shoes01.uasset",
    "Content/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_teeth_base.uasset",
    "Content/VISTA/MakeHumanCC0/R6/VISTA_CC0_Hero_Body_tongue01.uasset",
    "Content/VISTA/MakeHumanCC0/R6/brown_eye.uasset",
    "Content/VISTA/MakeHumanCC0/R6/eyebrow001.uasset",
    "Content/VISTA/MakeHumanCC0/R6/eyelashes01.uasset",
    "Content/VISTA/MakeHumanCC0/R6/female_casualsuit01_diffuse.uasset",
    "Content/VISTA/MakeHumanCC0/R6/female_casualsuit01_normal.uasset",
    "Content/VISTA/MakeHumanCC0/R6/long01_diffuse.uasset",
    "Content/VISTA/MakeHumanCC0/R6/shoes01_diffuse.uasset",
    "Content/VISTA/MakeHumanCC0/R6/shoes01_normal.uasset",
    "Content/VISTA/MakeHumanCC0/R6/teeth.uasset",
    "Content/VISTA/MakeHumanCC0/R6/tongue01_diffuse.uasset",
    "Content/VISTA/MakeHumanCC0/R6/young_eurasian_female_diffuse.uasset",
)

R8_PACKAGE_PATHS = (
    "Content/VISTA/MakeHumanCC0/R8/Animations/ABP_VistaCC0Hero_R8.uasset",
    "Content/VISTA/MakeHumanCC0/R8/Animations/BS_VistaCC0Locomotion_R8.uasset",
    "Content/VISTA/MakeHumanCC0/R8/Animations/Montages/"
    "AM_VistaCC0MugPickupCountertop.uasset",
    "Content/VISTA/MakeHumanCC0/R8/Animations/Montages/"
    "AM_VistaCC0MugPlaceCountertop.uasset",
    "Content/VISTA/MakeHumanCC0/R8/Animations/Sequences/AS_VistaCC0Idle.uasset",
    "Content/VISTA/MakeHumanCC0/R8/Animations/Sequences/"
    "AS_VistaCC0MugPickupCountertop.uasset",
    "Content/VISTA/MakeHumanCC0/R8/Animations/Sequences/"
    "AS_VistaCC0MugPlaceCountertop.uasset",
    "Content/VISTA/MakeHumanCC0/R8/Animations/Sequences/AS_VistaCC0Run.uasset",
    "Content/VISTA/MakeHumanCC0/R8/Animations/Sequences/AS_VistaCC0Walk.uasset",
)


class PlanError(RuntimeError):
    """A bounded closed-contract failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclasses.dataclass(frozen=True)
class FilePin:
    sha256: str
    size_bytes: int
    mode: int

    def public(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mode": f"{self.mode:04o}",
        }


@dataclasses.dataclass(frozen=True)
class PinnedFile:
    path: Path
    pin: FilePin

    def public(self) -> dict[str, Any]:
        return {"path": str(self.path), **self.pin.public()}


@dataclasses.dataclass(frozen=True)
class TreeProjection:
    sha256: str
    file_count: int
    directory_count: int | None
    total_bytes: int

    def public(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "sha256": self.sha256,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
        }
        if self.directory_count is not None:
            result["directory_count"] = self.directory_count
        return result


@dataclasses.dataclass(frozen=True)
class ParentContract:
    root: Path
    complete: PinnedFile
    combined: PinnedFile
    host: PinnedFile
    project: PinnedFile
    map_package: PinnedFile
    failure_marker: Path
    tree: TreeProjection


@dataclasses.dataclass(frozen=True)
class R3Contract:
    attempt_root: Path
    project_root: Path
    receipt: PinnedFile
    project_tree: TreeProjection
    inventory_digest: str
    package_paths: tuple[str, ...]
    package_mode: int


@dataclasses.dataclass(frozen=True)
class R8Authority:
    root: Path
    host_receipt: PinnedFile
    runtime_receipt: PinnedFile


@dataclasses.dataclass(frozen=True)
class BuildPluginContract:
    root: Path
    source_path: Path
    projection_sha256: str
    inventory_sha256: str
    file_count: int
    directory_count: int
    total_bytes: int
    critical_files: Mapping[str, FilePin]

    @property
    def payload(self) -> Path:
        return self.root / "payload"


@dataclasses.dataclass(frozen=True)
class BuildPluginAuthority:
    root: Path
    manifest: PinnedFile
    receipt: PinnedFile


@dataclasses.dataclass(frozen=True)
class Config:
    run_parent: Path
    parent: ParentContract
    r3: R3Contract
    r8_published_parent: Path
    r8_authority: R8Authority | None
    buildplugin: BuildPluginContract
    buildplugin_authority: BuildPluginAuthority | None
    require_root_owned_future_authorities: bool = True


@dataclasses.dataclass(frozen=True)
class PreparedPlan:
    report: Mapping[str, Any]

    @property
    def raw(self) -> bytes:
        return canonical_json(self.report)


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
        raise PlanError("OVERLAY_JSON_INVALID", "value is not canonical JSON") from exc


def content_digest(
    document: Mapping[str, Any], *, trailing_newline: bool = True
) -> str:
    body = copy.deepcopy(dict(document))
    body.pop("content_digest", None)
    raw = canonical_json(body)
    if not trailing_newline:
        raw = raw.removesuffix(b"\n")
    return hashlib.sha256(raw).hexdigest()


def seal_document(document: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(document))
    result["content_digest"] = content_digest(result)
    return result


def _fail(code: str, detail: str) -> None:
    raise PlanError(code, detail)


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        _fail(code, detail)


def _require_directory_no_symlink(path: Path, label: str) -> None:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise PlanError("OVERLAY_PATH_INVALID", f"{label} is unavailable") from exc
    _require(
        stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        "OVERLAY_PATH_INVALID",
        f"{label} is not a direct directory",
    )


def _require_safe_file_parent_chain(
    root: Path,
    path: Path,
    label: str,
    *,
    require_root_owned_immutable: bool = False,
) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise PlanError(
            "OVERLAY_PATH_INVALID", f"{label} escaped its fixed root"
        ) from exc
    current = root
    _require_directory_no_symlink(current, f"{label} root")
    if require_root_owned_immutable:
        _require_root_immutable(current, f"{label} root")
    for component in relative.parts[:-1]:
        current /= component
        _require_directory_no_symlink(current, f"{label} parent")
        if require_root_owned_immutable:
            _require_root_immutable(current, f"{label} parent")


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    _require(
        0 < len(raw) <= MAX_DOCUMENT_BYTES,
        "OVERLAY_DOCUMENT_INVALID",
        f"{label} size is invalid",
    )
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid constant: {token}")
            ),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise PlanError(
            "OVERLAY_DOCUMENT_INVALID", f"{label} is not strict JSON"
        ) from exc
    _require(
        type(value) is dict,
        "OVERLAY_DOCUMENT_INVALID",
        f"{label} is not an object",
    )
    return value


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_pinned_file(
    item: PinnedFile,
    label: str,
    *,
    maximum_bytes: int | None = None,
    require_single_link: bool = True,
    require_root_owned: bool = False,
) -> bytes:
    pin = item.pin
    _require(
        SHA256_RE.fullmatch(pin.sha256) is not None
        and type(pin.size_bytes) is int
        and pin.size_bytes > 0
        and type(pin.mode) is int,
        "OVERLAY_PIN_INVALID",
        f"{label} pin is invalid",
    )
    try:
        before = os.lstat(item.path)
    except OSError as exc:
        raise PlanError("OVERLAY_INPUT_MISSING", f"{label} is unavailable") from exc
    _require(
        stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
        "OVERLAY_INPUT_INVALID",
        f"{label} is not a regular file",
    )
    _require(
        not require_single_link or before.st_nlink == 1,
        "OVERLAY_INPUT_INVALID",
        f"{label} link count differs",
    )
    _require(
        not require_root_owned or (before.st_uid == 0 and before.st_gid == 0),
        "OVERLAY_AUTHORITY_INVALID",
        f"{label} is not root-owned",
    )
    _require(
        before.st_size == pin.size_bytes and stat.S_IMODE(before.st_mode) == pin.mode,
        "OVERLAY_PIN_MISMATCH",
        f"{label} size or mode differs",
    )
    if maximum_bytes is not None:
        _require(
            before.st_size <= maximum_bytes,
            "OVERLAY_INPUT_INVALID",
            f"{label} exceeds size policy",
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    try:
        descriptor = os.open(item.path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            _require(
                _identity(opened) == _identity(before),
                "OVERLAY_INPUT_CHANGED",
                f"{label} changed while opening",
            )
            for block in iter(lambda: handle.read(CHUNK_BYTES), b""):
                digest.update(block)
                chunks.append(block)
    except PlanError:
        raise
    except OSError as exc:
        raise PlanError("OVERLAY_INPUT_INVALID", f"{label} cannot be read") from exc
    after = os.lstat(item.path)
    _require(
        _identity(after) == _identity(before),
        "OVERLAY_INPUT_CHANGED",
        f"{label} changed while hashing",
    )
    _require(
        digest.hexdigest() == pin.sha256,
        "OVERLAY_PIN_MISMATCH",
        f"{label} SHA-256 differs",
    )
    return b"".join(chunks)


def _read_document(
    item: PinnedFile,
    label: str,
    *,
    trailing_newline: bool = True,
    require_root_owned: bool = False,
) -> dict[str, Any]:
    document = _strict_json(
        _read_pinned_file(
            item,
            label,
            maximum_bytes=MAX_DOCUMENT_BYTES,
            require_root_owned=require_root_owned,
        ),
        label,
    )
    _require(
        document.get("content_digest")
        == content_digest(document, trailing_newline=trailing_newline),
        "OVERLAY_DOCUMENT_SEAL_MISMATCH",
        f"{label} content digest differs",
    )
    return document


def _safe_package_path(value: Any, namespace: str, label: str) -> str:
    _require(
        type(value) is str
        and value
        and "\\" not in value
        and all(
            not (ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F)
            for character in value
        ),
        "OVERLAY_PACKAGE_PATH_INVALID",
        f"{label} is invalid",
    )
    pure = PurePosixPath(value)
    _require(
        not pure.is_absolute()
        and all(part not in {"", ".", ".."} for part in pure.parts)
        and pure.as_posix() == value
        and value.startswith(namespace + "/")
        and value.endswith(".uasset"),
        "OVERLAY_PACKAGE_PATH_INVALID",
        f"{label} escaped its namespace",
    )
    return value


def _assert_distinct_paths(paths: Sequence[str], label: str) -> None:
    _require(
        len(paths) == len(set(paths)),
        "OVERLAY_PACKAGE_INVENTORY_INVALID",
        f"{label} contains duplicates",
    )
    folded: dict[str, str] = {}
    for path in paths:
        prior = folded.get(path.casefold())
        _require(
            prior is None,
            "OVERLAY_PACKAGE_INVENTORY_INVALID",
            f"{label} contains a case-fold collision",
        )
        folded[path.casefold()] = path


def _pin_mapping(item: PinnedFile) -> dict[str, Any]:
    return item.public()


def _tree_mapping(tree: TreeProjection) -> dict[str, Any]:
    result = tree.public()
    result["algorithm"] = "sha256-path-nul-mode-size-content-v1"
    return result


def _receipt_file_mapping(item: PinnedFile) -> dict[str, Any]:
    return {
        "path": str(item.path),
        "sha256": item.pin.sha256,
        "size_bytes": item.pin.size_bytes,
    }


def _validate_parent(config: Config) -> dict[str, Any]:
    contract = config.parent
    _require_directory_no_symlink(contract.root, "h authority root")
    _require_directory_no_symlink(contract.root / "project", "h project root")
    _require(
        contract.complete.path.parent == contract.root
        and contract.combined.path.parent == contract.root
        and contract.host.path.parent == contract.root
        and contract.project.path == contract.root / "project" / PROJECT_DESCRIPTOR_NAME
        and contract.map_package.path == contract.root / "project" / MAP_RELATIVE_PATH,
        "OVERLAY_PARENT_PATH_INVALID",
        "parent paths differ from the closed layout",
    )
    complete = _read_document(contract.complete, "h complete receipt")
    combined = _read_document(contract.combined, "h combined receipt")
    host = _read_document(contract.host, "h host receipt")
    _require_safe_file_parent_chain(
        contract.root / "project", contract.project.path, "h project descriptor"
    )
    _require_safe_file_parent_chain(
        contract.root / "project", contract.map_package.path, "h map package"
    )
    _read_pinned_file(contract.project, "h project descriptor")
    _read_pinned_file(contract.map_package, "h map package")

    _require(
        set(complete) == H_COMPLETE_KEYS
        and complete.get("schema_version") == H_COMPLETE_SCHEMA
        and complete.get("status") == H_COMPLETE_STATUS
        and complete.get("attempt_root") == str(contract.root)
        and complete.get("failure_absent") is True,
        "OVERLAY_PARENT_RECEIPT_INVALID",
        "h complete receipt differs",
    )
    _require(
        complete.get("combined_receipt") == _receipt_file_mapping(contract.combined)
        and complete.get("host_receipt") == _receipt_file_mapping(contract.host),
        "OVERLAY_PARENT_LINEAGE_INVALID",
        "h complete receipt lineage differs",
    )
    _require(
        set(combined) == H_COMBINED_KEYS
        and combined.get("schema_version") == H_COMBINED_SCHEMA
        and combined.get("status") == H_COMBINED_STATUS,
        "OVERLAY_PARENT_RECEIPT_INVALID",
        "h combined receipt differs",
    )
    _require(
        set(host) == H_HOST_KEYS
        and host.get("schema_version") == H_HOST_SCHEMA
        and host.get("status") == H_HOST_STATUS,
        "OVERLAY_PARENT_RECEIPT_INVALID",
        "h host receipt differs",
    )

    expected_tree = {
        "algorithm": "sha256-path-nul-mode-size-content-v1",
        "file_count": contract.tree.file_count,
        "total_bytes": contract.tree.total_bytes,
        "tree_sha256": contract.tree.sha256,
    }
    expected_project = {
        "path": str(contract.project.path),
        "sha256": contract.project.pin.sha256,
        "size_bytes": contract.project.pin.size_bytes,
    }
    expected_map = {
        "object_path": MAP_OBJECT_PATH,
        "package": {
            "path": str(contract.map_package.path),
            "sha256": contract.map_package.pin.sha256,
            "size_bytes": contract.map_package.pin.size_bytes,
        },
    }
    for label, document in (("combined", combined), ("host", host)):
        _require(
            document.get("project_static_tree") == expected_tree
            and document.get("project") == expected_project
            and document.get("map") == expected_map
            and document.get("provider_id") == SOURCE_PROVIDER
            and document.get("human_operated_visual_demo_only") is True
            and document.get("prohibited_agent_adapter") is True
            and document.get("legal_scope") == LEGAL_SCOPE
            and document.get("claims") == PARENT_CLAIMS,
            "OVERLAY_PARENT_COHERENCE_INVALID",
            f"h {label} authority differs",
        )
    current = complete.get("current_state")
    _require(
        type(current) is dict
        and current.get("project_static_tree") == expected_tree
        and current.get("map")
        == {
            "path": str(contract.map_package.path),
            "sha256": contract.map_package.pin.sha256,
            "size_bytes": contract.map_package.pin.size_bytes,
        },
        "OVERLAY_PARENT_COHERENCE_INVALID",
        "h complete current-state authority differs",
    )
    revalidation = host.get("current_byte_revalidation")
    _require(
        type(revalidation) is dict
        and revalidation.get("passed") is True
        and revalidation.get("project_static_tree") == expected_tree
        and revalidation.get("map") == current.get("map"),
        "OVERLAY_PARENT_COHERENCE_INVALID",
        "h host current-byte revalidation differs",
    )
    _require(
        not os.path.lexists(contract.failure_marker),
        "OVERLAY_PARENT_FAILURE_PRESENT",
        "h failure marker exists",
    )

    vista_content = contract.root / "project/Content/VISTA"
    _require_directory_no_symlink(vista_content, "h VISTA content root")
    try:
        entries = list(os.scandir(vista_content))
    except OSError as exc:
        raise PlanError(
            "OVERLAY_PARENT_PATH_INVALID", "h VISTA content root is unavailable"
        ) from exc
    _require(
        all(entry.name.casefold() != "makehumancc0" for entry in entries),
        "OVERLAY_PARENT_NAMESPACE_COLLISION",
        "h already contains a MakeHumanCC0 namespace",
    )
    _require_directory_no_symlink(
        contract.root / "project" / PLUGIN_TARGET, "h plugin replacement target"
    )
    return {
        "root": str(contract.root),
        "complete_receipt": _pin_mapping(contract.complete),
        "combined_receipt": _pin_mapping(contract.combined),
        "host_receipt": _pin_mapping(contract.host),
        "project": _pin_mapping(contract.project),
        "map": {
            "object_path": MAP_OBJECT_PATH,
            "relative_path": MAP_RELATIVE_PATH,
            "package": _pin_mapping(contract.map_package),
        },
        "project_static_tree": _tree_mapping(contract.tree),
        "full_tree_rescan_performed": False,
        "full_tree_rescan_required_by_future_materializer": True,
    }


def _inventory_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(canonical_json({"package_inventory": list(rows)})).hexdigest()


def _validate_package_rows(
    rows: Any,
    *,
    expected_paths: Sequence[str],
    namespace: str,
    project_root: Path,
    package_mode: int,
    label: str,
    expected_asset_inventory: Sequence[Mapping[str, Any]] | None = None,
    require_root_owned: bool = False,
) -> list[dict[str, Any]]:
    _require(
        type(rows) is list and len(rows) == len(expected_paths),
        "OVERLAY_PACKAGE_INVENTORY_INVALID",
        f"{label} package count differs",
    )
    _require(
        expected_asset_inventory is None
        or len(expected_asset_inventory) == len(expected_paths),
        "OVERLAY_PACKAGE_INVENTORY_INVALID",
        f"{label} expected class inventory differs",
    )
    normalized: list[dict[str, Any]] = []
    observed_paths: list[str] = []
    for index, raw in enumerate(rows):
        _require(
            type(raw) is dict and set(raw) == PACKAGE_ROW_KEYS,
            "OVERLAY_PACKAGE_INVENTORY_INVALID",
            f"{label} package row {index} differs",
        )
        row = dict(raw)
        relative = _safe_package_path(
            row.get("project_relative_path"), namespace, f"{label} package path"
        )
        _require(
            type(row.get("class_path")) is str
            and str(row["class_path"]).startswith("/Script/")
            and type(row.get("object_path")) is str
            and type(row.get("package_name")) is str
            and type(row.get("sha256")) is str
            and SHA256_RE.fullmatch(str(row["sha256"])) is not None
            and type(row.get("size_bytes")) is int
            and row["size_bytes"] > 0,
            "OVERLAY_PACKAGE_INVENTORY_INVALID",
            f"{label} package metadata differs: {relative}",
        )
        expected_package = "/Game/" + relative.removeprefix("Content/").removesuffix(
            ".uasset"
        )
        expected_object = expected_package + "." + PurePosixPath(expected_package).name
        _require(
            row["package_name"] == expected_package
            and row["object_path"] == expected_object,
            "OVERLAY_PACKAGE_INVENTORY_INVALID",
            f"{label} package/object path differs: {relative}",
        )
        if expected_asset_inventory is not None:
            expected_asset = expected_asset_inventory[index]
            _require(
                type(expected_asset) is dict
                and set(expected_asset) == {"class_path", "object_path"}
                and row["class_path"] == expected_asset["class_path"]
                and row["object_path"] == expected_asset["object_path"],
                "OVERLAY_PACKAGE_INVENTORY_INVALID",
                f"{label} package class differs: {relative}",
            )
        _require_safe_file_parent_chain(
            project_root,
            project_root / relative,
            f"{label} package {relative}",
            require_root_owned_immutable=require_root_owned,
        )
        _read_pinned_file(
            PinnedFile(
                project_root / relative,
                FilePin(str(row["sha256"]), int(row["size_bytes"]), package_mode),
            ),
            f"{label} package {relative}",
            require_root_owned=require_root_owned,
        )
        observed_paths.append(relative)
        normalized.append(row)
    _assert_distinct_paths(observed_paths, label)
    _require(
        tuple(observed_paths) == tuple(expected_paths),
        "OVERLAY_PACKAGE_INVENTORY_INVALID",
        f"{label} package paths or order differ",
    )
    return normalized


def _validate_r3(
    config: Config,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = config.r3
    _require_directory_no_symlink(contract.attempt_root, "R3 authority root")
    _require_directory_no_symlink(contract.project_root, "R3 project root")
    _require(
        contract.receipt.path.parent == contract.attempt_root
        and contract.project_root == contract.attempt_root / "project",
        "OVERLAY_R3_PATH_INVALID",
        "R3 paths differ from the closed layout",
    )
    receipt = _read_document(
        contract.receipt, "R3 host receipt", trailing_newline=False
    )
    _require(
        set(receipt) == R3_KEYS
        and receipt.get("schema_version") == R3_SCHEMA
        and receipt.get("status") == R3_STATUS
        and receipt.get("accepted") is False
        and receipt.get("attempt_root") == str(contract.attempt_root)
        and receipt.get("project_root") == str(contract.project_root)
        and receipt.get("claims") == R3_CLAIMS,
        "OVERLAY_R3_RECEIPT_INVALID",
        "R3 host receipt differs",
    )
    expected_projection = {
        "sha256": contract.project_tree.sha256,
        "file_count": contract.project_tree.file_count,
        "directory_count": contract.project_tree.directory_count,
        "total_bytes": contract.project_tree.total_bytes,
    }
    _require(
        receipt.get("output_project_projection") == expected_projection,
        "OVERLAY_R3_RECEIPT_INVALID",
        "R3 project projection differs",
    )
    rows = receipt.get("package_inventory")
    _require(
        type(rows) is list and _inventory_digest(rows) == contract.inventory_digest,
        "OVERLAY_R3_INVENTORY_SEAL_INVALID",
        "R3 package inventory digest differs",
    )
    normalized = _validate_package_rows(
        rows,
        expected_paths=contract.package_paths,
        namespace=R3_NAMESPACE,
        project_root=contract.project_root,
        package_mode=contract.package_mode,
        label="R3",
    )
    return (
        {
            "authority_root": str(contract.attempt_root),
            "host_receipt": _pin_mapping(contract.receipt),
            "source_project_static_tree": contract.project_tree.public(),
            "inventory_digest": contract.inventory_digest,
            "package_count": len(normalized),
            "project_relative_paths": [
                str(row["project_relative_path"]) for row in normalized
            ],
            "copy_policy": "exact_packages_only",
        },
        normalized,
    )


def _require_root_immutable(path: Path, label: str) -> None:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise PlanError("OVERLAY_AUTHORITY_INVALID", f"{label} is unavailable") from exc
    _require(
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_uid == 0
        and info.st_gid == 0
        and stat.S_IMODE(info.st_mode) & 0o222 == 0,
        "OVERLAY_AUTHORITY_INVALID",
        f"{label} is not root-owned immutable authority",
    )


def _type_strict_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(
            _type_strict_equal(actual[key], expected[key]) for key in expected
        )
    if type(expected) is list:
        return len(actual) == len(expected) and all(
            _type_strict_equal(left, right)
            for left, right in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


def _valid_file_reference(value: Any, *, path: str) -> bool:
    return (
        type(value) is dict
        and set(value) == {"path", "sha256", "size_bytes"}
        and value.get("path") == path
        and type(value.get("sha256")) is str
        and SHA256_RE.fullmatch(value["sha256"]) is not None
        and type(value.get("size_bytes")) is int
        and value["size_bytes"] > 0
    )


def _content_projection(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    files = sorted((dict(row) for row in rows), key=lambda row: str(row["path"]))
    return {
        "sha256": hashlib.sha256(canonical_json({"files": files})).hexdigest(),
        "file_count": len(files),
        "total_bytes": sum(int(row["size_bytes"]) for row in files),
    }


def _expected_r8_content_delta(
    r3_rows: Sequence[Mapping[str, Any]],
    r8_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    before = [
        {
            "path": row["project_relative_path"],
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
        }
        for row in r3_rows
    ]
    after = [
        *before,
        *(
            {
                "path": row["project_relative_path"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
            }
            for row in r8_rows
        ),
    ]
    return {
        "before_projection": _content_projection(before),
        "after_projection": _content_projection(after),
        "existing_file_count_unchanged": len(before),
        "added_project_relative_paths": list(R8_PACKAGE_PATHS),
        "existing_files_byte_identical": True,
        "exact_nine_package_delta": True,
    }


def _expected_r8_project_counts(
    config: Config,
    r8_rows: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Return the exact additive counts implied by the sealed R3 tree."""

    _require(
        config.r3.project_tree.directory_count is not None,
        "OVERLAY_R8_RECEIPT_INVALID",
        "R3 directory count is unavailable",
    )
    inherited_directories = {
        str(parent)
        for path in R3_PACKAGE_PATHS
        for parent in PurePosixPath(path).parents
        if str(parent) != "."
    }
    output_directories = {
        str(parent)
        for path in R8_PACKAGE_PATHS
        for parent in PurePosixPath(path).parents
        if str(parent) != "."
    }
    added_directories = output_directories - inherited_directories
    return {
        "file_count": config.r3.project_tree.file_count + len(R8_PACKAGE_PATHS),
        "directory_count": config.r3.project_tree.directory_count
        + len(added_directories),
        "total_bytes": config.r3.project_tree.total_bytes
        + sum(int(row["size_bytes"]) for row in r8_rows),
    }


def _validate_runtime_bindings(value: Any) -> None:
    _require(
        type(value) is dict and set(value) == R8_RUNTIME_BINDING_KEYS,
        "OVERLAY_R8_RECEIPT_INVALID",
        "R8 runtime bindings differ",
    )
    _require(
        value.get("engine") == r8_executor_contract.EXPECTED_ENGINE_VERSION
        and value.get("project") == str(r8_executor_contract.SANDBOX_PROJECT_FILE)
        and value.get("execution_manifest")
        == str(r8_executor_contract.SANDBOX_EXECUTION_PATH)
        and type(value.get("execution_manifest_sha256")) is str
        and SHA256_RE.fullmatch(value["execution_manifest_sha256"]) is not None
        and value.get("skeleton_object_path")
        == r8_executor_contract.SKELETON_OBJECT_PATH
        and value.get("mesh_object_path") == r8_executor_contract.MESH_OBJECT_PATH
        and _valid_file_reference(
            value.get("source_host_receipt"),
            path=str(r8_executor_contract.SANDBOX_SOURCE_RECEIPT_PATH),
        )
        and _valid_file_reference(
            value.get("commandlet"),
            path=str(r8_executor_contract.SANDBOX_COMMANDLET_PATH),
        ),
        "OVERLAY_R8_RECEIPT_INVALID",
        "R8 runtime fixed bindings differ",
    )
    source_fbx = value.get("source_fbx")
    _require(
        type(source_fbx) is list
        and len(source_fbx) == len(r8_executor_contract.CLIP_SPECS),
        "OVERLAY_R8_RECEIPT_INVALID",
        "R8 source FBX bindings differ",
    )
    for item, spec in zip(source_fbx, r8_executor_contract.CLIP_SPECS, strict=True):
        _require(
            type(item) is dict
            and set(item) == {"clip_id", "path", "sha256", "size_bytes"}
            and item.get("clip_id") == spec["clip_id"]
            and item.get("path")
            == str(
                r8_executor_contract.SANDBOX_FBX_ROOT / f"{spec['sequence_name']}.fbx"
            )
            and type(item.get("sha256")) is str
            and SHA256_RE.fullmatch(item["sha256"]) is not None
            and type(item.get("size_bytes")) is int
            and item["size_bytes"] > 0,
            "OVERLAY_R8_RECEIPT_INVALID",
            f"R8 source FBX binding differs: {spec['clip_id']}",
        )


def _validate_sequence_inspection(value: Any) -> None:
    try:
        r8_executor_contract._validate_sequence_inspection(value)
    except r8_executor_contract.ExecutorError as exc:
        raise PlanError(
            "OVERLAY_R8_RECEIPT_INVALID", "R8 sequence inspection differs"
        ) from exc


def _validate_r8(
    config: Config, r3_rows: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], str | None]:
    authority = config.r8_authority
    _require_directory_no_symlink(config.r8_published_parent, "R8 publication parent")
    if authority is None:
        if config.r8_published_parent.exists():
            unreviewed = sorted(
                entry.name
                for entry in os.scandir(config.r8_published_parent)
                if R8_ATTEMPT_RE.fullmatch(entry.name)
            )
            _require(
                not unreviewed,
                "OVERLAY_UNPINNED_AUTHORITY_PRESENT",
                "an unpinned R8 publication exists",
            )
        return (
            {
                "authority_ready": False,
                "namespace": R8_NAMESPACE,
                "package_count": len(R8_PACKAGE_PATHS),
                "project_relative_paths": list(R8_PACKAGE_PATHS),
                "copy_policy": "exact_packages_only",
            },
            "fresh_root_published_r8_animation_authority",
        )

    _require(
        authority.root.parent == config.r8_published_parent
        and R8_ATTEMPT_RE.fullmatch(authority.root.name) is not None
        and authority.host_receipt.path == authority.root / "host-receipt.json"
        and authority.host_receipt.pin.mode == 0o444
        and authority.runtime_receipt.path
        == authority.root / "evidence/makehuman-cc0-animation-runtime-receipt.json"
        and authority.runtime_receipt.pin.mode == 0o444,
        "OVERLAY_R8_PATH_INVALID",
        "R8 authority layout differs",
    )
    if config.require_root_owned_future_authorities:
        _require_root_immutable(authority.root, "R8 authority root")
    _require_directory_no_symlink(authority.root / "project", "R8 project root")
    _require_directory_no_symlink(authority.root / "evidence", "R8 evidence root")
    if config.require_root_owned_future_authorities:
        _require_root_immutable(authority.root / "project", "R8 project root")
        _require_root_immutable(authority.root / "evidence", "R8 evidence root")
    _require_safe_file_parent_chain(
        authority.root,
        authority.host_receipt.path,
        "R8 host receipt",
        require_root_owned_immutable=config.require_root_owned_future_authorities,
    )
    _require_safe_file_parent_chain(
        authority.root,
        authority.runtime_receipt.path,
        "R8 runtime receipt",
        require_root_owned_immutable=config.require_root_owned_future_authorities,
    )
    host = _read_document(
        authority.host_receipt,
        "R8 host receipt",
        require_root_owned=config.require_root_owned_future_authorities,
    )
    runtime = _read_document(
        authority.runtime_receipt,
        "R8 runtime receipt",
        require_root_owned=config.require_root_owned_future_authorities,
    )
    _require(
        set(host) == R8_HOST_KEYS
        and host.get("schema") == R8_HOST_SCHEMA
        and host.get("status") == R8_HOST_STATUS
        and host.get("accepted") is False
        and host.get("attempt_name") == authority.root.name
        and host.get("added_project_relative_paths") == list(R8_PACKAGE_PATHS),
        "OVERLAY_R8_RECEIPT_INVALID",
        "R8 host receipt differs",
    )
    bindings = host.get("bindings")
    digest_binding_keys = R8_HOST_BINDING_KEYS - {
        "engine_build_id",
        "r3_project_tree_digest",
        "buildplugin_tree_digest",
        "commandlet_receipt_content_digest",
    }
    _require(
        type(bindings) is dict
        and set(bindings) == R8_HOST_BINDING_KEYS
        and all(
            type(bindings.get(key)) is str
            and SHA256_RE.fullmatch(bindings[key]) is not None
            for key in digest_binding_keys
        )
        and type(bindings.get("engine_build_id")) is str
        and bindings["engine_build_id"].isdigit()
        and bindings.get("r3_project_tree_digest") == config.r3.project_tree.sha256
        and bindings.get("buildplugin_tree_digest")
        == config.buildplugin.projection_sha256
        and bindings.get("commandlet_receipt_content_digest")
        == runtime.get("content_digest"),
        "OVERLAY_R8_LINEAGE_INVALID",
        "R8 host lineage differs",
    )
    project_projection = host.get("project_projection")
    _require(
        type(project_projection) is dict
        and set(project_projection)
        == {"sha256", "file_count", "directory_count", "total_bytes"}
        and type(project_projection.get("sha256")) is str
        and SHA256_RE.fullmatch(project_projection["sha256"]) is not None
        and all(
            type(project_projection.get(key)) is int and project_projection[key] > 0
            for key in ("file_count", "directory_count", "total_bytes")
        ),
        "OVERLAY_R8_RECEIPT_INVALID",
        "R8 host project projection differs",
    )
    expected_host_claims = {
        "ue_animation_imported": True,
        "typed_notifies_authored_in_ue": True,
        "runtime_assets_authored": True,
        **r8_executor_contract.NEGATIVE_CLAIMS,
    }
    _require(
        _type_strict_equal(host.get("claims"), expected_host_claims),
        "OVERLAY_R8_RECEIPT_INVALID",
        "R8 host claims differ",
    )
    _require(
        set(runtime) == R8_RUNTIME_KEYS
        and runtime.get("schema_version") == R8_RUNTIME_SCHEMA
        and runtime.get("status") == R8_RUNTIME_STATUS
        and runtime.get("accepted") is False
        and runtime.get("error") is None
        and runtime.get("attempt_root") == str(r8_executor_contract.SANDBOX_WORK_ROOT)
        and runtime.get("project_root")
        == str(r8_executor_contract.SANDBOX_PROJECT_ROOT)
        and runtime.get("content_namespace") == r8_executor_contract.CONTENT_NAMESPACE,
        "OVERLAY_R8_RECEIPT_INVALID",
        "R8 runtime receipt differs",
    )
    _validate_runtime_bindings(runtime.get("bindings"))
    runtime_bindings = runtime["bindings"]
    _require(
        bindings.get("r8_host_receipt_sha256")
        == runtime_bindings["source_host_receipt"]["sha256"]
        and bindings.get("commandlet_result_receipt_sha256")
        == authority.runtime_receipt.pin.sha256,
        "OVERLAY_R8_LINEAGE_INVALID",
        "R8 host-to-runtime lineage differs",
    )
    _require(
        _type_strict_equal(
            runtime.get("returned_object_paths"),
            list(r8_executor_contract.EXPECTED_RETURNED_OBJECT_PATHS),
        )
        and _type_strict_equal(
            runtime.get("pipeline_policies"),
            [
                r8_executor_contract._pipeline_policy(spec["sequence_name"])
                for spec in r8_executor_contract.CLIP_SPECS
            ],
        )
        and _type_strict_equal(
            runtime.get("runtime_authoring_result"),
            r8_executor_contract.EXPECTED_RUNTIME_AUTHORING_RESULT,
        )
        and _type_strict_equal(
            runtime.get("asset_inventory"),
            sorted(
                r8_executor_contract.EXPECTED_INVENTORY,
                key=lambda item: item["object_path"],
            ),
        )
        and _type_strict_equal(
            runtime.get("gates"), r8_executor_contract.TERMINAL_GATE_EXPECTATIONS
        )
        and _type_strict_equal(
            runtime.get("claims"), r8_executor_contract.TERMINAL_CLAIMS
        ),
        "OVERLAY_R8_RECEIPT_INVALID",
        "R8 runtime terminal contract differs",
    )
    _validate_sequence_inspection(runtime.get("sequence_inspection"))
    _validate_package_rows(
        list(r3_rows),
        expected_paths=config.r3.package_paths,
        namespace=R3_NAMESPACE,
        project_root=authority.root / "project",
        package_mode=0o444,
        label="R8 inherited R3",
        require_root_owned=config.require_root_owned_future_authorities,
    )
    expected_assets = sorted(
        r8_executor_contract.EXPECTED_INVENTORY,
        key=lambda item: item["object_path"],
    )
    rows = _validate_package_rows(
        runtime.get("package_inventory"),
        expected_paths=R8_PACKAGE_PATHS,
        namespace=R8_NAMESPACE,
        project_root=authority.root / "project",
        package_mode=0o444,
        label="R8",
        expected_asset_inventory=expected_assets,
        require_root_owned=config.require_root_owned_future_authorities,
    )
    expected_project_counts = _expected_r8_project_counts(config, rows)
    _require(
        all(
            project_projection.get(key) == value
            for key, value in expected_project_counts.items()
        ),
        "OVERLAY_R8_RECEIPT_INVALID",
        "R8 host project projection counts differ",
    )
    _require(
        _type_strict_equal(
            runtime.get("project_content_delta"),
            _expected_r8_content_delta(r3_rows, rows),
        ),
        "OVERLAY_R8_RECEIPT_INVALID",
        "R8 project content delta differs",
    )
    return (
        {
            "authority_ready": True,
            "authority_root": str(authority.root),
            "host_receipt": _pin_mapping(authority.host_receipt),
            "runtime_receipt": _pin_mapping(authority.runtime_receipt),
            "namespace": R8_NAMESPACE,
            "package_count": len(rows),
            "project_relative_paths": list(R8_PACKAGE_PATHS),
            "copy_policy": "exact_packages_only",
            "inherited_r3_character_packages_byte_identical": True,
        },
        None,
    )


def _manifest_source_records(
    entries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in entries:
        record = {key: value for key, value in entry.items() if key != "authority_mode"}
        records.append(record)
    return records


def _plugin_projection(records: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    projected = []
    for record in records:
        if record.get("kind") == "directory":
            projected.append({"kind": "directory", "path": record.get("path")})
        else:
            projected.append(
                {
                    "kind": "file",
                    "path": record.get("path"),
                    "sha256": record.get("sha256"),
                    "size_bytes": record.get("size_bytes"),
                }
            )
    for record in sorted(
        projected, key=lambda item: (str(item["path"]), str(item["kind"]))
    ):
        raw = json.dumps(
            record,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", "strict")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _critical_public(contract: BuildPluginContract) -> dict[str, Any]:
    return {
        relative: pin.public()
        for relative, pin in sorted(contract.critical_files.items())
    }


def _payload_namespace(
    root: Path, *, require_root_owned: bool
) -> tuple[set[str], set[str]]:
    directories = {"."}
    files: set[str] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda entry: entry.name)
        except OSError as exc:
            raise PlanError(
                "OVERLAY_BUILDPLUGIN_PAYLOAD_INVALID",
                "BuildPlugin payload namespace cannot be scanned",
            ) from exc
        for entry in entries:
            path = Path(entry.path)
            info = os.lstat(path)
            relative = path.relative_to(root).as_posix()
            _require(
                not stat.S_ISLNK(info.st_mode),
                "OVERLAY_BUILDPLUGIN_PAYLOAD_INVALID",
                f"BuildPlugin payload contains a symlink: {relative}",
            )
            _require(
                not require_root_owned or (info.st_uid == 0 and info.st_gid == 0),
                "OVERLAY_AUTHORITY_INVALID",
                f"BuildPlugin payload is not root-owned: {relative}",
            )
            if stat.S_ISDIR(info.st_mode):
                _require(
                    stat.S_IMODE(info.st_mode) == 0o555,
                    "OVERLAY_BUILDPLUGIN_PAYLOAD_INVALID",
                    f"BuildPlugin directory mode differs: {relative}",
                )
                directories.add(relative)
                stack.append(path)
            elif stat.S_ISREG(info.st_mode):
                _require(
                    stat.S_IMODE(info.st_mode) == 0o444 and info.st_nlink == 1,
                    "OVERLAY_BUILDPLUGIN_PAYLOAD_INVALID",
                    f"BuildPlugin file mode or link count differs: {relative}",
                )
                files.add(relative)
            else:
                _fail(
                    "OVERLAY_BUILDPLUGIN_PAYLOAD_INVALID",
                    f"BuildPlugin payload contains a special file: {relative}",
                )
    return directories, files


def _valid_positive_pin(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == {"sha256", "size_bytes"}
        and type(value.get("sha256")) is str
        and SHA256_RE.fullmatch(value["sha256"]) is not None
        and type(value.get("size_bytes")) is int
        and value["size_bytes"] > 0
    )


def _valid_buildplugin_admin_publication(value: Any) -> bool:
    if type(value) is not dict or set(value) != {
        "authority_root",
        "authority_mode",
        "launcher",
        "receipt",
        "bootstrap_provenance",
        "admin_launcher_fd_required",
    }:
        return False
    launcher = value.get("launcher")
    receipt = value.get("receipt")
    bootstrap = value.get("bootstrap_provenance")
    return bool(
        value.get("authority_root") == str(BUILDPLUGIN_ADMIN_AUTHORITY_ROOT)
        and value.get("authority_mode") == "0555"
        and value.get("admin_launcher_fd_required") is True
        and type(launcher) is dict
        and set(launcher) == {"name", "path", "sha256", "size_bytes", "mode"}
        and launcher.get("name") == BUILDPLUGIN_ADMIN_LAUNCHER.name
        and launcher.get("path") == str(BUILDPLUGIN_ADMIN_LAUNCHER)
        and launcher.get("mode") == "0500"
        and _valid_positive_pin(
            {
                "sha256": launcher.get("sha256"),
                "size_bytes": launcher.get("size_bytes"),
            }
        )
        and type(receipt) is dict
        and set(receipt)
        == {
            "name",
            "path",
            "sha256",
            "size_bytes",
            "mode",
            "schema",
            "content_digest",
        }
        and receipt.get("name") == BUILDPLUGIN_ADMIN_RECEIPT.name
        and receipt.get("path") == str(BUILDPLUGIN_ADMIN_RECEIPT)
        and receipt.get("mode") == "0444"
        and receipt.get("schema") == BUILDPLUGIN_ADMIN_RECEIPT_SCHEMA
        and _valid_positive_pin(
            {
                "sha256": receipt.get("sha256"),
                "size_bytes": receipt.get("size_bytes"),
            }
        )
        and type(receipt.get("content_digest")) is str
        and SHA256_RE.fullmatch(receipt["content_digest"]) is not None
        and type(bootstrap) is dict
        and set(bootstrap) == {"core_review_audit_pin", "content_digest"}
        and _valid_positive_pin(bootstrap.get("core_review_audit_pin"))
        and type(bootstrap.get("content_digest")) is str
        and SHA256_RE.fullmatch(bootstrap["content_digest"]) is not None
    )


def _validate_buildplugin(
    config: Config,
) -> tuple[dict[str, Any], str | None]:
    contract = config.buildplugin
    authority = config.buildplugin_authority
    if authority is None:
        _require(
            not os.path.lexists(contract.root),
            "OVERLAY_UNPINNED_AUTHORITY_PRESENT",
            "an unpinned BuildPlugin authority exists",
        )
        return (
            {
                "authority_ready": False,
                "target": PLUGIN_TARGET,
                "policy": "replace_tree",
                "expected_authority_root": str(contract.root),
                "reviewed_source_path": str(contract.source_path),
                "expected_projection_sha256": contract.projection_sha256,
                "expected_inventory_sha256": contract.inventory_sha256,
                "expected_file_count": contract.file_count,
                "expected_directory_count": contract.directory_count,
                "expected_total_bytes": contract.total_bytes,
                "expected_critical_files": _critical_public(contract),
            },
            "reviewed_root_buildplugin_authority",
        )
    _require(
        authority.root == contract.root
        and authority.manifest.path == contract.root / "manifest.json"
        and authority.manifest.pin.mode == 0o444
        and authority.receipt.path == contract.root / "receipt.json"
        and authority.receipt.pin.mode == 0o444,
        "OVERLAY_BUILDPLUGIN_PATH_INVALID",
        "BuildPlugin authority layout differs",
    )
    if config.require_root_owned_future_authorities:
        _require_root_immutable(authority.root, "BuildPlugin authority root")
        _require_root_immutable(contract.payload, "BuildPlugin payload")
    _require_safe_file_parent_chain(
        authority.root,
        authority.manifest.path,
        "BuildPlugin manifest",
        require_root_owned_immutable=config.require_root_owned_future_authorities,
    )
    _require_safe_file_parent_chain(
        authority.root,
        authority.receipt.path,
        "BuildPlugin receipt",
        require_root_owned_immutable=config.require_root_owned_future_authorities,
    )
    manifest_raw = _read_pinned_file(
        authority.manifest,
        "BuildPlugin manifest",
        maximum_bytes=MAX_DOCUMENT_BYTES,
        require_root_owned=config.require_root_owned_future_authorities,
    )
    manifest = _strict_json(manifest_raw, "BuildPlugin manifest")
    receipt = _read_document(
        authority.receipt,
        "BuildPlugin receipt",
        require_root_owned=config.require_root_owned_future_authorities,
    )
    source = manifest.get("source")
    expected_source = {
        "path": str(contract.source_path),
        "projection_sha256": contract.projection_sha256,
        "inventory_sha256": contract.inventory_sha256,
        "file_count": contract.file_count,
        "directory_count": contract.directory_count,
        "total_bytes": contract.total_bytes,
    }
    _require(
        set(manifest) == BUILDPLUGIN_MANIFEST_KEYS
        and manifest.get("schema_version") == BUILDPLUGIN_MANIFEST_SCHEMA
        and type(source) is dict
        and source == expected_source,
        "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
        "BuildPlugin source projection differs",
    )
    expected_authority = {
        "root": str(contract.root),
        "payload": str(contract.payload),
        "directory_mode": "0555",
        "file_mode": "0444",
    }
    _require(
        manifest.get("authority") == expected_authority,
        "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
        "BuildPlugin authority binding differs",
    )
    _require(
        manifest.get("critical_files") == _critical_public(contract),
        "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
        "BuildPlugin critical-file contract differs",
    )
    entries = manifest.get("entries")
    _require(
        type(entries) is list,
        "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
        "BuildPlugin entries differ",
    )
    records = _manifest_source_records(entries)
    directory_count = 0
    file_count = 0
    total_bytes = 0
    paths: list[str] = []
    manifest_directories: set[str] = set()
    manifest_files: set[str] = set()
    for index, (entry, record) in enumerate(zip(entries, records, strict=True)):
        _require(
            type(entry) is dict,
            "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
            f"BuildPlugin entry {index} differs",
        )
        kind = record.get("kind")
        path_value = record.get("path")
        _require(
            kind in {"directory", "file"} and type(path_value) is str,
            "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
            f"BuildPlugin entry {index} shape differs",
        )
        if path_value == ".":
            _require(
                kind == "directory",
                "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
                "BuildPlugin root entry differs",
            )
            relative_parts: tuple[str, ...] = ()
        else:
            pure = PurePosixPath(path_value)
            _require(
                not pure.is_absolute()
                and pure.as_posix() == path_value
                and all(part not in {"", ".", ".."} for part in pure.parts)
                and "\\" not in path_value,
                "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
                f"BuildPlugin path is unsafe: {path_value}",
            )
            relative_parts = pure.parts
            paths.append(path_value)
        target = contract.payload.joinpath(*relative_parts)
        try:
            info = os.lstat(target)
        except OSError as exc:
            raise PlanError(
                "OVERLAY_BUILDPLUGIN_PAYLOAD_INVALID",
                f"BuildPlugin payload is missing: {path_value}",
            ) from exc
        if kind == "directory":
            directory_count += 1
            manifest_directories.add(path_value)
            _require(
                set(entry) == {"kind", "path", "source_mode", "authority_mode"}
                and entry.get("authority_mode") == "0555"
                and stat.S_ISDIR(info.st_mode)
                and not stat.S_ISLNK(info.st_mode)
                and stat.S_IMODE(info.st_mode) == 0o555,
                "OVERLAY_BUILDPLUGIN_PAYLOAD_INVALID",
                f"BuildPlugin directory differs: {path_value}",
            )
        else:
            file_count += 1
            manifest_files.add(path_value)
            _require(
                set(entry)
                == {
                    "kind",
                    "path",
                    "source_mode",
                    "authority_mode",
                    "size_bytes",
                    "sha256",
                }
                and entry.get("authority_mode") == "0444",
                "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
                f"BuildPlugin file entry differs: {path_value}",
            )
            size = entry.get("size_bytes")
            sha = entry.get("sha256")
            _require(
                type(size) is int
                and size > 0
                and type(sha) is str
                and SHA256_RE.fullmatch(sha) is not None,
                "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
                f"BuildPlugin file pin differs: {path_value}",
            )
            _read_pinned_file(
                PinnedFile(target, FilePin(sha, size, 0o444)),
                f"BuildPlugin payload {path_value}",
                require_root_owned=config.require_root_owned_future_authorities,
            )
            total_bytes += size
    observed_directories, observed_files = _payload_namespace(
        contract.payload,
        require_root_owned=config.require_root_owned_future_authorities,
    )
    entries_by_path = {
        str(entry["path"]): entry
        for entry in entries
        if type(entry) is dict and entry.get("kind") == "file"
    }
    for relative, pin in contract.critical_files.items():
        entry = entries_by_path.get(relative)
        _require(
            type(entry) is dict
            and entry.get("sha256") == pin.sha256
            and entry.get("size_bytes") == pin.size_bytes
            and entry.get("source_mode") == oct(pin.mode),
            "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
            f"BuildPlugin critical file differs: {relative}",
        )
    _assert_distinct_paths(paths, "BuildPlugin")
    _require(
        observed_directories == manifest_directories
        and observed_files == manifest_files
        and directory_count == contract.directory_count
        and file_count == contract.file_count
        and total_bytes == contract.total_bytes
        and hashlib.sha256(canonical_json(records)).hexdigest()
        == contract.inventory_sha256
        and _plugin_projection(records) == contract.projection_sha256,
        "OVERLAY_BUILDPLUGIN_MANIFEST_INVALID",
        "BuildPlugin complete inventory differs",
    )
    receipt_authority = receipt.get("authority")
    publisher = receipt.get("publisher")
    helper = publisher.get("helper") if type(publisher) is dict else None
    _require(
        set(receipt) == BUILDPLUGIN_RECEIPT_KEYS
        and receipt.get("schema_version") == BUILDPLUGIN_RECEIPT_SCHEMA
        and receipt.get("status") == BUILDPLUGIN_RECEIPT_STATUS
        and receipt.get("accepted") is True
        and receipt.get("source") == source
        and type(receipt_authority) is dict
        and set(receipt_authority)
        == {
            "root",
            "payload",
            "payload_projection_sha256",
            "manifest",
            "root_owned_nonwritable",
        }
        and receipt_authority.get("root") == str(contract.root)
        and receipt_authority.get("payload") == str(contract.payload)
        and receipt_authority.get("payload_projection_sha256")
        == contract.projection_sha256
        and receipt_authority.get("root_owned_nonwritable") is True
        and receipt_authority.get("manifest")
        == {
            "path": "manifest.json",
            "sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "size_bytes": len(manifest_raw),
        }
        and type(publisher) is dict
        and set(publisher) == {"helper", "interpreter"}
        and type(helper) is dict
        and set(helper) == {"path", "mode", "sha256", "size_bytes"}
        and helper.get("path") == str(BUILDPLUGIN_HELPER_PATH)
        and helper.get("mode") == "0500"
        and helper.get("sha256") == BUILDPLUGIN_HELPER_SHA256
        and helper.get("size_bytes") == BUILDPLUGIN_HELPER_SIZE_BYTES
        and publisher.get("interpreter") == BUILDPLUGIN_INTERPRETER
        and _valid_buildplugin_admin_publication(receipt.get("admin_publication"))
        and receipt.get("policy") == BUILDPLUGIN_POLICY
        and receipt.get("claims") == BUILDPLUGIN_NEGATIVE_CLAIMS,
        "OVERLAY_BUILDPLUGIN_RECEIPT_INVALID",
        "BuildPlugin receipt differs",
    )
    return (
        {
            "authority_ready": True,
            "target": PLUGIN_TARGET,
            "policy": "replace_tree",
            "authority_root": str(contract.root),
            "payload": str(contract.payload),
            "manifest": _pin_mapping(authority.manifest),
            "receipt": _pin_mapping(authority.receipt),
            "projection_sha256": contract.projection_sha256,
            "inventory_sha256": contract.inventory_sha256,
            "file_count": contract.file_count,
            "directory_count": contract.directory_count,
            "total_bytes": contract.total_bytes,
        },
        None,
    )


def _validate_attempt(attempt_name: str, config: Config) -> Path:
    _require(
        type(attempt_name) is str and ATTEMPT_RE.fullmatch(attempt_name) is not None,
        "OVERLAY_ATTEMPT_INVALID",
        "attempt name differs from the closed contract",
    )
    _require(
        config.run_parent.is_absolute(),
        "OVERLAY_ATTEMPT_INVALID",
        "run parent is unavailable",
    )
    _require_directory_no_symlink(config.run_parent, "run parent")
    attempt = config.run_parent / attempt_name
    _require(
        attempt.parent == config.run_parent,
        "OVERLAY_ATTEMPT_INVALID",
        "attempt is not a direct child",
    )
    _require(
        not os.path.lexists(attempt),
        "OVERLAY_ATTEMPT_NOT_FRESH",
        "attempt already exists",
    )
    return attempt


def build_plan(attempt_name: str, *, config: Config | None = None) -> PreparedPlan:
    selected = PRODUCTION_CONFIG if config is None else config
    attempt = _validate_attempt(attempt_name, selected)
    parent = _validate_parent(selected)
    r3, r3_rows = _validate_r3(selected)

    additive_paths = [*R3_PACKAGE_PATHS, *R8_PACKAGE_PATHS]
    for path in R3_PACKAGE_PATHS:
        _safe_package_path(path, R3_NAMESPACE, "R3 target path")
    for path in R8_PACKAGE_PATHS:
        _safe_package_path(path, R8_NAMESPACE, "R8 target path")
    _assert_distinct_paths(additive_paths, "combined additive partitions")
    _require(
        all(
            not os.path.lexists(selected.parent.root / "project" / path)
            for path in additive_paths
        ),
        "OVERLAY_PARENT_NAMESPACE_COLLISION",
        "an additive target already exists in h",
    )

    r8, r8_blocker = _validate_r8(selected, r3_rows)
    plugin, plugin_blocker = _validate_buildplugin(selected)
    blockers = [
        blocker for blocker in (r8_blocker, plugin_blocker) if blocker is not None
    ]
    status = BLOCKED_STATUS if blockers else READY_STATUS
    report = seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "status": status,
            "accepted": False,
            "mode": MODE,
            "attempt_name": attempt_name,
            "attempt_root": str(attempt),
            "base_h_authority": parent,
            "r3_character_overlay": r3,
            "r8_animation_overlay": r8,
            "plugin_replacement": plugin,
            "provider_transition": {
                "source_provider": SOURCE_PROVIDER,
                "target_provider": TARGET_PROVIDER,
                "activation_argument": "-VistaCharacterProvider=makehuman_cc0_r8",
                "runtime_activation_verified": False,
            },
            "expected_child_delta": {
                "additive_package_count": len(additive_paths),
                "r3_character_package_count": len(R3_PACKAGE_PATHS),
                "r8_animation_package_count": len(R8_PACKAGE_PATHS),
                "additive_project_relative_paths": additive_paths,
                "map_policy": "byte_identical_during_planning",
                "plugin_policy": "whole_subtree_replacement",
            },
            "blockers": blockers,
            "claims": PLAN_CLAIMS,
            "legal_scope": LEGAL_SCOPE,
            "security": {
                "default_zero_write": True,
                "writes_performed": False,
                "will_run_unreal": False,
                "will_run_blender": False,
                "will_use_gpu": False,
                "will_change_services": False,
                "caller_path_or_authority_overrides": False,
                "quarantined_development_animation_fallback": False,
                "full_parent_tree_copy_or_rescan": False,
            },
            "next_gate": (
                "install_and_pin_missing_root_authorities"
                if blockers
                else "review_separate_append_only_materializer_spec"
            ),
        }
    )
    return PreparedPlan(report=report)


RUN_PARENT = Path("/data/sysx/vista-world/runs/vista-action-world-r1")
H_ROOT = RUN_PARENT / "hssd-r2-citysample-live-r5-20260830h"
R3_ROOT = RUN_PARENT / "makehuman-cc0-ue-import-r3-20260829"
R8_PUBLISHED_PARENT = Path("/data/vista-published/vista-action-world-r1")
BUILDPLUGIN_ROOT = Path("/data/vista-authorities/vista-r8-ue-animation-buildplugin-r1")

PRODUCTION_CONFIG = Config(
    run_parent=RUN_PARENT,
    parent=ParentContract(
        root=H_ROOT,
        complete=PinnedFile(
            H_ROOT / "hssd-r2-citysample-live-host-complete.json",
            FilePin(
                "52ec26972109b0b2ca195607f8536b845c56b2c413e50d5a207609452e46211a",
                15_176,
                0o600,
            ),
        ),
        combined=PinnedFile(
            H_ROOT / "human-visual-demo-combined-receipt.json",
            FilePin(
                "869c8247e975cd79af9be5a7cca4dc169b2de8b7b3badf673ec3f93f425bdc48",
                28_155,
                0o600,
            ),
        ),
        host=PinnedFile(
            H_ROOT / "hssd-r2-citysample-live-host-receipt.json",
            FilePin(
                "ec35ebc8aa6989fa3486207866779d5ff1898ecb2116bf7a4a0f9bf652a73848",
                28_565,
                0o600,
            ),
        ),
        project=PinnedFile(
            H_ROOT / "project" / PROJECT_DESCRIPTOR_NAME,
            FilePin(
                "fe11c7e48eb895eec74e48868fc458a24a2290e826f8cbe75edea0e8ba8b674a",
                522,
                0o600,
            ),
        ),
        map_package=PinnedFile(
            H_ROOT / "project" / MAP_RELATIVE_PATH,
            FilePin(
                "1fda153459fea9845cab969b9802ce418bdde51bdbf6884ccd17c77b796dd588",
                682_737,
                0o600,
            ),
        ),
        failure_marker=H_ROOT / "hssd-r2-citysample-live-host-failure.json",
        tree=TreeProjection(
            "74846d5a0afeb7f72ee3b21bbe965afd46968a4b16e60ca9dff08d665c380376",
            2_453,
            None,
            9_153_718_809,
        ),
    ),
    r3=R3Contract(
        attempt_root=R3_ROOT,
        project_root=R3_ROOT / "project",
        receipt=PinnedFile(
            R3_ROOT / "makehuman-cc0-import-host-receipt.json",
            FilePin(
                "ef7c198ed1726b9c1857fd63c2a8ba93e7fce0e5f82f2b566152890c76d852d7",
                48_560,
                0o600,
            ),
        ),
        project_tree=TreeProjection(
            "b8a116993c3f1d7a9cae6fb93f1fe247e973c92d2ab90e564993cb406d7f40f0",
            24,
            11,
            43_545_997,
        ),
        inventory_digest=(
            "07512786e035004297dbc08162411370d26b69b92a0ee57a4f23bc410b508929"
        ),
        package_paths=R3_PACKAGE_PATHS,
        package_mode=0o600,
    ),
    r8_published_parent=R8_PUBLISHED_PARENT,
    r8_authority=None,
    buildplugin=BuildPluginContract(
        root=BUILDPLUGIN_ROOT,
        source_path=(RUN_PARENT / "vista-r8-ue-animation-buildplugin-dev-20260830c"),
        projection_sha256=(
            "69153cd676ac35579115d1be9c8ced7d86c70beab7f8adb681ad7b8d373ae48e"
        ),
        inventory_sha256=(
            "cad2d8f0481934cc1565c3cad0dbad041d293795cf31ea420a6a646d8c2b46b2"
        ),
        file_count=241,
        directory_count=32,
        total_bytes=51_661_522,
        critical_files={
            "VistaPlayableHome.uplugin": FilePin(
                "eb33ebafcf959b7050b32081db4f2a9ca75303b98afaa70c4ecc202abb63d1f0",
                891,
                0o644,
            ),
            "Binaries/Linux/UnrealEditor.modules": FilePin(
                "1e3a4969992d7b580ddd45242b4887189be5147f75e80a40e8d58461d28eb601",
                183,
                0o644,
            ),
            "Binaries/Linux/libUnrealEditor-VistaPlayableHome.so": FilePin(
                "ac61ed119f1bdae685b8176a2a14c3e258c7a00164e1b09476206daad8507f78",
                1_506_288,
                0o755,
            ),
            "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so": FilePin(
                "cb15bda09c1670e9b27b539c8027170996ef5824f273757b069a21de1e652849",
                532_000,
                0o755,
            ),
        },
    ),
    buildplugin_authority=None,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit the fixed, zero-write h -> CC0 R8 overlay plan."
    )
    parser.add_argument("--attempt-name", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        prepared = build_plan(args.attempt_name)
    except PlanError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(prepared.raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
