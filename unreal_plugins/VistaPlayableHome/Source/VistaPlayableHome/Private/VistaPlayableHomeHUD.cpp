#include "VistaPlayableHomeHUD.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "VistaEventSubsystem.h"
#include "VistaInteractable.h"
#include "VistaInteractionComponent.h"
#include "VistaLiquidReceiverActor.h"
#include "VistaPickupActor.h"
#include "VistaPlayableHomeCharacter.h"
#include "VistaPostureComponent.h"
#include "VistaSeatActor.h"

namespace
{
FString FriendlyNameFromSemanticId(const FString& SemanticId)
{
    FString Leaf = SemanticId;
    int32 SeparatorIndex = INDEX_NONE;
    if (Leaf.FindChar(TEXT('#'), SeparatorIndex))
    {
        Leaf.LeftInline(SeparatorIndex, EAllowShrinking::No);
    }
    if (Leaf.FindLastChar(TEXT('/'), SeparatorIndex))
    {
        Leaf.RightChopInline(SeparatorIndex + 1, EAllowShrinking::No);
    }

    Leaf.ReplaceInline(TEXT("."), TEXT("_"), ESearchCase::CaseSensitive);
    Leaf.ReplaceInline(TEXT("-"), TEXT("_"), ESearchCase::CaseSensitive);
    TArray<FString> Tokens;
    Leaf.ParseIntoArray(Tokens, TEXT("_"), true);

    TArray<FString> FriendlyWords;
    for (FString Token : Tokens)
    {
        Token.TrimStartAndEndInline();
        const bool bStructuralToken =
            Token.Equals(TEXT("entity"), ESearchCase::IgnoreCase) ||
            Token.Equals(TEXT("anchor"), ESearchCase::IgnoreCase) ||
            Token.Equals(TEXT("actor"), ESearchCase::IgnoreCase) ||
            Token.Equals(TEXT("object"), ESearchCase::IgnoreCase) ||
            Token.Equals(TEXT("prop"), ESearchCase::IgnoreCase);
        if (Token.IsEmpty() || Token.IsNumeric() || bStructuralToken)
        {
            continue;
        }
        Token.ToLowerInline();
        Token[0] = FChar::ToUpper(Token[0]);
        FriendlyWords.Add(MoveTemp(Token));
    }
    return FriendlyWords.IsEmpty()
        ? FString(TEXT("Object"))
        : FString::Join(FriendlyWords, TEXT(" "));
}

FString FriendlyNameForActor(AActor* Actor)
{
    if (!IsValid(Actor) ||
        !Actor->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        return TEXT("Object");
    }
    return FriendlyNameFromSemanticId(
        IVistaInteractable::Execute_VistaGetSemanticId(Actor));
}

bool IsEnabledRuntimeValue(const FString& Value)
{
    return Value.Equals(TEXT("true"), ESearchCase::IgnoreCase) ||
           Value.Equals(TEXT("on"), ESearchCase::IgnoreCase) ||
           Value.Equals(TEXT("1"), ESearchCase::CaseSensitive);
}

bool IsToggleEnabled(AActor* Actor)
{
    if (!IsValid(Actor) ||
        !Actor->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        return false;
    }
    const FVistaEntityRuntimeState State =
        IVistaInteractable::Execute_VistaGetRuntimeState(Actor);
    const TCHAR* ToggleKeys[] = {TEXT("active"), TEXT("powered"), TEXT("on")};
    for (const TCHAR* Key : ToggleKeys)
    {
        if (const FString* Value = State.Values.Find(FName(Key)))
        {
            return IsEnabledRuntimeValue(*Value);
        }
    }
    return false;
}

FString BuildInteractionLabel(
    const AVistaPlayableHomeCharacter& Character,
    AActor* Target)
{
    if (!IsValid(Target))
    {
        return FString();
    }

    const AVistaPickupActor* Held = Character.GetHeldPickup();
    if (IsValid(Held) && Target != Held)
    {
        if (Held->IsPourable() &&
            IsValid(Cast<AVistaLiquidReceiverActor>(Target)))
        {
            return FString::Printf(
                TEXT("Pour %s into %s"),
                *FriendlyNameFromSemanticId(Held->SemanticId),
                *FriendlyNameForActor(Target));
        }
        return FString::Printf(
            TEXT("Place %s"), *FriendlyNameFromSemanticId(Held->SemanticId));
    }

    const FString TargetName = FriendlyNameForActor(Target);
    switch (Character.GetDefaultInteractionAffordance(Target))
    {
        case EVistaAffordance::Open:
            return FString::Printf(TEXT("Open %s"), *TargetName);
        case EVistaAffordance::Close:
            return FString::Printf(TEXT("Close %s"), *TargetName);
        case EVistaAffordance::PickUp:
            return FString::Printf(TEXT("Pick Up %s"), *TargetName);
        case EVistaAffordance::Drop:
            return FString::Printf(TEXT("Drop %s"), *TargetName);
        case EVistaAffordance::Place:
            return FString::Printf(TEXT("Place %s"), *TargetName);
        case EVistaAffordance::Press:
            return FString::Printf(TEXT("Press %s control"), *TargetName);
        case EVistaAffordance::TurnOn:
            return FString::Printf(TEXT("Turn On %s"), *TargetName);
        case EVistaAffordance::TurnOff:
            return FString::Printf(TEXT("Turn Off %s"), *TargetName);
        case EVistaAffordance::Toggle:
            return IsToggleEnabled(Target)
                ? FString::Printf(TEXT("Turn Off %s"), *TargetName)
                : FString::Printf(TEXT("Turn On %s"), *TargetName);
        case EVistaAffordance::Sit:
            return FString::Printf(TEXT("Sit on %s"), *TargetName);
        case EVistaAffordance::Stand:
            return FString::Printf(TEXT("Stand up from %s"), *TargetName);
        case EVistaAffordance::Inspect:
        default:
            return FString::Printf(TEXT("Inspect %s"), *TargetName);
    }
}

FString BuildSelectedActionLabel(const FVistaPlayerActionOption& Action)
{
    const FString TargetName = FriendlyNameForActor(Action.Target);
    switch (Action.Affordance)
    {
        case EVistaAffordance::Press:
            return FString::Printf(TEXT("Press %s control"), *TargetName);
        case EVistaAffordance::TurnOn:
            return FString::Printf(TEXT("Turn On %s"), *TargetName);
        case EVistaAffordance::TurnOff:
            return FString::Printf(TEXT("Turn Off %s"), *TargetName);
        case EVistaAffordance::Open:
            return FString::Printf(TEXT("Open %s"), *TargetName);
        case EVistaAffordance::Close:
            return FString::Printf(TEXT("Close %s"), *TargetName);
        case EVistaAffordance::Inspect:
            return FString::Printf(TEXT("Inspect %s"), *TargetName);
        case EVistaAffordance::Sit:
            return FString::Printf(TEXT("Sit on %s"), *TargetName);
        case EVistaAffordance::Stand:
            return FString::Printf(TEXT("Stand up from %s"), *TargetName);
        case EVistaAffordance::Pour:
            return FString::Printf(
                TEXT("Pour %s into %s"),
                *TargetName,
                *FriendlyNameForActor(Action.SecondaryTarget));
        case EVistaAffordance::PickUp:
            return FString::Printf(TEXT("Pick Up %s"), *TargetName);
        case EVistaAffordance::Place:
            return FString::Printf(
                TEXT("Place %s on %s"),
                *TargetName,
                *FriendlyNameForActor(Action.SecondaryTarget));
        default:
            return FString();
    }
}

FString CondenseGoal(const FString& PublicGoal)
{
    FString Goal = PublicGoal;
    Goal.ReplaceInline(TEXT("\r"), TEXT(" "), ESearchCase::CaseSensitive);
    Goal.ReplaceInline(TEXT("\n"), TEXT(" "), ESearchCase::CaseSensitive);
    while (Goal.ReplaceInline(TEXT("  "), TEXT(" "), ESearchCase::CaseSensitive) > 0)
    {
    }
    Goal.TrimStartAndEndInline();
    constexpr int32 MaxGoalCharacters = 92;
    if (Goal.Len() > MaxGoalCharacters)
    {
        Goal = Goal.Left(MaxGoalCharacters - 3) + TEXT("...");
    }
    return Goal;
}

FString ScenarioStatusLabel(EVistaEventStatus Status)
{
    switch (Status)
    {
        case EVistaEventStatus::Applying:
            return TEXT("STARTING");
        case EVistaEventStatus::Active:
            return TEXT("IN PROGRESS");
        case EVistaEventStatus::Succeeded:
            return TEXT("COMPLETE");
        case EVistaEventStatus::Failed:
            return TEXT("FAILED");
        case EVistaEventStatus::TimedOut:
            return TEXT("TIME EXPIRED");
        case EVistaEventStatus::Resetting:
            return TEXT("RESETTING");
        case EVistaEventStatus::Inactive:
        default:
            return FString();
    }
}

FLinearColor ScenarioStatusColor(EVistaEventStatus Status)
{
    switch (Status)
    {
        case EVistaEventStatus::Succeeded:
            return FLinearColor(0.43f, 0.70f, 0.52f, 1.0f);
        case EVistaEventStatus::Failed:
        case EVistaEventStatus::TimedOut:
            return FLinearColor(0.82f, 0.35f, 0.30f, 1.0f);
        default:
            return FLinearColor(0.78f, 0.61f, 0.32f, 1.0f);
    }
}

bool SupportsInspect(AActor* Actor)
{
    return IsValid(Actor) &&
        Actor->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()) &&
        IVistaInteractable::Execute_VistaGetAffordances(Actor).Contains(
            EVistaAffordance::Inspect);
}

FString AffordanceLabel(EVistaAffordance Affordance)
{
    switch (Affordance)
    {
        case EVistaAffordance::Open: return TEXT("Open");
        case EVistaAffordance::Close: return TEXT("Close");
        case EVistaAffordance::PickUp: return TEXT("Pick up");
        case EVistaAffordance::Drop: return TEXT("Drop");
        case EVistaAffordance::Place: return TEXT("Place");
        case EVistaAffordance::Toggle: return TEXT("Toggle");
        case EVistaAffordance::Sit: return TEXT("Sit");
        case EVistaAffordance::Stand: return TEXT("Stand");
        case EVistaAffordance::Inspect: return TEXT("Inspect");
        case EVistaAffordance::Press: return TEXT("Press");
        case EVistaAffordance::TurnOn: return TEXT("Turn on");
        case EVistaAffordance::TurnOff: return TEXT("Turn off");
        case EVistaAffordance::Pour: return TEXT("Pour");
        default: return TEXT("Unknown");
    }
}

FString PhaseLabel(EVistaActionPhase Phase)
{
    switch (Phase)
    {
        case EVistaActionPhase::Approach: return TEXT("APPROACHING");
        case EVistaActionPhase::Align: return TEXT("ALIGNING");
        case EVistaActionPhase::Animate: return TEXT("ANIMATING");
        case EVistaActionPhase::ContactCommit: return TEXT("CONTACT");
        case EVistaActionPhase::Complete: return TEXT("COMPLETE");
        case EVistaActionPhase::RollingBack: return TEXT("ROLLING BACK");
        case EVistaActionPhase::Failed: return TEXT("FAILED");
        case EVistaActionPhase::Idle:
        default:
            return TEXT("READY");
    }
}

FString ResultStatusLabel(const FVistaPlayerActionFeedback& Feedback)
{
    if (!Feedback.bTerminal)
    {
        return PhaseLabel(Feedback.Phase);
    }
    switch (Feedback.Status)
    {
        case EVistaInteractionStatus::Succeeded: return TEXT("COMPLETE");
        case EVistaInteractionStatus::Unsupported: return TEXT("UNSUPPORTED");
        case EVistaInteractionStatus::InvalidRequester: return TEXT("INVALID REQUESTER");
        case EVistaInteractionStatus::InvalidState: return TEXT("INVALID STATE");
        case EVistaInteractionStatus::Busy: return TEXT("BUSY");
        case EVistaInteractionStatus::Blocked: return TEXT("BLOCKED");
        case EVistaInteractionStatus::NotFound: return TEXT("NOT FOUND");
        case EVistaInteractionStatus::TimedOut: return TEXT("TIMED OUT");
        case EVistaInteractionStatus::RevisionMismatch: return TEXT("REVISION CHANGED");
        case EVistaInteractionStatus::Rejected:
        default:
            return TEXT("REJECTED");
    }
}

FLinearColor ResultStatusColor(const FVistaPlayerActionFeedback& Feedback)
{
    if (!Feedback.bTerminal)
    {
        return FLinearColor(0.78f, 0.61f, 0.32f, 1.0f);
    }
    return Feedback.Status == EVistaInteractionStatus::Succeeded
        ? FLinearColor(0.43f, 0.70f, 0.52f, 1.0f)
        : FLinearColor(0.82f, 0.35f, 0.30f, 1.0f);
}

FString PublicStateLabel(FName Key)
{
    FString Label = Key.ToString();
    Label.ReplaceInline(TEXT("_"), TEXT(" "));
    Label.ToLowerInline();
    if (!Label.IsEmpty())
    {
        Label[0] = FChar::ToUpper(Label[0]);
    }
    return Label;
}
} // namespace

void AVistaPlayableHomeHUD::DrawHUD()
{
    Super::DrawHUD();
    if (!Canvas || !PlayerOwner || !GEngine)
    {
        return;
    }
    const AVistaPlayableHomeCharacter* Character =
        Cast<AVistaPlayableHomeCharacter>(PlayerOwner->GetPawn());
    if (!IsValid(Character))
    {
        return;
    }

    UFont* Font = GEngine->GetSmallFont();
    if (!IsValid(Font))
    {
        return;
    }

    const float UiScale = FMath::Clamp(Canvas->ClipY / 1080.0f, 0.75f, 1.5f);
    const FLinearColor Panel(0.035f, 0.038f, 0.041f, 0.86f);
    const FLinearColor Primary(0.92f, 0.90f, 0.85f, 1.0f);
    const FLinearColor Muted(0.61f, 0.60f, 0.56f, 1.0f);
    const FLinearColor Accent(0.78f, 0.61f, 0.32f, 1.0f);

    // A restrained reticle keeps the interaction surface game-like without
    // competing with the world or exposing implementation details.
    const float ReticleSize = 4.0f * UiScale;
    const float ReticleX = Canvas->ClipX * 0.5f;
    const float ReticleY = Canvas->ClipY * 0.5f;
    DrawRect(FLinearColor(0.92f, 0.90f, 0.85f, 0.78f),
             ReticleX - ReticleSize * 0.5f,
             ReticleY - ReticleSize * 0.5f,
             ReticleSize, ReticleSize);
    if (Character->IsInspectionActive())
    {
        const float FocusRadius = 34.0f * UiScale;
        const float CornerLength = 11.0f * UiScale;
        const float Stroke = 2.0f * UiScale;
        for (const float XSign : {-1.0f, 1.0f})
        {
            for (const float YSign : {-1.0f, 1.0f})
            {
                const float CornerX = ReticleX + XSign * FocusRadius;
                const float CornerY = ReticleY + YSign * FocusRadius;
                DrawRect(Accent,
                         CornerX - (XSign < 0.0f ? 0.0f : CornerLength),
                         CornerY,
                         CornerLength,
                         Stroke);
                DrawRect(Accent,
                         CornerX,
                         CornerY - (YSign < 0.0f ? 0.0f : CornerLength),
                         Stroke,
                         CornerLength);
            }
        }
    }

    if (GetWorld())
    {
        const UVistaEventSubsystem* Events =
            GetWorld()->GetSubsystem<UVistaEventSubsystem>();
        if (IsValid(Events))
        {
            const EVistaEventStatus Status = Events->GetEventStatus();
            const FString Goal = CondenseGoal(Events->GetPublicGoal());
            const FString StatusLabel = ScenarioStatusLabel(Status);
            if (!Goal.IsEmpty() && !StatusLabel.IsEmpty())
            {
                const float Margin = 32.0f * UiScale;
                const float PanelWidth = FMath::Min(
                    620.0f * UiScale,
                    FMath::Max(280.0f * UiScale, Canvas->ClipX - Margin * 2.0f));
                const float PanelHeight = 78.0f * UiScale;
                DrawRect(Panel, Margin, Margin, PanelWidth, PanelHeight);
                DrawRect(Accent, Margin, Margin, 3.0f * UiScale, PanelHeight);
                DrawText(TEXT("OBJECTIVE"), Muted,
                         Margin + 18.0f * UiScale, Margin + 12.0f * UiScale,
                         Font, 0.82f * UiScale, false);
                DrawText(StatusLabel, ScenarioStatusColor(Status),
                         Margin + 112.0f * UiScale, Margin + 12.0f * UiScale,
                         Font, 0.82f * UiScale, false);
                DrawText(Goal, Primary,
                         Margin + 18.0f * UiScale, Margin + 39.0f * UiScale,
                         Font, UiScale, false);
            }
        }
    }

    const UVistaInteractionComponent* Interaction = Character->InteractionComponent;
    AActor* FocusedActor = IsValid(Interaction)
        ? Interaction->GetFocusedActor()
        : nullptr;
    if (IsValid(Character->PostureComponent) &&
        Character->PostureComponent->GetPostureState() == EVistaPostureState::Seated &&
        IsValid(Character->PostureComponent->GetActiveSeat()))
    {
        FocusedActor = Character->PostureComponent->GetActiveSeat();
    }
    const FString InteractionLabel = BuildInteractionLabel(
        *Character, FocusedActor);
    FString Prompt;
    if (Character->IsInspectionActive())
    {
        Prompt = TEXT("[I / ESC]  Exit inspection");
    }
    else if (!InteractionLabel.IsEmpty())
    {
        Prompt = FString::Printf(TEXT("[E]  %s"), *InteractionLabel);
        if (SupportsInspect(FocusedActor))
        {
            Prompt += TEXT("      [I]  Inspect");
        }
    }
    if (!Prompt.IsEmpty())
    {
        float TextWidth = 0.0f;
        float TextHeight = 0.0f;
        GetTextSize(Prompt, TextWidth, TextHeight, Font, UiScale);
        const float PanelWidth = FMath::Clamp(
            TextWidth + 46.0f * UiScale, 220.0f * UiScale, 760.0f * UiScale);
        const float PanelHeight = 44.0f * UiScale;
        const float PanelX = (Canvas->ClipX - PanelWidth) * 0.5f;
        const float PanelY = Canvas->ClipY - 76.0f * UiScale;
        DrawRect(Panel, PanelX, PanelY, PanelWidth, PanelHeight);
        DrawRect(Accent, PanelX, PanelY + PanelHeight - 2.0f * UiScale,
                 PanelWidth, 2.0f * UiScale);
        DrawText(Prompt, Primary,
                 PanelX + (PanelWidth - TextWidth) * 0.5f,
                 PanelY + (PanelHeight - TextHeight) * 0.5f,
                 Font, UiScale, false);
    }

    FVistaPlayerActionOption SelectedAction;
    if (!Character->IsInspectionActive() &&
        Character->GetSelectedPlayerAction(SelectedAction))
    {
        const FString SelectedLabel = BuildSelectedActionLabel(SelectedAction);
        const int32 ActionCount =
            Character->GetExecutablePlayerActions().Num();
        const int32 SelectedNumber =
            Character->GetSelectedPlayerActionIndex() + 1;
        const FString CycleHint = ActionCount > 1
            ? FString::Printf(
                TEXT("      [R / WHEEL]  SELECT  %d/%d"),
                SelectedNumber,
                ActionCount)
            : FString();
        const FString SelectorPrompt = FString::Printf(
            TEXT("[F]  %s%s"),
            *SelectedLabel,
            *CycleHint);
        float SelectorWidth = 0.0f;
        float SelectorHeight = 0.0f;
        GetTextSize(
            SelectorPrompt,
            SelectorWidth,
            SelectorHeight,
            Font,
            0.88f * UiScale);
        const float PanelWidth = FMath::Clamp(
            SelectorWidth + 46.0f * UiScale,
            260.0f * UiScale,
            820.0f * UiScale);
        const float PanelHeight = 38.0f * UiScale;
        const float PanelX = (Canvas->ClipX - PanelWidth) * 0.5f;
        const float PanelY = Canvas->ClipY - 120.0f * UiScale;
        DrawRect(Panel, PanelX, PanelY, PanelWidth, PanelHeight);
        DrawRect(Accent, PanelX, PanelY, 3.0f * UiScale, PanelHeight);
        DrawText(
            SelectorPrompt,
            Primary,
            PanelX + (PanelWidth - SelectorWidth) * 0.5f,
            PanelY + (PanelHeight - SelectorHeight) * 0.5f,
            Font,
            0.88f * UiScale,
            false);
    }

    const FVistaInspectionPresentation& Inspection =
        Character->GetInspectionPresentation();
    if (Inspection.bActive)
    {
        const float Margin = 32.0f * UiScale;
        const float CardWidth = FMath::Min(
            390.0f * UiScale,
            FMath::Max(260.0f * UiScale, Canvas->ClipX - Margin * 2.0f));
        const int32 StateRowCount = FMath::Min(
            Inspection.PublicState.Num(), 8);
        const float CardHeight = (150.0f + StateRowCount * 21.0f) * UiScale;
        const float CardX = Canvas->ClipX - Margin - CardWidth;
        const float CardY = 128.0f * UiScale;
        DrawRect(Panel, CardX, CardY, CardWidth, CardHeight);
        DrawRect(Accent, CardX, CardY, 3.0f * UiScale, CardHeight);

        const FString FriendlyTarget =
            FriendlyNameFromSemanticId(Inspection.SemanticId);
        DrawText(TEXT("INSPECTION"), Muted,
                 CardX + 18.0f * UiScale, CardY + 14.0f * UiScale,
                 Font, 0.76f * UiScale, false);
        DrawText(FriendlyTarget, Primary,
                 CardX + 18.0f * UiScale, CardY + 38.0f * UiScale,
                 Font, 1.12f * UiScale, false);
        DrawText(TEXT("SEMANTIC ID"), Muted,
                 CardX + 18.0f * UiScale, CardY + 69.0f * UiScale,
                 Font, 0.70f * UiScale, false);
        DrawText(Inspection.SemanticId, Primary,
                 CardX + 112.0f * UiScale, CardY + 69.0f * UiScale,
                 Font, 0.70f * UiScale, false);

        TArray<FString> AffordanceLabels;
        for (const EVistaAffordance Affordance : Inspection.Affordances)
        {
            AffordanceLabels.Add(AffordanceLabel(Affordance));
        }
        DrawText(TEXT("ACTIONS"), Muted,
                 CardX + 18.0f * UiScale, CardY + 94.0f * UiScale,
                 Font, 0.70f * UiScale, false);
        DrawText(FString::Join(AffordanceLabels, TEXT("  /  ")), Primary,
                 CardX + 86.0f * UiScale, CardY + 94.0f * UiScale,
                 Font, 0.70f * UiScale, false);
        DrawRect(Muted.CopyWithNewOpacity(0.28f),
                 CardX + 18.0f * UiScale, CardY + 120.0f * UiScale,
                 CardWidth - 36.0f * UiScale, 1.0f * UiScale);

        for (int32 Index = 0; Index < StateRowCount; ++Index)
        {
            const FVistaInspectionStateRow& StateRow =
                Inspection.PublicState[Index];
            const float RowY = CardY + (132.0f + Index * 21.0f) * UiScale;
            DrawText(PublicStateLabel(StateRow.Key), Muted,
                     CardX + 18.0f * UiScale, RowY,
                     Font, 0.74f * UiScale, false);
            DrawText(StateRow.Value, Primary,
                     CardX + 190.0f * UiScale, RowY,
                     Font, 0.74f * UiScale, false);
        }
    }

    if (Character->IsActionFeedbackVisible())
    {
        const FVistaPlayerActionFeedback& Feedback = Character->GetActionFeedback();
        const FString StatusLabel = ResultStatusLabel(Feedback);
        const FString CodeLabel = Feedback.Code.ToString().Left(56);
        const float Margin = 32.0f * UiScale;
        const float FeedbackWidth = 330.0f * UiScale;
        const float FeedbackHeight = 56.0f * UiScale;
        const float FeedbackX = Canvas->ClipX - Margin - FeedbackWidth;
        const float FeedbackY = Canvas->ClipY - 154.0f * UiScale;
        DrawRect(Panel, FeedbackX, FeedbackY, FeedbackWidth, FeedbackHeight);
        DrawRect(ResultStatusColor(Feedback), FeedbackX, FeedbackY,
                 3.0f * UiScale, FeedbackHeight);
        DrawText(StatusLabel, ResultStatusColor(Feedback),
                 FeedbackX + 16.0f * UiScale, FeedbackY + 9.0f * UiScale,
                 Font, 0.78f * UiScale, false);
        DrawText(CodeLabel, Primary,
                 FeedbackX + 16.0f * UiScale, FeedbackY + 31.0f * UiScale,
                 Font, 0.72f * UiScale, false);
    }

    const AVistaPickupActor* Held = Character->GetHeldPickup();
    if (IsValid(Held))
    {
        const float Margin = 32.0f * UiScale;
        const float PanelWidth = 220.0f * UiScale;
        const float PanelHeight = 54.0f * UiScale;
        const float PanelY = Canvas->ClipY - Margin - PanelHeight;
        DrawRect(Panel, Margin, PanelY, PanelWidth, PanelHeight);
        DrawText(TEXT("CARRYING"), Muted,
                 Margin + 14.0f * UiScale, PanelY + 8.0f * UiScale,
                 Font, 0.75f * UiScale, false);
        DrawText(FriendlyNameFromSemanticId(Held->SemanticId), Primary,
                 Margin + 14.0f * UiScale, PanelY + 28.0f * UiScale,
                 Font, 0.92f * UiScale, false);
        DrawText(TEXT("[Q] DROP"), Accent,
                 Margin + 142.0f * UiScale, PanelY + 28.0f * UiScale,
                 Font, 0.75f * UiScale, false);
    }
}
