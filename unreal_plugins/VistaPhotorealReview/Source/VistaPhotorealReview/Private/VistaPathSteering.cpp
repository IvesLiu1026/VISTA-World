#include "VistaPathSteering.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"

bool VistaPathSteering::ClearFloorChord(const ACharacter* Walker,const FVector& End,const AActor* Ignore)
{
    const FVector Start=Walker->GetActorLocation();
    const auto* Capsule=Walker->GetCapsuleComponent();
    const float Half=Capsule->GetScaledCapsuleHalfHeight(),Radius=Capsule->GetScaledCapsuleRadius();
    FCollisionQueryParams Q(SCENE_QUERY_STAT(VistaCornerClearance),false,Walker);
    if (Ignore) Q.AddIgnoredActor(Ignore);
    // Extra lateral margin, original full height. The native capsule remains authoritative.
    FHitResult Hit;
    if (Walker->GetWorld()->SweepSingleByChannel(Hit,Start,End,FQuat::Identity,ECC_Pawn,
        FCollisionShape::MakeCapsule(Radius+3,Half),Q)) return false;
    const int32 Samples=FMath::Max(1,FMath::CeilToInt(FVector::Dist2D(Start,End)/22.f));
    for (int32 I=1;I<=Samples;++I)
    {
        const FVector P=FMath::Lerp(Start,End,float(I)/Samples);
        if (!Walker->GetWorld()->LineTraceSingleByChannel(Hit,P-FVector(0,0,Half-12),
            P-FVector(0,0,Half+18),ECC_Visibility,Q) || Hit.ImpactNormal.Z<.9f ||
            FMath::Abs(Hit.ImpactPoint.Z-(Start.Z-Half))>12) return false;
    }
    // Stair/ledge transitions intentionally keep their original collision-driven route.
    return true;
}

FVector VistaPathSteering::PreviewCorner(const ACharacter* Walker,const FVector& Corner,
                                       const FVector& Next,float LookAhead,const AActor* Ignore)
{
    const FVector Here=Walker->GetActorLocation();
    FVector Goal=Corner;Goal.Z=Here.Z;
    const float Distance=FVector::Dist2D(Here,Goal);
    if (Distance>=LookAhead) return Goal;
    const FVector Exit=(Next-Corner).GetSafeNormal2D();
    const float Beyond=FMath::Min(LookAhead-Distance,FVector::Dist2D(Next,Corner)*.45f);
    // Shorten the arc if furniture or a wall narrows this corner.
    for (float Scale:{1.f,.75f,.5f,.25f})
    {
        const FVector Candidate=Goal+Exit*Beyond*Scale;
        if (Beyond*Scale>2 && ClearFloorChord(Walker,Candidate,Ignore)) return Candidate;
    }
    return Goal;
}

float VistaPathSteering::ForwardClearance(const ACharacter* Walker,const FVector& Direction,float Distance)
{
    const auto* Capsule=Walker->GetCapsuleComponent();
    FCollisionQueryParams Q(SCENE_QUERY_STAT(VistaAnticipatoryBrake),false,Walker);FHitResult Hit;
    // Waist-height probe excludes stair risers, while detecting walls and people early.
    const FVector Start=Walker->GetActorLocation()+FVector(0,0,15);
    if (Walker->GetWorld()->SweepSingleByChannel(Hit,Start,Start+Direction*Distance,FQuat::Identity,
        ECC_Pawn,FCollisionShape::MakeCapsule(Capsule->GetScaledCapsuleRadius(),40),Q))
        return FMath::Max(0.f,Hit.Distance);
    return Distance;
}

FVector VistaPathSteering::AvoidNearObstacle(const ACharacter* Walker,const FVector& Goal)
{
    const FVector Here=Walker->GetActorLocation(),Direct=(Goal-Here).GetSafeNormal2D();
    const float Remaining=FVector::Dist2D(Goal,Here);
    const float Clearance=ForwardClearance(Walker,Direct,95);
    if (Remaining<18 || Clearance>FMath::Min(65.f,Remaining+8)) return Direct;
    const FVector Heading=Walker->GetActorForwardVector();
    FVector Best=Direct;float Score=Clearance/95.f+2+.3f*FVector::DotProduct(Heading,Direct);
    // A short lateral correction starts before contact, e.g. following a human
    // past a door post. Candidates must remain on supported floor and make
    // progress toward the route. No actor/collision exemptions are introduced.
    for (float Angle:{15.f,-15.f,30.f,-30.f,45.f,-45.f,60.f,-60.f})
    {
        const FVector Direction=Direct.RotateAngleAxis(Angle,FVector::UpVector);
        const float Free=ForwardClearance(Walker,Direction,95);
        const float Value=Free/95.f+2*FVector::DotProduct(Direction,Direct)+.3f*FVector::DotProduct(Heading,Direction);
        if (Free<35 || Value<=Score || !ClearFloorChord(Walker,Here+Direction*35)) continue;
        Best=Direction;Score=Value;
    }
    return Best;
}
