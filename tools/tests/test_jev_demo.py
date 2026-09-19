import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from runtime.vista_jev.protocol import Memory, validate_observation, validate_answer, normalize_jev, ACTIONS
from runtime.vista_jev.prepare import fixture, prepare
from runtime.vista_jev.runner import run
from runtime.vista_streaming.policy import Policy
from runtime.vista_jev.serve import byte_range, handler, FILES


class ObservationBoundaryTests(unittest.TestCase):
    def test_oracle_fields_and_nested_transcript_metadata_are_rejected(self):
        for key in ('seed', 'future', 'deadline', 'gold', 'event_id', 'priority', 'decision'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_observation(dict(fixture(0), **{key: 'hidden'}))
        obs = fixture(0, text='Please help')
        obs['utterance']['expected_action'] = 'notice_water'
        with self.assertRaises(ValueError): validate_observation(obs)

    def test_reviewer_camera_cannot_enter_model_input(self):
        obs = fixture(0)
        obs['view'] = 'third_person_review'
        with self.assertRaises(ValueError): Memory().ingest(obs)

    def test_memory_contains_only_past_observations_and_own_notices(self):
        memory = Memory()
        first = memory.ingest(fixture(0, ['visible_water_near_rim']))
        frozen = copy.deepcopy(first)
        memory.accept('notice_water')
        later = memory.ingest(fixture(10, ['visible_bath_tap_off']))
        self.assertEqual(first, frozen)
        self.assertNotIn('visible_bath_tap_off', json.dumps(first))
        self.assertEqual(later['assistant_notices'][0]['age_s'], 10)
        self.assertEqual(later['last_seen_cues'][0]['age_s'], 10)
        with self.assertRaises(ValueError): memory.ingest(fixture(1))

    def test_invalid_or_unimplemented_actions_and_nan_are_rejected(self):
        for action in ('turn_off_faucet', 'navigate', 'invented'):
            with self.assertRaises(ValueError):
                validate_answer({'action': action, 'confidence': 1, 'reason': 'x'})
        for confidence in (float('nan'), float('inf'), True, -1, 2):
            with self.assertRaises(ValueError):
                validate_answer({'action': 'wait', 'confidence': confidence, 'reason': 'x'})

    def test_jev_requires_complete_distribution(self):
        raw = {'answers': {'next_action': {'type': 'choice', 'choice': 'wait',
               'probabilities': {a: .2 for a in ACTIONS}, 'confidence': .2}}}
        self.assertEqual(normalize_jev(raw)['action'], 'wait')
        raw['answers']['next_action']['probabilities']['wait'] = 1
        with self.assertRaises(ValueError): normalize_jev(raw)

    def test_jev_accepts_rounded_probabilities_but_rejects_inconsistent_choice(self):
        raw = {'answers': {'next_action': {'type': 'choice', 'choice': 'wait',
               'probabilities': dict(zip(ACTIONS, [.34, .33, .33, .01, .01])), 'confidence': .1}}}
        self.assertEqual(normalize_jev(raw)['action'], 'wait')
        raw['answers']['next_action']['choice'] = 'notice_water'
        with self.assertRaises(ValueError): normalize_jev(raw)

    def test_controls_are_separate_and_original_decisions_never_transferred(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d)/'source.json'
            obs = fixture(0)
            obs['source'] = 'engine_visible_metadata_not_vlm'
            source.write_text(json.dumps([{'observation': obs, 'decision': {'gold': 'secret evaluator'}}]))
            out = Path(d)/'prepared'
            prepare(source, out)
            public = (out/'inputs.jsonl').read_text()
            self.assertNotIn('secret evaluator', public)
            self.assertNotIn('allowed_actions', public)
            self.assertIn('authored_observation_fixture', public)
            self.assertTrue(json.loads((out/'control-labels.json').read_text()))


class RunnerReceiptTests(unittest.TestCase):
    def test_openrouter_jev_uses_decisions_api_and_retains_real_identity_and_distribution(self):
        import io
        raw = {'id': 'test-generation', 'model': 'typesafe/jev-1.13-20260917',
               'provider': 'TypeSafe', 'usage': {'input_tokens': 100, 'output_tokens': 0, 'cost': .0000042},
               'answers': {'next_action': {'type': 'choice', 'choice': 'wait', 'confidence': .95,
                           'probabilities': {a: float(a == 'wait') for a in ACTIONS}}}}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); inputs = root/'inputs.jsonl'
            inputs.write_text(json.dumps({'id': 'r-0', 'episode': 'e', 'observation': fixture(0)})+'\n')
            args = SimpleNamespace(inputs=inputs, out=root/'results', provider='openrouter-jev',
                                   key_file=None, limit=1, budget=.1)
            response = io.BytesIO(json.dumps(raw).encode()); response.status = 200
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-only-placeholder'}):
                with patch('urllib.request.OpenerDirector.open', return_value=response) as send:
                    run(args)
                    request = send.call_args.args[0]
                    self.assertEqual(request.full_url, 'https://openrouter.ai/api/alpha/decisions')
                    body = json.loads(request.data)
                    self.assertEqual(body['model'], 'typesafe/jev-1.13')
                    self.assertNotIn('messages', body)
                    self.assertEqual(body['questions']['next_action']['type'], 'choice')
                    self.assertNotIn('allowed_actions', json.dumps(body))
                    receipt = json.loads((args.out/'r-0.receipt.json').read_text())
                    self.assertEqual(receipt['returned_model'], raw['model'])
                    self.assertEqual(receipt['answer']['probabilities']['wait'], 1)
                    self.assertEqual(receipt['cost_usd'], .0000042)
                with patch('urllib.request.OpenerDirector.open') as send:
                    run(args)
                    send.assert_not_called()

    def test_unreceipted_submission_is_not_automatically_retried(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); out = root/'results'; out.mkdir()
            inputs = root/'input.jsonl'
            inputs.write_text(json.dumps({'id': 'r-0', 'episode': 'e', 'observation': fixture(0)})+'\n')
            (out/'r-0.started.json').write_text('{}')
            args = SimpleNamespace(inputs=inputs, out=out, provider='openrouter', key_file=None, limit=1, budget=.1)
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-only-placeholder'}):
                with patch('urllib.request.OpenerDirector.open') as send:
                    with self.assertRaisesRegex(RuntimeError, 'Unreceipted'): run(args)
                    send.assert_not_called()

    def test_missing_credentials_never_produce_a_mock_success(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); inputs = root/'inputs.jsonl'
            inputs.write_text(json.dumps({'id': 'r-0', 'episode': 'e', 'observation': fixture(0)})+'\n')
            args = SimpleNamespace(inputs=inputs, out=root/'results', provider='jev', key_file=None, limit=1, budget=.1)
            with patch.dict('os.environ', {}, clear=True):
                with self.assertRaisesRegex(SystemExit, 'Missing'): run(args)
            self.assertEqual(json.loads((args.out/'status.json').read_text())['status'], 'missing_credentials')
            self.assertEqual(list(args.out.glob('*.receipt.json')), [])

    def test_unexpected_provider_model_is_preserved_as_a_failed_call(self):
        import io
        raw = {'model': 'different-model', 'usage': {'cost': .001}, 'answers': {}}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); inputs = root/'input.jsonl'
            inputs.write_text(json.dumps({'id': 'r-0', 'episode': 'e', 'observation': fixture(0)})+'\n')
            args = SimpleNamespace(inputs=inputs, out=root/'results', provider='openrouter-jev',
                                   key_file=None, limit=1, budget=.1)
            response = io.BytesIO(json.dumps(raw).encode()); response.status = 200
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-only-placeholder'}):
                with patch('urllib.request.OpenerDirector.open', return_value=response) as send:
                    run(args)
                    self.assertEqual(send.call_count, 1)
            receipt = json.loads((args.out/'r-0.receipt.json').read_text())
            self.assertIsNone(receipt['answer'])
            self.assertEqual(receipt['cost_usd'], .001)
            self.assertEqual(receipt['returned_model'], 'different-model')
            self.assertEqual(json.loads((args.out/'r-0.response.json').read_text()), raw)


class ComparisonIntegrityTests(unittest.TestCase):
    def test_changed_control_labels_cannot_be_reported_as_a_matched_comparison(self):
        from runtime.vista_jev.report import build
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); new = root/'new'; prior = root/'prior'
            new.mkdir(); prior.mkdir()
            row = {'id': 'r-0', 'episode': 'control', 'relative_s': 0, 'observation': fixture(0)}
            labels = [{'id': 'r-0', 'allowed_actions': ['wait']}]
            for run_dir in (new, prior):
                (run_dir/'inputs.jsonl').write_text(json.dumps(row)+'\n')
                (run_dir/'control-labels.json').write_text(json.dumps(labels))
            (prior/'control-labels.json').write_text('[]')
            trace = root/'trace.json'; trace.write_text('[]')
            with self.assertRaisesRegex(ValueError, 'identical frozen inputs and labels'):
                build(new, trace, 'jev', prior)
            self.assertFalse((new/'web').exists())


class PrivateReviewServerTests(unittest.TestCase):
    def test_video_ranges_support_safari_suffix_and_reject_invalid_ranges(self):
        self.assertEqual(byte_range('bytes=0-1', 100), (0, 1, True))
        self.assertEqual(byte_range('bytes=-12', 100), (88, 99, True))
        self.assertEqual(byte_range('bytes=90-', 100), (90, 99, True))
        for value in ('bytes=100-', 'bytes=-0', 'bytes=5-2', 'bytes=0-1,5-6'):
            with self.subTest(value=value), self.assertRaises(ValueError): byte_range(value, 100)

    def test_only_inventoried_assets_are_exposed_and_post_is_disabled(self):
        import hashlib
        from http.server import ThreadingHTTPServer
        import threading
        from urllib.request import urlopen, Request
        from urllib.error import HTTPError
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); manifest = {}
            for name in FILES:
                (root/name).write_bytes(b'0123456789')
                manifest[name] = {'sha256': hashlib.sha256(b'0123456789').hexdigest()}
            (root/'web-assets.json').write_text(json.dumps(manifest))
            (root/'private.txt').write_text('not public')
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(root))
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            base = 'http://127.0.0.1:'+str(server.server_port)
            try:
                req = Request(base+'/demo.mp4', headers={'Range': 'bytes=0-1'})
                with urlopen(req) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.read(), b'01')
                    self.assertEqual(response.headers['Content-Range'], 'bytes 0-1/10')
                for path in ('/private.txt', '/../private.txt', '/web-assets.json'):
                    with self.assertRaises(HTTPError) as error: urlopen(base+path)
                    self.assertEqual(error.exception.code, 404)
                with self.assertRaises(HTTPError) as error: urlopen(Request(base+'/', data=b'{}'))
                self.assertEqual(error.exception.code, 405)
            finally:
                server.shutdown(); server.server_close(); worker.join()


if __name__ == '__main__': unittest.main()
