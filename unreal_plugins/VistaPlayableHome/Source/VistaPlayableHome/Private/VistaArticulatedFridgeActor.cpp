#include "VistaArticulatedFridgeActor.h"

#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/OverlapResult.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "Net/UnrealNetwork.h"

namespace
{
bool ParseExactBoolean(const FString& Value, bool& OutValue)
{
    if (Value.Equals(TEXT("true"), ESearchCase::CaseSensitive))
    {
        OutValue = true;
        return true;
    }
    if (Value.Equals(TEXT("false"), ESearchCase::CaseSensitive))
    {
        OutValue = false;
        return true;
    }
    return false;
}
}

AVistaArticulatedFridgeActor::AVistaArticulatedFridgeActor()
{
    PrimaryActorTick.bCanEverTick = true;

    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    SetRootComponent(SceneRoot);

    BodyMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BodyMesh"));
    BodyMesh->SetupAttachment(SceneRoot);
    BodyMesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));

    PrimaryHinge = CreateDefaultSubobject<USceneComponent>(TEXT("PrimaryHinge"));
    PrimaryHinge->SetupAttachment(SceneRoot);
    PrimaryDoorMesh =
        CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PrimaryDoorMesh"));
    PrimaryDoorMesh->SetupAttachment(PrimaryHinge);
    PrimaryDoorMesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));
    PrimaryDoorMesh->SetGenerateOverlapEvents(true);

    SecondaryHinge =
        CreateDefaultSubobject<USceneComponent>(TEXT("SecondaryHinge"));
    SecondaryHinge->SetupAttachment(SceneRoot);
    SecondaryDoorMesh =
        CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SecondaryDoorMesh"));
    SecondaryDoorMesh->SetupAttachment(SecondaryHinge);
    SecondaryDoorMesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));
    SecondaryDoorMesh->SetGenerateOverlapEvents(true);

    HandleTarget = CreateDefaultSubobject<USceneComponent>(TEXT("HandleTarget"));
    HandleTarget->SetupAttachment(PrimaryHinge);
    HandleTarget->ComponentTags.Add(TEXT("VistaDoorHandleTarget"));

    AllowedAffordances = {
        EVistaAffordance::Inspect,
        EVistaAffordance::Open,
        EVistaAffordance::Close};
}

void AVistaArticulatedFridgeActor::BeginPlay()
{
    Super::BeginPlay();
    PrimaryClosedRotation = PrimaryHinge->GetRelativeRotation();
    SecondaryClosedRotation = SecondaryHinge->GetRelativeRotation();
    if (HasAuthority())
    {
        bOpen = bInitiallyOpen;
    }
    ApplyDoorState(true);
}

void AVistaArticulatedFridgeActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    PrimaryHinge->SetRelativeRotation(FMath::RInterpConstantTo(
        PrimaryHinge->GetRelativeRotation(),
        PrimaryTargetRotation,
        DeltaSeconds,
        AngularSpeedDegrees));
    SecondaryHinge->SetRelativeRotation(FMath::RInterpConstantTo(
        SecondaryHinge->GetRelativeRotation(),
        SecondaryTargetRotation,
        DeltaSeconds,
        AngularSpeedDegrees));
}

void AVistaArticulatedFridgeActor::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaArticulatedFridgeActor, bOpen);
}

FVistaEntityRuntimeState
AVistaArticulatedFridgeActor::VistaGetRuntimeState_Implementation() const
{
    FVistaEntityRuntimeState State = Super::VistaGetRuntimeState_Implementation();
    State.Values.Add(TEXT("open"), bOpen ? TEXT("true") : TEXT("false"));
    State.Values.Add(
        TEXT("primary_door_open"), bOpen ? TEXT("true") : TEXT("false"));
    State.Values.Add(TEXT("secondary_door_open"), TEXT("false"));
    State.Values.Add(
        TEXT("primary_angle_deg"),
        FString::SanitizeFloat(PrimaryHinge->GetRelativeRotation().Yaw));
    State.Values.Add(TEXT("receptacle_count"), FString::FromInt(ReceptacleCount));
    return State;
}

FVistaInteractionResult
AVistaArticulatedFridgeActor::VistaApplyRuntimeState_Implementation(
    const FVistaEntityRuntimeState& State)
{
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("AUTHORITY_REQUIRED"),
            SemanticId);
    }
    if (!State.SemanticId.IsEmpty() && State.SemanticId != SemanticId)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::NotFound,
            TEXT("SEMANTIC_ID_MISMATCH"),
            SemanticId);
    }

    bool bRequestedOpen = bOpen;
    if (const FString* OpenValue = State.Values.Find(TEXT("open")))
    {
        if (!ParseExactBoolean(*OpenValue, bRequestedOpen))
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::InvalidState,
                TEXT("FRIDGE_OPEN_STATE_INVALID"),
                SemanticId);
        }
    }
    if (bRequestedOpen != bOpen && IsDoorMotionObstructed(bRequestedOpen))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Blocked,
            TEXT("FRIDGE_DOOR_SWEEP_OBSTRUCTED"),
            SemanticId);
    }

    // All fridge-specific validation is complete before the base class is
    // allowed to mutate transform, visibility, or runtime state.
    const FVistaInteractionResult BaseResult =
        Super::VistaApplyRuntimeState_Implementation(State);
    if (!BaseResult.IsSuccess())
    {
        return BaseResult;
    }
    bOpen = bRequestedOpen;
    ApplyDoorState(false);
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("FRIDGE_STATE_APPLIED"));
}

FVistaInteractionResult AVistaArticulatedFridgeActor::VistaInteract_Implementation(
    const FVistaInteractionRequest& Request)
{
    const FVistaInteractionResult Validation = ValidateRequest(Request);
    if (!Validation.IsSuccess())
    {
        return Validation;
    }
    if (Request.Affordance == EVistaAffordance::Inspect)
    {
        return Super::VistaInteract_Implementation(Request);
    }
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("AUTHORITY_REQUIRED"),
            SemanticId);
    }

    const bool bRequestedOpen = Request.Affordance == EVistaAffordance::Open;
    if (Request.Affordance != EVistaAffordance::Open &&
        Request.Affordance != EVistaAffordance::Close)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Unsupported,
            TEXT("FRIDGE_AFFORDANCE_UNSUPPORTED"),
            SemanticId);
    }
    if (bRequestedOpen == bOpen)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            bOpen ? FName(TEXT("FRIDGE_ALREADY_OPEN"))
                  : FName(TEXT("FRIDGE_ALREADY_CLOSED")),
            SemanticId);
    }
    if (IsDoorMotionObstructed(bRequestedOpen))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Blocked,
            TEXT("FRIDGE_DOOR_SWEEP_OBSTRUCTED"),
            SemanticId);
    }

    bOpen = bRequestedOpen;
    ApplyDoorState(false);
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        bOpen ? TEXT("FRIDGE_OPENED") : TEXT("FRIDGE_CLOSED"));
}

void AVistaArticulatedFridgeActor::OnRep_OpenState()
{
    ApplyDoorState(false);
}

bool AVistaArticulatedFridgeActor::IsDoorMotionObstructed(
    const bool bRequestedOpen) const
{
    const UStaticMesh* Mesh = PrimaryDoorMesh->GetStaticMesh();
    const UWorld* World = GetWorld();
    if (!IsValid(Mesh) || !IsValid(World))
    {
        return true;
    }

    const FBox LocalBounds = Mesh->GetBoundingBox();
    const FVector Scale = PrimaryDoorMesh->GetRelativeScale3D();
    const FVector Extent(
        FMath::Abs(LocalBounds.GetExtent().X * Scale.X) + 2.0f,
        FMath::Abs(LocalBounds.GetExtent().Y * Scale.Y) + 2.0f,
        FMath::Abs(LocalBounds.GetExtent().Z * Scale.Z) + 2.0f);
    const FVector LeafCenterFromHinge =
        PrimaryDoorMesh->GetRelativeLocation() + LocalBounds.GetCenter();
    const FTransform RootTransform = SceneRoot->GetComponentTransform();
    const float StartYaw = PrimaryHinge->GetRelativeRotation().Yaw;
    const float EndYaw = PrimaryClosedRotation.Yaw +
        (bRequestedOpen ? -OpenAngleDegrees : 0.0f);

    FCollisionObjectQueryParams ObjectTypes;
    ObjectTypes.AddObjectTypesToQuery(ECC_Pawn);
    ObjectTypes.AddObjectTypesToQuery(ECC_PhysicsBody);
    ObjectTypes.AddObjectTypesToQuery(ECC_WorldDynamic);
    FCollisionQueryParams QueryParams(
        SCENE_QUERY_STAT(VistaFridgeDoorSweep), false, this);
    QueryParams.AddIgnoredActor(this);

    constexpr int32 SweepSteps = 24;
    for (int32 Step = 0; Step <= SweepSteps; ++Step)
    {
        const float Alpha = static_cast<float>(Step) /
            static_cast<float>(SweepSteps);
        const FRotator Rotation(
            PrimaryClosedRotation.Pitch,
            FMath::Lerp(StartYaw, EndYaw, Alpha),
            PrimaryClosedRotation.Roll);
        const FVector CenterInRoot = PrimaryHinge->GetRelativeLocation() +
            Rotation.RotateVector(LeafCenterFromHinge);
        const FVector WorldCenter = RootTransform.TransformPosition(CenterInRoot);
        const FQuat WorldRotation =
            RootTransform.GetRotation() * Rotation.Quaternion();
        TArray<FOverlapResult> Overlaps;
        if (!World->OverlapMultiByObjectType(
                Overlaps,
                WorldCenter,
                WorldRotation,
                ObjectTypes,
                FCollisionShape::MakeBox(Extent),
                QueryParams))
        {
            continue;
        }
        for (const FOverlapResult& Overlap : Overlaps)
        {
            AActor* Actor = Overlap.GetActor();
            if (!IsValid(Actor) || Actor == this)
            {
                continue;
            }
            if (Actor->IsA<APawn>())
            {
                return true;
            }
            const UPrimitiveComponent* Component = Overlap.GetComponent();
            if (IsValid(Component) && Component->IsSimulatingPhysics())
            {
                return true;
            }
        }
    }
    return false;
}

void AVistaArticulatedFridgeActor::ApplyDoorState(const bool bInstant)
{
    PrimaryTargetRotation = PrimaryClosedRotation +
        FRotator(0.0f, bOpen ? -OpenAngleDegrees : 0.0f, 0.0f);
    // R1 exposes the primary refrigerator compartment.  The second HSSD link
    // remains physically present and closed until part-targeted affordances are
    // added to the catalog.
    SecondaryTargetRotation = SecondaryClosedRotation;
    if (bInstant)
    {
        PrimaryHinge->SetRelativeRotation(PrimaryTargetRotation);
        SecondaryHinge->SetRelativeRotation(SecondaryTargetRotation);
    }
    BodyMesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    PrimaryDoorMesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    SecondaryDoorMesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
}
