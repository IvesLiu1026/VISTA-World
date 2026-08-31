from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREPARE = ROOT / "tools/admin/prepare_vista_r8_native_builder_r2.sh"
ACTIVATE = ROOT / "tools/admin/activate_vista_r8_native_builder_r2_phase_a.sh"


def _raw(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _prefix(path: Path) -> str:
    raw = _raw(path)
    marker = '[[ "${EUID}" -eq 0'
    assert marker in raw
    return raw.split(marker, 1)[0]


def test_scripts_have_valid_bash_syntax() -> None:
    for path in (PREPARE, ACTIVATE):
        subprocess.run(["/usr/bin/bash", "-n", str(path)], check=True)


def test_fixed_commit_input_and_reviewed_source_pins() -> None:
    raw = _raw(PREPARE)
    required = {
        "83f180e03935bcc7994962ec95f2d8c8027f405d",
        "54ba5e0ae512fa9661ccec04ee245de6510d343ae21445f8f169b239fd557533",
        "3301129",
        "fb8e99428b4e7cb043c96591f73d413500834667f263eeec3f3c70af66f318e0",
        "2483438",
        "bd82c3b8899eb71835a60dbc34b13b3dc0a8d0f8ea904c68be253b9d4444da37",
        "da51dfe7bef6495f3cc659d78de0795e3fd99404a17daaa5bcdea32795255084",
        "abc072477e5a10265405d1cc4d44c0f629142bb652beafc861080751fa7d59e7",
        "1a07936c9d3e5a157c6e3b13353c54cb2e8dbb3af26f06673b56a0f6b2a3d8f3",
        "403bf91313539edf78b840f3a3342d9270c2b503b03f6a6ce32d0ac9127ccd75",
        "vista.r8-native-builder-trace-contract/v5",
        "proc-chain-mount-metadata-volatile-v2",
    }
    for token in required:
        assert token in raw


def test_prepare_document_gate_is_exact_and_fail_closed() -> None:
    raw = _raw(PREPARE)
    required_checks = (
        'bundle_heads="$(/usr/bin/git bundle list-heads',
        '"${bundle_heads}" == "${COMMIT} ${BUNDLE_REF}"',
        'request.get("schema") != "vista.r8-native-builder-request/v2"',
        'request.get("source_commit") != expected_commit',
        'request.get("trace_contract", {}).get("schema") != "vista.r8-native-builder-trace-contract/v5"',
        'request.get("source_bundle", {}).get("path") != "/etc/vista-r8-native-builder-r2/source.bundle"',
        'input_set.get("schema") != "vista.r8-native-builder-r2-input-set/v1"',
        "observed != hashlib.sha256(canonical).hexdigest()",
    )
    for check in required_checks:
        assert check in raw


def test_candidate_fd_verifier_follows_only_the_held_fd(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.write_bytes(b"held-candidate\n")
    candidate.chmod(0o444)
    pin = hashlib.sha256(candidate.read_bytes()).hexdigest()
    size = candidate.stat().st_size
    prefix = (
        _prefix(PREPARE)
        .replace(
            "readonly CANDIDATE_UID='1000021'",
            f"readonly CANDIDATE_UID='{candidate.stat().st_uid}'",
        )
        .replace(
            "readonly CANDIDATE_GID='1000001'",
            f"readonly CANDIDATE_GID='{candidate.stat().st_gid}'",
        )
    )
    harness = (
        prefix
        + "\n"
        + """
exec 10<"$1"
verify_candidate_fd 10 "$1" "$2" "$3" >/dev/null
"""
    )
    result = subprocess.run(
        [
            "/usr/bin/bash",
            "-c",
            harness,
            "ceremony-test",
            str(candidate),
            pin,
            str(size),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_prepare_does_not_mask_fd_binding_failures() -> None:
    raw = _raw(PREPARE)
    assert not re.search(r"readonly\s+\w+_ID=\"\$\(verify_candidate_fd", raw)
    for name in (
        "BOOTSTRAP_ID",
        "BUILDER_ID",
        "PHASE_A_ID",
        "PHASE_B_ID",
        "BUNDLE_ID",
        "REQUEST_ID",
        "INPUT_SET_ID",
    ):
        assert re.search(
            rf"^{name}=\"\$\(verify_candidate_fd .+\)\" \|\| fail", raw, re.M
        )
    assert "readonly BOOTSTRAP_ID BUILDER_ID PHASE_A_ID" in raw


def test_prepare_uses_checked_traversals_and_safe_signal_traps() -> None:
    raw = _raw(PREPARE)
    assert "trap cleanup EXIT" in raw
    assert "trap 'exit 129' HUP" in raw
    assert "trap 'exit 130' INT" in raw
    assert "trap 'exit 143' TERM" in raw
    assert "done < <(" not in raw
    assert "fresh_list" in raw
    assert "cannot enumerate systemd aliases" in raw
    assert "cannot enumerate systemd dependencies" in raw
    assert "cannot enumerate sync tree" in raw


def test_prepare_hands_internal_lock_to_bootstrap_and_has_no_lifecycle_mutation() -> (
    None
):
    raw = _raw(PREPARE)
    close_at = raw.index("exec {GLOBAL_LOCK_FD}>&-")
    framework_at = raw.index("install-framework \\\n")
    assert close_at < framework_at
    assert "/usr/bin/flock -n 9" in raw
    assert not re.search(r"/usr/bin/flock\s+-n\s+\"?\$\{GLOBAL_LOCK_FD\}", raw)
    assert not re.search(
        r"/usr/bin/systemctl\s+(?:daemon-reload|start|stop|restart|reload|"
        r"reset-failed|enable|disable|mask|unmask|kill)\b",
        raw,
    )


def test_prepare_pins_the_exact_failed_r1_vector() -> None:
    raw = _raw(PREPARE)
    for token in (
        "81d481f1eb764c60a737835b867fcb63",
        "675339972529",
        "675341234136",
        "exit-code|yes|1|2",
        "success|no|0|0|0|0|",
    ):
        assert token in raw
    assert raw.count("assert_r1_manager_vector") >= 3


def test_prepare_empty_manager_properties_fail_closed() -> None:
    prefix = _prefix(PREPARE)
    harness = (
        prefix
        + "\n"
        + """
value="$(property "$1" DropInPaths)"
[[ "$value" == "" ]]
"""
    )
    for document in ("LoadState=loaded\n", "DropInPaths=\nDropInPaths=\n"):
        result = subprocess.run(
            ["/usr/bin/bash", "-c", harness, "fixture", document],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0


def test_prepare_masks_signals_across_no_replace_publication_flag() -> None:
    raw = _raw(PREPARE)
    publish = raw.split('sync_tree "${TRUSTED_STAGING}"', 1)[1].split(
        'assert_absent "${TRUSTED_STAGING}"', 1
    )[0]
    assert "trap '' HUP INT TERM" in publish
    assert (
        '/usr/bin/mv --no-clobber --no-target-directory -- "${TRUSTED_STAGING}"'
        in publish
    )
    assert publish.index("FINAL_R2_PATH_PUBLISHED='true'") > publish.index(
        "/usr/bin/mv --no-clobber"
    )
    assert "trap 'exit 129' HUP" in publish


def test_prepare_cleanup_is_limited_to_locally_owned_paths() -> None:
    raw = _raw(PREPARE)
    cleanup = raw.split("cleanup() {", 1)[1].split("\n}", 1)[0]
    for flag in (
        "OUTER_LOCK_OWNED",
        "TRUSTED_STAGING_OWNED",
        "INPUT_STAGING_OWNED",
    ):
        assert f"${{{flag}}}" in cleanup
        assert f"{flag}='true'" in raw
    assert raw.count("trap '' HUP INT TERM") >= 4


def test_activation_requires_closed_r1_seal_and_exact_sealer() -> None:
    raw = _raw(ACTIVATE)
    for token in (
        "/root/vista-r8-native-builder-r1-failure-seal-b7ead170-83f180e0-20260901c",
        "vista.r8-native-builder-r1-failure-seal/v1",
        "c418918f6907d595895fb8139bae3576741799bc7e789b2b8751ed5a1d1b163d",
        "35026",
        "TRACE_PATH_DRIFT: trace host file[21]",
        "r2_activation_authorized=false",
        "sha256sum -c -- receipt.sha256",
        "r1_seal_tree_digest",
        'assert_file "${R1_SEALER}" 500 0 0',
    ):
        assert token in raw


def test_activation_has_distinct_pre_and_post_reload_gates() -> None:
    raw = _raw(ACTIVATE)
    before, after = raw.split("/usr/bin/systemctl daemon-reload", 1)
    assert "assert_r2_pre_reload_not_found" in before
    assert (
        'assert_r2_never_started "${PHASE_A}"'
        not in before.split("assert_r2_pre_reload_not_found()", 1)[-1]
    )
    assert 'assert_r2_never_started "${PHASE_A}"' in after
    assert raw.count("/usr/bin/systemctl daemon-reload") == 1
    assert "case \"${unit_file_state}\" in '' | static)" in raw


def test_empty_manager_properties_fail_closed_when_missing_or_duplicated(
    tmp_path: Path,
) -> None:
    prefix = _prefix(ACTIVATE)
    property_harness = (
        prefix
        + "\n"
        + """
value="$(property "$1" DropInPaths)"
[[ "$value" == "" ]]
"""
    )
    for document in ("LoadState=loaded\n", "DropInPaths=\nDropInPaths=\n"):
        result = subprocess.run(
            ["/usr/bin/bash", "-c", property_harness, "fixture", document],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0

    fixture = tmp_path / "manager.show"
    file_harness = (
        prefix
        + "\n"
        + """
value="$(file_property "$1" DropInPaths)"
[[ "$value" == "" ]]
"""
    )
    for document in ("LoadState=loaded\n", "DropInPaths=\nDropInPaths=\n"):
        fixture.write_text(document, encoding="utf-8")
        result = subprocess.run(
            ["/usr/bin/bash", "-c", file_harness, "fixture", str(fixture)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0


def test_capture_pair_checks_both_manager_reads() -> None:
    raw = _raw(ACTIVATE)
    body = raw.split("capture_pair() {", 1)[1].split("\n}", 1)[0]
    assert 'first="$(manager_document "$1")" || return 1' in body
    assert 'second="$(manager_document "$2")" || return 1' in body


def test_activation_starts_only_phase_a_once_and_never_resets() -> None:
    raw = _raw(ACTIVATE)
    starts = re.findall(r"/usr/bin/systemctl start[^\n]+", raw)
    assert starts == [
        '/usr/bin/systemctl start --no-ask-password --wait -- "${PHASE_A}"'
    ]
    assert "${PHASE_B}" not in starts[0]
    assert not re.search(
        r"/usr/bin/systemctl\s+(?:stop|restart|reload|reset-failed|enable|"
        r"disable|mask|unmask|kill)\b",
        raw,
    )


def test_activation_r1_unchanged_gate_is_complete_and_stateful() -> None:
    raw = _raw(ACTIVATE)
    gate = raw.split("assert_r1_vector() {", 1)[1].split("\n}", 1)[0]
    for field in (
        "Id",
        "Names",
        "FragmentPath",
        "DropInPaths",
        "WantedBy",
        "RequiredBy",
        "Job",
        "ConditionResult",
    ):
        assert (
            f'property "${{a}}" {field}' in gate or f'property "${{b}}" {field}' in gate
        )
    for token in (
        "R1_STATE_INVENTORY",
        "assert_r1_state_filesystem",
        "assert_r1_state_matches_seal",
        "r1_state_seal_projection",
        "r1_state_current_projection",
        "secure_reexec_with_r1_build_locks",
        "os.O_RDONLY",
        "os.O_NOFOLLOW",
        "os.O_NONBLOCK",
        "fcntl.LOCK_EX | fcntl.LOCK_NB",
        "os.dup2(source, target, inheritable=True)",
        '/usr/bin/flock -n "${R1_PHASE_A_LOCK_FD}"',
        '/usr/bin/flock -n "${R1_PHASE_B_LOCK_FD}"',
        "verify_r1_build_lock_bindings",
        "r1-before-reload-state.txt",
        "r1-after-reload-state.txt",
        "r1-after-start-state.txt",
        "assert_r1_state_matches",
        'cmp -s -- "${RECEIPT_STAGING}/r1-before-reload-state.txt"',
    ):
        assert token in raw
    assert 'assert_closed_file_metadata "${R1_SEAL}/${name}" 444 0 0' in raw
    assert "regular file|444|0|0|1" not in raw
    assert "%F|%a|%u|%g|%h|%s|%d|%i|%y|%z" in raw
    assert "os.O_CREAT" not in raw
    assert not re.search(r"exec[^\n]*<>[^\n]*\.build\.lock", raw)
    assert raw.index(
        "secure_reexec_with_r1_build_locks\nR1_PHASE_A_LOCK_ID"
    ) < raw.index('assert_absent "${RECEIPT_FINAL}"')


def test_activation_defers_signals_and_seals_postcondition_failures() -> None:
    raw = _raw(ACTIVATE)
    mutation = raw.index("MUTATION_BEGUN='true'")
    publish = raw.index('seal_receipt "${OUTCOME}"')
    trap_at = raw.rindex("trap '' HUP INT TERM", 0, mutation)
    critical = raw[trap_at:publish]
    assert trap_at < mutation
    assert "POST_RELOAD_EXIT" in critical
    assert "POST_VALIDATION_EXIT" in critical
    assert "failed-preserved-no-retry" in critical
    assert "post-start-validation.txt" in critical
    assert "not-captured" in raw[:mutation]
    assert "JOURNAL_CAPTURE_EXIT" in critical
    assert "vista.r8-native-builder-phase-a-manifest/v1" in critical
    assert publish < raw.index("VISTA_R8_NATIVE_BUILDER_R2_PHASE_A_FAILED_PRESERVED")


def test_activation_receipt_is_root_only_atomic_and_non_production() -> None:
    raw = _raw(ACTIVATE)
    assert "RECEIPT_FINAL='/root/" in raw
    assert "/usr/bin/mv -T --no-clobber" in raw
    assert "receipt.sha256" in raw
    assert "content_digest=" in raw
    assert "activation-self-pin.sha256" in raw
    assert "activator_sha256=${LIVE_SELF_SHA256}" in raw
    assert "activator_size=${LIVE_SELF_BYTES}" in raw
    assert "network_access=false" in raw
    assert "production_native_output=false" in raw
    assert not re.search(r"(?:curl|wget|scp|rsync|ssh)\s", raw)


def test_activation_holds_and_rebinds_the_global_bootstrap_lock() -> None:
    raw = _raw(ACTIVATE)
    assert 'exec 10<>"${GLOBAL_LOCK}"' in raw
    assert "/usr/bin/flock -n 10" in raw
    assert "another R2 bootstrap or activation holds the global lock" in raw
    assert (
        '"$(/usr/bin/stat -Lc \'%d:%i\' -- /proc/$$/fd/10)" == "${GLOBAL_LOCK_ID}"'
        in raw
    )


def test_activation_pre_mutation_cleanup_removes_only_owned_files() -> None:
    raw = _raw(ACTIVATE)
    cleanup = raw.split("cleanup() {", 1)[1].split("\n}", 1)[0]
    assert "${OUTER_LOCK}/r1-seal-tree.sha256" in cleanup
    assert '/usr/bin/rm -f -- "${OUTER_LOCK}/r1-seal-tree.sha256"' in cleanup
    assert '/usr/bin/rmdir -- "${OUTER_LOCK}"' in cleanup
    assert cleanup.count("rm -f") == 1
    assert "${OUTER_LOCK_OWNED}" in cleanup
    assert "${RECEIPT_STAGING_OWNED}" in cleanup
    assert "OUTER_LOCK_OWNED='true'" in raw
    assert "RECEIPT_STAGING_OWNED='true'" in raw


def test_phase_a_manifest_hash_is_materialized_before_receipt_write() -> None:
    raw = _raw(ACTIVATE)
    assert 'manifest_sha="$(sha256_of "${PHASE_A_FINAL}/manifest.json")" || fail' in raw
    assert '"${manifest_sha}" "${PHASE_A_FINAL}/manifest.json"' in raw


def test_activation_content_digest_hash_loop_is_explicitly_checked() -> None:
    raw = _raw(ACTIVATE)
    assert 'digest_ledger="${RECEIPT_STAGING}/.content-digest-input.sha256"' in raw
    assert 'fail "cannot hash activation receipt input: ${name}"' in raw
    assert 'digest="$(sha256_of "${digest_ledger}")" || fail' in raw
    assert '/usr/bin/rm -f -- "${digest_ledger}" || fail' in raw
    assert "done) | /usr/bin/sha256sum" not in raw
