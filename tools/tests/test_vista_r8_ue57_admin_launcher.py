from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest


SOURCE = (
    Path(__file__).resolve().parents[1] / "admin" / "vista_r8_ue57_admin_launcher.c"
)
GCC = Path("/usr/bin/gcc-12")
READELF = Path("/usr/bin/readelf")

PYTHON_PATH = "/usr/bin/python3.10"
HELPER_PATH = "/root/vista-r8-ue57-authority-r2/vista_r8_ue57_authority_admin.py"
HELPER_SOURCE = SOURCE.with_name("vista_r8_ue57_authority_admin.py")
RUNTIME_SELF = "/root/vista-r8-ue57-runtime-plan-r1/publish-reconcile-r8-ue57"
BUNDLE_SELF = "/root/vista-r8-ue57-bundle-plan-r1/publish-reconcile-r8-ue57"

RUNTIME_PUBLISH = "publish-host-runtime"
RUNTIME_RECONCILE = "reconcile-host-runtime"
BUNDLE_PUBLISH = "publish-executor-bundle"
BUNDLE_RECONCILE = "reconcile-executor-bundle"

RUNTIME_PUBLISH_ACK = (
    "I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 "
    "host-runtime authority."
)
RUNTIME_RECONCILE_ACK = (
    "I acknowledge reconciliation of the existing reviewed VISTA R8 UE 5.7 "
    "host-runtime authority without republishing or deleting it."
)
BUNDLE_PUBLISH_ACK = (
    "I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 R2 "
    "executor bundle."
)
BUNDLE_RECONCILE_ACK = (
    "I acknowledge reconciliation of the existing reviewed VISTA R8 UE 5.7 "
    "R2 executor bundle without republishing or deleting it."
)


@dataclass(frozen=True)
class FilePin:
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class CompiledLaunchers:
    runtime: Path
    bundle: Path
    python_pin: FilePin
    helper_pin: FilePin


def _pin(path: Path) -> FilePin:
    raw = path.read_bytes()
    return FilePin(hashlib.sha256(raw).hexdigest(), len(raw))


def _pin_defines(python_pin: FilePin, helper_pin: FilePin) -> tuple[str, ...]:
    return (
        f'-DEXPECTED_PYTHON_SHA256="{python_pin.sha256}"',
        f"-DEXPECTED_PYTHON_SIZE={python_pin.size_bytes}",
        f'-DEXPECTED_HELPER_SHA256="{helper_pin.sha256}"',
        f"-DEXPECTED_HELPER_SIZE={helper_pin.size_bytes}",
    )


def _compile(
    source: Path,
    output: Path,
    stage_define: str,
    python_pin: FilePin,
    helper_pin: FilePin,
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
            f"-D{stage_define}=1",
            *_pin_defines(python_pin, helper_pin),
            str(source),
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _compile_hash_harness(
    source: Path,
    output: Path,
    python_pin: FilePin,
    helper_pin: FilePin,
) -> None:
    source.write_text(
        f"""
#define _GNU_SOURCE
#include <stdlib.h>
#define main vista_r8_admin_launcher_main
#include \"{SOURCE}\"
#undef main

int main(int argc, char **argv) {{
  char *end = NULL;
  long long parsed_size;
  int descriptor;
  int accepted;

  if (argc != 4) {{
    return 2;
  }}
  parsed_size = strtoll(argv[2], &end, 10);
  if (end == argv[2] || *end != '\\0' || parsed_size <= 0) {{
    return 2;
  }}
  descriptor = open(argv[1], O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (descriptor < 0) {{
    return 2;
  }}
  accepted = verify_fd_pin(descriptor, (off_t)parsed_size, argv[3]);
  (void)close(descriptor);
  return accepted == 0 ? 0 : 3;
}}
""".lstrip(),
        encoding="utf-8",
    )
    _compile(
        source,
        output,
        "VISTA_R8_ADMIN_STAGE_RUNTIME",
        python_pin,
        helper_pin,
    )


@pytest.fixture(scope="module")
def launchers(tmp_path_factory: pytest.TempPathFactory) -> CompiledLaunchers:
    if not GCC.is_file() or not READELF.is_file():
        pytest.skip("reviewed GCC/readelf paths are unavailable")
    root = tmp_path_factory.mktemp("vista-r8-admin-launchers")
    runtime = root / "runtime-admin-launcher"
    bundle = root / "bundle-admin-launcher"
    python_pin = _pin(Path(PYTHON_PATH))
    helper_pin = _pin(HELPER_SOURCE)
    _compile(
        SOURCE,
        runtime,
        "VISTA_R8_ADMIN_STAGE_RUNTIME",
        python_pin,
        helper_pin,
    )
    _compile(
        SOURCE,
        bundle,
        "VISTA_R8_ADMIN_STAGE_BUNDLE",
        python_pin,
        helper_pin,
    )
    return CompiledLaunchers(
        runtime=runtime,
        bundle=bundle,
        python_pin=python_pin,
        helper_pin=helper_pin,
    )


@pytest.fixture(scope="module")
def hash_harness(
    tmp_path_factory: pytest.TempPathFactory, launchers: CompiledLaunchers
) -> Path:
    root = tmp_path_factory.mktemp("vista-r8-admin-hash-harness")
    source = root / "hash-harness.c"
    output = root / "hash-harness"
    _compile_hash_harness(
        source,
        output,
        launchers.python_pin,
        launchers.helper_pin,
    )
    return output


@pytest.mark.parametrize(
    "defines",
    [
        (),
        (
            "-DVISTA_R8_ADMIN_STAGE_RUNTIME=1",
            "-DVISTA_R8_ADMIN_STAGE_BUNDLE=1",
        ),
    ],
)
def test_compile_requires_exactly_one_stage(
    tmp_path: Path, defines: tuple[str, ...]
) -> None:
    if not GCC.is_file():
        pytest.skip("reviewed GCC path is unavailable")
    result = subprocess.run(
        [
            str(GCC),
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            *defines,
            *_pin_defines(_pin(Path(PYTHON_PATH)), _pin(HELPER_SOURCE)),
            str(SOURCE),
            "-o",
            str(tmp_path / "invalid-stage"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "define exactly one VISTA R8 administrator stage" in result.stderr


@pytest.mark.parametrize(
    "missing_define",
    [
        "EXPECTED_PYTHON_SHA256",
        "EXPECTED_PYTHON_SIZE",
        "EXPECTED_HELPER_SHA256",
        "EXPECTED_HELPER_SIZE",
    ],
)
def test_compile_requires_every_reviewed_file_pin(
    tmp_path: Path, missing_define: str
) -> None:
    if not GCC.is_file():
        pytest.skip("reviewed GCC path is unavailable")
    defines = [
        value
        for value in _pin_defines(_pin(Path(PYTHON_PATH)), _pin(HELPER_SOURCE))
        if not value.startswith(f"-D{missing_define}=")
    ]
    result = subprocess.run(
        [
            str(GCC),
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DVISTA_R8_ADMIN_STAGE_RUNTIME=1",
            *defines,
            str(SOURCE),
            "-o",
            str(tmp_path / f"missing-{missing_define}"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert f"{missing_define} is required" in result.stderr


@pytest.mark.parametrize("binary_name", ["runtime", "bundle"])
def test_stage_binaries_are_static_without_an_elf_interpreter(
    launchers: CompiledLaunchers, binary_name: str
) -> None:
    binary = getattr(launchers, binary_name)
    program_headers = subprocess.run(
        [str(READELF), "-lW", str(binary)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    dynamic = subprocess.run(
        [str(READELF), "-dW", str(binary)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert " INTERP " not in program_headers
    assert "Requesting program interpreter" not in program_headers
    assert "There is no dynamic section in this file." in dynamic
    assert "(NEEDED)" not in dynamic


@pytest.mark.parametrize(
    ("payload", "known_sha256"),
    [
        (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
        (
            b"a" * 1_000_000,
            "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
        ),
    ],
    ids=("abc", "million-a"),
)
def test_internal_sha256_matches_known_vectors(
    tmp_path: Path, hash_harness: Path, payload: bytes, known_sha256: str
) -> None:
    candidate = tmp_path / "candidate"
    candidate.write_bytes(payload)
    assert hashlib.sha256(payload).hexdigest() == known_sha256

    result = subprocess.run(
        [str(hash_harness), str(candidate), str(len(payload)), known_sha256],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_internal_pin_check_rejects_hash_size_and_content_drift(
    tmp_path: Path, hash_harness: Path
) -> None:
    candidate = tmp_path / "candidate"
    original = b"reviewed helper bytes\n"
    expected_sha256 = hashlib.sha256(original).hexdigest()
    candidate.write_bytes(original)

    def check(size: int, sha256: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(hash_harness), str(candidate), str(size), sha256],
            check=False,
            capture_output=True,
            text=True,
        )

    assert check(len(original), expected_sha256).returncode == 0
    assert check(len(original) + 1, expected_sha256).returncode == 3
    assert check(len(original), "0" * 64).returncode == 3
    assert check(len(original), expected_sha256.upper()).returncode == 3

    candidate.write_bytes(b"tampered helper bytes\n")
    assert len(candidate.read_bytes()) == len(original)
    assert check(len(original), expected_sha256).returncode == 3


def test_held_helper_fd_path_resolves_to_the_literal_file(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "held_helper_resolve_probe.py"
    probe.write_text(
        "from pathlib import Path\n"
        "actual = Path(__file__).resolve(strict=True)\n"
        f"expected = Path({str(probe)!r}).resolve(strict=True)\n"
        "raise SystemExit(0 if actual == expected else 7)\n",
        encoding="utf-8",
    )
    descriptor = os.open(probe, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        result = subprocess.run(
            [
                PYTHON_PATH,
                "-I",
                "-B",
                f"/proc/self/fd/{descriptor}",
            ],
            check=False,
            capture_output=True,
            text=True,
            pass_fds=(descriptor,),
        )
    finally:
        os.close(descriptor)
    assert result.returncode == 0, result.stderr


def test_runtime_binary_contains_only_the_runtime_stage_contract(
    launchers: CompiledLaunchers,
) -> None:
    raw = launchers.runtime.read_bytes()

    for expected in (
        RUNTIME_SELF,
        RUNTIME_PUBLISH,
        RUNTIME_RECONCILE,
        RUNTIME_PUBLISH_ACK,
        RUNTIME_RECONCILE_ACK,
    ):
        assert expected.encode() in raw
    for forbidden in (
        BUNDLE_SELF,
        BUNDLE_PUBLISH,
        BUNDLE_RECONCILE,
        BUNDLE_PUBLISH_ACK,
        BUNDLE_RECONCILE_ACK,
    ):
        assert forbidden.encode() not in raw


def test_bundle_binary_contains_only_the_bundle_stage_contract(
    launchers: CompiledLaunchers,
) -> None:
    raw = launchers.bundle.read_bytes()

    for expected in (
        BUNDLE_SELF,
        BUNDLE_PUBLISH,
        BUNDLE_RECONCILE,
        BUNDLE_PUBLISH_ACK,
        BUNDLE_RECONCILE_ACK,
    ):
        assert expected.encode() in raw
    for forbidden in (
        RUNTIME_SELF,
        RUNTIME_PUBLISH,
        RUNTIME_RECONCILE,
        RUNTIME_PUBLISH_ACK,
        RUNTIME_RECONCILE_ACK,
    ):
        assert forbidden.encode() not in raw


@pytest.mark.parametrize("binary_name", ["runtime", "bundle"])
def test_each_binary_embeds_only_fixed_execution_inputs(
    launchers: CompiledLaunchers, binary_name: str
) -> None:
    raw = getattr(launchers, binary_name).read_bytes()
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        PYTHON_PATH,
        HELPER_PATH,
        "/proc/self/exe",
        "/proc/self/fd/%d",
        "--acknowledgement",
        "PATH=/usr/bin:/bin",
        "HOME=/nonexistent",
        "LANG=C.UTF-8",
        "PYTHONNOUSERSITE=1",
        "PYTHONDONTWRITEBYTECODE=1",
        launchers.python_pin.sha256,
        launchers.helper_pin.sha256,
    ):
        assert expected.encode() in raw

    assert "SYS_execveat" in source
    assert "AT_EMPTY_PATH" in source
    assert "O_NOFOLLOW" in source
    assert "FD_CLOEXEC" in source
    assert "verify_fd_pin" in source
    assert "same_file_identity" in source
    assert source.count("open_verified_regular(EXPECTED_SELF_PATH") == 2
    assert "getenv(" not in source
    assert "system(" not in source
    assert "popen(" not in source
    assert "PYTHONHOME=" not in source


@pytest.mark.parametrize(
    ("binary_name", "wrong_operation"),
    [
        ("runtime", BUNDLE_PUBLISH),
        ("runtime", BUNDLE_RECONCILE),
        ("bundle", RUNTIME_PUBLISH),
        ("bundle", RUNTIME_RECONCILE),
        ("runtime", "caller-selected-operation"),
        ("bundle", "caller-selected-operation"),
    ],
)
def test_wrong_or_cross_stage_operation_is_rejected_before_root_entry(
    launchers: CompiledLaunchers, binary_name: str, wrong_operation: str
) -> None:
    result = subprocess.run(
        [
            str(getattr(launchers, binary_name)),
            wrong_operation,
            "caller-selected-acknowledgement",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 126
    assert result.stderr == (
        "R8_ADMIN_LAUNCHER: operation differs from compiled stage\n"
    )


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        (RUNTIME_PUBLISH,),
        (RUNTIME_PUBLISH, RUNTIME_PUBLISH_ACK, "extra"),
    ],
)
def test_runtime_launcher_rejects_any_arity_other_than_operation_and_ack(
    launchers: CompiledLaunchers, arguments: tuple[str, ...]
) -> None:
    result = subprocess.run(
        [str(launchers.runtime), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 126
    assert result.stderr == (
        "R8_ADMIN_LAUNCHER: exactly one operation and acknowledgement required\n"
    )


@pytest.mark.parametrize(
    ("binary_name", "operation", "wrong_acknowledgement"),
    [
        ("runtime", RUNTIME_PUBLISH, RUNTIME_RECONCILE_ACK),
        ("runtime", RUNTIME_RECONCILE, RUNTIME_PUBLISH_ACK),
        ("bundle", BUNDLE_PUBLISH, BUNDLE_RECONCILE_ACK),
        ("bundle", BUNDLE_RECONCILE, "approved"),
    ],
)
def test_operation_requires_its_exact_embedded_acknowledgement(
    launchers: CompiledLaunchers,
    binary_name: str,
    operation: str,
    wrong_acknowledgement: str,
) -> None:
    result = subprocess.run(
        [
            str(getattr(launchers, binary_name)),
            operation,
            wrong_acknowledgement,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 126
    assert result.stderr == "R8_ADMIN_LAUNCHER: acknowledgement differs\n"


@pytest.mark.skipif(os.geteuid() == 0, reason="test requires an unprivileged EUID")
@pytest.mark.parametrize(
    ("binary_name", "operation", "acknowledgement"),
    [
        ("runtime", RUNTIME_PUBLISH, RUNTIME_PUBLISH_ACK),
        ("bundle", BUNDLE_RECONCILE, BUNDLE_RECONCILE_ACK),
    ],
)
def test_valid_stage_operation_still_requires_root_euid(
    launchers: CompiledLaunchers,
    binary_name: str,
    operation: str,
    acknowledgement: str,
) -> None:
    result = subprocess.run(
        [str(getattr(launchers, binary_name)), operation, acknowledgement],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 126
    assert result.stderr == "R8_ADMIN_LAUNCHER: root EUID required\n"


def test_user_namespace_root_still_rejects_a_noninstalled_self(
    launchers: CompiledLaunchers,
) -> None:
    unshare = shutil.which("unshare")
    if unshare is None:
        pytest.skip("unshare is unavailable")
    result = subprocess.run(
        [
            unshare,
            "-Ur",
            str(launchers.runtime),
            RUNTIME_PUBLISH,
            RUNTIME_PUBLISH_ACK,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 126 and "Operation not permitted" in result.stderr:
        pytest.skip("unprivileged user namespaces are disabled")
    assert result.returncode == 126
    assert result.stderr == ("R8_ADMIN_LAUNCHER: installed self metadata differs\n")
