import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

import route_tool as tool
from route_history import request_key
from test_route_tool import build, FSDS, Server


def configurations():
    first, second = build(), build()
    second['data']['UnladenMass'] = 500
    second['data']['FuelCapacity']['Main'] = 16
    return [dict(raw=json.dumps(first), name='Explorer', cargo=2, reserve=1),
            dict(raw=json.dumps(second), name='Transfer ship', cargo=7, reserve=3)]


class PerLegTests(unittest.TestCase):
    def test_different_ships_and_boundary_arrival_departure_remain_distinct(self):
        configs, server = configurations(), Server()
        info = tool.plan(configs[0]['raw'], ['A', 'B', 'C'], tool.Options(already_supercharged=True),
                         http=server, fsds=FSDS, leg_configs=configs)
        self.assertTrue(info['complete'], info['reason'])
        self.assertEqual([r['tank_size'] for r in server.requests], [32, 16])
        self.assertEqual([r['base_mass'] for r in server.requests], [280.63, 500.63])
        self.assertEqual([r['cargo'] for r in server.requests], [2, 7])
        self.assertEqual([r['reserve_size'] for r in server.requests], [1, 3])
        self.assertEqual([r['is_supercharged'] for r in server.requests], [1, 0])
        self.assertEqual([r['ship_build'] for r in server.requests], [c['raw'] for c in configs])
        boundary = info['rows'][1]
        self.assertEqual((boundary['ship_name'], boundary['departure_ship']), ('Explorer', 'Transfer ship'))
        self.assertEqual((boundary['cargo'], boundary['departure_cargo']), (2, 7))
        self.assertEqual((boundary['fuel_in_tank'], boundary['departure_fuel']), (1.25, 16))
        self.assertEqual(info['segments'][1]['ship_name'], 'Transfer ship')

    def test_invalid_later_build_or_reserve_prevents_even_system_resolution(self):
        for invalid in ('reserve', 'drive', 'mass', 'cargo'):
            configs = configurations()
            if invalid == 'reserve':
                configs[1]['reserve'] = 16
            elif invalid == 'cargo':
                configs[1]['cargo'] = -1
            else:
                raw = json.loads(configs[1]['raw'])
                if invalid == 'drive':
                    raw['data']['Modules'][0]['Item'] = 'unknown'
                else:
                    raw['data']['UnladenMass'] = None
                configs[1]['raw'] = json.dumps(raw)
            calls = []
            info = tool.plan(configs[0]['raw'], ['A', 'B', 'C'], tool.Options(),
                             http=lambda *args: calls.append(args), fsds=FSDS, leg_configs=configs)
            self.assertFalse(info['complete'])
            self.assertEqual(info['failed_segment'], 2)
            self.assertEqual(info['rows'], [])
            self.assertEqual(calls, [])

    def test_later_route_failure_preserves_first_ship_only(self):
        configs, server = configurations(), Server(fail_leg=2)
        info = tool.plan(configs[0]['raw'], ['A', 'B', 'C'], tool.Options(),
                         http=server, fsds=FSDS, leg_configs=configs)
        self.assertFalse(info['complete'])
        self.assertEqual([row['ship_name'] for row in info['rows']], ['Explorer', 'Explorer'])
        self.assertFalse(info['rows'][-1]['full_tank_start'])
        self.assertEqual(info['rows'][-1]['departure_ship'], '')

    def test_fingerprint_contains_every_leg_build_cargo_and_reserve(self):
        configs = configurations()
        key = request_key(configs[0]['raw'], ['A', 'B', 'C'], tool.Options(), configs)
        for field, value in (('raw', configs[0]['raw']), ('cargo', 4), ('reserve', 5)):
            changed = copy.deepcopy(configs)
            changed[1][field] = value
            self.assertNotEqual(request_key(configs[0]['raw'], ['A', 'B', 'C'], tool.Options(), changed), key)
        renamed = copy.deepcopy(configs)
        renamed[1]['name'] = 'A new favourite name'
        self.assertEqual(request_key(configs[0]['raw'], ['A', 'B', 'C'], tool.Options(), renamed), key)

    def test_csv_names_per_leg_and_escapes_formula_favourite(self):
        configs, server = configurations(), Server()
        configs[1]['name'] = '=unsafe'
        info = tool.plan(configs[0]['raw'], ['A', 'B', 'C'], tool.Options(),
                         http=server, fsds=FSDS, leg_configs=configs)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legs.csv'
            tool.export_csv(path, info, language='en')
            with path.open(encoding='utf-8-sig', newline='') as file:
                rows = list(csv.reader(file))
        header, boundary = rows[6], rows[8]
        self.assertEqual(boundary[header.index('Leg build')], 'Explorer')
        self.assertEqual(boundary[header.index('Departure build')], "'=unsafe")
