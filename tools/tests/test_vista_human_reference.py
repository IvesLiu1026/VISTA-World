"""Support estimates must reject airborne and sliding feet, regardless of phase."""
import unittest
from tools.blender.vista_villa_r1.contact_reference import cycle_contacts, support_confidence


class HumanReferenceTests(unittest.TestCase):
    def test_grounded_stationary_heel_and_swing(self):
        self.assertEqual(support_confidence(7, 7, 0), 1)
        self.assertEqual(support_confidence(12, 7, 0), 0)
        self.assertEqual(support_confidence(7, 7, 150), 0)
        self.assertGreater(support_confidence(8.5, 7, 10), .5)

    def test_phase_shift_changes_contact_instead_of_using_fixed_clock(self):
        stance = [(2., 0.)]*12
        swing = [(10., 130.)]*12
        left = stance+swing; right = swing+stance
        a = cycle_contacts([left+[left[0]], right+[right[0]]])
        shift = 7
        rotated = [s[shift:]+s[:shift] for s in [left, right]]
        b = cycle_contacts([s+[s[0]] for s in rotated])
        self.assertEqual(a[0], a[-1])
        self.assertEqual(b[0], b[-1])
        self.assertEqual(a[shift:-1]+a[:shift], b[:-1])
        self.assertEqual(a[6], [1, 0])
        self.assertEqual(a[18], [0, 1])

    def test_invalid_recordings_fail(self):
        for data in [[[(0, 0)]], [[(float('nan'), 0)]*3]]:
            with self.assertRaises(ValueError):
                cycle_contacts(data)


if __name__ == '__main__':
    unittest.main()
