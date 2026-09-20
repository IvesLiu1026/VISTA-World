import unittest
from runtime.vista_live.motion_audit import walking_continuity


def sample(clock, position, session='trial'):
    return {'native': {'clock_s': clock, 'player_cm': position, 'session_id': session}}


class ContinuityTests(unittest.TestCase):
    def test_normal_downstairs_motion_over_sixty_five_cm_is_continuous(self):
        frames=[sample(10,[0,0,100]),sample(10.404,[0,60.44,66.26])]
        self.assertTrue(walking_continuity(frames)['passed'])

    def test_teleport_is_rejected_even_with_changing_clock(self):
        result=walking_continuity([sample(1,[0,0,0]),sample(1.2,[100,0,0])])
        self.assertFalse(result['passed'])
        self.assertEqual(result['issues'][0]['reason'],'exceeds_walk_speed')

    def test_vertical_jump_and_unobserved_interval_are_rejected(self):
        for end in (sample(1.2,[0,0,100]),sample(2,[0,0,0])):
            self.assertFalse(walking_continuity([sample(1,[0,0,0]),end])['passed'])

    def test_repeated_stationary_sample_is_allowed_but_frozen_time_motion_is_not(self):
        a=sample(1,[0,0,0])
        self.assertTrue(walking_continuity([a,a])['passed'])
        self.assertFalse(walking_continuity([a,sample(1,[1,0,0])])['passed'])

    def test_reset_or_changed_session_cannot_be_hidden_by_small_displacement(self):
        a=sample(1,[0,0,0])
        for b in (sample(0,[0,0,0]),sample(1.1,[0,0,0],'other')):
            self.assertFalse(walking_continuity([a,b])['passed'])

    def test_empty_and_single_frame_are_not_evidence(self):
        for frames in ([],[sample(1,[0,0,0])]):
            self.assertFalse(walking_continuity(frames)['passed'])
