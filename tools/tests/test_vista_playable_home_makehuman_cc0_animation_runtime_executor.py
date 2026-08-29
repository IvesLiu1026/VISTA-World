from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.ue.vista_playable_home import (
    makehuman_cc0_animation_runtime_executor as executor,
)
from tools.ue.vista_playable_home import (
    makehuman_cc0_animation_runtime_sandbox_wrapper as wrapper,
)


ATTEMPT = "makehuman-cc0-animation-ue57-r1-unit"


def _sealed(value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    result["content_digest"] = wrapper.content_digest(result)
    return result


def _archive_members() -> dict[str, bytes]:
    return {
        path: ("payload:" + path).encode() for path in executor.EXPECTED_ARCHIVE_PATHS
    }


def _pin_document(character: str, size_bytes: int = 1) -> dict[str, object]:
    return {"sha256": character * 64, "size_bytes": size_bytes}


def _trusted_root_lstat(path: os.PathLike[str] | str) -> SimpleNamespace:
    info = os.lstat(path)
    kind = stat.S_IFDIR if stat.S_ISDIR(info.st_mode) else stat.S_IFREG
    mode = 0o555 if stat.S_ISDIR(info.st_mode) or info.st_mode & 0o111 else 0o444
    return SimpleNamespace(
        st_mode=kind | mode,
        st_uid=0,
        st_gid=0,
        st_size=info.st_size,
    )


def _write(path: Path, raw: bytes, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o755 if executable else 0o644)


def _pin(path: Path, *, executable: bool = False) -> executor.FilePin:
    raw = path.read_bytes()
    return executor.FilePin(
        hashlib.sha256(raw).hexdigest(), len(raw), executable=executable
    )


def _projection(tree: executor.TreeSnapshot) -> dict[str, object]:
    return {
        "tree_digest": tree.sha256,
        "file_count": len(tree.files),
        "directory_count": len(tree.directories),
        "total_bytes": tree.total_bytes,
    }


def _engine_manifest(root: Path) -> tuple[dict[str, object], str]:
    entries: list[dict[str, object]] = []
    for current, directories, files in os.walk(root):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name in directories:
            relative = (current_path / name).relative_to(root).as_posix()
            entries.append(
                {
                    "path": relative,
                    "type": "directory",
                    "mode": 0o555,
                    "uid": 0,
                    "gid": 0,
                    "size_bytes": 0,
                    "sha256": "",
                }
            )
        for name in files:
            path = current_path / name
            raw = path.read_bytes()
            relative = path.relative_to(root).as_posix()
            entries.append(
                {
                    "path": relative,
                    "type": "file",
                    "mode": 0o555 if path.stat().st_mode & 0o111 else 0o444,
                    "uid": 0,
                    "gid": 0,
                    "size_bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
    entries.sort(key=lambda item: str(item["path"]))
    content_entries = [
        {
            "path": item["path"],
            "type": item["type"],
            "size_bytes": item["size_bytes"],
            "sha256": item["sha256"],
        }
        for item in entries
    ]
    tree_digest = hashlib.sha256(
        executor.canonical_json({"entries": content_entries})
    ).hexdigest()
    return (
        executor.seal_document(
            {
                "schema": executor.ENGINE_MANIFEST_SCHEMA,
                "engine_root": str(root),
                "entries": entries,
                "tree_root_digest": tree_digest,
            }
        ),
        tree_digest,
    )


def _complete_fake_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[executor.ExecutionPlan, dict[str, Path]]:
    authority = tmp_path / "authority"
    bundle = authority / "bundle"
    root_policy = authority / "root-policy.json"
    python = authority / "bin/python3.10"
    bwrap = authority / "bin/bwrap"
    runtime = authority / "host-runtime"
    engine = authority / "engine"
    engine_manifest_path = authority / "engine-manifest.json"
    r3_root = authority / "r3/project"
    r3_receipt = authority / "r3/receipt.json"
    r8_parent = authority / "r8"
    r8_name = "makehuman-cc0-animation-r8-fresh-root-r1"
    r8_root = r8_parent / r8_name
    plugin = authority / "plugin"
    published = tmp_path / "published"

    for name, value in {
        "ROOT_POLICY_PATH": root_policy,
        "ROOT_BUNDLE": bundle,
        "WRAPPER_PYTHON": python,
        "BWRAP_PATH": bwrap,
        "HOST_RUNTIME_ROOT": runtime,
        "IMMUTABLE_ENGINE_ROOT": engine,
        "IMMUTABLE_ENGINE_MANIFEST": engine_manifest_path,
        "R3_PROJECT_ROOT": r3_root,
        "R3_RECEIPT_PATH": r3_receipt,
        "R8_PUBLISHED_PARENT": r8_parent,
        "BUILDPLUGIN_ROOT": plugin,
        "PUBLISHED_PARENT": published,
    }.items():
        monkeypatch.setattr(executor, name, value)
    monkeypatch.setattr(wrapper, "ROOT_POLICY_PATH", root_policy)
    monkeypatch.setattr(executor, "AUTHORITY_LSTAT", _trusted_root_lstat)

    _write(python, b"#!/bin/sh\n", executable=True)
    _write(bwrap, b"#!/bin/sh\n", executable=True)
    for relative in executor.HOST_RUNTIME_REQUIRED_DIRECTORIES:
        (runtime / relative).mkdir(parents=True, exist_ok=True)
    _write(runtime / "lib/runtime.so", b"runtime closure")
    runtime_tree = executor.snapshot_tree(
        runtime, "fake runtime", immutable_authority=False
    )

    engine_command = engine / "Engine/Binaries/Linux/UnrealEditor-Cmd"
    engine_modules = engine / "Engine/Binaries/Linux/UnrealEditor.modules"
    engine_version = engine / "Engine/Build/Build.version"
    _write(engine_command, b"#!/bin/sh\n", executable=True)
    _write(
        engine_modules,
        (json.dumps({"BuildId": "123456", "Modules": {}}, indent=2) + "\n").encode(),
    )
    _write(
        engine_version,
        (
            json.dumps(
                {
                    "MajorVersion": 5,
                    "MinorVersion": 7,
                    "PatchVersion": 3,
                    "BranchName": "++UE5+Release-5.7",
                },
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    engine_manifest, engine_tree_digest = _engine_manifest(engine)
    _write(engine_manifest_path, executor.canonical_json(engine_manifest))

    _write(r3_root / executor.PROJECT_FILE_NAME, b'{"FileVersion":3}\n')
    _write(r3_root / "Content/Base.uasset", b"base")
    (r3_root / "Content/EmptyDirectory").mkdir(parents=True)
    r3_tree = executor.snapshot_tree(r3_root, "fake R3", immutable_authority=False)
    r3_digest = "d" * 64
    r3_receipt_document = {
        "schema_version": "vista.makehuman-cc0-ue57-import-host-receipt/v1",
        "status": "cc0_skeletal_import_post_exit_project_sealed",
        "accepted": False,
        "content_digest": r3_digest,
        "output_project_projection": {
            "sha256": r3_tree.sha256,
            "file_count": len(r3_tree.files),
            "directory_count": len(r3_tree.directories),
            "total_bytes": r3_tree.total_bytes,
        },
        "claims": {
            "ue_skeletal_imported": True,
            "own_skeleton_imported": True,
            "exact_53_bones_verified": True,
            "animation_verified": False,
        },
    }
    _write(r3_receipt, executor.canonical_json(r3_receipt_document))

    artifacts: list[dict[str, object]] = []
    blend_relative = "library/vista_cc0_animation_library_r8.blend"
    blend = r8_root / "artifacts" / blend_relative
    _write(blend, b"blend")
    artifacts.append(
        {
            "relative_path": blend_relative,
            "sha256": hashlib.sha256(b"blend").hexdigest(),
            "size_bytes": 5,
        }
    )
    for index, spec in enumerate(executor.CLIP_SPECS):
        relative = spec["fbx_relative_path"]
        raw = f"fbx-{index}".encode()
        _write(r8_root / "artifacts" / relative, raw)
        artifacts.append(
            {
                "relative_path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
        )
    r8_receipt_document = executor.seal_document(
        {
            "schema_version": executor.SOURCE_HOST_RECEIPT_SCHEMA,
            "accepted": False,
            "status": executor.SOURCE_SUCCESS_STATUS,
            "claims": {
                "blender_animation_authored": True,
                "fbx_roundtrip_verified": True,
                "ue_animation_imported": False,
                "runtime_interaction_verified": False,
                "human_motion_quality_accepted": False,
            },
            "artifacts": artifacts,
        }
    )
    r8_receipt = r8_root / "host-receipt.json"
    _write(r8_receipt, executor.canonical_json(r8_receipt_document))

    _write(
        plugin / "VistaPlayableHome.uplugin",
        (
            json.dumps(
                {
                    "Modules": [
                        {"Name": "VistaPlayableHome"},
                        {"Name": "VistaPlayableHomeEditor"},
                    ]
                },
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    _write(
        plugin / "Binaries/Linux/UnrealEditor.modules",
        (
            json.dumps(
                {
                    "BuildId": "123456",
                    "Modules": {
                        "VistaPlayableHome": "libUnrealEditor-VistaPlayableHome.so",
                        "VistaPlayableHomeEditor": (
                            "libUnrealEditor-VistaPlayableHomeEditor.so"
                        ),
                    },
                },
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    _write(
        plugin / "Binaries/Linux/libUnrealEditor-VistaPlayableHome.so",
        b"\x7fELF-runtime",
    )
    _write(
        plugin / "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so",
        b"\x7fELF-editor",
    )
    (plugin / "Resources/EmptyDirectory").mkdir(parents=True)
    plugin_tree = executor.snapshot_tree(
        plugin, "fake plugin", immutable_authority=False
    )

    executor_source = Path(executor.__file__)
    wrapper_source = Path(wrapper.__file__)
    commandlet_source = executor_source.with_name(
        "makehuman_cc0_animation_runtime_commandlet.py"
    )
    executor_copy = bundle / executor_source.name
    wrapper_copy = bundle / wrapper_source.name
    commandlet_copy = bundle / commandlet_source.name
    _write(executor_copy, executor_source.read_bytes(), executable=True)
    _write(wrapper_copy, wrapper_source.read_bytes())
    _write(commandlet_copy, commandlet_source.read_bytes())
    bundle_pins = {
        executor_copy.name: _pin(executor_copy, executable=True),
        wrapper_copy.name: _pin(wrapper_copy),
        commandlet_copy.name: _pin(commandlet_copy),
    }
    bundle_manifest = executor.seal_document(
        {
            "schema": executor.BUNDLE_MANIFEST_SCHEMA,
            "files": [
                {
                    "path": name,
                    "sha256": pin.sha256,
                    "size_bytes": pin.size_bytes,
                    "executable": pin.executable,
                }
                for name, pin in sorted(bundle_pins.items())
            ],
        }
    )
    bundle_manifest_path = bundle / "bundle-manifest.json"
    _write(bundle_manifest_path, executor.canonical_json(bundle_manifest))

    policy_document = executor.seal_document(
        {
            "schema": executor.ROOT_POLICY_SCHEMA,
            "bundle_manifest_pin": dataclasses.asdict(_pin(bundle_manifest_path)) | {},
            "bundle_manifest_content_digest": bundle_manifest["content_digest"],
            "executor_pin": {
                "sha256": bundle_pins[executor_copy.name].sha256,
                "size_bytes": bundle_pins[executor_copy.name].size_bytes,
            },
            "wrapper_pin": {
                "sha256": bundle_pins[wrapper_copy.name].sha256,
                "size_bytes": bundle_pins[wrapper_copy.name].size_bytes,
            },
            "commandlet_pin": {
                "sha256": bundle_pins[commandlet_copy.name].sha256,
                "size_bytes": bundle_pins[commandlet_copy.name].size_bytes,
            },
            "wrapper_python_pin": {
                "sha256": _pin(python, executable=True).sha256,
                "size_bytes": _pin(python, executable=True).size_bytes,
            },
            "host_runtime": _projection(runtime_tree),
            "engine": {
                "manifest_pin": {
                    "sha256": _pin(engine_manifest_path).sha256,
                    "size_bytes": _pin(engine_manifest_path).size_bytes,
                },
                "manifest_content_digest": engine_manifest["content_digest"],
                "tree_digest": engine_tree_digest,
                "critical_files": [
                    {
                        "relative_path": path.relative_to(engine).as_posix(),
                        "sha256": _pin(path, executable=path == engine_command).sha256,
                        "size_bytes": _pin(path).size_bytes,
                        "executable": path == engine_command,
                    }
                    for path in (engine_command, engine_modules, engine_version)
                ],
            },
            "r3": {
                "receipt_pin": {
                    "sha256": _pin(r3_receipt).sha256,
                    "size_bytes": _pin(r3_receipt).size_bytes,
                },
                "receipt_content_digest": r3_digest,
                "project": _projection(r3_tree),
            },
            "r8": {
                "attempt_name": r8_name,
                "receipt_pin": {
                    "sha256": _pin(r8_receipt).sha256,
                    "size_bytes": _pin(r8_receipt).size_bytes,
                },
                "receipt_content_digest": r8_receipt_document["content_digest"],
            },
            "plugin": _projection(plugin_tree),
            "bwrap_pin": {
                "sha256": _pin(bwrap, executable=True).sha256,
                "size_bytes": _pin(bwrap, executable=True).size_bytes,
            },
        }
    )
    # FilePin.executable is policy-derived and therefore absent from pin records.
    policy_document["bundle_manifest_pin"].pop("executable")
    policy_document["content_digest"] = executor.content_digest(policy_document)
    _write(root_policy, executor.canonical_json(policy_document))
    published.mkdir()

    policy = executor.load_root_policy()
    dry = executor.build_plan(
        ATTEMPT,
        execute=True,
        execution_acknowledgement=executor.EXECUTION_ACKNOWLEDGEMENT,
        policy=policy,
        running_executor_path=policy.executor_path,
        effective_uid=0,
    )
    assert dry.report["blockers"] == []
    plan = executor.prepare_execution(dry)
    return plan, {
        "r3_base": r3_root / "Content/Base.uasset",
        "r3_empty": r3_root / "Content/EmptyDirectory",
    }


def _terminal_sequence_inspection() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for spec in executor.CLIP_SPECS:
        frame_count = spec["frame_end"] - spec["frame_start"]
        result.append(
            {
                "object_path": (
                    f"{executor.CONTENT_NAMESPACE}/Sequences/"
                    f"{spec['sequence_name']}.{spec['sequence_name']}"
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
    return result


def _terminal_members(plan: executor.ExecutionPlan) -> dict[str, bytes]:
    members = _archive_members()
    package_payloads = {
        relative: members["project/" + relative]
        for relative in executor.EXPECTED_PACKAGE_PATHS
    }
    inventory = sorted(
        executor.EXPECTED_INVENTORY, key=lambda item: item["object_path"]
    )
    packages: list[dict[str, object]] = []
    for expected in inventory:
        object_path = expected["object_path"]
        package_name = object_path.split(".", 1)[0]
        relative = "Content/" + package_name.removeprefix("/Game/") + ".uasset"
        raw = package_payloads[relative]
        packages.append(
            {
                "class_path": expected["class_path"],
                "object_path": object_path,
                "package_name": package_name,
                "project_relative_path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }
        )
    receipt = executor.seal_document(
        {
            "schema_version": executor.COMMANDLET_RECEIPT_SCHEMA,
            "status": executor.SUCCESS_STATUS,
            "accepted": False,
            "error": None,
            "attempt_root": str(executor.SANDBOX_WORK_ROOT),
            "project_root": str(executor.SANDBOX_PROJECT_ROOT),
            "content_namespace": executor.CONTENT_NAMESPACE,
            "bindings": {
                "engine": executor.EXPECTED_ENGINE_VERSION,
                "project": str(executor.SANDBOX_PROJECT_FILE),
                "execution_manifest": str(executor.SANDBOX_EXECUTION_PATH),
                "execution_manifest_sha256": hashlib.sha256(
                    plan.commandlet_execution_raw
                ).hexdigest(),
                "source_host_receipt": plan.commandlet_execution["source_host_receipt"],
                "source_fbx": plan.commandlet_execution["source_fbx"],
                "commandlet": plan.commandlet_execution["commandlet"],
                "skeleton_object_path": executor.SKELETON_OBJECT_PATH,
                "mesh_object_path": executor.MESH_OBJECT_PATH,
            },
            "returned_object_paths": list(executor.EXPECTED_RETURNED_OBJECT_PATHS),
            "pipeline_policies": [
                executor._pipeline_policy(spec["sequence_name"])
                for spec in executor.CLIP_SPECS
            ],
            "sequence_inspection": _terminal_sequence_inspection(),
            "runtime_authoring_result": executor.EXPECTED_RUNTIME_AUTHORING_RESULT,
            "asset_inventory": inventory,
            "package_inventory": packages,
            "project_content_delta": executor._expected_content_delta(
                plan, package_payloads
            ),
            "gates": executor.TERMINAL_GATE_EXPECTATIONS,
            "claims": executor.TERMINAL_CLAIMS,
        }
    )
    receipt_raw = executor.canonical_json(receipt)
    result = {
        "schema_version": executor.COMMANDLET_RESULT_SCHEMA,
        "status": executor.SUCCESS_STATUS,
        "receipt": str(executor.SANDBOX_IMPORT_RECEIPT_PATH),
        "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "receipt_content_digest": receipt["content_digest"],
    }
    members[executor.ARCHIVE_RECEIPT_PATH] = receipt_raw
    members[executor.ARCHIVE_RESULT_PATH] = executor.canonical_json(result)
    return members


def _mutate_terminal_receipt(
    members: dict[str, bytes], mutation: str
) -> dict[str, bytes]:
    changed = dict(members)
    receipt = json.loads(changed[executor.ARCHIVE_RECEIPT_PATH])
    receipt.pop("content_digest")
    if mutation == "missing_gate":
        receipt["gates"].pop("packages_saved_reloaded")
    elif mutation == "gate_true_as_one":
        receipt["gates"]["packages_saved_reloaded"] = 1
    elif mutation == "gate_false_as_zero":
        receipt["gates"]["quarantined"] = 0
    elif mutation == "claim_true_as_one":
        receipt["claims"]["ue_animation_imported"] = 1
    elif mutation == "extra_top_level":
        receipt["review_override"] = True
    elif mutation == "incomplete_package":
        receipt["package_inventory"][0].pop("class_path")
    elif mutation == "package_binding":
        receipt["package_inventory"][0]["package_name"] = "/Game/Forged"
    elif mutation == "binding_extra":
        receipt["bindings"]["caller_override"] = "forbidden"
    elif mutation == "returned_object_paths":
        receipt["returned_object_paths"] = receipt["returned_object_paths"][:-1]
    elif mutation == "pipeline_policies":
        receipt["pipeline_policies"][0]["import_materials"] = True
    elif mutation == "pipeline_false_as_zero":
        receipt["pipeline_policies"][0]["import_materials"] = 0
    elif mutation == "sequence_inspection":
        receipt["sequence_inspection"][0]["inspection_phase"] = "pre_save_authoring"
    elif mutation == "runtime_authoring_result":
        receipt["runtime_authoring_result"]["status"] = "authored_pending"
    elif mutation == "runtime_false_as_zero":
        receipt["runtime_authoring_result"]["accepted"] = 0
    elif mutation == "asset_inventory":
        receipt["asset_inventory"][0]["class_path"] = "/Script/Engine.StaticMesh"
    elif mutation == "project_content_delta":
        receipt["project_content_delta"]["existing_file_count_unchanged"] += 1
    elif mutation == "content_delta_true_as_one":
        receipt["project_content_delta"]["existing_files_byte_identical"] = 1
    else:  # pragma: no cover - test helper closure
        raise AssertionError(mutation)
    receipt["content_digest"] = executor.content_digest(receipt)
    receipt_raw = executor.canonical_json(receipt)
    result = json.loads(changed[executor.ARCHIVE_RESULT_PATH])
    result["receipt_sha256"] = hashlib.sha256(receipt_raw).hexdigest()
    result["receipt_content_digest"] = receipt["content_digest"]
    changed[executor.ARCHIVE_RECEIPT_PATH] = receipt_raw
    changed[executor.ARCHIVE_RESULT_PATH] = executor.canonical_json(result)
    return changed


def _replace_header_field(
    archive: bytes, offset: int, start: int, end: int, value: bytes
) -> bytes:
    changed = bytearray(archive)
    header = bytearray(changed[offset : offset + 512])
    header[start:end] = b"\0" * (end - start)
    header[start : start + len(value)] = value
    header[148:156] = b"        "
    header[148:156] = f"{sum(header):06o}".encode("ascii") + b"\0 "
    changed[offset : offset + 512] = header
    return bytes(changed)


def test_dry_plan_is_deterministic_zero_write_and_production_blocked(
    tmp_path: Path,
) -> None:
    policy = dataclasses.replace(
        executor.PRODUCTION_POLICY,
        published_parent=tmp_path / "never-created",
    )
    before = set(tmp_path.iterdir())
    first = executor.build_plan(
        ATTEMPT,
        policy=policy,
        running_executor_path=Path(executor.__file__),
        effective_uid=1000,
    )
    second = executor.build_plan(
        ATTEMPT,
        policy=policy,
        running_executor_path=Path(executor.__file__),
        effective_uid=1000,
    )

    assert first.report == second.report
    assert set(tmp_path.iterdir()) == before
    assert first.report["mode"] == "dry_run_zero_writes"
    assert first.report["will_write"] is False
    assert first.report["will_execute_unreal"] is False
    assert first.report["accepted"] is False
    assert first.report["claims"] == executor.NEGATIVE_CLAIMS
    assert first.report["blockers"] == [
        "external_root_policy_bootstrap",
        "root_installed_executor_bundle_pins",
        "root_installed_executor_identity",
        "immutable_ue57_engine_authority_pins",
        "pinned_host_runtime_closure",
        "fresh_root_published_r8_authority_pins",
        "reviewed_root_buildplugin_authority_pins",
        "root_execution_and_publication_context",
    ]
    assert first.report["content_digest"] == executor.content_digest(first.report)


def test_execute_requires_exact_acknowledgement_before_authority_reads() -> None:
    with pytest.raises(executor.ExecutorError, match="exact animation-only"):
        executor.build_plan(
            ATTEMPT,
            execute=True,
            execution_acknowledgement="approved",
        )


def test_partial_authority_pins_never_unblock_execution() -> None:
    policy = dataclasses.replace(
        executor.PRODUCTION_POLICY,
        bundle_manifest_pin=executor.FilePin("a" * 64, 1),
        r8_attempt_name="makehuman-cc0-animation-r8-fresh-root-r1",
        plugin_root=Path("/authority/plugin"),
    )
    blockers = executor.authority_blockers(
        policy,
        running_executor_path=policy.executor_path,
        effective_uid=0,
    )
    assert "root_installed_executor_bundle_pins" in blockers
    assert "immutable_ue57_engine_authority_pins" in blockers
    assert "fresh_root_published_r8_authority_pins" in blockers
    assert "reviewed_root_buildplugin_authority_pins" in blockers


def test_external_root_policy_is_fixed_root_owned_bootstrap_not_self_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy_path = tmp_path / "root-policy.json"
    document = executor.seal_document(
        {
            "schema": executor.ROOT_POLICY_SCHEMA,
            "bundle_manifest_pin": _pin_document("1"),
            "bundle_manifest_content_digest": "2" * 64,
            "executor_pin": _pin_document("3"),
            "wrapper_pin": _pin_document("4"),
            "commandlet_pin": _pin_document("5"),
            "wrapper_python_pin": _pin_document("6"),
            "host_runtime": {
                "tree_digest": "7" * 64,
                "file_count": 1,
                "directory_count": 6,
                "total_bytes": 1,
            },
            "engine": {
                "manifest_pin": _pin_document("8"),
                "manifest_content_digest": "9" * 64,
                "tree_digest": "a" * 64,
                "critical_files": [
                    {
                        "relative_path": "Engine/Binaries/Linux/UnrealEditor-Cmd",
                        "sha256": "b" * 64,
                        "size_bytes": 1,
                        "executable": True,
                    }
                ],
            },
            "r3": {
                "receipt_pin": _pin_document("1"),
                "receipt_content_digest": "2" * 64,
                "project": {
                    "tree_digest": "3" * 64,
                    "file_count": 1,
                    "directory_count": 1,
                    "total_bytes": 1,
                },
            },
            "r8": {
                "attempt_name": "makehuman-cc0-animation-r8-fresh-root-r1",
                "receipt_pin": _pin_document("c"),
                "receipt_content_digest": "d" * 64,
            },
            "plugin": {
                "tree_digest": "e" * 64,
                "file_count": 1,
                "directory_count": 1,
                "total_bytes": 1,
            },
            "bwrap_pin": _pin_document("f"),
        }
    )
    policy_path.write_bytes(executor.canonical_json(document))
    monkeypatch.setattr(executor, "ROOT_POLICY_PATH", policy_path)
    monkeypatch.setattr(executor, "AUTHORITY_LSTAT", _trusted_root_lstat)

    policy = executor.load_root_policy()

    assert policy.policy_path == policy_path
    assert policy.policy_content_digest == document["content_digest"]
    assert policy.executor_pin == executor.FilePin("3" * 64, 1, True)
    assert policy.wrapper_python == Path("/usr/bin/python3.10")
    assert "policy_pin" not in document


def test_root_owned_authority_gate_is_valid_for_root_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()
    (authority / "sealed").write_bytes(b"bytes")
    monkeypatch.setattr(executor, "AUTHORITY_LSTAT", _trusted_root_lstat)
    monkeypatch.setattr(executor, "GETEUID", lambda: 0)

    executor._authority_chain(authority, "root caller authority")


def test_authority_tree_rejects_non_root_mutable_and_symlink_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()
    (authority / "file").write_bytes(b"sealed")

    def trusted_lstat(path: os.PathLike[str] | str) -> SimpleNamespace:
        info = os.lstat(path)
        mode = 0o555 if stat.S_ISDIR(info.st_mode) else 0o444
        return SimpleNamespace(
            st_mode=(stat.S_IFDIR if stat.S_ISDIR(info.st_mode) else stat.S_IFREG)
            | mode,
            st_uid=0,
            st_gid=0,
            st_size=info.st_size,
        )

    monkeypatch.setattr(executor, "AUTHORITY_LSTAT", trusted_lstat)
    snapshot = executor.snapshot_tree(
        authority, "fake authority", immutable_authority=True
    )
    assert (
        snapshot.by_relative()["file"].sha256 == hashlib.sha256(b"sealed").hexdigest()
    )

    monkeypatch.setattr(
        executor,
        "AUTHORITY_LSTAT",
        lambda path: SimpleNamespace(
            st_mode=stat.S_IFREG | 0o666,
            st_uid=1000,
            st_gid=1000,
            st_size=os.lstat(path).st_size,
        ),
    )
    with pytest.raises(executor.ExecutorError, match="not root-owned|writable"):
        executor.snapshot_tree(authority, "fake authority", immutable_authority=True)

    link = tmp_path / "link"
    link.symlink_to(authority, target_is_directory=True)
    with pytest.raises(executor.ExecutorError, match="symlink"):
        executor.snapshot_tree(link, "fake authority", immutable_authority=False)


def test_memfd_is_read_only_and_has_all_linux_seals() -> None:
    descriptor = executor._sealed_memfd("unit", b"immutable")
    try:
        expected = (
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE
        )
        assert fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) == expected
        assert os.pread(descriptor, 9, 0) == b"immutable"
        with pytest.raises(OSError):
            os.write(descriptor, b"x")
    finally:
        os.close(descriptor)


def test_bwrap_command_has_closed_mount_and_environment_surface() -> None:
    fds = {
        "bwrap": 10,
        "engine": 11,
        "plugin": 12,
        "python": 13,
        "host_runtime": 19,
        "execution": 14,
        "host_execution": 15,
        "wrapper": 16,
        "commandlet": 17,
        "source_receipt": 18,
        **{f"fbx:{index}": 20 + index for index, _ in enumerate(executor.CLIP_SPECS)},
        "r3:0": 30,
    }
    snapshot = executor.ImmutableSnapshot(
        fds=fds,
        r3_tokens={executor.PROJECT_FILE_NAME: "r3:0"},
    )
    plan = SimpleNamespace(
        authorities=SimpleNamespace(
            r3_project=SimpleNamespace(directories=(".", "EmptyDirectory"))
        )
    )
    command = executor.build_sandbox_command(plan, snapshot)  # type: ignore[arg-type]
    joined = " ".join(command)

    assert command[0] == "/proc/self/fd/10"
    assert "--unshare-all" in command
    assert "--share-net" not in command
    assert "--clearenv" in command
    assert "--ro-bind-data" in command
    assert "--ro-bind-fd" in command
    assert str(executor.SANDBOX_RUNTIME_ROOT) in command
    assert str(executor.SANDBOX_PYTHON_PATH) == "/usr/bin/python3.10"
    assert not any(
        command[index] == "--ro-bind" and command[index + 1] in {"/usr", "/etc"}
        for index in range(len(command) - 1)
    )
    assert str(executor.SANDBOX_R3_ROOT / "EmptyDirectory") in command
    assert "/dev/dri" not in joined
    assert "DISPLAY" not in command
    assert str(executor.PUBLISHED_PARENT) not in joined
    assert str(Path(executor.__file__).parents[3]) not in joined
    assert command[-4:] == (
        str(executor.SANDBOX_PYTHON_PATH),
        "-I",
        "-B",
        str(executor.SANDBOX_WRAPPER_PATH),
    )


def test_wrapper_and_host_share_exact_canonical_ustar_protocol() -> None:
    members = _archive_members()
    wrapped = wrapper.canonical_ustar(members)
    hosted = executor.canonical_ustar(members)

    assert wrapped == hosted
    assert executor.parse_canonical_ustar(wrapped) == members
    assert wrapped.endswith(b"\0" * 1024)


@pytest.mark.parametrize("mutation", ["link", "traversal", "duplicate", "trailing"])
def test_archive_parser_rejects_noncanonical_or_unsafe_input(mutation: str) -> None:
    archive = executor.canonical_ustar(_archive_members())
    if mutation == "link":
        changed = _replace_header_field(archive, 0, 156, 157, b"2")
    elif mutation == "traversal":
        changed = _replace_header_field(archive, 0, 0, 100, b"../escape")
    elif mutation == "duplicate":
        first_name = archive[:100].split(b"\0", 1)[0]
        first_size = int(archive[124:135], 8)
        second = 512 + ((first_size + 511) // 512) * 512
        changed = _replace_header_field(archive, second, 0, 100, first_name)
    else:
        changed = archive + b"\0" * 512

    with pytest.raises(executor.ExecutorError):
        executor.parse_canonical_ustar(changed)


def test_wrapper_manifest_binds_fixed_ue_command_and_execution_bytes() -> None:
    execution = _sealed(
        {
            "schema_version": wrapper.COMMANDLET_EXECUTION_SCHEMA,
            "mode": "apply",
            "execution_acknowledgement": wrapper.EXECUTION_ACKNOWLEDGEMENT,
            "attempt_root": str(wrapper.SANDBOX_WORK_ROOT),
            "project_root": str(wrapper.SANDBOX_PROJECT_ROOT),
            "project_file": str(wrapper.SANDBOX_PROJECT_FILE),
            "project_sha256": "1" * 64,
            "content_namespace": wrapper.CONTENT_NAMESPACE,
            "skeleton_object_path": wrapper.SKELETON_OBJECT_PATH,
            "mesh_object_path": wrapper.MESH_OBJECT_PATH,
            "source_host_receipt": {
                "path": str(wrapper.SOURCE_RECEIPT_PATH),
                "sha256": "2" * 64,
                "size_bytes": 2,
            },
            "source_fbx": [
                {
                    "clip_id": spec["clip_id"],
                    "path": str(
                        wrapper.SANDBOX_FBX_ROOT / f"{spec['sequence_name']}.fbx"
                    ),
                    "sha256": f"{index + 3:x}" * 64,
                    "size_bytes": index + 3,
                }
                for index, spec in enumerate(wrapper.CLIP_SPECS)
            ],
            "clip_specs": list(wrapper.CLIP_SPECS),
            "expected_inventory": list(wrapper.EXPECTED_INVENTORY),
            "commandlet": {
                "path": str(wrapper.COMMANDLET_PATH),
                "sha256": "8" * 64,
                "size_bytes": 8,
            },
            "import_receipt": str(wrapper.IMPORT_RECEIPT_PATH),
            "import_result": str(wrapper.IMPORT_RESULT_PATH),
            "claims": wrapper.NEGATIVE_CLAIMS,
        }
    )
    execution_raw = wrapper.canonical_json(execution)
    host = _sealed(
        {
            "schema": wrapper.HOST_EXECUTION_SCHEMA,
            "root_policy": {
                "path": str(wrapper.ROOT_POLICY_PATH),
                "content_digest": "9" * 64,
            },
            "engine": {
                "root": str(wrapper.SANDBOX_ENGINE_ROOT),
                "manifest_content_digest": "a" * 64,
                "tree_digest": "b" * 64,
                "build_id": "1234",
            },
            "host_runtime": {
                "root": str(wrapper.SANDBOX_RUNTIME_ROOT),
                "tree_digest": "c" * 64,
                "directory_count": 1,
                "file_count": 1,
                "total_bytes": 1,
            },
            "r3_project": {
                "root": str(wrapper.SANDBOX_R3_ROOT),
                "tree_digest": "d" * 64,
                "directory_count": 2,
                "file_count": 0,
                "total_bytes": 0,
                "directories": [".", "EmptyDirectory"],
                "files": [],
            },
            "plugin": {
                "root": str(wrapper.SANDBOX_PLUGIN_ROOT),
                "tree_digest": "e" * 64,
                "directory_count": 1,
                "file_count": 0,
                "total_bytes": 0,
                "directories": ["."],
                "files": [],
            },
            "commandlet_execution": {
                "path": str(wrapper.COMMANDLET_EXECUTION_PATH),
                "sha256": hashlib.sha256(execution_raw).hexdigest(),
                "content_digest": execution["content_digest"],
                "size_bytes": len(execution_raw),
            },
            "ue_command": wrapper.fixed_ue_command(),
            "expected_archive_paths": list(wrapper.EXPECTED_ARCHIVE_PATHS),
            "expected_project_delta": list(wrapper.EXPECTED_PACKAGE_PATHS),
            "claims": wrapper.NEGATIVE_CLAIMS,
        }
    )
    host_raw = wrapper.canonical_json(host)
    assert wrapper.validate_manifests(host_raw, execution_raw) == (host, execution)

    changed = dict(host)
    changed.pop("content_digest")
    changed["ue_command"] = ["/caller/chosen/UnrealEditor"]
    changed = _sealed(changed)
    with pytest.raises(wrapper.WrapperError, match="closed contract"):
        wrapper.validate_manifests(wrapper.canonical_json(changed), execution_raw)

    extra_execution = dict(execution)
    extra_execution.pop("content_digest")
    extra_execution["caller_override"] = "forbidden"
    extra_execution = _sealed(extra_execution)
    extra_raw = wrapper.canonical_json(extra_execution)
    rebound_host = dict(host)
    rebound_host.pop("content_digest")
    rebound_host["commandlet_execution"] = {
        "path": str(wrapper.COMMANDLET_EXECUTION_PATH),
        "sha256": hashlib.sha256(extra_raw).hexdigest(),
        "content_digest": extra_execution["content_digest"],
        "size_bytes": len(extra_raw),
    }
    rebound_host = _sealed(rebound_host)
    with pytest.raises(wrapper.WrapperError, match="commandlet execution"):
        wrapper.validate_manifests(wrapper.canonical_json(rebound_host), extra_raw)

    numeric_host_claim = json.loads(json.dumps(host))
    numeric_host_claim.pop("content_digest")
    numeric_host_claim["claims"]["gta_level_quality"] = 0
    numeric_host_claim = _sealed(numeric_host_claim)
    with pytest.raises(wrapper.WrapperError, match="host execution"):
        wrapper.validate_manifests(
            wrapper.canonical_json(numeric_host_claim), execution_raw
        )

    numeric_loop = json.loads(json.dumps(execution))
    numeric_loop.pop("content_digest")
    numeric_loop["clip_specs"][0]["loop"] = 1
    numeric_loop = _sealed(numeric_loop)
    numeric_loop_raw = wrapper.canonical_json(numeric_loop)
    rebound_numeric_loop = json.loads(json.dumps(host))
    rebound_numeric_loop.pop("content_digest")
    rebound_numeric_loop["commandlet_execution"] = {
        "path": str(wrapper.COMMANDLET_EXECUTION_PATH),
        "sha256": hashlib.sha256(numeric_loop_raw).hexdigest(),
        "content_digest": numeric_loop["content_digest"],
        "size_bytes": len(numeric_loop_raw),
    }
    rebound_numeric_loop = _sealed(rebound_numeric_loop)
    with pytest.raises(wrapper.WrapperError, match="commandlet execution"):
        wrapper.validate_manifests(
            wrapper.canonical_json(rebound_numeric_loop), numeric_loop_raw
        )


def test_wrapper_and_host_validate_the_exact_terminal_receipt_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, _ = _complete_fake_plan(tmp_path, monkeypatch)
    members = _terminal_members(plan)
    package_payloads = {
        relative: members["project/" + relative]
        for relative in executor.EXPECTED_PACKAGE_PATHS
    }

    wrapper_receipt, wrapper_result = wrapper._validate_receipt_and_result(
        members[executor.ARCHIVE_RECEIPT_PATH],
        members[executor.ARCHIVE_RESULT_PATH],
        plan.host_execution,
        plan.commandlet_execution,
        package_payloads,
    )
    host_receipt, host_result = executor.validate_captured_members(plan, members)

    assert wrapper_receipt == host_receipt
    assert wrapper_result == host_result
    assert len(host_receipt["gates"]) == 17
    assert all(len(item) == 6 for item in host_receipt["package_inventory"])


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_gate",
        "gate_true_as_one",
        "gate_false_as_zero",
        "claim_true_as_one",
        "extra_top_level",
        "incomplete_package",
        "package_binding",
        "binding_extra",
        "returned_object_paths",
        "pipeline_policies",
        "pipeline_false_as_zero",
        "sequence_inspection",
        "runtime_authoring_result",
        "runtime_false_as_zero",
        "asset_inventory",
        "project_content_delta",
        "content_delta_true_as_one",
    ),
)
def test_wrapper_and_host_reject_semantically_forged_terminal_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    plan, _ = _complete_fake_plan(tmp_path, monkeypatch)
    members = _mutate_terminal_receipt(_terminal_members(plan), mutation)
    package_payloads = {
        relative: members["project/" + relative]
        for relative in executor.EXPECTED_PACKAGE_PATHS
    }

    with pytest.raises(wrapper.WrapperError):
        wrapper._validate_receipt_and_result(
            members[executor.ARCHIVE_RECEIPT_PATH],
            members[executor.ARCHIVE_RESULT_PATH],
            plan.host_execution,
            plan.commandlet_execution,
            package_payloads,
        )
    with pytest.raises(executor.ExecutorError):
        executor.validate_captured_members(plan, members)


def test_wrapper_preserves_declared_empty_directories(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    (source / "EmptyDirectory").mkdir(parents=True)
    (source / "Nested/Vacant").mkdir(parents=True)
    payload = b"sealed input"
    (source / "Nested/file.bin").write_bytes(payload)
    section: dict[str, object] = {
        "root": str(source),
        "tree_digest": "0" * 64,
        "directory_count": 4,
        "file_count": 1,
        "total_bytes": len(payload),
        "directories": [".", "EmptyDirectory", "Nested", "Nested/Vacant"],
        "files": [
            {
                "relative_path": "Nested/file.bin",
                "path": str(source / "Nested/file.bin"),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        ],
    }
    section["tree_digest"] = wrapper._tree_digest(section)

    wrapper._copy_manifest_tree(section, source, destination, "fake tree")

    assert (destination / "EmptyDirectory").is_dir()
    assert (destination / "Nested/Vacant").is_dir()
    assert (destination / "Nested/file.bin").read_bytes() == payload


def test_pretty_byte_pinned_ue_module_json_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin = tmp_path / "plugin"
    binaries = plugin / "Binaries/Linux"
    binaries.mkdir(parents=True)
    descriptor = {
        "Modules": [
            {"Name": "VistaPlayableHome"},
            {"Name": "VistaPlayableHomeEditor"},
        ]
    }
    modules = {
        "BuildId": "123456",
        "Modules": {
            "VistaPlayableHome": "libUnrealEditor-VistaPlayableHome.so",
            "VistaPlayableHomeEditor": "libUnrealEditor-VistaPlayableHomeEditor.so",
        },
    }
    (plugin / "VistaPlayableHome.uplugin").write_text(
        __import__("json").dumps(descriptor, indent=2) + "\n", encoding="utf-8"
    )
    (binaries / "UnrealEditor.modules").write_text(
        __import__("json").dumps(modules, indent=4) + "\n", encoding="utf-8"
    )
    for name in (
        "libUnrealEditor-VistaPlayableHome.so",
        "libUnrealEditor-VistaPlayableHomeEditor.so",
    ):
        (binaries / name).write_bytes(b"\x7fELFfake")
    tree = executor.snapshot_tree(plugin, "fake plugin", immutable_authority=False)
    policy = dataclasses.replace(
        executor.PRODUCTION_POLICY,
        plugin_root=plugin,
        plugin_tree_digest=tree.sha256,
        plugin_file_count=len(tree.files),
        plugin_directory_count=len(tree.directories),
        plugin_total_bytes=tree.total_bytes,
    )
    monkeypatch.setattr(
        executor,
        "snapshot_tree",
        lambda *args, **kwargs: tree,
    )

    assert executor._validate_plugin(policy, "123456") == tree


def test_archive_limit_is_checked_cumulatively_before_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    members = _archive_members()
    monkeypatch.setattr(executor, "MAX_ARCHIVE_BYTES", 7_000)
    monkeypatch.setattr(wrapper, "MAX_ARCHIVE_BYTES", 7_000)

    with pytest.raises(executor.ExecutorError, match="cumulative"):
        executor.canonical_ustar(members)
    with pytest.raises(wrapper.WrapperError, match="cumulative"):
        wrapper.canonical_ustar(members)


def test_supervisor_kills_and_waits_child_on_setup_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePipe:
        def __init__(self, descriptor: int) -> None:
            self.descriptor = descriptor
            self.closed = False

        def fileno(self) -> int:
            return self.descriptor

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 4242
            self.stdout = FakePipe(101)
            self.stderr = FakePipe(102)
            self.return_code: int | None = None
            self.wait_calls = 0

        def poll(self) -> int | None:
            return self.return_code

        def wait(self, timeout: float | None = None) -> int:
            self.wait_calls += 1
            self.return_code = -9
            return self.return_code

        def kill(self) -> None:
            self.return_code = -9

    process = FakeProcess()
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(executor.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        executor.selectors,
        "DefaultSelector",
        lambda: (_ for _ in ()).throw(RuntimeError("selector setup failed")),
    )
    monkeypatch.setattr(
        executor.os, "killpg", lambda pid, sig: killed.append((pid, sig))
    )

    with pytest.raises(RuntimeError, match="selector setup failed"):
        executor.capture_bounded_child(
            ["/never/executed"], pass_fds=(), timeout_seconds=30.0
        )

    assert killed == [(4242, executor.signal.SIGKILL)]
    assert process.wait_calls == 1
    assert process.stdout.closed and process.stderr.closed


def test_supervisor_cleanup_failures_never_mask_the_primary_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PrimaryFailure(RuntimeError):
        pass

    class FakePipe:
        def __init__(self, descriptor: int) -> None:
            self.descriptor = descriptor
            self.closed = False

        def fileno(self) -> int:
            return self.descriptor

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 5151
            self.stdout = FakePipe(201)
            self.stderr = FakePipe(202)
            self.kill_calls = 0
            self.wait_calls = 0

        def poll(self) -> None:
            return None

        def kill(self) -> None:
            self.kill_calls += 1
            raise OSError("fallback kill failed")

        def wait(self, timeout: float | None = None) -> int:
            self.wait_calls += 1
            raise OSError("wait failed")

    process = FakeProcess()
    monkeypatch.setattr(executor.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        executor.selectors,
        "DefaultSelector",
        lambda: (_ for _ in ()).throw(PrimaryFailure("primary setup failed")),
    )
    monkeypatch.setattr(
        executor.os,
        "killpg",
        lambda pid, sig: (_ for _ in ()).throw(OSError("killpg failed")),
    )

    with pytest.raises(PrimaryFailure, match="primary setup failed"):
        executor.capture_bounded_child(
            ["/never/executed"], pass_fds=(), timeout_seconds=30.0
        )

    assert process.kill_calls == 2
    assert process.wait_calls == 2
    assert process.stdout.closed and process.stderr.closed


def test_complete_fake_root_policy_validates_and_binds_actual_sandbox_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, paths = _complete_fake_plan(tmp_path, monkeypatch)

    assert plan.authorities.wrapper_python.path.name == "python3.10"
    assert plan.authorities.host_runtime.sha256 == (
        plan.dry_plan.policy.host_runtime_tree_digest
    )
    assert "Content/EmptyDirectory" in plan.authorities.r3_project.directories
    assert plan.host_execution["r3_project"]["directories"] == list(
        plan.authorities.r3_project.directories
    )
    assert wrapper.validate_manifests(
        plan.host_execution_raw, plan.commandlet_execution_raw
    ) == (plan.host_execution, plan.commandlet_execution)
    assert paths["r3_empty"].is_dir()

    with executor.immutable_snapshot(plan) as snapshot:
        command = executor.build_sandbox_command(plan, snapshot)
        assert snapshot.fds["host_runtime"] in snapshot.pass_fds
        assert str(executor.SANDBOX_R3_ROOT / "Content/EmptyDirectory") in command
        assert not any(
            command[index] == "--ro-bind" and command[index + 1] in {"/usr", "/etc"}
            for index in range(len(command) - 1)
        )
        assert plan.launch_document["normalized_bwrap_command"] == (
            executor._normalized_sandbox_command(plan.authorities)
        )
        for key in (
            "execution",
            "host_execution",
            "wrapper",
            "commandlet",
            "source_receipt",
        ):
            seals = fcntl.fcntl(snapshot.fds[key], fcntl.F_GET_SEALS)
            assert seals & fcntl.F_SEAL_WRITE
            assert seals & fcntl.F_SEAL_SEAL


def test_same_uid_r3_mutation_is_rejected_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, paths = _complete_fake_plan(tmp_path, monkeypatch)
    paths["r3_base"].write_bytes(b"mutated after validation")

    with pytest.raises(
        executor.ExecutorError, match="changed after authority validation"
    ):
        with executor.immutable_snapshot(plan):
            pytest.fail("mutated R3 file must not reach sandbox launch")


def test_fake_publication_preserves_empty_dirs_and_fsyncs_after_final_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, _ = _complete_fake_plan(tmp_path, monkeypatch)
    members = _archive_members()
    archive = executor.canonical_ustar(members)
    regular_sync_modes: list[int] = []
    directory_sync_modes: list[int] = []
    real_regular_fsync = executor._fsync_regular
    real_directory_fsync = executor._fsync_directory

    def record_regular(path: Path) -> None:
        regular_sync_modes.append(stat.S_IMODE(path.stat().st_mode))
        real_regular_fsync(path)

    def record_directory(path: Path) -> None:
        if path.exists():
            directory_sync_modes.append(stat.S_IMODE(path.stat().st_mode))
        real_directory_fsync(path)

    monkeypatch.setattr(executor, "_fsync_regular", record_regular)
    monkeypatch.setattr(executor, "_fsync_directory", record_directory)
    monkeypatch.setattr(executor, "RENAME_NOREPLACE", os.rename)

    with executor.immutable_snapshot(plan) as snapshot:
        receipt = executor.publish_validated(
            plan,
            snapshot,
            members,
            archive,
            b"diagnostics",
            {"content_digest": "a" * 64},
            {"receipt_sha256": "b" * 64},
            require_root=False,
        )

    final = plan.dry_plan.policy.published_parent / ATTEMPT
    assert receipt["accepted"] is False
    assert (final / "project/Content/EmptyDirectory").is_dir()
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in final.rglob("*")
        if path.is_file()
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o555
        for path in (final, *[item for item in final.rglob("*") if item.is_dir()])
    )
    assert regular_sync_modes and set(regular_sync_modes) == {0o444}
    assert 0o555 in directory_sync_modes


def test_post_rename_parent_fsync_failure_removes_final_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, _ = _complete_fake_plan(tmp_path, monkeypatch)
    members = _archive_members()
    parent = plan.dry_plan.policy.published_parent
    final = parent / ATTEMPT
    real_directory_fsync = executor._fsync_directory
    parent_fsync_calls = 0

    def fail_second_parent_fsync(path: Path) -> None:
        nonlocal parent_fsync_calls
        if path == parent:
            parent_fsync_calls += 1
            if parent_fsync_calls == 2:
                raise OSError("post-rename parent fsync failed")
        real_directory_fsync(path)

    monkeypatch.setattr(executor, "_fsync_directory", fail_second_parent_fsync)
    monkeypatch.setattr(executor, "RENAME_NOREPLACE", os.rename)

    with executor.immutable_snapshot(plan) as snapshot:
        with pytest.raises(OSError, match="post-rename"):
            executor.publish_validated(
                plan,
                snapshot,
                members,
                executor.canonical_ustar(members),
                b"diagnostics",
                {"content_digest": "a" * 64},
                {"receipt_sha256": "b" * 64},
                require_root=False,
            )

    assert parent_fsync_calls >= 3
    assert not os.path.lexists(final)
    assert not any(
        path.name.startswith(f".{ATTEMPT}.staging-") for path in parent.iterdir()
    )
