#pragma once
#include "CoreMinimal.h"
#include "ProceduralMeshComponent.h"

// A resolved ballistic column covers the sub-cell stream that a small FLIP
// domain cannot resolve. Emitted slices continue falling after source-off.
// Niagara remains responsible for the surrounding coarse splash simulation.
namespace VistaStream
{
struct FSlice {FVector Origin;double Age=0,Duration=0,Rate=0,Speed=0,Floor=0;};
struct FColumn
{
    TArray<FSlice> Slices;
    void Reset() {Slices.Empty();}
    void Update(UProceduralMeshComponent* Mesh,double Dt,FVector Origin,double Rate,double Speed,double Floor)
    {
        if (!Mesh || Dt<=0) return;
        for (auto& S:Slices) S.Age+=Dt;
        if (Rate>0) Slices.Add({Origin,Dt,Dt,Rate,Speed,Floor});
        TArray<FVector> Vertices,Normals;TArray<int32> Indices;
        for (int32 I=Slices.Num()-1;I>=0;--I)
        {
            const auto& S=Slices[I];
            const double Height=FMath::Max(0.,S.Origin.Z-S.Floor);
            const double Life=(FMath::Sqrt(S.Speed*S.Speed+1960.*Height)-S.Speed)/980.;
            const double Young=FMath::Max(0.,S.Age-S.Duration),Old=FMath::Min(Life,S.Age);
            if (Young>=Life) {Slices.RemoveAt(I);continue;}
            constexpr int32 Sides=16;
            const int32 Start=Vertices.Num();
            for (double T:{Young,Old})
            {
                const double Radius=FMath::Sqrt(S.Rate/(PI*FMath::Max(1.,S.Speed+980.*T)));
                const FVector Centre=S.Origin-FVector(0,0,S.Speed*T+490.*T*T);
                for (int32 J=0;J<Sides;++J)
                {
                    const double A=J*2.*PI/Sides;const FVector N(FMath::Cos(A),FMath::Sin(A),0);
                    Vertices.Add(Centre+Radius*N);Normals.Add(N);
                }
            }
            for (int32 J=0;J<Sides;++J)
            {
                const int32 A=Start+J,B=Start+(J+1)%Sides,C=B+Sides,D=A+Sides;
                Indices.Append({A,C,B,A,D,C});
            }
        }
        Mesh->SetVisibility(!Vertices.IsEmpty());
        Mesh->CreateMeshSection_LinearColor(0,Vertices,Indices,Normals,TArray<FVector2D>(),
            TArray<FLinearColor>(),TArray<FProcMeshTangent>(),false);
    }
};
}
