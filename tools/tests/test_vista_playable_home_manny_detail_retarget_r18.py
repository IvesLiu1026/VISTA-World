from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tools.ue.vista_playable_home import (
    manny_detail_actions_retarget_r18_contract as contract,
)
from tools.ue.vista_playable_home import (
    run_manny_detail_actions_retarget_r18 as runner,
)


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools/ue/vista_playable_home"
RUNTIME = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_contract_closes_fourteen_clips_and_fresh_manny_inventory() -> None:
    assert len(contract.CLIP_SPECS) == 14
    assert [item["source_revision"] for item in contract.CLIP_SPECS].count("R8") == 2
    assert [item["source_revision"] for item in contract.CLIP_SPECS].count("R14") == 3
    assert [item["source_revision"] for item in contract.CLIP_SPECS].count("R15") == 9
    assert len(contract.EXPECTED_INVENTORY) == 31
    assert len({item["object_path"] for item in contract.EXPECTED_INVENTORY}) == 31
    assert all(
        item["target_sequence_object_path"].startswith(contract.SEQUENCE_NAMESPACE)
        and item["target_montage_object_path"].startswith(contract.MONTAGE_NAMESPACE)
        and "VistaManny" in item["target_sequence_name"]
        and item["target_sequence_name"].endswith("_R18")
        and item["target_montage_name"].endswith("_R18")
        and item["root_motion_policy"] == "forbidden"
        for item in contract.CLIP_SPECS
    )
    assert contract.SOURCE_MESH_OBJECT_PATH.startswith("/Game/VISTA/MakeHumanCC0/R6/")
    assert contract.TARGET_MESH_OBJECT_PATH == (
        "/Game/Characters/Mannequins/Meshes/SKM_Manny.SKM_Manny"
    )
    by_id = {item["clip_id"]: item for item in contract.CLIP_SPECS}
    assert by_id["mug_pickup_countertop"]["typed_notifies"] == [
        {"frame": 34, "kind": "contact", "signal": "vista_pickup_contact"},
        {
            "frame": 59,
            "kind": "completion",
            "signal": "vista_pickup_completed",
        },
    ]
    assert by_id["mug_place_countertop"]["typed_notifies"] == [
        {"frame": 34, "kind": "release", "signal": "vista_drop_release"},
        {
            "frame": 59,
            "kind": "completion",
            "signal": "vista_drop_completed",
        },
    ]


def test_contract_uses_exact_symmetric_nineteen_chain_mapping() -> None:
    expected_names = {
        "Root",
        "Spine",
        "Head",
        "LeftClavicle",
        "RightClavicle",
        "LeftArm",
        "RightArm",
        "LeftLeg",
        "RightLeg",
        *{
            side + finger
            for side in ("Left", "Right")
            for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky")
        },
    }
    assert len(contract.CHAIN_SPECS) == 19
    assert {item["name"] for item in contract.CHAIN_SPECS} == expected_names
    by_name = {item["name"]: item for item in contract.CHAIN_SPECS}
    assert (
        by_name["Root"]["source"]
        == by_name["Root"]["target"]
        == (
            "root",
            "root",
        )
    )
    assert by_name["Spine"]["source"] == ("spine_01", "spine_03")
    assert by_name["Spine"]["target"] == ("spine_01", "spine_05")
    assert (
        by_name["Head"]["source"]
        == by_name["Head"]["target"]
        == (
            "neck_01",
            "head",
        )
    )
    source_bones = {
        bone for item in contract.CHAIN_SPECS for bone in item["source"]
    } | {"pelvis"}
    assert source_bones <= set(contract.SOURCE_BONE_NAMES)


def test_worker_uses_closed_ue57_retarget_api_and_false_success_checks() -> None:
    worker_path = TOOLS / "author_manny_detail_actions_retarget_r18.py"
    worker = text(worker_path)
    ast.parse(worker)
    for authority in (
        "IKRigDefinitionFactory.create_new_ik_rig_asset",
        "IKRigController.get_controller",
        "add_retarget_chain",
        "set_retarget_root",
        "IKRetargetFactory()",
        "assign_ik_rig_to_all_ops",
        "auto_map_chains(unreal.AutoMapChainType.EXACT, True)",
        "auto_align_all_bones",
        "IKRetargetBatchOperation.duplicate_and_retarget",
        "include_referenced_assets=False",
        "overwrite_existing_files=False",
    ):
        assert authority in worker
    assert 'EXPECTED_ENGINE = "5.7.3-50162420+++UE5+Release-5.7"' in worker
    assert "tracks == expected_tracks" in worker
    assert "is_root_motion_lock_forced(sequence) is True" in worker
    assert "RootMotionRootLock.REF_POSE" in worker
    assert "retargeted motion is structurally static" in worker
    assert "temporary retarget assets remain in /Game" in worker
    assert "events = sorted(" in worker
    assert "author() if mode == contract.AUTHOR_MODE else verify()" in worker


def test_runner_dry_run_contract_is_zero_write_and_execution_is_external() -> None:
    source = text(TOOLS / "run_manny_detail_actions_retarget_r18.py")
    ast.parse(source)
    assert '"status": "dry_run_validated_zero_write"' in source
    assert '"writes_performed": False' in source
    assert '"external_only": True' in source
    assert "if args.execute else plan.report" in source
    assert "--unshare-net" in source
    assert '"/vista/source"' in source
    assert '"/vista/work"' in source
    assert "source_assets_byte_identical_after_author_and_verify" in source
    assert "validate_r8_receipt" in source
    assert 'object_paths=expected_source_paths("R8")' in source
    assert 'author_receipt["inspection"] == verify_receipt["inspection"]' in source
    assert runner.expected_added_paths() == {
        item["object_path"].split(".", 1)[0].removeprefix("/Game/") + ".uasset"
        for item in contract.EXPECTED_INVENTORY
    }
    runner.validate_attempt_name("manny-detail-actions-retarget-r18-test")
    with pytest.raises(runner.RunnerError):
        runner.validate_attempt_name("../escape")


def test_runtime_selects_manny_only_for_exact_human_operated_provider() -> None:
    provider_h = text(RUNTIME / "Public/VistaCharacterProviderComponent.h")
    provider_cpp = text(RUNTIME / "Private/VistaCharacterProviderComponent.cpp")
    animation = text(RUNTIME / "Private/VistaAnimationComponent.cpp")
    assert "IsCitySampleHumanOperatedVisualDemoActive" in provider_h
    for authority in (
        "CitySampleVisualDemoActiveUnverifiedStatus",
        "IsCitySampleHumanVisualDemoCommandLineAllowed",
        "ValidateCitySampleVisualDemo",
        "SKM_Manny.SKM_Manny",
        "SK_Mannequin.SK_Mannequin",
    ):
        assert authority in provider_cpp
    for montage in (
        "AM_VistaMannyFridgeOpenRight_R18",
        "AM_VistaMannyFridgeCloseRight_R18",
        "AM_VistaMannyObjectInspectRight_R18",
        "AM_VistaMannyRotaryTurnOnRight_R18",
        "AM_VistaMannyRotaryTurnOffRight_R18",
        "AM_VistaMannyButtonPressRight_R18",
        "AM_VistaMannyCabinetDrawerOpenRight_R18",
        "AM_VistaMannyCabinetDrawerCloseRight_R18",
        "AM_VistaMannySitDownChair_R18",
        "AM_VistaMannySeatedIdleLoop_R18",
        "AM_VistaMannyStandUpChair_R18",
        "AM_VistaMannyPourRight_R18",
        "AM_VistaMannyMugPickupCountertop_R18",
        "AM_VistaMannyMugPlaceCountertop_R18",
    ):
        assert montage in animation
    assert "IsExactMannyR18MontageAvailable" in animation
    assert "ANIMATION_MANNY_R18_RETARGET_UNAVAILABLE" in animation
    assert "ANIMATION_MANNY_R18_SKELETON_MISMATCH" in animation
    assert "ANIMATION_CC0_MONTAGE_ON_MANNY_FORBIDDEN" in animation
    assert "ResolvedMontage->GetSkeleton() != CharacterSkeleton" in animation
    assert "Type == EVistaNpcActionType::PickUp" in animation
    assert (
        "Type == EVistaNpcActionType::Place || Type == EVistaNpcActionType::Drop"
        in animation
    )
    target_free = animation.split("bool ValidateMannyR18Binding", 1)[1].split(
        "bool ResolveAuthoredInteractionPoint", 1
    )[0]
    assert "MannyR18MontageFor(Type, nullptr)" in target_free
    assert target_free.index("Type == EVistaNpcActionType::PickUp") < target_free.index(
        "ANIMATION_TARGET_PREFLIGHT_DEFERRED"
    )


def test_citysample_cache_is_set_only_by_citysample_success_path() -> None:
    provider_cpp = text(RUNTIME / "Private/VistaCharacterProviderComponent.cpp")
    metahuman = provider_cpp.split(
        "bool UVistaCharacterProviderComponent::ActivateAllowlistedMetaHuman", 1
    )[1].split(
        "bool UVistaCharacterProviderComponent::ActivateAllowlistedCitySampleVisualDemo",
        1,
    )[0]
    citysample = provider_cpp.split(
        "bool UVistaCharacterProviderComponent::ActivateAllowlistedCitySampleVisualDemo",
        1,
    )[1].split(
        "bool UVistaCharacterProviderComponent::IsCitySampleHumanVisualDemoCommandLineAllowed",
        1,
    )[0]
    assert "bCitySampleHumanOperatedVisualDemoValidated = true" not in metahuman
    assert "bCitySampleHumanOperatedVisualDemoValidated = true" in citysample


def test_tick_preflight_uses_cached_provider_and_loaded_asset_fast_path() -> None:
    provider_cpp = text(RUNTIME / "Private/VistaCharacterProviderComponent.cpp")
    animation = text(RUNTIME / "Private/VistaAnimationComponent.cpp")
    provider_getter = provider_cpp.split(
        "IsCitySampleHumanOperatedVisualDemoActive() const", 1
    )[1].split("void UVistaCharacterProviderComponent::BeginPlay", 1)[0]
    assert "bCitySampleHumanOperatedVisualDemoValidated" in provider_getter
    assert "ValidateCitySampleVisualDemo(" not in provider_getter
    assert "IsCitySampleHumanVisualDemoCommandLineAllowed(" not in provider_getter
    availability = animation.split("bool IsExactMannyR18MontageAvailable", 1)[1].split(
        "bool ValidateMannyR18Binding", 1
    )[0]
    assert availability.index("MontageReference.Get()") < availability.index(
        "MontageReference.LoadSynchronous()"
    )
    assert "UnavailableMannyR18Montages.Contains" in availability
    assert "UnavailableMannyR18Montages.Add" in availability
    start = animation.split("bool UVistaAnimationComponent::StartNpcAction", 1)[
        1
    ].split("void UVistaAnimationComponent::RecordSignal", 1)[0]
    assert start.index("RequiresTarget(Action.Type)") < start.index(
        "HasApprovedMutationAnimation(Action.Type, Target, OutCode)"
    )


def test_contract_keeps_all_binary_and_acceptance_claims_closed() -> None:
    assert contract.LEGAL_SCOPE == {
        "cc0_motion_preserved_as_source": True,
        "epic_ue_target_skeleton_used": True,
        "external_binary_policy": "outside_git_only",
        "human_operated_visual_demo_only": True,
        "private_noncommercial_research_only": True,
        "source_uasset_redistribution": False,
    }
    assert contract.NEGATIVE_CLAIMS
    assert not any(contract.NEGATIVE_CLAIMS.values())
