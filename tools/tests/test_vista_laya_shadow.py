import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from runtime.vista_live.laya_shadow import observation, ShadowClient
from tools.tests import test_vista_research as research_fixtures
from tools.tests.test_vista_research import observation as rgb, decision


class ShadowTests(unittest.TestCase):
    def test_only_observed_dialogue_and_loopback_are_accepted(self):
        turn = {'id':'a','role':'human','audience':'assistant','text':'Please wait here.'}
        self.assertEqual(observation({'turns':[turn]}), [turn])
        for packet in ({'turns':[turn],'hazards':['stove']}, {'turns':[{**turn,'permission':True}]},
                       {'turns':[]}, {'turns':[turn]*7}, {'turns':[{**turn,'text':'x'*501}]}):
            with self.assertRaises(ValueError): observation(packet)
        for url in ('https://example.com','http://192.168.1.1:49130','http://127.0.0.1:49130/extra'):
            with self.assertRaises(ValueError): ShadowClient(url, Mock())

    def test_advice_cannot_replace_large_model_decision_or_supply_permission(self):
        with tempfile.TemporaryDirectory() as folder:
            live = research_fixtures.ResearchRuntimeTests.live(self,Path(folder))
            live.laya_shadow = Mock(latest={'choice':'help','confidence':1.0})
            turn = live.add_turn('Do not touch the stove.')
            self.assertFalse(live.bridge.calls)
            self.assertEqual(live.laya_shadow.submit.call_args.args[0][-1]['id'],turn['id'])
            packet=rgb(); live.revision=1
            live.api=lambda *args:{'answer':{**decision(),'action':'observe','permission_turn_id':''},
                                   'model':'large-model','latency_ms':10}
            live.research_decide(1,1,'job',packet)
            self.assertFalse(live.bridge.calls)
            self.assertEqual(live.last_decision['decision']['action'],'observe')
