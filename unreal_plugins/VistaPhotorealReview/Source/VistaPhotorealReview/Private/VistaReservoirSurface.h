#pragma once
#include "CoreMinimal.h"
#include "ProceduralMeshComponent.h"

// Hydrostatic presentation of the conservative vessel ledger. Clip the actual
// lathed interior against a gravity-level plane; solve plane height by volume.
// Niagara separately solves the outgoing stream and splashes.
namespace VistaReservoir
{
struct FSurface
{
    TArray<FVector> Vertices;
    TArray<int32> Indices;
    TArray<FVector> Normals;
    double Volume=0;
    void Triangle(FVector A,FVector B,FVector C)
    {
        FVector N=FVector::CrossProduct(B-A,C-A).GetSafeNormal();
        if (N.IsNearlyZero()) return;
        Volume+=FVector::DotProduct(A,FVector::CrossProduct(B,C))/6.;
        const int32 I=Vertices.Num();Vertices.Append({A,B,C});Indices.Append({I,I+1,I+2});Normals.Append({N,N,N});
    }
};
inline FSurface Clip(const TArray<FVector>& Shell,double Height)
{
    FSurface Result;TArray<FVector> Cut;
    for (int32 I=0;I<Shell.Num();I+=3)
    {
        TArray<FVector> Polygon;
        for (int32 J=0;J<3;++J)
        {
            const FVector A=Shell[I+J],B=Shell[I+(J+1)%3];
            const bool InA=A.Z<=Height,InB=B.Z<=Height;
            if (InA) Polygon.Add(A);
            if (InA!=InB)
            {
                FVector P=FMath::Lerp(A,B,(Height-A.Z)/(B.Z-A.Z));Polygon.Add(P);
                if (!Cut.ContainsByPredicate([&](FVector Q){return P.Equals(Q,.0001);})) Cut.Add(P);
            }
        }
        for (int32 J=1;J+1<Polygon.Num();++J) Result.Triangle(Polygon[0],Polygon[J],Polygon[J+1]);
    }
    if (Cut.Num()>2)
    {
        FVector Centre=FVector::ZeroVector;for (FVector P:Cut) Centre+=P;Centre/=Cut.Num();
        Cut.Sort([&](FVector A,FVector B){return FMath::Atan2(A.Y-Centre.Y,A.X-Centre.X)<FMath::Atan2(B.Y-Centre.Y,B.X-Centre.X);});
        for (int32 I=0;I<Cut.Num();++I) Result.Triangle(Centre,Cut[I],Cut[(I+1)%Cut.Num()]);
    }
    return Result;
}
inline double Update(UProceduralMeshComponent* Component,const FTransform& Vessel,double Millilitres,bool Carafe)
{
    if (!Component) return 0;
    Component->SetVisibility(Millilitres>.02);
    if (Millilitres<=.02) return 0;
    const TArray<FVector2D> Rings=Carafe?TArray<FVector2D>{{4.58,.62},{4.68,1.0},{4.48,13.5},{2.78,19.2},{2.58,21.8},{2.58,24.8},{2.76,25.48}}:
        TArray<FVector2D>{{2.93,.92},{3.38,6},{3.53,9},{3.48,9.48}};
    constexpr int32 Sides=40;TArray<FVector> Shell;
    auto P=[&](int32 R,int32 I){double A=I*2.*PI/Sides;return Vessel.GetRotation().RotateVector(FVector(Rings[R].X*FMath::Cos(A),Rings[R].X*FMath::Sin(A),Rings[R].Y));};
    auto Add=[&](FVector A,FVector B,FVector C){Shell.Append({A,B,C});};
    const FVector Base=Vessel.GetRotation().RotateVector(FVector(0,0,Rings[0].Y));
    const int32 Top=Rings.Num()-1;const FVector Lid=Vessel.GetRotation().RotateVector(FVector(0,0,Rings[Top].Y));
    for (int32 I=0;I<Sides;++I)
    {
        Add(Base,P(0,I+1),P(0,I));Add(Lid,P(Top,I),P(Top,I+1));
        for (int32 R=0;R<Top;++R)
        {Add(P(R,I),P(R,I+1),P(R+1,I+1));Add(P(R,I),P(R+1,I+1),P(R+1,I));}
    }
    double Low=MAX_dbl,High=-MAX_dbl;for (FVector V:Shell) {Low=FMath::Min(Low,V.Z);High=FMath::Max(High,V.Z);}
    for (int32 I=0;I<18;++I) {double Mid=(Low+High)*.5;if (Clip(Shell,Mid).Volume<Millilitres) Low=Mid;else High=Mid;}
    FSurface Result=Clip(Shell,(Low+High)*.5);
    Component->SetWorldLocationAndRotation(Vessel.GetLocation(),FQuat::Identity);
    Component->CreateMeshSection_LinearColor(0,Result.Vertices,Result.Indices,Result.Normals,
        TArray<FVector2D>(),TArray<FLinearColor>(),TArray<FProcMeshTangent>(),false);
    return Result.Volume;
}
}
