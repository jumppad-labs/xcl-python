"""Fixtures for the integration tests, which drive the real engine.

The engine is the one the run selects: the program built into ``xcl/_bin``
by ``make engine``, or with ``XCL_TRANSPORT=inprocess`` the library built into
``xcl/_lib`` by ``make libxcl``. The fixture plugins the tests load are built
into ``build/plugins`` by ``make plugins``, which is run here once per session
when they are missing and Go is installed, from the xcl checkout the
``xcl_src`` fixture finds (``XCL_SRC``, or the sibling ``xcl`` directory).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

import xcl_source
from engines import selected_engine

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "build" / "plugins"
SLOW = xcl_source.executable("xcl-plugin-slow")
RECORDING = xcl_source.executable("xcl-plugin-recording")


@pytest.fixture(scope="session")
def engine() -> Path:
    """The path of the engine the run selects; skips, or fails in strict mode, when it has not been built."""
    return selected_engine()


@pytest.fixture(scope="session")
def plugins_dir() -> Path:
    """The directory of the fixture plugins, built with ``make plugins`` when missing."""
    if (PLUGINS / SLOW).exists() and (PLUGINS / RECORDING).exists():
        return PLUGINS
    if shutil.which("go") is None:
        xcl_source.skip(f"the fixture plugins are not built in {PLUGINS} and go is not on PATH to build them")
    source = xcl_source.require("bindings/libxcl").parents[1]
    result = subprocess.run(
        ["make", "plugins", f"XCL_SRC={source}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        xcl_source.skip(f"make plugins failed:\n{result.stdout}\n{result.stderr}")
    return PLUGINS


@pytest.fixture(scope="session")
def slow_plugin(plugins_dir: Path) -> Path:
    """The slow fixture plugin: ``resource "slow" "<name>" { delay_ms = ... }``."""
    return plugins_dir / SLOW


@pytest.fixture(scope="session")
def recording_plugin(plugins_dir: Path) -> Path:
    """The recording fixture plugin: ``resource "recording" "<name>" { log = ..., value = ... }``."""
    return plugins_dir / RECORDING
