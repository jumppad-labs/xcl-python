"""Entity classes: ``Resource``, ``Meta``, the ``entity`` decorator and the generic ``Entity``."""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Iterator, Mapping
from typing import Any, Callable, Optional, TypeVar

from xcl._schema import SchemaError, is_dataclass_itself, schema_for

C = TypeVar("C", bound=type)


@dataclasses.dataclass
class Meta:
    """What the engine records about every entity: its address and where it was declared."""

    id: str = ""
    name: str = ""
    type: str = ""
    subtype: str = ""
    module: str = ""
    file: str = ""
    line: int = 0
    column: int = 0
    status: str = ""
    links: list[str] = dataclasses.field(default_factory=list)
    references: dict[str, str] = dataclasses.field(default_factory=dict)
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Meta:
        """A ``Meta`` from the entity JSON's ``meta`` object; unknown keys are kept in ``extra``."""
        known = {f.name for f in dataclasses.fields(cls)} - {"extra"}
        values: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for key, value in data.items():
            if key in known:
                values[key] = value
            else:
                extra[key] = value
        meta = cls(**values)
        meta.extra = extra
        return meta

    @property
    def address(self) -> str:
        """The entity's address, its ``id``."""
        return self.id


@dataclasses.dataclass(kw_only=True)
class Resource:
    """The base of every entity class: the fields every block type has.

    Subclass it with ``@dataclass`` and register the class with
    :func:`entity`. ``meta`` is filled in by the engine, ``depends_on`` and
    ``disabled`` may be set in configuration.
    """

    meta: Optional[Meta] = None
    depends_on: list[str] = dataclasses.field(default_factory=list)
    disabled: bool = False

    @property
    def address(self) -> str:
        """The entity's address, or an empty string before it is applied."""
        return self.meta.id if self.meta else ""


_registry_lock = threading.Lock()
_registry: dict[tuple[str, str], type] = {}


def entity(type: str, subtype: Optional[str] = None) -> Callable[[C], C]:  # noqa: A002 - mirrors the Go name
    """Register a dataclass as the entity type ``type``, with an optional ``subtype``.

    The type and subtype become the block's labels and address, as in Go: a
    class registered as ``("app",)`` is written ``app "web" {}`` and found at
    ``app.web``; one registered as ``("database", "postgres")`` is written
    ``database "postgres" "main" {}`` and found at ``database.postgres.main``.
    The class's annotations are checked at registration and its schema
    derived; an annotation with no configuration form raises
    :class:`SchemaError` naming the field.
    """
    if not type:
        raise SchemaError("an entity type must be named")

    def register(cls: C) -> C:
        if not is_dataclass_itself(cls):
            raise SchemaError(
                f"{cls.__name__} must be a dataclass to be registered as an entity type; "
                "decorate the class itself with @dataclass, a dataclass base is not enough"
            )
        cls.__xcl_type__ = type  # type: ignore[attr-defined]
        cls.__xcl_subtype__ = subtype or ""  # type: ignore[attr-defined]
        cls.__xcl_schema__ = schema_for(cls, type_name=type, subtype=subtype)  # type: ignore[attr-defined]
        with _registry_lock:
            _registry[(type, subtype or "")] = cls
        return cls

    return register


def registration_of(cls: type) -> tuple[str, str]:
    """The type and subtype ``cls`` was registered with; raises :class:`SchemaError` when it was not."""
    t = getattr(cls, "__xcl_type__", None)
    if not t:
        raise SchemaError(f"{cls.__name__} is not registered as an entity type; decorate it with @xcl.entity(type, subtype)")
    return t, getattr(cls, "__xcl_subtype__", "") or ""


def schema_of(cls: type) -> dict[str, Any]:
    """The schema v1 document derived for a registered class."""
    doc = getattr(cls, "__xcl_schema__", None)
    if doc is None:
        return schema_for(cls)
    return doc


def registered_class(type: str, subtype: str = "", *, registry: Optional[dict[tuple[str, str], type]] = None) -> Optional[type]:  # noqa: A002
    """The class registered for a type and subtype, or ``None``."""
    source = registry if registry is not None else _registry
    return source.get((type, subtype or ""))


def registered_classes() -> dict[tuple[str, str], type]:
    """Every registered class, by type and subtype."""
    with _registry_lock:
        return dict(_registry)


class Entity(Mapping[str, Any]):
    """An entity of a type no class was registered for, such as a Go plugin's.

    It is a read-only mapping of the entity's JSON: attributes are read by
    name, ``entity["image"]`` or ``entity.image``, ``meta`` is its
    :class:`Meta` and ``address`` its address.
    """

    __slots__ = ("_data", "_meta")

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = dict(data)
        raw = self._data.get("meta")
        self._meta = Meta.from_json(raw) if isinstance(raw, Mapping) else Meta()

    @property
    def meta(self) -> Meta:
        return self._meta

    @property
    def address(self) -> str:
        return self._meta.id

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"entity {self._meta.id or '<unknown>'} has no attribute {name!r}") from None

    def __repr__(self) -> str:
        return f"Entity({self._meta.id!r}, {self._data!r})"

    def to_dict(self) -> dict[str, Any]:
        """The entity's JSON as a plain dict."""
        return dict(self._data)
