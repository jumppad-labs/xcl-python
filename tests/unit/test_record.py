"""Building an entity's JSON from a Python object, the mirror of hydration."""

import dataclasses
import json
from dataclasses import dataclass
from typing import Any

import pytest

from xcl import Computed, Entity, Meta, NotEncodableError, NotRegisteredError, Sensitive, field
from xcl._classes import ClassMap
from xcl._schema import hydrate, record_bytes, record_of
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
    log_level: str = field(name="log-level", default="info")
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
class Bucket:
    region: str
    handle: str = field(label=True, default="")


@dataclass
class Cluster:
    nodes: int
    kind: str = field(label=True, default="")
    handle: str = field(label=True, default="")


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


@dataclass
class Bag:
    contents: Any = None
    meta: Meta | None = None


@dataclass
class Stray:
    text: str
    meta: Meta | None = None


def classes() -> ClassMap:
    registry = LocalRegistry()
    registry.register_type(App, "record_app")
    registry.register_type(Database, "record_database", "postgres")
    registry.register_type(Bucket, "record_bucket")
    registry.register_type(Cluster, "record_cluster", "kubernetes")
    registry.register_type(Note, "record_note")
    registry.register_type(Team, "record_team")
    registry.register_type(Bag, "record_bag")
    return ClassMap(registry.types)


def app_record() -> dict[str, Any]:
    return {
        "meta": {
            "id": "record_app.web",
            "name": "web",
            "type": "record_app",
            "module": "db",
            "file": "/f",
            "line": 2,
            "column": 1,
            "status": "created",
            "links": ["record_database.postgres.main"],
            "references": {"database": "record_database.postgres.main"},
            "generation": 7,
        },
        "disabled": True,
        "depends_on": ["record_database.postgres.main"],
        "image": "nginx",
        "replicas": 3,
        "region": "us",
        "log-level": "debug",
        "password": "(sensitive)",
        "endpoint": "https://web.example",
        "health": {"path": "/healthz"},
        "volume": [{"name": "data", "source": "/data"}, {"name": "logs", "source": "/logs"}],
        "listener": {"http": {"name": "http", "port": 80}, "https": {"name": "https", "port": 443}},
    }


def test_record_of_hydrated_instance_round_trips():
    app = hydrate(app_record(), registry=classes())

    assert record_of(app, classes()) == app_record()


def test_record_of_hydrated_subtype_instance_round_trips():
    data = {
        "meta": {
            "id": "record_database.postgres.main",
            "name": "main",
            "type": "record_database",
            "subtype": "postgres",
        },
        "version": "16",
    }

    database = hydrate(data, registry=classes())

    assert record_of(database, classes()) == data


def test_record_of_hydrated_instance_with_nested_meta_field_round_trips():
    data = {
        "meta": {"id": "record_team.core", "name": "core", "type": "record_team"},
        "owner": {"meta": "lead", "name": "ada"},
    }

    team = hydrate(data, registry=classes())

    assert record_of(team, classes()) == data


def test_record_of_hydrated_instance_leaves_out_filled_defaults():
    data = {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
    }

    app = hydrate(data, registry=classes())

    # hydration filled replicas, region, log-level, volume and listener with
    # the dataclass defaults; none of them was in the engine's JSON
    assert app.replicas == 2
    assert app.volume == []
    assert record_of(app, classes()) == {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
    }


def test_record_of_hydrated_instance_writes_changed_default():
    data = {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
    }

    app = hydrate(data, registry=classes())
    app.replicas = 5

    assert record_of(app, classes()) == {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
        "replicas": 5,
    }


def test_record_of_hydrated_instance_writes_edited_field():
    data = {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
    }

    app = hydrate(data, registry=classes())
    app.image = "caddy"

    assert record_of(app, classes()) == {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "caddy",
    }


def test_record_of_copied_instance_writes_filled_defaults():
    data = {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
    }

    # a copy was not hydrated, so it has no JSON to be written from
    app = dataclasses.replace(hydrate(data, registry=classes()))

    assert record_of(app, classes()) == {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
        "replicas": 2,
        "region": "eu",
        "log-level": "info",
        "volume": [],
        "listener": {},
    }


def test_record_of_writes_labels_into_meta():
    bucket = Bucket(region="eu", handle="assets")

    assert record_of(bucket, classes()) == {
        "meta": {"type": "record_bucket", "name": "assets"},
        "region": "eu",
    }


def test_record_of_hydrated_label_is_written_as_name():
    data = {"meta": {"id": "record_bucket.assets", "name": "assets", "type": "record_bucket"}, "region": "eu"}

    bucket = hydrate(data, registry=classes())

    assert bucket.handle == "assets"
    # the class has no meta field, so the meta is the one it was hydrated from
    assert record_of(bucket, classes()) == {
        "meta": {"id": "record_bucket.assets", "type": "record_bucket", "name": "assets"},
        "region": "eu",
    }


def test_record_of_hand_built_label_is_written_as_name():
    bucket = Bucket(handle="assets", region="eu")

    assert record_of(bucket, classes()) == {"meta": {"type": "record_bucket", "name": "assets"}, "region": "eu"}


def test_record_of_two_labels_takes_registered_subtype():
    cluster = Cluster(nodes=3, kind="ignored", handle="main")

    assert record_of(cluster, classes()) == {
        "meta": {"type": "record_cluster", "subtype": "kubernetes", "name": "main"},
        "nodes": 3,
    }


def test_record_of_singleton_has_no_name():
    note = Note(text="buy milk")

    assert record_of(note, classes()) == {"meta": {"type": "record_note"}, "text": "buy milk"}


def test_record_of_hand_built_sensitive_is_real_value():
    app = App(image="nginx", password=Sensitive("s3cret"), meta=Meta(name="web"))

    record = record_of(app, classes())

    assert record["password"] == "s3cret"


def test_record_of_redacted_sensitive_is_marker():
    app = App(image="nginx", password=Sensitive.redacted(), meta=Meta(name="web"))

    record = record_of(app, classes())

    assert record["password"] == "(sensitive)"


def test_record_of_renamed_field_uses_schema_name():
    app = App(image="nginx", log_level="debug", meta=Meta(name="web"))

    record = record_of(app, classes())

    assert record["log-level"] == "debug"
    assert "log_level" not in record


def test_record_of_nested_block_labels_are_keys():
    app = App(
        image="nginx",
        volume=[Volume(source="/data", name="data")],
        listener={"http": Listener(port=80, name="http")},
        meta=Meta(name="web"),
    )

    record = record_of(app, classes())

    assert record["volume"] == [{"source": "/data", "name": "data"}]
    assert record["listener"] == {"http": {"port": 80, "name": "http"}}


def test_record_of_nested_block_is_written_as_object():
    app = App(image="nginx", health=Health(path="/healthz"), meta=Meta(name="web"))

    record = record_of(app, classes())

    assert record["health"] == {"path": "/healthz"}


def test_record_of_disabled_and_depends_on_beside_meta():
    app = App(image="nginx", meta=Meta(name="web", disabled=True, depends_on=["record_database.postgres.main"]))

    record = record_of(app, classes())

    assert record["disabled"] is True
    assert record["depends_on"] == ["record_database.postgres.main"]
    assert "disabled" not in record["meta"]
    assert "depends_on" not in record["meta"]


def test_record_of_not_disabled_and_no_depends_on_are_omitted():
    app = App(image="nginx", meta=Meta(name="web"))

    record = record_of(app, classes())

    assert "disabled" not in record
    assert "depends_on" not in record


def test_record_of_computed_field_is_written():
    data = {"meta": {"id": "record_app.web", "name": "web", "type": "record_app"}, "image": "nginx", "endpoint": "https://web.example"}

    app = hydrate(data, registry=classes())
    record = record_of(app, classes())

    assert record["endpoint"] == "https://web.example"


def test_record_of_nullable_none_is_omitted():
    app = App(image="nginx", meta=Meta(name="web"))

    record = record_of(app, classes())

    assert "password" not in record
    assert "endpoint" not in record
    assert "health" not in record


def test_record_of_untyped_entity_is_its_dict():
    data = {
        "meta": {"id": "record_unregistered.main", "name": "main", "type": "record_unregistered", "subtype": "plugin"},
        "log": "/var/log",
        "disabled": True,
    }

    assert record_of(Entity(data), classes()) == data


def test_record_of_hand_built_names_registered_type_and_subtype():
    database = Database(version="16", meta=Meta(name="main"))

    assert record_of(database, classes()) == {
        "meta": {"type": "record_database", "subtype": "postgres", "name": "main"},
        "version": "16",
    }


def test_record_of_hand_built_meta_type_and_subtype_give_way_to_registration():
    database = Database(version="16", meta=Meta(name="main", type="other", subtype="mysql"))

    record = record_of(database, classes())

    assert record["meta"]["type"] == "record_database"
    assert record["meta"]["subtype"] == "postgres"


def test_record_of_unregistered_subtype_is_omitted_from_meta():
    app = App(image="nginx", meta=Meta(name="web", subtype="stale"))

    record = record_of(app, classes())

    assert "subtype" not in record["meta"]


def test_record_bytes_is_record_as_json():
    app = App(image="nginx", password=Sensitive("s3cret"), meta=Meta(name="web"))

    assert json.loads(record_bytes(app, classes())) == record_of(app, classes())


def test_record_of_none_is_not_encodable():
    with pytest.raises(NotEncodableError) as raised:
        record_of(None, classes())

    assert raised.value.details["reason"] == "it is not an entity"
    assert "NoneType" in raised.value.details["what"]


def test_record_of_dict_is_not_encodable():
    with pytest.raises(NotEncodableError) as raised:
        record_of({"meta": {"type": "record_app", "name": "web"}, "image": "nginx"}, classes())

    assert raised.value.details["reason"] == "it is not an entity"
    assert "dict" in raised.value.details["what"]


def test_record_of_dataclass_class_is_not_encodable():
    with pytest.raises(NotEncodableError) as raised:
        record_of(App, classes())

    assert raised.value.details["reason"] == "it is not an entity"


def test_record_of_other_object_is_not_encodable():
    with pytest.raises(NotEncodableError) as raised:
        record_of(object(), classes())

    assert raised.value.details["reason"] == "it is not an entity"


def test_record_of_unregistered_class_raises_not_registered():
    stray = Stray(text="lost", meta=Meta(name="lost"))

    with pytest.raises(NotRegisteredError) as raised:
        record_of(stray, classes())

    assert raised.value.details == {"class": "Stray"}


def test_record_of_unnamed_entity_is_not_encodable():
    app = App(image="nginx")

    with pytest.raises(NotEncodableError) as raised:
        record_of(app, classes())

    assert "it has no name" in raised.value.details["reason"]
    assert raised.value.details["what"] == "a record_app entity"


def test_record_of_empty_label_is_not_encodable():
    bucket = Bucket(region="eu")

    with pytest.raises(NotEncodableError) as raised:
        record_of(bucket, classes())

    assert "it has no name" in raised.value.details["reason"]


def test_record_bytes_unserialisable_set_is_not_encodable():
    bag = Bag(contents={1, 2}, meta=Meta(name="things"))

    with pytest.raises(NotEncodableError) as raised:
        record_bytes(bag, classes())

    assert raised.value.details["reason"] == "it holds a value with no configuration form"


def test_record_bytes_unserialisable_object_is_not_encodable():
    bag = Bag(contents=object(), meta=Meta(name="things"))

    with pytest.raises(NotEncodableError) as raised:
        record_bytes(bag, classes())

    assert raised.value.details["reason"] == "it holds a value with no configuration form"


def test_record_of_hydrated_nested_block_leaves_out_filled_default():
    data = {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
        "volume": [{"source": "/logs"}],
    }

    app = hydrate(data, registry=classes())

    # hydration filled the unlabelled volume's name with its default
    assert app.volume[0].name == ""
    assert record_of(app, classes())["volume"] == [{"source": "/logs"}]


def test_record_of_hydrated_nested_block_writes_edited_field():
    data = {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
        "volume": [{"source": "/logs"}],
    }

    app = hydrate(data, registry=classes())
    app.volume[0].source = "/var/log"

    assert record_of(app, classes())["volume"] == [{"source": "/var/log"}]


def test_record_of_hydrated_unset_sensitive_stays_marker():
    data = {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
        "password": "(sensitive)",
    }

    app = hydrate(data, registry=classes())

    # the engine fills the marker from its own copy, set or not
    assert record_of(app, classes())["password"] == "(sensitive)"


def test_record_of_hydrated_edited_sensitive_is_real_value():
    data = {
        "meta": {"id": "record_app.web", "name": "web", "type": "record_app"},
        "image": "nginx",
        "password": "(sensitive)",
    }

    app = hydrate(data, registry=classes())
    app.password = Sensitive("rotated")

    assert record_of(app, classes())["password"] == "rotated"
