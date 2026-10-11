"""Deriving the schema v1 document from a dataclass's annotations."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

from xcl import Computed, Resource, SchemaError, Sensitive, entity, field
from xcl._schema import schema_for

PARITY_TYPES = (
    Path(__file__).resolve().parents[3] / "xcl" / "bindings" / "libxcl" / "testdata" / "parity" / "annotations" / "types.json"
)


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


@entity("app")
@dataclass
class App(Resource):
    image: str
    replicas: int = 2
    region: str = "eu"
    password: Sensitive[str] | None = None
    endpoint: Computed[str] = None
    health: Health | None = None
    volume: list[Volume] = field(default_factory=list)
    listener: dict[str, Listener] = field(default_factory=dict)


def _only_field(cls: type) -> dict[str, Any]:
    fields = schema_for(cls, type_name="t")["fields"]
    assert len(fields) == 1
    return fields[0]


def test_annotations_dataclass_matches_parity_fixture():
    documents = json.loads(PARITY_TYPES.read_text())

    assert schema_for(App) == documents[0]


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


def test_base_fields_not_listed():
    @dataclass
    class Block(Resource):
        image: str

    names = [f["name"] for f in schema_for(Block, type_name="t")["fields"]]

    assert names == ["image"]


def test_non_dataclass_is_refused():
    class Plain:
        image: str

    with pytest.raises(SchemaError, match="Plain"):
        schema_for(Plain)


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


def test_type_and_subtype_in_document():
    @dataclass
    class Database(Resource):
        version: str

    doc = schema_for(Database, type_name="database", subtype="postgres")

    assert doc["schema_version"] == 1
    assert doc["type"] == "database"
    assert doc["subtype"] == "postgres"
    assert doc["fields"] == [{"name": "version", "type": "string"}]
