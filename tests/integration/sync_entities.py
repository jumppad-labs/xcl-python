"""The entity classes and state store the synchronous integration tests use.

They live in a module of their own, rather than in the test module, so a
test that loads state in a second interpreter registers exactly the same
classes the first one saved with.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import xcl


@dataclass
class Health:
    """A nested block: ``health { path = ..., interval = ... }``."""

    path: str
    interval: int = 10


@dataclass
class Volume:
    """A repeated block written with a name: ``volume "data" { ... }``."""

    name: str = xcl.field(label=True, default="")
    source: str = ""
    target: str = ""


@dataclass
class Listener:
    """A map of named blocks: ``listener "http" { port = 80 }``."""

    name: str = xcl.field(label=True, default="")
    port: int = 0


@dataclass
class SyncApp:
    """Every annotation form the schema supports, on one config-only type."""

    image: str
    replicas: int = 2
    password: xcl.Sensitive[str] | None = None
    endpoint: xcl.Computed[str] = None
    health: Health | None = None
    volume: list[Volume] = field(default_factory=list)
    listener: dict[str, Listener] = field(default_factory=dict)
    region: str | None = None
    meta: xcl.Meta | None = None
    disabled: bool = False
    depends_on: list[str] = field(default_factory=list)


@dataclass
class SyncDatabase:
    """A type with a subtype: ``sync_database "postgres" "main" {}``."""

    version: str = "16"
    meta: xcl.Meta | None = None


@dataclass
class PlainApp:
    """The plainest block type: no base, no decorator, no meta, disabled or depends_on."""

    image: str
    replicas: int = 1


def registry() -> xcl.LocalRegistry:
    """A registry declaring both classes."""
    found = xcl.LocalRegistry()
    found.register_type(SyncApp, "sync_app")
    found.register_type(SyncDatabase, "sync_database", "postgres")
    return found


class JsonLinesStore:
    """A state store that keeps the engine's records as JSON lines in one file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[bytes]:
        if not self.path.exists():
            return []
        return [line.encode() for line in self.path.read_text().splitlines() if line.strip()]

    def save(self, entities: list[bytes]) -> None:
        self.path.write_text("".join(e.decode() + "\n" for e in entities))

    def exists(self) -> bool:
        return self.path.exists()

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def records(self) -> list[dict]:
        """The saved records decoded, for assertions."""
        return [json.loads(line) for line in self.load()]


class MemoryStore:
    """A state store that keeps the engine's records in memory."""

    def __init__(self) -> None:
        self.saved: list[bytes] = []

    def load(self) -> list[bytes]:
        return list(self.saved)

    def save(self, entities: list[bytes]) -> None:
        self.saved = list(entities)

    def exists(self) -> bool:
        return bool(self.saved)

    def clear(self) -> None:
        self.saved = []

    def record(self, address: str) -> bytes:
        """The saved record of the entity at ``address``."""
        for raw in self.saved:
            if json.loads(raw).get("meta", {}).get("id") == address:
                return raw
        raise KeyError(address)
