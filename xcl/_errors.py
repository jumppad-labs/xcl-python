"""The exceptions the package raises.

Every application error the engine reports crosses as one ``Error`` message
with a stable ``code``, a message for people, ``details`` by name and the
``causes`` it collects. ``from_proto`` turns it into the exception class
registered for its code, so a program catches ``xcl.NotFoundError`` rather
than inspecting a code; an unknown code raises the base :class:`Error`, so it
is still catchable.

Three errors are raised by the binding itself, never by the engine:
:class:`ForkedProcessError`, :class:`EngineVersionError` and
:class:`InternalBindingError`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class Error(Exception):
    """An error reported by the xcl engine.

    ``code`` is the stable code a subclass is registered for, ``message`` the
    engine's message, ``details`` the fields of the engine's detail type by
    name, and ``causes`` the errors it collects, in order.
    """

    code: str = "internal"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Mapping[str, str] | None = None,
        causes: Sequence[Error] = (),
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details: dict[str, str] = dict(details or {})
        self.causes: list[Error] = list(causes)

    def __str__(self) -> str:
        return self.message


class NotFoundError(Error):
    """No entity exists at the address asked for; ``details["address"]`` names it."""

    code = "not_found"


class NotUniqueError(Error):
    """More than one entity matched a lookup that expects exactly one; ``details["count"]`` says how many."""

    code = "not_unique"


class UnknownTypeError(Error):
    """A lookup named a type nothing declares; ``details["name"]`` is the segment."""

    code = "unknown_type"


class NotTypeableError(Error):
    """A lookup's segments span more than one type, such as a type given without its subtype."""

    code = "not_typeable"


class NotRegisteredError(Error):
    """A type was asked for that no registry declares."""

    code = "not_registered"


class TypeMismatchError(Error):
    """An entity was found but is not of the type asked for."""

    code = "type_mismatch"


class NotAnEntityError(Error):
    """A lookup named something that is not a declaration of its own, such as a nested block."""

    code = "not_an_entity"


class TypeNameClashError(Error):
    """Two registries, or a registry and a builtin, declare the same type."""

    code = "type_name_clash"


class TypeFormError(Error):
    """A type was declared both with and without a subtype."""

    code = "type_form"


class InvalidTypeError(Error):
    """A declared type has a field configuration cannot be decoded into."""

    code = "invalid_type"


class FunctionNameClashError(Error):
    """A function name is offered twice; ``details`` name both sources and their registries."""

    code = "function_name_clash"


class InvalidFunctionError(Error):
    """A function cannot be called from configuration, such as one with an unsupported parameter type."""

    code = "invalid_function"


class PluginLoadError(Error):
    """A plugin failed to load; ``details["plugin"]`` and ``details["registry"]`` name it."""

    code = "plugin_load"


class PluginNotFoundError(Error):
    """A plugin release was not found for this platform; ``details`` carry the repository, version and platform."""

    code = "plugin_not_found"


class PluginVerificationError(Error):
    """A plugin release failed its checksum or signature check and was refused."""

    code = "plugin_verification"


class EmptyConfigurationError(Error):
    """The configuration declares no blocks; use ``destroy`` to remove everything."""

    code = "empty_configuration"


class UnregisteredTypeError(Error):
    """A saved record names a type no registry declares."""

    code = "unregistered_type"


class InvalidSavedDataError(Error):
    """A saved record cannot be decoded."""

    code = "invalid_saved_data"


class NotEncodableError(Error):
    """A value cannot be rendered as configuration text."""

    code = "not_encodable"


class UnrecoverableError(Error):
    """A masked value in state cannot be recovered with the mask configured."""

    code = "unrecoverable"


class MaskNotReversibleError(Error):
    """The state mask cannot recover the values it masks, so it is refused."""

    code = "mask_not_reversible"


@dataclass(frozen=True)
class Problem:
    """One problem in configuration, positioned where it was found."""

    file: str
    line: int
    column: int
    message: str

    def __str__(self) -> str:
        where = self.file
        if self.line:
            where = f"{self.file}:{self.line}"
            if self.column:
                where = f"{where}:{self.column}"
        return f"{where}: {self.message}" if where else self.message


class ConfigError(Error):
    """The configuration is invalid; ``problems`` lists each problem with its file and line."""

    code = "config"

    @property
    def problems(self) -> list[Problem]:
        """Every positioned problem the error collects, in order."""
        found = []
        for cause in self.causes:
            if cause.code in ("config", "provider") and "file" in cause.details:
                found.append(
                    Problem(
                        file=cause.details.get("file", ""),
                        line=_int(cause.details.get("line")),
                        column=_int(cause.details.get("column")),
                        message=cause.details.get("summary") or cause.message,
                    )
                )
        if not found and "file" in self.details:
            found.append(
                Problem(
                    file=self.details.get("file", ""),
                    line=_int(self.details.get("line")),
                    column=_int(self.details.get("column")),
                    message=self.details.get("summary") or self.message,
                )
            )
        return found


class ProviderError(Error):
    """A provider failed during a lifecycle step; ``details["address"]`` and ``details["step"]`` say where."""

    code = "provider"


class CancelledError(Error):
    """The operation was cancelled before it reached every entity; the progress made was saved."""

    code = "cancelled"


class OperationInProgressError(Error):
    """A call was refused because an operation is running on the configuration."""

    code = "operation_in_progress"


class InvalidArgumentError(Error):
    """A request parsed but made no sense, such as an operation with no paths."""

    code = "invalid_argument"


class InternalError(Error):
    """An error the engine could not classify."""

    code = "internal"


class ForkedProcessError(Error):
    """XCL was used in a process forked after the parent had used it.

    The engine is a Go runtime, which cannot be forked. Either start worker
    processes with the ``spawn`` start method, or create the configuration
    after the fork (in gunicorn's ``post_fork`` hook, or celery's
    ``worker_process_init`` signal) so each child loads its own engine.
    """

    code = "forked_process"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or (
                "xcl cannot be used in a process forked after the parent used it: "
                "the engine is a Go runtime, which does not survive fork(). "
                'Use the "spawn" start method, multiprocessing.set_start_method("spawn"), '
                "or create the configuration after the fork, in gunicorn's post_fork hook "
                "or celery's worker_process_init signal, so each child loads its own engine."
            )
        )


class EngineVersionError(Error):
    """The engine's version, or its ABI version, is not the one this package was built for."""

    code = "engine_version"

    def __init__(self, message: str, *, package: str, engine: str) -> None:
        super().__init__(message, details={"package": package, "engine": engine})
        self.package = package
        self.engine = engine


class InternalBindingError(Error):
    """The engine refused a call with a negative status, which is a bug in this package."""

    code = "internal_binding"

    def __init__(self, method: str, status: int) -> None:
        reason = _STATUS_REASONS.get(status, "unknown status")
        super().__init__(
            f"the engine refused {method} with status {status} ({reason}); this is a bug in the xcl package",
            details={"method": method, "status": str(status)},
        )
        self.method = method
        self.status = status


_STATUS_REASONS = {
    -1: "unknown method",
    -2: "the request did not parse",
    -3: "unknown or released handle",
    -4: "handle given where none is taken, or missing where one is needed",
}


# every exception class registered for a code, built from the classes above
_BY_CODE: dict[str, type[Error]] = {
    cls.code: cls
    for cls in (
        NotFoundError,
        NotUniqueError,
        UnknownTypeError,
        NotTypeableError,
        NotRegisteredError,
        TypeMismatchError,
        NotAnEntityError,
        TypeNameClashError,
        TypeFormError,
        InvalidTypeError,
        FunctionNameClashError,
        InvalidFunctionError,
        PluginLoadError,
        PluginNotFoundError,
        PluginVerificationError,
        EmptyConfigurationError,
        UnregisteredTypeError,
        InvalidSavedDataError,
        NotEncodableError,
        UnrecoverableError,
        MaskNotReversibleError,
        ConfigError,
        ProviderError,
        CancelledError,
        OperationInProgressError,
        InvalidArgumentError,
        InternalError,
    )
}


def class_for(code: str) -> type[Error]:
    """Return the exception class registered for ``code``, or :class:`Error`."""
    return _BY_CODE.get(code, Error)


def from_proto(err: Any) -> Error:
    """Turn an ``Error`` message from the engine into the exception for its code."""
    causes = [from_proto(cause) for cause in err.causes]
    cls = class_for(err.code)
    if cls is Error:
        return Error(err.message, code=err.code, details=dict(err.details), causes=causes)
    return cls(err.message, details=dict(err.details), causes=causes)


def _int(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0
