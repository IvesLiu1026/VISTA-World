from __future__ import annotations

import ast
import pathlib
import sys
import types

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET_ROOT = ROOT / "tools/ue/vista_playable_home"
COMMANDLET = COMMANDLET_ROOT / "compose_hybrid_r3_commandlet.py"
sys.path.insert(0, str(COMMANDLET_ROOT))
import run_hybrid_r3_composition as runner  # noqa: E402


@pytest.fixture
def commandlet(monkeypatch: pytest.MonkeyPatch):
    unreal = types.ModuleType("unreal")
    monkeypatch.setitem(sys.modules, "unreal", unreal)
    tree = ast.parse(COMMANDLET.read_text(encoding="utf-8"), filename=str(COMMANDLET))
    terminal = tree.body[-1]
    assert isinstance(terminal, ast.Expr)
    assert isinstance(terminal.value, ast.Call)
    assert isinstance(terminal.value.func, ast.Name)
    assert terminal.value.func.id == "run"
    tree.body.pop()
    module = types.ModuleType("vista_hybrid_r3_commandlet_test")
    module.__file__ = str(COMMANDLET)
    exec(compile(tree, str(COMMANDLET), "exec"), module.__dict__)
    return module


def _room_observations():
    counts = {
        "home.r1/room.entry_hall": 1,
        "home.r1/room.kitchen_dining": 2,
        "home.r1/room.living_room": 2,
    }
    result = []
    serial = 0
    for room_id in runner.PRODUCTION_PRESENTATION_ROOMS:
        target_ids = []
        for _ in range(counts[room_id]):
            target_ids.append(f"{room_id}/entity.semantic_{serial}.01")
            serial += 1
        result.append(
            {
                "room_id": room_id,
                "external_content": {"semantic_target_ids": target_ids},
            }
        )
    return result


def test_commandlet_has_exactly_one_terminal_entrypoint() -> None:
    tree = ast.parse(COMMANDLET.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run"
    ]
    terminal = tree.body[-1]
    assert len(calls) == 1
    assert isinstance(terminal, ast.Expr)
    assert terminal.value is calls[0]


def test_production_semantic_authority_is_exact_five_disjoint_targets(
    commandlet,
) -> None:
    targets = commandlet._production_semantic_target_ids(_room_observations())

    assert len(targets) == runner.PRODUCTION_SEMANTIC_TARGET_COUNT == 5
    assert targets == sorted(set(targets))
    assert all(
        target.startswith(tuple(room + "/" for room in runner.FORBIDDEN_HSSD_ROOMS))
        for target in targets
    )


def test_production_semantic_authority_rejects_duplicates(commandlet) -> None:
    observations = _room_observations()
    observations[1]["external_content"]["semantic_target_ids"][0] = observations[0][
        "external_content"
    ]["semantic_target_ids"][0]

    with pytest.raises(RuntimeError, match="target count differs"):
        commandlet._production_semantic_target_ids(observations)


def test_commandlet_uses_pinned_upstream_helpers_and_filtered_execution() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    assert "load_upstream_commandlet_helpers" in source
    assert 'execution["scripts"]["upstream_phase2_commandlet"]' in source
    assert "placements, imported" in source
    assert "len(placements) == hybrid.HSSD_PLACEMENT_COUNT" in source
    assert "hybrid.FORBIDDEN_HSSD_ROOMS" in source
    assert "len(hssd_actors) == hybrid.HSSD_PLACEMENT_COUNT" in source
    assert "hybrid.HISTORICAL_ENGINE_VERSION" in source
    assert "hybrid.HISTORICAL_HSSD_ASSET_IDS" in source
    assert "hybrid.phase2." not in source


def test_commandlet_preserves_production_before_and_after_save_reload() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    assert "presentation_reloaded == presentation_before" in source
    assert "production_semantic_reloaded == production_semantic_before" in source
    assert "EditorLoadingAndSavingUtils.save_map" in source
    assert source.count("level_subsystem.load_level") >= 2
    assert '"production_presentation_before"' in source
    assert '"production_semantic_authority_reloaded"' in source


def test_commandlet_never_claims_human_gta_or_player_eye_acceptance() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    assert '"gta_level": False' in source
    assert '"real_human_present": False' in source
    assert '"player_eye_reviewed": False' in source
    assert '"interaction_proven": False' in source


def test_commandlet_has_no_live_runtime_or_gpu_process_control() -> None:
    source = COMMANDLET.read_text(encoding="utf-8")
    forbidden = (
        "subprocess",
        "CUDA_VISIBLE_DEVICES",
        "PixelStreaming",
        "Sunshine",
        "pkill",
        "killpg",
    )
    assert all(token not in source for token in forbidden)
