"""Diffs: what an apply would do."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from xcl._types import UNKNOWN
from xcl.highlight._kinds import Token


@dataclasses.dataclass(frozen=True)
class Summary:
    """How many entities an apply would create, update, replace, delete and leave unchanged."""

    create: int = 0
    update: int = 0
    replace: int = 0
    delete: int = 0
    unchanged: int = 0


@dataclasses.dataclass(frozen=True)
class Change:
    """One setting an apply would change: its path, the value before and after, or :data:`xcl.UNKNOWN` after."""

    path: str
    before: Any = None
    after: Any = None
    unknown: bool = False
    sensitive: bool = False

    @property
    def after_value(self) -> Any:
        """The value after the apply, or :data:`xcl.UNKNOWN` when it is only known once it has run."""
        return UNKNOWN if self.unknown else self.after


@dataclasses.dataclass(frozen=True)
class Dependency:
    """A dependency whose own change affects an entity."""

    address: str
    action: str = ""


@dataclasses.dataclass(frozen=True)
class ResourceDiff:
    """What an apply would do to one entity."""

    address: str
    action: str
    reason: str = ""
    replaced_dependencies: tuple[str, ...] = ()
    dependencies: tuple[Dependency, ...] = ()
    changes: tuple[Change, ...] = ()


@dataclasses.dataclass(frozen=True)
class Diff:
    """What an apply would do: a summary and the entities it would touch, as ``diff`` returns it.

    ``tokens`` is the git-style change summary Go's ``xcl.PrintDiff`` prints,
    as labelled text (a tuple of :class:`xcl.highlight.Token`), laid out by
    the engine; :func:`xcl.print_diff` prints it in any format. It is empty
    for a ``Diff`` built by hand.
    """

    summary: Summary
    resources: tuple[ResourceDiff, ...]
    raw: dict[str, Any] = dataclasses.field(default_factory=dict, compare=False, repr=False)
    tokens: tuple[Token, ...] = dataclasses.field(default=(), compare=False, repr=False)

    @classmethod
    def _from_json(cls, data: bytes, tokens: tuple[Token, ...] = ()) -> Diff:
        raw = json.loads(data) if data else {}
        summary = raw.get("summary") or {}
        resources = []
        for r in raw.get("resources") or []:
            changes = tuple(
                Change(
                    path=_path_text(c.get("path")),
                    before=c.get("before"),
                    after=c.get("after"),
                    unknown=bool(c.get("unknown", False)),
                    sensitive=bool(c.get("sensitive", False)),
                )
                for c in r.get("changes") or []
            )
            dependencies = tuple(
                Dependency(address=str(d.get("address", "")), action=str(d.get("action", "")))
                for d in r.get("dependencies") or []
            )
            resources.append(
                ResourceDiff(
                    address=str(r.get("address", "")),
                    action=str(r.get("action", "")),
                    reason=str(r.get("reason", "") or ""),
                    replaced_dependencies=tuple(r.get("replaced_dependencies") or []),
                    dependencies=dependencies,
                    changes=changes,
                )
            )
        return cls(
            summary=Summary(**{k: int(summary.get(k, 0)) for k in ("create", "update", "replace", "delete", "unchanged")}),
            resources=tuple(resources),
            raw=raw,
            tokens=tokens,
        )

    def changed(self) -> int:
        """How many entities the apply would create, update, replace or delete."""
        s = self.summary
        return s.create + s.update + s.replace + s.delete

    def resource(self, address: str) -> ResourceDiff | None:
        """The entry for ``address``, or ``None`` when the apply would leave it alone."""
        for r in self.resources:
            if r.address == address:
                return r
        return None


def _path_text(path: Any) -> str:
    if isinstance(path, str):
        return path
    return json.dumps(path) if path is not None else ""


__all__ = ["Diff", "Summary", "ResourceDiff", "Change", "Dependency"]
