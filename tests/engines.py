"""Which engine a test run uses, and what happens when it is missing.

A test that needs the real engine asks :func:`selected_engine` for the engine
the run selected (the program, or the shared library under
``XCL_TRANSPORT=inprocess``). When that engine has not been built, the test
goes through :func:`skip_missing_engine`, the only place a missing-engine
skip is raised.

CI makes those skips strict. ``XCL_TEST_ENGINES`` lists, comma separated, the
routes a job builds an engine for (``subprocess`` everywhere, plus
``inprocess`` on the job that also builds the library), and with
``XCL_TEST_STRICT=1`` a missing engine for a listed route fails the run
rather than skipping, so a job that should have built an engine can never go
green with its tests skipped. A route the job does not build stays a skip.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from xcl._errors import EngineNotFoundError
from xcl._transport.inprocess import default_library_path
from xcl._transport.select import SUBPROCESS, selected_route
from xcl._transport.subprocess import program_path

TEST_ENGINES_ENV = "XCL_TEST_ENGINES"
TEST_STRICT_ENV = "XCL_TEST_STRICT"


def expected_routes() -> set[str]:
    """The routes this run is expected to have an engine for, from ``XCL_TEST_ENGINES``."""
    value = os.environ.get(TEST_ENGINES_ENV, "")
    return {route.strip() for route in value.split(",") if route.strip()}


def skip_missing_engine(route: str, reason: str) -> None:
    """Skip the test because the engine for ``route`` is missing, or fail it in strict mode for an expected route."""
    if os.environ.get(TEST_STRICT_ENV) == "1" and route in expected_routes():
        pytest.fail(f"{reason} ({TEST_STRICT_ENV}=1 and {TEST_ENGINES_ENV} lists {route})")
    pytest.skip(reason)


def selected_engine() -> Path:
    """The engine this run uses, skipping (or failing, in strict mode) when it has not been built."""
    route = selected_route()
    program = program_path()
    library = default_library_path()
    engine = program if route == SUBPROCESS else library
    if not engine.is_file():
        error = EngineNotFoundError(program=program, library=library, transport=route)
        build = "make engine" if route == SUBPROCESS else "make libxcl"
        skip_missing_engine(route, f"{error}; run {build}")
    return engine
