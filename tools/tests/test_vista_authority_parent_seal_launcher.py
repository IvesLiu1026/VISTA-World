from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "admin"
    / "vista_authority_parent_seal_launcher.c"
)
GCC = Path("/usr/bin/gcc-12")
READELF = Path("/usr/bin/readelf")
PYTHON = Path("/usr/bin/python3.10")
LAUNCHER_NAME = "launch-vista-authority-parent-seal"
HELPER_NAME = "vista_authority_parent_seal.py"
PYTHON_PIN = (
    "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86",
    5_917_224,
)
PRODUCTION_HELPER_PIN = (
    "3c2f7f582a50da5bfa2adaece3e0e62443a7f00891f43f646f734e931a57bfd4",
    28_146,
)
SEAL_ACK = (
    "I confirm no VISTA authority publisher is running and acknowledge one "
    "irreversible seal of /data/vista-authorities from 0755 to 0555."
)
RECONCILE_ACK = (
    "I acknowledge an audit-and-fsync-only reconciliation of the already "
    "sealed /data/vista-authorities directory."
)


def _pin(raw: bytes) -> tuple[str, int]:
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _quote(name: str, value: str) -> str:
    assert '"' not in value and "\\" not in value
    return f'-D{name}="{value}"'


def _production_pin_flags() -> list[str]:
    return [
        _quote("EXPECTED_PYTHON_SHA256", PYTHON_PIN[0]),
        f"-DEXPECTED_PYTHON_SIZE={PYTHON_PIN[1]}",
        _quote("EXPECTED_HELPER_SHA256", PRODUCTION_HELPER_PIN[0]),
        f"-DEXPECTED_HELPER_SIZE={PRODUCTION_HELPER_PIN[1]}",
    ]


def _helper_bytes() -> bytes:
    return (
        "import os, sys\n"
        "assert sys.flags.isolated == 1\n"
        "assert sys.flags.no_user_site == 1\n"
        "assert sys.dont_write_bytecode\n"
        "assert sys.argv[1] in {'audit', 'seal', 'reconcile'}\n"
        "assert '--parent-seal-launcher-fd' in sys.argv\n"
        "i = sys.argv.index('--parent-seal-launcher-fd')\n"
        "assert int(sys.argv[i + 1]) >= 3\n"
        "os.fstat(int(sys.argv[i + 1]))\n"
        "if sys.argv[1] == 'audit': assert len(sys.argv) == 4\n"
        "else: assert '--acknowledgement' in sys.argv and len(sys.argv) == 6\n"
        "raise SystemExit(0)\n"
    ).encode()


def _compile_test_launcher(root: Path, helper_pin: tuple[str, int]) -> Path:
    uid = os.getuid()
    gid = os.getgid()
    python_pin = _pin(PYTHON.read_bytes())
    output = root / LAUNCHER_NAME
    subprocess.run(
        [
            str(GCC),
            "-std=c11",
            "-O2",
            "-static",
            "-Wall",
            "-Wextra",
            "-Werror",
            _quote("EXPECTED_PYTHON_SHA256", python_pin[0]),
            f"-DEXPECTED_PYTHON_SIZE={python_pin[1]}",
            "-DVISTA_PARENT_SEAL_LAUNCHER_TESTING=1",
            _quote("VISTA_PARENT_SEAL_TEST_ROOT", str(root)),
            f"-DVISTA_PARENT_SEAL_TEST_REQUIRED_EUID={uid}",
            f"-DVISTA_PARENT_SEAL_TEST_REQUIRED_EGID={gid}",
            f"-DVISTA_PARENT_SEAL_TEST_OWNER_UID={uid}",
            f"-DVISTA_PARENT_SEAL_TEST_OWNER_GID={gid}",
            _quote("VISTA_PARENT_SEAL_TEST_HELPER_SHA256", helper_pin[0]),
            f"-DVISTA_PARENT_SEAL_TEST_HELPER_SIZE={helper_pin[1]}",
            str(SOURCE),
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    output.chmod(0o555)
    return output


def _build_root(tmp_path: Path) -> tuple[Path, Path, Path]:
    if not GCC.is_file() or not PYTHON.is_file():
        pytest.skip("reviewed GCC/Python unavailable")
    root = tmp_path / "vista-authority-parent-seal-r1"
    root.mkdir()
    helper = root / HELPER_NAME
    raw = _helper_bytes()
    helper.write_bytes(raw)
    helper.chmod(0o500)
    launcher = _compile_test_launcher(root, _pin(raw))
    root.chmod(0o555)
    return root, launcher, helper


def _run(
    launcher: Path, *args: str, timeout: float = 3
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(launcher), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_source_contract_is_fixed_native_and_matches_python_helper() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    joined = re.sub(r'"\s*\\?\s*"', "", source)
    assert "/root/vista-authority-parent-seal-r1" in source
    assert LAUNCHER_NAME in source
    assert HELPER_NAME in source
    assert PYTHON_PIN[0] not in source
    assert PRODUCTION_HELPER_PIN[0] not in source
    for macro in (
        "EXPECTED_PYTHON_SHA256",
        "EXPECTED_PYTHON_SIZE",
        "EXPECTED_HELPER_SHA256",
        "EXPECTED_HELPER_SIZE",
    ):
        assert f'#error "{macro} is required"' in source
    assert SEAL_ACK in joined
    assert RECONCILE_ACK in joined
    assert "SYS_execveat" in source
    assert "O_NOFOLLOW" in source
    assert "O_NONBLOCK" in source
    assert "exact_inventory" in source
    assert '"--parent-seal-launcher-fd"' in source
    for forbidden in ("system(", "popen(", "fork(", "/bin/sh", "sha256sum"):
        assert forbidden not in source


@pytest.mark.parametrize(
    "args",
    [
        ("audit",),
        ("seal", SEAL_ACK),
        ("reconcile", RECONCILE_ACK),
    ],
)
def test_closed_operations_exec_held_python_and_helper(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    _root, launcher, _helper = _build_root(tmp_path)
    result = _run(launcher, *args)
    assert result.returncode == 0, result.stderr


def test_launcher_is_static_without_interpreter(tmp_path: Path) -> None:
    _root, launcher, _helper = _build_root(tmp_path)
    headers = subprocess.run(
        [str(READELF), "-lW", str(launcher)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    dynamic = subprocess.run(
        [str(READELF), "-dW", str(launcher)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert " INTERP " not in headers
    assert "Requesting program interpreter" not in headers
    assert "(NEEDED)" not in dynamic
    assert "There is no dynamic section in this file." in dynamic


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("audit", "extra"),
        ("seal",),
        ("seal", "wrong"),
        ("reconcile", "wrong"),
        ("unknown",),
    ],
)
def test_wrong_operation_argc_or_ack_is_rejected(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    _root, launcher, _helper = _build_root(tmp_path)
    assert _run(launcher, *args).returncode == 126


@pytest.mark.parametrize(
    "mutation", ["extra", "symlink", "hardlink", "mode", "tamper", "fifo", "huge"]
)
def test_exact_helper_contract_rejects_tamper_without_blocking(
    tmp_path: Path, mutation: str
) -> None:
    root, launcher, helper = _build_root(tmp_path)
    root.chmod(0o700)
    if mutation == "extra":
        extra = root / "extra"
        extra.write_bytes(b"x")
        extra.chmod(0o500)
    elif mutation == "symlink":
        helper.unlink()
        target = tmp_path / "target"
        target.write_bytes(_helper_bytes())
        target.chmod(0o500)
        helper.symlink_to(target)
    elif mutation == "hardlink":
        raw = helper.read_bytes()
        helper.unlink()
        original = tmp_path / "original"
        original.write_bytes(raw)
        original.chmod(0o500)
        os.link(original, helper)
    elif mutation == "mode":
        helper.chmod(0o700)
    elif mutation == "tamper":
        helper.chmod(0o700)
        raw = bytearray(helper.read_bytes())
        raw[-1] ^= 1
        helper.write_bytes(raw)
        helper.chmod(0o500)
    elif mutation == "fifo":
        helper.unlink()
        os.mkfifo(helper, 0o500)
    elif mutation == "huge":
        helper.unlink()
        with helper.open("wb") as stream:
            stream.truncate(17 * 1024 * 1024)
        helper.chmod(0o500)
    root.chmod(0o555)
    result = _run(launcher, "audit", timeout=2)
    assert result.returncode == 126


def test_fixed_self_path_must_match_proc_self_exe(tmp_path: Path) -> None:
    root, launcher, _helper = _build_root(tmp_path)
    copy = tmp_path / "copied-launcher"
    shutil.copyfile(launcher, copy)
    copy.chmod(0o555)
    result = _run(copy, "audit")
    assert result.returncode == 126
    assert "live self identity differs" in result.stderr
    assert root.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="requires non-root runner")
def test_production_binary_rejects_nonroot_before_root_traversal(
    tmp_path: Path,
) -> None:
    output = tmp_path / "production-parent-seal"
    subprocess.run(
        [
            str(GCC),
            "-std=c11",
            "-O2",
            "-static",
            "-Wall",
            "-Wextra",
            "-Werror",
            *_production_pin_flags(),
            str(SOURCE),
            "-o",
            str(output),
        ],
        check=True,
    )
    result = _run(output, "audit")
    assert result.returncode == 126
    assert "root EUID and EGID required" in result.stderr


@pytest.mark.parametrize(
    ("payload", "sha256"),
    [
        (
            b"abc",
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        ),
        (
            b"a" * 1_000_000,
            "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
        ),
    ],
    ids=("abc", "million-a"),
)
def test_internal_sha256_known_vectors(
    tmp_path: Path, payload: bytes, sha256: str
) -> None:
    harness_source = tmp_path / "harness.c"
    harness = tmp_path / "harness"
    harness_source.write_text(
        "#define main parent_seal_launcher_main\n"
        f'#include "{SOURCE}"\n'
        "#undef main\n"
        "int main(int argc, char **argv) {\n"
        "  fixed_pin pin; int fd; char *end = 0; long long size;\n"
        "  if (argc != 4) return 2;\n"
        "  size = strtoll(argv[2], &end, 10); if (!end || *end) return 2;\n"
        "  pin.sha256 = argv[3]; pin.size_bytes = (off_t)size;\n"
        "  fd = open(argv[1], O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);\n"
        "  return fd >= 0 && verify_pin(fd, &pin) == 0 ? 0 : 3;\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            str(GCC),
            "-std=c11",
            "-O2",
            "-static",
            "-Wall",
            "-Wextra",
            "-Werror",
            *_production_pin_flags(),
            str(harness_source),
            "-o",
            str(harness),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    candidate = tmp_path / "candidate"
    candidate.write_bytes(payload)
    assert hashlib.sha256(payload).hexdigest() == sha256
    assert (
        subprocess.run(
            [str(harness), str(candidate), str(len(payload)), sha256],
            check=False,
            timeout=2,
        ).returncode
        == 0
    )
    candidate.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    assert (
        subprocess.run(
            [str(harness), str(candidate), str(len(payload)), sha256],
            check=False,
            timeout=2,
        ).returncode
        == 3
    )


@pytest.mark.parametrize(
    "missing",
    [
        "VISTA_PARENT_SEAL_TEST_ROOT",
        "VISTA_PARENT_SEAL_TEST_REQUIRED_EUID",
        "VISTA_PARENT_SEAL_TEST_REQUIRED_EGID",
        "VISTA_PARENT_SEAL_TEST_OWNER_UID",
        "VISTA_PARENT_SEAL_TEST_OWNER_GID",
        "VISTA_PARENT_SEAL_TEST_HELPER_SHA256",
        "VISTA_PARENT_SEAL_TEST_HELPER_SIZE",
    ],
)
def test_testing_build_requires_all_test_contract_macros(
    tmp_path: Path, missing: str
) -> None:
    values = {
        "VISTA_PARENT_SEAL_TEST_ROOT": _quote(
            "VISTA_PARENT_SEAL_TEST_ROOT", "/tmp/test-root"
        ),
        "VISTA_PARENT_SEAL_TEST_REQUIRED_EUID": "-DVISTA_PARENT_SEAL_TEST_REQUIRED_EUID=1",
        "VISTA_PARENT_SEAL_TEST_REQUIRED_EGID": "-DVISTA_PARENT_SEAL_TEST_REQUIRED_EGID=1",
        "VISTA_PARENT_SEAL_TEST_OWNER_UID": "-DVISTA_PARENT_SEAL_TEST_OWNER_UID=1",
        "VISTA_PARENT_SEAL_TEST_OWNER_GID": "-DVISTA_PARENT_SEAL_TEST_OWNER_GID=1",
        "VISTA_PARENT_SEAL_TEST_HELPER_SHA256": _quote(
            "VISTA_PARENT_SEAL_TEST_HELPER_SHA256", "1" * 64
        ),
        "VISTA_PARENT_SEAL_TEST_HELPER_SIZE": "-DVISTA_PARENT_SEAL_TEST_HELPER_SIZE=1",
    }
    python_pin = _pin(PYTHON.read_bytes())
    result = subprocess.run(
        [
            str(GCC),
            "-std=c11",
            "-DVISTA_PARENT_SEAL_LAUNCHER_TESTING=1",
            _quote("EXPECTED_PYTHON_SHA256", python_pin[0]),
            f"-DEXPECTED_PYTHON_SIZE={python_pin[1]}",
            *(value for key, value in values.items() if key != missing),
            "-c",
            str(SOURCE),
            "-o",
            str(tmp_path / "missing.o"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert f"{missing} is required" in result.stderr


@pytest.mark.parametrize(
    "missing",
    [
        "EXPECTED_PYTHON_SHA256",
        "EXPECTED_PYTHON_SIZE",
        "EXPECTED_HELPER_SHA256",
        "EXPECTED_HELPER_SIZE",
    ],
)
def test_production_build_requires_all_active_pin_macros(
    tmp_path: Path, missing: str
) -> None:
    values = {
        "EXPECTED_PYTHON_SHA256": _quote("EXPECTED_PYTHON_SHA256", "1" * 64),
        "EXPECTED_PYTHON_SIZE": "-DEXPECTED_PYTHON_SIZE=1",
        "EXPECTED_HELPER_SHA256": _quote("EXPECTED_HELPER_SHA256", "2" * 64),
        "EXPECTED_HELPER_SIZE": "-DEXPECTED_HELPER_SIZE=1",
    }
    result = subprocess.run(
        [
            str(GCC),
            "-std=c11",
            *(value for key, value in values.items() if key != missing),
            "-c",
            str(SOURCE),
            "-o",
            str(tmp_path / "missing-production.o"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert f"{missing} is required" in result.stderr


def test_production_source_has_no_hardcoded_pin_defaults() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "PYTHON_SHA256_DEFAULT" not in text
    assert "HELPER_SHA256_DEFAULT" not in text
    assert "#define PYTHON_SHA256 EXPECTED_PYTHON_SHA256" in text
    assert "#define HELPER_SHA256 EXPECTED_HELPER_SHA256" in text
