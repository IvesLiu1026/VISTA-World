from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.ue.vista_playable_home import build_home
from tools.ue.vista_playable_home import (
    materialize_makehuman_cc0_animation_runtime as sealed_contract,
)
from tools.ue.vista_playable_home import (
    run_makehuman_cc0_animation_dev_demo as runner,
)


IMPORT_NAME = "makehuman-cc0-animation-ue57-dev-r1-pytest"
OVERLAY_NAME = "hssd-r2-makehuman-action-dev-r1-pytest"


def _seal(path: Path, character: str = "a", size_bytes: int = 1) -> runner.FileSeal:
    return runner.FileSeal(path, character * 64, size_bytes)


def _tree() -> build_home.TreeSnapshot:
    return build_home.TreeSnapshot("b" * 64, 241, 51_750_166, ())


def _fake_config(tmp_path: Path) -> runner.DevConfig:
    run_parent = tmp_path / "runs"
    run_parent.mkdir()
    return dataclasses.replace(
        runner.PRODUCTION_CONFIG,
        run_parent=run_parent,
        engine_root=tmp_path / "engine",
        unreal_editor_cmd=tmp_path / "engine/Engine/Binaries/Linux/UnrealEditor-Cmd",
        unreal_editor=tmp_path / "engine/Engine/Binaries/Linux/UnrealEditor",
        bwrap=tmp_path / "bin/bwrap",
        rsync=tmp_path / "bin/rsync",
    )


def _stub_import_validators(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    r3_packages = tuple(
        {
            "project_relative_path": f"Content/VISTA/MakeHumanCC0/R6/P{index}.uasset",
            "sha256": "1" * 64,
            "size_bytes": 1,
        }
        for index in range(23)
    )
    source_fbx = tuple(
        (spec, _seal(tmp_path / f"{spec['sequence_name']}.fbx", "2", 2))
        for spec in sealed_contract.CLIP_SPECS
    )
    monkeypatch.setattr(
        runner,
        "_validate_r3",
        lambda config: ({"content_digest": "3" * 64}, r3_packages),
    )
    monkeypatch.setattr(
        runner,
        "_validate_source",
        lambda config: (
            {"content_digest": "4" * 64},
            _seal(tmp_path / "host-receipt.json", "4", 4),
            source_fbx,
        ),
    )
    monkeypatch.setattr(
        runner,
        "_validate_r6_plugin",
        lambda config: ({"accepted": False}, _tree()),
    )
    monkeypatch.setattr(
        runner,
        "_validate_tool",
        lambda path, pin, label: runner.FileSeal(path, pin.sha256, pin.size_bytes),
    )
    monkeypatch.setattr(
        runner,
        "_commandlet_seal",
        lambda config: _seal(tmp_path / "commandlet.py", "5", 5),
    )
    monkeypatch.setattr(
        runner,
        "_git_source",
        lambda: {"commit": "6" * 40, "clean": False, "authority": False},
    )


def _fake_import_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[runner.DevConfig, runner.ImportPlan]:
    config = _fake_config(tmp_path)
    _stub_import_validators(monkeypatch, tmp_path)
    return config, runner.build_import_plan(IMPORT_NAME, config=config)


def test_import_plan_is_zero_write_and_explicitly_nonpromotable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, plan = _fake_import_plan(tmp_path, monkeypatch)

    assert not plan.attempt_root.exists()
    assert plan.attempt_root == config.run_parent / IMPORT_NAME
    assert plan.report["mode"] == "dry_run_zero_writes"
    assert plan.report["writes_performed"] is False
    assert plan.report["will_run_unreal"] is False
    assert plan.report["interactive_renderer_allowed"] is False
    assert plan.report["gpu_allowed"] is False
    assert plan.report["network_allowed"] is False
    assert plan.report["accepted"] is False
    assert plan.report["claims"] == runner.DEV_CLAIMS
    assert plan.report["claims"]["human_operated_development_only"] is True
    assert plan.report["claims"]["nonpromotable"] is True
    assert plan.report["claims"]["accepted_research_evidence"] is False
    assert plan.report["expected_assets"] == list(
        sealed_contract.EXPECTED_NAMESPACE_INVENTORY
    )
    assert plan.report["content_digest"] == runner._content_digest(plan.report)
    assert plan.report["future_execute_argv"][-1] == runner.IMPORT_ACKNOWLEDGEMENT


def test_import_execute_requires_literal_ack_before_creating_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, plan = _fake_import_plan(tmp_path, monkeypatch)

    with pytest.raises(runner.DevDemoError, match="exact development import"):
        runner.execute_import(plan, "approved", config=config)

    assert not plan.attempt_root.exists()


def test_commandlet_manifest_is_the_existing_closed_five_clip_nine_asset_contract(
    tmp_path: Path,
) -> None:
    source_fbx = tuple(
        (spec, _seal(tmp_path / f"{spec['sequence_name']}.fbx", str(index + 1), 3))
        for index, spec in enumerate(sealed_contract.CLIP_SPECS)
    )

    document = runner._commandlet_execution(
        tmp_path / "attempt",
        _seal(tmp_path / runner.IMPORT_PROJECT_FILE_NAME, "a", 4),
        _seal(tmp_path / "host-receipt.json", "b", 5),
        source_fbx,
        _seal(tmp_path / "commandlet.py", "c", 6),
    )

    assert document["schema_version"] == sealed_contract.EXECUTION_SCHEMA
    assert document["execution_acknowledgement"] == (
        sealed_contract.EXECUTION_ACKNOWLEDGEMENT
    )
    assert document["clip_specs"] == [
        {key: value for key, value in spec.items() if key != "fbx_relative_path"}
        for spec in sealed_contract.CLIP_SPECS
    ]
    assert document["expected_inventory"] == list(
        sealed_contract.EXPECTED_NAMESPACE_INVENTORY
    )
    assert len(document["source_fbx"]) == 5
    assert document["claims"] == sealed_contract.NEGATIVE_CLAIMS
    assert document["content_digest"] == sealed_contract.content_digest(document)


def test_import_sandbox_is_cpu_nullrhi_offline_and_uses_configured_authorities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, plan = _fake_import_plan(tmp_path, monkeypatch)

    argv = runner._bwrap_command(plan, tmp_path / "input", "d" * 64, config=config)
    ue_argv = argv[argv.index("--") + 1 :]

    assert argv[0] == str(config.bwrap)
    assert "--unshare-net" in argv
    assert ["--ro-bind", "/", "/"] not in [
        argv[index : index + 3] for index in range(len(argv) - 2)
    ]
    assert ["--ro-bind", "/usr", "/usr"] in [
        argv[index : index + 3] for index in range(len(argv) - 2)
    ]
    assert ["--tmpfs", "/vista/work/control"] in [
        argv[index : index + 2] for index in range(len(argv) - 1)
    ]
    assert ["--ro-bind", str(config.engine_root), "/vista/engine"] == argv[
        argv.index(str(config.engine_root)) - 1 : argv.index(str(config.engine_root))
        + 2
    ]
    assert ue_argv[0] == "/vista/engine/Engine/Binaries/Linux/UnrealEditor-Cmd"
    assert "-nullrhi" in ue_argv
    assert "-unattended" in ue_argv
    assert not any("graphicsadapter" in token.casefold() for token in argv)
    assert not any("/dev/dri" in token for token in argv)
    assert not any("sunshine" in token.casefold() for token in argv)


def test_overlay_plan_is_copy_only_and_does_not_launch_unreal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _fake_config(tmp_path)
    import_root = config.run_parent / IMPORT_NAME
    inventory = tuple(
        {
            "project_relative_path": (
                f"Content/VISTA/MakeHumanCC0/R8/Animations/P{index}.uasset"
            ),
            "sha256": "e" * 64,
            "size_bytes": index + 1,
        }
        for index in range(9)
    )
    monkeypatch.setattr(
        runner,
        "_load_import_attempt",
        lambda name, config: (
            import_root,
            {"content_digest": "f" * 64, "accepted": False},
            inventory,
        ),
    )
    monkeypatch.setattr(runner, "_validate_base", lambda config: {"accepted": False})
    monkeypatch.setattr(
        runner,
        "_validate_r6_plugin",
        lambda config: ({"accepted": False}, _tree()),
    )
    monkeypatch.setattr(
        runner,
        "_validate_tool",
        lambda path, pin, label: runner.FileSeal(path, pin.sha256, pin.size_bytes),
    )
    monkeypatch.setattr(
        runner,
        "_git_source",
        lambda: {"commit": "6" * 40, "clean": False, "authority": False},
    )

    plan = runner.build_overlay_plan(OVERLAY_NAME, IMPORT_NAME, config=config)

    assert not plan.attempt_root.exists()
    assert plan.report["mode"] == "dry_run_zero_writes"
    assert plan.report["writes_performed"] is False
    assert plan.report["will_run_unreal"] is False
    assert plan.report["will_launch_interactive_renderer"] is False
    assert plan.report["accepted"] is False
    assert plan.report["claims"] == runner.DEV_CLAIMS
    assert plan.report["overlay"]["r3_package_count"] == 23
    assert plan.report["overlay"]["r8_package_count"] == 9
    assert plan.report["future_execute_argv"][-1] == runner.OVERLAY_ACKNOWLEDGEMENT
    launch = runner._overlay_launch_argv(plan.attempt_root, config=config)
    assert launch[0] == str(config.flock)
    assert str(config.bwrap) in launch
    assert "--unshare-net" in launch
    assert "--conflict-exit-code=75" in launch
    assert str(config.unreal_editor) in launch
    assert "-VistaCharacterProvider=makehuman_cc0_r8" in launch
    assert "-VistaHumanOperatedVisualDemo" in launch

    with pytest.raises(runner.DevDemoError, match="exact development overlay"):
        runner.execute_overlay(plan, "approved", config=config)
    assert not plan.attempt_root.exists()


def test_overlay_copy_omits_old_plugin_instead_of_deleting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    observed: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        observed.append(argv)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    runner._rsync_tree(source, destination, "development base", Path("/usr/bin/rsync"))

    assert destination.is_dir()
    assert observed == [
        [
            "/usr/bin/rsync",
            "--archive",
            "--numeric-ids",
            "--exclude=/Plugins/VistaPlayableHome/",
            "--",
            f"{source}/",
            f"{destination}/",
        ]
    ]


def test_attempt_names_and_cli_do_not_accept_caller_selected_authority_paths(
    tmp_path: Path,
) -> None:
    config = _fake_config(tmp_path)
    for name in ("../escape", "/tmp/escape", "makehuman-cc0-animation-ue57-r1-x"):
        with pytest.raises(runner.DevDemoError, match="name is invalid"):
            runner._attempt_path(
                name, runner.IMPORT_ATTEMPT_RE, config, "development import attempt"
            )

    parser = runner._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "plan-import",
                "--attempt-name",
                IMPORT_NAME,
                "--source-root",
                "/tmp/unreviewed",
            ]
        )
    with pytest.raises(SystemExit):
        parser.parse_args(["execute-import", "--attempt-name", IMPORT_NAME])


def test_makehuman_overlay_closure_rejects_any_extra_file(tmp_path: Path) -> None:
    project = tmp_path / "project"
    records: dict[str, list[dict[str, object]]] = {"r3": [], "r8": []}
    for label, prefix, count in (
        ("r3", runner.R3_NAMESPACE_RELATIVE, 23),
        ("r8", runner.R8_NAMESPACE_RELATIVE, 9),
    ):
        for index in range(count):
            relative = (prefix / f"P{index}.uasset").as_posix()
            raw = f"{label}-{index}".encode()
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            records[label].append(
                {
                    "project_relative_path": relative,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }
            )

    runner._validate_makehuman_package_closure(project, records["r3"], records["r8"])
    extra = project / runner.MAKEHUMAN_ROOT_RELATIVE / "unexpected.bin"
    extra.write_bytes(b"not part of the overlay")

    with pytest.raises(runner.DevDemoError, match="extra file"):
        runner._validate_makehuman_package_closure(
            project, records["r3"], records["r8"]
        )


def test_real_pinned_authorities_pass_zero_write_import_plan_when_mounted() -> None:
    required = (
        runner.PRODUCTION_CONFIG.source_receipt,
        runner.PRODUCTION_CONFIG.r3_project_root,
        runner.PRODUCTION_CONFIG.r6_manifest,
        runner.PRODUCTION_CONFIG.r6_plugin_root,
        runner.PRODUCTION_CONFIG.unreal_editor_cmd,
        runner.PRODUCTION_CONFIG.unreal_editor,
        runner.PRODUCTION_CONFIG.bwrap,
        runner.PRODUCTION_CONFIG.flock,
        runner.PRODUCTION_CONFIG.rsync,
    )
    if not all(path.exists() for path in required):
        pytest.skip("host-published development authorities are not mounted")
    attempt = runner.PRODUCTION_CONFIG.run_parent / IMPORT_NAME
    if attempt.exists():
        pytest.skip("reserved zero-write test name is already occupied")

    plan = runner.build_import_plan(IMPORT_NAME)

    assert not attempt.exists()
    assert plan.source_receipt_seal.sha256 == runner.SOURCE_HOST_RECEIPT_SHA256
    assert plan.source_receipt["content_digest"] == runner.SOURCE_HOST_CONTENT_DIGEST
    assert len(plan.source_fbx) == 5
    assert len(plan.r3_packages) == 23
    assert plan.plugin_tree.sha256 == runner.R6_PLUGIN_TREE["tree_sha256"]
    assert plan.report["accepted"] is False
    assert plan.report["claims"]["nonpromotable"] is True
