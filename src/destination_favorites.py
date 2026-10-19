"""Local named destination systems; saving never resolves systems online."""
import json
import os

from runtime_paths import data_file
import session_store


def clean_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256 or any(ord(c) < 32 for c in value):
        raise ValueError('收藏名称和星系须为非空单行文本，最多256个字符。')
    return value.strip()


class DestinationFavorites:
    def __init__(self, path=None):
        self.path = path or data_file('destination_favorites.json')

    def load(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path, encoding='utf-8') as file:
            data = json.load(file)
        if (not isinstance(data, dict) or type(data.get('version')) is not int
                or data['version'] != 1 or not isinstance(data.get('destinations'), dict)):
            raise ValueError('目的地收藏文件无效，未覆盖原文件。')
        destinations = data['destinations']
        names = set()
        for name, system in destinations.items():
            if clean_text(name) != name or clean_text(system) != system or name.casefold() in names:
                raise ValueError('目的地收藏文件无效，未覆盖原文件。')
            names.add(name.casefold())
        return destinations

    def _save(self, destinations):
        session_store.save(self.path, dict(version=1, destinations=destinations))

    def put(self, name, system):
        name, system = clean_text(name), clean_text(system)
        destinations = self.load()
        if any(n.casefold() == name.casefold() for n in destinations):
            raise ValueError('目的地收藏名称已存在，请使用其他名称。')
        destinations[name] = system
        self._save(destinations)

    def rename(self, old, new):
        new = clean_text(new)
        destinations = self.load()
        if old not in destinations:
            raise ValueError('未找到目的地收藏。')
        if any(n != old and n.casefold() == new.casefold() for n in destinations):
            raise ValueError('目的地收藏名称已存在，请使用其他名称。')
        destinations[new] = destinations.pop(old)
        self._save(destinations)

    def delete(self, name):
        destinations = self.load()
        if name not in destinations:
            raise ValueError('未找到目的地收藏。')
        del destinations[name]
        self._save(destinations)
