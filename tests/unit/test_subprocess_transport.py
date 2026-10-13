"""The subprocess transport, driven against a fake engine program.

The fake engine, ``tests/fake_engine.py``, speaks the same frame protocol as
the real ``xcl-core --serve`` and adds a few test-only methods (``Echo``,
``Status``, ``Exit`` and ``Kill``) so the transport's handling of concurrent
calls, signed statuses and an engine that dies can be exercised directly.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

import xcl
from xcl._core import core_pb2
from xcl._transport.subprocess import SubprocessTransport, signed_status

FAKE_ENGINE = Path(__file__).resolve().parent.parent / "fake_engine.py"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# how long a test waits for anything the fake engine does, in seconds
TIMEOUT = 10.0

fork_only = pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is not available on this platform")
posix_only = pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="SIGKILL is not available on this platform")
# the child only uses the transport and exits, so forking a process with the
# transport's reader thread running is safe here, and Python's warning about
# forking a multi-threaded process is silenced
fork_quietly = pytest.mark.filterwarnings("ignore:This process .* is multi-threaded:DeprecationWarning")

EXIT_PASSED = 0
EXIT_FORKED_ERROR = 3
EXIT_WRONG_MESSAGE = 4
EXIT_OTHER_ERROR = 5
EXIT_NO_ERROR = 6
EXIT_SAME_ENGINE = 7


class FakeLauncher:
    """Starts the fake engine in place of the program, recording each launch.

    The program arguments the transport passes are recorded and otherwise
    ignored; ``env``, when given, is the fake engine's whole environment on
    top of this process's. ``FAKE_LAUNCHER_PID`` tells the fake engine which
    process started it, so it can tell when an interpreter stub sits between.
    """

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = env
        self.launches: list[tuple[list[str], dict]] = []
        self.processes: list[subprocess.Popen[bytes]] = []

    def __call__(self, args: list[str], **kwargs) -> subprocess.Popen[bytes]:
        self.launches.append((list(args), dict(kwargs)))
        kwargs["env"] = {**os.environ, **(self.env or {}), "FAKE_LAUNCHER_PID": str(os.getpid())}
        process = subprocess.Popen([sys.executable, str(FAKE_ENGINE)], **kwargs)
        self.processes.append(process)
        return process

    def kill_all(self) -> None:
        """End every fake engine still running, so none outlives its test."""
        for process in self.processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=TIMEOUT)


def close_everything(transport: SubprocessTransport, launcher: FakeLauncher) -> None:
    transport.close()
    launcher.kill_all()


@pytest.fixture
def launcher():
    return FakeLauncher()


@pytest.fixture
def transport(launcher):
    transport = SubprocessTransport(program=FAKE_ENGINE, launcher=launcher)
    yield transport
    close_everything(transport, launcher)


def create_config(transport: SubprocessTransport) -> int:
    status, payload = transport.call(0, "CreateConfig", core_pb2.CreateConfigRequest().SerializeToString())
    assert status == 0
    return core_pb2.CreateConfigResponse.FromString(payload).handle


def echo_payload(tag: str, delay_ms: int, started_file: Path | None = None) -> bytes:
    options: dict = {"tag": tag, "delay_ms": delay_ms}
    if started_file is not None:
        options["started_file"] = str(started_file)
    return json.dumps(options).encode("utf-8")


def wait_for_file(path: Path) -> None:
    deadline = time.monotonic() + TIMEOUT
    while not path.exists():
        assert time.monotonic() < deadline, f"the fake engine never created {path}"
        time.sleep(0.01)


class CallInThread:
    """Runs one transport call on its own thread, keeping its result or the exception it raised."""

    def __init__(self, transport: SubprocessTransport, handle: int, method: str, request: bytes) -> None:
        self.result: tuple[int, bytes] | None = None
        self.error: BaseException | None = None
        self.finished_at: float | None = None
        self.thread = threading.Thread(target=self._run, args=(transport, handle, method, request), daemon=True)
        self.thread.start()

    def _run(self, transport: SubprocessTransport, handle: int, method: str, request: bytes) -> None:
        try:
            self.result = transport.call(handle, method, request)
        except BaseException as error:  # noqa: BLE001 - the test inspects whatever was raised
            self.error = error
        self.finished_at = time.monotonic()

    def join(self) -> None:
        self.thread.join(timeout=TIMEOUT)
        assert not self.thread.is_alive(), "the call did not finish in time"


def test_engine_not_started_at_construction(launcher):
    transport = SubprocessTransport(program=FAKE_ENGINE, launcher=launcher)
    try:
        assert transport.pid is None
        assert launcher.launches == []
        assert transport.program == FAKE_ENGINE
    finally:
        close_everything(transport, launcher)


def test_first_call_starts_engine(transport, launcher):
    create_config(transport)

    assert transport.pid is not None
    assert transport.pid == launcher.processes[0].pid
    assert len(launcher.launches) == 1
    args, kwargs = launcher.launches[0]
    assert args == [str(FAKE_ENGINE), "--serve"]
    assert kwargs["stdin"] == subprocess.PIPE
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["stderr"] is None
    assert kwargs["bufsize"] == 0


def test_concurrent_calls_get_their_own_responses(transport, tmp_path):
    handle = create_config(transport)
    slow_started = tmp_path / "slow-started"
    slow_request = echo_payload("slow", 500, started_file=slow_started)
    fast_request = echo_payload("fast", 0)

    slow = CallInThread(transport, handle, "Echo", slow_request)
    wait_for_file(slow_started)
    fast = CallInThread(transport, handle, "Echo", fast_request)
    fast.join()
    slow.join()

    assert slow.error is None
    assert fast.error is None
    assert slow.result == (0, slow_request)
    assert fast.result == (0, fast_request)
    assert fast.finished_at < slow.finished_at


def test_several_configurations_share_one_engine(transport, launcher):
    create_config(transport)
    first_pid = transport.pid
    create_config(transport)
    create_config(transport)

    assert len(launcher.launches) == 1
    assert transport.pid == first_pid


def test_configurations_get_distinct_handles(transport):
    first = create_config(transport)
    second = create_config(transport)

    assert first != 0
    assert second != 0
    assert first != second


def test_releasing_last_handle_stops_engine(transport, launcher):
    handle = create_config(transport)

    status = transport.release(handle)

    assert status == 0
    assert transport.pid is None
    assert launcher.processes[0].poll() == 0


def test_releasing_one_of_two_handles_keeps_engine(transport, launcher):
    first = create_config(transport)
    create_config(transport)
    pid = transport.pid

    status = transport.release(first)

    assert status == 0
    assert transport.pid == pid
    assert launcher.processes[0].poll() is None


def test_close_stops_engine(transport, launcher):
    create_config(transport)

    transport.close()

    assert transport.pid is None
    assert launcher.processes[0].poll() == 0


def test_engine_exit_fails_waiting_call_with_status(transport, tmp_path):
    handle = create_config(transport)
    started = tmp_path / "started"
    waiting = CallInThread(transport, handle, "Echo", echo_payload("waiting", 60_000, started_file=started))
    wait_for_file(started)

    with pytest.raises(xcl.EngineExitedError):
        transport.call(handle, "Exit", b"3")
    waiting.join()

    assert isinstance(waiting.error, xcl.EngineExitedError)
    assert waiting.error.returncode == 3
    assert waiting.error.details == {"status": "3"}
    assert waiting.error.code == "engine_exited"


@posix_only
def test_engine_killed_fails_waiting_call_with_signal(transport, tmp_path):
    handle = create_config(transport)
    started = tmp_path / "started"
    waiting = CallInThread(transport, handle, "Echo", echo_payload("waiting", 60_000, started_file=started))
    wait_for_file(started)

    with pytest.raises(xcl.EngineExitedError):
        transport.call(handle, "Kill", b"")
    waiting.join()

    assert isinstance(waiting.error, xcl.EngineExitedError)
    assert waiting.error.returncode == -signal.SIGKILL
    assert waiting.error.details == {"signal": "SIGKILL"}


def test_next_call_after_exit_starts_new_engine(transport, launcher):
    handle = create_config(transport)
    first_pid = transport.pid
    with pytest.raises(xcl.EngineExitedError):
        transport.call(handle, "Exit", b"3")

    create_config(transport)

    assert len(launcher.launches) == 2
    assert transport.pid is not None
    assert transport.pid != first_pid
    assert transport.pid == launcher.processes[1].pid


def test_handle_from_dead_engine_raises_engine_exited(transport):
    handle = create_config(transport)
    with pytest.raises(xcl.EngineExitedError):
        transport.call(handle, "Exit", b"3")

    with pytest.raises(xcl.EngineExitedError) as raised:
        transport.call(handle, "Echo", echo_payload("after", 0))

    assert raised.value.returncode == 3


def test_handle_from_dead_engine_does_not_reach_new_engine(transport, launcher):
    old_handle = create_config(transport)
    with pytest.raises(xcl.EngineExitedError):
        transport.call(old_handle, "Exit", b"3")
    # the new engine numbers its first configuration 1, as the dead one did
    new_handle = create_config(transport)
    assert len(launcher.launches) == 2

    with pytest.raises(xcl.EngineExitedError):
        transport.call(old_handle, "Echo", echo_payload("after", 0))

    assert new_handle != old_handle


def test_releasing_handle_from_dead_engine_is_quiet(transport):
    handle = create_config(transport)
    with pytest.raises(xcl.EngineExitedError):
        transport.call(handle, "Exit", b"3")

    status = transport.release(handle)

    assert status == 0


def test_unknown_handle_returns_unknown_handle_status(transport, launcher):
    status, payload = transport.call(999, "Echo", echo_payload("unknown", 0))

    assert status == -3
    assert payload == b""
    assert launcher.launches == []


def test_abi_mismatch_refused_naming_both():
    launcher = FakeLauncher(env={"FAKE_ABI": "2"})
    transport = SubprocessTransport(program=FAKE_ENGINE, launcher=launcher)
    try:
        with pytest.raises(xcl.EngineVersionError) as raised:
            create_config(transport)

        error = raised.value
        assert error.details == {"package": "abi 1", "engine": "abi 2"}
        assert error.package == "abi 1"
        assert error.engine == "abi 2"
        assert "ABI" in error.message
        assert transport.pid is None
        assert launcher.processes[0].poll() is not None
    finally:
        close_everything(transport, launcher)


def test_negative_status_decoded_signed(transport):
    status, payload = transport.call(0, "Status", b"-4")

    assert status == -4
    assert payload == b""


def test_missing_program_raises_engine_not_found(launcher, tmp_path):
    missing = tmp_path / "no-such-engine"
    transport = SubprocessTransport(program=missing, launcher=launcher)
    try:
        with pytest.raises(xcl.EngineNotFoundError) as raised:
            create_config(transport)

        error = raised.value
        assert error.code == "engine_not_found"
        assert error.details["program"] == str(missing)
        assert error.details["transport"] == "subprocess"
        assert launcher.launches == []
    finally:
        close_everything(transport, launcher)


@fork_only
@fork_quietly
def test_forked_child_old_handle_raises_forked_error(transport):
    handle = create_config(transport)

    pid = os.fork()
    if pid == 0:
        try:
            transport.call(handle, "Echo", echo_payload("child", 0))
        except xcl.ForkedProcessError as error:
            if "create a new xcl.Config in the child after the fork" in error.message:
                os._exit(EXIT_FORKED_ERROR)
            os._exit(EXIT_WRONG_MESSAGE)
        except BaseException:
            os._exit(EXIT_OTHER_ERROR)
        os._exit(EXIT_NO_ERROR)
    _, wait_status = os.waitpid(pid, 0)
    exit_code = os.waitstatus_to_exitcode(wait_status)

    assert exit_code == EXIT_FORKED_ERROR
    # the parent's configuration still reaches the parent's engine
    request = echo_payload("parent", 0)
    assert transport.call(handle, "Echo", request) == (0, request)


@fork_only
@fork_quietly
def test_forked_child_new_configuration_starts_own_engine(transport):
    create_config(transport)
    parent_engine_pid = transport.pid

    pid = os.fork()
    if pid == 0:
        try:
            create_config(transport)
            child_engine_pid = transport.pid
            transport.close()
        except BaseException:
            os._exit(EXIT_OTHER_ERROR)
        if child_engine_pid is None or child_engine_pid == parent_engine_pid:
            os._exit(EXIT_SAME_ENGINE)
        os._exit(EXIT_PASSED)
    _, wait_status = os.waitpid(pid, 0)
    exit_code = os.waitstatus_to_exitcode(wait_status)

    assert exit_code == EXIT_PASSED
    # the parent's engine is untouched by the child
    assert transport.pid == parent_engine_pid


def test_engine_stderr_reaches_host_stderr():
    script = textwrap.dedent(
        f"""
        import subprocess
        import sys

        sys.path.insert(0, {str(REPO_ROOT)!r})

        from xcl._transport.subprocess import SubprocessTransport

        def launcher(args, **kwargs):
            return subprocess.Popen([sys.executable, {str(FAKE_ENGINE)!r}], **kwargs)

        transport = SubprocessTransport(program={str(FAKE_ENGINE)!r}, launcher=launcher)
        transport.call(0, "GetVersion", b"")
        transport.close()
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        env={**os.environ, "FAKE_STDERR": "fake-engine-stderr-marker"},
        timeout=TIMEOUT * 3,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"fake-engine-stderr-marker" in result.stderr


def test_signed_status_keeps_positive_value():
    assert signed_status(5) == 5


def test_signed_status_decodes_twos_complement_negative():
    assert signed_status(0xFFFFFFFC) == -4
