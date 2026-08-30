from __future__ import annotations

from dataclasses import dataclass
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
    / "vista_r8_ue57_stage_transfer_launcher.c"
)
GCC = Path("/usr/bin/gcc-12")
READELF = Path("/usr/bin/readelf")
PYTHON = Path("/usr/bin/python3.10")
SELF_NAME = "transfer-r8-ue57-stage-installer"
INSTALLER_NAME = "install-reconcile-r8-ue57-stage"


@dataclass(frozen=True)
class Stage:
    key: str
    install_ack: str
    reconcile_ack: str


STAGES = (
    Stage(
        "runtime-input",
        "I acknowledge one fresh root transfer of the externally reviewed "
        "VISTA R8 UE 5.7 runtime-input one-shot stage installer.",
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 runtime-input one-shot stage installer without republishing "
        "or deleting it.",
    ),
    Stage(
        "runtime-plan",
        "I acknowledge one fresh root transfer of the externally reviewed "
        "VISTA R8 UE 5.7 runtime-plan one-shot stage installer.",
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 runtime-plan one-shot stage installer without republishing "
        "or deleting it.",
    ),
    Stage(
        "bundle-input",
        "I acknowledge one fresh root transfer of the externally reviewed "
        "VISTA R8 UE 5.7 bundle-input one-shot stage installer.",
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 bundle-input one-shot stage installer without republishing "
        "or deleting it.",
    ),
    Stage(
        "bundle-plan",
        "I acknowledge one fresh root transfer of the externally reviewed "
        "VISTA R8 UE 5.7 bundle-plan one-shot stage installer.",
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 bundle-plan one-shot stage installer without republishing "
        "or deleting it.",
    ),
)


@dataclass
class Case:
    stage: Stage
    core: Path
    review_parent: Path
    final_parent: Path
    candidate: Path
    final: Path
    binary: Path
    helper: Path
    installer_pin: tuple[str, int]


def _pin(raw: bytes) -> tuple[str, int]:
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _file_pin(path: Path) -> tuple[str, int]:
    return _pin(path.read_bytes())


def _quote(name: str, value: str) -> str:
    assert '"' not in value and "\\" not in value
    return f'-D{name}="{value}"'


def _helper_bytes() -> bytes:
    return (
        "import os, stat, sys\n"
        "assert sys.flags.isolated == 1 and sys.dont_write_bytecode\n"
        "assert sys.argv[1] in {'install-stage-installer-authority', "
        "'reconcile-stage-installer-authority'}\n"
        "for flag in ('--stage', '--reviewed-installer-sha256', "
        "'--reviewed-installer-size', '--stage-transfer-launcher-fd', "
        "'--acknowledgement'): assert flag in sys.argv\n"
        "i = sys.argv.index('--stage-transfer-launcher-fd')\n"
        "fd = int(sys.argv[i + 1])\n"
        "assert fd >= 3 and stat.S_ISREG(os.fstat(fd).st_mode)\n"
        "raise SystemExit(0)\n"
    ).encode()


def _pin_defines(helper: Path) -> list[str]:
    python_pin = _file_pin(PYTHON)
    helper_pin = _file_pin(helper)
    return [
        _quote("EXPECTED_PYTHON_SHA256", python_pin[0]),
        f"-DEXPECTED_PYTHON_SIZE={python_pin[1]}",
        _quote("EXPECTED_HELPER_SHA256", helper_pin[0]),
        f"-DEXPECTED_HELPER_SIZE={helper_pin[1]}",
    ]


def _test_defines(core: Path, review_parent: Path, final_parent: Path) -> list[str]:
    uid = os.getuid()
    gid = os.getgid()
    return [
        "-DVISTA_R8_STAGE_TRANSFER_TESTING=1",
        _quote("VISTA_R8_TRANSFER_TEST_CORE_ROOT", str(core)),
        _quote("VISTA_R8_TRANSFER_TEST_REVIEW_PARENT", str(review_parent)),
        _quote("VISTA_R8_TRANSFER_TEST_FINAL_PARENT", str(final_parent)),
        f"-DVISTA_R8_TRANSFER_TEST_REQUIRED_EUID={uid}",
        f"-DVISTA_R8_TRANSFER_TEST_REQUIRED_EGID={gid}",
        f"-DVISTA_R8_TRANSFER_TEST_CORE_UID={uid}",
        f"-DVISTA_R8_TRANSFER_TEST_CORE_GID={gid}",
        f"-DVISTA_R8_TRANSFER_TEST_REVIEW_UID={uid}",
        f"-DVISTA_R8_TRANSFER_TEST_REVIEW_GID={gid}",
    ]


def _compile(
    output: Path,
    helper: Path,
    core: Path,
    review_parent: Path,
    final_parent: Path,
) -> None:
    subprocess.run(
        [
            str(GCC),
            "-std=c11",
            "-O2",
            "-static",
            "-Wall",
            "-Wextra",
            "-Werror",
            *_pin_defines(helper),
            *_test_defines(core, review_parent, final_parent),
            str(SOURCE),
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    output.chmod(0o555)


def _write(path: Path, raw: bytes, mode: int) -> None:
    path.write_bytes(raw)
    path.chmod(mode)


def _build_case(tmp_path: Path, stage: Stage) -> Case:
    if not GCC.is_file() or not PYTHON.is_file():
        pytest.skip("reviewed GCC/Python paths unavailable")
    core = tmp_path / "core"
    review_parent = tmp_path / "review"
    final_parent = tmp_path / "final"
    core.mkdir()
    review_parent.mkdir()
    final_parent.mkdir()
    helper = core / "vista_r8_ue57_authority_admin.py"
    _write(helper, _helper_bytes(), 0o500)
    _write(core / "provision_vista_r8_ue57_engine.sh", b"#!/bin/sh\n", 0o500)
    _write(core / "engine-source-pin.json", b"{}\n", 0o444)
    for lock in (".engine.lock", ".runtime.lock", ".bundle.lock", ".executor.lock"):
        _write(core / lock, b"", 0o600)
    binary = core / SELF_NAME
    _compile(binary, helper, core, review_parent, final_parent)
    core.chmod(0o555)
    candidate = review_parent / stage.key
    candidate.mkdir()
    installer = b"\x7fELFfixture-one-shot-stage-installer\n"
    _write(candidate / INSTALLER_NAME, installer, 0o555)
    candidate.chmod(0o555)
    final = final_parent / stage.key
    return Case(
        stage,
        core,
        review_parent,
        final_parent,
        candidate,
        final,
        binary,
        helper,
        _pin(installer),
    )


def _create_final(case: Case) -> None:
    case.final.mkdir()
    _write(
        case.final / INSTALLER_NAME,
        (case.candidate / INSTALLER_NAME).read_bytes(),
        0o555,
    )
    _write(case.final / "receipt.json", b"{}\n", 0o444)
    case.final.chmod(0o555)


def _run(
    case: Case,
    operation: str,
    stage: str,
    sha256: str,
    size: str,
    acknowledgement: str,
    *,
    timeout: float = 3,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(case.binary),
            operation,
            stage,
            sha256,
            size,
            acknowledgement,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_install(case: Case, *, timeout: float = 3) -> subprocess.CompletedProcess[str]:
    return _run(
        case,
        "install-stage-installer-authority",
        case.stage.key,
        case.installer_pin[0],
        str(case.installer_pin[1]),
        case.stage.install_ack,
        timeout=timeout,
    )


def _run_reconcile(case: Case) -> subprocess.CompletedProcess[str]:
    return _run(
        case,
        "reconcile-stage-installer-authority",
        case.stage.key,
        case.installer_pin[0],
        str(case.installer_pin[1]),
        case.stage.reconcile_ack,
    )


def test_source_contract_is_closed_and_has_no_external_utility() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    joined = re.sub(r'"\s*\\?\s*"', "", source)
    assert "/root/vista-r8-ue57-authority-r2" in source
    assert "/data/sysx/vista-world/runs/vista-action-world-r1" in source
    assert "/root/vista-r8-ue57-stage-installers-r1" in source
    assert "argc != 6" in source
    for stage in STAGES:
        assert stage.key in source
        assert stage.install_ack in joined
        assert stage.reconcile_ack in joined
    for required in (
        "EXPECTED_PYTHON_SHA256",
        "EXPECTED_PYTHON_SIZE",
        "EXPECTED_HELPER_SHA256",
        "EXPECTED_HELPER_SIZE",
        "SYS_execveat",
        "O_NOFOLLOW",
        "O_NONBLOCK",
        '"--stage-transfer-launcher-fd"',
    ):
        assert required in source
    for forbidden in ("system(", "popen(", "fork(", "/bin/sh", "sha256sum"):
        assert forbidden not in source


@pytest.mark.parametrize("stage", STAGES, ids=lambda value: value.key)
def test_install_for_all_four_stages_executes_held_helper(
    tmp_path: Path, stage: Stage
) -> None:
    case = _build_case(tmp_path, stage)
    result = _run_install(case)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("stage", STAGES, ids=lambda value: value.key)
def test_reconcile_is_final_only_and_candidate_independent(
    tmp_path: Path, stage: Stage
) -> None:
    case = _build_case(tmp_path, stage)
    _create_final(case)
    case.candidate.chmod(0o755)
    shutil.rmtree(case.candidate)
    result = _run_reconcile(case)
    assert result.returncode == 0, result.stderr


def test_binary_is_static_without_interpreter(tmp_path: Path) -> None:
    case = _build_case(tmp_path, STAGES[0])
    headers = subprocess.run(
        [str(READELF), "-lW", str(case.binary)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    dynamic = subprocess.run(
        [str(READELF), "-dW", str(case.binary)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert " INTERP " not in headers
    assert "Requesting program interpreter" not in headers
    assert "(NEEDED)" not in dynamic
    assert "There is no dynamic section in this file." in dynamic


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation", "wrong"),
        ("stage", "wrong"),
        ("sha256", "0" * 64),
        ("sha256", "A" * 64),
        ("size", "0"),
        ("size", "01"),
        ("size", str(17 * 1024 * 1024)),
        ("ack", "wrong"),
    ],
)
def test_runtime_contract_rejects_nonclosed_values(
    tmp_path: Path, field: str, value: str
) -> None:
    case = _build_case(tmp_path, STAGES[0])
    values = {
        "operation": "install-stage-installer-authority",
        "stage": case.stage.key,
        "sha256": case.installer_pin[0],
        "size": str(case.installer_pin[1]),
        "ack": case.stage.install_ack,
    }
    values[field] = value
    result = _run(
        case,
        values["operation"],
        values["stage"],
        values["sha256"],
        values["size"],
        values["ack"],
    )
    assert result.returncode == 126


@pytest.mark.parametrize(
    "mutation", ["extra", "symlink", "hardlink", "mode", "tamper", "fifo", "huge"]
)
def test_review_candidate_rejects_special_or_drifted_bytes_without_hang(
    tmp_path: Path, mutation: str
) -> None:
    case = _build_case(tmp_path, STAGES[0])
    installer = case.candidate / INSTALLER_NAME
    case.candidate.chmod(0o755)
    if mutation == "extra":
        _write(case.candidate / "extra", b"x", 0o444)
    elif mutation == "symlink":
        installer.unlink()
        target = tmp_path / "target"
        _write(target, b"target", 0o555)
        installer.symlink_to(target)
    elif mutation == "hardlink":
        raw = installer.read_bytes()
        installer.unlink()
        original = tmp_path / "original"
        _write(original, raw, 0o555)
        os.link(original, installer)
    elif mutation == "mode":
        installer.chmod(0o755)
    elif mutation == "tamper":
        installer.chmod(0o755)
        raw = bytearray(installer.read_bytes())
        raw[-1] ^= 1
        installer.write_bytes(raw)
        installer.chmod(0o555)
    elif mutation == "fifo":
        installer.unlink()
        os.mkfifo(installer, 0o555)
    elif mutation == "huge":
        installer.unlink()
        with installer.open("wb") as stream:
            stream.truncate(17 * 1024 * 1024)
        installer.chmod(0o555)
    case.candidate.chmod(0o555)
    assert _run_install(case, timeout=2).returncode == 126


def test_final_installer_tamper_rejects_reconcile(tmp_path: Path) -> None:
    case = _build_case(tmp_path, STAGES[2])
    _create_final(case)
    case.final.chmod(0o755)
    installer = case.final / INSTALLER_NAME
    installer.chmod(0o755)
    raw = bytearray(installer.read_bytes())
    raw[-1] ^= 1
    installer.write_bytes(raw)
    installer.chmod(0o555)
    case.final.chmod(0o555)
    assert _run_reconcile(case).returncode == 126


def test_exact_core_inventory_and_helper_pin_are_enforced(tmp_path: Path) -> None:
    case = _build_case(tmp_path, STAGES[0])
    case.core.chmod(0o755)
    _write(case.core / "extra", b"x", 0o444)
    case.core.chmod(0o555)
    assert _run_install(case).returncode == 126


def test_core_helper_byte_tamper_is_rejected(tmp_path: Path) -> None:
    case = _build_case(tmp_path, STAGES[0])
    case.core.chmod(0o755)
    case.helper.chmod(0o700)
    raw = bytearray(case.helper.read_bytes())
    raw[-1] ^= 1
    case.helper.write_bytes(raw)
    case.helper.chmod(0o500)
    case.core.chmod(0o555)
    assert _run_install(case).returncode == 126


@pytest.mark.parametrize("mutation", ["mode", "hardlink", "fifo"])
def test_final_receipt_special_node_or_metadata_drift_is_rejected(
    tmp_path: Path, mutation: str
) -> None:
    case = _build_case(tmp_path, STAGES[1])
    _create_final(case)
    receipt = case.final / "receipt.json"
    case.final.chmod(0o755)
    if mutation == "mode":
        receipt.chmod(0o644)
    elif mutation == "hardlink":
        raw = receipt.read_bytes()
        receipt.unlink()
        original = tmp_path / "receipt-source"
        _write(original, raw, 0o444)
        os.link(original, receipt)
    else:
        receipt.unlink()
        os.mkfifo(receipt, 0o444)
    case.final.chmod(0o555)
    assert _run_reconcile(case).returncode == 126


def test_fixed_self_must_match_proc_self_exe(tmp_path: Path) -> None:
    case = _build_case(tmp_path, STAGES[0])
    copied = tmp_path / "copied-transfer"
    shutil.copyfile(case.binary, copied)
    copied.chmod(0o555)
    result = subprocess.run(
        [
            str(copied),
            "install-stage-installer-authority",
            case.stage.key,
            case.installer_pin[0],
            str(case.installer_pin[1]),
            case.stage.install_ack,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 126
    assert "live self identity differs" in result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="requires non-root runner")
def test_production_binary_rejects_nonroot_before_root_access(tmp_path: Path) -> None:
    helper = SOURCE.with_name("vista_r8_ue57_authority_admin.py")
    output = tmp_path / "production"
    subprocess.run(
        [
            str(GCC),
            "-std=c11",
            "-O2",
            "-static",
            "-Wall",
            "-Wextra",
            "-Werror",
            *_pin_defines(helper),
            str(SOURCE),
            "-o",
            str(output),
        ],
        check=True,
    )
    fake = _pin(b"x")
    result = subprocess.run(
        [
            str(output),
            "install-stage-installer-authority",
            STAGES[0].key,
            fake[0],
            str(fake[1]),
            STAGES[0].install_ack,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
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
    helper = tmp_path / "helper"
    _write(helper, b"x", 0o500)
    harness_source = tmp_path / "harness.c"
    harness = tmp_path / "harness"
    harness_source.write_text(
        "#define main stage_transfer_main\n"
        f'#include "{SOURCE}"\n'
        "#undef main\n"
        "int main(int argc, char **argv) {\n"
        "  file_pin pin; int fd; char *end = 0; long long size;\n"
        "  if (argc != 4) return 2;\n"
        "  size = strtoll(argv[2], &end, 10); if (!end || *end) return 2;\n"
        "  memcpy(pin.sha256, argv[3], 65); pin.size_bytes = (off_t)size;\n"
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
            *_pin_defines(helper),
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
        "EXPECTED_PYTHON_SHA256",
        "EXPECTED_PYTHON_SIZE",
        "EXPECTED_HELPER_SHA256",
        "EXPECTED_HELPER_SIZE",
    ],
)
def test_compile_requires_every_common_pin(tmp_path: Path, missing: str) -> None:
    defines = [
        _quote("EXPECTED_PYTHON_SHA256", "1" * 64),
        "-DEXPECTED_PYTHON_SIZE=1",
        _quote("EXPECTED_HELPER_SHA256", "2" * 64),
        "-DEXPECTED_HELPER_SIZE=1",
    ]
    result = subprocess.run(
        [
            str(GCC),
            "-std=c11",
            *(value for value in defines if not value.startswith(f"-D{missing}=")),
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
