"""The synchronous configuration API."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Optional, TextIO

from xcl import _errors
from xcl._client import Client, default_client
from xcl._core import core_pb2
from xcl._classes import ClassMap
from xcl._poll import Handlers, Operation, StateStore, drive
from xcl._schema import hydrate, record_bytes
from xcl.diff import Diff
from xcl.events import Event, EventDataLevel
from xcl.highlight._formatters import PLAIN, Formatter
from xcl.highlight._kinds import Token, _tokens_from_proto
from xcl.highlight._theme import DEFAULT_THEME, Theme
from xcl.mask import Mask

_EVENT_DATA_WIRE: dict[EventDataLevel, core_pb2.EventDataLevel] = {
    EventDataLevel.NONE: core_pb2.EVENT_DATA_NONE,
    EventDataLevel.RAW: core_pb2.EVENT_DATA_RAW,
    EventDataLevel.PROCESSED: core_pb2.EVENT_DATA_PROCESSED,
}


def _event_data_level(value: object) -> core_pb2.EventDataLevel:
    """Check the ``event_data`` option and return the protocol level it carries.

    Only an :class:`xcl.EventDataLevel` member is accepted. The check is on
    type, not equality: a member compares and hashes equal to its string, so
    a lookup alone would let a bare word through.
    """
    if not isinstance(value, EventDataLevel):
        raise TypeError(
            f"event_data must be an xcl.EventDataLevel, such as xcl.EventDataLevel.PROCESSED, "
            f"not {value!r} ({type(value).__name__})"
        )
    return _EVENT_DATA_WIRE[value]


class Config:
    """A configuration: the Python form of ``xcl.NewConfig``.

    ``registries`` are the :class:`xcl.LocalRegistry` and
    :class:`xcl.GitHubRegistry` objects whose types, functions and plugins the
    configuration may use. State is kept in the directory ``state_path``, or
    in ``state_store``, an object with ``load``, ``save``, ``exists`` and
    ``clear``; ``state_mask`` masks sensitive values in it. ``variables`` are
    passed in by name. ``on_event`` receives every :class:`xcl.Event`;
    ``event_data`` is an :class:`xcl.EventDataLevel`,
    ``EventDataLevel.NONE`` (the default), ``RAW`` or ``PROCESSED``,
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
        event_data: EventDataLevel = EventDataLevel.NONE,
        event_buffer_size: int = 0,
        event_mask: Optional[Mask] = None,
        no_event_mask: bool = False,
        client: Optional[Client] = None,
    ) -> None:
        level = _event_data_level(event_data)
        # the level the configuration was created with, which tells a
        # handler whether an event without data is expected to have none
        self._event_data = event_data
        self._client = client or default_client()
        self._registries = list(registries)
        self._classes = ClassMap.from_registries(self._registries)
        self._state_store = state_store
        self._on_event = on_event
        self._functions: dict[str, Callable[..., Any]] = {}
        for r in self._registries:
            self._functions.update(getattr(r, "functions", {}) or {})
        self._handlers = Handlers(
            functions=self._functions, store=state_store, on_event=on_event, classes=self._classes, config=self
        )
        self._handle: Optional[int] = None

        if state_path is not None and state_store is not None:
            raise ValueError("give state_path or state_store, not both")

        request = self._request(
            state_path=state_path,
            state_mask=state_mask,
            variables=variables,
            event_data=level,
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
        event_data: core_pb2.EventDataLevel = core_pb2.EVENT_DATA_NONE,
        event_buffer_size: int = 0,
        event_mask: Optional[Mask] = None,
        no_event_mask: bool = False,
    ) -> core_pb2.CreateConfigRequest:
        request = core_pb2.CreateConfigRequest(
            registries=[r._to_proto() for r in self._registries],
            events=self._on_event is not None,
            event_buffer_size=int(event_buffer_size),
            event_data=event_data,
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
        """Every entity the configuration holds, as the classes registered on it or :class:`xcl.Entity`."""
        response = self._client.call(self._open(), "Entities", core_pb2.EntitiesRequest())
        return [hydrate(json.loads(e), registry=self._classes) for e in response.entities]

    def entity_count(self) -> int:
        """How many entities the configuration holds."""
        return len(self._client.call(self._open(), "Entities", core_pb2.EntitiesRequest()).entities)

    def find(self, cls: Optional[type], address: str) -> Any:
        """The entity at ``address``, as ``cls``, or as the class registered on this configuration or :class:`xcl.Entity` when ``cls`` is ``None``.

        A ``cls`` this configuration did not register raises :class:`xcl.NotRegisteredError`.
        """
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
        """Every entity of ``cls``, a class registered on this configuration."""
        type_name, subtype = self._classes.names_of(cls)
        path = [type_name, subtype] if subtype else [type_name]
        return self.find_by_type(cls, *path)

    def outputs(self) -> dict[str, Any]:
        """The configuration's outputs, by address, as Python values."""
        response = self._client.call(self._open(), "Outputs", core_pb2.OutputsRequest())
        return json.loads(response.outputs_json) if response.outputs_json else {}

    def encode_entity(
        self,
        entity: object,
        *,
        include_computed: bool = False,
        include_empty: bool = False,
        reveal_sensitive: bool = False,
        show_references: bool = False,
    ) -> str:
        """An entity rendered as configuration text, the same text Go's ``xcl.EncodeEntity`` writes.

        ``entity`` is an instance of a class registered on this
        configuration, whether returned by a lookup, carried by an event or
        built by hand, or the :class:`xcl.Entity` a lookup returns for a type
        with no class. Changes made to a looked-up entity show in the text.
        The text is one block, ``<type> "<subtype>" "<name>"`` or
        ``<type> "<name>"``. Every choice is off by default:

        - ``include_computed`` also writes the fields a provider filled in.
        - ``include_empty`` also writes attributes that are unset or at their
          zero value.
        - ``reveal_sensitive`` writes each sensitive value as its real value
          rather than ``(sensitive)``. A looked-up entity holds only the
          marker, so the engine shows its own configured value, found by the
          entity's ``meta.id``; a value the entity holds for real, such as an
          edit or one set by hand, is shown as it is.
        - ``show_references`` writes each field that referred to another
          entity as the configuration wrote it, rather than its value.

        Raises :class:`xcl.NotEncodableError` for a value that is not an
        entity, a variable, output or module, or a value with no
        configuration form, :class:`xcl.NotRegisteredError` for an instance
        of a class this configuration did not register, and
        :class:`xcl.OperationInProgressError` while an operation runs,
        including from an ``on_event`` handler, because it reads the
        engine's own copy of the entity. To render from an event handler,
        use ``encode_saved_entity(event.data)``, which is allowed then.
        """
        request = _encode_entity_request(
            record_bytes(entity, self._classes),
            _encode_options(include_computed, include_empty, reveal_sensitive, show_references),
            tokens=False,
        )
        response = self._client.call(self._open(), "EncodeEntity", request)
        return response.text.decode()

    def entity_tokens(
        self,
        entity: object,
        *,
        include_computed: bool = False,
        include_empty: bool = False,
        reveal_sensitive: bool = False,
        show_references: bool = False,
    ) -> list[Token]:
        """The labelled text of an entity's configuration text, as Go's ``xcl.EntityTokens`` returns it.

        The tokens, joined in order, are the text :meth:`encode_entity`
        returns with the same choices, each piece labelled with its
        :class:`xcl.highlight.Kind`, such as an attribute name or a string,
        for a format of your own. It raises what :meth:`encode_entity`
        raises, including :class:`xcl.OperationInProgressError` while an
        operation runs.
        """
        request = _encode_entity_request(
            record_bytes(entity, self._classes),
            _encode_options(include_computed, include_empty, reveal_sensitive, show_references),
            tokens=True,
        )
        response = self._client.call(self._open(), "EncodeEntity", request)
        return _tokens_from_proto(response.tokens)

    def print_entity(
        self,
        entity: object,
        file: TextIO | None = None,
        *,
        include_computed: bool = False,
        include_empty: bool = False,
        reveal_sensitive: bool = False,
        show_references: bool = False,
        formatter: Formatter = PLAIN,
        theme: Theme = DEFAULT_THEME,
    ) -> None:
        """Print an entity to ``file`` as configuration text, in one call, as Go's ``xcl.PrintEntity`` does.

        ``file`` is ``sys.stdout`` when not given. The text is the one
        :meth:`encode_entity` returns with the same choices, written in the
        format ``formatter`` chooses (plain text by default) and styled by
        ``theme``; the formatter is given the whole labelled text at once::

            cfg.print_entity(db, include_computed=True, formatter=xcl.highlight.for_stream(sys.stdout))

        It raises what :meth:`encode_entity` raises, writing nothing; to
        print from an event handler while an operation runs, use
        :meth:`print_saved_entity`.
        """
        tokens = self.entity_tokens(
            entity,
            include_computed=include_computed,
            include_empty=include_empty,
            reveal_sensitive=reveal_sensitive,
            show_references=show_references,
        )
        formatter.format(sys.stdout if file is None else file, theme, tokens)

    def encode_saved_entity(
        self,
        data: bytes,
        *,
        include_computed: bool = False,
        include_empty: bool = False,
        reveal_sensitive: bool = False,
        show_references: bool = False,
    ) -> str:
        """A saved record, as state stores it and events carry it, rendered as configuration text.

        The text is the same :meth:`encode_entity` writes for the same
        entity, with the same choices, all off by default:
        ``include_computed`` also writes the fields a provider filled in,
        ``include_empty`` the attributes that are unset or at their zero
        value, ``reveal_sensitive`` each sensitive value the record holds
        for real rather than ``(sensitive)``, and ``show_references`` each
        field that referred to another entity as the configuration wrote
        it.

        It can be called at any time, including from an ``on_event`` handler
        while an operation runs, because it reads none of the
        configuration's entities. A program created with
        ``event_data=xcl.EventDataLevel.PROCESSED`` can therefore print each
        created resource as its create success event arrives, and the text
        is the same as the same render after the operation.

        Raises :class:`xcl.InvalidSavedDataError` for data that is not one
        saved record, :class:`xcl.UnregisteredTypeError` for a record of a
        type this configuration does not know, :class:`xcl.NotEncodableError`
        for a variable, output or module, and :class:`xcl.PluginLoadError`
        when a plugin the record needs fails to load.
        """
        request = _encode_saved_entity_request(
            data,
            _encode_options(include_computed, include_empty, reveal_sensitive, show_references),
            tokens=False,
        )
        response = self._client.call(self._open(), "EncodeSavedEntity", request)
        return response.text.decode()

    def saved_entity_tokens(
        self,
        data: bytes,
        *,
        include_computed: bool = False,
        include_empty: bool = False,
        reveal_sensitive: bool = False,
        show_references: bool = False,
    ) -> list[Token]:
        """The labelled text of a saved record's configuration text.

        The tokens, joined in order, are the text
        :meth:`encode_saved_entity` returns with the same choices, each piece
        labelled with its :class:`xcl.highlight.Kind`. Like
        :meth:`encode_saved_entity`, it can be called from an ``on_event``
        handler while an operation runs, and raises what it raises.
        """
        return self._saved_entity_tokens_now(
            data,
            include_computed=include_computed,
            include_empty=include_empty,
            reveal_sensitive=reveal_sensitive,
            show_references=show_references,
        )

    def _saved_entity_tokens_now(
        self,
        data: bytes,
        *,
        include_computed: bool = False,
        include_empty: bool = False,
        reveal_sensitive: bool = False,
        show_references: bool = False,
    ) -> list[Token]:
        """The labelled text of a saved record, asked of the engine with a blocking call on the calling thread.

        Private: it is the render :mod:`xcl.prettylog` makes from an
        ``on_event`` handler while an operation runs, which the engine
        allows for a saved record. Both configuration flavours have it, so
        a handler can use it whichever delivered the event.
        """
        return _saved_entity_tokens(
            self._client,
            self._open(),
            data,
            _encode_options(include_computed, include_empty, reveal_sensitive, show_references),
        )

    def print_saved_entity(
        self,
        data: bytes,
        file: TextIO | None = None,
        *,
        include_computed: bool = False,
        include_empty: bool = False,
        reveal_sensitive: bool = False,
        show_references: bool = False,
        formatter: Formatter = PLAIN,
        theme: Theme = DEFAULT_THEME,
    ) -> None:
        """Print a saved record to ``file`` as configuration text, in one call.

        ``file`` is ``sys.stdout`` when not given. The text is the one
        :meth:`encode_saved_entity` returns with the same choices, in the
        format ``formatter`` chooses (plain text by default), styled by
        ``theme``. It can be called from an ``on_event`` handler while an
        operation runs, so a program can print each created resource as its
        create success event arrives::

            def on_event(event: xcl.Event) -> None:
                if event.operation == "create" and event.phase == "success" and event.data:
                    cfg.print_saved_entity(event.data, include_computed=True)

        It raises what :meth:`encode_saved_entity` raises, writing nothing.
        """
        tokens = self.saved_entity_tokens(
            data,
            include_computed=include_computed,
            include_empty=include_empty,
            reveal_sensitive=reveal_sensitive,
            show_references=show_references,
        )
        formatter.format(sys.stdout if file is None else file, theme, tokens)

    def _hydrate(self, data: bytes, cls: Optional[type]) -> Any:
        decoded = json.loads(data)
        if cls is not None:
            meta = decoded.get("meta") or {}
            want = self._classes.names_of(cls)
            got = (meta.get("type", ""), meta.get("subtype", "") or "")
            if got != want:
                raise _errors.TypeMismatchError(
                    f"the entity at {meta.get('id', '?')} is a {'.'.join(filter(None, got))}, not a {'.'.join(filter(None, want))}",
                    details={"address": meta.get("id", ""), "want": ".".join(filter(None, want)), "got": ".".join(filter(None, got))},
                )
        return hydrate(decoded, cls, registry=self._classes)


def _encode_options(include_computed: bool, include_empty: bool, reveal_sensitive: bool, show_references: bool) -> core_pb2.EncodeOptions:
    """The encoding choices as the engine reads them, the four options of Go's encoder."""
    return core_pb2.EncodeOptions(
        include_computed=include_computed,
        include_empty=include_empty,
        reveal_sensitive=reveal_sensitive,
        show_references=show_references,
    )


def _encode_entity_request(record: bytes, options: core_pb2.EncodeOptions, *, tokens: bool) -> core_pb2.EncodeEntityRequest:
    """The request rendering an entity's record, asking for its labelled text too when ``tokens`` is true."""
    return core_pb2.EncodeEntityRequest(entity=record, options=options, tokens=tokens)


def _encode_saved_entity_request(data: bytes, options: core_pb2.EncodeOptions, *, tokens: bool) -> core_pb2.EncodeSavedEntityRequest:
    """The request rendering a saved record, asking for its labelled text too when ``tokens`` is true."""
    return core_pb2.EncodeSavedEntityRequest(entity=bytes(data), options=options, tokens=tokens)


def _saved_entity_tokens(client: Client, handle: int, data: bytes, options: core_pb2.EncodeOptions) -> list[Token]:
    """The labelled text of a saved record, from a blocking ``EncodeSavedEntity`` call straight through ``client``."""
    request = _encode_saved_entity_request(data, options, tokens=True)
    response = client.call(handle, "EncodeSavedEntity", request)
    return _tokens_from_proto(response.tokens)


def _paths(paths: Iterable[str | os.PathLike[str]]) -> list[str]:
    listed = [os.fspath(p) for p in paths]
    if not listed:
        raise _errors.InvalidArgumentError("at least one path is required", details={"argument": "paths"})
    return listed


__all__ = ["Config", "StateStore"]
