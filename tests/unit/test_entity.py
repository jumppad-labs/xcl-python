"""Meta, and the names removed from the package in favour of plain dataclasses."""

import pytest

import xcl
from xcl import Meta, RemovedNameError


def test_meta_from_entity_keeps_extra():
    meta = Meta.from_entity(
        {"meta": {"id": "app.web", "name": "web", "type": "app", "line": 2, "column": 1, "generation": 7, "labels": ["x"]}}
    )

    assert meta.id == "app.web"
    assert meta.name == "web"
    assert meta.type == "app"
    assert meta.subtype == ""
    assert meta.line == 2
    assert meta.column == 1
    assert meta.extra == {"generation": 7, "labels": ["x"]}
    assert meta.disabled is False
    assert meta.depends_on == []


def test_meta_from_entity_reads_disabled_and_depends_on_beside_meta():
    meta = Meta.from_entity(
        {"meta": {"id": "app.web"}, "disabled": True, "depends_on": ["app.base"], "image": "nginx"}
    )

    assert meta.disabled is True
    assert meta.depends_on == ["app.base"]
    assert meta.extra == {}


def test_meta_to_record_round_trips_from_entity():
    record = {
        "id": "app.web",
        "name": "web",
        "type": "app",
        "subtype": "container",
        "module": "db",
        "file": "/f",
        "line": 2,
        "column": 1,
        "status": "created",
        "links": ["app.base"],
        "references": {"base": "app.base"},
        "generation": 7,
    }

    meta = Meta.from_entity({"meta": record})

    assert meta.to_record() == record


def test_meta_to_record_omits_empty_keys():
    meta = Meta(id="app.web", name="web")

    assert meta.to_record() == {"id": "app.web", "name": "web"}


def test_meta_to_record_leaves_out_disabled_and_depends_on():
    meta = Meta(id="app.web", disabled=True, depends_on=["app.base"])

    assert meta.to_record() == {"id": "app.web"}


def test_resource_attribute_raises_removed_name_error_naming_register_type():
    with pytest.raises(RemovedNameError, match="register_type"):
        xcl.Resource


def test_entity_attribute_raises_removed_name_error_naming_register_type():
    with pytest.raises(RemovedNameError, match="register_type"):
        xcl.entity


def test_from_xcl_import_resource_raises_removed_name_error_naming_register_type():
    with pytest.raises(RemovedNameError, match="register_type"):
        from xcl import Resource  # noqa: F401


def test_from_xcl_import_entity_raises_removed_name_error_naming_register_type():
    with pytest.raises(RemovedNameError, match="register_type"):
        from xcl import entity  # noqa: F401


def test_removed_name_message_says_resource_was_removed():
    with pytest.raises(RemovedNameError) as raised:
        xcl.Resource

    assert "xcl.Resource has been removed" in str(raised.value)


def test_removed_name_message_points_to_readme_migration_section():
    with pytest.raises(RemovedNameError) as raised:
        xcl.entity

    assert "Migrating from xcl.Resource and @xcl.entity" in str(raised.value)


def test_removed_name_error_is_an_xcl_error():
    with pytest.raises(RemovedNameError) as raised:
        xcl.Resource

    assert isinstance(raised.value, xcl.Error)


def test_removed_name_error_is_an_import_error():
    with pytest.raises(RemovedNameError) as raised:
        xcl.Resource

    assert isinstance(raised.value, ImportError)


def test_removed_name_error_has_removed_name_code():
    with pytest.raises(RemovedNameError) as raised:
        xcl.Resource

    assert raised.value.code == "removed_name"


def test_removed_name_error_name_is_resource():
    with pytest.raises(RemovedNameError) as raised:
        xcl.Resource

    assert raised.value.name == "Resource"


def test_removed_name_error_name_is_entity():
    with pytest.raises(RemovedNameError) as raised:
        xcl.entity

    assert raised.value.name == "entity"


def test_removed_name_error_details_carry_the_name():
    with pytest.raises(RemovedNameError) as raised:
        xcl.entity

    assert raised.value.details == {"name": "entity"}


def test_unknown_attribute_raises_attribute_error():
    with pytest.raises(AttributeError, match="module 'xcl' has no attribute 'not_a_name'"):
        xcl.not_a_name


def test_unknown_attribute_is_not_a_removed_name_error():
    with pytest.raises(AttributeError) as raised:
        xcl.not_a_name

    assert not isinstance(raised.value, RemovedNameError)


def test_resource_is_not_exported():
    assert "Resource" not in xcl.__all__


def test_entity_decorator_is_not_exported():
    assert "entity" not in xcl.__all__


def test_removed_name_error_is_exported():
    assert "RemovedNameError" in xcl.__all__


def test_entity_module_keeps_no_process_wide_class_registry():
    import xcl._entity

    assert not hasattr(xcl._entity, "_registry")
    assert not hasattr(xcl._entity, "registered_class")
    assert not hasattr(xcl._entity, "registered_classes")
    assert not hasattr(xcl._entity, "registration_of")
    assert not hasattr(xcl._entity, "schema_of")
