import tempfile
import time
import threading
import unittest
from pathlib import Path

from runtime.vista_live.budget import Budget
from runtime.vista_live.conversation import Conversation
from runtime.vista_live.contracts import validate_dialogue
from tools.tests import test_vista_live as baseline
observation = baseline.observation


def ready(c, text, now=1):
    c.human(text, 'typed_user_input', now, now)
    c.pending['classified'] = True
    return c.begin(now+1)


class TurnTests(unittest.TestCase):
    def test_open_topic_and_both_speakers_preserved_only_after_delivery(self):
        c = Conversation(); ticket, ctx = ready(c, 'I like astronomy and green tea.')
        self.assertEqual(len(ctx['turns']), 1)
        self.assertTrue(c.delivered(ticket, 'What interests you about astronomy?', 3, 3))
        ticket, ctx = ready(c, 'What drink did I mention?', 4)
        self.assertEqual([t['role'] for t in ctx['turns']], ['human', 'assistant', 'human'])
        self.assertIn('green tea', ctx['turns'][0]['text'])
        self.assertEqual(ctx['turns'][1]['source'], 'native_playback_completed')

    def test_pause_invalidates_network_and_queued_voice(self):
        c = Conversation(); ticket, _ = ready(c, 'Tell me about jazz.')
        c.pause()
        self.assertFalse(c.valid(ticket)); self.assertIsNone(c.begin(100))
        self.assertFalse(c.delivered(ticket, 'Jazz began...', 5, 5))

    def test_caption_is_real_text_evidence_but_not_claimed_as_completed_audio(self):
        c = Conversation(); ticket, _ = ready(c, 'Coffee?')
        self.assertTrue(c.presented(ticket, 'Do you prefer espresso?', 3))
        self.assertEqual(c.turns[-1]['source'], 'native_caption_presented')
        c.delivered(ticket, 'Do you prefer espresso?', 4, 4)
        self.assertEqual(len(c.turns), 2)
        self.assertEqual(c.turns[-1]['source'], 'native_caption_and_playback_completed')

    def test_interruption_retains_unanswered_question_and_resumes_once(self):
        c = Conversation(); old, _ = ready(c, 'Why is the sky blue?')
        c.interrupt(); c.interrupt()
        self.assertFalse(c.valid(old)); self.assertIsNone(c.begin(10))
        self.assertFalse(c.delivered(old, 'An interrupted explanation.', 10, 10))
        c.release(10)
        self.assertIsNone(c.begin(11))
        new, ctx = c.begin(12)
        self.assertEqual(ctx['mode'], 'resume')
        self.assertEqual(ctx['question'], 'Why is the sky blue?')
        self.assertTrue(c.delivered(new, 'Air scatters shorter blue wavelengths more.', 14, 14))
        self.assertIsNone(c.begin(200))  # Never invent a human answer or nag.

    def test_new_input_supersedes_generated_reply_without_erasing_history(self):
        c = Conversation(); old, _ = ready(c, 'Tell me about music.')
        newer, ctx = ready(c, 'Actually, explain black holes.', 3)
        self.assertFalse(c.valid(old)); self.assertTrue(c.valid(newer))
        self.assertEqual(ctx['question'], 'Actually, explain black holes.')

    def test_wait_for_intent_and_do_not_retry_a_failed_generation(self):
        c = Conversation(); c.human('Hello', 'typed_user_input', 1, 1)
        self.assertIsNone(c.begin(20))
        c.pending['classified'] = True; ticket, _ = c.begin(21)
        c.failed(ticket)
        self.assertIsNone(c.begin(100)); self.assertEqual(c.status, 'unavailable')

    def test_resume_after_heard_answer_preserves_real_topic(self):
        c = Conversation(); ticket, _ = ready(c, 'My hobby is chess.')
        c.delivered(ticket, 'Do you prefer quick games?', 3, 3)
        c.interrupt(); c.release(5)
        _, ctx = c.begin(7)
        self.assertEqual(ctx['mode'], 'resume')
        self.assertEqual(ctx['question'], '')
        self.assertEqual(len(ctx['turns']), 2)

    def test_task_request_does_not_replace_topic_on_resume(self):
        c = Conversation(); ticket, _ = ready(c, 'Why do stars twinkle?')
        c.delivered(ticket, 'Air turbulence changes their light.', 3, 3)
        ready(c, 'I need my keys.', 4)
        c.pending['task_request'] = True
        c.interrupt(); c.release(7)
        _, ctx = c.begin(9)
        self.assertEqual(ctx['question'], '')
        self.assertEqual(ctx['mode'], 'resume')

    def test_both_captioned_and_audio_only_task_replies_keep_their_purpose(self):
        for caption in (False, True):
            with self.subTest(caption=caption):
                c = Conversation(); ticket, _ = ready(c, 'Help me find my keys.')
                c.pending['task_request'] = True
                if caption: c.presented(ticket, 'I cannot see them here.', 2)
                self.assertTrue(c.delivered(ticket, 'I cannot see them here.', 3, 3))
                self.assertEqual(c.turns[-1]['purpose'], 'task')
                self.assertEqual(c.turns[-1]['ticket'], ticket)
                ready(c, 'I still need my keys.', 4); c.pending['task_request'] = True
                c.interrupt(); c.release(5); ticket, _ = c.begin(7)
                self.assertTrue(c.delivered(ticket, 'Back to our music discussion.', 8, 8))
                self.assertEqual(c.turns[-1]['purpose'], 'casual')

    def test_separate_speech_schema_cannot_smuggle_engine_actions(self):
        self.assertEqual(validate_dialogue({'speech': 'You mentioned green tea.'})['speech'], 'You mentioned green tea.')
        for data in ({'speech': 'Hello', 'turn_off': 'stove'}, {'speech': 'word '*46}, {'speech': '你好'}):
            with self.assertRaises(ValueError): validate_dialogue(data)

    def test_task_allowance_is_durable_and_cannot_be_silently_raised(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'budget.sqlite'
            limits = {'decision': 8, 'plan': 4, 'tts': 2}
            b = Budget(path, cap=.2, limits=limits); b.reserve('one', 'decision', {})
            self.assertEqual(Budget(path).status()['limits'], limits)
            with self.assertRaises(ValueError): Budget(path, cap=2)
            with self.assertRaises(ValueError): Budget(path, limits={**limits, 'tts': 40})
            self.assertEqual(Budget(path).status()['counts']['decision'], 1)


class ConversationServiceTests(unittest.TestCase):
    def live(self, folder):
        live = baseline.LiveConcurrencyTests.live(self, folder)
        live.policy.ingest(observation(2, ['visible_bath_tap_off']))
        return live

    def test_stale_chat_completion_never_reaches_tts(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); ticket, ctx = ready(live.conversation, 'Coffee?')
            calls = []
            def api(kind, value):
                calls.append(kind)
                live.conversation.human('New topic', 'typed_user_input', 5, 5)
                return {'answer': {'speech': 'Do you like espresso?'}}
            live.api = api; live.chat_answer(1, ticket, ctx)
            self.assertEqual(calls, ['chat']); self.assertFalse(live.bridge.calls)

    def test_pause_during_native_start_stops_the_acknowledged_voice(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); ticket, _ = ready(live.conversation, 'Hello')
            started, release = threading.Event(), threading.Event(); calls = []
            def command(op, fields=None, identity=None):
                calls.append(op)
                if op == 'speech':
                    started.set(); release.wait(3)
                return {'code': 'SPEECH_STARTED' if op == 'speech' else 'SPEECH_STOPPED'}
            live.bridge.command = command
            a = threading.Thread(target=lambda: live.speak(live.clips['assistant_water'], 1, cause='chat:'+str(ticket)))
            b = threading.Thread(target=live.pause_chat)
            try:
                a.start(); self.assertTrue(started.wait(2)); b.start(); time.sleep(.02)
            finally:
                release.set(); a.join(3)
                if b.ident: b.join(3)
            self.assertFalse(a.is_alive()); self.assertFalse(b.is_alive())
            self.assertEqual(calls, ['speech', 'stop_speech'])
            self.assertEqual(live.conversation.status, 'quiet')

    def test_urgent_evidence_between_generation_and_voice_discards_reply(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); ticket, ctx = ready(live.conversation, 'Coffee?')
            def api(kind, value):
                live.policy.ingest(observation(3, ['visible_running_bath_tap', 'visible_water_near_rim']))
                return {'answer': {'speech': 'Do you like espresso?'}}
            live.api = api; live.chat_answer(1, ticket, ctx)
            self.assertFalse(live.bridge.calls)

    def test_jev_interprets_physical_request_while_chat_is_suspended(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d))
            ident = live.conversation.human('Please turn off the tap.', 'typed_user_input', 3, 3)
            live.conversation.interrupt(); calls = []
            live.api = lambda kind, value: {'answer': {'choice': 'faucet', 'human_goal': 'none'}}
            live.respond = lambda *args: calls.append(args)
            live.interpret(1, 'Please turn off the tap.', ident)
            self.assertEqual(calls[0][3], 'faucet')

    def test_stale_intent_cannot_move_character(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); ident = live.conversation.human('Follow me.', 'typed_user_input', 3, 3)
            live.conversation.human('Wait, explain jazz.', 'typed_user_input', 4, 4)
            live.api = lambda kind, value: {'answer': {'choice': 'follow', 'human_goal': 'none'}}
            live.interpret(1, 'Follow me.', ident)
            self.assertFalse(live.bridge.calls)

    def test_low_priority_keys_allow_chat_but_phone_and_water_yield(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); live.policy.active = 'notice_keys'
            self.assertFalse(live.chat_blocked())
            live.policy.current['human_activity'] = 'phone_at_ear'
            self.assertTrue(live.chat_blocked())
            live.policy.current['human_activity'] = 'unspecified'
            live.policy.active = 'notice_water'
            self.assertTrue(live.chat_blocked())

    def test_casual_generator_does_not_receive_hazard_ledger_or_task_chatter(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); ticket, ctx = ready(live.conversation, 'Why do stars twinkle?')
            ctx['turns'].insert(0, {'role': 'human', 'text': 'Find my keys.', 'purpose': 'task'})
            ctx['turns'].insert(1, {'role': 'assistant', 'text': 'I cannot see the keys.', 'purpose': 'task'})
            seen = []
            def api(kind, value):
                seen.append(value)
                live.conversation.pause()  # Inspect inputs without generating audio.
                return {'answer': {'speech': 'Air turbulence makes the light shimmer.'}}
            live.api = api; live.chat_answer(1, ticket, ctx)
            self.assertNotIn('observed_state', seen[0])
            self.assertNotIn('pending_tasks', seen[0])
            self.assertEqual(len(seen[0]['conversation']), 1)
            self.assertEqual(seen[0]['current_observation'], live.policy.current)

    def test_practical_request_does_not_receive_unrelated_casual_history(self):
        with tempfile.TemporaryDirectory() as d:
            live = self.live(Path(d)); ticket, ctx = ready(live.conversation, 'Help me find my keys.')
            ctx['task_request'] = True
            ctx['turns'].insert(0, {'role': 'human', 'text': 'I enjoy Python and music.', 'purpose': 'casual'})
            seen = []
            def api(kind, value):
                seen.append(value); live.conversation.pause()
                return {'answer': {'speech': 'I cannot see your keys here.'}}
            live.api = api; live.chat_answer(1, ticket, ctx)
            self.assertEqual(seen[0]['mode'], 'task')
            self.assertEqual(seen[0]['human_request'], 'Help me find my keys.')
            self.assertEqual(seen[0]['conversation'], [])
            self.assertEqual(seen[0]['current_observation'], live.policy.current)


if __name__ == '__main__':
    unittest.main()
