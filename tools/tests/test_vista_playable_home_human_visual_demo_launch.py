from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from unittest import mock

import pytest

from tools.runtime.vista_playable_home import human_visual_demo_launch as launcher


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pin(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "sha256": _sha(path),
        "size_bytes": path.stat().st_size,
    }


def _write_receipt(root: Path) -> tuple[Path, dict[str, object]]:
    project = root / "project" / "HumanVisualDemo.uproject"
    map_package = root / "project" / "Content/VISTA/HumanDemo/HumanDemo.umap"
    config = root / "project" / "Config/DefaultEngine.ini"
    plugin = root / "project" / "Plugins/HumanDemo/HumanDemo.uplugin"
    executable = root / "UE/Engine/Binaries/Linux/UnrealEditor"
    project.parent.mkdir(parents=True)
    map_package.parent.mkdir(parents=True)
    config.parent.mkdir(parents=True)
    plugin.parent.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    project.write_text('{"FileVersion":3}\n', encoding="utf-8")
    map_package.write_bytes(b"sealed-map-fixture\n")
    config.write_text("[/Script/Engine.Engine]\n", encoding="utf-8")
    plugin.write_text('{"FileVersion":3}\n', encoding="utf-8")
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o500)

    provenance: dict[str, object] = {}
    for key in launcher.SOURCE_PROVENANCE_ARTIFACT_KEYS:
        artifact = root / "provenance" / f"{key}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f'{{"source":"{key}"}}\n', encoding="utf-8")
        provenance[key] = _pin(artifact)
    provenance["plugin_package_tree_sha256"] = "a" * 64
    provenance["plugin_source_git_commit"] = "b" * 40

    receipt: dict[str, object] = {
        "schema_version": launcher.COMBINED_RECEIPT_SCHEMA,
        "status": launcher.COMBINED_RECEIPT_STATUS,
        "provider_id": launcher.PROVIDER_ID,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "project": _pin(project),
        "project_static_tree": launcher.compute_project_static_tree(project),
        "source_provenance": provenance,
        "executable": _pin(executable),
        "map": {
            "object_path": "/Game/VISTA/HumanDemo/HumanDemo",
            "package": _pin(map_package),
        },
        "legal_scope": copy.deepcopy(launcher.LEGAL_SCOPE),
        "claims": copy.deepcopy(launcher.CLAIMS),
    }
    receipt["content_digest"] = launcher.content_digest(receipt)
    receipt_path = root / launcher.COMBINED_RECEIPT_NAME
    raw = launcher.canonical_json(receipt)
    receipt_path.write_bytes(raw)
    sidecar = root / launcher.COMBINED_RECEIPT_SIDECAR_NAME
    sidecar.write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {launcher.COMBINED_RECEIPT_NAME}\n",
        encoding="ascii",
    )
    return receipt_path, receipt


def _reseal(receipt_path: Path, receipt: dict[str, object]) -> None:
    receipt["content_digest"] = launcher.content_digest(receipt)
    raw = launcher.canonical_json(receipt)
    receipt_path.write_bytes(raw)
    receipt_path.with_name(launcher.COMBINED_RECEIPT_SIDECAR_NAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {launcher.COMBINED_RECEIPT_NAME}\n",
        encoding="ascii",
    )


def test_closed_receipt_binds_project_executable_map_sidecar_and_legal_scope(
    tmp_path: Path,
) -> None:
    receipt_path, receipt = _write_receipt(tmp_path)

    inputs = launcher.load_combined_receipt(receipt_path)

    assert inputs.project.path == Path(receipt["project"]["path"])
    assert inputs.executable.path == Path(receipt["executable"]["path"])
    assert inputs.map_object_path == "/Game/VISTA/HumanDemo/HumanDemo"
    assert inputs.receipt_content_digest == receipt["content_digest"]
    assert inputs.project_static_tree == receipt["project_static_tree"]
    assert inputs.source_provenance == receipt["source_provenance"]
    assert receipt["legal_scope"] == launcher.LEGAL_SCOPE
    assert receipt["claims"] == {
        "runtime_visual_acceptance": False,
        "interaction_accepted": False,
        "photoreal_character_accepted": False,
        "gta_level_quality": False,
    }


def test_command_and_environment_are_human_only_closed_and_non_networked(
    tmp_path: Path,
) -> None:
    receipt_path, _receipt = _write_receipt(tmp_path)
    inputs = launcher.load_combined_receipt(receipt_path)
    command = launcher.build_command(inputs)
    cache_root = launcher.runtime_cache_root(inputs)
    environment = launcher.sanitized_environment(tmp_path / "private", cache_root)
    rendered = " ".join(command).lower()

    assert command[:7] == [
        str(launcher.NETWORK_NAMESPACE_EXECUTABLE),
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
    ]
    assert command[7] == str(inputs.executable.path)
    assert command[8] == str(inputs.project.path)
    assert "-VistaHumanOperatedVisualDemo" in command
    assert f"-VistaCharacterProvider={launcher.PROVIDER_ID}" in command
    assert "-graphicsadapter=0" in command
    assert f"-UserDir={cache_root / 'user'}" in command
    assert f"-VistaCameraProfile={launcher.CAMERA_PROFILE}" in command
    assert "-NoVSync" in command
    assert (
        f"-ExecCmds=t.MaxFPS {launcher.TARGET_FPS},"
        f"r.ScreenPercentage {launcher.SCREEN_PERCENTAGE}"
    ) in command
    assert "-ddc=InstalledNoZenLocalFallback" in command
    assert "-SaveToUserDir" in command
    assert "-NOSOUND" in command
    assert (
        "-ini:Engine:[/Script/AppleARKit.AppleARKitSettings]:"
        "bEnableLiveLinkForFaceTracking=False"
    ) in command
    assert "vistaworldport" not in rendered
    assert "pixelstreaming" not in rendered
    assert "token" not in rendered
    assert "api_key" not in rendered
    assert "model" not in rendered
    assert environment["DISPLAY"] == ":118"
    assert environment["CUDA_VISIBLE_DEVICES"] == "0"
    assert environment["UE_LocalDataCachePath"] == str(cache_root / "ddc")
    assert environment["VISTA_CHARACTER_PROVIDER"] == launcher.PROVIDER_ID
    assert all(
        prohibited not in key.upper()
        for key in environment
        for prohibited in ("TOKEN", "API_KEY", "MODEL", "PORT")
    )
    assert set(environment) == {
        "LANG",
        "LC_ALL",
        "PATH",
        "DISPLAY",
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "HOME",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "UE_LocalDataCachePath",
        "VISTA_CHARACTER_PROVIDER",
        "VISTA_HUMAN_OPERATED_VISUAL_DEMO",
    }


def test_default_cli_is_zero_write_dry_run_and_has_no_launch_side_effect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt_path, _receipt = _write_receipt(tmp_path)
    before = sorted(
        (path.relative_to(tmp_path).as_posix(), path.read_bytes())
        for path in tmp_path.rglob("*")
        if path.is_file()
    )

    with mock.patch.object(launcher.subprocess, "Popen") as popen:
        assert launcher.main(["--combined-receipt", str(receipt_path)]) == 0

    popen.assert_not_called()
    after = sorted(
        (path.relative_to(tmp_path).as_posix(), path.read_bytes())
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    assert after == before
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == launcher.PENDING_STATUS
    assert plan["provider_id"] == launcher.PROVIDER_ID
    assert plan["security"] == {
        "closed_environment": True,
        "shell": False,
        "extra_ue_arguments": False,
        "vista_agent_tcp_listener_requested": False,
        "network_readiness_probe": False,
        "local_zen_autolaunch_disabled": True,
        "apple_arkit_livelink_disabled": True,
        "private_network_namespace": True,
        "receipt_bound_private_runtime_cache": True,
        "target_fps_cap_request_bound": True,
        "screen_percentage_request_bound": True,
        "agent_runtime_invoked": False,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "immediate_pre_popen_revalidation": True,
        "same_uid_concurrent_mutation_out_of_scope": True,
        "project_static_files_not_group_world_writable": True,
    }
    assert plan["claims"] == launcher.CLAIMS


def test_launch_uses_no_shell_listener_probe_or_runtime_readiness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt_path, _receipt = _write_receipt(tmp_path)
    inputs = launcher.load_combined_receipt(receipt_path)
    process = mock.Mock(pid=4242)
    process.poll.side_effect = [None, 0, 0]
    process.wait.return_value = 0
    popen = mock.Mock(return_value=process)

    with (
        mock.patch.object(launcher, "LOCK_ROOT", tmp_path / "locks"),
        mock.patch.object(launcher, "CACHE_PARENT", tmp_path / "cache/human"),
    ):
        expected_command = launcher.build_command(inputs)
        assert (
            launcher.run_human_visual_demo(
                inputs, popen_factory=popen, startup_grace_seconds=0
            )
            == 0
        )

    popen.assert_called_once()
    args, kwargs = popen.call_args
    assert args == (expected_command,)
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True
    assert kwargs["stdout"] is launcher.subprocess.DEVNULL
    assert kwargs["stderr"] is launcher.subprocess.STDOUT
    assert kwargs["env"]["UE_LocalDataCachePath"] == str(
        tmp_path / "cache/human" / inputs.receipt_sha256 / "ddc"
    )
    statuses = [
        json.loads(line)["status"] for line in capsys.readouterr().out.splitlines()
    ]
    assert statuses == [launcher.PENDING_STATUS, launcher.READY_STATUS]

    source = Path(launcher.__file__).read_text(encoding="utf-8")
    assert "import socket" not in source
    assert "probe_typed_runtime" not in source
    assert "wait_for_readiness" not in source
    assert "VistaWorldPort" not in source
    assert "tools.runtime.vista_playable_home.runtime" not in source


def test_launch_revalidates_all_pins_before_popen(tmp_path: Path) -> None:
    receipt_path, receipt = _write_receipt(tmp_path)
    inputs = launcher.load_combined_receipt(receipt_path)
    map_package = Path(receipt["map"]["package"]["path"])
    map_package.write_bytes(b"changed-before-popen\n")
    popen = mock.Mock()

    with (
        mock.patch.object(launcher, "LOCK_ROOT", tmp_path / "locks"),
        mock.patch.object(launcher, "CACHE_PARENT", tmp_path / "cache/human"),
        pytest.raises(launcher.HumanVisualDemoError, match="static tree"),
    ):
        launcher.run_human_visual_demo(
            inputs, popen_factory=popen, startup_grace_seconds=0
        )

    popen.assert_not_called()


def test_launch_rejects_network_namespace_wrapper_drift_before_popen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt_path, _receipt = _write_receipt(tmp_path)
    inputs = launcher.load_combined_receipt(receipt_path)
    wrapper = tmp_path / "bwrap"
    wrapper.write_bytes(b"not-the-pinned-wrapper\n")
    wrapper.chmod(0o500)
    monkeypatch.setattr(launcher, "NETWORK_NAMESPACE_EXECUTABLE", wrapper)
    popen = mock.Mock()

    with (
        mock.patch.object(launcher, "LOCK_ROOT", tmp_path / "locks"),
        mock.patch.object(launcher, "CACHE_PARENT", tmp_path / "cache/human"),
        pytest.raises(
            launcher.HumanVisualDemoError,
            match="private network namespace wrapper differs",
        ),
    ):
        launcher.run_human_visual_demo(
            inputs, popen_factory=popen, startup_grace_seconds=0
        )

    popen.assert_not_called()


def test_status_vocabulary_and_fields_are_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt_path, _receipt = _write_receipt(tmp_path)
    inputs = launcher.load_combined_receipt(receipt_path)

    with pytest.raises(launcher.HumanVisualDemoError, match="closed vocabulary"):
        launcher._emit_status("accepted", inputs)
    with pytest.raises(launcher.HumanVisualDemoError, match="fields are not closed"):
        launcher._emit_status(launcher.PENDING_STATUS, inputs, accepted=True)
    with pytest.raises(launcher.HumanVisualDemoError, match="identity is invalid"):
        launcher._emit_status(launcher.READY_STATUS, inputs, pid=0)
    assert capsys.readouterr().out == ""


def test_project_static_tree_is_complete_deterministic_and_excludes_mutable_dirs(
    tmp_path: Path,
) -> None:
    receipt_path, receipt = _write_receipt(tmp_path)
    project = Path(receipt["project"]["path"])
    first = launcher.compute_project_static_tree(project)
    assert first == receipt["project_static_tree"]
    assert set(first) == launcher.PROJECT_STATIC_TREE_KEYS
    assert first["algorithm"] == launcher.PROJECT_STATIC_TREE_ALGORITHM
    assert first["file_count"] == 4

    saved = project.parent / "Saved/Mutable.log"
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_bytes(b"mutable-and-excluded\n")
    assert launcher.compute_project_static_tree(project) == first
    assert launcher.load_combined_receipt(receipt_path).project_static_tree == first

    added = project.parent / "Content/VISTA/HumanDemo/Added.uasset"
    added.write_bytes(b"new-static-file\n")
    with pytest.raises(launcher.HumanVisualDemoError, match="static tree differs"):
        launcher.load_combined_receipt(receipt_path)


def test_nested_mutable_named_directories_are_part_of_static_roots(
    tmp_path: Path,
) -> None:
    receipt_path, receipt = _write_receipt(tmp_path)
    project = Path(receipt["project"]["path"])
    before = launcher.compute_project_static_tree(project)
    nested = project.parent / "Content/Intermediate/generated.uasset"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"nested-static-content\n")

    after = launcher.compute_project_static_tree(project)
    assert after["file_count"] == before["file_count"] + 1
    assert after["tree_sha256"] != before["tree_sha256"]
    with pytest.raises(launcher.HumanVisualDemoError, match="static tree differs"):
        launcher.load_combined_receipt(receipt_path)


def test_project_root_rejects_unpinned_source_binary_or_script_entries(
    tmp_path: Path,
) -> None:
    receipt_path, receipt = _write_receipt(tmp_path)
    project_root = Path(receipt["project"]["path"]).parent
    for root_name in ("Source", "Binaries", "Platforms", "Script"):
        extra = project_root / root_name
        extra.mkdir()
        with pytest.raises(
            launcher.HumanVisualDemoError, match="unpinned static entry"
        ):
            launcher.load_combined_receipt(receipt_path)
        extra.rmdir()


@pytest.mark.parametrize("case", ["symlink", "special", "group_writable"])
def test_project_static_tree_rejects_unsafe_entries(tmp_path: Path, case: str) -> None:
    receipt_path, receipt = _write_receipt(tmp_path)
    project = Path(receipt["project"]["path"])
    unsafe = project.parent / "Content/VISTA/HumanDemo/Unsafe"
    if case == "symlink":
        unsafe.symlink_to(Path(receipt["map"]["package"]["path"]))
    elif case == "special":
        os.mkfifo(unsafe)
    else:
        unsafe.write_bytes(b"unsafe-mode\n")
        unsafe.chmod(0o664)

    with pytest.raises(launcher.HumanVisualDemoError, match="symlink|special|writable"):
        launcher.load_combined_receipt(receipt_path)


def test_unreal_executable_must_not_be_writable_by_current_uid(tmp_path: Path) -> None:
    receipt_path, receipt = _write_receipt(tmp_path)
    executable = Path(receipt["executable"]["path"])
    executable.chmod(0o700)

    with pytest.raises(launcher.HumanVisualDemoError, match="current process"):
        launcher.load_combined_receipt(receipt_path)


def test_nas_acl_access_result_is_out_of_scope_but_mode_and_hash_stay_enforced(
    tmp_path: Path,
) -> None:
    receipt_path, _receipt = _write_receipt(tmp_path)
    with mock.patch.object(launcher.os, "access", return_value=True) as access:
        inputs = launcher.load_combined_receipt(receipt_path)

    access.assert_not_called()
    assert inputs.executable.path.stat().st_mode & 0o222 == 0
    assert inputs.project_static_tree["tree_sha256"]


def test_source_provenance_is_closed_and_rehashed(tmp_path: Path) -> None:
    receipt_path, receipt = _write_receipt(tmp_path)
    source = Path(receipt["source_provenance"]["citysample_result"]["path"])
    source.write_text('{"source":"changed"}\n', encoding="utf-8")

    with pytest.raises(launcher.HumanVisualDemoError, match="receipt pin"):
        launcher.load_combined_receipt(receipt_path)


def test_display_gpu_launch_lock_is_exclusive_across_receipts(tmp_path: Path) -> None:
    first_receipt, _first_payload = _write_receipt(tmp_path / "first")
    second_receipt, _second_payload = _write_receipt(tmp_path / "second")
    first_inputs = launcher.load_combined_receipt(first_receipt)
    second_inputs = launcher.load_combined_receipt(second_receipt)
    assert first_inputs.receipt_sha256 != second_inputs.receipt_sha256
    with mock.patch.object(launcher, "LOCK_ROOT", tmp_path / "locks"):
        first = launcher._acquire_launch_lock(first_inputs)
        try:
            with pytest.raises(launcher.HumanVisualDemoError, match="already"):
                launcher._acquire_launch_lock(second_inputs)
            assert (tmp_path / "locks/display-118-gpu-0.lock").is_file()
        finally:
            launcher._release_launch_lock(first)


def test_runtime_cache_is_receipt_bound_private_and_reused(tmp_path: Path) -> None:
    receipt_path, _receipt = _write_receipt(tmp_path / "receipt")
    inputs = launcher.load_combined_receipt(receipt_path)

    with mock.patch.object(launcher, "CACHE_PARENT", tmp_path / "cache/human"):
        expected = tmp_path / "cache/human" / inputs.receipt_sha256
        assert launcher.runtime_cache_root(inputs) == expected
        assert launcher.ensure_runtime_cache(inputs) == expected
        assert launcher.ensure_runtime_cache(inputs) == expected

    for directory in (
        tmp_path / "cache",
        tmp_path / "cache/human",
        expected,
        expected / "ddc",
        expected / "user",
    ):
        assert directory.is_dir()
        assert directory.stat().st_mode & 0o777 == 0o700


def test_runtime_cache_rejects_symlinked_namespace(tmp_path: Path) -> None:
    receipt_path, _receipt = _write_receipt(tmp_path / "receipt")
    inputs = launcher.load_combined_receipt(receipt_path)
    real = tmp_path / "real"
    real.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o700)
    namespace = cache / "human"
    namespace.symlink_to(real, target_is_directory=True)

    with (
        mock.patch.object(launcher, "CACHE_PARENT", namespace),
        pytest.raises(launcher.HumanVisualDemoError, match="private real directory"),
    ):
        launcher.ensure_runtime_cache(inputs)


def test_process_group_cleanup_escalates_after_timeout() -> None:
    process = mock.Mock(pid=4242)
    process.poll.return_value = None
    process.wait.side_effect = [launcher.subprocess.TimeoutExpired("ue", 1), 0]
    with mock.patch.object(launcher.os, "killpg") as killpg:
        launcher._terminate_process_group(process, timeout_seconds=1)
    assert killpg.call_args_list == [
        mock.call(4242, launcher.signal.SIGTERM),
        mock.call(4242, launcher.signal.SIGKILL),
    ]


def test_cli_has_no_provider_extra_arg_port_or_production_tuple_override() -> None:
    destinations = {action.dest for action in launcher.parser()._actions}
    assert destinations == {"help", "combined_receipt", "display", "gpu", "launch"}
    assert launcher.DISPLAY == ":118"
    assert launcher.GPU == 0
    source = Path(launcher.__file__).read_text(encoding="utf-8")
    assert 'DEFAULT_DISPLAY = ":117"' not in source
    assert "55620" not in source
    assert "55621" not in source
    with pytest.raises(SystemExit):
        launcher.parser().parse_args(
            [
                "--combined-receipt",
                "/tmp/receipt.json",
                "--provider",
                "other",
            ]
        )
    with pytest.raises(SystemExit):
        launcher.parser().parse_args(
            [
                "--combined-receipt",
                "/tmp/receipt.json",
                "--extra-ue-arg=-ExecCmds=quit",
            ]
        )
    with pytest.raises(SystemExit):
        launcher.parser().parse_args(
            ["--combined-receipt", "/tmp/receipt.json", "--display", ":117"]
        )
    with pytest.raises(SystemExit):
        launcher.parser().parse_args(
            ["--combined-receipt", "/tmp/receipt.json", "--gpu", "1"]
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda receipt: receipt.update({"extra": True}), "key inventory"),
        (
            lambda receipt: receipt.update({"provider_id": "other"}),
            "provider differs",
        ),
        (
            lambda receipt: receipt.update({"human_operated_visual_demo_only": False}),
            "human-only gate differs",
        ),
        (
            lambda receipt: receipt.update({"prohibited_agent_adapter": False}),
            "agent prohibition differs",
        ),
        (
            lambda receipt: receipt["claims"].update({"gta_level_quality": True}),
            "claims boolean values differ",
        ),
        (
            lambda receipt: receipt["legal_scope"].update(
                {"excluded_from_ai_vlm_training_testing_evaluation_or_review": False}
            ),
            "legal scope boolean values differ",
        ),
        (
            lambda receipt: receipt["legal_scope"].update(
                {"private_noncommercial_research_only": 1}
            ),
            "legal scope boolean values differ",
        ),
        (
            lambda receipt: receipt["claims"].update({"runtime_visual_acceptance": 0}),
            "claims boolean values differ",
        ),
    ],
)
def test_receipt_scope_and_closed_keys_fail_closed(
    tmp_path: Path, mutation, message: str
) -> None:
    receipt_path, receipt = _write_receipt(tmp_path)
    mutation(receipt)
    _reseal(receipt_path, receipt)

    with pytest.raises(launcher.HumanVisualDemoError, match=message):
        launcher.load_combined_receipt(receipt_path)


def test_sidecar_content_digest_and_artifact_drift_fail_closed(tmp_path: Path) -> None:
    receipt_path, receipt = _write_receipt(tmp_path)
    sidecar_path = receipt_path.with_name(launcher.COMBINED_RECEIPT_SIDECAR_NAME)

    sidecar_path.write_text(
        f"{'0' * 64}  {launcher.COMBINED_RECEIPT_NAME}\n", encoding="ascii"
    )
    with pytest.raises(launcher.HumanVisualDemoError, match="sidecar differs"):
        launcher.load_combined_receipt(receipt_path)

    _reseal(receipt_path, receipt)
    receipt["content_digest"] = "0" * 64
    raw = launcher.canonical_json(receipt)
    receipt_path.write_bytes(raw)
    sidecar_path.write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {launcher.COMBINED_RECEIPT_NAME}\n",
        encoding="ascii",
    )
    with pytest.raises(launcher.HumanVisualDemoError, match="content digest differs"):
        launcher.load_combined_receipt(receipt_path)

    _reseal(receipt_path, receipt)
    map_package = Path(receipt["map"]["package"]["path"])
    map_package.write_bytes(b"changed-map\n")
    with pytest.raises(launcher.HumanVisualDemoError, match="static tree"):
        launcher.load_combined_receipt(receipt_path)
