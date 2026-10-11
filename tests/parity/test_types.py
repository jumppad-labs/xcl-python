"""The Python classes in ``types.py`` derive exactly each fixture's ``types.json`` documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xcl._schema import schema_for

from parity import types as fixture_types
from parity.conftest import FIXTURES


def _documents(fixture: str) -> list[dict[str, Any]]:
    path = FIXTURES / fixture / "types.json"
    assert path.is_file(), f"no types.json for the parity fixture {fixture} at {path}"
    return json.loads(Path(path).read_text())


def _derived(fixture: str) -> list[dict[str, Any]]:
    return [schema_for(cls) for cls in fixture_types.register(fixture)]


def test_basic_types_types_match_fixture(xcl_src):
    assert _derived("basic_types") == _documents("basic_types")


def test_annotations_types_match_fixture(xcl_src):
    assert _derived("annotations") == _documents("annotations")


def test_functions_types_match_fixture(xcl_src):
    assert _derived("functions") == _documents("functions")


def test_variables_types_match_fixture(xcl_src):
    assert _derived("variables") == _documents("variables")


def test_outputs_types_match_fixture(xcl_src):
    assert _derived("outputs") == _documents("outputs")


def test_plugin_entities_types_match_fixture(xcl_src):
    assert _derived("plugin_entities") == _documents("plugin_entities")


def test_invalid_types_match_fixture(xcl_src):
    assert _derived("invalid") == _documents("invalid")
