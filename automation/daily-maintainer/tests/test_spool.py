from __future__ import annotations

import datetime as dt
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vista_daily_maintainer.candidate import (
    Backlog,
    Candidate,
    CandidateSource,
    candidate_authorization_digest,
)
from vista_daily_maintainer.finalizer import (
    build_verification_subject,
    finalize_verification,
)
from vista_daily_maintainer.guard import ChangedFile, GuardReport
from vista_daily_maintainer.patcher import PatcherRequest
from vista_daily_maintainer.spool import (
    MAX_PATCH_BUNDLE_BYTES,
    ImmutableFileSpool,
    PreparedPublisherCheckout,
    PublisherRematerializer,
    PublisherStateStore,
    RematerializationError,
    RematerializationSubject,
    RematerializedPublisherCheckout,
    SealedSpoolRecord,
    SpoolConflictError,
    SpoolContractError,
    SpoolDeploymentError,
    SpoolDeploymentEvidence,
    SpoolError,
    SpoolIncompleteError,
    SpoolIntegrityError,
    SpoolWrite,
)
from vista_daily_maintainer.state import (
    BranchDisposition,
    Lifecycle,
    RunKey,
    RunState,
)
from vista_daily_maintainer.verifier import (
    IsolationEvidence,
    ValidationResult,
    VerificationReport,
    verification_check_subject_digest,
)


BASE_SHA = "a" * 40
BACKLOG_SHA256 = "b" * 64
PATCH_SHA256 = "c" * 64
RUN_DATE = dt.date(2026, 8, 21)
REPOSITORY = "IvesLiu1026/VISTA-World"
SLUG = "spool-contract-test"
SPOOL_ID = "2026-08-21-vw-dm-0001-aaaaaaaaaaaa"

_BIND_MOUNT_PROBE = """
import os
import sys
from pathlib import Path

try:
    from vista_daily_maintainer.spool import (
        SpoolDeploymentError,
        SpoolDeploymentEvidence,
        SpoolSubject,
        _validate_source_outside_deployment,
    )

    publisher_root = Path(sys.argv[1])
    alias_root = Path(sys.argv[2])
    spool_root = Path(sys.argv[3])
    publisher_state_root = Path(sys.argv[4])
    publisher_metadata = publisher_root.stat()
    alias_metadata = alias_root.stat()
    if (publisher_metadata.st_dev, publisher_metadata.st_ino) != (
        alias_metadata.st_dev,
        alias_metadata.st_ino,
    ):
        raise RuntimeError("bind mount did not expose the publisher root identity")
    def attest(state_root):
        return SpoolDeploymentEvidence.attest(
            spool_root=spool_root,
            publisher_root=publisher_root,
            publisher_state_root=state_root,
            control_uid=spool_root.stat().st_uid,
            publisher_uid=publisher_metadata.st_uid,
            patcher_uid=publisher_metadata.st_uid + 1,
            publisher_group_gid=spool_root.stat().st_gid,
            distinct_uids_enforced=False,
            publisher_spool_read_only=False,
            patcher_spool_unmounted=False,
            patcher_publisher_root_unmounted=False,
            patcher_publisher_state_root_unmounted=False,
            publisher_patcher_root_unmounted=False,
            attested_by="bind-mount-namespace-probe",
        )

    try:
        attest(alias_root)
    except SpoolDeploymentError as exc:
        if "inode alias" not in str(exc):
            raise RuntimeError("root alias failed for an unrelated reason") from exc
    else:
        raise RuntimeError("deployment attestation accepted a bind-mounted root alias")
    deployment = attest(publisher_state_root)
    base_sha = "a" * 40
    digest = "b" * 64
    subject = SpoolSubject(
        run_id=f"2026-08-21/IvesLiu1026/VISTA-World@{base_sha}",
        run_date="2026-08-21",
        repository="IvesLiu1026/VISTA-World",
        base_sha=base_sha,
        branch_name="codex/daily/2026-08-21-bind-alias-aaaaaaaa",
        candidate_id="VW-DM-0001",
        candidate_slug="bind-alias",
        candidate_sha256=digest,
        backlog_sha256=digest,
        backlog_authorization_sha256=digest,
        run_state_sha256=digest,
        verification_subject_sha256=digest,
        patch_sha256=digest,
        verified_head_sha256=digest,
        final_envelope_sha256=digest,
        source_worktree_path=str(alias_root / "missing" / "worktree"),
        changed_paths=("tests/test_contract.py",),
    )
except Exception as exc:
    print(f"probe setup failed: {exc!r}", file=sys.stderr)
    raise SystemExit(78) from exc

try:
    _validate_source_outside_deployment(subject, deployment)
except SpoolDeploymentError:
    raise SystemExit(0)
except Exception as exc:
    print(f"probe validation failed: {exc!r}", file=sys.stderr)
    raise SystemExit(78) from exc
raise SystemExit(42)
"""

_NESTED_BIND_MOUNT_PROBE = """
import os
import sys
from pathlib import Path

try:
    from vista_daily_maintainer.spool import (
        SpoolDeploymentError,
        SpoolDeploymentEvidence,
    )

    backing_root = Path(sys.argv[1])
    publisher_state_root = Path(sys.argv[2])
    spool_root = Path(sys.argv[3])
    publisher_root = Path(sys.argv[4])
    if not os.path.samefile(backing_root, publisher_state_root):
        raise RuntimeError("nested bind mount does not alias its backing directory")
    publisher_metadata = publisher_root.stat()
    state_metadata = publisher_state_root.stat()
    if (publisher_metadata.st_dev, publisher_metadata.st_ino) == (
        state_metadata.st_dev,
        state_metadata.st_ino,
    ):
        raise RuntimeError("probe did not preserve distinct root inode identities")
    try:
        SpoolDeploymentEvidence.attest(
            spool_root=spool_root,
            publisher_root=publisher_root,
            publisher_state_root=publisher_state_root,
            control_uid=spool_root.stat().st_uid,
            publisher_uid=publisher_metadata.st_uid,
            patcher_uid=publisher_metadata.st_uid + 1,
            publisher_group_gid=spool_root.stat().st_gid,
            distinct_uids_enforced=False,
            publisher_spool_read_only=False,
            patcher_spool_unmounted=False,
            patcher_publisher_root_unmounted=False,
            patcher_publisher_state_root_unmounted=False,
            publisher_patcher_root_unmounted=False,
            attested_by="nested-bind-provisioning-probe",
        )
    except SpoolDeploymentError as exc:
        if "initially empty" not in str(exc):
            raise RuntimeError("nested bind failed for an unrelated reason") from exc
    else:
        raise SystemExit(42)
except Exception as exc:
    print(f"nested bind probe failed: {exc!r}", file=sys.stderr)
    raise SystemExit(78) from exc
raise SystemExit(0)
"""

_BIND_MOUNT_SHELL = (
    'mount --bind "$1" "$2" || exit 77; '
    '"$3" -c "$4" "$1" "$2" "$5" "$6"; status=$?; '
    'umount "$2" >/dev/null 2>&1 || true; exit "$status"'
)


def tree_snapshot(root: Path) -> tuple[tuple[object, ...], ...]:
    records = []
    for path in sorted(root.iterdir()):
        metadata = path.lstat()
        records.append(
            (
                path.name,
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_uid,
                metadata.st_gid,
                metadata.st_nlink,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return tuple(records)


def captured_inode_alias(
    alias: Path,
    target: Path,
):
    real_lstat = os.lstat
    real_stat = os.stat
    target_link = real_lstat(target)
    target_metadata = real_stat(target)

    def is_alias(value: object) -> bool:
        try:
            return Path(value) == alias  # type: ignore[arg-type]
        except TypeError:
            return False

    def alias_lstat(value, *args, **kwargs):
        if is_alias(value):
            return target_link
        return real_lstat(value, *args, **kwargs)

    def alias_stat(value, *args, **kwargs):
        if is_alias(value):
            return target_metadata
        return real_stat(value, *args, **kwargs)

    return alias_lstat, alias_stat


def finalized_envelope(worktree: Path):
    candidate = Candidate(
        candidate_id="VW-DM-0001",
        title="Cover immutable publisher handoff",
        risk_tier=0,
        allowed_paths=("tests/**",),
        acceptance=("Publisher bytes are rematerialized outside the patcher tree.",),
        validation_profiles=("tools-python-offline",),
        expected_external_side_effects="none",
        source=CandidateSource(
            kind="curated_backlog",
            manifest_revision=7,
            approved_by="IvesLiu1026",
        ),
    )
    backlog = Backlog(
        schema_version="vista.world.daily-maintainer.backlog.v1",
        manifest_revision=7,
        approved_by="IvesLiu1026",
        sha256=BACKLOG_SHA256,
        candidates=(candidate,),
    )
    request = PatcherRequest(
        run_date=RUN_DATE,
        repository=REPOSITORY,
        base_sha=BASE_SHA,
        backlog_sha256=BACKLOG_SHA256,
        manifest_revision=7,
        approved_by="IvesLiu1026",
        candidate=candidate,
        backlog=backlog,
        candidate_slug=SLUG,
        candidate_sha256=candidate_authorization_digest(candidate),
    )
    state = RunState(
        key=RunKey(RUN_DATE.isoformat(), REPOSITORY, BASE_SHA),
        candidate_id=candidate.candidate_id,
        candidate_slug=SLUG,
        backlog_sha256=BACKLOG_SHA256,
        candidate_sha256=request.candidate_sha256,
        remote="origin",
        remote_branch="main",
        branch_name=f"codex/daily/{RUN_DATE.isoformat()}-{SLUG}-{BASE_SHA[:8]}",
        lifecycle=Lifecycle.WORKTREE_READY,
        branch_disposition=BranchDisposition.CREATED,
        branch_head_sha=BASE_SHA,
        worktree_path=str(worktree),
        observed_remote_sha=BASE_SHA,
    )
    guard = GuardReport(
        base_sha=BASE_SHA,
        patch_sha256=PATCH_SHA256,
        changed_files=(
            ChangedFile(
                path="tests/test_contract.py",
                status="M",
                additions=5,
                deletions=0,
                is_test=True,
            ),
        ),
        violations=(),
        production_files=0,
        production_lines=0,
        test_files=1,
        test_lines=5,
    )
    subject = build_verification_subject(request, state)
    check_subject = verification_check_subject_digest(
        subject.sha256, guard.patch_sha256
    )
    report = VerificationReport(
        subject=subject,
        check_subject_sha256=check_subject,
        candidate_sha256=request.candidate_sha256,
        guard=guard,
        final_guard=guard,
        validation=(
            ValidationResult("git-diff-check", 0, "d" * 64, 10, check_subject),
            ValidationResult("tools-python-offline", 0, "e" * 64, 20, check_subject),
        ),
        isolation_evidence=IsolationEvidence.attest(
            subject.sha256,
            PATCH_SHA256,
            observed_by="outer-sandbox-controller",
        ),
    )
    return finalize_verification(request, state, report)


class ReadOnlySpoolProbe:
    def __init__(self, spool: ImmutableFileSpool) -> None:
        self.deployment = spool.deployment
        self._spool = spool
        self.read_count = 0
        self.write_attempts = 0

    def read(self, spool_id: str):
        self.read_count += 1
        return self._spool.read(spool_id)

    def claim(self, *_args) -> None:
        self.write_attempts += 1
        raise AssertionError("publisher attempted to write the inbound spool")

    def record_materialization(self, *_args) -> None:
        self.write_attempts += 1
        raise AssertionError("publisher attempted to write the inbound spool")

    def put(self, *_args) -> None:
        self.write_attempts += 1
        raise AssertionError("publisher attempted to write the inbound spool")

    def reserve(self, *_args) -> None:
        self.write_attempts += 1
        raise AssertionError("publisher attempted to write the inbound spool")

    def seal(self, *_args) -> None:
        self.write_attempts += 1
        raise AssertionError("publisher attempted to write the inbound spool")


class StaticReadOnlySpool:
    def __init__(self, deployment, record: SealedSpoolRecord) -> None:
        self.deployment = deployment
        self.record = record
        self.read_count = 0

    def read(self, _spool_id: str) -> SealedSpoolRecord:
        self.read_count += 1
        return self.record


class FakeCheckoutPort:
    def __init__(self) -> None:
        self.apply_count = 0
        self.prepare_count = 0
        self.prepared_path: Path | None = None
        self.inspection_subject_override: RematerializationSubject | None = None
        self.use_source_worktree = False

    def prepare_base(
        self,
        subject: RematerializationSubject,
        publisher_root: Path,
    ) -> PreparedPublisherCheckout:
        self.prepare_count += 1
        target = (
            Path(subject.source_worktree_path)
            if self.use_source_worktree
            else publisher_root / f"checkout-{subject.spool_id}"
        )
        if not target.exists():
            target.mkdir(mode=0o700)
        os.chmod(target, 0o700)
        self.prepared_path = target
        return PreparedPublisherCheckout.attest(
            target,
            subject,
            observed_by="fake-publisher-git-adapter",
        )

    def apply_patch_bundle(
        self,
        checkout: PreparedPublisherCheckout,
        patch_bundle: bytes,
        subject: RematerializationSubject,
    ) -> None:
        self.apply_count += 1
        target = Path(checkout.path) / "applied.patch"
        target.write_bytes(patch_bundle)
        os.chmod(target, 0o600)

    def inspect(
        self,
        path: Path,
        subject: RematerializationSubject,
    ) -> RematerializedPublisherCheckout:
        observed_subject = self.inspection_subject_override or subject
        return RematerializedPublisherCheckout.attest(
            path,
            observed_subject,
            observed_by="fake-publisher-git-adapter",
        )


class SpoolFixture:
    def __init__(self, root: Path, *, source_worktree: Path | None = None) -> None:
        self.root = root
        self.spool_root = root / "control-spool"
        self.publisher_root = root / "publisher-checkouts"
        self.publisher_state_root = root / "publisher-state"
        self.patcher_root = root / "patcher-worktree"
        self.spool_root.mkdir(mode=0o750)
        self.publisher_root.mkdir(mode=0o700)
        self.publisher_state_root.mkdir(mode=0o700)
        self.patcher_root.mkdir(mode=0o700)
        os.chmod(self.spool_root, 0o750)
        os.chmod(self.publisher_root, 0o700)
        os.chmod(self.publisher_state_root, 0o700)
        os.chmod(self.patcher_root, 0o700)
        self.deployment = SpoolDeploymentEvidence.attest(
            spool_root=self.spool_root,
            publisher_root=self.publisher_root,
            publisher_state_root=self.publisher_state_root,
            control_uid=os.getuid(),
            publisher_uid=os.getuid(),
            patcher_uid=os.getuid() + 1,
            publisher_group_gid=os.getgid(),
            distinct_uids_enforced=False,
            publisher_spool_read_only=False,
            patcher_spool_unmounted=False,
            patcher_publisher_root_unmounted=False,
            patcher_publisher_state_root_unmounted=False,
            publisher_patcher_root_unmounted=False,
            attested_by="unit-test-control-plane",
        )
        self.spool = ImmutableFileSpool(self.deployment)
        self.publisher_state = PublisherStateStore(self.deployment)
        self.envelope = finalized_envelope(source_worktree or self.patcher_root)
        self.patch_bundle = b"vista-portable-patch-bundle-v1\nopaque verified bytes\n"
        self.write = SpoolWrite.from_finalized(
            spool_id=SPOOL_ID,
            envelope=self.envelope,
            patch_bundle=self.patch_bundle,
        )

    def artifact(self, suffix: str, spool_id: str = SPOOL_ID) -> Path:
        return self.spool_root / f"{spool_id}.{suffix}"


class ImmutableSpoolTests(unittest.TestCase):
    def test_stable_manifest_atomic_modes_and_idempotent_replay(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))

            first = fixture.spool.put(fixture.write)
            second = fixture.spool.put(fixture.write)

            self.assertEqual(first, second)
            self.assertEqual(first.manifest.subject.patch_sha256, PATCH_SHA256)
            self.assertEqual(
                first.manifest.subject.final_envelope_sha256,
                fixture.envelope.sha256,
            )
            self.assertEqual(first.patch_bundle, fixture.patch_bundle)
            self.assertEqual(
                first.manifest.canonical_bytes, second.manifest.canonical_bytes
            )
            for path in fixture.spool_root.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o440)
                self.assertEqual(path.stat().st_nlink, 1)

    def test_invalid_id_traversal_and_preexisting_symlink_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            with self.assertRaisesRegex(SpoolContractError, "spool ID"):
                SpoolWrite.from_finalized(
                    spool_id="../escape",
                    envelope=fixture.envelope,
                    patch_bundle=fixture.patch_bundle,
                )

            outside = fixture.root / "outside"
            outside.write_text("unchanged", encoding="utf-8")
            fixture.artifact("reserved.json").symlink_to(outside)
            with self.assertRaises(SpoolConflictError):
                fixture.spool.reserve(fixture.write)
            self.assertEqual(outside.read_text(encoding="utf-8"), "unchanged")

    def test_symlink_hardlink_and_content_tampering_are_detected(self) -> None:
        cases = ("symlink", "hardlink", "fifo", "content")
        for case in cases:
            with self.subTest(case=case), TemporaryDirectory() as directory:
                fixture = SpoolFixture(Path(directory))
                fixture.spool.put(fixture.write)
                patch = fixture.artifact("patch.bundle")
                if case == "symlink":
                    payload = patch.read_bytes()
                    patch.unlink()
                    target = fixture.root / "replacement"
                    target.write_bytes(payload)
                    patch.symlink_to(target)
                elif case == "hardlink":
                    os.link(patch, fixture.root / "outside-hardlink")
                elif case == "fifo":
                    patch.unlink()
                    os.mkfifo(patch, 0o440)
                else:
                    os.chmod(patch, 0o640)
                    patch.write_bytes(b"x" * len(fixture.patch_bundle))
                    os.chmod(patch, 0o440)
                with self.assertRaises(SpoolError):
                    fixture.spool.read(SPOOL_ID)

    def test_cross_entry_file_swap_is_rejected_by_inode_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            first = fixture.spool.put(fixture.write)
            second_write = SpoolWrite.from_finalized(
                spool_id="second-entry",
                envelope=fixture.envelope,
                patch_bundle=fixture.patch_bundle,
            )
            fixture.spool.put(second_write)
            os.replace(
                fixture.artifact("patch.bundle", "second-entry"),
                fixture.artifact("patch.bundle"),
            )
            with self.assertRaisesRegex(SpoolIntegrityError, "inode"):
                fixture.spool.read(first.manifest.spool_id)

    def test_partial_reservation_is_never_treated_as_sealed(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            fixture.spool.reserve(fixture.write)
            with self.assertRaises(SpoolIncompleteError):
                fixture.spool.read(SPOOL_ID)
            with self.assertRaises(SpoolConflictError):
                fixture.spool.reserve(fixture.write)

    def test_source_worktree_cannot_overlap_any_deployment_root(self) -> None:
        root_names = ("spool_root", "publisher_root", "publisher_state_root")
        for root_name in root_names:
            with self.subTest(root=root_name), TemporaryDirectory() as directory:
                fixture = SpoolFixture(Path(directory))
                source = getattr(fixture, root_name) / "nested-patcher-worktree"
                write = SpoolWrite.from_finalized(
                    spool_id=SPOOL_ID,
                    envelope=finalized_envelope(source),
                    patch_bundle=fixture.patch_bundle,
                )
                with self.assertRaisesRegex(SpoolDeploymentError, "overlaps"):
                    fixture.spool.put(write)
                self.assertEqual(list(fixture.spool_root.iterdir()), [])
                self.assertEqual(list(fixture.publisher_state_root.iterdir()), [])

        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            alias = fixture.root / "publisher-root-alias"
            alias.symlink_to(fixture.publisher_root, target_is_directory=True)
            write = SpoolWrite.from_finalized(
                spool_id=SPOOL_ID,
                envelope=finalized_envelope(alias / "nested-patcher-worktree"),
                patch_bundle=fixture.patch_bundle,
            )
            with self.assertRaisesRegex(SpoolDeploymentError, "overlaps"):
                fixture.spool.put(write)
            self.assertEqual(list(fixture.spool_root.iterdir()), [])

    def test_source_existing_ancestor_inode_alias_fails_before_spool_write(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            alias = fixture.root / "captured-bind-alias"
            alias.mkdir(mode=0o700)
            write = SpoolWrite.from_finalized(
                spool_id=SPOOL_ID,
                envelope=finalized_envelope(alias / "missing" / "worktree"),
                patch_bundle=fixture.patch_bundle,
            )
            alias_lstat, alias_stat = captured_inode_alias(
                alias, fixture.publisher_root
            )

            with (
                patch(
                    "vista_daily_maintainer.spool.os.lstat",
                    side_effect=alias_lstat,
                ),
                patch(
                    "vista_daily_maintainer.spool.os.stat",
                    side_effect=alias_stat,
                ),
                self.assertRaisesRegex(SpoolDeploymentError, "aliases"),
            ):
                fixture.spool.put(write)

            self.assertEqual(list(fixture.spool_root.iterdir()), [])
            self.assertEqual(list(fixture.publisher_state_root.iterdir()), [])

    def test_unmounted_nonexistent_source_leaf_remains_valid(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            source = fixture.root / "unmounted-patcher" / "missing-worktree"
            self.assertFalse(source.exists())
            write = SpoolWrite.from_finalized(
                spool_id=SPOOL_ID,
                envelope=finalized_envelope(source),
                patch_bundle=fixture.patch_bundle,
            )

            record = fixture.spool.put(write)

            self.assertEqual(record.manifest.subject.source_worktree_path, str(source))

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux mount namespaces")
    def test_linux_bind_mount_alias_is_rejected_when_namespace_is_available(
        self,
    ) -> None:
        required = ("unshare", "mount", "umount")
        if any(shutil.which(command) is None for command in required):
            self.skipTest("Linux unshare/mount tools are unavailable")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool_root = root / "spool"
            publisher_root = root / "publisher"
            publisher_state_root = root / "publisher-state"
            alias_root = root / "bind-alias"
            spool_root.mkdir(mode=0o750)
            publisher_root.mkdir(mode=0o700)
            publisher_state_root.mkdir(mode=0o700)
            alias_root.mkdir(mode=0o700)
            os.chmod(spool_root, 0o750)
            os.chmod(publisher_root, 0o700)
            os.chmod(publisher_state_root, 0o700)
            os.chmod(alias_root, 0o700)

            completed = subprocess.run(
                (
                    "unshare",
                    "--user",
                    "--map-root-user",
                    "--mount",
                    "--fork",
                    "sh",
                    "-c",
                    _BIND_MOUNT_SHELL,
                    "bind-mount-probe",
                    str(publisher_root),
                    str(alias_root),
                    sys.executable,
                    _BIND_MOUNT_PROBE,
                    str(spool_root),
                    str(publisher_state_root),
                ),
                capture_output=True,
                check=False,
                text=True,
                timeout=20,
            )

        diagnostic = (completed.stdout + completed.stderr).strip()
        if completed.returncode in {1, 77}:
            self.skipTest(
                "Linux user/mount namespace unavailable"
                + (f": {diagnostic}" if diagnostic else "")
            )
        self.assertEqual(
            completed.returncode,
            0,
            "bind-mount alias bypassed or probe failed: " + diagnostic,
        )

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux mount namespaces")
    def test_linux_nested_bind_backing_fails_empty_root_provisioning(self) -> None:
        required = ("unshare", "mount", "umount")
        if any(shutil.which(command) is None for command in required):
            self.skipTest("Linux unshare/mount tools are unavailable")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool_root = root / "spool"
            publisher_root = root / "publisher"
            backing_root = publisher_root / "state-backing"
            publisher_state_root = root / "publisher-state"
            spool_root.mkdir(mode=0o750)
            publisher_root.mkdir(mode=0o700)
            backing_root.mkdir(mode=0o700)
            publisher_state_root.mkdir(mode=0o700)
            os.chmod(spool_root, 0o750)
            os.chmod(publisher_root, 0o700)
            os.chmod(backing_root, 0o700)
            os.chmod(publisher_state_root, 0o700)

            completed = subprocess.run(
                (
                    "unshare",
                    "--user",
                    "--map-root-user",
                    "--mount",
                    "--fork",
                    "sh",
                    "-c",
                    _BIND_MOUNT_SHELL,
                    "nested-bind-probe",
                    str(backing_root),
                    str(publisher_state_root),
                    sys.executable,
                    _NESTED_BIND_MOUNT_PROBE,
                    str(spool_root),
                    str(publisher_root),
                ),
                capture_output=True,
                check=False,
                text=True,
                timeout=20,
            )

            diagnostic = (completed.stdout + completed.stderr).strip()
            if completed.returncode in {1, 77}:
                self.skipTest(
                    "Linux user/mount namespace unavailable"
                    + (f": {diagnostic}" if diagnostic else "")
                )
            self.assertEqual(
                completed.returncode,
                0,
                "nested bind bypassed provisioning: " + diagnostic,
            )
            self.assertEqual(list(spool_root.iterdir()), [])
            self.assertEqual(
                [path.name for path in publisher_root.iterdir()], ["state-backing"]
            )
            self.assertEqual(list(backing_root.iterdir()), [])
            self.assertEqual(list(publisher_state_root.iterdir()), [])

    def test_concurrent_reserve_has_one_exclusive_winner(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            barrier = threading.Barrier(6)
            outcomes: list[str] = []
            lock = threading.Lock()

            def attempt() -> None:
                barrier.wait()
                try:
                    fixture.spool.reserve(fixture.write)
                    result = "reserved"
                except SpoolConflictError:
                    result = "conflict"
                with lock:
                    outcomes.append(result)

            threads = [threading.Thread(target=attempt) for _ in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(outcomes.count("reserved"), 1)
            self.assertEqual(outcomes.count("conflict"), 5)

    def test_digest_mismatch_and_oversized_bundle_fail_before_write(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            with self.assertRaisesRegex(SpoolContractError, "oversized"):
                SpoolWrite.from_finalized(
                    spool_id=SPOOL_ID,
                    envelope=fixture.envelope,
                    patch_bundle=b"x" * (MAX_PATCH_BUNDLE_BYTES + 1),
                )
            self.assertEqual(list(fixture.spool_root.iterdir()), [])

    def test_mutated_finalizer_objects_are_fully_reconstructed_before_write(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            mutations = (
                ("checks", ()),
                ("backlog_candidate_bindings", ()),
                ("isolation_subject_sha256", "f" * 64),
                ("run_remote", "upstream"),
            )
            for field, replacement in mutations:
                with self.subTest(field=field):
                    mutated = replace(fixture.envelope)
                    object.__setattr__(mutated, field, replacement)
                    mutated_bytes = mutated.canonical_bytes
                    self.assertEqual(
                        mutated.sha256,
                        hashlib.sha256(mutated_bytes).hexdigest(),
                    )
                    with self.assertRaises(SpoolContractError):
                        SpoolWrite.from_finalized(
                            spool_id=SPOOL_ID,
                            envelope=mutated,
                            patch_bundle=fixture.patch_bundle,
                        )
            self.assertEqual(list(fixture.spool_root.iterdir()), [])

    def test_unsafe_root_mode_and_owner_contract_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            fixture.spool.put(fixture.write)
            os.chmod(fixture.spool_root, 0o770)
            with self.assertRaises(SpoolDeploymentError):
                fixture.spool.read(SPOOL_ID)

        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            record = fixture.spool.put(fixture.write)
            os.chmod(fixture.publisher_state_root, 0o770)
            with self.assertRaisesRegex(SpoolDeploymentError, "publisher state root"):
                fixture.publisher_state.claim(record)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool_root = root / "spool"
            publisher_root = root / "publisher"
            publisher_state_root = root / "publisher-state"
            spool_root.mkdir(mode=0o750)
            publisher_root.mkdir(mode=0o700)
            publisher_state_root.mkdir(mode=0o700)
            os.chmod(spool_root, 0o750)
            os.chmod(publisher_root, 0o700)
            os.chmod(publisher_state_root, 0o700)
            with self.assertRaisesRegex(SpoolDeploymentError, "publisher-owned"):
                SpoolDeploymentEvidence.attest(
                    spool_root=spool_root,
                    publisher_root=publisher_root,
                    publisher_state_root=publisher_state_root,
                    control_uid=os.getuid(),
                    publisher_uid=os.getuid() + 1,
                    patcher_uid=os.getuid() + 2,
                    publisher_group_gid=os.getgid(),
                    distinct_uids_enforced=True,
                    publisher_spool_read_only=True,
                    patcher_spool_unmounted=True,
                    patcher_publisher_root_unmounted=True,
                    patcher_publisher_state_root_unmounted=True,
                    publisher_patcher_root_unmounted=True,
                    attested_by="unit-test-control-plane",
                )

    def test_deployment_root_inode_aliases_are_rejected_for_every_pair(self) -> None:
        pairs = (
            ("publisher_root", "spool_root"),
            ("publisher_state_root", "spool_root"),
            ("publisher_state_root", "publisher_root"),
        )
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            for target_name, source_name in pairs:
                with self.subTest(target=target_name, source=source_name):
                    target = getattr(fixture.deployment, target_name)
                    source = getattr(fixture.deployment, source_name)
                    aliased = replace(
                        target,
                        device=source.device,
                        inode=source.inode,
                    )
                    with self.assertRaisesRegex(SpoolDeploymentError, "inode alias"):
                        replace(fixture.deployment, **{target_name: aliased})

    def test_deployment_attestation_requires_every_root_initially_empty(self) -> None:
        root_names = ("spool_root", "publisher_root", "publisher_state_root")
        for root_name in root_names:
            with self.subTest(root=root_name), TemporaryDirectory() as directory:
                root = Path(directory)
                roots = {
                    "spool_root": root / "spool",
                    "publisher_root": root / "publisher",
                    "publisher_state_root": root / "publisher-state",
                }
                roots["spool_root"].mkdir(mode=0o750)
                roots["publisher_root"].mkdir(mode=0o700)
                roots["publisher_state_root"].mkdir(mode=0o700)
                os.chmod(roots["spool_root"], 0o750)
                os.chmod(roots["publisher_root"], 0o700)
                os.chmod(roots["publisher_state_root"], 0o700)
                occupied = roots[root_name] / "preexisting-entry"
                occupied.mkdir(mode=0o700)

                with self.assertRaisesRegex(
                    SpoolDeploymentError, "not initially empty"
                ):
                    SpoolDeploymentEvidence.attest(
                        spool_root=roots["spool_root"],
                        publisher_root=roots["publisher_root"],
                        publisher_state_root=roots["publisher_state_root"],
                        control_uid=os.getuid(),
                        publisher_uid=os.getuid(),
                        patcher_uid=os.getuid() + 1,
                        publisher_group_gid=os.getgid(),
                        distinct_uids_enforced=False,
                        publisher_spool_read_only=False,
                        patcher_spool_unmounted=False,
                        patcher_publisher_root_unmounted=False,
                        patcher_publisher_state_root_unmounted=False,
                        publisher_patcher_root_unmounted=False,
                        attested_by="unit-test-control-plane",
                    )

                self.assertTrue(occupied.is_dir())
                self.assertEqual(list(occupied.iterdir()), [])

    def test_initial_empty_fact_is_required_and_gates_unattended_use(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            self.assertTrue(fixture.deployment.roots_initially_empty)
            mutated = replace(fixture.deployment)
            object.__setattr__(mutated, "roots_initially_empty", False)
            self.assertFalse(mutated.unattended_ready)
            with self.assertRaisesRegex(SpoolDeploymentError, "not proven"):
                replace(fixture.deployment, roots_initially_empty=False)

    def test_unattended_activation_stays_dormant_without_t13_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            self.assertFalse(fixture.deployment.unattended_ready)
            with self.assertRaisesRegex(SpoolDeploymentError, "dormant"):
                fixture.deployment.require_unattended_ready()
            with self.assertRaisesRegex(SpoolDeploymentError, "dormant"):
                PublisherRematerializer(
                    spool=fixture.spool,
                    state_store=fixture.publisher_state,
                    checkout_port=FakeCheckoutPort(),
                    unattended=True,
                )
            self.assertEqual(list(fixture.publisher_root.iterdir()), [])


class RematerializationTests(unittest.TestCase):
    def test_source_nested_under_publisher_root_fails_before_prepare(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "source-deployment"
            target_root = root / "target-deployment"
            source_root.mkdir()
            target_root.mkdir()
            target = SpoolFixture(target_root)
            source = SpoolFixture(
                source_root,
                source_worktree=(target.publisher_root / "patcher-worktree"),
            )
            source_record = source.spool.put(source.write)
            rebound_manifest = replace(
                source_record.manifest,
                deployment_evidence_sha256=target.deployment.evidence_sha256,
            )
            rebound_record = SealedSpoolRecord(
                rebound_manifest,
                source_record.envelope_bytes,
                source_record.patch_bundle,
            )
            reader = StaticReadOnlySpool(target.deployment, rebound_record)
            port = FakeCheckoutPort()
            rematerializer = PublisherRematerializer(
                spool=reader,
                state_store=target.publisher_state,
                checkout_port=port,
                unattended=False,
            )

            with self.assertRaisesRegex(SpoolDeploymentError, "overlaps"):
                rematerializer.rematerialize(SPOOL_ID)

            self.assertEqual(port.prepare_count, 0)
            self.assertEqual(list(target.publisher_root.iterdir()), [])
            self.assertEqual(list(target.publisher_state_root.iterdir()), [])
            self.assertEqual(list(target.spool_root.iterdir()), [])

    def test_source_ancestor_inode_alias_fails_before_claim_or_prepare(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "source-deployment"
            target_root = root / "target-deployment"
            alias = root / "captured-bind-alias"
            source_root.mkdir()
            target_root.mkdir()
            alias.mkdir(mode=0o700)
            target = SpoolFixture(target_root)
            source = SpoolFixture(
                source_root,
                source_worktree=(alias / "missing" / "worktree"),
            )
            source_record = source.spool.put(source.write)
            rebound_record = SealedSpoolRecord(
                replace(
                    source_record.manifest,
                    deployment_evidence_sha256=target.deployment.evidence_sha256,
                ),
                source_record.envelope_bytes,
                source_record.patch_bundle,
            )
            reader = StaticReadOnlySpool(target.deployment, rebound_record)
            port = FakeCheckoutPort()
            rematerializer = PublisherRematerializer(
                spool=reader,
                state_store=target.publisher_state,
                checkout_port=port,
                unattended=False,
            )
            alias_lstat, alias_stat = captured_inode_alias(alias, target.publisher_root)

            with (
                patch(
                    "vista_daily_maintainer.spool.os.lstat",
                    side_effect=alias_lstat,
                ),
                patch(
                    "vista_daily_maintainer.spool.os.stat",
                    side_effect=alias_stat,
                ),
                self.assertRaisesRegex(SpoolDeploymentError, "aliases"),
            ):
                rematerializer.rematerialize(SPOOL_ID)

            self.assertEqual(port.prepare_count, 0)
            self.assertEqual(list(target.publisher_root.iterdir()), [])
            self.assertEqual(list(target.publisher_state_root.iterdir()), [])
            self.assertEqual(list(target.spool_root.iterdir()), [])

    def test_read_only_spool_is_unchanged_and_replay_is_idempotent(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            record = fixture.spool.put(fixture.write)
            inbound_before = tree_snapshot(fixture.spool_root)
            read_only_spool = ReadOnlySpoolProbe(fixture.spool)
            port = FakeCheckoutPort()
            rematerializer = PublisherRematerializer(
                spool=read_only_spool,
                state_store=fixture.publisher_state,
                checkout_port=port,
                unattended=False,
            )

            first = rematerializer.rematerialize(SPOOL_ID)
            second = rematerializer.rematerialize(SPOOL_ID)

            self.assertEqual(first, second)
            self.assertEqual(port.apply_count, 1)
            self.assertGreater(read_only_spool.read_count, 1)
            self.assertEqual(read_only_spool.write_attempts, 0)
            self.assertEqual(tree_snapshot(fixture.spool_root), inbound_before)
            self.assertEqual(
                sorted(path.name for path in fixture.publisher_state_root.iterdir()),
                [
                    f"{SPOOL_ID}.claimed.json",
                    f"{SPOOL_ID}.materialized.json",
                ],
            )
            for path in fixture.publisher_state_root.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o400)
                self.assertEqual(path.stat().st_nlink, 1)
            self.assertNotEqual(Path(first.path), fixture.patcher_root)
            self.assertTrue(Path(first.path).is_relative_to(fixture.publisher_root))
            self.assertEqual(first.patch_sha256, PATCH_SHA256)
            self.assertEqual(first.final_envelope_sha256, fixture.envelope.sha256)
            self.assertEqual(
                Path(first.path, "applied.patch").read_bytes(), fixture.patch_bundle
            )
            other = fixture.publisher_root / "other-checkout"
            other.mkdir(mode=0o700)
            replacement = RematerializedPublisherCheckout.attest(
                other,
                RematerializationSubject.from_record(record),
                observed_by="fake-publisher-git-adapter",
            )
            with self.assertRaisesRegex(SpoolConflictError, "replay changed"):
                fixture.publisher_state.record_materialization(record, replacement)

    def test_subject_digest_swap_from_checkout_inspection_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            record = fixture.spool.put(fixture.write)
            subject = RematerializationSubject.from_record(record)
            port = FakeCheckoutPort()
            port.inspection_subject_override = replace(
                subject,
                candidate_sha256="f" * 64,
            )
            rematerializer = PublisherRematerializer(
                spool=fixture.spool,
                state_store=fixture.publisher_state,
                checkout_port=port,
                unattended=False,
            )
            with self.assertRaisesRegex(RematerializationError, "authority"):
                rematerializer.rematerialize(SPOOL_ID)

    def test_adapter_cannot_return_the_mutable_patcher_worktree(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = SpoolFixture(Path(directory))
            fixture.spool.put(fixture.write)
            port = FakeCheckoutPort()
            port.use_source_worktree = True
            rematerializer = PublisherRematerializer(
                spool=fixture.spool,
                state_store=fixture.publisher_state,
                checkout_port=port,
                unattended=False,
            )
            with self.assertRaisesRegex(
                RematerializationError, "escaped|shares patcher"
            ):
                rematerializer.rematerialize(SPOOL_ID)


if __name__ == "__main__":
    unittest.main()
