"""The opt-in colour choice: terminal colour for a terminal, plain text for anything else or with NO_COLOR set."""

import io
import os
import sys

import pytest

from xcl.highlight import PLAIN, TERMINAL, for_stream


class Terminal:
    """A stream that says it is a terminal."""

    def isatty(self) -> bool:
        return True


class ClosedTerminal:
    """A terminal stream that has been closed, whose ``isatty`` raises as a closed file's does."""

    def isatty(self) -> bool:
        raise ValueError("I/O operation on closed file")


class NoIsatty:
    """An object written to like a stream that has no ``isatty`` at all."""

    def write(self, text: str) -> int:
        return len(text)


def test_for_stream_terminal_for_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    assert for_stream(Terminal()) is TERMINAL


def test_for_stream_plain_for_stringio(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    assert for_stream(io.StringIO()) is PLAIN


def test_for_stream_plain_for_regular_file(monkeypatch, tmp_path):
    monkeypatch.delenv("NO_COLOR", raising=False)

    with open(tmp_path / "out.txt", "w") as stream:
        assert for_stream(stream) is PLAIN


def test_for_stream_plain_for_tty_with_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")

    assert for_stream(Terminal()) is PLAIN


def test_for_stream_terminal_for_tty_with_empty_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "")

    assert for_stream(Terminal()) is TERMINAL


def test_for_stream_plain_for_closed_stream(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    assert for_stream(ClosedTerminal()) is PLAIN


def test_for_stream_plain_for_object_without_isatty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    assert for_stream(NoIsatty()) is PLAIN


@pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")
def test_for_stream_terminal_for_real_pty(monkeypatch):
    import pty

    monkeypatch.delenv("NO_COLOR", raising=False)
    controller, follower = pty.openpty()
    try:
        with os.fdopen(controller, "w") as stream:
            assert for_stream(stream) is TERMINAL
    finally:
        os.close(follower)
