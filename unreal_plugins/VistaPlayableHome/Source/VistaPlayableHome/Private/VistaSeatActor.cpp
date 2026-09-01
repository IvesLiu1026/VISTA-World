#include "VistaSeatActor.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Net/UnrealNetwork.h"
#include "VistaPostureComponent.h"

namespace
{
const FName OccupiedKey(TEXT("occupied"));
const FName OccupiedByKey(TEXT("occupied_by"));

bool IsExactBoolean(const FString& Value, const bool Expected)
{
    return Value.Equals(
        Expected ? TEXT("true") : TEXT("false"),
        ESearchCase::CaseSensitive);
}
} // namespace

AVistaSeatActor::AVistaSeatActor()
{
    Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SeatMesh"));
    SetRootComponent(Mesh);
    Mesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));

    SeatTarget = CreateDefaultSubobject<USceneComponent>(TEXT("SeatTarget"));
    SeatTarget->SetupAttachment(Mesh);
    SeatTarget->ComponentTags.Add(TEXT("VistaSeatTarget"));

    AllowedAffordances = {
        EVistaAffordance::Inspect,
        EVistaAffordance::Sit,
        EVistaAffordance::Stand};
}

void AVistaSeatActor::BeginPlay()
{
    Super::BeginPlay();
    if (HasAuthority())
    {
        ClearReservation();
        SetOccupancy(FVistaSeatOccupancyState{});
    }
    else
    {
        SyncOccupancyRuntimeValues();
    }
}

void AVistaSeatActor::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (HasAuthority())
    {
        TArray<UVistaPostureComponent*> AffectedPostures;
        if (ReservedPosture.IsValid())
        {
            AffectedPostures.AddUnique(ReservedPosture.Get());
        }
        if (IsValid(Occupancy.OccupiedBy))
        {
            if (UVistaPostureComponent* OccupiedPosture =
                    Occupancy.OccupiedBy->FindComponentByClass<UVistaPostureComponent>())
            {
                AffectedPostures.AddUnique(OccupiedPosture);
            }
        }
        for (UVistaPostureComponent* Posture : AffectedPostures)
        {
            if (IsValid(Posture))
            {
                Posture->HandleSeatEndPlay(this);
            }
        }
        ClearReservation();
        SetOccupancy(FVistaSeatOccupancyState{});
    }
    Super::EndPlay(EndPlayReason);
}

void AVistaSeatActor::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaSeatActor, Occupancy);
}

bool AVistaSeatActor::IsReserved() const
{
    return HasAnyReservationField();
}

bool AVistaSeatActor::IsOccupiedBy(
    const AActor* Occupant,
    const FString& OccupantSemanticId) const
{
    return Occupancy.IsClosed() && Occupancy.bOccupied &&
        IsValid(Occupant) && Occupancy.OccupiedBy == Occupant &&
        !OccupantSemanticId.IsEmpty() &&
        Occupancy.OccupiedBySemanticId == OccupantSemanticId;
}

void AVistaSeatActor::ReleaseForPostureEndPlay(
    UVistaPostureComponent* Posture,
    AActor* Occupant,
    const FString& OccupantSemanticId)
{
    if (!HasAuthority() || !IsValid(Posture) || !IsValid(Occupant))
    {
        return;
    }
    if (ReservedPosture.Get() == Posture || ReservedOccupant.Get() == Occupant)
    {
        ClearReservation();
    }
    if (IsOccupiedBy(Occupant, OccupantSemanticId))
    {
        SetOccupancy(FVistaSeatOccupancyState{});
    }
}

TArray<EVistaAffordance> AVistaSeatActor::VistaGetAffordances_Implementation() const
{
    return Occupancy.bOccupied
        ? TArray<EVistaAffordance>{EVistaAffordance::Inspect, EVistaAffordance::Stand}
        : TArray<EVistaAffordance>{EVistaAffordance::Inspect, EVistaAffordance::Sit};
}

FVistaEntityRuntimeState
AVistaSeatActor::VistaGetRuntimeState_Implementation() const
{
    FVistaEntityRuntimeState State =
        Super::VistaGetRuntimeState_Implementation();
    State.Values.Add(
        OccupiedKey,
        Occupancy.bOccupied ? TEXT("true") : TEXT("false"));
    State.Values.Add(OccupiedByKey, Occupancy.OccupiedBySemanticId);
    return State;
}

FVistaInteractionResult
AVistaSeatActor::VistaApplyRuntimeState_Implementation(
    const FVistaEntityRuntimeState& State)
{
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("AUTHORITY_REQUIRED"),
            SemanticId);
    }
    if (HasAnyReservationField())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Busy,
            TEXT("SEAT_RESERVED"),
            SemanticId);
    }
    if (!Occupancy.IsClosed() || Occupancy.bOccupied)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Busy,
            TEXT("SEAT_OCCUPIED"),
            SemanticId);
    }

    const FString* RequestedOccupied = State.Values.Find(OccupiedKey);
    const FString* RequestedOccupiedBy = State.Values.Find(OccupiedByKey);
    if ((RequestedOccupied != nullptr &&
         !IsExactBoolean(*RequestedOccupied, false)) ||
        (RequestedOccupiedBy != nullptr && !RequestedOccupiedBy->IsEmpty()))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("SEAT_OCCUPANCY_AUTHORITY_REQUIRED"),
            SemanticId);
    }

    const FVistaInteractionResult BaseResult =
        Super::VistaApplyRuntimeState_Implementation(State);
    if (!BaseResult.IsSuccess())
    {
        return BaseResult;
    }
    SyncOccupancyRuntimeValues();
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("SEAT_FREE_STATE_APPLIED"));
}

FVistaInteractionResult AVistaSeatActor::VistaInteract_Implementation(
    const FVistaInteractionRequest& Request)
{
    const FVistaInteractionResult Validation = ValidateRequest(Request);
    if (!Validation.IsSuccess())
    {
        return Validation;
    }
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("AUTHORITY_REQUIRED"),
            SemanticId);
    }
    if (Request.Affordance == EVistaAffordance::Sit ||
        Request.Affordance == EVistaAffordance::Stand)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("POSTURE_COMPONENT_REQUIRED"),
            SemanticId);
    }
    return Super::VistaInteract_Implementation(Request);
}

bool AVistaSeatActor::TryReserveForSit(
    UVistaPostureComponent* Posture,
    const FName CommandId,
    AActor* Occupant,
    const FString& OccupantSemanticId,
    FName& OutCode)
{
    if (!HasAuthority())
    {
        OutCode = TEXT("SEAT_AUTHORITY_REQUIRED");
        return false;
    }
    if (!IsValid(Posture) || !IsValid(Occupant) || CommandId.IsNone() ||
        OccupantSemanticId.IsEmpty() || Posture->GetOwner() != Occupant)
    {
        OutCode = TEXT("SEAT_RESERVATION_ARGUMENT_INVALID");
        return false;
    }
    if (!Occupancy.IsClosed())
    {
        OutCode = TEXT("SEAT_OCCUPANCY_INVALID");
        return false;
    }
    if (Occupancy.bOccupied)
    {
        OutCode = TEXT("SEAT_OCCUPIED");
        return false;
    }
    if (HasAnyReservationField())
    {
        OutCode = TEXT("SEAT_RESERVED");
        return false;
    }
    ReservedPosture = Posture;
    ReservedOccupant = Occupant;
    ReservedOccupantSemanticId = OccupantSemanticId;
    ReservationCommandId = CommandId;
    OutCode = TEXT("SEAT_RESERVED_FOR_SIT");
    return true;
}

bool AVistaSeatActor::TryReserveForStand(
    UVistaPostureComponent* Posture,
    const FName CommandId,
    AActor* Occupant,
    const FString& OccupantSemanticId,
    FName& OutCode)
{
    if (!HasAuthority())
    {
        OutCode = TEXT("SEAT_AUTHORITY_REQUIRED");
        return false;
    }
    if (!IsValid(Posture) || !IsValid(Occupant) || CommandId.IsNone() ||
        OccupantSemanticId.IsEmpty() || Posture->GetOwner() != Occupant)
    {
        OutCode = TEXT("SEAT_RESERVATION_ARGUMENT_INVALID");
        return false;
    }
    if (!IsOccupiedBy(Occupant, OccupantSemanticId))
    {
        OutCode = TEXT("SEAT_OCCUPANT_MISMATCH");
        return false;
    }
    if (HasAnyReservationField())
    {
        OutCode = TEXT("SEAT_RESERVED");
        return false;
    }
    ReservedPosture = Posture;
    ReservedOccupant = Occupant;
    ReservedOccupantSemanticId = OccupantSemanticId;
    ReservationCommandId = CommandId;
    OutCode = TEXT("SEAT_RESERVED_FOR_STAND");
    return true;
}

bool AVistaSeatActor::ReservationMatches(
    const UVistaPostureComponent* Posture,
    const FName CommandId,
    const AActor* Occupant,
    const FString& OccupantSemanticId) const
{
    return HasClosedReservation() && IsValid(Posture) &&
        IsValid(Occupant) && !CommandId.IsNone() &&
        !OccupantSemanticId.IsEmpty() &&
        ReservedPosture.Get() == Posture &&
        ReservedOccupant.Get() == Occupant &&
        ReservedOccupantSemanticId == OccupantSemanticId &&
        ReservationCommandId == CommandId;
}

bool AVistaSeatActor::ReleaseReservation(
    UVistaPostureComponent* Posture,
    const FName CommandId,
    AActor* Occupant,
    const FString& OccupantSemanticId,
    FName& OutCode)
{
    if (!HasAuthority())
    {
        OutCode = TEXT("SEAT_AUTHORITY_REQUIRED");
        return false;
    }
    if (!ReservationMatches(
            Posture,
            CommandId,
            Occupant,
            OccupantSemanticId))
    {
        OutCode = TEXT("SEAT_RESERVATION_REQUIRED");
        return false;
    }
    ClearReservation();
    OutCode = TEXT("SEAT_RESERVATION_RELEASED");
    return true;
}

bool AVistaSeatActor::CommitSitOccupancy(
    UVistaPostureComponent* Posture,
    const FName CommandId,
    AActor* Occupant,
    const FString& OccupantSemanticId,
    FName& OutCode)
{
    if (!HasAuthority())
    {
        OutCode = TEXT("SEAT_AUTHORITY_REQUIRED");
        return false;
    }
    if (!ReservationMatches(
            Posture,
            CommandId,
            Occupant,
            OccupantSemanticId))
    {
        OutCode = TEXT("SEAT_RESERVATION_REQUIRED");
        return false;
    }
    if (!Occupancy.IsClosed() || Occupancy.bOccupied)
    {
        OutCode = TEXT("SEAT_OCCUPANCY_CONFLICT");
        return false;
    }

    FVistaSeatOccupancyState NewOccupancy;
    NewOccupancy.bOccupied = true;
    NewOccupancy.OccupiedBy = Occupant;
    NewOccupancy.OccupiedBySemanticId = OccupantSemanticId;
    if (!NewOccupancy.IsClosed())
    {
        OutCode = TEXT("SEAT_OCCUPANCY_INVALID");
        return false;
    }
    SetOccupancy(NewOccupancy);
    ClearReservation();
    OutCode = TEXT("SEAT_OCCUPIED_AT_SIT_COMPLETION");
    return true;
}

bool AVistaSeatActor::CommitStandVacancy(
    UVistaPostureComponent* Posture,
    const FName CommandId,
    AActor* Occupant,
    const FString& OccupantSemanticId,
    FName& OutCode)
{
    if (!HasAuthority())
    {
        OutCode = TEXT("SEAT_AUTHORITY_REQUIRED");
        return false;
    }
    if (!ReservationMatches(
            Posture,
            CommandId,
            Occupant,
            OccupantSemanticId))
    {
        OutCode = TEXT("SEAT_RESERVATION_REQUIRED");
        return false;
    }
    if (!IsOccupiedBy(Occupant, OccupantSemanticId))
    {
        OutCode = TEXT("SEAT_OCCUPANT_MISMATCH");
        return false;
    }

    SetOccupancy(FVistaSeatOccupancyState{});
    ClearReservation();
    OutCode = TEXT("SEAT_VACATED_AT_STAND_COMPLETION");
    return true;
}

void AVistaSeatActor::ClearReservation()
{
    ReservedPosture.Reset();
    ReservedOccupant.Reset();
    ReservedOccupantSemanticId.Empty();
    ReservationCommandId = NAME_None;
}

void AVistaSeatActor::SetOccupancy(
    const FVistaSeatOccupancyState& NewOccupancy)
{
    check(NewOccupancy.IsClosed());
    Occupancy = NewOccupancy;
    SyncOccupancyRuntimeValues();
    OnSeatOccupancyChanged(
        Occupancy.bOccupied,
        Occupancy.OccupiedBy.Get(),
        Occupancy.OccupiedBySemanticId);
    ForceNetUpdate();
}

void AVistaSeatActor::SyncOccupancyRuntimeValues()
{
    RuntimeStateValues.Add(
        OccupiedKey,
        Occupancy.bOccupied ? TEXT("true") : TEXT("false"));
    RuntimeStateValues.Add(OccupiedByKey, Occupancy.OccupiedBySemanticId);
}

bool AVistaSeatActor::HasClosedReservation() const
{
    return ReservedPosture.IsValid() &&
        ReservedOccupant.IsValid() && !ReservedOccupantSemanticId.IsEmpty() &&
        !ReservationCommandId.IsNone() &&
        ReservedPosture->GetOwner() == ReservedOccupant.Get();
}

bool AVistaSeatActor::HasAnyReservationField() const
{
    return ReservedPosture.IsValid() || ReservedOccupant.IsValid() ||
        !ReservedOccupantSemanticId.IsEmpty() ||
        !ReservationCommandId.IsNone();
}

void AVistaSeatActor::OnRep_Occupancy()
{
    if (!Occupancy.IsClosed())
    {
        return;
    }
    SyncOccupancyRuntimeValues();
    OnSeatOccupancyChanged(
        Occupancy.bOccupied,
        Occupancy.OccupiedBy.Get(),
        Occupancy.OccupiedBySemanticId);
}
