#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "VistaPlayableHomeCc0R15DetailActionLibrary.generated.h"

/**
 * Closed editor bridge for the fresh MakeHuman CC0 R15 detail-action assets.
 *
 * The caller cannot choose a namespace, skeleton, source sequence, montage,
 * slot, or notify contract.  Those identities are compiled into the editor
 * module so a Python import cannot redirect authoring into an unrelated asset.
 */
UCLASS()
class VISTAPLAYABLEHOMEEDITOR_API UVistaPlayableHomeCc0R15DetailActionLibrary final
    : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

  public:
    /** Create exactly nine fresh R15 montages from the nine imported clips. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Editor|CC0 Detail Actions")
    static FString AuthorMakeHumanCc0R15DetailActionMontages();

    /** Verify all sequence, montage, skeleton, slot, and typed-notify bindings.
     */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Editor|CC0 Detail Actions")
    static FString InspectMakeHumanCc0R15DetailActionAssets();
};
