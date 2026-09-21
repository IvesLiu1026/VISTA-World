#pragma once

#include "CoreMinimal.h"
#include "Async/Future.h"
#include "VistaVillaCharacter.h"
#include "Dom/JsonObject.h"
#include "HomeActions.generated.h"

class ULightComponent;
class UAudioComponent;
class USoundWaveProcedural;
class USceneCaptureComponent2D;
class UTextureRenderTarget2D;

struct FHomeEntity
{
    FString Id, ShortId, Kind, Display, Room;
    TSharedPtr<FJsonObject> Spec, State;
    TWeakObjectPtr<AStaticMeshActor> Actor;
    TWeakObjectPtr<UStaticMeshComponent> Mesh;
    TArray<TWeakObjectPtr<AActor>> Children;
    FTransform Baseline, Closed;
    FVector ControlLocal = FVector::ZeroVector;
    float Aperture = 0.f;
    bool bBaselinePhysics = false;
};

struct FHomeBefore
{
    TSharedPtr<FJsonObject> State;
    FTransform Transform;
    FVector Velocity = FVector::ZeroVector;
    FVector AngularVelocity = FVector::ZeroVector;
    bool bPhysics = false;
    float Aperture = 0.f;
    ECollisionEnabled::Type Collision = ECollisionEnabled::QueryAndPhysics;
    FCollisionResponseContainer Responses;
    TWeakObjectPtr<USceneComponent> AttachParent;
    FName AttachSocket;
};

// Author/evaluator state. Never serialize this into a policy observation.
struct FHomeConcurrentEvent
{
    TSharedPtr<FJsonObject> Definition;
    FString TemplateId,Status=TEXT("running"),Terminal;
    float Started=0,Elapsed=0;
    TSet<FString> Interactions,WrittenEntities;
};

struct FHomeContactTriangle
{
    FVector A, B, C, Normal;
    FBox Bounds;
};
struct FHomeContactNode
{
    FBox Bounds;
    int32 Start=0, Count=0, Left=INDEX_NONE, Right=INDEX_NONE;
};
struct FHomeFineSurface
{
    TArray<FHomeContactTriangle> Triangles;
    TArray<FHomeContactNode> Nodes;
    TArray<FString> Fingers;
    FString Mode;
    bool bHorizontalPinch=false,bUseWideGrip=false;
    bool bSupportBothHands=false;
    TArray<FVector> GripPoints;
    FVector GripCenter=FVector::ZeroVector;
    float PinchRollDegrees=0.f;
    float MaximumError=.45f, Clearance=.12f, MaximumJointAngle=45.f;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AHomeActionsCharacter : public AVistaVillaCharacter
{
    GENERATED_BODY()
public:
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
    virtual void EmbodiedInteract() override;
    virtual void EmbodiedPlace() override;
    virtual void EmbodiedDrop() override;
    virtual void EmbodiedReset() override;
    virtual FString GetInteractionHint() const override;
    virtual void ReviewSnapshot() override;
    UFUNCTION(Exec) void HomeAction(const FString& Action,const FString& Target,const FString& Secondary=TEXT(""));
    UFUNCTION(Exec) void HomeEvent(const FString& EventId);
    UFUNCTION(Exec) void HomeEventAdd(const FString& EventId);
    UFUNCTION(Exec) void HomePhone(bool Enabled);
    UFUNCTION(Exec) void HomeNotice(const FString& Code);
    UFUNCTION(Exec) void HomeHumanSay(const FString& Code);
    UFUNCTION(Exec) void HomeState();
    UFUNCTION(Exec) virtual void HomeRoom(int32 Index);
    UFUNCTION(Exec) void HomeFocus(const FString& Target);
    UFUNCTION(Exec) void HomeCancel();
    UFUNCTION(Exec) void HomeObserve(bool Clean);
    bool HasSceneReady() const { return bSceneReady; }
    FString GetEventHint() const;
    bool IsCleanObservation() const { return bCleanObservation; }
    TArray<FString> VisibleActionIds() const { return AvailableActions(); }
    FString VisibleActionName(const FString& Id) const;
    void ExecuteVisibleAction(const FString& Id);
    bool CanLeaveSpace() const;
    TArray<TPair<FString,FString>> VisibleEvents() const;
    // A separate, visibility-filtered input for the conversational companion.
    // Never return the engineering state, task evaluator, or hidden event labels.
    TSharedPtr<FJsonObject> CompanionObservation(bool WearerView=false) const;
    TSharedPtr<FJsonObject> StreamingObservation() const;
    bool CommitCompanionOff(const FString& Target,AActor* Helper,const FVector& Finger,FString& Code);
protected:
    virtual bool UsesHomeActions() const override {return true;}
    virtual void SetView(FVector Position,FRotator Rotation) override;
    virtual void SetPhase(EEmbodiedPhase NewPhase) override;
    virtual void UpdateInteraction(float Dt) override;
    virtual void ReleaseCup(bool bDropped) override;
    virtual void CancelReach(const FString& Reason) override;
    virtual FTransform DesiredGrip() const override;
    virtual FTransform CarryTarget() const override;
    virtual bool FindPlacement(FVector& Location,FQuat& Rotation) const override;
    virtual FVector PickupAimPoint() const override;
    virtual void InteractionView(FVector& Eye, FRotator& Rotation) const override { ActionView(Eye, Rotation); }
    virtual void RefreshScenePoseGoals() override;
    virtual void AdjustScenePoseGoals() override;
    virtual FTransform AdjustedSceneHandGoal(FTransform Goal,bool bLeft=false) const override;
    virtual void OnPoseFinalized() override;
    virtual void RefineSceneBodyPose(TArray<FTransform>& LocalPose) override;
    virtual bool IsSceneContactReady(FString& Reason) const override;
private:
    // Enabled by a short-lived backend lease. No HUD, labels or evaluator data.
    void CaptureResearchViews();
    UPROPERTY() TObjectPtr<USceneCaptureComponent2D> ResearchEgo;
    UPROPERTY() TObjectPtr<USceneCaptureComponent2D> ResearchExo;
    UPROPERTY() TObjectPtr<AActor> ResearchObserver;
    UPROPERTY() TObjectPtr<UTextureRenderTarget2D> ResearchEgoTarget;
    UPROPERTY() TObjectPtr<UTextureRenderTarget2D> ResearchExoTarget;
    double ResearchNextCapture = 0;
    uint64 ResearchCaptureSerial = 0;
    TFuture<void> ResearchCaptureWrite;
    TSharedPtr<FJsonObject> Contract;
    TMap<FString,FHomeEntity> Entities;
    TMap<FString,FHomeBefore> Before;
    TMap<FString,TSharedPtr<FJsonObject>> Ledger;
    TMap<FString,FHomeConcurrentEvent> ConcurrentEvents;
    uint64 ConcurrentSerial=0;
    TMap<FName,TArray<FName>> HumanFaceMorphs;
    bool bPhoneCall=false,bStreamingEnabled=false;
    float PhoneBlend=0,DailyClock=0;
    FQuat PhoneRotation=FRotator(0,0,-90).Quaternion();
    FVector PhoneEarOffset=FVector(6,10,0);
    UPROPERTY() TObjectPtr<UAudioComponent> HumanVoice;
    UPROPERTY() TObjectPtr<USoundWaveProcedural> HumanWave;
    TArray<float> HumanMouth;
    float HumanMouthOpen=0;
    int32 HumanAudioBytes=0,HumanAudioRate=24000;
    void UpdateDailyMotion(float Dt);
    void PollPrivateReview();
    void PollLiveCommands();
    void DirectorCommand(const TSharedPtr<FJsonObject>& Request,FString& Code);
    void StopDirector();
    FString DirectorOwner,DirectorAction;
    double DirectorUntil=0;
    bool bDirectorThird=false,bDirectorWasClean=false;
    bool ApplyLiveScene(const FString& Layout,int32 Room,FString& Code);
    bool ApplyMicroScene(const TSharedPtr<FJsonObject>& Recipe,FString& Code);
    void ClearMicroScene();
    TMap<FString,FHomeEntity> ForgeOriginals;
    TSharedPtr<FJsonObject> ForgeReceipt;
    UPROPERTY() TArray<TObjectPtr<AActor>> ForgeActors;
    int32 ForgeSerial=0;
    UPROPERTY() TArray<TObjectPtr<AActor>> LiveDressing;
    void TickPrivateReview(float Dt);
    void PrivateDialogue(const FString& Role,const FString& Code);
    void ActionView(FVector& Eye,FRotator& View) const;
    bool bPrivateHumanLipSync=true;
    bool bPrivateMoving=false,bPrivateLooking=false;
    FVector PrivateTarget=FVector::ZeroVector,PrivatePrevious=FVector::ZeroVector;
    TArray<FVector> PrivatePath;
    FRotator PrivateLook=FRotator::ZeroRotator;
    float PrivateStall=0,PrivateMoveClock=0;
    float PrivatePreviewCm=0,PrivateClearance=95;
    int32 PrivateCornerFrames=0;
    FString PrivateMotion=TEXT("idle");
    void UpdateConcurrentEvents(float Dt);
    TArray<TSharedPtr<FJsonValue>> ConcurrentEventState() const;
    UPROPERTY() TMap<FString,TObjectPtr<AStaticMeshActor>> Effects;
    UPROPERTY() TMap<FString,TObjectPtr<UEmbodiedPoseLibrary>> HandProfiles;
    UPROPERTY() TObjectPtr<UEmbodiedPoseLibrary> DefaultPoses;
    UPROPERTY() TObjectPtr<ULightComponent> FloorLight;
    UPROPERTY() TMap<FString,TObjectPtr<UMaterialInterface>> DeviceMaterials;
    TSet<FString> Interactions;
    TSet<FString> ProcessedRequests;
    TSharedPtr<FJsonObject> Transaction;
    TMap<FName,FVector> FineTipOffsets;
    TMap<FName,FVector> FineFlexionAxes,FineSpreadAxes;
    TMap<FString,FHomeFineSurface> FineSurfaces;
    TSharedPtr<FJsonObject> FineContactSnapshot;
    FString FineWristEntity;
    FVector FineWristCorrection[2] = {FVector::ZeroVector,FVector::ZeroVector};
    bool bFineContacts=false;
    bool LoadFineContacts();
    const FHomeEntity* FineContactEntity() const;
    bool FineLeftRequired(const FHomeEntity& Entity) const;
    FTransform FinePinchWrist(const FHomeEntity& Entity) const;
    void MeasureFineContacts();
    bool ClosestFineSurface(const FHomeFineSurface& Surface,const FVector& Point,FVector& Closest,FVector& Normal) const;
    FString Revision, BridgeDir, SessionId;
    FString ActiveId, ActionId, TargetId, SecondaryId, HeldId, SeatId;
    FString StandingOn;
    FString FocusId, LastCode, EventId, EventStatus=TEXT("inactive"), TerminalCondition;
    FString CommandSignature;
    int32 Generation=0, SceneEpoch=0, SelectedAction=0, EventIndex=-1;
    float ActionTime=0.f, EventTime=0.f, BridgeClock=0.f, SceneClock=0.f;
    float ActionStartAperture=0.f, ActionEndAperture=0.f;
    float RightContactError=0.f, LeftContactError=0.f;
    float ContactMaximum=0.f;
    int32 ActionStage=0;
    float FineSupportLossTime=0.f;
    int32 FineSupportSamples=0;
    bool bSceneReady=false, bPhysicalAction=false, bCommitted=false, bSuppressReceipt=false;
    bool bCleanObservation=false, bControlHeld=false, bJog=false, bSprint=false;
    FTransform ActionHandStart, ActionHandEnd, LeftRelativeToItem, ControlHandRelative;
    FTransform ActorBefore, ItemBefore, ActionBodyStart;
    FVector ActionRootEnd=FVector::ZeroVector;
    FVector StorageEntry=FVector::ZeroVector;
    FVector ClimbFeetStart[2];
    FVector LastItemVelocity=FVector::ZeroVector;
    float LocomotionTime=0.f;
    FVector SpillPosition=FVector::ZeroVector;
    TMap<FString,FVector> PreviousVelocities;
    TMap<FString,float> PendingImpacts;
    float HazardCooldown=0.f;
    TArray<FString> AvailableActions() const;
    void UpdateFocus();
    void NextAction();
    void PreviousAction();
    void InspectFocus();
    void NextEvent();
    void ToggleCrouch();
    void ToggleBackpack();
    void JogOn();
    void JogOff();
    FHomeEntity* Resolve(const FString& Name);
    const FHomeEntity* Resolve(const FString& Name) const;
    FVector ControlPoint(const FHomeEntity& Entity) const;
    FTransform WristAt(const FVector& Contact,bool bLeft=false,bool bPoint=false,FVector Axis=FVector::UpVector,bool bTop=false) const;
    FVector FingerOffset(bool bLeft) const;
    bool CheckReach(const FHomeEntity& Entity,const FVector& Point,FString& Code,bool bRequireView=true) const;
    bool BeginAction(const FString& Command,const FString& Action,const FString& Target,const FString& Secondary,FString& Code);
    void CaptureBefore();
    bool RestoreBefore();
    void FinishAction(bool bSuccess,const FString& Code);
    bool CommitAction(FString& Code);
    void UpdateSemanticAction(float Dt);
    void UpdateClimb(float Dt);
    void ApplyAperture(FHomeEntity& Entity,float Value);
    void SelectPickup(FHomeEntity& Entity);
    void UpdatePresentation(float Dt);
    void UpdatePhysicalConsequences(float Dt);
    void SpillLiquid(FHomeEntity& Entity,const FString& Cause);
    void UpdateEvent(float Dt);
    bool StartEvent(const FString& Id,FString& Code,bool bReset=true);
    bool ResetScene(FString& Code);
    bool EvaluateCondition(const TSharedPtr<FJsonObject>& Condition,const FHomeConcurrentEvent* Context=nullptr) const;
    FString RoomAt(const FVector& Location) const;
    FVector ScenePoint(const FString& Room,const FVector& Legacy) const;
    void RoomOne() {HomeRoom(1);}
    void RoomTwo() {HomeRoom(2);}
    void RoomThree() {HomeRoom(3);}
    void RoomFour() {HomeRoom(4);}
    void RoomFive() {HomeRoom(5);}
    void RoomSix() {HomeRoom(6);}
    void PollBridge();
    void PublishState();
    void AppendReceipt(const TSharedPtr<FJsonObject>& Record);
    TSharedRef<FJsonObject> MakeState() const;
    void Reply(const TSharedPtr<FJsonObject>& Request,const FString& Code);
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AHomeActionsHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AHomeActionsGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AHomeActionsGameMode();
};

UCLASS()
class VISTAPHOTOREALREVIEW_API UHomeActionsAuthoring : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable,Category="HomeActions") static bool ConfigurePickup(UStaticMesh* Mesh,const FString& Kind);
    UFUNCTION(BlueprintCallable,Category="HomeActions") static FVector StaticSupportPoint(AStaticMeshActor* Actor,FVector Point);
    UFUNCTION(BlueprintCallable,Category="HomeActions") static bool MirrorHandPoses(USkeletalMesh* Mesh,UEmbodiedPoseLibrary* Library);
};
