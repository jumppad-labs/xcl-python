"""Deriving the schema v1 document from a dataclass's annotations."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

from xcl import Computed, Meta, SchemaError, Sensitive, field
from xcl._schema import schema_for

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


def _only_field(cls: type) -> dict[str, Any]:
    fields = schema_for(cls, type_name="t")["fields"]
    assert len(fields) == 1
    return fields[0]


def test_annotations_dataclass_matches_parity_fixture(xcl_src: Path):
    parity_types = xcl_src / "bindings" / "libxcl" / "testdata" / "parity" / "annotations" / "types.json"
    documents = json.loads(parity_types.read_text())

    assert schema_for(App, type_name="app") == documents[0]


def test_str_is_string():
    @dataclass
    class Block:
        image: str

    assert _only_field(Block) == {"name": "image", "type": "string"}


def test_int_is_number_int():
    @dataclass
    class Block:
        replicas: int

    assert _only_field(Block) == {"name": "replicas", "type": "number", "format": "int"}


def test_float_is_number_float():
    @dataclass
    class Block:
        ratio: float

    assert _only_field(Block) == {"name": "ratio", "type": "number", "format": "float"}


def test_bool_is_bool():
    @dataclass
    class Block:
        enabled: bool

    assert _only_field(Block) == {"name": "enabled", "type": "bool"}


def test_any_is_any():
    @dataclass
    class Block:
        payload: Any

    assert _only_field(Block) == {"name": "payload", "type": "any"}


def test_list_of_str_is_list():
    @dataclass
    class Block:
        tags: list[str]

    assert _only_field(Block) == {"name": "tags", "type": {"list": "string"}}


def test_dict_of_int_is_map():
    @dataclass
    class Block:
        counts: dict[str, int]

    assert _only_field(Block) == {"name": "counts", "type": {"map": "number"}, "format": "int"}


def test_optional_union_none_is_optional():
    @dataclass
    class Block:
        region: str | None

    assert _only_field(Block) == {"name": "region", "type": "string", "optional": True}


def test_default_becomes_default():
    @dataclass
    class Block:
        replicas: int = 2

    assert _only_field(Block) == {"name": "replicas", "type": "number", "format": "int", "optional": True, "default": 2}


def test_none_default_is_optional_without_default():
    @dataclass
    class Block:
        region: Optional[str] = None

    doc = _only_field(Block)

    assert doc == {"name": "region", "type": "string", "optional": True}
    assert "default" not in doc


def test_sensitive_str_sets_sensitive():
    @dataclass
    class Block:
        password: Sensitive[str]

    assert _only_field(Block) == {"name": "password", "type": "string", "sensitive": True}


def test_sensitive_list_of_str_allowed():
    @dataclass
    class Block:
        keys: Sensitive[list[str]]

    assert _only_field(Block) == {"name": "keys", "type": {"list": "string"}, "sensitive": True}


def test_sensitive_list_of_int_is_refused():
    @dataclass
    class Block:
        pins: Sensitive[list[int]]

    with pytest.raises(SchemaError, match="Block.pins"):
        schema_for(Block, type_name="t")


def test_computed_is_computed_without_optional():
    @dataclass
    class Block:
        endpoint: Computed[str] = None

    doc = _only_field(Block)

    assert doc == {"name": "endpoint", "type": "string", "computed": True}
    assert "optional" not in doc


def test_dataclass_field_is_block():
    @dataclass
    class Block:
        health: Health

    assert _only_field(Block) == {
        "name": "health",
        "kind": "block",
        "type": {"object": [{"name": "path", "type": "string"}]},
    }


def test_optional_dataclass_is_optional_block():
    @dataclass
    class Block:
        health: Health | None = None

    assert _only_field(Block) == {
        "name": "health",
        "kind": "block",
        "type": {"object": [{"name": "path", "type": "string"}]},
        "optional": True,
    }


def test_dataclass_with_block_false_is_object_attribute():
    @dataclass
    class Block:
        health: Health = field(block=False)

    doc = _only_field(Block)

    assert doc == {"name": "health", "type": {"object": [{"name": "path", "type": "string"}]}}
    assert "kind" not in doc


def test_list_of_dataclass_is_repeated_block():
    @dataclass
    class Check:
        path: str

    @dataclass
    class Block:
        check: list[Check]

    assert _only_field(Block) == {
        "name": "check",
        "kind": "block",
        "type": {"object": [{"name": "path", "type": "string"}]},
        "repeated": True,
    }


def test_dict_of_dataclass_is_named_block_map():
    @dataclass
    class Port:
        number: int

    @dataclass
    class Block:
        port: dict[str, Port]

    assert _only_field(Block) == {
        "name": "port",
        "kind": "block",
        "type": {"map": {"object": [{"name": "number", "type": "number", "format": "int"}]}},
    }


def test_label_field_names_label_and_is_excluded():
    @dataclass
    class Block:
        volume: list[Volume]

    doc = _only_field(Block)

    assert doc["label"] == "name"
    assert doc["type"] == {"object": [{"name": "source", "type": "string"}]}


def test_field_name_override():
    @dataclass
    class Block:
        image_name: str = field(name="image")

    assert _only_field(Block) == {"name": "image", "type": "string"}


def test_meta_not_listed():
    @dataclass
    class Block:
        image: str
        meta: Meta | None = None

    names = [f["name"] for f in schema_for(Block, type_name="t")["fields"]]

    assert names == ["image"]


def test_non_dataclass_is_refused():
    class Plain:
        image: str

    with pytest.raises(SchemaError, match="Plain"):
        schema_for(Plain, type_name="t")


def test_set_field_is_refused_naming_field():
    @dataclass
    class Block:
        tags: set[str]

    with pytest.raises(SchemaError, match="Block.tags"):
        schema_for(Block, type_name="t")


def test_tuple_field_is_refused_naming_field():
    @dataclass
    class Block:
        pair: tuple[str, str]

    with pytest.raises(SchemaError, match="Block.pair"):
        schema_for(Block, type_name="t")


def test_union_of_two_types_is_refused():
    @dataclass
    class Block:
        value: str | int

    with pytest.raises(SchemaError, match="Block.value"):
        schema_for(Block, type_name="t")


def test_non_string_map_key_is_refused():
    @dataclass
    class Block:
        by_number: dict[int, str]

    with pytest.raises(SchemaError, match="Block.by_number"):
        schema_for(Block, type_name="t")


def test_dataclass_without_meta_or_label_is_singleton():
    @dataclass
    class Runner:
        server: str

    doc = schema_for(Runner, type_name="runner")

    assert doc["singleton"] is True
    assert doc["fields"] == [{"name": "server", "type": "string"}]


def test_dataclass_with_meta_is_not_singleton():
    @dataclass
    class Agent:
        model: str
        meta: Meta | None = None

    assert "singleton" not in schema_for(Agent, type_name="agent")


def test_dataclass_with_label_field_is_not_singleton():
    @dataclass
    class Agent:
        model: str
        handle: str = field(label=True, default="")

    doc = schema_for(Agent, type_name="agent")

    assert "singleton" not in doc
    assert doc["fields"] == [{"name": "model", "type": "string"}]


def test_singleton_with_subtype_is_refused():
    @dataclass
    class Runner:
        server: str

    with pytest.raises(SchemaError, match="takes no subtype"):
        schema_for(Runner, type_name="runner", subtype="big")


def test_label_fields_must_match_the_labels():
    @dataclass
    class Agent:
        model: str
        kind: str = field(label=True, default="")
        handle: str = field(label=True, default="")

    with pytest.raises(SchemaError, match="2 label fields, a block of its type has 1 labels"):
        schema_for(Agent, type_name="agent")


def test_type_and_subtype_in_document():
    @dataclass
    class Database:
        version: str
        meta: Meta | None = None

    doc = schema_for(Database, type_name="database", subtype="postgres")

    assert doc["schema_version"] == 1
    assert doc["type"] == "database"
    assert doc["subtype"] == "postgres"
    assert doc["fields"] == [{"name": "version", "type": "string"}]


def test_top_level_meta_is_not_listed():
    @dataclass
    class Block:
        image: str
        meta: Meta | None = None

    names = [f["name"] for f in schema_for(Block, type_name="t")["fields"]]

    assert names == ["image"]


def test_top_level_meta_typed_meta_without_none_is_not_listed():
    @dataclass
    class Block:
        image: str
        meta: Meta = None

    names = [f["name"] for f in schema_for(Block, type_name="t")["fields"]]

    assert names == ["image"]


def test_top_level_disabled_is_refused():
    @dataclass
    class Block:
        image: str
        disabled: bool = False

    with pytest.raises(SchemaError, match=r"Block\.disabled.*\"disabled\" is held by every block.*reads it from meta"):
        schema_for(Block, type_name="t")


def test_top_level_depends_on_is_refused():
    @dataclass
    class Block:
        image: str
        depends_on: list[str] = field(default_factory=list)

    with pytest.raises(SchemaError, match=r"Block\.depends_on.*\"depends_on\" is held by every block.*reads it from meta"):
        schema_for(Block, type_name="t")


def test_field_renamed_to_disabled_is_refused():
    @dataclass
    class Block:
        image: str
        is_off: bool = field(name="disabled", default=False)

    with pytest.raises(SchemaError, match=r"Block\.is_off.*\"disabled\" is held by every block"):
        schema_for(Block, type_name="t")


def test_field_renamed_to_depends_on_is_refused():
    @dataclass
    class Block:
        image: str
        after: list[str] = field(name="depends_on", default_factory=list)

    with pytest.raises(SchemaError, match=r"Block\.after.*\"depends_on\" is held by every block"):
        schema_for(Block, type_name="t")


def test_nested_block_lists_base_field_names_as_ordinary_fields():
    @dataclass
    class Inner:
        meta: str
        disabled: str
        depends_on: int

    @dataclass
    class Block:
        inner: Inner

    assert _only_field(Block) == {
        "name": "inner",
        "kind": "block",
        "type": {
            "object": [
                {"name": "meta", "type": "string"},
                {"name": "disabled", "type": "string"},
                {"name": "depends_on", "type": "number", "format": "int"},
            ]
        },
    }


def test_top_level_meta_of_wrong_type_is_refused():
    @dataclass
    class Block:
        meta: str = ""

    with pytest.raises(SchemaError, match=r"Block\.meta.*must be an xcl\.Meta \| None"):
        schema_for(Block, type_name="t")


def test_field_renamed_to_meta_is_refused():
    @dataclass
    class Block:
        info: str = field(name="meta", default="")

    with pytest.raises(SchemaError, match=r"Block\.info.*\"meta\" is held by every block"):
        schema_for(Block, type_name="t")


def test_meta_given_a_configuration_name_is_refused():
    @dataclass
    class Block:
        meta: Meta | None = field(name="info", default=None)

    with pytest.raises(SchemaError, match=r"Block\.meta.*takes no configuration name"):
        schema_for(Block, type_name="t")


def test_schema_has_no_subtype_key_when_subtype_is_absent():
    @dataclass
    class Block:
        image: str

    doc = schema_for(Block, type_name="app")

    assert doc["type"] == "app"
    assert "subtype" not in doc
