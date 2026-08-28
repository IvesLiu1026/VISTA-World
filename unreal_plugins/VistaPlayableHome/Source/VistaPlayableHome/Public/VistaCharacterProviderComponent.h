#pragma once

#include "Components/ActorComponent.h"
#include "CoreMinimal.h"
#include "VistaCharacterProviderComponent.generated.h"

class AActor;
class AVistaHomeNpcCharacter;
class UChildActorComponent;
class USkeletalMeshComponent;

/**
 * Fail-closed visual-provider bridge for a VISTA semantic NPC.
 *
 * The semantic actor, controller, collision capsule, action queue and Manny mesh
 * remain owned by AVistaHomeNpcCharacter. This component may attach one reviewed
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

    /**
     * Closed provider identifier. Supported values are "manny" and the one
     * compiled MetaHuman provider ID. Unknown values never become asset paths.
     */
    UPROPERTY(EditAnywhere, Config, BlueprintReadOnly, Category = "VISTA|Character Provider")
    FName RequestedProviderId = TEXT("manny");

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

protected:
    virtual void BeginPlay() override;

private:
    UPROPERTY(Transient)
    TObjectPtr<UChildActorComponent> ProviderChildActorComponent = nullptr;

    FName ResolveRequestedProviderId() const;
    bool ActivateAllowlistedMetaHuman(AVistaHomeNpcCharacter& OwnerCharacter);
    bool ValidateMetaHumanVisual(
        AActor& VisualActor,
        FName& OutFailureCode) const;
    static USkeletalMeshComponent* FindNamedSkeletalMesh(
        AActor& VisualActor,
        FName ComponentName);
    static bool HasReadyGroomOrHairComponent(AActor& VisualActor);
    static void DisableVisualCollision(AActor& VisualActor);
    static void SetMannyFallbackVisible(
        AVistaHomeNpcCharacter& OwnerCharacter,
        bool bVisible);
    void SetPhotorealUnavailable(
        AVistaHomeNpcCharacter& OwnerCharacter,
        FName FailureCode);
};
