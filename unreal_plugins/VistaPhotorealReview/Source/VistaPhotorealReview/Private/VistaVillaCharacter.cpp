#include "VistaVillaCharacter.h"
#include "VistaAlpineProof.h"
#include "VistaVillaMotionProof.h"
#include "HomeFluidAuthoring.h"
#include "HomeActionsJson.h"
#include "VistaMotionCurves.h"
#include "VistaReservoirSurface.h"
#include "VistaLiquidStream.h"
#include "Materials/MaterialInterface.h"
#include "Camera/CameraComponent.h"
#include "Camera/CameraActor.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/Canvas.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "InputCoreTypes.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "NiagaraComponent.h"
#include "NiagaraSystem.h"
#include "NiagaraSystemInstanceController.h"
#include "NiagaraEmitterInstance.h"
#include "PhysicsEngine/PhysicsHandleComponent.h"
#include "TimerManager.h"
#include "UnrealClient.h"
#if WITH_EDITOR
#include "ShaderCompiler.h"
#endif

using namespace HomeJson;
struct FVillaStreams {VistaStream::FColumn Pour,Tap;};
void FVillaStreamsDeleter::operator()(FVillaStreams* Value) const {delete Value;}
AVistaVillaCharacter::AVistaVillaCharacter()=default;
AVistaVillaCharacter::~AVistaVillaCharacter()=default;

AVistaVillaGameMode::AVistaVillaGameMode()
{DefaultPawnClass=AVistaVillaCharacter::StaticClass();HUDClass=AVistaVillaHUD::StaticClass();}

void AVistaVillaHUD::DrawHUD()
{
    Super::DrawHUD();if (!Canvas) return;
    auto* Body=Cast<AVistaVillaCharacter>(GetOwningPawn());if (!Body) return;
    DrawRect(FLinearColor(.025f,.04f,.03f,.82f),20,20,390,70);
    DrawText(TEXT("VISTA  /  ALPINE VILLA R3"),FColor(237,232,215),36,30,nullptr,1.35f);
    DrawText(Body->IsThirdPerson()?TEXT("THIRD PERSON"):TEXT("FIRST PERSON"),FColor(191,209,195),36,61,nullptr,.85f);
    DrawRect(FLinearColor(.02f,.03f,.025f,.80f),20,Canvas->SizeY-52,Canvas->SizeX-40,32);
    DrawText(Body->GetInteractionHint(),FColor(238,235,221),32,Canvas->SizeY-44,nullptr,.85f);
    DrawRect(FLinearColor(.9f,.9f,.8f,.9f),Canvas->SizeX*.5f-1,Canvas->SizeY*.5f-1,2,2);
}

void AVistaVillaCharacter::BeginPlay()
{
    Super::BeginPlay();
    for (TActorIterator<AStaticMeshActor> It(GetWorld());It;++It)
    {
        if (It->ActorHasTag(TEXT("VillaJug"))) Jug=*It;
        if (It->ActorHasTag(TEXT("VillaMug"))) Mug=*It;
    }
    FString AppearanceText;TSharedPtr<FJsonObject> Appearance;
    if (FFileHelper::LoadFileToString(AppearanceText,*(FPaths::ProjectContentDir()/TEXT("VISTA/VillaR1/appearance.json")))) Appearance=Decode(AppearanceText);
    const FString WorldPath=Appearance?String(Appearance,TEXT("world")):TEXT("/Game/VISTA/VillaR1/Character/World/SK_VillaWorld.SK_VillaWorld");
    const FString OwnerPath=Appearance?String(Appearance,TEXT("owner")):TEXT("/Game/VISTA/VillaR1/Character/Owner/SK_VillaOwner.SK_VillaOwner");
    auto* WorldBody=LoadObject<USkeletalMesh>(nullptr,*WorldPath);
    auto* FirstBody=LoadObject<USkeletalMesh>(nullptr,*OwnerPath);
    if (!Jug || !Mug || !WorldBody || !FirstBody || !bReady)
    {UE_LOG(LogTemp,Error,TEXT("VILLA_REQUIRED_ASSET_MISSING"));return;}
    const auto& Ref=WorldBody->GetRefSkeleton();
    if (Ref.GetNum()!=Parents.Num()) {bReady=false;return;}
    for (int32 I=0;I<Ref.GetNum();++I)
        if (Ref.GetBoneName(I)!=Poses->BoneNames[I]) {bReady=false;UE_LOG(LogTemp,Error,TEXT("VILLA_BONE_ORDER_MISMATCH"));return;}
    GetMesh()->SetSkeletalMesh(WorldBody);OwnerBody->SetSkeletalMesh(FirstBody);
    GetMesh()->SetAnimInstanceClass(nullptr);
    GetMesh()->SetAnimInstanceClass(UEmbodiedBodyAnimInstance::StaticClass());
    GetMesh()->InitAnim(true);OwnerBody->SetLeaderPoseComponent(GetMesh(),true,false);
    JugInitial=Jug->GetActorTransform();MugInitial=Mug->GetActorTransform();
    for (TActorIterator<ACameraActor> It(GetWorld());It;++It) TourCameras.Add(*It);
    for (auto* Item:{Jug.Get(),Mug.Get()})
    {
        auto* Mesh=Item->GetStaticMeshComponent();Mesh->SetMobility(EComponentMobility::Movable);
        Mesh->SetCollisionProfileName(TEXT("PhysicsActor"));Mesh->BodyInstance.bUseCCD=true;
        Mesh->SetMassOverrideInKg(NAME_None,Item==Jug?.65f:.32f,true);Mesh->SetSimulatePhysics(true);
        Mesh->SetLinearDamping(.4);Mesh->SetAngularDamping(.8);
    }
    LoadMotionLibrary();
    LoadAlpineMotion();
    if (Motions.Num()<2 || MotionIdle.Num()!=Parents.Num())
    {bReady=false;UE_LOG(LogTemp,Error,TEXT("VILLA_MOTION_ASSET_INVALID"));return;}
    bAllowReachDetour=true;
    auto* System=LoadObject<UNiagaraSystem>(nullptr,TEXT("/Game/VISTA/VillaR1/Fluids/NS_ControlledHose.NS_ControlledHose"));
    for (int32 I=0;I<2;++I)
    {
        auto* Fluid=NewObject<UNiagaraComponent>(this);Fluid->RegisterComponent();
        Fluid->SetAsset(System);Fluid->SetWorldLocation(I?TapOrigin:PourOrigin);
        const FString Configuration=I?
            TEXT("{\"User.Num Cells Max Axis\":48,\"User.Particles Per Cell\":4,\"User.Pressure Iterations\":24,\"User.World Grid Extents\":[58,54,60],\"User.Water Height\":0,\"User.SourceRate\":0,\"User.SourceRadius\":0.65,\"User.SourcePosition\":[0,0,45],\"User.Show Bounds\":false}"):
            TEXT("{\"User.Num Cells Max Axis\":48,\"User.Particles Per Cell\":4,\"User.Pressure Iterations\":24,\"User.World Grid Extents\":[48,40,45],\"User.Water Height\":0,\"User.SourceRate\":0,\"User.SourceRadius\":0.55,\"User.SourcePosition\":[0,0,30],\"User.Show Bounds\":false}");
        const auto Result=Decode(UHomeFluidAuthoring::ConfigureComponent(Fluid,Configuration));
        if (!Result || !Bool(Result,TEXT("ok"))) {UE_LOG(LogTemp,Error,TEXT("VILLA_FLUID_BINDING_FAILED"));bReady=false;return;}
        Fluid->SetForceSolo(true);Fluid->Activate(true);Fluid->SetEmitterEnable(TEXT("Grid3D_FLIP_Secondary_Emitter"),false);
        // An empty domain has no motion to advance. Start it on first inflow;
        // once started, closing the source does not pause existing water.
        Fluid->SetPaused(true);
        if (I) TapFluid=Fluid;else PourFluid=Fluid;
    }
    TapLedger.Source=TapLedger.Initial=0;
    auto* WaterMaterial=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/VISTA/VillaR1/Fluids/M_VesselWater.M_VesselWater"));
    Streams.Reset(new FVillaStreams());
    for (int32 I=0;I<4;++I)
    {
        auto* Surface=NewObject<UProceduralMeshComponent>(this);Surface->RegisterComponent();
        Surface->SetCollisionEnabled(ECollisionEnabled::NoCollision);Surface->SetCastShadow(false);
        Surface->SetMaterial(0,WaterMaterial);Surface->SetTranslucentSortPriority(2);
        if (I==0) JugSurface=Surface;else if (I==1) MugSurface=Surface;else if (I==2) PourColumn=Surface;else TapColumn=Surface;
    }
    bProof=FParse::Param(FCommandLine::Get(),TEXT("VistaVillaProof"));
    ProofDir=FPaths::ProjectSavedDir()/TEXT("VillaProof");
    if (bProof && IFileManager::Get().DirectoryExists(*ProofDir)) {bProof=false;UE_LOG(LogTemp,Error,TEXT("VILLA_PROOF_REUSED"));}
    if (bProof) IFileManager::Get().MakeDirectory(*ProofDir,true);
    FTimerHandle Start;
    GetWorldTimerManager().SetTimer(Start,[this]()
    {
        SetActorLocation(bProof?FVector(1210,-1000,83):FVector(680,-110,83),false,nullptr,ETeleportType::TeleportPhysics);
        SetActorRotation(FRotator(0,bProof?90:140,0));Controller->SetControlRotation(FRotator(-10,bProof?90:140,0));
        bFeetReady=false;
    },1.35f,false);
    UE_LOG(LogTemp,Display,TEXT("VILLA_READY motion_frames=%d bones=%d"),Motions.Num(),Ref.GetNum());
}

void AVistaVillaCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    // The inherited apartment tour uses coordinates from its own map. This
    // villa owns its navigation and must not expose those unrelated shortcuts.
    Input->KeyBindings.RemoveAll([](const FInputKeyBinding& B)
    {const FKey K=B.Chord.Key;return K==EKeys::One || K==EKeys::Two || K==EKeys::Three || K==EKeys::Four || K==EKeys::Five || K==EKeys::Six || K==EKeys::Seven || K==EKeys::Eight || K==EKeys::Nine || K==EKeys::C || K==EKeys::Zero || K==EKeys::V || K==EKeys::F;});
    Input->BindKey(EKeys::P,IE_Pressed,this,&AVistaVillaCharacter::VillaPour);
    Input->BindKey(EKeys::F,IE_Pressed,this,&AVistaVillaCharacter::VillaTap);
    Input->BindKey(EKeys::H,IE_Pressed,this,&AVistaVillaCharacter::VillaDemo);
    Input->BindKey(EKeys::LeftShift,IE_Pressed,this,&AVistaVillaCharacter::StartRunning);
    Input->BindKey(EKeys::LeftShift,IE_Released,this,&AVistaVillaCharacter::StopRunning);
    Input->BindKey(EKeys::SpaceBar,IE_Pressed,this,&AVistaVillaCharacter::StartAlpineJump);
    Input->BindKey(EKeys::SpaceBar,IE_Released,this,&ACharacter::StopJumping);
}

FTransform AVistaVillaCharacter::DesiredGrip() const
{
    FTransform T=Super::DesiredGrip();
    if (Cup==Jug) T.AddToTranslation(CupMesh->GetUpVector()*6.8f);
    return T;
}
FTransform AVistaVillaCharacter::CarryTarget() const
{
    return FTransform(GetActorQuat()*HoldRelativeRotation,
        GetActorLocation()+GetActorQuat().RotateVector(FVector(32,18,Cup==Jug?26:20)));
}
void AVistaVillaCharacter::EmbodiedInteract()
{
    if (TryGardenDoor()) return;
    if (bPouring) {FeedbackMessage(TEXT("Finish pouring before placing"));return;}
    if (Phase==EEmbodiedPhase::Idle && Jug && Mug)
    {
        FVector Eye;FRotator View;Cast<APlayerController>(Controller)->GetPlayerViewPoint(Eye,View);
        AStaticMeshActor* Best=nullptr;float Score=.9f;
        for (auto* Item:{Jug.Get(),Mug.Get()})
        {
            const float S=FVector::DotProduct((Item->GetStaticMeshComponent()->Bounds.Origin-Eye).GetSafeNormal(),View.Vector());
            if (S>Score && FVector::Dist2D(Item->GetActorLocation(),GetActorLocation())<86) {Score=S;Best=Item;}
        }
        if (Best)
        {
            Cup=Best;CupMesh=Best->GetStaticMeshComponent();ItemRadius=Best==Jug?5.f:3.85f;ItemHeight=Best==Jug?25.5f:9.5f;
            bAllowReachDetour=true;
        }
    }
    Super::EmbodiedInteract();
}
void AVistaVillaCharacter::VillaPour()
{
    if (Phase!=EEmbodiedPhase::Held || Cup!=Jug || bPouring) {FeedbackMessage(TEXT("Pick up the glass carafe, then P to pour"));return;}
    if (FVector::Dist2D(Mug->GetActorLocation(),GetActorLocation())>70) {FeedbackMessage(TEXT("Move close to the mug"));return;}
    if (Liquid.Source<=0) {FeedbackMessage(TEXT("The carafe is empty"));return;}
    PourStart=CupMesh->GetComponentTransform();PourClock=0;bPouring=true;bSceneActionBusy=true;
}
void AVistaVillaCharacter::VillaTap()
{
    if (!bDemo && FVector::Dist2D(GetActorLocation(),FVector(1080,-895,0))>115)
    {FeedbackMessage(TEXT("Move beside the sink to operate its tap"));return;}
    bTap=!bTap;FeedbackMessage(bTap?TEXT("Tap on"):TEXT("Tap off"));
}
void AVistaVillaCharacter::UpdateInteraction(float Dt)
{
    if (!bPouring) {Super::UpdateInteraction(Dt);return;}
    if (!GripHandle->GrabbedComponent) {bPouring=false;bSceneActionBusy=false;return;}
    PourClock+=Dt;
    const float Into=VistaMotion::Ease(PourClock/1.15f);
    const float Out=VistaMotion::Ease((PourClock-4.5f)/1.25f);
    const FQuat Tilt=FQuat(GetActorRightVector(),FMath::DegreesToRadians(78.f));
    const FQuat R=Tilt*PourStart.GetRotation();
    const FVector LipLocal(0,0,25.3f);
    const FVector Mouth=Mug->GetActorLocation()+FVector(0,0,19.f);
    const FTransform Tilted(R,Mouth-R.RotateVector(LipLocal));
    FTransform Goal;Goal.Blend(PourStart,Tilted,Into);FTransform Return=CarryTarget();
    Goal.Blend(Goal,Return,Out);
    GripHandle->SetTargetLocationAndRotation(Goal.GetLocation(),Goal.Rotator());
    LastHandGoal=HandRelativeToCup*CupMesh->GetComponentTransform();ReachAlpha=FingerAlpha=1;
    if (PourClock>5.9f)
    {bPouring=false;bSceneActionBusy=false;HoldStart=CupMesh->GetComponentTransform();PhaseTime=0;FeedbackMessage(TEXT("Pour complete — look at the counter and E to place"));}
}
void AVistaVillaCharacter::UpdateLiquids(float Dt)
{
    if (!PourFluid || !TapFluid || !Jug || !Mug) return;
    const auto Transform=Jug->GetActorTransform();const FVector Lip=Transform.TransformPosition(FVector(0,0,25.3f));
    const FVector Receiver=Mug->GetActorLocation()+FVector(0,0,9.5f);
    const float Angle=FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(Jug->GetActorUpVector().Z,-1.f,1.f)));
    const float Rate=bPouring && PourClock>1.1f && PourClock<4.5f?FMath::Clamp((Angle-48.f)/22.f,0.f,1.f)*65.f:0.f;
    const double Flight=FMath::Sqrt(FMath::Max(0.,2.*(Lip.Z-Receiver.Z)/980.));
    const bool Hits=FVector::Dist2D(Lip,Receiver)<3.4f && Lip.Z>Receiver.Z && Mug->GetActorUpVector().Z>.95;
    Liquid.Step(Dt);const double Emitted=Liquid.Emit(Rate,Dt,Flight,Hits);
    if (Emitted>0) PourFluid->SetPaused(false);
    PourFluid->SetVariableFloat(TEXT("User.SourceRate"),Emitted>0?float(Emitted/Dt)*35.f:0.f);
    PourFluid->SetVariableVec3(TEXT("User.SourcePosition"),Lip-PourOrigin);
    PourFluid->SetVariableVec3(TEXT("User.SourceVelocity"),FVector(0,0,-65));
    JugRenderedMl=VistaReservoir::Update(JugSurface,Jug->GetActorTransform(),Liquid.Source,true);
    MugRenderedMl=VistaReservoir::Update(MugSurface,Mug->GetActorTransform(),Liquid.Receiver,false);
    TapLedger.Step(Dt,true);const double TapMl=TapLedger.Emit(bTap?90.:0.,Dt,.3,false,true);
    if (TapMl>0) TapFluid->SetPaused(false);
    TapFluid->SetVariableFloat(TEXT("User.SourceRate"),TapMl>0?3150.f:0.f);
    TapFluid->SetVariableVec3(TEXT("User.SourcePosition"),FVector(1080,-895,120)-TapOrigin);
    TapFluid->SetVariableVec3(TEXT("User.SourceVelocity"),FVector(0,0,-70));
    Streams->Pour.Update(PourColumn,Dt,Lip,Emitted/Dt,65,Hits?Receiver.Z:96.);
    Streams->Tap.Update(TapColumn,Dt,FVector(1080,-895,120),TapMl/Dt,70,76.);
    // Deactivating the component would erase in-flight water: only source rate
    // is switched. The same GPU solvers and collision domains keep ticking.
    if (FMath::Abs(Liquid.Residual())>1e-5 || FMath::Abs(TapLedger.Residual())>1e-5)
        UE_LOG(LogTemp,Error,TEXT("VILLA_LIQUID_MASS_BALANCE_FAILURE"));
}
void AVistaVillaCharacter::EmbodiedReset()
{
    if (!Jug || !Mug) return;
    bDemo=bPouring=bSceneActionBusy=bTap=false;GripHandle->ReleaseComponent();
    for (auto* Item:{Jug.Get(),Mug.Get()})
    {
        auto* Mesh=Item->GetStaticMeshComponent();Mesh->SetPhysicsLinearVelocity(FVector::ZeroVector);Mesh->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
        Item->SetActorTransform(Item==Jug?JugInitial:MugInitial,false,nullptr,ETeleportType::TeleportPhysics);
        Mesh->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);GetCapsuleComponent()->IgnoreActorWhenMoving(Item,false);
    }
    Liquid=VistaLiquid::Ledger();TapLedger=VistaLiquid::Ledger();TapLedger.Source=TapLedger.Initial=0;
    if (Streams) {Streams->Pour.Reset();Streams->Tap.Reset();}
    for (auto* Fluid:{PourFluid.Get(),TapFluid.Get()})
        if (Fluid) {Fluid->SetVariableFloat(TEXT("User.SourceRate"),0);Fluid->ReinitializeSystem();Fluid->SetPaused(true);}
    SetPhase(EEmbodiedPhase::Idle);ReachAlpha=FingerAlpha=LeftReachAlpha=LeftFingerAlpha=0;
    bReachDetour=bFeetReady=false;UnreachableTime=0;
    Cast<APlayerController>(Controller)->SetViewTarget(this);
}
FString AVistaVillaCharacter::GetInteractionHint() const
{
    if (Clock<FeedbackUntil) return Feedback;
    return bPouring?TEXT("Pouring — keeping the rim above the mug"):
        TEXT("WASD move  |  Shift run  |  Space jump  |  E door / pick / place  |  P pour  |  F tap  |  Tab view  |  H tour  |  R reset");
}
void AVistaVillaCharacter::VillaDemo()
{
    if (!bReady || bDemo) return;
    EmbodiedReset();
    GetCharacterMovement()->StopMovementImmediately();
    SetActorLocation(FVector(1210,-1000,83),false,nullptr,ETeleportType::TeleportPhysics);
    SetActorRotation(FRotator(0,90,0));Controller->SetControlRotation(FRotator(-15,90,0));EmbodiedView(0);
    bStairSetup=bStairsPassed=bTourReady=bTourCaptured=false;TourIndex=0;
    bEmptyCaptured=bDownCaptured=bPourCaptured=bFlightCaptured=bPlacedCaptured=bTapCaptured=false;
    bDemo=true;DemoClock=0;DemoStage=0;FeedbackMessage(TEXT("Kitchen demonstration"));
}
void AVistaVillaCharacter::AdvanceDemo(float Dt)
{
    if (!bDemo) return;DemoClock+=Dt;
    auto Aim=[this](FVector P){FVector Eye;FRotator Look;Cast<APlayerController>(Controller)->GetPlayerViewPoint(Eye,Look);Controller->SetControlRotation((P-Eye).Rotation());};
    if (DemoStage==0)
    {
        if (DemoClock>1 && !bEmptyCaptured) {CaptureProof(TEXT("01_empty_hands"));bEmptyCaptured=true;}
        if (DemoClock>1.3f && DemoClock<2.3f) Controller->SetControlRotation(FRotator(-85,90,0));
        if (DemoClock>2.0f && !bDownCaptured) {CaptureProof(TEXT("01b_look_down_body"));bDownCaptured=true;}
        if (DemoClock>2.6f) {Controller->SetControlRotation(FRotator(-15,90,0));EmbodiedView(1);DemoStage=1;DemoClock=0;}
    }
    else if (DemoStage==1)
    {
        FVector Goal(1210,-967,83);FVector Delta=Goal-GetActorLocation();Delta.Z=0;
        if (Delta.Size()>3) AddMovementInput(Delta.GetSafeNormal(),1);
        else {GetCharacterMovement()->StopMovementImmediately();DemoStage=2;DemoClock=0;CaptureProof(TEXT("02_walk_and_stop"));}
    }
    else if (DemoStage==2)
    {
        EmbodiedView(0);Aim(Jug->GetActorLocation()+FVector(0,0,13));
        if (DemoClock>.8f) {EmbodiedInteract();DemoStage=3;DemoClock=0;}
    }
    else if (DemoStage==3)
    {
        if (Phase==EEmbodiedPhase::Held) {CaptureProof(TEXT("03_grasped_carafe"));VillaPour();DemoStage=4;DemoClock=0;}
    }
    else if (DemoStage==4)
    {
        Aim(Mug->GetActorLocation()+FVector(0,-3,13));
        if (DemoClock>2.3f && !bPourCaptured) {CaptureProof(TEXT("04_pouring"));bPourCaptured=true;}
        if (!bPouring && DemoClock>5.9f) {DemoStage=5;DemoClock=0;}
    }
    else if (DemoStage==5)
    {
        Aim(FVector(1200,-917,96));
        if (DemoClock>.8f) {EmbodiedPlace();DemoStage=6;DemoClock=0;}
    }
    else if (DemoStage==6 && Phase==EEmbodiedPhase::Idle)
    {
        if (!bPlacedCaptured) {CaptureProof(TEXT("05_placed"));bPlacedCaptured=true;DemoClock=0;return;}
        if (DemoClock<.3f) return;
        // Approach at an angle so the faucet stem does not occlude its stream.
        FVector Delta=FVector(1038,-967,GetActorLocation().Z)-GetActorLocation();
        if (Delta.Size()>3) AddMovementInput(Delta.GetSafeNormal(),1);
        else {GetCharacterMovement()->StopMovementImmediately();Aim(FVector(1080,-887,99));DemoStage=7;DemoClock=0;VillaTap();}
    }
    else if (DemoStage==7)
    {
        if (!bTapCaptured && DemoClock>2.) {CaptureProof(TEXT("06_tap_on"));bTapCaptured=true;DemoClock=0;}
        else if (bTapCaptured && DemoClock>.35) {VillaTap();DemoStage=8;DemoClock=0;}
    }
    else if (DemoStage==8 && DemoClock>1.0)
    {
        CaptureProof(TEXT("07_source_off_solver_alive"));DemoStage=9;DemoClock=0;
    }
    else if (DemoStage==9)
    {
        if (!bStairSetup)
        {
            if (DemoClock<.2f) return;
            // Set up the independent stair test after the preceding image has
            // rendered. All ascent uses CharacterMovement and mesh collision.
            SetActorLocation(FVector(1395,-90,83),false,nullptr,ETeleportType::TeleportPhysics);
            SetActorRotation(FRotator(0,-90,0));Controller->SetControlRotation(FRotator(-12,-90,0));bFeetReady=false;EmbodiedView(1);
            bStairSetup=true;DemoClock=0;return;
        }
        if (GetActorLocation().Y>-710) AddMovementInput(FVector(0,-1,0),1);
        else
        {
            GetCharacterMovement()->StopMovementImmediately();bStairsPassed=FMath::Abs(GetActorLocation().Z-402)<6;
            CaptureProof(TEXT("08_stair_landing"));DemoStage=10;DemoClock=0;
        }
    }
    else if (DemoStage==10)
    {
        if (!bTourReady && DemoClock>.2f)
        {
            if (TourIndex<TourCameras.Num())
            {
                Cast<APlayerController>(Controller)->SetViewTarget(TourCameras[TourIndex].Get());
                bTourReady=true;bTourCaptured=false;DemoClock=0;
            }
            else {bDemo=false;Cast<APlayerController>(Controller)->SetViewTarget(this);if (bProof) FinishProof();}
        }
        if (bTourReady && DemoClock>1.5f && !bTourCaptured)
        {CaptureProof(FString::Printf(TEXT("%02d_architecture"),9+TourIndex));bTourCaptured=true;}
        if (bTourReady && DemoClock>1.8f) {++TourIndex;bTourReady=false;DemoClock=0;}
    }
    if (DemoStage==8 && DemoClock>.1f && !bFlightCaptured) {CaptureProof(TEXT("07a_source_off_in_flight"));bFlightCaptured=true;}
    if (DemoClock>14)
    {UE_LOG(LogTemp,Error,TEXT("VILLA_DEMO_STAGE_TIMEOUT stage=%d position=%s"),DemoStage,*GetActorLocation().ToString());CaptureProof(TEXT("failed_stage"));bDemo=false;if (bProof) FinishProof();}
}
void AVistaVillaCharacter::CaptureProof(const FString& Name)
{
    if (bProof) PendingCapture=Name;
}
void AVistaVillaCharacter::OnPoseFinalized()
{
    Super::OnPoseFinalized();
    CaptureVillaMotionProof(this);
    CaptureAlpineProof(this);
    if (!PendingCapture.IsEmpty())
    {
        const FString Name=PendingCapture;PendingCapture.Empty();CaptureProofNow(Name);
        if (bFinishAfterCapture) {bFinishAfterCapture=false;FinishProof();}
    }
}
void AVistaVillaCharacter::CaptureProofNow(const FString& Name)
{
    if (!bProof) return;
    auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("name"),Name);R->SetNumberField(TEXT("time_s"),ProofClock);
    R->SetNumberField(TEXT("stage"),DemoStage);R->SetNumberField(TEXT("pickups"),CompletedPickups);R->SetNumberField(TEXT("placements"),CompletedPlacements);
    R->SetStringField(TEXT("snapshot_phase"),TEXT("after bone transforms finalized"));
    if (ReachAlpha>.99f) R->SetNumberField(TEXT("wrist_error_cm"),FVector::Distance(GetMesh()->GetSocketLocation(TEXT("hand_r")),LastHandGoal.GetLocation()));
    else R->SetField(TEXT("wrist_error_cm"),MakeShared<FJsonValueNull>());
    R->SetNumberField(TEXT("source_ml"),Liquid.Source);
    R->SetNumberField(TEXT("receiver_ml"),Liquid.Receiver);R->SetNumberField(TEXT("spill_ml"),Liquid.Spill);
    R->SetNumberField(TEXT("airborne_ml"),Liquid.Airborne());R->SetNumberField(TEXT("mass_residual_ml"),Liquid.Residual());
    R->SetNumberField(TEXT("jug_surface_ml"),JugRenderedMl);R->SetNumberField(TEXT("mug_surface_ml"),MugRenderedMl);
    R->SetStringField(TEXT("stream_model"),TEXT("ballistic sub-cell surface; Niagara coarse splashes"));
    R->SetNumberField(TEXT("pour_column_slices"),Streams?Streams->Pour.Slices.Num():0);
    R->SetNumberField(TEXT("tap_column_slices"),Streams?Streams->Tap.Slices.Num():0);
    R->SetBoolField(TEXT("tap_on"),bTap);R->SetNumberField(TEXT("tap_airborne_ml"),TapLedger.Airborne());
    R->SetBoolField(TEXT("gpu_solver_active_after_source_off"),PourFluid && PourFluid->IsActive() && TapFluid && TapFluid->IsActive());
    bool PourValid=false,TapValid=false;
    R->SetNumberField(TEXT("pour_source_particles_per_s"),PourFluid?PourFluid->GetVariableFloat(TEXT("User.SourceRate"),PourValid):0);
    R->SetNumberField(TEXT("tap_source_particles_per_s"),TapFluid?TapFluid->GetVariableFloat(TEXT("User.SourceRate"),TapValid):0);
    R->SetBoolField(TEXT("source_parameters_valid"),PourValid && TapValid);
    R->SetBoolField(TEXT("source_position_is_component_relative"),true);
    bool HeightValid=false;R->SetNumberField(TEXT("pour_initial_water_height"),PourFluid->GetVariableFloat(TEXT("User.Water Height"),HeightValid));
    R->SetBoolField(TEXT("water_height_binding_valid"),HeightValid);
    TArray<TSharedPtr<FJsonValue>> Systems;
    for (auto* Fluid:{PourFluid.Get(),TapFluid.Get()})
    {
        auto S=MakeShared<FJsonObject>();int32 Count=0;TArray<TSharedPtr<FJsonValue>> Emitters;
        if (Fluid && Fluid->GetSystemInstanceController())
        {
            auto C=Fluid->GetSystemInstanceController();C->WaitForConcurrentTickAndFinalize();
            if (auto* Instance=C->GetSystemInstance_Unsafe())
                for (const auto& E:Instance->GetEmitters())
                {
                    Count+=E->GetNumParticles();auto Detail=MakeShared<FJsonObject>();
                    Detail->SetStringField(TEXT("name"),E->GetEmitterHandle().GetName().ToString());
                    Detail->SetNumberField(TEXT("particles"),E->GetNumParticles());Detail->SetBoolField(TEXT("local_space"),E->IsLocalSpace());
                    const FBox Bounds=E->GetBounds();Detail->SetArrayField(TEXT("bounds_min"),Values(Bounds.Min));Detail->SetArrayField(TEXT("bounds_max"),Values(Bounds.Max));
                    Emitters.Add(MakeShared<FJsonValueObject>(Detail));
                }
        }
        S->SetStringField(TEXT("source"),Fluid==PourFluid?TEXT("pour"):TEXT("tap"));
        S->SetNumberField(TEXT("estimated_particles"),Count);Systems.Add(MakeShared<FJsonValueObject>(S));
        S->SetArrayField(TEXT("emitters"),Emitters);
    }
    R->SetArrayField(TEXT("visual_solver_particles_not_volume"),Systems);
    FVector Eye;FRotator View;Cast<APlayerController>(Controller)->GetPlayerViewPoint(Eye,View);
    R->SetArrayField(TEXT("camera_cm"),Values(Eye));R->SetArrayField(TEXT("camera_rotation"),Values(FVector(View.Pitch,View.Yaw,View.Roll)));
    R->SetArrayField(TEXT("actor_cm"),Values(GetActorLocation()));R->SetBoolField(TEXT("third_person"),bThirdPerson);
    R->SetStringField(TEXT("anim_instance"),GetMesh()->GetAnimInstance()?GetMesh()->GetAnimInstance()->GetClass()->GetName():TEXT("missing"));
    R->SetArrayField(TEXT("hand_r_cm"),Values(GetMesh()->GetSocketLocation(TEXT("hand_r"))));
    R->SetArrayField(TEXT("hand_goal_cm"),Values(LastHandGoal.GetLocation()));
    R->SetNumberField(TEXT("reach_alpha"),ReachAlpha);R->SetNumberField(TEXT("rest_alpha"),FirstPersonRestAlpha);
    R->SetArrayField(TEXT("jug_cm"),Values(Jug->GetActorLocation()));R->SetArrayField(TEXT("mug_cm"),Values(Mug->GetActorLocation()));
    Records.Add(MakeShared<FJsonValueObject>(R));FScreenshotRequest::RequestScreenshot(ProofDir/(Name+TEXT(".png")),false,false);
}
void AVistaVillaCharacter::FinishProof()
{
    if (!PendingCapture.IsEmpty()) {bFinishAfterCapture=true;return;}
    auto Out=MakeShared<FJsonObject>();Out->SetStringField(TEXT("schema"),TEXT("vista.villa-integration-proof/v1"));
    Out->SetArrayField(TEXT("records"),Records);Out->SetNumberField(TEXT("motion_library_frames"),Motions.Num());
    Out->SetNumberField(TEXT("pickups"),CompletedPickups);Out->SetNumberField(TEXT("placements"),CompletedPlacements);
    Out->SetNumberField(TEXT("cancelled_actions"),CancelledActions);Out->SetNumberField(TEXT("receiver_ml"),Liquid.Receiver);
    Out->SetNumberField(TEXT("mass_residual_ml"),Liquid.Residual());Out->SetBoolField(TEXT("demo_completed"),DemoStage==10 && TourIndex==TourCameras.Num());
    Out->SetBoolField(TEXT("stairs_reached_upper_floor"),bStairsPassed);
    Out->SetStringField(TEXT("volume_model"),TEXT("conservative reservoir/flight ledger; Niagara surface is not a mass measurement"));
    FrameTimes.Sort();if (FrameTimes.Num())
    {Out->SetNumberField(TEXT("frame_ms_median"),FrameTimes[FrameTimes.Num()/2]);Out->SetNumberField(TEXT("frame_ms_p95"),FrameTimes[FMath::Min(FrameTimes.Num()-1,int32(FrameTimes.Num()*.95))]);}
    FFileHelper::SaveStringToFile(Encode(Out),*(ProofDir/TEXT("proof.json")));
    bProof=false;FTimerHandle Exit;GetWorldTimerManager().SetTimer(Exit,[](){FGenericPlatformMisc::RequestExit(false);},1.f,false);
}
void AVistaVillaCharacter::Tick(float Dt)
{
    const double Now=FPlatformTime::Seconds();
    if (LastWallFrame>0 && bProof && bDemo) FrameTimes.Add((Now-LastWallFrame)*1000.);
    LastWallFrame=Now;
    LastFrameDt=Dt;TickAlpine(Dt);Super::Tick(Dt);if (!bReady) return;
    UpdateLiquids(Dt);ProofClock+=Dt;++ProofFrames;
    if (bProof && !bDemo && Records.IsEmpty() && ProofClock>5)
    {
#if WITH_EDITOR
        if (GShaderCompilingManager && GShaderCompilingManager->IsCompiling()) return;
#endif
        VillaDemo();
    }
    AdvanceDemo(Dt);
    TickVillaMotionProof(this,Dt);
    TickAlpineProof(this,Dt);
}
