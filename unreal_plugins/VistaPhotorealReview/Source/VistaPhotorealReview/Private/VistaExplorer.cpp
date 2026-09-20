#include "VistaExplorer.h"
#include "VistaCompanion.h"
#include "HomeActionsJson.h"
#include "Camera/CameraComponent.h"
#include "Camera/CameraTypes.h"
#include "Camera/PlayerCameraManager.h"
#include "VistaCameraClearance.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Canvas.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "TimerManager.h"
#include "UObject/Package.h"
#include "UnrealClient.h"

using namespace HomeJson;

AVistaCampusVehicle::AVistaCampusVehicle()
{
    PrimaryActorTick.bCanEverTick=true;
    Collision=CreateDefaultSubobject<UBoxComponent>(TEXT("VehicleCollision"));SetRootComponent(Collision);
    Collision->SetBoxExtent(FVector(212,88,67));Collision->SetCollisionProfileName(TEXT("BlockAllDynamic"));
    Body=CreateDefaultSubobject<UStaticMeshComponent>(TEXT("VehicleBody"));Body->SetupAttachment(Collision);
    Body->SetRelativeLocation(FVector(0,0,-67));Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}
void AVistaCampusVehicle::BeginPlay()
{
    Super::BeginPlay();RouteStart=GetActorLocation();RouteYaw=GetActorRotation().Yaw;
    if (bScooter) {Collision->SetBoxExtent(FVector(100,37,62));Body->SetRelativeLocation(FVector(0,0,-62));}
    if (SteeringAsset)
    {
        SteeringPart=NewObject<UStaticMeshComponent>(this);SteeringPart->SetupAttachment(Collision);
        SteeringPart->SetStaticMesh(SteeringAsset);SteeringPart->SetRelativeLocation(bScooter?FVector(53,0,46):FVector(35,-40,37));
        SteeringPart->SetCollisionEnabled(ECollisionEnabled::NoCollision);SteeringPart->RegisterComponent();
    }
    if (DoorAsset && !bScooter)
    {
        DoorPart=NewObject<UStaticMeshComponent>(this);DoorPart->SetupAttachment(Collision);
        DoorPart->SetStaticMesh(DoorAsset);DoorPart->SetRelativeLocation(FVector(82,-85.5f,28));
        DoorPart->SetCollisionEnabled(ECollisionEnabled::NoCollision);DoorPart->RegisterComponent();
    }
    if (!WheelAsset) return;
    const TArray<FVector> Points=bScooter?TArray<FVector>{FVector(68,0,-36),FVector(-65,0,-36)}:
        TArray<FVector>{FVector(135,-83,-34),FVector(135,83,-34),FVector(-130,-83,-34),FVector(-130,83,-34)};
    for (const auto& Point:Points)
    {
        auto* Wheel=NewObject<UStaticMeshComponent>(this);Wheel->SetupAttachment(Collision);
        Wheel->SetStaticMesh(WheelAsset);Wheel->SetRelativeLocation(Point);
        Wheel->SetCollisionEnabled(ECollisionEnabled::NoCollision);Wheel->RegisterComponent();Wheels.Add(Wheel);
    }
}
FVector AVistaCampusVehicle::SeatPoint() const
{return GetActorTransform().TransformPosition(bScooter?FVector(10,0,22):FVector(-15,-40,12));}
FQuat AVistaCampusVehicle::GripRotation() const
{return bScooter?FQuat(FVector::UpVector,FMath::DegreesToRadians(Steering*27.5f)):FQuat(FVector::ForwardVector,FMath::DegreesToRadians(Steering*75.f));}
FVector AVistaCampusVehicle::GripPoint(bool Left) const
{
    const FVector Centre=bScooter?FVector(53,0,46):FVector(35,-40,37);
    const FVector Offset=bScooter?FVector(0,Left?-30:30,0):FVector(0,Left?-14:14,9.65f);
    return GetActorTransform().TransformPosition(Centre+GripRotation().RotateVector(Offset));
}
void AVistaCampusVehicle::SetDoor(float Alpha)
{if (DoorPart) DoorPart->SetRelativeRotation(FRotator(0,FMath::Clamp(Alpha,0.f,1.f)*68.f,0));}
float AVistaCampusVehicle::GripSurface(FVector WorldPoint,bool Left,FVector& ClosestWorld) const
{
    const FVector Centre=bScooter?FVector(53,0,46):FVector(35,-40,37);
    const FVector P=GripRotation().Inverse().RotateVector(GetActorTransform().InverseTransformPosition(WorldPoint)-Centre);
    FVector Axis;float Radius;
    if (bScooter) {const float Side=Left?-1:1;Axis=FVector(0,FMath::Clamp(P.Y,Side*30-7,Side*30+7),0);Radius=2.2f;}
    else {Axis=FVector(0,P.Y,P.Z).GetSafeNormal()*17;Radius=1.8f;}
    const FVector Normal=(P-Axis).GetSafeNormal(SMALL_NUMBER,FVector::UpVector);
    ClosestWorld=GetActorTransform().TransformPosition(Centre+GripRotation().RotateVector(Axis+Normal*(Radius+.12f)));
    return FVector::Distance(P,Axis)-Radius;
}
bool AVistaCampusVehicle::FindExit(FVector& Out) const
{
    for (float Side:{-1.f,1.f})
    {
        if (!bScooter && Side>0) continue; // The authored car has a left driver door.
        const FVector Candidate=GetActorTransform().TransformPosition(FVector(0,Side*(bScooter?100:160),140));
        FCollisionQueryParams Query(SCENE_QUERY_STAT(CampusExit),false,this);Query.AddIgnoredActor(Driver.Get());
        FHitResult Ground;
        if (!GetWorld()->LineTraceSingleByChannel(Ground,Candidate,Candidate-FVector(0,0,500),ECC_Visibility,Query) || Ground.ImpactNormal.Z<.75f) continue;
        Out=Ground.ImpactPoint+FVector(0,0,90);
        if (!GetWorld()->OverlapBlockingTestByChannel(Out,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(31,87),Query)) return true;
    }
    return false;
}
void AVistaCampusVehicle::Drive(float Throttle,float Steer,bool Brake,float Dt)
{
    ThrottleInput=Brake?0:Throttle;
    // Bounded substeps plus a swept root prevent tunnelling under low frame rates.
    int32 Steps=FMath::Clamp(FMath::CeilToInt(Dt/.025f),1,20);float H=FMath::Min(Dt,.5f)/Steps;
    for (int32 I=0;I<Steps;++I)
    {
        bBrake=Brake;Steering=FMath::FInterpTo(Steering,Steer,H,6);
        if (Brake) Speed=FMath::FInterpConstantTo(Speed,0,H,900);
        else if (FMath::Abs(Throttle)>.01f) Speed=FMath::Clamp(Speed+Throttle*250*H,-250.f,bScooter?1000.f:1400.f);
        else Speed=FMath::FInterpConstantTo(Speed,0,H,70);
        const float YawDelta=FMath::RadiansToDegrees(Speed/(bScooter?135.f:265.f)*FMath::Tan(Steering*.48f))*H;
        const FRotator NextRotation(0,GetActorRotation().Yaw+YawDelta,0);
        FCollisionQueryParams Query(SCENE_QUERY_STAT(CampusVehicleTurn),false,this);Query.AddIgnoredActor(Driver.Get());
        // Sample the whole chassis footprint before motion. A centre-only trace
        // wedges the swept box at kerbs or drops its rear into the pavement.
        const auto SupportZ=[&](const FVector& At,const FRotator& Rotation)
        {
            float Highest=-FLT_MAX;const FVector Extent=Collision->GetScaledBoxExtent();
            FHitResult Pad;
            if (GetWorld()->SweepSingleByChannel(Pad,At+FVector(0,0,100),At-FVector(0,0,170),Rotation.Quaternion(),ECC_Visibility,
                FCollisionShape::MakeBox(FVector(Extent.X+2,Extent.Y+2,2)),Query) && Pad.ImpactNormal.Z>.8f)
            {
                const float Height=Pad.ImpactPoint.Z+Extent.Z+3;
                if (Height-GetActorLocation().Z<=25) Highest=Height;
            }
            const TArray<FVector> Points={FVector::ZeroVector,FVector(Extent.X+2,Extent.Y+2,0),
                FVector(Extent.X+2,-Extent.Y-2,0),FVector(-Extent.X-2,Extent.Y+2,0),FVector(-Extent.X-2,-Extent.Y-2,0)};
            for (const auto& Offset:Points)
            {
                const FVector P=At+Rotation.RotateVector(Offset);FHitResult Ground;
                if (GetWorld()->LineTraceSingleByChannel(Ground,P+FVector(0,0,100),P-FVector(0,0,170),ECC_Visibility,Query) && Ground.ImpactNormal.Z>.8f)
                {
                    const float Height=Ground.ImpactPoint.Z+Extent.Z+3;
                    if (Height-GetActorLocation().Z<=25) Highest=FMath::Max(Highest,Height);
                }
            }
            return Highest;
        };
        const FVector Candidate=GetActorLocation()+NextRotation.Vector()*Speed*H;
        const float Lift=SupportZ(Candidate,NextRotation)-GetActorLocation().Z;
        if (Lift>0 && Lift<=25)
        {
            FHitResult UpHit;SetActorLocation(GetActorLocation()+FVector(0,0,Lift),true,&UpHit);
            if (UpHit.bBlockingHit) {Speed=0;++Contacts;}
        }
        const bool TurnBlocked=GetWorld()->OverlapBlockingTestByChannel(GetActorLocation(),NextRotation.Quaternion(),ECC_WorldDynamic,
            FCollisionShape::MakeBox(Collision->GetScaledBoxExtent()*.97f),Query);
        if (!TurnBlocked) SetActorRotation(NextRotation);
        const FVector Delta=GetActorForwardVector()*Speed*H;
        FHitResult Hit;const FVector Before=GetActorLocation();
        SetActorLocation(Before+Delta,true,&Hit);
        if (Hit.bBlockingHit) {Speed=0;++Contacts;}
        const float Distance=FVector::Dist2D(Before,GetActorLocation());Travel+=Distance;
        const float Sign=FVector::DotProduct(GetActorLocation()-Before,GetActorForwardVector())>=0?1.f:-1.f;
        WheelAngle+=FMath::RadiansToDegrees(Distance/(bScooter?26.f:33.f))*Sign;
        for (int32 W=0;W<Wheels.Num();++W)
        {const bool Front=bScooter?W==0:W<2;Wheels[W]->SetRelativeRotation(FRotator(-WheelAngle,Front?Steering*27.5f:0,0));}
        if (SteeringPart) SteeringPart->SetRelativeRotation(GripRotation());
        const FVector P=GetActorLocation();const float GroundZ=SupportZ(P,GetActorRotation());
        if (GroundZ>-FLT_MAX && FMath::Abs(GroundZ-P.Z)<=25)
            SetActorLocation(FVector(P.X,P.Y,GroundZ),false);
    }
}
void AVistaCampusVehicle::Tick(float Dt)
{
    Super::Tick(Dt);if (!bTraffic || Driver.IsValid()) return;
    const float Clock=FMath::Fmod(GetWorld()->GetTimeSeconds(),32.f);
    const bool VehicleGreen=Clock<15;
    const float ForwardSign=GetActorForwardVector().X>0?1.f:-1.f;
    const float ToLine=(-700*ForwardSign-GetActorLocation().X)*ForwardSign;
    bool Stop=!VehicleGreen && ToLine>=-20 && ToLine<700;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(CampusTraffic),false,this);FHitResult Hit;
    const FVector Front=GetActorLocation()+GetActorForwardVector()*(bScooter?120:235);
    if (GetWorld()->SweepSingleByChannel(Hit,Front,Front+GetActorForwardVector()*650,FQuat::Identity,ECC_Visibility,
        FCollisionShape::MakeSphere(38),Query)) Stop=true;
    if (FVector::Dist2D(RouteStart,GetActorLocation())>RouteHalfLength*2) Stop=true;
    Drive(Speed<CruiseSpeed?1:0,0,Stop,Dt);
}

AVistaExplorerCharacter::AVistaExplorerCharacter()
{Companion=CreateDefaultSubobject<UVistaCompanionComponent>(TEXT("IndoorCompanion"));}
void AVistaExplorerCharacter::CompanionTalk(){if(Companion)Companion->TogglePanel();}
void AVistaExplorerCharacter::CompanionAsk(const FString& Text){if(Companion)Companion->Ask(Text);}
void AVistaExplorerCharacter::CompanionFollow(bool Enabled){if(Companion)Companion->Follow(Enabled);}
void AVistaExplorerCharacter::CompanionStop(){if(Companion)Companion->Stop();}
void AVistaExplorerCharacter::HomeRoom(int32 Index)
{
    const FVector Before=GetActorLocation();Super::HomeRoom(Index);
    if(FVector::Distance(Before,GetActorLocation())>1 && Companion && Companion->Companion && Companion->Companion->bFollowing)
        Companion->Companion->bBlocked=!Companion->Companion->PlaceNear(this);
}
void AVistaExplorerCharacter::BeginPlay()
{
    bCampus=GetWorld()->GetWorldSettings()->ActorHasTag(TEXT("VistaCampus"));
    Super::BeginPlay();
    FString Text;
    if (bReady && FFileHelper::LoadFileToString(Text,*(FPaths::ProjectConfigDir()/TEXT("VistaFineContacts.json"))))
    {
        const auto Data=Decode(Text);const TSharedPtr<FJsonObject>* Tips;
        if (Data && Data->TryGetObjectField(TEXT("tip_landmarks"),Tips))
            for (const auto& Pair:(*Tips)->Values)
            {
                const FName Bone(*Pair.Key);if (!BoneIndex.Contains(Bone)) continue;
                const auto Item=Pair.Value->AsObject();const auto& V=Item->GetArrayField(TEXT("source_component_cm"));
                if (V.Num()==3) VehicleTipOffsets.Add(Bone,ReferenceGlobal[BoneIndex.FindChecked(Bone)].InverseTransformPosition(FVector(V[0]->AsNumber(),V[1]->AsNumber(),V[2]->AsNumber())));
            }
        const TSharedPtr<FJsonObject>* Frames;
        if (Data && Data->TryGetObjectField(TEXT("joint_frames"),Frames))
            for (const auto& Pair:(*Frames)->Values)
            {
                const FName Bone(*Pair.Key);if (!BoneIndex.Contains(Bone)) continue;
                const auto& Q=Pair.Value->AsObject()->GetArrayField(TEXT("source_component_rotation_xyzw"));
                if (Q.Num()!=4) continue;
                FQuat Source(Q[0]->AsNumber(),Q[1]->AsNumber(),Q[2]->AsNumber(),Q[3]->AsNumber());Source.Normalize();
                VehicleFlexAxes.Add(Bone,ReferenceGlobal[BoneIndex.FindChecked(Bone)].InverseTransformVectorNoScale(Source.RotateVector(FVector::ForwardVector)).GetSafeNormal());
            }
    }
    if (FFileHelper::LoadFileToString(Text,*(FPaths::ProjectConfigDir()/TEXT("VistaExplorer.json"))))
    {
        const auto Data=Decode(Text);
        if (Data && String(Data,TEXT("schema"))==TEXT("vista.explorer/v1"))
            for (const auto& V:Data->GetArrayField(TEXT("scenes")))
            {
                const auto Row=V->AsObject();FVistaSceneChoice Scene;
                Scene.Id=String(Row,TEXT("id"));Scene.Title=String(Row,TEXT("title"));
                Scene.Detail=String(Row,TEXT("detail"));Scene.Map=String(Row,TEXT("map"));
                Scene.bAvailable=Scene.Map.StartsWith(TEXT("/Game/VISTA/")) && FPackageName::DoesPackageExist(Scene.Map);
                if (GetWorld()->GetOutermost()->GetName()==Scene.Map) SceneTitle=Scene.Title;
                Scenes.Add(Scene);
            }
    }
    FParse::Value(FCommandLine::Get(),TEXT("VistaExplorerProof="),ProofDir);
    if (!ProofDir.IsEmpty()) IFileManager::Get().MakeDirectory(*ProofDir,true);
    for (TActorIterator<AStaticMeshActor> It(GetWorld());It;++It)
    {
        if (It->ActorHasTag(TEXT("CampusGreen"))) GreenLamps.Add(*It);
        if (It->ActorHasTag(TEXT("CampusRed"))) RedLamps.Add(*It);
    }
    FTimerHandle Ready;GetWorldTimerManager().SetTimer(Ready,[this]()
    {
        if (!GetWorld()->URL.HasOption(TEXT("Explore"))) SetMenu(1);
        UE_LOG(LogTemp,Display,TEXT("VISTA_EXPLORER_READY campus=%d body=%d scenes=%d"),bCampus,bReady,Scenes.Num());
        PublishExplorerState();
    },1.8f,false);
}
void AVistaExplorerCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);BindExploreKeys(Input);
}
void AVistaExplorerCharacter::BindExploreKeys(UInputComponent* Input)
{
    // This game-facing subclass replaces review/debug shortcuts; donors keep theirs.
    Input->KeyBindings.Reset();
    Input->BindKey(EKeys::E,IE_Pressed,this,&AVistaExplorerCharacter::EmbodiedInteract);
    Input->BindKey(EKeys::Escape,IE_Pressed,this,&AVistaExplorerCharacter::ExplorerMenu);
    Input->BindKey(EKeys::Q,IE_Pressed,this,&AVistaExplorerCharacter::ExplorerActions);
    Input->BindKey(EKeys::T,IE_Pressed,this,&AVistaExplorerCharacter::CompanionTalk);
    Input->BindKey(EKeys::Tab,IE_Pressed,this,&AVistaExplorerCharacter::ToggleExplorerView);
    Input->BindKey(EKeys::G,IE_Pressed,this,&AVistaExplorerCharacter::EmbodiedDrop);
    Input->BindKey(EKeys::SpaceBar,IE_Pressed,this,&AVistaExplorerCharacter::ExplorerJump);
    Input->BindKey(EKeys::SpaceBar,IE_Released,this,&ACharacter::StopJumping);
    Input->BindKey(EKeys::LeftShift,IE_Pressed,this,&AVistaExplorerCharacter::ExplorerRun);
    Input->BindKey(EKeys::LeftShift,IE_Released,this,&AVistaExplorerCharacter::ExplorerWalk);
    Input->BindKey(EKeys::F8,IE_Pressed,this,&AVistaExplorerCharacter::ExplorerState);
}
void AVistaExplorerCharacter::ExplorerRun() {if (!Menu) bRun=true;}
void AVistaExplorerCharacter::ExplorerWalk() {bRun=false;}
void AVistaExplorerCharacter::ExplorerJump() {if (!Menu && !Riding.IsValid()) StartAlpineJump();}
void AVistaExplorerCharacter::ToggleExplorerView() {if (!Menu) ToggleView();}
void AVistaExplorerCharacter::SetMenu(int32 Value)
{
    Menu=Value;bRun=false;GetCharacterMovement()->StopMovementImmediately();
    if (auto* PC=Cast<APlayerController>(Controller))
    {
        PC->ResetIgnoreMoveInput();PC->ResetIgnoreLookInput();PC->SetIgnoreMoveInput(Menu!=0);PC->SetIgnoreLookInput(Menu!=0);
        PC->bShowMouseCursor=Menu!=0;PC->bEnableClickEvents=Menu!=0;PC->bEnableMouseOverEvents=Menu!=0;
        if (Menu) {FInputModeGameAndUI Mode;Mode.SetHideCursorDuringCapture(false);Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);PC->SetInputMode(Mode);}
        else PC->SetInputMode(FInputModeGameOnly());
    }
    PublishExplorerState();
}
void AVistaExplorerCharacter::ExplorerMenu() {if(Companion && Companion->IsOpen()){Companion->ClosePanel();return;}if (!IsCleanObservation()) SetMenu(Menu?0:1);}
void AVistaExplorerCharacter::ExplorerActions() {if(Companion && Companion->IsOpen()){Companion->ClosePanel();return;}if (!IsCleanObservation()) SetMenu(Menu?0:2);}
void AVistaExplorerCharacter::ExplorerScene(const FString& Id)
{
    if (bChangingScene) return;
    if (Riding.IsValid() || !CanLeaveSpace())
    {FeedbackMessage(TEXT("Finish the task and put down items / leave the seat before changing scenes"));return;}
    for (const auto& Scene:Scenes) if (Scene.Id==Id)
    {
        if (!Scene.bAvailable) {FeedbackMessage(TEXT("This scene is not installed"));return;}
        bChangingScene=true;
        UE_LOG(LogTemp,Display,TEXT("VISTA_SCENE_TRAVEL from=%s to=%s"),*GetWorld()->GetOutermost()->GetName(),*Scene.Map);
        UGameplayStatics::OpenLevel(this,FName(Scene.Map),true,TEXT("Explore=1"));return;
    }
    FeedbackMessage(TEXT("Unknown scene"));
}
void AVistaExplorerCharacter::ActivateMenuItem(FName Item)
{
    const FString Key=Item.ToString();
    if (Key==TEXT("companion")) {CompanionTalk();return;}
    if (Key==TEXT("resume")) {SetMenu(0);return;}
    if (Key.StartsWith(TEXT("scene:"))) {ExplorerScene(Key.Mid(6));return;}
    if (Key==TEXT("view")) {SetMenu(0);ToggleView();return;}
    if (Key==TEXT("reset")) {SetMenu(0);EmbodiedReset();return;}
    if (Key==TEXT("cancel")) {SetMenu(0);EmbodiedDrop();return;}
    if (Key==TEXT("primary")) {SetMenu(0);EmbodiedInteract();return;}
    if (Key==TEXT("tasks")) {SetMenu(3);return;}
    if (Key.StartsWith(TEXT("event:"))) {SetMenu(0);HomeEvent(Key.Mid(6));return;}
    if (Key.StartsWith(TEXT("action:"))) {SetMenu(0);ExecuteVisibleAction(Key.Mid(7));return;}
    if (Key.StartsWith(TEXT("room:"))) {SetMenu(0);HomeRoom(FCString::Atoi(*Key.Mid(5)));return;}
}
void AVistaExplorerCharacter::EmbodiedInteract()
{
    if (Menu || bChangingScene) return;
    if (auto* Vehicle=Riding.Get())
    {
        if (RidePhase!=TEXT("riding")) {FeedbackMessage(TEXT("Complete the entry / exit movement first"));return;}
        if (FMath::Abs(Vehicle->Speed)>20) {FeedbackMessage(TEXT("Brake to a stop before getting off"));return;}
        if (!Vehicle->FindExit(RideExit)) {FeedbackMessage(TEXT("The exit is blocked"));return;}
        Vehicle->Speed=0;RidePhase=TEXT("exiting");RideElapsed=RideProgress=0;
        RideStart=GetActorLocation();StartPelvis=GetMesh()->GetBoneLocation(TEXT("pelvis"));
        for (int32 I=0;I<2;++I) StartFeet[I]=GetMesh()->GetBoneLocation(I?TEXT("foot_r"):TEXT("foot_l"));
        FeedbackMessage(TEXT("Getting off - wait for both feet to reach the ground"));return;
    }
    if (auto* Vehicle=Nearby.Get())
    {
        if (!CanLeaveSpace()) {FeedbackMessage(TEXT("Put down the carried item first"));return;}
        if (!Vehicle->FindExit(RideApproach)) {FeedbackMessage(TEXT("The entry side is blocked"));return;}
        FCollisionQueryParams Query(SCENE_QUERY_STAT(CampusEntry),false,this);Query.AddIgnoredActor(Vehicle);FHitResult Hit;
        if (GetWorld()->SweepSingleByChannel(Hit,GetActorLocation(),RideApproach,FQuat::Identity,ECC_Pawn,
            FCollisionShape::MakeCapsule(30,85),Query)) {FeedbackMessage(TEXT("Walk around the obstacle to enter"));return;}
        RideStart=GetActorLocation();RideStartRotation=GetActorQuat();StartPelvis=GetMesh()->GetBoneLocation(TEXT("pelvis"));
        for (int32 I=0;I<2;++I) StartFeet[I]=GetMesh()->GetBoneLocation(I?TEXT("foot_r"):TEXT("foot_l"));
        Riding=Vehicle;Vehicle->Driver=this;Vehicle->Speed=0;RidePhase=TEXT("entering");RideElapsed=RideProgress=0;FootPlant=1;
        bSceneActionBusy=true;GetCharacterMovement()->StopMovementImmediately();GetCharacterMovement()->DisableMovement();
        GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        if (Controller) Controller->SetControlRotation(Vehicle->GetActorRotation());
        FeedbackMessage(Vehicle->bScooter?TEXT("Mounting scooter"):TEXT("Opening the driver door and getting in"));
        PublishExplorerState();return;
    }
    if (bCampus) AEmbodiedReviewCharacter::EmbodiedInteract();else Super::EmbodiedInteract();
}
void AVistaExplorerCharacter::EmbodiedDrop()
{
    if (Menu || Riding.IsValid()) return;
    if (bCampus) AEmbodiedReviewCharacter::EmbodiedDrop();else Super::EmbodiedDrop();
}
void AVistaExplorerCharacter::EmbodiedReset()
{
    if (Riding.IsValid()) {FeedbackMessage(TEXT("Stop and get off before restarting"));return;}
    if (bCampus) {for (const auto& Scene:Scenes) if (Scene.Map==GetWorld()->GetOutermost()->GetName()) {ExplorerScene(Scene.Id);return;}}
    else Super::EmbodiedReset();
}
bool AVistaExplorerCharacter::WalkSignal() const {return SignalClock>=18 && SignalClock<28;}
void AVistaExplorerCharacter::TickTrafficSignals(float Dt)
{
    SignalClock=FMath::Fmod(GetWorld()->GetTimeSeconds(),32.f);
    for (const auto& L:GreenLamps) if (L.IsValid()) L->SetActorHiddenInGame(!WalkSignal());
    for (const auto& L:RedLamps) if (L.IsValid()) L->SetActorHiddenInGame(WalkSignal());
    if (GreenLamps.IsEmpty() || Riding.IsValid()) return;
    const FVector P=GetActorLocation();const bool Inside=FMath::Abs(P.X)<400 && FMath::Abs(P.Y-CrossY)<710;
    if (Inside && !bInCrossing) {EntrySide=(P.Y-CrossY)<0?-1:1;if (!WalkSignal()) ++RedEntries;CrossingStatus=TEXT("Crossing");}
    if (!Inside && bInCrossing)
    {
        if (FMath::Abs(P.X)<430 && (P.Y-CrossY)*EntrySide<-710) {++CrossingCount;CrossingStatus=TEXT("Reached the opposite pavement");}
        else CrossingStatus=TEXT("Left the crossing");
    }
    bInCrossing=Inside;
}
void AVistaExplorerCharacter::Tick(float Dt)
{
    if (auto* Vehicle=Riding.Get())
    {
        const auto* PC=Cast<APlayerController>(Controller);
        const float Throttle=RidePhase==TEXT("riding") && !Menu && PC?(float(PC->IsInputKeyDown(EKeys::W))-float(PC->IsInputKeyDown(EKeys::S))):0;
        const float Steer=RidePhase==TEXT("riding") && !Menu && PC?(float(PC->IsInputKeyDown(EKeys::D))-float(PC->IsInputKeyDown(EKeys::A))):0;
        const float PreviousYaw=Vehicle->GetActorRotation().Yaw;
        Vehicle->Drive(Throttle,Steer,RidePhase!=TEXT("riding") || Menu!=0 || (PC && PC->IsInputKeyDown(EKeys::SpaceBar)),Dt);
        if (Controller)
        {
            FRotator Look=Controller->GetControlRotation();
            Look.Yaw+=FMath::FindDeltaAngleDegrees(PreviousYaw,Vehicle->GetActorRotation().Yaw);
            Controller->SetControlRotation(Look);
        }
        if (RidePhase==TEXT("riding"))
        {
            SetActorLocation(Vehicle->SeatPoint()+FVector(0,0,25),false);SetActorRotation(Vehicle->GetActorRotation());
            FootPlant=FMath::FInterpTo(FootPlant,FMath::Abs(Vehicle->Speed)<25?1.f:0.f,Dt,4);
        }
        else TickRideTransition(Dt);
    }
    Super::Tick(Dt);
    // A hidden menu must not keep consuming game input during clean observation.
    if (IsCleanObservation() && Menu) SetMenu(0);
    if (bCampus && !Riding.IsValid()) GetCharacterMovement()->MaxWalkSpeed=bRun?350:180;
    if (!Menu && !Riding.IsValid() && bCampus)
    {
        Nearby.Reset();float Best=300;FVector Eye;FRotator View;
        if (auto* PC=Cast<APlayerController>(Controller)) PC->GetPlayerViewPoint(Eye,View);
        for (TActorIterator<AVistaCampusVehicle> It(GetWorld());It;++It)
        {
            if (It->bTraffic || It->Driver.IsValid()) continue;
            const FVector Point=It->GetActorLocation();const float Distance=FVector::Dist2D(Point,GetActorLocation());
            if (Distance>=Best || FMath::Abs(Point.Z-GetActorLocation().Z)>130 || FVector::DotProduct((Point-Eye).GetSafeNormal(),View.Vector())<.45f) continue;
            FHitResult Hit;FCollisionQueryParams Query(SCENE_QUERY_STAT(CampusMount),true,this);
            if (GetWorld()->LineTraceSingleByChannel(Hit,Eye,Point,ECC_Visibility,Query) && Hit.GetActor()!=*It) continue;
            Best=Distance;Nearby=*It;
        }
    }
    TickWalkthrough(Dt);
    TickTrafficSignals(Dt);PublishClock+=Dt;
}
void AVistaExplorerCharacter::UpdateBodyFacing(float Dt)
{if (!Riding.IsValid()) Super::UpdateBodyFacing(Dt);}
void AVistaExplorerCharacter::UpdateInteraction(float Dt)
{if (!Riding.IsValid()) Super::UpdateInteraction(Dt);else RefreshScenePoseGoals();}
void AVistaExplorerCharacter::CalcCamera(float Dt,FMinimalViewInfo& Out)
{
    if (const auto* V=Riding.Get())
    {
        const FRotator View=Controller?Controller->GetControlRotation():V->GetActorRotation();
        const FVector Eye=RidePhase==TEXT("riding")?V->SeatPoint()+FVector(0,0,64):GetMesh()->GetBoneLocation(TEXT("head"))+V->GetActorForwardVector()*8+FVector(0,0,3);
        Out.Location=Eye;Out.Rotation=View;Out.FOV=82;
        if (bThirdPerson)
        {
            const FVector End=Eye-View.Vector()*480+FVector(0,0,110);FHitResult Hit;
            FCollisionQueryParams Query(SCENE_QUERY_STAT(CampusChaseCamera),true,this);Query.AddIgnoredActor(V);
            Out.Location=GetWorld()->SweepSingleByChannel(Hit,Eye,End,FQuat::Identity,ECC_Visibility,FCollisionShape::MakeSphere(12),Query)?Hit.Location:End;
            Out.Rotation=(Eye-Out.Location).Rotation();
        }
        return;
    }
    Super::CalcCamera(Dt,Out);
    // Use the resolved view in this frame. Actor Tick precedes camera update;
    // comparing last frame's camera to newly moved pawns reports false contact.
    if (PublishClock>.1f) {PublishClock=0;PublishExplorerState(&Out);}
}
FString AVistaExplorerCharacter::GetInteractionHint() const
{
    if (bCampus && Clock<FeedbackUntil) return Feedback;
    if (const auto* V=Riding.Get()) return FString::Printf(TEXT("%s  |  %.0f km/h  |  Space: brake  |  E: get off when stopped"),V->bScooter?TEXT("Scooter"):TEXT("Car"),FMath::Abs(V->Speed)*.036f);
    if (const auto* V=Nearby.Get()) return V->bScooter?TEXT("E  Ride scooter"):TEXT("E  Enter car");
    if (bCampus) return bHasCandidate?TEXT("E  Pick up cup"):TEXT("WASD + mouse to explore  |  Look toward a parked vehicle to use it");
    return Super::GetInteractionHint().Replace(TEXT("wheel: action   F: inspect"),TEXT("Q: more actions"));
}
void AVistaExplorerCharacter::PublishExplorerState(const FMinimalViewInfo* ResolvedView)
{
    if (ProofDir.IsEmpty()) return;
    auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),TEXT("vista.explorer-state/v1"));
    O->SetStringField(TEXT("map"),GetWorld()->GetOutermost()->GetName());O->SetBoolField(TEXT("body_ready"),bReady);
    O->SetNumberField(TEXT("clock_s"),GetWorld()->GetTimeSeconds());O->SetNumberField(TEXT("menu"),Menu);
    O->SetNumberField(TEXT("camera_yaw"),Controller?Controller->GetControlRotation().Yaw:0);
    O->SetBoolField(TEXT("campus"),bCampus);O->SetBoolField(TEXT("third_person"),bThirdPerson);
    auto Tour=MakeShared<FJsonObject>();Tour->SetStringField(TEXT("status"),WalkthroughStatus);
    Tour->SetNumberField(TEXT("index"),WalkthroughIndex);Tour->SetNumberField(TEXT("points"),Walkthrough.Num());
    Tour->SetNumberField(TEXT("elapsed_s"),WalkthroughClock);Tour->SetNumberField(TEXT("travel_cm"),WalkthroughDistance);
    O->SetObjectField(TEXT("walkthrough"),Tour);
    if (const auto* PC=Cast<APlayerController>(Controller)) if (PC->PlayerCameraManager)
    {
        const auto& View=ResolvedView?*ResolvedView:PC->PlayerCameraManager->GetCameraCacheView();
        O->SetArrayField(TEXT("camera_cm"),Values(View.Location));
        O->SetNumberField(TEXT("camera_near_cm"),View.GetFinalPerspectiveNearClipPlane());
        float Aspect=View.AspectRatio;
        if (!View.bConstrainAspectRatio) {int32 W=0,H=0;PC->GetViewportSize(W,H);if(W>0 && H>0)Aspect=float(W)/H;}
        const float Radius=VistaCamera::Clearance(View.GetFinalPerspectiveNearClipPlane(),View.FOV,Aspect);
        FCollisionQueryParams Q(SCENE_QUERY_STAT(ExplorerCameraProof),true,this);
        if (Cup && (Phase!=EEmbodiedPhase::Idle || bSceneActionBusy)) Q.AddIgnoredActor(Cup);
        O->SetBoolField(TEXT("camera_overlap"),GetWorld()->OverlapBlockingTestByChannel(View.Location,FQuat::Identity,
            ECC_Camera,FCollisionShape::MakeSphere(Radius-.25f),Q));
    }
    O->SetArrayField(TEXT("player_cm"),Values(GetActorLocation()));O->SetStringField(TEXT("nearby"),Nearby.IsValid()?Nearby->VehicleId:TEXT(""));
    if (const auto* C=FindComponentByClass<UVistaCompanionComponent>()) if (const auto* A=C->Companion.Get())
    {
        auto D=MakeShared<FJsonObject>();const FVector Offset=A->GetActorLocation()-GetActorLocation();
        const auto* Mine=GetCapsuleComponent();const auto* Theirs=A->GetCapsuleComponent();
        const float Radii=Mine->GetScaledCapsuleRadius()+Theirs->GetScaledCapsuleRadius();
        const float SegmentGap=FMath::Max(0.f,float(FMath::Abs(Offset.Z))-
            Mine->GetScaledCapsuleHalfHeight()-Theirs->GetScaledCapsuleHalfHeight()+Radii);
        D->SetArrayField(TEXT("position_cm"),Values(A->GetActorLocation()));
        D->SetNumberField(TEXT("distance_3d_cm"),Offset.Size());
        D->SetNumberField(TEXT("capsule_gap_cm"),FMath::Sqrt(Offset.SizeSquared2D()+SegmentGap*SegmentGap)-Radii);
        D->SetBoolField(TEXT("blocked"),A->bBlocked);D->SetBoolField(TEXT("following"),A->bFollowing);
        O->SetObjectField(TEXT("companion"),D);
    }
    O->SetStringField(TEXT("riding"),Riding.IsValid()?Riding->VehicleId:TEXT(""));
    O->SetStringField(TEXT("ride_phase"),RidePhase);O->SetNumberField(TEXT("ride_progress"),RideProgress);
    O->SetNumberField(TEXT("foot_plant"),FootPlant);
    O->SetBoolField(TEXT("pose_finalized_this_frame"),FMath::Abs(LastPoseClock-GetWorld()->GetTimeSeconds())<.001);
    if (Riding.IsValid() && bReady)
    {
        O->SetArrayField(TEXT("pelvis_cm"),Values(GetMesh()->GetBoneLocation(TEXT("pelvis"))));
        O->SetArrayField(TEXT("hand_r_cm"),Values(GetMesh()->GetBoneLocation(TEXT("hand_r"))));
        O->SetArrayField(TEXT("hand_l_cm"),Values(GetMesh()->GetBoneLocation(TEXT("hand_l"))));
        O->SetArrayField(TEXT("foot_l_cm"),Values(GetMesh()->GetBoneLocation(TEXT("foot_l"))));
        O->SetArrayField(TEXT("foot_r_cm"),Values(GetMesh()->GetBoneLocation(TEXT("foot_r"))));
        O->SetNumberField(TEXT("pelvis_error_cm"),FVector::Distance(GetMesh()->GetBoneLocation(TEXT("pelvis")),SeatPelvisWorld));
        const FVector Foot=GetMesh()->GetBoneLocation(TEXT("foot_l"));FHitResult Floor;
        FCollisionQueryParams Query(SCENE_QUERY_STAT(CampusFootProof),false,this);Query.AddIgnoredActor(Riding.Get());
        if (GetWorld()->LineTraceSingleByChannel(Floor,Foot+FVector(0,0,5),Foot-FVector(0,0,160),ECC_Visibility,Query))
            O->SetNumberField(TEXT("left_foot_floor_clearance_cm"),Foot.Z-Floor.ImpactPoint.Z);
        O->SetNumberField(TEXT("hand_r_error_cm"),FVector::Distance(GetMesh()->GetBoneLocation(TEXT("hand_r")),LastHandGoal.GetLocation()));
        O->SetNumberField(TEXT("hand_l_error_cm"),FVector::Distance(GetMesh()->GetBoneLocation(TEXT("hand_l")),LeftHandGoal.GetLocation()));
        auto Gaps=MakeShared<FJsonObject>();const auto* V=Riding.Get();
        for (const auto& Tip:VehicleTipOffsets)
        {
            FVector Closest;Gaps->SetNumberField(Tip.Key.ToString(),V->GripSurface(GetMesh()->GetSocketTransform(Tip.Key).TransformPosition(Tip.Value),Tip.Key.ToString().EndsWith(TEXT("_l")),Closest));
        }
        O->SetObjectField(TEXT("finger_surface_gap_cm"),Gaps);
    }
    O->SetNumberField(TEXT("crossings"),CrossingCount);O->SetNumberField(TEXT("red_entries"),RedEntries);O->SetBoolField(TEXT("walk_signal"),WalkSignal());
    O->SetBoolField(TEXT("can_change_scene"),!Riding.IsValid() && CanLeaveSpace());O->SetStringField(TEXT("hint"),GetInteractionHint());
    TArray<TSharedPtr<FJsonValue>> Vehicles;
    for (TActorIterator<AVistaCampusVehicle> It(GetWorld());It;++It)
    {
        auto V=MakeShared<FJsonObject>();V->SetStringField(TEXT("id"),It->VehicleId);V->SetBoolField(TEXT("traffic"),It->bTraffic);
        V->SetArrayField(TEXT("position_cm"),Values(It->GetActorLocation()));V->SetNumberField(TEXT("yaw"),It->GetActorRotation().Yaw);
        V->SetNumberField(TEXT("speed_cm_s"),It->Speed);V->SetNumberField(TEXT("travel_cm"),It->Travel);V->SetNumberField(TEXT("contacts"),It->Contacts);
        V->SetNumberField(TEXT("steering"),It->Steering);
        V->SetNumberField(TEXT("steering_part_angle"),It->SteeringPart?(It->bScooter?It->SteeringPart->GetRelativeRotation().Yaw:It->SteeringPart->GetRelativeRotation().Roll):0);
        V->SetNumberField(TEXT("throttle"),It->ThrottleInput);V->SetBoolField(TEXT("brake"),It->bBrake);
        V->SetNumberField(TEXT("door_yaw"),It->DoorPart?It->DoorPart->GetRelativeRotation().Yaw:0);
        V->SetBoolField(TEXT("articulated_steering"),It->SteeringPart!=nullptr);
        Vehicles.Add(MakeShared<FJsonValueObject>(V));
    }
    O->SetArrayField(TEXT("vehicles"),Vehicles);
    const FString Target=ProofDir/TEXT("state.json"),Temp=ProofDir/TEXT("state.tmp");
    FFileHelper::SaveStringToFile(Encode(O),*Temp);IFileManager::Get().Move(*Target,*Temp,true,true);
}
void AVistaExplorerCharacter::ExplorerState()
{PublishExplorerState();FScreenshotRequest::RequestScreenshot(TEXT("Explorer"),true,true);}

AVistaExplorerGameMode::AVistaExplorerGameMode()
{DefaultPawnClass=AVistaExplorerCharacter::StaticClass();HUDClass=AVistaExplorerHUD::StaticClass();}
void AVistaExplorerHUD::NotifyHitBoxClick(FName Name)
{Super::NotifyHitBoxClick(Name);if (auto* P=Cast<AVistaExplorerCharacter>(GetOwningPawn())) P->ActivateMenuItem(Name);}
void AVistaExplorerHUD::DrawHUD()
{
    Super::DrawHUD();if (!Canvas) return;
    auto* P=Cast<AVistaExplorerCharacter>(GetOwningPawn());if (!P || P->IsCleanObservation()) return;
    const float W=Canvas->SizeX,H=Canvas->SizeY,S=FMath::Min(W/1920.f,H/1080.f);
    const FLinearColor White(.95,.97,1),Muted(.63,.72,.8),Accent(.32,.83,.72),Panel(.025,.043,.06,.94);
    const auto Text=[&](const FString& T,float X,float Y,float Size,FLinearColor Color){DrawText(T,Color,X*S,Y*S,nullptr,Size*S);};
    const auto Rect=[&](float X,float Y,float Width,float Height,FLinearColor C){DrawRect(C,X*S,Y*S,Width*S,Height*S);};
    const auto Button=[&](FName Id,const FString& Label,float X,float Y,float Width,bool Enabled=true)
    {
        float MX=-1,MY=-1;if (auto* PC=GetOwningPlayerController()) PC->GetMousePosition(MX,MY);
        const bool Hover=Enabled && MX>=X*S && MX<=(X+Width)*S && MY>=Y*S && MY<=(Y+52)*S;
        Rect(X,Y,Width,52,Hover?FLinearColor(.09,.29,.31,.98):FLinearColor(.075,.115,.15,.95));
        Text(Label,X+18,Y+15,1.15,Enabled?(Hover?Accent:White):Muted);
        if (Enabled) AddHitBox(FVector2D(X*S,Y*S),FVector2D(Width*S,52*S),Id,true);
    };
    Rect(26,24,480,68,Panel);Text(TEXT("VISTA  /  EXPLORE"),44,35,1.3,Accent);Text(P->SceneTitle,44,65,.95,White);
    if(P->Companion && P->Companion->IsOpen())return;
    if (!P->Menu)
    {
        Rect(26,990,1500,62,Panel);Text(P->GetInteractionHint(),46,1008,1.12,White);
        Text(P->Companion && P->Companion->IsEnabled()?TEXT("T  Talk     Q  Actions     Tab  View     Esc  Rooms"):TEXT("Q  Actions     Tab  View     Esc  Scenes & controls"),1120,38,1.0,White);
        if (!P->bCampus) Text(P->GetEventHint().Replace(TEXT("Free exploration   |   F2: next VISTA scenario   R: reset"),TEXT("Free exploration  |  Q: activities and room selection")),44,113,.85,Muted);
        Rect(958,538,4,4,FLinearColor(1,1,1,.8));
        return;
    }
    Rect(0,0,1920,1080,FLinearColor(.01,.018,.029,.78));
    Rect(185,140,1550,780,Panel);
    Text(P->Menu==1?TEXT("Choose your space"):P->Menu==3?TEXT("Choose an activity"):TEXT("What would you like to do?"),230,180,2.35,White);
    Text(P->bCampus?TEXT("NYCU Guangfu / Daxue Road  -  approximate campus reconstruction"):TEXT("Six rooms / everyday interactions"),232,228,1.1,Muted);
    if (P->bChangingScene) {Text(TEXT("Loading scene..."),232,310,2,Accent);return;}
    if (P->Menu==1)
    {
        if(P->Companion && P->Companion->IsEnabled())
        {
            const TCHAR* Names[]={TEXT("Entry"),TEXT("Living room"),TEXT("Kitchen / dining"),TEXT("Bedroom"),TEXT("Office"),TEXT("Bathroom / laundry")};
            for(int32 I=0;I<6;++I)Button(FName(FString::Printf(TEXT("room:%d"),I+1)),Names[I],232+(I%2)*735,288+(I/2)*98,690,P->CanLeaveSpace());
            Button(TEXT("companion"),TEXT("Talk to your companion"),232,610,690);
            Text(TEXT("WASD  Walk     Mouse  Look     E  Interact     T  Talk"),232,715,1.25,White);
            Text(TEXT("Q  More actions / activities     Tab  First / third person"),232,759,1.15,Muted);
            Button(TEXT("resume"),TEXT("Explore together"),232,833,1410);return;
        }
        for (int32 I=0;I<P->Scenes.Num();++I)
        {
            const auto& Scene=P->Scenes[I];const float X=232+(I%2)*735,Y=288+(I/2)*145;
            Button(FName(TEXT("scene:")+Scene.Id),Scene.Title,X,Y,690,Scene.bAvailable);
            Text(Scene.Detail,X+18,Y+67,.98,Muted);
        }
        Text(TEXT("ON FOOT"),232,605,1.2,Accent);
        Text(TEXT("WASD  Move     Mouse  Look     Shift  Walk faster     Space  Jump"),232,640,1.1,White);
        Text(TEXT("E  Main action     Q  Choose other actions     Tab  First / third person"),232,675,1.1,White);
        Text(TEXT("DRIVING / RIDING"),232,728,1.2,Accent);
        Text(TEXT("W / S  Accelerate / reverse     A / D  Steer     Space  Brake     E  Get off"),232,763,1.1,White);
        Button(TEXT("resume"),TEXT("Resume exploration"),232,833,420);
        Button(TEXT("view"),TEXT("Change camera view"),682,833,420);
        Button(TEXT("reset"),TEXT("Restart this space"),1132,833,510);
    }
    else
    {
        int32 N=0;
        const auto Option=[&](const FString& Id,const FString& Label)
        {const float X=232+(N%2)*735,Y=295+(N/2)*65;Button(FName(Id),Label,X,Y,690);++N;};
        if (P->Menu==3)
        {
            for (const auto& Event:P->VisibleEvents()) Option(TEXT("event:")+Event.Key,Event.Value.Len()>62?Event.Value.Left(59)+TEXT("..."):Event.Value);
        }
        else if (P->bCampus || P->Riding.IsValid()) Option(TEXT("primary"),P->Riding.IsValid()?TEXT("Get off / leave car"):P->Nearby.IsValid()?TEXT("Use this vehicle"):TEXT("Interact with the object"));
        else for (const auto& Id:P->VisibleActionIds()) Option(TEXT("action:")+Id,P->VisibleActionName(Id));
        Option(TEXT("cancel"),TEXT("Cancel action / release carried item"));Option(TEXT("view"),TEXT("Change camera view"));
        if (!P->bCampus && P->Menu==2) Option(TEXT("tasks"),TEXT("Choose a VISTA activity"));
        if (!P->bCampus && P->Menu==2 && P->CanLeaveSpace())
        {
            const TCHAR* Names[]={TEXT("Entry"),TEXT("Living room"),TEXT("Kitchen / dining"),TEXT("Bedroom"),TEXT("Office"),TEXT("Bathroom / laundry")};
            for (int32 I=0;I<6;++I) Option(FString::Printf(TEXT("room:%d"),I+1),FString(TEXT("Go to "))+Names[I]);
        }
        Text(TEXT("Only actions available here are offered. The world continues while this menu is open."),232,782,.95,Muted);
        Button(TEXT("resume"),TEXT("Back to exploration"),232,833,1410);
    }
    if (P->GetInteractionHint().Len()) Text(P->GetInteractionHint(),232,946,.95,White);
}
