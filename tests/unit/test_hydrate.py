"""Turning an entity's JSON back into the registered class, or a generic Entity."""

from dataclasses import dataclass
from typing import Any

import pytest

from xcl import Computed, Entity, Resource, Sensitive, entity, field
from xcl._schema import hydrate


@dataclass
class Health:
    path: str


@dataclass
class Volume:
    source: str
    name: str = field(label=True, default="")


@dataclass
class Listener:
    port: int
    name: str = field(label=True, default="")


@entity("hydrate_app")
@dataclass
class App(Resource):
    image: str
    replicas: int = 2
    region: str = "eu"
    password: Sensitive[str] | None = None
    endpoint: Computed[str] = None
    health: Health | None = None
    volume: list[Volume] = field(default_factory=list)
    listener: dict[str, Listener] = field(default_factory=dict)


@entity("hydrate_database", "postgres")
@dataclass
class Database(Resource):
    version: str


def app_json() -> dict[str, Any]:
    return {
        "meta": {"id": "hydrate_app.web", "name": "web", "type": "hydrate_app", "file": "/f", "line": 2, "column": 1},
        "image": "nginx",
        "replicas": 2,
        "region": "eu",
        "password": "(sensitive)",
        "health": {"path": "/healthz"},
        "volume": [{"name": "data", "source": "/data"}, {"source": "/logs"}],
        "listener": {"http": {"name": "http", "port": 80}, "https": {"name": "https", "port": 443}},
    }


def test_hydrate_registered_class():
    app = hydrate(app_json())

    assert isinstance(app, App)
    assert app.address == "hydrate_app.web"
    assert app.meta.line == 2
    assert app.meta.column == 1
    assert app.meta.file == "/f"
    assert app.image == "nginx"
    assert app.replicas == 2
    assert app.region == "eu"


def test_hydrate_nested_block():
    app = hydrate(app_json())

    assert app.health == Health("/healthz")


def test_hydrate_repeated_block_in_order():
    app = hydrate(app_json())

    assert app.volume == [Volume("/data", "data"), Volume("/logs", "")]


def test_hydrate_named_block_map_to_dict():
    app = hydrate(app_json())

    assert set(app.listener) == {"http", "https"}
    assert app.listener["https"] == Listener(443, "https")
    assert app.listener["https"].port == 443


def test_hydrate_sensitive_marker_is_redacted():
    app = hydrate(app_json())

    assert isinstance(app.password, Sensitive)
    assert app.password.is_redacted
    assert app.password.reveal() is None
    assert str(app.password) == "(sensitive)"


def test_hydrate_masked_envelope_is_redacted():
    data = app_json()
    data["password"] = {"xcl_masked": "redact", "value": "(sensitive)"}

    app = hydrate(data)

    assert app.password == Sensitive.redacted()
    assert app.password.reveal() is None


def test_hydrate_real_sensitive_value_reveals():
    data = app_json()
    data["password"] = "s3cret"

    app = hydrate(data)

    assert app.password == Sensitive("s3cret")
    assert app.password.reveal() == "s3cret"
    assert not app.password.is_redacted
    assert repr(app.password) == "(sensitive)"


def test_hydrate_computed_absent_is_none():
    app = hydrate(app_json())

    assert app.endpoint is None


def test_hydrate_computed_present_is_value():
    data = app_json()
    data["endpoint"] = "https://web.example"

    app = hydrate(data)

    assert app.endpoint == "https://web.example"


def test_unregistered_type_becomes_entity():
    data = {
        "meta": {"id": "hydrate_unregistered.main", "name": "main", "type": "hydrate_unregistered", "subtype": "plugin"},
        "log": "/var/log",
    }

    found = hydrate(data)

    assert isinstance(found, Entity)
    assert found.address == "hydrate_unregistered.main"
    assert found.meta.subtype == "plugin"


def test_entity_attribute_access_and_mapping():
    data = {
        "meta": {"id": "hydrate_unregistered.main", "name": "main", "type": "hydrate_unregistered"},
        "log": "/var/log",
    }

    found = hydrate(data)

    assert found["log"] == "/var/log"
    assert found.log == "/var/log"
    assert dict(found) == data
    assert len(found) == 2
    assert found.to_dict() == data


def test_entity_missing_attribute_raises():
    found = hydrate({"meta": {"id": "hydrate_unregistered.main", "type": "hydrate_unregistered"}})

    with pytest.raises(AttributeError, match="nope"):
        found.nope


def test_hydrate_with_explicit_class():
    data = app_json()
    data["meta"]["type"] = "hydrate_not_registered"

    app = hydrate(data, App)

    assert isinstance(app, App)
    assert app.image == "nginx"
    assert app.meta.type == "hydrate_not_registered"


def test_hydrate_subtype_class_by_meta():
    data = {
        "meta": {
            "id": "hydrate_database.postgres.main",
            "name": "main",
            "type": "hydrate_database",
            "subtype": "postgres",
        },
        "version": "16",
    }

    database = hydrate(data)

    assert isinstance(database, Database)
    assert database.address == "hydrate_database.postgres.main"
    assert database.meta.type == "hydrate_database"
    assert database.meta.subtype == "postgres"
    assert database.version == "16"


def test_hydrate_non_dict_is_returned_as_is():
    assert hydrate("plain") == "plain"
