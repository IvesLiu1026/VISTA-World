// Trusted scenario runner controls the HUMAN. This is not an assistant skill.
#include "HomeActions.h"
#include "HomeActionsJson.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"

using namespace HomeJson;

void AHomeActionsCharacter::StopDirector()
{
    if (DirectorOwner.IsEmpty()) return;
    if (!DirectorAction.IsEmpty() && ActiveId==DirectorAction) HomeCancel();
    PrivatePath.Empty();bPrivateMoving=bPrivateLooking=false;PrivateMotion=TEXT("stopped");
    GetCharacterMovement()->StopMovementImmediately();
    HomeObserve(bDirectorWasClean);
    DirectorOwner.Empty();DirectorAction.Empty();DirectorUntil=0;
}

void AHomeActionsCharacter::DirectorCommand(const TSharedPtr<FJsonObject>& D,FString& Code)
{
    Code=TEXT("ACTOR_REJECTED");const FString Owner=String(D,TEXT("owner")),Control=String(D,TEXT("control"));
    bool Valid=Owner.Len()==32;
    for (TCHAR C:Owner) Valid&=FChar::IsHexDigit(C);
    if (!Valid || !Controller) return;
    if (Control==TEXT("begin"))
    {
        const FString View=String(D,TEXT("view"));
        if (!DirectorOwner.IsEmpty() || !ActiveId.IsEmpty() || (View!=TEXT("first") && View!=TEXT("third"))) return;
        DirectorOwner=Owner;DirectorAction.Empty();DirectorUntil=FPlatformTime::Seconds()+8;
        bDirectorThird=View==TEXT("third");bDirectorWasClean=bCleanObservation;
        EmbodiedView(bDirectorThird?1:0);HomeObserve(true);
        PrivatePath.Empty();bPrivateMoving=bPrivateLooking=false;PrivateMotion=TEXT("idle");
        Code=TEXT("ACTOR_ACCEPTED");return;
    }
    if (DirectorOwner!=Owner || FPlatformTime::Seconds()>DirectorUntil) return;
    if (Control==TEXT("stop")) {StopDirector();Code=TEXT("ACTOR_ACCEPTED");return;}
    if (Control==TEXT("heartbeat")) {DirectorUntil=FPlatformTime::Seconds()+8;Code=TEXT("ACTOR_ACCEPTED");return;}
    if (!ActiveId.IsEmpty() || bPrivateMoving || bPrivateLooking) {Code=TEXT("ACTOR_BUSY");return;}
    if (Control==TEXT("path"))
    {
        const TArray<TSharedPtr<FJsonValue>>* Rows;
        if (!D->TryGetArrayField(TEXT("points_cm"),Rows) || Rows->Num()<1 || Rows->Num()>96) return;
        TArray<FVector> Points;
        for (const auto& V:*Rows)
        {
            if (V->Type!=EJson::Array || V->AsArray().Num()!=3) return;
            const auto& A=V->AsArray();for (const auto& N:A) if (N->Type!=EJson::Number) return;
            const FVector P(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber());
            if (P.ContainsNaN() || P.Size()>100000) return;Points.Add(P);
        }
        PrivateTarget=Points[0];Points.RemoveAt(0);PrivatePath=Points;
        PrivatePrevious=GetActorLocation();PrivateStall=PrivateMoveClock=0;
        PrivateLook=FRotator(-8,GetControlRotation().Yaw,0);PrivatePreviewCm=0;PrivateCornerFrames=0;
        bPrivateMoving=bPrivateLooking=true;PrivateMotion=TEXT("walking");
    }
    else if (Control==TEXT("look"))
    {
        auto* E=Resolve(String(D,TEXT("target")));
        if (!E || !E->Actor.IsValid()) return;
        FVector Eye;FRotator Look;ActionView(Eye,Look);
        PrivateLook=(ControlPoint(*E)-Eye).Rotation();PrivateLook.Pitch=FMath::Clamp(PrivateLook.Pitch,-80.f,80.f);
        bPrivateLooking=true;PrivateMotion=TEXT("looking");
    }
    else if (Control==TEXT("phone"))
    {
        if (!D->HasTypedField<EJson::Boolean>(TEXT("enabled"))) return;
        HomePhone(Bool(D,TEXT("enabled")));
        if (bPhoneCall!=Bool(D,TEXT("enabled"))) {Code=LastCode;return;}
        // Return the gaze from the tabletop to conversational eye level.
        if (bPhoneCall)
        {PrivateLook=FRotator(-5,GetControlRotation().Yaw,0);bPrivateLooking=true;PrivateMotion=TEXT("looking");}
        else PrivateMotion=TEXT("arrived");
    }
    else if (Control==TEXT("action"))
    {
        const FString Action=String(D,TEXT("action")),Target=String(D,TEXT("target")),Id=String(D,TEXT("action_id"));
        bool IdValid=Id.Len()==32;for (TCHAR C:Id) IdValid&=FChar::IsHexDigit(C);if (!IdValid) return;
        const bool Allowed=(Action==TEXT("pick_up") && Target==TEXT("phone")) ||
            (Action==TEXT("look_at") && (Target==TEXT("phone") || Target==TEXT("stove") || Target==TEXT("faucet") || Target==TEXT("keys"))) ||
            (Action==TEXT("crouch") && Target.IsEmpty());
        if (!Allowed) return;
        auto* E=Resolve(Target);DirectorAction=Id;
        if (!BeginAction(Id,Action,E?E->Id:TEXT(""),TEXT(""),Code)) return;
    }
    else return;
    DirectorUntil=FPlatformTime::Seconds()+8;Code=TEXT("ACTOR_ACCEPTED");
}
