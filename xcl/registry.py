"""Registries: where a configuration's types, functions and plugins come from.

A registry is described to the engine when the configuration is created, so
these classes are plain builders: register what the configuration may use,
then pass the registry to :class:`xcl.Config`.
"""

from __future__ import annotations

import dataclasses
import json
import os
from collections.abc import Callable, Iterable
from typing import Any, Optional

from xcl._core import core_pb2
from xcl._schema import SchemaError, is_dataclass_itself, schema_for, signature_for


@dataclasses.dataclass(frozen=True)
class Registration:
    """A class registered as a block type: the class, its type and subtype, and its derived schema."""

    cls: type
    type: str
    subtype: str
    schema: dict[str, Any]


class LocalRegistry:
    """Types, functions and plugins the program itself provides.

    ``plugin_pattern`` names the files a plugin directory is searched for,
    such as ``xcl-plugin-*``; left out, the engine's default applies.
    """

    def __init__(self, *, plugin_pattern: Optional[str] = None) -> None:
        self._plugin_pattern = plugin_pattern
        self._types: list[Registration] = []
        self._functions: dict[str, Callable[..., Any]] = {}
        self._signatures: dict[str, dict[str, Any]] = {}
        self._external_plugins: list[str] = []
        self._plugin_directories: list[str] = []

    def register_type(self, cls: type, type: str, subtype: Optional[str] = None) -> None:  # noqa: A002 - mirrors the Go name
        """Declare the dataclass ``cls`` as the block type ``type``, with an optional ``subtype``.

        The type and subtype become the block's labels and address, as in Go:
        ``register_type(App, "app")`` is written ``app "web" {}`` and found
        at ``app.web``; ``register_type(Database, "database", "postgres")``
        is written ``database "postgres" "main" {}`` and found at
        ``database.postgres.main``. The class needs no base class or
        decorator; it may declare ``meta``, ``disabled`` and ``depends_on``
        to receive them. A class that is not itself a dataclass, an empty
        type name, or an annotation with no configuration form raises
        :class:`SchemaError` naming the class or field.
        """
        self._types.append(_registration(cls, type, subtype))

    def register_function(self, fn: Callable[..., Any], name: Optional[str] = None) -> None:
        """Offer ``fn`` to configuration under ``name``, its own name by default.

        The function's annotations give its signature, which the engine builds
        the configuration function from: ``str``, ``bool``, ``int`` and
        ``float`` parameters and result, and lists and dicts of those. A name
        a builtin or another function already uses is reported when the
        configuration is created.
        """
        function_name = name or getattr(fn, "__name__", None)
        if not function_name:
            raise SchemaError("a function registered without a name must have a __name__")
        if function_name in self._functions:
            raise SchemaError(f"function {function_name} is already registered on this registry")
        self._signatures[function_name] = signature_for(fn)
        self._functions[function_name] = fn

    def register_external_plugin(self, path: str | os.PathLike[str]) -> None:
        """Use the Go-compiled plugin binary at ``path``."""
        self._external_plugins.append(os.fspath(path))

    def register_plugin_directory(self, path: str | os.PathLike[str]) -> None:
        """Use every plugin binary found in the directory at ``path``."""
        self._plugin_directories.append(os.fspath(path))

    @property
    def types(self) -> list[Registration]:
        """The block types registered, in order."""
        return list(self._types)

    @property
    def functions(self) -> dict[str, Callable[..., Any]]:
        """The functions registered, by the name configuration calls them by."""
        return dict(self._functions)

    def _to_proto(self) -> core_pb2.Registry:
        local = core_pb2.LocalRegistry(
            plugin_pattern=self._plugin_pattern or "",
            types=[_declared_type(r) for r in self._types],
            external_plugins=list(self._external_plugins),
            plugin_directories=list(self._plugin_directories),
            functions=[
                core_pb2.DeclaredFunction(name=name, signature=json.dumps(signature).encode())
                for name, signature in self._signatures.items()
            ],
        )
        return core_pb2.Registry(local=local)


class GitHubRegistry:
    """Plugins published as signed GitHub releases, installed on first use.

    ``cache_dir`` is where releases are installed, ``trusted_keys`` the
    armoured public keys a release's signature must verify against,
    ``token`` a GitHub token for private repositories or a higher rate limit,
    and ``api_url`` the API to read releases from, for a GitHub Enterprise
    host or a test server.
    """

    def __init__(
        self,
        *,
        cache_dir: Optional[str | os.PathLike[str]] = None,
        trusted_keys: Iterable[str] = (),
        token: Optional[str] = None,
        api_url: Optional[str] = None,
    ) -> None:
        self._cache_dir = os.fspath(cache_dir) if cache_dir is not None else None
        self._trusted_keys = list(trusted_keys)
        self._token = token
        self._api_url = api_url
        self._plugins: list[tuple[str, str]] = []
        self._types: list[Registration] = []

    def register_plugin(self, repository: str, version: str) -> None:
        """Use the plugin released by ``repository`` (``owner/repo``) at ``version`` (``vX.Y.Z``)."""
        if not repository or not version:
            raise ValueError("a GitHub plugin needs a repository and a version")
        self._plugins.append((repository, version))

    def register_type(self, cls: type, type: str, subtype: Optional[str] = None) -> None:  # noqa: A002 - mirrors the Go name
        """Declare the dataclass ``cls`` as a block type on this registry, as :meth:`LocalRegistry.register_type` does."""
        self._types.append(_registration(cls, type, subtype))

    @property
    def types(self) -> list[Registration]:
        """The block types registered on this registry, in order."""
        return list(self._types)

    @property
    def functions(self) -> dict[str, Callable[..., Any]]:
        """The functions this registry offers; a GitHub registry offers none of its own."""
        return {}

    def _to_proto(self) -> core_pb2.Registry:
        github = core_pb2.GitHubRegistry(
            plugins=[core_pb2.GitHubPlugin(repository=r, version=v) for r, v in self._plugins],
            cache_dir=self._cache_dir or "",
            trusted_keys=list(self._trusted_keys),
            token=self._token or "",
            api_url=self._api_url or "",
            types=[_declared_type(r) for r in self._types],
        )
        return core_pb2.Registry(github=github)


def _registration(cls: type, type_name: str, subtype: Optional[str]) -> Registration:
    name = getattr(cls, "__name__", None) or repr(cls)
    if not is_dataclass_itself(cls):
        raise SchemaError(
            f"{name} must be a dataclass to be registered as a block type; "
            "decorate the class itself with @dataclass, a dataclass base is not enough"
        )
    if not type_name:
        raise SchemaError(f"{name} must be registered with a type name, such as register_type({name}, \"app\")")
    schema = schema_for(cls, type_name=type_name, subtype=subtype)
    return Registration(cls=cls, type=type_name, subtype=subtype or "", schema=schema)


def _declared_type(registration: Registration) -> core_pb2.DeclaredType:
    return core_pb2.DeclaredType(
        type=registration.type,
        subtype=registration.subtype,
        schema=json.dumps(registration.schema).encode(),
    )


__all__ = ["LocalRegistry", "GitHubRegistry"]
