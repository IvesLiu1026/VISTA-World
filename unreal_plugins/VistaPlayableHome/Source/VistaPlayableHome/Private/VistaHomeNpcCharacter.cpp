#include "VistaHomeNpcCharacter.h"

#include "Animation/AnimInstance.h"
#include "Components/CapsuleComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Net/UnrealNetwork.h"
#include "UObject/ConstructorHelpers.h"
#include "VistaAnimationComponent.h"
#include "VistaCharacterProviderComponent.h"
#include "VistaHomeNpcController.h"
#include "VistaPickupActor.h"

AVistaHomeNpcCharacter::AVistaHomeNpcCharacter()
{
    bReplicates = true;
    // Match the authored 34 cm navigation-agent radius. A 100 cm doorway then
    // retains 32 cm of total lateral clearance while the 96 cm half-height stays fixed.
    GetCapsuleComponent()->InitCapsuleSize(34.0f, 96.0f);
    AIControllerClass = AVistaHomeNpcController::StaticClass();
    AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
    GetCharacterMovement()->bOrientRotationToMovement = true;
    GetCharacterMovement()->RotationRate = FRotator(0.0f, 360.0f, 0.0f);
    GetCharacterMovement()->MaxWalkSpeed = 240.0f;

    static ConstructorHelpers::FObjectFinder<USkeletalMesh> MannyMesh(
        TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny.SKM_Manny"));
    if (MannyMesh.Succeeded())
    {
        GetMesh()->SetSkeletalMesh(MannyMesh.Object);
        GetMesh()->SetRelativeLocation(FVector(0.0f, 0.0f, -96.0f));
        GetMesh()->SetRelativeRotation(FRotator(0.0f, -90.0f, 0.0f));
    }
    static ConstructorHelpers::FClassFinder<UAnimInstance> MannyAnimBlueprint(
        TEXT("/Game/Characters/Mannequins/Animations/ABP_Manny"));
    if (MannyAnimBlueprint.Succeeded())
    {
        GetMesh()->SetAnimInstanceClass(MannyAnimBlueprint.Class);
    }

    AllowedAffordances = {EVistaAffordance::Inspect};

    AnimationComponent =
        CreateDefaultSubobject<UVistaAnimationComponent>(TEXT("VistaAnimationComponent"));

    CharacterProviderComponent =
        CreateDefaultSubobject<UVistaCharacterProviderComponent>(
            TEXT("VistaCharacterProviderComponent"));
    CharacterProviderComponent->RequestedProviderId =
        UVistaCharacterProviderComponent::GetMannyProviderId();
    CharacterProviderComponent->bAllowCommandLineProviderOverride = false;

    CarryAnchor = CreateDefaultSubobject<USceneComponent>(TEXT("VistaCarryAnchor"));
    CarryAnchor->SetupAttachment(GetMesh());
    CarryAnchor->SetRelativeLocation(FVector(35.0f, 25.0f, 110.0f));
    CarryAnchor->ComponentTags.Add(TEXT("VistaCarryAnchor"));
}

FString AVistaHomeNpcCharacter::VistaGetSemanticId_Implementation() const
{
    return SemanticId;
}

TArray<EVistaAffordance> AVistaHomeNpcCharacter::VistaGetAffordances_Implementation() const
{
    return AllowedAffordances;
}

FVistaEntityRuntimeState AVistaHomeNpcCharacter::VistaGetRuntimeState_Implementation() const
{
    FVistaEntityRuntimeState State;
    State.SemanticId = SemanticId;
    State.Transform = GetActorTransform();
    State.bHidden = IsHidden();
    State.Values.Add(TEXT("current_room_id"), CurrentRoomId);
    if (IsValid(CharacterProviderComponent))
    {
        State.Values.Add(
            TEXT("character_provider_id"),
            CharacterProviderComponent->ActiveProviderId.ToString());
        State.Values.Add(
            TEXT("character_provider_status"),
            CharacterProviderComponent->GetProviderStatus().ToString());
        State.Values.Add(
            TEXT("photoreal_character_ready"),
            CharacterProviderComponent->IsPhotorealCharacterReady()
                ? TEXT("true")
                : TEXT("false"));
        if (!CharacterProviderComponent->ProviderFailureCode.IsNone())
        {
            State.Values.Add(
                TEXT("character_provider_failure_code"),
                CharacterProviderComponent->ProviderFailureCode.ToString());
        }
    }
    return State;
}

FVistaInteractionResult AVistaHomeNpcCharacter::VistaApplyRuntimeState_Implementation(
    const FVistaEntityRuntimeState& State)
{
    if (!State.SemanticId.IsEmpty() && State.SemanticId != SemanticId)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::NotFound, TEXT("SEMANTIC_ID_MISMATCH"), SemanticId);
    }
    SetActorTransform(State.Transform, false, nullptr, ETeleportType::TeleportPhysics);
    SetActorHiddenInGame(State.bHidden);
    SetActorEnableCollision(!State.bHidden);
    if (const FString* Room = State.Values.Find(TEXT("current_room_id")))
    {
        CurrentRoomId = *Room;
    }
    return FVistaInteractionResult::Success(
        SemanticId, VistaGetRuntimeState_Implementation(), TEXT("STATE_APPLIED"));
}

FVistaInteractionResult AVistaHomeNpcCharacter::VistaInteract_Implementation(
    const FVistaInteractionRequest& Request)
{
    if (!IsValid(Request.Requester))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidRequester, TEXT("REQUESTER_REQUIRED"), SemanticId);
    }
    if (!Request.ExpectedRevision.IsNone() && Request.ExpectedRevision != WorldRevision)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::RevisionMismatch, TEXT("REVISION_MISMATCH"), SemanticId);
    }
    if (!AllowedAffordances.Contains(Request.Affordance))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Unsupported, TEXT("AFFORDANCE_UNSUPPORTED"), SemanticId);
    }
    return FVistaInteractionResult::Success(
        SemanticId, VistaGetRuntimeState_Implementation(), TEXT("NPC_INSPECTED"));
}

void AVistaHomeNpcCharacter::BeginPlay()
{
    Super::BeginPlay();
    // Event-only residents are serialized hidden by the world composer.  Keep
    // their capsule from becoming an invisible navigation obstacle until an
    // event queue explicitly reveals them.
    SetActorEnableCollision(!IsHidden());
    if (!SemanticId.IsEmpty())
    {
        Tags.AddUnique(FName(*SemanticId));
        if (CurrentRoomId.IsEmpty())
        {
            const int32 EntityMarker = SemanticId.Find(TEXT("/entity."));
            if (EntityMarker > 0)
            {
                CurrentRoomId = SemanticId.Left(EntityMarker);
            }
        }
    }
}

USceneComponent* AVistaHomeNpcCharacter::VistaGetCarryAnchor_Implementation() const
{
    return CarryAnchor;
}

AActor* AVistaHomeNpcCharacter::VistaGetHeldItem_Implementation() const
{
    return HeldItem;
}

bool AVistaHomeNpcCharacter::VistaTryClaimItem_Implementation(AActor* Item)
{
    AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(Item);
    if (!IsValid(Pickup) || IsValid(HeldItem))
    {
        return false;
    }
    HeldItem = Pickup;
    return true;
}

void AVistaHomeNpcCharacter::VistaReleaseItem_Implementation(AActor* Item)
{
    if (HeldItem == Item)
    {
        HeldItem = nullptr;
    }
}

void AVistaHomeNpcCharacter::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaHomeNpcCharacter, HeldItem);
}
