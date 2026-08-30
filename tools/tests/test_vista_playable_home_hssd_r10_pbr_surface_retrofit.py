from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from tools.ue.vista_playable_home import (
    compose_hssd_r10_pbr_surface_retrofit_commandlet as commandlet,
)
from tools.ue.vista_playable_home import (
    materialize_hssd_r10_pbr_surface_retrofit as materializer,
)


ATTEMPT = "hssd-r10-pbr-surface-retrofit-r1-unit"
REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    REPO_ROOT / "world_packs/vista_playable_home_r1/visual_profiles/"
    "hssd_r10_pbr_surface_retrofit_r1.json"
)
R2_PROFILE_PATH = (
    REPO_ROOT / "world_packs/vista_playable_home_r1/visual_profiles/"
    "hssd_r2_citysample_live_r1.json"
)


TOP_LEVEL_KEYS = {
    "schema_version",
    "profile_id",
    "source_parent",
    "presentation_provenance",
    "replacement_packages",
    "actor_invariants",
    "bindings",
    "mutation_policy",
    "claims",
    "content_digest",
}
SOURCE_PARENT_KEYS = {
    "run_parent",
    "attempt_name",
    "attempt_root",
    "complete_receipt",
    "combined_receipt",
    "host_receipt",
    "scene_receipt",
    "finish_profile",
    "project_descriptor",
    "map_package",
    "project_static_tree",
    "map_object_path",
    "world_object_path",
    "world_settings_path",
    "default_game_mode",
    "provider_id",
    "legal_scope",
    "claims",
}
PROVENANCE_KEYS = {
    "source_attempt_name",
    "source_root",
    "presentation_manifest",
    "presentation_artifact_receipt",
    "presentation_import_receipt",
    "cc0_acquisition",
    "external_material_links",
}
PACKAGE_KEYS = {
    "material_id",
    "object_path",
    "class_path",
    "project_relative_path",
    "sha256",
    "size_bytes",
    "mode",
    "source_kind",
    "active_texture_semantics",
}
BINDING_KEYS = {
    "room_id",
    "surface_role",
    "actor_path",
    "component_path",
    "slot_index",
    "before",
    "after",
}
EXPECTED_PARENT_SHA256 = {
    "complete_receipt": (
        "52ec26972109b0b2ca195607f8536b845c56b2c413e50d5a207609452e46211a"
    ),
    "combined_receipt": (
        "869c8247e975cd79af9be5a7cca4dc169b2de8b7b3badf673ec3f93f425bdc48"
    ),
    "host_receipt": (
        "ec35ebc8aa6989fa3486207866779d5ff1898ecb2116bf7a4a0f9bf652a73848"
    ),
    "scene_receipt": (
        "67cbea713749283bec2cbcb15cd4d47d79b9d7a857602cfc313d3db33ba0ef57"
    ),
    "finish_profile": (
        "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb"
    ),
    "project_descriptor": (
        "fe11c7e48eb895eec74e48868fc458a24a2290e826f8cbe75edea0e8ba8b674a"
    ),
    "map_package": ("1fda153459fea9845cab969b9802ce418bdde51bdbf6884ccd17c77b796dd588"),
}
EXPECTED_PROVENANCE_SHA256 = {
    "presentation_manifest": (
        "b5c6b0dd2d172255cb5f7bb494657b8c1ed7f2f7a214557b08d7642590e0a71e"
    ),
    "presentation_artifact_receipt": (
        "f4c55a1ef674ad3ba3cfa980e4321255663437fc0811723768ce32ce604488c5"
    ),
    "presentation_import_receipt": (
        "7e46e1fb338b586ca0a64a1a917f07b8ca61a6c16df0b6bf662159ebd86c83b4"
    ),
}
EXPECTED_PACKAGE_PINS = [
    (
        "VISTA_M_r2_slate_honed",
        "735e5493137d44ef2d371172a6dcb65d185f0ad8bdb2ec9ae01c0033ed4d0cca",
        67_375,
    ),
    (
        "VISTA_M_r2_plaster_warm",
        "9ac8086d804df268eac42e0533d379a6fcdac8594ff6f1ad97064ada4527affc",
        67_419,
    ),
    (
        "VISTA_M_r2_ceiling_matte",
        "d5c534429d2fa928f7323329a27d606579e0a6577cb6a868ca0e26b274b0ce7d",
        67_427,
    ),
    (
        "r2_external_t_8e98f99344e39",
        "1b58b820e3e3e4d646357127c90b8b86606bb1fb4c9e6f041bbc065c94d35899",
        68_184,
    ),
    (
        "r2_external_t_72b7127467c9a",
        "e6a290bb97bbdab95863cdf45b30393d711468382394e2add864774d1dd30af5",
        68_070,
    ),
]
EXPECTED_BINDINGS = [
    (
        "home.r1/room.bathroom_laundry",
        "floor",
        "StaticMeshActor_0",
        0,
        "VISTA_M_r2_slate_honed",
    ),
    (
        "home.r1/room.bathroom_laundry",
        "wall",
        "StaticMeshActor_0",
        1,
        "VISTA_M_r2_plaster_warm",
    ),
    (
        "home.r1/room.bathroom_laundry",
        "ceiling",
        "StaticMeshActor_0",
        2,
        "VISTA_M_r2_ceiling_matte",
    ),
    (
        "home.r1/room.bedroom",
        "floor",
        "StaticMeshActor_1",
        0,
        "r2_external_t_8e98f99344e39",
    ),
    ("home.r1/room.bedroom", "wall", "StaticMeshActor_1", 1, "VISTA_M_r2_plaster_warm"),
    (
        "home.r1/room.bedroom",
        "ceiling",
        "StaticMeshActor_1",
        2,
        "VISTA_M_r2_ceiling_matte",
    ),
    (
        "home.r1/room.office",
        "floor",
        "StaticMeshActor_5",
        0,
        "r2_external_t_72b7127467c9a",
    ),
    ("home.r1/room.office", "wall", "StaticMeshActor_5", 1, "VISTA_M_r2_plaster_warm"),
    (
        "home.r1/room.office",
        "ceiling",
        "StaticMeshActor_5",
        2,
        "VISTA_M_r2_ceiling_matte",
    ),
]


@dataclasses.dataclass(frozen=True)
class Fixture:
    config: materializer.Config
    profile: dict[str, Any]
    parent_documents: dict[str, dict[str, Any]]
    provenance_documents: dict[str, dict[str, Any]]


@dataclasses.dataclass(frozen=True)
class PublicationHarness:
    prepared: Any
    execution_path: Path
    execution: dict[str, Any]
    execution_sha256: str
    result: dict[str, Any]
    scene: dict[str, Any]
    stdout_path: Path
    engine_log: Path
    closed_log_seals: dict[str, Any]
    baseline_manifest: dict[str, dict[str, Any]]


def _canonical_compact(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", "strict")


def _profile_digest(value: dict[str, Any]) -> str:
    body = copy.deepcopy(value)
    body.pop("content_digest", None)
    return hashlib.sha256(_canonical_compact(body)).hexdigest()


def _seal_profile(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["content_digest"] = _profile_digest(result)
    return result


def _seal_receipt(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result.pop("content_digest", None)
    raw = _canonical_compact(result) + b"\n"
    result["content_digest"] = hashlib.sha256(raw).hexdigest()
    return result


def _write(path: Path, raw: bytes, mode: int = 0o600) -> materializer.PinnedFile:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()
    path.write_bytes(raw)
    path.chmod(mode)
    return materializer.PinnedFile(
        path,
        materializer.FilePin(hashlib.sha256(raw).hexdigest(), len(raw), mode),
    )


def _write_receipt(
    path: Path, value: dict[str, Any]
) -> tuple[dict[str, Any], materializer.PinnedFile]:
    document = _seal_receipt(value)
    return document, _write(path, _canonical_compact(document) + b"\n")


def _write_profile(
    path: Path, value: dict[str, Any]
) -> tuple[dict[str, Any], materializer.PinnedFile]:
    profile = _seal_profile(value)
    raw = json.dumps(profile, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    return profile, _write(path, raw)


def _pin_profile_row(row: dict[str, Any], pin: materializer.PinnedFile) -> None:
    row["sha256"] = pin.pin.sha256
    row["size_bytes"] = pin.pin.size_bytes
    row["mode"] = f"{pin.pin.mode:04o}"


def _tree_state(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    rows: list[tuple[str, int, int, str]] = []
    for current, directories, files in os.walk(root):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name in files:
            path = current_path / name
            raw = path.read_bytes()
            rows.append(
                (
                    path.relative_to(root).as_posix(),
                    path.stat().st_mode & 0o7777,
                    len(raw),
                    hashlib.sha256(raw).hexdigest(),
                )
            )
    return tuple(rows)


def _actor_observation(
    actor: dict[str, Any], bindings: list[dict[str, Any]]
) -> dict[str, Any]:
    materials = [row["before"]["object_path"] for row in bindings]
    return {
        "actor_class_path": actor["actor_class_path"],
        "actor_collision_enabled": actor["actor_collision_enabled"],
        "actor_hidden_in_game": actor["actor_hidden_in_game"],
        "actor_label": actor["actor_label"],
        "actor_path": actor["actor_path"],
        "actor_transform": actor["actor_transform"],
        "light_components": [],
        "static_mesh_components": [
            {
                "attach_parent_component_path": actor["attach_parent_component_path"],
                "can_ever_affect_navigation": actor["can_ever_affect_navigation"],
                "cast_hidden_shadow": actor["cast_hidden_shadow"],
                "cast_shadow": actor["cast_shadow"],
                "collision_mode": actor["collision_mode"],
                "collision_profile_name": actor["collision_profile_name"],
                "collision_responses": actor["collision_responses"],
                "component_name": actor["component_name"],
                "component_path": actor["component_path"],
                "generate_overlap_events": actor["generate_overlap_events"],
                "materials": materials,
                "mesh_object_path": actor["mesh_object_path"],
                "mobility": actor["mobility"],
                "relative_transform": actor["relative_transform"],
                "simulate_physics": actor["simulate_physics"],
                "visible": actor["visible"],
            }
        ],
        "tags": actor["tags"],
    }


def _fixture(tmp_path: Path) -> Fixture:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    run_parent = tmp_path / "runs"
    run_parent.mkdir(parents=True)
    h_root = run_parent / "hssd-r2-citysample-live-r5-unit"
    project_root = h_root / "project"
    project_pin = _write(
        project_root / "VistaPlayableHome.uproject", b'{"FileVersion":3}\n'
    )
    map_pin = _write(
        project_root / profile["source_parent"]["map_package"]["project_relative_path"],
        b"sealed-map",
    )

    for package in profile["replacement_packages"]:
        pin = _write(
            project_root / package["project_relative_path"],
            ("sealed:" + package["material_id"]).encode("utf-8"),
        )
        _pin_profile_row(package, pin)
        for binding in profile["bindings"]:
            if binding["after"]["material_id"] == package["material_id"]:
                binding["after"]["package_sha256"] = pin.pin.sha256
                binding["after"]["package_size_bytes"] = pin.pin.size_bytes

    r2_profile_raw = R2_PROFILE_PATH.read_bytes()
    finish_pin = _write(
        h_root / "hssd-r2-citysample-live-finish-profile.json", r2_profile_raw
    )
    r2_profile = json.loads(r2_profile_raw)

    tree = materializer.TreeProjection("a" * 64, 8, 10, 2048)
    tree_mapping = {
        "algorithm": "sha256-path-nul-mode-size-content-v1",
        "file_count": tree.file_count,
        "total_bytes": tree.total_bytes,
        "tree_sha256": tree.sha256,
    }
    map_file = {
        "path": str(map_pin.path),
        "sha256": map_pin.pin.sha256,
        "size_bytes": map_pin.pin.size_bytes,
    }
    map_mapping = {
        "object_path": profile["source_parent"]["map_object_path"],
        "package": map_file,
    }
    project_mapping = {
        "path": str(project_pin.path),
        "sha256": project_pin.pin.sha256,
        "size_bytes": project_pin.pin.size_bytes,
    }
    parent_claims = profile["source_parent"]["claims"]
    legal_scope = profile["source_parent"]["legal_scope"]

    architecture = []
    for actor in profile["actor_invariants"]:
        rows = [
            row
            for row in profile["bindings"]
            if row["actor_path"] == actor["actor_path"]
        ]
        architecture.append(_actor_observation(actor, rows))
    scene, scene_pin = _write_receipt(
        h_root / "hssd-r2-citysample-live-scene-receipt.json",
        {
            "schema_version": "simworld.vista.hssd-r2-citysample-live-scene-receipt/v1",
            "status": "hssd_r2_citysample_live_saved_cold_reloaded",
            "acceptance": {"runtime_play_proof": "pending"},
            "claims": parent_claims,
            "execution": {"sha256": "1" * 64},
            "human_operated_visual_demo_only": True,
            "legal_scope": legal_scope,
            "map_object_path": profile["source_parent"]["map_object_path"],
            "map_package": map_file,
            "observations": {
                "six_room_finish": {
                    "architecture_reloaded": architecture,
                    "fixtures_reloaded": [{"fixture": index} for index in range(6)],
                },
                "collision": {
                    "semantic_static_reloaded": [
                        {"proxy": index} for index in range(16)
                    ],
                    "semantic_dynamic_instance_ids": [
                        "dynamic.semantic." + str(index) for index in range(3)
                    ],
                    "secondary_reloaded": [{"proxy": index} for index in range(20)],
                    "detail_reloaded": [{"proxy": index} for index in range(21)],
                    "policy_counts": {
                        "detail_no_collision": 21,
                        "secondary_query_proxies": 20,
                        "semantic_proxies": 19,
                    },
                },
                "world_reloaded": {
                    "default_game_mode": profile["source_parent"]["default_game_mode"],
                    "force_no_precomputed_lighting": True,
                    "world_path": profile["source_parent"]["world_object_path"],
                    "world_settings_path": profile["source_parent"][
                        "world_settings_path"
                    ],
                },
            },
            "prohibited_agent_adapter": True,
            "project_static_tree": tree_mapping,
            "provider_id": profile["source_parent"]["provider_id"],
            "result": {"sha256": "2" * 64},
        },
    )
    combined, combined_pin = _write_receipt(
        h_root / "human-visual-demo-combined-receipt.json",
        {
            "schema_version": "simworld.vista.human-visual-demo-combined-receipt/v5",
            "status": "sealed_human_visual_demo_candidate",
            "claims": parent_claims,
            "executable": {"path": "private-demo"},
            "hssd_r2_citysample_live_r1_upgrade": {"status": "sealed"},
            "human_operated_visual_demo_only": True,
            "legal_scope": legal_scope,
            "map": map_mapping,
            "prohibited_agent_adapter": True,
            "project": project_mapping,
            "project_static_tree": tree_mapping,
            "provider_id": profile["source_parent"]["provider_id"],
            "source_provenance": {"fixture": "unit"},
        },
    )
    host, host_pin = _write_receipt(
        h_root / "hssd-r2-citysample-live-host-receipt.json",
        {
            "schema_version": "simworld.vista.hssd-r2-citysample-live-host-receipt/v1",
            "status": "hssd_r2_citysample_live_saved_cold_reloaded",
            "acceptance": {"runtime_play_proof": "pending"},
            "claims": parent_claims,
            "containment": {"network": "private"},
            "current_byte_revalidation": {
                "passed": True,
                "project_static_tree": tree_mapping,
                "map": map_file,
            },
            "execution": {"sha256": "3" * 64},
            "fixture_evidence_manifest": {"content_digest": "4" * 64},
            "gates": {"nullrhi_no_gpu": True},
            "human_operated_visual_demo_only": True,
            "legal_scope": legal_scope,
            "log_closure": {"closed": True},
            "logs": [],
            "map": map_mapping,
            "prohibited_agent_adapter": True,
            "project": project_mapping,
            "project_static_tree": tree_mapping,
            "provider_id": profile["source_parent"]["provider_id"],
            "result": {"sha256": "5" * 64},
            "scene_receipt": {
                "path": str(scene_pin.path),
                "sha256": scene_pin.pin.sha256,
                "size_bytes": scene_pin.pin.size_bytes,
            },
            "static_delta": {"changed_file_count": 10},
        },
    )
    complete, complete_pin = _write_receipt(
        h_root / "hssd-r2-citysample-live-host-complete.json",
        {
            "schema_version": "simworld.vista.hssd-r2-citysample-live-complete/v1",
            "status": "hssd_r2_citysample_live_publication_complete",
            "attempt_root": str(h_root),
            "combined_receipt": {
                "path": str(combined_pin.path),
                "sha256": combined_pin.pin.sha256,
                "size_bytes": combined_pin.pin.size_bytes,
            },
            "combined_receipt_sidecar": {"path": "combined.sha256"},
            "current_state": {"project_static_tree": tree_mapping, "map": map_file},
            "failure_absent": True,
            "host_receipt": {
                "path": str(host_pin.path),
                "sha256": host_pin.pin.sha256,
                "size_bytes": host_pin.pin.size_bytes,
            },
        },
    )

    acquisition = profile["presentation_provenance"]["cc0_acquisition"]
    acquisition_reference = {
        "acquisition_manifest_sha256": acquisition["acquisition_manifest_sha256"],
        "provider": acquisition["provider"],
        "receipt_digest": acquisition["receipt_content_digest"],
        "receipt_file_sha256": acquisition["receipt_file_sha256"],
        "receipt_schema_version": acquisition["receipt_schema_version"],
    }
    manifest, manifest_pin = _write_receipt(
        tmp_path / "provenance/presentation-manifest.json",
        {
            "schema_version": "simworld.vista.playable-home-presentation-manifest/v1",
            "external_placement": {"acquisition_receipt": acquisition_reference},
            "ue_import_bundles": [
                {"external_content": {"acquisition_receipt": acquisition_reference}}
                for _index in range(3)
            ],
            "materials": [
                {
                    "material_id": row["manifest_material_id"],
                    "material_identity_sha256": row["material_identity_sha256"],
                    "source_logical_asset_id": row["source_logical_asset_id"],
                    "source_tree_sha256": row["source_tree_sha256"],
                    "active_texture_semantics": row["active_texture_semantics"],
                    "pbr_source": {
                        "asset_id": row["source_asset_id"],
                        "logical_asset_id": row["source_logical_asset_id"],
                        "provider_files_hash": row["provider_files_hash"],
                        "resolution": row["resolution"],
                        "source_tree_sha256": row["source_tree_sha256"],
                        "files": row["source_files"],
                    },
                }
                for row in profile["presentation_provenance"]["external_material_links"]
            ],
        },
    )
    material_ids = [
        row["manifest_material_id"]
        for row in profile["presentation_provenance"]["external_material_links"]
    ]
    artifact, artifact_pin = _write_receipt(
        tmp_path / "provenance/presentation-artifact-receipt.json",
        {
            "schema_version": "simworld.vista.playable-home-presentation-artifact/v1",
            "artifacts": [{"artifact_id": "entry_hall", "material_ids": material_ids}],
            "ue_import_bundles": [
                {
                    "target_asset_id": "asset_bundle_entry_hall",
                    "material_ids": material_ids,
                }
            ],
        },
    )
    external_paths = [
        package["object_path"]
        for package in profile["replacement_packages"]
        if package["material_id"].startswith("r2_external_t_")
    ]
    imported, import_pin = _write_receipt(
        tmp_path / "provenance/presentation-import-receipt.json",
        {
            "schema_version": "simworld.vista.playable-home-presentation-import/v1",
            "assets": [
                {
                    "target_asset_id": "asset_bundle_entry_hall",
                    "material_ids": material_ids,
                    "inspection": {
                        "class_path": "/Script/Engine.StaticMesh",
                        "material_paths": external_paths,
                    },
                    "returned_object_paths": external_paths,
                }
            ],
        },
    )

    profile["source_parent"].update(
        {
            "run_parent": str(run_parent),
            "attempt_name": h_root.name,
            "attempt_root": str(h_root),
            "project_static_tree": tree_mapping,
        }
    )
    source_pins = {
        "complete_receipt": (complete_pin, complete),
        "combined_receipt": (combined_pin, combined),
        "host_receipt": (host_pin, host),
        "scene_receipt": (scene_pin, scene),
    }
    for key, (pin, document) in source_pins.items():
        row = profile["source_parent"][key]
        _pin_profile_row(row, pin)
        row["content_digest"] = document["content_digest"]
    _pin_profile_row(profile["source_parent"]["finish_profile"], finish_pin)
    profile["source_parent"]["finish_profile"]["content_digest"] = r2_profile[
        "content_digest"
    ]
    _pin_profile_row(profile["source_parent"]["project_descriptor"], project_pin)
    _pin_profile_row(profile["source_parent"]["map_package"], map_pin)

    provenance_root = manifest_pin.path.parent
    profile["presentation_provenance"]["source_root"] = str(provenance_root)
    provenance_pins = {
        "presentation_manifest": manifest_pin,
        "presentation_artifact_receipt": artifact_pin,
        "presentation_import_receipt": import_pin,
    }
    for key, pin in provenance_pins.items():
        _pin_profile_row(profile["presentation_provenance"][key], pin)

    profile, profile_pin = _write_profile(tmp_path / "profile.json", profile)
    config = dataclasses.replace(
        materializer.PRODUCTION_CONFIG,
        run_parent=run_parent,
        parent=materializer.ParentContract(
            root=h_root,
            complete=complete_pin,
            combined=combined_pin,
            host=host_pin,
            scene=scene_pin,
            finish_profile=finish_pin,
            project=project_pin,
            map_package=map_pin,
            failure_marker=h_root / "hssd-r2-citysample-live-host-failure.json",
            tree=tree,
        ),
        provenance=materializer.ProvenanceContract(
            root=provenance_root,
            manifest=manifest_pin,
            artifact_receipt=artifact_pin,
            import_receipt=import_pin,
        ),
        profile=profile_pin,
    )
    return Fixture(
        config=config,
        profile=profile,
        parent_documents={
            "complete": complete,
            "combined": combined,
            "host": host,
            "scene": scene,
        },
        provenance_documents={
            "manifest": manifest,
            "artifact_receipt": artifact,
            "import_receipt": imported,
        },
    )


def _publication_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> PublicationHarness:
    """Create a source-safe post-_validate_outputs publication checkpoint."""

    fixture = _fixture(tmp_path / "fixture")
    attempt = (tmp_path / "attempt").resolve()
    attempt.mkdir(mode=0o700)
    project_root = attempt / "project"
    project_root.mkdir(mode=0o700)
    source_project_root = fixture.config.parent.project.path.parent
    project_path = project_root / materializer.PROJECT_NAME
    _write(project_path, fixture.config.parent.project.path.read_bytes())
    map_relative = Path(materializer.MAP_RELATIVE_PATH)
    _write(
        project_root / map_relative,
        fixture.config.parent.map_package.path.read_bytes() + b"-r10",
    )
    for package in fixture.profile["replacement_packages"]:
        relative = Path(package["project_relative_path"])
        _write(
            project_root / relative,
            (source_project_root / relative).read_bytes(),
        )
    output_tree, output_manifest = materializer.r4._project_manifest(project_path)
    baseline_manifest = copy.deepcopy(output_manifest)
    baseline_manifest[map_relative.as_posix()]["sha256"] = "0" * 64
    map_artifact = materializer.r4._artifact(
        project_root / map_relative, "unit R10 output map"
    )

    def pin(name: str, digit: str) -> dict[str, Any]:
        return {
            "path": str(attempt / name),
            "sha256": digit * 64,
            "size_bytes": 1,
        }

    copied_inputs = {
        "materializer": pin(materializer.MATERIALIZER_NAME, "1"),
        "commandlet": pin(materializer.COMMANDLET_NAME, "2"),
        "source_h_commandlet_support": pin(materializer.SUPPORT_COMMANDLET_NAME, "3"),
        "profile": pin(materializer.PROFILE_LOCAL_NAME, "4"),
        "source_execution": pin(materializer.SOURCE_EXECUTION_LOCAL_NAME, "5"),
        "source_result": pin(materializer.SOURCE_RESULT_LOCAL_NAME, "6"),
        "source_scene": pin(materializer.SOURCE_SCENE_LOCAL_NAME, "7"),
        "source_finish_profile": pin(
            materializer.SOURCE_FINISH_PROFILE_LOCAL_NAME, "8"
        ),
        "source_host": pin(materializer.SOURCE_HOST_LOCAL_NAME, "9"),
        "source_complete": pin(materializer.SOURCE_COMPLETE_LOCAL_NAME, "a"),
        "source_combined": pin(materializer.SOURCE_COMBINED_LOCAL_NAME, "b"),
    }
    source_h = materializer._source_h_authority(copied_inputs)
    source_tree = copy.deepcopy(output_tree)
    source_tree["tree_sha256"] = "c" * 64
    execution = materializer._seal_document(
        {
            "schema_version": materializer.EXECUTION_SCHEMA,
            "status": materializer.EXECUTION_STATUS,
            "materializer": copied_inputs["materializer"],
            "commandlet": copied_inputs["commandlet"],
            "source_h_commandlet_support": copied_inputs["source_h_commandlet_support"],
            "profile": copied_inputs["profile"],
            "source_h_authority": source_h,
            "source_project_static_tree": source_tree,
        }
    )
    execution_path = attempt / materializer.EXECUTION_NAME
    execution_pin = _write(execution_path, materializer._canonical_json(execution)).pin
    result = materializer._seal_document(
        {
            "schema_version": materializer.RESULT_SCHEMA,
            "status": materializer.RESULT_STATUS,
            "provider_id": materializer.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution_sha256": execution_pin.sha256,
            "source_h_authority": source_h,
            "map_object_path": materializer.MAP_OBJECT_PATH,
            "map_package": map_artifact,
            "source_project_static_tree": source_tree,
            "project_static_tree": output_tree,
            "bindings": copy.deepcopy(fixture.profile["bindings"]),
            "observations": {"unit": "closed"},
            "legal_scope": copy.deepcopy(materializer.LEGAL_SCOPE),
            "claims": copy.deepcopy(materializer.RESULT_CLAIMS),
            "acceptance": copy.deepcopy(materializer.ACCEPTANCE),
            "gates": {"unit_closed": True},
            "error": None,
        }
    )
    result_path = attempt / materializer.RESULT_NAME
    result_pin = _write(result_path, materializer._canonical_json(result)).pin
    _write(
        result_path.with_name(result_path.name + ".sha256"),
        f"{result_pin.sha256}  {result_path.name}\n".encode("ascii"),
    )
    scene = materializer._seal_document(
        {
            "schema_version": materializer.SCENE_SCHEMA,
            "status": materializer.RESULT_STATUS,
            "provider_id": materializer.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": {
                "path": str(execution_path),
                "sha256": execution_pin.sha256,
                "size_bytes": execution_pin.size_bytes,
            },
            "result": {
                "path": str(result_path),
                "sha256": result_pin.sha256,
                "size_bytes": result_pin.size_bytes,
            },
            "source_h_authority": source_h,
            "map_object_path": materializer.MAP_OBJECT_PATH,
            "map_package": map_artifact,
            "source_project_static_tree": source_tree,
            "project_static_tree": output_tree,
            "bindings": copy.deepcopy(fixture.profile["bindings"]),
            "observations": {"unit": "closed"},
            "legal_scope": copy.deepcopy(materializer.LEGAL_SCOPE),
            "claims": copy.deepcopy(materializer.RESULT_CLAIMS),
            "acceptance": copy.deepcopy(materializer.ACCEPTANCE),
        }
    )
    scene_path = attempt / materializer.SCENE_NAME
    scene_pin = _write(scene_path, materializer._canonical_json(scene)).pin
    _write(
        scene_path.with_name(scene_path.name + ".sha256"),
        f"{scene_pin.sha256}  {scene_path.name}\n".encode("ascii"),
    )
    stdout_path = attempt / materializer.STDOUT_NAME
    _write(
        stdout_path,
        (
            materializer.RESULT_MARKER
            + json.dumps({"path": str(result_path), "sha256": result_pin.sha256})
            + "\n"
            + materializer.SCENE_MARKER
            + json.dumps({"path": str(scene_path), "sha256": scene_pin.sha256})
            + "\n"
        ).encode("utf-8"),
    )
    engine_log = attempt / materializer.ENGINE_LOG_NAME
    _write(engine_log, b"closed engine log\n")
    prepared = SimpleNamespace(attempt_root=attempt, profile=fixture.profile)
    validated_result, validated_scene, outputs = materializer._validate_outputs(
        prepared,
        execution=execution,
        execution_sha256=execution_pin.sha256,
        stdout_path=stdout_path,
        engine_log=engine_log,
        baseline_manifest=baseline_manifest,
    )
    monkeypatch.setattr(materializer, "_assert_prepared_sources", lambda _value: None)
    monkeypatch.setattr(
        materializer,
        "_validate_copied_inputs",
        lambda _value: copy.deepcopy(copied_inputs),
    )
    harness = PublicationHarness(
        prepared=prepared,
        execution_path=execution_path,
        execution=execution,
        execution_sha256=execution_pin.sha256,
        result=validated_result,
        scene=validated_scene,
        stdout_path=stdout_path,
        engine_log=engine_log,
        closed_log_seals=outputs["closed_log_seals"],
        baseline_manifest=baseline_manifest,
    )
    materializer._publication_state(
        harness.prepared,
        execution_path=harness.execution_path,
        execution=harness.execution,
        execution_sha256=harness.execution_sha256,
        result=harness.result,
        scene=harness.scene,
        stdout_path=harness.stdout_path,
        engine_log=harness.engine_log,
        closed_log_seals=harness.closed_log_seals,
        baseline_manifest=harness.baseline_manifest,
    )
    return harness


def _replace_profile(
    fixture: Fixture, mutate: Callable[[dict[str, Any]], None]
) -> materializer.Config:
    profile = copy.deepcopy(fixture.profile)
    mutate(profile)
    _, pin = _write_profile(fixture.config.profile.path, profile)
    return dataclasses.replace(fixture.config, profile=pin)


def test_committed_profile_is_exact_closed_and_canonical() -> None:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

    assert set(profile) == TOP_LEVEL_KEYS
    assert set(profile["source_parent"]) == SOURCE_PARENT_KEYS
    assert set(profile["presentation_provenance"]) == PROVENANCE_KEYS
    assert profile["schema_version"] == materializer.PROFILE_SCHEMA
    assert profile["profile_id"] == materializer.PROFILE_ID
    assert profile["content_digest"] == _profile_digest(profile)
    assert profile["content_digest"] == materializer.PROFILE_CONTENT_DIGEST
    assert all(set(row) == PACKAGE_KEYS for row in profile["replacement_packages"])
    assert all(set(row) == BINDING_KEYS for row in profile["bindings"])

    source = profile["source_parent"]
    assert {
        key: source[key]["sha256"] for key in EXPECTED_PARENT_SHA256
    } == EXPECTED_PARENT_SHA256
    assert source["project_static_tree"] == {
        "algorithm": "sha256-path-nul-mode-size-content-v1",
        "file_count": 2453,
        "total_bytes": 9_153_718_809,
        "tree_sha256": "74846d5a0afeb7f72ee3b21bbe965afd46968a4b16e60ca9dff08d665c380376",
    }
    assert source["provider_id"] == "citysample_crowd_visual_demo_v1"
    assert all(value is False for value in source["claims"].values())

    provenance = profile["presentation_provenance"]
    assert {
        key: provenance[key]["sha256"] for key in EXPECTED_PROVENANCE_SHA256
    } == EXPECTED_PROVENANCE_SHA256
    assert provenance["cc0_acquisition"] == {
        "provider": "poly_haven",
        "license": "CC0-1.0",
        "receipt_schema_version": "simworld.vista.playable-home-poly-haven-receipt/v1",
        "receipt_file_sha256": "6b894d75f61115a2d2d63769c091ae4da511e9ce9697cd0809fff1b3d1f910a3",
        "receipt_content_digest": "a8a6b03c8fae71b299a2fcb36764e2dc1ec32c1e4dcd0b30ff0d3db3223fef70",
        "acquisition_manifest_sha256": "317ca0f30409d04365ae8d7b5aa096e8454d8bc8fbe13a8b386935b19e719774",
    }
    assert len(provenance["external_material_links"]) == 2
    assert all(
        row["resolution"] == "4k" for row in provenance["external_material_links"]
    )
    assert all(
        len(row["source_files"]) == 3 for row in provenance["external_material_links"]
    )

    packages = profile["replacement_packages"]
    assert [
        (row["material_id"], row["sha256"], row["size_bytes"]) for row in packages
    ] == EXPECTED_PACKAGE_PINS
    assert all(
        row["class_path"] == "/Script/Engine.MaterialInstanceConstant"
        for row in packages
    )
    assert len({row["project_relative_path"] for row in packages}) == 5

    assert len(profile["actor_invariants"]) == 3
    assert all(
        row["actor_collision_enabled"] is True for row in profile["actor_invariants"]
    )
    assert all(
        row["collision_mode"] == "QueryAndPhysics"
        for row in profile["actor_invariants"]
    )
    assert all(
        row["collision_profile_name"] == "BlockAll"
        for row in profile["actor_invariants"]
    )
    assert all(
        row["collision_responses"] == {"Pawn": "Block", "Visibility": "Block"}
        for row in profile["actor_invariants"]
    )

    assert [
        (
            row["room_id"],
            row["surface_role"],
            row["actor_path"].rsplit(".", 1)[-1],
            row["slot_index"],
            row["after"]["material_id"],
        )
        for row in profile["bindings"]
    ] == EXPECTED_BINDINGS
    assert all(
        row["before"]["object_path"].startswith("/Game/") for row in profile["bindings"]
    )
    assert all(
        row["after"]["object_path"].startswith("/Game/") for row in profile["bindings"]
    )
    assert all(value is False for value in profile["claims"].values())
    assert profile["mutation_policy"]["binary_payload_in_git"] is False


def test_load_profile_rejects_raw_pin_digest_and_duplicate_key_drift(
    tmp_path: Path,
) -> None:
    source = PROFILE_PATH.read_bytes()
    exact = _write(tmp_path / "exact.json", source)
    loaded = materializer.load_profile(path=exact.path, expected_pin=exact.pin)
    assert loaded["content_digest"] == materializer.PROFILE_CONTENT_DIGEST

    changed = source.replace(b'"binding_count": 9', b'"binding_count": 8')
    changed_pin = _write(tmp_path / "changed.json", changed)
    with pytest.raises(materializer.R10Error):
        materializer.load_profile(path=changed_pin.path, expected_pin=exact.pin)
    with pytest.raises(materializer.R10Error):
        materializer.load_profile(path=changed_pin.path, expected_pin=changed_pin.pin)

    duplicate = source.replace(
        b'"profile_id": "hssd_r10_pbr_surface_retrofit_r1",',
        b'"profile_id": "hssd_r10_pbr_surface_retrofit_r1",\n'
        b'  "profile_id": "hssd_r10_pbr_surface_retrofit_r1",',
    )
    duplicate_pin = _write(tmp_path / "duplicate.json", duplicate)
    with pytest.raises(materializer.R10Error):
        materializer.load_profile(
            path=duplicate_pin.path, expected_pin=duplicate_pin.pin
        )


def test_dry_plan_is_deterministic_exact_and_zero_write(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    before = _tree_state(tmp_path)
    first = materializer.build_plan(ATTEMPT, config=fixture.config)
    second = materializer.build_plan(ATTEMPT, config=fixture.config)

    assert first.raw == second.raw
    assert _tree_state(tmp_path) == before
    assert not (fixture.config.run_parent / ATTEMPT).exists()
    report = first.report
    assert report["schema_version"] == materializer.PLAN_SCHEMA
    assert report["status"] == "ready_for_separate_nullrhi_execution"
    assert report["accepted"] is False
    assert report["mode"] == "dry_run_zero_writes"
    assert report["bindings"] == fixture.profile["bindings"]
    assert report["actor_invariants"] == fixture.profile["actor_invariants"]
    assert report["replacement_packages"] == fixture.profile["replacement_packages"]
    assert report["expected_delta"] == {
        "changed_file_count": 1,
        "changed_project_relative_paths": [
            fixture.profile["mutation_policy"]["only_changed_project_relative_path"]
        ],
        "material_binding_count": 9,
        "unchanged_replacement_package_count": 5,
    }
    assert report["security"] == {
        "default_zero_write": True,
        "writes_performed": False,
        "will_run_unreal": False,
        "will_run_blender": False,
        "will_use_gpu": False,
        "will_change_services": False,
        "will_download_assets": False,
        "caller_path_map_material_provider_overrides": False,
    }
    assert report["claims"] == fixture.profile["claims"]
    assert report["content_digest"] == materializer.content_digest(report)


@pytest.mark.parametrize(
    "attempt_name",
    [
        "../escape",
        "/absolute",
        "hssd-r10-pbr-surface-retrofit-r1-UPPER",
        "hssd-r10-pbr-surface-retrofit-r2-unit",
        "hssd-r10-pbr-surface-retrofit-r1-",
    ],
)
def test_attempt_name_path_variants_fail_closed(
    tmp_path: Path, attempt_name: str
) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(materializer.R10Error):
        materializer.build_plan(attempt_name, config=fixture.config)


def test_existing_and_casefold_attempt_collisions_fail_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    (fixture.config.run_parent / ATTEMPT).mkdir()
    with pytest.raises(materializer.R10Error):
        materializer.build_plan(ATTEMPT, config=fixture.config)

    (fixture.config.run_parent / ATTEMPT).rmdir()
    (fixture.config.run_parent / ATTEMPT.upper()).mkdir()
    with pytest.raises(materializer.R10Error):
        materializer.build_plan(ATTEMPT, config=fixture.config)


@pytest.mark.parametrize(
    ("mutate", "label"),
    [
        (
            lambda profile: profile["bindings"].append(
                copy.deepcopy(profile["bindings"][0])
            ),
            "extra binding",
        ),
        (lambda profile: profile["bindings"].reverse(), "binding order"),
        (
            lambda profile: profile["bindings"][0].__setitem__("slot_index", 1),
            "slot drift",
        ),
        (
            lambda profile: profile["bindings"][0]["after"].__setitem__(
                "object_path", profile["bindings"][0]["after"]["object_path"].lower()
            ),
            "case drift",
        ),
        (
            lambda profile: profile["actor_invariants"][0].__setitem__(
                "collision_profile_name", "NoCollision"
            ),
            "collision drift",
        ),
        (
            lambda profile: profile["actor_invariants"][0].__setitem__(
                "mesh_object_path", "/Game/caller/mesh.mesh"
            ),
            "mesh drift",
        ),
        (
            lambda profile: profile["replacement_packages"][0].__setitem__(
                "class_path", "/Script/Engine.Material"
            ),
            "class drift",
        ),
        (
            lambda profile: profile["claims"].__setitem__("gta_level_quality", True),
            "positive claim",
        ),
        (
            lambda profile: profile["presentation_provenance"][
                "cc0_acquisition"
            ].__setitem__("license", "proprietary"),
            "license drift",
        ),
    ],
)
def test_semantically_resealed_profile_drift_fails_closed(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    label: str,
) -> None:
    fixture = _fixture(tmp_path)
    config = _replace_profile(fixture, mutate)
    assert label
    with pytest.raises(materializer.R10Error):
        materializer.build_plan(ATTEMPT, config=config)


def test_coherent_reseal_cannot_swap_bathroom_slate_and_bedroom_wool(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    def swap(profile: dict[str, Any]) -> None:
        bathroom = profile["bindings"][0]
        bedroom = profile["bindings"][3]
        bathroom["after"], bedroom["after"] = (
            copy.deepcopy(bedroom["after"]),
            copy.deepcopy(bathroom["after"]),
        )

    config = _replace_profile(fixture, swap)
    with pytest.raises(materializer.R10Error, match="R10_literal"):
        materializer.build_plan(ATTEMPT, config=config)


def test_package_hash_path_case_and_symlink_drift_fail_closed(tmp_path: Path) -> None:
    for drift in ("hash", "case", "symlink"):
        root = tmp_path / drift
        root.mkdir()
        fixture = _fixture(root)
        package = fixture.profile["replacement_packages"][0]
        path = fixture.config.parent.root / "project" / package["project_relative_path"]
        if drift == "hash":
            path.write_bytes(path.read_bytes() + b"drift")
        elif drift == "case":
            path.rename(path.with_name(path.name.swapcase()))
        else:
            target = path.with_suffix(".held")
            path.rename(target)
            path.symlink_to(target)
        with pytest.raises(materializer.R10Error):
            materializer.build_plan(ATTEMPT, config=fixture.config)


def test_parent_provider_map_and_claim_drift_fail_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    cases = [
        lambda profile: profile["source_parent"].__setitem__("provider_id", "caller"),
        lambda profile: profile["source_parent"].__setitem__(
            "map_object_path", profile["source_parent"]["map_object_path"].lower()
        ),
        lambda profile: profile["source_parent"]["claims"].__setitem__(
            "runtime_visual_acceptance", True
        ),
    ]
    for index, mutate in enumerate(cases):
        config = _replace_profile(fixture, mutate)
        with pytest.raises(materializer.R10Error, match="R10_"):
            materializer.build_plan(f"{ATTEMPT}-{index}", config=config)


def test_provenance_pin_and_identity_drift_fail_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture.config.provenance.manifest.path.write_bytes(
        fixture.config.provenance.manifest.path.read_bytes() + b"drift"
    )
    with pytest.raises(materializer.R10Error):
        materializer.build_plan(ATTEMPT, config=fixture.config)

    identity_fixture = _fixture(tmp_path / "identity")
    config = _replace_profile(
        identity_fixture,
        lambda profile: profile["presentation_provenance"]["external_material_links"][
            0
        ].__setitem__("material_identity_sha256", "f" * 64),
    )
    with pytest.raises(materializer.R10Error):
        materializer.build_plan(f"{ATTEMPT}-identity", config=config)


def test_provenance_acquisition_reference_projection_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    manifest = copy.deepcopy(fixture.provenance_documents["manifest"])
    manifest["external_placement"]["acquisition_receipt"]["provider"] = "caller"
    _document, manifest_pin = _write_receipt(
        fixture.config.provenance.manifest.path,
        manifest,
    )
    profile = copy.deepcopy(fixture.profile)
    _pin_profile_row(
        profile["presentation_provenance"]["presentation_manifest"],
        manifest_pin,
    )
    _profile, profile_pin = _write_profile(fixture.config.profile.path, profile)
    config = dataclasses.replace(
        fixture.config,
        provenance=dataclasses.replace(
            fixture.config.provenance,
            manifest=manifest_pin,
        ),
        profile=profile_pin,
    )

    with pytest.raises(materializer.R10Error, match="acquisition reference"):
        materializer.build_plan(ATTEMPT, config=config)


def test_cli_surface_has_no_path_map_material_or_provider_override() -> None:
    completed = subprocess.run(
        [sys.executable, str(Path(materializer.__file__)), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--attempt-name" in completed.stdout
    assert "--apply" in completed.stdout
    assert "--execution-acknowledgement" in completed.stdout
    for prohibited in (
        "--profile",
        "--run-parent",
        "--parent",
        "--map",
        "--material",
        "--provider",
        "--engine-root",
        "--gpu",
        "--service",
    ):
        assert prohibited not in completed.stdout

    rejected = subprocess.run(
        [
            sys.executable,
            str(Path(materializer.__file__)),
            "--attempt-name",
            ATTEMPT,
            "--provider",
            "caller",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 2
    assert "unrecognized arguments" in rejected.stderr


def test_apply_flag_only_authorizes_a_plan_and_does_not_execute(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    before = _tree_state(tmp_path)
    prepared = materializer.build_plan(
        ATTEMPT,
        config=fixture.config,
        apply=True,
        execution_acknowledgement=materializer.EXECUTION_ACKNOWLEDGEMENT,
    )

    assert _tree_state(tmp_path) == before
    assert not (fixture.config.run_parent / ATTEMPT).exists()
    assert prepared.report["mode"] == "authorized_plan_zero_writes"
    assert prepared.report["security"]["writes_performed"] is False
    assert prepared.report["security"]["will_run_unreal"] is False


@pytest.mark.parametrize("acknowledgement", [None, "", "caller-selected"])
def test_apply_requires_the_exact_execution_acknowledgement(
    tmp_path: Path, acknowledgement: str | None
) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(materializer.R10Error):
        materializer.build_plan(
            ATTEMPT,
            config=fixture.config,
            apply=True,
            execution_acknowledgement=acknowledgement,
        )


def test_host_and_commandlet_closed_contracts_are_exactly_aligned() -> None:
    assert materializer.EXECUTION_SCHEMA == commandlet.EXECUTION_SCHEMA
    assert materializer.RESULT_SCHEMA == commandlet.RESULT_SCHEMA
    assert materializer.SCENE_SCHEMA == commandlet.SCENE_RECEIPT_SCHEMA
    assert materializer.RESULT_STATUS == commandlet.RESULT_STATUS
    assert materializer.PROFILE_SCHEMA == commandlet.PROFILE_SCHEMA
    assert materializer.PROFILE_ID == commandlet.PROFILE_ID
    assert materializer.PROFILE_CONTENT_DIGEST == commandlet.PROFILE_CONTENT_DIGEST
    assert materializer.EXECUTION_CLAIMS == commandlet.EXECUTION_CLAIMS
    assert materializer.RESULT_CLAIMS == commandlet.RESULT_CLAIMS
    assert materializer.LEGAL_SCOPE == commandlet.LEGAL_SCOPE
    assert materializer.ACCEPTANCE == commandlet.ACCEPTANCE
    assert materializer.ACKNOWLEDGEMENTS == commandlet.ACKNOWLEDGEMENTS
    assert materializer.EXPECTED_COUNTS == commandlet.EXPECTED_COUNTS
    assert materializer.SUPPORT_COMMANDLET_NAME == commandlet.SUPPORT_NAME
    assert (
        materializer.SOURCE_EXECUTION_LOCAL_NAME == commandlet.SOURCE_H_EXECUTION_NAME
    )
    assert materializer.SOURCE_RESULT_LOCAL_NAME == commandlet.SOURCE_H_RESULT_NAME
    assert materializer.SOURCE_SCENE_LOCAL_NAME == commandlet.SOURCE_H_SCENE_NAME
    assert (
        materializer.SOURCE_FINISH_PROFILE_LOCAL_NAME
        == commandlet.SOURCE_H_FINISH_PROFILE_NAME
    )
    assert materializer.SOURCE_HOST_LOCAL_NAME == commandlet.SOURCE_H_HOST_NAME
    assert materializer.SOURCE_COMPLETE_LOCAL_NAME == commandlet.SOURCE_H_COMPLETE_NAME
    assert materializer.SOURCE_COMBINED_LOCAL_NAME == commandlet.SOURCE_H_COMBINED_NAME
    assert materializer.RESULT_KEYS == set(commandlet.RESULT_KEYS)
    assert materializer.SCENE_KEYS == set(commandlet.SCENE_KEYS)
    assert materializer.LITERAL_BINDING_MATRIX == tuple(
        (
            row["room_id"],
            row["actor_path"],
            row["component_path"],
            row["slot_index"],
            row["before"]["object_path"],
            row["before"]["class_path"],
            row["after"]["material_id"],
            row["after"]["object_path"],
            row["after"]["class_path"],
            row["after"]["package_project_relative_path"],
            row["after"]["package_sha256"],
            row["after"]["package_size_bytes"],
        )
        for row in commandlet.BINDING_AUTHORITY
    )


def test_nullrhi_command_and_environment_are_closed_without_gpu_or_credentials(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    prepared = materializer.build_plan(
        ATTEMPT,
        config=fixture.config,
        apply=True,
        execution_acknowledgement=materializer.EXECUTION_ACKNOWLEDGEMENT,
    )
    project = prepared.attempt_root / "project/VistaPlayableHome.uproject"
    commandlet_path = prepared.attempt_root / materializer.COMMANDLET_NAME
    private_root = prepared.attempt_root / "runtime"
    command = materializer.build_unreal_command(
        prepared,
        project=project,
        commandlet=commandlet_path,
        private_root=private_root,
    )
    assert command[:4] == [
        str(fixture.config.bwrap.path),
        "--unshare-net",
        "--unshare-pid",
        "--die-with-parent",
    ]
    assert "--ro-bind" in command
    assert "-nullrhi" in command
    assert "-notraceserver" in command
    assert "-NoAnalytics" in command
    assert "-run=pythonscript" in command
    assert f"-script={commandlet_path}" in command
    assert not any("graphicsadapter" in value.lower() for value in command)

    execution_path = prepared.attempt_root / materializer.EXECUTION_NAME
    environment = materializer.sanitized_environment(
        prepared,
        execution_path=execution_path,
        execution_sha256="a" * 64,
        private_root=private_root,
    )
    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert set(environment) == {
        "LANG",
        "LC_ALL",
        "PATH",
        "HOME",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "CUDA_VISIBLE_DEVICES",
        materializer.EXECUTION_ENV,
        materializer.EXECUTION_SHA_ENV,
        materializer.RESULT_ENV,
    }
    assert not any(
        token in key.upper()
        for key in environment
        for token in ("DISPLAY", "PROXY", "TOKEN", "SECRET", "AWS", "SSH")
    )


def test_post_commandlet_revalidation_rejects_any_copied_h_authority_drift(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    prepared = materializer.build_plan(
        ATTEMPT,
        config=fixture.config,
        apply=True,
        execution_acknowledgement=materializer.EXECUTION_ACKNOWLEDGEMENT,
    )
    prepared.attempt_root.mkdir(mode=0o700)
    copied = materializer._local_inputs(prepared)
    assert (
        materializer._validate_copied_inputs(prepared)["source_scene"]
        == copied["source_scene"]
    )

    source_scene = prepared.attempt_root / materializer.SOURCE_SCENE_LOCAL_NAME
    source_scene.write_bytes(source_scene.read_bytes() + b"drift")
    with pytest.raises(materializer.R10Error, match="source_scene"):
        materializer._validate_copied_inputs(prepared)


def test_terminal_receipt_and_sidecar_revalidation_rejects_drift(
    tmp_path: Path,
) -> None:
    document = materializer._seal_document(
        {"schema_version": materializer.COMBINED_SCHEMA, "status": "unit"}
    )
    path = tmp_path / materializer.COMBINED_NAME
    pin = _write(path, materializer._canonical_json(document))
    observed = materializer._validate_expected_document(path, document, "combined")
    assert observed["sha256"] == pin.pin.sha256

    sidecar = path.with_name(path.name + ".sha256")
    _write(sidecar, f"{pin.pin.sha256}  {path.name}\n".encode("ascii"))
    materializer._validate_expected_sidecar(
        sidecar,
        digest=pin.pin.sha256,
        target_name=path.name,
        label="combined sidecar",
    )
    sidecar.write_bytes(b"0" * 64 + b"  wrong.json\n")
    with pytest.raises(materializer.R10Error):
        materializer._validate_expected_sidecar(
            sidecar,
            digest=pin.pin.sha256,
            target_name=path.name,
            label="combined sidecar",
        )


def _revalidate_publication(harness: PublicationHarness) -> dict[str, Any]:
    return materializer._publication_state(
        harness.prepared,
        execution_path=harness.execution_path,
        execution=harness.execution,
        execution_sha256=harness.execution_sha256,
        result=harness.result,
        scene=harness.scene,
        stdout_path=harness.stdout_path,
        engine_log=harness.engine_log,
        closed_log_seals=harness.closed_log_seals,
        baseline_manifest=harness.baseline_manifest,
    )


@pytest.mark.parametrize("name", [materializer.RESULT_NAME, materializer.SCENE_NAME])
def test_publication_rejects_single_shot_document_mutation_after_output_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    harness = _publication_harness(tmp_path, monkeypatch)
    path = harness.prepared.attempt_root / name
    path.write_bytes(path.read_bytes() + b"single-shot-drift")

    with pytest.raises(materializer.R10Error, match="current canonical bytes"):
        _revalidate_publication(harness)


@pytest.mark.parametrize("name", [materializer.RESULT_NAME, materializer.SCENE_NAME])
def test_publication_rejects_commandlet_sidecar_mutation_after_output_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    harness = _publication_harness(tmp_path, monkeypatch)
    sidecar = harness.prepared.attempt_root / (name + ".sha256")
    sidecar.write_bytes(b"0" * 64 + b"  drift.json\n")

    with pytest.raises(materializer.R10Error, match="linkage or mode"):
        _revalidate_publication(harness)


@pytest.mark.parametrize(
    "name",
    [
        materializer.RESULT_NAME,
        materializer.SCENE_NAME,
        materializer.RESULT_NAME + ".sha256",
        materializer.SCENE_NAME + ".sha256",
    ],
)
def test_publication_rejects_commandlet_document_or_sidecar_chmod_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    harness = _publication_harness(tmp_path, monkeypatch)
    (harness.prepared.attempt_root / name).chmod(0o640)

    with pytest.raises(materializer.R10Error, match="mode"):
        _revalidate_publication(harness)


@pytest.mark.parametrize("log_name", ["stdout", "engine"])
def test_publication_rejects_closed_log_mutation_after_output_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    log_name: str,
) -> None:
    harness = _publication_harness(tmp_path, monkeypatch)
    path = harness.stdout_path if log_name == "stdout" else harness.engine_log
    path.write_bytes(path.read_bytes() + b"late-log-drift\n")

    with pytest.raises(materializer.R10Error, match="closed log changed"):
        _revalidate_publication(harness)


def test_expected_document_and_sidecar_helpers_require_private_mode(
    tmp_path: Path,
) -> None:
    document = materializer._seal_document(
        {"schema_version": materializer.COMBINED_SCHEMA, "status": "mode-unit"}
    )
    path = tmp_path / materializer.COMBINED_NAME
    pin = _write(path, materializer._canonical_json(document))
    sidecar = path.with_name(path.name + ".sha256")
    _write(sidecar, f"{pin.pin.sha256}  {path.name}\n".encode("ascii"))

    path.chmod(0o640)
    with pytest.raises(materializer.R10Error, match="mode"):
        materializer._validate_expected_document(path, document, "mode document")
    path.chmod(0o600)
    sidecar.chmod(0o640)
    with pytest.raises(materializer.R10Error, match="mode"):
        materializer._validate_expected_sidecar(
            sidecar,
            digest=pin.pin.sha256,
            target_name=path.name,
            label="mode sidecar",
        )


def test_terminal_publication_snapshot_precedes_final_complete_o_excl() -> None:
    source = Path(materializer.__file__).read_text(encoding="utf-8")
    terminal_receipts = source.index(
        '"R10 terminal receipt bytes changed before COMPLETE"'
    )
    terminal_state = source.index("terminal = _publication_state(", terminal_receipts)
    complete_write = source.index(
        "r4._write_exclusive(attempt / COMPLETE_NAME", terminal_state
    )
    successful_return = source.index("return combined", complete_write)

    assert terminal_receipts < terminal_state < complete_write < successful_return
    assert source[complete_write:successful_return].count("r4._write_exclusive(") == 1
