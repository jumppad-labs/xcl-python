"""Deriving a function signature document from a Python function's annotations."""

import pytest

from xcl import SchemaError
from xcl._schema import signature_for


def test_signature_str_to_str():
    def upper(title: str) -> str:
        return title.upper()

    assert signature_for(upper) == {"params": [{"name": "title", "type": "string"}], "return": "string"}


def test_signature_numbers_and_bool():
    def compare(count: int, ratio: float, strict: bool) -> bool:
        return strict

    assert signature_for(compare) == {
        "params": [
            {"name": "count", "type": "number"},
            {"name": "ratio", "type": "number"},
            {"name": "strict", "type": "bool"},
        ],
        "return": "bool",
    }


def test_signature_list_and_map():
    def pick(names: list[str], counts: dict[str, int]) -> list[str]:
        return names

    assert signature_for(pick) == {
        "params": [
            {"name": "names", "type": ["list", "string"]},
            {"name": "counts", "type": ["map", "number"]},
        ],
        "return": ["list", "string"],
    }


def test_signature_variadic_args():
    def join(*args: str) -> str:
        return "".join(args)

    assert signature_for(join) == {
        "params": [],
        "return": "string",
        "variadic": {"name": "args", "type": "string"},
    }


def test_signature_missing_param_annotation_refused():
    def unannotated(title) -> str:
        return title

    with pytest.raises(SchemaError, match="unannotated"):
        signature_for(unannotated)


def test_signature_missing_return_refused():
    def no_return(title: str):
        return title

    with pytest.raises(SchemaError, match="no_return"):
        signature_for(no_return)


def test_signature_keyword_only_refused():
    def keyword_only(*, title: str) -> str:
        return title

    with pytest.raises(SchemaError, match="keyword_only"):
        signature_for(keyword_only)


def test_signature_rejects_object_param():
    def takes_object(value: object) -> str:
        return str(value)

    with pytest.raises(SchemaError, match="takes_object"):
        signature_for(takes_object)
