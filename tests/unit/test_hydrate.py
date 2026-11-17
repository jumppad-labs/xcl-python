"""Turning an entity's JSON back into the registered class, or a generic Entity."""

from dataclasses import dataclass
from typing import Any

import pytest

from xcl import Computed, Entity, Meta, Sensitive, field
from xcl._classes import ClassMap
from xcl._schema import hydrate
from xcl.registry import LocalRegistry


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


@dataclass
class App:
    image: str
    replicas: int = 2
    region: str = "eu"
    password: Sensitive[str] | None = None
    endpoint: Computed[str] = None
    health: Health | None = None
    volume: list[Volume] = field(default_factory=list)
    listener: dict[str, Listener] = field(default_factory=dict)
    meta: Meta | None = None


@dataclass
class Database:
    version: str
    meta: Meta | None = None


@dataclass
class Note:
    text: str


@dataclass
class Owner:
    meta: str
    name: str = ""


@dataclass
class Team:
    owner: Owner | None = None
    meta: Meta | None = None


def classes() -> ClassMap:
    registry = LocalRegistry()
    registry.register_type(App, "hydrate_app")
    registry.register_type(Database, "hydrate_database", "postgres")
    registry.register_type(Note, "hydrate_note")
    registry.register_type(Team, "hydrate_team")
    return ClassMap(registry.types)


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
    app = hydrate(app_json(), registry=classes())

    assert isinstance(app, App)
    assert app.meta.id == "hydrate_app.web"
    assert app.meta.line == 2
    assert app.meta.column == 1
    assert app.meta.file == "/f"
    assert app.image == "nginx"
    assert app.replicas == 2
    assert app.region == "eu"


def test_hydrate_nested_block():
    app = hydrate(app_json(), registry=classes())

    assert app.health == Health("/healthz")


def test_hydrate_repeated_block_in_order():
    app = hydrate(app_json(), registry=classes())

    assert app.volume == [Volume("/data", "data"), Volume("/logs", "")]


def test_hydrate_named_block_map_to_dict():
    app = hydrate(app_json(), registry=classes())

    assert set(app.listener) == {"http", "https"}
    assert app.listener["https"] == Listener(443, "https")
    assert app.listener["https"].port == 443


def test_hydrate_sensitive_marker_is_redacted():
    app = hydrate(app_json(), registry=classes())

    assert isinstance(app.password, Sensitive)
    assert app.password.is_redacted
    assert app.password.reveal() is None
    assert str(app.password) == "(sensitive)"


def test_hydrate_masked_envelope_is_redacted():
    data = app_json()
    data["password"] = {"xcl_masked": "redact", "value": "(sensitive)"}

    app = hydrate(data, registry=classes())

    assert app.password == Sensitive.redacted()
    assert app.password.reveal() is None


def test_hydrate_real_sensitive_value_reveals():
    data = app_json()
    data["password"] = "s3cret"

    app = hydrate(data, registry=classes())

    assert app.password == Sensitive("s3cret")
    assert app.password.reveal() == "s3cret"
    assert not app.password.is_redacted
    assert repr(app.password) == "(sensitive)"


def test_hydrate_computed_absent_is_none():
    app = hydrate(app_json(), registry=classes())

    assert app.endpoint is None


def test_hydrate_computed_present_is_value():
    data = app_json()
    data["endpoint"] = "https://web.example"

    app = hydrate(data, registry=classes())

    assert app.endpoint == "https://web.example"


def test_type_with_no_registered_class_becomes_entity():
    data = {
        "meta": {"id": "hydrate_unregistered.main", "name": "main", "type": "hydrate_unregistered", "subtype": "plugin"},
        "log": "/var/log",
    }

    found = hydrate(data, registry=classes())

    assert isinstance(found, Entity)
    assert found.meta.id == "hydrate_unregistered.main"
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

    database = hydrate(data, registry=classes())

    assert isinstance(database, Database)
    assert database.meta.id == "hydrate_database.postgres.main"
    assert database.meta.type == "hydrate_database"
    assert database.meta.subtype == "postgres"
    assert database.version == "16"


def test_hydrate_non_dict_is_returned_as_is():
    assert hydrate("plain") == "plain"


def test_untyped_hydrate_without_registry_becomes_entity():
    found = hydrate(app_json())

    assert isinstance(found, Entity)
    assert found.meta.id == "hydrate_app.web"
    assert found.image == "nginx"


def test_class_without_meta_field_gets_no_meta():
    data = {"meta": {"id": "hydrate_note.todo", "name": "todo", "type": "hydrate_note"}, "text": "buy milk"}

    note = hydrate(data, registry=classes())

    assert note == Note("buy milk")
    assert not hasattr(note, "meta")


def test_top_level_meta_field_is_filled_as_meta():
    data = {
        "meta": {"id": "hydrate_team.core", "name": "core", "type": "hydrate_team"},
        "owner": {"meta": "lead", "name": "ada"},
    }

    team = hydrate(data, registry=classes())

    assert isinstance(team.meta, Meta)
    assert team.meta.id == "hydrate_team.core"


def test_nested_block_meta_field_stays_an_ordinary_value():
    data = {
        "meta": {"id": "hydrate_team.core", "name": "core", "type": "hydrate_team"},
        "owner": {"meta": "lead", "name": "ada"},
    }

    team = hydrate(data, registry=classes())

    assert team.owner == Owner(meta="lead", name="ada")
    assert team.owner.meta == "lead"


# entity values: references held by block=False fields


@dataclass
class PostgresRef:
    location: str
    port: int = 5432
    meta: Meta | None = None


@dataclass
class LabelledRef:
    location: str
    name: str = field(label=True, default="")


@dataclass
class SubtypedRef:
    location: str
    kind: str = field(label=True, default="")
    name: str = field(label=True, default="")


@dataclass
class Endpoint:
    port: int
    meta_note: str = ""


@dataclass
class Service:
    database: PostgresRef | None = field(block=False, default=None)
    databases: list[PostgresRef] = field(block=False, default_factory=list)
    by_name: dict[str, PostgresRef] = field(block=False, default_factory=dict)
    labelled: LabelledRef | None = field(block=False, default=None)
    subtyped: SubtypedRef | None = field(block=False, default=None)
    endpoint: Endpoint | None = field(block=False, default=None)
    meta: Meta | None = None


def service_classes() -> ClassMap:
    registry = LocalRegistry()
    registry.register_type(Service, "hydrate_service")
    return ClassMap(registry.types)


def postgres_json(name: str, location: str) -> dict[str, Any]:
    return {
        "meta": {
            "id": f"database.postgres.{name}",
            "name": name,
            "type": "database",
            "subtype": "postgres",
            "file": "/main.xcl",
            "line": 1,
            "column": 1,
        },
        "location": location,
        "port": 5432,
    }


def service_json(**fields: Any) -> dict[str, Any]:
    return {"meta": {"id": "hydrate_service.web", "name": "web", "type": "hydrate_service"}, **fields}


def test_hydrate_entity_value_fills_its_meta():
    service = hydrate(service_json(database=postgres_json("main", "eu-west-1")), registry=service_classes())

    assert isinstance(service.database, PostgresRef)
    assert isinstance(service.database.meta, Meta)
    assert service.database.meta.id == "database.postgres.main"
    assert service.database.meta.name == "main"
    assert service.database.meta.subtype == "postgres"
    assert service.database.location == "eu-west-1"


def test_hydrate_entity_value_meta_takes_disabled_and_depends_on():
    database = postgres_json("main", "eu-west-1")
    database["disabled"] = True
    database["depends_on"] = ["network.main"]

    service = hydrate(service_json(database=database), registry=service_classes())

    assert service.database.meta.disabled is True
    assert service.database.meta.depends_on == ["network.main"]


def test_hydrate_entity_value_with_one_label_fills_it_with_the_name():
    service = hydrate(service_json(labelled=postgres_json("main", "eu-west-1")), registry=service_classes())

    assert service.labelled == LabelledRef(location="eu-west-1", name="main")


def test_hydrate_entity_value_with_two_labels_fills_the_subtype_and_name():
    service = hydrate(service_json(subtyped=postgres_json("main", "eu-west-1")), registry=service_classes())

    assert service.subtyped == SubtypedRef(location="eu-west-1", kind="postgres", name="main")


def test_hydrate_list_of_entity_values_keeps_order_and_meta():
    service = hydrate(
        service_json(databases=[postgres_json("a", "eu"), postgres_json("b", "us")]), registry=service_classes()
    )

    assert [d.meta.id for d in service.databases] == ["database.postgres.a", "database.postgres.b"]
    assert [d.location for d in service.databases] == ["eu", "us"]


def test_hydrate_map_of_entity_values_keeps_keys_and_meta():
    service = hydrate(
        service_json(by_name={"primary": postgres_json("a", "eu"), "replica": postgres_json("b", "us")}),
        registry=service_classes(),
    )

    assert list(service.by_name) == ["primary", "replica"]
    assert service.by_name["replica"].meta.id == "database.postgres.b"


def test_hydrate_entity_value_does_not_take_the_holding_entity_meta():
    service = hydrate(service_json(database=postgres_json("main", "eu-west-1")), registry=service_classes())

    assert service.meta.id == "hydrate_service.web"
    assert service.database.meta.id == "database.postgres.main"


def test_hydrate_plain_block_false_dataclass_is_an_object_without_meta():
    service = hydrate(service_json(endpoint={"port": 80, "meta_note": "x"}), registry=service_classes())

    assert service.endpoint == Endpoint(port=80, meta_note="x")
