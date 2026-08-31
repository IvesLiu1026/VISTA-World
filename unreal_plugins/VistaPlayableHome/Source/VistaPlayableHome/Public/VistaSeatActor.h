#pragma once

#include "CoreMinimal.h"
#include "VistaSemanticActor.h"
#include "VistaSeatActor.generated.h"

class UStaticMeshComponent;
class USceneComponent;
class UVistaPostureComponent;

/** One atomic, authoritative occupancy record for an authored seat. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaSeatOccupancyState
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Seat")
    bool bOccupied = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Seat")
    TObjectPtr<AActor> OccupiedBy = nullptr;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Seat")
    FString OccupiedBySemanticId;

    bool IsClosed() const
    {
        return bOccupied
            ? IsValid(OccupiedBy) && !OccupiedBySemanticId.IsEmpty()
            : !IsValid(OccupiedBy) && OccupiedBySemanticId.IsEmpty();
    }
};

/**
 * Closed authority for one authored seat target.
 *
 * Runtime callers cannot provide an attachment target. UVistaPostureComponent
 * alone may reserve this actor and commit occupancy against SeatTarget.
 */
UCLASS(Blueprintable)
class VISTAPLAYABLEHOME_API AVistaSeatActor final : public AVistaSemanticActor
{
    GENERATED_BODY()

public:
    AVistaSeatActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Seat")
    TObjectPtr<UStaticMeshComponent> Mesh;

    /** Project-authored pelvis/root target; never supplied by NLP or TCP. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Seat")
    TObjectPtr<USceneComponent> SeatTarget;

    UFUNCTION(BlueprintPure, Category = "VISTA|Seat")
    bool IsOccupied() const { return Occupancy.bOccupied; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Seat")
    AActor* GetOccupiedBy() const { return Occupancy.OccupiedBy.Get(); }

    UFUNCTION(BlueprintPure, Category = "VISTA|Seat")
    FString GetOccupiedBySemanticId() const
    {
        return Occupancy.OccupiedBySemanticId;
    }

    UFUNCTION(BlueprintPure, Category = "VISTA|Seat")
    bool IsReserved() const;

    UFUNCTION(BlueprintPure, Category = "VISTA|Seat")
    FVistaSeatOccupancyState GetOccupancyState() const { return Occupancy; }

    bool IsOccupiedBy(
        const AActor* Occupant,
        const FString& OccupantSemanticId) const;

    virtual FVistaEntityRuntimeState VistaGetRuntimeState_Implementation() const override;
    virtual FVistaInteractionResult VistaApplyRuntimeState_Implementation(
        const FVistaEntityRuntimeState& State) override;
    virtual FVistaInteractionResult VistaInteract_Implementation(
        const FVistaInteractionRequest& Request) override;
    virtual void GetLifetimeReplicatedProps(
        TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:
    virtual void BeginPlay() override;

    UFUNCTION(BlueprintImplementableEvent, Category = "VISTA|Seat")
    void OnSeatOccupancyChanged(
        bool bNewOccupied,
        AActor* NewOccupant,
        const FString& NewOccupantSemanticId);

private:
    friend class UVistaPostureComponent;

    UPROPERTY(ReplicatedUsing = OnRep_Occupancy)
    FVistaSeatOccupancyState Occupancy;

    TWeakObjectPtr<UVistaPostureComponent> ReservedPosture;
    TWeakObjectPtr<AActor> ReservedOccupant;
    FString ReservedOccupantSemanticId;
    FName ReservationCommandId = NAME_None;

    UFUNCTION()
    void OnRep_Occupancy();

    bool TryReserveForSit(
        UVistaPostureComponent* Posture,
        FName CommandId,
        AActor* Occupant,
        const FString& OccupantSemanticId,
        FName& OutCode);
    bool TryReserveForStand(
        UVistaPostureComponent* Posture,
        FName CommandId,
        AActor* Occupant,
        const FString& OccupantSemanticId,
        FName& OutCode);
    bool ReservationMatches(
        const UVistaPostureComponent* Posture,
        FName CommandId,
        const AActor* Occupant,
        const FString& OccupantSemanticId) const;
    bool ReleaseReservation(
        UVistaPostureComponent* Posture,
        FName CommandId,
        AActor* Occupant,
        const FString& OccupantSemanticId,
        FName& OutCode);
    bool CommitSitOccupancy(
        UVistaPostureComponent* Posture,
        FName CommandId,
        AActor* Occupant,
        const FString& OccupantSemanticId,
        FName& OutCode);
    bool CommitStandVacancy(
        UVistaPostureComponent* Posture,
        FName CommandId,
        AActor* Occupant,
        const FString& OccupantSemanticId,
        FName& OutCode);

    void ClearReservation();
    void SetOccupancy(const FVistaSeatOccupancyState& NewOccupancy);
    void SyncOccupancyRuntimeValues();
    bool HasAnyReservationField() const;
    bool HasClosedReservation() const;
};
