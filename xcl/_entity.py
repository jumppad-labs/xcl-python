"""Entity classes: ``Meta``, a block's metadata, and the generic ``Entity``.

A block type is a plain dataclass registered by name with
:meth:`xcl.LocalRegistry.register_type`; it may declare a ``meta: Meta |
None`` field to receive the block's metadata.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping
from typing import Any


@dataclasses.dataclass
class Meta:
    """What the engine records about every entity: its address and where it was declared.

    ``id`` is the entity's address, such as ``module.db.app.web``.
    ``disabled`` and ``depends_on`` are what configuration set on the block,
    which every block takes, so a class never declares them itself.
    """

    id: str = ""
    name: str = ""
    type: str = ""
    subtype: str = ""
    module: str = ""
    file: str = ""
    line: int = 0
    column: int = 0
    disabled: bool = False
    depends_on: list[str] = dataclasses.field(default_factory=list)
    status: str = ""
    links: list[str] = dataclasses.field(default_factory=list)
    references: dict[str, str] = dataclasses.field(default_factory=dict)
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_entity(cls, data: Mapping[str, Any]) -> Meta:
        """A ``Meta`` from an entity's JSON: its ``meta`` object, unknown keys kept in ``extra``, and its ``disabled`` and ``depends_on``."""
        raw = data.get("meta")
        known = set(_record_keys())
        values: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for key, value in (raw.items() if isinstance(raw, Mapping) else ()):
            if key in known:
                values[key] = value
            else:
                extra[key] = value
        meta = cls(**values)
        meta.extra = extra
        meta.disabled = bool(data.get("disabled") or False)
        meta.depends_on = list(data.get("depends_on") or [])
        return meta

    def to_record(self) -> dict[str, Any]:
        """The entity JSON's ``meta`` object, the mirror of :meth:`from_entity`.

        Keys left at their empty value are omitted, as the engine reads a
        missing key as empty, and ``extra`` is merged back in. ``disabled``
        and ``depends_on`` are not part of it: they sit beside ``meta`` in
        the entity's JSON.
        """
        record: dict[str, Any] = {}
        for key in _record_keys():
            value = getattr(self, key)
            if value:
                record[key] = value
        record.update(self.extra)
        return record


def _record_keys() -> list[str]:
    """The keys of ``Meta`` the entity JSON's ``meta`` object holds, in order: every field but ``extra``, ``disabled`` and ``depends_on``."""
    return [f.name for f in dataclasses.fields(Meta) if f.name not in ("extra", "disabled", "depends_on")]


class Entity(Mapping[str, Any]):
    """An entity of a type no class was registered for, such as a Go plugin's.

    It is a read-only mapping of the entity's JSON: attributes are read by
    name, ``entity["image"]`` or ``entity.image``, and ``meta`` is its
    :class:`Meta`, ``meta.id`` its address.
    """

    __slots__ = ("_data", "_meta")

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = dict(data)
        self._meta = Meta.from_entity(self._data)

    @property
    def meta(self) -> Meta:
        """What the engine recorded about the entity: its address and where it was declared."""
        return self._meta

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
