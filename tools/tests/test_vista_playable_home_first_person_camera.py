from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNTIME = (
    ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
)
CHARACTER_HEADER = RUNTIME / "Public/VistaPlayableHomeCharacter.h"
CHARACTER_SOURCE = RUNTIME / "Private/VistaPlayableHomeCharacter.cpp"
HUD_SOURCE = RUNTIME / "Private/VistaPlayableHomeHUD.cpp"


def _method(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


class VistaFirstPersonCameraSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = CHARACTER_HEADER.read_text(encoding="utf-8")
        cls.character = CHARACTER_SOURCE.read_text(encoding="utf-8")
        cls.hud = HUD_SOURCE.read_text(encoding="utf-8")

    def test_default_view_remains_the_existing_third_person_camera(self) -> None:
        constructor = _method(
            self.character,
            "AVistaPlayableHomeCharacter::AVistaPlayableHomeCharacter()",
            "void AVistaPlayableHomeCharacter::BeginPlay()",
        )
        self.assertIn("CameraBoom->TargetArmLength = 320.0f;", constructor)
        self.assertIn(
            "CameraBoom->SocketOffset = FVector(0.0f, 55.0f, 65.0f);",
            constructor,
        )
        self.assertIn('TEXT("FirstPersonCamera")', constructor)
        self.assertIn(
            "FirstPersonCamera->SetupAttachment(GetCapsuleComponent());",
            constructor,
        )
        self.assertIn("FirstPersonCamera->bUsePawnControlRotation = true;", constructor)
        self.assertIn("FirstPersonCamera->SetAutoActivate(false);", constructor)
        self.assertIn("FirstPersonCamera->SetActive(false);", constructor)
        self.assertIn("bool bFirstPersonViewEnabled = false;", self.header)

    def test_v_switches_only_owner_local_camera_presentation(self) -> None:
        setup = _method(
            self.character,
            "void AVistaPlayableHomeCharacter::SetupPlayerInputComponent(",
            "void AVistaPlayableHomeCharacter::Move(",
        )
        toggle = _method(
            self.character,
            "bool AVistaPlayableHomeCharacter::SetFirstPersonViewEnabled(",
            "void AVistaPlayableHomeCharacter::ToggleCameraView()",
        )
        self.assertIn("EKeys::V", setup)
        self.assertIn("ToggleCameraViewPressed", setup)
        self.assertIn("!IsLocallyControlled()", toggle)
        self.assertIn("FollowCamera->Deactivate();", toggle)
        self.assertIn("FirstPersonCamera->Activate(true);", toggle)
        self.assertNotIn("Server", toggle)
        self.assertNotIn("CameraBoom->", toggle)
        self.assertNotIn("SetActorRotation", toggle)
        self.assertNotIn("bUseControllerRotationYaw", toggle)

    def test_toggle_restores_exact_prior_activation_and_visibility_state(self) -> None:
        toggle = _method(
            self.character,
            "bool AVistaPlayableHomeCharacter::SetFirstPersonViewEnabled(",
            "void AVistaPlayableHomeCharacter::ToggleCameraView()",
        )
        restore = _method(
            self.character,
            "void AVistaPlayableHomeCharacter::RestoreCameraPresentation()",
            "void AVistaPlayableHomeCharacter::EndPlay(",
        )
        for saved in (
            "bFollowCameraWasActive = FollowCamera->IsActive();",
            "bFirstPersonCameraWasActive = FirstPersonCamera->IsActive();",
            "bVisualWasHiddenBeforeFirstPerson = bNearCameraVisualHidden;",
        ):
            self.assertIn(saved, toggle)
        self.assertIn(
            "FirstPersonCamera->SetActive(bFirstPersonCameraWasActive, true);",
            restore,
        )
        self.assertIn(
            "FollowCamera->SetActive(bFollowCameraWasActive, true);", restore
        )
        self.assertIn(
            "SetNearCameraVisualHidden(bVisualWasHiddenBeforeFirstPerson);", restore
        )

    def test_first_person_hides_only_owner_visual_and_keeps_mouse_look(self) -> None:
        occlusion = _method(
            self.character,
            "void AVistaPlayableHomeCharacter::UpdateNearCameraVisualOcclusion(",
            "void AVistaPlayableHomeCharacter::SetNearCameraVisualHidden(",
        )
        hide = _method(
            self.character,
            "void AVistaPlayableHomeCharacter::SetNearCameraVisualHidden(",
            "void AVistaPlayableHomeCharacter::RestoreNearCameraVisualOcclusion()",
        )
        look = _method(
            self.character,
            "void AVistaPlayableHomeCharacter::Look(",
            "void AVistaPlayableHomeCharacter::MoveForwardLegacy(",
        )
        self.assertIn("bFirstPersonViewEnabled && IsLocallyControlled()", occlusion)
        self.assertIn("SetNearCameraVisualHidden(true);", occlusion)
        self.assertIn("GetMesh()->SetOwnerNoSee(bHidden);", hide)
        self.assertIn(
            "CharacterProviderComponent->SetOwnerNoSeeForNearCamera(bHidden);",
            hide,
        )
        self.assertNotIn("SetVisibility", occlusion + hide)
        self.assertNotIn("SetActorHiddenInGame", occlusion + hide)
        self.assertIn("AddControllerYawInput(LookAxis.X);", look)
        self.assertIn("AddControllerPitchInput(LookAxis.Y);", look)
        self.assertNotIn("bFirstPersonViewEnabled", look)

    def test_lifecycle_and_hud_keep_the_mode_recoverable_and_discoverable(self) -> None:
        end_play = _method(
            self.character,
            "void AVistaPlayableHomeCharacter::EndPlay(",
            "void AVistaPlayableHomeCharacter::UnPossessed()",
        )
        unpossessed = _method(
            self.character,
            "void AVistaPlayableHomeCharacter::UnPossessed()",
            "void AVistaPlayableHomeCharacter::SetupPlayerInputComponent(",
        )
        self.assertIn("RestoreCameraPresentation();", end_play)
        self.assertIn("RestoreCameraPresentation();", unpossessed)
        self.assertIn("Character->IsFirstPersonViewEnabled()", self.hud)
        self.assertIn('TEXT("FIRST PERSON     [V] THIRD PERSON")', self.hud)
        self.assertIn('TEXT("THIRD PERSON     [V] FIRST PERSON")', self.hud)


if __name__ == "__main__":
    unittest.main()
