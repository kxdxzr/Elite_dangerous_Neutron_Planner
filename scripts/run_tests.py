"""Run isolated source tests without requiring installation."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project / 'src'))
sys.path.insert(0, str(project / 'tests'))
with tempfile.TemporaryDirectory() as directory:
    os.environ['ELITE_NEUTRON_DATA_DIR'] = directory
    suite = (unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:]) if len(sys.argv) > 1
             else unittest.defaultTestLoader.discover(str(project / 'tests')))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
