#pragma once

#include "CoreMinimal.h"
#include "HomeActions.h"
#include "VistaExplorer.generated.h"

class UBoxComponent;
class AVistaCampusVehicle;

struct FVistaSceneChoice
{
    FString Id, Title, Detail, Map;
    bool bAvailable=false;
};

// A swept, ground-following arcade vehicle. Not a tyre or traffic safety simulator.
UCLASS()
class VISTAPHOTOREALREVIEW_API AVistaCampusVehicle : public AActor
{
    GENERATED_BODY()
public:
    AVistaCampusVehicle();
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    UPROPERTY(VisibleAnywhere,BlueprintReadOnly,Category="Campus") TObjectPtr<UBoxComponent> Collision;
    UPROPERTY(VisibleAnywhere,BlueprintReadOnly,Category="Campus") TObjectPtr<UStaticMeshComponent> Body;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Campus") bool bScooter=false;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Campus") bool bTraffic=false;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Campus") FString VehicleId;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Campus") TObjectPtr<UStaticMesh> WheelAsset;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Campus") TObjectPtr<UStaticMesh> SteeringAsset;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Campus") TObjectPtr<UStaticMesh> DoorAsset;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Campus") float CruiseSpeed=350.f;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="Campus") float RouteHalfLength=7000.f;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Wheels;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> SteeringPart;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> DoorPart;
    TWeakObjectPtr<class AVistaExplorerCharacter> Driver;
    float Speed=0, Steering=0, Travel=0;
    float ThrottleInput=0;
    int32 Contacts=0;
    bool bBrake=true;
    void Drive(float Throttle,float Steer,bool Brake,float Dt);
    FVector SeatPoint() const;
    FVector GripPoint(bool Left) const;
    FQuat GripRotation() const;
    float GripSurface(FVector WorldPoint,bool Left,FVector& ClosestWorld) const;
    void SetDoor(float Alpha);
    bool FindExit(FVector& Out) const;
private:
    FVector RouteStart;
    float RouteYaw=0, WheelAngle=0;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AVistaExplorerCharacter : public AHomeActionsCharacter
{
    GENERATED_BODY()
public:
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
    virtual void EmbodiedInteract() override;
    virtual void EmbodiedDrop() override;
    virtual void EmbodiedReset() override;
    virtual void CalcCamera(float Dt,FMinimalViewInfo& Out) override;
    virtual FString GetInteractionHint() const override;
    UFUNCTION(Exec) void ExplorerMenu();
    UFUNCTION(Exec) void ExplorerActions();
    UFUNCTION(Exec) void ExplorerScene(const FString& Id);
    UFUNCTION(Exec) void ExplorerState();
    void ActivateMenuItem(FName Item);
    int32 Menu=0; // 0 play, 1 scenes/help, 2 context actions
    bool bCampus=false;
    TArray<FVistaSceneChoice> Scenes;
    FString SceneTitle;
    TWeakObjectPtr<AVistaCampusVehicle> Riding, Nearby;
    float SignalClock=0;
    bool WalkSignal() const;
    FString CrossingStatus;
    int32 CrossingCount=0, RedEntries=0;
    bool bChangingScene=false;
    FString RidePhase=TEXT("on_foot");
    float RideProgress=0;
protected:
    virtual bool UsesReviewBookmarks() const override { return false; }
    virtual void UpdateInteraction(float Dt) override;
    virtual void RefreshScenePoseGoals() override;
    virtual void UpdateBodyFacing(float Dt) override;
    virtual float ReachTorsoLeanScale() const override {return Riding.IsValid()?.20f:1.f;}
    virtual void RefineSceneBodyPose(TArray<FTransform>& LocalPose) override;
    virtual void OnPoseFinalized() override;
private:
    void TickRideTransition(float Dt);
    FTransform VehicleHandGoal(bool Left) const;
    FVector RideStart, RideApproach, RideExit, StartPelvis, StartFeet[2];
    FQuat RideStartRotation;
    float RideElapsed=0, FootPlant=1;
    double LastPoseClock=-1;
    TMap<FName,FVector> VehicleTipOffsets;
    TMap<FName,FVector> VehicleFlexAxes;
    void SetMenu(int32 Value);
    void BindExploreKeys(UInputComponent* Input);
    void ToggleExplorerView();
    void ExplorerJump();
    void ExplorerRun();
    void ExplorerWalk();
    void TickTrafficSignals(float Dt);
    void PublishExplorerState();
    bool bRun=false, bInCrossing=false;
    float PublishClock=0, EntrySide=0, CrossY=0;
    FString ProofDir;
    TArray<TWeakObjectPtr<AStaticMeshActor>> GreenLamps, RedLamps;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AVistaExplorerHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
    virtual void NotifyHitBoxClick(FName BoxName) override;
};

UCLASS()
class VISTAPHOTOREALREVIEW_API AVistaExplorerGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AVistaExplorerGameMode();
};
