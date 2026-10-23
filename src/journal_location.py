"""Read a position from explicitly requested local Journal files; no networking."""
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import time

MAX_SCAN_BYTES = 16 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
MAX_LINE_BYTES = 1024 * 1024
LOCATION_EVENTS = {'Location', 'FSDJump', 'CarrierJump'}
JOURNAL_NAME = re.compile(r'Journal\.(.+)\.(\d+)\.log', re.I)


@dataclass(frozen=True)
class JournalLocation:
    system: str
    timestamp: str
    filename: str


def default_directory():
    # Only used on a button click, never enumerated automatically at startup.
    return str(Path.home() / 'Saved Games' / 'Frontier Developments' / 'Elite Dangerous')


def reverse_lines(file, budget):
    """Read backwards, ignoring an incomplete leading line at the scan limit."""
    file.seek(0, 2)
    position = file.tell()
    pending = b''
    while position and budget[0] > 0:
        size = min(position, CHUNK_BYTES, budget[0])
        position -= size
        budget[0] -= size
        file.seek(position)
        parts = (file.read(size) + pending).split(b'\n')
        pending = parts[0]
        for line in reversed(parts[1:]):
            if len(line) > MAX_LINE_BYTES:
                raise ValueError('日志行过长，无法安全读取当前位置。')
            if line.strip():
                yield line
        if len(pending) > MAX_LINE_BYTES:
            raise ValueError('日志行过长，无法安全读取当前位置。')
    if position == 0 and pending.strip():
        yield pending.removeprefix(b'\xef\xbb\xbf')


def journal_files(directory):
    folder = Path(directory)
    if not folder.is_dir():
        raise ValueError('未找到游戏日志文件夹，请选择 Journal 所在文件夹。')
    files = []
    for path in folder.iterdir():
        match = JOURNAL_NAME.fullmatch(path.name)
        if match and path.is_file():
            files.append((path.stat().st_mtime_ns, path, match.group(1), int(match.group(2))))
            if len(files) > 5000:
                raise ValueError('日志文件过多，请选择只含近期 Journal 的文件夹。')
    if not files:
        raise ValueError('文件夹中没有 Journal 日志，请先进入游戏或选择其他文件夹。')
    return files


def parse_location(line, filename):
    try:
        record = json.loads(line.decode('utf-8-sig'))
    except (ValueError, RecursionError):
        return None
    if not isinstance(record, dict) or record.get('event') not in LOCATION_EVENTS:
        return None
    system, timestamp = record.get('StarSystem'), record.get('timestamp')
    if (not isinstance(system, str) or not system.strip() or len(system) > 256
            or any(ord(c) < 32 for c in system) or not isinstance(timestamp, str)):
        raise ValueError('日志中的位置信息无效，请等待游戏写入新的位置记录。')
    try:
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError
    except ValueError:
        raise ValueError('日志中的位置信息无效，请等待游戏写入新的位置记录。') from None
    return JournalLocation(system.strip(), timestamp, filename)


def read_current_system(directory):
    files = journal_files(directory)
    latest = max(files, key=lambda item: (item[0], item[1].name))
    # Only follow numbered parts of this session. Never take another commander's
    # or an earlier session's location when the latest session has none yet.
    parts = sorted((item for item in files if item[2] == latest[2]), key=lambda item: item[3], reverse=True)
    budget = [MAX_SCAN_BYTES]
    for item in parts:
        path = item[1]
        with path.open('rb') as file:
            for line in reverse_lines(file, budget):
                location = parse_location(line, path.name)
                if location is not None:
                    return location
        if budget[0] <= 0:
            raise ValueError('近期日志过大且未找到位置，请在游戏中更新位置后重试。')
    raise ValueError('最新游戏会话尚无位置记录，请进入游戏后重试。')


class JournalFollower:
    """Opt-in incremental tailer. Use from one worker, not from the Tk thread."""
    def __init__(self, directory, clock=time.monotonic):
        self.directory, self.clock = Path(directory), clock
        self.path = self.identity = self.directory_stamp = None
        self.last_scan = float('-inf')
        self.offset, self.pending, self.location = 0, b'', None
        self.last_read_bytes = 0

    def _snapshot(self):
        stat = self.path.stat()
        self.identity = (stat.st_dev, stat.st_ino)
        self.offset = stat.st_size
        # Retain a partially written trailing line for the next append.
        with self.path.open('rb') as file:
            file.seek(max(0, self.offset - MAX_LINE_BYTES))
            tail = file.read(min(self.offset, MAX_LINE_BYTES))
        self.pending = tail.rsplit(b'\n', 1)[-1]
        if len(self.pending) >= MAX_LINE_BYTES:
            raise ValueError('日志行过长，无法安全读取当前位置。')
        try:
            self.location = read_current_system(self.directory)
        except ValueError:
            # A fresh session may have only a Fileheader so far. Its future
            # appended Location will be read, without using an older session.
            self.location = None

    def poll(self):
        self.last_read_bytes = 0
        stamp, now = self.directory.stat().st_mtime_ns, self.clock()
        if self.path is None or stamp != self.directory_stamp or now - self.last_scan >= 10:
            files = journal_files(self.directory)
            latest = max(files, key=lambda item: (item[0], item[1].name))
            self.directory_stamp, self.last_scan = stamp, now
            if latest[1] != self.path:
                self.path = latest[1]
                self._snapshot()
                return self.location
        stat = self.path.stat()
        if (stat.st_dev, stat.st_ino) != self.identity or stat.st_size < self.offset or stat.st_size - self.offset > MAX_SCAN_BYTES:
            self._snapshot()
            return self.location
        if stat.st_size == self.offset:
            return self.location
        with self.path.open('rb') as file:
            file.seek(self.offset)
            data = file.read(min(MAX_SCAN_BYTES, stat.st_size - self.offset))
        self.offset += len(data)
        self.last_read_bytes = len(data)
        lines = (self.pending + data).split(b'\n')
        self.pending = lines.pop()
        if len(self.pending) > MAX_LINE_BYTES or any(len(line) > MAX_LINE_BYTES for line in lines):
            self.location = None
            raise ValueError('日志行过长，无法安全读取当前位置。')
        for line in lines:
            try:
                location = parse_location(line, self.path.name)
                if location is not None:
                    self.location = location
            except ValueError:
                self.location = None
        return self.location
