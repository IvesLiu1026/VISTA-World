#include "VistaPickupActor.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "HAL/PlatformMemory.h"
#include "Net/UnrealNetwork.h"
#include "VistaActionExecutorComponent.h"
#include "VistaContainerActor.h"
#include "VistaHomeNpcCharacter.h"
#include "VistaItemCarrier.h"
#include "VistaLiquidReceiverActor.h"
#include "VistaPlayableHomeCharacter.h"

namespace
{
constexpr const TCHAR* StableSemanticTagPrefix = TEXT("VistaSemanticId=");
constexpr const TCHAR* PlacementOwnerTagPrefix = TEXT("VistaOwner=");
constexpr const TCHAR* PlacementAnchorDelimiter = TEXT("/anchor.");
const FName PourableKey(TEXT("pourable"));
const FName FilledKey(TEXT("filled"));
const FName LiquidTypeKey(TEXT("liquid_type"));
const FName LiquidCapacityKey(TEXT("liquid_capacity_ml"));
const FName LiquidAmountKey(TEXT("liquid_amount_ml"));
const FName LiquidLevelKey(TEXT("liquid_level"));
const FName ContainedInKey(TEXT("contained_in"));

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

bool PhysicalSnapshotsBitExact(
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

bool LiquidStatesBitExact(
    const FVistaLiquidStateSnapshot& Left,
    const FVistaLiquidStateSnapshot& Right)
{
    return Left.bPourable == Right.bPourable &&
        Left.LiquidType == Right.LiquidType &&
        ScalarBitsEqual(
            Left.CapacityMilliliters, Right.CapacityMilliliters) &&
        ScalarBitsEqual(Left.AmountMilliliters, Right.AmountMilliliters);
}

bool ParseStrictBoolean(const FString& Value, bool& OutValue)
{
    if (Value == TEXT("true"))
    {
        OutValue = true;
        return true;
    }
    if (Value == TEXT("false"))
    {
        OutValue = false;
        return true;
    }
    return false;
}

bool ParseFiniteFloat(const FString& Value, float& OutValue)
{
    return LexTryParseString(OutValue, *Value) && FMath::IsFinite(OutValue);
}

bool IsClosedLiquidType(const FName Value)
{
    const FString Text = Value.ToString();
    if (Text.IsEmpty() || Text.Len() > 64)
    {
        return false;
    }
    for (const TCHAR Character : Text)
    {
        if (!((Character >= TEXT('a') && Character <= TEXT('z')) ||
              (Character >= TEXT('0') && Character <= TEXT('9')) ||
              Character == TEXT('.') || Character == TEXT('_') ||
              Character == TEXT('-')))
        {
            return false;
        }
    }
    return true;
}

bool IsLowerAsciiAlpha(const TCHAR Character)
{
    return Character >= TEXT('a') && Character <= TEXT('z');
}

bool IsAsciiDigit(const TCHAR Character)
{
    return Character >= TEXT('0') && Character <= TEXT('9');
}

bool IsStablePlacementAnchorSemanticId(const FString& Value)
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
    const FString AnchorId = Value.Mid(
        DelimiterIndex + FCString::Strlen(PlacementAnchorDelimiter));
    const FString OwnerSemanticId = Value.Left(DelimiterIndex);
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

bool CanonicalizePlacementAnchorSemanticId(const FString& Value, FString& OutSemanticId)
{
    FString Candidate = Value;
    int32 CompactDelimiterIndex = INDEX_NONE;
    if (Candidate.FindChar(TEXT('#'), CompactDelimiterIndex))
    {
        if (CompactDelimiterIndex <= 0 || CompactDelimiterIndex + 1 >= Candidate.Len() ||
            Candidate.Mid(CompactDelimiterIndex + 1).Contains(TEXT("#")))
        {
            return false;
        }
        Candidate = Candidate.Left(CompactDelimiterIndex) + PlacementAnchorDelimiter +
            Candidate.Mid(CompactDelimiterIndex + 1);
    }
    if (!IsStablePlacementAnchorSemanticId(Candidate))
    {
        return false;
    }
    OutSemanticId = MoveTemp(Candidate);
    return true;
}

bool IsNullPlacementStateValue(const FString& Value)
{
    return Value.IsEmpty() || Value.Equals(TEXT("none"), ESearchCase::IgnoreCase) ||
        Value.Equals(TEXT("null"), ESearchCase::IgnoreCase);
}

bool IsUniqueStablePlacementAnchor(UWorld* World,
                                   const FString& SemanticId,
                                   const AActor* ExpectedOwner = nullptr)
{
    if (!IsValid(World) || !IsStablePlacementAnchorSemanticId(SemanticId))
    {
        return false;
    }
    const FName StableTag(*(FString(StableSemanticTagPrefix) + SemanticId));
    const int32 DelimiterIndex = SemanticId.Find(
        PlacementAnchorDelimiter, ESearchCase::CaseSensitive, ESearchDir::FromStart);
    const FName OwnerTag(*(FString(PlacementOwnerTagPrefix) +
        SemanticId.Left(DelimiterIndex)));
    const AActor* Match = nullptr;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (!It->ActorHasTag(StableTag) || !It->ActorHasTag(OwnerTag))
        {
            continue;
        }
        if (Match != nullptr)
        {
            return false;
        }
        Match = *It;
    }
    return IsValid(Match) && IsValid(Match->GetRootComponent()) &&
        (ExpectedOwner == nullptr || Match == ExpectedOwner);
}

bool StablePlacementAnchorSemanticId(const USceneComponent* PlacementAnchor,
                                     FString& OutSemanticId)
{
    if (!IsValid(PlacementAnchor))
    {
        return false;
    }
    const AActor* Owner = PlacementAnchor->GetOwner();
    if (!IsValid(Owner) || PlacementAnchor != Owner->GetRootComponent())
    {
        return false;
    }

    FString Match;
    for (const FName& Tag : Owner->Tags)
    {
        const FString TagValue = Tag.ToString();
        if (!TagValue.StartsWith(StableSemanticTagPrefix, ESearchCase::CaseSensitive))
        {
            continue;
        }
        const FString Candidate = TagValue.RightChop(FCString::Strlen(StableSemanticTagPrefix));
        if (!IsStablePlacementAnchorSemanticId(Candidate))
        {
            continue;
        }
        if (!Match.IsEmpty() && Match != Candidate)
        {
            return false;
        }
        Match = Candidate;
    }
    if (Match.IsEmpty() ||
        !IsUniqueStablePlacementAnchor(Owner->GetWorld(), Match, Owner))
    {
        return false;
    }
    OutSemanticId = MoveTemp(Match);
    return true;
}

bool NormalizeStoredPlacementAnchor(UWorld* World,
                                    const FString& Value,
                                    FString& OutSemanticId)
{
    return CanonicalizePlacementAnchorSemanticId(Value, OutSemanticId) &&
        IsUniqueStablePlacementAnchor(World, OutSemanticId);
}

FString CarrierSemanticId(const AActor* Carrier)
{
    if (const AVistaPlayableHomeCharacter* Player =
            Cast<AVistaPlayableHomeCharacter>(Carrier))
    {
        return Player->SemanticId;
    }
    if (const AVistaHomeNpcCharacter* Npc = Cast<AVistaHomeNpcCharacter>(Carrier))
    {
        return Npc->SemanticId;
    }
    if (IsValid(Carrier) &&
        Carrier->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        return IVistaInteractable::Execute_VistaGetSemanticId(
            const_cast<AActor*>(Carrier));
    }
    return FString();
}

AActor* ResolveCarrier(UWorld* World, const FString& SemanticId)
{
    if (!IsValid(World) || SemanticId.IsEmpty())
    {
        return nullptr;
    }
    const FName RawTag(*SemanticId);
    const FName StableTag(*(FString(TEXT("VistaSemanticId=")) + SemanticId));
    AActor* Match = nullptr;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (It->ActorHasTag(RawTag) || It->ActorHasTag(StableTag))
        {
            if (Match != nullptr)
            {
                return nullptr;
            }
            Match = *It;
        }
    }
    return Match;
}

AVistaContainerActor* ResolveStorageContainer(
    UWorld* World,
    const FString& SemanticId)
{
    if (!IsValid(World) || SemanticId.IsEmpty())
    {
        return nullptr;
    }
    AVistaContainerActor* Match = nullptr;
    for (TActorIterator<AVistaContainerActor> It(World); It; ++It)
    {
        if (It->SemanticId != SemanticId)
        {
            continue;
        }
        if (Match != nullptr)
        {
            return nullptr;
        }
        Match = *It;
    }
    return Match;
}

AActor* CarrierInventoryItem(AActor* Carrier)
{
    return IsValid(Carrier) &&
        Carrier->GetClass()->ImplementsInterface(UVistaItemCarrier::StaticClass())
        ? IVistaItemCarrier::Execute_VistaGetHeldItem(Carrier)
        : nullptr;
}

bool CarrierInventoryIsEmpty(AActor* Carrier)
{
    return IsValid(Carrier) && !IsValid(CarrierInventoryItem(Carrier));
}

bool CarrierInventoryHolds(AActor* Carrier, const AActor* Item)
{
    return IsValid(Carrier) && IsValid(Item) &&
        CarrierInventoryItem(Carrier) == Item;
}
}

AVistaPickupActor::AVistaPickupActor()
{
    Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PickupMesh"));
    SetRootComponent(Mesh);
    Mesh->SetCollisionProfileName(UCollisionProfile::PhysicsActor_ProfileName);
    Mesh->SetSimulatePhysics(true);
    Mesh->SetGenerateOverlapEvents(true);
    PhysicalDisposition.CollisionEnabled =
        static_cast<uint8>(Mesh->GetCollisionEnabled());
    PhysicalDisposition.CollisionProfileName =
        UCollisionProfile::PhysicsActor_ProfileName;

    PresentationMesh =
        CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PresentationMesh"));
    PresentationMesh->SetupAttachment(Mesh);
    PresentationMesh->SetMobility(EComponentMobility::Movable);
    PresentationMesh->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
    PresentationMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    PresentationMesh->SetSimulatePhysics(false);
    PresentationMesh->SetGenerateOverlapEvents(false);
    PresentationMesh->SetCanEverAffectNavigation(false);
    PresentationMesh->SetVisibility(false, false);
    AllowedAffordances = {
        EVistaAffordance::Inspect,
        EVistaAffordance::PickUp,
        EVistaAffordance::Drop,
        EVistaAffordance::Place,
        EVistaAffordance::Pour,
        EVistaAffordance::Insert,
        EVistaAffordance::Remove};

    LiquidState.bPourable = bPourable;
    LiquidState.LiquidType = InitialLiquidType;
    LiquidState.CapacityMilliliters = LiquidCapacityMilliliters;
    LiquidState.AmountMilliliters =
        LiquidCapacityMilliliters * InitialLiquidLevel;
}

bool AVistaPickupActor::ConfigurePresentationMesh(
    UStaticMesh* StaticMesh,
    const FTransform& RelativeTransform)
{
    if (!IsValid(PresentationMesh) || !IsValid(StaticMesh) ||
        RelativeTransform.ContainsNaN())
    {
        return false;
    }

    PresentationMesh->SetStaticMesh(StaticMesh);
    PresentationMesh->SetRelativeTransform(RelativeTransform);
    RefreshPresentationState();
    return true;
}

void AVistaPickupActor::ClearPresentationMesh()
{
    if (!IsValid(PresentationMesh))
    {
        return;
    }
    PresentationMesh->SetStaticMesh(nullptr);
    PresentationMesh->SetRelativeTransform(FTransform::Identity);
    Mesh->SetVisibility(true, false);
    RefreshPresentationState();
}

bool AVistaPickupActor::HasPresentationMesh() const
{
    return IsValid(PresentationMesh) && IsValid(PresentationMesh->GetStaticMesh());
}

void AVistaPickupActor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    RefreshPresentationState();
}

void AVistaPickupActor::BeginPlay()
{
    Super::BeginPlay();
    RefreshPresentationState();
    NormalizePlacementState();
    if (HasAuthority())
    {
        FVistaLiquidStateSnapshot Fallback;
        Fallback.bPourable = bPourable ||
            InitialStateValues.Contains(FilledKey) ||
            InitialStateValues.Contains(LiquidLevelKey);
        Fallback.LiquidType = InitialLiquidType;
        Fallback.CapacityMilliliters = LiquidCapacityMilliliters;
        Fallback.AmountMilliliters =
            LiquidCapacityMilliliters * InitialLiquidLevel;
        FVistaLiquidStateSnapshot InitialState;
        FName Code;
        const FVistaEntityRuntimeState AuthoredState =
            Super::VistaGetRuntimeState_Implementation();
        if (!ReadLiquidState(AuthoredState, Fallback, InitialState, Code))
        {
            InitialState = Fallback;
            if (!ValidateLiquidState(InitialState, Code))
            {
                InitialState = FVistaLiquidStateSnapshot();
                InitialState.CapacityMilliliters = 250.0f;
                InitialState.LiquidType = TEXT("generic");
            }
        }
        SetLiquidState(InitialState);
    }
    else
    {
        SyncRuntimeLiquidValues();
    }
}

void AVistaPickupActor::EndPlay(
    const EEndPlayReason::Type EndPlayReason)
{
    ReleaseActiveStorageReservationForEndPlay();
    ReleaseActivePourReservationForEndPlay();
    Super::EndPlay(EndPlayReason);
}

FString AVistaPickupActor::GetContainedInSemanticId() const
{
    const AVistaContainerActor* Container =
        PhysicalDisposition.StorageContainer.Get();
    return PhysicalDisposition.Disposition == EVistaPickupDisposition::Contained &&
            IsValid(Container)
        ? Container->SemanticId : FString();
}

bool AVistaPickupActor::IsContainedIn(
    const AVistaContainerActor* Container) const
{
    return PhysicalDisposition.Disposition == EVistaPickupDisposition::Contained &&
        IsValid(Container) &&
        PhysicalDisposition.StorageContainer.Get() == Container &&
        GetContainedInSemanticId() == Container->SemanticId;
}

void AVistaPickupActor::ReleaseActivePourReservationForEndPlay()
{
    if (!HasAuthority())
    {
        return;
    }
    UVistaActionExecutorComponent* Executor =
        ActiveTransactionExecutor.Get();
    const FName CommandId = ActiveTransactionCommandId;
    AVistaLiquidReceiverActor* Receiver = ActivePourReceiver.Get();
    if (Executor != nullptr && !CommandId.IsNone() &&
        Receiver != nullptr &&
        IsPourTransactionReservedBy(Executor, CommandId, Receiver))
    {
        Receiver->ReleaseReservationForSourceEndPlay(
            this, Executor, CommandId);
    }

    // Clear only the identity captured on entry. A different transaction can
    // never be released as a side effect of peer teardown.
    if (ActiveTransactionExecutor.Get() == Executor &&
        ActiveTransactionCommandId == CommandId)
    {
        ActivePourReceiver.Reset();
        ActiveTransactionExecutor.Reset();
        ActiveTransactionCommandId = NAME_None;
    }
}

void AVistaPickupActor::GetLifetimeReplicatedProps(
    TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AVistaPickupActor, PhysicalDisposition);
    DOREPLIFETIME(AVistaPickupActor, LiquidState);
}

FVistaEntityRuntimeState AVistaPickupActor::VistaGetRuntimeState_Implementation() const
{
    FVistaEntityRuntimeState State = Super::VistaGetRuntimeState_Implementation();
    State.bPortable = bPortable;
    const bool bHeld =
        PhysicalDisposition.Disposition == EVistaPickupDisposition::Held &&
        IsValid(PhysicalDisposition.Carrier.Get());
    State.Values.Add(TEXT("held"), bHeld ? TEXT("true") : TEXT("false"));
    State.Values.Add(
        TEXT("held_by"),
        bHeld ? CarrierSemanticId(PhysicalDisposition.Carrier.Get()) : FString());
    if (bHeld)
    {
        State.Values.Remove(TEXT("placed_at"));
    }
    else if (PhysicalDisposition.Disposition == EVistaPickupDisposition::Placed)
    {
        State.Values.Add(
            TEXT("placed_at"), PhysicalDisposition.PlacementAnchorSemanticId);
    }
    else
    {
        State.Values.Remove(TEXT("placed_at"));
    }
    const FString ContainedIn = GetContainedInSemanticId();
    if (ContainedIn.IsEmpty())
    {
        State.Values.Remove(ContainedInKey);
    }
    else
    {
        State.Values.Add(ContainedInKey, ContainedIn);
    }
    State.Values.Add(
        PourableKey, LiquidState.bPourable ? TEXT("true") : TEXT("false"));
    State.Values.Add(
        FilledKey, LiquidState.IsFilled() ? TEXT("true") : TEXT("false"));
    State.Values.Add(LiquidTypeKey, LiquidState.LiquidType.ToString());
    State.Values.Add(
        LiquidCapacityKey,
        FString::SanitizeFloat(LiquidState.CapacityMilliliters));
    State.Values.Add(
        LiquidAmountKey,
        FString::SanitizeFloat(LiquidState.AmountMilliliters));
    State.Values.Add(
        LiquidLevelKey,
        FString::SanitizeFloat(LiquidState.GetLiquidLevel()));
    return State;
}

bool AVistaPickupActor::ValidateLiquidState(
    const FVistaLiquidStateSnapshot& State,
    FName& OutCode)
{
    if (!FMath::IsFinite(State.CapacityMilliliters) ||
        State.CapacityMilliliters < 1.0f ||
        State.CapacityMilliliters > 100000.0f ||
        !FMath::IsFinite(State.AmountMilliliters) ||
        State.AmountMilliliters < 0.0f ||
        State.AmountMilliliters > State.CapacityMilliliters)
    {
        OutCode = TEXT("LIQUID_CAPACITY_OR_AMOUNT_INVALID");
        return false;
    }
    if (State.IsFilled() && !IsClosedLiquidType(State.LiquidType))
    {
        OutCode = TEXT("LIQUID_TYPE_REQUIRED");
        return false;
    }
    if (!State.LiquidType.IsNone() && !IsClosedLiquidType(State.LiquidType))
    {
        OutCode = TEXT("LIQUID_TYPE_INVALID");
        return false;
    }
    OutCode = TEXT("LIQUID_STATE_VALID");
    return true;
}

bool AVistaPickupActor::ReadLiquidState(
    const FVistaEntityRuntimeState& State,
    const FVistaLiquidStateSnapshot& Fallback,
    FVistaLiquidStateSnapshot& OutState,
    FName& OutCode) const
{
    OutState = Fallback;
    if (const FString* PourableValue = State.Values.Find(PourableKey))
    {
        if (!ParseStrictBoolean(*PourableValue, OutState.bPourable))
        {
            OutCode = TEXT("POURABLE_STATE_INVALID");
            return false;
        }
    }
    if (const FString* TypeValue = State.Values.Find(LiquidTypeKey))
    {
        OutState.LiquidType = TypeValue->IsEmpty()
            ? NAME_None : FName(**TypeValue);
    }
    if (const FString* CapacityValue = State.Values.Find(LiquidCapacityKey))
    {
        if (!ParseFiniteFloat(
                *CapacityValue, OutState.CapacityMilliliters))
        {
            OutCode = TEXT("LIQUID_CAPACITY_INVALID");
            return false;
        }
    }

    bool bAmountPresent = false;
    if (const FString* AmountValue = State.Values.Find(LiquidAmountKey))
    {
        bAmountPresent = true;
        if (!ParseFiniteFloat(*AmountValue, OutState.AmountMilliliters))
        {
            OutCode = TEXT("LIQUID_AMOUNT_INVALID");
            return false;
        }
    }
    bool bLevelPresent = false;
    float Level = 0.0f;
    if (const FString* LevelValue = State.Values.Find(LiquidLevelKey))
    {
        bLevelPresent = true;
        if (!ParseFiniteFloat(*LevelValue, Level) ||
            Level < 0.0f || Level > 1.0f)
        {
            OutCode = TEXT("LIQUID_LEVEL_INVALID");
            return false;
        }
        const float LevelAmount = OutState.CapacityMilliliters * Level;
        if (bAmountPresent &&
            !FMath::IsNearlyEqual(
                OutState.AmountMilliliters, LevelAmount, 0.01f))
        {
            OutCode = TEXT("LIQUID_AMOUNT_LEVEL_MISMATCH");
            return false;
        }
        OutState.AmountMilliliters = LevelAmount;
    }

    if (const FString* FilledValue = State.Values.Find(FilledKey))
    {
        bool bFilled = false;
        if (!ParseStrictBoolean(*FilledValue, bFilled))
        {
            OutCode = TEXT("LIQUID_FILLED_STATE_INVALID");
            return false;
        }
        if (!bAmountPresent && !bLevelPresent)
        {
            OutState.AmountMilliliters =
                bFilled ? OutState.CapacityMilliliters : 0.0f;
        }
        else if (bFilled != OutState.IsFilled())
        {
            OutCode = TEXT("LIQUID_FILLED_LEVEL_MISMATCH");
            return false;
        }
    }
    return ValidateLiquidState(OutState, OutCode);
}

void AVistaPickupActor::SyncRuntimeLiquidValues()
{
    RuntimeStateValues.Add(
        PourableKey, LiquidState.bPourable ? TEXT("true") : TEXT("false"));
    RuntimeStateValues.Add(
        FilledKey, LiquidState.IsFilled() ? TEXT("true") : TEXT("false"));
    RuntimeStateValues.Add(LiquidTypeKey, LiquidState.LiquidType.ToString());
    RuntimeStateValues.Add(
        LiquidCapacityKey,
        FString::SanitizeFloat(LiquidState.CapacityMilliliters));
    RuntimeStateValues.Add(
        LiquidAmountKey,
        FString::SanitizeFloat(LiquidState.AmountMilliliters));
    RuntimeStateValues.Add(
        LiquidLevelKey,
        FString::SanitizeFloat(LiquidState.GetLiquidLevel()));
}

void AVistaPickupActor::SetLiquidState(
    const FVistaLiquidStateSnapshot& State)
{
    LiquidState = State;
    SyncRuntimeLiquidValues();
    if (HasAuthority())
    {
        ForceNetUpdate();
    }
}

bool AVistaPickupActor::ValidatePublicStatePatch(
    const FVistaEntityRuntimeState& State,
    FName& OutCode) const
{
    const FVistaEntityRuntimeState Current = VistaGetRuntimeState_Implementation();
    if ((!State.SemanticId.IsEmpty() && State.SemanticId != SemanticId) ||
        !TransformBitsEqual(State.Transform, Current.Transform))
    {
        OutCode = TEXT("PHYSICAL_TRANSFORM_PATCH_REJECTED");
        return false;
    }
    if (State.bPortable != Current.bPortable)
    {
        OutCode = TEXT("PORTABLE_PHYSICS_PATCH_REJECTED");
        return false;
    }
    for (const FName Key : {FName(TEXT("held")), FName(TEXT("held_by")),
                            FName(TEXT("placed_at")), ContainedInKey})
    {
        const FString* Requested = State.Values.Find(Key);
        const FString* Existing = Current.Values.Find(Key);
        if ((Requested == nullptr) != (Existing == nullptr) ||
            (Requested != nullptr && *Requested != *Existing))
        {
            OutCode = TEXT("PHYSICAL_STATE_PATCH_REJECTED");
            return false;
        }
    }
    for (const FName Key : {
             FName(TEXT("attachment_parent")),
             FName(TEXT("attachment_socket")),
             FName(TEXT("simulate_physics")),
             FName(TEXT("collision_enabled")),
             FName(TEXT("collision_profile")),
             FName(TEXT("linear_velocity")),
             FName(TEXT("angular_velocity")),
             FName(TEXT("physical_disposition"))})
    {
        if (State.Values.Contains(Key))
        {
            OutCode = TEXT("PHYSICS_METADATA_PATCH_REJECTED");
            return false;
        }
    }
    for (const TPair<FName, FString>& Pair : State.Values)
    {
        const FString Key = Pair.Key.ToString().ToLower();
        if (Key.StartsWith(TEXT("attachment")) ||
            Key.StartsWith(TEXT("physics")) ||
            Key.StartsWith(TEXT("collision")) ||
            Key.StartsWith(TEXT("simulate")) ||
            Key.Contains(TEXT("velocity")) ||
            Key == TEXT("physical_disposition"))
        {
            OutCode = TEXT("PHYSICS_METADATA_PATCH_REJECTED");
            return false;
        }
    }
    OutCode = TEXT("PICKUP_NON_PHYSICAL_PATCH_ALLOWED");
    return true;
}

FVistaInteractionResult AVistaPickupActor::VistaApplyRuntimeState_Implementation(
    const FVistaEntityRuntimeState& State)
{
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected, TEXT("AUTHORITY_REQUIRED"), SemanticId);
    }
    if (ActiveTransactionExecutor.IsValid() ||
        !ActiveTransactionCommandId.IsNone())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Busy,
            TEXT("PICKUP_TARGET_RESERVED"),
            SemanticId);
    }

    FName ValidationCode;
    if (!ValidatePublicStatePatch(State, ValidationCode))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected, ValidationCode, SemanticId);
    }
    FVistaLiquidStateSnapshot NewLiquidState;
    if (!ReadLiquidState(
            State, LiquidState, NewLiquidState, ValidationCode))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            ValidationCode,
            SemanticId);
    }
    if (NewLiquidState.bPourable != LiquidState.bPourable ||
        !ScalarBitsEqual(
            NewLiquidState.CapacityMilliliters,
            LiquidState.CapacityMilliliters))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("LIQUID_AUTHORITY_PATCH_REJECTED"),
            SemanticId);
    }
    // A public patch may change only non-physical values/presentation. Never
    // forward caller-owned transform data to the semantic-actor base, even
    // when it happens to compare equal to the current physical transform.
    FVistaEntityRuntimeState NonPhysicalState = State;
    NonPhysicalState.Transform = GetActorTransform();
    NonPhysicalState.bPortable = bPortable;
    const FVistaInteractionResult BaseResult =
        Super::VistaApplyRuntimeState_Implementation(NonPhysicalState);
    if (!BaseResult.IsSuccess())
    {
        return BaseResult;
    }
    SyncRuntimeDispositionValues();
    SetLiquidState(NewLiquidState);
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("PICKUP_NON_PHYSICAL_STATE_APPLIED"));
}

FVistaInteractionResult AVistaPickupActor::VistaInteract_Implementation(
    const FVistaInteractionRequest& Request)
{
    const FVistaInteractionResult Validation = ValidateRequest(Request);
    if (!Validation.IsSuccess())
    {
        return Validation;
    }
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected, TEXT("AUTHORITY_REQUIRED"), SemanticId);
    }

    if (Request.Affordance == EVistaAffordance::Pour ||
        Request.Affordance == EVistaAffordance::Insert ||
        Request.Affordance == EVistaAffordance::Remove ||
        UVistaActionExecutorComponent::IsPhysicalAffordance(Request.Affordance))
    {
        // Physical state is committed only by UVistaActionExecutorComponent at
        // a verified contact notify. The interface remains readable and keeps
        // non-physical source compatibility, but cannot bypass the transaction.
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("ACTION_EXECUTOR_REQUIRED"),
            SemanticId);
    }
    return Super::VistaInteract_Implementation(Request);
}

bool AVistaPickupActor::TryReserveTransaction(
    UVistaActionExecutorComponent* Executor,
    FName CommandId)
{
    if (!IsValid(Executor) || CommandId.IsNone())
    {
        return false;
    }
    if (ActiveTransactionExecutor.IsValid() ||
        !ActiveTransactionCommandId.IsNone() ||
        ActivePourReceiver.IsValid() ||
        ActiveStorageContainer.IsValid())
    {
        return false;
    }
    ActiveTransactionExecutor = Executor;
    ActiveTransactionCommandId = CommandId;
    return true;
}

void AVistaPickupActor::ReleaseTransaction(
    UVistaActionExecutorComponent* Executor,
    FName CommandId)
{
    if (ActiveTransactionExecutor.Get() == Executor &&
        ActiveTransactionCommandId == CommandId &&
        !ActivePourReceiver.IsValid() &&
        !ActiveStorageContainer.IsValid())
    {
        ActiveTransactionExecutor.Reset();
        ActiveTransactionCommandId = NAME_None;
    }
}

bool AVistaPickupActor::IsTransactionReservedBy(
    const UVistaActionExecutorComponent* Executor,
    FName CommandId) const
{
    return IsValid(Executor) && !CommandId.IsNone() &&
        ActiveTransactionExecutor.Get() == Executor &&
        ActiveTransactionCommandId == CommandId;
}

bool AVistaPickupActor::TryReservePourTransaction(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    AVistaLiquidReceiverActor* Receiver)
{
    if (!HasAuthority() || !IsValid(Receiver) ||
        !TryReserveTransaction(Executor, CommandId))
    {
        return false;
    }
    ActivePourReceiver = Receiver;
    return IsPourTransactionReservedBy(Executor, CommandId, Receiver);
}

bool AVistaPickupActor::ReleasePourTransactionReservation(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    AVistaLiquidReceiverActor* Receiver)
{
    if (!HasAuthority() ||
        !IsPourTransactionReservedBy(Executor, CommandId, Receiver))
    {
        return false;
    }
#if WITH_DEV_AUTOMATION_TESTS
    if (bFailNextPourRelease)
    {
        bFailNextPourRelease = false;
        return false;
    }
#endif
    ActivePourReceiver.Reset();
    ActiveTransactionExecutor.Reset();
    ActiveTransactionCommandId = NAME_None;
    return IsTransactionUnreserved();
}

bool AVistaPickupActor::ReleasePourReservationForReceiverEndPlay(
    AVistaLiquidReceiverActor* Receiver,
    UVistaActionExecutorComponent* Executor,
    FName CommandId)
{
    if (!HasAuthority() || Receiver == nullptr || Executor == nullptr ||
        CommandId.IsNone() || ActiveTransactionExecutor.Get() != Executor ||
        ActiveTransactionCommandId != CommandId ||
        ActivePourReceiver.Get(true) != Receiver)
    {
        return false;
    }
    ActivePourReceiver.Reset();
    ActiveTransactionExecutor.Reset();
    ActiveTransactionCommandId = NAME_None;
    return IsTransactionUnreserved();
}

bool AVistaPickupActor::IsPourTransactionReservedBy(
    const UVistaActionExecutorComponent* Executor,
    FName CommandId,
    const AVistaLiquidReceiverActor* Receiver) const
{
    return Receiver != nullptr &&
        IsTransactionReservedBy(Executor, CommandId) &&
        ActivePourReceiver.Get() == Receiver;
}

bool AVistaPickupActor::IsTransactionUnreserved() const
{
    return !ActiveTransactionExecutor.IsValid() &&
        ActiveTransactionCommandId.IsNone() &&
        !ActivePourReceiver.IsValid() &&
        !ActiveStorageContainer.IsValid();
}

bool AVistaPickupActor::TryReserveStorageTransaction(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    AVistaContainerActor* Container)
{
    if (!HasAuthority() || !IsValid(Container) ||
        !TryReserveTransaction(Executor, CommandId))
    {
        return false;
    }
    ActiveStorageContainer = Container;
    return IsStorageTransactionReservedBy(Executor, CommandId, Container);
}

bool AVistaPickupActor::ReleaseStorageTransactionReservation(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    AVistaContainerActor* Container)
{
    if (!HasAuthority() ||
        !IsStorageTransactionReservedBy(Executor, CommandId, Container))
    {
        return false;
    }
    ActiveStorageContainer.Reset();
    ActiveTransactionExecutor.Reset();
    ActiveTransactionCommandId = NAME_None;
    return IsTransactionUnreserved();
}

bool AVistaPickupActor::ReleaseStorageReservationForContainerEndPlay(
    AVistaContainerActor* Container,
    UVistaActionExecutorComponent* Executor,
    const FName CommandId)
{
    if (!HasAuthority() || Container == nullptr || Executor == nullptr ||
        CommandId.IsNone() || ActiveTransactionExecutor.Get() != Executor ||
        ActiveTransactionCommandId != CommandId ||
        ActiveStorageContainer.Get(true) != Container)
    {
        return false;
    }
    ActiveStorageContainer.Reset();
    ActiveTransactionExecutor.Reset();
    ActiveTransactionCommandId = NAME_None;
    return IsTransactionUnreserved();
}

bool AVistaPickupActor::IsStorageTransactionReservedBy(
    const UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    const AVistaContainerActor* Container) const
{
    return Container != nullptr &&
        IsTransactionReservedBy(Executor, CommandId) &&
        ActiveStorageContainer.Get() == Container;
}

void AVistaPickupActor::ReleaseActiveStorageReservationForEndPlay()
{
    if (!HasAuthority())
    {
        return;
    }
    UVistaActionExecutorComponent* Executor =
        ActiveTransactionExecutor.Get();
    const FName CommandId = ActiveTransactionCommandId;
    AVistaContainerActor* Container = ActiveStorageContainer.Get();
    if (Executor != nullptr && !CommandId.IsNone() && Container != nullptr &&
        IsStorageTransactionReservedBy(Executor, CommandId, Container))
    {
        Container->ReleaseReservationForItemEndPlay(
            this, Executor, CommandId);
    }
    if (ActiveTransactionExecutor.Get() == Executor &&
        ActiveTransactionCommandId == CommandId)
    {
        ActiveStorageContainer.Reset();
        ActiveTransactionExecutor.Reset();
        ActiveTransactionCommandId = NAME_None;
    }
}

bool AVistaPickupActor::CapturePourTransactionState(
    const AActor* ExpectedRequester,
    FVistaLiquidStateSnapshot& OutLiquid,
    FVistaPickupPhysicalStateSnapshot& OutPhysical,
    FName& OutCode) const
{
    OutLiquid = FVistaLiquidStateSnapshot();
    OutPhysical = FVistaPickupPhysicalStateSnapshot();
    if (!HasAuthority() || !IsValid(ExpectedRequester) ||
        GetCarrier() != ExpectedRequester)
    {
        OutCode = TEXT("POUR_SOURCE_NOT_HELD_BY_REQUESTER");
        return false;
    }
    if (!LiquidState.bPourable)
    {
        OutCode = TEXT("POUR_SOURCE_NOT_POURABLE");
        return false;
    }
    if (!ValidateLiquidState(LiquidState, OutCode) ||
        !LiquidState.IsFilled())
    {
        if (OutCode == TEXT("LIQUID_STATE_VALID"))
        {
            OutCode = TEXT("POUR_SOURCE_EMPTY");
        }
        return false;
    }

    USceneComponent* AttachmentParent = nullptr;
    AActor* Carrier = nullptr;
    EVistaPickupDisposition Disposition = EVistaPickupDisposition::Free;
    if (!CapturePhysicalState(
            OutPhysical, AttachmentParent, Carrier, Disposition) ||
        Carrier != ExpectedRequester ||
        Disposition != EVistaPickupDisposition::Held ||
        !OutPhysical.bHeld || !OutPhysical.bHasAttachmentParent)
    {
        OutCode = TEXT("POUR_SOURCE_HELD_STATE_INVALID");
        return false;
    }
    OutLiquid = LiquidState;
    OutCode = TEXT("POUR_SOURCE_READY");
    return true;
}

FVistaInteractionResult AVistaPickupActor::CommitPourOut(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    const FVistaLiquidStateSnapshot& ExpectedBefore,
    float TransferMilliliters)
{
    if (!IsTransactionReservedBy(Executor, CommandId))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("TRANSACTION_RESERVATION_REQUIRED"),
            SemanticId);
    }
    if (!HasAuthority() || !LiquidStatesBitExact(LiquidState, ExpectedBefore) ||
        !FMath::IsFinite(TransferMilliliters) ||
        TransferMilliliters <= 0.0f ||
        TransferMilliliters > ExpectedBefore.AmountMilliliters)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("POUR_SOURCE_STATE_DRIFT"),
            SemanticId);
    }
    FVistaLiquidStateSnapshot After = ExpectedBefore;
    After.AmountMilliliters =
        FMath::Max(0.0f, ExpectedBefore.AmountMilliliters - TransferMilliliters);
    FName Code;
    if (!ValidateLiquidState(After, Code))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            Code,
            SemanticId);
    }
    SetLiquidState(After);
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("POUR_SOURCE_DEBITED"));
}

FVistaInteractionResult AVistaPickupActor::RestorePourLiquidState(
    UVistaActionExecutorComponent* Executor,
    FName CommandId,
    const FVistaLiquidStateSnapshot& State)
{
    if (!IsTransactionReservedBy(Executor, CommandId))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("TRANSACTION_RESERVATION_REQUIRED"),
            SemanticId);
    }
    FName Code;
    if (!HasAuthority() || !ValidateLiquidState(State, Code))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            HasAuthority() ? Code : FName(TEXT("AUTHORITY_REQUIRED")),
            SemanticId);
    }
    SetLiquidState(State);
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("POUR_SOURCE_STATE_RESTORED"));
}

bool AVistaPickupActor::PourStateMatches(
    const FVistaLiquidStateSnapshot& ExpectedLiquid,
    const FVistaPickupPhysicalStateSnapshot& ExpectedPhysical) const
{
    FVistaPickupPhysicalStateSnapshot ActualPhysical;
    USceneComponent* AttachmentParent = nullptr;
    AActor* Carrier = nullptr;
    EVistaPickupDisposition Disposition = EVistaPickupDisposition::Free;
    return CapturePhysicalState(
               ActualPhysical, AttachmentParent, Carrier, Disposition) &&
        LiquidStatesBitExact(LiquidState, ExpectedLiquid) &&
        PhysicalSnapshotsBitExact(ActualPhysical, ExpectedPhysical);
}

bool AVistaPickupActor::CaptureStorageTransactionState(
    const AActor* ExpectedRequester,
    const AVistaContainerActor* ExpectedContainer,
    const EVistaAffordance Affordance,
    FVistaPickupPhysicalStateSnapshot& OutPhysical,
    FName& OutCode) const
{
    OutPhysical = FVistaPickupPhysicalStateSnapshot();
    if (!HasAuthority() || !IsValid(ExpectedRequester) ||
        !IsValid(ExpectedContainer) || !bPortable ||
        (Affordance != EVistaAffordance::Insert &&
         Affordance != EVistaAffordance::Remove))
    {
        OutCode = !bPortable
            ? FName(TEXT("ITEM_NOT_PORTABLE"))
            : FName(TEXT("STORAGE_PARTICIPANT_INVALID"));
        return false;
    }
    USceneComponent* AttachmentParent = nullptr;
    AActor* Carrier = nullptr;
    EVistaPickupDisposition Disposition = EVistaPickupDisposition::Free;
    if (!CapturePhysicalState(
            OutPhysical, AttachmentParent, Carrier, Disposition))
    {
        OutCode = TEXT("STORAGE_ITEM_PHYSICAL_STATE_INVALID");
        return false;
    }
    if (Affordance == EVistaAffordance::Insert)
    {
        if (Disposition != EVistaPickupDisposition::Held ||
            Carrier != ExpectedRequester || !OutPhysical.bHeld ||
            !OutPhysical.bHasAttachmentParent ||
            OutPhysical.InventoryItemSemanticId != SemanticId ||
            !OutPhysical.ContainedInSemanticId.IsEmpty())
        {
            OutCode = TEXT("INSERT_ITEM_NOT_EXACTLY_HELD");
            return false;
        }
        OutCode = TEXT("INSERT_ITEM_READY");
        return true;
    }
    if (Disposition != EVistaPickupDisposition::Contained ||
        Carrier != nullptr || OutPhysical.bHeld ||
        !OutPhysical.bHasAttachmentParent ||
        !IsContainedIn(ExpectedContainer) ||
        OutPhysical.ContainedInSemanticId != ExpectedContainer->SemanticId ||
        !CarrierInventoryIsEmpty(const_cast<AActor*>(ExpectedRequester)))
    {
        OutCode = !CarrierInventoryIsEmpty(
                const_cast<AActor*>(ExpectedRequester))
            ? FName(TEXT("CARRIER_SLOT_UNAVAILABLE"))
            : FName(TEXT("REMOVE_ITEM_NOT_IN_EXACT_CONTAINER"));
        return false;
    }
    OutCode = TEXT("REMOVE_ITEM_READY");
    return true;
}

FVistaInteractionResult AVistaPickupActor::CommitStorageInsert(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    AActor* Requester,
    AVistaContainerActor* Container,
    USceneComponent* ContentsAnchor)
{
    if (!IsStorageTransactionReservedBy(Executor, CommandId, Container))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("STORAGE_RESERVATION_REQUIRED"),
            SemanticId);
    }
    FVistaPickupPhysicalStateSnapshot Before;
    FName Code;
    if (!IsValid(ContentsAnchor) ||
        ContentsAnchor != Container->ContentsAnchor ||
        !CaptureStorageTransactionState(
            Requester, Container, EVistaAffordance::Insert, Before, Code))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            Code.IsNone() ? FName(TEXT("CONTENTS_ANCHOR_INVALID")) : Code,
            SemanticId);
    }
    AActor* PreviousCarrier = GetCarrier();
    const FVistaPickupReplicatedDisposition Previous = PhysicalDisposition;
    PhysicalDisposition.Disposition = EVistaPickupDisposition::Contained;
    PhysicalDisposition.Carrier = nullptr;
    PhysicalDisposition.PlacementAnchorSemanticId.Reset();
    PhysicalDisposition.StorageContainer = Container;
    PhysicalDisposition.WorldTransform =
        ContentsAnchor->GetComponentTransform();
    PhysicalDisposition.AttachmentRelativeTransform = FTransform::Identity;
    PhysicalDisposition.AttachmentSocketName = NAME_None;
    PhysicalDisposition.bSimulatePhysics = false;
    PhysicalDisposition.CollisionEnabled =
        static_cast<uint8>(ECollisionEnabled::NoCollision);
    PhysicalDisposition.CollisionProfileName =
        UCollisionProfile::NoCollision_ProfileName;
    PhysicalDisposition.LinearVelocity = FVector::ZeroVector;
    PhysicalDisposition.AngularVelocityDegrees = FVector::ZeroVector;
    if (!ApplyPhysicalDisposition())
    {
        PhysicalDisposition = Previous;
        const bool bRestored = ApplyPhysicalDisposition();
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            bRestored
                ? FName(TEXT("STORAGE_ATTACHMENT_FAILED"))
                : FName(TEXT("STORAGE_ATTACHMENT_ROLLBACK_FAILED")),
            SemanticId);
    }
    IVistaItemCarrier::Execute_VistaReleaseItem(PreviousCarrier, this);
    if (!CarrierInventoryIsEmpty(PreviousCarrier))
    {
        PhysicalDisposition = Previous;
        const bool bPhysicalRestored = ApplyPhysicalDisposition();
        const bool bInventoryRestored =
            CarrierInventoryHolds(PreviousCarrier, this) ||
            (CarrierInventoryIsEmpty(PreviousCarrier) &&
             IVistaItemCarrier::Execute_VistaTryClaimItem(
                 PreviousCarrier, this) &&
             CarrierInventoryHolds(PreviousCarrier, this));
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            bPhysicalRestored && bInventoryRestored
                ? FName(TEXT("STORAGE_CARRIER_RELEASE_FAILED"))
                : FName(TEXT("STORAGE_CARRIER_ROLLBACK_FAILED")),
            SemanticId);
    }
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("ITEM_INSERTED"));
}

#if WITH_DEV_AUTOMATION_TESTS
bool AVistaPickupActor::ConfigureLiquidStateForDevAutomation(
    const FVistaLiquidStateSnapshot& State,
    FName& OutCode)
{
    if (!HasAuthority() || ActiveTransactionExecutor.IsValid() ||
        !ActiveTransactionCommandId.IsNone() ||
        !ValidateLiquidState(State, OutCode))
    {
        if (!HasAuthority())
        {
            OutCode = TEXT("AUTHORITY_REQUIRED");
        }
        else if (ActiveTransactionExecutor.IsValid() ||
                 !ActiveTransactionCommandId.IsNone())
        {
            OutCode = TEXT("PICKUP_TARGET_RESERVED");
        }
        return false;
    }
    SetLiquidState(State);
    OutCode = TEXT("LIQUID_STATE_CONFIGURED_FOR_TEST");
    return true;
}

bool AVistaPickupActor::CapturePourStateForDevAutomation(
    FVistaLiquidStateSnapshot& OutLiquid,
    FVistaPickupPhysicalStateSnapshot& OutPhysical) const
{
    USceneComponent* AttachmentParent = nullptr;
    AActor* Carrier = nullptr;
    EVistaPickupDisposition Disposition = EVistaPickupDisposition::Free;
    OutLiquid = LiquidState;
    return CapturePhysicalState(
        OutPhysical, AttachmentParent, Carrier, Disposition);
}

bool AVistaPickupActor::IsReservedForDevAutomation(
    const UVistaActionExecutorComponent* Executor,
    FName CommandId) const
{
    return IsTransactionReservedBy(Executor, CommandId);
}

void AVistaPickupActor::FailNextPourReleaseForDevAutomation()
{
    bFailNextPourRelease = true;
}

void AVistaPickupActor::ReleasePourReservationForEndPlayForDevAutomation()
{
    ReleaseActivePourReservationForEndPlay();
}

void AVistaPickupActor::
    ReleaseStorageReservationForEndPlayForDevAutomation()
{
    ReleaseActiveStorageReservationForEndPlay();
}
#endif

FVistaInteractionResult AVistaPickupActor::CommitTransactionalInteraction(
    UVistaActionExecutorComponent* Executor,
    const FVistaInteractionRequest& Request,
    FName CommitCommandId,
    const FVector& ReleaseVelocity)
{
    if (!IsValid(Executor) || CommitCommandId.IsNone() ||
        ActiveTransactionExecutor.Get() != Executor ||
        ActiveTransactionCommandId != CommitCommandId)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("TRANSACTION_RESERVATION_REQUIRED"),
            SemanticId);
    }
    const FVistaInteractionResult Validation = ValidateRequest(Request);
    if (!Validation.IsSuccess())
    {
        return Validation;
    }
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected, TEXT("AUTHORITY_REQUIRED"), SemanticId);
    }
    switch (Request.Affordance)
    {
    case EVistaAffordance::PickUp:
        return TryAttachTo(Request.Requester);
    case EVistaAffordance::Drop:
        if (GetCarrier() != Request.Requester)
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::InvalidRequester,
                TEXT("NOT_ITEM_CARRIER"), SemanticId);
        }
        return ReleaseFromCarrier(ReleaseVelocity);
    case EVistaAffordance::Place:
        if (GetCarrier() != Request.Requester || !IsValid(Request.PlacementAnchor))
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::InvalidState,
                TEXT("PLACEMENT_ANCHOR_REQUIRED"), SemanticId);
        }
        return ReleaseFromCarrier(FVector::ZeroVector, Request.PlacementAnchor);
    default:
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Unsupported,
            TEXT("PHYSICAL_AFFORDANCE_REQUIRED"), SemanticId);
    }
}

FVistaInteractionResult AVistaPickupActor::CommitStorageRemove(
    UVistaActionExecutorComponent* Executor,
    const FName CommandId,
    AActor* Requester,
    AVistaContainerActor* Container)
{
    if (!IsStorageTransactionReservedBy(Executor, CommandId, Container))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("STORAGE_RESERVATION_REQUIRED"),
            SemanticId);
    }
    FVistaPickupPhysicalStateSnapshot Before;
    FName Code;
    if (!CaptureStorageTransactionState(
            Requester, Container, EVistaAffordance::Remove, Before, Code))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            Code,
            SemanticId);
    }
    return TryAttachTo(Requester);
}

FVistaInteractionResult AVistaPickupActor::TryAttachTo(AActor* Carrier)
{
    if (!bPortable)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState, TEXT("ITEM_NOT_PORTABLE"), SemanticId);
    }
    if (IsValid(GetCarrier()))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Busy, TEXT("ITEM_ALREADY_HELD"), SemanticId);
    }
    if (!IsValid(Carrier) || !Carrier->GetClass()->ImplementsInterface(UVistaItemCarrier::StaticClass()))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidRequester, TEXT("CARRIER_REQUIRED"), SemanticId);
    }
    FName CarryCode;
    USceneComponent* Anchor =
        UVistaActionExecutorComponent::PrepareCarryAnchor(Carrier, CarryCode);
    if (!IsValid(Anchor))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Busy,
            CarryCode,
            SemanticId);
    }
    if (!CarrierInventoryIsEmpty(Carrier) ||
        !IVistaItemCarrier::Execute_VistaTryClaimItem(Carrier, this))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Busy,
            TEXT("CARRIER_SLOT_UNAVAILABLE"),
            SemanticId);
    }
    if (!CarrierInventoryHolds(Carrier, this))
    {
        IVistaItemCarrier::Execute_VistaReleaseItem(Carrier, this);
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            CarrierInventoryIsEmpty(Carrier)
                ? FName(TEXT("CARRIER_CLAIM_VERIFY_FAILED"))
                : FName(TEXT("CARRIER_CLAIM_COMPENSATION_FAILED")),
            SemanticId);
    }

    FVistaPickupReplicatedDisposition Previous = PhysicalDisposition;
    Previous.WorldTransform = GetActorTransform();
    Previous.AttachmentRelativeTransform =
        GetRootComponent()->GetRelativeTransform();
    Previous.AttachmentSocketName = GetRootComponent()->GetAttachSocketName();
    Previous.bSimulatePhysics = Mesh->IsSimulatingPhysics();
    Previous.CollisionEnabled = static_cast<uint8>(Mesh->GetCollisionEnabled());
    Previous.CollisionProfileName = Mesh->GetCollisionProfileName();
    Previous.LinearVelocity = Mesh->GetPhysicsLinearVelocity();
    Previous.AngularVelocityDegrees =
        Mesh->GetPhysicsAngularVelocityInDegrees();
    PhysicalDisposition.Disposition = EVistaPickupDisposition::Held;
    PhysicalDisposition.Carrier = Carrier;
    PhysicalDisposition.PlacementAnchorSemanticId.Reset();
    PhysicalDisposition.StorageContainer = nullptr;
    PhysicalDisposition.WorldTransform = GetActorTransform();
    PhysicalDisposition.AttachmentRelativeTransform = FTransform::Identity;
    PhysicalDisposition.AttachmentSocketName = NAME_None;
    PhysicalDisposition.bSimulatePhysics = false;
    PhysicalDisposition.CollisionEnabled =
        static_cast<uint8>(ECollisionEnabled::NoCollision);
    PhysicalDisposition.CollisionProfileName =
        UCollisionProfile::NoCollision_ProfileName;
    PhysicalDisposition.LinearVelocity = FVector::ZeroVector;
    PhysicalDisposition.AngularVelocityDegrees = FVector::ZeroVector;
    if (!ApplyPhysicalDisposition() || !CarrierInventoryHolds(Carrier, this))
    {
        IVistaItemCarrier::Execute_VistaReleaseItem(Carrier, this);
        const bool bCarrierSlotReleased = CarrierInventoryIsEmpty(Carrier);
        PhysicalDisposition = Previous;
        const bool bPreviousRestored = ApplyPhysicalDisposition();
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            bPreviousRestored && bCarrierSlotReleased
                ? FName(TEXT("CARRY_ATTACHMENT_FAILED"))
                : FName(TEXT("CARRY_ATTACHMENT_ROLLBACK_FAILED")),
            SemanticId);
    }
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId, VistaGetRuntimeState_Implementation(), TEXT("ITEM_PICKED_UP"));
}

FVistaInteractionResult AVistaPickupActor::ReleaseFromCarrier(
    const FVector& LinearVelocity,
    USceneComponent* PlacementAnchor)
{
    if (!HasAuthority())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected, TEXT("AUTHORITY_REQUIRED"), SemanticId);
    }
    if (!IsValid(GetCarrier()))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState, TEXT("ITEM_NOT_HELD"), SemanticId);
    }

    FString PlacementAnchorSemanticId;
    if (IsValid(PlacementAnchor) &&
        !StablePlacementAnchorSemanticId(PlacementAnchor, PlacementAnchorSemanticId))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("PLACEMENT_ANCHOR_NOT_STABLE"), SemanticId);
    }

    AActor* PreviousCarrier = GetCarrier();
    if (!CarrierInventoryHolds(PreviousCarrier, this))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("CARRIER_INVENTORY_DIVERGED"),
            SemanticId);
    }
    FVistaPickupReplicatedDisposition Previous = PhysicalDisposition;
    Previous.WorldTransform = GetActorTransform();
    Previous.AttachmentRelativeTransform =
        GetRootComponent()->GetRelativeTransform();
    Previous.AttachmentSocketName = GetRootComponent()->GetAttachSocketName();
    Previous.bSimulatePhysics = Mesh->IsSimulatingPhysics();
    Previous.CollisionEnabled = static_cast<uint8>(Mesh->GetCollisionEnabled());
    Previous.CollisionProfileName = Mesh->GetCollisionProfileName();
    Previous.LinearVelocity = Mesh->GetPhysicsLinearVelocity();
    Previous.AngularVelocityDegrees =
        Mesh->GetPhysicsAngularVelocityInDegrees();
    PhysicalDisposition.Disposition = IsValid(PlacementAnchor)
        ? EVistaPickupDisposition::Placed : EVistaPickupDisposition::Free;
    PhysicalDisposition.Carrier = nullptr;
    PhysicalDisposition.PlacementAnchorSemanticId = PlacementAnchorSemanticId;
    PhysicalDisposition.StorageContainer = nullptr;
    PhysicalDisposition.WorldTransform = IsValid(PlacementAnchor)
        ? PlacementAnchor->GetComponentTransform() : GetActorTransform();
    PhysicalDisposition.AttachmentRelativeTransform = FTransform::Identity;
    PhysicalDisposition.AttachmentSocketName = NAME_None;
    PhysicalDisposition.bSimulatePhysics = !IsValid(PlacementAnchor) && bPortable;
    PhysicalDisposition.CollisionProfileName =
        UCollisionProfile::PhysicsActor_ProfileName;
    PhysicalDisposition.CollisionEnabled =
        static_cast<uint8>(ECollisionEnabled::QueryAndPhysics);
    PhysicalDisposition.LinearVelocity = IsValid(PlacementAnchor)
        ? FVector::ZeroVector : LinearVelocity;
    PhysicalDisposition.AngularVelocityDegrees = FVector::ZeroVector;
    if (!ApplyPhysicalDisposition())
    {
        PhysicalDisposition = Previous;
        const bool bPreviousRestored = ApplyPhysicalDisposition();
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            !bPreviousRestored ||
                    !CarrierInventoryHolds(PreviousCarrier, this)
                ? FName(TEXT("PHYSICAL_DISPOSITION_ROLLBACK_FAILED"))
                : IsValid(PlacementAnchor)
                    ? FName(TEXT("PLACEMENT_TRANSFORM_MISMATCH"))
                    : FName(TEXT("DROP_DISPOSITION_FAILED")),
            SemanticId);
    }
    IVistaItemCarrier::Execute_VistaReleaseItem(PreviousCarrier, this);
    if (!CarrierInventoryIsEmpty(PreviousCarrier))
    {
        PhysicalDisposition = Previous;
        const bool bPhysicalRestored = ApplyPhysicalDisposition();
        const bool bInventoryRestored =
            CarrierInventoryHolds(PreviousCarrier, this) ||
            (CarrierInventoryIsEmpty(PreviousCarrier) &&
             IVistaItemCarrier::Execute_VistaTryClaimItem(
                 PreviousCarrier, this) &&
             CarrierInventoryHolds(PreviousCarrier, this));
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            bPhysicalRestored && bInventoryRestored
                ? FName(TEXT("CARRIER_RELEASE_VERIFY_FAILED"))
                : FName(TEXT("CARRIER_RELEASE_ROLLBACK_FAILED")),
            SemanticId);
    }
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId, VistaGetRuntimeState_Implementation(),
        IsValid(PlacementAnchor) ? TEXT("ITEM_PLACED") : TEXT("ITEM_DROPPED"));
}

void AVistaPickupActor::OnRep_PhysicalDisposition()
{
    if (!ApplyPhysicalDisposition())
    {
        UE_LOG(
            LogTemp,
            Error,
            TEXT("VISTA_PICKUP_DISPOSITION_REJECTED semantic_id=%s disposition=%d"),
            *SemanticId,
            static_cast<int32>(PhysicalDisposition.Disposition));
    }
}

void AVistaPickupActor::OnRep_LiquidState()
{
    FName Code;
    if (!ValidateLiquidState(LiquidState, Code))
    {
        UE_LOG(
            LogTemp,
            Error,
            TEXT("VISTA_PICKUP_LIQUID_STATE_REJECTED semantic_id=%s code=%s"),
            *SemanticId,
            *Code.ToString());
        return;
    }
    SyncRuntimeLiquidValues();
}

void AVistaPickupActor::SyncRuntimeDispositionValues()
{
    const bool bHeld =
        PhysicalDisposition.Disposition == EVistaPickupDisposition::Held &&
        IsValid(PhysicalDisposition.Carrier.Get());
    RuntimeStateValues.Add(TEXT("held"), bHeld ? TEXT("true") : TEXT("false"));
    RuntimeStateValues.Add(
        TEXT("held_by"),
        bHeld ? CarrierSemanticId(PhysicalDisposition.Carrier.Get()) : FString());
    if (PhysicalDisposition.Disposition == EVistaPickupDisposition::Placed)
    {
        RuntimeStateValues.Add(
            TEXT("placed_at"), PhysicalDisposition.PlacementAnchorSemanticId);
    }
    else
    {
        RuntimeStateValues.Remove(TEXT("placed_at"));
    }
    const FString ContainedIn = GetContainedInSemanticId();
    if (ContainedIn.IsEmpty())
    {
        RuntimeStateValues.Remove(ContainedInKey);
    }
    else
    {
        RuntimeStateValues.Add(ContainedInKey, ContainedIn);
    }
}

bool AVistaPickupActor::ApplyPhysicalDisposition()
{
    if (!IsValid(Mesh) || !IsValid(GetRootComponent()) ||
        PhysicalDisposition.WorldTransform.ContainsNaN() ||
        PhysicalDisposition.AttachmentRelativeTransform.ContainsNaN() ||
        PhysicalDisposition.LinearVelocity.ContainsNaN() ||
        PhysicalDisposition.AngularVelocityDegrees.ContainsNaN())
    {
        return false;
    }

    if (PhysicalDisposition.Disposition == EVistaPickupDisposition::Held)
    {
        AActor* Carrier = PhysicalDisposition.Carrier.Get();
        FName CarryCode;
        USceneComponent* Anchor =
            UVistaActionExecutorComponent::PrepareCarryAnchor(Carrier, CarryCode);
        if (!IsValid(Carrier) || !IsValid(Anchor) ||
            !PhysicalDisposition.PlacementAnchorSemanticId.IsEmpty() ||
            IsValid(PhysicalDisposition.StorageContainer.Get()) ||
            PhysicalDisposition.bSimulatePhysics)
        {
            Mesh->SetSimulatePhysics(false);
            Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            return false;
        }
        Mesh->SetSimulatePhysics(false);
        Mesh->SetPhysicsLinearVelocity(PhysicalDisposition.LinearVelocity);
        Mesh->SetPhysicsAngularVelocityInDegrees(
            PhysicalDisposition.AngularVelocityDegrees);
        Mesh->SetCollisionProfileName(PhysicalDisposition.CollisionProfileName);
        Mesh->SetCollisionEnabled(
            static_cast<ECollisionEnabled::Type>(
                PhysicalDisposition.CollisionEnabled));
        if ((GetRootComponent()->GetAttachParent() != Anchor ||
             GetRootComponent()->GetAttachSocketName() !=
                 PhysicalDisposition.AttachmentSocketName) &&
            !AttachToComponent(
                Anchor,
                FAttachmentTransformRules::KeepWorldTransform,
                PhysicalDisposition.AttachmentSocketName))
        {
            return false;
        }
        GetRootComponent()->SetRelativeTransform(
            PhysicalDisposition.AttachmentRelativeTransform,
            false,
            nullptr,
            ETeleportType::TeleportPhysics);
        SyncRuntimeDispositionValues();
        return GetRootComponent()->GetAttachParent() == Anchor &&
            GetRootComponent()->GetAttachSocketName() ==
                PhysicalDisposition.AttachmentSocketName &&
            TransformBitsEqual(
                GetRootComponent()->GetRelativeTransform(),
                PhysicalDisposition.AttachmentRelativeTransform) &&
            !Mesh->IsSimulatingPhysics() &&
            static_cast<uint8>(Mesh->GetCollisionEnabled()) ==
                PhysicalDisposition.CollisionEnabled &&
            Mesh->GetCollisionProfileName() ==
                PhysicalDisposition.CollisionProfileName &&
            VectorBitsEqual(
                Mesh->GetPhysicsLinearVelocity(),
                PhysicalDisposition.LinearVelocity) &&
            VectorBitsEqual(
                Mesh->GetPhysicsAngularVelocityInDegrees(),
                PhysicalDisposition.AngularVelocityDegrees);
    }

    if (PhysicalDisposition.Disposition == EVistaPickupDisposition::Contained)
    {
        AVistaContainerActor* Container =
            PhysicalDisposition.StorageContainer.Get();
        USceneComponent* Anchor = IsValid(Container)
            ? Container->ContentsAnchor.Get() : nullptr;
        if (!IsValid(Container) || !IsValid(Anchor) ||
            Container->SemanticId.IsEmpty() ||
            IsValid(PhysicalDisposition.Carrier.Get()) ||
            !PhysicalDisposition.PlacementAnchorSemanticId.IsEmpty() ||
            PhysicalDisposition.bSimulatePhysics)
        {
            Mesh->SetSimulatePhysics(false);
            Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            return false;
        }
        Mesh->SetSimulatePhysics(false);
        Mesh->SetPhysicsLinearVelocity(PhysicalDisposition.LinearVelocity);
        Mesh->SetPhysicsAngularVelocityInDegrees(
            PhysicalDisposition.AngularVelocityDegrees);
        Mesh->SetCollisionProfileName(PhysicalDisposition.CollisionProfileName);
        Mesh->SetCollisionEnabled(
            static_cast<ECollisionEnabled::Type>(
                PhysicalDisposition.CollisionEnabled));
        if ((GetRootComponent()->GetAttachParent() != Anchor ||
             GetRootComponent()->GetAttachSocketName() !=
                 PhysicalDisposition.AttachmentSocketName) &&
            !AttachToComponent(
                Anchor,
                FAttachmentTransformRules::KeepWorldTransform,
                PhysicalDisposition.AttachmentSocketName))
        {
            return false;
        }
        GetRootComponent()->SetRelativeTransform(
            PhysicalDisposition.AttachmentRelativeTransform,
            false,
            nullptr,
            ETeleportType::TeleportPhysics);
        SyncRuntimeDispositionValues();
        return GetRootComponent()->GetAttachParent() == Anchor &&
            GetRootComponent()->GetAttachSocketName() ==
                PhysicalDisposition.AttachmentSocketName &&
            TransformBitsEqual(
                GetRootComponent()->GetRelativeTransform(),
                PhysicalDisposition.AttachmentRelativeTransform) &&
            !Mesh->IsSimulatingPhysics() &&
            static_cast<uint8>(Mesh->GetCollisionEnabled()) ==
                PhysicalDisposition.CollisionEnabled &&
            Mesh->GetCollisionProfileName() ==
                PhysicalDisposition.CollisionProfileName &&
            VectorBitsEqual(
                Mesh->GetPhysicsLinearVelocity(), FVector::ZeroVector) &&
            VectorBitsEqual(
                Mesh->GetPhysicsAngularVelocityInDegrees(),
                FVector::ZeroVector);
    }

    DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
    Mesh->SetSimulatePhysics(false);
    Mesh->SetCollisionProfileName(PhysicalDisposition.CollisionProfileName);
    Mesh->SetCollisionEnabled(
        static_cast<ECollisionEnabled::Type>(PhysicalDisposition.CollisionEnabled));
    const bool bTransformApplied = SetActorTransform(
        PhysicalDisposition.WorldTransform,
        false,
        nullptr,
        ETeleportType::TeleportPhysics);
    Mesh->SetSimulatePhysics(PhysicalDisposition.bSimulatePhysics);
    Mesh->SetPhysicsLinearVelocity(PhysicalDisposition.LinearVelocity);
    Mesh->SetPhysicsAngularVelocityInDegrees(
        PhysicalDisposition.AngularVelocityDegrees);
    SyncRuntimeDispositionValues();
    FString NormalizedPlacementIdentity;
    const bool bPlacementIdentityValid =
        PhysicalDisposition.Disposition != EVistaPickupDisposition::Placed ||
        (HasAuthority()
            ? NormalizeStoredPlacementAnchor(
                  GetWorld(),
                  PhysicalDisposition.PlacementAnchorSemanticId,
                  NormalizedPlacementIdentity) &&
                  NormalizedPlacementIdentity ==
                      PhysicalDisposition.PlacementAnchorSemanticId
            : IsStablePlacementAnchorSemanticId(
                  PhysicalDisposition.PlacementAnchorSemanticId));
    return bTransformApplied && bPlacementIdentityValid &&
        !IsValid(PhysicalDisposition.Carrier.Get()) &&
        (PhysicalDisposition.Disposition == EVistaPickupDisposition::Placed
            ? !PhysicalDisposition.bSimulatePhysics &&
                !PhysicalDisposition.PlacementAnchorSemanticId.IsEmpty()
            : PhysicalDisposition.Disposition == EVistaPickupDisposition::Free &&
                PhysicalDisposition.PlacementAnchorSemanticId.IsEmpty()) &&
        !IsValid(PhysicalDisposition.StorageContainer.Get()) &&
        GetRootComponent()->GetAttachParent() == nullptr &&
        TransformBitsEqual(
            GetActorTransform(), PhysicalDisposition.WorldTransform) &&
        Mesh->IsSimulatingPhysics() ==
            PhysicalDisposition.bSimulatePhysics &&
        static_cast<uint8>(Mesh->GetCollisionEnabled()) ==
            PhysicalDisposition.CollisionEnabled &&
        Mesh->GetCollisionProfileName() ==
            PhysicalDisposition.CollisionProfileName &&
        VectorBitsEqual(
            Mesh->GetPhysicsLinearVelocity(),
            PhysicalDisposition.LinearVelocity) &&
        VectorBitsEqual(
            Mesh->GetPhysicsAngularVelocityInDegrees(),
            PhysicalDisposition.AngularVelocityDegrees);
}

bool AVistaPickupActor::CapturePhysicalState(
    FVistaPickupPhysicalStateSnapshot& OutSnapshot,
    USceneComponent*& OutAttachmentParent,
    AActor*& OutCarrier,
    EVistaPickupDisposition& OutDisposition) const
{
    OutSnapshot = FVistaPickupPhysicalStateSnapshot();
    OutAttachmentParent = nullptr;
    OutCarrier = nullptr;
    OutDisposition = EVistaPickupDisposition::Free;
    if (!IsValid(Mesh) || !IsValid(GetRootComponent()))
    {
        return false;
    }

    const USceneComponent* Root = GetRootComponent();
    OutAttachmentParent = Root->GetAttachParent();
    OutCarrier = GetCarrier();
    OutDisposition = PhysicalDisposition.Disposition;
    OutSnapshot.WorldTransform = GetActorTransform();
    OutSnapshot.bSimulatePhysics = Mesh->IsSimulatingPhysics();
    OutSnapshot.CollisionEnabled =
        static_cast<uint8>(Mesh->GetCollisionEnabled());
    OutSnapshot.CollisionProfileName = Mesh->GetCollisionProfileName();
    OutSnapshot.LinearVelocity = Mesh->GetPhysicsLinearVelocity();
    OutSnapshot.AngularVelocityDegrees =
        Mesh->GetPhysicsAngularVelocityInDegrees();
    OutSnapshot.bHasAttachmentParent = IsValid(OutAttachmentParent);
    if (IsValid(OutAttachmentParent))
    {
        OutSnapshot.AttachmentParentOwnerSemanticId =
            CarrierSemanticId(OutAttachmentParent->GetOwner());
        OutSnapshot.AttachmentParentComponentName =
            OutAttachmentParent->GetFName();
        OutSnapshot.AttachmentSocketName = Root->GetAttachSocketName();
        OutSnapshot.AttachmentRelativeTransform = Root->GetRelativeTransform();
    }
    OutSnapshot.bHeld = IsValid(OutCarrier);
    OutSnapshot.CarrierSemanticId = CarrierSemanticId(OutCarrier);
    if (IsValid(OutCarrier))
    {
        AActor* InventoryItem = CarrierInventoryItem(OutCarrier);
        OutSnapshot.InventoryCarrierSemanticId =
            CarrierSemanticId(OutCarrier);
        OutSnapshot.bInventorySlotOccupied = IsValid(InventoryItem);
        OutSnapshot.InventoryItemSemanticId = CarrierSemanticId(InventoryItem);
    }
    if (PhysicalDisposition.Disposition == EVistaPickupDisposition::Placed)
    {
        OutSnapshot.PlacedAtSemanticId =
            PhysicalDisposition.PlacementAnchorSemanticId;
    }
    else if (PhysicalDisposition.Disposition == EVistaPickupDisposition::Contained)
    {
        OutSnapshot.ContainedInSemanticId = GetContainedInSemanticId();
    }

    const bool bDispositionCoherent =
        (OutDisposition == EVistaPickupDisposition::Held &&
         OutSnapshot.bHeld && OutSnapshot.bHasAttachmentParent &&
         !OutSnapshot.bSimulatePhysics &&
         OutSnapshot.PlacedAtSemanticId.IsEmpty() &&
         OutSnapshot.ContainedInSemanticId.IsEmpty()) ||
        (OutDisposition == EVistaPickupDisposition::Placed &&
         !OutSnapshot.bHeld && !OutSnapshot.bHasAttachmentParent &&
         !OutSnapshot.bSimulatePhysics &&
         !OutSnapshot.PlacedAtSemanticId.IsEmpty() &&
         OutSnapshot.ContainedInSemanticId.IsEmpty()) ||
        (OutDisposition == EVistaPickupDisposition::Contained &&
         !OutSnapshot.bHeld && OutSnapshot.bHasAttachmentParent &&
         !OutSnapshot.bSimulatePhysics &&
         OutSnapshot.PlacedAtSemanticId.IsEmpty() &&
         !OutSnapshot.ContainedInSemanticId.IsEmpty()) ||
        (OutDisposition == EVistaPickupDisposition::Free &&
         !OutSnapshot.bHeld && !OutSnapshot.bHasAttachmentParent &&
         OutSnapshot.PlacedAtSemanticId.IsEmpty() &&
         OutSnapshot.ContainedInSemanticId.IsEmpty());
    return bDispositionCoherent &&
        !OutSnapshot.WorldTransform.ContainsNaN() &&
        !OutSnapshot.AttachmentRelativeTransform.ContainsNaN() &&
        !OutSnapshot.LinearVelocity.ContainsNaN() &&
        !OutSnapshot.AngularVelocityDegrees.ContainsNaN() &&
        (!OutSnapshot.bHeld ||
         (!OutSnapshot.CarrierSemanticId.IsEmpty() &&
          OutSnapshot.bInventorySlotOccupied &&
          OutSnapshot.InventoryItemSemanticId == SemanticId));
}

bool AVistaPickupActor::CapturePhysicalStateTrusted(
    FVistaPickupPhysicalStateSnapshot& OutSnapshot,
    USceneComponent*& OutAttachmentParent,
    AActor*& OutCarrier,
    EVistaPickupDisposition& OutDisposition,
    const FVistaTrustedPhysicalRestoreToken& Token) const
{
    static_cast<void>(Token);
    return CapturePhysicalState(
        OutSnapshot, OutAttachmentParent, OutCarrier, OutDisposition);
}

bool AVistaPickupActor::MatchesPhysicalStateTrusted(
    const FVistaPickupPhysicalStateSnapshot& ExpectedSnapshot,
    const USceneComponent* ExpectedAttachmentParent,
    const AActor* ExpectedCarrier,
    EVistaPickupDisposition ExpectedDisposition,
    const FVistaTrustedPhysicalRestoreToken& Token) const
{
    FVistaPickupPhysicalStateSnapshot ActualSnapshot;
    USceneComponent* ActualAttachmentParent = nullptr;
    AActor* ActualCarrier = nullptr;
    EVistaPickupDisposition ActualDisposition = EVistaPickupDisposition::Free;
    return CapturePhysicalStateTrusted(
               ActualSnapshot,
               ActualAttachmentParent,
               ActualCarrier,
               ActualDisposition,
               Token) &&
        ActualAttachmentParent == ExpectedAttachmentParent &&
        ActualCarrier == ExpectedCarrier &&
        ActualDisposition == ExpectedDisposition &&
        (!IsValid(ExpectedCarrier) ||
         CarrierInventoryHolds(
             const_cast<AActor*>(ExpectedCarrier), this)) &&
        PhysicalSnapshotsBitExact(ActualSnapshot, ExpectedSnapshot);
}

bool AVistaPickupActor::ClearForTrustedBaselineRestore(
    const FVistaTrustedPhysicalRestoreToken& Token)
{
    static_cast<void>(Token);
    if (!HasAuthority() || !IsValid(Mesh))
    {
        return false;
    }
    if (AActor* PreviousCarrier = GetCarrier(); IsValid(PreviousCarrier))
    {
        if (!CarrierInventoryHolds(PreviousCarrier, this))
        {
            return false;
        }
        IVistaItemCarrier::Execute_VistaReleaseItem(PreviousCarrier, this);
        if (!CarrierInventoryIsEmpty(PreviousCarrier))
        {
            return false;
        }
    }
    PhysicalDisposition.Disposition = EVistaPickupDisposition::Free;
    PhysicalDisposition.Carrier = nullptr;
    PhysicalDisposition.PlacementAnchorSemanticId.Reset();
    PhysicalDisposition.StorageContainer = nullptr;
    PhysicalDisposition.WorldTransform = GetActorTransform();
    PhysicalDisposition.AttachmentRelativeTransform = FTransform::Identity;
    PhysicalDisposition.AttachmentSocketName = NAME_None;
    PhysicalDisposition.bSimulatePhysics = bPortable;
    PhysicalDisposition.CollisionProfileName =
        UCollisionProfile::PhysicsActor_ProfileName;
    PhysicalDisposition.CollisionEnabled =
        static_cast<uint8>(ECollisionEnabled::QueryAndPhysics);
    PhysicalDisposition.LinearVelocity = FVector::ZeroVector;
    PhysicalDisposition.AngularVelocityDegrees = FVector::ZeroVector;
    return ApplyPhysicalDisposition();
}

FVistaInteractionResult AVistaPickupActor::RestorePhysicalStateTrusted(
    const FVistaEntityRuntimeState& State,
    const FVistaPickupPhysicalStateSnapshot* PhysicalSnapshot,
    USceneComponent* AttachmentParent,
    AActor* Carrier,
    const FVistaTrustedPhysicalRestoreToken& Token)
{
    static_cast<void>(Token);
    if (!HasAuthority() || !IsValid(Mesh) ||
        (!State.SemanticId.IsEmpty() && State.SemanticId != SemanticId) ||
        State.Transform.ContainsNaN())
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::Rejected,
            TEXT("TRUSTED_RESTORE_INPUT_INVALID"),
            SemanticId);
    }

    FVistaLiquidStateSnapshot DesiredLiquidState;
    FName LiquidCode;
    if (!ReadLiquidState(
            State, LiquidState, DesiredLiquidState, LiquidCode))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            LiquidCode,
            SemanticId);
    }

    const FString* HeldValue = State.Values.Find(TEXT("held"));
    const bool bRestoreHeld = HeldValue &&
        HeldValue->Equals(TEXT("true"), ESearchCase::IgnoreCase);
    const FString* HeldByValue = State.Values.Find(TEXT("held_by"));
    const FString* PlacedAtValue = State.Values.Find(TEXT("placed_at"));
    const bool bRestorePlaced = PlacedAtValue &&
        !IsNullPlacementStateValue(*PlacedAtValue);
    const FString* ContainedInValue = State.Values.Find(ContainedInKey);
    const bool bRestoreContained = ContainedInValue != nullptr &&
        !ContainedInValue->IsEmpty();
    if ((bRestoreHeld ? 1 : 0) + (bRestorePlaced ? 1 : 0) +
            (bRestoreContained ? 1 : 0) >
        1)
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("TRUSTED_RESTORE_DISPOSITION_CONFLICT"),
            SemanticId);
    }

    FVistaPickupReplicatedDisposition Desired;
    Desired.WorldTransform = State.Transform;
    Desired.CollisionProfileName = (bRestoreHeld || bRestoreContained)
        ? UCollisionProfile::NoCollision_ProfileName
        : UCollisionProfile::PhysicsActor_ProfileName;
    Desired.CollisionEnabled = (bRestoreHeld || bRestoreContained)
        ? static_cast<uint8>(ECollisionEnabled::NoCollision)
        : static_cast<uint8>(ECollisionEnabled::QueryAndPhysics);
    Desired.bSimulatePhysics =
        !bRestoreHeld && !bRestorePlaced && !bRestoreContained &&
        State.bPortable;
    if (PhysicalSnapshot != nullptr)
    {
        if (PhysicalSnapshot->WorldTransform.ContainsNaN() ||
            PhysicalSnapshot->AttachmentRelativeTransform.ContainsNaN() ||
            PhysicalSnapshot->LinearVelocity.ContainsNaN() ||
            PhysicalSnapshot->AngularVelocityDegrees.ContainsNaN() ||
            PhysicalSnapshot->bHeld != bRestoreHeld ||
            (PhysicalSnapshot->bHasAttachmentParent !=
             (bRestoreHeld || bRestoreContained)) ||
            (PhysicalSnapshot->bSimulatePhysics &&
             PhysicalSnapshot->bHasAttachmentParent) ||
            PhysicalSnapshot->PlacedAtSemanticId !=
                (bRestorePlaced ? *PlacedAtValue : FString()) ||
            PhysicalSnapshot->ContainedInSemanticId !=
                (bRestoreContained ? *ContainedInValue : FString()))
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::InvalidState,
                TEXT("TRUSTED_RESTORE_SNAPSHOT_INVALID"),
                SemanticId);
        }
        Desired.WorldTransform = PhysicalSnapshot->WorldTransform;
        Desired.AttachmentRelativeTransform =
            PhysicalSnapshot->AttachmentRelativeTransform;
        Desired.AttachmentSocketName = PhysicalSnapshot->AttachmentSocketName;
        Desired.bSimulatePhysics = PhysicalSnapshot->bSimulatePhysics;
        Desired.CollisionEnabled = PhysicalSnapshot->CollisionEnabled;
        Desired.CollisionProfileName = PhysicalSnapshot->CollisionProfileName;
        Desired.LinearVelocity = PhysicalSnapshot->LinearVelocity;
        Desired.AngularVelocityDegrees =
            PhysicalSnapshot->AngularVelocityDegrees;
    }

    if (bRestoreHeld)
    {
        if (!IsValid(Carrier) && HeldByValue != nullptr)
        {
            Carrier = ResolveCarrier(GetWorld(), *HeldByValue);
        }
        if (!IsValid(Carrier))
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("BASELINE_CARRIER_NOT_FOUND"),
                SemanticId);
        }
        FName CarryCode;
        USceneComponent* ExactCarryAnchor =
            UVistaActionExecutorComponent::PrepareCarryAnchor(Carrier, CarryCode);
        if (!IsValid(ExactCarryAnchor) ||
            (AttachmentParent != nullptr && AttachmentParent != ExactCarryAnchor) ||
            HeldByValue == nullptr ||
            *HeldByValue != CarrierSemanticId(Carrier) ||
            (PhysicalSnapshot != nullptr &&
             (PhysicalSnapshot->AttachmentParentOwnerSemanticId !=
                  CarrierSemanticId(Carrier) ||
              PhysicalSnapshot->AttachmentParentComponentName !=
                  ExactCarryAnchor->GetFName())))
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("TRUSTED_RESTORE_CARRIER_INVALID"),
                SemanticId);
        }
        Desired.Disposition = EVistaPickupDisposition::Held;
        Desired.Carrier = Carrier;
    }
    else if (bRestorePlaced)
    {
        FString NormalizedPlacement;
        if (!NormalizeStoredPlacementAnchor(
                GetWorld(), *PlacedAtValue, NormalizedPlacement) ||
            NormalizedPlacement != *PlacedAtValue || AttachmentParent != nullptr ||
            IsValid(Carrier))
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("TRUSTED_RESTORE_PLACEMENT_INVALID"),
                SemanticId);
        }
        Desired.Disposition = EVistaPickupDisposition::Placed;
        Desired.PlacementAnchorSemanticId = NormalizedPlacement;
        Desired.bSimulatePhysics = false;
    }
    else if (bRestoreContained)
    {
        AVistaContainerActor* Container = ResolveStorageContainer(
            GetWorld(), *ContainedInValue);
        USceneComponent* ExactContentsAnchor = IsValid(Container)
            ? Container->ContentsAnchor.Get() : nullptr;
        if (!IsValid(Container) || !IsValid(ExactContentsAnchor) ||
            (AttachmentParent != nullptr &&
             AttachmentParent != ExactContentsAnchor) ||
            IsValid(Carrier) ||
            (PhysicalSnapshot != nullptr &&
             (PhysicalSnapshot->AttachmentParentOwnerSemanticId !=
                  Container->SemanticId ||
              PhysicalSnapshot->AttachmentParentComponentName !=
                  ExactContentsAnchor->GetFName())))
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::NotFound,
                TEXT("TRUSTED_RESTORE_CONTAINER_INVALID"),
                SemanticId);
        }
        Desired.Disposition = EVistaPickupDisposition::Contained;
        Desired.StorageContainer = Container;
        Desired.bSimulatePhysics = false;
    }
    else
    {
        if (AttachmentParent != nullptr || IsValid(Carrier))
        {
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::InvalidState,
                TEXT("TRUSTED_RESTORE_FREE_ATTACHMENT_INVALID"),
                SemanticId);
        }
        Desired.Disposition = EVistaPickupDisposition::Free;
    }

    if (!ClearForTrustedBaselineRestore(Token))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("TRUSTED_RESTORE_CLEAR_FAILED"),
            SemanticId);
    }
    bPortable = State.bPortable;
    const FVistaInteractionResult BaseResult =
        Super::VistaApplyRuntimeState_Implementation(State);
    if (!BaseResult.IsSuccess())
    {
        return BaseResult;
    }
    bool bCarrierClaimed = false;
    if (Desired.Disposition == EVistaPickupDisposition::Held)
    {
        bCarrierClaimed =
            IVistaItemCarrier::Execute_VistaTryClaimItem(Carrier, this);
        if (!bCarrierClaimed || !CarrierInventoryHolds(Carrier, this))
        {
            if (bCarrierClaimed)
            {
                IVistaItemCarrier::Execute_VistaReleaseItem(Carrier, this);
            }
            return FVistaInteractionResult::Failure(
                EVistaInteractionStatus::Busy,
                CarrierInventoryIsEmpty(Carrier)
                    ? FName(TEXT("TRUSTED_RESTORE_CARRIER_SLOT_UNAVAILABLE"))
                    : FName(TEXT("TRUSTED_RESTORE_CARRIER_CLAIM_DIVERGED")),
                SemanticId);
        }
    }
    PhysicalDisposition = Desired;
    if (!ApplyPhysicalDisposition())
    {
        if (bCarrierClaimed)
        {
            IVistaItemCarrier::Execute_VistaReleaseItem(Carrier, this);
        }
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            !bCarrierClaimed || CarrierInventoryIsEmpty(Carrier)
                ? FName(TEXT("TRUSTED_RESTORE_APPLY_FAILED"))
                : FName(TEXT("TRUSTED_RESTORE_COMPENSATION_FAILED")),
            SemanticId);
    }
    if (Desired.Disposition == EVistaPickupDisposition::Held &&
        !CarrierInventoryHolds(Carrier, this))
    {
        return FVistaInteractionResult::Failure(
            EVistaInteractionStatus::InvalidState,
            TEXT("TRUSTED_RESTORE_CARRIER_VERIFY_FAILED"),
            SemanticId);
    }
    SetLiquidState(DesiredLiquidState);
    ForceNetUpdate();
    return FVistaInteractionResult::Success(
        SemanticId,
        VistaGetRuntimeState_Implementation(),
        TEXT("TRUSTED_PHYSICAL_STATE_RESTORED"));
}

void AVistaPickupActor::NormalizePlacementState()
{
    if (!HasAuthority())
    {
        return;
    }
    const FString* PlacementValue = RuntimeStateValues.Find(TEXT("placed_at"));
    FString NormalizedPlacement;
    const bool bPlaced = PlacementValue &&
        !IsNullPlacementStateValue(*PlacementValue) &&
        NormalizeStoredPlacementAnchor(
            GetWorld(), *PlacementValue, NormalizedPlacement);
    PhysicalDisposition.Disposition = bPlaced
        ? EVistaPickupDisposition::Placed : EVistaPickupDisposition::Free;
    PhysicalDisposition.Carrier = nullptr;
    PhysicalDisposition.PlacementAnchorSemanticId = bPlaced
        ? NormalizedPlacement : FString();
    PhysicalDisposition.StorageContainer = nullptr;
    PhysicalDisposition.WorldTransform = GetActorTransform();
    PhysicalDisposition.AttachmentRelativeTransform = FTransform::Identity;
    PhysicalDisposition.AttachmentSocketName = NAME_None;
    PhysicalDisposition.bSimulatePhysics = !bPlaced && bPortable;
    PhysicalDisposition.CollisionProfileName =
        UCollisionProfile::PhysicsActor_ProfileName;
    PhysicalDisposition.CollisionEnabled =
        static_cast<uint8>(ECollisionEnabled::QueryAndPhysics);
    PhysicalDisposition.LinearVelocity = bPlaced
        ? FVector::ZeroVector : Mesh->GetPhysicsLinearVelocity();
    PhysicalDisposition.AngularVelocityDegrees = bPlaced
        ? FVector::ZeroVector : Mesh->GetPhysicsAngularVelocityInDegrees();
    if (!ApplyPhysicalDisposition())
    {
        UE_LOG(
            LogTemp,
            Error,
            TEXT("VISTA_PICKUP_INITIAL_DISPOSITION_REJECTED semantic_id=%s"),
            *SemanticId);
    }
    ForceNetUpdate();
}

void AVistaPickupActor::RefreshPresentationState()
{
    if (!IsValid(Mesh) || !IsValid(PresentationMesh))
    {
        return;
    }

    const bool bHasPresentation = HasPresentationMesh();
    PresentationMesh->SetMobility(EComponentMobility::Movable);
    PresentationMesh->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
    PresentationMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    PresentationMesh->SetSimulatePhysics(false);
    PresentationMesh->SetGenerateOverlapEvents(false);
    PresentationMesh->SetCanEverAffectNavigation(false);
    PresentationMesh->SetVisibility(bHasPresentation, false);

    // Do not hide the actor: the render-only child must follow every actor-level
    // attach, detach, placement, and physics transform owned by PickupMesh.
    if (bHasPresentation)
    {
        Mesh->SetVisibility(false, false);
    }
}
