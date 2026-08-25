from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins" / "VistaPlayableHome" / "Source" / "VistaPlayableHome"


class VistaPlayableHomeAnimationRuntimeTests(unittest.TestCase):
    def test_project_owned_montage_allowlist_covers_t13(self) -> None:
        source = (PLUGIN / "Private" / "VistaAnimationComponent.cpp").read_text(encoding="utf-8")
        self.assertIn('ProjectAnimationRoot = TEXT("/Game/VISTA/Animations/V1/")', source)
        for asset in (
            "AM_VistaLookAt", "AM_VistaBrace", "AM_VistaDrag", "AM_VistaLiftFoot",
            "AM_VistaPause", "AM_VistaFall", "AM_VistaRecover",
        ):
            self.assertIn(asset, source)
        self.assertNotIn("/Game/Characters/", source)
        self.assertNotIn("/Game/Human_Avatar/", source)

    def test_completion_and_contact_notifies_fail_closed(self) -> None:
        component = (PLUGIN / "Private" / "VistaAnimationComponent.cpp").read_text(encoding="utf-8")
        notify = (PLUGIN / "Private" / "VistaAnimationSignalNotify.cpp").read_text(encoding="utf-8")
        self.assertIn("ANIMATION_COMPLETION_NOTIFY_MISSING", component)
        for signal in ("vista_pickup_contact", "vista_drop_release", "vista_door_handle_contact"):
            self.assertIn(signal, component)
        self.assertIn("Component->RecordSignal(SignalName)", notify)

    def test_typed_queue_has_no_caller_asset_or_execution_surface(self) -> None:
        tcp = (PLUGIN / "Private" / "VistaWorldTcpAdapter.cpp").read_text(encoding="utf-8")
        for action in ("brace", "drag", "lift_foot", "pause", "fall", "recover"):
            self.assertIn(f'TEXT("{action}")', tcp)
        for field in ("distance_cm", "height_cm", "hand", "foot", "direction"):
            self.assertIn(f'TEXT("{field}")', tcp)
        for prohibited in (
            'TEXT("object_path")', 'TEXT("class")', 'TEXT("function")',
            'TEXT("script")', 'TEXT("console_command")',
        ):
            self.assertNotIn(prohibited, tcp)

    def test_new_actions_fail_closed_and_legacy_fallback_is_narrow(self) -> None:
        controller = (PLUGIN / "Private" / "VistaHomeNpcController.cpp").read_text(encoding="utf-8")
        component = (PLUGIN / "Private" / "VistaAnimationComponent.cpp").read_text(encoding="utf-8")
        self.assertIn("ANIMATION_ASSET_UNAVAILABLE", component)
        self.assertIn("IsLegacyFallbackAction", controller)
        self.assertIn('AnimationCode != FName(TEXT("ANIMATION_ASSET_UNAVAILABLE"))', controller)
        for guard in (
            "BRACE_REQUIRES_BOTH_HANDS", "DRAG_PARAMETERS_REQUIRED",
            "LIFT_FOOT_PARAMETERS_REQUIRED", "DIRECTION_FORWARD_REQUIRED",
        ):
            self.assertIn(guard, controller)

    def test_player_and_npc_both_own_the_animation_component(self) -> None:
        player = (PLUGIN / "Private" / "VistaPlayableHomeCharacter.cpp").read_text(encoding="utf-8")
        npc = (PLUGIN / "Private" / "VistaHomeNpcCharacter.cpp").read_text(encoding="utf-8")
        token = 'CreateDefaultSubobject<UVistaAnimationComponent>(TEXT("VistaAnimationComponent"))'
        self.assertIn(token, player)
        self.assertIn(token, npc)

    def test_read_only_npc_status_exposes_queue_and_animation_evidence(self) -> None:
        runtime_h = (PLUGIN / "Public" / "VistaPlayableHomeRuntimeSubsystem.h").read_text(
            encoding="utf-8"
        )
        runtime_cpp = (PLUGIN / "Private" / "VistaPlayableHomeRuntimeSubsystem.cpp").read_text(
            encoding="utf-8"
        )
        tcp = (PLUGIN / "Private" / "VistaWorldTcpAdapter.cpp").read_text(encoding="utf-8")
        self.assertIn("GetNpcStatus", runtime_h)
        self.assertIn("NPC_STATUS_OBSERVED", runtime_cpp)
        self.assertIn('Operation == TEXT("npc_status")', tcp)
        self.assertIn('TEXT("queued_action_count")', tcp)
        self.assertIn('TEXT("contact_observed")', tcp)
        npc_status_body = runtime_cpp.split("GetNpcStatus", 1)[1].split("GetRendererStatus", 1)[0]
        self.assertNotIn("CommitCommandGeneration", npc_status_body)


if __name__ == "__main__":
    unittest.main()
