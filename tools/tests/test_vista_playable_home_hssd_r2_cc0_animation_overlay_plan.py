from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

from tools.admin import vista_r8_buildplugin_authority as buildplugin_authority
from tools.ue.vista_playable_home import (
    makehuman_cc0_animation_runtime_executor as executor,
)
from tools.ue.vista_playable_home import (
    plan_hssd_r2_cc0_animation_overlay as planner,
)


ATTEMPT = "hssd-r2-cc0-animation-overlay-r1-unit"


@dataclasses.dataclass(frozen=True)
class Fixture:
    config: planner.Config
    parent_documents: dict[str, dict[str, Any]]
    r3_receipt: dict[str, Any]


def _write(path: Path, raw: bytes, mode: int = 0o600) -> planner.PinnedFile:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.chmod(0o600)
    path.write_bytes(raw)
    path.chmod(mode)
    return planner.PinnedFile(
        path,
        planner.FilePin(hashlib.sha256(raw).hexdigest(), len(raw), mode),
    )


def _write_document(
    path: Path,
    document: dict[str, Any],
    *,
    mode: int = 0o600,
    trailing_newline: bool = True,
) -> tuple[dict[str, Any], planner.PinnedFile]:
    value = dict(document)
    value["content_digest"] = planner.content_digest(
        value, trailing_newline=trailing_newline
    )
    raw = planner.canonical_json(value)
    if not trailing_newline:
        raw = raw.removesuffix(b"\n")
    return value, _write(path, raw, mode)


def _package_row(
    root: Path,
    relative: str,
    class_path: str,
    *,
    mode: int,
) -> dict[str, Any]:
    raw = ("payload:" + relative).encode()
    _write(root / relative, raw, mode)
    package_name = "/Game/" + relative.removeprefix("Content/").removesuffix(".uasset")
    return {
        "class_path": class_path,
        "object_path": package_name + "." + Path(package_name).name,
        "package_name": package_name,
        "project_relative_path": relative,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _r3_class(index: int) -> str:
    if index == 0:
        return "/Script/Engine.SkeletalMesh"
    if index == 1:
        return "/Script/Engine.PhysicsAsset"
    if index == 2:
        return "/Script/Engine.Skeleton"
    if index < 12:
        return "/Script/Engine.Material"
    return "/Script/Engine.Texture2D"


def _r8_class(relative: str) -> str:
    name = Path(relative).name
    if name.startswith("ABP_"):
        return "/Script/Engine.AnimBlueprint"
    if name.startswith("BS_"):
        return "/Script/Engine.BlendSpace1D"
    if name.startswith("AM_"):
        return "/Script/Engine.AnimMontage"
    return "/Script/Engine.AnimSequence"


def _sequence_inspection() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in executor.CLIP_SPECS:
        frame_count = spec["frame_end"] - spec["frame_start"]
        sequence_name = spec["sequence_name"]
        rows.append(
            {
                "object_path": (
                    f"{executor.CONTENT_NAMESPACE}/Sequences/{sequence_name}."
                    f"{sequence_name}"
                ),
                "skeleton": executor.SKELETON_OBJECT_PATH,
                "sample_rate": {"numerator": 30, "denominator": 1},
                "frame_count": frame_count,
                "bone_track_names": sorted(executor.BONE_NAMES),
                "play_length_seconds": frame_count / 30.0,
                "loop_contract": spec["loop"],
                "root_motion_enabled": False,
                "force_root_lock": True,
                "root_motion_lock_type": "REF_POSE",
                "inspection_phase": "cold_reload_postcondition",
                "root_start_translation": [0.0, 0.0, 0.0],
                "root_end_translation": [0.0, 0.0, 0.0],
                "root_start_rotation": [0.0, 0.0, 0.0, 1.0],
                "root_end_rotation": [0.0, 0.0, 0.0, 1.0],
                "maximum_root_translation_delta": 0.0,
                "maximum_root_scale_delta": 0.0,
                "maximum_root_rotation_delta": 0.0,
                "root_delta_verified_zero": True,
            }
        )
    return rows


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


def _fixture(tmp_path: Path) -> Fixture:
    run_parent = tmp_path / "runs"
    run_parent.mkdir(parents=True)
    h_root = run_parent / "hssd-r2-citysample-live-r5-unit"
    project_root = h_root / "project"
    vista_root = project_root / "Content/VISTA"
    vista_root.mkdir(parents=True)
    (project_root / planner.PLUGIN_TARGET).mkdir(parents=True)
    project_pin = _write(
        project_root / planner.PROJECT_DESCRIPTOR_NAME,
        b'{"FileVersion":3}\n',
    )
    map_pin = _write(project_root / planner.MAP_RELATIVE_PATH, b"sealed-map")
    tree = planner.TreeProjection("a" * 64, 12, None, 3456)
    tree_mapping = {
        "algorithm": "sha256-path-nul-mode-size-content-v1",
        "file_count": tree.file_count,
        "total_bytes": tree.total_bytes,
        "tree_sha256": tree.sha256,
    }
    project_mapping = {
        "path": str(project_pin.path),
        "sha256": project_pin.pin.sha256,
        "size_bytes": project_pin.pin.size_bytes,
    }
    map_file_mapping = {
        "path": str(map_pin.path),
        "sha256": map_pin.pin.sha256,
        "size_bytes": map_pin.pin.size_bytes,
    }
    map_mapping = {
        "object_path": planner.MAP_OBJECT_PATH,
        "package": map_file_mapping,
    }
    combined, combined_pin = _write_document(
        h_root / "human-visual-demo-combined-receipt.json",
        {
            "schema_version": planner.H_COMBINED_SCHEMA,
            "status": planner.H_COMBINED_STATUS,
            "claims": planner.PARENT_CLAIMS,
            "executable": {"path": "private-demo"},
            "hssd_r2_citysample_live_r1_upgrade": {"status": "sealed"},
            "human_operated_visual_demo_only": True,
            "legal_scope": planner.LEGAL_SCOPE,
            "map": map_mapping,
            "prohibited_agent_adapter": True,
            "project": project_mapping,
            "project_static_tree": tree_mapping,
            "provider_id": planner.SOURCE_PROVIDER,
            "source_provenance": {"fixture": "unit"},
        },
    )
    current_map = map_file_mapping
    host, host_pin = _write_document(
        h_root / "hssd-r2-citysample-live-host-receipt.json",
        {
            "schema_version": planner.H_HOST_SCHEMA,
            "status": planner.H_HOST_STATUS,
            "acceptance": {"runtime_play_proof": "pending"},
            "claims": planner.PARENT_CLAIMS,
            "containment": {"network": "private"},
            "current_byte_revalidation": {
                "passed": True,
                "project_static_tree": tree_mapping,
                "map": current_map,
            },
            "execution": {"sha256": "1" * 64},
            "fixture_evidence_manifest": {"content_digest": "2" * 64},
            "gates": {"nullrhi_no_gpu": True},
            "human_operated_visual_demo_only": True,
            "legal_scope": planner.LEGAL_SCOPE,
            "log_closure": {"closed": True},
            "logs": [],
            "map": map_mapping,
            "prohibited_agent_adapter": True,
            "project": project_mapping,
            "project_static_tree": tree_mapping,
            "provider_id": planner.SOURCE_PROVIDER,
            "result": {"sha256": "3" * 64},
            "scene_receipt": {"sha256": "4" * 64},
            "static_delta": {"changed_file_count": 10},
        },
    )
    complete, complete_pin = _write_document(
        h_root / "hssd-r2-citysample-live-host-complete.json",
        {
            "schema_version": planner.H_COMPLETE_SCHEMA,
            "status": planner.H_COMPLETE_STATUS,
            "attempt_root": str(h_root),
            "combined_receipt": planner._receipt_file_mapping(combined_pin),
            "combined_receipt_sidecar": {"path": "combined.sha256"},
            "current_state": {
                "project_static_tree": tree_mapping,
                "map": current_map,
            },
            "failure_absent": True,
            "host_receipt": planner._receipt_file_mapping(host_pin),
        },
    )

    r3_root = run_parent / "makehuman-cc0-ue-import-r3-unit"
    r3_project = r3_root / "project"
    _write(r3_project / "VistaMakeHumanCC0Import.uproject", b"{}\n")
    r3_rows = [
        _package_row(r3_project, relative, _r3_class(index), mode=0o600)
        for index, relative in enumerate(planner.R3_PACKAGE_PATHS)
    ]
    r3_tree = planner.TreeProjection("b" * 64, 24, 11, 43_545_997)
    r3_document, r3_pin = _write_document(
        r3_root / "makehuman-cc0-import-host-receipt.json",
        {
            "schema_version": planner.R3_SCHEMA,
            "status": planner.R3_STATUS,
            "accepted": False,
            "attempt_root": str(r3_root),
            "project_root": str(r3_project),
            "claims": planner.R3_CLAIMS,
            "execution_manifest": {"sha256": "5" * 64},
            "import_receipt": {"sha256": "6" * 64},
            "logs": {},
            "output_project_projection": {
                "sha256": r3_tree.sha256,
                "file_count": r3_tree.file_count,
                "directory_count": r3_tree.directory_count,
                "total_bytes": r3_tree.total_bytes,
            },
            "package_inventory": r3_rows,
            "source": {"character_id": "unit"},
        },
        trailing_newline=False,
    )
    r8_parent = tmp_path / "published"
    r8_parent.mkdir()
    buildplugin_root = tmp_path / "authorities/buildplugin"
    config = planner.Config(
        run_parent=run_parent,
        parent=planner.ParentContract(
            root=h_root,
            complete=complete_pin,
            combined=combined_pin,
            host=host_pin,
            project=project_pin,
            map_package=map_pin,
            failure_marker=h_root / "hssd-r2-citysample-live-host-failure.json",
            tree=tree,
        ),
        r3=planner.R3Contract(
            attempt_root=r3_root,
            project_root=r3_project,
            receipt=r3_pin,
            project_tree=r3_tree,
            inventory_digest=planner._inventory_digest(r3_rows),
            package_paths=planner.R3_PACKAGE_PATHS,
            package_mode=0o600,
        ),
        r8_published_parent=r8_parent,
        r8_authority=None,
        buildplugin=planner.BuildPluginContract(
            root=buildplugin_root,
            source_path=tmp_path / "reviewed-buildplugin-source",
            projection_sha256="c" * 64,
            inventory_sha256="d" * 64,
            file_count=2,
            directory_count=2,
            total_bytes=20,
            critical_files={},
        ),
        buildplugin_authority=None,
        require_root_owned_future_authorities=False,
    )
    return Fixture(
        config=config,
        parent_documents={
            "complete": complete,
            "combined": combined,
            "host": host,
        },
        r3_receipt=r3_document,
    )


def _with_r8(fixture: Fixture) -> planner.Config:
    config = fixture.config
    root = config.r8_published_parent / "makehuman-cc0-animation-ue57-r1-unit"
    for relative in planner.R3_PACKAGE_PATHS:
        _write(
            root / "project" / relative,
            (config.r3.project_root / relative).read_bytes(),
            0o444,
        )
    rows = [
        _package_row(root / "project", relative, _r8_class(relative), mode=0o444)
        for relative in planner.R8_PACKAGE_PATHS
    ]
    runtime_bindings = {
        "engine": executor.EXPECTED_ENGINE_VERSION,
        "project": str(executor.SANDBOX_PROJECT_FILE),
        "execution_manifest": str(executor.SANDBOX_EXECUTION_PATH),
        "execution_manifest_sha256": "1" * 64,
        "source_host_receipt": {
            "path": str(executor.SANDBOX_SOURCE_RECEIPT_PATH),
            "sha256": "2" * 64,
            "size_bytes": 100,
        },
        "source_fbx": [
            {
                "clip_id": spec["clip_id"],
                "path": str(executor.SANDBOX_FBX_ROOT / f"{spec['sequence_name']}.fbx"),
                "sha256": f"{index + 3:x}" * 64,
                "size_bytes": index + 10,
            }
            for index, spec in enumerate(executor.CLIP_SPECS)
        ],
        "commandlet": {
            "path": str(executor.SANDBOX_COMMANDLET_PATH),
            "sha256": "8" * 64,
            "size_bytes": 200,
        },
        "skeleton_object_path": executor.SKELETON_OBJECT_PATH,
        "mesh_object_path": executor.MESH_OBJECT_PATH,
    }
    runtime, runtime_pin = _write_document(
        root / "evidence/makehuman-cc0-animation-runtime-receipt.json",
        {
            "schema_version": planner.R8_RUNTIME_SCHEMA,
            "status": planner.R8_RUNTIME_STATUS,
            "accepted": False,
            "error": None,
            "attempt_root": str(executor.SANDBOX_WORK_ROOT),
            "project_root": str(executor.SANDBOX_PROJECT_ROOT),
            "content_namespace": executor.CONTENT_NAMESPACE,
            "bindings": runtime_bindings,
            "returned_object_paths": list(executor.EXPECTED_RETURNED_OBJECT_PATHS),
            "pipeline_policies": [
                executor._pipeline_policy(spec["sequence_name"])
                for spec in executor.CLIP_SPECS
            ],
            "sequence_inspection": _sequence_inspection(),
            "runtime_authoring_result": executor.EXPECTED_RUNTIME_AUTHORING_RESULT,
            "asset_inventory": sorted(
                executor.EXPECTED_INVENTORY, key=lambda item: item["object_path"]
            ),
            "package_inventory": rows,
            "project_content_delta": planner._expected_r8_content_delta(
                fixture.r3_receipt["package_inventory"], rows
            ),
            "gates": executor.TERMINAL_GATE_EXPECTATIONS,
            "claims": executor.TERMINAL_CLAIMS,
        },
        mode=0o444,
    )
    host_bindings = {
        "root_policy_content_digest": "9" * 64,
        "launch_plan_content_digest": "a" * 64,
        "host_execution_content_digest": "b" * 64,
        "commandlet_execution_content_digest": "c" * 64,
        "engine_manifest_content_digest": "d" * 64,
        "engine_tree_digest": "e" * 64,
        "engine_build_id": "123456",
        "host_runtime_tree_digest": "f" * 64,
        "r3_project_tree_digest": config.r3.project_tree.sha256,
        "r8_host_receipt_sha256": runtime_bindings["source_host_receipt"]["sha256"],
        "buildplugin_tree_digest": config.buildplugin.projection_sha256,
        "sandbox_archive_sha256": "2" * 64,
        "commandlet_receipt_content_digest": runtime["content_digest"],
        "commandlet_result_receipt_sha256": runtime_pin.pin.sha256,
    }
    expected_project_counts = planner._expected_r8_project_counts(config, rows)
    host, host_pin = _write_document(
        root / "host-receipt.json",
        {
            "schema": planner.R8_HOST_SCHEMA,
            "status": planner.R8_HOST_STATUS,
            "accepted": False,
            "attempt_name": root.name,
            "bindings": host_bindings,
            "project_projection": {
                "sha256": "4" * 64,
                **expected_project_counts,
            },
            "added_project_relative_paths": list(planner.R8_PACKAGE_PATHS),
            "claims": {
                "ue_animation_imported": True,
                "typed_notifies_authored_in_ue": True,
                "runtime_assets_authored": True,
                **executor.NEGATIVE_CLAIMS,
            },
        },
        mode=0o444,
    )
    assert host["content_digest"]
    return dataclasses.replace(
        config,
        r8_authority=planner.R8Authority(
            root=root,
            host_receipt=host_pin,
            runtime_receipt=runtime_pin,
        ),
    )


def _with_buildplugin(config: planner.Config) -> planner.Config:
    root = config.buildplugin.root
    payload = root / "payload"
    file_a = _write(payload / "VistaPlayableHome.uplugin", b"plugin", 0o444)
    file_b = _write(payload / "Binaries/Linux/module.so", b"module", 0o444)
    (payload / "Binaries/Linux").chmod(0o555)
    (payload / "Binaries").chmod(0o555)
    payload.chmod(0o555)
    records: list[dict[str, Any]] = [
        {"kind": "directory", "path": ".", "source_mode": "0o755"},
        {"kind": "directory", "path": "Binaries", "source_mode": "0o755"},
        {
            "kind": "directory",
            "path": "Binaries/Linux",
            "source_mode": "0o755",
        },
        {
            "kind": "file",
            "path": "Binaries/Linux/module.so",
            "source_mode": "0o755",
            "size_bytes": file_b.pin.size_bytes,
            "sha256": file_b.pin.sha256,
        },
        {
            "kind": "file",
            "path": "VistaPlayableHome.uplugin",
            "source_mode": "0o644",
            "size_bytes": file_a.pin.size_bytes,
            "sha256": file_a.pin.sha256,
        },
    ]
    projection = planner._plugin_projection(records)
    inventory = hashlib.sha256(planner.canonical_json(records)).hexdigest()
    contract = planner.BuildPluginContract(
        root=root,
        source_path=config.buildplugin.source_path,
        projection_sha256=projection,
        inventory_sha256=inventory,
        file_count=2,
        directory_count=3,
        total_bytes=file_a.pin.size_bytes + file_b.pin.size_bytes,
        critical_files={
            "VistaPlayableHome.uplugin": planner.FilePin(
                file_a.pin.sha256, file_a.pin.size_bytes, 0o644
            ),
            "Binaries/Linux/module.so": planner.FilePin(
                file_b.pin.sha256, file_b.pin.size_bytes, 0o755
            ),
        },
    )
    source = {
        "path": str(contract.source_path),
        "projection_sha256": projection,
        "inventory_sha256": inventory,
        "file_count": 2,
        "directory_count": 3,
        "total_bytes": contract.total_bytes,
    }
    entries = [
        {
            **record,
            "authority_mode": "0555" if record["kind"] == "directory" else "0444",
        }
        for record in records
    ]
    manifest = {
        "schema_version": planner.BUILDPLUGIN_MANIFEST_SCHEMA,
        "source": source,
        "authority": {
            "root": str(root),
            "payload": str(payload),
            "directory_mode": "0555",
            "file_mode": "0444",
        },
        "critical_files": planner._critical_public(contract),
        "entries": entries,
    }
    manifest_pin = _write(
        root / "manifest.json", planner.canonical_json(manifest), 0o444
    )
    _, receipt_pin = _write_document(
        root / "receipt.json",
        {
            "schema_version": planner.BUILDPLUGIN_RECEIPT_SCHEMA,
            "status": planner.BUILDPLUGIN_RECEIPT_STATUS,
            "accepted": True,
            "source": source,
            "authority": {
                "root": str(root),
                "payload": str(payload),
                "payload_projection_sha256": projection,
                "manifest": {
                    "path": "manifest.json",
                    "sha256": manifest_pin.pin.sha256,
                    "size_bytes": manifest_pin.pin.size_bytes,
                },
                "root_owned_nonwritable": True,
            },
            "publisher": {
                "helper": {
                    "path": str(planner.BUILDPLUGIN_HELPER_PATH),
                    "mode": "0500",
                    "sha256": planner.BUILDPLUGIN_HELPER_SHA256,
                    "size_bytes": planner.BUILDPLUGIN_HELPER_SIZE_BYTES,
                },
                "interpreter": planner.BUILDPLUGIN_INTERPRETER,
            },
            "admin_publication": {
                "authority_root": str(planner.BUILDPLUGIN_ADMIN_AUTHORITY_ROOT),
                "authority_mode": "0555",
                "launcher": {
                    "name": planner.BUILDPLUGIN_ADMIN_LAUNCHER.name,
                    "path": str(planner.BUILDPLUGIN_ADMIN_LAUNCHER),
                    "sha256": "a" * 64,
                    "size_bytes": 101,
                    "mode": "0500",
                },
                "receipt": {
                    "name": planner.BUILDPLUGIN_ADMIN_RECEIPT.name,
                    "path": str(planner.BUILDPLUGIN_ADMIN_RECEIPT),
                    "sha256": "b" * 64,
                    "size_bytes": 102,
                    "mode": "0444",
                    "schema": planner.BUILDPLUGIN_ADMIN_RECEIPT_SCHEMA,
                    "content_digest": "c" * 64,
                },
                "bootstrap_provenance": {
                    "core_review_audit_pin": {
                        "sha256": "d" * 64,
                        "size_bytes": 103,
                    },
                    "content_digest": "e" * 64,
                },
                "admin_launcher_fd_required": True,
            },
            "policy": planner.BUILDPLUGIN_POLICY,
            "claims": planner.BUILDPLUGIN_NEGATIVE_CLAIMS,
        },
        mode=0o444,
    )
    result = dataclasses.replace(
        config,
        buildplugin=contract,
        buildplugin_authority=planner.BuildPluginAuthority(
            root=root,
            manifest=manifest_pin,
            receipt=receipt_pin,
        ),
    )
    if result.r8_authority is not None:
        r8 = result.r8_authority
        host = json.loads(r8.host_receipt.path.read_text())
        host["bindings"]["buildplugin_tree_digest"] = projection
        _, host_pin = _write_document(r8.host_receipt.path, host, mode=0o444)
        result = dataclasses.replace(
            result,
            r8_authority=dataclasses.replace(r8, host_receipt=host_pin),
        )
    return result


def _rewrite_parent(
    fixture: Fixture,
    name: str,
    mutate: Callable[[dict[str, Any]], None],
) -> planner.Config:
    parent = fixture.config.parent
    document = json.loads(json.dumps(fixture.parent_documents[name]))
    mutate(document)
    path = getattr(parent, name).path
    updated, pin = _write_document(path, document)
    updates: dict[str, Any] = {name: pin}
    if name in {"combined", "host"}:
        complete = json.loads(json.dumps(fixture.parent_documents["complete"]))
        complete[f"{name}_receipt"] = planner._receipt_file_mapping(pin)
        _, complete_pin = _write_document(parent.complete.path, complete)
        updates["complete"] = complete_pin
    assert updated["content_digest"]
    return dataclasses.replace(
        fixture.config, parent=dataclasses.replace(parent, **updates)
    )


def _rewrite_r3(
    fixture: Fixture,
    mutate: Callable[[dict[str, Any]], None],
    *,
    update_expected_inventory: bool = False,
) -> planner.Config:
    document = json.loads(json.dumps(fixture.r3_receipt))
    mutate(document)
    updated, pin = _write_document(
        fixture.config.r3.receipt.path,
        document,
        trailing_newline=False,
    )
    digest = (
        planner._inventory_digest(updated["package_inventory"])
        if update_expected_inventory
        else fixture.config.r3.inventory_digest
    )
    return dataclasses.replace(
        fixture.config,
        r3=dataclasses.replace(
            fixture.config.r3,
            receipt=pin,
            inventory_digest=digest,
        ),
    )


def test_blocked_plan_is_deterministic_exact_and_zero_write(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    before = _tree_state(tmp_path)
    first = planner.build_plan(ATTEMPT, config=fixture.config)
    second = planner.build_plan(ATTEMPT, config=fixture.config)

    assert first.raw == second.raw
    assert _tree_state(tmp_path) == before
    assert not (fixture.config.run_parent / ATTEMPT).exists()
    assert first.report["status"] == planner.BLOCKED_STATUS
    assert first.report["mode"] == planner.MODE
    assert first.report["accepted"] is False
    assert first.report["blockers"] == [
        "fresh_root_published_r8_animation_authority",
        "reviewed_root_buildplugin_authority",
    ]
    assert first.report["expected_child_delta"]["additive_package_count"] == 32
    assert first.report["r3_character_overlay"]["package_count"] == 23
    assert first.report["r8_animation_overlay"]["package_count"] == 9
    assert all(value is False for value in first.report["claims"].values())
    assert first.report["security"] == {
        "default_zero_write": True,
        "writes_performed": False,
        "will_run_unreal": False,
        "will_run_blender": False,
        "will_use_gpu": False,
        "will_change_services": False,
        "caller_path_or_authority_overrides": False,
        "quarantined_development_animation_fallback": False,
        "full_parent_tree_copy_or_rescan": False,
    }
    assert first.report["content_digest"] == planner.content_digest(first.report)


def test_direct_cli_import_does_not_create_bytecode(tmp_path: Path) -> None:
    cli_root = tmp_path / "clean-cli"
    cli_root.mkdir()
    planner_copy = cli_root / Path(planner.__file__).name
    executor_copy = cli_root / Path(executor.__file__).name
    shutil.copy2(planner.__file__, planner_copy)
    shutil.copy2(executor.__file__, executor_copy)
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE"):
        environment.pop(name, None)

    completed = subprocess.run(
        [sys.executable, str(planner_copy), "--help"],
        cwd=cli_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--attempt-name" in completed.stdout
    assert not list(cli_root.rglob("__pycache__"))
    assert not list(cli_root.rglob("*.pyc"))


def test_complete_fake_authorities_are_only_ready_for_materializer(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    config = _with_buildplugin(_with_r8(fixture))
    before = _tree_state(tmp_path)

    prepared = planner.build_plan(ATTEMPT, config=config)

    assert _tree_state(tmp_path) == before
    assert prepared.report["status"] == planner.READY_STATUS
    assert prepared.report["blockers"] == []
    assert prepared.report["r8_animation_overlay"]["authority_ready"] is True
    assert prepared.report["plugin_replacement"]["authority_ready"] is True
    assert (
        prepared.report["next_gate"] == "review_separate_append_only_materializer_spec"
    )
    assert all(value is False for value in prepared.report["claims"].values())
    assert prepared.report["provider_transition"] == {
        "source_provider": planner.SOURCE_PROVIDER,
        "target_provider": planner.TARGET_PROVIDER,
        "activation_argument": "-VistaCharacterProvider=makehuman_cc0_r8",
        "runtime_activation_verified": False,
    }


@pytest.mark.parametrize(
    ("name", "mutate", "match"),
    [
        (
            "combined",
            lambda value: value.__setitem__("provider_id", "caller_override"),
            "authority differs",
        ),
        (
            "combined",
            lambda value: value["project_static_tree"].__setitem__(
                "tree_sha256", "9" * 64
            ),
            "authority differs",
        ),
        (
            "host",
            lambda value: value["legal_scope"].__setitem__(
                "excluded_from_vista_dataset_or_database", False
            ),
            "authority differs",
        ),
        (
            "host",
            lambda value: value["claims"].__setitem__("gta_level_quality", True),
            "authority differs",
        ),
    ],
)
def test_parent_coherence_drift_fails_closed(
    tmp_path: Path,
    name: str,
    mutate: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    fixture = _fixture(tmp_path)
    config = _rewrite_parent(fixture, name, mutate)
    with pytest.raises(planner.PlanError, match=match):
        planner.build_plan(ATTEMPT, config=config)


def test_parent_current_map_bytes_are_rehashed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture.config.parent.map_package.path.write_bytes(b"changedmap")
    with pytest.raises(planner.PlanError, match="map package SHA-256 differs"):
        planner.build_plan(ATTEMPT, config=fixture.config)


def test_parent_failure_marker_and_namespace_collision_fail(tmp_path: Path) -> None:
    failure_fixture = _fixture(tmp_path / "failure")
    _write(failure_fixture.config.parent.failure_marker, b"failure")
    with pytest.raises(planner.PlanError, match="failure marker exists"):
        planner.build_plan(ATTEMPT, config=failure_fixture.config)

    namespace_fixture = _fixture(tmp_path / "namespace")
    (
        namespace_fixture.config.parent.root / "project/Content/VISTA/MAKEHUMANCC0"
    ).mkdir()
    with pytest.raises(planner.PlanError, match="already contains"):
        planner.build_plan(ATTEMPT, config=namespace_fixture.config)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows.pop(),
        lambda rows: rows.append(dict(rows[-1])),
        lambda rows: rows.__setitem__(slice(0, 2), [rows[1], rows[0]]),
    ],
)
def test_r3_inventory_omission_extra_and_order_drift_fail(
    tmp_path: Path, mutate: Callable[[list[dict[str, Any]]], None]
) -> None:
    fixture = _fixture(tmp_path)
    config = _rewrite_r3(fixture, lambda value: mutate(value["package_inventory"]))
    with pytest.raises(planner.PlanError, match="inventory digest differs"):
        planner.build_plan(ATTEMPT, config=config)


def test_r3_package_bytes_and_modes_are_rehashed(tmp_path: Path) -> None:
    bytes_fixture = _fixture(tmp_path / "bytes")
    relative = planner.R3_PACKAGE_PATHS[0]
    package = bytes_fixture.config.r3.project_root / relative
    original = package.read_bytes()
    package.write_bytes(b"x" * len(original))
    with pytest.raises(planner.PlanError, match="SHA-256 differs"):
        planner.build_plan(ATTEMPT, config=bytes_fixture.config)

    mode_fixture = _fixture(tmp_path / "mode")
    package = mode_fixture.config.r3.project_root / relative
    package.chmod(0o640)
    with pytest.raises(planner.PlanError, match="size or mode differs"):
        planner.build_plan(ATTEMPT, config=mode_fixture.config)


@pytest.mark.parametrize(
    "value",
    [
        "/Content/VISTA/MakeHumanCC0/R6/Bad.uasset",
        "Content/VISTA/MakeHumanCC0/R6/../Bad.uasset",
        "Content\\VISTA\\MakeHumanCC0\\R6\\Bad.uasset",
        "Content/VISTA/MakeHumanCC0/R6/Bad\x00.uasset",
        "Content/VISTA/MakeHumanCC0/R6/Bad\x7f.uasset",
        "Content/VISTA/MakeHumanCC0/R7/Bad.uasset",
        "Content/VISTA/MakeHumanCC0/R6/Bad.txt",
    ],
)
def test_package_paths_reject_traversal_aliases_and_wrong_namespace(
    value: str,
) -> None:
    with pytest.raises(planner.PlanError, match="PACKAGE_PATH_INVALID"):
        planner._safe_package_path(value, planner.R3_NAMESPACE, "test")


def test_casefold_collisions_and_cross_partition_overlap_fail() -> None:
    with pytest.raises(planner.PlanError, match="case-fold collision"):
        planner._assert_distinct_paths(
            [
                "Content/VISTA/MakeHumanCC0/R6/Hero.uasset",
                "content/vista/makehumancc0/r6/hero.uasset",
            ],
            "test",
        )


def test_attempt_must_be_fresh_closed_direct_child(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    for value in (
        "../escape",
        "hssd-r2-cc0-animation-overlay-r1-a/b",
        "caller-selected-name",
    ):
        with pytest.raises(planner.PlanError, match="attempt name differs"):
            planner.build_plan(value, config=fixture.config)
    (fixture.config.run_parent / ATTEMPT).mkdir()
    with pytest.raises(planner.PlanError, match="already exists"):
        planner.build_plan(ATTEMPT, config=fixture.config)


def test_run_parent_and_authority_roots_must_not_be_symlinks(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "base")
    alias = tmp_path / "run-alias"
    alias.symlink_to(fixture.config.run_parent, target_is_directory=True)
    config = dataclasses.replace(fixture.config, run_parent=alias)
    with pytest.raises(planner.PlanError, match="not a direct directory"):
        planner.build_plan(ATTEMPT, config=config)

    parent_fixture = _fixture(tmp_path / "parent")
    real_root = parent_fixture.config.parent.root
    parent_alias = tmp_path / "h-alias"
    parent_alias.symlink_to(real_root, target_is_directory=True)
    parent = dataclasses.replace(parent_fixture.config.parent, root=parent_alias)
    config = dataclasses.replace(parent_fixture.config, parent=parent)
    with pytest.raises(planner.PlanError, match="not a direct directory"):
        planner.build_plan(ATTEMPT, config=config)


def test_unpinned_future_authorities_fail_instead_of_fallback(tmp_path: Path) -> None:
    r8_fixture = _fixture(tmp_path / "r8")
    (
        r8_fixture.config.r8_published_parent / "makehuman-cc0-animation-ue57-r1-x"
    ).mkdir()
    with pytest.raises(planner.PlanError, match="unpinned R8"):
        planner.build_plan(ATTEMPT, config=r8_fixture.config)

    plugin_fixture = _fixture(tmp_path / "plugin")
    plugin_fixture.config.buildplugin.root.mkdir(parents=True)
    with pytest.raises(planner.PlanError, match="unpinned BuildPlugin"):
        planner.build_plan(ATTEMPT, config=plugin_fixture.config)


def test_r8_lineage_and_package_inventory_fail_closed(tmp_path: Path) -> None:
    lineage_fixture = _fixture(tmp_path / "lineage")
    config = _with_r8(lineage_fixture)
    authority = config.r8_authority
    assert authority is not None
    host = json.loads(authority.host_receipt.path.read_text())
    host["bindings"]["r3_project_tree_digest"] = "0" * 64
    _, host_pin = _write_document(authority.host_receipt.path, host, mode=0o444)
    config = dataclasses.replace(
        config,
        r8_authority=dataclasses.replace(authority, host_receipt=host_pin),
    )
    with pytest.raises(planner.PlanError, match="host lineage differs"):
        planner.build_plan(ATTEMPT, config=config)

    inventory_fixture = _fixture(tmp_path / "inventory")
    config = _with_r8(inventory_fixture)
    authority = config.r8_authority
    assert authority is not None
    runtime = json.loads(authority.runtime_receipt.path.read_text())
    runtime["package_inventory"].pop()
    runtime, runtime_pin = _write_document(
        authority.runtime_receipt.path, runtime, mode=0o444
    )
    host = json.loads(authority.host_receipt.path.read_text())
    host["bindings"]["commandlet_receipt_content_digest"] = runtime["content_digest"]
    host["bindings"]["commandlet_result_receipt_sha256"] = runtime_pin.pin.sha256
    _, host_pin = _write_document(authority.host_receipt.path, host, mode=0o444)
    config = dataclasses.replace(
        config,
        r8_authority=dataclasses.replace(
            authority,
            host_receipt=host_pin,
            runtime_receipt=runtime_pin,
        ),
    )
    with pytest.raises(planner.PlanError, match="package count differs"):
        planner.build_plan(ATTEMPT, config=config)


@pytest.mark.parametrize(
    "binding_name",
    ["r8_host_receipt_sha256", "commandlet_result_receipt_sha256"],
)
def test_r8_host_runtime_receipt_sha_lineage_must_close(
    tmp_path: Path, binding_name: str
) -> None:
    fixture = _fixture(tmp_path)
    config = _with_r8(fixture)
    authority = config.r8_authority
    assert authority is not None
    host = json.loads(authority.host_receipt.path.read_text())
    host["bindings"][binding_name] = "0" * 64
    _, host_pin = _write_document(authority.host_receipt.path, host, mode=0o444)
    config = dataclasses.replace(
        config,
        r8_authority=dataclasses.replace(authority, host_receipt=host_pin),
    )

    with pytest.raises(planner.PlanError, match="host-to-runtime lineage differs"):
        planner.build_plan(ATTEMPT, config=config)


@pytest.mark.parametrize(
    "projection_field", ["file_count", "directory_count", "total_bytes"]
)
def test_r8_host_project_projection_counts_are_exact(
    tmp_path: Path, projection_field: str
) -> None:
    fixture = _fixture(tmp_path)
    config = _with_r8(fixture)
    authority = config.r8_authority
    assert authority is not None
    host = json.loads(authority.host_receipt.path.read_text())
    host["project_projection"][projection_field] += 1
    _, host_pin = _write_document(authority.host_receipt.path, host, mode=0o444)
    config = dataclasses.replace(
        config,
        r8_authority=dataclasses.replace(authority, host_receipt=host_pin),
    )

    with pytest.raises(planner.PlanError, match="project projection counts differ"):
        planner.build_plan(ATTEMPT, config=config)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda runtime: runtime["package_inventory"][0].__setitem__(
                "class_path", "/Script/Engine.SkeletalMesh"
            ),
            "package class differs",
        ),
        (
            lambda runtime: runtime["claims"].__setitem__(
                "private_epic_content_used", True
            ),
            "terminal contract differs",
        ),
        (
            lambda runtime: runtime["gates"].__setitem__(
                "exact_nine_asset_inventory", False
            ),
            "terminal contract differs",
        ),
    ],
)
def test_r8_wrong_class_positive_claim_and_failed_gate_are_rejected(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    fixture = _fixture(tmp_path)
    config = _with_r8(fixture)
    authority = config.r8_authority
    assert authority is not None
    runtime = json.loads(authority.runtime_receipt.path.read_text())
    mutate(runtime)
    runtime, runtime_pin = _write_document(
        authority.runtime_receipt.path, runtime, mode=0o444
    )
    host = json.loads(authority.host_receipt.path.read_text())
    host["bindings"]["commandlet_receipt_content_digest"] = runtime["content_digest"]
    host["bindings"]["commandlet_result_receipt_sha256"] = runtime_pin.pin.sha256
    _, host_pin = _write_document(authority.host_receipt.path, host, mode=0o444)
    config = dataclasses.replace(
        config,
        r8_authority=dataclasses.replace(
            authority,
            host_receipt=host_pin,
            runtime_receipt=runtime_pin,
        ),
    )
    with pytest.raises(planner.PlanError, match=match):
        planner.build_plan(ATTEMPT, config=config)


def test_r8_inherited_r3_packages_must_remain_byte_identical(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    config = _with_r8(fixture)
    authority = config.r8_authority
    assert authority is not None
    path = authority.root / "project" / planner.R3_PACKAGE_PATHS[0]
    raw = path.read_bytes()
    path.chmod(0o600)
    path.write_bytes(b"z" * len(raw))
    path.chmod(0o444)
    with pytest.raises(planner.PlanError, match="SHA-256 differs"):
        planner.build_plan(ATTEMPT, config=config)


def test_buildplugin_manifest_projection_drift_fails(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    config = _with_buildplugin(_with_r8(fixture))
    authority = config.buildplugin_authority
    assert authority is not None
    manifest = json.loads(authority.manifest.path.read_text())
    manifest["source"]["projection_sha256"] = "0" * 64
    manifest_pin = _write(
        authority.manifest.path, planner.canonical_json(manifest), 0o444
    )
    receipt = json.loads(authority.receipt.path.read_text())
    receipt["authority"]["manifest"] = {
        "path": "manifest.json",
        "sha256": manifest_pin.pin.sha256,
        "size_bytes": manifest_pin.pin.size_bytes,
    }
    _, receipt_pin = _write_document(authority.receipt.path, receipt, mode=0o444)
    config = dataclasses.replace(
        config,
        buildplugin_authority=dataclasses.replace(
            authority, manifest=manifest_pin, receipt=receipt_pin
        ),
    )
    with pytest.raises(planner.PlanError, match="source projection differs"):
        planner.build_plan(ATTEMPT, config=config)


def test_buildplugin_rejects_unmanifested_payload_bytes(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    config = _with_buildplugin(_with_r8(fixture))
    payload = config.buildplugin.payload
    payload.chmod(0o755)
    _write(payload / "UNMANIFESTED.bin", b"unexpected", 0o444)
    payload.chmod(0o555)
    with pytest.raises(planner.PlanError, match="complete inventory differs"):
        planner.build_plan(ATTEMPT, config=config)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipt: receipt.__setitem__("publisher", {}),
        lambda receipt: receipt.__setitem__("policy", {}),
        lambda receipt: receipt.__setitem__(
            "schema_version", "vista.r8-buildplugin-authority-receipt/v1"
        ),
        lambda receipt: receipt.pop("admin_publication"),
        lambda receipt: receipt["admin_publication"].__setitem__("unexpected", True),
        lambda receipt: receipt["admin_publication"].__setitem__(
            "admin_launcher_fd_required", False
        ),
        lambda receipt: receipt["admin_publication"].__setitem__(
            "admin_launcher_fd_required", 1
        ),
        lambda receipt: receipt["admin_publication"]["receipt"].__setitem__(
            "path", "/root/rebound/receipt.json"
        ),
        lambda receipt: receipt["claims"].__setitem__(
            "private_epic_content_used", True
        ),
    ],
)
def test_buildplugin_requires_exact_publisher_policy_and_negative_claims(
    tmp_path: Path, mutate: Callable[[dict[str, Any]], None]
) -> None:
    fixture = _fixture(tmp_path)
    config = _with_buildplugin(_with_r8(fixture))
    authority = config.buildplugin_authority
    assert authority is not None
    receipt = json.loads(authority.receipt.path.read_text())
    mutate(receipt)
    _, receipt_pin = _write_document(authority.receipt.path, receipt, mode=0o444)
    config = dataclasses.replace(
        config,
        buildplugin_authority=dataclasses.replace(authority, receipt=receipt_pin),
    )
    with pytest.raises(planner.PlanError, match="BuildPlugin receipt differs"):
        planner.build_plan(ATTEMPT, config=config)


def test_future_authority_regular_files_must_be_root_owned_when_required(
    tmp_path: Path,
) -> None:
    path = tmp_path / "authority-file"
    pin = _write(path, b"authority", 0o444)
    with pytest.raises(planner.PlanError, match="not root-owned"):
        planner._read_pinned_file(pin, "authority", require_root_owned=True)


def test_cli_has_no_path_authority_provider_or_execute_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = _fixture(tmp_path)
    monkeypatch.setattr(planner, "PRODUCTION_CONFIG", fixture.config)
    assert planner.main(["--attempt-name", ATTEMPT]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == planner.BLOCKED_STATUS
    destinations = {action.dest for action in planner._parser()._actions}
    assert destinations == {"help", "attempt_name"}
    with pytest.raises(SystemExit):
        planner._parser().parse_args(
            ["--attempt-name", ATTEMPT, "--parent-root", str(tmp_path)]
        )
    with pytest.raises(SystemExit):
        planner._parser().parse_args(["--attempt-name", ATTEMPT, "--execute"])


def test_checked_in_animation_inventory_is_exactly_shared_with_executor() -> None:
    assert planner.R8_PACKAGE_PATHS == executor.EXPECTED_PACKAGE_PATHS
    assert len(planner.R3_PACKAGE_PATHS) == 23
    paths_digest = hashlib.sha256(
        planner.canonical_json(
            {"project_relative_paths": sorted(planner.R3_PACKAGE_PATHS)}
        )
    ).hexdigest()
    assert paths_digest == (
        "5338443816584d5e8ec0f783bb30b7cb862ef2247cf9520660e33f828ca46861"
    )


def test_production_buildplugin_contract_matches_reviewed_publisher() -> None:
    contract = planner.PRODUCTION_CONFIG.buildplugin
    reviewed = buildplugin_authority.PRODUCTION_CONTRACT
    assert contract.root == reviewed.authority_root
    assert contract.source_path == reviewed.source_root
    assert contract.projection_sha256 == reviewed.projection_sha256
    assert contract.inventory_sha256 == reviewed.inventory_sha256
    assert contract.file_count == reviewed.file_count
    assert contract.directory_count == reviewed.directory_count
    assert contract.total_bytes == reviewed.total_bytes
    assert {
        path: (pin.sha256, pin.size_bytes, pin.mode)
        for path, pin in contract.critical_files.items()
    } == {
        path: (pin.sha256, pin.size_bytes, pin.mode)
        for path, pin in reviewed.critical_file_pins.items()
    }
    assert planner.BUILDPLUGIN_POLICY == {
        "copy_from_held_source_descriptors_only": True,
        "all_source_file_descriptors_held": True,
        "source_namespace_revalidated_after_copy": True,
        "fresh_staging_only": True,
        "atomic_publish": "renameat2_noreplace",
        "output_directory_mode": "0555",
        "output_file_mode": "0444",
    }
    assert planner.BUILDPLUGIN_NEGATIVE_CLAIMS == dict(
        buildplugin_authority.NEGATIVE_CLAIMS
    )
    helper_raw = Path(buildplugin_authority.__file__).read_bytes()
    assert hashlib.sha256(helper_raw).hexdigest() == planner.BUILDPLUGIN_HELPER_SHA256
    assert len(helper_raw) == planner.BUILDPLUGIN_HELPER_SIZE_BYTES
