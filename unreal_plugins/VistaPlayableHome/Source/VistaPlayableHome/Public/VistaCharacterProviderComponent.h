#pragma once

#include "Components/ActorComponent.h"
#include "CoreMinimal.h"
#include "VistaCharacterProviderComponent.generated.h"

class AActor;
class ACharacter;
class UChildActorComponent;
class UIKRetargeter;
class URetargetComponent;
class USkeletalMeshComponent;

/**
 * Fail-closed visual-provider bridge for a VISTA character.
 *
 * The semantic actor, controller, collision capsule, action queue and Manny mesh
 * remain owned by ACharacter. This component may attach one reviewed
 * visual-only assembled character from a compiled allowlist. It never accepts an
 * Unreal object path from TCP, NLP, Blueprint or runtime state.
 */
UCLASS(
    Config = Game,
    DefaultConfig,
    ClassGroup = (VISTA),
    meta = (BlueprintSpawnableComponent))
class VISTAPLAYABLEHOME_API UVistaCharacterProviderComponent final
    : public UActorComponent
{
    GENERATED_BODY()

public:
    UVistaCharacterProviderComponent();

    /** Closed identifiers shared by the player and NPC constructors. */
    static FName GetMannyProviderId();
    static FName GetMetaHumanVivianProviderId();
    static FName GetCitySampleCrowdVisualDemoProviderId();
    static FName GetMakeHumanCc0R8ProviderId();

    /** True only after the exact R6 mesh and R8 AnimBP pass runtime binding. */
    UFUNCTION(BlueprintPure, Category = "VISTA|Character Provider")
    bool IsMakeHumanCc0R8Active() const;

    /**
     * True only for the gated human-operated City Sample visual demo when its
     * hidden animation authority is the exact project Manny mesh/skeleton and
     * the visual retarget bridge remains valid. This is not a photoreal or AI
     * data-use acceptance signal.
     */
    UFUNCTION(BlueprintPure, Category = "VISTA|Character Provider")
    bool IsCitySampleHumanOperatedVisualDemoActive() const;

    /**
     * Closed provider identifier. Supported values are "manny", the reviewed
     * Vivian provider and the human-operated City Sample visual-demo provider.
     * Unknown values never become asset paths.
     */
    UPROPERTY(EditAnywhere, Config, BlueprintReadOnly, Category = "VISTA|Character Provider")
    FName RequestedProviderId = TEXT("manny");

    /**
     * Command-line provider selection is opt-in per character. The playable
     * character opts in; NPCs explicitly stay on Manny so a process-wide flag
     * cannot accidentally instantiate one MetaHuman per NPC.
     */
    UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "VISTA|Character Provider")
    bool bAllowCommandLineProviderOverride = false;

    /**
     * Explicit uniform scale for the licensed City Sample visual shell. The
     * shell is still visual-only: movement and collision remain on the owning
     * VISTA character capsule. Runtime fit validation rejects invalid config or
     * a scaled shell that cannot fit inside that capsule vertically.
     */
    UPROPERTY(
        EditAnywhere,
        Config,
        BlueprintReadOnly,
        Category = "VISTA|Character Provider|City Sample Visual Fit",
        meta = (ClampMin = "0.75", ClampMax = "1.00", UIMin = "0.75", UIMax = "1.00"))
    float CitySampleVisualScale = 0.90f;

    /** Clearance between the measured visual feet and authoritative capsule bottom. */
    UPROPERTY(
        EditAnywhere,
        Config,
        BlueprintReadOnly,
        Category = "VISTA|Character Provider|City Sample Visual Fit",
        meta = (ClampMin = "0.00", ClampMax = "5.00", UIMin = "0.00", UIMax = "5.00"))
    float CitySampleVisualFloorClearanceCm = 1.0f;

    /** Required headroom below the authoritative capsule top after scaling. */
    UPROPERTY(
        EditAnywhere,
        Config,
        BlueprintReadOnly,
        Category = "VISTA|Character Provider|City Sample Visual Fit",
        meta = (ClampMin = "0.00", ClampMax = "10.00", UIMin = "0.00", UIMax = "10.00"))
    float CitySampleVisualTopClearanceCm = 2.0f;

    UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "VISTA|Character Provider")
    FName ActiveProviderId = TEXT("manny");

    UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "VISTA|Character Provider")
    FName ProviderStatus = TEXT("manny_active");

    UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "VISTA|Character Provider")
    FName ProviderFailureCode = NAME_None;

    UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "VISTA|Character Provider")
    bool bPhotorealCharacterReady = false;

    UFUNCTION(BlueprintPure, Category = "VISTA|Character Provider")
    bool IsPhotorealCharacterReady() const { return bPhotorealCharacterReady; }

    UFUNCTION(BlueprintPure, Category = "VISTA|Character Provider")
    FName GetProviderStatus() const { return ProviderStatus; }

    /**
     * Hide only this character provider from its owning local camera while a
     * collision-compressed spring arm is inside the visual shell.
     */
    void SetOwnerNoSeeForNearCamera(bool bHidden);

protected:
    virtual void BeginPlay() override;

private:
    UPROPERTY(Transient)
    TObjectPtr<UChildActorComponent> ProviderChildActorComponent = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<URetargetComponent> ProviderRetargetComponent = nullptr;

    /** Set only after the full City Sample visual/retarget validation succeeds. */
    UPROPERTY(Transient)
    bool bCitySampleHumanOperatedVisualDemoValidated = false;

    bool bOwnerNoSeeForNearCamera = false;

    FName ResolveRequestedProviderId() const;
    bool ActivateMakeHumanCc0R8(ACharacter& OwnerCharacter);
    bool ValidateMakeHumanCc0R8(
        const ACharacter& OwnerCharacter,
        FName& OutFailureCode) const;
    bool ActivateAllowlistedMetaHuman(ACharacter& OwnerCharacter);
    bool ActivateAllowlistedCitySampleVisualDemo(ACharacter& OwnerCharacter);
    bool IsCitySampleHumanVisualDemoCommandLineAllowed(
        FName& OutFailureCode) const;
    bool NeutralizeCitySampleCharacter(
        ACharacter& OwnerCharacter,
        ACharacter& VisualCharacter,
        FName& OutFailureCode) const;
    bool ConfigureCitySampleVisualFit(
        ACharacter& OwnerCharacter,
        ACharacter& VisualCharacter,
        FName& OutFailureCode) const;
    bool ValidateCitySampleVisualFit(
        ACharacter& OwnerCharacter,
        ACharacter& VisualCharacter,
        FName& OutFailureCode) const;
    bool ValidateCitySampleVisualDemo(
        ACharacter& OwnerCharacter,
        ACharacter& VisualCharacter,
        FName& OutFailureCode) const;
    bool ValidateMetaHumanVisualShell(
        AActor& VisualActor,
        FName& OutFailureCode) const;
    bool ConfigureMetaHumanRetarget(
        ACharacter& OwnerCharacter,
        AActor& VisualActor,
        UIKRetargeter& RetargetAsset,
        FName& OutFailureCode);
    bool ValidateMetaHumanVisual(
        AActor& VisualActor,
        FName& OutFailureCode) const;
    static USkeletalMeshComponent* FindNamedSkeletalMesh(
        AActor& VisualActor,
        FName ComponentName);
    static bool TryMeasureVisibleSkeletalBounds(
        AActor& VisualActor,
        FBox& OutBounds);
    static bool HasReadyGroomOrHairComponent(AActor& VisualActor);
    static void DisableVisualCollision(AActor& VisualActor);
    static void SetMannyFallbackVisible(
        ACharacter& OwnerCharacter,
        bool bVisible);
    void DestroyProviderRetargetComponent();
    void DestroyProviderChildActorComponent();
    void SetPhotorealUnavailable(
        ACharacter& OwnerCharacter,
        FName FailureCode);
    void SetProviderUnavailable(
        ACharacter& OwnerCharacter,
        FName RequestedProvider,
        FName FailureCode);
};
