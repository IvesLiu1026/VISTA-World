from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Iterator

import pytest

from tools.admin import vista_r8_ue57_authority_admin as authority_admin
from tools.admin import vista_r8_ue57_initial_bootstrap as initial_bootstrap


SOURCE = (
    Path(__file__).parents[1] / "admin" / "vista_r8_ue57_initial_bootstrap_launcher.c"
)
PUBLISH_OPERATION = "publish-initial-authorities"
PUBLISH_ACK = (
    "I acknowledge one irreversible append-only publication of the four "
    "externally reviewed VISTA R8 UE 5.7 initial authorities from an empty prefix."
)
RECONCILE_OPERATION = "reconcile-initial-authorities"
RECONCILE_ACK = (
    "I acknowledge candidate-free audit and fsync reconciliation of the existing "
    "VISTA R8 UE 5.7 initial-authority prefix without creating, deleting, or "
    "repairing any root."
)
RESUME_OPERATION = "resume-initial-authorities"
RESUME_ACK = (
    "I acknowledge candidate-free reconciliation followed by append-only resume "
    "of the externally reviewed VISTA R8 UE 5.7 initial-authority prefix."
)


def _pin(path: Path) -> tuple[str, int]:
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _c_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class LauncherFixture:
    def __init__(self, tmp_path: Path, *, wrong_euid: bool = False) -> None:
        self.root = tmp_path / "initial-root"
        self.root.mkdir(mode=0o700)
        self.python = Path(os.path.realpath(os.sys.executable))
        self.helper = self.root / "vista_r8_ue57_initial_bootstrap.py"
        self.helper.write_text(
            "import json, os, sys\n"
            "fds = [int(sys.argv[index]) for index in (3, 5, 7, 9, 11)]\n"
            "assert all(os.fstat(fd).st_nlink == 1 for fd in fds)\n"
            "print(json.dumps({'argv': sys.argv[1:]}))\n"
        )
        self.helper.chmod(0o500)
        helper_sha, helper_size = _pin(self.helper)
        python_sha, python_size = _pin(self.python)
        self.launcher = self.root / "bootstrap-r8-ue57-initial-authorities"
        uid, gid = os.getuid(), os.getgid()
        required_uid = uid + 1 if wrong_euid else uid
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
            "-DVISTA_R8_INITIAL_BOOTSTRAP_TESTING",
            f"-DVISTA_R8_INITIAL_TEST_ROOT={_c_string(str(self.root))}",
            f"-DVISTA_R8_INITIAL_TEST_PYTHON={_c_string(str(self.python))}",
            f"-DVISTA_R8_INITIAL_TEST_REQUIRED_EUID={required_uid}",
            f"-DVISTA_R8_INITIAL_TEST_REQUIRED_EGID={gid}",
            f"-DVISTA_R8_INITIAL_TEST_OWNER_UID={uid}",
            f"-DVISTA_R8_INITIAL_TEST_OWNER_GID={gid}",
            f"-DVISTA_R8_INITIAL_TEST_PYTHON_UID={self.python.stat().st_uid}",
            f"-DVISTA_R8_INITIAL_TEST_PYTHON_GID={self.python.stat().st_gid}",
            f'-DEXPECTED_HELPER_SHA256="{helper_sha}"',
            f"-DEXPECTED_HELPER_SIZE={helper_size}",
            f'-DEXPECTED_PYTHON_SHA256="{python_sha}"',
            f"-DEXPECTED_PYTHON_SIZE={python_size}",
            str(SOURCE),
            "-o",
            str(self.launcher),
        ]
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        self.launcher.chmod(0o500)
        launcher_sha, launcher_size = _pin(self.launcher)
        self.input_pin = self.root / "input-pin.json"
        document = {
            "components": {
                "helper": {
                    "path": str(self.helper),
                    "pin": {"sha256": helper_sha, "size_bytes": helper_size},
                },
                "launcher": {
                    "path": str(self.launcher),
                    "pin": {"sha256": launcher_sha, "size_bytes": launcher_size},
                },
                "python": {
                    "path": str(self.python),
                    "pin": {"sha256": python_sha, "size_bytes": python_size},
                },
            },
            "schema": "vista.r8-ue57-initial-bootstrap-input-pin/v2",
        }
        self.input_pin.write_bytes(
            (
                json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        )
        self.input_pin.chmod(0o444)
        self.lock = self.root / ".bootstrap.lock"
        self.lock.touch(mode=0o600)
        self.root.chmod(0o555)

    def run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.launcher), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={"PATH": "/usr/bin:/bin", "BASH_ENV": "/tmp/forbidden"},
        )


@pytest.fixture
def launcher(tmp_path: Path) -> Iterator[LauncherFixture]:
    yield LauncherFixture(tmp_path)


def test_input_schema_matches_both_python_producers_and_launcher() -> None:
    schema = "vista.r8-ue57-initial-bootstrap-input-pin/v2"
    assert authority_admin.INITIAL_BOOTSTRAP_INPUT_PIN_SCHEMA == schema
    assert initial_bootstrap.INPUT_PIN_SCHEMA == schema
    assert schema in SOURCE.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("operation", "acknowledgement"),
    [
        (PUBLISH_OPERATION, PUBLISH_ACK),
        (RECONCILE_OPERATION, RECONCILE_ACK),
        (RESUME_OPERATION, RESUME_ACK),
    ],
)
def test_closed_operations_exec_held_python_and_helper(
    launcher: LauncherFixture, operation: str, acknowledgement: str
) -> None:
    result = launcher.run(operation, acknowledgement)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["argv"][0] == operation
    assert output["argv"][-2:] == ["--acknowledgement", acknowledgement]
    assert "--launcher-fd" in output["argv"]
    assert "--helper-fd" in output["argv"]
    assert "--input-pin-fd" in output["argv"]
    assert "--python-fd" in output["argv"]
    assert "--lock-fd" in output["argv"]


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        (PUBLISH_OPERATION,),
        (PUBLISH_OPERATION, PUBLISH_ACK, "extra"),
        ("unknown", PUBLISH_ACK),
        (PUBLISH_OPERATION, "wrong"),
        (RECONCILE_OPERATION, PUBLISH_ACK),
        (RESUME_OPERATION, RECONCILE_ACK),
    ],
)
def test_wrong_argc_operation_or_ack_is_rejected(
    launcher: LauncherFixture, arguments: tuple[str, ...]
) -> None:
    result = launcher.run(*arguments)
    assert result.returncode == 126
    assert "INITIAL_BOOTSTRAP_LAUNCHER" in result.stderr


def test_wrong_euid_is_rejected(tmp_path: Path) -> None:
    fixture = LauncherFixture(tmp_path, wrong_euid=True)
    result = fixture.run(PUBLISH_OPERATION, PUBLISH_ACK)
    assert result.returncode == 126
    assert "EUID/EGID" in result.stderr


def test_input_self_helper_and_python_binding_tamper_is_rejected(
    launcher: LauncherFixture,
) -> None:
    launcher.root.chmod(0o755)
    launcher.input_pin.chmod(0o644)
    raw = launcher.input_pin.read_bytes().replace(b'"sha256":"', b'"sha256":"f', 1)
    launcher.input_pin.write_bytes(raw)
    launcher.input_pin.chmod(0o444)
    launcher.root.chmod(0o555)
    result = launcher.run(PUBLISH_OPERATION, PUBLISH_ACK)
    assert result.returncode == 126
    assert "input binding" in result.stderr


def test_busy_lock_is_rejected_without_waiting(launcher: LauncherFixture) -> None:
    descriptor = os.open(launcher.lock, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = launcher.run(PUBLISH_OPERATION, PUBLISH_ACK)
    finally:
        os.close(descriptor)
    assert result.returncode == 126
    assert "lock is busy" in result.stderr


def test_execution_from_byte_identical_noncanonical_self_is_rejected(
    launcher: LauncherFixture, tmp_path: Path
) -> None:
    copied = tmp_path / "copied-launcher"
    copied.write_bytes(launcher.launcher.read_bytes())
    copied.chmod(0o500)
    result = subprocess.run(
        [str(copied), PUBLISH_OPERATION, PUBLISH_ACK],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 126
    assert "live self differs" in result.stderr


@pytest.mark.parametrize("attack", ["extra", "mode", "hardlink", "symlink"])
def test_installed_inventory_attacks_are_rejected(
    launcher: LauncherFixture, attack: str
) -> None:
    launcher.root.chmod(0o755)
    if attack == "extra":
        extra = launcher.root / "extra"
        extra.write_text("extra")
        extra.chmod(0o444)
    elif attack == "mode":
        launcher.helper.chmod(0o555)
    elif attack == "hardlink":
        os.link(launcher.helper, launcher.root / "helper-alias")
    else:
        launcher.input_pin.unlink()
        launcher.input_pin.symlink_to(launcher.helper.name)
    launcher.root.chmod(0o555)
    result = launcher.run(PUBLISH_OPERATION, PUBLISH_ACK)
    assert result.returncode == 126


def test_binary_is_static_without_interp_or_needed(launcher: LauncherFixture) -> None:
    result = subprocess.run(
        ["/usr/bin/readelf", "-l", "-d", str(launcher.launcher)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0
    assert "INTERP" not in result.stdout
    assert "NEEDED" not in result.stdout
    assert stat.S_IMODE(launcher.launcher.stat().st_mode) == 0o500


def test_source_has_no_shell_subprocess_or_caller_path_interface() -> None:
    raw = SOURCE.read_text()
    assert "system(" not in raw
    assert "popen(" not in raw
    assert "/bin/sh" not in raw
    assert "candidate_root" not in raw
    assert "reviewed_sha" not in raw
