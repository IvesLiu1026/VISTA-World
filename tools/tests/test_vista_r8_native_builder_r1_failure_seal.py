from __future__ import annotations

import fcntl
import os
import re
import stat
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SEALER = ROOT / "tools/admin/seal_vista_r8_native_builder_r1_failure.sh"


def _raw() -> str:
    return SEALER.read_text(encoding="utf-8")


def _function_harness(body: str) -> str:
    raw = _raw()
    marker = '[[ "${EUID}" -eq 0 ]]'
    assert marker in raw
    return raw.split(marker, 1)[0] + "\n" + body + "\n"


def _secure_lock_probe(tmp_path: Path) -> tuple[Path, Path, Path]:
    state_root = tmp_path / "state"
    phase_a = state_root / "phase-a-slot"
    phase_b = state_root / "phase-b-slot"
    phase_a.mkdir(parents=True)
    phase_b.mkdir()
    phase_a.chmod(0o711)
    phase_b.chmod(0o711)
    lock_a = phase_a / ".build.lock"
    lock_b = phase_b / ".build.lock"
    lock_a.write_bytes(b"")
    lock_b.write_bytes(b"")
    lock_a.chmod(0o600)
    lock_b.chmod(0o600)

    probe = tmp_path / "secure-lock-probe.sh"
    prefix = (
        _function_harness("")
        .replace(
            "readonly LIVE_SELF='/root/"
            "seal-vista-r8-native-builder-r1-failure-83f180e0-20260901b.sh'",
            f"readonly LIVE_SELF='{probe}'",
        )
        .replace(
            "readonly STATE_ROOT='/var/lib/vista-r8-native-builder-r1'",
            f"readonly STATE_ROOT='{state_root}'",
        )
        .replace(
            "readonly R1_BUILDER_UID='997'", f"readonly R1_BUILDER_UID='{os.getuid()}'"
        )
        .replace(
            "readonly R1_BUILDER_GID='997'", f"readonly R1_BUILDER_GID='{os.getgid()}'"
        )
    )
    body = r"""
secure_reexec_with_r1_build_locks
lock_a_id="$(/usr/bin/stat -Lc '%d:%i' -- "/proc/$$/fd/${R1_PHASE_A_LOCK_FD}")"
lock_b_id="$(/usr/bin/stat -Lc '%d:%i' -- "/proc/$$/fd/${R1_PHASE_B_LOCK_FD}")"
verify_held_r1_lock "${STATE_ROOT}/phase-a-slot/.build.lock" \
  "${R1_PHASE_A_LOCK_FD}" "${lock_a_id}" 'probe Phase A lock'
verify_held_r1_lock "${STATE_ROOT}/phase-b-slot/.build.lock" \
  "${R1_PHASE_B_LOCK_FD}" "${lock_b_id}" 'probe Phase B lock'
printf '%s\n' SECURE_LOCKS_HELD
"""
    probe.write_text(prefix + "\n" + body, encoding="utf-8")
    probe.chmod(0o700)
    return probe, lock_a, lock_b


def _manager_fixture(*, phase: str, drift: tuple[str, str] | None = None) -> str:
    if phase == "a":
        values = {
            "MainPID": "0",
            "ControlPID": "0",
            "Result": "exit-code",
            "NRestarts": "0",
            "ExecMainStartTimestampMonotonic": "675339972529",
            "ExecMainExitTimestampMonotonic": "675341234136",
            "ExecMainCode": "1",
            "ExecMainStatus": "2",
            "ProcSubset": "all",
            "Names": "vista-r8-native-builder-phase-a.service",
            "LoadState": "loaded",
            "ActiveState": "failed",
            "SubState": "failed",
            "FragmentPath": "/etc/systemd/system/vista-r8-native-builder-phase-a.service",
            "DropInPaths": "",
            "UnitFileState": "static",
            "ActiveEnterTimestampMonotonic": "0",
            "Job": "",
            "NeedDaemonReload": "no",
            "ConditionResult": "yes",
            "InvocationID": "81d481f1eb764c60a737835b867fcb63",
        }
    else:
        values = {
            "MainPID": "0",
            "ControlPID": "0",
            "Result": "success",
            "NRestarts": "0",
            "ExecMainStartTimestampMonotonic": "0",
            "ExecMainExitTimestampMonotonic": "0",
            "ExecMainCode": "0",
            "ExecMainStatus": "0",
            "ProcSubset": "all",
            "Names": "vista-r8-native-builder-phase-b.service",
            "LoadState": "loaded",
            "ActiveState": "inactive",
            "SubState": "dead",
            "FragmentPath": "/etc/systemd/system/vista-r8-native-builder-phase-b.service",
            "DropInPaths": "",
            "UnitFileState": "static",
            "ActiveEnterTimestampMonotonic": "0",
            "Job": "",
            "NeedDaemonReload": "no",
            "ConditionResult": "no",
            "InvocationID": "",
        }
    if drift is not None:
        values[drift[0]] = drift[1]
    return "".join(f"{key}={value}\n" for key, value in values.items())


def test_shell_syntax() -> None:
    subprocess.run(["/usr/bin/bash", "-n", str(SEALER)], check=True)


def test_fixed_evidence_contract_and_known_failure_pins() -> None:
    raw = _raw()
    required = (
        "vista.r8-native-builder-r1-failure-seal/v1",
        "EVIDENCE_PARENT='/root'",
        "FINAL_NAME='vista-r8-native-builder-r1-failure-seal-"
        "b7ead170-83f180e0-20260901b'",
        "'81d481f1eb764c60a737835b867fcb63'",
        "'675339972529'",
        "'675341234136'",
        "'TRACE_PATH_DRIFT: trace host file[21]'",
        "'b5ce8dc8b558ee62f92247c97a5daa169ec83e3864fa388f6088aad3aa3a904f'",
        "'abd3c562ad5b975919aab3a6b0420f5326bd802774dda6e74a0db99d78b95387'",
        "'9b6c4b587456de26e9c20560d5eb62d09982e73e1e6cb9493dbf663b521fa441'",
        "'f3acaf39ad92fe2bc70680c9f7e0d8ab1e1f68f68553ebd4a74137c0cf939520'",
        "'1e65b23e2ae857b88d3b488a63cfcba3d6462c265ff3b4d3b33da046b9f96035'",
        "REQUEST_V4_RECORD_SHA256='d368db55dc50b90822dda55d2c1ad5b2a8cdabaf8b9ba7aac61e50832f4fd476'",
        "request-v4-record.json",
        "manifest.txt",
        "receipt.sha256",
    )
    for token in required:
        assert token in raw


def test_script_has_only_observational_systemd_commands() -> None:
    raw = _raw()
    invocations = re.findall(r"/usr/bin/systemctl\s+([^\n\\]+)", raw)
    assert invocations
    assert all(invocation.strip().startswith("show") for invocation in invocations)
    assert not re.search(
        r"/usr/bin/systemctl\s+(?:start|stop|restart|reload|daemon-reload|"
        r"reset-failed|enable|disable|mask|unmask|kill)\b",
        raw,
    )
    assert "/usr/bin/journalctl" in raw


def test_journal_boot_id_is_compacted_without_losing_kernel_evidence() -> None:
    raw = _raw()
    assert 'JOURNAL_BOOT_ID="$(compact_journal_boot_id "${BOOT_ID}")"' in raw
    assert raw.count('--boot="${JOURNAL_BOOT_ID}"') == 2
    assert '--boot="${BOOT_ID}"' not in raw
    assert 'printf \'%s\\n\' "${BOOT_ID}" >"${STAGING_PATH}/boot-id.txt"' in raw

    harness = _function_harness('compact_journal_boot_id "$1"')
    accepted = subprocess.run(
        [
            "/usr/bin/bash",
            "-c",
            harness,
            "fixture",
            "9121029d-2bf0-4ace-9413-2c6031f95f8b",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout == "9121029d2bf04ace94132c6031f95f8b"

    rejected = subprocess.run(
        ["/usr/bin/bash", "-c", harness, "fixture", "not-a-boot-id"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode != 0


def test_empty_file_evidence_uses_gnu_stat_empty_type(tmp_path: Path) -> None:
    fixture = tmp_path / "empty.lock"
    fixture.write_bytes(b"")
    fixture.chmod(0o600)
    harness = _function_harness(
        f'assert_empty_file "$1" 600 {os.getuid()} {os.getgid()} "fixture lock"'
    )
    accepted = subprocess.run(
        ["/usr/bin/bash", "-c", harness, "fixture", str(fixture)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert accepted.returncode == 0, accepted.stderr

    fixture.write_bytes(b"not empty")
    rejected = subprocess.run(
        ["/usr/bin/bash", "-c", harness, "fixture", str(fixture)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 126
    assert "metadata differs" in rejected.stderr


def test_no_replace_lock_and_staging_only_cleanup_are_explicit() -> None:
    raw = _raw()
    assert "candidate run's evidence" in raw
    assert 'assert_directory "${EVIDENCE_PARENT}" 700 0 0' in raw
    assert "flock -n" in raw
    assert "mv -T --no-clobber" in raw
    assert 'rm -rf --one-file-system -- "${STAGING_PATH}"' in raw
    assert raw.count("rm -rf") == 1
    assert "STAGING_OWNED='true'" in raw
    assert "PUBLISHED='true'" in raw
    assert "final evidence already exists" in raw
    assert "final evidence collided before publish" in raw
    assert raw.count("trap '' HUP INT TERM") == 2
    create = raw.index("/usr/bin/mkdir -m 0700")
    owned = raw.index("STAGING_OWNED='true'", create)
    assert create < owned < raw.index("trap 'exit 129' HUP", owned)
    publish = raw.index("mv -T --no-clobber")
    published = raw.index("PUBLISHED='true'", publish)
    assert publish < published < raw.index("trap 'exit 129' HUP", published)


def test_discovery_materializes_checked_owned_nul_lists() -> None:
    raw = _raw()
    assert "mapfile" not in raw
    assert "< <(" not in raw
    assert "fresh_traversal_list" in raw
    assert "if ! /usr/bin/find -P" in raw
    assert '/usr/bin/sort -z >"${list}"' in raw
    assert '/usr/bin/sort -z >"${roots_list}"' in raw
    assert 'rm -f -- "${list}" || fail' in raw
    assert 'rm -f -- "${roots_list}" || fail' in raw
    assert 'encoded_path="$(encode "${path}")" || fail' in raw
    assert not re.search(r"printf [^\n]*\$\(encode", raw)


def test_self_and_terminal_hashes_are_fail_closed() -> None:
    raw = _raw()
    assert 'SELF_HELD="/proc/$$/fd/${SELF_FD}"' in raw
    assert 'sha256_of "${SELF_HELD}"' in raw
    assert "verify_live_self" in raw
    assert 'FINAL_MANIFEST_SHA256="$(sha256_of' in raw
    assert 'FINAL_RECEIPT_SHA256="$(sha256_of' in raw
    assert not re.search(r"printf [^\n]*\$\(sha256_of", raw)
    assert 'cd "${STAGING_PATH}" &&' in raw
    assert 'cd "${FINAL_PATH}" &&' in raw


def test_each_manager_snapshot_has_one_phase_b_capture() -> None:
    raw = _raw()
    assert (
        raw.count(
            'capture_manager "${PHASE_B}" "${STAGING_PATH}/phase-b.systemctl-show.txt"'
        )
        == 1
    )
    assert (
        raw.count('capture_manager "${PHASE_B}" "${STAGING_PATH}/.phase-b.close"') == 1
    )


def test_r2_native_builder_namespaces_are_never_operational_targets() -> None:
    raw = _raw()
    forbidden = (
        "/usr/local/libexec/vista-r8-native-builder-r2",
        "/etc/vista-r8-native-builder-r2",
        "/var/lib/vista-r8-native-builder-r2",
        "/root/vista-r8-native-builder-bootstrap-r2",
        "vista-r8-native-builder-r2-phase-a.service",
        "vista-r8-native-builder-r2-phase-b.service",
    )
    for token in forbidden:
        assert token not in raw


def test_root_history_is_metadata_only_and_covers_prior_ceremonies() -> None:
    raw = _raw()
    assert "root-history-inventory.tsv" in raw
    assert "emit_record" in raw
    assert "sha256_of" in raw
    assert "stat -c" in raw
    assert "readlink" in raw
    for suffix in ("20260831b.sh", "20260831c.sh", "20260831d.sh"):
        assert f"recovery-b7ead170-{suffix}" in raw
    assert "failed-b7ead170-recovery-partial-20260831a" in raw
    assert "failed-journal-boot-descriptor-20260901a.sh" in raw
    assert "518e9ecbf2f37d9bb70069e334a0e4ab5125cf6a8a756abd28be31aaa1641c90" in raw
    assert 'assert_file "${FAILED_SEALER}" 500 0 0' in raw
    assert "failed-empty-lock-metadata-20260901b.sh" in raw
    assert "109dbc378343c0309198d2c43b0772e124201609554440c63d80dc1c9b7101ba" in raw
    assert 'assert_file "${FAILED_EMPTY_LOCK_SEALER}" 500 0 0' in raw
    assert 'emit_record "${FAILED_SEALER_LOCK}"' in raw
    assert 'assert_empty_file "${FAILED_SEALER_LOCK}" 600 0 0' in raw
    assert '[[ ! -e "${FAILED_EMPTY_LOCK_SEALER_LOCK}"' in raw
    assert "seal-vista-r8-native-builder-r1-failure-*.sh" in raw
    assert not re.search(r"(?:cp|install).*ROOT_HISTORY", raw)


def test_inventory_records_high_resolution_mtime_and_ctime(tmp_path: Path) -> None:
    raw = _raw()
    metadata_format = "%F|%a|%u|%g|%h|%s|%d|%i|%y|%z"
    assert metadata_format in raw
    assert "mtime_full|ctime_full" in raw
    assert "mtime_s" not in raw

    fixture = tmp_path / "restored-mtime.txt"
    fixture.write_bytes(b"same bytes\n")
    before_state = fixture.stat()
    before = subprocess.check_output(
        ["/usr/bin/stat", "-c", "%y|%z", "--", str(fixture)], text=True
    )
    time.sleep(0.01)
    fixture.write_bytes(b"same bytes\n")
    os.utime(
        fixture,
        ns=(before_state.st_atime_ns, before_state.st_mtime_ns),
    )
    after_state = fixture.stat()
    after = subprocess.check_output(
        ["/usr/bin/stat", "-c", "%y|%z", "--", str(fixture)], text=True
    )
    assert after_state.st_mtime_ns == before_state.st_mtime_ns
    assert after_state.st_ctime_ns != before_state.st_ctime_ns
    assert after != before


def test_r1_build_locks_use_noncreating_nofollow_reexec_and_rebind() -> None:
    raw = _raw()
    for token in (
        "secure_reexec_with_r1_build_locks",
        "os.O_RDONLY",
        "os.O_NOFOLLOW",
        "os.O_NONBLOCK",
        "fcntl.LOCK_EX | fcntl.LOCK_NB",
        "os.dup2(source, target, inheritable=True)",
        'os.execve("/usr/bin/bash", ["/usr/bin/bash", live_self], environment)',
        '/usr/bin/flock -n "${R1_PHASE_A_LOCK_FD}"',
        '/usr/bin/flock -n "${R1_PHASE_B_LOCK_FD}"',
        "verify_held_r1_lock",
        '"${R1_PHASE_A_LOCK_ID}"',
        '"${R1_PHASE_B_LOCK_ID}"',
    ):
        assert token in raw
    assert raw.count("verify_held_r1_lock") >= 5
    assert "os.O_CREAT" not in raw
    assert not re.search(r"exec[^\n]*<>[^\n]*\.build\.lock", raw)
    assert raw.index(
        "secure_reexec_with_r1_build_locks\nR1_PHASE_A_LOCK_ID"
    ) < raw.index("cannot create fixed seal lock")


def test_secure_r1_lock_opener_holds_both_locks(tmp_path: Path) -> None:
    probe, lock_a, lock_b = _secure_lock_probe(tmp_path)
    result = subprocess.run(
        ["/usr/bin/bash", str(probe)],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "SECURE_LOCKS_HELD\n"
    assert lock_a.is_file()
    assert lock_b.is_file()


def test_secure_r1_lock_opener_never_creates_or_follows(tmp_path: Path) -> None:
    missing_probe, missing, _ = _secure_lock_probe(tmp_path / "missing")
    missing.unlink()
    missing_result = subprocess.run(
        ["/usr/bin/bash", str(missing_probe)],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert missing_result.returncode == 126
    assert not missing.exists()

    symlink_probe, symlink, _ = _secure_lock_probe(tmp_path / "symlink")
    victim = tmp_path / "symlink" / "victim"
    victim.write_bytes(b"must remain untouched\n")
    symlink.unlink()
    symlink.symlink_to(victim)
    symlink_result = subprocess.run(
        ["/usr/bin/bash", str(symlink_probe)],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert symlink_result.returncode == 126
    assert symlink.is_symlink()
    assert victim.read_bytes() == b"must remain untouched\n"

    fifo_probe, fifo, _ = _secure_lock_probe(tmp_path / "fifo")
    fifo.unlink()
    os.mkfifo(fifo, mode=0o600)
    fifo_result = subprocess.run(
        ["/usr/bin/bash", str(fifo_probe)],
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    assert fifo_result.returncode == 126
    assert stat.S_ISFIFO(fifo.lstat().st_mode)


def test_r1_lock_contention_and_replacement_fail_closed(tmp_path: Path) -> None:
    lock = tmp_path / "build.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
    prefix = (
        _function_harness("")
        .replace(
            "readonly R1_BUILDER_UID='997'", f"readonly R1_BUILDER_UID='{os.getuid()}'"
        )
        .replace(
            "readonly R1_BUILDER_GID='997'", f"readonly R1_BUILDER_GID='{os.getgid()}'"
        )
    )

    with lock.open("r+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        contended = subprocess.run(
            [
                "/usr/bin/bash",
                "-c",
                prefix + '\nexec 18<>"$1"\n/usr/bin/flock -n 18\n',
                "fixture",
                str(lock),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
    assert contended.returncode != 0

    replacement_harness = (
        prefix
        + """
exec 18<>"$1"
/usr/bin/flock -n 18
lock_id="$(/usr/bin/stat -Lc '%d:%i' -- /proc/$$/fd/18)"
/usr/bin/mv -- "$1" "$1.old"
: >"$1"
/usr/bin/chmod 0600 -- "$1"
verify_held_r1_lock "$1" 18 "$lock_id" 'fixture lock'
"""
    )
    replaced = subprocess.run(
        ["/usr/bin/bash", "-c", replacement_harness, "fixture", str(lock)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert replaced.returncode == 126
    assert "inode binding differs" in replaced.stderr


def test_manager_fixture_accepts_only_the_exact_failed_r1_state(tmp_path: Path) -> None:
    phase_a = tmp_path / "a.show"
    phase_b = tmp_path / "b.show"
    phase_a.write_text(_manager_fixture(phase="a"), encoding="utf-8")
    phase_b.write_text(_manager_fixture(phase="b"), encoding="utf-8")
    harness = _function_harness('assert_manager_state "$1" "$2"')
    accepted = subprocess.run(
        ["/usr/bin/bash", "-c", harness, "fixture", str(phase_a), str(phase_b)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert accepted.returncode == 0, accepted.stderr

    phase_a.write_text(
        _manager_fixture(phase="a", drift=("ExecMainStatus", "0")),
        encoding="utf-8",
    )
    rejected = subprocess.run(
        ["/usr/bin/bash", "-c", harness, "fixture", str(phase_a), str(phase_b)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 126
    assert "ExecMainStatus differs" in rejected.stderr


def test_empty_manager_properties_cannot_fail_open(tmp_path: Path) -> None:
    phase_a = tmp_path / "a.show"
    phase_b = tmp_path / "b.show"
    phase_a.write_text(_manager_fixture(phase="a"), encoding="utf-8")
    phase_b.write_text(_manager_fixture(phase="b"), encoding="utf-8")
    harness = _function_harness('assert_manager_state "$1" "$2"')

    missing = _manager_fixture(phase="a").replace("DropInPaths=\n", "")
    phase_a.write_text(missing, encoding="utf-8")
    rejected_missing = subprocess.run(
        ["/usr/bin/bash", "-c", harness, "fixture", str(phase_a), str(phase_b)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected_missing.returncode == 126
    assert "cannot read unique manager property: DropInPaths" in rejected_missing.stderr

    duplicate = _manager_fixture(phase="a") + "DropInPaths=\n"
    phase_a.write_text(duplicate, encoding="utf-8")
    rejected_duplicate = subprocess.run(
        ["/usr/bin/bash", "-c", harness, "fixture", str(phase_a), str(phase_b)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected_duplicate.returncode == 126
    assert (
        "cannot read unique manager property: DropInPaths" in rejected_duplicate.stderr
    )


def test_inventory_fixture_rejects_an_extra_entry(tmp_path: Path) -> None:
    (tmp_path / "one").write_text("one", encoding="utf-8")
    harness = _function_harness('assert_inventory "$1" "$2"')
    accepted = subprocess.run(
        ["/usr/bin/bash", "-c", harness, "fixture", str(tmp_path), "one"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert accepted.returncode == 0, accepted.stderr

    (tmp_path / "two").write_text("two", encoding="utf-8")
    rejected = subprocess.run(
        ["/usr/bin/bash", "-c", harness, "fixture", str(tmp_path), "one"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 126
    assert "inventory differs" in rejected.stderr
