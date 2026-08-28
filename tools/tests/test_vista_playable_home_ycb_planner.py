from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib

import pytest

from tools.blender.vista_playable_home_ycb import planner


def _pin(path: pathlib.Path, raw: bytes) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {
        "path": path.as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _seal_and_write(path: pathlib.Path, contract: dict[str, object]) -> None:
    contract["content_digest"] = planner.content_digest(contract)
    path.write_bytes(planner.canonical_json_bytes(contract))


@pytest.fixture
def fixture_contract(tmp_path: pathlib.Path) -> dict[str, object]:
    contract = json.loads(planner.CONTRACT_PATH.read_text(encoding="utf-8"))
    root = tmp_path / "source"
    root.mkdir()
    revision = "1" * 40
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text(revision + "\n", encoding="ascii")
    contract_path = tmp_path / "contract.json"
    source = contract["source"]
    source["root"] = str(root)
    source["revision"] = revision
    license_raw = b"CC BY 4.0 synthetic fixture\n"
    readme_raw = b"Synthetic YCB planner fixture\n"
    license_pin = _pin(root / "LICENSE.txt", license_raw)
    readme_pin = _pin(root / "README.md", readme_raw)
    license_pin["path"] = "LICENSE.txt"
    readme_pin["path"] = "README.md"
    source["evidence"] = {"license": license_pin, "readme": readme_pin}

    source_bytes: dict[str, dict[str, bytes]] = {}
    total_bytes = 0
    for asset in contract["assets"]:
        asset_id = asset["asset_id"]
        config_raw = planner.canonical_json_bytes(asset["expected_config"])
        render_raw = f"synthetic-render:{asset_id}\n".encode()
        collision_raw = f"synthetic-collision:{asset_id}\n".encode()
        config_path = root.joinpath(
            *pathlib.PurePosixPath(asset["config"]["path"]).parts
        )
        render_path = root.joinpath(
            *pathlib.PurePosixPath(asset["render"]["path"]).parts
        )
        collision_path = root.joinpath(
            *pathlib.PurePosixPath(asset["collision"]["path"]).parts
        )
        config_pin = _pin(config_path, config_raw)
        render_pin = _pin(render_path, render_raw)
        collision_pin = _pin(collision_path, collision_raw)
        asset["config"] = config_pin
        asset["render"] = render_pin
        asset["collision"] = collision_pin
        # Pins are relative to source.root, never caller-selected absolute paths.
        for pin, path in (
            (config_pin, config_path),
            (render_pin, render_path),
            (collision_pin, collision_path),
        ):
            pin["path"] = path.relative_to(root).as_posix()
        source_bytes[asset_id] = {
            "config": config_raw,
            "render": render_raw,
            "collision": collision_raw,
        }
        total_bytes += len(config_raw) + len(render_raw) + len(collision_raw)
    contract["aggregate_evidence"]["pinned_source_bytes"] = total_bytes
    _seal_and_write(contract_path, contract)
    return {
        "contract": contract,
        "contract_path": contract_path,
        "root": root,
        "source_bytes": source_bytes,
    }


def _reloaded(fixture: dict[str, object]) -> dict[str, object]:
    return json.loads(
        pathlib.Path(fixture["contract_path"]).read_text(encoding="utf-8")
    )


def _rewrite_contract(fixture: dict[str, object], contract: dict[str, object]) -> None:
    contract["aggregate_evidence"]["pinned_source_bytes"] = sum(
        asset[pin_name]["bytes"]
        for asset in contract["assets"]
        for pin_name in ("config", "render", "collision")
    )
    _seal_and_write(pathlib.Path(fixture["contract_path"]), contract)


def _source_file(
    fixture: dict[str, object],
    contract: dict[str, object],
    asset_index: int,
    pin_name: str,
) -> pathlib.Path:
    pin = contract["assets"][asset_index][pin_name]
    return pathlib.Path(fixture["root"]).joinpath(
        *pathlib.PurePosixPath(pin["path"]).parts
    )


def test_production_contract_pins_exact_audited_kit() -> None:
    contract = planner.load_contract()
    assert contract["content_digest"] == planner.PINNED_SOURCE_CONTRACT_CONTENT_DIGEST
    assert (
        tuple(asset["asset_id"] for asset in contract["assets"])
        == planner.EXPECTED_ASSET_IDS
    )
    assert contract["aggregate_evidence"] == {
        "asset_count": 18,
        "pinned_source_file_count": 54,
        "pinned_source_bytes": 102_844_700,
        "render_triangle_count": 58_968,
        "initial_interaction_candidates": list(planner.EXPECTED_INTERACTIVE_IDS),
    }
    assert contract["license"]["spdx"] == "CC-BY-4.0"
    assert contract["blender"]["version"] == "4.5.8"


def test_production_contract_has_an_independent_trust_pin(
    fixture_contract: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    contract_path = pathlib.Path(fixture_contract["contract_path"])
    monkeypatch.setattr(planner, "CONTRACT_PATH", contract_path)
    with pytest.raises(planner.YcbPreparationError, match="CONTRACT_TRUST_PIN_DRIFT"):
        planner.load_contract(contract_path)


def test_dry_run_is_deterministic_and_makes_zero_writes(
    fixture_contract: dict[str, object], tmp_path: pathlib.Path
) -> None:
    attempt = tmp_path / "must-remain-absent"
    kwargs = {
        "contract_path": pathlib.Path(fixture_contract["contract_path"]),
        "source_root": pathlib.Path(fixture_contract["root"]),
        "attempt_root": attempt,
    }
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    first = planner.build_plan(**kwargs)
    second = planner.build_plan(**kwargs)
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert first == second
    assert before == after
    assert not attempt.exists()
    assert first["claims"] == {
        "source_bytes_verified": True,
        "blender_executed": False,
        "full_pbr_verified": False,
        "ue_imported": False,
        "ue_interactions_verified": False,
        "gta_level_quality": False,
    }


def test_plan_encodes_metric_ucx_texture_and_safe_ue_policy(
    fixture_contract: dict[str, object], tmp_path: pathlib.Path
) -> None:
    plan = planner.build_plan(
        contract_path=pathlib.Path(fixture_contract["contract_path"]),
        attempt_root=tmp_path / "attempt",
    )
    contract = fixture_contract["contract"]
    by_id = {asset["asset_id"]: asset for asset in plan["assets"]}
    for source in contract["assets"]:
        item = by_id[source["asset_id"]]
        assert item["source_transport"] == {
            "render": "byte_identical_rename_from_glb_orig_to_glb",
            "textures": "preserve_embedded_4096x4096_png_without_resampling",
            "material_scope": "verified_base_color_only_not_full_pbr",
        }
        assert item["blender_4_5_8_plan"]["scene_units"] == {
            "system": "METRIC",
            "length": "METERS",
            "scale_length": 1,
        }
        assert (
            len(item["blender_4_5_8_plan"]["ucx_objects"])
            == source["collision_geometry"]["convex_parts"]
        )
        assert item["ue_policy"]["mobility"] == "Movable"
        assert item["ue_policy"]["simulate_physics"] is False
        assert "ue_import_and_lod_validation" in item["known_missing_work"]


def test_apply_requires_exact_cc_by_ack_before_any_write(
    fixture_contract: dict[str, object], tmp_path: pathlib.Path
) -> None:
    attempt = tmp_path / "attempt"
    plan = planner.build_plan(
        contract_path=pathlib.Path(fixture_contract["contract_path"]),
        attempt_root=attempt,
    )
    with pytest.raises(planner.YcbPreparationError, match="ATTRIBUTION_ACK_REQUIRED"):
        planner.apply_preparation(
            plan,
            acknowledgement=None,
            contract_path=pathlib.Path(fixture_contract["contract_path"]),
        )
    assert not attempt.exists()


def test_apply_creates_one_fresh_append_only_preparation_attempt(
    fixture_contract: dict[str, object], tmp_path: pathlib.Path
) -> None:
    attempt = tmp_path / "attempt"
    contract_path = pathlib.Path(fixture_contract["contract_path"])
    plan = planner.build_plan(contract_path=contract_path, attempt_root=attempt)
    receipt = planner.apply_preparation(
        plan,
        acknowledgement=planner.ACKNOWLEDGEMENT_TEXT,
        contract_path=contract_path,
    )
    assert receipt["status"] == "source_bytes_prepared_blender_and_ue_not_executed"
    assert receipt["asset_count"] == 18
    assert receipt["claims"]["ue_imported"] is False
    published = attempt / planner.PREPARATION_RECEIPT_NAME
    provisional = attempt / planner.PREPARATION_RECEIPT_PROVISIONAL_NAME
    assert published.read_bytes() == provisional.read_bytes()
    assert os.lstat(published).st_ino == os.lstat(provisional).st_ino
    for asset in fixture_contract["contract"]["assets"]:
        staged = attempt / "assets" / asset["slug"]
        expected = fixture_contract["source_bytes"][asset["asset_id"]]
        assert (staged / "source-config.json").read_bytes() == expected["config"]
        assert (staged / "render.glb").read_bytes() == expected["render"]
        assert (staged / "collision.glb").read_bytes() == expected["collision"]
    with pytest.raises(planner.YcbPreparationError, match="OUTPUT_ALREADY_EXISTS"):
        planner.apply_preparation(
            plan,
            acknowledgement=planner.ACKNOWLEDGEMENT_TEXT,
            contract_path=contract_path,
        )


def test_apply_rejects_attempt_inside_source_or_another_git_checkout(
    fixture_contract: dict[str, object], tmp_path: pathlib.Path
) -> None:
    contract_path = pathlib.Path(fixture_contract["contract_path"])
    source_root = pathlib.Path(fixture_contract["root"])
    inside_source = source_root / "forbidden-attempt"
    source_plan = planner.build_plan(
        contract_path=contract_path, attempt_root=inside_source
    )
    with pytest.raises(
        planner.YcbPreparationError, match="OUTPUT_INSIDE_PROTECTED_SOURCE"
    ):
        planner.apply_preparation(
            source_plan,
            acknowledgement=planner.ACKNOWLEDGEMENT_TEXT,
            contract_path=contract_path,
        )
    assert not inside_source.exists()

    other_checkout = tmp_path / "other-checkout"
    (other_checkout / ".git").mkdir(parents=True)
    inside_other_checkout = other_checkout / "forbidden-attempt"
    checkout_plan = planner.build_plan(
        contract_path=contract_path, attempt_root=inside_other_checkout
    )
    with pytest.raises(
        planner.YcbPreparationError, match="OUTPUT_INSIDE_GIT_REPOSITORY"
    ):
        planner.apply_preparation(
            checkout_plan,
            acknowledgement=planner.ACKNOWLEDGEMENT_TEXT,
            contract_path=contract_path,
        )
    assert not inside_other_checkout.exists()


@pytest.mark.parametrize("drift", ["bytes", "hash"])
def test_source_integrity_drift_fails_closed(
    fixture_contract: dict[str, object], drift: str
) -> None:
    contract = _reloaded(fixture_contract)
    if drift == "bytes":
        contract["assets"][0]["render"]["bytes"] += 1
    else:
        contract["assets"][0]["render"]["sha256"] = "f" * 64
    _rewrite_contract(fixture_contract, contract)
    expected = "SOURCE_BYTE_DRIFT" if drift == "bytes" else "SOURCE_HASH_DRIFT"
    with pytest.raises(planner.YcbPreparationError, match=expected):
        planner.build_plan(
            contract_path=pathlib.Path(fixture_contract["contract_path"])
        )


def test_config_asset_redirect_fails_even_when_file_pin_is_updated(
    fixture_contract: dict[str, object],
) -> None:
    contract = _reloaded(fixture_contract)
    path = _source_file(fixture_contract, contract, 0, "config")
    redirected = copy.deepcopy(contract["assets"][0]["expected_config"])
    redirected["render_asset"] = "../meshes/redirected.glb"
    raw = planner.canonical_json_bytes(redirected)
    path.write_bytes(raw)
    contract["assets"][0]["config"]["bytes"] = len(raw)
    contract["assets"][0]["config"]["sha256"] = hashlib.sha256(raw).hexdigest()
    _rewrite_contract(fixture_contract, contract)
    with pytest.raises(planner.YcbPreparationError, match="CONFIG_REDIRECT_OR_DRIFT"):
        planner.build_plan(
            contract_path=pathlib.Path(fixture_contract["contract_path"])
        )


@pytest.mark.parametrize("replacement", ["symlink", "hardlink", "fifo"])
def test_redirects_links_and_special_files_are_rejected(
    fixture_contract: dict[str, object], replacement: str
) -> None:
    contract = _reloaded(fixture_contract)
    target = _source_file(fixture_contract, contract, 0, "render")
    raw = target.read_bytes()
    target.unlink()
    if replacement == "symlink":
        backup = target.with_name("render-backup.glb.orig")
        backup.write_bytes(raw)
        target.symlink_to(backup.name)
        error = "SYMLINK_REJECTED"
    elif replacement == "hardlink":
        seed = target.with_name("render-hardlink-seed.glb.orig")
        seed.write_bytes(raw)
        os.link(seed, target)
        error = "HARDLINK_REJECTED"
    else:
        os.mkfifo(target)
        error = "SPECIAL_FILE_REJECTED"
    with pytest.raises(planner.YcbPreparationError, match=error):
        planner.build_plan(
            contract_path=pathlib.Path(fixture_contract["contract_path"])
        )


def test_casefold_source_path_collision_is_rejected(
    fixture_contract: dict[str, object],
) -> None:
    contract = _reloaded(fixture_contract)
    original = contract["assets"][0]["render"]["path"]
    contract["assets"][1]["render"]["path"] = original.swapcase()
    _rewrite_contract(fixture_contract, contract)
    with pytest.raises(planner.YcbPreparationError, match="CASE_COLLISION"):
        planner.build_plan(
            contract_path=pathlib.Path(fixture_contract["contract_path"])
        )


def test_revision_drift_is_rejected(fixture_contract: dict[str, object]) -> None:
    root = pathlib.Path(fixture_contract["root"])
    (root / ".git" / "HEAD").write_text("2" * 40 + "\n", encoding="ascii")
    with pytest.raises(planner.YcbPreparationError, match="SOURCE_REVISION_DRIFT"):
        planner.build_plan(
            contract_path=pathlib.Path(fixture_contract["contract_path"])
        )


def test_duplicate_json_key_and_contract_digest_drift_are_rejected(
    fixture_contract: dict[str, object],
) -> None:
    contract_path = pathlib.Path(fixture_contract["contract_path"])
    raw = contract_path.read_text(encoding="utf-8")
    duplicate = raw.replace(
        '"schema_version":', '"schema_version": "duplicate", "schema_version":', 1
    )
    contract_path.write_text(duplicate, encoding="utf-8")
    with pytest.raises(planner.YcbPreparationError, match="DUPLICATE_JSON_KEY"):
        planner.load_contract(contract_path)
    contract = fixture_contract["contract"]
    _seal_and_write(contract_path, contract)
    contract["profile_id"] = "drifted-without-reseal"
    contract_path.write_bytes(planner.canonical_json_bytes(contract))
    with pytest.raises(planner.YcbPreparationError, match="CONTRACT_DIGEST_DRIFT"):
        planner.load_contract(contract_path)


def test_partial_apply_is_preserved_and_quarantined(
    fixture_contract: dict[str, object],
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt = tmp_path / "attempt"
    contract_path = pathlib.Path(fixture_contract["contract_path"])
    plan = planner.build_plan(contract_path=contract_path, attempt_root=attempt)
    original = planner._write_exclusive
    failed = False

    def fault(path: pathlib.Path, raw: bytes) -> None:
        nonlocal failed
        if path.name == "render.glb" and not failed:
            failed = True
            raise OSError("injected write fault")
        original(path, raw)

    monkeypatch.setattr(planner, "_write_exclusive", fault)
    with pytest.raises(OSError, match="injected write fault"):
        planner.apply_preparation(
            plan,
            acknowledgement=planner.ACKNOWLEDGEMENT_TEXT,
            contract_path=contract_path,
        )
    assert attempt.is_dir()
    quarantine = json.loads((attempt / "_QUARANTINED.json").read_text(encoding="utf-8"))
    assert quarantine["status"] == "incomplete_do_not_consume"
    assert not (attempt / planner.PREPARATION_RECEIPT_NAME).exists()


@pytest.mark.parametrize("fault", ["write", "fsync", "link"])
def test_receipt_publication_fault_never_exposes_final_success(
    fixture_contract: dict[str, object],
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    attempt = tmp_path / "attempt"
    contract_path = pathlib.Path(fixture_contract["contract_path"])
    plan = planner.build_plan(contract_path=contract_path, attempt_root=attempt)

    if fault == "write":
        original_write = planner._write_exclusive

        def fail_after_provisional_write(path: pathlib.Path, raw: bytes) -> str:
            digest = original_write(path, raw)
            if path.name == planner.PREPARATION_RECEIPT_PROVISIONAL_NAME:
                raise OSError("injected provisional write fault")
            return digest

        monkeypatch.setattr(planner, "_write_exclusive", fail_after_provisional_write)
    elif fault == "fsync":
        original_fsync = planner.os.fsync

        def fail_provisional_fsync(descriptor: int) -> None:
            target = os.readlink(f"/proc/self/fd/{descriptor}")
            if target.endswith(planner.PREPARATION_RECEIPT_PROVISIONAL_NAME):
                raise OSError("injected provisional fsync fault")
            original_fsync(descriptor)

        monkeypatch.setattr(planner.os, "fsync", fail_provisional_fsync)
    else:
        monkeypatch.setattr(
            planner.os,
            "link",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                OSError("injected receipt link fault")
            ),
        )

    with pytest.raises(OSError, match="injected"):
        planner.apply_preparation(
            plan,
            acknowledgement=planner.ACKNOWLEDGEMENT_TEXT,
            contract_path=contract_path,
        )
    assert not (attempt / planner.PREPARATION_RECEIPT_NAME).exists()
    assert (attempt / planner.QUARANTINE_NAME).is_file()


def test_exception_after_atomic_receipt_link_never_adds_quarantine(
    fixture_contract: dict[str, object],
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt = tmp_path / "attempt"
    contract_path = pathlib.Path(fixture_contract["contract_path"])
    plan = planner.build_plan(contract_path=contract_path, attempt_root=attempt)
    original_publish = planner._publish_receipt

    def publish_then_interrupt(target: pathlib.Path, raw: bytes) -> None:
        original_publish(target, raw)
        raise KeyboardInterrupt

    monkeypatch.setattr(planner, "_publish_receipt", publish_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        planner.apply_preparation(
            plan,
            acknowledgement=planner.ACKNOWLEDGEMENT_TEXT,
            contract_path=contract_path,
        )
    assert (attempt / planner.PREPARATION_RECEIPT_NAME).is_file()
    assert not (attempt / planner.QUARANTINE_NAME).exists()
