"""The exceptions the package raises.

Every application error the engine reports crosses as one ``Error`` message
with a stable ``code``, a message for people, ``details`` by name and the
``causes`` it collects. ``from_proto`` turns it into the exception class
registered for its code, so a program catches ``xcl.NotFoundError`` rather
than inspecting a code; an unknown code raises the base :class:`Error`, so it
is still catchable.

Five errors are raised by the binding itself, never by the engine:
:class:`ForkedProcessError`, :class:`EngineVersionError`,
:class:`EngineNotFoundError`, :class:`EngineExitedError` and
:class:`InternalBindingError`.
"""

from __future__ import annotations

import signal
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from os import PathLike
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
    """One problem in configuration, positioned where it was found.

    ``message`` says what is wrong and why. ``detail`` is the why on its own,
    and ``entity`` and ``field`` name the block and the field within it the
    problem is in, when the engine knows them.
    """

    file: str
    line: int
    column: int
    message: str
    detail: str = ""
    entity: str = ""
    field: str = ""

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
                found.append(_problem(cause))
        if not found and "file" in self.details:
            found.append(_problem(self))
        return found


def _problem(error: Error) -> Problem:
    """The problem an error describes from its details: a diagnostic's summary
    and detail together, as its message is written, or an older positioned
    error's summary."""
    details = error.details
    summary = details.get("summary") or error.message
    detail = details.get("detail", "")
    return Problem(
        file=details.get("file", ""),
        line=_int(details.get("line")),
        column=_int(details.get("column")),
        message=f"{summary}; {detail}" if detail else summary,
        detail=detail,
        entity=details.get("entity", ""),
        field=details.get("field", ""),
    )


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
    """A configuration was used in a process forked after the parent had used xcl.

    With the bundled engine program, the default, the configuration's engine
    belongs to the parent: a child creates its own configuration after the
    fork, which starts the child's own engine. With the shared library
    (``XCL_TRANSPORT=inprocess``) the engine is a Go runtime, which cannot be
    forked: start worker processes with the ``spawn`` start method, or create
    the configuration after the fork (in gunicorn's ``post_fork`` hook, or
    celery's ``worker_process_init`` signal) so each child loads its own
    engine.
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


class EngineNotFoundError(Error):
    """The engine this package was asked to run is not where it should be.

    Every wheel bundles the engine program, ``xcl/_bin/xcl-core``, and runs
    it by default; a source build can also build the shared library,
    ``xcl/_lib/libxcl.*``, which ``XCL_TRANSPORT=inprocess`` selects.
    ``details`` names both expected locations as ``program`` and ``library``,
    and the route that was selected as ``transport``.
    """

    code = "engine_not_found"

    def __init__(self, *, program: str | PathLike[str], library: str | PathLike[str], transport: str) -> None:
        wanted = "engine program" if transport == "subprocess" else "shared library"
        super().__init__(
            f"the xcl {wanted} for the {transport} route was not found. "
            f"The engine program is expected at {program}: every xcl-lang wheel bundles it, "
            "and a source checkout builds it with make engine. "
            f"The shared library is expected at {library}: a source checkout builds it with make libxcl, "
            "and XCL_TRANSPORT=inprocess selects it.",
            details={"program": str(program), "library": str(library), "transport": transport},
        )
        self.program = str(program)
        self.library = str(library)
        self.transport = transport


class EngineExitedError(Error):
    """The engine program exited while this package was using it.

    Every call waiting on the engine raises it, carrying the exit status, or
    on Linux and macOS the signal that ended the engine; ``returncode`` is the
    status as :class:`subprocess.Popen` reports it, negative for a signal.
    The host process carries on: the next use starts a fresh engine, and a
    configuration created before the exit raises this error again, since the
    engine that held it is gone.
    """

    code = "engine_exited"

    def __init__(self, returncode: int | None) -> None:
        details: dict[str, str] = {}
        if returncode is None:
            how = "its pipe closed"
        elif returncode < 0:
            name = _signal_name(-returncode)
            how = f"it was ended by signal {name}"
            details["signal"] = name
        else:
            how = f"it exited with status {returncode}"
            details["status"] = str(returncode)
        super().__init__(
            f"the xcl engine stopped unexpectedly: {how}. Configurations created before it stopped are gone; "
            "the next configuration starts a new engine",
            details=details,
        )
        self.returncode = returncode


def _signal_name(number: int) -> str:
    try:
        return signal.Signals(number).name
    except ValueError:
        return str(number)


class InternalBindingError(Error):
    """The engine refused a call with a negative status, which is a bug in this package."""

    code = "internal_binding"

    def __init__(self, method: str, status: int) -> None:
        reason = _STATUS_REASONS.get(status, "unknown status")
        super().__init__(
            f"the engine refused {method} with status {status} ({reason}); this is a bug in the xcl-lang package",
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
