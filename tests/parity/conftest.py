"""Fixtures for the parity tests, which run the Go and Python parity programs.

The Go program and the fixture plugins are built into ``build/plugins`` by
``make plugins`` from the xcl checkout the ``xcl_src`` fixture finds,
``XCL_SRC`` in the environment or the sibling ``xcl`` directory by default,
and the fixtures are read from it; the Python program is
``tests/parity/run_python.py`` and needs the engine the run selects, built
by ``make engine``, or by ``make libxcl`` with ``XCL_TRANSPORT=inprocess``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

import xcl_source
from engines import selected_engine

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "build" / "plugins"
RUN_PYTHON = Path(__file__).resolve().parent / "run_python.py"

RunParity = Callable[[str], tuple[dict[str, Any], dict[str, Any]]]


@pytest.fixture(scope="session")
def parity_fixtures(xcl_src: Path) -> Path:
    """The parity fixtures in the xcl checkout; skips, or fails in strict mode, when they are missing."""
    return xcl_source.require("bindings/libxcl/testdata/parity")


@pytest.fixture(scope="session")
def engine() -> Path:
    """The path of the engine the run selects; skips, or fails in strict mode, when it has not been built."""
    return selected_engine()


@pytest.fixture(scope="session")
def plugins_dir(xcl_src: Path) -> Path:
    """The directory of the Go parity program and the fixture plugins, built with ``make plugins`` when missing."""
    wanted = tuple(xcl_source.executable(name) for name in ("parity", "xcl-plugin-recording", "xcl-plugin-slow"))
    if all((PLUGINS / name).exists() for name in wanted):
        return PLUGINS
    if shutil.which("go") is None:
        xcl_source.skip(f"the parity binaries are not built in {PLUGINS} and go is not on PATH to build them")
    result = subprocess.run(
        ["make", "plugins", f"XCL_SRC={xcl_src}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        xcl_source.skip(f"make plugins failed:\n{result.stdout}\n{result.stderr}")
    return PLUGINS


@pytest.fixture
def run_parity(engine: Path, plugins_dir: Path, parity_fixtures: Path, tmp_path: Path) -> RunParity:
    """Run both parity programs on a fixture by name and return the two decoded records, Go first."""

    def run(name: str) -> tuple[dict[str, Any], dict[str, Any]]:
        fixture = parity_fixtures / name
        assert fixture.is_dir(), f"no parity fixture named {name} in {parity_fixtures}"

        go_out = tmp_path / "go.json"
        python_out = tmp_path / "python.json"

        _run_program(
            "go",
            [str(plugins_dir / xcl_source.executable("parity")), "-fixture", str(fixture), "-plugins", str(plugins_dir), "-out", str(go_out)],
        )
        _run_program(
            "python",
            [sys.executable, str(RUN_PYTHON), "--fixture", str(fixture), "--plugins", str(plugins_dir), "--out", str(python_out)],
        )

        return json.loads(go_out.read_text()), json.loads(python_out.read_text())

    return run


def _run_program(side: str, command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        pytest.fail(
            f"the {side} parity program failed with status {completed.returncode}\n"
            f"command: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
