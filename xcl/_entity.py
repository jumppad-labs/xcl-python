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
        """What the engine recorded about the entity: its address and where it was declared."""
        return self._meta

    @property
    def address(self) -> str:
        """The entity's address, such as ``docker.network.main``."""
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
