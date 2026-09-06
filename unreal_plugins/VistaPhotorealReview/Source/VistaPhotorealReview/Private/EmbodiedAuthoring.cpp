#include "EmbodiedReview.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"

bool UEmbodiedAuthoringLibrary::ConfigureCupMesh(UStaticMesh* Mesh)
{
    if (!Mesh || !Mesh->GetBodySetup()) return false;
    UBodySetup* Body=Mesh->GetBodySetup();
    Body->AggGeom.EmptyElements();
    Body->CollisionTraceFlag=CTF_UseSimpleAndComplex;
    // Convex wall wedges preserve the cavity. A single hull would close the
    // cup and handle holes, unlike the visible manufactured geometry.
    constexpr int32 Count=16;
    for (int32 I=0;I<Count;++I)
    {
        FKConvexElem Wall;
        for (int32 Height=0;Height<2;++Height)
            for (int32 Side=0;Side<2;++Side)
                for (int32 Inside=0;Inside<2;++Inside)
                {
                    const float A=(I+Side)*2.f*PI/Count;
                    const float R=Height?(Inside?3.85f:4.3f):(Inside?3.2f:3.75f);
                    Wall.VertexData.Add(FVector(R*FMath::Cos(A),R*FMath::Sin(A),Height?9.6f:.6f));
                }
        Wall.UpdateElemBox();Body->AggGeom.ConvexElems.Add(Wall);
    }
    FKConvexElem Base;
    for (int32 Height=0;Height<2;++Height)
        for (int32 I=0;I<Count;++I)
            Base.VertexData.Add(FVector(3.45f*FMath::Cos(I*2.f*PI/Count),3.45f*FMath::Sin(I*2.f*PI/Count),Height?.8f:.0f));
    Base.UpdateElemBox();Body->AggGeom.ConvexElems.Add(Base);
    const FVector Points[]={FVector(4,0,7.8),FVector(6.1,0,8.1),FVector(7.5,0,6),FVector(7.2,0,3.4),FVector(5.7,0,2.1),FVector(3.8,0,2.7)};
    for (int32 I=0;I<5;++I)
    {
        FKSphylElem Segment;
        Segment.Center=(Points[I]+Points[I+1])*.5f;
        Segment.Radius=.64f;Segment.Length=FVector::Distance(Points[I],Points[I+1]);
        Segment.Rotation=FQuat::FindBetweenNormals(FVector::UpVector,(Points[I+1]-Points[I]).GetSafeNormal()).Rotator();
        Body->AggGeom.SphylElems.Add(Segment);
    }
    Body->InvalidatePhysicsData();Body->CreatePhysicsMeshes();
    Mesh->MarkPackageDirty();
    UE_LOG(LogTemp,Display,TEXT("EMBODIED_CUP_COLLISION convex=%d capsules=%d"),Body->AggGeom.ConvexElems.Num(),Body->AggGeom.SphylElems.Num());
    return Body->AggGeom.ConvexElems.Num()==17;
}

bool UEmbodiedAuthoringLibrary::PreparePoseLibrary(USkeletalMesh* Mesh,UEmbodiedPoseLibrary* Library)
{
    if (!Mesh || !Library) return false;
    const FReferenceSkeleton& Ref=Mesh->GetRefSkeleton();
    const int32 N=Ref.GetNum();
    if (N!=Library->BoneNames.Num() || N!=Library->Rest.Num()) return false;
    TArray<FTransform> SourceGlobal,TargetGlobal;SourceGlobal.SetNum(N);TargetGlobal.SetNum(N);
    float MaxPosition=0.f,MaxRotation=0.f;
    for (int32 I=0;I<N;++I)
    {
        if (Ref.GetBoneName(I)!=Library->BoneNames[I])
        { UE_LOG(LogTemp,Error,TEXT("EMBODIED_AUTHOR_BONE_ORDER index=%d ue=%s source=%s"),I,*Ref.GetBoneName(I).ToString(),*Library->BoneNames[I].ToString());return false; }
        const int32 Parent=Ref.GetParentIndex(I);
        SourceGlobal[I]=Parent>=0?Library->Rest[I]*SourceGlobal[Parent]:Library->Rest[I];
        TargetGlobal[I]=Parent>=0?Ref.GetRefBonePose()[I]*TargetGlobal[Parent]:Ref.GetRefBonePose()[I];
        MaxPosition=FMath::Max(MaxPosition,float(FVector::Distance(SourceGlobal[I].GetLocation(),TargetGlobal[I].GetLocation())));
        MaxRotation=FMath::Max(MaxRotation,float(FMath::RadiansToDegrees(SourceGlobal[I].GetRotation().AngularDistance(TargetGlobal[I].GetRotation()))));
        if (I==0 || I==8 || I==27 || I==48)
            UE_LOG(LogTemp,Display,TEXT("EMBODIED_REF bone=%s source=%s ue=%s"),*Ref.GetBoneName(I).ToString(),*SourceGlobal[I].ToString(),*TargetGlobal[I].ToString());
    }
    UE_LOG(LogTemp,Display,TEXT("EMBODIED_REF_DIFFERENCE position_cm=%.6f angle_deg=%.6f"),MaxPosition,MaxRotation);
    if (MaxPosition>.15f) return false;
    // Preserve the actual imported rest axes. Transfer authored component-space
    // rotations, then rebuild locals instead of assuming identical bone rolls.
    for (TArray<FTransform>* Poses : {&Library->Relaxed,&Library->OpenHand,&Library->Grip})
    {
        if (Poses->Num()!=N) return false;
        TArray<FTransform> Global,Retargeted;Global.SetNum(N);Retargeted.SetNum(N);
        for (int32 I=0;I<N;++I)
        {
            const int32 Parent=Ref.GetParentIndex(I);
            Global[I]=Parent>=0?(*Poses)[I]*Global[Parent]:(*Poses)[I];
            const FQuat Delta=Global[I].GetRotation()*SourceGlobal[I].GetRotation().Inverse();
            Retargeted[I]=FTransform((Delta*TargetGlobal[I].GetRotation()).GetNormalized(),
                Global[I].GetLocation()+TargetGlobal[I].GetLocation()-SourceGlobal[I].GetLocation());
        }
        for (int32 I=0;I<N;++I)
        {
            const int32 Parent=Ref.GetParentIndex(I);
            (*Poses)[I]=Parent>=0?Retargeted[I].GetRelativeTransform(Retargeted[Parent]):Retargeted[I];
        }
    }
    const int32 Hand=Ref.FindBoneIndex(TEXT("hand_r"));
    Library->WristRelativeToCup.SetRotation((Library->WristRelativeToCup.GetRotation()*
        SourceGlobal[Hand].GetRotation().Inverse()*TargetGlobal[Hand].GetRotation()).GetNormalized());
    Library->Rest=Ref.GetRefBonePose();Library->MarkPackageDirty();
    return true;
}
