"""Apply the sealed R6 phone/cup presentation-only accessory upgrade.

The script operates only on an append-only copied project.  It uses text
metadata and Unreal reflection; it never renders, captures, or analyzes City
Sample pixels.  PickupMesh and the pickup actor remain the physical,
interaction, replication, attachment, and transform authority.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import re
import stat

import unreal


EXECUTION_SCHEMA = "simworld.vista.human-visual-demo-accessory-r6-execution/v1"
RESULT_SCHEMA = "simworld.vista.human-visual-demo-accessory-r6-result/v1"
RESULT_STATUS = "accessory_r6_map_saved_cold_reloaded"
FAILURE_STATUS = "accessory_r6_commandlet_failed"
PROVIDER_ID = "citysample_crowd_visual_demo_v1"
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
PROJECT_NAME = "VistaPlayableHome.uproject"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
MAP_RELATIVE_PATH = (
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
MATERIALIZER_NAME = "materialize_accessory_r6.py"
COMMANDLET_NAME = "compose_accessory_r6_commandlet.py"
R4_SUPPORT_NAME = "r4-commandlet-support.py"
EXECUTION_NAME = "accessory-r6-execution.json"
RESULT_NAME = "accessory-r6-result.json"
EXECUTION_ENV = "VISTA_ACCESSORY_R6_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_ACCESSORY_R6_EXECUTION_SHA256"
RESULT_ENV = "VISTA_ACCESSORY_R6_RESULT"
RESULT_SIDECAR_ENV = "VISTA_ACCESSORY_R6_RESULT_SIDECAR"
RESULT_MARKER = "VISTA_ACCESSORY_R6_RESULT:"
FIT_POLICY = "uniform_contain_existing_visual_envelope_v1"
PICKUP_CLASS_PATH = "/Script/VistaPlayableHome.VistaPickupActor"
POT_SEMANTIC_ID = "home.r1/room.kitchen_dining/entity.pot.01"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
ARTIFACT_KEYS = {"path", "sha256", "size_bytes"}
EXECUTION_KEYS = {
    "schema_version",
    "status",
    "attempt_root",
    "project",
    "materializer",
    "commandlet",
    "r4_commandlet_support",
    "result",
    "engine",
    "map",
    "parent_combined_receipt",
    "source_project_static_tree",
    "source_static_manifest",
    "asset_inventory",
    "accessory_contract",
    "legal_scope",
    "acknowledgements",
    "claims",
    "acceptance",
    "content_digest",
}
RESULT_GATE_KEYS = {
    "fixed_map_loaded",
    "source_actor_inventory_exact",
    "exact_two_targets_found",
    "exact_static_mesh_assets_loaded",
    "asset_registry_type_and_provenance_exact",
    "deterministic_reflection_fit_computed",
    "only_target_presentations_mutated",
    "semantic_actor_authority_preserved",
    "pickup_collision_proxy_preserved",
    "pot_presentation_preserved",
    "map_saved",
    "map_cold_reloaded",
    "actor_inventory_reloaded_exact",
    "target_presentations_reloaded_exact",
    "only_map_static_artifact_changed",
    "cold_reloaded_map_artifact_sealed",
}
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
ACCEPTANCE = {"human_visual_acceptance": "pending", "runtime_play_proof": "pending"}
ACKNOWLEDGEMENTS = {
    "private_noncommercial_research": (
        "I acknowledge City Sample use is restricted to private noncommercial research."
    ),
    "epic_ue_only_content_entitlement": (
        "I confirm my Epic entitlement and UE-only use of City Sample content."
    ),
    "no_redistribution": (
        "I acknowledge source UAssets and external asset payloads may not be redistributed."
    ),
    "external_assets_outside_git": (
        "I acknowledge every external asset payload remains outside Git."
    ),
    "human_visual_demo_only": (
        "I acknowledge these accessories are for a human-operated visual demo only."
    ),
    "excluded_from_vista_and_ai": (
        "I acknowledge this output is excluded from VISTA datasets/databases and AI/VLM training, testing, evaluation, or review."
    ),
    "sealed_r4_large_copy": (
        "I authorize an isolated 9.15 GiB reflink or copy of the sealed R4-C project."
    ),
}
TARGETS = [
    {
        "semantic_id": "home.r1/room.bedroom/entity.phone.01",
        "actor_path": (
            "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
            "VistaPlayableHome.VistaPlayableHome:PersistentLevel.VistaPickupActor_2"
        ),
        "source_mesh_object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            "HSSDPrivateResearch/Assets/hssd_static_phone/"
            "hssd_static_phone.hssd_static_phone"
        ),
        "asset": {
            "asset_class": "StaticMesh",
            "object_path": "/Game/CitySampleCrowd/Character/Accessories/phoneA.phoneA",
            "package_name": "/Game/CitySampleCrowd/Character/Accessories/phoneA",
        },
        "uasset": {
            "relative_path": "Content/CitySampleCrowd/Character/Accessories/phoneA.uasset",
            "sha256": "02b6cb33727624293fbfd206f32d562972a60554f36d91657a2389b0359b09da",
            "size_bytes": 76212,
            "mode": 0o600,
        },
        "fit_policy": FIT_POLICY,
    },
    {
        "semantic_id": "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        "actor_path": (
            "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
            "VistaPlayableHome.VistaPlayableHome:PersistentLevel.VistaPickupActor_3"
        ),
        "source_mesh_object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            "HSSDPrivateResearch/Assets/hssd_static_coffee_cup/"
            "hssd_static_coffee_cup.hssd_static_coffee_cup"
        ),
        "asset": {
            "asset_class": "StaticMesh",
            "object_path": "/Game/CitySampleCrowd/Character/Accessories/cupA.cupA",
            "package_name": "/Game/CitySampleCrowd/Character/Accessories/cupA",
        },
        "uasset": {
            "relative_path": "Content/CitySampleCrowd/Character/Accessories/cupA.uasset",
            "sha256": "ffc9b7b8d9468832f3c9e28825a522f5a3a3f1e6faf3e4ef4f87e9f505b4854e",
            "size_bytes": 250764,
            "mode": 0o600,
        },
        "fit_policy": FIT_POLICY,
    },
]
TARGETS.sort(key=lambda row: row["semantic_id"])


class CommandletFailure(RuntimeError):
    """Raised whenever the closed R6 proof cannot be completed."""


def require(condition, message):
    if not condition:
        raise CommandletFailure(message)


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON duplicate key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite JSON constant: " + value)


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
        raise CommandletFailure("value is not finite canonical JSON") from exc


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


def content_digest(value):
    body = copy.deepcopy(value)
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal(value):
    result = copy.deepcopy(value)
    result["content_digest"] = content_digest(result)
    return result


def sha256_file(path):
    digest = hashlib.sha256()
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
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


def validate_artifact(value, label, expected_path=None):
    require(type(value) is dict and set(value) == ARTIFACT_KEYS, label + " pin differs")
    path = canonical_absolute(value["path"], label)
    metadata = os.lstat(path)
    require(
        stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and type(value["sha256"]) is str
        and SHA256_RE.fullmatch(value["sha256"])
        and type(value["size_bytes"]) is int
        and not isinstance(value["size_bytes"], bool)
        and value["size_bytes"] >= 0
        and metadata.st_size == value["size_bytes"]
        and sha256_file(path) == value["sha256"],
        label + " differs from its pin",
    )
    if expected_path is not None:
        require(path == expected_path, label + " path binding differs")
    return path


def load_support(path):
    spec = importlib.util.spec_from_file_location("vista_r6_r4_support", path)
    require(
        spec is not None and spec.loader is not None, "R4 support loader unavailable"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_execution():
    execution_value = os.environ.get(EXECUTION_ENV)
    execution_sha = os.environ.get(EXECUTION_SHA_ENV)
    result_value = os.environ.get(RESULT_ENV)
    sidecar_value = os.environ.get(RESULT_SIDECAR_ENV)
    require(
        execution_value
        and execution_sha
        and result_value
        and sidecar_value
        and SHA256_RE.fullmatch(execution_sha),
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
        and execution.get("content_digest") == content_digest(execution)
        and execution.get("schema_version") == EXECUTION_SCHEMA
        and execution.get("status") == "authorized_apply_request"
        and execution.get("legal_scope") == LEGAL_SCOPE
        and execution.get("acknowledgements") == ACKNOWLEDGEMENTS
        and execution.get("claims") == CLAIMS
        and execution.get("acceptance") == ACCEPTANCE,
        "execution identity or closed contract differs",
    )
    attempt = canonical_absolute(execution["attempt_root"], "attempt root")
    require(
        execution_path == attempt / EXECUTION_NAME, "execution/attempt binding differs"
    )
    project = validate_artifact(
        execution["project"], "project", attempt / "project" / PROJECT_NAME
    )
    validate_artifact(
        execution["materializer"], "materializer", attempt / MATERIALIZER_NAME
    )
    commandlet = validate_artifact(
        execution["commandlet"], "commandlet", attempt / COMMANDLET_NAME
    )
    require(
        pathlib.Path(__file__).resolve(strict=True) == commandlet,
        "running commandlet differs",
    )
    support_path = validate_artifact(
        execution["r4_commandlet_support"],
        "R4 commandlet support",
        attempt / R4_SUPPORT_NAME,
    )
    engine = execution["engine"]
    require(
        type(engine) is dict
        and set(engine)
        == {
            "version",
            "unreal_editor_cmd",
            "build_version",
            "network_namespace",
            "null_rhi",
        }
        and engine["version"] == ENGINE_VERSION
        and engine["null_rhi"] is True,
        "engine contract differs",
    )
    validate_artifact(engine["unreal_editor_cmd"], "UnrealEditor-Cmd")
    validate_artifact(engine["build_version"], "Build.version")
    network_namespace = validate_artifact(
        engine["network_namespace"], "private network namespace wrapper"
    )
    require(
        network_namespace == pathlib.Path("/usr/bin/bwrap")
        and os.stat(network_namespace, follow_symlinks=False).st_mode & 0o111
        and engine["network_namespace"]
        == {
            "path": "/usr/bin/bwrap",
            "sha256": "d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca",
            "size_bytes": 72160,
        },
        "private network namespace toolchain differs",
    )
    map_contract = execution["map"]
    require(
        type(map_contract) is dict
        and set(map_contract) == {"object_path", "relative_path", "source_package"}
        and map_contract["object_path"] == MAP_OBJECT_PATH
        and map_contract["relative_path"] == MAP_RELATIVE_PATH,
        "map contract differs",
    )
    validate_artifact(
        map_contract["source_package"],
        "copied source map",
        attempt / "project" / MAP_RELATIVE_PATH,
    )
    require(
        project
        == pathlib.Path(unreal.Paths.get_project_file_path()).resolve(strict=True),
        "running project differs",
    )
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
    contract = execution["accessory_contract"]
    require(
        type(contract) is dict
        and set(contract) == {"targets", "pot_semantic_id", "fit_policy"}
        and contract["targets"] == TARGETS
        and contract["pot_semantic_id"] == POT_SEMANTIC_ID
        and contract["fit_policy"] == FIT_POLICY,
        "accessory contract differs",
    )
    inventory = execution["asset_inventory"]
    expected_records = sorted(
        [row["asset"] for row in TARGETS], key=lambda row: row["object_path"]
    )
    require(
        type(inventory) is dict
        and set(inventory) == {"citysample_result", "dependency_asset_records"}
        and inventory["dependency_asset_records"] == expected_records,
        "asset inventory contract differs",
    )
    validate_artifact(inventory["citysample_result"], "City Sample result")
    source_manifest = execution["source_static_manifest"]
    require(
        type(source_manifest) is dict and source_manifest, "source manifest differs"
    )
    for target in TARGETS:
        pin = target["uasset"]
        require(
            source_manifest.get(pin["relative_path"])
            == {key: pin[key] for key in ("sha256", "size_bytes", "mode")},
            "source UAsset manifest pin differs",
        )
    support = load_support(support_path)
    require(
        support.static_manifest_tree(source_manifest)
        == execution["source_project_static_tree"],
        "source manifest/tree cross-binding differs",
    )
    return execution, execution_sha, result, sidecar, support


def normalized_number(value):
    number = float(value)
    require(math.isfinite(number), "reflected number is not finite")
    rounded = round(number, 6)
    return 0.0 if rounded == 0.0 else rounded


def contain_scale(value):
    number = float(value)
    require(math.isfinite(number) and number > 0.0, "fit scale is not positive finite")
    floored = math.floor(number * 1_000_000.0) / 1_000_000.0
    return normalized_number(floored)


def vector_row(value):
    return [
        normalized_number(value.x),
        normalized_number(value.y),
        normalized_number(value.z),
    ]


def transform_row(component_or_actor, actor=False):
    if actor:
        location = component_or_actor.get_actor_location()
        rotation = component_or_actor.get_actor_rotation()
        scale = component_or_actor.get_actor_scale3d()
    else:
        location = component_or_actor.get_editor_property("relative_location")
        rotation = component_or_actor.get_editor_property("relative_rotation")
        scale = component_or_actor.get_editor_property("relative_scale3d")
    return {
        "location_cm": vector_row(location),
        "rotation_deg": [
            normalized_number(rotation.roll),
            normalized_number(rotation.pitch),
            normalized_number(rotation.yaw),
        ],
        "scale": vector_row(scale),
    }


def property_value(value, name, label):
    try:
        return value.get_editor_property(name)
    except Exception as exc:
        raise CommandletFailure(label + " property is unavailable: " + name) from exc


def bool_property(value, name, label):
    result = property_value(value, name, label)
    require(type(result) is bool, label + " boolean differs: " + name)
    return result


def collision_label(component):
    value = component.get_collision_enabled()
    names = {
        "NO_COLLISION": "NoCollision",
        "QUERY_ONLY": "QueryOnly",
        "PHYSICS_ONLY": "PhysicsOnly",
        "QUERY_AND_PHYSICS": "QueryAndPhysics",
        "PROBE_ONLY": "ProbeOnly",
        "QUERY_AND_PROBE": "QueryAndProbe",
    }
    for attribute, label in names.items():
        candidate = getattr(unreal.CollisionEnabled, attribute, None)
        if candidate is not None and value == candidate:
            return label
    raise CommandletFailure("collision mode is outside the closed enum")


def serialized_simulates_physics(component, label):
    # `is_simulating_physics()` reports transient world/runtime activation and
    # can differ before versus after a cold editor reload.  UE 5.7 stores the
    # serialized flag in the nested FBodyInstance rather than flattening it on
    # UPrimitiveComponent's Python reflection surface.
    body_instance = property_value(component, "body_instance", label)
    require(body_instance is not None, label + " body instance is unavailable")
    return bool_property(body_instance, "simulate_physics", label + " body instance")


def component_observation(component, expected_name):
    require(
        isinstance(component, unreal.StaticMeshComponent),
        "static mesh component unavailable",
    )
    mesh = property_value(component, "static_mesh", expected_name)
    require(
        isinstance(mesh, unreal.StaticMesh), expected_name + " StaticMesh unavailable"
    )
    attach_parent = component.get_attach_parent()
    return {
        "component_path": str(component.get_path_name()),
        "component_name": str(component.get_name()),
        "mesh_object_path": str(mesh.get_path_name()),
        "relative_transform": transform_row(component),
        "visible": bool_property(component, "visible", expected_name),
        "collision_mode": collision_label(component),
        "collision_profile_name": str(component.get_collision_profile_name()),
        # UE 5.7 does not expose USceneComponent::GetMobility in its generated
        # Python wrapper.  Preserve the exact enum string used by the receipt,
        # but obtain the value through the stable editor-reflection surface.
        "mobility": str(property_value(component, "mobility", expected_name)),
        "attach_parent_component_path": (
            str(attach_parent.get_path_name()) if attach_parent is not None else None
        ),
        # The schema key remains stable; its value is serialized configuration,
        # not transient runtime-active physics state.
        "simulate_physics": serialized_simulates_physics(component, expected_name),
        "generate_overlap_events": bool_property(
            component, "generate_overlap_events", expected_name
        ),
        "can_ever_affect_navigation": bool_property(
            component, "can_ever_affect_navigation", expected_name
        ),
        "cast_shadow": bool_property(component, "cast_shadow", expected_name),
        "cast_hidden_shadow": bool_property(
            component, "cast_hidden_shadow", expected_name
        ),
    }


def semantic_id(actor):
    value = property_value(actor, "semantic_id", "pickup")
    require(type(value) is str and value, "pickup semantic id unavailable")
    return value


def pickup_observation(actor):
    semantic = semantic_id(actor)
    proxy = property_value(actor, "mesh", "pickup")
    presentation = property_value(actor, "presentation_mesh", "pickup")
    tags = sorted(str(value) for value in property_value(actor, "tags", "pickup"))
    actor_class = actor.get_class()
    require(actor_class is not None, "pickup class unavailable")
    carrier = actor.get_carrier()
    attach_parent_actor = actor.get_attach_parent_actor()
    owner = actor.get_owner()
    observation = {
        "semantic_id": semantic,
        "actor_path": str(actor.get_path_name()),
        "actor_class_path": str(actor_class.get_path_name()),
        "tags": tags,
        "actor_transform": transform_row(actor, actor=True),
        "actor_replication": {
            "replicates": bool_property(actor, "replicates", "pickup"),
            "replicate_movement": bool_property(actor, "replicate_movement", "pickup"),
            "net_load_on_client": bool_property(actor, "net_load_on_client", "pickup"),
        },
        "portable": bool_property(actor, "portable", "pickup"),
        "carrier_path": str(carrier.get_path_name()) if carrier is not None else None,
        "attach_parent_actor_path": (
            str(attach_parent_actor.get_path_name())
            if attach_parent_actor is not None
            else None
        ),
        "owner_path": str(owner.get_path_name()) if owner is not None else None,
        "actor_hidden_in_game": bool_property(actor, "hidden", "pickup"),
        "proxy": component_observation(proxy, "PickupMesh"),
        "presentation": component_observation(presentation, "PresentationMesh"),
    }
    require(
        observation["actor_class_path"] == PICKUP_CLASS_PATH
        and "VistaRole=pickup" in tags
        and "VistaSemanticId=" + semantic in tags
        and observation["proxy"]["component_name"] == "PickupMesh"
        and observation["presentation"]["component_name"] == "PresentationMesh"
        and observation["proxy"]["attach_parent_component_path"] is None
        and observation["presentation"]["attach_parent_component_path"]
        == observation["proxy"]["component_path"]
        and observation["presentation"]["collision_profile_name"] == "NoCollision",
        "pickup identity or component authority differs",
    )
    return observation


def authority_view(observation):
    return {
        key: copy.deepcopy(value)
        for key, value in observation.items()
        if key != "presentation"
    }


def presentation_policy_view(observation):
    result = copy.deepcopy(observation["presentation"])
    result.pop("mesh_object_path")
    result.pop("relative_transform")
    return result


def pickup_for(actors, semantic, expected_path=None):
    matches = [
        actor
        for actor in actors
        if actor.get_class() is not None
        and str(actor.get_class().get_path_name()) == PICKUP_CLASS_PATH
        and semantic_id(actor) == semantic
        and "VistaSemanticId=" + semantic
        in sorted(str(value) for value in property_value(actor, "tags", "pickup"))
    ]
    require(len(matches) == 1, "pickup semantic identity is not exact: " + semantic)
    if expected_path is not None:
        require(
            str(matches[0].get_path_name()) == expected_path,
            "pickup actor path differs",
        )
    return matches[0]


def reflected_property(value, name):
    try:
        return value.get_editor_property(name)
    except Exception:
        return getattr(value, name, None)


def asset_class_name(asset_data):
    value = reflected_property(asset_data, "asset_class_path")
    if value is None:
        value = reflected_property(asset_data, "asset_class")
    nested = reflected_property(value, "asset_name") if value is not None else None
    if nested:
        return str(nested)
    text = str(value)
    return text.rsplit(".", 1)[-1] if "." in text else text


def runtime_asset_record(registry, expected):
    package_name = expected["package_name"]
    try:
        values = registry.get_assets_by_package_name(package_name, True)
    except TypeError:
        values = registry.get_assets_by_package_name(package_name)
    records = []
    for asset_data in list(values):
        object_path = str(reflected_property(asset_data, "object_path") or "")
        if not object_path:
            asset_name = str(reflected_property(asset_data, "asset_name") or "")
            object_path = (
                package_name + "." + asset_name if asset_name else package_name
            )
        records.append(
            {
                "asset_class": asset_class_name(asset_data),
                "object_path": object_path,
                "package_name": str(
                    reflected_property(asset_data, "package_name") or package_name
                ),
            }
        )
    require(records.count(expected) == 1, "runtime AssetData record differs")
    return copy.deepcopy(expected)


def mesh_bounds(mesh):
    require(isinstance(mesh, unreal.StaticMesh), "bounds source is not StaticMesh")
    box = mesh.get_bounding_box()
    minimum = vector_row(box.min)
    maximum = vector_row(box.max)
    size = [normalized_number(high - low) for low, high in zip(minimum, maximum)]
    center = [
        normalized_number((low + high) / 2.0) for low, high in zip(minimum, maximum)
    ]
    require(
        all(value > 0.0 for value in size), "StaticMesh bounds have non-positive extent"
    )
    return {"min_cm": minimum, "max_cm": maximum, "size_cm": size, "center_cm": center}


def compute_fit(source_component, target_mesh, semantic):
    source_mesh = property_value(source_component, "static_mesh", "source presentation")
    require(
        isinstance(source_mesh, unreal.StaticMesh),
        "source presentation mesh unavailable",
    )
    source_bounds = mesh_bounds(source_mesh)
    target_bounds = mesh_bounds(target_mesh)
    source_transform = transform_row(source_component)
    require(
        all(value > 0.0 for value in source_transform["scale"]),
        "source presentation scale must be strictly positive",
    )
    envelope = [
        normalized_number(size * abs(scale))
        for size, scale in zip(source_bounds["size_cm"], source_transform["scale"])
    ]
    ratios = [envelope[index] / target_bounds["size_cm"][index] for index in range(3)]
    uniform = contain_scale(min(ratios))
    require(uniform > 0.0, "deterministic fit scale is non-positive")
    delta = unreal.Vector(
        x=source_bounds["center_cm"][0] * source_transform["scale"][0]
        - target_bounds["center_cm"][0] * uniform,
        y=source_bounds["center_cm"][1] * source_transform["scale"][1]
        - target_bounds["center_cm"][1] * uniform,
        z=source_bounds["center_cm"][2] * source_transform["scale"][2]
        - target_bounds["center_cm"][2] * uniform,
    )
    rotation = unreal.Rotator(
        roll=source_transform["rotation_deg"][0],
        pitch=source_transform["rotation_deg"][1],
        yaw=source_transform["rotation_deg"][2],
    )
    require(hasattr(delta, "rotate"), "Vector.rotate reflection unavailable")
    rotated = delta.rotate(rotation)
    final = {
        "location_cm": [
            normalized_number(source_transform["location_cm"][index] + value)
            for index, value in enumerate((rotated.x, rotated.y, rotated.z))
        ],
        "rotation_deg": copy.deepcopy(source_transform["rotation_deg"]),
        "scale": [uniform, uniform, uniform],
    }
    return {
        "semantic_id": semantic,
        "policy": FIT_POLICY,
        "bounds_method": "StaticMesh.get_bounding_box",
        "source_mesh_object_path": str(source_mesh.get_path_name()),
        "target_mesh_object_path": str(target_mesh.get_path_name()),
        "source_bounds": source_bounds,
        "target_bounds": target_bounds,
        "source_envelope_cm": envelope,
        "uniform_scale": uniform,
        "final_relative_transform": final,
    }


def unreal_transform(value):
    return unreal.Transform(
        location=unreal.Vector(
            x=value["location_cm"][0],
            y=value["location_cm"][1],
            z=value["location_cm"][2],
        ),
        rotation=unreal.Rotator(
            roll=value["rotation_deg"][0],
            pitch=value["rotation_deg"][1],
            yaw=value["rotation_deg"][2],
        ),
        scale=unreal.Vector(
            x=value["scale"][0], y=value["scale"][1], z=value["scale"][2]
        ),
    )


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


def map_artifact(path):
    metadata = os.lstat(path)
    require(
        path.resolve(strict=True) == path
        and stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode),
        "cold-reloaded map is not a canonical regular file",
    )
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "size_bytes": metadata.st_size,
    }


def run():
    execution, execution_sha, result_path, sidecar_path, support = read_execution()
    gates = {key: False for key in RESULT_GATE_KEYS}
    inventory_before = []
    inventory_reloaded = []
    target_before = []
    target_after = []
    target_reloaded = []
    target_asset_records = []
    fit_records = []
    pot_before = None
    pot_reloaded = None
    map_package = None
    error = None
    try:
        project = pathlib.Path(execution["project"]["path"])
        source_manifest = support.static_project_manifest(project)
        require(
            source_manifest == execution["source_static_manifest"],
            "copied project drifted",
        )
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        require(level_subsystem.load_level(MAP_OBJECT_PATH), "fixed map failed to load")
        gates["fixed_map_loaded"] = True
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "fixed map world unavailable")
        actors = list(actor_subsystem.get_all_level_actors())
        inventory_before = support.actor_inventory(actors)
        require(len(inventory_before) == 150, "R4 actor inventory cardinality differs")
        gates["source_actor_inventory_exact"] = True
        targets = [
            pickup_for(actors, row["semantic_id"], row["actor_path"]) for row in TARGETS
        ]
        pot = pickup_for(actors, POT_SEMANTIC_ID)
        require(
            len({str(actor.get_path_name()) for actor in [*targets, pot]}) == 3,
            "target overlap",
        )
        gates["exact_two_targets_found"] = True
        target_before = [pickup_observation(actor) for actor in targets]
        require(
            all(
                observation["presentation"]["mesh_object_path"]
                == target["source_mesh_object_path"]
                for observation, target in zip(target_before, TARGETS)
            ),
            "R4-C source presentation mesh identity differs",
        )
        pot_before = pickup_observation(pot)
        meshes = []
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        for target in TARGETS:
            target_asset_records.append(runtime_asset_record(registry, target["asset"]))
            mesh = unreal.load_asset(target["asset"]["object_path"])
            require(
                isinstance(mesh, unreal.StaticMesh)
                and str(mesh.get_path_name()) == target["asset"]["object_path"],
                "exact accessory StaticMesh failed to load",
            )
            meshes.append(mesh)
        gates["exact_static_mesh_assets_loaded"] = len(meshes) == 2
        gates["asset_registry_type_and_provenance_exact"] = (
            sorted(target_asset_records, key=lambda row: row["object_path"])
            == execution["asset_inventory"]["dependency_asset_records"]
        )
        for actor, mesh, source in zip(targets, meshes, target_before):
            presentation = property_value(actor, "presentation_mesh", "pickup")
            fit = compute_fit(presentation, mesh, source["semantic_id"])
            fit_records.append(fit)
            require(
                actor.configure_presentation_mesh(
                    mesh, unreal_transform(fit["final_relative_transform"])
                )
                is True,
                "ConfigurePresentationMesh returned false",
            )
            upgraded = pickup_observation(actor)
            require(
                authority_view(upgraded) == authority_view(source)
                and presentation_policy_view(upgraded)
                == presentation_policy_view(source)
                and upgraded["presentation"]["mesh_object_path"]
                == fit["target_mesh_object_path"]
                and upgraded["presentation"]["relative_transform"]
                == fit["final_relative_transform"],
                "target mutation escaped presentation asset/fit fields",
            )
            target_after.append(upgraded)
        gates["deterministic_reflection_fit_computed"] = len(fit_records) == 2
        gates["only_target_presentations_mutated"] = True
        gates["semantic_actor_authority_preserved"] = all(
            authority_view(before) == authority_view(after)
            for before, after in zip(target_before, target_after)
        )
        gates["pickup_collision_proxy_preserved"] = all(
            before["proxy"] == after["proxy"]
            for before, after in zip(target_before, target_after)
        )
        gates["pot_presentation_preserved"] = pickup_observation(pot) == pot_before
        require(
            all(
                gates[key]
                for key in (
                    "semantic_actor_authority_preserved",
                    "pickup_collision_proxy_preserved",
                    "pot_presentation_preserved",
                )
            ),
            "authority or pot changed before save",
        )
        require(
            support.actor_inventory(list(actor_subsystem.get_all_level_actors()))
            == inventory_before,
            "actor identity changed before save",
        )
        require(
            unreal.EditorLoadingAndSavingUtils.save_map(world, MAP_OBJECT_PATH),
            "R6 map save failed",
        )
        gates["map_saved"] = True
        require(
            level_subsystem.load_level(MAP_OBJECT_PATH), "R6 map cold reload failed"
        )
        gates["map_cold_reloaded"] = True
        reloaded_actors = list(actor_subsystem.get_all_level_actors())
        inventory_reloaded = support.actor_inventory(reloaded_actors)
        gates["actor_inventory_reloaded_exact"] = inventory_reloaded == inventory_before
        reloaded_targets = [
            pickup_for(reloaded_actors, row["semantic_id"], row["actor_path"])
            for row in TARGETS
        ]
        target_reloaded = [pickup_observation(actor) for actor in reloaded_targets]
        pot_reloaded = pickup_observation(pickup_for(reloaded_actors, POT_SEMANTIC_ID))
        gates["target_presentations_reloaded_exact"] = target_reloaded == target_after
        gates["pot_presentation_preserved"] = pot_reloaded == pot_before
        require(
            gates["actor_inventory_reloaded_exact"]
            and gates["target_presentations_reloaded_exact"]
            and gates["pot_presentation_preserved"],
            "cold-reloaded actor/accessory state differs",
        )
        map_path = project.parent / MAP_RELATIVE_PATH
        map_package = map_artifact(map_path)
        output_manifest = support.static_project_manifest(project)
        gates["only_map_static_artifact_changed"] = support.only_map_changed(
            source_manifest, output_manifest
        )
        gates["cold_reloaded_map_artifact_sealed"] = True
        require(all(gates.values()), "terminal R6 gate inventory is incomplete")
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
            "map_object_path": MAP_OBJECT_PATH,
            "map_package": map_package,
            "actor_inventory_before": inventory_before,
            "actor_inventory_reloaded": inventory_reloaded,
            "target_observations_before": target_before,
            "target_asset_records": sorted(
                target_asset_records, key=lambda row: row["object_path"]
            ),
            "target_fit_records": fit_records,
            "target_observations_after_save": target_after,
            "target_observations_reloaded": target_reloaded,
            "pot_observation_before": pot_before,
            "pot_observation_reloaded": pot_reloaded,
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "acceptance": copy.deepcopy(ACCEPTANCE),
            "gates": gates,
            "error": error,
        }
    )
    publish_result(result_path, sidecar_path, result)
    require(succeeded, "accessory R6 commandlet failed")


if __name__ == "__main__":
    run()
