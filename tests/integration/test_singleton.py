"""Singletons and label fields against the real engine.

A dataclass with neither a ``meta`` field nor a label field cannot read a
name, so its block is written without labels and addressed by its type
alone; a label field is filled from the block's label.
"""

from __future__ import annotations

import asyncio
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

import xcl
import xcl.aio
from sync_entities import MemoryStore

pytestmark = pytest.mark.usefixtures("engine")


@xcl.entity("single_runner")
@dataclass
class Runner:
    server: str
    listen: str = ""


@xcl.entity("single_agent")
@dataclass
class Agent:
    model: str
    handle: str = xcl.field(label=True, default="")


@xcl.entity("single_database", "postgres")
@dataclass
class Database:
    version: str
    engine: str = xcl.field(label=True, default="")
    handle: str = xcl.field(label=True, default="")


@dataclass
class Endpoint:
    server: str


@xcl.entity("single_client")
@dataclass
class Client(xcl.Resource):
    server: str
    runner: Endpoint = xcl.field(block=False)


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
    found.register_type(Runner)
    found.register_type(Agent)
    found.register_type(Database)
    found.register_type(Client)
    return found


def test_singleton_is_written_without_labels_and_found_by_its_type(tmp_path):
    config = write_config(
        tmp_path,
        """
        single_runner {
          server = "https://maalstrom.app"
          listen = "127.0.0.1:7660"
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(Runner, "single_runner")

    assert isinstance(found, Runner)
    assert found.server == "https://maalstrom.app"
    assert found.listen == "127.0.0.1:7660"


def test_singleton_is_loaded_from_saved_state(tmp_path):
    config = write_config(
        tmp_path,
        """
        single_runner {
          server = "https://maalstrom.app"
        }
        """,
    )
    state = tmp_path / "state"

    with xcl.Config(registries=[registry()], state_path=state) as c:
        c.apply(config)

    with xcl.Config(registries=[registry()], state_path=state) as c:
        c.load()
        found = c.find(Runner, "single_runner")

    assert found.server == "https://maalstrom.app"


def test_singleton_is_encoded_without_labels(tmp_path):
    config = write_config(
        tmp_path,
        """
        single_runner {
          server = "https://maalstrom.app"
        }
        """,
    )
    store = MemoryStore()

    with xcl.Config(registries=[registry()], state_store=store) as c:
        c.apply(config)
        text = c.encode_saved_entity(store.record("single_runner"))

    assert text == 'single_runner {\n  server = "https://maalstrom.app"\n}\n'


def test_singleton_is_found_through_the_asyncio_api(tmp_path):
    config = write_config(
        tmp_path,
        """
        single_runner {
          server = "https://maalstrom.app"
        }
        """,
    )

    async def main() -> Runner:
        async with xcl.aio.Config(registries=[registry()]) as c:
            await c.apply(config)
            return await c.find_one(Runner, "single_runner")

    found = asyncio.run(main())

    assert found.server == "https://maalstrom.app"


def test_singleton_is_referenced_by_its_type(tmp_path):
    config = write_config(
        tmp_path,
        """
        single_runner {
          server = "https://maalstrom.app"
        }

        single_client "web" {
          server = single_runner.server
          runner = single_runner
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(Client, "single_client.web")

    assert found.server == "https://maalstrom.app"
    assert found.runner.server == "https://maalstrom.app"


def test_singleton_with_a_label_is_refused(tmp_path):
    config = write_config(
        tmp_path,
        """
        single_runner "nas" {
          server = "https://maalstrom.app"
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        with pytest.raises(xcl.ConfigError) as raised:
            c.validate(config)

    assert "single_runner takes no labels" in str(raised.value)


def test_label_field_is_filled_from_the_label(tmp_path):
    config = write_config(
        tmp_path,
        """
        single_agent "claude" {
          model = "claude/opus"
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(Agent, "single_agent.claude")

    assert found.handle == "claude"
    assert found.model == "claude/opus"


def test_two_label_fields_are_filled_with_the_subtype_and_the_label(tmp_path):
    config = write_config(
        tmp_path,
        """
        single_database "postgres" "main" {
          version = "15"
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(Database, "single_database.postgres.main")

    assert found.engine == "postgres"
    assert found.handle == "main"
