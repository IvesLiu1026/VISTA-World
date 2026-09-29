#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Components/ActorComponent.h"
#include "GameFramework/Character.h"
#include "Dom/JsonObject.h"
#include "VistaCompanion.generated.h"

class UAudioComponent;
class USoundWaveProcedural;
class USpotLightComponent;
class UMaterialInstanceDynamic;
class SWidget;
class SEditableTextBox;
class IHttpRequest;

UCLASS(Transient)
class VISTAPHOTOREALREVIEW_API UVistaCompanionAnim : public UAnimInstance
{
    GENERATED_BODY()
public:
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
    virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) override;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AVistaCompanion : public ACharacter
{
    GENERATED_BODY()
public:
    AVistaCompanion();
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    void BuildPose(TArray<FTransform>& Out) const;
    void Speak(const TSharedPtr<FJsonObject>& Reply);
    void StopSpeech();
    bool PlaceNear(const AActor* Player);
    bool ResetForScene(const AActor* Player);
    bool BeginAssist(const FString& Target,AActor* Entity,FVector Control);
    void CancelAssist();
    FString AssistStatus=TEXT("idle"),AssistTarget,AssistId;
    float ContactError=0;
    TSharedPtr<FJsonObject> AssistDiagnostics() const;
    TWeakObjectPtr<ACharacter> Leader;
    bool bFollowing=true,bReady=false,bSpeaking=false,bBlocked=false;
    float AudioClock=0,MouthOpen=0,Travel=0;
    FString Subtitle;
private:
    UPROPERTY() TObjectPtr<UAudioComponent> Speech;
    UPROPERTY() TObjectPtr<USpotLightComponent> FaceFill;
    UPROPERTY() TObjectPtr<USoundWaveProcedural> Wave;
    UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> StatusMaterial;
    bool bRobotAppearance=false;
    TArray<FTransform> Idle,CurrentPose,ReferenceGlobal;
    TArray<TArray<FTransform>> Walk;
    TArray<int32> Parents;
    TArray<FVector> Trail;
    TArray<FVector> Mouth;
    FVector Previous,LastLeader,YieldGoal;
    float Cycle=143,Phase=0,MoveBlend=0,BlinkClock=0,StuckTime=0,YieldTime=0;
    int32 AudioBytes=0,Rate=24000,Head=INDEX_NONE,Spine=INDEX_NONE;
    TMap<FName,TArray<FName>> FaceMorphs;
    void Face(FName Name,float Value);
    void LoadMotion();
    void TickAssist(float Dt);
    void PoseAssist(float Dt);
    bool PlanAssistApproach();
    bool AssistChord(const FVector& Start,const FVector& End) const;
    bool HumanBlocksAssistChord(const FVector& Start,const FVector& End) const;
    TWeakObjectPtr<AActor> AssistEntity;
    FVector AssistControl,AssistGoal,AssistPrevious;
    float AssistClock=0,AssistReach=0,AssistContact=0,AssistStall=0;
    float AssistReachClock=0,AssistCheckClock=0,AssistPlanMs=0,AssistWaitClock=0,AssistLeanDegrees=0;
    TArray<FVector> AssistPath;
    int32 AssistPathIndex=0,AssistReplans=0,AssistCandidates=0,AssistFloorRejected=0,
        AssistBodyRejected=0,AssistReachRejected=0,AssistOccludedRejected=0,AssistExpanded=0,AssistHumanOccupied=0;
    bool bResumeFollow=true,bAssistHumanBlocksRoute=false;
};

UCLASS(ClassGroup=VISTA)
class VISTAPHOTOREALREVIEW_API UVistaCompanionComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UVistaCompanionComponent();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void TickComponent(float Dt,ELevelTick Tick,FActorComponentTickFunction* ThisTick) override;
    void TogglePanel();
    void ClosePanel();
    void Ask(const FString& Text);
    void Stop();
    void Follow(bool Enabled);
    void LiveRequest(const FString& Route,const FString& Text=TEXT(""),const FString& Target=TEXT(""));
    bool IsOpen() const {return bOpen;}
    bool IsEnabled() const {return Companion!=nullptr;}
    TSharedPtr<FJsonObject> State() const;
    UPROPERTY() TObjectPtr<AVistaCompanion> Companion;
    double NoticeUntil=0;
    FString Reply=TEXT("你好，我會陪你探索這六個房間。"),Status=TEXT("準備好了"),LastQuestion;
private:
    TSharedPtr<SWidget> Panel;
    TSharedPtr<SWidget> Captions;
    TSharedPtr<SEditableTextBox> Entry;
    TSharedPtr<IHttpRequest,ESPMode::ThreadSafe> Pending;
    TSharedPtr<FJsonObject> PanelObservation;
    FString Session,Endpoint=TEXT("http://127.0.0.1:49010"),ProofDir,LastRoom;
    bool bOpen=false,bBusy=false,bLive=false;
    int32 Serial=0;
    float PublishClock=0;
    double ObservationTime=0;
    void Start();
};
