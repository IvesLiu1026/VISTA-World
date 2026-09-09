#include "HomeFluidAuthoring.h"
#include "HomeActionsJson.h"
#include "NiagaraComponent.h"
#include "NiagaraSystem.h"
#include "NiagaraTypes.h"
#include "NiagaraEmitter.h"
#include "NiagaraScript.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"
#if WITH_EDITOR
#include "NiagaraGraph.h"
#include "NiagaraScriptSource.h"
#include "NiagaraNodeFunctionCall.h"
#include "NiagaraNodeAssignment.h"
#include "ViewModels/Stack/NiagaraStackGraphUtilities.h"
#include "ViewModels/Stack/NiagaraParameterHandle.h"
#endif

FString UHomeFluidAuthoring::InspectHoseSource(UNiagaraSystem* System)
{
    auto Out=MakeShared<FJsonObject>();TArray<TSharedPtr<FJsonValue>> Rows;
#if WITH_EDITORONLY_DATA
    if (System && System->GetPathName().StartsWith(TEXT("/Game/VISTA/VillaR1/")))
        for (const auto& H:System->GetEmitterHandles())
        {
            TArray<UNiagaraScript*> Scripts;H.GetEmitterData()->GetScripts(Scripts,false);
            for (auto* Script:Scripts) if (Script)
            {
                const auto& VM=Script->GetVMExecutableData();TArray<FString> Lines;
                (VM.LastHlslTranslation+TEXT("\n")+VM.LastHlslTranslationGPU).ParseIntoArrayLines(Lines);
                FString Excerpt;int32 Last=-1;
                for (int32 I=0;I<Lines.Num();++I)
                    if (Lines[I].Contains(TEXT("SourcePosition")) || Lines[I].Contains(TEXT("SphereLocation")) || Lines[I].Contains(TEXT("WaterHeight")))
                        for (int32 J=FMath::Max(Last+1,I-4);J<FMath::Min(Lines.Num(),I+12);++J)
                        {Excerpt+=Lines[J]+TEXT("\n");Last=J;}
                if (!Excerpt.IsEmpty())
                {auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("emitter"),H.GetName().ToString());R->SetStringField(TEXT("script"),Script->GetName());R->SetStringField(TEXT("source_excerpt"),Excerpt);Rows.Add(MakeShared<FJsonValueObject>(R));}
            }
        }
#endif
    Out->SetArrayField(TEXT("compiled_source_bindings"),Rows);return HomeJson::Encode(Out);
}

bool UHomeFluidAuthoring::ConfigureVesselCollision(UStaticMesh* Mesh,bool Carafe)
{
    if (!Mesh || !Mesh->GetBodySetup() || !Mesh->GetPathName().StartsWith(TEXT("/Game/VISTA/VillaR1/"))) return false;
    auto* Body=Mesh->GetBodySetup();Body->AggGeom.EmptyElements();Body->CollisionTraceFlag=CTF_UseSimpleAndComplex;
    // (outer radius, inner radius, height), sampled from the Blender lathe.
    const TArray<FVector> Rings=Carafe?TArray<FVector>{{4.9,4.6,.6},{5,4.7,1},{4.7,4.5,13.5},{3,2.8,19.2},{2.8,2.6,21.8},{2.8,2.6,24.8},{3,2.78,25.5}}:
        TArray<FVector>{{3.33,2.95,.9},{3.75,3.4,6},{3.85,3.55,9},{3.67,3.50,9.5}};
    constexpr int32 Segments=24;
    for (int32 Z=0;Z<Rings.Num()-1;++Z)
        for (int32 I=0;I<Segments;++I)
        {
            FKConvexElem E;
            for (int32 K=0;K<2;++K) for (int32 S=0;S<2;++S) for (int32 R=0;R<2;++R)
            {
                const float A=(I+S)*2.f*PI/Segments;const auto P=Rings[Z+K];const float Radius=R?P.Y:P.X;
                E.VertexData.Add(FVector(Radius*FMath::Cos(A),Radius*FMath::Sin(A),P.Z));
            }
            E.UpdateElemBox();Body->AggGeom.ConvexElems.Add(E);
        }
    FKConvexElem Base;
    for (int32 Z=0;Z<2;++Z) for (int32 I=0;I<Segments;++I)
    {const float A=I*2.f*PI/Segments;Base.VertexData.Add(FVector((Carafe?4.1f:2.95f)*FMath::Cos(A),(Carafe?4.1f:2.95f)*FMath::Sin(A),Z?(Carafe?.6f:.9f):0.f));}
    Base.UpdateElemBox();Body->AggGeom.ConvexElems.Add(Base);
    if (!Carafe)
    {
        const FVector Points[]={FVector(-3.4,0,7.6),FVector(-6,0,7.6),FVector(-7,0,5),FVector(-6,0,2.5),FVector(-3.3,0,2.3)};
        for (int32 I=0;I<4;++I)
        {FKSphylElem E;E.Center=(Points[I]+Points[I+1])*.5f;E.Radius=.5f;E.Length=FVector::Distance(Points[I],Points[I+1]);E.Rotation=FQuat::FindBetweenNormals(FVector::UpVector,(Points[I+1]-Points[I]).GetSafeNormal()).Rotator();Body->AggGeom.SphylElems.Add(E);}
    }
    Body->InvalidatePhysicsData();Body->CreatePhysicsMeshes();Mesh->MarkPackageDirty();return true;
}

FString UHomeFluidAuthoring::ExposeHoseSource(UNiagaraSystem* System)
{
    auto Out=MakeShared<FJsonObject>();Out->SetBoolField(TEXT("ok"),false);
#if WITH_EDITOR
    if (!System || !System->GetPathName().StartsWith(TEXT("/Game/VISTA/VillaR1/")))
    {Out->SetStringField(TEXT("error"),TEXT("PROJECT_OWNED_COPY_REQUIRED"));return HomeJson::Encode(Out);}
    struct FBinding {FString Function,Input,User;FNiagaraTypeDefinition Type;};
    const TArray<FBinding> Bindings={
        {TEXT("SpawnRate001"),TEXT("SpawnRate"),TEXT("User.SourceRate"),FNiagaraTypeDefinition::GetFloatDef()},
        {TEXT("SphereLocation"),TEXT("Offset"),TEXT("User.SourcePosition"),FNiagaraTypeDefinition::GetVec3Def()},
        {TEXT("SphereLocation"),TEXT("Sphere Radius"),TEXT("User.SourceRadius"),FNiagaraTypeDefinition::GetFloatDef()},
        {TEXT("VelocityAssignment"),TEXT("Particles.Velocity"),TEXT("User.SourceVelocity"),FNiagaraTypeDefinition::GetVec3Def()}};
    struct FWork {UNiagaraNodeFunctionCall* Node;FBinding Binding;};TArray<FWork> Work;
    for (const auto& H:System->GetEmitterHandles())
    {
        if (!H.GetName().ToString().Contains(TEXT("FluidControl"))) continue;
        auto* Source=Cast<UNiagaraScriptSource>(H.GetEmitterData()->GraphSource);
        if (!Source || !Source->NodeGraph) continue;
        for (const FBinding& B:Bindings)
            for (UEdGraphNode* Node:Source->NodeGraph->Nodes)
                if (auto* Call=Cast<UNiagaraNodeFunctionCall>(Node))
                {
                    if (Call->GetFunctionName()==B.Function) Work.Add({Call,B});
                    if (B.Function==TEXT("VelocityAssignment"))
                        if (auto* Assignment=Cast<UNiagaraNodeAssignment>(Call))
                            if (Assignment->FindAssignmentTarget(TEXT("Particles.Velocity"))!=INDEX_NONE)
                            {FBinding Actual=B;Actual.Function=Call->GetFunctionName();Work.Add({Call,Actual});}
                }
    }
    if (Work.Num()!=Bindings.Num())
    {Out->SetStringField(TEXT("error"),TEXT("EXPECTED_HOSE_MODULES_MISSING"));Out->SetNumberField(TEXT("found"),Work.Num());return HomeJson::Encode(Out);}
    System->Modify();TSet<FNiagaraVariableBase> Known;
    for (const auto& B:Bindings)
    {
        FNiagaraVariable V(B.Type,FName(*B.User));V.AllocateData();
        if (B.Type==FNiagaraTypeDefinition::GetFloatDef()) V.SetValue<float>(B.User.EndsWith(TEXT("Radius"))?.6f:0.f);
        else V.SetValue<FVector3f>(FVector3f(0,0,B.User.EndsWith(TEXT("Velocity"))?-65:50));
        System->GetExposedParameters().AddParameter(V,true);
        System->GetExposedParameters().SetParameterData(V.GetData(),V);
        Known.Add(V);
    }
    TArray<TSharedPtr<FJsonValue>> Rows;
    for (const auto& W:Work)
    {
        const FName Input(*(TEXT("Module.")+W.Binding.Input));
        auto Handle=FNiagaraParameterHandle::CreateAliasedModuleParameterHandle(Input,FName(*W.Node->GetFunctionName()));
        auto& Pin=FNiagaraStackGraphUtilities::GetOrCreateStackFunctionInputOverridePin(*W.Node,Handle,W.Binding.Type,FGuid(),FGuid());
        if (Pin.LinkedTo.Num()==0)
            FNiagaraStackGraphUtilities::SetLinkedParameterValueForFunctionInput(Pin,
                FNiagaraVariableBase(W.Binding.Type,FName(*W.Binding.User)),Known);
        else
        {
            // The corresponding stack inspection helper is not exported by
            // this installed engine. Inspect this public graph link directly.
            const auto* Existing=Pin.LinkedTo.Num()==1?Pin.LinkedTo[0]:nullptr;
            if (!Existing || Existing->GetOwningNode()->GetClass()->GetName()!=TEXT("NiagaraNodeParameterMapGet") || Existing->PinName!=FName(*W.Binding.User))
            {Out->SetStringField(TEXT("error"),TEXT("INPUT_HAS_A_DIFFERENT_LINK"));return HomeJson::Encode(Out);}
        }
        // A rapid-iteration value for the old literal must not shadow its link.
        for (const auto& H:System->GetEmitterHandles())
        {
            TArray<UNiagaraScript*> Scripts;H.GetEmitterData()->GetScripts(Scripts,false);
            for (auto* S:Scripts) if (S)
            {
                TArray<FNiagaraVariable> Vars;S->RapidIterationParameters.GetParameters(Vars);
                for (const auto& V:Vars)
                    if (V.GetName().ToString().EndsWith(TEXT(".")+W.Binding.Function+TEXT(".")+W.Binding.Input))
                        S->RapidIterationParameters.RemoveParameter(V);
            }
        }
        auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("module"),W.Node->GetFunctionName());
        R->SetStringField(TEXT("input"),W.Binding.Input);R->SetStringField(TEXT("linked_parameter"),W.Binding.User);
        Rows.Add(MakeShared<FJsonValueObject>(R));
    }
    System->RequestCompile(true);System->WaitForCompilationComplete(false,false);System->MarkPackageDirty();
    Out->SetArrayField(TEXT("bindings"),Rows);Out->SetBoolField(TEXT("ok"),true);
#else
    Out->SetStringField(TEXT("error"),TEXT("EDITOR_REQUIRED"));
#endif
    return HomeJson::Encode(Out);
}

FString UHomeFluidAuthoring::DescribeSystem(UNiagaraSystem* System)
{
    auto Out=MakeShared<FJsonObject>();
    Out->SetBoolField(TEXT("ok"),System!=nullptr);
    if (!System) return HomeJson::Encode(Out);
    Out->SetStringField(TEXT("asset"),System->GetPathName());
    const auto& Store=System->GetExposedParameters();
    TArray<FNiagaraVariable> Vars;Store.GetParameters(Vars);
    TArray<TSharedPtr<FJsonValue>> Rows;
    for (auto& V:Vars)
    {
        auto R=MakeShared<FJsonObject>();
        R->SetStringField(TEXT("name"),V.GetName().ToString());
        R->SetStringField(TEXT("type"),V.GetType().GetName());
        if (const uint8* Data=Store.GetParameterData(V))
        {
            V.SetData(Data);
            R->SetStringField(TEXT("default"),V.ToString());
        }
        Rows.Add(MakeShared<FJsonValueObject>(R));
    }
    Out->SetArrayField(TEXT("parameters"),Rows);
#if WITH_EDITORONLY_DATA
    TArray<TSharedPtr<FJsonValue>> Emitters;
    for (const auto& Handle:System->GetEmitterHandles())
    {
        auto E=MakeShared<FJsonObject>();
        E->SetStringField(TEXT("name"),Handle.GetName().ToString());
        TArray<TSharedPtr<FJsonValue>> Scripts;
        if (const auto* Data=Handle.GetEmitterData())
        {
            TArray<UNiagaraScript*> All;Data->GetScripts(All,false);
            for (const auto* Script:All)
            {
                if (!Script) continue;
                auto S=MakeShared<FJsonObject>();S->SetStringField(TEXT("path"),Script->GetPathName());
                TArray<FNiagaraVariable> Values;Script->RapidIterationParameters.GetParameters(Values);
                TArray<TSharedPtr<FJsonValue>> Params;
                for (auto& V:Values)
                {
                    auto P=MakeShared<FJsonObject>();P->SetStringField(TEXT("name"),V.GetName().ToString());
                    P->SetStringField(TEXT("type"),V.GetType().GetName());
                    if (const uint8* Raw=Script->RapidIterationParameters.GetParameterData(V))
                    {V.SetData(Raw);P->SetStringField(TEXT("default"),V.ToString());}
                    Params.Add(MakeShared<FJsonValueObject>(P));
                }
                S->SetArrayField(TEXT("rapid_iteration_parameters"),Params);
                Scripts.Add(MakeShared<FJsonValueObject>(S));
            }
        }
        E->SetArrayField(TEXT("scripts"),Scripts);Emitters.Add(MakeShared<FJsonValueObject>(E));
    }
    Out->SetArrayField(TEXT("emitters"),Emitters);
#endif
    return HomeJson::Encode(Out);
}

FString UHomeFluidAuthoring::ConfigureComponent(UNiagaraComponent* Component,const FString& ParametersJson)
{
    auto Out=MakeShared<FJsonObject>();Out->SetBoolField(TEXT("ok"),false);
    const auto Params=HomeJson::Decode(ParametersJson);
    if (!Component || !Component->GetAsset() || !Params)
    {Out->SetStringField(TEXT("error"),TEXT("COMPONENT_ASSET_OR_JSON_MISSING"));return HomeJson::Encode(Out);}
    TArray<FNiagaraVariable> Vars;Component->GetAsset()->GetExposedParameters().GetParameters(Vars);
    // Validate the entire request before making any mutation.
    for (const auto& Pair:Params->Values)
    {
        const auto* V=Vars.FindByPredicate([&](const auto& X){return X.GetName().ToString()==Pair.Key;});
        bool Valid=false;
        if (V)
        {
            const auto& T=V->GetType();
            if (T==FNiagaraTypeDefinition::GetBoolDef()) Valid=Pair.Value->Type==EJson::Boolean;
            else if (T==FNiagaraTypeDefinition::GetFloatDef() || T==FNiagaraTypeDefinition::GetIntDef())
            {
                Valid=Pair.Value->Type==EJson::Number && FMath::IsFinite(Pair.Value->AsNumber());
                if (Valid && T==FNiagaraTypeDefinition::GetFloatDef())
                    Valid=FMath::Abs(Pair.Value->AsNumber())<=MAX_flt;
                if (Valid && T==FNiagaraTypeDefinition::GetIntDef())
                {const double N=Pair.Value->AsNumber();Valid=N>=MIN_int32 && N<=MAX_int32 && N==FMath::FloorToDouble(N);}
            }
            else if (T==FNiagaraTypeDefinition::GetVec3Def() || T==FNiagaraTypeDefinition::GetPositionDef())
            {
                Valid=Pair.Value->Type==EJson::Array && Pair.Value->AsArray().Num()==3;
                if (Valid) for (const auto& N:Pair.Value->AsArray())
                    Valid=Valid && N->Type==EJson::Number && FMath::IsFinite(N->AsNumber()) &&
                        FMath::Abs(N->AsNumber())<=MAX_flt;
            }
        }
        if (!Valid)
        {Out->SetStringField(TEXT("error"),TEXT("UNKNOWN_OR_MISMATCHED_PARAMETER"));Out->SetStringField(TEXT("parameter"),Pair.Key);return HomeJson::Encode(Out);}
    }
    for (const auto& Pair:Params->Values)
    {
        const auto& T=Vars.FindByPredicate([&](const auto& X){return X.GetName().ToString()==Pair.Key;})->GetType();
        const FName Name(*Pair.Key);
        if (T==FNiagaraTypeDefinition::GetBoolDef()) Component->SetVariableBool(Name,Pair.Value->AsBool());
        else if (T==FNiagaraTypeDefinition::GetFloatDef()) Component->SetVariableFloat(Name,Pair.Value->AsNumber());
        else if (T==FNiagaraTypeDefinition::GetIntDef()) Component->SetVariableInt(Name,int32(Pair.Value->AsNumber()));
        else if (T==FNiagaraTypeDefinition::GetPositionDef()) Component->SetVariablePosition(Name,HomeJson::Vector(Params,*Pair.Key));
        else Component->SetVariableVec3(Name,HomeJson::Vector(Params,*Pair.Key));
    }
    Out->SetBoolField(TEXT("ok"),true);Out->SetNumberField(TEXT("applied"),Params->Values.Num());
    return HomeJson::Encode(Out);
}
