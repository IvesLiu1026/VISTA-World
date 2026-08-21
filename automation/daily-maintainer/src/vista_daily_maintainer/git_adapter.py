from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from .finalizer import verified_head_digest
from .naming import is_v1_daily_branch_name
from .publisher import (
    AUTOMATION_TRAILER,
    CANONICAL_REPOSITORY,
    DEFAULT_BRANCH,
    CommitRecord,
    CommitSpec,
    GitIdentity,
    LocalBranchSnapshot,
    PatchSnapshot,
    PushSpec,
)


CANONICAL_REMOTE_URL = "https://github.com/IvesLiu1026/VISTA-World.git"
PATCH_MATERIALIZATION_SCHEMA = (
    "vista.world.daily-maintainer.patch-materialization-subject.v1"
)
PATCH_BUNDLE_SCHEMA = "vista.world.daily-maintainer.authenticated-patch-bundle.v1"

_OBJECT_ID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_EMAIL = re.compile(r"^[^\s<>@]+@[^\s<>@]+$")
_IDENTITY = re.compile(
    rb"^(?P<name>[^\x00\r\n<>]{1,100}) <(?P<email>[^\x00\s<>@]+@[^\x00\s<>@]+)> "
    rb"-?[0-9]+ [+-][0-9]{4}$"
)
_PATH_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SYSTEM_EXECUTABLE_DIRS = (
    Path("/usr/local/sbin"),
    Path("/usr/local/bin"),
    Path("/usr/sbin"),
    Path("/usr/bin"),
    Path("/sbin"),
    Path("/bin"),
)
_SYSTEM_PATH = os.pathsep.join(str(path) for path in _SYSTEM_EXECUTABLE_DIRS)
_MAX_CONFIG_BYTES = 64 * 1024
_MAX_PATCH_BYTES = 8 * 1024 * 1024
_MAX_PATHS = 256
_READ_CHUNK_BYTES = 64 * 1024


class GitAdapterError(RuntimeError):
    """A concrete publisher Git operation failed closed."""


class GitAdapterContractError(GitAdapterError, ValueError):
    """Trusted adapter input is malformed or internally inconsistent."""


class GitAdapterRepositoryError(GitAdapterError):
    """The publisher checkout, Git authority, or repository state is unsafe."""


class GitAdapterOperationError(GitAdapterError):
    """A bounded shell-free Git command failed without exposing raw output."""


class HttpsCredentialPortRequiredError(GitAdapterError):
    """T13 has not injected the root-owned short-lived HTTPS credential port."""


class RootOwnedHttpsCredentialPort(Protocol):
    """Activation seam owned by T13, intentionally unavailable in this stage.

    A production implementation must keep the short-lived credential outside
    argv, the child environment, repository config, and inherited credential
    helpers.  This adapter never falls back to any of those channels.
    """

    def capability_evidence_sha256(self) -> str: ...


@dataclass(frozen=True)
class GitAdapterLimits:
    timeout_seconds: float = 30.0
    stdout_bytes: int = 512 * 1024
    stderr_bytes: int = 128 * 1024
    patch_bytes: int = _MAX_PATCH_BYTES

    def __post_init__(self) -> None:
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0.05 <= self.timeout_seconds <= 120
        ):
            raise GitAdapterContractError("Git timeout limit is invalid")
        for value, label, maximum in (
            (self.stdout_bytes, "stdout", 8 * 1024 * 1024),
            (self.stderr_bytes, "stderr", 2 * 1024 * 1024),
            (self.patch_bytes, "patch", _MAX_PATCH_BYTES),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1024
                or value > maximum
            ):
                raise GitAdapterContractError(f"Git {label} limit is invalid")


@dataclass(frozen=True)
class GitExecutableEvidence:
    path: str
    sha256: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    mode: int
    uid: int

    def __post_init__(self) -> None:
        _require_sha256(self.sha256, "Git executable digest")
        if not isinstance(self.path, str) or not Path(self.path).is_absolute():
            raise GitAdapterContractError("Git executable path must be absolute")
        for value, label in (
            (self.device, "device"),
            (self.inode, "inode"),
            (self.size, "size"),
            (self.mtime_ns, "mtime"),
            (self.mode, "mode"),
            (self.uid, "owner"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GitAdapterContractError(
                    f"Git executable {label} evidence is invalid"
                )
        self.validate_current(hash_contents=True)

    @classmethod
    def capture(cls, executable: Path | None = None) -> GitExecutableEvidence:
        if executable is None:
            found = shutil.which("git", path=_SYSTEM_PATH)
            if found is None:
                raise GitAdapterRepositoryError("pinned Git executable is unavailable")
            executable = Path(found)
        try:
            resolved = executable.resolve(strict=True)
            metadata = resolved.stat()
        except OSError as exc:
            raise GitAdapterRepositoryError(
                "pinned Git executable is unavailable"
            ) from exc
        _validate_executable_path(resolved, metadata)
        return cls(
            path=str(resolved),
            sha256=_file_sha256(resolved),
            device=metadata.st_dev,
            inode=metadata.st_ino,
            size=metadata.st_size,
            mtime_ns=metadata.st_mtime_ns,
            mode=metadata.st_mode,
            uid=metadata.st_uid,
        )

    def validate_current(self, *, hash_contents: bool = False) -> Path:
        path = Path(self.path)
        try:
            resolved = path.resolve(strict=True)
            metadata = resolved.stat()
        except OSError as exc:
            raise GitAdapterRepositoryError("pinned Git executable changed") from exc
        if resolved != path:
            raise GitAdapterRepositoryError("pinned Git executable path changed")
        _validate_executable_path(resolved, metadata)
        observed = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_mode,
            metadata.st_uid,
        )
        expected = (
            self.device,
            self.inode,
            self.size,
            self.mtime_ns,
            self.mode,
            self.uid,
        )
        if observed != expected:
            raise GitAdapterRepositoryError("pinned Git executable evidence changed")
        if hash_contents and _file_sha256(resolved) != self.sha256:
            raise GitAdapterRepositoryError("pinned Git executable digest changed")
        return resolved


@dataclass(frozen=True)
class PatchMaterializationSubject:
    finalized_envelope_sha256: str
    repository: str
    base_sha: str
    branch: str
    publisher_checkout: str
    patch_sha256: str
    head_sha256: str
    changed_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.finalized_envelope_sha256, "finalized envelope digest")
        if self.repository != CANONICAL_REPOSITORY:
            raise GitAdapterContractError("patch repository is not canonical")
        _require_object_id(self.base_sha, "patch base SHA")
        if not is_v1_daily_branch_name(self.branch):
            raise GitAdapterContractError("patch branch is not a V1 daily branch")
        _require_sha256(self.patch_sha256, "verified patch digest")
        _require_sha256(self.head_sha256, "verified head digest")
        checkout = _validated_absolute_path(
            self.publisher_checkout, "publisher checkout"
        )
        object.__setattr__(self, "publisher_checkout", str(checkout))
        _validate_changed_paths(self.changed_paths)
        expected_head = verified_head_digest(
            self.base_sha,
            self.patch_sha256,
            self.changed_paths,
        )
        if self.head_sha256 != expected_head:
            raise GitAdapterContractError("verified head digest does not match patch")

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(
            {
                "schema_version": PATCH_MATERIALIZATION_SCHEMA,
                "finalized_envelope_sha256": self.finalized_envelope_sha256,
                "repository": self.repository,
                "base_sha": self.base_sha,
                "branch": self.branch,
                "publisher_checkout": self.publisher_checkout,
                "patch_sha256": self.patch_sha256,
                "head_sha256": self.head_sha256,
                "changed_paths": list(self.changed_paths),
            }
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


@dataclass(frozen=True)
class AuthenticatedPatchBundle:
    """Immutable patch bytes plus rebinding-resistant trusted-spool evidence.

    The digest is not a signature.  T13 must deliver this object from a
    root-owned immutable spool and authenticate the spool entry before it
    reaches the publisher process.
    """

    spool_id: str
    issued_by: str
    subject: PatchMaterializationSubject
    subject_sha256: str
    patch_bytes: bytes
    patch_bytes_sha256: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.spool_id, str) or not _SAFE_ID.fullmatch(self.spool_id):
            raise GitAdapterContractError("patch spool ID is invalid")
        if not isinstance(self.issued_by, str) or not _SAFE_ID.fullmatch(
            self.issued_by
        ):
            raise GitAdapterContractError("patch spool issuer is invalid")
        if not isinstance(self.subject, PatchMaterializationSubject):
            raise GitAdapterContractError("patch materialization subject is invalid")
        _require_sha256(self.subject_sha256, "patch subject digest")
        _require_sha256(self.patch_bytes_sha256, "patch bytes digest")
        _require_sha256(self.evidence_sha256, "patch evidence digest")
        if not isinstance(self.patch_bytes, bytes) or not self.patch_bytes:
            raise GitAdapterContractError("authenticated patch bytes are invalid")
        if len(self.patch_bytes) > _MAX_PATCH_BYTES:
            raise GitAdapterContractError("authenticated patch exceeds hard limit")
        if self.subject_sha256 != self.subject.sha256:
            raise GitAdapterContractError("patch subject digest does not match")
        if hashlib.sha256(self.patch_bytes).hexdigest() != self.patch_bytes_sha256:
            raise GitAdapterContractError("authenticated patch bytes changed")
        expected = _patch_bundle_evidence_digest(
            spool_id=self.spool_id,
            issued_by=self.issued_by,
            subject_sha256=self.subject_sha256,
            patch_bytes_sha256=self.patch_bytes_sha256,
        )
        if self.evidence_sha256 != expected:
            raise GitAdapterContractError("patch spool evidence does not match")

    @classmethod
    def from_trusted_spool(
        cls,
        *,
        spool_id: str,
        issued_by: str,
        subject: PatchMaterializationSubject,
        patch_bytes: bytes,
    ) -> AuthenticatedPatchBundle:
        subject_sha256 = subject.sha256
        patch_bytes_sha256 = hashlib.sha256(patch_bytes).hexdigest()
        return cls(
            spool_id=spool_id,
            issued_by=issued_by,
            subject=subject,
            subject_sha256=subject_sha256,
            patch_bytes=patch_bytes,
            patch_bytes_sha256=patch_bytes_sha256,
            evidence_sha256=_patch_bundle_evidence_digest(
                spool_id=spool_id,
                issued_by=issued_by,
                subject_sha256=subject_sha256,
                patch_bytes_sha256=patch_bytes_sha256,
            ),
        )


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: bytes
    stderr_sha256: str


class ShellFreeGitPublisherAdapter:
    """Concrete GitPort over one publisher-owned canonical checkout.

    The production transport remains fail-closed until T13 provides a
    root-owned, short-lived HTTPS credential port.  A local-bare constructor is
    provided only for offline integration tests and never accepts an HTTPS URL.
    """

    def __init__(
        self,
        *,
        checkout: Path,
        patch_bundle: AuthenticatedPatchBundle,
        git_executable: GitExecutableEvidence,
        limits: GitAdapterLimits | None = None,
        https_credential_port: RootOwnedHttpsCredentialPort | None = None,
        _local_bare_test_remote: Path | None = None,
    ) -> None:
        if not isinstance(checkout, Path) or not checkout.is_absolute():
            raise GitAdapterContractError("publisher checkout must be an absolute Path")
        try:
            resolved = checkout.resolve(strict=True)
        except OSError as exc:
            raise GitAdapterRepositoryError(
                "publisher checkout does not exist"
            ) from exc
        if not resolved.is_dir() or resolved != checkout:
            raise GitAdapterRepositoryError("publisher checkout is not canonical")
        if not isinstance(patch_bundle, AuthenticatedPatchBundle):
            raise GitAdapterContractError("authenticated patch bundle is required")
        if patch_bundle.subject.publisher_checkout != str(resolved):
            raise GitAdapterContractError(
                "patch materialization subject targets another checkout"
            )
        if not isinstance(git_executable, GitExecutableEvidence):
            raise GitAdapterContractError("pinned Git executable evidence is required")
        self._checkout = resolved
        self._patch_bundle = patch_bundle
        self._git_evidence = git_executable
        self._limits = limits or GitAdapterLimits()
        if len(patch_bundle.patch_bytes) > self._limits.patch_bytes:
            raise GitAdapterContractError(
                "authenticated patch exceeds configured limit"
            )
        if https_credential_port is not None:
            raise GitAdapterContractError(
                "T13 HTTPS credential port integration is not activated"
            )
        self._local_bare_remote: Path | None = None
        if _local_bare_test_remote is None:
            self._remote_url = CANONICAL_REMOTE_URL
        else:
            self._local_bare_remote = _validated_local_bare_remote(
                _local_bare_test_remote
            )
            self._remote_url = self._local_bare_remote.as_uri()
        self._materialized = False
        self._expected_tree_sha: str | None = None
        self._audit_repository()

    @classmethod
    def for_local_bare_test(
        cls,
        *,
        checkout: Path,
        bare_remote: Path,
        patch_bundle: AuthenticatedPatchBundle,
        git_executable: GitExecutableEvidence,
        limits: GitAdapterLimits | None = None,
    ) -> ShellFreeGitPublisherAdapter:
        return cls(
            checkout=checkout,
            patch_bundle=patch_bundle,
            git_executable=git_executable,
            limits=limits,
            _local_bare_test_remote=bare_remote,
        )

    @property
    def git_executable_sha256(self) -> str:
        return self._git_evidence.sha256

    @property
    def requires_t13_https_credential_port(self) -> bool:
        return self._local_bare_remote is None

    def inspect_patch(self, worktree: Path, base_sha: str) -> PatchSnapshot:
        self._require_checkout(worktree)
        subject = self._patch_bundle.subject
        if base_sha != subject.base_sha:
            raise GitAdapterContractError("patch inspection base is not authenticated")
        self._audit_repository()
        if not self._materialized:
            self._require_initial_clean_base()
            self._validate_patch_bundle_now()
            self._apply_authenticated_patch()
            self._materialized = True
        snapshot, tree_sha = self._inspect_materialized_patch()
        self._expected_tree_sha = tree_sha
        self._audit_repository()
        return snapshot

    def read_local_branch(
        self, worktree: Path, branch: str
    ) -> LocalBranchSnapshot | None:
        self._require_checkout(worktree)
        self._require_subject_branch(branch)
        self._audit_repository()
        ref = f"refs/heads/{branch}"
        result = self._git(
            "for-each-ref",
            "--format=%(objectname)%00%(refname)",
            ref,
            operation="local branch read",
        )
        if not result.stdout:
            return None
        lines = result.stdout.splitlines()
        if len(lines) != 1:
            raise GitAdapterRepositoryError("local branch read-back is ambiguous")
        fields = lines[0].split(b"\0")
        if len(fields) != 2 or fields[1] != ref.encode("ascii"):
            raise GitAdapterRepositoryError("local branch read returned another ref")
        head_sha = _decode_object_id(fields[0], "local branch")
        symbolic = self._git(
            "symbolic-ref",
            "--quiet",
            "HEAD",
            check=False,
            allowed_returncodes=frozenset({0, 1}),
            operation="checked-out branch read",
        )
        checked_out = (
            symbolic.returncode == 0 and symbolic.stdout == (ref + "\n").encode()
        )
        self._audit_repository()
        return LocalBranchSnapshot(branch, head_sha, checked_out)

    def create_branch(self, worktree: Path, branch: str, start_sha: str) -> None:
        self._require_checkout(worktree)
        self._require_subject_branch(branch)
        subject = self._patch_bundle.subject
        if start_sha != subject.base_sha:
            raise GitAdapterContractError("branch start is not authenticated base")
        self._require_materialized_snapshot()
        if self.read_local_branch(worktree, branch) is not None:
            raise GitAdapterRepositoryError("publication branch already exists")
        if self._head_sha() != start_sha or self._symbolic_head() is not None:
            raise GitAdapterRepositoryError(
                "publisher checkout must remain detached at authenticated base"
            )
        self._git(
            "switch",
            "--no-track",
            "-c",
            branch,
            start_sha,
            operation="daily branch creation",
        )
        observed = self.read_local_branch(worktree, branch)
        if observed != LocalBranchSnapshot(branch, start_sha, True):
            raise GitAdapterRepositoryError("daily branch creation read-back failed")
        self._require_materialized_snapshot()

    def commit(self, worktree: Path, spec: CommitSpec) -> None:
        self._require_checkout(worktree)
        if not isinstance(spec, CommitSpec):
            raise GitAdapterContractError("commit spec has an invalid type")
        subject = self._patch_bundle.subject
        if spec.paths != subject.changed_paths:
            raise GitAdapterContractError(
                "commit paths do not match authenticated patch"
            )
        if spec.message.count(AUTOMATION_TRAILER) != 1:
            raise GitAdapterContractError("commit trailer is not unique")
        branch = self.read_local_branch(worktree, subject.branch)
        if branch != LocalBranchSnapshot(subject.branch, subject.base_sha, True):
            raise GitAdapterRepositoryError("daily branch is not at authenticated base")
        self._require_materialized_snapshot()
        environment = self._safe_environment(
            {
                "GIT_AUTHOR_NAME": spec.author.name,
                "GIT_AUTHOR_EMAIL": spec.author.email,
                "GIT_COMMITTER_NAME": spec.committer.name,
                "GIT_COMMITTER_EMAIL": spec.committer.email,
            }
        )
        self._git(
            "commit",
            "--no-verify",
            "--no-gpg-sign",
            "--cleanup=verbatim",
            "-F",
            "-",
            input_bytes=spec.message.encode("utf-8"),
            environment=environment,
            operation="logical commit creation",
        )
        head_sha = self._head_sha()
        if head_sha == subject.base_sha:
            raise GitAdapterRepositoryError("commit creation did not advance HEAD")
        record = self.inspect_commit(worktree, head_sha)
        if (
            record.message != spec.message
            or record.author != spec.author
            or record.committer != spec.committer
        ):
            raise GitAdapterRepositoryError(
                "commit identity or message read-back failed"
            )

    def inspect_commit(self, worktree: Path, head_sha: str) -> CommitRecord:
        self._require_checkout(worktree)
        _require_object_id(head_sha, "commit SHA")
        subject = self._patch_bundle.subject
        self._audit_repository()
        if self._head_sha() != head_sha:
            raise GitAdapterRepositoryError(
                "queried commit is not publisher checkout HEAD"
            )
        branch = self.read_local_branch(worktree, subject.branch)
        if branch != LocalBranchSnapshot(subject.branch, head_sha, True):
            raise GitAdapterRepositoryError("queried commit is not on daily branch")
        snapshot, tree_sha = self._inspect_materialized_patch()
        if self._expected_tree_sha is not None and tree_sha != self._expected_tree_sha:
            raise GitAdapterRepositoryError(
                "committed tree changed from materialized patch"
            )
        parsed_tree, parent, author, committer, message = self._read_commit_object(
            head_sha,
            operation="commit object read-back",
        )
        if parsed_tree != tree_sha:
            raise GitAdapterRepositoryError(
                "commit tree read-back does not match index"
            )
        if parent != subject.base_sha:
            raise GitAdapterRepositoryError("commit parent is not authenticated base")
        if snapshot != self._authenticated_patch_snapshot():
            raise GitAdapterRepositoryError("commit patch read-back changed")
        self._audit_repository()
        return CommitRecord(
            head_sha=head_sha,
            parent_sha=parent,
            patch_sha256=subject.patch_sha256,
            head_sha256=subject.head_sha256,
            message=message,
            author=author,
            committer=committer,
        )

    def inspect_remote_commit(
        self,
        worktree: Path,
        repository: str,
        branch: str,
        head_sha: str,
    ) -> CommitRecord:
        """Fetch and verify remote commit content against authenticated bytes.

        This is an integration seam beyond the current ``GitPort`` protocol.
        It lets the publisher replace metadata-only GitHub commit inspection
        with an independent Git object/tree read-back.  The fetch writes no
        FETCH_HEAD or ref and the exact branch OID is pinned before and after.
        """

        self._require_checkout(worktree)
        if repository != CANONICAL_REPOSITORY:
            raise GitAdapterContractError("remote commit repository is not canonical")
        self._require_subject_branch(branch)
        _require_object_id(head_sha, "remote commit SHA")
        if not self._materialized:
            self.inspect_patch(worktree, self._patch_bundle.subject.base_sha)
        self._require_materialized_snapshot()
        self._require_remote_ref(branch, head_sha)
        refs_before = self._local_ref_snapshot()
        remote_ref = f"refs/heads/{branch}"
        self._git(
            "fetch",
            "--no-tags",
            "--no-write-fetch-head",
            "--no-recurse-submodules",
            "--refmap=",
            self._remote_url,
            remote_ref,
            operation="remote commit object fetch",
        )
        if self._local_ref_snapshot() != refs_before:
            raise GitAdapterRepositoryError("remote commit fetch changed local refs")
        self._require_remote_ref(branch, head_sha)
        tree, parent, author, committer, message = self._read_commit_object(
            head_sha,
            operation="remote commit object read-back",
        )
        subject = self._patch_bundle.subject
        if parent != subject.base_sha:
            raise GitAdapterRepositoryError(
                "remote commit parent is not authenticated base"
            )
        if self._expected_tree_sha is None or tree != self._expected_tree_sha:
            raise GitAdapterRepositoryError(
                "remote commit tree does not match authenticated materialization"
            )
        changed = self._git(
            "diff",
            "--name-only",
            "-z",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            parent,
            head_sha,
            "--",
            operation="remote commit changed-path read-back",
        ).stdout
        if _parse_nul_paths(changed) != subject.changed_paths:
            raise GitAdapterRepositoryError(
                "remote commit paths do not match authenticated materialization"
            )
        self._require_materialized_snapshot()
        self._require_remote_ref(branch, head_sha)
        return CommitRecord(
            head_sha=head_sha,
            parent_sha=parent,
            patch_sha256=subject.patch_sha256,
            head_sha256=subject.head_sha256,
            message=message,
            author=author,
            committer=committer,
        )

    def push_new_branch(self, worktree: Path, spec: PushSpec) -> None:
        self._require_checkout(worktree)
        if not isinstance(spec, PushSpec):
            raise GitAdapterContractError("push spec has an invalid type")
        subject = self._patch_bundle.subject
        if (
            spec.repository != CANONICAL_REPOSITORY
            or spec.branch != subject.branch
            or spec.expected_main_sha != subject.base_sha
            or spec.force
        ):
            raise GitAdapterContractError(
                "push spec is outside authenticated authority"
            )
        if self._local_bare_remote is None:
            # The protocol is explicit so T13 can supply a secure port later,
            # but this stage never consumes inherited or secret-bearing state.
            raise HttpsCredentialPortRequiredError(
                "root-owned short-lived HTTPS credential port is required"
            )
        record = self.inspect_commit(worktree, spec.head_sha)
        if record.head_sha != spec.head_sha:
            raise GitAdapterRepositoryError("push commit read-back changed")
        self._require_remote_ref(DEFAULT_BRANCH, spec.expected_main_sha)
        if self._read_remote_ref(spec.branch) is not None:
            raise GitAdapterRepositoryError("remote publication branch already exists")
        self._audit_repository()
        self._require_remote_ref(DEFAULT_BRANCH, spec.expected_main_sha)
        if self._read_remote_ref(spec.branch) is not None:
            raise GitAdapterRepositoryError("remote publication branch appeared")
        ref = f"refs/heads/{spec.branch}"
        # The empty expected value is an atomic creation lease.  The refspec
        # itself is not forced and can never update a pre-existing branch.
        self._git(
            "push",
            "--porcelain",
            "--no-verify",
            "--atomic",
            f"--force-with-lease={ref}:",
            self._remote_url,
            f"{spec.head_sha}:{ref}",
            operation="new daily branch push",
        )
        self._require_remote_ref(DEFAULT_BRANCH, spec.expected_main_sha)
        self._require_remote_ref(spec.branch, spec.head_sha)
        self._audit_repository()

    def _require_checkout(self, worktree: Path) -> None:
        if not isinstance(worktree, Path) or not worktree.is_absolute():
            raise GitAdapterContractError("GitPort worktree must be an absolute Path")
        try:
            resolved = worktree.resolve(strict=True)
        except OSError as exc:
            raise GitAdapterRepositoryError(
                "GitPort worktree no longer exists"
            ) from exc
        if resolved != self._checkout:
            raise GitAdapterContractError(
                "GitPort worktree is not publisher-owned checkout"
            )

    def _require_subject_branch(self, branch: str) -> None:
        if branch != self._patch_bundle.subject.branch:
            raise GitAdapterContractError(
                "branch is not authenticated by patch subject"
            )

    def _validate_patch_bundle_now(self) -> None:
        bundle = self._patch_bundle
        if bundle.subject_sha256 != bundle.subject.sha256:
            raise GitAdapterRepositoryError(
                "patch subject changed before materialization"
            )
        if hashlib.sha256(bundle.patch_bytes).hexdigest() != bundle.patch_bytes_sha256:
            raise GitAdapterRepositoryError(
                "patch bytes changed before materialization"
            )
        expected = _patch_bundle_evidence_digest(
            spool_id=bundle.spool_id,
            issued_by=bundle.issued_by,
            subject_sha256=bundle.subject_sha256,
            patch_bytes_sha256=bundle.patch_bytes_sha256,
        )
        if bundle.evidence_sha256 != expected:
            raise GitAdapterRepositoryError(
                "patch evidence changed before materialization"
            )

    def _apply_authenticated_patch(self) -> None:
        patch_bytes = self._patch_bundle.patch_bytes
        self._git(
            "apply",
            "--check",
            "--index",
            "--whitespace=error-all",
            "-",
            input_bytes=patch_bytes,
            operation="authenticated patch preflight",
        )
        self._audit_repository()
        self._require_initial_clean_base()
        self._validate_patch_bundle_now()
        self._git(
            "apply",
            "--index",
            "--whitespace=error-all",
            "-",
            input_bytes=patch_bytes,
            operation="authenticated patch materialization",
        )
        self._inspect_materialized_patch()

    def _require_initial_clean_base(self) -> None:
        subject = self._patch_bundle.subject
        if self._head_sha() != subject.base_sha:
            raise GitAdapterRepositoryError(
                "publisher checkout is not at authenticated base"
            )
        if self._symbolic_head() is not None:
            raise GitAdapterRepositoryError("publisher checkout must begin detached")
        status = self._git(
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignored=matching",
            operation="initial checkout cleanliness check",
        ).stdout
        if status:
            raise GitAdapterRepositoryError(
                "publisher checkout contains dirty, untracked, or ignored state"
            )

    def _require_materialized_snapshot(self) -> None:
        if not self._materialized:
            raise GitAdapterRepositoryError("authenticated patch is not materialized")
        snapshot, tree_sha = self._inspect_materialized_patch()
        if snapshot != self._authenticated_patch_snapshot():
            raise GitAdapterRepositoryError("materialized patch changed")
        if self._expected_tree_sha is not None and tree_sha != self._expected_tree_sha:
            raise GitAdapterRepositoryError("materialized tree changed")
        self._expected_tree_sha = tree_sha

    def _inspect_materialized_patch(self) -> tuple[PatchSnapshot, str]:
        subject = self._patch_bundle.subject
        self._audit_repository()
        unstaged = self._git(
            "diff",
            "--quiet",
            "--no-ext-diff",
            "--no-textconv",
            "--",
            check=False,
            allowed_returncodes=frozenset({0, 1}),
            operation="unstaged diff check",
        )
        if unstaged.returncode != 0:
            raise GitAdapterRepositoryError("publisher checkout has unstaged changes")
        untracked = self._git(
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            operation="untracked state check",
        ).stdout
        ignored = self._git(
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
            "--",
            operation="ignored state check",
        ).stdout
        if untracked or ignored:
            raise GitAdapterRepositoryError(
                "publisher checkout contains untracked or ignored state"
            )
        changed = self._git(
            "diff",
            "--cached",
            "--name-only",
            "-z",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            subject.base_sha,
            "--",
            operation="materialized changed-path read",
        ).stdout
        changed_paths = _parse_nul_paths(changed)
        if changed_paths != subject.changed_paths:
            raise GitAdapterRepositoryError(
                "materialized changed paths do not match authenticated subject"
            )
        self._git(
            "diff",
            "--cached",
            "--check",
            subject.base_sha,
            "--",
            operation="materialized patch whitespace check",
        )
        self._validate_materialized_paths(changed_paths)
        tree_sha = _parse_single_object_id(
            self._git("write-tree", operation="materialized tree read").stdout,
            "materialized tree",
        )
        return self._authenticated_patch_snapshot(), tree_sha

    def _validate_materialized_paths(self, paths: tuple[str, ...]) -> None:
        for path in paths:
            current = self._checkout
            parts = PurePosixPath(path).parts
            deleted = not (self._checkout / path).exists()
            for index, part in enumerate(parts):
                current /= part
                try:
                    metadata = current.lstat()
                except FileNotFoundError:
                    if deleted and index == len(parts) - 1:
                        break
                    raise GitAdapterRepositoryError(
                        "materialized path is unexpectedly missing"
                    ) from None
                if stat.S_ISLNK(metadata.st_mode):
                    raise GitAdapterRepositoryError(
                        "materialized path contains a symlink"
                    )
            if not deleted and not stat.S_ISREG((self._checkout / path).stat().st_mode):
                raise GitAdapterRepositoryError(
                    "materialized path is not a regular file"
                )

    def _authenticated_patch_snapshot(self) -> PatchSnapshot:
        subject = self._patch_bundle.subject
        return PatchSnapshot(
            base_sha=subject.base_sha,
            patch_sha256=subject.patch_sha256,
            head_sha256=subject.head_sha256,
            changed_paths=subject.changed_paths,
        )

    def _audit_repository(self) -> None:
        metadata = self._checkout.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise GitAdapterRepositoryError("publisher checkout root is unsafe")
        top = self._git(
            "rev-parse", "--show-toplevel", operation="repository root read"
        ).stdout
        try:
            top_path = Path(top.decode("utf-8", "strict").strip()).resolve(strict=True)
        except (UnicodeDecodeError, OSError) as exc:
            raise GitAdapterRepositoryError(
                "repository root read-back is invalid"
            ) from exc
        if top_path != self._checkout:
            raise GitAdapterRepositoryError("checkout is not exact repository root")
        bare = self._git(
            "rev-parse", "--is-bare-repository", operation="repository type read"
        ).stdout
        if bare != b"false\n":
            raise GitAdapterRepositoryError("publisher checkout must be non-bare")
        git_dir_raw = self._git(
            "rev-parse", "--absolute-git-dir", operation="Git directory read"
        ).stdout
        try:
            git_dir = Path(git_dir_raw.decode("utf-8", "strict").strip()).resolve(
                strict=True
            )
        except (UnicodeDecodeError, OSError) as exc:
            raise GitAdapterRepositoryError(
                "Git directory read-back is invalid"
            ) from exc
        expected_git_dir = self._checkout / ".git"
        if git_dir != expected_git_dir or not expected_git_dir.is_dir():
            raise GitAdapterRepositoryError(
                "publisher checkout cannot be a linked or shared worktree"
            )
        self._audit_config(git_dir)
        self._audit_repository_files(git_dir)
        replacement_refs = self._git(
            "for-each-ref",
            "--format=%(refname)",
            "refs/replace",
            operation="replacement ref audit",
        ).stdout
        if replacement_refs:
            raise GitAdapterRepositoryError("replacement refs are forbidden")

    def _audit_config(self, git_dir: Path) -> None:
        raw = self._git(
            "config",
            "--local",
            "--null",
            "--list",
            stdout_limit=_MAX_CONFIG_BYTES,
            operation="repository config audit",
        ).stdout
        try:
            decoded = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise GitAdapterRepositoryError("repository config is not UTF-8") from exc
        records: list[tuple[str, str]] = []
        for record in decoded.split("\0"):
            if not record:
                continue
            name, separator, value = record.partition("\n")
            if not separator or not name:
                raise GitAdapterRepositoryError("repository config is malformed")
            records.append((name.casefold(), value))
        names = [name for name, _value in records]
        if len(names) != len(set(names)):
            raise GitAdapterRepositoryError("repository config contains duplicate keys")
        expected = {
            "core.bare": frozenset({"false"}),
            "core.filemode": frozenset({"true", "false"}),
            "core.logallrefupdates": frozenset({"true"}),
            "core.repositoryformatversion": frozenset({"0"}),
            "remote.origin.fetch": frozenset({"+refs/heads/*:refs/remotes/origin/*"}),
            "remote.origin.url": frozenset({self._remote_url}),
        }
        if set(names) != set(expected):
            raise GitAdapterRepositoryError(
                "repository config is outside the publisher allowlist"
            )
        for name, value in records:
            if value not in expected[name]:
                raise GitAdapterRepositoryError(
                    "repository config value is outside the publisher allowlist"
                )
        if (git_dir / "config.worktree").exists():
            raise GitAdapterRepositoryError("per-worktree config is forbidden")
        remote_urls = self._git(
            "remote",
            "get-url",
            "--all",
            "origin",
            operation="remote URL read-back",
        ).stdout.splitlines()
        if remote_urls != [self._remote_url.encode()]:
            raise GitAdapterRepositoryError("remote URL is not exact pinned transport")

    @staticmethod
    def _audit_repository_files(git_dir: Path) -> None:
        forbidden = (
            git_dir / "shallow",
            git_dir / "info" / "grafts",
            git_dir / "objects" / "info" / "alternates",
        )
        if any(path.exists() for path in forbidden):
            raise GitAdapterRepositoryError(
                "shallow, graft, or alternate object authority is forbidden"
            )
        for path in (git_dir / "info" / "exclude", git_dir / "info" / "attributes"):
            if not path.exists():
                continue
            try:
                payload = path.read_bytes()
            except OSError as exc:
                raise GitAdapterRepositoryError(
                    "repository info authority could not be audited"
                ) from exc
            if len(payload) > _MAX_CONFIG_BYTES:
                raise GitAdapterRepositoryError(
                    "repository info authority is oversized"
                )
            for line in payload.splitlines():
                if line.strip() and not line.lstrip().startswith(b"#"):
                    raise GitAdapterRepositoryError(
                        "repository info authority contains active rules"
                    )
        hooks = git_dir / "hooks"
        if hooks.exists():
            for item in hooks.iterdir():
                if item.name.endswith(".sample") and item.is_file():
                    continue
                raise GitAdapterRepositoryError("repository hooks are forbidden")

    def _head_sha(self) -> str:
        return _parse_single_object_id(
            self._git(
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
                operation="HEAD commit read",
            ).stdout,
            "HEAD commit",
        )

    def _read_commit_object(
        self,
        head_sha: str,
        *,
        operation: str,
    ) -> tuple[str, str, GitIdentity, GitIdentity, str]:
        raw = self._git(
            "cat-file",
            "commit",
            head_sha,
            operation=operation,
        ).stdout
        return _parse_commit_object(raw)

    def _local_ref_snapshot(self) -> bytes:
        return self._git(
            "for-each-ref",
            "--format=%(refname)%00%(objectname)",
            operation="local ref snapshot",
        ).stdout

    def _symbolic_head(self) -> str | None:
        result = self._git(
            "symbolic-ref",
            "--quiet",
            "HEAD",
            check=False,
            allowed_returncodes=frozenset({0, 1}),
            operation="HEAD symbolic ref read",
        )
        if result.returncode == 1:
            return None
        try:
            value = result.stdout.decode("ascii", "strict").strip()
        except UnicodeDecodeError as exc:
            raise GitAdapterRepositoryError("HEAD symbolic ref is invalid") from exc
        if not value.startswith("refs/heads/"):
            raise GitAdapterRepositoryError(
                "HEAD symbolic ref is outside local branches"
            )
        return value

    def _read_remote_ref(self, branch: str) -> str | None:
        if branch != DEFAULT_BRANCH and branch != self._patch_bundle.subject.branch:
            raise GitAdapterContractError(
                "remote ref read is outside publication authority"
            )
        ref = f"refs/heads/{branch}"
        result = self._git(
            "ls-remote",
            "--exit-code",
            "--refs",
            self._remote_url,
            ref,
            check=False,
            allowed_returncodes=frozenset({0, 2}),
            operation="remote ref read",
        )
        if result.returncode == 2:
            if result.stdout:
                raise GitAdapterRepositoryError("missing remote ref returned output")
            return None
        lines = result.stdout.splitlines()
        if len(lines) != 1:
            raise GitAdapterRepositoryError("remote ref read is ambiguous")
        fields = lines[0].split(b"\t")
        if len(fields) != 2 or fields[1] != ref.encode("ascii"):
            raise GitAdapterRepositoryError("remote ref read returned another ref")
        return _parse_single_object_id(fields[0] + b"\n", "remote ref")

    def _require_remote_ref(self, branch: str, expected: str) -> None:
        if self._read_remote_ref(branch) != expected:
            raise GitAdapterRepositoryError("remote ref does not match expected object")

    def _fixed_config(self) -> tuple[str, ...]:
        file_protocol = "always" if self._local_bare_remote is not None else "never"
        return (
            "-c",
            "advice.detachedHead=false",
            "-c",
            "commit.gpgSign=false",
            "-c",
            "core.attributesFile=/dev/null",
            "-c",
            "core.excludesFile=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.sshCommand=/bin/false",
            "-c",
            "core.useReplaceRefs=false",
            "-c",
            "credential.helper=",
            "-c",
            "credential.interactive=never",
            "-c",
            "diff.external=",
            "-c",
            "fetch.fsckObjects=true",
            "-c",
            "http.extraHeader=",
            "-c",
            "http.followRedirects=false",
            "-c",
            "http.proxy=",
            "-c",
            "protocol.ext.allow=never",
            "-c",
            f"protocol.file.allow={file_protocol}",
            "-c",
            "receive.fsckObjects=true",
            "-c",
            "ssh.variant=simple",
            "-c",
            "tag.gpgSign=false",
            "-c",
            "transfer.fsckObjects=true",
        )

    def _safe_environment(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        environment = {
            "PATH": _SYSTEM_PATH,
            "HOME": "/nonexistent/vista-world-publisher",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "GIT_ASKPASS": "/bin/false",
            "GIT_CONFIG_COUNT": "0",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_EDITOR": "/bin/false",
            "GIT_FLUSH": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "",
            "GIT_PROTOCOL_FROM_USER": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "PAGER": "",
            "SSH_ASKPASS": "/bin/false",
        }
        if extra:
            for key, value in extra.items():
                if key not in {
                    "GIT_AUTHOR_NAME",
                    "GIT_AUTHOR_EMAIL",
                    "GIT_COMMITTER_NAME",
                    "GIT_COMMITTER_EMAIL",
                }:
                    raise GitAdapterContractError(
                        "Git environment extension is forbidden"
                    )
                if not isinstance(value, str) or "\0" in value or "\n" in value:
                    raise GitAdapterContractError("Git identity environment is invalid")
                environment[key] = value
        return environment

    def _git(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        environment: dict[str, str] | None = None,
        check: bool = True,
        allowed_returncodes: frozenset[int] = frozenset({0}),
        stdout_limit: int | None = None,
        operation: str,
    ) -> _CommandResult:
        executable = self._git_evidence.validate_current()
        argv = (str(executable), *self._fixed_config(), *args)
        result = _run_bounded_argv(
            argv,
            cwd=self._checkout,
            environment=environment or self._safe_environment(),
            input_bytes=input_bytes,
            timeout_seconds=float(self._limits.timeout_seconds),
            stdout_limit=stdout_limit or self._limits.stdout_bytes,
            stderr_limit=self._limits.stderr_bytes,
            operation=operation,
        )
        self._git_evidence.validate_current()
        if result.returncode not in allowed_returncodes:
            raise GitAdapterOperationError(f"{operation} returned an invalid status")
        if check and result.returncode != 0:
            raise GitAdapterOperationError(f"{operation} failed")
        return result


def _run_bounded_argv(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    environment: dict[str, str],
    input_bytes: bytes | None,
    timeout_seconds: float,
    stdout_limit: int,
    stderr_limit: int,
    operation: str,
) -> _CommandResult:
    input_handle = None
    stdin: int | object = subprocess.DEVNULL
    if input_bytes is not None:
        input_handle = tempfile.TemporaryFile()
        input_handle.write(input_bytes)
        input_handle.seek(0)
        stdin = input_handle
    try:
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=environment,
                stdin=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            raise GitAdapterOperationError(f"{operation} could not start") from exc
        if process.stdout is None or process.stderr is None:
            _kill_process_group(process)
            raise GitAdapterOperationError(f"{operation} pipes are unavailable")
        stdout = bytearray()
        stderr = bytearray()
        streams = {
            process.stdout.fileno(): (process.stdout, stdout, stdout_limit, "stdout"),
            process.stderr.fileno(): (process.stderr, stderr, stderr_limit, "stderr"),
        }
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        selector.register(process.stderr, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout_seconds
        failure: str | None = None
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    failure = "timed out"
                    break
                events = selector.select(remaining)
                if not events:
                    failure = "timed out"
                    break
                for key, _mask in events:
                    stream, buffer, limit, label = streams[key.fd]
                    chunk = os.read(key.fd, _READ_CHUNK_BYTES)
                    if not chunk:
                        selector.unregister(stream)
                        continue
                    available = limit - len(buffer)
                    if len(chunk) > available:
                        if available > 0:
                            buffer.extend(chunk[:available])
                        failure = f"{label} exceeded output limit"
                        break
                    buffer.extend(chunk)
                if failure is not None:
                    break
        finally:
            selector.close()
        if failure is not None:
            _kill_process_group(process)
            for stream in (process.stdout, process.stderr):
                stream.close()
            raise GitAdapterOperationError(f"{operation} {failure}")
        try:
            returncode = process.wait(timeout=max(0.05, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            _kill_process_group(process)
            raise GitAdapterOperationError(f"{operation} timed out") from exc
        finally:
            process.stdout.close()
            process.stderr.close()
        return _CommandResult(
            returncode=returncode,
            stdout=bytes(stdout),
            stderr_sha256=hashlib.sha256(stderr).hexdigest(),
        )
    finally:
        if input_handle is not None:
            input_handle.close()


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=0.25)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.25)
    except subprocess.TimeoutExpired:
        pass


def _parse_commit_object(
    payload: bytes,
) -> tuple[str, str, GitIdentity, GitIdentity, str]:
    headers_raw, separator, message_raw = payload.partition(b"\n\n")
    if not separator:
        raise GitAdapterRepositoryError("commit object is malformed")
    headers: dict[bytes, list[bytes]] = {}
    for line in headers_raw.splitlines():
        name, space, value = line.partition(b" ")
        if not space or line.startswith(b" "):
            raise GitAdapterRepositoryError("commit object headers are malformed")
        headers.setdefault(name, []).append(value)
    if set(headers) != {b"tree", b"parent", b"author", b"committer"} or any(
        len(values) != 1 for values in headers.values()
    ):
        raise GitAdapterRepositoryError(
            "commit object authority is not a single-parent commit"
        )
    tree = _decode_object_id(headers[b"tree"][0], "commit tree")
    parent = _decode_object_id(headers[b"parent"][0], "commit parent")
    author = _parse_identity(headers[b"author"][0], "commit author")
    committer = _parse_identity(headers[b"committer"][0], "commit committer")
    try:
        message = message_raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise GitAdapterRepositoryError("commit message is not UTF-8") from exc
    if "\0" in message:
        raise GitAdapterRepositoryError("commit message contains NUL")
    return tree, parent, author, committer, message


def _parse_identity(payload: bytes, label: str) -> GitIdentity:
    match = _IDENTITY.fullmatch(payload)
    if match is None:
        raise GitAdapterRepositoryError(f"{label} is malformed")
    try:
        name = match.group("name").decode("utf-8", "strict")
        email = match.group("email").decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise GitAdapterRepositoryError(f"{label} encoding is invalid") from exc
    if not _EMAIL.fullmatch(email):
        raise GitAdapterRepositoryError(f"{label} email is invalid")
    return GitIdentity(name, email)


def _parse_nul_paths(payload: bytes) -> tuple[str, ...]:
    values: list[str] = []
    for raw in payload.split(b"\0"):
        if not raw:
            continue
        try:
            values.append(raw.decode("utf-8", "strict"))
        except UnicodeDecodeError as exc:
            raise GitAdapterRepositoryError("Git path is not UTF-8") from exc
    result = tuple(sorted(values))
    _validate_changed_paths(result)
    return result


def _parse_single_object_id(payload: bytes, label: str) -> str:
    lines = payload.splitlines()
    if len(lines) != 1:
        raise GitAdapterRepositoryError(f"{label} read-back is ambiguous")
    return _decode_object_id(lines[0], label)


def _decode_object_id(payload: bytes, label: str) -> str:
    try:
        value = payload.decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise GitAdapterRepositoryError(f"{label} is invalid") from exc
    _require_object_id(value, label)
    return value


def _validate_changed_paths(paths: tuple[str, ...]) -> None:
    if (
        not isinstance(paths, tuple)
        or not paths
        or len(paths) > _MAX_PATHS
        or tuple(sorted(paths)) != paths
        or len(set(paths)) != len(paths)
    ):
        raise GitAdapterContractError("authenticated changed paths are invalid")
    for path in paths:
        if not isinstance(path, str) or len(path.encode("utf-8")) > 1024:
            raise GitAdapterContractError("authenticated changed path is invalid")
        pure = PurePosixPath(path)
        if (
            not path
            or path.startswith(("/", "\\"))
            or "\\" in path
            or _PATH_CONTROL.search(path)
            or any(part in {"", ".", ".."} for part in pure.parts)
            or pure.parts[0].casefold() == ".git"
        ):
            raise GitAdapterContractError("authenticated changed path is unsafe")


def _validated_absolute_path(value: str, label: str) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or "\0" in value
        or "\n" in value
        or not Path(value).is_absolute()
        or value.startswith("//")
        or os.path.normpath(value) != value
    ):
        raise GitAdapterContractError(f"{label} is invalid")
    return Path(value)


def _validated_local_bare_remote(value: Path) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise GitAdapterContractError("local bare test remote must be absolute")
    try:
        resolved = value.resolve(strict=True)
        metadata = resolved.lstat()
    except OSError as exc:
        raise GitAdapterRepositoryError(
            "local bare test remote is unavailable"
        ) from exc
    if (
        resolved != value
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
    ):
        raise GitAdapterRepositoryError("local bare test remote is unsafe")
    if not (resolved / "HEAD").is_file() or not (resolved / "objects").is_dir():
        raise GitAdapterRepositoryError("local test remote is not a bare repository")
    return resolved


def _validate_executable_path(path: Path, metadata: os.stat_result) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & 0o022
        or not os.access(path, os.X_OK)
    ):
        raise GitAdapterRepositoryError(
            "pinned Git executable is not root-owned immutable"
        )
    for directory in (path.parent, *path.parents):
        info = directory.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise GitAdapterRepositoryError(
                "pinned Git executable has a writable path ancestor"
            )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise GitAdapterRepositoryError(
            "pinned executable could not be hashed"
        ) from exc
    return digest.hexdigest()


def _require_object_id(value: object, label: str) -> None:
    if not isinstance(value, str) or not _OBJECT_ID.fullmatch(value):
        raise GitAdapterContractError(f"{label} is invalid")


def _require_sha256(value: object, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise GitAdapterContractError(f"{label} is invalid")


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _patch_bundle_evidence_digest(
    *,
    spool_id: str,
    issued_by: str,
    subject_sha256: str,
    patch_bytes_sha256: str,
) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "schema_version": PATCH_BUNDLE_SCHEMA,
                "spool_id": spool_id,
                "issued_by": issued_by,
                "subject_sha256": subject_sha256,
                "patch_bytes_sha256": patch_bytes_sha256,
            }
        )
    ).hexdigest()
