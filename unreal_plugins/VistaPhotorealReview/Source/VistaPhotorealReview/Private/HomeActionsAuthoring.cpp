#include "HomeActions.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"

bool UHomeActionsAuthoring::ConfigurePickup(UStaticMesh* Mesh,const FString& Kind)
{
    if (!Mesh || !Mesh->GetBodySetup()) return false;
    UBodySetup* Body=Mesh->GetBodySetup();Body->AggGeom.EmptyElements();Body->CollisionTraceFlag=CTF_UseSimpleAndComplex;
    const FBoxSphereBounds B=Mesh->GetBounds();
    if (Kind==TEXT("pot") || Kind==TEXT("jug"))
    {
        const float R=Kind==TEXT("pot")?12.f:8.f;
        const float H=Kind==TEXT("pot")?14.8f:25.3f;
        for (int32 I=0;I<20;++I)
        {
            FKConvexElem Wall;
            for (int32 Z=0;Z<2;++Z) for (int32 S=0;S<2;++S) for (int32 Inner=0;Inner<2;++Inner)
            {
                const float A=(I+S)*2*PI/20;const float Radius=R-(Inner?.65f:0.f);
                Wall.VertexData.Add(FVector(Radius*FMath::Cos(A),Radius*FMath::Sin(A),Z?H:.6f));
            }
            Wall.UpdateElemBox();Body->AggGeom.ConvexElems.Add(Wall);
        }
        FKBoxElem Base;Base.Center=FVector(0,0,.45);Base.X=R*1.42f;Base.Y=R*1.42f;Base.Z=.9;
        Body->AggGeom.BoxElems.Add(Base);
        if (Kind==TEXT("pot")) for (float Side:{-1.f,1.f})
        {FKBoxElem Handle;Handle.Center=FVector(Side*14.3f,0,11.8f);Handle.X=5.8;Handle.Y=7.8;Handle.Z=1.4;Body->AggGeom.BoxElems.Add(Handle);}
    }
    else
    {
        FKBoxElem Box;Box.Center=B.Origin;Box.X=FMath::Max(.35f,float(B.BoxExtent.X*1.95));
        Box.Y=FMath::Max(.35f,float(B.BoxExtent.Y*1.95));Box.Z=FMath::Max(.4f,float(B.BoxExtent.Z*1.96));
        Body->AggGeom.BoxElems.Add(Box);
    }
    Body->InvalidatePhysicsData();Body->CreatePhysicsMeshes();Mesh->MarkPackageDirty();return true;
}

bool UHomeActionsAuthoring::MirrorHandPoses(USkeletalMesh* Mesh,UEmbodiedPoseLibrary* Library)
{
    if (!Mesh || !Library) return false;
    const auto& Ref=Mesh->GetRefSkeleton();const int32 N=Ref.GetNum();
    if (Library->Rest.Num()!=N) return false;
    TArray<FTransform> Rest;Rest.SetNum(N);
    for (int32 I=0;I<N;++I) {const int32 P=Ref.GetParentIndex(I);Rest[I]=P>=0?Library->Rest[I]*Rest[P]:Library->Rest[I];}
    for (auto* Pose:{&Library->OpenHand,&Library->Grip})
    {
        if (Pose->Num()!=N) return false;
        TArray<FTransform> G;G.SetNum(N);
        for (int32 I=0;I<N;++I) {const int32 P=Ref.GetParentIndex(I);G[I]=P>=0?(*Pose)[I]*G[P]:(*Pose)[I];}
        const auto Original=G;
        for (int32 I=0;I<N;++I)
        {
            const FString Name=Ref.GetBoneName(I).ToString();if (!Name.EndsWith(TEXT("_l"))) continue;
            const int32 R=Ref.FindBoneIndex(FName(Name.LeftChop(2)+TEXT("_r")));if (R<0) continue;
            const FQuat Delta=Original[R].GetRotation()*Rest[R].GetRotation().Inverse();
            const FQuat Mirror(Delta.X,-Delta.Y,-Delta.Z,Delta.W);
            FVector Offset=Original[R].GetLocation()-Rest[R].GetLocation();Offset.X=-Offset.X;
            G[I]=FTransform((Mirror*Rest[I].GetRotation()).GetNormalized(),Rest[I].GetLocation()+Offset);
        }
        for (int32 I=0;I<N;++I) {const int32 P=Ref.GetParentIndex(I);(*Pose)[I]=P>=0?G[I].GetRelativeTransform(G[P]):G[I];}
    }
    Library->MarkPackageDirty();return true;
}
