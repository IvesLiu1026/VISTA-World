import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from runtime.vista_live.streaming import read_completion, speech_chunks, speech_preview
from runtime.vista_live.provider import Provider
from tools.tests.test_vista_research import observation, decision
from tools.tests import test_vista_research as research_fixtures


def event(content='', finish=None, **extra):
    return ('data: ' + json.dumps({'id': 'gen-test', 'model': 'openai/gpt-5.4-mini',
        'provider': 'OpenAI', 'choices': [{'index': 0, 'delta': {'content': content},
        'finish_reason': finish}], **extra}) + '\n\n').encode()


class StreamParsingTests(unittest.TestCase):
    def test_preview_is_complete_top_level_text_only(self):
        text = 'I can help with that. Let us check the door.'
        document = json.dumps({'observed': 'A quoted "speech": "fake".', 'speech': text, 'reason': 'ok'})
        end = document.index(', "reason"')
        self.assertIsNone(speech_preview(document[:document.index('with')]))
        self.assertEqual(speech_preview(document[:end]), text)
        self.assertEqual(speech_preview('```json\n'+document[:end]), text)
        self.assertIsNone(speech_preview('Here is my reply:\n```json\n'+document))
        self.assertIsNone(speech_preview('{"nested":{"speech":"Do something else."},'))
        self.assertIsNone(speech_preview('{"observed":"x","observed":"y","speech":"Bad duplicate."}'))
        self.assertIsNone(speech_preview('{"speech":"line\\nline"}'))

    def test_sentences_keep_words_and_abbreviations(self):
        text = 'Please ask Dr. Lee about it. The meeting starts at 11.30.'
        parts = speech_chunks(text)
        self.assertEqual(parts, ['Please ask Dr. Lee about it.', 'The meeting starts at 11.30.'])
        self.assertEqual(' '.join(speech_chunks('Yes. I can help with that.')), 'Yes. I can help with that.')

    def test_usage_terminal_repeat_and_comments(self):
        text = json.dumps({'speech': 'Your meeting starts at eleven.', 'next_tasks': []})
        wire = b': processing\n\n' + event(text[:20]) + event(text[20:], 'stop')
        wire += event('', 'stop', usage={'cost': .001}) + b'data: [DONE]\n\n'
        previews = []
        raw, timing = read_completion(io.BytesIO(wire), previews.append)
        self.assertEqual(raw['choices'][0]['message']['content'], text)
        self.assertEqual(raw['usage']['cost'], .001)
        self.assertEqual(previews, ['Your meeting starts at eleven.'])
        self.assertIn('first_content_ms', timing)

    def test_truncation_error_changed_identity_and_extra_content_fail(self):
        good = event('{"speech":"Hello there."}', 'stop')
        bad = [good, event('{}', 'length') + b'data: [DONE]\n\n',
               event('{}', error={'message': 'failed'}) + b'data: [DONE]\n\n',
               good + event('extra') + b'data: [DONE]\n\n',
               event('{') + event('}', 'stop', model='other/model') + b'data: [DONE]\n\n']
        for wire in bad:
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                read_completion(io.BytesIO(wire))


class ProviderStreamTests(unittest.TestCase):
    def test_final_validation_and_persistent_accounting_still_apply(self):
        class Reply(io.BytesIO):
            headers = {'Content-Type': 'text/event-stream'}
        class Opener:
            def __init__(self, answer): self.answer = answer; self.sent = None
            def open(self, req, timeout):
                self.sent = json.loads(req.data)
                return Reply(event(json.dumps(self.answer), 'stop', usage={'cost': .001}) + b'data: [DONE]\n\n')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key = root/'key'; key.write_text('sk-or-v1-test-only-placeholder')
            provider = Provider(root/'provider', key, chat_model='openai/gpt-5.4-mini')
            answer = {**decision(), 'speech': 'I will help with the stove.'}
            opener = Opener(answer); provider.opener = opener
            previews = []
            request = {'id': 'stream-one', 'kind': 'research', 'input': observation()}
            result = provider.call(request, previews.append)
            self.assertEqual(result['answer'], answer)
            self.assertEqual(previews, [answer['speech']])
            self.assertTrue(opener.sent['stream'])
            self.assertEqual(provider.budget.status()['counts']['plan'], 1)
            self.assertEqual(provider.call(request, previews.append), result)
            self.assertEqual(provider.budget.status()['counts']['plan'], 1)
            opener.answer = {**answer, 'permission_turn_id': 'invented'}
            with self.assertRaises(RuntimeError):
                provider.call({**request, 'id': 'stream-invalid'}, previews.append)
            # Speculative speech can exist, but the invalid decision is never returned.
            self.assertEqual(provider.budget.status()['counts']['plan'], 2)
            self.assertTrue((provider.root/'stream-invalid.failure.json').exists())


class StreamedRuntimeTests(unittest.TestCase):
    def live(self, root):
        live = research_fixtures.ResearchRuntimeTests.live(self, root)
        self.addCleanup(live.voice_pool.shutdown, wait=True)
        live.research_stream = True
        live.local_tts = 'http://127.0.0.1:49119'
        return live

    def test_preview_only_prepares_audio_and_final_must_validate(self):
        for outcome in ('valid', 'invalid', 'new_turn', 'stop', 'changed_speech'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as folder:
                live = self.live(Path(folder)); prepared = []; played = []
                live.voice = lambda line, role: prepared.append(line) or {'text':line,'role':role}
                live.speak = lambda clip, *args: played.append(clip['text'])
                preview = 'I can help with that. The stove is near you.'
                final = 'I will check the stove.' if outcome == 'changed_speech' else preview
                answer = {**decision(), 'speech': final}
                if outcome == 'invalid': answer['permission_turn_id'] = 'invented'
                class Response:
                    headers = {'Content-Type':'application/x-ndjson'}
                    def __enter__(self): return self
                    def __exit__(self, *args): pass
                    def __iter__(self):
                        yield (json.dumps({'event':'speech_preview','text':preview})+'\n').encode()
                        # Wait for speculative preparation, but no execution is allowed.
                        live.voice_pool.submit(lambda:None).result(timeout=2)
                        if live.bridge.calls or played: raise AssertionError('Executed before validation')
                        if outcome == 'new_turn': live.add_turn('Actually, leave it alone.')
                        if outcome == 'stop': live.enabled = False
                        yield (json.dumps({'event':'result','result':{'answer':answer,
                            'model':'large-model','latency_ms':123}})+'\n').encode()
                with patch('urllib.request.urlopen', return_value=Response()):
                    live.research_decide(1,1,'job',observation())
                if outcome in ('valid','changed_speech'):
                    self.assertEqual(played, speech_chunks(final))
                    self.assertEqual(live.bridge.calls, [('assist',{'target':'stove'})])
                    self.assertEqual(prepared.count(speech_chunks(preview)[0]), 1)
                else:
                    self.assertFalse(played)
                    self.assertFalse(live.bridge.calls)

    def test_preview_does_not_start_paid_tts_and_stale_segments_are_dropped(self):
        with tempfile.TemporaryDirectory() as folder:
            live = self.live(Path(folder)); live.local_tts = None
            live.voice = lambda *args: self.fail('Preview must not call cloud TTS')
            wire = (json.dumps({'event':'speech_preview','text':'I can help with that.'})+'\n'+
                    json.dumps({'event':'error','error':'Incomplete model stream'})+'\n').encode()
            class Response(io.BytesIO): headers={'Content-Type':'application/x-ndjson'}
            with patch('urllib.request.urlopen', return_value=Response(wire)), self.assertRaises(RuntimeError):
                live.research_api(observation(),'job',1,1)
            live.decisions.append({'id':'old','revision':0})
            live._speak({'role':'assistant','text':'Obsolete sentence.'},1,cause='research:old')
            self.assertFalse(live.bridge.calls)

    def test_first_native_audio_times_direct_turn_once_not_later_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            live=self.live(Path(folder)); turn=live.add_turn('Can you help me?')
            live.decisions.append({'id':'answer','revision':live.revision})
            live.research_timing['answer']={'request_wall':time.time()-.4,
                'turn_wall':live.turn_wall[turn['id']], 'turn_id':turn['id']}
            clip={'text':'I can help with that.','role':'assistant','duration_s':.2,
                  'pcm_b64':'AA==','sample_rate':24000}
            live.speak(clip,live.epoch,cause='research:answer')
            self.assertIn(turn['id'],live.answered_turn_ids)
            self.assertGreaterEqual(live.last_latency['request_to_audio_ms'],400)
            self.assertEqual(live.last_latency['turn_id'],turn['id'])
            pending=[];live.pool=Mock(submit=lambda *args:pending.append(args))
            live.capture.observation=lambda *args:observation();live.speech_until=0
            live.queue_research(time.monotonic())
            self.assertEqual(len(pending),1)
            self.assertIsNone(live.research_timing[pending[0][3]]['turn_id'])


if __name__ == '__main__':
    unittest.main()
