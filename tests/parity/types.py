"""The Python classes equivalent to each parity fixture's ``types.json``.

The Go parity program registers the schema v1 documents in a fixture's
``types.json`` directly; the Python side registers these dataclasses, whose
derived schema must equal those documents (``test_types.py`` checks it).

Several fixtures declare a type called ``app`` with different fields, and
``xcl.entity`` keys its module-wide registry by type name, so the classes are
plain dataclasses here and :func:`register` decorates a fixture's classes
right before a run builds its registry; re-registering replaces the entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import xcl

# -- basic_types --------------------------------------------------------------


@dataclass
class BasicTypesService(xcl.Resource):
    port: int
    ratio: float | None = None
    enabled: bool | None = None
    tags: list[str] | None = None
    labels: dict[str, str] | None = None
    upstream: str | None = None


# -- annotations --------------------------------------------------------------


@dataclass
class AnnotationsHealth:
    path: str


@dataclass
class AnnotationsVolume:
    source: str
    name: str = xcl.field(label=True, default="")


@dataclass
class AnnotationsListener:
    port: int
    name: str = xcl.field(label=True, default="")


@dataclass
class AnnotationsApp(xcl.Resource):
    image: str
    replicas: int = 2
    region: str = "eu"
    password: xcl.Sensitive[str] | None = None
    endpoint: xcl.Computed[str] = None
    health: AnnotationsHealth | None = None
    volume: list[AnnotationsVolume] = field(default_factory=list)
    listener: dict[str, AnnotationsListener] = field(default_factory=dict)


# -- functions ----------------------------------------------------------------


@dataclass
class FunctionsApp(xcl.Resource):
    name: str
    secret: xcl.Sensitive[str] | None = None
    token: xcl.Sensitive[str] | None = None


# -- variables ----------------------------------------------------------------


@dataclass
class VariablesApp(xcl.Resource):
    region: str
    replicas: int | None = None


# -- outputs ------------------------------------------------------------------


@dataclass
class OutputsApp(xcl.Resource):
    region: str
    ports: list[int] | None = None


# -- invalid ------------------------------------------------------------------


@dataclass
class InvalidApp(xcl.Resource):
    image: str
    endpoint: xcl.Computed[str] = None


# FIXTURES maps a fixture directory's name to its types: (type, subtype, class),
# in the order of the fixture's types.json
FIXTURES: dict[str, list[tuple[str, Optional[str], type]]] = {
    "basic_types": [("service", None, BasicTypesService)],
    "annotations": [("app", None, AnnotationsApp)],
    "functions": [("app", None, FunctionsApp)],
    "variables": [("app", None, VariablesApp)],
    "outputs": [("app", None, OutputsApp)],
    "plugin_entities": [],
    "invalid": [("app", None, InvalidApp)],
}


def register(fixture: str) -> list[type]:
    """Register the classes of ``fixture`` under the fixture's type names and return them."""
    registered = []
    for type_name, subtype, cls in FIXTURES[fixture]:
        registered.append(xcl.entity(type_name, subtype)(cls))
    return registered


def slugify(title: str) -> str:
    """The function every parity side registers: lower case, spaces to dashes."""
    return title.lower().replace(" ", "-")
