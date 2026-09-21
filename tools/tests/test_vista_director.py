import copy
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from runtime.vista_live.bridge import atomic
from runtime.vista_live.director import Director, Stopped
from runtime.vista_live.director_contract import validate_scenario
from runtime.vista_live.director_routes import route


def step(skill,target='none',line='',seconds=0,speaker='human',audience='assistant'):
    return dict(skill=skill,target=target,line=line,seconds=seconds,speaker=speaker,audience=audience)


def scenario():
    return dict(supported=True,explanation='書房通話',mode='micro',scene_description='warm study',
        start_room='office',steps=[step('walk','phone'),step('pickup_phone'),step('answer_phone'),
        step('say',line='I will call you later.',audience='phone'),step('hangup_phone'),step('walk','window')],events=[])


class Contracts(unittest.TestCase):
    def test_valid_and_owned_copy(self):
        spec=scenario(); actual=validate_scenario(spec); actual['steps'].clear()
        self.assertEqual(len(spec['steps']),6)

    def test_phone_requires_reachable_pickup_and_active_call(self):
        for index in (0,1,2):
            spec=scenario(); del spec['steps'][index]
            with self.subTest(index=index), self.assertRaises(ValueError): validate_scenario(spec)

    def test_micro_cannot_inherit_home_device_events(self):
        spec=scenario(); spec['events']=[dict(id='mmg_021',at_s=5)]
        with self.assertRaises(ValueError): validate_scenario(spec)
        spec=scenario(); spec['steps'].insert(0,step('walk','bathroom_laundry'))
        with self.assertRaises(ValueError): validate_scenario(spec)

    def test_no_code_coordinates_assistant_role_or_unknown_fields(self):
        for change in ({'skill':'exec'},{'target':'/tmp/file'},{'speaker':'assistant'},
                       {'points_cm':[[1,2,3]]},{'seconds':True}):
            spec=scenario(); spec['steps'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): validate_scenario(spec)

    def test_unsupported_cannot_execute(self):
        spec=scenario(); spec['supported']=False
        with self.assertRaises(ValueError): validate_scenario(spec)
        spec['steps']=[]; self.assertFalse(validate_scenario(spec)['supported'])
        spec['scene_description']=''; self.assertFalse(validate_scenario(spec)['supported'])
        spec=scenario(); spec['scene_description']=''
        with self.assertRaises(ValueError): validate_scenario(spec)

    def test_named_rooms_use_stairs_not_xy_shortcut(self):
        points=route({'player_cm':[1147,-1071,86]},'bedroom')
        self.assertIn([1230,-50,246],points)
        self.assertIn([1410,-50,246],points)
        self.assertEqual(points[-1],[382,-1082,406])

    def test_departed_route_refused(self):
        with self.assertRaises(RuntimeError): route({'player_cm':[9999,0,0]},'bedroom')

    def test_micro_navigation_uses_rotation_and_binding(self):
        state={'player_cm':[-4160,-1960,1286],'micro_room':{'origin_cm':[-4000,-1800,1200],
            'arrangement':1,'family':'study'},'entities':[{'short_id':'phone','position_cm':[-3900,-1880,1300]}]}
        points=route(state,'window'); self.assertEqual(points[-1],[-4210,-1615,1286])


class Runner(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.live=Mock(); self.live.root=Path(self.temp.name); self.live.pool=Mock()
        self.live.world_lock=threading.RLock(); self.live.lock=threading.RLock()
        self.d=Director(self.live); self.d.owner='a'*32; self.d.identity=('session',1)
        self.state={'director':{'owner':self.d.owner},'clock_s':5,'session_id':'session','scene_epoch':1}
        atomic(self.live.root/'state.json',self.state)
        self.live.bridge.snapshot.return_value=(self.live.root,self.d.identity,{})
        self.d.folder=self.live.root

    def test_cancel_prevents_next_native_step(self):
        self.d.stop_event.set()
        with self.assertRaises(Stopped): self.d.command('path',points_cm=[[1,2,3]])
        self.live.bridge.command.assert_not_called()

    def test_scene_epoch_change_prevents_native_step(self):
        self.live.bridge.snapshot.return_value=(self.live.root,('session',2),{})
        with self.assertRaises(Stopped): self.d.command('phone',enabled=True)
        self.live.bridge.command.assert_not_called()

    def test_native_rejection_is_not_completion(self):
        self.live.bridge.command.return_value={'code':'ACTOR_BUSY'}
        with self.assertRaisesRegex(RuntimeError,'ACTOR_BUSY'): self.d.command('path',points_cm=[[1,2,3]])

    def test_action_waits_for_terminal_receipt_and_rejects_failure(self):
        def command(control,**fields):
            atomic(self.d.folder/'responses'/(fields['action_id']+'.json'),
                   {'status':'failed','code':'OUT_OF_REACH'})
        self.d.command=command
        with self.assertRaisesRegex(RuntimeError,'OUT_OF_REACH'): self.d.action('pick_up','phone')

    def test_one_job_at_a_time(self):
        self.d.job={'status':'running'}
        with self.assertRaises(ValueError): self.d.compile('another room')
        self.live.pool.submit.assert_not_called()

    def test_unsupported_compile_does_not_reset_or_request_voice(self):
        spec=scenario(); spec.update(supported=False,steps=[],events=[])
        self.live.api.return_value={'answer':spec}
        self.d._compile('x','unsupported',0)
        self.assertEqual(self.d.job['status'],'unsupported')
        self.live.apply.assert_not_called(); self.live.voice.assert_not_called()

    def test_restart_does_not_load_execution_receipts_as_proposals(self):
        row={'id':'test','scenario':scenario(),'prompt':'study','seed':0,'micro':None,
             'compiler_ms':1,'scene_ms':2}
        atomic(self.d.root/'a.json',row)
        atomic(self.d.root/'z.run.json',{'id':'test','scenario':scenario(),'status':'completed'})
        restored=Director(self.live)
        self.assertEqual(restored.state()['items'][0]['prompt'],'study')


if __name__=='__main__': unittest.main()
