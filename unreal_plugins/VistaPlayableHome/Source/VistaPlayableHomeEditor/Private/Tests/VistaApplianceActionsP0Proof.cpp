#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/AutomationTest.h"
#include "VistaStatefulApplianceActor.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FVistaApplianceActionsP0TransitionProof,
    "VISTA.PlayableHome.ApplianceActionsP0.TransitionContract",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FVistaApplianceActionsP0TransitionProof::RunTest(
    const FString& Parameters)
{
    static_cast<void>(Parameters);
    const FVistaApplianceActivityProfile ActivityProfile;
    const FVistaAppliancePressProfile StartProfile;
    FVistaApplianceState After;
    bool bMutated = false;
    FName Code;

    FVistaApplianceState Off;
    Off.bPowered = false;
    Off.bActive = false;
    Off.Status = TEXT("off");
    TestFalse(
        TEXT("unpowered turn_on fails closed"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Off,
            EVistaAffordance::TurnOn,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("unpowered turn_on has zero mutation"), bMutated);
    TestTrue(TEXT("unpowered turn_on preserves state"), After == Off);
    TestEqual(
        TEXT("unpowered turn_on has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_POWER_REQUIRED")));

    FVistaApplianceState PoweredInactive;
    PoweredInactive.bPowered = true;
    PoweredInactive.bActive = false;
    PoweredInactive.Status = TEXT("idle");
    TestTrue(
        TEXT("turn_on succeeds with external power"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            PoweredInactive,
            EVistaAffordance::TurnOn,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestTrue(TEXT("turn_on mutates once"), bMutated);
    TestTrue(TEXT("turn_on preserves power"), After.bPowered);
    TestTrue(TEXT("turn_on starts activity"), After.bActive);
    TestEqual(
        TEXT("turn_on enters target active status"),
        After.Status,
        FName(TEXT("running")));

    const FVistaApplianceState Running = After;
    TestTrue(
        TEXT("repeated turn_on succeeds"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Running,
            EVistaAffordance::TurnOn,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("repeated turn_on is idempotent"), bMutated);
    TestTrue(TEXT("repeated turn_on preserves exact state"), After == Running);
    TestEqual(
        TEXT("repeated turn_on has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_ALREADY_ACTIVE")));

    TestTrue(
        TEXT("toggle succeeds with power"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            PoweredInactive,
            EVistaAffordance::Toggle,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestTrue(TEXT("toggle mutates active"), After.bActive);
    TestTrue(TEXT("toggle preserves power"), After.bPowered);
    TestEqual(TEXT("toggle preserves status"), After.Status, FName(TEXT("idle")));

    FVistaApplianceState Loaded = PoweredInactive;
    Loaded.Status = TEXT("loaded");
    TestTrue(
        TEXT("washer start press succeeds"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Loaded,
            EVistaAffordance::Press,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestTrue(TEXT("washer start becomes active"), After.bActive);
    TestTrue(TEXT("washer start preserves power"), After.bPowered);
    TestEqual(TEXT("washer start becomes running"), After.Status, FName(TEXT("running")));

    const FVistaApplianceState PressRunning = After;
    TestTrue(
        TEXT("repeated washer start succeeds"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            PressRunning,
            EVistaAffordance::Press,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("repeated washer start is idempotent"), bMutated);
    TestTrue(
        TEXT("repeated washer start preserves exact state"),
        After == PressRunning);
    TestEqual(
        TEXT("repeated press has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_PRESS_ALREADY_APPLIED")));

    TestFalse(
        TEXT("unpowered toggle fails closed"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Off,
            EVistaAffordance::Toggle,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("failed toggle has zero mutation"), bMutated);
    TestTrue(TEXT("failed toggle preserves state"), After == Off);
    TestEqual(
        TEXT("unpowered toggle has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_POWER_REQUIRED")));
    TestFalse(
        TEXT("unpowered washer press fails closed"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Off,
            EVistaAffordance::Press,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("failed press has zero mutation"), bMutated);
    TestTrue(TEXT("failed press preserves state"), After == Off);
    TestEqual(
        TEXT("unpowered washer press has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_POWER_REQUIRED")));

    TestTrue(
        TEXT("turn_off succeeds from running"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Running,
            EVistaAffordance::TurnOff,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestTrue(TEXT("turn_off preserves power"), After.bPowered);
    TestFalse(TEXT("turn_off stops activity"), After.bActive);
    TestEqual(TEXT("turn_off enters idle"), After.Status, FName(TEXT("idle")));

    const FVistaApplianceState PoweredOff = After;
    TestTrue(
        TEXT("repeated turn_off succeeds"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            PoweredOff,
            EVistaAffordance::TurnOff,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("repeated turn_off is idempotent"), bMutated);
    TestTrue(
        TEXT("repeated turn_off preserves exact state"),
        After == PoweredOff);
    TestEqual(
        TEXT("repeated turn_off has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_ALREADY_INACTIVE")));

    TestTrue(
        TEXT("unpowered inactive turn_off is idempotent"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Off,
            EVistaAffordance::TurnOff,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("unpowered inactive turn_off has zero mutation"), bMutated);
    TestTrue(TEXT("unpowered inactive turn_off preserves state"), After == Off);

    FVistaApplianceState Inconsistent = Off;
    Inconsistent.bActive = true;
    TestFalse(
        TEXT("active without power fails closed"),
        AVistaStatefulApplianceActor::PlanInteractionTransition(
            Inconsistent,
            EVistaAffordance::TurnOff,
            ActivityProfile,
            StartProfile,
            After,
            bMutated,
            Code));
    TestFalse(TEXT("inconsistent state has zero mutation"), bMutated);
    TestEqual(
        TEXT("inconsistent state has explicit code"),
        Code,
        FName(TEXT("APPLIANCE_STATE_INVALID")));
    return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
