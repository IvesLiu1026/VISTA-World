#include "HomeFluidAuthoring.h"
#include "HomeActionsJson.h"
#include "NiagaraComponent.h"
#include "NiagaraSystem.h"
#include "NiagaraTypes.h"
#include "NiagaraEmitter.h"
#include "NiagaraScript.h"

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
