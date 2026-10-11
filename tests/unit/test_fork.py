"""The fork guard, exercised with a real fork()."""

import os

import pytest

import xcl
from xcl._transport.inprocess import ForkGuard

# the child only runs guard.check() and exits, so forking a process whose
# other tests have started the engine's threads is safe here, and Python's
# warning about forking a multi-threaded process is silenced
fork_only = pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is not available on this platform")
fork_quietly = pytest.mark.filterwarnings("ignore:This process .* is multi-threaded:DeprecationWarning")

EXIT_PASSED = 0
EXIT_FORKED_ERROR = 3
EXIT_OTHER_ERROR = 4


def check_in_forked_child(guard: ForkGuard) -> int:
    """Fork, run ``guard.check()`` in the child, and return the child's exit code."""
    pid = os.fork()
    if pid == 0:
        try:
            guard.check()
        except xcl.ForkedProcessError:
            os._exit(EXIT_FORKED_ERROR)
        except BaseException:
            os._exit(EXIT_OTHER_ERROR)
        os._exit(EXIT_PASSED)
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


@fork_only
@fork_quietly
def test_forked_child_after_use_raises():
    guard = ForkGuard()
    guard.loaded()

    exit_code = check_in_forked_child(guard)

    assert exit_code == EXIT_FORKED_ERROR
    # the parent that loaded the engine is unaffected
    guard.check()


@fork_only
@fork_quietly
def test_forked_child_after_import_only_works():
    guard = ForkGuard()

    exit_code = check_in_forked_child(guard)

    assert exit_code == EXIT_PASSED


def test_fork_error_names_spawn_and_post_fork():
    error = xcl.ForkedProcessError()

    assert error.code == "forked_process"
    assert "spawn" in error.message
    assert 'multiprocessing.set_start_method("spawn")' in error.message
    assert "post_fork" in error.message
    assert "worker_process_init" in error.message
