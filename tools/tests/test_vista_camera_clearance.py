"""Check that the native camera guard encloses every near-plane corner."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class CameraClearance(unittest.TestCase):
    def test_projection_corners_landscape_portrait_and_wide_fov(self):
        inc = Path(__file__).resolve().parents[2] / 'unreal_plugins/VistaPhotorealReview/Source/VistaPhotorealReview/Public'
        code = r'''
#include "VistaCameraClearance.h"
#include <cassert>
int main() {
  for (float aspect : {.5625f, 1.f, 1.7777778f, 2.4f})
    for (float fov : {60.f, 78.f, 100.f, 120.f}) {
      const float r=VistaCamera::Clearance(3.f,fov,aspect);
      const float w=3.f*std::tan(fov*.00872664626f),h=w/aspect;
      assert(r*r > 9.f+w*w+h*h);
      assert(std::isfinite(r) && r>=6.f);
    }
  assert(std::isfinite(VistaCamera::Clearance(3.f,78.f,0)));
}
'''
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d/'test.cpp').write_text(code)
            subprocess.run(['c++', '-std=c++17', '-I'+str(inc), str(d/'test.cpp'), '-o', str(d/'test')], check=True)
            subprocess.run([str(d/'test')], check=True)
