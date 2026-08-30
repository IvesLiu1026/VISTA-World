from __future__ import annotations

import copy
import hashlib
import json
import pathlib
from types import SimpleNamespace
from typing import Any

import pytest

from tools.ue.vista_playable_home import (
    compose_hssd_r10_pbr_surface_retrofit_commandlet as commandlet,
)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    REPO_ROOT / "world_packs/vista_playable_home_r1/visual_profiles/"
    "hssd_r10_pbr_surface_retrofit_r1.json"
)
SUPPORT_PATH = (
    REPO_ROOT
    / "tools/ue/vista_playable_home/compose_hssd_r2_citysample_live_commandlet.py"
)
SOURCE_H_PROFILE_PATH = (
    REPO_ROOT / "world_packs/vista_playable_home_r1/visual_profiles/"
    "hssd_r2_citysample_live_r1.json"
)


def _profile() -> dict[str, Any]:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _identity(path: str, *, tags: list[str] | None = None) -> dict[str, Any]:
    return {
        "actor_path": path,
        "actor_class_path": "/Script/Engine.StaticMeshActor",
        "tags": sorted(tags or []),
    }


def _target_observation(
    invariant: dict[str, Any], bindings: list[dict[str, Any]]
) -> dict[str, Any]:
    by_slot = {row["slot_index"]: row for row in bindings}
    return {
        "actor_path": invariant["actor_path"],
        "actor_class_path": invariant["actor_class_path"],
        "tags": copy.deepcopy(invariant["tags"]),
        "actor_label": invariant["actor_label"],
        "actor_transform": copy.deepcopy(invariant["actor_transform"]),
        "actor_hidden_in_game": invariant["actor_hidden_in_game"],
        "actor_collision_enabled": invariant["actor_collision_enabled"],
        "static_mesh_components": [
            {
                "component_path": invariant["component_path"],
                "component_name": invariant["component_name"],
                "mesh_object_path": invariant["mesh_object_path"],
                "relative_transform": copy.deepcopy(invariant["relative_transform"]),
                "visible": invariant["visible"],
                "collision_mode": invariant["collision_mode"],
                "collision_profile_name": invariant["collision_profile_name"],
                "collision_responses": copy.deepcopy(invariant["collision_responses"]),
                "mobility": invariant["mobility"],
                "attach_parent_component_path": invariant[
                    "attach_parent_component_path"
                ],
                "simulate_physics": invariant["simulate_physics"],
                "generate_overlap_events": invariant["generate_overlap_events"],
                "can_ever_affect_navigation": invariant["can_ever_affect_navigation"],
                "cast_shadow": invariant["cast_shadow"],
                "cast_hidden_shadow": invariant["cast_hidden_shadow"],
                "materials": [
                    by_slot[index]["before"]["object_path"] for index in range(3)
                ],
            }
        ],
        "light_components": [],
    }


def _minimal_observation(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        **copy.deepcopy(identity),
        "static_mesh_components": [],
    }


def _synthetic_source(profile: dict[str, Any]) -> tuple[dict[str, Any], list[dict]]:
    target_identities = [
        _identity(row["actor_path"], tags=row["tags"])
        for row in profile["actor_invariants"]
    ]
    preserved = copy.deepcopy(target_identities)
    for index in range(5):
        preserved.append(
            _identity(
                f"{commandlet.WORLD_OBJECT_PATH}:PersistentLevel.Portal_{index}",
                tags=["VistaRole=portal", f"VistaSemanticId=portal.{index}"],
            )
        )
    while len(preserved) < 108:
        index = len(preserved)
        preserved.append(
            _identity(
                f"{commandlet.WORLD_OBJECT_PATH}:PersistentLevel.Preserved_{index:03d}"
            )
        )
    static = [
        _identity(f"{commandlet.WORLD_OBJECT_PATH}:PersistentLevel.Hssd_{index:03d}")
        for index in range(57)
    ]
    secondary = [
        _identity(
            f"{commandlet.WORLD_OBJECT_PATH}:PersistentLevel.Secondary_{index:03d}"
        )
        for index in range(20)
    ]
    segments = [
        _identity(f"{commandlet.WORLD_OBJECT_PATH}:PersistentLevel.Finish_{index:03d}")
        for index in range(26)
    ]
    observations_by_path = {
        row["actor_path"]: _minimal_observation(row)
        for row in [*preserved, *static, *secondary, *segments]
    }
    binding_by_actor: dict[str, list[dict[str, Any]]] = {}
    for binding in profile["bindings"]:
        binding_by_actor.setdefault(binding["actor_path"], []).append(binding)
    for invariant in profile["actor_invariants"]:
        observations_by_path[invariant["actor_path"]] = _target_observation(
            invariant, binding_by_actor[invariant["actor_path"]]
        )
    all_before = sorted(
        observations_by_path.values(), key=lambda row: row["actor_path"]
    )

    finish_architecture = [
        copy.deepcopy(observations_by_path[row["actor_path"]])
        for row in profile["actor_invariants"]
    ]
    finish_architecture.extend(
        _minimal_observation(
            _identity(
                f"{commandlet.WORLD_OBJECT_PATH}:PersistentLevel.ArchitectureExtra_{i}"
            )
        )
        for i in range(3)
    )
    finish_architecture.sort(key=lambda row: row["actor_path"])
    world = {
        "world_path": commandlet.WORLD_OBJECT_PATH,
        "world_settings_path": commandlet.WORLD_SETTINGS_OBJECT_PATH,
        "default_game_mode": commandlet.DEFAULT_GAME_MODE_OBJECT_PATH,
        "force_no_precomputed_lighting": True,
    }
    scene = {
        "observations": {
            "preserved_non_hssd": {"reloaded_inventory": preserved},
            "shell_migration": {"static_reloaded": [{"actor": row} for row in static]},
            "collision": {
                "secondary_reloaded": [{"actor": row} for row in secondary],
                "semantic_static_reloaded": [{"semantic": "sealed"}],
                "detail_reloaded": [{"detail": "sealed"}],
            },
            "six_room_finish": {
                "architecture_reloaded": finish_architecture,
                "fixtures_reloaded": [{"fixture": "sealed"}],
                "r4_lights_reloaded": [{"light": "sealed"}],
                "segments_reloaded": [
                    {
                        **row,
                        "static_mesh_components": [],
                        "segment_id": f"segment.{index}",
                    }
                    for index, row in enumerate(segments)
                ],
            },
            "dynamic_presentations": {"reloaded": [{"dynamic": "sealed"}]},
            "world_reloaded": world,
        }
    }
    return scene, all_before


def _artifact(path: str, digit: str = "a", size: int = 1) -> dict[str, Any]:
    return {"path": path, "sha256": digit * 64, "size_bytes": size}


def _valid_result_bundle() -> tuple[dict, dict, dict, dict, dict]:
    profile = _profile()
    source_scene, all_before = _synthetic_source(profile)
    attempt = pathlib.PurePath("/tmp/r10-commandlet-contract")
    project = attempt / "project" / commandlet.PROJECT_NAME
    source_h = {
        key: _artifact(str(attempt / value["name"]), str(index + 1)[-1])
        for index, (key, value) in enumerate(commandlet.SOURCE_H_PINS.items())
    }
    execution: dict[str, Any] = {
        "schema_version": commandlet.EXECUTION_SCHEMA,
        "status": "authorized_apply_request",
        "attempt_root": str(attempt),
        "project": _artifact(str(project)),
        "materializer": _artifact(str(attempt / commandlet.MATERIALIZER_NAME)),
        "commandlet": _artifact(str(attempt / commandlet.COMMANDLET_NAME)),
        "source_h_commandlet_support": _artifact(
            str(attempt / commandlet.SUPPORT_NAME)
        ),
        "profile": _artifact(str(attempt / commandlet.PROFILE_NAME)),
        "source_h_authority": source_h,
        "source_project_static_tree": copy.deepcopy(commandlet.SOURCE_PROJECT_TREE),
        "source_static_manifest": {"placeholder": {}},
        "mutation_contract": commandlet._mutation_contract(profile),
        "engine": {},
        "map": {
            "object_path": commandlet.MAP_OBJECT_PATH,
            "relative_path": commandlet.MAP_RELATIVE_PATH,
            "source_package": {
                "path": str(project.parent / commandlet.MAP_RELATIVE_PATH),
                "sha256": commandlet.SOURCE_MAP_SHA256,
                "size_bytes": commandlet.SOURCE_MAP_BYTES,
            },
        },
        "result": {
            "result_path": str(attempt / commandlet.RESULT_NAME),
            "result_sidecar_path": str(attempt / (commandlet.RESULT_NAME + ".sha256")),
            "scene_receipt_path": str(attempt / commandlet.SCENE_RECEIPT_NAME),
            "scene_receipt_sidecar_path": str(
                attempt / (commandlet.SCENE_RECEIPT_NAME + ".sha256")
            ),
        },
        "legal_scope": copy.deepcopy(commandlet.LEGAL_SCOPE),
        "acknowledgements": copy.deepcopy(commandlet.ACKNOWLEDGEMENTS),
        "claims": copy.deepcopy(commandlet.EXECUTION_CLAIMS),
        "acceptance": copy.deepcopy(commandlet.ACCEPTANCE),
    }
    execution = commandlet.seal(execution)
    all_after = commandlet.expected_actor_observations(all_before, profile["bindings"])
    protected_before = commandlet.source_protected_projection(source_scene)
    protected_after = commandlet.expected_protected_projection(
        protected_before, profile["bindings"]
    )
    output_map = {
        "path": str(project.parent / commandlet.MAP_RELATIVE_PATH),
        "sha256": "f" * 64,
        "size_bytes": commandlet.SOURCE_MAP_BYTES + 1,
    }
    packages = [
        {
            "project_relative_path": row["project_relative_path"],
            "source_pin": {
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
                "mode": int(row["mode"], 8),
            },
            "output_pin": {
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
                "mode": int(row["mode"], 8),
            },
        }
        for row in profile["replacement_packages"]
    ]
    descriptor = {
        "project_relative_path": commandlet.PROJECT_NAME,
        "source_pin": {
            "sha256": commandlet.PROJECT_DESCRIPTOR_SHA256,
            "size_bytes": commandlet.PROJECT_DESCRIPTOR_BYTES,
            "mode": 0o600,
        },
        "output_pin": {
            "sha256": commandlet.PROJECT_DESCRIPTOR_SHA256,
            "size_bytes": commandlet.PROJECT_DESCRIPTOR_BYTES,
            "mode": 0o600,
        },
    }
    result = commandlet.seal(
        {
            "schema_version": commandlet.RESULT_SCHEMA,
            "status": commandlet.RESULT_STATUS,
            "provider_id": commandlet.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution_sha256": hashlib.sha256(
                commandlet.canonical_json(execution)
            ).hexdigest(),
            "source_h_authority": source_h,
            "map_object_path": commandlet.MAP_OBJECT_PATH,
            "map_package": output_map,
            "source_project_static_tree": copy.deepcopy(commandlet.SOURCE_PROJECT_TREE),
            "project_static_tree": {
                **commandlet.SOURCE_PROJECT_TREE,
                "total_bytes": commandlet.SOURCE_PROJECT_TREE["total_bytes"] + 1,
                "tree_sha256": "e" * 64,
            },
            "bindings": copy.deepcopy(profile["bindings"]),
            "observations": {
                "source_actor_inventory": commandlet.reconstruct_source_h_actor_inventory(
                    source_scene
                ),
                "all_actors_before": all_before,
                "all_actors_after_save": all_after,
                "all_actors_reloaded": copy.deepcopy(all_after),
                "world_before": protected_before["world"],
                "world_after_save": protected_before["world"],
                "world_reloaded": protected_before["world"],
                "protected_before": protected_before,
                "protected_after_save": protected_after,
                "protected_reloaded": copy.deepcopy(protected_after),
                "binding_observations": {
                    "before": commandlet._expected_binding_observations(
                        profile["bindings"], "before"
                    ),
                    "after_save": commandlet._expected_binding_observations(
                        profile["bindings"], "after"
                    ),
                    "reloaded": commandlet._expected_binding_observations(
                        profile["bindings"], "after"
                    ),
                },
                "static_delta": {
                    "policy": "exact_map_only/v1",
                    "changed_relative_paths": [commandlet.MAP_RELATIVE_PATH],
                    "source_map_package": execution["map"]["source_package"],
                    "output_map_package": output_map,
                },
                "replacement_package_projection": packages,
                "project_descriptor_projection": descriptor,
            },
            "legal_scope": copy.deepcopy(commandlet.LEGAL_SCOPE),
            "claims": copy.deepcopy(commandlet.RESULT_CLAIMS),
            "acceptance": copy.deepcopy(commandlet.ACCEPTANCE),
            "gates": {key: True for key in commandlet.RESULT_GATE_KEYS},
            "error": None,
        }
    )
    result_raw = commandlet.canonical_json(result)
    scene = commandlet.seal(
        {
            "schema_version": commandlet.SCENE_RECEIPT_SCHEMA,
            "status": commandlet.RESULT_STATUS,
            "provider_id": commandlet.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": {
                "path": str(attempt / commandlet.EXECUTION_NAME),
                "sha256": hashlib.sha256(
                    commandlet.canonical_json(execution)
                ).hexdigest(),
                "size_bytes": len(commandlet.canonical_json(execution)),
            },
            "result": {
                "path": str(attempt / commandlet.RESULT_NAME),
                "sha256": hashlib.sha256(result_raw).hexdigest(),
                "size_bytes": len(result_raw),
            },
            "source_h_authority": source_h,
            "map_object_path": commandlet.MAP_OBJECT_PATH,
            "map_package": copy.deepcopy(output_map),
            "source_project_static_tree": copy.deepcopy(commandlet.SOURCE_PROJECT_TREE),
            "project_static_tree": copy.deepcopy(result["project_static_tree"]),
            "bindings": copy.deepcopy(result["bindings"]),
            "observations": copy.deepcopy(result["observations"]),
            "legal_scope": copy.deepcopy(commandlet.LEGAL_SCOPE),
            "claims": copy.deepcopy(commandlet.RESULT_CLAIMS),
            "acceptance": copy.deepcopy(commandlet.ACCEPTANCE),
        }
    )
    return execution, result, scene, profile, {"scene_receipt": source_scene}


def test_committed_profile_and_support_pins_match_commandlet() -> None:
    profile_raw = PROFILE_PATH.read_bytes()
    support_raw = SUPPORT_PATH.read_bytes()
    profile = json.loads(profile_raw)

    assert hashlib.sha256(profile_raw).hexdigest() == commandlet.PROFILE_SHA256
    assert len(profile_raw) == commandlet.PROFILE_BYTES
    assert profile["content_digest"] == commandlet.PROFILE_CONTENT_DIGEST
    assert (
        commandlet.profile_content_digest(profile) == commandlet.PROFILE_CONTENT_DIGEST
    )
    assert commandlet._validate_profile(profile) == profile
    assert hashlib.sha256(support_raw).hexdigest() == commandlet.SUPPORT_SHA256
    assert len(support_raw) == commandlet.SUPPORT_BYTES


def test_pretty_profile_authorities_are_pinned_without_json_reencoding() -> None:
    raw = SOURCE_H_PROFILE_PATH.read_bytes()
    profile = commandlet.strict_json(raw, "source h finish profile")
    support = commandlet._load_support(SUPPORT_PATH)

    assert raw != commandlet.canonical_json(profile)
    assert (
        hashlib.sha256(raw).hexdigest()
        == commandlet.SOURCE_H_PINS["finish_profile"]["sha256"]
    )
    assert len(raw) == commandlet.SOURCE_H_PINS["finish_profile"]["size_bytes"]
    assert support.validate_profile(profile) == profile


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["claims"].__setitem__("gta_level_quality", True),
        lambda value: value["bindings"][0].__setitem__("slot_index", 2),
        lambda value: value["bindings"][0]["before"].__setitem__(
            "object_path", "/Game/Drift.Drift"
        ),
        lambda value: value["actor_invariants"][0].__setitem__(
            "collision_profile_name", "NoCollision"
        ),
        lambda value: value["replacement_packages"][0].__setitem__(
            "class_path", "/Script/Engine.Material"
        ),
        lambda value: value["mutation_policy"].__setitem__("actor_spawn_allowed", True),
    ],
)
def test_profile_validation_fails_closed_on_contract_drift(mutation: Any) -> None:
    profile = _profile()
    mutation(profile)
    profile["content_digest"] = commandlet.profile_content_digest(profile)

    with pytest.raises(commandlet.CommandletFailure):
        commandlet._validate_profile(profile)


def test_independent_literal_rejects_coherent_reseal_material_swap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile()
    bathroom_floor = profile["bindings"][0]
    bedroom_floor = profile["bindings"][3]
    bathroom_floor["after"], bedroom_floor["after"] = (
        copy.deepcopy(bedroom_floor["after"]),
        copy.deepcopy(bathroom_floor["after"]),
    )
    resealed = commandlet.profile_content_digest(profile)
    profile["content_digest"] = resealed
    # Model a compromised/coherently updated profile pin.  The independent
    # literal must still reject the semantically wrong room/material mapping.
    monkeypatch.setattr(commandlet, "PROFILE_CONTENT_DIGEST", resealed)

    with pytest.raises(
        commandlet.CommandletFailure,
        match="independent nine-row literal",
    ):
        commandlet._validate_profile(profile)


def test_expected_actor_observations_changes_exactly_nine_material_cells() -> None:
    profile = _profile()
    binding_by_actor: dict[str, list[dict[str, Any]]] = {}
    for binding in profile["bindings"]:
        binding_by_actor.setdefault(binding["actor_path"], []).append(binding)
    before = [
        _target_observation(row, binding_by_actor[row["actor_path"]])
        for row in profile["actor_invariants"]
    ]

    after = commandlet.expected_actor_observations(before, profile["bindings"])

    assert commandlet._binding_observations(
        before, profile["bindings"]
    ) == commandlet._expected_binding_observations(profile["bindings"], "before")
    assert commandlet._binding_observations(
        after, profile["bindings"]
    ) == commandlet._expected_binding_observations(profile["bindings"], "after")
    changed = []
    before_by_path = {row["actor_path"]: row for row in before}
    after_by_path = {row["actor_path"]: row for row in after}
    for binding in profile["bindings"]:
        actor_path = binding["actor_path"]
        slot = binding["slot_index"]
        left = before_by_path[actor_path]["static_mesh_components"][0]["materials"][
            slot
        ]
        right = after_by_path[actor_path]["static_mesh_components"][0]["materials"][
            slot
        ]
        changed.append((actor_path, slot, left, right))
    assert len(changed) == 9
    assert all(left != right for _, _, left, right in changed)


@pytest.mark.parametrize("drift", ["actor", "component", "slot", "before", "duplicate"])
def test_expected_actor_observations_rejects_selector_drift(drift: str) -> None:
    profile = _profile()
    binding_by_actor: dict[str, list[dict[str, Any]]] = {}
    for binding in profile["bindings"]:
        binding_by_actor.setdefault(binding["actor_path"], []).append(binding)
    before = [
        _target_observation(row, binding_by_actor[row["actor_path"]])
        for row in profile["actor_invariants"]
    ]
    bindings = copy.deepcopy(profile["bindings"])
    if drift == "actor":
        bindings[0]["actor_path"] += "_drift"
    elif drift == "component":
        bindings[0]["component_path"] += "_drift"
    elif drift == "slot":
        bindings[0]["slot_index"] = 99
    elif drift == "before":
        bindings[0]["before"]["object_path"] += "_drift"
    else:
        bindings[1] = copy.deepcopy(bindings[0])

    with pytest.raises(commandlet.CommandletFailure):
        commandlet.expected_actor_observations(before, bindings)


def test_only_map_changed_is_exact_not_subset_based() -> None:
    source = {
        commandlet.PROJECT_NAME: {"sha256": "a" * 64, "size_bytes": 1, "mode": 0o600},
        commandlet.MAP_RELATIVE_PATH: {
            "sha256": commandlet.SOURCE_MAP_SHA256,
            "size_bytes": commandlet.SOURCE_MAP_BYTES,
            "mode": 0o600,
        },
        "Content/Fixed.uasset": {"sha256": "b" * 64, "size_bytes": 2, "mode": 0o600},
    }
    output = copy.deepcopy(source)
    output[commandlet.MAP_RELATIVE_PATH]["sha256"] = "c" * 64

    assert commandlet.only_map_changed(source, output) == (
        True,
        [commandlet.MAP_RELATIVE_PATH],
    )
    output["Content/Fixed.uasset"]["size_bytes"] = 3
    assert commandlet.only_map_changed(source, output) == (
        False,
        sorted([commandlet.MAP_RELATIVE_PATH, "Content/Fixed.uasset"]),
    )


def test_source_h_inventory_reconstruction_is_exact_and_portal_closed() -> None:
    profile = _profile()
    source_scene, _before = _synthetic_source(profile)

    rows = commandlet.reconstruct_source_h_actor_inventory(source_scene)

    assert len(rows) == 211
    assert len({row["actor_path"] for row in rows}) == 211
    assert len([row for row in rows if "VistaRole=portal" in row["tags"]]) == 5
    source_scene["observations"]["preserved_non_hssd"]["reloaded_inventory"][3][
        "tags"
    ] = []
    with pytest.raises(commandlet.CommandletFailure):
        commandlet.reconstruct_source_h_actor_inventory(source_scene)


def test_result_scene_validator_closes_full_actor_and_negative_claims() -> None:
    execution, result, scene, profile, source_documents = _valid_result_bundle()

    commandlet.validate_result_document(
        execution, result, scene, profile, source_documents
    )

    drifted = copy.deepcopy(result)
    drifted["claims"]["gta_level_quality"] = True
    drifted["content_digest"] = commandlet.content_digest(drifted)
    with pytest.raises(commandlet.CommandletFailure):
        commandlet.validate_result_document(
            execution, drifted, scene, profile, source_documents
        )


def test_result_scene_validator_rejects_hidden_non_material_actor_drift() -> None:
    execution, result, scene, profile, source_documents = _valid_result_bundle()
    drifted = copy.deepcopy(result)
    drifted["observations"]["all_actors_reloaded"][0]["hidden_drift"] = True
    drifted["content_digest"] = commandlet.content_digest(drifted)

    with pytest.raises(commandlet.CommandletFailure):
        commandlet.validate_result_document(
            execution, drifted, scene, profile, source_documents
        )


def test_publication_is_exclusive_and_emits_one_marker(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / commandlet.RESULT_NAME
    sidecar_path = tmp_path / (commandlet.RESULT_NAME + ".sha256")
    messages: list[str] = []
    monkeypatch.setattr(commandlet, "unreal", SimpleNamespace(log=messages.append))
    value = commandlet.seal({"fixture": True})

    published = commandlet.publish_document(
        result_path, sidecar_path, value, commandlet.RESULT_MARKER
    )

    assert len(messages) == 1
    assert messages[0].startswith(commandlet.RESULT_MARKER)
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == published["sha256"]
    assert sidecar_path.read_text(encoding="ascii") == (
        f"{published['sha256']}  {commandlet.RESULT_NAME}\n"
    )
    with pytest.raises(FileExistsError):
        commandlet.publish_document(
            result_path, sidecar_path, value, commandlet.RESULT_MARKER
        )


def test_source_exposes_only_the_narrow_nullrhi_material_mutation_surface() -> None:
    source = pathlib.Path(commandlet.__file__).read_text(encoding="utf-8")

    assert source.count('if __name__ == "__main__":') == 1
    assert source.count("component.set_material(") == 1
    assert source.count("level_subsystem.load_level(MAP_OBJECT_PATH)") == 2
    assert source.count("EditorLoadingAndSavingUtils.save_map") == 1
    assert commandlet.RESULT_MARKER in source
    assert commandlet.SCENE_MARKER in source
    assert commandlet.SUPPORT_SHA256 in source
    for prohibited in (
        "spawn_actor_from_class",
        "destroy_actor",
        ".set_actor_location(",
        ".set_actor_rotation(",
        ".set_actor_scale3d(",
        ".set_collision_",
        '.set_editor_property("tags"',
        "AssetImportTask",
        "capture_screenshot",
        "MoviePipeline",
        "requests.",
        "urllib",
        "socket.",
        "openai",
        "anthropic",
    ):
        assert prohibited not in source
