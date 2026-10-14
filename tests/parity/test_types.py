"""The Python classes in ``types.py`` derive exactly each fixture's ``types.json`` documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xcl._schema import schema_for

from parity import types as fixture_types


def _documents(fixtures: Path, fixture: str) -> list[dict[str, Any]]:
    path = fixtures / fixture / "types.json"
    assert path.is_file(), f"no types.json for the parity fixture {fixture} at {path}"
    return json.loads(Path(path).read_text())


def _derived(fixture: str) -> list[dict[str, Any]]:
    return [
        schema_for(cls, type_name=type_name, subtype=subtype)
        for type_name, subtype, cls in fixture_types.FIXTURES[fixture]
    ]


def test_basic_types_types_match_fixture(parity_fixtures):
    assert _derived("basic_types") == _documents(parity_fixtures, "basic_types")


def test_annotations_types_match_fixture(parity_fixtures):
    assert _derived("annotations") == _documents(parity_fixtures, "annotations")


def test_functions_types_match_fixture(parity_fixtures):
    assert _derived("functions") == _documents(parity_fixtures, "functions")


def test_variables_types_match_fixture(parity_fixtures):
    assert _derived("variables") == _documents(parity_fixtures, "variables")


def test_outputs_types_match_fixture(parity_fixtures):
    assert _derived("outputs") == _documents(parity_fixtures, "outputs")


def test_plugin_entities_types_match_fixture(parity_fixtures):
    assert _derived("plugin_entities") == _documents(parity_fixtures, "plugin_entities")


def test_invalid_types_match_fixture(parity_fixtures):
    assert _derived("invalid") == _documents(parity_fixtures, "invalid")
