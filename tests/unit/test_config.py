"""Config creation and release, against the fake transport."""

import asyncio
import io
import json
import threading
from dataclasses import dataclass

import pytest

import xcl
import xcl.aio
from xcl import Meta
from xcl._client import Client
from xcl._core import core_pb2
from xcl.highlight import Kind, Token
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


def test_encode_entity_sends_record():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    text = config.encode_entity(hand_built_app())

    assert text == 'app "web" {\n  image = "nginx"\n}\n'
    request = sent_encode_entity_request(transport)
    assert json.loads(request.entity) == {"meta": {"type": "app", "name": "web"}, "image": "nginx"}


def test_encode_entity_highlight_keyword_is_refused():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    with pytest.raises(TypeError, match="unexpected keyword argument 'highlight'"):
        config.encode_entity(hand_built_app(), highlight=True)  # type: ignore[call-arg]

    assert "EncodeEntity" not in transport.methods_called()


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


def test_encode_saved_entity_sends_record():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    text = config.encode_saved_entity(SAVED_RECORD)

    assert text == 'app "web" {\n  image = "nginx"\n}\n'
    request = sent_encode_saved_entity_request(transport)
    assert request.entity == SAVED_RECORD


def test_encode_saved_entity_highlight_keyword_is_refused():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    with pytest.raises(TypeError, match="unexpected keyword argument 'highlight'"):
        config.encode_saved_entity(SAVED_RECORD, highlight=True)  # type: ignore[call-arg]

    assert "EncodeSavedEntity" not in transport.methods_called()


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
    assert request.options.include_computed is True
    assert request.options.include_empty is True
    assert request.options.reveal_sensitive is True
    assert request.options.show_references is True


def test_aio_encode_entity_highlight_keyword_is_refused():
    transport = encode_transport()

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], client=Client(transport))
        try:
            await config.encode_entity(hand_built_app(), highlight=True)  # type: ignore[call-arg]
        finally:
            await config.close()

    with pytest.raises(TypeError, match="unexpected keyword argument 'highlight'"):
        asyncio.run(run())

    assert "EncodeEntity" not in transport.methods_called()


def test_aio_encode_saved_entity_highlight_keyword_is_refused():
    transport = encode_transport()

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], client=Client(transport))
        try:
            await config.encode_saved_entity(SAVED_RECORD, highlight=True)  # type: ignore[call-arg]
        finally:
            await config.close()

    with pytest.raises(TypeError, match="unexpected keyword argument 'highlight'"):
        asyncio.run(run())

    assert "EncodeSavedEntity" not in transport.methods_called()


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


# -- labelled text and printing ---------------------------------------------

ENCODED_TOKENS = [
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_BLOCK_TYPE, text="app"),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" "),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_NAME_LABEL, text='"web"'),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" {\n  "),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_ATTRIBUTE, text="image"),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" = "),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_STRING, text='"nginx"'),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="\n}\n"),
]


def tokens_transport() -> FakeTransport:
    return FakeTransport(
        {
            "EncodeEntity": core_pb2.EncodeEntityResponse(text=ENCODED_TEXT, tokens=ENCODED_TOKENS),
            "EncodeSavedEntity": core_pb2.EncodeSavedEntityResponse(text=ENCODED_TEXT, tokens=ENCODED_TOKENS),
        }
    )


class RecordingFormatter:
    """A format of the user's own: records each call and writes each token as ``[kind]text``."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, object, list[Token]]] = []

    def format(self, out, theme, tokens) -> None:
        self.calls.append((out, theme, list(tokens)))
        for token in tokens:
            out.write(f"[{int(token.kind)}]{token.text}")


def test_encode_entity_does_not_ask_for_tokens():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_entity(hand_built_app())

    assert sent_encode_entity_request(transport).tokens is False


def test_encode_saved_entity_does_not_ask_for_tokens():
    transport = encode_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.encode_saved_entity(SAVED_RECORD)

    assert sent_encode_saved_entity_request(transport).tokens is False


def test_entity_tokens_asks_for_tokens():
    transport = tokens_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    tokens = config.entity_tokens(hand_built_app(), include_computed=True, show_references=True)

    request = sent_encode_entity_request(transport)
    assert request.tokens is True
    assert json.loads(request.entity) == {"meta": {"type": "app", "name": "web"}, "image": "nginx"}
    assert request.options.include_computed is True
    assert request.options.include_empty is False
    assert request.options.reveal_sensitive is False
    assert request.options.show_references is True
    assert tokens[0] == Token(kind=Kind.BLOCK_TYPE, text="app")
    assert tokens[4] == Token(kind=Kind.ATTRIBUTE, text="image")
    assert "".join(token.text for token in tokens) == 'app "web" {\n  image = "nginx"\n}\n'


def test_print_entity_formats_tokens():
    transport = tokens_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))
    out = io.StringIO()

    config.print_entity(hand_built_app(), out, reveal_sensitive=True)

    assert out.getvalue() == 'app "web" {\n  image = "nginx"\n}\n'
    request = sent_encode_entity_request(transport)
    assert request.tokens is True
    assert request.options.reveal_sensitive is True


def test_print_entity_defaults_to_stdout(capsys):
    transport = tokens_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config.print_entity(hand_built_app())

    assert capsys.readouterr().out == 'app "web" {\n  image = "nginx"\n}\n'


def test_print_entity_in_terminal_colour():
    transport = tokens_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))
    out = io.StringIO()

    config.print_entity(hand_built_app(), out, formatter=xcl.highlight.TERMINAL)

    assert out.getvalue().startswith("\x1b[1;35mapp\x1b[0m ")


def test_print_entity_gives_custom_format_whole_text_in_one_call():
    transport = tokens_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))
    out = io.StringIO()
    formatter = RecordingFormatter()
    theme = {Kind.ATTRIBUTE: "#ff8800"}

    config.print_entity(hand_built_app(), out, formatter=formatter, theme=theme)

    assert len(formatter.calls) == 1
    stream, given_theme, tokens = formatter.calls[0]
    assert stream is out
    assert given_theme is theme
    assert len(tokens) == 8
    assert out.getvalue().startswith('[101]app[0] [202]"web"')


def test_print_entity_not_an_entity_writes_nothing():
    transport = tokens_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))
    out = io.StringIO()

    with pytest.raises(xcl.NotEncodableError):
        config.print_entity(None, out)

    assert out.getvalue() == ""
    assert "EncodeEntity" not in transport.methods_called()


def test_saved_entity_tokens_asks_for_tokens():
    transport = tokens_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    tokens = config.saved_entity_tokens(SAVED_RECORD, include_empty=True)

    request = sent_encode_saved_entity_request(transport)
    assert request.tokens is True
    assert request.entity == SAVED_RECORD
    assert request.options.include_computed is False
    assert request.options.include_empty is True
    assert request.options.reveal_sensitive is False
    assert request.options.show_references is False
    assert tokens[2] == Token(kind=Kind.NAME_LABEL, text='"web"')


def test_print_saved_entity_formats_tokens():
    transport = tokens_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))
    out = io.StringIO()

    config.print_saved_entity(SAVED_RECORD, out, include_computed=True)

    assert out.getvalue() == 'app "web" {\n  image = "nginx"\n}\n'
    request = sent_encode_saved_entity_request(transport)
    assert request.tokens is True
    assert request.options.include_computed is True


def test_print_saved_entity_gives_custom_format_whole_text_in_one_call():
    transport = tokens_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))
    out = io.StringIO()
    formatter = RecordingFormatter()

    config.print_saved_entity(SAVED_RECORD, out, formatter=formatter)

    assert len(formatter.calls) == 1
    assert formatter.calls[0][0] is out
    assert len(formatter.calls[0][2]) == 8


def test_aio_print_entity_formats_tokens():
    transport = tokens_transport()
    out = io.StringIO()

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], client=Client(transport))
        try:
            await config.print_entity(hand_built_app(), out, include_computed=True)
        finally:
            await config.close()

    asyncio.run(run())

    assert out.getvalue() == 'app "web" {\n  image = "nginx"\n}\n'
    encode_calls = [call for call in transport.calls if call[1] == "EncodeEntity"]
    assert len(encode_calls) == 1
    request = core_pb2.EncodeEntityRequest.FromString(encode_calls[0][2])
    assert request.tokens is True
    assert request.options.include_computed is True


def test_aio_entity_tokens_asks_for_tokens():
    transport = tokens_transport()
    found: list[list[Token]] = []

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], client=Client(transport))
        try:
            found.append(await config.entity_tokens(hand_built_app()))
        finally:
            await config.close()

    asyncio.run(run())

    assert found[0][4] == Token(kind=Kind.ATTRIBUTE, text="image")
    encode_calls = [call for call in transport.calls if call[1] == "EncodeEntity"]
    assert core_pb2.EncodeEntityRequest.FromString(encode_calls[0][2]).tokens is True


def test_aio_print_saved_entity_formats_tokens():
    transport = tokens_transport()
    out = io.StringIO()

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], client=Client(transport))
        try:
            await config.print_saved_entity(SAVED_RECORD, out, show_references=True)
        finally:
            await config.close()

    asyncio.run(run())

    assert out.getvalue() == 'app "web" {\n  image = "nginx"\n}\n'
    encode_calls = [call for call in transport.calls if call[1] == "EncodeSavedEntity"]
    assert len(encode_calls) == 1
    request = core_pb2.EncodeSavedEntityRequest.FromString(encode_calls[0][2])
    assert request.tokens is True
    assert request.entity == SAVED_RECORD
    assert request.options.show_references is True


def test_aio_saved_entity_tokens_asks_for_tokens():
    transport = tokens_transport()
    found: list[list[Token]] = []

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], client=Client(transport))
        try:
            found.append(await config.saved_entity_tokens(SAVED_RECORD))
        finally:
            await config.close()

    asyncio.run(run())

    assert found[0][6] == Token(kind=Kind.STRING, text='"nginx"')
    encode_calls = [call for call in transport.calls if call[1] == "EncodeSavedEntity"]
    assert core_pb2.EncodeSavedEntityRequest.FromString(encode_calls[0][2]).tokens is True


# -- diffs keep their labelled text -----------------------------------------

DIFF_JSON = b'{"summary": {"create": 1}, "resources": [{"address": "resource.recording.one", "action": "create"}]}'

DIFF_TOKENS = [
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_INSERTED, text="+ resource.recording.one"),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="\n"),
]


def diff_transport() -> FakeTransport:
    return FakeTransport(
        {
            "StartDiff": core_pb2.StartOperationResponse(operation_id=3),
            "Poll": [
                core_pb2.PollResponse(
                    finished=core_pb2.OperationFinished(operation_id=3, diff_json=DIFF_JSON, diff_tokens=DIFF_TOKENS)
                ),
            ],
        }
    )


def test_finished_diff_keeps_its_tokens():
    config = xcl.Config(client=Client(diff_transport()))

    diff = config.diff("main.xcl")

    assert diff.summary.create == 1
    assert diff.tokens == (
        Token(kind=Kind.INSERTED, text="+ resource.recording.one"),
        Token(kind=Kind.TEXT, text="\n"),
    )


def test_aio_finished_diff_keeps_its_tokens():
    found: list[xcl.Diff] = []

    async def run() -> None:
        config = xcl.aio.Config(client=Client(diff_transport()))
        try:
            found.append(await config.diff("main.xcl"))
        finally:
            await config.close()

    asyncio.run(run())

    assert found[0].tokens == (
        Token(kind=Kind.INSERTED, text="+ resource.recording.one"),
        Token(kind=Kind.TEXT, text="\n"),
    )


def test_diff_tokens_take_no_part_in_equality():
    config = xcl.Config(client=Client(diff_transport()))
    diff = config.diff("main.xcl")

    assert diff == xcl.Diff(summary=diff.summary, resources=diff.resources)


# -- the private blocking render a handler uses --------------------------------


def test_saved_entity_tokens_now_asks_for_tokens():
    transport = tokens_transport()
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    tokens = config._saved_entity_tokens_now(SAVED_RECORD, include_computed=True)

    request = sent_encode_saved_entity_request(transport)
    assert request.tokens is True
    assert request.entity == SAVED_RECORD
    assert request.options.include_computed is True
    assert request.options.include_empty is False
    assert request.options.reveal_sensitive is False
    assert request.options.show_references is False
    assert tokens[2] == Token(kind=Kind.NAME_LABEL, text='"web"')


def test_saved_entity_tokens_now_runs_on_calling_thread():
    transport = ThreadRecordingTransport(tokens_transport().script)
    config = xcl.Config(registries=[app_registry()], client=Client(transport))

    config._saved_entity_tokens_now(SAVED_RECORD)

    assert transport.encode_threads == [threading.get_ident()]


class ThreadRecordingTransport(FakeTransport):
    """A fake transport that records the thread each EncodeSavedEntity call is made on."""

    def __init__(self, script) -> None:
        super().__init__(script)
        self.encode_threads: list[int] = []

    def call(self, handle, method, request):
        if method == "EncodeSavedEntity":
            self.encode_threads.append(threading.get_ident())
        return super().call(handle, method, request)


def test_aio_saved_entity_tokens_now_asks_for_tokens():
    transport = tokens_transport()
    tokens: list[Token] = []

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], client=Client(transport))
        try:
            await config.open()
            tokens.extend(config._saved_entity_tokens_now(SAVED_RECORD, include_computed=True))
        finally:
            await config.close()

    asyncio.run(run())

    encode_calls = [call for call in transport.calls if call[1] == "EncodeSavedEntity"]
    assert len(encode_calls) == 1
    handle, _, body = encode_calls[0]
    request = core_pb2.EncodeSavedEntityRequest.FromString(body)
    assert handle == 7
    assert request.tokens is True
    assert request.entity == SAVED_RECORD
    assert request.options.include_computed is True
    assert tokens[2] == Token(kind=Kind.NAME_LABEL, text='"web"')


def test_aio_saved_entity_tokens_now_calls_on_calling_thread():
    transport = ThreadRecordingTransport(tokens_transport().script)
    caller_threads: list[int] = []

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], client=Client(transport))
        try:
            await config.open()

            def render() -> None:
                caller_threads.append(threading.get_ident())
                config._saved_entity_tokens_now(SAVED_RECORD)

            # a plain on_event handler runs on the default executor, so the
            # render is made from one of its threads
            await asyncio.get_running_loop().run_in_executor(None, render)
        finally:
            await config.close()

    asyncio.run(run())

    assert transport.encode_threads == caller_threads


def test_aio_saved_entity_tokens_now_refuses_before_open():
    config = xcl.aio.Config(registries=[app_registry()], client=Client(tokens_transport()))

    with pytest.raises(RuntimeError, match="not open"):
        config._saved_entity_tokens_now(SAVED_RECORD)


def test_config_remembers_event_data_level():
    config = xcl.Config(event_data=xcl.EventDataLevel.PROCESSED, client=Client(FakeTransport()))

    assert config._event_data is xcl.EventDataLevel.PROCESSED


def test_config_remembers_default_event_data_level():
    config = xcl.Config(client=Client(FakeTransport()))

    assert config._event_data is xcl.EventDataLevel.NONE


def test_aio_config_remembers_event_data_level():
    config = xcl.aio.Config(event_data=xcl.EventDataLevel.RAW, client=Client(FakeTransport()))

    assert config._event_data is xcl.EventDataLevel.RAW


def test_aio_config_remembers_default_event_data_level():
    config = xcl.aio.Config(client=Client(FakeTransport()))

    assert config._event_data is xcl.EventDataLevel.NONE
