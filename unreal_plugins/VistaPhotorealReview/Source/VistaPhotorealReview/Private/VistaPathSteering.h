#pragma once
#include "CoreMinimal.h"
class ACharacter;

// Local steering over an existing route. Never changes collision or teleports.
namespace VistaPathSteering
{
    bool ClearFloorChord(const ACharacter* Walker,const FVector& End,const AActor* Ignore=nullptr);
    FVector PreviewCorner(const ACharacter* Walker,const FVector& Corner,const FVector& Next,
                         float LookAhead,const AActor* Ignore=nullptr);
    float ForwardClearance(const ACharacter* Walker,const FVector& Direction,float Distance);
    FVector AvoidNearObstacle(const ACharacter* Walker,const FVector& Goal);
}
