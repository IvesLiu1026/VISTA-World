"""Exercise the actual C++ blend used by the native reach/pose code."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MotionCurveInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp/'sample.cpp'
            source.write_text('#include "VistaMotionCurves.h"\n#include <iostream>\n#include <iomanip>\n'
                'int main(){std::cout<<std::setprecision(9);'
                'for(int i=-100;i<=1100;i++) std::cout<<VistaMotion::Ease(i/1000.f)<<"\\n";}\n')
            include = ROOT/'unreal_plugins/VistaPhotorealReview/Source/VistaPhotorealReview/Public'
            subprocess.run(['c++', '-std=c++17', '-I'+str(include), str(source), '-o', str(tmp/'sample')], check=True)
            cls.samples = [float(v) for v in subprocess.check_output([str(tmp/'sample')], text=True).splitlines()]

    def value(self, index):
        return self.samples[index+100]

    def test_clamped_endpoints_and_no_meaningful_reverse_motion(self):
        self.assertTrue(all(v == 0 for v in self.samples[:101]))
        self.assertTrue(all(v == 1 for v in self.samples[1100:]))
        self.assertTrue(all(-1e-6 <= v <= 1+1e-6 for v in self.samples))
        self.assertTrue(all(b-a >= -1e-6 for a, b in zip(self.samples, self.samples[1:])))
        self.assertAlmostEqual(self.value(500), .5, places=6)

    def test_quiet_start_stop_and_symmetric_acceleration(self):
        # Finite 10 ms neighborhoods; tolerances include float32 arithmetic.
        h = .01
        start_velocity = (self.value(10)-self.value(0))/h
        stop_velocity = (self.value(1000)-self.value(990))/h
        self.assertLess(abs(start_velocity), .0011)
        self.assertLess(abs(stop_velocity), .0011)
        for i in range(0, 1001, 10):
            self.assertAlmostEqual(self.value(i)+self.value(1000-i), 1, delta=1e-6)


if __name__ == '__main__':
    unittest.main()
