"""Fixed UE commandlet that composes and reload-verifies one home revision."""

# Modified in VISTA-World on 2026-08-22: materialize closed EventSpec outcomes.

import hashlib
import json
import math
import os
import stat
import sys

import unreal


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from commandlet_common import (  # noqa: E402
    IMPORT_RECEIPT_SCHEMA,
    IMPORT_RECEIPT_SHA_ENV,
    SCENE_MARKER,
    SCENE_RECEIPT_SCHEMA,
    SCENE_RESULT_FILE,
    canonical_json,
    canonical_path,
    load_build_plan,
    load_execution,
    require,
    require_sha,
    safe_attempt_child,
    sha256_file,
    write_exclusive_receipt,
)


REALISM_R4_PROFILE_SCHEMA = "simworld.vista.playable-home-realism-r4/v1"
REALISM_R4_PROFILE_ID = "realistic_interior_r4_lighting_shadows_v1"
REALISM_R4_SCENE_RECEIPT_SCHEMA = "simworld.vista.playable-home-ue-scene-receipt/v2"
REALISM_R4_OBSERVATION_SCHEMA = "simworld.vista.playable-home-realism-r4-observation/v1"
REALISM_R4_ROOM_IDS = {
    "home.r1/room.entry_hall",
    "home.r1/room.living_room",
    "home.r1/room.kitchen_dining",
    "home.r1/room.bedroom",
    "home.r1/room.office",
    "home.r1/room.bathroom_laundry",
}
APPLIANCE_RUNTIME_PROFILES = {
    "stove": {
        "active_status": "heating",
        "inactive_status": "idle",
        "control_style": "rotary",
        "control_target_local_cm": [0.0, -31.0, 90.0],
        "extra_affordances": ("turn_on", "turn_off"),
        "press": None,
    },
    "faucet": {
        "active_status": "flowing",
        "inactive_status": "idle",
        "control_style": "rotary",
        "control_target_local_cm": [0.0, -5.0, 24.0],
        "extra_affordances": ("turn_on", "turn_off"),
        "press": None,
    },
    "washer": {
        "active_status": "running",
        "inactive_status": "idle",
        "control_style": "button",
        "control_target_local_cm": [0.0, -38.0, 82.0],
        "extra_affordances": ("press", "turn_on", "turn_off"),
        "press": {
            "control_id": "start",
            "result_active": True,
            "result_status": "running",
        },
    },
}


def vector(values):
    return unreal.Vector(x=values[0], y=values[1], z=values[2])


def rotation(values):
    # The HouseSpec contract stores right-handed XYZ Euler components.  Unreal
    # names rotations by their axis instead: roll=X, pitch=Y, yaw=Z.  Keep the
    # source axes intact when constructing an FRotator; in particular, the
    # common [0, 0, 90] doorway transform must become a 90 degree yaw rather
    # than tipping the door onto its side with a 90 degree roll.
    return unreal.Rotator(pitch=values[1], yaw=values[2], roll=values[0])


def normalized_number(value):
    rounded = round(float(value), 3)
    return 0.0 if rounded == -0.0 else rounded


def normalized_angle(value):
    normalized = (float(value) + 180.0) % 360.0 - 180.0
    return normalized_number(normalized)


def observed_actor_transform(actor):
    location = actor.get_actor_location()
    actor_rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return {
        "location_cm": [
            normalized_number(location.x),
            normalized_number(location.y),
            normalized_number(location.z),
        ],
        "rotation_deg": [
            normalized_angle(actor_rotation.roll),
            normalized_angle(actor_rotation.pitch),
            normalized_angle(actor_rotation.yaw),
        ],
        "scale": [
            normalized_number(scale.x),
            normalized_number(scale.y),
            normalized_number(scale.z),
        ],
    }


def normalized_profile_transform(value):
    return {
        "location_cm": [normalized_number(item) for item in value["location_cm"]],
        "rotation_deg": [normalized_angle(item) for item in value["rotation_deg"]],
        "scale": [normalized_number(item) for item in value["scale"]],
    }


def transform(value):
    return unreal.Transform(
        location=vector(value["location_cm"]),
        rotation=rotation(value["rotation_deg"]),
        scale=vector(value["scale"]),
    )


def safe_label(semantic_id):
    return (
        "VISTA_"
        + "".join(
            character if character.isalnum() else "_" for character in semantic_id
        )[:180]
    )


def load_import_receipt(execution):
    expected_sha = require_sha(
        os.environ.get(IMPORT_RECEIPT_SHA_ENV, ""), "import receipt"
    )
    path = canonical_path(execution["import_receipt"])
    require(
        os.path.isfile(path) and sha256_file(path) == expected_sha,
        "import receipt pin mismatch",
    )
    with open(path, "r", encoding="utf-8") as source:
        receipt = json.load(source)
    require(
        receipt.get("schema_version") == IMPORT_RECEIPT_SCHEMA
        and receipt.get("status") == "imported_candidate",
        "import did not reach candidate state",
    )
    require(
        receipt.get("content_namespace")
        == execution["composition_spec"]["content_namespace"],
        "import namespace mismatch",
    )
    require(
        receipt.get("bindings", {}).get("execution_manifest_sha256")
        == os.environ["VISTA_PLAYABLE_HOME_EXECUTION_SHA256"],
        "import receipt execution binding mismatch",
    )
    return receipt, path, expected_sha


def verify_runtime(execution):
    engine = str(unreal.SystemLibrary.get_engine_version())
    require(engine.startswith("5."), "Unreal Engine major version mismatch")
    project = canonical_path(unreal.Paths.get_project_file_path())
    require(
        project == canonical_path(execution["project_file"]),
        "loaded project identity mismatch",
    )
    require(
        sha256_file(project) == execution["project_sha256"],
        "loaded project digest mismatch",
    )
    plugin_class = unreal.load_class(
        None, "/Script/VistaPlayableHome.VistaPlayableHomeGameMode"
    )
    require(
        plugin_class is not None,
        "VistaPlayableHome compiled plugin is not loaded in this project",
    )
    return engine, project


def set_tags(actor, tags):
    actor.set_editor_property("tags", [unreal.Name(tag) for tag in sorted(tags)])


def set_if_present(value, name, setting):
    try:
        value.set_editor_property(name, setting)
        return True
    except Exception:
        return False


def set_required(value, name, setting):
    require(
        set_if_present(value, name, setting),
        "required Unreal property is unavailable: " + name,
    )


def required_bool_property(value, name, label):
    try:
        observed = value.get_editor_property(name)
    except Exception as exc:
        raise RuntimeError(label + " property is unavailable: " + name) from exc
    require(isinstance(observed, bool), label + " property is not boolean: " + name)
    return observed


def static_mesh_component(actor):
    try:
        component = actor.get_editor_property("static_mesh_component")
        if component:
            return component
    except Exception:
        pass
    try:
        component = actor.get_editor_property("mesh")
        if isinstance(component, unreal.StaticMeshComponent):
            return component
    except Exception:
        pass
    components = actor.get_components_by_class(unreal.StaticMeshComponent)
    return components[0] if components else None


def light_component(actor):
    components = actor.get_components_by_class(unreal.LightComponentBase)
    return components[0] if components else None


def reject_json_constant(value):
    raise RuntimeError("R4 materialized profile contains non-finite JSON: " + value)


def reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "R4 materialized profile contains duplicate keys")
        result[key] = value
    return result


def load_materialized_r4_profile(execution):
    descriptor = execution.get("realism_r4_profile")
    require(
        isinstance(descriptor, dict)
        and set(descriptor)
        == {
            "path",
            "sha256",
            "source_sha256",
            "schema_version",
            "profile_id",
            "content_digest",
            "runtime_visual_acceptance",
            "gta_quality_accepted",
        },
        "R4 materialized profile descriptor differs",
    )
    attempt_root = canonical_path(execution["attempt_root"])
    path = safe_attempt_child(
        descriptor["path"], attempt_root, "R4 materialized profile"
    )
    contracts_root = canonical_path(os.path.join(attempt_root, "contracts"))
    require(
        os.path.dirname(path) == contracts_root
        and os.path.basename(path) == "realism-r4-profile.json"
        and not os.path.islink(path),
        "R4 materialized profile path is not the fixed contracts child",
    )
    expected_sha = require_sha(descriptor["sha256"], "R4 materialized profile")
    require_sha(descriptor["source_sha256"], "R4 source profile")
    try:
        descriptor_fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise RuntimeError("R4 materialized profile cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor_fd)
        require(
            stat.S_ISREG(before.st_mode)
            and before.st_nlink == 1
            and before.st_size <= 4 * 1024 * 1024,
            "R4 materialized profile has unsafe metadata",
        )
        chunks = []
        while True:
            block = os.read(descriptor_fd, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
            require(
                sum(len(chunk) for chunk in chunks) <= 4 * 1024 * 1024,
                "R4 materialized profile is oversized",
            )
        raw = b"".join(chunks)
        after = os.fstat(descriptor_fd)
        require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and len(raw) == before.st_size,
            "R4 materialized profile changed while being read",
        )
    finally:
        os.close(descriptor_fd)
    require(
        hashlib.sha256(raw).hexdigest() == expected_sha,
        "R4 materialized profile digest differs from execution",
    )
    try:
        profile = json.loads(
            raw.decode("utf-8", "strict"),
            parse_constant=reject_json_constant,
            object_pairs_hook=reject_duplicate_json_keys,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("R4 materialized profile is not strict JSON") from exc
    require(
        isinstance(profile, dict) and raw == canonical_json(profile),
        "R4 materialized profile is not canonical JSON",
    )
    body = dict(profile)
    content_digest = body.pop("content_digest", None)
    require(
        isinstance(content_digest, str)
        and hashlib.sha256(canonical_json(body)).hexdigest() == content_digest,
        "R4 materialized profile content digest differs",
    )
    require(
        descriptor["schema_version"] == REALISM_R4_PROFILE_SCHEMA
        and descriptor["profile_id"] == REALISM_R4_PROFILE_ID
        and descriptor["content_digest"] == content_digest
        and descriptor["runtime_visual_acceptance"] is False
        and descriptor["gta_quality_accepted"] is False,
        "R4 materialized profile descriptor identity differs",
    )
    require(
        profile == execution.get("realism_r4_composition"),
        "R4 materialized profile differs from embedded composition",
    )
    return profile


def validate_r4_profile(execution, spec):
    profile = load_materialized_r4_profile(execution)
    require(
        profile.get("schema_version") == REALISM_R4_PROFILE_SCHEMA
        and profile.get("profile_id") == REALISM_R4_PROFILE_ID
        and profile.get("base_visual_profile", {}).get("visual_profile_id")
        == spec.get("visual_profile_id")
        and profile.get("base_visual_profile", {}).get("content_digest")
        == spec.get("visual_profile_content_digest"),
        "R4 execution profile identity differs",
    )
    renderer = profile.get("renderer_contract")
    require(
        renderer
        == {
            "dynamic_gi": "software_lumen",
            "reflections": "lumen",
            "anti_aliasing": "tsr",
            "shadow_method": "virtual_shadow_maps",
            "hardware_ray_tracing": False,
            "config_is_runtime_proof": False,
        },
        "R4 renderer contract does not preserve software Lumen, TSR, and VSM",
    )
    pairs = profile.get("practical_fixture_light_pairs")
    require(
        isinstance(pairs, list)
        and len(pairs) == 6
        and {pair.get("room_id") for pair in pairs} == REALISM_R4_ROOM_IDS
        and len({pair.get("pair_id") for pair in pairs}) == 6
        and len({pair.get("fixture", {}).get("fixture_id") for pair in pairs}) == 6
        and len({pair.get("light", {}).get("light_id") for pair in pairs}) == 6
        and all(
            pair.get("fixture", {}).get("cast_shadow") is True
            and pair.get("light", {}).get("cast_shadow") is True
            for pair in pairs
        ),
        "R4 profile does not contain six exact room fixture/light pairs",
    )
    post = profile.get("post_process")
    require(
        isinstance(post, dict)
        and float(post.get("motion_blur_amount")) == 0.0
        and float(post.get("chromatic_aberration_intensity")) == 0.0
        and float(post.get("film_grain_intensity")) == 0.0
        and 0.2 <= float(post.get("bloom_intensity")) <= 0.4
        and 0.0 <= float(post.get("vignette_intensity")) <= 0.15
        and float(post.get("exposure", {}).get("min_ev100"))
        < float(post.get("exposure", {}).get("max_ev100")),
        "R4 restrained post-process contract differs",
    )
    require(
        profile.get("shadow_policy")
        == {
            "visible_presentation_cast_shadow": True,
            "visible_presentation_cast_hidden_shadow": False,
            "hidden_collision_proxy_cast_shadow": False,
            "hidden_collision_proxy_cast_hidden_shadow": False,
        }
        and profile.get("claims")
        == {
            "runtime_visual_acceptance": False,
            "gta_quality_accepted": False,
            "runtime_play_proof": "pending",
        },
        "R4 shadow policy or non-acceptance claims differ",
    )
    return profile


def configure_r2_review_camera(camera, operation):
    require(
        operation["transform"]["rotation_deg"][0] == 0.0,
        "r2 look-at camera roll is not zero",
    )
    component = camera.get_editor_property("camera_component")
    set_required(component, "field_of_view", operation["fov_deg"])
    set_required(component, "constrain_aspect_ratio", True)
    set_required(component, "aspect_ratio", 16.0 / 9.0)
    set_required(component, "post_process_blend_weight", 1.0)
    exposure = operation["exposure"]
    require(
        exposure.get("mode") == "pinned_physical_camera",
        "r2 review camera exposure is not pinned physical camera",
    )
    settings = component.get_editor_property("post_process_settings")
    required_settings = {
        "override_auto_exposure_method": True,
        "auto_exposure_method": unreal.AutoExposureMethod.AEM_MANUAL,
        "override_auto_exposure_apply_physical_camera_exposure": True,
        "auto_exposure_apply_physical_camera_exposure": True,
        "override_camera_iso": True,
        "camera_iso": exposure["iso"],
        "override_camera_shutter_speed": True,
        "camera_shutter_speed": 1.0 / exposure["shutter_speed_s"],
        "override_depth_of_field_fstop": True,
        "depth_of_field_fstop": exposure["aperture_fstop"],
        "override_auto_exposure_bias": True,
        "auto_exposure_bias": exposure["exposure_compensation_ev"],
    }
    for name, setting in required_settings.items():
        set_required(settings, name, setting)
    set_required(component, "post_process_settings", settings)


def spawn_r2_lighting(actor_subsystem, operation, realism_r4_profile=None):
    require(
        operation.get("profile") == "neutral_day"
        and operation.get("light_mobility") == "movable"
        and operation.get("runtime_observation_required") is True,
        "unsupported r2 lighting profile",
    )
    rig_tag = "VistaLightingRig=" + operation["rig_id"]
    sun_spec = operation["sun"]
    sun = actor_subsystem.spawn_actor_from_class(
        unreal.DirectionalLight,
        unreal.Vector(0.0, 0.0, 500.0),
        rotation(sun_spec["rotation_deg"]),
        transient=False,
    )
    sky = actor_subsystem.spawn_actor_from_class(
        unreal.SkyLight,
        unreal.Vector(0.0, 0.0, 400.0),
        unreal.Rotator(),
        transient=False,
    )
    atmosphere = actor_subsystem.spawn_actor_from_class(
        unreal.SkyAtmosphere,
        unreal.Vector(0.0, 0.0, 0.0),
        unreal.Rotator(),
        transient=False,
    )
    require(
        sun is not None and sky is not None and atmosphere is not None,
        "failed to spawn r2 sun/sky/atmosphere",
    )
    sun.set_actor_label("VISTA_R2_DirectionalSun")
    sky.set_actor_label("VISTA_R2_SkyLight")
    atmosphere.set_actor_label("VISTA_R2_SkyAtmosphere")
    set_tags(sun, ["VistaRole=lighting", rig_tag, "VistaLightType=sun"])
    set_tags(sky, ["VistaRole=lighting", rig_tag, "VistaLightType=sky"])
    # Do not use VistaRole=lighting: the reload gate deliberately counts only
    # actors backed by LightComponents.
    set_tags(atmosphere, ["VistaRole=sky_atmosphere", rig_tag])
    sun_component = light_component(sun)
    sky_component = light_component(sky)
    require(
        sun_component is not None and sky_component is not None,
        "failed to resolve r2 sun/sky components",
    )
    sun_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    set_required(sun_component, "intensity", sun_spec["illuminance_lux"])
    set_required(sun_component, "use_temperature", True)
    set_required(sun_component, "temperature", sun_spec["temperature_k"])
    set_required(sun_component, "cast_shadows", True)
    set_required(sun_component, "atmosphere_sun_light", True)
    sky_spec = operation["sky"]
    require(sky_spec.get("source") == "real_time_capture", "unsupported r2 sky source")
    set_required(
        sky_component, "source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE
    )
    set_required(sky_component, "real_time_capture", True)
    set_required(sky_component, "intensity", sky_spec["sky_intensity"])
    created = [sun, sky, atmosphere]
    r4_pairs = (
        realism_r4_profile["practical_fixture_light_pairs"]
        if realism_r4_profile is not None
        else None
    )
    practical_inputs = (
        [(pair, pair["light"]) for pair in r4_pairs]
        if r4_pairs is not None
        else [(None, light) for light in operation["practical_lights"]]
    )
    for pair, light_spec in practical_inputs:
        if pair is not None:
            fixture_spec = pair["fixture"]
            fixture_mesh = unreal.load_asset(fixture_spec["mesh_object_path"])
            require(
                isinstance(fixture_mesh, unreal.StaticMesh),
                "R4 practical fixture mesh is unavailable",
            )
            fixture = actor_subsystem.spawn_actor_from_class(
                unreal.StaticMeshActor,
                vector(fixture_spec["location_cm"]),
                rotation(fixture_spec["rotation_deg"]),
                transient=False,
            )
            require(fixture is not None, "failed to place R4 practical fixture")
            fixture.set_actor_scale3d(vector(fixture_spec["scale"]))
            fixture.set_actor_label(safe_label(fixture_spec["fixture_id"]))
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
            fixture_component = static_mesh_component(fixture)
            require(
                fixture_component is not None,
                "R4 practical fixture has no StaticMeshComponent",
            )
            fixture_component.set_static_mesh(fixture_mesh)
            fixture_component.set_collision_profile_name(unreal.Name("NoCollision"))
            fixture_component.set_simulate_physics(False)
            fixture_component.set_editor_property("generate_overlap_events", False)
            fixture_component.set_mobility(unreal.ComponentMobility.STATIC)
            fixture_component.set_cast_shadow(True)
            fixture_component.set_cast_hidden_shadow(False)
            created.append(fixture)
        actor_class = (
            unreal.RectLight if light_spec["type"] == "rect" else unreal.SpotLight
        )
        practical = actor_subsystem.spawn_actor_from_class(
            actor_class,
            vector(light_spec["location_cm"]),
            rotation(light_spec["rotation_deg"]),
            transient=False,
        )
        require(practical is not None, "failed to place r2 practical light")
        if pair is not None:
            practical.set_actor_scale3d(vector(light_spec["scale"]))
        practical.set_actor_label(safe_label(light_spec["light_id"]))
        light_tags = (
            [
                "VistaSemanticId=" + light_spec["light_id"],
                "VistaRoom=" + pair["room_id"],
                "VistaRole=lighting",
                "VistaR4Pair=" + pair["pair_id"],
                "VistaPracticalLightId=" + light_spec["light_id"],
                "VistaFixtureId=" + pair["fixture"]["fixture_id"],
            ]
            if pair is not None
            else list(light_spec["tags"])
        )
        set_tags(practical, light_tags + [rig_tag])
        component = light_component(practical)
        require(component is not None, "failed to resolve r2 practical light component")
        component.set_mobility(unreal.ComponentMobility.MOVABLE)
        set_required(component, "intensity", light_spec["intensity"])
        set_required(component, "use_temperature", True)
        set_required(component, "temperature", light_spec["temperature_k"])
        set_required(component, "cast_shadows", True)
        if pair is not None:
            set_required(
                component,
                "attenuation_radius",
                light_spec["attenuation_radius_cm"],
            )
        unit_name = "LUMENS" if light_spec["unit"] == "lumens" else "CANDELAS"
        set_required(
            component, "intensity_units", getattr(unreal.LightUnits, unit_name)
        )
        created.append(practical)

    post_profile = (
        realism_r4_profile["post_process"] if realism_r4_profile is not None else None
    )
    exposure = (
        post_profile["exposure"]
        if post_profile is not None
        else operation["gameplay_exposure"]
    )
    post = actor_subsystem.spawn_actor_from_class(
        unreal.PostProcessVolume, unreal.Vector(), unreal.Rotator(), transient=False
    )
    require(post is not None, "failed to place r2 gameplay post process")
    post.set_actor_label(
        "VISTA_R4_PostProcess"
        if realism_r4_profile is not None
        else "VISTA_R2_PostProcess"
    )
    set_tags(
        post,
        [
            "VistaRole=post_process",
            rig_tag,
            "VistaExposureProfile=bounded_histogram",
            *(
                ["VistaRealismProfile=" + REALISM_R4_PROFILE_ID]
                if realism_r4_profile is not None
                else []
            ),
        ],
    )
    set_required(post, "unbound", True)
    set_required(post, "priority", 100.0)
    set_required(post, "blend_weight", 1.0)
    settings = post.get_editor_property("settings")
    required_exposure = {
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
    }
    for name, setting in required_exposure.items():
        set_required(settings, name, setting)
    if post_profile is not None:
        restrained_settings = {
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
        for name, setting in restrained_settings.items():
            set_required(settings, name, setting)
    set_required(post, "settings", settings)
    created.append(post)
    return created


def spawn(actor_subsystem, actor_class, value_transform, label, tags):
    actor = actor_subsystem.spawn_actor_from_class(
        actor_class,
        vector(value_transform["location_cm"]),
        rotation(value_transform["rotation_deg"]),
        transient=False,
    )
    require(actor is not None, "failed to spawn " + label)
    actor.set_actor_scale3d(vector(value_transform["scale"]))
    actor.set_actor_label(label)
    set_tags(actor, tags)
    return actor


def asset_objects(import_receipt):
    result = {}
    for entry in import_receipt["assets"]:
        require(entry["asset_id"] not in result, "duplicate asset in import receipt")
        object_path = entry["object_path"]
        loaded = (
            unreal.load_class(None, object_path)
            if object_path.startswith("/Script/")
            else unreal.load_asset(object_path)
        )
        require(loaded is not None, "receipt asset unavailable: " + object_path)
        result[entry["asset_id"]] = {"object": loaded, "object_path": object_path}
    return result


def apply_entity_properties(actor, operation, asset_entry):
    semantic_id = operation["semantic_id"]
    set_if_present(actor, "semantic_id", semantic_id)
    set_if_present(
        actor, "world_revision", unreal.Name(operation.get("world_revision", ""))
    )
    component = static_mesh_component(actor)
    asset = asset_entry["object"]
    if component and isinstance(asset, unreal.StaticMesh):
        component.set_static_mesh(asset)
        collision = operation["collision"]
        component.set_collision_profile_name(unreal.Name(collision["profile"]))
        # UE 5.7 no longer exposes UPrimitiveComponent::SetGenerateOverlapEvents
        # as a Python method.  The reflected property remains writable and is
        # the commandlet-safe API (it does not require an editor UI).
        component.set_editor_property(
            "generate_overlap_events", bool(collision["generate_overlap"])
        )
        component.set_simulate_physics(collision["simulate_physics"])
        mobility = operation["mobility"]
        component.set_mobility(
            unreal.ComponentMobility.STATIC
            if mobility == "static"
            else unreal.ComponentMobility.MOVABLE
        )
        set_if_present(
            component, "can_ever_affect_navigation", bool(operation["nav_obstacle"])
        )
    baseline = operation["baseline_state"]
    set_if_present(
        actor,
        "initial_state_values",
        {
            unreal.Name(key): str(value).lower()
            if isinstance(value, bool)
            else str(value)
            for key, value in baseline.items()
        },
    )
    # Runtime actors that do not derive from AVistaSemanticActor (notably the
    # resident NPC) do not consume InitialStateValues in BeginPlay.  Apply the
    # compiled visibility baseline directly so event-only actors cannot leak
    # into the exploration scene before an event explicitly reveals them.
    actor.set_actor_hidden_in_game(not bool(baseline.get("visible", True)))
    if operation["component_role"] in {"door", "container"}:
        set_if_present(actor, "initially_open", bool(baseline.get("open", False)))
    if operation["component_role"] == "container":
        handle_target = actor.get_editor_property("handle_target")
        require(handle_target is not None, "container handle target is unavailable")
        handle_target.set_editor_property(
            "relative_location", vector([0.0, -31.0, 110.0])
        )
    runtime_affordances = list(operation["affordances"])
    if operation["component_role"] == "appliance":
        category = operation["category"]
        runtime_profile = APPLIANCE_RUNTIME_PROFILES.get(category)
        initially_active = bool(baseline.get("active", False))
        initially_powered = bool(baseline.get("powered", True))
        set_if_present(
            actor,
            "initially_on",
            initially_active,
        )
        set_if_present(actor, "initially_powered", initially_powered)
        set_if_present(actor, "appliance_kind", unreal.Name(category))
        if runtime_profile is not None:
            control_style = getattr(
                unreal.VistaApplianceControlStyle,
                runtime_profile["control_style"].upper(),
            )
            require(
                set_if_present(actor, "control_style", control_style),
                "known appliance category lacks the R15 control style property",
            )
            control_target = actor.get_editor_property("control_target")
            require(
                control_target is not None,
                "known appliance category lacks the R15 control target",
            )
            control_target.set_editor_property(
                "relative_location",
                vector(runtime_profile["control_target_local_cm"]),
            )
            initial_status = baseline.get(
                "status",
                runtime_profile[
                    "active_status" if initially_active else "inactive_status"
                ],
            )
            set_if_present(actor, "initial_status", unreal.Name(initial_status))
            activity_profile = unreal.VistaApplianceActivityProfile()
            activity_profile.set_editor_property(
                "active_status", unreal.Name(runtime_profile["active_status"])
            )
            activity_profile.set_editor_property(
                "inactive_status", unreal.Name(runtime_profile["inactive_status"])
            )
            require(
                set_if_present(actor, "activity_profile", activity_profile),
                "known appliance category lacks the R18 activity profile property",
            )
            if runtime_profile["press"] is not None:
                press_source = runtime_profile["press"]
                press_profile = unreal.VistaAppliancePressProfile()
                press_profile.set_editor_property(
                    "control_id", unreal.Name(press_source["control_id"])
                )
                press_profile.set_editor_property(
                    "result_active", bool(press_source["result_active"])
                )
                press_profile.set_editor_property(
                    "result_status", unreal.Name(press_source["result_status"])
                )
                require(
                    set_if_present(actor, "press_profile", press_profile),
                    "washer lacks the R18 press profile property",
                )
            runtime_affordances.extend(runtime_profile["extra_affordances"])
    if operation["component_role"] == "pickup":
        set_if_present(actor, "portable", bool(baseline.get("portable", True)))
    if operation["component_role"] == "npc":
        set_if_present(actor, "semantic_id", semantic_id)
        profile = operation["npc_profile"]
        require(
            set_if_present(
                actor,
                "patrol_target_semantic_ids",
                list(profile["patrol_target_semantic_ids"]),
            ),
            "NPC patrol targets property is unavailable",
        )
        require(
            set_if_present(
                actor,
                "patrol_action_timeout_seconds",
                float(profile["action_timeout_s"]),
            ),
            "NPC patrol timeout property is unavailable",
        )
        require(
            set_if_present(actor, "auto_start_patrol", False),
            "NPC auto-patrol property is unavailable",
        )
    try:
        enum_values = [
            getattr(unreal.VistaAffordance, name.upper())
            for name in dict.fromkeys(runtime_affordances)
        ]
        set_if_present(actor, "allowed_affordances", enum_values)
    except Exception as exc:
        require(
            not runtime_affordances,
            "failed to bind typed affordances: " + str(exc),
        )


LEGACY_AXIS_MAPPINGS = {
    ("MoveForward", "W", 1.0),
    ("MoveForward", "S", -1.0),
    ("MoveRight", "D", 1.0),
    ("MoveRight", "A", -1.0),
    ("Turn", "MouseX", 1.0),
    ("LookUp", "MouseY", -1.0),
}
LEGACY_ACTION_MAPPINGS = {
    ("Jump", "SpaceBar"),
    ("Sprint", "LeftShift"),
    ("Crouch", "C"),
    ("Interact", "E"),
    ("Drop", "Q"),
    ("Inspect", "I"),
    ("ExitInspect", "Escape"),
}


def verify_legacy_input_mappings():
    settings = unreal.InputSettings.get_input_settings()
    existing_axes = {
        (
            str(item.get_editor_property("axis_name")),
            str(item.get_editor_property("key").get_editor_property("key_name")),
            float(item.get_editor_property("scale")),
        )
        for item in settings.get_editor_property("axis_mappings")
    }
    existing_actions = {
        (
            str(item.get_editor_property("action_name")),
            str(item.get_editor_property("key").get_editor_property("key_name")),
        )
        for item in settings.get_editor_property("action_mappings")
    }
    require(
        LEGACY_AXIS_MAPPINGS.issubset(existing_axes),
        "DefaultInput.ini is missing required axis mappings",
    )
    require(
        LEGACY_ACTION_MAPPINGS.issubset(existing_actions),
        "DefaultInput.ini is missing required action mappings",
    )


def event_definitions(plan, assets, room_anchor_ids):
    operation_types = {
        "spawn_fixture": unreal.VistaEventOperationType.SPAWN_FIXTURE,
        "set_transform": unreal.VistaEventOperationType.SET_TRANSFORM,
        "set_state": unreal.VistaEventOperationType.SET_STATE,
        "set_visibility": unreal.VistaEventOperationType.SET_VISIBILITY,
        "set_portable": unreal.VistaEventOperationType.SET_PORTABLE,
        "set_npc_queue": unreal.VistaEventOperationType.SET_NPC_QUEUE,
        "set_goal": unreal.VistaEventOperationType.SET_GOAL,
    }
    action_types = {
        "navigate_to": unreal.VistaNpcActionType.NAVIGATE_TO,
        "look_at": unreal.VistaNpcActionType.LOOK_AT,
        "pick_up": unreal.VistaNpcActionType.PICK_UP,
        "place": unreal.VistaNpcActionType.PLACE,
        "drop": unreal.VistaNpcActionType.DROP,
        "open_door": unreal.VistaNpcActionType.OPEN_DOOR,
        "open": unreal.VistaNpcActionType.OPEN_DOOR,
        "close_door": unreal.VistaNpcActionType.CLOSE_DOOR,
        "close": unreal.VistaNpcActionType.CLOSE_DOOR,
        "sit": unreal.VistaNpcActionType.SIT,
        "inspect": unreal.VistaNpcActionType.INSPECT,
        "wait": unreal.VistaNpcActionType.WAIT,
        "speak": unreal.VistaNpcActionType.SPEAK,
        "brace": unreal.VistaNpcActionType.BRACE,
        "drag": unreal.VistaNpcActionType.DRAG,
        "lift_foot": unreal.VistaNpcActionType.LIFT_FOOT,
        "pause": unreal.VistaNpcActionType.PAUSE,
        "fall": unreal.VistaNpcActionType.FALL,
        "recover": unreal.VistaNpcActionType.RECOVER,
        # EventSpec v3 source mappings are deliberately fail-closed.  These
        # names document the compiler contract, but a commandlet run may use
        # them only after the loaded plugin exposes a matching native enum.
        # Presence here is not a runtime-acceptance receipt.
        "toggle": getattr(unreal.VistaNpcActionType, "TOGGLE", None),
        "press": getattr(unreal.VistaNpcActionType, "PRESS", None),
        "turn_on": getattr(unreal.VistaNpcActionType, "TURN_ON", None),
        "turn_off": getattr(unreal.VistaNpcActionType, "TURN_OFF", None),
    }
    condition_types = {
        "entity_state": unreal.VistaEventConditionType.ENTITY_STATE,
        "entity_room": unreal.VistaEventConditionType.ENTITY_ROOM,
        "player_room": unreal.VistaEventConditionType.PLAYER_ROOM,
        "interaction": unreal.VistaEventConditionType.INTERACTION,
        "elapsed": unreal.VistaEventConditionType.ELAPSED,
    }
    condition_operators = {
        "eq": unreal.VistaEventConditionOperator.EQ,
        "gte": unreal.VistaEventConditionOperator.GTE,
    }
    affordances = {
        "open": unreal.VistaAffordance.OPEN,
        "close": unreal.VistaAffordance.CLOSE,
        "pick_up": unreal.VistaAffordance.PICK_UP,
        "drop": unreal.VistaAffordance.DROP,
        "place": unreal.VistaAffordance.PLACE,
        "toggle": unreal.VistaAffordance.TOGGLE,
        "sit": unreal.VistaAffordance.SIT,
        "inspect": unreal.VistaAffordance.INSPECT,
    }
    rooms = {room["room_id"]: room for room in plan["rooms"]}

    def materialize_condition(source):
        condition = unreal.VistaEventCondition()
        condition.set_editor_property(
            "condition_id", unreal.Name(source["condition_id"])
        )
        condition.set_editor_property("type", condition_types[source["type"]])
        condition.set_editor_property("target_semantic_id", source.get("target_id", ""))
        condition.set_editor_property("room_semantic_id", source.get("room_id", ""))
        condition.set_editor_property(
            "field_name", unreal.Name(source.get("field", ""))
        )
        condition.set_editor_property(
            "operator", condition_operators[source.get("operator", "eq")]
        )
        expected = source.get("value", "")
        if isinstance(expected, bool):
            expected = str(expected).lower()
        condition.set_editor_property("expected_value", str(expected))
        condition.set_editor_property("seconds", float(source.get("seconds", 0.0)))
        condition.set_editor_property(
            "affordance", affordances[source.get("affordance", "inspect")]
        )
        if source.get("room_id"):
            require(source["room_id"] in rooms, "event condition room is unknown")
            bounds = rooms[source["room_id"]]["world_bounds_cm"]
            condition.set_editor_property("room_min_cm", vector(bounds["min_cm"]))
            condition.set_editor_property("room_max_cm", vector(bounds["max_cm"]))
        return condition

    definitions = []
    for event_plan in plan["event_plans"]:
        definition = unreal.VistaEventDefinition()
        definition.set_editor_property("event_id", unreal.Name(event_plan["event_id"]))
        definition.set_editor_property(
            "compatible_revision", unreal.Name(plan["house"]["revision"])
        )
        definition.set_editor_property("public_title", event_plan["title"])
        public_goals = sorted(
            event_plan["public_goals"], key=lambda goal: goal["goal_id"]
        )
        definition.set_editor_property(
            "public_goal",
            " ".join(goal["description"] for goal in public_goals),
        )
        definition.set_editor_property(
            "timeout_seconds", min(float(event_plan["timeout_s"]), 3600.0)
        )
        definition.set_editor_property(
            "triggers", [materialize_condition(item) for item in event_plan["triggers"]]
        )
        definition.set_editor_property(
            "success_conditions",
            [materialize_condition(item) for item in event_plan["success_conditions"]],
        )
        definition.set_editor_property(
            "failure_conditions",
            [materialize_condition(item) for item in event_plan["failure_conditions"]],
        )
        operations = []
        for op_index, source_op in enumerate(event_plan["operations"]):
            operation = unreal.VistaEventOperation()
            operation.set_editor_property(
                "operation_id", unreal.Name(source_op["op_id"])
            )
            operation.set_editor_property("type", operation_types[source_op["op"]])
            target_id = source_op.get("target_id", source_op.get("entity_id", ""))
            operation.set_editor_property("target_semantic_id", target_id)
            if "world_transform_cm" in source_op:
                operation.set_editor_property(
                    "transform", transform(source_op["world_transform_cm"])
                )
            if source_op["op"] == "set_state":
                operation.set_editor_property(
                    "state_values",
                    {
                        unreal.Name(key): str(value).lower()
                        if isinstance(value, bool)
                        else str(value)
                        for key, value in source_op["state_patch"].items()
                    },
                )
            elif source_op["op"] in {"set_visibility", "set_portable"}:
                operation.set_editor_property(
                    "boolean_value",
                    bool(
                        source_op["visible"]
                        if source_op["op"] == "set_visibility"
                        else source_op["portable"]
                    ),
                )
            elif source_op["op"] == "spawn_fixture":
                fixture = assets[source_op["asset"]["asset_id"]]["object"]
                require(
                    isinstance(fixture, unreal.Class),
                    "spawn fixture asset must resolve to an allowlisted class",
                )
                operation.set_editor_property("fixture_class", fixture)
            elif source_op["op"] == "set_npc_queue":
                npc_actions = []
                for action_index, source_action in enumerate(source_op["actions"]):
                    mapped_action_type = action_types[source_action["action"]]
                    require(
                        mapped_action_type is not None,
                        "NPC action has source mapping but no runtime-authorized enum: "
                        + source_action["action"],
                    )
                    action = unreal.VistaNpcAction()
                    action.set_editor_property(
                        "action_id",
                        unreal.Name("%s_%02d" % (source_op["op_id"], action_index)),
                    )
                    action.set_editor_property("type", mapped_action_type)
                    target = source_action.get("target_id", "")
                    if not target and source_action.get("room_id"):
                        target = room_anchor_ids[source_action["room_id"]]
                    action.set_editor_property("target_semantic_id", target)
                    action.set_editor_property(
                        "duration_seconds", float(source_action.get("duration_s", 0.0))
                    )
                    action.set_editor_property(
                        "distance_cm", float(source_action.get("distance_cm", 0.0))
                    )
                    action.set_editor_property(
                        "height_cm", float(source_action.get("height_cm", 0.0))
                    )
                    action.set_editor_property(
                        "timeout_seconds", min(float(event_plan["timeout_s"]), 60.0)
                    )
                    action.set_editor_property(
                        "speech", source_action.get("utterance", "")
                    )
                    npc_actions.append(action)
                operation.set_editor_property("npc_actions", npc_actions)
            operations.append(operation)
        definition.set_editor_property("initial_operations", operations)
        definitions.append(definition)
    return definitions


def actor_record(actor):
    return {
        "label": str(actor.get_actor_label()),
        "class_path": str(actor.get_class().get_path_name()),
        "path": str(actor.get_path_name()),
        "tags": sorted(str(tag) for tag in actor.get_editor_property("tags")),
    }


def run():
    execution, manifest_path, manifest_sha = load_execution("compose", __file__)
    plan = load_build_plan(execution)
    import_receipt, import_path, import_sha = load_import_receipt(execution)
    engine, project = verify_runtime(execution)
    input_config = canonical_path(
        os.path.join(os.path.dirname(project), "Config", "DefaultInput.ini")
    )
    require(os.path.isfile(input_config), "DefaultInput.ini is missing")
    input_config_sha = sha256_file(input_config)
    spec = execution["composition_spec"]
    is_r2 = "visual_profile_id" in spec
    has_r4_profile = "realism_r4_profile" in execution
    has_r4_composition = "realism_r4_composition" in execution
    require(
        has_r4_profile == has_r4_composition,
        "R4 execution profile/composition presence differs",
    )
    is_r4 = has_r4_composition
    r4_profile = validate_r4_profile(execution, spec) if is_r4 else None
    map_path = spec["map_path"]
    require(
        not unreal.EditorAssetLibrary.does_asset_exist(map_path),
        "target map already exists",
    )
    assets = asset_objects(import_receipt)
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    require(level_subsystem.new_level(map_path), "failed to create fresh target map")
    world = unreal.EditorLevelLibrary.get_editor_world()
    require(world is not None, "new map world unavailable")
    world_settings = world.get_world_settings()
    require(world_settings is not None, "new map world settings unavailable")
    world_settings.set_editor_property("force_no_precomputed_lighting", True)
    created = []
    status = "failed_unsaved_quarantined"
    error = None
    reload_verified = False
    dynamic_lighting_verified = False
    deterministic_exposure_verified = False
    input_mappings_verified = False
    r4_fixture_light_pairs_verified = False
    r4_restrained_post_process_verified = False
    r4_renderer_contract_preserved = False
    r4_observation = None
    stage = {"phase": "compose_operations", "operation_id": None, "kind": None}
    try:
        for operation in spec["operations"]:
            kind = operation["kind"]
            stage = {
                "phase": "compose_operation",
                "operation_id": operation["operation_id"],
                "kind": kind,
            }
            if kind == "place_room_bundle":
                actor = spawn(
                    actor_subsystem,
                    unreal.StaticMeshActor,
                    operation["transform"],
                    safe_label(operation["semantic_id"]),
                    operation["tags"],
                )
                mesh = assets[operation["asset"]["asset_id"]]["object"]
                require(
                    isinstance(mesh, unreal.StaticMesh),
                    "room bundle is not a StaticMesh",
                )
                component = static_mesh_component(actor)
                component.set_static_mesh(mesh)
                component.set_collision_profile_name(unreal.Name("BlockAll"))
                component.set_mobility(unreal.ComponentMobility.STATIC)
                created.append(actor)
            elif kind in {"place_room_anchor", "place_portal_anchor"}:
                if "transform" in operation:
                    value_transform = operation["transform"]
                else:
                    value_transform = {
                        "location_cm": operation["location_cm"],
                        "rotation_deg": [0.0, 0.0, 0.0],
                        "scale": [1.0, 1.0, 1.0],
                    }
                created.append(
                    spawn(
                        actor_subsystem,
                        unreal.TargetPoint,
                        value_transform,
                        safe_label(operation["semantic_id"]),
                        operation["tags"],
                    )
                )
            elif kind == "place_review_camera":
                camera = spawn(
                    actor_subsystem,
                    unreal.CameraActor,
                    operation["transform"],
                    safe_label(operation["semantic_id"]),
                    operation["tags"],
                )
                if "review_shot_id" in operation:
                    configure_r2_review_camera(camera, operation)
                else:
                    camera.get_editor_property("camera_component").set_editor_property(
                        "field_of_view", operation["fov_deg"]
                    )
                created.append(camera)
            elif kind == "place_entity":
                actor_class = unreal.load_class(None, operation["actor_class"])
                require(actor_class is not None, "typed gameplay class unavailable")
                actor = spawn(
                    actor_subsystem,
                    actor_class,
                    operation["transform"],
                    safe_label(operation["semantic_id"]),
                    operation["tags"],
                )
                operation["world_revision"] = plan["house"]["revision"]
                apply_entity_properties(
                    actor, operation, assets[operation["asset"]["asset_id"]]
                )
                created.append(actor)
            elif kind == "place_placement_anchor":
                created.append(
                    spawn(
                        actor_subsystem,
                        unreal.TargetPoint,
                        operation["transform"],
                        safe_label(operation["semantic_id"]),
                        operation["tags"],
                    )
                )
            elif kind == "place_player_start":
                created.append(
                    spawn(
                        actor_subsystem,
                        unreal.PlayerStart,
                        operation["transform"],
                        "VISTA_PlayerStart",
                        operation["tags"],
                    )
                )
            elif kind == "place_lighting":
                require(
                    operation.get("profile") == "vista_playable_home_neutral_day_v2"
                    and operation.get("light_mobility") == "movable",
                    "unsupported lighting profile",
                )
                exposure = operation.get("exposure", {})
                require(
                    exposure.get("method") == "manual"
                    and exposure.get("apply_physical_camera_exposure") is False
                    and float(exposure.get("bias")) == -6.0,
                    "unsupported exposure profile",
                )
                directional = actor_subsystem.spawn_actor_from_class(
                    unreal.DirectionalLight,
                    unreal.Vector(0.0, 0.0, 500.0),
                    unreal.Rotator(pitch=-35.0, yaw=-45.0, roll=0.0),
                    transient=False,
                )
                skylight = actor_subsystem.spawn_actor_from_class(
                    unreal.SkyLight,
                    unreal.Vector(0.0, 0.0, 400.0),
                    unreal.Rotator(),
                    transient=False,
                )
                directional.set_actor_label("VISTA_DirectionalLight")
                skylight.set_actor_label("VISTA_SkyLight")
                set_tags(directional, ["VistaRole=lighting"])
                set_tags(skylight, ["VistaRole=lighting"])
                directional_component = light_component(directional)
                skylight_component = light_component(skylight)
                require(
                    directional_component is not None
                    and skylight_component is not None,
                    "failed to resolve deterministic environment lights",
                )
                directional_component.set_mobility(unreal.ComponentMobility.MOVABLE)
                skylight_component.set_mobility(unreal.ComponentMobility.MOVABLE)
                created.extend([directional, skylight])
                for light_spec in operation["indoor_lights"]:
                    point = actor_subsystem.spawn_actor_from_class(
                        unreal.PointLight,
                        vector(light_spec["location_cm"]),
                        unreal.Rotator(),
                        transient=False,
                    )
                    require(
                        point is not None, "failed to place deterministic indoor light"
                    )
                    point.set_actor_label(safe_label(light_spec["semantic_id"]))
                    set_tags(point, list(light_spec["tags"]) + ["VistaRole=lighting"])
                    component = point.get_editor_property("point_light_component")
                    component.set_mobility(unreal.ComponentMobility.MOVABLE)
                    component.set_editor_property("intensity", 3200.0)
                    component.set_editor_property(
                        "attenuation_radius", light_spec["attenuation_radius_cm"]
                    )
                    component.set_editor_property("use_temperature", True)
                    component.set_editor_property("temperature", 4000.0)
                    component.set_editor_property("cast_shadows", True)
                    created.append(point)
                post = actor_subsystem.spawn_actor_from_class(
                    unreal.PostProcessVolume,
                    unreal.Vector(),
                    unreal.Rotator(),
                    transient=False,
                )
                require(post is not None, "failed to place deterministic post process")
                post.set_actor_label("VISTA_PostProcess")
                set_tags(post, ["VistaRole=post_process"])
                post.set_editor_property("unbound", True)
                post.set_editor_property("priority", 100.0)
                post.set_editor_property("blend_weight", 1.0)
                settings = post.get_editor_property("settings")
                settings.set_editor_property("override_auto_exposure_method", True)
                settings.set_editor_property(
                    "auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL
                )
                settings.set_editor_property(
                    "override_auto_exposure_apply_physical_camera_exposure", True
                )
                settings.set_editor_property(
                    "auto_exposure_apply_physical_camera_exposure", False
                )
                settings.set_editor_property("override_auto_exposure_bias", True)
                settings.set_editor_property("auto_exposure_bias", exposure["bias"])
                post.set_editor_property("settings", settings)
                created.append(post)
            elif kind == "place_realistic_lighting":
                require(is_r2, "r2 lighting operation requires a visual profile")
                created.extend(
                    spawn_r2_lighting(
                        actor_subsystem,
                        operation,
                        realism_r4_profile=r4_profile,
                    )
                )
            elif kind == "configure_game_mode":
                game_mode_path = assets[operation["game_mode"]["asset_id"]][
                    "object_path"
                ]
                pawn_path = assets[operation["pawn"]["asset_id"]]["object_path"]
                require(
                    game_mode_path
                    == "/Script/VistaPlayableHome.VistaPlayableHomeGameMode"
                    and pawn_path
                    == "/Script/VistaPlayableHome.VistaPlayableHomeCharacter",
                    "runtime classes are not the fixed playable-home classes",
                )
                game_mode = unreal.load_class(None, game_mode_path)
                stage = {
                    "phase": "configure_game_mode_world_settings",
                    "operation_id": operation["operation_id"],
                    "kind": kind,
                }
                world.get_world_settings().set_editor_property(
                    "default_game_mode", game_mode
                )
                stage = {
                    "phase": "configure_game_mode_input",
                    "operation_id": operation["operation_id"],
                    "kind": kind,
                }
                verify_legacy_input_mappings()
                stage = {
                    "phase": "configure_game_mode_events",
                    "operation_id": operation["operation_id"],
                    "kind": kind,
                }
                definition_class = unreal.load_class(
                    None, "/Script/VistaPlayableHome.VistaEventDefinitionActor"
                )
                definition_actor = actor_subsystem.spawn_actor_from_class(
                    definition_class, unreal.Vector(), unreal.Rotator(), transient=False
                )
                definition_actor.set_actor_label("VISTA_EventDefinitions")
                room_anchor_ids = {
                    room["room_id"]: room["room_id"] + "/anchor.room_center"
                    for room in plan["rooms"]
                }
                definition_actor.set_editor_property(
                    "definitions", event_definitions(plan, assets, room_anchor_ids)
                )
                created.append(definition_actor)
            elif kind == "place_navmesh_bounds":
                bounds = operation["bounds"]
                center = [
                    (low + high) / 2.0
                    for low, high in zip(bounds["min_cm"], bounds["max_cm"])
                ]
                desired_extent = [
                    (high - low) / 2.0
                    for low, high in zip(bounds["min_cm"], bounds["max_cm"])
                ]
                nav = actor_subsystem.spawn_actor_from_class(
                    unreal.NavMeshBoundsVolume,
                    vector(center),
                    unreal.Rotator(),
                    transient=False,
                )
                nav.set_actor_label("VISTA_NavMeshBounds")
                origin, current_extent = nav.get_actor_bounds(False)
                require(
                    current_extent.x > 0
                    and current_extent.y > 0
                    and current_extent.z > 0,
                    "NavMesh volume default brush has invalid bounds",
                )
                nav.set_actor_scale3d(
                    unreal.Vector(
                        desired_extent[0] / current_extent.x,
                        desired_extent[1] / current_extent.y,
                        desired_extent[2] / current_extent.z,
                    )
                )
                set_tags(nav, ["VistaRole=navmesh_bounds"])
                navigation_system = unreal.NavigationSystemV1.get_navigation_system(
                    world
                )
                require(navigation_system is not None, "navigation system unavailable")
                navigation_system.on_navigation_bounds_updated(nav)
                created.append(nav)

        stage = {"phase": "save_map", "operation_id": None, "kind": None}
        require(
            unreal.EditorLoadingAndSavingUtils.save_map(world, map_path),
            "map save failed",
        )
        status = "saved_candidate"
        stage = {"phase": "reload_map", "operation_id": None, "kind": None}
        require(level_subsystem.load_level(map_path), "saved map reload failed")
        reloaded = actor_subsystem.get_all_level_actors()
        observed_tags = {
            str(tag) for actor in reloaded for tag in actor.get_editor_property("tags")
        }
        expected_tags = {
            spec["stable_tag_prefix"] + semantic_id
            for operation in spec["operations"]
            for semantic_id in (
                [operation["semantic_id"]] if "semantic_id" in operation else []
            )
        }
        require(
            expected_tags.issubset(observed_tags), "reloaded map lost semantic actors"
        )
        require(
            any(isinstance(actor, unreal.PlayerStart) for actor in reloaded),
            "reloaded map lost PlayerStart",
        )
        require(
            any(isinstance(actor, unreal.NavMeshBoundsVolume) for actor in reloaded),
            "reloaded map lost NavMesh bounds",
        )
        reloaded_world = unreal.EditorLevelLibrary.get_editor_world()
        require(
            reloaded_world is not None
            and reloaded_world.get_world_settings().get_editor_property(
                "force_no_precomputed_lighting"
            ),
            "reloaded map lost dynamic-lighting world policy",
        )
        vista_lights = [
            actor
            for actor in reloaded
            if unreal.Name("VistaRole=lighting") in actor.get_editor_property("tags")
        ]
        lighting_operation = next(
            operation
            for operation in spec["operations"]
            if operation["kind"] in {"place_lighting", "place_realistic_lighting"}
        )
        expected_light_count = 2 + len(
            r4_profile["practical_fixture_light_pairs"]
            if is_r4
            else lighting_operation["practical_lights"]
            if is_r2
            else lighting_operation["indoor_lights"]
        )
        require(
            len(vista_lights) == expected_light_count, "reloaded map lost VISTA lights"
        )
        require(
            all(
                light_component(actor) is not None
                and light_component(actor).get_editor_property("mobility")
                == unreal.ComponentMobility.MOVABLE
                for actor in vista_lights
            ),
            "reloaded map contains a non-movable VISTA light",
        )
        post_volumes = [
            actor
            for actor in reloaded
            if unreal.Name("VistaRole=post_process")
            in actor.get_editor_property("tags")
        ]
        require(
            len(post_volumes) == 1
            and post_volumes[0].get_editor_property("unbound")
            and float(post_volumes[0].get_editor_property("blend_weight")) == 1.0
            and float(post_volumes[0].get_editor_property("priority")) == 100.0,
            "reloaded map lost unbound VISTA post process",
        )
        post_settings = post_volumes[0].get_editor_property("settings")
        if is_r2:
            sky_lights = [
                actor
                for actor in vista_lights
                if unreal.Name("VistaLightType=sky")
                in actor.get_editor_property("tags")
            ]
            require(len(sky_lights) == 1, "reloaded r2 sky light set is not exact")
            sky_atmospheres = [
                actor
                for actor in reloaded
                if unreal.Name("VistaRole=sky_atmosphere")
                in actor.get_editor_property("tags")
            ]
            sun_lights = [
                actor
                for actor in vista_lights
                if unreal.Name("VistaLightType=sun")
                in actor.get_editor_property("tags")
            ]
            require(
                len(sky_atmospheres) == 1
                and isinstance(sky_atmospheres[0], unreal.SkyAtmosphere)
                and len(sun_lights) == 1
                and bool(
                    light_component(sun_lights[0]).get_editor_property(
                        "atmosphere_sun_light"
                    )
                ),
                "reloaded r2 sky atmosphere/sun binding is not exact",
            )
            reloaded_sky_component = light_component(sky_lights[0])
            sky_spec = lighting_operation["sky"]
            require(
                reloaded_sky_component is not None
                and sky_spec.get("source") == "real_time_capture"
                and reloaded_sky_component.get_editor_property("source_type")
                == unreal.SkyLightSourceType.SLS_CAPTURED_SCENE
                and bool(
                    reloaded_sky_component.get_editor_property("real_time_capture")
                )
                and math.isclose(
                    float(reloaded_sky_component.get_editor_property("intensity")),
                    float(sky_spec["sky_intensity"]),
                    rel_tol=0.0,
                    abs_tol=1e-6,
                ),
                "reloaded r2 sky lost captured-scene real-time intensity",
            )
            exposure = (
                r4_profile["post_process"]["exposure"]
                if is_r4
                else lighting_operation["gameplay_exposure"]
            )
            require(
                bool(post_settings.get_editor_property("override_auto_exposure_method"))
                and post_settings.get_editor_property("auto_exposure_method")
                == unreal.AutoExposureMethod.AEM_HISTOGRAM
                and float(
                    post_settings.get_editor_property("auto_exposure_min_brightness")
                )
                == exposure["min_ev100"]
                and float(
                    post_settings.get_editor_property("auto_exposure_max_brightness")
                )
                == exposure["max_ev100"]
                and float(post_settings.get_editor_property("auto_exposure_speed_up"))
                == exposure["speed_up"]
                and float(post_settings.get_editor_property("auto_exposure_speed_down"))
                == exposure["speed_down"],
                "reloaded map lost bounded histogram exposure",
            )
            if is_r4:
                post_profile = r4_profile["post_process"]
                effect_properties = {
                    "motion_blur_amount": post_profile["motion_blur_amount"],
                    "scene_fringe_intensity": post_profile[
                        "chromatic_aberration_intensity"
                    ],
                    "grain_intensity": post_profile["film_grain_intensity"],
                    "bloom_intensity": post_profile["bloom_intensity"],
                    "vignette_intensity": post_profile["vignette_intensity"],
                }
                require(
                    all(
                        required_bool_property(
                            post_settings,
                            "override_" + name,
                            "R4 post process",
                        )
                        and math.isclose(
                            float(post_settings.get_editor_property(name)),
                            float(expected),
                            rel_tol=0.0,
                            abs_tol=1e-6,
                        )
                        for name, expected in effect_properties.items()
                    ),
                    "reloaded map lost restrained R4 post process",
                )
                fixture_inventory = [
                    actor
                    for actor in reloaded
                    if unreal.Name("VistaRole=practical_fixture")
                    in actor.get_editor_property("tags")
                ]
                practical_light_inventory = [
                    actor
                    for actor in reloaded
                    if any(
                        str(tag).startswith("VistaPracticalLightId=")
                        for tag in actor.get_editor_property("tags")
                    )
                ]
                require(
                    len(fixture_inventory) == 6 and len(practical_light_inventory) == 6,
                    "reloaded R4 fixture/light inventory is not exactly six pairs",
                )
                expected_light_classes = {
                    "rect": "/Script/Engine.RectLight",
                    "spot": "/Script/Engine.SpotLight",
                }
                expected_light_units = {
                    "lumens": unreal.LightUnits.LUMENS,
                    "candelas": unreal.LightUnits.CANDELAS,
                }
                pair_observations = []
                observed_fixture_paths = set()
                observed_light_paths = set()
                for pair in sorted(
                    r4_profile["practical_fixture_light_pairs"],
                    key=lambda value: value["pair_id"],
                ):
                    pair_tag = unreal.Name("VistaR4Pair=" + pair["pair_id"])
                    fixture_tag = unreal.Name(
                        "VistaFixtureId=" + pair["fixture"]["fixture_id"]
                    )
                    light_tag = unreal.Name(
                        "VistaPracticalLightId=" + pair["light"]["light_id"]
                    )
                    fixture_matches = [
                        actor
                        for actor in reloaded
                        if pair_tag in actor.get_editor_property("tags")
                        and fixture_tag in actor.get_editor_property("tags")
                        and unreal.Name("VistaRole=practical_fixture")
                        in actor.get_editor_property("tags")
                    ]
                    light_matches = [
                        actor
                        for actor in vista_lights
                        if pair_tag in actor.get_editor_property("tags")
                        and light_tag in actor.get_editor_property("tags")
                    ]
                    require(
                        len(fixture_matches) == 1 and len(light_matches) == 1,
                        "reloaded R4 fixture/light pair is not exact",
                    )
                    fixture_actor = fixture_matches[0]
                    practical_actor = light_matches[0]
                    fixture_actor_path = str(fixture_actor.get_path_name())
                    practical_actor_path = str(practical_actor.get_path_name())
                    require(
                        fixture_actor_path not in observed_fixture_paths
                        and practical_actor_path not in observed_light_paths,
                        "reloaded R4 fixture/light actor is reused",
                    )
                    fixture_component = static_mesh_component(fixture_actor)
                    practical_component = light_component(practical_actor)
                    fixture_mesh = (
                        fixture_component.get_editor_property("static_mesh")
                        if fixture_component is not None
                        else None
                    )
                    fixture_cast_shadow = required_bool_property(
                        fixture_component, "cast_shadow", "R4 fixture"
                    )
                    fixture_cast_hidden_shadow = required_bool_property(
                        fixture_component, "cast_hidden_shadow", "R4 fixture"
                    )
                    light_cast_shadow = required_bool_property(
                        practical_component, "cast_shadows", "R4 practical light"
                    )
                    fixture_visible = required_bool_property(
                        fixture_component, "visible", "R4 fixture"
                    )
                    light_use_temperature = required_bool_property(
                        practical_component,
                        "use_temperature",
                        "R4 practical light",
                    )
                    fixture_transform = observed_actor_transform(fixture_actor)
                    practical_transform = observed_actor_transform(practical_actor)
                    light_spec = pair["light"]
                    observed_intensity = normalized_number(
                        practical_component.get_editor_property("intensity")
                    )
                    observed_temperature = normalized_number(
                        practical_component.get_editor_property("temperature")
                    )
                    observed_attenuation = normalized_number(
                        practical_component.get_editor_property("attenuation_radius")
                    )
                    observed_light_unit = practical_component.get_editor_property(
                        "intensity_units"
                    )
                    require(
                        fixture_component is not None
                        and practical_component is not None
                        and str(fixture_actor.get_class().get_path_name())
                        == "/Script/Engine.StaticMeshActor"
                        and str(practical_actor.get_class().get_path_name())
                        == expected_light_classes[light_spec["type"]]
                        and fixture_transform
                        == normalized_profile_transform(pair["fixture"])
                        and practical_transform
                        == normalized_profile_transform(light_spec)
                        and isinstance(fixture_mesh, unreal.StaticMesh)
                        and str(fixture_mesh.get_path_name())
                        == pair["fixture"]["mesh_object_path"]
                        and str(fixture_component.get_collision_profile_name())
                        == "NoCollision"
                        and fixture_visible is True
                        and fixture_cast_shadow is True
                        and fixture_cast_hidden_shadow is False
                        and light_cast_shadow is True,
                        "reloaded R4 fixture/light transform or component policy differs",
                    )
                    require(
                        observed_intensity == normalized_number(light_spec["intensity"])
                        and observed_light_unit
                        == expected_light_units[light_spec["unit"]]
                        and light_use_temperature is True
                        and observed_temperature
                        == normalized_number(light_spec["temperature_k"])
                        and observed_attenuation
                        == normalized_number(light_spec["attenuation_radius_cm"]),
                        "reloaded R4 practical light photometric policy differs",
                    )
                    observed_fixture_paths.add(fixture_actor_path)
                    observed_light_paths.add(practical_actor_path)
                    pair_observations.append(
                        {
                            "pair_id": pair["pair_id"],
                            "room_id": pair["room_id"],
                            "fixture": {
                                "fixture_id": pair["fixture"]["fixture_id"],
                                "actor_path": fixture_actor_path,
                                "actor_class_path": str(
                                    fixture_actor.get_class().get_path_name()
                                ),
                                "world_transform_cm": fixture_transform,
                                "mesh_object_path": str(fixture_mesh.get_path_name()),
                                "collision_profile": str(
                                    fixture_component.get_collision_profile_name()
                                ),
                                "visible": fixture_visible,
                                "cast_shadow": fixture_cast_shadow,
                                "cast_hidden_shadow": fixture_cast_hidden_shadow,
                            },
                            "light": {
                                "light_id": light_spec["light_id"],
                                "actor_path": practical_actor_path,
                                "actor_class_path": str(
                                    practical_actor.get_class().get_path_name()
                                ),
                                "type": light_spec["type"],
                                "world_transform_cm": practical_transform,
                                "intensity": observed_intensity,
                                "unit": light_spec["unit"],
                                "use_temperature": light_use_temperature,
                                "temperature_k": observed_temperature,
                                "attenuation_radius_cm": observed_attenuation,
                                "cast_shadow": light_cast_shadow,
                            },
                        }
                    )
                require(
                    observed_fixture_paths
                    == {str(actor.get_path_name()) for actor in fixture_inventory}
                    and observed_light_paths
                    == {
                        str(actor.get_path_name())
                        for actor in practical_light_inventory
                    },
                    "reloaded R4 fixture/light inventory contains unbound actors",
                )
                r4_fixture_light_pairs_verified = True
                r4_restrained_post_process_verified = True
                r4_renderer_contract_preserved = True
                r4_observation = {
                    "schema_version": REALISM_R4_OBSERVATION_SCHEMA,
                    "profile_id": r4_profile["profile_id"],
                    "profile_content_digest": r4_profile["content_digest"],
                    "renderer_contract": r4_profile["renderer_contract"],
                    "fixture_light_pairs": pair_observations,
                    "post_process": r4_profile["post_process"],
                    "claims": r4_profile["claims"],
                }
            camera_operations = [
                operation
                for operation in spec["operations"]
                if operation["kind"] == "place_review_camera"
            ]
            for camera_operation in camera_operations:
                semantic_tag = unreal.Name(
                    spec["stable_tag_prefix"] + camera_operation["semantic_id"]
                )
                matches = [
                    actor
                    for actor in reloaded
                    if isinstance(actor, unreal.CameraActor)
                    and semantic_tag in actor.get_editor_property("tags")
                ]
                require(len(matches) == 1, "reloaded r2 review camera set is not exact")
                actual_rotation = matches[0].get_actor_rotation()
                expected_rotation = camera_operation["transform"]["rotation_deg"]
                require(
                    abs(float(actual_rotation.roll)) <= 0.01
                    and abs(
                        (float(actual_rotation.pitch) - expected_rotation[1] + 180.0)
                        % 360.0
                        - 180.0
                    )
                    <= 0.05
                    and abs(
                        (float(actual_rotation.yaw) - expected_rotation[2] + 180.0)
                        % 360.0
                        - 180.0
                    )
                    <= 0.05,
                    "reloaded r2 review camera lost zero-roll look-at rotation",
                )
                component = matches[0].get_editor_property("camera_component")
                camera_settings = component.get_editor_property("post_process_settings")
                require(
                    math.isclose(
                        float(component.get_editor_property("field_of_view")),
                        camera_operation["fov_deg"],
                        abs_tol=0.05,
                    )
                    and bool(
                        camera_settings.get_editor_property(
                            "auto_exposure_apply_physical_camera_exposure"
                        )
                    ),
                    "reloaded r2 review camera lost FOV or pinned physical exposure",
                )
        else:
            require(
                bool(post_settings.get_editor_property("override_auto_exposure_method"))
                and bool(
                    post_settings.get_editor_property(
                        "override_auto_exposure_apply_physical_camera_exposure"
                    )
                )
                and bool(
                    post_settings.get_editor_property("override_auto_exposure_bias")
                )
                and post_settings.get_editor_property("auto_exposure_method")
                == unreal.AutoExposureMethod.AEM_MANUAL
                and not bool(
                    post_settings.get_editor_property(
                        "auto_exposure_apply_physical_camera_exposure"
                    )
                )
                and float(post_settings.get_editor_property("auto_exposure_bias"))
                == -6.0,
                "reloaded map lost deterministic manual exposure",
            )
        verify_legacy_input_mappings()
        dynamic_lighting_verified = True
        deterministic_exposure_verified = True
        input_mappings_verified = True
        reload_verified = True
        status = "saved_reloaded_candidate"
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc)[:512],
            "stage": stage,
        }
        if status == "saved_candidate":
            status = "partial_saved_quarantined"
        else:
            status = "failed_unsaved_quarantined"

    actors = [actor_record(actor) for actor in actor_subsystem.get_all_level_actors()]
    gates = {
        "map_saved": status == "saved_reloaded_candidate",
        "map_reloaded": reload_verified,
        "semantic_tags_verified": reload_verified,
        "player_start_verified": reload_verified,
        "game_mode_configured": reload_verified,
        "navmesh_bounds_verified": reload_verified,
        "dynamic_lighting_verified": dynamic_lighting_verified,
        "deterministic_exposure_verified": deterministic_exposure_verified,
        "input_mappings_verified": input_mappings_verified,
        "quarantined": status != "saved_reloaded_candidate",
        "runtime_play_proof": "pending",
    }
    if is_r4:
        gates.update(
            {
                "realism_r4_fixture_light_pairs_verified": (
                    r4_fixture_light_pairs_verified
                ),
                "realism_r4_restrained_post_process_verified": (
                    r4_restrained_post_process_verified
                ),
                "realism_r4_renderer_contract_preserved": (
                    r4_renderer_contract_preserved
                ),
                "human_visual_acceptance": "pending",
                "gta_quality_accepted": False,
            }
        )
    receipt = {
        "schema_version": (
            REALISM_R4_SCENE_RECEIPT_SCHEMA if is_r4 else SCENE_RECEIPT_SCHEMA
        ),
        "status": status,
        "error": error,
        "bindings": {
            "engine": engine,
            "project": project,
            "execution_manifest": manifest_path,
            "execution_manifest_sha256": manifest_sha,
            "import_receipt": import_path,
            "import_receipt_sha256": import_sha,
            "composition_spec_sha256": execution["composition_spec_sha256"],
            "input_config": input_config,
            "input_config_sha256": input_config_sha,
        },
        "content_namespace": spec["content_namespace"],
        "map_path": map_path,
        "actor_inventory": sorted(actors, key=lambda item: item["path"]),
        "gates": gates,
    }
    if is_r4:
        receipt["realism_r4_observation"] = r4_observation
    receipt_sha = write_exclusive_receipt(
        execution["scene_receipt"], execution["attempt_root"], receipt
    )
    result = {
        "status": status,
        "receipt": execution["scene_receipt"],
        "sha256": receipt_sha,
    }
    write_exclusive_receipt(
        os.path.join(execution["attempt_root"], SCENE_RESULT_FILE),
        execution["attempt_root"],
        result,
    )
    marker = SCENE_MARKER + json.dumps(result, sort_keys=True)
    # Commandlets reliably retain engine log messages even when embedded
    # Python stdout is discarded during shutdown.
    unreal.log(marker)
    print(marker, flush=True)
    if status != "saved_reloaded_candidate":
        raise RuntimeError(
            "VISTA Playable Home composition failed; fresh revision quarantined"
        )


run()
