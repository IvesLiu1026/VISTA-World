#include "VistaExplorer.h"
#include "HomeActionsJson.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"

using namespace HomeJson;

void AVistaExplorerCharacter::ExplorerWalkthrough(bool Enabled)
{
    // A deterministic human demonstration controller, available only in the
    // isolated review process. It never teleports, opens doors, or switches view.
    if (!FParse::Param(FCommandLine::Get(),TEXT("VistaPrivateReview"))) return;
    GetCharacterMovement()->StopMovementImmediately();WalkthroughStatus=TEXT("stopped");
    if (!Enabled) return;
    FString Text;
    if (!CanLeaveSpace() || bCampus || !FFileHelper::LoadFileToString(Text,
        *(FPaths::ProjectConfigDir()/TEXT("VistaWalkthrough.json")))) return;
    const auto Data=Decode(Text);const TArray<TSharedPtr<FJsonValue>>* Points;
    if (!Data || String(Data,TEXT("schema"))!=TEXT("vista.walkthrough/v1") || !Data->TryGetArrayField(TEXT("points"),Points) || Points->Num()>150 || Points->IsEmpty()) return;
    Walkthrough.Empty();for (const auto& V:*Points) {if (!V->AsObject())return;Walkthrough.Add(V->AsObject());}
    if (FVector::Dist2D(GetActorLocation(),Vector(Walkthrough[0],TEXT("position_cm")))>25) {WalkthroughStatus=TEXT("start_mismatch");return;}
    WalkthroughIndex=0;WalkthroughWait=4;WalkthroughStall=WalkthroughClock=WalkthroughDistance=0;
    WalkthroughPrevious=GetActorLocation();bWalkthroughThird=bThirdPerson;WalkthroughStatus=TEXT("running");
}

void AVistaExplorerCharacter::TickWalkthrough(float Dt)
{
    if (WalkthroughStatus!=TEXT("running")) return;
    WalkthroughClock+=Dt;
    const float Moved=FVector::Dist2D(GetActorLocation(),WalkthroughPrevious);
    WalkthroughPrevious=GetActorLocation();WalkthroughDistance+=Moved;
    if (bThirdPerson!=bWalkthroughThird || Riding.IsValid() || WalkthroughClock>360 || Moved>80)
    {WalkthroughStatus=TEXT("interrupted");GetCharacterMovement()->StopMovementImmediately();return;}
    if (Menu) return;
    if (WalkthroughWait>0)
    {
        WalkthroughWait-=Dt;
        if (WalkthroughIndex>0 && Controller)
        {
            const auto P=Walkthrough[WalkthroughIndex-1];FRotator R=Controller->GetControlRotation();
            if (P->HasField(TEXT("look_yaw"))) R.Yaw=FMath::FixedTurn(R.Yaw,Number(P,TEXT("look_yaw")),60*Dt);
            R.Pitch=FMath::FInterpTo(R.Pitch,Number(P,TEXT("pitch"),-8),Dt,3);Controller->SetControlRotation(R);
        }
        return;
    }
    while (Walkthrough.IsValidIndex(WalkthroughIndex))
    {
        const auto P=Walkthrough[WalkthroughIndex];FVector Delta=Vector(P,TEXT("position_cm"))-GetActorLocation();Delta.Z=0;
        const float Distance=Delta.Size();
        if (Distance<12)
        {
            ++WalkthroughIndex;WalkthroughStall=0;
            WalkthroughWait=FMath::Clamp(float(Number(P,TEXT("pause_s"))),0.f,15.f);
            if (P->HasField(TEXT("say"))) HomeHumanSay(String(P,TEXT("say")));
            if (WalkthroughWait>0) {GetCharacterMovement()->StopMovementImmediately();return;}
            continue;
        }
        if (!Controller) return;
        FRotator Look=Controller->GetControlRotation();const float Desired=Delta.Rotation().Yaw;
        Look.Yaw=FMath::FixedTurn(Look.Yaw,Desired,65*Dt);
        Look.Pitch=FMath::FInterpTo(Look.Pitch,bThirdPerson?-12.f:-5.f,Dt,3);Controller->SetControlRotation(Look);
        const float Error=FMath::Abs(FMath::FindDeltaAngleDegrees(Look.Yaw,Desired));
        const float Input=FMath::Clamp((60-Error)/35.f,0.f,1.f)*FMath::Clamp(Distance/38.f,.25f,1.f);
        AddMovementInput(Delta.GetSafeNormal(),Input,true);
        WalkthroughStall=Input>.15f && Moved<.01f?WalkthroughStall+Dt:0;
        if (WalkthroughStall>5) {WalkthroughStatus=TEXT("blocked");GetCharacterMovement()->StopMovementImmediately();}
        return;
    }
    WalkthroughStatus=TEXT("completed");GetCharacterMovement()->StopMovementImmediately();
}
