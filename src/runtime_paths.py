"""Independent application data; never move or delete the filter's settings."""
import os
from pathlib import Path

def data_directory():
    override = os.environ.get('ELITE_NEUTRON_DATA_DIR')
    if override:
        return os.path.abspath(os.path.expanduser(override))
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / '.local' / 'share')
    return str(Path(base) / 'EliteDangerousNeutronPlanner')

def data_file(filename):
    directory = Path(data_directory())
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / filename)
