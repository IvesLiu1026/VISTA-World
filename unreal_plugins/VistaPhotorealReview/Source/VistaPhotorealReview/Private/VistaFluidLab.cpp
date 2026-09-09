#include "VistaFluidLab.h"
#include "HomeFluidAuthoring.h"
#include "HomeActionsJson.h"
#include "VistaMotionCurves.h"
#include "NiagaraComponent.h"
#include "NiagaraSystem.h"
#include "NiagaraSystemInstanceController.h"
#include "NiagaraEmitterInstance.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Camera/CameraActor.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Pawn.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "HighResScreenshot.h"
#include "UnrealClient.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"

AVistaFluidLab::AVistaFluidLab()
{
    PrimaryActorTick.bCanEverTick=true;
    RootComponent=CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    Fluid=CreateDefaultSubobject<UNiagaraComponent>(TEXT("FLIP"));
    Fluid->SetupAttachment(RootComponent);Fluid->SetAutoActivate(false);
    Displacer=CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Displacer"));
    Displacer->SetupAttachment(RootComponent);Displacer->SetMobility(EComponentMobility::Movable);
    Displacer->SetCollisionProfileName(TEXT("BlockAll"));
    Displacer->ComponentTags.Add(TEXT("CollideAgainst"));
    Tags.Add(TEXT("CollideAgainst"));
}

void AVistaFluidLab::BeginPlay()
{
    Super::BeginPlay();
    bProof=FParse::Param(FCommandLine::Get(),TEXT("VistaFluidLabProof"));
    if (bProof)
    {
        Directory=FPaths::ProjectSavedDir()/TEXT("FluidLabProof");
        if (IFileManager::Get().DirectoryExists(*Directory))
        {UE_LOG(LogTemp,Error,TEXT("FLUID_LAB_REQUIRES_FRESH_USER_DIR"));FPlatformMisc::RequestExitWithStatus(false,1);return;}
        IFileManager::Get().MakeDirectory(*Directory,true);
    }
    if (APlayerController* PC=GetWorld()->GetFirstPlayerController())
    {
        // Hide the default pawn without unpossessing: deferred camera management
        // after unpossess can replace the inspection camera with an origin view.
        PC->bAutoManageActiveCameraTarget=false;
        if (APawn* Pawn=PC->GetPawn()) {Pawn->SetActorHiddenInGame(true);Pawn->SetActorEnableCollision(false);}
        for (TActorIterator<ACameraActor> It(GetWorld());It;++It) {PC->SetViewTarget(*It);break;}
    }
    Displacer->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));
    Displacer->SetRelativeScale3D(FVector(.42,.42,.42));
    Displacer->SetRelativeLocation(FVector(0,0,160));
    Fluid->SetAsset(LoadObject<UNiagaraSystem>(nullptr,
        TEXT("/NiagaraFluids/Templates/Liquid/3D/Systems/Grid3D_Flip_Pool.Grid3D_FLIP_Pool")));
    const FString Result=UHomeFluidAuthoring::ConfigureComponent(Fluid,
        TEXT("{\"User.Num Cells Max Axis\":48,\"User.Particles Per Cell\":4,\"User.Pressure Iterations\":60,\"User.World Grid Extents\":[200,200,200],\"User.Water Height\":55,\"User.Show Bounds\":false}"));
    UE_LOG(LogTemp,Display,TEXT("VISTA_FLUID_CONFIG %s"),*Result);
    if (!HomeJson::Decode(Result)->GetBoolField(TEXT("ok")))
    {FPlatformMisc::RequestExitWithStatus(false,1);return;}
    Fluid->SetForceSolo(true);Fluid->Activate(true);
    Fluid->SetEmitterEnable(TEXT("Grid3D_FLIP_Secondary_Emitter"),false);
}

void AVistaFluidLab::Tick(float Dt)
{
    Super::Tick(Dt);
    if (APlayerController* PC=GetWorld()->GetFirstPlayerController())
        for (TActorIterator<ACameraActor> It(GetWorld());It;++It)
        {if (PC->GetViewTarget()!=*It) PC->SetViewTarget(*It);break;}
    if (!Fluid->GetAsset() || !Fluid->GetAsset()->IsReadyToRun()) return;
    ++Frames;
    // Repeatable moving collision fixture. This is not a human animation or
    // a benchmark ground-truth trajectory; the liquid is simulated by Niagara.
    const float T=Frames/30.f;
    const float Down=VistaMotion::Ease((T-5.f)/1.5f);
    const float Up=VistaMotion::Ease((T-9.f)/2.f);
    Displacer->SetRelativeLocation(FVector(0,0,160-130*Down+130*Up));
    if (!bProof) return;
    if (Frames==120 || Frames==240 || Frames==330 || Frames==450)
    {
        const FString Name=FString::Printf(TEXT("frame_%04d.png"),Frames);
        FScreenshotRequest::RequestScreenshot(Directory/Name,false,false);
        auto Row=MakeShared<FJsonObject>();Row->SetNumberField(TEXT("frame"),Frames);
        Row->SetNumberField(TEXT("world_seconds"),GetWorld()->GetTimeSeconds());
        Row->SetBoolField(TEXT("active"),Fluid->IsActive());
        Row->SetNumberField(TEXT("displacer_height_cm"),Displacer->GetRelativeLocation().Z);
        Row->SetStringField(TEXT("screenshot"),Name);
        if (APlayerController* PC=GetWorld()->GetFirstPlayerController())
        {
            FVector View;FRotator Rotation;PC->GetPlayerViewPoint(View,Rotation);
            Row->SetArrayField(TEXT("camera_world_cm"),{MakeShared<FJsonValueNumber>(View.X),
                MakeShared<FJsonValueNumber>(View.Y),MakeShared<FJsonValueNumber>(View.Z)});
        }
        TArray<TSharedPtr<FJsonValue>> Counts;
        const auto Controller=Fluid->GetSystemInstanceController();
        if (Controller.IsValid())
        {
            // Tick reads after finishing concurrent work; GPU counts remain
            // Niagara estimates, not a conservation/mass measurement.
            Controller->WaitForConcurrentTickAndFinalize();
            auto* Instance=Controller->GetSystemInstance_Unsafe();
            if (Instance) for (const auto& E:Instance->GetEmitters())
            {
                auto C=MakeShared<FJsonObject>();C->SetStringField(TEXT("emitter"),E->GetEmitterHandle().GetName().ToString());
                C->SetNumberField(TEXT("estimated_particles"),E->GetNumParticles());
                Counts.Add(MakeShared<FJsonValueObject>(C));
            }
        }
        Row->SetArrayField(TEXT("emitters"),Counts);Samples.Add(MakeShared<FJsonValueObject>(Row));
        UE_LOG(LogTemp,Display,TEXT("VISTA_FLUID_CAPTURE %d"),Frames);
    }
    if (Frames==465)
    {
        auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("schema"),TEXT("vista.fluid-lab-native-proof/v1"));
        R->SetStringField(TEXT("status"),TEXT("captured_pending_visual_review"));
        R->SetStringField(TEXT("system"),Fluid->GetAsset()->GetPathName());
        R->SetStringField(TEXT("solver"),TEXT("UE 5.7 Niagara Fluids 3D FLIP template"));
        R->SetBoolField(TEXT("coupled_to_home_action_volume"),false);
        R->SetArrayField(TEXT("samples"),Samples);
        FFileHelper::SaveStringToFile(HomeJson::Encode(R),*(Directory/TEXT("proof.json")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
        UE_LOG(LogTemp,Display,TEXT("VISTA_FLUID_LAB_PROOF_DONE"));FPlatformMisc::RequestExitWithStatus(false,0);
    }
}
