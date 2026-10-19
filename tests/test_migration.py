import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_route_tool import build
import route_tool
from migration import import_favorites
from runtime_paths import data_directory

class MigrationTests(unittest.TestCase):
    def test_independent_path_ignores_filter_override(self):
        with patch.dict(os.environ, {'ELITE_FILTER_DATA_DIR': 'DO-NOT-USE'}, clear=False):
            self.assertNotEqual(data_directory(), 'DO-NOT-USE')

    def test_import_copies_without_touching_old_file_and_rejects_conflicts(self):
        with tempfile.TemporaryDirectory() as folder:
            source = route_tool.Favorites(str(Path(folder) / 'old.json'))
            source.put('Explorer', json.dumps(build()))
            before = Path(source.path).read_bytes()
            target = route_tool.Favorites(str(Path(folder) / 'new.json'))
            self.assertEqual(import_favorites(source.path, target), 1)
            self.assertEqual(source.load(), target.load())
            with self.assertRaises(ValueError):
                import_favorites(source.path, target)
            self.assertEqual(Path(source.path).read_bytes(), before)
