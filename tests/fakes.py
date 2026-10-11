"""A fake transport: answers CoreService calls from a script, with no engine."""

from __future__ import annotations

from typing import Any

import xcl
from xcl._core import core_pb2

STATUS_OK = 0
STATUS_ERROR = 1


class FakeTransport:
    """Records every call and answers each method from ``script``.

    A script entry is one of:

    - a response message, answered with status 0 and its serialised bytes
    - a ``core_pb2.Error``, answered with status 1 and its serialised bytes
    - an int, answered as that status with an empty body

    ``GetVersion`` reports the package version with ABI 1 and ``CreateConfig``
    returns handle 7 unless the script overrides them. ``release`` returns
    ``release_status`` and records the handle in ``released``.
    """

    def __init__(self, script: dict[str, Any] | None = None, *, release_status: int = STATUS_OK) -> None:
        self.script: dict[str, Any] = {
            "GetVersion": core_pb2.GetVersionResponse(version=xcl.__version__, abi_version=1),
            "CreateConfig": core_pb2.CreateConfigResponse(handle=7),
        }
        self.script.update(script or {})
        self.release_status = release_status
        self.calls: list[tuple[int, str, bytes]] = []
        self.released: list[int] = []

    def call(self, handle: int, method: str, request: bytes) -> tuple[int, bytes]:
        self.calls.append((handle, method, request))
        answer = self.script[method]
        if isinstance(answer, int):
            return answer, b""
        if isinstance(answer, core_pb2.Error):
            return STATUS_ERROR, answer.SerializeToString()
        return STATUS_OK, answer.SerializeToString()

    def release(self, handle: int) -> int:
        self.released.append(handle)
        return self.release_status

    def methods_called(self) -> list[str]:
        return [method for _, method, _ in self.calls]
