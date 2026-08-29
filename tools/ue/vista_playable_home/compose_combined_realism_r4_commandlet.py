"""Upgrade the sealed combined R3 map to the additive R4 lighting contract.

This script is copied and SHA-pinned by ``materialize_combined_realism_r4``.
It has no network, rendering, agent, VLM, or mutable asset-provider surface.
Only the four exact legacy R2 actors in ``R2_REMOVAL_ALLOWLIST`` may be
destroyed.  Every other actor identity is preserved while the fixed six-room
fixture/light pairs and restrained post process are added.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import pathlib
import re
import stat

import unreal


EXECUTION_SCHEMA = "simworld.vista.human-visual-demo-combined-realism-r4-execution/v1"
RESULT_SCHEMA = "simworld.vista.human-visual-demo-combined-realism-r4-result/v1"
RESULT_STATUS = "realism_r4_map_saved_cold_reloaded"
FAILURE_STATUS = "realism_r4_commandlet_failed"
PROFILE_SCHEMA = "simworld.vista.playable-home-realism-r4/v1"
PROFILE_ID = "realistic_interior_r4_lighting_shadows_v1"
PROFILE_SHA256 = "887f50e7edd438c8d7952336b13cade5ef38970284093360e5f14521d6521139"
PROFILE_CONTENT_DIGEST = (
    "8df2d80cc9af526ad5cc1ff26af708642908fb9c77ba7e8b5e1ef3cf8149f090"
)
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
PROVIDER_ID = "citysample_crowd_visual_demo_v1"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
MAP_RELATIVE_PATH = (
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
PROJECT_NAME = "VistaPlayableHome.uproject"
MATERIALIZER_NAME = "materialize_combined_realism_r4.py"
COMMANDLET_NAME = "compose_combined_realism_r4_commandlet.py"
EXECUTION_NAME = "combined-realism-r4-execution.json"
PROFILE_NAME = "realism-r4-profile.json"
RESULT_NAME = "combined-realism-r4-result.json"
EXECUTION_ENV = "VISTA_COMBINED_REALISM_R4_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_COMBINED_REALISM_R4_EXECUTION_SHA256"
RESULT_ENV = "VISTA_COMBINED_REALISM_R4_RESULT"
RESULT_SIDECAR_ENV = "VISTA_COMBINED_REALISM_R4_RESULT_SIDECAR"
RESULT_MARKER = "VISTA_COMBINED_REALISM_R4_RESULT:"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
PROJECT_STATIC_ROOTS = ("Config", "Content", "Plugins")
MUTABLE_PROJECT_DIRECTORIES = frozenset({"Saved", "Intermediate", "DerivedDataCache"})
PARENT_RECEIPT_SHA256 = (
    "91dfaa32e1efc66747c93dc7e891e4ab4ed6c80aca08178fae11af9018544d5d"
)
PARENT_RECEIPT_BYTES = 2_981
SOURCE_PROJECT_STATIC_TREE = {
    "algorithm": "sha256-path-nul-mode-size-content-v1",
    "file_count": 2_444,
    "total_bytes": 9_152_732_558,
    "tree_sha256": "83228f27dafc1c6fd8e43047993229da1450311dd4fc4caa450215811b291c21",
}
SOURCE_MAP_SHA256 = "55c254d60af6b7357f6bb801f498b65993c9b98a9e8b3a99d67b5b57ea80ed45"
SOURCE_MAP_BYTES = 442_784
UNREAL_EDITOR_CMD_SHA256 = (
    "66a4391f345d5984af224feb0df15fbd26ba0e2dd1436cac7e85809c9a88d674"
)
UNREAL_EDITOR_CMD_BYTES = 459_320
BUILD_VERSION_SHA256 = (
    "ffe01f6d1e96ef86cd06158cfb561150971823fc77e5c8df352910bcf4d365ef"
)
BUILD_VERSION_BYTES = 215

LEGAL_SCOPE = {
    "private_noncommercial_research_only": True,
    "epic_ue_only_content_entitlement_confirmed": True,
    "no_source_uasset_redistribution": True,
    "external_assets_outside_git": True,
    "metahuman_human_operated_visual_demo_only": True,
    "excluded_from_vista_dataset_or_database": True,
    "excluded_from_ai_vlm_training_testing_evaluation_or_review": True,
}
CLAIMS = {
    "runtime_visual_acceptance": False,
    "interaction_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
}
ACCEPTANCE = {
    "human_visual_acceptance": "pending",
    "runtime_play_proof": "pending",
}
ACKNOWLEDGEMENTS = {
    "private_noncommercial_research": (
        "I acknowledge City Sample and HSSD use is restricted to private "
        "noncommercial research."
    ),
    "epic_ue_only_content_entitlement": (
        "I confirm my Epic entitlement and UE-only use of City Sample content."
    ),
    "no_redistribution": (
        "I acknowledge source UAssets and external asset payloads may not be "
        "redistributed."
    ),
    "external_assets_outside_git": (
        "I acknowledge every external asset payload remains outside Git."
    ),
    "large_combined_copy": (
        "I authorize the isolated large HSSD and City Sample project copy."
    ),
    "metahuman_visual_demo_only": (
        "I acknowledge City Sample and MetaHuman content is for a "
        "human-operated visual demo only and is excluded from VISTA datasets, "
        "databases, and AI/VLM training, testing, evaluation, and review."
    ),
    "hssd_attribution": (
        "I acknowledge HSSD attribution is required and public payload "
        "distribution is prohibited."
    ),
    "hssd_material_conflict": (
        "I acknowledge inherited HSSD material conflicts remain nonpromotable."
    ),
    "sealed_r3_large_copy": (
        "I authorize an isolated 9.15 GiB reflink or copy of the sealed R3 project."
    ),
}
RENDERER_CONTRACT = {
    "dynamic_gi": "software_lumen",
    "reflections": "lumen",
    "anti_aliasing": "tsr",
    "shadow_method": "virtual_shadow_maps",
    "hardware_ray_tracing": False,
    "config_is_runtime_proof": False,
}
SHADOW_POLICY = {
    "visible_presentation_cast_shadow": True,
    "visible_presentation_cast_hidden_shadow": False,
    "hidden_collision_proxy_cast_shadow": False,
    "hidden_collision_proxy_cast_hidden_shadow": False,
}
VISIBLE_ACTOR_ROLE_ALLOWLIST = frozenset({"room", "hssd_visual_shell"})
HIDDEN_ACTOR_ROLE_ALLOWLIST = frozenset({"room_collision_proxy"})
PICKUP_ROLE = "pickup"
PICKUP_PRESENTATION_COMPONENT = "PresentationMesh"
PICKUP_PROXY_COMPONENT = "PickupMesh"
EXPECTED_SOURCE_COUNTS = {
    "actors": 141,
    "room_actors": 6,
    "room_collision_proxies": 3,
    "hssd_visual_shells": 42,
    "pickup_actors": 8,
    "pickup_presentations": 3,
}
R2_RIG_TAG = "VistaLightingRig=neutral_day_practicals_v1"
R2_POST_TAGS = frozenset(
    {
        "VistaExposureProfile=bounded_histogram",
        R2_RIG_TAG,
        "VistaRole=post_process",
    }
)
R2_REMOVAL_ALLOWLIST = (
    {
        "kind": "practical_light",
        "class_path": "/Script/Engine.SpotLight",
        "semantic_id": "light.entry_hall.01",
    },
    {
        "kind": "practical_light",
        "class_path": "/Script/Engine.RectLight",
        "semantic_id": "light.kitchen_dining.01",
    },
    {
        "kind": "practical_light",
        "class_path": "/Script/Engine.RectLight",
        "semantic_id": "light.living_room.01",
    },
    {
        "kind": "post_process",
        "class_path": "/Script/Engine.PostProcessVolume",
        "required_tags": sorted(R2_POST_TAGS),
    },
)
EXPECTED_ROOM_IDS = frozenset(
    {
        "home.r1/room.entry_hall",
        "home.r1/room.living_room",
        "home.r1/room.kitchen_dining",
        "home.r1/room.bedroom",
        "home.r1/room.office",
        "home.r1/room.bathroom_laundry",
    }
)
ALLOWED_FIXTURE_MESHES = frozenset({"/Engine/BasicShapes/Cylinder.Cylinder"})
ALLOWED_LIGHT_CLASSES = {
    "rect": (unreal.RectLight, "/Script/Engine.RectLight"),
    "spot": (unreal.SpotLight, "/Script/Engine.SpotLight"),
}
EXECUTION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "attempt_root",
        "project",
        "materializer",
        "commandlet",
        "profile",
        "result",
        "engine",
        "map",
        "parent_combined_receipt",
        "source_project_static_tree",
        "source_static_manifest",
        "actor_contract",
        "legal_scope",
        "acknowledgements",
        "claims",
        "acceptance",
        "content_digest",
    }
)
ARTIFACT_KEYS = frozenset({"path", "sha256", "size_bytes"})
MAP_KEYS = frozenset({"object_path", "relative_path", "source_package"})
ACTOR_CONTRACT_KEYS = frozenset(
    {
        "r2_removal_allowlist",
        "visible_actor_role_allowlist",
        "hidden_actor_role_allowlist",
        "pickup_role",
        "pickup_presentation_component",
        "pickup_proxy_component",
        "expected_source_counts",
    }
)
RESULT_GATE_KEYS = frozenset(
    {
        "fixed_map_loaded",
        "source_actor_inventory_exact",
        "exact_r2_removal_allowlist_matched",
        "only_exact_r2_allowlist_destroyed",
        "exact_six_fixture_light_pairs_spawned",
        "restrained_post_process_spawned",
        "visible_presentation_shadow_policy_applied",
        "hidden_collision_proxy_no_shadow_policy_applied",
        "unrelated_actor_identities_preserved",
        "renderer_contract_preserved",
        "map_saved",
        "map_cold_reloaded",
        "r4_actor_inventory_reloaded_exact",
        "shadow_policy_reloaded_exact",
        "only_map_static_artifact_changed",
        "cold_reloaded_map_artifact_sealed",
    }
)


class CommandletFailure(RuntimeError):
    """Raised when the R4 upgrade cannot be proven without widening scope."""


def require(condition, message):
    if not condition:
        raise CommandletFailure(message)


def canonical_json(value):
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
        raise CommandletFailure("value is not finite canonical UTF-8 JSON") from exc


def content_digest(value):
    body = copy.deepcopy(dict(value))
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal(value):
    result = copy.deepcopy(dict(value))
    result["content_digest"] = content_digest(result)
    return result


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite JSON number: " + value)


def strict_json(raw, label):
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except (UnicodeError, ValueError) as exc:
        raise CommandletFailure(label + " is not strict JSON") from exc
    require(type(value) is dict, label + " must be an object")
    return value


def sha256_file(path):
    digest = hashlib.sha256()
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), "pinned artifact is not regular")
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
        require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "pinned artifact changed while hashing",
        )
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def canonical_absolute(value, label):
    require(type(value) is str and value, label + " path is missing")
    path = pathlib.Path(value)
    require(
        path.is_absolute()
        and os.path.normpath(value) == value
        and path.resolve(strict=True) == path,
        label + " path is not canonical",
    )
    return path


def validate_artifact(value, label, *, expected_path=None):
    require(type(value) is dict and set(value) == ARTIFACT_KEYS, label + " pin differs")
    path = canonical_absolute(value["path"], label)
    metadata = os.lstat(path)
    require(
        stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and type(value["sha256"]) is str
        and SHA256_RE.fullmatch(value["sha256"]) is not None
        and type(value["size_bytes"]) is int
        and not isinstance(value["size_bytes"], bool)
        and value["size_bytes"] >= 0
        and metadata.st_size == value["size_bytes"]
        and sha256_file(path) == value["sha256"],
        label + " differs from its pin",
    )
    if expected_path is not None:
        require(path == expected_path, label + " binding differs")
    return path


def static_manifest_tree(manifest):
    require(type(manifest) is dict and manifest, "source static manifest differs")
    digest = hashlib.sha256()
    total_bytes = 0
    for relative, pin in sorted(
        manifest.items(), key=lambda item: item[0].encode("utf-8")
    ):
        pure = pathlib.PurePosixPath(relative)
        require(
            type(relative) is str
            and relative
            and not pure.is_absolute()
            and all(part not in {"", ".", ".."} for part in pure.parts)
            and (relative == PROJECT_NAME or pure.parts[0] in PROJECT_STATIC_ROOTS)
            and type(pin) is dict
            and set(pin) == {"sha256", "size_bytes", "mode"}
            and type(pin["sha256"]) is str
            and SHA256_RE.fullmatch(pin["sha256"]) is not None
            and type(pin["size_bytes"]) is int
            and not isinstance(pin["size_bytes"], bool)
            and pin["size_bytes"] >= 0
            and type(pin["mode"]) is int
            and not isinstance(pin["mode"], bool)
            and pin["mode"] >= 0
            and pin["mode"] <= 0o7777
            and not pin["mode"] & 0o022,
            "source static manifest entry differs",
        )
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(format(pin["mode"], "04o").encode("ascii"))
        digest.update(b"\0")
        digest.update(str(pin["size_bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(pin["sha256"].encode("ascii"))
        digest.update(b"\n")
        total_bytes += pin["size_bytes"]
    return {
        "algorithm": "sha256-path-nul-mode-size-content-v1",
        "file_count": len(manifest),
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }


def static_project_manifest(project):
    root = project.parent
    allowed = {project.name, *PROJECT_STATIC_ROOTS, *MUTABLE_PROJECT_DIRECTORIES}
    require(
        set(os.listdir(root)).issubset(allowed),
        "project root contains an unpinned static entry",
    )
    files = [(project.name, project)]
    for root_name in PROJECT_STATIC_ROOTS:
        static_root = root / root_name
        if not static_root.exists():
            continue
        for current, directories, filenames in os.walk(static_root, followlinks=False):
            current_path = pathlib.Path(current)
            directories.sort()
            filenames.sort()
            current_metadata = os.lstat(current_path)
            require(
                stat.S_ISDIR(current_metadata.st_mode)
                and not stat.S_ISLNK(current_metadata.st_mode)
                and not current_metadata.st_mode & 0o022,
                "project static directory differs",
            )
            for name in directories:
                metadata = os.lstat(current_path / name)
                require(
                    stat.S_ISDIR(metadata.st_mode)
                    and not stat.S_ISLNK(metadata.st_mode)
                    and not metadata.st_mode & 0o022,
                    "project static child directory differs",
                )
            for name in filenames:
                path = current_path / name
                relative = path.relative_to(root).as_posix()
                files.append((relative, path))
    manifest = {}
    for relative, path in sorted(files, key=lambda row: row[0].encode("utf-8")):
        metadata = os.lstat(path)
        require(
            path.resolve(strict=True) == path
            and stat.S_ISREG(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
            and not metadata.st_mode & 0o022,
            "project static file differs",
        )
        manifest[relative] = {
            "sha256": sha256_file(path),
            "size_bytes": metadata.st_size,
            "mode": stat.S_IMODE(metadata.st_mode),
        }
    return manifest


def only_map_changed(before, after):
    require(set(before) == set(after), "project static path inventory changed")
    changed = sorted(key for key in before if before[key] != after[key])
    require(changed == [MAP_RELATIVE_PATH], "static artifact outside map changed")
    require(
        before[MAP_RELATIVE_PATH]["mode"] == after[MAP_RELATIVE_PATH]["mode"]
        and before[MAP_RELATIVE_PATH]["sha256"] != after[MAP_RELATIVE_PATH]["sha256"],
        "map-only mutation contract differs",
    )
    return True


def read_execution():
    execution_value = os.environ.get(EXECUTION_ENV)
    execution_sha = os.environ.get(EXECUTION_SHA_ENV)
    result_value = os.environ.get(RESULT_ENV)
    sidecar_value = os.environ.get(RESULT_SIDECAR_ENV)
    require(
        execution_value is not None
        and execution_sha is not None
        and result_value is not None
        and sidecar_value is not None
        and SHA256_RE.fullmatch(execution_sha) is not None,
        "closed execution environment is absent",
    )
    execution_path = canonical_absolute(execution_value, "execution")
    raw = execution_path.read_bytes()
    require(
        len(raw) <= MAX_DOCUMENT_BYTES
        and hashlib.sha256(raw).hexdigest() == execution_sha,
        "execution bytes differ",
    )
    execution = strict_json(raw, "execution")
    require(
        set(execution) == EXECUTION_KEYS
        and raw == canonical_json(execution)
        and execution.get("content_digest") == content_digest(execution),
        "execution is not a closed canonical document",
    )
    attempt = canonical_absolute(execution["attempt_root"], "attempt root")
    require(
        attempt.is_dir() and execution_path == attempt / EXECUTION_NAME,
        "execution/attempt binding differs",
    )
    validate_execution_contract(execution, attempt)
    result = pathlib.Path(result_value)
    sidecar = pathlib.Path(sidecar_value)
    require(
        result == attempt / RESULT_NAME
        and sidecar == attempt / (RESULT_NAME + ".sha256")
        and execution["result"] == {"path": str(result), "sidecar_path": str(sidecar)}
        and not result.exists()
        and not sidecar.exists(),
        "result binding differs",
    )
    return execution, execution_sha, result, sidecar


def validate_execution_contract(execution, attempt):
    require(
        execution["schema_version"] == EXECUTION_SCHEMA
        and execution["status"] == "authorized_apply_request"
        and execution["legal_scope"] == LEGAL_SCOPE
        and execution["claims"] == CLAIMS
        and execution["acceptance"] == ACCEPTANCE,
        "execution identity or claim boundary differs",
    )
    project = validate_artifact(
        execution["project"],
        "project",
        expected_path=attempt / "project" / PROJECT_NAME,
    )
    validate_artifact(
        execution["materializer"],
        "materializer",
        expected_path=attempt / MATERIALIZER_NAME,
    )
    commandlet = validate_artifact(
        execution["commandlet"],
        "commandlet",
        expected_path=attempt / COMMANDLET_NAME,
    )
    require(
        os.path.realpath(__file__).replace("\\", "/") == str(commandlet),
        "running commandlet differs from execution",
    )
    profile_path = validate_artifact(
        execution["profile"],
        "profile",
        expected_path=attempt / PROFILE_NAME,
    )
    engine = execution["engine"]
    require(
        type(engine) is dict
        and set(engine) == {"version", "unreal_editor_cmd", "build_version", "null_rhi"}
        and engine["version"] == ENGINE_VERSION
        and engine["null_rhi"] is True,
        "engine contract differs",
    )
    validate_artifact(engine["unreal_editor_cmd"], "UnrealEditor-Cmd")
    validate_artifact(engine["build_version"], "Build.version")
    map_contract = execution["map"]
    require(
        type(map_contract) is dict
        and set(map_contract) == MAP_KEYS
        and map_contract["object_path"] == MAP_OBJECT_PATH
        and map_contract["relative_path"] == MAP_RELATIVE_PATH,
        "map contract differs",
    )
    validate_artifact(
        map_contract["source_package"],
        "copied source map",
        expected_path=attempt / "project" / MAP_RELATIVE_PATH,
    )
    require(
        map_contract["source_package"]["sha256"] == SOURCE_MAP_SHA256
        and map_contract["source_package"]["size_bytes"] == SOURCE_MAP_BYTES,
        "copied source map pin differs from sealed R3",
    )
    require(
        project
        == pathlib.Path(unreal.Paths.get_project_file_path()).resolve(strict=True),
        "loaded project differs",
    )
    profile = strict_json(profile_path.read_bytes(), "R4 profile")
    require(
        execution["profile"]["sha256"] == PROFILE_SHA256,
        "R4 source profile SHA differs",
    )
    validate_profile(profile)
    actor_contract = execution["actor_contract"]
    require(
        type(actor_contract) is dict
        and set(actor_contract) == ACTOR_CONTRACT_KEYS
        and actor_contract["r2_removal_allowlist"]
        == copy.deepcopy(list(R2_REMOVAL_ALLOWLIST))
        and actor_contract["visible_actor_role_allowlist"]
        == sorted(VISIBLE_ACTOR_ROLE_ALLOWLIST)
        and actor_contract["hidden_actor_role_allowlist"]
        == sorted(HIDDEN_ACTOR_ROLE_ALLOWLIST)
        and actor_contract["pickup_role"] == PICKUP_ROLE
        and actor_contract["pickup_presentation_component"]
        == PICKUP_PRESENTATION_COMPONENT
        and actor_contract["pickup_proxy_component"] == PICKUP_PROXY_COMPONENT
        and actor_contract["expected_source_counts"] == EXPECTED_SOURCE_COUNTS,
        "actor allowlist contract differs",
    )
    validate_artifact(execution["parent_combined_receipt"], "parent combined receipt")
    require(
        execution["parent_combined_receipt"]["sha256"] == PARENT_RECEIPT_SHA256
        and execution["parent_combined_receipt"]["size_bytes"] == PARENT_RECEIPT_BYTES
        and execution["source_project_static_tree"] == SOURCE_PROJECT_STATIC_TREE,
        "parent combined receipt or source tree differs",
    )
    require(
        static_manifest_tree(execution["source_static_manifest"])
        == execution["source_project_static_tree"],
        "source static manifest/tree cross-binding differs",
    )
    require(
        engine["unreal_editor_cmd"]["sha256"] == UNREAL_EDITOR_CMD_SHA256
        and engine["unreal_editor_cmd"]["size_bytes"] == UNREAL_EDITOR_CMD_BYTES
        and engine["build_version"]["sha256"] == BUILD_VERSION_SHA256
        and engine["build_version"]["size_bytes"] == BUILD_VERSION_BYTES,
        "fixed Unreal toolchain pin differs",
    )
    require(
        execution["acknowledgements"] == ACKNOWLEDGEMENTS,
        "exact legal and large-copy acknowledgements differ",
    )
    require(
        str(unreal.SystemLibrary.get_engine_version()) == ENGINE_VERSION,
        "runtime engine differs",
    )


def validate_profile(profile):
    require(
        profile.get("schema_version") == PROFILE_SCHEMA
        and profile.get("profile_id") == PROFILE_ID
        and profile.get("content_digest") == PROFILE_CONTENT_DIGEST
        and profile.get("renderer_contract") == RENDERER_CONTRACT
        and profile.get("shadow_policy") == SHADOW_POLICY
        and profile.get("claims")
        == {
            "runtime_visual_acceptance": False,
            "gta_quality_accepted": False,
            "runtime_play_proof": "pending",
        }
        and profile.get("content_digest") == content_digest(profile),
        "R4 profile identity differs",
    )
    pairs = profile.get("practical_fixture_light_pairs")
    require(type(pairs) is list and len(pairs) == 6, "R4 pair count differs")
    require(
        {pair.get("room_id") for pair in pairs} == EXPECTED_ROOM_IDS
        and len({pair.get("pair_id") for pair in pairs}) == 6
        and len({pair.get("fixture", {}).get("fixture_id") for pair in pairs}) == 6
        and len({pair.get("light", {}).get("light_id") for pair in pairs}) == 6,
        "R4 pair identities differ",
    )
    for pair in pairs:
        fixture = pair.get("fixture")
        light = pair.get("light")
        require(
            type(fixture) is dict
            and type(light) is dict
            and fixture.get("mesh_object_path") in ALLOWED_FIXTURE_MESHES
            and fixture.get("cast_shadow") is True
            and light.get("type") in ALLOWED_LIGHT_CLASSES
            and light.get("cast_shadow") is True
            and light.get("unit") == "lumens",
            "R4 fixture/light asset allowlist differs",
        )
    require(
        profile.get("post_process")
        == {
            "motion_blur_amount": 0,
            "chromatic_aberration_intensity": 0,
            "film_grain_intensity": 0,
            "bloom_intensity": 0.3,
            "vignette_intensity": 0.1,
            "exposure": {
                "metering_mode": "histogram",
                "min_ev100": 7.5,
                "max_ev100": 11,
                "speed_up": 3,
                "speed_down": 1,
            },
        },
        "R4 post-process contract differs",
    )
    return profile


def sorted_tags(actor):
    return sorted(str(value) for value in actor.get_editor_property("tags"))


def roles(actor):
    return frozenset(
        tag.split("=", 1)[1]
        for tag in sorted_tags(actor)
        if tag.startswith("VistaRole=")
    )


def actor_class_path(actor):
    return str(actor.get_class().get_path_name())


def actor_inventory(actors):
    rows = [
        {
            "actor_path": str(actor.get_path_name()),
            "actor_class_path": actor_class_path(actor),
            "tags": sorted_tags(actor),
        }
        for actor in actors
    ]
    rows.sort(key=lambda row: row["actor_path"])
    require(
        len(rows) == len({row["actor_path"] for row in rows}),
        "actor inventory contains duplicate paths",
    )
    return rows


def find_r2_removal_actors(actors):
    matches = []
    for contract in R2_REMOVAL_ALLOWLIST:
        if contract["kind"] == "practical_light":
            required = {
                R2_RIG_TAG,
                "VistaRole=lighting",
                "VistaVisualRevision=realistic_interior_r2",
                "VistaSemanticId=" + contract["semantic_id"],
            }
            selected = [
                actor
                for actor in actors
                if actor_class_path(actor) == contract["class_path"]
                and required.issubset(sorted_tags(actor))
            ]
        else:
            selected = [
                actor
                for actor in actors
                if actor_class_path(actor) == contract["class_path"]
                and set(contract["required_tags"]).issubset(sorted_tags(actor))
            ]
        require(len(selected) == 1, "R2 removal allowlist match is not exact")
        matches.append(selected[0])
    require(
        len({str(actor.get_path_name()) for actor in matches}) == 4,
        "R2 removal allowlist actor identities overlap",
    )
    return matches


def vector(values):
    return unreal.Vector(x=values[0], y=values[1], z=values[2])


def rotator(values):
    return unreal.Rotator(roll=values[0], pitch=values[1], yaw=values[2])


def set_tags(actor, values):
    actor.set_editor_property("tags", [unreal.Name(value) for value in sorted(values)])


def normalized_number(value):
    number = float(value)
    require(math.isfinite(number), "observed transform is non-finite")
    if abs(number) < 1e-9:
        return 0.0
    return number


def normalized_angle(value):
    number = normalized_number(value)
    wrapped = ((number + 180.0) % 360.0) - 180.0
    return 0.0 if abs(wrapped) < 1e-9 else wrapped


def actor_transform(actor):
    location = actor.get_actor_location()
    rotation_value = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return {
        "location_cm": [
            normalized_number(location.x),
            normalized_number(location.y),
            normalized_number(location.z),
        ],
        "rotation_deg": [
            normalized_angle(rotation_value.roll),
            normalized_angle(rotation_value.pitch),
            normalized_angle(rotation_value.yaw),
        ],
        "scale": [
            normalized_number(scale.x),
            normalized_number(scale.y),
            normalized_number(scale.z),
        ],
    }


def profile_transform(value):
    return {
        "location_cm": [normalized_number(item) for item in value["location_cm"]],
        "rotation_deg": [normalized_angle(item) for item in value["rotation_deg"]],
        "scale": [normalized_number(item) for item in value["scale"]],
    }


def transform_matches(actual, expected):
    return all(
        math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=0.0001)
        for key in ("location_cm", "rotation_deg", "scale")
        for left, right in zip(actual[key], expected[key])
    )


def static_mesh_components(actor):
    return list(actor.get_components_by_class(unreal.StaticMeshComponent))


def light_component(actor):
    values = list(actor.get_components_by_class(unreal.LightComponentBase))
    require(len(values) == 1, "light component inventory differs")
    return values[0]


def component_name(component):
    try:
        return str(component.get_name())
    except Exception:
        return str(component.get_path_name()).rsplit(".", 1)[-1]


def bool_property(value, name, label):
    observed = value.get_editor_property(name)
    require(type(observed) is bool, label + " property is unavailable: " + name)
    return observed


def set_shadow(component, *, cast_shadow, cast_hidden_shadow):
    component.set_cast_shadow(cast_shadow)
    component.set_cast_hidden_shadow(cast_hidden_shadow)
    require(
        bool_property(component, "cast_shadow", "shadow component") is cast_shadow
        and bool_property(component, "cast_hidden_shadow", "shadow component")
        is cast_hidden_shadow,
        "component shadow policy differs after write",
    )


def observe_shadow(actor, component, category):
    return {
        "actor_path": str(actor.get_path_name()),
        "actor_class_path": actor_class_path(actor),
        "component_path": str(component.get_path_name()),
        "component_name": component_name(component),
        "category": category,
        "visible": bool_property(component, "visible", "shadow component"),
        "cast_shadow": bool_property(component, "cast_shadow", "shadow component"),
        "cast_hidden_shadow": bool_property(
            component, "cast_hidden_shadow", "shadow component"
        ),
    }


def apply_shadow_policy(actors):
    observations = []
    counts = {
        "room_actors": 0,
        "room_collision_proxies": 0,
        "hssd_visual_shells": 0,
        "pickup_actors": 0,
        "pickup_presentations": 0,
    }
    for actor in actors:
        actor_roles = roles(actor)
        if "room" in actor_roles:
            counts["room_actors"] += 1
            components = static_mesh_components(actor)
            require(len(components) == 1, "room component inventory differs")
            component = components[0]
            if actor_roles.intersection(HIDDEN_ACTOR_ROLE_ALLOWLIST):
                counts["room_collision_proxies"] += 1
                set_shadow(component, cast_shadow=False, cast_hidden_shadow=False)
                observations.append(
                    observe_shadow(actor, component, "room_proxy_hidden")
                )
            else:
                require(
                    actor_roles.intersection(VISIBLE_ACTOR_ROLE_ALLOWLIST),
                    "visible room is outside shadow allowlist",
                )
                set_shadow(component, cast_shadow=True, cast_hidden_shadow=False)
                observations.append(observe_shadow(actor, component, "room_visible"))
        if "hssd_visual_shell" in actor_roles:
            counts["hssd_visual_shells"] += 1
            components = static_mesh_components(actor)
            require(len(components) == 1, "HSSD shell component inventory differs")
            component = components[0]
            require(
                bool_property(component, "visible", "HSSD shell") is True,
                "HSSD shell is not an intended visible presentation",
            )
            set_shadow(component, cast_shadow=True, cast_hidden_shadow=False)
            observations.append(observe_shadow(actor, component, "hssd_visible"))
        if PICKUP_ROLE in actor_roles:
            counts["pickup_actors"] += 1
            for component in static_mesh_components(actor):
                name = component_name(component)
                if name == PICKUP_PRESENTATION_COMPONENT:
                    counts["pickup_presentations"] += 1
                    require(
                        bool_property(component, "visible", "pickup presentation")
                        is True,
                        "pickup presentation is not visible",
                    )
                    set_shadow(component, cast_shadow=True, cast_hidden_shadow=False)
                    observations.append(
                        observe_shadow(actor, component, "pickup_presentation_visible")
                    )
                elif name == PICKUP_PROXY_COMPONENT and not bool_property(
                    component, "visible", "pickup proxy"
                ):
                    set_shadow(component, cast_shadow=False, cast_hidden_shadow=False)
                    observations.append(
                        observe_shadow(actor, component, "pickup_proxy_hidden")
                    )
    require(
        counts == {key: EXPECTED_SOURCE_COUNTS[key] for key in counts},
        "shadow actor counts differ",
    )
    observations.sort(key=lambda row: (row["actor_path"], row["component_path"]))
    require(
        observations
        and len(observations) == len({row["component_path"] for row in observations}),
        "shadow observation inventory overlaps",
    )
    return observations


def spawn_pairs(actor_subsystem, profile):
    rig_tag = "VistaLightingRig=" + PROFILE_ID
    for pair in sorted(
        profile["practical_fixture_light_pairs"], key=lambda row: row["pair_id"]
    ):
        fixture_spec = pair["fixture"]
        light_spec = pair["light"]
        mesh = unreal.load_asset(fixture_spec["mesh_object_path"])
        require(
            isinstance(mesh, unreal.StaticMesh), "allowlisted fixture mesh unavailable"
        )
        fixture = actor_subsystem.spawn_actor_from_class(
            unreal.StaticMeshActor,
            vector(fixture_spec["location_cm"]),
            rotator(fixture_spec["rotation_deg"]),
            transient=False,
        )
        require(fixture is not None, "R4 fixture spawn failed")
        fixture.set_actor_scale3d(vector(fixture_spec["scale"]))
        fixture.set_actor_label(
            "VISTA_R4_" + fixture_spec["fixture_id"].replace(".", "_")
        )
        set_tags(
            fixture,
            [
                "VistaRole=practical_fixture",
                "VistaRoom=" + pair["room_id"],
                "VistaR4Pair=" + pair["pair_id"],
                "VistaFixtureId=" + fixture_spec["fixture_id"],
                rig_tag,
            ],
        )
        components = static_mesh_components(fixture)
        require(len(components) == 1, "R4 fixture component inventory differs")
        fixture_component = components[0]
        fixture_component.set_static_mesh(mesh)
        fixture_component.set_collision_profile_name(unreal.Name("NoCollision"))
        fixture_component.set_simulate_physics(False)
        fixture_component.set_editor_property("generate_overlap_events", False)
        fixture_component.set_mobility(unreal.ComponentMobility.STATIC)
        set_shadow(fixture_component, cast_shadow=True, cast_hidden_shadow=False)

        light_class, expected_class = ALLOWED_LIGHT_CLASSES[light_spec["type"]]
        light = actor_subsystem.spawn_actor_from_class(
            light_class,
            vector(light_spec["location_cm"]),
            rotator(light_spec["rotation_deg"]),
            transient=False,
        )
        require(light is not None, "R4 practical light spawn failed")
        light.set_actor_scale3d(vector(light_spec["scale"]))
        light.set_actor_label("VISTA_R4_" + light_spec["light_id"].replace(".", "_"))
        set_tags(
            light,
            [
                "VistaRole=lighting",
                "VistaRoom=" + pair["room_id"],
                "VistaR4Pair=" + pair["pair_id"],
                "VistaPracticalLightId=" + light_spec["light_id"],
                "VistaFixtureId=" + fixture_spec["fixture_id"],
                rig_tag,
            ],
        )
        component = light_component(light)
        component.set_mobility(unreal.ComponentMobility.MOVABLE)
        component.set_editor_property("intensity", light_spec["intensity"])
        component.set_editor_property("use_temperature", True)
        component.set_editor_property("temperature", light_spec["temperature_k"])
        component.set_editor_property(
            "attenuation_radius", light_spec["attenuation_radius_cm"]
        )
        component.set_editor_property("cast_shadows", True)
        component.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
        require(
            actor_class_path(light) == expected_class,
            "spawned R4 light class differs",
        )
    return observe_pairs(list(actor_subsystem.get_all_level_actors()), profile)


def observe_pairs(actors, profile):
    observations = []
    expected_units = {"lumens": unreal.LightUnits.LUMENS}
    for pair in sorted(
        profile["practical_fixture_light_pairs"], key=lambda row: row["pair_id"]
    ):
        pair_tag = "VistaR4Pair=" + pair["pair_id"]
        fixture_tag = "VistaFixtureId=" + pair["fixture"]["fixture_id"]
        light_tag = "VistaPracticalLightId=" + pair["light"]["light_id"]
        fixtures = [
            actor
            for actor in actors
            if actor_class_path(actor) == "/Script/Engine.StaticMeshActor"
            and pair_tag in sorted_tags(actor)
            and fixture_tag in sorted_tags(actor)
            and "VistaRole=practical_fixture" in sorted_tags(actor)
        ]
        lights = [
            actor
            for actor in actors
            if pair_tag in sorted_tags(actor)
            and light_tag in sorted_tags(actor)
            and "VistaRole=lighting" in sorted_tags(actor)
        ]
        require(len(fixtures) == 1 and len(lights) == 1, "R4 pair lookup differs")
        fixture = fixtures[0]
        light = lights[0]
        fixture_components = static_mesh_components(fixture)
        require(len(fixture_components) == 1, "R4 fixture component differs")
        fixture_component = fixture_components[0]
        mesh = fixture_component.get_editor_property("static_mesh")
        component = light_component(light)
        light_spec = pair["light"]
        fixture_spec = pair["fixture"]
        observation = {
            "pair_id": pair["pair_id"],
            "room_id": pair["room_id"],
            "fixture_actor_path": str(fixture.get_path_name()),
            "fixture_class_path": actor_class_path(fixture),
            "fixture_mesh_object_path": str(mesh.get_path_name()) if mesh else None,
            "fixture_transform": actor_transform(fixture),
            "fixture_visible": bool_property(fixture_component, "visible", "fixture"),
            "fixture_cast_shadow": bool_property(
                fixture_component, "cast_shadow", "fixture"
            ),
            "fixture_cast_hidden_shadow": bool_property(
                fixture_component, "cast_hidden_shadow", "fixture"
            ),
            "fixture_collision_profile": str(
                fixture_component.get_collision_profile_name()
            ),
            "light_actor_path": str(light.get_path_name()),
            "light_class_path": actor_class_path(light),
            "light_transform": actor_transform(light),
            "light_intensity": normalized_number(
                component.get_editor_property("intensity")
            ),
            "light_temperature_k": normalized_number(
                component.get_editor_property("temperature")
            ),
            "light_attenuation_radius_cm": normalized_number(
                component.get_editor_property("attenuation_radius")
            ),
            "light_use_temperature": bool_property(
                component, "use_temperature", "light"
            ),
            "light_cast_shadow": bool_property(component, "cast_shadows", "light"),
            "light_intensity_units": (
                "lumens"
                if component.get_editor_property("intensity_units")
                == unreal.LightUnits.LUMENS
                else "unsupported"
            ),
        }
        require(
            isinstance(mesh, unreal.StaticMesh)
            and observation["fixture_mesh_object_path"]
            == fixture_spec["mesh_object_path"]
            and transform_matches(
                observation["fixture_transform"], profile_transform(fixture_spec)
            )
            and observation["fixture_visible"] is True
            and observation["fixture_cast_shadow"] is True
            and observation["fixture_cast_hidden_shadow"] is False
            and observation["fixture_collision_profile"] == "NoCollision"
            and observation["light_class_path"]
            == ALLOWED_LIGHT_CLASSES[light_spec["type"]][1]
            and transform_matches(
                observation["light_transform"], profile_transform(light_spec)
            )
            and math.isclose(
                observation["light_intensity"],
                float(light_spec["intensity"]),
                rel_tol=0.0,
                abs_tol=0.0001,
            )
            and math.isclose(
                observation["light_temperature_k"],
                float(light_spec["temperature_k"]),
                rel_tol=0.0,
                abs_tol=0.0001,
            )
            and math.isclose(
                observation["light_attenuation_radius_cm"],
                float(light_spec["attenuation_radius_cm"]),
                rel_tol=0.0,
                abs_tol=0.0001,
            )
            and observation["light_use_temperature"] is True
            and observation["light_cast_shadow"] is True
            and component.get_editor_property("intensity_units")
            == expected_units[light_spec["unit"]],
            "R4 pair observation differs from profile",
        )
        observations.append(observation)
    require(
        len(observations) == 6
        and len({row["fixture_actor_path"] for row in observations}) == 6
        and len({row["light_actor_path"] for row in observations}) == 6,
        "R4 pair observation count differs",
    )
    return observations


def spawn_post_process(actor_subsystem, profile):
    post = actor_subsystem.spawn_actor_from_class(
        unreal.PostProcessVolume, unreal.Vector(), unreal.Rotator(), transient=False
    )
    require(post is not None, "R4 post process spawn failed")
    post.set_actor_label("VISTA_R4_PostProcess")
    set_tags(
        post,
        [
            "VistaRole=post_process",
            "VistaLightingRig=" + PROFILE_ID,
            "VistaExposureProfile=bounded_histogram",
            "VistaRealismProfile=" + PROFILE_ID,
        ],
    )
    post.set_editor_property("unbound", True)
    post.set_editor_property("priority", 100.0)
    post.set_editor_property("blend_weight", 1.0)
    settings = post.get_editor_property("settings")
    post_profile = profile["post_process"]
    exposure = post_profile["exposure"]
    properties = {
        "override_auto_exposure_method": True,
        "auto_exposure_method": unreal.AutoExposureMethod.AEM_HISTOGRAM,
        "override_auto_exposure_min_brightness": True,
        "auto_exposure_min_brightness": exposure["min_ev100"],
        "override_auto_exposure_max_brightness": True,
        "auto_exposure_max_brightness": exposure["max_ev100"],
        "override_auto_exposure_speed_up": True,
        "auto_exposure_speed_up": exposure["speed_up"],
        "override_auto_exposure_speed_down": True,
        "auto_exposure_speed_down": exposure["speed_down"],
        "override_motion_blur_amount": True,
        "motion_blur_amount": post_profile["motion_blur_amount"],
        "override_scene_fringe_intensity": True,
        "scene_fringe_intensity": post_profile["chromatic_aberration_intensity"],
        "override_grain_intensity": True,
        "grain_intensity": post_profile["film_grain_intensity"],
        "override_bloom_intensity": True,
        "bloom_intensity": post_profile["bloom_intensity"],
        "override_vignette_intensity": True,
        "vignette_intensity": post_profile["vignette_intensity"],
    }
    for name, value in properties.items():
        settings.set_editor_property(name, value)
    post.set_editor_property("settings", settings)
    return observe_post_process(post, profile)


def observe_post_process(post, profile):
    require(
        actor_class_path(post) == "/Script/Engine.PostProcessVolume"
        and "VistaLightingRig=" + PROFILE_ID in sorted_tags(post)
        and "VistaRole=post_process" in sorted_tags(post),
        "R4 post-process identity differs",
    )
    settings = post.get_editor_property("settings")
    post_profile = profile["post_process"]
    exposure = post_profile["exposure"]
    override_names = (
        "override_auto_exposure_method",
        "override_auto_exposure_min_brightness",
        "override_auto_exposure_max_brightness",
        "override_auto_exposure_speed_up",
        "override_auto_exposure_speed_down",
        "override_motion_blur_amount",
        "override_scene_fringe_intensity",
        "override_grain_intensity",
        "override_bloom_intensity",
        "override_vignette_intensity",
    )
    observed = {
        "actor_path": str(post.get_path_name()),
        "class_path": actor_class_path(post),
        "tags": sorted_tags(post),
        "unbound": bool_property(post, "unbound", "post process"),
        "priority": float(post.get_editor_property("priority")),
        "blend_weight": float(post.get_editor_property("blend_weight")),
        "motion_blur_amount": normalized_number(
            settings.get_editor_property("motion_blur_amount")
        ),
        "chromatic_aberration_intensity": normalized_number(
            settings.get_editor_property("scene_fringe_intensity")
        ),
        "film_grain_intensity": normalized_number(
            settings.get_editor_property("grain_intensity")
        ),
        "bloom_intensity": normalized_number(
            settings.get_editor_property("bloom_intensity")
        ),
        "vignette_intensity": normalized_number(
            settings.get_editor_property("vignette_intensity")
        ),
        "auto_exposure_method_histogram": (
            settings.get_editor_property("auto_exposure_method")
            == unreal.AutoExposureMethod.AEM_HISTOGRAM
        ),
        "override_flags": {
            name: bool_property(settings, name, "R4 post process")
            for name in override_names
        },
        "exposure": {
            "min_ev100": normalized_number(
                settings.get_editor_property("auto_exposure_min_brightness")
            ),
            "max_ev100": normalized_number(
                settings.get_editor_property("auto_exposure_max_brightness")
            ),
            "speed_up": normalized_number(
                settings.get_editor_property("auto_exposure_speed_up")
            ),
            "speed_down": normalized_number(
                settings.get_editor_property("auto_exposure_speed_down")
            ),
        },
    }
    require(
        observed["unbound"] is True
        and observed["auto_exposure_method_histogram"] is True
        and set(observed["override_flags"]) == set(override_names)
        and all(value is True for value in observed["override_flags"].values())
        and math.isclose(observed["priority"], 100.0, rel_tol=0.0, abs_tol=1e-6)
        and math.isclose(observed["blend_weight"], 1.0, rel_tol=0.0, abs_tol=1e-6)
        and all(
            math.isclose(
                observed[key], float(post_profile[key]), rel_tol=0.0, abs_tol=1e-6
            )
            for key in (
                "motion_blur_amount",
                "chromatic_aberration_intensity",
                "film_grain_intensity",
                "bloom_intensity",
                "vignette_intensity",
            )
        )
        and all(
            math.isclose(
                observed["exposure"][key],
                float(exposure[key]),
                rel_tol=0.0,
                abs_tol=1e-6,
            )
            for key in ("min_ev100", "max_ev100", "speed_up", "speed_down")
        ),
        "R4 post-process observation differs",
    )
    return observed


def r4_actor_inventory(actors):
    rig_tag = "VistaLightingRig=" + PROFILE_ID
    rows = [
        row
        for row in actor_inventory(actors)
        if rig_tag in row["tags"]
        and (
            "VistaRole=practical_fixture" in row["tags"]
            or "VistaRole=lighting" in row["tags"]
            or "VistaRole=post_process" in row["tags"]
        )
    ]
    require(len(rows) == 13, "R4 actor inventory is not six pairs plus post process")
    return rows


def shadow_observations(actors):
    rows = []
    for actor in actors:
        actor_roles = roles(actor)
        if (
            "room" in actor_roles
            or "hssd_visual_shell" in actor_roles
            or PICKUP_ROLE in actor_roles
        ):
            for component in static_mesh_components(actor):
                name = component_name(component)
                category = None
                if "room_collision_proxy" in actor_roles:
                    category = "room_proxy_hidden"
                elif "room" in actor_roles:
                    category = "room_visible"
                elif "hssd_visual_shell" in actor_roles:
                    category = "hssd_visible"
                elif name == PICKUP_PRESENTATION_COMPONENT:
                    category = "pickup_presentation_visible"
                elif name == PICKUP_PROXY_COMPONENT and not bool_property(
                    component, "visible", "pickup proxy"
                ):
                    category = "pickup_proxy_hidden"
                if category is not None:
                    rows.append(observe_shadow(actor, component, category))
    rows.sort(key=lambda row: (row["actor_path"], row["component_path"]))
    return rows


def shadow_rows_valid(rows):
    require(rows, "shadow observation inventory is empty")
    for row in rows:
        hidden = row["category"] in {"room_proxy_hidden", "pickup_proxy_hidden"}
        require(
            row["visible"] is (not hidden)
            and row["cast_shadow"] is (not hidden)
            and row["cast_hidden_shadow"] is False,
            "reloaded shadow observation differs",
        )
    return True


def renderer_observation(world):
    settings = world.get_world_settings()
    force_dynamic = bool(settings.get_editor_property("force_no_precomputed_lighting"))
    require(force_dynamic, "world lost dynamic-lighting policy")
    return {
        "contract": copy.deepcopy(RENDERER_CONTRACT),
        "force_no_precomputed_lighting": force_dynamic,
        "configuration_mutation_requested": False,
        "null_rhi_visual_proof": False,
    }


def pair_identity_rows(rows):
    return [
        {
            "pair_id": row["pair_id"],
            "fixture_actor_path": row["fixture_actor_path"],
            "light_actor_path": row["light_actor_path"],
        }
        for row in rows
    ]


def write_exclusive(path, raw):
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            require(written > 0, "exclusive result write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_result(path, sidecar, result):
    raw = canonical_json(result)
    digest = hashlib.sha256(raw).hexdigest()
    write_exclusive(path, raw)
    write_exclusive(sidecar, f"{digest}  {RESULT_NAME}\n".encode("ascii"))
    unreal.log(
        RESULT_MARKER
        + json.dumps({"path": str(path), "sha256": digest}, sort_keys=True)
    )


def run():
    execution, execution_sha, result_path, sidecar_path = read_execution()
    profile_path = pathlib.Path(execution["profile"]["path"])
    profile = validate_profile(strict_json(profile_path.read_bytes(), "R4 profile"))
    gates = {key: False for key in RESULT_GATE_KEYS}
    inventory_before = []
    inventory_reloaded = []
    removed_paths = []
    r4_pairs_before_save = []
    r4_pairs_reloaded = []
    post_process_before_save = None
    post_process_reloaded = None
    shadows_before_save = []
    shadows_reloaded = []
    renderer = None
    map_package = None
    error = None
    try:
        source_static_manifest = static_project_manifest(
            pathlib.Path(execution["project"]["path"])
        )
        require(
            source_static_manifest == execution["source_static_manifest"],
            "copied source project differs before map mutation",
        )
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        require(level_subsystem.load_level(MAP_OBJECT_PATH), "fixed map failed to load")
        gates["fixed_map_loaded"] = True
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "fixed map world is unavailable")
        actors = list(actor_subsystem.get_all_level_actors())
        inventory_before = actor_inventory(actors)
        require(
            not any(
                "VistaLightingRig=" + PROFILE_ID in sorted_tags(actor)
                or any(tag.startswith("VistaR4Pair=") for tag in sorted_tags(actor))
                or "VistaRole=practical_fixture" in sorted_tags(actor)
                for actor in actors
            ),
            "source map already contains R4 actor identities",
        )
        source_counts = {
            "actors": len(actors),
            "room_actors": sum("room" in roles(actor) for actor in actors),
            "room_collision_proxies": sum(
                "room_collision_proxy" in roles(actor) for actor in actors
            ),
            "hssd_visual_shells": sum(
                "hssd_visual_shell" in roles(actor) for actor in actors
            ),
            "pickup_actors": sum(PICKUP_ROLE in roles(actor) for actor in actors),
            "pickup_presentations": sum(
                component_name(component) == PICKUP_PRESENTATION_COMPONENT
                for actor in actors
                if PICKUP_ROLE in roles(actor)
                for component in static_mesh_components(actor)
            ),
        }
        require(
            source_counts == EXPECTED_SOURCE_COUNTS, "source actor inventory differs"
        )
        gates["source_actor_inventory_exact"] = True

        removal = find_r2_removal_actors(actors)
        gates["exact_r2_removal_allowlist_matched"] = True
        removed_paths = sorted(str(actor.get_path_name()) for actor in removal)
        unrelated_before = [
            row for row in inventory_before if row["actor_path"] not in removed_paths
        ]
        for actor in removal:
            require(
                actor_subsystem.destroy_actor(actor),
                "R2 allowlist actor destroy failed",
            )
        after_destroy = list(actor_subsystem.get_all_level_actors())
        require(
            actor_inventory(after_destroy) == unrelated_before,
            "actor outside R2 removal allowlist changed",
        )
        gates["only_exact_r2_allowlist_destroyed"] = True

        shadows_before_save = apply_shadow_policy(after_destroy)
        gates["visible_presentation_shadow_policy_applied"] = shadow_rows_valid(
            shadows_before_save
        )
        gates["hidden_collision_proxy_no_shadow_policy_applied"] = True
        r4_pairs_before_save = spawn_pairs(actor_subsystem, profile)
        gates["exact_six_fixture_light_pairs_spawned"] = len(r4_pairs_before_save) == 6
        post_process_before_save = spawn_post_process(actor_subsystem, profile)
        gates["restrained_post_process_spawned"] = True
        renderer = renderer_observation(world)
        gates["renderer_contract_preserved"] = True

        require(
            unreal.EditorLoadingAndSavingUtils.save_map(world, MAP_OBJECT_PATH),
            "R4 map save failed",
        )
        gates["map_saved"] = True
        require(
            level_subsystem.load_level(MAP_OBJECT_PATH), "R4 map cold reload failed"
        )
        gates["map_cold_reloaded"] = True
        reloaded_world = unreal.EditorLevelLibrary.get_editor_world()
        require(reloaded_world is not None, "cold-reloaded world unavailable")
        reloaded_actors = list(actor_subsystem.get_all_level_actors())
        inventory_reloaded = actor_inventory(reloaded_actors)
        r4_inventory = r4_actor_inventory(reloaded_actors)
        r4_pairs_reloaded = observe_pairs(reloaded_actors, profile)
        post_matches = [
            actor
            for actor in reloaded_actors
            if actor_class_path(actor) == "/Script/Engine.PostProcessVolume"
            and "VistaLightingRig=" + PROFILE_ID in sorted_tags(actor)
            and "VistaRole=post_process" in sorted_tags(actor)
        ]
        require(len(post_matches) == 1, "reloaded R4 post process is not exact")
        post_process_reloaded = observe_post_process(post_matches[0], profile)
        gates["r4_actor_inventory_reloaded_exact"] = (
            len(r4_inventory) == 13
            and pair_identity_rows(r4_pairs_reloaded)
            == pair_identity_rows(r4_pairs_before_save)
            and post_process_reloaded["actor_path"]
            == post_process_before_save["actor_path"]
        )
        reloaded_unrelated = [
            row
            for row in inventory_reloaded
            if "VistaLightingRig=" + PROFILE_ID not in row["tags"]
        ]
        gates["unrelated_actor_identities_preserved"] = (
            reloaded_unrelated == unrelated_before
        )
        require(
            gates["unrelated_actor_identities_preserved"],
            "unrelated actor identity changed after reload",
        )
        shadows_reloaded = shadow_observations(reloaded_actors)
        gates["shadow_policy_reloaded_exact"] = shadow_rows_valid(
            shadows_reloaded
        ) and len(shadows_reloaded) == len(shadows_before_save)
        renderer = renderer_observation(reloaded_world)
        map_path = pathlib.Path(execution["project"]["path"]).parent / MAP_RELATIVE_PATH
        metadata = os.lstat(map_path)
        require(
            map_path.resolve(strict=True) == map_path
            and stat.S_ISREG(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode),
            "cold-reloaded map is not a canonical regular file",
        )
        map_package = {
            "path": str(map_path),
            "sha256": sha256_file(map_path),
            "size_bytes": metadata.st_size,
        }
        output_static_manifest = static_project_manifest(
            pathlib.Path(execution["project"]["path"])
        )
        gates["only_map_static_artifact_changed"] = only_map_changed(
            source_static_manifest, output_static_manifest
        )
        gates["cold_reloaded_map_artifact_sealed"] = True
        require(all(gates.values()), "terminal R4 gate inventory is incomplete")
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)[:512]}

    succeeded = error is None and all(gates.values())
    result = seal(
        {
            "schema_version": RESULT_SCHEMA,
            "status": RESULT_STATUS if succeeded else FAILURE_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution_sha256": execution_sha,
            "profile": copy.deepcopy(execution["profile"]),
            "map_object_path": MAP_OBJECT_PATH,
            "map_package": map_package,
            "actor_inventory_before": inventory_before,
            "actor_inventory_reloaded": inventory_reloaded,
            "removed_r2_actor_paths": removed_paths,
            "r4_pair_observations_before_save": r4_pairs_before_save,
            "r4_pair_observations_reloaded": r4_pairs_reloaded,
            "post_process_observation_before_save": post_process_before_save,
            "post_process_observation_reloaded": post_process_reloaded,
            "shadow_observations_before_save": shadows_before_save,
            "shadow_observations_reloaded": shadows_reloaded,
            "renderer_observation": renderer,
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
            "gates": gates,
            "error": error,
        }
    )
    publish_result(result_path, sidecar_path, result)
    require(succeeded, "combined R4 commandlet failed")


if __name__ == "__main__":
    run()
