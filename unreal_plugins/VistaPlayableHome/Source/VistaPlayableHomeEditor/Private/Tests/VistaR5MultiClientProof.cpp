#include "CQTest.h"
#include "Components/PIENetworkComponent.h"
#include "Tests/VistaR5MultiClientProofActors.h"

#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/NetDriver.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/GameModeBase.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMemory.h"
#include "Misc/CommandLine.h"
#include "Misc/EngineVersion.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/Parse.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/UObjectGlobals.h"
#include "VistaActionExecutorComponent.h"
#include "VistaEventSubsystem.h"
#include "VistaInteractable.h"
#include "VistaItemCarrier.h"
#include "VistaPickupActor.h"

#if ENABLE_PIE_NETWORK_TEST && WITH_DEV_AUTOMATION_TESTS

namespace
{
const FString CarrierASemanticId(TEXT("home.r5/entity.proof_carrier_a"));
const FString CarrierBSemanticId(TEXT("home.r5/entity.proof_carrier_b"));
const FString PickupSemanticId(TEXT("home.r5/entity.proof_cup"));
const FString PlacementOwnerSemanticId(TEXT("home.r5/entity.proof_table"));
const FString PlacementAnchorSemanticId(
    TEXT("home.r5/entity.proof_table/anchor.cup"));
const FName ProofRevision(TEXT("vista-r5-multiclient-proof-r1"));
const FName ProofEventId(TEXT("r5-proof-event"));
const FVector DropVelocity(37.0, -11.0, 23.0);
const FString PrivateReceiptPath(
    TEXT("/vista-private/r5-multiclient-proof-receipt.json"));

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

bool SnapshotBitsEqual(
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
        Left.PlacedAtSemanticId == Right.PlacedAtSemanticId;
}

template <typename T>
FString ScalarBits(const T& Value)
{
    static_assert(sizeof(T) == sizeof(uint32) || sizeof(T) == sizeof(uint64));
    if constexpr (sizeof(T) == sizeof(uint32))
    {
        uint32 Bits = 0;
        FPlatformMemory::Memcpy(&Bits, &Value, sizeof(Bits));
        return FString::Printf(TEXT("%08x"), Bits);
    }
    uint64 Bits = 0;
    FPlatformMemory::Memcpy(&Bits, &Value, sizeof(Bits));
    return FString::Printf(
        TEXT("%016llx"), static_cast<unsigned long long>(Bits));
}

TArray<TSharedPtr<FJsonValue>> VectorBitArray(const FVector& Vector)
{
    return {
        MakeShared<FJsonValueString>(ScalarBits(Vector.X)),
        MakeShared<FJsonValueString>(ScalarBits(Vector.Y)),
        MakeShared<FJsonValueString>(ScalarBits(Vector.Z))};
}

TArray<TSharedPtr<FJsonValue>> TransformBitArray(const FTransform& Transform)
{
    const FVector Translation = Transform.GetTranslation();
    const FQuat Rotation = Transform.GetRotation();
    const FVector Scale = Transform.GetScale3D();
    return {
        MakeShared<FJsonValueString>(ScalarBits(Translation.X)),
        MakeShared<FJsonValueString>(ScalarBits(Translation.Y)),
        MakeShared<FJsonValueString>(ScalarBits(Translation.Z)),
        MakeShared<FJsonValueString>(ScalarBits(Rotation.X)),
        MakeShared<FJsonValueString>(ScalarBits(Rotation.Y)),
        MakeShared<FJsonValueString>(ScalarBits(Rotation.Z)),
        MakeShared<FJsonValueString>(ScalarBits(Rotation.W)),
        MakeShared<FJsonValueString>(ScalarBits(Scale.X)),
        MakeShared<FJsonValueString>(ScalarBits(Scale.Y)),
        MakeShared<FJsonValueString>(ScalarBits(Scale.Z))};
}

FString DispositionName(EVistaPickupDisposition Disposition)
{
    switch (Disposition)
    {
    case EVistaPickupDisposition::Free: return TEXT("free");
    case EVistaPickupDisposition::Held: return TEXT("held");
    case EVistaPickupDisposition::Placed: return TEXT("placed");
    default: return TEXT("invalid");
    }
}

FString NetModeName(ENetMode NetMode)
{
    switch (NetMode)
    {
    case NM_Standalone: return TEXT("standalone");
    case NM_DedicatedServer: return TEXT("dedicated_server");
    case NM_ListenServer: return TEXT("listen_server");
    case NM_Client: return TEXT("client");
    default: return TEXT("invalid");
    }
}

FString TransactionStatusName(EVistaActionTransactionStatus Status)
{
    switch (Status)
    {
    case EVistaActionTransactionStatus::Idle: return TEXT("idle");
    case EVistaActionTransactionStatus::Running: return TEXT("running");
    case EVistaActionTransactionStatus::Succeeded: return TEXT("succeeded");
    case EVistaActionTransactionStatus::Failed: return TEXT("failed");
    case EVistaActionTransactionStatus::TimedOut: return TEXT("timed_out");
    case EVistaActionTransactionStatus::Canceled: return TEXT("canceled");
    default: return TEXT("invalid");
    }
}

FString EventStatusName(EVistaEventStatus Status)
{
    switch (Status)
    {
    case EVistaEventStatus::Inactive: return TEXT("inactive");
    case EVistaEventStatus::Applying: return TEXT("applying");
    case EVistaEventStatus::Active: return TEXT("active");
    case EVistaEventStatus::Succeeded: return TEXT("succeeded");
    case EVistaEventStatus::Failed: return TEXT("failed");
    case EVistaEventStatus::TimedOut: return TEXT("timed_out");
    case EVistaEventStatus::Resetting: return TEXT("resetting");
    default: return TEXT("invalid");
    }
}

TSharedPtr<FJsonObject> EventStateJson(const UVistaEventSubsystem* Events)
{
    TSharedPtr<FJsonObject> Object = MakeShared<FJsonObject>();
    Object->SetStringField(
        TEXT("active_event_id"), Events->GetActiveEventId().ToString());
    Object->SetStringField(
        TEXT("event_status"), EventStatusName(Events->GetEventStatus()));
    Object->SetNumberField(
        TEXT("session_generation"), Events->GetSessionGeneration());
    Object->SetStringField(TEXT("public_goal"), Events->GetPublicGoal());
    Object->SetStringField(
        TEXT("terminal_condition_id"),
        Events->GetTerminalConditionId().ToString());
    return Object;
}

FString SnapshotDispositionName(
    const FVistaPickupPhysicalStateSnapshot& Snapshot)
{
    if (Snapshot.bHeld)
    {
        return TEXT("held");
    }
    return Snapshot.PlacedAtSemanticId.IsEmpty()
        ? TEXT("free") : TEXT("placed");
}

FString SemanticIdFor(const AActor* Actor)
{
    if (!IsValid(Actor) ||
        !Actor->GetClass()->ImplementsInterface(UVistaInteractable::StaticClass()))
    {
        return FString();
    }
    return IVistaInteractable::Execute_VistaGetSemanticId(
        const_cast<AActor*>(Actor));
}

bool IsSafeAttemptId(const FString& Value)
{
    if (Value.Len() < 16 || Value.Len() > 96)
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        const bool bAllowed =
            (Character >= TEXT('a') && Character <= TEXT('z')) ||
            (Character >= TEXT('0') && Character <= TEXT('9')) ||
            Character == TEXT('-');
        if (!bAllowed)
        {
            return false;
        }
    }
    return true;
}

bool IsLowerHexDigest(const FString& Value, const int32 ExpectedLength)
{
    if (Value.Len() != ExpectedLength)
    {
        return false;
    }
    for (const TCHAR Character : Value)
    {
        if (!((Character >= TEXT('0') && Character <= TEXT('9')) ||
              (Character >= TEXT('a') && Character <= TEXT('f'))))
        {
            return false;
        }
    }
    return true;
}
} // namespace

NETWORK_TEST_CLASS(VistaR5MultiClientProof, "VISTA.R5")
{
    struct FProofNetworkState final : public FBasePIENetworkComponentState
    {
        AVistaR5ProofCarrier* CarrierA = nullptr;
        AVistaR5ProofCarrier* CarrierB = nullptr;
        AVistaPickupActor* Pickup = nullptr;
        AVistaR5ProofPlacementAnchor* PlacementAnchor = nullptr;
    };

    struct FCheckpoint final
    {
        FString Name;
        TArray<TSharedPtr<FJsonValue>> Observations;
    };

    FPIENetworkComponent<FProofNetworkState> Network{
        TestRunner, TestCommandBuilder, bInitializing};

    UStaticMesh* OriginalPickupMesh = nullptr;
    FString OriginalPickupSemanticId;
    bool bOriginalPickupGravity = true;
    float OriginalPickupLinearDamping = 0.0f;
    float OriginalPickupAngularDamping = 0.0f;
    TArray<FCheckpoint> Checkpoints;
    FVistaActionTransactionRecord EventResetActiveRecord;
    FVistaActionTransactionRecord PickupRecord;
    FVistaActionTransactionRecord ReplayRecord;
    FVistaActionTransactionRecord CollisionRecord;
    FVistaActionTransactionRecord RollbackRecord;
    FVistaActionTransactionRecord PlaceRecord;
    FVistaActionTransactionRecord PickupAgainRecord;
    FVistaActionTransactionRecord DropRecord;
    FName EventResetCode = NAME_None;
    bool bEventResetAccepted = true;
    TSharedPtr<FJsonObject> EventResetBeforeState;
    TSharedPtr<FJsonObject> EventResetAfterRejectionState;
    bool bHasActiveActionAfterResetRejection = false;

    BEFORE_EACH()
    {
        EventResetBeforeState.Reset();
        EventResetAfterRejectionState.Reset();
        bHasActiveActionAfterResetRejection = false;
        AVistaPickupActor* PickupCdo = GetMutableDefault<AVistaPickupActor>();
        OriginalPickupMesh = IsValid(PickupCdo) && IsValid(PickupCdo->Mesh)
            ? PickupCdo->Mesh->GetStaticMesh() : nullptr;
        OriginalPickupSemanticId = IsValid(PickupCdo)
            ? PickupCdo->SemanticId : FString();
        bOriginalPickupGravity = IsValid(PickupCdo) && IsValid(PickupCdo->Mesh)
            ? PickupCdo->Mesh->IsGravityEnabled() : true;
        OriginalPickupLinearDamping =
            IsValid(PickupCdo) && IsValid(PickupCdo->Mesh)
                ? PickupCdo->Mesh->GetLinearDamping() : 0.0f;
        OriginalPickupAngularDamping =
            IsValid(PickupCdo) && IsValid(PickupCdo->Mesh)
                ? PickupCdo->Mesh->GetAngularDamping() : 0.0f;

        UStaticMesh* ProofMesh = LoadObject<UStaticMesh>(
            nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
        AddErrorIfFalse(
            IsValid(PickupCdo) && IsValid(PickupCdo->Mesh) &&
                IsValid(ProofMesh),
            TEXT("R5 proof requires the engine BasicShapes Cube body"));
        if (IsValid(PickupCdo) && IsValid(PickupCdo->Mesh) && IsValid(ProofMesh))
        {
            PickupCdo->SemanticId = PickupSemanticId;
            PickupCdo->Mesh->SetStaticMesh(ProofMesh);
            PickupCdo->Mesh->SetEnableGravity(false);
            PickupCdo->Mesh->SetLinearDamping(0.0f);
            PickupCdo->Mesh->SetAngularDamping(0.0f);
        }

        for (const TCHAR* Name : {
                 TEXT("initial_free"),
                 TEXT("held_after_pickup"),
                 TEXT("held_after_rollback"),
                 TEXT("placed"),
                 TEXT("held_again"),
                 TEXT("free_after_drop")})
        {
            FCheckpoint& Checkpoint = Checkpoints.AddDefaulted_GetRef();
            Checkpoint.Name = Name;
        }

        FNetworkComponentBuilder<FProofNetworkState>()
            .WithClients(2)
            .AsDedicatedServer()
            .WithGameMode(AGameModeBase::StaticClass())
            .Build(Network);
    }

    AFTER_EACH()
    {
        AVistaPickupActor* PickupCdo = GetMutableDefault<AVistaPickupActor>();
        if (IsValid(PickupCdo) && IsValid(PickupCdo->Mesh))
        {
            PickupCdo->SemanticId = OriginalPickupSemanticId;
            PickupCdo->Mesh->SetStaticMesh(OriginalPickupMesh);
            PickupCdo->Mesh->SetEnableGravity(bOriginalPickupGravity);
            PickupCdo->Mesh->SetLinearDamping(OriginalPickupLinearDamping);
            PickupCdo->Mesh->SetAngularDamping(OriginalPickupAngularDamping);
        }
    }

    bool Require(bool bCondition, const FString& Message)
    {
        return AddErrorIfFalse(bCondition, Message);
    }

    static FVistaPhysicalActionRequest MakeRequest(
        const FProofNetworkState& State,
        AVistaR5ProofCarrier* Requester,
        FName CommandId,
        EVistaAffordance Affordance,
        const FVector& ReleaseVelocity = FVector::ZeroVector)
    {
        FVistaPhysicalActionRequest Request;
        Request.CommandId = CommandId;
        Request.Requester = Requester;
        Request.Target = State.Pickup;
        Request.RequesterSemanticId = SemanticIdFor(Requester);
        Request.TargetSemanticId = SemanticIdFor(State.Pickup);
        Request.Affordance = Affordance;
        Request.ExpectedRevision = ProofRevision;
        Request.SessionGeneration = 0;
        Request.TimeoutSeconds = 10.0f;
        Request.ReleaseVelocity = ReleaseVelocity;
        if (Affordance == EVistaAffordance::Place)
        {
            Request.PlacementAnchor = State.PlacementAnchor->GetRootComponent();
            Request.PlacementAnchorSemanticId = PlacementAnchorSemanticId;
        }
        return Request;
    }

    static bool HasProofIdentities(const FProofNetworkState& State)
    {
        return IsValid(State.World) &&
            IsValid(State.World->GetNetDriver()) &&
            IsValid(State.CarrierA) &&
            IsValid(State.CarrierB) &&
            IsValid(State.Pickup) &&
            IsValid(State.PlacementAnchor) &&
            SemanticIdFor(State.CarrierA) == CarrierASemanticId &&
            SemanticIdFor(State.CarrierB) == CarrierBSemanticId &&
            SemanticIdFor(State.Pickup) == PickupSemanticId &&
            State.PlacementAnchor->HasAppliedProofIdentity() &&
            State.PlacementAnchor->GetProofAnchorSemanticId() ==
                PlacementAnchorSemanticId;
    }

    static bool MatchesDisposition(
        const FProofNetworkState& State,
        EVistaPickupDisposition Expected,
        const FVector* ExpectedReleaseVelocity = nullptr)
    {
        if (!HasProofIdentities(State) || !IsValid(State.Pickup->Mesh) ||
            !IsValid(State.Pickup->GetRootComponent()))
        {
            return false;
        }
        if (State.Pickup->GetActorTransform().ContainsNaN() ||
            State.Pickup->GetRootComponent()
                ->GetRelativeTransform().ContainsNaN())
        {
            return false;
        }
        const FVistaPickupReplicatedDisposition Disposition =
            State.Pickup->GetReplicatedDispositionForDevAutomation();
        AActor* InventoryItem = IVistaItemCarrier::Execute_VistaGetHeldItem(
            State.CarrierA);
        const USceneComponent* Parent =
            State.Pickup->GetRootComponent()->GetAttachParent();
        if (Disposition.Disposition != Expected)
        {
            return false;
        }
        const bool bLiveBodyMatchesReplicatedPayload =
            State.Pickup->Mesh->IsSimulatingPhysics() ==
                Disposition.bSimulatePhysics &&
            static_cast<uint8>(
                State.Pickup->Mesh->GetCollisionEnabled()) ==
                Disposition.CollisionEnabled &&
            State.Pickup->Mesh->GetCollisionProfileName() ==
                Disposition.CollisionProfileName &&
            VectorBitsEqual(
                State.Pickup->Mesh->GetPhysicsLinearVelocity(),
                Disposition.LinearVelocity) &&
            VectorBitsEqual(
                State.Pickup->Mesh->GetPhysicsAngularVelocityInDegrees(),
                Disposition.AngularVelocityDegrees);
        if (!bLiveBodyMatchesReplicatedPayload)
        {
            return false;
        }
        if (Expected == EVistaPickupDisposition::Held)
        {
            return Disposition.Carrier == State.CarrierA &&
                InventoryItem == State.Pickup &&
                Parent == State.CarrierA->GetProofCarryAnchor() &&
                Disposition.PlacementAnchorSemanticId.IsEmpty() &&
                !Disposition.bSimulatePhysics &&
                Disposition.CollisionEnabled ==
                    static_cast<uint8>(ECollisionEnabled::NoCollision) &&
                VectorBitsEqual(
                    Disposition.LinearVelocity, FVector::ZeroVector) &&
                VectorBitsEqual(
                    Disposition.AngularVelocityDegrees, FVector::ZeroVector) &&
                TransformBitsEqual(
                    Disposition.AttachmentRelativeTransform,
                    FTransform::Identity) &&
                TransformBitsEqual(
                    State.Pickup->GetRootComponent()->GetRelativeTransform(),
                    FTransform::Identity) &&
                State.Pickup->GetRootComponent()->GetAttachSocketName() ==
                    Disposition.AttachmentSocketName;
        }
        if (IsValid(Disposition.Carrier.Get()) || IsValid(InventoryItem) ||
            Parent != nullptr ||
            Disposition.CollisionEnabled !=
                static_cast<uint8>(ECollisionEnabled::QueryAndPhysics))
        {
            return false;
        }
        if (Expected == EVistaPickupDisposition::Placed)
        {
            return Disposition.PlacementAnchorSemanticId ==
                    PlacementAnchorSemanticId &&
                !Disposition.bSimulatePhysics &&
                VectorBitsEqual(
                    Disposition.LinearVelocity, FVector::ZeroVector) &&
                VectorBitsEqual(
                    Disposition.AngularVelocityDegrees, FVector::ZeroVector) &&
                TransformBitsEqual(
                    Disposition.WorldTransform,
                    State.PlacementAnchor->GetActorTransform()) &&
                TransformBitsEqual(
                    State.Pickup->GetActorTransform(),
                    State.PlacementAnchor->GetActorTransform()) &&
                TransformBitsEqual(
                    State.Pickup->GetActorTransform(),
                    Disposition.WorldTransform);
        }
        if (!Disposition.PlacementAnchorSemanticId.IsEmpty() ||
            !Disposition.bSimulatePhysics ||
            !State.Pickup->Mesh->IsSimulatingPhysics())
        {
            return false;
        }
        return ExpectedReleaseVelocity == nullptr
            ? TransformBitsEqual(
                  State.Pickup->GetActorTransform(),
                  Disposition.WorldTransform) &&
                  VectorBitsEqual(
                      Disposition.LinearVelocity, FVector::ZeroVector) &&
                  VectorBitsEqual(
                      Disposition.AngularVelocityDegrees,
                      FVector::ZeroVector)
            : VectorBitsEqual(
                  Disposition.LinearVelocity, *ExpectedReleaseVelocity) &&
                  VectorBitsEqual(
                      State.Pickup->Mesh->GetPhysicsLinearVelocity(),
                      *ExpectedReleaseVelocity);
    }

    TSharedPtr<FJsonObject> MakeWorldObservation(
        const FString& Checkpoint,
        const FProofNetworkState& State) const
    {
        const FVistaPickupReplicatedDisposition Disposition =
            State.Pickup->GetReplicatedDispositionForDevAutomation();
        AActor* InventoryItem = IVistaItemCarrier::Execute_VistaGetHeldItem(
            State.CarrierA);
        const USceneComponent* Parent =
            State.Pickup->GetRootComponent()->GetAttachParent();
        const bool bServer = State.World->GetNetDriver()->IsServer();

        TSharedPtr<FJsonObject> Object = MakeShared<FJsonObject>();
        Object->SetStringField(TEXT("checkpoint"), Checkpoint);
        Object->SetStringField(TEXT("role"), bServer ? TEXT("server") : TEXT("client"));
        Object->SetNumberField(TEXT("client_index"), bServer ? -1 : State.ClientIndex);
        Object->SetStringField(
            TEXT("net_mode"), NetModeName(State.World->GetNetMode()));
        Object->SetBoolField(TEXT("net_driver_is_server"), bServer);
        Object->SetBoolField(
            TEXT("pickup_has_authority"), State.Pickup->HasAuthority());
        Object->SetBoolField(
            TEXT("carrier_has_authority"), State.CarrierA->HasAuthority());
        Object->SetStringField(
            TEXT("disposition"), DispositionName(Disposition.Disposition));
        Object->SetStringField(
            TEXT("carrier_semantic_id"), SemanticIdFor(Disposition.Carrier.Get()));
        Object->SetStringField(
            TEXT("inventory_item_semantic_id"), SemanticIdFor(InventoryItem));
        Object->SetStringField(
            TEXT("placement_anchor_semantic_id"),
            Disposition.PlacementAnchorSemanticId);
        Object->SetBoolField(
            TEXT("simulate_physics"), Disposition.bSimulatePhysics);
        Object->SetNumberField(
            TEXT("collision_enabled"), Disposition.CollisionEnabled);
        Object->SetStringField(
            TEXT("collision_profile"),
            Disposition.CollisionProfileName.ToString());
        Object->SetStringField(
            TEXT("attachment_parent_name"),
            IsValid(Parent) ? Parent->GetName() : FString());
        Object->SetStringField(
            TEXT("attachment_socket"),
            Disposition.AttachmentSocketName.ToString());
        Object->SetArrayField(
            TEXT("world_transform_bits"),
            TransformBitArray(Disposition.WorldTransform));
        Object->SetArrayField(
            TEXT("attachment_relative_transform_bits"),
            TransformBitArray(Disposition.AttachmentRelativeTransform));
        Object->SetArrayField(
            TEXT("linear_velocity_bits"),
            VectorBitArray(Disposition.LinearVelocity));
        Object->SetArrayField(
            TEXT("angular_velocity_bits"),
            VectorBitArray(Disposition.AngularVelocityDegrees));
        Object->SetBoolField(
            TEXT("actual_simulate_physics"),
            State.Pickup->Mesh->IsSimulatingPhysics());
        Object->SetNumberField(
            TEXT("actual_collision_enabled"),
            static_cast<uint8>(State.Pickup->Mesh->GetCollisionEnabled()));
        Object->SetStringField(
            TEXT("actual_collision_profile"),
            State.Pickup->Mesh->GetCollisionProfileName().ToString());
        Object->SetArrayField(
            TEXT("actual_world_transform_bits"),
            TransformBitArray(State.Pickup->GetActorTransform()));
        Object->SetArrayField(
            TEXT("actual_relative_transform_bits"),
            TransformBitArray(
                State.Pickup->GetRootComponent()->GetRelativeTransform()));
        Object->SetArrayField(
            TEXT("actual_linear_velocity_bits"),
            VectorBitArray(
                State.Pickup->Mesh->GetPhysicsLinearVelocity()));
        Object->SetArrayField(
            TEXT("actual_angular_velocity_bits"),
            VectorBitArray(
                State.Pickup->Mesh->GetPhysicsAngularVelocityInDegrees()));
        return Object;
    }

    void AppendObservation(
        int32 CheckpointIndex,
        const FProofNetworkState& State)
    {
        if (!Checkpoints.IsValidIndex(CheckpointIndex))
        {
            AddError(TEXT("R5 proof checkpoint index invalid"));
            return;
        }
        FCheckpoint& Checkpoint = Checkpoints[CheckpointIndex];
        Checkpoint.Observations.Add(
            MakeShared<FJsonValueObject>(
                MakeWorldObservation(Checkpoint.Name, State)));
    }

    TSharedPtr<FJsonObject> TransactionJson(
        const FVistaActionTransactionRecord& Record) const
    {
        TSharedPtr<FJsonObject> Object = MakeShared<FJsonObject>();
        Object->SetStringField(TEXT("command_id"), Record.CommandId.ToString());
        Object->SetStringField(
            TEXT("status"), TransactionStatusName(Record.Status));
        Object->SetStringField(TEXT("code"), Record.Code.ToString());
        Object->SetNumberField(
            TEXT("physical_mutation_count"), Record.PhysicalMutationCount);
        Object->SetBoolField(
            TEXT("contact_mutation_attempted"),
            Record.bContactMutationAttempted);
        Object->SetBoolField(
            TEXT("contact_committed"), Record.bContactCommitted);
        Object->SetBoolField(
            TEXT("rollback_attempted"), Record.bRollbackAttempted);
        Object->SetBoolField(TEXT("rolled_back"), Record.bRolledBack);
        Object->SetStringField(
            TEXT("before_disposition"),
            Record.bHasBeforePhysicalState
                ? SnapshotDispositionName(Record.BeforePhysicalState)
                : TEXT("missing"));
        Object->SetStringField(
            TEXT("contact_disposition"),
            Record.bHasContactPhysicalState
                ? SnapshotDispositionName(Record.ContactPhysicalState)
                : TEXT("missing"));
        Object->SetStringField(
            TEXT("after_disposition"),
            Record.bHasAfterPhysicalState
                ? SnapshotDispositionName(Record.AfterPhysicalState)
                : TEXT("missing"));
        return Object;
    }

    bool WriteClosedReceipt()
    {
        FString AttemptId;
        FString ReceiptPath;
        FString TrustedGitCommit;
        FString TrustedProjectionDigest;
        FString InputManifestDigest;
        FString LaunchPlanDigest;
        FString BuildProvenanceDigest;
        if (!FParse::Value(
                FCommandLine::Get(),
                TEXT("VistaR5ProofAttemptId="),
                AttemptId) ||
            !FParse::Value(
                FCommandLine::Get(),
                TEXT("VistaR5ProofReceipt="),
                ReceiptPath) ||
            !FParse::Value(
                FCommandLine::Get(),
                TEXT("VistaR5ProofGitCommit="),
                TrustedGitCommit) ||
            !FParse::Value(
                FCommandLine::Get(),
                TEXT("VistaR5ProofProjectionDigest="),
                TrustedProjectionDigest) ||
            !FParse::Value(
                FCommandLine::Get(),
                TEXT("VistaR5ProofInputDigest="),
                InputManifestDigest) ||
            !FParse::Value(
                FCommandLine::Get(),
                TEXT("VistaR5ProofLaunchDigest="),
                LaunchPlanDigest) ||
            !FParse::Value(
                FCommandLine::Get(),
                TEXT("VistaR5ProofBuildDigest="),
                BuildProvenanceDigest) ||
            !IsSafeAttemptId(AttemptId) ||
            ReceiptPath != PrivateReceiptPath ||
            !IsLowerHexDigest(TrustedGitCommit, 40) ||
            !IsLowerHexDigest(TrustedProjectionDigest, 64) ||
            !IsLowerHexDigest(InputManifestDigest, 64) ||
            !IsLowerHexDigest(LaunchPlanDigest, 64) ||
            !IsLowerHexDigest(BuildProvenanceDigest, 64))
        {
            AddError(TEXT("R5 proof receipt command line/path contract invalid"));
            return false;
        }
        for (const FCheckpoint& Checkpoint : Checkpoints)
        {
            if (Checkpoint.Observations.Num() != 3)
            {
                AddError(FString::Printf(
                    TEXT("R5 checkpoint %s does not contain server + 2 clients"),
                    *Checkpoint.Name));
                return false;
            }
        }

        TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
        Root->SetStringField(
            TEXT("schema"), TEXT("vista.r5-multiclient-proof-receipt/v3"));
        Root->SetStringField(TEXT("status"), TEXT("passed"));
        Root->SetStringField(TEXT("attempt_id"), AttemptId);
        Root->SetStringField(
            TEXT("engine_version"), FEngineVersion::Current().ToString());
        Root->SetStringField(
            TEXT("harness"), TEXT("ue-cqtest-pie-dedicated-server-two-clients"));
        Root->SetNumberField(TEXT("client_count"), 2);
        Root->SetNumberField(TEXT("worlds_per_checkpoint"), 3);
        Root->SetStringField(TEXT("trusted_git_commit"), TrustedGitCommit);
        Root->SetStringField(
            TEXT("trusted_projection_digest"), TrustedProjectionDigest);
        Root->SetStringField(
            TEXT("input_manifest_digest"), InputManifestDigest);
        Root->SetStringField(TEXT("launch_plan_digest"), LaunchPlanDigest);
        Root->SetStringField(
            TEXT("build_provenance_digest"), BuildProvenanceDigest);

        TArray<TSharedPtr<FJsonValue>> CheckpointValues;
        for (const FCheckpoint& Checkpoint : Checkpoints)
        {
            TSharedPtr<FJsonObject> CheckpointObject = MakeShared<FJsonObject>();
            CheckpointObject->SetStringField(TEXT("name"), Checkpoint.Name);
            CheckpointObject->SetArrayField(
                TEXT("worlds"), Checkpoint.Observations);
            CheckpointValues.Add(
                MakeShared<FJsonValueObject>(CheckpointObject));
        }
        Root->SetArrayField(TEXT("checkpoints"), CheckpointValues);

        TSharedPtr<FJsonObject> Transactions = MakeShared<FJsonObject>();
        TSharedPtr<FJsonObject> Reset = MakeShared<FJsonObject>();
        if (!EventResetBeforeState.IsValid() ||
            !EventResetAfterRejectionState.IsValid())
        {
            AddError(TEXT("R5 proof reset rejection state is missing"));
            return false;
        }
        Reset->SetStringField(
            TEXT("claim"), TEXT("active_action_reset_rejection_only"));
        Reset->SetBoolField(TEXT("accepted"), bEventResetAccepted);
        Reset->SetStringField(TEXT("code"), EventResetCode.ToString());
        Reset->SetBoolField(
            TEXT("has_active_action_after_rejection"),
            bHasActiveActionAfterResetRejection);
        Reset->SetObjectField(
            TEXT("before_event"), EventResetBeforeState);
        Reset->SetObjectField(
            TEXT("after_rejection_event"), EventResetAfterRejectionState);
        Reset->SetObjectField(
            TEXT("active_transaction"), TransactionJson(EventResetActiveRecord));
        Transactions->SetObjectField(TEXT("event_reset_while_active"), Reset);
        Transactions->SetObjectField(TEXT("pickup"), TransactionJson(PickupRecord));
        Transactions->SetObjectField(TEXT("exact_retry"), TransactionJson(ReplayRecord));
        Transactions->SetObjectField(
            TEXT("command_id_collision"), TransactionJson(CollisionRecord));
        Transactions->SetObjectField(
            TEXT("failed_place_rollback"), TransactionJson(RollbackRecord));
        Transactions->SetObjectField(TEXT("place"), TransactionJson(PlaceRecord));
        Transactions->SetObjectField(
            TEXT("pickup_again"), TransactionJson(PickupAgainRecord));
        Transactions->SetObjectField(TEXT("drop"), TransactionJson(DropRecord));
        Root->SetObjectField(TEXT("transactions"), Transactions);

        FString Serialized;
        const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>>
            Writer = TJsonWriterFactory<
                TCHAR,
                TCondensedJsonPrintPolicy<TCHAR>>::Create(&Serialized);
        if (!FJsonSerializer::Serialize(Root.ToSharedRef(), Writer))
        {
            AddError(TEXT("R5 proof receipt serialization failed"));
            return false;
        }
        const FString TemporaryPath = ReceiptPath + TEXT(".tmp-") +
            FGuid::NewGuid().ToString(EGuidFormats::Digits);
        if (!FFileHelper::SaveStringToFile(
                Serialized,
                *TemporaryPath,
                FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM) ||
            !IFileManager::Get().Move(
                *ReceiptPath,
                *TemporaryPath,
                false,
                false,
                false,
                true))
        {
            IFileManager::Get().Delete(*TemporaryPath, false, true, true);
            AddError(TEXT("R5 proof private receipt atomic close failed"));
            return false;
        }
        return true;
    }

    TEST_METHOD(ReplicatesTransactionalPhysicalState)
    {
        Network
            .SpawnAndReplicate<
                AVistaR5ProofCarrier,
                &FProofNetworkState::CarrierA>(
                [](AVistaR5ProofCarrier& Carrier)
                {
                    Carrier.ConfigureProofIdentity(CarrierASemanticId);
                })
            .SpawnAndReplicate<
                AVistaR5ProofCarrier,
                &FProofNetworkState::CarrierB>(
                [](AVistaR5ProofCarrier& Carrier)
                {
                    Carrier.ConfigureProofIdentity(CarrierBSemanticId);
                })
            .SpawnAndReplicate<
                AVistaPickupActor,
                &FProofNetworkState::Pickup>(
                [](AVistaPickupActor& Pickup)
                {
                    Pickup.SemanticId = PickupSemanticId;
                    Pickup.WorldRevision = ProofRevision;
                    Pickup.Mesh->SetEnableGravity(false);
                })
            .SpawnAndReplicate<
                AVistaR5ProofPlacementAnchor,
                &FProofNetworkState::PlacementAnchor>(
                [](AVistaR5ProofPlacementAnchor& Anchor)
                {
                    Anchor.ConfigureProofIdentity(
                        PlacementOwnerSemanticId,
                        PlacementAnchorSemanticId);
                    Anchor.SetActorLocation(FVector(120.0, 0.0, 0.0));
                })
            .UntilClients(
                TEXT("clients receive proof identities and initial free state"),
                [](FProofNetworkState& State)
                {
                    return HasProofIdentities(State) &&
                        MatchesDisposition(
                            State, EVistaPickupDisposition::Free);
                })
            .ThenServer(
                TEXT("record initial server authority"),
                [this](FProofNetworkState& State)
                {
                    if (Require(
                            State.World->GetNetMode() == NM_DedicatedServer &&
                                State.World->GetNetDriver()->IsServer() &&
                                State.Pickup->HasAuthority() &&
                                State.CarrierA->HasAuthority() &&
                                MatchesDisposition(
                                    State, EVistaPickupDisposition::Free),
                            TEXT("server initial authority/free state invalid")))
                    {
                        AppendObservation(0, State);
                    }
                })
            .ThenClients(
                TEXT("record initial client replicas"),
                [this](FProofNetworkState& State)
                {
                    if (Require(
                            State.World->GetNetMode() == NM_Client &&
                                !State.World->GetNetDriver()->IsServer() &&
                                !State.Pickup->HasAuthority() &&
                                !State.CarrierA->HasAuthority() &&
                                MatchesDisposition(
                                    State, EVistaPickupDisposition::Free),
                            TEXT("client initial authority/free state invalid")))
                    {
                        AppendObservation(0, State);
                    }
                })
            .ThenServer(
                TEXT("event reset rejects active physical action"),
                [this](FProofNetworkState& State)
                {
                    UVistaEventSubsystem* Events =
                        State.World->GetSubsystem<UVistaEventSubsystem>();
                    if (!Require(
                            IsValid(Events),
                            TEXT("event subsystem unavailable")))
                    {
                        return;
                    }
                    Events->InitializeWorldRevision(ProofRevision);
                    FVistaEventDefinition Definition;
                    Definition.EventId = ProofEventId;
                    Definition.CompatibleRevision = ProofRevision;
                    Definition.PublicTitle = TEXT("R5 proof active reset gate");
                    Definition.PublicGoal = TEXT("Remain active during proof");
                    Definition.TimeoutSeconds = 3600.0f;
                    FVistaEventCondition Success;
                    Success.ConditionId = TEXT("proof-elapsed");
                    Success.Type = EVistaEventConditionType::Elapsed;
                    Success.Operator = EVistaEventConditionOperator::Gte;
                    Success.Seconds = 3000.0f;
                    Definition.SuccessConditions.Add(Success);
                    FName Code;
                    if (!Require(
                            Events->RegisterEventDefinitions({Definition}, Code) &&
                                Code == FName(TEXT("EVENTS_REGISTERED")) &&
                                Events->StartEvent(
                                    ProofEventId, ProofRevision, 0, Code) &&
                                Code == FName(TEXT("EVENT_STARTED")),
                            TEXT("proof event failed to start")))
                    {
                        return;
                    }
                    const FVistaPhysicalActionRequest Request = MakeRequest(
                        State,
                        State.CarrierA,
                        TEXT("r5-event-reset-active"),
                        EVistaAffordance::PickUp);
                    if (!Require(
                            State.CarrierA->GetProofExecutor()
                                ->BeginPhysicalInteractionForDevAutomation(
                                    Request, EventResetActiveRecord) &&
                                State.CarrierA->GetProofExecutor()
                                    ->HasActiveAction(),
                            TEXT("proof active action did not begin")))
                    {
                        return;
                    }
                    EventResetBeforeState = EventStateJson(Events);
                    bEventResetAccepted = Events->ResetEvent(
                        ProofRevision, 0, EventResetCode);
                    EventResetAfterRejectionState = EventStateJson(Events);
                    bHasActiveActionAfterResetRejection =
                        State.CarrierA->GetProofExecutor()->HasActiveAction();
                    Require(
                        !bEventResetAccepted &&
                            EventResetCode ==
                                FName(TEXT("EVENT_RESET_ACTION_ACTIVE")) &&
                            bHasActiveActionAfterResetRejection,
                        TEXT("event reset did not fail closed on active action"));
                    Require(
                        State.CarrierA->GetProofExecutor()->CancelActiveAction(
                            TEXT("R5_PROOF_ACTIVE_RESET_CLEANUP")),
                        TEXT("active reset proof cleanup failed"));
                    State.CarrierA->GetProofExecutor()->GetTransaction(
                        Request.CommandId, EventResetActiveRecord);
                })
            .ThenServer(
                TEXT("pickup commits once"),
                [this](FProofNetworkState& State)
                {
                    const FVistaPhysicalActionRequest Request = MakeRequest(
                        State,
                        State.CarrierA,
                        TEXT("r5-pickup-once"),
                        EVistaAffordance::PickUp);
                    FVistaActionTransactionRecord BeginRecord;
                    Require(
                        State.CarrierA->GetProofExecutor()
                            ->BeginPhysicalInteractionForDevAutomation(
                                Request, BeginRecord) &&
                            State.CarrierA->GetProofExecutor()
                                ->DrivePhysicalInteractionForDevAutomation(
                                    false, PickupRecord) &&
                            PickupRecord.Status ==
                                EVistaActionTransactionStatus::Succeeded &&
                            PickupRecord.PhysicalMutationCount == 1 &&
                            PickupRecord.bContactCommitted,
                        TEXT("pickup transaction did not commit exactly once"));
                })
            .UntilClients(
                TEXT("clients receive held disposition and inventory"),
                [](FProofNetworkState& State)
                {
                    return MatchesDisposition(
                        State, EVistaPickupDisposition::Held);
                })
            .ThenServer(
                TEXT("record held server state"),
                [this](FProofNetworkState& State)
                {
                    if (Require(
                            MatchesDisposition(
                                State, EVistaPickupDisposition::Held),
                            TEXT("server held state invalid")))
                    {
                        AppendObservation(1, State);
                    }
                })
            .ThenClients(
                TEXT("record held client replicas"),
                [this](FProofNetworkState& State)
                {
                    if (Require(
                            MatchesDisposition(
                                State, EVistaPickupDisposition::Held),
                            TEXT("client held state invalid")))
                    {
                        AppendObservation(1, State);
                    }
                })
            .ThenServer(
                TEXT("world ledger replays exact request and rejects collision"),
                [this](FProofNetworkState& State)
                {
                    UVistaActionExecutorComponent* ReplayExecutor =
                        NewObject<UVistaActionExecutorComponent>(
                            State.CarrierA,
                            TEXT("ProofReplayExecutor"));
                    State.CarrierA->AddInstanceComponent(ReplayExecutor);
                    ReplayExecutor->RegisterComponent();
                    const FVistaPhysicalActionRequest ExactRetry = MakeRequest(
                        State,
                        State.CarrierA,
                        PickupRecord.CommandId,
                        EVistaAffordance::PickUp);
                    const FVistaPickupReplicatedDisposition BeforeReplay =
                        State.Pickup
                            ->GetReplicatedDispositionForDevAutomation();
                    if (!Require(
                            ReplayExecutor->BeginPhysicalInteraction(
                                ExactRetry, ReplayRecord) &&
                                !ReplayExecutor->HasActiveAction() &&
                                ReplayRecord.Status ==
                                    EVistaActionTransactionStatus::Succeeded &&
                                ReplayRecord.PhysicalMutationCount == 1 &&
                                ReplayRecord.CommandId == PickupRecord.CommandId,
                            TEXT("world ledger exact retry did not replay")))
                    {
                        return;
                    }
                    const FVistaPickupReplicatedDisposition AfterReplay =
                        State.Pickup
                            ->GetReplicatedDispositionForDevAutomation();
                    Require(
                        BeforeReplay.Disposition == AfterReplay.Disposition &&
                            BeforeReplay.Carrier == AfterReplay.Carrier &&
                            TransformBitsEqual(
                                BeforeReplay.AttachmentRelativeTransform,
                                AfterReplay.AttachmentRelativeTransform) &&
                            VectorBitsEqual(
                                BeforeReplay.LinearVelocity,
                                AfterReplay.LinearVelocity),
                        TEXT("exact retry changed physical state"));

                    const FVistaPhysicalActionRequest Collision = MakeRequest(
                        State,
                        State.CarrierB,
                        PickupRecord.CommandId,
                        EVistaAffordance::PickUp);
                    Require(
                        !State.CarrierB->GetProofExecutor()
                            ->BeginPhysicalInteraction(
                                Collision, CollisionRecord) &&
                            CollisionRecord.Code ==
                                FName(TEXT("COMMAND_ID_COLLISION")) &&
                            CollisionRecord.PhysicalMutationCount == 0 &&
                            !State.CarrierB->GetProofExecutor()
                                ->HasActiveAction() &&
                            MatchesDisposition(
                                State, EVistaPickupDisposition::Held),
                        TEXT("world ledger command-id collision did not fail closed"));
                })
            .ThenServer(
                TEXT("post-contact place failure rolls back full held state"),
                [this](FProofNetworkState& State)
                {
                    const FVistaPhysicalActionRequest Request = MakeRequest(
                        State,
                        State.CarrierA,
                        TEXT("r5-place-forced-failure"),
                        EVistaAffordance::Place);
                    FVistaActionTransactionRecord BeginRecord;
                    Require(
                        State.CarrierA->GetProofExecutor()
                            ->BeginPhysicalInteractionForDevAutomation(
                                Request, BeginRecord) &&
                            State.CarrierA->GetProofExecutor()
                                ->DrivePhysicalInteractionForDevAutomation(
                                    true, RollbackRecord) &&
                            RollbackRecord.Status ==
                                EVistaActionTransactionStatus::Failed &&
                            RollbackRecord.bContactMutationAttempted &&
                            RollbackRecord.bContactCommitted &&
                            RollbackRecord.PhysicalMutationCount == 1 &&
                            RollbackRecord.bRollbackAttempted &&
                            RollbackRecord.bRolledBack &&
                            RollbackRecord.bHasBeforePhysicalState &&
                            RollbackRecord.bHasAfterPhysicalState &&
                            SnapshotBitsEqual(
                                RollbackRecord.BeforePhysicalState,
                                RollbackRecord.AfterPhysicalState) &&
                            MatchesDisposition(
                                State, EVistaPickupDisposition::Held),
                        TEXT("failed place did not restore exact held snapshot/inventory"));
                })
            .UntilClients(
                TEXT("clients retain held state after rollback"),
                [](FProofNetworkState& State)
                {
                    return MatchesDisposition(
                        State, EVistaPickupDisposition::Held);
                })
            .ThenServer(
                TEXT("record rolled-back server state"),
                [this](FProofNetworkState& State)
                {
                    AppendObservation(2, State);
                })
            .ThenClients(
                TEXT("record rolled-back client replicas"),
                [this](FProofNetworkState& State)
                {
                    AppendObservation(2, State);
                })
            .ThenServer(
                TEXT("place commits authoritative target transform"),
                [this](FProofNetworkState& State)
                {
                    const FVistaPhysicalActionRequest Request = MakeRequest(
                        State,
                        State.CarrierA,
                        TEXT("r5-place-success"),
                        EVistaAffordance::Place);
                    FVistaActionTransactionRecord BeginRecord;
                    Require(
                        State.CarrierA->GetProofExecutor()
                            ->BeginPhysicalInteractionForDevAutomation(
                                Request, BeginRecord) &&
                            State.CarrierA->GetProofExecutor()
                                ->DrivePhysicalInteractionForDevAutomation(
                                    false, PlaceRecord) &&
                            PlaceRecord.PhysicalMutationCount == 1 &&
                            MatchesDisposition(
                                State, EVistaPickupDisposition::Placed),
                        TEXT("place did not commit exact TargetPoint state"));
                })
            .UntilClients(
                TEXT("clients receive placed disposition and transform"),
                [](FProofNetworkState& State)
                {
                    return MatchesDisposition(
                        State, EVistaPickupDisposition::Placed);
                })
            .ThenServer(
                TEXT("record placed server state"),
                [this](FProofNetworkState& State)
                {
                    AppendObservation(3, State);
                })
            .ThenClients(
                TEXT("record placed client replicas"),
                [this](FProofNetworkState& State)
                {
                    AppendObservation(3, State);
                })
            .ThenServer(
                TEXT("pickup placed cup again"),
                [this](FProofNetworkState& State)
                {
                    const FVistaPhysicalActionRequest Request = MakeRequest(
                        State,
                        State.CarrierA,
                        TEXT("r5-pickup-again"),
                        EVistaAffordance::PickUp);
                    FVistaActionTransactionRecord BeginRecord;
                    Require(
                        State.CarrierA->GetProofExecutor()
                            ->BeginPhysicalInteractionForDevAutomation(
                                Request, BeginRecord) &&
                            State.CarrierA->GetProofExecutor()
                                ->DrivePhysicalInteractionForDevAutomation(
                                    false, PickupAgainRecord) &&
                            MatchesDisposition(
                                State, EVistaPickupDisposition::Held),
                        TEXT("second pickup failed"));
                })
            .UntilClients(
                TEXT("clients receive second held state"),
                [](FProofNetworkState& State)
                {
                    return MatchesDisposition(
                        State, EVistaPickupDisposition::Held);
                })
            .ThenServer(
                TEXT("record second held server state"),
                [this](FProofNetworkState& State)
                {
                    AppendObservation(4, State);
                })
            .ThenClients(
                TEXT("record second held client replicas"),
                [this](FProofNetworkState& State)
                {
                    AppendObservation(4, State);
                })
            .ThenServer(
                TEXT("drop commits replicated release velocity"),
                [this](FProofNetworkState& State)
                {
                    const FVistaPhysicalActionRequest Request = MakeRequest(
                        State,
                        State.CarrierA,
                        TEXT("r5-drop-success"),
                        EVistaAffordance::Drop,
                        DropVelocity);
                    FVistaActionTransactionRecord BeginRecord;
                    Require(
                        State.CarrierA->GetProofExecutor()
                            ->BeginPhysicalInteractionForDevAutomation(
                                Request, BeginRecord) &&
                            State.CarrierA->GetProofExecutor()
                                ->DrivePhysicalInteractionForDevAutomation(
                                    false, DropRecord) &&
                            DropRecord.PhysicalMutationCount == 1 &&
                            MatchesDisposition(
                                State,
                                EVistaPickupDisposition::Free,
                                &DropVelocity),
                        TEXT("drop did not commit exact release velocity"));
                })
            .UntilClients(
                TEXT("clients receive free disposition and release velocity"),
                [](FProofNetworkState& State)
                {
                    return MatchesDisposition(
                        State,
                        EVistaPickupDisposition::Free,
                        &DropVelocity);
                })
            .ThenServer(
                TEXT("record dropped server state"),
                [this](FProofNetworkState& State)
                {
                    AppendObservation(5, State);
                })
            .ThenClients(
                TEXT("record dropped client replicas"),
                [this](FProofNetworkState& State)
                {
                    AppendObservation(5, State);
                })
            .Then(
                TEXT("atomically close structured proof receipt"),
                [this]()
                {
                    Require(
                        WriteClosedReceipt(),
                        TEXT("R5 structured receipt was not closed"));
                });
    }
};

#endif // ENABLE_PIE_NETWORK_TEST && WITH_DEV_AUTOMATION_TESTS
