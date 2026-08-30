from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


SOURCE = (
    Path(__file__).resolve().parents[1] / "admin" / "vista_r8_ue57_stage_installer.c"
)
GCC = Path("/usr/bin/gcc-12")
READELF = Path("/usr/bin/readelf")
PYTHON = Path("/usr/bin/python3.10")
INSTALLER_NAME = "install-reconcile-r8-ue57-stage"


@dataclass(frozen=True)
class Pin:
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class Variant:
    key: str
    define: str
    primary_name: str
    secondary_name: str | None
    install_operation: str
    reconcile_operation: str
    install_acknowledgement: str
    reconcile_acknowledgement: str


VARIANTS = (
    Variant(
        "runtime-input",
        "VISTA_R8_STAGE_RUNTIME_INPUT",
        "input-pin.json",
        None,
        "install-runtime-input-authority",
        "reconcile-runtime-input-authority",
        "I acknowledge one fresh publication of the externally reviewed "
        "VISTA R8 UE 5.7 runtime input authority.",
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 runtime input authority without republishing or deleting it.",
    ),
    Variant(
        "runtime-plan",
        "VISTA_R8_STAGE_RUNTIME_PLAN",
        "reviewed-plan-pin.json",
        "publish-reconcile-r8-ue57",
        "install-runtime-plan-authority",
        "reconcile-runtime-plan-authority",
        "I acknowledge one fresh publication of the externally reviewed "
        "VISTA R8 UE 5.7 runtime plan authority.",
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 runtime plan authority without republishing or deleting it.",
    ),
    Variant(
        "bundle-input",
        "VISTA_R8_STAGE_BUNDLE_INPUT",
        "input-pin.json",
        "launch-r8-ue57",
        "install-bundle-input-authority",
        "reconcile-bundle-input-authority",
        "I acknowledge one fresh publication of the externally reviewed "
        "VISTA R8 UE 5.7 bundle input authority.",
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 bundle input authority without republishing or deleting it.",
    ),
    Variant(
        "bundle-plan",
        "VISTA_R8_STAGE_BUNDLE_PLAN",
        "reviewed-plan-pin.json",
        "publish-reconcile-r8-ue57",
        "install-bundle-plan-authority",
        "reconcile-bundle-plan-authority",
        "I acknowledge one fresh publication of the externally reviewed "
        "VISTA R8 UE 5.7 bundle plan authority.",
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 bundle plan authority without republishing or deleting it.",
    ),
)
BY_KEY = {variant.key: variant for variant in VARIANTS}


@dataclass
class BuiltCase:
    variant: Variant
    binary: Path
    self_root: Path
    candidate_root: Path
    final_root: Path
    helper: Path
    primary_pin: Pin
    secondary_pin: Pin | None


def _pin_bytes(raw: bytes) -> Pin:
    return Pin(hashlib.sha256(raw).hexdigest(), len(raw))


def _pin(path: Path) -> Pin:
    return _pin_bytes(path.read_bytes())


def _canonical(value: object) -> bytes:
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


def _sealed(value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    result["content_digest"] = hashlib.sha256(_canonical(value)).hexdigest()
    return result


def _write_mode(path: Path, raw: bytes, mode: int) -> None:
    path.write_bytes(raw)
    path.chmod(mode)


def _helper_bytes() -> bytes:
    # This fixture is itself executed by the held /usr/bin/python3.10 FD.
    return (
        "import os, stat, sys\n"
        "assert sys.flags.isolated == 1\n"
        "assert sys.dont_write_bytecode\n"
        "assert '--stage-installer-fd' in sys.argv\n"
        "i = sys.argv.index('--stage-installer-fd')\n"
        "fd = int(sys.argv[i + 1])\n"
        "assert fd >= 3 and stat.S_ISREG(os.fstat(fd).st_mode)\n"
        "assert '--acknowledgement' in sys.argv\n"
        "raise SystemExit(0)\n"
    ).encode()


def _candidate_payloads(variant: Variant) -> tuple[bytes, bytes | None]:
    if variant.key == "bundle-input":
        secondary = b"\x7fELFfixture-launch-r8-ue57\n"
        launcher_pin = _pin_bytes(secondary)
        primary = _canonical(
            {
                "launcher_binary_pin": {
                    "sha256": launcher_pin.sha256,
                    "size_bytes": launcher_pin.size_bytes,
                },
                "schema": "fixture",
            }
        )
        return primary, secondary
    if variant.secondary_name is not None:
        return (
            _canonical({"schema": f"fixture-{variant.key}"}),
            b"\x7fELFfixture-admin-launcher\n",
        )
    return _canonical({"schema": "fixture-runtime-input"}), None


def _quote_define(name: str, value: str) -> str:
    assert '"' not in value and "\\" not in value
    return f'-D{name}="{value}"'


def _common_pin_defines(helper: Path) -> list[str]:
    python_pin = _pin(PYTHON)
    helper_pin = _pin(helper)
    return [
        _quote_define("EXPECTED_PYTHON_SHA256", python_pin.sha256),
        f"-DEXPECTED_PYTHON_SIZE={python_pin.size_bytes}",
        _quote_define("EXPECTED_HELPER_SHA256", helper_pin.sha256),
        f"-DEXPECTED_HELPER_SIZE={helper_pin.size_bytes}",
    ]


def _stage_pin_defines(
    variant: Variant, primary_pin: Pin, secondary_pin: Pin | None
) -> list[str]:
    if variant.key.endswith("input"):
        return [
            _quote_define("EXPECTED_INPUT_PIN_SHA256", primary_pin.sha256),
            f"-DEXPECTED_INPUT_PIN_SIZE={primary_pin.size_bytes}",
        ]
    assert secondary_pin is not None
    return [
        _quote_define("EXPECTED_REVIEWED_PLAN_PIN_SHA256", primary_pin.sha256),
        f"-DEXPECTED_REVIEWED_PLAN_PIN_SIZE={primary_pin.size_bytes}",
        _quote_define("EXPECTED_ADMIN_LAUNCHER_SHA256", secondary_pin.sha256),
        f"-DEXPECTED_ADMIN_LAUNCHER_SIZE={secondary_pin.size_bytes}",
    ]


def _test_path_defines(
    self_root: Path,
    candidate_root: Path,
    final_root: Path,
    helper: Path,
    *,
    review_uid: int | None = None,
) -> list[str]:
    uid = os.getuid()
    gid = os.getgid()
    return [
        "-DVISTA_R8_STAGE_INSTALLER_TESTING=1",
        _quote_define("VISTA_R8_TEST_SELF_ROOT", str(self_root)),
        _quote_define("VISTA_R8_TEST_CANDIDATE_ROOT", str(candidate_root)),
        _quote_define("VISTA_R8_TEST_FINAL_ROOT", str(final_root)),
        _quote_define("VISTA_R8_TEST_HELPER_PATH", str(helper)),
        f"-DVISTA_R8_TEST_REQUIRED_EUID={uid}",
        f"-DVISTA_R8_TEST_REQUIRED_EGID={gid}",
        f"-DVISTA_R8_TEST_SELF_UID={uid}",
        f"-DVISTA_R8_TEST_SELF_GID={gid}",
        f"-DVISTA_R8_TEST_REVIEW_UID={uid if review_uid is None else review_uid}",
        f"-DVISTA_R8_TEST_REVIEW_GID={gid}",
        f"-DVISTA_R8_TEST_HELPER_UID={uid}",
        f"-DVISTA_R8_TEST_HELPER_GID={gid}",
    ]


def _compile(
    output: Path,
    variant: Variant,
    helper: Path,
    primary_pin: Pin,
    secondary_pin: Pin | None,
    test_path_defines: list[str],
    *,
    common_pin_defines: list[str] | None = None,
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
            f"-D{variant.define}=1",
            *(common_pin_defines or _common_pin_defines(helper)),
            *_stage_pin_defines(variant, primary_pin, secondary_pin),
            *test_path_defines,
            str(SOURCE),
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _receipt(case: BuiltCase) -> bytes:
    installer_pin = _pin(case.binary)
    helper_pin = _pin(case.helper)
    python_pin = _pin(PYTHON)
    authority = str(case.self_root)
    installed_path = str(case.binary)
    review_path = (
        "/data/sysx/vista-world/runs/vista-action-world-r1/"
        f"vista-r8-ue57-{case.variant.key}-stage-installer-"
        f"review-candidate-20260830a/{INSTALLER_NAME}"
    )
    body: dict[str, object] = {
        "schema": "vista.r8-ue57-stage-installer-transfer-receipt/v1",
        "status": "root_published_immutable_stage_installer_authority",
        "accepted": True,
        "stage": case.variant.key,
        "authority_root": authority,
        "installer": {
            "path": installed_path,
            "pin": {
                "sha256": installer_pin.sha256,
                "size_bytes": installer_pin.size_bytes,
            },
        },
        "reviewed_candidate": {
            "path": review_path,
            "pin": {
                "sha256": installer_pin.sha256,
                "size_bytes": installer_pin.size_bytes,
            },
            "uid": 1000021,
            "gid": 1000001,
            "mode": 0o555,
        },
        "publisher": {
            "helper_pin": {
                "sha256": helper_pin.sha256,
                "size_bytes": helper_pin.size_bytes,
            },
            "interpreter_pin": {
                "sha256": python_pin.sha256,
                "size_bytes": python_pin.size_bytes,
            },
            "stage_transfer_launcher_pin": {
                "sha256": "1" * 64,
                "size_bytes": 1,
            },
        },
        "stage_contract": {
            "install_operation": case.variant.install_operation,
            "reconcile_operation": case.variant.reconcile_operation,
            "install_acknowledgement": case.variant.install_acknowledgement,
            "reconcile_acknowledgement": case.variant.reconcile_acknowledgement,
            "candidate_root": str(case.candidate_root),
            "final_root": str(case.final_root),
        },
        "claims": {
            "external_review_pin_required": True,
            "no_replace": True,
            "held_fd_copy": True,
            "reconcile_only": True,
            "no_deletion": True,
        },
    }
    return _canonical(_sealed(body))


def _build_case(
    root: Path,
    variant: Variant,
    *,
    review_uid: int | None = None,
    common_pin_defines: list[str] | None = None,
) -> BuiltCase:
    if not GCC.is_file() or not PYTHON.is_file():
        pytest.skip("reviewed GCC/Python paths unavailable")
    self_root = root / "self" / variant.key
    candidate_root = root / "candidate" / variant.key
    final_root = root / "final" / variant.key
    helper = root / "core" / f"helper-{variant.key}.py"
    self_root.mkdir(parents=True)
    candidate_root.mkdir(parents=True)
    final_root.parent.mkdir(parents=True, exist_ok=True)
    helper.parent.mkdir(parents=True, exist_ok=True)
    _write_mode(helper, _helper_bytes(), 0o500)
    primary, secondary = _candidate_payloads(variant)
    _write_mode(candidate_root / variant.primary_name, primary, 0o444)
    secondary_pin = None
    if variant.secondary_name is not None:
        assert secondary is not None
        _write_mode(candidate_root / variant.secondary_name, secondary, 0o555)
        secondary_pin = _pin_bytes(secondary)
    candidate_root.chmod(0o555)
    primary_pin = _pin_bytes(primary)
    binary = self_root / INSTALLER_NAME
    _compile(
        binary,
        variant,
        helper,
        primary_pin,
        secondary_pin,
        _test_path_defines(
            self_root,
            candidate_root,
            final_root,
            helper,
            review_uid=review_uid,
        ),
        common_pin_defines=common_pin_defines,
    )
    binary.chmod(0o555)
    case = BuiltCase(
        variant,
        binary,
        self_root,
        candidate_root,
        final_root,
        helper,
        primary_pin,
        secondary_pin,
    )
    _write_mode(self_root / "receipt.json", _receipt(case), 0o444)
    self_root.chmod(0o555)
    return case


def _run(
    case: BuiltCase, operation: str, acknowledgement: str, *, timeout: float = 4
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(case.binary), operation, acknowledgement],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _create_final(case: BuiltCase) -> None:
    case.final_root.mkdir()
    for name in (case.variant.primary_name, case.variant.secondary_name):
        if name is None:
            continue
        destination = case.final_root / name
        destination.write_bytes((case.candidate_root / name).read_bytes())
        destination.chmod(0o555 if name == case.variant.secondary_name else 0o444)
    case.final_root.chmod(0o555)


def _make_candidate_mutable(case: BuiltCase) -> None:
    case.candidate_root.chmod(0o755)


def test_source_contract_has_four_closed_root_authorities_and_no_shell() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    joined_literals = re.sub(r'"\s*\\?\s*"', "", source)
    for variant in VARIANTS:
        assert variant.define in source
        assert variant.install_operation in source
        assert variant.reconcile_operation in source
        assert variant.install_acknowledgement in joined_literals
        assert variant.reconcile_acknowledgement in joined_literals
        assert f"/root/vista-r8-ue57-stage-installers-r1/{variant.key}" in source
        assert (
            f"vista-r8-ue57-{variant.key}-stage-installer-review-candidate-" in source
        )
    for forbidden in ("system(", "popen(", "fork(", "/bin/sh", "sha256sum"):
        assert forbidden not in source
    assert "SYS_execveat" in source
    assert "O_NOFOLLOW" in source
    assert "O_NONBLOCK" in source
    assert '"--stage-installer-fd"' in source
    assert "argc != 3" in source


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda item: item.key)
def test_all_four_variants_compile_static_and_install_execveat_helper(
    tmp_path: Path, variant: Variant
) -> None:
    case = _build_case(tmp_path, variant)
    result = _run(case, variant.install_operation, variant.install_acknowledgement)
    assert result.returncode == 0, result.stderr
    program_headers = subprocess.run(
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
    assert " INTERP " not in program_headers
    assert "Requesting program interpreter" not in program_headers
    assert "(NEEDED)" not in dynamic
    assert "There is no dynamic section in this file." in dynamic


@pytest.mark.parametrize("variant", VARIANTS, ids=lambda item: item.key)
def test_reconcile_uses_only_installed_final_not_mutable_candidate(
    tmp_path: Path, variant: Variant
) -> None:
    case = _build_case(tmp_path, variant)
    _create_final(case)
    _make_candidate_mutable(case)
    shutil.rmtree(case.candidate_root)
    result = _run(case, variant.reconcile_operation, variant.reconcile_acknowledgement)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("bad_argv", [[], ["wrong"], ["wrong", "ack"]])
def test_wrong_argc_operation_or_ack_is_rejected(
    tmp_path: Path, bad_argv: list[str]
) -> None:
    case = _build_case(tmp_path, BY_KEY["runtime-input"])
    if bad_argv == ["wrong"]:
        argv = [str(case.binary), "wrong", case.variant.install_acknowledgement]
    elif bad_argv == ["wrong", "ack"]:
        argv = [str(case.binary), case.variant.install_operation, "wrong"]
    else:
        argv = [str(case.binary)]
    result = subprocess.run(argv, check=False, capture_output=True, text=True)
    assert result.returncode == 126


@pytest.mark.skipif(os.geteuid() == 0, reason="requires a non-root runner")
def test_production_variant_rejects_nonroot_before_fixed_root_access(
    tmp_path: Path,
) -> None:
    helper = SOURCE.with_name("vista_r8_ue57_authority_admin.py")
    primary = _pin_bytes(b"x")
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
            "-DVISTA_R8_STAGE_RUNTIME_INPUT=1",
            *_common_pin_defines(helper),
            *_stage_pin_defines(BY_KEY["runtime-input"], primary, None),
            str(SOURCE),
            "-o",
            str(output),
        ],
        check=True,
    )
    result = subprocess.run(
        [
            str(output),
            BY_KEY["runtime-input"].install_operation,
            BY_KEY["runtime-input"].install_acknowledgement,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 126
    assert "root EUID and EGID required" in result.stderr


@pytest.mark.parametrize(
    "mutation",
    ["extra", "symlink", "hardlink", "mode", "tamper", "fifo", "huge"],
)
def test_runtime_input_candidate_rejects_closed_tree_violations_without_hang(
    tmp_path: Path, mutation: str
) -> None:
    case = _build_case(tmp_path, BY_KEY["runtime-input"])
    primary = case.candidate_root / case.variant.primary_name
    _make_candidate_mutable(case)
    if mutation == "extra":
        _write_mode(case.candidate_root / "extra", b"x", 0o444)
    elif mutation == "symlink":
        primary.unlink()
        target = tmp_path / "target"
        _write_mode(target, b"target", 0o444)
        primary.symlink_to(target)
    elif mutation == "hardlink":
        original = tmp_path / "hardlink-source"
        _write_mode(original, primary.read_bytes(), 0o444)
        primary.unlink()
        os.link(original, primary)
    elif mutation == "mode":
        primary.chmod(0o644)
    elif mutation == "tamper":
        raw = bytearray(primary.read_bytes())
        raw[0] ^= 1
        primary.chmod(0o644)
        primary.write_bytes(raw)
        primary.chmod(0o444)
    elif mutation == "fifo":
        primary.unlink()
        os.mkfifo(primary, 0o444)
    elif mutation == "huge":
        primary.unlink()
        with primary.open("wb") as stream:
            stream.truncate(129 * 1024 * 1024)
        primary.chmod(0o444)
    case.candidate_root.chmod(0o555)
    result = _run(
        case,
        case.variant.install_operation,
        case.variant.install_acknowledgement,
        timeout=2,
    )
    assert result.returncode == 126


def test_candidate_owner_contract_is_rejected(tmp_path: Path) -> None:
    case = _build_case(tmp_path, BY_KEY["runtime-input"], review_uid=os.getuid() + 1)
    result = _run(
        case, case.variant.install_operation, case.variant.install_acknowledgement
    )
    assert result.returncode == 126


def test_install_requires_absent_final(tmp_path: Path) -> None:
    case = _build_case(tmp_path, BY_KEY["runtime-plan"])
    _create_final(case)
    result = _run(
        case, case.variant.install_operation, case.variant.install_acknowledgement
    )
    assert result.returncode == 126
    assert "not fresh" in result.stderr


def test_reconcile_rejects_installed_final_tamper(tmp_path: Path) -> None:
    case = _build_case(tmp_path, BY_KEY["bundle-input"])
    _create_final(case)
    case.final_root.chmod(0o755)
    launcher = case.final_root / "launch-r8-ue57"
    launcher.chmod(0o755)
    raw = bytearray(launcher.read_bytes())
    raw[-1] ^= 1
    launcher.write_bytes(raw)
    launcher.chmod(0o555)
    case.final_root.chmod(0o555)
    result = _run(
        case,
        case.variant.reconcile_operation,
        case.variant.reconcile_acknowledgement,
    )
    assert result.returncode == 126


def test_receipt_must_cross_bind_live_self_pin(tmp_path: Path) -> None:
    case = _build_case(tmp_path, BY_KEY["runtime-input"])
    receipt = case.self_root / "receipt.json"
    case.self_root.chmod(0o755)
    receipt.chmod(0o644)
    document = json.loads(receipt.read_text())
    document["installer"]["pin"]["sha256"] = "0" * 64
    receipt.write_bytes(_canonical(document))
    receipt.chmod(0o444)
    case.self_root.chmod(0o555)
    result = _run(
        case, case.variant.install_operation, case.variant.install_acknowledgement
    )
    assert result.returncode == 126
    assert "receipt does not bind" in result.stderr


def test_truncated_receipt_pin_is_bounded_and_rejected(tmp_path: Path) -> None:
    case = _build_case(tmp_path, BY_KEY["runtime-input"])
    receipt = case.self_root / "receipt.json"
    case.self_root.chmod(0o755)
    receipt.chmod(0o644)
    receipt.write_bytes(
        (
            '{"installer":{"path":"' + str(case.binary) + '","pin":{"sha256":"abc'
        ).encode()
    )
    receipt.chmod(0o444)
    case.self_root.chmod(0o555)
    result = _run(
        case, case.variant.install_operation, case.variant.install_acknowledgement
    )
    assert result.returncode == 126
    assert "receipt does not bind" in result.stderr


def test_pinned_truncated_bundle_launcher_pin_is_bounded_and_rejected(
    tmp_path: Path,
) -> None:
    case = _build_case(tmp_path, BY_KEY["bundle-input"])
    malformed = b'{"launcher_binary_pin":{"sha256":"abc'
    primary = case.candidate_root / case.variant.primary_name
    case.candidate_root.chmod(0o755)
    primary.chmod(0o644)
    primary.write_bytes(malformed)
    primary.chmod(0o444)
    case.candidate_root.chmod(0o555)
    case.primary_pin = _pin_bytes(malformed)
    case.self_root.chmod(0o755)
    case.binary.chmod(0o755)
    _compile(
        case.binary,
        case.variant,
        case.helper,
        case.primary_pin,
        case.secondary_pin,
        _test_path_defines(
            case.self_root,
            case.candidate_root,
            case.final_root,
            case.helper,
        ),
    )
    case.binary.chmod(0o555)
    receipt = case.self_root / "receipt.json"
    receipt.chmod(0o644)
    receipt.write_bytes(_receipt(case))
    receipt.chmod(0o444)
    case.self_root.chmod(0o555)
    result = _run(
        case, case.variant.install_operation, case.variant.install_acknowledgement
    )
    assert result.returncode == 126
    assert "transitive pin differs" in result.stderr


def test_helper_pin_tamper_is_rejected(tmp_path: Path) -> None:
    case = _build_case(tmp_path, BY_KEY["runtime-input"])
    case.helper.chmod(0o700)
    raw = bytearray(case.helper.read_bytes())
    raw[-1] ^= 1
    case.helper.write_bytes(raw)
    case.helper.chmod(0o500)
    result = _run(
        case, case.variant.install_operation, case.variant.install_acknowledgement
    )
    assert result.returncode == 126


@pytest.mark.parametrize(
    ("payload", "known_sha256"),
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
    tmp_path: Path, payload: bytes, known_sha256: str
) -> None:
    harness_source = tmp_path / "hash-harness.c"
    harness = tmp_path / "hash-harness"
    dummy_helper = tmp_path / "helper"
    _write_mode(dummy_helper, b"x", 0o500)
    harness_source.write_text(
        "#define main vista_stage_installer_main\n"
        f'#include "{SOURCE}"\n'
        "#undef main\n"
        "int main(int argc, char **argv) {\n"
        "  file_pin pin; int fd; char *end = 0; long long size;\n"
        "  if (argc != 4) return 2;\n"
        "  size = strtoll(argv[2], &end, 10);\n"
        "  if (!end || *end || size <= 0) return 2;\n"
        "  memcpy(pin.sha256, argv[3], 65); pin.size_bytes = (off_t)size;\n"
        "  fd = open(argv[1], O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);\n"
        "  if (fd < 0) return 2;\n"
        "  return verify_fd_pin(fd, &pin) == 0 ? 0 : 3;\n"
        "}\n",
        encoding="utf-8",
    )
    one = _pin_bytes(b"x")
    subprocess.run(
        [
            str(GCC),
            "-std=c11",
            "-O2",
            "-static",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DVISTA_R8_STAGE_RUNTIME_INPUT=1",
            *_common_pin_defines(dummy_helper),
            *_stage_pin_defines(BY_KEY["runtime-input"], one, None),
            *_test_path_defines(
                tmp_path / "self",
                tmp_path / "candidate",
                tmp_path / "final",
                dummy_helper,
            ),
            str(harness_source),
            "-o",
            str(harness),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    candidate = tmp_path / "vector"
    candidate.write_bytes(payload)
    assert hashlib.sha256(payload).hexdigest() == known_sha256
    accepted = subprocess.run(
        [str(harness), str(candidate), str(len(payload)), known_sha256],
        check=False,
        timeout=2,
    )
    assert accepted.returncode == 0
    candidate.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    rejected = subprocess.run(
        [str(harness), str(candidate), str(len(payload)), known_sha256],
        check=False,
        timeout=2,
    )
    assert rejected.returncode == 3


@pytest.mark.parametrize(
    "defines, expected",
    [
        ([], "define exactly one VISTA R8 stage installer variant"),
        (
            [
                "-DVISTA_R8_STAGE_RUNTIME_INPUT=1",
                "-DVISTA_R8_STAGE_BUNDLE_INPUT=1",
            ],
            "define exactly one VISTA R8 stage installer variant",
        ),
    ],
)
def test_compile_requires_exactly_one_variant(
    tmp_path: Path, defines: list[str], expected: str
) -> None:
    result = subprocess.run(
        [
            str(GCC),
            "-std=c11",
            *defines,
            "-c",
            str(SOURCE),
            "-o",
            str(tmp_path / "x.o"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert expected in result.stderr


@pytest.mark.parametrize(
    "variant, missing",
    [
        (BY_KEY["runtime-input"], "EXPECTED_PYTHON_SHA256"),
        (BY_KEY["runtime-input"], "EXPECTED_PYTHON_SIZE"),
        (BY_KEY["runtime-input"], "EXPECTED_HELPER_SHA256"),
        (BY_KEY["runtime-input"], "EXPECTED_HELPER_SIZE"),
        (BY_KEY["runtime-input"], "EXPECTED_INPUT_PIN_SHA256"),
        (BY_KEY["runtime-input"], "EXPECTED_INPUT_PIN_SIZE"),
        (BY_KEY["runtime-plan"], "EXPECTED_REVIEWED_PLAN_PIN_SHA256"),
        (BY_KEY["runtime-plan"], "EXPECTED_REVIEWED_PLAN_PIN_SIZE"),
        (BY_KEY["runtime-plan"], "EXPECTED_ADMIN_LAUNCHER_SHA256"),
        (BY_KEY["runtime-plan"], "EXPECTED_ADMIN_LAUNCHER_SIZE"),
    ],
)
def test_compile_requires_all_reviewed_pin_macros(
    tmp_path: Path, variant: Variant, missing: str
) -> None:
    common = [
        _quote_define("EXPECTED_PYTHON_SHA256", "1" * 64),
        "-DEXPECTED_PYTHON_SIZE=1",
        _quote_define("EXPECTED_HELPER_SHA256", "2" * 64),
        "-DEXPECTED_HELPER_SIZE=1",
    ]
    stage = (
        [
            _quote_define("EXPECTED_INPUT_PIN_SHA256", "3" * 64),
            "-DEXPECTED_INPUT_PIN_SIZE=1",
        ]
        if variant.key.endswith("input")
        else [
            _quote_define("EXPECTED_REVIEWED_PLAN_PIN_SHA256", "3" * 64),
            "-DEXPECTED_REVIEWED_PLAN_PIN_SIZE=1",
            _quote_define("EXPECTED_ADMIN_LAUNCHER_SHA256", "4" * 64),
            "-DEXPECTED_ADMIN_LAUNCHER_SIZE=1",
        ]
    )
    defines = [
        item for item in (*common, *stage) if not item.startswith(f"-D{missing}=")
    ]
    result = subprocess.run(
        [
            str(GCC),
            "-std=c11",
            f"-D{variant.define}=1",
            *defines,
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
