"""Author or cold-verify the exact R20 typed upgrade in the copied R6 map.

This script is executed only by the hash-pinned host runner.  Author mode
replaces the four semantic seat proxies, adds the typed liquid actors and
anchors, and replaces the exact legacy fridge proxy/shell with the sealed
three-link articulated actor.  Verify mode starts in a separate UE process and
reconstructs the same inspection from the saved map.  Neither mode launches
PIE, a renderer, a live service, or a network transport.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import PurePosixPath
import re

import unreal


EXECUTION_SCHEMA = "vista.live-scene-upgrade-r20-execution/v1"
WORKER_SCHEMA = "vista.live-scene-upgrade-r20-worker/v1"
SUCCESS_STATUS = "r20_typed_main_map_saved_reloaded_verified"
FAILURE_STATUS = "r20_typed_main_map_quarantined"
EXECUTION_ENV = "VISTA_LIVE_SCENE_UPGRADE_R20_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_LIVE_SCENE_UPGRADE_R20_EXECUTION_SHA256"
MODE_ENV = "VISTA_LIVE_SCENE_UPGRADE_R20_MODE"
AUTHOR_MODE = "author"
VERIFY_MODE = "verify"
ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
MAP_OBJECT_PATH = (
    "/Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome"
)
WORLD_REVISION = "vista_playable_home_r1"
PROFILE_ID = "vista_home_typed_scene_r18"
PROFILE_CONTENT_DIGEST = (
    "2267f918ea41102f8450609171570b35d2a2c7d310b16a574b15202786058666"
)
SEMANTIC_TAG_PREFIX = "VistaSemanticId="
HSSD_TARGET_TAG_PREFIX = "VistaHssdSemanticTargetId="
HSSD_INSTANCE_TAG_PREFIX = "VistaHssdInstanceId="
SEMANTIC_PROP_CLASS = "/Script/VistaPlayableHome.VistaSemanticPropActor"
SEAT_CLASS = "/Script/VistaPlayableHome.VistaSeatActor"
PICKUP_CLASS = "/Script/VistaPlayableHome.VistaPickupActor"
LIQUID_RECEIVER_CLASS = "/Script/VistaPlayableHome.VistaLiquidReceiverActor"
FRIDGE_PROXY_CLASS = "/Script/VistaPlayableHome.VistaContainerActor"
FRIDGE_CLASS = "/Script/VistaPlayableHome.VistaArticulatedFridgeActor"
STATIC_MESH_ACTOR_CLASS = "/Script/Engine.StaticMeshActor"
TARGET_POINT_CLASS = "/Script/Engine.TargetPoint"
FRIDGE_ID = "home.r1/room.kitchen_dining/entity.fridge.01"
WATER_JUG_ID = "home.r1/room.kitchen_dining/entity.water_jug.18"
DRINKING_GLASS_ID = "home.r1/room.kitchen_dining/entity.drinking_glass.18"
SERVING_BOWL_ID = "home.r1/room.kitchen_dining/entity.serving_bowl.18"
SEAT_IDS = (
    "home.r1/room.entry_hall/entity.shoe_bench.01",
    "home.r1/room.living_room/entity.sofa.01",
    "home.r1/room.bedroom/entity.bed.01",
    "home.r1/room.office/entity.rolling_chair.01",
)
EXPECTED_TYPED_IDS = (
    *SEAT_IDS,
    WATER_JUG_ID,
    DRINKING_GLASS_ID,
    SERVING_BOWL_ID,
    FRIDGE_ID,
    *tuple(
        anchor
        for semantic_id in SEAT_IDS
        for anchor in (
            semantic_id + "/anchor.seat_target",
            semantic_id + "/anchor.exit_target",
        )
    ),
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 16 * 1024 * 1024
TREE_ALGORITHM = "sha256-path-nul-mode-size-content-v1"
NEGATIVE_CLAIMS = {
    "accepted_research_evidence": False,
    "ai_or_vlm_data_pipeline_authorized": False,
    "dataset_or_database_authorized": False,
    "gta_level_quality": False,
    "human_motion_quality_accepted": False,
    "photoreal_character_accepted": False,
    "production_authority": False,
    "runtime_interaction_verified": False,
    "visual_quality_accepted": False,
}
LEGAL_SCOPE = {
    "citysample_and_epic_content_human_visual_demo_only": True,
    "external_binary_policy": "outside_git_only",
    "hssd_private_noncommercial_research_only": True,
    "no_external_uasset_redistribution": True,
    "not_for_ai_vlm_training_testing_evaluation_or_review": True,
    "not_for_vista_dataset_or_database": True,
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def duplicate_keys(items):
    result = {}
    for key, value in items:
        require(key not in result, "JSON contains duplicate key " + key)
        result[key] = value
    return result


def reject_constant(token):
    raise RuntimeError("JSON contains non-finite constant " + token)


def canonical_json(value):
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


def content_digest(value):
    body = copy.deepcopy(value)
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value):
    result = copy.deepcopy(value)
    result["content_digest"] = content_digest(result)
    return result


def canonical_path(path):
    return os.path.realpath(os.path.abspath(str(path))).replace("\\", "/")


def sha256_file(path):
    digest = hashlib.sha256()
    observed = 0
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
            observed += len(block)
    return {"sha256": digest.hexdigest(), "size_bytes": observed}


def safe_attempt_file(path, attempt, label, *, must_exist=True):
    candidate = canonical_path(path)
    root = canonical_path(attempt)
    require(candidate.startswith(root + "/"), label + " escaped attempt")
    if must_exist:
        require(
            os.path.isfile(candidate) and not os.path.islink(candidate),
            label + " is missing or symlinked",
        )
    return candidate


def strict_json(path, label, require_canonical=True):
    require(
        os.path.isfile(path) and not os.path.islink(path), label + " is missing"
    )
    raw = open(path, "rb").read()
    require(0 < len(raw) <= MAX_JSON_BYTES, label + " size is invalid")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=duplicate_keys,
            parse_constant=reject_constant,
        )
    except Exception as exc:
        raise RuntimeError(label + " is not strict JSON") from exc
    require(type(value) is dict, label + " root is not an object")
    if require_canonical:
        require(raw == canonical_json(value), label + " is not canonical")
    return value, hashlib.sha256(raw).hexdigest()


def tree_snapshot(root):
    require(os.path.isdir(root) and not os.path.islink(root), "tree root is invalid")
    records = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort()
        files.sort()
        for name in directories:
            path = os.path.join(current, name)
            require(not os.path.islink(path), "tree contains a symlink directory")
        for name in files:
            path = os.path.join(current, name)
            require(
                os.path.isfile(path) and not os.path.islink(path),
                "tree contains an unsafe file",
            )
            relative = os.path.relpath(path, root).replace("\\", "/")
            pure = PurePosixPath(relative)
            require(
                not pure.is_absolute()
                and all(part not in {"", ".", ".."} for part in pure.parts),
                "tree relative path is unsafe",
            )
            metadata = os.stat(path, follow_symlinks=False)
            seal = sha256_file(path)
            records.append(
                (
                    relative,
                    metadata.st_mode & 0o7777,
                    seal["size_bytes"],
                    seal["sha256"],
                )
            )
    require(records, "tree contains no files")
    raw = b"".join(
        (
            "%s\0%o\0%d\0%s\n" % (relative, mode, size, digest)
        ).encode("utf-8")
        for relative, mode, size, digest in records
    )
    return {
        "algorithm": TREE_ALGORITHM,
        "tree_sha256": hashlib.sha256(raw).hexdigest(),
        "file_count": len(records),
        "total_bytes": sum(record[2] for record in records),
    }


def validate_tree(binding, label):
    require(
        set(binding)
        == {"root", "algorithm", "tree_sha256", "file_count", "total_bytes"},
        label + " tree fields differ",
    )
    root = canonical_path(binding["root"])
    observed = tree_snapshot(root)
    require(
        observed
        == {
            "algorithm": binding["algorithm"],
            "tree_sha256": binding["tree_sha256"],
            "file_count": binding["file_count"],
            "total_bytes": binding["total_bytes"],
        },
        label + " tree differs",
    )


def validate_file(binding, attempt, label):
    require(
        set(binding) == {"path", "sha256", "size_bytes"},
        label + " fields differ",
    )
    path = safe_attempt_file(binding["path"], attempt, label)
    seal = sha256_file(path)
    require(
        seal == {"sha256": binding["sha256"], "size_bytes": binding["size_bytes"]},
        label + " bytes differ",
    )
    return path


def load_execution():
    path = canonical_path(os.environ.get(EXECUTION_ENV, ""))
    expected_sha = os.environ.get(EXECUTION_SHA_ENV, "")
    mode = os.environ.get(MODE_ENV, "")
    require(SHA256_RE.fullmatch(expected_sha or "") is not None, "execution SHA is invalid")
    require(mode in {AUTHOR_MODE, VERIFY_MODE}, "execution mode is invalid")
    value, observed_sha = strict_json(path, "R20 execution")
    require(observed_sha == expected_sha, "execution SHA differs")
    require(
        set(value)
        == {
            "schema_version",
            "acknowledgement",
            "engine_version",
            "attempt_root",
            "project",
            "typed_profile",
            "compiled_plugin",
            "overlays",
            "fridge_binding",
            "ycb_mesh_bindings",
            "commandlet",
            "outputs",
            "policy",
            "claims",
            "legal_scope",
            "content_digest",
        }
        and value["schema_version"] == EXECUTION_SCHEMA
        and value["content_digest"] == content_digest(value)
        and value["engine_version"] == ENGINE_VERSION
        and value["claims"] == NEGATIVE_CLAIMS
        and value["legal_scope"] == LEGAL_SCOPE,
        "R20 execution identity differs",
    )
    attempt = canonical_path(value["attempt_root"])
    require(path == attempt + "/inputs/r20-live-scene-upgrade-execution.json", "execution path differs")
    require(
        value["policy"]
        == {
            "append_only_attempt": True,
            "source_r6_read_only": True,
            "main_map_only": True,
            "save_reload_required": True,
            "separate_cold_verify_process": True,
            "network_isolated": True,
            "live_services_mutated": False,
            "external_binary_assets_outside_git": True,
            "accepted": False,
        },
        "execution policy differs",
    )
    commandlet = value["commandlet"]
    require(
        canonical_path(commandlet["path"]) == canonical_path(__file__)
        and sha256_file(__file__)
        == {
            "sha256": commandlet["sha256"],
            "size_bytes": commandlet["size_bytes"],
        },
        "fixed commandlet identity differs",
    )
    project = value["project"]
    project_file = safe_attempt_file(project["file"], attempt, "project descriptor")
    require(
        canonical_path(unreal.Paths.get_project_file_path()) == project_file
        and sha256_file(project_file)["sha256"] == project["descriptor_sha256"],
        "loaded project differs",
    )
    require(
        str(unreal.SystemLibrary.get_engine_version()) == ENGINE_VERSION,
        "loaded engine version differs",
    )
    map_file = safe_attempt_file(project["map_file"], attempt, "main map")
    require(project["map_object_path"] == MAP_OBJECT_PATH, "main map object path differs")
    profile_path = validate_file(
        {
            key: value["typed_profile"][key]
            for key in ("path", "sha256", "size_bytes")
        },
        attempt,
        "typed profile",
    )
    profile, _ = strict_json(
        profile_path, "typed profile", require_canonical=False
    )
    require(
        value["typed_profile"]["profile_id"] == PROFILE_ID
        and value["typed_profile"]["content_digest"] == PROFILE_CONTENT_DIGEST
        and profile.get("profile_id") == PROFILE_ID
        and profile.get("content_digest") == PROFILE_CONTENT_DIGEST
        and profile.get("content_digest") == content_digest(profile)
        and profile.get("runtime_acceptance") is False,
        "typed profile binding differs",
    )
    validate_tree(value["compiled_plugin"], "compiled plugin")
    expected_roles = {"r8", "r14", "r15", "manny_r18", "fridge"}
    require(set(value["overlays"]) == expected_roles, "overlay roles differ")
    for role, binding in value["overlays"].items():
        require(
            set(binding) == {"tree", "namespace", "inventory", "receipt"},
            role + " overlay fields differ",
        )
        validate_tree(binding["tree"], role + " overlay")
        validate_file(binding["receipt"], attempt, role + " receipt")
        require(type(binding["inventory"]) is list and binding["inventory"], role + " inventory is empty")
    outputs = value["outputs"]
    require(set(outputs) == {"author", "verify"}, "worker output fields differ")
    for output_mode, output_path in outputs.items():
        candidate = safe_attempt_file(
            output_path,
            attempt,
            output_mode + " output",
            must_exist=(mode == VERIFY_MODE and output_mode == AUTHOR_MODE),
        )
        if mode == AUTHOR_MODE or output_mode == VERIFY_MODE:
            require(not os.path.lexists(candidate), output_mode + " output already exists")
    return value, path, expected_sha, mode, profile, map_file


def write_exclusive(path, attempt, value):
    output = safe_attempt_file(path, attempt, "worker output", must_exist=False)
    require(os.path.dirname(output) == canonical_path(attempt) + "/evidence", "worker output directory differs")
    raw = canonical_json(value)
    descriptor = os.open(
        output,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def normalized(value):
    result = round(float(value), 5)
    return 0.0 if result == -0.0 else result


def normalized_angle(value):
    return normalized((float(value) + 180.0) % 360.0 - 180.0)


def vector(values):
    return unreal.Vector(x=values[0], y=values[1], z=values[2])


def rotation(values):
    return unreal.Rotator(pitch=values[1], yaw=values[2], roll=values[0])


def transform_record(actor):
    location = actor.get_actor_location()
    observed_rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return {
        "location_cm": [normalized(location.x), normalized(location.y), normalized(location.z)],
        "rotation_deg": [
            normalized_angle(observed_rotation.roll),
            normalized_angle(observed_rotation.pitch),
            normalized_angle(observed_rotation.yaw),
        ],
        "scale": [normalized(scale.x), normalized(scale.y), normalized(scale.z)],
    }


def relative_transform_record(component):
    location = component.get_editor_property("relative_location")
    observed_rotation = component.get_editor_property("relative_rotation")
    scale = component.get_editor_property("relative_scale3d")
    return {
        "location_cm": [normalized(location.x), normalized(location.y), normalized(location.z)],
        "rotation_deg": [
            normalized_angle(observed_rotation.roll),
            normalized_angle(observed_rotation.pitch),
            normalized_angle(observed_rotation.yaw),
        ],
        "scale": [normalized(scale.x), normalized(scale.y), normalized(scale.z)],
    }


def set_relative_transform(component, value):
    component.set_editor_property("relative_location", vector(value["location_cm"]))
    component.set_editor_property("relative_rotation", rotation(value["rotation_deg"]))
    component.set_editor_property("relative_scale3d", vector(value["scale"]))


def class_path(value):
    reflected = value.get_class() if value is not None else None
    return str(reflected.get_path_name()) if reflected is not None else ""


def tags(actor):
    return sorted(str(tag) for tag in actor.get_editor_property("tags"))


def set_tags(actor, values):
    actor.set_editor_property("tags", [unreal.Name(value) for value in sorted(set(values))])


def safe_label(value):
    return "VISTA_R20_" + re.sub(r"[^A-Za-z0-9_]", "_", value)


def semantic_ids(actor):
    return [tag[len(SEMANTIC_TAG_PREFIX) :] for tag in tags(actor) if tag.startswith(SEMANTIC_TAG_PREFIX)]


def actors_with_tag(actors, exact_tag):
    return [actor for actor in actors if exact_tag in tags(actor)]


def one_actor_with_tag(actors, exact_tag, label):
    matches = actors_with_tag(actors, exact_tag)
    require(len(matches) == 1, label + " actor count differs")
    return matches[0]


def mesh_component(actor, property_name="mesh"):
    try:
        component = actor.get_editor_property(property_name)
        if isinstance(component, unreal.StaticMeshComponent):
            return component
    except Exception:
        pass
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    require(len(components) == 1, "actor static-mesh component count differs")
    return components[0]


def mesh_snapshot(component):
    mesh = component.get_editor_property("static_mesh")
    return {
        "component_path": str(component.get_path_name()),
        "mesh_path": str(mesh.get_path_name()) if mesh is not None else "",
        "relative_transform": relative_transform_record(component),
        "collision_profile": str(component.get_collision_profile_name()),
        "collision_enabled": str(component.get_collision_enabled()),
        "simulate_physics": bool(component.is_simulating_physics()),
        "generate_overlap_events": bool(component.get_editor_property("generate_overlap_events")),
        "can_ever_affect_navigation": bool(component.get_editor_property("can_ever_affect_navigation")),
        "mobility": str(component.get_editor_property("mobility")),
        "visible": bool(component.get_editor_property("visible")),
    }


def actor_snapshot(actor, *, mesh=None):
    hidden = actor.get_editor_property("hidden")
    require(type(hidden) is bool, "actor hidden state is unavailable")
    result = {
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "actor_class_path": class_path(actor),
        "actor_hidden_in_game": hidden,
        "actor_collision_enabled": bool(actor.get_actor_enable_collision()),
        "world_transform_cm": transform_record(actor),
        "tags": tags(actor),
    }
    if mesh is not None:
        result["mesh"] = mesh_snapshot(mesh)
    return result


def copy_mesh_presentation(source, target):
    static_mesh = source.get_editor_property("static_mesh")
    require(static_mesh is not None, "source semantic mesh is absent")
    target.set_static_mesh(static_mesh)
    set_relative_transform(target, relative_transform_record(source))
    target.set_collision_profile_name(source.get_collision_profile_name())
    target.set_collision_enabled(source.get_collision_enabled())
    target.set_simulate_physics(source.is_simulating_physics())
    target.set_editor_property(
        "generate_overlap_events",
        bool(source.get_editor_property("generate_overlap_events")),
    )
    target.set_editor_property(
        "can_ever_affect_navigation",
        bool(source.get_editor_property("can_ever_affect_navigation")),
    )
    target.set_mobility(source.get_editor_property("mobility"))
    target.set_visibility(bool(source.get_editor_property("visible")), True)


def spawn_like(actor_subsystem, actor_class, source_actor, label):
    actor = actor_subsystem.spawn_actor_from_class(
        actor_class,
        source_actor.get_actor_location(),
        source_actor.get_actor_rotation(),
        transient=False,
    )
    require(actor is not None, "failed to spawn " + label)
    actor.set_actor_scale3d(source_actor.get_actor_scale3d())
    actor.set_actor_label(label)
    return actor


def spawn_at(actor_subsystem, actor_class, value, label):
    actor = actor_subsystem.spawn_actor_from_class(
        actor_class,
        vector(value["location_cm"]),
        rotation(value["rotation_deg"]),
        transient=False,
    )
    require(actor is not None, "failed to spawn " + label)
    actor.set_actor_scale3d(vector(value["scale"]))
    actor.set_actor_label(label)
    return actor


def set_semantic(actor, semantic_id, affordances):
    actor.set_editor_property("semantic_id", semantic_id)
    actor.set_editor_property("world_revision", unreal.Name(WORLD_REVISION))
    actor.set_editor_property("allowed_affordances", affordances)


def exact_transform(value):
    return {
        "location_cm": [normalized(item) for item in value["location_cm"]],
        "rotation_deg": [normalized_angle(item) for item in value["rotation_deg"]],
        "scale": [normalized(item) for item in value["scale"]],
    }


def validate_registry(actors, *, require_new):
    registry = {}
    for actor in actors:
        ids = semantic_ids(actor)
        require(len(ids) <= 1, "actor contains multiple stable semantic IDs")
        if ids:
            registry.setdefault(ids[0], []).append(str(actor.get_path_name()))
    duplicates = sorted(key for key, values in registry.items() if len(values) != 1)
    require(not duplicates, "map contains duplicate semantic IDs")
    if require_new:
        require(set(EXPECTED_TYPED_IDS).issubset(registry), "typed semantic registry is incomplete")
    else:
        new_only = set(EXPECTED_TYPED_IDS) - set(SEAT_IDS) - {FRIDGE_ID}
        require(not (new_only & set(registry)), "fresh typed semantic IDs already exist")
    return registry


def validate_legacy_fridge(actor, expected, role):
    snapshot = actor_snapshot(actor, mesh=mesh_component(actor))
    require(
        snapshot["actor_path"] == expected["actor_path"]
        and snapshot["actor_label"] == expected["actor_label"]
        and snapshot["actor_class_path"] == expected["actor_class_path"]
        and snapshot["actor_hidden_in_game"] == expected["actor_hidden_in_game"]
        and snapshot["actor_collision_enabled"] == expected["actor_collision_enabled"]
        and snapshot["world_transform_cm"] == exact_transform(expected["world_transform_cm"])
        and snapshot["tags"] == sorted(expected["tags"]),
        "legacy fridge " + role + " identity differs",
    )
    expected_mesh = expected.get("component_mesh_path", expected.get("mesh_path"))
    require(snapshot["mesh"]["mesh_path"] == expected_mesh, "legacy fridge " + role + " mesh differs")
    return snapshot


def author_seats(actor_subsystem, actors, profile):
    seat_class = unreal.load_class(None, SEAT_CLASS)
    require(seat_class is not None, "AVistaSeatActor class is unavailable")
    lineage = []
    for binding in profile["seat_bindings"]:
        semantic_id = binding["entity_id"]
        old = one_actor_with_tag(
            actors, SEMANTIC_TAG_PREFIX + semantic_id, "legacy seat " + semantic_id
        )
        require(class_path(old) == SEMANTIC_PROP_CLASS, "legacy seat class differs")
        old_mesh = mesh_component(old)
        old_snapshot = actor_snapshot(old, mesh=old_mesh)
        shells = actors_with_tag(actors, HSSD_TARGET_TAG_PREFIX + semantic_id)
        require(
            len(shells) == 1 and class_path(shells[0]) == STATIC_MESH_ACTOR_CLASS,
            "seat HSSD shell binding differs",
        )
        shell_snapshot = actor_snapshot(shells[0], mesh=mesh_component(shells[0]))
        new = spawn_like(actor_subsystem, seat_class, old, safe_label(semantic_id))
        set_tags(
            new,
            old_snapshot["tags"]
            + ["VistaTypedRole=seat", "VistaAccepted=false"],
        )
        set_semantic(
            new,
            semantic_id,
            [
                unreal.VistaAffordance.INSPECT,
                unreal.VistaAffordance.SIT,
                unreal.VistaAffordance.STAND,
            ],
        )
        new.set_actor_hidden_in_game(old_snapshot["actor_hidden_in_game"])
        new.set_actor_enable_collision(old_snapshot["actor_collision_enabled"])
        copy_mesh_presentation(old_mesh, mesh_component(new))
        seat_target = new.get_editor_property("seat_target")
        set_relative_transform(seat_target, binding["interaction_target_local_cm"])
        anchors = []
        for role, key, suffix in (
            ("seat_interaction", "interaction_target_local_cm", "seat_target"),
            ("seat_exit", "exit_target_local_cm", "exit_target"),
        ):
            anchor_id = semantic_id + "/anchor." + suffix
            anchor = actor_subsystem.spawn_actor_from_class(
                unreal.TargetPoint,
                new.get_actor_location(),
                new.get_actor_rotation(),
                transient=False,
            )
            require(anchor is not None, "failed to spawn seat anchor")
            anchor.set_actor_label(safe_label(anchor_id))
            set_tags(
                anchor,
                [
                    SEMANTIC_TAG_PREFIX + anchor_id,
                    "VistaTypedRole=seat_anchor",
                    "VistaAnchorRole=" + role,
                    "VistaAnchorOwner=" + semantic_id,
                    "VistaAccepted=false",
                ],
            )
            root = anchor.get_editor_property("root_component")
            root.set_mobility(unreal.ComponentMobility.MOVABLE)
            anchor.attach_to_actor(
                new,
                unreal.Name(),
                unreal.AttachmentRule.KEEP_WORLD,
                unreal.AttachmentRule.KEEP_WORLD,
                unreal.AttachmentRule.KEEP_WORLD,
                False,
            )
            set_relative_transform(root, binding[key])
            anchors.append(anchor_id)
        old_path = str(old.get_path_name())
        require(actor_subsystem.destroy_actor(old), "failed to destroy legacy seat")
        lineage.append(
            {
                "semantic_id": semantic_id,
                "old_authority": old_snapshot,
                "preserved_hssd_shell": shell_snapshot,
                "new_authority_path": str(new.get_path_name()),
                "anchor_ids": anchors,
                "old_authority_path": old_path,
            }
        )
    return lineage


def author_liquids(actor_subsystem, profile, mesh_bindings):
    pickup_class = unreal.load_class(None, PICKUP_CLASS)
    receiver_class = unreal.load_class(None, LIQUID_RECEIVER_CLASS)
    require(pickup_class is not None and receiver_class is not None, "typed liquid classes unavailable")
    source = profile["liquid_sources"][0]
    source_actor = spawn_at(
        actor_subsystem,
        pickup_class,
        source["world_transform_cm"],
        safe_label(source["semantic_id"]),
    )
    source_binding = mesh_bindings[source["semantic_id"]]
    source_mesh = unreal.load_asset(source_binding["object_path"])
    require(isinstance(source_mesh, unreal.StaticMesh), "water-jug proxy mesh unavailable")
    mesh_component(source_actor).set_static_mesh(source_mesh)
    set_tags(
        source_actor,
        [
            SEMANTIC_TAG_PREFIX + source["semantic_id"],
            "VistaTypedRole=liquid_source",
            "VistaVisualBinding=r18.visual.kitchen.water_jug",
            "VistaVisualProxyUnaccepted=true",
            "VistaVisualDisposition=" + source_binding["visual_disposition"],
            "VistaAccepted=false",
        ],
    )
    set_semantic(
        source_actor,
        source["semantic_id"],
        [
            unreal.VistaAffordance.PICK_UP,
            unreal.VistaAffordance.DROP,
            unreal.VistaAffordance.PLACE,
            unreal.VistaAffordance.INSPECT,
            unreal.VistaAffordance.POUR,
        ],
    )
    source_actor.set_editor_property("portable", True)
    source_actor.set_editor_property("pourable", True)
    source_actor.set_editor_property("liquid_capacity_milliliters", float(source["capacity_ml"]))
    source_actor.set_editor_property("initial_liquid_level", float(source["initial_level"]))
    source_actor.set_editor_property("initial_liquid_type", unreal.Name(source["liquid_type"]))

    for receiver in profile["liquid_receivers"]:
        actor = spawn_at(
            actor_subsystem,
            receiver_class,
            receiver["world_transform_cm"],
            safe_label(receiver["semantic_id"]),
        )
        binding = mesh_bindings[receiver["semantic_id"]]
        mesh = unreal.load_asset(binding["object_path"])
        require(isinstance(mesh, unreal.StaticMesh), "receiver mesh unavailable")
        component = mesh_component(actor)
        component.set_static_mesh(mesh)
        component.set_collision_profile_name(unreal.Name("BlockAllDynamic"))
        component.set_simulate_physics(False)
        component.set_mobility(unreal.ComponentMobility.MOVABLE)
        set_tags(
            actor,
            [
                SEMANTIC_TAG_PREFIX + receiver["semantic_id"],
                "VistaTypedRole=liquid_receiver",
                "VistaReceiverKind=" + receiver["receiver_kind"],
                "VistaVisualProxyUnaccepted=true",
                "VistaVisualDisposition=" + binding["visual_disposition"],
                "VistaAccepted=false",
            ],
        )
        set_semantic(
            actor,
            receiver["semantic_id"],
            [unreal.VistaAffordance.INSPECT, unreal.VistaAffordance.POUR],
        )
        actor.set_editor_property("receiver_kind", unreal.Name(receiver["receiver_kind"]))
        actor.set_editor_property("accepted_liquid_type", unreal.Name(receiver["accepted_liquid_type"]))
        actor.set_editor_property("capacity_milliliters", float(receiver["capacity_ml"]))
        actor.set_editor_property("initial_liquid_level", float(receiver["initial_level"]))
        actor.set_editor_property("initial_liquid_type", unreal.Name("None"))
        set_relative_transform(
            actor.get_editor_property("pour_target"),
            receiver["pour_target_local_cm"],
        )


def author_fridge(actor_subsystem, actors, binding):
    legacy = binding["legacy"]
    expected_proxy = legacy["proxy"]
    expected_shell = legacy["shell"]
    proxy = one_actor_with_tag(
        actors, SEMANTIC_TAG_PREFIX + FRIDGE_ID, "legacy fridge proxy"
    )
    shell = one_actor_with_tag(
        actors,
        HSSD_INSTANCE_TAG_PREFIX + "hssd.r1/kitchen_dining.fridge.01",
        "legacy fridge shell",
    )
    require(class_path(proxy) == FRIDGE_PROXY_CLASS, "legacy fridge proxy class differs")
    require(class_path(shell) == STATIC_MESH_ACTOR_CLASS, "legacy fridge shell class differs")
    proxy_snapshot = validate_legacy_fridge(proxy, expected_proxy, "proxy")
    shell_snapshot = validate_legacy_fridge(shell, expected_shell, "shell")
    require(
        proxy_snapshot["world_transform_cm"] == shell_snapshot["world_transform_cm"],
        "legacy fridge proxy/shell transforms differ",
    )
    fridge_class = unreal.load_class(None, FRIDGE_CLASS)
    require(fridge_class is not None, "AVistaArticulatedFridgeActor is unavailable")
    actor = spawn_like(actor_subsystem, fridge_class, proxy, "VISTA_R20_ARTICULATED_FRIDGE")
    source_actor = binding["articulated_actor"]
    assets = {}
    for item in binding["imported_assets"]:
        asset = unreal.load_asset(item["object_path"])
        require(isinstance(asset, unreal.StaticMesh), "fridge link mesh unavailable")
        assets[item["role"]] = asset
    require(set(assets) == {"body", "primary_door", "secondary_door"}, "fridge links differ")
    components = {
        "body": actor.get_editor_property("body_mesh"),
        "primary_door": actor.get_editor_property("primary_door_mesh"),
        "secondary_door": actor.get_editor_property("secondary_door_mesh"),
    }
    for role, component in components.items():
        component.set_static_mesh(assets[role])
        component.set_collision_profile_name(unreal.Name("BlockAllDynamic"))
        component.set_simulate_physics(False)
        component.set_editor_property("generate_overlap_events", True)
        component.set_editor_property("can_ever_affect_navigation", role == "body")
        set_relative_transform(component, source_actor["meshes"][role]["relative_transform"])
    set_relative_transform(
        actor.get_editor_property("primary_hinge"),
        source_actor["hinges"]["primary_hinge"],
    )
    set_relative_transform(
        actor.get_editor_property("secondary_hinge"),
        source_actor["hinges"]["secondary_hinge"],
    )
    actor.get_editor_property("handle_target").set_editor_property(
        "relative_location", vector(source_actor["handle_relative_location_cm"])
    )
    actor.set_editor_property("open_angle_degrees", float(source_actor["open_angle_deg"]))
    actor.set_editor_property("angular_speed_degrees", float(source_actor["angular_speed_deg_s"]))
    actor.set_editor_property("receptacle_count", int(source_actor["receptacle_count"]))
    actor.set_editor_property("initially_open", False)
    set_semantic(
        actor,
        FRIDGE_ID,
        [
            unreal.VistaAffordance.OPEN,
            unreal.VistaAffordance.CLOSE,
            unreal.VistaAffordance.INSPECT,
        ],
    )
    lineage_tags = [
        SEMANTIC_TAG_PREFIX + FRIDGE_ID,
        "VistaRole=articulated_fridge",
        "VistaTypedRole=articulated_fridge",
        "VistaHssdInstanceId=hssd.r1/kitchen_dining.fridge.01",
        "VistaHssdSourceAssetId=hssd.static.fridge",
        "VistaHssdLegacyShellLineagePreserved=true",
        "VistaAccepted=false",
    ]
    set_tags(actor, lineage_tags)
    actor.set_actor_hidden_in_game(False)
    actor.set_actor_enable_collision(True)
    old_paths = [str(proxy.get_path_name()), str(shell.get_path_name())]
    require(actor_subsystem.destroy_actor(proxy), "failed to remove legacy fridge proxy")
    require(actor_subsystem.destroy_actor(shell), "failed to remove legacy fridge shell")
    return {
        "semantic_id": FRIDGE_ID,
        "old_proxy": proxy_snapshot,
        "old_hssd_shell": shell_snapshot,
        "old_authority_paths": old_paths,
        "new_authority_path": str(actor.get_path_name()),
        "lineage_tags": sorted(lineage_tags),
    }


def asset_inventory(execution):
    result = []
    for role, binding in sorted(execution["overlays"].items()):
        for expected in binding["inventory"]:
            asset = unreal.load_asset(expected["object_path"])
            require(asset is not None, "overlay asset unavailable: " + expected["object_path"])
            observed_class = class_path(asset)
            require(observed_class == expected["class_path"], "overlay asset class differs")
            result.append(
                {
                    "overlay_role": role,
                    "object_path": expected["object_path"],
                    "class_path": observed_class,
                }
            )
    for semantic_id, binding in sorted(execution["ycb_mesh_bindings"].items()):
        asset = unreal.load_asset(binding["object_path"])
        require(isinstance(asset, unreal.StaticMesh), "YCB binding is not a StaticMesh")
        result.append(
            {
                "overlay_role": "r6_ycb_visual",
                "semantic_id": semantic_id,
                "object_path": binding["object_path"],
                "class_path": class_path(asset),
                "visual_proxy_accepted": binding["visual_proxy_accepted"],
                "visual_disposition": binding["visual_disposition"],
            }
        )
    return result


def inspect_world(execution, profile, lineage, map_file):
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = actor_subsystem.get_all_level_actors()
    registry = validate_registry(actors, require_new=True)
    old_paths = {
        item["old_authority_path"] for item in lineage["seats"]
    } | set(lineage["fridge"]["old_authority_paths"])
    observed_paths = {str(actor.get_path_name()) for actor in actors}
    require(not (old_paths & observed_paths), "old authority path survived")
    seats = []
    shell_preserved = True
    seat_binding_by_id = {
        item["entity_id"]: item for item in profile["seat_bindings"]
    }
    lineage_by_id = {item["semantic_id"]: item for item in lineage["seats"]}
    for semantic_id in SEAT_IDS:
        actor = one_actor_with_tag(actors, SEMANTIC_TAG_PREFIX + semantic_id, "typed seat")
        require(class_path(actor) == SEAT_CLASS, "typed seat class differs")
        binding = seat_binding_by_id[semantic_id]
        seat_target = actor.get_editor_property("seat_target")
        require(
            relative_transform_record(seat_target)
            == exact_transform(binding["interaction_target_local_cm"]),
            "typed seat target differs",
        )
        anchors = []
        for suffix, key in (
            ("seat_target", "interaction_target_local_cm"),
            ("exit_target", "exit_target_local_cm"),
        ):
            anchor_id = semantic_id + "/anchor." + suffix
            anchor = one_actor_with_tag(actors, SEMANTIC_TAG_PREFIX + anchor_id, "seat anchor")
            require(class_path(anchor) == TARGET_POINT_CLASS, "seat anchor class differs")
            root = anchor.get_editor_property("root_component")
            parent = root.get_editor_property("attach_parent")
            require(
                parent is not None
                and str(parent.get_owner().get_path_name()) == str(actor.get_path_name())
                and relative_transform_record(root) == exact_transform(binding[key]),
                "seat anchor transform/owner differs",
            )
            anchors.append(
                {
                    "semantic_id": anchor_id,
                    "actor_path": str(anchor.get_path_name()),
                    "actor_class_path": class_path(anchor),
                    "owner_actor_path": str(actor.get_path_name()),
                    "relative_transform": relative_transform_record(root),
                }
            )
        shell = one_actor_with_tag(actors, HSSD_TARGET_TAG_PREFIX + semantic_id, "seat shell")
        observed_shell = actor_snapshot(shell, mesh=mesh_component(shell))
        expected_shell = lineage_by_id[semantic_id]["preserved_hssd_shell"]
        shell_preserved = shell_preserved and observed_shell == expected_shell
        old_mesh = lineage_by_id[semantic_id]["old_authority"]["mesh"]
        current_mesh = mesh_snapshot(mesh_component(actor))
        current_actor = actor_snapshot(actor, mesh=mesh_component(actor))
        old_actor = lineage_by_id[semantic_id]["old_authority"]
        require(
            current_actor["world_transform_cm"]
            == old_actor["world_transform_cm"]
            and current_actor["actor_hidden_in_game"]
            == old_actor["actor_hidden_in_game"]
            and current_actor["actor_collision_enabled"]
            == old_actor["actor_collision_enabled"]
            and current_mesh["mesh_path"] == old_mesh["mesh_path"]
            and current_mesh["relative_transform"] == old_mesh["relative_transform"]
            and current_mesh["collision_profile"] == old_mesh["collision_profile"]
            and current_mesh["collision_enabled"] == old_mesh["collision_enabled"]
            and current_mesh["simulate_physics"] == old_mesh["simulate_physics"]
            and current_mesh["generate_overlap_events"] == old_mesh["generate_overlap_events"]
            and current_mesh["can_ever_affect_navigation"]
            == old_mesh["can_ever_affect_navigation"]
            and current_mesh["mobility"] == old_mesh["mobility"]
            and current_mesh["visible"] == old_mesh["visible"],
            "typed seat mesh/collision presentation relation differs",
        )
        seats.append(
            {
                "semantic_id": semantic_id,
                "actor": current_actor,
                "seat_target_relative": relative_transform_record(seat_target),
                "anchors": anchors,
                "preserved_hssd_shell": observed_shell,
            }
        )
    require(shell_preserved, "seat HSSD shells changed")

    liquids = []
    profile_liquids = {
        profile["liquid_sources"][0]["semantic_id"]: profile["liquid_sources"][0],
        **{item["semantic_id"]: item for item in profile["liquid_receivers"]},
    }
    for semantic_id, expected_class in (
        (WATER_JUG_ID, PICKUP_CLASS),
        (DRINKING_GLASS_ID, LIQUID_RECEIVER_CLASS),
        (SERVING_BOWL_ID, LIQUID_RECEIVER_CLASS),
    ):
        actor = one_actor_with_tag(actors, SEMANTIC_TAG_PREFIX + semantic_id, "typed liquid")
        require(class_path(actor) == expected_class, "typed liquid class differs")
        binding = execution["ycb_mesh_bindings"][semantic_id]
        expected_liquid = profile_liquids[semantic_id]
        require(
            transform_record(actor)
            == exact_transform(expected_liquid["world_transform_cm"])
            and mesh_snapshot(mesh_component(actor))["mesh_path"]
            == binding["object_path"]
            and "VistaVisualProxyUnaccepted=true" in tags(actor),
            "typed liquid visual binding differs",
        )
        item = {
            "semantic_id": semantic_id,
            "actor": actor_snapshot(actor, mesh=mesh_component(actor)),
            "visual_binding": copy.deepcopy(binding),
        }
        if semantic_id != WATER_JUG_ID:
            pour_target = actor.get_editor_property("pour_target")
            require(
                relative_transform_record(pour_target)
                == exact_transform(profile_liquids[semantic_id]["pour_target_local_cm"]),
                "receiver pour target differs",
            )
            item["pour_target_relative"] = relative_transform_record(pour_target)
            require(
                str(actor.get_editor_property("receiver_kind"))
                == expected_liquid["receiver_kind"]
                and str(actor.get_editor_property("accepted_liquid_type"))
                == expected_liquid["accepted_liquid_type"]
                and normalized(actor.get_editor_property("capacity_milliliters"))
                == normalized(expected_liquid["capacity_ml"]),
                "typed receiver liquid properties differ",
            )
        else:
            require(
                bool(actor.get_editor_property("pourable")) is True
                and normalized(
                    actor.get_editor_property("liquid_capacity_milliliters")
                )
                == normalized(expected_liquid["capacity_ml"])
                and normalized(actor.get_editor_property("initial_liquid_level"))
                == normalized(expected_liquid["initial_level"])
                and str(actor.get_editor_property("initial_liquid_type"))
                == expected_liquid["liquid_type"],
                "typed source liquid properties differ",
            )
        liquids.append(item)

    fridge = one_actor_with_tag(actors, SEMANTIC_TAG_PREFIX + FRIDGE_ID, "typed fridge")
    require(class_path(fridge) == FRIDGE_CLASS, "typed fridge class differs")
    fridge_tags = tags(fridge)
    require(
        "VistaHssdInstanceId=hssd.r1/kitchen_dining.fridge.01" in fridge_tags
        and "VistaHssdSourceAssetId=hssd.static.fridge" in fridge_tags
        and "VistaHssdLegacyShellLineagePreserved=true" in fridge_tags,
        "fridge HSSD lineage tags differ",
    )
    expected_fridge_assets = {
        item["role"]: item["object_path"]
        for item in execution["fridge_binding"]["imported_assets"]
    }
    fridge_meshes = {
        "body": mesh_snapshot(fridge.get_editor_property("body_mesh")),
        "primary_door": mesh_snapshot(fridge.get_editor_property("primary_door_mesh")),
        "secondary_door": mesh_snapshot(fridge.get_editor_property("secondary_door_mesh")),
    }
    require(
        transform_record(fridge)
        == lineage["fridge"]["old_proxy"]["world_transform_cm"]
        and all(
            fridge_meshes[role]["mesh_path"] == path
            for role, path in expected_fridge_assets.items()
        )
        and all(
            fridge_meshes[role]["relative_transform"]
            == exact_transform(
                execution["fridge_binding"]["articulated_actor"]["meshes"][role][
                    "relative_transform"
                ]
            )
            for role in expected_fridge_assets
        ),
        "fridge articulated mesh bindings differ",
    )
    map_seal = sha256_file(map_file)
    return {
        "map": {
            "object_path": MAP_OBJECT_PATH,
            "package_file": map_file,
            "package_sha256": map_seal["sha256"],
            "package_size_bytes": map_seal["size_bytes"],
        },
        "replacement_lineage": copy.deepcopy(lineage),
        "semantic_registry": {
            "expected_typed_ids": sorted(EXPECTED_TYPED_IDS),
            "typed_actor_paths": {
                semantic_id: registry[semantic_id][0]
                for semantic_id in sorted(EXPECTED_TYPED_IDS)
            },
            "duplicate_semantic_ids": [],
            "old_authority_paths": sorted(old_paths),
        },
        "seats": sorted(seats, key=lambda item: item["semantic_id"]),
        "liquids": sorted(liquids, key=lambda item: item["semantic_id"]),
        "fridge": {
            "semantic_id": FRIDGE_ID,
            "actor": actor_snapshot(fridge),
            "meshes": fridge_meshes,
            "lineage": copy.deepcopy(lineage["fridge"]),
        },
        "asset_inventory": asset_inventory(execution),
        "gates": {
            "exact_classes_and_semantic_ids": True,
            "exact_anchor_transforms": True,
            "exact_mesh_bindings": True,
            "old_authorities_absent": True,
            "duplicate_semantic_ids_absent": True,
            "seat_hssd_shells_preserved": shell_preserved,
            "fridge_hssd_lineage_preserved": True,
            "map_saved_reloaded": True,
        },
    }


def load_author_lineage(execution, attempt, execution_sha):
    receipt, _ = strict_json(execution["outputs"]["author"], "author receipt")
    require(
        receipt.get("schema_version") == WORKER_SCHEMA
        and receipt.get("mode") == AUTHOR_MODE
        and receipt.get("status") == SUCCESS_STATUS
        and receipt.get("execution_sha256") == execution_sha
        and receipt.get("content_digest") == content_digest(receipt)
        and receipt.get("error") is None,
        "author receipt cannot authorize cold verification",
    )
    safe_attempt_file(execution["outputs"]["author"], attempt, "author receipt")
    return receipt["inspection"]["replacement_lineage"]


def run():
    execution = None
    execution_sha = os.environ.get(EXECUTION_SHA_ENV, "")
    mode = os.environ.get(MODE_ENV, "")
    attempt = ""
    output = ""
    try:
        execution, _, execution_sha, mode, profile, map_file = load_execution()
        attempt = canonical_path(execution["attempt_root"])
        output = execution["outputs"][mode]
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        require(level_subsystem.load_level(MAP_OBJECT_PATH), "failed to load exact main map")
        actors = actor_subsystem.get_all_level_actors()
        if mode == AUTHOR_MODE:
            require(
                sha256_file(map_file)
                == {
                    "sha256": execution["project"]["source_map_sha256"],
                    "size_bytes": execution["project"]["source_map_size_bytes"],
                },
                "author source map bytes differ",
            )
            validate_registry(actors, require_new=False)
            seat_lineage = author_seats(actor_subsystem, actors, profile)
            author_liquids(actor_subsystem, profile, execution["ycb_mesh_bindings"])
            fridge_lineage = author_fridge(
                actor_subsystem, actors, execution["fridge_binding"]
            )
            lineage = {"seats": seat_lineage, "fridge": fridge_lineage}
            world = unreal.EditorLevelLibrary.get_editor_world()
            require(world is not None, "main map world is unavailable")
            require(
                unreal.EditorLoadingAndSavingUtils.save_map(world, MAP_OBJECT_PATH),
                "failed to save upgraded main map",
            )
            require(level_subsystem.load_level(MAP_OBJECT_PATH), "failed to reload saved main map")
        else:
            lineage = load_author_lineage(execution, attempt, execution_sha)
            require(level_subsystem.load_level(MAP_OBJECT_PATH), "cold map reload failed")
        inspection = inspect_world(execution, profile, lineage, map_file)
        receipt = seal_document(
            {
                "schema_version": WORKER_SCHEMA,
                "status": SUCCESS_STATUS,
                "mode": mode,
                "execution_sha256": execution_sha,
                "accepted": False,
                "error": None,
                "inspection": inspection,
                "claims": copy.deepcopy(NEGATIVE_CLAIMS),
                "legal_scope": copy.deepcopy(LEGAL_SCOPE),
            }
        )
        write_exclusive(output, attempt, receipt)
    except Exception as exc:
        if execution is not None and attempt and output and not os.path.lexists(output):
            failure = seal_document(
                {
                    "schema_version": WORKER_SCHEMA,
                    "status": FAILURE_STATUS,
                    "mode": mode,
                    "execution_sha256": execution_sha,
                    "accepted": False,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                    "inspection": None,
                    "claims": copy.deepcopy(NEGATIVE_CLAIMS),
                    "legal_scope": copy.deepcopy(LEGAL_SCOPE),
                }
            )
            write_exclusive(output, attempt, failure)
        raise


run()
