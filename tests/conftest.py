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


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "subprocess_only: runs only on the engine program route (XCL_TRANSPORT unset or subprocess)",
    )
    config.addinivalue_line(
        "markers",
        "inprocess_only: runs only on the shared library route (XCL_TRANSPORT=inprocess)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip the tests that belong to the route this run did not select.

    These are plain skips, never strict failures: a test of the other route
    is not a missing engine.
    """
    import pytest

    from xcl._transport.select import INPROCESS, SUBPROCESS, selected_route

    route = selected_route()
    other = INPROCESS if route == SUBPROCESS else SUBPROCESS
    skip = pytest.mark.skip(reason=f"runs only on the {other} route; XCL_TRANSPORT selects {route}")
    for item in items:
        if item.get_closest_marker(f"{other}_only") is not None:
            item.add_marker(skip)
