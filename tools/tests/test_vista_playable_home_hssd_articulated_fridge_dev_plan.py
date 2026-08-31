from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from ue.vista_playable_home import plan_hssd_articulated_fridge_dev as module


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (
    ROOT
    / "world_packs/vista_playable_home_r1/articulations/hssd_side_by_side_fridge_r1.json"
)
COMMANDLET = (
    ROOT / "tools/ue/vista_playable_home/compose_hssd_articulated_fridge_commandlet.py"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seal(value: dict) -> dict:
    result = copy.deepcopy(value)
    result["content_digest"] = module._content_digest(result)
    return result


def _legacy_scene(path: Path, *, duplicate_shell: bool = False) -> Path:
    transform = {
        "location_cm": [200.0, -120.0, 0.0],
        "rotation_deg": [0.0, 0.0, 180.0],
        "scale": [1.0, 1.0, 1.0],
    }
    shell = {
        "instance_id": module.INSTANCE_ID,
        "semantic_target_id": module.SEMANTIC_ID,
        "source_asset_id": "hssd.static.fridge",
        "object_path": "/Game/VISTA/HSSD/SM_Fridge.SM_Fridge",
        "actor_path": "/Game/VISTA/PlayableHome/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.VISTA_HSSD_R7_Fridge",
        "actor_label": "VISTA_HSSD_R7_Fridge",
        "actor_class_path": module.LEGACY_SHELL_CLASS,
        "actor_hidden_in_game": False,
        "actor_collision_enabled": False,
        "world_transform_cm": transform,
        "tags": sorted(
            [
                "VistaRole=hssd_visual_shell",
                "VistaHssdInstanceId=" + module.INSTANCE_ID,
                "VistaHssdSemanticTargetId=" + module.SEMANTIC_ID,
            ]
        ),
        "collision_profile": "NoCollision",
        "collision_enabled": False,
    }
    proxy = {
        "semantic_target_id": module.SEMANTIC_ID,
        "actor_path": "/Game/VISTA/PlayableHome/Maps/VistaPlayableHome.VistaPlayableHome:PersistentLevel.VISTA_Fridge_Proxy",
        "actor_label": "VISTA_Fridge_Proxy",
        "actor_class_path": module.LEGACY_PROXY_CLASS,
        "actor_hidden_in_game": True,
        "actor_collision_enabled": True,
        "world_transform_cm": transform,
        "tags": ["VistaSemanticId=" + module.SEMANTIC_ID],
        "components": [
            {
                "mesh_path": "/Engine/BasicShapes/Cube.Cube",
                "collision_profile": "Custom",
                "collision_mode": "QueryOnly",
                "collision_enabled": True,
                "simulate_physics": False,
                "visible": False,
            }
        ],
    }
    value = _seal(
        {
            "schema_version": "simworld.vista.playable-home-hssd-private-research-phase2-scene-receipt/v2",
            "accepted_as_ue_runtime": False,
            "diagnostic_only": True,
            "map_path": "/Game/VISTA/PlayableHome/Maps/VistaPlayableHome",
            "actors": [shell] * (2 if duplicate_shell else 1),
            "semantic_proxies": [
                {
                    "semantic_target_id": module.SEMANTIC_ID,
                    "reloaded": proxy,
                }
            ],
        }
    )
    path.write_bytes(module._canonical_json(value))
    return path


def _transport(attempt: Path) -> Path:
    root = attempt / "transport"
    assets = root / "assets"
    assets.mkdir(parents=True)
    outputs = []
    bounds = {
        "body": {"min_m": [-0.46, -0.35, 0.0], "max_m": [0.46, 0.35, 1.77]},
        "primary_door": {"min_m": [0.0, -0.06, -0.9], "max_m": [0.45, 0.02, 0.9]},
        "secondary_door": {"min_m": [-0.45, -0.06, -0.9], "max_m": [0.0, 0.02, 0.9]},
    }
    for role in module.OUTPUT_ROLES:
        path = assets / f"{role}.glb"
        path.write_bytes((role + "-core-png").encode())
        outputs.append(
            {
                "role": role,
                "derivative": {
                    "relative_path": "assets/" + path.name,
                    "sha256": _sha(path),
                    "size_bytes": path.stat().st_size,
                },
                "validation": {
                    "self_contained": True,
                    "single_mesh": True,
                    "embedded_png_images_valid": True,
                },
                "mesh_bounds": bounds[role],
            }
        )
    contract = json.loads(CONTRACT.read_text())
    receipt = _seal(
        {
            "schema_version": module.TRANSPORT_SCHEMA,
            "status": "transported_pending_ue_import_runtime_and_human_review",
            "accepted": False,
            "ue_imported": False,
            "contract": {
                "sha256": _sha(CONTRACT),
                "content_digest": contract["content_digest"],
            },
            "outputs": outputs,
        }
    )
    path = root / "articulated-fridge-transport-receipt.json"
    path.write_bytes(module._canonical_json(receipt))
    return path


def _fixture(tmp_path: Path) -> dict[str, Path]:
    attempt = (tmp_path / "dev-attempt").resolve()
    project_root = attempt / "project"
    base = project_root / "Content/VISTA/PlayableHome/Maps/VistaPlayableHome.umap"
    base.parent.mkdir(parents=True)
    base.write_bytes(b"base-map-r6-copy")
    project = project_root / "VistaFridgeDev.uproject"
    project.write_text("{}\n")
    legacy = _legacy_scene(tmp_path / "legacy-scene.json")
    transport = _transport(attempt)
    return {
        "attempt": attempt,
        "project": project,
        "base": base,
        "legacy": legacy,
        "transport": transport,
    }


def _plan(paths: dict[str, Path]) -> dict:
    return module.plan_execution(
        attempt_root=paths["attempt"],
        project_file=paths["project"],
        contract_path=CONTRACT,
        transport_receipt_path=paths["transport"],
        legacy_scene_receipt_path=paths["legacy"],
        derivative_map_path="/Game/VISTA/Dev/ArticulatedFridge/R1/Maps/VistaFridgeR1",
        content_namespace="/Game/VISTA/Dev/ArticulatedFridge/R1/Content",
        commandlet_path=COMMANDLET,
    )


def test_plan_seals_fresh_map_exact_legacy_identity_and_three_links(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    execution = _plan(paths)

    assert execution["mode"] == "dev_only_fresh_derivative"
    assert execution["policy"]["base_map_read_only"] is True
    assert execution["policy"]["launch_ue"] is False
    assert execution["base_map"]["package_sha256"] == _sha(paths["base"])
    assert execution["legacy"]["shell"]["instance_id"] == module.INSTANCE_ID
    assert execution["legacy"]["proxy"]["actor_class_path"] == module.LEGACY_PROXY_CLASS
    assert [item["role"] for item in execution["actor_binding"]["assets"]] == list(
        module.OUTPUT_ROLES
    )
    assert execution["actor_binding"]["actor_class_path"] == module.ACTOR_CLASS
    assert execution["actor_binding"]["semantic_id"] == module.SEMANTIC_ID
    assert execution["actor_binding"]["receptacle_count"] == 11
    assert execution["actor_binding"]["handle_relative_location_cm"] == pytest.approx(
        [43.2, -6.0, 0.0]
    )
    manifest = paths["attempt"] / module.EXECUTION_NAME
    assert manifest.read_bytes() == module._canonical_json(execution)
    assert (paths["attempt"] / "inputs/articulated-fridge-contract.json").is_file()
    assert (paths["attempt"] / "inputs/legacy-scene-receipt.json").is_file()
    assert not Path(execution["derivative_map"]["package_file"]).exists()


def test_duplicate_legacy_shell_fails_closed_before_input_copy(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    paths["legacy"] = _legacy_scene(
        tmp_path / "duplicate-scene.json", duplicate_shell=True
    )

    with pytest.raises(module.ArticulatedFridgePlanError, match="not unique"):
        _plan(paths)

    assert not (paths["attempt"] / "inputs").exists()
    assert not (paths["attempt"] / module.EXECUTION_NAME).exists()


def test_transport_hash_drift_fails_before_input_copy(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    (paths["attempt"] / "transport/assets/body.glb").write_bytes(b"changed")

    with pytest.raises(module.ArticulatedFridgePlanError, match="bytes differ"):
        _plan(paths)

    assert not (paths["attempt"] / "inputs").exists()


def test_non_dev_derivative_or_existing_map_is_refused(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    with pytest.raises(module.ArticulatedFridgePlanError, match="dev-only"):
        module.plan_execution(
            attempt_root=paths["attempt"],
            project_file=paths["project"],
            contract_path=CONTRACT,
            transport_receipt_path=paths["transport"],
            legacy_scene_receipt_path=paths["legacy"],
            derivative_map_path="/Game/VISTA/PlayableHome/Maps/VistaPlayableHome",
            content_namespace="/Game/VISTA/Dev/ArticulatedFridge/R1/Content",
            commandlet_path=COMMANDLET,
        )


def test_planner_contains_no_ue_launch_or_process_execution() -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "import unreal" not in source
    assert "subprocess" not in source
    assert "Popen" not in source
    assert 'launch_ue": False' in source
