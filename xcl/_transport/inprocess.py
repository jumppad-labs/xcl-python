"""The in-process transport: libxcl loaded into this process.

This route is for a source build only: no wheel carries the shared library.
``make libxcl`` builds it into ``xcl/_lib``, and ``XCL_TRANSPORT=inprocess``
selects it; the default is the bundled engine program, see
:mod:`xcl._transport.subprocess`.

The library is loaded on first use, never at import, because loading a Go
shared library starts the Go runtime and its threads, and a process that
imported xcl and then forks (gunicorn, celery's prefork pool, multiprocessing
with the fork start method) would fork a live Go runtime, which Go does not
support. A parent that imports xcl but never uses it before forking is
therefore safe. For a parent that did use it, the child is marked at fork and
refused with :class:`ForkedProcessError`.

cffi in ABI mode loads the library with the four-function declaration below,
so no extension is compiled and the GIL is released for the duration of each
call; ctypes, which also releases the GIL, is the fallback when cffi is not
installed. Every response buffer the engine allocates is copied into Python
and freed at once with ``xcl_free``.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Callable

from xcl._errors import EngineVersionError, ForkedProcessError

# ABI_VERSION is the C ABI version this package was written against; the
# engine's xcl_abi_version() must equal it
ABI_VERSION = 1

CDEF = """
    uint32_t xcl_abi_version(void);
    int32_t  xcl_call(uint64_t handle, const char *method,
                      const uint8_t *req, size_t req_len,
                      uint8_t **resp, size_t *resp_len);
    void     xcl_free(uint8_t *resp);
    int32_t  xcl_release(uint64_t handle);
"""

# LIBRARY_PATH_ENV names the environment variable that overrides where the
# engine is loaded from, for development against a locally built library
LIBRARY_PATH_ENV = "XCL_LIBRARY_PATH"


def library_filename() -> str:
    """The file name of the engine for this platform."""
    if sys.platform == "win32":
        return "libxcl.dll"
    if sys.platform == "darwin":
        return "libxcl.dylib"
    return "libxcl.so"


def default_library_path() -> Path:
    """Where the engine is loaded from: ``XCL_LIBRARY_PATH``, or the bundled copy."""
    override = os.environ.get(LIBRARY_PATH_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "_lib" / library_filename()


class ForkGuard:
    """Detects use of the engine in a child forked after the engine was loaded.

    ``loaded`` is called once the library is loaded, recording the process it
    was loaded in; ``check`` raises :class:`ForkedProcessError` in any other
    process. A fork hook marks a child of a process that had loaded the
    engine, and the pid comparison catches a fork the hook did not see.
    """

    def __init__(self) -> None:
        self._pid: int | None = None
        self._forked = False
        self._lock = threading.Lock()
        if hasattr(os, "register_at_fork"):
            os.register_at_fork(after_in_child=self._after_fork_in_child)

    def loaded(self) -> None:
        with self._lock:
            self._pid = os.getpid()
            self._forked = False

    def is_loaded(self) -> bool:
        return self._pid is not None

    def _after_fork_in_child(self) -> None:
        # only a child of a process that had loaded the engine is unsafe
        if self._pid is not None:
            self._forked = True

    def check(self) -> None:
        if self._pid is None:
            return
        if self._forked or os.getpid() != self._pid:
            raise ForkedProcessError()


class InProcessTransport:
    """Calls the engine loaded into this process.

    ``path`` is the library to load, by default :func:`default_library_path`;
    ``loader`` builds the library object on first use and is replaceable for
    tests. The ABI version is checked as soon as the library is loaded.
    """

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        loader: Callable[[Path], _Library] | None = None,
        guard: ForkGuard | None = None,
    ) -> None:
        self._path = Path(path) if path is not None else None
        self._loader = loader or load_library
        self._guard = guard if guard is not None else _default_guard
        self._lib: _Library | None = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        """Whether the engine has been loaded by this transport."""
        return self._lib is not None

    @property
    def path(self) -> Path:
        """The library this transport loads."""
        return self._path if self._path is not None else default_library_path()

    def _library(self) -> _Library:
        self._guard.check()
        if self._lib is not None:
            return self._lib
        with self._lock:
            if self._lib is None:
                lib = self._loader(self.path)
                abi = lib.abi_version()
                if abi != ABI_VERSION:
                    raise EngineVersionError(
                        f"the xcl engine at {self.path} implements ABI version {abi}, "
                        f"but this package was built for ABI version {ABI_VERSION}; "
                        "install the xcl-lang package matching the engine",
                        package=f"abi {ABI_VERSION}",
                        engine=f"abi {abi}",
                    )
                self._guard.loaded()
                self._lib = lib
        return self._lib

    def call(self, handle: int, method: str, request: bytes) -> tuple[int, bytes]:
        return self._library().call(handle, method, request)

    def release(self, handle: int) -> int:
        return self._library().release(handle)


class _Library:
    """The four functions of a loaded engine, behind one of two FFIs."""

    def abi_version(self) -> int:
        raise NotImplementedError

    def call(self, handle: int, method: str, request: bytes) -> tuple[int, bytes]:
        raise NotImplementedError

    def release(self, handle: int) -> int:
        raise NotImplementedError


class _CFFILibrary(_Library):
    def __init__(self, path: Path) -> None:
        from cffi import FFI

        self._ffi = FFI()
        self._ffi.cdef(CDEF)
        self._lib = self._ffi.dlopen(str(path))

    def abi_version(self) -> int:
        return int(self._lib.xcl_abi_version())

    def call(self, handle: int, method: str, request: bytes) -> tuple[int, bytes]:
        ffi = self._ffi
        resp = ffi.new("uint8_t **")
        resp_len = ffi.new("size_t *")
        status = self._lib.xcl_call(handle, method.encode(), request, len(request), resp, resp_len)
        try:
            body = bytes(ffi.buffer(resp[0], resp_len[0])) if resp_len[0] else b""
        finally:
            self._lib.xcl_free(resp[0])
        return int(status), body

    def release(self, handle: int) -> int:
        return int(self._lib.xcl_release(handle))


class _CtypesLibrary(_Library):
    def __init__(self, path: Path) -> None:
        import ctypes

        self._ctypes = ctypes
        lib = ctypes.CDLL(str(path))
        lib.xcl_abi_version.restype = ctypes.c_uint32
        lib.xcl_abi_version.argtypes = []
        lib.xcl_call.restype = ctypes.c_int32
        lib.xcl_call.argtypes = [
            ctypes.c_uint64,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lib.xcl_free.restype = None
        lib.xcl_free.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
        lib.xcl_release.restype = ctypes.c_int32
        lib.xcl_release.argtypes = [ctypes.c_uint64]
        self._lib = lib

    def abi_version(self) -> int:
        return int(self._lib.xcl_abi_version())

    def call(self, handle: int, method: str, request: bytes) -> tuple[int, bytes]:
        ctypes = self._ctypes
        req = (ctypes.c_uint8 * len(request)).from_buffer_copy(request) if request else None
        resp = ctypes.POINTER(ctypes.c_uint8)()
        resp_len = ctypes.c_size_t(0)
        status = self._lib.xcl_call(handle, method.encode(), req, len(request), ctypes.byref(resp), ctypes.byref(resp_len))
        try:
            body = ctypes.string_at(resp, resp_len.value) if resp_len.value else b""
        finally:
            self._lib.xcl_free(resp)
        return int(status), body

    def release(self, handle: int) -> int:
        return int(self._lib.xcl_release(handle))


def load_library(path: Path) -> _Library:
    """Load the engine at ``path`` with cffi, or with ctypes when cffi is unavailable."""
    if not path.exists():
        raise OSError(
            f"the xcl engine was not found at {path}; the wheel for this platform bundles it, "
            f"or set {LIBRARY_PATH_ENV} to a locally built libxcl"
        )
    try:
        import cffi  # noqa: F401
    except ImportError:
        return _CtypesLibrary(path)
    return _CFFILibrary(path)


_default_guard = ForkGuard()


def default_guard() -> ForkGuard:
    """The fork guard every in-process transport shares by default."""
    return _default_guard

