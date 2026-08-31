from __future__ import annotations

import ast
import copy
import hashlib
from pathlib import Path

import pytest

from tools.animation.vista_playable_home_cc0 import vertical_slice as r8_slice
from tools.animation.vista_playable_home_cc0_detail_actions_r14 import plan as r14


WORKER_PATH = (
    r14.REPOSITORY_ROOT
    / "tools/blender/vista_playable_home_makehuman_cc0_detail_actions_r14"
    / "blender_worker.py"
)


def _reseal(value: dict[str, object]) -> dict[str, object]:
    value["content_digest"] = r14.content_digest(value)
    return value


def test_profile_is_strict_fresh_cc0_r14_authority() -> None:
    profile = r14.load_profile()

    assert profile["schema_version"] == r14.PROFILE_SCHEMA_VERSION
    assert profile["profile_id"] == r14.PROFILE_ID
    assert profile["character_id"] == r14.CHARACTER_ID
    assert profile["namespace_contract"] == {
        "source_namespace": "vista.makehuman-cc0-detail-actions/r14",
        "ue_content_namespace": "/Game/VISTA/MakeHumanCC0/R14/DetailActions",
        "artifact_namespace": "makehuman_cc0_detail_actions_r14",
        "existing_r8_bytes_reused": False,
    }
    assert profile["source_character_binding"]["bone_count"] == 53
    assert profile["source_character_binding"]["source_character_asset_lane"] == (
        "makehuman_cc0_character_r6"
    )
    assert profile["source_character_binding"]["motion_source_policy"] == (
        "fresh_numeric_recipes_only"
    )
    assert profile["source_character_binding"]["r8_animation_artifact_dependency"] == (
        "none"
    )
    assert profile["license_scope"] == r14.LICENSE_SCOPE
    assert profile["provenance"] == r14.PROVENANCE
    assert profile["quality_contract"] == {
        "anticipation_contact_follow_through_required": True,
        "pickup_clip_reuse_prohibited": True,
        "human_motion_review_required": True,
        "runtime_acceptance_default": False,
    }
    assert profile["content_digest"] == r14.content_digest(profile)


def test_profile_schema_rejects_unknown_fields() -> None:
    profile = copy.deepcopy(r14.load_profile())
    profile["unexpected"] = True
    _reseal(profile)

    with pytest.raises(r14.DetailActionError) as error:
        r14.validate_profile(profile)

    assert error.value.code == "PROFILE_SCHEMA_INVALID"


@pytest.mark.parametrize(
    "mutation,code",
    [
        (
            lambda value: value["provenance"].__setitem__(
                "contains_motion_capture", True
            ),
            "PROFILE_SCHEMA_INVALID",
        ),
        (
            lambda value: value["namespace_contract"].__setitem__(
                "existing_r8_bytes_reused", True
            ),
            "PROFILE_SCHEMA_INVALID",
        ),
        (
            lambda value: value["clips"][0].__setitem__(
                "recipe_id", "cc0_numeric_mug_pickup_right_r14"
            ),
            "PICKUP_CLIP_REUSE_PROHIBITED",
        ),
        (
            lambda value: value["clips"][0]["phase_contract"].__setitem__(
                "follow_through_start_frame", 20
            ),
            "MOTION_PHASE_INVALID",
        ),
    ],
)
def test_profile_mutations_fail_closed(mutation, code: str) -> None:
    profile = copy.deepcopy(r14.load_profile())
    mutation(profile)
    _reseal(profile)

    with pytest.raises(r14.DetailActionError) as error:
        r14.validate_profile(profile)

    assert error.value.code == code


def test_three_action_event_and_typed_notify_contract_is_exact() -> None:
    clips = {clip["clip_id"]: clip for clip in r14.load_profile()["clips"]}

    assert tuple(clips) == r14.EXPECTED_CLIPS
    assert clips["fridge_open_right"]["event_action"] == "open"
    assert clips["fridge_close_right"]["event_action"] == "close"
    assert clips["object_inspect_right"]["event_action"] == "inspect"
    assert clips["fridge_open_right"]["typed_notifies"] == [
        {
            "frame": 26,
            "kind": "contact",
            "signal": "vista_fridge_door_handle_contact",
        },
        {
            "frame": 66,
            "kind": "completion",
            "signal": "vista_fridge_open_completed",
        },
    ]
    assert clips["fridge_close_right"]["typed_notifies"] == [
        {
            "frame": 24,
            "kind": "contact",
            "signal": "vista_fridge_door_handle_contact",
        },
        {
            "frame": 66,
            "kind": "completion",
            "signal": "vista_fridge_close_completed",
        },
    ]
    assert clips["object_inspect_right"]["typed_notifies"] == [
        {
            "frame": 88,
            "kind": "completion",
            "signal": "vista_inspect_completed",
        }
    ]
    assert all(clip["fps"] == 30 for clip in clips.values())
    assert all(clip["loop"] is False for clip in clips.values())
    assert all(clip["root_motion_policy"] == "forbidden" for clip in clips.values())


def test_numeric_recipes_have_explicit_motion_phases_and_no_root_channel() -> None:
    plan = r14.build_plan()

    assert len(r14.EXPECTED_BONES) == 53
    assert tuple(plan["rig_bone_names"]) == r14.EXPECTED_BONES
    for clip in plan["clips"]:
        frames = [keyframe["frame"] for keyframe in clip["keyframes"]]
        phases = clip["phase_contract"]
        assert frames[0] == 0
        assert frames[-1] == clip["frame_end"]
        assert phases["anticipation_end_frame"] in frames
        assert phases["engagement_frame"] in frames
        assert phases["follow_through_start_frame"] in frames
        assert phases["completion_frame"] in frames
        assert all("root" not in keyframe["bones"] for keyframe in clip["keyframes"])
        assert all(
            set(keyframe["bones"]) < set(r14.EXPECTED_BONES)
            for keyframe in clip["keyframes"]
        )
        assert any(
            name.endswith("_01_r") or name.endswith("_02_r")
            for keyframe in clip["keyframes"]
            for name in keyframe["bones"]
        )


def test_r14_numeric_recipes_are_distinct_and_not_r8_pickup_or_place() -> None:
    plan = r14.build_plan()
    r14_digests = {clip["numeric_recipe_sha256"] for clip in plan["clips"]}
    old_motion_digests = {
        hashlib.sha256(
            r14.canonical_json(r8_slice.MOTION_KEYFRAMES[clip_id])
        ).hexdigest()
        for clip_id in ("mug_pickup_countertop", "mug_place_countertop")
    }

    assert len(r14_digests) == 3
    assert r14_digests.isdisjoint(old_motion_digests)
    assert all(
        all(token not in clip["recipe_id"] for token in ("mug_", "pickup", "place"))
        for clip in plan["clips"]
    )


def test_dry_run_plan_is_sealed_and_never_claims_generated_acceptance() -> None:
    plan = r14.build_plan()

    assert plan["schema_version"] == r14.PLAN_SCHEMA_VERSION
    assert plan["mode"] == "dry_run"
    assert plan["status"] == "dry_run_validated_no_write"
    assert plan["will_write"] is False
    assert plan["will_execute_blender"] is False
    assert plan["accepted"] is False
    assert plan["output"] == {
        "destination_root": None,
        "blend_relative_path": "blend/vista_cc0_detail_actions_r14.blend",
        "external_binary_policy": "outside_git_only",
    }
    assert not any(plan["claims"].values())
    assert plan["content_digest"] == r14.content_digest(plan)
    r14.validate_plan(plan)


def test_execute_plan_only_allows_fresh_external_destination(tmp_path: Path) -> None:
    destination = tmp_path / "fresh-r14-candidate"
    plan = r14.build_plan(mode="execute", destination_root=destination)

    assert plan["mode"] == "execute"
    assert plan["status"] == "execution_plan_only_not_run"
    assert plan["will_write"] is True
    assert plan["will_execute_blender"] is True
    assert plan["output"]["destination_root"] == str(destination)
    assert not destination.exists()
    r14.validate_plan(plan)

    destination.mkdir()
    with pytest.raises(r14.DetailActionError) as error:
        r14.validate_plan(plan)
    assert error.value.code == "PLAN_OUTPUT_INVALID"


def test_plan_rejects_root_motion_and_numeric_recipe_drift() -> None:
    plan = r14.build_plan()
    clip = copy.deepcopy(plan["clips"][0])
    clip["keyframes"][1]["bones"]["root"] = {
        "rotation_deg_xyz": [0.0, 0.0, 0.0],
        "location_m": [0.0, 0.1, 0.0],
    }

    with pytest.raises(r14.DetailActionError) as error:
        r14._validate_keyframes(clip)

    assert error.value.code == "ROOT_MOTION_OR_BONE_INVALID"


def test_worker_is_standalone_r14_headless_source() -> None:
    source = WORKER_PATH.read_text(encoding="utf-8")
    syntax = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(syntax)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert (
        "tools.animation.vista_playable_home_cc0.vertical_slice" not in imported_modules
    )
    assert (
        "tools.blender.vista_playable_home_makehuman_cc0_animation.blender_worker"
        not in imported_modules
    )
    assert "EXPECTED_CLIPS = (" in source
    assert '"fridge_open_right"' in source
    assert '"fridge_close_right"' in source
    assert '"object_inspect_right"' in source
    assert "action.pose_markers.new" in source
    assert 'action["vista_typed_notifies_json"]' in source
    assert "_roundtrip_fbx" in source
    assert "_root_static" in source
    assert "existing R8 bytes are prohibited" in source
    compile(source, str(WORKER_PATH), "exec")
