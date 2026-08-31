from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from tools.ue.vista_playable_home import (
    makehuman_cc0_detail_actions_r15_contract as authority,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_SOURCE = (
    REPOSITORY_ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/Private/Tests"
    / "VistaR15DetailActionAssetContractProof.cpp"
)
RUNBOOK = (
    REPOSITORY_ROOT
    / "docs/runbooks/vista-r15-detail-actions-asset-contract-automation.md"
)


@dataclass(frozen=True)
class ParsedNotify:
    signal: str
    frame: int


@dataclass(frozen=True)
class ParsedClip:
    clip_id: str
    sequence_path: str
    montage_path: str
    frame_count: int
    notifies: tuple[ParsedNotify, ...]


TEXT_EXPRESSION = re.compile(r'TEXT\(((?:\s*"[^"]*"\s*)+)\)')
CLIP_ENTRY = re.compile(
    r"\{\s*'(?P<clip_id>[^']+)',\s*"
    r"'(?P<sequence_path>[^']+)',\s*"
    r"'(?P<montage_path>[^']+)',\s*"
    r"(?P<frame_count>\d+),\s*"
    r"(?P<notify_count>\d+),\s*"
    r"\{(?P<notifies>\{.*?\})\},\s*\},",
    re.DOTALL,
)
NOTIFY_ENTRY = re.compile(r"\{'(?P<signal>[^']+)',\s*(?P<frame>\d+)\}")


def _collapse_text_expressions(source: str) -> str:
    def collapse(match: re.Match[str]) -> str:
        fragments = re.findall(r'"([^"]*)"', match.group(1))
        return repr("".join(fragments))

    return TEXT_EXPRESSION.sub(collapse, source)


def parse_clip_specs(source: str) -> tuple[ParsedClip, ...]:
    start = "const FClipSpec ClipSpecs[] = {"
    end = "};\nstatic_assert(UE_ARRAY_COUNT(ClipSpecs) == 9"
    assert source.count(start) == 1
    assert source.count(end) == 1
    table = source.split(start, 1)[1].split(end, 1)[0]
    normalized = _collapse_text_expressions(table)
    clips: list[ParsedClip] = []
    for match in CLIP_ENTRY.finditer(normalized):
        notify_count = int(match.group("notify_count"))
        notifies = tuple(
            ParsedNotify(item.group("signal"), int(item.group("frame")))
            for item in NOTIFY_ENTRY.finditer(match.group("notifies"))
        )
        assert len(notifies) == notify_count
        clips.append(
            ParsedClip(
                clip_id=match.group("clip_id"),
                sequence_path=match.group("sequence_path"),
                montage_path=match.group("montage_path"),
                frame_count=int(match.group("frame_count")),
                notifies=notifies,
            )
        )
    return tuple(clips)


def validate_automation_source(source: str) -> tuple[ParsedClip, ...]:
    clips = parse_clip_specs(source)
    assert len(clips) == 9
    assert len({clip.clip_id for clip in clips}) == 9

    expected_by_id = {str(item["clip_id"]): item for item in authority.CLIP_SPECS}
    assert set(expected_by_id) == {clip.clip_id for clip in clips}
    for clip in clips:
        expected = expected_by_id[clip.clip_id]
        sequence_name = str(expected["sequence_name"])
        montage_name = str(expected["montage_name"])
        assert clip.sequence_path == (
            f"{authority.SEQUENCE_NAMESPACE}/{sequence_name}.{sequence_name}"
        )
        assert clip.montage_path == (
            f"{authority.MONTAGE_NAMESPACE}/{montage_name}.{montage_name}"
        )
        assert clip.frame_count == (
            int(expected["frame_end"]) - int(expected["frame_start"])
        )
        assert clip.notifies == tuple(
            ParsedNotify(str(item["signal"]), int(item["frame"]))
            for item in expected["typed_notifies"]
        )

    occurrences = [notify for clip in clips for notify in clip.notifies]
    assert len(occurrences) == 16
    assert len({notify.signal for notify in occurrences}) == 14

    required_semantics = (
        '"VISTA.PlayableHome.R15DetailActions.AssetContract"',
        "ExpectedBoneTrackCount = 53",
        "ExpectedAssetCount = 18",
        "ExpectedNotifyOccurrenceCount = 16",
        "ExpectedUniqueSignalCount = 14",
        "FindObject<UObject>(nullptr, *ObjectPath) == nullptr",
        "Registry.ScanPathsSynchronous",
        "DiskAssets, true, true",
        "ObservedInventory.Contains(Key)",
        "Sequence->GetSkeleton() == Skeleton",
        "Montage->GetSkeleton() == Skeleton",
        "Skeleton->GetReferenceSkeleton()",
        "ReferenceSkeleton.GetNum(), ExpectedBoneTrackCount",
        "ReferenceSkeleton.FindBoneIndex(ExpectedBone) != INDEX_NONE",
        "Sequence->bEnableRootMotion",
        "Sequence->bForceRootLock",
        "ERootMotionRootLock::RefPose",
        "Sequence->HasRootMotion()",
        "Montage->HasRootMotion()",
        "DataModel->GetFrameRate()",
        "Sequence->GetSamplingFrameRate()",
        "DataModel->GetNumberOfFrames()",
        "Sequence->GetNumberOfSampledKeys()",
        "DataModel->GetNumBoneTracks()",
        "DataModel->GetBoneTrackNames(BoneTrackNames)",
        "RootAtFrame.Equals(InitialRoot, TransformTolerance)",
        "Montage->GetFirstAnimReference() == Sequence",
        "Montage->SlotAnimTracks.Num(), 1",
        "FAnimSlotGroup::DefaultSlotName",
        "Segment.GetAnimReference() == Sequence",
        "Segment.LoopingCount, 1",
        "Cast<UVistaAnimationSignalNotify>",
        "ObservedClipNotifies.Contains(ExpectedNotify)",
    )
    for token in required_semantics:
        assert token in source

    assert "VistaActionExecutorComponent.h" not in source
    assert "VistaPlayableHomeRuntimeSubsystem.h" not in source
    assert "VistaEvent" not in source
    return clips


def test_r15_editor_automation_is_exact_closed_asset_contract() -> None:
    source = AUTOMATION_SOURCE.read_text(encoding="utf-8")
    clips = validate_automation_source(source)

    assert [clip.clip_id for clip in clips] == [
        str(item["clip_id"]) for item in authority.CLIP_SPECS
    ]
    assert authority.SKELETON_OBJECT_PATH in _collapse_text_expressions(source)
    assert (
        "EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter"
        in source
    )


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (
            "AS_VistaCC0RotaryTurnOnRight_R15",
            "AS_VistaCC0RotaryTurnOnRight_WRONG",
        ),
        ("vista_pour_completed", "vista_pour_complete_WRONG"),
        ("ExpectedBoneTrackCount = 53", "ExpectedBoneTrackCount = 52"),
        ("DiskAssets, true, true", "DiskAssets, true, false"),
        ("Segment.LoopingCount, 1", "Segment.LoopingCount, 2"),
    ),
)
def test_r15_editor_automation_rejects_resealed_semantic_drift(
    old: str, new: str
) -> None:
    source = AUTOMATION_SOURCE.read_text(encoding="utf-8")
    assert old in source
    with pytest.raises(AssertionError):
        validate_automation_source(source.replace(old, new, 1))


def test_runbook_keeps_runtime_and_target_alignment_claims_closed() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "source-only until an authorized UE run" in runbook
    assert (
        "does not prove target-aware IK, Motion Warping, or scene-target paths"
        in runbook
    )
    assert "fresh UnrealEditor-Cmd process" in runbook
    assert "9 `AnimSequence` + 9 `AnimMontage`" in runbook
