"""The transport: the only layer that touches the engine's C library.

A transport moves bytes: ``call`` passes a serialised CoreService request to
the engine and returns the status and the serialised response, and
``release`` frees a configuration handle. Everything above it, the typed
client and the public API, is written against this protocol, so tests run
against a fake transport with no engine, and a later out-of-process
transport is another class with the same two methods.
"""

from __future__ import annotations

from typing import Protocol


class Transport(Protocol):
    """What the typed client needs from a transport."""

    def call(self, handle: int, method: str, request: bytes) -> tuple[int, bytes]:
        """Dispatch one CoreService method and return its status and response bytes."""
        ...

    def release(self, handle: int) -> int:
        """Free the configuration behind ``handle`` and return the status."""
        ...


from xcl._transport.inprocess import InProcessTransport  # noqa: E402

__all__ = ["Transport", "InProcessTransport"]
