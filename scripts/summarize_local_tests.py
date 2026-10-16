"""Summarize a unittest log without printing repeated tracebacks."""
from collections import Counter
from pathlib import Path
import sys

log = Path(sys.argv[1] if len(sys.argv) > 1 else 'test-results/backend.log').read_text(encoding='utf-8')
counts = Counter()
for line in log.splitlines():
    if line.startswith('test_') and ' ... ' in line:
        counts[line.split(' ... ', 1)[1].split(' ', 1)[0]] += 1
print(dict(counts))
for index, line in enumerate(log.splitlines()):
    if line.startswith(('ERROR:', 'FAIL:')):
        print('\n'.join(log.splitlines()[index:index + 18]))
print('\n'.join(log.splitlines()[-35:]))
print('Unique exception messages:')
print('\n'.join(sorted({line for line in log.splitlines()
                        if line.startswith(('ModuleNotFoundError:', 'PermissionError:', 'AssertionError:', 'ValueError:'))})))
