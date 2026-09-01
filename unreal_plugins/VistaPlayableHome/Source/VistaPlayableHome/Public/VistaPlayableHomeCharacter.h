#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "VistaItemCarrier.h"
#include "VistaPlayableHomeTypes.h"
#include "VistaPlayableHomeCharacter.generated.h"

class AVistaPickupActor;
class APlayerCameraManager;
class UCameraComponent;
class UInputAction;
class UInputMappingContext;
class USceneComponent;
class USpringArmComponent;
class UVistaActionExecutorComponent;
class UVistaAnimationComponent;
class UVistaCharacterProviderComponent;
class UVistaInteractionComponent;
class UVistaPostureComponent;
struct FMinimalViewInfo;
struct FInputActionValue;

/** Bounded player-facing projection of one interaction result. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaPlayerActionFeedback
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Presentation")
    bool bVisible = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Presentation")
    bool bTerminal = true;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Presentation")
    EVistaInteractionStatus Status = EVistaInteractionStatus::Rejected;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Presentation")
    EVistaActionPhase Phase = EVistaActionPhase::Idle;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Presentation")
    FName Code = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Presentation")
    FString SemanticId;
};

/** Safe, read-only information exposed while the local player inspects a target. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaInspectionStateRow
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Inspection")
    FName Key = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Inspection")
    FString Value;
};

/** Safe, read-only information exposed while the local player inspects a target. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaInspectionPresentation
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Inspection")
    bool bActive = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Inspection")
    FString SemanticId;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Inspection")
    TArray<EVistaAffordance> Affordances;

    /** Closed allow-list projection; arbitrary actor state is never copied here. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Inspection")
    TArray<FVistaInspectionStateRow> PublicState;
};

/** One locally-derived executable action; actors remain the transaction targets. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaPlayerActionOption
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action Selector")
    EVistaAffordance Affordance = EVistaAffordance::Inspect;

    /** Mutation target: the focused actor, or the held source for Place/Pour. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action Selector")
    TObjectPtr<AActor> Target = nullptr;

    /** Pour receiver or Place owner; forbidden for single-target actions. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action Selector")
    TObjectPtr<AActor> SecondaryTarget = nullptr;

    bool Matches(const FVistaPlayerActionOption& Other) const
    {
        return Affordance == Other.Affordance && Target == Other.Target &&
            SecondaryTarget == Other.SecondaryTarget;
    }
};

/** Closed, measured settings for the realistic-interior gameplay camera. */
USTRUCT(BlueprintType)
struct VISTAPLAYABLEHOME_API FVistaIndoorCameraProfile
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    FName ProfileId = NAME_None;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    float TargetBoomLengthCm = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    float FieldOfViewDegrees = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    FVector SocketOffsetCm = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    float CollisionProbeSizeCm = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    float CameraLagSpeed = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    float CameraLagMaxDistanceCm = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    float CollisionRecoverySpeed = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    float RecoverySnapThresholdCm = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    float NearCameraHideDistanceCm = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    float NearCameraShowDistanceCm = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    bool bEnableCameraCollision = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    bool bEnableCameraLag = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    bool bEnableCameraLagSubstepping = false;

    static FVistaIndoorCameraProfile RealisticInteriorR2();
    bool IsValid(FString& OutReason) const;
};

UCLASS(Blueprintable)
class VISTAPLAYABLEHOME_API AVistaPlayableHomeCharacter final
    : public ACharacter,
      public IVistaItemCarrier
{
    GENERATED_BODY()

public:
    AVistaPlayableHomeCharacter();

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Identity")
    FString SemanticId = TEXT("home.r1/player.01");

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    TObjectPtr<USpringArmComponent> CameraBoom;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Camera")
    TObjectPtr<UCameraComponent> FollowCamera;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Interaction")
    TObjectPtr<UVistaInteractionComponent> InteractionComponent;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Animation")
    TObjectPtr<UVistaAnimationComponent> AnimationComponent;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Action")
    TObjectPtr<UVistaActionExecutorComponent> ActionExecutorComponent;

    /** Shared authority for sit, seated-idle, and stand transitions. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Posture")
    TObjectPtr<UVistaPostureComponent> PostureComponent;

    /**
     * Visual-only provider. Gameplay, collision and input remain on this
     * character while the reviewed Vivian assembly mirrors the Manny pose.
     */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Character Provider")
    TObjectPtr<UVistaCharacterProviderComponent> CharacterProviderComponent;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "VISTA|Carry")
    TObjectPtr<USceneComponent> CarryAnchor;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Input")
    TObjectPtr<UInputMappingContext> DefaultMappingContext;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Input")
    TObjectPtr<UInputAction> MoveAction;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Input")
    TObjectPtr<UInputAction> LookAction;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Input")
    TObjectPtr<UInputAction> JumpAction;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Input")
    TObjectPtr<UInputAction> SprintAction;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Input")
    TObjectPtr<UInputAction> CrouchAction;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Input")
    TObjectPtr<UInputAction> InteractAction;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Input")
    TObjectPtr<UInputAction> DropAction;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Input")
    TObjectPtr<UInputAction> InspectAction;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Input")
    TObjectPtr<UInputAction> ExitInspectAction;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Movement")
    float WalkSpeed = 350.0f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Movement")
    float SprintSpeed = 600.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "VISTA|Location")
    FString CurrentRoomId;

    UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "VISTA|Camera")
    FName ActiveCameraProfileId = TEXT("legacy_r1");

    UFUNCTION(BlueprintPure, Category = "VISTA|Carry")
    AVistaPickupActor* GetHeldPickup() const { return HeldItem; }

    UFUNCTION(BlueprintCallable, Category = "VISTA|Interaction")
    FVistaInteractionResult PerformDefaultInteraction();

    /** Explicit typed player path for appliance UI/input bindings. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Interaction")
    FVistaInteractionResult PerformFocusedApplianceInteraction(
        EVistaAffordance Affordance);

    /** Read-only resolver shared by input handling and player-facing prompts. */
    EVistaAffordance GetDefaultInteractionAffordance(AActor* Target) const;

    UFUNCTION(BlueprintCallable, Category = "VISTA|Carry")
    FVistaInteractionResult DropHeldItem();

    /** Explicit secondary action; it never substitutes for the E-key resolver. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Inspection")
    FVistaInteractionResult PerformInspectInteraction();

    UFUNCTION(BlueprintCallable, Category = "VISTA|Inspection")
    void ExitInspection();

    UFUNCTION(BlueprintPure, Category = "VISTA|Inspection")
    bool IsInspectionActive() const { return InspectionPresentation.bActive; }

    const FVistaInspectionPresentation& GetInspectionPresentation() const
    {
        return InspectionPresentation;
    }

    const FVistaPlayerActionFeedback& GetActionFeedback() const
    {
        return ActionFeedback;
    }

    bool IsActionFeedbackVisible() const;

    /** True only when the focused actor explicitly advertises Inspect. */
    bool CanInspectFocusedActor() const;

    /**
     * Closed, deterministic action projection for the current focus, held item,
     * and posture. Options that already fail known local preconditions are
     * omitted; the authoritative executor still revalidates at execution time.
     */
    TArray<FVistaPlayerActionOption> BuildExecutablePlayerActions() const;

    const TArray<FVistaPlayerActionOption>& GetExecutablePlayerActions() const
    {
        return ExecutablePlayerActions;
    }

    bool GetSelectedPlayerAction(FVistaPlayerActionOption& OutAction) const;

    int32 GetSelectedPlayerActionIndex() const
    {
        return SelectedPlayerActionIndex;
    }

    /** Authority-only direct entry used by the local selector and server RPC. */
    FVistaInteractionResult PerformSelectedPlayerAction();

    /** Applies all camera settings atomically after closed-range validation. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Camera")
    bool ApplyIndoorCameraProfile(const FVistaIndoorCameraProfile& Profile);

    virtual USceneComponent* VistaGetCarryAnchor_Implementation() const override;
    virtual AActor* VistaGetHeldItem_Implementation() const override;
    virtual bool VistaTryClaimItem_Implementation(AActor* Item) override;
    virtual void VistaReleaseItem_Implementation(AActor* Item) override;

    virtual void GetLifetimeReplicatedProps(
        TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void CalcCamera(
        float DeltaTime,
        FMinimalViewInfo& OutResult) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void UnPossessed() override;
    virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
    virtual bool CanCrouch() const override;
    virtual bool CanJumpInternal_Implementation() const override;

private:
    UPROPERTY(Replicated)
    TObjectPtr<AVistaPickupActor> HeldItem = nullptr;

    bool bSprinting = false;
    bool bIndoorViewLimitsApplied = false;
    TWeakObjectPtr<APlayerCameraManager> IndoorViewCameraManager;
    float PreviousViewPitchMin = 0.0f;
    float PreviousViewPitchMax = 0.0f;
    float PreviousViewRollMin = 0.0f;
    float PreviousViewRollMax = 0.0f;
    float NearCameraHideDistanceCm = 0.0f;
    float NearCameraShowDistanceCm = 0.0f;
    bool bNearCameraVisualHidden = false;

    UPROPERTY(Transient)
    FVistaInspectionPresentation InspectionPresentation;

    UPROPERTY(Transient)
    FVistaPlayerActionFeedback ActionFeedback;

    /** Local presentation cache rebuilt from authoritative replicated state. */
    UPROPERTY(Transient)
    TArray<FVistaPlayerActionOption> ExecutablePlayerActions;

    int32 SelectedPlayerActionIndex = INDEX_NONE;

    TWeakObjectPtr<AActor> InspectedTarget;
    /** Target whose Inspect presentation waits for the typed montage to finish. */
    TWeakObjectPtr<AActor> PendingInspectionTarget;
    FRotator PreInspectionControlRotation = FRotator::ZeroRotator;
    double InspectionStartedAtSeconds = 0.0;
    double ActionFeedbackExpiresAtSeconds = 0.0;
    FName PendingPresentationCommandId = NAME_None;
    EVistaActionPhase LastPresentedActionPhase = EVistaActionPhase::Idle;
    EVistaActionTransactionStatus LastPresentedTransactionStatus =
        EVistaActionTransactionStatus::Idle;
    FName LastPresentedTransactionCode = NAME_None;

    void Move(const FInputActionValue& Value);
    void Look(const FInputActionValue& Value);
    bool HasStandingControlAuthority() const;
    void SetSprinting(bool bEnabled);
    void BeginSprint();
    void EndSprint();
    void BeginCrouch();
    void EndCrouch();
    void InteractPressed();
    void DropPressed();
    void InspectPressed();
    void ExitInspectPressed();
    void CyclePlayerActionNextPressed();
    void CyclePlayerActionPreviousPressed();
    void ExecuteSelectedPlayerActionPressed();
    void MoveForwardLegacy(float Value);
    void MoveRightLegacy(float Value);
    void LookYawLegacy(float Value);
    void LookPitchLegacy(float Value);
    void ApplyRequestedCameraProfile();
    void ConfigureIndoorViewLimits();
    void RestoreIndoorViewLimits();
    void UpdateNearCameraVisualOcclusion(const FVector& CameraLocation);
    void SetNearCameraVisualHidden(bool bHidden);
    void RestoreNearCameraVisualOcclusion();
    void BeginInspectionPresentation(
        AActor* Target,
        const FVistaInspectionPresentation& Presentation);
    void UpdateInspectionFocus();
    void SetActionFeedbackLocal(const FVistaPlayerActionFeedback& Feedback);
    void PublishInteractionResult(
        const FVistaInteractionResult& Result,
        EVistaActionPhase Phase = EVistaActionPhase::Complete,
        bool bTerminal = true);
    void PublishTransactionFeedback(const FVistaActionTransactionRecord& Record);
    void UpdatePendingActionFeedback();
    void RefreshPlayerActionSelection();
    void CyclePlayerAction(int32 Direction);
    int32 FindDefaultPlayerActionIndex(
        const TArray<FVistaPlayerActionOption>& Options) const;
    FVistaInteractionResult PerformPlayerAction(
        const FVistaPlayerActionOption& Action);
    FVistaInteractionResult PerformRequestedPlayerAction(
        EVistaAffordance Affordance,
        AActor* Target,
        AActor* SecondaryTarget);
    void PresentStartedPlayerAction(const FVistaInteractionResult& Result);
    FVistaInteractionResult BeginAnimatedInspectInteraction();
    bool CancelPendingAnimatedInspection(FName Reason);
    void PresentCompletedInspection(
        AActor* Target,
        const FVistaEntityRuntimeState& InspectedState);
    FVistaInteractionResult BeginPhysicalInteraction(
        AActor* PhysicalTarget,
        EVistaAffordance Affordance,
        AActor* PlacementOwner = nullptr,
        const FVector& ReleaseVelocity = FVector::ZeroVector);
    FVistaInteractionResult BeginSemanticInteraction(
        AActor* Target,
        EVistaAffordance Affordance,
        AActor* SecondaryTarget = nullptr);

    UFUNCTION(Server, Reliable)
    void ServerPerformDefaultInteraction();

    UFUNCTION(Server, Reliable)
    void ServerDropHeldItem();

    UFUNCTION(Server, Reliable)
    void ServerPerformInspectInteraction();

    UFUNCTION(Server, Reliable)
    void ServerCancelPendingInspection();

    UFUNCTION(Server, Reliable)
    void ServerPerformSelectedPlayerAction(
        EVistaAffordance Affordance,
        AActor* Target,
        AActor* SecondaryTarget);

    UFUNCTION(Client, Reliable)
    void ClientBeginInspectionPresentation(
        AActor* Target,
        const FVistaInspectionPresentation& Presentation);

    UFUNCTION(Client, Reliable)
    void ClientPresentInteractionFeedback(
        const FVistaPlayerActionFeedback& Feedback);

    UFUNCTION(Server, Reliable)
    void ServerSetSprinting(bool bEnabled);
};
