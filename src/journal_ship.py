"""Explicit, bounded local Loadout import; no EDMC or network dependency.

Journal reference: https://elite-journal.readthedocs.io/en/latest/Startup.html
Current import uses only the latest active session. History import explicitly
scans older sessions, keeping commander/ShipID identities separate.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math

import journal_location as journal
import route_ship
from export_metadata import PROJECT_NAME, PROJECT_VERSION


@dataclass(frozen=True)
class JournalShip:
    raw: str
    timestamp: str
    filename: str


# A newer mutation invalidates an older snapshot until a fresh Loadout arrives.
CHANGES = {'LoadGame', 'ShipyardSwap', 'ShipyardNew', 'ModuleBuy', 'ModuleSell',
           'ModuleSwap', 'ModuleStore', 'ModuleRetrieve', 'MassModuleStore',
           'EngineerCraft', 'EngineerLegacyConvert', 'SetUserShipName', 'Resurrect'}


def text(value, label, required=True):
    if (not isinstance(value, str) or required and not value.strip()
            or len(value) > 256 or any(ord(c) < 32 for c in value)):
        raise ValueError('Invalid Loadout ' + label)
    return value


def convert_loadout(record):
    """Normalise a Journal snapshot into the existing SLEF-shaped build input.

    Keep fitted module engineering, but exclude commander IDs, finances, health
    and unrelated Journal events. Do not derive mass from MaxJumpRange.
    """
    stamp = text(record.get('timestamp'), 'timestamp')
    try:
        if datetime.fromisoformat(stamp.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError
    except ValueError:
        raise ValueError('Invalid Loadout timestamp') from None
    data = dict(Ship=text(record.get('Ship'), 'Ship'),
                ShipName=text(record.get('ShipName', ''), 'ShipName', False),
                ShipIdent=text(record.get('ShipIdent', ''), 'ShipIdent', False),
                UnladenMass=route_ship.numeric(record.get('UnladenMass'), 'Unladen mass', True))
    fuel = record.get('FuelCapacity')
    if not isinstance(fuel, dict):
        raise ValueError('Invalid Loadout FuelCapacity')
    data['FuelCapacity'] = dict(Main=route_ship.numeric(fuel.get('Main'), 'Tank size', True),
                                Reserve=route_ship.numeric(fuel.get('Reserve'), 'Reservoir'))
    modules = record.get('Modules')
    if not isinstance(modules, list) or not 1 <= len(modules) <= 256:
        raise ValueError('Invalid Loadout Modules')
    clean, slots = [], set()
    for module in modules:
        if not isinstance(module, dict):
            raise ValueError('Invalid Loadout module')
        slot, item = text(module.get('Slot'), 'Slot'), text(module.get('Item'), 'Item')
        if slot.casefold() in slots:
            raise ValueError('Duplicate Loadout slot: ' + slot)
        slots.add(slot.casefold())
        fitted = dict(Slot=slot, Item=item)
        if 'On' in module:
            if not isinstance(module['On'], bool):
                raise ValueError('Invalid Loadout module On')
            fitted['On'] = module['On']
        if 'Engineering' in module:
            engineering = module['Engineering']
            if not isinstance(engineering, dict):
                raise ValueError('Invalid Loadout Engineering')
            modifiers = engineering.get('Modifiers', engineering.get('Modifications'))
            if not isinstance(modifiers, list) or not modifiers:
                raise ValueError('Loadout engineering modifiers missing; refresh the ship loadout in-game.')
            normalised = []
            for mod in modifiers:
                if not isinstance(mod, dict):
                    raise ValueError('Invalid Loadout modifier')
                label = text(mod.get('Label'), 'modifier label')
                value = mod.get('Value')
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError('Invalid Loadout modifier value: ' + label)
                if label.casefold() in ('fsdoptimalmass', 'maxfuelperjump'):
                    route_ship.numeric(value, label, True)
                normalised.append(dict(Label=label, Value=value))
            if slot.casefold() == 'frameshiftdrive' and not any(
                    m['Label'].casefold() == 'fsdoptimalmass' for m in normalised):
                raise ValueError('Loadout engineered FSD optimal mass missing.')
            fitted['Engineering'] = dict(Modifiers=normalised)
        clean.append(fitted)
    if 'frameshiftdrive' not in slots:
        raise ValueError('Exactly one Frame Shift Drive is required.')
    data['Modules'] = clean
    return json.dumps(dict(header=dict(appName=PROJECT_NAME, appVersion=PROJECT_VERSION),
                           data=data), ensure_ascii=False)


def read_current_ship(directory):
    files = journal.journal_files(directory)
    latest = max(files, key=lambda item: (item[0], item[1].name))
    parts = sorted((item for item in files if item[2] == latest[2]),
                   key=lambda item: item[3], reverse=True)
    budget = [journal.MAX_SCAN_BYTES]
    for _, path, _, _ in parts:
        with path.open('rb') as file:
            for line in journal.reverse_lines(file, budget):
                try:
                    record = json.loads(line.decode('utf-8-sig'))
                except (ValueError, RecursionError):
                    continue
                if not isinstance(record, dict):
                    continue
                if record.get('event') == 'Loadout':
                    return JournalShip(convert_loadout(record), record['timestamp'], path.name)
                if record.get('event') in CHANGES:
                    raise ValueError('配船已变更但尚无完整记录，请在游戏中退出配装界面或重新进入游戏后重试。')
        if budget[0] <= 0:
            break
    raise ValueError('最新游戏会话中未找到完整配船，请切换到目标舰船或重新进入游戏后重试。')


MAX_HISTORY_BYTES = 64 * 1024 * 1024
MAX_HISTORY_SHIPS = 500


@dataclass(frozen=True)
class HistoricalShip:
    commander_id: str  # In memory only; never written into the saved build.
    commander_name: str
    ship_id: int
    snapshot: JournalShip


@dataclass(frozen=True)
class ShipHistory:
    ships: tuple
    limited: bool
    skipped: int


def read_ship_history(directory, stop=None):
    """Scan complete sessions within a shared byte budget, newest files first.

    Never attach a Loadout to an inferred commander. Session part files share
    identity only after a Commander/LoadGame FID has been observed. Skip an
    oversized session as a whole; do not use its potentially stale early rows.
    Each (FID, ShipID) keeps its newest snapshot by UTC record time. An invalid
    latest snapshot suppresses older versions rather than silently using them.
    """
    sessions = {}
    for entry in journal.journal_files(directory):
        sessions.setdefault(entry[2], []).append(entry)
    ordered = sorted(sessions.values(), key=lambda parts: max(p[0] for p in parts), reverse=True)
    remaining, skipped, limited = MAX_HISTORY_BYTES, 0, False
    latest = {}
    for parts in ordered:
        if stop is not None and stop.is_set():
            raise InterruptedError('Journal scan cancelled.')
        # Snapshot file sizes, so concurrent appends cannot make work unbounded.
        sized = [(item, item[1].stat().st_size) for item in sorted(parts, key=lambda p: p[3])]
        size = sum(length for _, length in sized)
        if size > remaining:
            limited = True
            continue
        remaining -= size
        commander, commander_name = None, ''
        pending = {}
        session_valid = True
        for (_, path, _, _), length in sized:
            with path.open('rb') as file:
                consumed = 0
                while consumed < length:
                    if stop is not None and stop.is_set():
                        raise InterruptedError('Journal scan cancelled.')
                    line = file.readline(min(journal.MAX_LINE_BYTES + 1, length - consumed))
                    consumed += len(line)
                    if not line:
                        break
                    if len(line) > journal.MAX_LINE_BYTES:
                        session_valid = False
                        break
                    if not line.endswith(b'\n'):
                        # An actively written trailing record is not a snapshot.
                        break
                    try:
                        record = json.loads(line.decode('utf-8-sig'))
                    except (ValueError, RecursionError):
                        skipped += 1
                        continue
                    if not isinstance(record, dict):
                        continue
                    event = record.get('event')
                    if event in ('Commander', 'LoadGame'):
                        try:
                            commander = text(record.get('FID'), 'FID')
                            commander_name = text(record.get('Name' if event == 'Commander' else 'Commander', ''),
                                                  'Commander name', False)
                        except ValueError:
                            commander, commander_name = None, ''
                    if event != 'Loadout':
                        continue
                    ident = record.get('ShipID')
                    if commander is None or isinstance(ident, bool) or not isinstance(ident, int) or ident < 0:
                        skipped += 1
                        continue
                    key = (commander, ident)
                    try:
                        stamp = datetime.fromisoformat(record.get('timestamp', '').replace('Z', '+00:00'))
                        if stamp.tzinfo is None:
                            raise ValueError
                        stamp = stamp.astimezone(timezone.utc)
                    except (ValueError, AttributeError):
                        stamp = datetime.max.replace(tzinfo=timezone.utc)
                    try:
                        raw = convert_loadout(record)
                        snapshot = HistoricalShip(commander, commander_name, ident,
                                                  JournalShip(raw, record['timestamp'], path.name))
                    except (ValueError, TypeError):
                        snapshot = None
                        skipped += 1
                    if key not in pending or stamp >= pending[key][0]:
                        pending[key] = (stamp, snapshot)
                    if len(pending) > MAX_HISTORY_SHIPS:
                        session_valid = False
                        break
            if not session_valid:
                break
        if not session_valid:
            limited = True
            continue
        for key, candidate in pending.items():
            if key in latest:
                if candidate[0] > latest[key][0]:
                    latest[key] = candidate
            elif len(latest) < MAX_HISTORY_SHIPS:
                latest[key] = candidate
            else:
                limited = True
    ships = tuple(item[1] for item in sorted(latest.values(), key=lambda value: value[0], reverse=True)
                  if item[1] is not None)
    return ShipHistory(ships, limited, skipped)
