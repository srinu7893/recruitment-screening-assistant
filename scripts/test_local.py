"""Run backend checks, optionally including the dedicated local PostgreSQL service."""
import argparse
import os
from pathlib import Path
import sys
import unittest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--postgres-url-file', type=Path)
args = parser.parse_args()
if args.postgres_url_file:
    os.environ['TEST_DATABASE_URL'] = args.postgres_url_file.read_text(encoding='utf-8').strip()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests'))
raise SystemExit(0 if result.wasSuccessful() else 1)
