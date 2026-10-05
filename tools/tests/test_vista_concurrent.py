import copy
import unittest
from runtime.vista_concurrent.policy import Planner,validate
from runtime.vista_concurrent.scenario import compile_prompt,DEFAULT_PROMPT

def observation(t=0,cues=(),call=False,text='',speaker='human'):
    o={'schema':'vista.streaming-observation/v1','source':'engine_visible_metadata_not_vlm',
       'wearer_role':'human_needing_assistance','view':'human_ego','clock_s':t,'room':'Kitchen',
       'focused':'','objects':[],'cues':list(cues),'human_activity':'phone_at_ear' if call else 'unspecified'}
    if text:o['utterance']={'source':'authored_transcript','speaker_role':speaker,'text':text}
    return o

class ConcurrentPolicyTests(unittest.TestCase):
    def test_closed_boundary(self):
        for field,value in [('events',[{'answer':'water'}]),('future_schedule',[]),('gold','alarm')]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate({**observation(),field:value})
        bad=observation();bad['objects']=[{'hidden_state':'on'}]
        with self.assertRaises(ValueError):validate(bad)
        bad=observation();bad['view']='third_person_review'
        with self.assertRaises(ValueError):validate(bad)
    def test_monotonic_and_finite_clock(self):
        p=Planner();p.step(observation(3))
        for value in (2,float('nan'),float('inf')):
            with self.assertRaises(ValueError):p.step(observation(value))
    def test_phone_alone_is_not_need(self):
        p=Planner()
        for i in range(6):self.assertIsNone(p.step(observation(i,call=True))['speech'])
        self.assertFalse(p.needs)
    def test_other_speaker_cannot_create_user_intent(self):
        p=Planner();p.step(observation(1,['visible_stove_on_control'],text="I'm heading out. Find my keys.",speaker='phone'))
        self.assertFalse(p.leaving);self.assertFalse(p.needs)
    def test_offscreen_is_not_resolved(self):
        p=Planner();d=p.step(observation(1,['visible_water_near_rim']))
        self.assertEqual(d['speech'],'assistant_water')
        for i in (2,10,100):
            d=p.step(observation(i));self.assertIsNone(d['speech'])
            self.assertNotEqual(p.needs['water'].status,'resolved')
    def test_preempt_verify_resume(self):
        p=Planner();p.step(observation(1,['visible_stove_on_control'],text="I'm heading out; help me find my keys."))
        d=p.step(observation(2,['visible_water_near_rim'],True))
        self.assertEqual(d['reason'],'urgent_interrupt')
        self.assertEqual(p.needs['stove'].status,'suspended')
        d=p.step(observation(3,['visible_bath_tap_off'],True));self.assertIsNone(d['speech'])
        d=p.step(observation(4));self.assertEqual(d['speech'],'assistant_resume')
        for i in range(5,30):self.assertIsNone(p.step(observation(i))['speech'])
        self.assertEqual(p.step(observation(30,['visible_stove_off']))['speech'],'assistant_stove_off')
        self.assertEqual(p.step(observation(31,['visible_keys']))['speech'],'assistant_keys')
    def test_normal_and_resolved_control(self):
        p=Planner()
        d=p.step(observation(1,['visible_stove_off','visible_bath_tap_off'],text="I'm heading out."))
        self.assertIsNone(d['speech']);self.assertFalse(p.needs)
    def test_nonurgent_waits_during_phone(self):
        p=Planner();d=p.step(observation(1,['visible_keys'],True,"Where are my keys?"))
        self.assertEqual(d['reason'],'defer_nonurgent_during_call')
        self.assertEqual(p.step(observation(2,['visible_keys']))['speech'],'assistant_keys')
        self.assertIsNone(p.step(observation(3,['visible_keys']))['speech'])
    def test_observation_not_mutated(self):
        o=observation(1,['visible_water_near_rim']);before=copy.deepcopy(o);Planner().step(o);self.assertEqual(o,before)

class ScenarioTests(unittest.TestCase):
    def test_catalog_compilation_and_provenance(self):
        d=compile_prompt(DEFAULT_PROMPT)
        self.assertEqual(len(d['events']),3);self.assertFalse(d['narrator'])
        self.assertEqual(d['episodes'],['first','third'])
        self.assertIn('New authored concurrency',d['provenance']['composition'])
    def test_reject_missing_or_unimplemented_capabilities(self):
        for prompt in ('Build a city with a car and a dog',DEFAULT_PROMPT+'不要有電話',DEFAULT_PROMPT+'並開車'):
            with self.subTest(prompt=prompt),self.assertRaises(ValueError):compile_prompt(prompt)

if __name__=='__main__':unittest.main()
