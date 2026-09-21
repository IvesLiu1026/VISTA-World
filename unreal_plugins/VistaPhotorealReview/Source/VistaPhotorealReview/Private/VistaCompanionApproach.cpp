// Local same-floor navigation for a requested interaction. Geometry is used by
// the native motor controller, never passed to the model's observation stream.
#include "VistaCompanion.h"
#include "Algo/Reverse.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"

namespace {
bool SupportedChord(const ACharacter* Walker,const FVector& Start,const FVector& End,const AActor* DiagnosticIgnore=nullptr)
{
    const float Half=Walker->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const float Radius=Walker->GetCapsuleComponent()->GetScaledCapsuleRadius();
    FCollisionQueryParams Q(SCENE_QUERY_STAT(AssistLocalChord),false,Walker);FHitResult Hit;
    if (DiagnosticIgnore) Q.AddIgnoredActor(DiagnosticIgnore);
    if (Walker->GetWorld()->SweepSingleByChannel(Hit,Start,End,FQuat::Identity,ECC_Pawn,
        FCollisionShape::MakeCapsule(Radius,Half),Q)) return false;
    const int32 Count=FMath::Max(1,FMath::CeilToInt(FVector::Dist2D(Start,End)/18.f));
    for (int32 I=1;I<=Count;++I)
    {
        const FVector P=FMath::Lerp(Start,End,float(I)/Count);
        if (!Walker->GetWorld()->LineTraceSingleByChannel(Hit,P-FVector(0,0,Half-12),P-FVector(0,0,Half+15),ECC_Visibility,Q) ||
            Hit.ImpactNormal.Z<.9f || FMath::Abs(Hit.ImpactPoint.Z-(Start.Z-Half))>12) return false;
    }
    return true;
}
}

bool AVistaCompanion::AssistChord(const FVector& Start,const FVector& End) const
{
    return SupportedChord(this,Start,End);
}

bool AVistaCompanion::HumanBlocksAssistChord(const FVector& Start,const FVector& End) const
{
    if (!Leader.IsValid()) return false;
    FCollisionQueryParams Q(SCENE_QUERY_STAT(AssistHumanObstruction),false,this);FHitResult Hit;
    const float Half=GetCapsuleComponent()->GetScaledCapsuleHalfHeight(),Radius=GetCapsuleComponent()->GetScaledCapsuleRadius();
    // A human hit plus a supported chord without that human proves a temporary
    // obstruction. The diagnostic chord is NEVER returned as an executable path.
    return GetWorld()->SweepSingleByChannel(Hit,Start,End,FQuat::Identity,ECC_Pawn,
        FCollisionShape::MakeCapsule(Radius,Half),Q) && Hit.GetActor()==Leader.Get() &&
        SupportedChord(this,Start,End,Leader.Get());
}

bool AVistaCompanion::PlanAssistApproach()
{
    const double Started=FPlatformTime::Seconds();
    AssistPath.Empty();AssistPathIndex=0;AssistCandidates=AssistExpanded=0;
    AssistFloorRejected=AssistBodyRejected=AssistReachRejected=AssistOccludedRejected=AssistHumanOccupied=0;
    bAssistHumanBlocksRoute=false;
    auto Finish=[&](bool Ok){AssistPlanMs=(FPlatformTime::Seconds()-Started)*1000;return Ok;};
    const FVector Here=GetActorLocation();
    const float Half=GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const float Radius=GetCapsuleComponent()->GetScaledCapsuleRadius();
    FCollisionQueryParams Q(SCENE_QUERY_STAT(AssistLocalPlan),false,this);
    FCollisionQueryParams WithoutHuman=Q;WithoutHuman.AddIgnoredActor(Leader.Get());
    auto Support=[&](FVector& P,bool* HumanOnly=nullptr)
    {
        FHitResult Floor;
        if (!GetWorld()->LineTraceSingleByChannel(Floor,P-FVector(0,0,Half-15),P-FVector(0,0,Half+18),ECC_Visibility,Q) ||
            Floor.ImpactNormal.Z<.9f || FMath::Abs(Floor.ImpactPoint.Z-(Here.Z-Half))>12)
        {++AssistFloorRejected;return false;}
        P.Z=Floor.ImpactPoint.Z+Half+2;
        if (GetWorld()->OverlapBlockingTestByChannel(P,FQuat::Identity,ECC_Pawn,
            FCollisionShape::MakeCapsule(Radius+1,Half),Q))
        {
            ++AssistBodyRejected;
            // Diagnostic only: a human-occupied candidate can request room,
            // but is never added to the route or used by movement/commit checks.
            if (HumanOnly && !GetWorld()->OverlapBlockingTestByChannel(P,FQuat::Identity,ECC_Pawn,
                FCollisionShape::MakeCapsule(Radius+1,Half),WithoutHuman)) {*HumanOnly=true;return true;}
            return false;
        }
        return true;
    };
    const FTransform Actor=GetActorTransform();
    const FVector RestShoulder=Actor.InverseTransformPosition(GetMesh()->GetSocketLocation(TEXT("upperarm_r"))),
        Waist=Actor.InverseTransformPosition(GetMesh()->GetSocketLocation(TEXT("spine_01"))),
        RestHead=Actor.InverseTransformPosition(GetMesh()->GetSocketLocation(TEXT("head")));
    AssistLeanDegrees=FMath::Clamp((Here.Z+RestShoulder.Z-AssistControl.Z-20.f)*.9f,0.f,25.f);
    const FQuat Lean(FVector::RightVector,FMath::DegreesToRadians(AssistLeanDegrees));
    const FVector ShoulderLocal=Waist+Lean.RotateVector(RestShoulder-Waist),
        HeadLocal=Waist+Lean.RotateVector(RestHead-Waist);
    const float ArmLength=FVector::Distance(GetMesh()->GetSocketLocation(TEXT("upperarm_r")),GetMesh()->GetSocketLocation(TEXT("lowerarm_r")))+
        FVector::Distance(GetMesh()->GetSocketLocation(TEXT("lowerarm_r")),GetMesh()->GetSocketLocation(TEXT("hand_r")))+
        FVector::Distance(GetMesh()->GetSocketLocation(TEXT("hand_r")),GetMesh()->GetSocketLocation(TEXT("index_03_r")));
    TArray<FVector> Goals;
    const FVector Toward=(AssistControl-Here).GetSafeNormal2D();
    for (float R:{30.f,34.f,40.f,48.f,56.f,64.f,72.f,80.f}) for (int32 A=0;A<360;A+=20)
    {
        FVector P=AssistControl-Toward.RotateAngleAxis(A,FVector::UpVector)*R;P.Z=Here.Z;
        bool HumanOccupied=false;
        if (!Support(P,&HumanOccupied)) continue;
        const float Yaw=(AssistControl-P).Rotation().Yaw;
        const FVector Shoulder=P+FRotator(0,Yaw,0).RotateVector(ShoulderLocal);
        if (FVector::Distance(Shoulder,AssistControl)>ArmLength-.5f) {++AssistReachRejected;continue;}
        FHitResult Hit;
        // Check the upper-body lean as well as the standing capsule. Ignoring
        // the human is diagnostic only for candidates already excluded above.
        const auto& BodyQuery=HumanOccupied?WithoutHuman:Q;
        bool BodyClear=true;
        for (const auto& Segment:TArray<TPair<FVector,FVector>>{{RestShoulder,ShoulderLocal},{RestHead,HeadLocal}})
        {
            const FVector From=P+FRotator(0,Yaw,0).RotateVector(Segment.Key),To=P+FRotator(0,Yaw,0).RotateVector(Segment.Value);
            if (GetWorld()->SweepSingleByChannel(Hit,From,To,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeSphere(12),BodyQuery))
            {BodyClear=false;break;}
        }
        if (!BodyClear) {++AssistOccludedRejected;continue;}
        if (GetWorld()->LineTraceSingleByChannel(Hit,Shoulder,AssistControl,ECC_Visibility,Q) &&
            Hit.GetActor()!=AssistEntity.Get() && FVector::Distance(Hit.ImpactPoint,AssistControl)>3)
        {
            if (Hit.GetActor()==Leader.Get() &&
                (!GetWorld()->LineTraceSingleByChannel(Hit,Shoulder,AssistControl,ECC_Visibility,WithoutHuman) ||
                 Hit.GetActor()==AssistEntity.Get() || FVector::Distance(Hit.ImpactPoint,AssistControl)<=3)) HumanOccupied=true;
            else {++AssistOccludedRejected;continue;}
        }
        if (HumanOccupied) {++AssistHumanOccupied;continue;}
        Goals.Add(P);
    }
    AssistCandidates=Goals.Num();if (!Goals.Num()) return Finish(false);
    float Best=TNumericLimits<float>::Max();FVector Destination;bool HumanBlocksDirect=false;
    for (const FVector& P:Goals)
    {
        const float Cost=FVector::Dist2D(Here,P);
        if (Cost<Best && AssistChord(Here,P)) {Best=Cost;Destination=P;}
        else if (!HumanBlocksDirect && HumanBlocksAssistChord(Here,P)) HumanBlocksDirect=true;
    }
    if (Best<TNumericLimits<float>::Max())
    {AssistGoal=Destination;AssistPath.Add(Destination);return Finish(true);}

    // A bounded 24 cm grid connects capsule-clear, supported segments around a
    // person or furniture. No actor is ignored except this walker; no stairs,
    // floor gaps, collision exemptions or root teleports are introduced.
    constexpr float Step=24,Margin=144;
    const int32 MinX=FMath::FloorToInt((FMath::Min(Here.X,AssistControl.X)-Margin-Here.X)/Step),
        MaxX=FMath::CeilToInt((FMath::Max(Here.X,AssistControl.X)+Margin-Here.X)/Step),
        MinY=FMath::FloorToInt((FMath::Min(Here.Y,AssistControl.Y)-Margin-Here.Y)/Step),
        MaxY=FMath::CeilToInt((FMath::Max(Here.Y,AssistControl.Y)+Margin-Here.Y)/Step);
    const int32 Width=MaxX-MinX+1,Height=MaxY-MinY+1;
    if (Width*Height>1600) return Finish(false);
    struct Node {FVector P;float Cost=TNumericLimits<float>::Max();int32 Parent=-1;int8 Valid=-1;bool Closed=false;};
    TArray<Node> Nodes;Nodes.SetNum(Width*Height);
    for (int32 Y=MinY;Y<=MaxY;++Y) for (int32 X=MinX;X<=MaxX;++X)
        Nodes[(Y-MinY)*Width+X-MinX].P=Here+FVector(X*Step,Y*Step,0);
    const int32 Start=-MinY*Width-MinX;Nodes[Start].Cost=0;Nodes[Start].Valid=1;
    int32 End=-1;
    for (int32 Iteration=0;Iteration<Nodes.Num();++Iteration)
    {
        int32 Current=-1;float Score=Best;
        for (int32 I=0;I<Nodes.Num();++I) if (!Nodes[I].Closed)
        {
            const float F=Nodes[I].Cost+FMath::Max(0.f,float(FVector::Dist2D(Nodes[I].P,AssistControl))-80.f);
            if (F<Score) {Current=I;Score=F;}
        }
        if (Current<0) break;
        Node& N=Nodes[Current];N.Closed=true;++AssistExpanded;
        for (const FVector& Goal:Goals)
        {
            const float D=FVector::Dist2D(N.P,Goal),Cost=N.Cost+D;
            if (D<=Step*1.8f && Cost<Best && AssistChord(N.P,Goal))
            {Best=Cost;End=Current;Destination=Goal;}
        }
        const int32 X=Current%Width,Y=Current/Width;
        for (int32 DY=-1;DY<=1;++DY) for (int32 DX=-1;DX<=1;++DX)
        {
            if ((!DX && !DY) || X+DX<0 || X+DX>=Width || Y+DY<0 || Y+DY>=Height) continue;
            const int32 I=(Y+DY)*Width+X+DX;Node& Next=Nodes[I];if (Next.Closed) continue;
            const float Cost=N.Cost+Step*(DX && DY?1.41421356f:1.f);if (Cost>=Next.Cost) continue;
            if (Next.Valid<0) Next.Valid=Support(Next.P)?1:0;
            if (!Next.Valid || !AssistChord(N.P,Next.P)) continue;
            Next.Cost=Cost;Next.Parent=Current;
        }
    }
    if (End<0) {bAssistHumanBlocksRoute=HumanBlocksDirect;return Finish(false);}
    TArray<FVector> Reverse;
    for (int32 I=End;I!=Start && I>=0;I=Nodes[I].Parent) Reverse.Add(Nodes[I].P);
    Algo::Reverse(Reverse);Reverse.Add(Destination);
    FVector From=Here;
    for (int32 I=0;I<Reverse.Num();)
    {
        int32 Last=I;
        for (int32 J=I+1;J<Reverse.Num();++J) if (AssistChord(From,Reverse[J])) Last=J;
        AssistPath.Add(Reverse[Last]);From=Reverse[Last];I=Last+1;
    }
    AssistGoal=Destination;return Finish(true);
}

TSharedPtr<FJsonObject> AVistaCompanion::AssistDiagnostics() const
{
    auto D=MakeShared<FJsonObject>();D->SetNumberField(TEXT("plan_ms"),AssistPlanMs);
    D->SetNumberField(TEXT("candidates"),AssistCandidates);D->SetNumberField(TEXT("expanded"),AssistExpanded);
    D->SetNumberField(TEXT("floor_rejected"),AssistFloorRejected);D->SetNumberField(TEXT("body_rejected"),AssistBodyRejected);
    D->SetNumberField(TEXT("reach_rejected"),AssistReachRejected);D->SetNumberField(TEXT("occluded_rejected"),AssistOccludedRejected);
    D->SetNumberField(TEXT("replans"),AssistReplans);D->SetNumberField(TEXT("path_index"),AssistPathIndex);
    D->SetNumberField(TEXT("reach_clock_s"),AssistReachClock);
    D->SetNumberField(TEXT("human_occupied_candidates"),AssistHumanOccupied);
    D->SetBoolField(TEXT("human_blocks_route"),bAssistHumanBlocksRoute);
    D->SetNumberField(TEXT("wait_clock_s"),AssistWaitClock);
    D->SetNumberField(TEXT("lean_degrees"),AssistLeanDegrees);
    const FVector Shoulder=GetMesh()->GetSocketLocation(TEXT("upperarm_r")),
        Elbow=GetMesh()->GetSocketLocation(TEXT("lowerarm_r")),Hand=GetMesh()->GetSocketLocation(TEXT("hand_r")),
        Finger=GetMesh()->GetSocketLocation(TEXT("index_03_r"));
    D->SetNumberField(TEXT("arm_length_cm"),FVector::Distance(Shoulder,Elbow)+FVector::Distance(Elbow,Hand)+FVector::Distance(Hand,Finger));
    D->SetNumberField(TEXT("shoulder_height_above_control_cm"),Shoulder.Z-AssistControl.Z);
    TArray<TSharedPtr<FJsonValue>> Points;
    for (const FVector& P:AssistPath)
        Points.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z)}));
    D->SetArrayField(TEXT("path_cm"),Points);return D;
}
