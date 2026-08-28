from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins" / "VistaPlayableHome" / "Source" / "VistaPlayableHome"
PROVIDER_HEADER = PLUGIN / "Public" / "VistaCharacterProviderComponent.h"
PROVIDER_SOURCE = PLUGIN / "Private" / "VistaCharacterProviderComponent.cpp"
NPC_HEADER = PLUGIN / "Public" / "VistaHomeNpcCharacter.h"
NPC_SOURCE = PLUGIN / "Private" / "VistaHomeNpcCharacter.cpp"


def test_provider_selection_is_default_manny_and_closed_to_one_reviewed_class() -> None:
    header = PROVIDER_HEADER.read_text(encoding="utf-8")
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")

    assert 'RequestedProviderId = TEXT("manny")' in header
    assert 'TEXT("VistaCharacterProvider=")' in source
    assert 'TEXT("metahuman_vivian_ue57_v1")' in source
    assert (
        'TEXT("/Game/VISTA/Characters/MetaHumans/Vivian_VISTA/"\n'
        '         "BP_Vivian_VISTA.BP_Vivian_VISTA_C")'
    ) in source
    assert source.count("BP_Vivian_VISTA.BP_Vivian_VISTA_C") == 1
    assert "FSoftObjectPath(MetaHumanVivianClassPath)" in source
    assert "FSoftObjectPath(ProviderValue)" not in source
    assert "LoadClass" not in source
    assert "TCP" not in source
    assert "NLP" not in source


def test_photoreal_child_hides_manny_only_after_validation() -> None:
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")

    assert "NewObject<UChildActorComponent>" in source
    assert "SetChildActorClass(LoadedProviderClass)" in source
    assert "SetRelativeLocation(FVector::ZeroVector)" in source
    assert "SetRelativeLocation(FVector(0.0f, 0.0f, -96.0f))" not in source
    assert "VisualActor->GetClass() != LoadedProviderClass" in source
    assert "!VisualActor->IsActorInitialized()" in source
    assert "LoadedProviderClass->IsChildOf(APawn::StaticClass())" in source
    assert "VisualActor->SetActorEnableCollision(false)" in source
    assert "Primitive->SetCollisionEnabled(ECollisionEnabled::NoCollision)" in source
    assert "Primitive->SetGenerateOverlapEvents(false)" in source
    assert "ValidateMetaHumanVisual(*VisualActor, FailureCode)" in source
    ready_branch = source.split("// This is intentionally the only path", 1)[1]
    assert ready_branch.index("SetMannyFallbackVisible(OwnerCharacter, false)") < (
        ready_branch.index("bPhotorealCharacterReady = true")
    )
    before_ready = source.split(
        "// This is intentionally the only path that hides Manny.", 1
    )[0]
    assert "SetMannyFallbackVisible(OwnerCharacter, false)" not in before_ready


def test_provider_requires_body_face_groom_and_animation_readiness() -> None:
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")

    for component_name in ('TEXT("Body")', 'TEXT("Face")'):
        assert component_name in source
    for failure_code in (
        "character_provider_body_not_ready",
        "character_provider_face_not_ready",
        "character_provider_groom_not_ready",
        "character_provider_animation_not_ready",
    ):
        assert failure_code in source
    assert "GetSkeletalMeshAsset()" in source
    assert "IsVisible()" in source
    assert "GetAnimInstance()" in source
    assert "GetAnimClass()" in source
    assert 'Contains(TEXT("Groom"), ESearchCase::IgnoreCase)' in source
    assert 'Contains(TEXT("Hair"), ESearchCase::IgnoreCase)' in source


def test_every_photoreal_failure_keeps_manny_and_reports_stable_status() -> None:
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")

    assert 'TEXT("photoreal_character_unavailable")' in source
    unavailable = source.split(
        "void UVistaCharacterProviderComponent::SetPhotorealUnavailable", 1
    )[1]
    assert "SetMannyFallbackVisible(OwnerCharacter, true);" in unavailable
    assert "ActiveProviderId = MannyProviderId;" in unavailable
    assert "ProviderStatus = PhotorealUnavailableStatus;" in unavailable
    assert "bPhotorealCharacterReady = false;" in unavailable
    assert "Manny remains active" in unavailable


def test_npc_owns_provider_without_changing_semantic_or_animation_components() -> None:
    header = NPC_HEADER.read_text(encoding="utf-8")
    source = NPC_SOURCE.read_text(encoding="utf-8")

    assert (
        "TObjectPtr<UVistaCharacterProviderComponent> CharacterProviderComponent;"
        in header
    )
    assert (
        "CreateDefaultSubobject<UVistaCharacterProviderComponent>(\n"
        '            TEXT("VistaCharacterProviderComponent"))'
    ) in source
    assert (
        source.count(
            'CreateDefaultSubobject<UVistaAnimationComponent>(TEXT("VistaAnimationComponent"))'
        )
        == 1
    )
    assert "AIControllerClass = AVistaHomeNpcController::StaticClass();" in source


def test_runtime_state_reports_provider_without_accepting_mutation() -> None:
    source = NPC_SOURCE.read_text(encoding="utf-8")

    for key in (
        "character_provider_id",
        "character_provider_status",
        "photoreal_character_ready",
        "character_provider_failure_code",
    ):
        assert f'TEXT("{key}")' in source
    apply_state = source.split(
        "AVistaHomeNpcCharacter::VistaApplyRuntimeState_Implementation", 1
    )[1].split("AVistaHomeNpcCharacter::VistaInteract_Implementation", 1)[0]
    assert "character_provider" not in apply_state
    assert "photoreal_character" not in apply_state
