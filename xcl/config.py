"""The synchronous configuration API."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Optional

from xcl import _errors
from xcl._client import Client, default_client
from xcl._core import core_pb2
from xcl._entity import registration_of
from xcl._poll import Handlers, Operation, StateStore, drive
from xcl._schema import hydrate
from xcl.diff import Diff
from xcl.events import Event
from xcl.mask import Mask

EVENT_DATA_LEVELS = {
    "none": core_pb2.EVENT_DATA_NONE,
    "raw": core_pb2.EVENT_DATA_RAW,
    "processed": core_pb2.EVENT_DATA_PROCESSED,
}


class Config:
    """A configuration: the Python form of ``xcl.NewConfig``.

    ``registries`` are the :class:`xcl.LocalRegistry` and
    :class:`xcl.GitHubRegistry` objects whose types, functions and plugins the
    configuration may use. State is kept in the directory ``state_path``, or
    in ``state_store``, an object with ``load``, ``save``, ``exists`` and
    ``clear``; ``state_mask`` masks sensitive values in it. ``variables`` are
    passed in by name. ``on_event`` receives every :class:`xcl.Event`;
    ``event_data`` is ``"none"``, ``"raw"`` or ``"processed"``,
    ``event_buffer_size`` bounds the events waiting for the handler, and
    ``event_mask`` masks sensitive values in event data (redacted unless
    ``no_event_mask``).

    Creating a configuration loads the engine on first use. Every operation
    runs to completion before returning and keeps other Python threads
    running meanwhile. ``close`` releases the configuration, and a ``Config``
    is a context manager that closes on exit.
    """

    def __init__(
        self,
        *,
        registries: Iterable[Any] = (),
        state_path: Optional[str | os.PathLike[str]] = None,
        state_store: Optional[StateStore] = None,
        state_mask: Optional[Mask] = None,
        variables: Optional[Mapping[str, Any]] = None,
        on_event: Optional[Callable[[Event], Any]] = None,
        event_data: str = "none",
        event_buffer_size: int = 0,
        event_mask: Optional[Mask] = None,
        no_event_mask: bool = False,
        client: Optional[Client] = None,
    ) -> None:
        self._client = client or default_client()
        self._registries = list(registries)
        self._state_store = state_store
        self._on_event = on_event
        self._functions: dict[str, Callable[..., Any]] = {}
        for r in self._registries:
            self._functions.update(getattr(r, "functions", {}) or {})
        self._handlers = Handlers(functions=self._functions, store=state_store, on_event=on_event)
        self._handle: Optional[int] = None

        if state_path is not None and state_store is not None:
            raise ValueError("give state_path or state_store, not both")
        if event_data not in EVENT_DATA_LEVELS:
            raise ValueError(f'event_data must be "none", "raw" or "processed", not {event_data!r}')

        request = self._request(
            state_path=state_path,
            state_mask=state_mask,
            variables=variables,
            event_data=event_data,
            event_buffer_size=event_buffer_size,
            event_mask=event_mask,
            no_event_mask=no_event_mask,
        )
        self._handle = self._client.call(0, "CreateConfig", request).handle

    def _request(
        self,
        *,
        state_path: Optional[str | os.PathLike[str]] = None,
        state_mask: Optional[Mask] = None,
        variables: Optional[Mapping[str, Any]] = None,
        event_data: str = "none",
        event_buffer_size: int = 0,
        event_mask: Optional[Mask] = None,
        no_event_mask: bool = False,
    ) -> core_pb2.CreateConfigRequest:
        request = core_pb2.CreateConfigRequest(
            registries=[r._to_proto() for r in self._registries],
            events=self._on_event is not None,
            event_buffer_size=int(event_buffer_size),
            event_data=EVENT_DATA_LEVELS[event_data],
            no_event_mask=bool(no_event_mask),
        )
        if state_path is not None:
            request.state_store.path = os.fspath(state_path)
        elif self._state_store is not None:
            request.state_store.host = True
        if state_mask is not None:
            request.state_mask.CopyFrom(state_mask._to_proto())
        if event_mask is not None:
            request.event_mask.CopyFrom(event_mask._to_proto())
        if variables:
            request.variables_json = json.dumps(dict(variables)).encode()
        return request

    # -- lifecycle ---------------------------------------------------------

    @property
    def handle(self) -> int:
        """The configuration's handle in the engine; 0 once closed."""
        return self._handle or 0

    def close(self) -> None:
        """Release the configuration in the engine. Closing twice is harmless."""
        if self._handle is not None:
            handle, self._handle = self._handle, None
            self._client.release(handle)

    def __enter__(self) -> Config:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _open(self) -> int:
        if self._handle is None:
            raise RuntimeError("the configuration is closed")
        return self._handle

    # -- operations --------------------------------------------------------

    def _run(self, method: str, request: Any) -> Optional[Diff]:
        handle = self._open()
        started = self._client.call(handle, method, request)
        op = Operation(self._client, handle, started.operation_id)
        return drive(op, self._handlers)

    def validate(self, *paths: str | os.PathLike[str]) -> None:
        """Check the configuration at ``paths`` is valid, calling no provider; raises :class:`xcl.ConfigError`."""
        self._run("StartValidate", core_pb2.StartValidateRequest(paths=_paths(paths)))

    def apply(self, *paths: str | os.PathLike[str]) -> None:
        """Apply the configuration at ``paths``: create, update and destroy entities, then save state."""
        self._run("StartApply", core_pb2.StartApplyRequest(paths=_paths(paths)))

    def diff(self, *paths: str | os.PathLike[str], reveal_sensitive: bool = False) -> Diff:
        """What applying the configuration at ``paths`` would do, without doing it."""
        result = self._run("StartDiff", core_pb2.StartDiffRequest(paths=_paths(paths), reveal_sensitive=reveal_sensitive))
        assert result is not None
        return result

    def destroy(self) -> None:
        """Destroy every entity in the saved state, children first, saving after each."""
        self._run("StartDestroy", core_pb2.StartDestroyRequest())

    def load(self) -> None:
        """Read the saved state into the configuration, so lookups answer from it."""
        self._run("StartLoad", core_pb2.StartLoadRequest())

    # -- lookups -----------------------------------------------------------

    def entities(self) -> list[Any]:
        """Every entity the configuration holds, as registered classes or :class:`xcl.Entity`."""
        response = self._client.call(self._open(), "Entities", core_pb2.EntitiesRequest())
        return [hydrate(json.loads(e)) for e in response.entities]

    def entity_count(self) -> int:
        """How many entities the configuration holds."""
        return len(self._client.call(self._open(), "Entities", core_pb2.EntitiesRequest()).entities)

    def find(self, cls: Optional[type], address: str) -> Any:
        """The entity at ``address``, as ``cls``, or as its registered class or :class:`xcl.Entity` when ``cls`` is ``None``."""
        response = self._client.call(self._open(), "Find", core_pb2.FindRequest(address=address))
        return self._hydrate(response.entity, cls)

    def find_by_type(self, cls: Optional[type], *path: str) -> list[Any]:
        """Every entity of the type the segments name, as :meth:`find` returns them."""
        response = self._client.call(self._open(), "FindByType", core_pb2.FindByTypeRequest(path=list(path)))
        return [self._hydrate(e, cls) for e in response.entities]

    def find_one(self, cls: Optional[type], *path: str) -> Any:
        """The single entity of the type the segments name; raises :class:`xcl.NotFoundError` or :class:`xcl.NotUniqueError`."""
        response = self._client.call(self._open(), "FindOne", core_pb2.FindByTypeRequest(path=list(path)))
        return self._hydrate(response.entity, cls)

    def all(self, cls: type) -> list[Any]:
        """Every entity of the registered class ``cls``."""
        type_name, subtype = registration_of(cls)
        path = [type_name, subtype] if subtype else [type_name]
        return self.find_by_type(cls, *path)

    def outputs(self) -> dict[str, Any]:
        """The configuration's outputs, by address, as Python values."""
        response = self._client.call(self._open(), "Outputs", core_pb2.OutputsRequest())
        return json.loads(response.outputs_json) if response.outputs_json else {}

    def encode_saved_entity(self, data: bytes, *, highlight: bool = False) -> str:
        """A saved record rendered as configuration text, coloured for a terminal when ``highlight``."""
        response = self._client.call(self._open(), "EncodeSavedEntity", core_pb2.EncodeSavedEntityRequest(entity=bytes(data), highlight=highlight))
        return response.text.decode()

    def _hydrate(self, data: bytes, cls: Optional[type]) -> Any:
        decoded = json.loads(data)
        if cls is not None:
            meta = decoded.get("meta") or {}
            want = registration_of(cls)
            got = (meta.get("type", ""), meta.get("subtype", "") or "")
            if got != want:
                raise _errors.TypeMismatchError(
                    f"the entity at {meta.get('id', '?')} is a {'.'.join(filter(None, got))}, not a {'.'.join(filter(None, want))}",
                    details={"address": meta.get("id", ""), "want": ".".join(filter(None, want)), "got": ".".join(filter(None, got))},
                )
        return hydrate(decoded, cls)


def _paths(paths: Iterable[str | os.PathLike[str]]) -> list[str]:
    listed = [os.fspath(p) for p in paths]
    if not listed:
        raise _errors.InvalidArgumentError("at least one path is required", details={"argument": "paths"})
    return listed


__all__ = ["Config", "StateStore"]
