#pragma once

#include "AIController.h"
#include "CoreMinimal.h"
#include "Navigation/PathFollowingComponent.h"
#include "VistaPlayableHomeTypes.h"
#include "VistaHomeNpcController.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FVistaNpcActionFinished,
                                            const FVistaNpcActionResult&, Result);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FVistaNpcSpoke,
                                             const FString&, NpcSemanticId,
                                             const FString&, Speech);

class UVistaActionExecutorComponent;
enum class EVistaPostureState : uint8;

UCLASS(Blueprintable)
class VISTAPLAYABLEHOME_API AVistaHomeNpcController final : public AAIController
{
    GENERATED_BODY()

public:
    AVistaHomeNpcController();

    UPROPERTY(BlueprintAssignable, Category = "VISTA|NPC")
    FVistaNpcActionFinished OnActionFinished;

    UPROPERTY(BlueprintAssignable, Category = "VISTA|NPC")
    FVistaNpcSpoke OnNpcSpoke;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    TObjectPtr<UVistaActionExecutorComponent> ActionExecutorComponent;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|NPC",
              meta = (ClampMin = "1", ClampMax = "64"))
    int32 MaxQueueDepth = 32;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|NPC",
              meta = (ClampMin = "10.0", ClampMax = "250.0"))
    float NavigationAcceptanceRadius = 75.0f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|NPC",
              meta = (ClampMin = "50.0", ClampMax = "500.0"))
    float NavigationProjectionExtent = 200.0f;

    UFUNCTION(BlueprintCallable, Category = "VISTA|NPC")
    bool ReplaceActionQueue(const TArray<FVistaNpcAction>& Actions, FName& OutCode);

    /** Validate queue shape, target identity, affordances, and inventory read-only. */
    UFUNCTION(BlueprintPure, Category = "VISTA|NPC")
    bool PreflightActionQueue(const TArray<FVistaNpcAction>& Actions,
                              FName& OutCode) const;

    UFUNCTION(BlueprintCallable, Category = "VISTA|NPC")
    bool EnqueueAction(const FVistaNpcAction& Action, FName& OutCode);

    UFUNCTION(BlueprintCallable, Category = "VISTA|NPC")
    void CancelActionQueue(FName Reason = TEXT("QUEUE_CANCELED"));

    UFUNCTION(BlueprintPure, Category = "VISTA|NPC")
    FVistaNpcActionResult GetCurrentActionResult() const { return CurrentResult; }

    UFUNCTION(BlueprintPure, Category = "VISTA|NPC")
    bool HasLastCompletedActionResult() const { return bHasLastCompletedResult; }

    UFUNCTION(BlueprintPure, Category = "VISTA|NPC")
    FVistaNpcActionResult GetLastCompletedActionResult() const
    {
        return LastCompletedResult;
    }

    UFUNCTION(BlueprintPure, Category = "VISTA|NPC")
    FString GetLastCompletedRoomId() const { return LastCompletedRoomId; }

    UFUNCTION(BlueprintPure, Category = "VISTA|NPC")
    int32 GetQueuedActionCount() const { return ActionQueue.Num(); }

    virtual void Tick(float DeltaSeconds) override;

protected:
    virtual void OnMoveCompleted(FAIRequestID RequestId,
                                 const FPathFollowingResult& Result) override;

private:
    TArray<FVistaNpcAction> ActionQueue;
    TOptional<FVistaNpcAction> CurrentAction;
    FVistaNpcActionResult CurrentResult;
    FVistaNpcActionResult LastCompletedResult;
    FString LastCompletedRoomId;
    bool bHasLastCompletedResult = false;
    double ActionStartedAt = 0.0;
    bool bActionStarted = false;
    TOptional<FVector> ActiveNavigationGoal;
    FAIRequestID ActiveNavigationRequestId = FAIRequestID::InvalidRequest;

    bool ValidateAction(const FVistaNpcAction& Action, FName& OutCode) const;
    bool ValidateQueueShape(const TArray<FVistaNpcAction>& Actions,
                            FName& OutCode) const;
    bool ValidateActionTargetReadOnly(const FVistaNpcAction& Action,
                                      AActor*& InOutSimulatedHeldItem,
                                      EVistaPostureState& InOutSimulatedPosture,
                                      FString& InOutSimulatedSeatSemanticId,
                                      TMap<FString, FVistaLiquidStateSnapshot>&
                                          InOutSimulatedSourceLiquids,
                                      TMap<FString, FVistaLiquidStateSnapshot>&
                                          InOutSimulatedReceiverLiquids,
                                      FName& OutCode) const;
    void StopControlledMotion();
    void EnterCommandedIdle(bool bMotionAlreadyStopped = false);
    void StartNextAction();
    void StartCurrentAction();
    void RememberCurrentExternalResult();
    void CompleteCurrent(EVistaNpcActionStatus Status, FName Code);
    void UpdateCurrentRoomFromNavigationTarget(const FVistaNpcAction& Action) const;
    AActor* ResolveSemanticActor(const FString& SemanticId) const;
    FVistaInteractionResult ExecuteInteraction(AActor* Target, EVistaAffordance Affordance,
                                                USceneComponent* PlacementAnchor = nullptr) const;
    bool PollAnimationAction();
    bool PollPhysicalAction();
    bool StartPhysicalAction(const FVistaNpcAction& Action, AActor* Target);
};
