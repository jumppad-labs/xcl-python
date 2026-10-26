"""The poll loop: one operation, driven step by step.

An operation runs inside the engine; everything it needs from Python,
function calls, state-store calls and events, arrives as a task through
``Poll``, and its end as the finished task. :class:`Operation` owns that loop
for one operation and nothing else: ``step`` takes the next task, ``complete``
answers one, ``finish`` turns the finished task into the operation's result,
and ``cancel`` asks the engine to stop. The synchronous API drives it on the
calling thread and the asyncio API from an executor, so neither has loop
logic of its own.

:class:`Handlers` is what a driver answers tasks with; :func:`answer_state`
and :func:`answer_function` turn a store or a function call into the task's
result, and :func:`drive` runs the whole loop synchronously.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from typing import Any, Optional, Protocol

from xcl import _errors
from xcl._classes import ClassMap
from xcl._client import Client
from xcl._core import core_pb2
from xcl._functions import call_function, failed_result
from xcl.diff import Diff
from xcl.events import Event
from xcl.highlight._kinds import _tokens_from_proto

# POLL_WAIT_MS is how long one Poll may block; it bounds how quickly a cancel
# is noticed on the Python side
POLL_WAIT_MS = 200


class StateStore(Protocol):
    """A state store written in Python, given to :class:`xcl.Config` as ``state_store``.

    ``load`` returns the saved records, each as the JSON bytes the engine
    gave ``save`` or a dict of the same; ``save`` receives every record of the
    state as JSON bytes, with real sensitive values unless a state mask is
    set; ``exists`` says whether anything was saved; ``clear`` removes it.
    Under :class:`xcl.aio.Config` the methods may be ``async def``.
    """

    def load(self) -> Any:
        """Return the saved records, each as JSON bytes or a dict."""
        ...

    def save(self, entities: list[bytes]) -> Any:
        """Save every record of the state, given as JSON bytes."""
        ...

    def exists(self) -> Any:
        """Whether anything has been saved."""
        ...

    def clear(self) -> Any:
        """Remove everything saved."""
        ...


@dataclasses.dataclass
class Handlers:
    """What a driver answers tasks with."""

    functions: Mapping[str, Callable[..., Any]] = dataclasses.field(default_factory=dict)
    store: Optional[Any] = None
    on_event: Optional[Callable[[Event], Any]] = None
    classes: Optional[ClassMap] = None


class Operation:
    """One operation in the engine, polled and completed through the client."""

    def __init__(self, client: Client, handle: int, operation_id: int) -> None:
        self._client = client
        self._handle = handle
        self._id = operation_id
        self._finished: Optional[core_pb2.OperationFinished] = None

    @property
    def id(self) -> int:
        return self._id

    @property
    def done(self) -> bool:
        return self._finished is not None

    def step(self, wait_ms: int = POLL_WAIT_MS) -> Optional[core_pb2.PollResponse]:
        """The next task, waiting up to ``wait_ms`` for one, or ``None``; the finished task is kept."""
        response = self._client.call(self._handle, "Poll", core_pb2.PollRequest(wait_ms=wait_ms))
        kind = response.WhichOneof("task")
        if kind is None:
            return None
        if kind == "finished":
            self._finished = response.finished
        return response

    def complete(self, task_id: int, result: Any) -> None:
        """Answer a task with a ``StateResult`` or a ``FunctionResult``."""
        request = core_pb2.CompleteRequest(task_id=task_id)
        if isinstance(result, core_pb2.StateResult):
            request.state.CopyFrom(result)
        elif isinstance(result, core_pb2.FunctionResult):
            request.function.CopyFrom(result)
        else:
            raise TypeError(f"a task is completed with a StateResult or a FunctionResult, not {type(result).__name__}")
        try:
            self._client.call(self._handle, "Complete", request)
        except _errors.InvalidArgumentError:
            # the operation ended, or was cancelled, before the answer: the
            # task is no longer waited for, which is harmless
            pass

    def cancel(self) -> None:
        """Ask the engine to stop the operation; it ends with the cancelled code once it has."""
        try:
            self._client.call(self._handle, "Cancel", core_pb2.CancelRequest(operation_id=self._id))
        except _errors.InvalidArgumentError:
            pass

    def finish(self) -> Optional[Diff]:
        """The operation's result: the diff of a diff, ``None`` otherwise; raises its error."""
        if self._finished is None:
            raise RuntimeError("the operation has not finished")
        if self._finished.HasField("error"):
            raise _errors.from_proto(self._finished.error)
        if self._finished.diff_json:
            return Diff._from_json(self._finished.diff_json, tokens=tuple(_tokens_from_proto(self._finished.diff_tokens)))
        return None


def answer_state(store: Any, task: core_pb2.StateTask, *, result_of: Callable[[Any], Any] = lambda v: v) -> core_pb2.StateResult:
    """Call the store method a state task asks for and return the result.

    ``result_of`` unwraps what the store returned, for a driver that awaited
    it; an exception becomes the result's error, which fails the operation.
    """
    try:
        if store is None:
            raise RuntimeError("the engine asked the host for state, but no state store was given")
        kind = task.kind
        if kind == core_pb2.StateTask.LOAD:
            records = result_of(store.load()) or []
            return core_pb2.StateResult(entities=[_record_bytes(r) for r in records])
        if kind == core_pb2.StateTask.SAVE:
            result_of(store.save([bytes(e) for e in task.entities]))
            return core_pb2.StateResult()
        if kind == core_pb2.StateTask.EXISTS:
            return core_pb2.StateResult(exists=bool(result_of(store.exists())))
        if kind == core_pb2.StateTask.CLEAR:
            result_of(store.clear())
            return core_pb2.StateResult()
        raise RuntimeError(f"unknown state task kind {kind}")
    except Exception as exc:  # noqa: BLE001 - every failure becomes the task's error
        return core_pb2.StateResult(error=core_pb2.Error(code="state_store", message=str(exc) or exc.__class__.__name__))


def answer_function(functions: Mapping[str, Callable[..., Any]], task: core_pb2.FunctionTask) -> core_pb2.FunctionResult:
    """Call the registered function a function task names and return its result."""
    fn = functions.get(task.name)
    if fn is None:
        return failed_result(KeyError(f"no Python function is registered as {task.name}"))
    return call_function(fn, bytes(task.args))


def _record_bytes(record: Any) -> bytes:
    if isinstance(record, (bytes, bytearray)):
        return bytes(record)
    if isinstance(record, str):
        return record.encode()
    return json.dumps(record).encode()


def drive(op: Operation, handlers: Handlers) -> Optional[Diff]:
    """Run ``op`` to its end on the calling thread, answering every task from ``handlers``.

    A ``KeyboardInterrupt`` while it runs cancels the operation, drains it to
    its finished task so the engine saves its progress, and is re-raised.
    """
    try:
        while not op.done:
            response = op.step()
            if response is None:
                continue
            _dispatch(op, response, handlers)
    except KeyboardInterrupt:
        op.cancel()
        _drain(op)
        raise
    return op.finish()


def _dispatch(op: Operation, response: core_pb2.PollResponse, handlers: Handlers) -> None:
    kind = response.WhichOneof("task")
    if kind == "event":
        if handlers.on_event is not None:
            handlers.on_event(Event._from_proto(response.event, handlers.classes))
    elif kind == "state":
        op.complete(response.state.task_id, answer_state(handlers.store, response.state))
    elif kind == "function":
        op.complete(response.function.task_id, answer_function(handlers.functions, response.function))


def _drain(op: Operation) -> None:
    while not op.done:
        try:
            op.step()
        except KeyboardInterrupt:
            continue
