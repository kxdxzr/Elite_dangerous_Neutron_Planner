"""Bounded Spansh system-name suggestions."""
import json
import urllib.parse
import urllib.request
from functools import lru_cache

@lru_cache(maxsize=128)
def suggest_systems(query):
    query = query.strip()
    if len(query) < 2:
        return []
    url = 'https://spansh.co.uk/api/systems/field_values/system_names?q=' + urllib.parse.quote(query)
    request = urllib.request.Request(url, headers={'User-Agent': 'EliteDangerousNeutronPlanner/0.1'})
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read(1024 * 1024 + 1)
    if len(body) > 1024 * 1024:
        raise ValueError('System-name response too large.')
    data = json.loads(body)
    values = data.get('values', []) if isinstance(data, dict) else data
    return [value for value in values if isinstance(value, str)][:10] if isinstance(values, list) else []
