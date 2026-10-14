"""The asyncio configuration API: ``xcl.aio.Config``.

Every operation and lookup of :class:`xcl.Config` is offered as an awaitable
that never blocks the event loop. The engine is polled from a dedicated
executor thread, and each task the engine posts is dispatched as an asyncio
task: a registered ``async def`` function, event handler or state-store
method is awaited on the loop, and a plain one runs in the default executor.
Cancelling the awaiting task cancels the engine's work, waits for it to stop
and save its progress, then lets the cancellation through.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import json
import os
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Optional

from xcl import _errors
from xcl._client import Client, default_client
from xcl._core import core_pb2
from xcl._classes import ClassMap
from xcl._functions import decode_args, encode_result, failed_result
from xcl._poll import POLL_WAIT_MS, Operation, StateStore, answer_state
from xcl.config import EVENT_DATA_LEVELS
from xcl.config import Config as _SyncConfig
from xcl.diff import Diff
from xcl.events import Event
from xcl.mask import Mask


class Config:
    """A configuration whose operations and lookups are awaitables.

    It takes the options of :class:`xcl.Config`; ``on_event``, the
    ``state_store`` methods and registered functions may be ``async def``.
    Use it as ``async with``, or ``await close()`` when done.
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
        self._classes = ClassMap.from_registries(self._registries)
        self._state_store = state_store
        self._on_event = on_event
        self._functions: dict[str, Callable[..., Any]] = {}
        for r in self._registries:
            self._functions.update(getattr(r, "functions", {}) or {})
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="xcl-poll")
        self._handle: Optional[int] = None
        self._lock = asyncio.Lock()

        if state_path is not None and state_store is not None:
            raise ValueError("give state_path or state_store, not both")
        if event_data not in EVENT_DATA_LEVELS:
            raise ValueError(f'event_data must be "none", "raw" or "processed", not {event_data!r}')

        self._request = _SyncConfig._request(
            self,  # type: ignore[arg-type]
            state_path=state_path,
            state_mask=state_mask,
            variables=variables,
            event_data=event_data,
            event_buffer_size=event_buffer_size,
            event_mask=event_mask,
            no_event_mask=no_event_mask,
        )

    # -- lifecycle ---------------------------------------------------------

    async def _ensure_open(self) -> int:
        if self._handle is None:
            self._handle = (await self._in_executor(self._client.call, 0, "CreateConfig", self._request)).handle
        return self._handle

    @property
    def handle(self) -> int:
        """The configuration's handle in the engine; 0 before the first operation or once closed."""
        return self._handle or 0

    async def open(self) -> Config:
        """Create the configuration in the engine now rather than on the first operation."""
        await self._ensure_open()
        return self

    async def close(self) -> None:
        """Release the configuration in the engine. Closing twice is harmless."""
        if self._handle is not None:
            handle, self._handle = self._handle, None
            await self._in_executor(self._client.release, handle)
        self._executor.shutdown(wait=False)

    async def __aenter__(self) -> Config:
        await self._ensure_open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _in_executor(self, fn: Callable[..., Any], *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn, *args)

    # -- operations --------------------------------------------------------

    async def _run(self, method: str, request: Any) -> Optional[Diff]:
        handle = await self._ensure_open()
        async with self._lock:
            started = await self._in_executor(self._client.call, handle, method, request)
            op = Operation(self._client, handle, started.operation_id)
            return await self._drive(op)

    async def _drive(self, op: Operation) -> Optional[Diff]:
        pending: set[asyncio.Task[Any]] = set()
        try:
            while not op.done:
                response = await self._in_executor(op.step, POLL_WAIT_MS)
                if response is None:
                    continue
                task = self._dispatch(op, response)
                if task is not None:
                    pending.add(task)
                    task.add_done_callback(pending.discard)
            await asyncio.gather(*pending, return_exceptions=True)
        except asyncio.CancelledError:
            # stop the engine's work, let it save its progress, then let the
            # cancellation through
            await asyncio.shield(self._stop(op, pending))
            raise
        return op.finish()

    async def _stop(self, op: Operation, pending: set[asyncio.Task[Any]]) -> None:
        for task in list(pending):
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await self._in_executor(op.cancel)
        while not op.done:
            await self._in_executor(op.step, POLL_WAIT_MS)

    def _dispatch(self, op: Operation, response: core_pb2.PollResponse) -> Optional[asyncio.Task[Any]]:
        kind = response.WhichOneof("task")
        if kind == "event":
            if self._on_event is None:
                return None
            return asyncio.create_task(self._handle_event(response.event))
        if kind == "state":
            return asyncio.create_task(self._handle_state(op, response.state))
        if kind == "function":
            return asyncio.create_task(self._handle_function(op, response.function))
        return None

    async def _handle_event(self, event: core_pb2.Event) -> None:
        assert self._on_event is not None
        await _call_maybe_async(self._on_event, Event._from_proto(event, self._classes))

    async def _handle_state(self, op: Operation, task: core_pb2.StateTask) -> None:
        result = await _answer_state_async(self._state_store, task)
        await self._in_executor(op.complete, task.task_id, result)

    async def _handle_function(self, op: Operation, task: core_pb2.FunctionTask) -> None:
        fn = self._functions.get(task.name)
        if fn is None:
            result = failed_result(KeyError(f"no Python function is registered as {task.name}"))
        else:
            try:
                value = await _call_maybe_async(fn, *decode_args(bytes(task.args)))
                result = core_pb2.FunctionResult(result=encode_result(value))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - every failure becomes the call's error
                result = failed_result(exc)
        await self._in_executor(op.complete, task.task_id, result)

    async def validate(self, *paths: str | os.PathLike[str]) -> None:
        """Check the configuration at ``paths`` is valid; raises :class:`xcl.ConfigError`."""
        await self._run("StartValidate", core_pb2.StartValidateRequest(paths=_paths(paths)))

    async def apply(self, *paths: str | os.PathLike[str]) -> None:
        """Apply the configuration at ``paths``."""
        await self._run("StartApply", core_pb2.StartApplyRequest(paths=_paths(paths)))

    async def diff(self, *paths: str | os.PathLike[str], reveal_sensitive: bool = False) -> Diff:
        """What applying the configuration at ``paths`` would do."""
        result = await self._run("StartDiff", core_pb2.StartDiffRequest(paths=_paths(paths), reveal_sensitive=reveal_sensitive))
        assert result is not None
        return result

    async def destroy(self) -> None:
        """Destroy every entity in the saved state."""
        await self._run("StartDestroy", core_pb2.StartDestroyRequest())

    async def load(self) -> None:
        """Read the saved state into the configuration."""
        await self._run("StartLoad", core_pb2.StartLoadRequest())

    # -- lookups -----------------------------------------------------------

    async def _lookup(self, method: str, request: Any) -> Any:
        handle = await self._ensure_open()
        return await self._in_executor(self._client.call, handle, method, request)

    async def entities(self) -> list[Any]:
        """Every entity the configuration holds."""
        from xcl._schema import hydrate

        response = await self._lookup("Entities", core_pb2.EntitiesRequest())
        return [hydrate(json.loads(e), registry=self._classes) for e in response.entities]

    async def entity_count(self) -> int:
        """How many entities the configuration holds."""
        response = await self._lookup("Entities", core_pb2.EntitiesRequest())
        return len(response.entities)

    async def find(self, cls: Optional[type], address: str) -> Any:
        """The entity at ``address``; see :meth:`xcl.Config.find`."""
        response = await self._lookup("Find", core_pb2.FindRequest(address=address))
        return _SyncConfig._hydrate(self, response.entity, cls)  # type: ignore[arg-type]

    async def find_by_type(self, cls: Optional[type], *path: str) -> list[Any]:
        """Every entity of the type the segments name."""
        response = await self._lookup("FindByType", core_pb2.FindByTypeRequest(path=list(path)))
        return [_SyncConfig._hydrate(self, e, cls) for e in response.entities]  # type: ignore[arg-type]

    async def find_one(self, cls: Optional[type], *path: str) -> Any:
        """The single entity of the type the segments name."""
        response = await self._lookup("FindOne", core_pb2.FindByTypeRequest(path=list(path)))
        return _SyncConfig._hydrate(self, response.entity, cls)  # type: ignore[arg-type]

    async def all(self, cls: type) -> list[Any]:
        """Every entity of ``cls``, a class registered on this configuration."""
        type_name, subtype = self._classes.names_of(cls)
        path = [type_name, subtype] if subtype else [type_name]
        return await self.find_by_type(cls, *path)

    async def outputs(self) -> dict[str, Any]:
        """The configuration's outputs, by address."""
        response = await self._lookup("Outputs", core_pb2.OutputsRequest())
        return json.loads(response.outputs_json) if response.outputs_json else {}

    async def encode_saved_entity(self, data: bytes, *, highlight: bool = False) -> str:
        """A saved record rendered as configuration text."""
        response = await self._lookup("EncodeSavedEntity", core_pb2.EncodeSavedEntityRequest(entity=bytes(data), highlight=highlight))
        return response.text.decode()


async def _call_maybe_async(fn: Callable[..., Any], *args: Any) -> Any:
    """Call ``fn``: awaited when it is a coroutine function or returns an awaitable, otherwise in the default executor."""
    if inspect.iscoroutinefunction(fn):
        return await fn(*args)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, fn, *args)
    if inspect.isawaitable(result):
        return await result
    return result


async def _answer_state_async(store: Any, task: core_pb2.StateTask) -> core_pb2.StateResult:
    """Answer a state task, awaiting the store's method when it is async."""
    if store is None:
        return answer_state(None, task)
    try:
        kind = task.kind
        if kind == core_pb2.StateTask.LOAD:
            records = await _call_maybe_async(store.load) or []
            return core_pb2.StateResult(entities=[_record_bytes(r) for r in records])
        if kind == core_pb2.StateTask.SAVE:
            await _call_maybe_async(store.save, [bytes(e) for e in task.entities])
            return core_pb2.StateResult()
        if kind == core_pb2.StateTask.EXISTS:
            return core_pb2.StateResult(exists=bool(await _call_maybe_async(store.exists)))
        if kind == core_pb2.StateTask.CLEAR:
            await _call_maybe_async(store.clear)
            return core_pb2.StateResult()
        raise RuntimeError(f"unknown state task kind {kind}")
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure becomes the task's error
        return core_pb2.StateResult(error=core_pb2.Error(code="state_store", message=str(exc) or exc.__class__.__name__))


def _record_bytes(record: Any) -> bytes:
    if isinstance(record, (bytes, bytearray)):
        return bytes(record)
    if isinstance(record, str):
        return record.encode()
    return json.dumps(record).encode()


def _paths(paths: Iterable[str | os.PathLike[str]]) -> list[str]:
    listed = [os.fspath(p) for p in paths]
    if not listed:
        raise _errors.InvalidArgumentError("at least one path is required", details={"argument": "paths"})
    return listed


__all__ = ["Config"]
