"""Bounded, offline import of native bilingual and Spansh Exact Plotter CSV."""
import csv
import hashlib
import io
import json
import math
from pathlib import Path

from i18n import translate
from route_tool import COLUMNS, FULL_TANK_NOTE, SHIP_SWAP_NOTE

MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 100000
STATE_MARKER = '# Neutron Planner route state v1'


def table_digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def unescape(value):
    return value[1:] if len(value) > 1 and value[0] == "'" and value[1] in "'=+-@" else value


def number(value, label, signed=False, integer=False):
    value = unescape(value.strip())
    if not value:
        return None
    try:
        result = float(value.replace(',', ''))
    except ValueError:
        raise ValueError('Invalid CSV number: ' + label) from None
    if not math.isfinite(result) or not signed and result < 0 or integer and (result < 1 or not result.is_integer()):
        raise ValueError('Invalid CSV number: ' + label)
    return int(result) if integer else result


def flag(value):
    value = value.strip().casefold()
    if value in ('yes', 'true', '1', '是'):
        return True
    if value in ('no', 'false', '0', '否'):
        return False
    if value in ('', 'unknown', '情况未知'):
        return None
    raise ValueError('Invalid CSV flag: ' + value)


def header_keys(header):
    aliases = {}
    for key, label in COLUMNS:
        for name in (key, label, translate(label, 'en')):
            aliases[name.strip().casefold()] = key
    aliases.update({
        'system name': 'name', 'system': 'name', 'distance': 'distance',
        'distance travelled': 'distance', 'distance remaining': 'distance_to_destination',
        'remaining': 'distance_to_destination', 'fuel left': 'fuel_in_tank',
        'fuel remaining': 'fuel_in_tank', 'fuel used': 'fuel_used',
        'refuel': 'must_refuel', 'neutron star': 'has_neutron', 'neutron': 'has_neutron',
        'inject': 'must_inject', 'injection': 'must_inject', 'x': 'x', 'y': 'y', 'z': 'z',
    })
    keys = [aliases.get(cell.strip().casefold()) for cell in header]
    known = [key for key in keys if key is not None]
    if len(known) != len(set(known)):
        raise ValueError('Duplicate CSV columns.')
    required = {'name', 'distance', 'distance_to_destination', 'fuel_in_tank', 'fuel_used'}
    if not required.issubset(known):
        raise ValueError('Unsupported route CSV headers.')
    return keys


def import_csv(path, stop=None):
    with open(path, 'rb') as file:
        data = file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Route CSV is too large (maximum 32 MiB).')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('Route CSV must use UTF-8 encoding.') from None
    try:
        return parse_csv(text, stop=stop, filename=Path(path).name)
    except csv.Error as exc:
        raise ValueError('Invalid route CSV: ' + str(exc)) from None


def parse_csv(text, stop=None, filename=''):
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    header = None
    for index, record in enumerate(reader):
        if index >= 32:
            raise ValueError('Route CSV header not found.')
        if not record or not any(record):
            continue
        if record[0].startswith('# '):
            continue
        header = record
        break
    if header is None:
        raise ValueError('Route CSV is empty.')
    keys = header_keys(header)
    native = 'step' in keys and 'segment' in keys
    raw_rows, rows, metadata = [], [], None
    for record in reader:
        if stop is not None and stop.is_set():
            raise InterruptedError('CSV import cancelled.')
        if not record or not any(record):
            continue
        if record[0] == STATE_MARKER:
            if metadata is not None or len(record) < 2:
                raise ValueError('Invalid route CSV state.')
            try:
                metadata = json.loads(record[1])
            except (ValueError, RecursionError):
                raise ValueError('Invalid route CSV state.') from None
            continue
        if metadata is not None or len(record) != len(header):
            raise ValueError('Invalid route CSV row width or order.')
        if len(rows) >= MAX_ROWS:
            raise ValueError('Route CSV has too many rows.')
        raw_rows.append(record)
        values = {key: value for key, value in zip(keys, record) if key is not None}
        name = unescape(values['name']) if native else values['name']
        if (not name.strip() or len(name) > 256 or any(ord(c) < 32 for c in name)):
            raise ValueError('Invalid CSV system name.')
        row = dict(name=name.strip(), full_tank_start=False, waypoint=False, job='')
        for field in ('distance', 'distance_to_destination', 'fuel_in_tank', 'fuel_used',
                      'departure_fuel', 'cargo', 'reserve', 'departure_cargo', 'departure_reserve', 'x', 'y', 'z'):
            if field in values:
                row[field] = number(values[field], field, signed=field in ('x', 'y', 'z'))
        for field in ('must_refuel', 'has_neutron', 'must_inject', 'waypoint'):
            row[field] = flag(values.get(field, ''))
        row['segment'] = number(values.get('segment', '1'), 'segment', integer=True)
        if row['segment'] is None:
            raise ValueError('Missing route segment number.')
        row['departure_segment'] = number(values.get('departure_segment', ''), 'departure segment', integer=True)
        for field in ('ship_name', 'departure_ship'):
            value = unescape(values.get(field, ''))
            if len(value) > 256 or any(ord(c) < 32 for c in value):
                raise ValueError('Invalid CSV build name.')
            row[field] = value
        assumption = values.get('assumption', '')
        row['full_tank_start'] = any(translate(FULL_TANK_NOTE, language) in assumption for language in ('zh', 'en'))
        row['ship_change'] = any(translate(SHIP_SWAP_NOTE, language) in assumption for language in ('zh', 'en'))
        rows.append(row)
    if not rows:
        raise ValueError('Route CSV contains no systems.')
    # Enforce ordered contiguous segments, including shared-endpoint departures.
    segment_count, grouped = 1, {}
    for index, row in enumerate(rows):
        segment = row['segment']
        if index == 0 and segment != 1 or segment < segment_count or segment > segment_count + 1:
            raise ValueError('Invalid CSV segment sequence.')
        segment_count = segment
        departure = row['departure_segment']
        if departure is not None and departure not in (segment, segment + 1):
            raise ValueError('Invalid CSV departure segment.')
        for leg in {segment, departure} - {None}:
            group = grouped.setdefault(leg, [row['name'], row['name']])
            group[1] = row['name']
    segments = []
    for number_ in range(1, segment_count + 1):
        if number_ not in grouped:
            raise ValueError('Missing CSV segment.')
        segments.append(dict(number=number_, source=grouped[number_][0], destination=grouped[number_][1], job=''))
    complete, planned, failed, full_tank, status_known = False, segment_count, None, None, False
    if metadata is not None:
        if (not native or not isinstance(metadata, dict) or type(metadata.get('complete')) is not bool
                or metadata.get('row_count') != len(rows) or metadata.get('table_sha256') != table_digest(raw_rows)
                or type(metadata.get('planned_segments')) is not int or metadata['planned_segments'] < segment_count
                or metadata.get('full_tank_each_segment') is not True and metadata.get('full_tank_each_segment') is not None):
            raise ValueError('Route CSV state does not match its data.')
        failed = metadata.get('failed_segment')
        if failed is not None and (type(failed) is not int or not 1 <= failed <= metadata['planned_segments']):
            raise ValueError('Invalid CSV failed segment.')
        complete, planned, full_tank = metadata['complete'], metadata['planned_segments'], metadata.get('full_tank_each_segment')
        status_known = metadata.get('status_known', True)
        if type(status_known) is not bool or not status_known and complete:
            raise ValueError('Invalid CSV completeness marker.')
        if complete and (failed is not None or planned != segment_count):
            raise ValueError('Invalid complete CSV route state.')
    return dict(complete=complete, rows=rows, segments=segments, planned_segments=planned,
                failed_segment=failed, full_tank_each_segment=full_tank,
                imported=True, import_filename=filename, import_state_known=status_known,
                reason='CSV 已导入；仅使用文件记录，未重新验证航线。' if status_known else
                       'CSV 已导入；完整状态未知，末行仅代表文件末尾。')
