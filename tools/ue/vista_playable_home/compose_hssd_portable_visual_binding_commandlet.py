"""Bind two imported HSSD meshes to portable semantic actors in a fresh map.

This fixed UE Python commandlet accepts only the hash-pinned execution emitted
by ``plan_hssd_portable_visual_binding_dev.py``.  It creates a new map from the
completed articulated-fridge derivative, proves the contract-declared coffee
shell is already absent and the exact slipper visual shell is present before
mutating anything, deletes only that one redundant shell, and binds both
existing StaticMeshes to each ``AVistaPickupActor`` authority's render-only
``PresentationMesh`` child.  Failures stay quarantined.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import PurePosixPath
import re

import unreal


EXECUTION_SCHEMA = "vista.playable-hssd-portable-visual-binding-dev-execution/v1"
RECEIPT_SCHEMA = "vista.playable-hssd-portable-visual-binding-dev-scene-receipt/v1"
EXPECTED_ENGINE_VERSION = "5.7.3-50162420+++UE5+Release-5.7"
EXECUTION_ENV = "VISTA_HSSD_PORTABLE_VISUAL_BINDING_EXECUTION"
EXECUTION_SHA_ENV = "VISTA_HSSD_PORTABLE_VISUAL_BINDING_EXECUTION_SHA256"
SUCCESS_STATUS = "dev_derivative_bound_pending_runtime_and_human_review"
FAILURE_STATUS = "partial_dev_derivative_quarantined"
MARKER = "VISTA_HSSD_PORTABLE_VISUAL_BINDING_RESULT:"
SOURCE_MAP_ROOT = "/Game/VISTA/Dev/ArticulatedFridge/"
DERIVATIVE_ROOT = "/Game/VISTA/Dev/PortableVisualBindings/"
PICKUP_CLASS = "/Script/VistaPlayableHome.VistaPickupActor"
SHELL_CLASS = "/Script/Engine.StaticMeshActor"
CONTRACT_SCHEMA = "vista.playable-hssd-portable-visual-binding/v1"
CONTRACT_ID = "hssd_portable_pickups_r1"
CONTRACT_SHA256 = "822fd1ad7c180e9c5a590f900196e10ab745566e74207d94802940f5b089679b"
CONTRACT_CONTENT_DIGEST = (
    "9ff240df82ef192be745af5f774b9cd297b3a3a971a8c31bdc54f290e2683dfe"
)
SOURCE_RECEIPT_SCHEMA = "vista.playable-articulated-fridge-dev-scene-receipt/v1"
SOURCE_SUCCESS_STATUS = "dev_derivative_composed_pending_runtime_and_human_review"
SEMANTIC_IDS = (
    "home.r1/room.kitchen_dining/entity.coffee_cup.01",
    "home.r1/room.living_room/entity.slipper.01",
)
ABSENT_SHELL_DISPOSITION = "already_absent_source_shell"
DELETE_SHELL_DISPOSITION = "exact_visual_shell_to_delete"
EXACT_SOURCE_PRESENTATION = "exact_existing_presentation_to_replace"
NO_SOURCE_PRESENTATION = "no_existing_presentation"
SHELL_DISPOSITIONS = (
    ABSENT_SHELL_DISPOSITION,
    DELETE_SHELL_DISPOSITION,
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "execution contains a duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise RuntimeError("execution contains a non-finite JSON constant: " + value)


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
    ).encode("utf-8")


def content_digest(value):
    body = copy.deepcopy(value)
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def valid_content_digest(value):
    expected = value.get("content_digest")
    if not isinstance(expected, str) or SHA256.fullmatch(expected) is None:
        return False
    body = copy.deepcopy(value)
    body.pop("content_digest", None)
    raw = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return expected in {
        hashlib.sha256(raw).hexdigest(),
        hashlib.sha256(raw + b"\n").hexdigest(),
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_path(path):
    return os.path.realpath(os.path.abspath(str(path))).replace("\\", "/")


def map_package_file(project, object_path):
    require(
        isinstance(object_path, str)
        and object_path.startswith("/Game/")
        and "." not in object_path,
        "map object path is not one /Game package path",
    )
    relative = PurePosixPath(object_path.removeprefix("/Game/") + ".umap")
    require(".." not in relative.parts, "map object path escapes Content")
    return canonical_path(
        os.path.join(os.path.dirname(project), "Content", *relative.parts)
    )


def safe_attempt_child(path, attempt_root, label, *, must_exist=True):
    resolved = canonical_path(path)
    root = canonical_path(attempt_root)
    require(resolved.startswith(root + "/"), label + " escapes attempt root")
    if must_exist:
        require(
            os.path.isfile(resolved) and not os.path.islink(resolved),
            label + " is missing or symlinked",
        )
    return resolved


def load_json_file(path, label):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            value = json.load(
                stream,
                object_pairs_hook=duplicate_keys,
                parse_constant=reject_constant,
            )
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(label + " is not strict UTF-8 JSON") from exc
    require(type(value) is dict, label + " root must be one object")
    return value


def write_exclusive(path, attempt_root, value):
    output = safe_attempt_child(path, attempt_root, "output", must_exist=False)
    require(
        os.path.dirname(output) == canonical_path(attempt_root),
        "output must be a direct attempt-root child",
    )
    descriptor = os.open(
        output,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    raw = canonical_json(value)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    return hashlib.sha256(raw).hexdigest()


def load_execution():
    path = canonical_path(os.environ.get(EXECUTION_ENV, ""))
    expected_sha = os.environ.get(EXECUTION_SHA_ENV, "")
    require(SHA256.fullmatch(expected_sha or "") is not None, "execution SHA invalid")
    require(
        os.path.isfile(path) and not os.path.islink(path),
        "execution manifest missing or symlinked",
    )
    require(sha256_file(path) == expected_sha, "execution manifest bytes differ")
    with open(path, "r", encoding="utf-8") as stream:
        execution = json.load(
            stream,
            object_pairs_hook=duplicate_keys,
            parse_constant=reject_constant,
        )
    require(
        set(execution)
        == {
            "schema_version",
            "mode",
            "engine_version",
            "attempt_root",
            "project",
            "source_map",
            "derivative_map",
            "contract",
            "source_fridge_receipt",
            "bindings",
            "commandlet",
            "outputs",
            "policy",
            "content_digest",
        },
        "execution top-level fields differ",
    )
    require(execution["schema_version"] == EXECUTION_SCHEMA, "execution schema differs")
    require(
        execution["content_digest"] == content_digest(execution),
        "execution content digest differs",
    )
    require(
        execution["mode"] == "dev_only_fresh_derivative_from_completed_fridge",
        "execution mode differs",
    )
    require(
        execution["engine_version"] == EXPECTED_ENGINE_VERSION, "engine pin differs"
    )
    require(
        execution["policy"]
        == {
            "append_only_attempt": True,
            "isolated_project_required": True,
            "source_map_read_only": True,
            "fresh_derivative_map_required": True,
            "new_level_from_template_required": True,
            "asset_import_or_replacement_forbidden": True,
            "exact_identity_before_delete_required": True,
            "only_visual_shells_may_be_deleted": True,
            "declared_absent_shell_must_be_proved": True,
            "exact_one_visual_shell_may_be_deleted": True,
            "pickup_authority_must_be_preserved": True,
            "save_reload_required": True,
            "quarantine_on_failure": True,
            "accepted": False,
            "launch_ue": False,
        },
        "execution safety policy differs",
    )
    attempt = canonical_path(execution["attempt_root"])
    require(
        path == attempt + "/hssd-portable-visual-binding-execution.json",
        "execution manifest is not the direct attempt child",
    )
    project_record = execution["project"]
    require(set(project_record) == {"path", "sha256"}, "project record differs")
    project = safe_attempt_child(project_record["path"], attempt, "project")
    require(
        PurePosixPath(project).parent.name == "project"
        and project.endswith(".uproject"),
        "project is not an isolated attempt project",
    )
    require(sha256_file(project) == project_record["sha256"], "project bytes differ")
    require(
        canonical_path(unreal.Paths.get_project_file_path()) == project,
        "loaded project differs",
    )
    require(
        str(unreal.SystemLibrary.get_engine_version()) == EXPECTED_ENGINE_VERSION,
        "loaded engine differs",
    )
    source = execution["source_map"]
    derivative = execution["derivative_map"]
    require(
        set(source)
        == {
            "object_path",
            "package_file",
            "package_sha256",
            "package_size_bytes",
            "source_receipt_content_digest",
        }
        and set(derivative) == {"object_path", "package_file"},
        "map records differ",
    )
    source_package = safe_attempt_child(source["package_file"], attempt, "source map")
    derivative_package = safe_attempt_child(
        derivative["package_file"], attempt, "derivative map", must_exist=False
    )
    require(
        source["object_path"].startswith(SOURCE_MAP_ROOT)
        and derivative["object_path"].startswith(DERIVATIVE_ROOT)
        and source["object_path"] != derivative["object_path"]
        and source_package != derivative_package
        and not os.path.lexists(derivative_package),
        "map closure is not a fresh portable-binding derivative",
    )
    require(
        source_package == map_package_file(project, source["object_path"])
        and derivative_package == map_package_file(project, derivative["object_path"]),
        "map package files do not match their loaded-project object paths",
    )
    require(
        os.path.getsize(source_package) == source["package_size_bytes"]
        and sha256_file(source_package) == source["package_sha256"],
        "source map bytes differ",
    )
    commandlet = execution["commandlet"]
    require(
        canonical_path(commandlet["path"]) == canonical_path(__file__)
        and sha256_file(__file__) == commandlet["sha256"],
        "fixed commandlet identity differs",
    )
    evidence_paths = {}
    for label in ("contract", "source_fridge_receipt"):
        record = execution[label]
        source_file = safe_attempt_child(record["path"], attempt, label)
        require(
            os.path.getsize(source_file) == record["size_bytes"]
            and sha256_file(source_file) == record["sha256"],
            label + " bytes differ",
        )
        evidence_paths[label] = source_file
    contract_record = execution["contract"]
    require(
        set(contract_record)
        == {"path", "sha256", "size_bytes", "contract_id", "content_digest"}
        and contract_record["sha256"] == CONTRACT_SHA256
        and contract_record["contract_id"] == CONTRACT_ID
        and contract_record["content_digest"] == CONTRACT_CONTENT_DIGEST,
        "fixed contract record differs",
    )
    contract_document = load_json_file(evidence_paths["contract"], "contract")
    require(
        valid_content_digest(contract_document)
        and contract_document.get("schema_version") == CONTRACT_SCHEMA
        and contract_document.get("contract_id") == CONTRACT_ID
        and contract_document.get("content_digest") == CONTRACT_CONTENT_DIGEST
        and contract_document.get("pickup_actor_class_path") == PICKUP_CLASS
        and contract_document.get("source_policy")
        == {
            "source_map_role": "completed_articulated_fridge_dev_derivative",
            "new_level_from_template_required": True,
            "source_map_read_only": True,
            "delete_visual_shell_only": True,
            "preserve_pickup_authority": True,
            "external_assets_outside_git": True,
        },
        "fixed contract document differs",
    )
    source_receipt_record = execution["source_fridge_receipt"]
    require(
        set(source_receipt_record)
        == {"path", "sha256", "size_bytes", "schema_version", "content_digest"},
        "source fridge receipt record differs",
    )
    require(
        source_receipt_record["schema_version"] == SOURCE_RECEIPT_SCHEMA,
        "source fridge receipt schema pin differs",
    )
    source_receipt = load_json_file(
        evidence_paths["source_fridge_receipt"], "source fridge receipt"
    )
    source_gates = source_receipt.get("gates", {})
    source_claims = source_receipt.get("claims", {})
    source_derivative = source_receipt.get("derivative_map", {})
    require(
        valid_content_digest(source_receipt)
        and source_receipt.get("schema_version") == SOURCE_RECEIPT_SCHEMA
        and source_receipt.get("status") == SOURCE_SUCCESS_STATUS
        and source_receipt.get("error") is None
        and source_receipt.get("accepted") is False
        and source_receipt.get("ue_imported") is True
        and source_receipt.get("runtime_verified") is False
        and source_receipt.get("human_reviewed") is False
        and source_receipt.get("promotable") is False
        and source_receipt.get("diagnostic_only") is True
        and source_receipt.get("content_digest")
        == source_receipt_record["content_digest"]
        and source_derivative.get("object_path") == source["object_path"]
        and source_derivative.get("package_sha256") == source["package_sha256"]
        and source_derivative.get("package_size_bytes") == source["package_size_bytes"]
        and source_receipt.get("base_map", {}).get("unchanged") is True
        and source_gates.get("exact_legacy_shell_and_proxy_validated_before_delete")
        is True
        and source_gates.get("legacy_shell_and_proxy_removed_only_in_derivative")
        is True
        and source_gates.get("fresh_derivative_map_created") is True
        and source_gates.get("base_map_package_unchanged") is True
        and source_gates.get("map_saved") is True
        and source_gates.get("map_cold_reloaded") is True
        and source_gates.get("one_visible_semantic_authority") is True
        and source_gates.get("quarantined") is False
        and source_claims.get("r6_touched") is False
        and source_claims.get("production_promoted") is False
        and source_claims.get("ue_runtime_launched") is False,
        "completed source fridge receipt differs",
    )
    require(
        execution["source_fridge_receipt"]["content_digest"]
        == source["source_receipt_content_digest"],
        "source receipt/map linkage differs",
    )
    bindings = execution["bindings"]
    require(
        isinstance(bindings, list)
        and [row.get("semantic_id") for row in bindings] == list(SEMANTIC_IDS)
        and tuple(row.get("shell_disposition") for row in bindings)
        == SHELL_DISPOSITIONS
        and len({row.get("hssd_instance_id") for row in bindings}) == 2
        and all(row.get("shell_actor_class_path") == SHELL_CLASS for row in bindings),
        "closed portable binding inventory differs",
    )
    require(
        bindings == contract_document.get("bindings"),
        "manifest bindings differ from contract",
    )
    outputs = execution["outputs"]
    require(set(outputs) == {"scene_receipt", "scene_result"}, "outputs differ")
    for output in outputs.values():
        safe_attempt_child(output, attempt, "terminal output", must_exist=False)
        require(not os.path.lexists(output), "terminal output already exists")
    return execution, path, expected_sha


def property_or_none(value, name):
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def property_value(value, name, label):
    try:
        return value.get_editor_property(name)
    except Exception as exc:
        raise RuntimeError(label + " property unavailable: " + name) from exc


def actor_root_component(actor, label):
    method = getattr(actor, "get_root_component", None)
    if callable(method):
        try:
            root = method()
        except Exception as exc:
            raise RuntimeError(label + " root component method failed") from exc
        reflected = property_or_none(actor, "root_component")
        if reflected is not None:
            try:
                same_path = str(root.get_path_name()) == str(
                    reflected.get_path_name()
                )
            except Exception as exc:
                raise RuntimeError(label + " root component sources are ambiguous") from exc
            require(same_path, label + " root component sources differ")
    else:
        root = property_value(actor, "root_component", label)
    require(root is not None, label + " root component is missing")
    try:
        path = str(root.get_path_name())
    except Exception as exc:
        raise RuntimeError(label + " root component path is unavailable") from exc
    require(bool(path), label + " root component path is empty")
    return root


def class_path(value):
    reflected = value.get_class() if value is not None else None
    return str(reflected.get_path_name()) if reflected is not None else ""


def sorted_tags(actor):
    return sorted(str(tag) for tag in property_value(actor, "tags", "actor"))


def set_tags(actor, tags):
    actor.set_editor_property("tags", [unreal.Name(tag) for tag in sorted(tags)])


def actor_hidden(actor):
    value = property_or_none(actor, "hidden")
    if type(value) is bool:
        return value
    try:
        return bool(actor.is_hidden_ed()) or bool(actor.is_hidden())
    except Exception as exc:
        raise RuntimeError("actor hidden state unavailable") from exc


def actor_collision(actor):
    try:
        value = actor.get_actor_enable_collision()
    except Exception:
        value = property_or_none(actor, "actor_enable_collision")
    require(type(value) is bool, "actor collision state unavailable")
    return value


def bool_property(value, name, label):
    result = property_value(value, name, label)
    require(type(result) is bool, label + " boolean differs: " + name)
    return result


def serialized_simulates_physics(component, label):
    body_instance = property_value(component, "body_instance", label)
    require(body_instance is not None, label + " body instance unavailable")
    return bool_property(body_instance, "simulate_physics", label + " body instance")


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
    raise RuntimeError("collision mode is outside the closed enum")


def mobility_label(value):
    enum_labels = (
        ("STATIC", "Static"),
        ("STATIONARY", "Stationary"),
        ("MOVABLE", "Movable"),
    )
    enum_type = getattr(unreal, "ComponentMobility", None)
    for attribute, label in enum_labels:
        candidate = (
            getattr(enum_type, attribute, None) if enum_type is not None else None
        )
        if candidate is not None and (value is candidate or value == candidate):
            return label

    token = str(value).strip()
    aliases = {
        "Static": "Static",
        "Stationary": "Stationary",
        "Movable": "Movable",
        "ComponentMobility.STATIC": "Static",
        "ComponentMobility.STATIONARY": "Stationary",
        "ComponentMobility.MOVABLE": "Movable",
        "<ComponentMobility.STATIC: 0>": "Static",
        "<ComponentMobility.STATIONARY: 1>": "Stationary",
        "<ComponentMobility.MOVABLE: 2>": "Movable",
    }
    require(
        token in aliases,
        "component mobility is outside the closed enum: " + repr(token[:96]),
    )
    return aliases[token]


def vector(values):
    return unreal.Vector(x=values[0], y=values[1], z=values[2])


def rotator(values):
    return unreal.Rotator(roll=values[0], pitch=values[1], yaw=values[2])


def unreal_transform(value):
    return unreal.Transform(
        location=vector(value["location_cm"]),
        rotation=rotator(value["rotation_deg"]),
        scale=vector(value["scale"]),
    )


def observed_transform(value, *, actor=False):
    if actor:
        location = value.get_actor_location()
        rotation = value.get_actor_rotation()
        scale = value.get_actor_scale3d()
    else:
        location = property_value(value, "relative_location", "component")
        rotation = property_value(value, "relative_rotation", "component")
        scale = property_value(value, "relative_scale3d", "component")
    return {
        "location_cm": [float(location.x), float(location.y), float(location.z)],
        "rotation_deg": [
            float(rotation.roll),
            float(rotation.pitch),
            float(rotation.yaw),
        ],
        "scale": [float(scale.x), float(scale.y), float(scale.z)],
    }


def transform_matches(actual, expected):
    return (
        all(
            abs(float(a) - float(b)) <= 0.05
            for a, b in zip(actual["location_cm"], expected["location_cm"])
        )
        and all(
            abs((float(a) - float(b) + 180.0) % 360.0 - 180.0) <= 0.05
            for a, b in zip(actual["rotation_deg"], expected["rotation_deg"])
        )
        and all(
            abs(float(a) - float(b)) <= 0.0001
            for a, b in zip(actual["scale"], expected["scale"])
        )
    )


def static_mesh_components(actor):
    return list(actor.get_components_by_class(unreal.StaticMeshComponent) or [])


def mesh_path(component):
    mesh = property_or_none(component, "static_mesh")
    return str(mesh.get_path_name()) if isinstance(mesh, unreal.StaticMesh) else None


def component_observation(component, label, *, mesh_required=True):
    require(
        isinstance(component, unreal.StaticMeshComponent), label + " component differs"
    )
    path = mesh_path(component)
    require(path is not None or not mesh_required, label + " mesh unavailable")
    parent = component.get_attach_parent()
    return {
        "component_path": str(component.get_path_name()),
        "component_name": str(component.get_name()),
        "mesh_object_path": path,
        "relative_transform": observed_transform(component),
        "attach_parent_component_path": (
            str(parent.get_path_name()) if parent is not None else None
        ),
        "visible": bool_property(component, "visible", label),
        "collision_mode": collision_label(component),
        "collision_profile": str(component.get_collision_profile_name()),
        "mobility": mobility_label(property_value(component, "mobility", label)),
        "simulate_physics": serialized_simulates_physics(component, label),
        "generate_overlap_events": bool_property(
            component, "generate_overlap_events", label
        ),
        "can_ever_affect_navigation": bool_property(
            component, "can_ever_affect_navigation", label
        ),
    }


def semantic_id(actor):
    value = property_value(actor, "semantic_id", "pickup")
    require(type(value) is str and value, "pickup semantic_id unavailable")
    return value


def pickup_for(actors, binding, *, bound=False):
    semantic = binding["semantic_id"]
    required = set(binding["pickup_required_tags"])
    if bound:
        required.add("VistaHssdInstanceId=" + binding["hssd_instance_id"])
    matches = [
        actor
        for actor in actors
        if class_path(actor) == PICKUP_CLASS
        and semantic_id(actor) == semantic
        and required.issubset(set(sorted_tags(actor)))
    ]
    require(len(matches) == 1, "pickup semantic identity is not unique: " + semantic)
    return matches[0]


def shell_identity_inventory(actors, binding):
    instance_tag = "VistaHssdInstanceId=" + binding["hssd_instance_id"]
    actor_label = binding["shell_actor_label"]
    semantic_target_tag = binding["shell_semantic_target_tag"]
    return {
        "instance_tag_actor_paths": sorted(
            str(actor.get_path_name())
            for actor in actors
            if instance_tag in sorted_tags(actor)
        ),
        "actor_label_actor_paths": sorted(
            str(actor.get_path_name())
            for actor in actors
            if str(actor.get_actor_label()) == actor_label
        ),
        "semantic_target_tag_actor_paths": (
            sorted(
                str(actor.get_path_name())
                for actor in actors
                if semantic_target_tag in sorted_tags(actor)
            )
            if semantic_target_tag is not None
            else []
        ),
    }


def require_shell_identity_absent(
    actors, binding, context, *, allowed_instance_tag_actor_paths=()
):
    inventory = shell_identity_inventory(actors, binding)
    allowed_paths = set(allowed_instance_tag_actor_paths)
    observed_instance_paths = set(inventory["instance_tag_actor_paths"])
    require(
        allowed_paths.issubset(observed_instance_paths),
        context + " allowed pickup instance-tag path is absent",
    )
    unexpected_inventory = copy.deepcopy(inventory)
    unexpected_inventory["instance_tag_actor_paths"] = sorted(
        observed_instance_paths - allowed_paths
    )
    counts = {key: len(paths) for key, paths in unexpected_inventory.items()}
    require(
        all(count == 0 for count in counts.values()),
        context
        + " identity is not absent: "
        + ", ".join(
            (
                "instance_tag=" + str(counts["instance_tag_actor_paths"]),
                "actor_label=" + str(counts["actor_label_actor_paths"]),
                "semantic_target_tag="
                + str(counts["semantic_target_tag_actor_paths"]),
            )
        ),
    )
    return {
        "identity_match_counts": counts,
        "identity_match_actor_paths": unexpected_inventory,
        "allowed_instance_tag_actor_paths": sorted(allowed_paths),
    }


def verify_declared_absent_shell(actors, binding):
    require(
        binding["shell_disposition"] == ABSENT_SHELL_DISPOSITION
        and isinstance(binding["shell_semantic_target_tag"], str)
        and bool(binding["shell_semantic_target_tag"]),
        "declared absent shell contract differs: " + binding["semantic_id"],
    )
    evidence = require_shell_identity_absent(
        actors, binding, "declared absent HSSD shell"
    )
    return {
        "semantic_id": binding["semantic_id"],
        "hssd_instance_id": binding["hssd_instance_id"],
        "declared_disposition": binding["shell_disposition"],
        "observed_disposition": "absent",
        "deleted": False,
        **evidence,
        "cold_reload_absence_evidence": None,
    }


def exact_shell_for(actors, binding):
    require(
        binding["shell_disposition"] == DELETE_SHELL_DISPOSITION,
        "deletable shell contract disposition differs: " + binding["semantic_id"],
    )
    inventory = shell_identity_inventory(actors, binding)
    instance_paths = inventory["instance_tag_actor_paths"]
    label_paths = inventory["actor_label_actor_paths"]
    require(
        len(instance_paths) == 1
        and len(label_paths) == 1
        and instance_paths == label_paths,
        "deletable HSSD shell identity is not exact and unique: "
        + binding["hssd_instance_id"],
    )
    matches = [
        actor for actor in actors if str(actor.get_path_name()) == instance_paths[0]
    ]
    require(
        len(matches) == 1,
        "deletable HSSD shell actor path is not unique: " + instance_paths[0],
    )
    return matches[0], inventory


def require_single_identity_tag(tags, prefix, expected):
    matches = [tag for tag in tags if tag.startswith(prefix)]
    require(
        matches == [prefix + expected], "HSSD shell identity tags conflict: " + prefix
    )


def require_exact_shell_tags(tags, binding):
    expected = sorted(binding["shell_required_tags"])
    require(tags == expected, "HSSD shell tags differ from the closed contract")


def validate_shell(actor, binding):
    components = static_mesh_components(actor)
    require(len(components) == 1, "HSSD shell component count differs")
    component = component_observation(components[0], "HSSD shell")
    tags = sorted_tags(actor)
    require_exact_shell_tags(tags, binding)
    require_single_identity_tag(tags, "VistaRole=", "hssd_visual_shell")
    require_single_identity_tag(
        tags, "VistaHssdInstanceId=", binding["hssd_instance_id"]
    )
    require_single_identity_tag(
        tags, "VistaHssdSourceAssetId=", binding["source_asset_id"]
    )
    require_single_identity_tag(tags, "VistaRoomId=", binding["room_id"])
    semantic_prefix = "VistaHssdSemanticTargetId="
    semantic_tags = [tag for tag in tags if tag.startswith(semantic_prefix)]
    expected_semantic = binding["shell_semantic_target_tag"]
    root = actor_root_component(actor, "HSSD shell")
    require(
        class_path(actor) == binding["shell_actor_class_path"]
        and str(actor.get_actor_label()) == binding["shell_actor_label"]
        and semantic_tags == ([expected_semantic] if expected_semantic else [])
        and actor_hidden(actor) is False
        and actor_collision(actor) is False
        and transform_matches(
            observed_transform(actor, actor=True), binding["shell_world_transform_cm"]
        )
        and component["mesh_object_path"] == binding["hssd_mesh_object_path"]
        and root is not None
        and str(root.get_path_name()) == component["component_path"]
        and component["visible"] is True
        and component["mobility"] == "Static"
        and component["collision_mode"] == "NoCollision"
        and component["collision_profile"] == "NoCollision"
        and component["simulate_physics"] is False
        and component["generate_overlap_events"] is False
        and component["can_ever_affect_navigation"] is False,
        "HSSD visual shell no longer matches the closed contract: "
        + binding["hssd_instance_id"],
    )
    return {
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "actor_class_path": class_path(actor),
        "tags": tags,
        "actor_hidden_in_game": actor_hidden(actor),
        "actor_collision_enabled": actor_collision(actor),
        "world_transform_cm": observed_transform(actor, actor=True),
        "component": component,
    }


def pickup_observation(actor):
    root = property_value(actor, "mesh", "pickup")
    presentation = property_value(actor, "presentation_mesh", "pickup")
    root_component = actor_root_component(actor, "pickup")
    require(
        isinstance(root, unreal.StaticMeshComponent)
        and isinstance(presentation, unreal.StaticMeshComponent)
        and root_component is not None
        and str(root_component.get_path_name()) == str(root.get_path_name()),
        "pickup component/root authority differs",
    )
    root_observation = component_observation(root, "PickupMesh")
    presentation_observation = component_observation(
        presentation, "PresentationMesh", mesh_required=False
    )
    actor_class = class_path(actor)
    tags = sorted_tags(actor)
    observation = {
        "semantic_id": semantic_id(actor),
        "actor_path": str(actor.get_path_name()),
        "actor_label": str(actor.get_actor_label()),
        "actor_class_path": actor_class,
        "tags": tags,
        "world_transform_cm": observed_transform(actor, actor=True),
        "actor_hidden_in_game": actor_hidden(actor),
        "actor_collision_enabled": actor_collision(actor),
        "portable": bool_property(actor, "portable", "pickup"),
        "replication": {
            "replicates": bool_property(actor, "replicates", "pickup"),
            "replicate_movement": bool_property(actor, "replicate_movement", "pickup"),
            "net_load_on_client": bool_property(actor, "net_load_on_client", "pickup"),
        },
        "root": root_observation,
        "presentation": presentation_observation,
    }
    require(
        actor_class == PICKUP_CLASS
        and "VistaRole=pickup" in tags
        and "VistaSemanticId=" + observation["semantic_id"] in tags
        and observation["actor_collision_enabled"] is True
        and observation["portable"] is True
        and root_observation["component_name"] == "PickupMesh"
        and root_observation["attach_parent_component_path"] is None
        and root_observation["collision_mode"] != "NoCollision"
        and presentation_observation["component_name"] == "PresentationMesh"
        and presentation_observation["attach_parent_component_path"]
        == root_observation["component_path"]
        and presentation_observation["collision_mode"] == "NoCollision"
        and presentation_observation["collision_profile"] == "NoCollision"
        and presentation_observation["simulate_physics"] is False
        and presentation_observation["generate_overlap_events"] is False
        and presentation_observation["can_ever_affect_navigation"] is False,
        "pickup authority/component closure differs",
    )
    return observation


def validate_source_presentation(observation, binding):
    source = binding["source_presentation"]
    require(
        set(source)
        == {"disposition", "mesh_object_path", "relative_transform", "visible"},
        "source presentation contract fields differ: " + binding["semantic_id"],
    )
    disposition = source["disposition"]
    mesh = source["mesh_object_path"]
    require(
        (disposition == EXACT_SOURCE_PRESENTATION and isinstance(mesh, str) and mesh)
        or (disposition == NO_SOURCE_PRESENTATION and mesh is None),
        "source presentation disposition is outside the closed contract: "
        + binding["semantic_id"],
    )
    presentation = observation["presentation"]
    require(
        presentation["mesh_object_path"] == mesh
        and transform_matches(
            presentation["relative_transform"], source["relative_transform"]
        )
        and presentation["visible"] is source["visible"]
        and presentation["mobility"] == "Movable",
        "source presentation no longer matches the closed contract: "
        + binding["semantic_id"],
    )


def validate_source_pickup(actor, binding):
    observation = pickup_observation(actor)
    require(
        observation["semantic_id"] == binding["semantic_id"]
        and observation["actor_label"] == binding["pickup_actor_label"]
        and set(binding["pickup_required_tags"]).issubset(set(observation["tags"]))
        and transform_matches(
            observation["world_transform_cm"], binding["pickup_world_transform_cm"]
        )
        and observation["root"]["mesh_object_path"]
        == binding["pickup_root_mesh_object_path"],
        "source pickup no longer matches the closed identity contract: "
        + binding["semantic_id"],
    )
    validate_source_presentation(observation, binding)
    return observation


def authority_view(observation):
    result = copy.deepcopy(observation)
    result.pop("tags")
    result.pop("actor_hidden_in_game")
    presentation = result.pop("presentation")
    result["root"].pop("visible")
    # Attachment path is authority evidence, but presentation bytes/visibility
    # are the intentionally mutated visual slice.
    result["presentation_attachment"] = presentation["attach_parent_component_path"]
    return result


def validate_bound_pickup(actor, binding, before):
    observation = pickup_observation(actor)
    expected_tags = set(before["tags"]) | {
        "VistaHssdInstanceId=" + binding["hssd_instance_id"],
        "VistaHssdSourceAssetId=" + binding["source_asset_id"],
        "VistaRole=hssd_portable_presentation",
        "VistaHssdPortableBindingContractId=hssd_portable_pickups_r1",
        "VistaDevDerivative=true",
        "VistaAccepted=false",
    }
    presentation = observation["presentation"]
    policy = binding["presentation_policy"]
    require(
        authority_view(observation) == authority_view(before)
        and set(observation["tags"]) == expected_tags
        and observation["actor_hidden_in_game"] is False
        and observation["root"]["visible"] is policy["root_mesh_visible"]
        and presentation["mesh_object_path"] == binding["hssd_mesh_object_path"]
        and transform_matches(
            presentation["relative_transform"],
            binding["presentation_relative_transform"],
        )
        and presentation["visible"] is policy["visible"]
        and presentation["collision_mode"] == policy["collision_mode"]
        and presentation["collision_profile"] == policy["collision_profile"]
        and presentation["simulate_physics"] is policy["simulate_physics"]
        and presentation["generate_overlap_events"] is policy["generate_overlap_events"]
        and presentation["can_ever_affect_navigation"]
        is policy["can_ever_affect_navigation"],
        "bound pickup escaped the closed presentation-only mutation: "
        + binding["semantic_id"],
    )
    return observation


def actor_inventory(actors):
    return sorted(
        [
            {
                "actor_path": str(actor.get_path_name()),
                "actor_class_path": class_path(actor),
                "actor_label": str(actor.get_actor_label()),
                "tags": sorted_tags(actor),
            }
            for actor in actors
        ],
        key=lambda row: row["actor_path"],
    )


def material_paths(mesh):
    result = []
    for slot in list(property_or_none(mesh, "static_materials") or []):
        material = property_or_none(slot, "material_interface")
        require(material is not None, "HSSD mesh material slot is unresolved")
        path = str(material.get_path_name())
        require(
            "DefaultMaterial" not in path and "BasicShapeMaterial" not in path,
            "HSSD mesh uses a fallback material",
        )
        result.append(path)
    require(result, "HSSD mesh has no material slots")
    return result


def run():
    execution, manifest_path, manifest_sha = load_execution()
    attempt = execution["attempt_root"]
    outputs = execution["outputs"]
    stage = {"phase": "validate", "detail": None}
    status = FAILURE_STATUS
    error = None
    source_map_revalidated = False
    source_map_unchanged = False
    map_created = False
    map_saved = False
    map_reloaded = False
    all_binding_identities_validated = False
    declared_absent_shell_verified = False
    exact_one_shell_deleted = False
    only_declared_shell_deleted = False
    authority_preserved = False
    shell_disposition_observations = []
    pickups_before = []
    pickups_after = []
    pickups_reloaded = []
    mesh_records = []
    try:
        source = execution["source_map"]
        derivative = execution["derivative_map"]
        require(
            sha256_file(source["package_file"]) == source["package_sha256"]
            and os.path.getsize(source["package_file"]) == source["package_size_bytes"],
            "source map package changed before composition",
        )
        source_map_revalidated = True
        require(
            not unreal.EditorAssetLibrary.does_asset_exist(derivative["object_path"]),
            "fresh portable-binding derivative already exists",
        )
        stage = {"phase": "new_level_from_template", "detail": None}
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        require(
            level_subsystem.new_level_from_template(
                derivative["object_path"], source["object_path"]
            ),
            "failed to create fresh derivative from completed fridge source map",
        )
        map_created = True
        world = unreal.EditorLevelLibrary.get_editor_world()
        require(world is not None, "fresh portable-binding world unavailable")
        actors = list(actor_subsystem.get_all_level_actors())
        inventory_before = actor_inventory(actors)

        stage = {"phase": "prove_all_identities_before_delete", "detail": None}
        shells_to_delete = []
        pickups = []
        meshes = []
        for binding in execution["bindings"]:
            stage["detail"] = binding["semantic_id"]
            disposition = binding["shell_disposition"]
            shell = None
            if disposition == ABSENT_SHELL_DISPOSITION:
                shell_disposition_observations.append(
                    verify_declared_absent_shell(actors, binding)
                )
            elif disposition == DELETE_SHELL_DISPOSITION:
                shell, identity_inventory = exact_shell_for(actors, binding)
                shell_disposition_observations.append(
                    {
                        "semantic_id": binding["semantic_id"],
                        "hssd_instance_id": binding["hssd_instance_id"],
                        "declared_disposition": disposition,
                        "observed_disposition": "present",
                        "deleted": False,
                        "identity_match_counts": {
                            key: len(paths)
                            for key, paths in identity_inventory.items()
                        },
                        "identity_match_actor_paths": identity_inventory,
                        "shell_observation_before_delete": validate_shell(
                            shell, binding
                        ),
                        "cold_reload_absence_evidence": None,
                    }
                )
                shells_to_delete.append(shell)
            else:
                require(False, "shell disposition is outside the closed enum")
            pickup = pickup_for(actors, binding)
            require(shell is None or shell != pickup, "visual shell aliases pickup")
            pickups.append(pickup)
            pickups_before.append(validate_source_pickup(pickup, binding))
            mesh = unreal.load_asset(binding["hssd_mesh_object_path"])
            require(
                isinstance(mesh, unreal.StaticMesh)
                and str(mesh.get_path_name()) == binding["hssd_mesh_object_path"],
                "exact imported HSSD StaticMesh is unavailable",
            )
            mesh_records.append(
                {
                    "semantic_id": binding["semantic_id"],
                    "object_path": str(mesh.get_path_name()),
                    "class_path": class_path(mesh),
                    "material_paths": material_paths(mesh),
                }
            )
            meshes.append(mesh)
        require(
            len(shell_disposition_observations) == 2
            and len(shells_to_delete) == 1
            and len(pickups) == 2
            and len(meshes) == 2
            and len(
                {
                    str(value.get_path_name())
                    for value in [*shells_to_delete, *pickups]
                }
            )
            == 3,
            "portable shell/pickup identity closure overlaps",
        )
        declared_absent_shell_verified = (
            sum(
                row["declared_disposition"] == ABSENT_SHELL_DISPOSITION
                and row["observed_disposition"] == "absent"
                for row in shell_disposition_observations
            )
            == 1
        )
        exact_deletable_shell_verified = (
            sum(
                row["declared_disposition"] == DELETE_SHELL_DISPOSITION
                and row["observed_disposition"] == "present"
                and "shell_observation_before_delete" in row
                for row in shell_disposition_observations
            )
            == 1
        )
        all_binding_identities_validated = (
            declared_absent_shell_verified and exact_deletable_shell_verified
        )

        stage = {"phase": "delete_exact_visual_shell", "detail": None}
        require(
            len(shells_to_delete) == 1,
            "exactly one declared visual shell must be deleted",
        )
        shell_to_delete = shells_to_delete[0]
        deleted_path = str(shell_to_delete.get_path_name())
        require(
            actor_subsystem.destroy_actor(shell_to_delete),
            "failed to delete the exact declared visual-only shell",
        )
        remaining = list(actor_subsystem.get_all_level_actors())
        expected_inventory = [
            row for row in inventory_before if row["actor_path"] != deleted_path
        ]
        require(
            len(inventory_before) - len(expected_inventory) == 1
            and actor_inventory(remaining) == expected_inventory,
            "actor inventory changed beyond the one declared visual shell deletion",
        )
        deletion_records = [
            row
            for row in shell_disposition_observations
            if row["declared_disposition"] == DELETE_SHELL_DISPOSITION
        ]
        require(
            len(deletion_records) == 1
            and deletion_records[0]["shell_observation_before_delete"]["actor_path"]
            == deleted_path,
            "deleted shell receipt linkage differs",
        )
        deletion_records[0]["observed_disposition"] = "deleted"
        deletion_records[0]["deleted"] = True
        deletion_records[0]["deleted_actor_path"] = deleted_path
        exact_one_shell_deleted = True
        only_declared_shell_deleted = True

        stage = {"phase": "bind_hssd_presentations", "detail": None}
        for binding, actor, mesh, before in zip(
            execution["bindings"], pickups, meshes, pickups_before
        ):
            tags = set(before["tags"]) | {
                "VistaHssdInstanceId=" + binding["hssd_instance_id"],
                "VistaHssdSourceAssetId=" + binding["source_asset_id"],
                "VistaRole=hssd_portable_presentation",
                "VistaHssdPortableBindingContractId=hssd_portable_pickups_r1",
                "VistaDevDerivative=true",
                "VistaAccepted=false",
            }
            set_tags(actor, tags)
            require(
                actor.configure_presentation_mesh(
                    mesh, unreal_transform(binding["presentation_relative_transform"])
                )
                is True,
                "ConfigurePresentationMesh returned false: " + binding["semantic_id"],
            )
            actor.set_actor_hidden_in_game(False)
            pickups_after.append(validate_bound_pickup(actor, binding, before))
        authority_preserved = all(
            authority_view(after) == authority_view(before)
            for before, after in zip(pickups_before, pickups_after)
        )
        require(authority_preserved, "pickup collision/physics authority changed")

        stage = {"phase": "save_derivative_map", "detail": None}
        require(
            unreal.EditorLoadingAndSavingUtils.save_map(
                world, derivative["object_path"]
            ),
            "portable-binding derivative map save failed",
        )
        map_saved = True
        stage = {"phase": "cold_reload_derivative_map", "detail": None}

        actors = None
        inventory_before = None
        shells_to_delete = None
        pickups = None
        meshes = None
        remaining = None
        world = None
        shell = None
        shell_to_delete = None
        pickup = None
        mesh = None
        actor = None
        unreal.collect_garbage()

        require(
            level_subsystem.load_level(derivative["object_path"]),
            "portable-binding derivative cold reload failed",
        )
        map_reloaded = True
        reloaded_world = unreal.EditorLevelLibrary.get_editor_world()
        require(
            reloaded_world is not None, "cold-reloaded derivative world unavailable"
        )
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        reloaded_actors = list(actor_subsystem.get_all_level_actors())
        for binding, before, expected_after in zip(
            execution["bindings"], pickups_before, pickups_after
        ):
            reloaded_actor = pickup_for(reloaded_actors, binding, bound=True)
            reloaded_observation = validate_bound_pickup(
                reloaded_actor, binding, before
            )
            require(
                reloaded_observation == expected_after,
                "portable presentation changed across cold reload: "
                + binding["semantic_id"],
            )
            pickups_reloaded.append(reloaded_observation)
            absence_evidence = require_shell_identity_absent(
                reloaded_actors,
                binding,
                "portable shell after cold reload",
                allowed_instance_tag_actor_paths=(
                    str(reloaded_actor.get_path_name()),
                ),
            )
            disposition_records = [
                row
                for row in shell_disposition_observations
                if row["semantic_id"] == binding["semantic_id"]
            ]
            require(
                len(disposition_records) == 1,
                "shell disposition receipt linkage differs after cold reload",
            )
            disposition_records[0]["cold_reload_absence_evidence"] = absence_evidence
        require(
            sha256_file(source["package_file"]) == source["package_sha256"]
            and os.path.getsize(source["package_file"]) == source["package_size_bytes"],
            "source map package changed during derivative composition",
        )
        source_map_unchanged = True
        require(
            os.path.isfile(derivative["package_file"])
            and not os.path.islink(derivative["package_file"]),
            "portable-binding derivative map package missing or symlinked",
        )
        status = SUCCESS_STATUS
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc)[:512],
            "stage": stage,
        }

    succeeded = status == SUCCESS_STATUS
    derivative_package = execution["derivative_map"]["package_file"]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": status,
        "error": error,
        "accepted": False,
        "ue_imported": succeeded,
        "runtime_verified": False,
        "human_reviewed": False,
        "gta_quality": False,
        "promotable": False,
        "diagnostic_only": True,
        "attempt_root": attempt,
        "bindings": {
            "engine": str(unreal.SystemLibrary.get_engine_version()),
            "project": execution["project"]["path"],
            "execution_manifest": manifest_path,
            "execution_manifest_sha256": manifest_sha,
            "contract_sha256": execution["contract"]["sha256"],
            "contract_content_digest": execution["contract"]["content_digest"],
            "source_fridge_receipt_sha256": execution["source_fridge_receipt"][
                "sha256"
            ],
            "source_fridge_receipt_content_digest": execution["source_fridge_receipt"][
                "content_digest"
            ],
        },
        "source_map": {**execution["source_map"], "unchanged": source_map_unchanged},
        "derivative_map": {
            **execution["derivative_map"],
            "package_sha256": sha256_file(derivative_package) if succeeded else None,
            "package_size_bytes": (
                os.path.getsize(derivative_package) if succeeded else None
            ),
        },
        "shell_disposition_observations": shell_disposition_observations,
        "mesh_records": mesh_records,
        "pickup_observations_before": pickups_before,
        "pickup_observations_after": pickups_after,
        "pickup_observations_reloaded": pickups_reloaded,
        "gates": {
            "completed_fridge_source_map_revalidated": source_map_revalidated,
            "fresh_derivative_map_created": map_created,
            "declared_absent_source_shell_verified_before_mutation": declared_absent_shell_verified,
            "exact_one_shell_and_two_pickups_validated_before_delete": all_binding_identities_validated,
            "exact_two_existing_hssd_meshes_loaded": len(mesh_records) == 2,
            "exact_one_visual_shell_deleted": exact_one_shell_deleted,
            "only_declared_visual_shell_deleted": only_declared_shell_deleted,
            "pickup_collision_physics_authority_preserved": authority_preserved,
            "presentation_meshes_bound_with_identity_transform": len(pickups_after)
            == 2,
            "map_saved": map_saved,
            "map_cold_reloaded": map_reloaded,
            "bound_pickups_reloaded_exact": len(pickups_reloaded) == 2,
            "declared_shell_dispositions_revalidated_after_cold_reload": len(
                shell_disposition_observations
            )
            == 2
            and all(
                row["cold_reload_absence_evidence"] is not None
                for row in shell_disposition_observations
            ),
            "source_map_package_unchanged": source_map_unchanged,
            "runtime_pickup_place_drop_verified": False,
            "human_visual_reviewed": False,
            "quarantined": not succeeded,
        },
        "claims": {
            "external_asset_imported": False,
            "source_map_saved": False,
            "production_promoted": False,
            "ue_runtime_launched": False,
            "runtime_actions_accepted": False,
            "visual_quality_accepted": False,
        },
    }
    receipt["content_digest"] = content_digest(receipt)
    receipt_sha = write_exclusive(outputs["scene_receipt"], attempt, receipt)
    result = {
        "status": status,
        "receipt": outputs["scene_receipt"],
        "sha256": receipt_sha,
    }
    write_exclusive(outputs["scene_result"], attempt, result)
    marker = MARKER + json.dumps(result, sort_keys=True)
    unreal.log(marker)
    print(marker, flush=True)
    if not succeeded:
        raise RuntimeError(
            "portable HSSD visual-binding derivative failed and is quarantined"
        )


run()
