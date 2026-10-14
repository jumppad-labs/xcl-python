"""Config creation and release, against the fake transport."""

from dataclasses import dataclass

import pytest

import xcl
from xcl import Meta
from xcl._client import Client
from xcl._core import core_pb2
from fakes import FakeTransport


def test_config_creates_and_keeps_handle():
    transport = FakeTransport({"CreateConfig": core_pb2.CreateConfigResponse(handle=42)})
    client = Client(transport)

    config = xcl.Config(client=client)

    assert config.handle == 42
    assert transport.methods_called() == ["GetVersion", "CreateConfig"]
    handle, _, request = transport.calls[-1]
    assert handle == 0
    assert request == core_pb2.CreateConfigRequest().SerializeToString()
    assert transport.released == []


def test_close_releases_once():
    transport = FakeTransport()
    config = xcl.Config(client=Client(transport))

    config.close()
    config.close()

    assert transport.released == [7]
    assert config.handle == 0


def test_context_manager_closes():
    transport = FakeTransport()

    with xcl.Config(client=Client(transport)) as config:
        assert config.handle == 7
        assert transport.released == []

    assert transport.released == [7]
    assert config.handle == 0


@dataclass
class App:
    image: str
    meta: Meta | None = None


@dataclass
class OtherApp:
    image: str
    meta: Meta | None = None


@dataclass
class Database:
    version: str
    meta: Meta | None = None


@dataclass
class Note:
    text: str


@dataclass
class Unregistered:
    name: str


APP_JSON = b'{"meta": {"id": "app.web", "name": "web", "type": "app"}, "image": "nginx"}'
DATABASE_JSON = b'{"meta": {"id": "database.postgres.main", "name": "main", "type": "database", "subtype": "postgres"}, "version": "16"}'
CACHE_JSON = b'{"meta": {"id": "cache.redis", "name": "redis", "type": "cache"}, "size": 64}'
NOTE_JSON = b'{"meta": {"id": "note.todo", "name": "todo", "type": "note"}, "text": "buy milk"}'


def app_registry() -> xcl.LocalRegistry:
    registry = xcl.LocalRegistry()
    registry.register_type(App, "app")
    registry.register_type(Database, "database", "postgres")
    registry.register_type(Note, "note")
    return registry


def test_untyped_find_returns_registered_class():
    transport = FakeTransport({"Find": core_pb2.EntityResponse(entity=APP_JSON)})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.find(None, "app.web")

    assert found == App(image="nginx", meta=xcl.Meta(id="app.web", name="web", type="app"))


def test_untyped_find_returns_registered_class_for_subtype():
    transport = FakeTransport({"Find": core_pb2.EntityResponse(entity=DATABASE_JSON)})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.find(None, "database.postgres.main")

    assert isinstance(found, Database)
    assert found.version == "16"
    assert found.meta.address == "database.postgres.main"


def test_untyped_find_of_unregistered_type_returns_generic_entity():
    transport = FakeTransport({"Find": core_pb2.EntityResponse(entity=CACHE_JSON)})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.find(None, "cache.redis")

    assert isinstance(found, xcl.Entity)
    assert found.meta.address == "cache.redis"
    assert found.size == 64


def test_entities_return_registered_classes_and_generic_entities():
    transport = FakeTransport({"Entities": core_pb2.EntitiesResponse(entities=[APP_JSON, CACHE_JSON])})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.entities()

    assert len(found) == 2
    assert found[0] == App(image="nginx", meta=xcl.Meta(id="app.web", name="web", type="app"))
    assert isinstance(found[1], xcl.Entity)
    assert found[1].meta.address == "cache.redis"


def test_untyped_find_by_type_returns_registered_class():
    transport = FakeTransport({"FindByType": core_pb2.EntitiesResponse(entities=[APP_JSON])})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.find_by_type(None, "app")

    assert found == [App(image="nginx", meta=xcl.Meta(id="app.web", name="web", type="app"))]


def test_untyped_find_one_returns_registered_class():
    transport = FakeTransport({"FindOne": core_pb2.EntityResponse(entity=APP_JSON)})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.find_one(None, "app")

    assert found == App(image="nginx", meta=xcl.Meta(id="app.web", name="web", type="app"))


def test_untyped_find_of_class_without_meta_has_no_meta():
    transport = FakeTransport({"Find": core_pb2.EntityResponse(entity=NOTE_JSON)})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.find(None, "note.todo")

    assert found == Note(text="buy milk")
    assert not hasattr(found, "meta")


def test_typed_find_with_registered_class_returns_that_class():
    transport = FakeTransport({"Find": core_pb2.EntityResponse(entity=APP_JSON)})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.find(App, "app.web")

    assert found == App(image="nginx", meta=xcl.Meta(id="app.web", name="web", type="app"))


def test_all_with_registered_class_finds_by_its_type_and_subtype():
    transport = FakeTransport({"FindByType": core_pb2.EntitiesResponse(entities=[DATABASE_JSON])})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.all(Database)

    assert len(found) == 1
    assert found[0].version == "16"
    _, _, request = transport.calls[-1]
    assert request == core_pb2.FindByTypeRequest(path=["database", "postgres"]).SerializeToString()


def test_two_configs_hydrate_the_same_entity_into_their_own_classes():
    first_registry = xcl.LocalRegistry()
    first_registry.register_type(App, "app")
    second_registry = xcl.LocalRegistry()
    second_registry.register_type(OtherApp, "app")
    first = xcl.Config(registries=[first_registry], client=Client(FakeTransport({"Find": core_pb2.EntityResponse(entity=APP_JSON)})))
    second = xcl.Config(registries=[second_registry], client=Client(FakeTransport({"Find": core_pb2.EntityResponse(entity=APP_JSON)})))

    from_first = first.find(None, "app.web")
    from_second = second.find(None, "app.web")

    assert type(from_first) is App
    assert type(from_second) is OtherApp
    assert from_first.image == "nginx"
    assert from_second.image == "nginx"


def test_typed_find_with_unregistered_class_raises_not_registered():
    transport = FakeTransport({"Find": core_pb2.EntityResponse(entity=APP_JSON)})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    with pytest.raises(xcl.NotRegisteredError, match="Unregistered is not registered"):
        config.find(Unregistered, "app.web")


def test_typed_find_with_class_registered_on_another_config_raises_not_registered():
    other_registry = xcl.LocalRegistry()
    other_registry.register_type(OtherApp, "app")
    transport = FakeTransport({"Find": core_pb2.EntityResponse(entity=APP_JSON)})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))
    xcl.Config(registries=[other_registry], client=Client(FakeTransport()))

    with pytest.raises(xcl.NotRegisteredError, match="OtherApp is not registered"):
        config.find(OtherApp, "app.web")


def test_typed_find_with_class_of_another_type_raises_type_mismatch():
    transport = FakeTransport({"Find": core_pb2.EntityResponse(entity=APP_JSON)})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    with pytest.raises(xcl.TypeMismatchError, match="app.web is a app, not a database.postgres"):
        config.find(Database, "app.web")


def test_all_with_unregistered_class_raises_not_registered():
    transport = FakeTransport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    with pytest.raises(xcl.NotRegisteredError, match="Unregistered is not registered"):
        config.all(Unregistered)

    assert "FindByType" not in transport.methods_called()


def test_all_with_none_raises_not_registered():
    transport = FakeTransport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    with pytest.raises(xcl.NotRegisteredError):
        config.all(None)


def test_class_registered_twice_in_one_registry_is_refused_at_creation():
    registry = xcl.LocalRegistry()
    registry.register_type(App, "app")
    registry.register_type(App, "service")
    transport = FakeTransport()

    with pytest.raises(xcl.SchemaError, match="App is registered as both app and service"):
        xcl.Config(registries=[registry], client=Client(transport))

    assert "CreateConfig" not in transport.methods_called()


def test_class_registered_twice_across_registries_is_refused_at_creation():
    first = xcl.LocalRegistry()
    first.register_type(App, "app")
    second = xcl.LocalRegistry()
    second.register_type(App, "service")
    transport = FakeTransport()

    with pytest.raises(xcl.SchemaError, match="App is registered as both app and service"):
        xcl.Config(registries=[first, second], client=Client(transport))

    assert "CreateConfig" not in transport.methods_called()
