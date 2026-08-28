#include "VistaCharacterProviderComponent.h"

#include "Animation/AnimInstance.h"
#include "Components/ChildActorComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "UObject/SoftObjectPtr.h"
#include "VistaHomeNpcCharacter.h"

DEFINE_LOG_CATEGORY_STATIC(LogVistaCharacterProvider, Log, All);

namespace
{
const FName MannyProviderId(TEXT("manny"));
const FName MetaHumanVivianProviderId(TEXT("metahuman_vivian_ue57_v1"));
const FName MannyActiveStatus(TEXT("manny_active"));
const FName PhotorealReadyStatus(TEXT("photoreal_character_ready"));
const FName PhotorealUnavailableStatus(TEXT("photoreal_character_unavailable"));
const TCHAR* CharacterProviderCommandLineKey = TEXT("VistaCharacterProvider=");

// This is the only external visual class that the runtime may load. The path is
// compiled into the plugin and mirrors the reviewed disposable-project authoring
// commandlet; RequestedProviderId can never be interpreted as an object path.
const TCHAR* MetaHumanVivianClassPath =
    TEXT("/Game/VISTA/Characters/MetaHumans/Vivian_VISTA/"
         "BP_Vivian_VISTA.BP_Vivian_VISTA_C");

const FName BodyComponentName(TEXT("Body"));
const FName FaceComponentName(TEXT("Face"));
}

UVistaCharacterProviderComponent::UVistaCharacterProviderComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
}

void UVistaCharacterProviderComponent::BeginPlay()
{
    Super::BeginPlay();

    AVistaHomeNpcCharacter* OwnerCharacter = Cast<AVistaHomeNpcCharacter>(GetOwner());
    if (!IsValid(OwnerCharacter))
    {
        ProviderStatus = PhotorealUnavailableStatus;
        ProviderFailureCode = TEXT("character_provider_owner_invalid");
        return;
    }

    // Manny is deliberately made visible first. Every failure path therefore
    // leaves the semantic NPC functional and visually inspectable.
    SetMannyFallbackVisible(*OwnerCharacter, true);
    ActiveProviderId = MannyProviderId;
    ProviderStatus = MannyActiveStatus;
    ProviderFailureCode = NAME_None;
    bPhotorealCharacterReady = false;

    const FName ProviderId = ResolveRequestedProviderId();
    if (ProviderId == MannyProviderId)
    {
        return;
    }
    if (ProviderId != MetaHumanVivianProviderId)
    {
        SetPhotorealUnavailable(
            *OwnerCharacter,
            TEXT("character_provider_not_allowlisted"));
        return;
    }

    ActivateAllowlistedMetaHuman(*OwnerCharacter);
}

FName UVistaCharacterProviderComponent::ResolveRequestedProviderId() const
{
    FString ProviderValue;
    if (!FParse::Value(
            FCommandLine::Get(),
            CharacterProviderCommandLineKey,
            ProviderValue))
    {
        ProviderValue = RequestedProviderId.ToString();
    }
    ProviderValue.TrimStartAndEndInline();
    ProviderValue.ToLowerInline();
    return ProviderValue.IsEmpty() ? MannyProviderId : FName(*ProviderValue);
}

bool UVistaCharacterProviderComponent::ActivateAllowlistedMetaHuman(
    AVistaHomeNpcCharacter& OwnerCharacter)
{
    const TSoftClassPtr<AActor> ProviderClass{
        FSoftObjectPath(MetaHumanVivianClassPath)};
    UClass* LoadedProviderClass = ProviderClass.LoadSynchronous();
    if (!IsValid(LoadedProviderClass) ||
        !LoadedProviderClass->IsChildOf(AActor::StaticClass()) ||
        LoadedProviderClass->IsChildOf(APawn::StaticClass()))
    {
        SetPhotorealUnavailable(
            OwnerCharacter,
            TEXT("character_provider_class_unavailable"));
        return false;
    }

    ProviderChildActorComponent = NewObject<UChildActorComponent>(
        &OwnerCharacter,
        TEXT("VistaPhotorealCharacterChild"));
    if (!IsValid(ProviderChildActorComponent))
    {
        SetPhotorealUnavailable(
            OwnerCharacter,
            TEXT("character_provider_child_component_unavailable"));
        return false;
    }

    OwnerCharacter.AddInstanceComponent(ProviderChildActorComponent);
    ProviderChildActorComponent->SetupAttachment(OwnerCharacter.GetRootComponent());
    ProviderChildActorComponent->SetRelativeLocation(FVector::ZeroVector);
    ProviderChildActorComponent->SetRelativeRotation(FRotator::ZeroRotator);
    ProviderChildActorComponent->SetChildActorClass(LoadedProviderClass);
    ProviderChildActorComponent->RegisterComponent();

    AActor* VisualActor = ProviderChildActorComponent->GetChildActor();
    FName FailureCode = NAME_None;
    if (!IsValid(VisualActor) || VisualActor->GetClass() != LoadedProviderClass ||
        !VisualActor->IsActorInitialized() || VisualActor->IsActorBeingDestroyed())
    {
        FailureCode = TEXT("character_provider_actor_unavailable");
    }
    else
    {
        // The assembled Blueprint is a visual shell. Canonical movement,
        // navigation and interaction collision stay on AVistaHomeNpcCharacter.
        VisualActor->SetActorEnableCollision(false);
        VisualActor->SetCanBeDamaged(false);
        DisableVisualCollision(*VisualActor);
        if (ValidateMetaHumanVisual(*VisualActor, FailureCode))
        {
            // This is intentionally the only path that hides Manny.
            SetMannyFallbackVisible(OwnerCharacter, false);
            ActiveProviderId = MetaHumanVivianProviderId;
            ProviderStatus = PhotorealReadyStatus;
            ProviderFailureCode = NAME_None;
            bPhotorealCharacterReady = true;
            UE_LOG(
                LogVistaCharacterProvider,
                Display,
                TEXT("VISTA_CHARACTER_PROVIDER_READY provider=%s"),
                *MetaHumanVivianProviderId.ToString());
            return true;
        }
    }

    if (IsValid(VisualActor))
    {
        VisualActor->SetActorHiddenInGame(true);
    }
    ProviderChildActorComponent->SetVisibility(false, true);
    SetPhotorealUnavailable(OwnerCharacter, FailureCode);
    return false;
}

bool UVistaCharacterProviderComponent::ValidateMetaHumanVisual(
    AActor& VisualActor,
    FName& OutFailureCode) const
{
    USkeletalMeshComponent* Body =
        FindNamedSkeletalMesh(VisualActor, BodyComponentName);
    if (!IsValid(Body) || !Body->IsRegistered() || !Body->IsVisible() ||
        !IsValid(Body->GetSkeletalMeshAsset()))
    {
        OutFailureCode = TEXT("character_provider_body_not_ready");
        return false;
    }

    USkeletalMeshComponent* Face =
        FindNamedSkeletalMesh(VisualActor, FaceComponentName);
    if (!IsValid(Face) || Face == Body || !Face->IsRegistered() ||
        !Face->IsVisible() ||
        !IsValid(Face->GetSkeletalMeshAsset()))
    {
        OutFailureCode = TEXT("character_provider_face_not_ready");
        return false;
    }

    if (!HasReadyGroomOrHairComponent(VisualActor))
    {
        OutFailureCode = TEXT("character_provider_groom_not_ready");
        return false;
    }

    if (!IsValid(Body->GetAnimInstance()) && !IsValid(Body->GetAnimClass()))
    {
        OutFailureCode = TEXT("character_provider_animation_not_ready");
        return false;
    }

    OutFailureCode = NAME_None;
    return true;
}

USkeletalMeshComponent* UVistaCharacterProviderComponent::FindNamedSkeletalMesh(
    AActor& VisualActor,
    FName ComponentName)
{
    TInlineComponentArray<USkeletalMeshComponent*> SkeletalMeshes;
    VisualActor.GetComponents(SkeletalMeshes);
    for (USkeletalMeshComponent* SkeletalMesh : SkeletalMeshes)
    {
        if (IsValid(SkeletalMesh) &&
            SkeletalMesh->GetFName() == ComponentName)
        {
            return SkeletalMesh;
        }
    }
    return nullptr;
}

bool UVistaCharacterProviderComponent::HasReadyGroomOrHairComponent(
    AActor& VisualActor)
{
    TInlineComponentArray<UActorComponent*> Components;
    VisualActor.GetComponents(Components);
    for (UActorComponent* Component : Components)
    {
        UPrimitiveComponent* VisualComponent = Cast<UPrimitiveComponent>(Component);
        if (!IsValid(VisualComponent) || !VisualComponent->IsRegistered() ||
            !VisualComponent->IsActive() || !VisualComponent->IsVisible())
        {
            continue;
        }
        const FString ClassName = Component->GetClass()->GetName();
        const FString ComponentName = Component->GetName();
        const bool bGroomOrHair =
            ClassName.Contains(TEXT("Groom"), ESearchCase::IgnoreCase) ||
            ClassName.Contains(TEXT("Hair"), ESearchCase::IgnoreCase) ||
            ComponentName.Contains(TEXT("Groom"), ESearchCase::IgnoreCase) ||
            ComponentName.Contains(TEXT("Hair"), ESearchCase::IgnoreCase);
        if (bGroomOrHair)
        {
            return true;
        }
    }
    return false;
}

void UVistaCharacterProviderComponent::DisableVisualCollision(AActor& VisualActor)
{
    TInlineComponentArray<UPrimitiveComponent*> VisualPrimitives;
    VisualActor.GetComponents(VisualPrimitives);
    for (UPrimitiveComponent* Primitive : VisualPrimitives)
    {
        if (IsValid(Primitive))
        {
            Primitive->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            Primitive->SetGenerateOverlapEvents(false);
        }
    }
}

void UVistaCharacterProviderComponent::SetMannyFallbackVisible(
    AVistaHomeNpcCharacter& OwnerCharacter,
    bool bVisible)
{
    if (USkeletalMeshComponent* MannyMesh = OwnerCharacter.GetMesh())
    {
        MannyMesh->SetVisibility(bVisible, true);
        MannyMesh->SetHiddenInGame(!bVisible, true);
    }
}

void UVistaCharacterProviderComponent::SetPhotorealUnavailable(
    AVistaHomeNpcCharacter& OwnerCharacter,
    FName FailureCode)
{
    SetMannyFallbackVisible(OwnerCharacter, true);
    ActiveProviderId = MannyProviderId;
    ProviderStatus = PhotorealUnavailableStatus;
    ProviderFailureCode = FailureCode.IsNone()
        ? FName(TEXT("character_provider_validation_failed"))
        : FailureCode;
    bPhotorealCharacterReady = false;
    UE_LOG(
        LogVistaCharacterProvider,
        Warning,
        TEXT("VISTA_CHARACTER_PROVIDER_UNAVAILABLE requested=%s code=%s; Manny remains active"),
        *MetaHumanVivianProviderId.ToString(),
        *ProviderFailureCode.ToString());
}
