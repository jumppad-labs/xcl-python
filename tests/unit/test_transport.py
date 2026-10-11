"""The in-process transport, driven through a fake library loader."""

import sys
from pathlib import Path

import pytest

import xcl
from xcl._transport import InProcessTransport
from xcl._transport.inprocess import (
    ForkGuard,
    default_library_path,
    library_filename,
)


class FakeLibrary:
    """The four engine functions, answering with fixed values."""

    def __init__(self, abi: int = 1) -> None:
        self.abi = abi
        self.calls: list[tuple[int, str, bytes]] = []

    def abi_version(self) -> int:
        return self.abi

    def call(self, handle: int, method: str, request: bytes) -> tuple[int, bytes]:
        self.calls.append((handle, method, request))
        return 0, b""

    def release(self, handle: int) -> int:
        return 0


class FakeLoader:
    """Builds a FakeLibrary and records the path it was asked to load."""

    def __init__(self, library: FakeLibrary) -> None:
        self.library = library
        self.paths: list[Path] = []

    def __call__(self, path: Path) -> FakeLibrary:
        self.paths.append(path)
        return self.library


def test_abi_version_mismatch_raises():
    loader = FakeLoader(FakeLibrary(abi=2))
    transport = InProcessTransport("/fake/libxcl.so", loader=loader, guard=ForkGuard())

    with pytest.raises(xcl.EngineVersionError) as raised:
        transport.call(0, "GetVersion", b"")

    error = raised.value
    assert "ABI" in error.message
    assert error.package == "abi 1"
    assert error.engine == "abi 2"
    assert transport.loaded is False


def test_library_loaded_on_first_call_only():
    library = FakeLibrary()
    loader = FakeLoader(library)
    guard = ForkGuard()
    transport = InProcessTransport("/fake/libxcl.so", loader=loader, guard=guard)

    assert transport.loaded is False
    assert guard.is_loaded() is False

    transport.call(0, "GetVersion", b"")
    transport.call(0, "GetVersion", b"")

    assert transport.loaded is True
    assert guard.is_loaded() is True
    assert len(loader.paths) == 1
    assert library.calls == [(0, "GetVersion", b""), (0, "GetVersion", b"")]


def test_loader_receives_configured_path():
    loader = FakeLoader(FakeLibrary())
    transport = InProcessTransport("/somewhere/else/libxcl.so", loader=loader, guard=ForkGuard())

    transport.release(7)

    assert transport.path == Path("/somewhere/else/libxcl.so")
    assert loader.paths == [Path("/somewhere/else/libxcl.so")]


def test_library_path_env_override(monkeypatch):
    monkeypatch.setenv("XCL_LIBRARY_PATH", "/opt/xcl/libxcl.so")

    assert default_library_path() == Path("/opt/xcl/libxcl.so")
    assert InProcessTransport().path == Path("/opt/xcl/libxcl.so")


def test_library_filename_for_platform():
    expected = {"win32": "libxcl.dll", "darwin": "libxcl.dylib"}.get(sys.platform, "libxcl.so")

    assert library_filename() == expected
