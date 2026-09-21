import copy
import unittest

from runtime.vista_live.research_audit import audit_trace, audit_inputs


class EpisodeEvidence(unittest.TestCase):
    def trace(self):
        return [{'session_id': 'one', 'scene_epoch': 1, 'clock_s': i * .2,
                 'third_person': False, 'player_cm': [i * 20, 0, 0], 'frame_time_s': .03,
                 'targets': [{'short_id': 'stove', 'state': {'active': i < 4}}]} for i in range(8)]

    def job(self):
        return {'status': 'completed', 'view': 'first', 'assistant': 'live',
                'interventions': [{'target': 'stove', 'status': 'committed'}]}

    def test_requires_both_state_transition_and_committed_receipt(self):
        self.assertTrue(audit_trace(self.trace(), self.job(), ['stove'])['passed'])
        trace = self.trace()
        for frame in trace: frame['targets'][0]['state']['active'] = True
        self.assertFalse(audit_trace(trace, self.job(), ['stove'])['passed'])
        job = self.job(); job['interventions'][0]['status'] = 'reaching'
        self.assertFalse(audit_trace(self.trace(), job, ['stove'])['passed'])

    def test_actor_completion_cannot_hide_camera_switch_teleport_or_reset(self):
        for patch in ({'third_person': True}, {'player_cm': [9999, 0, 0]}, {'scene_epoch': 2}):
            trace = self.trace(); trace[4].update(copy.deepcopy(patch))
            with self.subTest(patch=patch):
                self.assertFalse(audit_trace(trace, self.job())['passed'])

    def test_no_intervention_control_rejects_a_committed_assistant_action(self):
        job = self.job(); job['assistant'] = 'off'
        self.assertFalse(audit_trace(self.trace(), job)['passed'])
        job['interventions'] = []
        self.assertTrue(audit_trace(self.trace(), job)['passed'])

    def test_empty_or_single_frame_does_not_pass(self):
        self.assertFalse(audit_trace([], self.job())['passed'])
        self.assertFalse(audit_trace(self.trace()[:1], self.job())['passed'])

    def test_control_audit_counts_calls_inside_episode_but_separates_later_manual_use(self):
        from pathlib import Path
        packet = {'session_id': 'one', 'scene_epoch': 1}
        later = {'id': 'manual', 'kind': 'research', 'wall_time': 21, 'input': packet}
        result = audit_inputs([later], Path('/unused'), ('one', 1), (10, 20))
        self.assertEqual(result['request_count'], 0)
        self.assertFalse(result['failures'])
        self.assertEqual(result['outside_episode_request_ids'], ['manual'])
        inside = {**later, 'id': 'inside', 'wall_time': 15}
        result = audit_inputs([inside, later], Path('/unused'), ('one', 1), (10, 20))
        self.assertEqual(result['request_count'], 1)
        self.assertTrue(result['failures'])  # Invalid inside packets never disappear.
        missing = {k: v for k, v in later.items() if k != 'wall_time'}
        self.assertTrue(audit_inputs([missing], Path('/unused'), ('one', 1), (10, 20))['failures'])


if __name__ == '__main__': unittest.main()
