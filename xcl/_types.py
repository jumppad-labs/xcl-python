"""Value types used in entity classes: ``Sensitive``, ``Computed``, ``field`` and ``UNKNOWN``."""

from __future__ import annotations

import dataclasses
from typing import Annotated, Any, Generic, Optional, TypeVar

T = TypeVar("T")

SENSITIVE_MARKER = "(sensitive)"


class Sensitive(Generic[T]):
    """A secret value, printed as ``(sensitive)`` and read only through :meth:`reveal`.

    A field annotated ``xcl.Sensitive[str]`` is a sensitive attribute: the
    engine masks it in events and state, and lookups return it as the marker
    rather than the value, so a ``Sensitive`` read back from a lookup holds
    no value and :meth:`reveal` returns ``None``. Construct one with the value
    to hold it; compare two with ``==``.
    """

    __slots__ = ("_value", "_redacted")

    def __init__(self, value: Optional[T] = None, *, redacted: bool = False) -> None:
        self._value = value
        self._redacted = redacted or value is None

    @classmethod
    def redacted(cls) -> Sensitive[T]:
        """A sensitive value whose real value was masked before it reached Python."""
        return cls(None, redacted=True)

    def reveal(self) -> Optional[T]:
        """The real value, or ``None`` when it was masked before it reached Python."""
        return None if self._redacted else self._value

    @property
    def is_redacted(self) -> bool:
        """Whether the value was masked before it reached Python."""
        return self._redacted

    def __repr__(self) -> str:
        return SENSITIVE_MARKER

    def __str__(self) -> str:
        return SENSITIVE_MARKER

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sensitive):
            return NotImplemented
        return self._redacted == other._redacted and self._value == other._value

    def __hash__(self) -> int:
        return hash((self._redacted, self._value if not isinstance(self._value, (list, dict)) else repr(self._value)))


class _ComputedMarker:
    """Marks an annotation as computed: owned by the provider, never set in configuration."""

    def __repr__(self) -> str:
        return "xcl.Computed"


COMPUTED = _ComputedMarker()


class Computed:
    """``xcl.Computed[T]``: a field the provider sets, which configuration may not.

    It annotates an optional ``T``; the engine refuses configuration that sets
    the field and fills it in from what the provider returns.
    """

    def __class_getitem__(cls, item: Any) -> Any:
        return Annotated[Optional[item], COMPUTED]


class _Unknown:
    """The value of a setting only known once the apply has run."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "xcl.UNKNOWN"

    def __bool__(self) -> bool:
        return False


UNKNOWN = _Unknown()


@dataclasses.dataclass(frozen=True)
class FieldOptions:
    """What :func:`field` records about a field, beside the dataclass field itself."""

    name: Optional[str] = None
    block: Optional[bool] = None
    label: bool = False


METADATA_KEY = "xcl"


def field(
    *,
    name: Optional[str] = None,
    block: Optional[bool] = None,
    label: bool = False,
    default: Any = dataclasses.MISSING,
    default_factory: Any = dataclasses.MISSING,
) -> Any:
    """A dataclass field with configuration options.

    ``name`` is the name configuration uses when it differs from the
    attribute's; ``block=True`` makes a dataclass-typed field a nested block
    (the default for a dataclass) and ``block=False`` an attribute holding an
    object value; ``label=True`` marks the string field of a block's element
    that holds the block's name, which a map of blocks fills from the key and
    a list of blocks fills when the block is written with a name. ``default``
    and ``default_factory`` are the dataclass's.
    """
    options = FieldOptions(name=name, block=block, label=label)
    if default is not dataclasses.MISSING:
        return dataclasses.field(default=default, metadata={METADATA_KEY: options})
    if default_factory is not dataclasses.MISSING:
        return dataclasses.field(default_factory=default_factory, metadata={METADATA_KEY: options})
    return dataclasses.field(metadata={METADATA_KEY: options})


def options_of(f: dataclasses.Field[Any]) -> FieldOptions:
    """The :class:`FieldOptions` recorded on a dataclass field, or the defaults."""
    found = f.metadata.get(METADATA_KEY) if f.metadata else None
    return found if isinstance(found, FieldOptions) else FieldOptions()
