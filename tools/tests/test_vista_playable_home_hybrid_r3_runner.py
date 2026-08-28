from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import sys
import types

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET_ROOT = ROOT / "tools/ue/vista_playable_home"
sys.path.insert(0, str(COMMANDLET_ROOT))
import run_hybrid_r3_composition as runner  # noqa: E402


def _placements() -> tuple[dict, ...]:
    rooms = (*runner.FORBIDDEN_HSSD_ROOMS, *runner.SELECTED_ROOMS)
    values = []
    semantic_count = 0
    for room_index, room_id in enumerate(rooms):
        for item_index in range(10):
            semantic_target_id = None
            if room_id in runner.SELECTED_ROOMS and semantic_count < 11:
                semantic_target_id = f"{room_id}/entity.test_{semantic_count}.01"
                semantic_count += 1
            values.append(
                {
                    "instance_id": f"hssd.r1/{room_index}.{item_index}",
                    "room_id": room_id,
                    "source_asset_id": "hssd.static.bed",
                    "semantic_target_id": semantic_target_id,
                    "object_path": runner._historical_asset_path("hssd.static.bed"),
                    "world_transform_cm": {
                        "location_cm": [item_index, 0, 0],
                        "rotation_deg": [0, 0, 0],
                        "scale": [1, 1, 1],
                    },
                    "actor_label": f"VISTA_HSSD_R5_{room_index}_{item_index}",
                    "tags": [
                        "VistaRole=hssd_visual_shell",
                        "VistaRoomId=" + room_id,
                    ],
                    "visual_policy": {
                        "collision_profile": "NoCollision",
                        "collision_enabled": False,
                        "simulate_physics": False,
                        "generate_overlap_events": False,
                        "can_ever_affect_navigation": False,
                        "mobility": "Static",
                        "interaction_authority": "none_visual_dressing",
                    },
                }
            )
    assert len(values) == 60
    return tuple(values)


def _snapshot(root: pathlib.Path, digest: str, files: int, directories: int, size: int):
    records = tuple(
        runner.phase1.FileRecord(
            relative_path=f"f{index}",
            source=root / f"f{index}",
            size_bytes=1,
            mode=runner.PRIVATE_FILE_MODE,
            sha256="0" * 64,
            device=1,
            inode=index + 1,
        )
        for index in range(files)
    )
    return runner.TreeSource(
        snapshot=runner.phase1.ProjectSnapshot(
            root=root,
            directories=tuple(f"d{index}" for index in range(directories)),
            files=records,
            tree_sha256=digest,
            total_bytes=size,
        ),
        root_entries=(),
    )


def _sources() -> runner.AcceptedSources:
    selected = tuple(
        copy.deepcopy(item)
        for item in _placements()
        if item["room_id"] in runner.SELECTED_ROOMS
    )
    return runner.AcceptedSources(
        production=_snapshot(
            pathlib.Path("/source/production"),
            runner.PRODUCTION_PROJECT_TREE_SHA256,
            runner.PRODUCTION_PROJECT_FILE_COUNT,
            runner.PRODUCTION_PROJECT_DIRECTORY_COUNT,
            runner.PRODUCTION_PROJECT_TOTAL_BYTES,
        ),
        hssd_namespace=_snapshot(
            pathlib.Path("/source/hssd"),
            runner.HSSD_NAMESPACE_TREE_SHA256,
            runner.HSSD_NAMESPACE_FILE_COUNT,
            runner.HSSD_NAMESPACE_DIRECTORY_COUNT,
            runner.HSSD_NAMESPACE_TOTAL_BYTES,
        ),
        production_result={},
        production_import={},
        production_scene={
            "room_observations": [
                {"room_id": room_id, "presentation_id": room_id + "/presentation"}
                for room_id in runner.PRODUCTION_PRESENTATION_ROOMS
            ]
        },
        production_manifest={},
        hssd_host={},
        hssd_scene={},
        hssd_import={
            "assets": [
                {
                    "source_asset_id": asset_id,
                    "object_path": runner._historical_asset_path(asset_id),
                }
                for asset_id in runner.HISTORICAL_HSSD_ASSET_IDS
            ]
        },
        placements=selected,
    )


def _production_evidence() -> dict[str, dict]:
    result = runner._seal(
        {
            "schema_version": "simworld.vista.playable-home-ue-build-result/v1",
            "status": "accepted_candidate",
            "visual_profile_id": "realistic_interior_r2",
            "attempt_root": str(runner.PRODUCTION_ATTEMPT_ROOT),
            "map_path": runner.MAP_PATH,
            "presentation_bundle_count": 3,
            "presentation_external_content_verified": True,
            "presentation_external_nanite_disabled_verified": True,
            "import_receipt_sha256": runner.PRODUCTION_EVIDENCE_PINS[
                "import-receipt.json"
            ],
            "scene_receipt_sha256": runner.PRODUCTION_EVIDENCE_PINS[
                "scene-receipt.json"
            ],
            "base_scene_receipt_sha256": runner.PRODUCTION_EVIDENCE_PINS[
                "scene-receipt.json"
            ],
            "presentation_import_receipt_sha256": runner.PRODUCTION_EVIDENCE_PINS[
                "presentation-import-receipt.json"
            ],
            "presentation_scene_receipt_sha256": runner.PRODUCTION_EVIDENCE_PINS[
                "presentation-scene-receipt.json"
            ],
            "presentation_artifact_receipt_sha256": (
                runner.PRODUCTION_EVIDENCE_PINS[
                    "contracts/presentation-artifact-receipt.json"
                ]
            ),
            "presentation_manifest_sha256": runner.PRODUCTION_EVIDENCE_PINS[
                "contracts/presentation-manifest.json"
            ],
            "runtime_play_proof": "pending",
            "presentation_runtime_play_proof": "pending",
            "renderer_runtime_observation": "pending",
            "presentation_ue_import_observation": "verified_by_commandlet",
        }
    )
    result["content_digest"] = runner.PRODUCTION_RESULT_CONTENT_DIGEST
    room_counts = ((3, 1), (9, 2), (28, 2))
    rooms = []
    dressing_serial = 0
    target_serial = 0
    for room_id, (dressing_count, target_count) in zip(
        runner.PRODUCTION_PRESENTATION_ROOMS, room_counts
    ):
        dressings = [
            f"dress.synthetic.{dressing_serial + index}"
            for index in range(dressing_count)
        ]
        dressing_serial += dressing_count
        targets = [
            f"{room_id}/entity.synthetic_{target_serial + index}.01"
            for index in range(target_count)
        ]
        target_serial += target_count
        semantic_observations = [
            {
                "semantic_target_id": target,
                "semantic_id_property": target,
                "actor_path": "synthetic://" + target,
                "actor_hidden_in_game": True,
                "actor_class_path": (
                    "/Script/VistaPlayableHome.VistaSemanticPropActor"
                ),
                "interaction_affordances": ["inspect"],
                "render_components": [
                    {
                        "component_path": "synthetic://" + target + "/component",
                        "collision_enabled": True,
                        "collision_profile": (
                            runner.PRODUCTION_SEMANTIC_COLLISION_PROFILE
                        ),
                        "visible": False,
                    }
                ],
            }
            for target in targets
        ]
        rooms.append(
            {
                "room_id": room_id,
                "r1_authority_hidden_in_game": True,
                "r1_authority_component_visible": False,
                "r1_authority_collision_profile": (
                    runner.PRODUCTION_SEMANTIC_COLLISION_PROFILE
                ),
                "r1_semantic_visual_observations": semantic_observations,
                "external_content": {
                    "dressing_ids": dressings,
                    "semantic_target_ids": targets,
                },
            }
        )
    bundles = [
        {
            "room_id": room_id,
            "mesh_count": 1,
            "material_count": expected["material_count"],
            "pbr_complete_material_count": expected["material_count"],
            "texture_count": expected["texture_count"],
            "collision_policy": ("presentation_no_collision_use_hidden_r1_proxies"),
            "unreal_collision_profile": "NoCollision",
            "semantic_policy": "presentation_only_preserve_r1_authority",
            "external_content": {
                "semantic_target_ids": next(
                    room["external_content"]["semantic_target_ids"]
                    for room in rooms
                    if room["room_id"] == room_id
                ),
                "dressing_ids": next(
                    room["external_content"]["dressing_ids"]
                    for room in rooms
                    if room["room_id"] == room_id
                ),
            },
        }
        for room_id, expected in runner.PRODUCTION_BUNDLE_EVIDENCE.items()
    ]
    model_sources = [
        {
            "asset_type": "model",
            "resolution": "4k" if index >= 18 else "2k",
            "logical_asset_id": f"visual.model.synthetic.{index}",
            "source_tree_sha256": f"{index + 1:064x}",
            "files": [
                {
                    "texture_semantics": [
                        "base_color",
                        "normal",
                        "roughness",
                    ]
                }
            ],
        }
        for index in range(runner.PRODUCTION_EXTERNAL_MODEL_SOURCE_COUNT)
    ]
    texture_sources = [
        {
            "asset_type": "texture",
            "resolution": "4k",
            "logical_asset_id": material_id,
            "source_tree_sha256": f"{index + 101:064x}",
            "files": [{"texture_semantics": ["base_color", "normal", "roughness"]}],
        }
        for index, material_id in enumerate(
            runner.PRODUCTION_PROJECT_AUTHORED_PBR_MATERIAL_IDS
        )
    ]
    pbr_sources = [*model_sources, *texture_sources]
    all_dressings = [
        dressing
        for room in rooms
        for dressing in room["external_content"]["dressing_ids"]
    ]
    all_targets = [
        target
        for room in rooms
        for target in room["external_content"]["semantic_target_ids"]
    ]
    external_specs = [
        (dressing, None, "dressing") for dressing in all_dressings[:28]
    ] + [
        (f"hero.synthetic.external.{index}", target, "semantic_fixed")
        for index, target in enumerate(all_targets[:2])
    ]
    authored_specs = [
        (dressing, None, "dressing") for dressing in all_dressings[28:]
    ] + [
        (f"hero.synthetic.authored.{index}", target, "semantic_fixed")
        for index, target in enumerate(all_targets[2:])
    ]
    external_placements = [
        {
            "placement_id": placement_id,
            "placement_kind": placement_kind,
            "semantic_target_id": semantic_target_id,
            "realization_mode": "external_blend",
            "source_logical_asset_id": model_sources[index % len(model_sources)][
                "logical_asset_id"
            ],
            "source_tree_sha256": model_sources[index % len(model_sources)][
                "source_tree_sha256"
            ],
            "geometry_recipe": None,
            "material_logical_asset_ids": [],
        }
        for index, (placement_id, semantic_target_id, placement_kind) in enumerate(
            external_specs
        )
    ]
    authored_placements = [
        {
            "placement_id": placement_id,
            "placement_kind": placement_kind,
            "semantic_target_id": semantic_target_id,
            "realization_mode": "project_authored",
            "source_logical_asset_id": None,
            "source_tree_sha256": None,
            "geometry_recipe": "synthetic_geometry_v1",
            "material_logical_asset_ids": [
                runner.PRODUCTION_PROJECT_AUTHORED_PBR_MATERIAL_IDS[
                    index % len(runner.PRODUCTION_PROJECT_AUTHORED_PBR_MATERIAL_IDS)
                ]
            ],
        }
        for index, (placement_id, semantic_target_id, placement_kind) in enumerate(
            authored_specs
        )
    ]
    return {
        "result-receipt.json": result,
        "import-receipt.json": {
            "schema_version": "simworld.vista.playable-home-ue-import-receipt/v1",
            "status": "imported_candidate",
            "error": None,
            "assets": [{}] * runner.PRODUCTION_BASE_IMPORT_ASSET_COUNT,
            "gates": {
                "all_assets_bound": True,
                "core_textures_imported_and_used": True,
                "quarantined": False,
            },
        },
        "scene-receipt.json": {
            "schema_version": "simworld.vista.playable-home-ue-scene-receipt/v1",
            "status": "saved_reloaded_candidate",
            "error": None,
            "map_path": runner.MAP_PATH,
            "gates": {
                "map_saved": True,
                "map_reloaded": True,
                "semantic_tags_verified": True,
                "runtime_play_proof": "pending",
                "quarantined": False,
            },
        },
        "presentation-import-receipt.json": {
            "schema_version": (
                "simworld.vista.playable-home-ue-presentation-import-receipt/v2"
            ),
            "status": "imported_candidate",
            "error": None,
            "assets": [{}, {}, {}],
            "gates": {
                "exact_three_room_bundles": True,
                "external_content_preserved": True,
                "materials_and_textures_inspected": True,
                "runtime_play_proof": "pending",
                "quarantined": False,
            },
        },
        "presentation-scene-receipt.json": {
            "schema_version": (
                "simworld.vista.playable-home-ue-presentation-scene-receipt/v2"
            ),
            "status": "saved_reloaded_candidate",
            "error": None,
            "map_path": runner.MAP_PATH,
            "room_observations": rooms,
            "gates": {
                "exact_three_presentation_actors": True,
                "hidden_r1_collision_authority_verified": True,
                "semantic_authority_preserved": True,
                "external_r1_semantic_visual_targets_verified": True,
                "presentation_no_collision_verified": True,
                "runtime_play_proof": "pending",
                "quarantined": False,
            },
        },
        "contracts/presentation-artifact-receipt.json": {
            "schema_version": "simworld.vista.playable-home-realism-artifacts/v2",
            "artifacts": [{}] * runner.PRODUCTION_PRESENTATION_ARTIFACT_COUNT,
            "ue_import_bundles": copy.deepcopy(bundles),
        },
        "contracts/presentation-manifest.json": {
            "schema_version": "simworld.vista.playable-home-realism-forge/v2",
            "visual_profile_id": "realistic_interior_r2",
            "build_quality": {
                "accepted_as_r2_visual_evidence": False,
                "production_minimum_texture_size_px": (
                    runner.PRODUCTION_MINIMUM_TEXTURE_SIZE_PX
                ),
                "requires_downstream_asset_and_ue_review": True,
            },
            "external_placement": {
                "acquisition_receipt": {
                    "provider": runner.PRODUCTION_EXTERNAL_ASSET_PROVIDER
                },
                "asset_sources": pbr_sources,
                "placements": [*external_placements, *authored_placements],
                "content_digest": runner.PRODUCTION_EXTERNAL_PLACEMENT_CONTENT_DIGEST,
                "placement_manifest_sha256": (
                    runner.PRODUCTION_EXTERNAL_PLACEMENT_MANIFEST_SHA256
                ),
            },
            "ue_import_bundles": bundles,
        },
    }


@pytest.fixture
def planned(monkeypatch: pytest.MonkeyPatch):
    sources = _sources()
    monkeypatch.setattr(runner, "_validate_toolchain", lambda: None)
    monkeypatch.setattr(runner, "validate_sources", lambda: sources)
    return sources


def _patch_synthetic_production_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    def placement_digest(values):
        modes = {item.get("realization_mode") for item in values}
        if len(values) == runner.PRODUCTION_PBR_BACKED_PLACEMENT_COUNT:
            return runner.PRODUCTION_PBR_PLACEMENTS_SHA256
        if modes == {"external_blend"}:
            return runner.PRODUCTION_EXTERNAL_MODEL_PLACEMENTS_SHA256
        if modes == {"project_authored"}:
            return runner.PRODUCTION_PROJECT_AUTHORED_PBR_PLACEMENTS_SHA256
        return "0" * 64

    monkeypatch.setattr(
        runner, "_content_digest", lambda value: value.get("content_digest")
    )
    monkeypatch.setattr(runner, "_compact_json_sha256", placement_digest)


def test_hybrid_contract_is_closed_to_unfinished_rooms() -> None:
    assert runner.SELECTED_ROOMS == (
        "home.r1/room.bedroom",
        "home.r1/room.office",
        "home.r1/room.bathroom_laundry",
    )
    assert set(runner.SELECTED_ROOMS).isdisjoint(runner.FORBIDDEN_HSSD_ROOMS)
    assert runner.SELECTED_ROOM_COUNTS == {
        room_id: 10 for room_id in runner.SELECTED_ROOMS
    }
    assert runner.HSSD_PLACEMENT_COUNT == 30
    assert runner.HSSD_SEMANTIC_PROXY_COUNT == 11


def test_historical_contract_pins_are_literal_and_match_attempt_bytes() -> None:
    assert runner.HSSD_CONTRACT_SOURCES == {
        "profile": (
            runner.HSSD_PHASE2_ATTEMPT_ROOT / "contracts/hssd_private_research_r1.json",
            runner.HISTORICAL_HSSD_PROFILE_SHA256,
        ),
        "house": (
            runner.HSSD_PHASE2_ATTEMPT_ROOT / "contracts/house.json",
            runner.HISTORICAL_HSSD_HOUSE_SHA256,
        ),
        "scene_plan": (
            runner.HSSD_PHASE2_ATTEMPT_ROOT / "contracts/scene-plan.json",
            runner.HISTORICAL_HSSD_SCENE_PLAN_SHA256,
        ),
    }
    for label, (path, expected_sha) in runner.HSSD_CONTRACT_SOURCES.items():
        document = runner._read_pinned_json(path, expected_sha, label)
        assert runner._sha256(path) == expected_sha
        assert isinstance(document["content_digest"], str)
    assert runner.HISTORICAL_HSSD_PROFILE_SHA256 != runner.phase2.PROFILE_SHA256
    assert runner.HISTORICAL_HSSD_HOUSE_SHA256 != runner.phase2.HOUSE_SHA256
    assert runner.HISTORICAL_HSSD_SCENE_PLAN_SHA256 != runner.phase2.SCENE_PLAN_SHA256


def test_historical_proxy_validator_accepts_only_pinned_r3_authority() -> None:
    scene = runner._read_pinned_json(
        runner.HSSD_PHASE2_ATTEMPT_ROOT / "hssd-phase2-scene-receipt.json",
        runner.HSSD_EVIDENCE_PINS["hssd-phase2-scene-receipt.json"],
        "historical HSSD scene receipt",
    )
    proxies = scene["semantic_proxies"]

    assert len(proxies) == 19
    assert all(runner._historical_proxy_receipt_valid(proxy) for proxy in proxies)
    assert runner._historical_semantic_proxy_component_total(proxies) == 19

    tampered = copy.deepcopy(proxies[0])
    tampered["reloaded"]["components"][0]["collision_responses"]["Pawn"] = "Ignore"
    assert not runner._historical_proxy_receipt_valid(tampered)


def test_production_r3_pins_match_attempt_bytes_and_projection() -> None:
    assert runner.PRODUCTION_ATTEMPT_ROOT == pathlib.Path(
        "/data/sysx/vista-world/runs/vista-action-world-r1/ue/"
        "attempt-golden-r3-presentation-r1"
    )
    assert runner.PRODUCTION_EVIDENCE_PINS == {
        "result-receipt.json": (
            "5e2f511f5b42b99066b1f1ab5293f78d9dde25490ecf1f3cf48a888e800abe43"
        ),
        "import-receipt.json": (
            "649e53e28183aa25a27ebf0939c82143a158ba8bb76a68548f22fbd704f26e7a"
        ),
        "scene-receipt.json": (
            "4acb2541348c30107e259df7a0bec0214736d88fdd06c747f0855e76beb32dfd"
        ),
        "presentation-import-receipt.json": (
            "7e46e1fb338b586ca0a64a1a917f07b8ca61a6c16df0b6bf662159ebd86c83b4"
        ),
        "presentation-scene-receipt.json": (
            "3cd656faee49d53e067337242fd3b7a00fd1a326af9c59a0dbdc14e7712a009f"
        ),
        "contracts/presentation-artifact-receipt.json": (
            "f4c55a1ef674ad3ba3cfa980e4321255663437fc0811723768ce32ce604488c5"
        ),
        "contracts/presentation-manifest.json": (
            "b5c6b0dd2d172255cb5f7bb494657b8c1ed7f2f7a214557b08d7642590e0a71e"
        ),
    }
    assert runner.PRODUCTION_RESULT_CONTENT_DIGEST == (
        "03208aa552b8945e9ac4b4fdb15fe2862477e9f66ac79fb904ee0c623d7e975f"
    )
    assert runner.PRODUCTION_PROJECT_DESCRIPTOR_SHA256 == (
        "784fbbf0bf2f2581571de6b190dc4d7e5f328d9c10ef561a8d9bb851e02604b4"
    )
    assert runner.PRODUCTION_MAP_SHA256 == (
        "4767da064bcb0f470724635579e50fc288984cd2328849adda8a41b8e2e71a9f"
    )
    assert runner.PRODUCTION_PBR_BACKED_PLACEMENT_COUNT == 45
    assert runner.PRODUCTION_EXTERNAL_MODEL_PLACEMENT_COUNT == 30
    assert runner.PRODUCTION_PROJECT_AUTHORED_PBR_PLACEMENT_COUNT == 15
    assert runner.PRODUCTION_PBR_PLACEMENTS_SHA256 == (
        "56351a7753a9eb82169e78fc9164d901fa43c37f6ab7c55bf070aa6fa7f55ed4"
    )
    assert (
        runner._sha256(runner.PRODUCTION_PROJECT_ROOT / runner.PRODUCTION_PROJECT_NAME)
        == runner.PRODUCTION_PROJECT_DESCRIPTOR_SHA256
    )
    assert (
        runner._sha256(
            runner.PRODUCTION_PROJECT_ROOT / pathlib.Path(runner.MAP_RELATIVE_FILE)
        )
        == runner.PRODUCTION_MAP_SHA256
    )
    for relative, expected_sha in runner.PRODUCTION_EVIDENCE_PINS.items():
        assert runner._sha256(runner.PRODUCTION_ATTEMPT_ROOT / relative) == expected_sha

    source = runner._snapshot_tree(
        runner.PRODUCTION_PROJECT_ROOT,
        required_entries=(
            *runner.PRODUCTION_COPY_ROOTS,
            runner.PRODUCTION_PROJECT_NAME,
        ),
        allowed_entries=(
            *runner.PRODUCTION_COPY_ROOTS,
            *runner.PRODUCTION_EXCLUDED_ROOTS,
            runner.PRODUCTION_PROJECT_NAME,
        ),
        include_entries=(*runner.PRODUCTION_COPY_ROOTS, runner.PRODUCTION_PROJECT_NAME),
    )
    assert source.snapshot.tree_sha256 == (
        "9d8c234e12507b8c3d9e449cb6dafacb4d62b16ea2884dcdb1d35631bfdd30d6"
    )
    assert len(source.snapshot.files) == 745
    assert len(source.snapshot.directories) == 190
    assert source.snapshot.total_bytes == 2_497_876_659


def test_production_r3_real_receipts_validate_without_mocks() -> None:
    evidence = runner._load_evidence(
        runner.PRODUCTION_ATTEMPT_ROOT,
        runner.PRODUCTION_EVIDENCE_PINS,
        "Production R3 test evidence",
    )

    runner._validate_production_evidence(evidence)


def test_production_evidence_derives_exact_45_pbr_backed_placements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _production_evidence()
    _patch_synthetic_production_digests(monkeypatch)

    runner._validate_production_evidence(evidence)


def test_production_evidence_rejects_44_pbr_backed_placements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _production_evidence()
    evidence["presentation-scene-receipt.json"]["room_observations"][0][
        "external_content"
    ]["dressing_ids"].pop()
    _patch_synthetic_production_digests(monkeypatch)

    with pytest.raises(runner.RunnerError, match="scene receipt differs"):
        runner._validate_production_evidence(evidence)


def test_production_evidence_rejects_semantic_authority_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _production_evidence()
    observation = evidence["presentation-scene-receipt.json"]["room_observations"][0][
        "r1_semantic_visual_observations"
    ][0]
    observation["render_components"][0]["collision_profile"] = "NoCollision"
    _patch_synthetic_production_digests(monkeypatch)

    with pytest.raises(runner.RunnerError, match="scene receipt differs"):
        runner._validate_production_evidence(evidence)


def test_runtime_semantic_authority_rejects_collision_and_affordance_drift() -> None:
    evidence = _production_evidence()
    expected = evidence["presentation-scene-receipt.json"]["room_observations"][0][
        "r1_semantic_visual_observations"
    ][0]
    semantic_target_id = expected["semantic_target_id"]
    component_path = expected["render_components"][0]["component_path"]
    actual = {
        "semantic_target_id": semantic_target_id,
        "actor_path": expected["actor_path"],
        "actor_label": "Synthetic authority",
        "actor_class_path": expected["actor_class_path"],
        "actor_hidden_in_game": True,
        "actor_collision_enabled": True,
        "world_transform_cm": {
            "location_cm": [0, 0, 0],
            "rotation_deg": [0, 0, 0],
            "scale": [1, 1, 1],
        },
        "tags": ["VistaSemanticId=" + semantic_target_id],
        "semantic_state": {
            "semantic_id": semantic_target_id,
            "world_revision": "vista_playable_home_r1",
            "allowed_affordances": ["<VistaAffordance.INSPECT: 7>"],
            "initial_state_values": {},
        },
        "components": [
            {
                "component_path": component_path,
                "mesh_path": "/Game/Synthetic/SyntheticMesh.SyntheticMesh",
                "collision_profile": runner.PRODUCTION_SEMANTIC_COLLISION_PROFILE,
                "collision_mode": runner.PRODUCTION_SEMANTIC_COLLISION_MODE,
                "collision_responses": (runner.PRODUCTION_SEMANTIC_COLLISION_RESPONSES),
                "collision_enabled": True,
                "simulate_physics": False,
                "generate_overlap_events": False,
                "can_ever_affect_navigation": True,
                "mobility": "Static",
                "visible": False,
            }
        ],
    }

    assert runner._production_runtime_semantic_valid(actual, expected)

    wrong_mode = copy.deepcopy(actual)
    wrong_mode["components"][0]["collision_mode"] = "NoCollision"
    assert not runner._production_runtime_semantic_valid(wrong_mode, expected)

    wrong_response = copy.deepcopy(actual)
    wrong_response["components"][0]["collision_responses"]["Pawn"] = "Ignore"
    assert not runner._production_runtime_semantic_valid(wrong_response, expected)

    wrong_affordance = copy.deepcopy(actual)
    wrong_affordance["semantic_state"]["allowed_affordances"] = [
        "<VistaAffordance.TOGGLE: 5>"
    ]
    assert not runner._production_runtime_semantic_valid(wrong_affordance, expected)


def test_production_evidence_rejects_incomplete_pbr_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _production_evidence()
    evidence["contracts/presentation-manifest.json"]["ue_import_bundles"][0][
        "pbr_complete_material_count"
    ] -= 1
    _patch_synthetic_production_digests(monkeypatch)

    with pytest.raises(runner.RunnerError, match="manifest differs"):
        runner._validate_production_evidence(evidence)


def test_production_evidence_rejects_30_15_realization_split_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _production_evidence()
    placements = evidence["contracts/presentation-manifest.json"]["external_placement"][
        "placements"
    ]
    authored = next(
        item for item in placements if item["realization_mode"] == "project_authored"
    )
    authored["realization_mode"] = "external_blend"
    _patch_synthetic_production_digests(monkeypatch)

    with pytest.raises(runner.RunnerError, match="manifest differs"):
        runner._validate_production_evidence(evidence)


def test_production_evidence_rejects_runtime_acceptance_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _production_evidence()
    evidence["result-receipt.json"]["runtime_play_proof"] = "accepted"
    _patch_synthetic_production_digests(monkeypatch)

    with pytest.raises(runner.RunnerError, match="Production R3 result"):
        runner._validate_production_evidence(evidence)


def test_selected_placements_are_derived_from_real_historical_contracts() -> None:
    selected = runner._derive_selected_placements()

    assert len(selected) == 30
    assert {item["room_id"] for item in selected} == set(runner.SELECTED_ROOMS)
    assert not {item["room_id"] for item in selected}.intersection(
        runner.FORBIDDEN_HSSD_ROOMS
    )
    assert sum(item["semantic_target_id"] is not None for item in selected) == 11
    assert (
        hashlib.sha256(
            json.dumps(
                selected,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        == runner.HISTORICAL_SELECTED_PLACEMENTS_SHA256
    )


def test_selected_placement_derivation_fails_closed_on_count_drift() -> None:
    contracts = {
        label: runner._read_pinned_json(path, expected_sha, label)
        for label, (path, expected_sha) in runner.HSSD_CONTRACT_SOURCES.items()
    }
    contracts["scene_plan"]["placements"].pop()

    with pytest.raises(runner.RunnerError, match="scene-plan identity differs"):
        runner._derive_historical_placements(
            contracts["profile"], contracts["house"], contracts["scene_plan"]
        )


def test_dry_run_is_nonwriting_and_denies_quality_claims(planned) -> None:
    attempt = runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-unit-dry-run"
    assert not os.path.lexists(attempt)

    plan, returned = runner.build_plan(attempt, apply=False)

    assert returned is planned
    assert plan["mode"] == "dry_run"
    assert plan["will_write"] is False
    assert plan["will_run_unreal"] is False
    assert plan["placement_count"] == 30
    assert plan["room_counts"] == runner.SELECTED_ROOM_COUNTS
    assert plan["production_source"] == runner._production_source_summary(planned)
    assert plan["production_source"]["presentation_bundle_count"] == 3
    assert plan["production_source"]["pbr_backed_placement_count"] == 45
    assert plan["production_source"]["external_model_placement_count"] == 30
    assert plan["production_source"]["project_authored_pbr_placement_count"] == 15
    assert plan["production_source"]["semantic_target_count"] == 5
    assert plan["production_source"]["runtime_play_proof"] == "pending"
    assert plan["claims"] == {
        "production_presentation_preserved": False,
        "hssd_placements_composed": False,
        "player_eye_reviewed": False,
        "gta_level": False,
        "real_human_present": False,
        "interaction_proven": False,
    }
    assert plan["content_digest"] == runner._content_digest(plan)
    assert not os.path.lexists(attempt)


@pytest.mark.parametrize(
    ("license_allowed", "material_allowed"),
    [(False, False), (True, False), (False, True)],
)
def test_apply_requires_both_nonpromotable_acknowledgements(
    planned, license_allowed: bool, material_allowed: bool
) -> None:
    attempt = runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-unit-refused"
    assert not os.path.lexists(attempt)

    with pytest.raises(runner.RunnerError, match="requires both explicit"):
        runner.build_plan(
            attempt,
            apply=True,
            allow_private_noncommercial_license=license_allowed,
            allow_nonpromotable_material_conflict=material_allowed,
        )

    assert not os.path.lexists(attempt)


def test_authorized_apply_plan_still_denies_promotion_and_gpu1(planned) -> None:
    attempt = runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-unit-authorized"
    plan, _ = runner.build_plan(
        attempt,
        apply=True,
        allow_private_noncommercial_license=True,
        allow_nonpromotable_material_conflict=True,
    )

    assert plan["mode"] == "diagnostic_apply"
    assert plan["promotable"] is False
    assert plan["full_material_fidelity"] is False
    assert plan["accepted_as_visual_evidence"] is False
    assert plan["toolchain"]["rendering"] == "NullRHI"
    assert plan["toolchain"]["gpu_assignment"] == "GPU0_only"
    assert plan["toolchain"]["gpu1_use"] is False
    assert plan["policy"]["license_scope"] == "private_noncommercial_research_only"
    assert plan["policy"]["public_payload_distribution"] == "prohibited"


def test_apply_rejects_tampered_sealed_plan_before_creation(planned) -> None:
    attempt = runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-unit-tampered"
    plan, _ = runner.build_plan(
        attempt,
        apply=True,
        allow_private_noncommercial_license=True,
        allow_nonpromotable_material_conflict=True,
    )
    plan["placement_count"] = 60

    with pytest.raises(runner.RunnerError, match="intact authorized"):
        runner.apply_plan(plan, planned)

    assert not os.path.lexists(attempt)


def test_apply_rejects_resealed_production_source_tamper(planned) -> None:
    attempt = runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-unit-source-tampered"
    plan, _ = runner.build_plan(
        attempt,
        apply=True,
        allow_private_noncommercial_license=True,
        allow_nonpromotable_material_conflict=True,
    )
    plan["production_source"]["runtime_play_proof"] = "accepted"
    plan["content_digest"] = runner._content_digest(plan)

    with pytest.raises(runner.RunnerError, match="intact authorized"):
        runner.apply_plan(plan, planned)

    assert not os.path.lexists(attempt)


def test_apply_rejects_resealed_attempt_redirect_before_creation(planned) -> None:
    original = runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-unit-redirect-source"
    redirected = pathlib.Path("/tmp/hybrid-r3-unit-redirect-target")
    assert not os.path.lexists(original)
    assert not os.path.lexists(redirected)
    plan, _ = runner.build_plan(
        original,
        apply=True,
        allow_private_noncommercial_license=True,
        allow_nonpromotable_material_conflict=True,
    )
    plan["attempt_root"] = str(redirected)
    plan["content_digest"] = runner._content_digest(plan)

    with pytest.raises(runner.RunnerError):
        runner.apply_plan(plan, planned)

    assert not os.path.lexists(original)
    assert not os.path.lexists(redirected)


@pytest.mark.parametrize(
    "attempt",
    [
        pathlib.Path("/tmp/hybrid-r3-outside"),
        runner.DEFAULT_OUTPUT_PARENT / "wrong-prefix",
        runner.DEFAULT_OUTPUT_PARENT / "hybrid-r3-nested/child",
    ],
)
def test_attempt_must_be_fresh_fixed_parent(attempt: pathlib.Path) -> None:
    with pytest.raises(runner.RunnerError):
        runner._fresh_attempt(attempt)


def test_snapshot_tree_rejects_symlink(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "real").write_text("x", encoding="utf-8")
    (source / "link").symlink_to(source / "real")

    with pytest.raises(runner.RunnerError, match="symlink"):
        runner._snapshot_tree(source)


def test_copy_tree_is_exclusive_and_byte_exact(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "root.bin").write_bytes(b"root")
    (source / "nested/payload.bin").write_bytes(b"payload")
    snapshot = runner._snapshot_tree(source).snapshot
    target = tmp_path / "target"

    runner._copy_tree(snapshot, target)

    observed = runner._snapshot_tree(target).snapshot
    assert observed.tree_sha256 == snapshot.tree_sha256
    assert observed.total_bytes == snapshot.total_bytes
    assert (target / "nested/payload.bin").read_bytes() == b"payload"
    assert (target / "root.bin").stat().st_mode & 0o777 == runner.PRIVATE_FILE_MODE
    assert target.stat().st_mode & 0o777 == runner.PRIVATE_DIRECTORY_MODE
    assert (target / "nested").stat().st_mode & 0o777 == runner.PRIVATE_DIRECTORY_MODE
    with pytest.raises(runner.RunnerError, match="already exists"):
        runner._copy_tree(snapshot, target)


def test_copy_tree_rejects_source_content_drift(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    payload = source / "payload.bin"
    payload.write_bytes(b"before")
    snapshot = runner._snapshot_tree(source).snapshot
    payload.write_bytes(b"after!")

    with pytest.raises(runner.RunnerError, match="copied tree file differs"):
        runner._copy_tree(snapshot, tmp_path / "target")


def test_post_project_projection_allows_only_map_and_exact_namespace(
    tmp_path: pathlib.Path,
) -> None:
    production_root = tmp_path / "production"
    map_path = production_root / pathlib.Path(runner.MAP_RELATIVE_FILE)
    map_path.parent.mkdir(parents=True)
    (production_root / "Config").mkdir()
    (production_root / "Plugins").mkdir()
    (production_root / runner.PRODUCTION_PROJECT_NAME).write_text(
        "{}", encoding="utf-8"
    )
    (production_root / "Config/DefaultEngine.ini").write_text(
        "[Core]", encoding="utf-8"
    )
    map_path.write_bytes(b"production-map")
    production = runner._snapshot_tree(production_root).snapshot

    namespace_root = tmp_path / "namespace"
    (namespace_root / "Assets/chair").mkdir(parents=True)
    (namespace_root / "Assets/chair/chair.uasset").write_bytes(b"sealed-hssd")
    namespace = runner._snapshot_tree(namespace_root).snapshot

    project = tmp_path / "project"
    runner._copy_tree(production, project)
    runner._copy_tree(namespace, project / pathlib.Path(runner.HSSD_NAMESPACE_RELATIVE))
    (project / pathlib.Path(runner.MAP_RELATIVE_FILE)).write_bytes(b"hybrid-map")
    for relative in runner.POST_COMMANDLET_EMPTY_CACHE_DIRECTORIES:
        (project / relative).mkdir(parents=True, exist_ok=True)

    observed = runner._validate_post_project_projection(project, production, namespace)
    assert len(observed.snapshot.files) == len(production.files) + len(namespace.files)
    assert not any(
        record.relative_path.startswith("DerivedDataCache/")
        for record in observed.snapshot.files
    )

    (project / "DerivedDataCache/VT/unexpected-cache.bin").write_bytes(b"cache")
    with pytest.raises(runner.RunnerError, match="gained or lost"):
        runner._validate_post_project_projection(project, production, namespace)
    (project / "DerivedDataCache/VT/unexpected-cache.bin").unlink()

    (project / "Content/unexpected.uasset").write_bytes(b"unexpected")
    with pytest.raises(runner.RunnerError, match="gained or lost"):
        runner._validate_post_project_projection(project, production, namespace)


def test_upstream_commandlet_pin_has_one_terminal_run() -> None:
    path = (
        runner.HSSD_PHASE2_ATTEMPT_ROOT
        / "scripts/compose_hssd_private_research_phase2_commandlet.py"
    )
    tree = runner.ast.parse(path.read_text(encoding="utf-8"))
    terminal = tree.body[-1]
    assert isinstance(terminal, runner.ast.Expr)
    assert isinstance(terminal.value, runner.ast.Call)
    assert isinstance(terminal.value.func, runner.ast.Name)
    assert terminal.value.func.id == "run"
    assert runner._script_sources()["upstream_phase2_commandlet"] == path.resolve()
    assert (
        runner._sha256(path)
        == runner.UPSTREAM_SCRIPT_PINS["upstream_phase2_commandlet"]
    )


def test_execution_manifest_sha_survives_later_contract_validation(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "hybrid-r3-execution.json"
    manifest.write_text('{"schema_version":"fixture"}', encoding="utf-8")
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    monkeypatch.setenv(runner.EXECUTION_ENV, str(manifest))
    monkeypatch.setenv(runner.EXECUTION_SHA_ENV, manifest_sha)

    path, observed_sha, execution = runner._load_execution_manifest_from_environment()

    assert path == manifest
    assert observed_sha == manifest_sha
    assert execution == {"schema_version": "fixture"}
    source = pathlib.Path(runner.__file__).read_text(encoding="utf-8")
    assert "expected_contract_sha" in source
    assert "str(manifest_path),\n        execution_manifest_sha," in source


def test_upstream_helper_loader_executes_only_allowlisted_definitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = runner._script_sources()["upstream_phase2_commandlet"]
    monkeypatch.setitem(sys.modules, "unreal", types.ModuleType("unreal"))
    path_before = tuple(sys.path)

    helpers = runner.load_upstream_commandlet_helpers(
        path, runner.UPSTREAM_SCRIPT_PINS["upstream_phase2_commandlet"]
    )

    assert tuple(sys.path) == path_before
    assert "run" not in helpers.__dict__
    assert callable(helpers.configure_visual_shell)
    assert callable(helpers.semantic_proxy_observation)


def test_upstream_helper_loader_rejects_extra_top_level_code(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = runner._script_sources()["upstream_phase2_commandlet"].read_text(
        encoding="utf-8"
    )
    tampered = source.replace(
        "\ndef require(condition, message):",
        "\nTOP_LEVEL_SIDE_EFFECT = object()\n\ndef require(condition, message):",
        1,
    )
    path = tmp_path / "compose_hssd_private_research_phase2_commandlet.py"
    path.write_text(tampered, encoding="utf-8")
    expected_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setitem(sys.modules, "unreal", types.ModuleType("unreal"))

    with pytest.raises(runner.RunnerError, match="non-helper top-level code"):
        runner.load_upstream_commandlet_helpers(path, expected_sha)


def test_all_upstream_phase2_dependencies_match_successful_r3_pins() -> None:
    scripts = runner._script_sources()

    runner._validate_upstream_scripts(scripts)

    assert set(runner.UPSTREAM_SCRIPT_PINS) == {
        "base",
        "compatibility",
        "hssd_common",
        "phase1_runner",
        "phase2_runner",
        "upstream_phase2_commandlet",
    }
    assert all(
        path.parent == runner.HSSD_PHASE2_ATTEMPT_ROOT / "scripts"
        for label, path in scripts.items()
        if label in runner.UPSTREAM_SCRIPT_PINS
    )


def test_policy_preserves_production_and_merges_only_hssd_namespace() -> None:
    assert runner.HYBRID_POLICY["source_candidate"] == (
        "accepted_production_r3_presentation_exact"
    )
    assert runner.HYBRID_POLICY["production_presentation_bundles_preserved"] == 3
    assert runner.HYBRID_POLICY["production_pbr_backed_placements_preserved"] == 45
    assert runner.HYBRID_POLICY["production_external_model_placements_preserved"] == 30
    assert (
        runner.HYBRID_POLICY["production_project_authored_pbr_placements_preserved"]
        == 15
    )
    assert runner.HYBRID_POLICY["production_external_asset_provider"] == "poly_haven"
    assert runner.HYBRID_POLICY["production_semantic_authority"] == (
        "hidden_r1_collision_authority_preserved"
    )
    assert runner.HYBRID_POLICY["production_semantic_collision_profile"] == "BlockAll"
    assert runner.HYBRID_POLICY["production_semantic_collision_mode"] == (
        "QueryAndPhysics"
    )
    assert runner.HYBRID_POLICY["production_semantic_collision_responses"] == {
        "Pawn": "Block",
        "Visibility": "Block",
    }
    assert runner.HYBRID_POLICY["hssd_namespace_merge"] == (
        "exact_sealed_namespace_only"
    )
    assert runner.HYBRID_POLICY["upstream_phase2_commandlet_reuse"] == (
        "exact_pinned_helper_definitions_terminal_run_replaced_for_30_room_slice"
    )
    assert runner.HYBRID_POLICY["live_runtime_mutation"] is False
