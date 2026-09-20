import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest

from runtime.vista_live.budget import Budget
from runtime.vista_live.contracts import public_observation, validate_scene, validate_plan
from runtime.vista_live.policy import Policy


def observation(clock=1, cues=()):
    return {'schema': 'vista.streaming-observation/v1', 'source': 'engine_visible_metadata_not_vlm',
            'wearer_role': 'human_needing_assistance', 'view': 'human_ego', 'clock_s': clock,
            'room': 'kitchen_dining', 'focused': '', 'objects': [], 'cues': list(cues),
            'human_activity': 'unspecified'}


class LivePolicyTests(unittest.TestCase):
    def test_hidden_fields_and_fixtures_rejected(self):
        for patch in ({'event_id': 'mmg_001'}, {'source': 'authored_observation_fixture'},
                      {'view': 'third_person_review'}, {'deadline_s': 3}, {'seed': 7}):
            with self.assertRaises(ValueError):
                public_observation({**observation(), **patch})

    def test_no_hazard_or_goal_no_notice(self):
        p = Policy(); p.ingest(observation())
        self.assertIsNotNone(p.guard('notice_water'))
        self.assertIsNotNone(p.guard('notice_keys'))
        p.ingest(observation(2, ['visible_stove_on_control']))
        self.assertEqual(p.guard('notice_stove'), 'no_human_goal')

    def test_phone_and_normal_water_not_urgent(self):
        p = Policy(); o = observation(1, ['visible_running_bath_tap']); o['human_activity'] = 'phone_at_ear'
        p.ingest(o)
        self.assertEqual(p.guard('notice_water'), 'no_observed_urgent_water')

    def test_preempt_resolve_resume_without_hidden_state(self):
        p = Policy(); p.ingest(observation(1, ['visible_stove_on_control']))
        p.utter("I'm leaving. Help me find my keys.", 'typed_user_input')
        p.record_goal('leave_find_keys')
        self.assertIsNone(p.accept('notice_stove'))
        p.ingest(observation(5, ['visible_water_near_rim']))
        self.assertIsNone(p.accept('notice_water'))
        self.assertEqual(p.pending['notice_stove'], 'suspended')
        p.ingest(observation(6))  # Leaving view is not resolution.
        self.assertEqual(p.active, 'notice_water')
        self.assertEqual(p.guard('notice_stove'), 'repeat_cooldown')
        p.ingest(observation(8, ['visible_bath_tap_off']))
        self.assertIsNone(p.accept('notice_stove'))
        self.assertEqual(p.active, 'notice_stove')

    def test_new_off_cancels_old_on_memory(self):
        p = Policy(); p.ingest(observation(1, ['visible_water_near_rim']))
        p.accept('notice_water'); p.ingest(observation(2, ['visible_bath_tap_off']))
        self.assertFalse(p.pending)
        self.assertIsNotNone(p.guard('notice_water'))

    def test_repeat_cooldown_and_changed_evidence_revision(self):
        p = Policy(); p.ingest(observation(1, ['visible_water_near_rim'])); revision = p.revision
        self.assertFalse(p.ingest(observation(1.2, ['visible_water_near_rim'])))
        self.assertEqual(revision, p.revision)
        p.accept('notice_water')
        self.assertEqual(p.guard('notice_water'), 'repeat_cooldown')
        p.ingest(observation(32, ['visible_water_near_rim']))
        self.assertIsNone(p.guard('notice_water'))

    def test_backward_clock_rejected(self):
        p = Policy(); p.ingest(observation(10))
        with self.assertRaises(ValueError): p.ingest(observation(2))

    def test_decorative_visibility_does_not_trigger_risk_reclassification(self):
        p = Policy(); p.ingest(observation())
        changed = observation(2); changed['objects'] = ['Sofa', 'Coffee table']
        self.assertFalse(p.ingest(changed))
        self.assertEqual(p.state()['current_observation']['objects'], changed['objects'])
        self.assertTrue(p.ingest(observation(3, ['visible_water_near_rim'])))

    def test_typed_request_keeps_provenance(self):
        p = Policy(); p.ingest(observation()); p.utter('Help please', 'typed_user_input')
        self.assertEqual(p.state()['human_utterances'][0]['source'], 'typed_user_input')
        with self.assertRaises(ValueError): p.utter('hello', 'ASR')

    def test_manipulation_needs_explicit_request_and_current_cue(self):
        p = Policy(); p.ingest(observation(1, ['visible_stove_on_control']))
        self.assertFalse(p.manipulation_allowed('stove'))
        self.assertTrue(p.manipulation_allowed('stove', True))
        p.ingest(observation(2))
        self.assertFalse(p.manipulation_allowed('stove', True))

    def test_state_copy_cannot_mutate_policy(self):
        p = Policy(); p.ingest(observation()); value = p.state()
        value['current_observation']['cues'].append('visible_water_near_rim')
        self.assertFalse(p.current['cues'])

    def test_water_stays_resolved_when_only_the_water_remains_visible(self):
        p = Policy(); p.ingest(observation(1, ['visible_running_bath_tap', 'visible_water_near_rim']))
        p.accept('notice_water'); p.ingest(observation(2, ['visible_bath_tap_off']))
        p.ingest(observation(3, ['visible_water_near_rim']))
        self.assertEqual(p.guard('notice_water'), 'tap_known_off')
        self.assertNotIn('notice_water', p.state()['eligible_actions'])
        self.assertIn('wait', p.state()['eligible_actions'])

    def test_keys_in_hand_resolves_goal_without_hidden_labels(self):
        p = Policy(); p.ingest(observation(1, ['visible_keys'])); p.utter('Find my keys', 'typed_user_input')
        p.record_goal('find_keys')
        p.accept('notice_keys'); p.ingest(observation(2, ['proprioceptive_keys_in_hand']))
        self.assertFalse(p.pending)
        self.assertEqual(p.guard('notice_keys'), 'keys_already_in_hand')


class LiveConcurrencyTests(unittest.TestCase):
    def live(self, folder):
        from runtime.vista_live.service import Live
        class FakeBridge:
            def __init__(self): self.calls = []
            def command(self, op, fields=None, identity=None):
                self.calls.append((op, fields, identity))
                return {'code': 'SPEECH_STARTED' if op == 'speech' else 'LIVE_STOPPED'}
        speech = folder / 'clips'; speech.mkdir()
        live = Live(folder / 'service', FakeBridge(), speech)
        self.addCleanup(live.pool.shutdown, wait=True)
        live.identity = ('session', 1); live.epoch = 1; live.world_ready = True
        live.policy.ingest(observation(1, ['visible_water_near_rim']))
        live.clips['assistant_water'] = {'role': 'assistant', 'text': 'Check the water.',
            'sample_rate': 24000, 'pcm_b64': 'AAAA', 'duration_s': 1, 'mouth': []}
        return live

    def test_external_scene_reset_clears_applied_proposal_but_same_scene_keeps_it(self):
        import time
        from unittest.mock import patch
        for identity, retained in ((('session', 1), True), (('session', 2), False)):
            with self.subTest(identity=identity), tempfile.TemporaryDirectory() as d:
                live = self.live(Path(d)); live.enabled = False
                live.author_job = {'id': 'old-room', 'status': 'applied'}
                live.budget_at = time.monotonic()
                def snapshot():
                    live.running = False
                    return {}, identity, observation(2)
                live.bridge.snapshot = snapshot
                live.bridge.feedback = lambda: None
                with patch('runtime.vista_live.service.time.sleep'):
                    live.tick()
                self.assertEqual(bool(live.author_job), retained)
                self.assertEqual(live.identity, identity)
                self.assertTrue(live.world_ready)

    def test_delayed_decision_cannot_survive_new_off_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); revision = live.policy.revision
            def api(kind, value):
                live.policy.ingest(observation(2, ['visible_bath_tap_off']))
                return {'answer': {'action': 'notice_water'}}
            live.api = api
            live.decide(1, revision, live.policy.state())
            self.assertFalse(live.bridge.calls)
            self.assertFalse(live.policy.pending)

    def test_cancel_invalidates_pending_network_reply(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); revision = live.policy.revision
            def api(kind, value):
                live.cancel()
                return {'answer': {'action': 'notice_water'}}
            live.api = api
            live.decide(1, revision, live.policy.state())
            self.assertEqual([c[0] for c in live.bridge.calls], ['stop'])

    def test_paused_queued_notice_does_not_play(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); live.enabled = False
            live.speak(live.clips['assistant_water'], 1, 100, 'jev:notice_water')
            self.assertFalse(live.bridge.calls)

    def test_urgent_notice_preempts_waiting_speech(self):
        import time
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); live.speech_until = time.monotonic() + 30
            live.policy.accept('notice_water')
            live.speak(live.clips['assistant_water'], 1, 100, 'jev:notice_water')
            self.assertEqual(live.bridge.calls[0][0], 'speech')

    def test_selection_is_not_evidence_of_audible_delivery(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); live.policy.accept('notice_water')
            self.assertEqual(live.policy.state()['assistant_notices'], [])
            live.speak(live.clips['assistant_water'], 1, 100, 'jev:notice_water')
            self.assertEqual(live.policy.state()['assistant_notices'][0]['action'], 'notice_water')

    def test_resolved_notice_cannot_play_from_the_queue(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); live.policy.accept('notice_water')
            live.policy.ingest(observation(2, ['visible_bath_tap_off']))
            live.speak(live.clips['assistant_water'], 1, 100, 'jev:notice_water')
            self.assertFalse(live.bridge.calls)

    def test_interrupted_human_line_is_not_observation(self):
        import time
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); live.policy.accept('notice_water')
            live.schedule = [{'kind': 'heard', 'at_wall': time.monotonic()+30, 'text': 'I am leaving.', 'epoch': 1}]
            live.speak(live.clips['assistant_water'], 1, 100, 'jev:notice_water')
            self.assertFalse(live.schedule)

    def test_failed_model_does_not_synthesize_a_fake_decision(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d))
            def api(*args): raise RuntimeError('Provider unavailable')
            live.api = api
            live.decide(1, live.policy.revision, live.policy.state())
            self.assertFalse(live.bridge.calls)
            self.assertIsNone(live.last_decision)
            self.assertIn('Provider unavailable', live.error)

    def test_rejected_stale_voice_does_not_disable_live_decisions(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); live.planned.add('notice_water')
            calls = []
            def api(kind, value):
                calls.append(kind)
                return {'answer': {'action': 'notice_water'}}
            live.api = api
            live.bridge.command = lambda *args: {'code': 'STALE_LIVE_REJECTED'}
            live.decide(1, live.policy.revision, live.policy.state())
            self.assertEqual(calls, ['decision'])
            self.assertEqual(live.error, '')
            self.assertTrue(live.dirty)
            self.assertFalse(live.policy.notices)
            self.assertIsNone(live.policy.guard('notice_water'))
            self.assertEqual(live.native_receipt['code'], 'STALE_LIVE_REJECTED')

    def test_unauthorized_generated_plan_is_not_published_or_executed(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d))
            live.api = lambda *args: {'answer': {'speech': 'I can check the tap.', 'steps': [
                {'skill': 'turn_off', 'target': 'faucet', 'description': 'Turn off the tap.'}]}}
            live.plan(1, live.policy.state(), 'notice_water', speak=False)
            self.assertIsNone(live.last_plan)
            self.assertFalse(live.bridge.calls)
            self.assertIn('not authorized', live.warning)


class BudgetTests(unittest.TestCase):
    def test_persistent_idempotency_and_no_ambiguous_retry(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'budget.sqlite'; b = Budget(path)
            self.assertIsNone(b.reserve('one', 'decision', {'a': 1}))
            with self.assertRaises(RuntimeError): Budget(path).reserve('one', 'decision', {'a': 1})
            b.finish('one', {'answer': 'wait'})
            self.assertEqual(Budget(path).reserve('one', 'decision', {'a': 1}), {'answer': 'wait'})
            with self.assertRaises(ValueError): b.reserve('one', 'decision', {'a': 2})
            self.assertEqual(b.status()['counts']['decision'], 1)

    def test_cap_reservation_is_atomic_across_threads(self):
        with tempfile.TemporaryDirectory() as d:
            b = Budget(Path(d) / 'budget.sqlite', cap=.02); success = []
            def reserve(i):
                try: b.reserve(str(i), 'plan', {}); success.append(i)
                except RuntimeError: pass
            threads = [threading.Thread(target=reserve, args=(i,)) for i in range(5)]
            for t in threads: t.start()
            for t in threads: t.join()
            self.assertEqual(len(success), 1)
            self.assertAlmostEqual(b.status()['reserved_usd'], .02)

    def test_failed_call_still_counts(self):
        with tempfile.TemporaryDirectory() as d:
            b = Budget(Path(d) / 'budget.sqlite', cap=.0015)
            b.reserve('a', 'decision', {}); b.finish('a', {'error': 'timeout'}, False)
            with self.assertRaises(RuntimeError): b.reserve('b', 'decision', {})

    def test_reported_cost_releases_only_unused_reservation_not_request_count(self):
        with tempfile.TemporaryDirectory() as d:
            b = Budget(Path(d) / 'budget.sqlite', cap=.002)
            b.reserve('a', 'decision', {})
            b.finish('a', {'usage': {'cost': .0001}})
            b.reserve('b', 'decision', {})
            self.assertEqual(b.status()['counts']['decision'], 2)
            self.assertAlmostEqual(b.status()['committed_usd'], .0016)
            b.finish('b', {'usage': {'cost': 0}}, False)
            self.assertAlmostEqual(Budget(b.path).status()['committed_usd'], .0016)

    def test_unknown_tts_cost_keeps_full_reservation(self):
        with tempfile.TemporaryDirectory() as d:
            b = Budget(Path(d) / 'budget.sqlite', cap=.04)
            b.reserve('a', 'tts', {}); b.finish('a', {'pcm_b64': 'AAAA'})
            self.assertAlmostEqual(b.status()['reserved_usd'], .04)
            with self.assertRaises(RuntimeError): b.reserve('b', 'decision', {})


class BridgeIdentityTests(unittest.TestCase):
    def test_native_replace_gap_is_retried_locally(self):
        from unittest.mock import patch
        from runtime.vista_live.bridge import read
        with patch.object(Path, 'read_text', side_effect=[FileNotFoundError(), '{"ready":true}']):
            self.assertEqual(read(Path('native-state.json')), {'ready': True})

    def test_action_generation_preserves_identity_but_scene_reset_changes_it(self):
        from runtime.vista_live.bridge import Bridge, atomic
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); folder = root / 'session'
            atomic(folder / 'observation.json', observation())
            raw = {'session_id': 's', 'scene_epoch': 1, 'generation': 2, 'clock_s': 1}
            atomic(folder / 'state.json', raw)
            b = Bridge(root, root); initial = b.snapshot()[1]
            atomic(folder / 'state.json', {**raw, 'generation': 3})
            self.assertEqual(b.snapshot()[1], initial)
            atomic(folder / 'state.json', {**raw, 'scene_epoch': 2, 'generation': 4})
            self.assertNotEqual(b.snapshot()[1], initial)


class AuthoringTests(unittest.TestCase):
    def setUp(self):
        self.spec = {'supported': True, 'explanation': '無爐火，浴缸延後放水', 'layout': 'workday',
                     'start_room': 'office', 'events': [{'id': 'mmg_021', 'delay_s': 30}],
                     'phone_call': False, 'phone_delay_s': 0, 'human_goal': 'none'}

    def test_no_stove_spec_preserved(self):
        self.assertEqual(validate_scene(self.spec)['events'], [{'id': 'mmg_021', 'delay_s': 30}])

    def test_reject_unknown_assets_events_timing_and_duplicates(self):
        for change in ({'layout': 'new_castle'}, {'events': [{'id': 'mmg_999', 'delay_s': 0}]},
                       {'events': [{'id': 'mmg_021', 'delay_s': -1}]},
                       {'events': self.spec['events'] * 2}, {'seed': 3}, {'phone_call': 1}):
            with self.assertRaises(ValueError): validate_scene({**self.spec, **change})

    def test_no_arbitrary_engine_or_human_actions(self):
        for skill in ('exec_console', 'teleport_human', 'turn_on', 'delete_wall'):
            with self.assertRaises(ValueError):
                validate_plan({'speech': 'I can help.', 'steps': [
                    {'skill': skill, 'target': 'stove', 'description': 'unsafe'}]})

    def test_generated_speech_is_short_english(self):
        for speech in ('你好', 'word ' * 26):
            with self.assertRaises(ValueError): validate_plan({'speech': speech, 'steps': []})

    def test_jev_subset_contract_still_rejects_nonwinner_or_ineligible_choice(self):
        from runtime.vista_live.contracts import normalize_live_choice
        raw = {'answers': {'next_action': {'type': 'choice', 'choice': 'wait',
            'confidence': .9, 'probabilities': {'wait': .9, 'observe': .1}}}}
        self.assertEqual(normalize_live_choice(raw, ['wait', 'observe'])['action'], 'wait')
        raw['answers']['next_action']['choice'] = 'observe'
        with self.assertRaises(ValueError): normalize_live_choice(raw, ['wait', 'observe'])
        raw['answers']['next_action']['choice'] = 'notice_water'
        with self.assertRaises(ValueError): normalize_live_choice(raw, ['wait', 'observe'])


if __name__ == '__main__': unittest.main()
