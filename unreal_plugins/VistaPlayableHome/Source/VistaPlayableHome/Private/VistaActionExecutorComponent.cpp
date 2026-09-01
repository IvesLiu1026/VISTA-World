#include "VistaActionExecutorComponent.h"

#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Containers/StringConv.h"
#include "Engine/CollisionProfile.h"
#include "Engine/TargetPoint.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "HAL/PlatformMemory.h"
#include "VistaAnimationComponent.h"
#include "VistaEventSubsystem.h"
#include "VistaHomeNpcCharacter.h"
#include "VistaInteractable.h"
#include "VistaItemCarrier.h"
#include "VistaPickupActor.h"
#include "VistaPlayableHomeCharacter.h"
#include "VistaPlayableHomeRuntimeSubsystem.h"

namespace
{
constexpr const TCHAR* StableSemanticTagPrefix = TEXT("VistaSemanticId=");
constexpr const TCHAR* PlacementOwnerTagPrefix = TEXT("VistaOwner=");
constexpr const TCHAR* PlacementAnchorDelimiter = TEXT("/anchor.");
const FName RightHandSocket(TEXT("hand_r"));
const FName ProviderGripTag(TEXT("VistaProviderGripSocket"));
const FName ValidatedCarryAnchorTag(TEXT("VistaValidatedCarryAnchor"));
constexpr float MaximumContactDistanceCm = 300.0f;

EVistaNpcActionType AnimationTypeForPhysicalAffordance(
    const EVistaAffordance Affordance)
{
    switch (Affordance)
    {
    case EVistaAffordance::PickUp: return EVistaNpcActionType::PickUp;
    case EVistaAffordance::Place: return EVistaNpcActionType::Place;
    case EVistaAffordance::Drop: return EVistaNpcActionType::Drop;
    default: return EVistaNpcActionType::Wait;
    }
}

template <typename T>
bool ScalarBitsEqual(const T& Left, const T& Right)
{
    return FPlatformMemory::Memcmp(&Left, &Right, sizeof(T)) == 0;
}

bool VectorBitsEqual(const FVector& Left, const FVector& Right)
{
    return ScalarBitsEqual(Left.X, Right.X) &&
        ScalarBitsEqual(Left.Y, Right.Y) &&
        ScalarBitsEqual(Left.Z, Right.Z);
}

bool TransformBitsEqual(const FTransform& Left, const FTransform& Right)
{
    const FVector LeftTranslation = Left.GetTranslation();
    const FVector RightTranslation = Right.GetTranslation();
    const FVector LeftScale = Left.GetScale3D();
    const FVector RightScale = Right.GetScale3D();
    const FQuat LeftRotation = Left.GetRotation();
    const FQuat RightRotation = Right.GetRotation();
    return VectorBitsEqual(LeftTranslation, RightTranslation) &&
        VectorBitsEqual(LeftScale, RightScale) &&
        ScalarBitsEqual(LeftRotation.X, RightRotation.X) &&
        ScalarBitsEqual(LeftRotation.Y, RightRotation.Y) &&
        ScalarBitsEqual(LeftRotation.Z, RightRotation.Z) &&
        ScalarBitsEqual(LeftRotation.W, RightRotation.W);
}

void AppendUInt32(TArray<uint8>& Output, uint32 Value)
{
    Output.Add(static_cast<uint8>((Value >> 24) & 0xff));
    Output.Add(static_cast<uint8>((Value >> 16) & 0xff));
    Output.Add(static_cast<uint8>((Value >> 8) & 0xff));
    Output.Add(static_cast<uint8>(Value & 0xff));
}

void AppendUInt64(TArray<uint8>& Output, uint64 Value)
{
    for (int32 Shift = 56; Shift >= 0; Shift -= 8)
    {
        Output.Add(static_cast<uint8>((Value >> Shift) & 0xff));
    }
}

void AppendUtf8(TArray<uint8>& Output, const FString& Value)
{
    const FTCHARToUTF8 Converted(*Value);
    AppendUInt32(Output, static_cast<uint32>(Converted.Length()));
    Output.Append(
        reinterpret_cast<const uint8*>(Converted.Get()),
        Converted.Length());
}

FString LowerHex(const TArray<uint8>& Bytes)
{
    static constexpr TCHAR Digits[] = TEXT("0123456789abcdef");
    FString Result;
    Result.Reserve(Bytes.Num() * 2);
    for (uint8 Byte : Bytes)
    {
        Result.AppendChar(Digits[(Byte >> 4) & 0x0f]);
        Result.AppendChar(Digits[Byte & 0x0f]);
    }
    return Result;
}

bool HasCameraInAttachmentChain(const USceneComponent* Component)
{
    for (const USceneComponent* Current = Component;
         IsValid(Current);
         Current = Current->GetAttachParent())
    {
        if (Current->IsA<UCameraComponent>())
        {
            return true;
        }
    }
    return false;
}

bool IsLowerAsciiAlpha(const TCHAR Character)
{
    return Character >= TEXT('a') && Character <= TEXT('z');
}

bool IsAsciiDigit(const TCHAR Character)
{
    return Character >= TEXT('0') && Character <= TEXT('9');
}

bool IsStableAnchorSemanticId(const FString& Value)
{
    if (Value.IsEmpty() || Value.Len() > 240 || !IsLowerAsciiAlpha(Value[0]) ||
        Value.Contains(TEXT("#")))
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        if (!(IsLowerAsciiAlpha(Character) || IsAsciiDigit(Character) ||
              Character == TEXT('.') || Character == TEXT('_') ||
              Character == TEXT('/') || Character == TEXT('-')))
        {
            return false;
        }
    }
    const int32 DelimiterIndex = Value.Find(
        PlacementAnchorDelimiter, ESearchCase::CaseSensitive, ESearchDir::FromStart);
    if (DelimiterIndex <= 0 ||
        DelimiterIndex + FCString::Strlen(PlacementAnchorDelimiter) >= Value.Len() ||
        Value.Find(PlacementAnchorDelimiter, ESearchCase::CaseSensitive,
                   ESearchDir::FromStart, DelimiterIndex + 1) != INDEX_NONE)
    {
        return false;
    }
    const FString OwnerSemanticId = Value.Left(DelimiterIndex);
    const FString AnchorId = Value.Mid(
        DelimiterIndex + FCString::Strlen(PlacementAnchorDelimiter));
    if (!OwnerSemanticId.Contains(TEXT("/entity."), ESearchCase::CaseSensitive) ||
        AnchorId.IsEmpty() || !IsLowerAsciiAlpha(AnchorId[0]))
    {
        return false;
    }
    for (const TCHAR Character : AnchorId)
    {
        if (!(IsLowerAsciiAlpha(Character) || IsAsciiDigit(Character) ||
              Character == TEXT('_')))
        {
            return false;
        }
    }
    return true;
}

bool StateMatchesPhysicalEffect(
    const FVistaEntityRuntimeState& State,
    const FVistaPhysicalActionRequest& Request)
{
    const FString* Held = State.Values.Find(TEXT("held"));
    const FString* HeldBy = State.Values.Find(TEXT("held_by"));
    const FString* PlacedAt = State.Values.Find(TEXT("placed_at"));
    const bool bHeld = Held != nullptr &&
        Held->Equals(TEXT("true"), ESearchCase::CaseSensitive);
    switch (Request.Affordance)
    {
    case EVistaAffordance::PickUp:
        return bHeld && HeldBy != nullptr &&
            *HeldBy == Request.RequesterSemanticId && PlacedAt == nullptr;
    case EVistaAffordance::Drop:
        return Held != nullptr && !bHeld &&
            (HeldBy == nullptr || HeldBy->IsEmpty()) && PlacedAt == nullptr;
    case EVistaAffordance::Place:
        return Held != nullptr && !bHeld &&
            (HeldBy == nullptr || HeldBy->IsEmpty()) && PlacedAt != nullptr &&
            *PlacedAt == Request.PlacementAnchorSemanticId;
    default:
        return false;
    }
}

bool PhysicalSnapshotMatchesEffect(
    const FVistaPickupPhysicalStateSnapshot& Snapshot,
    const FVistaPhysicalActionRequest& Request,
    const AVistaPickupActor* Pickup,
    const USceneComponent* CarryAnchor,
    const USceneComponent* PlacementAnchor)
{
    const USceneComponent* CurrentParent =
        IsValid(Pickup) && IsValid(Pickup->GetRootComponent())
            ? Pickup->GetRootComponent()->GetAttachParent() : nullptr;
    switch (Request.Affordance)
    {
    case EVistaAffordance::PickUp:
        return Snapshot.bHeld && !Snapshot.bSimulatePhysics &&
            Snapshot.bHasAttachmentParent &&
            IsValid(CarryAnchor) && CurrentParent == CarryAnchor &&
            IsValid(Pickup) && Pickup->GetCarrier() == Request.Requester &&
            Snapshot.CarrierSemanticId == Request.RequesterSemanticId &&
            Snapshot.InventoryCarrierSemanticId == Request.RequesterSemanticId &&
            Snapshot.bInventorySlotOccupied &&
            Snapshot.InventoryItemSemanticId == Request.TargetSemanticId &&
            Snapshot.AttachmentParentOwnerSemanticId ==
                Request.RequesterSemanticId &&
            Snapshot.AttachmentParentComponentName == CarryAnchor->GetFName() &&
            Snapshot.AttachmentSocketName.IsNone() &&
            TransformBitsEqual(
                Snapshot.AttachmentRelativeTransform,
                FTransform::Identity) &&
            Snapshot.CollisionEnabled ==
                static_cast<uint8>(ECollisionEnabled::NoCollision) &&
            Snapshot.CollisionProfileName ==
                UCollisionProfile::NoCollision_ProfileName &&
            VectorBitsEqual(Snapshot.LinearVelocity, FVector::ZeroVector) &&
            VectorBitsEqual(
                Snapshot.AngularVelocityDegrees, FVector::ZeroVector) &&
            Snapshot.PlacedAtSemanticId.IsEmpty() &&
            Snapshot.ContainedInSemanticId.IsEmpty();
    case EVistaAffordance::Drop:
        return !Snapshot.bHeld && Snapshot.bSimulatePhysics &&
            !Snapshot.bHasAttachmentParent && CurrentParent == nullptr &&
            Snapshot.AttachmentParentOwnerSemanticId.IsEmpty() &&
            Snapshot.AttachmentParentComponentName.IsNone() &&
            Snapshot.CarrierSemanticId.IsEmpty() &&
            Snapshot.InventoryCarrierSemanticId == Request.RequesterSemanticId &&
            !Snapshot.bInventorySlotOccupied &&
            Snapshot.InventoryItemSemanticId.IsEmpty() &&
            Snapshot.AttachmentSocketName.IsNone() &&
            TransformBitsEqual(
                Snapshot.AttachmentRelativeTransform,
                FTransform::Identity) &&
            Snapshot.CollisionEnabled ==
                static_cast<uint8>(ECollisionEnabled::QueryAndPhysics) &&
            Snapshot.CollisionProfileName ==
                UCollisionProfile::PhysicsActor_ProfileName &&
            VectorBitsEqual(Snapshot.LinearVelocity, Request.ReleaseVelocity) &&
            VectorBitsEqual(
                Snapshot.AngularVelocityDegrees, FVector::ZeroVector) &&
            Snapshot.PlacedAtSemanticId.IsEmpty() &&
            Snapshot.ContainedInSemanticId.IsEmpty();
    case EVistaAffordance::Place:
        return !Snapshot.bHeld && !Snapshot.bSimulatePhysics &&
            !Snapshot.bHasAttachmentParent && CurrentParent == nullptr &&
            Snapshot.AttachmentParentOwnerSemanticId.IsEmpty() &&
            Snapshot.AttachmentParentComponentName.IsNone() &&
            IsValid(PlacementAnchor) &&
            TransformBitsEqual(
                Snapshot.WorldTransform,
                PlacementAnchor->GetComponentTransform()) &&
            Snapshot.CarrierSemanticId.IsEmpty() &&
            Snapshot.InventoryCarrierSemanticId == Request.RequesterSemanticId &&
            !Snapshot.bInventorySlotOccupied &&
            Snapshot.InventoryItemSemanticId.IsEmpty() &&
            Snapshot.AttachmentSocketName.IsNone() &&
            TransformBitsEqual(
                Snapshot.AttachmentRelativeTransform,
                FTransform::Identity) &&
            Snapshot.CollisionEnabled ==
                static_cast<uint8>(ECollisionEnabled::QueryAndPhysics) &&
            Snapshot.CollisionProfileName ==
                UCollisionProfile::PhysicsActor_ProfileName &&
            VectorBitsEqual(Snapshot.LinearVelocity, FVector::ZeroVector) &&
            VectorBitsEqual(
                Snapshot.AngularVelocityDegrees, FVector::ZeroVector) &&
            Snapshot.PlacedAtSemanticId == Request.PlacementAnchorSemanticId &&
            Snapshot.ContainedInSemanticId.IsEmpty();
    default:
        return false;
    }
}

bool RuntimeStatesEquivalent(
    const FVistaEntityRuntimeState& Left,
    const FVistaEntityRuntimeState& Right)
{
    if (Left.SemanticId != Right.SemanticId ||
        !TransformBitsEqual(Left.Transform, Right.Transform) ||
        Left.bHidden != Right.bHidden || Left.bPortable != Right.bPortable ||
        Left.Values.Num() != Right.Values.Num())
    {
        return false;
    }
    for (const TPair<FName, FString>& Pair : Left.Values)
    {
        const FString* RightValue = Right.Values.Find(Pair.Key);
        if (RightValue == nullptr || *RightValue != Pair.Value)
        {
            return false;
        }
    }
    return true;
}
} // namespace

UVistaActionExecutorComponent::UVistaActionExecutorComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
}

bool UVistaActionExecutorComponent::IsPhysicalAffordance(EVistaAffordance Affordance)
{
    return Affordance == EVistaAffordance::PickUp ||
        Affordance == EVistaAffordance::Drop ||
        Affordance == EVistaAffordance::Place;
}

FString UVistaActionExecutorComponent::SemanticIdForActor(const AActor* Actor)
{
    if (!IsValid(Actor))
    {
        return FString();
    }
    if (const AVistaPlayableHomeCharacter* Player =
            Cast<AVistaPlayableHomeCharacter>(Actor))
    {
        return Player->SemanticId;
    }
    if (const AVistaHomeNpcCharacter* Npc = Cast<AVistaHomeNpcCharacter>(Actor))
    {
        return Npc->SemanticId;
    }
    if (Actor->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        return IVistaInteractable::Execute_VistaGetSemanticId(
            const_cast<AActor*>(Actor));
    }
    FString Match;
    for (const FName& Tag : Actor->Tags)
    {
        const FString Value = Tag.ToString();
        if (Value.StartsWith(StableSemanticTagPrefix, ESearchCase::CaseSensitive))
        {
            const FString Candidate =
                Value.RightChop(FCString::Strlen(StableSemanticTagPrefix));
            if (!Match.IsEmpty() && Match != Candidate)
            {
                return FString();
            }
            Match = Candidate;
        }
    }
    return Match;
}

bool UVistaActionExecutorComponent::StableAnchorIdentity(
    const ATargetPoint* Anchor,
    FString& OutOwnerSemanticId,
    FString& OutAnchorSemanticId)
{
    OutOwnerSemanticId.Reset();
    OutAnchorSemanticId.Reset();
    if (!IsValid(Anchor) || !IsValid(Anchor->GetRootComponent()))
    {
        return false;
    }
    for (const FName& Tag : Anchor->Tags)
    {
        const FString Value = Tag.ToString();
        if (Value.StartsWith(StableSemanticTagPrefix, ESearchCase::CaseSensitive))
        {
            const FString Candidate =
                Value.RightChop(FCString::Strlen(StableSemanticTagPrefix));
            if (!IsStableAnchorSemanticId(Candidate) ||
                (!OutAnchorSemanticId.IsEmpty() && OutAnchorSemanticId != Candidate))
            {
                return false;
            }
            OutAnchorSemanticId = Candidate;
        }
        else if (Value.StartsWith(PlacementOwnerTagPrefix, ESearchCase::CaseSensitive))
        {
            const FString Candidate =
                Value.RightChop(FCString::Strlen(PlacementOwnerTagPrefix));
            if (Candidate.IsEmpty() ||
                (!OutOwnerSemanticId.IsEmpty() && OutOwnerSemanticId != Candidate))
            {
                return false;
            }
            OutOwnerSemanticId = Candidate;
        }
    }
    if (OutOwnerSemanticId.IsEmpty() || OutAnchorSemanticId.IsEmpty())
    {
        return false;
    }
    const int32 DelimiterIndex = OutAnchorSemanticId.Find(
        PlacementAnchorDelimiter, ESearchCase::CaseSensitive, ESearchDir::FromStart);
    return DelimiterIndex > 0 &&
        OutAnchorSemanticId.Left(DelimiterIndex) == OutOwnerSemanticId;
}

USceneComponent* UVistaActionExecutorComponent::ResolveStablePlacementAnchor(
    AActor* Requester,
    AActor* FocusedOwner,
    FName& OutCode,
    FString& OutSemanticId)
{
    OutSemanticId.Reset();
    const FString OwnerSemanticId = SemanticIdForActor(FocusedOwner);
    if (!IsValid(Requester) || !IsValid(FocusedOwner) || OwnerSemanticId.IsEmpty() ||
        !IsValid(FocusedOwner->GetWorld()))
    {
        OutCode = TEXT("PLACEMENT_OWNER_INVALID");
        return nullptr;
    }

    struct FCandidate final
    {
        ATargetPoint* Anchor = nullptr;
        FString SemanticId;
        double DistanceSquared = 0.0;
    };
    TArray<FCandidate> Candidates;
    const FName RequiredOwnerTag(*(FString(PlacementOwnerTagPrefix) + OwnerSemanticId));
    for (TActorIterator<ATargetPoint> It(FocusedOwner->GetWorld()); It; ++It)
    {
        FString TaggedOwner;
        FString AnchorSemanticId;
        if (!It->ActorHasTag(RequiredOwnerTag) ||
            !StableAnchorIdentity(*It, TaggedOwner, AnchorSemanticId) ||
            TaggedOwner != OwnerSemanticId)
        {
            continue;
        }
        int32 IdentityMatches = 0;
        const FName StableTag(*(FString(StableSemanticTagPrefix) + AnchorSemanticId));
        for (TActorIterator<ATargetPoint> DuplicateIt(FocusedOwner->GetWorld());
             DuplicateIt; ++DuplicateIt)
        {
            IdentityMatches += DuplicateIt->ActorHasTag(StableTag) ? 1 : 0;
        }
        if (IdentityMatches != 1)
        {
            OutCode = TEXT("PLACEMENT_ANCHOR_IDENTITY_AMBIGUOUS");
            return nullptr;
        }
        FCandidate Candidate;
        Candidate.Anchor = *It;
        Candidate.SemanticId = MoveTemp(AnchorSemanticId);
        Candidate.DistanceSquared = FVector::DistSquared(
            Requester->GetActorLocation(), It->GetActorLocation());
        Candidates.Add(MoveTemp(Candidate));
    }
    if (Candidates.IsEmpty())
    {
        OutCode = TEXT("PLACEMENT_TARGET_POINT_NOT_FOUND");
        return nullptr;
    }
    Candidates.Sort([](const FCandidate& Left, const FCandidate& Right)
    {
        if (!FMath::IsNearlyEqual(Left.DistanceSquared, Right.DistanceSquared, 0.01))
        {
            return Left.DistanceSquared < Right.DistanceSquared;
        }
        return Left.SemanticId < Right.SemanticId;
    });
    OutSemanticId = Candidates[0].SemanticId;
    OutCode = TEXT("PLACEMENT_TARGET_POINT_RESOLVED");
    return Candidates[0].Anchor->GetRootComponent();
}

bool UVistaActionExecutorComponent::IsCarryAnchorSafe(
    const AActor* Requester,
    const USceneComponent* Anchor)
{
    if (!IsValid(Requester) || !IsValid(Anchor) || Anchor->GetOwner() != Requester ||
        HasCameraInAttachmentChain(Anchor))
    {
        return false;
    }
    const USceneComponent* Parent = Anchor->GetAttachParent();
    if (!IsValid(Parent) || Parent->GetOwner() != Requester)
    {
        return false;
    }
    int32 ProviderGripMatches = 0;
    bool bExactProviderGrip = false;
    TArray<USceneComponent*> Components;
    Requester->GetComponents<USceneComponent>(Components);
    for (const USceneComponent* Component : Components)
    {
        if (IsValid(Component) && Component != Anchor &&
            Component->GetOwner() == Requester &&
            Component->ComponentHasTag(ProviderGripTag) &&
            !HasCameraInAttachmentChain(Component))
        {
            ++ProviderGripMatches;
            bExactProviderGrip = Component == Parent;
        }
    }
    const bool bProviderGrip =
        ProviderGripMatches == 1 && bExactProviderGrip;
    const USkeletalMeshComponent* ParentMesh =
        Cast<USkeletalMeshComponent>(Parent);
    const ACharacter* Character = Cast<ACharacter>(Requester);
    const bool bMannyRightHand = IsValid(Character) &&
        IsValid(ParentMesh) &&
        ParentMesh == Character->GetMesh() &&
        ParentMesh->DoesSocketExist(RightHandSocket) &&
        Anchor->GetAttachSocketName() == RightHandSocket;
    return (bProviderGrip || bMannyRightHand) &&
        Anchor->ComponentHasTag(ValidatedCarryAnchorTag);
}

USceneComponent* UVistaActionExecutorComponent::PrepareCarryAnchor(
    AActor* Requester,
    FName& OutCode)
{
    if (!IsValid(Requester) ||
        !Requester->GetClass()->ImplementsInterface(UVistaItemCarrier::StaticClass()))
    {
        OutCode = TEXT("CARRIER_REQUIRED");
        return nullptr;
    }
    USceneComponent* Anchor = IVistaItemCarrier::Execute_VistaGetCarryAnchor(Requester);
    if (!IsValid(Anchor) || Anchor->GetOwner() != Requester)
    {
        OutCode = TEXT("CARRY_ANCHOR_INVALID");
        return nullptr;
    }
    if (IsCarryAnchorSafe(Requester, Anchor))
    {
        OutCode = TEXT("CARRY_ANCHOR_READY");
        return Anchor;
    }
    // A constructor tag is only an intent until the local mesh/provider contract
    // has been revalidated. Never leave stale validation on a failed client path.
    Anchor->ComponentTags.Remove(ValidatedCarryAnchorTag);
    if (HasCameraInAttachmentChain(Anchor))
    {
        Anchor->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
    }

    USceneComponent* ProviderGrip = nullptr;
    TArray<USceneComponent*> Components;
    Requester->GetComponents<USceneComponent>(Components);
    for (USceneComponent* Component : Components)
    {
        if (IsValid(Component) && Component != Anchor &&
            Component->GetOwner() == Requester &&
            Component->ComponentHasTag(ProviderGripTag) &&
            !HasCameraInAttachmentChain(Component))
        {
            if (ProviderGrip != nullptr)
            {
                OutCode = TEXT("PROVIDER_GRIP_AMBIGUOUS");
                return nullptr;
            }
            ProviderGrip = Component;
        }
    }

    bool bAttached = false;
    if (IsValid(ProviderGrip))
    {
        bAttached = Anchor->AttachToComponent(
            ProviderGrip, FAttachmentTransformRules::SnapToTargetNotIncludingScale);
    }
    else if (ACharacter* Character = Cast<ACharacter>(Requester))
    {
        USkeletalMeshComponent* Mesh = Character->GetMesh();
        if (!IsValid(Mesh) || !Mesh->DoesSocketExist(RightHandSocket))
        {
            OutCode = TEXT("RIGHT_HAND_SOCKET_UNAVAILABLE");
            return nullptr;
        }
        bAttached = Anchor->AttachToComponent(
            Mesh,
            FAttachmentTransformRules::SnapToTargetNotIncludingScale,
            RightHandSocket);
    }
    if (!bAttached)
    {
        OutCode = TEXT("CARRY_ANCHOR_ATTACH_FAILED");
        return nullptr;
    }
    Anchor->ComponentTags.AddUnique(ValidatedCarryAnchorTag);
    if (!IsCarryAnchorSafe(Requester, Anchor))
    {
        Anchor->ComponentTags.Remove(ValidatedCarryAnchorTag);
        OutCode = TEXT("CARRY_ANCHOR_VALIDATION_FAILED");
        return nullptr;
    }
    OutCode = TEXT("CARRY_ANCHOR_READY");
    return Anchor;
}

FString UVistaActionExecutorComponent::CanonicalRequestHex(
    const FVistaPhysicalActionRequest& Request)
{
    const FString RequesterId = Request.RequesterSemanticId.IsEmpty()
        ? SemanticIdForActor(Request.Requester) : Request.RequesterSemanticId;
    const FString TargetId = Request.TargetSemanticId.IsEmpty()
        ? SemanticIdForActor(Request.Target) : Request.TargetSemanticId;
    const FString PlacementOwnerId = SemanticIdForActor(Request.PlacementOwner);
    FString PlacementAnchorId = Request.PlacementAnchorSemanticId;
    if (PlacementAnchorId.IsEmpty() && IsValid(Request.PlacementAnchor))
    {
        if (const ATargetPoint* Anchor =
                Cast<ATargetPoint>(Request.PlacementAnchor->GetOwner()))
        {
            FString TaggedOwner;
            StableAnchorIdentity(Anchor, TaggedOwner, PlacementAnchorId);
        }
    }

    TArray<uint8> Bytes;
    Bytes.Reserve(256);
    AppendUtf8(Bytes, TEXT("vista.physical-command/v1"));
    AppendUtf8(Bytes, RequesterId);
    AppendUtf8(Bytes, TargetId);
    Bytes.Add(static_cast<uint8>(Request.Affordance));
    AppendUtf8(Bytes, PlacementOwnerId);
    AppendUtf8(Bytes, PlacementAnchorId);
    AppendUtf8(Bytes, Request.ExpectedRevision.ToString());
    AppendUInt32(Bytes, static_cast<uint32>(Request.SessionGeneration));

    uint32 TimeoutBits = 0;
    FPlatformMemory::Memcpy(
        &TimeoutBits, &Request.TimeoutSeconds, sizeof(TimeoutBits));
    AppendUInt32(Bytes, TimeoutBits);
    for (double Component : {
             static_cast<double>(Request.ReleaseVelocity.X),
             static_cast<double>(Request.ReleaseVelocity.Y),
             static_cast<double>(Request.ReleaseVelocity.Z)})
    {
        uint64 ComponentBits = 0;
        FPlatformMemory::Memcpy(&ComponentBits, &Component, sizeof(ComponentBits));
        AppendUInt64(Bytes, ComponentBits);
    }
    Bytes.Add(Request.bCommitSessionGenerationOnSuccess ? 1 : 0);
    return LowerHex(Bytes);
}

void UVistaActionExecutorComponent::SetRejectedRecord(
    const FVistaPhysicalActionRequest& Request,
    FName Code,
    FVistaActionTransactionRecord& OutRecord)
{
    OutRecord = FVistaActionTransactionRecord();
    OutRecord.CommandId = Request.CommandId;
    OutRecord.Affordance = Request.Affordance;
    OutRecord.RequesterSemanticId = Request.RequesterSemanticId.IsEmpty()
        ? SemanticIdForActor(Request.Requester) : Request.RequesterSemanticId;
    OutRecord.TargetSemanticId = Request.TargetSemanticId.IsEmpty()
        ? SemanticIdForActor(Request.Target) : Request.TargetSemanticId;
    OutRecord.PlacementAnchorSemanticId = Request.PlacementAnchorSemanticId;
    OutRecord.Status = EVistaActionTransactionStatus::Failed;
    OutRecord.Phase = EVistaActionPhase::Idle;
    OutRecord.Code = Code;
    OutRecord.SessionGeneration = Request.SessionGeneration;
}

bool UVistaActionExecutorComponent::CapturePickupPhysicalState(
    const AVistaPickupActor* Pickup,
    const AActor* InventoryCarrier,
    FVistaPickupPhysicalStateSnapshot& OutSnapshot)
{
    if (!IsValid(Pickup))
    {
        return false;
    }
    const FVistaTrustedPhysicalRestoreToken Token;
    USceneComponent* AttachmentParent = nullptr;
    AActor* Carrier = nullptr;
    EVistaPickupDisposition Disposition = EVistaPickupDisposition::Free;
    if (!Pickup->CapturePhysicalStateTrusted(
        OutSnapshot,
        AttachmentParent,
        Carrier,
        Disposition,
        Token))
    {
        return false;
    }
    if (IsValid(InventoryCarrier))
    {
        if (!InventoryCarrier->GetClass()->ImplementsInterface(
                UVistaItemCarrier::StaticClass()))
        {
            return false;
        }
        OutSnapshot.InventoryCarrierSemanticId =
            SemanticIdForActor(InventoryCarrier);
        AActor* InventoryItem = IVistaItemCarrier::Execute_VistaGetHeldItem(
            const_cast<AActor*>(InventoryCarrier));
        OutSnapshot.bInventorySlotOccupied = IsValid(InventoryItem);
        OutSnapshot.InventoryItemSemanticId = SemanticIdForActor(InventoryItem);
        if (OutSnapshot.InventoryCarrierSemanticId.IsEmpty() ||
            (OutSnapshot.bInventorySlotOccupied &&
             OutSnapshot.InventoryItemSemanticId.IsEmpty()))
        {
            return false;
        }
    }
    return true;
}

bool UVistaActionExecutorComponent::PhysicalSnapshotsEquivalent(
    const FVistaPickupPhysicalStateSnapshot& Left,
    const FVistaPickupPhysicalStateSnapshot& Right)
{
    return TransformBitsEqual(Left.WorldTransform, Right.WorldTransform) &&
        Left.bSimulatePhysics == Right.bSimulatePhysics &&
        Left.CollisionEnabled == Right.CollisionEnabled &&
        Left.CollisionProfileName == Right.CollisionProfileName &&
        VectorBitsEqual(Left.LinearVelocity, Right.LinearVelocity) &&
        VectorBitsEqual(
            Left.AngularVelocityDegrees, Right.AngularVelocityDegrees) &&
        Left.bHasAttachmentParent == Right.bHasAttachmentParent &&
        Left.AttachmentParentOwnerSemanticId ==
            Right.AttachmentParentOwnerSemanticId &&
        Left.AttachmentParentComponentName ==
            Right.AttachmentParentComponentName &&
        Left.AttachmentSocketName == Right.AttachmentSocketName &&
        TransformBitsEqual(
            Left.AttachmentRelativeTransform,
            Right.AttachmentRelativeTransform) &&
        Left.bHeld == Right.bHeld &&
        Left.CarrierSemanticId == Right.CarrierSemanticId &&
        Left.InventoryCarrierSemanticId ==
            Right.InventoryCarrierSemanticId &&
        Left.bInventorySlotOccupied == Right.bInventorySlotOccupied &&
        Left.InventoryItemSemanticId == Right.InventoryItemSemanticId &&
        Left.PlacedAtSemanticId == Right.PlacedAtSemanticId &&
        Left.ContainedInSemanticId == Right.ContainedInSemanticId;
}

bool UVistaActionExecutorComponent::RestoreAndVerifyBeforePhysicalState(
    FName& OutCode)
{
    if (!ActiveAction.IsSet() ||
        !ActiveAction->Record.bHasBeforeState ||
        !ActiveAction->Record.bHasBeforePhysicalState)
    {
        OutCode = TEXT("ROLLBACK_SNAPSHOT_MISSING");
        return false;
    }
    AVistaPickupActor* Pickup =
        Cast<AVistaPickupActor>(ActiveAction->Target.Get());
    if (!IsValid(Pickup) || !IsValid(Pickup->Mesh) ||
        !IsValid(Pickup->GetRootComponent()))
    {
        OutCode = TEXT("ROLLBACK_TARGET_LOST");
        return false;
    }
    const FVistaPickupPhysicalStateSnapshot& Before =
        ActiveAction->Record.BeforePhysicalState;
    if (Before.bSimulatePhysics && Before.bHasAttachmentParent)
    {
        OutCode = TEXT("ROLLBACK_SNAPSHOT_PHYSICS_ATTACHMENT_CONFLICT");
        return false;
    }

    const FVistaTrustedPhysicalRestoreToken RestoreToken;
    const FVistaInteractionResult RestoreResult =
        Pickup->RestorePhysicalStateTrusted(
            ActiveAction->Record.BeforeState,
            &Before,
            ActiveAction->BeforeAttachmentParent.Get(),
            ActiveAction->BeforeCarrier.Get(),
            RestoreToken);
    if (!RestoreResult.IsSuccess())
    {
        OutCode = RestoreResult.Code.IsNone()
            ? FName(TEXT("ROLLBACK_TRUSTED_RESTORE_FAILED"))
            : RestoreResult.Code;
        return false;
    }

    USceneComponent* Root = Pickup->GetRootComponent();

    ActiveAction->Record.AfterState =
        IVistaInteractable::Execute_VistaGetRuntimeState(Pickup);
    ActiveAction->Record.bHasAfterState = true;
    ActiveAction->Record.bHasAfterPhysicalState = CapturePickupPhysicalState(
        Pickup,
        ActiveAction->Requester.Get(),
        ActiveAction->Record.AfterPhysicalState);
    const USceneComponent* CurrentParent = Root->GetAttachParent();
    const AActor* CurrentCarrier = Pickup->GetCarrier();
    AActor* Requester = ActiveAction->Requester.Get();
    const AActor* CurrentRequesterInventoryItem = IsValid(Requester)
        ? IVistaItemCarrier::Execute_VistaGetHeldItem(Requester)
        : nullptr;
    const bool bExactParent = Before.bHasAttachmentParent
        ? CurrentParent == ActiveAction->BeforeAttachmentParent.Get()
        : CurrentParent == nullptr;
    const bool bExactCarrier = Before.bHeld
        ? CurrentCarrier == ActiveAction->BeforeCarrier.Get()
        : CurrentCarrier == nullptr;
    const bool bExactRequesterInventory = IsValid(Requester) &&
        CurrentRequesterInventoryItem ==
            ActiveAction->BeforeRequesterInventoryItem.Get();
    const EVistaPickupDisposition BeforeDisposition = Before.bHeld
        ? EVistaPickupDisposition::Held
        : !Before.ContainedInSemanticId.IsEmpty()
            ? EVistaPickupDisposition::Contained
        : Before.PlacedAtSemanticId.IsEmpty()
            ? EVistaPickupDisposition::Free
            : EVistaPickupDisposition::Placed;
    const bool bExactPhysicalState = Pickup->MatchesPhysicalStateTrusted(
        Before,
        ActiveAction->BeforeAttachmentParent.Get(),
        ActiveAction->BeforeCarrier.Get(),
        BeforeDisposition,
        RestoreToken);
    if (!ActiveAction->Record.bHasAfterPhysicalState || !bExactParent ||
        !bExactCarrier || !bExactRequesterInventory ||
        !bExactPhysicalState ||
        !RuntimeStatesEquivalent(
            ActiveAction->Record.AfterState,
            ActiveAction->Record.BeforeState) ||
        !PhysicalSnapshotsEquivalent(
            ActiveAction->Record.AfterPhysicalState,
            ActiveAction->Record.BeforePhysicalState))
    {
        OutCode = TEXT("ROLLBACK_FULL_STATE_MISMATCH");
        return false;
    }
    OutCode = TEXT("ROLLBACK_FULL_STATE_RESTORED");
    return true;
}

bool UVistaActionExecutorComponent::RejectNewRequest(
    const FVistaPhysicalActionRequest& SignatureRequest,
    const FVistaPhysicalActionRequest& EvidenceRequest,
    FName Code,
    FVistaActionTransactionRecord& OutRecord)
{
    SetRejectedRecord(EvidenceRequest, Code, OutRecord);
    if (!SignatureRequest.CommandId.IsNone() && IsValid(GetWorld()))
    {
        if (UVistaPlayableHomeRuntimeSubsystem* Runtime =
                GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>())
        {
            Runtime->PublishPhysicalCommand(
                SignatureRequest.CommandId,
                CanonicalRequestHex(SignatureRequest),
                this,
                OutRecord,
                true);
        }
    }
    return false;
}

bool UVistaActionExecutorComponent::TryReplayPhysicalInteraction(
    const FVistaPhysicalActionRequest& Request,
    FVistaActionTransactionRecord& OutRecord,
    bool& bOutCommandKnown) const
{
    check(IsInGameThread());
    bOutCommandKnown = false;
    if (Request.CommandId.IsNone() || !IsValid(GetWorld()))
    {
        return false;
    }
    const UVistaPlayableHomeRuntimeSubsystem* Runtime =
        GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>();
    if (!IsValid(Runtime))
    {
        return false;
    }
    const EVistaPhysicalCommandClaimOutcome Outcome =
        Runtime->TryReplayPhysicalCommand(
            Request.CommandId, CanonicalRequestHex(Request), OutRecord);
    if (Outcome == EVistaPhysicalCommandClaimOutcome::Replay)
    {
        bOutCommandKnown = true;
        return true;
    }
    if (Outcome == EVistaPhysicalCommandClaimOutcome::Collision)
    {
        bOutCommandKnown = true;
        SetRejectedRecord(Request, TEXT("COMMAND_ID_COLLISION"), OutRecord);
    }
    return false;
}

bool UVistaActionExecutorComponent::BeginPhysicalInteraction(
    const FVistaPhysicalActionRequest& InputRequest,
    FVistaActionTransactionRecord& OutRecord)
{
    return BeginPhysicalInteractionImpl(InputRequest, OutRecord, false);
}

#if WITH_DEV_AUTOMATION_TESTS
bool UVistaActionExecutorComponent::BeginPhysicalInteractionForDevAutomation(
    const FVistaPhysicalActionRequest& InputRequest,
    FVistaActionTransactionRecord& OutRecord)
{
    return BeginPhysicalInteractionImpl(InputRequest, OutRecord, true);
}
#endif

bool UVistaActionExecutorComponent::BeginPhysicalInteractionImpl(
    const FVistaPhysicalActionRequest& InputRequest,
    FVistaActionTransactionRecord& OutRecord,
    const bool bDevAutomationBypassesAnimationReadiness)
{
    check(IsInGameThread());
    if (InputRequest.CommandId.IsNone())
    {
        SetRejectedRecord(InputRequest, TEXT("COMMAND_ID_REQUIRED"), OutRecord);
        return false;
    }
    UVistaPlayableHomeRuntimeSubsystem* Runtime = IsValid(GetWorld())
        ? GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>() : nullptr;
    if (!IsValid(Runtime))
    {
        SetRejectedRecord(InputRequest, TEXT("ACTION_LEDGER_UNAVAILABLE"), OutRecord);
        return false;
    }
    FVistaActionTransactionRecord ClaimedRecord;
    SetRejectedRecord(InputRequest, TEXT("ACTION_CLAIMED"), ClaimedRecord);
    ClaimedRecord.Status = EVistaActionTransactionStatus::Running;
    const FString CanonicalRequest = CanonicalRequestHex(InputRequest);
    const EVistaPhysicalCommandClaimOutcome Claim = Runtime->ClaimPhysicalCommand(
        InputRequest.CommandId,
        CanonicalRequest,
        this,
        ClaimedRecord,
        OutRecord);
    if (Claim == EVistaPhysicalCommandClaimOutcome::Replay)
    {
        return true;
    }
    if (Claim == EVistaPhysicalCommandClaimOutcome::Collision)
    {
        SetRejectedRecord(InputRequest, TEXT("COMMAND_ID_COLLISION"), OutRecord);
        return false;
    }
    if (Claim != EVistaPhysicalCommandClaimOutcome::Claimed)
    {
        SetRejectedRecord(InputRequest, TEXT("COMMAND_LEDGER_CAPACITY"), OutRecord);
        return false;
    }
    if (HasActiveAction())
    {
        return RejectNewRequest(
            InputRequest, InputRequest, TEXT("ACTION_EXECUTOR_BUSY"), OutRecord);
    }
    if (!IsPhysicalAffordance(InputRequest.Affordance))
    {
        return RejectNewRequest(
            InputRequest,
            InputRequest,
            TEXT("PHYSICAL_AFFORDANCE_REQUIRED"),
            OutRecord);
    }
    AActor* Requester = InputRequest.Requester;
    AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(InputRequest.Target);
    if (!IsValid(Requester) || !IsValid(Pickup) ||
        !Requester->GetClass()->ImplementsInterface(UVistaItemCarrier::StaticClass()))
    {
        return RejectNewRequest(
            InputRequest,
            InputRequest,
            TEXT("PHYSICAL_PARTICIPANT_INVALID"),
            OutRecord);
    }
    UVistaAnimationComponent* RequesterAnimation =
        Requester->FindComponentByClass<UVistaAnimationComponent>();
    FName AnimationReadinessCode = IsValid(RequesterAnimation)
        ? FName(TEXT("ANIMATION_NOT_APPROVED"))
        : FName(TEXT("ANIMATION_COMPONENT_UNAVAILABLE"));
    const EVistaNpcActionType AnimationType =
        AnimationTypeForPhysicalAffordance(InputRequest.Affordance);
    bool bAnimationReady = IsValid(RequesterAnimation) &&
        RequesterAnimation->HasApprovedMutationAnimation(
            AnimationType,
            AnimationReadinessCode);
#if WITH_DEV_AUTOMATION_TESTS
    bAnimationReady = bAnimationReady ||
        bDevAutomationBypassesAnimationReadiness;
#else
    static_cast<void>(bDevAutomationBypassesAnimationReadiness);
#endif
    if (!bAnimationReady)
    {
        return RejectNewRequest(
            InputRequest,
            InputRequest,
            AnimationReadinessCode,
            OutRecord);
    }
    if (!IsValid(GetWorld()) || Requester->GetWorld() != GetWorld() ||
        Pickup->GetWorld() != GetWorld())
    {
        return RejectNewRequest(
            InputRequest, InputRequest, TEXT("ACTION_WORLD_MISMATCH"), OutRecord);
    }
    if (!Requester->HasAuthority() || !Pickup->HasAuthority())
    {
        return RejectNewRequest(
            InputRequest, InputRequest, TEXT("AUTHORITY_REQUIRED"), OutRecord);
    }
    const TArray<EVistaAffordance> Affordances =
        IVistaInteractable::Execute_VistaGetAffordances(Pickup);
    if (!Affordances.Contains(InputRequest.Affordance))
    {
        return RejectNewRequest(
            InputRequest, InputRequest, TEXT("AFFORDANCE_UNSUPPORTED"), OutRecord);
    }
    if ((InputRequest.Affordance == EVistaAffordance::PickUp &&
         IsValid(Pickup->GetCarrier())) ||
        (InputRequest.Affordance != EVistaAffordance::PickUp &&
         Pickup->GetCarrier() != Requester))
    {
        return RejectNewRequest(
            InputRequest, InputRequest, TEXT("PHYSICAL_STATE_MISMATCH"), OutRecord);
    }
    if (InputRequest.Affordance == EVistaAffordance::PickUp &&
        Pickup->GetPhysicalDisposition() == EVistaPickupDisposition::Contained)
    {
        return RejectNewRequest(
            InputRequest,
            InputRequest,
            TEXT("ITEM_CONTAINED_REMOVE_REQUIRED"),
            OutRecord);
    }
    AActor* RequesterInventoryItem =
        IVistaItemCarrier::Execute_VistaGetHeldItem(Requester);
    if ((InputRequest.Affordance == EVistaAffordance::PickUp &&
         IsValid(RequesterInventoryItem)) ||
        (InputRequest.Affordance != EVistaAffordance::PickUp &&
         RequesterInventoryItem != Pickup))
    {
        return RejectNewRequest(
            InputRequest,
            InputRequest,
            TEXT("CARRIER_INVENTORY_STATE_MISMATCH"),
            OutRecord);
    }
    if (!FMath::IsFinite(InputRequest.TimeoutSeconds) ||
        InputRequest.TimeoutSeconds <= 0.0f || InputRequest.TimeoutSeconds > 300.0f)
    {
        return RejectNewRequest(
            InputRequest, InputRequest, TEXT("ACTION_TIMEOUT_INVALID"), OutRecord);
    }
    if (InputRequest.ReleaseVelocity.ContainsNaN() ||
        InputRequest.ReleaseVelocity.SizeSquared() > FMath::Square(5000.0f) ||
        (InputRequest.Affordance != EVistaAffordance::Drop &&
         !InputRequest.ReleaseVelocity.IsNearlyZero()))
    {
        return RejectNewRequest(
            InputRequest, InputRequest, TEXT("RELEASE_VELOCITY_INVALID"), OutRecord);
    }

    FVistaPhysicalActionRequest Request = InputRequest;
    Request.RequesterSemanticId = SemanticIdForActor(Requester);
    Request.TargetSemanticId = SemanticIdForActor(Pickup);
    if (Request.RequesterSemanticId.IsEmpty() || Request.TargetSemanticId.IsEmpty() ||
        (!InputRequest.RequesterSemanticId.IsEmpty() &&
         InputRequest.RequesterSemanticId != Request.RequesterSemanticId) ||
        (!InputRequest.TargetSemanticId.IsEmpty() &&
         InputRequest.TargetSemanticId != Request.TargetSemanticId))
    {
        return RejectNewRequest(
            InputRequest, InputRequest, TEXT("SEMANTIC_ID_MISMATCH"), OutRecord);
    }

    FName AnchorCode;
    USceneComponent* ResolvedCarryAnchor = nullptr;
    if (Request.Affordance == EVistaAffordance::PickUp)
    {
        ResolvedCarryAnchor = PrepareCarryAnchor(Requester, AnchorCode);
        if (!IsValid(ResolvedCarryAnchor))
        {
            return RejectNewRequest(
                InputRequest, Request, AnchorCode, OutRecord);
        }
    }
    else
    {
        USceneComponent* ExistingAnchor =
            IVistaItemCarrier::Execute_VistaGetCarryAnchor(Requester);
        if (!IsCarryAnchorSafe(Requester, ExistingAnchor))
        {
            return RejectNewRequest(
                InputRequest,
                Request,
                TEXT("CARRY_ANCHOR_NOT_READY"),
                OutRecord);
        }
        ResolvedCarryAnchor = ExistingAnchor;
    }

    if (Request.Affordance == EVistaAffordance::Place)
    {
        if (!IsValid(Request.PlacementAnchor))
        {
            Request.PlacementAnchor = ResolveStablePlacementAnchor(
                Requester,
                Request.PlacementOwner,
                AnchorCode,
                Request.PlacementAnchorSemanticId);
        }
        else
        {
            ATargetPoint* AnchorActor = Cast<ATargetPoint>(Request.PlacementAnchor->GetOwner());
            FString TaggedOwner;
            FString TaggedAnchor;
            if (!IsValid(AnchorActor) ||
                Request.PlacementAnchor != AnchorActor->GetRootComponent() ||
                !StableAnchorIdentity(AnchorActor, TaggedOwner, TaggedAnchor) ||
                (IsValid(Request.PlacementOwner) &&
                 SemanticIdForActor(Request.PlacementOwner) != TaggedOwner) ||
                (!Request.PlacementAnchorSemanticId.IsEmpty() &&
                 Request.PlacementAnchorSemanticId != TaggedAnchor))
            {
                AnchorCode = TEXT("PLACEMENT_TARGET_POINT_INVALID");
                Request.PlacementAnchor = nullptr;
            }
            else
            {
                int32 IdentityMatches = 0;
                const FName StableTag(
                    *(FString(StableSemanticTagPrefix) + TaggedAnchor));
                for (TActorIterator<ATargetPoint> It(Requester->GetWorld()); It; ++It)
                {
                    IdentityMatches += It->ActorHasTag(StableTag) ? 1 : 0;
                }
                if (IdentityMatches != 1)
                {
                    AnchorCode = TEXT("PLACEMENT_ANCHOR_IDENTITY_AMBIGUOUS");
                    Request.PlacementAnchor = nullptr;
                }
                else
                {
                    Request.PlacementAnchorSemanticId = TaggedAnchor;
                }
            }
        }
        if (!IsValid(Request.PlacementAnchor))
        {
            return RejectNewRequest(
                InputRequest,
                Request,
                AnchorCode.IsNone()
                    ? FName(TEXT("PLACEMENT_TARGET_POINT_REQUIRED"))
                    : AnchorCode,
                OutRecord);
        }
    }
    else if (IsValid(Request.PlacementAnchor) ||
             !Request.PlacementAnchorSemanticId.IsEmpty())
    {
        return RejectNewRequest(
            InputRequest,
            Request,
            TEXT("PLACEMENT_ANCHOR_UNEXPECTED"),
            OutRecord);
    }

    FActivePhysicalAction Active;
    Active.Request = Request;
    Active.CanonicalRequest = CanonicalRequest;
    Active.Requester = Requester;
    Active.Target = Pickup;
    Active.PlacementOwner = Request.PlacementOwner;
    Active.PlacementAnchor = Request.PlacementAnchor;
    Active.CarryAnchor = ResolvedCarryAnchor;
    Active.BeforeAttachmentParent = Pickup->GetRootComponent()
        ? Pickup->GetRootComponent()->GetAttachParent() : nullptr;
    Active.BeforeCarrier = Pickup->GetCarrier();
    Active.BeforeRequesterInventoryItem = RequesterInventoryItem;
    Active.Animation = RequesterAnimation;
    Active.StartedAtSeconds = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
    Active.Record.CommandId = Request.CommandId;
    Active.Record.Affordance = Request.Affordance;
    Active.Record.RequesterSemanticId = Request.RequesterSemanticId;
    Active.Record.TargetSemanticId = Request.TargetSemanticId;
    Active.Record.PlacementAnchorSemanticId = Request.PlacementAnchorSemanticId;
    Active.Record.Status = EVistaActionTransactionStatus::Running;
    Active.Record.Code = TEXT("ACTION_ACCEPTED");
    Active.Record.SessionGeneration = Request.SessionGeneration;
    Active.Record.RequesterBeforeTransform = Requester->GetActorTransform();
    Active.Record.BeforeState =
        IVistaInteractable::Execute_VistaGetRuntimeState(Pickup);
    if (Active.Record.BeforeState.SemanticId != Request.TargetSemanticId ||
        Active.Record.BeforeState.Transform.ContainsNaN())
    {
        return RejectNewRequest(
            InputRequest, Request, TEXT("BEFORE_STATE_INVALID"), OutRecord);
    }
    Active.Record.bHasBeforeState = true;
    Active.Record.bHasBeforePhysicalState = CapturePickupPhysicalState(
        Pickup, Requester, Active.Record.BeforePhysicalState);
    if (!Active.Record.bHasBeforePhysicalState ||
        (Active.Record.BeforePhysicalState.bSimulatePhysics &&
         Active.Record.BeforePhysicalState.bHasAttachmentParent) ||
        Active.Record.BeforePhysicalState.bHeld != Active.BeforeCarrier.IsValid() ||
        Active.Record.BeforePhysicalState.InventoryCarrierSemanticId !=
            Request.RequesterSemanticId ||
        Active.Record.BeforePhysicalState.bInventorySlotOccupied !=
            IsValid(RequesterInventoryItem) ||
        Active.Record.BeforePhysicalState.InventoryItemSemanticId !=
            SemanticIdForActor(RequesterInventoryItem) ||
        Active.Record.BeforePhysicalState.bHasAttachmentParent !=
            Active.Record.BeforePhysicalState.bHeld ||
        (Active.Record.BeforePhysicalState.bHeld &&
         (Active.Record.BeforePhysicalState.bSimulatePhysics ||
          Pickup->GetRootComponent()->GetAttachParent() !=
              ResolvedCarryAnchor)))
    {
        return RejectNewRequest(
            InputRequest, Request, TEXT("BEFORE_PHYSICAL_STATE_INVALID"), OutRecord);
    }
    if (!Pickup->TryReserveTransaction(this, Request.CommandId))
    {
        return RejectNewRequest(
            InputRequest, Request, TEXT("PHYSICAL_TARGET_BUSY"), OutRecord);
    }
    ActiveAction = MoveTemp(Active);
    if (!Transition(EVistaActionPhase::Approach, TEXT("ACTION_APPROACH")))
    {
        ActiveAction->Record.Status = EVistaActionTransactionStatus::Failed;
        ActiveAction->Record.Code = TEXT("ACTION_LEDGER_PUBLISH_FAILED");
        OutRecord = ActiveAction->Record;
        const bool bTerminalPublished = PublishRecord(true);
        ensureMsgf(
            bTerminalPublished,
            TEXT("VISTA action claim could not publish terminal failure"));
        AbandonActiveAfterPublishFailure();
        return false;
    }
    OutRecord = ActiveAction->Record;
    return true;
}

#if WITH_DEV_AUTOMATION_TESTS
bool UVistaActionExecutorComponent::DrivePhysicalInteractionForDevAutomation(
    const bool bFailAfterContact,
    FVistaActionTransactionRecord& OutRecord)
{
    check(IsInGameThread());
    if (!ActiveAction.IsSet())
    {
        OutRecord = FVistaActionTransactionRecord();
        OutRecord.Code = TEXT("DEV_AUTOMATION_ACTION_REQUIRED");
        OutRecord.Status = EVistaActionTransactionStatus::Failed;
        return false;
    }

    const FName CommandId = ActiveAction->Record.CommandId;
    AdvanceApproach();
    if (!ActiveAction.IsSet() ||
        ActiveAction->Record.Phase != EVistaActionPhase::Align)
    {
        return GetTransaction(CommandId, OutRecord) && OutRecord.IsTerminal();
    }
    AdvanceAlign();
    if (!ActiveAction.IsSet() ||
        ActiveAction->Record.Phase != EVistaActionPhase::Animate)
    {
        return GetTransaction(CommandId, OutRecord) && OutRecord.IsTerminal();
    }
    if (!Transition(
            EVistaActionPhase::ContactCommit,
            TEXT("DEV_AUTOMATION_CONTACT_COMMIT")))
    {
        FinishFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
        GetTransaction(CommandId, OutRecord);
        return false;
    }

    FName ContactCode;
    if (!CommitContact(ContactCode))
    {
        FinishFailure(
            EVistaActionTransactionStatus::Failed,
            ContactCode.IsNone()
                ? FName(TEXT("DEV_AUTOMATION_CONTACT_FAILED"))
                : ContactCode);
        GetTransaction(CommandId, OutRecord);
        return false;
    }
    if (bFailAfterContact)
    {
        FinishFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("DEV_AUTOMATION_FORCED_POST_CONTACT_FAILURE"));
    }
    else
    {
        CompleteSuccess();
    }
    if (!GetTransaction(CommandId, OutRecord))
    {
        OutRecord = FVistaActionTransactionRecord();
        OutRecord.CommandId = CommandId;
        OutRecord.Code = TEXT("DEV_AUTOMATION_LEDGER_RECORD_MISSING");
        OutRecord.Status = EVistaActionTransactionStatus::Failed;
        return false;
    }
    return bFailAfterContact
        ? OutRecord.Status == EVistaActionTransactionStatus::Failed &&
            OutRecord.bRollbackAttempted && OutRecord.bRolledBack
        : OutRecord.Status == EVistaActionTransactionStatus::Succeeded;
}
#endif

void UVistaActionExecutorComponent::TickComponent(
    float DeltaTime,
    ELevelTick TickType,
    FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    if (ActiveSemanticAction.IsSet())
    {
        TickSemanticAction();
        return;
    }
    if (!ActiveAction.IsSet())
    {
        return;
    }
    const double Elapsed = GetWorld()
        ? GetWorld()->GetTimeSeconds() - ActiveAction->StartedAtSeconds : 0.0;
    if (Elapsed > ActiveAction->Request.TimeoutSeconds)
    {
        if (UVistaAnimationComponent* Animation = ActiveAction->Animation.Get())
        {
            Animation->StopActiveAction(TEXT("ACTION_TIMED_OUT"));
        }
        FinishFailure(EVistaActionTransactionStatus::TimedOut, TEXT("ACTION_TIMED_OUT"));
        return;
    }
    switch (ActiveAction->Record.Phase)
    {
    case EVistaActionPhase::Approach: AdvanceApproach(); break;
    case EVistaActionPhase::Align: AdvanceAlign(); break;
    case EVistaActionPhase::Animate: AdvanceAnimation(); break;
    case EVistaActionPhase::ContactCommit: AdvanceAfterContact(); break;
    default: break;
    }
}

void UVistaActionExecutorComponent::AdvanceApproach()
{
    AActor* Requester = ActiveAction->Requester.Get();
    AActor* Target = ActiveAction->Request.Affordance == EVistaAffordance::Place
        ? ActiveAction->PlacementAnchor.IsValid()
            ? ActiveAction->PlacementAnchor->GetOwner() : nullptr
        : ActiveAction->Target.Get();
    if (!IsValid(Requester) || !IsValid(Target))
    {
        FinishFailure(EVistaActionTransactionStatus::Failed, TEXT("ACTION_PARTICIPANT_LOST"));
        return;
    }
    if (FVector::Dist(Requester->GetActorLocation(), Target->GetActorLocation()) >
        MaximumContactDistanceCm)
    {
        FinishFailure(EVistaActionTransactionStatus::Failed, TEXT("ACTION_APPROACH_REQUIRED"));
        return;
    }
    if (!Transition(EVistaActionPhase::Align, TEXT("ACTION_ALIGN")))
    {
        FinishFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
    }
}

void UVistaActionExecutorComponent::AdvanceAlign()
{
    AActor* Requester = ActiveAction->Requester.Get();
    const USceneComponent* PlacementAnchor = ActiveAction->PlacementAnchor.Get();
    AActor* Target = ActiveAction->PlacementOwner.IsValid()
        ? ActiveAction->PlacementOwner.Get() : ActiveAction->Target.Get();
    if (!IsValid(Requester) || (!IsValid(Target) && !IsValid(PlacementAnchor)))
    {
        FinishFailure(EVistaActionTransactionStatus::Failed, TEXT("ACTION_ALIGNMENT_TARGET_LOST"));
        return;
    }
    const FVector TargetLocation = IsValid(PlacementAnchor)
        ? PlacementAnchor->GetComponentLocation() : Target->GetActorLocation();
    FVector Direction = TargetLocation - Requester->GetActorLocation();
    Direction.Z = 0.0f;
    // From Align onward the montage may apply root motion even when no yaw
    // change is necessary, so every terminal failure restores this snapshot.
    ActiveAction->bAlignmentApplied = true;
    if (!Direction.IsNearlyZero())
    {
        if (!Requester->SetActorRotation(Direction.Rotation()))
        {
            FinishFailure(EVistaActionTransactionStatus::Failed,
                          TEXT("ACTION_ALIGNMENT_FAILED"));
            return;
        }
    }
    if (!Transition(EVistaActionPhase::Animate, TEXT("ACTION_ANIMATE")))
    {
        FinishFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
    }
}

bool UVistaActionExecutorComponent::StartAnimation(FName& OutCode)
{
    UVistaAnimationComponent* Animation = ActiveAction->Animation.Get();
    AActor* AnimationTarget =
        ActiveAction->Request.Affordance == EVistaAffordance::Place &&
        ActiveAction->PlacementAnchor.IsValid()
            ? ActiveAction->PlacementAnchor->GetOwner()
            : ActiveAction->Target.Get();
    if (!IsValid(Animation) || !IsValid(AnimationTarget))
    {
        OutCode = TEXT("ANIMATION_COMPONENT_OR_TARGET_UNAVAILABLE");
        return false;
    }
    FVistaNpcAction Action;
    Action.ActionId = ActiveAction->Record.CommandId;
    Action.Type = AnimationTypeForPhysicalAffordance(
        ActiveAction->Request.Affordance);
    Action.TargetSemanticId = ActiveAction->Record.TargetSemanticId;
    Action.Hand = EVistaAnimationHand::Right;
    Action.TimeoutSeconds = ActiveAction->Request.TimeoutSeconds;
    return Animation->StartNpcAction(Action, AnimationTarget, OutCode);
}

void UVistaActionExecutorComponent::AdvanceAnimation()
{
    UVistaAnimationComponent* Animation = ActiveAction->Animation.Get();
    if (!ActiveAction->bAnimationStarted)
    {
        FName Code;
        if (!StartAnimation(Code))
        {
            // Physical actions never use the legacy immediate-mutation fallback.
            FinishFailure(EVistaActionTransactionStatus::Failed,
                Code.IsNone() ? FName(TEXT("ANIMATION_NOT_READY")) : Code);
            return;
        }
        ActiveAction->bAnimationStarted = true;
        return;
    }
    if (!IsValid(Animation))
    {
        FinishFailure(EVistaActionTransactionStatus::Failed,
                      TEXT("ANIMATION_COMPONENT_LOST"));
        return;
    }
    if (Animation->ConsumeContactSignal())
    {
        if (!Transition(
                EVistaActionPhase::ContactCommit,
                TEXT("ACTION_CONTACT_COMMIT")))
        {
            Animation->StopActiveAction(TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
            FinishFailure(
                EVistaActionTransactionStatus::Failed,
                TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
            return;
        }
        FName Code;
        if (!CommitContact(Code))
        {
            Animation->StopActiveAction(Code);
            FinishFailure(EVistaActionTransactionStatus::Failed, Code);
            return;
        }
        AdvanceAfterContact();
        return;
    }
    const FVistaAnimationPlaybackResult Playback = Animation->GetPlaybackResult();
    switch (Playback.Status)
    {
    case EVistaAnimationPlaybackStatus::Running: return;
    case EVistaAnimationPlaybackStatus::TimedOut:
        FinishFailure(EVistaActionTransactionStatus::TimedOut, Playback.Code);
        return;
    case EVistaAnimationPlaybackStatus::Failed:
    case EVistaAnimationPlaybackStatus::Stopped:
        FinishFailure(EVistaActionTransactionStatus::Failed, Playback.Code);
        return;
    case EVistaAnimationPlaybackStatus::Succeeded:
        FinishFailure(EVistaActionTransactionStatus::Failed,
                      TEXT("ANIMATION_CONTACT_NOTIFY_MISSING"));
        return;
    default: return;
    }
}

bool UVistaActionExecutorComponent::CommitContact(FName& OutCode)
{
    if (ActiveAction->Record.bContactMutationAttempted ||
        ActiveAction->Record.bContactCommitted ||
        ActiveAction->Record.PhysicalMutationCount != 0)
    {
        OutCode = TEXT("CONTACT_ALREADY_COMMITTED");
        return false;
    }
    AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(ActiveAction->Target.Get());
    AActor* Requester = ActiveAction->Requester.Get();
    if (!IsValid(Pickup) || !IsValid(Requester))
    {
        OutCode = TEXT("ACTION_PARTICIPANT_LOST");
        return false;
    }
    AActor* ContactTarget =
        ActiveAction->Request.Affordance == EVistaAffordance::Place &&
        ActiveAction->PlacementAnchor.IsValid()
            ? ActiveAction->PlacementAnchor->GetOwner()
            : Pickup;
    if (!IsValid(ContactTarget) ||
        FVector::Dist(Requester->GetActorLocation(), ContactTarget->GetActorLocation()) >
            MaximumContactDistanceCm)
    {
        OutCode = TEXT("ACTION_CONTACT_OUT_OF_RANGE");
        return false;
    }
    FVistaInteractionRequest Interaction;
    Interaction.Requester = Requester;
    Interaction.Affordance = ActiveAction->Request.Affordance;
    Interaction.PlacementAnchor = ActiveAction->PlacementAnchor.Get();
    Interaction.ExpectedRevision = ActiveAction->Request.ExpectedRevision;
    Interaction.SessionGeneration = ActiveAction->Request.SessionGeneration;
    // A mutator may fail after changing only part of attachment/body state or
    // after its local compensation also fails. Mark the attempt before entry
    // so FinishFailure always executes the outer trusted full-state restore.
    ActiveAction->Record.bContactMutationAttempted = true;
    const bool bAttemptPublished = PublishRecord(false);
    ensureMsgf(
        bAttemptPublished,
        TEXT("VISTA contact attempt record publish failed"));
    if (!bAttemptPublished)
    {
        OutCode = TEXT("ACTION_LEDGER_PUBLISH_FAILED");
        return false;
    }
    const FVistaInteractionResult Result = Pickup->CommitTransactionalInteraction(
        this,
        Interaction,
        ActiveAction->Record.CommandId,
        ActiveAction->Request.ReleaseVelocity);
    if (!Result.IsSuccess())
    {
        OutCode = Result.Code;
        return false;
    }
    ActiveAction->Record.bContactCommitted = true;
    ActiveAction->Record.PhysicalMutationCount = 1;
    ActiveAction->Record.ContactState = Result.State;
    ActiveAction->Record.bHasContactState = true;
    ActiveAction->Record.bHasContactPhysicalState = CapturePickupPhysicalState(
        Pickup,
        Requester,
        ActiveAction->Record.ContactPhysicalState);
    ActiveAction->Record.RequesterContactTransform =
        Requester->GetActorTransform();
    ActiveAction->ContactResultCode = Result.Code;
    if (Result.State.SemanticId != ActiveAction->Record.TargetSemanticId ||
        Result.State.Transform.ContainsNaN() ||
        !ActiveAction->Record.bHasContactPhysicalState)
    {
        OutCode = TEXT("CONTACT_STATE_INVALID");
        return false;
    }
    if (!StateMatchesPhysicalEffect(Result.State, ActiveAction->Request) ||
        !PhysicalSnapshotMatchesEffect(
            ActiveAction->Record.ContactPhysicalState,
            ActiveAction->Request,
            Pickup,
            ActiveAction->CarryAnchor.Get(),
            ActiveAction->PlacementAnchor.Get()))
    {
        OutCode = TEXT("CONTACT_STATE_EFFECT_MISMATCH");
        return false;
    }
    const bool bContactPublished = PublishRecord(false);
    ensureMsgf(
        bContactPublished,
        TEXT("VISTA contact commit record publish failed"));
    if (!bContactPublished)
    {
        OutCode = TEXT("ACTION_LEDGER_PUBLISH_FAILED");
        return false;
    }
    OutCode = Result.Code;
    return true;
}

void UVistaActionExecutorComponent::AdvanceAfterContact()
{
    UVistaAnimationComponent* Animation = ActiveAction->Animation.Get();
    if (!IsValid(Animation))
    {
        FinishFailure(EVistaActionTransactionStatus::Failed,
                      TEXT("ANIMATION_COMPONENT_LOST"));
        return;
    }
    const FVistaAnimationPlaybackResult Playback = Animation->GetPlaybackResult();
    switch (Playback.Status)
    {
    case EVistaAnimationPlaybackStatus::Running: return;
    case EVistaAnimationPlaybackStatus::Succeeded: CompleteSuccess(); return;
    case EVistaAnimationPlaybackStatus::TimedOut:
        FinishFailure(EVistaActionTransactionStatus::TimedOut, Playback.Code);
        return;
    case EVistaAnimationPlaybackStatus::Failed:
    case EVistaAnimationPlaybackStatus::Stopped:
        FinishFailure(EVistaActionTransactionStatus::Failed, Playback.Code);
        return;
    default:
        FinishFailure(EVistaActionTransactionStatus::Failed,
                      TEXT("ANIMATION_TERMINAL_STATE_INVALID"));
        return;
    }
}

void UVistaActionExecutorComponent::CompleteSuccess()
{
    AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(ActiveAction->Target.Get());
    if (!IsValid(Pickup) || !ActiveAction->Record.bContactCommitted ||
        ActiveAction->Record.PhysicalMutationCount != 1)
    {
        FinishFailure(EVistaActionTransactionStatus::Failed,
                      TEXT("CONTACT_COMMIT_EVIDENCE_INVALID"));
        return;
    }
    ActiveAction->Record.AfterState =
        IVistaInteractable::Execute_VistaGetRuntimeState(Pickup);
    ActiveAction->Record.bHasAfterPhysicalState = CapturePickupPhysicalState(
        Pickup,
        ActiveAction->Requester.Get(),
        ActiveAction->Record.AfterPhysicalState);
    if (ActiveAction->Record.AfterState.SemanticId !=
            ActiveAction->Record.TargetSemanticId ||
        ActiveAction->Record.AfterState.Transform.ContainsNaN() ||
        !ActiveAction->Record.bHasAfterPhysicalState)
    {
        FinishFailure(EVistaActionTransactionStatus::Failed,
                      TEXT("AFTER_STATE_INVALID"));
        return;
    }
    if (!StateMatchesPhysicalEffect(
            ActiveAction->Record.AfterState, ActiveAction->Request) ||
        !PhysicalSnapshotMatchesEffect(
            ActiveAction->Record.AfterPhysicalState,
            ActiveAction->Request,
            Pickup,
            ActiveAction->CarryAnchor.Get(),
            ActiveAction->PlacementAnchor.Get()))
    {
        FinishFailure(EVistaActionTransactionStatus::Failed,
                      TEXT("AFTER_STATE_EFFECT_MISMATCH"));
        return;
    }
    ActiveAction->Record.bHasAfterState = true;
    ActiveAction->Record.RequesterAfterTransform =
        ActiveAction->Requester.IsValid()
            ? ActiveAction->Requester->GetActorTransform()
            : ActiveAction->Record.RequesterContactTransform;
    if (!Transition(
            EVistaActionPhase::Complete,
            ActiveAction->ContactResultCode.IsNone()
                ? FName(TEXT("ACTION_COMPLETE"))
                : ActiveAction->ContactResultCode))
    {
        FinishFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
        return;
    }
    ActiveAction->Record.Status = EVistaActionTransactionStatus::Succeeded;
    if (!Transition(EVistaActionPhase::Idle, ActiveAction->Record.Code))
    {
        FinishFailure(
            EVistaActionTransactionStatus::Failed,
            TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
        return;
    }
    FVistaActionTransactionRecord FinalRecord;
    if (!FinalizeActive(&FinalRecord))
    {
        FinishFailure(
            EVistaActionTransactionStatus::Failed,
            ActiveAction.IsSet() && !ActiveAction->Record.Code.IsNone()
                ? ActiveAction->Record.Code
                : FName(TEXT("ACTION_LEDGER_TERMINAL_PUBLISH_FAILED")));
        return;
    }
    if (UVistaEventSubsystem* Events = GetWorld()
            ? GetWorld()->GetSubsystem<UVistaEventSubsystem>() : nullptr)
    {
        Events->RecordSuccessfulInteraction(
            FinalRecord.TargetSemanticId,
            FinalRecord.Affordance);
    }
}

void UVistaActionExecutorComponent::FinishFailure(
    EVistaActionTransactionStatus Status,
    FName Code)
{
    if (!ActiveAction.IsSet())
    {
        return;
    }
    const bool bRollbackRequired = ActiveAction->bAlignmentApplied ||
        ActiveAction->Record.bContactMutationAttempted;
    bool bRollbackSucceeded = true;
    if (bRollbackRequired)
    {
        Transition(EVistaActionPhase::RollingBack, TEXT("ACTION_ROLLING_BACK"));
        ActiveAction->Record.bRollbackAttempted = true;
    }
    if (ActiveAction->bAlignmentApplied)
    {
        AActor* Requester = ActiveAction->Requester.Get();
        const bool bSetTransform = IsValid(Requester) && Requester->SetActorTransform(
                ActiveAction->Record.RequesterBeforeTransform,
                false,
                nullptr,
                ETeleportType::TeleportPhysics);
        ActiveAction->Record.bRequesterTransformRestored = bSetTransform &&
            TransformBitsEqual(
                Requester->GetActorTransform(),
                ActiveAction->Record.RequesterBeforeTransform);
        bRollbackSucceeded = ActiveAction->Record.bRequesterTransformRestored;
    }
    if (ActiveAction->Record.bContactMutationAttempted)
    {
        FName PhysicalRollbackCode;
        const bool bPhysicalRollbackSucceeded =
            RestoreAndVerifyBeforePhysicalState(PhysicalRollbackCode);
        ActiveAction->Record.RollbackCode = PhysicalRollbackCode;
        bRollbackSucceeded =
            bRollbackSucceeded && bPhysicalRollbackSucceeded;
        if (!bPhysicalRollbackSucceeded)
        {
            if (AVistaPickupActor* Pickup =
                    Cast<AVistaPickupActor>(ActiveAction->Target.Get()))
            {
                ActiveAction->Record.AfterState =
                    IVistaInteractable::Execute_VistaGetRuntimeState(Pickup);
                ActiveAction->Record.bHasAfterState = true;
                ActiveAction->Record.bHasAfterPhysicalState =
                    CapturePickupPhysicalState(
                        Pickup,
                        ActiveAction->Requester.Get(),
                        ActiveAction->Record.AfterPhysicalState);
            }
        }
    }
    else if (AVistaPickupActor* Pickup =
                 Cast<AVistaPickupActor>(ActiveAction->Target.Get()))
    {
        ActiveAction->Record.AfterState =
            IVistaInteractable::Execute_VistaGetRuntimeState(Pickup);
        ActiveAction->Record.bHasAfterState = true;
        ActiveAction->Record.bHasAfterPhysicalState = CapturePickupPhysicalState(
            Pickup,
            ActiveAction->Requester.Get(),
            ActiveAction->Record.AfterPhysicalState);
    }
    ActiveAction->Record.bRolledBack =
        bRollbackRequired && bRollbackSucceeded;
    if (bRollbackRequired && ActiveAction->Record.RollbackCode.IsNone())
    {
        ActiveAction->Record.RollbackCode = bRollbackSucceeded
            ? FName(TEXT("ACTOR_TRANSFORM_RESTORED"))
            : FName(TEXT("ACTOR_TRANSFORM_RESTORE_FAILED"));
    }
    if (bRollbackRequired && !bRollbackSucceeded)
    {
        ActiveAction->Record.RollbackCode = TEXT("ACTION_ROLLBACK_FAILED");
        Status = EVistaActionTransactionStatus::Failed;
        Code = TEXT("ACTION_ROLLBACK_FAILED");
    }
    ActiveAction->Record.RequesterAfterTransform =
        ActiveAction->Requester.IsValid()
            ? ActiveAction->Requester->GetActorTransform()
            : ActiveAction->Record.RequesterBeforeTransform;
    Transition(EVistaActionPhase::Failed, Code.IsNone()
        ? FName(TEXT("ACTION_FAILED")) : Code);
    ActiveAction->Record.Status = Status;
    Transition(EVistaActionPhase::Idle, ActiveAction->Record.Code);
    if (!FinalizeActive())
    {
        AbandonActiveAfterPublishFailure();
    }
}

bool UVistaActionExecutorComponent::CancelActiveAction(FName Reason)
{
    if (ActiveSemanticAction.IsSet())
    {
        const FName Code = Reason.IsNone()
            ? FName(TEXT("ACTION_CANCELED"))
            : Reason;
        if (UVistaAnimationComponent* Animation =
                ActiveSemanticAction->Animation.Get())
        {
            Animation->StopActiveAction(Code);
        }
        FinishSemanticFailure(EVistaActionTransactionStatus::Canceled, Code);
        return true;
    }
    if (!ActiveAction.IsSet())
    {
        return false;
    }
    const FName Code = Reason.IsNone() ? FName(TEXT("ACTION_CANCELED")) : Reason;
    if (UVistaAnimationComponent* Animation = ActiveAction->Animation.Get())
    {
        Animation->StopActiveAction(Code);
    }
    FinishFailure(EVistaActionTransactionStatus::Canceled, Code);
    return true;
}

bool UVistaActionExecutorComponent::Transition(
    EVistaActionPhase Phase,
    FName Code)
{
    check(ActiveAction.IsSet());
    check(IsInGameThread());
    ActiveAction->Record.Phase = Phase;
    ActiveAction->Record.Code = Code;
    ActiveAction->Record.PhaseHistory.Add(Phase);
    const bool bPublished = PublishRecord(false);
    ensureMsgf(
        bPublished,
        TEXT("VISTA action phase record publish failed phase=%d"),
        static_cast<int32>(Phase));
    return bPublished;
}

bool UVistaActionExecutorComponent::FinalizeActive(
    FVistaActionTransactionRecord* OutFinalRecord)
{
    check(ActiveAction.IsSet());
    check(IsInGameThread());
    UVistaPlayableHomeRuntimeSubsystem* Runtime =
        IsValid(GetWorld()) ? GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>() : nullptr;
    FName FinalizeCode;
    const bool bPublished = IsValid(Runtime) &&
        Runtime->FinalizePhysicalCommand(
            ActiveAction->Record.CommandId,
            ActiveAction->CanonicalRequest,
            this,
            ActiveAction->Record,
            ActiveAction->Record.Status == EVistaActionTransactionStatus::Succeeded &&
                ActiveAction->Request.bCommitSessionGenerationOnSuccess,
            ActiveAction->Request.SessionGeneration,
            [this]()
            {
                AVistaPickupActor* Pickup = Cast<AVistaPickupActor>(ActiveAction->Target.Get());
                if (!IsValid(Pickup))
                {
                    return false;
                }
                Pickup->ReleaseTransaction(this, ActiveAction->Record.CommandId);
                return !Pickup->IsTransactionReservedBy(this, ActiveAction->Record.CommandId);
            },
            FinalizeCode);
    ensureMsgf(
        bPublished,
        TEXT("VISTA terminal action record publish failed: %s"),
        *FinalizeCode.ToString());
    if (!bPublished)
    {
        ActiveAction->Record.Code =
            FinalizeCode.IsNone() ? FName(TEXT("ACTION_LEDGER_TERMINAL_PUBLISH_FAILED")) : FinalizeCode;
        return false;
    }
    const FVistaActionTransactionRecord Record = ActiveAction->Record;
    if (OutFinalRecord != nullptr)
    {
        *OutFinalRecord = Record;
    }
    ActiveAction.Reset();
    return true;
}

void UVistaActionExecutorComponent::AbandonActiveAfterPublishFailure()
{
    if (!ActiveAction.IsSet())
    {
        return;
    }
    if (UVistaAnimationComponent* Animation = ActiveAction->Animation.Get())
    {
        Animation->StopActiveAction(TEXT("ACTION_LEDGER_PUBLISH_FAILED"));
    }
    if (AVistaPickupActor* Pickup =
            Cast<AVistaPickupActor>(ActiveAction->Target.Get()))
    {
        Pickup->ReleaseTransaction(this, ActiveAction->Record.CommandId);
    }
    ActiveAction.Reset();
}

bool UVistaActionExecutorComponent::PublishRecord(bool bTerminal)
{
    if (!ActiveAction.IsSet() || !IsValid(GetWorld()))
    {
        return false;
    }
    UVistaPlayableHomeRuntimeSubsystem* Runtime =
        GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>();
    return IsValid(Runtime) && Runtime->PublishPhysicalCommand(
        ActiveAction->Record.CommandId,
        ActiveAction->CanonicalRequest,
        this,
        ActiveAction->Record,
        bTerminal);
}

bool UVistaActionExecutorComponent::GetTransaction(
    FName CommandId,
    FVistaActionTransactionRecord& OutRecord) const
{
    check(IsInGameThread());
    const UVistaPlayableHomeRuntimeSubsystem* Runtime = IsValid(GetWorld())
        ? GetWorld()->GetSubsystem<UVistaPlayableHomeRuntimeSubsystem>() : nullptr;
    return IsValid(Runtime) &&
        Runtime->GetPhysicalCommandRecord(CommandId, OutRecord);
}

FVistaInteractionResult
UVistaActionExecutorComponent::InteractionResultFromTransaction(
    const FVistaActionTransactionRecord& Record)
{
    const FVistaEntityRuntimeState& State = Record.bHasAfterState
        ? Record.AfterState
        : Record.bHasContactState ? Record.ContactState : Record.BeforeState;
    if (Record.Status == EVistaActionTransactionStatus::Running ||
        Record.Status == EVistaActionTransactionStatus::Succeeded)
    {
        return FVistaInteractionResult::Success(
            Record.TargetSemanticId, State, Record.Code);
    }
    EVistaInteractionStatus Status = EVistaInteractionStatus::Rejected;
    if (Record.Status == EVistaActionTransactionStatus::TimedOut)
    {
        Status = EVistaInteractionStatus::TimedOut;
    }
    else if (Record.Code == FName(TEXT("ACTION_EXECUTOR_BUSY")))
    {
        Status = EVistaInteractionStatus::Busy;
    }
    else if (Record.Code == FName(TEXT("ACTION_APPROACH_REQUIRED")))
    {
        Status = EVistaInteractionStatus::Blocked;
    }
    return FVistaInteractionResult::Failure(Status, Record.Code,
                                             Record.TargetSemanticId);
}

void UVistaActionExecutorComponent::EndPlay(
    const EEndPlayReason::Type EndPlayReason)
{
    CancelActiveAction(TEXT("EXECUTOR_END_PLAY"));
    Super::EndPlay(EndPlayReason);
}
