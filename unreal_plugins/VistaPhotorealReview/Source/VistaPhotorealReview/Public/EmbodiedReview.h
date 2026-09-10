#pragma once

#include "CoreMinimal.h"
#include "PhotorealReview.h"
#include "Animation/AnimInstance.h"
#include "Engine/DataAsset.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "EmbodiedReview.generated.h"

class UPhysicsHandleComponent;
class USpringArmComponent;
class USkeletalMeshComponent;
class UStaticMeshComponent;
class AStaticMeshActor;
class UStaticMesh;
class USkeletalMesh;
struct FEmbodiedFirstPersonProof;

UCLASS()
class VISTAPHOTOREALREVIEW_API UEmbodiedPoseLibrary : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere,Category="Embodied") TArray<FName> BoneNames;
    UPROPERTY(EditAnywhere,Category="Embodied") TArray<FTransform> Rest;
    UPROPERTY(EditAnywhere,Category="Embodied") TArray<FTransform> Relaxed;
    UPROPERTY(EditAnywhere,Category="Embodied") TArray<FTransform> OpenHand;
    UPROPERTY(EditAnywhere,Category="Embodied") TArray<FTransform> Grip;
    UPROPERTY(EditAnywhere,Category="Embodied") FTransform WristRelativeToCup;
    UPROPERTY(EditAnywhere,Category="Embodied") float ContactReferenceHeightCm = 6.2f;
};

UCLASS(Transient)
class VISTAPHOTOREALREVIEW_API UEmbodiedBodyAnimInstance : public UAnimInstance
{
    GENERATED_BODY()
public:
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
    virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) override;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API UEmbodiedAuthoringLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable,Category="Embodied") static bool ConfigureCupMesh(UStaticMesh* Mesh);
    UFUNCTION(BlueprintCallable,Category="Embodied") static bool PreparePoseLibrary(USkeletalMesh* Mesh,UEmbodiedPoseLibrary* Library);
};

UENUM()
enum class EEmbodiedPhase : uint8 { Idle, Reaching, Closing, Held, Placing, Releasing, Retracting };

struct FEmbodiedFoot
{
    FVector Planted = FVector::ZeroVector;
    FVector Start = FVector::ZeroVector;
    FVector Goal = FVector::ZeroVector;
    FVector Current = FVector::ZeroVector;
    float Progress = 1.f;
    float Yaw = 0.f;
    float Duration = .4f;
    bool bMovingStep = false;
    float Roll = 0.f;
    FVector ToeGoal = FVector::ZeroVector;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AEmbodiedReviewCharacter : public APhotorealReviewCharacter
{
    GENERATED_BODY()
    friend struct FEmbodiedFirstPersonProof;
public:
    AEmbodiedReviewCharacter();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
    virtual void ReviewSnapshot() override;
    void BuildBodyPose(TArray<FTransform>& LocalPose);
    UFUNCTION(Exec) void EmbodiedState();
    UFUNCTION(Exec) void EmbodiedBones();
    UFUNCTION(Exec) void EmbodiedTrace(float Seconds);
    UFUNCTION(Exec) void EmbodiedTestStand(float HeightCm,float CupYaw);
    UFUNCTION(Exec) void EmbodiedPosition(float X,float Y,float Z,float Yaw);
    UFUNCTION(Exec) void EmbodiedView(int32 View);
    UFUNCTION(Exec) virtual void EmbodiedReset();
    UFUNCTION(Exec) void EmbodiedInspect(int32 View);
    UFUNCTION(Exec) void EmbodiedCup(float X, float Y, float Z, float Yaw);
    UFUNCTION(Exec) void EmbodiedCamera(float Pitch, float Yaw);
    UFUNCTION(Exec) virtual void EmbodiedInteract();
    UFUNCTION(Exec) virtual void EmbodiedDrop();
    UFUNCTION(Exec) virtual void EmbodiedPlace();
    virtual FString GetInteractionHint() const;
    bool IsThirdPerson() const { return bThirdPerson; }
    EEmbodiedPhase GetPhase() const { return Phase; }
    UPROPERTY() TObjectPtr<UEmbodiedPoseLibrary> Poses;
    UPROPERTY() TObjectPtr<USkeletalMeshComponent> OwnerBody;
    UPROPERTY() TObjectPtr<USpringArmComponent> FollowBoom;
    UPROPERTY() TObjectPtr<UCameraComponent> FollowCamera;
    UPROPERTY() TObjectPtr<UPhysicsHandleComponent> GripHandle;
protected:
    UPROPERTY() TObjectPtr<AStaticMeshActor> Cup;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> CupMesh;
    UPROPERTY() TObjectPtr<AStaticMeshActor> TestStand;
    EEmbodiedPhase Phase = EEmbodiedPhase::Idle;
    bool bThirdPerson = false;
    bool bFeetReady = false;
    bool bReady = false;
    bool bHasCandidate = false;
    float PhaseTime = 0.f;
    float ReachAlpha = 0.f;
    float FingerAlpha = 0.f;
    float RetractFrom = 0.f;
    float Clock = 0.f;
    float TraceRemaining = 0.f;
    bool bCapturePending = false;
    FDelegateHandle BoneFinalizedHandle;
    float HandErrorCm = 0.f;
    float HandAngleDeg = 0.f;
    float MaxHeldError = 0.f;
    float UnreachableTime = 0.f;
    float StepClock = 0.f;
    float TurnOffset = 0.f;
    float FirstPersonRestAlpha = 0.f;
    bool bFirstPersonRestObstructed = false;
    int32 NextFoot = 0;
    int32 CompletedPickups = 0;
    int32 CompletedPlacements = 0;
    int32 CompletedDrops = 0;
    int32 CancelledActions = 0;
    int32 TransitionSerial = 0;
    FVector PreviousLocation = FVector::ZeroVector;
    FVector ReachStart = FVector::ZeroVector;
    bool bAllowReachDetour = false;
    bool bReachDetour = false;
    bool bSceneCarryLift = false;
    FVector ReachViaA = FVector::ZeroVector;
    FVector ReachViaB = FVector::ZeroVector;
    FVector PlaceLocation = FVector::ZeroVector;
    FQuat PlaceRotation = FQuat::Identity;
    FTransform HandRelativeToCup;
    FTransform LastHandGoal;
    FTransform InitialCupTransform;
    FTransform HoldStart;
    // Optional scene action presentation, zeroed for the original cup review.
    bool bSceneActionBusy = false;
    float LeftReachAlpha = 0.f;
    float LeftFingerAlpha = 0.f;
    float CrouchAlpha = 0.f;
    float SeatedAlpha = 0.f;
    float FallAlpha = 0.f;
    float SceneReachHipAdvance = 0.f;
    bool bSceneFeetOverride = false;
    FVector SceneFootWorld[2];
    FVector SeatPelvisWorld = FVector::ZeroVector;
    FTransform LeftHandGoal;
    float ItemRadius = 3.7f;
    float ItemHeight = 9.6f;
    virtual void RefreshScenePoseGoals() {}
    virtual void AdjustScenePoseGoals() {}
    virtual FTransform AdjustedSceneHandGoal(FTransform Goal,bool bLeft=false) const { return Goal; }
    FQuat HoldRelativeRotation = FQuat::Identity;
    FEmbodiedFoot Feet[2];
    TArray<FTransform> ReferenceGlobal;
    TArray<int32> Parents;
    TMap<FName,int32> BoneIndex;
    FString Feedback;
    float FeedbackUntil = 0.f;
    void ToggleView();
    void ViewCup() { EmbodiedInspect(0); }
    virtual void SetPhase(EEmbodiedPhase NewPhase);
    void FeedbackMessage(const FString& Text);
    virtual void UpdateFeet(float DeltaSeconds);
    virtual void UpdateBodyFacing(float DeltaSeconds);
    void UpdateFirstPersonRest(float DeltaSeconds);
    virtual void UpdateInteraction(float DeltaSeconds);
    virtual void ReleaseCup(bool bDropped);
    virtual void CancelReach(const FString& Reason);
    bool IsCupReachable(FString& Reason) const;
    virtual FVector PickupAimPoint() const;
    virtual bool FindPlacement(FVector& Location, FQuat& Rotation) const;
    virtual FTransform DesiredGrip() const;
    virtual FTransform CarryTarget() const;
    void MeasureContact();
    virtual void OnPoseFinalized();
    virtual void RefineSceneBodyPose(TArray<FTransform>& LocalPose) {}
    virtual void ModifyBaseBodyPose(TArray<FTransform>& LocalPose) {}
    virtual bool WantsFirstPersonReadyPose() const { return true; }
    virtual bool PreserveUnoccupiedArmPose() const { return false; }
    virtual float UnoccupiedFingerCurl() const { return 0.f; }
    virtual void AdjustFirstPersonEyeTarget(FVector& EyeTarget) const {}
    virtual bool PreserveMotionFootRotation() const { return false; }
    virtual float ProceduralGaitWeight() const { return 1.f; }
    virtual bool UsesGroundFootIK() const { return true; }
    virtual float UnoccupiedMovementSpeed() const { return 125.f; }
    virtual FVector FirstPersonReadyOffset(float Sign,float Swing) const
    {return FVector(Sign*22.f,30.f+Swing*.18f,-10.f+.15f*FMath::Sin(Clock*1.4f+(Sign<0?.35f:0.f)));}
    virtual bool IsSceneContactReady(FString& Reason) const { return true; }
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AEmbodiedReviewHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AEmbodiedReviewGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AEmbodiedReviewGameMode();
};
