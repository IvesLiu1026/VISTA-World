from __future__ import annotations

import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
CHARACTER_H = PLUGIN / "Public/VistaPlayableHomeCharacter.h"
CHARACTER_CPP = PLUGIN / "Private/VistaPlayableHomeCharacter.cpp"
HUD_CPP = PLUGIN / "Private/VistaPlayableHomeHUD.cpp"
INTERACTION_H = PLUGIN / "Public/VistaInteractionComponent.h"
INTERACTION_CPP = PLUGIN / "Private/VistaInteractionComponent.cpp"
SEMANTIC_EXECUTOR_CPP = PLUGIN / "Private/VistaActionExecutorSemantic.cpp"
COMPOSE = ROOT / "tools/ue/vista_playable_home/compose_home_commandlet.py"
BUILD = ROOT / "tools/ue/vista_playable_home/build_home.py"
MATERIALIZER = ROOT / "tools/ue/vista_playable_home/materialize_package_project.py"


def _source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def test_inspect_is_a_separate_i_key_action_with_two_explicit_exit_paths() -> None:
    header = _source(CHARACTER_H)
    source = _source(CHARACTER_CPP)

    assert "TObjectPtr<UInputAction> InspectAction;" in header
    assert "TObjectPtr<UInputAction> ExitInspectAction;" in header
    assert 'BindAction(TEXT("Inspect"), IE_Pressed' in source
    assert 'BindAction(TEXT("ExitInspect"), IE_Pressed' in source
    assert "&ThisClass::InspectPressed" in source
    assert "&ThisClass::ExitInspectPressed" in source
    assert "if (InspectionPresentation.bActive)" in source
    assert "ExitInspection();" in source


def test_player_inspect_waits_for_the_typed_animation_before_presentation() -> None:
    header = _source(CHARACTER_H)
    source = _source(CHARACTER_CPP)

    pressed = source.split("void AVistaPlayableHomeCharacter::InspectPressed()", 1)[
        1
    ].split("void AVistaPlayableHomeCharacter::ExitInspectPressed()", 1)[0]
    begin = source.split(
        "AVistaPlayableHomeCharacter::BeginAnimatedInspectInteraction()", 1
    )[1].split("void AVistaPlayableHomeCharacter::PresentCompletedInspection", 1)[0]
    feedback = source.split(
        "void AVistaPlayableHomeCharacter::UpdatePendingActionFeedback()", 1
    )[1].split("AVistaPlayableHomeCharacter::BeginAnimatedInspectInteraction()", 1)[0]

    public_api = source.split(
        "FVistaInteractionResult AVistaPlayableHomeCharacter::PerformInspectInteraction()",
        1,
    )[1].split("void AVistaPlayableHomeCharacter::BeginInspectionPresentation", 1)[0]

    assert "PerformInspectInteraction()" in pressed
    assert "return BeginAnimatedInspectInteraction();" in public_api
    default_interaction = source.split(
        "FVistaInteractionResult AVistaPlayableHomeCharacter::PerformDefaultInteraction()",
        1,
    )[1].split(
        "EVistaAffordance AVistaPlayableHomeCharacter::GetDefaultInteractionAffordance",
        1,
    )[0]
    assert "Affordance == EVistaAffordance::Inspect" in default_interaction
    assert "return BeginAnimatedInspectInteraction();" in default_interaction
    assert "BeginSemanticInteraction(Target, EVistaAffordance::Inspect)" in begin
    assert "PendingInspectionTarget = Target" in begin
    assert "Record.Status == EVistaActionTransactionStatus::Succeeded" in feedback
    assert "Record.Affordance == EVistaAffordance::Inspect" in feedback
    assert "Record.bHasAfterState" in feedback
    assert "Record.AfterState" in feedback
    assert "TWeakObjectPtr<AActor> PendingInspectionTarget;" in header


def test_multi_affordance_objects_keep_e_primary_and_offer_i_inspect() -> None:
    character = _source(CHARACTER_CPP)
    hud = _source(HUD_CPP)

    assert "GetDefaultInteractionAffordance(Target)" in character
    assert "Affordances.Contains(EVistaAffordance::PickUp)" in character
    assert "Affordances.Contains(EVistaAffordance::Open)" in character
    assert "Affordances.Contains(EVistaAffordance::Toggle)" in character
    assert "Affordances.Contains(EVistaAffordance::Inspect)" in character
    assert "SupportsInspect(FocusedActor)" in hud
    assert 'Prompt += TEXT("      [I]  Inspect")' in hud


def test_inspection_projection_is_read_only_bounded_and_allow_listed() -> None:
    source = _source(CHARACTER_CPP)
    header = _source(CHARACTER_H)
    executor = _source(SEMANTIC_EXECUTOR_CPP)

    assert "RuntimeStatesEquivalent(Before, After)" in executor
    assert "INSPECT_MUTATION_REJECTED" in executor
    assert "Execute_VistaApplyRuntimeState" in executor
    assert "MaximumPresentationTextCharacters = 128" in source
    assert "InspectionMaximumSeconds = 20.0" in source
    assert "InspectionMaximumDistanceCm = 500.0f" in source
    assert "arbitrary actor state is never copied here" in header
    assert "TArray<FVistaInspectionStateRow> PublicState;" in header
    assert "TMap<FName, FString> PublicState;" not in header

    projection = source.split("static const FName PublicValueKeys[]", 1)[1].split(
        "};", 1
    )[0]
    assert set(
        token
        for token in ("open", "active", "powered", "on", "held", "placed_at")
        if f'TEXT("{token}")' in projection
    ) == {"open", "active", "powered", "on", "held", "placed_at"}
    for forbidden in ("event", "goal", "oracle", "review", "token", "secret"):
        assert forbidden not in projection.casefold()


def test_inspection_observation_is_published_only_after_read_only_validation() -> None:
    executor = _source(SEMANTIC_EXECUTOR_CPP)
    interaction_header = _source(INTERACTION_H)
    interaction_source = _source(INTERACTION_CPP)

    assert "TryInteractDeferredObservation" not in interaction_header
    assert "TryInteractDeferredObservation" not in interaction_source
    assert "bPublishSuccessfulObservation" not in interaction_source
    effect = executor.split("bool StateMatchesSemanticEffect", 1)[1].split(
        "bool ResolveContactLocation", 1
    )[0]
    complete = executor.split(
        "void UVistaActionExecutorComponent::CompleteSemanticSuccess", 1
    )[1].split("void UVistaActionExecutorComponent::FinishSemanticFailure", 1)[0]
    assert "Affordance == EVistaAffordance::Inspect" in effect
    assert "RuntimeStatesEquivalent(Before, After)" in effect
    assert complete.index("StateMatchesSemanticEffect(") < complete.index(
        "RecordSuccessfulInteraction("
    )
    assert complete.count("RecordSuccessfulInteraction(") == 1


def test_pending_inspect_is_revision_bound_cancelable_and_snapshot_exact() -> None:
    source = _source(CHARACTER_CPP)
    header = _source(CHARACTER_H)
    interaction = _source(INTERACTION_H)

    semantic = source.split(
        "FVistaInteractionResult AVistaPlayableHomeCharacter::BeginSemanticInteraction",
        1,
    )[1].split("USceneComponent* AVistaPlayableHomeCharacter::VistaGetCarryAnchor", 1)[
        0
    ]
    cancel = source.split(
        "bool AVistaPlayableHomeCharacter::CancelPendingAnimatedInspection", 1
    )[1].split("void AVistaPlayableHomeCharacter::PresentCompletedInspection", 1)[0]
    present = source.split(
        "void AVistaPlayableHomeCharacter::PresentCompletedInspection", 1
    )[1].split(
        "FVistaInteractionResult AVistaPlayableHomeCharacter::PerformDefaultInteraction",
        1,
    )[0]

    assert "GetExpectedRevision() const" in interaction
    assert "Request.ExpectedRevision" in semantic
    assert "InteractionComponent->GetExpectedRevision()" in semantic
    assert "Events->GetSessionGeneration()" in semantic
    assert "CancelActiveAction(Reason)" in cancel
    assert "ServerCancelPendingInspection" in header
    assert 'CancelPendingAnimatedInspection(TEXT("PLAYER_UNPOSSESSED"))' in source
    assert 'CancelPendingAnimatedInspection(TEXT("PLAYER_INSPECT_CANCELED"))' in source
    assert "const FVistaEntityRuntimeState& InspectedState" in present
    assert "BuildInspectionPresentation(Target, InspectedState)" in present
    assert "Execute_VistaGetRuntimeState(Target)" not in present
    assert "ACTION_RECEIPT_UNAVAILABLE" in source
    assert (
        source.count(
            "const bool bHadPendingAction = !PendingPresentationCommandId.IsNone();"
        )
        == 2
    )
    assert (
        source.count("bHadPendingAction || !PendingPresentationCommandId.IsNone()") == 2
    )
    assert source.count("UpdatePendingActionFeedback();") >= 7
    assert source.count('FName(TEXT("ACTION_IN_PROGRESS"))') == 2


def test_rejected_e_and_async_phases_flow_to_typed_hud_feedback() -> None:
    source = _source(CHARACTER_CPP)
    header = _source(CHARACTER_H)
    hud = _source(HUD_CPP)

    assert "FVistaPlayerActionFeedback" in header
    assert "ClientPresentInteractionFeedback" in header
    assert "PublishInteractionResult(Result);" in source
    assert "UpdatePendingActionFeedback();" in source
    assert "Record.IsTerminal()" in source
    assert "Feedback.Code" in hud
    assert "PhaseLabel(Feedback.Phase)" in hud
    assert "ResultStatusLabel(Feedback)" in hud


def test_all_input_contract_generators_require_inspect_and_escape() -> None:
    compose = _source(COMPOSE)
    build = _source(BUILD)
    materializer = _source(MATERIALIZER)

    for source in (compose, build, materializer):
        assert '("Inspect", "I")' in source or 'ActionName="Inspect"' in source
        assert (
            '("ExitInspect", "Escape")' in source
            or 'ActionName="ExitInspect"' in source
        )

    assert (
        'ActionName="Inspect",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=I'
        in build
    )
    assert (
        'ActionName="ExitInspect",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=Escape'
        in build
    )
