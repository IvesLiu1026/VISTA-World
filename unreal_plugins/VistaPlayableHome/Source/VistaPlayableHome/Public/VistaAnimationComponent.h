#pragma once

#include "Components/ActorComponent.h"
#include "CoreMinimal.h"
#include "VistaPlayableHomeTypes.h"
#include "VistaAnimationComponent.generated.h"

class AActor;
class UAnimMontage;

/**
 * Fixed project-owned animation bridge for playable-home characters.
 *
 * Callers select only EVistaNpcActionType and typed parameters. Asset paths are
 * compiled into this component under /Game/VISTA/Animations/V1 and are never
 * accepted from TCP, NLP, SimWorld, Blueprint, or event payloads.
 */
UCLASS(ClassGroup = (VISTA), meta = (BlueprintSpawnableComponent))
class VISTAPLAYABLEHOME_API UVistaAnimationComponent final : public UActorComponent
{
    GENERATED_BODY()

public:
    UVistaAnimationComponent();

    UFUNCTION(BlueprintCallable, Category = "VISTA|Animation")
    bool StartNpcAction(const FVistaNpcAction& Action, AActor* Target, FName& OutCode);

    UFUNCTION(BlueprintCallable, Category = "VISTA|Animation")
    void StopActiveAction(FName Reason = TEXT("ANIMATION_STOPPED"));

    UFUNCTION(BlueprintPure, Category = "VISTA|Animation")
    FVistaAnimationPlaybackResult GetPlaybackResult() const { return PlaybackResult; }

    bool ConsumeContactSignal();
    void RecordSignal(FName SignalName);

    static bool SupportsAction(EVistaNpcActionType Type);
    static bool IsLegacyFallbackAction(EVistaNpcActionType Type);
    /** Closed gate matching the reviewed animation profile's current license state. */
    static bool HasApprovedMutationAnimation(
        EVistaNpcActionType Type,
        FName& OutCode);

    virtual void TickComponent(
        float DeltaTime,
        ELevelTick TickType,
        FActorComponentTickFunction* ThisTickFunction) override;

private:
    UPROPERTY(Transient)
    TObjectPtr<UAnimMontage> ActiveMontage = nullptr;

    TMap<EVistaNpcActionType, TSoftObjectPtr<UAnimMontage>> MontageByAction;
    TOptional<FVistaNpcAction> ActiveAction;
    FVistaAnimationPlaybackResult PlaybackResult;
    FName ExpectedContactSignal = NAME_None;
    FName ExpectedCompletionSignal = NAME_None;
    double StartedAtSeconds = 0.0;
    bool bCompletionObserved = false;
    bool bContactPending = false;

    void HandleMontageEnded(UAnimMontage* Montage, bool bInterrupted);
    void SetTerminal(EVistaAnimationPlaybackStatus Status, FName Code);
    static FName CompletionSignalFor(EVistaNpcActionType Type);
    static FName ContactSignalFor(EVistaNpcActionType Type);
    static bool RequiresTarget(EVistaNpcActionType Type);
};
