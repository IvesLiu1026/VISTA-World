"""Source-level closure tests for typed EventSpec outcome evaluation."""

from __future__ import annotations

import pathlib
import py_compile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"


class VistaPlayableHomeEventOutcomeTests(unittest.TestCase):
    def test_all_closed_condition_variants_are_typed_and_materialized(self) -> None:
        types = (PLUGIN / "Public/VistaPlayableHomeTypes.h").read_text(encoding="utf-8")
        commandlet_path = ROOT / "tools/ue/vista_playable_home/compose_home_commandlet.py"
        commandlet = commandlet_path.read_text(encoding="utf-8")
        py_compile.compile(str(commandlet_path), doraise=True)

        for cpp_type, plan_type in (
            ("EntityState", "entity_state"),
            ("EntityRoom", "entity_room"),
            ("PlayerRoom", "player_room"),
            ("Interaction", "interaction"),
            ("Elapsed", "elapsed"),
        ):
            self.assertIn(cpp_type, types)
            self.assertIn('"%s"' % plan_type, commandlet)
        for collection in ("Triggers", "SuccessConditions", "FailureConditions"):
            self.assertIn(collection, types)
        for property_name in ("triggers", "success_conditions", "failure_conditions"):
            self.assertIn('"%s"' % property_name, commandlet)
        self.assertIn('rooms[source["room_id"]]["world_bounds_cm"]', commandlet)

    def test_runtime_uses_all_success_any_failure_and_timeout_last(self) -> None:
        source = (PLUGIN / "Private/VistaEventSubsystem.cpp").read_text(encoding="utf-8")
        self.assertIn("bAllSuccess = !ActiveSuccessConditions.IsEmpty()", source)
        self.assertIn("for (const FVistaEventCondition& Condition : ActiveFailureConditions)", source)
        self.assertIn("EvaluateOutcome();", source)
        self.assertIn("EVistaEventStatus::Succeeded", source)
        self.assertIn("EVistaEventStatus::Failed", source)
        self.assertIn("EVistaEventStatus::TimedOut", source)
        self.assertLess(source.index("EvaluateOutcome();", source.index("void UVistaEventSubsystem::Tick")),
                        source.index("EVistaEventStatus::TimedOut", source.index("void UVistaEventSubsystem::Tick")))
        self.assertIn("FBox(Condition.RoomMinCm, Condition.RoomMaxCm)", source)
        self.assertIn("ObservedInteractions.Contains", source)

    def test_every_gameplay_interaction_entry_reports_success(self) -> None:
        paths = (
            "Private/VistaInteractionComponent.cpp",
            "Private/VistaPlayableHomeRuntimeSubsystem.cpp",
            "Private/VistaPlayableHomeCharacter.cpp",
            "Private/VistaHomeNpcController.cpp",
        )
        for relative in paths:
            with self.subTest(relative=relative):
                source = (PLUGIN / relative).read_text(encoding="utf-8")
                self.assertIn("RecordSuccessfulInteraction", source)
                self.assertIn("Result.IsSuccess()", source)


if __name__ == "__main__":
    unittest.main()
