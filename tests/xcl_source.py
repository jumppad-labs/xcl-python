"""Where the xcl sources are, and how a test skips when something it needs is missing.

The xcl checkout the fixtures, the fixture plugins and the Go parity program
come from is ``XCL_SRC`` when it is set, and the sibling ``xcl`` directory of
this package's checkout otherwise. Every test that needs it gets it through
the ``xcl_src`` fixture, so there is one answer to where it is.

Every skip the test harness raises for something missing goes through
:func:`skip`. Locally it skips with a message naming what to set. CI sets
``XCL_TEST_STRICT=1``, and then a missing source checkout, fixture plugin
build or plugin release fails the run instead, so a job that should have had
them can never go green with its tests skipped. A missing engine is a matter
of which routes the job builds, so it is handed to
:func:`engines.skip_missing_engine`, which fails only for a route
``XCL_TEST_ENGINES`` lists. The route markers (``subprocess_only`` and
``inprocess_only``) and ordinary platform ``skipif`` markers never come here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NoReturn, Optional

import pytest

from engines import TEST_STRICT_ENV, skip_missing_engine

SOURCE_ENV = "XCL_SRC"

# the root of this package's checkout
ROOT = Path(__file__).resolve().parents[1]


def path() -> Path:
    """The xcl checkout: ``XCL_SRC`` when set, else the sibling ``xcl`` directory, resolved."""
    value = os.environ.get(SOURCE_ENV)
    if value:
        return Path(value).resolve()
    return (ROOT.parent / "xcl").resolve()


def strict() -> bool:
    """Whether the run is strict, ``XCL_TEST_STRICT=1``, as CI is."""
    return os.environ.get(TEST_STRICT_ENV) == "1"


def skip(reason: str, *, route: Optional[str] = None) -> NoReturn:
    """Skip the test because something it needs is missing, or fail it in a strict run.

    Without ``route`` the missing thing is one every run is meant to have (the
    xcl sources, the fixture plugins, the plugin release), so a strict run
    fails. With ``route`` (``"subprocess"`` or ``"inprocess"``) it is the
    engine for that route, and :func:`engines.skip_missing_engine` decides.
    """
    if route is not None:
        skip_missing_engine(route, reason)
    if strict():
        pytest.fail(f"{reason} ({TEST_STRICT_ENV}=1 turns this skip into a failure)")
    pytest.skip(reason)
    raise AssertionError("unreachable")  # pragma: no cover


def require(relative: str) -> Path:
    """``relative`` inside the xcl checkout, skipping (or failing, in a strict run) when it is not there."""
    target = path() / relative
    if not target.exists():
        skip(f"the xcl sources are not at {path()}; set {SOURCE_ENV} to the xcl checkout")
    return target


def executable(name: str) -> str:
    """The file name of the program ``name`` on this platform, with ``.exe`` on Windows as ``make plugins`` builds it."""
    return name + ".exe" if sys.platform == "win32" else name
