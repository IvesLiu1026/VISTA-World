#include "VistaVillaCharacter.h"
#include "HomeActionsJson.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

using namespace HomeJson;

void AVistaVillaCharacter::LoadAlpineMotion()
{
    FString Text;
    if (!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectContentDir()/TEXT("VISTA/AlpineR3/locomotion.json")))) return;
    const auto Data=Decode(Text);
    if (!Data || String(Data,TEXT("schema"))!=TEXT("vista.directional-locomotion/v1")) return;
    const auto& Names=Data->GetArrayField(TEXT("bone_names"));
    if (Names.Num()!=Parents.Num()) return;
    for (int32 I=0;I<Names.Num();++I) if (Names[I]->AsString()!=Poses->BoneNames[I].ToString()) return;
    const auto Read=[](const TArray<TSharedPtr<FJsonValue>>& Rows)
    {
        TArray<FTransform> Result;
        for (const auto& Row:Rows)
        {
            const auto& V=Row->AsArray();
            Result.Add(FTransform(FQuat(V[3]->AsNumber(),V[4]->AsNumber(),V[5]->AsNumber(),V[6]->AsNumber()).GetNormalized(),FVector(V[0]->AsNumber(),V[1]->AsNumber(),V[2]->AsNumber())));
        }
        return Result;
    };
    auto Rest=Read(Data->GetArrayField(TEXT("rest")));TArray<FTransform> RestGlobal;
    for (int32 I=0;I<Rest.Num();++I) RestGlobal.Add(Parents[I]>=0?Rest[I]*RestGlobal[Parents[I]]:Rest[I]);
    for (const auto& Pair:Data->GetObjectField(TEXT("clips"))->Values)
    {
        const auto C=Pair.Value->AsObject();FAlpineMotionClip Clip;
        Clip.Duration=Number(C,TEXT("duration_s"));Clip.Distance=Number(C,TEXT("cycle_distance_cm"));
        for (const auto& Value:C->GetArrayField(TEXT("frames")))
        {
            const auto F=Value->AsObject();const auto Source=Read(F->GetArrayField(TEXT("pose")));
            if (Source.Num()!=Parents.Num()) {AlpineClips.Empty();return;}
            FVillaMotionFrame Frame;TArray<FTransform> Global;TArray<FQuat> Target;
            for (int32 I=0;I<Source.Num();++I)
            {
                Global.Add(Parents[I]>=0?Source[I]*Global[Parents[I]]:Source[I]);
                Target.Add((Global[I].GetRotation()*RestGlobal[I].GetRotation().Inverse()*ReferenceGlobal[I].GetRotation()).GetNormalized());
                Frame.Pose.Add(FTransform(Parents[I]>=0?Target[Parents[I]].Inverse()*Target[I]:Target[I],Poses->Relaxed[I].GetTranslation()));
                if (Poses->BoneNames[I]==TEXT("pelvis")) Frame.Pose[I].AddToTranslation(Source[I].GetTranslation()-Rest[I].GetTranslation());
            }
            Frame.Phase=Number(F,TEXT("phase"));Frame.Speed=Number(F,TEXT("speed_cm_s"));Frame.SourceFrame=Number(F,TEXT("source_frame"));
            for (int32 S=0;S<2;++S) Frame.Contact[S]=F->GetArrayField(TEXT("contacts"))[S]->AsNumber();
            Clip.Frames.Add(MoveTemp(Frame));
        }
        if (Clip.Frames.Num()<2 || Clip.Duration<=0) {AlpineClips.Empty();return;}
        AlpineClips.Add(Pair.Key,MoveTemp(Clip));
    }
    const TCHAR* Directions[]={TEXT("fwd"),TEXT("fwd_left"),TEXT("left"),TEXT("bwd_left"),TEXT("bwd"),TEXT("bwd_right"),TEXT("right"),TEXT("fwd_right")};
    for (const TCHAR* D:Directions) for (const TCHAR* G:{TEXT("walk_"),TEXT("run_")})
        if (!AlpineClips.Contains(FString(G)+D)) {AlpineClips.Empty();return;}
    for (const TCHAR* Key:{TEXT("jump"),TEXT("fall"),TEXT("land")}) if (!AlpineClips.Contains(Key)) {AlpineClips.Empty();return;}
    GetCharacterMovement()->JumpZVelocity=360.f;GetCharacterMovement()->AirControl=.28f;
    GetCharacterMovement()->MaxAcceleration=650.f;GetCharacterMovement()->BrakingDecelerationWalking=900.f;
    for (TActorIterator<AStaticMeshActor> It(GetWorld());It;++It) if (It->ActorHasTag(TEXT("AlpineGardenPanel")))
    {GardenPanels.Add(*It);GardenClosed.Add(It->GetActorLocation());}
    UE_LOG(LogTemp,Display,TEXT("ALPINE_MOTION_READY clips=%d garden_panels=%d"),AlpineClips.Num(),GardenPanels.Num());
}

float AVistaVillaCharacter::UnoccupiedMovementSpeed() const {return bRunning && !AlpineClips.IsEmpty()?350.f:125.f;}
bool AVistaVillaCharacter::UsesGroundFootIK() const {return AlpineClips.IsEmpty() || !GetCharacterMovement()->IsFalling();}
void AVistaVillaCharacter::StartRunning() {bRunning=true;}
void AVistaVillaCharacter::StopRunning() {bRunning=false;}
void AVistaVillaCharacter::StartAlpineJump()
{
    if (AlpineClips.IsEmpty() || Phase!=EEmbodiedPhase::Idle || bSceneActionBusy || bDemo || !GetCharacterMovement()->IsMovingOnGround()) return;
    Jump();AirClock=0;LandClock=10;bFeetReady=false;
}
void AVistaVillaCharacter::Landed(const FHitResult& Hit)
{Super::Landed(Hit);LandClock=0;AirClock=0;bFeetReady=false;bAlpineAir=false;}

bool AVistaVillaCharacter::TryGardenDoor()
{
    if (GardenPanels.IsEmpty() || Phase!=EEmbodiedPhase::Idle || bSceneActionBusy || !Controller) return false;
    // The GLB retains architectural coordinates; the actor origin is not the
    // door's centre. Use the closed portal bounds even while its leaf is open.
    const FVector Portal(439.5,-1201,132);
    FVector Eye;FRotator View;Cast<APlayerController>(Controller)->GetPlayerViewPoint(Eye,View);
    if (FVector::Dist2D(GetActorLocation(),Portal)>240 || FVector::DotProduct((Portal-Eye).GetSafeNormal(),View.Vector())<.55f) return false;
    if (bGardenOpen && FMath::Abs(GetActorLocation().Y-Portal.Y)<55 && FMath::Abs(GetActorLocation().X-Portal.X)<135)
    {FeedbackMessage(TEXT("Step clear of the sliding door before closing"));return true;}
    bGardenOpen=!bGardenOpen;FeedbackMessage(bGardenOpen?TEXT("Garden door opening"):TEXT("Garden door closing"));return true;
}

void AVistaVillaCharacter::TickAlpine(float Dt)
{
    if (!bGardenOpen && GardenAlpha>.01f && FMath::Abs(GetActorLocation().Y+1201)<55 && FMath::Abs(GetActorLocation().X-439.5)<135)
        bGardenOpen=true;
    GardenAlpha=FMath::FInterpConstantTo(GardenAlpha,bGardenOpen?1.f:0.f,Dt,.85f);
    const float Smooth=GardenAlpha*GardenAlpha*(3-2*GardenAlpha);
    for (int32 I=0;I<GardenPanels.Num();++I) if (GardenPanels[I].IsValid())
        GardenPanels[I]->SetActorLocation(GardenClosed[I]+FVector(-218*Smooth,0,0),false);
    LandClock+=Dt;
}

bool AVistaVillaCharacter::UpdateAlpineMotion(float Dt,FVillaMotionFrame& A,FVillaMotionFrame& B,float& Fraction,bool& Reset)
{
    if (AlpineClips.IsEmpty()) return false;
    const float Speed=GetVelocity().Size2D();const bool Air=GetCharacterMovement()->IsFalling();
    Reset=!bFeetReady || FVector::Distance(PreviousLocation,GetActorLocation())>70.f;
    PreviousLocation=GetActorLocation();
    if (Reset || (Speed>8 && PreviousLocomotionSpeed<=8)) StepClock=.30f;
    PreviousLocomotionSpeed=Speed;
    const FVector V=GetMesh()->GetComponentTransform().InverseTransformVectorNoScale(GetVelocity()).GetSafeNormal2D();
    const float Direction=FMath::Fmod(FMath::Atan2(V.X,V.Y)*4.f/PI+8.f,8.f);
    const TCHAR* D[]={TEXT("fwd"),TEXT("fwd_left"),TEXT("left"),TEXT("bwd_left"),TEXT("bwd"),TEXT("bwd_right"),TEXT("right"),TEXT("fwd_right")};
    const int32 First=FMath::FloorToInt(Direction)%8,Second=(First+1)%8;const float Turn=Direction-First;
    RunBlend=FMath::FInterpTo(RunBlend,FMath::Clamp((Speed-150.f)/120.f,0.f,1.f),Dt,8.f);
    const auto& WA=AlpineClips.FindChecked(FString(TEXT("walk_"))+D[First]);
    const auto& WB=AlpineClips.FindChecked(FString(TEXT("walk_"))+D[Second]);
    const auto& RA=AlpineClips.FindChecked(FString(TEXT("run_"))+D[First]);
    const auto& RB=AlpineClips.FindChecked(FString(TEXT("run_"))+D[Second]);
    CycleDistance=FMath::Lerp(FMath::Lerp(WA.Distance,WB.Distance,Turn),FMath::Lerp(RA.Distance,RB.Distance,Turn),RunBlend);
    // Recorded sprint strides are too long for a slow indoor walk. Shorten
    // both foot travel and travelled distance per cycle by the same factor.
    CycleDistance*=FMath::Lerp(.52f,.68f,RunBlend);
    StepClock=FMath::Frac(StepClock+Dt*Speed/FMath::Max(CycleDistance,30.f));
    MotionWeight=FMath::FInterpTo(MotionWeight,FMath::Clamp(Speed/75.f,0.f,1.f),Dt,8.f);
    const auto Sample=[](const FAlpineMotionClip& Clip,float T)
    {
        const float X=FMath::Clamp(T,0.f,1.f)*(Clip.Frames.Num()-1);const int32 Index=FMath::Min(FMath::FloorToInt(X),Clip.Frames.Num()-2);
        const float F=X-Index;FVillaMotionFrame Result=Clip.Frames[Index];
        for (int32 I=0;I<Result.Pose.Num();++I) Result.Pose[I].Blend(Clip.Frames[Index].Pose[I],Clip.Frames[Index+1].Pose[I],F);
        for (int32 S=0;S<2;++S) Result.Contact[S]=FMath::Lerp(Clip.Frames[Index].Contact[S],Clip.Frames[Index+1].Contact[S],F);
        return Result;
    };
    const auto Blend=[](const FVillaMotionFrame& X,const FVillaMotionFrame& Y,float F)
    {
        auto Result=X;for (int32 I=0;I<Result.Pose.Num();++I) Result.Pose[I].Blend(X.Pose[I],Y.Pose[I],F);
        for (int32 S=0;S<2;++S) Result.Contact[S]=FMath::Lerp(X.Contact[S],Y.Contact[S],F);return Result;
    };
    A=Blend(Blend(Sample(WA,StepClock),Sample(WB,StepClock),Turn),Blend(Sample(RA,StepClock),Sample(RB,StepClock),Turn),RunBlend);
    AlpineMotionName=FString(RunBlend>.5?TEXT("run_"):TEXT("walk_"))+D[First];
    if (Air)
    {
        if (!bAlpineAir) AirClock=0;AirClock+=Dt;bAlpineAir=true;
        const auto& JumpClip=AlpineClips.FindChecked(TEXT("jump"));
        auto JumpPose=Sample(JumpClip,FMath::Clamp(.14f+AirClock/JumpClip.Duration,0.f,.9f));
        auto FallPose=Sample(AlpineClips.FindChecked(TEXT("fall")),FMath::Frac(AirClock/3.f));
        A=Blend(JumpPose,FallPose,FMath::Clamp(-GetVelocity().Z/200.f,0.f,.75f));
        MotionWeight=1;AlpineMotionName=GetVelocity().Z>0?TEXT("jump"):TEXT("fall");
        bFeetReady=false;FootLocked[0]=FootLocked[1]=false;ContactWeight[0]=ContactWeight[1]=0;
    }
    else if (bAlpineAir) {LandClock=0;bAlpineAir=false;Reset=true;}
    B=A;Fraction=0;MotionIndex=FMath::Clamp(FMath::FloorToInt(StepClock*60),0,59);
    for (int32 I=0;I<MotionBlend.Num();++I)
    {
        const FString Name=Poses->BoneNames[I].ToString();
        const float Arm=Name.StartsWith(TEXT("upperarm_"))?.65f:Name.StartsWith(TEXT("lowerarm_"))?.45f:Name.StartsWith(TEXT("hand_"))?0.f:1.f;
        FTransform Target;Target.Blend(MotionIdle[I],A.Pose[I],Air?1.f:MotionWeight*FMath::Lerp(Arm,1.f,RunBlend));
        if (!Air && LandClock<.35f)
        {
            const auto Landing=Sample(AlpineClips.FindChecked(TEXT("land")),LandClock/.5f);
            FTransform Land;Land.Blend(Target,Landing.Pose[I],(1-LandClock/.35f)*FMath::Lerp(.8f,.3f,MotionWeight));Target=Land;
        }
        FTransform Smooth;Smooth.Blend(MotionBlend[I],Target,1-FMath::Exp(-Dt*18.f));MotionBlend[I]=Smooth;
    }
    return true;
}
