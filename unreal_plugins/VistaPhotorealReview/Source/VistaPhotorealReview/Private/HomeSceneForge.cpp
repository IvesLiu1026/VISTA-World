// Small room assembly from reviewed materials and existing furniture. No model
// coordinates or executable code. Geometry and interaction binding stay native.
#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "VistaCompanion.h"
#include "ProceduralMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstanceDynamic.h"

using namespace HomeJson;

namespace
{
struct FForgeMesh
{
    TArray<FVector> Vertices,Normals;
    TArray<int32> Indices;
    TArray<FVector2D> UV;
    TArray<FLinearColor> Colors;
    TArray<FProcMeshTangent> Tangents;
    void Box(FVector P,FVector Size)
    {
        const FVector E=Size*.5;
        const FVector N[6]={FVector(1,0,0),FVector(-1,0,0),FVector(0,1,0),FVector(0,-1,0),FVector(0,0,1),FVector(0,0,-1)};
        for (const FVector& Normal:N)
        {
            const FVector U=Normal.Z!=0?FVector(1,0,0):FVector(0,0,1);
            const FVector V=FVector::CrossProduct(Normal,U);
            const float NU=FVector::DotProduct(U.GetAbs(),E),NV=FVector::DotProduct(V.GetAbs(),E),NN=FVector::DotProduct(Normal.GetAbs(),E);
            const int32 Start=Vertices.Num();
            for (const FVector2D C:{FVector2D(-1,-1),FVector2D(1,-1),FVector2D(1,1),FVector2D(-1,1)})
            {
                Vertices.Add(P+Normal*NN+U*(C.X*NU)+V*(C.Y*NV));Normals.Add(Normal);
                UV.Add(FVector2D((C.X+1)*NU/100,(C.Y+1)*NV/100));Colors.Add(FLinearColor::White);Tangents.Add(FProcMeshTangent(U,false));
            }
            for (int32 I:{0,2,1,0,3,2}) Indices.Add(Start+I);
        }
    }
};
}

void AHomeActionsCharacter::ClearMicroScene()
{
    if (!ForgeReceipt.IsValid() && ForgeActors.IsEmpty()) return;
    if (auto* C=FindComponentByClass<UVistaCompanionComponent>();C && C->Companion) C->Companion->CancelAssist();
    for (auto& Pair:ForgeOriginals) Entities.Add(Pair.Key,Pair.Value);
    ForgeOriginals.Empty();
    for (const auto& A:ForgeActors) if (IsValid(A)) A->Destroy();
    ForgeActors.Empty();ForgeReceipt.Reset();
}

bool AHomeActionsCharacter::ApplyMicroScene(const TSharedPtr<FJsonObject>& Recipe,FString& Code)
{
    const double Started=FPlatformTime::Seconds();
    if (!Recipe || Recipe->Values.Num()!=9 || String(Recipe,TEXT("schema"))!=TEXT("vista.micro-room/v1") ||
        Number(Recipe,TEXT("width_cm"))!=600 || Number(Recipe,TEXT("depth_cm"))!=520 || Number(Recipe,TEXT("height_cm"))!=290)
    {Code=TEXT("MICRO_RECIPE_REJECTED");return false;}
    const FString Family=String(Recipe,TEXT("family")),Palette=String(Recipe,TEXT("palette")),Lighting=String(Recipe,TEXT("lighting"));
    const double Seed=Number(Recipe,TEXT("seed"),-1),Arrangement=Number(Recipe,TEXT("arrangement"),-1);
    if (!(Family==TEXT("lounge") || Family==TEXT("study") || Family==TEXT("bedroom")) ||
        !(Palette==TEXT("oak") || Palette==TEXT("walnut") || Palette==TEXT("stone")) ||
        !(Lighting==TEXT("daylight") || Lighting==TEXT("warm")) || Seed<0 || Seed>2147483647 || FMath::FloorToDouble(Seed)!=Seed ||
        Arrangement!=static_cast<int64>(Seed)%3)
    {Code=TEXT("MICRO_RECIPE_REJECTED");return false;}
    const FString Root=TEXT("/Game/VISTA/HomeMaterialsR4e/Materials/");
    auto Material=[&](const FString& Name){return LoadObject<UMaterialInterface>(nullptr,*(Root+Name+TEXT(".")+Name));};
    UMaterialInterface* Wall=Material(TEXT("M_WallPaint"));
    UMaterialInterface* Floor=Material(Palette==TEXT("stone")?TEXT("M_Terrazzo"):TEXT("M_OakFloor2"));
    UMaterialInterface* Trim=Material(TEXT("M_WhiteOak"));
    if (!Wall || !Floor || !Trim) {Code=TEXT("MICRO_MATERIAL_MISSING");return false;}
    // Alternate staging islands. A rejected candidate cannot destroy the room
    // the human is currently using. Both are far from the preserved main home.
    const FVector Origin(-4000-1600*((ForgeSerial+1)%2),-1800,1200);
    const float Rotation=Arrangement==1?180.f:0.f;
    const FQuat Turn=FRotator(0,Rotation,0).Quaternion();
    auto Map=[&](FVector P){return Origin+Turn.RotateVector(P);};
    TArray<TObjectPtr<AActor>> Stage;
    TMap<FString,FHomeEntity> Bound;
    TArray<FBox> Footprints;
    FString Failure;
    auto Abort=[&](){for (const auto& A:Stage) if (IsValid(A)) A->Destroy();Code=Failure;return false;};
    auto Shell=[&](const FForgeMesh& Data,UMaterialInterface* Mat,const TCHAR* Name,bool Collision=true)
    {
        auto* A=GetWorld()->SpawnActor<AActor>(Origin,FRotator::ZeroRotator);Stage.Add(A);
        auto* M=NewObject<UProceduralMeshComponent>(A);A->SetRootComponent(M);M->RegisterComponent();
        A->SetActorLocation(Origin);
        M->CreateMeshSection_LinearColor(0,Data.Vertices,Data.Indices,Data.Normals,Data.UV,Data.UV,Data.UV,Data.UV,Data.Colors,Data.Tangents,Collision);
        M->SetMaterial(0,Mat);M->SetCollisionEnabled(Collision?ECollisionEnabled::QueryAndPhysics:ECollisionEnabled::NoCollision);
        M->SetCollisionResponseToAllChannels(ECR_Block);A->Tags.Add(FName(Name));return M;
    };
    FForgeMesh Slab;Slab.Box(FVector(0,0,-8),FVector(628,548,16));
    UMaterialInterface* ActualFloor=Floor;
    if (Palette==TEXT("walnut"))
    {
        auto* M=UMaterialInstanceDynamic::Create(Floor,this);M->SetVectorParameterValue(TEXT("AlbedoGain"),FLinearColor(.48,.32,.23,1));ActualFloor=M;
    }
    Shell(Slab,ActualFloor,TEXT("Forge_floor"));
    FForgeMesh Walls;
    Walls.Box(FVector(-307,0,145),FVector(14,548,290));
    Walls.Box(FVector(0,-267,145),FVector(600,14,290));
    Walls.Box(FVector(0,267,145),FVector(600,14,290));
    // Real 240 x 155 cm opening, thick jambs, opaque wall faces on both sides.
    Walls.Box(FVector(307,-195,145),FVector(14,130,290));
    Walls.Box(FVector(307,195,145),FVector(14,130,290));
    Walls.Box(FVector(307,0,42.5),FVector(14,260,85));
    Walls.Box(FVector(307,0,267.5),FVector(14,260,45));
    Walls.Box(FVector(0,0,297),FVector(628,548,14));Shell(Walls,Wall,TEXT("Forge_walls"));
    FForgeMesh Detail;
    for (float X:{-298.f,298.f}) Detail.Box(FVector(X,0,5),FVector(2,520,10));
    for (float Y:{-258.f,258.f}) Detail.Box(FVector(0,Y,5),FVector(600,2,10));
    for (float Y:{-126.f,126.f}) Detail.Box(FVector(303,Y,165),FVector(20,8,168));
    for (float Z:{85.f,245.f}) Detail.Box(FVector(300,0,Z),FVector(24,260,8));
    Detail.Box(FVector(304,0,165),FVector(10,4,152));Shell(Detail,Trim,TEXT("Forge_trim"));
    // A collision-only closed window keeps the playable room bounded without
    // masking light or faking transparent walls.
    FForgeMesh Window;Window.Box(FVector(307,0,165),FVector(3,248,156));
    auto* Barrier=Shell(Window,Wall,TEXT("Forge_window_barrier"));Barrier->SetVisibility(false);Barrier->SetCastShadow(false);
    auto CopyProp=[&](const FString& Id,FVector Point,float ExtraYaw=0.f,bool OnSurface=false)->AStaticMeshActor*
    {
        auto* E=Resolve(Id);
        const FHomeEntity* Original=E;
        if (E && ForgeOriginals.Contains(E->Id)) Original=&ForgeOriginals[E->Id];
        if (!Original || !Original->Actor.IsValid() || !Original->Mesh.IsValid()) {Failure=TEXT("MICRO_ASSET_MISSING_")+Id;return nullptr;}
        auto* A=GetWorld()->SpawnActor<AStaticMeshActor>();Stage.Add(A);auto* M=A->GetStaticMeshComponent();
        A->Tags.Add(FName(*(TEXT("Forge_")+Id)));
        M->SetMobility(EComponentMobility::Movable);M->SetStaticMesh(Original->Mesh->GetStaticMesh());
        for (int32 I=0;I<Original->Mesh->GetNumMaterials();++I) M->SetMaterial(I,Original->Mesh->GetMaterial(I));
        A->SetActorScale3D(Original->Actor->GetActorScale3D());
        A->SetActorRotation(Original->Baseline.Rotator()+FRotator(0,Rotation+ExtraYaw,0));
        A->SetActorLocation(Map(Point));M->UpdateBounds();const FBox B=M->Bounds.GetBox();
        A->AddActorWorldOffset(Map(Point)-FVector(B.GetCenter().X,B.GetCenter().Y,B.Min.Z));M->UpdateBounds();
        M->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);M->SetCollisionResponseToAllChannels(ECR_Block);
        const FBox Final=M->Bounds.GetBox();const FBox Local=Final.ShiftBy(-Origin);
        if (Local.Min.X < -286 || Local.Max.X >286 || Local.Min.Y < -246 || Local.Max.Y>246 || Local.Max.Z>280)
        {Failure=TEXT("MICRO_FOOTPRINT_REJECTED_")+Id;return nullptr;}
        if (!OnSurface)
        {
            for (const FBox& Other:Footprints)
                if (Final.ExpandBy(-1).Intersect(Other.ExpandBy(-1))) {Failure=TEXT("MICRO_OVERLAP_REJECTED_")+Id;return nullptr;}
            Footprints.Add(Final);
        }
        FHomeEntity Clone=*Original;Clone.Actor=A;Clone.Mesh=M;Clone.Baseline=Clone.Closed=A->GetActorTransform();
        Clone.Children.Empty();Clone.bBaselinePhysics=false;Clone.State=Copy(Original->Spec->GetObjectField(TEXT("initial_state")));
        Clone.Spec=Copy(Original->Spec);
        // Seating/contact rigs and electrical effects have house-specific
        // anchors. Expose only reviewed portable skills in generated rooms;
        // decorative furniture must not manipulate the original house.
        if (Clone.Kind!=TEXT("pickup"))
            Clone.Spec->SetArrayField(TEXT("actions"),{MakeShared<FJsonValueString>(TEXT("inspect"))});
        Bound.Add(Clone.Id,Clone);return A;
    };
    AStaticMeshActor* Table=nullptr;
    const float Offset=Arrangement==2?18.f:0.f;
    if (Family==TEXT("lounge"))
    {
        CopyProp(TEXT("sofa"),FVector(-145,-155+Offset,0));
        Table=CopyProp(TEXT("coffee_table"),FVector(-145,5+Offset,0));
    }
    else if (Family==TEXT("study"))
    {
        Table=CopyProp(TEXT("desk"),FVector(-170,80+Offset,0));
        CopyProp(TEXT("rolling_chair"),FVector(-50,80+Offset,0));
    }
    else
    {
        CopyProp(TEXT("bed"),FVector(-165,-65+Offset,0));
        Table=CopyProp(TEXT("nightstand"),FVector(-165,145+Offset,0));
    }
    if (!Failure.IsEmpty() || !Table) return Abort();
    const FBox Support=Table->GetStaticMeshComponent()->Bounds.GetBox();
    const FHomeEntity* Surface=nullptr;
    for (const auto& Pair:Bound) if (Pair.Value.Actor.Get()==Table) Surface=&Pair.Value;
    if (!Surface) {Failure=TEXT("MICRO_SURFACE_MISSING");return Abort();}
    // Assets may include a lamp, monitor, keyboard or books. The bounding-box
    // maximum is not a tabletop. Use the authored surface height and verify
    // the actual mesh under every candidate corner, then pack loose objects.
    const float SurfaceZ=Table->GetActorTransform().TransformPosition(Surface->ControlLocal).Z;
    TArray<FBox> Loose;
    TArray<FString> Items;
    Items.Add(TEXT("phone"));
    // Reserve the accessible edge for the handset before packing decoration.
    // A non-overlapping book can still obstruct the fingers and wrist.
    Items.Add(TEXT("keys"));
    if (Family!=TEXT("bedroom")) Items.Add(TEXT("daily_3"));
    if (Family!=TEXT("bedroom")) Items.Add(TEXT("living_cup"));
    for (const FString& Id:Items)
    {
        auto* A=CopyProp(Id,Turn.UnrotateVector(FVector(Support.GetCenter().X,Support.GetCenter().Y,SurfaceZ+.2)-Origin),0,true);
        if (!A) return Abort();
        auto* Mesh=A->GetStaticMeshComponent();const FVector Extent=Mesh->Bounds.BoxExtent;
        bool Placed=false;
        for (float FY:{-.8f,.8f,-.65f,.65f,-.5f,.5f,-.32f,.32f,-.16f,.16f,0.f})
        {
            if (Placed) break;
            // The open walking corridor is on the positive X side. Prefer its
            // table edge so monitors and lamps cannot occlude the first prop.
            for (float FX:{.8f,-.8f,.65f,-.65f,.5f,-.5f,.32f,-.32f,.16f,-.16f,0.f})
            {
                const FVector Center(Support.GetCenter().X+FX*Support.GetExtent().X,
                                     Support.GetCenter().Y+FY*Support.GetExtent().Y,SurfaceZ);
                const FBox Candidate(Center-FVector(Extent.X,Extent.Y,0),Center+FVector(Extent.X,Extent.Y,Extent.Z*2));
                if (Candidate.Min.X<Support.Min.X+1 || Candidate.Max.X>Support.Max.X-1 ||
                    Candidate.Min.Y<Support.Min.Y+1 || Candidate.Max.Y>Support.Max.Y-1) continue;
                bool Free=true;
                for (int32 I=0;I<Loose.Num();++I)
                    if (Candidate.ExpandBy(I==0?8.f:.7f).Intersect(Loose[I])) {Free=false;break;}
                if (!Free) continue;
                float ActualZ=SurfaceZ-3;
                for (const FVector2D Corner:{FVector2D(0,0),FVector2D(-1,-1),FVector2D(-1,1),FVector2D(1,-1),FVector2D(1,1)})
                {
                    const FVector XY=Center+FVector(Corner.X*Extent.X,Corner.Y*Extent.Y,0);
                    FHitResult Hit;FCollisionQueryParams Q(SCENE_QUERY_STAT(ForgeSupport),true);
                    if (!Table->GetStaticMeshComponent()->LineTraceComponent(Hit,FVector(XY.X,XY.Y,Support.Max.Z+5),
                        FVector(XY.X,XY.Y,SurfaceZ-3),Q) || Hit.ImpactNormal.Z<.95f || FMath::Abs(Hit.ImpactPoint.Z-SurfaceZ)>1.2f)
                    {Free=false;break;}
                    ActualZ=FMath::Max(ActualZ,Hit.ImpactPoint.Z);
                }
                if (!Free) continue;
                const FBox Current=Mesh->Bounds.GetBox();
                A->AddActorWorldOffset(FVector(Center.X,Center.Y,ActualZ+.15)-FVector(Current.GetCenter().X,Current.GetCenter().Y,Current.Min.Z));
                Mesh->UpdateBounds();Loose.Add(Mesh->Bounds.GetBox());
                for (auto& Pair:Bound) if (Pair.Value.Actor.Get()==A) Pair.Value.Baseline=Pair.Value.Closed=A->GetActorTransform();
                Placed=true;break;
            }
        }
        if (!Placed) {Failure=TEXT("MICRO_SUPPORT_REJECTED_")+Id;return Abort();}
    }
    // Validate the full 27 cm capsule corridor and floor at every corner before
    // changing the live scene. Rendering alone is not traversal acceptance.
    const TArray<FVector> Route={FVector(160,160,88),FVector(210,160,88),FVector(210,-185,88),FVector(75,-185,88),FVector(75,160,88),FVector(160,160,88)};
    for (int32 I=0;I<Route.Num();++I)
    {
        FCollisionQueryParams Q(SCENE_QUERY_STAT(ForgeWalk),false,this);FHitResult Hit;
        const FVector P=Map(Route[I]);
        const bool FloorHit=GetWorld()->LineTraceSingleByChannel(Hit,P,P-FVector(0,0,100),ECC_Visibility,Q);
        if (!FloorHit || Hit.ImpactNormal.Z<.95f || FMath::Abs(Hit.ImpactPoint.Z-Origin.Z)>1)
        {UE_LOG(LogTemp,Warning,TEXT("FORGE_FLOOR hit=%d point=%s normal=%s"),FloorHit,*Hit.ImpactPoint.ToString(),*Hit.ImpactNormal.ToString());Failure=TEXT("MICRO_FLOOR_REJECTED");return Abort();}
        if (I && GetWorld()->SweepSingleByChannel(Hit,Map(Route[I-1]),P,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(27,86),Q))
        {Failure=TEXT("MICRO_WALKWAY_REJECTED");return Abort();}
    }
    auto* LightActor=GetWorld()->SpawnActor<AActor>(Origin+FVector(180,0,245),FRotator::ZeroRotator);Stage.Add(LightActor);
    auto* Light=NewObject<UPointLightComponent>(LightActor);LightActor->SetRootComponent(Light);Light->RegisterComponent();
    LightActor->SetActorLocation(Origin+FVector(180,0,245));
    Light->SetIntensity(Lighting==TEXT("warm")?950:1300);Light->SetAttenuationRadius(750);
    Light->SetLightColor(Lighting==TEXT("warm")?FLinearColor(1,.71,.43):FLinearColor(1,.95,.87));
    if (!ResetScene(Code)) {Failure=Code;return Abort();}
    for (const auto& A:LiveDressing) if (IsValid(A)) A->Destroy();LiveDressing.Empty();
    for (const auto& Pair:Bound) {ForgeOriginals.Add(Pair.Key,Entities[Pair.Key]);Entities[Pair.Key]=Pair.Value;}
    ForgeActors=MoveTemp(Stage);++ForgeSerial;
    ForgeReceipt=Copy(Recipe);ForgeReceipt->SetArrayField(TEXT("origin_cm"),Values(Origin));
    ForgeReceipt->SetNumberField(TEXT("rotation_deg"),Rotation);ForgeReceipt->SetNumberField(TEXT("actor_count"),ForgeActors.Num());
    ForgeReceipt->SetNumberField(TEXT("interactive_bindings"),Bound.Num());
    ForgeReceipt->SetBoolField(TEXT("capsule_corridor_checked"),true);ForgeReceipt->SetBoolField(TEXT("supported_props"),true);
    ForgeReceipt->SetNumberField(TEXT("assembly_ms"),(FPlatformTime::Seconds()-Started)*1000);
    SetView(Map(Route[0]-FVector(0,0,2)),FRotator(-10,215+Rotation,0));
    GetCharacterMovement()->StopMovementImmediately();
    if (auto* C=FindComponentByClass<UVistaCompanionComponent>();C && C->Companion)
    {C->Companion->CancelAssist();C->Companion->StopSpeech();C->Companion->PlaceNear(this);}
    PublishState();Code=TEXT("MICRO_SCENE_APPLIED");return true;
}
