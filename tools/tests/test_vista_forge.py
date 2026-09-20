import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from runtime.vista_live.forge import (THEMES, CHOICES, catalogue, home_spec, micro_spec,
    normalize_recipe, signature, validate_micro, validate_recipe)
from runtime.vista_live.forge_service import Forge


RECIPE = {'support':'supported','family':'study','palette':'oak','lighting':'daylight'}


class FakeLive:
    def __init__(self, root):
        self.root=root;self.lock=threading.RLock();self.pool=ThreadPoolExecutor(2)
        self.proposals={};self.calls=[];self.voices=[];self.logs=[];self.author_job={};self.epoch=1
        self.gate=None;self.started=threading.Event();self.warning=''

    def api(self, kind, value):
        self.calls.append((kind,value));self.started.set()
        if self.gate:self.gate.wait(3)
        return {'answer':copy.deepcopy(RECIPE),'model':'test-only-compiler'}

    def voice(self, text, role):return {'text':text,'role':role}
    def speak(self, clip, epoch, cause):self.voices.append((clip,epoch,cause))
    def log(self,name,value):self.logs.append((name,value))


class ForgeTests(unittest.TestCase):
    def test_ten_distinct_themes_with_reproducible_events(self):
        self.assertEqual(len(THEMES),10)
        self.assertEqual(len({x['id'] for x in THEMES}),10)
        self.assertEqual(len({x['opening'] for x in THEMES}),10)
        for t in THEMES:
            a=home_spec(t['id'],3);self.assertEqual(a,home_spec(t['id'],3))
            self.assertNotEqual(signature(a),signature(home_spec(t['id'],9)))
            self.assertEqual({e['id'] for e in a['events']},set(t['events']))
        self.assertEqual(len({t['room'] for t in THEMES}),6)

    def test_geometry_is_bounded_and_cannot_inject_coordinates(self):
        m=micro_spec(RECIPE,8);self.assertEqual(validate_micro(m),m)
        for key,value in [('width_cm',10000),('seed',False),('arrangement',0),('schema','other')]:
            with self.assertRaises(ValueError):validate_micro({**m,key:value})
        with self.assertRaises(ValueError):validate_recipe({**RECIPE,'code':'run anything'})
        with self.assertRaises(ValueError):micro_spec({**RECIPE,'support':'unsupported'},1)
        self.assertEqual(m['arrangement'],2)

    def test_seed_does_not_claim_unbounded_geometry(self):
        a=micro_spec(RECIPE,1);b=micro_spec(RECIPE,4)
        self.assertNotEqual(signature(a),signature(b))
        self.assertEqual({k:v for k,v in a.items() if k!='seed'},
                         {k:v for k,v in b.items() if k!='seed'})

    def test_invalid_jev_distribution_is_not_accepted_as_a_recipe(self):
        raw={'answers':{k:{'type':'choice','choice':RECIPE[k],
             'probabilities':{x:1. if x==RECIPE[k] else 0. for x in opts},'confidence':1.}
             for k,opts in CHOICES.items()}}
        self.assertEqual(normalize_recipe(raw),RECIPE)
        bad=copy.deepcopy(raw);bad['answers']['family']['choice']='bedroom'
        with self.assertRaises(ValueError):normalize_recipe(bad)
        bad=copy.deepcopy(raw);bad['answers']['family']['probabilities']['pool']=0.
        with self.assertRaises(ValueError):normalize_recipe(bad)

    def test_seed_and_catalogue_are_copied(self):
        rows=catalogue();rows[0]['title']='changed';self.assertNotEqual(catalogue()[0]['title'],'changed')
        for seed in [-1,1.5,True,2**31]:
            with self.assertRaises(ValueError):home_spec('work',seed)

    def wait(self, forge):
        until=time.monotonic()+4
        while forge.state()['job']['status'] in ('building','stopping'):
            if time.monotonic()>until:self.fail('worker did not finish')
            time.sleep(.005)

    def test_generation_is_reviewable_without_changing_world(self):
        with tempfile.TemporaryDirectory() as d:
            live=FakeLive(Path(d));f=Forge(live)
            try:
                f.generate('work',12,'micro',count=3);self.wait(f)
                self.assertEqual(f.job['completed'],3)
                self.assertEqual([i['seed'] for i in f.items],[12,13,14])
                self.assertEqual(len({i['signature'] for i in f.items}),3)
                self.assertFalse(live.voices)
                for kind,value in live.calls:
                    self.assertEqual(kind,'forge_jev');self.assertEqual(set(value),{'request'})
                    self.assertNotIn('seed',json.dumps(value));self.assertNotIn('mmg_',json.dumps(value))
                self.assertEqual([i['seed'] for i in Forge(live).items],[12,13,14])
            finally:live.pool.shutdown()

    def test_stop_during_paid_call_preserves_result_and_stops_next_call(self):
        with tempfile.TemporaryDirectory() as d:
            live=FakeLive(Path(d));live.gate=threading.Event();f=Forge(live)
            try:
                f.generate('work',4,'micro',count=10)
                self.assertTrue(live.started.wait(1))
                with self.assertRaises(RuntimeError):f.generate('travel',1)
                f.cancel();live.gate.set();self.wait(f)
                self.assertEqual(f.job['status'],'stopped');self.assertEqual(len(live.calls),1)
                self.assertEqual(len(f.items),1)
            finally:live.gate.set();live.pool.shutdown()

    def test_bounded_batch_and_authored_opening_need_applied_scene(self):
        with tempfile.TemporaryDirectory() as d:
            live=FakeLive(Path(d));f=Forge(live)
            try:
                for n in [0,11,True,1.5]:
                    with self.assertRaises(ValueError):f.generate('work',1,count=n)
                f.generate('reading',7);self.wait(f)
                ident=f.items[0]['id']
                with self.assertRaises(ValueError):f.opening(ident)
                live.author_job={'id':ident,'status':'applied'};f.opening(ident)
            finally:live.pool.shutdown()
            self.assertEqual(len(live.voices),1)
            self.assertEqual(live.voices[0][2],'authored_theme_opening')
            self.assertFalse(live.calls)

    def test_provider_failure_stops_batch_without_retry(self):
        with tempfile.TemporaryDirectory() as d:
            live=FakeLive(Path(d));f=Forge(live)
            def fail(kind,value):live.calls.append((kind,value));raise RuntimeError('test rejection')
            live.api=fail
            try:
                f.generate('work',0,'micro',count=3);self.wait(f)
                self.assertEqual(f.job['status'],'failed');self.assertEqual(len(live.calls),1)
                self.assertFalse(f.items);self.assertEqual(len(live.logs),1)
            finally:live.pool.shutdown()


if __name__=='__main__':unittest.main()
