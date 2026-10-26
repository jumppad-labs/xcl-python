"""The package's typing as a user's type checker sees it.

Each test writes a small user-style program to a temporary directory and runs
mypy over it in a fresh process, as a user would. No ``MYPYPATH`` is set, so
mypy resolves ``xcl`` as the installed package, which it reads only because
the package ships its ``py.typed`` marker. The programs only construct
configurations inside a function that is never called, so no engine is
needed.
"""

import subprocess
import sys
import textwrap
from pathlib import Path


def run_mypy(directory: Path, program: str) -> subprocess.CompletedProcess[str]:
    path = directory / "program.py"
    path.write_text(textwrap.dedent(program).lstrip())
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--no-incremental", "--no-error-summary", "--hide-error-context", str(path)],
        cwd=directory,
        capture_output=True,
        text=True,
    )


def test_mypy_flags_string_event_data(tmp_path):
    result = run_mypy(
        tmp_path,
        """
        import xcl
        import xcl.aio


        def build() -> None:
            xcl.Config(event_data="processed")
            xcl.aio.Config(event_data="processed")
        """,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    errors = [line for line in result.stdout.splitlines() if ": error:" in line]
    sync_errors = [line for line in errors if "program.py:6:" in line]
    aio_errors = [line for line in errors if "program.py:7:" in line]
    assert len(sync_errors) == 1, result.stdout
    assert "EventDataLevel" in sync_errors[0]
    assert len(aio_errors) == 1, result.stdout
    assert "EventDataLevel" in aio_errors[0]


def test_mypy_accepts_event_data_member(tmp_path):
    result = run_mypy(
        tmp_path,
        """
        import xcl
        import xcl.aio


        def build() -> None:
            xcl.Config(event_data=xcl.EventDataLevel.PROCESSED)
            xcl.aio.Config(event_data=xcl.EventDataLevel.PROCESSED)
        """,
    )

    assert result.returncode == 0, result.stdout + result.stderr
