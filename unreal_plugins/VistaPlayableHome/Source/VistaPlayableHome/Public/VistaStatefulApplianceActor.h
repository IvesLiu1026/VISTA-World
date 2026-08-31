#pragma once

#include "CoreMinimal.h"
#include "VistaSemanticActor.h"
#include "VistaStatefulApplianceActor.generated.h"

class UStaticMeshComponent;
class USceneComponent;
class UVistaActionExecutorComponent;

/** Closed visual-control vocabulary used by the R15 gesture router. */
UENUM(BlueprintType)
enum class EVistaApplianceControlStyle : uint8
{
    Rotary,
    Button
};

/** Project-authored effect of the appliance's primary pressable control. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaAppliancePressProfile
{
    GENERATED_BODY()

    /** Stable authored identity such as start, stop, brew, or flush. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    FName ControlId = TEXT("start");

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    bool bResultActive = true;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    FName ResultStatus = TEXT("running");
};

/** Target-authored status vocabulary for activation/deactivation. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaApplianceActivityProfile
{
    GENERATED_BODY()

    /** Category-specific active state: running, heating, flowing, and so on. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    FName ActiveStatus = TEXT("running");

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    FName InactiveStatus = TEXT("idle");
};

/** Closed, rollback-safe appliance state. No field aliases another field. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaApplianceState
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    bool bPowered = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    bool bActive = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    FName Status = TEXT("off");

    bool operator==(const FVistaApplianceState& Other) const
    {
        return bPowered == Other.bPowered && bActive == Other.bActive &&
            Status == Other.Status;
    }
};

UCLASS(Blueprintable)
class VISTAPLAYABLEHOME_API AVistaStatefulApplianceActor final : public AVistaSemanticActor
{
    GENERATED_BODY()

public:
    AVistaStatefulApplianceActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    TObjectPtr<UStaticMeshComponent> Mesh;

    /** Unique authored hand-contact point; never supplied by TCP/NLP input. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    TObjectPtr<USceneComponent> ControlTarget;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    FName ApplianceKind = TEXT("generic");

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    EVistaApplianceControlStyle ControlStyle =
        EVistaApplianceControlStyle::Rotary;

    /** Backward-compatible authored default for active; it never implies power. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    bool bInitiallyOn = false;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    bool bInitiallyPowered = true;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    FName InitialStatus = TEXT("idle");

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    FVistaApplianceActivityProfile ActivityProfile;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Appliance")
    FVistaAppliancePressProfile PressProfile;

    UFUNCTION(BlueprintPure, Category = "VISTA|Appliance")
    bool IsOn() const { return bActive; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Appliance")
    bool IsPowered() const { return bPowered; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Appliance")
    bool IsActive() const { return bActive; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Appliance")
    FName GetApplianceStatus() const { return Status; }

    /** Pure transition planner shared by runtime commits and automation proof. */
    static bool PlanInteractionTransition(
        const FVistaApplianceState& Before,
        EVistaAffordance Affordance,
        const FVistaApplianceActivityProfile& InActivityProfile,
        const FVistaAppliancePressProfile& InPressProfile,
        FVistaApplianceState& OutAfter,
        bool& bOutMutated,
        FName& OutCode);

    static bool IsTransactionalApplianceAffordance(EVistaAffordance Affordance);

    /** Recomputes the authored transition and compares the exact observed state. */
    bool StateMatchesTransition(
        const FVistaEntityRuntimeState& Before,
        const FVistaEntityRuntimeState& After,
        EVistaAffordance Affordance) const;

    virtual FVistaEntityRuntimeState VistaGetRuntimeState_Implementation() const override;
    virtual FVistaInteractionResult VistaApplyRuntimeState_Implementation(
        const FVistaEntityRuntimeState& State) override;
    virtual FVistaInteractionResult VistaInteract_Implementation(
        const FVistaInteractionRequest& Request) override;
    virtual void GetLifetimeReplicatedProps(
        TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:
    virtual void BeginPlay() override;

    UFUNCTION(BlueprintImplementableEvent, Category = "VISTA|Appliance")
    void OnApplianceStateChanged(bool bNewOn);

    UFUNCTION(BlueprintImplementableEvent, Category = "VISTA|Appliance")
    void OnApplianceRuntimeStateChanged(
        bool bNewPowered,
        bool bNewActive,
        FName NewStatus);

private:
    friend class UVistaActionExecutorComponent;

    UPROPERTY(ReplicatedUsing = OnRep_ApplianceState)
    bool bPowered = false;

    UPROPERTY(ReplicatedUsing = OnRep_ApplianceState)
    bool bActive = false;

    UPROPERTY(ReplicatedUsing = OnRep_ApplianceState)
    FName Status = TEXT("off");

    TWeakObjectPtr<UVistaActionExecutorComponent> ActiveTransactionExecutor;
    FName ActiveTransactionCommandId = NAME_None;

    UFUNCTION()
    void OnRep_ApplianceState();

    bool TryReserveTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    bool ReleaseTransaction(
        UVistaActionExecutorComponent* Executor,
        FName CommandId);
    FVistaInteractionResult CommitTransactionalInteraction(
        UVistaActionExecutorComponent* Executor,
        const FVistaInteractionRequest& Request,
        FName CommitCommandId);
    FVistaInteractionResult RestoreTransactionalState(
        UVistaActionExecutorComponent* Executor,
        FName CommandId,
        const FVistaEntityRuntimeState& State);
    FVistaInteractionResult ApplyApplianceRuntimeState(
        const FVistaEntityRuntimeState& State,
        FName SuccessCode);
    FVistaApplianceState GetClosedApplianceState() const;
    void SetClosedApplianceState(const FVistaApplianceState& NewState);
    void SyncRuntimeStateValues();
    static bool ReadBooleanValue(
        const TMap<FName, FString>& Values,
        FName Key,
        bool& OutValue,
        bool& bOutPresent);
    static bool ReadClosedState(
        const FVistaEntityRuntimeState& State,
        const FVistaApplianceState& Fallback,
        FVistaApplianceState& OutState,
        FName& OutCode);

};
