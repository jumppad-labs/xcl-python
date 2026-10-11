"""Importing the package must not load the engine."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# run in a fresh interpreter so that nothing another test did to the default
# client in this process can mask the state right after import
CHECK = """
import xcl
import xcl._client
from xcl._transport import InProcessTransport
from xcl._transport.inprocess import default_guard

assert xcl._client._default_client is None, "default client built at import"
assert InProcessTransport().loaded is False, "transport loaded at import"
assert default_guard().is_loaded() is False, "engine marked loaded at import"
print("not loaded")
"""


def test_import_does_not_load_engine():
    result = subprocess.run(
        [sys.executable, "-c", CHECK],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "not loaded" in result.stdout
