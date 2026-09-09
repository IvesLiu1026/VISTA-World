#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Misc/FileHelper.h"
#include "VistaMotionCurves.h"
#include <cstdio>

namespace HomeJson
{
inline FString String(const TSharedPtr<FJsonObject>& O,const TCHAR* Key,const FString& Default=TEXT(""))
{ FString V;return O && O->TryGetStringField(Key,V)?V:Default; }
inline double Number(const TSharedPtr<FJsonObject>& O,const TCHAR* Key,double Default=0.)
{ double V;return O && O->TryGetNumberField(Key,V)?V:Default; }
inline bool Bool(const TSharedPtr<FJsonObject>& O,const TCHAR* Key,bool Default=false)
{ bool V;return O && O->TryGetBoolField(Key,V)?V:Default; }
inline FVector Vector(const TSharedPtr<FJsonObject>& O,const TCHAR* Key,FVector Default=FVector::ZeroVector)
{
    const TArray<TSharedPtr<FJsonValue>>* A;
    if (!O || !O->TryGetArrayField(Key,A) || A->Num()!=3) return Default;
    return FVector((*A)[0]->AsNumber(),(*A)[1]->AsNumber(),(*A)[2]->AsNumber());
}
inline TArray<TSharedPtr<FJsonValue>> Values(FVector V)
{ return {MakeShared<FJsonValueNumber>(V.X),MakeShared<FJsonValueNumber>(V.Y),MakeShared<FJsonValueNumber>(V.Z)}; }
inline FString Encode(const TSharedPtr<FJsonObject>& O)
{ FString S;auto W=TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&S);FJsonSerializer::Serialize(O.ToSharedRef(),W);return S; }
inline TSharedPtr<FJsonObject> Decode(const FString& S)
{ TSharedPtr<FJsonObject> O;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(S),O);return O; }
inline TSharedPtr<FJsonObject> Copy(const TSharedPtr<FJsonObject>& O)
{ return O?Decode(Encode(O)):MakeShared<FJsonObject>(); }
inline bool AtomicSave(const FString& Path,const FString& Text)
{
    const FString Temp=Path+TEXT(".tmp");
    if (!FFileHelper::SaveStringToFile(Text,*Temp,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM)) return false;
    // POSIX rename replaces the destination atomically. IFileManager::Move's
    // replace mode deletes it first, leaving a missing-file window to readers.
    return std::rename(TCHAR_TO_UTF8(*Temp),TCHAR_TO_UTF8(*Path))==0;
}
inline bool Contains(const TSharedPtr<FJsonObject>& O,const TCHAR* Key,const FString& V)
{
    const TArray<TSharedPtr<FJsonValue>>* A;
    if (O && O->TryGetArrayField(Key,A)) for (const auto& X:*A) if (X->AsString()==V) return true;
    return false;
}
inline FString RequestSignature(const TSharedPtr<FJsonObject>& O)
{
    FString Result;
    for (const TCHAR* Key:{TEXT("schema"),TEXT("command_id"),TEXT("session_id"),TEXT("revision"),TEXT("operation"),
        TEXT("action"),TEXT("target_id"),TEXT("secondary_target_id"),TEXT("event_id"),TEXT("active_command_id")})
    {const FString V=String(O,Key);Result+=FString::Printf(TEXT("%d:"),V.Len())+V;}
    return Result+FString::Printf(TEXT("#%.0f"),Number(O,TEXT("expected_generation"),-1));
}
inline float Ease(float V) { return VistaMotion::Ease(V); }
}
