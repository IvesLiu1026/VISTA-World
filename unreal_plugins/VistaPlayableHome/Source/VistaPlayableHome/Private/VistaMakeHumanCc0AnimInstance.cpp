#include "VistaMakeHumanCc0AnimInstance.h"

#include "GameFramework/Pawn.h"

void UVistaMakeHumanCc0AnimInstance::NativeUpdateAnimation(const float DeltaSeconds)
{
    Super::NativeUpdateAnimation(DeltaSeconds);

    const APawn* Pawn = TryGetPawnOwner();
    if (!IsValid(Pawn))
    {
        GroundSpeedCmPerSecond = 0.0F;
        return;
    }

    const FVector Velocity = Pawn->GetVelocity();
    const float Speed = FVector(Velocity.X, Velocity.Y, 0.0).Size();
    GroundSpeedCmPerSecond = FMath::IsFinite(Speed)
        ? FMath::Clamp(Speed, 0.0F, 10000.0F)
        : 0.0F;
}
