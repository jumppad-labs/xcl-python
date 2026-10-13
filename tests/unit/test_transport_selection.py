"""Choosing the transport: what the package holds and ``XCL_TRANSPORT`` decide.

The program and the library are stand-in files in a temporary directory: the
selection only looks at whether they exist, and nothing is started or loaded.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import xcl
from xcl._transport import InProcessTransport, SubprocessTransport
from xcl._transport import select


@pytest.fixture
def program(tmp_path, monkeypatch) -> Path:
    """Where the selection looks for the engine program; the file is not created."""
    path = tmp_path / "_bin" / "xcl-core"
    monkeypatch.setattr(select, "program_path", lambda: path)
    return path


@pytest.fixture
def library(tmp_path, monkeypatch) -> Path:
    """Where the selection looks for the shared library; the file is not created."""
    path = tmp_path / "_lib" / "libxcl.so"
    monkeypatch.setattr(select, "default_library_path", lambda: path)
    return path


def create(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"stand-in engine")


def test_default_selects_program_even_with_library_present(program, library, monkeypatch):
    monkeypatch.delenv(select.TRANSPORT_ENV, raising=False)
    create(program)
    create(library)

    transport = select.select_transport()

    assert isinstance(transport, SubprocessTransport)
    assert transport.program == program
    assert transport.pid is None


def test_subprocess_override_selects_program(program, library, monkeypatch):
    monkeypatch.setenv(select.TRANSPORT_ENV, "subprocess")
    create(program)
    create(library)

    transport = select.select_transport()

    assert isinstance(transport, SubprocessTransport)
    assert transport.program == program


def test_inprocess_override_selects_library(program, library, monkeypatch):
    monkeypatch.setenv(select.TRANSPORT_ENV, "inprocess")
    create(program)
    create(library)

    transport = select.select_transport()

    assert isinstance(transport, InProcessTransport)
    assert transport.path == library
    assert transport.loaded is False


def test_unknown_override_value_raises(program, library, monkeypatch):
    monkeypatch.setenv(select.TRANSPORT_ENV, "carrier-pigeon")
    create(program)
    create(library)

    with pytest.raises(ValueError) as raised:
        select.select_transport()

    message = str(raised.value)
    assert "carrier-pigeon" in message
    assert "'subprocess'" in message
    assert "'inprocess'" in message


def test_missing_program_raises_naming_both_paths(program, library, monkeypatch):
    monkeypatch.delenv(select.TRANSPORT_ENV, raising=False)

    with pytest.raises(xcl.EngineNotFoundError) as raised:
        select.select_transport()

    error = raised.value
    assert str(program) in error.message
    assert str(library) in error.message
    assert error.details == {"program": str(program), "library": str(library), "transport": "subprocess"}
    assert error.transport == "subprocess"


def test_missing_library_with_override_raises_naming_both_paths(program, library, monkeypatch):
    monkeypatch.setenv(select.TRANSPORT_ENV, "inprocess")
    create(program)

    with pytest.raises(xcl.EngineNotFoundError) as raised:
        select.select_transport()

    error = raised.value
    assert str(program) in error.message
    assert str(library) in error.message
    assert error.details == {"program": str(program), "library": str(library), "transport": "inprocess"}
    assert error.transport == "inprocess"


def test_missing_program_does_not_fall_back_to_library(program, library, monkeypatch):
    monkeypatch.delenv(select.TRANSPORT_ENV, raising=False)
    create(library)

    with pytest.raises(xcl.EngineNotFoundError) as raised:
        select.select_transport()

    assert raised.value.transport == "subprocess"
