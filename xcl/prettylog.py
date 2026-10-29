"""A ready-made pretty logger: every event as a readable, coloured line, set up in one line.

It is the Python form of the event receiver Go's examples share
(``example/prettylog``), written with the standard library and the
package's own printing support. Each event at or above the chosen level is
one line, in the layout Go's example writes:

.. code-block:: text

    3:04PM INFO create start source=core operation=create phase=start resource=resource.recording.one type=recording.one
    3:04PM INFO create success source=core operation=create phase=success resource=resource.recording.one type=recording.one duration=1.2ms
      resource "recording" "one" {
        log    = "/work/log.jsonl"
        output = "one-a"
        value  = "a"
      }

Beneath the line reporting a resource's creation it writes that resource's
configuration, including the values the provider filled in, as soon as the
creation is reported. Beneath the line reporting a configuration mistake it
writes the mistake's report, with the source lines in question. It is set
up in one line, on either client::

    cfg = xcl.Config(
        on_event=xcl.prettylog.handler(sys.stderr, xcl.prettylog.level_from_env()),
        event_data=xcl.EventDataLevel.PROCESSED,  # puts each created resource on its event
    )

    cfg = xcl.aio.Config(on_event=xcl.prettylog.handler(sys.stderr), event_data=xcl.EventDataLevel.PROCESSED)

The configuration needs ``event_data=xcl.EventDataLevel.PROCESSED`` for the
created resources to be shown; without it the logger says so, once.
"""

from __future__ import annotations

import io
import logging
import os
import sys
import threading
from collections.abc import Callable, Sequence
from typing import Final, Optional, TextIO

from xcl import _errors, _logbridge, _prettyline
from xcl._print import format_error
from xcl.events import Event, EventDataLevel
from xcl.highlight._formatters import PLAIN, Formatter
from xcl.highlight._kinds import Kind, Token
from xcl.highlight._stream import for_stream
from xcl.highlight._theme import DEFAULT_THEME

LEVEL_ENV: Final[str] = "XCL_LOG_LEVEL"
"""The environment variable :func:`level_from_env` reads, the one Go's example reads."""

_LEVELS = {
    "debug": logging.DEBUG,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}

# what a run is told, once, when it shows no configuration because the
# configuration delivers events without resource data
_GUIDANCE = "configuration not shown: events carry no resource data"
_GUIDANCE_HINT = "create the configuration with event_data=xcl.EventDataLevel.PROCESSED"

# the warning written for a resource whose configuration cannot be shown
_UNABLE = "unable to show configuration"


def level_from_env() -> int:
    """The level named by ``XCL_LOG_LEVEL``, as Go's ``prettylog.LevelFromEnv`` reads it.

    ``debug``, ``info``, ``warn`` and ``error``, in any letter case, give
    ``logging.DEBUG``, ``INFO``, ``WARNING`` and ``ERROR``; anything else, or
    the variable unset, gives ``logging.INFO``.
    """
    return _LEVELS.get(os.environ.get(LEVEL_ENV, "").lower(), logging.INFO)


def handler(
    file: Optional[TextIO] = None,
    level: int = logging.INFO,
    *,
    logger: Optional[logging.Logger] = None,
    formatter: Optional[Formatter] = None,
) -> Callable[[Event], None]:
    """An ``on_event`` handler writing every event at ``level`` or above as a readable line, as Go's ``prettylog.Handler``.

    ``file`` is the stream written to, ``sys.stderr`` when not given.
    ``level`` is a ``logging`` level, ``logging.INFO`` when not given, or
    :func:`level_from_env` for the one ``XCL_LOG_LEVEL`` names. Each event is
    one line: its time, level and message, then its source, operation,
    phase, resource and any other attributes as ``key=value``, with the
    source, operation and resource highlighted.

    At info and below, beneath the line reporting a resource's creation it
    writes the resource's configuration, with the values the provider filled
    in, rendered from the event's saved record. That needs the configuration
    created with ``event_data=xcl.EventDataLevel.PROCESSED``; when it was
    created without resource data, one line says how to turn it on. A
    resource whose configuration cannot be shown gets one warning line, and
    variables, outputs and modules, which have no configuration form, are
    skipped silently. At every level, beneath the line reporting a
    configuration mistake it writes the mistake's report, with the source
    lines in question, once per problem. Above info nothing else is written.

    Colour is chosen from the stream, with :func:`xcl.highlight.for_stream`:
    terminal colour for a terminal when ``NO_COLOR`` is unset, plain text
    otherwise. ``formatter`` chooses another format.

    With ``logger`` the lines go to that logger rather than a stream, so an
    application's own logging setup carries them: each event is one record,
    at the event's level and time, whose message is the event's line and
    anything written beneath it, plain unless ``formatter`` says otherwise.
    The records carry the event's fields as attributes, as
    :func:`xcl.logging_handler`'s do. Give ``file`` or ``logger``, not both.

    The handler never raises into the operation: a failure to write is
    ignored, as Go's example ignores it. One handler may serve several
    configurations.
    """
    if type(level) is bool or not isinstance(level, int):
        raise TypeError(f"level must be a logging level such as logging.INFO, not {level!r} ({type(level).__name__})")
    if file is not None and logger is not None:
        raise ValueError("give file or logger, not both")
    if logger is not None and not isinstance(logger, logging.Logger):
        raise TypeError(f"logger must be a logging.Logger, not {logger!r} ({type(logger).__name__})")
    stream: Optional[TextIO] = None
    if logger is None:
        stream = sys.stderr if file is None else file
    if formatter is None:
        formatter = PLAIN if logger is not None else for_stream(stream)
    return _PrettyLog(stream, level, logger, formatter)


class _PrettyLog:
    """The handler :func:`handler` returns: decides what to write for each event, and writes it."""

    def __init__(self, stream: Optional[TextIO], level: int, logger: Optional[logging.Logger], formatter: Formatter) -> None:
        self._stream = stream
        self._level = level
        self._logger = logger
        self._formatter = formatter
        # guards writing, the once-only guidance and the count of problems
        # shown, so a handler shared by several configurations or threads
        # never splits a line from the text beneath it
        self._lock = threading.Lock()
        self._guided = False
        # how many problems each configuration's running operation has shown,
        # by the configuration's identity, so operations of configurations
        # sharing the handler never hide or repeat each other's reports
        self._shown_problems: dict[int, int] = {}

    def __call__(self, event: Event) -> None:
        try:
            self._handle(event)
        except Exception:  # noqa: BLE001 - a receiver must never affect the operation
            pass

    def _handle(self, event: Event) -> None:
        if _starts_operation(event):
            # each operation counts the problems it has shown afresh, even
            # when its start line is below the level
            with self._lock:
                self._shown_problems.pop(id(event._config), None)
        level = _logbridge.event_level(event)
        if level < self._level:
            return
        if self._logger is not None and not self._logger.isEnabledFor(level):
            # the logger would drop the line, so nothing beneath it is
            # rendered or written either
            return
        line = _prettyline.format_line(event, level, _logbridge.event_message(event), self._style)

        # everything is rendered before the lock is taken, which guards
        # writing only, so one slow render never holds up another thread
        block = ""
        warning: Optional[str] = None
        guidance = False
        if self._level <= logging.INFO and event.operation == "create" and event.phase == "success":
            block, warning, guidance = self._configuration(event)
        report = self._report(event)

        with self._lock:
            if report is not None and self._report_wanted(event, report[1]):
                block += report[0]
            if guidance:
                guidance, self._guided = not self._guided, True
            self._write(event, level, line + block)
            if warning is not None:
                attrs = [("resource", event.resource_id), ("error", warning)]
                self._write(event, logging.WARNING, _prettyline.format_record(event.time, logging.WARNING, _UNABLE, attrs, self._style))
            if guidance:
                attrs = [("hint", _GUIDANCE_HINT)]
                self._write(event, logging.INFO, _prettyline.format_record(event.time, logging.INFO, _GUIDANCE, attrs, self._style))

    def _configuration(self, event: Event) -> tuple[str, Optional[str], bool]:
        """What goes with a creation: the created resource's configuration, a warning's error, and whether guidance is due."""
        config = event._config
        if not event.data:
            # no data is expected when the configuration was created without
            # it, so say once how to turn it on; an event built by hand
            # without data shows nothing, as in Go
            return "", None, config is not None and getattr(config, "_event_data", None) is EventDataLevel.NONE
        if config is None:
            return "", "the event was not delivered by a configuration", False
        try:
            tokens = config._saved_entity_tokens_now(event.data, include_computed=True)
        except _errors.NotEncodableError:
            # a variable, output or module is never written as
            # configuration, so there is nothing to show and nothing to report
            return "", None, False
        except Exception as exc:  # noqa: BLE001 - one warning and carry on, as Go's example does
            return "", str(exc) or type(exc).__name__, False
        return _indent(self._render(tokens)), None, False

    def _report(self, event: Event) -> Optional[tuple[str, int]]:
        """The report beneath a configuration mistake's error line, and how many problems it shows, or ``None``."""
        err = event.error
        if event.phase != "error" or not isinstance(err, _errors.Error) or not err.tokens:
            return None
        problems = len(err.problems) if isinstance(err, _errors.ConfigError) and err.problems else 1
        return _indent(format_error(err, formatter=self._formatter, theme=DEFAULT_THEME, width=80)), problems

    def _report_wanted(self, event: Event, problems: int) -> bool:
        """Whether a report is written: each problem is reported once, beneath the first line about it.

        A block's own error (a parse error, or a resource's) is always
        reported, and its problems counted. The operation's closing error
        holds every problem again, so its report is written only when it
        holds problems no earlier line showed. Called under the lock.
        """
        if event.operation == "parse" or event.resource_id:
            key = id(event._config)
            self._shown_problems[key] = self._shown_problems.get(key, 0) + problems
            return True
        wanted = problems > self._shown_problems.pop(id(event._config), 0)
        return wanted

    def _style(self, text: str, style: str) -> str:
        """``text`` in ``style``, written by the formatter as one piece of plain text styled by a one-entry theme."""
        if not style or not text:
            return text
        out = io.StringIO()
        self._formatter.format(out, {Kind.TEXT: style}, [Token(kind=Kind.TEXT, text=text)])
        return out.getvalue()

    def _render(self, tokens: Sequence[Token]) -> str:
        """Labelled text as the formatter writes it with the default theme."""
        out = io.StringIO()
        self._formatter.format(out, DEFAULT_THEME, tokens)
        return out.getvalue()

    def _write(self, event: Event, level: int, text: str) -> None:
        """Write one group, a line and what is beneath it, to the stream or as one record to the logger. Called under the lock."""
        if self._logger is not None:
            if self._logger.isEnabledFor(level):
                self._logger.handle(_logbridge.event_record(self._logger, event, level, text.rstrip("\n")))
            return
        assert self._stream is not None
        try:
            self._stream.write(text)
            flush = getattr(self._stream, "flush", None)
            if flush is not None:
                flush()
        except (OSError, ValueError):
            # a failed write must not affect the operation, as Go's bridge
            # discards it
            pass


def _starts_operation(event: Event) -> bool:
    """Whether the event starts an operation, which begins a fresh count of the problems shown."""
    return event.phase == "start" and not event.resource_id and event.operation != "parse"


def _indent(text: str) -> str:
    """Every non-empty line of ``text`` moved right two spaces, ending in one line break, as Go's example indents."""
    lines = text.rstrip("\n").split("\n")
    return "\n".join("  " + line if line else line for line in lines) + "\n"


__all__ = ["LEVEL_ENV", "handler", "level_from_env"]
