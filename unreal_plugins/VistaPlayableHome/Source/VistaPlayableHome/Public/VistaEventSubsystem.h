#pragma once

// Modified in VISTA-World on 2026-08-22: evaluate typed EventSpec outcomes.

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VistaPlayableHomeTypes.h"
#include "VistaEventSubsystem.generated.h"

UCLASS()
class VISTAPLAYABLEHOME_API UVistaEventSubsystem final : public UTickableWorldSubsystem
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category = "VISTA|Event")
    void InitializeWorldRevision(FName Revision);

    UFUNCTION(BlueprintCallable, Category = "VISTA|Event")
    bool RegisterEventDefinitions(const TArray<FVistaEventDefinition>& Definitions,
                                  FName& OutCode);

    UFUNCTION(BlueprintCallable, Category = "VISTA|Event")
    bool StartEvent(FName EventId, FName ExpectedRevision,
                    int32 ExpectedGeneration, FName& OutCode);

    UFUNCTION(BlueprintCallable, Category = "VISTA|Event")
    bool ResetEvent(FName ExpectedRevision, int32 ExpectedGeneration,
                    FName& OutCode);

    UFUNCTION(BlueprintPure, Category = "VISTA|Event")
    FName GetWorldRevision() const { return WorldRevision; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Event")
    int32 GetSessionGeneration() const { return SessionGeneration; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Event")
    FName GetActiveEventId() const { return ActiveEventId; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Event")
    EVistaEventStatus GetEventStatus() const { return EventStatus; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Event")
    FString GetPublicGoal() const { return ActivePublicGoal; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Event")
    FName GetTerminalConditionId() const { return TerminalConditionId; }

    /** Record one successful closed affordance from local, NPC, or TCP gameplay. */
    void RecordSuccessfulInteraction(const FString& TargetSemanticId,
                                     EVistaAffordance Affordance);

    /** Advance exactly once after a successful broker-owned live mutation. */
    bool CommitCommandGeneration(int32 ExpectedGeneration, int32& OutGeneration);

    virtual void Tick(float DeltaTime) override;
    virtual TStatId GetStatId() const override;

private:
    FName WorldRevision = NAME_None;
    int32 SessionGeneration = 0;
    TMap<FName, FVistaEventDefinition> EventDefinitions;
    FName ActiveEventId = NAME_None;
    FString ActivePublicGoal;
    EVistaEventStatus EventStatus = EVistaEventStatus::Inactive;
    double EventStartedAt = 0.0;
    float ActiveTimeoutSeconds = 0.0f;
    TMap<TWeakObjectPtr<AActor>, FVistaEntityRuntimeState> BaselineStates;
    TArray<TWeakObjectPtr<AActor>> SpawnedFixtures;
    TArray<TWeakObjectPtr<class AVistaHomeNpcController>> ModifiedNpcControllers;
    TArray<FVistaEventCondition> ActiveSuccessConditions;
    TArray<FVistaEventCondition> ActiveFailureConditions;
    TSet<FString> ObservedInteractions;
    FName TerminalConditionId = NAME_None;

    bool ValidateDefinition(const FVistaEventDefinition& Definition, FName& OutCode) const;
    bool ValidateCondition(const FVistaEventCondition& Condition, FName& OutCode) const;
    bool EvaluateCondition(const FVistaEventCondition& Condition,
                           double ElapsedSeconds) const;
    void EvaluateOutcome();
    bool ApplyOperation(const FVistaEventOperation& Operation, FName& OutCode);
    void RestoreBaseline();
    AActor* ResolveSemanticActor(const FString& SemanticId) const;
    AActor* ResolvePlayerActor() const;
    static FString InteractionKey(const FString& TargetSemanticId,
                                  EVistaAffordance Affordance);
    bool ValidateEnvelope(FName ExpectedRevision, int32 ExpectedGeneration,
                          FName& OutCode) const;
};
