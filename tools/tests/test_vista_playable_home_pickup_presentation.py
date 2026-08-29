from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / (
    "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Public/"
    "VistaPickupActor.h"
)
SOURCE = ROOT / (
    "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Private/"
    "VistaPickupActor.cpp"
)


def _function(source: str, signature: str, next_signature: str) -> str:
    return source.split(signature, 1)[1].split(next_signature, 1)[0]


def test_pickup_exposes_one_closed_presentation_binding_surface() -> None:
    header = HEADER.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")

    assert "TObjectPtr<UStaticMeshComponent> PresentationMesh;" in header
    assert "bool ConfigurePresentationMesh(" in header
    assert "UStaticMesh* StaticMesh," in header
    assert "const FTransform& RelativeTransform);" in header
    assert "void ClearPresentationMesh();" in header
    assert "bool HasPresentationMesh() const;" in header

    configure = _function(
        source,
        "bool AVistaPickupActor::ConfigurePresentationMesh(",
        "void AVistaPickupActor::ClearPresentationMesh()",
    )
    assert "!IsValid(PresentationMesh) || !IsValid(StaticMesh)" in configure
    assert "RelativeTransform.ContainsNaN()" in configure
    assert "PresentationMesh->SetStaticMesh(StaticMesh);" in configure
    assert "PresentationMesh->SetRelativeTransform(RelativeTransform);" in configure
    assert "RefreshPresentationState();" in configure


def test_presentation_child_is_render_only_and_movable() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    constructor = _function(
        source,
        "AVistaPickupActor::AVistaPickupActor()",
        "bool AVistaPickupActor::ConfigurePresentationMesh(",
    )
    refresh = source.split("void AVistaPickupActor::RefreshPresentationState()", 1)[1]

    assert (
        'CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PresentationMesh"))'
        in constructor
    )
    assert "PresentationMesh->SetupAttachment(Mesh);" in constructor
    for contract in (
        "PresentationMesh->SetMobility(EComponentMobility::Movable);",
        "PresentationMesh->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);",
        "PresentationMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);",
        "PresentationMesh->SetSimulatePhysics(false);",
        "PresentationMesh->SetGenerateOverlapEvents(false);",
        "PresentationMesh->SetCanEverAffectNavigation(false);",
    ):
        assert contract in constructor
        assert contract in refresh


def test_runtime_attachment_keeps_presentation_under_pickup_actor_authority() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    refresh = source.split("void AVistaPickupActor::RefreshPresentationState()", 1)[1]
    attach = _function(
        source,
        "FVistaInteractionResult AVistaPickupActor::TryAttachTo(AActor* Carrier)",
        "FVistaInteractionResult AVistaPickupActor::ReleaseFromCarrier(",
    )
    release = _function(
        source,
        "FVistaInteractionResult AVistaPickupActor::ReleaseFromCarrier(",
        "void AVistaPickupActor::OnRep_PhysicalDisposition()",
    )
    attachment_state = _function(
        source,
        "bool AVistaPickupActor::ApplyPhysicalDisposition()",
        "bool AVistaPickupActor::ClearForTrustedBaselineRestore(",
    )

    assert "PresentationMesh->SetVisibility(bHasPresentation, false);" in refresh
    assert "if (bHasPresentation)" in refresh
    assert "Mesh->SetVisibility(false, false);" in refresh
    assert "SetActorHiddenInGame" not in source

    assert "SetRootComponent(Mesh);" in source
    assert "AttachToComponent(" in attachment_state
    assert (
        "DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);"
        in attachment_state
    )
    assert "Mesh->SetCollisionProfileName(" in attachment_state
    assert (
        "Mesh->SetSimulatePhysics(PhysicalDisposition.bSimulatePhysics);"
        in attachment_state
    )
    assert "PhysicalDisposition = Previous;" in release
    assert "ApplyPhysicalDisposition();" in release
    for direct_mutation in (
        "DetachFromActor(",
        "Mesh->SetCollisionProfileName(",
        "Mesh->SetSimulatePhysics(",
        "AttachToComponent(",
    ):
        assert direct_mutation not in release
    assert "PresentationMesh" not in attach
    assert "PresentationMesh" not in release
    assert "PresentationMesh" not in attachment_state


def test_no_presentation_restores_original_mesh_without_state_mutation() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    clear = _function(
        source,
        "void AVistaPickupActor::ClearPresentationMesh()",
        "bool AVistaPickupActor::HasPresentationMesh() const",
    )
    refresh = source.split("void AVistaPickupActor::RefreshPresentationState()", 1)[1]

    assert "PresentationMesh->SetStaticMesh(nullptr);" in clear
    assert "PresentationMesh->SetRelativeTransform(FTransform::Identity);" in clear
    assert "Mesh->SetVisibility(true, false);" in clear
    assert "const bool bHasPresentation = HasPresentationMesh();" in refresh
    assert "Mesh->SetVisibility(true, false);" not in refresh
    for state_token in ("HeldBy", "RuntimeStateValues", "bPortable"):
        assert state_token not in clear
