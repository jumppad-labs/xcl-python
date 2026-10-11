"""XCL, the declarative configuration language, for Python.

The package drives the xcl engine, a Go shared library bundled in the wheel,
so a Python program validates, diffs, applies, loads and destroys
configuration exactly as a Go program does, uses the same Go plugins, and
adds its own Python functions to configuration. ``import xcl`` loads nothing:
the engine is loaded the first time a configuration is created.
"""

from xcl._errors import (
    CancelledError,
    ConfigError,
    EmptyConfigurationError,
    EngineVersionError,
    Error,
    ForkedProcessError,
    FunctionNameClashError,
    InternalBindingError,
    InternalError,
    InvalidArgumentError,
    InvalidFunctionError,
    InvalidSavedDataError,
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
    TypeFormError,
    TypeMismatchError,
    TypeNameClashError,
    UnknownTypeError,
    UnrecoverableError,
    UnregisteredTypeError,
)
from xcl._entity import Entity, Meta, Resource, entity
from xcl._schema import SchemaError
from xcl._types import UNKNOWN, Computed, Sensitive, field
from xcl._version import __version__
from xcl.config import Config

__all__ = [
    "__version__",
    "Config",
    "entity",
    "Resource",
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
    "InternalBindingError",
    "engine_version",
]


def engine_version() -> str:
    """The version the bundled engine reports, loading it if it is not loaded yet."""
    from xcl._client import default_client

    return default_client().engine_version()
