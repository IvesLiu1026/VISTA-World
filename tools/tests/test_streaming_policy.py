import unittest
from runtime.vista_streaming.policy import Policy

def observation(t,cues=(),call=False,text=''):
    x={'schema':'vista.streaming-observation/v1','source':'engine_visible_metadata_not_vlm','wearer_role':'human_needing_assistance','view':'human_ego','clock_s':t,'room':'客廳','objects':[],'focused':'','cues':list(cues),'human_activity':'phone_at_ear' if call else 'unspecified'}
    if text:x['utterance']={'speaker_role':'human','source':'authored_transcript','text':text}
    return x

class StreamingPolicyTests(unittest.TestCase):
    def test_normal_life_is_not_a_hazard(self):
        p=Policy()
        self.assertEqual(p.step(observation(1,['visible_stove_flame','visible_running_bath_tap']))['action'],'wait')
    def test_call_deferral_urgent_preemption_and_resume(self):
        p=Policy();d=p.step(observation(1,['visible_stove_flame'],text='我要出門'))
        self.assertEqual(d['notice'],'stove')
        self.assertEqual(p.step(observation(3,['visible_keys'],True,'幫我找鑰匙'))['reason'],'defer_nonurgent_during_call')
        d=p.step(observation(4,['visible_water_near_rim'],True))
        self.assertEqual(d['notice'],'water');self.assertEqual(p.tasks['stove'].status,'suspended')
        self.assertEqual(p.step(observation(5,[],True))['action'],'wait')
        self.assertEqual(p.step(observation(10,['visible_bath_tap_off'],True))['reason'],'defer_nonurgent_during_call')
        self.assertEqual(p.step(observation(40))['notice'],'stove')
        self.assertEqual(p.step(observation(42,['visible_stove_off']))['notice'],'keys')
    def test_out_of_view_does_not_resolve(self):
        p=Policy();p.step(observation(1,['visible_water_near_rim']));p.step(observation(2))
        self.assertNotEqual(p.tasks['water'].status,'resolved')
    def test_resolved_need_stays_quiet_and_can_recur(self):
        p=Policy();p.step(observation(1,['visible_water_near_rim']));p.step(observation(2,['visible_bath_tap_off']))
        self.assertEqual(p.step(observation(60))['action'],'wait')
        self.assertEqual(p.step(observation(61,['visible_water_near_rim']))['notice'],'water')
    def test_review_state_and_future_rejected(self):
        p=Policy()
        for k in ['event_id','future','success_conditions','priority','seed']:
            with self.assertRaises(ValueError):p.step(dict(observation(1),**{k:'oracle'}))
    def test_backwards_clock_rejected(self):
        p=Policy();p.step(observation(5))
        with self.assertRaises(ValueError):p.step(observation(3))
    def test_review_camera_not_used(self):
        p=Policy();o=observation(1,['visible_water_near_rim']);o['view']='third_person_review'
        self.assertEqual(p.step(o)['tasks'],[])

if __name__=='__main__':unittest.main()
