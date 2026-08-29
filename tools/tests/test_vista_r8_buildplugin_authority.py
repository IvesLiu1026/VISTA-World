from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path

import pytest

from tools.admin import vista_r8_buildplugin_authority as authority

RUNBOOK = (
    Path(__file__).resolve().parents[2]
    / "docs/runbooks/vista-r8-buildplugin-authority-r1.md"
)


def _write(path: Path, raw: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)


def _fake_source(root: Path) -> None:
    uplugin = {
        "FileVersion": 3,
        "EngineVersion": "5.7.0",
        "Modules": [
            {
                "Name": "VistaPlayableHome",
                "Type": "Runtime",
                "LoadingPhase": "Default",
            },
            {
                "Name": "VistaPlayableHomeEditor",
                "Type": "Editor",
                "LoadingPhase": "Default",
            },
        ],
    }
    modules = {
        "BuildId": "fake-build-id",
        "Modules": {
            "VistaPlayableHome": "libUnrealEditor-VistaPlayableHome.so",
            "VistaPlayableHomeEditor": ("libUnrealEditor-VistaPlayableHomeEditor.so"),
        },
    }
    _write(
        root / "VistaPlayableHome.uplugin",
        authority.canonical_json(uplugin),
    )
    _write(
        root / "Binaries/Linux/UnrealEditor.modules",
        authority.canonical_json(modules),
    )
    _write(
        root / "Binaries/Linux/libUnrealEditor-VistaPlayableHome.so",
        b"runtime-editor-so\0",
        0o755,
    )
    _write(
        root / "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so",
        b"editor-so\0",
        0o755,
    )
    _write(root / "README.md", b"fake package\n", 0o600)


def _records(root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    directories: list[dict[str, object]] = []
    files: list[dict[str, object]] = []
    for current, names, filenames in os.walk(root, topdown=True, followlinks=False):
        names.sort()
        filenames.sort()
        current_path = Path(current)
        relative_directory = current_path.relative_to(root).as_posix()
        directories.append(
            {
                "kind": "directory",
                "path": "." if relative_directory == "." else relative_directory,
                "source_mode": oct(stat.S_IMODE(os.lstat(current_path).st_mode)),
            }
        )
        for name in filenames:
            path = current_path / name
            metadata = os.lstat(path)
            raw = path.read_bytes()
            files.append(
                {
                    "kind": "file",
                    "path": path.relative_to(root).as_posix(),
                    "source_mode": oct(stat.S_IMODE(metadata.st_mode)),
                    "size_bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
    return (
        sorted(directories, key=lambda item: str(item["path"])),
        sorted(files, key=lambda item: str(item["path"])),
    )


def _contract(root: Path, destination: Path) -> authority.Contract:
    directories, files = _records(root)
    projection_records: list[dict[str, object]] = [
        {"kind": "directory", "path": item["path"]} for item in directories
    ]
    projection_records.extend(
        {
            "kind": "file",
            "path": item["path"],
            "sha256": item["sha256"],
            "size_bytes": item["size_bytes"],
        }
        for item in files
    )
    digest = hashlib.sha256()
    for record in sorted(
        projection_records, key=lambda item: (str(item["path"]), str(item["kind"]))
    ):
        raw = json.dumps(
            record,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    by_path = {str(item["path"]): item for item in files}
    critical = {
        relative: authority.FilePin(
            str(by_path[relative]["sha256"]),
            int(by_path[relative]["size_bytes"]),
            int(str(by_path[relative]["source_mode"]), 8),
        )
        for relative in authority.CRITICAL_FILE_PINS
    }
    return authority.Contract(
        source_root=root,
        authority_root=destination,
        projection_sha256=digest.hexdigest(),
        inventory_sha256=hashlib.sha256(
            authority.canonical_json([*directories, *files])
        ).hexdigest(),
        file_count=len(files),
        directory_count=len(directories),
        total_bytes=sum(int(item["size_bytes"]) for item in files),
        critical_file_pins=critical,
        max_file_count=32,
        max_directory_count=16,
        max_total_bytes=1024 * 1024,
    )


@pytest.fixture
def fake_package(tmp_path: Path) -> tuple[Path, authority.Contract]:
    source = tmp_path / "source"
    _fake_source(source)
    contract = _contract(source, tmp_path / "authority")
    return source, contract


def _test_noreplace(source: Path, destination: Path) -> None:
    if os.path.lexists(destination):
        raise authority.BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_NOT_FRESH", str(destination)
        )
    os.rename(source, destination)


def test_production_contract_and_critical_pins_are_exact() -> None:
    contract = authority.PRODUCTION_CONTRACT

    assert contract.source_root == Path(
        "/data/sysx/vista-world/runs/vista-action-world-r1/"
        "vista-r8-ue-animation-buildplugin-dev-20260830c"
    )
    assert contract.authority_root == Path(
        "/data/vista-authorities/vista-r8-ue-animation-buildplugin-r1"
    )
    assert contract.projection_sha256 == (
        "69153cd676ac35579115d1be9c8ced7d86c70beab7f8adb681ad7b8d373ae48e"
    )
    assert contract.inventory_sha256 == (
        "cad2d8f0481934cc1565c3cad0dbad041d293795cf31ea420a6a646d8c2b46b2"
    )
    assert (contract.file_count, contract.directory_count, contract.total_bytes) == (
        241,
        32,
        51_661_522,
    )
    assert (
        authority.CRITICAL_FILE_PINS[
            "Binaries/Linux/libUnrealEditor-VistaPlayableHomeEditor.so"
        ].sha256
        == "cb15bda09c1670e9b27b539c8027170996ef5824f273757b069a21de1e652849"
    )


def test_separate_runbook_literal_pins_finalized_helper_without_hash_cycle() -> None:
    helper = Path(authority.__file__)
    raw = helper.read_bytes()
    runbook = RUNBOOK.read_text(encoding="utf-8")
    digest_match = re.search(r"^sha256: ([0-9a-f]{64})$", runbook, re.MULTILINE)
    size_match = re.search(r"^size_bytes: ([0-9]+)$", runbook, re.MULTILINE)

    assert digest_match is not None
    assert size_match is not None
    assert hashlib.sha256(raw).hexdigest() == digest_match.group(1)
    assert len(raw) == int(size_match.group(1))
    assert "post-install verification closes" in runbook
    assert "EXPECTED=$(sha256sum mutable-checkout-file)" in runbook
    assert "EXPECTED=$(sha256sum tools/admin" not in runbook


def test_fake_tree_audit_holds_every_fd_and_is_zero_write(
    fake_package: tuple[Path, authority.Contract],
) -> None:
    source, contract = fake_package
    before = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))

    with authority.hold_source_tree(contract) as tree:
        report = authority.audit_report(tree, contract)
        assert len(tree.files) == contract.file_count
        assert len(tree.directories) == contract.directory_count
        assert all(os.fstat(item.descriptor) for item in tree.files)
        assert all(os.fstat(item.descriptor) for item in tree.directories)
        assert report["accepted"] is False
        assert report["status"] == "fixed_source_audited_zero_write"
        assert report["authority_observation"]["exists"] is False
        assert report["authority_observation"]["validated"] is False
        assert report["authority_observation"]["publication_performed"] is False
        assert report["execution_boundary"] == {
            "expected_installed_helper_path": str(authority.INSTALLED_HELPER),
            "external_helper_trust_anchor_required": True,
            "pinned_interpreter": {
                "path": str(authority.PINNED_PYTHON),
                "sha256": authority.PINNED_PYTHON_SHA256,
                "size_bytes": authority.PINNED_PYTHON_BYTES,
            },
            "live_interpreter_validated": False,
        }
        assert all(report["audit_gates"].values())
        assert report["content_digest"] == authority._content_digest(report)
    after = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))

    assert before == after
    assert not contract.authority_root.exists()


def test_audit_report_is_closed_and_observes_existing_authority_without_claiming_it(
    fake_package: tuple[Path, authority.Contract],
) -> None:
    _source, contract = fake_package
    contract.authority_root.mkdir()
    with authority.hold_source_tree(contract) as tree:
        report = authority.audit_report(tree, contract)

    assert report["authority_observation"] == {
        "path": str(contract.authority_root),
        "exists": True,
        "validated": False,
        "publication_performed": False,
    }
    mutated = dict(report)
    mutated["extra"] = True
    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="BUILDPLUGIN_AUTHORITY_AUDIT_INVALID",
    ):
        authority.validate_audit_report(mutated, contract, authority_exists=True)
    mutated = json.loads(json.dumps(report))
    mutated["execution_boundary"]["live_interpreter_validated"] = True
    mutated["content_digest"] = authority._content_digest(mutated)
    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="BUILDPLUGIN_AUTHORITY_AUDIT_INVALID",
    ):
        authority.validate_audit_report(mutated, contract, authority_exists=True)
    mutated = dict(report)
    mutated["content_digest"] = "0" * 64
    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="BUILDPLUGIN_AUTHORITY_AUDIT_INVALID",
    ):
        authority.validate_audit_report(mutated, contract, authority_exists=True)


def test_complete_pin_detects_content_or_mode_drift(
    fake_package: tuple[Path, authority.Contract],
) -> None:
    source, contract = fake_package
    readme = source / "README.md"
    readme.write_bytes(b"changed package\n")

    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="BUILDPLUGIN_AUTHORITY_SOURCE_PIN_INVALID",
    ):
        authority.hold_source_tree(contract)

    _fake_source(source)
    contract = _contract(source, contract.authority_root)
    (source / "README.md").chmod(0o644)
    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="BUILDPLUGIN_AUTHORITY_SOURCE_PIN_INVALID",
    ):
        authority.hold_source_tree(contract)


def test_strict_critical_semantics_reject_self_consistent_bad_modules(
    fake_package: tuple[Path, authority.Contract],
) -> None:
    source, original = fake_package
    bad = source / "Binaries/Linux/UnrealEditor.modules"
    bad.write_text(
        '{"BuildId":"x","Modules":{"VistaPlayableHome":"wrong.so"}}\n',
        encoding="utf-8",
    )
    contract = _contract(source, original.authority_root)

    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="BUILDPLUGIN_AUTHORITY_CRITICAL_INVALID",
    ):
        authority.hold_source_tree(contract)


@pytest.mark.parametrize("unsafe_kind", ["symlink", "fifo", "hardlink"])
def test_links_and_special_entries_are_rejected(
    fake_package: tuple[Path, authority.Contract],
    unsafe_kind: str,
) -> None:
    source, original = fake_package
    target = source / "README.md"
    if unsafe_kind == "symlink":
        target.unlink()
        target.symlink_to("VistaPlayableHome.uplugin")
    elif unsafe_kind == "fifo":
        target.unlink()
        os.mkfifo(target)
    else:
        target.unlink()
        os.link(source / "VistaPlayableHome.uplugin", target)
    contract = authority.dataclasses.replace(
        original,
        # Aggregate pins are irrelevant: the type/link gate must run first.
        file_count=original.file_count,
    )

    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="BUILDPLUGIN_AUTHORITY_SOURCE_INVALID",
    ):
        authority.hold_source_tree(contract)


def test_case_collision_is_rejected_before_aggregate_acceptance(
    fake_package: tuple[Path, authority.Contract],
) -> None:
    source, original = fake_package
    _write(source / "readme.MD", b"collision\n")
    contract = _contract(source, original.authority_root)

    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="case-insensitive collision",
    ):
        authority.hold_source_tree(contract)


def test_path_replacement_after_hold_fails_before_copy_and_revalidation(
    fake_package: tuple[Path, authority.Contract], tmp_path: Path
) -> None:
    source, contract = fake_package
    with authority.hold_source_tree(contract) as tree:
        held = next(item for item in tree.files if item.relative_path == "README.md")
        old_raw = (source / "README.md").read_bytes()
        replacement = source / "replacement"
        replacement.write_bytes(old_raw)
        replacement.chmod(0o600)
        os.replace(replacement, source / "README.md")
        copied = tmp_path / "held-copy"
        os.lseek(held.descriptor, 0, os.SEEK_SET)
        assert os.read(held.descriptor, len(old_raw) + 1) == old_raw
        with pytest.raises(
            authority.BuildPluginAuthorityError,
            match="BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED",
        ):
            authority._copy_held_file(held, copied, (os.getuid(), os.getgid()))
        assert not copied.exists()
        with pytest.raises(
            authority.BuildPluginAuthorityError,
            match="BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED",
        ):
            authority.revalidate_held_tree(tree)


def test_regular_file_to_fifo_open_race_is_nonblocking_and_rejected(
    fake_package: tuple[Path, authority.Contract],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, contract = fake_package
    real_open = authority.os.open
    raced = False

    def racing_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal raced
        if path == "README.md" and dir_fd is not None and not raced:
            raced = True
            assert flags & os.O_NONBLOCK
            target = source / "README.md"
            target.unlink()
            os.mkfifo(target, 0o600)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(authority.os, "open", racing_open)
    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="BUILDPLUGIN_AUTHORITY_SOURCE_CHANGED",
    ):
        authority.hold_source_tree(contract)
    assert raced is True


def test_live_proc_exe_is_bound_to_pinned_path_inode_and_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_path = Path(os.path.realpath(os.readlink("/proc/self/exe")))
    metadata = live_path.stat()
    raw = live_path.read_bytes()
    monkeypatch.setattr(authority, "ROOT_UID", metadata.st_uid)
    monkeypatch.setattr(authority, "ROOT_GID", metadata.st_gid)
    monkeypatch.setattr(authority, "PINNED_PYTHON", live_path)
    monkeypatch.setattr(
        authority, "PINNED_PYTHON_SHA256", hashlib.sha256(raw).hexdigest()
    )
    monkeypatch.setattr(authority, "PINNED_PYTHON_BYTES", len(raw))
    monkeypatch.setattr(authority.sys, "executable", str(live_path))

    pin = authority._bind_live_interpreter()

    assert pin.sha256 == hashlib.sha256(raw).hexdigest()
    assert pin.size_bytes == len(raw)
    real_readlink = authority.os.readlink
    monkeypatch.setattr(
        authority.os,
        "readlink",
        lambda path: (
            "/bin/false" if str(path) == "/proc/self/exe" else real_readlink(path)
        ),
    )
    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="live /proc/self/exe",
    ):
        authority._bind_live_interpreter()


def test_nonroot_and_worktree_publish_are_preoutput_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def forbidden(*_args: object, **_kwargs: object) -> str:
        nonlocal called
        called = True
        raise AssertionError("staging must not be created")

    monkeypatch.setattr(authority.tempfile, "mkdtemp", forbidden)
    monkeypatch.setattr(authority.os, "geteuid", lambda: 12345)
    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="BUILDPLUGIN_AUTHORITY_ROOT_REQUIRED",
    ):
        authority.publish_fixed_authority(authority.ACKNOWLEDGEMENT)
    assert called is False

    monkeypatch.setattr(authority.os, "geteuid", lambda: 0)
    with pytest.raises(
        authority.BuildPluginAuthorityError,
        match="must run from /root/vista-r8-buildplugin-authority-r1",
    ):
        authority.publish_fixed_authority(authority.ACKNOWLEDGEMENT)
    assert called is False
    assert not any(tmp_path.iterdir())


def test_private_staging_copies_held_fds_and_publishes_immutable_tree(
    fake_package: tuple[Path, authority.Contract],
) -> None:
    _source, contract = fake_package
    owner = (os.getuid(), os.getgid())
    fake_pin = authority.FilePin("a" * 64, 12, 0o500)

    with authority.hold_source_tree(contract) as tree:
        receipt = authority._publish_held_tree(
            tree,
            contract,
            fake_pin,
            authority.FilePin("b" * 64, 34, 0o755),
            owner=owner,
            rename_function=_test_noreplace,
        )

    assert receipt["accepted"] is True
    assert receipt["status"] == "root_published_immutable_buildplugin_authority"
    assert receipt["claims"] == authority.NEGATIVE_CLAIMS
    assert receipt["content_digest"] == authority._content_digest(receipt)
    assert stat.S_IMODE(contract.authority_root.stat().st_mode) == 0o555
    for path in contract.authority_root.rglob("*"):
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == (0o555 if path.is_dir() else 0o444)
    manifest_raw = (contract.authority_root / authority.MANIFEST_NAME).read_bytes()
    manifest = json.loads(manifest_raw)
    assert manifest["schema_version"] == authority.MANIFEST_SCHEMA
    assert len(manifest["entries"]) == contract.file_count + contract.directory_count
    assert (
        receipt["authority"]["manifest"]["sha256"]
        == hashlib.sha256(manifest_raw).hexdigest()
    )
    assert (contract.authority_root / "payload/README.md").read_bytes() == (
        b"fake package\n"
    )


def test_existing_destination_refuses_before_staging(
    fake_package: tuple[Path, authority.Contract], monkeypatch: pytest.MonkeyPatch
) -> None:
    _source, contract = fake_package
    contract.authority_root.mkdir()
    called = False

    def forbidden(*_args: object, **_kwargs: object) -> str:
        nonlocal called
        called = True
        raise AssertionError("staging must not be created")

    monkeypatch.setattr(authority.tempfile, "mkdtemp", forbidden)
    with (
        authority.hold_source_tree(contract) as tree,
        pytest.raises(
            authority.BuildPluginAuthorityError,
            match="BUILDPLUGIN_AUTHORITY_NOT_FRESH",
        ),
    ):
        authority._publish_held_tree(
            tree,
            contract,
            authority.FilePin("a" * 64, 1, 0o500),
            authority.FilePin("b" * 64, 1, 0o755),
            owner=(os.getuid(), os.getgid()),
            rename_function=_test_noreplace,
        )
    assert called is False


def test_rename_collision_cleans_only_fresh_staging(
    fake_package: tuple[Path, authority.Contract],
) -> None:
    _source, contract = fake_package

    def collide(_source: Path, destination: Path) -> None:
        destination.mkdir()
        raise authority.BuildPluginAuthorityError(
            "BUILDPLUGIN_AUTHORITY_NOT_FRESH", str(destination)
        )

    with (
        authority.hold_source_tree(contract) as tree,
        pytest.raises(
            authority.BuildPluginAuthorityError,
            match="BUILDPLUGIN_AUTHORITY_NOT_FRESH",
        ),
    ):
        authority._publish_held_tree(
            tree,
            contract,
            authority.FilePin("a" * 64, 1, 0o500),
            authority.FilePin("b" * 64, 1, 0o755),
            owner=(os.getuid(), os.getgid()),
            rename_function=collide,
        )

    assert contract.authority_root.is_dir()
    assert not list(
        contract.authority_root.parent.glob(
            f".{contract.authority_root.name}.staging-*"
        )
    )


def test_post_rename_parent_fsync_failure_is_durability_unknown_and_reconcilable(
    fake_package: tuple[Path, authority.Contract],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, contract = fake_package
    owner = (os.getuid(), os.getgid())
    helper_pin = authority.FilePin("a" * 64, 1, 0o500)
    interpreter_pin = authority.FilePin("b" * 64, 1, 0o755)
    real_fsync_directory = authority._fsync_directory

    def fail_published_parent(path: Path) -> None:
        if path == contract.authority_root.parent and contract.authority_root.exists():
            raise OSError("injected parent fsync failure")
        real_fsync_directory(path)

    with authority.hold_source_tree(contract) as tree:
        monkeypatch.setattr(authority, "_fsync_directory", fail_published_parent)
        with pytest.raises(
            authority.BuildPluginAuthorityError,
            match="BUILDPLUGIN_AUTHORITY_PUBLISHED_DURABILITY_UNKNOWN",
        ):
            authority._publish_held_tree(
                tree,
                contract,
                helper_pin,
                interpreter_pin,
                owner=owner,
                rename_function=_test_noreplace,
            )

        assert contract.authority_root.is_dir()
        assert (contract.authority_root / authority.RECEIPT_NAME).is_file()
        assert not list(
            contract.authority_root.parent.glob(
                f".{contract.authority_root.name}.staging-*"
            )
        )
        monkeypatch.setattr(authority, "_fsync_directory", real_fsync_directory)
        reconciled = authority._reconcile_held_tree(
            tree,
            contract,
            helper_pin,
            interpreter_pin,
            owner=owner,
        )

    assert reconciled["accepted"] is True
    assert reconciled["status"] == (
        "published_buildplugin_authority_durability_reconciled"
    )
    assert reconciled["authority"]["parent_fsync_verified"] is True
    assert reconciled["authority"]["republished"] is False
    assert reconciled["content_digest"] == authority._content_digest(reconciled)


def test_production_uses_linux_renameat2_noreplace_without_replace_fallback() -> None:
    source = Path(authority.__file__).read_text(encoding="utf-8")

    assert "renameat2" in source
    assert "_RENAME_NOREPLACE" in source
    assert "os.replace(source, destination)" not in source
    assert "os.rename(source, destination)" not in source
    assert "copy_from_held_source_descriptors_only" in source
    assert "os.O_NONBLOCK" in source
    assert 'Path("/proc/self/exe")' in source
    assert "BUILDPLUGIN_AUTHORITY_PUBLISHED_DURABILITY_UNKNOWN" in source
