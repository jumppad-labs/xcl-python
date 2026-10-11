"""Calling a registered Python function for a function task."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from xcl._core import core_pb2
from xcl._schema import cty_to_python
from xcl._types import Sensitive


def decode_args(args: bytes) -> list[Any]:
    """The arguments of a function task as Python values."""
    decoded = json.loads(args) if args else []
    if not isinstance(decoded, list):
        raise ValueError("function arguments must be a JSON array")
    return [cty_to_python(a) for a in decoded]


def encode_result(value: Any) -> bytes:
    """A function's result as the JSON the engine decodes against the declared return type."""
    if isinstance(value, Sensitive):
        value = value.reveal()
    return json.dumps(value).encode()


def call_function(fn: Callable[..., Any], args: bytes) -> core_pb2.FunctionResult:
    """Call ``fn`` with the task's arguments and return the result, or the exception as the error."""
    try:
        result = fn(*decode_args(args))
        return core_pb2.FunctionResult(result=encode_result(result))
    except Exception as exc:  # noqa: BLE001 - every failure becomes the call's error in configuration
        return failed_result(exc)


def failed_result(exc: BaseException) -> core_pb2.FunctionResult:
    """A function result carrying an exception as the call's error."""
    message = str(exc) or exc.__class__.__name__
    return core_pb2.FunctionResult(error=core_pb2.Error(code="function", message=message))
