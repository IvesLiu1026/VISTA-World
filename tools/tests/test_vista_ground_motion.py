"""Run the production C++ controller at several sample rates, without UE mocks."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class GroundMotionTests(unittest.TestCase):
    def test_support_turns_arrival_and_heading(self):
        source = r'''
#include "VistaGroundMotion.h"
#include <cassert>
#include <iostream>
using namespace VistaMotion;
int main(){
  assert(ArrivalSpeed(0,160,0)==0);
  assert(ArrivalSpeed(100,160,100)<1e-10);
  assert(ArrivalSpeed(100,160,60)<ArrivalSpeed(100,160,30));
  for(double d=0;d<100;d+=.5) {
    double v=ArrivalSpeed(d,160,0);
    assert(v*v<=2*240*d+1e-8); // Enough room to brake before the goal.
    assert(v<=ArrivalSpeed(d+.5,160,0));
  }
  assert(std::abs(AngleDelta(179,-179)-2)<1e-9);
  for(int fps:{15,30,60,120}) for(int sign:{-1,1}) {
    double dt=1.0/fps,yaw=170,rate=0;
    TurnSteps feet;GroundPoint goals[2];int lifting=0;
    for(int frame=0;frame<fps*6;++frame){
      double previousYaw=yaw;
      if(frame<fps*3)yaw=AdvanceHeading(yaw,170+sign*179,dt,100,rate);
      double a=yaw*3.141592653589793/180;
      for(int s=0;s<2;++s){double side=s?12:-12;goals[s]={-std::sin(a)*side,std::cos(a)*side,6.22};}
      GroundPoint old[2]={feet.Feet[0],feet.Feet[1]};int previousSwing=feet.Swing;
      feet.Update(dt,goals,yaw,false);
      assert(std::abs(AngleDelta(previousYaw,yaw))<=100*dt+1e-8);
      int airborne=0;
      for(int s=0;s<2;++s){
        assert(feet.Feet[s].Z>=6.22-1e-8 && feet.Feet[s].Z<=11.22+1e-8);
        if(feet.Feet[s].Z>6.23)++airborne;
        if(frame && s!=previousSwing && s!=feet.Swing)
          assert(GroundDistance(old[s],feet.Feet[s])<1e-9); // Support stays still.
      }
      assert(airborne<=1);lifting+=airborne;
    }
    assert(std::abs(AngleDelta(yaw,170+sign*179))<.001);
    assert(feet.Count>=4 && lifting>fps/2 && feet.Swing==-1);
    for(int s=0;s<2;++s)assert(GroundDistance(feet.Feet[s],goals[s])<=5.01);
    // Teleport/reset does not drag old anchors across rooms.
    goals[0]={2000,1000,80};goals[1]={2024,1000,80};
    feet.Update(dt,goals,90,true);
    assert(feet.Swing==-1 && GroundDistance(feet.Feet[0],goals[0])==0);
  }
  std::cout<<"ground motion invariants passed\n";
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp/'check.cpp').write_text(source)
            include = ROOT/'unreal_plugins/VistaPhotorealReview/Source/VistaPhotorealReview/Public'
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I'+str(include), str(tmp/'check.cpp'), '-o', str(tmp/'check')], check=True)
            result = subprocess.check_output([str(tmp/'check')], text=True)
            self.assertIn('invariants passed', result)


if __name__ == '__main__':
    unittest.main()
