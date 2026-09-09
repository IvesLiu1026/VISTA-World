#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "Algo/Sort.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "Misc/Paths.h"

using namespace HomeJson;

namespace
{
bool ReadPoint(const TSharedPtr<FJsonValue>& Value,FVector& Point)
{
    if (!Value || Value->Type!=EJson::Array || Value->AsArray().Num()!=3) return false;
    const auto& A=Value->AsArray();
    for (int32 I=0;I<3;++I)
        if (!A[I]->TryGetNumber(Point[I]) || !FMath::IsFinite(Point[I]) || FMath::Abs(Point[I])>5000.) return false;
    return true;
}

int32 BuildNode(FHomeFineSurface& Surface,int32 Start,int32 Count)
{
    FHomeContactNode Node;Node.Bounds.Init();Node.Start=Start;Node.Count=Count;
    for (int32 I=Start;I<Start+Count;++I) Node.Bounds+=Surface.Triangles[I].Bounds;
    const int32 Index=Surface.Nodes.Add(Node);
    if (Count>12)
    {
        const FVector Size=Node.Bounds.GetSize();int32 Axis=Size.Y>Size.X?1:0;if (Size.Z>Size[Axis]) Axis=2;
        Algo::Sort(MakeArrayView(Surface.Triangles.GetData()+Start,Count),[Axis](const FHomeContactTriangle& A,const FHomeContactTriangle& B)
        {return A.Bounds.GetCenter()[Axis]<B.Bounds.GetCenter()[Axis];});
        const int32 Half=Count/2;
        const int32 Left=BuildNode(Surface,Start,Half),Right=BuildNode(Surface,Start+Half,Count-Half);
        Surface.Nodes[Index].Left=Left;Surface.Nodes[Index].Right=Right;Surface.Nodes[Index].Count=0;
    }
    return Index;
}

void RotateFingerBranch(TArray<FTransform>& Global,const TArray<int32>& Parents,int32 Root,const FQuat& Rotation)
{
    const FVector Pivot=Global[Root].GetLocation();
    const FQuat Delta=(Rotation*Global[Root].GetRotation().Inverse()).GetNormalized();
    for (int32 I=Root;I<Global.Num();++I)
    {
        int32 P=I;while (P>Root) P=Parents[P];if (P!=Root) continue;
        Global[I].SetLocation(Pivot+Delta.RotateVector(Global[I].GetLocation()-Pivot));
        Global[I].SetRotation((Delta*Global[I].GetRotation()).GetNormalized());
    }
}
}

bool AHomeActionsCharacter::LoadFineContacts()
{
    const FString Path=FPaths::ProjectConfigDir()/TEXT("VistaFineContacts.json");
    if (!IFileManager::Get().FileExists(*Path)) return true;
    if (IFileManager::Get().FileSize(*Path)>64*1024*1024) return false;
    FString Text;if (!FFileHelper::LoadFileToString(Text,*Path)) return false;
    const auto Data=Decode(Text);
    if (!Data || String(Data,TEXT("schema"))!=TEXT("vista.home-fine-contact/v1") ||
        String(Data,TEXT("audience"))!=TEXT("privileged_runtime_authoring_only")) return false;
    if (!Bool(Data,TEXT("enabled"))) return true;
    const TSharedPtr<FJsonObject>* Tips;const TSharedPtr<FJsonObject>* Frames;
    const TArray<TSharedPtr<FJsonValue>>* Surfaces;
    if (!Data->TryGetObjectField(TEXT("tip_landmarks"),Tips) || (*Tips)->Values.Num()!=10 ||
        !Data->TryGetObjectField(TEXT("joint_frames"),Frames) || (*Frames)->Values.Num()!=30 ||
        !Data->TryGetArrayField(TEXT("surfaces"),Surfaces) || Surfaces->IsEmpty() || Surfaces->Num()>64) return false;
    for (const TCHAR* Side:{TEXT("l"),TEXT("r")})
        for (const TCHAR* Finger:{TEXT("index"),TEXT("middle"),TEXT("ring"),TEXT("pinky"),TEXT("thumb")})
        {
            if (!(*Tips)->HasField(FString::Printf(TEXT("%s_03_%s"),Finger,Side))) return false;
            for (int32 Joint=1;Joint<=3;++Joint)
                if (!(*Frames)->HasField(FString::Printf(TEXT("%s_%02d_%s"),Finger,Joint,Side))) return false;
        }
    for (const auto& Pair:(*Frames)->Values)
    {
        const FName Bone(*Pair.Key);const auto Item=Pair.Value->AsObject();
        const TArray<TSharedPtr<FJsonValue>>* Rotation;
        if (!BoneIndex.Contains(Bone) || !Item || !Item->HasField(TEXT("source_component_cm")) ||
            !Item->TryGetArrayField(TEXT("source_component_rotation_xyzw"),Rotation) || Rotation->Num()!=4) return false;
        double Components[4];
        for (int32 I=0;I<4;++I) if (!(*Rotation)[I]->TryGetNumber(Components[I]) || !FMath::IsFinite(Components[I])) return false;
        FQuat Source(Components[0],Components[1],Components[2],Components[3]);
        if (FMath::Abs(Source.SizeSquared()-1.)>.001) return false;
        Source.Normalize();FVector Position;
        if (!ReadPoint(Item->Values[TEXT("source_component_cm")],Position)) return false;
        const auto& Target=ReferenceGlobal[BoneIndex.FindChecked(Bone)];
        if (FVector::Distance(Position,Target.GetLocation())>.15f) return false;
        FineFlexionAxes.Add(Bone,Target.InverseTransformVectorNoScale(Source.RotateVector(FVector::ForwardVector)).GetSafeNormal());
        FineSpreadAxes.Add(Bone,Target.InverseTransformVectorNoScale(Source.RotateVector(FVector::UpVector)).GetSafeNormal());
    }
    for (const auto& Pair:(*Tips)->Values)
    {
        const FName Bone(*Pair.Key);const auto Item=Pair.Value->AsObject();
        if (!BoneIndex.Contains(Bone) || !Item || !Item->HasField(TEXT("source_component_cm"))) return false;
        FVector Point;if (!ReadPoint(Item->Values[TEXT("source_component_cm")],Point)) return false;
        // Interchange changes bone rolls. A Blender bone-local vector cannot
        // be used directly with imported UE sockets; retarget the skin patch
        // through the two component-space rest frames, like the pose library.
        const FVector Offset=ReferenceGlobal[BoneIndex.FindChecked(Bone)].InverseTransformPosition(Point);
        if (Offset.Size()>15.f) return false;
        FineTipOffsets.Add(Bone,Offset);
    }
    for (const auto& Value:*Surfaces)
    {
        const auto Item=Value->AsObject();if (!Item) return false;
        const FString Id=String(Item,TEXT("entity_id"));
        if (!Resolve(Id) || FineSurfaces.Contains(Id)) return false;
        const TArray<TSharedPtr<FJsonValue>>* Triangles;const TArray<TSharedPtr<FJsonValue>>* Fingers;
        if (!Item->TryGetArrayField(TEXT("triangles_cm"),Triangles) || Triangles->Num()<1 || Triangles->Num()>100000 ||
            !Item->TryGetArrayField(TEXT("required_fingers"),Fingers) || Fingers->Num()<1 || Fingers->Num()>5) return false;
        FHomeFineSurface Surface;Surface.Mode=String(Item,TEXT("mode"));
        if (Surface.Mode!=TEXT("point") && Surface.Mode!=TEXT("pinch") && Surface.Mode!=TEXT("wrap")) return false;
        Surface.bHorizontalPinch=Bool(Item,TEXT("horizontal_pinch"));
        Surface.bUseWideGrip=Bool(Item,TEXT("wide_grip_pose"));
        Surface.PinchRollDegrees=Number(Item,TEXT("pinch_roll_deg"));
        if (!FMath::IsFinite(Surface.PinchRollDegrees) || FMath::Abs(Surface.PinchRollDegrees)>45.f) return false;
        Surface.bSupportBothHands=Bool(Item,TEXT("both_hands_when_reaching"));
        if (Surface.bHorizontalPinch && (!Item->HasField(TEXT("grip_center_cm")) ||
            !ReadPoint(Item->Values[TEXT("grip_center_cm")],Surface.GripCenter))) return false;
        if (Item->HasField(TEXT("control_local_cm")))
        {
            FVector Control;if (!ReadPoint(Item->Values[TEXT("control_local_cm")],Control)) return false;
            Resolve(Id)->ControlLocal=Control;
        }
        if (Item->HasField(TEXT("grip_points_cm")))
        {
            const TArray<TSharedPtr<FJsonValue>>* Points;
            if (!Bool(Resolve(Id)->Spec,TEXT("two_hands")) || !Item->TryGetArrayField(TEXT("grip_points_cm"),Points) || Points->Num()!=2) return false;
            for (const auto& Row:*Points) {FVector Point;if (!ReadPoint(Row,Point)) return false;Surface.GripPoints.Add(Point);}
        }
        Surface.MaximumError=Number(Item,TEXT("maximum_tip_error_cm"));Surface.Clearance=Number(Item,TEXT("skin_clearance_cm"));
        Surface.MaximumJointAngle=Number(Item,TEXT("maximum_joint_adjustment_deg"));
        if (Surface.MaximumError<.1f || Surface.MaximumError>1.f || Surface.Clearance<0 || Surface.Clearance>.3f ||
            Surface.MaximumJointAngle<1 || Surface.MaximumJointAngle>60) return false;
        for (const auto& Finger:*Fingers)
        {
            const FString Name=Finger->AsString();
            if (Surface.Fingers.Contains(Name) || !FineTipOffsets.Contains(FName(*(Name+TEXT("_03_r"))))) return false;
            Surface.Fingers.Add(Name);
        }
        for (const auto& Row:*Triangles)
        {
            if (Row->Type!=EJson::Array || Row->AsArray().Num()!=3) return false;
            const auto& P=Row->AsArray();FHomeContactTriangle Triangle;
            if (!ReadPoint(P[0],Triangle.A) || !ReadPoint(P[1],Triangle.B) || !ReadPoint(P[2],Triangle.C)) return false;
            Triangle.Normal=FVector::CrossProduct(Triangle.B-Triangle.A,Triangle.C-Triangle.A).GetSafeNormal();
            if (Triangle.Normal.IsNearlyZero()) return false;
            Triangle.Bounds.Init();Triangle.Bounds+=Triangle.A;Triangle.Bounds+=Triangle.B;Triangle.Bounds+=Triangle.C;
            Surface.Triangles.Add(Triangle);
        }
        BuildNode(Surface,0,Surface.Triangles.Num());FineSurfaces.Add(Id,MoveTemp(Surface));
    }
    bFineContacts=true;
    UE_LOG(LogTemp,Display,TEXT("HOME_FINE_CONTACT_READY surfaces=%d landmarks=%d"),FineSurfaces.Num(),FineTipOffsets.Num());
    return true;
}

bool AHomeActionsCharacter::ClosestFineSurface(const FHomeFineSurface& Surface,const FVector& Point,FVector& Closest,FVector& Normal) const
{
    if (Surface.Nodes.IsEmpty()) return false;
    double Best=MAX_dbl;TArray<int32,TInlineAllocator<64>> Pending;Pending.Add(0);
    while (!Pending.IsEmpty())
    {
        const auto& Node=Surface.Nodes[Pending.Pop(EAllowShrinking::No)];
        if (Node.Bounds.ComputeSquaredDistanceToPoint(Point)>Best) continue;
        if (Node.Count)
        {
            for (int32 I=Node.Start;I<Node.Start+Node.Count;++I)
            {
                const auto& Triangle=Surface.Triangles[I];
                const FVector Q=FMath::ClosestPointOnTriangleToPoint(Point,Triangle.A,Triangle.B,Triangle.C);
                const double Error=(Q-Point).SizeSquared();
                if (Error<Best) {Best=Error;Closest=Q;Normal=Triangle.Normal;}
            }
        }
        else {Pending.Add(Node.Left);Pending.Add(Node.Right);}
    }
    return Best<MAX_dbl;
}

const FHomeEntity* AHomeActionsCharacter::FineContactEntity() const
{
    if (!bFineContacts || ReachAlpha<.85f || FallAlpha>.1f) return nullptr;
    // Looking at a receiver while carrying must keep the grip on the held prop.
    const auto* Entity=Resolve(HeldId.IsEmpty()?TargetId:HeldId);
    if (!Entity || !Entity->Mesh.IsValid() || !FineSurfaces.Contains(Entity->Id)) return nullptr;
    if (HeldId.IsEmpty() && (ActionId==TEXT("inspect") || ActionId==TEXT("look_at") || ActionId==TEXT("sit_down") || ActionId==TEXT("stand_up"))) return nullptr;
    return Entity;
}

void AHomeActionsCharacter::AdjustScenePoseGoals()
{
    const auto* Entity=FineContactEntity();
    if (!Entity || FineWristEntity!=Entity->Id)
    {
        FineWristCorrection[0]=FineWristCorrection[1]=FVector::ZeroVector;
        FineWristEntity=Entity?Entity->Id:FString();
    }
    if (!Entity) return;
    // Change the goal before the complete arm IK. Translating only hand bones
    // would disconnect the wrist from the forearm and conceal reach failures.
    LastHandGoal=AdjustedSceneHandGoal(LastHandGoal);
    if (FineLeftRequired(*Entity)) LeftHandGoal=AdjustedSceneHandGoal(LeftHandGoal,true);
}

FTransform AHomeActionsCharacter::AdjustedSceneHandGoal(FTransform Goal,bool bLeft) const
{
    const auto* Entity=FineContactEntity();
    if (Entity && FineWristEntity==Entity->Id)
        Goal.AddToTranslation(Entity->Mesh->GetComponentTransform().TransformVectorNoScale(FineWristCorrection[bLeft?0:1])*Ease((ReachAlpha-.85f)/.15f));
    return Goal;
}

bool AHomeActionsCharacter::FineLeftRequired(const FHomeEntity& Entity) const
{
    return Bool(Entity.Spec,TEXT("two_hands")) ||
        (FineSurfaces.FindChecked(Entity.Id).bSupportBothHands && LeftReachAlpha>.85f);
}

FTransform AHomeActionsCharacter::FinePinchWrist(const FHomeEntity& Entity) const
{
    const auto& Surface=FineSurfaces.FindChecked(Entity.Id);
    TArray<FTransform> Global;Global.SetNum(Parents.Num());
    for (int32 I=0;I<Global.Num();++I) Global[I]=Parents[I]>=0?Poses->Grip[I]*Global[Parents[I]]:Poses->Grip[I];
    const auto& Hand=Global[BoneIndex.FindChecked(TEXT("hand_r"))];
    const auto Tip=[&](FName Name) {return Hand.InverseTransformPosition(Global[BoneIndex.FindChecked(Name)].TransformPosition(FineTipOffsets.FindChecked(Name)));};
    const FVector Index=Tip(TEXT("index_03_r")),Thumb=Tip(TEXT("thumb_03_r")),Middle=(Index+Thumb)*.5f;
    const FVector Across=(Thumb-Index).GetSafeNormal();
    const FVector Approach=(Middle-Across*FVector::DotProduct(Middle,Across)).GetSafeNormal();
    FVector Direction=Entity.Actor->GetActorForwardVector();
    if (FVector::DotProduct(Direction,GetActorRightVector())<0) Direction=-Direction;
    const FQuat Source=FRotationMatrix::MakeFromXY(Across,Approach).ToQuat();
    const FQuat Destination=FRotationMatrix::MakeFromXY(Direction,FVector::DownVector).ToQuat();
    const FQuat Rotation=(FQuat(Direction,FMath::DegreesToRadians(Surface.PinchRollDegrees))*Destination*Source.Inverse()).GetNormalized();
    // Opposed side contacts keep both pads above the supporting surface when
    // picking a flat phone or ring. A vertical pinch would put a finger below it.
    return FTransform(Rotation,Entity.Actor->GetActorTransform().TransformPosition(Surface.GripCenter)-Rotation.RotateVector(Middle));
}

void AHomeActionsCharacter::RefineSceneBodyPose(TArray<FTransform>& Local)
{
    // BuildBodyPose invokes this on the animation proxy's game-thread PreUpdate.
    // The worker receives only the resulting local transforms.
    const auto* Entity=FineContactEntity();if (!Entity) return;
    const auto& Surface=FineSurfaces.FindChecked(Entity->Id);
    const FTransform World=GetMesh()->GetComponentTransform();
    const FTransform Object=Entity->Mesh->GetComponentTransform();
    TArray<FTransform> Global;Global.SetNum(Local.Num());
    if (Surface.Mode==TEXT("point"))
        for (int32 I=0;I<Local.Num();++I)
        {
            const FString Name=Poses->BoneNames[I].ToString();
            if (Name.EndsWith(TEXT("_r")) && !Name.StartsWith(TEXT("index_")) &&
                (Name.StartsWith(TEXT("middle_")) || Name.StartsWith(TEXT("ring_")) || Name.StartsWith(TEXT("pinky_")) || Name.StartsWith(TEXT("thumb_"))))
                Local[I].Blend(Poses->OpenHand[I],Poses->Grip[I],.65f*ReachAlpha);
        }
    for (int32 I=0;I<Local.Num();++I) Global[I]=Parents[I]>=0?Local[I]*Global[Parents[I]]:Local[I];
    const auto OriginalLocal=Local;
    for (int32 Side=0;Side<2;++Side)
    {
        const bool Left=Side==0;
        if (Left && (LeftReachAlpha<.85f || !FineLeftRequired(*Entity))) continue;
        const float Alpha=Surface.Mode==TEXT("point")?ReachAlpha:(Left?LeftFingerAlpha:FingerAlpha);
        if (Alpha<.2f) continue;
        for (const FString& Finger:Surface.Fingers)
        {
            const FString Suffix=Left?TEXT("_l"):TEXT("_r");
            const FName TipName(*(Finger+TEXT("_03")+Suffix));
            const int32 End=BoneIndex.FindChecked(TipName);
            const FVector Offset=FineTipOffsets.FindChecked(TipName);
            const FVector Start=Object.InverseTransformPosition(World.TransformPosition(Global[End].TransformPosition(Offset)));
            FVector Point,Normal;
            if (!ClosestFineSurface(Surface,Start,Point,Normal) || FVector::Distance(Start,Point)>10.f) continue;
            for (int32 Iteration=0;Iteration<16;++Iteration)
            {
                // Project again after each pass. Curved and thin surfaces need
                // a reachable contact point, not the initial Euclidean projection.
                const FVector Current=Object.InverseTransformPosition(World.TransformPosition(Global[End].TransformPosition(Offset)));
                if (!ClosestFineSurface(Surface,Current,Point,Normal)) break;
                const FVector Goal=World.InverseTransformPosition(Object.TransformPosition(Point+Normal*Surface.Clearance));
                for (int32 Joint=3;Joint>=1;--Joint)
                {
                    const FName JointName(*FString::Printf(TEXT("%s_%02d%s"),*Finger,Joint,*Suffix));
                    const int32 Index=BoneIndex.FindChecked(JointName);
                    const FVector Pivot=Global[Index].GetLocation();
                    const FVector From=Global[End].TransformPosition(Offset)-Pivot,To=Goal-Pivot;
                    FQuat Delta;
                    // The metacarpophalangeal joint also abducts. Restricting
                    // all three joints to flexion left narrow handles outside
                    // the finger's plane even when the wrist reached correctly.
                    if (Finger==TEXT("thumb") || Joint==1)
                    {
                        Delta=FQuat::FindBetweenVectors(From,To);
                        const double Angle=Delta.GetAngle();
                        if (Angle>.17) Delta=FQuat::Slerp(FQuat::Identity,Delta,.17/Angle);
                    }
                    else
                    {
                        const FVector Axis=Global[Index].GetRotation().RotateVector(FineFlexionAxes.FindChecked(JointName));
                        const FVector A=From-Axis*FVector::DotProduct(From,Axis),B=To-Axis*FVector::DotProduct(To,Axis);
                        const double Angle=FMath::Atan2(FVector::DotProduct(Axis,FVector::CrossProduct(A,B)),FVector::DotProduct(A,B));
                        Delta=FQuat(Axis,FMath::Clamp(Angle,-.17,.17));
                    }
                    const FQuat Parent=Global[Parents[Index]].GetRotation();
                    FQuat Proposed=(Parent.Inverse()*Delta*Global[Index].GetRotation()).GetNormalized();
                    const FQuat Base=OriginalLocal[Index].GetRotation();
                    if (Joint==1 && Finger!=TEXT("thumb"))
                    {
                        FVector Axis;double Angle;(Base.Inverse()*Proposed).ToAxisAndAngle(Axis,Angle);
                        if (Angle>PI) Angle-=2*PI;
                        const FVector Flex=FineFlexionAxes.FindChecked(JointName),Spread=FineSpreadAxes.FindChecked(JointName);
                        const double FlexAngle=FVector::DotProduct(Axis*Angle,Flex);
                        const double SpreadAngle=FMath::Clamp(FVector::DotProduct(Axis*Angle,Spread),-PI/10.,PI/10.);
                        Proposed=Base*FQuat(Flex,FlexAngle)*FQuat(Spread,SpreadAngle);
                    }
                    const double Difference=Base.AngularDistance(Proposed);
                    const double Limit=FMath::DegreesToRadians(Surface.MaximumJointAngle)*Ease((Alpha-.2f)/.8f);
                    if (Difference>Limit && Difference>1e-6) Proposed=FQuat::Slerp(Base,Proposed,Limit/Difference);
                    RotateFingerBranch(Global,Parents,Index,(Parent*Proposed).GetNormalized());
                }
            }
        }
    }
    for (int32 I=0;I<Local.Num();++I)
    {Local[I]=Parents[I]>=0?Global[I].GetRelativeTransform(Global[Parents[I]]):Global[I];Local[I].NormalizeRotation();}
}

void AHomeActionsCharacter::MeasureFineContacts()
{
    FineContactSnapshot=MakeShared<FJsonObject>();
    FineContactSnapshot->SetBoolField(TEXT("enabled"),bFineContacts);
    FineContactSnapshot->SetBoolField(TEXT("active"),false);
    const auto* Entity=FineContactEntity();if (!Entity) return;
    const auto& Surface=FineSurfaces.FindChecked(Entity->Id);
    const bool Mature=Surface.Mode==TEXT("point")?ReachAlpha>.98f:FingerAlpha>.98f;
    FineContactSnapshot->SetBoolField(TEXT("active"),Mature);
    FineContactSnapshot->SetStringField(TEXT("entity_id"),Entity->Id);
    FineContactSnapshot->SetStringField(TEXT("measurement"),TEXT("post_animation_fingertip_skin_patch_to_source_mesh"));
    FineContactSnapshot->SetNumberField(TEXT("maximum_allowed_error_cm"),Surface.MaximumError);
    const FTransform Object=Entity->Mesh->GetComponentTransform();
    double Maximum=0.;bool Ready=Mature;TArray<TSharedPtr<FJsonValue>> Contacts;
    for (int32 Side=0;Side<2;++Side)
    {
        const bool Left=Side==0;if (Left && !FineLeftRequired(*Entity)) continue;
        if (Left && LeftReachAlpha<.98f) Ready=false;
        double Worst=0.;FVector Correction=FVector::ZeroVector;
        for (const FString& Finger:Surface.Fingers)
        {
            const FName Tip(*(Finger+TEXT("_03")+(Left?TEXT("_l"):TEXT("_r"))));
            const FVector WorldPoint=GetMesh()->GetSocketTransform(Tip).TransformPosition(FineTipOffsets.FindChecked(Tip));
            const FVector LocalPoint=Object.InverseTransformPosition(WorldPoint);
            FVector Point,Normal;if (!ClosestFineSurface(Surface,LocalPoint,Point,Normal)) {Ready=false;continue;}
            const double Distance=FVector::Distance(WorldPoint,Object.TransformPosition(Point));Maximum=FMath::Max(Maximum,Distance);
            const double Signed=FVector::DotProduct(LocalPoint-Point,Normal);
            Ready=Ready && Distance<=Surface.MaximumError && Signed>=-.2;
            if ((Distance>Surface.MaximumError || Signed<-.2) && Distance>Worst)
            {Worst=Distance;Correction=Point+Normal*Surface.Clearance-LocalPoint;}
            auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("bone"),Tip.ToString());
            Row->SetNumberField(TEXT("distance_cm"),Distance);Row->SetNumberField(TEXT("signed_distance_cm"),Signed);
            Row->SetArrayField(TEXT("tip_world_cm"),Values(WorldPoint));
            Row->SetArrayField(TEXT("surface_world_cm"),Values(Object.TransformPosition(Point)));
            Contacts.Add(MakeShared<FJsonValueObject>(Row));
        }
        if (Mature && (!Left || LeftFingerAlpha>.98f) && Worst>0.)
        {
            const FVector Previous=FineWristCorrection[Side];
            const FVector Proposed=(Previous+Correction.GetClampedToMaxSize(FMath::Min(.15f,GetWorld()->GetDeltaSeconds()*3.f))).GetClampedToMaxSize(2.f);
            const FVector Start=GetMesh()->GetSocketLocation(Left?TEXT("hand_l"):TEXT("hand_r"));
            const FVector End=Start+Object.TransformVectorNoScale(Proposed-Previous);
            FHitResult Hit;FCollisionQueryParams Query(SCENE_QUERY_STAT(HomeFineWristCorrection),true,this);
            Query.AddIgnoredActor(Entity->Actor.Get());
            if (!GetWorld()->SweepSingleByChannel(Hit,Start,End,FQuat::Identity,ECC_Visibility,FCollisionShape::MakeSphere(3.f),Query))
                FineWristCorrection[Side]=Proposed;
        }
    }
    FineContactSnapshot->SetArrayField(TEXT("contacts"),Contacts);
    FineContactSnapshot->SetNumberField(TEXT("maximum_error_cm"),Maximum);
    FineContactSnapshot->SetBoolField(TEXT("ready"),Ready);
    FineContactSnapshot->SetArrayField(TEXT("left_wrist_adjustment_cm"),Values(FineWristCorrection[0]));
    FineContactSnapshot->SetArrayField(TEXT("right_wrist_adjustment_cm"),Values(FineWristCorrection[1]));
}

bool AHomeActionsCharacter::IsSceneContactReady(FString& Reason) const
{
    const auto* Entity=FineContactEntity();if (!Entity) return true;
    const bool Ready=FineContactSnapshot && Bool(FineContactSnapshot,TEXT("active")) &&
        String(FineContactSnapshot,TEXT("entity_id"))==Entity->Id && Bool(FineContactSnapshot,TEXT("ready"));
    if (!Ready) Reason=TEXT("FINGERTIP_CONTACT_INCOMPLETE");
    return Ready;
}
