#if WITH_DEV_AUTOMATION_TESTS

#include "Animation/AnimData/IAnimationDataModel.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Misc/AutomationTest.h"
#include "Modules/ModuleManager.h"
#include "ReferenceSkeleton.h"
#include "UObject/UObjectGlobals.h"
#include "VistaAnimationSignalNotify.h"

namespace VistaR15DetailActionAssetContract {
constexpr const TCHAR *ContentNamespace =
    TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions");
constexpr const TCHAR *SkeletonPath =
    TEXT("/Game/VISTA/MakeHumanCC0/R6/"
         "SK_VISTA_CC0_Hero_R6_Skeleton.SK_VISTA_CC0_Hero_R6_Skeleton");
constexpr int32 FramesPerSecond = 30;
constexpr int32 ExpectedBoneTrackCount = 53;
constexpr int32 ExpectedAssetCount = 18;
constexpr int32 ExpectedNotifyOccurrenceCount = 16;
constexpr int32 ExpectedUniqueSignalCount = 14;
constexpr float TimeToleranceSeconds = 1.0F / 3000.0F;
constexpr float TransformTolerance = 1.0E-5F;

struct FNotifySpec {
  const TCHAR *Signal;
  int32 Frame;
};

struct FClipSpec {
  const TCHAR *ClipId;
  const TCHAR *SequencePath;
  const TCHAR *MontagePath;
  int32 FrameCount;
  int32 NotifyCount;
  FNotifySpec Notifies[2];
};

const FClipSpec ClipSpecs[] = {
    {
        TEXT("rotary_turn_on_right"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Sequences/"
             "AS_VistaCC0RotaryTurnOnRight_R15."
             "AS_VistaCC0RotaryTurnOnRight_R15"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
             "AM_VistaCC0RotaryTurnOnRight_R15."
             "AM_VistaCC0RotaryTurnOnRight_R15"),
        72,
        2,
        {{TEXT("vista_appliance_power_contact"), 24},
         {TEXT("vista_appliance_turn_on_completed"), 60}},
    },
    {
        TEXT("rotary_turn_off_right"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Sequences/"
             "AS_VistaCC0RotaryTurnOffRight_R15."
             "AS_VistaCC0RotaryTurnOffRight_R15"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
             "AM_VistaCC0RotaryTurnOffRight_R15."
             "AM_VistaCC0RotaryTurnOffRight_R15"),
        72,
        2,
        {{TEXT("vista_appliance_power_contact"), 24},
         {TEXT("vista_appliance_turn_off_completed"), 60}},
    },
    {
        TEXT("button_press_right"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Sequences/"
             "AS_VistaCC0ButtonPressRight_R15."
             "AS_VistaCC0ButtonPressRight_R15"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
             "AM_VistaCC0ButtonPressRight_R15."
             "AM_VistaCC0ButtonPressRight_R15"),
        66,
        2,
        {{TEXT("vista_appliance_button_contact"), 24},
         {TEXT("vista_appliance_press_completed"), 54}},
    },
    {
        TEXT("cabinet_drawer_open_right"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Sequences/"
             "AS_VistaCC0CabinetDrawerOpenRight_R15."
             "AS_VistaCC0CabinetDrawerOpenRight_R15"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
             "AM_VistaCC0CabinetDrawerOpenRight_R15."
             "AM_VistaCC0CabinetDrawerOpenRight_R15"),
        78,
        2,
        {{TEXT("vista_cabinet_handle_contact"), 26},
         {TEXT("vista_cabinet_open_completed"), 66}},
    },
    {
        TEXT("cabinet_drawer_close_right"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Sequences/"
             "AS_VistaCC0CabinetDrawerCloseRight_R15."
             "AS_VistaCC0CabinetDrawerCloseRight_R15"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
             "AM_VistaCC0CabinetDrawerCloseRight_R15."
             "AM_VistaCC0CabinetDrawerCloseRight_R15"),
        78,
        2,
        {{TEXT("vista_cabinet_handle_contact"), 26},
         {TEXT("vista_cabinet_close_completed"), 66}},
    },
    {
        TEXT("sit_down_chair"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Sequences/"
             "AS_VistaCC0SitDownChair_R15.AS_VistaCC0SitDownChair_R15"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
             "AM_VistaCC0SitDownChair_R15.AM_VistaCC0SitDownChair_R15"),
        90,
        2,
        {{TEXT("vista_chair_seat_contact"), 54},
         {TEXT("vista_sit_completed"), 78}},
    },
    {
        TEXT("seated_idle_loop"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Sequences/"
             "AS_VistaCC0SeatedIdleLoop_R15.AS_VistaCC0SeatedIdleLoop_R15"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
             "AM_VistaCC0SeatedIdleLoop_R15.AM_VistaCC0SeatedIdleLoop_R15"),
        60,
        1,
        {{TEXT("vista_seated_idle_cycle_completed"), 54}, {nullptr, 0}},
    },
    {
        TEXT("stand_up_chair"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Sequences/"
             "AS_VistaCC0StandUpChair_R15.AS_VistaCC0StandUpChair_R15"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
             "AM_VistaCC0StandUpChair_R15.AM_VistaCC0StandUpChair_R15"),
        90,
        1,
        {{TEXT("vista_stand_completed"), 78}, {nullptr, 0}},
    },
    {
        TEXT("pour_right"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Sequences/"
             "AS_VistaCC0PourRight_R15.AS_VistaCC0PourRight_R15"),
        TEXT("/Game/VISTA/MakeHumanCC0/R15/DetailActions/Montages/"
             "AM_VistaCC0PourRight_R15.AM_VistaCC0PourRight_R15"),
        96,
        2,
        {{TEXT("vista_pour_tilt_contact"), 36},
         {TEXT("vista_pour_completed"), 84}},
    },
};
static_assert(UE_ARRAY_COUNT(ClipSpecs) == 9,
              "R15 asset proof is closed to exactly nine clips");

const TCHAR *ExpectedBoneNames[] = {
    TEXT("ball_l"),      TEXT("ball_r"),      TEXT("calf_l"),
    TEXT("calf_r"),      TEXT("clavicle_l"),  TEXT("clavicle_r"),
    TEXT("foot_l"),      TEXT("foot_r"),      TEXT("hand_l"),
    TEXT("hand_r"),      TEXT("head"),        TEXT("index_01_l"),
    TEXT("index_01_r"),  TEXT("index_02_l"),  TEXT("index_02_r"),
    TEXT("index_03_l"),  TEXT("index_03_r"),  TEXT("lowerarm_l"),
    TEXT("lowerarm_r"),  TEXT("middle_01_l"), TEXT("middle_01_r"),
    TEXT("middle_02_l"), TEXT("middle_02_r"), TEXT("middle_03_l"),
    TEXT("middle_03_r"), TEXT("neck_01"),     TEXT("pelvis"),
    TEXT("pinky_01_l"),  TEXT("pinky_01_r"),  TEXT("pinky_02_l"),
    TEXT("pinky_02_r"),  TEXT("pinky_03_l"),  TEXT("pinky_03_r"),
    TEXT("ring_01_l"),   TEXT("ring_01_r"),   TEXT("ring_02_l"),
    TEXT("ring_02_r"),   TEXT("ring_03_l"),   TEXT("ring_03_r"),
    TEXT("root"),        TEXT("spine_01"),    TEXT("spine_02"),
    TEXT("spine_03"),    TEXT("thigh_l"),     TEXT("thigh_r"),
    TEXT("thumb_01_l"),  TEXT("thumb_01_r"),  TEXT("thumb_02_l"),
    TEXT("thumb_02_r"),  TEXT("thumb_03_l"),  TEXT("thumb_03_r"),
    TEXT("upperarm_l"),  TEXT("upperarm_r"),
};
static_assert(UE_ARRAY_COUNT(ExpectedBoneNames) == ExpectedBoneTrackCount,
              "R6 source-track closure must stay at 53 bones");

template <typename T> T *LoadExact(const TCHAR *ObjectPath) {
  T *Asset = LoadObject<T>(nullptr, ObjectPath);
  return IsValid(Asset) && Asset->GetPathName() == ObjectPath ? Asset : nullptr;
}

FString InventoryKey(const FTopLevelAssetPath &ClassPath,
                     const FString &ObjectPath) {
  return ClassPath.ToString() + TEXT("|") + ObjectPath;
}

FString Context(const TCHAR *ClipId, const TCHAR *Check) {
  return FString::Printf(TEXT("%s: %s"), ClipId, Check);
}
} // namespace VistaR15DetailActionAssetContract

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FVistaR15DetailActionAssetContractProof,
    "VISTA.PlayableHome.R15DetailActions.AssetContract",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FVistaR15DetailActionAssetContractProof::RunTest(
    const FString &Parameters) {
  using namespace VistaR15DetailActionAssetContract;
  static_cast<void>(Parameters);

  TSet<FString> ExpectedInventory;
  TArray<FString> ExpectedObjectPaths;
  for (const FClipSpec &Spec : ClipSpecs) {
    const FString SequencePath(Spec.SequencePath);
    const FString MontagePath(Spec.MontagePath);
    ExpectedObjectPaths.Add(SequencePath);
    ExpectedObjectPaths.Add(MontagePath);
    ExpectedInventory.Add(InventoryKey(
        UAnimSequence::StaticClass()->GetClassPathName(), SequencePath));
    ExpectedInventory.Add(InventoryKey(
        UAnimMontage::StaticClass()->GetClassPathName(), MontagePath));
  }
  TestEqual(TEXT("closed inventory contains 18 unique identities"),
            ExpectedInventory.Num(), ExpectedAssetCount);

  // A fresh editor process must execute this test before anything loads the R15
  // namespace. This makes the subsequent disk inventory + LoadObject pass a
  // genuine cold-load contract instead of an in-memory inspection.
  for (const FString &ObjectPath : ExpectedObjectPaths) {
    TestTrue(FString::Printf(TEXT("cold precondition: %s is not loaded"),
                             *ObjectPath),
             FindObject<UObject>(nullptr, *ObjectPath) == nullptr);
  }
  if (HasAnyErrors()) {
    AddError(TEXT("R15 cold-load precondition failed; run this test first in "
                  "a fresh UnrealEditor-Cmd process"));
    return false;
  }

  IAssetRegistry &Registry =
      FModuleManager::LoadModuleChecked<FAssetRegistryModule>(
          TEXT("AssetRegistry"))
          .Get();
  Registry.ScanPathsSynchronous({FString(ContentNamespace)}, false, false);
  Registry.WaitForCompletion();

  TArray<FAssetData> DiskAssets;
  const bool bRegistryQuerySucceeded =
      Registry.GetAssetsByPath(FName(ContentNamespace), DiskAssets, true, true);
  TestTrue(TEXT("R15 on-disk Asset Registry query succeeds"),
           bRegistryQuerySucceeded);
  TestEqual(TEXT("R15 namespace has exactly 18 on-disk assets"),
            DiskAssets.Num(), ExpectedAssetCount);

  TSet<FString> ObservedInventory;
  for (const FAssetData &AssetData : DiskAssets) {
    const FString Key =
        InventoryKey(AssetData.AssetClassPath, AssetData.GetObjectPathString());
    TestTrue(FString::Printf(TEXT("expected on-disk asset: %s"), *Key),
             ExpectedInventory.Contains(Key));
    TestTrue(
        FString::Printf(TEXT("on-disk asset identity is unique: %s"), *Key),
        !ObservedInventory.Contains(Key));
    ObservedInventory.Add(Key);
  }
  for (const FString &Key : ExpectedInventory) {
    TestTrue(FString::Printf(TEXT("on-disk inventory contains: %s"), *Key),
             ObservedInventory.Contains(Key));
  }
  for (const FString &ObjectPath : ExpectedObjectPaths) {
    TestTrue(FString::Printf(TEXT("registry scan does not warm-load: %s"),
                             *ObjectPath),
             FindObject<UObject>(nullptr, *ObjectPath) == nullptr);
  }
  if (HasAnyErrors()) {
    return false;
  }

  USkeleton *Skeleton = LoadExact<USkeleton>(SkeletonPath);
  if (!IsValid(Skeleton)) {
    AddError(FString::Printf(TEXT("exact R6 skeleton cannot cold-load: %s"),
                             SkeletonPath));
    return false;
  }

  TSet<FName> ExpectedBoneSet;
  for (const TCHAR *BoneName : ExpectedBoneNames) {
    ExpectedBoneSet.Add(FName(BoneName));
  }
  TestEqual(TEXT("expected R6 bone names are unique"), ExpectedBoneSet.Num(),
            ExpectedBoneTrackCount);
  const FReferenceSkeleton &ReferenceSkeleton =
      Skeleton->GetReferenceSkeleton();
  TestEqual(TEXT("exact R6 skeleton has 53 reference bones"),
            ReferenceSkeleton.GetNum(), ExpectedBoneTrackCount);
  for (const FName ExpectedBone : ExpectedBoneSet) {
    TestTrue(FString::Printf(TEXT("R6 reference bone present: %s"),
                             *ExpectedBone.ToString()),
             ReferenceSkeleton.FindBoneIndex(ExpectedBone) != INDEX_NONE);
  }

  TSet<FName> ObservedUniqueSignals;
  int32 ObservedNotifyOccurrences = 0;
  const FName RootBoneName(TEXT("root"));
  for (const FClipSpec &Spec : ClipSpecs) {
    UAnimSequence *Sequence = LoadExact<UAnimSequence>(Spec.SequencePath);
    UAnimMontage *Montage = LoadExact<UAnimMontage>(Spec.MontagePath);
    if (!IsValid(Sequence) || !IsValid(Montage)) {
      AddError(Context(Spec.ClipId,
                       TEXT("exact sequence or montage cannot cold-load")));
      continue;
    }

    TestTrue(Context(Spec.ClipId, TEXT("sequence uses exact R6 skeleton")),
             Sequence->GetSkeleton() == Skeleton);
    TestTrue(Context(Spec.ClipId, TEXT("montage uses exact R6 skeleton")),
             Montage->GetSkeleton() == Skeleton);
    TestFalse(Context(Spec.ClipId, TEXT("sequence root motion disabled")),
              Sequence->bEnableRootMotion);
    TestTrue(Context(Spec.ClipId, TEXT("sequence root lock forced")),
             Sequence->bForceRootLock);
    TestEqual(Context(Spec.ClipId, TEXT("root lock is reference pose")),
              static_cast<int32>(Sequence->RootMotionRootLock.GetValue()),
              static_cast<int32>(ERootMotionRootLock::RefPose));
    TestFalse(Context(Spec.ClipId, TEXT("sequence reports no root motion")),
              Sequence->HasRootMotion());
    TestFalse(Context(Spec.ClipId, TEXT("montage reports no root motion")),
              Montage->HasRootMotion());
    TestEqual(Context(Spec.ClipId, TEXT("sequence has no notifies")),
              Sequence->Notifies.Num(), 0);

    IAnimationDataModel *DataModel = Sequence->GetDataModel();
    if (DataModel == nullptr) {
      AddError(
          Context(Spec.ClipId, TEXT("sequence data model is unavailable")));
      continue;
    }
    const FFrameRate SourceRate = DataModel->GetFrameRate();
    const FFrameRate SampleRate = Sequence->GetSamplingFrameRate();
    TestEqual(Context(Spec.ClipId, TEXT("source fps numerator")),
              SourceRate.Numerator, FramesPerSecond);
    TestEqual(Context(Spec.ClipId, TEXT("source fps denominator")),
              SourceRate.Denominator, 1);
    TestEqual(Context(Spec.ClipId, TEXT("sample fps numerator")),
              SampleRate.Numerator, FramesPerSecond);
    TestEqual(Context(Spec.ClipId, TEXT("sample fps denominator")),
              SampleRate.Denominator, 1);
    TestEqual(Context(Spec.ClipId, TEXT("source frame count")),
              DataModel->GetNumberOfFrames(), Spec.FrameCount);
    TestEqual(Context(Spec.ClipId, TEXT("sampled key count is inclusive")),
              Sequence->GetNumberOfSampledKeys(), Spec.FrameCount + 1);
    TestTrue(Context(Spec.ClipId, TEXT("play length matches frames/fps")),
             FMath::IsNearlyEqual(Sequence->GetPlayLength(),
                                  static_cast<double>(Spec.FrameCount) /
                                      FramesPerSecond,
                                  static_cast<double>(TimeToleranceSeconds)));

    TArray<FName> BoneTrackNames;
    DataModel->GetBoneTrackNames(BoneTrackNames);
    TSet<FName> BoneTrackSet;
    for (const FName BoneName : BoneTrackNames) {
      BoneTrackSet.Add(BoneName);
    }
    TestEqual(Context(Spec.ClipId, TEXT("bone-track count")),
              DataModel->GetNumBoneTracks(), ExpectedBoneTrackCount);
    TestEqual(Context(Spec.ClipId, TEXT("bone-track names are unique")),
              BoneTrackSet.Num(), ExpectedBoneTrackCount);
    for (const FName ExpectedBone : ExpectedBoneSet) {
      TestTrue(
          Context(Spec.ClipId, *FString::Printf(TEXT("bone track present: %s"),
                                                *ExpectedBone.ToString())),
          BoneTrackSet.Contains(ExpectedBone));
    }

    if (DataModel->IsValidBoneTrackName(RootBoneName)) {
      const FTransform InitialRoot =
          DataModel->GetBoneTrackTransform(RootBoneName, FFrameNumber(0));
      for (int32 Frame = 0; Frame <= Spec.FrameCount; ++Frame) {
        const FTransform RootAtFrame =
            DataModel->GetBoneTrackTransform(RootBoneName, FFrameNumber(Frame));
        TestTrue(Context(Spec.ClipId,
                         *FString::Printf(
                             TEXT("root delta is zero at frame %d"), Frame)),
                 RootAtFrame.Equals(InitialRoot, TransformTolerance));
      }
    } else {
      AddError(Context(Spec.ClipId, TEXT("root bone track is missing")));
    }

    TestTrue(Context(Spec.ClipId, TEXT("montage references sequence")),
             Montage->GetFirstAnimReference() == Sequence);
    TestEqual(Context(Spec.ClipId, TEXT("one slot track")),
              Montage->SlotAnimTracks.Num(), 1);
    if (Montage->SlotAnimTracks.Num() == 1) {
      const FSlotAnimationTrack &SlotTrack = Montage->SlotAnimTracks[0];
      TestTrue(Context(Spec.ClipId, TEXT("default slot")),
               SlotTrack.SlotName == FAnimSlotGroup::DefaultSlotName);
      TestEqual(Context(Spec.ClipId, TEXT("one animation segment")),
                SlotTrack.AnimTrack.AnimSegments.Num(), 1);
      if (SlotTrack.AnimTrack.AnimSegments.Num() == 1) {
        const FAnimSegment &Segment = SlotTrack.AnimTrack.AnimSegments[0];
        TestTrue(
            Context(Spec.ClipId, TEXT("segment references exact sequence")),
            Segment.GetAnimReference() == Sequence);
        TestEqual(Context(Spec.ClipId, TEXT("one montage iteration")),
                  Segment.LoopingCount, 1);
        TestTrue(Context(Spec.ClipId, TEXT("segment starts at zero")),
                 FMath::IsNearlyZero(Segment.StartPos));
        TestTrue(Context(Spec.ClipId, TEXT("sequence range starts at zero")),
                 FMath::IsNearlyZero(Segment.AnimStartTime));
        TestTrue(
            Context(Spec.ClipId, TEXT("sequence range reaches full length")),
            FMath::IsNearlyEqual(Segment.AnimEndTime,
                                 static_cast<float>(Sequence->GetPlayLength()),
                                 TimeToleranceSeconds));
        TestTrue(Context(Spec.ClipId, TEXT("segment play rate is one")),
                 FMath::IsNearlyEqual(Segment.AnimPlayRate, 1.0F));
      }
    }

    TestEqual(Context(Spec.ClipId, TEXT("typed notify count")),
              Montage->Notifies.Num(), Spec.NotifyCount);
    TSet<FString> ExpectedClipNotifies;
    for (int32 Index = 0; Index < Spec.NotifyCount; ++Index) {
      const FNotifySpec &NotifySpec = Spec.Notifies[Index];
      ExpectedClipNotifies.Add(
          FString::Printf(TEXT("%s@%d"), NotifySpec.Signal, NotifySpec.Frame));
    }
    TSet<FString> ObservedClipNotifies;
    for (const FAnimNotifyEvent &NotifyEvent : Montage->Notifies) {
      const UVistaAnimationSignalNotify *Notify =
          Cast<UVistaAnimationSignalNotify>(NotifyEvent.Notify);
      if (!IsValid(Notify)) {
        AddError(
            Context(Spec.ClipId, TEXT("notify is not typed VISTA signal")));
        continue;
      }
      ObservedUniqueSignals.Add(Notify->SignalName);
      ++ObservedNotifyOccurrences;
      const float FrameValue = NotifyEvent.GetTime() * FramesPerSecond;
      const int32 NearestFrame = FMath::RoundToInt(FrameValue);
      TestTrue(Context(Spec.ClipId,
                       *FString::Printf(TEXT("notify %s lands on a frame"),
                                        *Notify->SignalName.ToString())),
               FMath::IsNearlyEqual(FrameValue,
                                    static_cast<float>(NearestFrame),
                                    TimeToleranceSeconds * FramesPerSecond));
      ObservedClipNotifies.Add(FString::Printf(
          TEXT("%s@%d"), *Notify->SignalName.ToString(), NearestFrame));
    }
    for (const FString &ExpectedNotify : ExpectedClipNotifies) {
      TestTrue(Context(Spec.ClipId,
                       *FString::Printf(TEXT("typed notify present: %s"),
                                        *ExpectedNotify)),
               ObservedClipNotifies.Contains(ExpectedNotify));
    }
    TestEqual(Context(Spec.ClipId, TEXT("notify identities are exact")),
              ObservedClipNotifies.Num(), ExpectedClipNotifies.Num());
  }

  TestEqual(TEXT("all per-clip typed notify occurrences verified"),
            ObservedNotifyOccurrences, ExpectedNotifyOccurrenceCount);
  TestEqual(TEXT("closed typed signal vocabulary has 14 names"),
            ObservedUniqueSignals.Num(), ExpectedUniqueSignalCount);
  return !HasAnyErrors();
}

#endif // WITH_DEV_AUTOMATION_TESTS
