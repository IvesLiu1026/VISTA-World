from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
CHARACTER_H = PLUGIN / "Public/VistaPlayableHomeCharacter.h"
CHARACTER_CPP = PLUGIN / "Private/VistaPlayableHomeCharacter.cpp"
HUD_CPP = PLUGIN / "Private/VistaPlayableHomeHUD.cpp"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _method(source: str, name: str, next_name: str) -> str:
    return source.split(name, 1)[1].split(next_name, 1)[0]


def test_selector_uses_one_closed_deterministic_cycle_order() -> None:
    source = _source(CHARACTER_CPP)
    order = source.split("constexpr EVistaAffordance PlayerActionOrder[]", 1)[
        1
    ].split("};", 1)[0]
    expected = (
        "Press",
        "TurnOn",
        "TurnOff",
        "Open",
        "Close",
        "Inspect",
        "Sit",
        "Stand",
        "Pour",
        "PickUp",
        "Place",
    )
    offsets = [order.index(f"EVistaAffordance::{name}") for name in expected]
    assert offsets == sorted(offsets)
    assert "EVistaAffordance::Drop" not in order
    assert "EVistaAffordance::Toggle" not in order


def test_selector_filters_known_non_executable_state_before_display() -> None:
    source = _source(CHARACTER_CPP)
    build = _method(
        source,
        "AVistaPlayableHomeCharacter::BuildExecutablePlayerActions() const",
        "AVistaPlayableHomeCharacter::FindDefaultPlayerActionIndex",
    )
    assert "InspectionPresentation.bActive" in build
    assert "!PendingPresentationCommandId.IsNone()" in build
    assert "ActionExecutorComponent->HasActiveAction()" in build
    assert "TargetState.SemanticId.IsEmpty()" in build
    assert "TargetState.Transform.ContainsNaN()" in build
    assert "HasApprovedPlayerActionAnimation(" in build
    assert "PostureState != EVistaPostureState::Standing" in build
    assert "ActiveSeat->IsOccupiedBy(this, SemanticId)" in build
    assert "!ActiveSeat->IsReserved()" in build
    assert "bHasOpenState && !bOpen" in build
    assert "bHasOpenState && bOpen" in build
    assert "ApplianceBefore.bPowered &&" in build
    assert "!ApplianceBefore.bActive" in build
    assert "ApplianceBefore.bActive" in build
    assert "!Seat->IsOccupied() && !Seat->IsReserved()" in build
    assert "FocusedPickup->GetPhysicalDisposition() !=" in build
    assert "EVistaPickupDisposition::Held" in build


def test_pour_and_place_are_planned_from_typed_runtime_authorities() -> None:
    source = _source(CHARACTER_CPP)
    build = _method(
        source,
        "AVistaPlayableHomeCharacter::BuildExecutablePlayerActions() const",
        "AVistaPlayableHomeCharacter::FindDefaultPlayerActionIndex",
    )
    assert "Held->GetCarrier() == this" in build
    assert "Receiver->IsReserved()" in build
    assert "AVistaLiquidReceiverActor::PlanPourTransition(" in build
    assert "TransferMilliliters > KINDA_SMALL_NUMBER" in build
    assert "UVistaActionExecutorComponent::ResolveStablePlacementAnchor(" in build
    assert "ActionTarget = Held;" in build
    assert "SecondaryTarget = Receiver;" in build
    assert "SecondaryTarget = FocusedTarget;" in build


def test_selected_action_is_revalidated_server_side_and_uses_shared_executor() -> None:
    source = _source(CHARACTER_CPP)
    header = _source(CHARACTER_H)
    assert "ServerPerformSelectedPlayerAction(" in header
    server = _method(
        source,
        "ServerPerformSelectedPlayerAction_Implementation",
        "ClientBeginInspectionPresentation_Implementation",
    )
    assert "PerformRequestedPlayerAction" in server
    requested = _method(
        source,
        "AVistaPlayableHomeCharacter::PerformRequestedPlayerAction",
        "AVistaPlayableHomeCharacter::PerformPlayerAction",
    )
    assert "BuildExecutablePlayerActions()" in requested
    assert "Option.Matches(Requested)" in requested
    assert 'TEXT("PLAYER_ACTION_NOT_AVAILABLE")' in requested

    execute = _method(
        source,
        "AVistaPlayableHomeCharacter::PerformPlayerAction",
        "AVistaPlayableHomeCharacter::PerformInspectInteraction",
    )
    assert "BeginPhysicalInteraction(" in execute
    assert "BeginSemanticInteraction(" in execute
    assert "BeginAnimatedInspectInteraction()" in execute
    assert "Execute_VistaInteract" not in execute
    assert "InteractionComponent->TryInteract" not in execute


def test_existing_e_q_i_controls_remain_and_selector_has_direct_fallback_keys() -> None:
    source = _source(CHARACTER_CPP)
    setup = _method(
        source,
        "AVistaPlayableHomeCharacter::SetupPlayerInputComponent",
        "AVistaPlayableHomeCharacter::Move(",
    )
    for action, handler in (
        ("Interact", "InteractPressed"),
        ("Drop", "DropPressed"),
        ("Inspect", "InspectPressed"),
        ("ExitInspect", "ExitInspectPressed"),
    ):
        assert f'TEXT("{action}")' in setup
        assert handler in setup
    assert "EKeys::R" in setup
    assert "EKeys::MouseScrollDown" in setup
    assert "EKeys::MouseScrollUp" in setup
    assert "EKeys::F" in setup
    assert "CyclePlayerActionNextPressed" in setup
    assert "CyclePlayerActionPreviousPressed" in setup
    assert "ExecuteSelectedPlayerActionPressed" in setup


def test_hud_names_selected_action_and_only_offers_cycle_hint_when_useful() -> None:
    source = _source(HUD_CPP)
    assert "BuildSelectedActionLabel" in source
    for label in (
        "Press %s control",
        "Turn On %s",
        "Turn Off %s",
        "Open %s",
        "Close %s",
        "Inspect %s",
        "Sit on %s",
        "Stand up from %s",
        "Pour %s into %s",
        "Pick Up %s",
        "Place %s on %s",
    ):
        assert f'TEXT("{label}")' in source
    selector = source.split("FVistaPlayerActionOption SelectedAction", 1)[1].split(
        "const FVistaInspectionPresentation& Inspection", 1
    )[0]
    assert "Character->GetSelectedPlayerAction(SelectedAction)" in selector
    assert "Character->GetExecutablePlayerActions().Num()" in selector
    assert "ActionCount > 1" in selector
    assert 'TEXT("[F]  %s%s")' in selector
    assert 'TEXT("      [R / WHEEL]  SELECT  %d/%d")' in selector
