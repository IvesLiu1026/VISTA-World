#include "VistaCompanion.h"
#include "VistaPathSteering.h"
#include "EmbodiedReview.h"
#include "HomeActionsJson.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNodeBase.h"
#include "Components/AudioComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/SpotLightComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/Base64.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Sound/SoundWaveProcedural.h"

using namespace HomeJson;
namespace {
struct FCompanionProxy final : FAnimInstanceProxy
{
    TArray<FTransform> Pose;
    explicit FCompanionProxy(UAnimInstance* I):FAnimInstanceProxy(I){}
    virtual void PreUpdate(UAnimInstance* I,float Dt) override
    {FAnimInstanceProxy::PreUpdate(I,Dt);if(auto* C=Cast<AVistaCompanion>(I->TryGetPawnOwner())) C->BuildPose(Pose);}
    virtual bool Evaluate(FPoseContext& Out) override
    {
        Out.ResetToRefPose();
        for(FCompactPoseBoneIndex I:Out.Pose.ForEachBoneIndex())
        {const int32 J=Out.Pose.GetBoneContainer().MakeMeshPoseIndex(I).GetInt();if(Pose.IsValidIndex(J)) Out.Pose[I]=Pose[J];}
        Out.Pose.NormalizeRotations();return true;
    }
};
}
FAnimInstanceProxy* UVistaCompanionAnim::CreateAnimInstanceProxy(){return new FCompanionProxy(this);}
void UVistaCompanionAnim::DestroyAnimInstanceProxy(FAnimInstanceProxy* P){delete P;}
AVistaCompanion::AVistaCompanion()
{
    PrimaryActorTick.bCanEverTick=true;AutoPossessPlayer=EAutoReceiveInput::Disabled;
    GetCapsuleComponent()->InitCapsuleSize(27,82);
    GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);
    auto* M=GetCharacterMovement();M->bRunPhysicsWithNoController=true;M->MaxWalkSpeed=145;
    M->MaxAcceleration=430;M->BrakingDecelerationWalking=650;M->bOrientRotationToMovement=false;
    GetMesh()->SetRelativeLocation(FVector(0,0,-82));GetMesh()->SetRelativeRotation(FRotator(0,-90,0));
    GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    GetMesh()->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    Speech=CreateDefaultSubobject<UAudioComponent>(TEXT("CompanionSpeech"));Speech->SetupAttachment(GetMesh(),TEXT("head"));
    Speech->bAutoActivate=false;Speech->bAllowSpatialization=true;Speech->bOverrideAttenuation=true;
    Speech->AttenuationOverrides.bAttenuate=true;Speech->AttenuationOverrides.AttenuationShapeExtents=FVector(180);
    Speech->AttenuationOverrides.FalloffDistance=1200;Speech->SetVolumeMultiplier(.85f);
    // A soft portrait fill keeps the companion legible against bright windows.
    FaceFill=CreateDefaultSubobject<USpotLightComponent>(TEXT("CompanionPortraitFill"));FaceFill->SetupAttachment(GetRootComponent());
    FaceFill->SetRelativeLocation(FVector(100,-65,88));FaceFill->SetRelativeRotation(FVector(-100,65,-18).Rotation());
    FaceFill->SetIntensityUnits(ELightUnits::Lumens);FaceFill->SetIntensity(240);FaceFill->SetAttenuationRadius(380);
    FaceFill->SetInnerConeAngle(35);FaceFill->SetOuterConeAngle(65);FaceFill->SetSourceRadius(16);FaceFill->SetCastShadows(false);
}
void AVistaCompanion::BeginPlay()
{
    Super::BeginPlay();FString Text;
    if(!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectConfigDir()/TEXT("VistaCompanion.json"))))return;
    auto Config=Decode(Text);auto* Mesh=LoadObject<USkeletalMesh>(nullptr,*String(Config,TEXT("mesh")));
    if(!Mesh)return;GetMesh()->SetSkeletalMesh(Mesh);GetMesh()->SetAnimInstanceClass(UVistaCompanionAnim::StaticClass());
    GetMesh()->AddTickPrerequisiteActor(this);GetMesh()->SetForcedLOD(1);LoadMotion();Previous=GetActorLocation();
    const TSharedPtr<FJsonObject>* Morphs;
    if(Config && Config->TryGetObjectField(TEXT("face_morphs"),Morphs))for(const auto& Row:(*Morphs)->Values)
        for(const auto& V:Row.Value->AsArray())if(Mesh->FindMorphTarget(FName(V->AsString())))FaceMorphs.FindOrAdd(FName(Row.Key)).Add(FName(V->AsString()));
    bReady=Idle.Num()==53 && Walk.Num()>1 && FaceMorphs.Contains(TEXT("JawOpen")) && FaceMorphs.Contains(TEXT("Blink"));
    UE_LOG(LogTemp,Display,TEXT("VISTA_COMPANION_READY bones=%d frames=%d face=%d"),Idle.Num(),Walk.Num(),bReady);
}
void AVistaCompanion::LoadMotion()
{
    FString Text;if(!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("VISTA/VillaR1/mocap.json"))))return;
    auto D=Decode(Text);if(!D || String(D,TEXT("schema"))!=TEXT("vista.continuous-walk/v2"))return;
    auto* P=LoadObject<UEmbodiedPoseLibrary>(nullptr,TEXT("/Game/VISTA/EmbodiedR1/DA_BodyPoses.DA_BodyPoses"));
    const auto& Ref=GetMesh()->GetSkeletalMeshAsset()->GetRefSkeleton();
    if(!P || Ref.GetNum()!=P->BoneNames.Num())return;
    TArray<int32> Mapping;const auto& Names=D->GetArrayField(TEXT("bone_names"));
    for(int32 I=0;I<Ref.GetNum();++I)
    {
        if(Ref.GetBoneName(I)!=P->BoneNames[I])return;
        int32 J=Names.IndexOfByPredicate([&](const auto& N){return N->AsString()==P->BoneNames[I].ToString();});if(J<0)return;
        Mapping.Add(J);Parents.Add(Ref.GetParentIndex(I));
        ReferenceGlobal.Add(Parents[I]>=0?Ref.GetRefBonePose()[I]*ReferenceGlobal[Parents[I]]:Ref.GetRefBonePose()[I]);
    }
    Head=Ref.FindBoneIndex(TEXT("head"));Spine=Ref.FindBoneIndex(TEXT("spine_03"));
    auto Read=[&](const TArray<TSharedPtr<FJsonValue>>& Rows){TArray<FTransform> R;
        for(int32 J:Mapping){const auto& V=Rows[J]->AsArray();R.Add(FTransform(FQuat(V[3]->AsNumber(),V[4]->AsNumber(),V[5]->AsNumber(),V[6]->AsNumber()).GetNormalized(),FVector(V[0]->AsNumber(),V[1]->AsNumber(),V[2]->AsNumber())));}return R;};
    auto Rest=Read(D->GetArrayField(TEXT("rest")));TArray<FTransform> RestGlobal;
    for(int32 I=0;I<Rest.Num();++I)RestGlobal.Add(Parents[I]>=0?Rest[I]*RestGlobal[Parents[I]]:Rest[I]);
    auto Retarget=[&](const TArray<TSharedPtr<FJsonValue>>& Rows){auto Src=Read(Rows);TArray<FTransform> G,R;TArray<FQuat> Q;
        for(int32 I=0;I<Src.Num();++I){G.Add(Parents[I]>=0?Src[I]*G[Parents[I]]:Src[I]);Q.Add((G[I].GetRotation()*RestGlobal[I].GetRotation().Inverse()*ReferenceGlobal[I].GetRotation()).GetNormalized());
            R.Add(FTransform(Parents[I]>=0?Q[Parents[I]].Inverse()*Q[I]:Q[I],P->Relaxed[I].GetTranslation()));
            if(P->BoneNames[I]==TEXT("pelvis"))R[I].AddToTranslation(Src[I].GetTranslation()-Rest[I].GetTranslation());}return R;};
    Idle=Retarget(D->GetArrayField(TEXT("idle")));Cycle=Number(D,TEXT("cycle_distance_cm"));
    if(Cycle<30 || Cycle>200){Idle.Empty();return;}
    for(const auto& V:D->GetArrayField(TEXT("frames")))Walk.Add(Retarget(V->AsObject()->GetArrayField(TEXT("pose"))));
    CurrentPose=Idle;
}
bool AVistaCompanion::PlaceNear(const AActor* Player)
{
    FCollisionQueryParams Q(SCENE_QUERY_STAT(CompanionSpawn),false,this);Q.AddIgnoredActor(Player);
    const auto* Pawn=Cast<APawn>(Player);const float ViewYaw=Pawn?Pawn->GetControlRotation().Yaw:Player->GetActorRotation().Yaw;
    const auto* Character=Cast<ACharacter>(Player);
    const float Feet=Player->GetActorLocation().Z-(Character?Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight():86);
    for(float Radius:{150.f,115.f})for(float Angle:{30.f,-30.f,80.f,-80.f,140.f,-140.f,180.f})
    {
        FVector V=FRotator(0,ViewYaw,0).Vector().RotateAngleAxis(Angle,FVector::UpVector)*Radius;
        FVector P=Player->GetActorLocation()+V;FHitResult Ground;
        if(!GetWorld()->LineTraceSingleByChannel(Ground,P+FVector(0,0,80),P-FVector(0,0,220),ECC_Visibility,Q) || Ground.ImpactNormal.Z<.8f || FMath::Abs(Ground.ImpactPoint.Z-Feet)>35)continue;
        P=Ground.ImpactPoint+FVector(0,0,84);
        if(GetWorld()->OverlapBlockingTestByChannel(P,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(28,82),Q))continue;
        FHitResult Wall;if(GetWorld()->LineTraceSingleByChannel(Wall,Player->GetActorLocation()+FVector(0,0,50),P+FVector(0,0,50),ECC_Visibility,Q))continue;
        SetActorLocation(P,false,nullptr,ETeleportType::TeleportPhysics);SetActorRotation(FRotator(0,(Player->GetActorLocation()-P).Rotation().Yaw,0));
        GetCharacterMovement()->StopMovementImmediately();Previous=P;LastLeader=Player->GetActorLocation();Trail.Empty();YieldTime=0;bBlocked=false;return true;
    }
    return false;
}
void AVistaCompanion::Tick(float Dt)
{
    Super::Tick(Dt);if(!bReady)return;
    const FVector Here=GetActorLocation();const float Moved=FVector::Dist2D(Here,Previous);Previous=Here;
    if(Moved<100){Travel+=Moved;Phase=FMath::Fmod(Phase+Moved/Cycle,1.f);}
    const bool Assisting=AssistStatus==TEXT("approaching") || AssistStatus==TEXT("reaching") || AssistStatus==TEXT("waiting_clearance");
    if(Assisting) TickAssist(Dt);
    if(Leader.IsValid() && !Assisting && AssistReach<=0)
    {
        const FVector P=Leader->GetActorLocation();
        // Explicit room/bookmark travel resets the companion too. Ordinary following is swept walking.
        if(bFollowing && !LastLeader.IsNearlyZero() && FVector::Distance(P,LastLeader)>450)PlaceNear(Leader.Get());
        if(bFollowing && (Trail.IsEmpty() || FVector::Distance(P,Trail.Last())>28))Trail.Add(P);
        LastLeader=P;
        while(Trail.Num()>1 && FVector::Distance(Here,Trail[0])<20)Trail.RemoveAt(0);
        if(Trail.Num()>600){Trail.RemoveAt(0,Trail.Num()-600);bBlocked=true;}
        const float Distance=FVector::Distance(Here,P);
        FCollisionQueryParams Path(SCENE_QUERY_STAT(CompanionDirectPath),false,this);Path.AddIgnoredActor(Leader.Get());
        FHitResult Obstacle;
        const bool Direct=FMath::Abs(Here.Z-P.Z)<35 && !GetWorld()->SweepSingleByChannel(Obstacle,Here,P,
            FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(27,82),Path);
        // A human reversing through a doorway must not be trapped by their
        // follower. Walk to a supported, swept-clear side position and wait
        // briefly for them to pass. Acceleration retains intent at contact.
        const FVector Along=Leader->GetCharacterMovement()->GetCurrentAcceleration().GetSafeNormal2D();
        const FVector Relative=Here-P;
        const float Ahead=FVector::DotProduct(Along,Relative);
        if (bFollowing && YieldTime<=0 && Distance<145 && FMath::Abs(Relative.Z)<35 && Ahead>0 &&
            (Relative-Along*Ahead).Size2D()<85 && !Along.IsNearlyZero())
        {
            const FVector Side=FVector::CrossProduct(Along,FVector::UpVector);
            // Beside a coffee table neither side is supported floor. Continue
            // through the narrow aisle to a clear landing instead of trapping
            // the leader. Every longer candidate still requires a clear swept
            // capsule and supported floor; never step onto furniture.
            for (const FVector Offset:{Side*90,-Side*90,Along*75,Side*65,-Side*65,Along*110,
                                       Along*170,Along*230,Along*290,Along*110+Side*90,Along*110-Side*90})
            {
                FVector Candidate=Here+Offset;FHitResult Floor,Block;
                if (!GetWorld()->LineTraceSingleByChannel(Floor,Candidate+FVector(0,0,70),Candidate-FVector(0,0,130),ECC_Visibility,Path) ||
                    Floor.ImpactNormal.Z<.8f || FMath::Abs(Floor.ImpactPoint.Z-(Here.Z-84))>25) continue;
                Candidate.Z=Floor.ImpactPoint.Z+84;
                if (GetWorld()->SweepSingleByChannel(Block,Here,Candidate,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(27,82),Path) ||
                    GetWorld()->OverlapBlockingTestByChannel(Candidate,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(28,82),Path)) continue;
                YieldGoal=Candidate;YieldTime=2.8f;Trail.Empty();break;
            }
        }
        // Keep doorway/stair breadcrumbs when the human is close across a
        // wall or on another floor. Planar distance used to erase that route.
        if (bFollowing && YieldTime>0)
        {
            YieldTime-=Dt;const FVector Delta=YieldGoal-Here;const FVector Direction=Delta.GetSafeNormal2D();
            const float Desired=Direction.Rotation().Yaw;
            const float Turn=FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw,Desired);
            if (Delta.Size2D()>12)
            {
                SetActorRotation(FRotator(0,FMath::FixedTurn(GetActorRotation().Yaw,Desired,150*Dt),0));
                if (FMath::Abs(Turn)<55) AddMovementInput(Direction,.85f,true);
            }
            else GetCharacterMovement()->StopMovementImmediately();
            StuckTime=0;bBlocked=false;
        }
        else if(bFollowing && Trail.Num() && (Distance>155 || !Direct))
        {
            // Pull only short, supported, capsule-clear chords through the human's
            // recorded trail. This previews bends without cutting a wall or stairwell.
            while (Trail.Num()>1 && FVector::Dist2D(Here,Trail[1])<95 &&
                   FMath::Abs(Here.Z-Trail[1].Z)<12 &&
                   VistaPathSteering::ClearFloorChord(this,FVector(Trail[1].X,Trail[1].Y,Here.Z),Leader.Get()))
                Trail.RemoveAt(0);
            FVector Goal=Trail[0];Goal.Z=Here.Z;FVector Direction=(Goal-Here).GetSafeNormal();
            if (Trail.Num()>1) Goal=VistaPathSteering::PreviewCorner(this,Trail[0],Trail[1],85,Leader.Get());
            Direction=VistaPathSteering::AvoidNearObstacle(this,Goal);
            float Desired=Direction.Rotation().Yaw;float Delta=FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw,Desired);
            SetActorRotation(FRotator(0,FMath::FixedTurn(GetActorRotation().Yaw,Desired,150*Dt),0));
            const bool Live=FParse::Param(FCommandLine::Get(),TEXT("VistaLiveAssistant"));
            const float DesiredSpeed=Live?FMath::Clamp(Leader->GetVelocity().Size2D()+25.f+(Distance-230)*.12f,120.f,240.f):145.f;
            GetCharacterMovement()->MaxWalkSpeed=FMath::FInterpTo(GetCharacterMovement()->MaxWalkSpeed,DesiredSpeed,Dt,3);
            const float Brake=FMath::Clamp(VistaPathSteering::ForwardClearance(this,Direction,95)/60.f,.22f,1.f);
            if(FMath::Abs(Delta)<75)AddMovementInput(Direction,FMath::Clamp((80-FMath::Abs(Delta))/35.f,.1f,1.f)*Brake,true);
            StuckTime=Moved<.03f?StuckTime+Dt:0;bBlocked=StuckTime>2;
        }
        else
        {
            GetCharacterMovement()->StopMovementImmediately();StuckTime=0;bBlocked=false;
            if(Direct && Distance<230)Trail.Empty();
            const float Look=(P-Here).Rotation().Yaw;
            const float Offset=FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw,Look);
            if(FMath::Abs(Offset)>35)SetActorRotation(FRotator(0,FMath::FixedTurn(GetActorRotation().Yaw,Look,80*Dt),0));
        }
    }
    MoveBlend=FMath::FInterpTo(MoveBlend,FMath::Clamp(GetVelocity().Size2D()/90.f,0.f,1.f),Dt,7);
    const float Frame=Phase*(Walk.Num()-1);const int32 A=FMath::FloorToInt(Frame),B=FMath::Min(A+1,Walk.Num()-1);
    CurrentPose=Idle;
    for(int32 I=0;I<CurrentPose.Num();++I){FTransform W;W.Blend(Walk[A][I],Walk[B][I],Frame-A);CurrentPose[I].Blend(Idle[I],W,MoveBlend);}
    PoseAssist(Dt);
    if(Leader.IsValid() && Head>=0)
    {
        TArray<FTransform> G;for(int32 I=0;I<CurrentPose.Num();++I)G.Add(Parents[I]>=0?CurrentPose[I]*G[Parents[I]]:CurrentPose[I]);
        float Yaw=FMath::Clamp(FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw,(Leader->GetActorLocation()-Here).Rotation().Yaw),-35.f,35.f)*(1-MoveBlend*.8f);
        FQuat Turn(FVector::UpVector,FMath::DegreesToRadians(Yaw));
        CurrentPose[Head].SetRotation((G[Parents[Head]].GetRotation().Inverse()*Turn*G[Head].GetRotation()).GetNormalized());
    }
    BlinkClock+=Dt;const float BlinkPhase=FMath::Fmod(BlinkClock,4.1f);
    const float Blink=BlinkPhase<.17f?FMath::Sin(BlinkPhase/.17f*PI)*.88f:0;
    Face(TEXT("Blink"),Blink);FVector MouthShape=FVector::ZeroVector;
    if(bSpeaking && Wave)
    {
        AudioClock=FMath::Clamp((AudioBytes-Wave->GetAvailableAudioByteCount())/(2.f*Rate),0.f,Wave->Duration);
        const int32 I=FMath::Clamp(FMath::FloorToInt(AudioClock*50),0,FMath::Max(0,Mouth.Num()-1));
        if(Mouth.IsValidIndex(I))MouthShape=Mouth[I];
        if(AudioClock>=Wave->Duration-.015f || !Speech->IsPlaying())StopSpeech();
    }
    MouthOpen=FMath::FInterpTo(MouthOpen,bSpeaking?MouthShape.X:0,Dt,18);
    Face(TEXT("JawOpen"),MouthOpen);
    Face(TEXT("MouthRound"),bSpeaking?MouthShape.Y:0);Face(TEXT("MouthWide"),bSpeaking?MouthShape.Z:0);
    Face(TEXT("Smile"),bSpeaking?.13f:.07f);
}
void AVistaCompanion::Face(FName Name,float Value)
{if(const auto* Names=FaceMorphs.Find(Name))for(FName Target:*Names)GetMesh()->SetMorphTarget(Target,Value);}
void AVistaCompanion::BuildPose(TArray<FTransform>& Out) const {Out=CurrentPose;}
void AVistaCompanion::Speak(const TSharedPtr<FJsonObject>& R)
{
    StopSpeech();TArray<uint8> PCM;if(!FBase64::Decode(String(R,TEXT("pcm_b64")),PCM) || PCM.Num()<2)return;
    Rate=Number(R,TEXT("sample_rate"));if(Rate<8000 || Rate>48000 || PCM.Num()>Rate*2*90)return;
    Wave=NewObject<USoundWaveProcedural>(this);Wave->SetSampleRate(Rate);Wave->NumChannels=1;Wave->Duration=PCM.Num()/(2.f*Rate);
    Wave->SoundGroup=SOUNDGROUP_Voice;Wave->bLooping=false;Wave->QueueAudio(PCM.GetData(),PCM.Num());AudioBytes=PCM.Num();AudioClock=0;
    for(const auto& Row:R->GetArrayField(TEXT("mouth"))){const auto& V=Row->AsArray();if(V.Num()==3)Mouth.Add(FVector(V[0]->AsNumber(),V[1]->AsNumber(),V[2]->AsNumber()));}
    Subtitle=String(R,TEXT("text"));Speech->SetSound(Wave);Speech->Play();bSpeaking=true;
}
void AVistaCompanion::StopSpeech(){Speech->Stop();bSpeaking=false;Mouth.Empty();if(Wave)Wave->ResetAudio();Wave=nullptr;}
