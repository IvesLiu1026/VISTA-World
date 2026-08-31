from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from ue.vista_playable_home import plan_hssd_portable_visual_binding_dev as module


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (
    ROOT / "world_packs/vista_playable_home_r1/visual_bindings/"
    "hssd_portable_pickups_r1.json"
)
COMMANDLET = (
    ROOT / "tools/ue/vista_playable_home/"
    "compose_hssd_portable_visual_binding_commandlet.py"
)
SOURCE_OBJECT_PATH = "/Game/VISTA/Dev/ArticulatedFridge/R1/Maps/VistaFridgeR1"
DERIVATIVE_OBJECT_PATH = (
    "/Game/VISTA/Dev/PortableVisualBindings/R1/Maps/VistaPortableHssdR1"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seal(value: dict) -> dict:
    result = copy.deepcopy(value)
    result["content_digest"] = module._content_digest(result)
    return result


def _fixture(tmp_path: Path, *, source_gate=True) -> dict[str, Path]:
    attempt = (tmp_path / "portable-dev-attempt").resolve()
    project_root = attempt / "project"
    project_root.mkdir(parents=True)
    project = project_root / "VistaPortableBindingsDev.uproject"
    project.write_text("{}\n", encoding="utf-8")
    source_map = module._map_package_file(project, SOURCE_OBJECT_PATH)
    source_map.parent.mkdir(parents=True)
    source_map.write_bytes(b"completed-articulated-fridge-source-map")
    receipt = _seal(
        {
            "schema_version": module.SOURCE_RECEIPT_SCHEMA,
            "status": module.SOURCE_SUCCESS_STATUS,
            "error": None,
            "accepted": False,
            "ue_imported": True,
            "runtime_verified": False,
            "human_reviewed": False,
            "promotable": False,
            "diagnostic_only": True,
            "base_map": {"unchanged": True},
            "derivative_map": {
                "object_path": SOURCE_OBJECT_PATH,
                "package_file": "/previous/attempt/project/source.umap",
                "package_sha256": _sha(source_map),
                "package_size_bytes": source_map.stat().st_size,
            },
            "gates": {
                "exact_legacy_shell_and_proxy_validated_before_delete": source_gate,
                "legacy_shell_and_proxy_removed_only_in_derivative": True,
                "fresh_derivative_map_created": True,
                "base_map_package_unchanged": True,
                "map_saved": True,
                "map_cold_reloaded": True,
                "one_visible_semantic_authority": True,
                "quarantined": False,
            },
            "claims": {
                "r6_touched": False,
                "production_promoted": False,
                "ue_runtime_launched": False,
            },
        }
    )
    receipt_path = (tmp_path / "articulated-fridge-scene-receipt.json").resolve()
    receipt_path.write_bytes(module._canonical_json(receipt))
    return {
        "attempt": attempt,
        "project": project,
        "source_map": source_map,
        "receipt": receipt_path,
    }


def _plan(paths: dict[str, Path]) -> dict:
    return module.plan_execution(
        attempt_root=paths["attempt"],
        project_file=paths["project"],
        source_fridge_scene_receipt_path=paths["receipt"],
        derivative_map_path=DERIVATIVE_OBJECT_PATH,
        contract_path=CONTRACT,
        commandlet_path=COMMANDLET,
    )


def test_plan_seals_completed_fridge_source_and_two_closed_bindings(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    execution = _plan(paths)

    assert execution["mode"] == "dev_only_fresh_derivative_from_completed_fridge"
    assert execution["source_map"]["package_sha256"] == _sha(paths["source_map"])
    assert execution["policy"]["source_map_read_only"] is True
    assert execution["policy"]["new_level_from_template_required"] is True
    assert execution["policy"]["asset_import_or_replacement_forbidden"] is True
    assert execution["policy"]["declared_absent_shell_must_be_proved"] is True
    assert execution["policy"]["exact_one_visual_shell_may_be_deleted"] is True
    assert execution["policy"]["launch_ue"] is False
    assert [row["semantic_id"] for row in execution["bindings"]] == list(
        module.binding_contract.EXPECTED_SEMANTIC_IDS
    )
    assert tuple(row["shell_disposition"] for row in execution["bindings"]) == (
        module.binding_contract.ABSENT_SHELL_DISPOSITION,
        module.binding_contract.DELETE_SHELL_DISPOSITION,
    )
    assert (
        paths["attempt"] / "inputs/hssd-portable-visual-binding-contract.json"
    ).is_file()
    assert (
        paths["attempt"] / "inputs/source-articulated-fridge-scene-receipt.json"
    ).is_file()
    manifest = paths["attempt"] / module.EXECUTION_NAME
    assert manifest.read_bytes() == module._canonical_json(execution)
    assert not Path(execution["derivative_map"]["package_file"]).exists()


def test_incomplete_fridge_receipt_fails_before_any_input_copy(tmp_path: Path) -> None:
    paths = _fixture(tmp_path, source_gate=False)
    with pytest.raises(module.PortableVisualBindingPlanError, match="gates"):
        _plan(paths)
    assert not (paths["attempt"] / "inputs").exists()


def test_copied_source_map_hash_drift_fails_before_input_copy(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    paths["source_map"].write_bytes(b"drift")
    with pytest.raises(module.PortableVisualBindingPlanError, match="bytes differ"):
        _plan(paths)
    assert not (paths["attempt"] / "inputs").exists()


def test_existing_or_non_dev_derivative_fails_closed(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    with pytest.raises(module.PortableVisualBindingPlanError, match="fresh"):
        module.plan_execution(
            attempt_root=paths["attempt"],
            project_file=paths["project"],
            source_fridge_scene_receipt_path=paths["receipt"],
            derivative_map_path=SOURCE_OBJECT_PATH,
            contract_path=CONTRACT,
            commandlet_path=COMMANDLET,
        )
    assert not (paths["attempt"] / "inputs").exists()


def test_planner_contains_no_ue_launch_or_process_execution() -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "import unreal" not in source
    assert "subprocess" not in source
    assert "Popen" not in source
    assert '"launch_ue": False' in source
