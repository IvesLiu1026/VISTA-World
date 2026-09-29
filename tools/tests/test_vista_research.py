import base64
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from runtime.vista_live.research_contract import model_request, validate_decision, validate_observation


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress((b'\0' + b'\x80\x80\x80' * 64) * 64)) + chunk(b'IEND', b''))


def observation():
    pixels = png()
    return {'schema': 'vista.research-observation/v1', 'session_id': 'session', 'scene_epoch': 1,
            'clock_s': 10, 'frame': {'id': 'frame10', 'clock_s': 10, 'width': 64, 'height': 64,
                                   'sha256': hashlib.sha256(pixels).hexdigest(), 'png_b64': base64.b64encode(pixels).decode()},
            'utterances': [{'id': 'turn9', 'role': 'human', 'audience': 'assistant', 'clock_s': 9,
                            'text': 'Please turn off the stove.', 'source': 'completed_in_world_speech'}],
            'own_action': None, 'memory': []}


def decision():
    return {'observed': 'The human asked for help.', 'evidence_ids': ['turn9', 'frame10'],
            'urgency': 'medium', 'action': 'turn_off_stove',
            'speech': '', 'permission_turn_id': 'turn9', 'reason': 'A direct request.', 'next_tasks': []}


class ResearchContractTests(unittest.TestCase):
    def test_provider_gets_real_image_and_no_exo_or_hidden_state(self):
        value = observation()
        body = model_request(value)
        parts = body['messages'][-1]['content']
        self.assertTrue(parts[1]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertNotIn('png_b64', parts[0]['text'])
        self.assertEqual(value, observation())
        for forbidden in ('events', 'scenario', 'seed', 'ground_truth', 'exo_file', 'cues'):
            with self.subTest(forbidden=forbidden), self.assertRaises(ValueError):
                validate_observation({**value, forbidden: 'secret'})

    def test_nested_hidden_fields_rejected(self):
        for field in ('frame', 'utterances'):
            value = observation()
            (value[field] if field == 'frame' else value[field][0])['hazard_truth'] = True
            with self.assertRaises(ValueError): validate_observation(value)

    def test_current_turn_focus_preserves_speaker_and_audience_without_inventing_facts(self):
        value = observation()
        value['utterances'].append({**value['utterances'][0], 'id': 'latest', 'role': 'phone',
                                    'audience': 'phone', 'text': 'Bring the green folder.'})
        focus = model_request(value)['messages'][-1]['content'][-1]['text']
        self.assertIn('"id": "latest"', focus)
        self.assertIn('"role": "phone"', focus)
        self.assertIn('"audience": "phone"', focus)
        self.assertIn('Bring the green folder.', focus)

    def test_future_dialogue_and_stale_capture_rejected(self):
        for change in ('future_dialogue', 'future_frame', 'stale_frame'):
            value = observation()
            if change == 'future_dialogue': value['utterances'][0]['clock_s'] = 11
            else: value['frame']['clock_s'] = 11 if change == 'future_frame' else 5
            with self.assertRaises(ValueError): validate_observation(value)

    def test_wrong_bytes_and_dimensions_rejected(self):
        for key, invalid in (('sha256', '0' * 64), ('width', 65), ('png_b64', '%%%'), ('png_b64', 'http://example.com')):
            value = observation(); value['frame'][key] = invalid
            with self.assertRaises(ValueError): validate_observation(value)

    def test_manipulation_needs_direct_unconsumed_current_request(self):
        self.assertEqual(validate_decision(decision(), observation())['action'], 'turn_off_stove')
        for patch in ({'audience': 'phone'}, {'role': 'phone'}, {'id': 'unknown'}):
            value = observation(); value['utterances'][0].update(patch)
            with self.assertRaises(ValueError): validate_decision(decision(), value)
        value = observation(); value['clock_s'] = 70
        with self.assertRaises(ValueError): validate_decision(decision(), value)
        value = observation(); value['memory'] = [{'permission_turn_id': 'turn9', 'result': 'accepted', 'action': 'turn_off_stove'}]
        with self.assertRaises(ValueError): validate_decision(decision(), value)

    def test_consumed_permission_changes_schema_but_not_hazard_priority(self):
        value = observation()
        schema = model_request(value)['response_format']['json_schema']['schema']
        self.assertIn('turn_off_stove', schema['properties']['action']['enum'])
        self.assertIn('turn_off_faucet', schema['properties']['action']['enum'])
        value['memory'] = [{'clock_s': 9.5, 'observed': 'Requested stove operation.',
                            'action': 'turn_off_stove', 'target': 'stove', 'speech': '',
                            'permission_turn_id': 'turn9', 'result': 'accepted'}]
        schema = model_request(value)['response_format']['json_schema']['schema']
        self.assertEqual(schema['properties']['action']['enum'], ['observe', 'speak'])
        self.assertEqual(schema['properties']['permission_turn_id']['enum'], [''])
        self.assertEqual(model_request(observation())['response_format']['json_schema']['schema']['properties']['action']['enum'],
                         ['observe', 'speak', 'turn_off_stove', 'turn_off_faucet', 'follow', 'wait', 'cancel'])

    def test_unknown_evidence_and_unsupported_action_rejected(self):
        for patch in ({'evidence_ids': ['future']}, {'action': 'teleport'}, {'target': 'keys'}):
            with self.assertRaises(ValueError): validate_decision({**decision(), **patch}, observation())

    def test_completion_can_cite_only_its_supplied_own_execution_receipt(self):
        value = observation()
        value['own_action'] = {'id': 'native1', 'status': 'committed', 'target': 'stove'}
        answer = {**decision(), 'action': 'speak', 'permission_turn_id': '',
                  'speech': 'The stove is off.', 'evidence_ids': ['native1']}
        self.assertEqual(validate_decision(answer, value), answer)
        schema = model_request(value)['response_format']['json_schema']['schema']
        self.assertEqual(set(schema['properties']['evidence_ids']['items']['enum']), {'native1', 'frame10', 'turn9'})
        with self.assertRaises(ValueError): validate_decision(answer, observation())

    def test_only_single_complete_json_fence_is_unwrapped(self):
        from runtime.vista_live.provider import research_json
        valid = json.dumps(decision())
        self.assertEqual(research_json('```json\n' + valid + '\n```'), decision())
        for invalid in ('Here it is: ' + valid, '```json\n' + valid + '\n``` trailing',
                        '```json\n{"action":"observe","action":"cancel"}\n```',
                        '```json\n{}\n```\n```json\n{}\n```'):
            with self.assertRaises(ValueError): research_json(invalid)

    def test_english_typography_is_canonical_but_non_english_or_long_speech_still_rejected(self):
        answer = {**decision(), 'speech': 'I\u2019ll turn it off.'}
        self.assertEqual(validate_decision(answer, observation())['speech'], "I'll turn it off.")
        self.assertEqual(answer['speech'], 'I\u2019ll turn it off.')
        for invalid in ('\u597d\u7684', '\U0001f600', 'word ' * 33, 'x' * 241, 'two\nlines'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_decision({**decision(), 'speech': invalid}, observation())


class ResearchRuntimeTests(unittest.TestCase):
    def live(self, root):
        from runtime.vista_live.research import ResearchLive
        class Bridge:
            def __init__(self): self.calls = []
            def command(self, op, fields=None, identity=None):
                self.calls.append((op, fields))
                return {'code': {'assist': 'ASSIST_ACCEPTED', 'speech': 'SPEECH_STARTED',
                                 'stop': 'LIVE_STOPPED', 'stop_speech': 'SPEECH_STOPPED',
                                 'caption': 'CAPTION_SET'}[op], 'action_id': 'a1'}
        clips = root / 'clips'; clips.mkdir()
        live = ResearchLive(root / 'live', Bridge(), clips)
        self.addCleanup(live.pool.shutdown, wait=True)
        live.identity = ('session', 1); live.epoch = 1; live.revision = 1
        live.research_clock = 11; live.world_ready = True
        live.api = lambda kind, packet: {'answer': decision(), 'model': 'large-model', 'latency_ms': 123}
        return live

    def test_large_model_decides_without_jev_or_fixed_hazard_priority(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); calls = []
            def api(kind, packet):
                calls.append(kind)
                return {'answer': decision(), 'model': 'large-model', 'latency_ms': 123}
            live.api = api
            live.research_decide(1, 1, 'job', observation())
            self.assertEqual(calls, ['research'])
            self.assertEqual(live.bridge.calls, [('assist', {'target': 'stove'})])
            self.assertEqual(live.decisions[0]['result'], 'accepted')

    def test_delayed_reply_rejected_after_new_human_input_or_cancel(self):
        for change in ('new_turn', 'phone_turn', 'cancel', 'reset', 'stale', 'execution_advanced'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                live = self.live(Path(d))
                def api(kind, packet):
                    if change == 'new_turn': live.add_turn('No, leave it alone.')
                    elif change == 'phone_turn': live.add_turn('The appointment moved to Friday.', role='phone', audience='phone')
                    elif change == 'cancel': live.enabled = False
                    elif change == 'reset': live.identity = ('session', 2)
                    elif change == 'execution_advanced': live.feedback = {'id': 'new', 'status': 'committed'}
                    else: live.research_clock = 25
                    return {'answer': decision(), 'model': 'large-model', 'latency_ms': 123}
                live.api = api
                live.research_decide(1, 1, 'job', observation())
                self.assertFalse(live.bridge.calls)

    def test_same_permission_never_executes_twice_even_after_memory_rollover(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d))
            live.research_decide(1, 1, 'job1', observation())
            live.memory.clear()
            live.research_decide(1, 1, 'job2', observation())
            self.assertEqual(len(live.bridge.calls), 1)
            self.assertEqual(live.decisions[-1]['result'], 'native_rejected')

    def test_failed_native_action_is_not_reported_as_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d))
            live.bridge.command = lambda *a, **kw: {'code': 'ASSIST_APPROACH_REJECTED'}
            live.research_decide(1, 1, 'job1', observation())
            self.assertEqual(live.decisions[0]['result'], 'native_rejected')
            self.assertFalse(live.consumed_permissions)

    def test_reset_drops_prior_action_and_cancel_retains_own_target(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d))
            native = {'id': 'old', 'status': 'cancelled', 'target': '', 'finger_error_cm': 0}
            self.assertEqual(live.own_feedback(native), {})
            live.action_targets['old'] = 'stove'
            self.assertEqual(live.own_feedback(native)['target'], 'stove')
            self.assertEqual(native['target'], '')
            live._reset_research(('session', 2))
            self.assertEqual(live.own_feedback(native), {})

    def test_manual_requests_do_not_contaminate_no_intervention_comparison(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d))
            live.enabled = False
            for phase in ('starting', 'running', 'stopping'):
                live.director.job = {'status': phase, 'assistant': 'off'}
                with self.assertRaisesRegex(ValueError, 'no-intervention'):
                    live.say('Please turn off the stove.')
                with self.assertRaisesRegex(ValueError, 'no-intervention'):
                    live.observe()
                self.assertFalse(live.enabled)
                self.assertFalse(live.turns)
                self.assertFalse(live.bridge.calls)
            live.director.job['status'] = 'stopped'
            self.assertTrue(live.observe()['accepted'])
            self.assertTrue(live.enabled)

    def test_new_turn_bypasses_one_slow_call_but_never_exceeds_two(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d))
            pending = []
            live.pool = Mock(submit=lambda *args: pending.append(args))
            live.capture.observation = lambda *args: observation()
            live.say('Please turn off the stove.')
            live.queue_research(100)
            self.assertEqual(len(pending), 1)
            live.say('Wait, please turn off the tap instead.')
            live.queue_research(101)
            self.assertEqual(len(pending), 2)
            live.say('Actually, stop and wait here.')
            live.queue_research(102)
            self.assertEqual(len(pending), 2)
            # The obsolete response cannot act. It frees a slot for only the
            # latest turn, rather than replaying every intermediate request.
            pending[0][0](*pending[0][1:])
            self.assertFalse(live.bridge.calls)
            live.queue_research(103)
            self.assertEqual(len(pending), 3)
            self.assertEqual(len(live.research_inflight), 2)
            self.assertEqual(pending[-1][2], live.revision)

    def test_obsolete_provider_error_does_not_pause_newer_turn(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d))
            def old_request(*args):
                live.say('A new request.')
                raise RuntimeError('Old request timed out')
            live.api = old_request
            live.research_decide(1, 1, 'old', observation())
            self.assertEqual(live.error, '')
            self.assertTrue(live.research_requested)

    def test_execution_confirmation_waits_for_an_image_after_the_receipt(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); pending = []
            live.pool = Mock(submit=lambda *args: pending.append(args))
            live.capture.observation = lambda *args: observation()
            live.capture.latest = {'clock_s': 10}
            live.executions = [{'clock_s': 10.5, 'status': 'committed'}]
            live.research_requested = True
            live.queue_research(100)
            self.assertFalse(pending)
            live.capture.latest['clock_s'] = 10.6
            live.queue_research(101)
            self.assertEqual(len(pending), 1)

    def test_speech_only_enters_observation_after_completed_playback(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d))
            clip = {'text': 'Tell me about your day.', 'role': 'phone', 'sample_rate': 24000,
                    'pcm_b64': 'AAAA', 'duration_s': 1, 'mouth': []}
            live.speak(clip, 1, cause='authored_phone_exchange:1')
            self.assertFalse(live.turns)
            self.assertEqual(live.schedule[0]['kind'], 'research_heard')
            clip = {**clip, 'text': 'I need to go.', 'role': 'human'}
            live.speak(clip, 1, 100, cause='scenario_human:2')
            self.assertFalse(any(s['kind'] == 'research_heard' for s in live.schedule))
            self.assertEqual(live.schedule[0]['kind'], 'heard')


class ResearchProviderTests(unittest.TestCase):
    def test_explicit_larger_model_preserves_contract_and_checks_returned_identity(self):
        import io
        from runtime.vista_live.provider import Provider
        model = 'qwen/qwen3.5-397b-a17b'
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); key = root / 'key'; key.write_text('sk-or-v1-test-only-placeholder')
            provider = Provider(root / 'evidence', key, chat_model=model)
            bodies = []
            class Response(io.BytesIO):
                headers = {'Content-Type': 'application/json'}
            class Upstream:
                def open(self, request, timeout):
                    bodies.append(json.loads(request.data))
                    return Response(json.dumps({'model': model if len(bodies) == 1 else 'qwen/qwen3.5-35b-a3b',
                        'choices': [{'message': {'content': json.dumps(decision())}}],
                        'usage': {'cost': .004}}).encode())
            provider.opener = Upstream()
            result = provider.call({'id': 'first', 'kind': 'research', 'input': observation()})
            self.assertEqual(result['model'], model)
            self.assertEqual(bodies[0]['model'], model)
            self.assertFalse(bodies[0]['provider']['allow_fallbacks'])
            self.assertTrue(bodies[0]['response_format']['json_schema']['strict'])
            with self.assertRaisesRegex(RuntimeError, 'model identity mismatch'):
                provider.call({'id': 'second', 'kind': 'research', 'input': observation()})
            self.assertEqual(provider.budget.status()['counts']['plan'], 2)

    def test_explicit_openai_adapter_keeps_strict_schema_and_supported_parameters(self):
        import io
        from runtime.vista_live.provider import Provider
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); key = root / 'key'; key.write_text('sk-or-v1-test-only-placeholder')
            provider = Provider(root / 'evidence', key, chat_model='openai/gpt-5.4-mini', chat_provider='openai')
            bodies = []
            class Response(io.BytesIO):
                headers = {'Content-Type': 'application/json'}
            class Upstream:
                def open(self, request, timeout):
                    bodies.append(json.loads(request.data))
                    return Response(json.dumps({'model': 'openai/gpt-5.4-mini',
                        'choices': [{'message': {'content': json.dumps(decision())}}],
                        'usage': {'cost': .004}}).encode())
            provider.opener = Upstream()
            provider.call({'id': 'first', 'kind': 'research', 'input': observation()})
            self.assertNotIn('temperature', bodies[0])
            self.assertEqual(bodies[0]['reasoning'], {'effort': 'low'})
            self.assertEqual(bodies[0]['max_tokens'], 1400)
            self.assertEqual(bodies[0]['provider']['only'], ['openai'])
            self.assertTrue(bodies[0]['response_format']['json_schema']['strict'])

    def test_explicit_endpoint_and_open_circuit_do_not_change_allowance(self):
        import io
        from runtime.vista_live.provider import Provider
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); key = root / 'key'; key.write_text('sk-or-v1-test-only-placeholder')
            provider = Provider(root / 'evidence', key, chat_provider='deepinfra/fp8')
            bodies = []
            class Response(io.BytesIO):
                headers = {'Content-Type': 'application/json'}
            class Upstream:
                def open(self, request, timeout):
                    bodies.append(json.loads(request.data))
                    return Response(json.dumps({'model': 'qwen/qwen3.5-35b-a3b', 'provider': 'DeepInfra',
                        'choices': [{'message': {'content': json.dumps(decision())}}],
                        'usage': {'cost': .001}}).encode())
            provider.opener = Upstream()
            provider.call({'id': 'first', 'kind': 'research', 'input': observation()})
            self.assertEqual(bodies[0]['provider']['only'], ['deepinfra/fp8'])
            self.assertFalse(bodies[0]['provider']['allow_fallbacks'])
            before = provider.budget.status()
            (provider.root / 'circuit.json').write_text('{"http_status":429}')
            with self.assertRaisesRegex(RuntimeError, 'circuit open'):
                provider.call({'id': 'second', 'kind': 'research', 'input': observation()})
            self.assertEqual(before, provider.budget.status())
            self.assertEqual(len(bodies), 1)


if __name__ == '__main__':
    unittest.main()
