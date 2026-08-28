"""Plan or materialize the pinned HSSD six-room private-research profile.

Dry-run is the default and performs no writes.  ``--execute`` is the only mode
that creates a fresh append-only output directory and invokes the fixed Blender
worker.  No caller-selected script, asset subset, network source, or fallback is
accepted.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import pathlib
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.blender.vista_playable_home_hssd import glb_transport  # noqa: E402
from tools.blender.vista_playable_home_hssd import planner as hssd  # noqa: E402
PLAN_SCHEMA = "simworld.vista.hssd-private-research-forge-plan/v1"
SCENE_PLAN_SCHEMA = "simworld.vista.hssd-private-research-scene-plan/v1"
ASSET_RECEIPT_SCHEMA = "simworld.vista.hssd-private-research-asset-receipt/v1"
RESULT_SCHEMA = "simworld.vista.hssd-private-research-forge-result/v1"
PROFILE_SCHEMA_VERSION = (
    "simworld.vista.playable-home-hssd-private-research-profile/v1"
)

PINNED_PROFILE_CONTENT_DIGEST = (
    "4b76e178ab1a3043d6adda6fe5786a5111f58523f4f8a23eb9cc2c82d883e8d3"
)
PINNED_PROFILE_SHA256 = (
    "45085a4c3153c204cde92045af84cc1cc4f5c679bc881057de5b8d0ffeaddd24"
)
PINNED_HOUSE_SHA256 = "ccdf385b4ec8b88221ccd5c68eb5553fb7186e5aa5e87095176e1c3c62fec45f"
PINNED_DATASET_REVISION = "4369cb9876214c7fbebcf552eb532380e4d287e4"
PINNED_DATASET_README_SHA256 = (
    "4509914d584031173390bf5f41722ec25e19de3f1e0ea54a423eadf63073d49c"
)
PINNED_BLENDER_VERSION = (4, 5, 8)
PINNED_BLENDER_SHA256 = (
    "86b39e16cf8043a93de6b4ac5e23399d790f662c644573f600398a3c3bd121eb"
)
PINNED_NODE_SHA256 = "81925c0995b5c1427b5d538e6a90ca2fdc4daffb786b09af749beaf7369d4e90"
PINNED_BASIS_JS_SHA256 = (
    "8478b5b6d6b74e7d3082b89f6417321d8d1dc0307f2b30d4484bb11b441696a1"
)
PINNED_BASIS_WASM_SHA256 = (
    "6cf17dc889352c42e9acf8897107978d127005fe3386c36a0e3845e27967630a"
)
MAXIMUM_AXIS_SCALE_ANISOTROPY = 2.75
MINIMUM_UNIFORM_SCALE = 0.10
MAXIMUM_UNIFORM_SCALE = 10.0
EXPECTED_SOURCE_COUNT = 26
EXPECTED_PLACEMENT_COUNT = 60
EXPECTED_ARTICULATION_ROLES = frozenset(
    {"fridge", "desk", "nightstand", "wardrobe", "stove"}
)
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
BLENDER_TIMEOUT_SECONDS = 3 * 60 * 60

PROFILE_PATH = (
    REPOSITORY_ROOT
    / "world_packs"
    / "vista_playable_home_r1"
    / "visual_profiles"
    / "hssd_private_research_r1.json"
)
HOUSE_PATH = REPOSITORY_ROOT / "world_packs" / "vista_playable_home_r1" / "house.json"
WORKER_PATH = pathlib.Path(__file__).resolve().with_name("blender_worker.py")
DEFAULT_HSSD_ROOT = pathlib.Path("/mnt/NAS2/yhliu/habitat_data/versioned_data/hssd-hab")
DEFAULT_BLENDER = pathlib.Path("/home/yhliu/.local/opt/blender-4.5.8-linux-x64/blender")
DEFAULT_NODE = pathlib.Path("/home/yhliu/.local/opt/node/bin/node")
DEFAULT_BASIS_JS = pathlib.Path(
    "/home/yhliu/judge-project/node_modules/three/examples/jsm/libs/basis/basis_transcoder.js"
)
DEFAULT_BASIS_WASM = pathlib.Path(
    "/home/yhliu/judge-project/node_modules/three/examples/jsm/libs/basis/basis_transcoder.wasm"
)

SOURCE_FILES = (
    REPOSITORY_ROOT / "tools/blender/vista_playable_home_hssd/basisu_decode.mjs",
    REPOSITORY_ROOT / "tools/blender/vista_playable_home_hssd/build.py",
    REPOSITORY_ROOT / "tools/blender/vista_playable_home_hssd/glb_transport.py",
    REPOSITORY_ROOT / "tools/blender/vista_playable_home_hssd/planner.py",
    REPOSITORY_ROOT / "tools/worlds/vista_playable_home_hssd_private_research.py",
    pathlib.Path(__file__).resolve().with_name("__init__.py"),
    pathlib.Path(__file__).resolve().with_name("__main__.py"),
    WORKER_PATH,
    pathlib.Path(__file__).resolve(),
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,255}$")
_PROHIBITED_PLAN_KEYS = frozenset(
    {
        "script",
        "script_path",
        "command",
        "shell_command",
        "python_code",
        "network_url",
        "download_url",
        "auth_token",
        "access_token",
        "password",
        "secret",
    }
)


class ForgeError(RuntimeError):
    """Stable failure from the private-research forge."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise ForgeError(code, message)


def canonical_json(value: Any, *, newline: bool = True) -> bytes:
    try:
        raw = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ForgeError(
            "FORGE_JSON_INVALID", "value is not finite canonical JSON"
        ) from exc
    return raw + (b"\n" if newline else b"")


def content_digest(value: Mapping[str, Any]) -> str:
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(dict(value))
    sealed["content_digest"] = content_digest(sealed)
    return sealed


def _reject_constant(value: str) -> None:
    _fail("FORGE_JSON_NON_FINITE", f"JSON constant {value!r} is prohibited")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("FORGE_JSON_DUPLICATE_KEY", f"duplicate object key: {key}")
        result[key] = value
    return result


def load_json(
    path: pathlib.Path, *, maximum_bytes: int = 64 * 1024 * 1024
) -> dict[str, Any]:
    seal = seal_regular_file(
        path, label=path.name, capture=True, maximum_bytes=maximum_bytes
    )
    assert seal.raw is not None
    try:
        parsed = json.loads(
            seal.raw.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except ForgeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ForgeError(
            "FORGE_JSON_INVALID", f"invalid UTF-8 JSON: {path.name}"
        ) from exc
    if type(parsed) is not dict:
        _fail("FORGE_JSON_INVALID", f"JSON root must be an object: {path.name}")
    return parsed


def _stat_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IMODE(metadata.st_mode),
    )


@dataclass(frozen=True)
class FileSeal:
    path: pathlib.Path
    sha256: str
    size_bytes: int
    raw: bytes | None = None


def seal_regular_file(
    path: pathlib.Path,
    *,
    label: str,
    expected_sha256: str | None = None,
    executable: bool = False,
    capture: bool = False,
    maximum_bytes: int | None = None,
) -> FileSeal:
    candidate = pathlib.Path(path)
    if not candidate.is_absolute() or ".." in candidate.parts:
        _fail("SOURCE_PATH_INVALID", f"{label} must be an absolute traversal-free path")
    descriptor = -1
    captured = bytearray() if capture else None
    digest = hashlib.sha256()
    total = 0
    try:
        before = os.lstat(candidate)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            _fail("SOURCE_INVALID", f"{label} must be a single-link regular file")
        if executable and not before.st_mode & stat.S_IXUSR:
            _fail("SOURCE_INVALID", f"{label} must be executable")
        descriptor = os.open(
            candidate,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if _stat_identity(opened) != _stat_identity(before):
            _fail("SOURCE_CHANGED", f"{label} changed while opening")
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            total += len(block)
            if maximum_bytes is not None and total > maximum_bytes:
                _fail("SOURCE_TOO_LARGE", f"{label} exceeds the byte limit")
            digest.update(block)
            if captured is not None:
                captured.extend(block)
        after = os.fstat(descriptor)
        after_path = os.lstat(candidate)
        if _stat_identity(after) != _stat_identity(opened) or _stat_identity(
            after_path
        ) != _stat_identity(opened):
            _fail("SOURCE_CHANGED", f"{label} changed while reading")
    except ForgeError:
        raise
    except OSError as exc:
        raise ForgeError("SOURCE_UNREADABLE", f"unable to read {label}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    observed = digest.hexdigest()
    if expected_sha256 is not None and observed != expected_sha256:
        _fail("SOURCE_HASH_MISMATCH", f"{label} SHA-256 drifted")
    return FileSeal(
        candidate, observed, total, bytes(captured) if captured is not None else None
    )


def _canonical_directory(path: pathlib.Path, *, label: str) -> pathlib.Path:
    candidate = pathlib.Path(path)
    if not candidate.is_absolute() or ".." in candidate.parts:
        _fail(
            "DIRECTORY_PATH_INVALID", f"{label} must be an absolute traversal-free path"
        )
    try:
        metadata = os.lstat(candidate)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ForgeError("DIRECTORY_UNAVAILABLE", f"{label} is unavailable") from exc
    if not stat.S_ISDIR(metadata.st_mode) or resolved != candidate:
        _fail(
            "DIRECTORY_PATH_INVALID",
            f"{label} must be a canonical non-symlink directory",
        )
    return candidate


def _validate_output_destination(path: pathlib.Path) -> pathlib.Path:
    candidate = pathlib.Path(path)
    if (
        not candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.name in {"", ".", ".."}
    ):
        _fail(
            "OUTPUT_PATH_INVALID",
            "output root must be an absolute traversal-free new directory",
        )
    parent = _canonical_directory(candidate.parent, label="output parent")
    target = parent / candidate.name
    for ancestor in (parent, *parent.parents):
        git_marker = ancestor / ".git"
        try:
            os.lstat(git_marker)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ForgeError(
                "OUTPUT_PATH_INVALID", "unable to inspect Git containment"
            ) from exc
        _fail(
            "OUTPUT_INSIDE_GIT_PROHIBITED",
            "private binary output must be outside every Git worktree",
        )
    try:
        os.lstat(target)
    except FileNotFoundError:
        return target
    except OSError as exc:
        raise ForgeError(
            "OUTPUT_PATH_INVALID", "unable to inspect output root"
        ) from exc
    _fail("OUTPUT_ALREADY_EXISTS", "append-only output root must not exist")


def _prepare_output_root(path: pathlib.Path) -> pathlib.Path:
    target = _validate_output_destination(path)
    try:
        os.mkdir(target, PRIVATE_DIRECTORY_MODE)
    except OSError as exc:
        raise ForgeError(
            "OUTPUT_CREATE_FAILED", "could not create fresh append-only output root"
        ) from exc
    return target


def _write_exclusive(path: pathlib.Path, raw: bytes) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            PRIVATE_FILE_MODE,
        )
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("OUTPUT_WRITE_FAILED", f"short write: {path.name}")
            view = view[written:]
        os.fsync(descriptor)
    except ForgeError:
        raise
    except OSError as exc:
        raise ForgeError(
            "OUTPUT_WRITE_FAILED", f"could not create {path.name}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _relative_source_path(path: pathlib.Path) -> str:
    try:
        return path.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError as exc:
        raise ForgeError(
            "BUILDER_SOURCE_INVALID", "builder source escaped the repository"
        ) from exc


def _safe_relative(value: str, *, label: str) -> pathlib.PurePosixPath:
    candidate = pathlib.PurePosixPath(value)
    if (
        candidate.is_absolute()
        or "\\" in value
        or "%" in value
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        _fail("RELATIVE_PATH_INVALID", f"unsafe relative path for {label}")
    return candidate


def _scan_closed(value: Any, *, path: str = "$") -> None:
    if type(value) is dict:
        for key, child in value.items():
            normalized = key.strip().lower().replace("-", "_")
            if normalized in _PROHIBITED_PLAN_KEYS:
                _fail("PLAN_PROHIBITED_FIELD", f"prohibited plan field at {path}.{key}")
            _scan_closed(child, path=f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _scan_closed(child, path=f"{path}[{index}]")
    elif type(value) is float and not math.isfinite(value):
        _fail("PLAN_NON_FINITE", f"non-finite value at {path}")


@dataclass(frozen=True)
class ForgeConfig:
    hssd_root: pathlib.Path
    output_root: pathlib.Path
    blender: pathlib.Path = DEFAULT_BLENDER
    node: pathlib.Path = DEFAULT_NODE
    basis_js: pathlib.Path = DEFAULT_BASIS_JS
    basis_wasm: pathlib.Path = DEFAULT_BASIS_WASM
    license_accept: str = "CC-BY-NC-4.0"
    execute: bool = False


@dataclass(frozen=True)
class ForgePreflight:
    config: ForgeConfig
    profile: Mapping[str, Any]
    house: Mapping[str, Any]
    scene_plan: Mapping[str, Any]
    build_plan: Mapping[str, Any]
    asset_jobs: tuple[Mapping[str, Any], ...]


def _verify_pinned_contract_identity(
    *, validate_schema: bool
) -> tuple[
    dict[str, Any], dict[str, Any], list[dict[str, Any]]
]:
    profile_seal = seal_regular_file(
        PROFILE_PATH,
        label="pinned HSSD profile",
        expected_sha256=PINNED_PROFILE_SHA256,
        capture=True,
        maximum_bytes=4 * 1024 * 1024,
    )
    house_seal = seal_regular_file(
        HOUSE_PATH,
        label="pinned HouseSpec",
        expected_sha256=PINNED_HOUSE_SHA256,
        capture=True,
        maximum_bytes=8 * 1024 * 1024,
    )
    assert profile_seal.raw is not None and house_seal.raw is not None
    try:
        profile = json.loads(profile_seal.raw.decode("utf-8"))
        house = json.loads(house_seal.raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ForgeError(
            "CONTRACT_JSON_INVALID", "pinned profile or HouseSpec is invalid"
        ) from exc
    if type(profile) is not dict or type(house) is not dict:
        _fail("CONTRACT_JSON_INVALID", "pinned profile and HouseSpec must be objects")
    if validate_schema:
        # Keep jsonschema outside Blender's embedded Python.  The host validates
        # the closed Git contract before it writes a plan; the worker rechecks
        # the same pinned bytes and the closed plan without importing host-only
        # dependencies.
        from tools.worlds import vista_playable_home_hssd_private_research

        try:
            vista_playable_home_hssd_private_research.validate_profile(
                profile, house
            )
        except (
            vista_playable_home_hssd_private_research.HssdPrivateResearchProfileError
        ) as exc:
            raise ForgeError("PROFILE_CONTRACT_INVALID", str(exc)) from exc
    if profile.get("content_digest") != PINNED_PROFILE_CONTENT_DIGEST:
        _fail(
            "PROFILE_IDENTITY_MISMATCH",
            "checked-in profile content digest is not the approved revision",
        )
    source_receipts = [
        {
            "path": _relative_source_path(PROFILE_PATH),
            "sha256": profile_seal.sha256,
            "bytes": profile_seal.size_bytes,
        },
        {
            "path": _relative_source_path(HOUSE_PATH),
            "sha256": house_seal.sha256,
            "bytes": house_seal.size_bytes,
        },
    ]
    return profile, house, source_receipts


def _verify_checked_in_contracts() -> tuple[
    dict[str, Any], dict[str, Any], list[dict[str, Any]]
]:
    return _verify_pinned_contract_identity(validate_schema=True)


def _verify_toolchain(config: ForgeConfig) -> dict[str, Any]:
    blender = seal_regular_file(
        config.blender,
        label="Blender binary",
        expected_sha256=PINNED_BLENDER_SHA256,
        executable=True,
    )
    node = seal_regular_file(
        config.node,
        label="Node binary",
        expected_sha256=PINNED_NODE_SHA256,
        executable=True,
    )
    basis_js = seal_regular_file(
        config.basis_js,
        label="Basis transcoder JS",
        expected_sha256=PINNED_BASIS_JS_SHA256,
    )
    basis_wasm = seal_regular_file(
        config.basis_wasm,
        label="Basis transcoder WASM",
        expected_sha256=PINNED_BASIS_WASM_SHA256,
    )
    source_files = []
    for path in SOURCE_FILES:
        receipt = seal_regular_file(path.resolve(), label=path.name)
        source_files.append(
            {
                "path": _relative_source_path(path.resolve()),
                "sha256": receipt.sha256,
                "bytes": receipt.size_bytes,
            }
        )
    return {
        "blender": {
            "version": ".".join(str(value) for value in PINNED_BLENDER_VERSION),
            "sha256": blender.sha256,
            "bytes": blender.size_bytes,
            "version_enforcement": "worker_requires_exact_bpy_app_version",
            "dry_run_version_probe": False,
        },
        "node": {"sha256": node.sha256, "bytes": node.size_bytes},
        "basis_transcoder": {
            "distribution": "three",
            "distribution_version": "0.185.1",
            "javascript_sha256": basis_js.sha256,
            "javascript_bytes": basis_js.size_bytes,
            "wasm_sha256": basis_wasm.sha256,
            "wasm_bytes": basis_wasm.size_bytes,
            "basis_universal_license": "Apache-2.0",
            "three_license": "MIT",
        },
        "builder_sources": source_files,
    }


def _load_catalog_semantic_rows(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    try:
        semantics_path = hssd._contained_file(
            root,
            "metadata/hssd_obj_semantics_condensed.csv",
            "HSSD semantics",
        )
        fields, rows = hssd._read_csv_rows(semantics_path)
    except hssd.HssdBindingError as exc:
        raise ForgeError("HSSD_DATASET_INVALID", str(exc)) from exc
    id_field = next(
        (field for field in fields if field.strip().casefold() in {"object hash", "id"}),
        None,
    )
    condensed_field = next(
        (field for field in fields if "condensed" in field.casefold()), None
    )
    primary_field = next(
        (
            field
            for field in fields
            if field != condensed_field and "primary semantic category" in field.casefold()
        ),
        None,
    )
    if id_field is None or condensed_field is None or primary_field is None:
        _fail(
            "HSSD_CATALOG_PROVENANCE_INVALID",
            "semantic catalog lacks exact id/condensed/primary fields",
        )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        model_id = str(row.get(id_field, "")).strip().casefold()
        if not model_id:
            continue
        if model_id in result:
            _fail(
                "HSSD_CATALOG_PROVENANCE_INVALID",
                f"duplicate semantic catalog model: {model_id}",
            )
        result[model_id] = {
            "semantic_condensed_category": str(
                row.get(condensed_field, "")
            ).strip(),
            "semantic_primary_category": str(row.get(primary_field, "")).strip(),
        }
    return result


def _verify_dataset_and_sources(
    profile: Mapping[str, Any], hssd_root: pathlib.Path
) -> tuple[dict[str, Any], ...]:
    root = _canonical_directory(hssd_root, label="HSSD root")
    try:
        dataset = hssd.dataset_identity(
            root, expected_readme_sha256=PINNED_DATASET_README_SHA256
        )
    except hssd.HssdBindingError as exc:
        raise ForgeError("HSSD_DATASET_INVALID", str(exc)) from exc
    profile_dataset = profile["dataset"]
    if (
        dataset.get("dataset") != profile_dataset.get("name")
        or dataset.get("project_url") != profile_dataset.get("project_url")
        or dataset.get("dataset_revision") != PINNED_DATASET_REVISION
        or dataset.get("dataset_revision") != profile_dataset.get("dataset_revision")
        or dataset.get("readme_relpath") != profile_dataset.get("readme_relpath")
        or dataset.get("readme_sha256") != PINNED_DATASET_README_SHA256
        or dataset.get("readme_sha256") != profile_dataset.get("readme_sha256")
        or dataset.get("license") != profile_dataset.get("license")
        or dataset.get("license", {}).get("spdx") != "CC-BY-NC-4.0"
    ):
        _fail(
            "HSSD_DATASET_IDENTITY_MISMATCH",
            "local HSSD identity/license differs from the profile",
        )

    source_assets = profile["source_assets"]
    if len(source_assets) != EXPECTED_SOURCE_COUNT:
        _fail(
            "HSSD_SOURCE_COUNT_INVALID",
            f"exactly {EXPECTED_SOURCE_COUNT} unique sources are required",
        )
    try:
        _semantics, catalog_models = hssd._load_metadata(root)
    except hssd.HssdBindingError as exc:
        raise ForgeError("HSSD_DATASET_INVALID", str(exc)) from exc
    catalog_semantics = _load_catalog_semantic_rows(root)
    catalog_receipts = {
        item["source_asset_id"]: item
        for item in profile["catalog_semantic_receipts"]
    }
    if len(catalog_receipts) != EXPECTED_SOURCE_COUNT:
        _fail(
            "HSSD_CATALOG_PROVENANCE_INVALID",
            "catalog semantic receipt coverage is not closed",
        )
    jobs: list[dict[str, Any]] = []
    for source in source_assets:
        model_id = source["model_id"]
        if not _MODEL_ID_RE.fullmatch(model_id):
            _fail("HSSD_MODEL_ID_INVALID", "source model ID is invalid")
        try:
            glb_path = hssd._contained_file(
                root, source["render_asset_relpath"], "HSSD render asset"
            )
            config_path = hssd._contained_file(
                root, source["object_config_relpath"], "HSSD object config"
            )
            if hssd.sha256_file(glb_path) != source["render_asset_sha256"]:
                _fail(
                    "HSSD_SOURCE_HASH_MISMATCH",
                    f"render asset drift: {source['source_asset_id']}",
                )
            if hssd.sha256_file(config_path) != source["object_config_sha256"]:
                _fail(
                    "HSSD_SOURCE_HASH_MISMATCH",
                    f"object config drift: {source['source_asset_id']}",
                )
            object_config = hssd._load_json(config_path)
            if (
                object_config.get("render_asset") != f"{model_id}.glb"
                or object_config.get("up") != [0.0, 1.0, 0.0]
                or object_config.get("front") != [0.0, 0.0, -1.0]
            ):
                _fail(
                    "HSSD_OBJECT_CONFIG_INVALID",
                    f"object config drift: {source['source_asset_id']}",
                )
            model = catalog_models.get(model_id)
            semantic_row = catalog_semantics.get(model_id)
            receipt = catalog_receipts.get(source["source_asset_id"])
            if (
                not model
                or not semantic_row
                or not receipt
                or not str(model.get("aligned.dims", "")).strip()
            ):
                _fail(
                    "HSSD_CATALOG_PROVENANCE_INVALID",
                    f"catalog identity unavailable: {source['source_asset_id']}",
                )
            catalog_has_multiple_objects = (
                str(model.get("hasMultipleObjects", "")).strip().casefold() == "true"
            )
            observed_catalog_receipt = {
                "source_asset_id": source["source_asset_id"],
                "model_id": model_id,
                "catalog_name": str(model.get("name", "")),
                "catalog_wnsynsetkey": str(model.get("wnsynsetkey", "")),
                "semantic_condensed_category": semantic_row[
                    "semantic_condensed_category"
                ],
                "semantic_primary_category": semantic_row[
                    "semantic_primary_category"
                ],
                "catalog_has_multiple_objects": catalog_has_multiple_objects,
                "reviewed_semantic_category": source["semantic_category"],
                "review_status": "catalog_verified_identity_visual_review_pending",
            }
            if receipt != observed_catalog_receipt:
                _fail(
                    "HSSD_CATALOG_SEMANTIC_MISMATCH",
                    f"catalog evidence differs: {source['source_asset_id']}",
                )
            catalog_dimensions = hssd._parse_dimensions(
                str(model["aligned.dims"]), model_id
            )
            inspection = hssd.inspect_glb(glb_path)
            geometry = hssd.inspect_glb_geometry(glb_path)
            document, _binary = glb_transport.read_glb(glb_path)
        except ForgeError:
            raise
        except hssd.HssdBindingError as exc:
            raise ForgeError(
                "HSSD_SOURCE_INVALID", f"{source['source_asset_id']}: {exc}"
            ) from exc
        if (
            inspection.get("basisu_required") != 1
            or not glb_transport.uses_required_basisu(document)
            or inspection.get("mesh_count", 0) < 1
            or inspection.get("material_count", 0) < 1
            or inspection.get("pbr_texture_slot_count", 0) < 1
            or inspection.get("all_primitives_material_bound") != 1
        ):
            _fail(
                "HSSD_SOURCE_PBR_BASISU_INVALID",
                f"source is not closed PBR/BasisU: {source['source_asset_id']}",
            )
        source_dimensions = geometry.get("blender_dimensions_m")
        if not isinstance(source_dimensions, list) or len(source_dimensions) != 3:
            _fail(
                "HSSD_SOURCE_GEOMETRY_INVALID",
                f"missing measured dimensions: {source['source_asset_id']}",
            )
        try:
            rotation, scales, anisotropy, uniform = hssd._fit_transform(
                source_dimensions,
                source["normalized_dimensions_m"],
            )
        except hssd.HssdBindingError as exc:
            raise ForgeError(
                "HSSD_NORMALIZATION_INVALID", f"{source['source_asset_id']}: {exc}"
            ) from exc
        if anisotropy > MAXIMUM_AXIS_SCALE_ANISOTROPY or not (
            MINIMUM_UNIFORM_SCALE <= uniform <= MAXIMUM_UNIFORM_SCALE
        ):
            _fail(
                "HSSD_NORMALIZATION_INVALID",
                f"unsafe normalization fit: {source['source_asset_id']}",
            )
        asset_slug = source["source_asset_id"]
        if not _SAFE_ID_RE.fullmatch(asset_slug):
            _fail("HSSD_SOURCE_ID_INVALID", "source asset ID is unsafe")
        jobs.append(
            {
                "source_asset_id": asset_slug,
                "semantic_category": source["semantic_category"],
                "model_id": model_id,
                "source": {
                    "render_asset_relpath": source["render_asset_relpath"],
                    "render_asset_sha256": source["render_asset_sha256"],
                    "object_config_relpath": source["object_config_relpath"],
                    "object_config_sha256": source["object_config_sha256"],
                    "source_basisu_required": True,
                    "catalog_aligned_dimensions_m": list(catalog_dimensions),
                    "catalog_semantic_receipt": copy.deepcopy(receipt),
                    "inspection": inspection,
                    "geometry": geometry,
                },
                "normalization": {
                    "target_dimensions_m": source["normalized_dimensions_m"],
                    "origin_policy": "footprint_center_bottom_z_zero",
                    "planned_rotate_z_deg": rotation,
                    "planned_scale_xyz": [round(value, 12) for value in scales],
                    "scale_anisotropy": round(anisotropy, 12),
                    "uniform_scale": round(uniform, 12),
                    "maximum_axis_scale_anisotropy": MAXIMUM_AXIS_SCALE_ANISOTROPY,
                },
                "texture_transport": {
                    "required_mode": "KHR_texture_basisu_to_core_png",
                    "source_basisu_required": True,
                    "output_basisu_required": False,
                    "output_image_transport": "embedded_core_png",
                },
                "output": {
                    "glb_relpath": f"assets/{asset_slug}.glb",
                    "receipt_relpath": f"receipts/{asset_slug}.json",
                },
                "visual_role": "static_presentation_shell",
                "interaction_authority": "none_static_joined_glb",
            }
        )
    jobs.sort(key=lambda item: item["source_asset_id"])
    if len({item["source_asset_id"] for item in jobs}) != EXPECTED_SOURCE_COUNT:
        _fail("HSSD_SOURCE_COUNT_INVALID", "source asset IDs are not unique")
    return tuple(jobs)


def _build_scene_plan(profile: Mapping[str, Any]) -> dict[str, Any]:
    plan = seal_document(
        {
            "schema_version": SCENE_PLAN_SCHEMA,
            "profile_id": profile["profile_id"],
            "profile_content_digest": profile["content_digest"],
            "house_id": profile["house_id"],
            "house_revision": profile["house_revision"],
            "coordinate_frame": "room_local_m",
            "placement_count": len(profile["placements"]),
            "placements": copy.deepcopy(profile["placements"]),
            "articulated_sibling_candidates": copy.deepcopy(
                profile["articulated_sibling_candidates"]
            ),
            "interaction_policy": {
                "static_visuals": "presentation_only_hidden_r1_proxy_remains_authoritative",
                "articulation": "pending_blocked_until_validated",
            },
            "assembly_status": "plan_only_not_assembled",
            "render_status": "not_rendered",
            "accepted_as_visual_evidence": False,
        }
    )
    validate_scene_plan(plan)
    return plan


def _builder_source_receipts() -> list[dict[str, Any]]:
    receipts = []
    for path in SOURCE_FILES:
        seal = seal_regular_file(path.resolve(), label=path.name)
        receipts.append(
            {
                "path": _relative_source_path(path.resolve()),
                "sha256": seal.sha256,
                "bytes": seal.size_bytes,
            }
        )
    return receipts


def _build_plan(
    *,
    profile: Mapping[str, Any],
    house: Mapping[str, Any],
    contract_sources: list[dict[str, Any]],
    jobs: tuple[Mapping[str, Any], ...],
    scene_plan: Mapping[str, Any],
    toolchain: Mapping[str, Any],
    execute: bool,
) -> dict[str, Any]:
    status = (
        "ready_for_explicit_blender_execution"
        if execute
        else "dry_run_validated_no_write"
    )
    plan = seal_document(
        {
            "schema_version": PLAN_SCHEMA,
            "mode": "execute" if execute else "dry_run",
            "will_write": execute,
            "will_execute_blender": execute,
            "accepted": False,
            "status": status,
            "profile": {
                "profile_id": profile["profile_id"],
                "schema_version": profile["schema_version"],
                "content_digest": profile["content_digest"],
                "source_files": contract_sources,
            },
            "house": {
                "house_id": house["house_id"],
                "revision": house["revision"],
                "content_digest": house["content_digest"],
            },
            "dataset": copy.deepcopy(profile["dataset"]),
            "license_scope": copy.deepcopy(profile["license_scope"]),
            "payload_policy": copy.deepcopy(profile["payload_policy"]),
            "network_policy": {
                "network_resolution": "not_used",
                "network_fallback": "disabled",
                "proxy_environment_forwarding": "disabled",
            },
            "toolchain": copy.deepcopy(toolchain),
            "normalization_policy": {
                "blender_version": "4.5.8",
                "origin_policy": "footprint_center_bottom_z_zero",
                "maximum_axis_scale_anisotropy": MAXIMUM_AXIS_SCALE_ANISOTROPY,
                "texture_transport": "KHR_texture_basisu_to_core_png",
                "one_primary_mesh_per_source": True,
            },
            "asset_jobs": [copy.deepcopy(dict(item)) for item in jobs],
            "scene_plan": {
                "schema_version": scene_plan["schema_version"],
                "content_digest": scene_plan["content_digest"],
                "path": "scene-plan.json",
                "placement_count": scene_plan["placement_count"],
            },
            "output_contract": {
                "root_policy": "fresh_append_only_external_directory",
                "build_plan_path": "build-plan.json",
                "scene_plan_path": "scene-plan.json",
                "asset_directory": "assets",
                "receipt_directory": "receipts",
                "result_path": "build-result.json",
                "log_path": "blender.log",
                "binary_payload_in_git": False,
            },
            "closed_world": {
                "source_asset_ids": sorted(item["source_asset_id"] for item in jobs),
                "placement_ids": sorted(
                    item["instance_id"] for item in profile["placements"]
                ),
                "articulation_roles": sorted(
                    item["semantic_role"]
                    for item in profile["articulated_sibling_candidates"]
                ),
                "source_count": len(jobs),
                "placement_count": len(profile["placements"]),
                "unaccounted_source_asset_ids": [],
                "unaccounted_placement_ids": [],
            },
            "acceptance_gates": {
                "profile_validated": True,
                "local_source_hashes_validated": True,
                "toolchain_hashes_validated": True,
                "normalized_pbr_glbs_built": False,
                "scene_assembled": False,
                "rendered": False,
                "accepted_as_visual_evidence": False,
            },
        }
    )
    validate_build_plan(plan)
    return plan


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, label: str) -> None:
    if set(value) != expected:
        _fail(
            "PLAN_NOT_CLOSED", f"{label} keys differ: {sorted(set(value) ^ expected)}"
        )


def validate_scene_plan(plan: Mapping[str, Any]) -> None:
    _scan_closed(plan)
    _exact_keys(
        plan,
        {
            "schema_version",
            "profile_id",
            "profile_content_digest",
            "house_id",
            "house_revision",
            "coordinate_frame",
            "placement_count",
            "placements",
            "articulated_sibling_candidates",
            "interaction_policy",
            "assembly_status",
            "render_status",
            "accepted_as_visual_evidence",
            "content_digest",
        },
        label="scene plan",
    )
    if plan.get("schema_version") != SCENE_PLAN_SCHEMA or plan.get(
        "content_digest"
    ) != content_digest(plan):
        _fail("SCENE_PLAN_IDENTITY_INVALID", "scene-plan schema or digest mismatch")
    placements = plan.get("placements")
    candidates = plan.get("articulated_sibling_candidates")
    if not isinstance(placements, list) or len(placements) != EXPECTED_PLACEMENT_COUNT:
        _fail(
            "SCENE_PLAN_PLACEMENT_COUNT_INVALID",
            "scene plan must contain exactly 60 placements",
        )
    if plan.get("placement_count") != len(placements):
        _fail(
            "SCENE_PLAN_PLACEMENT_COUNT_INVALID",
            "scene-plan placement count is inconsistent",
        )
    ids = [item.get("instance_id") for item in placements if isinstance(item, dict)]
    if len(ids) != len(placements) or len(set(ids)) != len(ids):
        _fail(
            "SCENE_PLAN_PLACEMENT_IDS_INVALID",
            "scene-plan placement IDs are invalid or duplicated",
        )
    for item in placements:
        assert isinstance(item, dict)
        _exact_keys(
            item,
            {
                "instance_id",
                "room_id",
                "source_asset_id",
                "transform",
                "placement_intent",
                "semantic_target_id",
                "normalization_policy",
                "interaction_policy",
            },
            label="scene placement",
        )
        transform = item.get("transform")
        intent = item.get("placement_intent")
        if not isinstance(transform, dict) or not isinstance(intent, dict):
            _fail(
                "SCENE_PLAN_PLACEMENT_INVALID",
                "placement transform and intent must be objects",
            )
        _exact_keys(
            transform,
            {"coordinate_frame", "location_m", "rotation_deg", "scale"},
            label="placement transform",
        )
        _exact_keys(
            intent, {"role", "support_mode", "reason"}, label="placement intent"
        )
        if (
            transform.get("coordinate_frame") != "room_local_m"
            or transform.get("scale") != [1, 1, 1]
            or item.get("normalization_policy")
            != "use_source_normalized_dimensions_exactly"
        ):
            _fail(
                "SCENE_PLAN_PLACEMENT_INVALID",
                "placement coordinate or normalization policy drifted",
            )
    if any(
        item.get("interaction_policy")
        != "visual_only_hidden_r1_proxy_remains_authoritative"
        for item in placements
        if isinstance(item, dict)
    ):
        _fail(
            "SCENE_PLAN_STATIC_INTERACTION_LIE",
            "scene-plan static placement claims interaction authority",
        )
    if not isinstance(candidates, list) or any(
        not isinstance(item, dict) for item in candidates
    ):
        _fail(
            "SCENE_PLAN_ARTICULATION_INVALID", "articulation candidates must be objects"
        )
    if {
        item.get("semantic_role") for item in candidates
    } != EXPECTED_ARTICULATION_ROLES:
        _fail(
            "SCENE_PLAN_ARTICULATION_INVALID",
            "scene plan lacks the five pending articulation roles",
        )
    for item in candidates:
        if not isinstance(item, dict):
            _fail(
                "SCENE_PLAN_ARTICULATION_INVALID",
                "articulation candidate must be an object",
            )
        _exact_keys(
            item,
            {
                "semantic_role",
                "static_source_asset_id",
                "candidate_model_id",
                "urdf_relpath",
                "urdf_sha256",
                "ao_config_relpath",
                "ao_config_sha256",
                "relationship_status",
                "selection_status",
                "validation_status",
                "ue_integration_status",
                "articulation_authority",
                "static_fallback_policy",
            },
            label="articulation candidate",
        )
    if any(
        not isinstance(item, dict)
        or item.get("selection_status") != "pending"
        or item.get("validation_status") != "pending"
        or item.get("ue_integration_status") != "pending"
        or item.get("articulation_authority") != "blocked_until_validated"
        or item.get("static_fallback_policy") != "presentation_only_never_interactive"
        for item in candidates
    ):
        _fail(
            "SCENE_PLAN_ARTICULATION_INVALID",
            "articulation candidates must remain pending and blocked",
        )
    if (
        plan.get("assembly_status") != "plan_only_not_assembled"
        or plan.get("render_status") != "not_rendered"
        or plan.get("accepted_as_visual_evidence") is not False
    ):
        _fail(
            "SCENE_PLAN_ACCEPTANCE_LIE",
            "unassembled scene plan cannot claim render or acceptance",
        )
    interaction_policy = plan.get("interaction_policy")
    if interaction_policy != {
        "static_visuals": "presentation_only_hidden_r1_proxy_remains_authoritative",
        "articulation": "pending_blocked_until_validated",
    }:
        _fail(
            "SCENE_PLAN_STATIC_INTERACTION_LIE", "scene-plan interaction policy drifted"
        )


def _validate_asset_job(job: Mapping[str, Any]) -> None:
    _exact_keys(
        job,
        {
            "source_asset_id",
            "semantic_category",
            "model_id",
            "source",
            "normalization",
            "texture_transport",
            "output",
            "visual_role",
            "interaction_authority",
        },
        label="asset job",
    )
    source_asset_id = job.get("source_asset_id")
    model_id = job.get("model_id")
    if not isinstance(source_asset_id, str) or not _SAFE_ID_RE.fullmatch(
        source_asset_id
    ):
        _fail("PLAN_ASSET_JOB_INVALID", "asset job source ID is unsafe")
    if not isinstance(model_id, str) or not _MODEL_ID_RE.fullmatch(model_id):
        _fail("PLAN_ASSET_JOB_INVALID", "asset job model ID is invalid")
    source = job.get("source")
    normalization = job.get("normalization")
    transport = job.get("texture_transport")
    output = job.get("output")
    if not all(
        isinstance(value, dict) for value in (source, normalization, transport, output)
    ):
        _fail("PLAN_ASSET_JOB_INVALID", "asset job subcontracts must be objects")
    assert (
        isinstance(source, dict)
        and isinstance(normalization, dict)
        and isinstance(transport, dict)
        and isinstance(output, dict)
    )
    _exact_keys(
        source,
        {
            "render_asset_relpath",
            "render_asset_sha256",
            "object_config_relpath",
            "object_config_sha256",
            "source_basisu_required",
            "catalog_aligned_dimensions_m",
            "catalog_semantic_receipt",
            "inspection",
            "geometry",
        },
        label="asset job source",
    )
    inspection = source.get("inspection")
    geometry = source.get("geometry")
    catalog_receipt = source.get("catalog_semantic_receipt")
    if (
        not isinstance(inspection, dict)
        or not isinstance(geometry, dict)
        or not isinstance(catalog_receipt, dict)
    ):
        _fail(
            "PLAN_ASSET_JOB_INVALID",
            "source catalog receipt, inspection and geometry must be objects",
        )
    _exact_keys(
        inspection,
        {
            "mesh_count",
            "primitive_count",
            "material_bound_primitive_count",
            "all_primitives_material_bound",
            "triangle_count",
            "material_count",
            "pbr_material_count",
            "texture_count",
            "image_count",
            "pbr_texture_slot_count",
            "base_normal_orm_texture_slot_count",
            "basisu_required",
        },
        label="source inspection",
    )
    _exact_keys(
        geometry,
        {
            "measurement_policy",
            "coordinate_conversion",
            "mesh_node_count",
            "position_accessor_count",
            "position_vertex_count",
            "gltf_bounds_m",
            "gltf_dimensions_m",
            "blender_bounds_m",
            "blender_dimensions_m",
        },
        label="source geometry",
    )
    _exact_keys(
        catalog_receipt,
        {
            "source_asset_id",
            "model_id",
            "catalog_name",
            "catalog_wnsynsetkey",
            "semantic_condensed_category",
            "semantic_primary_category",
            "catalog_has_multiple_objects",
            "reviewed_semantic_category",
            "review_status",
        },
        label="catalog semantic receipt",
    )
    if (
        catalog_receipt.get("source_asset_id") != source_asset_id
        or catalog_receipt.get("model_id") != model_id
        or catalog_receipt.get("reviewed_semantic_category")
        != job.get("semantic_category")
        or catalog_receipt.get("review_status")
        != "catalog_verified_identity_visual_review_pending"
        or not all(
            isinstance(catalog_receipt.get(key), str)
            for key in (
                "catalog_name",
                "catalog_wnsynsetkey",
                "semantic_condensed_category",
                "semantic_primary_category",
            )
        )
        or type(catalog_receipt.get("catalog_has_multiple_objects")) is not bool
    ):
        _fail(
            "PLAN_ASSET_JOB_INVALID", "catalog semantic receipt identity drifted"
        )
    for bounds_key in ("gltf_bounds_m", "blender_bounds_m"):
        bounds = geometry.get(bounds_key)
        if not isinstance(bounds, dict):
            _fail("PLAN_ASSET_JOB_INVALID", "source geometry bounds must be objects")
        _exact_keys(bounds, {"min_m", "max_m"}, label="source geometry bounds")
    _exact_keys(
        normalization,
        {
            "target_dimensions_m",
            "origin_policy",
            "planned_rotate_z_deg",
            "planned_scale_xyz",
            "scale_anisotropy",
            "uniform_scale",
            "maximum_axis_scale_anisotropy",
        },
        label="asset job normalization",
    )
    _exact_keys(
        transport,
        {
            "required_mode",
            "source_basisu_required",
            "output_basisu_required",
            "output_image_transport",
        },
        label="asset job transport",
    )
    _exact_keys(output, {"glb_relpath", "receipt_relpath"}, label="asset job output")
    for key in ("render_asset_relpath", "object_config_relpath"):
        _safe_relative(source[key], label=key)
    for key in ("glb_relpath", "receipt_relpath"):
        _safe_relative(output[key], label=key)
    if (
        source["render_asset_relpath"] != f"objects/{model_id[0]}/{model_id}.glb"
        or source["object_config_relpath"]
        != f"objects/{model_id[0]}/{model_id}.object_config.json"
        or source["source_basisu_required"] is not True
        or transport
        != {
            "required_mode": "KHR_texture_basisu_to_core_png",
            "source_basisu_required": True,
            "output_basisu_required": False,
            "output_image_transport": "embedded_core_png",
        }
        or output["glb_relpath"] != f"assets/{source_asset_id}.glb"
        or output["receipt_relpath"] != f"receipts/{source_asset_id}.json"
        or job.get("visual_role") != "static_presentation_shell"
        or job.get("interaction_authority") != "none_static_joined_glb"
        or inspection.get("basisu_required") != 1
        or inspection.get("mesh_count", 0) < 1
        or inspection.get("pbr_texture_slot_count", 0) < 1
        or inspection.get("all_primitives_material_bound") != 1
    ):
        _fail(
            "PLAN_ASSET_JOB_INVALID",
            "asset job source, transport, output, or authority drifted",
        )
    if not all(
        isinstance(source.get(key), str) and _SHA256_RE.fullmatch(source[key])
        for key in ("render_asset_sha256", "object_config_sha256")
    ):
        _fail("PLAN_ASSET_JOB_INVALID", "asset job source hashes are invalid")
    dimensions = normalization.get("target_dimensions_m")
    catalog_dimensions = source.get("catalog_aligned_dimensions_m")
    source_dimensions = geometry.get("blender_dimensions_m")
    if (
        not isinstance(dimensions, list)
        or len(dimensions) != 3
        or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0
            for value in dimensions
        )
        or normalization.get("origin_policy") != "footprint_center_bottom_z_zero"
        or normalization.get("maximum_axis_scale_anisotropy")
        != MAXIMUM_AXIS_SCALE_ANISOTROPY
        or float(normalization.get("scale_anisotropy", math.inf))
        > MAXIMUM_AXIS_SCALE_ANISOTROPY
        or not isinstance(catalog_dimensions, list)
        or len(catalog_dimensions) != 3
        or not isinstance(source_dimensions, list)
        or len(source_dimensions) != 3
    ):
        _fail("PLAN_ASSET_JOB_INVALID", "asset job normalization is invalid")


def validate_build_plan(
    plan: Mapping[str, Any], *, expected_mode: str | None = None
) -> None:
    _scan_closed(plan)
    _exact_keys(
        plan,
        {
            "schema_version",
            "mode",
            "will_write",
            "will_execute_blender",
            "accepted",
            "status",
            "profile",
            "house",
            "dataset",
            "license_scope",
            "payload_policy",
            "network_policy",
            "toolchain",
            "normalization_policy",
            "asset_jobs",
            "scene_plan",
            "output_contract",
            "closed_world",
            "acceptance_gates",
            "content_digest",
        },
        label="build plan",
    )
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get(
        "content_digest"
    ) != content_digest(plan):
        _fail("PLAN_IDENTITY_INVALID", "build-plan schema or digest mismatch")
    mode = plan.get("mode")
    if mode not in {"dry_run", "execute"} or (
        expected_mode is not None and mode != expected_mode
    ):
        _fail("PLAN_MODE_INVALID", "build-plan mode is invalid")
    execute = mode == "execute"
    if (
        plan.get("will_write") is not execute
        or plan.get("will_execute_blender") is not execute
        or plan.get("accepted") is not False
    ):
        _fail("PLAN_MODE_INVALID", "build-plan side-effect flags are inconsistent")
    expected_status = (
        "ready_for_explicit_blender_execution"
        if execute
        else "dry_run_validated_no_write"
    )
    if plan.get("status") != expected_status:
        _fail("PLAN_MODE_INVALID", "build-plan status is inconsistent")
    profile = plan.get("profile")
    if (
        not isinstance(profile, dict)
        or profile.get("content_digest") != PINNED_PROFILE_CONTENT_DIGEST
    ):
        _fail("PLAN_PROFILE_INVALID", "build plan targets another profile")
    _exact_keys(
        profile,
        {"profile_id", "schema_version", "content_digest", "source_files"},
        label="profile receipt",
    )
    if (
        profile.get("profile_id") != "hssd_private_research_r1"
        or profile.get("schema_version") != PROFILE_SCHEMA_VERSION
        or not isinstance(profile.get("source_files"), list)
        or len(profile["source_files"]) != 2
    ):
        _fail("PLAN_PROFILE_INVALID", "profile receipt is invalid")
    house = plan.get("house")
    if not isinstance(house, dict):
        _fail("PLAN_HOUSE_INVALID", "house receipt must be an object")
    _exact_keys(
        house, {"house_id", "revision", "content_digest"}, label="house receipt"
    )
    if house != {
        "house_id": "home.r1",
        "revision": "vista_playable_home_r1",
        "content_digest": "51208e0ecc1ad1450ca6d9b14a4fb46989bff90fd8dc15422a0a47df6827c8c3",
    }:
        _fail("PLAN_HOUSE_INVALID", "house receipt differs from the pinned HouseSpec")

    def validate_file_receipts(receipts: Any, *, label: str) -> None:
        if not isinstance(receipts, list) or not receipts:
            _fail("PLAN_SOURCE_RECEIPT_INVALID", f"{label} must be a non-empty array")
        paths: set[str] = set()
        for receipt in receipts:
            if not isinstance(receipt, dict):
                _fail(
                    "PLAN_SOURCE_RECEIPT_INVALID", f"{label} receipt must be an object"
                )
            _exact_keys(receipt, {"path", "sha256", "bytes"}, label=label)
            path_value = receipt.get("path")
            if not isinstance(path_value, str):
                _fail("PLAN_SOURCE_RECEIPT_INVALID", f"{label} path is invalid")
            _safe_relative(path_value, label=label)
            if (
                path_value in paths
                or not isinstance(receipt.get("sha256"), str)
                or not _SHA256_RE.fullmatch(receipt["sha256"])
                or isinstance(receipt.get("bytes"), bool)
                or not isinstance(receipt.get("bytes"), int)
                or receipt["bytes"] <= 0
            ):
                _fail("PLAN_SOURCE_RECEIPT_INVALID", f"{label} receipt is invalid")
            paths.add(path_value)

    validate_file_receipts(profile["source_files"], label="profile source file")
    dataset = plan.get("dataset")
    if not isinstance(dataset, dict):
        _fail("PLAN_DATASET_INVALID", "dataset receipt must be an object")
    _exact_keys(
        dataset,
        {
            "name",
            "project_url",
            "dataset_revision",
            "readme_relpath",
            "readme_sha256",
            "license",
        },
        label="dataset",
    )
    dataset_license = dataset.get("license")
    if not isinstance(dataset_license, dict):
        _fail("PLAN_DATASET_INVALID", "dataset license must be an object")
    _exact_keys(
        dataset_license,
        {
            "spdx",
            "url",
            "attribution_required",
            "modification_notice_required",
            "commercial_use",
        },
        label="dataset license",
    )
    if (
        dataset.get("name") != "Habitat Synthetic Scenes Dataset (HSSD)"
        or dataset.get("project_url") != "https://3dlg-hcvc.github.io/hssd/"
        or dataset.get("dataset_revision") != PINNED_DATASET_REVISION
        or dataset.get("readme_relpath") != "README.md"
        or dataset.get("readme_sha256") != PINNED_DATASET_README_SHA256
        or dataset_license
        != {
            "spdx": "CC-BY-NC-4.0",
            "url": "https://creativecommons.org/licenses/by-nc/4.0/",
            "attribution_required": True,
            "modification_notice_required": True,
            "commercial_use": "prohibited_without_separate_permission",
        }
    ):
        _fail("PLAN_DATASET_INVALID", "dataset identity or CC-BY-NC license drifted")
    license_scope = plan.get("license_scope")
    payload_policy = plan.get("payload_policy")
    if not isinstance(license_scope, dict) or not isinstance(payload_policy, dict):
        _fail(
            "PLAN_LICENSE_POLICY_INVALID",
            "license and payload policies must be objects",
        )
    _exact_keys(
        license_scope,
        {
            "use_class",
            "commercial_release",
            "public_payload_distribution",
            "attribution_notice",
        },
        label="license scope",
    )
    _exact_keys(
        payload_policy,
        {
            "git_contents",
            "binary_payload_location",
            "accepted_build_outputs",
            "network_fallback",
        },
        label="payload policy",
    )
    if (
        license_scope.get("use_class") != "private_noncommercial_research_only"
        or license_scope.get("commercial_release") != "blocked"
        or license_scope.get("public_payload_distribution") != "prohibited"
        or payload_policy.get("git_contents")
        != "manifests_digests_licenses_and_recipes_only"
        or payload_policy.get("binary_payload_location") != "outside_git_required"
        or payload_policy.get("accepted_build_outputs") != "append_only_outside_git"
        or payload_policy.get("network_fallback") != "disabled"
    ):
        _fail(
            "PLAN_LICENSE_POLICY_INVALID",
            "private-research license or external-payload policy drifted",
        )
    toolchain = plan.get("toolchain")
    if not isinstance(toolchain, dict):
        _fail("PLAN_TOOLCHAIN_INVALID", "toolchain receipt must be an object")
    _exact_keys(
        toolchain,
        {"blender", "node", "basis_transcoder", "builder_sources"},
        label="toolchain",
    )
    blender = toolchain.get("blender")
    node = toolchain.get("node")
    basis = toolchain.get("basis_transcoder")
    if not all(isinstance(value, dict) for value in (blender, node, basis)):
        _fail("PLAN_TOOLCHAIN_INVALID", "toolchain components must be objects")
    assert (
        isinstance(blender, dict) and isinstance(node, dict) and isinstance(basis, dict)
    )
    _exact_keys(
        blender,
        {"version", "sha256", "bytes", "version_enforcement", "dry_run_version_probe"},
        label="Blender receipt",
    )
    _exact_keys(node, {"sha256", "bytes"}, label="Node receipt")
    _exact_keys(
        basis,
        {
            "distribution",
            "distribution_version",
            "javascript_sha256",
            "javascript_bytes",
            "wasm_sha256",
            "wasm_bytes",
            "basis_universal_license",
            "three_license",
        },
        label="Basis receipt",
    )
    if (
        blender.get("version") != "4.5.8"
        or blender.get("sha256") != PINNED_BLENDER_SHA256
        or blender.get("version_enforcement") != "worker_requires_exact_bpy_app_version"
        or blender.get("dry_run_version_probe") is not False
        or node.get("sha256") != PINNED_NODE_SHA256
        or basis.get("distribution") != "three"
        or basis.get("distribution_version") != "0.185.1"
        or basis.get("javascript_sha256") != PINNED_BASIS_JS_SHA256
        or basis.get("wasm_sha256") != PINNED_BASIS_WASM_SHA256
        or basis.get("basis_universal_license") != "Apache-2.0"
        or basis.get("three_license") != "MIT"
    ):
        _fail("PLAN_TOOLCHAIN_INVALID", "pinned Blender/Node/Basis toolchain drifted")
    validate_file_receipts(toolchain.get("builder_sources"), label="builder source")
    normalization_policy = plan.get("normalization_policy")
    if not isinstance(normalization_policy, dict):
        _fail("PLAN_NORMALIZATION_INVALID", "normalization policy must be an object")
    _exact_keys(
        normalization_policy,
        {
            "blender_version",
            "origin_policy",
            "maximum_axis_scale_anisotropy",
            "texture_transport",
            "one_primary_mesh_per_source",
        },
        label="normalization policy",
    )
    if normalization_policy != {
        "blender_version": "4.5.8",
        "origin_policy": "footprint_center_bottom_z_zero",
        "maximum_axis_scale_anisotropy": MAXIMUM_AXIS_SCALE_ANISOTROPY,
        "texture_transport": "KHR_texture_basisu_to_core_png",
        "one_primary_mesh_per_source": True,
    }:
        _fail("PLAN_NORMALIZATION_INVALID", "normalization policy drifted")
    jobs = plan.get("asset_jobs")
    if not isinstance(jobs, list) or len(jobs) != EXPECTED_SOURCE_COUNT:
        _fail(
            "PLAN_SOURCE_COUNT_INVALID",
            f"build plan must contain exactly {EXPECTED_SOURCE_COUNT} source jobs",
        )
    for job in jobs:
        if not isinstance(job, dict):
            _fail("PLAN_ASSET_JOB_INVALID", "asset job must be an object")
        _validate_asset_job(job)
    source_ids = [job["source_asset_id"] for job in jobs]
    if len(set(source_ids)) != len(source_ids):
        _fail("PLAN_SOURCE_IDS_INVALID", "asset job IDs are duplicated")
    scene = plan.get("scene_plan")
    closed = plan.get("closed_world")
    gates = plan.get("acceptance_gates")
    if (
        not isinstance(scene, dict)
        or scene.get("placement_count") != EXPECTED_PLACEMENT_COUNT
    ):
        _fail("PLAN_SCENE_INVALID", "build plan scene reference is invalid")
    _exact_keys(
        scene,
        {"schema_version", "content_digest", "path", "placement_count"},
        label="scene reference",
    )
    if (
        scene.get("schema_version") != SCENE_PLAN_SCHEMA
        or not isinstance(scene.get("content_digest"), str)
        or not _SHA256_RE.fullmatch(scene["content_digest"])
        or scene.get("path") != "scene-plan.json"
    ):
        _fail("PLAN_SCENE_INVALID", "build plan scene reference drifted")
    if (
        not isinstance(closed, dict)
        or closed.get("source_count") != EXPECTED_SOURCE_COUNT
        or closed.get("placement_count") != EXPECTED_PLACEMENT_COUNT
    ):
        _fail("PLAN_CLOSED_WORLD_INVALID", "build plan closed-world counts are invalid")
    _exact_keys(
        closed,
        {
            "source_asset_ids",
            "placement_ids",
            "articulation_roles",
            "source_count",
            "placement_count",
            "unaccounted_source_asset_ids",
            "unaccounted_placement_ids",
        },
        label="closed world",
    )
    if (
        set(closed.get("source_asset_ids", [])) != set(source_ids)
        or closed.get("unaccounted_source_asset_ids") != []
        or closed.get("unaccounted_placement_ids") != []
    ):
        _fail(
            "PLAN_CLOSED_WORLD_INVALID",
            "build plan source/placement coverage is not closed",
        )
    if set(closed.get("articulation_roles", [])) != EXPECTED_ARTICULATION_ROLES:
        _fail(
            "PLAN_CLOSED_WORLD_INVALID",
            "build plan articulation coverage is not closed",
        )
    if not isinstance(gates, dict) or any(
        gates.get(key) is not False
        for key in (
            "normalized_pbr_glbs_built",
            "scene_assembled",
            "rendered",
            "accepted_as_visual_evidence",
        )
    ):
        _fail(
            "PLAN_ACCEPTANCE_LIE",
            "an unexecuted build plan cannot claim materialization or visual acceptance",
        )
    _exact_keys(
        gates,
        {
            "profile_validated",
            "local_source_hashes_validated",
            "toolchain_hashes_validated",
            "normalized_pbr_glbs_built",
            "scene_assembled",
            "rendered",
            "accepted_as_visual_evidence",
        },
        label="acceptance gates",
    )
    if any(
        gates.get(key) is not True
        for key in (
            "profile_validated",
            "local_source_hashes_validated",
            "toolchain_hashes_validated",
        )
    ):
        _fail("PLAN_ACCEPTANCE_LIE", "preflight validation gates are incomplete")
    output_contract = plan.get("output_contract")
    if not isinstance(output_contract, dict):
        _fail("PLAN_OUTPUT_CONTRACT_INVALID", "output contract must be an object")
    _exact_keys(
        output_contract,
        {
            "root_policy",
            "build_plan_path",
            "scene_plan_path",
            "asset_directory",
            "receipt_directory",
            "result_path",
            "log_path",
            "binary_payload_in_git",
        },
        label="output contract",
    )
    if output_contract != {
        "root_policy": "fresh_append_only_external_directory",
        "build_plan_path": "build-plan.json",
        "scene_plan_path": "scene-plan.json",
        "asset_directory": "assets",
        "receipt_directory": "receipts",
        "result_path": "build-result.json",
        "log_path": "blender.log",
        "binary_payload_in_git": False,
    }:
        _fail("PLAN_OUTPUT_CONTRACT_INVALID", "output contract drifted")
    network = plan.get("network_policy")
    if not isinstance(network, dict):
        _fail("PLAN_NETWORK_POLICY_INVALID", "network policy must be an object")
    _exact_keys(
        network,
        {"network_resolution", "network_fallback", "proxy_environment_forwarding"},
        label="network policy",
    )
    if network != {
        "network_resolution": "not_used",
        "network_fallback": "disabled",
        "proxy_environment_forwarding": "disabled",
    }:
        _fail("PLAN_NETWORK_POLICY_INVALID", "network policy is not closed and offline")


def build_preflight(config: ForgeConfig) -> ForgePreflight:
    """Validate all local inputs and return a deterministic zero-write plan."""

    if config.license_accept != "CC-BY-NC-4.0":
        _fail(
            "LICENSE_NOT_ACCEPTED", "explicit CC-BY-NC-4.0 acknowledgement is required"
        )
    output_target = _validate_output_destination(config.output_root)
    hssd_root = _canonical_directory(config.hssd_root, label="HSSD root")
    try:
        output_target.relative_to(hssd_root)
    except ValueError:
        pass
    else:
        _fail(
            "OUTPUT_INSIDE_DATASET_PROHIBITED",
            "private binary output must not modify the pinned HSSD source tree",
        )
    profile, house, contract_sources = _verify_checked_in_contracts()
    jobs = _verify_dataset_and_sources(profile, config.hssd_root)
    toolchain = _verify_toolchain(config)
    scene_plan = _build_scene_plan(profile)
    build_plan = _build_plan(
        profile=profile,
        house=house,
        contract_sources=contract_sources,
        jobs=jobs,
        scene_plan=scene_plan,
        toolchain=toolchain,
        execute=config.execute,
    )
    return ForgePreflight(config, profile, house, scene_plan, build_plan, jobs)


def _safe_blender_environment() -> dict[str, str]:
    allowed = (
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "TMPDIR",
        "USER",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
    )
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "VISTA_NETWORK_DISABLED": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
            "PYTHONNOUSERSITE": "1",
        }
    )
    return environment


def _validate_result_manifest(
    result: Mapping[str, Any], output_root: pathlib.Path, plan: Mapping[str, Any]
) -> None:
    _scan_closed(result)
    _exact_keys(
        result,
        {
            "schema_version",
            "build_plan_content_digest",
            "scene_plan_content_digest",
            "profile_content_digest",
            "status",
            "accepted",
            "asset_count",
            "assets",
            "scene_assembly_status",
            "render_status",
            "articulation_status",
            "content_digest",
        },
        label="build result",
    )
    if (
        result.get("schema_version") != RESULT_SCHEMA
        or result.get("content_digest") != content_digest(result)
        or result.get("build_plan_content_digest") != plan["content_digest"]
        or result.get("scene_plan_content_digest")
        != plan["scene_plan"]["content_digest"]
        or result.get("profile_content_digest") != PINNED_PROFILE_CONTENT_DIGEST
    ):
        _fail(
            "RESULT_IDENTITY_INVALID",
            "build-result schema, digest, or source identity mismatch",
        )
    assets = result.get("assets")
    if (
        not isinstance(assets, list)
        or len(assets) != EXPECTED_SOURCE_COUNT
        or result.get("asset_count") != len(assets)
    ):
        _fail(
            "RESULT_ASSET_COUNT_INVALID",
            f"build result must contain {EXPECTED_SOURCE_COUNT} asset receipts",
        )
    expected_jobs = {job["source_asset_id"]: job for job in plan["asset_jobs"]}
    seen: set[str] = set()
    for index, entry in enumerate(assets):
        if not isinstance(entry, dict):
            _fail(
                "RESULT_ASSET_INVALID", f"asset receipt index {index} is not an object"
            )
        _exact_keys(
            entry,
            {
                "source_asset_id",
                "glb_relpath",
                "receipt_relpath",
                "output_sha256",
                "receipt_content_digest",
            },
            label="result asset index",
        )
        asset_id = entry.get("source_asset_id")
        job = expected_jobs.get(asset_id)
        if job is None or asset_id in seen:
            _fail("RESULT_ASSET_INVALID", "asset receipt is unknown or duplicated")
        seen.add(asset_id)
        receipt_relpath = entry.get("receipt_relpath")
        output_relpath = entry.get("glb_relpath")
        if (
            receipt_relpath != job["output"]["receipt_relpath"]
            or output_relpath != job["output"]["glb_relpath"]
        ):
            _fail("RESULT_ASSET_INVALID", "asset receipt paths differ from the plan")
        receipt_path = output_root.joinpath(
            *_safe_relative(receipt_relpath, label="receipt").parts
        )
        output_path = output_root.joinpath(
            *_safe_relative(output_relpath, label="GLB").parts
        )
        receipt = load_json(receipt_path)
        _exact_keys(
            receipt,
            {
                "schema_version",
                "build_plan_content_digest",
                "profile_content_digest",
                "source_asset_id",
                "semantic_category",
                "model_id",
                "source_render_asset_sha256",
                "catalog_semantic_receipt",
                "output_relpath",
                "output_sha256",
                "output_bytes",
                "target_dimensions_m",
                "actual_dimensions_m",
                "normalization",
                "inspection",
                "texture_transport",
                "texture_transport_receipt",
                "source_basisu_required",
                "output_basisu_required",
                "visual_role",
                "interaction_authority",
                "accepted_as_interactive_asset",
                "status",
                "content_digest",
            },
            label="asset receipt",
        )
        if (
            receipt.get("schema_version") != ASSET_RECEIPT_SCHEMA
            or receipt.get("content_digest") != content_digest(receipt)
            or receipt.get("source_asset_id") != asset_id
            or receipt.get("semantic_category") != job["semantic_category"]
            or receipt.get("model_id") != job["model_id"]
            or receipt.get("source_render_asset_sha256")
            != job["source"]["render_asset_sha256"]
            or receipt.get("catalog_semantic_receipt")
            != job["source"]["catalog_semantic_receipt"]
            or receipt.get("output_relpath") != output_relpath
            or receipt.get("output_sha256") != entry.get("output_sha256")
            or receipt.get("content_digest") != entry.get("receipt_content_digest")
            or receipt.get("target_dimensions_m")
            != job["normalization"]["target_dimensions_m"]
            or receipt.get("build_plan_content_digest") != plan["content_digest"]
            or receipt.get("visual_role") != "static_presentation_shell"
            or receipt.get("interaction_authority") != "none_static_joined_glb"
            or receipt.get("texture_transport") != "KHR_texture_basisu_to_core_png"
            or receipt.get("source_basisu_required") is not True
            or receipt.get("output_basisu_required") is not False
            or receipt.get("accepted_as_interactive_asset") is not False
            or receipt.get("status") != "normalized_pbr_glb_built_for_private_research"
        ):
            _fail("RESULT_ASSET_RECEIPT_INVALID", f"asset receipt invalid: {asset_id}")
        actual_dimensions = receipt.get("actual_dimensions_m")
        target_dimensions = job["normalization"]["target_dimensions_m"]
        if (
            not isinstance(actual_dimensions, list)
            or len(actual_dimensions) != 3
            or any(
                abs(float(actual) - float(target)) > 0.0005
                for actual, target in zip(actual_dimensions, target_dimensions)
            )
        ):
            _fail(
                "RESULT_ASSET_RECEIPT_INVALID", f"asset dimensions invalid: {asset_id}"
            )
        output_seal = seal_regular_file(
            output_path,
            label=f"materialized GLB {asset_id}",
            expected_sha256=receipt.get("output_sha256"),
        )
        if output_seal.size_bytes != receipt.get("output_bytes"):
            _fail(
                "RESULT_ASSET_RECEIPT_INVALID", f"asset byte count invalid: {asset_id}"
            )
        try:
            inspection = hssd.inspect_glb(output_path)
        except hssd.HssdBindingError as exc:
            raise ForgeError("RESULT_ASSET_GLTF_INVALID", f"{asset_id}: {exc}") from exc
        if (
            inspection.get("mesh_count") != 1
            or inspection.get("material_count", 0) < 1
            or inspection.get("pbr_texture_slot_count", 0) < 1
            or inspection.get("all_primitives_material_bound") != 1
            or inspection.get("basisu_required") != 0
        ):
            _fail(
                "RESULT_ASSET_GLTF_INVALID",
                f"normalized PBR GLB gate failed: {asset_id}",
            )
    if seen != set(expected_jobs):
        _fail("RESULT_ASSET_COUNT_INVALID", "result asset coverage is not closed")
    if (
        result.get("status") != "assets_materialized_scene_plan_only_not_rendered"
        or result.get("accepted") is not False
        or result.get("scene_assembly_status") != "plan_only_not_assembled"
        or result.get("render_status") != "not_rendered"
        or result.get("articulation_status") != "pending_blocked_until_validated"
    ):
        _fail(
            "RESULT_ACCEPTANCE_LIE",
            "build result overclaims scene, render, articulation, or acceptance",
        )


def apply_forge(preflight: ForgePreflight) -> dict[str, Any]:
    """Create a fresh external attempt and run the fixed Blender worker."""

    if not preflight.config.execute or preflight.build_plan.get("mode") != "execute":
        _fail(
            "EXECUTE_NOT_AUTHORIZED",
            "re-plan with explicit execute=True before materializing",
        )
    output_root = _prepare_output_root(preflight.config.output_root)
    _write_exclusive(
        output_root / "build-plan.json", canonical_json(preflight.build_plan)
    )
    _write_exclusive(
        output_root / "scene-plan.json", canonical_json(preflight.scene_plan)
    )
    try:
        os.mkdir(output_root / "assets", PRIVATE_DIRECTORY_MODE)
        os.mkdir(output_root / "receipts", PRIVATE_DIRECTORY_MODE)
    except OSError as exc:
        raise ForgeError(
            "OUTPUT_CREATE_FAILED", "could not create private output subdirectories"
        ) from exc

    command = [
        str(preflight.config.blender),
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(WORKER_PATH),
        "--",
        "--build-plan",
        str(output_root / "build-plan.json"),
        "--hssd-root",
        str(preflight.config.hssd_root),
        "--output-root",
        str(output_root),
        "--node",
        str(preflight.config.node),
        "--basis-transcoder-js",
        str(preflight.config.basis_js),
        "--basis-transcoder-wasm",
        str(preflight.config.basis_wasm),
    ]
    log_path = output_root / "blender.log"
    descriptor = -1
    try:
        descriptor = os.open(
            log_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            PRIVATE_FILE_MODE,
        )
        with os.fdopen(descriptor, "wb", closefd=True) as log_handle:
            descriptor = -1
            subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                env=_safe_blender_environment(),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                timeout=BLENDER_TIMEOUT_SECONDS,
                check=True,
            )
    except subprocess.TimeoutExpired as exc:
        raise ForgeError(
            "BLENDER_TIMEOUT", "fixed Blender worker exceeded the time limit"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ForgeError(
            "BLENDER_FAILED", "fixed Blender worker failed; inspect the append-only log"
        ) from exc
    except OSError as exc:
        raise ForgeError(
            "BLENDER_START_FAILED", "could not start the pinned Blender worker"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    result_path = output_root / "build-result.json"
    if not result_path.is_file() or result_path.is_symlink():
        _fail(
            "BLENDER_FAILED",
            "fixed Blender worker exited without a result; inspect the append-only log",
        )
    result = load_json(result_path)
    _validate_result_manifest(result, output_root, preflight.build_plan)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hssd-root", type=pathlib.Path, default=DEFAULT_HSSD_ROOT)
    parser.add_argument("--output-root", type=pathlib.Path, required=True)
    parser.add_argument("--blender", type=pathlib.Path, default=DEFAULT_BLENDER)
    parser.add_argument("--node", type=pathlib.Path, default=DEFAULT_NODE)
    parser.add_argument(
        "--basis-transcoder-js", type=pathlib.Path, default=DEFAULT_BASIS_JS
    )
    parser.add_argument(
        "--basis-transcoder-wasm", type=pathlib.Path, default=DEFAULT_BASIS_WASM
    )
    parser.add_argument("--license-accept", required=True, choices=["CC-BY-NC-4.0"])
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Create a fresh output and invoke the fixed Blender worker",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = ForgeConfig(
        hssd_root=args.hssd_root,
        output_root=args.output_root,
        blender=args.blender,
        node=args.node,
        basis_js=args.basis_transcoder_js,
        basis_wasm=args.basis_transcoder_wasm,
        license_accept=args.license_accept,
        execute=args.execute,
    )
    preflight = build_preflight(config)
    if args.execute:
        result = apply_forge(preflight)
        summary = {
            "status": result["status"],
            "accepted": False,
            "asset_count": result["asset_count"],
            "scene_assembly_status": result["scene_assembly_status"],
            "render_status": result["render_status"],
            "result": "build-result.json",
        }
    else:
        summary = {
            "status": preflight.build_plan["status"],
            "mode": "dry_run",
            "will_write": False,
            "will_execute_blender": False,
            "build_plan_content_digest": preflight.build_plan["content_digest"],
            "scene_plan_content_digest": preflight.scene_plan["content_digest"],
            "asset_count": len(preflight.asset_jobs),
            "placement_count": preflight.scene_plan["placement_count"],
            "articulation_status": "pending_blocked_until_validated",
            "render_status": "not_rendered",
            "accepted": False,
        }
    sys.stdout.buffer.write(canonical_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
