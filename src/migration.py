"""Explicit, validated, non-destructive import of old ship favourites."""
from pathlib import Path
import route_tool

def import_favorites(path, destination=None):
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Favourites file exceeds 32 MiB.')
    source = route_tool.Favorites(str(path)).load()
    target = destination if destination is not None else route_tool.Favorites()
    existing = target.load()
    names = {name.casefold() for name in existing}
    if any(name.casefold() in names for name in source):
        raise ValueError('Duplicate favourite names; no data was overwritten.')
    target.save(dict(existing, **source))
    return len(source)
