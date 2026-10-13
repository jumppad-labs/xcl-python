"""Fixtures for the integration tests, which drive the real engine.

The engine is the one the run selects: the program built into ``xcl/_bin``
by ``make engine``, or with ``XCL_TRANSPORT=inprocess`` the library built into
``xcl/_lib`` by ``make libxcl``. The fixture plugins the tests load are built
into ``build/plugins`` by ``make plugins``, which is run here once per session
when they are missing and Go is installed.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from engines import selected_engine

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "build" / "plugins"
XCL_SRC = ROOT.parent / "xcl"


@pytest.fixture(scope="session")
def engine() -> Path:
    """The path of the engine the run selects; skips, or fails in strict mode, when it has not been built."""
    return selected_engine()


@pytest.fixture(scope="session")
def plugins_dir() -> Path:
    """The directory of the fixture plugins, built with ``make plugins`` when missing."""
    if (PLUGINS / "xcl-plugin-slow").exists() and (PLUGINS / "xcl-plugin-recording").exists():
        return PLUGINS
    if shutil.which("go") is None:
        pytest.skip(f"the fixture plugins are not built in {PLUGINS} and go is not on PATH to build them")
    if not XCL_SRC.exists():
        pytest.skip(f"the fixture plugins are not built in {PLUGINS} and the xcl checkout is not at {XCL_SRC}")
    result = subprocess.run(
        ["make", "plugins", f"XCL_SRC={XCL_SRC}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"make plugins failed:\n{result.stdout}\n{result.stderr}")
    return PLUGINS


@pytest.fixture(scope="session")
def slow_plugin(plugins_dir: Path) -> Path:
    """The slow fixture plugin: ``resource "slow" "<name>" { delay_ms = ... }``."""
    return plugins_dir / "xcl-plugin-slow"


@pytest.fixture(scope="session")
def recording_plugin(plugins_dir: Path) -> Path:
    """The recording fixture plugin: ``resource "recording" "<name>" { log = ..., value = ... }``."""
    return plugins_dir / "xcl-plugin-recording"
