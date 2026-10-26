"""XCL, the declarative configuration language, for Python.

The package, published as ``xcl-lang`` and imported as ``xcl``, drives the xcl
engine, a small program bundled in the wheel and run as a subprocess, the same
way on every platform, so a Python program validates, diffs, applies, loads and
destroys configuration exactly as a Go program does, uses the same Go plugins,
and adds its own Python functions to configuration. ``import xcl`` starts
nothing: the engine starts the first time a configuration is created, is
shared by every configuration, and stops when the last one is closed.
"""

from xcl._errors import (
    CancelledError,
    ConfigError,
    EmptyConfigurationError,
    EngineExitedError,
    EngineNotFoundError,
    EngineVersionError,
    Error,
    ForkedProcessError,
    FunctionNameClashError,
    InternalBindingError,
    InternalError,
    InvalidArgumentError,
    InvalidFunctionError,
    InvalidSavedDataError,
    InvalidStyleError,
    InvalidThemeError,
    InvalidTypeError,
    MaskNotReversibleError,
    NotAnEntityError,
    NotEncodableError,
    NotFoundError,
    NotRegisteredError,
    NotTypeableError,
    NotUniqueError,
    OperationInProgressError,
    PluginLoadError,
    PluginNotFoundError,
    PluginVerificationError,
    Problem,
    ProviderError,
    RemovedNameError,
    TypeFormError,
    TypeMismatchError,
    TypeNameClashError,
    UnknownTypeError,
    UnrecoverableError,
    UnregisteredTypeError,
)
from xcl._entity import Entity, Meta
from xcl._schema import SchemaError
from xcl._types import UNKNOWN, Computed, Sensitive, field
from xcl._logbridge import logging_handler
from xcl._poll import StateStore
from xcl._print import format_error, print_diff, print_error
from xcl._version import __version__
from xcl import highlight, mask
from xcl.config import Config
from xcl.diff import Change, Diff, ResourceDiff, Summary
from xcl.events import Event, EventDataLevel
from xcl.registry import GitHubRegistry, LocalRegistry

__all__ = [
    "__version__",
    "Config",
    "LocalRegistry",
    "GitHubRegistry",
    "StateStore",
    "Event",
    "EventDataLevel",
    "Diff",
    "ResourceDiff",
    "Change",
    "Summary",
    "mask",
    "highlight",
    "Entity",
    "Meta",
    "Sensitive",
    "Computed",
    "field",
    "UNKNOWN",
    "SchemaError",
    "Error",
    "Problem",
    "NotFoundError",
    "NotUniqueError",
    "UnknownTypeError",
    "NotTypeableError",
    "NotRegisteredError",
    "TypeMismatchError",
    "NotAnEntityError",
    "TypeNameClashError",
    "TypeFormError",
    "InvalidTypeError",
    "FunctionNameClashError",
    "InvalidFunctionError",
    "PluginLoadError",
    "PluginNotFoundError",
    "PluginVerificationError",
    "EmptyConfigurationError",
    "UnregisteredTypeError",
    "InvalidSavedDataError",
    "NotEncodableError",
    "UnrecoverableError",
    "MaskNotReversibleError",
    "ConfigError",
    "ProviderError",
    "CancelledError",
    "OperationInProgressError",
    "InvalidArgumentError",
    "InternalError",
    "ForkedProcessError",
    "EngineVersionError",
    "EngineNotFoundError",
    "EngineExitedError",
    "InternalBindingError",
    "RemovedNameError",
    "InvalidStyleError",
    "InvalidThemeError",
    "engine_version",
    "print_error",
    "format_error",
    "print_diff",
    "logging_handler",
]


def engine_version() -> str:
    """The version the bundled engine reports, loading it if it is not loaded yet."""
    from xcl._client import default_client

    return default_client().engine_version()


# _REMOVED are the names removed from the package, with what replaces each,
# so code still using one fails with directions rather than a bare
# AttributeError; they can go once code has had time to move
_PLAIN_DATACLASS = (
    "Declare the block type as a plain dataclass and give its type name when registering it:\n"
    "\n"
    "    @dataclass\n"
    "    class App:\n"
    "        image: str\n"
    "        meta: xcl.Meta | None = None  # optional: the block's metadata, meta.id its address\n"
    "\n"
    "    local.register_type(App, \"app\")\n"
    "\n"
    "See \"Migrating from xcl.Resource and @xcl.entity\" in the README."
)
_REMOVED = {
    "Resource": "xcl.Resource has been removed; a block type needs no base class. " + _PLAIN_DATACLASS,
    "entity": "xcl.entity has been removed; a block type needs no decorator. " + _PLAIN_DATACLASS,
}


def __getattr__(name: str) -> object:
    if name in _REMOVED:
        raise RemovedNameError(name, _REMOVED[name])
    raise AttributeError(f"module 'xcl' has no attribute {name!r}")
