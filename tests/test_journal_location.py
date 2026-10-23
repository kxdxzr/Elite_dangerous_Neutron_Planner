import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from journal_location import read_current_system, JournalFollower


def event(kind, system='Sol', timestamp='2026-10-23T12:00:00Z'):
    return dict(timestamp=timestamp, event=kind, StarSystem=system)


class JournalLocationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)

    def write(self, name, events, mtime=100):
        path = self.folder / name
        path.write_text('\n'.join(json.dumps(e) for e in events) + '\n', encoding='utf-8')
        os.utime(path, (mtime, mtime))
        return path

    def test_last_confirmed_location_ignores_jump_destination_and_partial_line(self):
        path = self.write('Journal.2026-10-23T120000.01.log',
                          [event('Location'), event('FSDJump', 'Achenar'), event('StartJump', 'Colonia')])
        with path.open('ab') as file:
            file.write(b'{"event":"FSDJump","StarSystem":"unfinished')
        found = read_current_system(self.folder)
        self.assertEqual(found.system, 'Achenar')
        self.assertEqual(found.filename, path.name)
        self.assertEqual(found.timestamp, '2026-10-23T12:00:00Z')

    def test_carrier_jump_and_unicode_names(self):
        self.write('Journal.2026-10-23T120000.01.log', [event('Location'), event('CarrierJump', '测试星系')])
        self.assertEqual(read_current_system(self.folder).system, '测试星系')

    def test_only_latest_session_not_previous_commander(self):
        self.write('Journal.2026-10-22T120000.01.log', [event('Location', 'Old session')], mtime=100)
        self.write('Journal.2026-10-23T120000.01.log', [{'event': 'Fileheader'}], mtime=200)
        with self.assertRaisesRegex(ValueError, '最新游戏会话'):
            read_current_system(self.folder)

    def test_numbered_parts_of_same_session_can_supply_position(self):
        self.write('Journal.2026-10-22T120000.01.log', [event('Location', 'Wrong session')], mtime=50)
        first = self.write('Journal.2026-10-23T120000.01.log', [event('Location', 'Sol')], mtime=100)
        self.write('Journal.2026-10-23T120000.02.log', [{'event': 'Fileheader'}], mtime=200)
        self.assertEqual(read_current_system(self.folder).filename, first.name)

    def test_missing_folder_and_missing_journals(self):
        with self.assertRaisesRegex(ValueError, '未找到'):
            read_current_system(self.folder / 'missing')
        (self.folder / 'Status.json').write_text('{"StarSystem":"Not Journal"}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '没有 Journal'):
            read_current_system(self.folder)

    def test_invalid_location_never_silently_uses_older_position(self):
        for invalid in (event('Location', ''), event('Location', 'A\nB'), event('Location', 'Sol', 'bad')):
            with self.subTest(invalid=invalid):
                self.write('Journal.2026-10-23T120000.01.log', [event('Location'), invalid])
                with self.assertRaisesRegex(ValueError, '位置信息无效'):
                    read_current_system(self.folder)

    def test_bom_and_reverse_chunk_boundary(self):
        path = self.write('Journal.161023120000.01.log', [event('Location', 'BOM system')])
        path.write_bytes(b'\xef\xbb\xbf' + path.read_bytes())
        with patch('journal_location.CHUNK_BYTES', 17):
            self.assertEqual(read_current_system(self.folder).system, 'BOM system')

    def test_scan_and_line_limits(self):
        self.write('Journal.2026-10-23T120000.01.log', [event('Location'), {'event': 'Other', 'data': 'x' * 1000}])
        with patch('journal_location.MAX_SCAN_BYTES', 100):
            with self.assertRaisesRegex(ValueError, '日志过大'):
                read_current_system(self.folder)
        with patch('journal_location.MAX_LINE_BYTES', 100):
            with self.assertRaisesRegex(ValueError, '日志行过长'):
                read_current_system(self.folder)

    def test_follower_reads_only_appends_and_retains_partial_line(self):
        path = self.write('Journal.2026-10-23T120000.01.log', [event('Location', 'A')])
        reader = JournalFollower(self.folder)
        with patch('journal_location.read_current_system', wraps=read_current_system) as snapshot:
            self.assertEqual(reader.poll().system, 'A')
            self.assertEqual(reader.poll().system, 'A')
            self.assertEqual(reader.last_read_bytes, 0)
            data = json.dumps(event('FSDJump', 'B')).encode('utf-8')
            with path.open('ab') as file:
                file.write(data[:20])
            self.assertEqual(reader.poll().system, 'A')
            self.assertEqual(reader.last_read_bytes, 20)
            with path.open('ab') as file:
                file.write(data[20:] + b'\n')
            self.assertEqual(reader.poll().system, 'B')
            self.assertEqual(reader.last_read_bytes, len(data) - 20 + 1)
            snapshot.assert_called_once()

    def test_follower_handles_partial_line_present_at_startup(self):
        path = self.write('Journal.2026-10-23T120000.01.log', [event('Location', 'A')])
        data = json.dumps(event('FSDJump', 'B')).encode('utf-8')
        with path.open('ab') as file:
            file.write(data[:15])
        reader = JournalFollower(self.folder)
        self.assertEqual(reader.poll().system, 'A')
        with path.open('ab') as file:
            file.write(data[15:] + b'\n')
        self.assertEqual(reader.poll().system, 'B')

    def test_follower_switches_sessions_without_carrying_old_position(self):
        self.write('Journal.2026-10-23T120000.01.log', [event('Location', 'A')], mtime=100)
        clock = [0]
        reader = JournalFollower(self.folder, clock=lambda: clock[0])
        self.assertEqual(reader.poll().system, 'A')
        latest = self.write('Journal.2026-10-23T130000.01.log', [dict(event='Fileheader')], mtime=200)
        clock[0] = 11
        self.assertIsNone(reader.poll())
        with latest.open('ab') as file:
            file.write((json.dumps(event('Location', 'B')) + '\n').encode('utf-8'))
        self.assertEqual(reader.poll().system, 'B')

    def test_follower_recovers_from_truncation_and_ignores_start_jump(self):
        path = self.write('Journal.2026-10-23T120000.01.log',
                          [event('Location', 'A'), dict(event='Other', padding='x' * 1000)])
        reader = JournalFollower(self.folder)
        self.assertEqual(reader.poll().system, 'A')
        path.write_text(json.dumps(event('Location', 'B')) + '\n', encoding='utf-8')
        self.assertEqual(reader.poll().system, 'B')
        with path.open('ab') as file:
            file.write((json.dumps(event('StartJump', 'C')) + '\n').encode('utf-8'))
        self.assertEqual(reader.poll().system, 'B')

    def test_follower_invalid_position_clears_previous_until_valid_record(self):
        path = self.write('Journal.2026-10-23T120000.01.log', [event('Location', 'A')])
        reader = JournalFollower(self.folder)
        reader.poll()
        with path.open('ab') as file:
            file.write((json.dumps(event('FSDJump', '')) + '\n').encode('utf-8'))
        self.assertIsNone(reader.poll())
        with path.open('ab') as file:
            file.write((json.dumps(event('CarrierJump', 'C')) + '\n').encode('utf-8'))
        self.assertEqual(reader.poll().system, 'C')
