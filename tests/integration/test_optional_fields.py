"""Optional fields left out of configuration, against the real engine.

An optional field the block does not set reads back as its default, ``None``
for a field typed ``T | None``, whether the field is an attribute, an object
attribute or a nested block.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

import xcl

pytestmark = pytest.mark.usefixtures("engine")


@dataclass
class Endpoint:
    location: str


@dataclass
class Service:
    image: str
    region: str | None = None
    database: Endpoint | None = xcl.field(block=False, default=None)
    health: Endpoint | None = None
    meta: xcl.Meta | None = None


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    """Plugins are cached under HOME, so every test gets its own."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def write_config(directory: Path, text: str) -> Path:
    path = directory / "main.xcl"
    path.write_text(textwrap.dedent(text).lstrip())
    return path


def registry() -> xcl.LocalRegistry:
    found = xcl.LocalRegistry()
    found.register_type(Service, "optional_service")
    return found


def test_omitted_optional_fields_read_back_as_none(tmp_path):
    config = write_config(
        tmp_path,
        """
        optional_service "web" {
          image = "nginx"
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(Service, "optional_service.web")

    assert found.region is None
    assert found.database is None
    assert found.health is None


def test_set_optional_fields_read_back(tmp_path):
    config = write_config(
        tmp_path,
        """
        optional_service "web" {
          image    = "nginx"
          region   = "eu"
          database = { location = "db:5432" }

          health {
            location = "/healthz"
          }
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(Service, "optional_service.web")

    assert found.region == "eu"
    assert found.database == Endpoint(location="db:5432")
    assert found.health == Endpoint(location="/healthz")
