import math
import unittest

from route_map import top_down, line_runs, View


class RouteMapGeometryTests(unittest.TestCase):
    def test_coordinates_are_signed_and_height_is_not_used(self):
        self.assertEqual(top_down(dict(x=-20, y=999, z=0)), (-20, 0))
        for value in (None, True, '3', math.nan, math.inf, 1e100):
            self.assertIsNone(top_down(dict(x=value, z=1)))
        self.assertIsNone(top_down(dict(x=1, y=2)))

    def test_missing_coordinates_break_instead_of_bridging_route(self):
        points = [(0, 0), (1, 2), None, (4, 5), None, (6, 7), (8, 9)]
        self.assertEqual(line_runs(points), [[(0, 0), (1, 2)], [(6, 7), (8, 9)]])
        self.assertEqual(line_runs([None, (0, 0), None]), [])

    def test_fit_preserves_aspect_ratio_and_z_points_up(self):
        view = View()
        view.fit([(0, 0), (100, 200)], 800, 600)
        a, b = view.project((0, 0)), view.project((100, 200))
        self.assertAlmostEqual((b[0] - a[0]) / (a[1] - b[1]), .5)
        self.assertLess(b[1], a[1])
        self.assertGreaterEqual(a[0], 50)
        self.assertGreaterEqual(b[1], 50)

    def test_zoom_keeps_pointer_world_position_and_single_point_fits(self):
        view = View()
        view.fit([(42, -8), (42, -8), None], 800, 600)
        self.assertEqual(view.project((42, -8)), (400, 300))
        view.zoom(1.2, 400, 300)
        self.assertEqual(view.project((42, -8)), (400, 300))
        view.fit([], 800, 600)
        self.assertEqual(view.project((0, 0)), (400, 300))
