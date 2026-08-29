#!/usr/bin/env python3
"""Fail-closed UE 5.7 forward-load smoke for local CitySampleCrowd content.

The default operation is a read-only plan.  An apply is deliberately awkward:
the operator must acknowledge the private/noncommercial research scope, their
Epic/Unreal content entitlement, the no-redistribution boundary, the rule that
source-format UAssets stay outside Git, the roughly 10 GiB full-Content
fallback copy, and that the MetaHuman-backed crowd remains isolated to a
human-operated visual demo rather than any VISTA dataset or AI/VLM use.

There is no trustworthy source-side ``AssetRegistry.bin`` in the pinned
SimWorld project.  Consequently this runner never guesses a dependency closure
from filenames or binary strings.  It first copies the complete ``Content``
tree into a fresh external attempt and creates a minimal sanitized ``Config``;
the source Config is not copied because it contains unrelated runtime/network
settings.  The pinned UE 5.7 editor then builds an in-memory Asset Registry and
validates the target class and recursive dependency closure under ``-nullrhi``.
The source project is never opened by Unreal and is never written.

This is only a private-research compatibility smoke.  It cannot accept or
publish a character provider and makes no runtime, visual-fidelity, animation,
interaction, or redistribution claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

PLAN_SCHEMA = "vista.citysample-crowd-human-forward-load-plan/v1"
REQUEST_SCHEMA = "vista.citysample-crowd-human-forward-load-request/v1"
RESULT_SCHEMA = "vista.citysample-crowd-human-forward-load-result/v1"
HOST_RECEIPT_SCHEMA = "vista.citysample-crowd-human-forward-load-host-receipt/v1"
COPY_MANIFEST_SCHEMA = "vista.citysample-crowd-human-full-content-copy-manifest/v1"
QUARANTINE_SCHEMA = "vista.citysample-crowd-human-forward-load-quarantine/v1"

PINNED_ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
PINNED_BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
PINNED_EDITOR_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
PINNED_SOURCE_PROJECT_SHA256 = (
    "134f3a1414411a9951c286245440f0d9ef4def95a1235f2c58466a08478a6c21"
)
PINNED_TARGET_UASSET_SHA256 = (
    "4deeaef11653c887ab85242cb444a8b3752b611a2a3c7c341d570f0646f82450"
)
PINNED_ARCHIVE_RECEIPT_SHA256 = (
    "5d2d452ed388d053e4395a9c9478d1211806d9ecb8c7c02d8bfcbf8046acbe11"
)

PINNED_SOURCE_PROJECT_SIZE = 567
PINNED_TARGET_UASSET_SIZE = 1_538_864
PINNED_ARCHIVE_RECEIPT_SIZE = 956
PINNED_EDITOR_SIZE = 459_320
PINNED_BUILD_VERSION_SIZE = 215
PINNED_CONTENT_FILE_COUNT = 2_967
PINNED_CONTENT_SIZE_BYTES = 10_218_144_848
PINNED_CONTENT_METADATA_PROJECTION_SHA256 = (
    "a97b341c1fb610d5c40c3396fe0b305cafb7c17319678ff057823a4ac702b0c2"
)

ENGINE_PLUGIN_PINS: Mapping[str, tuple[PurePosixPath, str, int]] = {
    "HairStrands": (
        PurePosixPath("Engine/Plugins/Runtime/HairStrands/HairStrands.uplugin"),
        "f95269163143061d2b13c00f574d5318cbf38d43d385c38b8582f9421a6a294d",
        1_429,
    ),
    "MassGameplay": (
        PurePosixPath("Engine/Plugins/Runtime/MassGameplay/MassGameplay.uplugin"),
        "b516d319d521944f2b6e1fe82d10df256be9331e874cc79d3b9504bb02f9fcf6",
        1_805,
    ),
    "PythonScriptPlugin": (
        PurePosixPath(
            "Engine/Plugins/Experimental/PythonScriptPlugin/PythonScriptPlugin.uplugin"
        ),
        "7a355543790998ba9bf947abc0ac52bdcc942b173d6c863d687d84e95c894699",
        1_006,
    ),
    "RigLogic": (
        PurePosixPath("Engine/Plugins/Animation/RigLogic/RigLogic.uplugin"),
        "c6ce682b00793943614fea31fdae5c201a6a4595f96bf4a901d3657f79e5e340",
        1_044,
    ),
}
REQUIRED_NATIVE_MODULES_BY_PLUGIN = {
    "HairStrands": ("HairStrandsCore",),
    "MassGameplay": ("MassActors",),
    "PythonScriptPlugin": ("PythonScriptPlugin", "PythonScriptPluginPreload"),
    # The pinned Linux editor descriptor loads the two runtime modules and the
    # UncookedOnly/PreDefault developer module.  RigLogicEditor is deliberately
    # excluded because that exact descriptor restricts it to Win64.
    "RigLogic": ("RigLogicLib", "RigLogicModule", "RigLogicDeveloper"),
}
PINNED_ENGINE_BUILD_ID = "47537391"
ENGINE_NATIVE_BINARY_PINS: tuple[Mapping[str, Any], ...] = (
    {
        "binary_relative_path": (
            "Engine/Plugins/Runtime/HairStrands/Binaries/Linux/"
            "libUnrealEditor-HairStrandsCore.so"
        ),
        "binary_sha256": (
            "9c23d053f91222a8a2384cad77e3b97ae26b9e3ba4b2a02cc53bcbd6fbd95849"
        ),
        "binary_size_bytes": 4_211_808,
        "module_name": "HairStrandsCore",
        "modules_receipt_relative_path": (
            "Engine/Plugins/Runtime/HairStrands/Binaries/Linux/UnrealEditor.modules"
        ),
        "plugin_name": "HairStrands",
    },
    {
        "binary_relative_path": (
            "Engine/Plugins/Runtime/MassGameplay/Binaries/Linux/"
            "libUnrealEditor-MassActors.so"
        ),
        "binary_sha256": (
            "06397bf474c86e8ea039a93a6b2c827101cb4d3af4ef244887fa43d39ffaa734"
        ),
        "binary_size_bytes": 552_848,
        "module_name": "MassActors",
        "modules_receipt_relative_path": (
            "Engine/Plugins/Runtime/MassGameplay/Binaries/Linux/UnrealEditor.modules"
        ),
        "plugin_name": "MassGameplay",
    },
    {
        "binary_relative_path": (
            "Engine/Plugins/Experimental/PythonScriptPlugin/Binaries/Linux/"
            "libUnrealEditor-PythonScriptPlugin.so"
        ),
        "binary_sha256": (
            "0bdb1456413da669eae53cf61795c25a70376050445d340e8277b452a66032be"
        ),
        "binary_size_bytes": 7_959_824,
        "module_name": "PythonScriptPlugin",
        "modules_receipt_relative_path": (
            "Engine/Plugins/Experimental/PythonScriptPlugin/Binaries/Linux/"
            "UnrealEditor.modules"
        ),
        "plugin_name": "PythonScriptPlugin",
    },
    {
        "binary_relative_path": (
            "Engine/Plugins/Experimental/PythonScriptPlugin/Binaries/Linux/"
            "libUnrealEditor-PythonScriptPluginPreload.so"
        ),
        "binary_sha256": (
            "aaf9458af7925a23fc003f258115027f20cb2640c0c742196a5f1ee3ae7a2655"
        ),
        "binary_size_bytes": 364_128,
        "module_name": "PythonScriptPluginPreload",
        "modules_receipt_relative_path": (
            "Engine/Plugins/Experimental/PythonScriptPlugin/Binaries/Linux/"
            "UnrealEditor.modules"
        ),
        "plugin_name": "PythonScriptPlugin",
    },
    {
        "binary_relative_path": (
            "Engine/Plugins/Animation/RigLogic/Binaries/Linux/"
            "libUnrealEditor-RigLogicLib.so"
        ),
        "binary_sha256": (
            "efda18f1bb2d361ca96833541d4f95e9240c44a491c882dd5cd7ae3beb15968e"
        ),
        "binary_size_bytes": 1_942_744,
        "module_name": "RigLogicLib",
        "modules_receipt_relative_path": (
            "Engine/Plugins/Animation/RigLogic/Binaries/Linux/UnrealEditor.modules"
        ),
        "plugin_name": "RigLogic",
    },
    {
        "binary_relative_path": (
            "Engine/Plugins/Animation/RigLogic/Binaries/Linux/"
            "libUnrealEditor-RigLogicModule.so"
        ),
        "binary_sha256": (
            "c5244c83d59cbfda87e07554c7f59da04601202f23ca69a191d26f670b067b64"
        ),
        "binary_size_bytes": 849_728,
        "module_name": "RigLogicModule",
        "modules_receipt_relative_path": (
            "Engine/Plugins/Animation/RigLogic/Binaries/Linux/UnrealEditor.modules"
        ),
        "plugin_name": "RigLogic",
    },
    {
        "binary_relative_path": (
            "Engine/Plugins/Animation/RigLogic/Binaries/Linux/"
            "libUnrealEditor-RigLogicDeveloper.so"
        ),
        "binary_sha256": (
            "d53c036d5f4b7e695f1d1107de0ab248bdf29fa41979580c9f4d89d0053fdefb"
        ),
        "binary_size_bytes": 59_464,
        "module_name": "RigLogicDeveloper",
        "modules_receipt_relative_path": (
            "Engine/Plugins/Animation/RigLogic/Binaries/Linux/UnrealEditor.modules"
        ),
        "plugin_name": "RigLogic",
    },
)
ENGINE_MODULES_RECEIPT_PINS: tuple[Mapping[str, Any], ...] = (
    {
        "module_bindings": {
            "HairStrandsCore": "libUnrealEditor-HairStrandsCore.so",
        },
        "modules_receipt_build_id": PINNED_ENGINE_BUILD_ID,
        "modules_receipt_relative_path": (
            "Engine/Plugins/Runtime/HairStrands/Binaries/Linux/UnrealEditor.modules"
        ),
        "modules_receipt_sha256": (
            "915bfaaaa00fb6e8bae41b5ca3f7ca1bc61814ca8e1cc84dc6bd19e0f44f70ad"
        ),
        "modules_receipt_size_bytes": 510,
        "plugin_name": "HairStrands",
    },
    {
        "module_bindings": {
            "MassActors": "libUnrealEditor-MassActors.so",
        },
        "modules_receipt_build_id": PINNED_ENGINE_BUILD_ID,
        "modules_receipt_relative_path": (
            "Engine/Plugins/Runtime/MassGameplay/Binaries/Linux/UnrealEditor.modules"
        ),
        "modules_receipt_sha256": (
            "0e5ce59af3f6285cdc48124c15dad7c2fe8a76321d29a882913b04c7ba80ed78"
        ),
        "modules_receipt_size_bytes": 971,
        "plugin_name": "MassGameplay",
    },
    {
        "module_bindings": {
            "PythonScriptPlugin": "libUnrealEditor-PythonScriptPlugin.so",
            "PythonScriptPluginPreload": (
                "libUnrealEditor-PythonScriptPluginPreload.so"
            ),
        },
        "modules_receipt_build_id": PINNED_ENGINE_BUILD_ID,
        "modules_receipt_relative_path": (
            "Engine/Plugins/Experimental/PythonScriptPlugin/Binaries/Linux/"
            "UnrealEditor.modules"
        ),
        "modules_receipt_sha256": (
            "6f436c8e22ce1b75ac0721a91a257b731131932b80b9328835cbb1e361aaff3b"
        ),
        "modules_receipt_size_bytes": 189,
        "plugin_name": "PythonScriptPlugin",
    },
    {
        "module_bindings": {
            "RigLogicDeveloper": "libUnrealEditor-RigLogicDeveloper.so",
            "RigLogicLib": "libUnrealEditor-RigLogicLib.so",
            "RigLogicModule": "libUnrealEditor-RigLogicModule.so",
        },
        "modules_receipt_build_id": PINNED_ENGINE_BUILD_ID,
        "modules_receipt_relative_path": (
            "Engine/Plugins/Animation/RigLogic/Binaries/Linux/UnrealEditor.modules"
        ),
        "modules_receipt_sha256": (
            "d92089953171e325bb03cf40be10138ee1d77d4143d0e529eb62fc9233b2ab62"
        ),
        "modules_receipt_size_bytes": 273,
        "plugin_name": "RigLogic",
    },
)

DEFAULT_ENGINE_ROOT = Path("/mnt/NAS2/yhliu/UE_5.7.3_prebuilt")
DEFAULT_SOURCE_ROOT = Path(
    "/mnt/NAS2/yhliu/SimWorldStudio/0.2.0-806e869a/runtime/"
    "SimWorld-Studio-Minimal-806e869a/gym_citynav"
)
DEFAULT_ARCHIVE_RECEIPT = Path(
    "/mnt/NAS2/yhliu/SimWorldStudio/0.2.0-806e869a/receipts/archive-receipt.json"
)
DEFAULT_RUN_ROOT = Path("/data/sysx/vista-world/runs/vista-action-world-r1")

SOURCE_PROJECT_NAME = "gym_citynav.uproject"
DISPOSABLE_PROJECT_NAME = "VistaCitySampleCrowdSmoke.uproject"
TARGET_RELATIVE = PurePosixPath(
    "Content/CitySampleCrowd/Blueprints/BP_CrowdCharacter.uasset"
)
TARGET_PACKAGE = "/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter"
TARGET_OBJECT = TARGET_PACKAGE + ".BP_CrowdCharacter"
TARGET_CLASS = TARGET_OBJECT + "_C"
TARGET_CDO_PATH = TARGET_PACKAGE + ".Default__BP_CrowdCharacter_C"
TARGET_ROOT = "/Game/CitySampleCrowd"

# These byte pins prove that the copied source contains concrete animation,
# skeletal-mesh, and skeleton candidates.  UE's Asset Registry must still show
# that the target's recursive hard/soft dependency closure reaches each class
# category; the runner does not infer dependency authority from these files.
KEY_SOURCE_PINS: Mapping[PurePosixPath, tuple[str, int, str]] = {
    PurePosixPath("Content/CitySampleCrowd/Blueprints/NPC1_AnimBP.uasset"): (
        "a106aa2c1ca33b05ab345c5ff5710d7f62f147e2503e45deae5a77d8754ded99",
        44_040,
        "anim_blueprint",
    ),
    PurePosixPath(
        "Content/CitySampleCrowd/Character/Female/NormalWeight/Meshes/"
        "f_tal_nrw_body.uasset"
    ): (
        "893c97319068efb07c2caf66351598ce69dffd83451daf132ca8a2c4db45caf7",
        4_289_289,
        "skeletal_mesh",
    ),
    PurePosixPath(
        "Content/CitySampleCrowd/Character/Shared/Rig/metahuman_base_skel.uasset"
    ): (
        "03b5e510a1a0eb47a7807254d2f54857543f41f448442af182a31fd863a1184e",
        375_871,
        "skeleton",
    ),
}
KEY_KIND_ASSET_CLASSES = {
    "anim_blueprint": "AnimBlueprint",
    "skeletal_mesh": "SkeletalMesh",
    "skeleton": "Skeleton",
}

SANITIZED_CONFIG_FILES: Mapping[PurePosixPath, bytes] = {
    PurePosixPath("Config/DefaultEngine.ini"): (
        b"[/Script/Engine.RendererSettings]\n"
        b"r.VirtualTextures=True\n"
        b"r.GPUSkin.Support16BitBoneIndex=True\n"
        b"r.GPUSkin.UnlimitedBoneInfluences=True\n"
        b"r.SkinCache.CompileShaders=True\n"
        b"\n"
        b"[/Script/AndroidFileServerEditor.AndroidFileServerRuntimeSettings]\n"
        b"bEnablePlugin=False\n"
        b"bAllowNetworkConnection=False\n"
        b"bIncludeInShipping=False\n"
        b"bAllowExternalStartInShipping=False\n"
        b"bCompileAFSProject=False\n"
    ),
    PurePosixPath("Config/DefaultGame.ini"): (
        b"[/Script/EngineSettings.GeneralProjectSettings]\n"
        b"ProjectName=VistaCitySampleCrowdSmoke\n"
    ),
}

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMMANDLET_SOURCE = (
    Path(__file__).resolve().with_name("citysample_crowd_human_smoke_commandlet.py")
)
RUNNER_SOURCE = Path(__file__).resolve()
EDITOR_RELATIVE = PurePosixPath("Engine/Binaries/Linux/UnrealEditor-Cmd")
BUILD_VERSION_RELATIVE = PurePosixPath("Engine/Build/Build.version")

PLAN_NAME = "citysample-crowd-human-plan.json"
COPY_MANIFEST_NAME = "citysample-crowd-human-copy-manifest.json"
COMMANDLET_NAME = "citysample_crowd_human_smoke_commandlet.py"
REQUEST_NAME = "citysample-crowd-human-request.json"
RESULT_NAME = "citysample-crowd-human-result.json"
HOST_RECEIPT_NAME = "citysample-crowd-human-host-receipt.json"
QUARANTINE_NAME = "CITYSAMPLE_CROWD_HUMAN_QUARANTINED.json"
LOG_NAME = "citysample-crowd-human-unreal.log"
ISOLATED_RUNTIME_DIRECTORIES = (
    "runtime-home",
    "runtime-cache",
    "runtime-config",
    "runtime-data",
    "runtime-state",
    "runtime-tmp",
)
FIXED_COMMAND_ARGUMENTS_AFTER_SCRIPT = (
    "-nullrhi",
    "-NoSound",
    "-unattended",
    "-nop4",
    "-nosplash",
    "-NoAssetRegistryCache",
    "-NoEpicPortal",
    "-NoLauncher",
    "-NoAnalytics",
    "-NoMessaging",
    "-NoUdpMessaging",
    "-NoTcpMessaging",
    "-NoWebSockets",
    "-NoHttp",
    "-stdout",
    "-FullStdOutLogOutput",
    "-UTF8Output",
)
NETWORK_TRANSPORT_DISABLE_FLAGS = (
    "-NoMessaging",
    "-NoUdpMessaging",
    "-NoTcpMessaging",
    "-NoWebSockets",
    "-NoHttp",
)
FORBIDDEN_COMMAND_ARGUMENTS = frozenset(
    {"-Messaging", "-UdpMessaging", "-TcpMessaging", "-WebSockets"}
)
ACKNOWLEDGEMENT_KEYS = (
    "private_noncommercial_research",
    "epic_ue_only_content_entitlement",
    "no_redistribution",
    "source_uassets_outside_git",
    "large_full_content_copy",
    "metahuman_visual_demo_only_not_ai_training_testing",
)

REQUEST_ENV = "VISTA_CITYSAMPLE_CROWD_HUMAN_REQUEST"
REQUEST_SHA_ENV = "VISTA_CITYSAMPLE_CROWD_HUMAN_REQUEST_SHA256"
RESULT_ENV = "VISTA_CITYSAMPLE_CROWD_HUMAN_RESULT"
RESULT_SHA_ENV = "VISTA_CITYSAMPLE_CROWD_HUMAN_RESULT_SHA256"

ATTEMPT_RE = re.compile(
    r"^citysample-crowd-human-smoke-[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_FILES = 100_000
MAX_SOURCE_BYTES = 128 * 1024**3
MAX_JSON_BYTES = 32 * 1024 * 1024
COPY_BLOCK_BYTES = 4 * 1024 * 1024
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
COMMAND_TIMEOUT_SECONDS = 2 * 60 * 60
PROCESS_GROUP_GRACE_SECONDS = 5


class CitySampleCrowdSmokeError(RuntimeError):
    """Stable host-side failure for the private-research smoke."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise CitySampleCrowdSmokeError(code, message)


def canonical_json(value: Any, *, newline: bool = True) -> bytes:
    try:
        raw = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CitySampleCrowdSmokeError(
            "JSON_INVALID", "value is not finite canonical JSON"
        ) from exc
    return raw + (b"\n" if newline else b"")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _content_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    return _sha256_bytes(canonical_json(body))


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
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
    path: Path
    sha256: str
    size_bytes: int
    identity: tuple[int, int, int, int, int, int]
    raw: bytes | None = None


@dataclass(frozen=True)
class TreeEntry:
    source: Path
    relative: PurePosixPath
    size_bytes: int
    identity: tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class SmokeConfig:
    engine_root: Path
    source_root: Path
    archive_receipt: Path
    run_root: Path
    attempt_name: str

    @property
    def attempt_root(self) -> Path:
        return self.run_root / self.attempt_name


@dataclass(frozen=True)
class SmokePlan:
    config: SmokeConfig
    report: Mapping[str, Any]
    report_raw: bytes
    request: Mapping[str, Any]
    request_raw: bytes
    runner_seal: FileSeal
    commandlet_seal: FileSeal
    editor_seal: FileSeal
    engine_plugin_seals: tuple[FileSeal, ...]
    engine_native_binary_seals: tuple[FileSeal, ...]
    engine_modules_receipt_seals: tuple[FileSeal, ...]
    fixed_source_seals: tuple[FileSeal, ...]
    tree_entries: tuple[TreeEntry, ...]


@dataclass(frozen=True)
class ExecutionContract:
    command: tuple[str, ...]
    environment: Mapping[str, str]
    evidence: Mapping[str, Any]


def _canonical_existing_directory(path: Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute() or ".." in candidate.parts:
        _fail("PATH_INVALID", f"{label} must be absolute and traversal-free")
    try:
        metadata = os.lstat(candidate)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise CitySampleCrowdSmokeError(
            "PATH_UNAVAILABLE", f"{label} is unavailable"
        ) from exc
    if not stat.S_ISDIR(metadata.st_mode) or resolved != candidate:
        _fail("PATH_INVALID", f"{label} must be a canonical non-symlink directory")
    return candidate


def _child(root: Path, relative: PurePosixPath, *, label: str) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise AssertionError(f"fixed {label} path escaped")
    path = root.joinpath(*relative.parts)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise CitySampleCrowdSmokeError(
            "SOURCE_INVALID", f"fixed {label} is unavailable or escaped"
        ) from exc
    return resolved


def _seal_file(
    path: Path,
    *,
    label: str,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    capture: bool = False,
    executable: bool = False,
) -> FileSeal:
    descriptor = -1
    captured = bytearray() if capture else None
    digest = hashlib.sha256()
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            _fail("SOURCE_INVALID", f"{label} must be a single-link regular file")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            _fail("SOURCE_CHANGED", f"{label} changed while opening")
        while True:
            block = os.read(descriptor, COPY_BLOCK_BYTES)
            if not block:
                break
            digest.update(block)
            if captured is not None:
                captured.extend(block)
        after = os.fstat(descriptor)
        path_after = os.lstat(path)
    except CitySampleCrowdSmokeError:
        raise
    except OSError as exc:
        raise CitySampleCrowdSmokeError(
            "SOURCE_UNREADABLE", f"could not read {label}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if _identity(opened) != _identity(after) or _identity(after) != _identity(
        path_after
    ):
        _fail("SOURCE_CHANGED", f"{label} changed while reading")
    observed = digest.hexdigest()
    if expected_sha256 is not None and observed != expected_sha256:
        _fail("SOURCE_PIN_MISMATCH", f"{label} SHA-256 differs")
    if expected_size is not None and after.st_size != expected_size:
        _fail("SOURCE_PIN_MISMATCH", f"{label} size differs")
    if executable and not (after.st_mode & stat.S_IXUSR):
        _fail("SOURCE_NOT_EXECUTABLE", f"{label} is not owner-executable")
    return FileSeal(
        path=path,
        sha256=observed,
        size_bytes=after.st_size,
        identity=_identity(after),
        raw=bytes(captured) if captured is not None else None,
    )


def _strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        _fail("JSON_INVALID", f"{label} exceeds the maximum size")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CitySampleCrowdSmokeError(
            "JSON_INVALID", f"{label} is not strict UTF-8 JSON"
        ) from exc
    if type(value) is not dict:
        _fail("JSON_INVALID", f"{label} must be an object")
    return value


def _reject_git_ancestor(path: Path) -> None:
    current = path if path.exists() else path.parent
    while True:
        marker = current / ".git"
        try:
            metadata = os.lstat(marker)
        except FileNotFoundError:
            metadata = None
        except OSError as exc:
            raise CitySampleCrowdSmokeError(
                "GIT_GUARD_FAILED", "could not inspect destination ancestors"
            ) from exc
        if metadata is not None:
            _fail(
                "DESTINATION_IN_GIT",
                "source-format Epic UAssets may not be copied below Git metadata",
            )
        parent = current.parent
        if parent == current:
            return
        current = parent


def _inventory_tree(root: Path, prefix: str) -> tuple[TreeEntry, ...]:
    entries: list[TreeEntry] = []
    total_bytes = 0

    def visit(directory: Path, relative_directory: PurePosixPath) -> None:
        nonlocal total_bytes
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise CitySampleCrowdSmokeError(
                "SOURCE_INVENTORY_FAILED", "could not enumerate source project tree"
            ) from exc
        for child in children:
            if child.name in {".", ".."} or "/" in child.name or "\0" in child.name:
                _fail("SOURCE_INVALID", "source tree contains an unsafe name")
            relative = relative_directory / child.name
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise CitySampleCrowdSmokeError(
                    "SOURCE_INVENTORY_FAILED", "could not stat source project tree"
                ) from exc
            if stat.S_ISLNK(metadata.st_mode):
                _fail("SOURCE_INVALID", "source tree contains a symbolic link")
            if stat.S_ISDIR(metadata.st_mode):
                visit(Path(child.path), relative)
                continue
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                _fail("SOURCE_INVALID", "source tree contains a non-regular entry")
            total_bytes += metadata.st_size
            if len(entries) >= MAX_FILES or total_bytes > MAX_SOURCE_BYTES:
                _fail("SOURCE_TOO_LARGE", "source tree exceeds the closed copy bounds")
            entries.append(
                TreeEntry(
                    source=Path(child.path),
                    relative=PurePosixPath(prefix) / relative,
                    size_bytes=metadata.st_size,
                    identity=_identity(metadata),
                )
            )

    visit(root, PurePosixPath())
    return tuple(entries)


def _tree_projection(entries: Sequence[TreeEntry]) -> str:
    projection = [
        {
            "relative_path": entry.relative.as_posix(),
            "size_bytes": entry.size_bytes,
            "mtime_ns": entry.identity[3],
        }
        for entry in entries
    ]
    return _sha256_bytes(canonical_json(projection))


def _source_inventory(source_root: Path) -> tuple[TreeEntry, ...]:
    content = _child(source_root, PurePosixPath("Content"), label="Content tree")
    if not content.is_dir():
        _fail("SOURCE_INVALID", "source Content must be a directory")
    entries = _inventory_tree(content, "Content")
    paths = [entry.relative.as_posix() for entry in entries]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        _fail("SOURCE_INVALID", "source projection is not unique and sorted")
    return entries


def _find_source_asset_registries(source_root: Path) -> tuple[Path, ...]:
    """Find registries without trusting or parsing them and without following links."""

    found: list[Path] = []
    visited = 0
    pending = [source_root]
    while pending:
        directory = pending.pop()
        try:
            children = tuple(os.scandir(directory))
        except OSError as exc:
            raise CitySampleCrowdSmokeError(
                "SOURCE_INVENTORY_FAILED",
                "could not audit source Asset Registry presence",
            ) from exc
        for child in children:
            visited += 1
            if visited > MAX_FILES * 4:
                _fail(
                    "SOURCE_TOO_LARGE", "source project entry count exceeds audit bound"
                )
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise CitySampleCrowdSmokeError(
                    "SOURCE_INVENTORY_FAILED", "could not stat source project entry"
                ) from exc
            if stat.S_ISLNK(metadata.st_mode):
                _fail("SOURCE_INVALID", "source project contains a symbolic link")
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(Path(child.path))
            elif stat.S_ISREG(metadata.st_mode) and child.name == "AssetRegistry.bin":
                found.append(Path(child.path))
    return tuple(sorted(found))


def _archive_receipt(raw: bytes) -> Mapping[str, Any]:
    receipt = _strict_json(raw, label="archive receipt")
    expected = {
        "schema": "vista-simworld-archive-receipt/v1",
        "repository": "SimWorld-AI/SimWorld-Studio",
        "repository_type": "dataset",
        "dataset_revision": "26bdd2ca18f06ab455023b0a602ede60b3afb243",
        "filename": "SimWorld-Studio-Minimal.tar.gz",
        "expected_size_bytes": 15_170_703_068,
        "actual_size_bytes": 15_170_703_068,
        "expected_sha256": (
            "806e869ad1c65b298f05a39854b28e4188bb50817f539744451849e054990e2f"
        ),
        "actual_sha256": (
            "806e869ad1c65b298f05a39854b28e4188bb50817f539744451849e054990e2f"
        ),
        "verified": True,
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            _fail("ARCHIVE_RECEIPT_INVALID", f"archive receipt field {key!r} differs")
    return receipt


def _disposable_project_descriptor(source_raw: bytes) -> bytes:
    source = _strict_json(source_raw, label="source project descriptor")
    if source.get("FileVersion") != 3 or source.get("TargetPlatforms") != ["Linux"]:
        _fail("SOURCE_PROJECT_INVALID", "source project descriptor contract differs")
    source_plugins = source.get("Plugins")
    if type(source_plugins) is not list:
        _fail("SOURCE_PROJECT_INVALID", "source project plugin inventory differs")
    allowed = {"PythonScriptPlugin", "EditorScriptingUtilities", "SunPosition"}
    plugins = []
    for entry in source_plugins:
        if type(entry) is not dict or type(entry.get("Name")) is not str:
            _fail("SOURCE_PROJECT_INVALID", "source project plugin entry differs")
        if entry["Name"] in allowed:
            plugins.append({"Enabled": True, "Name": entry["Name"]})
    if {item["Name"] for item in plugins} != allowed:
        _fail("SOURCE_PROJECT_INVALID", "required editor plugins are unavailable")
    existing_plugin_names = {item["Name"] for item in plugins}
    plugins.extend(
        {"Enabled": True, "Name": plugin_name}
        for plugin_name in ENGINE_PLUGIN_PINS
        if plugin_name not in existing_plugin_names
    )
    # UE may otherwise auto-enable AndroidFileServer and append a random
    # SecurityToken to DefaultEngine.ini before the Python commandlet runs.
    # Keep both the descriptor and sanitized INI pinned so any startup mutation
    # remains a hard manifest failure rather than an accepted random token.
    plugins.append({"Enabled": False, "Name": "AndroidFileServer"})
    # Project modules and enabled network/streaming plugins are intentionally
    # absent: this audit needs only source-format content and editor Python.
    descriptor = {
        "Category": "Private Research",
        "Description": "Disposable CitySampleCrowd UE 5.7 forward-load smoke",
        "EngineAssociation": "5.7",
        "FileVersion": 3,
        "Plugins": sorted(plugins, key=lambda item: item["Name"]),
        "TargetPlatforms": ["Linux"],
    }
    return canonical_json(descriptor)


def _engine_plugin_descriptor_records(
    seals: Sequence[FileSeal],
) -> list[dict[str, Any]]:
    if len(seals) != len(ENGINE_PLUGIN_PINS) or set(ENGINE_PLUGIN_PINS) != set(
        REQUIRED_NATIVE_MODULES_BY_PLUGIN
    ):
        raise AssertionError("engine plugin descriptor seal inventory differs")
    records = []
    for (name, (relative, expected_sha, expected_size)), seal in zip(
        ENGINE_PLUGIN_PINS.items(), seals, strict=True
    ):
        if seal.sha256 != expected_sha or seal.size_bytes != expected_size:
            raise AssertionError("validated engine plugin descriptor seal differs")
        records.append(
            {
                "name": name,
                "relative_path": relative.as_posix(),
                "required_native_modules": list(
                    REQUIRED_NATIVE_MODULES_BY_PLUGIN[name]
                ),
                "sha256": seal.sha256,
                "size_bytes": seal.size_bytes,
            }
        )
    return records


def _revalidate_engine_plugin_descriptors(
    plan: SmokePlan,
) -> list[dict[str, Any]]:
    expected = _engine_plugin_descriptor_records(plan.engine_plugin_seals)
    if plan.request.get("engine_plugin_descriptors") != expected:
        _fail(
            "ENGINE_PLUGIN_PIN_MISMATCH",
            "planned engine plugin descriptor pins differ",
        )
    evidence = []
    for record, seal in zip(expected, plan.engine_plugin_seals, strict=True):
        _assert_seal_unchanged(seal, label=f"UE 5.7 {record['name']} plugin descriptor")
        if seal.raw is None:
            raise AssertionError("captured engine plugin descriptor is unavailable")
        descriptor = _strict_json(seal.raw, label=f"{record['name']} plugin descriptor")
        modules = descriptor.get("Modules")
        if type(modules) is not list or not set(
            record["required_native_modules"]
        ).issubset({module.get("Name") for module in modules if type(module) is dict}):
            _fail(
                "ENGINE_PLUGIN_PIN_MISMATCH",
                f"{record['name']} required native module inventory differs",
            )
        evidence.append({**record, "descriptor_file_validated": True})
    return evidence


def _validated_native_binary_pin(pin: Mapping[str, Any]) -> dict[str, Any]:
    required_keys = {
        "binary_relative_path",
        "binary_sha256",
        "binary_size_bytes",
        "module_name",
        "modules_receipt_relative_path",
        "plugin_name",
    }
    if type(pin) is not dict or set(pin) != required_keys:
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "native binary pin key inventory differs",
        )
    string_keys = required_keys - {"binary_size_bytes"}
    if any(type(pin[key]) is not str or not pin[key] for key in string_keys):
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "native binary pin string value differs",
        )
    if type(pin["binary_size_bytes"]) is not int or pin["binary_size_bytes"] <= 0:
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "native binary pin size differs",
        )
    if SHA256_RE.fullmatch(pin["binary_sha256"]) is None:
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "native binary SHA-256 pin differs",
        )
    binary_relative = PurePosixPath(pin["binary_relative_path"])
    receipt_relative = PurePosixPath(pin["modules_receipt_relative_path"])
    if (
        binary_relative.is_absolute()
        or receipt_relative.is_absolute()
        or ".." in binary_relative.parts
        or ".." in receipt_relative.parts
        or binary_relative.parts[:2] != ("Engine", "Plugins")
        or receipt_relative.parts[:2] != ("Engine", "Plugins")
        or binary_relative.parent != receipt_relative.parent
        or receipt_relative.name != "UnrealEditor.modules"
    ):
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "native binary path or receipt association differs",
        )
    return dict(pin)


def _validated_modules_receipt_pin(pin: Mapping[str, Any]) -> dict[str, Any]:
    required_keys = {
        "module_bindings",
        "modules_receipt_build_id",
        "modules_receipt_relative_path",
        "modules_receipt_sha256",
        "modules_receipt_size_bytes",
        "plugin_name",
    }
    if type(pin) is not dict or set(pin) != required_keys:
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "modules receipt pin key inventory differs",
        )
    if (
        any(
            type(pin[key]) is not str or not pin[key]
            for key in required_keys - {"module_bindings", "modules_receipt_size_bytes"}
        )
        or type(pin["modules_receipt_size_bytes"]) is not int
        or pin["modules_receipt_size_bytes"] <= 0
        or SHA256_RE.fullmatch(pin["modules_receipt_sha256"]) is None
        or pin["modules_receipt_build_id"] != PINNED_ENGINE_BUILD_ID
    ):
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "modules receipt scalar pin differs",
        )
    bindings = pin["module_bindings"]
    if (
        type(bindings) is not dict
        or not bindings
        or any(
            type(module) is not str
            or not module
            or type(filename) is not str
            or not filename.startswith("libUnrealEditor-")
            or not filename.endswith(".so")
            or "/" in filename
            for module, filename in bindings.items()
        )
    ):
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "modules receipt binding inventory differs",
        )
    receipt_relative = PurePosixPath(pin["modules_receipt_relative_path"])
    if (
        receipt_relative.is_absolute()
        or ".." in receipt_relative.parts
        or receipt_relative.parts[:2] != ("Engine", "Plugins")
        or receipt_relative.name != "UnrealEditor.modules"
    ):
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "modules receipt path differs",
        )
    return {
        **dict(pin),
        "module_bindings": dict(sorted(bindings.items())),
    }


def _native_authority_inventory(
    binary_pins: Sequence[Mapping[str, Any]],
    receipt_pins: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    binaries = [_validated_native_binary_pin(pin) for pin in binary_pins]
    receipts = [_validated_modules_receipt_pin(pin) for pin in receipt_pins]
    binary_paths = [pin["binary_relative_path"] for pin in binaries]
    receipt_paths = [pin["modules_receipt_relative_path"] for pin in receipts]
    if (
        len(binary_paths) != len(set(binary_paths))
        or len(receipt_paths) != len(set(receipt_paths))
        or set(binary_paths).intersection(receipt_paths)
        or len({pin["module_name"] for pin in binaries}) != len(binaries)
    ):
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "native authority distinct-file inventory differs",
        )
    required_modules_by_plugin = {
        plugin_name: sorted(module_names)
        for plugin_name, module_names in REQUIRED_NATIVE_MODULES_BY_PLUGIN.items()
    }
    observed_modules_by_plugin: dict[str, list[str]] = {}
    for binary in binaries:
        observed_modules_by_plugin.setdefault(binary["plugin_name"], []).append(
            binary["module_name"]
        )
    observed_modules_by_plugin = {
        plugin_name: sorted(module_names)
        for plugin_name, module_names in observed_modules_by_plugin.items()
    }
    if observed_modules_by_plugin != required_modules_by_plugin or {
        pin["plugin_name"] for pin in receipts
    } != set(required_modules_by_plugin):
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "native binaries do not exactly cover required plugin modules",
        )
    receipt_by_path = {pin["modules_receipt_relative_path"]: pin for pin in receipts}
    receipt_use_counts = {path: 0 for path in receipt_paths}
    for binary in binaries:
        receipt = receipt_by_path.get(binary["modules_receipt_relative_path"])
        if (
            receipt is None
            or receipt["plugin_name"] != binary["plugin_name"]
            or receipt["module_bindings"].get(binary["module_name"])
            != PurePosixPath(binary["binary_relative_path"]).name
        ):
            _fail(
                "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
                "native binary is not bound by its exact modules receipt",
            )
        receipt_use_counts[binary["modules_receipt_relative_path"]] += 1
    if any(count < 1 for count in receipt_use_counts.values()):
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "an unreferenced modules receipt pin is present",
        )
    return {
        "binary_file_count": len(binary_paths),
        "distinct_file_count": len(binary_paths) + len(receipt_paths),
        "modules_receipt_file_count": len(receipt_paths),
        "shared_modules_receipt_paths": sorted(
            path for path, count in receipt_use_counts.items() if count > 1
        ),
    }


def _exact_engine_file(
    engine_root: Path, relative: PurePosixPath, *, label: str
) -> Path:
    candidate = engine_root.joinpath(*relative.parts)
    resolved = _child(engine_root, relative, label=label)
    if resolved != candidate:
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            f"{label} must be the exact canonical engine file",
        )
    return candidate


def _validate_modules_receipt(
    pin: Mapping[str, Any], receipt_raw: bytes, *, label: str
) -> None:
    receipt = _strict_json(receipt_raw, label=label)
    modules = receipt.get("Modules")
    if (
        receipt.get("BuildId") != pin["modules_receipt_build_id"]
        or type(modules) is not dict
        or any(
            modules.get(module) != filename
            for module, filename in pin["module_bindings"].items()
        )
    ):
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            f"{label} does not bind the exact native module binary",
        )


def _seal_engine_native_authority(
    engine_root: Path,
) -> tuple[tuple[FileSeal, ...], tuple[FileSeal, ...]]:
    _native_authority_inventory(ENGINE_NATIVE_BINARY_PINS, ENGINE_MODULES_RECEIPT_PINS)
    binaries: list[FileSeal] = []
    for raw_pin in ENGINE_NATIVE_BINARY_PINS:
        pin = _validated_native_binary_pin(raw_pin)
        binary_relative = PurePosixPath(pin["binary_relative_path"])
        binary = _seal_file(
            _exact_engine_file(
                engine_root,
                binary_relative,
                label=f"{pin['module_name']} native module binary",
            ),
            label=f"UE 5.7 {pin['module_name']} native module binary",
            expected_sha256=pin["binary_sha256"],
            expected_size=pin["binary_size_bytes"],
        )
        binaries.append(binary)
    receipts: list[FileSeal] = []
    for raw_pin in ENGINE_MODULES_RECEIPT_PINS:
        pin = _validated_modules_receipt_pin(raw_pin)
        receipt_relative = PurePosixPath(pin["modules_receipt_relative_path"])
        receipt = _seal_file(
            _exact_engine_file(
                engine_root,
                receipt_relative,
                label=f"{pin['plugin_name']} module receipt",
            ),
            label=f"UE 5.7 {pin['plugin_name']} UnrealEditor.modules receipt",
            expected_sha256=pin["modules_receipt_sha256"],
            expected_size=pin["modules_receipt_size_bytes"],
            capture=True,
        )
        if receipt.raw is None:
            raise AssertionError("captured UnrealEditor.modules receipt is unavailable")
        _validate_modules_receipt(
            pin,
            receipt.raw,
            label=f"{pin['plugin_name']} UnrealEditor.modules receipt",
        )
        receipts.append(receipt)
    return tuple(binaries), tuple(receipts)


def _native_authority_request(
    binary_seals: Sequence[FileSeal],
    receipt_seals: Sequence[FileSeal],
) -> dict[str, Any]:
    if len(binary_seals) != len(ENGINE_NATIVE_BINARY_PINS) or len(receipt_seals) != len(
        ENGINE_MODULES_RECEIPT_PINS
    ):
        raise AssertionError("native authority seal inventory differs")
    binaries = []
    for raw_pin, seal in zip(ENGINE_NATIVE_BINARY_PINS, binary_seals, strict=True):
        pin = _validated_native_binary_pin(raw_pin)
        if (
            seal.sha256 != pin["binary_sha256"]
            or seal.size_bytes != pin["binary_size_bytes"]
        ):
            raise AssertionError("validated native binary seal differs")
        binaries.append(pin)
    receipts = []
    for raw_pin, seal in zip(ENGINE_MODULES_RECEIPT_PINS, receipt_seals, strict=True):
        pin = _validated_modules_receipt_pin(raw_pin)
        if (
            seal.sha256 != pin["modules_receipt_sha256"]
            or seal.size_bytes != pin["modules_receipt_size_bytes"]
        ):
            raise AssertionError("validated modules receipt seal differs")
        receipts.append(pin)
    return {
        "binary_files": binaries,
        "inventory": _native_authority_inventory(binaries, receipts),
        "modules_receipt_files": receipts,
    }


def _expected_native_module_evidence(
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    binaries = authority.get("binary_files")
    receipts = authority.get("modules_receipt_files")
    if type(binaries) is not list or type(receipts) is not list:
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "native authority request shape differs",
        )
    inventory = _native_authority_inventory(binaries, receipts)
    if authority.get("inventory") != inventory or set(authority) != {
        "binary_files",
        "inventory",
        "modules_receipt_files",
    }:
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "native authority request inventory differs",
        )
    return {
        "binary_files": [
            {
                **_validated_native_binary_pin(pin),
                "binary_file_validated": True,
            }
            for pin in binaries
        ],
        "inventory": inventory,
        "modules_receipt_files": [
            {
                **_validated_modules_receipt_pin(pin),
                "modules_receipt_binding_validated": True,
            }
            for pin in receipts
        ],
    }


def _revalidate_engine_native_module_authority(
    plan: SmokePlan,
) -> dict[str, Any]:
    expected_authority = _native_authority_request(
        plan.engine_native_binary_seals,
        plan.engine_modules_receipt_seals,
    )
    if plan.request.get("engine_native_authority") != expected_authority:
        _fail(
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "planned native authority request differs",
        )
    for pin, binary in zip(
        expected_authority["binary_files"],
        plan.engine_native_binary_seals,
        strict=True,
    ):
        _assert_seal_unchanged(
            binary, label=f"UE 5.7 {pin['module_name']} native module binary"
        )
    for pin, receipt in zip(
        expected_authority["modules_receipt_files"],
        plan.engine_modules_receipt_seals,
        strict=True,
    ):
        _assert_seal_unchanged(
            receipt,
            label=f"UE 5.7 {pin['plugin_name']} UnrealEditor.modules receipt",
        )
        if receipt.raw is None:
            raise AssertionError("captured UnrealEditor.modules receipt is unavailable")
        _validate_modules_receipt(
            pin,
            receipt.raw,
            label=f"{pin['plugin_name']} UnrealEditor.modules receipt",
        )
    return _expected_native_module_evidence(expected_authority)


def _build_request(
    *,
    config: SmokeConfig,
    project_sha256: str,
    commandlet_sha256: str,
    copy_projection_sha256: str,
    key_source_seals: Sequence[FileSeal],
    engine_plugin_seals: Sequence[FileSeal],
    engine_native_binary_seals: Sequence[FileSeal],
    engine_modules_receipt_seals: Sequence[FileSeal],
) -> dict[str, Any]:
    attempt = config.attempt_root
    key_pins = []
    for relative, seal in zip(KEY_SOURCE_PINS, key_source_seals, strict=True):
        expected_sha, expected_size, kind = KEY_SOURCE_PINS[relative]
        if seal.sha256 != expected_sha or seal.size_bytes != expected_size:
            raise AssertionError("validated key source seal differs")
        package = "/Game/" + relative.with_suffix("").relative_to("Content").as_posix()
        asset_class = KEY_KIND_ASSET_CLASSES[kind]
        key_pins.append(
            {
                "asset_class": asset_class,
                "kind": kind,
                "object_path": package + "." + relative.stem,
                "package_name": package,
                "project_relative_path": relative.as_posix(),
                "sha256": seal.sha256,
                "size_bytes": seal.size_bytes,
            }
        )
    request = {
        "schema_version": REQUEST_SCHEMA,
        "attempt_root": str(attempt),
        "project_file": str(attempt / "project" / DISPOSABLE_PROJECT_NAME),
        "project_sha256": project_sha256,
        "commandlet_path": str(attempt / COMMANDLET_NAME),
        "commandlet_sha256": commandlet_sha256,
        "copy_manifest_path": str(attempt / COPY_MANIFEST_NAME),
        "copy_manifest_sha256": None,
        "copy_projection_sha256": copy_projection_sha256,
        "source_content_projection": {
            "file_count": PINNED_CONTENT_FILE_COUNT,
            "size_bytes": PINNED_CONTENT_SIZE_BYTES,
            "metadata_projection_sha256": (PINNED_CONTENT_METADATA_PROJECTION_SHA256),
        },
        "result_path": str(attempt / RESULT_NAME),
        "result_sha256_path": str(attempt / (RESULT_NAME + ".sha256")),
        "engine_version": PINNED_ENGINE_VERSION,
        "engine_plugin_descriptors": _engine_plugin_descriptor_records(
            engine_plugin_seals
        ),
        "engine_native_authority": _native_authority_request(
            engine_native_binary_seals,
            engine_modules_receipt_seals,
        ),
        "target": {
            "asset_class": "Blueprint",
            "class_path": TARGET_CLASS,
            "default_object_path": TARGET_CDO_PATH,
            "generated_class_path": TARGET_CLASS,
            "object_path": TARGET_OBJECT,
            "package_name": TARGET_PACKAGE,
            "project_relative_path": TARGET_RELATIVE.as_posix(),
            "sha256": PINNED_TARGET_UASSET_SHA256,
            "size_bytes": PINNED_TARGET_UASSET_SIZE,
        },
        "key_dependencies": key_pins,
        "dependency_policy": {
            "asset_registry_required": True,
            "include_hard_package_references": True,
            "include_soft_package_references": True,
            "recursive": True,
            "required_asset_classes": ["AnimBlueprint", "SkeletalMesh", "Skeleton"],
            "root": TARGET_ROOT,
        },
        "authorization": {
            "epic_ue_only_content_entitlement_acknowledged": False,
            "large_full_content_copy_acknowledged": False,
            "metahuman_visual_demo_only_not_ai_training_testing_acknowledged": False,
            "no_redistribution_acknowledged": False,
            "private_noncommercial_research_acknowledged": False,
            "source_uassets_outside_git_acknowledged": False,
        },
        "execution_contract": {
            "cuda_visible_devices": "0",
            "display_present": False,
            "fixed_arguments_after_script": list(FIXED_COMMAND_ARGUMENTS_AFTER_SCRIPT),
            "network_transport_disable_flags": list(NETWORK_TRANSPORT_DISABLE_FLAGS),
            "network_ports": [],
            "xauthority_present": False,
        },
        "policy": {
            "accepted": False,
            "append_only_attempt": True,
            "copy_strategy": "full_content_and_sanitized_config_then_registry_audit",
            "gpu": 0,
            "network_ports": [],
            "null_rhi": True,
            "publish_character_provider": False,
            "quarantine_on_failure": True,
            "runtime_visual_acceptance": False,
            "source_project_opened_by_unreal": False,
        },
        "content_digest": "",
    }
    request["content_digest"] = _content_digest(request)
    return request


def plan_smoke(config: SmokeConfig) -> SmokePlan:
    """Return a deterministic, zero-write plan for the fixed local source."""

    engine_root = _canonical_existing_directory(config.engine_root, label="engine root")
    source_root = _canonical_existing_directory(config.source_root, label="source root")
    run_root = _canonical_existing_directory(config.run_root, label="run root")
    if ATTEMPT_RE.fullmatch(config.attempt_name) is None:
        _fail("ATTEMPT_NAME_INVALID", "attempt name does not match the closed prefix")
    normalized = SmokeConfig(
        engine_root=engine_root,
        source_root=source_root,
        archive_receipt=Path(config.archive_receipt),
        run_root=run_root,
        attempt_name=config.attempt_name,
    )
    if normalized.attempt_root.exists():
        _fail(
            "ATTEMPT_EXISTS", "append-only attempt already exists and cannot be reused"
        )
    _reject_git_ancestor(normalized.attempt_root)
    try:
        normalized.attempt_root.relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        _fail("DESTINATION_IN_GIT", "attempt root must remain outside this repository")

    project_seal = _seal_file(
        _child(source_root, PurePosixPath(SOURCE_PROJECT_NAME), label="source project"),
        label="source project descriptor",
        expected_sha256=PINNED_SOURCE_PROJECT_SHA256,
        expected_size=PINNED_SOURCE_PROJECT_SIZE,
        capture=True,
    )
    target_seal = _seal_file(
        _child(source_root, TARGET_RELATIVE, label="target UAsset"),
        label="target CitySampleCrowd UAsset",
        expected_sha256=PINNED_TARGET_UASSET_SHA256,
        expected_size=PINNED_TARGET_UASSET_SIZE,
    )
    archive_seal = _seal_file(
        Path(config.archive_receipt),
        label="SimWorld archive receipt",
        expected_sha256=PINNED_ARCHIVE_RECEIPT_SHA256,
        expected_size=PINNED_ARCHIVE_RECEIPT_SIZE,
        capture=True,
    )
    if archive_seal.raw is None:
        raise AssertionError("captured archive receipt is unavailable")
    archive = _archive_receipt(archive_seal.raw)

    editor_seal = _seal_file(
        _child(engine_root, EDITOR_RELATIVE, label="UE editor"),
        label="UE 5.7 UnrealEditor-Cmd",
        expected_sha256=PINNED_EDITOR_SHA256,
        expected_size=PINNED_EDITOR_SIZE,
        executable=True,
    )
    build_seal = _seal_file(
        _child(engine_root, BUILD_VERSION_RELATIVE, label="UE Build.version"),
        label="UE 5.7 Build.version",
        expected_sha256=PINNED_BUILD_VERSION_SHA256,
        expected_size=PINNED_BUILD_VERSION_SIZE,
        capture=True,
    )
    if build_seal.raw is None:
        raise AssertionError("captured Build.version is unavailable")
    build = _strict_json(build_seal.raw, label="UE Build.version")
    observed_version = (
        f"{build.get('MajorVersion')}.{build.get('MinorVersion')}."
        f"{build.get('PatchVersion')}-{build.get('Changelist')}"
        f"+{build.get('BranchName')}"
    )
    if observed_version != PINNED_ENGINE_VERSION:
        _fail("ENGINE_PIN_MISMATCH", "UE Build.version identity differs")

    engine_plugin_seals = tuple(
        _seal_file(
            _child(engine_root, relative, label=f"{name} plugin descriptor"),
            label=f"UE 5.7 {name} plugin descriptor",
            expected_sha256=expected_sha,
            expected_size=expected_size,
            capture=True,
        )
        for name, (relative, expected_sha, expected_size) in ENGINE_PLUGIN_PINS.items()
    )
    for (name, _), seal in zip(
        ENGINE_PLUGIN_PINS.items(), engine_plugin_seals, strict=True
    ):
        if seal.raw is None:
            raise AssertionError("captured engine plugin descriptor is unavailable")
        descriptor = _strict_json(seal.raw, label=f"{name} plugin descriptor")
        modules = descriptor.get("Modules")
        required_modules = set(REQUIRED_NATIVE_MODULES_BY_PLUGIN[name])
        if type(modules) is not list or not required_modules.issubset(
            {module.get("Name") for module in modules if type(module) is dict}
        ):
            _fail(
                "ENGINE_PLUGIN_PIN_MISMATCH",
                f"{name} descriptor does not provide the required native module",
            )

    (
        engine_native_binary_seals,
        engine_modules_receipt_seals,
    ) = _seal_engine_native_authority(engine_root)
    runner_seal = _seal_file(RUNNER_SOURCE, label="source-controlled smoke runner")
    commandlet_seal = _seal_file(
        COMMANDLET_SOURCE,
        label="source-controlled smoke commandlet",
        capture=True,
    )
    key_source_seals = tuple(
        _seal_file(
            _child(source_root, relative, label=f"key {kind} UAsset"),
            label=f"key {kind} UAsset",
            expected_sha256=expected_sha,
            expected_size=expected_size,
        )
        for relative, (expected_sha, expected_size, kind) in KEY_SOURCE_PINS.items()
    )
    registries = _find_source_asset_registries(source_root)
    if registries:
        _fail(
            "SOURCE_REGISTRY_UNEXPECTED",
            "a source AssetRegistry appeared; dependency strategy needs review",
        )
    tree_entries = _source_inventory(source_root)
    relative_paths = {entry.relative for entry in tree_entries}
    required_paths = {TARGET_RELATIVE, *KEY_SOURCE_PINS}
    if not required_paths.issubset(relative_paths):
        _fail(
            "SOURCE_INVENTORY_INVALID", "fixed UAssets are absent from copy projection"
        )
    if project_seal.raw is None:
        raise AssertionError("captured source project descriptor is unavailable")
    project_raw = _disposable_project_descriptor(project_seal.raw)
    projection = _tree_projection(tree_entries)
    observed_content_size = sum(entry.size_bytes for entry in tree_entries)
    if (
        len(tree_entries) != PINNED_CONTENT_FILE_COUNT
        or observed_content_size != PINNED_CONTENT_SIZE_BYTES
        or projection != PINNED_CONTENT_METADATA_PROJECTION_SHA256
    ):
        _fail(
            "SOURCE_CONTENT_PROJECTION_MISMATCH",
            "source Content inventory differs from the pinned canonical projection",
        )
    request = _build_request(
        config=normalized,
        project_sha256=_sha256_bytes(project_raw),
        commandlet_sha256=commandlet_seal.sha256,
        copy_projection_sha256=projection,
        key_source_seals=key_source_seals,
        engine_plugin_seals=engine_plugin_seals,
        engine_native_binary_seals=engine_native_binary_seals,
        engine_modules_receipt_seals=engine_modules_receipt_seals,
    )
    request_raw = canonical_json(request)
    report = {
        "schema_version": PLAN_SCHEMA,
        "mode": "dry_run",
        "attempt_root": str(normalized.attempt_root),
        "will_write": False,
        "will_execute_unreal": False,
        "claims": [],
        "accepted": False,
        "acknowledgements": {key: False for key in ACKNOWLEDGEMENT_KEYS},
        "source": {
            "archive_receipt": {
                "path": str(archive_seal.path),
                "sha256": archive_seal.sha256,
                "size_bytes": archive_seal.size_bytes,
                "archive_payload_sha256_from_receipt": archive["actual_sha256"],
                "archive_payload_rehashed_by_this_plan": False,
            },
            "project_file": {
                "path": str(project_seal.path),
                "sha256": project_seal.sha256,
                "size_bytes": project_seal.size_bytes,
            },
            "target_uasset": {
                "path": str(target_seal.path),
                "sha256": target_seal.sha256,
                "size_bytes": target_seal.size_bytes,
            },
            "key_dependency_uassets": [
                {
                    "kind": kind,
                    "path": str(seal.path),
                    "sha256": seal.sha256,
                    "size_bytes": seal.size_bytes,
                }
                for seal, (_, _, kind) in zip(
                    key_source_seals, KEY_SOURCE_PINS.values(), strict=True
                )
            ],
            "full_copy_projection": {
                "file_count": PINNED_CONTENT_FILE_COUNT,
                "size_bytes": PINNED_CONTENT_SIZE_BYTES,
                "metadata_projection_sha256": projection,
                "source_roots": ["Content"],
                "generated_config_files": [
                    {
                        "project_relative_path": relative.as_posix(),
                        "sha256": _sha256_bytes(raw),
                        "size_bytes": len(raw),
                    }
                    for relative, raw in SANITIZED_CONFIG_FILES.items()
                ],
                "source_config_copied": False,
            },
            "source_asset_registry_available": False,
            "source_opened_by_unreal": False,
        },
        "toolchain": {
            "engine_version": PINNED_ENGINE_VERSION,
            "build_version_sha256": build_seal.sha256,
            "editor_sha256": editor_seal.sha256,
            "runner_sha256": runner_seal.sha256,
            "commandlet_sha256": commandlet_seal.sha256,
            "engine_plugin_descriptors": _engine_plugin_descriptor_records(
                engine_plugin_seals
            ),
            "engine_native_authority": _native_authority_request(
                engine_native_binary_seals,
                engine_modules_receipt_seals,
            ),
            "gpu": 0,
            "rendering": "NullRHI",
            "display": None,
            "network_ports": [],
        },
        "execution_contract": request["execution_contract"],
        "copy_strategy": {
            "reason": "no_trusted_source_asset_registry",
            "phase_1": "copy_full_content_and_generate_sanitized_config",
            "phase_2": "build_ue57_registry_and_validate_recursive_dependency_closure",
            "source_format_uassets_in_git": False,
            "source_config_copied": False,
            "source_network_settings_copied": False,
            "redistribution": False,
        },
        "gates": {
            "class_forward_load_validated": False,
            "default_object_validated": False,
            "engine_plugin_descriptors_validated": False,
            "engine_native_authority_validated": False,
            "key_anim_dependency_validated": False,
            "key_skeletal_mesh_dependency_validated": False,
            "key_skeleton_dependency_validated": False,
            "runtime_visual_acceptance": False,
            "character_provider_published": False,
        },
    }
    report_raw = canonical_json(report)
    return SmokePlan(
        config=normalized,
        report=report,
        report_raw=report_raw,
        request=request,
        request_raw=request_raw,
        runner_seal=runner_seal,
        commandlet_seal=commandlet_seal,
        editor_seal=editor_seal,
        engine_plugin_seals=engine_plugin_seals,
        engine_native_binary_seals=engine_native_binary_seals,
        engine_modules_receipt_seals=engine_modules_receipt_seals,
        fixed_source_seals=(
            project_seal,
            target_seal,
            archive_seal,
            build_seal,
            *engine_plugin_seals,
            *engine_native_binary_seals,
            *engine_modules_receipt_seals,
            *key_source_seals,
        ),
        tree_entries=tree_entries,
    )


def _write_all(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            _fail("WRITE_FAILED", "exclusive write made no progress")
        view = view[written:]


def _write_exclusive(path: Path, raw: bytes, *, mode: int = PRIVATE_FILE_MODE) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        os.fchmod(descriptor, mode)
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    except CitySampleCrowdSmokeError:
        raise
    except OSError as exc:
        raise CitySampleCrowdSmokeError(
            "WRITE_FAILED", "could not create append-only attempt file"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _mkdir_exclusive(path: Path) -> None:
    try:
        os.mkdir(path, PRIVATE_DIRECTORY_MODE)
        os.chmod(path, PRIVATE_DIRECTORY_MODE, follow_symlinks=False)
    except FileExistsError as exc:
        raise CitySampleCrowdSmokeError(
            "ATTEMPT_EXISTS", "append-only path already exists"
        ) from exc
    except OSError as exc:
        raise CitySampleCrowdSmokeError(
            "WRITE_FAILED", "could not create append-only attempt directory"
        ) from exc


def _sealed_json(path: Path, value: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    sealed = dict(value)
    sealed["content_digest"] = _content_digest(sealed)
    raw = canonical_json(sealed)
    _write_exclusive(path, raw)
    digest = _sha256_bytes(raw)
    _write_exclusive(
        path.with_name(path.name + ".sha256"), f"{digest}  {path.name}\n".encode()
    )
    return sealed, digest


def _assert_seal_unchanged(seal: FileSeal, *, label: str) -> None:
    current = _seal_file(seal.path, label=label)
    if current.identity != seal.identity or current.sha256 != seal.sha256:
        _fail("SOURCE_CHANGED", f"{label} changed after planning")


def _copy_entry(entry: TreeEntry, destination: Path) -> tuple[str, int]:
    try:
        before = os.lstat(entry.source)
    except OSError as exc:
        raise CitySampleCrowdSmokeError(
            "SOURCE_CHANGED", "source entry disappeared before copy"
        ) from exc
    if _identity(before) != entry.identity:
        _fail("SOURCE_CHANGED", "source entry metadata changed before copy")
    destination.parent.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
    source_descriptor = destination_descriptor = -1
    digest = hashlib.sha256()
    copied = 0
    try:
        source_descriptor = os.open(
            entry.source,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        if _identity(os.fstat(source_descriptor)) != entry.identity:
            _fail("SOURCE_CHANGED", "source entry changed while opening for copy")
        destination_descriptor = os.open(
            destination,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            PRIVATE_FILE_MODE,
        )
        while True:
            block = os.read(source_descriptor, COPY_BLOCK_BYTES)
            if not block:
                break
            digest.update(block)
            copied += len(block)
            _write_all(destination_descriptor, block)
        os.fsync(destination_descriptor)
        if _identity(os.fstat(source_descriptor)) != entry.identity:
            _fail("SOURCE_CHANGED", "source entry changed during copy")
    except CitySampleCrowdSmokeError:
        raise
    except OSError as exc:
        raise CitySampleCrowdSmokeError(
            "COPY_FAILED", "could not copy the sealed source projection"
        ) from exc
    finally:
        if source_descriptor >= 0:
            os.close(source_descriptor)
        if destination_descriptor >= 0:
            os.close(destination_descriptor)
    if copied != entry.size_bytes:
        _fail("COPY_FAILED", "copied source entry size differs")
    return digest.hexdigest(), copied


def _copy_project(plan: SmokePlan, project_root: Path) -> tuple[dict[str, Any], str]:
    records = []
    for entry in plan.tree_entries:
        destination = project_root.joinpath(*entry.relative.parts)
        digest, size = _copy_entry(entry, destination)
        records.append(
            {
                "project_relative_path": entry.relative.as_posix(),
                "sha256": digest,
                "size_bytes": size,
                "source_kind": "pinned_source_content_copy",
            }
        )
    for relative, raw in SANITIZED_CONFIG_FILES.items():
        destination = project_root.joinpath(*relative.parts)
        destination.parent.mkdir(
            mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True
        )
        _write_exclusive(destination, raw)
        records.append(
            {
                "project_relative_path": relative.as_posix(),
                "sha256": _sha256_bytes(raw),
                "size_bytes": len(raw),
                "source_kind": "project_generated_sanitized_config",
            }
        )
    records.sort(key=lambda record: record["project_relative_path"])
    after = _source_inventory(plan.config.source_root)
    if _tree_projection(after) != plan.request["copy_projection_sha256"]:
        _fail("SOURCE_CHANGED", "source tree projection changed during copy")
    manifest = {
        "schema_version": COPY_MANIFEST_SCHEMA,
        "accepted": False,
        "copy_strategy": "full_content_and_sanitized_config_then_registry_audit",
        "source_root": str(plan.config.source_root),
        "destination_project": str(project_root),
        "source_metadata_projection_sha256": plan.request["copy_projection_sha256"],
        "source_content_file_count": PINNED_CONTENT_FILE_COUNT,
        "source_content_size_bytes": PINNED_CONTENT_SIZE_BYTES,
        "file_count": len(records),
        "size_bytes": sum(record["size_bytes"] for record in records),
        "files": records,
        "source_format_uassets_in_git": False,
        "source_config_copied": False,
        "source_network_settings_copied": False,
        "redistribution_authorized": False,
    }
    return _sealed_json(plan.config.attempt_root / COPY_MANIFEST_NAME, manifest)


def _bind_execution_request(
    plan: SmokePlan,
    manifest_sha256: str,
    acknowledgements: Mapping[str, bool],
) -> tuple[dict[str, Any], bytes]:
    if SHA256_RE.fullmatch(manifest_sha256) is None:
        raise AssertionError("copy manifest SHA-256 is malformed")
    request = dict(plan.request)
    if request.get("copy_manifest_sha256") is not None:
        raise AssertionError("dry-run request template was already bound")
    if set(acknowledgements) != set(ACKNOWLEDGEMENT_KEYS) or any(
        acknowledgements[key] is not True for key in ACKNOWLEDGEMENT_KEYS
    ):
        raise AssertionError("execution acknowledgements are incomplete")
    request["copy_manifest_sha256"] = manifest_sha256
    request["authorization"] = {
        "epic_ue_only_content_entitlement_acknowledged": acknowledgements[
            "epic_ue_only_content_entitlement"
        ],
        "large_full_content_copy_acknowledged": acknowledgements[
            "large_full_content_copy"
        ],
        "metahuman_visual_demo_only_not_ai_training_testing_acknowledged": (
            acknowledgements["metahuman_visual_demo_only_not_ai_training_testing"]
        ),
        "no_redistribution_acknowledged": acknowledgements["no_redistribution"],
        "private_noncommercial_research_acknowledged": acknowledgements[
            "private_noncommercial_research"
        ],
        "source_uassets_outside_git_acknowledged": acknowledgements[
            "source_uassets_outside_git"
        ],
    }
    request["content_digest"] = ""
    request["content_digest"] = _content_digest(request)
    return request, canonical_json(request)


def _prepare_isolated_runtime_directories(attempt_root: Path) -> None:
    for name in ISOLATED_RUNTIME_DIRECTORIES:
        _mkdir_exclusive(attempt_root / name)


def _safe_environment(plan: SmokePlan, request_raw: bytes) -> dict[str, str]:
    attempt = plan.config.attempt_root
    environment = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "CUDA_VISIBLE_DEVICES": "0",
        "HOME": str(attempt / "runtime-home"),
        "TMPDIR": str(attempt / "runtime-tmp"),
        "XDG_CACHE_HOME": str(attempt / "runtime-cache"),
        "XDG_CONFIG_HOME": str(attempt / "runtime-config"),
        "XDG_DATA_HOME": str(attempt / "runtime-data"),
        "XDG_RUNTIME_DIR": str(attempt / "runtime-state"),
        REQUEST_ENV: str(plan.config.attempt_root / REQUEST_NAME),
        REQUEST_SHA_ENV: _sha256_bytes(request_raw),
        RESULT_ENV: str(plan.config.attempt_root / RESULT_NAME),
        RESULT_SHA_ENV: str(plan.config.attempt_root / (RESULT_NAME + ".sha256")),
    }
    for key in ("LANG", "LC_ALL", "LOGNAME", "USER"):
        value = os.environ.get(key)
        if value is not None:
            if "\0" in value:
                _fail("ENVIRONMENT_INVALID", f"{key} contains NUL")
            environment[key] = value
    # Deliberately no DISPLAY, XAUTHORITY, API token, proxy, or caller-selected
    # environment reaches this isolated NullRHI smoke.
    return environment


def _fixed_command(plan: SmokePlan) -> list[str]:
    attempt = plan.config.attempt_root
    return [
        str(plan.editor_seal.path),
        str(attempt / "project" / DISPOSABLE_PROJECT_NAME),
        "-run=pythonscript",
        f"-script={attempt / COMMANDLET_NAME}",
        *FIXED_COMMAND_ARGUMENTS_AFTER_SCRIPT,
    ]


def _validated_execution_contract(
    plan: SmokePlan, request_raw: bytes
) -> ExecutionContract:
    command = tuple(_fixed_command(plan))
    environment = _safe_environment(plan, request_raw)
    if command[4:] != FIXED_COMMAND_ARGUMENTS_AFTER_SCRIPT:
        _fail("EXECUTION_CONTRACT_INVALID", "fixed command arguments differ")
    if any(flag not in command for flag in NETWORK_TRANSPORT_DISABLE_FLAGS):
        _fail("EXECUTION_CONTRACT_INVALID", "network disable flags are incomplete")
    if any(argument in FORBIDDEN_COMMAND_ARGUMENTS for argument in command):
        _fail("EXECUTION_CONTRACT_INVALID", "a network enable flag is present")
    required_environment_keys = {
        "CUDA_VISIBLE_DEVICES",
        "HOME",
        "PATH",
        REQUEST_ENV,
        REQUEST_SHA_ENV,
        RESULT_ENV,
        RESULT_SHA_ENV,
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
    }
    allowed_environment_keys = required_environment_keys | {
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "USER",
    }
    if not required_environment_keys.issubset(environment) or not set(
        environment
    ).issubset(allowed_environment_keys):
        _fail("EXECUTION_CONTRACT_INVALID", "environment key inventory differs")
    if environment.get("CUDA_VISIBLE_DEVICES") != "0":
        _fail("EXECUTION_CONTRACT_INVALID", "GPU visibility differs")
    if any(
        key in environment
        for key in (
            "DISPLAY",
            "XAUTHORITY",
            "DBUS_SESSION_BUS_ADDRESS",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
    ):
        _fail("EXECUTION_CONTRACT_INVALID", "display or network environment leaked")
    request = _strict_json(request_raw, label="execution request")
    expected_request_contract = {
        "cuda_visible_devices": "0",
        "display_present": False,
        "fixed_arguments_after_script": list(FIXED_COMMAND_ARGUMENTS_AFTER_SCRIPT),
        "network_transport_disable_flags": list(NETWORK_TRANSPORT_DISABLE_FLAGS),
        "network_ports": [],
        "xauthority_present": False,
    }
    if request.get("execution_contract") != expected_request_contract:
        _fail("EXECUTION_CONTRACT_INVALID", "request execution contract differs")
    evidence = {
        "argv": list(command),
        "argv_sha256": _sha256_bytes(canonical_json(list(command))),
        "environment": dict(sorted(environment.items())),
        "environment_sha256": _sha256_bytes(
            canonical_json(dict(sorted(environment.items())))
        ),
        "network_transport_disable_flags": list(NETWORK_TRANSPORT_DISABLE_FLAGS),
        "network_ports": [],
        "gpu": 0,
        "display_present": False,
        "xauthority_present": False,
    }
    return ExecutionContract(
        command=command,
        environment=environment,
        evidence=evidence,
    )


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=PROCESS_GROUP_GRACE_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            process.wait(timeout=PROCESS_GROUP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass


def _run_unreal(
    plan: SmokePlan,
    request_raw: bytes,
    execution: ExecutionContract | None = None,
) -> int:
    if execution is None:
        execution = _validated_execution_contract(plan, request_raw)
    log_path = plan.config.attempt_root / LOG_NAME
    descriptor = os.open(
        log_path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        PRIVATE_FILE_MODE,
    )
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            list(execution.command),
            cwd=plan.config.attempt_root / "project",
            env=dict(execution.environment),
            stdin=subprocess.DEVNULL,
            stdout=descriptor,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
        try:
            return process.wait(timeout=COMMAND_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(process)
            raise CitySampleCrowdSmokeError(
                "UNREAL_TIMEOUT", "UE 5.7 forward-load commandlet timed out"
            ) from exc
    except CitySampleCrowdSmokeError:
        raise
    except OSError as exc:
        if process is not None:
            _terminate_process_group(process)
        raise CitySampleCrowdSmokeError(
            "UNREAL_LAUNCH_FAILED", "could not launch the pinned UE editor"
        ) from exc
    finally:
        os.close(descriptor)


def _read_sealed_result(plan: SmokePlan) -> tuple[dict[str, Any], str]:
    result_path = plan.config.attempt_root / RESULT_NAME
    sidecar_path = result_path.with_name(result_path.name + ".sha256")
    seal = _seal_file(result_path, label="commandlet result", capture=True)
    sidecar = _seal_file(sidecar_path, label="commandlet result sidecar", capture=True)
    if seal.raw is None or sidecar.raw is None:
        raise AssertionError("captured commandlet receipt bytes are unavailable")
    expected_sidecar = f"{seal.sha256}  {RESULT_NAME}\n".encode()
    if sidecar.raw != expected_sidecar:
        _fail("RESULT_INVALID", "commandlet result SHA-256 sidecar differs")
    result = _strict_json(seal.raw, label="commandlet result")
    if seal.raw != canonical_json(result):
        _fail("RESULT_INVALID", "commandlet result is not canonical JSON")
    if result.get("content_digest") != _content_digest(result):
        _fail("RESULT_INVALID", "commandlet result content digest differs")
    required_result_keys = {
        "accepted",
        "blueprint_object_path",
        "character_provider_published",
        "commandlet_sha256",
        "content_digest",
        "copy_projection_sha256",
        "default_object_path",
        "dependency_asset_count",
        "dependency_asset_records",
        "dependency_class_counts",
        "dependency_closure_sha256",
        "dependency_packages",
        "engine_native_module_evidence",
        "engine_plugin_descriptor_evidence",
        "engine_version",
        "gates",
        "generated_class_path",
        "key_dependency_evidence",
        "loaded_class_path",
        "runtime_visual_acceptance",
        "schema_version",
        "skeletal_component_count",
        "status",
        "target_asset_data",
        "target_class_path",
        "target_uasset_sha256",
    }
    if set(result) != required_result_keys:
        _fail("RESULT_INVALID", "commandlet result key inventory differs")
    expected = {
        "schema_version": RESULT_SCHEMA,
        "status": "forward_load_validated_private_research_only",
        "accepted": False,
        "engine_version": PINNED_ENGINE_VERSION,
        "target_class_path": TARGET_CLASS,
        "target_uasset_sha256": PINNED_TARGET_UASSET_SHA256,
        "copy_projection_sha256": plan.request["copy_projection_sha256"],
        "commandlet_sha256": plan.commandlet_seal.sha256,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            _fail("RESULT_INVALID", f"commandlet result field {key!r} differs")
    expected_plugin_descriptor_evidence = _revalidate_engine_plugin_descriptors(plan)
    if (
        result.get("engine_plugin_descriptor_evidence")
        != expected_plugin_descriptor_evidence
    ):
        _fail("RESULT_INVALID", "engine plugin descriptor evidence differs")
    expected_native_module_evidence = _revalidate_engine_native_module_authority(plan)
    if result.get("engine_native_module_evidence") != expected_native_module_evidence:
        _fail("RESULT_INVALID", "engine native module evidence differs")
    expected_target_asset_data = {
        "asset_class": "Blueprint",
        "object_path": TARGET_OBJECT,
        "package_name": TARGET_PACKAGE,
    }
    if result.get("target_asset_data") != expected_target_asset_data:
        _fail("RESULT_INVALID", "target AssetData evidence differs")
    exact_paths = {
        "blueprint_object_path": TARGET_OBJECT,
        "generated_class_path": TARGET_CLASS,
        "loaded_class_path": TARGET_CLASS,
        "default_object_path": TARGET_CDO_PATH,
    }
    for key, value in exact_paths.items():
        if result.get(key) != value:
            _fail("RESULT_INVALID", f"exact class evidence {key!r} differs")
    component_count = result.get("skeletal_component_count")
    if type(component_count) is not int or not 1 <= component_count <= 64:
        _fail("RESULT_INVALID", "skeletal component count differs")

    packages = result.get("dependency_packages")
    if (
        type(packages) is not list
        or not packages
        or len(packages) > 50_000
        or any(
            type(package) is not str or not package.startswith("/")
            for package in packages
        )
        or packages != sorted(set(packages))
    ):
        _fail("RESULT_INVALID", "dependency package closure differs")
    records = result.get("dependency_asset_records")
    if type(records) is not list or not records or len(records) > 100_000:
        _fail("RESULT_INVALID", "dependency asset records differ")
    expected_record_keys = {"asset_class", "object_path", "package_name"}
    normalized_records = []
    for record in records:
        if type(record) is not dict or set(record) != expected_record_keys:
            _fail("RESULT_INVALID", "dependency asset record shape differs")
        if any(
            type(record[key]) is not str or not record[key]
            for key in expected_record_keys
        ):
            _fail("RESULT_INVALID", "dependency asset record value differs")
        if record["package_name"] not in packages or not record[
            "object_path"
        ].startswith(record["package_name"] + "."):
            _fail("RESULT_INVALID", "dependency asset record binding differs")
        normalized_records.append(record)
    expected_record_order = sorted(
        normalized_records,
        key=lambda item: (
            item["package_name"],
            item["object_path"],
            item["asset_class"],
        ),
    )
    if records != expected_record_order or len(
        {
            (item["package_name"], item["object_path"], item["asset_class"])
            for item in records
        }
    ) != len(records):
        _fail("RESULT_INVALID", "dependency asset record order or uniqueness differs")
    if result.get("dependency_asset_count") != len(records):
        _fail("RESULT_INVALID", "dependency asset count differs")
    computed_class_counts: dict[str, int] = {}
    for record in records:
        asset_class = record["asset_class"]
        computed_class_counts[asset_class] = (
            computed_class_counts.get(asset_class, 0) + 1
        )
    computed_class_counts = dict(sorted(computed_class_counts.items()))
    if result.get("dependency_class_counts") != computed_class_counts:
        _fail("RESULT_INVALID", "dependency class counts differ")
    computed_closure_digest = _sha256_bytes(
        canonical_json({"asset_records": records, "packages": packages})
    )
    if result.get("dependency_closure_sha256") != computed_closure_digest:
        _fail("RESULT_INVALID", "dependency closure digest differs")
    expected_key_evidence = [
        {
            "asset_class": binding["asset_class"],
            "kind": binding["kind"],
            "object_path": binding["object_path"],
            "package_name": binding["package_name"],
            "reachable": True,
        }
        for binding in plan.request["key_dependencies"]
    ]
    if result.get("key_dependency_evidence") != expected_key_evidence:
        _fail("RESULT_INVALID", "exact key dependency evidence differs")
    for evidence in expected_key_evidence:
        expected_record = {
            "asset_class": evidence["asset_class"],
            "object_path": evidence["object_path"],
            "package_name": evidence["package_name"],
        }
        if (
            packages.count(evidence["package_name"]) != 1
            or records.count(expected_record) != 1
        ):
            _fail("RESULT_INVALID", "key dependency closure binding differs")
    gates = result.get("gates")
    required_gates = {
        "asset_registry_dependency_closure_validated",
        "blueprint_generated_class_bound",
        "class_forward_load_validated",
        "default_object_is_character",
        "default_object_path_bound",
        "engine_plugin_descriptors_validated",
        "engine_native_authority_validated",
        "key_anim_dependency_validated",
        "key_skeletal_mesh_dependency_validated",
        "key_skeleton_dependency_validated",
        "source_uassets_remained_outside_git",
        "target_asset_data_validated",
    }
    if type(gates) is not dict or set(gates) != required_gates:
        _fail("RESULT_INVALID", "commandlet result gate inventory differs")
    if any(gates[key] is not True for key in required_gates):
        _fail("RESULT_REJECTED", "one or more forward-load gates failed")
    if result.get("runtime_visual_acceptance") is not False:
        _fail("RESULT_FALSE_PROMOTION", "commandlet promoted runtime visual acceptance")
    if result.get("character_provider_published") is not False:
        _fail("RESULT_FALSE_PROMOTION", "commandlet promoted a character provider")
    return result, seal.sha256


def _host_receipt(
    plan: SmokePlan,
    *,
    status: str,
    quarantined: bool,
    command_return_code: int | None,
    result_sha256: str | None,
    failure_code: str | None,
    request_raw: bytes | None,
    acknowledgements: Mapping[str, bool],
    execution_evidence: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if not quarantined and execution_evidence is None:
        raise AssertionError("successful receipt requires execution evidence")
    if set(acknowledgements) != set(ACKNOWLEDGEMENT_KEYS) or any(
        acknowledgements[key] is not True for key in ACKNOWLEDGEMENT_KEYS
    ):
        raise AssertionError("receipt acknowledgement inventory differs")
    if execution_evidence is not None:
        if request_raw is None:
            raise AssertionError("execution evidence requires a request")
        expected_execution = _validated_execution_contract(plan, request_raw)
        if execution_evidence != expected_execution.evidence:
            raise AssertionError("receipt execution evidence differs")
        request = _strict_json(request_raw, label="receipt execution request")
        expected_authorization = {
            "epic_ue_only_content_entitlement_acknowledged": acknowledgements[
                "epic_ue_only_content_entitlement"
            ],
            "large_full_content_copy_acknowledged": acknowledgements[
                "large_full_content_copy"
            ],
            "metahuman_visual_demo_only_not_ai_training_testing_acknowledged": (
                acknowledgements["metahuman_visual_demo_only_not_ai_training_testing"]
            ),
            "no_redistribution_acknowledged": acknowledgements["no_redistribution"],
            "private_noncommercial_research_acknowledged": acknowledgements[
                "private_noncommercial_research"
            ],
            "source_uassets_outside_git_acknowledged": acknowledgements[
                "source_uassets_outside_git"
            ],
        }
        if request.get("authorization") != expected_authorization:
            raise AssertionError("receipt request authorization differs")
    native_module_evidence = (
        None if quarantined else _revalidate_engine_native_module_authority(plan)
    )
    plugin_descriptor_evidence = (
        None if quarantined else _revalidate_engine_plugin_descriptors(plan)
    )
    return {
        "schema_version": HOST_RECEIPT_SCHEMA,
        "status": status,
        "accepted": False,
        "quarantined": quarantined,
        "attempt_root": str(plan.config.attempt_root),
        "plan_sha256": _sha256_bytes(plan.report_raw),
        "request_sha256": _sha256_bytes(request_raw)
        if request_raw is not None
        else None,
        "commandlet_sha256": plan.commandlet_seal.sha256,
        "runner_sha256": plan.runner_seal.sha256,
        "editor_sha256": plan.editor_seal.sha256,
        "source_project_sha256": PINNED_SOURCE_PROJECT_SHA256,
        "target_uasset_sha256": PINNED_TARGET_UASSET_SHA256,
        "archive_receipt_sha256": PINNED_ARCHIVE_RECEIPT_SHA256,
        "copy_projection_sha256": plan.request["copy_projection_sha256"],
        "command_return_code": command_return_code,
        "commandlet_result_sha256": result_sha256,
        "failure_code": failure_code,
        "acknowledgements": {
            key: acknowledgements[key] for key in ACKNOWLEDGEMENT_KEYS
        },
        "execution_evidence": execution_evidence,
        "engine_native_module_evidence": native_module_evidence,
        "engine_plugin_descriptor_evidence": plugin_descriptor_evidence,
        "scope": "private_noncommercial_research_only",
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
        "redistribution_authorized": False,
        "source_format_uassets_in_git": False,
        "runtime_visual_acceptance": False,
        "character_provider_published": False,
        "claims": (
            ["ue57_forward_load_and_dependency_smoke_validated"]
            if not quarantined
            else []
        ),
    }


def _write_quarantine(plan: SmokePlan, error: CitySampleCrowdSmokeError) -> None:
    marker = plan.config.attempt_root / QUARANTINE_NAME
    if marker.exists():
        return
    value = {
        "schema_version": QUARANTINE_SCHEMA,
        "status": "failed_quarantined_no_reuse",
        "accepted": False,
        "failure_code": error.code,
        "message": error.message,
        "attempt_root": str(plan.config.attempt_root),
        "reuse_allowed": False,
        "redistribution_authorized": False,
        "character_provider_published": False,
    }
    _sealed_json(marker, value)


def apply_smoke(
    plan: SmokePlan,
    *,
    acknowledge_private_noncommercial_research: bool,
    acknowledge_epic_ue_only_content_entitlement: bool,
    acknowledge_no_redistribution: bool,
    acknowledge_source_uassets_outside_git: bool,
    acknowledge_large_full_content_copy: bool,
    acknowledge_metahuman_visual_demo_only_not_ai_training_testing: bool,
) -> Mapping[str, Any]:
    acknowledgements = {
        "private_noncommercial_research": acknowledge_private_noncommercial_research,
        "epic_ue_only_content_entitlement": acknowledge_epic_ue_only_content_entitlement,
        "no_redistribution": acknowledge_no_redistribution,
        "source_uassets_outside_git": acknowledge_source_uassets_outside_git,
        "large_full_content_copy": acknowledge_large_full_content_copy,
        "metahuman_visual_demo_only_not_ai_training_testing": (
            acknowledge_metahuman_visual_demo_only_not_ai_training_testing
        ),
    }
    if any(value is not True for value in acknowledgements.values()):
        _fail(
            "ACKNOWLEDGEMENT_REQUIRED",
            "all six private-content apply gates are required",
        )

    attempt = plan.config.attempt_root
    _mkdir_exclusive(attempt)
    command_return_code: int | None = None
    result_sha256: str | None = None
    execution_request_raw: bytes | None = None
    execution_evidence: Mapping[str, Any] | None = None
    try:
        _mkdir_exclusive(attempt / "project")
        _write_exclusive(attempt / PLAN_NAME, plan.report_raw)
        _write_exclusive(
            attempt / (PLAN_NAME + ".sha256"),
            f"{_sha256_bytes(plan.report_raw)}  {PLAN_NAME}\n".encode(),
        )
        for index, seal in enumerate(plan.fixed_source_seals):
            _assert_seal_unchanged(seal, label=f"fixed source {index}")
        _assert_seal_unchanged(plan.runner_seal, label="source-controlled smoke runner")
        _assert_seal_unchanged(plan.commandlet_seal, label="smoke commandlet")
        _assert_seal_unchanged(plan.editor_seal, label="UE editor")

        project_seal = plan.fixed_source_seals[0]
        if project_seal.raw is None:
            raise AssertionError("captured source project descriptor is unavailable")
        project_raw = _disposable_project_descriptor(project_seal.raw)
        _write_exclusive(
            attempt / "project" / DISPOSABLE_PROJECT_NAME,
            project_raw,
        )
        _, manifest_sha256 = _copy_project(plan, attempt / "project")
        if plan.commandlet_seal.raw is None:
            raise AssertionError("captured commandlet bytes are unavailable")
        _write_exclusive(attempt / COMMANDLET_NAME, plan.commandlet_seal.raw)
        copied_commandlet = _seal_file(
            attempt / COMMANDLET_NAME,
            label="copied smoke commandlet",
            expected_sha256=plan.commandlet_seal.sha256,
        )
        if copied_commandlet.sha256 != plan.commandlet_seal.sha256:
            raise AssertionError("copied commandlet pin differs")
        _, execution_request_raw = _bind_execution_request(
            plan, manifest_sha256, acknowledgements
        )
        _write_exclusive(attempt / REQUEST_NAME, execution_request_raw)
        _write_exclusive(
            attempt / (REQUEST_NAME + ".sha256"),
            f"{_sha256_bytes(execution_request_raw)}  {REQUEST_NAME}\n".encode(),
        )
        if (
            manifest_sha256
            != _seal_file(
                attempt / COPY_MANIFEST_NAME,
                label="copy manifest",
            ).sha256
        ):
            raise AssertionError("copy manifest seal differs")

        _prepare_isolated_runtime_directories(attempt)
        execution = _validated_execution_contract(plan, execution_request_raw)
        execution_evidence = execution.evidence
        command_return_code = _run_unreal(plan, execution_request_raw, execution)
        if command_return_code != 0:
            _fail("UNREAL_REJECTED", "UE 5.7 commandlet returned nonzero")
        _, result_sha256 = _read_sealed_result(plan)
        receipt = _host_receipt(
            plan,
            status="forward_load_validated_private_research_only",
            quarantined=False,
            command_return_code=command_return_code,
            result_sha256=result_sha256,
            failure_code=None,
            request_raw=execution_request_raw,
            acknowledgements=acknowledgements,
            execution_evidence=execution_evidence,
        )
        sealed, _ = _sealed_json(attempt / HOST_RECEIPT_NAME, receipt)
        return sealed
    except CitySampleCrowdSmokeError as error:
        receipt_path = attempt / HOST_RECEIPT_NAME
        if not receipt_path.exists():
            _sealed_json(
                receipt_path,
                _host_receipt(
                    plan,
                    status="failed_quarantined_no_reuse",
                    quarantined=True,
                    command_return_code=command_return_code,
                    result_sha256=result_sha256,
                    failure_code=error.code,
                    request_raw=execution_request_raw,
                    acknowledgements=acknowledgements,
                    execution_evidence=execution_evidence,
                ),
            )
        _write_quarantine(plan, error)
        raise
    except Exception as unexpected:
        error = CitySampleCrowdSmokeError(
            "APPLY_FAILED", "unexpected host failure after attempt creation"
        )
        receipt_path = attempt / HOST_RECEIPT_NAME
        if not receipt_path.exists():
            _sealed_json(
                receipt_path,
                _host_receipt(
                    plan,
                    status="failed_quarantined_no_reuse",
                    quarantined=True,
                    command_return_code=command_return_code,
                    result_sha256=result_sha256,
                    failure_code=error.code,
                    request_raw=execution_request_raw,
                    acknowledgements=acknowledgements,
                    execution_evidence=execution_evidence,
                ),
            )
        _write_quarantine(plan, error)
        raise error from unexpected


def _fixed_config(attempt_name: str) -> SmokeConfig:
    return SmokeConfig(
        engine_root=DEFAULT_ENGINE_ROOT,
        source_root=DEFAULT_SOURCE_ROOT,
        archive_receipt=DEFAULT_ARCHIVE_RECEIPT,
        run_root=DEFAULT_RUN_ROOT,
        attempt_name=attempt_name,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--attempt-name",
        default="citysample-crowd-human-smoke-r1",
        help="fresh append-only attempt name with the fixed CitySample prefix",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--ack-private-noncommercial-research",
        action="store_true",
    )
    parser.add_argument(
        "--ack-epic-ue-only-content-entitlement",
        action="store_true",
    )
    parser.add_argument("--ack-no-redistribution", action="store_true")
    parser.add_argument("--ack-source-uassets-outside-git", action="store_true")
    parser.add_argument("--ack-large-full-content-copy", action="store_true")
    parser.add_argument(
        "--ack-metahuman-visual-demo-only-not-ai-training-testing",
        action="store_true",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        plan = plan_smoke(_fixed_config(arguments.attempt_name))
        if not arguments.apply:
            sys.stdout.buffer.write(plan.report_raw)
            return 0
        receipt = apply_smoke(
            plan,
            acknowledge_private_noncommercial_research=(
                arguments.ack_private_noncommercial_research
            ),
            acknowledge_epic_ue_only_content_entitlement=(
                arguments.ack_epic_ue_only_content_entitlement
            ),
            acknowledge_no_redistribution=arguments.ack_no_redistribution,
            acknowledge_source_uassets_outside_git=(
                arguments.ack_source_uassets_outside_git
            ),
            acknowledge_large_full_content_copy=(arguments.ack_large_full_content_copy),
            acknowledge_metahuman_visual_demo_only_not_ai_training_testing=(
                arguments.ack_metahuman_visual_demo_only_not_ai_training_testing
            ),
        )
        sys.stdout.buffer.write(canonical_json(receipt))
        return 0
    except CitySampleCrowdSmokeError as error:
        sys.stderr.write(str(error) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
