from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome"
PUBLIC = PLUGIN / "Public"
PRIVATE = PLUGIN / "Private"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def _anchor_safe_model(
    *,
    requester: str,
    anchor_owner: str,
    parent_owner: str,
    parent: str,
    character_mesh: str,
    provider_grips: tuple[str, ...] = (),
    socket: str = "hand_r",
    validated: bool = True,
    camera_chain: bool = False,
) -> bool:
    exact_body_parent = parent == character_mesh and socket == "hand_r"
    exact_provider = len(provider_grips) == 1 and parent == provider_grips[0]
    return (
        requester == anchor_owner == parent_owner
        and validated
        and not camera_chain
        and (exact_body_parent or exact_provider)
    )


def _replicated_disposition_model(disposition: str) -> dict[str, object]:
    if disposition == "held":
        return {"attached": True, "simulate": False, "collision": "none"}
    if disposition == "placed":
        return {"attached": False, "simulate": False, "collision": "world"}
    return {"attached": False, "simulate": True, "collision": "world"}


def test_player_carry_anchor_is_body_owned_and_never_camera_owned() -> None:
    player = _source(PRIVATE / "VistaPlayableHomeCharacter.cpp")
    executor = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    constructor = _between(
        player,
        "AVistaPlayableHomeCharacter::AVistaPlayableHomeCharacter()",
        "void AVistaPlayableHomeCharacter::BeginPlay",
    )
    assert 'CarryAnchor->SetupAttachment(GetMesh(), TEXT("hand_r"));' in constructor
    assert "CarryAnchor->SetupAttachment(FollowCamera)" not in constructor
    assert 'TEXT("VistaValidatedCarryAnchor")' in constructor

    safe = _between(
        executor,
        "bool UVistaActionExecutorComponent::IsCarryAnchorSafe",
        "USceneComponent* UVistaActionExecutorComponent::PrepareCarryAnchor",
    )
    assert "HasCameraInAttachmentChain(Anchor)" in safe
    assert "Parent->GetOwner() != Requester" in safe
    assert "ProviderGripMatches == 1" in safe
    assert "ParentMesh == Character->GetMesh()" in safe
    assert "Anchor->GetAttachSocketName() == RightHandSocket" in safe
    assert "ParentMesh->DoesSocketExist(RightHandSocket)" in safe
    prepare = _between(
        executor,
        "USceneComponent* UVistaActionExecutorComponent::PrepareCarryAnchor",
        "FString UVistaActionExecutorComponent::CanonicalRequestHex",
    )
    assert "VistaProviderGripSocket" in executor
    assert "Component->ComponentHasTag(ProviderGripTag)" in prepare
    assert "PROVIDER_GRIP_AMBIGUOUS" in prepare
    assert "RIGHT_HAND_SOCKET_UNAVAILABLE" in prepare
    assert "SnapToTargetNotIncludingScale" in prepare

    assert _anchor_safe_model(
        requester="npc",
        anchor_owner="npc",
        parent_owner="npc",
        parent="mesh",
        character_mesh="mesh",
    )
    assert not _anchor_safe_model(
        requester="npc",
        anchor_owner="npc",
        parent_owner="foreign",
        parent="mesh",
        character_mesh="mesh",
    )
    assert not _anchor_safe_model(
        requester="npc",
        anchor_owner="npc",
        parent_owner="npc",
        parent="wrong_same_owner_mesh",
        character_mesh="mesh",
    )
    assert not _anchor_safe_model(
        requester="npc",
        anchor_owner="npc",
        parent_owner="npc",
        parent="grip_a",
        character_mesh="mesh",
        provider_grips=("grip_a", "grip_b"),
    )


def test_place_resolves_true_stable_target_point_from_focused_owner_tags() -> None:
    executor = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    player = _source(PRIVATE / "VistaPlayableHomeCharacter.cpp")
    resolver = _between(
        executor,
        "USceneComponent* UVistaActionExecutorComponent::ResolveStablePlacementAnchor",
        "bool UVistaActionExecutorComponent::IsCarryAnchorSafe",
    )
    for token in (
        "TActorIterator<ATargetPoint>",
        "VistaOwner=",
        "VistaSemanticId=",
        "StableAnchorIdentity",
        "IdentityMatches != 1",
        "PLACEMENT_ANCHOR_IDENTITY_AMBIGUOUS",
        "DistanceSquared",
        "Left.SemanticId < Right.SemanticId",
        'TEXT("/entity.")',
    ):
        assert token in executor or token in resolver
    assert "return Candidates[0].Anchor->GetRootComponent();" in resolver

    begin = _between(
        executor,
        "bool UVistaActionExecutorComponent::BeginPhysicalInteraction",
        "void UVistaActionExecutorComponent::TickComponent",
    )
    assert "Cast<ATargetPoint>(Request.PlacementAnchor->GetOwner())" in begin
    assert "Request.PlacementAnchor != AnchorActor->GetRootComponent()" in begin
    assert "PLACEMENT_TARGET_POINT_INVALID" in begin

    start_animation = _between(
        executor,
        "bool UVistaActionExecutorComponent::StartAnimation",
        "void UVistaActionExecutorComponent::AdvanceAnimation",
    )
    assert "ActiveAction->PlacementAnchor->GetOwner()" in start_animation
    assert "ActiveAction->PlacementOwner.Get()" not in start_animation

    player_interact = _between(
        player,
        "FVistaInteractionResult AVistaPlayableHomeCharacter::PerformDefaultInteraction",
        "EVistaAffordance AVistaPlayableHomeCharacter::GetDefaultInteractionAffordance",
    )
    assert "HeldItem, EVistaAffordance::Place, Target" in player_interact
    assert "Target->GetRootComponent()" not in player_interact


def test_pickup_actor_attaches_only_to_a_validated_hand_or_provider_grip() -> None:
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    attach = _between(
        pickup,
        "FVistaInteractionResult AVistaPickupActor::TryAttachTo",
        "FVistaInteractionResult AVistaPickupActor::ReleaseFromCarrier",
    )
    assert "UVistaActionExecutorComponent::PrepareCarryAnchor" in attach
    assert "IVistaItemCarrier::Execute_VistaTryClaimItem" in attach
    apply = _between(
        pickup,
        "bool AVistaPickupActor::ApplyPhysicalDisposition",
        "void AVistaPickupActor::NormalizePlacementState",
    )
    assert "UVistaActionExecutorComponent::PrepareCarryAnchor" in apply
    assert "AttachToComponent(" in apply
    assert "Anchor," in apply
    assert "GetAttachParent() == Anchor" in apply
    assert "CARRY_ATTACHMENT_FAILED" in attach
    assert "PhysicalDisposition = Previous" in attach


def test_npc_carry_anchor_is_constructor_deterministic_and_replication_safe() -> None:
    header = _source(PUBLIC / "VistaHomeNpcCharacter.h")
    npc = _source(PRIVATE / "VistaHomeNpcCharacter.cpp")
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    constructor = _between(
        npc,
        "AVistaHomeNpcCharacter::AVistaHomeNpcCharacter()",
        "FString AVistaHomeNpcCharacter::VistaGetSemanticId_Implementation",
    )
    for token in (
        'CarryAnchor->SetupAttachment(GetMesh(), TEXT("hand_r"));',
        "CarryAnchor->SetRelativeTransform(FTransform::Identity);",
        "CarryAnchor->SetIsReplicated(true);",
        'CarryAnchor->ComponentTags.Add(TEXT("VistaValidatedCarryAnchor"));',
    ):
        assert token in constructor
    assert "FollowCamera" not in constructor
    assert "ReplicatedUsing = OnRep_HeldItem" in header
    assert "UFUNCTION()\n    void OnRep_HeldItem();" in header
    begin_play = _between(
        npc,
        "void AVistaHomeNpcCharacter::BeginPlay",
        "void AVistaHomeNpcCharacter::EnsureCarryAnchorReady",
    )
    on_rep = _between(
        npc,
        "void AVistaHomeNpcCharacter::OnRep_HeldItem",
        "USceneComponent* AVistaHomeNpcCharacter::VistaGetCarryAnchor_Implementation",
    )
    assert "EnsureCarryAnchorReady();" in begin_play
    assert "EnsureCarryAnchorReady();" in on_rep
    assert "DOREPLIFETIME(AVistaHomeNpcCharacter, HeldItem);" in npc

    pickup_on_rep = _between(
        pickup,
        "void AVistaPickupActor::OnRep_PhysicalDisposition",
        "void AVistaPickupActor::NormalizePlacementState",
    )
    assert "ApplyPhysicalDisposition()" in pickup_on_rep
    assert "UVistaActionExecutorComponent::PrepareCarryAnchor(Carrier" in pickup_on_rep


def test_one_replicated_disposition_drives_all_client_physical_state() -> None:
    types = _source(PUBLIC / "VistaPlayableHomeTypes.h")
    header = _source(PUBLIC / "VistaPickupActor.h")
    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    for token in (
        "EVistaPickupDisposition::Free",
        "EVistaPickupDisposition::Held",
        "EVistaPickupDisposition::Placed",
    ):
        assert token in pickup or token in types
    for token in (
        "FVistaPickupReplicatedDisposition",
        "PlacementAnchorSemanticId",
        "WorldTransform",
        "AttachmentRelativeTransform",
        "bSimulatePhysics",
        "CollisionEnabled",
        "CollisionProfileName",
        "LinearVelocity",
        "AngularVelocityDegrees",
    ):
        assert token in header
    assert header.count("ReplicatedUsing = OnRep_PhysicalDisposition") == 1
    assert "ReplicatedUsing = OnRep_HeldBy" not in header
    assert "DOREPLIFETIME(AVistaPickupActor, PhysicalDisposition);" in pickup
    on_rep = _between(
        pickup,
        "void AVistaPickupActor::OnRep_PhysicalDisposition",
        "void AVistaPickupActor::SyncRuntimeDispositionValues",
    )
    assert "ApplyPhysicalDisposition()" in on_rep
    release = _between(
        pickup,
        "FVistaInteractionResult AVistaPickupActor::ReleaseFromCarrier",
        "void AVistaPickupActor::OnRep_PhysicalDisposition",
    )
    assert "PlacementAnchor->GetComponentTransform()" in release
    assert "EVistaPickupDisposition::Placed" in release
    assert "PhysicalDisposition.bSimulatePhysics = !IsValid(PlacementAnchor)" in release
    apply = _between(
        pickup,
        "bool AVistaPickupActor::ApplyPhysicalDisposition",
        "bool AVistaPickupActor::ClearForTrustedBaselineRestore",
    )
    assert "SetSimulatePhysics(PhysicalDisposition.bSimulatePhysics)" in apply
    assert "PhysicalDisposition.Disposition == EVistaPickupDisposition::Placed" in apply
    assert "!PhysicalDisposition.bSimulatePhysics" in apply
    assert _replicated_disposition_model("free")["simulate"] is True
    assert _replicated_disposition_model("held")["simulate"] is False
    assert _replicated_disposition_model("placed")["simulate"] is False


def test_contact_requires_exact_carry_parent_and_exact_place_transform() -> None:
    executor = _source(PRIVATE / "VistaActionExecutorComponent.cpp")
    effect = _between(
        executor,
        "bool PhysicalSnapshotMatchesEffect",
        "bool RuntimeStatesEquivalent",
    )
    assert "CurrentParent == CarryAnchor" in effect
    assert "Pickup->GetCarrier() == Request.Requester" in effect
    assert "PlacementAnchor->GetComponentTransform()" in effect
    assert "TransformBitsEqual(" in effect
    assert "Snapshot.WorldTransform.Equals" not in effect
    assert "0.01f" not in effect
    assert "CurrentParent == nullptr" in effect
    commit = _between(
        executor,
        "bool UVistaActionExecutorComponent::CommitContact",
        "void UVistaActionExecutorComponent::AdvanceAfterContact",
    )
    assert "ActiveAction->CarryAnchor.Get()" in commit
    assert "ActiveAction->PlacementAnchor.Get()" in commit

    pickup = _source(PRIVATE / "VistaPickupActor.cpp")
    release = _between(
        pickup,
        "FVistaInteractionResult AVistaPickupActor::ReleaseFromCarrier",
        "void AVistaPickupActor::OnRep_PhysicalDisposition",
    )
    assert "PLACEMENT_TRANSFORM_MISMATCH" in release
    assert "PhysicalDisposition = Previous" in release


def test_live_contract_exposes_transaction_evidence_and_requires_place_anchor() -> None:
    runtime_header = _source(PUBLIC / "VistaPlayableHomeRuntimeSubsystem.h")
    runtime = _source(PRIVATE / "VistaPlayableHomeRuntimeSubsystem.cpp")
    tcp = _source(PRIVATE / "VistaWorldTcpAdapter.cpp")
    for token in ("bHasActionTransaction", "ActionTransaction"):
        assert token in runtime_header
    for token in (
        'TEXT("action_transaction")',
        'TEXT("phase_history")',
        'TEXT("before_state")',
        'TEXT("contact_state")',
        'TEXT("after_state")',
        'TEXT("before_physical_state")',
        'TEXT("contact_physical_state")',
        'TEXT("after_physical_state")',
        'TEXT("simulate_physics")',
        'TEXT("collision_profile")',
        'TEXT("linear_velocity_cm_s")',
        'TEXT("angular_velocity_deg_s")',
        'TEXT("attachment_parent_owner_semantic_id")',
        'TEXT("attachment_socket")',
        'TEXT("carrier_semantic_id")',
        'TEXT("inventory_carrier_semantic_id")',
        'TEXT("inventory_slot_occupied")',
        'TEXT("inventory_item_semantic_id")',
        'TEXT("placed_at_semantic_id")',
        'TEXT("physical_mutation_count")',
        'TEXT("contact_mutation_attempted")',
        'TEXT("rollback_attempted")',
        'TEXT("rolled_back")',
        'TEXT("requester_before_transform")',
        'TEXT("requester_contact_transform")',
        'TEXT("requester_after_transform")',
        'TEXT("requester_transform_restored")',
    ):
        assert token in tcp
    branch = tcp.split('Operation == TEXT("interaction")', 1)[1].split(
        'Operation == TEXT("npc_cancel")', 1
    )[0]
    assert "Command.Affordance == EVistaAffordance::Place" in branch
    assert "PLACEMENT_ANCHOR_REQUIRED" in branch
    assert "PLACEMENT_ANCHOR_UNEXPECTED" in branch
    assert "Runtime->ExecuteInteraction(Command)" in branch
    apply_result = _between(
        runtime,
        "void UVistaPlayableHomeRuntimeSubsystem::ApplyTransactionResult",
        "FVistaLiveCommandResult UVistaPlayableHomeRuntimeSubsystem::ExecuteNpcQueue",
    )
    assert "OutResult.bHasActionTransaction = true" in apply_result
    assert (
        "Transaction.Status == EVistaActionTransactionStatus::Running" in apply_result
    )
