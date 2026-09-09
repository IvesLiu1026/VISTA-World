#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/LightComponent.h"
#include "Materials/MaterialInterface.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Canvas.h"
#include "Engine/StaticMeshActor.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "InputCoreTypes.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "PhysicsEngine/PhysicsHandleComponent.h"
#include "TimerManager.h"

using namespace HomeJson;

namespace
{
FString ActionLabel(const FString& Action)
{
    static const TMap<FString,FString> Names={
        {TEXT("articulation.open"),TEXT("Open")},{TEXT("close"),TEXT("Close")},
        {TEXT("storage.insert"),TEXT("Put inside")},{TEXT("storage.remove"),TEXT("Take out")},
        {TEXT("pick_up"),TEXT("Pick up")},{TEXT("place"),TEXT("Place on surface")},{TEXT("drop"),TEXT("Drop")},
        {TEXT("equip"),TEXT("Put on backpack")},{TEXT("unequip"),TEXT("Take off backpack")},
        {TEXT("pour"),TEXT("Pour into container")},{TEXT("spill"),TEXT("Tip out liquid")},
        {TEXT("step_up"),TEXT("Climb ladder")},{TEXT("step_down"),TEXT("Climb down")},
        {TEXT("sit_down"),TEXT("Sit down")},{TEXT("stand_up"),TEXT("Stand up")},
        {TEXT("pull_drag"),TEXT("Pull")},{TEXT("contact.brace"),TEXT("Hold ladder rail")},
        {TEXT("appliance.toggle_rotary"),TEXT("Turn control")},{TEXT("press_button"),TEXT("Press button")}};
    if (const auto* Name=Names.Find(Action)) return *Name;
    return Action.Replace(TEXT("_"),TEXT(" "));
}
FString FeedbackLabel(const FString& Code)
{
    static const TMap<FString,FString> Labels={
        {TEXT("ACTION_COMPLETE"),TEXT("Done")},{TEXT("PICKUP_COMPLETE"),TEXT("Object picked up")},
        {TEXT("PLACEMENT_COMPLETE"),TEXT("Object placed")},{TEXT("DROP_COMPLETE"),TEXT("Object released")},
        {TEXT("INSERT_COMPLETE"),TEXT("Object stored")},{TEXT("REMOVE_COMPLETE"),TEXT("Object taken out")},
        {TEXT("POUR_COMPLETE"),TEXT("Pour complete")},{TEXT("SPILL_COMPLETE"),TEXT("Liquid spilled")},
        {TEXT("PLATFORM_REACHED"),TEXT("On the top platform - E to climb down")},{TEXT("GROUND_REACHED"),TEXT("Back on the floor")},
        {TEXT("EQUIPMENT_REMOVED"),TEXT("Backpack taken off")},{TEXT("OBSERVED"),TEXT("Inspected")},
        {TEXT("SCENE_RESET"),TEXT("Home reset")},{TEXT("EVENT_STARTED"),TEXT("Scenario ready")},
        {TEXT("CANCELLED"),TEXT("Action cancelled; previous state restored")},
        {TEXT("OUT_OF_REACH"),TEXT("Move closer to the object")},{TEXT("LOOK_AT_TARGET"),TEXT("Look at the object")},
        {TEXT("OCCLUDED"),TEXT("An object blocks the reach")},{TEXT("HANDS_OCCUPIED"),TEXT("Put down what you are carrying first")},
        {TEXT("WASHER_DOOR_LOCKED"),TEXT("Stop the washer before opening its door")},
        {TEXT("WASHER_DOOR_OPEN"),TEXT("Close the washer door first")},{TEXT("WASHER_EMPTY"),TEXT("Put clothes in the washer first")},
        {TEXT("DOOR_APPROACH_BLOCKED"),TEXT("Move to the side to give the door room")},
        {TEXT("NO_SUPPORTED_PLACEMENT"),TEXT("Look at a clear, flat surface within reach")},
        {TEXT("ITEM_NOT_HELD"),TEXT("Pick up the object first")},{TEXT("CONTAINER_CLOSED"),TEXT("Open the container first")},
        {TEXT("ITEM_DOES_NOT_FIT"),TEXT("This object does not fit in the container")},
        {TEXT("STORAGE_SLOT_OCCUPIED"),TEXT("Take out the stored object first")},
        {TEXT("RECEIVER_FULL"),TEXT("The receiving container is full")},{TEXT("BUSY"),TEXT("Finish this action, or press G to cancel")}};
    if (const auto* Label=Labels.Find(Code)) return *Label;
    return Code.Contains(TEXT("_"))?Code.ToLower().Replace(TEXT("_"),TEXT(" ")):Code;
}
}


FHomeEntity* AHomeActionsCharacter::Resolve(const FString& Name)
{
    if (FHomeEntity* E=Entities.Find(Name)) return E;
    for (auto& Pair:Entities) if (Pair.Value.ShortId==Name) return &Pair.Value;
    return nullptr;
}
const FHomeEntity* AHomeActionsCharacter::Resolve(const FString& Name) const
{ return const_cast<AHomeActionsCharacter*>(this)->Resolve(Name); }

void AHomeActionsCharacter::BeginPlay()
{
    Super::BeginPlay();
    FString Text;
    if (!FFileHelper::LoadFileToString(Text,*(FPaths::ProjectConfigDir()/TEXT("VistaHomeActions.json")))) return;
    Contract=Decode(Text);
    if (!Contract || String(Contract,TEXT("schema"))!=TEXT("vista.photoreal-actions/v1") || !bReady) return;
    Revision=String(Contract,TEXT("revision"));SessionId=FGuid::NewGuid().ToString(EGuidFormats::Digits);
    if (!FParse::Value(FCommandLine::Get(),TEXT("VistaHomeBridge="),BridgeDir))
        BridgeDir=FPaths::ProjectSavedDir()/TEXT("HomeActions")/SessionId;
    IFileManager::Get().MakeDirectory(*BridgeDir,true);
    if (IFileManager::Get().FileExists(*(BridgeDir/TEXT("session.json"))))
    { UE_LOG(LogTemp,Error,TEXT("HOME_BRIDGE_ALREADY_USED"));return; }
    TMap<FString,AStaticMeshActor*> Actors;
    for (TActorIterator<AStaticMeshActor> It(GetWorld());It;++It)
        for (FName Tag:It->Tags)
            if (Tag.ToString().StartsWith(TEXT("HomeLabel="))) Actors.Add(Tag.ToString().Mid(10),*It);
    const TArray<TSharedPtr<FJsonValue>>* Rows;
    if (!Contract->TryGetArrayField(TEXT("entities"),Rows)) return;
    for (const auto& V:*Rows)
    {
        FHomeEntity E;E.Spec=V->AsObject();E.Id=String(E.Spec,TEXT("id"));E.ShortId=String(E.Spec,TEXT("short_id"));
        E.Kind=String(E.Spec,TEXT("kind"));E.Display=String(E.Spec,TEXT("display"));E.Room=String(E.Spec,TEXT("room"));
        const TSharedPtr<FJsonObject>* Initial;
        E.State=E.Spec->TryGetObjectField(TEXT("initial_state"),Initial)?Copy(*Initial):MakeShared<FJsonObject>();
        const FString Label=String(E.Spec,TEXT("label"));
        if (!Label.IsEmpty())
        {
            AStaticMeshActor** Found=Actors.Find(Label);
            if (!Found) {UE_LOG(LogTemp,Error,TEXT("HOME_BINDING_MISSING %s %s"),*E.Id,*Label);return;}
            E.Actor=*Found;E.Mesh=(*Found)->GetStaticMeshComponent();
            if (E.Spec->HasField(TEXT("position_cm"))) E.Actor->SetActorLocation(Vector(E.Spec,TEXT("position_cm")),false,nullptr,ETeleportType::TeleportPhysics);
            E.Closed=E.Actor->GetActorTransform();E.Baseline=E.Closed;
            E.ControlLocal=E.Closed.InverseTransformPosition(Vector(E.Spec,TEXT("control_cm")));
            if (E.Kind==TEXT("pickup"))
            {
                E.Mesh->SetMobility(EComponentMobility::Movable);
                E.Mesh->SetCollisionProfileName(TEXT("PhysicsActor"));
                E.Mesh->SetMassOverrideInKg(NAME_None,Number(E.Spec,TEXT("mass"),.5),true);
                E.Mesh->SetLinearDamping(.3f);E.Mesh->SetAngularDamping(.8f);
                E.Mesh->BodyInstance.bUseCCD=true;E.bBaselinePhysics=!Bool(E.State,TEXT("mounted"));E.Mesh->SetSimulatePhysics(E.bBaselinePhysics);
                if (E.Spec->HasField(TEXT("liquid_ml"))) E.State->SetNumberField(TEXT("liquid_ml"),Number(E.Spec,TEXT("liquid_ml")));
            }
            if (E.Kind==TEXT("door") || E.Kind==TEXT("container") || E.Kind==TEXT("drawer") || E.Spec->HasField(TEXT("axis")))
                E.Mesh->SetMobility(EComponentMobility::Movable);
            const TArray<TSharedPtr<FJsonValue>>* ChildLabels;
            if (E.Spec->TryGetArrayField(TEXT("children"),ChildLabels))
                for (const auto& C:*ChildLabels)
                    if (AStaticMeshActor** Child=Actors.Find(C->AsString()))
                    {
                        (*Child)->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
                        (*Child)->SetActorEnableCollision(false);
                        (*Child)->AttachToActor(E.Actor.Get(),FAttachmentTransformRules::KeepWorldTransform);
                        E.Children.Add(*Child);
                    }
            ApplyAperture(E,Bool(E.State,TEXT("open"))?1.f:0.f);
        }
        Entities.Add(E.Id,MoveTemp(E));
    }
    if (UEmbodiedPoseLibrary* NewPoses=LoadObject<UEmbodiedPoseLibrary>(nullptr,TEXT("/Game/VISTA/HomeActionsR2/DA_BodyPoses.DA_BodyPoses"))) Poses=NewPoses;
    else {UE_LOG(LogTemp,Error,TEXT("HOME_BIMANUAL_POSES_MISSING"));return;}
    DefaultPoses=Poses;
    const TSharedPtr<FJsonObject>* Profiles;
    if (Contract->TryGetObjectField(TEXT("pose_profiles"),Profiles))
        for (const auto& Pair:(*Profiles)->Values)
        {
            auto* Library=LoadObject<UEmbodiedPoseLibrary>(nullptr,*Pair.Value->AsString());
            if (!Library) {UE_LOG(LogTemp,Error,TEXT("HOME_HAND_PROFILE_MISSING %s"),*Pair.Key);return;}
            HandProfiles.Add(Pair.Key,Library);
        }
    for (auto& Pair:Entities)
        if (auto* Container=Resolve(String(Pair.Value.State,TEXT("container_in"))))
        {
            Pair.Value.Mesh->SetSimulatePhysics(false);
            auto A=Container->State->GetArrayField(TEXT("contents"));A.Add(MakeShared<FJsonValueString>(Pair.Key));
            Container->State->SetArrayField(TEXT("contents"),A);
        }
    for (const FString Name:{TEXT("tv_screen"),TEXT("computer_screen"),TEXT("lamp_bulb")})
        if (auto** Found=Actors.Find(TEXT("PR_")+Name)) Effects.Add(Name,*Found);
    for (TActorIterator<AActor> It(GetWorld());It;++It)
        if (It->Tags.Contains(FName(TEXT("HomeLabel=Living floor lamp")))) FloorLight=It->FindComponentByClass<ULightComponent>();
    const FString MaterialRoot=String(Contract,TEXT("presentation_assets_root"),TEXT("/Game/VISTA/HomeActionsR2"));
    for (const FString Name:{TEXT("M_ScreenOn"),TEXT("M_ScreenOff"),TEXT("M_LampOn"),TEXT("M_LampOff")})
        DeviceMaterials.Add(Name,LoadObject<UMaterialInterface>(nullptr,*(MaterialRoot+TEXT("/")+Name+TEXT(".")+Name)));
    auto Session=MakeShared<FJsonObject>();Session->SetStringField(TEXT("session_id"),SessionId);
    Session->SetStringField(TEXT("revision"),Revision);Session->SetStringField(TEXT("schema"),TEXT("vista.home-session/v1"));
    FFileHelper::SaveStringToFile(Encode(Session),*(BridgeDir/TEXT("session.json")));
    if (!LoadFineContacts()) {UE_LOG(LogTemp,Error,TEXT("HOME_FINE_CONTACT_CONFIG_INVALID"));return;}
    bSceneReady=true;
    UE_LOG(LogTemp,Display,TEXT("HOME_ACTIONS_READY entities=%d bridge=%s revision=%s"),Entities.Num(),*BridgeDir,*Revision);
    PublishState();
}

void AHomeActionsCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    Input->KeyBindings.RemoveAll([](const FInputKeyBinding& K)
    {return K.Chord.Key==EKeys::F || K.Chord.Key==EKeys::C;});
    Input->BindKey(EKeys::F,IE_Pressed,this,&AHomeActionsCharacter::InspectFocus);
    Input->BindKey(EKeys::C,IE_Pressed,this,&AHomeActionsCharacter::ToggleCrouch);
    Input->BindKey(EKeys::B,IE_Pressed,this,&AHomeActionsCharacter::ToggleBackpack);
    Input->BindKey(EKeys::MouseScrollUp,IE_Pressed,this,&AHomeActionsCharacter::NextAction);
    Input->BindKey(EKeys::MouseScrollDown,IE_Pressed,this,&AHomeActionsCharacter::PreviousAction);
    Input->BindKey(EKeys::F2,IE_Pressed,this,&AHomeActionsCharacter::NextEvent);
    Input->BindKey(EKeys::LeftShift,IE_Pressed,this,&AHomeActionsCharacter::JogOn);
    Input->BindKey(EKeys::LeftShift,IE_Released,this,&AHomeActionsCharacter::JogOff);
}

FVector AHomeActionsCharacter::ControlPoint(const FHomeEntity& E) const
{
    return E.Actor.IsValid()?E.Actor->GetActorTransform().TransformPosition(E.ControlLocal):Vector(E.Spec,TEXT("control_cm"));
}

TArray<FString> AHomeActionsCharacter::AvailableActions() const
{
    TArray<FString> Result;
    if (!SeatId.IsEmpty()) return {TEXT("stand_up")};
    const FHomeEntity* E=Resolve(FocusId);
    if (const auto* Held=Resolve(HeldId))
    {
        if (E && E->Id!=HeldId && E->Kind==TEXT("container") && Bool(E->State,TEXT("open")) &&
            E->State->GetArrayField(TEXT("contents")).IsEmpty()) Result.Add(TEXT("storage.insert"));
        if (E && E->Id!=HeldId && E->Spec->HasField(TEXT("capacity_ml")) &&
            Contains(Held->Spec,TEXT("actions"),TEXT("pour")) && Number(Held->State,TEXT("liquid_ml"))>0 &&
            Number(E->State,TEXT("liquid_ml"))<Number(E->Spec,TEXT("capacity_ml"))) Result.Add(TEXT("pour"));
        Result.Add(TEXT("place"));Result.Add(TEXT("drop"));
        if (Contains(Held->Spec,TEXT("actions"),TEXT("equip"))) Result.Add(TEXT("equip"));
        if (Number(Held->State,TEXT("liquid_ml"))>0) Result.Add(TEXT("spill"));
        return Result;
    }
    if (!E) return StandingOn.IsEmpty()?Result:TArray<FString>{TEXT("step_down")};
    const TArray<TSharedPtr<FJsonValue>>* A;
    if (!E->Spec->TryGetArrayField(TEXT("actions"),A)) return Result;
    for (const auto& V:*A)
    {
        const FString S=V->AsString();
        if (S==TEXT("insert") || S==TEXT("inspect") || S==TEXT("carry") || S==TEXT("seated_idle") || S==TEXT("stand_up")) continue;
        if (S==TEXT("pick_up") && (!HeldId.IsEmpty() || !String(E->State,TEXT("container_in")).IsEmpty())) continue;
        if ((S==TEXT("place") || S==TEXT("drop") || S==TEXT("equip") || S==TEXT("pour") || S==TEXT("spill")) && HeldId!=E->Id) continue;
        if ((S==TEXT("articulation.open") && Bool(E->State,TEXT("open"))) || (S==TEXT("close") && !Bool(E->State,TEXT("open")))) continue;
        if ((S==TEXT("turn_on") && Bool(E->State,TEXT("active"))) || (S==TEXT("turn_off") && !Bool(E->State,TEXT("active")))) continue;
        if (S==TEXT("storage.insert") && (HeldId.IsEmpty() || !Bool(E->State,TEXT("open")))) continue;
        if (S==TEXT("storage.remove") && (!HeldId.IsEmpty() || !Bool(E->State,TEXT("open")) || E->State->GetArrayField(TEXT("contents")).Num()==0)) continue;
        if (S==TEXT("load") || S==TEXT("unload")) continue; // UI names the exact storage transaction.
        if ((S==TEXT("step_up") && !StandingOn.IsEmpty()) || (S==TEXT("step_down") && StandingOn!=E->Id)) continue;
        if (S==TEXT("unequip") && String(E->State,TEXT("equipped_by"))!=TEXT("player")) continue;
        if (!HeldId.IsEmpty() && S!=TEXT("storage.insert") && S!=TEXT("place") && S!=TEXT("drop") && S!=TEXT("pour") && S!=TEXT("spill") && S!=TEXT("equip")) continue;
        Result.Add(S);
    }
    if (!HeldId.IsEmpty() && !Result.Contains(TEXT("place"))) Result.Insert(TEXT("place"),0);
    return Result;
}

void AHomeActionsCharacter::UpdateFocus()
{
    FVector Eye;FRotator Rotation;
    const APlayerController* PC=Cast<APlayerController>(Controller);if (!PC) return;
    PC->GetPlayerViewPoint(Eye,Rotation);
    FString Found;float Score=0.f;
    for (const auto& Pair:Entities)
    {
        const auto& E=Pair.Value;if (E.Id==HeldId || !E.Actor.IsValid() || !Bool(E.State,TEXT("visible"),true)) continue;
        FVector Point=ControlPoint(E);
        const FVector Delta=Point-Eye;
        const float Alignment=FVector::DotProduct(Delta.GetSafeNormal(),Rotation.Vector());
        if (Delta.Size()>330.f || Alignment<.94f) continue;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(HomeFocus),true,this);FHitResult Hit;
        if (const auto* Held=Resolve(HeldId)) Params.AddIgnoredActor(Held->Actor.Get());
        if (GetWorld()->LineTraceSingleByChannel(Hit,Eye,Point,ECC_Visibility,Params) && Hit.GetActor()!=E.Actor.Get() &&
            FVector::Distance(Hit.ImpactPoint,Point)>7.f) continue;
        const float Value=Alignment-(Delta.Size()/300.f)*.006f+(E.Kind==TEXT("pickup")?.008f:0.f);
        if (Value>Score) {Score=Value;Found=E.Id;}
    }
    if (Found!=FocusId) {FocusId=Found;SelectedAction=0;}
}

void AHomeActionsCharacter::NextAction() { const auto A=AvailableActions();if (A.Num()) SelectedAction=(SelectedAction+1)%A.Num(); }
void AHomeActionsCharacter::PreviousAction() { const auto A=AvailableActions();if (A.Num()) SelectedAction=(SelectedAction+A.Num()-1)%A.Num(); }
void AHomeActionsCharacter::InspectFocus() { HomeAction(TEXT("inspect"),FocusId,TEXT("")); }
void AHomeActionsCharacter::ToggleCrouch() { HomeAction(TEXT("crouch"),TEXT(""),TEXT("")); }
void AHomeActionsCharacter::ToggleBackpack()
{
    if (const auto* Pack=Resolve(TEXT("backpack")))
        HomeAction(String(Pack->State,TEXT("equipped_by"))==TEXT("player")?TEXT("unequip"):TEXT("equip"),Pack->Id,TEXT(""));
}
void AHomeActionsCharacter::JogOn() { bJog=true; }
void AHomeActionsCharacter::JogOff() { bJog=false; }
void AHomeActionsCharacter::SetView(FVector Position,FRotator Rotation)
{
    if (bSceneReady && (!ActiveId.IsEmpty() || !HeldId.IsEmpty() || !SeatId.IsEmpty() || !StandingOn.IsEmpty()))
    {FeedbackMessage(TEXT("Finish the current interaction before changing rooms"));return;}
    Super::SetView(Position,Rotation);
}
void AHomeActionsCharacter::HomeFocus(const FString& Target)
{
    if (FHomeEntity* E=Resolve(Target))
    {
        FocusId=E->Id;SelectedAction=0;
        FVector Eye;FRotator R;Cast<APlayerController>(Controller)->GetPlayerViewPoint(Eye,R);
        const FVector Point=ControlPoint(*E);
        Controller->SetControlRotation((Point-Eye).Rotation());
    }
}

void AHomeActionsCharacter::EmbodiedInteract()
{
    if (!bSceneReady || !ActiveId.IsEmpty()) return;
    if (FallAlpha>.5f) {HomeAction(TEXT("recover"),TEXT(""),TEXT(""));return;}
    if (!SeatId.IsEmpty()) {HomeAction(TEXT("stand_up"),SeatId,TEXT(""));return;}
    const auto Actions=AvailableActions();
    if (!Actions.Num()) {FeedbackMessage(TEXT("Look at an object within reach"));return;}
    const FString A=Actions[FMath::Clamp(SelectedAction,0,Actions.Num()-1)];
    if (A==TEXT("step_down")) HomeAction(A,StandingOn,TEXT(""));
    else if (A==TEXT("storage.insert")) HomeAction(A,HeldId,FocusId);
    else if (A==TEXT("storage.remove"))
    {
        const auto* E=Resolve(FocusId);const auto& Contents=E->State->GetArrayField(TEXT("contents"));
        HomeAction(A,Contents[0]->AsString(),FocusId);
    }
    else if (A==TEXT("pour")) HomeAction(A,HeldId,FocusId==HeldId?TEXT("coffee_cup"):FocusId);
    else HomeAction(A,A==TEXT("place") || A==TEXT("drop") || A==TEXT("spill")?HeldId:FocusId,TEXT(""));
}
void AHomeActionsCharacter::EmbodiedPlace() { HomeAction(TEXT("place"),HeldId,TEXT("")); }
void AHomeActionsCharacter::EmbodiedDrop()
{
    if (!ActiveId.IsEmpty()) {HomeCancel();return;}
    if (!HeldId.IsEmpty()) HomeAction(TEXT("drop"),HeldId,TEXT(""));
}
void AHomeActionsCharacter::EmbodiedReset()
{ FString Code;ResetScene(Code);FeedbackMessage(Code); }
void AHomeActionsCharacter::HomeObserve(bool Clean) { bCleanObservation=Clean; }
void AHomeActionsCharacter::NextEvent()
{
    if (!Contract) return;
    const auto& Events=Contract->GetArrayField(TEXT("events"));
    EventIndex=(EventIndex+1)%Events.Num();HomeEvent(String(Events[EventIndex]->AsObject(),TEXT("event_id")));
}
void AHomeActionsCharacter::HomeEvent(const FString& Id)
{ FString Code;StartEvent(Id,Code);FeedbackMessage(Code);PublishState(); }

void AHomeActionsCharacter::Tick(float Dt)
{
    Super::Tick(Dt);if (!bSceneReady) return;
    SceneClock+=Dt;BridgeClock+=Dt;
    const bool ContactReach=!ActiveId.IsEmpty() && !TargetId.IsEmpty() &&
        ActionId!=TEXT("step_up") && ActionId!=TEXT("step_down") && ActionId!=TEXT("equip") && ActionId!=TEXT("unequip") && ActionId!=TEXT("inspect") && ActionId!=TEXT("look_at");
    SceneReachHipAdvance=FMath::FInterpTo(SceneReachHipAdvance,ContactReach?9.f:0.f,Dt,6.f);
    UpdateFocus();UpdatePhysicalConsequences(Dt);UpdatePresentation(Dt);UpdateEvent(Dt);
    GetCharacterMovement()->bOrientRotationToMovement=bThirdPerson && Phase==EEmbodiedPhase::Idle && !bSceneActionBusy && SeatId.IsEmpty();
    if (!bSceneActionBusy && SeatId.IsEmpty() && (Phase==EEmbodiedPhase::Idle || Phase==EEmbodiedPhase::Held))
        GetCharacterMovement()->MaxWalkSpeed=HeldId.IsEmpty()?(CrouchAlpha>.1f?62.f:(bJog?210.f:125.f)):85.f;
    if (FallAlpha>.5f || (bSceneCarryLift && Phase==EEmbodiedPhase::Held)) GetCharacterMovement()->MaxWalkSpeed=0.f;
    if (bSceneActionBusy && (ActionId==TEXT("walk") || ActionId==TEXT("jog") || ActionId==TEXT("sprint")))
        GetCharacterMovement()->MaxWalkSpeed=ActionId==TEXT("sprint")?300.f:(ActionId==TEXT("jog")?210.f:125.f);
    if (!StandingOn.IsEmpty() || (bSceneActionBusy && (ActionId==TEXT("step_up") || ActionId==TEXT("step_down")))) GetCharacterMovement()->MaxWalkSpeed=0.f;
    if (BridgeClock>=.2f) {BridgeClock=0;PollBridge();PublishState();}
}

void AHomeActionsCharacter::OnPoseFinalized()
{
    if (bSceneReady)
    {
        MeasureFineContacts();
        RightContactError=FVector::Distance(GetMesh()->GetSocketLocation(TEXT("hand_r")),LastHandGoal.GetLocation());
        LeftContactError=LeftReachAlpha>.95f?FVector::Distance(GetMesh()->GetSocketLocation(TEXT("hand_l")),LeftHandGoal.GetLocation()):0.f;
        if (!ActiveId.IsEmpty() && ReachAlpha>.95f && ActionStage==1)
            ContactMaximum=FMath::Max(ContactMaximum,FMath::Max(RightContactError,LeftContactError));
    }
    Super::OnPoseFinalized();
}

FString AHomeActionsCharacter::GetInteractionHint() const
{
    if (!bSceneReady) return TEXT("Home interaction assets unavailable");
    if (Clock<FeedbackUntil) return FeedbackLabel(Feedback);
    if (!ActiveId.IsEmpty()) return FString::Printf(TEXT("%s  |  G: cancel"),*ActionLabel(ActionId));
    const FHomeEntity* E=Resolve(FocusId);const auto A=AvailableActions();
    if (!SeatId.IsEmpty()) return TEXT("E: stand up   |   Tab: change view");
    if (A.Num()) return FString::Printf(TEXT("%s   |   E: %s   |   wheel: action   F: inspect"),
        E?*E->Display:TEXT("Carried object"),*ActionLabel(A[FMath::Clamp(SelectedAction,0,A.Num()-1)]));
    return TEXT("Look at an object   |   WASD: walk   Tab: first / third person");
}
FString AHomeActionsCharacter::GetEventHint() const
{
    if (EventId.IsEmpty()) return TEXT("Free exploration   |   F2: next VISTA scenario   R: reset");
    FString Goal;
    for (const auto& V:Contract->GetArrayField(TEXT("events")))
        if (String(V->AsObject(),TEXT("event_id"))==EventId)
            Goal=String(V->AsObject()->GetArrayField(TEXT("public_goals"))[0]->AsObject(),TEXT("description"));
    return FString::Printf(TEXT("%s  [%s]  %s"),*EventId,*EventStatus,*Goal);
}
void AHomeActionsCharacter::ReviewSnapshot() { Super::ReviewSnapshot();HomeState(); }
void AHomeActionsCharacter::HomeState()
{ if (bSceneReady) UE_LOG(LogTemp,Display,TEXT("HOME_STATE %s"),*Encode(MakeState())); }

void AHomeActionsHUD::DrawHUD()
{
    Super::DrawHUD();if (!Canvas) return;
    const auto* P=Cast<AHomeActionsCharacter>(GetOwningPawn());if (!P || P->IsCleanObservation()) return;
    DrawRect(FLinearColor(.025,.035,.031,.8),22,20,1250,95);
    DrawText(TEXT("VISTA HOME  /  INTERACTIONS"),FLinearColor(.95,.95,.88),38,29,nullptr,1.3f);
    DrawText(TEXT("1 Entry   2 Living   3 Kitchen   4 Bedroom   5 Office   6 Bath   |   Tab: view   C: crouch   Shift: jog   B: backpack"),FLinearColor(.82,.85,.79),38,59,nullptr,1.f);
    DrawText(P->GetEventHint(),FLinearColor(.87,.88,.79),38,84,nullptr,.9f);
    DrawRect(FLinearColor(.02,.025,.02,.78),22,Canvas->ClipY-78,1120,50);
    DrawText(P->GetInteractionHint(),FLinearColor(.97,.95,.84),38,Canvas->ClipY-62,nullptr,1.15f);
    DrawRect(FLinearColor(1,1,1,.65),Canvas->ClipX*.5f-2,Canvas->ClipY*.5f-2,4,4);
}
AHomeActionsGameMode::AHomeActionsGameMode()
{ DefaultPawnClass=AHomeActionsCharacter::StaticClass();HUDClass=AHomeActionsHUD::StaticClass(); }
