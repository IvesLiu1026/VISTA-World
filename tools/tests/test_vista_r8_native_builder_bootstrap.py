from __future__ import annotations

from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).parents[2]
BOOTSTRAP = ROOT / "tools/admin/bootstrap_vista_r8_native_builder.sh"
UNIT_ROOT = ROOT / "tools/admin/systemd"
PHASE_A_UNIT = UNIT_ROOT / "vista-r8-native-builder-phase-a.service"
PHASE_B_UNIT = UNIT_ROOT / "vista-r8-native-builder-phase-b.service"
RUNBOOK = ROOT / "docs/runbooks/vista-r8-native-builder-r1.md"

INPUT_ROOT = "/etc/vista-r8-native-builder-r1"
STATE_ROOT = "/var/lib/vista-r8-native-builder-r1"
BUILDER = "/usr/local/libexec/vista-r8-native-builder-r1/vista_r8_native_builder.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, name: str) -> list[str]:
    result: list[str] = []
    active = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            active = line == f"[{name}]"
        elif active and line and not line.startswith(("#", ";")):
            result.append(line)
    return result


def _values(lines: list[str], key: str) -> list[str]:
    prefix = f"{key}="
    return [line[len(prefix) :] for line in lines if line.startswith(prefix)]


def _bash_array(name: str) -> tuple[str, ...]:
    match = re.search(
        rf"readonly -a {re.escape(name)}=\(\n(?P<body>.*?)\n\)",
        _text(BOOTSTRAP),
        re.DOTALL,
    )
    assert match is not None
    return tuple(re.findall(r"^  '([^']+)'$", match.group("body"), re.MULTILINE))


def _subid_awk_program() -> str:
    match = re.search(
        r"readonly SUBID_RANGE_AWK='\n(?P<program>.*?)\n'\n",
        _text(BOOTSTRAP),
        re.DOTALL,
    )
    assert match is not None
    return match.group("program")


def _process_id_awk_program() -> str:
    match = re.search(
        r"readonly PROCESS_ID_AWK='\n(?P<program>.*?)\n'\n",
        _text(BOOTSTRAP),
        re.DOTALL,
    )
    assert match is not None
    return match.group("program")


def _bash_function(name: str) -> str:
    match = re.search(
        rf"^{re.escape(name)}\(\) \{{\n.*?^\}}\n",
        _text(BOOTSTRAP),
        re.DOTALL | re.MULTILINE,
    )
    assert match is not None
    return match.group(0)


def test_bootstrap_is_bash_syntax_clean_and_never_runs_systemd_or_builder() -> None:
    result = subprocess.run(
        ["/usr/bin/bash", "-n", str(BOOTSTRAP)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    text = _text(BOOTSTRAP)
    assert text.startswith("#!/usr/bin/env bash\n")
    assert '[[ "$#" -eq 8 ]]' in text
    assert '[[ "$#" -eq 6 ]]' in text
    assert '[[ "$#" -eq 4 ]]' in text
    assert 'readonly OPERATION="${1:-}"' in text
    assert "readonly INSTALL_FRAMEWORK='install-framework'" in text
    assert "readonly INSTALL_PHASE_A='install-phase-a-inputs'" in text
    assert "readonly INSTALL_PHASE_B='install-phase-b-request'" in text
    assert (
        "readonly INPUT_CANDIDATE_ROOT='/root/vista-r8-native-builder-bootstrap-input-r1'"
        in text
    )
    assert "/tmp/vista_r8_native_builder.py" not in text
    assert "systemctl daemon-reload" not in text
    assert re.search(r"systemctl\s+(start|enable|restart|try-restart)", text) is None
    assert re.search(r"python3(?:\.10)?\s+.*vista_r8_native_builder", text) is None


def test_bootstrap_local_declarations_do_not_expand_peer_assignments() -> None:
    """Bash expands a complete ``local`` command before assigning any peer."""

    for line_number, raw_line in enumerate(_text(BOOTSTRAP).splitlines(), start=1):
        line = raw_line.strip()
        if not line.startswith("local "):
            continue
        declared = set(re.findall(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=", line))
        expanded = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", line))
        assert not declared & expanded, (
            f"line {line_number} expands a variable declared by the same local "
            f"command: {line}"
        )


def test_bootstrap_fixes_identity_and_fails_closed_on_collisions() -> None:
    text = _text(BOOTSTRAP)
    for literal in (
        "readonly BUILDER_NAME='vista-r8-builder'",
        "readonly BUILDER_UID='997'",
        "readonly BUILDER_GID='997'",
        "readonly BUILDER_HOME='/nonexistent'",
        "readonly BUILDER_SHELL='/usr/sbin/nologin'",
        'getent group "${BUILDER_NAME}"',
        'getent group "${BUILDER_GID}"',
        'getent passwd "${BUILDER_NAME}"',
        'getent passwd "${BUILDER_UID}"',
        "builder group name/GID collision",
        "builder user name/UID collision",
        "--no-create-home --no-user-group --password '!'",
        'passwd --status "${BUILDER_NAME}"',
        "builder password must be locked",
        'id -G "${BUILDER_NAME}"',
        "builder supplementary groups are forbidden",
        "reject_subordinate_id_ranges",
        "numeric ID 997 has a delegated range",
    ):
        assert literal in text
    assert "usermod" not in text


@pytest.mark.parametrize(
    ("record", "expected_status"),
    [
        ("other:997:1\n", 0),
        ("other:900:98\n", 0),
        ("other:900:97\n", 1),
        ("other:998:65536\n", 1),
        ("vista-r8-builder:100000:65536\n", 0),
        ("other:4294967295:2\n", 2),
        ("other:not-a-number:2\n", 2),
        ("malformed\n", 2),
    ],
)
def test_subid_gate_rejects_any_range_containing_numeric_997(
    tmp_path: Path, record: str, expected_status: int
) -> None:
    database = tmp_path / "subid"
    database.write_text(record, encoding="ascii")
    result = subprocess.run(
        [
            "/usr/bin/awk",
            "-F:",
            "-v",
            "target=997",
            "-v",
            "builder=vista-r8-builder",
            _subid_awk_program(),
            str(database),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == expected_status, result.stderr


def test_subid_gate_checks_both_databases_without_username_assumption() -> None:
    text = _text(BOOTSTRAP)
    assert "for database in /etc/subuid /etc/subgid" in text
    assert '-v target="${BUILDER_UID}"' in text
    assert "(target >= start && target < end)" in text
    assert "$1 == builder ||" in text


@pytest.mark.parametrize(
    ("status_document", "expected_status"),
    [
        ("Uid:\t997\t997\t997\t997\nGid:\t0\t0\t0\t0\nGroups:\t0\n", 0),
        ("Uid:\t0\t0\t0\t0\nGid:\t997\t997\t997\t997\nGroups:\t0\n", 0),
        ("Uid:\t0\t0\t0\t0\nGid:\t0\t0\t0\t0\nGroups:\t27 997\n", 0),
        ("Uid:\t0\t0\t0\t0\nGid:\t0\t0\t0\t0\nGroups:\t0 27\n", 1),
        ("Uid:\t0\t0\t0\nGid:\t0\t0\t0\t0\nGroups:\t0\n", 2),
        ("Uid:\t0\t0\t0\t0\nGid:\t0\t0\t0\t0\n", 2),
    ],
)
def test_process_identity_gate_rejects_uid_gid_or_group_997(
    tmp_path: Path, status_document: str, expected_status: int
) -> None:
    status_file = tmp_path / "status"
    status_file.write_text(status_document, encoding="ascii")
    result = subprocess.run(
        [
            "/usr/bin/awk",
            "-v",
            "target=997",
            _process_id_awk_program(),
            str(status_file),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == expected_status, result.stderr


def test_bootstrap_rejects_orphan_builder_identity_processes() -> None:
    text = _text(BOOTSTRAP)
    assert text.count("assert_builder_identity_unused") >= 5
    assert "local -a status_files=(/proc/[0-9]*/status)" in text
    assert "numeric UID/GID 997 is active in process ${pid}" in text


def test_bootstrap_installs_only_fixed_roots_modes_and_slot_inventory() -> None:
    text = _text(BOOTSTRAP)
    for literal in (
        "readonly LIBEXEC_ROOT='/usr/local/libexec/vista-r8-native-builder-r1'",
        "readonly INPUT_ROOT='/etc/vista-r8-native-builder-r1'",
        "readonly STATE_ROOT='/var/lib/vista-r8-native-builder-r1'",
        'ensure_directory "${LIBEXEC_ROOT}" root root 0555 0 0',
        'ensure_directory "${INPUT_ROOT}" root root 0555 0 0',
        'ensure_directory "${STATE_ROOT}" root root 0555 0 0',
        'ensure_directory "${PHASE_A_SLOT}" "${BUILDER_NAME}" "${BUILDER_NAME}" 0711',
        'ensure_directory "${PHASE_B_SLOT}" "${BUILDER_NAME}" "${BUILDER_NAME}" 0711',
        'create_lock_once "${PHASE_A_SLOT}/.build.lock"',
        'create_lock_once "${PHASE_B_SLOT}/.build.lock"',
        'install_held_once "${BUILDER_FD}" "${BUILDER_DEST}"',
        'install_held_once "${PHASE_A_UNIT_FD}" "${UNIT_ROOT}/${PHASE_A_UNIT}"',
        'install_held_once "${PHASE_B_UNIT_FD}" "${UNIT_ROOT}/${PHASE_B_UNIT}"',
        'install_held_once "${BUNDLE_FD}" "${BUNDLE_DEST}"',
        'install_held_once "${PHASE_A_REQUEST_FD}" "${PHASE_A_REQUEST_DEST}"',
        'install_held_once "${PHASE_B_REQUEST_FD}" "${PHASE_B_REQUEST_DEST}"',
        '/usr/bin/sync --file-system -- "${TEMP_PATH}"',
        '/usr/bin/sync --file-system -- "${destination}"',
        '/usr/bin/sync --file-system -- "${destination%/*}"',
        "assert_exact_inventory \"${STATE_ROOT}\" 'phase-a-slot' 'phase-b-slot'",
        "assert_exact_inventory \"${PHASE_A_SLOT}\" '.build.lock'",
        "assert_exact_inventory \"${PHASE_B_SLOT}\" '.build.lock'",
    ):
        assert literal in text
    assert "${STATE_ROOT}/inputs" not in text
    assert "${STATE_ROOT}/published" not in text
    assert text.count('/usr/bin/sync --file-system -- "${path}"') >= 2
    assert text.count('/usr/bin/sync --file-system -- "${path%/*}"') >= 2
    assert text.count('/usr/bin/sync --file-system -- "${destination}"') >= 2
    assert text.count('/usr/bin/sync --file-system -- "${destination%/*}"') >= 2


def test_bootstrap_requires_inactive_empty_service_cgroups() -> None:
    text = _text(BOOTSTRAP)
    assert text.count('assert_unit_inactive_and_empty "${PHASE_A_UNIT}"') == 1
    assert text.count('assert_unit_inactive_and_empty "${PHASE_B_UNIT}"') == 1
    assert text.count("assert_services_quiescent") >= 5
    assert 'systemctl is-active "${unit}"' in text
    assert "/sys/fs/cgroup/system.slice/${unit}/cgroup.events" in text
    assert "grep -qx 'populated 0'" in text
    assert "systemd was not reloaded, enabled, or started" in text


def test_bootstrap_exhaustively_rejects_systemd_filesystem_overrides() -> None:
    assert _bash_array("SYSTEMD_UNIT_SEARCH_ROOTS") == (
        "/etc/systemd/system.control",
        "/run/systemd/system.control",
        "/run/systemd/transient",
        "/run/systemd/generator.early",
        "/etc/systemd/system",
        "/etc/systemd/system.attached",
        "/run/systemd/system",
        "/run/systemd/system.attached",
        "/run/systemd/generator",
        "/usr/local/lib/systemd/system",
        "/usr/lib/systemd/system",
        "/lib/systemd/system",
        "/run/systemd/generator.late",
    )
    assert _bash_array("SYSTEMD_DROPIN_NAMES") == (
        "vista-.service.d",
        "vista-r8-.service.d",
        "vista-r8-native-.service.d",
        "vista-r8-native-builder-.service.d",
        "vista-r8-native-builder-phase-.service.d",
        "service.d",
    )
    text = _text(BOOTSTRAP)
    audit = text.split("assert_unit_filesystem_provenance() {", 1)[1].split(
        "\n}\n\nassert_systemd_provenance()", 1
    )[0]
    for literal in (
        "custom SYSTEMD_UNIT_PATH is forbidden",
        'candidate="${root}/${unit}"',
        "shadow fragment, link, or mask is forbidden",
        'for dropin in "${unit}.d" "${SYSTEMD_DROPIN_NAMES[@]}"',
        "systemd drop-in path is forbidden",
        '/usr/bin/find -H "${root}" -mindepth 1 -print0 >/dev/null',
        "systemd alias, mask, enabled link, or linked unit is forbidden",
        '\\( -path "*.wants/${unit}" -o -path "*.requires/${unit}" \\)',
        "systemd wants/requires entry is forbidden",
    ):
        assert literal in audit
    assert text.count("assert_systemd_provenance 'true'") >= 2
    assert "assert_systemd_provenance 'false'" in text


def test_bootstrap_validates_loaded_manager_provenance_without_mutation() -> None:
    text = _text(BOOTSTRAP)
    manager = text.split("assert_unit_manager_provenance() {", 1)[1].split(
        "\n}\n\nassert_unit_filesystem_provenance()", 1
    )[0]
    for literal in (
        "/usr/bin/systemctl show --no-pager",
        "--property=LoadState",
        "--property=FragmentPath",
        "--property=DropInPaths",
        "--property=UnitFileState",
        "--property=Names",
        "--property=WantedBy",
        "--property=RequiredBy",
        '[[ "${fragment_path}" == "${expected}" ]]',
        "manager DropInPaths are forbidden",
        "manager reverse dependencies are forbidden",
        "manager aliases are forbidden",
        "manager UnitFileState is enabled, linked, masked, or otherwise forbidden",
        "manager FragmentPath differs",
    ):
        assert literal in manager
    assert (
        re.search(r"systemctl\s+(daemon-reload|start|enable|link|mask)", text) is None
    )


def test_bootstrap_requires_fixed_root_owned_live_self_and_held_assets() -> None:
    text = _text(BOOTSTRAP)
    for literal in (
        "readonly TRUSTED_ROOT='/root/vista-r8-native-builder-bootstrap-r1'",
        '[[ "${live_self}" == "${TRUSTED_SELF}" ]]',
        'assert_directory "${TRUSTED_ROOT}" 0 0 0555',
        'assert_directory "${TRUSTED_SYSTEMD}" 0 0 0555',
        "'bootstrap_vista_r8_native_builder.sh' 'vista_r8_native_builder.py' 'systemd'",
        'exec {SELF_FD}<"${TRUSTED_SELF}"',
        'exec {BUILDER_FD}<"${TRUSTED_BUILDER}"',
        'observed_held_pin "${SELF_FD}" 0 0 0500',
        'observed_held_pin "${BUILDER_FD}" 0 0 0400',
        'observed_held_pin "${PHASE_A_UNIT_FD}" 0 0 0400',
        'observed_held_pin "${PHASE_B_UNIT_FD}" 0 0 0400',
        "printf '/proc/%s/fd/%s' \"${BOOTSTRAP_PID}\"",
    ):
        assert literal in text


def test_runbook_requires_independent_bootstrap_self_pin_verification() -> None:
    text = _text(RUNBOOK)
    assert "The bootstrap script itself is part of that independent record" in text
    assert "separately conveyed SHA-256 and byte size" in text
    assert (
        "/root/vista-r8-native-builder-bootstrap-r1/"
        "bootstrap_vista_r8_native_builder.sh"
    ) in text
    assert re.search(r"does not self-authorize a digest derived from\s+itself", text)


def test_bootstrap_operations_have_literal_acknowledgements_and_no_destination() -> (
    None
):
    text = _text(BOOTSTRAP)
    for literal in (
        "readonly FRAMEWORK_ACK='I acknowledge installation or exact reconciliation",
        "readonly PHASE_A_ACK='I acknowledge fresh append or exact reconciliation",
        "readonly PHASE_B_ACK='I acknowledge fresh append or exact reconciliation",
        '[[ "$8" == "${FRAMEWORK_ACK}" ]]',
        '[[ "$6" == "${PHASE_A_ACK}" ]]',
        '[[ "$4" == "${PHASE_B_ACK}" ]]',
    ):
        assert literal in text
    assert "DESTINATION_SOURCE" not in text
    assert "CALLER_DESTINATION" not in text


def test_phase_b_input_append_requires_closed_phase_a_and_fresh_b_slot() -> None:
    text = _text(BOOTSTRAP)
    phase_b_case = text.split('"${INSTALL_PHASE_B}")', 1)[1]
    assert "assert_closed_phase_a" in phase_b_case
    assert "'artifacts' 'manifest.json' 'manifests' 'parent-seal-candidate'" in text
    assert 'assert_directory "${PHASE_A_FINAL}/parent-seal-candidate"' in text
    assert (
        "'vista_authority_parent_seal.py' 'launch-vista-authority-parent-seal'" in text
    )
    assert 'assert_closed_regular "${PHASE_A_FINAL}/artifacts/${name}"' in text
    assert 'assert_closed_regular "${PHASE_A_FINAL}/manifests/${name}"' in text
    assert (
        "assert_exact_inventory \"${PHASE_A_SLOT}\" '.build.lock' 'published'" in text
    )
    assert "assert_exact_inventory \"${PHASE_B_SLOT}\" '.build.lock'" in text
    assert text.count("'source bundle candidate'") >= 2
    assert text.count("'phase A request candidate'") >= 2
    assert text.count("'phase B request candidate'") >= 2


def test_terminal_operation_close_gate_is_the_last_validation_before_success() -> None:
    text = _text(BOOTSTRAP)
    gate = _bash_function("verify_operation_close_state")
    assert gate.count("verify_framework\n") == 1
    assert gate.index("verify_framework\n") < gate.index('case "${operation}" in')
    for literal in (
        'assert_exact_inventory "${INPUT_ROOT}"',
        "assert_exact_inventory \"${PHASE_A_SLOT}\" '.build.lock'",
        "assert_exact_inventory \"${PHASE_B_SLOT}\" '.build.lock'",
        'verify_installed_file "${BUNDLE_DEST}" "$2" "$3" 0444',
        'verify_installed_file "${PHASE_A_REQUEST_DEST}" "$4" "$5" 0444',
        'verify_installed_file "${PHASE_B_REQUEST_DEST}" "$2" "$3" 0444',
        '[[ ! -e "${PHASE_A_FINAL}" && ! -L "${PHASE_A_FINAL}" ]]',
        '[[ ! -e "${PHASE_B_FINAL}" && ! -L "${PHASE_B_FINAL}" ]]',
        "assert_closed_phase_a",
    ):
        assert literal in gate
    terminal = text.rsplit("esac\n", 1)[1]
    ordered = (
        "assert_services_quiescent",
        "assert_systemd_provenance 'true'",
        "assert_builder_identity_unused",
        'verify_held_file "${SELF_FD}"',
        'verify_held_file "${BUILDER_FD}"',
        'verify_held_file "${PHASE_A_UNIT_FD}"',
        'verify_held_file "${PHASE_B_UNIT_FD}"',
        'verify_operation_close_state "$@"',
        "printf '%s\\n'",
    )
    offsets = [terminal.index(literal) for literal in ordered]
    assert offsets == sorted(offsets)
    assert re.search(
        r'verify_operation_close_state "\$@"\n\nprintf \'%s\\n\'', terminal
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ("install-framework", "a", "1", "b", "2", "c", "3", "ack"),
        ("install-phase-a-inputs", "a", "1", "b", "2", "ack"),
        ("install-phase-b-request", "a", "1", "ack"),
    ],
)
def test_terminal_operation_close_gate_rejects_mocked_concurrent_mutation(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    harness = f"""
set -euo pipefail
INSTALL_FRAMEWORK='install-framework'
INSTALL_PHASE_A='install-phase-a-inputs'
INSTALL_PHASE_B='install-phase-b-request'
INPUT_ROOT={tmp_path!s}/inputs
PHASE_A_SLOT={tmp_path!s}/phase-a-slot
PHASE_B_SLOT={tmp_path!s}/phase-b-slot
PHASE_A_FINAL={tmp_path!s}/phase-a-final
PHASE_B_FINAL={tmp_path!s}/phase-b-final
BUNDLE_DEST={tmp_path!s}/source.bundle
PHASE_A_REQUEST_DEST={tmp_path!s}/phase-a-request.json
PHASE_B_REQUEST_DEST={tmp_path!s}/phase-b-request.json
BUNDLE_FD=10
PHASE_A_REQUEST_FD=11
PHASE_B_REQUEST_FD=12
PHASE_B_EXISTING_BUNDLE_SHA256='{"1" * 64}'
PHASE_B_EXISTING_BUNDLE_SIZE=1
PHASE_B_EXISTING_PHASE_A_SHA256='{"2" * 64}'
PHASE_B_EXISTING_PHASE_A_SIZE=2
STATE='clean'
fail() {{ printf '%s\n' "$*" >&2; exit 126; }}
verify_framework() {{ STATE='mutated-after-framework-check'; }}
assert_exact_inventory() {{
  [[ "${{STATE}}" == 'clean' ]] || fail 'terminal concurrent mutation detected'
}}
verify_installed_file() {{ :; }}
verify_held_file() {{ :; }}
assert_closed_phase_a() {{ :; }}
{_bash_function("verify_operation_close_state")}
verify_operation_close_state "$@"
"""
    result = subprocess.run(
        ["/usr/bin/bash", "-c", harness, "bootstrap-close-test", *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 126
    assert "terminal concurrent mutation detected" in result.stderr


def test_units_use_only_the_pinned_python_builder_and_literal_phase() -> None:
    for phase, path in (("phase-a", PHASE_A_UNIT), ("phase-b", PHASE_B_UNIT)):
        service = _section(_text(path), "Service")
        assert _values(service, "Type") == ["oneshot"]
        assert _values(service, "User") == ["vista-r8-builder"]
        assert _values(service, "Group") == ["vista-r8-builder"]
        assert _values(service, "SupplementaryGroups") == [""]
        assert _values(service, "UMask") == ["0077"]
        assert _values(service, "ExecStart") == [
            f"/usr/bin/python3.10 -I -B {BUILDER} --phase {phase}"
        ]
        assert all(
            not line.startswith(("ExecStartPre=", "ExecStartPost=", "ExecReload="))
            for line in service
        )


def test_units_are_network_filesystem_device_and_process_hardened() -> None:
    required = {
        "NoNewPrivileges=yes",
        "Restart=no",
        "KillMode=control-group",
        "KeyringMode=private",
        "StandardInput=null",
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
        "PrivateNetwork=yes",
        "PrivateDevices=yes",
        "PrivateTmp=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "ProtectClock=yes",
        "ProtectControlGroups=yes",
        "ProtectHostname=yes",
        "ProtectKernelLogs=yes",
        "ProtectKernelModules=yes",
        "ProtectKernelTunables=yes",
        "ProtectProc=invisible",
        "ProcSubset=all",
        f"ReadOnlyPaths={INPUT_ROOT}",
        "ReadOnlyPaths=/usr/local/libexec/vista-r8-native-builder-r1",
        "DevicePolicy=closed",
        "LockPersonality=yes",
        "MemoryDenyWriteExecute=yes",
        "RemoveIPC=yes",
        "RestrictAddressFamilies=AF_UNIX",
        "RestrictNamespaces=yes",
        "RestrictRealtime=yes",
        "RestrictSUIDSGID=yes",
        "SystemCallArchitectures=native",
        "SystemCallFilter=@system-service",
        "SystemCallFilter=~@clock @module @mount @obsolete @raw-io @reboot @swap",
        "SystemCallErrorNumber=EPERM",
        "TasksMax=64",
        "LimitNPROC=64",
    }
    for path in (PHASE_A_UNIT, PHASE_B_UNIT):
        text = _text(path)
        service_lines = _section(text, "Service")
        service = set(service_lines)
        assert required <= service
        assert _values(service_lines, "SystemCallFilter") == [
            "@system-service",
            "ptrace",
            "~@clock @module @mount @obsolete @raw-io @reboot @swap",
        ]
        assert _values(service_lines, "CapabilityBoundingSet") == [""]
        assert _values(service_lines, "AmbientCapabilities") == [""]
        assert "StateDirectory=vista-r8-native-builder-r1" not in service
        assert f"ReadWritePaths={STATE_ROOT}" not in service
        assert _section(text, "Install") == []


def test_units_expose_the_read_only_kernel_virtual_trace_authority() -> None:
    """Trace v4 pins /proc/sys/vm/overcommit_memory inside both builders."""
    for path in (PHASE_A_UNIT, PHASE_B_UNIT):
        service = _section(_text(path), "Service")
        assert _values(service, "ProcSubset") == ["all"]
        assert _values(service, "ProtectProc") == ["invisible"]
        assert _values(service, "ProtectKernelTunables") == ["yes"]
    runbook = _text(RUNBOOK)
    assert "`ProcSubset=all`" in runbook
    assert "`ProtectProc=invisible`" in runbook
    assert "`ProtectKernelTunables=yes`" in runbook


def test_phase_slots_are_mutually_write_isolated_and_b_reads_closed_a() -> None:
    phase_a_text = _text(PHASE_A_UNIT)
    phase_b_text = _text(PHASE_B_UNIT)
    phase_a_unit = _section(phase_a_text, "Unit")
    phase_b_unit = _section(phase_b_text, "Unit")
    phase_a_service = _section(phase_a_text, "Service")
    phase_b_service = _section(phase_b_text, "Service")

    phase_a_inputs = {
        f"{INPUT_ROOT}/source.bundle",
        f"{INPUT_ROOT}/phase-a-request.json",
    }
    phase_b_inputs = {
        *phase_a_inputs,
        f"{INPUT_ROOT}/phase-b-request.json",
    }
    assert phase_a_inputs <= set(_values(phase_a_unit, "ConditionPathExists"))
    assert f"{INPUT_ROOT}/phase-b-request.json" not in _values(
        phase_a_unit, "ConditionPathExists"
    )
    assert phase_b_inputs <= set(_values(phase_b_unit, "ConditionPathExists"))

    assert _values(phase_a_service, "WorkingDirectory") == [
        f"{STATE_ROOT}/phase-a-slot"
    ]
    assert _values(phase_a_service, "ReadWritePaths") == [f"{STATE_ROOT}/phase-a-slot"]
    assert _values(phase_b_service, "WorkingDirectory") == [
        f"{STATE_ROOT}/phase-b-slot"
    ]
    assert _values(phase_b_service, "ReadWritePaths") == [f"{STATE_ROOT}/phase-b-slot"]
    assert f"{STATE_ROOT}/phase-a-slot" not in _values(
        phase_b_service, "ReadWritePaths"
    )
    assert f"{STATE_ROOT}/phase-a-slot/published" in _values(
        phase_b_service, "ReadOnlyPaths"
    )

    assert _values(phase_b_unit, "Requires") == []
    assert _values(phase_b_unit, "After") == ["vista-r8-native-builder-phase-a.service"]
    phase_a_manifest = f"{STATE_ROOT}/phase-a-slot/published/manifest.json"
    phase_b_manifest = f"{STATE_ROOT}/phase-b-slot/published/manifest.json"
    assert phase_a_manifest in _values(phase_b_unit, "ConditionPathExists")
    assert f"!{phase_b_manifest}" in _values(phase_b_unit, "ConditionPathExists")
    assert f"!{phase_a_manifest}" in _values(phase_a_unit, "ConditionPathExists")


def test_runbook_preserves_layout_and_runtime_claims() -> None:
    text = _text(RUNBOOK)
    for literal in (
        "Status: source correction complete; inactive c963 framework retained as evidence;",
        "/root/vista-r8-native-builder-bootstrap-r1/",
        "/root/vista-r8-native-builder-bootstrap-input-r1/",
        "phase-a-slot/",
        "997:997 0711",
        "install-framework",
        "install-phase-a-inputs",
        "install-phase-b-request",
        "does not compile a local `yhliu` candidate",
        "Phase A inputs were not installed",
    ):
        assert literal in text
    assert "The Phase B unit has `After=phase-a` but not `Requires=phase-a`" in text
