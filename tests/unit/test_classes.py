"""A configuration's classes, by block type and by class."""

from dataclasses import dataclass

import pytest

from xcl import LocalRegistry, Meta, NotRegisteredError, SchemaError
from xcl._classes import ClassMap


@dataclass
class App:
    image: str


@dataclass
class Database:
    version: str
    meta: Meta | None = None


@dataclass
class Unregistered:
    name: str


def test_class_for_type_returns_registered_class():
    registry = LocalRegistry()
    registry.register_type(App, "app")

    classes = ClassMap(registry.types)

    assert classes.class_for("app") is App


def test_class_for_type_and_subtype_returns_registered_class():
    registry = LocalRegistry()
    registry.register_type(Database, "database", "postgres")

    classes = ClassMap(registry.types)

    assert classes.class_for("database", "postgres") is Database


def test_class_for_type_treats_none_subtype_as_none():
    registry = LocalRegistry()
    registry.register_type(App, "app")

    classes = ClassMap(registry.types)

    assert classes.class_for("app", None) is App


def test_class_for_unknown_type_is_none():
    registry = LocalRegistry()
    registry.register_type(App, "app")

    classes = ClassMap(registry.types)

    assert classes.class_for("container") is None


def test_class_for_type_without_its_subtype_is_none():
    registry = LocalRegistry()
    registry.register_type(Database, "database", "postgres")

    classes = ClassMap(registry.types)

    assert classes.class_for("database") is None


def test_names_of_class_without_subtype():
    registry = LocalRegistry()
    registry.register_type(App, "app")

    classes = ClassMap(registry.types)

    assert classes.names_of(App) == ("app", "")


def test_names_of_class_with_subtype():
    registry = LocalRegistry()
    registry.register_type(Database, "database", "postgres")

    classes = ClassMap(registry.types)

    assert classes.names_of(Database) == ("database", "postgres")


def test_names_of_unregistered_class_raises_not_registered():
    registry = LocalRegistry()
    registry.register_type(App, "app")
    classes = ClassMap(registry.types)

    with pytest.raises(NotRegisteredError, match="Unregistered is not registered.*register_type"):
        classes.names_of(Unregistered)


def test_names_of_none_raises_not_registered():
    classes = ClassMap()

    with pytest.raises(NotRegisteredError, match="register_type"):
        classes.names_of(None)


def test_from_registries_combines_every_registry():
    apps = LocalRegistry()
    apps.register_type(App, "app")
    databases = LocalRegistry()
    databases.register_type(Database, "database", "postgres")

    classes = ClassMap.from_registries([apps, databases])

    assert classes.class_for("app") is App
    assert classes.class_for("database", "postgres") is Database


def test_class_registered_twice_is_refused():
    registry = LocalRegistry()
    registry.register_type(App, "app")
    registry.register_type(App, "service")

    with pytest.raises(SchemaError, match="App is registered as both app and service"):
        ClassMap(registry.types)


def test_class_registered_twice_across_registries_is_refused():
    first = LocalRegistry()
    first.register_type(App, "app")
    second = LocalRegistry()
    second.register_type(App, "service")

    with pytest.raises(SchemaError, match="App is registered as both app and service"):
        ClassMap.from_registries([first, second])
