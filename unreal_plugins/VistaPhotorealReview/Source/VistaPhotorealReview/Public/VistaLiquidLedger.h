#pragma once
#include <algorithm>
#include <cmath>
#include <vector>

// Reservoir transport is explicit and conservative. Niagara solves the visible
// flow independently; its particle estimate is never used as a mass reading.
namespace VistaLiquid
{
struct Parcel { double Ml=0, Remaining=0; bool Receiver=false; };
struct Ledger
{
    double Source=600, Receiver=0, Spill=0, Drain=0, Supplied=0;
    double Initial=600, Capacity=260, Transferred=0;
    std::vector<Parcel> Flight;
    double Airborne() const {double V=0;for (const auto& P:Flight) V+=P.Ml;return V;}
    double Residual() const {return Source+Receiver+Spill+Drain+Airborne()-Initial-Supplied;}
    double Emit(double Rate,double Dt,double FlightSeconds,bool HitReceiver,bool Tap=false)
    {
        if (!std::isfinite(Rate) || !std::isfinite(Dt) || !std::isfinite(FlightSeconds) ||
            Rate<0 || Dt<=0 || FlightSeconds<0) return 0;
        const double Amount=Tap?Rate*Dt:std::min(Source,Rate*Dt);
        if (Tap) Supplied+=Amount;else Source-=Amount;
        if (Amount>0) Flight.push_back({Amount,FlightSeconds,HitReceiver});
        return Amount;
    }
    void Step(double Dt,bool TapDrain=false)
    {
        if (!std::isfinite(Dt) || Dt<=0) return;
        for (auto It=Flight.begin();It!=Flight.end();)
        {
            It->Remaining-=Dt;
            if (It->Remaining>0) {++It;continue;}
            if (TapDrain) Drain+=It->Ml;
            else if (It->Receiver)
            {
                const double Accepted=std::min(It->Ml,std::max(0.,Capacity-Receiver));
                Receiver+=Accepted;Transferred+=Accepted;Spill+=It->Ml-Accepted;
            }
            else Spill+=It->Ml;
            It=Flight.erase(It);
        }
    }
};
}
