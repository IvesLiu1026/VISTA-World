import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from runtime.vista_live.director import Director, Stopped
from runtime.vista_live.director_contract import LONG_SCHEMA, validate_scenario
from runtime.vista_live.research_contract import model_request, validate_decision, validate_observation, canonical_memory_selection
from runtime.vista_live.research_memory import EpisodicMemory
from runtime.vista_live.research_audit import audit_memory, audit_walk_speech
from tools.tests import test_vista_director as actor_examples
from tools.tests import test_vista_research as research_examples


def extended():
    return {**actor_examples.scenario(), 'schema': LONG_SCHEMA}


def answer(packet, keep):
    return {**research_examples.decision(), 'action': 'observe', 'speech': '',
            'permission_turn_id': '', 'evidence_ids': [packet['frame']['id']],
            'remember_turn_ids': keep, 'next_tasks': ['Remember the new meeting location']}


class MemoryTests(unittest.TestCase):
    def test_identical_transport_echo_yields_one_decision_and_conflicts_stay_rejected(self):
        from runtime.vista_live.provider import research_json, strict_json
        original = research_examples.decision(); text = json.dumps(original); notes = []
        self.assertEqual(research_json(text + '\n\n' + text, notes), original)
        self.assertEqual(notes, ['duplicate_identical_json_document_removed'])
        with self.assertRaises(ValueError): strict_json(text + '\n' + text)
        for invalid in (text + '\n' + json.dumps({**original, 'action': 'cancel'}),
                        text + '\n' + text + '\n' + text, text + '\nprose',
                        '{"action":"wait","action":"cancel"}\n{"action":"wait","action":"cancel"}'):
            with self.assertRaises(ValueError): research_json(invalid)

    def test_stop_follow_and_wait_need_exact_current_direct_permission(self):
        packet = EpisodicMemory().observation(research_examples.observation())
        packet['utterances'][0]['text'] = 'Please wait here.'
        for action in ('wait', 'cancel', 'follow'):
            result = {**answer(packet, []), 'action': action, 'permission_turn_id': 'turn9'}
            self.assertEqual(validate_decision(result, packet)['permission_turn_id'], 'turn9')
            for ident in ('', 'unknown'):
                with self.assertRaises(ValueError):
                    validate_decision({**result, 'permission_turn_id': ident}, packet)
            caller = copy.deepcopy(packet); caller['utterances'][0]['audience'] = 'phone'
            with self.assertRaises(ValueError): validate_decision(result, caller)
        acknowledged = {**answer(packet, []), 'action': 'speak', 'speech': 'Take your time.'}
        self.assertEqual(validate_decision(acknowledged, packet)['permission_turn_id'], '')

    def test_provider_set_normalization_changes_only_duplicate_existing_memory_ids(self):
        packet = EpisodicMemory().observation(research_examples.observation())
        raw = answer(packet, ['turn9','turn9'])
        normalized = canonical_memory_selection(raw,packet)
        self.assertEqual(normalized, {**raw,'remember_turn_ids':['turn9']})
        self.assertEqual(raw['remember_turn_ids'],['turn9','turn9'])
        self.assertEqual(validate_decision(normalized,packet),normalized)
        for ids in (['future','future'], ['turn9']*9, ['frame10'], [None]):
            with self.assertRaises(ValueError): canonical_memory_selection(answer(packet,ids),packet)
        physical = {**raw,'action':'turn_off_stove','permission_turn_id':'unseen'}
        with self.assertRaises(ValueError): validate_decision(canonical_memory_selection(physical,packet),packet)

    def test_verbatim_recall_survives_recent_window_and_has_original_provenance(self):
        memory = EpisodicMemory()
        p = memory.observation(research_examples.observation())
        memory.update(p, answer(p, ['turn9']))
        newer = research_examples.observation()
        newer['utterances'] = [{**newer['utterances'][0], 'id': 'other', 'text': 'How is the weather?'}]
        p2 = memory.observation(newer)
        self.assertEqual(p2['recalled_utterances'], p['utterances'])
        self.assertEqual(p2['agenda'], ['Remember the new meeting location'])
        p2['recalled_utterances'][0]['text'] = 'Tampered local copy'
        self.assertEqual(memory.utterances[0]['text'], 'Please turn off the stove.')

    def test_memory_may_only_select_existing_human_or_phone_turns(self):
        memory = EpisodicMemory(); p = memory.observation(research_examples.observation())
        p['utterances'].append({**p['utterances'][0], 'id': 'bot', 'role': 'assistant', 'audience': 'human'})
        for invalid in (['hidden-event'], ['bot'], ['turn9', 'turn9'], ['frame10'], 'turn9', [None]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                memory.update(p, answer(p, invalid))
        self.assertEqual(memory.utterances, [])

    def test_superseded_memory_can_be_replaced_without_rewriting_evidence(self):
        memory = EpisodicMemory(); p = memory.observation(research_examples.observation())
        memory.update(p, answer(p, ['turn9']))
        p['utterances'].append({**p['utterances'][0], 'id': 'correction', 'text': 'The meeting moved to eleven.'})
        memory.update(p, answer(p, ['correction']))
        self.assertEqual([r['id'] for r in memory.utterances], ['correction'])

    def test_recall_is_evidence_but_never_renews_physical_permission(self):
        memory = EpisodicMemory(); p = memory.observation(research_examples.observation())
        memory.update(p, answer(p, ['turn9']))
        later = research_examples.observation(); later['utterances'] = []
        later['clock_s'] = later['frame']['clock_s'] = 100
        packet = memory.observation(later)
        schema = model_request(packet)['response_format']['json_schema']['schema']
        self.assertIn('turn9', schema['properties']['evidence_ids']['items']['enum'])
        self.assertEqual(schema['properties']['permission_turn_id']['enum'], [''])
        self.assertEqual(schema['properties']['action']['enum'], ['observe', 'speak'])
        with self.assertRaises(ValueError):
            validate_decision({**research_examples.decision(), 'remember_turn_ids': ['turn9']}, packet)

    def test_identity_reset_discards_memory_and_late_update(self):
        memory = EpisodicMemory(); p = memory.observation(research_examples.observation())
        memory.update(p, answer(p, ['turn9']))
        fresh = research_examples.observation(); fresh['scene_epoch'] = 2
        self.assertEqual(memory.observation(fresh)['recalled_utterances'], [])
        self.assertEqual(memory.agenda, [])
        with self.assertRaises(ValueError): memory.update(p, answer(p, ['turn9']))

    def test_extended_observation_is_still_closed_at_every_level(self):
        memory = EpisodicMemory(); p = memory.observation(research_examples.observation())
        for key in ('scenario', 'events', 'ground_truth'):
            with self.assertRaises(ValueError): validate_observation({**p, key: []})
        for row in ({**p['utterances'][0], 'hidden': 1}, {**p['utterances'][0], 'clock_s': 11},
                    {**p['utterances'][0], 'role': 'assistant'}, None):
            packet = copy.deepcopy(p); packet['utterances'] = []; packet['recalled_utterances'] = [row]
            with self.assertRaises(ValueError): validate_observation(packet)
        with self.assertRaises(ValueError): validate_observation({**p, 'agenda': ['task'] * 5})
        with self.assertRaises(ValueError): validate_observation({**p, 'recalled_utterances': p['utterances']})

    def test_v1_does_not_accept_new_fields_or_decisions(self):
        old = research_examples.observation()
        with self.assertRaises(ValueError): validate_observation({**old, 'agenda': []})
        with self.assertRaises(ValueError): validate_decision(answer(old, []), old)


class LongContractTests(unittest.TestCase):
    def test_long_author_reserves_more_cost_inside_the_same_durable_plan_allowance(self):
        from runtime.vista_live.budget import Budget
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'budget.sqlite'; b=Budget(path,cap=.04)
            body={'kind':'scenario_long','input':'A long home scenario'}
            b.reserve('long','plan',body)
            self.assertEqual(b.status()['counts'],{'plan':1})
            self.assertAlmostEqual(b.status()['reserved_usd'],.04)
            with self.assertRaises(RuntimeError): Budget(path).reserve('other','plan',{})
            with self.assertRaises(RuntimeError): Budget(path).reserve('long','plan',body)
            b.finish('long',{'usage':{'cost':.005}})
            self.assertAlmostEqual(Budget(path).status()['committed_usd'],.005)
            b.reserve('short','plan',{})
            self.assertAlmostEqual(b.status()['reserved_usd'],.02)

    def test_curated_stimuli_are_executable_without_any_assistant_script(self):
        from runtime.vista_live.complex_examples import examples
        for row in examples():
            self.assertEqual(validate_scenario(row['scenario']), row['scenario'])
            self.assertEqual(row['compiler_model'], 'curated-human-stimulus/v1')
            self.assertTrue(all(s['speaker'] in ('human','phone') for s in row['scenario']['steps']))

    def test_long_profile_is_explicit_and_old_bounds_remain(self):
        p = extended(); p['steps'] = [actor_examples.step('wait', seconds=1)] * 48
        self.assertEqual(len(validate_scenario(p)['steps']), 48)
        old = copy.deepcopy(p); del old['schema']
        with self.assertRaises(ValueError): validate_scenario(old)
        p['steps'].append(actor_examples.step('wait', seconds=1))
        with self.assertRaises(ValueError): validate_scenario(p)

    def test_more_dialogue_is_allowed_only_within_extended_speech_and_wait_limits(self):
        p = extended(); p['steps'] = [actor_examples.step('say', line='Hello.', seconds=10)] * 16
        self.assertEqual(len(validate_scenario(p)['steps']), 16)
        p['steps'].append(actor_examples.step('say', line='Again.'))
        with self.assertRaises(ValueError): validate_scenario(p)
        p['steps'] = [actor_examples.step('wait', seconds=30)] * 11
        with self.assertRaises(ValueError): validate_scenario(p)

    def test_walk_say_needs_valid_scene_destination_and_phone_state(self):
        p = extended()
        p['steps'][3] = actor_examples.step('walk_say', 'window', 'We will meet at eleven.', speaker='phone', audience='phone')
        self.assertEqual(validate_scenario(p)['steps'][3]['skill'], 'walk_say')
        for patch in ({'target': 'stove'}, {'speaker': 'assistant'}, {'line': 'x' * 181}):
            bad = copy.deepcopy(p); bad['steps'][3].update(patch)
            with self.assertRaises(ValueError): validate_scenario(bad)
        del p['steps'][2]
        with self.assertRaises(ValueError): validate_scenario(p)

    def test_late_events_stay_bounded_and_do_not_add_new_hazards(self):
        p = extended(); p['mode'] = 'home'; p['steps'] = [actor_examples.step('wait', seconds=1)]
        p['events'] = [{'id': 'mmg_021', 'at_s': 600}]
        self.assertEqual(validate_scenario(p)['events'][0]['at_s'], 600)
        for event in ({'id':'mmg_021','at_s':601}, {'id':'hidden_event','at_s':2}):
            p['events'] = [event]
            with self.assertRaises(ValueError): validate_scenario(p)


class ConcurrentActorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.live = Mock(); self.live.root = Path(self.temp.name)
        self.live.lock = threading.RLock(); self.live.world_lock = threading.RLock()
        self.d = Director(self.live); self.calls = []
        self.d.check = lambda: {'crouch_alpha':0, 'player_cm':[0,0,0]}
        self.d.command = lambda control, **kw: self.calls.append(control) or {'clock_s':1}
        self.d.dialogue = lambda *args: self.calls.append('spoken') or {'status':'spoken'}
        self.d.until = lambda *args: {'clock_s':5, 'director':{'motion':'arrived'}, 'player_cm':[100,0,0]}
        self.d.wait = lambda value: self.calls.append('listen')

    def test_path_starts_before_voice_and_both_must_finish(self):
        with patch('runtime.vista_live.director.route', return_value=[[100,0,0]]):
            result = self.d.step(actor_examples.step('walk_say', 'office', 'Hello.', seconds=1), 0, {0:{}})
        self.assertEqual(self.calls, ['path', 'spoken', 'listen'])
        self.assertEqual(result['movement']['motion'], 'arrived')

    def test_spoken_line_cannot_hide_blocked_movement(self):
        self.d.until = lambda *args: {'clock_s':5, 'director':{'motion':'blocked'}}
        with patch('runtime.vista_live.director.route', return_value=[[100,0,0]]), self.assertRaisesRegex(RuntimeError, 'blocked'):
            self.d.step(actor_examples.step('walk_say', 'office', 'Hello.'), 0, {0:{}})

    def test_stop_during_voice_does_not_issue_a_second_motion(self):
        def stopped(*args): raise Stopped('Stopped during speech')
        self.d.dialogue = stopped
        with patch('runtime.vista_live.director.route', return_value=[[100,0,0]]), self.assertRaises(Stopped):
            self.d.step(actor_examples.step('walk_say', 'office', 'Hello.'), 0, {0:{}})
        self.assertEqual(self.calls, ['path'])


class PassiveDialogueTests(unittest.TestCase):
    def test_episode_tail_waits_for_reply_playback_and_completed_turn_without_new_calls(self):
        factory = research_examples.ResearchRuntimeTests()
        with tempfile.TemporaryDirectory() as directory:
            live = factory.live(Path(directory)); self.addCleanup(live.pool.shutdown)
            live.enabled = True; live.error = ''; live.research_job = 'pending'
            live.research_requested = False; live.speech_until = 0
            live.api = Mock(side_effect=AssertionError('Tail must not request a new answer'))
            d = live.director
            def phases(predicate, seconds, label):
                self.assertEqual(seconds, 45)
                self.assertFalse(predicate({}))  # Network or TTS still pending.
                live.research_job = None; live.speech_until = 105
                self.assertFalse(predicate({}))  # Native voice is still playing.
                live.speech_until = 99
                live.schedule = [{'kind':'research_heard','epoch':live.epoch}]
                self.assertFalse(predicate({}))  # Completed utterance not ingested yet.
                live.schedule.clear()
                self.assertTrue(predicate({}))
            d.until = phases
            with patch('runtime.vista_live.director.time.monotonic',return_value=100):
                d.finish_dialogue('live')
            live.api.assert_not_called()
            d.until = Mock(side_effect=AssertionError('Control must not wait for an assistant'))
            d.finish_dialogue('off')

    def test_episode_tail_remains_cancellable(self):
        factory = research_examples.ResearchRuntimeTests()
        with tempfile.TemporaryDirectory() as directory:
            live = factory.live(Path(directory)); self.addCleanup(live.pool.shutdown)
            live.director.check = Mock(side_effect=Stopped('User took control'))
            with self.assertRaises(Stopped): live.director.finish_dialogue('live')

    def test_phone_chain_coalesces_but_direct_request_and_periodic_scan_do_not_wait(self):
        factory = research_examples.ResearchRuntimeTests()
        with tempfile.TemporaryDirectory() as directory:
            live = factory.live(Path(directory)); pending = []
            self.addCleanup(live.pool.shutdown)
            live.pool = Mock(submit=lambda *args: pending.append(args))
            live.capture.observation = lambda *args: research_examples.observation()
            live.enabled = True; live.research_due = 130
            with patch('runtime.vista_live.research.time.monotonic',return_value=100):
                live.add_turn('The meeting moved.',role='phone',audience='phone')
            live.queue_research(100.5); self.assertFalse(pending)
            with patch('runtime.vista_live.research.time.monotonic',return_value=100.8):
                live.add_turn('Okay.',audience='phone')
            live.queue_research(101.1); self.assertFalse(pending)
            with patch('runtime.vista_live.research.time.monotonic',return_value=101.2):
                live.add_turn('Please wait here.')
            live.queue_research(101.2); self.assertEqual(len(pending),1)
            live.research_job = None;live.research_inflight.clear();live.research_due=130
            with patch('runtime.vista_live.research.time.monotonic',return_value=129.8):
                live.add_turn('One more thing.',role='phone',audience='phone')
            live.queue_research(130);self.assertEqual(len(pending),2)


class EvidenceAuditTests(unittest.TestCase):
    def test_question_review_uses_completed_assistant_turns_before_next_direct_input(self):
        from runtime.vista_live.complex_audit import after_question
        dialogue = [dict(role=r, audience=a, text=t) for r,a,t in [
            ('human','assistant','When?'), ('phone','phone','Ten.'),
            ('assistant','human','Eleven.'), ('human','phone','Thanks.'),
            ('human','assistant','Where?'), ('assistant','human','Library.')]]
        self.assertEqual(after_question(dialogue,'When?')['answers'],['Eleven.'])
        self.assertFalse(after_question(dialogue,'Missing')['present'])

    def test_dialogue_review_excludes_other_scene_and_future_turns(self):
        from runtime.vista_live.complex_audit import episode_dialogue
        turns=[{'clock_s':i,'wall_time':i,'id':str(i)} for i in range(8)]
        sessions=[{'wall_time':0,'identity':['one',1]},{'wall_time':4,'identity':['two',1]}]
        job={'requested_wall_time':2,'finished_wall_time':6}
        self.assertEqual([r['id'] for r in episode_dialogue(turns,sessions,job,('one',1))],['2','3'])

    def test_complex_success_is_not_inferred_from_a_complete_actor_or_empty_dialogue(self):
        from runtime.vista_live.complex_audit import audit_case
        for case in ('plans','permission'):
            self.assertFalse(audit_case(case,[],[],[],{'status':'completed'})['passed'])

    def test_recall_requires_identical_completed_same_scene_utterance(self):
        memory = EpisodicMemory(); p = memory.observation(research_examples.observation())
        memory.update(p, answer(p, ['turn9'])); later = research_examples.observation(); later['utterances'] = []
        packet = memory.observation(later)
        requests = [{'kind':'research','id':'req','wall_time':20,'input':packet}]
        dialogue = [{'wall_time':10,**p['utterances'][0]}]
        sessions = [{'wall_time':5,'identity':['session',1]}]
        actual = audit_memory(requests,dialogue,sessions,('session',1))
        self.assertTrue(actual['passed']);self.assertEqual(actual['recalled_ids'],['turn9'])
        for patch in ({'text':'invented'}, {'wall_time':21}):
            self.assertFalse(audit_memory(requests,[{**dialogue[0],**patch}],sessions,('session',1))['passed'])
        self.assertFalse(audit_memory(requests,dialogue,[{'wall_time':5,'identity':['other',1]}],('session',1))['passed'])

    def test_speech_requires_observed_motion_during_its_own_interval(self):
        job={'steps':[{'index':0,'step':{'skill':'walk_say','speaker':'phone'},
                      'receipt':{'status':'spoken','speech_started_clock_s':2,'speech_finished_clock_s':4,
                                 'movement':{'motion':'arrived'}}}]}
        trace=[{'clock_s':t,'player_cm':[t*30,0,0]} for t in range(6)]
        self.assertTrue(audit_walk_speech(trace,job)['passed'])
        still=[{**row,'player_cm':[0,0,0]} for row in trace]
        self.assertFalse(audit_walk_speech(still,job)['passed'])
        job['steps'][0]['receipt']['status']='interrupted'
        self.assertFalse(audit_walk_speech(trace,job)['passed'])


if __name__ == '__main__': unittest.main()
