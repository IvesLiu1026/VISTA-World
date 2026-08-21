from __future__ import annotations

import datetime as dt
import errno
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field, fields as dataclass_fields
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Protocol

from .candidate import (
    Candidate,
    CandidateSource,
    candidate_authorization_digest,
    enforce_v1_candidate_policy,
    path_matches_pattern,
)
from .finalizer import (
    FINALIZED_ENVELOPE_SCHEMA,
    FinalizedVerificationCheck,
    FinalizedVerifierEnvelope,
    verified_head_digest,
)
from .naming import v1_daily_branch_name
from .state import PublicationSnapshot, RunKey, RunState, state_digest
from .verifier import (
    VerificationSubject,
    isolation_evidence_digest,
    verification_check_subject_digest,
)


SPOOL_MANIFEST_SCHEMA = "vista.world.daily-maintainer.spool-manifest.v1"
SPOOL_TRANSITION_SCHEMA = "vista.world.daily-maintainer.spool-transition.v1"
REMATERIALIZATION_SCHEMA = "vista.world.daily-maintainer.rematerialization.v1"
CANONICAL_REPOSITORY = "IvesLiu1026/VISTA-World"

MAX_ENVELOPE_BYTES = 1024 * 1024
MAX_PATCH_BUNDLE_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
MAX_TRANSITION_BYTES = 32 * 1024

_SPOOL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_GIT_OBJECT_ID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_ID = re.compile(r"^VW-DM-[0-9]{4,}$")
_SAFE_ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPOOL_FILE_MODE = 0o440
_PUBLISHER_STATE_FILE_MODE = 0o400
_SPOOL_ROOT_MODE = 0o750
_PUBLISHER_ROOT_MODE = 0o700
_SPOOL_WRITE_FACTORY_TOKEN = object()


class SpoolError(RuntimeError):
    """Base class for fail-closed spool and rematerialization failures."""


class SpoolContractError(SpoolError, ValueError):
    """Typed spool input is malformed or exceeds a hard bound."""


class SpoolDeploymentError(SpoolError):
    """Observed filesystem ownership or isolation evidence is unsafe."""


class SpoolConflictError(SpoolError):
    """An append-only spool ID already has incompatible state."""


class SpoolIncompleteError(SpoolError):
    """A reserved spool entry never reached its sealed commit marker."""


class SpoolIntegrityError(SpoolError):
    """Sealed bytes, metadata, or transition evidence changed."""


class RematerializationError(SpoolError):
    """A publisher-owned checkout could not be reconstructed exactly."""


class SpoolState(str, Enum):
    RESERVED = "reserved"
    SEALED = "sealed"
    CLAIMED = "claimed"
    MATERIALIZED = "materialized"


@dataclass(frozen=True)
class DirectoryIdentity:
    path: str
    owner_uid: int
    group_gid: int
    mode: int
    device: int
    inode: int
    link_count: int

    def __post_init__(self) -> None:
        _absolute_normalized_path(self.path, "directory identity path")
        for value, label, minimum in (
            (self.owner_uid, "directory owner UID", 0),
            (self.group_gid, "directory group GID", 0),
            (self.mode, "directory mode", 0),
            (self.device, "directory device", 0),
            (self.inode, "directory inode", 1),
            (self.link_count, "directory link count", 2),
        ):
            _bounded_int(value, label, minimum=minimum)
        if self.mode > 0o7777:
            raise SpoolContractError("directory mode is invalid")

    @classmethod
    def capture(cls, path: Path) -> DirectoryIdentity:
        normalized = _absolute_directory(path, "deployment directory")
        metadata = normalized.lstat()
        if not stat.S_ISDIR(metadata.st_mode):
            raise SpoolDeploymentError("deployment path is not a real directory")
        return cls(
            path=str(normalized),
            owner_uid=metadata.st_uid,
            group_gid=metadata.st_gid,
            mode=stat.S_IMODE(metadata.st_mode),
            device=metadata.st_dev,
            inode=metadata.st_ino,
            link_count=metadata.st_nlink,
        )

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(_directory_payload(self))

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_bytes)


@dataclass(frozen=True)
class SpoolDeploymentEvidence:
    """Filesystem and namespace facts required before unattended activation.

    ``attest`` is a one-time provisioning operation and requires all three
    roots to be exactly empty. Preventing mounts or entries after that snapshot
    belongs to the T13 service-UID, capability, and mount-namespace boundary;
    runtime Python does not claim to close that race.

    The remaining contract can be exercised in report-only tests when the
    service UIDs do not yet exist. ``require_unattended_ready`` remains the
    explicit activation gate and rejects such evidence.
    """

    spool_root: DirectoryIdentity
    publisher_root: DirectoryIdentity
    publisher_state_root: DirectoryIdentity
    control_uid: int
    publisher_uid: int
    patcher_uid: int
    publisher_group_gid: int
    roots_initially_empty: bool
    distinct_uids_enforced: bool
    publisher_spool_read_only: bool
    patcher_spool_unmounted: bool
    patcher_publisher_root_unmounted: bool
    patcher_publisher_state_root_unmounted: bool
    publisher_patcher_root_unmounted: bool
    attested_by: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.spool_root, DirectoryIdentity)
            or not isinstance(self.publisher_root, DirectoryIdentity)
            or not isinstance(self.publisher_state_root, DirectoryIdentity)
        ):
            raise SpoolContractError("deployment directory identity is invalid")
        for value, label in (
            (self.control_uid, "control UID"),
            (self.publisher_uid, "publisher UID"),
            (self.patcher_uid, "patcher UID"),
            (self.publisher_group_gid, "publisher group GID"),
        ):
            _bounded_int(value, label, minimum=0)
        for name in (
            "roots_initially_empty",
            "distinct_uids_enforced",
            "publisher_spool_read_only",
            "patcher_spool_unmounted",
            "patcher_publisher_root_unmounted",
            "patcher_publisher_state_root_unmounted",
            "publisher_patcher_root_unmounted",
        ):
            if type(getattr(self, name)) is not bool:
                raise SpoolContractError(f"deployment {name} is invalid")
        if not self.roots_initially_empty:
            raise SpoolDeploymentError(
                "deployment roots were not proven initially empty"
            )
        _safe_actor(self.attested_by, "deployment attestor")
        _require_sha256(self.evidence_sha256, "deployment evidence digest")
        if self.spool_root.owner_uid != self.control_uid:
            raise SpoolDeploymentError("spool root is not control-owned")
        if self.spool_root.group_gid != self.publisher_group_gid:
            raise SpoolDeploymentError("spool root is not publisher-group readable")
        if self.spool_root.mode != _SPOOL_ROOT_MODE:
            raise SpoolDeploymentError("spool root mode is unsafe")
        if self.publisher_root.owner_uid != self.publisher_uid:
            raise SpoolDeploymentError("publisher root is not publisher-owned")
        if self.publisher_root.mode != _PUBLISHER_ROOT_MODE:
            raise SpoolDeploymentError("publisher root mode is unsafe")
        if self.publisher_state_root.owner_uid != self.publisher_uid:
            raise SpoolDeploymentError("publisher state root is not publisher-owned")
        if self.publisher_state_root.mode != _PUBLISHER_ROOT_MODE:
            raise SpoolDeploymentError("publisher state root mode is unsafe")
        roots = (
            Path(self.spool_root.path),
            Path(self.publisher_root.path),
            Path(self.publisher_state_root.path),
        )
        if any(
            _paths_overlap(left, right)
            for index, left in enumerate(roots)
            for right in roots[index + 1 :]
        ):
            raise SpoolDeploymentError("deployment roots overlap")
        root_inodes = {
            (self.spool_root.device, self.spool_root.inode),
            (self.publisher_root.device, self.publisher_root.inode),
            (self.publisher_state_root.device, self.publisher_state_root.inode),
        }
        if len(root_inodes) != 3:
            raise SpoolDeploymentError(
                "deployment roots share a filesystem inode alias"
            )
        if self.evidence_sha256 != _deployment_digest(self):
            raise SpoolContractError("deployment evidence digest does not match")

    @classmethod
    def attest(
        cls,
        *,
        spool_root: Path,
        publisher_root: Path,
        publisher_state_root: Path,
        control_uid: int,
        publisher_uid: int,
        patcher_uid: int,
        publisher_group_gid: int,
        distinct_uids_enforced: bool,
        publisher_spool_read_only: bool,
        patcher_spool_unmounted: bool,
        patcher_publisher_root_unmounted: bool,
        patcher_publisher_state_root_unmounted: bool,
        publisher_patcher_root_unmounted: bool,
        attested_by: str,
    ) -> SpoolDeploymentEvidence:
        spool_identity = DirectoryIdentity.capture(spool_root)
        publisher_identity = DirectoryIdentity.capture(publisher_root)
        publisher_state_identity = DirectoryIdentity.capture(publisher_state_root)
        for identity, expected_mode, label in (
            (spool_identity, _SPOOL_ROOT_MODE, "spool root"),
            (publisher_identity, _PUBLISHER_ROOT_MODE, "publisher root"),
            (
                publisher_state_identity,
                _PUBLISHER_ROOT_MODE,
                "publisher state root",
            ),
        ):
            _attest_initially_empty_directory(
                identity,
                expected_mode=expected_mode,
                label=label,
            )
        values = {
            "spool_root": spool_identity,
            "publisher_root": publisher_identity,
            "publisher_state_root": publisher_state_identity,
            "control_uid": control_uid,
            "publisher_uid": publisher_uid,
            "patcher_uid": patcher_uid,
            "publisher_group_gid": publisher_group_gid,
            "roots_initially_empty": True,
            "distinct_uids_enforced": distinct_uids_enforced,
            "publisher_spool_read_only": publisher_spool_read_only,
            "patcher_spool_unmounted": patcher_spool_unmounted,
            "patcher_publisher_root_unmounted": patcher_publisher_root_unmounted,
            "patcher_publisher_state_root_unmounted": (
                patcher_publisher_state_root_unmounted
            ),
            "publisher_patcher_root_unmounted": publisher_patcher_root_unmounted,
            "attested_by": attested_by,
        }
        digest = _sha256(_canonical_json_bytes(_deployment_payload(values)))
        return cls(**values, evidence_sha256=digest)

    @property
    def unattended_ready(self) -> bool:
        return (
            self.roots_initially_empty
            and self.distinct_uids_enforced
            and len({self.control_uid, self.publisher_uid, self.patcher_uid}) == 3
            and self.publisher_spool_read_only
            and self.patcher_spool_unmounted
            and self.patcher_publisher_root_unmounted
            and self.patcher_publisher_state_root_unmounted
            and self.publisher_patcher_root_unmounted
        )

    def require_unattended_ready(self) -> None:
        if not self.unattended_ready:
            raise SpoolDeploymentError(
                "unattended spool remains dormant without T13 provisioning/UID/mount evidence"
            )


@dataclass(frozen=True)
class SpoolSubject:
    run_id: str
    run_date: str
    repository: str
    base_sha: str
    branch_name: str
    candidate_id: str
    candidate_slug: str
    candidate_sha256: str
    backlog_sha256: str
    backlog_authorization_sha256: str
    run_state_sha256: str
    verification_subject_sha256: str
    patch_sha256: str
    verified_head_sha256: str
    final_envelope_sha256: str
    source_worktree_path: str
    changed_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        run_date = _canonical_date(self.run_date)
        if self.repository != CANONICAL_REPOSITORY:
            raise SpoolContractError("spool repository is not canonical")
        _safe_line(self.run_id, "spool run ID", maximum=256)
        _require_git_oid(self.base_sha, "spool base SHA")
        if self.run_id != f"{run_date}/{self.repository}@{self.base_sha}":
            raise SpoolContractError("spool run ID does not match run authority")
        if not isinstance(self.candidate_id, str) or not _CANDIDATE_ID.fullmatch(
            self.candidate_id
        ):
            raise SpoolContractError("spool candidate ID is invalid")
        _safe_line(self.candidate_slug, "spool candidate slug", maximum=48)
        if self.branch_name != v1_daily_branch_name(
            run_date, self.candidate_slug, self.base_sha
        ):
            raise SpoolContractError("spool branch does not match run authority")
        for value, label in (
            (self.candidate_sha256, "candidate digest"),
            (self.backlog_sha256, "backlog digest"),
            (self.backlog_authorization_sha256, "backlog authority digest"),
            (self.run_state_sha256, "run state digest"),
            (self.verification_subject_sha256, "verification subject digest"),
            (self.patch_sha256, "patch digest"),
            (self.verified_head_sha256, "verified head digest"),
            (self.final_envelope_sha256, "final envelope digest"),
        ):
            _require_sha256(value, label)
        _absolute_normalized_path(self.source_worktree_path, "source patcher worktree")
        _safe_changed_paths(self.changed_paths)

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(_subject_payload(self))

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_bytes)


@dataclass(frozen=True, init=False)
class SpoolWrite:
    spool_id: str
    subject: SpoolSubject
    envelope_bytes: bytes
    patch_bundle: bytes
    _factory_token: object = field(repr=False, compare=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise SpoolContractError("spool writes are factory-only finalized artifacts")

    def _validate(self) -> None:
        if self._factory_token is not _SPOOL_WRITE_FACTORY_TOKEN:
            raise SpoolContractError("spool write lacks finalized factory authority")
        _safe_spool_id(self.spool_id)
        if not isinstance(self.subject, SpoolSubject):
            raise SpoolContractError("spool subject is invalid")
        _bounded_bytes(
            self.envelope_bytes,
            "finalized envelope",
            maximum=MAX_ENVELOPE_BYTES,
        )
        _bounded_bytes(
            self.patch_bundle,
            "patch bundle",
            maximum=MAX_PATCH_BUNDLE_BYTES,
        )
        parsed = _subject_from_envelope_bytes(self.envelope_bytes)
        if parsed != self.subject:
            raise SpoolContractError("finalized envelope subject does not match")
        if _sha256(self.envelope_bytes) != self.subject.final_envelope_sha256:
            raise SpoolContractError("finalized envelope digest does not match")

    @classmethod
    def from_finalized(
        cls,
        *,
        spool_id: str,
        envelope: FinalizedVerifierEnvelope,
        patch_bundle: bytes,
    ) -> SpoolWrite:
        if type(envelope) is not FinalizedVerifierEnvelope:
            raise SpoolContractError("exact finalized verifier envelope is required")
        if type(patch_bundle) is not bytes:
            raise SpoolContractError("exact patch bundle bytes are required")
        envelope_bytes = envelope.canonical_bytes
        subject = _subject_from_envelope_bytes(envelope_bytes)
        value = object.__new__(cls)
        object.__setattr__(value, "spool_id", spool_id)
        object.__setattr__(value, "subject", subject)
        object.__setattr__(value, "envelope_bytes", envelope_bytes)
        object.__setattr__(value, "patch_bundle", patch_bundle)
        object.__setattr__(value, "_factory_token", _SPOOL_WRITE_FACTORY_TOKEN)
        value._validate()
        return value

    @property
    def patch_bundle_sha256(self) -> str:
        return _sha256(self.patch_bundle)

    @property
    def request_sha256(self) -> str:
        return _sha256(
            _canonical_json_bytes(
                {
                    "schema_version": "vista.world.daily-maintainer.spool-request.v1",
                    "spool_id": self.spool_id,
                    "subject": _subject_payload(self.subject),
                    "subject_sha256": self.subject.sha256,
                    "envelope_bytes": len(self.envelope_bytes),
                    "patch_bundle_bytes": len(self.patch_bundle),
                    "patch_bundle_sha256": self.patch_bundle_sha256,
                }
            )
        )


@dataclass(frozen=True)
class SpoolReservation:
    spool_id: str
    request_sha256: str
    subject_sha256: str

    def __post_init__(self) -> None:
        _safe_spool_id(self.spool_id)
        _require_sha256(self.request_sha256, "spool request digest")
        _require_sha256(self.subject_sha256, "spool subject digest")


@dataclass(frozen=True)
class SpoolFileIdentity:
    name: str
    sha256: str
    size: int
    device: int
    inode: int
    owner_uid: int
    group_gid: int
    mode: int
    link_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or "/" in self.name
            or "\\" in self.name
            or self.name in {"", ".", ".."}
        ):
            raise SpoolContractError("spool artifact name is invalid")
        _require_sha256(self.sha256, "spool artifact digest")
        for value, label, minimum in (
            (self.size, "spool artifact size", 1),
            (self.device, "spool artifact device", 0),
            (self.inode, "spool artifact inode", 1),
            (self.owner_uid, "spool artifact owner", 0),
            (self.group_gid, "spool artifact group", 0),
            (self.mode, "spool artifact mode", 0),
            (self.link_count, "spool artifact link count", 1),
        ):
            _bounded_int(value, label, minimum=minimum)
        if self.mode != _SPOOL_FILE_MODE or self.link_count != 1:
            raise SpoolContractError("spool artifact mode or link count is unsafe")


@dataclass(frozen=True)
class SpoolManifest:
    spool_id: str
    subject: SpoolSubject
    subject_sha256: str
    request_sha256: str
    patch_bundle_sha256: str
    deployment_evidence_sha256: str
    envelope_file: SpoolFileIdentity
    patch_file: SpoolFileIdentity
    schema_version: str = SPOOL_MANIFEST_SCHEMA
    state: str = SpoolState.SEALED.value

    def __post_init__(self) -> None:
        if self.schema_version != SPOOL_MANIFEST_SCHEMA or self.state != "sealed":
            raise SpoolContractError("spool manifest schema or state is invalid")
        _safe_spool_id(self.spool_id)
        if not isinstance(self.subject, SpoolSubject):
            raise SpoolContractError("spool manifest subject is invalid")
        for value, label in (
            (self.subject_sha256, "spool subject digest"),
            (self.request_sha256, "spool request digest"),
            (self.patch_bundle_sha256, "patch bundle digest"),
            (self.deployment_evidence_sha256, "deployment evidence digest"),
        ):
            _require_sha256(value, label)
        if self.subject_sha256 != self.subject.sha256:
            raise SpoolContractError("spool manifest subject digest does not match")
        if self.envelope_file.name != _artifact_name(self.spool_id, "envelope.json"):
            raise SpoolContractError("spool envelope filename does not match")
        if self.patch_file.name != _artifact_name(self.spool_id, "patch.bundle"):
            raise SpoolContractError("spool patch filename does not match")
        if self.envelope_file.sha256 != self.subject.final_envelope_sha256:
            raise SpoolContractError("spool envelope file digest does not match")
        if self.patch_file.sha256 != self.patch_bundle_sha256:
            raise SpoolContractError("spool patch file digest does not match")

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(_manifest_payload(self))

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_bytes)


@dataclass(frozen=True)
class SealedSpoolRecord:
    manifest: SpoolManifest
    envelope_bytes: bytes
    patch_bundle: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, SpoolManifest):
            raise SpoolContractError("sealed spool manifest is invalid")
        if _sha256(self.envelope_bytes) != self.manifest.envelope_file.sha256:
            raise SpoolIntegrityError("sealed envelope digest does not match")
        if _sha256(self.patch_bundle) != self.manifest.patch_bundle_sha256:
            raise SpoolIntegrityError("sealed patch bundle digest does not match")


@dataclass(frozen=True)
class RematerializationSubject:
    spool_id: str
    manifest_sha256: str
    subject_sha256: str
    patch_bundle_sha256: str
    run_id: str
    repository: str
    base_sha: str
    branch_name: str
    candidate_id: str
    candidate_sha256: str
    backlog_sha256: str
    backlog_authorization_sha256: str
    patch_sha256: str
    final_envelope_sha256: str
    source_worktree_path: str
    changed_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        _safe_spool_id(self.spool_id)
        for value, label in (
            (self.manifest_sha256, "spool manifest digest"),
            (self.subject_sha256, "spool subject digest"),
            (self.patch_bundle_sha256, "patch bundle digest"),
            (self.candidate_sha256, "candidate digest"),
            (self.backlog_sha256, "backlog digest"),
            (self.backlog_authorization_sha256, "backlog authority digest"),
            (self.patch_sha256, "patch digest"),
            (self.final_envelope_sha256, "final envelope digest"),
        ):
            _require_sha256(value, label)
        _safe_line(self.run_id, "rematerialization run ID", maximum=256)
        if self.repository != CANONICAL_REPOSITORY:
            raise SpoolContractError("rematerialization repository is not canonical")
        _require_git_oid(self.base_sha, "rematerialization base SHA")
        _safe_line(self.branch_name, "rematerialization branch", maximum=128)
        if not _CANDIDATE_ID.fullmatch(self.candidate_id):
            raise SpoolContractError("rematerialization candidate ID is invalid")
        _absolute_normalized_path(
            self.source_worktree_path, "rematerialization source worktree"
        )
        _safe_changed_paths(self.changed_paths)

    @classmethod
    def from_record(cls, record: SealedSpoolRecord) -> RematerializationSubject:
        subject = record.manifest.subject
        return cls(
            spool_id=record.manifest.spool_id,
            manifest_sha256=record.manifest.sha256,
            subject_sha256=subject.sha256,
            patch_bundle_sha256=record.manifest.patch_bundle_sha256,
            run_id=subject.run_id,
            repository=subject.repository,
            base_sha=subject.base_sha,
            branch_name=subject.branch_name,
            candidate_id=subject.candidate_id,
            candidate_sha256=subject.candidate_sha256,
            backlog_sha256=subject.backlog_sha256,
            backlog_authorization_sha256=subject.backlog_authorization_sha256,
            patch_sha256=subject.patch_sha256,
            final_envelope_sha256=subject.final_envelope_sha256,
            source_worktree_path=subject.source_worktree_path,
            changed_paths=subject.changed_paths,
        )

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(_rematerialization_subject_payload(self))

    @property
    def sha256(self) -> str:
        return _sha256(self.canonical_bytes)


@dataclass(frozen=True)
class PreparedPublisherCheckout:
    subject_sha256: str
    path: str
    repository: str
    base_sha: str
    branch_name: str
    owner_uid: int
    mode: int
    device: int
    inode: int
    link_count: int
    clean_base: bool
    publisher_owned: bool
    source_worktree_unmounted: bool
    observed_by: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(self.subject_sha256, "prepared checkout subject digest")
        _absolute_normalized_path(self.path, "prepared checkout path")
        if self.repository != CANONICAL_REPOSITORY:
            raise SpoolContractError("prepared checkout repository is not canonical")
        _require_git_oid(self.base_sha, "prepared checkout base SHA")
        _safe_line(self.branch_name, "prepared checkout branch", maximum=128)
        for value, label, minimum in (
            (self.owner_uid, "prepared checkout owner", 0),
            (self.mode, "prepared checkout mode", 0),
            (self.device, "prepared checkout device", 0),
            (self.inode, "prepared checkout inode", 1),
            (self.link_count, "prepared checkout link count", 2),
        ):
            _bounded_int(value, label, minimum=minimum)
        for name in ("clean_base", "publisher_owned", "source_worktree_unmounted"):
            if type(getattr(self, name)) is not bool:
                raise SpoolContractError(f"prepared checkout {name} is invalid")
        _safe_actor(self.observed_by, "prepared checkout observer")
        _require_sha256(self.evidence_sha256, "prepared checkout evidence digest")
        if self.evidence_sha256 != _prepared_checkout_digest(self):
            raise SpoolContractError("prepared checkout evidence digest does not match")

    @classmethod
    def attest(
        cls,
        path: Path,
        subject: RematerializationSubject,
        *,
        observed_by: str,
        clean_base: bool = True,
        publisher_owned: bool = True,
        source_worktree_unmounted: bool = True,
    ) -> PreparedPublisherCheckout:
        identity = DirectoryIdentity.capture(path)
        values = {
            "subject_sha256": subject.sha256,
            "path": identity.path,
            "repository": subject.repository,
            "base_sha": subject.base_sha,
            "branch_name": subject.branch_name,
            "owner_uid": identity.owner_uid,
            "mode": identity.mode,
            "device": identity.device,
            "inode": identity.inode,
            "link_count": identity.link_count,
            "clean_base": clean_base,
            "publisher_owned": publisher_owned,
            "source_worktree_unmounted": source_worktree_unmounted,
            "observed_by": observed_by,
        }
        digest = _sha256(_canonical_json_bytes(_prepared_checkout_payload(values)))
        return cls(**values, evidence_sha256=digest)


@dataclass(frozen=True)
class RematerializedPublisherCheckout:
    subject_sha256: str
    path: str
    repository: str
    base_sha: str
    branch_name: str
    candidate_id: str
    candidate_sha256: str
    backlog_sha256: str
    backlog_authorization_sha256: str
    patch_sha256: str
    patch_bundle_sha256: str
    final_envelope_sha256: str
    changed_paths: tuple[str, ...]
    owner_uid: int
    mode: int
    device: int
    inode: int
    link_count: int
    source_worktree_unmounted: bool
    observed_by: str
    evidence_sha256: str
    schema_version: str = REMATERIALIZATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != REMATERIALIZATION_SCHEMA:
            raise SpoolContractError("rematerialization schema is invalid")
        _require_sha256(self.subject_sha256, "rematerialized subject digest")
        _absolute_normalized_path(self.path, "rematerialized checkout path")
        if self.repository != CANONICAL_REPOSITORY:
            raise SpoolContractError("rematerialized repository is not canonical")
        _require_git_oid(self.base_sha, "rematerialized base SHA")
        _safe_line(self.branch_name, "rematerialized branch", maximum=128)
        if not _CANDIDATE_ID.fullmatch(self.candidate_id):
            raise SpoolContractError("rematerialized candidate ID is invalid")
        for value, label in (
            (self.candidate_sha256, "rematerialized candidate digest"),
            (self.backlog_sha256, "rematerialized backlog digest"),
            (
                self.backlog_authorization_sha256,
                "rematerialized backlog authority digest",
            ),
            (self.patch_sha256, "rematerialized patch digest"),
            (self.patch_bundle_sha256, "rematerialized bundle digest"),
            (self.final_envelope_sha256, "rematerialized envelope digest"),
        ):
            _require_sha256(value, label)
        _safe_changed_paths(self.changed_paths)
        for value, label, minimum in (
            (self.owner_uid, "rematerialized checkout owner", 0),
            (self.mode, "rematerialized checkout mode", 0),
            (self.device, "rematerialized checkout device", 0),
            (self.inode, "rematerialized checkout inode", 1),
            (self.link_count, "rematerialized checkout link count", 2),
        ):
            _bounded_int(value, label, minimum=minimum)
        if type(self.source_worktree_unmounted) is not bool:
            raise SpoolContractError("rematerialized namespace evidence is invalid")
        _safe_actor(self.observed_by, "rematerialization observer")
        _require_sha256(self.evidence_sha256, "rematerialization evidence digest")
        if self.evidence_sha256 != _rematerialized_checkout_digest(self):
            raise SpoolContractError("rematerialization evidence digest does not match")

    @classmethod
    def attest(
        cls,
        path: Path,
        subject: RematerializationSubject,
        *,
        observed_by: str,
        source_worktree_unmounted: bool = True,
    ) -> RematerializedPublisherCheckout:
        identity = DirectoryIdentity.capture(path)
        values = {
            "subject_sha256": subject.sha256,
            "path": identity.path,
            "repository": subject.repository,
            "base_sha": subject.base_sha,
            "branch_name": subject.branch_name,
            "candidate_id": subject.candidate_id,
            "candidate_sha256": subject.candidate_sha256,
            "backlog_sha256": subject.backlog_sha256,
            "backlog_authorization_sha256": subject.backlog_authorization_sha256,
            "patch_sha256": subject.patch_sha256,
            "patch_bundle_sha256": subject.patch_bundle_sha256,
            "final_envelope_sha256": subject.final_envelope_sha256,
            "changed_paths": subject.changed_paths,
            "owner_uid": identity.owner_uid,
            "mode": identity.mode,
            "device": identity.device,
            "inode": identity.inode,
            "link_count": identity.link_count,
            "source_worktree_unmounted": source_worktree_unmounted,
            "observed_by": observed_by,
        }
        digest = _sha256(
            _canonical_json_bytes(_rematerialized_checkout_payload(values))
        )
        return cls(**values, evidence_sha256=digest)


class PublisherCheckoutPort(Protocol):
    """Shell-free port implemented later by the publisher-owned Git adapter."""

    def prepare_base(
        self,
        subject: RematerializationSubject,
        publisher_root: Path,
    ) -> PreparedPublisherCheckout: ...

    def apply_patch_bundle(
        self,
        checkout: PreparedPublisherCheckout,
        patch_bundle: bytes,
        subject: RematerializationSubject,
    ) -> None: ...

    def inspect(
        self,
        path: Path,
        subject: RematerializationSubject,
    ) -> RematerializedPublisherCheckout: ...


class SealedSpoolReader(Protocol):
    """Publisher-visible, read-only projection of the control spool."""

    deployment: SpoolDeploymentEvidence

    def read(self, spool_id: str) -> SealedSpoolRecord: ...


class ImmutableFileSpool:
    """Append-only filesystem spool whose commit marker is written last."""

    def __init__(self, deployment: SpoolDeploymentEvidence) -> None:
        if not isinstance(deployment, SpoolDeploymentEvidence):
            raise SpoolContractError("exact spool deployment evidence is required")
        self.deployment = deployment
        self.root = Path(deployment.spool_root.path)
        self._validate_roots()

    def reserve(self, value: SpoolWrite) -> SpoolReservation:
        if type(value) is not SpoolWrite:
            raise SpoolContractError("exact spool write is required")
        value._validate()
        _validate_source_outside_deployment(value.subject, self.deployment)
        self._validate_roots()
        names = _entry_names(value.spool_id)
        if self._exists(names["sealed"]):
            record = self.read(value.spool_id)
            self._require_same_write(record, value)
            return SpoolReservation(
                value.spool_id, value.request_sha256, value.subject.sha256
            )
        if any(self._exists(name) for name in names.values()):
            raise SpoolConflictError("spool ID is already reserved or incomplete")
        payload = _transition_bytes(
            state=SpoolState.RESERVED,
            spool_id=value.spool_id,
            request_sha256=value.request_sha256,
            subject_sha256=value.subject.sha256,
            deployment_evidence_sha256=self.deployment.evidence_sha256,
        )
        self._write_exclusive(names["reserved"], payload, MAX_TRANSITION_BYTES)
        reread = self._read_artifact(names["reserved"], MAX_TRANSITION_BYTES)
        if reread != payload:
            raise SpoolIntegrityError("spool reservation read-back changed")
        return SpoolReservation(
            value.spool_id, value.request_sha256, value.subject.sha256
        )

    def seal(
        self,
        reservation: SpoolReservation,
        value: SpoolWrite,
    ) -> SealedSpoolRecord:
        if (
            not isinstance(reservation, SpoolReservation)
            or type(value) is not SpoolWrite
        ):
            raise SpoolContractError("exact reservation and spool write are required")
        value._validate()
        _validate_source_outside_deployment(value.subject, self.deployment)
        if (
            reservation.spool_id != value.spool_id
            or reservation.request_sha256 != value.request_sha256
            or reservation.subject_sha256 != value.subject.sha256
        ):
            raise SpoolConflictError("reservation describes another spool write")
        self._validate_roots()
        names = _entry_names(value.spool_id)
        if self._exists(names["sealed"]):
            record = self.read(value.spool_id)
            self._require_same_write(record, value)
            return record
        expected_reservation = _transition_bytes(
            state=SpoolState.RESERVED,
            spool_id=value.spool_id,
            request_sha256=value.request_sha256,
            subject_sha256=value.subject.sha256,
            deployment_evidence_sha256=self.deployment.evidence_sha256,
        )
        observed_reservation = self._read_artifact(
            names["reserved"], MAX_TRANSITION_BYTES
        )
        if observed_reservation != expected_reservation:
            raise SpoolIntegrityError("spool reservation evidence changed")
        if any(self._exists(names[name]) for name in ("envelope", "patch", "manifest")):
            raise SpoolIncompleteError("partial spool files cannot be resumed")
        envelope_file = self._write_exclusive(
            names["envelope"], value.envelope_bytes, MAX_ENVELOPE_BYTES
        )
        patch_file = self._write_exclusive(
            names["patch"], value.patch_bundle, MAX_PATCH_BUNDLE_BYTES
        )
        manifest = SpoolManifest(
            spool_id=value.spool_id,
            subject=value.subject,
            subject_sha256=value.subject.sha256,
            request_sha256=value.request_sha256,
            patch_bundle_sha256=value.patch_bundle_sha256,
            deployment_evidence_sha256=self.deployment.evidence_sha256,
            envelope_file=envelope_file,
            patch_file=patch_file,
        )
        self._write_exclusive(
            names["manifest"], manifest.canonical_bytes, MAX_MANIFEST_BYTES
        )
        sealed = _transition_bytes(
            state=SpoolState.SEALED,
            spool_id=value.spool_id,
            request_sha256=value.request_sha256,
            subject_sha256=value.subject.sha256,
            deployment_evidence_sha256=self.deployment.evidence_sha256,
            manifest_sha256=manifest.sha256,
        )
        self._write_exclusive(names["sealed"], sealed, MAX_TRANSITION_BYTES)
        record = self.read(value.spool_id)
        self._require_same_write(record, value)
        return record

    def put(self, value: SpoolWrite) -> SealedSpoolRecord:
        if type(value) is not SpoolWrite:
            raise SpoolContractError("exact spool write is required")
        value._validate()
        _validate_source_outside_deployment(value.subject, self.deployment)
        names = _entry_names(value.spool_id)
        if self._exists(names["sealed"]):
            record = self.read(value.spool_id)
            self._require_same_write(record, value)
            return record
        return self.seal(self.reserve(value), value)

    def read(self, spool_id: str) -> SealedSpoolRecord:
        _safe_spool_id(spool_id)
        self._validate_roots()
        names = _entry_names(spool_id)
        if not self._exists(names["reserved"]):
            raise SpoolIntegrityError("spool reservation is missing")
        if not self._exists(names["sealed"]):
            raise SpoolIncompleteError("spool entry is reserved but not sealed")
        manifest_bytes = self._read_artifact(names["manifest"], MAX_MANIFEST_BYTES)
        manifest = _parse_manifest(manifest_bytes)
        if manifest.spool_id != spool_id:
            raise SpoolIntegrityError("spool manifest ID does not match filename")
        if manifest.deployment_evidence_sha256 != self.deployment.evidence_sha256:
            raise SpoolIntegrityError("spool manifest belongs to another deployment")
        _validate_source_outside_deployment(manifest.subject, self.deployment)
        sealed = _transition_bytes(
            state=SpoolState.SEALED,
            spool_id=spool_id,
            request_sha256=manifest.request_sha256,
            subject_sha256=manifest.subject_sha256,
            deployment_evidence_sha256=self.deployment.evidence_sha256,
            manifest_sha256=manifest.sha256,
        )
        if self._read_artifact(names["sealed"], MAX_TRANSITION_BYTES) != sealed:
            raise SpoolIntegrityError("spool sealed transition changed")
        reserved = _transition_bytes(
            state=SpoolState.RESERVED,
            spool_id=spool_id,
            request_sha256=manifest.request_sha256,
            subject_sha256=manifest.subject_sha256,
            deployment_evidence_sha256=self.deployment.evidence_sha256,
        )
        if self._read_artifact(names["reserved"], MAX_TRANSITION_BYTES) != reserved:
            raise SpoolIntegrityError("spool reservation transition changed")
        envelope = self._read_artifact(
            names["envelope"], MAX_ENVELOPE_BYTES, manifest.envelope_file
        )
        patch = self._read_artifact(
            names["patch"], MAX_PATCH_BUNDLE_BYTES, manifest.patch_file
        )
        if _subject_from_envelope_bytes(envelope) != manifest.subject:
            raise SpoolIntegrityError("sealed envelope authority changed")
        record = SealedSpoolRecord(manifest, envelope, patch)
        if _request_digest(record) != manifest.request_sha256:
            raise SpoolIntegrityError("sealed request digest does not match")
        self._validate_roots()
        return record

    def _require_same_write(self, record: SealedSpoolRecord, value: SpoolWrite) -> None:
        if (
            record.manifest.request_sha256 != value.request_sha256
            or record.manifest.subject != value.subject
            or record.envelope_bytes != value.envelope_bytes
            or record.patch_bundle != value.patch_bundle
        ):
            raise SpoolConflictError("spool ID replay has different bytes or authority")

    def _validate_roots(self) -> None:
        _validate_directory_identity(
            self.deployment.spool_root,
            expected_mode=_SPOOL_ROOT_MODE,
            label="spool root",
        )

    def _exists(self, name: str) -> bool:
        root_fd = self._open_root()
        try:
            try:
                os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            except FileNotFoundError:
                return False
            except OSError as exc:
                raise SpoolIntegrityError("spool entry cannot be inspected") from exc
            return True
        finally:
            os.close(root_fd)

    def _open_root(self) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            descriptor = os.open(self.root, flags)
        except OSError as exc:
            raise SpoolDeploymentError("spool root cannot be opened safely") from exc
        try:
            _match_directory_stat(
                os.fstat(descriptor),
                self.deployment.spool_root,
                expected_mode=_SPOOL_ROOT_MODE,
                label="spool root",
            )
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    def _write_exclusive(
        self,
        name: str,
        payload: bytes,
        maximum: int,
    ) -> SpoolFileIdentity:
        _bounded_bytes(payload, "spool artifact", maximum=maximum)
        root_fd = self._open_root()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            try:
                descriptor = os.open(
                    name,
                    flags,
                    0o600,
                    dir_fd=root_fd,
                )
            except FileExistsError as exc:
                raise SpoolConflictError(
                    "spool append-only path already exists"
                ) from exc
            except OSError as exc:
                raise SpoolIntegrityError(
                    "spool artifact cannot be created safely"
                ) from exc
            try:
                offset = 0
                while offset < len(payload):
                    written = os.write(descriptor, payload[offset:])
                    if written <= 0:
                        raise SpoolIntegrityError(
                            "spool artifact write made no progress"
                        )
                    offset += written
                os.fchown(
                    descriptor,
                    self.deployment.control_uid,
                    self.deployment.publisher_group_gid,
                )
                os.fchmod(descriptor, _SPOOL_FILE_MODE)
                metadata = os.fstat(descriptor)
                os.fsync(descriptor)
            except Exception:
                os.close(descriptor)
                raise
            os.close(descriptor)
            os.fsync(root_fd)
            identity = _file_identity(name, payload, metadata)
            _validate_file_identity(identity, self.deployment)
            return identity
        finally:
            os.close(root_fd)

    def _read_artifact(
        self,
        name: str,
        maximum: int,
        expected: SpoolFileIdentity | None = None,
    ) -> bytes:
        root_fd = self._open_root()
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            try:
                descriptor = os.open(name, flags, dir_fd=root_fd)
            except FileNotFoundError as exc:
                raise SpoolIncompleteError(
                    "required spool artifact is missing"
                ) from exc
            except OSError as exc:
                raise SpoolIntegrityError(
                    "spool artifact cannot be opened safely"
                ) from exc
            try:
                before = os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode):
                    raise SpoolIntegrityError("spool artifact is not a regular file")
                observed = _file_identity_from_stat(
                    name,
                    before,
                    sha256=(expected.sha256 if expected is not None else "0" * 64),
                )
                _validate_file_identity(observed, self.deployment)
                if expected is not None and observed != expected:
                    raise SpoolIntegrityError("spool artifact inode evidence changed")
                if before.st_size < 1 or before.st_size > maximum:
                    raise SpoolIntegrityError(
                        "spool artifact size is outside its bound"
                    )
                chunks: list[bytes] = []
                remaining = before.st_size
                while remaining:
                    chunk = os.read(descriptor, min(remaining, 64 * 1024))
                    if not chunk:
                        raise SpoolIntegrityError("spool artifact ended early")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if os.read(descriptor, 1):
                    raise SpoolIntegrityError("spool artifact grew while read")
                after = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            if _stat_signature(before) != _stat_signature(after):
                raise SpoolIntegrityError("spool artifact changed while read")
            payload = b"".join(chunks)
            if expected is not None and _sha256(payload) != expected.sha256:
                raise SpoolIntegrityError("spool artifact digest changed")
            return payload
        finally:
            os.close(root_fd)


class PublisherStateStore:
    """Publisher-owned append-only claim and rematerialization evidence.

    This store is deliberately separate from the control-owned inbound spool.
    The publisher may append here, but receives only a read-only spool port.
    """

    def __init__(self, deployment: SpoolDeploymentEvidence) -> None:
        if not isinstance(deployment, SpoolDeploymentEvidence):
            raise SpoolContractError("exact spool deployment evidence is required")
        self.deployment = deployment
        self.root = Path(deployment.publisher_state_root.path)
        self._validate_root()

    def claim(self, record: SealedSpoolRecord) -> RematerializationSubject:
        if not isinstance(record, SealedSpoolRecord):
            raise SpoolContractError("exact sealed spool record is required")
        _validate_source_outside_deployment(record.manifest.subject, self.deployment)
        subject = RematerializationSubject.from_record(record)
        names = _publisher_state_names(subject.spool_id)
        payload = self._claim_bytes(record, subject)
        if self._exists(names["materialized"]) and not self._exists(names["claimed"]):
            raise SpoolIntegrityError(
                "publisher materialization exists without a claim"
            )
        if self._exists(names["claimed"]):
            if self._read(names["claimed"]) != payload:
                raise SpoolConflictError("publisher claim describes another subject")
            return subject
        self._write_exclusive(names["claimed"], payload)
        if self._read(names["claimed"]) != payload:
            raise SpoolIntegrityError("publisher claim read-back changed")
        return subject

    def record_materialization(
        self,
        record: SealedSpoolRecord,
        checkout: RematerializedPublisherCheckout,
    ) -> None:
        subject = self.claim(record)
        _validate_rematerialized_binding(checkout, subject)
        names = _publisher_state_names(subject.spool_id)
        payload = self._materialization_bytes(record, subject, checkout)
        if self._exists(names["materialized"]):
            if self._read(names["materialized"]) != payload:
                raise SpoolConflictError("publisher materialization replay changed")
            return
        self._write_exclusive(names["materialized"], payload)
        if self._read(names["materialized"]) != payload:
            raise SpoolIntegrityError("publisher materialization read-back changed")

    def read_materialization(self, record: SealedSpoolRecord) -> tuple[str, str] | None:
        if not isinstance(record, SealedSpoolRecord):
            raise SpoolContractError("exact sealed spool record is required")
        subject = RematerializationSubject.from_record(record)
        names = _publisher_state_names(subject.spool_id)
        if not self._exists(names["materialized"]):
            return None
        if not self._exists(names["claimed"]):
            raise SpoolIntegrityError(
                "publisher materialization exists without a claim"
            )
        if self._read(names["claimed"]) != self._claim_bytes(record, subject):
            raise SpoolIntegrityError("publisher claim authority changed")
        payload = _parse_transition(
            self._read(names["materialized"]),
            SpoolState.MATERIALIZED,
        )
        expected = {
            "schema_version": SPOOL_TRANSITION_SCHEMA,
            "state": SpoolState.MATERIALIZED.value,
            "spool_id": subject.spool_id,
            "request_sha256": record.manifest.request_sha256,
            "subject_sha256": subject.subject_sha256,
            "deployment_evidence_sha256": self.deployment.evidence_sha256,
            "manifest_sha256": subject.manifest_sha256,
            "rematerialization_subject_sha256": subject.sha256,
            "claim_sha256": _sha256(self._claim_bytes(record, subject)),
            "checkout_evidence_sha256": payload.get("checkout_evidence_sha256"),
            "checkout_path": payload.get("checkout_path"),
        }
        if payload != expected:
            raise SpoolIntegrityError("publisher materialization authority changed")
        digest = payload["checkout_evidence_sha256"]
        path = payload["checkout_path"]
        _require_sha256(digest, "stored checkout evidence digest")
        _absolute_normalized_path(path, "stored checkout path")
        return path, digest

    def _claim_bytes(
        self,
        record: SealedSpoolRecord,
        subject: RematerializationSubject,
    ) -> bytes:
        return _transition_bytes(
            state=SpoolState.CLAIMED,
            spool_id=subject.spool_id,
            request_sha256=record.manifest.request_sha256,
            subject_sha256=subject.subject_sha256,
            deployment_evidence_sha256=self.deployment.evidence_sha256,
            manifest_sha256=subject.manifest_sha256,
            rematerialization_subject_sha256=subject.sha256,
        )

    def _materialization_bytes(
        self,
        record: SealedSpoolRecord,
        subject: RematerializationSubject,
        checkout: RematerializedPublisherCheckout,
    ) -> bytes:
        claim = self._claim_bytes(record, subject)
        return _transition_bytes(
            state=SpoolState.MATERIALIZED,
            spool_id=subject.spool_id,
            request_sha256=record.manifest.request_sha256,
            subject_sha256=subject.subject_sha256,
            deployment_evidence_sha256=self.deployment.evidence_sha256,
            manifest_sha256=subject.manifest_sha256,
            rematerialization_subject_sha256=subject.sha256,
            claim_sha256=_sha256(claim),
            checkout_evidence_sha256=checkout.evidence_sha256,
            checkout_path=checkout.path,
        )

    def _validate_root(self) -> None:
        _validate_directory_identity(
            self.deployment.publisher_state_root,
            expected_mode=_PUBLISHER_ROOT_MODE,
            label="publisher state root",
        )

    def _open_root(self) -> int:
        self._validate_root()
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            descriptor = os.open(self.root, flags)
        except OSError as exc:
            raise SpoolDeploymentError(
                "publisher state root cannot be opened safely"
            ) from exc
        try:
            _match_directory_stat(
                os.fstat(descriptor),
                self.deployment.publisher_state_root,
                expected_mode=_PUBLISHER_ROOT_MODE,
                label="publisher state root",
            )
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    def _exists(self, name: str) -> bool:
        root_fd = self._open_root()
        try:
            try:
                os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            except FileNotFoundError:
                return False
            except OSError as exc:
                raise SpoolIntegrityError(
                    "publisher state cannot be inspected"
                ) from exc
            return True
        finally:
            os.close(root_fd)

    def _write_exclusive(self, name: str, payload: bytes) -> None:
        _bounded_bytes(payload, "publisher state", maximum=MAX_TRANSITION_BYTES)
        root_fd = self._open_root()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            try:
                descriptor = os.open(name, flags, 0o600, dir_fd=root_fd)
            except FileExistsError as exc:
                raise SpoolConflictError(
                    "publisher append-only state already exists"
                ) from exc
            except OSError as exc:
                raise SpoolIntegrityError(
                    "publisher state cannot be created safely"
                ) from exc
            try:
                offset = 0
                while offset < len(payload):
                    written = os.write(descriptor, payload[offset:])
                    if written <= 0:
                        raise SpoolIntegrityError(
                            "publisher state write made no progress"
                        )
                    offset += written
                os.fchown(
                    descriptor,
                    self.deployment.publisher_uid,
                    self.deployment.publisher_state_root.group_gid,
                )
                os.fchmod(descriptor, _PUBLISHER_STATE_FILE_MODE)
                os.fsync(descriptor)
            except Exception:
                os.close(descriptor)
                raise
            os.close(descriptor)
            os.fsync(root_fd)
        finally:
            os.close(root_fd)

    def _read(self, name: str) -> bytes:
        root_fd = self._open_root()
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            try:
                descriptor = os.open(name, flags, dir_fd=root_fd)
            except FileNotFoundError as exc:
                raise SpoolIncompleteError("publisher state is missing") from exc
            except OSError as exc:
                raise SpoolIntegrityError(
                    "publisher state cannot be opened safely"
                ) from exc
            try:
                before = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_uid != self.deployment.publisher_uid
                    or before.st_gid != self.deployment.publisher_state_root.group_gid
                    or stat.S_IMODE(before.st_mode) != _PUBLISHER_STATE_FILE_MODE
                    or before.st_nlink != 1
                    or before.st_size < 1
                    or before.st_size > MAX_TRANSITION_BYTES
                ):
                    raise SpoolIntegrityError(
                        "publisher state owner, mode, links, or size are unsafe"
                    )
                chunks: list[bytes] = []
                remaining = before.st_size
                while remaining:
                    chunk = os.read(descriptor, min(remaining, 64 * 1024))
                    if not chunk:
                        raise SpoolIntegrityError("publisher state ended early")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if os.read(descriptor, 1):
                    raise SpoolIntegrityError("publisher state grew while read")
                after = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            if _stat_signature(before) != _stat_signature(after):
                raise SpoolIntegrityError("publisher state changed while read")
            return b"".join(chunks)
        finally:
            os.close(root_fd)


class PublisherRematerializer:
    """Rebuild a publisher checkout from sealed bytes, never the patcher tree."""

    def __init__(
        self,
        *,
        spool: SealedSpoolReader,
        state_store: PublisherStateStore,
        checkout_port: PublisherCheckoutPort,
        unattended: bool,
    ) -> None:
        deployment = getattr(spool, "deployment", None)
        reader = getattr(spool, "read", None)
        if not isinstance(deployment, SpoolDeploymentEvidence) or not callable(reader):
            raise SpoolContractError("read-only sealed spool port is required")
        if not isinstance(state_store, PublisherStateStore):
            raise SpoolContractError("exact publisher state store is required")
        if state_store.deployment != deployment:
            raise SpoolContractError(
                "spool reader and publisher state use different deployment evidence"
            )
        if type(unattended) is not bool:
            raise SpoolContractError("rematerialization mode must be explicit")
        if unattended:
            deployment.require_unattended_ready()
        self._spool = spool
        self._state = state_store
        self._deployment = deployment
        self._checkout_port = checkout_port
        self._validate_publisher_root()

    def rematerialize(self, spool_id: str) -> RematerializedPublisherCheckout:
        self._validate_publisher_root()
        record = self._spool.read(spool_id)
        _validate_source_outside_deployment(record.manifest.subject, self._deployment)
        subject = self._state.claim(record)
        prior = self._state.read_materialization(record)
        if prior is not None:
            path, evidence_sha256 = prior
            observed = self._call_inspect(Path(path), subject)
            self._validate_checkout(observed, subject)
            if observed.evidence_sha256 != evidence_sha256:
                raise RematerializationError(
                    "materialized checkout read-back evidence changed"
                )
            self._require_same_record(record)
            return observed

        try:
            prepared = self._checkout_port.prepare_base(
                subject, Path(self._deployment.publisher_root.path)
            )
        except Exception as exc:
            raise RematerializationError("publisher base preparation failed") from exc
        self._validate_prepared(prepared, subject)
        self._require_same_record(record)
        try:
            self._checkout_port.apply_patch_bundle(
                prepared, bytes(record.patch_bundle), subject
            )
        except Exception as exc:
            raise RematerializationError("publisher patch application failed") from exc
        observed = self._call_inspect(Path(prepared.path), subject)
        self._validate_checkout(observed, subject, prepared=prepared)
        self._require_same_record(record)
        self._state.record_materialization(record, observed)
        reread = self._call_inspect(Path(observed.path), subject)
        self._validate_checkout(reread, subject, prepared=prepared)
        if reread != observed:
            raise RematerializationError("publisher checkout changed after sealing")
        self._require_same_record(record)
        stored = self._state.read_materialization(record)
        if stored != (observed.path, observed.evidence_sha256):
            raise RematerializationError("materialization marker read-back changed")
        return reread

    def _call_inspect(
        self, path: Path, subject: RematerializationSubject
    ) -> RematerializedPublisherCheckout:
        try:
            return self._checkout_port.inspect(path, subject)
        except Exception as exc:
            raise RematerializationError(
                "publisher checkout inspection failed"
            ) from exc

    def _require_same_record(self, expected: SealedSpoolRecord) -> None:
        if self._spool.read(expected.manifest.spool_id) != expected:
            raise RematerializationError(
                "sealed spool changed during rematerialization"
            )

    def _validate_prepared(
        self,
        value: PreparedPublisherCheckout,
        subject: RematerializationSubject,
    ) -> None:
        if not isinstance(value, PreparedPublisherCheckout):
            raise RematerializationError("prepared checkout evidence type is invalid")
        if (
            value.subject_sha256 != subject.sha256
            or value.repository != subject.repository
            or value.base_sha != subject.base_sha
            or value.branch_name != subject.branch_name
            or not value.clean_base
            or not value.publisher_owned
            or not value.source_worktree_unmounted
        ):
            raise RematerializationError("prepared checkout authority does not match")
        self._validate_checkout_path(value, subject)

    def _validate_checkout(
        self,
        value: RematerializedPublisherCheckout,
        subject: RematerializationSubject,
        *,
        prepared: PreparedPublisherCheckout | None = None,
    ) -> None:
        if not isinstance(value, RematerializedPublisherCheckout):
            raise RematerializationError("rematerialized evidence type is invalid")
        _validate_rematerialized_binding(value, subject)
        self._validate_checkout_path(value, subject)
        if prepared is not None and (
            value.path != prepared.path
            or value.device != prepared.device
            or value.inode != prepared.inode
        ):
            raise RematerializationError("publisher checkout inode was swapped")

    def _validate_checkout_path(
        self,
        value: PreparedPublisherCheckout | RematerializedPublisherCheckout,
        subject: RematerializationSubject,
    ) -> None:
        self._validate_publisher_root()
        target = Path(value.path)
        publisher_root = Path(self._deployment.publisher_root.path)
        source = Path(subject.source_worktree_path)
        try:
            resolved = target.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise RematerializationError("publisher checkout does not resolve") from exc
        if resolved != target or target == publisher_root:
            raise RematerializationError("publisher checkout path is not canonical")
        try:
            target.relative_to(publisher_root)
        except ValueError as exc:
            raise RematerializationError(
                "publisher checkout escaped its owned root"
            ) from exc
        if _paths_overlap(target, source):
            raise RematerializationError("publisher checkout shares patcher worktree")
        try:
            if source.exists() and os.path.samefile(target, source):
                raise RematerializationError(
                    "publisher checkout is the patcher worktree inode"
                )
        except OSError as exc:
            raise RematerializationError(
                "patcher worktree alias cannot be audited"
            ) from exc
        metadata = target.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != _PUBLISHER_ROOT_MODE
            or metadata.st_uid != self._deployment.publisher_uid
            or metadata.st_dev != value.device
            or metadata.st_ino != value.inode
            or metadata.st_nlink != value.link_count
            or value.mode != _PUBLISHER_ROOT_MODE
            or value.owner_uid != self._deployment.publisher_uid
        ):
            raise RematerializationError(
                "publisher checkout ownership, mode, or inode is unsafe"
            )

    def _validate_publisher_root(self) -> None:
        _validate_directory_identity(
            self._deployment.publisher_root,
            expected_mode=_PUBLISHER_ROOT_MODE,
            label="publisher root",
        )


def _validate_rematerialized_binding(
    value: RematerializedPublisherCheckout,
    subject: RematerializationSubject,
) -> None:
    if (
        value.subject_sha256 != subject.sha256
        or value.repository != subject.repository
        or value.base_sha != subject.base_sha
        or value.branch_name != subject.branch_name
        or value.candidate_id != subject.candidate_id
        or value.candidate_sha256 != subject.candidate_sha256
        or value.backlog_sha256 != subject.backlog_sha256
        or value.backlog_authorization_sha256 != subject.backlog_authorization_sha256
        or value.patch_sha256 != subject.patch_sha256
        or value.patch_bundle_sha256 != subject.patch_bundle_sha256
        or value.final_envelope_sha256 != subject.final_envelope_sha256
        or value.changed_paths != subject.changed_paths
        or not value.source_worktree_unmounted
    ):
        raise RematerializationError("rematerialized checkout authority does not match")


def _subject_from_envelope_bytes(payload: bytes) -> SpoolSubject:
    _bounded_bytes(payload, "finalized envelope", maximum=MAX_ENVELOPE_BYTES)
    envelope = _reconstruct_finalized_envelope(payload)
    return SpoolSubject(
        run_id=envelope.run_id,
        run_date=envelope.run_date,
        repository=envelope.repository,
        base_sha=envelope.base_sha,
        branch_name=envelope.branch_name,
        candidate_id=envelope.candidate_id,
        candidate_slug=envelope.candidate_slug,
        candidate_sha256=envelope.candidate_sha256,
        backlog_sha256=envelope.backlog_sha256,
        backlog_authorization_sha256=envelope.backlog_authorization_sha256,
        run_state_sha256=envelope.run_state_sha256,
        verification_subject_sha256=envelope.verification_subject_sha256,
        patch_sha256=envelope.guard_patch_sha256,
        verified_head_sha256=envelope.head_sha256,
        final_envelope_sha256=_sha256(payload),
        source_worktree_path=envelope.run_worktree_path,
        changed_paths=envelope.changed_paths,
    )


def _reconstruct_finalized_envelope(payload: bytes) -> FinalizedVerifierEnvelope:
    document = _parse_canonical_object(payload, "finalized envelope")
    expected_fields = {
        item.name for item in dataclass_fields(FinalizedVerifierEnvelope)
    }
    if set(document) != expected_fields:
        raise SpoolContractError("finalized envelope fields are not exact")

    tuple_fields = {
        "backlog_candidate_bindings",
        "acceptance",
        "allowed_paths",
        "changed_paths",
        "validation_profile_ids",
    }
    values: dict[str, object] = dict(document)
    for name in tuple_fields:
        raw = document[name]
        if not isinstance(raw, list) or any(type(item) is not str for item in raw):
            raise SpoolContractError(
                f"finalized envelope {name} must be a string array"
            )
        values[name] = tuple(raw)

    checks_raw = document["checks"]
    if not isinstance(checks_raw, list):
        raise SpoolContractError("finalized envelope checks must be an array")
    check_fields = {item.name for item in dataclass_fields(FinalizedVerificationCheck)}
    checks: list[FinalizedVerificationCheck] = []
    for raw in checks_raw:
        if not isinstance(raw, dict) or set(raw) != check_fields:
            raise SpoolContractError(
                "finalized verification check fields are not exact"
            )
        try:
            checks.append(FinalizedVerificationCheck(**raw))
        except (TypeError, ValueError) as exc:
            raise SpoolContractError("finalized verification check is invalid") from exc
    values["checks"] = tuple(checks)

    integer_fields = {
        "backlog_manifest_revision",
        "risk_tier",
        "source_manifest_revision",
    }
    boolean_fields = {
        "finalized",
        "guard_ok",
        "final_guard_ok",
        "mutation_detected",
        "isolation_network_isolated",
        "isolation_credentials_absent",
    }
    optional_string_fields = {
        "candidate_not_before",
        "candidate_expires_on",
        "source_issue_url",
    }
    for name in integer_fields:
        if type(document[name]) is not int:
            raise SpoolContractError(f"finalized envelope {name} is not an integer")
    for name in boolean_fields:
        if type(document[name]) is not bool:
            raise SpoolContractError(f"finalized envelope {name} is not boolean")
    for name in optional_string_fields:
        if document[name] is not None and type(document[name]) is not str:
            raise SpoolContractError(f"finalized envelope {name} is not optional text")
    scalar_string_fields = (
        expected_fields
        - tuple_fields
        - integer_fields
        - (boolean_fields | optional_string_fields | {"checks"})
    )
    for name in scalar_string_fields:
        value = document[name]
        if type(value) is not str or len(value.encode("utf-8", "strict")) > 4096:
            raise SpoolContractError(f"finalized envelope {name} is not bounded text")
        if _CONTROL.search(value):
            raise SpoolContractError(f"finalized envelope {name} has control bytes")

    try:
        reconstructed = FinalizedVerifierEnvelope(**values)
    except (TypeError, ValueError) as exc:
        raise SpoolContractError("finalized envelope reconstruction failed") from exc
    if reconstructed.canonical_bytes != payload:
        raise SpoolContractError("reconstructed finalized envelope bytes changed")
    _validate_reconstructed_envelope(reconstructed)
    return reconstructed


def _validate_reconstructed_envelope(envelope: FinalizedVerifierEnvelope) -> None:
    if (
        envelope.schema_version != FINALIZED_ENVELOPE_SCHEMA
        or envelope.finalized is not True
        or envelope.repository != CANONICAL_REPOSITORY
        or envelope.run_remote != "origin"
        or envelope.run_remote_branch != "main"
        or envelope.run_lifecycle != "worktree_ready"
        or envelope.run_branch_disposition != "created"
        or envelope.run_branch_head_sha != envelope.base_sha
        or envelope.run_observed_remote_sha != envelope.base_sha
        or envelope.run_publication_state not in {"unknown", "none"}
    ):
        raise SpoolContractError("finalized envelope run authority is not publishable")
    run_date = _canonical_date(envelope.run_date)
    _require_git_oid(envelope.base_sha, "finalized envelope base SHA")
    if envelope.run_id != f"{run_date}/{envelope.repository}@{envelope.base_sha}":
        raise SpoolContractError("finalized envelope run ID does not match")
    if envelope.branch_name != v1_daily_branch_name(
        run_date, envelope.candidate_slug, envelope.base_sha
    ):
        raise SpoolContractError("finalized envelope branch is not canonical")
    if (
        envelope.guard_ok is not True
        or envelope.final_guard_ok is not True
        or envelope.mutation_detected is not False
        or envelope.isolation_network_isolated is not True
        or envelope.isolation_credentials_absent is not True
        or envelope.guard_patch_sha256 != envelope.final_guard_patch_sha256
        or envelope.isolation_patch_sha256 != envelope.guard_patch_sha256
        or envelope.isolation_subject_sha256 != envelope.verification_subject_sha256
    ):
        raise SpoolContractError("finalized envelope verification did not pass")

    try:
        source = CandidateSource(
            kind=envelope.source_kind,
            manifest_revision=envelope.source_manifest_revision,
            approved_by=envelope.source_approved_by,
            issue_url=envelope.source_issue_url,
        )
        candidate = Candidate(
            candidate_id=envelope.candidate_id,
            title=envelope.candidate_title,
            risk_tier=envelope.risk_tier,
            allowed_paths=envelope.allowed_paths,
            acceptance=envelope.acceptance,
            validation_profiles=envelope.validation_profile_ids,
            expected_external_side_effects=envelope.expected_external_side_effects,
            source=source,
            state=envelope.candidate_state,
            not_before=(
                dt.date.fromisoformat(envelope.candidate_not_before)
                if envelope.candidate_not_before
                else None
            ),
            expires_on=(
                dt.date.fromisoformat(envelope.candidate_expires_on)
                if envelope.candidate_expires_on
                else None
            ),
        )
        enforce_v1_candidate_policy(candidate)
    except (TypeError, ValueError) as exc:
        raise SpoolContractError("finalized candidate authority is invalid") from exc
    if (
        candidate_authorization_digest(candidate) != envelope.candidate_sha256
        or not candidate.eligible_on(dt.date.fromisoformat(run_date))
        or envelope.source_manifest_revision != envelope.backlog_manifest_revision
        or envelope.source_approved_by != envelope.backlog_approved_by
        or any(
            not any(
                path_matches_pattern(path, pattern)
                for pattern in envelope.allowed_paths
            )
            for path in envelope.changed_paths
        )
    ):
        raise SpoolContractError("finalized candidate cross-binding failed")

    try:
        run_state = RunState(
            key=RunKey(run_date, envelope.repository, envelope.base_sha),
            candidate_id=envelope.candidate_id,
            candidate_slug=envelope.candidate_slug,
            backlog_sha256=envelope.backlog_sha256,
            candidate_sha256=envelope.candidate_sha256,
            remote=envelope.run_remote,
            remote_branch=envelope.run_remote_branch,
            branch_name=envelope.branch_name,
            lifecycle=envelope.run_lifecycle,
            branch_disposition=envelope.run_branch_disposition,
            branch_head_sha=envelope.run_branch_head_sha,
            worktree_path=envelope.run_worktree_path,
            observed_remote_sha=envelope.run_observed_remote_sha,
            publication=PublicationSnapshot(state=envelope.run_publication_state),
        )
    except (TypeError, ValueError) as exc:
        raise SpoolContractError("finalized run state is invalid") from exc
    if state_digest(run_state) != envelope.run_state_sha256:
        raise SpoolContractError("finalized run state digest does not match")
    try:
        subject = VerificationSubject(
            run_id=envelope.run_id,
            run_date=run_date,
            repository=envelope.repository,
            base_sha=envelope.base_sha,
            branch_name=envelope.branch_name,
            worktree_path=envelope.run_worktree_path,
            candidate_id=envelope.candidate_id,
            candidate_slug=envelope.candidate_slug,
            backlog_sha256=envelope.backlog_sha256,
            backlog_authorization_sha256=envelope.backlog_authorization_sha256,
            candidate_sha256=envelope.candidate_sha256,
            run_state_sha256=envelope.run_state_sha256,
        )
    except (TypeError, ValueError) as exc:
        raise SpoolContractError("finalized verification subject is invalid") from exc
    if subject.sha256 != envelope.verification_subject_sha256:
        raise SpoolContractError("finalized verification subject digest does not match")
    expected_check_subject = verification_check_subject_digest(
        subject.sha256, envelope.guard_patch_sha256
    )
    if envelope.check_subject_sha256 != expected_check_subject:
        raise SpoolContractError("finalized check subject digest does not match")
    if tuple(check.command_id for check in envelope.checks) != (
        "git-diff-check",
        *envelope.validation_profile_ids,
    ) or any(
        check.subject_sha256 != expected_check_subject
        or check.exit_code != 0
        or check.timed_out
        for check in envelope.checks
    ):
        raise SpoolContractError("finalized checks are not exact successful profiles")
    if envelope.head_sha256 != verified_head_digest(
        envelope.base_sha,
        envelope.guard_patch_sha256,
        envelope.changed_paths,
    ):
        raise SpoolContractError("finalized verified-head digest does not match")
    if envelope.isolation_evidence_sha256 != isolation_evidence_digest(
        subject_sha256=envelope.isolation_subject_sha256,
        patch_sha256=envelope.isolation_patch_sha256,
        network_isolated=envelope.isolation_network_isolated,
        credentials_absent=envelope.isolation_credentials_absent,
        observed_by=envelope.isolation_verified_by,
    ):
        raise SpoolContractError("finalized isolation evidence digest does not match")


def _parse_manifest(payload: bytes) -> SpoolManifest:
    document = _parse_canonical_object(payload, "spool manifest")
    expected = {
        "schema_version",
        "state",
        "spool_id",
        "subject",
        "subject_sha256",
        "request_sha256",
        "patch_bundle_sha256",
        "deployment_evidence_sha256",
        "envelope_file",
        "patch_file",
    }
    if set(document) != expected:
        raise SpoolIntegrityError("spool manifest fields are not exact")
    subject_raw = document["subject"]
    if not isinstance(subject_raw, dict):
        raise SpoolIntegrityError("spool manifest subject is not an object")
    subject = _subject_from_payload(subject_raw)
    try:
        return SpoolManifest(
            schema_version=document["schema_version"],
            state=document["state"],
            spool_id=document["spool_id"],
            subject=subject,
            subject_sha256=document["subject_sha256"],
            request_sha256=document["request_sha256"],
            patch_bundle_sha256=document["patch_bundle_sha256"],
            deployment_evidence_sha256=document["deployment_evidence_sha256"],
            envelope_file=_file_identity_from_payload(document["envelope_file"]),
            patch_file=_file_identity_from_payload(document["patch_file"]),
        )
    except (TypeError, ValueError) as exc:
        raise SpoolIntegrityError("spool manifest is invalid") from exc


def _subject_from_payload(value: dict[str, object]) -> SpoolSubject:
    expected = set(_subject_payload_keys())
    if set(value) != expected:
        raise SpoolIntegrityError("spool subject fields are not exact")
    changed = value["changed_paths"]
    if not isinstance(changed, list) or any(
        not isinstance(item, str) for item in changed
    ):
        raise SpoolIntegrityError("spool subject changed paths are invalid")
    try:
        return SpoolSubject(
            run_id=value["run_id"],
            run_date=value["run_date"],
            repository=value["repository"],
            base_sha=value["base_sha"],
            branch_name=value["branch_name"],
            candidate_id=value["candidate_id"],
            candidate_slug=value["candidate_slug"],
            candidate_sha256=value["candidate_sha256"],
            backlog_sha256=value["backlog_sha256"],
            backlog_authorization_sha256=value["backlog_authorization_sha256"],
            run_state_sha256=value["run_state_sha256"],
            verification_subject_sha256=value["verification_subject_sha256"],
            patch_sha256=value["patch_sha256"],
            verified_head_sha256=value["verified_head_sha256"],
            final_envelope_sha256=value["final_envelope_sha256"],
            source_worktree_path=value["source_worktree_path"],
            changed_paths=tuple(changed),
        )
    except (TypeError, ValueError) as exc:
        raise SpoolIntegrityError("spool subject is invalid") from exc


def _file_identity_from_payload(value: object) -> SpoolFileIdentity:
    if not isinstance(value, dict) or set(value) != {
        "name",
        "sha256",
        "size",
        "device",
        "inode",
        "owner_uid",
        "group_gid",
        "mode",
        "link_count",
    }:
        raise SpoolIntegrityError("spool file identity fields are not exact")
    try:
        return SpoolFileIdentity(**value)
    except (TypeError, ValueError) as exc:
        raise SpoolIntegrityError("spool file identity is invalid") from exc


def _parse_transition(payload: bytes, state: SpoolState) -> dict[str, object]:
    document = _parse_canonical_object(payload, "spool transition")
    if (
        document.get("schema_version") != SPOOL_TRANSITION_SCHEMA
        or document.get("state") != state.value
    ):
        raise SpoolIntegrityError("spool transition schema or state changed")
    return document


def _transition_bytes(
    *,
    state: SpoolState,
    spool_id: str,
    request_sha256: str,
    subject_sha256: str,
    deployment_evidence_sha256: str,
    manifest_sha256: str | None = None,
    rematerialization_subject_sha256: str | None = None,
    claim_sha256: str | None = None,
    checkout_evidence_sha256: str | None = None,
    checkout_path: str | None = None,
) -> bytes:
    payload: dict[str, object] = {
        "schema_version": SPOOL_TRANSITION_SCHEMA,
        "state": state.value,
        "spool_id": spool_id,
        "request_sha256": request_sha256,
        "subject_sha256": subject_sha256,
        "deployment_evidence_sha256": deployment_evidence_sha256,
    }
    if manifest_sha256 is not None:
        payload["manifest_sha256"] = manifest_sha256
    if rematerialization_subject_sha256 is not None:
        payload["rematerialization_subject_sha256"] = rematerialization_subject_sha256
    if claim_sha256 is not None:
        payload["claim_sha256"] = claim_sha256
    if checkout_evidence_sha256 is not None:
        payload["checkout_evidence_sha256"] = checkout_evidence_sha256
    if checkout_path is not None:
        payload["checkout_path"] = checkout_path
    return _canonical_json_bytes(payload)


def _request_digest(record: SealedSpoolRecord) -> str:
    return _sha256(
        _canonical_json_bytes(
            {
                "schema_version": "vista.world.daily-maintainer.spool-request.v1",
                "spool_id": record.manifest.spool_id,
                "subject": _subject_payload(record.manifest.subject),
                "subject_sha256": record.manifest.subject.sha256,
                "envelope_bytes": len(record.envelope_bytes),
                "patch_bundle_bytes": len(record.patch_bundle),
                "patch_bundle_sha256": _sha256(record.patch_bundle),
            }
        )
    )


def _entry_names(spool_id: str) -> dict[str, str]:
    _safe_spool_id(spool_id)
    return {
        "reserved": _artifact_name(spool_id, "reserved.json"),
        "envelope": _artifact_name(spool_id, "envelope.json"),
        "patch": _artifact_name(spool_id, "patch.bundle"),
        "manifest": _artifact_name(spool_id, "manifest.json"),
        "sealed": _artifact_name(spool_id, "sealed.json"),
    }


def _publisher_state_names(spool_id: str) -> dict[str, str]:
    _safe_spool_id(spool_id)
    return {
        "claimed": _artifact_name(spool_id, "claimed.json"),
        "materialized": _artifact_name(spool_id, "materialized.json"),
    }


def _artifact_name(spool_id: str, suffix: str) -> str:
    _safe_spool_id(spool_id)
    if not re.fullmatch(r"[a-z.]+", suffix):
        raise SpoolContractError("spool suffix is invalid")
    return f"{spool_id}.{suffix}"


def _file_identity(
    name: str, payload: bytes, metadata: os.stat_result
) -> SpoolFileIdentity:
    return SpoolFileIdentity(
        name=name,
        sha256=_sha256(payload),
        size=len(payload),
        device=metadata.st_dev,
        inode=metadata.st_ino,
        owner_uid=metadata.st_uid,
        group_gid=metadata.st_gid,
        mode=stat.S_IMODE(metadata.st_mode),
        link_count=metadata.st_nlink,
    )


def _file_identity_from_stat(
    name: str,
    metadata: os.stat_result,
    *,
    sha256: str,
) -> SpoolFileIdentity:
    return SpoolFileIdentity(
        name=name,
        sha256=sha256,
        size=metadata.st_size,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        owner_uid=metadata.st_uid,
        group_gid=metadata.st_gid,
        mode=stat.S_IMODE(metadata.st_mode),
        link_count=metadata.st_nlink,
    )


def _validate_file_identity(
    identity: SpoolFileIdentity,
    deployment: SpoolDeploymentEvidence,
) -> None:
    if (
        identity.owner_uid != deployment.control_uid
        or identity.group_gid != deployment.publisher_group_gid
        or identity.mode != _SPOOL_FILE_MODE
        or identity.link_count != 1
    ):
        raise SpoolIntegrityError("spool file owner, group, mode, or links are unsafe")


def _validate_directory_identity(
    identity: DirectoryIdentity,
    *,
    expected_mode: int,
    label: str,
) -> None:
    path = Path(identity.path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SpoolDeploymentError(f"{label} cannot be opened safely") from exc
    try:
        _match_directory_stat(
            os.fstat(descriptor), identity, expected_mode=expected_mode, label=label
        )
    finally:
        os.close(descriptor)


def _attest_initially_empty_directory(
    identity: DirectoryIdentity,
    *,
    expected_mode: int,
    label: str,
) -> None:
    """Take the one-time empty-root provisioning snapshot required by T13."""

    path = Path(identity.path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SpoolDeploymentError(f"{label} cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        _match_directory_stat(
            before,
            identity,
            expected_mode=expected_mode,
            label=label,
        )
        try:
            with os.scandir(descriptor) as entries:
                first_entry = next(entries, None)
        except OSError as exc:
            raise SpoolDeploymentError(
                f"{label} emptiness cannot be inspected safely"
            ) from exc
        after = os.fstat(descriptor)
        if _stat_signature(before) != _stat_signature(after):
            raise SpoolDeploymentError(
                f"{label} changed during initial emptiness attestation"
            )
        if first_entry is not None:
            raise SpoolDeploymentError(
                f"{label} is not initially empty; nested roots are forbidden"
            )
    finally:
        os.close(descriptor)


def _match_directory_stat(
    metadata: os.stat_result,
    identity: DirectoryIdentity,
    *,
    expected_mode: int,
    label: str,
) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_dev != identity.device
        or metadata.st_ino != identity.inode
        or metadata.st_uid != identity.owner_uid
        or metadata.st_gid != identity.group_gid
        or stat.S_IMODE(metadata.st_mode) != identity.mode
        or identity.mode != expected_mode
        or metadata.st_nlink < 2
    ):
        raise SpoolDeploymentError(f"{label} identity, owner, or mode changed")


def _deployment_digest(value: SpoolDeploymentEvidence) -> str:
    payload = _deployment_payload(
        {
            "spool_root": value.spool_root,
            "publisher_root": value.publisher_root,
            "publisher_state_root": value.publisher_state_root,
            "control_uid": value.control_uid,
            "publisher_uid": value.publisher_uid,
            "patcher_uid": value.patcher_uid,
            "publisher_group_gid": value.publisher_group_gid,
            "roots_initially_empty": value.roots_initially_empty,
            "distinct_uids_enforced": value.distinct_uids_enforced,
            "publisher_spool_read_only": value.publisher_spool_read_only,
            "patcher_spool_unmounted": value.patcher_spool_unmounted,
            "patcher_publisher_root_unmounted": value.patcher_publisher_root_unmounted,
            "patcher_publisher_state_root_unmounted": (
                value.patcher_publisher_state_root_unmounted
            ),
            "publisher_patcher_root_unmounted": value.publisher_patcher_root_unmounted,
            "attested_by": value.attested_by,
        }
    )
    return _sha256(_canonical_json_bytes(payload))


def _deployment_payload(values: dict[str, object]) -> dict[str, object]:
    spool_root = values["spool_root"]
    publisher_root = values["publisher_root"]
    publisher_state_root = values["publisher_state_root"]
    if (
        not isinstance(spool_root, DirectoryIdentity)
        or not isinstance(publisher_root, DirectoryIdentity)
        or not isinstance(publisher_state_root, DirectoryIdentity)
    ):
        raise SpoolContractError("deployment root identity is invalid")
    return {
        "schema_version": "vista.world.daily-maintainer.spool-deployment.v1",
        "spool_root": _directory_payload(spool_root),
        "publisher_root": _directory_payload(publisher_root),
        "publisher_state_root": _directory_payload(publisher_state_root),
        "control_uid": values["control_uid"],
        "publisher_uid": values["publisher_uid"],
        "patcher_uid": values["patcher_uid"],
        "publisher_group_gid": values["publisher_group_gid"],
        "roots_initially_empty": values["roots_initially_empty"],
        "distinct_uids_enforced": values["distinct_uids_enforced"],
        "publisher_spool_read_only": values["publisher_spool_read_only"],
        "patcher_spool_unmounted": values["patcher_spool_unmounted"],
        "patcher_publisher_root_unmounted": values["patcher_publisher_root_unmounted"],
        "patcher_publisher_state_root_unmounted": values[
            "patcher_publisher_state_root_unmounted"
        ],
        "publisher_patcher_root_unmounted": values["publisher_patcher_root_unmounted"],
        "attested_by": values["attested_by"],
    }


def _directory_payload(value: DirectoryIdentity) -> dict[str, object]:
    return {
        "path": value.path,
        "owner_uid": value.owner_uid,
        "group_gid": value.group_gid,
        "mode": value.mode,
        "device": value.device,
        "inode": value.inode,
        "link_count": value.link_count,
    }


def _subject_payload(value: SpoolSubject) -> dict[str, object]:
    return {
        "run_id": value.run_id,
        "run_date": value.run_date,
        "repository": value.repository,
        "base_sha": value.base_sha,
        "branch_name": value.branch_name,
        "candidate_id": value.candidate_id,
        "candidate_slug": value.candidate_slug,
        "candidate_sha256": value.candidate_sha256,
        "backlog_sha256": value.backlog_sha256,
        "backlog_authorization_sha256": value.backlog_authorization_sha256,
        "run_state_sha256": value.run_state_sha256,
        "verification_subject_sha256": value.verification_subject_sha256,
        "patch_sha256": value.patch_sha256,
        "verified_head_sha256": value.verified_head_sha256,
        "final_envelope_sha256": value.final_envelope_sha256,
        "source_worktree_path": value.source_worktree_path,
        "changed_paths": list(value.changed_paths),
    }


def _subject_payload_keys() -> tuple[str, ...]:
    return (
        "run_id",
        "run_date",
        "repository",
        "base_sha",
        "branch_name",
        "candidate_id",
        "candidate_slug",
        "candidate_sha256",
        "backlog_sha256",
        "backlog_authorization_sha256",
        "run_state_sha256",
        "verification_subject_sha256",
        "patch_sha256",
        "verified_head_sha256",
        "final_envelope_sha256",
        "source_worktree_path",
        "changed_paths",
    )


def _manifest_payload(value: SpoolManifest) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "state": value.state,
        "spool_id": value.spool_id,
        "subject": _subject_payload(value.subject),
        "subject_sha256": value.subject_sha256,
        "request_sha256": value.request_sha256,
        "patch_bundle_sha256": value.patch_bundle_sha256,
        "deployment_evidence_sha256": value.deployment_evidence_sha256,
        "envelope_file": _file_payload(value.envelope_file),
        "patch_file": _file_payload(value.patch_file),
    }


def _file_payload(value: SpoolFileIdentity) -> dict[str, object]:
    return {
        "name": value.name,
        "sha256": value.sha256,
        "size": value.size,
        "device": value.device,
        "inode": value.inode,
        "owner_uid": value.owner_uid,
        "group_gid": value.group_gid,
        "mode": value.mode,
        "link_count": value.link_count,
    }


def _rematerialization_subject_payload(
    value: RematerializationSubject,
) -> dict[str, object]:
    return {
        "schema_version": "vista.world.daily-maintainer.rematerialization-subject.v1",
        "spool_id": value.spool_id,
        "manifest_sha256": value.manifest_sha256,
        "subject_sha256": value.subject_sha256,
        "patch_bundle_sha256": value.patch_bundle_sha256,
        "run_id": value.run_id,
        "repository": value.repository,
        "base_sha": value.base_sha,
        "branch_name": value.branch_name,
        "candidate_id": value.candidate_id,
        "candidate_sha256": value.candidate_sha256,
        "backlog_sha256": value.backlog_sha256,
        "backlog_authorization_sha256": value.backlog_authorization_sha256,
        "patch_sha256": value.patch_sha256,
        "final_envelope_sha256": value.final_envelope_sha256,
        "source_worktree_path": value.source_worktree_path,
        "changed_paths": list(value.changed_paths),
    }


def _prepared_checkout_digest(value: PreparedPublisherCheckout) -> str:
    return _sha256(
        _canonical_json_bytes(
            _prepared_checkout_payload(
                {
                    "subject_sha256": value.subject_sha256,
                    "path": value.path,
                    "repository": value.repository,
                    "base_sha": value.base_sha,
                    "branch_name": value.branch_name,
                    "owner_uid": value.owner_uid,
                    "mode": value.mode,
                    "device": value.device,
                    "inode": value.inode,
                    "link_count": value.link_count,
                    "clean_base": value.clean_base,
                    "publisher_owned": value.publisher_owned,
                    "source_worktree_unmounted": value.source_worktree_unmounted,
                    "observed_by": value.observed_by,
                }
            )
        )
    )


def _prepared_checkout_payload(values: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "vista.world.daily-maintainer.prepared-checkout.v1",
        **values,
    }


def _rematerialized_checkout_digest(value: RematerializedPublisherCheckout) -> str:
    values = {
        "subject_sha256": value.subject_sha256,
        "path": value.path,
        "repository": value.repository,
        "base_sha": value.base_sha,
        "branch_name": value.branch_name,
        "candidate_id": value.candidate_id,
        "candidate_sha256": value.candidate_sha256,
        "backlog_sha256": value.backlog_sha256,
        "backlog_authorization_sha256": value.backlog_authorization_sha256,
        "patch_sha256": value.patch_sha256,
        "patch_bundle_sha256": value.patch_bundle_sha256,
        "final_envelope_sha256": value.final_envelope_sha256,
        "changed_paths": value.changed_paths,
        "owner_uid": value.owner_uid,
        "mode": value.mode,
        "device": value.device,
        "inode": value.inode,
        "link_count": value.link_count,
        "source_worktree_unmounted": value.source_worktree_unmounted,
        "observed_by": value.observed_by,
        "schema_version": value.schema_version,
    }
    return _sha256(_canonical_json_bytes(_rematerialized_checkout_payload(values)))


def _rematerialized_checkout_payload(values: dict[str, object]) -> dict[str, object]:
    payload = dict(values)
    changed = payload.get("changed_paths")
    if isinstance(changed, tuple):
        payload["changed_paths"] = list(changed)
    payload.setdefault("schema_version", REMATERIALIZATION_SCHEMA)
    return payload


def _parse_canonical_object(payload: bytes, label: str) -> dict[str, object]:
    try:
        decoded = payload.decode("utf-8", "strict")
        document = json.loads(
            decoded,
            parse_constant=lambda value: _raise_non_finite(value),
        )
    except (
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        SpoolContractError,
    ) as exc:
        raise SpoolContractError(f"{label} is not strict canonical JSON") from exc
    if not isinstance(document, dict):
        raise SpoolContractError(f"{label} must be a JSON object")
    if _canonical_json_bytes(document) != payload:
        raise SpoolContractError(f"{label} bytes are not canonical")
    return document


def _required_string(document: dict[str, object], field: str, maximum: int) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise SpoolContractError(f"finalized envelope {field} is invalid")
    if _CONTROL.search(value):
        raise SpoolContractError(f"finalized envelope {field} has control bytes")
    return value


def _required_sha(document: dict[str, object], field: str) -> str:
    value = document.get(field)
    return _require_sha256(value, f"finalized envelope {field}")


def _safe_changed_paths(value: tuple[str, ...]) -> None:
    if not isinstance(value, tuple) or not value:
        raise SpoolContractError("changed paths must be a non-empty tuple")
    if value != tuple(sorted(set(value))):
        raise SpoolContractError("changed paths must be sorted and unique")
    for path in value:
        if not isinstance(path, str) or len(path.encode("utf-8")) > 512:
            raise SpoolContractError("changed path is invalid")
        pure = PurePosixPath(path)
        if (
            path.startswith(("/", "\\"))
            or "\\" in path
            or _CONTROL.search(path)
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise SpoolContractError("changed path is not safe relative POSIX")


def _safe_spool_id(value: object) -> str:
    if not isinstance(value, str) or not _SPOOL_ID.fullmatch(value):
        raise SpoolContractError("spool ID is invalid")
    return value


def _safe_actor(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ACTOR.fullmatch(value):
        raise SpoolContractError(f"{label} is invalid")
    return value


def _safe_line(value: object, label: str, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8", "strict")) > maximum
        or _CONTROL.search(value)
    ):
        raise SpoolContractError(f"{label} is invalid")
    return value


def _canonical_date(value: object) -> str:
    if not isinstance(value, str):
        raise SpoolContractError("spool run date is invalid")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SpoolContractError("spool run date is invalid") from exc
    if parsed.isoformat() != value:
        raise SpoolContractError("spool run date is not canonical")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SpoolContractError(f"{label} must be lowercase SHA-256")
    return value


def _require_git_oid(value: object, label: str) -> str:
    if not isinstance(value, str) or not _GIT_OBJECT_ID.fullmatch(value):
        raise SpoolContractError(f"{label} is invalid")
    return value


def _bounded_int(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SpoolContractError(f"{label} is invalid")
    return value


def _bounded_bytes(value: object, label: str, *, maximum: int) -> bytes:
    if type(value) is not bytes or not value or len(value) > maximum:
        raise SpoolContractError(f"{label} bytes are empty or oversized")
    return value


def _absolute_normalized_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or _CONTROL.search(value):
        raise SpoolContractError(f"{label} is invalid")
    path = Path(value)
    if (
        not path.is_absolute()
        or value.startswith("//")
        or ".." in path.parts
        or str(path) != value
    ):
        raise SpoolContractError(f"{label} is not absolute and normalized")
    return path


def _absolute_directory(value: Path, label: str) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise SpoolContractError(f"{label} must be an absolute Path")
    try:
        resolved = value.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SpoolDeploymentError(f"{label} does not resolve") from exc
    if resolved != value or not resolved.is_dir():
        raise SpoolDeploymentError(f"{label} is not a canonical real directory")
    return resolved


def _paths_overlap(first: Path, second: Path) -> bool:
    return (
        first == second or first.is_relative_to(second) or second.is_relative_to(first)
    )


def _validate_source_outside_deployment(
    subject: SpoolSubject,
    deployment: SpoolDeploymentEvidence,
) -> None:
    if not isinstance(subject, SpoolSubject) or not isinstance(
        deployment, SpoolDeploymentEvidence
    ):
        raise SpoolContractError("source/deployment authority is invalid")
    source = Path(subject.source_worktree_path)
    try:
        resolved_source = source.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise SpoolDeploymentError(
            "patcher source worktree cannot be resolved safely"
        ) from exc
    roots = (
        Path(deployment.spool_root.path),
        Path(deployment.publisher_root.path),
        Path(deployment.publisher_state_root.path),
    )
    if any(
        _paths_overlap(candidate, root)
        for candidate in (source, resolved_source)
        for root in roots
    ):
        raise SpoolDeploymentError("patcher source worktree overlaps a deployment root")
    root_identities = {
        (deployment.spool_root.device, deployment.spool_root.inode),
        (deployment.publisher_root.device, deployment.publisher_root.inode),
        (deployment.publisher_state_root.device, deployment.publisher_state_root.inode),
    }
    inspected: set[Path] = set()
    for candidate in (source, resolved_source):
        current = candidate
        while current not in inspected:
            inspected.add(current)
            if root_identities.intersection(_stable_existing_path_identities(current)):
                raise SpoolDeploymentError(
                    "patcher source worktree aliases a deployment root inode"
                )
            parent = current.parent
            if parent == current:
                break
            current = parent


def _stable_existing_path_identities(path: Path) -> tuple[tuple[int, int], ...]:
    """Observe one path binding without claiming to close the final T13 race."""

    missing = {errno.ENOENT, errno.ENOTDIR}
    try:
        before_link = os.lstat(path)
    except OSError as exc:
        if exc.errno in missing:
            return ()
        raise SpoolDeploymentError(
            "patcher source ancestor cannot be inspected safely"
        ) from exc

    try:
        before_target = os.stat(path)
    except OSError as exc:
        if exc.errno not in missing:
            raise SpoolDeploymentError(
                "patcher source ancestor target cannot be inspected safely"
            ) from exc
        before_target = None

    try:
        after_link = os.lstat(path)
    except OSError as exc:
        raise SpoolDeploymentError(
            "patcher source ancestor changed during alias inspection"
        ) from exc
    try:
        after_target = os.stat(path)
    except OSError as exc:
        if exc.errno not in missing:
            raise SpoolDeploymentError(
                "patcher source ancestor target cannot be inspected safely"
            ) from exc
        after_target = None

    if _path_binding_signature(before_link) != _path_binding_signature(after_link):
        raise SpoolDeploymentError(
            "patcher source ancestor changed during alias inspection"
        )
    if (before_target is None) != (after_target is None) or (
        before_target is not None
        and after_target is not None
        and _path_binding_signature(before_target)
        != _path_binding_signature(after_target)
    ):
        raise SpoolDeploymentError(
            "patcher source ancestor target changed during alias inspection"
        )

    identities = {(before_link.st_dev, before_link.st_ino)}
    if before_target is not None:
        identities.add((before_target.st_dev, before_target.st_ino))
    return tuple(sorted(identities))


def _path_binding_signature(value: os.stat_result) -> tuple[int, int, int]:
    return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SpoolContractError("spool evidence is not canonical JSON") from exc


def _raise_non_finite(value: str) -> object:
    raise SpoolContractError(f"non-finite JSON value is forbidden: {value}")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stat_signature(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
