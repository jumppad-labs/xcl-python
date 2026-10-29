"""The Go and Python parity programs produce the same record for every fixture.

Each test runs ``cmd/parity`` from the xcl checkout and ``run_python.py``
on one fixture, both as subprocesses, decodes the two records and fails
naming the fixture and the first JSON path where they differ.
"""

from __future__ import annotations

import os
from typing import Any, Optional

Difference = tuple[str, Any, Any]


def first_difference(a: Any, b: Any, path: str = "") -> Optional[Difference]:
    """The first path at which two decoded JSON values differ, with both values, or ``None``.

    Dicts are walked by sorted key, lists by index; a key missing on one
    side, a list of another length, or a leaf that differs, is the
    difference. Booleans never equal numbers, as they would in Python.
    """
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            here = f"{path}.{key}" if path else key
            if key not in a:
                return here, "<missing>", b[key]
            if key not in b:
                return here, a[key], "<missing>"
            found = first_difference(a[key], b[key], here)
            if found is not None:
                return found
        return None

    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return path or "<root>", f"list of {len(a)}", f"list of {len(b)}"
        for index, (left, right) in enumerate(zip(a, b)):
            found = first_difference(left, right, f"{path}[{index}]")
            if found is not None:
                return found
        return None

    if isinstance(a, bool) != isinstance(b, bool) or a != b:
        return path or "<root>", a, b

    return None


def assert_same_record(name: str, go: dict[str, Any], python: dict[str, Any]) -> None:
    found = first_difference(go, python)
    if found is not None:
        path, left, right = found
        raise AssertionError(f"fixture {name}: the records differ at {path}: go={left!r} python={right!r}")


def test_parity_basic_types(run_parity):
    go, python = run_parity("basic_types")

    assert_same_record("basic_types", go, python)


def test_parity_annotations(run_parity):
    go, python = run_parity("annotations")

    assert_same_record("annotations", go, python)


def test_parity_functions(run_parity):
    go, python = run_parity("functions")

    assert_same_record("functions", go, python)


def test_parity_variables(run_parity):
    go, python = run_parity("variables")

    assert_same_record("variables", go, python)


def test_parity_outputs(run_parity):
    go, python = run_parity("outputs")

    assert_same_record("outputs", go, python)


def test_parity_plugin_entities(run_parity):
    go, python = run_parity("plugin_entities")

    assert_same_record("plugin_entities", go, python)


def test_parity_invalid(run_parity):
    go, python = run_parity("invalid")

    assert_same_record("invalid", go, python)


def test_parity_singletons(run_parity):
    go, python = run_parity("singletons")

    assert_same_record("singletons", go, python)


def test_parity_encode(run_parity):
    go, python = run_parity("encode")

    assert_same_record("encode", go, python)


def test_parity_unsupported_block(run_parity):
    go, python = run_parity("unsupported_block")

    assert_same_record("unsupported_block", go, python)


def test_parity_unsupported_block_report_is_byte_for_byte(run_parity):
    go, python = run_parity("unsupported_block")

    assert python["printed_apply"] == go["printed_apply"]
    # the engine names the file with the platform's separator
    assert f"  on <fixture>{os.sep}main.xcl line 7, in app.api, field timeout[0]:\n" in python["printed_apply"]


def test_parity_plugin_entities_printing_and_log(run_parity):
    go, python = run_parity("plugin_entities")

    assert python["printed_entities"] == go["printed_entities"]
    assert python["printed_diff_before"] == go["printed_diff_before"]
    assert python["printed_diff_changed"] == go["printed_diff_changed"]
    assert python["log"] == go["log"]
    assert {"level": "info", "message": "create success", "resource": "resource.recording.first", "operation": "create"} in python["log"]
