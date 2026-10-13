"""The typed client: CoreService messages in, messages out.

The client is built from the generated descriptor at run time, so nothing
beyond the message classes is generated. ``call`` serialises a request,
passes it to the transport, and decodes the response into the method's
output class, or raises the exception registered for the engine's error
code. On first use it checks that the engine's version equals the package's.
"""

from __future__ import annotations

import threading
from typing import Any

from google.protobuf import message_factory

from xcl import _errors
from xcl._core import core_pb2
from xcl._transport import Transport
from xcl._version import __version__

STATUS_OK = 0
STATUS_ERROR = 1

_SERVICE = core_pb2.DESCRIPTOR.services_by_name["CoreService"]


def normalise_version(version: str) -> str:
    """The form versions are compared in: the tag's leading ``v`` removed."""
    return version[1:] if version.startswith("v") else version


class Client:
    """Dispatches CoreService methods over a transport."""

    def __init__(self, transport: Transport, *, check_version: bool = True) -> None:
        self._transport = transport
        self._check_version = check_version
        self._checked = False
        self._lock = threading.Lock()
        self._engine_version: str | None = None

    @property
    def transport(self) -> Transport:
        return self._transport

    def call(self, handle: int, method: str, request: Any) -> Any:
        """Call ``method`` with ``request`` on ``handle`` and return the decoded response.

        A status of 1 raises the exception for the engine's error code; a
        negative status raises :class:`InternalBindingError`.
        """
        self._ensure_version()
        return self._call(handle, method, request)

    def _call(self, handle: int, method: str, request: Any) -> Any:
        descriptor = _SERVICE.methods_by_name[method]
        status, body = self._transport.call(handle, method, request.SerializeToString())
        if status == STATUS_ERROR:
            raise _errors.from_proto(core_pb2.Error.FromString(body))
        if status != STATUS_OK:
            raise _errors.InternalBindingError(method, status)
        return message_factory.GetMessageClass(descriptor.output_type).FromString(body)

    def release(self, handle: int) -> None:
        """Free the configuration behind ``handle``."""
        status = self._transport.release(handle)
        if status != STATUS_OK:
            raise _errors.InternalBindingError("Release", status)

    def engine_version(self) -> str:
        """The engine's version, as GetVersion reports it."""
        self._ensure_version()
        assert self._engine_version is not None
        return self._engine_version

    def _ensure_version(self) -> None:
        if self._checked:
            return
        with self._lock:
            if self._checked:
                return
            response = self._call(0, "GetVersion", core_pb2.GetVersionRequest())
            self._engine_version = response.version
            if self._check_version and normalise_version(response.version) != normalise_version(__version__):
                raise _errors.EngineVersionError(
                    f"the xcl engine reports version {response.version}, but this is xcl-lang package "
                    f"version {__version__}; the xcl-lang package only runs against the engine of its own release",
                    package=__version__,
                    engine=response.version,
                )
            self._checked = True


_default_client: Client | None = None
_default_lock = threading.Lock()


def default_client() -> Client:
    """The client every configuration uses unless given another.

    Its transport is chosen on first use by
    :func:`xcl._transport.select.select_transport`: the bundled engine
    program, or the shared library when ``XCL_TRANSPORT=inprocess``. Nothing
    is started until a call is made.
    """
    global _default_client
    if _default_client is None:
        with _default_lock:
            if _default_client is None:
                from xcl._transport.select import select_transport

                _default_client = Client(select_transport())
    return _default_client
