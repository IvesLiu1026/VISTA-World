#include "VistaAlpineFoliage.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"

AVistaAlpineFoliage::AVistaAlpineFoliage()
{
    Instances=CreateDefaultSubobject<UHierarchicalInstancedStaticMeshComponent>(TEXT("Vegetation"));
    RootComponent=Instances;
    Instances->SetMobility(EComponentMobility::Static);
    Instances->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Instances->SetCanEverAffectNavigation(false);
}
