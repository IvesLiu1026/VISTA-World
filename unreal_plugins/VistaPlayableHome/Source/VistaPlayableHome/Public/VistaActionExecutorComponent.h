#pragma once

#include "Components/ActorComponent.h"
#include "CoreMinimal.h"
#include "VistaPlayableHomeTypes.h"
#include "VistaActionExecutorComponent.generated.h"

class AActor;
class AVistaPickupActor;
class USceneComponent;
class UVistaAnimationComponent;

/** C++-only closed input to the physical action executor. */
struct VISTAPLAYABLEHOME_API FVistaPhysicalActionRequest final
{
    FName CommandId = NAME_None;
    AActor* Requester = nullptr;
    AActor* Target = nullptr;
    AActor* PlacementOwner = nullptr;
    USceneComponent* PlacementAnchor = nullptr;
    FString RequesterSemanticId;
    FString TargetSemanticId;
    FString PlacementAnchorSemanticId;
    EVistaAffordance Affordance = EVistaAffordance::Inspect;
    FName ExpectedRevision = NAME_None;
    int32 SessionGeneration = 0;
    float TimeoutSeconds = 10.0f;
    FVector ReleaseVelocity = FVector::ZeroVector;
    bool bCommitSessionGenerationOnSuccess = false;
};

/**
 * One authority for player, NPC, and typed-live pickup/place/drop mutations.
 *
 * The target is mutated only from ContactCommit after the fixed project-owned
 * montage emits its contact notify. A terminal failure after contact restores
 * the captured before-state before the transaction becomes observable as idle.
 */
UCLASS(ClassGroup = (VISTA), meta = (BlueprintSpawnableComponent))
class VISTAPLAYABLEHOME_API UVistaActionExecutorComponent final
    : public UActorComponent
{
    GENERATED_BODY()

public:
    UVistaActionExecutorComponent();

    bool BeginPhysicalInteraction(
        const FVistaPhysicalActionRequest& Request,
        FVistaActionTransactionRecord& OutRecord);

#if WITH_DEV_AUTOMATION_TESTS
    /**
     * Editor automation only: exercise the transaction independently of the
     * currently license-blocked montage assets. The production entry point
     * above still evaluates HasApprovedMutationAnimation and remains fail-closed.
     */
    bool BeginPhysicalInteractionForDevAutomation(
        const FVistaPhysicalActionRequest& Request,
        FVistaActionTransactionRecord& OutRecord);

    /**
     * Editor automation only: deterministically drive a previously accepted
     * action through contact, then either complete it or fail after contact so
     * the normal trusted rollback path is exercised.
     */
    bool DrivePhysicalInteractionForDevAutomation(
        bool bFailAfterContact,
        FVistaActionTransactionRecord& OutRecord);
#endif

    /** Replay is side-effect free; a known id with a different signature fails closed. */
    bool TryReplayPhysicalInteraction(
        const FVistaPhysicalActionRequest& Request,
        FVistaActionTransactionRecord& OutRecord,
        bool& bOutCommandKnown) const;

    UFUNCTION(BlueprintPure, Category = "VISTA|Action")
    bool GetTransaction(FName CommandId, FVistaActionTransactionRecord& OutRecord) const;

    UFUNCTION(BlueprintCallable, Category = "VISTA|Action")
    bool CancelActiveAction(FName Reason = TEXT("ACTION_CANCELED"));

    UFUNCTION(BlueprintPure, Category = "VISTA|Action")
    bool HasActiveAction() const { return ActiveAction.IsSet(); }

    static bool IsPhysicalAffordance(EVistaAffordance Affordance);
    /** Length-framed binary identity rendered as lowercase hex, never delimiter text. */
    static FString CanonicalRequestHex(const FVistaPhysicalActionRequest& Request);
    static FVistaInteractionResult InteractionResultFromTransaction(
        const FVistaActionTransactionRecord& Record);

    /** Configure or validate a body-owned hand/provider grip; camera chains are rejected. */
    static USceneComponent* PrepareCarryAnchor(AActor* Requester, FName& OutCode);
    static bool IsCarryAnchorSafe(const AActor* Requester, const USceneComponent* Anchor);

    /** Resolve an actual TargetPoint whose stable tags name the focused owner. */
    static USceneComponent* ResolveStablePlacementAnchor(
        AActor* Requester,
        AActor* FocusedOwner,
        FName& OutCode,
        FString& OutSemanticId);

    virtual void TickComponent(
        float DeltaTime,
        ELevelTick TickType,
        FActorComponentTickFunction* ThisTickFunction) override;

protected:
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    struct FActivePhysicalAction final
    {
        FVistaPhysicalActionRequest Request;
        FString CanonicalRequest;
        TWeakObjectPtr<AActor> Requester;
        TWeakObjectPtr<AActor> Target;
        TWeakObjectPtr<AActor> PlacementOwner;
        TWeakObjectPtr<USceneComponent> PlacementAnchor;
        TWeakObjectPtr<USceneComponent> CarryAnchor;
        TWeakObjectPtr<USceneComponent> BeforeAttachmentParent;
        TWeakObjectPtr<AActor> BeforeCarrier;
        TWeakObjectPtr<AActor> BeforeRequesterInventoryItem;
        TWeakObjectPtr<UVistaAnimationComponent> Animation;
        FVistaActionTransactionRecord Record;
        FName ContactResultCode = NAME_None;
        double StartedAtSeconds = 0.0;
        bool bAnimationStarted = false;
        bool bAlignmentApplied = false;
    };

    TOptional<FActivePhysicalAction> ActiveAction;

    bool BeginPhysicalInteractionImpl(
        const FVistaPhysicalActionRequest& Request,
        FVistaActionTransactionRecord& OutRecord,
        bool bDevAutomationBypassesAnimationReadiness);

    static FString SemanticIdForActor(const AActor* Actor);
    static bool StableAnchorIdentity(
        const class ATargetPoint* Anchor,
        FString& OutOwnerSemanticId,
        FString& OutAnchorSemanticId);
    static void SetRejectedRecord(
        const FVistaPhysicalActionRequest& Request,
        FName Code,
        FVistaActionTransactionRecord& OutRecord);
    static bool CapturePickupPhysicalState(
        const AVistaPickupActor* Pickup,
        const AActor* InventoryCarrier,
        FVistaPickupPhysicalStateSnapshot& OutSnapshot);
    static bool PhysicalSnapshotsEquivalent(
        const FVistaPickupPhysicalStateSnapshot& Left,
        const FVistaPickupPhysicalStateSnapshot& Right);
    bool RestoreAndVerifyBeforePhysicalState(FName& OutCode);
    bool RejectNewRequest(
        const FVistaPhysicalActionRequest& SignatureRequest,
        const FVistaPhysicalActionRequest& EvidenceRequest,
        FName Code,
        FVistaActionTransactionRecord& OutRecord);

    void AdvanceApproach();
    void AdvanceAlign();
    void AdvanceAnimation();
    void AdvanceAfterContact();
    bool StartAnimation(FName& OutCode);
    bool CommitContact(FName& OutCode);
    void CompleteSuccess();
    void FinishFailure(EVistaActionTransactionStatus Status, FName Code);
    bool Transition(EVistaActionPhase Phase, FName Code);
    bool FinalizeActive(FVistaActionTransactionRecord* OutFinalRecord = nullptr);
    void AbandonActiveAfterPublishFailure();
    bool PublishRecord(bool bTerminal = false);
};
