import copy
from pathlib import Path
import tempfile
import unittest

from route_history import RouteHistory, request_key, build_key, find_complete
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from route_tool import Options


def parameters():
    return dict(selected='Explorer', source='A', destination='B', cargo='0', reserve='0',
                algorithm='优先少跳', injection='不使用', supercharge=True, already_supercharged=False,
                exclude_secondary=False, refuel_every_scoopable=False)


def result(complete=True):
    return dict(complete=complete, rows=[dict(name='A', has_neutron=True, full_tank_start=True)],
                segments=[dict(number=1, source='A', destination='B', job='test')], planned_segments=1,
                full_tank_each_segment=True, reason='航线规划完成' if complete else 'Stopped', failed_segment=None)


class RouteHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'history.json'
        self.store = RouteHistory(self.path)

    def test_five_snapshots_survive_restart_without_mutation(self):
        entries = []
        info, values = result(), parameters()
        for i in range(7):
            entries = self.store.add(entries, str(i), 'ship', values, ['C'], info)
        info['rows'].clear()
        values['source'] = 'changed'
        saved = RouteHistory(self.path).load()
        self.assertEqual([e['key'] for e in saved], ['6', '5', '4', '3', '2'])
        self.assertEqual(saved[0]['parameters']['source'], 'A')
        self.assertTrue(saved[0]['result']['rows'][0]['has_neutron'])
        self.assertTrue(saved[0]['result']['full_tank_each_segment'])

    def test_partial_results_remain_partial(self):
        self.store.add([], 'key', 'ship', parameters(), [], result(False))
        self.assertFalse(self.store.load()[0]['result']['complete'])

    def test_corrupt_history_is_not_overwritten(self):
        for text in ('{', '[]', '{"version":1,"entries":[{}]}'):
            self.path.write_text(text, encoding='utf-8')
            with self.assertRaises(ValueError):
                self.store.add([], 'key', 'ship', parameters(), [], result())
            self.assertEqual(self.path.read_text(encoding='utf-8'), text)

    def test_request_identity_includes_build_points_and_every_option(self):
        raw = '{"b":2,"a":1}'
        options = Options().validate()
        initial = request_key(raw, ['A', 'B'], options)
        self.assertEqual(initial, request_key('{ "a": 1, "b": 2 }', [' a ', 'b'], options))
        self.assertNotEqual(initial, request_key('{"a":2}', ['A', 'B'], options))
        self.assertNotEqual(initial, request_key(raw, ['A', 'C', 'B'], options))
        for key, value in dict(cargo=1, reserve=1, supercharge=False, already_supercharged=True,
                               injection='always', algorithm='pessimistic', exclude_secondary=True,
                               refuel_every_scoopable=True).items():
            changed = copy.deepcopy(options)
            setattr(changed, key, value)
            self.assertNotEqual(initial, request_key(raw, ['A', 'B'], changed.validate()), key)
        self.assertEqual(build_key(raw), build_key('{"a":1,"b":2}'))
        with patch('route_ship.DATA_REVISION', 'different facts'):
            self.assertNotEqual(initial, request_key(raw, ['A', 'B'], options))

    def test_auto_reuse_requires_matching_complete_recent_result(self):
        entries = self.store.add([], 'key', 'ship', parameters(), [], result())
        now = datetime.now(timezone.utc)
        self.assertIsNotNone(find_complete(entries, 'key', now))
        self.assertIsNone(find_complete(entries, 'other key', now))
        self.assertIsNone(find_complete(entries, 'key', now + timedelta(days=2)))
        self.assertIsNone(find_complete(entries, 'key', now - timedelta(days=2)))
        entries[0]['result']['complete'] = False
        self.assertIsNone(find_complete(entries, 'key', now))
        entries[0]['result']['complete'] = True
        entries[0]['result']['segments'] = []
        self.assertIsNone(find_complete(entries, 'key', now))
