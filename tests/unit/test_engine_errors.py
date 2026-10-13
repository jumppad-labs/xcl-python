"""The errors the binding raises when the engine is missing or exits."""

import signal

import pytest

import xcl


def test_engine_not_found_error_names_both_paths():
    error = xcl.EngineNotFoundError(
        program="/opt/xcl/_bin/xcl-core",
        library="/opt/xcl/_lib/libxcl.so",
        transport="subprocess",
    )

    assert error.code == "engine_not_found"
    assert "/opt/xcl/_bin/xcl-core" in error.message
    assert "/opt/xcl/_lib/libxcl.so" in error.message
    assert error.details == {
        "program": "/opt/xcl/_bin/xcl-core",
        "library": "/opt/xcl/_lib/libxcl.so",
        "transport": "subprocess",
    }
    assert error.program == "/opt/xcl/_bin/xcl-core"
    assert error.library == "/opt/xcl/_lib/libxcl.so"
    assert error.transport == "subprocess"


def test_engine_not_found_error_is_an_xcl_error():
    error = xcl.EngineNotFoundError(program="/p", library="/l", transport="inprocess")

    assert isinstance(error, xcl.Error)
    assert "EngineNotFoundError" in xcl.__all__


def test_engine_exited_error_with_exit_status():
    error = xcl.EngineExitedError(3)

    assert error.code == "engine_exited"
    assert error.returncode == 3
    assert error.details == {"status": "3"}
    assert "status 3" in error.message


@pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="SIGKILL is not available on this platform")
def test_engine_exited_error_with_signal():
    error = xcl.EngineExitedError(-signal.SIGKILL)

    assert error.code == "engine_exited"
    assert error.returncode == -signal.SIGKILL
    assert error.details == {"signal": "SIGKILL"}
    assert "SIGKILL" in error.message


def test_engine_exited_error_is_an_xcl_error():
    error = xcl.EngineExitedError(1)

    assert isinstance(error, xcl.Error)
    assert "EngineExitedError" in xcl.__all__
