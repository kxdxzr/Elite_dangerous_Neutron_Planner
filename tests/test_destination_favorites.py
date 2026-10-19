import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from destination_favorites import DestinationFavorites


class DestinationFavoritesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'destinations.json'
        self.store = DestinationFavorites(self.path)

    def test_persist_rename_delete_and_trim(self):
        self.assertEqual(self.store.load(), {})
        self.store.put(' 探索基地 ', ' Colonia ')
        self.assertEqual(DestinationFavorites(self.path).load(), {'探索基地': 'Colonia'})
        self.store.rename('探索基地', 'Home')
        self.store.rename('Home', 'HOME')
        self.assertEqual(self.store.load(), {'HOME': 'Colonia'})
        self.store.delete('HOME')
        self.assertEqual(self.store.load(), {})

    def test_duplicates_and_invalid_input_do_not_change_file(self):
        self.store.put('Home', 'Sol')
        original = self.path.read_bytes()
        for name, system in [('home', 'Colonia'), ('', 'Sol'), ('x', ''),
                             ('x\ny', 'Sol'), ('x', 'Sol\n'), ('x' * 257, 'Sol'), ('x', None)]:
            with self.subTest(name=name, system=system), self.assertRaises(ValueError):
                self.store.put(name, system)
            self.assertEqual(self.path.read_bytes(), original)
        self.store.put('Other', 'Colonia')
        with self.assertRaises(ValueError):
            self.store.rename('Home', 'OTHER')
        self.assertEqual(self.store.load(), {'Home': 'Sol', 'Other': 'Colonia'})

    def test_damaged_files_are_not_overwritten(self):
        for data in ['{', '[]', json.dumps({'version': 1, 'destinations': {'x': 1}}),
                     json.dumps({'version': 1, 'destinations': {'x': 'Sol', 'X': 'Colonia'}}),
                     json.dumps({'version': True, 'destinations': {}})]:
            self.path.write_text(data, encoding='utf-8')
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.store.put('New', 'Sol')
            self.assertEqual(self.path.read_text(encoding='utf-8'), data)

    def test_failed_atomic_replace_preserves_previous_file(self):
        self.store.put('Home', 'Sol')
        with patch('session_store.os.replace', side_effect=OSError('write failed')):
            with self.assertRaises(OSError):
                self.store.put('Other', 'Colonia')
        self.assertEqual(self.store.load(), {'Home': 'Sol'})
