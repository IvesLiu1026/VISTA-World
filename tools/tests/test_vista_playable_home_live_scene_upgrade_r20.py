from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.runtime.vista_playable_home import human_visual_demo_launch as live_tree
from tools.ue.vista_playable_home import build_home
from tools.ue.vista_playable_home import live_scene_upgrade_r20_contract as contract
from tools.ue.vista_playable_home import run_live_scene_upgrade_r20 as runner


ROOT = Path(__file__).resolve().parents[2]
PROFILE = (
    ROOT
    / "world_packs/vista_playable_home_r1/composition_profiles/"
    "vista_home_typed_scene_r18.json"
)
COMMANDLET = (
    ROOT
    / "tools/ue/vista_playable_home/"
    "compose_live_scene_upgrade_r20_commandlet.py"
)


def _write(path: Path, raw: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)


def _canonical(path: Path, value: dict) -> None:
    _write(path, runner.canonical_json(value))


def _artifact(path: Path) -> dict:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _tree(path: Path) -> dict:
    snapshot = build_home.snapshot_tree(path, "test tree")
    return {
        "root": str(path),
        "tree_sha256": snapshot.sha256,
        "file_count": snapshot.file_count,
        "total_bytes": snapshot.total_bytes,
    }


def _seal(value: dict) -> dict:
    return contract.seal_document(value)


def _receipt(
    path: Path,
    *,
    schema: str,
    status: str,
    inventory_key: str,
    inventory: list[dict],
    extra: dict | None = None,
) -> None:
    value = {
        "schema_version": schema,
        "status": status,
        "accepted": False,
        inventory_key: inventory,
        **(extra or {}),
    }
    _canonical(path, _seal(value))


def _fixture(tmp_path: Path) -> tuple[Path, str, Path]:
    run_parent = tmp_path / "runs"
    run_parent.mkdir()
    source = tmp_path / "r6" / "project"
    descriptor = source / contract.PROJECT_DESCRIPTOR_NAME
    _write(descriptor, b'{"FileVersion":3}\n')
    _write(source / "Config/DefaultEngine.ini", b"[SystemSettings]\n")
    map_path = source / contract.MAP_RELATIVE_PATH
    _write(map_path, b"sealed-r6-map")
    _write(source / "Content/Characters/Dummy.uasset", b"character")
    _write(source / "Plugins/VistaPlayableHome/old.bin", b"old-plugin")
    static = live_tree.compute_project_static_tree(descriptor)
    manifest_path = source.parent / "human-fit-live-nonpromotable-manifest.json"
    manifest = {
        "project": {
            "descriptor": {
                **_artifact(descriptor),
            },
            "map_package": {
                **_artifact(map_path),
            },
            "static_tree": {
                **static,
                "verified_twice_identical": True,
            },
        },
        "legal_scope": {
            "human_operated_visual_demo_only": True,
            "external_assets_outside_git": True,
        },
        "claims": {"gta_quality_claim": False, "photoreal_claim": False},
    }
    _write(manifest_path, json.dumps(manifest, indent=2).encode() + b"\n")

    plugin = tmp_path / "plugin"
    _write(plugin / "VistaPlayableHome.uplugin", b'{"FriendlyName":"VISTA"}\n')
    _write(plugin / "Binaries/Linux/libUnrealEditor-VistaPlayableHome.so", b"runtime")
    _write(
        plugin / "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so",
        b"editor",
    )
    _write(plugin / "Binaries/Linux/UnrealEditor.modules", b"{}\n")

    receipt_specs = {
        "r8": (
            "vista.makehuman-cc0-ue57-animation-runtime-receipt/v1",
            "cc0_animation_runtime_assets_saved_reloaded_pending_runtime",
            "package_inventory",
            "/Game/VISTA/MakeHumanCC0/R8/Animations/Sequences/TestR8.TestR8",
            "/Script/Engine.AnimSequence",
        ),
        "r14": (
            "vista.makehuman-cc0-r14-ue57-import-receipt/v1",
            "r14_detail_actions_saved_reloaded_pending_runtime_review",
            "asset_inventory",
            "/Game/VISTA/MakeHumanCC0/R14/DetailActions/Sequences/TestR14.TestR14",
            "/Script/Engine.AnimSequence",
        ),
        "r15": (
            "vista.makehuman-cc0-r15-ue57-import-receipt/v1",
            "r15_detail_actions_saved_reloaded_pending_runtime_review",
            "asset_inventory",
            "/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/TestR15.TestR15",
            "/Script/Engine.AnimMontage",
        ),
        "manny_r18": (
            "vista.manny-detail-actions-retarget-r18-host-receipt/v1",
            "manny_r18_detail_actions_retargeted_cold_verified_external_only",
            "package_inventory",
            "/Game/VISTA/Manny/R18/DetailActions/Montages/TestR18.TestR18",
            "/Script/Engine.AnimMontage",
        ),
    }
    overlays = {}
    for role, (schema, status, key, object_path, class_path) in receipt_specs.items():
        root = tmp_path / "overlays" / role
        namespace = contract.OVERLAY_NAMESPACES[role]
        relative = object_path.split(".", 1)[0].removeprefix(namespace + "/")
        _write(root / (relative + ".uasset"), role.encode())
        receipt = tmp_path / "receipts" / (role + ".json")
        _receipt(
            receipt,
            schema=schema,
            status=status,
            inventory_key=key,
            inventory=[{"object_path": object_path, "class_path": class_path}],
        )
        overlays[role] = {"tree": _tree(root), "receipt": _artifact(receipt)}

    fridge_root = tmp_path / "overlays/fridge"
    fridge_inventory = []
    for role, filename in (
        ("body", "SM_HssdFridgeBody"),
        ("primary_door", "SM_HssdFridgePrimaryDoor"),
        ("secondary_door", "SM_HssdFridgeSecondaryDoor"),
    ):
        object_path = contract.OVERLAY_NAMESPACES["fridge"] + f"/{filename}.{filename}"
        _write(fridge_root / (filename + ".uasset"), role.encode())
        fridge_inventory.append(
            {
                "role": role,
                "object_path": object_path,
                "class_path": "/Script/Engine.StaticMesh",
            }
        )
    fridge_evidence = tmp_path / "fridge-evidence"
    fridge_receipt = fridge_evidence / "articulated-fridge-scene-receipt.json"
    _receipt(
        fridge_receipt,
        schema="vista.playable-articulated-fridge-dev-scene-receipt/v1",
        status="dev_derivative_composed_pending_runtime_and_human_review",
        inventory_key="imported_assets",
        inventory=fridge_inventory,
        extra={
            "gates": {"map_saved": True, "map_cold_reloaded": True},
            "articulated_actor": {"semantic_id": contract.FRIDGE_ID},
        },
    )
    fridge_execution = fridge_evidence / "articulated-fridge-execution.json"
    _canonical(
        fridge_execution,
        _seal(
            {
                "schema_version": "vista.playable-articulated-fridge-dev-execution/v1",
                "legacy": {"proxy": {"id": "proxy"}, "shell": {"id": "shell"}},
            }
        ),
    )
    overlays["fridge"] = {
        "tree": _tree(fridge_root),
        "receipt": _artifact(fridge_receipt),
        "execution": _artifact(fridge_execution),
    }

    fake_ue = tmp_path / "toolchain/Engine/Binaries/Linux/UnrealEditor-Cmd"
    fake_bwrap = tmp_path / "toolchain/bwrap"
    _write(fake_ue, b"#!/bin/sh\nexit 0\n", 0o700)
    _write(fake_bwrap, b"#!/bin/sh\nexit 0\n", 0o700)
    bindings = _seal(
        {
            "schema_version": runner.BINDING_SCHEMA,
            "run_parent": str(run_parent),
            "source_project": {
                "static_tree": {"root": str(source), **static},
                "descriptor": _artifact(descriptor),
                "map": _artifact(map_path),
                "manifest": _artifact(manifest_path),
            },
            "compiled_plugin": _tree(plugin),
            "typed_profile": _artifact(PROFILE),
            "overlays": overlays,
            "toolchain": {
                "unreal_editor_cmd": _artifact(fake_ue),
                "bwrap": _artifact(fake_bwrap),
            },
        }
    )
    binding_path = tmp_path / "r20-input-bindings.json"
    _canonical(binding_path, bindings)
    return binding_path, _artifact(binding_path)["sha256"], run_parent


def _file_projection(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_checked_in_typed_profile_is_exact_and_unaccepted() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    observed = contract.validate_typed_profile(profile)

    assert observed["content_digest"] == contract.TYPED_PROFILE_CONTENT_DIGEST
    assert observed["runtime_acceptance"] is False
    assert contract.expected_typed_ids() == (
        *contract.SEAT_IDS,
        *contract.LIQUID_IDS,
        contract.FRIDGE_ID,
        *contract.expected_anchor_ids(),
    )
    assert contract.YCB_MESH_BINDINGS[contract.WATER_JUG_ID][
        "visual_proxy_accepted"
    ] is False


def test_dry_run_validates_every_pin_without_writing(tmp_path: Path) -> None:
    binding, digest, run_parent = _fixture(tmp_path)
    before = _file_projection(tmp_path)

    plan = runner.build_plan(
        "live-scene-upgrade-r20-test-a", binding, digest
    )

    assert plan.report["status"] == contract.DRY_RUN_STATUS
    assert plan.report["planned_mutations"] == {
        "source_r6": False,
        "live_services": False,
        "gpu_or_renderer": False,
        "attempt_created": False,
        "fresh_project_created": False,
    }
    assert not (run_parent / "live-scene-upgrade-r20-test-a").exists()
    assert _file_projection(tmp_path) == before
    assert set(plan.report["overlays"]) == set(contract.OVERLAY_DESTINATIONS)
    assert "execution" in plan.report["overlays"]["fridge"]


def test_bwrap_creates_private_mountpoints_before_binding(tmp_path: Path) -> None:
    binding, digest, _ = _fixture(tmp_path)
    plan = runner.build_plan("live-scene-upgrade-r20-bwrap", binding, digest)
    command = runner._bwrap_command(plan, "0" * 64, contract.AUTHOR_MODE)

    tmpfs_index = next(
        index
        for index in range(len(command) - 1)
        if command[index : index + 2] == ["--tmpfs", "/vista"]
    )
    dev_bind_index = next(
        index
        for index in range(len(command) - 2)
        if command[index : index + 3] == ["--dev-bind", "/", "/"]
    )
    assert dev_bind_index < tmpfs_index
    for destination, bind_flag in (
        ("/vista/engine", "--ro-bind"),
        ("/vista/repository", "--ro-bind"),
        ("/vista/source-r6", "--ro-bind"),
        ("/vista/work", "--bind"),
    ):
        directory_index = next(
            index
            for index in range(len(command) - 1)
            if command[index : index + 2] == ["--dir", destination]
        )
        bind_index = next(
            index
            for index in range(len(command) - 2)
            if command[index] == bind_flag and command[index + 2] == destination
        )
        assert tmpfs_index < directory_index < bind_index


def test_pin_drift_and_missing_fridge_execution_fail_closed(tmp_path: Path) -> None:
    binding, digest, _ = _fixture(tmp_path)
    with pytest.raises(runner.RunnerError, match="bindings pin differs"):
        runner.build_plan(
            "live-scene-upgrade-r20-test-b", binding, "0" * 64
        )

    value = json.loads(binding.read_text(encoding="utf-8"))
    value["overlays"]["fridge"].pop("execution")
    value = _seal(value)
    _canonical(binding, value)
    new_digest = _artifact(binding)["sha256"]
    with pytest.raises(runner.RunnerError, match="fridge overlay fields differ"):
        runner.build_plan(
            "live-scene-upgrade-r20-test-c", binding, new_digest
        )


def test_commandlet_source_contains_action_critical_fail_closed_operations() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")

    assert "author_seats" in source
    assert "VistaAffordance.SIT" in source
    assert "VistaAffordance.STAND" in source
    assert 'suffix, key in (' in source
    assert "author_liquids" in source
    assert "VistaAffordance.POUR" in source
    assert "VistaVisualProxyUnaccepted=true" in source
    assert "author_fridge" in source
    assert "destroy_actor(proxy)" in source
    assert "destroy_actor(shell)" in source
    assert "VistaHssdLegacyShellLineagePreserved=true" in source
    assert "old_authorities_absent" in source
    assert "duplicate_semantic_ids_absent" in source
    assert "EditorLoadingAndSavingUtils.save_map" in source
    assert "load_author_lineage" in source
    assert "run()" in source


def test_profile_digest_mutation_is_rejected() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    changed = copy.deepcopy(profile)
    changed["seat_bindings"][0]["interaction_target_local_cm"]["location_cm"] = [
        1,
        2,
        3,
    ]
    with pytest.raises(contract.ContractError, match="identity or digest"):
        contract.validate_typed_profile(changed)
