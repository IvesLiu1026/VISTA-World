"""One-shot root sealer for the shared VISTA authority parent.

This helper performs exactly one permission transition on the fixed
``/data/vista-authorities`` directory: root-owned ``0755`` to root-owned
``0555``.  It snapshots the existing child namespace before the transition,
fsyncs the held directory descriptor, and proves that the path, descriptor,
and namespace still refer to the same objects afterwards.

The helper is deliberately separate from every authority publisher.  It must
be installed at the fixed root-owned path by a separately reviewed one-shot
installer that pins these source bytes and the Python interpreter.  Publishers
only accept an already sealed parent and never relax its mode.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import NoReturn, Sequence


AUTHORITY_PARENT = Path("/data/vista-authorities")
EXPECTED_CHILDREN = ("blender-4.5.8-r1",)
INSTALLED_ROOT = Path("/root/vista-authority-parent-seal-r1")
INSTALLED_LAUNCHER = INSTALLED_ROOT / "launch-vista-authority-parent-seal"
INSTALLED_HELPER = INSTALLED_ROOT / "vista_authority_parent_seal.py"
PINNED_PYTHON = Path("/usr/bin/python3.10")
PINNED_PYTHON_SHA256 = (
    "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86"
)
PINNED_PYTHON_BYTES = 5_917_224
ROOT_UID = 0
ROOT_GID = 0
READY_MODE = 0o755
SEALED_MODE = 0o555
HELPER_MODE = 0o500
LAUNCHER_MODE = 0o555
INSTALLED_ROOT_MODE = 0o555
SEAL_ACKNOWLEDGEMENT = (
    "I confirm no VISTA authority publisher is running and acknowledge one "
    "irreversible seal of /data/vista-authorities from 0755 to 0555."
)
RECONCILE_ACKNOWLEDGEMENT = (
    "I acknowledge an audit-and-fsync-only reconciliation of the already "
    "sealed /data/vista-authorities directory."
)
REPORT_SCHEMA = "vista.authority-parent-seal-report/v1"
PRODUCTION_ENVIRONMENT = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "PYTHONNOUSERSITE": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}


class ParentSealError(RuntimeError):
    """Closed failure carrying a stable machine-readable code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Identity:
    device: int
    inode: int
    file_type: int
    uid: int
    gid: int
    link_count: int


@dataclass(frozen=True)
class ChildIdentity:
    name: str
    device: int
    inode: int
    file_type: int
    mode: int
    uid: int
    gid: int
    link_count: int


def _fail(code: str, detail: str) -> NoReturn:
    raise ParentSealError(code, detail)


def _identity(metadata: os.stat_result) -> Identity:
    return Identity(
        device=metadata.st_dev,
        inode=metadata.st_ino,
        file_type=stat.S_IFMT(metadata.st_mode),
        uid=metadata.st_uid,
        gid=metadata.st_gid,
        link_count=metadata.st_nlink,
    )


def _open_directory(path: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        return os.open(path, flags)
    except OSError as exc:
        raise ParentSealError("AUTHORITY_PARENT_OPEN_FAILED", f"{path}: {exc}") from exc


def _require_secure_directory(
    metadata: os.stat_result,
    *,
    label: str,
    exact_modes: tuple[int, ...] | None = None,
) -> None:
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or mode & 0o022
        or (exact_modes is not None and mode not in exact_modes)
    ):
        _fail(
            "AUTHORITY_PARENT_SECURITY_INVALID",
            f"{label} metadata is not within the closed root-owned contract",
        )


def _ancestor_paths(path: Path) -> tuple[Path, ...]:
    parents = tuple(reversed(path.parents))
    return (*parents, path)


def _audit_ancestors() -> os.stat_result:
    parent_metadata: os.stat_result | None = None
    for path in _ancestor_paths(AUTHORITY_PARENT):
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise ParentSealError(
                "AUTHORITY_PARENT_SECURITY_INVALID", f"{path}: {exc}"
            ) from exc
        exact = (READY_MODE, SEALED_MODE) if path == AUTHORITY_PARENT else None
        _require_secure_directory(metadata, label=str(path), exact_modes=exact)
        if path == AUTHORITY_PARENT:
            parent_metadata = metadata
    if parent_metadata is None:  # pragma: no cover - fixed absolute path
        _fail("AUTHORITY_PARENT_SECURITY_INVALID", "parent was not audited")
    return parent_metadata


def _inventory_fd(descriptor: int) -> tuple[ChildIdentity, ...]:
    children: list[ChildIdentity] = []
    try:
        entries = list(os.scandir(descriptor))
    except OSError as exc:
        raise ParentSealError("AUTHORITY_PARENT_INVENTORY_FAILED", str(exc)) from exc
    names = tuple(sorted(entry.name for entry in entries))
    if any(name.startswith(".staging-") for name in names):
        _fail(
            "AUTHORITY_PARENT_NOT_QUIESCENT",
            "a staging namespace is present",
        )
    if names != EXPECTED_CHILDREN:
        _fail(
            "AUTHORITY_PARENT_INVENTORY_INVALID",
            f"expected {EXPECTED_CHILDREN!r}, observed {names!r}",
        )
    for entry in sorted(entries, key=lambda item: item.name):
        try:
            metadata = entry.stat(follow_symlinks=False)
        except OSError as exc:
            raise ParentSealError(
                "AUTHORITY_PARENT_INVENTORY_FAILED", f"{entry.name}: {exc}"
            ) from exc
        _require_secure_directory(
            metadata, label=entry.name, exact_modes=(SEALED_MODE,)
        )
        children.append(
            ChildIdentity(
                name=entry.name,
                device=metadata.st_dev,
                inode=metadata.st_ino,
                file_type=stat.S_IFMT(metadata.st_mode),
                mode=stat.S_IMODE(metadata.st_mode),
                uid=metadata.st_uid,
                gid=metadata.st_gid,
                link_count=metadata.st_nlink,
            )
        )
    return tuple(children)


def _bind_path_to_fd(
    descriptor: int,
    path_metadata: os.stat_result,
    *,
    allowed_modes: tuple[int, ...],
) -> os.stat_result:
    opened = os.fstat(descriptor)
    _require_secure_directory(
        opened, label=str(AUTHORITY_PARENT), exact_modes=allowed_modes
    )
    if _identity(path_metadata) != _identity(opened):
        _fail(
            "AUTHORITY_PARENT_IDENTITY_CHANGED",
            "lstat and held descriptor do not identify the same directory",
        )
    return opened


def _reopen_and_verify(
    held_descriptor: int,
    expected_identity: Identity,
    expected_inventory: tuple[ChildIdentity, ...],
) -> tuple[os.stat_result, tuple[ChildIdentity, ...]]:
    reopened = _open_directory(AUTHORITY_PARENT)
    try:
        reopened_metadata = os.fstat(reopened)
        path_metadata = os.lstat(AUTHORITY_PARENT)
        for label, metadata in (
            ("held descriptor", os.fstat(held_descriptor)),
            ("reopened descriptor", reopened_metadata),
            ("fixed path", path_metadata),
        ):
            _require_secure_directory(
                metadata,
                label=label,
                exact_modes=(SEALED_MODE,),
            )
            if _identity(metadata) != expected_identity:
                _fail(
                    "AUTHORITY_PARENT_IDENTITY_CHANGED",
                    f"{label} differs after sealing",
                )
        held_inventory = _inventory_fd(held_descriptor)
        reopened_inventory = _inventory_fd(reopened)
        if (
            held_inventory != expected_inventory
            or reopened_inventory != expected_inventory
        ):
            _fail(
                "AUTHORITY_PARENT_INVENTORY_CHANGED",
                "child namespace or metadata changed during sealing",
            )
        return reopened_metadata, reopened_inventory
    finally:
        os.close(reopened)


def _report(
    *,
    operation: str,
    status: str,
    metadata: os.stat_result,
    inventory: tuple[ChildIdentity, ...],
) -> dict[str, object]:
    return {
        "schema_version": REPORT_SCHEMA,
        "operation": operation,
        "status": status,
        "path": str(AUTHORITY_PARENT),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "owner": {"uid": metadata.st_uid, "gid": metadata.st_gid},
        "identity": asdict(_identity(metadata)),
        "inventory": [asdict(item) for item in inventory],
        "publishers_quiescent_acknowledged": operation == "seal",
        "permissions_relaxed": False,
    }


def audit_parent() -> dict[str, object]:
    path_metadata = _audit_ancestors()
    descriptor = _open_directory(AUTHORITY_PARENT)
    try:
        opened = _bind_path_to_fd(
            descriptor,
            path_metadata,
            allowed_modes=(READY_MODE, SEALED_MODE),
        )
        inventory = _inventory_fd(descriptor)
        return _report(
            operation="audit",
            status=(
                "ready_for_one_shot_seal"
                if stat.S_IMODE(opened.st_mode) == READY_MODE
                else "already_sealed"
            ),
            metadata=opened,
            inventory=inventory,
        )
    finally:
        os.close(descriptor)


def seal_parent() -> dict[str, object]:
    path_metadata = _audit_ancestors()
    if stat.S_IMODE(path_metadata.st_mode) != READY_MODE:
        _fail(
            "AUTHORITY_PARENT_NOT_FRESH",
            "seal requires the exact 0755 precondition; use reconcile for 0555",
        )
    descriptor = _open_directory(AUTHORITY_PARENT)
    transitioned = False
    try:
        opened = _bind_path_to_fd(
            descriptor,
            path_metadata,
            allowed_modes=(READY_MODE,),
        )
        expected_identity = _identity(opened)
        expected_inventory = _inventory_fd(descriptor)
        try:
            os.fchmod(descriptor, SEALED_MODE)
        except OSError as exc:
            try:
                observed_mode = stat.S_IMODE(os.fstat(descriptor).st_mode)
            except OSError as observe_exc:
                raise ParentSealError(
                    "PARENT_SEAL_DURABILITY_UNKNOWN",
                    "fchmod outcome cannot be observed; never relax the parent",
                ) from observe_exc
            if observed_mode != READY_MODE:
                raise ParentSealError(
                    "PARENT_SEAL_DURABILITY_UNKNOWN",
                    f"fchmod reported failure but mode is now {observed_mode:04o}; "
                    "never relax it and run reconcile only",
                ) from exc
            raise ParentSealError(
                "PARENT_SEAL_TRANSITION_FAILED",
                "fchmod failed before the sealed state was observed",
            ) from exc
        transitioned = True
        try:
            changed = os.fstat(descriptor)
            _require_secure_directory(
                changed,
                label="held descriptor after fchmod",
                exact_modes=(SEALED_MODE,),
            )
            if _identity(changed) != expected_identity:
                _fail(
                    "AUTHORITY_PARENT_IDENTITY_CHANGED",
                    "directory identity changed during fchmod",
                )
            os.fsync(descriptor)
            final_metadata, final_inventory = _reopen_and_verify(
                descriptor,
                expected_identity,
                expected_inventory,
            )
        except ParentSealError:
            raise
        except OSError as exc:
            raise ParentSealError(
                "PARENT_SEAL_DURABILITY_UNKNOWN",
                "mode may already be 0555; never relax it and run reconcile",
            ) from exc
        return _report(
            operation="seal",
            status="sealed_and_fsynced",
            metadata=final_metadata,
            inventory=final_inventory,
        )
    except ParentSealError as exc:
        if transitioned and exc.code != "PARENT_SEAL_DURABILITY_UNKNOWN":
            raise ParentSealError(
                "PARENT_SEAL_DURABILITY_UNKNOWN",
                f"{exc}; mode may already be 0555; run reconcile only",
            ) from exc
        raise
    finally:
        os.close(descriptor)


def reconcile_parent() -> dict[str, object]:
    path_metadata = _audit_ancestors()
    if stat.S_IMODE(path_metadata.st_mode) != SEALED_MODE:
        _fail(
            "AUTHORITY_PARENT_RECONCILE_INVALID",
            "reconcile requires an already sealed 0555 parent",
        )
    descriptor = _open_directory(AUTHORITY_PARENT)
    try:
        opened = _bind_path_to_fd(
            descriptor,
            path_metadata,
            allowed_modes=(SEALED_MODE,),
        )
        expected_identity = _identity(opened)
        expected_inventory = _inventory_fd(descriptor)
        try:
            os.fsync(descriptor)
            final_metadata, final_inventory = _reopen_and_verify(
                descriptor,
                expected_identity,
                expected_inventory,
            )
        except ParentSealError:
            raise
        except OSError as exc:
            raise ParentSealError(
                "PARENT_SEAL_DURABILITY_UNKNOWN",
                "sealed parent could not be durably reconciled",
            ) from exc
        return _report(
            operation="reconcile",
            status="sealed_and_fsynced",
            metadata=final_metadata,
            inventory=final_inventory,
        )
    finally:
        os.close(descriptor)


def _hash_fd(descriptor: int, maximum_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum_bytes:
            _fail("PARENT_SEAL_EXECUTION_INVALID", "pinned file exceeds expected size")
        digest.update(chunk)
    return digest.hexdigest(), total


def _bind_parent_seal_launcher(descriptor: int) -> None:
    if type(descriptor) is not int or descriptor < 3:
        _fail("PARENT_SEAL_EXECUTION_INVALID", "launcher descriptor is invalid")
    try:
        root_before = os.lstat(INSTALLED_ROOT)
        root_fd = os.open(
            INSTALLED_ROOT,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        )
        launcher_fd = _open_regular(INSTALLED_LAUNCHER)
        passed_fd = os.dup(descriptor)
        os.set_inheritable(passed_fd, False)
    except OSError as exc:
        raise ParentSealError("PARENT_SEAL_EXECUTION_INVALID", str(exc)) from exc
    try:
        root_opened = os.fstat(root_fd)
        launcher_metadata = os.fstat(launcher_fd)
        passed_metadata = os.fstat(passed_fd)
        helper_metadata = os.lstat(INSTALLED_HELPER)
        if (
            not stat.S_ISDIR(root_opened.st_mode)
            or _identity(root_opened) != _identity(root_before)
            or root_opened.st_uid != ROOT_UID
            or root_opened.st_gid != ROOT_GID
            or stat.S_IMODE(root_opened.st_mode) != INSTALLED_ROOT_MODE
            or set(os.listdir(root_fd))
            != {INSTALLED_LAUNCHER.name, INSTALLED_HELPER.name}
            or not stat.S_ISREG(launcher_metadata.st_mode)
            or launcher_metadata.st_uid != ROOT_UID
            or launcher_metadata.st_gid != ROOT_GID
            or launcher_metadata.st_nlink != 1
            or stat.S_IMODE(launcher_metadata.st_mode) != LAUNCHER_MODE
            or not stat.S_ISREG(helper_metadata.st_mode)
            or helper_metadata.st_uid != ROOT_UID
            or helper_metadata.st_gid != ROOT_GID
            or helper_metadata.st_nlink != 1
            or stat.S_IMODE(helper_metadata.st_mode) != HELPER_MODE
            or (
                launcher_metadata.st_dev,
                launcher_metadata.st_ino,
                launcher_metadata.st_size,
            )
            != (
                passed_metadata.st_dev,
                passed_metadata.st_ino,
                passed_metadata.st_size,
            )
        ):
            _fail(
                "PARENT_SEAL_EXECUTION_INVALID",
                "installed authority or held launcher identity differs",
            )
    finally:
        os.close(passed_fd)
        os.close(launcher_fd)
        os.close(root_fd)


def _bind_live_execution(parent_seal_launcher_fd: int) -> None:
    if os.geteuid() != ROOT_UID or os.getegid() != ROOT_GID:
        _fail("PARENT_SEAL_ROOT_REQUIRED", "effective root uid/gid are required")
    if (
        sys.flags.isolated != 1
        or sys.flags.no_user_site != 1
        or sys.flags.dont_write_bytecode != 1
        or dict(os.environ) != PRODUCTION_ENVIRONMENT
    ):
        _fail(
            "PARENT_SEAL_EXECUTION_INVALID",
            "isolated -I -B Python and the fixed cleared environment are required",
        )
    _bind_parent_seal_launcher(parent_seal_launcher_fd)
    try:
        helper_path = Path(__file__).resolve(strict=True)
    except OSError as exc:
        raise ParentSealError("PARENT_SEAL_EXECUTION_INVALID", str(exc)) from exc
    if helper_path != INSTALLED_HELPER:
        _fail("PARENT_SEAL_EXECUTION_INVALID", "helper path is not the fixed install")

    helper_fd = _open_regular(INSTALLED_HELPER)
    python_fd = _open_regular(PINNED_PYTHON)
    live_fd = -1
    try:
        helper_metadata = os.fstat(helper_fd)
        if (
            helper_metadata.st_uid != ROOT_UID
            or helper_metadata.st_gid != ROOT_GID
            or helper_metadata.st_nlink != 1
            or stat.S_IMODE(helper_metadata.st_mode) != HELPER_MODE
            or _identity(helper_metadata) != _identity(os.lstat(INSTALLED_HELPER))
        ):
            _fail("PARENT_SEAL_EXECUTION_INVALID", "installed helper metadata differs")
        python_metadata = os.fstat(python_fd)
        if (
            python_metadata.st_uid != ROOT_UID
            or python_metadata.st_gid != ROOT_GID
            or python_metadata.st_nlink != 1
            or stat.S_IMODE(python_metadata.st_mode) != 0o755
            or python_metadata.st_size != PINNED_PYTHON_BYTES
        ):
            _fail("PARENT_SEAL_EXECUTION_INVALID", "pinned Python metadata differs")
        python_sha, python_bytes = _hash_fd(python_fd, PINNED_PYTHON_BYTES)
        if (python_sha, python_bytes) != (
            PINNED_PYTHON_SHA256,
            PINNED_PYTHON_BYTES,
        ):
            _fail("PARENT_SEAL_EXECUTION_INVALID", "pinned Python bytes differ")
        proc_exe = Path("/proc/self/exe")
        target = os.readlink(proc_exe)
        if (
            target.endswith(" (deleted)")
            or Path(target).resolve(strict=True) != PINNED_PYTHON
        ):
            _fail("PARENT_SEAL_EXECUTION_INVALID", "live interpreter path differs")
        live_fd = os.open(
            proc_exe,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0),
        )
        if _identity(os.fstat(live_fd)) != _identity(python_metadata):
            _fail("PARENT_SEAL_EXECUTION_INVALID", "live interpreter identity differs")
        live_sha, live_bytes = _hash_fd(live_fd, PINNED_PYTHON_BYTES)
        if (live_sha, live_bytes) != (PINNED_PYTHON_SHA256, PINNED_PYTHON_BYTES):
            _fail("PARENT_SEAL_EXECUTION_INVALID", "live interpreter bytes differ")
        if (
            _identity(os.fstat(helper_fd)) != _identity(os.lstat(INSTALLED_HELPER))
            or _identity(os.fstat(python_fd)) != _identity(os.lstat(PINNED_PYTHON))
            or os.readlink(proc_exe) != target
        ):
            _fail("PARENT_SEAL_EXECUTION_INVALID", "execution identity changed")
    finally:
        os.close(helper_fd)
        os.close(python_fd)
        if live_fd >= 0:
            os.close(live_fd)


def _open_regular(path: Path) -> int:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            _fail("PARENT_SEAL_EXECUTION_INVALID", f"{path} is not regular")
        return descriptor
    except ParentSealError:
        raise
    except OSError as exc:
        raise ParentSealError(
            "PARENT_SEAL_EXECUTION_INVALID", f"{path}: {exc}"
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest="operation", required=True)
    audit = commands.add_parser("audit", allow_abbrev=False)
    audit.add_argument("--parent-seal-launcher-fd", required=True, type=int)
    seal = commands.add_parser("seal", allow_abbrev=False)
    seal.add_argument("--parent-seal-launcher-fd", required=True, type=int)
    seal.add_argument("--acknowledgement", required=True)
    reconcile = commands.add_parser("reconcile", allow_abbrev=False)
    reconcile.add_argument("--parent-seal-launcher-fd", required=True, type=int)
    reconcile.add_argument("--acknowledgement", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        _bind_live_execution(args.parent_seal_launcher_fd)
        if args.operation == "audit":
            report = audit_parent()
        elif args.operation == "seal":
            if args.acknowledgement != SEAL_ACKNOWLEDGEMENT:
                _fail(
                    "PARENT_SEAL_ACKNOWLEDGEMENT_INVALID",
                    "seal acknowledgement differs",
                )
            report = seal_parent()
        elif args.operation == "reconcile":
            if args.acknowledgement != RECONCILE_ACKNOWLEDGEMENT:
                _fail(
                    "PARENT_SEAL_ACKNOWLEDGEMENT_INVALID",
                    "reconcile acknowledgement differs",
                )
            report = reconcile_parent()
        else:  # pragma: no cover - argparse closes this branch
            _fail("PARENT_SEAL_OPERATION_INVALID", str(args.operation))
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except ParentSealError as exc:
        print(
            json.dumps(
                {"accepted": False, "code": exc.code, "detail": exc.detail},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
