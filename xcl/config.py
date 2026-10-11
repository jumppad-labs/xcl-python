"""The synchronous configuration API."""

from __future__ import annotations

from typing import Any

from xcl._client import Client, default_client
from xcl._core import core_pb2


class Config:
    """A configuration: the Python form of ``xcl.NewConfig``.

    Creating one loads the engine on first use and creates the configuration
    in it; ``close`` releases it, and a ``Config`` is a context manager that
    closes on exit. Every operation and lookup is added by the synchronous
    API; this class carries creation and release.
    """

    def __init__(self, *, client: Client | None = None) -> None:
        self._client = client or default_client()
        self._handle: int | None = None
        request = self._request()
        self._handle = self._client.call(0, "CreateConfig", request).handle

    def _request(self) -> Any:
        return core_pb2.CreateConfigRequest()

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
