"""Bounded local result snapshots and content-based request identities."""
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json

from runtime_paths import data_file
import session_store
import route_ship

MAX_BYTES = 32 * 1024 * 1024


def build_key(raw):
    canonical = json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def request_key(raw, points, options):
    # Bump the model number if parsing/physical assumptions change.
    data = [1, route_ship.DATA_REVISION, build_key(raw), [p.strip().casefold() for p in points], asdict(options)]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode('utf-8')).hexdigest()


def find_complete(entries, key, now=None, max_age=86400):
    now = now or datetime.now(timezone.utc)
    for index, entry in enumerate(entries):
        info = entry['result']
        if (entry['key'] != key or not info['complete'] or not info['rows']
                or len(info['segments']) != info['planned_segments']):
            continue
        try:
            created = datetime.fromisoformat(entry['created'])
            age = (now - created).total_seconds()
        except (ValueError, TypeError):
            continue
        if 0 <= age <= max_age:
            return index, copy.deepcopy(entry)
    return None


def validate_entry(entry):
    if not isinstance(entry, dict):
        raise ValueError('Invalid route history entry.')
    for key in ('key', 'build_key', 'created'):
        if not isinstance(entry.get(key), str):
            raise ValueError('Invalid route history identity.')
    parameters = entry.get('parameters')
    strings = ('selected', 'source', 'destination', 'cargo', 'reserve', 'algorithm', 'injection')
    switches = ('supercharge', 'already_supercharged', 'exclude_secondary', 'refuel_every_scoopable')
    if (not isinstance(parameters, dict)
            or any(not isinstance(parameters.get(k), str) for k in strings)
            or any(type(parameters.get(k)) is not bool for k in switches)
            or parameters['algorithm'] not in ('优先少跳', '优先计算速度')
            or parameters['injection'] not in ('不使用', '仅在需要时', '始终使用')):
        raise ValueError('Invalid route history parameters.')
    points = entry.get('points')
    if not isinstance(points, list) or any(not isinstance(p, str) or not p.strip() for p in points):
        raise ValueError('Invalid route history waypoints.')
    info = entry.get('result')
    if (not isinstance(info, dict) or type(info.get('complete')) is not bool
            or not isinstance(info.get('reason'), str) or not isinstance(info.get('rows'), list)
            or not isinstance(info.get('segments'), list)
            or type(info.get('planned_segments')) is not int or info['planned_segments'] < 1
            or len(info['segments']) > info['planned_segments']
            or info.get('full_tank_each_segment') is not True):
        raise ValueError('Invalid route history result.')
    for row in info['rows']:
        if (not isinstance(row, dict) or not isinstance(row.get('name'), str)
                or type(row.get('full_tank_start')) is not bool):
            raise ValueError('Invalid route history row.')


class RouteHistory:
    def __init__(self, path=None):
        self.path = path or data_file('route_history.json')

    def load(self):
        try:
            with open(self.path, encoding='utf-8') as file:
                raw = file.read(MAX_BYTES + 1)
        except FileNotFoundError:
            return []
        if len(raw.encode('utf-8')) > MAX_BYTES:
            raise ValueError('Route history is too large.')
        data = json.loads(raw)
        if (not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1
                or not isinstance(data.get('entries'), list) or len(data['entries']) > 5):
            raise ValueError('Invalid route history file; it has not been overwritten.')
        for entry in data['entries']:
            validate_entry(entry)
        return data['entries']

    def add(self, entries, key, ship_key, parameters, points, result):
        # Refuse to replace a damaged file, including corruption since startup.
        self.load()
        entry = dict(key=key, build_key=ship_key, parameters=copy.deepcopy(parameters),
                     points=list(points), result=copy.deepcopy(result),
                     created=datetime.now(timezone.utc).isoformat(timespec='seconds'))
        validate_entry(entry)
        # Keep the most recent five searches, including repeated attempts.
        updated = [entry, *entries][:5]
        data = dict(version=1, entries=updated)
        if len(json.dumps(data, ensure_ascii=False, indent=1).encode('utf-8')) > MAX_BYTES:
            raise ValueError('Route history is too large.')
        session_store.save(self.path, data)
        return updated
