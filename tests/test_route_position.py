import unittest

from route_position import RoutePosition


class RoutePositionTests(unittest.TestCase):
    def position(self, names):
        position = RoutePosition()
        position.set_route([dict(name=name) for name in names])
        return position

    def test_unique_positions_and_next_are_canonical(self):
        position = self.position(['Z', 'B', 'A'])
        self.assertEqual(position.match(' z '), 0)
        self.assertEqual(position.next_system, 'B')
        self.assertTrue(position.should_copy)
        position.mark_copied()
        self.assertFalse(position.should_copy)
        self.assertEqual(position.match('B'), 1)
        self.assertEqual(position.next_system, 'A')
        self.assertTrue(position.should_copy)
        self.assertEqual(position.match('A'), 2)
        self.assertIsNone(position.next_system)
        self.assertFalse(position.should_copy)

    def test_off_route_is_silent_and_does_not_recopy_old_position(self):
        position = self.position(['A', 'B', 'C'])
        position.match('A')
        position.mark_copied()
        self.assertIsNone(position.match('Not in route'))
        self.assertFalse(position.ambiguous)
        self.assertFalse(position.should_copy)
        position.match('A')
        self.assertFalse(position.should_copy)

    def test_repeated_system_needs_confirmation_or_unambiguous_progress(self):
        position = self.position(['A', 'B', 'A', 'C'])
        self.assertIsNone(position.match('A', ('file', '1')))
        self.assertTrue(position.ambiguous)
        self.assertFalse(position.choose(1, 'A'))
        self.assertTrue(position.choose(0, 'A'))
        self.assertEqual(position.match('A', ('file', '1')), 0)
        self.assertEqual(position.match('B', ('file', '2')), 1)
        self.assertEqual(position.match('A', ('file', '3')), 2)
        self.assertEqual(position.next_system, 'C')
        self.assertEqual(position.match('A', ('file', '3')), 2)

    def test_new_record_at_same_repeated_name_is_not_guessed(self):
        position = self.position(['A', 'B', 'A', 'C'])
        position.match('A', ('file', '1'))
        position.choose(0, 'A')
        self.assertIsNone(position.match('A', ('file', '2')))
        self.assertTrue(position.ambiguous)
        self.assertFalse(position.should_copy)

    def test_new_route_resets_copy_history_and_malformed_next_is_not_copied(self):
        position = self.position(['A', 'B'])
        position.match('A')
        position.mark_copied()
        position.set_route([dict(name='A'), dict(name='C')])
        position.match('A')
        self.assertTrue(position.should_copy)
        position.set_route([dict(name='A'), dict(name='bad\nname')])
        position.match('A')
        self.assertFalse(position.should_copy)
