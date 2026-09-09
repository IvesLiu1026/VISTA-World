#pragma once
#include "CoreMinimal.h"
#include "EmbodiedReview.h"
#include "VistaLiquidLedger.h"
#include "VistaVillaCharacter.generated.h"
class UNiagaraComponent;
class ACameraActor;
class UProceduralMeshComponent;
struct FVillaStreams;
struct FVillaStreamsDeleter {void operator()(FVillaStreams* Value) const;};

struct FVillaMotionFrame
{
    TArray<FTransform> Pose;
    float Phase=0,Speed=0;
    int32 Clip=0,SourceFrame=0;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AVistaVillaCharacter : public AEmbodiedReviewCharacter
{
    GENERATED_BODY()
public:
    AVistaVillaCharacter();
    virtual ~AVistaVillaCharacter() override;
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
    virtual void EmbodiedInteract() override;
    virtual void EmbodiedReset() override;
    virtual FString GetInteractionHint() const override;
    UFUNCTION(Exec) void VillaPour();
    UFUNCTION(Exec) void VillaTap();
    UFUNCTION(Exec) void VillaDemo();
protected:
    virtual void ModifyBaseBodyPose(TArray<FTransform>& LocalPose) override;
    virtual void UpdateInteraction(float Dt) override;
    virtual FTransform DesiredGrip() const override;
    virtual FTransform CarryTarget() const override;
    virtual void AdjustScenePoseGoals() override {SceneReachHipAdvance=bPouring?10.f:0.f;}
    virtual void OnPoseFinalized() override;
    virtual FVector FirstPersonReadyOffset(float Sign,float Swing) const override
    {return FVector(Sign*19.f,29.f+Swing*.15f,-22.f+.13f*FMath::Sin(Clock*1.4f));}
private:
    UPROPERTY() TObjectPtr<AStaticMeshActor> Jug;
    UPROPERTY() TObjectPtr<AStaticMeshActor> Mug;
    UPROPERTY() TObjectPtr<UNiagaraComponent> PourFluid;
    UPROPERTY() TObjectPtr<UNiagaraComponent> TapFluid;
    UPROPERTY() TObjectPtr<UProceduralMeshComponent> JugSurface;
    UPROPERTY() TObjectPtr<UProceduralMeshComponent> MugSurface;
    UPROPERTY() TObjectPtr<UProceduralMeshComponent> PourColumn;
    UPROPERTY() TObjectPtr<UProceduralMeshComponent> TapColumn;
    TUniquePtr<FVillaStreams,FVillaStreamsDeleter> Streams;
    double JugRenderedMl=0,MugRenderedMl=0;
    TArray<FVillaMotionFrame> Motions;
    TArray<FTransform> MotionBlend;
    VistaLiquid::Ledger Liquid,TapLedger;
    bool bPouring=false,bTap=false,bProof=false,bDemo=false;
    float PourClock=0,MotionWeight=0,LastFrameDt=0,ProofClock=0,DemoClock=0;
    int32 MotionIndex=INDEX_NONE,DemoStage=0,ProofFrames=0;
    FTransform PourStart;
    FVector PourOrigin=FVector(1220,-910,94);
    FVector TapOrigin=FVector(1080,-878,75);
    FString ProofDir;
    FString PendingCapture;
    bool bFinishAfterCapture=false;
    TArray<double> FrameTimes;
    double LastWallFrame=0;
    TArray<TSharedPtr<FJsonValue>> Records;
    FTransform JugInitial,MugInitial;
    bool bStairsPassed=false;
    int32 TourIndex=0;
    TArray<TWeakObjectPtr<ACameraActor>> TourCameras;
    bool bStairSetup=false,bTourReady=false,bTourCaptured=false;
    bool bEmptyCaptured=false,bDownCaptured=false,bPourCaptured=false,bFlightCaptured=false;
    bool bPlacedCaptured=false,bTapCaptured=false;
    void LoadMotionLibrary();
    void UpdateLiquids(float Dt);
    void AdvanceDemo(float Dt);
    void CaptureProof(const FString& Name);
    void CaptureProofNow(const FString& Name);
    void FinishProof();
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AVistaVillaHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AVistaVillaGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AVistaVillaGameMode();
};
