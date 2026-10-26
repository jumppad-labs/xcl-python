"""Asyncio event delivery: one event at a time, in the order the engine sent them."""

from __future__ import annotations

import asyncio
import threading
import time

import xcl.aio
from xcl._client import Client
from xcl._core import core_pb2
from xcl.events import Event
from fakes import FakeTransport

RESOURCES = ["app.one", "app.two", "app.three", "app.four", "app.five"]


def event_response(resource_id: str) -> core_pb2.PollResponse:
    return core_pb2.PollResponse(
        event=core_pb2.Event(
            time_unix_nano=1_700_000_000_000_000_000,
            source="core",
            operation="create",
            phase="success",
            resource_type="app",
            resource_id=resource_id,
        )
    )


def five_events_transport() -> FakeTransport:
    """An apply whose Poll gives the five events of RESOURCES in order, then finishes."""
    return FakeTransport(
        {
            "StartApply": core_pb2.StartOperationResponse(operation_id=3),
            "Poll": [event_response(r) for r in RESOURCES]
            + [core_pb2.PollResponse(finished=core_pb2.OperationFinished(operation_id=3))],
        }
    )


class CancellableTransport(FakeTransport):
    """An apply whose Poll gives the five events, then nothing until Cancel is called, then finishes cancelled."""

    def __init__(self) -> None:
        super().__init__({"StartApply": core_pb2.StartOperationResponse(operation_id=3), "Cancel": core_pb2.CancelResponse()})
        self.events = [event_response(r) for r in RESOURCES]
        self.cancelled = False

    def call(self, handle: int, method: str, request: bytes) -> tuple[int, bytes]:
        if method == "Poll":
            self.calls.append((handle, method, request))
            if self.events:
                return 0, self.events.pop(0).SerializeToString()
            if self.cancelled:
                finished = core_pb2.OperationFinished(
                    operation_id=3, error=core_pb2.Error(code="cancelled", message="the operation was cancelled")
                )
                return 0, core_pb2.PollResponse(finished=finished).SerializeToString()
            time.sleep(0.01)
            return 0, core_pb2.PollResponse().SerializeToString()
        if method == "Cancel":
            self.cancelled = True
        return super().call(handle, method, request)


def apply_with(on_event, transport: FakeTransport | None = None) -> None:
    async def run() -> None:
        config = xcl.aio.Config(on_event=on_event, client=Client(transport or five_events_transport()))
        try:
            await config.apply("main.xcl")
        finally:
            await config.close()

    asyncio.run(run())


def test_async_plain_handler_receives_events_in_order():
    received: list[str] = []

    def on_event(event: Event) -> None:
        if event.resource_id == "app.one":
            time.sleep(0.05)
        received.append(event.resource_id)

    apply_with(on_event)

    assert received == RESOURCES


def test_async_plain_handler_called_one_at_a_time():
    lock = threading.Lock()
    running = 0
    most_running = 0
    received: list[str] = []

    def on_event(event: Event) -> None:
        nonlocal running, most_running
        with lock:
            running += 1
            most_running = max(most_running, running)
        time.sleep(0.01)
        received.append(event.resource_id)
        with lock:
            running -= 1

    apply_with(on_event)

    assert most_running == 1
    assert received == RESOURCES


def test_async_coroutine_handler_receives_events_in_order():
    received: list[str] = []
    delays = {"app.one": 0.05, "app.two": 0.04, "app.three": 0.03, "app.four": 0.02, "app.five": 0.01}

    async def on_event(event: Event) -> None:
        await asyncio.sleep(delays[event.resource_id])
        received.append(event.resource_id)

    apply_with(on_event)

    assert received == RESOURCES


def test_async_coroutine_handler_called_one_at_a_time():
    running = 0
    most_running = 0

    async def on_event(event: Event) -> None:
        nonlocal running, most_running
        running += 1
        most_running = max(most_running, running)
        await asyncio.sleep(0.01)
        running -= 1

    apply_with(on_event)

    assert most_running == 1


def test_async_operation_returns_after_last_event_handled():
    received: list[str] = []

    def on_event(event: Event) -> None:
        if event.resource_id == "app.five":
            time.sleep(0.1)
        received.append(event.resource_id)

    apply_with(on_event)

    assert received == RESOURCES


def test_async_handler_exception_does_not_stop_later_events():
    received: list[str] = []

    def on_event(event: Event) -> None:
        received.append(event.resource_id)
        if event.resource_id == "app.two":
            raise RuntimeError("the handler failed")

    apply_with(on_event)

    assert received == RESOURCES


def test_async_coroutine_handler_exception_does_not_stop_later_events():
    received: list[str] = []

    async def on_event(event: Event) -> None:
        received.append(event.resource_id)
        if event.resource_id == "app.two":
            raise RuntimeError("the handler failed")

    apply_with(on_event)

    assert received == RESOURCES


def test_async_cancel_while_handling_events_stops_operation():
    transport = CancellableTransport()
    received: list[str] = []

    async def run() -> bool:
        never = asyncio.Event()

        async def on_event(event: Event) -> None:
            received.append(event.resource_id)
            await never.wait()

        config = xcl.aio.Config(on_event=on_event, client=Client(transport))
        try:
            task = asyncio.create_task(config.apply("main.xcl"))
            while not received:
                await asyncio.sleep(0.01)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return True
            return False
        finally:
            await config.close()

    cancelled = asyncio.run(run())

    assert cancelled
    assert "Cancel" in transport.methods_called()
    assert received == ["app.one"]
