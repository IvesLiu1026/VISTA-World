"""Exercise the actual motor controller and liquid ledger without Unreal."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PourControlTests(unittest.TestCase):
    def test_interruption_is_idempotent_and_preserves_consequences(self):
        source = r'''
#include "VistaPourControl.h"
#include <cassert>
#include <limits>
using namespace VistaPour;
int main() {
    Control c;
    assert(!c.Return(true)); assert(c.Start()); assert(!c.Start());
    c.Step(1.5); assert(c.Rate(78)==65);
    assert(c.Return(true)); const double at=c.Elapsed;
    c.Step(.2); assert(!c.Return(true) && !c.Return(false));
    assert(c.Elapsed>at && c.ReturnElapsed==.2 && c.Interrupted);
    // Stopping is a motor response: residual tilted flow still exists.
    assert(c.Rate(78)==65 && c.Rate(48)==0 && c.Rate(0)==0);
    c.Step(.5); assert(c.State==Phase::Withdrawing);
    c.Step(1); assert(c.Finished());
    c.State=Phase::Idle; assert(c.Rate(78)==0 && c.Start());
    c.Step(4.5); assert(c.AutoReturnDue() && c.Return(false) && !c.Interrupted);
    const auto previous=c.Elapsed;
    c.Step(-1); c.Step(std::numeric_limits<double>::infinity());
    assert(c.Elapsed==previous);
    assert(c.Rate(std::numeric_limits<double>::quiet_NaN())==0);

    VistaLiquid::Ledger l;
    assert(Initialize(l,600,160) && l.Initial==760 && l.Residual()==0);
    assert(!Initialize(l,-1,0) && !Initialize(l,601,0) && !Initialize(l,600,261));
    assert(!Initialize(l,600,std::numeric_limits<double>::quiet_NaN()));
    assert(l.Initial==760 && l.Receiver==160); // invalid configuration is atomic
    l.Emit(65,2,.2,true); // enough already released water to overflow
    const auto source=l.Source, air=l.Airborne();
    Control stop; stop.Start(); stop.Step(2); stop.Return(true);
    assert(l.Source==source && l.Airborne()==air && l.Spill==0);
    l.Step(.3); assert(l.Receiver==260 && l.Spill==30 && l.Residual()==0);
    stop.Step(2); assert(l.Spill==30); // completing return does not undo spill
    assert(Initialize(l,0,260) && l.Source==0 && l.Residual()==0);
    assert(l.Emit(65,1,.2,true)==0 && l.Airborne()==0);
}
'''
        inc = ROOT / 'unreal_plugins/VistaPhotorealReview/Source/VistaPhotorealReview/Public'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'check.cpp').write_text(source)
            subprocess.run(['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-I', str(inc), str(path / 'check.cpp'), '-o', str(path / 'check')],
                           check=True, capture_output=True)
            subprocess.run([str(path / 'check')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
