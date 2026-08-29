#include "Tests/VistaR5MultiClientProofActors.h"

#include "Components/SceneComponent.h"
#include "Net/UnrealNetwork.h"
#include "VistaActionExecutorComponent.h"
#include "VistaPickupActor.h"

namespace
{
constexpr const TCHAR* StableSemanticTagPrefix = TEXT("VistaSemanticId=");
constexpr const TCHAR* PlacementOwnerTagPrefix = TEXT("VistaOwner=");
const FName ProviderGripTag(TEXT("VistaProviderGripSocket"));
const FName ValidatedCarryAnchorTag(TEXT("VistaValidatedCarryAnchor"));
}

AVistaR5ProofCarrier::AVistaR5ProofCarrier()
{
    bReplicates = true;
    SetReplicateMovement(true);

    USceneComponent* SceneRoot =
        CreateDefaultSubobject<USceneComponent>(TEXT("ProofCarrierRoot"));
    SetRootComponent(SceneRoot);

    ProviderGrip =
        CreateDefaultSubobject<USceneComponent>(TEXT("ProofProviderGrip"));
    ProviderGrip->SetupAttachment(SceneRoot);
    ProviderGrip->ComponentTags.Add(ProviderGripTag);

    CarryAnchor =
        CreateDefaultSubobject<USceneComponent>(TEXT("ProofCarryAnchor"));
    CarryAnchor->SetupAttachment(ProviderGrip);
    CarryAnchor->SetRelativeTransform(FTransform::Identity);
    CarryAnchor->ComponentTags.Add(ValidatedCarryAnchorTag);

    ActionExecutor = CreateDefaultSubobject<UVistaActionExecutorComponent>(
        TEXT("ProofActionExecutor"));
}

void AVistaR5ProofCarrier::ConfigureProofIdentity(
    const FString& InSemanticId)
{
    check(HasAuthority());
    ProofSemanticId = InSemanticId;
    SemanticId = ProofSemanticId;
    ApplyProofIdentityTags();
    ForceNetUpdate();
}

void AVistaR5ProofCarrier::OnRep_ProofSemanticId()
{
    SemanticId = ProofSemanticId;
    ApplyProofIdentityTags();
}

void AVistaR5ProofCarrier::ApplyProofIdentityTags()
{
    if (ProofSemanticId.IsEmpty())
    {
        return;
    }
    Tags.AddUnique(FName(*ProofSemanticId));
    Tags.AddUnique(FName(*(FString(StableSemanticTagPrefix) + ProofSemanticId)));
}

USceneComponent*
AVistaR5ProofCarrier::VistaGetCarryAnchor_Implementation() const
{
    return CarryAnchor;
}

AActor* AVistaR5ProofCarrier::VistaGetHeldItem_Implementation() const
{
    return HeldItem;
}

bool AVistaR5ProofCarrier::VistaTryClaimItem_Implementation(AActor* Item)
{
    AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(Item);
    if (!HasAuthority() || !IsValid(Pickup) || IsValid(HeldItem))
    {
        return false;
    }
    HeldItem = Pickup;
    ForceNetUpdate();
    return HeldItem == Pickup;
}

void AVistaR5ProofCarrier::VistaReleaseItem_Implementation(AActor* Item)
{
    if (HasAuthority() && HeldItem == Item)
    {
        HeldItem = nullptr;
        ForceNetUpdate();
    }
}

void AVistaR5ProofCarrier::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaR5ProofCarrier, ProofSemanticId);
    DOREPLIFETIME(AVistaR5ProofCarrier, HeldItem);
}

AVistaR5ProofPlacementAnchor::AVistaR5ProofPlacementAnchor(
    const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
{
    bReplicates = true;
    SetReplicateMovement(true);
}

void AVistaR5ProofPlacementAnchor::ConfigureProofIdentity(
    const FString& InOwnerSemanticId,
    const FString& InAnchorSemanticId)
{
    check(HasAuthority());
    ProofOwnerSemanticId = InOwnerSemanticId;
    ProofAnchorSemanticId = InAnchorSemanticId;
    ApplyProofIdentityTags();
    ForceNetUpdate();
}

void AVistaR5ProofPlacementAnchor::OnRep_ProofIdentity()
{
    ApplyProofIdentityTags();
}

void AVistaR5ProofPlacementAnchor::ApplyProofIdentityTags()
{
    if (ProofOwnerSemanticId.IsEmpty() || ProofAnchorSemanticId.IsEmpty())
    {
        return;
    }
    Tags.AddUnique(FName(*(
        FString(StableSemanticTagPrefix) + ProofAnchorSemanticId)));
    Tags.AddUnique(FName(*(
        FString(PlacementOwnerTagPrefix) + ProofOwnerSemanticId)));
}

bool AVistaR5ProofPlacementAnchor::HasAppliedProofIdentity() const
{
    return !ProofOwnerSemanticId.IsEmpty() &&
        !ProofAnchorSemanticId.IsEmpty() &&
        ActorHasTag(FName(*(
            FString(StableSemanticTagPrefix) + ProofAnchorSemanticId))) &&
        ActorHasTag(FName(*(
            FString(PlacementOwnerTagPrefix) + ProofOwnerSemanticId)));
}

void AVistaR5ProofPlacementAnchor::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaR5ProofPlacementAnchor, ProofOwnerSemanticId);
    DOREPLIFETIME(AVistaR5ProofPlacementAnchor, ProofAnchorSemanticId);
}
