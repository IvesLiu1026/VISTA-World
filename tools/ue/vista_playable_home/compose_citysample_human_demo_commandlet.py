"""Compose three real HSSD pickup presentations in the sealed human demo.

This script is copied and SHA-pinned by ``materialize_citysample_human_demo``.
It accepts no arguments, network token, agent adapter, or mutable provider.  It
loads the exact City Sample crowd Blueprint for dependency proof, modifies the
fixed VISTA map, saves it, cold reloads it, and emits a closed result.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import re
import stat

import unreal


REQUEST_SCHEMA = "simworld.vista.citysample-human-demo-request/v1"
RESULT_SCHEMA = "simworld.vista.citysample-human-demo-result/v1"
RESULT_STATUS = "citysample_human_demo_map_saved_cold_reloaded"
FAILURE_STATUS = "citysample_human_demo_commandlet_failed"
PROVIDER_ID = "citysample_crowd_visual_demo_v1"
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
REQUEST_ENV = "VISTA_CITYSAMPLE_HUMAN_DEMO_REQUEST"
REQUEST_SHA_ENV = "VISTA_CITYSAMPLE_HUMAN_DEMO_REQUEST_SHA256"
RESULT_ENV = "VISTA_CITYSAMPLE_HUMAN_DEMO_RESULT"
RESULT_SHA_ENV = "VISTA_CITYSAMPLE_HUMAN_DEMO_RESULT_SHA256"
RESULT_MARKER = "VISTA_CITYSAMPLE_HUMAN_DEMO_RESULT:"
REQUEST_NAME = "citysample-human-demo-request.json"
RESULT_NAME = "citysample-human-demo-result.json"
COMMANDLET_NAME = "compose_citysample_human_demo_commandlet.py"
PROJECT_NAME = "VistaPlayableHome.uproject"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
MAP_RELATIVE_PATH = (
    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
)
CITY_BLUEPRINT_OBJECT = (
    "/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter.BP_CrowdCharacter"
)
CITY_GENERATED_CLASS = CITY_BLUEPRINT_OBJECT + "_C"
CITY_DEFAULT_OBJECT = (
    "/Game/CitySampleCrowd/Blueprints/BP_CrowdCharacter.Default__BP_CrowdCharacter_C"
)
PICKUP_CLASS_PATH = "/Script/VistaPlayableHome.VistaPickupActor"
DUPLICATE_HSSD_TAG = "VistaHssdInstanceId=hssd.r1/kitchen_dining.pot.01"
DUPLICATE_REQUIRED_ROLE = "VistaRole=hssd_curated_overlay"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_REQUEST_BYTES = 1024 * 1024

HSSD_HOST_RECEIPT_SHA256 = (
    "d8ea65744dd1357609013c8e00c880d3e05f1f580dfc04a1b59bb36b67d79c69"
)
HSSD_PROJECT_SHA256 = "850e7b22ad9ace3e50d586eba4fdfdd50d07ce25da3ba464c10d4966fe47a94a"
HSSD_SCENE_RECEIPT_SHA256 = (
    "7b50ad48bac26e0e4950b17b67f8c7c7fba09d9ea300e6f602b8ec29da15771b"
)
CITY_HOST_RECEIPT_SHA256 = (
    "c7983624af4c8b94742ee3647f938c7c734da617f15a66ad4aa793a095747169"
)
CITY_RESULT_SHA256 = "ad3bc45a087bed6e3ed688eb6ba111f4bf7d81d8ce1add5b5e297a2105e49f77"
CITY_CONTENT_SHA256 = "362f3e1796aadba96f9a309fc543562e7100bd403d68d3a2277f03a51a0cbe09"
PLUGIN_SOURCE_GIT_COMMIT = "dadb00a278218a1b402908c72b9d1c8967770035"

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
}
PRESENTATIONS = [
    {
        "semantic_id": "home.r1/room.bedroom/entity.phone.01",
        "mesh_object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            "HSSDPrivateResearch/Assets/hssd_static_phone/"
            "hssd_static_phone.hssd_static_phone"
        ),
        "relative_transform": {
            "location_cm": [0.0, 0.0, -6.0],
            "rotation_deg": [0.0, 0.0, 10.0],
            "scale": [1.0, 1.0, 1.0],
        },
    },
    {
        "semantic_id": "home.r1/room.kitchen_dining/entity.coffee_cup.01",
        "mesh_object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            "HSSDPrivateResearch/Assets/hssd_static_coffee_cup/"
            "hssd_static_coffee_cup.hssd_static_coffee_cup"
        ),
        "relative_transform": {
            "location_cm": [0.0, 0.0, -1.0106],
            "rotation_deg": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        },
    },
    {
        "semantic_id": "home.r1/room.kitchen_dining/entity.pot.01",
        "mesh_object_path": (
            "/Game/VISTA/PlayableHome/hssd_private_research_r5_phase1_diagnostic/"
            "HSSDPrivateResearch/Assets/hssd_static_cooking_pot/"
            "hssd_static_cooking_pot.hssd_static_cooking_pot"
        ),
        "relative_transform": {
            "location_cm": [0.0, 0.0, 4.25],
            "rotation_deg": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        },
    },
]

REQUEST_KEYS = {
    "schema_version",
    "attempt_root",
    "project_file",
    "project_file_sha256",
    "commandlet_path",
    "commandlet_sha256",
    "result_path",
    "result_sha256_path",
    "engine_version",
    "provider_id",
    "human_operated_visual_demo_only",
    "prohibited_agent_adapter",
    "map_object_path",
    "map_relative_path",
    "city_character",
    "presentations",
    "duplicate_hssd_actor_tag_to_destroy",
    "source_pins",
    "legal_scope",
    "acknowledgements",
    "claims",
    "content_digest",
}
SOURCE_PIN_KEYS = {
    "hssd_host_receipt_sha256",
    "hssd_project_sha256",
    "hssd_scene_receipt_sha256",
    "city_host_receipt_sha256",
    "city_result_sha256",
    "citysample_crowd_sha256",
    "plugin_package_sha256",
    "plugin_source_git_commit",
    "repository_plugin_contract",
}
RESULT_GATE_KEYS = {
    "exact_city_blueprint_loaded",
    "exact_generated_class_loaded",
    "exact_character_cdo_loaded",
    "fixed_map_loaded",
    "exact_three_pickups_found",
    "exact_three_presentation_meshes_loaded",
    "configure_presentation_mesh_succeeded",
    "pickup_actors_unhidden",
    "pickup_root_meshes_hidden",
    "presentation_collision_disabled",
    "presentation_physics_disabled",
    "presentation_navigation_disabled",
    "only_exact_duplicate_hssd_pot_destroyed",
    "all_other_actor_identities_preserved",
    "map_saved",
    "map_cold_reloaded",
    "cold_reloaded_map_artifact_sealed",
    "exact_three_presentations_reloaded",
    "pickup_actor_paths_stable_after_reload",
    "duplicate_absent_after_reload",
}


class CommandletFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise CommandletFailure(message)


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


def sha256_file(path):
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), "pinned file is not regular")
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
        require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "pinned file changed while hashing",
        )
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def canonical_absolute(path, label):
    require(type(path) is str and path, label + " is missing")
    candidate = pathlib.Path(path)
    require(
        candidate.is_absolute() and os.path.normpath(path) == path, label + " differs"
    )
    require(candidate.resolve(strict=True) == candidate, label + " is not canonical")
    return candidate


def direct_child(path, attempt, name, label):
    candidate = canonical_absolute(path, label)
    require(
        candidate == attempt / name and candidate.parent == attempt,
        label + " binding differs",
    )
    return candidate


def read_request():
    request_value = os.environ.get(REQUEST_ENV)
    request_sha = os.environ.get(REQUEST_SHA_ENV)
    result_value = os.environ.get(RESULT_ENV)
    result_sha_value = os.environ.get(RESULT_SHA_ENV)
    require(
        request_value is not None and request_sha is not None,
        "request environment is absent",
    )
    require(
        SHA256_RE.fullmatch(request_sha) is not None, "request SHA environment differs"
    )
    request_path = canonical_absolute(request_value, "request path")
    raw = request_path.read_bytes()
    require(
        len(raw) <= MAX_REQUEST_BYTES
        and hashlib.sha256(raw).hexdigest() == request_sha,
        "request bytes differ",
    )
    try:
        request = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except (UnicodeError, ValueError) as exc:
        raise CommandletFailure("request is not strict UTF-8 JSON") from exc
    require(
        type(request) is dict and set(request) == REQUEST_KEYS,
        "request key inventory differs",
    )
    require(raw == canonical_json(request), "request is not canonical")
    require(
        request.get("content_digest") == content_digest(request),
        "request digest differs",
    )
    attempt = canonical_absolute(request["attempt_root"], "attempt root")
    require(
        attempt.is_dir() and request_path == attempt / REQUEST_NAME,
        "attempt/request binding differs",
    )
    project_file = canonical_absolute(request["project_file"], "project file")
    require(
        project_file == attempt / "project" / PROJECT_NAME
        and sha256_file(project_file) == request["project_file_sha256"],
        "project descriptor binding differs",
    )
    commandlet = canonical_absolute(request["commandlet_path"], "commandlet path")
    require(
        commandlet == attempt / COMMANDLET_NAME
        and os.path.realpath(__file__).replace("\\", "/") == str(commandlet)
        and sha256_file(commandlet) == request["commandlet_sha256"],
        "commandlet binding differs",
    )
    result = pathlib.Path(request["result_path"])
    result_sidecar = pathlib.Path(request["result_sha256_path"])
    require(
        result == attempt / RESULT_NAME
        and result_sidecar == attempt / (RESULT_NAME + ".sha256")
        and result_value == str(result)
        and result_sha_value == str(result_sidecar)
        and not result.exists()
        and not result_sidecar.exists(),
        "result binding differs",
    )
    validate_request_contract(request)
    return request, request_sha, result, result_sidecar


def validate_repository_contract(value):
    require(
        type(value) is dict and 3 <= len(value) <= 512,
        "repository plugin contract differs",
    )
    for relative, pin in value.items():
        require(
            type(relative) is str
            and (
                relative == "VistaPlayableHome.uplugin"
                or relative.startswith("Source/")
            )
            and ".." not in pathlib.PurePosixPath(relative).parts
            and type(pin) is dict
            and set(pin) == {"sha256", "size_bytes"}
            and type(pin["sha256"]) is str
            and SHA256_RE.fullmatch(pin["sha256"]) is not None
            and type(pin["size_bytes"]) is int
            and not isinstance(pin["size_bytes"], bool)
            and pin["size_bytes"] >= 0,
            "repository plugin source/descriptor pin differs",
        )


def validate_request_contract(request):
    require(request["schema_version"] == REQUEST_SCHEMA, "request schema differs")
    require(request["engine_version"] == ENGINE_VERSION, "request engine differs")
    require(request["provider_id"] == PROVIDER_ID, "request provider differs")
    require(
        request["human_operated_visual_demo_only"] is True, "human-only gate differs"
    )
    require(request["prohibited_agent_adapter"] is True, "agent prohibition differs")
    require(request["map_object_path"] == MAP_OBJECT_PATH, "map object path differs")
    require(
        request["map_relative_path"] == MAP_RELATIVE_PATH, "map package path differs"
    )
    require(
        request["city_character"]
        == {
            "blueprint_object_path": CITY_BLUEPRINT_OBJECT,
            "generated_class_path": CITY_GENERATED_CLASS,
            "default_object_path": CITY_DEFAULT_OBJECT,
        },
        "City character binding differs",
    )
    require(request["presentations"] == PRESENTATIONS, "presentation contract differs")
    require(
        request["duplicate_hssd_actor_tag_to_destroy"] == DUPLICATE_HSSD_TAG,
        "duplicate tag differs",
    )
    pins = request["source_pins"]
    require(
        type(pins) is dict and set(pins) == SOURCE_PIN_KEYS,
        "source pin inventory differs",
    )
    require(
        pins["hssd_host_receipt_sha256"] == HSSD_HOST_RECEIPT_SHA256
        and pins["hssd_project_sha256"] == HSSD_PROJECT_SHA256
        and pins["hssd_scene_receipt_sha256"] == HSSD_SCENE_RECEIPT_SHA256
        and pins["city_host_receipt_sha256"] == CITY_HOST_RECEIPT_SHA256
        and pins["city_result_sha256"] == CITY_RESULT_SHA256
        and pins["citysample_crowd_sha256"] == CITY_CONTENT_SHA256
        and type(pins["plugin_package_sha256"]) is str
        and SHA256_RE.fullmatch(pins["plugin_package_sha256"]) is not None
        and pins["plugin_source_git_commit"] == PLUGIN_SOURCE_GIT_COMMIT,
        "fixed source pins differ",
    )
    validate_repository_contract(pins["repository_plugin_contract"])
    require(request["legal_scope"] == LEGAL_SCOPE, "legal scope differs")
    require(
        all(
            request["legal_scope"].get(key) is value
            for key, value in LEGAL_SCOPE.items()
        ),
        "legal booleans differ",
    )
    require(
        request["acknowledgements"] == ACKNOWLEDGEMENTS, "legal acknowledgements differ"
    )
    require(request["claims"] == CLAIMS, "honest claim boundary differs")
    require(
        all(request["claims"].get(key) is value for key, value in CLAIMS.items()),
        "claim booleans differ",
    )


def vector(values):
    return unreal.Vector(x=values[0], y=values[1], z=values[2])


def rotator(values):
    return unreal.Rotator(roll=values[0], pitch=values[1], yaw=values[2])


def transform(value):
    return unreal.Transform(
        location=vector(value["location_cm"]),
        rotation=rotator(value["rotation_deg"]),
        scale=vector(value["scale"]),
    )


def sorted_tags(actor):
    return sorted(str(value) for value in actor.get_editor_property("tags"))


def property_or_none(value, name):
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def actor_class_path(actor):
    actor_class = actor.get_class()
    require(actor_class is not None, "actor class is unavailable")
    return str(actor_class.get_path_name())


def actor_hidden(actor):
    value = property_or_none(actor, "hidden")
    require(type(value) is bool, "actor hidden state is unavailable")
    return value


def collision_label(component):
    value = component.get_collision_enabled()
    expected = getattr(unreal.CollisionEnabled, "NO_COLLISION", None)
    require(
        expected is not None and value == expected, "presentation collision is enabled"
    )
    return "NoCollision"


def simulates_physics(component):
    try:
        return bool(component.is_simulating_physics())
    except Exception:
        value = property_or_none(component, "simulate_physics")
        require(type(value) is bool, "presentation physics state is unavailable")
        return value


def relative_transform(component):
    location = component.get_relative_location()
    rotation = component.get_relative_rotation()
    scale = component.get_relative_scale3d()
    return {
        "location_cm": [float(location.x), float(location.y), float(location.z)],
        "rotation_deg": [
            float(rotation.roll),
            float(rotation.pitch),
            float(rotation.yaw),
        ],
        "scale": [float(scale.x), float(scale.y), float(scale.z)],
    }


def angle_delta(left, right):
    return abs((float(left) - float(right) + 180.0) % 360.0 - 180.0)


def transform_matches(actual, expected):
    return (
        all(
            abs(float(a) - float(b)) <= 0.0001
            for a, b in zip(actual["location_cm"], expected["location_cm"])
        )
        and all(
            angle_delta(a, b) <= 0.0001
            for a, b in zip(actual["rotation_deg"], expected["rotation_deg"])
        )
        and all(
            abs(float(a) - float(b)) <= 0.0001
            for a, b in zip(actual["scale"], expected["scale"])
        )
    )


def semantic_id(actor):
    value = property_or_none(actor, "semantic_id")
    require(type(value) is str and value, "pickup semantic_id property is unavailable")
    return value


def pickup_for(actors, expected_id):
    tag = "VistaSemanticId=" + expected_id
    matches = [
        actor
        for actor in actors
        if actor_class_path(actor) == PICKUP_CLASS_PATH
        and tag in sorted_tags(actor)
        and semantic_id(actor) == expected_id
    ]
    require(len(matches) == 1, "pickup identity is not exact: " + expected_id)
    return matches[0]


def component_mesh_path(component):
    mesh = property_or_none(component, "static_mesh")
    require(
        isinstance(mesh, unreal.StaticMesh), "presentation StaticMesh is unavailable"
    )
    return str(mesh.get_path_name())


def observe_pickup(actor, expected):
    require(actor_class_path(actor) == PICKUP_CLASS_PATH, "pickup class differs")
    require(
        semantic_id(actor) == expected["semantic_id"],
        "pickup semantic identity differs",
    )
    root = property_or_none(actor, "mesh")
    presentation = property_or_none(actor, "presentation_mesh")
    require(
        isinstance(root, unreal.StaticMeshComponent)
        and isinstance(presentation, unreal.StaticMeshComponent),
        "pickup presentation components are unavailable",
    )
    root_visible = property_or_none(root, "visible")
    presentation_visible = property_or_none(presentation, "visible")
    overlap = property_or_none(presentation, "generate_overlap_events")
    navigation = property_or_none(presentation, "can_ever_affect_navigation")
    observation = {
        "semantic_id": expected["semantic_id"],
        "actor_path": str(actor.get_path_name()),
        "actor_class_path": actor_class_path(actor),
        "actor_hidden_in_game": actor_hidden(actor),
        "root_component_path": str(root.get_path_name()),
        "root_visible": root_visible,
        "presentation_component_path": str(presentation.get_path_name()),
        "presentation_visible": presentation_visible,
        "mesh_object_path": component_mesh_path(presentation),
        "relative_transform": relative_transform(presentation),
        "collision_mode": collision_label(presentation),
        "simulate_physics": simulates_physics(presentation),
        "generate_overlap_events": overlap,
        "can_ever_affect_navigation": navigation,
    }
    require(
        observation["actor_hidden_in_game"] is False
        and observation["root_visible"] is False
        and observation["presentation_visible"] is True
        and observation["mesh_object_path"] == expected["mesh_object_path"]
        and transform_matches(
            observation["relative_transform"], expected["relative_transform"]
        )
        and observation["collision_mode"] == "NoCollision"
        and observation["simulate_physics"] is False
        and observation["generate_overlap_events"] is False
        and observation["can_ever_affect_navigation"] is False,
        "pickup presentation policy differs: " + expected["semantic_id"],
    )
    return observation


def load_exact_city_character():
    blueprint = unreal.EditorAssetLibrary.load_asset(CITY_BLUEPRINT_OBJECT)
    generated = unreal.EditorAssetLibrary.load_blueprint_class(CITY_BLUEPRINT_OBJECT)
    loaded = unreal.load_class(None, CITY_GENERATED_CLASS)
    require(
        blueprint is not None
        and str(blueprint.get_path_name()) == CITY_BLUEPRINT_OBJECT,
        "exact City Sample Blueprint failed to load",
    )
    require(
        generated is not None
        and str(generated.get_path_name()) == CITY_GENERATED_CLASS
        and loaded is not None
        and loaded == generated
        and str(loaded.get_path_name()) == CITY_GENERATED_CLASS,
        "exact City Sample generated class failed to load",
    )
    default = unreal.get_default_object(loaded)
    require(
        default is not None
        and isinstance(default, unreal.Character)
        and str(default.get_path_name()) == CITY_DEFAULT_OBJECT,
        "exact City Sample Character CDO failed to load",
    )
    return {
        "blueprint_object_path": CITY_BLUEPRINT_OBJECT,
        "generated_class_path": CITY_GENERATED_CLASS,
        "default_object_path": CITY_DEFAULT_OBJECT,
    }


def duplicate_actor(actors):
    matches = [actor for actor in actors if DUPLICATE_HSSD_TAG in sorted_tags(actor)]
    require(len(matches) == 1, "duplicate curated HSSD pot identity is not exact")
    require(
        DUPLICATE_REQUIRED_ROLE in sorted_tags(matches[0])
        and actor_class_path(matches[0]).endswith(".StaticMeshActor"),
        "duplicate curated HSSD pot authority differs",
    )
    return matches[0]


def actor_identity_inventory(actors):
    result = [
        {
            "actor_path": str(actor.get_path_name()),
            "actor_class_path": actor_class_path(actor),
            "tags": sorted_tags(actor),
        }
        for actor in actors
    ]
    result.sort(key=lambda row: row["actor_path"])
    require(
        len(result) == len({row["actor_path"] for row in result}),
        "actor identity inventory contains duplicate paths",
    )
    return result


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
            offset += os.write(descriptor, raw[offset:])
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
    request, request_sha, result_path, result_sidecar = read_request()
    require(
        str(unreal.SystemLibrary.get_engine_version()) == ENGINE_VERSION,
        "runtime engine differs",
    )
    loaded_project = os.path.realpath(unreal.Paths.get_project_file_path()).replace(
        "\\", "/"
    )
    require(
        loaded_project == request["project_file"]
        and sha256_file(loaded_project) == request["project_file_sha256"],
        "loaded project differs",
    )
    gates = {key: False for key in RESULT_GATE_KEYS}
    before_save = []
    reloaded = []
    destroyed_path = None
    actor_inventory_before = []
    actor_inventory_reloaded = []
    map_saved = False
    map_reloaded = False
    map_package = None
    error = None
    try:
        character = load_exact_city_character()
        gates["exact_city_blueprint_loaded"] = (
            character["blueprint_object_path"] == CITY_BLUEPRINT_OBJECT
        )
        gates["exact_generated_class_loaded"] = (
            character["generated_class_path"] == CITY_GENERATED_CLASS
        )
        gates["exact_character_cdo_loaded"] = (
            character["default_object_path"] == CITY_DEFAULT_OBJECT
        )

        meshes = {}
        for binding in PRESENTATIONS:
            mesh = unreal.load_asset(binding["mesh_object_path"])
            require(
                isinstance(mesh, unreal.StaticMesh), "presentation mesh failed to load"
            )
            meshes[binding["semantic_id"]] = mesh
        gates["exact_three_presentation_meshes_loaded"] = len(meshes) == 3

        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        require(level_subsystem.load_level(MAP_OBJECT_PATH), "fixed map failed to load")
        gates["fixed_map_loaded"] = True
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "fixed map world is unavailable")
        actors = list(actor_subsystem.get_all_level_actors())
        actor_inventory_before = actor_identity_inventory(actors)
        pickups = [
            pickup_for(actors, binding["semantic_id"]) for binding in PRESENTATIONS
        ]
        require(
            len({str(actor.get_path_name()) for actor in pickups}) == 3,
            "pickup identities overlap",
        )
        gates["exact_three_pickups_found"] = True

        duplicate = duplicate_actor(actors)
        destroyed_path = str(duplicate.get_path_name())
        require(
            actor_subsystem.destroy_actor(duplicate),
            "duplicate curated HSSD pot destroy failed",
        )
        remaining = list(actor_subsystem.get_all_level_actors())
        require(
            not any(DUPLICATE_HSSD_TAG in sorted_tags(actor) for actor in remaining),
            "duplicate curated HSSD pot remains",
        )
        gates["only_exact_duplicate_hssd_pot_destroyed"] = True
        expected_remaining_inventory = [
            row for row in actor_inventory_before if row["actor_path"] != destroyed_path
        ]
        require(
            actor_identity_inventory(remaining) == expected_remaining_inventory,
            "an actor other than the exact duplicate changed during destroy",
        )

        for actor, binding in zip(pickups, PRESENTATIONS):
            configured = actor.configure_presentation_mesh(
                meshes[binding["semantic_id"]],
                transform(binding["relative_transform"]),
            )
            require(configured is True, "ConfigurePresentationMesh returned false")
            actor.set_actor_hidden_in_game(False)
            before_save.append(observe_pickup(actor, binding))
        gates["configure_presentation_mesh_succeeded"] = len(before_save) == 3
        gates["pickup_actors_unhidden"] = all(
            row["actor_hidden_in_game"] is False for row in before_save
        )
        gates["pickup_root_meshes_hidden"] = all(
            row["root_visible"] is False for row in before_save
        )
        gates["presentation_collision_disabled"] = all(
            row["collision_mode"] == "NoCollision" for row in before_save
        )
        gates["presentation_physics_disabled"] = all(
            row["simulate_physics"] is False for row in before_save
        )
        gates["presentation_navigation_disabled"] = all(
            row["can_ever_affect_navigation"] is False for row in before_save
        )

        require(
            unreal.EditorLoadingAndSavingUtils.save_map(world, MAP_OBJECT_PATH),
            "combined human-demo map save failed",
        )
        map_saved = True
        gates["map_saved"] = True
        require(
            level_subsystem.load_level(MAP_OBJECT_PATH),
            "combined human-demo map cold reload failed",
        )
        map_reloaded = True
        gates["map_cold_reloaded"] = True
        reloaded_actors = list(actor_subsystem.get_all_level_actors())
        actor_inventory_reloaded = actor_identity_inventory(reloaded_actors)
        reloaded_pickups = [
            pickup_for(reloaded_actors, binding["semantic_id"])
            for binding in PRESENTATIONS
        ]
        reloaded = [
            observe_pickup(actor, binding)
            for actor, binding in zip(reloaded_pickups, PRESENTATIONS)
        ]
        gates["exact_three_presentations_reloaded"] = len(reloaded) == 3
        gates["pickup_actor_paths_stable_after_reload"] = [
            row["actor_path"] for row in before_save
        ] == [row["actor_path"] for row in reloaded]
        gates["duplicate_absent_after_reload"] = not any(
            DUPLICATE_HSSD_TAG in sorted_tags(actor) for actor in reloaded_actors
        )
        gates["all_other_actor_identities_preserved"] = (
            actor_inventory_reloaded == expected_remaining_inventory
        )
        map_path = pathlib.Path(loaded_project).parent / pathlib.Path(MAP_RELATIVE_PATH)
        map_metadata = os.lstat(map_path)
        require(
            map_path.resolve(strict=True) == map_path
            and stat.S_ISREG(map_metadata.st_mode)
            and not stat.S_ISLNK(map_metadata.st_mode),
            "cold-reloaded map package is not a canonical regular file",
        )
        map_package = {
            "path": str(map_path),
            "sha256": sha256_file(map_path),
            "size_bytes": map_metadata.st_size,
        }
        gates["cold_reloaded_map_artifact_sealed"] = True
        require(all(gates.values()), "terminal gate inventory is incomplete")
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)[:512]}

    succeeded = error is None and map_saved and map_reloaded and all(gates.values())
    result = seal(
        {
            "schema_version": RESULT_SCHEMA,
            "status": RESULT_STATUS if succeeded else FAILURE_STATUS,
            "provider_id": PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "request_sha256": request_sha,
            "map_object_path": MAP_OBJECT_PATH,
            "map_package": map_package,
            "city_character": request["city_character"],
            "presentations": request["presentations"],
            "observations_before_save": before_save,
            "observations_reloaded": reloaded,
            "actor_inventory_before": actor_inventory_before,
            "actor_inventory_reloaded": actor_inventory_reloaded,
            "duplicate_hssd_actor_tag_destroyed": DUPLICATE_HSSD_TAG
            if destroyed_path
            else None,
            "destroyed_actor_path": destroyed_path,
            "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            "claims": copy.deepcopy(CLAIMS),
            "gates": gates,
            "error": error,
        }
    )
    publish_result(result_path, result_sidecar, result)
    require(succeeded, "combined City Sample human-demo composition failed")


run()
