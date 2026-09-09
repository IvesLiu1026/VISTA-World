"""Prevent material routing from turning controls and containers into fabric."""
import unittest

from runtime.vista_home_materials_r4.bindings import match_slot, resolve_rule


class MaterialRoutingTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            'bindings': {'PR_Linen':'Canvas','R3_CharcoalWeave':'Cloth','PR_OakFloor1':'Oak'},
            'overrides': [
                {'label_contains':'computer','slots':['R3_CharcoalWeave'],'profile':'ABS'},
                {'label_contains':'basket','slots':['PR_Linen'],'profile':None},
            ],
        }

    def test_computer_keycaps_remain_hard_plastic(self):
        self.assertEqual(resolve_rule('PR_computer', 'R3_CharcoalWeave_2', self.plan), 'ABS')

    def test_backpack_keeps_its_fabric(self):
        self.assertEqual(resolve_rule('PR_backpack', 'R3_CharcoalWeave', self.plan), 'Cloth')

    def test_woven_basket_keeps_existing_rib_material(self):
        self.assertIsNone(resolve_rule('PR_laundry_basket', 'PR_Linen', self.plan))

    def test_book_cover_can_receive_canvas(self):
        self.assertEqual(resolve_rule('PR_living_table', 'PR_Linen.001', self.plan), 'Canvas')

    def test_partial_slot_name_does_not_bind(self):
        self.assertIsNone(resolve_rule('PR_floor', 'PR_OakFloor10', self.plan))

    def test_unrelated_external_asset_is_not_matched(self):
        self.assertIsNone(match_slot('External_PR_Linen', self.plan['bindings']))

    def test_numbered_import_suffix_is_supported(self):
        self.assertEqual(match_slot('PR_OakFloor1_17', self.plan['bindings']), 'PR_OakFloor1')


if __name__ == '__main__':
    unittest.main()
