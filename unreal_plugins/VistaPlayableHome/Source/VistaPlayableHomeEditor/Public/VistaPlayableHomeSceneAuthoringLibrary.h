#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "VistaPlayableHomeSceneAuthoringLibrary.generated.h"

class AActor;

/**
 * Native editor-only scene-authoring operations that must remain safe when
 * Unreal Editor runs unattended with NullRHI.
 *
 * EditorActorSubsystem spawning goes through viewport actor positioning.  A
 * PythonScriptCommandlet has no scene viewport, so this closed bridge spawns
 * the one supported authored actor directly through the current editor world.
 */
UCLASS()
class VISTAPLAYABLEHOMEEDITOR_API UVistaPlayableHomeSceneAuthoringLibrary final
    : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /**
     * Spawn exactly AVistaArticulatedFridgeActor in the current editor level.
     *
     * Returns null for a missing context, a non-editor world, or a world with
     * no current level.  The actor is transactional, non-transient, and uses
     * always-spawn collision handling.  The caller cannot supply an arbitrary
     * class or level.
     */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Editor|Scene Authoring")
    static AActor* SpawnArticulatedFridgeActor(
        UObject* WorldContextObject,
        const FVector& Location,
        const FRotator& Rotation);
};
