from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import subprocess
import time
from typing import Iterator

import pytest


SOURCE = (
    Path(__file__).parents[1] / "admin" / "vista_r8_ue57_initial_bootstrap_installer.c"
)
INSTALL_OPERATION = "install-initial-bootstrap"
INSTALL_ACK = (
    "I acknowledge one fresh no-replace installation of the externally "
    "reviewed VISTA R8 UE 5.7 initial bootstrap authority."
)
RECONCILE_OPERATION = "reconcile-initial-bootstrap"
RECONCILE_ACK = (
    "I acknowledge candidate-free fsync reconciliation of the existing VISTA "
    "R8 UE 5.7 initial bootstrap authority without creating, deleting, "
    "renaming, chmodding, or repairing it."
)
INSTALLER_NAME = "install-reconcile-r8-ue57-initial-bootstrap"
LAUNCHER_NAME = "bootstrap-r8-ue57-initial-authorities"
HELPER_NAME = "vista_r8_ue57_initial_bootstrap.py"
INPUT_NAME = "input-pin.json"
LOCK_NAME = ".bootstrap.lock"


def _pin(raw: bytes) -> tuple[str, int]:
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _c_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class InstallerFixture:
    def __init__(
        self,
        tmp_path: Path,
        *,
        wrong_euid: bool = False,
        wrong_review_owner: bool = False,
    ) -> None:
        uid, gid = os.getuid(), os.getgid()
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.root_parent = tmp_path / "root"
        self.root_parent.mkdir(mode=0o700)
        self.self_root = self.root_parent / "installer-root"
        self.self_root.mkdir(mode=0o700)
        self.candidate = tmp_path / "review-candidate"
        self.candidate.mkdir(mode=0o700)
        self.final = self.root_parent / "initial-root"
        self.launcher_raw = b"ELF-reviewed-static-bootstrap-launcher\n"
        self.helper_raw = b"#!/usr/bin/python3\n# reviewed helper\n" + b"x" * 20_000
        self.input_raw = b'{"schema":"reviewed-input"}\n'
        self.candidate_files = {
            LAUNCHER_NAME: (self.launcher_raw, 0o555),
            HELPER_NAME: (self.helper_raw, 0o444),
            INPUT_NAME: (self.input_raw, 0o444),
        }
        for name, (raw, mode) in self.candidate_files.items():
            path = self.candidate / name
            path.write_bytes(raw)
            path.chmod(mode)
        self.candidate.chmod(0o555)
        launcher_sha, launcher_size = _pin(self.launcher_raw)
        helper_sha, helper_size = _pin(self.helper_raw)
        input_sha, input_size = _pin(self.input_raw)
        self.installer = self.self_root / INSTALLER_NAME
        required_uid = uid + 1 if wrong_euid else uid
        review_uid = uid + 1 if wrong_review_owner else uid
        command = [
            "/usr/bin/gcc-12",
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-static",
            "-s",
            "-Wl,--build-id=none",
            "-x",
            "c",
            "-DVISTA_R8_INITIAL_INSTALLER_TESTING",
            f"-DVISTA_R8_TEST_SELF_ROOT={_c_string(str(self.self_root))}",
            f"-DVISTA_R8_TEST_CANDIDATE_ROOT={_c_string(str(self.candidate))}",
            f"-DVISTA_R8_TEST_FINAL_ROOT={_c_string(str(self.final))}",
            f"-DVISTA_R8_TEST_ROOT_PARENT={_c_string(str(self.root_parent))}",
            f"-DVISTA_R8_TEST_REQUIRED_EUID={required_uid}",
            f"-DVISTA_R8_TEST_REQUIRED_EGID={gid}",
            f"-DVISTA_R8_TEST_REVIEW_UID={review_uid}",
            f"-DVISTA_R8_TEST_REVIEW_GID={gid}",
            f'-DEXPECTED_LAUNCHER_SHA256="{launcher_sha}"',
            f"-DEXPECTED_LAUNCHER_SIZE={launcher_size}",
            f'-DEXPECTED_HELPER_SHA256="{helper_sha}"',
            f"-DEXPECTED_HELPER_SIZE={helper_size}",
            f'-DEXPECTED_INPUT_PIN_SHA256="{input_sha}"',
            f"-DEXPECTED_INPUT_PIN_SIZE={input_size}",
            str(SOURCE),
            "-o",
            str(self.installer),
        ]
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        self.installer.chmod(0o500)
        self.self_root.chmod(0o555)

    def run(
        self,
        operation: str = INSTALL_OPERATION,
        acknowledgement: str = INSTALL_ACK,
        *,
        failpoint: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = {"PATH": "/usr/bin:/bin", "LANG": "C"}
        if failpoint is not None:
            env["VISTA_R8_INITIAL_INSTALLER_FAILPOINT"] = failpoint
        return subprocess.run(
            [str(self.installer), operation, acknowledgement],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

    def assert_final(self) -> None:
        assert stat.S_IMODE(self.final.stat().st_mode) == 0o555
        assert {path.name for path in self.final.iterdir()} == {
            LAUNCHER_NAME,
            HELPER_NAME,
            INPUT_NAME,
            LOCK_NAME,
        }
        expected = {
            LAUNCHER_NAME: (self.launcher_raw, 0o500),
            HELPER_NAME: (self.helper_raw, 0o500),
            INPUT_NAME: (self.input_raw, 0o444),
            LOCK_NAME: (b"", 0o600),
        }
        for name, (raw, mode) in expected.items():
            path = self.final / name
            assert path.read_bytes() == raw
            assert stat.S_IMODE(path.stat().st_mode) == mode
            assert path.stat().st_nlink == 1

    def staging_paths(self) -> list[Path]:
        return list(self.root_parent.glob(".vista-r8-ue57-initial-bootstrap.staging-*"))


@pytest.fixture
def installer(tmp_path: Path) -> Iterator[InstallerFixture]:
    yield InstallerFixture(tmp_path)


def _start_paused_install(
    installer: InstallerFixture,
    pause_point: str,
    *,
    failpoint: str | None = None,
    ready_path: Path | None = None,
) -> subprocess.Popen[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "VISTA_R8_INITIAL_INSTALLER_PAUSE_POINT": pause_point,
        "VISTA_R8_INITIAL_INSTALLER_PAUSE_US": "1000000",
    }
    if failpoint is not None:
        env["VISTA_R8_INITIAL_INSTALLER_FAILPOINT"] = failpoint
    if ready_path is not None:
        env["VISTA_R8_INITIAL_INSTALLER_PAUSE_READY_PATH"] = str(ready_path)
    return subprocess.Popen(
        [str(installer.installer), INSTALL_OPERATION, INSTALL_ACK],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def _wait_for_path(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if path.exists():
            return
        assert process.poll() is None, process.stderr.read() if process.stderr else ""
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def _create_final_clone(installer: InstallerFixture, destination: Path) -> int:
    destination.mkdir(mode=0o700)
    replacement_files = {
        LAUNCHER_NAME: (installer.launcher_raw, 0o500),
        HELPER_NAME: (installer.helper_raw, 0o500),
        INPUT_NAME: (installer.input_raw, 0o444),
        LOCK_NAME: (b"", 0o600),
    }
    for name, (raw, mode) in replacement_files.items():
        path = destination / name
        path.write_bytes(raw)
        path.chmod(mode)
    destination.chmod(0o555)
    return destination.stat().st_ino


def test_fresh_install_and_candidate_free_reconcile(
    installer: InstallerFixture,
) -> None:
    result = installer.run()
    assert result.returncode == 0, result.stderr
    assert result.stdout == "installed-initial-bootstrap\n"
    installer.assert_final()
    assert installer.staging_paths() == []

    installer.candidate.chmod(0o700)
    for child in installer.candidate.iterdir():
        child.unlink()
    installer.candidate.rmdir()
    reconciled = installer.run(RECONCILE_OPERATION, RECONCILE_ACK)
    assert reconciled.returncode == 0, reconciled.stderr
    assert reconciled.stdout == "reconciled-initial-bootstrap\n"
    installer.assert_final()


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        (INSTALL_OPERATION,),
        (INSTALL_OPERATION, INSTALL_ACK, "extra"),
        ("unknown", INSTALL_ACK),
        (INSTALL_OPERATION, "wrong"),
        (RECONCILE_OPERATION, INSTALL_ACK),
    ],
)
def test_wrong_argc_operation_or_ack_fails(
    installer: InstallerFixture, arguments: tuple[str, ...]
) -> None:
    result = subprocess.run(
        [str(installer.installer), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 126
    assert "R8_INITIAL_INSTALLER" in result.stderr
    assert not installer.final.exists()


def test_wrong_euid_and_copied_self_fail(tmp_path: Path) -> None:
    wrong = InstallerFixture(tmp_path / "wrong", wrong_euid=True)
    result = wrong.run()
    assert result.returncode == 126
    assert "EUID" in result.stderr

    copied = tmp_path / "copied-installer"
    copied.write_bytes(wrong.installer.read_bytes())
    copied.chmod(0o500)
    result = subprocess.run(
        [str(copied), INSTALL_OPERATION, INSTALL_ACK],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 126


@pytest.mark.parametrize(
    "attack",
    [
        "extra",
        "missing",
        "symlink",
        "hardlink",
        "fifo",
        "mode",
        "oversize",
        "sparse",
    ],
)
def test_candidate_attacks_fail_without_staging(
    installer: InstallerFixture, attack: str
) -> None:
    installer.candidate.chmod(0o755)
    helper = installer.candidate / HELPER_NAME
    if attack == "extra":
        (installer.candidate / "extra").write_bytes(b"x")
    elif attack == "missing":
        helper.unlink()
    elif attack == "symlink":
        helper.unlink()
        helper.symlink_to(INPUT_NAME)
    elif attack == "hardlink":
        os.link(helper, installer.candidate.parent / "helper-hardlink-alias")
    elif attack == "fifo":
        helper.unlink()
        os.mkfifo(helper, 0o444)
    elif attack == "mode":
        helper.chmod(0o400)
    elif attack == "oversize":
        helper.chmod(0o644)
        helper.write_bytes(installer.helper_raw * 2)
        helper.chmod(0o444)
    else:
        helper.unlink()
        with helper.open("wb") as stream:
            stream.seek(len(installer.helper_raw) - 1)
            stream.write(b"\0")
        helper.chmod(0o444)
    installer.candidate.chmod(0o555)
    result = installer.run()
    assert result.returncode == 126
    assert not installer.final.exists()
    assert installer.staging_paths() == []


def test_wrong_candidate_owner_contract_fails(tmp_path: Path) -> None:
    fixture = InstallerFixture(tmp_path, wrong_review_owner=True)
    result = fixture.run()
    assert result.returncode == 126
    assert "candidate" in result.stderr


def test_self_inventory_and_parent_mode_fail_closed(
    installer: InstallerFixture,
) -> None:
    installer.self_root.chmod(0o755)
    extra = installer.self_root / "extra"
    extra.write_bytes(b"x")
    extra.chmod(0o444)
    installer.self_root.chmod(0o555)
    assert installer.run().returncode == 126
    installer.self_root.chmod(0o755)
    extra.unlink()
    installer.self_root.chmod(0o555)
    installer.root_parent.chmod(0o755)
    assert installer.run().returncode == 126


def test_collision_never_replaces_and_cleans_private_staging(
    installer: InstallerFixture,
) -> None:
    installer.final.mkdir(mode=0o700)
    sentinel = installer.final / "sentinel"
    sentinel.write_bytes(b"keep")
    result = installer.run()
    assert result.returncode == 126
    assert sentinel.read_bytes() == b"keep"
    assert installer.staging_paths() == []


def test_open_failure_after_mkdir_cleans_unopened_private_staging(
    installer: InstallerFixture,
) -> None:
    result = installer.run(failpoint="before_staging_open")
    assert result.returncode == 126
    assert "installation failed before rename" in result.stderr
    assert not installer.final.exists()
    assert installer.staging_paths() == []

    retry = installer.run()
    assert retry.returncode == 0, retry.stderr
    installer.assert_final()


def test_staging_path_swap_before_open_never_binds_replacement(
    installer: InstallerFixture,
) -> None:
    process = _start_paused_install(installer, "after_staging_identity")
    deadline = time.monotonic() + 3
    staging_paths: list[Path] = []
    while time.monotonic() < deadline:
        staging_paths = installer.staging_paths()
        if staging_paths:
            break
        assert process.poll() is None, process.stderr.read() if process.stderr else ""
        time.sleep(0.01)
    assert len(staging_paths) == 1

    staging_path = staging_paths[0]
    held_original = installer.root_parent / ".held-original-staging"
    original_inode = staging_path.stat().st_ino
    staging_path.rename(held_original)
    staging_path.mkdir(mode=0o700)
    replacement_inode = staging_path.stat().st_ino

    _stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 126, stderr
    assert "installation failed before rename" in stderr
    assert not installer.final.exists()
    assert held_original.stat().st_ino == original_inode
    assert staging_path.stat().st_ino == replacement_inode


@pytest.mark.parametrize("failpoint", ["before_staging_open", "before_rename"])
def test_cleanup_late_path_swap_never_deletes_replacement(
    installer: InstallerFixture, failpoint: str
) -> None:
    ready_path = installer.candidate.parent / f".{failpoint}-cleanup-ready"
    process = _start_paused_install(
        installer,
        "before_cleanup_final_rebind",
        failpoint=failpoint,
        ready_path=ready_path,
    )
    _wait_for_path(ready_path, process)
    staging_paths = installer.staging_paths()
    assert len(staging_paths) == 1
    staging_path = staging_paths[0]
    assert list(staging_path.iterdir()) == []

    held_original = installer.root_parent / f".held-{failpoint}-cleanup"
    original_inode = staging_path.stat().st_ino
    staging_path.rename(held_original)
    staging_path.mkdir(mode=0o700)
    replacement_inode = staging_path.stat().st_ino

    _stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 126, stderr
    assert "installation failed before rename" in stderr
    assert not installer.final.exists()
    assert held_original.stat().st_ino == original_inode
    assert staging_path.stat().st_ino == replacement_inode


def test_final_path_swap_before_reopen_never_binds_replacement(
    installer: InstallerFixture,
) -> None:
    replacement = installer.root_parent / ".replacement-final"
    replacement_inode = _create_final_clone(installer, replacement)

    process = _start_paused_install(installer, "after_rename_before_reopen")
    _wait_for_path(installer.final, process)
    promoted_inode = installer.final.stat().st_ino
    held_original = installer.root_parent / ".held-promoted-final"
    installer.final.rename(held_original)
    replacement.rename(installer.final)

    _stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 126, stderr
    assert "durability unknown; reconcile required" in stderr
    assert held_original.stat().st_ino == promoted_inode
    assert installer.final.stat().st_ino == replacement_inode
    installer.assert_final()


def test_final_path_swap_after_first_audit_fails_final_close(
    installer: InstallerFixture,
) -> None:
    replacement = installer.root_parent / ".late-replacement-final"
    replacement_inode = _create_final_clone(installer, replacement)
    ready_path = installer.candidate.parent / ".first-final-audit-ready"
    process = _start_paused_install(
        installer,
        "after_first_final_audit",
        ready_path=ready_path,
    )
    _wait_for_path(ready_path, process)

    promoted_inode = installer.final.stat().st_ino
    held_original = installer.root_parent / ".held-after-first-final-audit"
    installer.final.rename(held_original)
    replacement.rename(installer.final)

    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 126, stderr
    assert stdout == ""
    assert "durability unknown; reconcile required" in stderr
    assert held_original.stat().st_ino == promoted_inode
    assert installer.final.stat().st_ino == replacement_inode
    installer.assert_final()


def test_child_mutation_after_first_audit_fails_final_full_audit(
    installer: InstallerFixture,
) -> None:
    ready_path = installer.candidate.parent / ".first-audit-mutation-ready"
    process = _start_paused_install(
        installer,
        "after_first_final_audit",
        ready_path=ready_path,
    )
    _wait_for_path(ready_path, process)

    directory_info = installer.final.stat()
    helper = installer.final / HELPER_NAME
    helper.chmod(0o700)
    helper.write_bytes(b"mutated after first final audit\n")
    helper.chmod(0o500)
    assert installer.final.stat().st_ino == directory_info.st_ino
    assert installer.final.stat().st_mtime_ns == directory_info.st_mtime_ns

    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 126, stderr
    assert stdout == ""
    assert "durability unknown; reconcile required" in stderr


def test_ambiguous_rename_result_never_chmods_or_deletes_final(
    installer: InstallerFixture,
) -> None:
    result = installer.run(failpoint="ambiguous_rename_result")
    assert result.returncode == 126
    assert "durability unknown; reconcile required" in result.stderr
    installer.assert_final()
    assert installer.staging_paths() == []
    reconciled = installer.run(RECONCILE_OPERATION, RECONCILE_ACK)
    assert reconciled.returncode == 0, reconciled.stderr
    installer.assert_final()


@pytest.mark.parametrize(
    "failpoint",
    [
        "before_rename",
        "after_rename",
        "before_final_fsync",
        "after_final_fsync",
        "before_parent_fsync",
        "after_parent_fsync",
        "before_reopen",
        "after_reopen",
    ],
)
def test_failure_boundaries_preserve_checkpoint_and_reconcile(
    installer: InstallerFixture, failpoint: str
) -> None:
    result = installer.run(failpoint=failpoint)
    assert result.returncode == 126
    if failpoint == "before_rename":
        assert not installer.final.exists()
        assert installer.staging_paths() == []
        retry = installer.run()
        assert retry.returncode == 0, retry.stderr
    else:
        installer.assert_final()
        assert installer.staging_paths() == []
        retry = installer.run(RECONCILE_OPERATION, RECONCILE_ACK)
        assert retry.returncode == 0, retry.stderr
    installer.assert_final()


def test_candidate_mutation_while_held_fails_before_rename(
    installer: InstallerFixture,
) -> None:
    process = subprocess.Popen(
        [str(installer.installer), INSTALL_OPERATION, INSTALL_ACK],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "VISTA_R8_INITIAL_INSTALLER_PAUSE_US": "500000",
        },
    )
    time.sleep(0.1)
    installer.candidate.chmod(0o755)
    helper = installer.candidate / HELPER_NAME
    helper.chmod(0o644)
    helper.write_bytes(b"mutated reviewed helper\n")
    helper.chmod(0o444)
    installer.candidate.chmod(0o555)
    _stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 126, stderr
    assert not installer.final.exists()
    assert installer.staging_paths() == []


def test_binary_is_static_and_source_has_no_execution_or_network_api(
    installer: InstallerFixture,
) -> None:
    result = subprocess.run(
        ["/usr/bin/readelf", "-l", "-d", str(installer.installer)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0
    assert "INTERP" not in result.stdout
    assert "NEEDED" not in result.stdout
    raw = SOURCE.read_text()
    assert "/var/lib/vista-r8-native-builder-r2/phase-b-slot/published/" in raw
    assert "/var/lib/vista-r8-native-builder-r1/" not in raw
    assert '"initial-bootstrap-candidate"' in raw
    assert "#define REVIEW_UID ((uid_t)997)" in raw
    assert "#define REVIEW_GID ((gid_t)997)" in raw
    assert "VISTA_R8_TEST_REVIEW_UID" in raw
    assert "VISTA_R8_TEST_REVIEW_GID" in raw
    assert "vista-r8-ue57-initial-bootstrap-review-candidate-20260830a" not in raw
    for forbidden in ("system(", "popen(", "execve", "socket(", "/bin/sh"):
        assert forbidden not in raw
    assert "argv[3]" not in raw
