from __future__ import annotations

import dataclasses
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from vista_daily_maintainer.finalizer import verified_head_digest
from vista_daily_maintainer.git_adapter import (
    CANONICAL_REMOTE_URL,
    AuthenticatedPatchBundle,
    GitAdapterContractError,
    GitAdapterLimits,
    GitAdapterOperationError,
    GitAdapterRepositoryError,
    GitExecutableEvidence,
    HttpsCredentialPortRequiredError,
    PatchMaterializationSubject,
    ShellFreeGitPublisherAdapter,
)
from vista_daily_maintainer.naming import v1_daily_branch_name
from vista_daily_maintainer.publisher import (
    AUTOMATION_TRAILER,
    CANONICAL_REPOSITORY,
    CommitSpec,
    GitIdentity,
    IVES_AUTHOR,
    PushSpec,
)


COMMITTER = GitIdentity(
    "VISTA World Publisher",
    "publisher@users.noreply.github.com",
)
COMMIT_MESSAGE = (
    f"chore: address VW-DM-0001\n\nCandidate: VW-DM-0001\n\n{AUTOMATION_TRAILER}\n"
)


def run_git(
    cwd: Path,
    *args: str,
    input_bytes: bytes | None = None,
    check: bool = True,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ("git", *args),
        cwd=cwd,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=environment,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"test fixture Git command failed: {args!r}, status={result.returncode}"
        )
    return result


def git_text(cwd: Path, *args: str) -> str:
    return run_git(cwd, *args).stdout.decode("utf-8", "strict").strip()


class RepositoryFixture:
    def __init__(
        self,
        root: Path,
        git_evidence: GitExecutableEvidence,
        *,
        limits: GitAdapterLimits | None = None,
    ) -> None:
        self.root = root
        self.git_evidence = git_evidence
        self.seed = root / "seed"
        self.remote = root / "remote.git"
        self.patcher = root / "patcher"
        self.checkout = root / "publisher"

        self.seed.mkdir()
        run_git(self.seed, "init", "-q", "--initial-branch=main")
        run_git(self.seed, "config", "user.name", "Fixture Author")
        run_git(
            self.seed,
            "config",
            "user.email",
            "fixture-author@example.invalid",
        )
        (self.seed / "src").mkdir()
        (self.seed / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.seed / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
        (self.seed / "large.txt").write_text("x" * 8192, encoding="utf-8")
        run_git(self.seed, "add", "--all")
        run_git(self.seed, "commit", "-qm", "test: initial fixture")
        self.base_sha = git_text(self.seed, "rev-parse", "HEAD")

        self.remote.mkdir()
        run_git(
            self.remote,
            "init",
            "-q",
            "--bare",
            "--initial-branch=main",
        )
        self.remote_url = self.remote.as_uri()
        run_git(self.seed, "remote", "add", "origin", self.remote_url)
        run_git(self.seed, "push", "-q", "origin", "main")

        run_git(
            self.root,
            "clone",
            "-q",
            "--no-checkout",
            self.remote_url,
            str(self.checkout),
        )
        run_git(self.checkout, "checkout", "-q", "--detach", self.base_sha)
        run_git(self.checkout, "config", "--unset-all", "branch.main.remote")
        run_git(self.checkout, "config", "--unset-all", "branch.main.merge")
        run_git(
            self.root,
            "clone",
            "-q",
            self.remote_url,
            str(self.patcher),
        )
        (self.patcher / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.patcher / "tests").mkdir()
        (self.patcher / "tests" / "test_app.py").write_text(
            "def test_value():\n    assert 2 == 2\n",
            encoding="utf-8",
        )
        run_git(self.patcher, "add", "--intent-to-add", "tests/test_app.py")
        self.patch_bytes = run_git(
            self.patcher,
            "diff",
            "--binary",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            self.base_sha,
            "--",
        ).stdout
        self.changed_paths = ("src/app.py", "tests/test_app.py")
        self.branch = v1_daily_branch_name(
            "2026-08-21",
            "git-adapter-contract",
            self.base_sha,
        )
        self.patch_sha256 = hashlib.sha256(b"verified guard patch").hexdigest()
        self.bundle = self.make_bundle(
            patch_bytes=self.patch_bytes,
            changed_paths=self.changed_paths,
        )
        self.adapter = ShellFreeGitPublisherAdapter.for_local_bare_test(
            checkout=self.checkout,
            bare_remote=self.remote,
            patch_bundle=self.bundle,
            git_executable=self.git_evidence,
            limits=limits,
        )

    def make_bundle(
        self,
        *,
        patch_bytes: bytes,
        changed_paths: tuple[str, ...],
        finalized_envelope_sha256: str | None = None,
    ) -> AuthenticatedPatchBundle:
        head_sha256 = verified_head_digest(
            self.base_sha,
            self.patch_sha256,
            changed_paths,
        )
        subject = PatchMaterializationSubject(
            finalized_envelope_sha256=(
                finalized_envelope_sha256
                or hashlib.sha256(b"finalized envelope").hexdigest()
            ),
            repository=CANONICAL_REPOSITORY,
            base_sha=self.base_sha,
            branch=self.branch,
            publisher_checkout=str(self.checkout),
            patch_sha256=self.patch_sha256,
            head_sha256=head_sha256,
            changed_paths=changed_paths,
        )
        return AuthenticatedPatchBundle.from_trusted_spool(
            spool_id="run-patch",
            issued_by="root-spool",
            subject=subject,
            patch_bytes=patch_bytes,
        )

    @property
    def commit_spec(self) -> CommitSpec:
        return CommitSpec(
            paths=self.changed_paths,
            message=COMMIT_MESSAGE,
            author=IVES_AUTHOR,
            committer=COMMITTER,
        )

    def materialize_commit(self) -> str:
        snapshot = self.adapter.inspect_patch(self.checkout, self.base_sha)
        if snapshot.patch_sha256 != self.patch_sha256:
            raise AssertionError("fixture adapter returned another patch")
        self.adapter.create_branch(self.checkout, self.branch, self.base_sha)
        self.adapter.commit(self.checkout, self.commit_spec)
        return git_text(self.checkout, "rev-parse", "HEAD")

    def push_spec(self, head_sha: str) -> PushSpec:
        return PushSpec(
            repository=CANONICAL_REPOSITORY,
            branch=self.branch,
            head_sha=head_sha,
            expected_main_sha=self.base_sha,
        )


class GitPublisherAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.git_evidence = GitExecutableEvidence.capture()

    def fixture(
        self,
        temporary: str,
        *,
        limits: GitAdapterLimits | None = None,
    ) -> RepositoryFixture:
        return RepositoryFixture(Path(temporary), self.git_evidence, limits=limits)

    def test_local_bare_round_trip_reads_commit_tree_and_remote_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            snapshot = fixture.adapter.inspect_patch(fixture.checkout, fixture.base_sha)
            self.assertEqual(snapshot.base_sha, fixture.base_sha)
            self.assertEqual(snapshot.changed_paths, fixture.changed_paths)
            self.assertEqual(snapshot.patch_sha256, fixture.patch_sha256)
            self.assertEqual(snapshot.head_sha256, fixture.bundle.subject.head_sha256)
            self.assertIsNone(
                fixture.adapter.read_local_branch(fixture.checkout, fixture.branch)
            )

            fixture.adapter.create_branch(
                fixture.checkout, fixture.branch, fixture.base_sha
            )
            fixture.adapter.commit(fixture.checkout, fixture.commit_spec)
            head_sha = git_text(fixture.checkout, "rev-parse", "HEAD")
            record = fixture.adapter.inspect_commit(fixture.checkout, head_sha)

            self.assertEqual(record.parent_sha, fixture.base_sha)
            self.assertEqual(record.patch_sha256, fixture.patch_sha256)
            self.assertEqual(record.head_sha256, fixture.bundle.subject.head_sha256)
            self.assertEqual(record.message, COMMIT_MESSAGE)
            self.assertEqual(record.author, IVES_AUTHOR)
            self.assertEqual(record.committer, COMMITTER)
            fixture.adapter.push_new_branch(
                fixture.checkout, fixture.push_spec(head_sha)
            )
            self.assertEqual(
                git_text(
                    fixture.remote,
                    "rev-parse",
                    f"refs/heads/{fixture.branch}",
                ),
                head_sha,
            )
            remote_record = fixture.adapter.inspect_remote_commit(
                fixture.checkout,
                CANONICAL_REPOSITORY,
                fixture.branch,
                head_sha,
            )
            self.assertEqual(remote_record, record)
            self.assertRegex(fixture.adapter.git_executable_sha256, r"^[0-9a-f]{64}$")

    def test_patch_bundle_rejects_envelope_subject_and_byte_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            changed_subject = dataclasses.replace(
                fixture.bundle.subject,
                finalized_envelope_sha256="9" * 64,
            )
            with self.assertRaisesRegex(
                GitAdapterContractError, "subject digest does not match"
            ):
                dataclasses.replace(fixture.bundle, subject=changed_subject)
            with self.assertRaisesRegex(GitAdapterContractError, "patch bytes changed"):
                dataclasses.replace(
                    fixture.bundle,
                    patch_bytes=fixture.bundle.patch_bytes + b"\n",
                )
            with self.assertRaisesRegex(
                GitAdapterContractError, "targets another checkout"
            ):
                other = Path(temporary) / "other"
                other.mkdir()
                rebound_subject = dataclasses.replace(
                    fixture.bundle.subject,
                    publisher_checkout=str(other),
                )
                rebound = AuthenticatedPatchBundle.from_trusted_spool(
                    spool_id="run-patch",
                    issued_by="root-spool",
                    subject=rebound_subject,
                    patch_bytes=fixture.patch_bytes,
                )
                ShellFreeGitPublisherAdapter.for_local_bare_test(
                    checkout=fixture.checkout,
                    bare_remote=fixture.remote,
                    patch_bundle=rebound,
                    git_executable=self.git_evidence,
                )

    def test_unsafe_patch_cannot_escape_checkout(self) -> None:
        malicious = (
            b"diff --git a/../../escape.txt b/../../escape.txt\n"
            b"new file mode 100644\n"
            b"index 0000000..7898192\n"
            b"--- /dev/null\n"
            b"+++ b/../../escape.txt\n"
            b"@@ -0,0 +1 @@\n"
            b"+payload\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            bundle = fixture.make_bundle(
                patch_bytes=malicious,
                changed_paths=("src/app.py",),
            )
            adapter = ShellFreeGitPublisherAdapter.for_local_bare_test(
                checkout=fixture.checkout,
                bare_remote=fixture.remote,
                patch_bundle=bundle,
                git_executable=self.git_evidence,
            )
            with self.assertRaises(GitAdapterOperationError):
                adapter.inspect_patch(fixture.checkout, fixture.base_sha)
            self.assertFalse((Path(temporary).parent / "escape.txt").exists())

    def test_dirty_untracked_and_ignored_state_fail_closed(self) -> None:
        mutations = {
            "dirty": lambda fixture: (fixture.checkout / "src" / "app.py").write_text(
                "VALUE = 99\n", encoding="utf-8"
            ),
            "untracked": lambda fixture: (fixture.checkout / "extra.txt").write_text(
                "extra\n", encoding="utf-8"
            ),
            "ignored": lambda fixture: (fixture.checkout / "ignored.tmp").write_text(
                "ignored\n", encoding="utf-8"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                fixture = self.fixture(temporary)
                mutate(fixture)
                with self.assertRaisesRegex(
                    GitAdapterRepositoryError,
                    "dirty, untracked, or ignored",
                ):
                    fixture.adapter.inspect_patch(fixture.checkout, fixture.base_sha)

    def test_config_filter_hook_and_ref_poisoning_are_rejected(self) -> None:
        def poison_filter(fixture: RepositoryFixture) -> None:
            run_git(
                fixture.checkout,
                "config",
                "filter.evil.clean",
                "/tmp/should-never-run",
            )

        def poison_hook(fixture: RepositoryFixture) -> None:
            hook = fixture.checkout / ".git" / "hooks" / "pre-commit"
            hook.write_text("untrusted hook\n", encoding="utf-8")
            hook.chmod(0o755)

        def poison_replace_ref(fixture: RepositoryFixture) -> None:
            target = fixture.checkout / ".git" / "refs" / "replace" / fixture.base_sha
            target.parent.mkdir(parents=True)
            target.write_text(fixture.base_sha + "\n", encoding="ascii")

        def poison_graft(fixture: RepositoryFixture) -> None:
            target = fixture.checkout / ".git" / "info" / "grafts"
            target.write_text(fixture.base_sha + "\n", encoding="ascii")

        def poison_shallow(fixture: RepositoryFixture) -> None:
            target = fixture.checkout / ".git" / "shallow"
            target.write_text(fixture.base_sha + "\n", encoding="ascii")

        def poison_alternates(fixture: RepositoryFixture) -> None:
            target = fixture.checkout / ".git" / "objects" / "info" / "alternates"
            target.write_text("/tmp/untrusted-objects\n", encoding="utf-8")

        def poison_info_exclude(fixture: RepositoryFixture) -> None:
            target = fixture.checkout / ".git" / "info" / "exclude"
            target.write_text(
                "# standard comments are allowed\n*.hidden\n", encoding="utf-8"
            )

        for label, poison in {
            "filter": poison_filter,
            "hook": poison_hook,
            "replace-ref": poison_replace_ref,
            "graft": poison_graft,
            "shallow": poison_shallow,
            "alternates": poison_alternates,
            "info-exclude": poison_info_exclude,
        }.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                fixture = self.fixture(temporary)
                poison(fixture)
                with self.assertRaises(GitAdapterRepositoryError):
                    fixture.adapter.inspect_patch(fixture.checkout, fixture.base_sha)

    def test_remote_url_and_push_ref_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            run_git(
                fixture.checkout,
                "remote",
                "set-url",
                "origin",
                "file:///tmp/not-the-pinned-remote.git",
            )
            with self.assertRaisesRegex(
                GitAdapterRepositoryError, "config value|remote URL"
            ):
                fixture.adapter.inspect_patch(fixture.checkout, fixture.base_sha)

        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            head_sha = fixture.materialize_commit()
            run_git(
                fixture.seed,
                "push",
                "-q",
                fixture.remote_url,
                f"{fixture.base_sha}:refs/heads/{fixture.branch}",
            )
            with self.assertRaisesRegex(GitAdapterRepositoryError, "already exists"):
                fixture.adapter.push_new_branch(
                    fixture.checkout, fixture.push_spec(head_sha)
                )
            self.assertEqual(
                git_text(
                    fixture.remote,
                    "rev-parse",
                    f"refs/heads/{fixture.branch}",
                ),
                fixture.base_sha,
            )

    def test_remote_main_movement_blocks_push(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            head_sha = fixture.materialize_commit()
            (fixture.seed / "advance.txt").write_text("advance\n", encoding="utf-8")
            run_git(fixture.seed, "add", "advance.txt")
            run_git(fixture.seed, "commit", "-qm", "test: advance main")
            advanced = git_text(fixture.seed, "rev-parse", "HEAD")
            run_git(fixture.seed, "push", "-q", "origin", "main")
            with self.assertRaisesRegex(
                GitAdapterRepositoryError, "remote ref does not match"
            ):
                fixture.adapter.push_new_branch(
                    fixture.checkout, fixture.push_spec(head_sha)
                )
            self.assertEqual(
                git_text(fixture.remote, "rev-parse", "refs/heads/main"),
                advanced,
            )

    def test_https_push_fails_before_network_without_t13_credential_port(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            run_git(
                fixture.checkout,
                "remote",
                "set-url",
                "origin",
                CANONICAL_REMOTE_URL,
            )
            adapter = ShellFreeGitPublisherAdapter(
                checkout=fixture.checkout,
                patch_bundle=fixture.bundle,
                git_executable=self.git_evidence,
            )
            adapter.inspect_patch(fixture.checkout, fixture.base_sha)
            adapter.create_branch(fixture.checkout, fixture.branch, fixture.base_sha)
            adapter.commit(fixture.checkout, fixture.commit_spec)
            head_sha = git_text(fixture.checkout, "rev-parse", "HEAD")
            self.assertTrue(adapter.requires_t13_https_credential_port)
            with self.assertRaisesRegex(
                HttpsCredentialPortRequiredError, "short-lived HTTPS credential"
            ):
                adapter.push_new_branch(fixture.checkout, fixture.push_spec(head_sha))

    def test_unimplemented_https_credential_port_cannot_claim_activation(self) -> None:
        class FakeCredentialPort:
            def capability_evidence_sha256(self) -> str:
                return "0" * 64

        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            run_git(
                fixture.checkout,
                "remote",
                "set-url",
                "origin",
                CANONICAL_REMOTE_URL,
            )
            with self.assertRaisesRegex(
                GitAdapterContractError,
                "credential port integration is not activated",
            ):
                ShellFreeGitPublisherAdapter(
                    checkout=fixture.checkout,
                    patch_bundle=fixture.bundle,
                    git_executable=self.git_evidence,
                    https_credential_port=FakeCredentialPort(),
                )

    def test_output_flood_and_timeout_are_bounded(self) -> None:
        limits = GitAdapterLimits(
            timeout_seconds=0.2,
            stdout_bytes=1024,
            stderr_bytes=1024,
        )
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary, limits=limits)
            with self.assertRaisesRegex(
                GitAdapterOperationError, "stdout exceeded output limit"
            ):
                fixture.adapter._git(  # noqa: SLF001 - bounded-runner regression
                    "show",
                    f"{fixture.base_sha}:large.txt",
                    operation="output flood fixture",
                )

            fifo = fixture.checkout / "blocking-input"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(GitAdapterOperationError, "timed out"):
                fixture.adapter._git(  # noqa: SLF001 - process-group regression
                    "hash-object",
                    str(fifo),
                    operation="timeout fixture",
                )

    def test_local_state_toctou_is_detected_before_commit_and_push(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fixture.adapter.inspect_patch(fixture.checkout, fixture.base_sha)
            (fixture.checkout / "src" / "app.py").write_text(
                "VALUE = 999\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(GitAdapterRepositoryError, "unstaged changes"):
                fixture.adapter.create_branch(
                    fixture.checkout, fixture.branch, fixture.base_sha
                )

        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            head_sha = fixture.materialize_commit()
            run_git(
                fixture.checkout,
                "update-ref",
                f"refs/heads/{fixture.branch}",
                fixture.base_sha,
                head_sha,
            )
            with self.assertRaises(GitAdapterRepositoryError):
                fixture.adapter.push_new_branch(
                    fixture.checkout, fixture.push_spec(head_sha)
                )

    def test_remote_commit_tree_not_metadata_controls_readback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fixture.adapter.inspect_patch(fixture.checkout, fixture.base_sha)
            attacker = Path(temporary) / "attacker"
            run_git(
                Path(temporary),
                "clone",
                "-q",
                fixture.remote_url,
                str(attacker),
            )
            run_git(attacker, "switch", "-q", "-c", fixture.branch, fixture.base_sha)
            run_git(attacker, "config", "user.name", IVES_AUTHOR.name)
            run_git(attacker, "config", "user.email", IVES_AUTHOR.email)
            (attacker / "src" / "app.py").write_text("VALUE = 404\n", encoding="utf-8")
            (attacker / "tests").mkdir()
            (attacker / "tests" / "test_app.py").write_text(
                "def test_value():\n    assert 404 == 404\n",
                encoding="utf-8",
            )
            run_git(attacker, "add", "src/app.py", "tests/test_app.py")
            environment = dict(os.environ)
            environment.update(
                {
                    "GIT_AUTHOR_NAME": IVES_AUTHOR.name,
                    "GIT_AUTHOR_EMAIL": IVES_AUTHOR.email,
                    "GIT_COMMITTER_NAME": COMMITTER.name,
                    "GIT_COMMITTER_EMAIL": COMMITTER.email,
                }
            )
            run_git(
                attacker,
                "commit",
                "--cleanup=verbatim",
                "-F",
                "-",
                input_bytes=COMMIT_MESSAGE.encode(),
                environment=environment,
            )
            malicious_head = git_text(attacker, "rev-parse", "HEAD")
            run_git(attacker, "push", "-q", "origin", fixture.branch)
            with self.assertRaisesRegex(
                GitAdapterRepositoryError, "tree does not match"
            ):
                fixture.adapter.inspect_remote_commit(
                    fixture.checkout,
                    CANONICAL_REPOSITORY,
                    fixture.branch,
                    malicious_head,
                )

    def test_materialized_symlink_is_rejected_even_from_authenticated_bytes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            symlink_patcher = Path(temporary) / "symlink-patcher"
            run_git(
                Path(temporary),
                "clone",
                "-q",
                fixture.remote_url,
                str(symlink_patcher),
            )
            os.symlink("src/app.py", symlink_patcher / "linked.py")
            run_git(symlink_patcher, "add", "--intent-to-add", "linked.py")
            patch_bytes = run_git(
                symlink_patcher,
                "diff",
                "--binary",
                "--no-color",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                fixture.base_sha,
                "--",
            ).stdout
            bundle = fixture.make_bundle(
                patch_bytes=patch_bytes,
                changed_paths=("linked.py",),
            )
            adapter = ShellFreeGitPublisherAdapter.for_local_bare_test(
                checkout=fixture.checkout,
                bare_remote=fixture.remote,
                patch_bundle=bundle,
                git_executable=self.git_evidence,
            )
            with self.assertRaisesRegex(GitAdapterRepositoryError, "symlink"):
                adapter.inspect_patch(fixture.checkout, fixture.base_sha)

    def test_pinned_executable_evidence_rejects_tampering(self) -> None:
        with self.assertRaisesRegex(
            GitAdapterRepositoryError, "evidence changed|digest changed"
        ):
            dataclasses.replace(
                self.git_evidence,
                size=self.git_evidence.size + 1,
            )

    def test_shell_free_runner_never_resolves_git_from_inherited_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            fake_bin = Path(temporary) / "fake-bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text("must never execute\n", encoding="utf-8")
            fake_git.chmod(0o755)
            old_path = os.environ.get("PATH")
            os.environ["PATH"] = str(fake_bin)
            try:
                snapshot = fixture.adapter.inspect_patch(
                    fixture.checkout, fixture.base_sha
                )
            finally:
                if old_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = old_path
            self.assertEqual(snapshot.patch_sha256, fixture.patch_sha256)
            self.assertEqual(
                fixture.adapter.git_executable_sha256,
                self.git_evidence.sha256,
            )

    def test_local_test_transport_is_bare_and_not_an_https_escape_hatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(temporary)
            non_bare = Path(temporary) / "not-bare"
            non_bare.mkdir()
            with self.assertRaisesRegex(
                GitAdapterRepositoryError, "not a bare repository"
            ):
                ShellFreeGitPublisherAdapter.for_local_bare_test(
                    checkout=fixture.checkout,
                    bare_remote=non_bare,
                    patch_bundle=fixture.bundle,
                    git_executable=self.git_evidence,
                )


if __name__ == "__main__":
    unittest.main()
