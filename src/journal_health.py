"""FSD Health from local Loadout snapshots, never an inferred live durability."""
from dataclasses import dataclass
from datetime import datetime
import json
import math

import journal_location as journal


@dataclass(frozen=True)
class FsdHealth:
    value: float  # Journal fraction: 0..1, not percent.
    timestamp: str
    ship_id: int
    ship: str


# New identity, fitting or repairs require a fresh Loadout. Do not guess changes
# from repair costs, neutron jumps, module names or a saved historical build.
INVALIDATES = {'Commander', 'LoadGame', 'ShipyardSwap', 'ShipyardNew', 'ModuleBuy',
               'ModuleSell', 'ModuleSwap', 'ModuleStore', 'ModuleRetrieve',
               'MassModuleStore', 'EngineerCraft', 'EngineerLegacyConvert',
               'Resurrect', 'Repair', 'RepairAll', 'AfmuRepairs'}


def decode(line):
    try:
        record = json.loads(line.decode('utf-8-sig'))
    except (ValueError, RecursionError):
        return {}
    return record if isinstance(record, dict) else {}


def parse_health(record):
    ident, ship, stamp = record.get('ShipID'), record.get('Ship'), record.get('timestamp')
    if type(ident) is not int or ident < 0 or not isinstance(ship, str) or not ship.strip():
        return None
    if not isinstance(stamp, str):
        return None
    try:
        if datetime.fromisoformat(stamp.replace('Z', '+00:00')).tzinfo is None:
            return None
    except ValueError:
        return None
    modules = record.get('Modules')
    if not isinstance(modules, list):
        return None
    drives = [module for module in modules if isinstance(module, dict)
              and str(module.get('Slot', '')).casefold() == 'frameshiftdrive']
    if len(drives) != 1:
        return None
    value = drives[0].get('Health')
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return FsdHealth(float(value), stamp, ident, ship)


def read_current_health(directory, expected_session=None):
    files = journal.journal_files(directory)
    latest = max(files, key=lambda item: (item[0], item[1].name))
    if expected_session is not None and latest[2] != expected_session:
        return None
    parts = sorted((item for item in files if item[2] == latest[2]), key=lambda item: item[3], reverse=True)
    budget = [journal.MAX_SCAN_BYTES]
    for _, path, _, _ in parts:
        with path.open('rb') as file:
            for line in journal.reverse_lines(file, budget):
                record = decode(line)
                if record.get('event') == 'Loadout':
                    return parse_health(record)  # Invalid latest record must clear the old value.
                if record.get('event') in INVALIDATES:
                    return None
        if budget[0] <= 0:
            break
    return None


def update_health(previous, line):
    record = decode(line)
    if record.get('event') == 'Loadout':
        return parse_health(record)
    if record.get('event') in INVALIDATES:
        return None
    return previous
