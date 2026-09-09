#include "EmbodiedReview.h"

#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/Controller.h"

void AEmbodiedReviewCharacter::UpdateFirstPersonRest(float Dt)
{
    const auto Smooth=[](float V) { V=FMath::Clamp(V,0.f,1.f);return V*V*(3.f-2.f*V); };
    const float Pitch=Controller?FRotator::NormalizeAxis(Controller->GetControlRotation().Pitch):0.f;
    // Lower the hands towards the hips as the player inspects their torso and
    // feet. Keep the world and owner camera projections identical for contact.
    const float LookWeight=(1.f-Smooth((-Pitch-12.f)/40.f))*(1.f-Smooth((Pitch-20.f)/25.f));
    const float PostureWeight=1.f-FMath::Max3(CrouchAlpha,SeatedAlpha,FallAlpha);
    float Target=bThirdPerson?0.f:LookWeight*FMath::Clamp(PostureWeight,0.f,1.f);
    bFirstPersonRestObstructed=false;
    if (Target>.01f)
    {
        // A relaxed ready pose must not push empty hands through a nearby
        // wall. The existing reach/contact solver still owns active hands.
        const FVector Start=GetActorLocation()+FVector(0,0,42.f)+GetActorForwardVector()*8.f;
        const FVector End=Start+GetActorForwardVector()*52.f;
        FCollisionQueryParams Query(SCENE_QUERY_STAT(EmbodiedEmptyHands),false,this);
        FHitResult Hit;
        bFirstPersonRestObstructed=GetWorld()->SweepSingleByChannel(Hit,Start,End,FQuat::Identity,
            ECC_Visibility,FCollisionShape::MakeSphere(8.f),Query);
        if (bFirstPersonRestObstructed) Target=0.f;
    }
    // A bounded phase plus the pose's smoothstep avoids a large first-frame
    // wrist jump after switching view or returning from a look-down pose.
    FirstPersonRestAlpha=FMath::FInterpConstantTo(FirstPersonRestAlpha,Target,Dt,2.5f);
    if (FMath::Abs(FirstPersonRestAlpha-Target)<.0001f) FirstPersonRestAlpha=Target;
}
