"""Compile and exercise the same conservative transport used by Unreal."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]


class LiquidTransportTests(unittest.TestCase):
    def test_source_stop_flight_overflow_and_conservation(self):
        source=r'''
#include "VistaLiquidLedger.h"
#include <cassert>
#include <limits>
using namespace VistaLiquid;
int main() {
    Ledger l;
    // Stopping the source preserves a real transit interval and all mass.
    for(int i=0;i<30;i++){l.Step(1./60);l.Emit(60,1./60,.25,true);}
    const double before=l.Receiver;
    assert(l.Airborne()>0 && l.Source<600 && before>0);
    const double stopped=l.Source;
    for(int i=0;i<30;i++){l.Step(1./60);l.Emit(0,1./60,.25,true);}
    assert(l.Source==stopped && l.Receiver>before && l.Airborne()==0);
    assert(std::abs(l.Residual())<1e-8);
    // A full receiver routes overflow to a measured spill, not lost volume.
    l.Emit(1000,1,.01,true);l.Step(.1);
    assert(l.Source==0 && l.Receiver==260 && l.Spill==340);
    assert(std::abs(l.Residual())<1e-8);
    // A displaced receiver cannot receive a parcel that missed its mouth.
    Ledger miss;miss.Emit(100,.2,.2,false);miss.Step(.3);
    assert(miss.Receiver==0 && miss.Spill==20 && miss.Source==580);
    // Tap input and drainage are both present in the balance equation.
    Ledger tap;tap.Source=tap.Initial=0;
    for(int i=0;i<100;i++){tap.Step(.01,true);tap.Emit(90,.01,.3,false,true);}
    assert(tap.Supplied>89.9 && tap.Airborne()>0 && tap.Drain>0);
    for(int i=0;i<100;i++)tap.Step(.01,true);
    assert(tap.Airborne()==0 && std::abs(tap.Drain-tap.Supplied)<1e-8);
    assert(std::abs(tap.Residual())<1e-8);
    // Non-finite and negative requests cannot poison state.
    Ledger invalid;invalid.Emit(-1,1,1,true);invalid.Emit(1,-1,1,true);
    invalid.Emit(std::numeric_limits<double>::infinity(),1,1,true);
    invalid.Step(std::numeric_limits<double>::quiet_NaN());
    assert(invalid.Source==600 && invalid.Airborne()==0 && invalid.Residual()==0);
}
'''
        inc=ROOT/'unreal_plugins/VistaPhotorealReview/Source/VistaPhotorealReview/Public'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'check.cpp').write_text(source)
            subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(inc),str(p/'check.cpp'),'-o',str(p/'check')],check=True,capture_output=True)
            subprocess.run([str(p/'check')],check=True,capture_output=True)


if __name__=='__main__':unittest.main()
