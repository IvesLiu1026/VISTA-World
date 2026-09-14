import unittest
from runtime.vista_six_spaces.layout import entity_transform, port_contract, room_at, transform


class SixSpacePlacementTests(unittest.TestCase):
    def test_two_floors_do_not_complete_entry_goal_upstairs(self):
        self.assertEqual(room_at([1150, -200, 85]), 'home.r1/room.entry_hall')
        self.assertEqual(room_at([1150, -200, 405]), 'outside')
        self.assertEqual(room_at([1250, -1000, 405]), 'home.r1/room.bathroom_laundry')
        self.assertEqual(room_at([1250, -1000, 85]), 'home.r1/room.kitchen_dining')

    def test_portal_rotation_preserves_reach_distance(self):
        door = dict(short_id='bedroom_door', hinge_cm=[-159, -251, 0], control_cm=[-166.3, -161, 102])
        offset, yaw = entity_transform(door)
        self.assertEqual(transform(door['hinge_cm'], offset, yaw), [400, -809, 320])
        self.assertEqual(transform(door['control_cm'], offset, yaw), [490, -801.7, 422])

    def test_world_points_move_but_grasp_offsets_and_event_gold_do_not(self):
        entity = dict(short_id='water_jug', room='home.r1/room.kitchen_dining',
                      control_cm=[348, 282, 89], grip_offset_cm=[12.4, 0, 13],
                      capacity_cm=[35, 34, 28], anchors={'top': [348, 282, 89]})
        event = dict(event_id='mmg_040', success_conditions=[{'type': 'interaction', 'affordance': 'inspect'}])
        original = dict(entities=[entity], events=[event])
        moved = port_contract(original)
        self.assertEqual(moved['entities'][0]['control_cm'], [1098, -918, 89])
        self.assertEqual(moved['entities'][0]['grip_offset_cm'], entity['grip_offset_cm'])
        self.assertEqual(moved['entities'][0]['capacity_cm'], entity['capacity_cm'])
        self.assertEqual(moved['events'], original['events'])
        self.assertEqual(original['entities'][0]['control_cm'], [348, 282, 89])


if __name__ == '__main__':
    unittest.main()
