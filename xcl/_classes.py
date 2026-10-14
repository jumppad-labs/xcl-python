"""The classes a configuration hydrates entities into, by block type."""

from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Optional

from xcl._errors import NotRegisteredError
from xcl._schema import SchemaError

if TYPE_CHECKING:
    from xcl.registry import Registration


class ClassMap:
    """The block types a configuration's registries declare, by class and by type and subtype.

    A configuration builds one from its registries when it is created and
    never changes it, so it answers exactly as the engine was told; every
    lookup and event of that configuration hydrates through it. A class may
    be registered as one block type per configuration.
    """

    __slots__ = ("_by_names", "_by_class")

    def __init__(self, registrations: Iterable[Registration] = ()) -> None:
        by_names: dict[tuple[str, str], type] = {}
        by_class: dict[type, tuple[str, str]] = {}
        for registration in registrations:
            names = (registration.type, registration.subtype or "")
            if registration.cls in by_class:
                raise SchemaError(
                    f"{registration.cls.__name__} is registered as both {_dotted(by_class[registration.cls])} and "
                    f"{_dotted(names)} in one configuration; a class may be one block type per configuration"
                )
            by_class[registration.cls] = names
            by_names[names] = registration.cls
        self._by_names = MappingProxyType(by_names)
        self._by_class = MappingProxyType(by_class)

    @classmethod
    def from_registries(cls, registries: Iterable[Any]) -> ClassMap:
        """The block types every registry in ``registries`` declares, in order."""
        return cls(registration for registry in registries for registration in getattr(registry, "types", ()))

    def class_for(self, type: str, subtype: Optional[str] = "") -> Optional[type]:  # noqa: A002 - mirrors the Go name
        """The class registered for ``type`` and ``subtype``, or ``None`` when there is none."""
        return self._by_names.get((type, subtype or ""))

    def names_of(self, cls: Optional[type]) -> tuple[str, str]:
        """The type and subtype ``cls`` is registered as; raises :class:`xcl.NotRegisteredError` when it is not."""
        if cls is not None:
            names = self._by_class.get(cls)
            if names is not None:
                return names
        name = getattr(cls, "__name__", None) or repr(cls)
        raise NotRegisteredError(
            f"{name} is not registered on this configuration; register it with register_type({name}, type) on one of its registries",
            details={"class": name},
        )


def _dotted(names: tuple[str, str]) -> str:
    return ".".join(filter(None, names))
