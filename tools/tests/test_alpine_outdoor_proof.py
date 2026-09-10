"""Synthetic verifier fixtures; these are not native demonstration evidence."""
import copy
import math
import unittest
from runtime.vista_alpine_r3.verify_outdoor import check


def trajectory():
    frames=[];position=[439.5,-1020.,83.]
    joints={'upperarm_l':[18,0,140],'lowerarm_l':[21,0,116],'hand_l':[21,0,94],
            'upperarm_r':[-18,0,140],'lowerarm_r':[-21,0,116],'hand_r':[-21,0,94],
            'thigh_l':[10,0,85],'calf_l':[10,0,45],'foot_l':[10,0,6],
            'thigh_r':[-10,0,85],'calf_r':[-10,0,45],'foot_r':[-10,0,6]}
    for stage,count in enumerate([60,150,210,60,60,60,60,60,60,60]):
        for i in range(count):
            falling=False;v=[0,0,0]
            if stage==1:position[1]-=125/30;v[1]=-125
            if stage==2:
                position[0]-=350/30;v[0]=-350
                t=(i-54)/30
                if 0<t<720/980:
                    falling=True;position[2]=83+360*t-490*t*t;v[2]=360-980*t
                else:position[2]=83
            frames.append({'stage':stage,'time_s':len(frames)/30,'position_cm':list(position),'velocity_cm_s':v,
                           'falling':falling,'ground_ik':not falling,'door_alpha':1.,'ready_hands':0.,'joints':copy.deepcopy(joints)})
    return {'frames':frames,'captures':[{'stage':i} for i in range(10)]}


class OutdoorProofTests(unittest.TestCase):
    def test_continuous_physical_trajectory(self):self.assertEqual(check(trajectory())['errors'],[])

    def test_action_flags_cannot_replace_a_jump(self):
        data=trajectory();data['jump_requested']=True
        for row in data['frames']:row['falling']=False;row['velocity_cm_s'][2]=0
        self.assertIn('No complete physical jump arc',check(data)['errors'])

    def test_airborne_ground_lock_is_rejected(self):
        data=trajectory()
        for row in data['frames']:row['ground_ik']=True
        self.assertIn('Ground IK remained enabled in the air',check(data)['errors'])

    def test_teleport_does_not_prove_connected_navigation(self):
        data=trajectory();data['frames'][80]['position_cm'][0]+=200
        self.assertIn('Trajectory contains a teleport or excessive movement step',check(data)['errors'])

    def test_closed_portal_is_rejected(self):
        data=trajectory()
        for row in data['frames']:row['door_alpha']=0
        self.assertIn('Door was not open during crossing',check(data)['errors'])

    def test_bone_stretch_is_rejected(self):
        data=trajectory();data['frames'][220]['joints']['hand_l'][2]-=5
        self.assertIn('Animation stretched a limb',check(data)['errors'])

if __name__=='__main__':unittest.main()
