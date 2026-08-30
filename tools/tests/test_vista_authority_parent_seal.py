from __future__ import annotations

import importlib.util
import hashlib
import os
from pathlib import Path
import stat
import sys
from types import ModuleType, SimpleNamespace

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "admin" / "vista_authority_parent_seal.py"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "vista_authority_parent_seal_under_test", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = _load_module()
    parent = tmp_path / "vista-authorities"
    parent.mkdir(mode=0o755)
    child = parent / "blender-4.5.8-r1"
    child.mkdir(mode=0o555)
    child.chmod(0o555)
    parent.chmod(0o755)
    monkeypatch.setattr(module, "AUTHORITY_PARENT", parent)
    monkeypatch.setattr(module, "ROOT_UID", os.geteuid())
    monkeypatch.setattr(module, "ROOT_GID", os.getegid())
    monkeypatch.setattr(module, "_ancestor_paths", lambda _path: (parent,))
    return module


def test_audit_is_zero_write_and_reports_ready(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_fchmod(*_args: object) -> None:
        raise AssertionError("audit must not change permissions")

    monkeypatch.setattr(os, "fchmod", forbidden_fchmod)
    report = seal.audit_parent()
    assert report["status"] == "ready_for_one_shot_seal"
    assert report["mode"] == "0755"
    assert report["publishers_quiescent_acknowledged"] is False
    assert stat.S_IMODE(os.lstat(seal.AUTHORITY_PARENT).st_mode) == 0o755


def test_seal_transitions_once_and_preserves_child_identity(seal: ModuleType) -> None:
    child_before = os.lstat(seal.AUTHORITY_PARENT / "blender-4.5.8-r1")
    report = seal.seal_parent()
    child_after = os.lstat(seal.AUTHORITY_PARENT / "blender-4.5.8-r1")
    assert report["status"] == "sealed_and_fsynced"
    assert report["mode"] == "0555"
    assert report["permissions_relaxed"] is False
    assert report["publishers_quiescent_acknowledged"] is True
    assert (child_before.st_dev, child_before.st_ino) == (
        child_after.st_dev,
        child_after.st_ino,
    )
    with pytest.raises(seal.ParentSealError, match="AUTHORITY_PARENT_NOT_FRESH"):
        seal.seal_parent()


def test_reconcile_only_accepts_sealed_parent(seal: ModuleType) -> None:
    with pytest.raises(
        seal.ParentSealError, match="AUTHORITY_PARENT_RECONCILE_INVALID"
    ):
        seal.reconcile_parent()
    seal.AUTHORITY_PARENT.chmod(0o555)
    report = seal.reconcile_parent()
    assert report["operation"] == "reconcile"
    assert report["mode"] == "0555"


def test_sealed_audit_and_reconcile_never_call_fchmod(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    seal.AUTHORITY_PARENT.chmod(0o555)

    def forbidden_fchmod(*_args: object) -> None:
        raise AssertionError("sealed audit/reconcile must never call fchmod")

    monkeypatch.setattr(os, "fchmod", forbidden_fchmod)
    assert seal.audit_parent()["status"] == "already_sealed"
    assert seal.reconcile_parent()["status"] == "sealed_and_fsynced"


@pytest.mark.parametrize("name", ["unexpected", ".staging-publisher"])
def test_unexpected_or_staging_namespace_fails_closed(
    seal: ModuleType, name: str
) -> None:
    (seal.AUTHORITY_PARENT / name).mkdir()
    with pytest.raises(seal.ParentSealError):
        seal.audit_parent()
    assert stat.S_IMODE(os.lstat(seal.AUTHORITY_PARENT).st_mode) == 0o755


def test_symlink_or_wrong_mode_child_fails_closed(seal: ModuleType) -> None:
    child = seal.AUTHORITY_PARENT / "blender-4.5.8-r1"
    child.chmod(0o755)
    with pytest.raises(seal.ParentSealError, match="AUTHORITY_PARENT_SECURITY_INVALID"):
        seal.audit_parent()
    child.rmdir()
    child.symlink_to(seal.AUTHORITY_PARENT, target_is_directory=True)
    with pytest.raises(seal.ParentSealError, match="AUTHORITY_PARENT_SECURITY_INVALID"):
        seal.audit_parent()


def test_failed_fsync_preserves_0555_and_requires_reconcile(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_fsync = os.fsync

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("injected durability failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(seal.ParentSealError) as caught:
        seal.seal_parent()
    assert caught.value.code == "PARENT_SEAL_DURABILITY_UNKNOWN"
    assert stat.S_IMODE(os.lstat(seal.AUTHORITY_PARENT).st_mode) == 0o555
    with pytest.raises(seal.ParentSealError, match="AUTHORITY_PARENT_NOT_FRESH"):
        seal.seal_parent()
    monkeypatch.setattr(os, "fsync", real_fsync)
    assert seal.reconcile_parent()["status"] == "sealed_and_fsynced"


def test_fchmod_failure_does_not_claim_durability_unknown(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_fchmod(_descriptor: int, _mode: int) -> None:
        raise OSError("injected transition failure")

    monkeypatch.setattr(os, "fchmod", fail_fchmod)
    with pytest.raises(seal.ParentSealError) as caught:
        seal.seal_parent()
    assert caught.value.code == "PARENT_SEAL_TRANSITION_FAILED"
    assert stat.S_IMODE(os.lstat(seal.AUTHORITY_PARENT).st_mode) == 0o755


def test_fchmod_error_after_mode_change_is_durability_unknown(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_fchmod = os.fchmod

    def change_then_fail(descriptor: int, mode: int) -> None:
        real_fchmod(descriptor, mode)
        raise OSError("injected post-transition syscall error")

    monkeypatch.setattr(os, "fchmod", change_then_fail)
    with pytest.raises(seal.ParentSealError) as caught:
        seal.seal_parent()
    assert caught.value.code == "PARENT_SEAL_DURABILITY_UNKNOWN"
    assert stat.S_IMODE(os.lstat(seal.AUTHORITY_PARENT).st_mode) == 0o555


def test_post_transition_identity_error_becomes_durability_unknown(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_reopen(*_args: object, **_kwargs: object) -> None:
        raise seal.ParentSealError(
            "AUTHORITY_PARENT_IDENTITY_CHANGED", "injected replacement"
        )

    monkeypatch.setattr(seal, "_reopen_and_verify", fail_reopen)
    with pytest.raises(seal.ParentSealError) as caught:
        seal.seal_parent()
    assert caught.value.code == "PARENT_SEAL_DURABILITY_UNKNOWN"
    assert stat.S_IMODE(os.lstat(seal.AUTHORITY_PARENT).st_mode) == 0o555


def test_real_path_replacement_after_transition_is_detected(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_open = seal._open_directory
    calls = 0
    original = seal.AUTHORITY_PARENT
    displaced = original.with_name("vista-authorities-displaced")

    def replace_before_reopen(path: Path) -> int:
        nonlocal calls
        calls += 1
        if calls == 2:
            original.rename(displaced)
            original.mkdir(mode=0o555)
            (original / "blender-4.5.8-r1").mkdir(mode=0o555)
            (original / "blender-4.5.8-r1").chmod(0o555)
            original.chmod(0o555)
        return real_open(path)

    monkeypatch.setattr(seal, "_open_directory", replace_before_reopen)
    with pytest.raises(seal.ParentSealError) as caught:
        seal.seal_parent()
    assert caught.value.code == "PARENT_SEAL_DURABILITY_UNKNOWN"
    assert stat.S_IMODE(os.lstat(displaced).st_mode) == 0o555


def test_inventory_mutation_during_seal_fails_without_relaxing_mode(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_inventory = seal._inventory_fd
    calls = 0

    def mutate_after_snapshot(descriptor: int):
        nonlocal calls
        calls += 1
        result = real_inventory(descriptor)
        if calls == 1:
            (seal.AUTHORITY_PARENT / ".staging-race").mkdir()
        return result

    monkeypatch.setattr(seal, "_inventory_fd", mutate_after_snapshot)
    with pytest.raises(seal.ParentSealError) as caught:
        seal.seal_parent()
    assert caught.value.code == "PARENT_SEAL_DURABILITY_UNKNOWN"
    assert stat.S_IMODE(os.lstat(seal.AUTHORITY_PARENT).st_mode) == 0o555


def test_main_requires_exact_acknowledgements(
    seal: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(seal, "_bind_live_execution", lambda _descriptor: None)
    called = False

    def forbidden_seal() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(seal, "seal_parent", forbidden_seal)
    assert (
        seal.main(
            [
                "seal",
                "--parent-seal-launcher-fd",
                "8",
                "--acknowledgement",
                "wrong",
            ]
        )
        == 1
    )
    assert called is False
    assert "PARENT_SEAL_ACKNOWLEDGEMENT_INVALID" in capsys.readouterr().err


def test_live_execution_rejects_non_root(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1)
    with pytest.raises(seal.ParentSealError, match="PARENT_SEAL_ROOT_REQUIRED"):
        seal._bind_live_execution(3)


def test_ancestor_symlink_or_writable_directory_is_rejected(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    writable = tmp_path / "writable-ancestor"
    writable.mkdir()
    writable.chmod(0o777)
    monkeypatch.setattr(
        seal,
        "_ancestor_paths",
        lambda _path: (writable, seal.AUTHORITY_PARENT),
    )
    with pytest.raises(seal.ParentSealError, match="AUTHORITY_PARENT_SECURITY_INVALID"):
        seal.audit_parent()

    target = tmp_path / "safe-target"
    target.mkdir()
    target.chmod(0o755)
    symlink = tmp_path / "ancestor-link"
    symlink.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(
        seal,
        "_ancestor_paths",
        lambda _path: (symlink, seal.AUTHORITY_PARENT),
    )
    with pytest.raises(seal.ParentSealError, match="AUTHORITY_PARENT_SECURITY_INVALID"):
        seal.audit_parent()


def test_live_execution_binds_fixed_helper_python_and_rejects_tamper(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed_root = tmp_path / "vista-authority-parent-seal-r1"
    installed_root.mkdir(mode=0o755)
    helper = installed_root / "vista_authority_parent_seal.py"
    helper.write_bytes(b"# reviewed helper\n")
    helper.chmod(0o500)
    launcher = installed_root / "launch-vista-authority-parent-seal"
    launcher.write_bytes(b"\x7fELFreviewed parent launcher")
    launcher.chmod(0o555)
    installed_root.chmod(0o555)
    python = Path(os.readlink("/proc/self/exe")).resolve(strict=True)
    python_raw = python.read_bytes()
    root_metadata = os.lstat(installed_root)
    helper_metadata = os.lstat(helper)
    launcher_metadata = os.lstat(launcher)
    real_fstat = os.fstat
    real_lstat = os.lstat

    def root_owned(metadata: os.stat_result) -> os.stat_result:
        values = list(metadata)
        values[4] = 0
        values[5] = 0
        return os.stat_result(values)

    def trusted_fstat(descriptor: int) -> os.stat_result:
        metadata = real_fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) in {
            (root_metadata.st_dev, root_metadata.st_ino),
            (helper_metadata.st_dev, helper_metadata.st_ino),
            (launcher_metadata.st_dev, launcher_metadata.st_ino),
        }:
            return root_owned(metadata)
        return metadata

    def trusted_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        metadata = real_lstat(path)
        if Path(path) in {installed_root, helper, launcher}:
            return root_owned(metadata)
        return metadata

    monkeypatch.setattr(seal, "INSTALLED_ROOT", installed_root)
    monkeypatch.setattr(seal, "INSTALLED_LAUNCHER", launcher)
    monkeypatch.setattr(seal, "INSTALLED_HELPER", helper)
    monkeypatch.setattr(seal, "PINNED_PYTHON", python)
    monkeypatch.setattr(
        seal, "PINNED_PYTHON_SHA256", hashlib.sha256(python_raw).hexdigest()
    )
    monkeypatch.setattr(seal, "PINNED_PYTHON_BYTES", len(python_raw))
    monkeypatch.setattr(seal, "__file__", str(helper))
    monkeypatch.setattr(seal, "ROOT_UID", 0)
    monkeypatch.setattr(seal, "ROOT_GID", 0)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "getegid", lambda: 0)
    monkeypatch.setattr(os, "fstat", trusted_fstat)
    monkeypatch.setattr(os, "lstat", trusted_lstat)
    monkeypatch.setattr(
        seal.sys,
        "flags",
        SimpleNamespace(isolated=1, no_user_site=1, dont_write_bytecode=1),
    )
    monkeypatch.setattr(os, "environ", dict(seal.PRODUCTION_ENVIRONMENT))

    descriptor = os.open(launcher, os.O_RDONLY | os.O_CLOEXEC)
    wrong = os.open(helper, os.O_RDONLY | os.O_CLOEXEC)
    try:
        seal._bind_live_execution(descriptor)
        with pytest.raises(
            seal.ParentSealError, match="held launcher identity differs"
        ):
            seal._bind_live_execution(wrong)
        helper.chmod(0o700)
        with pytest.raises(
            seal.ParentSealError, match="installed authority or held launcher"
        ):
            seal._bind_live_execution(descriptor)
        helper.chmod(0o500)
        monkeypatch.setattr(seal, "PINNED_PYTHON_SHA256", "0" * 64)
        with pytest.raises(seal.ParentSealError, match="pinned Python bytes differ"):
            seal._bind_live_execution(descriptor)
    finally:
        os.close(wrong)
        os.close(descriptor)


def test_open_regular_uses_nonblocking_nofollow(
    seal: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed_flags = 0

    def inspect_open(_path: Path, flags: int) -> int:
        nonlocal observed_flags
        observed_flags = flags
        raise OSError("stop after flag inspection")

    monkeypatch.setattr(os, "open", inspect_open)
    with pytest.raises(seal.ParentSealError, match="PARENT_SEAL_EXECUTION_INVALID"):
        seal._open_regular(Path("/fixed"))
    assert observed_flags & os.O_NONBLOCK
    assert observed_flags & os.O_NOFOLLOW


def test_source_never_relaxes_parent_permissions() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "os.fchmod(descriptor, SEALED_MODE)" in source
    assert "os.fchmod(descriptor, READY_MODE)" not in source
    assert "chmod(0o755" not in source
