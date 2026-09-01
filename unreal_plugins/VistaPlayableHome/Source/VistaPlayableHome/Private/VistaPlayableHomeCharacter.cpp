#include "VistaPlayableHomeCharacter.h"

// Modified in VISTA-World on 2026-08-22: report direct placement interactions.

#include "Animation/AnimInstance.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputActionValue.h"
#include "InputMappingContext.h"
#include "InputCoreTypes.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "UObject/ConstructorHelpers.h"
#include "Net/UnrealNetwork.h"
#include "VistaAnimationComponent.h"
#include "VistaActionExecutorComponent.h"
#include "VistaCharacterProviderComponent.h"
#include "VistaEventSubsystem.h"
#include "VistaIndoorSpringArmComponent.h"
#include "VistaInteractable.h"
#include "VistaInteractionComponent.h"
#include "VistaLiquidReceiverActor.h"
#include "VistaPickupActor.h"
#include "VistaPlayableHomeRuntimeSubsystem.h"
#include "VistaPostureComponent.h"
#include "VistaSeatActor.h"
#include "VistaStatefulApplianceActor.h"

DEFINE_LOG_CATEGORY_STATIC(LogVistaPlayableHomeCamera, Log, All);

namespace
{
const FName RealisticInteriorR2CameraProfileId(TEXT("realistic_interior_r2"));
const TCHAR* CameraProfileCommandLineKey = TEXT("VistaCameraProfile=");
constexpr float IndoorViewPitchMinDegrees = -60.0f;
constexpr float IndoorViewPitchMaxDegrees = 45.0f;
constexpr float FirstPersonEyeHeightCm = 64.0f;
constexpr double InspectionMaximumSeconds = 20.0;
constexpr float InspectionMaximumDistanceCm = 500.0f;
constexpr double TerminalFeedbackSeconds = 4.0;
constexpr int32 MaximumPresentationTextCharacters = 128;

/** Stable cycle order; changing target state may remove entries, never reorder them. */
constexpr EVistaAffordance PlayerActionOrder[] = {
    EVistaAffordance::Press,
    EVistaAffordance::TurnOn,
    EVistaAffordance::TurnOff,
    EVistaAffordance::Open,
    EVistaAffordance::Close,
    EVistaAffordance::Inspect,
    EVistaAffordance::Sit,
    EVistaAffordance::Stand,
    EVistaAffordance::Pour,
    EVistaAffordance::PickUp,
    EVistaAffordance::Place,
};

bool ReadExactRuntimeBoolean(
    const FVistaEntityRuntimeState& State,
    const FName Key,
    bool& OutValue)
{
    const FString* Value = State.Values.Find(Key);
    if (Value == nullptr)
    {
        return false;
    }
    if (Value->Equals(TEXT("true"), ESearchCase::CaseSensitive))
    {
        OutValue = true;
        return true;
    }
    if (Value->Equals(TEXT("false"), ESearchCase::CaseSensitive))
    {
        OutValue = false;
        return true;
    }
    return false;
}

bool PlayerActionAnimationType(
    const EVistaAffordance Affordance,
    EVistaNpcActionType& OutType)
{
    switch (Affordance)
    {
    case EVistaAffordance::Press:
        OutType = EVistaNpcActionType::Press;
        return true;
    case EVistaAffordance::TurnOn:
        OutType = EVistaNpcActionType::TurnOn;
        return true;
    case EVistaAffordance::TurnOff:
        OutType = EVistaNpcActionType::TurnOff;
        return true;
    case EVistaAffordance::Open:
        OutType = EVistaNpcActionType::OpenDoor;
        return true;
    case EVistaAffordance::Close:
        OutType = EVistaNpcActionType::CloseDoor;
        return true;
    case EVistaAffordance::Inspect:
        OutType = EVistaNpcActionType::Inspect;
        return true;
    case EVistaAffordance::Sit:
        OutType = EVistaNpcActionType::Sit;
        return true;
    case EVistaAffordance::Stand:
        OutType = EVistaNpcActionType::StandUp;
        return true;
    case EVistaAffordance::Pour:
        OutType = EVistaNpcActionType::Pour;
        return true;
    case EVistaAffordance::PickUp:
        OutType = EVistaNpcActionType::PickUp;
        return true;
    case EVistaAffordance::Place:
        OutType = EVistaNpcActionType::Place;
        return true;
    default:
        return false;
    }
}

bool HasApprovedPlayerActionAnimation(
    const UVistaAnimationComponent* Animation,
    const EVistaAffordance Affordance,
    const AActor* Target,
    const AActor* SecondaryTarget)
{
    if (!IsValid(Animation))
    {
        return false;
    }
    EVistaNpcActionType AnimationType = EVistaNpcActionType::Inspect;
    if (!PlayerActionAnimationType(Affordance, AnimationType))
    {
        return false;
    }
    FName ReadinessCode;
    if (Affordance == EVistaAffordance::PickUp ||
        Affordance == EVistaAffordance::Place)
    {
        return Animation->HasApprovedMutationAnimation(
            AnimationType,
            ReadinessCode);
    }
    const AActor* AnimationTarget = Affordance == EVistaAffordance::Pour
        ? SecondaryTarget
        : Target;
    return IsValid(AnimationTarget) &&
        Animation->HasApprovedMutationAnimation(
            AnimationType,
            AnimationTarget,
            ReadinessCode);
}

FString BoundedPresentationText(const FString& Source, int32 MaximumCharacters)
{
    FString Result;
    Result.Reserve(FMath::Min(Source.Len(), MaximumCharacters));
    bool bPreviousWasSpace = false;
    for (const TCHAR Character : Source)
    {
        const bool bSpace = FChar::IsWhitespace(Character);
        if (bSpace)
        {
            if (!bPreviousWasSpace && !Result.IsEmpty())
            {
                Result.AppendChar(TEXT(' '));
            }
            bPreviousWasSpace = true;
        }
        else if (!FChar::IsControl(Character))
        {
            Result.AppendChar(Character);
            bPreviousWasSpace = false;
        }
        if (Result.Len() >= MaximumCharacters)
        {
            break;
        }
    }
    Result.TrimStartAndEndInline();
    return Result;
}

FVistaInspectionPresentation BuildInspectionPresentation(
    AActor* Target,
    const FVistaEntityRuntimeState& State)
{
    FVistaInspectionPresentation Presentation;
    Presentation.bActive = true;
    Presentation.SemanticId = BoundedPresentationText(
        State.SemanticId,
        MaximumPresentationTextCharacters);
    Presentation.Affordances =
        IVistaInteractable::Execute_VistaGetAffordances(Target);
    Presentation.Affordances.Sort(
        [](EVistaAffordance Left, EVistaAffordance Right)
        {
            return static_cast<uint8>(Left) < static_cast<uint8>(Right);
        });

    // Only this closed set may cross into the public inspection card. Values
    // such as private event conditions, review labels and arbitrary actor
    // metadata are intentionally excluded.
    static const FName PublicValueKeys[] = {
        TEXT("open"),
        TEXT("active"),
        TEXT("powered"),
        TEXT("on"),
        TEXT("held"),
        TEXT("placed_at"),
    };
    for (const FName Key : PublicValueKeys)
    {
        if (const FString* Value = State.Values.Find(Key))
        {
            FVistaInspectionStateRow Row;
            Row.Key = Key;
            Row.Value = BoundedPresentationText(*Value, 64);
            Presentation.PublicState.Add(MoveTemp(Row));
        }
    }
    FVistaInspectionStateRow PortableRow;
    PortableRow.Key = TEXT("portable");
    PortableRow.Value = State.bPortable ? TEXT("true") : TEXT("false");
    Presentation.PublicState.Add(MoveTemp(PortableRow));
    FVistaInspectionStateRow VisibleRow;
    VisibleRow.Key = TEXT("visible");
    VisibleRow.Value = State.bHidden ? TEXT("false") : TEXT("true");
    Presentation.PublicState.Add(MoveTemp(VisibleRow));
    Presentation.PublicState.Sort(
        [](const FVistaInspectionStateRow& Left,
           const FVistaInspectionStateRow& Right)
        {
            return Left.Key.ToString() < Right.Key.ToString();
        });
    return Presentation;
}
}

FVistaIndoorCameraProfile FVistaIndoorCameraProfile::RealisticInteriorR2()
{
    FVistaIndoorCameraProfile Profile;
    Profile.ProfileId = RealisticInteriorR2CameraProfileId;
    Profile.TargetBoomLengthCm = 220.0f;
    Profile.FieldOfViewDegrees = 80.0f;
    Profile.SocketOffsetCm = FVector(0.0f, 45.0f, 62.0f);
    Profile.CollisionProbeSizeCm = 18.0f;
    Profile.CameraLagSpeed = 14.0f;
    Profile.CameraLagMaxDistanceCm = 30.0f;
    Profile.CollisionRecoverySpeed = 8.0f;
    Profile.RecoverySnapThresholdCm = 1.0f;
    Profile.NearCameraHideDistanceCm = 82.0f;
    Profile.NearCameraShowDistanceCm = 108.0f;
    Profile.bEnableCameraCollision = true;
    Profile.bEnableCameraLag = true;
    Profile.bEnableCameraLagSubstepping = true;
    return Profile;
}

bool FVistaIndoorCameraProfile::IsValid(FString& OutReason) const
{
    OutReason.Reset();
    const bool bFinite =
        FMath::IsFinite(TargetBoomLengthCm) &&
        FMath::IsFinite(FieldOfViewDegrees) &&
        !SocketOffsetCm.ContainsNaN() &&
        FMath::IsFinite(CollisionProbeSizeCm) &&
        FMath::IsFinite(CameraLagSpeed) &&
        FMath::IsFinite(CameraLagMaxDistanceCm) &&
        FMath::IsFinite(CollisionRecoverySpeed) &&
        FMath::IsFinite(RecoverySnapThresholdCm) &&
        FMath::IsFinite(NearCameraHideDistanceCm) &&
        FMath::IsFinite(NearCameraShowDistanceCm);
    if (!bFinite)
    {
        OutReason = TEXT("non_finite_setting");
        return false;
    }
    if (ProfileId != RealisticInteriorR2CameraProfileId)
    {
        OutReason = TEXT("unknown_profile_id");
        return false;
    }
    if (TargetBoomLengthCm < 180.0f || TargetBoomLengthCm > 240.0f)
    {
        OutReason = TEXT("target_boom_out_of_range");
        return false;
    }
    if (FieldOfViewDegrees < 75.0f || FieldOfViewDegrees > 85.0f)
    {
        OutReason = TEXT("field_of_view_out_of_range");
        return false;
    }
    if (!FMath::IsNearlyZero(SocketOffsetCm.X) ||
        FMath::Abs(SocketOffsetCm.Y) > 65.0f ||
        SocketOffsetCm.Z < 45.0f || SocketOffsetCm.Z > 80.0f)
    {
        OutReason = TEXT("socket_offset_out_of_range");
        return false;
    }
    if (CollisionProbeSizeCm < 12.0f || CollisionProbeSizeCm > 24.0f ||
        CameraLagSpeed < 8.0f || CameraLagSpeed > 30.0f ||
        CameraLagMaxDistanceCm < 0.0f || CameraLagMaxDistanceCm > 50.0f ||
        CollisionRecoverySpeed < 4.0f || CollisionRecoverySpeed > 20.0f ||
        RecoverySnapThresholdCm < 0.1f || RecoverySnapThresholdCm > 5.0f ||
        NearCameraHideDistanceCm < 60.0f || NearCameraHideDistanceCm > 100.0f ||
        NearCameraShowDistanceCm < 90.0f || NearCameraShowDistanceCm > 140.0f ||
        NearCameraShowDistanceCm - NearCameraHideDistanceCm < 15.0f)
    {
        OutReason = TEXT("collision_or_lag_setting_out_of_range");
        return false;
    }
    if (!bEnableCameraCollision || !bEnableCameraLag ||
        !bEnableCameraLagSubstepping)
    {
        OutReason = TEXT("required_safety_feature_disabled");
        return false;
    }
    return true;
}

AVistaPlayableHomeCharacter::AVistaPlayableHomeCharacter()
{
    bReplicates = true;
    // Match the authored 34 cm navigation-agent radius. A 100 cm doorway then
    // retains 32 cm of total lateral clearance while the 96 cm half-height stays fixed.
    GetCapsuleComponent()->InitCapsuleSize(34.0f, 96.0f);
    bUseControllerRotationPitch = false;
    bUseControllerRotationYaw = false;
    bUseControllerRotationRoll = false;

    UCharacterMovementComponent* Movement = GetCharacterMovement();
    Movement->bOrientRotationToMovement = true;
    Movement->RotationRate = FRotator(0.0f, 540.0f, 0.0f);
    Movement->MaxWalkSpeed = WalkSpeed;
    Movement->GetNavAgentPropertiesRef().bCanCrouch = true;

    // These are optional project assets: source still compiles when content is
    // absent, while the known prebuilt VISTA project gets a visible Manny pawn.
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

    CameraBoom = CreateDefaultSubobject<UVistaIndoorSpringArmComponent>(TEXT("CameraBoom"));
    CameraBoom->SetupAttachment(RootComponent);
    CameraBoom->TargetArmLength = 320.0f;
    CameraBoom->SocketOffset = FVector(0.0f, 55.0f, 65.0f);
    CameraBoom->bUsePawnControlRotation = true;
    CameraBoom->bEnableCameraLag = true;
    CameraBoom->CameraLagSpeed = 12.0f;

    FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
    FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
    FollowCamera->bUsePawnControlRotation = false;

    FirstPersonCamera =
        CreateDefaultSubobject<UCameraComponent>(TEXT("FirstPersonCamera"));
    FirstPersonCamera->SetupAttachment(GetCapsuleComponent());
    FirstPersonCamera->SetRelativeLocation(
        FVector(0.0f, 0.0f, FirstPersonEyeHeightCm));
    FirstPersonCamera->bUsePawnControlRotation = true;
    FirstPersonCamera->SetAutoActivate(false);
    FirstPersonCamera->SetActive(false);

    CarryAnchor = CreateDefaultSubobject<USceneComponent>(TEXT("VistaCarryAnchor"));
    CarryAnchor->SetupAttachment(GetMesh(), TEXT("hand_r"));
    CarryAnchor->SetRelativeTransform(FTransform::Identity);
    CarryAnchor->ComponentTags.Add(TEXT("VistaCarryAnchor"));
    CarryAnchor->ComponentTags.Add(TEXT("VistaValidatedCarryAnchor"));

    InteractionComponent = CreateDefaultSubobject<UVistaInteractionComponent>(TEXT("InteractionComponent"));
    AnimationComponent =
        CreateDefaultSubobject<UVistaAnimationComponent>(TEXT("VistaAnimationComponent"));
    ActionExecutorComponent =
        CreateDefaultSubobject<UVistaActionExecutorComponent>(
            TEXT("VistaActionExecutorComponent"));
    PostureComponent =
        CreateDefaultSubobject<UVistaPostureComponent>(TEXT("VistaPostureComponent"));
    CharacterProviderComponent =
        CreateDefaultSubobject<UVistaCharacterProviderComponent>(
            TEXT("VistaCharacterProviderComponent"));
    CharacterProviderComponent->RequestedProviderId =
        UVistaCharacterProviderComponent::GetMetaHumanVivianProviderId();
    CharacterProviderComponent->bAllowCommandLineProviderOverride = true;
}

void AVistaPlayableHomeCharacter::BeginPlay()
{
    Super::BeginPlay();
    GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
    if (!SemanticId.IsEmpty())
    {
        Tags.AddUnique(FName(*SemanticId));
    }
    if (IsValid(PostureComponent))
    {
        PostureComponent->OccupantSemanticId = SemanticId;
    }

    ApplyRequestedCameraProfile();
    ConfigureIndoorViewLimits();
    FName CarryAnchorCode;
    if (!IsValid(UVistaActionExecutorComponent::PrepareCarryAnchor(
            this, CarryAnchorCode)))
    {
        UE_LOG(
            LogVistaPlayableHomeCamera,
            Error,
            TEXT("VISTA_CARRY_ANCHOR_REJECTED code=%s"),
            *CarryAnchorCode.ToString());
    }

    const APlayerController* PlayerController = Cast<APlayerController>(Controller);
    if (IsValid(PlayerController) && IsValid(DefaultMappingContext))
    {
        if (ULocalPlayer* LocalPlayer = PlayerController->GetLocalPlayer())
        {
            if (UEnhancedInputLocalPlayerSubsystem* Subsystem =
                    LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
            {
                Subsystem->AddMappingContext(DefaultMappingContext, 0);
            }
        }
    }
}

void AVistaPlayableHomeCharacter::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (HasAuthority())
    {
        UpdatePendingActionFeedback();
    }
    const UWorld* World = GetWorld();
    if (!IsValid(World) ||
        World->GetTimeSeconds() >= NextPlayerActionRefreshAtSeconds)
    {
        RefreshPlayerActionSelection();
    }
    if (!InspectionPresentation.bActive || !IsLocallyControlled())
    {
        return;
    }

    UWorld* InspectionWorld = GetWorld();
    AActor* Target = InspectedTarget.Get();
    if (!IsValid(InspectionWorld) || !IsValid(Target))
    {
        const FString LostSemanticId = InspectionPresentation.SemanticId;
        ExitInspection();
        PublishInteractionResult(
            FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("INSPECTION_TARGET_LOST"),
                LostSemanticId));
        return;
    }
    if (InspectionWorld->GetTimeSeconds() - InspectionStartedAtSeconds >=
        InspectionMaximumSeconds)
    {
        const FString TimedOutSemanticId = InspectionPresentation.SemanticId;
        ExitInspection();
        PublishInteractionResult(
            FVistaInteractionResult::Failure(
                EVistaInteractionStatus::TimedOut,
                TEXT("INSPECTION_TIMED_OUT"),
                TimedOutSemanticId));
        return;
    }
    if (FVector::Distance(GetActorLocation(), Target->GetActorLocation()) >
        InspectionMaximumDistanceCm)
    {
        const FString DistantSemanticId = InspectionPresentation.SemanticId;
        ExitInspection();
        PublishInteractionResult(
            FVistaInteractionResult::Failure(
                EVistaInteractionStatus::Blocked,
                TEXT("INSPECTION_RANGE_EXCEEDED"),
                DistantSemanticId));
        return;
    }
    UpdateInspectionFocus();
}

void AVistaPlayableHomeCharacter::CalcCamera(
    float DeltaTime,
    FMinimalViewInfo& OutResult)
{
    Super::CalcCamera(DeltaTime, OutResult);
    // CalcCamera runs after the PostPhysics spring-arm update and supplies the
    // exact view used for this frame. Sampling FollowCamera from the actor's
    // default PrePhysics tick would lag a new wall collision by one frame.
    UpdateNearCameraVisualOcclusion(OutResult.Location);
}

void AVistaPlayableHomeCharacter::UpdateNearCameraVisualOcclusion(
    const FVector& CameraLocation)
{
    if (bFirstPersonViewEnabled && IsLocallyControlled())
    {
        SetNearCameraVisualHidden(true);
        return;
    }
    if (ActiveCameraProfileId != RealisticInteriorR2CameraProfileId ||
        !IsLocallyControlled() || !IsValid(CameraBoom) || !IsValid(FollowCamera))
    {
        RestoreNearCameraVisualOcclusion();
        return;
    }

    const FVector ArmOrigin =
        CameraBoom->GetComponentLocation() + CameraBoom->TargetOffset;
    const float CameraDistanceCm =
        FVector::Distance(ArmOrigin, CameraLocation);
    if (!bNearCameraVisualHidden &&
        CameraDistanceCm <= NearCameraHideDistanceCm)
    {
        SetNearCameraVisualHidden(true);
    }
    else if (bNearCameraVisualHidden &&
             CameraDistanceCm >= NearCameraShowDistanceCm)
    {
        SetNearCameraVisualHidden(false);
    }
}

void AVistaPlayableHomeCharacter::SetNearCameraVisualHidden(bool bHidden)
{
    if (bNearCameraVisualHidden == bHidden)
    {
        return;
    }
    bNearCameraVisualHidden = bHidden;
    if (IsValid(GetMesh()))
    {
        GetMesh()->SetOwnerNoSee(bHidden);
    }
    if (IsValid(CharacterProviderComponent))
    {
        CharacterProviderComponent->SetOwnerNoSeeForNearCamera(bHidden);
    }
}

void AVistaPlayableHomeCharacter::RestoreNearCameraVisualOcclusion()
{
    SetNearCameraVisualHidden(false);
}

void AVistaPlayableHomeCharacter::ConfigureIndoorViewLimits()
{
    if (ActiveCameraProfileId != RealisticInteriorR2CameraProfileId)
    {
        return;
    }
    APlayerController* PlayerController = Cast<APlayerController>(Controller);
    if (!IsValid(PlayerController) || !IsValid(PlayerController->PlayerCameraManager))
    {
        UE_LOG(
            LogVistaPlayableHomeCamera,
            Warning,
            TEXT("VISTA_CAMERA_VIEW_LIMITS_DEFERRED player camera manager unavailable"));
        return;
    }
    APlayerCameraManager* CameraManager = PlayerController->PlayerCameraManager;
    if (bIndoorViewLimitsApplied && IndoorViewCameraManager.Get() != CameraManager)
    {
        RestoreIndoorViewLimits();
    }
    if (!bIndoorViewLimitsApplied)
    {
        IndoorViewCameraManager = CameraManager;
        PreviousViewPitchMin = CameraManager->ViewPitchMin;
        PreviousViewPitchMax = CameraManager->ViewPitchMax;
        PreviousViewRollMin = CameraManager->ViewRollMin;
        PreviousViewRollMax = CameraManager->ViewRollMax;
        bIndoorViewLimitsApplied = true;
    }
    CameraManager->ViewPitchMin = IndoorViewPitchMinDegrees;
    CameraManager->ViewPitchMax = IndoorViewPitchMaxDegrees;
    CameraManager->ViewRollMin = 0.0f;
    CameraManager->ViewRollMax = 0.0f;
}

void AVistaPlayableHomeCharacter::RestoreIndoorViewLimits()
{
    if (!bIndoorViewLimitsApplied)
    {
        return;
    }
    APlayerCameraManager* CameraManager = IndoorViewCameraManager.Get();
    if (IsValid(CameraManager))
    {
        CameraManager->ViewPitchMin = PreviousViewPitchMin;
        CameraManager->ViewPitchMax = PreviousViewPitchMax;
        CameraManager->ViewRollMin = PreviousViewRollMin;
        CameraManager->ViewRollMax = PreviousViewRollMax;
    }
    IndoorViewCameraManager.Reset();
    bIndoorViewLimitsApplied = false;
}

void AVistaPlayableHomeCharacter::ApplyRequestedCameraProfile()
{
    FString RequestedProfileId;
    if (!FParse::Value(
            FCommandLine::Get(),
            CameraProfileCommandLineKey,
            RequestedProfileId))
    {
        // No r2 selection means the accepted r1 camera remains untouched.
        return;
    }
    RequestedProfileId.TrimStartAndEndInline();
    if (!RequestedProfileId.Equals(
            RealisticInteriorR2CameraProfileId.ToString(),
            ESearchCase::CaseSensitive))
    {
        UE_LOG(
            LogVistaPlayableHomeCamera,
            Error,
            TEXT("VISTA_CAMERA_PROFILE_REJECTED unknown profile '%s'; keeping legacy_r1"),
            *RequestedProfileId);
        return;
    }

    if (!ApplyIndoorCameraProfile(FVistaIndoorCameraProfile::RealisticInteriorR2()))
    {
        UE_LOG(
            LogVistaPlayableHomeCamera,
            Error,
            TEXT("VISTA_CAMERA_PROFILE_REJECTED invalid realistic_interior_r2 profile; keeping legacy_r1"));
    }
}

bool AVistaPlayableHomeCharacter::ApplyIndoorCameraProfile(
    const FVistaIndoorCameraProfile& Profile)
{
    FString ValidationReason;
    if (!Profile.IsValid(ValidationReason))
    {
        UE_LOG(
            LogVistaPlayableHomeCamera,
            Error,
            TEXT("VISTA_CAMERA_PROFILE_REJECTED %s; camera settings unchanged"),
            *ValidationReason);
        return false;
    }

    UVistaIndoorSpringArmComponent* IndoorBoom =
        Cast<UVistaIndoorSpringArmComponent>(CameraBoom);
    if (!IsValid(IndoorBoom) || !IsValid(FollowCamera))
    {
        UE_LOG(
            LogVistaPlayableHomeCamera,
            Error,
            TEXT("VISTA_CAMERA_PROFILE_REJECTED required camera components missing"));
        return false;
    }

    // Validation completes before the first mutation, so malformed settings
    // cannot leave the pawn in a partially-applied camera state.
    IndoorBoom->TargetArmLength = Profile.TargetBoomLengthCm;
    IndoorBoom->SocketOffset = Profile.SocketOffsetCm;
    IndoorBoom->bDoCollisionTest = Profile.bEnableCameraCollision;
    IndoorBoom->ProbeSize = Profile.CollisionProbeSizeCm;
    IndoorBoom->ProbeChannel = ECC_Camera;
    IndoorBoom->bEnableCameraLag = Profile.bEnableCameraLag;
    IndoorBoom->CameraLagSpeed = Profile.CameraLagSpeed;
    IndoorBoom->CameraLagMaxDistance = Profile.CameraLagMaxDistanceCm;
    IndoorBoom->bUseCameraLagSubstepping = Profile.bEnableCameraLagSubstepping;
    IndoorBoom->CameraLagMaxTimeStep = 1.0f / 60.0f;
    IndoorBoom->ConfigureIndoorCollisionRecovery(
        Profile.bEnableCameraCollision,
        Profile.CollisionRecoverySpeed,
        Profile.RecoverySnapThresholdCm);
    NearCameraHideDistanceCm = Profile.NearCameraHideDistanceCm;
    NearCameraShowDistanceCm = Profile.NearCameraShowDistanceCm;
    FollowCamera->SetFieldOfView(Profile.FieldOfViewDegrees);
    ActiveCameraProfileId = Profile.ProfileId;
    ConfigureIndoorViewLimits();

    UE_LOG(
        LogVistaPlayableHomeCamera,
        Display,
        TEXT("VISTA_CAMERA_PROFILE_ACTIVE id=%s boom_cm=%.1f fov_deg=%.1f"),
        *ActiveCameraProfileId.ToString(),
        IndoorBoom->TargetArmLength,
        FollowCamera->FieldOfView);
    return true;
}

bool AVistaPlayableHomeCharacter::SetFirstPersonViewEnabled(bool bEnabled)
{
    if (bEnabled == bFirstPersonViewEnabled)
    {
        return true;
    }
    if (!IsLocallyControlled() || !IsValid(FollowCamera) ||
        !IsValid(FirstPersonCamera))
    {
        UE_LOG(
            LogVistaPlayableHomeCamera,
            Warning,
            TEXT("VISTA_CAMERA_VIEW_REJECTED owner-local camera unavailable"));
        return false;
    }

    if (!bEnabled)
    {
        RestoreCameraPresentation();
        return true;
    }

    // The third-person boom, socket and FollowCamera properties are never
    // mutated. Only active presentation components and owner-only visibility
    // are switched, then restored from this exact local snapshot.
    bFollowCameraWasActive = FollowCamera->IsActive();
    bFirstPersonCameraWasActive = FirstPersonCamera->IsActive();
    bVisualWasHiddenBeforeFirstPerson = bNearCameraVisualHidden;
    bCameraPresentationSnapshotValid = true;
    FollowCamera->Deactivate();
    FirstPersonCamera->Activate(true);
    bFirstPersonViewEnabled = true;
    SetNearCameraVisualHidden(true);

    UE_LOG(
        LogVistaPlayableHomeCamera,
        Display,
        TEXT("VISTA_CAMERA_VIEW_ACTIVE mode=first_person key=V"));
    return true;
}

void AVistaPlayableHomeCharacter::ToggleCameraView()
{
    SetFirstPersonViewEnabled(!bFirstPersonViewEnabled);
}

void AVistaPlayableHomeCharacter::RestoreCameraPresentation()
{
    if (!bCameraPresentationSnapshotValid)
    {
        bFirstPersonViewEnabled = false;
        return;
    }

    bFirstPersonViewEnabled = false;
    if (IsValid(FirstPersonCamera))
    {
        FirstPersonCamera->SetActive(bFirstPersonCameraWasActive, true);
    }
    if (IsValid(FollowCamera))
    {
        FollowCamera->SetActive(bFollowCameraWasActive, true);
    }
    SetNearCameraVisualHidden(bVisualWasHiddenBeforeFirstPerson);
    bCameraPresentationSnapshotValid = false;

    UE_LOG(
        LogVistaPlayableHomeCamera,
        Display,
        TEXT("VISTA_CAMERA_VIEW_ACTIVE mode=third_person key=V"));
}

void AVistaPlayableHomeCharacter::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    ExitInspection();
    RestoreCameraPresentation();
    RestoreNearCameraVisualOcclusion();
    RestoreIndoorViewLimits();
    SetSprinting(false);
    UnCrouch();
    if (HasAuthority() && IsValid(ActionExecutorComponent))
    {
        ActionExecutorComponent->CancelActiveAction(TEXT("PLAYER_END_PLAY"));
    }
    PendingInspectionTarget.Reset();
    PendingPresentationCommandId = NAME_None;
    if (HasAuthority() && IsValid(HeldItem))
    {
        HeldItem->ReleaseFromCarrier();
    }
    Super::EndPlay(EndPlayReason);
}

void AVistaPlayableHomeCharacter::UnPossessed()
{
    // Restore the shared camera manager before APawn clears Controller. This
    // also covers ordinary controller switches where the pawn stays alive and
    // EndPlay is never called.
    ExitInspection();
    if (HasAuthority())
    {
        CancelPendingAnimatedInspection(TEXT("PLAYER_UNPOSSESSED"));
    }
    PendingInspectionTarget.Reset();
    PendingPresentationCommandId = NAME_None;
    RestoreCameraPresentation();
    RestoreIndoorViewLimits();
    RestoreNearCameraVisualOcclusion();
    Super::UnPossessed();
}

void AVistaPlayableHomeCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
    Super::SetupPlayerInputComponent(PlayerInputComponent);
    ConfigureIndoorViewLimits();

    if (UEnhancedInputComponent* Enhanced = Cast<UEnhancedInputComponent>(PlayerInputComponent))
    {
        if (IsValid(MoveAction))
        {
            Enhanced->BindAction(MoveAction, ETriggerEvent::Triggered, this, &ThisClass::Move);
        }
        if (IsValid(LookAction))
        {
            Enhanced->BindAction(LookAction, ETriggerEvent::Triggered, this, &ThisClass::Look);
        }
        if (IsValid(JumpAction))
        {
            Enhanced->BindAction(JumpAction, ETriggerEvent::Started, this, &ACharacter::Jump);
            Enhanced->BindAction(JumpAction, ETriggerEvent::Completed, this, &ACharacter::StopJumping);
        }
        if (IsValid(SprintAction))
        {
            Enhanced->BindAction(SprintAction, ETriggerEvent::Started, this, &ThisClass::BeginSprint);
            Enhanced->BindAction(SprintAction, ETriggerEvent::Completed, this, &ThisClass::EndSprint);
            Enhanced->BindAction(SprintAction, ETriggerEvent::Canceled, this, &ThisClass::EndSprint);
        }
        if (IsValid(CrouchAction))
        {
            Enhanced->BindAction(CrouchAction, ETriggerEvent::Started, this, &ThisClass::BeginCrouch);
            Enhanced->BindAction(CrouchAction, ETriggerEvent::Completed, this, &ThisClass::EndCrouch);
            Enhanced->BindAction(CrouchAction, ETriggerEvent::Canceled, this, &ThisClass::EndCrouch);
        }
        if (IsValid(InteractAction))
        {
            Enhanced->BindAction(InteractAction, ETriggerEvent::Started, this, &ThisClass::InteractPressed);
        }
        if (IsValid(DropAction))
        {
            Enhanced->BindAction(DropAction, ETriggerEvent::Started, this, &ThisClass::DropPressed);
        }
        if (IsValid(InspectAction))
        {
            Enhanced->BindAction(
                InspectAction,
                ETriggerEvent::Started,
                this,
                &ThisClass::InspectPressed);
        }
        if (IsValid(ExitInspectAction))
        {
            Enhanced->BindAction(
                ExitInspectAction,
                ETriggerEvent::Started,
                this,
                &ThisClass::ExitInspectPressed);
        }
    }

    // Legacy bindings keep the C++ pawn usable in a disposable project before
    // Enhanced Input assets are assigned. The project may define either set.
    PlayerInputComponent->BindAxis(TEXT("MoveForward"), this, &ThisClass::MoveForwardLegacy);
    PlayerInputComponent->BindAxis(TEXT("MoveRight"), this, &ThisClass::MoveRightLegacy);
    PlayerInputComponent->BindAxis(TEXT("Turn"), this, &ThisClass::LookYawLegacy);
    PlayerInputComponent->BindAxis(TEXT("LookUp"), this, &ThisClass::LookPitchLegacy);
    PlayerInputComponent->BindAction(TEXT("Jump"), IE_Pressed, this, &ACharacter::Jump);
    PlayerInputComponent->BindAction(TEXT("Jump"), IE_Released, this, &ACharacter::StopJumping);
    PlayerInputComponent->BindAction(TEXT("Sprint"), IE_Pressed, this, &ThisClass::BeginSprint);
    PlayerInputComponent->BindAction(TEXT("Sprint"), IE_Released, this, &ThisClass::EndSprint);
    PlayerInputComponent->BindAction(TEXT("Crouch"), IE_Pressed, this, &ThisClass::BeginCrouch);
    PlayerInputComponent->BindAction(TEXT("Crouch"), IE_Released, this, &ThisClass::EndCrouch);
    PlayerInputComponent->BindAction(TEXT("Interact"), IE_Pressed, this, &ThisClass::InteractPressed);
    PlayerInputComponent->BindAction(TEXT("Drop"), IE_Pressed, this, &ThisClass::DropPressed);
    PlayerInputComponent->BindAction(TEXT("Inspect"), IE_Pressed, this, &ThisClass::InspectPressed);
    PlayerInputComponent->BindAction(TEXT("ExitInspect"), IE_Pressed, this, &ThisClass::ExitInspectPressed);

    // Direct keys keep the selector usable in generated projects without new
    // input assets. Existing E/Q/I bindings remain untouched.
    PlayerInputComponent->BindKey(
        EKeys::R, IE_Pressed, this, &ThisClass::CyclePlayerActionNextPressed);
    PlayerInputComponent->BindKey(
        EKeys::MouseScrollDown,
        IE_Pressed,
        this,
        &ThisClass::CyclePlayerActionNextPressed);
    PlayerInputComponent->BindKey(
        EKeys::MouseScrollUp,
        IE_Pressed,
        this,
        &ThisClass::CyclePlayerActionPreviousPressed);
    PlayerInputComponent->BindKey(
        EKeys::F,
        IE_Pressed,
        this,
        &ThisClass::ExecuteSelectedPlayerActionPressed);
    PlayerInputComponent->BindKey(
        EKeys::V,
        IE_Pressed,
        this,
        &ThisClass::ToggleCameraViewPressed);
}

void AVistaPlayableHomeCharacter::Move(const FInputActionValue& Value)
{
    if (InspectionPresentation.bActive || !HasStandingControlAuthority())
    {
        return;
    }
    const FVector2D MovementVector = Value.Get<FVector2D>();
    const FRotator ControlRotation = Controller ? Controller->GetControlRotation() : FRotator::ZeroRotator;
    const FRotator YawRotation(0.0f, ControlRotation.Yaw, 0.0f);
    AddMovementInput(FRotationMatrix(YawRotation).GetUnitAxis(EAxis::Y), MovementVector.X);
    AddMovementInput(FRotationMatrix(YawRotation).GetUnitAxis(EAxis::X), MovementVector.Y);
}

void AVistaPlayableHomeCharacter::Look(const FInputActionValue& Value)
{
    if (InspectionPresentation.bActive)
    {
        return;
    }
    const FVector2D LookAxis = Value.Get<FVector2D>();
    AddControllerYawInput(LookAxis.X);
    AddControllerPitchInput(LookAxis.Y);
}

void AVistaPlayableHomeCharacter::MoveForwardLegacy(float Value)
{
    if (!InspectionPresentation.bActive &&
        HasStandingControlAuthority() &&
        Controller &&
        !FMath::IsNearlyZero(Value))
    {
        const FRotator Yaw(0.0f, Controller->GetControlRotation().Yaw, 0.0f);
        AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), Value);
    }
}

void AVistaPlayableHomeCharacter::MoveRightLegacy(float Value)
{
    if (!InspectionPresentation.bActive &&
        HasStandingControlAuthority() &&
        Controller &&
        !FMath::IsNearlyZero(Value))
    {
        const FRotator Yaw(0.0f, Controller->GetControlRotation().Yaw, 0.0f);
        AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), Value);
    }
}

void AVistaPlayableHomeCharacter::LookYawLegacy(float Value)
{
    if (!InspectionPresentation.bActive)
    {
        AddControllerYawInput(Value);
    }
}

void AVistaPlayableHomeCharacter::LookPitchLegacy(float Value)
{
    if (!InspectionPresentation.bActive)
    {
        AddControllerPitchInput(Value);
    }
}

void AVistaPlayableHomeCharacter::ToggleCameraViewPressed()
{
    ToggleCameraView();
}

void AVistaPlayableHomeCharacter::SetSprinting(bool bEnabled)
{
    bSprinting = bEnabled && HasStandingControlAuthority();
    GetCharacterMovement()->MaxWalkSpeed = bSprinting ? SprintSpeed : WalkSpeed;
}

void AVistaPlayableHomeCharacter::BeginSprint()
{
    if (InspectionPresentation.bActive || !HasStandingControlAuthority())
    {
        return;
    }
    SetSprinting(true);
    if (!HasAuthority())
    {
        ServerSetSprinting(true);
    }
}

void AVistaPlayableHomeCharacter::EndSprint()
{
    SetSprinting(false);
    if (!HasAuthority())
    {
        ServerSetSprinting(false);
    }
}

void AVistaPlayableHomeCharacter::ServerSetSprinting_Implementation(bool bEnabled)
{
    SetSprinting(bEnabled && HasStandingControlAuthority());
}

void AVistaPlayableHomeCharacter::BeginCrouch()
{
    if (!InspectionPresentation.bActive && HasStandingControlAuthority())
    {
        Crouch();
    }
}
void AVistaPlayableHomeCharacter::EndCrouch()
{
    UnCrouch();
}

bool AVistaPlayableHomeCharacter::HasStandingControlAuthority() const
{
    return !IsValid(PostureComponent) || PostureComponent->GetPostureState() == EVistaPostureState::Standing;
}

bool AVistaPlayableHomeCharacter::CanCrouch() const
{
    return HasStandingControlAuthority() && Super::CanCrouch();
}

bool AVistaPlayableHomeCharacter::CanJumpInternal_Implementation() const
{
    return HasStandingControlAuthority() && Super::CanJumpInternal_Implementation();
}

void AVistaPlayableHomeCharacter::InteractPressed()
{
    if (InspectionPresentation.bActive)
    {
        PublishInteractionResult(
            FVistaInteractionResult::Failure(
                EVistaInteractionStatus::Busy,
                TEXT("INSPECTION_ACTIVE"),
                InspectionPresentation.SemanticId));
        return;
    }
    if (HasAuthority())
    {
        const FVistaInteractionResult Result = PerformDefaultInteraction();
        if (Result.Code == FName(TEXT("ACTION_ACCEPTED")) &&
            !PendingPresentationCommandId.IsNone())
        {
            UpdatePendingActionFeedback();
        }
        else
        {
            PublishInteractionResult(Result);
        }
    }
    else
    {
        ServerPerformDefaultInteraction();
    }
}

void AVistaPlayableHomeCharacter::DropPressed()
{
    if (InspectionPresentation.bActive)
    {
        PublishInteractionResult(
            FVistaInteractionResult::Failure(
                EVistaInteractionStatus::Busy,
                TEXT("INSPECTION_ACTIVE"),
                InspectionPresentation.SemanticId));
        return;
    }
    if (HasAuthority())
    {
        const FVistaInteractionResult Result = DropHeldItem();
        if (Result.Code == FName(TEXT("ACTION_ACCEPTED")) &&
            !PendingPresentationCommandId.IsNone())
        {
            UpdatePendingActionFeedback();
        }
        else
        {
            PublishInteractionResult(Result);
        }
    }
    else
    {
        ServerDropHeldItem();
    }
}

void AVistaPlayableHomeCharacter::InspectPressed()
{
    if (InspectionPresentation.bActive)
    {
        ExitInspection();
        return;
    }
    if (HasAuthority())
    {
        const FVistaInteractionResult Result = PerformInspectInteraction();
        if (Result.Code == FName(TEXT("ACTION_ACCEPTED")) &&
            !PendingPresentationCommandId.IsNone())
        {
            UpdatePendingActionFeedback();
        }
        else
        {
            PublishInteractionResult(Result);
        }
    }
    else
    {
        ServerPerformInspectInteraction();
    }
}

void AVistaPlayableHomeCharacter::ExitInspectPressed()
{
    if (InspectionPresentation.bActive)
    {
        ExitInspection();
        return;
    }
    if (HasAuthority())
    {
        CancelPendingAnimatedInspection(TEXT("PLAYER_INSPECT_CANCELED"));
    }
    else
    {
        ServerCancelPendingInspection();
    }
}

void AVistaPlayableHomeCharacter::CyclePlayerActionNextPressed()
{
    CyclePlayerAction(1);
}

void AVistaPlayableHomeCharacter::CyclePlayerActionPreviousPressed()
{
    CyclePlayerAction(-1);
}

void AVistaPlayableHomeCharacter::CyclePlayerAction(const int32 Direction)
{
    if (InspectionPresentation.bActive || Direction == 0)
    {
        return;
    }
    RefreshPlayerActionSelection();
    if (ExecutablePlayerActions.Num() < 2)
    {
        return;
    }
    SelectedPlayerActionIndex =
        (SelectedPlayerActionIndex + Direction) % ExecutablePlayerActions.Num();
    if (SelectedPlayerActionIndex < 0)
    {
        SelectedPlayerActionIndex += ExecutablePlayerActions.Num();
    }
}

void AVistaPlayableHomeCharacter::ExecuteSelectedPlayerActionPressed()
{
    if (InspectionPresentation.bActive)
    {
        PublishInteractionResult(
            FVistaInteractionResult::Failure(
                EVistaInteractionStatus::Busy,
                TEXT("INSPECTION_ACTIVE"),
                InspectionPresentation.SemanticId));
        return;
    }

    RefreshPlayerActionSelection();
    FVistaPlayerActionOption Action;
    if (!GetSelectedPlayerAction(Action))
    {
        PublishInteractionResult(
            FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("NO_EXECUTABLE_PLAYER_ACTION")));
        return;
    }
    if (HasAuthority())
    {
        PresentStartedPlayerAction(PerformPlayerAction(Action));
    }
    else
    {
        ServerPerformSelectedPlayerAction(
            Action.Affordance,
            Action.Target,
            Action.SecondaryTarget);
    }
}

void AVistaPlayableHomeCharacter::PresentStartedPlayerAction(
    const FVistaInteractionResult& Result)
{
    if (Result.Code == FName(TEXT("ACTION_ACCEPTED")) &&
        !PendingPresentationCommandId.IsNone())
    {
        UpdatePendingActionFeedback();
    }
    else
    {
        PublishInteractionResult(Result);
    }
}

void AVistaPlayableHomeCharacter::ServerPerformDefaultInteraction_Implementation()
{
    const FVistaInteractionResult Result = PerformDefaultInteraction();
    if (Result.Code == FName(TEXT("ACTION_ACCEPTED")) &&
        !PendingPresentationCommandId.IsNone())
    {
        UpdatePendingActionFeedback();
    }
    else
    {
        PublishInteractionResult(Result);
    }
}

void AVistaPlayableHomeCharacter::ServerDropHeldItem_Implementation()
{
    const FVistaInteractionResult Result = DropHeldItem();
    if (Result.Code == FName(TEXT("ACTION_ACCEPTED")) &&
        !PendingPresentationCommandId.IsNone())
    {
        UpdatePendingActionFeedback();
    }
    else
    {
        PublishInteractionResult(Result);
    }
}

void AVistaPlayableHomeCharacter::ServerPerformInspectInteraction_Implementation()
{
    const FVistaInteractionResult Result = PerformInspectInteraction();
    if (Result.Code == FName(TEXT("ACTION_ACCEPTED")) &&
        !PendingPresentationCommandId.IsNone())
    {
        UpdatePendingActionFeedback();
    }
    else
    {
        PublishInteractionResult(Result);
    }
}

void AVistaPlayableHomeCharacter::ServerCancelPendingInspection_Implementation()
{
    CancelPendingAnimatedInspection(TEXT("PLAYER_INSPECT_CANCELED"));
}

void AVistaPlayableHomeCharacter::ServerPerformSelectedPlayerAction_Implementation(
    const EVistaAffordance Affordance,
    AActor* Target,
    AActor* SecondaryTarget)
{
    PresentStartedPlayerAction(
        PerformRequestedPlayerAction(Affordance, Target, SecondaryTarget));
}

void AVistaPlayableHomeCharacter::ClientBeginInspectionPresentation_Implementation(
    AActor* Target,
    const FVistaInspectionPresentation& Presentation)
{
    if (!IsValid(Target) || !Presentation.bActive)
    {
        PublishInteractionResult(
            FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("INSPECTION_TARGET_UNAVAILABLE"),
                Presentation.SemanticId));
        return;
    }
    BeginInspectionPresentation(Target, Presentation);
}

void AVistaPlayableHomeCharacter::ClientPresentInteractionFeedback_Implementation(
    const FVistaPlayerActionFeedback& Feedback)
{
    SetActionFeedbackLocal(Feedback);
}

bool AVistaPlayableHomeCharacter::CanInspectFocusedActor() const
{
    const AActor* Target = IsValid(InteractionComponent)
        ? InteractionComponent->GetFocusedActor()
        : nullptr;
    if (!IsValid(Target) ||
        !Target->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        return false;
    }
    return IVistaInteractable::Execute_VistaGetAffordances(
        const_cast<AActor*>(Target)).Contains(EVistaAffordance::Inspect);
}

TArray<FVistaPlayerActionOption>
AVistaPlayableHomeCharacter::BuildExecutablePlayerActions() const
{
    TArray<FVistaPlayerActionOption> Options;
    if (InspectionPresentation.bActive ||
        !PendingPresentationCommandId.IsNone() ||
        (IsValid(ActionExecutorComponent) &&
         ActionExecutorComponent->HasActiveAction()))
    {
        return Options;
    }

    const EVistaPostureState PostureState = IsValid(PostureComponent)
        ? PostureComponent->GetPostureState()
        : EVistaPostureState::Standing;
    if (PostureState != EVistaPostureState::Standing)
    {
        if (PostureState == EVistaPostureState::Seated &&
            IsValid(PostureComponent))
        {
            AVistaSeatActor* ActiveSeat = PostureComponent->GetActiveSeat();
            if (IsValid(ActiveSeat) && !ActiveSeat->IsReserved() &&
                ActiveSeat->IsOccupiedBy(this, SemanticId) &&
                IVistaInteractable::Execute_VistaGetAffordances(ActiveSeat)
                    .Contains(EVistaAffordance::Stand) &&
                HasApprovedPlayerActionAnimation(
                    AnimationComponent,
                    EVistaAffordance::Stand,
                    ActiveSeat,
                    nullptr))
            {
                FVistaPlayerActionOption Stand;
                Stand.Affordance = EVistaAffordance::Stand;
                Stand.Target = ActiveSeat;
                Options.Add(Stand);
            }
        }
        return Options;
    }

    AActor* FocusedTarget = IsValid(InteractionComponent)
        ? InteractionComponent->GetFocusedActor()
        : nullptr;
    if (!IsValid(FocusedTarget) ||
        !FocusedTarget->GetClass()->ImplementsInterface(
            UVistaInteractable::StaticClass()))
    {
        return Options;
    }

    const TArray<EVistaAffordance> TargetAffordances =
        IVistaInteractable::Execute_VistaGetAffordances(FocusedTarget);
    const FVistaEntityRuntimeState TargetState =
        IVistaInteractable::Execute_VistaGetRuntimeState(FocusedTarget);
    if (TargetState.SemanticId.IsEmpty() ||
        TargetState.Transform.ContainsNaN())
    {
        return Options;
    }
    AVistaStatefulApplianceActor* Appliance =
        Cast<AVistaStatefulApplianceActor>(FocusedTarget);
    AVistaSeatActor* Seat = Cast<AVistaSeatActor>(FocusedTarget);
    AVistaPickupActor* FocusedPickup = Cast<AVistaPickupActor>(FocusedTarget);
    AVistaLiquidReceiverActor* Receiver =
        Cast<AVistaLiquidReceiverActor>(FocusedTarget);
    AVistaPickupActor* Held = IsValid(HeldItem) ? HeldItem.Get() : nullptr;

    bool bOpen = false;
    const bool bHasOpenState =
        ReadExactRuntimeBoolean(TargetState, TEXT("open"), bOpen);

    FVistaApplianceState ApplianceBefore;
    if (IsValid(Appliance))
    {
        ApplianceBefore.bPowered = Appliance->IsPowered();
        ApplianceBefore.bActive = Appliance->IsActive();
        ApplianceBefore.Status = Appliance->GetApplianceStatus();
    }

    for (const EVistaAffordance Affordance : PlayerActionOrder)
    {
        bool bExecutable = false;
        AActor* ActionTarget = FocusedTarget;
        AActor* SecondaryTarget = nullptr;
        switch (Affordance)
        {
        case EVistaAffordance::Press:
        case EVistaAffordance::TurnOn:
        case EVistaAffordance::TurnOff:
            if (IsValid(Appliance) && TargetAffordances.Contains(Affordance))
            {
                const bool bStateAllowsAction =
                    Affordance == EVistaAffordance::Press
                        ? ApplianceBefore.bPowered
                        : Affordance == EVistaAffordance::TurnOn
                            ? ApplianceBefore.bPowered &&
                                !ApplianceBefore.bActive
                            : ApplianceBefore.bActive;
                FVistaApplianceState PlannedState;
                bool bWouldMutate = false;
                FName PlanCode;
                bExecutable = bStateAllowsAction &&
                    AVistaStatefulApplianceActor::PlanInteractionTransition(
                        ApplianceBefore,
                        Affordance,
                        Appliance->ActivityProfile,
                        Appliance->PressProfile,
                        PlannedState,
                        bWouldMutate,
                        PlanCode) &&
                    (Affordance == EVistaAffordance::Press || bWouldMutate);
            }
            break;
        case EVistaAffordance::Open:
            bExecutable = TargetAffordances.Contains(Affordance) &&
                bHasOpenState && !bOpen;
            break;
        case EVistaAffordance::Close:
            bExecutable = TargetAffordances.Contains(Affordance) &&
                bHasOpenState && bOpen;
            break;
        case EVistaAffordance::Inspect:
            bExecutable = TargetAffordances.Contains(Affordance);
            break;
        case EVistaAffordance::Sit:
            bExecutable = IsValid(Seat) &&
                TargetAffordances.Contains(Affordance) &&
                !Seat->IsOccupied() && !Seat->IsReserved();
            break;
        case EVistaAffordance::Stand:
            // Stable seated posture is handled before focused-target actions.
            bExecutable = false;
            break;
        case EVistaAffordance::Pour:
            if (IsValid(Held) && Held != FocusedTarget &&
                IsValid(Receiver) && !Receiver->IsReserved() &&
                Held->GetCarrier() == this &&
                Held->GetPhysicalDisposition() ==
                    EVistaPickupDisposition::Held &&
                IVistaInteractable::Execute_VistaGetAffordances(Held)
                    .Contains(EVistaAffordance::Pour) &&
                TargetAffordances.Contains(EVistaAffordance::Pour))
            {
                FVistaLiquidStateSnapshot SourceAfter;
                FVistaLiquidStateSnapshot ReceiverAfter;
                float TransferMilliliters = 0.0f;
                FName PlanCode;
                bExecutable = AVistaLiquidReceiverActor::PlanPourTransition(
                    Held->GetLiquidState(),
                    Receiver->GetLiquidState(),
                    Receiver->AcceptedLiquidType,
                    SourceAfter,
                    ReceiverAfter,
                    TransferMilliliters,
                    PlanCode) &&
                    TransferMilliliters > KINDA_SMALL_NUMBER;
                ActionTarget = Held;
                SecondaryTarget = Receiver;
            }
            break;
        case EVistaAffordance::PickUp:
            bExecutable = !IsValid(Held) && IsValid(FocusedPickup) &&
                FocusedPickup->bPortable &&
                FocusedPickup->GetPhysicalDisposition() !=
                    EVistaPickupDisposition::Held &&
                TargetAffordances.Contains(EVistaAffordance::PickUp);
            break;
        case EVistaAffordance::Place:
            if (IsValid(Held) && Held != FocusedTarget &&
                Held->GetCarrier() == this &&
                Held->GetPhysicalDisposition() ==
                    EVistaPickupDisposition::Held &&
                IVistaInteractable::Execute_VistaGetAffordances(Held)
                    .Contains(EVistaAffordance::Place))
            {
                FName AnchorCode;
                FString AnchorSemanticId;
                bExecutable = IsValid(
                    UVistaActionExecutorComponent::ResolveStablePlacementAnchor(
                        const_cast<AVistaPlayableHomeCharacter*>(this),
                        FocusedTarget,
                        AnchorCode,
                        AnchorSemanticId));
                ActionTarget = Held;
                SecondaryTarget = FocusedTarget;
            }
            break;
        default:
            break;
        }

        if (bExecutable)
        {
            bExecutable = HasApprovedPlayerActionAnimation(
                AnimationComponent,
                Affordance,
                ActionTarget,
                SecondaryTarget);
        }
        if (bExecutable)
        {
            FVistaPlayerActionOption Option;
            Option.Affordance = Affordance;
            Option.Target = ActionTarget;
            Option.SecondaryTarget = SecondaryTarget;
            Options.Add(MoveTemp(Option));
        }
    }
    return Options;
}

int32 AVistaPlayableHomeCharacter::FindDefaultPlayerActionIndex(
    const TArray<FVistaPlayerActionOption>& Options) const
{
    if (Options.IsEmpty())
    {
        return INDEX_NONE;
    }
    if (IsValid(PostureComponent) &&
        PostureComponent->GetPostureState() == EVistaPostureState::Seated)
    {
        return Options.IndexOfByPredicate(
            [](const FVistaPlayerActionOption& Option)
            {
                return Option.Affordance == EVistaAffordance::Stand;
            });
    }

    AActor* FocusedTarget = IsValid(InteractionComponent)
        ? InteractionComponent->GetFocusedActor()
        : nullptr;
    if (IsValid(HeldItem) && IsValid(FocusedTarget) &&
        FocusedTarget != HeldItem)
    {
        const int32 PourIndex = Options.IndexOfByPredicate(
            [](const FVistaPlayerActionOption& Option)
            {
                return Option.Affordance == EVistaAffordance::Pour;
            });
        if (PourIndex != INDEX_NONE)
        {
            return PourIndex;
        }
        const int32 PlaceIndex = Options.IndexOfByPredicate(
            [](const FVistaPlayerActionOption& Option)
            {
                return Option.Affordance == EVistaAffordance::Place;
            });
        if (PlaceIndex != INDEX_NONE)
        {
            return PlaceIndex;
        }
    }
    const EVistaAffordance DefaultAffordance =
        GetDefaultInteractionAffordance(FocusedTarget);
    const int32 DefaultIndex = Options.IndexOfByPredicate(
        [DefaultAffordance](const FVistaPlayerActionOption& Option)
        {
            return Option.Affordance == DefaultAffordance;
        });
    return DefaultIndex != INDEX_NONE ? DefaultIndex : 0;
}

void AVistaPlayableHomeCharacter::RefreshPlayerActionSelection()
{
    FVistaPlayerActionOption PreviousSelection;
    const bool bHadSelection = GetSelectedPlayerAction(PreviousSelection);
    TArray<FVistaPlayerActionOption> NextOptions =
        BuildExecutablePlayerActions();
    int32 NextIndex = INDEX_NONE;
    if (bHadSelection)
    {
        NextIndex = NextOptions.IndexOfByPredicate(
            [&PreviousSelection](const FVistaPlayerActionOption& Option)
            {
                return Option.Matches(PreviousSelection);
            });
    }
    if (NextIndex == INDEX_NONE)
    {
        NextIndex = FindDefaultPlayerActionIndex(NextOptions);
    }
    ExecutablePlayerActions = MoveTemp(NextOptions);
    SelectedPlayerActionIndex = NextIndex;
    const UWorld* World = GetWorld();
    NextPlayerActionRefreshAtSeconds = IsValid(World)
        ? World->GetTimeSeconds() + PlayerActionRefreshIntervalSeconds
        : 0.0;
}

bool AVistaPlayableHomeCharacter::GetSelectedPlayerAction(
    FVistaPlayerActionOption& OutAction) const
{
    if (!ExecutablePlayerActions.IsValidIndex(SelectedPlayerActionIndex))
    {
        return false;
    }
    OutAction = ExecutablePlayerActions[SelectedPlayerActionIndex];
    return IsValid(OutAction.Target);
}

FVistaInteractionResult
AVistaPlayableHomeCharacter::PerformSelectedPlayerAction()
{
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("AUTHORITY_REQUIRED"));
    }
    RefreshPlayerActionSelection();
    FVistaPlayerActionOption Action;
    return GetSelectedPlayerAction(Action)
        ? PerformPlayerAction(Action)
        : FVistaInteractionResult::Failure(
            EVistaInteractionStatus::NotFound,
            TEXT("NO_EXECUTABLE_PLAYER_ACTION"));
}

FVistaInteractionResult AVistaPlayableHomeCharacter::PerformRequestedPlayerAction(
    const EVistaAffordance Affordance,
    AActor* Target,
    AActor* SecondaryTarget)
{
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("AUTHORITY_REQUIRED"));
    }
    FVistaPlayerActionOption Requested;
    Requested.Affordance = Affordance;
    Requested.Target = Target;
    Requested.SecondaryTarget = SecondaryTarget;
    const TArray<FVistaPlayerActionOption> CurrentOptions =
        BuildExecutablePlayerActions();
    const FVistaPlayerActionOption* Matched = CurrentOptions.FindByPredicate(
        [&Requested](const FVistaPlayerActionOption& Option)
        {
            return Option.Matches(Requested);
        });
    if (Matched == nullptr)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("PLAYER_ACTION_NOT_AVAILABLE"));
    }
    return PerformPlayerAction(*Matched);
}

FVistaInteractionResult AVistaPlayableHomeCharacter::PerformPlayerAction(
    const FVistaPlayerActionOption& Action)
{
    if (!HasAuthority() || !IsValid(Action.Target))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("AUTHORITY_OR_ACTION_TARGET_REQUIRED"));
    }
    switch (Action.Affordance)
    {
    case EVistaAffordance::PickUp:
        return BeginPhysicalInteraction(
            Action.Target,
            EVistaAffordance::PickUp);
    case EVistaAffordance::Place:
        return BeginPhysicalInteraction(
            Action.Target,
            EVistaAffordance::Place,
            Action.SecondaryTarget);
    case EVistaAffordance::Pour:
        return BeginSemanticInteraction(
            Action.Target,
            EVistaAffordance::Pour,
            Action.SecondaryTarget);
    case EVistaAffordance::Inspect:
        return BeginAnimatedInspectInteraction();
    case EVistaAffordance::Press:
    case EVistaAffordance::TurnOn:
    case EVistaAffordance::TurnOff:
    case EVistaAffordance::Open:
    case EVistaAffordance::Close:
    case EVistaAffordance::Sit:
    case EVistaAffordance::Stand:
        return BeginSemanticInteraction(Action.Target, Action.Affordance);
    default:
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Unsupported,
            TEXT("PLAYER_ACTION_SELECTOR_AFFORDANCE_UNSUPPORTED"));
    }
}

FVistaInteractionResult AVistaPlayableHomeCharacter::PerformInspectInteraction()
{
    return BeginAnimatedInspectInteraction();
}

void AVistaPlayableHomeCharacter::BeginInspectionPresentation(
    AActor* Target,
    const FVistaInspectionPresentation& Presentation)
{
    if (!IsLocallyControlled() || !IsValid(Target) || !Presentation.bActive)
    {
        return;
    }
    if (InspectionPresentation.bActive)
    {
        ExitInspection();
    }
    InspectionPresentation = Presentation;
    InspectedTarget = Target;
    InspectionStartedAtSeconds = IsValid(GetWorld())
        ? GetWorld()->GetTimeSeconds()
        : 0.0;
    if (IsValid(Controller))
    {
        PreInspectionControlRotation = Controller->GetControlRotation();
    }
    GetCharacterMovement()->StopMovementImmediately();
    EndSprint();
    EndCrouch();
    UpdateInspectionFocus();
}

void AVistaPlayableHomeCharacter::ExitInspection()
{
    if (!InspectionPresentation.bActive)
    {
        return;
    }
    const FString ClosedSemanticId = InspectionPresentation.SemanticId;
    InspectionPresentation = FVistaInspectionPresentation();
    InspectedTarget.Reset();
    InspectionStartedAtSeconds = 0.0;
    if (IsValid(Controller))
    {
        Controller->SetControlRotation(PreInspectionControlRotation);
    }
    FVistaEntityRuntimeState EmptyState;
    PublishInteractionResult(
        FVistaInteractionResult::Success(
            ClosedSemanticId,
            EmptyState,
            TEXT("INSPECTION_CLOSED")));
}

void AVistaPlayableHomeCharacter::UpdateInspectionFocus()
{
    AActor* Target = InspectedTarget.Get();
    if (!InspectionPresentation.bActive || !IsValid(Target) || !IsValid(Controller))
    {
        return;
    }
    FVector ViewLocation;
    FRotator IgnoredViewRotation;
    Controller->GetPlayerViewPoint(ViewLocation, IgnoredViewRotation);
    FVector TargetOrigin;
    FVector TargetExtent;
    Target->GetActorBounds(true, TargetOrigin, TargetExtent);
    if (!TargetOrigin.ContainsNaN() &&
        FVector::DistSquared(ViewLocation, TargetOrigin) > KINDA_SMALL_NUMBER)
    {
        Controller->SetControlRotation((TargetOrigin - ViewLocation).Rotation());
    }
}

bool AVistaPlayableHomeCharacter::IsActionFeedbackVisible() const
{
    if (!ActionFeedback.bVisible)
    {
        return false;
    }
    if (!ActionFeedback.bTerminal)
    {
        return true;
    }
    return !IsValid(GetWorld()) ||
        GetWorld()->GetTimeSeconds() <= ActionFeedbackExpiresAtSeconds;
}

void AVistaPlayableHomeCharacter::SetActionFeedbackLocal(
    const FVistaPlayerActionFeedback& Feedback)
{
    ActionFeedback = Feedback;
    ActionFeedbackExpiresAtSeconds =
        Feedback.bTerminal && IsValid(GetWorld())
            ? GetWorld()->GetTimeSeconds() + TerminalFeedbackSeconds
            : 0.0;
}

void AVistaPlayableHomeCharacter::PublishInteractionResult(
    const FVistaInteractionResult& Result,
    EVistaActionPhase Phase,
    bool bTerminal)
{
    FVistaPlayerActionFeedback Feedback;
    Feedback.bVisible = true;
    Feedback.bTerminal = bTerminal;
    Feedback.Status = Result.Status;
    Feedback.Phase = Phase;
    Feedback.Code = Result.Code.IsNone() ? FName(TEXT("UNKNOWN_RESULT")) : Result.Code;
    Feedback.SemanticId = BoundedPresentationText(
        Result.SemanticId,
        MaximumPresentationTextCharacters);
    SetActionFeedbackLocal(Feedback);
    if (HasAuthority() && !IsLocallyControlled())
    {
        ClientPresentInteractionFeedback(Feedback);
    }
}

void AVistaPlayableHomeCharacter::PublishTransactionFeedback(
    const FVistaActionTransactionRecord& Record)
{
    LastPresentedActionPhase = Record.Phase;
    LastPresentedTransactionStatus = Record.Status;
    LastPresentedTransactionCode = Record.Code;
    PublishInteractionResult(
        UVistaActionExecutorComponent::InteractionResultFromTransaction(Record),
        Record.Phase,
        Record.IsTerminal());
}

void AVistaPlayableHomeCharacter::UpdatePendingActionFeedback()
{
    if (!HasAuthority() || PendingPresentationCommandId.IsNone() ||
        !IsValid(ActionExecutorComponent))
    {
        return;
    }
    FVistaActionTransactionRecord Record;
    if (!ActionExecutorComponent->GetTransaction(
            PendingPresentationCommandId,
            Record))
    {
        const FString MissingSemanticId = PendingInspectionTarget.IsValid()
            ? IVistaInteractable::Execute_VistaGetSemanticId(
                PendingInspectionTarget.Get())
            : FString();
        PendingInspectionTarget.Reset();
        PendingPresentationCommandId = NAME_None;
        LastPresentedActionPhase = EVistaActionPhase::Idle;
        LastPresentedTransactionStatus = EVistaActionTransactionStatus::Idle;
        LastPresentedTransactionCode = NAME_None;
        PublishInteractionResult(
            FVistaInteractionResult::Failure(
                EVistaInteractionStatus::InvalidState,
                TEXT("ACTION_RECEIPT_UNAVAILABLE"),
                MissingSemanticId));
        return;
    }
    if (Record.Phase != LastPresentedActionPhase ||
        Record.Status != LastPresentedTransactionStatus ||
        Record.Code != LastPresentedTransactionCode)
    {
        PublishTransactionFeedback(Record);
    }
    if (Record.IsTerminal())
    {
        AActor* CompletedInspectionTarget =
            Record.Status == EVistaActionTransactionStatus::Succeeded &&
                Record.Affordance == EVistaAffordance::Inspect &&
                Record.bHasAfterState
            ? PendingInspectionTarget.Get()
            : nullptr;
        PendingPresentationCommandId = NAME_None;
        LastPresentedActionPhase = EVistaActionPhase::Idle;
        LastPresentedTransactionStatus = EVistaActionTransactionStatus::Idle;
        LastPresentedTransactionCode = NAME_None;
        PendingInspectionTarget.Reset();
        if (IsValid(CompletedInspectionTarget))
        {
            PresentCompletedInspection(
                CompletedInspectionTarget,
                Record.AfterState);
        }
    }
}

FVistaInteractionResult
AVistaPlayableHomeCharacter::BeginAnimatedInspectInteraction()
{
    if (!HasAuthority() || !IsValid(InteractionComponent))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("INSPECT_AUTHORITY_REQUIRED"));
    }
    AActor* Target = InteractionComponent->GetFocusedActor();
    if (!IsValid(Target) ||
        !Target->GetClass()->ImplementsInterface(
            UVistaInteractable::StaticClass()))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::NotFound,
            TEXT("NO_INTERACTABLE_TARGET"));
    }
    const TArray<EVistaAffordance> Affordances =
        IVistaInteractable::Execute_VistaGetAffordances(Target);
    if (!Affordances.Contains(EVistaAffordance::Inspect))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Unsupported,
            TEXT("INSPECT_UNSUPPORTED"),
            IVistaInteractable::Execute_VistaGetSemanticId(Target));
    }

    const FVistaInteractionResult Result =
        BeginSemanticInteraction(Target, EVistaAffordance::Inspect);
    if (Result.IsSuccess() && !PendingPresentationCommandId.IsNone())
    {
        PendingInspectionTarget = Target;
    }
    return Result;
}

bool AVistaPlayableHomeCharacter::CancelPendingAnimatedInspection(FName Reason)
{
    if (!HasAuthority() || PendingPresentationCommandId.IsNone() ||
        !IsValid(ActionExecutorComponent))
    {
        return false;
    }
    FVistaActionTransactionRecord Record;
    if (!ActionExecutorComponent->GetTransaction(
            PendingPresentationCommandId,
            Record))
    {
        const FString MissingSemanticId = PendingInspectionTarget.IsValid()
            ? IVistaInteractable::Execute_VistaGetSemanticId(
                PendingInspectionTarget.Get())
            : FString();
        PendingInspectionTarget.Reset();
        PendingPresentationCommandId = NAME_None;
        LastPresentedActionPhase = EVistaActionPhase::Idle;
        LastPresentedTransactionStatus = EVistaActionTransactionStatus::Idle;
        LastPresentedTransactionCode = NAME_None;
        PublishInteractionResult(
            FVistaInteractionResult::Failure(
                EVistaInteractionStatus::InvalidState,
                TEXT("ACTION_RECEIPT_UNAVAILABLE"),
                MissingSemanticId));
        return false;
    }
    if (Record.Affordance != EVistaAffordance::Inspect)
    {
        return false;
    }
    if (Record.IsTerminal())
    {
        // Escape or lifecycle teardown after terminal completion suppresses
        // the pending card while still publishing the terminal action result.
        PendingInspectionTarget.Reset();
        UpdatePendingActionFeedback();
        return true;
    }
    if (!ActionExecutorComponent->CancelActiveAction(Reason))
    {
        return false;
    }
    UpdatePendingActionFeedback();
    return true;
}

void AVistaPlayableHomeCharacter::PresentCompletedInspection(
    AActor* Target,
    const FVistaEntityRuntimeState& InspectedState)
{
    if (!HasAuthority() || !IsValid(Target) ||
        !Target->GetClass()->ImplementsInterface(
            UVistaInteractable::StaticClass()) ||
        InspectedState.SemanticId.IsEmpty() ||
        InspectedState.SemanticId !=
            IVistaInteractable::Execute_VistaGetSemanticId(Target))
    {
        return;
    }
    const FVistaInspectionPresentation Presentation =
        BuildInspectionPresentation(Target, InspectedState);
    if (IsLocallyControlled())
    {
        BeginInspectionPresentation(Target, Presentation);
    }
    else
    {
        ClientBeginInspectionPresentation(Target, Presentation);
    }
}

FVistaInteractionResult AVistaPlayableHomeCharacter::PerformDefaultInteraction()
{
    if (IsValid(PostureComponent) && PostureComponent->GetPostureState() == EVistaPostureState::Seated)
    {
        AVistaSeatActor* ActiveSeat = PostureComponent->GetActiveSeat();
        if (IsValid(ActiveSeat))
        {
            return BeginSemanticInteraction(ActiveSeat, EVistaAffordance::Stand);
        }
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("POSTURE_ACTIVE_SEAT_LOST"));
    }
    if (IsValid(PostureComponent) && PostureComponent->GetPostureState() != EVistaPostureState::Standing)
    {
        return FVistaInteractionResult::Failure(EVistaInteractionStatus::Busy, TEXT("POSTURE_TRANSITION_ACTIVE"));
    }
    AActor* Target = InteractionComponent->GetFocusedActor();
    if (!IsValid(Target))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::NotFound, TEXT("NO_INTERACTABLE_TARGET"));
    }

    if (IsValid(HeldItem) && Target != HeldItem)
    {
        if (HeldItem->IsPourable() &&
            IsValid(Cast<AVistaLiquidReceiverActor>(Target)))
        {
            return BeginSemanticInteraction(
                HeldItem,
                EVistaAffordance::Pour,
                Target);
        }
        return BeginPhysicalInteraction(
            HeldItem, EVistaAffordance::Place, Target);
    }
    const EVistaAffordance Affordance = GetDefaultInteractionAffordance(Target);
    if (Affordance == EVistaAffordance::PickUp)
    {
        return BeginPhysicalInteraction(Target, Affordance);
    }
    if (Affordance == EVistaAffordance::Inspect)
    {
        return BeginAnimatedInspectInteraction();
    }
    if (UVistaActionExecutorComponent::IsAnimatedSemanticAffordance(Affordance))
    {
        return BeginSemanticInteraction(Target, Affordance);
    }
    return InteractionComponent->TryInteract(Affordance);
}

FVistaInteractionResult
AVistaPlayableHomeCharacter::PerformFocusedApplianceInteraction(
    const EVistaAffordance Affordance)
{
    if (!AVistaStatefulApplianceActor::IsTransactionalApplianceAffordance(
            Affordance))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Unsupported,
            TEXT("APPLIANCE_AFFORDANCE_REQUIRED"));
    }
    AActor* Target = IsValid(InteractionComponent)
        ? InteractionComponent->GetFocusedActor() : nullptr;
    if (!IsValid(Target) ||
        !Target->IsA<AVistaStatefulApplianceActor>())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::NotFound,
            TEXT("APPLIANCE_TARGET_REQUIRED"));
    }
    const TArray<EVistaAffordance> Affordances =
        IVistaInteractable::Execute_VistaGetAffordances(Target);
    if (!Affordances.Contains(Affordance))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Unsupported,
            TEXT("AFFORDANCE_UNSUPPORTED"),
            IVistaInteractable::Execute_VistaGetSemanticId(Target));
    }
    return BeginSemanticInteraction(Target, Affordance);
}

EVistaAffordance AVistaPlayableHomeCharacter::GetDefaultInteractionAffordance(
    AActor* Target) const
{
    if (IsValid(PostureComponent) &&
        PostureComponent->GetPostureState() == EVistaPostureState::Seated &&
        PostureComponent->GetActiveSeat() == Target)
    {
        return EVistaAffordance::Stand;
    }
    if (!IsValid(Target) || !Target->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        return EVistaAffordance::Inspect;
    }
    const TArray<EVistaAffordance> Affordances =
        IVistaInteractable::Execute_VistaGetAffordances(Target);
    if (Affordances.Contains(EVistaAffordance::PickUp))
    {
        return EVistaAffordance::PickUp;
    }
    if (Affordances.Contains(EVistaAffordance::Open))
    {
        const FVistaEntityRuntimeState State = IVistaInteractable::Execute_VistaGetRuntimeState(Target);
        const FString* OpenValue = State.Values.Find(TEXT("open"));
        const bool bOpen = OpenValue && OpenValue->Equals(TEXT("true"), ESearchCase::CaseSensitive);
        return bOpen && Affordances.Contains(EVistaAffordance::Close)
            ? EVistaAffordance::Close
            : EVistaAffordance::Open;
    }
    if (Affordances.Contains(EVistaAffordance::TurnOn) ||
        Affordances.Contains(EVistaAffordance::TurnOff))
    {
        const FVistaEntityRuntimeState State =
            IVistaInteractable::Execute_VistaGetRuntimeState(Target);
        const FString* ActiveValue = State.Values.Find(TEXT("active"));
        const bool bActive = ActiveValue != nullptr &&
            ActiveValue->Equals(TEXT("true"), ESearchCase::CaseSensitive);
        if (bActive && Affordances.Contains(EVistaAffordance::TurnOff))
        {
            return EVistaAffordance::TurnOff;
        }
        if (!bActive && Affordances.Contains(EVistaAffordance::TurnOn))
        {
            return EVistaAffordance::TurnOn;
        }
    }
    if (Affordances.Contains(EVistaAffordance::Press))
    {
        return EVistaAffordance::Press;
    }
    if (Affordances.Contains(EVistaAffordance::Toggle))
    {
        return EVistaAffordance::Toggle;
    }
    if (Affordances.Contains(EVistaAffordance::Sit))
    {
        return EVistaAffordance::Sit;
    }
    if (Affordances.Contains(EVistaAffordance::Stand))
    {
        return EVistaAffordance::Stand;
    }
    return EVistaAffordance::Inspect;
}

FVistaInteractionResult AVistaPlayableHomeCharacter::DropHeldItem()
{
    if (!IsValid(HeldItem))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState, TEXT("NO_HELD_ITEM"));
    }
    const FVector ThrowVelocity = GetVelocity() + GetActorForwardVector() * 120.0f;
    return BeginPhysicalInteraction(
        HeldItem, EVistaAffordance::Drop, nullptr, ThrowVelocity);
}

FVistaInteractionResult AVistaPlayableHomeCharacter::BeginPhysicalInteraction(
    AActor* PhysicalTarget,
    EVistaAffordance Affordance,
    AActor* PlacementOwner,
    const FVector& ReleaseVelocity)
{
    const bool bHadPendingAction = !PendingPresentationCommandId.IsNone();
    if (bHadPendingAction)
    {
        UpdatePendingActionFeedback();
    }
    // A terminal drain can present an Inspect card only on the owning client.
    // Always consume that input edge instead of starting a second action on
    // the server before a remote client has seen the terminal presentation.
    if (bHadPendingAction || !PendingPresentationCommandId.IsNone() ||
        InspectionPresentation.bActive)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Busy,
            InspectionPresentation.bActive
                ? FName(TEXT("INSPECTION_ACTIVE"))
                : FName(TEXT("ACTION_IN_PROGRESS")));
    }
    if (!IsValid(ActionExecutorComponent) || !IsValid(PhysicalTarget))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("ACTION_EXECUTOR_UNAVAILABLE"));
    }
    UVistaPlayableHomeRuntimeSubsystem* Runtime = IsValid(GetWorld())
        ? GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>() : nullptr;
    const FName CommandId = IsValid(Runtime)
        ? Runtime->AllocatePhysicalActionCommandId() : NAME_None;
    if (CommandId.IsNone())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("ACTION_TICKET_UNAVAILABLE"));
    }
    FVistaPhysicalActionRequest Request;
    Request.CommandId = CommandId;
    Request.Requester = this;
    Request.Target = PhysicalTarget;
    Request.PlacementOwner = PlacementOwner;
    Request.Affordance = Affordance;
    Request.ExpectedRevision = IsValid(InteractionComponent)
        ? InteractionComponent->GetExpectedRevision()
        : NAME_None;
    if (const UVistaEventSubsystem* Events = IsValid(GetWorld())
            ? GetWorld()->GetSubsystem<UVistaEventSubsystem>()
            : nullptr)
    {
        Request.SessionGeneration = Events->GetSessionGeneration();
    }
    Request.TimeoutSeconds = 10.0f;
    Request.ReleaseVelocity = ReleaseVelocity;
    FVistaActionTransactionRecord Record;
    ActionExecutorComponent->BeginPhysicalInteraction(Request, Record);
    const FVistaInteractionResult Result =
        UVistaActionExecutorComponent::InteractionResultFromTransaction(Record);
    if (!Result.IsSuccess())
    {
        return Result;
    }
    if (!Record.IsTerminal())
    {
        PendingPresentationCommandId = CommandId;
        LastPresentedActionPhase = EVistaActionPhase::Idle;
        LastPresentedTransactionStatus = EVistaActionTransactionStatus::Idle;
        LastPresentedTransactionCode = NAME_None;
    }
    // UVistaActionExecutorComponent owns RecordSuccessfulInteraction and emits
    // it only after the animation completion phase; this player entry returns
    // the accepted ticket without duplicating that terminal event.
    return Result;
}

FVistaInteractionResult AVistaPlayableHomeCharacter::BeginSemanticInteraction(
    AActor* Target,
    const EVistaAffordance Affordance,
    AActor* SecondaryTarget)
{
    const bool bHadPendingAction = !PendingPresentationCommandId.IsNone();
    if (bHadPendingAction)
    {
        UpdatePendingActionFeedback();
    }
    // Match physical actions: the input that drains a completed transaction
    // cannot also enqueue a new semantic action behind its presentation.
    if (bHadPendingAction || !PendingPresentationCommandId.IsNone() ||
        InspectionPresentation.bActive)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Busy,
            InspectionPresentation.bActive
                ? FName(TEXT("INSPECTION_ACTIVE"))
                : FName(TEXT("ACTION_IN_PROGRESS")));
    }
    if (!IsValid(ActionExecutorComponent) || !IsValid(Target) ||
        !UVistaActionExecutorComponent::IsAnimatedSemanticAffordance(Affordance))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("SEMANTIC_ACTION_EXECUTOR_UNAVAILABLE"));
    }
    if (Affordance == EVistaAffordance::Sit)
    {
        EndSprint();
        EndCrouch();
    }
    UVistaPlayableHomeRuntimeSubsystem* Runtime = IsValid(GetWorld())
        ? GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>()
        : nullptr;
    const FName CommandId = IsValid(Runtime)
        ? Runtime->AllocatePhysicalActionCommandId()
        : NAME_None;
    if (CommandId.IsNone())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("ACTION_TICKET_UNAVAILABLE"));
    }
    FVistaSemanticActionRequest Request;
    Request.CommandId = CommandId;
    Request.Requester = this;
    Request.Target = Target;
    Request.SecondaryTarget = SecondaryTarget;
    Request.Affordance = Affordance;
    Request.ExpectedRevision = IsValid(InteractionComponent)
        ? InteractionComponent->GetExpectedRevision()
        : NAME_None;
    if (const UVistaEventSubsystem* Events = IsValid(GetWorld())
            ? GetWorld()->GetSubsystem<UVistaEventSubsystem>()
            : nullptr)
    {
        Request.SessionGeneration = Events->GetSessionGeneration();
    }
    Request.TimeoutSeconds = 10.0f;
    FVistaActionTransactionRecord Record;
    ActionExecutorComponent->BeginSemanticInteraction(Request, Record);
    const FVistaInteractionResult Result =
        UVistaActionExecutorComponent::InteractionResultFromTransaction(Record);
    if (Result.IsSuccess() && !Record.IsTerminal())
    {
        PendingPresentationCommandId = CommandId;
        LastPresentedActionPhase = EVistaActionPhase::Idle;
        LastPresentedTransactionStatus =
            EVistaActionTransactionStatus::Idle;
        LastPresentedTransactionCode = NAME_None;
    }
    return Result;
}

USceneComponent* AVistaPlayableHomeCharacter::VistaGetCarryAnchor_Implementation() const
{
    return CarryAnchor;
}

AActor* AVistaPlayableHomeCharacter::VistaGetHeldItem_Implementation() const
{
    return HeldItem;
}

bool AVistaPlayableHomeCharacter::VistaTryClaimItem_Implementation(AActor* Item)
{
    AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(Item);
    if (!IsValid(Pickup) || IsValid(HeldItem))
    {
        return false;
    }
    HeldItem = Pickup;
    ForceNetUpdate();
    return HeldItem == Pickup;
}

void AVistaPlayableHomeCharacter::VistaReleaseItem_Implementation(AActor* Item)
{
    if (HeldItem == Item)
    {
        HeldItem = nullptr;
        ForceNetUpdate();
    }
}

void AVistaPlayableHomeCharacter::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaPlayableHomeCharacter, HeldItem);
}
