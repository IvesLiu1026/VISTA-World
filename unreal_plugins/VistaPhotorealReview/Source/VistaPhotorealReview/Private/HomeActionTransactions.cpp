#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "PhysicsEngine/PhysicsHandleComponent.h"

using namespace HomeJson;

FVector AHomeActionsCharacter::FingerOffset(bool bLeft) const
{
    TArray<FTransform> G;G.SetNum(Parents.Num());
    for (int32 I=0;I<G.Num();++I) G[I]=Parents[I]>=0?Poses->OpenHand[I]*G[Parents[I]]:Poses->OpenHand[I];
    const int32 Hand=BoneIndex.FindChecked(bLeft?TEXT("hand_l"):TEXT("hand_r"));
    const int32 Tip=BoneIndex.FindChecked(bLeft?TEXT("index_03_l"):TEXT("index_03_r"));
    const int32 Mid=BoneIndex.FindChecked(bLeft?TEXT("index_02_l"):TEXT("index_02_r"));
    const FVector* Fine=bFineContacts?FineTipOffsets.Find(bLeft?TEXT("index_03_l"):TEXT("index_03_r")):nullptr;
    const FVector End=Fine?G[Tip].TransformPosition(*Fine):G[Tip].GetLocation()+(G[Tip].GetLocation()-G[Mid].GetLocation()).GetSafeNormal()*2.1f;
    return G[Hand].InverseTransformPosition(End);
}

FTransform AHomeActionsCharacter::WristAt(const FVector& Point,bool bLeft,bool bPoint,FVector Axis,bool bTop) const
{
    FQuat R=Poses->WristRelativeToCup.GetRotation();
    FVector Offset=Poses->WristRelativeToCup.GetLocation()-FVector(0,0,Poses->ContactReferenceHeightCm);
    if (bLeft)
    {
        const int32 L=BoneIndex.FindChecked(TEXT("hand_l")),Right=BoneIndex.FindChecked(TEXT("hand_r"));
        const FQuat Delta=R*ReferenceGlobal[Right].GetRotation().Inverse();
        R=FQuat(Delta.X,-Delta.Y,-Delta.Z,Delta.W)*ReferenceGlobal[L].GetRotation();
        Offset.X=-Offset.X;
    }
    const FQuat Orientation=bTop?FQuat::FindBetweenNormals(GetActorForwardVector(),FVector::DownVector):
        FQuat::FindBetweenNormals(FVector::UpVector,Axis.GetSafeNormal(SMALL_NUMBER,FVector::UpVector));
    R=Orientation*GetMesh()->GetComponentQuat()*R;
    const FVector Location=bPoint?Point-R.RotateVector(FingerOffset(bLeft)):
        Point+Orientation.RotateVector(GetMesh()->GetComponentQuat().RotateVector(Offset));
    return FTransform(R,Location);
}

FTransform AHomeActionsCharacter::DesiredGrip() const
{
    const auto* E=Resolve(TargetId.IsEmpty()?HeldId:TargetId);
    if (E && bFineContacts && FineSurfaces.Contains(E->Id) && FineSurfaces.FindChecked(E->Id).bHorizontalPinch)
        return FinePinchWrist(*E);
    if (!E || E->ShortId==TEXT("coffee_cup")) return Super::DesiredGrip();
    FVector Point=E->Actor->GetActorLocation()+FVector(0,0,Number(E->Spec,TEXT("grip_height"),ItemHeight*.6f));
    if (E->Spec->HasField(TEXT("grip_offset_cm"))) Point=E->Actor->GetActorTransform().TransformPosition(Vector(E->Spec,TEXT("grip_offset_cm")));
    if (Bool(E->Spec,TEXT("two_hands")))
    {
        FVector Side=E->Actor->GetActorRightVector();
        // Pot loops and box side panels are on the authored X axis.
        Side=E->Actor->GetActorForwardVector();
        if (FVector::DotProduct(Side,GetActorRightVector())<0) Side=-Side;
        Point+=Side*(Number(E->Spec,TEXT("grip_width"),28)*.5f);
        if (bFineContacts && FineSurfaces.Contains(E->Id) && FineSurfaces.FindChecked(E->Id).GripPoints.Num()==2)
        {
            const int32 Index=FVector::DotProduct(Side,E->Actor->GetActorForwardVector())>0?1:0;
            Point=E->Actor->GetActorTransform().TransformPosition(FineSurfaces.FindChecked(E->Id).GripPoints[Index]);
        }
    }
    return WristAt(Point,false,false,Bool(E->Spec,TEXT("two_hands"))?E->Actor->GetActorRightVector():
        E->Actor->GetActorQuat().RotateVector(Vector(E->Spec,TEXT("grip_axis"),FVector::UpVector)),Bool(E->Spec,TEXT("top_grip")));
}

FVector AHomeActionsCharacter::PickupAimPoint() const
{
    const auto* E=Resolve(TargetId.IsEmpty()?HeldId:TargetId);
    return E && E->ShortId!=TEXT("coffee_cup")?ControlPoint(*E):Super::PickupAimPoint();
}

FTransform AHomeActionsCharacter::CarryTarget() const
{
    const auto* E=Resolve(HeldId.IsEmpty()?TargetId:HeldId);
    const bool Two=E && Bool(E->Spec,TEXT("two_hands"));
    const float H=E?Number(E->Spec,TEXT("grip_height"),6.2):6.2;
    return FTransform(GetActorQuat()*HoldRelativeRotation,
        GetActorLocation()+GetActorQuat().RotateVector(FVector(Two?38:32,Two?0:18,26-H)));
}

bool AHomeActionsCharacter::FindPlacement(FVector& Location,FQuat& Rotation) const
{
    const auto* E=Resolve(HeldId);
    if (!E || E->ShortId==TEXT("coffee_cup")) return Super::FindPlacement(Location,Rotation);
    const auto* PC=Cast<APlayerController>(Controller);if (!PC || !E->Mesh.IsValid()) return false;
    FVector Eye;FRotator Look;PC->GetPlayerViewPoint(Eye,Look);
    FCollisionQueryParams P(SCENE_QUERY_STAT(HomePlacement),true,this);P.AddIgnoredActor(E->Actor.Get());
    FHitResult Hit;
    if (!GetWorld()->LineTraceSingleByChannel(Hit,Eye,Eye+Look.Vector()*330.f,ECC_Visibility,P) ||
        Hit.ImpactNormal.Z<.94f || FVector::Dist2D(Hit.ImpactPoint,GetActorLocation())>65.f) return false;
    const FBox B=E->Mesh->GetStaticMesh()->GetBoundingBox();
    const FVector Scale=E->Actor->GetActorScale3D();
    const FVector Center=B.GetCenter()*Scale;
    const FVector Half=B.GetExtent()*Scale;
    Rotation=FRotator(0,E->Actor->GetActorRotation().Yaw,0).Quaternion();
    Location=Hit.ImpactPoint-FVector(0,0,B.Min.Z*Scale.Z)+FVector(0,0,.25f);
    for (int32 I=0;I<8;++I)
    {
        const float A=I*PI/4.f;
        // Support the actual rectangular base of flat/large objects. Pot
        // handles may overhang; its round base is the supporting footprint.
        FVector Offset(FMath::Sign(FMath::Cos(A))*Half.X*.94f,FMath::Sign(FMath::Sin(A))*Half.Y*.94f,0);
        if (E->ShortId==TEXT("pot")) Offset=FVector(FMath::Cos(A),FMath::Sin(A),0)*Number(E->Spec,TEXT("radius"));
        const FVector Point=Hit.ImpactPoint+Rotation.RotateVector(Offset);
        FHitResult Support;
        if (!GetWorld()->LineTraceSingleByChannel(Support,Point+FVector(0,0,2),Point-FVector(0,0,3),ECC_Visibility,P) ||
            Support.ImpactNormal.Z<.94f || FMath::Abs(Support.ImpactPoint.Z-Hit.ImpactPoint.Z)>1.f) return false;
    }
    const FVector TestCenter=Location+Rotation.RotateVector(Center)+FVector(0,0,.15f);
    const FVector TestHalf(FMath::Max(.1f,Half.X-.15f),FMath::Max(.1f,Half.Y-.15f),FMath::Max(.08f,Half.Z-.15f));
    return !GetWorld()->OverlapBlockingTestByChannel(TestCenter,Rotation,ECC_Visibility,FCollisionShape::MakeBox(TestHalf),P);
}

void AHomeActionsCharacter::SelectPickup(FHomeEntity& E)
{
    bAllowReachDetour=E.ShortId!=TEXT("coffee_cup");
    bSceneCarryLift=E.ShortId==TEXT("phone");
    Cup=E.Actor.Get();CupMesh=E.Mesh.Get();ItemRadius=Number(E.Spec,TEXT("radius"),3.7);
    ItemHeight=Number(E.Spec,TEXT("height"),9.6);InitialCupTransform=E.Baseline;
    Poses=HandProfiles.Contains(String(E.Spec,TEXT("grip_profile")))?HandProfiles[String(E.Spec,TEXT("grip_profile"))]:DefaultPoses;
    if (bFineContacts && FineSurfaces.Contains(E.Id) && FineSurfaces.FindChecked(E.Id).bUseWideGrip) Poses=DefaultPoses;
    if (Bool(E.Spec,TEXT("two_hands")))
    {
        FVector Side=E.Actor->GetActorForwardVector();if (FVector::DotProduct(Side,GetActorRightVector())<0) Side=-Side;
        const FVector Center=E.Spec->HasField(TEXT("grip_offset_cm"))?
            E.Actor->GetActorTransform().TransformPosition(Vector(E.Spec,TEXT("grip_offset_cm"))):
            E.Actor->GetActorLocation()+FVector(0,0,Number(E.Spec,TEXT("grip_height")));
        FVector P=Center-Side*(Number(E.Spec,TEXT("grip_width"))*.5f);
        if (bFineContacts && FineSurfaces.Contains(E.Id) && FineSurfaces.FindChecked(E.Id).GripPoints.Num()==2)
        {
            const int32 Index=FVector::DotProduct(Side,E.Actor->GetActorForwardVector())>0?0:1;
            P=E.Actor->GetActorTransform().TransformPosition(FineSurfaces.FindChecked(E.Id).GripPoints[Index]);
        }
        LeftRelativeToItem=WristAt(P,true,false,E.Actor->GetActorRightVector()).GetRelativeTransform(E.Actor->GetActorTransform());
    }
}

bool AHomeActionsCharacter::CheckReach(const FHomeEntity& E,const FVector& Point,FString& Code,bool RequireView) const
{
    const float Height=Point.Z-GetMesh()->GetComponentLocation().Z;
    if (FVector::Dist2D(Point,GetActorLocation())>(Height<35?50.f:90.f) || Height>195.f || Height<0.f)
    {Code=TEXT("OUT_OF_REACH");return false;}
    FVector Eye;FRotator Look;
    const auto* PC=Cast<APlayerController>(Controller);if (!PC) {Code=TEXT("NO_VIEW");return false;}
    PC->GetPlayerViewPoint(Eye,Look);
    if (RequireView && FVector::DotProduct((Point-Eye).GetSafeNormal(),Look.Vector())<.90f)
    {Code=TEXT("LOOK_AT_TARGET");return false;}
    FCollisionQueryParams P(SCENE_QUERY_STAT(HomeActionReach),true,this);FHitResult Hit;
    if (GetWorld()->LineTraceSingleByChannel(Hit,Eye,Point,ECC_Visibility,P) &&
        Hit.GetActor()!=E.Actor.Get() && FVector::Distance(Hit.ImpactPoint,Point)>6.f)
    {Code=TEXT("OCCLUDED");return false;}
    Code=TEXT("READY");return true;
}

void AHomeActionsCharacter::CaptureBefore()
{
    Before.Empty();TSet<FString> Ids={TargetId,SecondaryId,HeldId,SeatId};
    if (ActionId==TEXT("load") || ActionId==TEXT("unload") || ActionId.StartsWith(TEXT("storage.")))
        if (const auto* W=Resolve(TEXT("washer"))) Ids.Add(W->Id);
    if (ActionId==TEXT("spill")) if (const auto* Marker=Resolve(TEXT("spill_marker"))) Ids.Add(Marker->Id);
    for (const auto& Id:Ids)
        if (auto* E=Resolve(Id))
        {
            FHomeBefore B;B.State=Copy(E->State);B.Aperture=E->Aperture;
            if (E->Actor.IsValid())
            {
                B.Transform=E->Actor->GetActorTransform();B.bPhysics=E->Mesh->IsSimulatingPhysics();
                B.Collision=E->Mesh->GetCollisionEnabled();B.Responses=E->Mesh->GetCollisionResponseToChannels();
                B.AttachParent=E->Actor->GetRootComponent()->GetAttachParent();B.AttachSocket=E->Actor->GetRootComponent()->GetAttachSocketName();
                B.Velocity=E->Mesh->GetPhysicsLinearVelocity();B.AngularVelocity=E->Mesh->GetPhysicsAngularVelocityInDegrees();
            }
            Before.Add(Id,MoveTemp(B));
        }
    ActorBefore=GetActorTransform();
    ActionBodyStart=ActorBefore;
    Transaction->SetStringField(TEXT("held_before"),HeldId);Transaction->SetStringField(TEXT("seat_before"),SeatId);
    Transaction->SetNumberField(TEXT("crouch_before"),CrouchAlpha);Transaction->SetNumberField(TEXT("fall_before"),FallAlpha);
    Transaction->SetStringField(TEXT("standing_on_before"),StandingOn);
    Transaction->SetNumberField(TEXT("capsule_radius_before"),GetCapsuleComponent()->GetUnscaledCapsuleRadius());
    Transaction->SetNumberField(TEXT("step_height_before"),GetCharacterMovement()->MaxStepHeight);
    Transaction->SetBoolField(TEXT("feet_override_before"),bSceneFeetOverride);
    for (int32 Side=0;Side<2;++Side) Transaction->SetArrayField(Side==0?TEXT("left_foot_before"):TEXT("right_foot_before"),Values(bSceneFeetOverride?SceneFootWorld[Side]:Feet[Side].Current));
}

bool AHomeActionsCharacter::RestoreBefore()
{
    bool Verified=true;
    GripHandle->ReleaseComponent();
    if (CupMesh) CupMesh->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);
    if (Cup) GetCapsuleComponent()->IgnoreActorWhenMoving(Cup,false);
    for (auto& Pair:Before)
        if (auto* E=Resolve(Pair.Key))
        {
            E->State=Copy(Pair.Value.State);E->Aperture=Pair.Value.Aperture;
            PendingImpacts.Remove(E->Id);PreviousVelocities.Add(E->Id,Pair.Value.Velocity);
            if (E->Actor.IsValid())
            {
                E->Mesh->SetSimulatePhysics(false);E->Actor->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
                E->Actor->SetActorTransform(Pair.Value.Transform,false,nullptr,ETeleportType::TeleportPhysics);
                E->Mesh->SetCollisionEnabled(Pair.Value.Collision);E->Mesh->SetCollisionResponseToChannels(Pair.Value.Responses);
                if (Pair.Value.AttachParent.IsValid()) E->Actor->AttachToComponent(Pair.Value.AttachParent.Get(),FAttachmentTransformRules::KeepWorldTransform,Pair.Value.AttachSocket);
                E->Mesh->SetSimulatePhysics(Pair.Value.bPhysics);
                if (Pair.Value.bPhysics)
                {E->Mesh->SetPhysicsLinearVelocity(Pair.Value.Velocity);E->Mesh->SetPhysicsAngularVelocityInDegrees(Pair.Value.AngularVelocity);}
                Verified&=E->Actor->GetActorTransform().Equals(Pair.Value.Transform,.05f) &&
                    E->Mesh->IsSimulatingPhysics()==Pair.Value.bPhysics && E->Mesh->GetCollisionEnabled()==Pair.Value.Collision &&
                    E->Mesh->GetCollisionResponseToChannels()==Pair.Value.Responses;
            }
            Verified&=FJsonValue::CompareEqual(FJsonValueObject(E->State),FJsonValueObject(Pair.Value.State));
        }
        else Verified=false;
    HeldId=String(Transaction,TEXT("held_before"));SeatId=String(Transaction,TEXT("seat_before"));
    CrouchAlpha=Number(Transaction,TEXT("crouch_before"));FallAlpha=Number(Transaction,TEXT("fall_before"));
    SeatedAlpha=SeatId.IsEmpty()?0.f:1.f;
    StandingOn=String(Transaction,TEXT("standing_on_before"));
    if (auto* Target=Resolve(TargetId)) if (Target->Kind==TEXT("equipment") && Target->Actor.IsValid())
        GetCapsuleComponent()->IgnoreActorWhenMoving(Target->Actor.Get(),!StandingOn.IsEmpty());
    bSceneFeetOverride=Bool(Transaction,TEXT("feet_override_before"));
    SceneFootWorld[0]=Vector(Transaction,TEXT("left_foot_before"));SceneFootWorld[1]=Vector(Transaction,TEXT("right_foot_before"));
    GetCapsuleComponent()->SetCapsuleRadius(Number(Transaction,TEXT("capsule_radius_before"),27.f));
    GetCharacterMovement()->MaxStepHeight=Number(Transaction,TEXT("step_height_before"),22.f);
    SetActorTransform(ActorBefore,false,nullptr,ETeleportType::TeleportPhysics);
    Verified&=GetActorTransform().Equals(ActorBefore,.05f);
    GetCharacterMovement()->StopMovementImmediately();GetCharacterMovement()->SetMovementMode(StandingOn.IsEmpty()?MOVE_Walking:MOVE_Flying);
    bFeetReady=false;
    if (auto* E=Resolve(HeldId))
    {
        SelectPickup(*E);CupMesh->SetSimulatePhysics(true);
        GripHandle->GrabComponentAtLocationWithRotation(CupMesh,NAME_None,CupMesh->GetComponentLocation(),CupMesh->GetComponentRotation());
        GetCapsuleComponent()->IgnoreActorWhenMoving(Cup,true);CupMesh->SetCollisionResponseToChannel(ECC_Pawn,ECR_Ignore);
        HandRelativeToCup=DesiredGrip().GetRelativeTransform(CupMesh->GetComponentTransform());
        HoldStart=CupMesh->GetComponentTransform();HoldRelativeRotation=GetActorQuat().Inverse()*HoldStart.GetRotation();
        Phase=EEmbodiedPhase::Held;PhaseTime=0;ReachAlpha=FingerAlpha=1;
        return Verified && GripHandle->GrabbedComponent==CupMesh;
    }
    Phase=EEmbodiedPhase::Idle;PhaseTime=0;ReachAlpha=FingerAlpha=LeftReachAlpha=LeftFingerAlpha=0;return Verified;
}

bool AHomeActionsCharacter::BeginAction(const FString& Command,const FString& Requested,const FString& Target,const FString& Secondary,FString& Code)
{
    if (!bSceneReady) {Code=TEXT("SCENE_NOT_READY");return false;}
    if (!ActiveId.IsEmpty() || (Phase!=EEmbodiedPhase::Idle && Phase!=EEmbodiedPhase::Held)) {Code=TEXT("BUSY");return false;}
    if (Ledger.Num()>=4096) {Code=TEXT("SESSION_LEDGER_FULL");return false;}
    FHomeEntity* E=Resolve(Target);FHomeEntity* S=Resolve(Secondary);
    FString A=Requested;
    // The source generic insert has explicit item/container roles on this scene.
    if (A==TEXT("insert")) A=TEXT("storage.insert");
    if (A==TEXT("use") && E)
    {
        if (E->State->HasField(TEXT("open"))) A=Bool(E->State,TEXT("open"))?TEXT("close"):TEXT("articulation.open");
        else if (E->Kind==TEXT("appliance")) A=Bool(E->State,TEXT("active"))?TEXT("turn_off"):TEXT("turn_on");
        else {Code=TEXT("NO_DEFAULT_USE");return false;}
    }
    const TSet<FString> Body={TEXT("idle"),TEXT("walk"),TEXT("jog"),TEXT("sprint"),TEXT("turn_in_place"),TEXT("crouch"),TEXT("pause"),
        TEXT("stumble"),TEXT("slip"),TEXT("fall"),TEXT("impact"),TEXT("recover"),TEXT("look_at")};
    const bool Storage=A==TEXT("storage.insert") || A==TEXT("storage.remove") || A==TEXT("load") || A==TEXT("unload");
    if (!Body.Contains(A) && !E) {Code=TEXT("TARGET_NOT_FOUND");return false;}
    if (E && !E->Actor.IsValid() && A!=TEXT("inspect") && A!=TEXT("look_at")) {Code=TEXT("NO_PHYSICAL_TARGET");return false;}
    if (A==TEXT("spill") && (!E || Number(E->State,TEXT("liquid_ml"))<=0)) {Code=TEXT("NO_LIQUID");return false;}
    if (E && !Bool(E->State,TEXT("visible"),true)) {Code=TEXT("TARGET_NOT_VISIBLE");return false;}
    if (A==TEXT("pick_up") && (!Bool(E->State,TEXT("portable")) || !String(E->State,TEXT("equipped_by")).IsEmpty()))
    {Code=TEXT("ITEM_NOT_PORTABLE");return false;}
    if (Storage)
    {
        if (!S || S->Kind!=TEXT("container") || !E || E->Kind!=TEXT("pickup") || E==S) {Code=TEXT("INVALID_STORAGE_ROLES");return false;}
        if (!Bool(S->State,TEXT("open"))) {Code=TEXT("CONTAINER_CLOSED");return false;}
        const bool Insert=A==TEXT("storage.insert") || A==TEXT("load");
        if ((Insert && HeldId!=E->Id) || (!Insert && (!HeldId.IsEmpty() || String(E->State,TEXT("container_in"))!=S->Id)))
        {Code=TEXT("STORAGE_OWNERSHIP_MISMATCH");return false;}
        if (Insert)
        {
            const FVector Capacity=Vector(S->Spec,TEXT("capacity_cm"));
            const FTransform TargetPose(FRotator(0,Number(S->Spec,TEXT("storage_yaw_deg")),0),FVector::ZeroVector,E->Actor->GetActorScale3D());
            const FVector Extent=E->Mesh->GetStaticMesh()->GetBounds().TransformBy(TargetPose).BoxExtent;
            if (Extent.X*2>Capacity.X || Extent.Y*2>Capacity.Y || Number(E->Spec,TEXT("height"))>Capacity.Z)
            {Code=TEXT("ITEM_DOES_NOT_FIT");return false;}
            if (S->State->GetArrayField(TEXT("contents")).Num()) {Code=TEXT("STORAGE_SLOT_OCCUPIED");return false;}
        }
        if (!CheckReach(*S,ControlPoint(*S),Code,false)) return false;
    }
    else if (!Body.Contains(A) && !Contains(E->Spec,TEXT("actions"),A) && A!=TEXT("spill"))
    {Code=TEXT("AFFORDANCE_NOT_SUPPORTED");return false;}
    if (A==TEXT("pick_up") && (!HeldId.IsEmpty() || !String(E->State,TEXT("container_in")).IsEmpty()))
    {Code=TEXT("ITEM_NOT_FREE");return false;}
    if ((A==TEXT("place") || A==TEXT("drop") || A==TEXT("pour") || A==TEXT("spill") || A==TEXT("equip") || A==TEXT("carry")) && (!E || HeldId!=E->Id))
    {Code=TEXT("ITEM_NOT_HELD");return false;}
    if (A==TEXT("unequip") && (!E || !HeldId.IsEmpty() || String(E->State,TEXT("equipped_by"))!=TEXT("player")))
    {Code=TEXT("EQUIPMENT_OWNERSHIP_MISMATCH");return false;}
    if ((A==TEXT("articulation.open") && Bool(E->State,TEXT("open"))) || (A==TEXT("close") && !Bool(E->State,TEXT("open"))))
    {Code=TEXT("ALREADY_IN_STATE");return false;}
    if (A==TEXT("stand_up") && SeatId!=(E?E->Id:TEXT(""))) {Code=TEXT("NOT_SEATED_HERE");return false;}
    if (A==TEXT("step_down") && StandingOn!=(E?E->Id:TEXT(""))) {Code=TEXT("NOT_ON_THIS_PLATFORM");return false;}
    if (A==TEXT("step_up") && !StandingOn.IsEmpty()) {Code=TEXT("ALREADY_ON_PLATFORM");return false;}
    if (A==TEXT("sit_down") && (!SeatId.IsEmpty() || Bool(E->State,TEXT("occupied")))) {Code=TEXT("SEAT_UNAVAILABLE");return false;}
    if (E && E->ShortId==TEXT("washer_door") && A==TEXT("articulation.open") && Bool(Resolve(TEXT("washer"))->State,TEXT("active")))
    {Code=TEXT("WASHER_DOOR_LOCKED");return false;}
    if (E && E->ShortId==TEXT("washer") && (A==TEXT("turn_on") || A==TEXT("appliance.toggle_rotary")) && !Bool(E->State,TEXT("active")))
    {
        const auto* Door=Resolve(TEXT("washer_door"));
        if (Bool(Door->State,TEXT("open"))) {Code=TEXT("WASHER_DOOR_OPEN");return false;}
        if (Door->State->GetArrayField(TEXT("contents")).Num()==0) {Code=TEXT("WASHER_EMPTY");return false;}
    }
    if (A==TEXT("pour"))
    {
        if (!S || E==S || !S->Spec->HasField(TEXT("capacity_ml")) || Number(E->State,TEXT("liquid_ml"))<=0)
        {Code=TEXT("INVALID_LIQUID_ROLES");return false;}
        if (Number(S->State,TEXT("liquid_ml"))>=Number(S->Spec,TEXT("capacity_ml"))) {Code=TEXT("RECEIVER_FULL");return false;}
        if (!CheckReach(*S,ControlPoint(*S),Code,false)) return false;
    }
    if ((A==TEXT("inspect") || A==TEXT("look_at")) && E)
    {
        FVector Eye;FRotator Look;const auto* PC=Cast<APlayerController>(Controller);
        if (!PC) {Code=TEXT("NO_VIEW");return false;}PC->GetPlayerViewPoint(Eye,Look);
        const FVector Point=ControlPoint(*E);const FVector Delta=Point-Eye;
        if (Delta.Size()>330.f) {Code=TEXT("OUT_OF_VIEW_RANGE");return false;}
        if (A==TEXT("inspect") && FVector::DotProduct(Delta.GetSafeNormal(),Look.Vector())<.9f) {Code=TEXT("LOOK_AT_TARGET");return false;}
        FCollisionQueryParams P(SCENE_QUERY_STAT(HomeInspect),true,this);FHitResult Hit;
        if (GetWorld()->LineTraceSingleByChannel(Hit,Eye,Point,ECC_Visibility,P) && Hit.GetActor()!=E->Actor.Get() && FVector::Distance(Hit.ImpactPoint,Point)>6.f)
        {Code=TEXT("OCCLUDED");return false;}
    }
    const bool Physical=A==TEXT("pick_up") || A==TEXT("place") || A==TEXT("drop");
    if (E && !Physical && !Storage && A!=TEXT("pour") && A!=TEXT("spill") && A!=TEXT("equip") && A!=TEXT("unequip") && A!=TEXT("step_down") && A!=TEXT("stand_up") && A!=TEXT("seated_idle") && A!=TEXT("carry") && A!=TEXT("look_at") && A!=TEXT("inspect"))
    {
        if (!HeldId.IsEmpty()) {Code=TEXT("HANDS_OCCUPIED");return false;}
        if (!CheckReach(*E,ControlPoint(*E),Code)) return false;
    }
    ActiveId=Command;ActionId=A;TargetId=E?E->Id:TEXT("");SecondaryId=S?S->Id:TEXT("");
    ActionTime=0;ActionStage=0;bCommitted=false;bPhysicalAction=Physical;ContactMaximum=0;
    Transaction=MakeShared<FJsonObject>();Transaction->SetStringField(TEXT("schema"),TEXT("vista.home-action-receipt/v1"));
    Transaction->SetStringField(TEXT("command_id"),Command);Transaction->SetStringField(TEXT("session_id"),SessionId);
    Transaction->SetStringField(TEXT("requested_action"),Requested);Transaction->SetStringField(TEXT("action"),A);
    Transaction->SetStringField(TEXT("target_id"),TargetId);Transaction->SetStringField(TEXT("secondary_target_id"),SecondaryId);
    Transaction->SetStringField(TEXT("event_id"),EventId);Transaction->SetStringField(TEXT("revision"),Revision);
    Transaction->SetNumberField(TEXT("generation_before"),Generation);Transaction->SetNumberField(TEXT("started_at_s"),SceneClock);
    Transaction->SetStringField(TEXT("status"),TEXT("running"));Ledger.Add(Command,Transaction);
    CaptureBefore();
    if (Physical)
    {
        SelectPickup(*E);
        if (A==TEXT("pick_up"))
        {
            AEmbodiedReviewCharacter::EmbodiedInteract();
            if (Phase!=EEmbodiedPhase::Reaching) {Code=TEXT("PICKUP_REACH_REJECTED");FinishAction(false,Code);return false;}
        }
        if (A==TEXT("place"))
        {
            AEmbodiedReviewCharacter::EmbodiedPlace();
            if (Phase!=EEmbodiedPhase::Placing) {Code=TEXT("NO_SUPPORTED_PLACEMENT");FinishAction(false,Code);return false;}
        }
        if (A==TEXT("drop")) AEmbodiedReviewCharacter::EmbodiedDrop();
    }
    else
    {
        GetCharacterMovement()->StopMovementImmediately();bSceneActionBusy=true;
        ActionHandStart=GetMesh()->GetSocketTransform(TEXT("hand_r"));
        if (E && HeldId.IsEmpty())
        {
            Poses=HandProfiles.Contains(String(E->Spec,TEXT("grip_profile")))?HandProfiles[String(E->Spec,TEXT("grip_profile"))]:DefaultPoses;
            ActionHandEnd=WristAt(ControlPoint(*E),false,E->Kind==TEXT("appliance") && !E->Spec->HasField(TEXT("axis")),
                E->Actor.IsValid()?E->Actor->GetActorQuat().RotateVector(Vector(E->Spec,TEXT("grip_axis"),FVector::UpVector)):FVector::UpVector);
        }
        if (E) {ActionStartAperture=E->Aperture;ActionEndAperture=A==TEXT("close")?0.f:1.f;}
        if (Storage || A==TEXT("pour") || A==TEXT("spill"))
        {
            SelectPickup(*E);ItemBefore=E->Actor->GetActorTransform();
            if (Storage)
            {
                PlaceLocation=Vector(S->Spec,TEXT("storage_cm"));
                StorageEntry=Vector(S->Spec,TEXT("entry_cm"),PlaceLocation+FVector(0,35,0));
                PlaceRotation=FRotator(0,Number(S->Spec,TEXT("storage_yaw_deg")),0).Quaternion();
            }
            else if (S) PlaceLocation=S->Actor->GetActorLocation()+FVector(0,0,Number(S->Spec,TEXT("height"),30)+13);
            else PlaceLocation=E->Actor->GetActorLocation();
        }
        if (A==TEXT("sit_down")) SeatPelvisWorld=E->Actor->GetActorTransform().TransformPosition(E->Baseline.InverseTransformPosition(Vector(E->Spec,TEXT("seat_cm"))));
        if (A==TEXT("equip") || A==TEXT("unequip"))
        {SelectPickup(*E);ItemBefore=E->Actor->GetActorTransform();ActionHandEnd=DesiredGrip();bControlHeld=false;}
    }
    Code=TEXT("STARTED");return true;
}

void AHomeActionsCharacter::HomeAction(const FString& Action,const FString& Target,const FString& Secondary)
{
    const FString Command=FGuid::NewGuid().ToString(EGuidFormats::Digits);FString Code;
    if (!BeginAction(Command,Action,Target,Secondary,Code))
    {
        FeedbackMessage(Code);LastCode=Code;
        if (!Ledger.Contains(Command))
        {
            auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("command_id"),Command);R->SetStringField(TEXT("action"),Action);
            R->SetStringField(TEXT("target_id"),Target);R->SetStringField(TEXT("status"),TEXT("rejected"));R->SetStringField(TEXT("code"),Code);
            R->SetNumberField(TEXT("generation_after"),Generation);Ledger.Add(Command,R);AppendReceipt(R);
        }
    }
}

void AHomeActionsCharacter::FinishAction(bool Success,const FString& Code)
{
    if (ActiveId.IsEmpty() || !Transaction) return;
    if (!Success)
        if (const auto* E=Resolve(TargetId)) if (E->Actor.IsValid())
        {
            Transaction->SetArrayField(TEXT("target_cm_before_recovery"),Values(E->Actor->GetActorLocation()));
            Transaction->SetArrayField(TEXT("placement_goal_cm"),Values(PlaceLocation));
        }
    Transaction->SetNumberField(TEXT("right_wrist_error_before_recovery_cm"),RightContactError);
    if (FineContactSnapshot) Transaction->SetObjectField(TEXT("fine_contact_before_recovery"),Copy(FineContactSnapshot));
    Transaction->SetNumberField(TEXT("left_wrist_error_before_recovery_cm"),LeftContactError);
    bool Restored=true;
    if (!Success) Restored=RestoreBefore();
    Transaction->SetStringField(TEXT("status"),Success?TEXT("succeeded"):(Restored?TEXT("failed"):TEXT("rollback_failed")));
    Transaction->SetStringField(TEXT("code"),Code);Transaction->SetBoolField(TEXT("contact_committed"),bCommitted);
    Transaction->SetBoolField(TEXT("rollback_verified"),!Success && Restored);
    Transaction->SetNumberField(TEXT("completed_at_s"),SceneClock);Transaction->SetNumberField(TEXT("max_contact_error_cm"),ContactMaximum);
    Transaction->SetNumberField(TEXT("terminal_reach_alpha"),ReachAlpha);
    if (ReachAlpha>.95f) Transaction->SetNumberField(TEXT("terminal_right_wrist_error_cm"),RightContactError);
    else Transaction->SetField(TEXT("terminal_right_wrist_error_cm"),MakeShared<FJsonValueNull>());
    if (LeftReachAlpha>.95f) Transaction->SetNumberField(TEXT("terminal_left_wrist_error_cm"),LeftContactError);
    else Transaction->SetField(TEXT("terminal_left_wrist_error_cm"),MakeShared<FJsonValueNull>());
    if (Success)
    {
        ++Generation;FString Semantic=ActionId;
        if (Semantic==TEXT("articulation.open")) Semantic=TEXT("open");
        if (Semantic==TEXT("sit_down")) Semantic=TEXT("sit");
        Interactions.Add(TargetId+TEXT("#")+Semantic);
    }
    Transaction->SetNumberField(TEXT("generation_after"),Generation);AppendReceipt(Transaction);
    LastCode=Code;FeedbackMessage(Code);ActiveId.Empty();bSceneActionBusy=false;bPhysicalAction=false;bControlHeld=false;
    GetCharacterMovement()->StopMovementImmediately();
    if (HeldId.IsEmpty() && Phase==EEmbodiedPhase::Idle) ReachAlpha=FingerAlpha=LeftReachAlpha=LeftFingerAlpha=0;
    UpdateEvent(0);PublishState();
}

void AHomeActionsCharacter::HomeCancel() { if (!ActiveId.IsEmpty()) FinishAction(false,TEXT("CANCELLED")); }
void AHomeActionsCharacter::CancelReach(const FString& Reason)
{
    if (!ActiveId.IsEmpty()) {FinishAction(false,Reason);return;}
    Super::CancelReach(Reason);
}
void AHomeActionsCharacter::SetPhase(EEmbodiedPhase NewPhase)
{
    const auto Old=Phase;Super::SetPhase(NewPhase);
    if (!bSceneReady || ActiveId.IsEmpty() || !bPhysicalAction) return;
    if (NewPhase==EEmbodiedPhase::Held && ActionId==TEXT("pick_up"))
    {
        if (FineContactSnapshot) Transaction->SetObjectField(TEXT("fine_contact_at_commit"),Copy(FineContactSnapshot));
        ContactMaximum=FMath::Max(HandErrorCm,LeftContactError);
        if (Bool(Resolve(TargetId)->Spec,TEXT("two_hands")) && LeftContactError>1.6f)
        {FinishAction(false,TEXT("LEFT_HAND_CONTACT_REQUIRED"));return;}
        HeldId=TargetId;auto* E=Resolve(HeldId);E->State->SetStringField(TEXT("held_by"),TEXT("player"));
        if (E->State->HasField(TEXT("mounted"))) E->State->SetBoolField(TEXT("mounted"),false);
        E->State->SetField(TEXT("container_in"),MakeShared<FJsonValueNull>());bCommitted=true;
        FinishAction(true,TEXT("PICKUP_COMPLETE"));
    }
    else if (NewPhase==EEmbodiedPhase::Held && Old==EEmbodiedPhase::Placing && ActionId==TEXT("place"))
        FinishAction(false,TEXT("PLACEMENT_BLOCKED"));
    else if (NewPhase==EEmbodiedPhase::Idle && (ActionId==TEXT("place") || ActionId==TEXT("drop")))
        FinishAction(true,ActionId==TEXT("place")?TEXT("PLACEMENT_COMPLETE"):TEXT("DROP_COMPLETE"));
}
void AHomeActionsCharacter::ReleaseCup(bool Dropped)
{
    const FString Released=HeldId;
    Super::ReleaseCup(Dropped);
    if (!bSceneReady || bSuppressReceipt) return;
    if (auto* E=Resolve(HeldId)) E->State->SetField(TEXT("held_by"),MakeShared<FJsonValueNull>());
    HeldId.Empty();bCommitted=true;
    if (ActiveId.IsEmpty() && !Released.IsEmpty())
    {
        auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("schema"),TEXT("vista.home-physical-outcome/v1"));
        R->SetStringField(TEXT("session_id"),SessionId);R->SetStringField(TEXT("target_id"),Released);
        R->SetStringField(TEXT("cause"),TEXT("grip_released"));R->SetNumberField(TEXT("generation_before"),Generation);
        R->SetNumberField(TEXT("generation_after"),++Generation);R->SetNumberField(TEXT("completed_at_s"),SceneClock);AppendReceipt(R);
    }
}

void AHomeActionsCharacter::UpdateInteraction(float Dt)
{
    if (!bSceneReady) {Super::UpdateInteraction(Dt);return;}
    if (!ActiveId.IsEmpty() && !bPhysicalAction) {UpdateSemanticAction(Dt);return;}
    Super::UpdateInteraction(Dt);
    if (!ActiveId.IsEmpty() && bPhysicalAction && Phase==EEmbodiedPhase::Reaching && PhaseTime>.8f && HandErrorCm>1.f &&
        FVector::Dist2D(GetActorLocation(),ActorBefore.GetLocation())<20.f)
    {
        FVector Delta=DesiredGrip().GetLocation()-GetMesh()->GetSocketLocation(TEXT("hand_r"));Delta.Z=0;
        FHitResult Hit;SetActorLocation(GetActorLocation()+Delta.GetClampedToMaxSize(Dt*20.f),true,&Hit);
    }
}

void AHomeActionsCharacter::RefreshScenePoseGoals()
{
    if (!bSceneReady) return;
    if (!ActiveId.IsEmpty() && (ActionId==TEXT("step_up") || ActionId==TEXT("step_down"))) {LastHandGoal=ActionHandEnd;return;}
    if (!ActiveId.IsEmpty() && (ActionId==TEXT("equip") || ActionId==TEXT("unequip"))) {LastHandGoal=ActionHandEnd;return;}
    const bool BodyCarry=!HeldId.IsEmpty() && (ActionId==TEXT("walk") || ActionId==TEXT("jog") || ActionId==TEXT("sprint") ||
        ActionId==TEXT("turn_in_place") || ActionId==TEXT("crouch") || ActionId==TEXT("inspect") || ActionId==TEXT("look_at") ||
        ActionId==TEXT("idle") || ActionId==TEXT("pause") || ActionId==TEXT("carry"));
    if (!ActiveId.IsEmpty() && !bPhysicalAction && !BodyCarry && ActionId!=TEXT("storage.insert") && ActionId!=TEXT("storage.remove") &&
        ActionId!=TEXT("load") && ActionId!=TEXT("unload") && ActionId!=TEXT("pour") && ActionId!=TEXT("spill")) LastHandGoal=ActionHandEnd;
    const auto* E=Resolve(HeldId.IsEmpty()?TargetId:HeldId);
    if (E && E->Actor.IsValid() && Bool(E->Spec,TEXT("two_hands")) && ReachAlpha>0.f)
    {
        LeftHandGoal=LeftRelativeToItem*E->Actor->GetActorTransform();LeftReachAlpha=ReachAlpha;LeftFingerAlpha=FingerAlpha;
        LeftContactError=FVector::Distance(GetMesh()->GetSocketLocation(TEXT("hand_l")),LeftHandGoal.GetLocation());
    }
    else {LeftReachAlpha=LeftFingerAlpha=0;LeftContactError=0;}
}
