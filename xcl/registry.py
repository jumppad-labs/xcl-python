"""Registries: where a configuration's types, functions and plugins come from.

A registry is described to the engine when the configuration is created, so
these classes are plain builders: register what the configuration may use,
then pass the registry to :class:`xcl.Config`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from typing import Any, Optional

from xcl._core import core_pb2
from xcl._entity import registration_of, schema_of
from xcl._schema import SchemaError, signature_for


class LocalRegistry:
    """Types, functions and plugins the program itself provides.

    ``plugin_pattern`` names the files a plugin directory is searched for,
    such as ``xcl-plugin-*``; left out, the engine's default applies.
    """

    def __init__(self, *, plugin_pattern: Optional[str] = None) -> None:
        self._plugin_pattern = plugin_pattern
        self._types: list[type] = []
        self._functions: dict[str, Callable[..., Any]] = {}
        self._signatures: dict[str, dict[str, Any]] = {}
        self._external_plugins: list[str] = []
        self._plugin_directories: list[str] = []

    def register_type(self, cls: type) -> None:
        """Declare an entity class registered with :func:`xcl.entity` as a config-only type."""
        registration_of(cls)
        self._types.append(cls)

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
    def types(self) -> list[type]:
        """The classes registered, in order."""
        return list(self._types)

    @property
    def functions(self) -> dict[str, Callable[..., Any]]:
        """The functions registered, by the name configuration calls them by."""
        return dict(self._functions)

    def _to_proto(self) -> core_pb2.Registry:
        local = core_pb2.LocalRegistry(
            plugin_pattern=self._plugin_pattern or "",
            types=[_declared_type(cls) for cls in self._types],
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
        self._types: list[type] = []

    def register_plugin(self, repository: str, version: str) -> None:
        """Use the plugin released by ``repository`` (``owner/repo``) at ``version`` (``vX.Y.Z``)."""
        if not repository or not version:
            raise ValueError("a GitHub plugin needs a repository and a version")
        self._plugins.append((repository, version))

    def register_type(self, cls: type) -> None:
        """Declare an entity class on this registry, as :meth:`LocalRegistry.register_type` does."""
        registration_of(cls)
        self._types.append(cls)

    @property
    def types(self) -> list[type]:
        """The classes registered on this registry, in order."""
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
            types=[_declared_type(cls) for cls in self._types],
        )
        return core_pb2.Registry(github=github)


def _declared_type(cls: type) -> core_pb2.DeclaredType:
    type_name, subtype = registration_of(cls)
    return core_pb2.DeclaredType(type=type_name, subtype=subtype, schema=json.dumps(schema_of(cls)).encode())


__all__ = ["LocalRegistry", "GitHubRegistry"]
