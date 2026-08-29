from __future__ import annotations

from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile

import pytest

from tools.admin import vista_blender_authority
from tools.admin import vista_r8_publisher_bundle
from tools.admin import vista_r8_root_bootstrap


def test_publisher_bundle_is_deterministic_and_exactly_pinned() -> None:
    first = vista_r8_publisher_bundle.build_bundle_bytes()
    second = vista_r8_publisher_bundle.build_bundle_bytes()

    assert first == second
    assert len(first) == vista_r8_publisher_bundle.EXPECTED_BUNDLE_BYTES == 192_512
    assert (
        hashlib.sha256(first).hexdigest()
        == vista_r8_publisher_bundle.EXPECTED_BUNDLE_SHA256
        == "a3ef15b22b0b0323409b937de275e2cb0d8f4a566e446074751612fc9eea408e"
    )
    assert (
        vista_r8_publisher_bundle.EXPECTED_PUBLISHER_FILES
        == vista_r8_root_bootstrap.EXPECTED_PUBLISHER_FILES
    )
    assert (
        vista_r8_publisher_bundle.EXPECTED_MANIFEST_SHA256
        == vista_r8_root_bootstrap.EXPECTED_PUBLISHER_MANIFEST_SHA256
    )
    members = vista_r8_root_bootstrap.parse_canonical_bundle(first)
    assert tuple(sorted(members)) == vista_r8_root_bootstrap.BUNDLE_MEMBER_PATHS
    assert all(type(payload) is bytes for payload in members.values())


def test_bundle_builder_publishes_o_excl_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "publisher.ustar"
    monkeypatch.setattr(vista_r8_publisher_bundle, "FIXED_BUNDLE_OUTPUT", output)
    monkeypatch.setattr(vista_r8_publisher_bundle.os, "geteuid", lambda: 1000)

    result = vista_r8_publisher_bundle.write_fixed_bundle()

    assert result["path"] == str(output)
    assert stat.S_IMODE(output.stat().st_mode) == 0o444
    with pytest.raises(
        vista_r8_publisher_bundle.PublisherBundleError,
        match="BUNDLE_OUTPUT_NOT_FRESH",
    ):
        vista_r8_publisher_bundle.write_fixed_bundle()


def _noncanonical_archive(members: dict[str, bytes], *, mutation: str) -> bytes:
    stream = BytesIO()
    with tarfile.open(
        fileobj=stream,
        mode="w",
        format=tarfile.USTAR_FORMAT,
    ) as archive:
        for index, name in enumerate(vista_r8_root_bootstrap.BUNDLE_MEMBER_PATHS):
            payload = members[name]
            emitted_name = (
                "../escape" if mutation == "traversal" and index == 0 else name
            )
            member = tarfile.TarInfo(emitted_name)
            member.mode = 0o444
            member.uid = 0
            member.gid = 0
            member.mtime = 0
            member.uname = ""
            member.gname = ""
            if mutation == "link" and index == 0:
                member.type = tarfile.SYMTYPE
                member.linkname = "target"
                member.size = 0
                archive.addfile(member)
            else:
                member.size = len(payload)
                archive.addfile(member, BytesIO(payload))
        if mutation == "extra":
            extra = tarfile.TarInfo("extra")
            extra.size = 1
            extra.mode = 0o444
            extra.uid = 0
            extra.gid = 0
            extra.mtime = 0
            extra.uname = ""
            extra.gname = ""
            archive.addfile(extra, BytesIO(b"x"))
        if mutation == "duplicate":
            name = vista_r8_root_bootstrap.BUNDLE_MEMBER_PATHS[0]
            duplicate = tarfile.TarInfo(name)
            duplicate.size = len(members[name])
            duplicate.mode = 0o444
            duplicate.uid = 0
            duplicate.gid = 0
            duplicate.mtime = 0
            duplicate.uname = ""
            duplicate.gname = ""
            archive.addfile(duplicate, BytesIO(members[name]))
    return stream.getvalue()


def test_bundle_tamper_fails_outer_pin() -> None:
    raw = bytearray(vista_r8_publisher_bundle.build_bundle_bytes())
    raw[600] ^= 1

    with pytest.raises(
        vista_r8_root_bootstrap.RootBootstrapError,
        match="ROOT_BOOTSTRAP_BUNDLE_PIN_INVALID",
    ):
        vista_r8_root_bootstrap.parse_canonical_bundle(bytes(raw))


@pytest.mark.parametrize(
    "mutation",
    ["noncanonical", "extra", "duplicate", "link", "traversal"],
)
def test_bundle_noncanonical_extra_duplicate_link_or_traversal_is_rejected(
    mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid = vista_r8_publisher_bundle.build_bundle_bytes()
    members = vista_r8_root_bootstrap.parse_canonical_bundle(valid)
    mutated = _noncanonical_archive(members, mutation=mutation)
    monkeypatch.setattr(
        vista_r8_root_bootstrap,
        "EXPECTED_BUNDLE_SHA256",
        hashlib.sha256(mutated).hexdigest(),
    )
    monkeypatch.setattr(
        vista_r8_root_bootstrap,
        "EXPECTED_BUNDLE_BYTES",
        len(mutated),
    )

    with pytest.raises(
        vista_r8_root_bootstrap.RootBootstrapError,
        match="ROOT_BOOTSTRAP_BUNDLE_INVALID",
    ):
        vista_r8_root_bootstrap.parse_canonical_bundle(mutated)


def test_nonroot_and_worktree_bootstrap_execution_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vista_r8_root_bootstrap.os, "geteuid", lambda: 12345)
    with pytest.raises(
        vista_r8_root_bootstrap.RootBootstrapError,
        match="ROOT_BOOTSTRAP_REQUIRED",
    ):
        vista_r8_root_bootstrap._require_installed_root_bootstrap()
    monkeypatch.setattr(
        vista_r8_root_bootstrap.os,
        "geteuid",
        lambda: vista_r8_root_bootstrap.ROOT_UID,
    )
    with pytest.raises(
        vista_r8_root_bootstrap.RootBootstrapError,
        match="ROOT_BOOTSTRAP_REQUIRED",
    ):
        vista_r8_root_bootstrap._require_installed_root_bootstrap()


def test_isolated_installed_layout_import_reaches_application_contract(
    tmp_path: Path,
) -> None:
    publisher_root = tmp_path / "publisher"
    members = vista_r8_root_bootstrap.parse_canonical_bundle(
        vista_r8_publisher_bundle.build_bundle_bytes()
    )
    for relative in vista_r8_root_bootstrap.PUBLISHER_FILE_RELATIVES:
        path = publisher_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(members[relative])
    supervisor = (
        publisher_root / "tools/animation/vista_playable_home_cc0/vertical_slice.py"
    )
    isolated_env = {"PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1"}
    rejected = subprocess.run(
        ["/usr/bin/python3.10", "-I", "-B", str(supervisor), "--help"],
        check=False,
        cwd="/",
        env=isolated_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    assert rejected.returncode != 0
    assert "ROOT_PUBLISHER_REQUIRED: alternate isolated supervisor" in rejected.stderr
    assert "No module named 'tools'" not in rejected.stderr

    source = supervisor.read_text(encoding="utf-8")
    fixed_source = source.replace(
        '"/root/vista-r8-cc0-animation-publisher-r1/"',
        f'"{publisher_root.as_posix()}/"',
        1,
    )
    assert fixed_source != source
    supervisor.write_text(fixed_source, encoding="utf-8")
    missing_no_bytecode = subprocess.run(
        ["/usr/bin/python3.10", "-I", str(supervisor), "--help"],
        check=False,
        cwd="/",
        env=isolated_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    assert missing_no_bytecode.returncode != 0
    assert "ROOT_PUBLISHER_REQUIRED: -B is required" in missing_no_bytecode.stderr
    assert not list(publisher_root.rglob("__pycache__"))
    result = subprocess.run(
        ["/usr/bin/python3.10", "-I", "-B", str(supervisor), "--help"],
        check=False,
        cwd="/",
        env=isolated_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Plan and materialize the VISTA-cleared" in result.stdout


@pytest.fixture
def bootstrap_install_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path | bytes]:
    uid = os.getuid()
    gid = os.getgid()
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    bootstrap_root = root / "bootstrap"
    bootstrap_root.mkdir(mode=0o700)
    installed_bootstrap = bootstrap_root / "vista_r8_root_bootstrap.py"
    installed_bootstrap.write_bytes(Path(vista_r8_root_bootstrap.__file__).read_bytes())
    installed_bootstrap.chmod(0o500)
    bundle_input = tmp_path / "publisher.ustar"
    bundle_input.write_bytes(vista_r8_publisher_bundle.build_bundle_bytes())
    archive_raw = b"official-blender-archive-test\n"
    archive_input = tmp_path / "blender.tar.xz"
    archive_input.write_bytes(archive_raw)
    blender_root = root / "blender"
    publisher_root = root / "publisher"
    active_receipt = bootstrap_root / "active-root-install-receipt.json"
    active_staging = bootstrap_root / ".active-root-install-receipt.staging"
    run_parent = root / "data/vista-published/vista-action-world-r1"

    patches = {
        "ROOT_UID": uid,
        "ROOT_GID": gid,
        "ROOT_BOOTSTRAP_ROOT": bootstrap_root,
        "INSTALLED_BOOTSTRAP": installed_bootstrap,
        "FIXED_BUNDLE_INPUT": bundle_input,
        "FIXED_BLENDER_ARCHIVE_INPUT": archive_input,
        "BLENDER_INSTALL_ROOT": blender_root,
        "PUBLISHER_INSTALL_ROOT": publisher_root,
        "STAGING_PARENT": root,
        "RUN_PARENT": run_parent,
        "ACTIVE_INSTALL_RECEIPT": active_receipt,
        "ACTIVE_INSTALL_STAGING": active_staging,
        "OFFICIAL_BLENDER_ARCHIVE_SHA256": hashlib.sha256(archive_raw).hexdigest(),
        "OFFICIAL_BLENDER_ARCHIVE_BYTES": len(archive_raw),
    }
    for name, value in patches.items():
        monkeypatch.setattr(vista_r8_root_bootstrap, name, value)
    monkeypatch.setattr(
        vista_r8_root_bootstrap,
        "_require_installed_root_bootstrap",
        lambda: None,
    )
    monkeypatch.setattr(
        vista_r8_root_bootstrap,
        "_ensure_root_run_parent",
        lambda: None,
    )

    yield {
        "root": root,
        "bootstrap_root": bootstrap_root,
        "installed_bootstrap": installed_bootstrap,
        "bundle_input": bundle_input,
        "archive_input": archive_input,
        "archive_raw": archive_raw,
        "blender_root": blender_root,
        "publisher_root": publisher_root,
        "active_receipt": active_receipt,
        "active_staging": active_staging,
    }

    for tree in (publisher_root, blender_root):
        if tree.exists():
            vista_r8_root_bootstrap._remove_owned_tree(tree)
    for path in (active_staging, active_receipt, installed_bootstrap):
        if path.exists() or path.is_symlink():
            path.chmod(0o600, follow_symlinks=False)
            path.unlink()
    if bootstrap_root.exists():
        bootstrap_root.chmod(0o700)
        bootstrap_root.rmdir()


def test_root_bootstrap_installs_exact_bytes_modes_manifest_and_receipts(
    bootstrap_install_env: dict[str, Path | bytes],
) -> None:
    result = vista_r8_root_bootstrap.install_fixed_inputs(
        vista_r8_root_bootstrap.BOOTSTRAP_ACKNOWLEDGEMENT
    )
    blender_root = bootstrap_install_env["blender_root"]
    publisher_root = bootstrap_install_env["publisher_root"]
    active_receipt = bootstrap_install_env["active_receipt"]
    assert isinstance(blender_root, Path)
    assert isinstance(publisher_root, Path)
    assert isinstance(active_receipt, Path)

    assert result["accepted"] is True
    assert stat.S_IMODE(blender_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(publisher_root.stat().st_mode) == 0o555
    assert (
        stat.S_IMODE(
            (blender_root / vista_r8_root_bootstrap.BLENDER_HELPER_INSTALL_NAME)
            .stat()
            .st_mode
        )
        == 0o500
    )
    assert (
        stat.S_IMODE(
            (blender_root / vista_r8_root_bootstrap.OFFICIAL_BLENDER_ARCHIVE_NAME)
            .stat()
            .st_mode
        )
        == 0o400
    )
    manifest = publisher_root / vista_r8_root_bootstrap.PUBLISHER_MANIFEST_MEMBER
    assert manifest.read_bytes() == vista_r8_publisher_bundle.canonical_manifest()
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o444
    receipts = [
        blender_root / vista_r8_root_bootstrap.ROOT_INSTALL_RECEIPT_NAME,
        publisher_root / vista_r8_root_bootstrap.ROOT_INSTALL_RECEIPT_NAME,
        active_receipt,
    ]
    assert len({path.read_bytes() for path in receipts}) == 1
    receipt = json.loads(receipts[0].read_bytes())
    assert receipt["publisher_bundle"] == {
        "format": "canonical_ustar_v1",
        "member_count": 11,
        "sha256": vista_r8_root_bootstrap.EXPECTED_BUNDLE_SHA256,
        "size_bytes": vista_r8_root_bootstrap.EXPECTED_BUNDLE_BYTES,
    }
    assert receipt["policy"]["partial_pair_usable"] is False
    for relative, (
        expected_sha256,
        expected_size,
    ) in vista_r8_root_bootstrap.EXPECTED_PUBLISHER_FILES.items():
        path = publisher_root / relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256
        assert path.stat().st_size == expected_size
        assert stat.S_IMODE(path.stat().st_mode) == 0o444


@pytest.mark.parametrize("corrupt", ["bundle", "archive"])
def test_bad_bundle_or_archive_fails_before_canonical_publish(
    bootstrap_install_env: dict[str, Path | bytes], corrupt: str
) -> None:
    target = bootstrap_install_env[f"{corrupt}_input"]
    assert isinstance(target, Path)
    raw = bytearray(target.read_bytes())
    raw[0] ^= 1
    target.write_bytes(raw)

    with pytest.raises(
        vista_r8_root_bootstrap.RootBootstrapError,
        match="ROOT_BOOTSTRAP_INPUT_PIN_INVALID",
    ):
        vista_r8_root_bootstrap.install_fixed_inputs(
            vista_r8_root_bootstrap.BOOTSTRAP_ACKNOWLEDGEMENT
        )

    for key in ("blender_root", "publisher_root", "active_receipt"):
        path = bootstrap_install_env[key]
        assert isinstance(path, Path)
        assert not path.exists()


def test_existing_destination_is_never_replaced(
    bootstrap_install_env: dict[str, Path | bytes],
) -> None:
    blender_root = bootstrap_install_env["blender_root"]
    publisher_root = bootstrap_install_env["publisher_root"]
    assert isinstance(blender_root, Path)
    assert isinstance(publisher_root, Path)
    blender_root.mkdir(mode=0o700)
    marker = blender_root / "marker"
    marker.write_bytes(b"existing\n")

    with pytest.raises(
        vista_r8_root_bootstrap.RootBootstrapError,
        match="ROOT_BOOTSTRAP_NOT_FRESH",
    ):
        vista_r8_root_bootstrap.install_fixed_inputs(
            vista_r8_root_bootstrap.BOOTSTRAP_ACKNOWLEDGEMENT
        )

    assert marker.read_bytes() == b"existing\n"
    assert not publisher_root.exists()


def test_first_visible_root_is_not_deleted_if_peer_publish_fails(
    bootstrap_install_env: dict[str, Path | bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_rename = vista_r8_root_bootstrap._rename_noreplace
    calls = 0

    def fail_second(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise vista_r8_root_bootstrap.RootBootstrapError(
                "ROOT_BOOTSTRAP_ATOMIC_PUBLISH_FAILED", "synthetic second failure"
            )
        real_rename(source, destination)

    monkeypatch.setattr(vista_r8_root_bootstrap, "_rename_noreplace", fail_second)

    with pytest.raises(
        vista_r8_root_bootstrap.RootBootstrapError,
        match="ROOT_BOOTSTRAP_PARTIAL_INSTALL",
    ):
        vista_r8_root_bootstrap.install_fixed_inputs(
            vista_r8_root_bootstrap.BOOTSTRAP_ACKNOWLEDGEMENT
        )

    blender_root = bootstrap_install_env["blender_root"]
    publisher_root = bootstrap_install_env["publisher_root"]
    active_receipt = bootstrap_install_env["active_receipt"]
    assert isinstance(blender_root, Path)
    assert isinstance(publisher_root, Path)
    assert isinstance(active_receipt, Path)
    assert blender_root.is_dir()
    assert not publisher_root.exists()
    assert not active_receipt.exists()


def test_helper_and_bootstrap_construct_the_same_paired_receipt(
    bootstrap_install_env: dict[str, Path | bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vista_r8_root_bootstrap.install_fixed_inputs(
        vista_r8_root_bootstrap.BOOTSTRAP_ACKNOWLEDGEMENT
    )
    blender_root = bootstrap_install_env["blender_root"]
    publisher_root = bootstrap_install_env["publisher_root"]
    active_receipt = bootstrap_install_env["active_receipt"]
    installed_bootstrap = bootstrap_install_env["installed_bootstrap"]
    archive_raw = bootstrap_install_env["archive_raw"]
    assert isinstance(blender_root, Path)
    assert isinstance(publisher_root, Path)
    assert isinstance(active_receipt, Path)
    assert isinstance(installed_bootstrap, Path)
    assert isinstance(archive_raw, bytes)
    receipt_raw = active_receipt.read_bytes()
    receipt = json.loads(receipt_raw)

    monkeypatch.setattr(vista_blender_authority, "ROOT_INSTALL_ROOT", blender_root)
    monkeypatch.setattr(
        vista_blender_authority,
        "INSTALLED_HELPER_PATH",
        blender_root / vista_r8_root_bootstrap.BLENDER_HELPER_INSTALL_NAME,
    )
    monkeypatch.setattr(
        vista_blender_authority,
        "PUBLISHER_INSTALL_ROOT",
        publisher_root,
    )
    monkeypatch.setattr(
        vista_blender_authority,
        "ROOT_BOOTSTRAP_PATH",
        installed_bootstrap,
    )
    monkeypatch.setattr(
        vista_blender_authority,
        "ACTIVE_INSTALL_RECEIPT",
        active_receipt,
    )
    monkeypatch.setattr(
        vista_blender_authority,
        "OFFICIAL_ARCHIVE_PATH",
        blender_root / vista_r8_root_bootstrap.OFFICIAL_BLENDER_ARCHIVE_NAME,
    )
    monkeypatch.setattr(
        vista_blender_authority,
        "OFFICIAL_ARCHIVE_SHA256",
        hashlib.sha256(archive_raw).hexdigest(),
    )
    monkeypatch.setattr(
        vista_blender_authority,
        "OFFICIAL_ARCHIVE_BYTES",
        len(archive_raw),
    )
    expected = vista_blender_authority._expected_root_install_receipt(
        bootstrap=receipt["root_bootstrap"],
        bundle_sha256=receipt["publisher_bundle"]["sha256"],
        bundle_size_bytes=receipt["publisher_bundle"]["size_bytes"],
        manifest=receipt["publisher_manifest"],
        publisher_records=vista_r8_root_bootstrap._publisher_payload_records(),
    )

    assert vista_blender_authority.canonical_json(expected) == receipt_raw
