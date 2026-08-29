#include "VistaCharacterProviderComponent.h"

#include "Animation/AnimInstance.h"
#include "Components/ChildActorComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/EngineBaseTypes.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "GameFramework/Pawn.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "RetargetAnimInstance.h"
#include "RetargetComponent.h"
#include "Retargeter/IKRetargeter.h"
#include "UObject/SoftObjectPtr.h"

DEFINE_LOG_CATEGORY_STATIC(LogVistaCharacterProvider, Log, All);

namespace
{
const FName MannyProviderId(TEXT("manny"));
const FName MetaHumanVivianProviderId(TEXT("metahuman_vivian_ue57_v1"));
const FName CitySampleCrowdVisualDemoProviderId(
    TEXT("citysample_crowd_visual_demo_v1"));
const FName MakeHumanCc0R8ProviderId(TEXT("makehuman_cc0_r8"));
const FName MannyActiveStatus(TEXT("manny_active"));
const FName MakeHumanCc0R8ActiveStatus(TEXT("makehuman_cc0_r8_active"));
const FName MakeHumanCc0R8UnavailableStatus(TEXT("makehuman_cc0_r8_unavailable"));
const FName PhotorealReadyStatus(TEXT("photoreal_character_ready"));
const FName PhotorealUnavailableStatus(TEXT("photoreal_character_unavailable"));
const FName CitySampleVisualDemoActiveUnverifiedStatus(
    TEXT("citysample_visual_demo_active_unverified"));
const FName CitySampleVisualDemoUnavailableStatus(
    TEXT("citysample_visual_demo_unavailable"));
const TCHAR* CharacterProviderCommandLineKey = TEXT("VistaCharacterProvider=");
const TCHAR* HumanOperatedVisualDemoCommandLineFlag =
    TEXT("VistaHumanOperatedVisualDemo");
const TCHAR* VistaWorldPortCommandLineKey = TEXT("VistaWorldPort=");

// These are the only external visual classes that the runtime may load. Their
// paths are compiled into the plugin; RequestedProviderId can never be
// interpreted as an object path.
const TCHAR* MetaHumanVivianClassPath =
    TEXT("/Game/VISTA/Characters/MetaHumans/Vivian_VISTA/"
         "BP_Vivian_VISTA.BP_Vivian_VISTA_C");
// This Epic/MetaHuman-backed class is licensed only for a human-operated,
// visual-only private demo. It must never become an agent, dataset/database
// record, or AI/VLM training, testing, evaluation, or review input.
const TCHAR* CitySampleCrowdVisualDemoClassPath =
    TEXT("/Game/CitySampleCrowd/Blueprints/"
         "BP_CrowdCharacter.BP_CrowdCharacter_C");
const TCHAR* MetaHumanRetargetAssetPath =
    TEXT("/Game/Characters/Mannequins/Rigs/"
         "RTG_Mannequin.RTG_Mannequin");

// Publicly redistributable CC0 lane.  These paths never reference Manny,
// MetaHuman, City Sample, Human_Avatar, or SimWorld animation content.
const TCHAR* MakeHumanCc0R6MeshPath =
    TEXT("/Game/VISTA/MakeHumanCC0/R6/"
         "SK_VISTA_CC0_Hero_R6.SK_VISTA_CC0_Hero_R6");
const TCHAR* MakeHumanCc0R6SkeletonPath =
    TEXT("/Game/VISTA/MakeHumanCC0/R6/"
         "SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton");
const TCHAR* MakeHumanCc0R8AnimBlueprintClassPath =
    TEXT("/Game/VISTA/MakeHumanCC0/R8/Animations/"
         "ABP_VistaCC0Hero_R8.ABP_VistaCC0Hero_R8_C");

const FName BodyComponentName(TEXT("Body"));
const FName FaceComponentName(TEXT("Face"));
}

UVistaCharacterProviderComponent::UVistaCharacterProviderComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
}

FName UVistaCharacterProviderComponent::GetMannyProviderId()
{
    return MannyProviderId;
}

FName UVistaCharacterProviderComponent::GetMetaHumanVivianProviderId()
{
    return MetaHumanVivianProviderId;
}

FName UVistaCharacterProviderComponent::GetCitySampleCrowdVisualDemoProviderId()
{
    return CitySampleCrowdVisualDemoProviderId;
}

FName UVistaCharacterProviderComponent::GetMakeHumanCc0R8ProviderId()
{
    return MakeHumanCc0R8ProviderId;
}

bool UVistaCharacterProviderComponent::IsMakeHumanCc0R8Active() const
{
    const ACharacter* OwnerCharacter = Cast<ACharacter>(GetOwner());
    FName FailureCode = NAME_None;
    return IsValid(OwnerCharacter) &&
        ActiveProviderId == MakeHumanCc0R8ProviderId &&
        ProviderStatus == MakeHumanCc0R8ActiveStatus &&
        ProviderFailureCode.IsNone() && !bPhotorealCharacterReady &&
        ValidateMakeHumanCc0R8(*OwnerCharacter, FailureCode) &&
        FailureCode.IsNone();
}

void UVistaCharacterProviderComponent::BeginPlay()
{
    Super::BeginPlay();

    ACharacter* OwnerCharacter = Cast<ACharacter>(GetOwner());
    if (!IsValid(OwnerCharacter))
    {
        ProviderStatus = PhotorealUnavailableStatus;
        ProviderFailureCode = TEXT("character_provider_owner_invalid");
        return;
    }

    // Manny is deliberately made visible first. Every failure path therefore
    // leaves the semantic character functional and visually inspectable.
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
    if (ProviderId == MakeHumanCc0R8ProviderId)
    {
        ActivateMakeHumanCc0R8(*OwnerCharacter);
        return;
    }
    if (ProviderId == MetaHumanVivianProviderId)
    {
        ActivateAllowlistedMetaHuman(*OwnerCharacter);
        return;
    }
    if (ProviderId == CitySampleCrowdVisualDemoProviderId)
    {
        ActivateAllowlistedCitySampleVisualDemo(*OwnerCharacter);
        return;
    }

    SetProviderUnavailable(
        *OwnerCharacter,
        ProviderId,
        TEXT("character_provider_not_allowlisted"));
}

bool UVistaCharacterProviderComponent::ActivateMakeHumanCc0R8(
    ACharacter& OwnerCharacter)
{
    USkeletalMeshComponent* MeshComponent = OwnerCharacter.GetMesh();
    if (!IsValid(MeshComponent))
    {
        SetProviderUnavailable(
            OwnerCharacter,
            MakeHumanCc0R8ProviderId,
            TEXT("makehuman_cc0_mesh_component_unavailable"));
        return false;
    }

    const TSoftObjectPtr<USkeletalMesh> MeshReference{
        FSoftObjectPath(MakeHumanCc0R6MeshPath)};
    USkeletalMesh* LoadedMesh = MeshReference.LoadSynchronous();
    const TSoftClassPtr<UAnimInstance> AnimClassReference{
        FSoftObjectPath(MakeHumanCc0R8AnimBlueprintClassPath)};
    UClass* LoadedAnimClass = AnimClassReference.LoadSynchronous();
    if (!IsValid(LoadedMesh) ||
        LoadedMesh->GetPathName() != MakeHumanCc0R6MeshPath ||
        !IsValid(LoadedAnimClass) ||
        !LoadedAnimClass->IsChildOf(UAnimInstance::StaticClass()) ||
        LoadedAnimClass->GetPathName() != MakeHumanCc0R8AnimBlueprintClassPath)
    {
        SetProviderUnavailable(
            OwnerCharacter,
            MakeHumanCc0R8ProviderId,
            TEXT("makehuman_cc0_runtime_assets_unavailable"));
        return false;
    }

    USkeletalMesh* OriginalMesh = MeshComponent->GetSkeletalMeshAsset();
    UClass* OriginalAnimClass = MeshComponent->GetAnimClass();
    const FVector OriginalRelativeLocation = MeshComponent->GetRelativeLocation();
    const FRotator OriginalRelativeRotation = MeshComponent->GetRelativeRotation();
    const ECollisionEnabled::Type OriginalCollision =
        MeshComponent->GetCollisionEnabled();
    const bool bOriginalOverlapEvents = MeshComponent->GetGenerateOverlapEvents();

    MeshComponent->SetSkeletalMesh(LoadedMesh, false);
    MeshComponent->SetAnimInstanceClass(LoadedAnimClass);
    MeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    MeshComponent->SetGenerateOverlapEvents(false);
    MeshComponent->SetVisibility(true, false);
    MeshComponent->SetHiddenInGame(false, false);
    MeshComponent->InitAnim(true);

    FName FailureCode = NAME_None;
    if (!ValidateMakeHumanCc0R8(OwnerCharacter, FailureCode))
    {
        MeshComponent->SetSkeletalMesh(OriginalMesh, false);
        MeshComponent->SetAnimInstanceClass(OriginalAnimClass);
        MeshComponent->SetRelativeLocation(OriginalRelativeLocation);
        MeshComponent->SetRelativeRotation(OriginalRelativeRotation);
        MeshComponent->SetCollisionEnabled(OriginalCollision);
        MeshComponent->SetGenerateOverlapEvents(bOriginalOverlapEvents);
        MeshComponent->InitAnim(true);
        SetProviderUnavailable(
            OwnerCharacter,
            MakeHumanCc0R8ProviderId,
            FailureCode);
        return false;
    }

    ActiveProviderId = MakeHumanCc0R8ProviderId;
    ProviderStatus = MakeHumanCc0R8ActiveStatus;
    ProviderFailureCode = NAME_None;
    bPhotorealCharacterReady = false;
    UE_LOG(
        LogVistaCharacterProvider,
        Display,
        TEXT("VISTA_CHARACTER_PROVIDER_READY provider=%s quality_claim=none"),
        *MakeHumanCc0R8ProviderId.ToString());
    return true;
}

bool UVistaCharacterProviderComponent::ValidateMakeHumanCc0R8(
    const ACharacter& OwnerCharacter,
    FName& OutFailureCode) const
{
    USkeletalMeshComponent* MeshComponent = OwnerCharacter.GetMesh();
    USkeletalMesh* Mesh = IsValid(MeshComponent)
        ? MeshComponent->GetSkeletalMeshAsset()
        : nullptr;
    if (!IsValid(MeshComponent) || !MeshComponent->IsRegistered() ||
        !IsValid(Mesh) || Mesh->GetPathName() != MakeHumanCc0R6MeshPath)
    {
        OutFailureCode = TEXT("makehuman_cc0_mesh_binding_invalid");
        return false;
    }
    if (!IsValid(Mesh->GetSkeleton()) ||
        Mesh->GetSkeleton()->GetPathName() != MakeHumanCc0R6SkeletonPath ||
        Mesh->GetRefSkeleton().GetNum() != 53 ||
        Mesh->GetRefSkeleton().GetBoneName(0) != FName(TEXT("root")) ||
        Mesh->GetRefSkeleton().FindBoneIndex(FName(TEXT("hand_r"))) == INDEX_NONE)
    {
        OutFailureCode = TEXT("makehuman_cc0_skeleton_contract_invalid");
        return false;
    }
    if (MeshComponent->GetAnimClass() == nullptr ||
        MeshComponent->GetAnimClass()->GetPathName() !=
            MakeHumanCc0R8AnimBlueprintClassPath ||
        !IsValid(MeshComponent->GetAnimInstance()))
    {
        OutFailureCode = TEXT("makehuman_cc0_anim_instance_invalid");
        return false;
    }
    if (MeshComponent->GetCollisionEnabled() != ECollisionEnabled::NoCollision ||
        MeshComponent->GetGenerateOverlapEvents() ||
        !IsValid(OwnerCharacter.GetCapsuleComponent()) ||
        OwnerCharacter.GetCapsuleComponent()->GetCollisionEnabled() ==
            ECollisionEnabled::NoCollision)
    {
        OutFailureCode = TEXT("makehuman_cc0_capsule_authority_invalid");
        return false;
    }
    OutFailureCode = NAME_None;
    return true;
}

bool UVistaCharacterProviderComponent::IsCitySampleHumanVisualDemoCommandLineAllowed(
    FName& OutFailureCode) const
{
    const FString CommandLine(FCommandLine::Get());
    if (CommandLine.Contains(
            VistaWorldPortCommandLineKey,
            ESearchCase::IgnoreCase))
    {
        OutFailureCode = TEXT("citysample_visual_demo_world_port_forbidden");
        return false;
    }

    if (!bAllowCommandLineProviderOverride ||
        !FParse::Param(
            FCommandLine::Get(),
            HumanOperatedVisualDemoCommandLineFlag))
    {
        OutFailureCode = TEXT("citysample_visual_demo_human_argv_required");
        return false;
    }

    FString ProviderValue;
    if (!FParse::Value(
            FCommandLine::Get(),
            CharacterProviderCommandLineKey,
            ProviderValue))
    {
        OutFailureCode = TEXT("citysample_visual_demo_provider_argv_required");
        return false;
    }
    ProviderValue.TrimStartAndEndInline();
    ProviderValue.ToLowerInline();
    if (FName(*ProviderValue) != CitySampleCrowdVisualDemoProviderId)
    {
        OutFailureCode = TEXT("citysample_visual_demo_provider_argv_mismatch");
        return false;
    }

    OutFailureCode = NAME_None;
    return true;
}

void UVistaCharacterProviderComponent::SetOwnerNoSeeForNearCamera(bool bHidden)
{
    bOwnerNoSeeForNearCamera = bHidden;
    ACharacter* OwnerCharacter = Cast<ACharacter>(GetOwner());
    if (IsValid(OwnerCharacter) && IsValid(OwnerCharacter->GetMesh()))
    {
        OwnerCharacter->GetMesh()->SetOwnerNoSee(bHidden);
    }

    if (!IsValid(ProviderChildActorComponent))
    {
        return;
    }
    AActor* VisualActor = ProviderChildActorComponent->GetChildActor();
    if (!IsValid(VisualActor))
    {
        return;
    }
    TInlineComponentArray<UPrimitiveComponent*> VisualPrimitives;
    VisualActor->GetComponents(VisualPrimitives);
    for (UPrimitiveComponent* Primitive : VisualPrimitives)
    {
        if (IsValid(Primitive))
        {
            Primitive->SetOwnerNoSee(bHidden);
        }
    }
}

FName UVistaCharacterProviderComponent::ResolveRequestedProviderId() const
{
    FString ProviderValue = RequestedProviderId.ToString();
    if (bAllowCommandLineProviderOverride)
    {
        FParse::Value(
            FCommandLine::Get(),
            CharacterProviderCommandLineKey,
            ProviderValue);
    }
    ProviderValue.TrimStartAndEndInline();
    ProviderValue.ToLowerInline();
    return ProviderValue.IsEmpty() ? MannyProviderId : FName(*ProviderValue);
}

bool UVistaCharacterProviderComponent::ActivateAllowlistedMetaHuman(
    ACharacter& OwnerCharacter)
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

    const TSoftObjectPtr<UIKRetargeter> RetargetAsset{
        FSoftObjectPath(MetaHumanRetargetAssetPath)};
    UIKRetargeter* LoadedRetargetAsset = RetargetAsset.LoadSynchronous();
    if (!IsValid(LoadedRetargetAsset))
    {
        SetPhotorealUnavailable(
            OwnerCharacter,
            TEXT("character_provider_retarget_asset_unavailable"));
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
        // OwnerNoSee resolves visibility through the AActor ownership chain,
        // not through UChildActorComponent::GetParentComponent(). Establish
        // that chain explicitly before applying the current camera state.
        VisualActor->SetOwner(&OwnerCharacter);
        if (VisualActor->GetOwner() != &OwnerCharacter)
        {
            FailureCode = TEXT("character_provider_visual_owner_invalid");
        }
        else
        {
            SetOwnerNoSeeForNearCamera(bOwnerNoSeeForNearCamera);

            // The assembled Blueprint is a visual shell. Canonical movement,
            // navigation and interaction collision stay on ACharacter.
            VisualActor->SetActorEnableCollision(false);
            VisualActor->SetCanBeDamaged(false);
            DisableVisualCollision(*VisualActor);
            if (ValidateMetaHumanVisualShell(*VisualActor, FailureCode) &&
                ConfigureMetaHumanRetarget(
                    OwnerCharacter,
                    *VisualActor,
                    *LoadedRetargetAsset,
                    FailureCode) &&
                ValidateMetaHumanVisual(*VisualActor, FailureCode))
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
    }

    if (IsValid(VisualActor))
    {
        VisualActor->SetActorHiddenInGame(true);
    }
    DestroyProviderRetargetComponent();
    DestroyProviderChildActorComponent();
    SetPhotorealUnavailable(OwnerCharacter, FailureCode);
    return false;
}

bool UVistaCharacterProviderComponent::ActivateAllowlistedCitySampleVisualDemo(
    ACharacter& OwnerCharacter)
{
    FName FailureCode = NAME_None;
    if (!IsCitySampleHumanVisualDemoCommandLineAllowed(FailureCode))
    {
        SetProviderUnavailable(
            OwnerCharacter,
            CitySampleCrowdVisualDemoProviderId,
            FailureCode);
        return false;
    }

    const TSoftClassPtr<ACharacter> ProviderClass{
        FSoftObjectPath(CitySampleCrowdVisualDemoClassPath)};
    UClass* LoadedProviderClass = ProviderClass.LoadSynchronous();
    if (!IsValid(LoadedProviderClass) ||
        !LoadedProviderClass->IsChildOf(ACharacter::StaticClass()))
    {
        SetProviderUnavailable(
            OwnerCharacter,
            CitySampleCrowdVisualDemoProviderId,
            TEXT("citysample_visual_demo_class_unavailable"));
        return false;
    }

    const TSoftObjectPtr<UIKRetargeter> RetargetAsset{
        FSoftObjectPath(MetaHumanRetargetAssetPath)};
    UIKRetargeter* LoadedRetargetAsset = RetargetAsset.LoadSynchronous();
    if (!IsValid(LoadedRetargetAsset))
    {
        SetProviderUnavailable(
            OwnerCharacter,
            CitySampleCrowdVisualDemoProviderId,
            TEXT("citysample_visual_demo_retarget_asset_unavailable"));
        return false;
    }

    ProviderChildActorComponent = NewObject<UChildActorComponent>(
        &OwnerCharacter,
        TEXT("VistaCitySampleVisualDemoChild"));
    if (!IsValid(ProviderChildActorComponent))
    {
        SetProviderUnavailable(
            OwnerCharacter,
            CitySampleCrowdVisualDemoProviderId,
            TEXT("citysample_visual_demo_child_component_unavailable"));
        return false;
    }

    OwnerCharacter.AddInstanceComponent(ProviderChildActorComponent);
    ProviderChildActorComponent->SetupAttachment(OwnerCharacter.GetRootComponent());
    ProviderChildActorComponent->SetRelativeLocation(FVector::ZeroVector);
    ProviderChildActorComponent->SetRelativeRotation(FRotator::ZeroRotator);
    ProviderChildActorComponent->SetChildActorClass(LoadedProviderClass);

    // UChildActorComponent defers FinishSpawning until after this customizer.
    // Strip all possession/AI intent before BP_CrowdCharacter can enter play;
    // NeutralizeCitySampleCharacter repeats and validates the shutdown after
    // Blueprint construction has completed.
    ProviderChildActorComponent->CreateChildActor(
        [](AActor* SpawnedVisualActor)
        {
            if (ACharacter* SpawnedVisualCharacter =
                    Cast<ACharacter>(SpawnedVisualActor))
            {
                SpawnedVisualCharacter->AutoPossessPlayer =
                    EAutoReceiveInput::Disabled;
                SpawnedVisualCharacter->AutoPossessAI = EAutoPossessAI::Disabled;
                SpawnedVisualCharacter->AIControllerClass = nullptr;
                SpawnedVisualCharacter->SetReplicates(false);
                SpawnedVisualCharacter->SetReplicateMovement(false);
                SpawnedVisualCharacter->SetActorTickEnabled(false);
                SpawnedVisualCharacter->SetActorEnableCollision(false);
                SpawnedVisualCharacter->SetCanBeDamaged(false);
            }
        });
    ProviderChildActorComponent->RegisterComponent();

    ACharacter* VisualCharacter = Cast<ACharacter>(
        ProviderChildActorComponent->GetChildActor());
    if (!IsValid(VisualCharacter) ||
        VisualCharacter->GetClass() != LoadedProviderClass ||
        !VisualCharacter->IsActorInitialized() ||
        VisualCharacter->IsActorBeingDestroyed())
    {
        FailureCode = TEXT("citysample_visual_demo_actor_unavailable");
    }
    else if (NeutralizeCitySampleCharacter(
                 OwnerCharacter,
                 *VisualCharacter,
                 FailureCode))
    {
        USkeletalMeshComponent* VisualBody = VisualCharacter->GetMesh();
        if (!IsValid(VisualBody) || !VisualBody->IsRegistered() ||
            !VisualBody->IsVisible() ||
            !IsValid(VisualBody->GetSkeletalMeshAsset()))
        {
            FailureCode = TEXT("citysample_visual_demo_body_not_ready");
        }
        else
        {
            // Discard the crowd Blueprint's pre-authored primary-body loop.
            // The possessed VISTA pawn's speed-aware Manny remains the sole
            // movement/animation authority and drives this visual through the
            // reviewed retarget bridge.
            VisualBody->SetAnimInstanceClass(nullptr);
            if (ConfigureMetaHumanRetarget(
                    OwnerCharacter,
                    *VisualCharacter,
                    *LoadedRetargetAsset,
                    FailureCode) &&
                ValidateCitySampleVisualDemo(
                    OwnerCharacter,
                    *VisualCharacter,
                    FailureCode))
            {
                SetOwnerNoSeeForNearCamera(bOwnerNoSeeForNearCamera);
                SetMannyFallbackVisible(OwnerCharacter, false);
                ActiveProviderId = CitySampleCrowdVisualDemoProviderId;
                ProviderStatus = CitySampleVisualDemoActiveUnverifiedStatus;
                ProviderFailureCode = NAME_None;

                // This provider is not a photoreal/GTA acceptance signal. Its
                // assets and pixels are excluded from every AI-facing VISTA
                // dataset, database, VLM review, training, test and evaluation.
                bPhotorealCharacterReady = false;
                UE_LOG(
                    LogVistaCharacterProvider,
                    Display,
                    TEXT("VISTA_CITYSAMPLE_VISUAL_DEMO_ACTIVE provider=%s "
                         "human_operated_only=true ai_vlm_data_use=forbidden "
                         "combined_runtime_proof=required photoreal_claim=false "
                         "gta_quality_claim=false"),
                    *CitySampleCrowdVisualDemoProviderId.ToString());
                return true;
            }
        }
    }

    if (IsValid(VisualCharacter))
    {
        VisualCharacter->SetActorHiddenInGame(true);
    }
    DestroyProviderRetargetComponent();
    DestroyProviderChildActorComponent();
    SetProviderUnavailable(
        OwnerCharacter,
        CitySampleCrowdVisualDemoProviderId,
        FailureCode);
    return false;
}

bool UVistaCharacterProviderComponent::NeutralizeCitySampleCharacter(
    ACharacter& OwnerCharacter,
    ACharacter& VisualCharacter,
    FName& OutFailureCode) const
{
    // BP_CrowdCharacter is an ACharacter, but it is permitted here only as a
    // sealed visual child. AVistaPlayableHomeCharacter keeps possession,
    // semantic identity, input, movement, collision and interaction authority.
    VisualCharacter.AutoPossessPlayer = EAutoReceiveInput::Disabled;
    VisualCharacter.AutoPossessAI = EAutoPossessAI::Disabled;
    VisualCharacter.AIControllerClass = nullptr;
    if (AController* VisualController = VisualCharacter.GetController())
    {
        VisualController->UnPossess();
        VisualController->SetActorTickEnabled(false);
        VisualController->Destroy();
    }
    if (VisualCharacter.GetController() != nullptr)
    {
        OutFailureCode = TEXT("citysample_visual_demo_controller_not_neutralized");
        return false;
    }

    VisualCharacter.SetReplicates(false);
    VisualCharacter.SetReplicateMovement(false);
    VisualCharacter.SetCanAffectNavigationGeneration(false);
    VisualCharacter.SetActorTickEnabled(false);
    VisualCharacter.SetCanBeDamaged(false);

    UCharacterMovementComponent* VisualMovement =
        VisualCharacter.GetCharacterMovement();
    if (!IsValid(VisualMovement))
    {
        OutFailureCode = TEXT("citysample_visual_demo_movement_unavailable");
        return false;
    }
    VisualMovement->StopMovementImmediately();
    VisualMovement->DisableMovement();
    VisualMovement->Deactivate();
    VisualMovement->SetComponentTickEnabled(false);

    VisualCharacter.SetActorEnableCollision(false);
    if (UCapsuleComponent* VisualCapsule = VisualCharacter.GetCapsuleComponent())
    {
        VisualCapsule->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        VisualCapsule->SetGenerateOverlapEvents(false);
    }
    DisableVisualCollision(VisualCharacter);

    if (!IsValid(ProviderChildActorComponent) ||
        !IsValid(VisualCharacter.GetRootComponent()))
    {
        OutFailureCode = TEXT("citysample_visual_demo_attachment_unavailable");
        return false;
    }
    if (VisualCharacter.GetRootComponent()->GetAttachParent() !=
        ProviderChildActorComponent)
    {
        const bool bAttached = VisualCharacter.AttachToComponent(
            ProviderChildActorComponent,
            FAttachmentTransformRules::SnapToTargetNotIncludingScale);
        if (!bAttached)
        {
            OutFailureCode = TEXT("citysample_visual_demo_attachment_failed");
            return false;
        }
    }
    VisualCharacter.SetOwner(&OwnerCharacter);
    if (VisualCharacter.GetOwner() != &OwnerCharacter ||
        VisualCharacter.GetAttachParentActor() != &OwnerCharacter)
    {
        OutFailureCode = TEXT("citysample_visual_demo_owner_invalid");
        return false;
    }

    OutFailureCode = NAME_None;
    return true;
}

bool UVistaCharacterProviderComponent::ValidateCitySampleVisualDemo(
    ACharacter& OwnerCharacter,
    ACharacter& VisualCharacter,
    FName& OutFailureCode) const
{
    if (VisualCharacter.GetOwner() != &OwnerCharacter ||
        VisualCharacter.GetAttachParentActor() != &OwnerCharacter ||
        VisualCharacter.GetController() != nullptr ||
        VisualCharacter.AutoPossessPlayer != EAutoReceiveInput::Disabled ||
        VisualCharacter.AutoPossessAI != EAutoPossessAI::Disabled ||
        VisualCharacter.AIControllerClass != nullptr)
    {
        OutFailureCode = TEXT("citysample_visual_demo_not_pure_visual");
        return false;
    }

    UCharacterMovementComponent* VisualMovement =
        VisualCharacter.GetCharacterMovement();
    if (!IsValid(VisualMovement) || VisualMovement->IsActive() ||
        VisualMovement->IsComponentTickEnabled())
    {
        OutFailureCode = TEXT("citysample_visual_demo_movement_not_disabled");
        return false;
    }

    const UCapsuleComponent* VisualCapsule = VisualCharacter.GetCapsuleComponent();
    if (VisualCharacter.GetActorEnableCollision() ||
        !IsValid(VisualCapsule) ||
        VisualCapsule->GetCollisionEnabled() != ECollisionEnabled::NoCollision)
    {
        OutFailureCode = TEXT("citysample_visual_demo_collision_not_disabled");
        return false;
    }
    TInlineComponentArray<UPrimitiveComponent*> VisualPrimitives;
    VisualCharacter.GetComponents(VisualPrimitives);
    for (const UPrimitiveComponent* Primitive : VisualPrimitives)
    {
        if (!IsValid(Primitive) ||
            Primitive->GetCollisionEnabled() != ECollisionEnabled::NoCollision ||
            Primitive->GetGenerateOverlapEvents())
        {
            OutFailureCode = TEXT("citysample_visual_demo_primitive_not_visual_only");
            return false;
        }
    }

    USkeletalMeshComponent* Body = VisualCharacter.GetMesh();
    if (!IsValid(Body) || !Body->IsRegistered() || !Body->IsVisible() ||
        !IsValid(Body->GetSkeletalMeshAsset()) ||
        !IsValid(Cast<URetargetAnimInstance>(Body->GetAnimInstance())) ||
        !IsValid(ProviderRetargetComponent) ||
        !ProviderRetargetComponent->IsRegistered() ||
        ProviderRetargetComponent->ControlledSkeletalMeshComponent.OverrideComponent.Get() !=
            Body ||
        !IsValid(ProviderRetargetComponent->RetargetAsset))
    {
        OutFailureCode = TEXT("citysample_visual_demo_retarget_not_ready");
        return false;
    }

    OutFailureCode = NAME_None;
    return true;
}

bool UVistaCharacterProviderComponent::ValidateMetaHumanVisualShell(
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

    OutFailureCode = NAME_None;
    return true;
}

bool UVistaCharacterProviderComponent::ConfigureMetaHumanRetarget(
    ACharacter& OwnerCharacter,
    AActor& VisualActor,
    UIKRetargeter& RetargetAsset,
    FName& OutFailureCode)
{
    USkeletalMeshComponent* SourceManny = OwnerCharacter.GetMesh();
    if (!IsValid(SourceManny) || !SourceManny->IsRegistered() ||
        !IsValid(SourceManny->GetSkeletalMeshAsset()) ||
        (!IsValid(SourceManny->GetAnimInstance()) &&
         !IsValid(SourceManny->GetAnimClass())))
    {
        OutFailureCode = TEXT("character_provider_source_animation_not_ready");
        return false;
    }

    USkeletalMeshComponent* Body = nullptr;
    if (ACharacter* VisualCharacter = Cast<ACharacter>(&VisualActor))
    {
        Body = VisualCharacter->GetMesh();
    }
    else
    {
        Body = FindNamedSkeletalMesh(VisualActor, BodyComponentName);
    }
    if (!IsValid(Body))
    {
        OutFailureCode = TEXT("character_provider_body_not_ready");
        return false;
    }

    // URetargetComponent::OnRegister clears its source override. Register first,
    // then wire the external Manny source exactly as Epic's MetaHuman editor
    // actor does after registration.
    ProviderRetargetComponent = NewObject<URetargetComponent>(
        &VisualActor,
        TEXT("VistaMetaHumanRetarget"));
    if (!IsValid(ProviderRetargetComponent))
    {
        OutFailureCode = TEXT("character_provider_retarget_component_unavailable");
        return false;
    }
    VisualActor.AddInstanceComponent(ProviderRetargetComponent);
    ProviderRetargetComponent->RegisterComponent();
    if (!ProviderRetargetComponent->IsRegistered())
    {
        OutFailureCode = TEXT("character_provider_retarget_component_unavailable");
        DestroyProviderRetargetComponent();
        return false;
    }

    // Call this before source/controlled assignment. With both assigned, Epic's
    // false branch resets the Face and clothing animation state we must retain.
    ProviderRetargetComponent->SetForceOtherMeshesToFollowControlledMesh(false);
    ProviderRetargetComponent->SetSourcePerformerMesh(SourceManny);
    ProviderRetargetComponent->SetControlledMesh(Body);
    ProviderRetargetComponent->SetRetargetAsset(&RetargetAsset);
    if (ProviderRetargetComponent->SourceSkeletalMeshComponent.OverrideComponent.Get() !=
            SourceManny ||
        ProviderRetargetComponent->ControlledSkeletalMeshComponent.OverrideComponent.Get() !=
            Body ||
        ProviderRetargetComponent->RetargetAsset != &RetargetAsset)
    {
        OutFailureCode = TEXT("character_provider_retarget_binding_failed");
        DestroyProviderRetargetComponent();
        return false;
    }
    ProviderRetargetComponent->InitiateAnimation();

    const bool bSourceTicksBeforeBody =
        Body->PrimaryComponentTick.GetPrerequisites().ContainsByPredicate(
            [SourceManny](const FTickPrerequisite& Prerequisite)
            {
                return Prerequisite.PrerequisiteObject.Get() == SourceManny &&
                    Prerequisite.Get() == &SourceManny->PrimaryComponentTick;
            });
    if (!bSourceTicksBeforeBody)
    {
        OutFailureCode = TEXT("character_provider_retarget_tick_order_invalid");
        DestroyProviderRetargetComponent();
        return false;
    }

    // Manny remains the animation authority after becoming visually hidden.
    // Its mesh never participates in gameplay collision; the character capsule
    // remains the sole authoritative collider.
    SourceManny->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    SourceManny->SetGenerateOverlapEvents(false);
    SourceManny->SetComponentTickEnabled(true);
    SourceManny->VisibilityBasedAnimTickOption =
        EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    OutFailureCode = NAME_None;
    return true;
}

bool UVistaCharacterProviderComponent::ValidateMetaHumanVisual(
    AActor& VisualActor,
    FName& OutFailureCode) const
{
    if (!ValidateMetaHumanVisualShell(VisualActor, OutFailureCode))
    {
        return false;
    }

    USkeletalMeshComponent* Body =
        FindNamedSkeletalMesh(VisualActor, BodyComponentName);
    if (!IsValid(Body->GetAnimInstance()) && !IsValid(Body->GetAnimClass()))
    {
        OutFailureCode = TEXT("character_provider_animation_not_ready");
        return false;
    }

    if (!IsValid(ProviderRetargetComponent) ||
        !ProviderRetargetComponent->IsRegistered() ||
        ProviderRetargetComponent->bForceOtherMeshesToFollowControlledMesh ||
        !IsValid(ProviderRetargetComponent->RetargetAsset) ||
        !IsValid(Cast<URetargetAnimInstance>(Body->GetAnimInstance())))
    {
        OutFailureCode = TEXT("character_provider_retarget_not_ready");
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
    ACharacter& OwnerCharacter,
    bool bVisible)
{
    if (USkeletalMeshComponent* MannyMesh = OwnerCharacter.GetMesh())
    {
        // The Manny mesh is the hidden retarget source. Do not propagate
        // visibility to attached camera, carry, or interaction components.
        MannyMesh->SetVisibility(bVisible, false);
        MannyMesh->SetHiddenInGame(!bVisible, false);
    }
}

void UVistaCharacterProviderComponent::DestroyProviderRetargetComponent()
{
    if (IsValid(ProviderRetargetComponent))
    {
        // UE 5.7 narrows URetargetComponent::DestroyComponent to protected,
        // while UActorComponent keeps the virtual lifecycle entry point public.
        // Dispatch through the public base so Epic's retarget cleanup override
        // still runs before the instance component is removed and collected.
        UActorComponent* RetargetComponentToDestroy =
            ProviderRetargetComponent.Get();
        RetargetComponentToDestroy->DestroyComponent();
    }
    ProviderRetargetComponent = nullptr;
}

void UVistaCharacterProviderComponent::DestroyProviderChildActorComponent()
{
    if (IsValid(ProviderChildActorComponent))
    {
        // A rejected MetaHuman shell is expensive even while hidden: Face,
        // Groom and clothing components can continue ticking. Tear down both
        // the spawned actor and its dynamic component on every failure path.
        ProviderChildActorComponent->DestroyChildActor();
        ProviderChildActorComponent->DestroyComponent();
    }
    ProviderChildActorComponent = nullptr;
}

void UVistaCharacterProviderComponent::SetPhotorealUnavailable(
    ACharacter& OwnerCharacter,
    FName FailureCode)
{
    SetProviderUnavailable(
        OwnerCharacter,
        MetaHumanVivianProviderId,
        FailureCode);
}

void UVistaCharacterProviderComponent::SetProviderUnavailable(
    ACharacter& OwnerCharacter,
    FName RequestedProvider,
    FName FailureCode)
{
    SetMannyFallbackVisible(OwnerCharacter, true);
    ActiveProviderId = MannyProviderId;
    if (RequestedProvider == CitySampleCrowdVisualDemoProviderId)
    {
        ProviderStatus = CitySampleVisualDemoUnavailableStatus;
    }
    else if (RequestedProvider == MakeHumanCc0R8ProviderId)
    {
        ProviderStatus = MakeHumanCc0R8UnavailableStatus;
    }
    else
    {
        ProviderStatus = PhotorealUnavailableStatus;
    }
    ProviderFailureCode = FailureCode.IsNone()
        ? FName(TEXT("character_provider_validation_failed"))
        : FailureCode;
    bPhotorealCharacterReady = false;
    UE_LOG(
        LogVistaCharacterProvider,
        Warning,
        TEXT("VISTA_CHARACTER_PROVIDER_UNAVAILABLE requested=%s code=%s; "
             "Manny remains active and authoritative"),
        *RequestedProvider.ToString(),
        *ProviderFailureCode.ToString());
}
