"""Pinned UE 5.7 CitySampleCrowd forward-load audit commandlet.

The host runner copies this file and the complete source ``Content`` projection
into a private disposable project, alongside a minimal generated Config.  The
source Config and its unrelated runtime/network settings are not copied.  This
commandlet accepts only the byte-pinned request supplied by the host, builds the
UE Asset Registry in that copy, and validates one fixed Blueprint generated
class.  It creates no assets, saves no packages, and cannot publish a character
provider.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat

import unreal

REQUEST_SCHEMA = "vista.citysample-crowd-human-forward-load-request/v1"
RESULT_SCHEMA = "vista.citysample-crowd-human-forward-load-result/v1"
COPY_MANIFEST_SCHEMA = "vista.citysample-crowd-human-full-content-copy-manifest/v1"
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
TARGET_ROOT = "/Game/CitySampleCrowd"
TARGET_PACKAGE = "/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter"
TARGET_OBJECT = TARGET_PACKAGE + ".BP_CrowdCharacter"
TARGET_CLASS = TARGET_OBJECT + "_C"
TARGET_CDO_PATH = TARGET_PACKAGE + ".Default__BP_CrowdCharacter_C"
TARGET_UASSET_SHA256 = (
    "4deeaef11653c887ab85242cb444a8b3752b611a2a3c7c341d570f0646f82450"
)
TARGET_UASSET_SIZE = 1_538_864
PROJECT_NAME = "VistaCitySampleCrowdSmoke.uproject"
COMMANDLET_NAME = "citysample_crowd_human_smoke_commandlet.py"
REQUEST_NAME = "citysample-crowd-human-request.json"
RESULT_NAME = "citysample-crowd-human-result.json"
COPY_MANIFEST_NAME = "citysample-crowd-human-copy-manifest.json"
REQUEST_ENV = "VISTA_CITYSAMPLE_CROWD_HUMAN_REQUEST"
REQUEST_SHA_ENV = "VISTA_CITYSAMPLE_CROWD_HUMAN_REQUEST_SHA256"
RESULT_ENV = "VISTA_CITYSAMPLE_CROWD_HUMAN_RESULT"
RESULT_SHA_ENV = "VISTA_CITYSAMPLE_CROWD_HUMAN_RESULT_SHA256"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_DEPENDENCY_PACKAGES = 50_000
PINNED_CONTENT_FILE_COUNT = 2_967
PINNED_CONTENT_SIZE_BYTES = 10_218_144_848
PINNED_CONTENT_METADATA_PROJECTION_SHA256 = (
    "a97b341c1fb610d5c40c3396fe0b305cafb7c17319678ff057823a4ac702b0c2"
)
SANITIZED_CONFIG_PINS = {
    "Config/DefaultEngine.ini": (
        "248f5102b5d2e79ed15d09df853049e7b4bb071f9ac834f4ff5b7d585c0c212e",
        165,
    ),
    "Config/DefaultGame.ini": (
        "33423326f1f164ae90d27ad3cd2b6ca5e721e06be626a4b58b613c2a392ce1a7",
        86,
    ),
}
ENGINE_PLUGIN_PINS = [
    {
        "name": "HairStrands",
        "relative_path": "Engine/Plugins/Runtime/HairStrands/HairStrands.uplugin",
        "required_native_modules": ["HairStrandsCore"],
        "sha256": "f95269163143061d2b13c00f574d5318cbf38d43d385c38b8582f9421a6a294d",
        "size_bytes": 1_429,
    },
    {
        "name": "MassGameplay",
        "relative_path": "Engine/Plugins/Runtime/MassGameplay/MassGameplay.uplugin",
        "required_native_modules": ["MassActors"],
        "sha256": "b516d319d521944f2b6e1fe82d10df256be9331e874cc79d3b9504bb02f9fcf6",
        "size_bytes": 1_805,
    },
    {
        "name": "PythonScriptPlugin",
        "relative_path": (
            "Engine/Plugins/Experimental/PythonScriptPlugin/PythonScriptPlugin.uplugin"
        ),
        "required_native_modules": [
            "PythonScriptPlugin",
            "PythonScriptPluginPreload",
        ],
        "sha256": "7a355543790998ba9bf947abc0ac52bdcc942b173d6c863d687d84e95c894699",
        "size_bytes": 1_006,
    },
    {
        "name": "RigLogic",
        "relative_path": "Engine/Plugins/Animation/RigLogic/RigLogic.uplugin",
        "required_native_modules": [
            "RigLogicLib",
            "RigLogicModule",
            "RigLogicDeveloper",
        ],
        "sha256": "c6ce682b00793943614fea31fdae5c201a6a4595f96bf4a901d3657f79e5e340",
        "size_bytes": 1_044,
    },
]
ENGINE_NATIVE_BINARY_PINS = [
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
]
ENGINE_MODULES_RECEIPT_PINS = [
    {
        "module_bindings": {
            "HairStrandsCore": "libUnrealEditor-HairStrandsCore.so",
        },
        "modules_receipt_build_id": "47537391",
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
        "modules_receipt_build_id": "47537391",
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
        "modules_receipt_build_id": "47537391",
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
        "modules_receipt_build_id": "47537391",
        "modules_receipt_relative_path": (
            "Engine/Plugins/Animation/RigLogic/Binaries/Linux/UnrealEditor.modules"
        ),
        "modules_receipt_sha256": (
            "d92089953171e325bb03cf40be10138ee1d77d4143d0e529eb62fc9233b2ab62"
        ),
        "modules_receipt_size_bytes": 273,
        "plugin_name": "RigLogic",
    },
]
KEY_DEPENDENCY_BINDINGS = [
    {
        "asset_class": "AnimBlueprint",
        "kind": "anim_blueprint",
        "object_path": "/Game/CitySampleCrowd/Blueprints/NPC1_AnimBP.NPC1_AnimBP",
        "package_name": "/Game/CitySampleCrowd/Blueprints/NPC1_AnimBP",
        "project_relative_path": "Content/CitySampleCrowd/Blueprints/NPC1_AnimBP.uasset",
        "sha256": "a106aa2c1ca33b05ab345c5ff5710d7f62f147e2503e45deae5a77d8754ded99",
        "size_bytes": 44_040,
    },
    {
        "asset_class": "SkeletalMesh",
        "kind": "skeletal_mesh",
        "object_path": (
            "/Game/CitySampleCrowd/Character/Female/NormalWeight/Meshes/"
            "f_tal_nrw_body.f_tal_nrw_body"
        ),
        "package_name": (
            "/Game/CitySampleCrowd/Character/Female/NormalWeight/Meshes/f_tal_nrw_body"
        ),
        "project_relative_path": (
            "Content/CitySampleCrowd/Character/Female/NormalWeight/Meshes/"
            "f_tal_nrw_body.uasset"
        ),
        "sha256": "893c97319068efb07c2caf66351598ce69dffd83451daf132ca8a2c4db45caf7",
        "size_bytes": 4_289_289,
    },
    {
        "asset_class": "Skeleton",
        "kind": "skeleton",
        "object_path": (
            "/Game/CitySampleCrowd/Character/Shared/Rig/"
            "metahuman_base_skel.metahuman_base_skel"
        ),
        "package_name": (
            "/Game/CitySampleCrowd/Character/Shared/Rig/metahuman_base_skel"
        ),
        "project_relative_path": (
            "Content/CitySampleCrowd/Character/Shared/Rig/metahuman_base_skel.uasset"
        ),
        "sha256": "03b5e510a1a0eb47a7807254d2f54857543f41f448442af182a31fd863a1184e",
        "size_bytes": 375_871,
    },
]
FIXED_COMMAND_ARGUMENTS_AFTER_SCRIPT = [
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
]
NETWORK_TRANSPORT_DISABLE_FLAGS = [
    "-NoMessaging",
    "-NoUdpMessaging",
    "-NoTcpMessaging",
    "-NoWebSockets",
    "-NoHttp",
]


class SmokeFailure(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


def require(condition, code, message):
    if not condition:
        raise SmokeFailure(code, message)


def canonical_json(value):
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
    except (TypeError, ValueError) as exc:
        raise SmokeFailure("JSON_INVALID", "value is not canonical JSON") from exc


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    descriptor = -1
    digest = hashlib.sha256()
    try:
        before = os.lstat(path)
        require(
            stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
            "FILE_PIN_MISMATCH",
            "sealed file must be a single-link regular file",
        )
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        require(
            file_identity(opened) == file_identity(before),
            "FILE_PIN_MISMATCH",
            "sealed file changed while opening",
        )
        while True:
            block = os.read(descriptor, 4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(descriptor)
        path_after = os.lstat(path)
        require(
            file_identity(opened) == file_identity(after) == file_identity(path_after),
            "FILE_PIN_MISMATCH",
            "sealed file changed while hashing",
        )
    except SmokeFailure:
        raise
    except OSError as exc:
        raise SmokeFailure("FILE_PIN_MISMATCH", "could not hash sealed file") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return digest.hexdigest()


def file_identity(metadata):
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IMODE(metadata.st_mode),
    )


def content_digest(value):
    body = dict(value)
    body.pop("content_digest", None)
    return sha256_bytes(canonical_json(body))


def reject_json_constant(value):
    raise SmokeFailure("JSON_INVALID", "non-finite JSON is prohibited: " + str(value))


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON_INVALID", "duplicate JSON key is prohibited")
        result[key] = value
    return result


def load_strict_json(path, label):
    try:
        size = os.path.getsize(path)
        require(size <= MAX_JSON_BYTES, "JSON_INVALID", label + " is too large")
        with open(path, "rb") as handle:
            raw = handle.read(MAX_JSON_BYTES + 1)
        value = json.loads(
            raw.decode("utf-8", "strict"),
            parse_constant=reject_json_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except SmokeFailure:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SmokeFailure("JSON_INVALID", label + " is not strict JSON") from exc
    require(type(value) is dict, "JSON_INVALID", label + " must be an object")
    return value, raw


def canonical_path(value):
    return os.path.realpath(os.path.abspath(str(value))).replace("\\", "/")


def direct_attempt_child(value, attempt_root, expected_name, label):
    path = canonical_path(value)
    root = canonical_path(attempt_root)
    require(path.startswith(root + "/"), "PATH_INVALID", label + " escapes attempt")
    require(os.path.dirname(path) == root, "PATH_INVALID", label + " is not direct")
    require(
        os.path.basename(path) == expected_name, "PATH_INVALID", label + " name differs"
    )
    return path


def project_child(value, attempt_root, expected_name):
    path = canonical_path(value)
    root = canonical_path(os.path.join(attempt_root, "project"))
    require(path.startswith(root + "/"), "PATH_INVALID", "project file escapes project")
    require(os.path.dirname(path) == root, "PATH_INVALID", "project file is not direct")
    require(
        os.path.basename(path) == expected_name, "PATH_INVALID", "project name differs"
    )
    return path


def reject_git_ancestor(path):
    current = canonical_path(path)
    while True:
        require(
            not os.path.lexists(os.path.join(current, ".git")),
            "DESTINATION_IN_GIT",
            "source-format UAssets are below Git metadata",
        )
        parent = os.path.dirname(current)
        if parent == current:
            return
        current = parent


def write_all(descriptor, raw):
    view = memoryview(raw)
    while view:
        written = os.write(descriptor, view)
        require(written > 0, "WRITE_FAILED", "exclusive write made no progress")
        view = view[written:]


def write_exclusive(path, raw):
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        write_all(descriptor, raw)
        os.fsync(descriptor)
    except SmokeFailure:
        raise
    except OSError as exc:
        raise SmokeFailure("WRITE_FAILED", "could not seal commandlet result") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def write_result(path, sha_path, value):
    sealed = dict(value)
    sealed["content_digest"] = content_digest(sealed)
    raw = canonical_json(sealed)
    write_exclusive(path, raw)
    digest = sha256_bytes(raw)
    write_exclusive(sha_path, (digest + "  " + os.path.basename(path) + "\n").encode())


def _request_paths():
    request_path = canonical_path(os.environ.get(REQUEST_ENV, ""))
    result_path = canonical_path(os.environ.get(RESULT_ENV, ""))
    result_sha_path = canonical_path(os.environ.get(RESULT_SHA_ENV, ""))
    request_sha = os.environ.get(REQUEST_SHA_ENV, "")
    require(os.path.isfile(request_path), "REQUEST_INVALID", "request is missing")
    require(
        SHA256_RE.fullmatch(request_sha) is not None,
        "REQUEST_INVALID",
        "request pin differs",
    )
    return request_path, request_sha, result_path, result_sha_path


def _exact_engine_pin_path(engine_directory, relative, label):
    require(
        type(relative) is str
        and relative.startswith("Engine/Plugins/")
        and "\\" not in relative
        and ".." not in relative.split("/"),
        "REQUEST_INVALID",
        label + " relative path differs",
    )
    candidate = os.path.abspath(
        os.path.join(engine_directory, *relative.split("/")[1:])
    ).replace("\\", "/")
    resolved = canonical_path(candidate)
    require(
        candidate == resolved
        and resolved.startswith(engine_directory + "/Plugins/")
        and os.path.isfile(resolved),
        "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
        label + " is not the exact canonical engine file",
    )
    return resolved


def _validate_engine_plugin_descriptors(request, engine_directory):
    require(
        request.get("engine_plugin_descriptors") == ENGINE_PLUGIN_PINS,
        "REQUEST_INVALID",
        "engine plugin descriptor pins differ",
    )
    evidence = []
    for plugin in ENGINE_PLUGIN_PINS:
        plugin_path = _exact_engine_pin_path(
            engine_directory,
            plugin["relative_path"],
            plugin["name"] + " plugin descriptor",
        )
        require(
            os.path.getsize(plugin_path) == plugin["size_bytes"]
            and sha256_file(plugin_path) == plugin["sha256"],
            "ENGINE_PLUGIN_PIN_MISMATCH",
            "engine plugin descriptor differs",
        )
        descriptor, _plugin_raw = load_strict_json(
            plugin_path, plugin["name"] + " plugin descriptor"
        )
        modules = descriptor.get("Modules")
        require(
            type(modules) is list
            and set(plugin["required_native_modules"]).issubset(
                {module.get("Name") for module in modules if type(module) is dict}
            ),
            "ENGINE_PLUGIN_PIN_MISMATCH",
            "required native module is absent from plugin descriptor",
        )
        evidence.append({**plugin, "descriptor_file_validated": True})
    return evidence


def _native_authority_contract():
    receipt_paths = [
        pin["modules_receipt_relative_path"] for pin in ENGINE_MODULES_RECEIPT_PINS
    ]
    use_counts = {path: 0 for path in receipt_paths}
    for binary in ENGINE_NATIVE_BINARY_PINS:
        require(
            binary["modules_receipt_relative_path"] in use_counts,
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            "native binary receipt association differs",
        )
        use_counts[binary["modules_receipt_relative_path"]] += 1
    required_modules_by_plugin = {
        plugin["name"]: sorted(plugin["required_native_modules"])
        for plugin in ENGINE_PLUGIN_PINS
    }
    observed_modules_by_plugin = {}
    for binary in ENGINE_NATIVE_BINARY_PINS:
        observed_modules_by_plugin.setdefault(binary["plugin_name"], []).append(
            binary["module_name"]
        )
    observed_modules_by_plugin = {
        plugin_name: sorted(module_names)
        for plugin_name, module_names in observed_modules_by_plugin.items()
    }
    require(
        observed_modules_by_plugin == required_modules_by_plugin
        and {pin["plugin_name"] for pin in ENGINE_MODULES_RECEIPT_PINS}
        == set(required_modules_by_plugin),
        "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
        "native binaries do not exactly cover required plugin modules",
    )
    return {
        "binary_files": ENGINE_NATIVE_BINARY_PINS,
        "inventory": {
            "binary_file_count": len(ENGINE_NATIVE_BINARY_PINS),
            "distinct_file_count": (
                len(ENGINE_NATIVE_BINARY_PINS) + len(ENGINE_MODULES_RECEIPT_PINS)
            ),
            "modules_receipt_file_count": len(ENGINE_MODULES_RECEIPT_PINS),
            "shared_modules_receipt_paths": sorted(
                path for path, count in use_counts.items() if count > 1
            ),
        },
        "modules_receipt_files": ENGINE_MODULES_RECEIPT_PINS,
    }


def _validate_engine_native_authority(request, engine_directory):
    contract = _native_authority_contract()
    require(
        request.get("engine_native_authority") == contract,
        "REQUEST_INVALID",
        "engine native authority differs",
    )
    binary_paths = [pin["binary_relative_path"] for pin in ENGINE_NATIVE_BINARY_PINS]
    receipt_paths = [
        pin["modules_receipt_relative_path"] for pin in ENGINE_MODULES_RECEIPT_PINS
    ]
    require(
        len(binary_paths) == len(set(binary_paths))
        and len(receipt_paths) == len(set(receipt_paths))
        and not set(binary_paths).intersection(receipt_paths)
        and contract["inventory"]["binary_file_count"] == 7
        and contract["inventory"]["modules_receipt_file_count"] == 4
        and contract["inventory"]["distinct_file_count"] == 11,
        "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
        "native authority distinct-file inventory differs",
    )
    receipt_by_relative = {
        pin["modules_receipt_relative_path"]: pin for pin in ENGINE_MODULES_RECEIPT_PINS
    }
    binary_evidence = []
    for pin in ENGINE_NATIVE_BINARY_PINS:
        binary_path = _exact_engine_pin_path(
            engine_directory,
            pin["binary_relative_path"],
            pin["module_name"] + " binary",
        )
        receipt_pin = receipt_by_relative.get(pin["modules_receipt_relative_path"])
        require(
            receipt_pin is not None
            and receipt_pin["plugin_name"] == pin["plugin_name"]
            and receipt_pin["module_bindings"].get(pin["module_name"])
            == os.path.basename(binary_path)
            and os.path.getsize(binary_path) == pin["binary_size_bytes"]
            and sha256_file(binary_path) == pin["binary_sha256"],
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            pin["module_name"] + " native module binary differs",
        )
        binary_evidence.append({**pin, "binary_file_validated": True})
    receipt_evidence = []
    for pin in ENGINE_MODULES_RECEIPT_PINS:
        receipt_path = _exact_engine_pin_path(
            engine_directory,
            pin["modules_receipt_relative_path"],
            pin["plugin_name"] + " UnrealEditor.modules receipt",
        )
        require(
            os.path.getsize(receipt_path) == pin["modules_receipt_size_bytes"]
            and sha256_file(receipt_path) == pin["modules_receipt_sha256"],
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            pin["plugin_name"] + " UnrealEditor.modules receipt differs",
        )
        receipt, _receipt_raw = load_strict_json(
            receipt_path, pin["plugin_name"] + " UnrealEditor.modules receipt"
        )
        modules = receipt.get("Modules")
        require(
            receipt.get("BuildId") == pin["modules_receipt_build_id"]
            and type(modules) is dict
            and all(
                modules.get(module) == filename
                for module, filename in pin["module_bindings"].items()
            ),
            "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
            pin["plugin_name"] + " module receipt binding differs",
        )
        receipt_evidence.append(
            {
                **pin,
                "modules_receipt_binding_validated": True,
            }
        )
    return {
        "binary_files": binary_evidence,
        "inventory": contract["inventory"],
        "modules_receipt_files": receipt_evidence,
    }


def _validate_request(
    request, request_raw, request_path, request_sha, result_path, result_sha_path
):
    require(
        request_raw == canonical_json(request),
        "REQUEST_INVALID",
        "request is not canonical",
    )
    require(
        sha256_bytes(request_raw) == request_sha,
        "REQUEST_INVALID",
        "request SHA differs",
    )
    require(
        request.get("schema_version") == REQUEST_SCHEMA,
        "REQUEST_INVALID",
        "schema differs",
    )
    require(
        request.get("content_digest") == content_digest(request),
        "REQUEST_INVALID",
        "digest differs",
    )
    attempt_root = canonical_path(request.get("attempt_root", ""))
    require(os.path.isdir(attempt_root), "PATH_INVALID", "attempt root is missing")
    reject_git_ancestor(attempt_root)
    require(
        direct_attempt_child(request_path, attempt_root, REQUEST_NAME, "request")
        == request_path,
        "PATH_INVALID",
        "request binding differs",
    )
    require(
        direct_attempt_child(result_path, attempt_root, RESULT_NAME, "result")
        == result_path,
        "PATH_INVALID",
        "result binding differs",
    )
    require(
        direct_attempt_child(
            result_sha_path,
            attempt_root,
            RESULT_NAME + ".sha256",
            "result sidecar",
        )
        == result_sha_path,
        "PATH_INVALID",
        "result sidecar binding differs",
    )
    project_path = project_child(
        request.get("project_file", ""), attempt_root, PROJECT_NAME
    )
    commandlet_path = direct_attempt_child(
        request.get("commandlet_path", ""),
        attempt_root,
        COMMANDLET_NAME,
        "commandlet",
    )
    manifest_path = direct_attempt_child(
        request.get("copy_manifest_path", ""),
        attempt_root,
        COPY_MANIFEST_NAME,
        "copy manifest",
    )
    require(
        request.get("result_path") == result_path,
        "REQUEST_INVALID",
        "result path differs",
    )
    require(
        request.get("result_sha256_path") == result_sha_path,
        "REQUEST_INVALID",
        "result sidecar path differs",
    )
    require(
        request.get("engine_version") == ENGINE_VERSION,
        "REQUEST_INVALID",
        "engine pin differs",
    )
    engine_directory = canonical_path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.engine_dir())
    )
    plugin_descriptor_evidence = _validate_engine_plugin_descriptors(
        request, engine_directory
    )
    native_module_evidence = _validate_engine_native_authority(
        request, engine_directory
    )
    require(
        SHA256_RE.fullmatch(str(request.get("commandlet_sha256", ""))) is not None,
        "REQUEST_INVALID",
        "commandlet pin is malformed",
    )
    require(
        sha256_file(commandlet_path) == request["commandlet_sha256"],
        "COMMANDLET_PIN_MISMATCH",
        "copied commandlet differs",
    )
    require(
        sha256_file(project_path) == request.get("project_sha256"),
        "PROJECT_PIN_MISMATCH",
        "disposable project descriptor differs",
    )
    project, project_raw = load_strict_json(project_path, "disposable project")
    require(
        project_raw == canonical_json(project),
        "PROJECT_PIN_MISMATCH",
        "disposable project descriptor is not canonical",
    )
    require(
        project.get("Plugins")
        == [
            {"Enabled": True, "Name": "EditorScriptingUtilities"},
            {"Enabled": True, "Name": "HairStrands"},
            {"Enabled": True, "Name": "MassGameplay"},
            {"Enabled": True, "Name": "PythonScriptPlugin"},
            {"Enabled": True, "Name": "RigLogic"},
            {"Enabled": True, "Name": "SunPosition"},
        ]
        and "Modules" not in project,
        "PROJECT_PIN_MISMATCH",
        "disposable project plugin/module policy differs",
    )
    observed_project = canonical_path(unreal.Paths.get_project_file_path())
    require(
        observed_project == project_path,
        "PROJECT_PIN_MISMATCH",
        "runtime project differs",
    )
    authorization = request.get("authorization")
    require(type(authorization) is dict, "REQUEST_INVALID", "authorization is missing")
    required_authorization = {
        "epic_ue_only_content_entitlement_acknowledged": True,
        "large_full_content_copy_acknowledged": True,
        "no_redistribution_acknowledged": True,
        "private_noncommercial_research_acknowledged": True,
        "source_uassets_outside_git_acknowledged": True,
    }
    require(
        authorization == required_authorization,
        "REQUEST_INVALID",
        "authorization differs",
    )
    require(
        request.get("source_content_projection")
        == {
            "file_count": PINNED_CONTENT_FILE_COUNT,
            "metadata_projection_sha256": (PINNED_CONTENT_METADATA_PROJECTION_SHA256),
            "size_bytes": PINNED_CONTENT_SIZE_BYTES,
        },
        "REQUEST_INVALID",
        "source Content projection differs",
    )
    require(
        request.get("execution_contract")
        == {
            "cuda_visible_devices": "0",
            "display_present": False,
            "fixed_arguments_after_script": FIXED_COMMAND_ARGUMENTS_AFTER_SCRIPT,
            "network_transport_disable_flags": NETWORK_TRANSPORT_DISABLE_FLAGS,
            "network_ports": [],
            "xauthority_present": False,
        },
        "REQUEST_INVALID",
        "execution contract differs",
    )
    require(
        os.environ.get("CUDA_VISIBLE_DEVICES") == "0"
        and "DISPLAY" not in os.environ
        and "XAUTHORITY" not in os.environ
        and not any(
            key in os.environ
            for key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            )
        ),
        "EXECUTION_CONTRACT_INVALID",
        "runtime GPU/display/network environment differs",
    )
    policy = request.get("policy")
    require(type(policy) is dict, "REQUEST_INVALID", "policy is missing")
    require(
        policy.get("accepted") is False, "REQUEST_INVALID", "request is pre-accepted"
    )
    require(policy.get("gpu") == 0, "REQUEST_INVALID", "GPU policy differs")
    require(policy.get("null_rhi") is True, "REQUEST_INVALID", "NullRHI policy differs")
    require(
        policy.get("network_ports") == [], "REQUEST_INVALID", "network policy differs"
    )
    require(
        policy.get("source_project_opened_by_unreal") is False,
        "REQUEST_INVALID",
        "source project policy differs",
    )
    require(
        policy.get("publish_character_provider") is False
        and policy.get("runtime_visual_acceptance") is False,
        "REQUEST_INVALID",
        "promotion policy differs",
    )
    require(
        policy.get("copy_strategy")
        == "full_content_and_sanitized_config_then_registry_audit",
        "REQUEST_INVALID",
        "copy strategy policy differs",
    )
    return (
        attempt_root,
        project_path,
        commandlet_path,
        manifest_path,
        plugin_descriptor_evidence,
        native_module_evidence,
    )


def _validate_copy_manifest(request, manifest_path, project_path):
    manifest, raw = load_strict_json(manifest_path, "copy manifest")
    require(
        raw == canonical_json(manifest), "MANIFEST_INVALID", "manifest is not canonical"
    )
    require(
        SHA256_RE.fullmatch(str(request.get("copy_manifest_sha256", ""))) is not None,
        "MANIFEST_INVALID",
        "manifest SHA-256 pin is malformed",
    )
    require(
        sha256_bytes(raw) == request["copy_manifest_sha256"],
        "MANIFEST_INVALID",
        "manifest SHA-256 pin differs",
    )
    sidecar_path = manifest_path + ".sha256"
    try:
        with open(sidecar_path, "rb") as handle:
            sidecar = handle.read(256)
    except OSError as exc:
        raise SmokeFailure(
            "MANIFEST_INVALID", "manifest sidecar is unavailable"
        ) from exc
    require(
        sidecar
        == (
            request["copy_manifest_sha256"] + "  " + COPY_MANIFEST_NAME + "\n"
        ).encode(),
        "MANIFEST_INVALID",
        "manifest sidecar differs",
    )
    require(
        manifest.get("content_digest") == content_digest(manifest),
        "MANIFEST_INVALID",
        "manifest content digest differs",
    )
    require(
        manifest.get("schema_version") == COPY_MANIFEST_SCHEMA,
        "MANIFEST_INVALID",
        "manifest schema differs",
    )
    require(
        manifest.get("accepted") is False,
        "MANIFEST_INVALID",
        "manifest is pre-accepted",
    )
    require(
        manifest.get("copy_strategy")
        == "full_content_and_sanitized_config_then_registry_audit",
        "MANIFEST_INVALID",
        "copy strategy differs",
    )
    require(
        manifest.get("source_metadata_projection_sha256")
        == request.get("copy_projection_sha256"),
        "MANIFEST_INVALID",
        "source copy projection differs",
    )
    require(
        manifest.get("source_content_file_count") == PINNED_CONTENT_FILE_COUNT
        and manifest.get("source_content_size_bytes") == PINNED_CONTENT_SIZE_BYTES
        and manifest.get("source_metadata_projection_sha256")
        == PINNED_CONTENT_METADATA_PROJECTION_SHA256,
        "MANIFEST_INVALID",
        "source Content inventory pins differ",
    )
    require(
        manifest.get("source_format_uassets_in_git") is False
        and manifest.get("redistribution_authorized") is False
        and manifest.get("source_config_copied") is False
        and manifest.get("source_network_settings_copied") is False,
        "MANIFEST_INVALID",
        "manifest policy differs",
    )
    records = manifest.get("files")
    require(
        type(records) is list and records,
        "MANIFEST_INVALID",
        "manifest files are empty",
    )
    require(
        manifest.get("file_count") == len(records),
        "MANIFEST_INVALID",
        "file count differs",
    )
    observed_size = 0
    observed_paths = []
    record_by_path = {}
    project_root = canonical_path(os.path.dirname(project_path))
    for record in records:
        require(type(record) is dict, "MANIFEST_INVALID", "manifest record differs")
        relative = record.get("project_relative_path")
        digest = record.get("sha256")
        size = record.get("size_bytes")
        require(
            type(relative) is str and relative,
            "MANIFEST_INVALID",
            "relative path differs",
        )
        require(
            not relative.startswith("/") and ".." not in relative.split("/"),
            "MANIFEST_INVALID",
            "relative path escapes project",
        )
        require(
            relative.startswith(("Config/", "Content/")),
            "MANIFEST_INVALID",
            "manifest includes an unsupported root",
        )
        require(
            SHA256_RE.fullmatch(str(digest)) is not None,
            "MANIFEST_INVALID",
            "file digest differs",
        )
        require(
            type(size) is int and size >= 0, "MANIFEST_INVALID", "file size differs"
        )
        source_kind = record.get("source_kind")
        if relative.startswith("Config/"):
            require(
                source_kind == "project_generated_sanitized_config"
                and relative in SANITIZED_CONFIG_PINS
                and (digest, size) == SANITIZED_CONFIG_PINS[relative],
                "MANIFEST_INVALID",
                "generated sanitized Config pin differs",
            )
        else:
            require(
                source_kind == "pinned_source_content_copy",
                "MANIFEST_INVALID",
                "source Content record kind differs",
            )
        candidate = canonical_path(os.path.join(project_root, *relative.split("/")))
        require(
            candidate.startswith(project_root + "/"),
            "MANIFEST_INVALID",
            "file escapes project",
        )
        require(os.path.isfile(candidate), "MANIFEST_INVALID", "copied file is missing")
        require(
            os.path.getsize(candidate) == size,
            "MANIFEST_INVALID",
            "copied size differs",
        )
        require(
            sha256_file(candidate) == digest,
            "MANIFEST_INVALID",
            "copied file digest differs",
        )
        observed_size += size
        observed_paths.append(relative)
        record_by_path[relative] = record
    require(
        observed_paths == sorted(observed_paths),
        "MANIFEST_INVALID",
        "file order differs",
    )
    require(
        len(observed_paths) == len(set(observed_paths)),
        "MANIFEST_INVALID",
        "duplicate path",
    )
    require(
        manifest.get("size_bytes") == observed_size,
        "MANIFEST_INVALID",
        "total size differs",
    )
    actual_paths = []
    for root_name in ("Config", "Content"):
        tree_root = os.path.join(project_root, root_name)
        for directory, directory_names, file_names in os.walk(
            tree_root, topdown=True, followlinks=False
        ):
            directory_names.sort()
            file_names.sort()
            for name in directory_names:
                require(
                    not os.path.islink(os.path.join(directory, name)),
                    "MANIFEST_INVALID",
                    "copied tree contains a directory link",
                )
            for name in file_names:
                candidate = os.path.join(directory, name)
                require(
                    not os.path.islink(candidate),
                    "MANIFEST_INVALID",
                    "copied tree contains a file link",
                )
                actual_paths.append(
                    os.path.relpath(candidate, project_root).replace("\\", "/")
                )
    require(
        sorted(actual_paths) == observed_paths,
        "MANIFEST_INVALID",
        "copied tree inventory differs from sealed manifest",
    )
    require(
        set(SANITIZED_CONFIG_PINS).issubset(record_by_path),
        "MANIFEST_INVALID",
        "sanitized Config inventory differs",
    )
    source_content_records = [
        record
        for record in records
        if record.get("source_kind") == "pinned_source_content_copy"
    ]
    require(
        len(source_content_records) == PINNED_CONTENT_FILE_COUNT
        and sum(record["size_bytes"] for record in source_content_records)
        == PINNED_CONTENT_SIZE_BYTES
        and len(records) == PINNED_CONTENT_FILE_COUNT + len(SANITIZED_CONFIG_PINS),
        "MANIFEST_INVALID",
        "sealed source Content record inventory differs",
    )
    return record_by_path


def _validate_pinned_copied_uassets(request, project_path, record_by_path):
    project_root = canonical_path(os.path.dirname(project_path))
    target = request.get("target")
    require(type(target) is dict, "REQUEST_INVALID", "target is missing")
    require(
        target
        == {
            "asset_class": "Blueprint",
            "class_path": TARGET_CLASS,
            "default_object_path": TARGET_CDO_PATH,
            "generated_class_path": TARGET_CLASS,
            "object_path": TARGET_OBJECT,
            "package_name": TARGET_PACKAGE,
            "project_relative_path": "Content/CitySampleCrowd/Blueprints/BP_CrowdCharacter.uasset",
            "sha256": TARGET_UASSET_SHA256,
            "size_bytes": TARGET_UASSET_SIZE,
        },
        "REQUEST_INVALID",
        "target contract differs",
    )
    key_dependencies = request.get("key_dependencies")
    require(
        key_dependencies == KEY_DEPENDENCY_BINDINGS,
        "REQUEST_INVALID",
        "key dependency inventory differs",
    )
    sources = [target] + key_dependencies
    require(len(sources) == 4, "REQUEST_INVALID", "key dependency inventory differs")
    for source in sources:
        require(type(source) is dict, "REQUEST_INVALID", "key dependency differs")
        relative = source.get("project_relative_path")
        record = record_by_path.get(relative)
        require(
            record is not None, "COPY_PIN_MISMATCH", "pinned copied UAsset is absent"
        )
        require(
            record.get("sha256") == source.get("sha256")
            and record.get("size_bytes") == source.get("size_bytes"),
            "COPY_PIN_MISMATCH",
            "pinned copied UAsset manifest entry differs",
        )
        candidate = canonical_path(os.path.join(project_root, *relative.split("/")))
        require(
            sha256_file(candidate) == source["sha256"],
            "COPY_PIN_MISMATCH",
            "UAsset bytes differ",
        )


def _dependency_options():
    try:
        options = unreal.AssetRegistryDependencyOptions()
    except Exception as exc:
        raise SmokeFailure(
            "ASSET_REGISTRY_UNAVAILABLE", "dependency options are unavailable"
        ) from exc
    values = {
        "include_hard_package_references": True,
        "include_soft_package_references": True,
        "include_hard_management_references": False,
        "include_soft_management_references": False,
        "include_searchable_names": False,
    }
    for name, value in values.items():
        try:
            options.set_editor_property(name, value)
        except Exception:  # noqa: BLE001 - Unreal reflection exceptions vary by build.
            try:
                setattr(options, name, value)
            except Exception as exc:
                raise SmokeFailure(
                    "ASSET_REGISTRY_UNAVAILABLE", "dependency option API differs"
                ) from exc
    return options


def _package_strings(value):
    if value is None:
        return []
    # Some engine versions expose a success/result tuple while UE 5.7 normally
    # returns an array directly.  Accept only the successful tuple form.
    if type(value) is tuple and len(value) == 2 and type(value[0]) is bool:
        require(value[0] is True, "ASSET_REGISTRY_FAILED", "dependency query failed")
        value = value[1]
    try:
        items = list(value)
    except TypeError as exc:
        raise SmokeFailure(
            "ASSET_REGISTRY_FAILED", "dependency result is not iterable"
        ) from exc
    result = []
    for item in items:
        text = str(item)
        require(
            text.startswith("/"), "ASSET_REGISTRY_FAILED", "dependency name differs"
        )
        result.append(text)
    return sorted(set(result))


def _recursive_dependencies(registry, package_name, options):
    pending = [package_name]
    visited = {package_name}
    dependencies = set()
    while pending:
        current = pending.pop(0)
        try:
            observed = registry.get_dependencies(current, options)
        except Exception as exc:
            raise SmokeFailure(
                "ASSET_REGISTRY_FAILED", "recursive dependency query failed"
            ) from exc
        for dependency in _package_strings(observed):
            if dependency in visited:
                continue
            visited.add(dependency)
            dependencies.add(dependency)
            require(
                len(visited) <= MAX_DEPENDENCY_PACKAGES,
                "ASSET_REGISTRY_FAILED",
                "dependency closure exceeds the closed bound",
            )
            pending.append(dependency)
    return sorted(dependencies)


def _asset_data_for_package(registry, package_name):
    try:
        values = registry.get_assets_by_package_name(package_name, True)
    except TypeError:
        try:
            values = registry.get_assets_by_package_name(package_name)
        except Exception as exc:
            raise SmokeFailure(
                "ASSET_REGISTRY_FAILED", "asset data query failed"
            ) from exc
    except Exception as exc:
        raise SmokeFailure("ASSET_REGISTRY_FAILED", "asset data query failed") from exc
    try:
        return list(values)
    except TypeError as exc:
        raise SmokeFailure(
            "ASSET_REGISTRY_FAILED", "asset data result differs"
        ) from exc


def _property(value, name):
    try:
        return value.get_editor_property(name)
    except Exception:  # noqa: BLE001 - Unreal reflection exceptions vary by build.
        return getattr(value, name, None)


def _class_name(asset_data):
    value = _property(asset_data, "asset_class_path")
    if value is None:
        value = _property(asset_data, "asset_class")
    nested_name = _property(value, "asset_name") if value is not None else None
    if nested_name:
        return str(nested_name)
    text = str(value)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def _asset_record(asset_data, package_name):
    object_path = str(_property(asset_data, "object_path") or "")
    if not object_path:
        asset_name = str(_property(asset_data, "asset_name") or "")
        object_path = package_name + "." + asset_name if asset_name else package_name
    return {
        "asset_class": _class_name(asset_data),
        "object_path": object_path,
        "package_name": package_name,
    }


def _target_asset_data_evidence(registry):
    observed = [
        _asset_record(asset_data, TARGET_PACKAGE)
        for asset_data in _asset_data_for_package(registry, TARGET_PACKAGE)
    ]
    expected = {
        "asset_class": "Blueprint",
        "object_path": TARGET_OBJECT,
        "package_name": TARGET_PACKAGE,
    }
    require(
        observed == [expected],
        "TARGET_ASSET_DATA_MISMATCH",
        "target package does not contain the one exact Blueprint AssetData",
    )
    return expected


def _key_dependency_evidence(records, dependencies, request):
    require(
        request.get("key_dependencies") == KEY_DEPENDENCY_BINDINGS,
        "REQUEST_INVALID",
        "key dependency bindings differ",
    )
    dependency_set = set(dependencies)
    evidence = []
    for binding in KEY_DEPENDENCY_BINDINGS:
        expected_record = {
            "asset_class": binding["asset_class"],
            "object_path": binding["object_path"],
            "package_name": binding["package_name"],
        }
        matching = [record for record in records if record == expected_record]
        require(
            binding["package_name"] in dependency_set and matching == [expected_record],
            "KEY_DEPENDENCY_MISMATCH",
            "an exact key dependency package/object/class is not reachable",
        )
        evidence.append(
            {
                **expected_record,
                "kind": binding["kind"],
                "reachable": True,
            }
        )
    return evidence


def _dependency_class_inventory(registry, dependencies):
    records = []
    class_counts = {}
    for package in dependencies:
        for asset_data in _asset_data_for_package(registry, package):
            record = _asset_record(asset_data, package)
            records.append(record)
            class_name = record["asset_class"]
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
    records.sort(
        key=lambda item: (
            item["package_name"],
            item["object_path"],
            item["asset_class"],
        )
    )
    return records, dict(sorted(class_counts.items()))


def _load_exact_target_class():
    try:
        blueprint = unreal.EditorAssetLibrary.load_asset(TARGET_OBJECT)
        generated_class = unreal.EditorAssetLibrary.load_blueprint_class(TARGET_OBJECT)
        loaded_class = unreal.load_class(None, TARGET_CLASS)
    except Exception as exc:
        raise SmokeFailure(
            "CLASS_FORWARD_LOAD_FAILED", "exact target Blueprint/class load raised"
        ) from exc
    require(
        blueprint is not None and str(blueprint.get_path_name()) == TARGET_OBJECT,
        "CLASS_FORWARD_LOAD_FAILED",
        "loaded Blueprint object binding differs",
    )
    require(
        generated_class is not None
        and str(generated_class.get_path_name()) == TARGET_CLASS,
        "CLASS_FORWARD_LOAD_FAILED",
        "Blueprint GeneratedClass binding differs",
    )
    require(
        loaded_class is not None
        and str(loaded_class.get_path_name()) == TARGET_CLASS
        and loaded_class == generated_class,
        "CLASS_FORWARD_LOAD_FAILED",
        "loaded class does not equal the exact Blueprint GeneratedClass",
    )
    try:
        default_object = unreal.get_default_object(loaded_class)
    except Exception as exc:
        raise SmokeFailure(
            "DEFAULT_OBJECT_FAILED", "exact default object load raised"
        ) from exc
    require(
        default_object is not None
        and str(default_object.get_path_name()) == TARGET_CDO_PATH,
        "DEFAULT_OBJECT_FAILED",
        "default object path is not bound to the exact target class",
    )
    try:
        is_character = isinstance(default_object, unreal.Character)
    except Exception as exc:
        raise SmokeFailure(
            "DEFAULT_OBJECT_FAILED", "Character type check raised"
        ) from exc
    require(
        is_character,
        "DEFAULT_OBJECT_FAILED",
        "exact target default object is not an Unreal Character",
    )
    try:
        components = list(
            default_object.get_components_by_class(unreal.SkeletalMeshComponent)
        )
    except Exception as exc:
        raise SmokeFailure(
            "DEFAULT_OBJECT_FAILED", "skeletal component query raised"
        ) from exc
    require(
        1 <= len(components) <= 64,
        "DEFAULT_OBJECT_FAILED",
        "exact target default object skeletal component count is invalid",
    )
    return {
        "blueprint_object_path": TARGET_OBJECT,
        "default_object_path": TARGET_CDO_PATH,
        "generated_class_path": TARGET_CLASS,
        "loaded_class_path": TARGET_CLASS,
        "skeletal_component_count": len(components),
    }


def _load_and_validate(request, native_module_evidence):
    contract = _native_authority_contract()
    require(
        native_module_evidence
        == {
            "binary_files": [
                {**pin, "binary_file_validated": True}
                for pin in contract["binary_files"]
            ],
            "inventory": contract["inventory"],
            "modules_receipt_files": [
                {**pin, "modules_receipt_binding_validated": True}
                for pin in contract["modules_receipt_files"]
            ],
        },
        "ENGINE_NATIVE_MODULE_PIN_MISMATCH",
        "native module validation evidence differs",
    )
    runtime_version = str(unreal.SystemLibrary.get_engine_version())
    require(
        runtime_version == ENGINE_VERSION,
        "ENGINE_PIN_MISMATCH",
        "runtime engine differs",
    )
    try:
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        registry.scan_paths_synchronous([TARGET_ROOT], True, False)
        registry.wait_for_completion()
    except Exception as exc:
        raise SmokeFailure(
            "ASSET_REGISTRY_UNAVAILABLE", "could not scan target root"
        ) from exc
    target_asset_data = _target_asset_data_evidence(registry)
    options = _dependency_options()
    dependencies = _recursive_dependencies(registry, TARGET_PACKAGE, options)
    require(
        dependencies, "DEPENDENCY_CLOSURE_EMPTY", "target dependency closure is empty"
    )
    records, class_counts = _dependency_class_inventory(registry, dependencies)

    dependency_policy = request.get("dependency_policy")
    require(
        dependency_policy
        == {
            "asset_registry_required": True,
            "include_hard_package_references": True,
            "include_soft_package_references": True,
            "recursive": True,
            "required_asset_classes": ["AnimBlueprint", "SkeletalMesh", "Skeleton"],
            "root": TARGET_ROOT,
        },
        "REQUEST_INVALID",
        "dependency policy differs",
    )
    key_dependency_evidence = _key_dependency_evidence(records, dependencies, request)
    class_evidence = _load_exact_target_class()
    closure_digest = sha256_bytes(
        canonical_json(
            {
                "asset_records": records,
                "packages": dependencies,
            }
        )
    )
    return {
        "dependency_packages": dependencies,
        "dependency_asset_records": records,
        "dependency_asset_count": len(records),
        "dependency_class_counts": class_counts,
        "dependency_closure_sha256": closure_digest,
        "target_asset_data": target_asset_data,
        "blueprint_object_path": class_evidence["blueprint_object_path"],
        "generated_class_path": class_evidence["generated_class_path"],
        "loaded_class_path": class_evidence["loaded_class_path"],
        "default_object_path": class_evidence["default_object_path"],
        "skeletal_component_count": class_evidence["skeletal_component_count"],
        "key_dependency_evidence": key_dependency_evidence,
        "gates": {
            "asset_registry_dependency_closure_validated": True,
            "blueprint_generated_class_bound": True,
            "class_forward_load_validated": True,
            "default_object_is_character": True,
            "default_object_path_bound": True,
            "engine_plugin_descriptors_validated": True,
            "engine_native_authority_validated": True,
            "key_anim_dependency_validated": True,
            "key_skeletal_mesh_dependency_validated": True,
            "key_skeleton_dependency_validated": True,
            "source_uassets_remained_outside_git": True,
            "target_asset_data_validated": True,
        },
    }


def _failure_result(request, code, message):
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "failed_quarantined_no_reuse",
        "accepted": False,
        "failure_code": code,
        "failure_message": message,
        "engine_version": ENGINE_VERSION,
        "target_class_path": TARGET_CLASS,
        "target_uasset_sha256": TARGET_UASSET_SHA256,
        "copy_projection_sha256": request.get("copy_projection_sha256"),
        "commandlet_sha256": request.get("commandlet_sha256"),
        "gates": {
            "asset_registry_dependency_closure_validated": False,
            "blueprint_generated_class_bound": False,
            "class_forward_load_validated": False,
            "default_object_is_character": False,
            "default_object_path_bound": False,
            "engine_plugin_descriptors_validated": False,
            "engine_native_authority_validated": False,
            "key_anim_dependency_validated": False,
            "key_skeletal_mesh_dependency_validated": False,
            "key_skeleton_dependency_validated": False,
            "source_uassets_remained_outside_git": False,
            "target_asset_data_validated": False,
        },
        "runtime_visual_acceptance": False,
        "character_provider_published": False,
    }


def main():
    request = {}
    request_path = request_sha = result_path = result_sha_path = None
    try:
        request_path, request_sha, result_path, result_sha_path = _request_paths()
        request, request_raw = load_strict_json(request_path, "request")
        (
            _,
            project_path,
            _,
            manifest_path,
            plugin_descriptor_evidence,
            native_module_evidence,
        ) = _validate_request(
            request,
            request_raw,
            request_path,
            request_sha,
            result_path,
            result_sha_path,
        )
        record_by_path = _validate_copy_manifest(request, manifest_path, project_path)
        _validate_pinned_copied_uassets(request, project_path, record_by_path)
        observed = _load_and_validate(request, native_module_evidence)
        result = {
            "schema_version": RESULT_SCHEMA,
            "status": "forward_load_validated_private_research_only",
            "accepted": False,
            "engine_version": ENGINE_VERSION,
            "target_class_path": TARGET_CLASS,
            "target_uasset_sha256": TARGET_UASSET_SHA256,
            "copy_projection_sha256": request["copy_projection_sha256"],
            "commandlet_sha256": request["commandlet_sha256"],
            "engine_plugin_descriptor_evidence": plugin_descriptor_evidence,
            "engine_native_module_evidence": native_module_evidence,
            **observed,
            "runtime_visual_acceptance": False,
            "character_provider_published": False,
        }
        write_result(result_path, result_sha_path, result)
        unreal.log("VISTA_CITYSAMPLE_CROWD_HUMAN_FORWARD_LOAD_VALIDATED")
        return
    except SmokeFailure as error:
        if result_path and result_sha_path:
            try:
                write_result(
                    result_path,
                    result_sha_path,
                    _failure_result(request, error.code, error.message),
                )
            except Exception:  # noqa: BLE001 - preserve the primary smoke failure.
                unreal.log_error(
                    "VISTA_CITYSAMPLE_CROWD_HUMAN_FAILURE_RESULT_WRITE_FAILED"
                )
        unreal.log_error("VISTA_CITYSAMPLE_CROWD_HUMAN_QUARANTINED " + error.code)
        raise RuntimeError(
            "CitySampleCrowd forward-load smoke failed; attempt quarantined: "
            + error.code
        ) from error
    except Exception as unexpected:
        error = SmokeFailure(
            "COMMANDLET_FAILED", "unexpected commandlet failure; attempt quarantined"
        )
        if result_path and result_sha_path:
            try:
                write_result(
                    result_path,
                    result_sha_path,
                    _failure_result(request, error.code, error.message),
                )
            except Exception:  # noqa: BLE001 - preserve the primary smoke failure.
                unreal.log_error(
                    "VISTA_CITYSAMPLE_CROWD_HUMAN_FAILURE_RESULT_WRITE_FAILED"
                )
        unreal.log_error("VISTA_CITYSAMPLE_CROWD_HUMAN_QUARANTINED " + error.code)
        raise RuntimeError(
            "CitySampleCrowd forward-load smoke failed; attempt quarantined: "
            + error.code
        ) from unexpected


main()
