"""Events: their entity, hydrated through the emitting configuration's classes."""

import asyncio
import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone

import xcl
import xcl.aio
from xcl import Meta
from xcl._classes import ClassMap
from xcl._client import Client
from xcl._core import core_pb2
from xcl.events import Event
from fakes import FakeTransport


@dataclass
class App:
    image: str
    meta: Meta | None = None


@dataclass
class OtherApp:
    image: str
    meta: Meta | None = None


APP_JSON = b'{"meta": {"id": "app.web", "name": "web", "type": "app", "subtype": ""}, "image": "nginx"}'
CACHE_JSON = b'{"meta": {"id": "cache.redis", "name": "redis", "type": "cache", "subtype": ""}, "size": 64}'


def app_classes() -> ClassMap:
    registry = xcl.LocalRegistry()
    registry.register_type(App, "app")
    return ClassMap.from_registries([registry])


def other_app_classes() -> ClassMap:
    registry = xcl.LocalRegistry()
    registry.register_type(OtherApp, "app")
    return ClassMap.from_registries([registry])


def event_proto(data: bytes) -> core_pb2.Event:
    return core_pb2.Event(
        time_unix_nano=1_700_000_000_000_000_000,
        source="core",
        operation="apply",
        phase="success",
        resource_type="app",
        resource_id="app.web",
        file="main.hcl",
        duration_nano=2_000_000,
        data=data,
        meta_json=b'{"level": "info", "message": "created"}',
    )


# -- entity() ------------------------------------------------------------------


def test_entity_is_the_class_registered_on_the_map():
    event = Event._from_proto(event_proto(APP_JSON), app_classes())

    entity = event.entity()

    assert type(entity) is App
    assert entity.image == "nginx"
    assert entity.meta.address == "app.web"
    assert entity.meta.name == "web"
    assert entity.meta.type == "app"


def test_entity_of_type_not_on_the_map_is_generic_entity():
    event = Event._from_proto(event_proto(CACHE_JSON), app_classes())

    entity = event.entity()

    assert type(entity) is xcl.Entity
    assert entity.address == "cache.redis"


def test_entity_of_event_built_by_hand_is_generic_entity():
    event = Event(
        time=datetime.fromtimestamp(0, tz=timezone.utc),
        source="core",
        operation="apply",
        phase="success",
        data=APP_JSON,
    )

    entity = event.entity()

    assert type(entity) is xcl.Entity
    assert entity.address == "app.web"


def test_entity_of_event_without_data_is_none():
    event = Event._from_proto(event_proto(b""), app_classes())

    assert event.entity() is None


def test_entities_of_events_from_different_maps_are_their_own_classes():
    first = Event._from_proto(event_proto(APP_JSON), app_classes())
    second = Event._from_proto(event_proto(APP_JSON), other_app_classes())

    assert type(first.entity()) is App
    assert type(second.entity()) is OtherApp


# -- equality, repr and fields -------------------------------------------------


def test_events_from_the_same_proto_with_different_maps_are_equal():
    first = Event._from_proto(event_proto(APP_JSON), app_classes())
    second = Event._from_proto(event_proto(APP_JSON), other_app_classes())

    assert first == second


def test_repr_does_not_mention_the_class_map():
    event = Event._from_proto(event_proto(APP_JSON), app_classes())

    text = repr(event)

    assert "_classes" not in text
    assert "ClassMap" not in text


def test_fields_are_exactly_the_public_fields():
    names = [field.name for field in dataclasses.fields(Event)]

    assert names == [
        "time",
        "source",
        "operation",
        "phase",
        "resource_type",
        "resource_id",
        "file",
        "duration",
        "error",
        "data",
        "meta",
    ]


# -- delivered by a configuration -------------------------------------------------


def apply_transport(data: bytes) -> FakeTransport:
    return FakeTransport(
        {
            "StartApply": core_pb2.StartOperationResponse(operation_id=3),
            "Poll": [
                core_pb2.PollResponse(event=event_proto(data)),
                core_pb2.PollResponse(finished=core_pb2.OperationFinished(operation_id=3)),
            ],
        }
    )


def app_registry() -> xcl.LocalRegistry:
    registry = xcl.LocalRegistry()
    registry.register_type(App, "app")
    return registry


def test_sync_config_delivers_event_entity_as_registered_class():
    received: list[Event] = []
    config = xcl.Config(registries=[app_registry()], on_event=received.append, client=Client(apply_transport(APP_JSON)))

    config.apply("main.hcl")

    assert len(received) == 1
    entity = received[0].entity()
    assert type(entity) is App
    assert entity.image == "nginx"
    assert entity.meta.address == "app.web"


def test_sync_config_delivers_event_entity_of_unregistered_type_as_generic_entity():
    received: list[Event] = []
    config = xcl.Config(registries=[app_registry()], on_event=received.append, client=Client(apply_transport(CACHE_JSON)))

    config.apply("main.hcl")

    assert len(received) == 1
    assert type(received[0].entity()) is xcl.Entity


def test_asyncio_config_delivers_event_entity_as_registered_class():
    received: list[Event] = []

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], on_event=received.append, client=Client(apply_transport(APP_JSON)))
        try:
            await config.apply("main.hcl")
        finally:
            await config.close()

    asyncio.run(run())

    assert len(received) == 1
    entity = received[0].entity()
    assert type(entity) is App
    assert entity.image == "nginx"
    assert entity.meta.address == "app.web"


def test_asyncio_config_delivers_event_entity_of_unregistered_type_as_generic_entity():
    received: list[Event] = []

    async def run() -> None:
        config = xcl.aio.Config(registries=[app_registry()], on_event=received.append, client=Client(apply_transport(CACHE_JSON)))
        try:
            await config.apply("main.hcl")
        finally:
            await config.close()

    asyncio.run(run())

    assert len(received) == 1
    assert type(received[0].entity()) is xcl.Entity
