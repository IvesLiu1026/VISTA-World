#include "VistaAnimationSignalNotify.h"

#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Actor.h"
#include "VistaAnimationComponent.h"

void UVistaAnimationSignalNotify::Notify(
    USkeletalMeshComponent* MeshComp,
    UAnimSequenceBase* Animation,
    const FAnimNotifyEventReference& EventReference)
{
    Super::Notify(MeshComp, Animation, EventReference);
    AActor* Owner = IsValid(MeshComp) ? MeshComp->GetOwner() : nullptr;
    if (IsValid(Owner))
    {
        if (UVistaAnimationComponent* Component =
                Owner->FindComponentByClass<UVistaAnimationComponent>())
        {
            Component->RecordSignal(SignalName);
        }
    }
}
