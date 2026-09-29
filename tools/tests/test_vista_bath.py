import copy
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from runtime.vista_live.bath import BathDemo, PROTOCOL
from runtime.vista_live.bath_eval import evaluate, relevant_warning


class BathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.live = SimpleNamespace(root=Path(self.tmp.name), lock=threading.RLock(),
                                    research_clock=20, decisions=[])
        self.b = BathDemo(self.live)
        self.b.active = {'run_id':'run', 'condition':'model','phase':'observing',
                         'start':0,'events':[], 'model_calls':0}

    def delivered(self,text,cause='research:accepted',role='assistant'):
        self.b.delivered({'id':'heard','role':role,'text':text},cause)

    def test_only_accepted_delivered_water_warning_releases_person(self):
        line = 'The bath is filling up. May I turn off the tap?'
        self.delivered(line)
        self.assertFalse(any(e['kind']=='warning_delivered' for e in self.b.active['events']))
        self.live.decisions=[{'id':'accepted','result':'accepted','decision':{'action':'speak'}}]
        self.delivered('Have a nice day.')
        self.delivered('The tap is already off.')
        self.assertFalse(any(e['kind']=='warning_delivered' for e in self.b.active['events']))
        self.delivered(line); self.delivered(line)
        self.assertEqual(1,sum(e['kind']=='warning_delivered' for e in self.b.active['events']))

    def test_reference_does_not_masquerade_as_model(self):
        self.delivered('The bath is full.','bath_reference:run')
        self.assertFalse(self.b.active['events'][-1]['matched'])
        self.b.active['condition']='timely'
        self.delivered('The bath is full.','bath_reference:run')
        self.assertEqual('warning_delivered',self.b.active['events'][-1]['kind'])

    def test_speech_stop_and_other_episode_cannot_trigger_branch(self):
        self.b.active['phase']='stopped'
        self.delivered('The bath is full.','bath_reference:run')
        self.assertEqual([],self.b.active['events'])
        self.b.active.update(phase='observing',condition='timely')
        self.delivered('The bath is full.','bath_reference:old')
        self.assertFalse(self.b.active['events'][-1]['matched'])

    def test_permission_requires_actual_scoped_human_playback(self):
        self.delivered(PROTOCOL['permission'],'scenario_human:wrong:permission','human')
        self.assertEqual([],self.b.active['events'])
        self.delivered(PROTOCOL['permission'],'scenario_human:run:permission','human')
        self.assertEqual('permission_delivered',self.b.active['events'][-1]['kind'])

    def test_model_cap_is_per_episode_and_control_never_calls(self):
        self.assertEqual([True]*8+[False]*4,[self.b.reserve_call() for _ in range(12)])
        self.b.active.update(condition='control',model_calls=0)
        self.assertFalse(self.b.reserve_call())

    def test_action_success_does_not_erase_prior_overflow(self):
        rows=[{'t':i,'level':min(1,.75+i/360),'tap_on':i<110,'overflow':i>=90,
               'stove_on':False,'session_id':'session','scene_epoch':1,
               'execution':{'target':'faucet','status':'committed' if i>=110 else 'idle'}} for i in range(141)]
        result=evaluate(rows,[],140)
        self.assertTrue(result['complete'] and result['tap_off'] and result['overflow_ever'])
        self.assertFalse(result['avoided_overflow'])
        self.assertEqual(90,result['first_overflow_s'])
        # Even a repaired final state cannot erase the event.
        rows[-1]['overflow']=False
        self.assertTrue(evaluate(rows,[],140)['overflow_ever'])
        self.assertFalse(evaluate(rows[:100],[],140)['complete'])
        rows[80]['scene_epoch']=2
        self.assertFalse(evaluate(rows,[],140)['complete'])

    def test_dropped_time_and_unrelated_change_are_visible(self):
        rows=[{'t':i,'level':.8,'tap_on':False,'overflow':False,'stove_on':i==3,
               'session_id':'s','scene_epoch':1,'execution':{'target':'faucet','status':'committed'}}
              for i in [0,1,2,3,10,11]]
        r=evaluate(rows,[],11)
        self.assertFalse(r['complete']); self.assertFalse(r['stove_preserved_off'])


if __name__=='__main__': unittest.main()
