"""Test configuration.

Puts the package root on ``sys.path`` so ``import xcl`` resolves from a
checkout without an install, and this directory so the test modules in
``unit/`` and ``integration/`` can import ``fakes``.
"""

import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_ROOT = _TESTS.parent

for _path in (str(_ROOT), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
