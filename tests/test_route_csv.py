import csv
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import route_csv
import route_tool as tool
from test_route_tool import build, FSDS, Server


SPANSH = ('"System Name","Distance","Distance Remaining","Fuel Left","Fuel Used","Refuel","Neutron Star"\n'
          '"A","0","200","32","0","Yes","No"\n'
          '"B","100","100","27","5","No","Yes"\n'
          '"A","100","0","22","5","No","No"\n')


class RouteCsvTests(unittest.TestCase):
    def round_trip(self, info, language='zh'):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'route.csv'
            tool.export_csv(path, info, language=language)
            return route_csv.import_csv(path), path.read_text(encoding='utf-8-sig')

    def test_spansh_seven_columns_keep_order_duplicates_flags_and_unknowns(self):
        info = route_csv.parse_csv(SPANSH)
        self.assertEqual([r['name'] for r in info['rows']], ['A', 'B', 'A'])
        self.assertTrue(info['rows'][0]['must_refuel'])
        self.assertTrue(info['rows'][1]['has_neutron'])
        self.assertIsNone(info['rows'][1]['must_inject'])
        self.assertFalse(info['complete'])
        self.assertFalse(info['import_state_known'])
        self.assertIsNone(info['full_tank_each_segment'])
        self.assertNotIn('x', info['rows'][0])
        self.assertEqual(info['rows'][0]['ship_name'], '')

    def test_bilingual_native_roundtrip_preserves_state_ships_boundaries_and_coordinates(self):
        from test_route_legs import configurations
        configs = configurations()
        info = tool.plan(configs[0]['raw'], ['A', 'B', 'C'], tool.Options(), http=Server(),
                         fsds=FSDS, leg_configs=configs)
        info['rows'][0].update(x=-1.234567, y=3, z=4.5)
        for language in ('zh', 'en'):
            restored, _ = self.round_trip(info, language)
            self.assertTrue(restored['complete'])
            self.assertTrue(restored['import_state_known'])
            self.assertEqual(restored['rows'][0]['x'], -1.234567)
            self.assertEqual(restored['rows'][1]['departure_ship'], 'Transfer ship')
            self.assertEqual(restored['rows'][1]['ship_name'], 'Explorer')
            self.assertEqual(restored['rows'][1]['departure_fuel'], 16)
            self.assertTrue(restored['rows'][1]['full_tank_start'])
            self.assertTrue(restored['rows'][1]['ship_change'])
            self.assertEqual(restored['segments'][1]['source'], 'B')

    def test_partial_and_unknown_stay_noncomplete_on_reexport(self):
        info = tool.plan(json.dumps(build()), ['A', 'B', 'C'], tool.Options(), http=Server(fail_leg=2), fsds=FSDS)
        restored, text = self.round_trip(info)
        self.assertFalse(restored['complete'])
        self.assertEqual(restored['failed_segment'], 2)
        self.assertEqual(restored['planned_segments'], 2)
        unknown, _ = self.round_trip(route_csv.parse_csv(SPANSH))
        self.assertFalse(unknown['complete'])
        self.assertFalse(unknown['import_state_known'])
        # Older native CSVs without state metadata cannot prove completeness.
        legacy = '\n'.join(text.splitlines()[:-1])
        self.assertFalse(route_csv.parse_csv(legacy)['import_state_known'])

    def test_formula_escaping_is_reversible_and_not_executed(self):
        info = tool.plan(json.dumps(build()), ['A', 'B'], tool.Options(), http=Server(), fsds=FSDS)
        for name in ('=formula', '+name', '-name', '@name', "'=literal", "''literal"):
            info['rows'][0]['name'] = name
            restored, text = self.round_trip(info)
            self.assertEqual(restored['rows'][0]['name'], name)
        # Spansh input is not assumed to use this application's escape scheme.
        self.assertEqual(route_csv.parse_csv(SPANSH.replace('"B"', '"\'=literal"'))['rows'][1]['name'], "'=literal")

    def test_bad_headers_numbers_flags_rows_and_metadata_are_rejected(self):
        for text in ('', 'Name,Value\nA,1', SPANSH.replace('"Fuel Used"', '"Fuel Left"'),
                     SPANSH.replace('"100"', '"NaN"'), SPANSH.replace('"Yes"', '"Maybe"'),
                     SPANSH.replace('"27","5"', '"27"'), SPANSH.replace('"B"', '"Bad\nName"')):
            with self.subTest(text=text[:50]), self.assertRaises(ValueError):
                route_csv.parse_csv(text)
        info = tool.plan(json.dumps(build()), ['A', 'B'], tool.Options(), http=Server(), fsds=FSDS)
        _, text = self.round_trip(info)
        with self.assertRaises(ValueError):
            route_csv.parse_csv(text.replace('4.12', '8.12', 1))

    def test_file_size_row_limit_utf8_and_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'route.csv'
            path.write_text(SPANSH, encoding='utf-8-sig')
            self.assertEqual(len(route_csv.import_csv(path)['rows']), 3)
            with patch('route_csv.MAX_BYTES', 10), self.assertRaises(ValueError):
                route_csv.import_csv(path)
            path.write_bytes(b'\xff\xff')
            with self.assertRaises(ValueError):
                route_csv.import_csv(path)
        with patch('route_csv.MAX_ROWS', 2), self.assertRaises(ValueError):
            route_csv.parse_csv(SPANSH)
        stop = threading.Event()
        stop.set()
        with self.assertRaises(InterruptedError):
            route_csv.parse_csv(SPANSH, stop)
