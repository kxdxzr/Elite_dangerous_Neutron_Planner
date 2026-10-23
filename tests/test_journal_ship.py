import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import journal_ship
import route_ship
from test_route_tool import build, FSDS


def loadout():
    return dict(copy.deepcopy(build()['data']), event='Loadout', Ship='asp',
                ShipName='Explorer', ShipIdent='AB-12', timestamp='2026-10-23T12:00:00Z')


class JournalShipTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)

    def write(self, records, session='2026-10-23T120000', part='01', mtime=100):
        path = self.folder / f'Journal.{session}.{part}.log'
        path.write_text('\n'.join(json.dumps(r) for r in records) + '\n', encoding='utf-8')
        os.utime(path, (mtime, mtime))
        return path

    def test_offline_conversion_preserves_routing_and_excludes_private_fields(self):
        record = loadout()
        record.update(Commander='Private', FID='secret', HullValue=123, Rebuy=456)
        record['Modules'][0]['Engineering'] = dict(Engineer='Not needed', Modifiers=[
            dict(Label='FSDOptimalMass', Value=1700), dict(Label='MaxFuelPerJump', Value=5.5)])
        self.write([record])
        with patch('route_tool.http_json', side_effect=AssertionError('No networking')):
            found = journal_ship.read_current_ship(self.folder)
        parsed = route_ship.parse_ship(found.raw, FSDS)
        self.assertEqual(parsed['optimal_mass'], 1700)
        self.assertEqual(parsed['max_fuel_per_jump'], 5.5)
        self.assertEqual(parsed['range_boost'], 10.5)
        self.assertEqual(parsed['base_mass'], 280.63)
        self.assertEqual(route_ship.ship_identity(found.raw)['model'], 'Asp Explorer')
        self.assertNotIn('Private', found.raw)
        self.assertNotIn('secret', found.raw)
        self.assertNotIn('HullValue', found.raw)

    def test_latest_snapshot_and_same_session_parts_only(self):
        self.write([loadout()])
        self.write([dict(event='Fileheader')], part='02', mtime=200)
        self.assertEqual(journal_ship.read_current_ship(self.folder).timestamp, loadout()['timestamp'])
        self.write([dict(event='Fileheader')], session='2026-10-23T130000', mtime=300)
        with self.assertRaisesRegex(ValueError, '未找到完整配船'):
            journal_ship.read_current_ship(self.folder)

    def test_newer_mutation_blocks_old_snapshot_until_fresh_loadout(self):
        for event in ('ModuleBuy', 'EngineerCraft', 'ShipyardSwap', 'LoadGame'):
            self.write([loadout(), dict(event=event)])
            with self.assertRaisesRegex(ValueError, '配船已变更'):
                journal_ship.read_current_ship(self.folder)
            updated = loadout()
            updated['UnladenMass'] = 300
            self.write([loadout(), dict(event=event), updated])
            raw = journal_ship.read_current_ship(self.folder).raw
            self.assertEqual(route_ship.parse_ship(raw, FSDS)['base_mass'], 300.63)

    def test_incomplete_new_snapshot_never_falls_back(self):
        for key in ('UnladenMass', 'FuelCapacity', 'Modules', 'Ship', 'timestamp'):
            invalid = loadout()
            invalid.pop(key)
            self.write([loadout(), invalid])
            with self.subTest(key=key), self.assertRaises(ValueError):
                journal_ship.read_current_ship(self.folder)

    def test_strict_modules_and_engineering(self):
        for mutate in (
                lambda r: r['Modules'].append(copy.deepcopy(r['Modules'][0])),
                lambda r: r['Modules'][0].update(Engineering={}),
                lambda r: r['Modules'][0].update(Engineering=dict(Modifiers=[dict(Label='FSDOptimalMass', Value=True)])),
                lambda r: r['Modules'][0].update(Engineering=dict(Modifiers=[dict(Label='Other', Value=1)])),
                lambda r: r.update(timestamp='bad'),
                lambda r: r['FuelCapacity'].update(Reserve=None)):
            record = loadout()
            mutate(record)
            with self.assertRaises(ValueError):
                journal_ship.convert_loadout(record)

    def test_scan_budget_partial_lines_and_unknown_drive(self):
        path = self.write([loadout()])
        with path.open('ab') as file:
            file.write(b'{"event":"Loadout"')
        self.assertTrue(journal_ship.read_current_ship(self.folder).raw)
        self.write([loadout(), dict(event='Other', padding='x' * 1000)])
        with patch('journal_location.MAX_SCAN_BYTES', 100):
            with self.assertRaises(ValueError):
                journal_ship.read_current_ship(self.folder)
        record = loadout()
        record['Modules'][0]['Item'] = 'unknown_drive'
        raw = journal_ship.convert_loadout(record)
        with self.assertRaisesRegex(ValueError, 'Unsupported Frame Shift Drive'):
            route_ship.parse_ship(raw, FSDS)

    def test_history_deduplicates_by_commander_and_ship_id_not_name_or_mtime(self):
        first = dict(loadout(), ShipID=1)
        second = dict(loadout(), ShipID=2, ShipName='Explorer')
        updated = dict(first, UnladenMass=350, timestamp='2026-10-23T14:00:00Z')
        self.write([dict(event='Commander', FID='F1', Name='One'), first, second], mtime=900)
        self.write([dict(event='Commander', FID='F1', Name='One'), updated],
                   session='2026-10-23T140000', mtime=300)
        self.write([dict(event='Commander', FID='F2', Name='Two'), first],
                   session='2026-10-23T150000', mtime=400)
        report = journal_ship.read_ship_history(self.folder)
        self.assertEqual(len(report.ships), 3)
        by_key = {(s.commander_id, s.ship_id): s for s in report.ships}
        raw = by_key['F1', 1].snapshot.raw
        self.assertEqual(route_ship.parse_ship(raw, FSDS)['base_mass'], 350.63)
        self.assertNotIn('F1', raw)
        self.assertFalse(report.limited)

    def test_history_session_identity_never_leaks_and_parts_share_identity(self):
        record = dict(loadout(), ShipID=1)
        self.write([dict(event='LoadGame', FID='F1', Commander='One')])
        self.write([record], part='02', mtime=200)
        self.write([dict(record, ShipID=3)], session='2026-10-23T140000', mtime=300)
        report = journal_ship.read_ship_history(self.folder)
        self.assertEqual([(s.commander_id, s.ship_id) for s in report.ships], [('F1', 1)])
        self.assertEqual(report.skipped, 1)

    def test_history_invalid_latest_snapshot_does_not_restore_older_build(self):
        record = dict(loadout(), ShipID=1)
        invalid = dict(record, UnladenMass=None, timestamp='2026-10-23T14:00:00Z')
        self.write([dict(event='Commander', FID='F1', Name='One'), record])
        self.write([dict(event='Commander', FID='F1', Name='One'), invalid],
                   session='2026-10-23T140000', mtime=200)
        report = journal_ship.read_ship_history(self.folder)
        self.assertEqual(report.ships, ())
        self.assertEqual(report.skipped, 1)

    def test_history_limits_cancel_and_partial_lines(self):
        import threading
        record = dict(loadout(), ShipID=1)
        path = self.write([dict(event='Commander', FID='F1', Name='One'), record])
        with path.open('ab') as file:
            file.write(b'{"event":"Loadout"')
        self.assertEqual(len(journal_ship.read_ship_history(self.folder).ships), 1)
        with patch('journal_ship.MAX_HISTORY_BYTES', 30):
            report = journal_ship.read_ship_history(self.folder)
        self.assertEqual(report.ships, ())
        self.assertTrue(report.limited)
        stopped = threading.Event()
        stopped.set()
        with self.assertRaises(InterruptedError):
            journal_ship.read_ship_history(self.folder, stopped)
