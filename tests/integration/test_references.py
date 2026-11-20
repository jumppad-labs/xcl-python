"""References to whole entities against the real engine.

A ``block=False`` dataclass with a ``meta`` field or a label field is an
entity value: a reference such as ``database = database.postgres.main``
gives it the referenced block's labels, attributes and metadata. The
website's references page (PostgreSQL and App) is the example.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

import xcl

pytestmark = pytest.mark.usefixtures("engine")


@dataclass
class PostgreSQL:
    location: str
    port: int = 5432
    meta: xcl.Meta | None = None


@dataclass
class App:
    image: str
    database: PostgreSQL = xcl.field(block=False)
    databases: list[PostgreSQL] = xcl.field(block=False, default_factory=list)
    name: str = xcl.field(label=True, default="")


@dataclass
class NamedDatabase:
    location: str
    kind: str = xcl.field(label=True, default="")
    handle: str = xcl.field(label=True, default="")


@dataclass
class Reporter:
    database: NamedDatabase = xcl.field(block=False)
    name: str = xcl.field(label=True, default="")


@dataclass
class Cache:
    size: int
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
    found.register_type(PostgreSQL, "database", "postgres")
    found.register_type(App, "app")
    found.register_type(Reporter, "reporter")
    found.register_type(Cache, "cache")
    return found


WEBSITE = """
    database "postgres" "main" {
      location = "db.internal"
      port     = 5432
    }

    database "postgres" "replica" {
      location = "db-replica.internal"
    }

    app "web" {
      image     = "nginx:1.27"
      database  = database.postgres.main
      databases = [database.postgres.main, database.postgres.replica]
    }
    """


def test_reference_gives_the_referenced_entity_with_its_meta(tmp_path):
    config = write_config(tmp_path, WEBSITE)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        web = c.find(App, "app.web")

    assert isinstance(web.database, PostgreSQL)
    assert web.database.location == "db.internal"
    assert web.database.port == 5432
    assert isinstance(web.database.meta, xcl.Meta)
    assert web.database.meta.id == "database.postgres.main"
    assert web.database.meta.name == "main"
    assert web.database.meta.type == "database"
    assert web.database.meta.subtype == "postgres"


def test_list_of_references_gives_each_entity_in_order(tmp_path):
    config = write_config(tmp_path, WEBSITE)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        web = c.find(App, "app.web")

    assert [d.meta.id for d in web.databases] == ["database.postgres.main", "database.postgres.replica"]
    assert [d.location for d in web.databases] == ["db.internal", "db-replica.internal"]
    assert [d.port for d in web.databases] == [5432, 5432]


def test_reference_fills_label_fields_from_the_referenced_block(tmp_path):
    config = write_config(
        tmp_path,
        WEBSITE
        + """
    reporter "nightly" {
      database = database.postgres.replica
    }
    """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        nightly = c.find(Reporter, "reporter.nightly")

    assert nightly.database == NamedDatabase(location="db-replica.internal", kind="postgres", handle="replica")


def test_reference_comes_back_after_a_load_from_saved_state(tmp_path):
    config = write_config(tmp_path, WEBSITE)
    state = tmp_path / "state"

    with xcl.Config(registries=[registry()], state_path=state) as c:
        c.apply(config)

    with xcl.Config(registries=[registry()], state_path=state) as c:
        c.load()
        web = c.find(App, "app.web")

    assert web.database.meta.id == "database.postgres.main"
    assert web.database.location == "db.internal"
    assert [d.meta.name for d in web.databases] == ["main", "replica"]


def test_looked_up_entity_holding_references_encodes_as_it_was_written(tmp_path):
    config = write_config(tmp_path, WEBSITE)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        web = c.find(App, "app.web")
        text = c.encode_entity(web, show_references=True)

    assert text == (
        'app "web" {\n'
        '  image     = "nginx:1.27"\n'
        "  database  = database.postgres.main\n"
        "  databases = [database.postgres.main, database.postgres.replica]\n"
        "}\n"
    )


def test_reference_to_a_block_that_does_not_fit_fails_at_apply(tmp_path):
    config = write_config(
        tmp_path,
        """
        cache "hot" {
          size = 64
        }

        app "web" {
          image    = "nginx:1.27"
          database = cache.hot
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.validate(config)
        with pytest.raises(xcl.ConfigError) as raised:
            c.apply(config)

    problems = raised.value.problems
    assert len(problems) == 1
    assert problems[0].line == 7
    assert problems[0].detail == 'Attribute "database": Unsuitable value: attribute "location" is required'
