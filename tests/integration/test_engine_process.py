"""The engine program's life beside the host process, against the real ``xcl-core``.

Every test that depends on process state runs its scenario in a fresh
interpreter, so the engine it watches belongs to that interpreter alone and
not to whichever engine this test process happens to be running. The scripts
print what they observe as ``key:value`` lines, and the tests read them back.
Every wait is bounded, and every process a test starts is ended before it
returns.
"""

from __future__ import annotations

import os
import queue
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from xcl._transport.inprocess import library_filename
from xcl._transport.subprocess import program_filename
from xcl._version import __version__

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

pytestmark = [pytest.mark.subprocess_only, pytest.mark.usefixtures("engine")]

# how long a test waits for an engine to disappear, in seconds
ENGINE_GONE_TIMEOUT = 5.0

# how long a test waits for a script's next line or its exit, in seconds
SCRIPT_TIMEOUT = 60.0

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals and process groups are not available on Windows")
fork_only = pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is not available on this platform")

PREAMBLE = f"import sys\nsys.path[:0] = [{str(ROOT)!r}, {str(HERE)!r}]\n"

WEB = """
sync_app "web" {
  image = "nginx"
}
"""


# -- helpers ----------------------------------------------------------------


def process_alive(pid: int) -> bool:
    """Whether the process ``pid`` is still running; a zombie awaiting its parent counts as gone."""
    if sys.platform == "win32":
        return _windows_process_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        try:
            # the state follows the command name, which is in parentheses
            state = stat.read_text().rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            return False
        return state not in ("Z", "X")
    return True


def _windows_process_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def wait_until_gone(pid: int, timeout: float = ENGINE_GONE_TIMEOUT) -> bool:
    """Wait up to ``timeout`` seconds for ``pid`` to disappear; True when it has."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_alive(pid):
            return True
        time.sleep(0.05)
    return not process_alive(pid)


def end_process(pid: int) -> None:
    """Make sure a process a test left behind is gone, whatever the test concluded."""
    if not process_alive(pid):
        return
    try:
        os.kill(pid, signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM)
    except OSError:
        pass


def child_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    """The environment of a script: this one's, with its own HOME, since plugins are cached there."""
    env = dict(os.environ)
    env["HOME"] = str(tmp_path / "home")
    env.update(overrides)
    return env


def run_script(script: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run ``script`` in a fresh interpreter that imports xcl from this checkout, and wait for it."""
    return subprocess.run(
        [sys.executable, "-c", PREAMBLE + textwrap.dedent(script)],
        cwd=ROOT,
        env=child_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=SCRIPT_TIMEOUT,
    )


class Script:
    """A script running in a fresh interpreter, whose output lines are read with a timeout."""

    def __init__(self, script: str, tmp_path: Path, **popen: object) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-c", PREAMBLE + textwrap.dedent(script)],
            cwd=ROOT,
            env=child_env(tmp_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **popen,  # type: ignore[arg-type]
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.stdout: list[str] = []
        self.stderr: list[str] = []
        self._readers = [
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        ]
        for reader in self._readers:
            reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.stdout.append(line)
            self.lines.put(line.rstrip("\n"))
        self.lines.put(None)

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self.stderr.append(line)

    def expect(self, prefix: str, timeout: float = SCRIPT_TIMEOUT) -> str:
        """The value of the next line starting ``prefix``, skipping others; fails if none arrives in time."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                pytest.fail(f"the script printed no {prefix!r} line within {timeout}s; stderr:\n{''.join(self.stderr)}")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                pytest.fail(f"the script ended without printing a {prefix!r} line; stderr:\n{''.join(self.stderr)}")
            if line.startswith(prefix):
                return line[len(prefix) :]

    def wait(self, timeout: float = SCRIPT_TIMEOUT) -> int:
        """Wait for the script to exit and its output to be read; kills it if it overruns."""
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=timeout)
            pytest.fail(f"the script did not exit within {timeout}s; stderr:\n{''.join(self.stderr)}")
        for reader in self._readers:
            reader.join(timeout=timeout)
        return self.process.returncode

    def close(self) -> None:
        """End the script if it is still running, and close its pipes."""
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=SCRIPT_TIMEOUT)
        for reader in self._readers:
            reader.join(timeout=SCRIPT_TIMEOUT)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass


def output_values(stdout: str, prefix: str) -> list[str]:
    """The values of every line of ``stdout`` starting ``prefix``."""
    return [line[len(prefix) :] for line in stdout.splitlines() if line.startswith(prefix)]


def write_config(directory: Path, text: str, name: str = "main.xcl") -> Path:
    path = directory / name
    path.write_text(textwrap.dedent(text).lstrip())
    return path


def copy_package(destination: Path, *, without: tuple[str, ...] = ()) -> Path:
    """Copy the ``xcl`` package of this checkout into ``destination``, leaving out ``without``; returns the copy."""
    copy = destination / "xcl"
    shutil.copytree(ROOT / "xcl", copy, ignore=shutil.ignore_patterns("__pycache__", *without))
    return copy


def run_copied_package(script: str, tmp_path: Path, package_parent: Path) -> subprocess.CompletedProcess[str]:
    """Run ``script`` in a fresh interpreter that imports xcl from the copy under ``package_parent``.

    The script runs from ``tmp_path``, not the checkout, so the checkout's
    package is not on the path ahead of the copy, and the transport and
    library overrides are cleared so the copy's own layout decides.
    """
    env = child_env(tmp_path, PYTHONPATH=str(package_parent))
    env.pop("XCL_TRANSPORT", None)
    env.pop("XCL_LIBRARY_PATH", None)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=SCRIPT_TIMEOUT,
    )


# -- one engine per interpreter ---------------------------------------------


SHARED_ENGINE = """
import glob, os
import xcl
from xcl._client import default_client

configs = []
for _ in range(3):
    configs.append(xcl.Config())
    print("pid:%d" % default_client().transport.pid, flush=True)

# the engine programs among this interpreter's children, where Linux lists them
children = []
for path in glob.glob("/proc/self/task/*/children"):
    with open(path) as listing:
        children.extend(listing.read().split())
if children:
    cores = 0
    for child in children:
        try:
            with open("/proc/%s/comm" % child) as comm:
                if comm.read().strip() == "xcl-core":
                    cores += 1
        except OSError:
            pass
    print("cores:%d" % cores, flush=True)
else:
    print("cores:unknown", flush=True)

for config in configs:
    config.close()
"""


def test_three_configurations_share_one_engine(tmp_path):
    result = run_script(SHARED_ENGINE, tmp_path)

    assert result.returncode == 0, result.stderr
    pids = output_values(result.stdout, "pid:")
    assert len(pids) == 3
    assert len(set(pids)) == 1
    cores = output_values(result.stdout, "cores:")
    # the count of engine children is checked only where the platform lists a process's children
    if cores != ["unknown"]:
        assert cores == ["1"]
    assert wait_until_gone(int(pids[0]))


CLOSE_AND_WAIT = """
import sys
import xcl
from xcl._client import default_client

first = xcl.Config()
second = xcl.Config()
print("pid:%d" % default_client().transport.pid, flush=True)
first.close()
second.close()
print("closed:yes", flush=True)
sys.stdin.readline()
"""


def test_closing_last_configuration_stops_engine(tmp_path):
    script = Script(CLOSE_AND_WAIT, tmp_path)
    pid = 0
    try:
        pid = int(script.expect("pid:"))
        script.expect("closed:")

        gone = wait_until_gone(pid)
        host_running = script.process.poll() is None

        assert script.process.stdin is not None
        script.process.stdin.close()
        returncode = script.wait()
    finally:
        script.close()
        if pid:
            end_process(pid)

    assert gone, f"the engine {pid} was still running {ENGINE_GONE_TIMEOUT}s after its last configuration closed"
    assert host_running
    assert returncode == 0, "".join(script.stderr)


EXIT_WITHOUT_CLOSING = """
import xcl
from xcl._client import default_client

config = xcl.Config()
print("pid:%d" % default_client().transport.pid, flush=True)
"""


def test_interpreter_exit_stops_engine(tmp_path):
    result = run_script(EXIT_WITHOUT_CLOSING, tmp_path)
    pid = int(output_values(result.stdout, "pid:")[0])
    try:
        gone = wait_until_gone(pid)
    finally:
        end_process(pid)

    assert result.returncode == 0, result.stderr
    assert gone, f"the engine {pid} was still running {ENGINE_GONE_TIMEOUT}s after its interpreter exited"


SLEEP_WITH_ENGINE = """
import time
import xcl
from xcl._client import default_client

config = xcl.Config()
print("pid:%d" % default_client().transport.pid, flush=True)
time.sleep(60)
"""


def test_killed_host_leaves_no_engine(tmp_path):
    script = Script(SLEEP_WITH_ENGINE, tmp_path)
    pid = 0
    try:
        pid = int(script.expect("pid:"))
        script.process.kill()
        script.wait()

        gone = wait_until_gone(pid)
    finally:
        script.close()
        if pid:
            end_process(pid)

    assert gone, f"the engine {pid} was still running {ENGINE_GONE_TIMEOUT}s after its host was killed"


# -- the engine dying under the host ----------------------------------------


KILL_ENGINE_MID_APPLY = """
import glob, os, signal, threading
import xcl
from xcl._client import default_client
from sync_entities import SyncApp, registry

plugins = xcl.LocalRegistry()
plugins.register_external_plugin({plugin!r})
creating = threading.Event()
outcome = {{}}

def on_event(event):
    if event.resource_id == "resource.slow.one" and event.operation == "create" and event.phase == "start":
        creating.set()

def apply(config):
    try:
        config.apply({slow!r})
        outcome["result"] = "completed"
    except BaseException as error:
        outcome["result"] = type(error).__name__
        outcome["details"] = getattr(error, "details", {{}})

config = xcl.Config(registries=[plugins], state_path={state!r}, on_event=on_event)
pid = default_client().transport.pid
print("pid:%d" % pid, flush=True)
worker = threading.Thread(target=apply, args=(config,), daemon=True)
worker.start()
if not creating.wait(30):
    print("creating:timeout", flush=True)
    raise SystemExit(2)
# the plugins the engine started outlive an engine ended by SIGKILL; they are
# listed so the test can end them
for listing in glob.glob("/proc/%d/task/*/children" % pid):
    with open(listing) as children:
        for child in children.read().split():
            print("plugin:%s" % child, flush=True)
os.kill(pid, signal.SIGKILL)
worker.join(30)
print("alive:%s" % worker.is_alive(), flush=True)
print("result:%s" % outcome.get("result"), flush=True)
print("signal:%s" % outcome.get("details", {{}}).get("signal"), flush=True)
config.close()

# the host carries on: a new configuration starts a new engine and applies
with xcl.Config(registries=[registry()]) as again:
    print("new-pid:%d" % default_client().transport.pid, flush=True)
    again.apply({web!r})
    print("image:%s" % again.find(SyncApp, "sync_app.web").image, flush=True)
"""


def kill_engine_mid_apply(tmp_path: Path, slow_plugin: Path) -> subprocess.CompletedProcess[str]:
    slow = write_config(
        tmp_path,
        """
        resource "slow" "one" {
          delay_ms = 30000
        }
        """,
        name="slow.xcl",
    )
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    web = write_config(web_dir, WEB)
    script = KILL_ENGINE_MID_APPLY.format(plugin=str(slow_plugin), slow=str(slow), state=str(tmp_path / "state"), web=str(web))
    result = run_script(script, tmp_path)
    for plugin in output_values(result.stdout, "plugin:"):
        end_process(int(plugin))
    return result


@posix_only
def test_engine_killed_mid_apply_raises_engine_exited(tmp_path, slow_plugin):
    result = kill_engine_mid_apply(tmp_path, slow_plugin)

    assert "alive:False" in result.stdout, result.stderr
    assert "result:EngineExitedError" in result.stdout, result.stderr
    assert "signal:SIGKILL" in result.stdout, result.stderr


@posix_only
def test_host_survives_engine_death_and_new_config_applies(tmp_path, slow_plugin):
    result = kill_engine_mid_apply(tmp_path, slow_plugin)

    assert result.returncode == 0, result.stderr
    old_pid = output_values(result.stdout, "pid:")[0]
    new_pid = output_values(result.stdout, "new-pid:")[0]
    assert new_pid != old_pid
    assert output_values(result.stdout, "image:") == ["nginx"]


# -- Ctrl-C at a terminal ---------------------------------------------------


INTERRUPTED_SEQUENCE = """
import signal
import xcl
from xcl._client import default_client

signal.signal(signal.SIGINT, signal.default_int_handler)
plugins = xcl.LocalRegistry()
plugins.register_external_plugin({plugin!r})

def on_event(event):
    if event.resource_id == "resource.slow.one" and event.operation == "create" and event.phase == "success":
        print("first:created", flush=True)

config = xcl.Config(registries=[plugins], state_path={state!r}, on_event=on_event)
print("pid:%d" % default_client().transport.pid, flush=True)
try:
    config.apply({config_path!r})
    print("outcome:completed", flush=True)
except KeyboardInterrupt:
    print("outcome:interrupted", flush=True)
config.close()

with xcl.Config(registries=[plugins], state_path={state!r}) as saved:
    saved.load()
    for name in ("one", "three"):
        try:
            saved.find(None, "resource.slow." + name)
            print("saved-%s:yes" % name, flush=True)
        except xcl.NotFoundError:
            print("saved-%s:no" % name, flush=True)
"""


@posix_only
def test_interrupt_to_process_group_cancels_apply(tmp_path, slow_plugin):
    config = write_config(
        tmp_path,
        """
        resource "slow" "one" {
          delay_ms = 200
        }

        resource "slow" "two" {
          delay_ms = 1500
          depends_on = ["resource.slow.one"]
        }

        resource "slow" "three" {
          delay_ms = 1500
          depends_on = ["resource.slow.two"]
        }
        """,
    )
    source = INTERRUPTED_SEQUENCE.format(plugin=str(slow_plugin), state=str(tmp_path / "state"), config_path=str(config))
    # a session of its own, as a terminal gives a foreground job, so Ctrl-C
    # reaches every process of the group: the host, its engine and the plugins
    script = Script(source, tmp_path, start_new_session=True)
    pid = 0
    try:
        pid = int(script.expect("pid:"))
        script.expect("first:")
        # the interrupt arrives while the second resource's create is in
        # flight: the engine lets it finish, and starts nothing after it
        time.sleep(0.5)
        began = time.monotonic()
        os.killpg(script.process.pid, signal.SIGINT)
        returncode = script.wait(timeout=20)
        elapsed = time.monotonic() - began
        gone = wait_until_gone(pid)
    finally:
        script.close()
        if pid:
            end_process(pid)
        try:
            os.killpg(script.process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    stdout = "".join(script.stdout)
    assert returncode == 0, "".join(script.stderr)
    assert "outcome:interrupted" in stdout
    assert "outcome:completed" not in stdout
    assert "saved-one:yes" in stdout
    assert "saved-three:no" in stdout
    assert elapsed < 10
    assert gone, f"the engine {pid} was still running {ENGINE_GONE_TIMEOUT}s after the interrupted host exited"


# -- fork --------------------------------------------------------------------


FORKED_CHILD_OWN_CONFIG = """
import os, warnings
import xcl
from xcl._client import default_client
from sync_entities import SyncApp, registry

warnings.simplefilter("ignore", DeprecationWarning)
parent = xcl.Config(registries=[registry()])
parent.apply({web!r})
print("parent-pid:%d" % default_client().transport.pid, flush=True)

child = os.fork()
if child == 0:
    code = 4
    try:
        with xcl.Config(registries=[registry()]) as own:
            print("child-pid:%d" % default_client().transport.pid, flush=True)
            own.apply({web!r})
            code = 0 if own.find(SyncApp, "sync_app.web").image == "nginx" else 5
    except BaseException as error:
        print("child-error:%r" % (error,), flush=True)
    os._exit(code)

_, status = os.waitpid(child, 0)
print("child-exit:%d" % os.waitstatus_to_exitcode(status), flush=True)
print("parent-image:%s" % parent.find(SyncApp, "sync_app.web").image, flush=True)
parent.close()
"""


@fork_only
def test_forked_child_applies_own_configuration(tmp_path):
    web = write_config(tmp_path, WEB)

    result = run_script(FORKED_CHILD_OWN_CONFIG.format(web=str(web)), tmp_path)

    assert result.returncode == 0, result.stderr
    assert output_values(result.stdout, "child-exit:") == ["0"], result.stdout
    assert output_values(result.stdout, "child-pid:") != output_values(result.stdout, "parent-pid:")
    assert output_values(result.stdout, "parent-image:") == ["nginx"]


FORKED_CHILD_PARENT_CONFIG = """
import os, warnings
import xcl
from sync_entities import SyncApp, registry

warnings.simplefilter("ignore", DeprecationWarning)
parent = xcl.Config(registries=[registry()])
parent.apply({web!r})

child = os.fork()
if child == 0:
    code = 4
    try:
        parent.find(SyncApp, "sync_app.web")
        code = 0
    except xcl.ForkedProcessError as error:
        print("fork-error:%s" % error.message, flush=True)
        code = 3
    except BaseException as error:
        print("child-error:%r" % (error,), flush=True)
    os._exit(code)

_, status = os.waitpid(child, 0)
print("child-exit:%d" % os.waitstatus_to_exitcode(status), flush=True)
parent.close()
"""


@fork_only
def test_forked_child_parent_configuration_raises_fork_error(tmp_path):
    web = write_config(tmp_path, WEB)

    result = run_script(FORKED_CHILD_PARENT_CONFIG.format(web=str(web)), tmp_path)

    assert result.returncode == 0, result.stderr
    assert output_values(result.stdout, "child-exit:") == ["3"], result.stdout
    message = output_values(result.stdout, "fork-error:")[0]
    assert "create a new xcl.Config in the child after the fork" in message


# -- what the package finds -------------------------------------------------


def xcl_source() -> Path:
    """The xcl checkout to build an engine from: ``XCL_SRC``, or the sibling directory."""
    return Path(os.environ.get("XCL_SRC") or ROOT.parent / "xcl")


VERSION_REFUSED = """
import xcl
print("package:%s" % xcl.__file__, flush=True)
try:
    xcl.Config()
    print("outcome:accepted", flush=True)
except xcl.EngineVersionError as error:
    print("outcome:refused", flush=True)
    print("message:%s" % error.message, flush=True)
"""


def test_engine_of_other_version_refused(tmp_path):
    source = xcl_source()
    if shutil.which("go") is None:
        pytest.skip("go is not on PATH to build an engine of another version")
    if not (source / "Makefile").is_file():
        pytest.skip(f"the xcl checkout is not at {source}; set XCL_SRC")
    packages = tmp_path / "packages"
    copy = copy_package(packages, without=("_bin", "_lib"))
    program = copy / "_bin" / program_filename()
    program.parent.mkdir()
    build = subprocess.run(
        ["make", "-C", str(source), "xcl-core", "XCL_CORE_VERSION=v9.9.9", f"XCL_CORE_OUT={program}"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert build.returncode == 0, f"building the v9.9.9 engine failed:\n{build.stdout}\n{build.stderr}"

    result = run_copied_package(VERSION_REFUSED, tmp_path, packages)

    assert result.returncode == 0, result.stderr
    assert output_values(result.stdout, "package:") == [str(copy / "__init__.py")]
    assert output_values(result.stdout, "outcome:") == ["refused"]
    message = output_values(result.stdout, "message:")[0]
    assert "v9.9.9" in message
    assert __version__ in message


FIRST_CONFIG_TIMED = """
import time
import xcl

began = time.perf_counter()
config = xcl.Config()
took = time.perf_counter() - began
config.close()
print("took:%f" % took, flush=True)
"""


def test_first_config_within_one_second(tmp_path):
    result = run_script(FIRST_CONFIG_TIMED, tmp_path)

    assert result.returncode == 0, result.stderr
    took = float(output_values(result.stdout, "took:")[0])
    assert took < 1.0, f"the first xcl.Config() took {took:.3f}s"


MISSING_PROGRAM = """
import xcl
print("package:%s" % xcl.__file__, flush=True)
xcl.Config()
"""


def test_missing_program_named_on_first_use(tmp_path):
    packages = tmp_path / "packages"
    copy = copy_package(packages, without=("_bin",)).resolve()

    result = run_copied_package(MISSING_PROGRAM, tmp_path, packages)

    assert result.returncode != 0
    assert output_values(result.stdout, "package:") == [str(copy / "__init__.py")]
    assert "xcl._errors.EngineNotFoundError" in result.stderr
    assert str(copy / "_bin" / program_filename()) in result.stderr
    assert str(copy / "_lib" / library_filename()) in result.stderr
