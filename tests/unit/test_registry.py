"""Registering plain dataclasses as block types on a registry."""

import json
from dataclasses import dataclass

import pytest

import xcl
from xcl import GitHubRegistry, LocalRegistry, Meta, SchemaError, field
from xcl.registry import Registration


@dataclass
class App:
    image: str
    replicas: int = 2
    meta: Meta | None = None


@dataclass
class Database:
    version: str
    meta: Meta | None = None
    disabled: bool = False
    depends_on: list[str] = field(default_factory=list)


APP_SCHEMA = {
    "schema_version": 1,
    "type": "app",
    "fields": [
        {"name": "image", "type": "string"},
        {"name": "replicas", "type": "number", "format": "int", "optional": True, "default": 2},
    ],
}

DATABASE_SCHEMA = {
    "schema_version": 1,
    "type": "database",
    "subtype": "postgres",
    "fields": [{"name": "version", "type": "string"}],
}


def test_local_registry_registers_plain_dataclass_by_type():
    registry = LocalRegistry()

    registry.register_type(App, "app")

    assert registry.types == [Registration(cls=App, type="app", subtype="", schema=APP_SCHEMA)]


def test_local_registry_registers_plain_dataclass_by_type_and_subtype():
    registry = LocalRegistry()

    registry.register_type(Database, "database", "postgres")

    assert registry.types == [
        Registration(cls=Database, type="database", subtype="postgres", schema=DATABASE_SCHEMA)
    ]


def test_local_registry_sends_declared_type_without_subtype():
    registry = LocalRegistry()
    registry.register_type(App, "app")

    declared = registry._to_proto().local.types

    assert len(declared) == 1
    assert declared[0].type == "app"
    assert declared[0].subtype == ""
    assert json.loads(declared[0].schema) == APP_SCHEMA


def test_local_registry_sends_declared_type_with_subtype():
    registry = LocalRegistry()
    registry.register_type(Database, "database", "postgres")

    declared = registry._to_proto().local.types

    assert len(declared) == 1
    assert declared[0].type == "database"
    assert declared[0].subtype == "postgres"
    assert json.loads(declared[0].schema) == DATABASE_SCHEMA


def test_local_registry_keeps_registration_order():
    registry = LocalRegistry()

    registry.register_type(App, "app")
    registry.register_type(Database, "database", "postgres")

    assert [(r.type, r.subtype) for r in registry.types] == [("app", ""), ("database", "postgres")]


def test_github_registry_registers_plain_dataclass_by_type():
    registry = GitHubRegistry()

    registry.register_type(App, "app")

    assert registry.types == [Registration(cls=App, type="app", subtype="", schema=APP_SCHEMA)]


def test_github_registry_registers_plain_dataclass_by_type_and_subtype():
    registry = GitHubRegistry()

    registry.register_type(Database, "database", "postgres")

    assert registry.types == [
        Registration(cls=Database, type="database", subtype="postgres", schema=DATABASE_SCHEMA)
    ]


def test_github_registry_sends_declared_type_without_subtype():
    registry = GitHubRegistry()
    registry.register_type(App, "app")

    declared = registry._to_proto().github.types

    assert len(declared) == 1
    assert declared[0].type == "app"
    assert declared[0].subtype == ""
    assert json.loads(declared[0].schema) == APP_SCHEMA


def test_github_registry_sends_declared_type_with_subtype():
    registry = GitHubRegistry()
    registry.register_type(Database, "database", "postgres")

    declared = registry._to_proto().github.types

    assert len(declared) == 1
    assert declared[0].type == "database"
    assert declared[0].subtype == "postgres"
    assert json.loads(declared[0].schema) == DATABASE_SCHEMA


def test_registration_error_is_an_xcl_error_and_a_type_error():
    class NotADataclass:
        image: str

    with pytest.raises(SchemaError) as raised:
        LocalRegistry().register_type(NotADataclass, "app")

    assert isinstance(raised.value, xcl.Error)
    assert isinstance(raised.value, TypeError)
    assert raised.value.code == "schema"


def test_local_registry_refuses_class_that_is_not_a_dataclass():
    class NotADataclass:
        image: str

    with pytest.raises(SchemaError, match="NotADataclass must be a dataclass"):
        LocalRegistry().register_type(NotADataclass, "app")


def test_github_registry_refuses_class_that_is_not_a_dataclass():
    class NotADataclass:
        image: str

    with pytest.raises(SchemaError, match="NotADataclass must be a dataclass"):
        GitHubRegistry().register_type(NotADataclass, "app")


def test_local_registry_refuses_undecorated_subclass_of_a_dataclass():
    class Derived(App):
        region: str = "eu"

    with pytest.raises(SchemaError, match="Derived must be a dataclass.*a dataclass base is not enough"):
        LocalRegistry().register_type(Derived, "app")


def test_local_registry_refuses_empty_type_name():
    with pytest.raises(SchemaError, match=r'App must be registered with a type name, such as register_type\(App, "app"\)'):
        LocalRegistry().register_type(App, "")


def test_github_registry_refuses_empty_type_name():
    with pytest.raises(SchemaError, match=r'App must be registered with a type name, such as register_type\(App, "app"\)'):
        GitHubRegistry().register_type(App, "")


def test_local_registry_refuses_meta_of_wrong_type():
    @dataclass
    class Block:
        meta: dict[str, str] = field(default_factory=dict)

    with pytest.raises(SchemaError, match=r"Block\.meta.*must be an xcl\.Meta \| None"):
        LocalRegistry().register_type(Block, "block")


def test_local_registry_refuses_disabled_of_wrong_type():
    @dataclass
    class Block:
        disabled: int = 0

    with pytest.raises(SchemaError, match=r"Block\.disabled.*must be a bool"):
        LocalRegistry().register_type(Block, "block")


def test_local_registry_refuses_depends_on_of_wrong_type():
    @dataclass
    class Block:
        depends_on: str = ""

    with pytest.raises(SchemaError, match=r"Block\.depends_on.*must be a list\[str\]"):
        LocalRegistry().register_type(Block, "block")


def test_refused_registration_leaves_registry_empty():
    registry = LocalRegistry()

    with pytest.raises(SchemaError):
        registry.register_type(App, "")

    assert registry.types == []


@dataclass
class WebApp:
    image: str


@dataclass
class WorkerApp:
    command: str


def test_registering_on_one_local_registry_leaves_another_empty():
    first = LocalRegistry()
    second = LocalRegistry()

    first.register_type(WebApp, "app")

    assert second.types == []


def test_two_local_registries_keep_their_own_class_for_the_same_type_name():
    first = LocalRegistry()
    second = LocalRegistry()

    first.register_type(WebApp, "app")
    second.register_type(WorkerApp, "app")

    assert [r.cls for r in first.types] == [WebApp]
    assert [r.cls for r in second.types] == [WorkerApp]


def test_registering_a_class_does_not_stamp_a_type_attribute():
    LocalRegistry().register_type(WebApp, "app")

    assert not hasattr(WebApp, "__xcl_type__")


def test_registering_a_class_does_not_stamp_a_subtype_attribute():
    LocalRegistry().register_type(Database, "database", "postgres")

    assert not hasattr(Database, "__xcl_subtype__")


def test_registering_a_class_does_not_stamp_a_schema_attribute():
    LocalRegistry().register_type(WebApp, "app")

    assert not hasattr(WebApp, "__xcl_schema__")
