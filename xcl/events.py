"""Events: what the engine reports as an operation runs."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from xcl import _errors
from xcl._core import core_pb2
from xcl._schema import hydrate


@dataclasses.dataclass
class Event:
    """One event of an operation, delivered to the configuration's ``on_event`` handler.

    ``operation`` and ``phase`` say what happened (``apply``/``start``,
    ``create``/``success``, ...), ``resource_id`` which entity it concerns,
    ``source`` whether the core or a plugin reported it, ``error`` the error
    of a failed step, ``data`` the entity as JSON when event data is on,
    masked by the event mask, and ``meta`` the details of a log message.
    """

    time: datetime
    source: str
    operation: str
    phase: str
    resource_type: str = ""
    resource_id: str = ""
    file: str = ""
    duration: timedelta = timedelta(0)
    error: Optional[_errors.Error] = None
    data: bytes = b""
    meta: dict[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def _from_proto(cls, e: core_pb2.Event) -> Event:
        meta: dict[str, Any] = {}
        if e.meta_json:
            try:
                meta = json.loads(e.meta_json)
            except ValueError:
                meta = {"raw": e.meta_json.decode(errors="replace")}
        return cls(
            time=datetime.fromtimestamp(e.time_unix_nano / 1e9, tz=timezone.utc) if e.time_unix_nano else datetime.fromtimestamp(0, tz=timezone.utc),
            source=e.source,
            operation=e.operation,
            phase=e.phase,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            file=e.file,
            duration=timedelta(microseconds=e.duration_nano / 1000),
            error=_errors.from_proto(e.error) if e.HasField("error") else None,
            data=bytes(e.data),
            meta=meta,
        )

    def entity(self) -> Any:
        """The entity the event's data holds, hydrated, or ``None`` when the event carries no data."""
        if not self.data:
            return None
        return hydrate(json.loads(self.data))

    @property
    def level(self) -> str:
        """A log message's level, from ``meta``, or an empty string."""
        return str(self.meta.get("level", ""))

    @property
    def message(self) -> str:
        """A log message's text, from ``meta``, or an empty string."""
        return str(self.meta.get("message", ""))


__all__ = ["Event"]
