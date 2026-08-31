from __future__ import annotations

import ast
import copy
import hashlib
from pathlib import Path

import pytest

from tools.animation.vista_playable_home_cc0 import vertical_slice as r8_slice
from tools.animation.vista_playable_home_cc0_detail_actions_r14 import plan as r14
from tools.animation.vista_playable_home_cc0_detail_actions_r15 import plan as r15


WORKER_PATH = (
    r15.REPOSITORY_ROOT
    / "tools/blender/vista_playable_home_makehuman_cc0_detail_actions_r15"
    / "blender_worker.py"
)
ANIMATION_COMPONENT_PATH = (
    r15.REPOSITORY_ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Private"
    / "VistaAnimationComponent.cpp"
)


def _reseal(value: dict[str, object]) -> dict[str, object]:
    value["content_digest"] = r15.content_digest(value)
    return value


def test_profile_is_closed_fresh_r15_authority() -> None:
    profile = r15.load_profile()

    assert profile["schema_version"] == r15.PROFILE_SCHEMA_VERSION
    assert profile["profile_id"] == r15.PROFILE_ID
    assert profile["character_id"] == r15.CHARACTER_ID
    assert profile["acceptance"] == r15.ACCEPTANCE
    assert profile["namespace_contract"] == {
        "source_namespace": "vista.makehuman-cc0-detail-actions/r15",
        "ue_content_namespace": "/Game/VISTA/MakeHumanCC0/R15/DetailActions",
        "artifact_namespace": "makehuman_cc0_detail_actions_r15",
        "existing_r8_or_r14_bytes_reused": False,
    }
    assert profile["source_character_binding"] == {
        "source_character_asset_lane": "makehuman_cc0_character_r6",
        "character_id": r15.CHARACTER_ID,
        "armature_name": r15.EXPORT_ARMATURE_NAME,
        "bone_count": 53,
        "motion_source_policy": "fresh_numeric_recipes_only",
        "prior_animation_artifact_dependency": "none",
    }
    assert profile["target_height_bands"] == r15.HEIGHT_BANDS
    assert profile["license_scope"] == r15.LICENSE_SCOPE
    assert profile["provenance"] == r15.PROVENANCE
    assert profile["content_digest"] == r15.content_digest(profile)


def test_profile_rejects_unknown_fields_and_acceptance_escalation() -> None:
    profile = copy.deepcopy(r15.load_profile())
    profile["unexpected"] = True
    _reseal(profile)

    with pytest.raises(r15.DetailActionR15Error) as error:
        r15.validate_profile(profile)
    assert error.value.code == "PROFILE_SCHEMA_INVALID"

    profile = copy.deepcopy(r15.load_profile())
    profile["acceptance"]["accepted"] = True
    _reseal(profile)
    with pytest.raises(r15.DetailActionR15Error) as error:
        r15.validate_profile(profile)
    assert error.value.code == "PROFILE_SCHEMA_INVALID"


@pytest.mark.parametrize(
    "mutation,code",
    [
        (
            lambda value: value["clips"][0]["runtime_binding"].update(
                {
                    "backend_status": "source_only_unimplemented",
                    "contact_signal_authority": "r15_source_contract_only",
                    "completion_signal_authority": "r15_source_contract_only",
                }
            ),
            "RUNTIME_BINDING_INVALID",
        ),
        (
            lambda value: value["clips"][3]["runtime_binding"].update(
                {
                    "backend_status": "typed_backend_available",
                    "contact_signal_authority": "UVistaAnimationComponent::ContactSignalFor",
                    "completion_signal_authority": "UVistaAnimationComponent::CompletionSignalFor",
                }
            ),
            "RUNTIME_BINDING_INVALID",
        ),
        (
            lambda value: value["clips"][5]["target"].update(
                {"actor_hand": "right", "hand_bone": "hand_r"}
            ),
            "TARGET_CONTACT_CONTRACT_INVALID",
        ),
        (
            lambda value: value["clips"][6].__setitem__("loop", False),
            "LOOP_POLICY_INVALID",
        ),
        (
            lambda value: value["clips"][8]["typed_notifies"][0].__setitem__(
                "signal", "vista_pickup_contact"
            ),
            "TYPED_NOTIFY_INVALID",
        ),
    ],
)
def test_semantic_profile_mutations_fail_closed(mutation, code: str) -> None:
    profile = copy.deepcopy(r15.load_profile())
    mutation(profile)
    _reseal(profile)

    with pytest.raises(r15.DetailActionR15Error) as error:
        r15.validate_profile(profile)
    assert error.value.code == code


def test_exact_nine_action_target_and_backend_partition() -> None:
    clips = {clip["clip_id"]: clip for clip in r15.load_profile()["clips"]}

    assert tuple(clips) == r15.EXPECTED_CLIPS
    assert {clip["target"]["height_band"] for clip in clips.values()} == {
        "counter",
        "waist",
        "seat",
    }
    assert {
        clip_id
        for clip_id, clip in clips.items()
        if clip["runtime_binding"]["backend_status"] == "typed_backend_available"
    } == r15._TYPED_BACKEND_CLIPS
    assert all(
        clip["runtime_binding"]["runtime_execution_authorized"] is False
        for clip in clips.values()
    )
    assert clips["sit_down_chair"]["target"]["primary_contact_bone"] == "pelvis"
    assert clips["seated_idle_loop"]["loop"] is True
    assert all(
        clip["target"]["hand_bone"] == "hand_r"
        for clip_id, clip in clips.items()
        if clip_id.endswith("_right")
    )


def test_typed_appliance_signals_match_runtime_authority() -> None:
    source = ANIMATION_COMPONENT_PATH.read_text(encoding="utf-8")
    clips = {clip["clip_id"]: clip for clip in r15.load_profile()["clips"]}
    expected = {
        "vista_appliance_power_contact",
        "vista_appliance_turn_on_completed",
        "vista_appliance_turn_off_completed",
        "vista_appliance_button_contact",
        "vista_appliance_press_completed",
    }

    assert expected <= {
        notify["signal"]
        for clip_id in r15._TYPED_BACKEND_CLIPS
        for notify in clips[clip_id]["typed_notifies"]
    }
    assert all(f'TEXT("{signal}")' in source for signal in expected)
    assert all(
        clip["runtime_binding"]["backend_status"] == "source_only_unimplemented"
        for clip_id, clip in clips.items()
        if clip_id not in r15._TYPED_BACKEND_CLIPS
    )


def test_numeric_recipes_have_phases_contact_bones_and_no_root() -> None:
    plan = r15.build_plan()

    assert len(r15.EXPECTED_BONES) == 53
    assert tuple(plan["rig_bone_names"]) == r15.EXPECTED_BONES
    for clip in plan["clips"]:
        frames = [keyframe["frame"] for keyframe in clip["keyframes"]]
        phases = clip["phase_contract"]
        assert frames[0] == 0
        assert frames[-1] == clip["frame_end"]
        assert {
            phases["anticipation_end_frame"],
            phases["engagement_frame"],
            phases["follow_through_start_frame"],
            phases["completion_frame"],
        } <= set(frames)
        assert all("root" not in keyframe["bones"] for keyframe in clip["keyframes"])
        engagement = next(
            keyframe
            for keyframe in clip["keyframes"]
            if keyframe["frame"] == phases["engagement_frame"]
        )
        assert clip["target"]["primary_contact_bone"] in engagement["bones"]
        r15._validate_keyframes(clip)


def test_r15_recipes_are_distinct_from_r8_and_r14() -> None:
    plan = r15.build_plan()
    r15_digests = {clip["numeric_recipe_sha256"] for clip in plan["clips"]}
    prior_digests = {
        hashlib.sha256(r15.canonical_json(keyframes)).hexdigest()
        for keyframes in (
            *r8_slice.MOTION_KEYFRAMES.values(),
            *r14.MOTION_RECIPES.values(),
        )
    }

    assert len(r15_digests) == 9
    assert r15_digests.isdisjoint(prior_digests)
    assert all(
        all(
            token not in clip["recipe_id"]
            for token in ("mug_", "pickup", "place", "fridge", "inspect", "_r14")
        )
        for clip in plan["clips"]
    )


def test_keyframe_validation_rejects_root_motion_contact_loss_and_bad_loop() -> None:
    plan = r15.build_plan()

    root_motion = copy.deepcopy(plan["clips"][0])
    root_motion["keyframes"][1]["bones"]["root"] = {
        "rotation_deg_xyz": [0.0, 0.0, 0.0],
        "location_m": [0.0, 0.1, 0.0],
    }
    with pytest.raises(r15.DetailActionR15Error) as error:
        r15._validate_keyframes(root_motion)
    assert error.value.code == "ROOT_MOTION_OR_BONE_INVALID"

    missing_contact = copy.deepcopy(plan["clips"][2])
    engagement = missing_contact["phase_contract"]["engagement_frame"]
    next(
        keyframe
        for keyframe in missing_contact["keyframes"]
        if keyframe["frame"] == engagement
    )["bones"].pop("hand_r")
    with pytest.raises(r15.DetailActionR15Error) as error:
        r15._validate_keyframes(missing_contact)
    assert error.value.code == "CONTACT_BONE_KEYFRAME_MISSING"

    bad_loop = copy.deepcopy(plan["clips"][6])
    bad_loop["keyframes"][-1]["bones"]["head"]["rotation_deg_xyz"][0] = 5.0
    with pytest.raises(r15.DetailActionR15Error) as error:
        r15._validate_keyframes(bad_loop)
    assert error.value.code == "LOOP_SEAM_INVALID"


def test_duplicate_and_non_finite_json_fail_before_semantic_validation(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"value":1,"value":2}', encoding="utf-8")
    with pytest.raises(r15.DetailActionR15Error) as error:
        r15.load_json(duplicate)
    assert error.value.code == "JSON_DUPLICATE_KEY"

    non_finite = tmp_path / "non-finite.json"
    non_finite.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(r15.DetailActionR15Error) as error:
        r15.load_json(non_finite)
    assert error.value.code == "JSON_NON_FINITE"


def test_dry_run_plan_is_sealed_and_never_claims_execution() -> None:
    plan = r15.build_plan()

    assert plan["schema_version"] == r15.PLAN_SCHEMA_VERSION
    assert plan["mode"] == "dry_run"
    assert plan["status"] == "dry_run_validated_no_write"
    assert plan["will_write"] is False
    assert plan["will_execute_blender"] is False
    assert plan["acceptance"] == r15.ACCEPTANCE
    assert plan["output"] == {
        "destination_root": None,
        "blend_relative_path": "blend/vista_cc0_detail_actions_r15.blend",
        "preview_relative_path": "preview/vista_cc0_detail_actions_r15_contact_sheet.png",
        "external_binary_policy": "outside_git_only",
    }
    assert not any(plan["claims"].values())
    assert plan["content_digest"] == r15.content_digest(plan)
    r15.validate_plan(plan)


def test_execute_plan_only_allows_fresh_external_destination(tmp_path: Path) -> None:
    destination = tmp_path / "fresh-r15-candidate"
    plan = r15.build_plan(mode="execute", destination_root=destination)

    assert plan["mode"] == "execute"
    assert plan["status"] == "execution_plan_only_not_run"
    assert plan["will_write"] is True
    assert plan["will_execute_blender"] is True
    assert plan["output"]["destination_root"] == str(destination)
    assert not destination.exists()
    r15.validate_plan(plan)

    destination.mkdir()
    with pytest.raises(r15.DetailActionR15Error) as error:
        r15.validate_plan(plan)
    assert error.value.code == "PLAN_OUTPUT_INVALID"


def test_worker_is_standalone_headless_source_with_roundtrip_and_cpu_preview() -> None:
    source = WORKER_PATH.read_text(encoding="utf-8")
    syntax = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(syntax)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not any(
        module.startswith("tools.animation.vista_playable_home_cc0")
        for module in imported_modules
    )
    assert "_roundtrip_fbx" in source
    assert "_root_static" in source
    assert "_create_contact_sheet" in source
    assert "cpu_skeletal_projection_png" in source
    assert "action.pose_markers.new" in source
    assert 'action["vista_target_contract_json"]' in source
    assert "existing_r8_or_r14_bytes_reused" in source
    compile(source, str(WORKER_PATH), "exec")
