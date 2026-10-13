"""Driving the real engine the run selects: the program in xcl/_bin, or the library in xcl/_lib."""

import subprocess
import sys
from pathlib import Path

import pytest

import xcl
from xcl._client import default_client, normalise_version
from xcl._core import core_pb2

ROOT = Path(__file__).resolve().parents[2]

# every test here drives the engine the run selects, which the engine fixture
# skips without, or fails without in strict mode
needs_engine = pytest.mark.usefixtures("engine")

# the ctypes fallback is exercised in a fresh interpreter: cffi is blocked
# before xcl is imported, so load_library has to fall back, and the process
# must still create a configuration and report the engine's version
CTYPES_FALLBACK = """
import sys
sys.modules["cffi"] = None

import xcl
from xcl._client import default_client
from xcl._transport.inprocess import _CtypesLibrary

config = xcl.Config()
config.close()
transport = default_client().transport
assert isinstance(transport._lib, _CtypesLibrary), type(transport._lib)
print("engine", xcl.engine_version())
"""


@needs_engine
def test_config_opens_and_closes_against_engine():
    config = xcl.Config()

    assert config.handle != 0

    config.close()

    assert config.handle == 0


@needs_engine
def test_engine_reports_package_version():
    reported = xcl.engine_version()

    assert normalise_version(reported) == normalise_version(xcl.__version__)


@needs_engine
def test_lookup_error_from_engine_is_typed():
    with xcl.Config() as config:
        with pytest.raises(xcl.NotFoundError) as raised:
            default_client().call(config.handle, "Find", core_pb2.FindRequest(address="app.nope"))

    error = raised.value
    assert error.details["address"] == "app.nope"
    assert error.code == "not_found"
    assert "app.nope" in error.message


@needs_engine
@pytest.mark.inprocess_only
def test_ctypes_fallback_drives_engine():
    result = subprocess.run(
        [sys.executable, "-c", CTYPES_FALLBACK],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert normalise_version(xcl.__version__) in result.stdout
