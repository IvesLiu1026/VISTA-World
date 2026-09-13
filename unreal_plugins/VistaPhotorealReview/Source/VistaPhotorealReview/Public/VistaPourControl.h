#pragma once
#include <algorithm>
#include <cmath>
#include "VistaLiquidLedger.h"

// Action timing and volume configuration, shared by native runtime and tests.
// This is a scripted human motor response, not a fluid solver or learned policy.
namespace VistaPour
{
enum class Phase { Idle, Pouring, Uprighting, Withdrawing };
struct Control
{
    Phase State=Phase::Idle;
    double Elapsed=0, ReturnElapsed=0;
    bool Interrupted=false;
    static constexpr double PourDuration=4.5, UprightDuration=.7, WithdrawDuration=.65;
    bool Start()
    {
        if (State!=Phase::Idle) return false;
        State=Phase::Pouring;Elapsed=ReturnElapsed=0;Interrupted=false;return true;
    }
    bool Return(bool UserStop)
    {
        if (State!=Phase::Pouring) return false;
        State=Phase::Uprighting;ReturnElapsed=0;Interrupted=UserStop;return true;
    }
    void Step(double Dt)
    {
        if (!std::isfinite(Dt) || Dt<=0 || State==Phase::Idle) return;
        Elapsed+=Dt;
        if (State!=Phase::Pouring)
        {
            ReturnElapsed+=Dt;
            if (ReturnElapsed>=UprightDuration) State=Phase::Withdrawing;
        }
    }
    bool AutoReturnDue() const {return State==Phase::Pouring && Elapsed>=PourDuration;}
    bool Finished() const {return State==Phase::Withdrawing && ReturnElapsed>=UprightDuration+WithdrawDuration+.15;}
    double Rate(double ActualTiltDegrees) const
    {
        if (!std::isfinite(ActualTiltDegrees) || State==Phase::Idle || Elapsed<=1.1) return 0;
        // Residual outflow continues while the measured vessel is still tilted.
        return std::clamp((ActualTiltDegrees-48.)/22.,0.,1.)*65.;
    }
};
inline bool Initialize(VistaLiquid::Ledger& Out,double Source,double Receiver)
{
    // Bounds follow this scene's authored reservoirs, in millilitres.
    if (!std::isfinite(Source) || !std::isfinite(Receiver) || Source<0 || Source>600 || Receiver<0 || Receiver>260) return false;
    VistaLiquid::Ledger Next;Next.Source=Source;Next.Receiver=Receiver;Next.Initial=Source+Receiver;
    Out=Next;return true;
}
}
