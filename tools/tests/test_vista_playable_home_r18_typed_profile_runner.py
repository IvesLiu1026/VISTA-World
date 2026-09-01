from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import pathlib

import pytest

from tools.tests.test_vista_playable_home_build_home import Fixture as BuildFixture
from tools.ue.vista_playable_home import build_home, planning


ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/composition_profiles"
    / "vista_home_typed_scene_r18.json"
).resolve(strict=True)
VISUAL_PROFILE_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/visual_profiles"
    / "realistic_interior_r2.json"
).resolve(strict=True)
REALISM_R4_PROFILE_PATH = (
    ROOT
    / "world_packs/vista_playable_home_r1/visual_profiles"
    / "realistic_interior_r4.json"
).resolve(strict=True)


def _seal_profile(value: dict) -> dict:
    sealed = copy.deepcopy(value)
    body = copy.deepcopy(sealed)
    body.pop("content_digest", None)
    sealed["content_digest"] = hashlib.sha256(planning.canonical_json(body)).hexdigest()
    return sealed


def _write_profile(
    root: pathlib.Path,
    name: str,
    value: dict,
) -> tuple[pathlib.Path, str]:
    path = (root / name).resolve()
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path, build_home.sha256_file(path)


def _with_profile(
    fixture: BuildFixture,
    *,
    path: pathlib.Path = PROFILE_PATH,
    sha256: str | None = None,
) -> build_home.BuildConfig:
    return dataclasses.replace(
        fixture.config(),
        typed_scene_profile=path,
        typed_scene_profile_sha256=(
            build_home.sha256_file(path) if sha256 is None else sha256
        ),
    )


def test_optional_profile_keeps_legacy_execution_shape_absent(
    tmp_path: pathlib.Path,
) -> None:
    fixture = BuildFixture(tmp_path)
    planned = build_home.plan_build(fixture.config())

    assert planned.typed_scene_profile is None
    assert planned.typed_scene_profile_raw is None
    assert set(planned.execution) == {
        "schema_version",
        "attempt_root",
        "project_file",
        "project_sha256",
        "build_plan_path",
        "build_plan_sha256",
        "build_plan_content_digest",
        "composition_spec",
        "composition_spec_sha256",
        "artifact_bindings",
        "scripts",
        "import_receipt",
        "scene_receipt",
        "policy",
    }
    assert "typed_scene_profile" not in planned.execution
    assert "typed_scene_profile" not in planned.dry_run_report["inputs"]
    assert "typed_scene_profile_id" not in planned.execution["composition_spec"]
    assert (
        planned.execution["composition_spec"]
        == planning.build_composition_spec(fixture.plan).value
    )


def test_profile_is_exactly_pinned_compiled_reported_and_materialized(
    tmp_path: pathlib.Path,
) -> None:
    fixture = BuildFixture(tmp_path)
    source_raw = PROFILE_PATH.read_bytes()
    source_sha = hashlib.sha256(source_raw).hexdigest()

    planned = build_home.plan_build(_with_profile(fixture, sha256=source_sha))

    profile = json.loads(source_raw.decode("utf-8"))
    staged = fixture.attempt / "contracts" / build_home.TYPED_SCENE_PROFILE_ATTEMPT_FILE
    descriptor = {
        "path": str(staged),
        "sha256": source_sha,
        "schema_version": planning.TYPED_SCENE_PROFILE_SCHEMA,
        "profile_id": "vista_home_typed_scene_r18",
        "content_digest": profile["content_digest"],
    }
    assert planned.typed_scene_profile == profile
    assert planned.typed_scene_profile_raw == source_raw
    assert planned.execution["typed_scene_profile"] == descriptor
    assert planned.execution["composition_spec"]["typed_scene_profile_id"] == (
        "vista_home_typed_scene_r18"
    )
    assert (
        planned.execution["composition_spec"]["typed_scene_profile_content_digest"]
        == profile["content_digest"]
    )
    kinds = {
        operation["kind"]
        for operation in planned.execution["composition_spec"]["operations"]
    }
    assert {
        "place_typed_anchor",
        "place_typed_liquid_source",
        "place_typed_liquid_receiver",
    } <= kinds
    assert planned.dry_run_report["inputs"]["typed_scene_profile"] == {
        **descriptor,
        "path": str(PROFILE_PATH),
        "staged_path": str(staged),
    }

    attempt, _copy_counts = build_home._materialize_inputs(planned)

    assert staged.read_bytes() == source_raw
    assert staged.stat().st_mode & 0o777 == 0o600
    assert (attempt / "execution.json").read_bytes() == planned.execution_raw
    materialized = json.loads((attempt / "execution.json").read_text())
    assert materialized["typed_scene_profile"] == descriptor
    preparation = json.loads((attempt / "preparation-receipt.json").read_text())
    assert preparation["typed_scene_profile_sha256"] == source_sha
    assert (
        preparation["typed_scene_profile_content_digest"] == profile["content_digest"]
    )


def test_materialized_contract_rechecks_profile_bytes_and_identity(
    tmp_path: pathlib.Path,
) -> None:
    fixture = BuildFixture(tmp_path)
    planned = build_home.plan_build(_with_profile(fixture))
    attempt, _copy_counts = build_home._materialize_inputs(planned)
    staged = attempt / "contracts" / build_home.TYPED_SCENE_PROFILE_ATTEMPT_FILE

    def compile_contract(
        *,
        sha256: str,
        profile: dict | None = None,
    ) -> build_home.contract.ExecutionManifest:
        return build_home.contract.build_execution_manifest(
            build_plan_path=attempt / "contracts/build-plan.json",
            build_plan=planned.plan,
            project_file=attempt / "project/VistaPlayableHome.uproject",
            attempt_root=attempt,
            artifact_bindings=planned.bindings,
            import_receipt=attempt / "import-receipt.json",
            scene_receipt=attempt / "scene-receipt.json",
            typed_scene_profile=(
                planned.typed_scene_profile if profile is None else profile
            ),
            typed_scene_profile_path=staged,
            typed_scene_profile_sha256=sha256,
        )

    regenerated = compile_contract(sha256=build_home.sha256_file(PROFILE_PATH))
    assert regenerated.raw == planned.execution_raw

    with pytest.raises(
        build_home.contract.VistaPlayableHomeContractError,
        match="TYPED_SCENE_PIN_MISMATCH",
    ):
        compile_contract(sha256="0" * 64)

    different = copy.deepcopy(planned.typed_scene_profile)
    different["profile_id"] = "different_typed_scene_profile"
    different = _seal_profile(different)
    staged.write_text(
        json.dumps(different, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        build_home.contract.VistaPlayableHomeContractError,
        match="TYPED_SCENE_PIN_MISMATCH",
    ):
        compile_contract(sha256=build_home.sha256_file(staged))
    with pytest.raises(
        build_home.contract.VistaPlayableHomeContractError,
        match="TYPED_SCENE_PROFILE_INVALID",
    ):
        compile_contract(
            sha256=build_home.sha256_file(staged),
            profile=different,
        )


def test_typed_profile_composes_with_existing_r2_and_r4_pins(
    tmp_path: pathlib.Path,
) -> None:
    fixture = BuildFixture(tmp_path)
    config = dataclasses.replace(
        _with_profile(fixture),
        visual_profile=VISUAL_PROFILE_PATH,
        visual_profile_sha256=build_home.sha256_file(VISUAL_PROFILE_PATH),
        realism_r4_profile=REALISM_R4_PROFILE_PATH,
        realism_r4_profile_sha256=build_home.sha256_file(REALISM_R4_PROFILE_PATH),
    )

    planned = build_home.plan_build(config)

    assert planned.execution["typed_scene_profile"]["profile_id"] == (
        "vista_home_typed_scene_r18"
    )
    assert planned.execution["visual_profile_path"].endswith(
        "/contracts/visual-profile.json"
    )
    assert planned.execution["realism_r4_profile"]["profile_id"] == (
        build_home.REALISM_R4_PROFILE_ID
    )
    attempt, _copy_counts = build_home._materialize_inputs(planned)
    assert (attempt / "execution.json").read_bytes() == planned.execution_raw
    assert (
        attempt / "contracts" / build_home.TYPED_SCENE_PROFILE_ATTEMPT_FILE
    ).read_bytes() == PROFILE_PATH.read_bytes()


def test_profile_path_and_sha_must_be_paired(tmp_path: pathlib.Path) -> None:
    fixture = BuildFixture(tmp_path)
    source_sha = build_home.sha256_file(PROFILE_PATH)

    with pytest.raises(build_home.BuildHomeError, match="PIN_INVALID"):
        build_home.plan_build(
            dataclasses.replace(
                fixture.config(),
                typed_scene_profile=PROFILE_PATH,
            )
        )
    with pytest.raises(build_home.BuildHomeError, match="ARGUMENT_INVALID"):
        build_home.plan_build(
            dataclasses.replace(
                fixture.config(),
                typed_scene_profile_sha256=source_sha,
            )
        )


def test_wrong_sha_profile_identity_house_and_digest_fail_closed(
    tmp_path: pathlib.Path,
) -> None:
    fixture = BuildFixture(tmp_path)

    with pytest.raises(build_home.BuildHomeError, match="PIN_MISMATCH"):
        build_home.plan_build(_with_profile(fixture, sha256="0" * 64))

    original = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

    wrong_identity = copy.deepcopy(original)
    wrong_identity["profile_id"] = "different_typed_scene_profile"
    wrong_identity = _seal_profile(wrong_identity)
    wrong_identity_path, wrong_identity_sha = _write_profile(
        tmp_path, "wrong-identity.json", wrong_identity
    )
    with pytest.raises(
        build_home.BuildHomeError,
        match="TYPED_SCENE_PROFILE_INVALID.*profile ID differs",
    ):
        build_home.plan_build(
            _with_profile(
                fixture,
                path=wrong_identity_path,
                sha256=wrong_identity_sha,
            )
        )

    wrong_house = copy.deepcopy(original)
    wrong_house["house_binding"]["content_digest"] = "f" * 64
    wrong_house = _seal_profile(wrong_house)
    wrong_house_path, wrong_house_sha = _write_profile(
        tmp_path, "wrong-house.json", wrong_house
    )
    with pytest.raises(
        build_home.BuildHomeError,
        match="TYPED_SCENE_HOUSE_MISMATCH",
    ):
        build_home.plan_build(
            _with_profile(
                fixture,
                path=wrong_house_path,
                sha256=wrong_house_sha,
            )
        )

    wrong_digest = copy.deepcopy(original)
    wrong_digest["content_digest"] = "f" * 64
    wrong_digest_path, wrong_digest_sha = _write_profile(
        tmp_path, "wrong-digest.json", wrong_digest
    )
    with pytest.raises(
        build_home.BuildHomeError,
        match="content digest differs",
    ):
        build_home.plan_build(
            _with_profile(
                fixture,
                path=wrong_digest_path,
                sha256=wrong_digest_sha,
            )
        )
