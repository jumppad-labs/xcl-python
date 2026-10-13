"""The subprocess transport: the bundled engine program run beside this process.

The engine is ``xcl-core``, a static program every wheel carries in
``xcl/_bin``. The transport starts it with ``xcl-core --serve`` on first use,
never at import, with a pipe pair for its standard input and output and its
standard error inherited, so the engine's diagnostics reach the user. Calls
cross the pipes as frames, a 4-byte big-endian length followed by a
``Request`` or ``Response`` message of ``transport.proto``; the first exchange
is ``GetVersion``, which checks the engine's ABI version.

One engine serves every configuration of the transport. Each call waits for
its own response, matched by id by a single reader thread, so a ``Poll`` that
waits never holds up a call from another thread, and waits in short slices,
which releases the GIL and lets Ctrl-C through on Windows. The engine is
stopped when the last configuration is released, when the transport is
closed and at interpreter exit: its input is closed, which makes it release
every configuration and exit, and it is terminated if it does not exit within
a bounded wait. A host that dies without cleaning up closes the engine's
input all the same; on Windows the engine is also put in a job object that
ends it with the host.

If the engine exits while calls wait on it, every one of them raises
:class:`~xcl.EngineExitedError` with the exit status, and the next call starts
a new engine. The handles the transport gives out are its own, mapped to the
engine that issued each one, so a configuration of an engine that has exited,
or of the parent of a forked child, is refused by name rather than reaching
whichever configuration a new engine numbered the same.
"""

from __future__ import annotations

import atexit
import itertools
import os
import struct
import subprocess
import sys
import threading
import warnings
import weakref
from pathlib import Path
from typing import IO, Any, Callable

from xcl._core import core_pb2, transport_pb2
from xcl._errors import EngineExitedError, EngineNotFoundError, EngineVersionError, ForkedProcessError
from xcl._transport.inprocess import ABI_VERSION, default_library_path

# FRAME_HEADER is the length prefix of every frame on the pipes
FRAME_HEADER = struct.Struct(">I")

# RELEASE_METHOD is the method name the frame protocol reserves for freeing a
# handle; it is not a CoreService method
RELEASE_METHOD = "Release"

# STATUS_UNKNOWN_HANDLE is the engine's status for a handle it never issued
# or has released
STATUS_UNKNOWN_HANDLE = -3

# WAIT_SLICE is how long a call waits for its response at a time, in seconds:
# each slice releases the GIL and gives Ctrl-C a chance to be delivered
WAIT_SLICE = 0.1

# STOP_TIMEOUT bounds, in seconds, how long stopping the engine waits after
# closing its input, and again after terminating it
STOP_TIMEOUT = 5.0

FORKED_MESSAGE = (
    "this configuration was created before the process forked, and its engine belongs to the parent; "
    "create a new xcl.Config in the child after the fork, which starts the child's own engine"
)

Launcher = Callable[..., "subprocess.Popen[bytes]"]


def program_filename() -> str:
    """The file name of the engine program for this platform."""
    return "xcl-core.exe" if sys.platform == "win32" else "xcl-core"


def program_path() -> Path:
    """Where the bundled engine program is: ``xcl/_bin/xcl-core``, ``xcl-core.exe`` on Windows."""
    return Path(__file__).resolve().parent.parent / "_bin" / program_filename()


def signed_status(status: int) -> int:
    """The status a ``Response`` carries as a two's-complement ``uint32``, as a signed value."""
    return status - (1 << 32) if status >= 1 << 31 else status


class _Waiter:
    """One call waiting for its response."""

    __slots__ = ("event", "status", "payload", "exited", "returncode")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.status = 0
        self.payload = b""
        self.exited = False
        self.returncode: int | None = None


class _Engine:
    """One running engine program and everything waiting on it."""

    def __init__(self, process: subprocess.Popen[bytes], generation: int) -> None:
        self.process = process
        self.stdin: IO[bytes] = process.stdin  # type: ignore[assignment]
        self.stdout: IO[bytes] = process.stdout  # type: ignore[assignment]
        self.generation = generation
        # the host process the engine was started by; a forked child differs
        self.host_pid = os.getpid()
        self.waiters: dict[int, _Waiter] = {}
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        # the transport handles of the configurations this engine holds, and
        # how many CreateConfig calls are on their way to it
        self.handles: set[int] = set()
        self.creating = 0
        self.reader: threading.Thread | None = None
        self.job: Any = None
        self.ended = False
        self.returncode: int | None = None


class SubprocessTransport:
    """Calls the engine program, started beside this process on first use.

    ``program`` is the engine program to run, by default :func:`program_path`;
    ``launcher`` starts it, taking :class:`subprocess.Popen`'s arguments, and
    is replaceable for tests. Nothing starts until the first call.
    """

    def __init__(self, program: str | os.PathLike[str] | None = None, *, launcher: Launcher | None = None) -> None:
        self._program = Path(program) if program is not None else program_path()
        self._launcher: Launcher = launcher or subprocess.Popen
        self._lock = threading.Lock()
        self._engine: _Engine | None = None
        self._generations = itertools.count(1)
        self._request_ids = itertools.count(1)
        self._handle_ids = itertools.count(1)
        # every handle given out and not released, mapped to the engine that
        # holds its configuration and that engine's own handle for it
        self._handles: dict[int, tuple[_Engine, int]] = {}

        reference = weakref.ref(self)
        atexit.register(_close_at_exit, reference)
        if hasattr(os, "register_at_fork"):
            os.register_at_fork(after_in_child=lambda: _after_fork_in_child(reference))

    @property
    def program(self) -> Path:
        """The engine program this transport runs."""
        return self._program

    @property
    def pid(self) -> int | None:
        """The process id of the running engine, or None when none is running."""
        engine = self._engine
        if engine is None or engine.ended or engine.host_pid != os.getpid():
            return None
        return engine.process.pid

    def call(self, handle: int, method: str, request: bytes) -> tuple[int, bytes]:
        if handle == 0:
            return self._call_without_handle(method, request)

        engine, engine_handle = self._resolve(handle)
        if engine is None:
            return STATUS_UNKNOWN_HANDLE, b""
        return self._exchange(engine, engine_handle, method, request)

    def release(self, handle: int) -> int:
        with self._lock:
            entry = self._handles.pop(handle, None)
        if entry is None:
            return STATUS_UNKNOWN_HANDLE

        engine, engine_handle = entry
        if engine.host_pid != os.getpid() or engine.ended:
            # the configuration went with its engine, or belongs to the
            # parent; there is nothing left to free here
            return 0

        try:
            status, _ = self._exchange(engine, engine_handle, RELEASE_METHOD, b"")
        except EngineExitedError:
            status = 0

        stop = False
        with self._lock:
            engine.handles.discard(handle)
            if not engine.handles and engine.creating == 0 and self._engine is engine:
                self._engine = None
                stop = True
        if stop:
            _stop(engine)
        return status

    def close(self) -> None:
        """Stop the engine now, if one is running. A later call starts a new one."""
        with self._lock:
            engine = self._engine
            self._engine = None
        if engine is not None and engine.host_pid == os.getpid():
            _stop(engine)

    def _call_without_handle(self, method: str, request: bytes) -> tuple[int, bytes]:
        creating = method == "CreateConfig"
        with self._lock:
            engine = self._running_engine()
            if creating:
                engine.creating += 1

        if not creating:
            return self._exchange(engine, 0, method, request)

        try:
            status, payload = self._exchange(engine, 0, method, request)
            if status != 0:
                return status, payload
            engine_handle = core_pb2.CreateConfigResponse.FromString(payload).handle
            with self._lock:
                handle = next(self._handle_ids)
                self._handles[handle] = (engine, engine_handle)
                engine.handles.add(handle)
            return status, core_pb2.CreateConfigResponse(handle=handle).SerializeToString()
        finally:
            with self._lock:
                engine.creating -= 1

    def _resolve(self, handle: int) -> tuple[_Engine | None, int]:
        """The engine holding ``handle`` and its own handle for it, or None when it is unknown."""
        entry = self._handles.get(handle)
        if entry is None:
            return None, 0
        engine, engine_handle = entry
        if engine.host_pid != os.getpid():
            raise ForkedProcessError(FORKED_MESSAGE)
        if engine.ended:
            raise EngineExitedError(engine.returncode)
        return engine, engine_handle

    def _running_engine(self) -> _Engine:
        """The current engine, started when none is running. Called with the lock held."""
        engine = self._engine
        if engine is not None and not engine.ended and engine.host_pid == os.getpid():
            return engine
        engine = self._start()
        self._engine = engine
        return engine

    def _start(self) -> _Engine:
        if not self._program.is_file():
            raise EngineNotFoundError(program=self._program, library=default_library_path(), transport="subprocess")

        process = self._launcher(
            [str(self._program), "--serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0,
        )
        engine = _Engine(process, next(self._generations))
        if sys.platform == "win32":
            engine.job = _windows_job_assign(process)

        engine.reader = threading.Thread(
            target=self._read,
            args=(engine,),
            name=f"xcl-engine-reader-{engine.generation}",
            daemon=True,
        )
        engine.reader.start()

        # the lock is held here, which the reader takes once the engine has
        # ended, so a failed start does not wait for the reader to finish
        try:
            status, payload = self._exchange(engine, 0, "GetVersion", core_pb2.GetVersionRequest().SerializeToString())
        except BaseException:
            _stop(engine, join_reader=False)
            raise
        abi = core_pb2.GetVersionResponse.FromString(payload).abi_version if status == 0 else None
        if abi != ABI_VERSION:
            _stop(engine, join_reader=False)
            raise EngineVersionError(
                f"the xcl engine at {self._program} implements ABI version {abi}, "
                f"but this package was built for ABI version {ABI_VERSION}; "
                "install the xcl-lang package matching the engine",
                package=f"abi {ABI_VERSION}",
                engine=f"abi {abi}",
            )
        return engine

    def _exchange(self, engine: _Engine, handle: int, method: str, request: bytes) -> tuple[int, bytes]:
        """Send one request to ``engine`` and wait for its response."""
        request_id = next(self._request_ids)
        waiter = _Waiter()
        frame = transport_pb2.Request(id=request_id, handle=handle, method=method, payload=request).SerializeToString()

        with engine.lock:
            if engine.ended:
                raise EngineExitedError(engine.returncode)
            engine.waiters[request_id] = waiter

        try:
            with engine.write_lock:
                _write_all(engine.stdin, FRAME_HEADER.pack(len(frame)) + frame)
        except (OSError, ValueError):
            # the engine has gone, or is being stopped: the reader reports
            # its exit to every waiter once its output ends
            pass

        while not waiter.event.wait(WAIT_SLICE):
            pass

        if waiter.exited:
            raise EngineExitedError(waiter.returncode)
        return signed_status(waiter.status), waiter.payload

    def _read(self, engine: _Engine) -> None:
        """Hand each response to the call waiting for it, until the engine's output ends."""
        try:
            while True:
                header = _read_exact(engine.stdout, FRAME_HEADER.size)
                if header is None:
                    break
                (size,) = FRAME_HEADER.unpack(header)
                body = _read_exact(engine.stdout, size)
                if body is None:
                    break
                response = transport_pb2.Response.FromString(body)
                with engine.lock:
                    waiter = engine.waiters.pop(response.id, None)
                if waiter is not None:
                    waiter.status = response.status
                    waiter.payload = response.payload
                    waiter.event.set()
        except Exception:  # noqa: BLE001 - a broken pipe or a garbled frame both end the engine
            pass
        self._ended(engine)

    def _ended(self, engine: _Engine) -> None:
        """Record that ``engine`` has stopped and fail every call still waiting on it."""
        returncode = _reap(engine.process)
        with engine.lock:
            engine.returncode = returncode
            engine.ended = True
            waiters = list(engine.waiters.values())
            engine.waiters.clear()
        # waiters are failed before the transport's lock is taken: a start
        # holds that lock while it waits for the engine's first answer
        for waiter in waiters:
            waiter.returncode = returncode
            waiter.exited = True
            waiter.event.set()
        with self._lock:
            if self._engine is engine:
                self._engine = None

    def _after_fork_in_child(self) -> None:
        """Forget the parent's engine in a forked child, leaving the parent's process alone."""
        self._lock = threading.Lock()
        engine = self._engine
        self._engine = None
        if engine is None:
            return
        # the child's copies of the pipes would keep the parent's engine
        # alive after the parent died; closing them here touches only the
        # child's descriptors
        for pipe in (engine.stdin, engine.stdout):
            try:
                pipe.close()
            except (OSError, ValueError):
                pass


def _close_at_exit(reference: weakref.ref[SubprocessTransport]) -> None:
    transport = reference()
    if transport is not None:
        transport.close()


def _after_fork_in_child(reference: weakref.ref[SubprocessTransport]) -> None:
    transport = reference()
    if transport is not None:
        transport._after_fork_in_child()


def _stop(engine: _Engine, *, join_reader: bool = True) -> None:
    """Stop ``engine``: close its input, which makes it release everything and exit, then end it if it lingers."""
    try:
        engine.stdin.close()
    except (OSError, ValueError):
        pass

    process = engine.process
    try:
        process.wait(timeout=STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    reader = engine.reader
    if join_reader and reader is not None and reader is not threading.current_thread():
        reader.join(timeout=STOP_TIMEOUT)

    if engine.job is not None:
        _windows_close_handle(engine.job)
        engine.job = None


def _reap(process: subprocess.Popen[bytes]) -> int | None:
    """Wait for a process whose output has ended and return its exit status."""
    try:
        return process.wait(timeout=STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait()


def _write_all(pipe: IO[bytes], data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = pipe.write(view)
        if written is None:
            raise OSError("the engine's input is not ready")
        view = view[written:]


def _read_exact(pipe: IO[bytes], size: int) -> bytes | None:
    """Read exactly ``size`` bytes, or None when the pipe ends first."""
    chunks = []
    remaining = size
    while remaining:
        chunk = pipe.read(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


# JOB_OBJECT_EXTENDED_LIMIT_INFORMATION is information class 9, and
# JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE ends every process in the job when its
# last handle closes, which is when the host process ends
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


def _windows_job_assign(process: subprocess.Popen[bytes]) -> Any:
    """Put the engine in a new job object that ends it when this process ends, returning the job's handle.

    The handle is kept open until the engine is stopped; when the host dies,
    Windows closes it and so ends the engine. A failure leaves the engine
    running without the job, still ended by the end of its input.
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

    class IOCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IOCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        warnings.warn(f"xcl: unable to create a job object for the engine: {ctypes.WinError(ctypes.get_last_error())}", RuntimeWarning, stacklevel=2)  # type: ignore[attr-defined]
        return None

    info = ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    assigned = kernel32.SetInformationJobObject(
        job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
    ) and kernel32.AssignProcessToJobObject(job, int(process._handle))  # type: ignore[attr-defined]
    if not assigned:
        error = ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        kernel32.CloseHandle(job)
        warnings.warn(f"xcl: unable to put the engine in a job object: {error}", RuntimeWarning, stacklevel=2)
        return None
    return job


def _windows_close_handle(handle: Any) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle(handle)
