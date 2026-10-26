"""xcl's events to Python's standard logging, at the levels and with the messages Go's ``events.SlogHandler`` uses."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from xcl.events import Event

# the attributes every LogRecord has, which logging refuses to let extra
# overwrite, so an event detail named after one is reachable only through
# the event itself
_RESERVED = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

# Go's log levels, as a log event's "level" detail names them
_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}


def logging_handler(logger: logging.Logger | None = None) -> Callable[[Event], None]:
    """An ``on_event`` handler writing each event to ``logger`` as Go's ``events.SlogHandler`` writes it to slog.

    ``logger`` is ``logging.getLogger("xcl")`` when not given. One line sends
    every event of a configuration to the logging setup a program already
    has::

        cfg = xcl.Config(on_event=xcl.logging_handler(logging.getLogger("app")))

    A log event (phase ``log``) is written at its own level (debug, info,
    warn or error) with its own message. Every other event is written as
    ``"<operation> <phase>"``, such as ``"create success"``: at error level
    for phase ``error``, warning for ``blocked``, and info otherwise. The
    logger's level is checked first, so a filtered event costs one call.

    Each record carries the event's time, and as attributes, under Go's
    names: ``source``, ``operation``, ``phase``, ``resource`` (the entity's
    address), ``type`` and ``file`` when set, ``duration`` (a ``timedelta``)
    when not zero, ``error`` (the :class:`xcl.Error`) when the event has
    one, then each of the event's details by name, and ``xcl_event``, the
    :class:`xcl.Event` itself. A detail named after an attribute every
    ``LogRecord`` has, such as ``name``, is reachable only through
    ``record.xcl_event.meta``. JSON and key-value formatters, structlog's
    ``ProcessorFormatter`` and loguru's standard logging integration see the
    attributes as fields, with no adapter.
    """
    target = logging.getLogger("xcl") if logger is None else logger

    def handle(event: Event) -> None:
        level = _level(event)
        if not target.isEnabledFor(level):
            return
        record = target.makeRecord(target.name, level, "(xcl)", 0, _message(event), (), None, extra=_extra(event))
        _set_time(record, event)
        target.handle(record)

    return handle


def _level(event: Event) -> int:
    """The logging level Go's bridge gives the event."""
    if event.phase == "log":
        written = event.meta.get("level")
        return _LOG_LEVELS.get(written, logging.INFO) if isinstance(written, str) else logging.INFO
    if event.phase == "error":
        return logging.ERROR
    if event.phase == "blocked":
        return logging.WARNING
    return logging.INFO


def _message(event: Event) -> str:
    """The message Go's bridge gives the event: a log event's own, else ``"<operation> <phase>"``."""
    if event.phase == "log":
        message = event.meta.get("message")
        return message if isinstance(message, str) else ""
    return f"{event.operation} {event.phase}"


def _extra(event: Event) -> dict[str, Any]:
    """The event's fields as record attributes, in Go's order and under Go's names."""
    extra: dict[str, Any] = {}
    for key, value in (
        ("source", event.source),
        ("operation", event.operation),
        ("phase", event.phase),
        ("resource", event.resource_id),
        ("type", event.resource_type),
        ("file", event.file),
    ):
        if value:
            extra[key] = value
    if event.duration != timedelta(0):
        extra["duration"] = event.duration
    if event.error is not None:
        extra["error"] = event.error
    for key in sorted(event.meta):
        if event.phase == "log" and key in ("level", "message"):
            continue
        if key in _RESERVED or key in extra or key == "xcl_event":
            continue
        extra[key] = event.meta[key]
    extra["xcl_event"] = event
    return extra


def _set_time(record: logging.LogRecord, event: Event) -> None:
    """Give the record the event's time rather than the time it was made, as Go's bridge does."""
    created = event.time.timestamp()
    record.relativeCreated += (created - record.created) * 1000
    record.created = created
    record.msecs = int((created - int(created)) * 1000) + 0.0
