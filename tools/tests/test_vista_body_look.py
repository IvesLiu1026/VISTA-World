"""Compile and exercise the joint-angle update used by the native character."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

class BodyLookContinuity(unittest.TestCase):
    def test_wrap_reversal_pitch_and_frame_rates(self):
        code=r'''
#include "VistaBodyLook.h"
#include <cassert>
#include <cmath>
int main() {
    for (float dt : {1.f/120,1.f/60,1.f/30,.08f}) {
        VistaMotion::BodyLook look;
        for (int i=0;i<400;++i) {
            float previous=look.Yaw, pitch=look.Pitch;
            // Cross +180/-180 repeatedly, then reverse; input can rotate
            // several turns without forcing an anatomical joint to do so.
            float target=i<180?170.f+i*9.f:179.f-(i-180)*18.f;
            look.Update(target,i%2?280.f:65.f,dt,true);
            assert(std::abs(look.Yaw)<=65.001f);
            assert(look.Pitch>=-50.001f && look.Pitch<=40.001f);
            assert(std::abs(look.Yaw-previous)<=180.f*dt+.001f);
            assert(std::abs(look.Pitch-pitch)<=140.f*dt+.001f);
        }
        for (int i=0;i<200;++i) look.Update(180,90,dt,false);
        assert(std::abs(look.Yaw)<.001f && std::abs(look.Pitch)<.001f);
        look.Update(90,-80,0,true);
        assert(look.Yaw==0 && look.Pitch==0);
        look.Update(90,-80,2,true); // a stall cannot create a one-frame snap
        assert(look.Yaw<=18.001f && look.Pitch>=-14.001f);
    }
    assert(std::abs(VistaMotion::BodyLook::Delta(179,-179)-2.f)<.001f);
    assert(std::abs(VistaMotion::BodyLook::Delta(-179,179)+2.f)<.001f);
}
'''
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);(d/'check.cpp').write_text(code)
            inc=ROOT/'unreal_plugins/VistaPhotorealReview/Source/VistaPhotorealReview/Public'
            subprocess.run(['c++','-std=c++17','-I'+str(inc),str(d/'check.cpp'),'-o',str(d/'check')],check=True)
            subprocess.run([str(d/'check')],check=True)

if __name__=='__main__':unittest.main()
