from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/ue/vista_playable_home/author_animation_montages.py"
HEADER = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/Public"
    / "VistaPlayableHomeAnimationLibrary.h"
)
SOURCE = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/Private"
    / "VistaPlayableHomeAnimationLibrary.cpp"
)
NANITE_SOURCE = (
    ROOT
    / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/Private"
    / "VistaPlayableHomeNaniteLibrary.cpp"
)
PROFILE = (
    ROOT
    / "world_packs/vista_playable_home_r1/animation_profiles"
    / "ue_5_7_3_animation_v1.json"
)


class AnimationAuthoringContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script_text = SCRIPT.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.script_text)

    def literal_assignment(self, name: str):
        assignment = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )
        )
        return ast.literal_eval(assignment.value)

    def test_action_map_is_closed_and_matches_runtime_montages(self) -> None:
        specs = self.literal_assignment("ACTION_SPECS")
        self.assertEqual(
            set(specs),
            {
                "look_at",
                "pickup",
                "drop",
                "door",
                "brace",
                "drag",
                "lift_foot",
                "pause",
                "fall",
                "recover",
            },
        )

    def test_typed_notify_wire_keys_match_the_public_profile(self) -> None:
        specs = self.literal_assignment("ACTION_SPECS")
        contact_signals = self.literal_assignment("CONTACT_SIGNALS")
        completion_signals = self.literal_assignment("COMPLETION_SIGNALS")
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        required = {
            action["action_id"]: set(action["required_notifies"])
            for action in profile["actions"]
        }

        self.assertEqual(set(completion_signals), set(specs))
        self.assertEqual(
            {action for action, values in specs.items() if values[3] is not None},
            set(contact_signals),
        )
        for action in specs:
            authored = {completion_signals[action]}
            if action in contact_signals:
                authored.add(contact_signals[action])
            self.assertEqual(authored, required[action], action)
        self.assertNotIn("contact", set(contact_signals.values()))
        self.assertNotIn("completed", set(completion_signals.values()))
        self.assertEqual(
            {value[2] for value in specs.values()},
            {
                "AM_VistaLookAt",
                "AM_VistaPickup",
                "AM_VistaDrop",
                "AM_VistaDoor",
                "AM_VistaBrace",
                "AM_VistaDrag",
                "AM_VistaLiftFoot",
                "AM_VistaPause",
                "AM_VistaFall",
                "AM_VistaRecover",
            },
        )

    def test_authoring_is_offline_and_has_fail_closed_receipt(self) -> None:
        for forbidden in ("requests", "urllib", "http://", "https://", "subprocess"):
            self.assertNotIn(forbidden, self.script_text)
        self.assertIn('"accepted": False', self.script_text)
        self.assertIn("VISTA_ANIMATION_REPORT", self.script_text)
        self.assertIn("TARGET_SKELETON", self.script_text)

    def test_authoring_modes_are_closed_and_montage_only_validates_sequences(self) -> None:
        self.assertEqual(
            self.literal_assignment("AUTHORING_MODES"),
            ("full", "montages_only"),
        )
        self.assertIn("VISTA_ANIMATION_AUTHORING_MODE", self.script_text)
        self.assertIn('authoring_mode not in AUTHORING_MODES', self.script_text)
        self.assertIn('authoring_mode == "montages_only"', self.script_text)
        self.assertIn(
            'sequence = _load(sequence_path, "AnimSequence")',
            self.script_text,
        )
        self.assertIn(
            'sequence.get_editor_property("skeleton").get_path_name()',
            self.script_text,
        )

    def test_native_bridge_is_editor_only_and_namespace_closed(self) -> None:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("VISTAPLAYABLEHOMEEDITOR_API", header)
        self.assertIn("CreateMontageFromSequence", header)
        self.assertIn(
            'TEXT("/Game/VISTA/Animations/V1/Sequences/")', source
        )
        self.assertIn(
            'TEXT("/Game/VISTA/Animations/V1/Montages/")', source
        )
        self.assertIn("MONTAGE_ALREADY_EXISTS", source)
        self.assertIn("UPackage::SavePackage", source)

    def test_ue_5_7_editor_dependencies_are_explicit(self) -> None:
        animation_source = SOURCE.read_text(encoding="utf-8")
        nanite_source = NANITE_SOURCE.read_text(encoding="utf-8")
        self.assertIn('#include "Animation/Skeleton.h"', animation_source)
        for source in (animation_source, nanite_source):
            self.assertIn(
                '#include "Policies/CondensedJsonPrintPolicy.h"', source
            )


if __name__ == "__main__":
    unittest.main()
