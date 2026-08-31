from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.ue.vista_playable_home import build_home
from tools.ue.vista_playable_home import (
    makehuman_cc0_detail_actions_r14_contract as contract,
)
from tools.ue.vista_playable_home import (
    run_makehuman_cc0_detail_actions_r14_import as runner,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMMANDLET = (
    REPOSITORY_ROOT
    / "tools/ue/vista_playable_home/makehuman_cc0_detail_actions_r14_commandlet.py"
)
EDITOR_PUBLIC = (
    REPOSITORY_ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/Public"
)
EDITOR_PRIVATE = EDITOR_PUBLIC.parent / "Private"


def write(path: Path, raw: bytes, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o755 if executable else 0o644)


def canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def sealed(value: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(value)
    result["content_digest"] = runner.content_digest(result)
    return result


def fake_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[runner.Config, runner.PluginAuthority]:
    run_parent = tmp_path / "runs"
    source_root = run_parent / "source-r14"
    r3_root = run_parent / "r3/project"
    plugin_root = run_parent / "build-r14/VistaPlayableHome"
    engine_root = tmp_path / "engine"
    engine = engine_root / "Engine/Binaries/Linux/UnrealEditor-Cmd"
    bwrap = tmp_path / "bin/bwrap"
    commandlet = tmp_path / "source/commandlet.py"

    clip_specs: list[dict[str, object]] = []
    artifacts: list[dict[str, object]] = []
    for index, original in enumerate(contract.CLIP_SPECS):
        raw = f"fbx-{index}".encode()
        spec = copy.deepcopy(original)
        spec["source_sha256"] = hashlib.sha256(raw).hexdigest()
        spec["source_size_bytes"] = len(raw)
        clip_specs.append(spec)
        relative = "fbx/" + str(spec["source_name"])
        write(source_root / "artifacts" / relative, raw)
        artifacts.append(
            {
                "relative_path": relative,
                "sha256": spec["source_sha256"],
                "size_bytes": len(raw),
            }
        )
    monkeypatch.setattr(contract, "CLIP_SPECS", tuple(clip_specs))
    monkeypatch.setattr(
        contract,
        "EXPECTED_INVENTORY",
        tuple(
            {
                "class_path": "/Script/Engine.AnimSequence",
                "object_path": (
                    f"{contract.SEQUENCE_NAMESPACE}/{item['sequence_name']}."
                    f"{item['sequence_name']}"
                ),
            }
            for item in clip_specs
        )
        + tuple(
            {
                "class_path": "/Script/Engine.AnimMontage",
                "object_path": (
                    f"{contract.MONTAGE_NAMESPACE}/{item['montage_name']}."
                    f"{item['montage_name']}"
                ),
            }
            for item in clip_specs
        ),
    )

    source_receipt = sealed(
        {
            "schema_version": contract.SOURCE_RECEIPT_SCHEMA,
            "status": "fresh_cc0_detail_action_candidates_roundtrip_verified",
            "accepted": False,
            "plan_content_digest": contract.SOURCE_PLAN_CONTENT_DIGEST,
            "profile_content_digest": contract.SOURCE_PROFILE_CONTENT_DIGEST,
            "artifacts": artifacts,
            "gates": {
                "fbx_roundtrip_verified": True,
                "exact_53_bone_contract": True,
            },
            "claims": {"ue_animation_imported": False},
        }
    )
    source_receipt_path = source_root / "evidence/worker-receipt.json"
    write(source_receipt_path, canonical(source_receipt))
    monkeypatch.setattr(
        runner,
        "SOURCE_RECEIPT_SHA256",
        hashlib.sha256(source_receipt_path.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(runner, "SOURCE_RECEIPT_SIZE", source_receipt_path.stat().st_size)
    monkeypatch.setattr(
        runner, "SOURCE_CONTENT_DIGEST", source_receipt["content_digest"]
    )

    write(r3_root / runner.PROJECT_FILE_NAME, b'{"FileVersion":3}\n')
    write(r3_root / "Content/VISTA/MakeHumanCC0/R6/Skeleton.uasset", b"skeleton")
    r3_tree = build_home.snapshot_tree(r3_root, "fake R3")
    r3_package = next(item for item in r3_tree.records if item[0].endswith(".uasset"))
    r3_receipt = {
        "schema_version": "vista.makehuman-cc0-ue57-import-host-receipt/v1",
        "status": "cc0_skeletal_import_post_exit_project_sealed",
        "accepted": False,
        "content_digest": "c" * 64,
        "output_project_projection": {
            "sha256": "p" * 64,
            "file_count": r3_tree.file_count,
            "directory_count": 3,
            "total_bytes": r3_tree.total_bytes,
        },
        "package_inventory": [
            {
                "project_relative_path": r3_package[0],
                "size_bytes": r3_package[2],
                "sha256": r3_package[3],
            }
        ],
        "claims": {
            "ue_skeletal_imported": True,
            "exact_53_bones_verified": True,
        },
    }
    r3_receipt_path = r3_root.parent.parent / "receipt.json"
    write(r3_receipt_path, json.dumps(r3_receipt, indent=2).encode() + b"\n")
    monkeypatch.setattr(
        runner,
        "R3_RECEIPT_SHA256",
        hashlib.sha256(r3_receipt_path.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(runner, "R3_RECEIPT_SIZE", r3_receipt_path.stat().st_size)
    monkeypatch.setattr(runner, "R3_RECEIPT_CONTENT_DIGEST", "c" * 64)
    monkeypatch.setattr(runner, "R3_PROJECT_PROJECTION", r3_receipt["output_project_projection"])

    write(engine, b"#!/bin/sh\n", executable=True)
    write(bwrap, b"#!/bin/sh\n", executable=True)
    write(commandlet, b"# commandlet\n")
    monkeypatch.setattr(
        runner,
        "UNREAL_EDITOR_CMD_PIN",
        (hashlib.sha256(engine.read_bytes()).hexdigest(), engine.stat().st_size),
    )
    monkeypatch.setattr(
        runner,
        "BWRAP_PIN",
        (hashlib.sha256(bwrap.read_bytes()).hexdigest(), bwrap.stat().st_size),
    )

    write(plugin_root / "VistaPlayableHome.uplugin", b"{}\n")
    write(
        plugin_root / "Binaries/Linux/UnrealEditor.modules",
        json.dumps(
            {
                "Modules": {
                    "VistaPlayableHome": "libUnrealEditor-VistaPlayableHome.so",
                    "VistaPlayableHomeEditor": (
                        "libUnrealEditor-VistaPlayableHomeEditor.so"
                    ),
                }
            }
        ).encode()
        + b"\n",
    )
    write(
        plugin_root / "Binaries/Linux/libUnrealEditor-VistaPlayableHome.so",
        b"runtime",
    )
    write(
        plugin_root / "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so",
        b"editor-r14",
    )
    plugin_tree = build_home.snapshot_tree(plugin_root, "fake plugin")
    authority = runner.PluginAuthority(
        plugin_root,
        plugin_tree.sha256,
        plugin_tree.file_count,
        plugin_tree.total_bytes,
    )
    config = runner.Config(
        run_parent=run_parent,
        source_root=source_root,
        source_receipt=source_receipt_path,
        r3_project_root=r3_root,
        r3_receipt=r3_receipt_path,
        engine_root=engine_root,
        unreal_editor_cmd=engine,
        bwrap=bwrap,
        commandlet=commandlet,
    )
    return config, authority


def test_contract_pins_exact_source_receipt_and_three_fbx() -> None:
    assert contract.SOURCE_RECEIPT_SHA256 == (
        "b142912fcf9d8a195c173d60064992b2f323c9208b467109af817134c26e3ed3"
    )
    assert contract.SOURCE_RECEIPT_SIZE == 5032
    assert contract.SOURCE_CONTENT_DIGEST == (
        "afe84bfaf120006c99e44c2f05531d759f538e193b03889a88334f752c6f2a12"
    )
    assert contract.CONTENT_NAMESPACE == "/Game/VISTA/MakeHumanCC0/R14/DetailActions"
    assert [item["clip_id"] for item in contract.CLIP_SPECS] == [
        "fridge_open_right",
        "fridge_close_right",
        "object_inspect_right",
    ]
    assert len(contract.EXPECTED_INVENTORY) == 6


def test_ue_contract_projects_the_checked_in_r14_profile_exactly() -> None:
    profile = json.loads(
        (
            REPOSITORY_ROOT
            / "world_packs/vista_playable_home_r1/animation_profiles/"
            "makehuman_cc0_detail_actions_r14.json"
        ).read_text(encoding="utf-8")
    )
    assert profile["namespace_contract"]["ue_content_namespace"] == (
        contract.CONTENT_NAMESPACE
    )
    profile_by_id = {item["clip_id"]: item for item in profile["clips"]}
    for spec in contract.CLIP_SPECS:
        source = profile_by_id[spec["clip_id"]]
        for key in (
            "clip_id",
            "frame_start",
            "frame_end",
            "fps",
            "loop",
            "typed_notifies",
        ):
            assert spec[key] == source[key]
        assert spec["sequence_name"] == source["ue_sequence_name"]
        assert spec["montage_name"] == source["ue_montage_name"]


def test_closed_editor_bridge_authors_only_fixed_sequences_and_montages() -> None:
    header = (
        EDITOR_PUBLIC / "VistaPlayableHomeCc0DetailActionLibrary.h"
    ).read_text(encoding="utf-8")
    source = (
        EDITOR_PRIVATE / "VistaPlayableHomeCc0DetailActionLibrary.cpp"
    ).read_text(encoding="utf-8")

    assert "AuthorMakeHumanCc0R14DetailActionMontages();" in header
    assert "InspectMakeHumanCc0R14DetailActionAssets();" in header
    assert "FString ObjectPath" in source
    assert "PackageIsFresh" in source
    assert "CreateSlotAnimationAsDynamicMontage" in source
    assert "FAnimSlotGroup::DefaultSlotName" in source
    assert "26.0F / 30.0F" in source
    assert "24.0F / 30.0F" in source
    assert "66.0F / 30.0F" in source
    assert "88.0F / 30.0F" in source
    for signal in (
        "vista_fridge_door_handle_contact",
        "vista_fridge_open_completed",
        "vista_fridge_close_completed",
        "vista_inspect_completed",
    ):
        assert signal in source
    assert "Writer->WriteValue(TEXT(\"accepted\"), false)" in source
    assert "FString PackagePath" not in header
    assert "FString ObjectPath" not in header


def test_commandlet_is_closed_animation_only_and_cold_reloads_six_assets() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")

    compile(source, str(COMMANDLET), "exec")
    for token in (
        '"import_static_meshes", False',
        '"import_skeletal_meshes", False',
        '"import_only_animations", True',
        '"import_materials", False',
        '"import_textures", False',
        "RootMotionRootLock.REF_POSE",
        "exact six-asset namespace inventory differs",
        "reload_packages",
        "author_make_human_cc0r14_detail_action_montages",
        "inspect_make_human_cc0r14_detail_action_assets",
    ):
        assert token in source
    assert "SOURCE_RECEIPT_SHA256" in source
    assert "SOURCE_CONTENT_DIGEST" in source
    assert "run()" in source


def test_commandlet_and_host_share_the_same_immutable_contract_values() -> None:
    syntax = ast.parse(COMMANDLET.read_text(encoding="utf-8"))
    names = {
        "EXECUTION_SCHEMA",
        "RECEIPT_SCHEMA",
        "RESULT_SCHEMA",
        "SUCCESS_STATUS",
        "EXECUTION_ENV",
        "EXECUTION_SHA_ENV",
        "EXECUTION_ACKNOWLEDGEMENT",
        "CONTENT_NAMESPACE",
        "SKELETON_OBJECT_PATH",
        "MESH_OBJECT_PATH",
        "SOURCE_RECEIPT_SCHEMA",
        "SOURCE_RECEIPT_SHA256",
        "SOURCE_RECEIPT_SIZE",
        "SOURCE_CONTENT_DIGEST",
        "SOURCE_PLAN_CONTENT_DIGEST",
        "SOURCE_PROFILE_CONTENT_DIGEST",
        "CLIP_SPECS",
        "NEGATIVE_CLAIMS",
    }
    observed: dict[str, object] = {}
    for node in syntax.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in names:
            observed[target.id] = ast.literal_eval(node.value)

    assert set(observed) == names
    for name, value in observed.items():
        assert value == getattr(contract, name), name


def test_fake_plan_is_zero_write_and_requires_complete_plugin_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, authority = fake_config(tmp_path, monkeypatch)
    attempt = "makehuman-cc0-detail-actions-r14-ue57-dev-r1-unit"

    blocked = runner.build_plan(attempt, config=config)
    assert blocked.report["status"] == runner.BLOCKED_STATUS
    assert blocked.report["writes_performed"] is False
    assert blocked.report["will_run_unreal"] is False
    assert not blocked.attempt_root.exists()

    ready = runner.build_plan(attempt, plugin_authority=authority, config=config)
    assert ready.report["status"] == "ready_for_cpu_only_dev_import"
    assert ready.report["compiled_plugin"]["tree_sha256"] == authority.tree_sha256
    assert ready.report["source"]["worker_receipt_content_digest"] == (
        runner.SOURCE_CONTENT_DIGEST
    )
    assert ready.report["content_digest"] == runner.content_digest(ready.report)
    assert len(ready.report["expected_inventory"]) == 6
    assert not ready.attempt_root.exists()


def test_partial_plugin_authority_fails_closed() -> None:
    with pytest.raises(runner.DetailActionImportError, match="all plugin pins"):
        runner.plugin_authority_from_values("/tmp/plugin", None, 4, 100)


def test_execution_manifest_and_sandbox_preserve_fixed_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, authority = fake_config(tmp_path, monkeypatch)
    plan = runner.build_plan(
        "makehuman-cc0-detail-actions-r14-ue57-dev-r1-command",
        plugin_authority=authority,
        config=config,
    )
    receipt = runner.FileSeal(Path("/tmp/receipt"), "a" * 64, 11)
    commandlet = runner.FileSeal(Path("/tmp/commandlet"), "b" * 64, 12)
    descriptor = runner.FileSeal(Path("/tmp/project"), "c" * 64, 13)
    sources = tuple(
        (
            spec,
            runner.FileSeal(
                Path("/tmp") / str(spec["source_name"]),
                str(spec["source_sha256"]),
                int(spec["source_size_bytes"]),
            ),
        )
        for spec in contract.CLIP_SPECS
    )
    execution = runner.commandlet_execution(
        descriptor, receipt, sources, commandlet
    )

    assert execution["content_namespace"] == contract.CONTENT_NAMESPACE
    assert execution["skeleton_object_path"] == contract.SKELETON_OBJECT_PATH
    assert execution["source_worker_receipt"]["content_digest"] == (
        runner.SOURCE_CONTENT_DIGEST
    )
    assert len(execution["source_fbx"]) == 3
    assert execution["claims"] == contract.NEGATIVE_CLAIMS
    assert execution["content_digest"] == runner.content_digest(execution)

    command = runner.bwrap_command(plan, tmp_path / "input", "d" * 64)
    assert "--unshare-net" in command
    assert "-nullrhi" in command
    assert "-DDC-ForceMemoryCache" in command
    assert "-ExecutePythonScript=/vista/input/commandlet.py" in command
    assert not any(token.startswith("CUDA_VISIBLE_DEVICES") for token in command)
