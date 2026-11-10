import json
import os
from pathlib import Path
import tempfile
import unittest

from journal_health import read_current_health
from journal_location import JournalFollower


def loadout(health=.9, ident=1):
    return dict(event='Loadout', ShipID=ident, Ship='asp', timestamp='2026-10-23T12:00:00Z',
                Modules=[dict(Slot='FrameShiftDrive', Item='int_hyperdrive_size5_class5', Health=health)])


class JournalHealthTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)

    def write(self, records, session='2026-10-23T120000', part='01', mtime=100):
        path = self.folder / f'Journal.{session}.{part}.log'
        path.write_text('\n'.join(json.dumps(row) for row in records) + '\n', encoding='utf-8')
        os.utime(path, (mtime, mtime))
        return path

    def test_latest_health_and_ship_identity_are_kept_not_hull_health(self):
        record = loadout(.84, ident=7)
        record['HullHealth'] = 1
        self.write([loadout(), record])
        found = read_current_health(self.folder)
        self.assertEqual((found.value, found.ship_id, found.ship), (.84, 7, 'asp'))
        self.assertEqual(found.timestamp, record['timestamp'])

    def test_invalid_latest_health_never_falls_back(self):
        for value in (None, True, -1, 85, float('nan'), float('inf'), '0.9'):
            self.write([loadout(.99), loadout(value)])
            with self.subTest(value=value):
                self.assertIsNone(read_current_health(self.folder))
        record = loadout()
        record['Modules'].append(dict(record['Modules'][0]))
        self.write([loadout(), record])
        self.assertIsNone(read_current_health(self.folder))

    def test_new_session_never_reuses_old_ship_health_and_same_session_parts_work(self):
        self.write([loadout(.82)])
        self.write([dict(event='Fileheader')], part='02', mtime=200)
        self.assertEqual(read_current_health(self.folder).value, .82)
        self.write([dict(event='Fileheader')], session='2026-10-23T140000', mtime=300)
        self.assertIsNone(read_current_health(self.folder))

    def test_ship_module_and_repair_changes_clear_snapshot(self):
        for event in ('LoadGame', 'Commander', 'ShipyardSwap', 'ModuleSwap', 'RepairAll', 'AfmuRepairs'):
            self.write([loadout(), dict(event=event)])
            with self.subTest(event=event):
                self.assertIsNone(read_current_health(self.folder))

    def test_follower_updates_health_even_without_location_change(self):
        location = dict(event='Location', StarSystem='A', timestamp='2026-10-23T12:00:00Z')
        path = self.write([loadout(.9), location])
        reader = JournalFollower(self.folder)
        self.assertEqual(reader.poll().system, 'A')
        self.assertEqual(reader.fsd_health.value, .9)
        with path.open('a', encoding='utf-8') as file:
            file.write(json.dumps(loadout(.79)) + '\n')
        self.assertEqual(reader.poll().system, 'A')
        self.assertEqual(reader.fsd_health.value, .79)
        with path.open('a', encoding='utf-8') as file:
            file.write(json.dumps(dict(event='ShipyardSwap')) + '\n')
        reader.poll()
        self.assertIsNone(reader.fsd_health)
        reader.poll()
        self.assertEqual(reader.last_read_bytes, 0)

    def test_follower_partial_loadout_waits_and_truncation_clears_health(self):
        path = self.write([loadout(.9)])
        reader = JournalFollower(self.folder)
        reader.poll()
        data = (json.dumps(loadout(.8)) + '\n').encode('utf-8')
        with path.open('ab') as file:
            file.write(data[:15])
        reader.poll()
        self.assertEqual(reader.fsd_health.value, .9)
        with path.open('ab') as file:
            file.write(data[15:])
        reader.poll()
        self.assertEqual(reader.fsd_health.value, .8)
        path.write_text('{"event":"Fileheader"}\n', encoding='utf-8')
        reader.poll()
        self.assertIsNone(reader.fsd_health)
