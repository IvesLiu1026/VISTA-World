from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins" / "VistaPlayableHome" / "Source" / "VistaPlayableHome"
PROVIDER_HEADER = PLUGIN / "Public" / "VistaCharacterProviderComponent.h"
PROVIDER_SOURCE = PLUGIN / "Private" / "VistaCharacterProviderComponent.cpp"
NPC_HEADER = PLUGIN / "Public" / "VistaHomeNpcCharacter.h"
NPC_SOURCE = PLUGIN / "Private" / "VistaHomeNpcCharacter.cpp"
PLAYER_HEADER = PLUGIN / "Public" / "VistaPlayableHomeCharacter.h"
PLAYER_SOURCE = PLUGIN / "Private" / "VistaPlayableHomeCharacter.cpp"
BUILD_RULES = PLUGIN / "VistaPlayableHome.Build.cs"
PLUGIN_DESCRIPTOR = (
    ROOT / "unreal_plugins" / "VistaPlayableHome" / "VistaPlayableHome.uplugin"
)


def test_provider_selection_is_default_manny_and_closed_to_one_reviewed_class() -> None:
    header = PROVIDER_HEADER.read_text(encoding="utf-8")
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")

    assert 'RequestedProviderId = TEXT("manny")' in header
    assert "bool bAllowCommandLineProviderOverride = false;" in header
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
    assert "ACharacter* OwnerCharacter = Cast<ACharacter>(GetOwner());" in source
    resolver = source.split(
        "FName UVistaCharacterProviderComponent::ResolveRequestedProviderId", 1
    )[1].split(
        "bool UVistaCharacterProviderComponent::ActivateAllowlistedMetaHuman", 1
    )[0]
    assert "if (bAllowCommandLineProviderOverride)" in resolver


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
        "character_provider_source_animation_not_ready",
        "character_provider_retarget_asset_unavailable",
        "character_provider_retarget_component_unavailable",
        "character_provider_retarget_binding_failed",
        "character_provider_retarget_tick_order_invalid",
        "character_provider_retarget_not_ready",
    ):
        assert failure_code in source
    assert "GetSkeletalMeshAsset()" in source
    assert "IsVisible()" in source
    assert "GetAnimInstance()" in source
    assert "GetAnimClass()" in source
    assert 'Contains(TEXT("Groom"), ESearchCase::IgnoreCase)' in source
    assert 'Contains(TEXT("Hair"), ESearchCase::IgnoreCase)' in source


def test_epic_retarget_component_drives_vivian_from_hidden_manny() -> None:
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")

    assert (
        'TEXT("/Game/Characters/Mannequins/Rigs/"\n'
        '         "RTG_Mannequin.RTG_Mannequin")'
    ) in source
    assert source.count("RTG_Mannequin.RTG_Mannequin") == 1
    assert "TSoftObjectPtr<UIKRetargeter>" in source
    configure = source.split(
        "bool UVistaCharacterProviderComponent::ConfigureMetaHumanRetarget", 1
    )[1].split("bool UVistaCharacterProviderComponent::ValidateMetaHumanVisual", 1)[0]
    for token in (
        "NewObject<URetargetComponent>",
        "&VisualActor",
        "VisualActor.AddInstanceComponent(ProviderRetargetComponent)",
        "ProviderRetargetComponent->RegisterComponent()",
        "ProviderRetargetComponent->SetForceOtherMeshesToFollowControlledMesh(false)",
        "ProviderRetargetComponent->SetSourcePerformerMesh(SourceManny)",
        "ProviderRetargetComponent->SetControlledMesh(Body)",
        "ProviderRetargetComponent->SetRetargetAsset(&RetargetAsset)",
        "SourceSkeletalMeshComponent.OverrideComponent.Get()",
        "ControlledSkeletalMeshComponent.OverrideComponent.Get()",
        "ProviderRetargetComponent->InitiateAnimation()",
        "Body->PrimaryComponentTick.GetPrerequisites().ContainsByPredicate",
        "Prerequisite.Get() == &SourceManny->PrimaryComponentTick",
        "SourceManny->SetCollisionEnabled(ECollisionEnabled::NoCollision)",
        "SourceManny->SetGenerateOverlapEvents(false)",
        "SourceManny->SetComponentTickEnabled(true)",
        "EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones",
    ):
        assert token in configure

    # Epic clears SourceSkeletalMeshComponent.OverrideComponent in OnRegister,
    # so the external Manny source must be wired only after registration.
    assert configure.index("RegisterComponent()") < configure.index(
        "SetSourcePerformerMesh(SourceManny)"
    )
    # Setting this after both meshes are bound would clear Face/clothing anim state.
    assert configure.index(
        "SetForceOtherMeshesToFollowControlledMesh(false)"
    ) < configure.index("SetSourcePerformerMesh(SourceManny)")

    validate = source.split(
        "bool UVistaCharacterProviderComponent::ValidateMetaHumanVisual(", 1
    )[1].split(
        "USkeletalMeshComponent* UVistaCharacterProviderComponent::FindNamedSkeletalMesh",
        1,
    )[0]
    assert "Cast<URetargetAnimInstance>(Body->GetAnimInstance())" in validate
    assert (
        "ProviderRetargetComponent->bForceOtherMeshesToFollowControlledMesh" in validate
    )
    assert "ProviderRetargetComponent->RetargetAsset" in validate


def test_hidden_manny_keeps_animation_authority_without_hiding_children() -> None:
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")
    visibility = source.split(
        "void UVistaCharacterProviderComponent::SetMannyFallbackVisible", 1
    )[1].split(
        "void UVistaCharacterProviderComponent::DestroyProviderRetargetComponent", 1
    )[0]

    assert "MannyMesh->SetVisibility(bVisible, false);" in visibility
    assert "MannyMesh->SetHiddenInGame(!bVisible, false);" in visibility
    assert "SetVisibility(bVisible, true)" not in visibility
    assert "SetHiddenInGame(!bVisible, true)" not in visibility

    teardown = source.split(
        "void UVistaCharacterProviderComponent::DestroyProviderRetargetComponent", 1
    )[1].split("void UVistaCharacterProviderComponent::SetPhotorealUnavailable", 1)[0]
    assert "UActorComponent* RetargetComponentToDestroy" in teardown
    assert "RetargetComponentToDestroy->DestroyComponent();" in teardown

    failed_activation = source.split(
        "bool UVistaCharacterProviderComponent::ActivateAllowlistedMetaHuman", 1
    )[1].split(
        "bool UVistaCharacterProviderComponent::ValidateMetaHumanVisualShell", 1
    )[0]
    assert failed_activation.index("DestroyProviderRetargetComponent();") < (
        failed_activation.index("DestroyProviderChildActorComponent();")
    )

    child_teardown = source.split(
        "void UVistaCharacterProviderComponent::DestroyProviderChildActorComponent", 1
    )[1].split("void UVistaCharacterProviderComponent::SetPhotorealUnavailable", 1)[0]
    assert "ProviderChildActorComponent->DestroyChildActor();" in child_teardown
    assert "ProviderChildActorComponent->DestroyComponent();" in child_teardown
    assert "ProviderChildActorComponent = nullptr;" in child_teardown


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
    assert (
        "CharacterProviderComponent->RequestedProviderId =\n"
        "        UVistaCharacterProviderComponent::GetMannyProviderId();"
    ) in source
    assert "bAllowCommandLineProviderOverride = false;" in source


def test_only_player_defaults_to_vivian_and_accepts_process_override() -> None:
    player_header = PLAYER_HEADER.read_text(encoding="utf-8")
    player_source = PLAYER_SOURCE.read_text(encoding="utf-8")
    npc_source = NPC_SOURCE.read_text(encoding="utf-8")

    assert (
        "TObjectPtr<UVistaCharacterProviderComponent> CharacterProviderComponent;"
        in player_header
    )
    assert (
        "CreateDefaultSubobject<UVistaCharacterProviderComponent>(\n"
        '            TEXT("VistaCharacterProviderComponent"))'
    ) in player_source
    assert (
        "CharacterProviderComponent->RequestedProviderId =\n"
        "        UVistaCharacterProviderComponent::GetMetaHumanVivianProviderId();"
    ) in player_source
    assert "bAllowCommandLineProviderOverride = true;" in player_source
    assert "GetMetaHumanVivianProviderId" not in npc_source


def test_runtime_module_declares_exact_retarget_dependencies() -> None:
    build = BUILD_RULES.read_text(encoding="utf-8")
    descriptor = json.loads(PLUGIN_DESCRIPTOR.read_text(encoding="utf-8"))
    private_dependencies = build.split("PrivateDependencyModuleNames.AddRange", 1)[1]

    for dependency in ("IKRig", "PerformanceCaptureCore"):
        assert f'"{dependency}"' in private_dependencies
    enabled_plugins = {
        item["Name"] for item in descriptor["Plugins"] if item.get("Enabled") is True
    }
    assert {
        "EnhancedInput",
        "IKRig",
        "PerformanceCaptureCore",
        "MetaHumanCharacter",
    }.issubset(enabled_plugins)


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


def test_event_only_npc_visibility_also_controls_capsule_collision() -> None:
    source = NPC_SOURCE.read_text(encoding="utf-8")
    event_source = (PLUGIN / "Private" / "VistaEventSubsystem.cpp").read_text(
        encoding="utf-8"
    )

    apply_state = source.split(
        "AVistaHomeNpcCharacter::VistaApplyRuntimeState_Implementation", 1
    )[1].split("AVistaHomeNpcCharacter::VistaInteract_Implementation", 1)[0]
    assert "SetActorHiddenInGame(State.bHidden);" in apply_state
    assert "SetActorEnableCollision(!State.bHidden);" in apply_state
    begin_play = source.split("void AVistaHomeNpcCharacter::BeginPlay()", 1)[1].split(
        "USceneComponent* AVistaHomeNpcCharacter::VistaGetCarryAnchor", 1
    )[0]
    assert "SetActorEnableCollision(!IsHidden());" in begin_play

    queue = event_source.split(
        "if (Operation.Type == EVistaEventOperationType::SetNpcQueue)", 1
    )[1].split('OutCode = TEXT("TARGET_NOT_STATEFUL")', 1)[0]
    assert queue.index("ReplaceActionQueue") < queue.index(
        "Npc->SetActorHiddenInGame(false);"
    )
    assert "Npc->SetActorEnableCollision(true);" in queue
