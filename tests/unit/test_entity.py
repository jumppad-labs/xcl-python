"""The entity decorator, its registry, Meta and the Resource base."""

from dataclasses import dataclass

import pytest

from xcl import Meta, Resource, SchemaError, entity
from xcl._entity import registered_class, registration_of, schema_of


def test_entity_decorator_registers_class():
    @entity("entity_app")
    @dataclass
    class EntityApp(Resource):
        image: str

    assert registered_class("entity_app") is EntityApp
    assert schema_of(EntityApp) == {
        "schema_version": 1,
        "type": "entity_app",
        "fields": [{"name": "image", "type": "string"}],
    }


def test_entity_decorator_records_type_and_subtype():
    @entity("entity_database", "postgres")
    @dataclass
    class EntityDatabase(Resource):
        version: str

    assert registration_of(EntityDatabase) == ("entity_database", "postgres")
    assert EntityDatabase.__xcl_type__ == "entity_database"
    assert EntityDatabase.__xcl_subtype__ == "postgres"
    assert registered_class("entity_database", "postgres") is EntityDatabase
    assert schema_of(EntityDatabase)["type"] == "entity_database"
    assert schema_of(EntityDatabase)["subtype"] == "postgres"


def test_entity_decorator_without_subtype_records_empty_subtype():
    @entity("entity_cache")
    @dataclass
    class EntityCache(Resource):
        size: int

    assert registration_of(EntityCache) == ("entity_cache", "")
    assert "subtype" not in schema_of(EntityCache)


def test_entity_decorator_refuses_non_dataclass():
    class EntityPlain:
        image: str

    with pytest.raises(SchemaError, match="EntityPlain"):
        entity("entity_plain")(EntityPlain)


def test_entity_decorator_refuses_bad_annotation_naming_field():
    @dataclass
    class EntityBad(Resource):
        tags: set[str]

    with pytest.raises(SchemaError, match="EntityBad.tags"):
        entity("entity_bad")(EntityBad)


def test_entity_decorator_refuses_empty_type():
    with pytest.raises(SchemaError):
        entity("")


def test_registration_of_unregistered_raises():
    @dataclass
    class Unregistered(Resource):
        image: str

    with pytest.raises(SchemaError, match="Unregistered"):
        registration_of(Unregistered)


def test_registered_class_unknown_type_is_none():
    assert registered_class("entity_never_registered") is None


def test_meta_from_json_keeps_extra():
    meta = Meta.from_json(
        {"id": "app.web", "name": "web", "type": "app", "line": 2, "column": 1, "generation": 7, "labels": ["x"]}
    )

    assert meta.id == "app.web"
    assert meta.address == "app.web"
    assert meta.name == "web"
    assert meta.type == "app"
    assert meta.subtype == ""
    assert meta.line == 2
    assert meta.column == 1
    assert meta.extra == {"generation": 7, "labels": ["x"]}


def test_resource_address_before_apply_is_empty():
    @dataclass
    class EntityPending(Resource):
        image: str

    pending = EntityPending(image="nginx")

    assert pending.meta is None
    assert pending.address == ""
    assert pending.depends_on == []
    assert pending.disabled is False


def test_resource_address_is_meta_id():
    @dataclass
    class EntityApplied(Resource):
        image: str

    applied = EntityApplied(image="nginx", meta=Meta(id="entity_applied.web"))

    assert applied.address == "entity_applied.web"


def test_entity_decorator_refuses_resource_subclass_without_dataclass():
    class EntityForgotDataclass(Resource):
        image: str

    with pytest.raises(SchemaError, match="EntityForgotDataclass"):
        entity("entity_forgot_dataclass")(EntityForgotDataclass)
