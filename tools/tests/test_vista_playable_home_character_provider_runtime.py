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
PLUGIN_CONFIG = (
    ROOT
    / "unreal_plugins"
    / "VistaPlayableHome"
    / "Config"
    / "DefaultVistaPlayableHome.ini"
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


def test_citysample_provider_is_closed_to_the_fixed_character_class() -> None:
    header = PROVIDER_HEADER.read_text(encoding="utf-8")
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")

    assert "GetCitySampleCrowdVisualDemoProviderId" in header
    assert 'TEXT("citysample_crowd_visual_demo_v1")' in source
    assert (
        'TEXT("/Game/CitySampleCrowd/Blueprints/"\n'
        '         "BP_CrowdCharacter.BP_CrowdCharacter_C")'
    ) in source
    assert source.count("BP_CrowdCharacter.BP_CrowdCharacter_C") == 1
    assert "TSoftClassPtr<ACharacter>" in source
    assert "FSoftObjectPath(CitySampleCrowdVisualDemoClassPath)" in source
    assert "LoadedProviderClass->IsChildOf(ACharacter::StaticClass())" in source
    assert "ProviderId == CitySampleCrowdVisualDemoProviderId" in source
    assert "FSoftObjectPath(ProviderValue)" not in source
    assert "LoadClass" not in source


def test_citysample_provider_requires_human_argv_and_refuses_world_port() -> None:
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")
    gate = source.split(
        "bool UVistaCharacterProviderComponent::"
        "IsCitySampleHumanVisualDemoCommandLineAllowed",
        1,
    )[1].split("void UVistaCharacterProviderComponent::SetOwnerNoSeeForNearCamera", 1)[
        0
    ]
    activation = source.split(
        "bool UVistaCharacterProviderComponent::"
        "ActivateAllowlistedCitySampleVisualDemo",
        1,
    )[1].split(
        "bool UVistaCharacterProviderComponent::NeutralizeCitySampleCharacter", 1
    )[0]

    assert 'TEXT("VistaHumanOperatedVisualDemo")' in source
    assert 'TEXT("VistaWorldPort=")' in source
    assert "ESearchCase::IgnoreCase" in gate
    assert "FParse::Param(" in gate
    assert "HumanOperatedVisualDemoCommandLineFlag" in gate
    assert "bAllowCommandLineProviderOverride" in gate
    assert "FParse::Value(" in gate
    assert "CharacterProviderCommandLineKey" in gate
    assert "FName(*ProviderValue) != CitySampleCrowdVisualDemoProviderId" in gate
    for failure_code in (
        "citysample_visual_demo_world_port_forbidden",
        "citysample_visual_demo_human_argv_required",
        "citysample_visual_demo_provider_argv_required",
        "citysample_visual_demo_provider_argv_mismatch",
    ):
        assert failure_code in gate
    assert activation.index("IsCitySampleHumanVisualDemoCommandLineAllowed") < (
        activation.index("ProviderClass.LoadSynchronous()")
    )


def test_citysample_character_is_neutralized_to_a_visual_child() -> None:
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")
    activation = source.split(
        "bool UVistaCharacterProviderComponent::"
        "ActivateAllowlistedCitySampleVisualDemo",
        1,
    )[1].split(
        "bool UVistaCharacterProviderComponent::NeutralizeCitySampleCharacter", 1
    )[0]
    neutralize = source.split(
        "bool UVistaCharacterProviderComponent::NeutralizeCitySampleCharacter", 1
    )[1].split(
        "bool UVistaCharacterProviderComponent::ValidateCitySampleVisualDemo", 1
    )[0]
    validate = source.split(
        "bool UVistaCharacterProviderComponent::ValidateCitySampleVisualDemo", 1
    )[1].split(
        "bool UVistaCharacterProviderComponent::ValidateMetaHumanVisualShell", 1
    )[0]

    assert "ProviderChildActorComponent->CreateChildActor(" in activation
    assert activation.index("CreateChildActor(") < activation.index(
        "ProviderChildActorComponent->RegisterComponent()"
    )
    customizer = activation.split("ProviderChildActorComponent->CreateChildActor(", 1)[
        1
    ].split("ProviderChildActorComponent->RegisterComponent()", 1)[0]
    assert "AutoPossessPlayer" in customizer
    assert "AutoPossessAI" in customizer
    assert "AIControllerClass = nullptr" in customizer

    for token in (
        "VisualCharacter.AutoPossessPlayer = EAutoReceiveInput::Disabled",
        "VisualCharacter.AutoPossessAI = EAutoPossessAI::Disabled",
        "VisualCharacter.AIControllerClass = nullptr",
        "VisualController->UnPossess()",
        "VisualController->SetActorTickEnabled(false)",
        "VisualController->Destroy()",
        "VisualCharacter.SetReplicates(false)",
        "VisualCharacter.SetReplicateMovement(false)",
        "VisualCharacter.SetCanAffectNavigationGeneration(false)",
        "VisualCharacter.SetActorTickEnabled(false)",
        "VisualMovement->StopMovementImmediately()",
        "VisualMovement->DisableMovement()",
        "VisualMovement->Deactivate()",
        "VisualMovement->SetComponentTickEnabled(false)",
        "VisualCharacter.SetActorEnableCollision(false)",
        "VisualCapsule->SetCollisionEnabled(ECollisionEnabled::NoCollision)",
        "DisableVisualCollision(VisualCharacter)",
        "VisualCharacter.AttachToComponent(",
        "FAttachmentTransformRules::SnapToTargetNotIncludingScale",
        "VisualCharacter.SetOwner(&OwnerCharacter)",
    ):
        assert token in neutralize
    assert neutralize.index("AutoPossessAI = EAutoPossessAI::Disabled") < (
        neutralize.index("VisualController->UnPossess()")
    )
    assert neutralize.index("VisualMovement->Deactivate()") < neutralize.index(
        "VisualCharacter.SetOwner(&OwnerCharacter)"
    )
    assert "VisualCharacter.GetAttachParentActor() != &OwnerCharacter" in validate
    assert "VisualCharacter.GetController() != nullptr" in validate
    assert "VisualMovement->IsActive()" in validate
    assert "VisualMovement->IsComponentTickEnabled()" in validate
    assert "VisualCharacter.GetActorEnableCollision()" in validate
    assert "Primitive->GetCollisionEnabled()" in validate
    assert "Primitive->GetGenerateOverlapEvents()" in validate


def test_citysample_visual_uses_hidden_manny_retarget_without_crowd_loop() -> None:
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")
    activation = source.split(
        "bool UVistaCharacterProviderComponent::"
        "ActivateAllowlistedCitySampleVisualDemo",
        1,
    )[1].split(
        "bool UVistaCharacterProviderComponent::NeutralizeCitySampleCharacter", 1
    )[0]
    configure = source.split(
        "bool UVistaCharacterProviderComponent::ConfigureMetaHumanRetarget", 1
    )[1].split("bool UVistaCharacterProviderComponent::ValidateMetaHumanVisual", 1)[0]

    assert "NPC1_AnimBP" not in source
    assert "VisualBody->SetAnimInstanceClass(nullptr);" in activation
    assert activation.index("VisualBody->SetAnimInstanceClass(nullptr)") < (
        activation.index("ConfigureMetaHumanRetarget(")
    )
    assert "ACharacter* VisualCharacter = Cast<ACharacter>(&VisualActor)" in configure
    assert "Body = VisualCharacter->GetMesh();" in configure
    assert "ProviderRetargetComponent->SetSourcePerformerMesh(SourceManny)" in configure
    assert "ProviderRetargetComponent->SetControlledMesh(Body)" in configure
    assert activation.index("ValidateCitySampleVisualDemo(") < activation.index(
        "SetMannyFallbackVisible(OwnerCharacter, false)"
    )


def test_citysample_visual_fit_is_configurable_measured_and_fail_closed() -> None:
    header = PROVIDER_HEADER.read_text(encoding="utf-8")
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")
    config = PLUGIN_CONFIG.read_text(encoding="utf-8")
    activation = source.split(
        "bool UVistaCharacterProviderComponent::"
        "ActivateAllowlistedCitySampleVisualDemo",
        1,
    )[1].split(
        "bool UVistaCharacterProviderComponent::NeutralizeCitySampleCharacter", 1
    )[0]
    configure = source.split(
        "bool UVistaCharacterProviderComponent::ConfigureCitySampleVisualFit", 1
    )[1].split("bool UVistaCharacterProviderComponent::ValidateCitySampleVisualFit", 1)[
        0
    ]
    validate_fit = source.split(
        "bool UVistaCharacterProviderComponent::ValidateCitySampleVisualFit", 1
    )[1].split(
        "bool UVistaCharacterProviderComponent::ValidateCitySampleVisualDemo", 1
    )[0]
    validate_demo = source.split(
        "bool UVistaCharacterProviderComponent::ValidateCitySampleVisualDemo", 1
    )[1].split(
        "bool UVistaCharacterProviderComponent::ValidateMetaHumanVisualShell", 1
    )[0]

    for field, default, clamp_max in (
        ("CitySampleVisualScale", "0.90f", 'ClampMax = "1.00"'),
        ("CitySampleVisualFloorClearanceCm", "1.0f", 'ClampMax = "5.00"'),
        ("CitySampleVisualTopClearanceCm", "2.0f", 'ClampMax = "10.00"'),
    ):
        assert field in header
        assert "Config" in header.split(field, 1)[0].rsplit("UPROPERTY", 1)[1]
        assert clamp_max in header.split(field, 1)[0].rsplit("UPROPERTY", 1)[1]
        assert f"{field} = {default};" in header
    assert "[/Script/VistaPlayableHome.VistaCharacterProviderComponent]" in config
    assert "CitySampleVisualScale=0.900000" in config
    assert "CitySampleVisualFloorClearanceCm=1.000000" in config
    assert "CitySampleVisualTopClearanceCm=2.000000" in config

    assert (
        activation.index("ConfigureMetaHumanRetarget(")
        < activation.index("ConfigureCitySampleVisualFit(")
        < activation.index("ValidateCitySampleVisualDemo(")
    )
    assert (
        "VisualCharacter.SetActorRelativeScale3D(FVector(CitySampleVisualScale))"
        in configure
    )
    assert "TryMeasureVisibleSkeletalBounds(VisualCharacter, VisualBounds)" in configure
    assert "VisualBounds.GetSize().Z" in configure
    assert "OwnerCapsule->GetScaledCapsuleHalfHeight()" in configure
    assert "VisualCharacter.AddActorWorldOffset(" in configure
    assert "ETeleportType::TeleportPhysics" in configure
    assert "ValidateCitySampleVisualFit(" in configure
    assert "VISTA_CITYSAMPLE_VISUAL_FIT" in configure

    for function in (configure, validate_fit):
        assert "ECollisionEnabled::NoCollision" in function
        assert "GetCollisionResponseToChannel(ECC_WorldStatic) != ECR_Block" in function
        assert (
            "GetCollisionResponseToChannel(ECC_WorldDynamic) != ECR_Block" in function
        )
        assert "citysample_visual_demo_capsule_authority_invalid" in function
    assert "citysample_visual_demo_scaled_height_exceeds_capsule" in configure
    assert "citysample_visual_demo_capsule_alignment_invalid" in validate_fit
    assert "ValidateCitySampleVisualFit(" in validate_demo


def test_citysample_visual_fit_keeps_visual_collision_disabled() -> None:
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")
    configure = source.split(
        "bool UVistaCharacterProviderComponent::ConfigureCitySampleVisualFit", 1
    )[1].split("bool UVistaCharacterProviderComponent::ValidateCitySampleVisualFit", 1)[
        0
    ]
    neutralize = source.split(
        "bool UVistaCharacterProviderComponent::NeutralizeCitySampleCharacter", 1
    )[1].split(
        "bool UVistaCharacterProviderComponent::ConfigureCitySampleVisualFit", 1
    )[0]

    assert "SetCollisionEnabled" not in configure
    assert "SetCollisionResponse" not in configure
    assert "VisualCharacter.SetActorEnableCollision(false)" in neutralize
    assert (
        "VisualCapsule->SetCollisionEnabled(ECollisionEnabled::NoCollision)"
        in neutralize
    )
    assert "DisableVisualCollision(VisualCharacter)" in neutralize


def test_citysample_status_makes_no_runtime_fidelity_or_ai_use_claim() -> None:
    source = PROVIDER_SOURCE.read_text(encoding="utf-8")
    activation = source.split(
        "bool UVistaCharacterProviderComponent::"
        "ActivateAllowlistedCitySampleVisualDemo",
        1,
    )[1].split(
        "bool UVistaCharacterProviderComponent::NeutralizeCitySampleCharacter", 1
    )[0]

    assert 'TEXT("citysample_visual_demo_active_unverified")' in source
    assert 'TEXT("citysample_visual_demo_unavailable")' in source
    assert "CitySampleVisualDemoActiveUnverifiedStatus" in activation
    assert "bPhotorealCharacterReady = false;" in activation
    assert "bPhotorealCharacterReady = true;" not in activation
    assert "human_operated_only=true" in activation
    assert "ai_vlm_data_use=forbidden" in activation
    assert "combined_runtime_proof=required" in activation
    assert "photoreal_claim=false" in activation
    assert "gta_quality_claim=false" in activation


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
