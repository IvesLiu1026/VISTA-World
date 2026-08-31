#include "VistaPlayableHomeSceneAuthoringLibrary.h"

#include "Engine/Engine.h"
#include "Engine/Level.h"
#include "Engine/World.h"
#include "VistaArticulatedFridgeActor.h"

AActor* UVistaPlayableHomeSceneAuthoringLibrary::SpawnArticulatedFridgeActor(
    UObject* WorldContextObject,
    const FVector& Location,
    const FRotator& Rotation)
{
    if (!IsValid(GEngine) || !IsValid(WorldContextObject))
    {
        return nullptr;
    }

    UWorld* World = GEngine->GetWorldFromContextObject(
        WorldContextObject, EGetWorldErrorMode::ReturnNull);
    if (!IsValid(World) || World->WorldType != EWorldType::Editor)
    {
        return nullptr;
    }

    ULevel* CurrentLevel = World->GetCurrentLevel();
    if (!IsValid(CurrentLevel) || CurrentLevel->GetWorld() != World)
    {
        return nullptr;
    }

    World->Modify();
    CurrentLevel->Modify();

    FActorSpawnParameters SpawnParameters;
    SpawnParameters.OverrideLevel = CurrentLevel;
    SpawnParameters.ObjectFlags |= RF_Transactional;
    SpawnParameters.SpawnCollisionHandlingOverride =
        ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

    AVistaArticulatedFridgeActor* Spawned =
        World->SpawnActor<AVistaArticulatedFridgeActor>(
            Location, Rotation, SpawnParameters);
    if (!IsValid(Spawned) || Spawned->GetLevel() != CurrentLevel)
    {
        if (IsValid(Spawned))
        {
            World->DestroyActor(Spawned);
        }
        return nullptr;
    }

    Spawned->SetFlags(RF_Transactional);
    CurrentLevel->MarkPackageDirty();
    return Spawned;
}
