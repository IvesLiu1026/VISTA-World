#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "VistaPlayableHomeCc0DetailActionLibrary.generated.h"

/**
 * Closed editor bridge for the fresh MakeHuman CC0 R14 detail-action assets.
 *
 * The caller cannot choose a namespace, skeleton, source sequence, montage,
 * slot, or notify contract.  Those identities are compiled into the editor
 * module so a Python import cannot redirect authoring into an unrelated asset.
 */
UCLASS()
class VISTAPLAYABLEHOMEEDITOR_API UVistaPlayableHomeCc0DetailActionLibrary final
    : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

  public:
    /** Create exactly three fresh R14 montages from the three imported clips. */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Editor|CC0 Detail Actions")
    static FString AuthorMakeHumanCc0R14DetailActionMontages();

    /** Verify all sequence, montage, skeleton, slot, and typed-notify bindings.
     */
    UFUNCTION(BlueprintCallable, Category = "VISTA|Editor|CC0 Detail Actions")
    static FString InspectMakeHumanCc0R14DetailActionAssets();
};
