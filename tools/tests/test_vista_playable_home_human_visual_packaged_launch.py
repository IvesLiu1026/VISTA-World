from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest

from tools.runtime.vista_playable_home import human_visual_packaged_launch as launcher
from tools.ue.vista_playable_home import human_visual_package_receipt as package


def _inputs(tmp_path: Path) -> launcher.PackagedLaunchInputs:
    receipt = tmp_path / package.FINAL_RECEIPT_RELATIVE
    archive = tmp_path / "archive"
    wrapper_path = tmp_path / "tools/bwrap"
    wrapper_path.parent.mkdir(parents=True)
    wrapper_path.write_bytes(b"fixture-bwrap\n")
    wrapper_path.chmod(0o555)
    wrapper = package.FileSeal(
        wrapper_path,
        hashlib.sha256(wrapper_path.read_bytes()).hexdigest(),
        wrapper_path.stat().st_size,
        wrapper_path.stat().st_mode & 0o7777,
    )
    package_binding = package.FinalPackageBinding(
        receipt=receipt,
        receipt_sha256="a" * 64,
        receipt_content_digest="b" * 64,
        archive_root=archive,
        archive_tree_sha256="c" * 64,
        launcher=package.FileSeal(
            archive / "Linux/VistaPlayableHome.sh", "d" * 64, 10, 0o555
        ),
        executable=package.FileSeal(
            archive / "Linux/VistaPlayableHome/Binaries/Linux/VistaPlayableHome",
            "e" * 64,
            20,
            0o555,
        ),
        pak=package.FileSeal(
            archive
            / "Linux/VistaPlayableHome/Content/Paks/VistaPlayableHome-Linux.pak",
            "f" * 64,
            30,
            0o444,
        ),
        source_receipt_sha256=package.PINNED_SOURCE_RECEIPT_SHA256,
        pso_expand_receipt_sha256="1" * 64,
        stable_cache_sha256="2" * 64,
    )
    return launcher.PackagedLaunchInputs(
        package=package_binding,
        cache_root=launcher.CACHE_PARENT / package_binding.receipt_sha256,
        network_wrapper=wrapper,
    )


def test_packaged_launch_is_fixed_to_118_gpu0_1080p_without_pso_logging(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    command = launcher.build_command(inputs)
    assert command[:7] == [
        str(inputs.network_wrapper.path),
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
    ]
    assert command[7] == str(inputs.package.launcher.path)
    assert "-ResX=1920" in command
    assert "-ResY=1080" in command
    assert "-graphicsadapter=0" in command
    assert "-NoVSync" in command
    assert "-VistaHumanOperatedVisualDemo" in command
    assert "-logpso" not in command
    assert not any("Agent" in item or "VLM" in item for item in command)
    assert f"-UserDir={inputs.cache_root / 'user'}" in command
    assert f"-LocalDataCachePath={inputs.cache_root / 'ddc'}" in command


def test_environment_and_cache_are_receipt_bound_and_persistent(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    environment = launcher.environment_plan(inputs)
    assert environment["DISPLAY"] == ":118"
    assert environment["CUDA_VISIBLE_DEVICES"] == "0"
    assert environment["NVIDIA_VISIBLE_DEVICES"] == "0"
    assert environment["HOME"] == str(inputs.cache_root / "user")
    assert environment["UE_LocalDataCachePath"] == str(inputs.cache_root / "ddc")
    assert inputs.cache_root == launcher.CACHE_PARENT / ("a" * 64)


def test_launch_plan_is_read_only_closed_and_keeps_claims_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    monkeypatch.setattr(
        package, "validate_network_wrapper", lambda: inputs.network_wrapper
    )
    monkeypatch.setattr(
        package, "load_final_package_receipt", lambda _path: inputs.package
    )
    assert not inputs.cache_root.exists()
    plan = launcher.build_plan(inputs)
    assert not inputs.cache_root.exists()
    assert plan["schema_version"] == launcher.PLAN_SCHEMA
    assert plan["execution"] == "not_authorized_plan_only"
    assert plan["runtime"] == {
        "display": ":118",
        "gpu": 0,
        "width": 1920,
        "height": 1080,
        "target_fps": 60,
        "screen_percentage": 100,
        "camera_profile": "realistic_interior_r2",
        "provider_id": "citysample_crowd_visual_demo_v1",
    }
    assert plan["persistent_user_cache"]["created_by_dry_run"] is False
    assert plan["security"]["default_zero_write"] is True
    assert plan["security"]["default_zero_subprocess"] is True
    assert plan["security"]["pso_capture_logging_disabled"] is True
    assert plan["security"]["network_wrapper_rehashed_during_plan"] is True
    assert plan["security"]["network_wrapper_sha256"] == inputs.network_wrapper.sha256
    assert plan["legal_scope"] == package.HUMAN_ONLY_LEGAL_BOUNDARY
    assert all(value is False for value in plan["claims"].values())
    assert (
        plan["command_sha256"]
        == hashlib.sha256(launcher.canonical_json(plan["command"])).hexdigest()
    )
    assert json.loads(launcher.canonical_json(plan)) == plan
    source = inspect.getsource(launcher)
    assert "import subprocess" not in source
    assert "subprocess.Popen" not in source


def test_load_inputs_wraps_final_receipt_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_path: Path) -> package.FinalPackageBinding:
        raise package.HumanVisualPackageError("ARCHIVE_PIN_MISMATCH", "changed")

    monkeypatch.setattr(package, "load_final_package_receipt", refuse)
    with pytest.raises(
        launcher.HumanVisualPackagedLaunchError,
        match="final package receipt was refused",
    ):
        launcher.load_inputs(tmp_path / package.FINAL_RECEIPT_NAME)


def test_load_inputs_rehashes_network_wrapper_every_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    calls = 0

    def final(_path: Path) -> package.FinalPackageBinding:
        return inputs.package

    def wrapper() -> package.FileSeal:
        nonlocal calls
        calls += 1
        return inputs.network_wrapper

    monkeypatch.setattr(package, "load_final_package_receipt", final)
    monkeypatch.setattr(package, "validate_network_wrapper", wrapper)
    first = launcher.load_inputs(inputs.package.receipt)
    second = launcher.load_inputs(inputs.package.receipt)
    assert calls == 2
    assert first.network_wrapper == second.network_wrapper == inputs.network_wrapper


def test_load_inputs_refuses_network_wrapper_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    monkeypatch.setattr(
        package, "load_final_package_receipt", lambda _path: inputs.package
    )

    def refuse() -> package.FileSeal:
        raise package.HumanVisualPackageError("NETWORK_WRAPPER_PIN_MISMATCH", "changed")

    monkeypatch.setattr(package, "validate_network_wrapper", refuse)
    with pytest.raises(
        launcher.HumanVisualPackagedLaunchError,
        match="network wrapper was refused",
    ):
        launcher.load_inputs(inputs.package.receipt)


def test_launch_plan_refuses_wrapper_drift_after_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    changed = package.FileSeal(
        inputs.network_wrapper.path,
        "9" * 64,
        inputs.network_wrapper.size_bytes,
        inputs.network_wrapper.mode,
    )
    monkeypatch.setattr(package, "validate_network_wrapper", lambda: changed)
    monkeypatch.setattr(
        package, "load_final_package_receipt", lambda _path: inputs.package
    )
    with pytest.raises(
        launcher.HumanVisualPackagedLaunchError,
        match="changed after input validation",
    ):
        launcher.build_plan(inputs)


def test_launch_plan_refuses_changed_revalidated_package_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs(tmp_path)
    changed = replace(inputs.package, archive_tree_sha256="8" * 64)
    monkeypatch.setattr(package, "load_final_package_receipt", lambda _path: changed)
    with pytest.raises(
        launcher.HumanVisualPackagedLaunchError,
        match="identity changed after input loading",
    ):
        launcher.build_plan(inputs)


def test_main_prints_plan_without_writes_or_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = _inputs(tmp_path)
    monkeypatch.setattr(launcher, "load_inputs", lambda _path: inputs)
    monkeypatch.setattr(
        package, "validate_network_wrapper", lambda: inputs.network_wrapper
    )
    monkeypatch.setattr(
        package, "load_final_package_receipt", lambda _path: inputs.package
    )
    code = launcher.main(["--package-receipt", str(inputs.package.receipt)])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert json.loads(captured.out)["schema_version"] == launcher.PLAN_SCHEMA
    assert not inputs.cache_root.exists()


def test_cli_exposes_no_launch_or_execute_flag() -> None:
    destinations = {action.dest for action in launcher.parser()._actions}
    assert "launch" not in destinations
    assert "execute" not in destinations
    with pytest.raises(launcher.HumanVisualPackagedLaunchError):
        launcher.canonical_json(float("nan"))
