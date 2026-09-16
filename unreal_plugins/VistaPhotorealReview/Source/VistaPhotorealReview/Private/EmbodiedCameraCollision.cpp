#include "EmbodiedReview.h"
#include "VistaCameraClearance.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"

void AEmbodiedReviewCharacter::CalcCamera(float Dt,FMinimalViewInfo& Out)
{
    Super::CalcCamera(Dt,Out);
    if (!bReady) return;
    // A local near plane preserves other cameras' project settings. Enclose
    // the full near plane, rather than testing only a two-cm eye sphere.
    Out.PerspectiveNearClipPlane=3.f;
    float Aspect=Out.AspectRatio;
    if (!Out.bConstrainAspectRatio) if (const auto* PC=Cast<APlayerController>(Controller))
    {int32 W=0,H=0;PC->GetViewportSize(W,H);if(W>0 && H>0)Aspect=float(W)/H;}
    const float Radius=VistaCamera::Clearance(3.f,Out.FOV,Aspect);
    const float HalfHeight=GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const FVector Local=GetActorTransform().InverseTransformPosition(Out.Location);
    FVector Anchor=GetActorTransform().TransformPosition(FVector(0,0,bThirdPerson?FollowBoom->GetRelativeLocation().Z:
        FMath::Clamp(float(Local.Z),-HalfHeight+Radius+1.f,HalfHeight-Radius-1.f)));
    FCollisionQueryParams Query(SCENE_QUERY_STAT(EmbodiedCameraClearance),true,this);
    if (Cup && (Phase!=EEmbodiedPhase::Idle || bSceneActionBusy)) Query.AddIgnoredActor(Cup);
    const FCollisionShape Shape=FCollisionShape::MakeSphere(Radius);
    FHitResult Hit;
    // Moving doors or a review bookmark can start a query in penetration.
    // Resolve it explicitly instead of accepting an unsafe desired camera.
    for (int32 I=0;I<4;++I)
    {
        if (!GetWorld()->SweepSingleByChannel(Hit,Anchor,Out.Location,FQuat::Identity,ECC_Camera,Shape,Query)) break;
        if (!Hit.bStartPenetrating) {Out.Location=Hit.Location;break;}
        Anchor+=Hit.Normal*(Hit.PenetrationDepth+.5f);
        if (I==3) Out.Location=Anchor;
    }
    if (!bThirdPerson) ReviewCamera->SetWorldLocation(Out.Location);
}
