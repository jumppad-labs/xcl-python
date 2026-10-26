"""Config creation and release, against the fake transport."""

import asyncio
import json
from dataclasses import dataclass

import pytest

import xcl
import xcl.aio
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


def test_config_sends_event_data_none():
    transport = FakeTransport()

    xcl.Config(event_data=xcl.EventDataLevel.NONE, client=Client(transport))

    _, method, raw = transport.calls[-1]
    assert method == "CreateConfig"
    request = core_pb2.CreateConfigRequest.FromString(raw)
    assert request.event_data == core_pb2.EVENT_DATA_NONE


def test_config_sends_event_data_raw():
    transport = FakeTransport()

    xcl.Config(event_data=xcl.EventDataLevel.RAW, client=Client(transport))

    _, method, raw = transport.calls[-1]
    assert method == "CreateConfig"
    request = core_pb2.CreateConfigRequest.FromString(raw)
    assert request.event_data == core_pb2.EVENT_DATA_RAW


def test_config_sends_event_data_processed():
    transport = FakeTransport()

    xcl.Config(event_data=xcl.EventDataLevel.PROCESSED, client=Client(transport))

    _, method, raw = transport.calls[-1]
    assert method == "CreateConfig"
    request = core_pb2.CreateConfigRequest.FromString(raw)
    assert request.event_data == core_pb2.EVENT_DATA_PROCESSED


def test_config_event_data_defaults_to_none():
    transport = FakeTransport()

    xcl.Config(client=Client(transport))

    _, method, raw = transport.calls[-1]
    assert method == "CreateConfig"
    request = core_pb2.CreateConfigRequest.FromString(raw)
    assert request.event_data == core_pb2.EVENT_DATA_NONE


def test_aio_config_sends_event_data_none():
    transport = FakeTransport()

    async def run() -> None:
        config = xcl.aio.Config(event_data=xcl.EventDataLevel.NONE, client=Client(transport))
        await config.open()
        await config.close()

    asyncio.run(run())

    create_calls = [call for call in transport.calls if call[1] == "CreateConfig"]
    assert len(create_calls) == 1
    request = core_pb2.CreateConfigRequest.FromString(create_calls[0][2])
    assert request.event_data == core_pb2.EVENT_DATA_NONE


def test_aio_config_sends_event_data_raw():
    transport = FakeTransport()

    async def run() -> None:
        config = xcl.aio.Config(event_data=xcl.EventDataLevel.RAW, client=Client(transport))
        await config.open()
        await config.close()

    asyncio.run(run())

    create_calls = [call for call in transport.calls if call[1] == "CreateConfig"]
    assert len(create_calls) == 1
    request = core_pb2.CreateConfigRequest.FromString(create_calls[0][2])
    assert request.event_data == core_pb2.EVENT_DATA_RAW


def test_aio_config_sends_event_data_processed():
    transport = FakeTransport()

    async def run() -> None:
        config = xcl.aio.Config(event_data=xcl.EventDataLevel.PROCESSED, client=Client(transport))
        await config.open()
        await config.close()

    asyncio.run(run())

    create_calls = [call for call in transport.calls if call[1] == "CreateConfig"]
    assert len(create_calls) == 1
    request = core_pb2.CreateConfigRequest.FromString(create_calls[0][2])
    assert request.event_data == core_pb2.EVENT_DATA_PROCESSED


def test_aio_config_event_data_defaults_to_none():
    transport = FakeTransport()

    async def run() -> None:
        config = xcl.aio.Config(client=Client(transport))
        await config.open()
        await config.close()

    asyncio.run(run())

    create_calls = [call for call in transport.calls if call[1] == "CreateConfig"]
    assert len(create_calls) == 1
    request = core_pb2.CreateConfigRequest.FromString(create_calls[0][2])
    assert request.event_data == core_pb2.EVENT_DATA_NONE


def test_config_refuses_event_data_string_processed():
    transport = FakeTransport()

    with pytest.raises(TypeError, match=r"xcl\.EventDataLevel"):
        xcl.Config(event_data="processed", client=Client(transport))  # type: ignore[arg-type]

    assert "CreateConfig" not in transport.methods_called()


def test_config_refuses_event_data_string_verbose():
    transport = FakeTransport()

    with pytest.raises(TypeError, match=r"xcl\.EventDataLevel"):
        xcl.Config(event_data="verbose", client=Client(transport))  # type: ignore[arg-type]

    assert "CreateConfig" not in transport.methods_called()


def test_config_refuses_event_data_integer():
    transport = FakeTransport()

    with pytest.raises(TypeError, match=r"xcl\.EventDataLevel"):
        xcl.Config(event_data=1, client=Client(transport))  # type: ignore[arg-type]

    assert "CreateConfig" not in transport.methods_called()


def test_config_refuses_event_data_none():
    transport = FakeTransport()

    with pytest.raises(TypeError, match=r"xcl\.EventDataLevel"):
        xcl.Config(event_data=None, client=Client(transport))  # type: ignore[arg-type]

    assert "CreateConfig" not in transport.methods_called()


def test_aio_config_refuses_event_data_string_processed():
    transport = FakeTransport()

    with pytest.raises(TypeError, match=r"xcl\.EventDataLevel"):
        xcl.aio.Config(event_data="processed", client=Client(transport))  # type: ignore[arg-type]

    assert transport.calls == []


def test_aio_config_refuses_event_data_string_verbose():
    transport = FakeTransport()

    with pytest.raises(TypeError, match=r"xcl\.EventDataLevel"):
        xcl.aio.Config(event_data="verbose", client=Client(transport))  # type: ignore[arg-type]

    assert transport.calls == []


def test_aio_config_refuses_event_data_integer():
    transport = FakeTransport()

    with pytest.raises(TypeError, match=r"xcl\.EventDataLevel"):
        xcl.aio.Config(event_data=1, client=Client(transport))  # type: ignore[arg-type]

    assert transport.calls == []


def test_aio_config_refuses_event_data_none():
    transport = FakeTransport()

    with pytest.raises(TypeError, match=r"xcl\.EventDataLevel"):
        xcl.aio.Config(event_data=None, client=Client(transport))  # type: ignore[arg-type]

    assert transport.calls == []


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
    assert found.meta.id == "database.postgres.main"


def test_untyped_find_of_unregistered_type_returns_generic_entity():
    transport = FakeTransport({"Find": core_pb2.EntityResponse(entity=CACHE_JSON)})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.find(None, "cache.redis")

    assert isinstance(found, xcl.Entity)
    assert found.meta.id == "cache.redis"
    assert found.size == 64


def test_entities_return_registered_classes_and_generic_entities():
    transport = FakeTransport({"Entities": core_pb2.EntitiesResponse(entities=[APP_JSON, CACHE_JSON])})
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    found = config.entities()

    assert len(found) == 2
    assert found[0] == App(image="nginx", meta=xcl.Meta(id="app.web", name="web", type="app"))
    assert isinstance(found[1], xcl.Entity)
    assert found[1].meta.id == "cache.redis"


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


ENCODED_TEXT = b'app "web" {\n  image = "nginx"\n}\n'
SAVED_RECORD = b'{"meta": {"id": "app.web", "name": "web", "type": "app"}, "image": "nginx"}'


def encode_transport() -> FakeTransport:
    return FakeTransport(
        {
            "EncodeEntity": core_pb2.EncodeEntityResponse(text=ENCODED_TEXT),
            "EncodeSavedEntity": core_pb2.EncodeSavedEntityResponse(text=ENCODED_TEXT),
        }
    )


def sent_encode_entity_request(transport: FakeTransport) -> core_pb2.EncodeEntityRequest:
    handle, method, request = transport.calls[-1]
    assert handle == 7
    assert method == "EncodeEntity"
    return core_pb2.EncodeEntityRequest.FromString(request)


def sent_encode_saved_entity_request(transport: FakeTransport) -> core_pb2.EncodeSavedEntityRequest:
    handle, method, request = transport.calls[-1]
    assert handle == 7
    assert method == "EncodeSavedEntity"
    return core_pb2.EncodeSavedEntityRequest.FromString(request)


def hand_built_app() -> App:
    return App(image="nginx", meta=xcl.Meta(name="web"))


def test_encode_entity_sends_record_and_highlight():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    text = config.encode_entity(hand_built_app(), highlight=True)

    assert text == 'app "web" {\n  image = "nginx"\n}\n'
    request = sent_encode_entity_request(transport)
    assert json.loads(request.entity) == {"meta": {"type": "app", "name": "web"}, "image": "nginx"}
    assert request.highlight is True


def test_encode_entity_sends_highlight_off_by_default():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_entity(hand_built_app())

    request = sent_encode_entity_request(transport)
    assert request.highlight is False


def test_encode_entity_sends_include_computed():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_entity(hand_built_app(), include_computed=True)

    options = sent_encode_entity_request(transport).options
    assert options.include_computed is True
    assert options.include_empty is False
    assert options.reveal_sensitive is False
    assert options.show_references is False


def test_encode_entity_sends_include_empty():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_entity(hand_built_app(), include_empty=True)

    options = sent_encode_entity_request(transport).options
    assert options.include_computed is False
    assert options.include_empty is True
    assert options.reveal_sensitive is False
    assert options.show_references is False


def test_encode_entity_sends_reveal_sensitive():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_entity(hand_built_app(), reveal_sensitive=True)

    options = sent_encode_entity_request(transport).options
    assert options.include_computed is False
    assert options.include_empty is False
    assert options.reveal_sensitive is True
    assert options.show_references is False


def test_encode_entity_sends_show_references():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_entity(hand_built_app(), show_references=True)

    options = sent_encode_entity_request(transport).options
    assert options.include_computed is False
    assert options.include_empty is False
    assert options.reveal_sensitive is False
    assert options.show_references is True


def test_encode_entity_default_options_all_off():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_entity(hand_built_app())

    options = sent_encode_entity_request(transport).options
    assert options.include_computed is False
    assert options.include_empty is False
    assert options.reveal_sensitive is False
    assert options.show_references is False


def test_encode_entity_not_an_entity_makes_no_call():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    with pytest.raises(xcl.NotEncodableError):
        config.encode_entity(None)

    assert "EncodeEntity" not in transport.methods_called()


def test_encode_entity_unregistered_class_makes_no_call():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    with pytest.raises(xcl.NotRegisteredError, match="Unregistered is not registered"):
        config.encode_entity(Unregistered(name="stray"))

    assert "EncodeEntity" not in transport.methods_called()


def test_encode_saved_entity_sends_record_and_highlight():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    text = config.encode_saved_entity(SAVED_RECORD, highlight=True)

    assert text == 'app "web" {\n  image = "nginx"\n}\n'
    request = sent_encode_saved_entity_request(transport)
    assert request.entity == SAVED_RECORD
    assert request.highlight is True


def test_encode_saved_entity_sends_include_computed():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_saved_entity(SAVED_RECORD, include_computed=True)

    options = sent_encode_saved_entity_request(transport).options
    assert options.include_computed is True
    assert options.include_empty is False
    assert options.reveal_sensitive is False
    assert options.show_references is False


def test_encode_saved_entity_sends_include_empty():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_saved_entity(SAVED_RECORD, include_empty=True)

    options = sent_encode_saved_entity_request(transport).options
    assert options.include_computed is False
    assert options.include_empty is True
    assert options.reveal_sensitive is False
    assert options.show_references is False


def test_encode_saved_entity_sends_reveal_sensitive():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_saved_entity(SAVED_RECORD, reveal_sensitive=True)

    options = sent_encode_saved_entity_request(transport).options
    assert options.include_computed is False
    assert options.include_empty is False
    assert options.reveal_sensitive is True
    assert options.show_references is False


def test_encode_saved_entity_sends_show_references():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_saved_entity(SAVED_RECORD, show_references=True)

    options = sent_encode_saved_entity_request(transport).options
    assert options.include_computed is False
    assert options.include_empty is False
    assert options.reveal_sensitive is False
    assert options.show_references is True


def test_encode_saved_entity_default_options_all_off():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_saved_entity(SAVED_RECORD)

    request = sent_encode_saved_entity_request(transport)
    assert request.highlight is False
    assert request.options.include_computed is False
    assert request.options.include_empty is False
    assert request.options.reveal_sensitive is False
    assert request.options.show_references is False


def test_aio_encode_entity_sends_options():
    transport = encode_transport()
    texts: list[str] = []

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], client=Client(transport))
        try:
            texts.append(
                await config.encode_entity(
                    hand_built_app(),
                    include_computed=True,
                    include_empty=True,
                    reveal_sensitive=True,
                    show_references=True,
                    highlight=True,
                )
            )
        finally:
            await config.close()

    asyncio.run(run())

    assert texts == ['app "web" {\n  image = "nginx"\n}\n']
    encode_calls = [call for call in transport.calls if call[1] == "EncodeEntity"]
    assert len(encode_calls) == 1
    handle, _, raw = encode_calls[0]
    assert handle == 7
    request = core_pb2.EncodeEntityRequest.FromString(raw)
    assert json.loads(request.entity) == {"meta": {"type": "app", "name": "web"}, "image": "nginx"}
    assert request.highlight is True
    assert request.options.include_computed is True
    assert request.options.include_empty is True
    assert request.options.reveal_sensitive is True
    assert request.options.show_references is True


def test_aio_encode_entity_not_an_entity_makes_no_call():
    transport = encode_transport()

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], client=Client(transport))
        try:
            await config.encode_entity(None)
        finally:
            await config.close()

    with pytest.raises(xcl.NotEncodableError):
        asyncio.run(run())

    assert "EncodeEntity" not in transport.methods_called()
