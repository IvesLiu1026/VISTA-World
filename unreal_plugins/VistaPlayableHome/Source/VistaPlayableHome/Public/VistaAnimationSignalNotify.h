#pragma once

#include "Animation/AnimNotifies/AnimNotify.h"
#include "CoreMinimal.h"
#include "VistaAnimationSignalNotify.generated.h"

/** Closed notify used by project-owned VISTA montages for contact/completion evidence. */
UCLASS(meta = (DisplayName = "VISTA Animation Signal"))
class VISTAPLAYABLEHOME_API UVistaAnimationSignalNotify final : public UAnimNotify
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "VISTA|Animation")
    FName SignalName = NAME_None;

    virtual void Notify(
        USkeletalMeshComponent* MeshComp,
        UAnimSequenceBase* Animation,
        const FAnimNotifyEventReference& EventReference) override;
};
