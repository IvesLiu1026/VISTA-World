#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "Components/CapsuleComponent.h"
#include "Components/LightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Materials/MaterialInterface.h"
#include "PhysicsEngine/PhysicsHandleComponent.h"

using namespace HomeJson;

FString AHomeActionsCharacter::RoomAt(const FVector& P) const
{
    FString Room;
    if (P.X>=-150 && P.X<=150 && P.Y>=-400 && P.Y<=400) Room=TEXT("entry_hall");
    else if (P.X>=-650 && P.X<-150 && P.Y>=0 && P.Y<=400) Room=TEXT("living_room");
    else if (P.X>150 && P.X<=650 && P.Y>=0 && P.Y<=400) Room=TEXT("kitchen_dining");
    else if (P.X>=-650 && P.X<-150 && P.Y>=-400 && P.Y<0) Room=TEXT("bedroom");
    else if (P.X>150 && P.X<=650 && P.Y>=-400 && P.Y<0) Room=TEXT("office");
    else if (P.X>=-150 && P.X<=150 && P.Y>=-800 && P.Y<-400) Room=TEXT("bathroom_laundry");
    return Room.IsEmpty()?TEXT("outside"):TEXT("home.r1/room.")+Room;
}

bool AHomeActionsCharacter::EvaluateCondition(const TSharedPtr<FJsonObject>& C) const
{
    const FString Type=String(C,TEXT("type"));const auto* E=Resolve(String(C,TEXT("target_id")));
    if (Type==TEXT("elapsed")) return EventTime>=Number(C,TEXT("seconds"));
    if (Type==TEXT("interaction")) return E && Interactions.Contains(E->Id+TEXT("#")+String(C,TEXT("affordance")));
    if (Type==TEXT("player_room")) return RoomAt(GetActorLocation())==String(C,TEXT("room_id"));
    if (Type==TEXT("entity_room")) return E && E->Actor.IsValid() && RoomAt(E->Actor->GetActorLocation())==String(C,TEXT("room_id"));
    if (Type==TEXT("entity_state") && E)
    {
        const auto* Actual=E->State->Values.Find(String(C,TEXT("field")));const auto* Expected=C->Values.Find(TEXT("value"));
        if (!Actual || !Expected || (*Actual)->Type!=(*Expected)->Type) return false;
        if ((*Actual)->Type==EJson::Boolean) return (*Actual)->AsBool()==(*Expected)->AsBool();
        if ((*Actual)->Type==EJson::String) return (*Actual)->AsString()==(*Expected)->AsString();
        if ((*Actual)->Type==EJson::Number) return FMath::IsNearlyEqual((*Actual)->AsNumber(),(*Expected)->AsNumber());
    }
    return false;
}

bool AHomeActionsCharacter::ResetScene(FString& Code)
{
    if (!bSceneReady) {Code=TEXT("SCENE_NOT_READY");return false;}
    if (!ActiveId.IsEmpty()) FinishAction(false,TEXT("RESET_CANCELLED_ACTION"));
    bSuppressReceipt=true;GripHandle->ReleaseComponent();
    if (Cup) GetCapsuleComponent()->IgnoreActorWhenMoving(Cup,false);
    for (auto& Pair:Entities)
    {
        auto& E=Pair.Value;E.State=Copy(E.Spec->GetObjectField(TEXT("initial_state")));
        if (E.Spec->HasField(TEXT("liquid_ml"))) E.State->SetNumberField(TEXT("liquid_ml"),Number(E.Spec,TEXT("liquid_ml")));
        if (!E.Actor.IsValid()) continue;
        E.Actor->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
        E.Mesh->SetSimulatePhysics(false);E.Mesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        E.Mesh->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);
        E.Actor->SetActorTransform(E.Baseline,false,nullptr,ETeleportType::TeleportPhysics);
        E.Mesh->SetSimulatePhysics(E.bBaselinePhysics && String(E.State,TEXT("container_in")).IsEmpty());
        if (E.Mesh->IsSimulatingPhysics())
        {E.Mesh->SetPhysicsLinearVelocity(FVector::ZeroVector);E.Mesh->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);}
        ApplyAperture(E,Bool(E.State,TEXT("open"))?1.f:0.f);
    }
    // Restore both sides of each initial containment tuple.
    for (auto& Pair:Entities)
        if (auto* Container=Resolve(String(Pair.Value.State,TEXT("container_in"))))
        {auto A=Container->State->GetArrayField(TEXT("contents"));A.Add(MakeShared<FJsonValueString>(Pair.Key));Container->State->SetArrayField(TEXT("contents"),A);}
    HeldId.Empty();SeatId.Empty();TargetId.Empty();SecondaryId.Empty();Interactions.Empty();
    EventId.Empty();EventStatus=TEXT("inactive");TerminalCondition.Empty();EventTime=0;
    Phase=EEmbodiedPhase::Idle;PhaseTime=0;ReachAlpha=FingerAlpha=LeftReachAlpha=LeftFingerAlpha=0;
    CrouchAlpha=SeatedAlpha=FallAlpha=0;bFeetReady=false;bSceneActionBusy=false;
    if (auto* Platform=Resolve(StandingOn)) GetCapsuleComponent()->IgnoreActorWhenMoving(Platform->Actor.Get(),false);
    StandingOn.Empty();bSceneFeetOverride=false;GetCapsuleComponent()->SetCapsuleRadius(27.f);GetCharacterMovement()->MaxStepHeight=22.f;
    PreviousVelocities.Empty();PendingImpacts.Empty();HazardCooldown=2.f;
    SelectPickup(*Resolve(TEXT("coffee_cup")));GetCharacterMovement()->SetMovementMode(MOVE_Walking);
    bSuppressReceipt=false;++Generation;EmbodiedInspect(0);Code=TEXT("SCENE_RESET");PublishState();return true;
}

bool AHomeActionsCharacter::StartEvent(const FString& Id,FString& Code)
{
    if (!bSceneReady) {Code=TEXT("SCENE_NOT_READY");return false;}
    TSharedPtr<FJsonObject> Definition;
    for (const auto& V:Contract->GetArrayField(TEXT("events")))
        if (String(V->AsObject(),TEXT("event_id"))==Id) Definition=V->AsObject();
    if (!Definition) {Code=TEXT("EVENT_NOT_FOUND");return false;}
    if (!ResetScene(Code)) return false;
    for (const auto& V:Definition->GetArrayField(TEXT("initial_operations")))
    {
        const auto O=V->AsObject();const FString Op=String(O,TEXT("op"));auto* E=Resolve(String(O,TEXT("target_id")));
        if (Op==TEXT("set_goal")) continue;
        if (!E) {Code=TEXT("EVENT_ENTITY_MISSING");return false;}
        if (Op==TEXT("set_state")) for (const auto& Patch:O->GetObjectField(TEXT("state_patch"))->Values) E->State->SetField(Patch.Key,Patch.Value);
        else if (Op==TEXT("set_visibility")) E->State->SetBoolField(TEXT("visible"),Bool(O,TEXT("visible")));
        else if (Op==TEXT("set_portable")) E->State->SetBoolField(TEXT("portable"),Bool(O,TEXT("portable")));
        else if (Op!=TEXT("set_transform")) {Code=TEXT("EVENT_OPERATION_UNSUPPORTED");return false;}
        // set_transform is bound to the reviewed replacement-scene baseline;
        // the frozen old-room coordinates are retained in the source contract.
    }
    if (Id==TEXT("mmg_070"))
    {
        auto* Clothes=Resolve(TEXT("clothes"));auto* Washer=Resolve(TEXT("washer_door"));auto* Basket=Resolve(TEXT("laundry_basket"));
        Clothes->Mesh->SetSimulatePhysics(false);
        Clothes->Actor->SetActorLocationAndRotation(Vector(Washer->Spec,TEXT("storage_cm")),FRotator(0,Number(Washer->Spec,TEXT("storage_yaw_deg")),0),false,nullptr,ETeleportType::TeleportPhysics);
        Clothes->State->SetStringField(TEXT("container_in"),Washer->Id);
        Basket->State->SetArrayField(TEXT("contents"),{});Washer->State->SetArrayField(TEXT("contents"),{MakeShared<FJsonValueString>(Clothes->Id)});
    }
    for (auto& Pair:Entities)
        if (Pair.Value.Kind==TEXT("appliance") && Pair.Value.Spec->HasField(TEXT("axis")))
            ApplyAperture(Pair.Value,Bool(Pair.Value.State,TEXT("active"))?1.f:0.f);
    EventId=Id;EventStatus=TEXT("running");EventTime=0;TerminalCondition.Empty();
    Code=TEXT("EVENT_STARTED");UpdatePresentation(0);PublishState();return true;
}

void AHomeActionsCharacter::UpdateEvent(float Dt)
{
    if (EventStatus!=TEXT("running")) return;EventTime+=Dt;
    TSharedPtr<FJsonObject> D;
    for (const auto& V:Contract->GetArrayField(TEXT("events"))) if (String(V->AsObject(),TEXT("event_id"))==EventId) D=V->AsObject();
    if (!D) return;
    // Evaluate only authoritative terminal observations. While a contact
    // transaction is pending its provisional state cannot finish an event.
    if (!ActiveId.IsEmpty()) return;
    for (const auto& V:D->GetArrayField(TEXT("failure_conditions")))
        if (EvaluateCondition(V->AsObject())) {EventStatus=TEXT("failed");TerminalCondition=String(V->AsObject(),TEXT("condition_id"));break;}
    if (EventStatus==TEXT("running"))
    {
        bool All=true;for (const auto& V:D->GetArrayField(TEXT("success_conditions"))) All&=EvaluateCondition(V->AsObject());
        if (All) {EventStatus=TEXT("succeeded");TerminalCondition=String(D->GetArrayField(TEXT("success_conditions"))[0]->AsObject(),TEXT("condition_id"));}
    }
    if (EventStatus==TEXT("running") && EventTime>=Number(D,TEXT("timeout_s"))) {EventStatus=TEXT("failed");TerminalCondition=TEXT("event_timeout");}
    if (EventStatus!=TEXT("running"))
    {
        auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("schema"),TEXT("vista.home-event-outcome/v1"));
        R->SetStringField(TEXT("event_id"),EventId);R->SetStringField(TEXT("status"),EventStatus);
        R->SetStringField(TEXT("condition_id"),TerminalCondition);R->SetNumberField(TEXT("elapsed_s"),EventTime);
        R->SetNumberField(TEXT("generation"),Generation);R->SetStringField(TEXT("session_id"),SessionId);AppendReceipt(R);
    }
}

void AHomeActionsCharacter::UpdatePresentation(float Dt)
{
    auto Shape=[this](const FString& Name,const FString& Primitive,const FString& Material,FVector Position,FVector Size,bool Visible)
    {
        AStaticMeshActor* A=Effects.FindRef(Name);
        if (!A)
        {
            A=GetWorld()->SpawnActor<AStaticMeshActor>();A->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
            const FString MeshPath=TEXT("/Engine/BasicShapes/")+Primitive+TEXT(".")+Primitive;
            A->GetStaticMeshComponent()->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,*MeshPath));
            const FString Root=String(Contract,TEXT("presentation_assets_root"),TEXT("/Game/VISTA/HomeActionsR2"));
            A->GetStaticMeshComponent()->SetMaterial(0,LoadObject<UMaterialInterface>(nullptr,*(Root+TEXT("/")+Material+TEXT(".")+Material)));
            A->SetActorEnableCollision(false);A->GetStaticMeshComponent()->SetCastShadow(false);Effects.Add(Name,A);
        }
        A->SetActorHiddenInGame(!Visible);A->SetActorLocation(Position);A->SetActorScale3D(Size/100.f);return A;
    };
    auto* Tap=Resolve(TEXT("faucet"));auto* Tub=Resolve(TEXT("bathtub"));auto* Washer=Resolve(TEXT("washer"));
    auto* Stove=Resolve(TEXT("stove"));auto* Spill=Resolve(TEXT("spill_marker"));auto* Overflow=Resolve(TEXT("overflow_marker"));
    float Level=Number(Tub->State,TEXT("liquid_level"),0);
    if (Bool(Tap->State,TEXT("active")))
    {
        Level=FMath::Min(1.f,Level+Dt/360.f);Tub->State->SetNumberField(TEXT("liquid_level"),Level);
        if (Level>=1.f) Overflow->State->SetBoolField(TEXT("visible"),true);
    }
    const float Height=15+Level*38;
    Shape(TEXT("bath_water"),TEXT("Cube"),TEXT("M_Water"),FVector(-99,-694,Height),FVector(51,143,.6),Level>0);
    Shape(TEXT("bath_stream"),TEXT("Cylinder"),TEXT("M_Water"),FVector(-92,-630,(68+Height)*.5f),FVector(.9,.9,FMath::Max(1.f,68-Height)),Bool(Tap->State,TEXT("active")));
    Shape(TEXT("overflow"),TEXT("Cylinder"),TEXT("M_Water"),FVector(-30,-647,1),FVector(78,118,.18),Bool(Overflow->State,TEXT("visible")));
    const auto* Slipper=Resolve(TEXT("slipper"));
    SpillPosition=Vector(Spill->State,TEXT("position_cm"),Slipper->Actor->GetActorLocation()+FVector(-8,0,.4));
    Shape(TEXT("coffee_spill"),TEXT("Cylinder"),TEXT("M_Coffee"),SpillPosition,FVector(58,44,.15),Bool(Spill->State,TEXT("visible")));
    Resolve(TEXT("fire_marker"))->State->SetBoolField(TEXT("visible"),Bool(Stove->State,TEXT("active")));
    for (int32 I=0;I<12;++I)
    {
        const float A=I*2*PI/12;
        Shape(FString::Printf(TEXT("flame_%d"),I),TEXT("Cone"),TEXT("M_Heat"),
            FVector(380.5f+5.7f*FMath::Cos(A),42.5f+5.7f*FMath::Sin(A),97.1f),FVector(1.1,1.1,2.1+.25*FMath::Sin(SceneClock*13+I)),Bool(Stove->State,TEXT("active")));
    }
    Shape(TEXT("washer_led"),TEXT("Sphere"),TEXT("M_Status"),FVector(71.3,-718.6,78.7),FVector(1,1,1),Bool(Washer->State,TEXT("active")));
    if (Bool(Washer->State,TEXT("active")))
    {
        auto* Clothes=Resolve(TEXT("clothes"));const auto* Door=Resolve(TEXT("washer_door"));
        if (String(Clothes->State,TEXT("container_in"))==Door->Id)
        {
            Clothes->Actor->SetActorLocation(Vector(Door->Spec,TEXT("storage_cm"))+FVector(0,FMath::Sin(SceneClock*2.5f)*3,FMath::Abs(FMath::Cos(SceneClock*2.5f))*4));
            Clothes->Actor->SetActorRotation(FRotator(0,Number(Door->Spec,TEXT("storage_yaw_deg")),FMath::Sin(SceneClock*2.5f)*22));
        }
    }
    for (const FString Name:{TEXT("coffee_cup"),TEXT("water_jug")})
    {
        const auto* Item=Resolve(Name);const float Liquid=Number(Item->State,TEXT("liquid_ml"));
        const float H=Number(Item->Spec,TEXT("height"))*(.08f+.80f*Liquid/Number(Item->Spec,TEXT("capacity_ml"),1));
        const float R=Number(Item->Spec,TEXT("radius"))*1.75f;
        auto* A=Shape(Name+TEXT("_liquid"),TEXT("Cylinder"),Name==TEXT("coffee_cup")?TEXT("M_Coffee"):TEXT("M_Water"),
            Item->Actor->GetActorTransform().TransformPosition(FVector(0,0,H)),FVector(R,R,.18),Liquid>0);
        A->SetActorRotation(Item->Actor->GetActorRotation());
    }
    const bool Pouring=!ActiveId.IsEmpty() && ActionId==TEXT("pour") && ActionTime>1.2f && !bCommitted;
    Shape(TEXT("pour_stream"),TEXT("Cylinder"),TEXT("M_Water"),PlaceLocation-FVector(0,0,6.5f),FVector(.75,.75,13),Pouring);
    for (const FString Name:{TEXT("television"),TEXT("computer"),TEXT("floor_lamp")})
    {
        const bool On=Bool(Resolve(Name)->State,TEXT("active"));
        const FString Label=Name==TEXT("television")?TEXT("tv_screen"):(Name==TEXT("computer")?TEXT("computer_screen"):TEXT("lamp_bulb"));
        const FString Mat=Name==TEXT("floor_lamp")?(On?TEXT("M_LampOn"):TEXT("M_LampOff")):(On?TEXT("M_ScreenOn"):TEXT("M_ScreenOff"));
        if (auto Screen=Effects.FindRef(Label))
            if (auto Material=DeviceMaterials.FindRef(Mat)) Screen->GetStaticMeshComponent()->SetMaterial(0,Material);
        if (Name==TEXT("floor_lamp") && FloorLight) FloorLight->SetVisibility(On);
    }
    const bool BasinOn=Bool(Resolve(TEXT("basin_faucet"))->State,TEXT("active"));
    Shape(TEXT("basin_stream"),TEXT("Cylinder"),TEXT("M_Water"),FVector(120,-515,82),FVector(.65,.65,19),BasinOn);
    auto* Toilet=Resolve(TEXT("toilet"));float Flush=Number(Toilet->State,TEXT("cycle_elapsed_s"));
    if (Bool(Toilet->State,TEXT("active")))
    {
        Flush+=Dt;Toilet->State->SetNumberField(TEXT("cycle_elapsed_s"),Flush);
        if (Flush>6.f)
        {Toilet->State->SetBoolField(TEXT("active"),false);Toilet->State->SetStringField(TEXT("status"),TEXT("idle"));}
    }
    const float FlushWave=Bool(Toilet->State,TEXT("active"))?FMath::Sin(Flush*6.f)*1.4f:0.f;
    Shape(TEXT("toilet_water"),TEXT("Cylinder"),TEXT("M_Water"),FVector(-93,-519,26+FlushWave),FVector(16,12,.25),true);
}

void AHomeActionsCharacter::SpillLiquid(FHomeEntity& E,const FString& Cause)
{
    const float Amount=Number(E.State,TEXT("liquid_ml"));if (Amount<=0 || !E.Actor.IsValid()) return;
    E.State->SetNumberField(TEXT("liquid_ml"),0);
    FVector Position=E.Actor->GetActorLocation();FHitResult Hit;
    FCollisionQueryParams P(SCENE_QUERY_STAT(HomeSpillSupport),true,this);P.AddIgnoredActor(E.Actor.Get());
    if (GetWorld()->LineTraceSingleByChannel(Hit,Position+FVector(0,0,10),Position-FVector(0,0,300),ECC_Visibility,P))
        Position=Hit.ImpactPoint+FVector(0,0,.35f);
    auto* Marker=Resolve(TEXT("spill_marker"));Marker->State->SetBoolField(TEXT("visible"),true);
    Marker->State->SetArrayField(TEXT("position_cm"),Values(Position));
    auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("schema"),TEXT("vista.home-physical-outcome/v1"));
    R->SetStringField(TEXT("session_id"),SessionId);R->SetStringField(TEXT("event_id"),EventId);
    R->SetStringField(TEXT("target_id"),E.Id);R->SetStringField(TEXT("cause"),Cause);
    R->SetNumberField(TEXT("spilled_ml"),Amount);R->SetNumberField(TEXT("completed_at_s"),SceneClock);
    R->SetNumberField(TEXT("generation_before"),Generation);R->SetNumberField(TEXT("generation_after"),++Generation);AppendReceipt(R);
}

void AHomeActionsCharacter::UpdatePhysicalConsequences(float Dt)
{
    HazardCooldown=FMath::Max(0.f,HazardCooldown-Dt);
    for (const FString Name:{TEXT("coffee_cup"),TEXT("water_jug")})
    {
        auto* E=Resolve(Name);const FVector Velocity=E->Mesh->GetPhysicsLinearVelocity();
        const FVector Previous=PreviousVelocities.FindRef(E->Id);PreviousVelocities.Add(E->Id,Velocity);
        if (Number(E->State,TEXT("liquid_ml"))<=0 || E->Id==HeldId ||
            !String(E->State,TEXT("container_in")).IsEmpty() || SceneClock<2.f) continue;
        const bool Impact=Previous.Z<-140.f && Velocity.Z>Previous.Z+120.f;
        if (Impact) PendingImpacts.Add(E->Id,SceneClock);
        const bool Tilt=FVector::DotProduct(E->Actor->GetActorUpVector(),FVector::UpVector)<.55f;
        if (ActiveId.IsEmpty() && (PendingImpacts.Contains(E->Id) || Tilt))
        {SpillLiquid(*E,PendingImpacts.Contains(E->Id)?TEXT("physical_impact"):TEXT("container_tipped"));PendingImpacts.Remove(E->Id);}
    }
    if (!ActiveId.IsEmpty() || !SeatId.IsEmpty() || FallAlpha>.05f || HazardCooldown>0.f || GetVelocity().Size2D()<65.f) return;
    const auto* Slipper=Resolve(TEXT("slipper"));
    const bool Trip=Slipper->Actor->GetActorLocation().Z<10.f && Slipper->Id!=HeldId &&
        FVector::Dist2D(GetActorLocation(),Slipper->Actor->GetActorLocation())<28.f;
    const auto* Overflow=Resolve(TEXT("overflow_marker"));const auto* Spill=Resolve(TEXT("spill_marker"));
    const bool Wet=(Bool(Overflow->State,TEXT("visible")) && FVector::Dist2D(GetActorLocation(),FVector(-30,-647,0))<38.f) ||
        (Bool(Spill->State,TEXT("visible")) && FVector::Dist2D(GetActorLocation(),Vector(Spill->State,TEXT("position_cm")))<24.f);
    if (Trip || Wet)
    {
        HazardCooldown=6.f;FString Code;
        BeginAction(FGuid::NewGuid().ToString(EGuidFormats::Digits),Trip?TEXT("stumble"):TEXT("slip"),TEXT(""),TEXT(""),Code);
    }
}
