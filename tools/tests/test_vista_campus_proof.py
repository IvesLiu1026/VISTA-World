import unittest
from runtime.vista_campus.proof import verify_motion_trace

def frames():
    return [dict(clock_s=t,vehicles=[dict(id='car',position_cm=[t*300,0,67])]) for t in [0,.1,.2,.3,.4]]

class CampusMotionEvidenceTests(unittest.TestCase):
    def test_accepts_finite_continuous_travel(self):
        self.assertAlmostEqual(verify_motion_trace(frames(),'car')['displacement_cm'],120)

    def test_rejects_motion_at_frozen_clock(self):
        data=frames();data[2]['clock_s']=data[1]['clock_s']
        with self.assertRaisesRegex(ValueError,'stale'):verify_motion_trace(data,'car')

    def test_rejects_teleport_between_valid_endpoints(self):
        data=frames();data[2]['vehicles'][0]['position_cm'][1]=500
        with self.assertRaisesRegex(ValueError,'Discontinuity'):verify_motion_trace(data,'car')

    def test_rejects_reversed_time(self):
        data=frames();data[2]['clock_s']=-1
        with self.assertRaisesRegex(ValueError,'Nonmonotonic'):verify_motion_trace(data,'car')

    def test_rejects_duplicate_vehicle_identity(self):
        data=frames();data[2]['vehicles']*=2
        with self.assertRaisesRegex(ValueError,'Ambiguous'):verify_motion_trace(data,'car')

    def test_rejects_stationary_or_nan_evidence(self):
        data=frames()
        for s in data:s['vehicles'][0]['position_cm']=[0,0,67]
        with self.assertRaisesRegex(ValueError,'No demonstrated'):verify_motion_trace(data,'car')
        data=frames();data[2]['vehicles'][0]['position_cm'][0]=float('nan')
        with self.assertRaisesRegex(ValueError,'Invalid coordinates'):verify_motion_trace(data,'car')
