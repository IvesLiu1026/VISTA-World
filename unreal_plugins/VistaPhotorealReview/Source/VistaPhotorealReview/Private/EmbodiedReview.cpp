#include "EmbodiedReview.h"

#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Canvas.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputCoreTypes.h"
#include "PhysicsEngine/PhysicsHandleComponent.h"
#include "Serialization/JsonSerializer.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "TimerManager.h"
#include "UnrealClient.h"

namespace
{
float Ease(float V) { V=FMath::Clamp(V,0.f,1.f);return V*V*(3.f-2.f*V); }
TArray<TSharedPtr<FJsonValue>> VectorJson(FVector V)
{
    return {MakeShared<FJsonValueNumber>(V.X),MakeShared<FJsonValueNumber>(V.Y),MakeShared<FJsonValueNumber>(V.Z)};
}
FString PhaseName(EEmbodiedPhase P) { return StaticEnum<EEmbodiedPhase>()->GetNameStringByValue(int64(P)); }
}

AEmbodiedReviewCharacter::AEmbodiedReviewCharacter()
{
    GetCapsuleComponent()->InitCapsuleSize(27.f,82.f);
    GetCharacterMovement()->MaxWalkSpeed=125.f;
    GetCharacterMovement()->MaxAcceleration=430.f;
    GetCharacterMovement()->BrakingDecelerationWalking=650.f;
    GetCharacterMovement()->RotationRate=FRotator(0,360,0);
    GetMesh()->SetRelativeLocation(FVector(0,0,-82));
    GetMesh()->SetRelativeRotation(FRotator(0,-90,0));
    GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    GetMesh()->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    GetMesh()->PrimaryComponentTick.TickGroup=TG_PostPhysics;
    ReviewCamera->SetRelativeLocation(FVector(12.545f,0,60.645f));
    ReviewCamera->SetFieldOfView(78.f);
    ReviewCamera->SetEnableFirstPersonFieldOfView(true);
    ReviewCamera->SetFirstPersonFieldOfView(78.f);
    ReviewCamera->SetEnableFirstPersonScale(true);
    ReviewCamera->SetFirstPersonScale(1.f);
    OwnerBody=CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("OwnerBody"));
    OwnerBody->SetupAttachment(GetMesh());
    OwnerBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    OwnerBody->SetOnlyOwnerSee(true);
    OwnerBody->SetCastShadow(false);
    OwnerBody->PrimaryComponentTick.TickGroup=TG_PostPhysics;
    FollowBoom=CreateDefaultSubobject<USpringArmComponent>(TEXT("FollowBoom"));
    FollowBoom->SetupAttachment(GetCapsuleComponent());
    FollowBoom->SetRelativeLocation(FVector(0,0,15));
    FollowBoom->TargetArmLength=220.f;
    FollowBoom->SocketOffset=FVector(0,24,10);
    FollowBoom->ProbeSize=13.f;
    FollowBoom->bDoCollisionTest=true;
    FollowBoom->bUsePawnControlRotation=true;
    FollowBoom->bEnableCameraLag=true;
    FollowBoom->CameraLagSpeed=12.f;
    FollowBoom->CameraLagMaxDistance=12.f;
    FollowCamera=CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
    FollowCamera->SetupAttachment(FollowBoom,USpringArmComponent::SocketName);
    FollowCamera->SetFieldOfView(78.f);
    FollowCamera->SetAutoActivate(false);
    GripHandle=CreateDefaultSubobject<UPhysicsHandleComponent>(TEXT("CupGrip"));
    GripHandle->SetLinearStiffness(2400.f);
    GripHandle->SetLinearDamping(170.f);
    GripHandle->SetAngularStiffness(1800.f);
    GripHandle->SetAngularDamping(130.f);
    GripHandle->InterpolationSpeed=18.f;
}

void AEmbodiedReviewCharacter::BeginPlay()
{
    Super::BeginPlay();
    USkeletalMesh* WorldMesh=LoadObject<USkeletalMesh>(nullptr,TEXT("/Game/VISTA/EmbodiedR1/WorldBody/SK_WorldBody.SK_WorldBody"));
    USkeletalMesh* Headless=LoadObject<USkeletalMesh>(nullptr,TEXT("/Game/VISTA/EmbodiedR1/OwnerBody/SK_OwnerBody.SK_OwnerBody"));
    Poses=LoadObject<UEmbodiedPoseLibrary>(nullptr,TEXT("/Game/VISTA/EmbodiedR1/DA_BodyPoses.DA_BodyPoses"));
    for (TActorIterator<AStaticMeshActor> It(GetWorld());It;++It)
        if (It->ActorHasTag(TEXT("EmbodiedCup"))) { Cup=*It;CupMesh=It->GetStaticMeshComponent();break; }
    if (!WorldMesh || !Headless || !Poses || !CupMesh)
    {
        UE_LOG(LogTemp,Error,TEXT("EMBODIED_ASSET_MISSING body=%d owner=%d poses=%d cup=%d"),!!WorldMesh,!!Headless,!!Poses,!!CupMesh);
        FeedbackMessage(TEXT("Character assets are missing"));return;
    }
    const FReferenceSkeleton& Ref=WorldMesh->GetRefSkeleton();
    if (Poses->BoneNames.Num()!=Ref.GetNum() || Poses->Relaxed.Num()!=Ref.GetNum() || Poses->Grip.Num()!=Ref.GetNum())
    { UE_LOG(LogTemp,Error,TEXT("EMBODIED_RIG_MISMATCH"));return; }
    Parents.SetNum(Ref.GetNum());ReferenceGlobal.SetNum(Ref.GetNum());
    for (int32 I=0;I<Ref.GetNum();++I)
    {
        if (Poses->BoneNames[I]!=Ref.GetBoneName(I)) { UE_LOG(LogTemp,Error,TEXT("EMBODIED_BONE_ORDER_MISMATCH %d"),I);return; }
        Parents[I]=Ref.GetParentIndex(I);BoneIndex.Add(Ref.GetBoneName(I),I);
        ReferenceGlobal[I]=Parents[I]>=0 ? Ref.GetRefBonePose()[I]*ReferenceGlobal[Parents[I]] : Ref.GetRefBonePose()[I];
    }
    GetMesh()->SetSkeletalMesh(WorldMesh);
    GetMesh()->SetAnimInstanceClass(UEmbodiedBodyAnimInstance::StaticClass());
    GetMesh()->AddTickPrerequisiteActor(this);
    GetMesh()->SetForcedLOD(1);
    OwnerBody->SetSkeletalMesh(Headless);
    OwnerBody->SetLeaderPoseComponent(GetMesh(),true,false);
    OwnerBody->AddTickPrerequisiteComponent(GetMesh());
    OwnerBody->SetForcedLOD(1);
    InitialCupTransform=Cup->GetActorTransform();
    CupMesh->SetMobility(EComponentMobility::Movable);
    CupMesh->SetCollisionProfileName(TEXT("PhysicsActor"));
    CupMesh->SetCollisionResponseToChannel(ECC_Visibility,ECR_Block);
    CupMesh->SetMassOverrideInKg(NAME_None,.32f,true);
    CupMesh->SetLinearDamping(.16f);CupMesh->SetAngularDamping(.35f);
    CupMesh->BodyInstance.bUseCCD=true;
    CupMesh->SetSimulatePhysics(true);
    CupMesh->SetEnableGravity(true);
    LastHandGoal=GetMesh()->GetComponentTransform();
    bReady=true;
    BoneFinalizedHandle=GetMesh()->RegisterOnBoneTransformsFinalizedDelegate(
        FOnBoneTransformsFinalizedMultiCast::FDelegate::CreateUObject(this,&AEmbodiedReviewCharacter::OnPoseFinalized));
    if (APlayerController* PC=Cast<APlayerController>(Controller))
    {
        PC->ConsoleCommand(TEXT("r.FirstPerson.SelfShadow 1"),true);
        PC->ConsoleCommand(TEXT("r.FirstPerson.SelfShadow.LightTypes 2"),true);
    }
    EmbodiedView(0);
    FTimerHandle StartTimer;
    GetWorldTimerManager().SetTimer(StartTimer,[this](){ EmbodiedInspect(0); },1.1f,false);
    UE_LOG(LogTemp,Display,TEXT("EMBODIED_READY bones=%d cup_mass=%.3f"),Ref.GetNum(),CupMesh->GetMass());
}

void AEmbodiedReviewCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    Input->BindKey(EKeys::Tab,IE_Pressed,this,&AEmbodiedReviewCharacter::ToggleView);
    Input->BindKey(EKeys::E,IE_Pressed,this,&AEmbodiedReviewCharacter::EmbodiedInteract);
    Input->BindKey(EKeys::LeftMouseButton,IE_Pressed,this,&AEmbodiedReviewCharacter::EmbodiedInteract);
    Input->BindKey(EKeys::G,IE_Pressed,this,&AEmbodiedReviewCharacter::EmbodiedDrop);
    Input->BindKey(EKeys::R,IE_Pressed,this,&AEmbodiedReviewCharacter::EmbodiedReset);
    Input->BindKey(EKeys::Zero,IE_Pressed,this,&AEmbodiedReviewCharacter::ViewCup);
}

void AEmbodiedReviewCharacter::ToggleView() { EmbodiedView(bThirdPerson?0:1); }
void AEmbodiedReviewCharacter::EmbodiedView(int32 View)
{
    if (bThirdPerson && View==0 && Controller)
    {
        FRotator R=Controller->GetControlRotation();R.Yaw=GetActorRotation().Yaw;
        Controller->SetControlRotation(R);
    }
    bThirdPerson=View!=0;
    ReviewCamera->SetActive(!bThirdPerson,true);FollowCamera->SetActive(bThirdPerson,true);
    OwnerBody->SetVisibility(!bThirdPerson);
    OwnerBody->SetFirstPersonPrimitiveType(EFirstPersonPrimitiveType::FirstPerson);
    GetMesh()->SetFirstPersonPrimitiveType(bThirdPerson?EFirstPersonPrimitiveType::None:EFirstPersonPrimitiveType::WorldSpaceRepresentation);
    GetMesh()->SetOwnerNoSee(!bThirdPerson);
    bUseControllerRotationYaw=false;
    GetCharacterMovement()->bOrientRotationToMovement=bThirdPerson && Phase==EEmbodiedPhase::Idle;
    UE_LOG(LogTemp,Display,TEXT("EMBODIED_CAMERA mode=%s phase=%s serial=%d"),bThirdPerson?TEXT("third"):TEXT("first"),*PhaseName(Phase),TransitionSerial);
}

void AEmbodiedReviewCharacter::SetPhase(EEmbodiedPhase NewPhase)
{
    UE_LOG(LogTemp,Display,TEXT("EMBODIED_TRANSITION from=%s to=%s serial=%d"),*PhaseName(Phase),*PhaseName(NewPhase),++TransitionSerial);
    Phase=NewPhase;PhaseTime=0.f;UnreachableTime=0.f;
    GetCharacterMovement()->bOrientRotationToMovement=bThirdPerson && Phase==EEmbodiedPhase::Idle;
}

void AEmbodiedReviewCharacter::FeedbackMessage(const FString& Text)
{ Feedback=Text;FeedbackUntil=Clock+3.f; }

FTransform AEmbodiedReviewCharacter::DesiredGrip() const
{
    FTransform Result=Poses->WristRelativeToCup;
    const FVector Axis=CupMesh->GetUpVector();
    FQuat Orientation=FQuat::FindBetweenNormals(FVector::UpVector,Axis)*GetMesh()->GetComponentQuat();
    if (Axis.Z<.85f)
    {
        // Approach a tipped cup from its exposed upper side, not through the floor.
        FQuat Best=Orientation;float BestScore=-BIG_NUMBER;
        const FVector Shoulder=GetMesh()->GetSocketLocation(TEXT("upperarm_r"));
        for (int32 I=0;I<8;++I)
        {
            const FQuat Candidate=FQuat(Axis,I*PI/4.f)*Orientation;
            const FVector Offset=Candidate.RotateVector(Result.GetLocation());
            const float Score=Offset.Z*1.5f-FVector::Distance(CupMesh->GetComponentLocation()+Offset,Shoulder)*.8f;
            if (Score>BestScore) {BestScore=Score;Best=Candidate;}
        }
        Orientation=Best;
    }
    Result.SetLocation(CupMesh->GetComponentLocation()+Orientation.RotateVector(Result.GetLocation()));
    Result.SetRotation(Orientation*Result.GetRotation());
    return Result;
}

bool AEmbodiedReviewCharacter::IsCupReachable(FString& Reason) const
{
    if (!CupMesh || !bReady) {Reason=TEXT("Cup unavailable");return false;}
    FVector Eye;FRotator LookRotation;
    if (const APlayerController* PC=Cast<APlayerController>(Controller)) PC->GetPlayerViewPoint(Eye,LookRotation);
    else {Reason=TEXT("View unavailable");return false;}
    const FVector Center=CupMesh->Bounds.Origin;
    const float ReachLimit=Center.Z-GetMesh()->GetComponentLocation().Z<35.f?46.f:86.f;
    if (FVector::Dist2D(Center,GetActorLocation())>ReachLimit || FMath::Abs(Center.Z-GetActorLocation().Z)>110.f)
    {Reason=TEXT("Move closer to the cup");return false;}
    const float Alignment=FVector::DotProduct((Center-Eye).GetSafeNormal(),LookRotation.Vector());
    if (Alignment<.93f) {Reason=TEXT("Look at the cup");return false;}
    FCollisionQueryParams Params(SCENE_QUERY_STAT(EmbodiedReach),true,this);
    FHitResult Hit;
    if (GetWorld()->LineTraceSingleByChannel(Hit,Eye,Center,ECC_Visibility,Params) && Hit.GetActor()!=Cup)
    {Reason=TEXT("The cup is behind an obstacle");return false;}
    if (CupMesh->GetPhysicsLinearVelocity().Size()>45.f)
    {Reason=TEXT("Wait for the cup to settle");return false;}
    Reason=TEXT("E / click: pick up cup");return true;
}

void AEmbodiedReviewCharacter::EmbodiedInteract()
{
    if (!bReady) return;
    if (Phase==EEmbodiedPhase::Held) {EmbodiedPlace();return;}
    if (Phase!=EEmbodiedPhase::Idle) return;
    FString Reason;
    if (!IsCupReachable(Reason)) {FeedbackMessage(Reason);UE_LOG(LogTemp,Display,TEXT("EMBODIED_REJECT %s"),*Reason);return;}
    GetCharacterMovement()->StopMovementImmediately();
    const FTransform Grip=DesiredGrip();
    FCollisionQueryParams PathParams(SCENE_QUERY_STAT(EmbodiedHandApproach),true,this);PathParams.AddIgnoredActor(Cup);
    FHitResult PathHit;
    if (GetWorld()->SweepSingleByChannel(PathHit,GetMesh()->GetSocketLocation(TEXT("hand_r")),Grip.GetLocation(),
        FQuat::Identity,ECC_Visibility,FCollisionShape::MakeSphere(2.f),PathParams))
    {FeedbackMessage(TEXT("The hand path is blocked"));UE_LOG(LogTemp,Display,TEXT("EMBODIED_REJECT hand path blocked"));return;}
    HandRelativeToCup=Grip.GetRelativeTransform(CupMesh->GetComponentTransform());
    LastHandGoal=Grip;ReachStart=GetMesh()->GetSocketLocation(TEXT("hand_r"));
    SetPhase(EEmbodiedPhase::Reaching);
}

void AEmbodiedReviewCharacter::MeasureContact()
{
    if (!bReady) return;
    const FTransform Hand=GetMesh()->GetSocketTransform(TEXT("hand_r"));
    HandErrorCm=FVector::Distance(Hand.GetLocation(),LastHandGoal.GetLocation());
    HandAngleDeg=FMath::RadiansToDegrees(Hand.GetRotation().AngularDistance(LastHandGoal.GetRotation()));
}

void AEmbodiedReviewCharacter::CancelReach(const FString& Reason)
{
    UE_LOG(LogTemp,Display,TEXT("EMBODIED_CANCEL %s error_cm=%.3f"),*Reason,HandErrorCm);
    ++CancelledActions;
    if (GripHandle->GrabbedComponent) ReleaseCup(true);
    RetractFrom=ReachAlpha;SetPhase(EEmbodiedPhase::Retracting);FeedbackMessage(Reason);
}

FTransform AEmbodiedReviewCharacter::CarryTarget() const
{
    const FVector Bottom=GetActorLocation()+GetActorQuat().RotateVector(FVector(32,18,20));
    return FTransform(GetActorQuat()*HoldRelativeRotation,Bottom);
}

bool AEmbodiedReviewCharacter::FindPlacement(FVector& Location,FQuat& Rotation) const
{
    FVector Eye;FRotator LookRotation;
    const APlayerController* PC=Cast<APlayerController>(Controller);if (!PC) return false;
    PC->GetPlayerViewPoint(Eye,LookRotation);
    FCollisionQueryParams Params(SCENE_QUERY_STAT(EmbodiedPlacement),true,this);Params.AddIgnoredActor(Cup);
    FHitResult Hit;
    if (!GetWorld()->LineTraceSingleByChannel(Hit,Eye,Eye+LookRotation.Vector()*330.f,ECC_Visibility,Params)) return false;
    if (Hit.ImpactNormal.Z<.94f || FVector::Dist2D(Hit.ImpactPoint,GetActorLocation())>60.f) return false;
    // The complete cup base must be supported, not only its centre ray.
    for (int32 I=0;I<8;++I)
    {
        const float A=I*PI/4.f;
        const FVector P=Hit.ImpactPoint+FVector(FMath::Cos(A)*3.7f,FMath::Sin(A)*3.7f,0);
        FHitResult Support;
        if (!GetWorld()->LineTraceSingleByChannel(Support,P+FVector(0,0,2),P-FVector(0,0,3),ECC_Visibility,Params) ||
            Support.ImpactNormal.Z<.94f || FMath::Abs(Support.ImpactPoint.Z-Hit.ImpactPoint.Z)>1.f) return false;
    }
    Location=Hit.ImpactPoint+FVector(0,0,.25f);
    Rotation=FRotator(0,CupMesh->GetComponentRotation().Yaw,0).Quaternion();
    // Check the body volume above the support before entering placement.
    FHitResult Obstacle;
    if (GetWorld()->SweepSingleByChannel(Obstacle,Location+FVector(0,0,5),Location+FVector(0,0,5.1),
        FQuat::Identity,ECC_Visibility,FCollisionShape::MakeBox(FVector(4.1,4.1,4.2)),Params)) return false;
    return true;
}

void AEmbodiedReviewCharacter::EmbodiedPlace()
{
    if (Phase!=EEmbodiedPhase::Held) return;
    if (!FindPlacement(PlaceLocation,PlaceRotation)) {FeedbackMessage(TEXT("Look at a clear surface within reach"));return;}
    HoldStart=CupMesh->GetComponentTransform();
    GetCharacterMovement()->StopMovementImmediately();
    SetPhase(EEmbodiedPhase::Placing);
}

void AEmbodiedReviewCharacter::ReleaseCup(bool bDropped)
{
    if (!CupMesh) return;
    GripHandle->ReleaseComponent();
    CupMesh->SetEnableGravity(true);CupMesh->WakeAllRigidBodies();
    GetCapsuleComponent()->IgnoreActorWhenMoving(Cup,false);
    CupMesh->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);
    if (bDropped) ++CompletedDrops;else ++CompletedPlacements;
}

void AEmbodiedReviewCharacter::EmbodiedDrop()
{
    if (Phase==EEmbodiedPhase::Held || Phase==EEmbodiedPhase::Placing)
    { ReleaseCup(true);RetractFrom=ReachAlpha;SetPhase(EEmbodiedPhase::Retracting); }
    else if (Phase==EEmbodiedPhase::Reaching || Phase==EEmbodiedPhase::Closing) CancelReach(TEXT("Reach cancelled"));
}

void AEmbodiedReviewCharacter::UpdateInteraction(float Dt)
{
    PhaseTime+=Dt;
    if (Phase==EEmbodiedPhase::Idle)
    { ReachAlpha=0;FingerAlpha=0;FString Reason;bHasCandidate=IsCupReachable(Reason);return; }
    bHasCandidate=false;
    if (Phase==EEmbodiedPhase::Retracting)
    {
        ReachAlpha=RetractFrom*(1.f-Ease(PhaseTime/.55f));FingerAlpha=FMath::FInterpConstantTo(FingerAlpha,0.f,Dt,3.f);
        if (PhaseTime>=.55f) SetPhase(EEmbodiedPhase::Idle);
        return;
    }
    LastHandGoal=HandRelativeToCup*CupMesh->GetComponentTransform();
    MeasureContact();
    if (Phase==EEmbodiedPhase::Reaching || Phase==EEmbodiedPhase::Closing)
    {
        if (FVector::Dist2D(CupMesh->Bounds.Origin,GetActorLocation())>94.f || CupMesh->GetPhysicsLinearVelocity().Size()>80.f)
        {CancelReach(TEXT("Cup moved out of reach"));return;}
        ReachAlpha=Phase==EEmbodiedPhase::Reaching?Ease(PhaseTime/.85f):1.f;
        if (Phase==EEmbodiedPhase::Reaching && PhaseTime>=.85f)
        {
            if (HandErrorCm<1.f && HandAngleDeg<10.f) SetPhase(EEmbodiedPhase::Closing);
            else if (PhaseTime>1.8f) CancelReach(TEXT("Hand cannot safely reach the cup"));
        }
        else if (Phase==EEmbodiedPhase::Closing)
        {
            FingerAlpha=Ease(PhaseTime/.38f);
            if (PhaseTime>=.38f && HandErrorCm<1.f && HandAngleDeg<10.f)
            {
                GripHandle->GrabComponentAtLocationWithRotation(CupMesh,NAME_None,CupMesh->GetComponentLocation(),CupMesh->GetComponentRotation());
                if (!GripHandle->GrabbedComponent) {CancelReach(TEXT("Could not establish grip"));return;}
                HoldStart=CupMesh->GetComponentTransform();
                HoldRelativeRotation=GetActorQuat().Inverse()*HoldStart.GetRotation();
                GetCapsuleComponent()->IgnoreActorWhenMoving(Cup,true);
                CupMesh->SetCollisionResponseToChannel(ECC_Pawn,ECR_Ignore);
                ++CompletedPickups;SetPhase(EEmbodiedPhase::Held);
            }
            else if (PhaseTime>1.1f) CancelReach(TEXT("Contact was lost"));
        }
        return;
    }
    if (!GripHandle->GrabbedComponent) {CancelReach(TEXT("Grip released"));return;}
    ReachAlpha=1.f;FingerAlpha=1.f;
    FTransform Target;
    if (Phase==EEmbodiedPhase::Held)
    {
        Target.Blend(HoldStart,CarryTarget(),Ease(PhaseTime/.75f));
    }
    else if (Phase==EEmbodiedPhase::Releasing)
    {
        Target=FTransform(PlaceRotation,PlaceLocation);
    }
    else
    {
        Target.Blend(HoldStart,FTransform(PlaceRotation,PlaceLocation),Ease(PhaseTime/.95f));
        Target.AddToTranslation(FVector(0,0,6.f*FMath::Sin(FMath::Clamp(PhaseTime/.95f,0.f,1.f)*PI)));
    }
    // A sweep limits the controller target before the physical object contacts
    // a wall. The object always remains a dynamic body throughout the grip.
    FCollisionQueryParams Params(SCENE_QUERY_STAT(EmbodiedCarry),false,this);Params.AddIgnoredActor(Cup);
    FHitResult Hit;
    const FVector From=CupMesh->GetComponentLocation()+FVector(0,0,5);
    const FVector To=Target.GetLocation()+FVector(0,0,5);
    if (GetWorld()->SweepSingleByChannel(Hit,From,To,FQuat::Identity,ECC_Visibility,FCollisionShape::MakeSphere(3.7f),Params) && !Hit.bStartPenetrating)
    {
        const FVector Safe=FMath::Lerp(From,To,FMath::Max(0.f,Hit.Time-.04f));
        FVector Slide=Safe+FVector::VectorPlaneProject(To-Safe,Hit.Normal);
        FHitResult Corner;
        if (GetWorld()->SweepSingleByChannel(Corner,Safe,Slide,FQuat::Identity,ECC_Visibility,
            FCollisionShape::MakeSphere(3.7f),Params) && !Corner.bStartPenetrating)
            Slide=FMath::Lerp(Safe,Slide,FMath::Max(0.f,Corner.Time-.04f));
        // Preserve the requested height along a wall. Reusing the actual cup
        // height every frame would accumulate the spring's gravity deflection.
        Target.SetLocation(Slide-FVector(0,0,5));
    }
    GripHandle->SetTargetLocationAndRotation(Target.GetLocation(),Target.Rotator());
    MaxHeldError=FMath::Max(MaxHeldError,HandErrorCm);
    UnreachableTime=HandErrorCm>14.f?UnreachableTime+Dt:0.f;
    if (PhaseTime>.9f && (UnreachableTime>.25f || FVector::Dist2D(CupMesh->GetComponentLocation(),GetActorLocation())>96.f))
    {CancelReach(TEXT("Grip released at the obstruction"));return;}
    if (Phase==EEmbodiedPhase::Placing && PhaseTime>1.0f)
    {
        const float Error=FVector::Distance(CupMesh->GetComponentLocation(),PlaceLocation);
        if (Error<1.2f && CupMesh->GetPhysicsLinearVelocity().Size()<12.f && HandErrorCm<1.f && HandAngleDeg<10.f)
        {SetPhase(EEmbodiedPhase::Releasing);}
        else if (PhaseTime>3.f) {SetPhase(EEmbodiedPhase::Held);HoldStart=CupMesh->GetComponentTransform();FeedbackMessage(TEXT("Placement blocked"));}
    }
    if (Phase==EEmbodiedPhase::Releasing)
    {
        FingerAlpha=1.f-Ease(PhaseTime/.3f);
        if (PhaseTime>.3f) {ReleaseCup(false);RetractFrom=1;SetPhase(EEmbodiedPhase::Retracting);}
    }
}

void AEmbodiedReviewCharacter::UpdateFeet(float Dt)
{
    const FVector Root=GetMesh()->GetComponentLocation();
    const FQuat Facing=GetActorQuat();
    const FVector V=GetVelocity();
    const auto GroundAnkle=[this,&Facing](FVector Point)
    {
        FCollisionQueryParams P(SCENE_QUERY_STAT(EmbodiedFeet),true,this);P.AddIgnoredActor(Cup);
        float Height=-BIG_NUMBER;
        // A sole spans several floor boards. A single ray can fall through a
        // narrow board joint and incorrectly choose the structural floor below.
        const FVector Samples[]={FVector::ZeroVector,FVector(5,0,0),FVector(-5,0,0),FVector(0,3,0),FVector(0,-3,0)};
        for (const FVector& Sample:Samples)
        {
            const FVector At=Point+Facing.RotateVector(Sample);FHitResult Hit;
            if (GetWorld()->LineTraceSingleByChannel(Hit,At+FVector(0,0,22),At-FVector(0,0,30),ECC_Visibility,P) && Hit.ImpactNormal.Z>.7f)
                Height=FMath::Max(Height,float(Hit.ImpactPoint.Z)+6.22f);
        }
        if (Height>-BIG_NUMBER) Point.Z=Height;
        return Point;
    };
    FVector Desired[2];
    for (int32 I=0;I<2;++I)
    {
        Desired[I]=Root+Facing.RotateVector(FVector(1.15f,I==0?-12.f:12.f,6.22f));
        Desired[I]=GroundAnkle(Desired[I]);
    }
    if (!bFeetReady || FVector::Distance(PreviousLocation,GetActorLocation())>70.f || GetCharacterMovement()->IsFlying())
    {
        for (int32 I=0;I<2;++I) {Feet[I].Planted=Feet[I].Current=Feet[I].Goal=Desired[I];Feet[I].Progress=1;Feet[I].Yaw=GetActorRotation().Yaw;Feet[I].Roll=0;}
        bFeetReady=true;
    }
    PreviousLocation=GetActorLocation();
    const float Speed=V.Size2D();
    StepClock+=Dt*FMath::Clamp(Speed/100.f,0.f,1.7f);
    bool Swinging=Feet[0].Progress<1 || Feet[1].Progress<1;
    if (!Swinging)
    {
        for (int32 Pass=0;Pass<2;++Pass)
        {
            const int32 I=(NextFoot+Pass)%2;
            const float Distance=FVector::Dist2D(Feet[I].Current,Desired[I]);
            const float Turn=FMath::Abs(FMath::FindDeltaAngleDegrees(Feet[I].Yaw,GetActorRotation().Yaw));
            if (Distance>(Speed>8?9.f:4.f) || Turn>23.f)
            {
                const float SupportAhead=FVector::DotProduct(Root-Feet[1-I].Planted,V.GetSafeNormal2D());
                Feet[I].Duration=Speed>10?FMath::Clamp((26.f-SupportAhead)/Speed,.16f,.4f):.24f;
                Feet[I].Start=Feet[I].Current;
                Feet[I].Goal=Desired[I]+V.GetClampedToMaxSize2D(140)*(Feet[I].Duration+.2f);
                Feet[I].Goal.Z=Desired[I].Z;Feet[I].Goal=GroundAnkle(Feet[I].Goal);
                Feet[I].bMovingStep=Speed>10;Feet[I].Progress=0;NextFoot=1-I;break;
            }
        }
    }
    for (int32 I=0;I<2;++I)
    {
        if (Feet[I].Progress<1)
        {
            if (Speed<=10 && Feet[I].bMovingStep)
            {
                // When braking, lower the airborne foot at its current reach
                // instead of finishing a prediction made at full walking speed.
                Feet[I].Goal=GroundAnkle(Feet[I].Current);
                Feet[I].Start=Feet[I].Current;
                Feet[I].bMovingStep=false;
            }
            if (Feet[I].Progress<.8f && Speed>10)
            {
                const float Remaining=(1.f-Feet[I].Progress)*Feet[I].Duration;
                Feet[I].Goal=Desired[I]+V.GetClampedToMaxSize2D(140)*(Remaining+.2f);
                Feet[I].Goal.Z=Desired[I].Z;Feet[I].Goal=GroundAnkle(Feet[I].Goal);
                Feet[I].bMovingStep=true;
            }
            Feet[I].Progress=FMath::Min(1.f,Feet[I].Progress+Dt/Feet[I].Duration);
            const float T=Ease(Feet[I].Progress);
            Feet[I].Current=FMath::Lerp(Feet[I].Start,Feet[I].Goal,T)+FVector(0,0,FMath::Sin(Feet[I].Progress*PI)*(Speed>10?6.5f:3.f));
            Feet[I].Yaw=FMath::FixedTurn(Feet[I].Yaw,GetActorRotation().Yaw,Dt*540.f);
            Feet[I].Roll=FMath::FInterpConstantTo(Feet[I].Roll,0.f,Dt,180.f);
            if (Feet[I].Progress>=1) Feet[I].Planted=Feet[I].Current;
        }
        else
        {
            const FQuat FootYaw=FRotator(0,Feet[I].Yaw,0).Quaternion();
            const float Behind=FVector::DotProduct(Root-Feet[I].Planted,FootYaw.RotateVector(FVector::ForwardVector));
            const float Roll=Speed>10?FMath::Clamp((Behind-7.f)*2.1f,0.f,40.f):0.f;
            Feet[I].Roll=FMath::FInterpConstantTo(Feet[I].Roll,Roll,Dt,180.f);
            const FVector ToeOffset(10.845f,I==0?-.384f:.384f,-5.509f);
            const FVector ToeAnchor=Feet[I].Planted+FootYaw.RotateVector(ToeOffset);
            const FQuat Pitch(FVector::RightVector,FMath::DegreesToRadians(Feet[I].Roll));
            Feet[I].Current=ToeAnchor-FootYaw.RotateVector(Pitch.RotateVector(ToeOffset));
        }
        const FQuat FootYaw=FRotator(0,Feet[I].Yaw,0).Quaternion();
        const FQuat Pitch(FVector::RightVector,FMath::DegreesToRadians(Feet[I].Roll));
        Feet[I].ToeGoal=Feet[I].Current+FootYaw.RotateVector(Pitch.RotateVector(FVector(10.845f,I==0?-.384f:.384f,-5.509f)));
    }
}

void AEmbodiedReviewCharacter::Tick(float Dt)
{
    Super::Tick(Dt);Clock+=Dt;
    if (!bReady) return;
    // Keep the look response immediate while the physical body and carried
    // object turn together at a finite speed.
    if ((!bThirdPerson || Phase!=EEmbodiedPhase::Idle) && Controller)
    {
        const float TurnSpeed=Phase==EEmbodiedPhase::Held?180.f:300.f;
        SetActorRotation(FRotator(0,FMath::FixedTurn(GetActorRotation().Yaw,Controller->GetControlRotation().Yaw,Dt*TurnSpeed),0));
    }
    UpdateFeet(Dt);UpdateInteraction(Dt);
    if (TraceRemaining>0.f)
    {
        TraceRemaining-=Dt;
    }
    ReviewCamera->SetFirstPersonFieldOfView(ReviewCamera->FieldOfView);
    const bool Busy=Phase==EEmbodiedPhase::Reaching || Phase==EEmbodiedPhase::Closing || Phase==EEmbodiedPhase::Placing || Phase==EEmbodiedPhase::Releasing;
    GetCharacterMovement()->MaxWalkSpeed=Busy?0.f:(Phase==EEmbodiedPhase::Held?95.f:125.f);
    // Calibrated from the fitted eye mesh, rather than from the head joint's
    // centre. A camera at the joint can look through the open shirt collar.
    const int32 HeadIndex=BoneIndex.FindChecked(TEXT("head"));
    const FVector EyeInHead=ReferenceGlobal[HeadIndex].InverseTransformPosition(FVector(0,12.545f,145.045f));
    const FVector EyeWorld=GetMesh()->GetSocketTransform(TEXT("head")).TransformPosition(EyeInHead);
    FVector EyeTarget=GetActorTransform().InverseTransformPosition(EyeWorld);
    EyeTarget.X=FMath::Clamp(EyeTarget.X,10.f,30.f);
    const FVector SmoothedEye=FMath::VInterpTo(ReviewCamera->GetRelativeLocation(),EyeTarget,Dt,6.f);
    FVector EyePosition=GetActorTransform().TransformPosition(SmoothedEye);
    const FVector EyeBase=GetActorTransform().TransformPosition(FVector(12.545f,0,60.645f));
    FCollisionQueryParams EyeParams(SCENE_QUERY_STAT(EmbodiedEye),true,this);EyeParams.AddIgnoredActor(Cup);
    FHitResult EyeHit;
    if (GetWorld()->SweepSingleByChannel(EyeHit,EyeBase,EyePosition,FQuat::Identity,ECC_Visibility,
        FCollisionShape::MakeSphere(2.f),EyeParams) && !EyeHit.bStartPenetrating) EyePosition=EyeHit.Location;
    ReviewCamera->SetRelativeLocation(GetActorTransform().InverseTransformPosition(EyePosition));
    if (const APlayerController* PC=Cast<APlayerController>(Controller))
    {
        if (PC->PlayerCameraManager)
        { PC->PlayerCameraManager->ViewPitchMin=-89.f;PC->PlayerCameraManager->ViewPitchMax=74.f; }
    }
}

void AEmbodiedReviewCharacter::EmbodiedInspect(int32 View)
{
    if (View==0) {SetView(FVector(391,317,86),FRotator(bThirdPerson?-24.f:-50.f,180,0));SetActorRotation(FRotator(0,180,0));}
    if (View==1) SetView(FVector(40,265,86),FRotator(-89,-90,0));
    if (View==2) SetView(FVector(-320,260,86),FRotator(-12,-90,0));
    bFeetReady=false;
}

void AEmbodiedReviewCharacter::EmbodiedCamera(float Pitch,float Yaw)
{ if (Controller) Controller->SetControlRotation(FRotator(FMath::Clamp(Pitch,-89.f,74.f),Yaw,0)); }

void AEmbodiedReviewCharacter::EmbodiedReset()
{
    if (!bReady) return;
    if (GripHandle->GrabbedComponent) ReleaseCup(true);
    CupMesh->SetPhysicsLinearVelocity(FVector::ZeroVector);CupMesh->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
    CupMesh->SetWorldTransform(InitialCupTransform,false,nullptr,ETeleportType::TeleportPhysics);
    CupMesh->WakeAllRigidBodies();ReachAlpha=FingerAlpha=0;SetPhase(EEmbodiedPhase::Idle);EmbodiedInspect(0);
}

void AEmbodiedReviewCharacter::EmbodiedCup(float X,float Y,float Z,float Yaw)
{
    if (!bReady || Phase!=EEmbodiedPhase::Idle) return;
    CupMesh->SetPhysicsLinearVelocity(FVector::ZeroVector);CupMesh->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
    CupMesh->SetWorldLocationAndRotation(FVector(X,Y,Z),FRotator(0,Yaw,0),false,nullptr,ETeleportType::TeleportPhysics);
    CupMesh->WakeAllRigidBodies();
}

FString AEmbodiedReviewCharacter::GetInteractionHint() const
{
    if (Clock<FeedbackUntil) return Feedback;
    if (Phase==EEmbodiedPhase::Held) return TEXT("E / click: place on surface     G: let go");
    if (Phase==EEmbodiedPhase::Idle) return bHasCandidate?TEXT("E / click: pick up cup"):TEXT("Walk closer and look at the cup");
    return Phase==EEmbodiedPhase::Retracting?TEXT("Returning hand"):TEXT("Reaching and handling cup");
}

void AEmbodiedReviewCharacter::EmbodiedState()
{
    if (!bReady) return;
    MeasureContact();
    TSharedRef<FJsonObject> O=MakeShared<FJsonObject>();
    O->SetStringField(TEXT("phase"),PhaseName(Phase));O->SetBoolField(TEXT("third_person"),bThirdPerson);
    O->SetNumberField(TEXT("time"),Clock);O->SetNumberField(TEXT("dt"),GetWorld()->GetDeltaSeconds());
    O->SetArrayField(TEXT("location"),VectorJson(GetActorLocation()));O->SetArrayField(TEXT("cup"),VectorJson(CupMesh->GetComponentLocation()));
    O->SetArrayField(TEXT("cup_velocity"),VectorJson(CupMesh->GetPhysicsLinearVelocity()));
    const FRotator CR=CupMesh->GetComponentRotation();
    O->SetArrayField(TEXT("cup_rotation"),VectorJson(FVector(CR.Pitch,CR.Yaw,CR.Roll)));
    O->SetArrayField(TEXT("hand"),VectorJson(GetMesh()->GetSocketLocation(TEXT("hand_r"))));
    O->SetArrayField(TEXT("hand_goal"),VectorJson(LastHandGoal.GetLocation()));
    O->SetNumberField(TEXT("contact_error_cm"),HandErrorCm);O->SetNumberField(TEXT("contact_angle_deg"),HandAngleDeg);
    O->SetNumberField(TEXT("reach_alpha"),ReachAlpha);O->SetNumberField(TEXT("finger_alpha"),FingerAlpha);
    O->SetBoolField(TEXT("constraint"),GripHandle->GrabbedComponent!=nullptr);O->SetBoolField(TEXT("simulated"),CupMesh->IsSimulatingPhysics());
    O->SetNumberField(TEXT("cup_mass_kg"),CupMesh->GetMass());
    O->SetNumberField(TEXT("pickups"),CompletedPickups);O->SetNumberField(TEXT("placements"),CompletedPlacements);O->SetNumberField(TEXT("drops"),CompletedDrops);
    O->SetNumberField(TEXT("cancellations"),CancelledActions);O->SetNumberField(TEXT("serial"),TransitionSerial);
    O->SetNumberField(TEXT("movement"),int32(GetCharacterMovement()->MovementMode));
    O->SetArrayField(TEXT("foot_l"),VectorJson(GetMesh()->GetSocketLocation(TEXT("foot_l"))));
    O->SetArrayField(TEXT("foot_r"),VectorJson(GetMesh()->GetSocketLocation(TEXT("foot_r"))));
    O->SetArrayField(TEXT("foot_l_goal"),VectorJson(Feet[0].Current));O->SetArrayField(TEXT("foot_r_goal"),VectorJson(Feet[1].Current));
    O->SetNumberField(TEXT("foot_l_progress"),Feet[0].Progress);O->SetNumberField(TEXT("foot_r_progress"),Feet[1].Progress);
    O->SetArrayField(TEXT("toe_l"),VectorJson(GetMesh()->GetSocketLocation(TEXT("ball_l"))));
    O->SetArrayField(TEXT("toe_r"),VectorJson(GetMesh()->GetSocketLocation(TEXT("ball_r"))));
    O->SetArrayField(TEXT("toe_l_goal"),VectorJson(Feet[0].ToeGoal));O->SetArrayField(TEXT("toe_r_goal"),VectorJson(Feet[1].ToeGoal));
    O->SetNumberField(TEXT("foot_l_roll"),Feet[0].Roll);O->SetNumberField(TEXT("foot_r_roll"),Feet[1].Roll);
    O->SetArrayField(TEXT("knee_l"),VectorJson(GetMesh()->GetSocketLocation(TEXT("calf_l"))));
    O->SetArrayField(TEXT("knee_r"),VectorJson(GetMesh()->GetSocketLocation(TEXT("calf_r"))));
    O->SetArrayField(TEXT("pelvis"),VectorJson(GetMesh()->GetSocketLocation(TEXT("pelvis"))));
    FVector Eye;FRotator Rotation;if (APlayerController* PC=Cast<APlayerController>(Controller)) PC->GetPlayerViewPoint(Eye,Rotation);
    O->SetArrayField(TEXT("camera"),VectorJson(Eye));O->SetArrayField(TEXT("rotation"),VectorJson(FVector(Rotation.Pitch,Rotation.Yaw,Rotation.Roll)));
    FString Text;FJsonSerializer::Serialize(O,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
    UE_LOG(LogTemp,Display,TEXT("EMBODIED_STATE %s"),*Text);
}

void AEmbodiedReviewCharacter::ReviewSnapshot()
{ bCapturePending=true; }

void AEmbodiedReviewCharacter::OnPoseFinalized()
{
    if (!bReady) return;
    if (bCapturePending || TraceRemaining>0.f) EmbodiedState();
    if (bCapturePending)
    {
        bCapturePending=false;FScreenshotRequest::RequestScreenshot(TEXT("EmbodiedReview"),true,true);
    }
}

void AEmbodiedReviewCharacter::EmbodiedTrace(float Seconds)
{TraceRemaining=FMath::Clamp(Seconds,0.f,300.f);}

void AEmbodiedReviewCharacter::EmbodiedPosition(float X,float Y,float Z,float Yaw)
{
    SetView(FVector(X,Y,Z),FRotator(-50,Yaw,0));SetActorRotation(FRotator(0,Yaw,0));bFeetReady=false;
}

void AEmbodiedReviewCharacter::EmbodiedTestStand(float HeightCm,float CupYaw)
{
    if (!bReady) return;
    EmbodiedReset();
    if (TestStand) {TestStand->Destroy();TestStand=nullptr;}
    if (HeightCm<=0.f) return;
    // Explicit validation fixture only; never saved into the residential map.
    const float Height=FMath::Clamp(HeightCm,60.f,110.f);
    UStaticMesh* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));if (!Cube) return;
    TestStand=GetWorld()->SpawnActor<AStaticMeshActor>();
    UStaticMeshComponent* StandMesh=TestStand->GetStaticMeshComponent();
    StandMesh->SetMobility(EComponentMobility::Movable);StandMesh->SetStaticMesh(Cube);
    StandMesh->SetCollisionProfileName(TEXT("BlockAll"));
    TestStand->SetActorLocation(FVector(0,0,Height*.5f+.3f));
    TestStand->SetActorScale3D(FVector(.7f,.7f,Height/100.f));
    EmbodiedView(0);EmbodiedPosition(86,0,86,180);
    EmbodiedCup(24,0,Height+.55f,CupYaw);
    EmbodiedCamera(FMath::RadiansToDegrees(FMath::Atan2(Height+4.8f-151.f,59.f)),180);
    UE_LOG(LogTemp,Display,TEXT("EMBODIED_TEST_STAND height_cm=%.2f yaw=%.2f"),Height,CupYaw);
}

void AEmbodiedReviewCharacter::EmbodiedBones()
{
    if (!bReady) return;
    TSharedRef<FJsonObject> O=MakeShared<FJsonObject>();
    for (FName Name:Poses->BoneNames)
    {
        const FTransform T=GetMesh()->GetSocketTransform(Name,RTS_Component);
        const FVector P=T.GetLocation();const FQuat Q=T.GetRotation();
        O->SetArrayField(Name.ToString(),{MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z),
            MakeShared<FJsonValueNumber>(Q.X),MakeShared<FJsonValueNumber>(Q.Y),MakeShared<FJsonValueNumber>(Q.Z),MakeShared<FJsonValueNumber>(Q.W)});
    }
    FString Text;FJsonSerializer::Serialize(O,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
    UE_LOG(LogTemp,Display,TEXT("EMBODIED_BONES %s"),*Text);
    TSharedRef<FJsonObject> Bind=MakeShared<FJsonObject>();
    const TArray<FMatrix44f>& Inverse=GetMesh()->GetSkeletalMeshAsset()->GetRefBasesInvMatrix();
    for (int32 I=0;I<Inverse.Num();++I)
    {
        const FTransform T(FMatrix(Inverse[I].Inverse()));
        const FVector P=T.GetLocation();const FQuat Q=T.GetRotation();
        Bind->SetArrayField(Poses->BoneNames[I].ToString(),{MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z),
            MakeShared<FJsonValueNumber>(Q.X),MakeShared<FJsonValueNumber>(Q.Y),MakeShared<FJsonValueNumber>(Q.Z),MakeShared<FJsonValueNumber>(Q.W)});
    }
    Text.Reset();FJsonSerializer::Serialize(Bind,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
    UE_LOG(LogTemp,Display,TEXT("EMBODIED_BIND %s"),*Text);
}

void AEmbodiedReviewCharacter::EndPlay(const EEndPlayReason::Type Reason)
{
    GetMesh()->UnregisterOnBoneTransformsFinalizedDelegate(BoneFinalizedHandle);
    if (GripHandle) GripHandle->ReleaseComponent();Super::EndPlay(Reason);
}

void AEmbodiedReviewHUD::DrawHUD()
{
    Super::DrawHUD();if (!Canvas) return;
    const AEmbodiedReviewCharacter* C=Cast<AEmbodiedReviewCharacter>(GetOwningPawn());if (!C) return;
    DrawRect(FLinearColor(.018f,.027f,.024f,.78f),22,20,770,103);
    DrawText(TEXT("VISTA  /  HOME INTERACTION"),FLinearColor(.94f,.94f,.86f),38,29,nullptr,1.4f);
    DrawText(TEXT("WASD + mouse  |  Tab: first / third person  |  E / click: pick up / place  |  G: let go"),FLinearColor(.88f,.9f,.84f),38,57,nullptr,1.f);
    DrawText(TEXT("1-6: rooms   0: cup view   R: reset cup   V: other angle   Esc: cursor"),FLinearColor(.77f,.8f,.74f),38,79,nullptr,1.f);
    DrawText(C->IsThirdPerson()?TEXT("THIRD PERSON"):TEXT("FIRST PERSON"),FLinearColor(.62f,.79f,.69f),38,101,nullptr,.9f);
    const float X=Canvas->SizeX*.5f,Y=Canvas->SizeY*.5f;
    DrawRect(FLinearColor(.95f,.95f,.9f,.8f),X-2,Y-2,4,4);
    DrawRect(FLinearColor(.018f,.027f,.024f,.78f),X-215,Canvas->SizeY-66,430,36);
    DrawText(C->GetInteractionHint(),FLinearColor(.93f,.95f,.87f),X-198,Canvas->SizeY-57,nullptr,1.f);
}

AEmbodiedReviewGameMode::AEmbodiedReviewGameMode()
{DefaultPawnClass=AEmbodiedReviewCharacter::StaticClass();HUDClass=AEmbodiedReviewHUD::StaticClass();}
