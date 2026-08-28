from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import json
import os
import pathlib
import stat
import sys
from dataclasses import dataclass

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/ue/vista_playable_home/materialize_hybrid_camera_overlay.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "materialize_hybrid_camera_overlay", MODULE_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError("camera overlay module cannot be loaded")
overlay = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = overlay
MODULE_SPEC.loader.exec_module(overlay)


@dataclass(frozen=True)
class Fixture:
    config: overlay.OverlayConfig
    attempt: pathlib.Path
    project_old_file: pathlib.Path
    plugin_new_file: pathlib.Path


def _mkdir(path: pathlib.Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)


def _write(path: pathlib.Path, raw: bytes, mode: int) -> None:
    _mkdir(path.parent, 0o700 if "project" in path.parts else 0o755)
    path.write_bytes(raw)
    os.chmod(path, mode)


def _pin(snapshot: overlay.TreeSnapshot) -> overlay.TreePin:
    return overlay.TreePin(
        snapshot.normalized_sha256,
        len(snapshot.files),
        len(snapshot.directories),
        snapshot.total_bytes,
    )


def _build_pin(snapshot: overlay.TreeSnapshot) -> overlay.BuildTreePin:
    return overlay.BuildTreePin(
        snapshot.build_sha256,
        len(snapshot.files),
        snapshot.total_bytes,
    )


def _fingerprint(root: pathlib.Path) -> tuple[tuple[object, ...], ...]:
    values: list[tuple[object, ...]] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort()
        files.sort()
        base = pathlib.Path(current)
        for name in directories:
            path = base / name
            metadata = os.lstat(path)
            values.append(
                (
                    path.relative_to(root).as_posix(),
                    "link" if stat.S_ISLNK(metadata.st_mode) else "directory",
                    stat.S_IMODE(metadata.st_mode),
                )
            )
        for name in files:
            path = base / name
            metadata = os.lstat(path)
            kind = "link" if stat.S_ISLNK(metadata.st_mode) else "file"
            digest = None
            if stat.S_ISREG(metadata.st_mode):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            values.append(
                (
                    path.relative_to(root).as_posix(),
                    kind,
                    stat.S_IMODE(metadata.st_mode),
                    metadata.st_size,
                    digest,
                )
            )
    return tuple(values)


@pytest.fixture
def fixture(tmp_path: pathlib.Path) -> Fixture:
    run_parent = tmp_path / "runs"
    hybrid_root = run_parent / "hybrid-r3-source"
    project = hybrid_root / "project"
    plugin = tmp_path / "camera-plugin"
    _mkdir(project)
    _mkdir(plugin, 0o755)

    project_files = {
        "VistaPlayableHome.uproject": b'{"FileVersion":3}\n',
        "Config/DefaultEngine.ini": b"[/Script/Engine.Engine]\n",
        "Content/Maps/Home.umap": b"sealed-hybrid-map",
        "Plugins/VistaPlayableHome/README.md": b"old plugin",
        "Plugins/VistaPlayableHome/Source/Shared.cpp": b"old shared source",
        "Plugins/VistaPlayableHome/Source/OldOnly.cpp": b"old only",
        "Plugins/Other/Other.uplugin": b"other plugin stays",
    }
    for relative, raw in project_files.items():
        _write(project / relative, raw, 0o600)
    _mkdir(project / "Content/EmptyRoom")
    _mkdir(project / "Plugins/VistaPlayableHome/OldEmpty")

    plugin_files = {
        "README.md": (b"camera plugin", 0o644),
        "VistaPlayableHome.uplugin": (b'{"Version":3}\n', 0o644),
        "Source/Shared.cpp": (b"new camera-safe shared source", 0o644),
        "Source/NewOnly.cpp": (b"new only", 0o600),
        "Binaries/Linux/libVista.so": (b"binary payload", 0o755),
    }
    for relative, (raw, mode) in plugin_files.items():
        _write(plugin / relative, raw, mode)
    _mkdir(plugin / "Config/EmptyCameraDirectory", 0o755)

    # Project inputs are required to be an already-private 0700/0600 tree.
    for current, directories, files in os.walk(project):
        os.chmod(current, 0o700)
        for name in directories:
            os.chmod(pathlib.Path(current) / name, 0o700)
        for name in files:
            os.chmod(pathlib.Path(current) / name, 0o600)

    project_snapshot = overlay.snapshot_tree(
        project, "fixture project", require_private_modes=True
    )
    plugin_snapshot = overlay.snapshot_tree(plugin, "fixture plugin")
    output_projection = overlay._derive_output_projection(
        project_snapshot, plugin_snapshot
    )
    output_pin = overlay.TreePin(
        output_projection.sha256,
        len(output_projection.files),
        len(output_projection.directories),
        output_projection.total_bytes,
    )

    host_receipt = {
        "schema_version": "fixture/v1",
        "status": overlay.HYBRID_HOST_STATUS,
        "attempt_root": str(hybrid_root),
        "post_project_projection_sha256": project_snapshot.normalized_sha256,
        "post_project_file_count": len(project_snapshot.files),
        "post_project_directory_count": len(project_snapshot.directories),
        "post_project_total_bytes": project_snapshot.total_bytes,
        "accepted_as_visual_evidence": False,
        "promotable": False,
        "diagnostic_only": True,
        "full_material_fidelity": False,
        "claims": {
            "gta_level": False,
            "real_human_present": False,
            "player_eye_reviewed": False,
            "interaction_proven": False,
        },
    }
    receipt_raw = overlay._canonical_json(host_receipt)
    receipt_path = hybrid_root / "hybrid-r3-host-receipt.json"
    _write(receipt_path, receipt_raw, 0o600)

    config = overlay.OverlayConfig(
        repository_root=ROOT,
        run_parent=run_parent,
        hybrid_root=hybrid_root,
        hybrid_project_root=project,
        hybrid_host_receipt=receipt_path,
        hybrid_host_receipt_sha256=hashlib.sha256(receipt_raw).hexdigest(),
        hybrid_host_status=overlay.HYBRID_HOST_STATUS,
        hybrid_project_pin=_pin(project_snapshot),
        camera_plugin_root=plugin,
        camera_plugin_build_pin=_build_pin(plugin_snapshot),
        camera_plugin_normalized_pin=_pin(plugin_snapshot),
        output_project_pin=output_pin,
    )
    return Fixture(
        config=config,
        attempt=run_parent / "hybrid-r3-camera-test",
        project_old_file=project / "Plugins/VistaPlayableHome/Source/OldOnly.cpp",
        plugin_new_file=plugin / "Source/NewOnly.cpp",
    )


def _apply_plan(fixture: Fixture) -> overlay.PreparedOverlay:
    return overlay.build_plan(
        fixture.config,
        fixture.attempt,
        apply=True,
        allow_private_noncommercial_license=True,
        allow_nonpromotable_material_conflict=True,
    )


def test_dry_run_is_deterministic_and_zero_write(fixture: Fixture) -> None:
    before = _fingerprint(fixture.config.run_parent.parent)
    first = overlay.build_plan(fixture.config, fixture.attempt)
    second = overlay.build_plan(fixture.config, fixture.attempt)

    assert first.report == second.report
    assert first.report["mode"] == "dry_run"
    assert first.report["status"] == overlay.DRY_RUN_STATUS
    assert first.report["claims"] == {
        "camera_plugin_overlaid": False,
        "gta_level": False,
        "real_human_present": False,
        "player_eye_reviewed": False,
        "interaction_proven": False,
        "visual_acceptance": False,
    }
    assert not fixture.attempt.exists()
    assert _fingerprint(fixture.config.run_parent.parent) == before


def test_buildplugin_tree_seal_uses_preorder_file_traversal(
    tmp_path: pathlib.Path,
) -> None:
    package = tmp_path / "package"
    _mkdir(package, 0o755)
    _write(package / "README.md", b"root", 0o644)
    _write(package / "Binaries/Linux/module.so", b"module", 0o755)
    snapshot = overlay.snapshot_tree(package, "ordered package")
    root_sha = hashlib.sha256(b"root").hexdigest()
    module_sha = hashlib.sha256(b"module").hexdigest()
    expected_raw = (
        "README.md\0" + f"644\0{4}\0{root_sha}\n"
        "Binaries/Linux/module.so\0" + f"755\0{6}\0{module_sha}\n"
    ).encode("utf-8")

    assert snapshot.build_sha256 == hashlib.sha256(expected_raw).hexdigest()


@pytest.mark.parametrize(
    ("private_ack", "material_ack", "message"),
    [
        (False, True, "private/noncommercial"),
        (True, False, "material-conflict"),
        (False, False, "private/noncommercial"),
    ],
)
def test_apply_requires_both_acknowledgements(
    fixture: Fixture, private_ack: bool, material_ack: bool, message: str
) -> None:
    with pytest.raises(overlay.OverlayError, match=message):
        overlay.build_plan(
            fixture.config,
            fixture.attempt,
            apply=True,
            allow_private_noncommercial_license=private_ack,
            allow_nonpromotable_material_conflict=material_ack,
        )
    assert not fixture.attempt.exists()


def test_attempt_and_input_path_redirects_are_refused(
    fixture: Fixture, tmp_path: pathlib.Path
) -> None:
    nested = fixture.config.run_parent / "nested"
    _mkdir(nested)
    with pytest.raises(overlay.OverlayError, match="direct child"):
        overlay.build_plan(fixture.config, nested / "hybrid-r3-camera-redirected")

    redirected_parent = tmp_path / "redirected-parent"
    _mkdir(redirected_parent)
    parent_link = tmp_path / "run-parent-link"
    parent_link.symlink_to(fixture.config.run_parent, target_is_directory=True)
    linked_config = dataclasses.replace(
        fixture.config,
        run_parent=parent_link,
    )
    with pytest.raises(overlay.OverlayError, match="symlink component"):
        overlay.build_plan(linked_config, parent_link / "hybrid-r3-camera-redirected")

    project_link = fixture.config.hybrid_root / "project-link"
    project_link.symlink_to(
        fixture.config.hybrid_project_root, target_is_directory=True
    )
    with pytest.raises(overlay.OverlayError, match="symlink component"):
        overlay.build_plan(
            dataclasses.replace(fixture.config, hybrid_project_root=project_link),
            fixture.attempt,
        )


@pytest.mark.parametrize("mutate", ["project", "plugin"])
def test_source_or_plugin_mutation_after_plan_is_refused_before_output(
    fixture: Fixture, mutate: str
) -> None:
    prepared = _apply_plan(fixture)
    target = (
        fixture.project_old_file if mutate == "project" else fixture.plugin_new_file
    )
    target.write_bytes(target.read_bytes() + b" mutation")

    with pytest.raises(overlay.OverlayError, match="differs"):
        overlay.apply_plan(prepared)
    assert not fixture.attempt.exists()


@pytest.mark.parametrize("unsafe", ["symlink", "special"])
def test_symlink_and_special_entries_are_rejected(
    fixture: Fixture, unsafe: str, tmp_path: pathlib.Path
) -> None:
    target = fixture.config.camera_plugin_root / "UnsafeEntry"
    if unsafe == "symlink":
        external = tmp_path / "external.bin"
        external.write_bytes(b"same machine, outside plugin")
        target.symlink_to(external)
        expected = "symlink"
    else:
        os.mkfifo(target, 0o600)
        expected = "special"

    with pytest.raises(overlay.OverlayError, match=expected):
        overlay.build_plan(fixture.config, fixture.attempt)
    assert not fixture.attempt.exists()


def test_exact_merge_excludes_old_plugin_and_preserves_new_and_empty_dirs(
    fixture: Fixture,
) -> None:
    source_before = _fingerprint(fixture.config.hybrid_root)
    plugin_before = _fingerprint(fixture.config.camera_plugin_root)
    receipt = overlay.apply_plan(_apply_plan(fixture))
    project = fixture.attempt / "project"

    assert not (project / "Plugins/VistaPlayableHome/Source/OldOnly.cpp").exists()
    assert (
        project / "Plugins/VistaPlayableHome/Source/NewOnly.cpp"
    ).read_bytes() == b"new only"
    assert (
        project / "Plugins/VistaPlayableHome/Source/Shared.cpp"
    ).read_bytes() == b"new camera-safe shared source"
    assert not (project / "Plugins/VistaPlayableHome/OldEmpty").exists()
    assert (project / "Plugins/VistaPlayableHome/Config/EmptyCameraDirectory").is_dir()
    assert (project / "Content/EmptyRoom").is_dir()
    assert (project / "Plugins/Other/Other.uplugin").is_file()

    observed = overlay.snapshot_tree(project, "test output", require_private_modes=True)
    overlay._assert_tree_pin(observed, fixture.config.output_project_pin, "test output")
    assert receipt["status"] == overlay.SUCCESS_STATUS
    assert _fingerprint(fixture.config.hybrid_root) == source_before
    assert _fingerprint(fixture.config.camera_plugin_root) == plugin_before


def test_output_collision_is_never_replaced(fixture: Fixture) -> None:
    prepared = _apply_plan(fixture)
    _mkdir(fixture.attempt)
    marker = fixture.attempt / "keep.txt"
    marker.write_text("do not replace", encoding="utf-8")

    with pytest.raises(overlay.OverlayError, match="already exists"):
        overlay.apply_plan(prepared)
    assert marker.read_text(encoding="utf-8") == "do not replace"


def test_host_receipt_is_append_only_private_and_honest(fixture: Fixture) -> None:
    receipt = overlay.apply_plan(_apply_plan(fixture))
    receipt_path = fixture.attempt / overlay.HOST_RECEIPT_NAME
    provisional_path = fixture.attempt / overlay.HOST_RECEIPT_PROVISIONAL_NAME
    parsed = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert parsed == receipt
    assert provisional_path.read_bytes() == receipt_path.read_bytes()
    assert os.lstat(provisional_path).st_ino == os.lstat(receipt_path).st_ino
    assert stat.S_IMODE(os.lstat(receipt_path).st_mode) == 0o600
    assert stat.S_IMODE(os.lstat(fixture.attempt).st_mode) == 0o700
    assert receipt["accepted_as_visual_evidence"] is False
    assert receipt["promotable"] is False
    assert receipt["diagnostic_only"] is True
    assert receipt["full_material_fidelity"] is False
    assert receipt["runtime_executed"] is False
    assert receipt["claims"] == {
        "camera_plugin_overlaid": True,
        "hybrid_project_preserved_except_exact_plugin_replacement": True,
        "gta_level": False,
        "real_human_present": False,
        "player_eye_reviewed": False,
        "interaction_proven": False,
        "visual_acceptance": False,
    }
    assert receipt["content_digest"] == overlay._content_digest(receipt)


def test_success_receipt_link_failure_leaves_only_provisional_and_failure(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse_publication(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("injected final-link failure")

    monkeypatch.setattr(overlay.os, "link", refuse_publication)
    with pytest.raises(OSError, match="final-link"):
        overlay.apply_plan(_apply_plan(fixture))

    assert not (fixture.attempt / overlay.HOST_RECEIPT_NAME).exists()
    assert (fixture.attempt / overlay.HOST_RECEIPT_PROVISIONAL_NAME).is_file()
    failure = json.loads(
        (fixture.attempt / overlay.HOST_FAILURE_NAME).read_text(encoding="utf-8")
    )
    assert failure["status"] == overlay.FAILURE_STATUS


def test_exception_after_success_link_never_adds_failure_disposition(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_publish = overlay._publish_exclusive_at

    def publish_then_interrupt(
        directory_fd: int,
        provisional_name: str,
        published_name: str,
        raw: bytes,
    ) -> str:
        real_publish(directory_fd, provisional_name, published_name, raw)
        raise KeyboardInterrupt

    monkeypatch.setattr(overlay, "_publish_exclusive_at", publish_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        overlay.apply_plan(_apply_plan(fixture))

    assert (fixture.attempt / overlay.HOST_RECEIPT_NAME).is_file()
    assert not (fixture.attempt / overlay.HOST_FAILURE_NAME).exists()


def test_attempt_open_failure_gets_parent_quarantine_receipt(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_open = overlay.os.open

    def refuse_attempt_directory(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if path == fixture.attempt.name and dir_fd is not None:
            raise OSError("injected attempt-open failure")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(overlay.os, "open", refuse_attempt_directory)
    with pytest.raises(OSError, match="attempt-open"):
        overlay.apply_plan(_apply_plan(fixture))

    parent_failure = fixture.config.run_parent / (
        fixture.attempt.name + overlay.PARENT_FAILURE_SUFFIX
    )
    assert fixture.attempt.is_dir()
    assert not (fixture.attempt / overlay.HOST_RECEIPT_NAME).exists()
    failure = json.loads(parent_failure.read_text(encoding="utf-8"))
    assert failure["status"] == overlay.FAILURE_STATUS


def test_recovered_attempt_binding_failure_closes_fd_and_uses_parent_quarantine(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_open = overlay.os.open
    real_assert_anchored = overlay._assert_anchored_path
    attempt_open_count = 0
    recovered_fd = -1

    def fail_first_attempt_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal attempt_open_count, recovered_fd
        if path == fixture.attempt.name and dir_fd is not None:
            attempt_open_count += 1
            if attempt_open_count == 1:
                raise OSError("injected first attempt-open failure")
            recovered_fd = real_open(path, flags, mode, dir_fd=dir_fd)
            return recovered_fd
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def fail_recovered_binding(path: pathlib.Path, descriptor: int, label: str) -> None:
        if label == "failed attempt root":
            raise overlay.OverlayError("injected recovered binding failure")
        real_assert_anchored(path, descriptor, label)

    monkeypatch.setattr(overlay.os, "open", fail_first_attempt_open)
    monkeypatch.setattr(overlay, "_assert_anchored_path", fail_recovered_binding)
    with pytest.raises(OSError, match="first attempt-open"):
        overlay.apply_plan(_apply_plan(fixture))

    parent_failure = fixture.config.run_parent / (
        fixture.attempt.name + overlay.PARENT_FAILURE_SUFFIX
    )
    assert recovered_fd >= 0
    assert not pathlib.Path(f"/proc/self/fd/{recovered_fd}").exists()
    assert parent_failure.is_file()
    assert not (fixture.attempt / overlay.HOST_RECEIPT_NAME).exists()


def test_cli_defaults_to_dry_run(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(overlay, "production_config", lambda: fixture.config)
    assert overlay.main(["--attempt-root", str(fixture.attempt)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "dry_run"
    assert not fixture.attempt.exists()


def test_implementation_never_shells_out_or_deletes() -> None:
    source_path = pathlib.Path(overlay.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden_attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"Popen", "run", "rmtree", "unlink", "remove", "system"}
    }

    assert "subprocess" not in imported
    assert forbidden_attributes == set()
