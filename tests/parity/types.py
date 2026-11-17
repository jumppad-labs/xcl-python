"""The Python classes equivalent to each parity fixture's ``types.json``.

The Go parity program registers the schema v1 documents in a fixture's
``types.json`` directly; the Python side registers these dataclasses, whose
derived schema must equal those documents (``test_types.py`` checks it).

Several fixtures declare a type called ``app`` with different fields. Each
configuration keeps its own map of type names to classes, so the classes are
plain dataclasses registered by name on the run's registry
(``local.register_type(cls, type, subtype)``); no per-run re-decoration is
needed to keep one fixture's ``app`` from replacing another's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import xcl

# -- basic_types --------------------------------------------------------------


@dataclass
class BasicTypesService:
    port: int
    ratio: float | None = None
    enabled: bool | None = None
    tags: list[str] | None = None
    labels: dict[str, str] | None = None
    upstream: str | None = None
    meta: xcl.Meta | None = None


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
class AnnotationsApp:
    image: str
    replicas: int = 2
    region: str = "eu"
    password: xcl.Sensitive[str] | None = None
    endpoint: xcl.Computed[str] = None
    health: AnnotationsHealth | None = None
    volume: list[AnnotationsVolume] = field(default_factory=list)
    listener: dict[str, AnnotationsListener] = field(default_factory=dict)
    meta: xcl.Meta | None = None


# -- functions ----------------------------------------------------------------


@dataclass
class FunctionsApp:
    name: str
    secret: xcl.Sensitive[str] | None = None
    token: xcl.Sensitive[str] | None = None
    meta: xcl.Meta | None = None


# -- variables ----------------------------------------------------------------


@dataclass
class VariablesApp:
    region: str
    replicas: int | None = None
    meta: xcl.Meta | None = None


# -- outputs ------------------------------------------------------------------


@dataclass
class OutputsApp:
    region: str
    ports: list[int] | None = None
    meta: xcl.Meta | None = None


# -- invalid ------------------------------------------------------------------


@dataclass
class InvalidApp:
    image: str
    endpoint: xcl.Computed[str] = None
    meta: xcl.Meta | None = None


# -- unsupported_block --------------------------------------------------------


@dataclass
class UnsupportedBlockApp:
    image: str
    endpoint: xcl.Computed[str] = None
    meta: xcl.Meta | None = None


# -- singletons ---------------------------------------------------------------


@dataclass
class SingletonsRunner:
    server: str
    listen: str | None = None


@dataclass
class SingletonsAgent:
    model: str
    server: str | None = None
    handle: str = xcl.field(label=True, default="")


# -- encode -------------------------------------------------------------------


@dataclass
class EncodeStore:
    address: str
    password: xcl.Sensitive[str]
    note: str = ""
    port: int | None = None
    tags: list[str] = field(default_factory=list)
    labels: dict[str, str] | None = None
    meta: xcl.Meta | None = None


@dataclass
class EncodeService:
    location: str
    secret: xcl.Sensitive[str] | None = None
    token: xcl.Sensitive[str] | None = None
    name: str = xcl.field(label=True, default="")


# -- object_values ------------------------------------------------------------


@dataclass
class ObjectValuesEndpoint:
    """An object value's class: required, defaulted, optional and sensitive fields."""

    port: int
    tls: bool = False
    path: str | None = None
    token: xcl.Sensitive[str] | None = None


@dataclass
class ObjectValuesPostgres:
    location: str
    port: int = 5432
    meta: xcl.Meta | None = None


@dataclass
class ObjectValuesApp:
    image: str
    default_endpoint: ObjectValuesEndpoint = xcl.field(block=False)
    endpoints: list[ObjectValuesEndpoint] = xcl.field(block=False, default_factory=list)
    routes: dict[str, ObjectValuesEndpoint] = xcl.field(block=False, default_factory=dict)
    database: ObjectValuesPostgres | None = xcl.field(block=False, default=None)
    databases: list[ObjectValuesPostgres] = xcl.field(block=False, default_factory=list)
    meta: xcl.Meta | None = None


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
    "unsupported_block": [("app", None, UnsupportedBlockApp)],
    "singletons": [("runner", None, SingletonsRunner), ("agent", None, SingletonsAgent)],
    "encode": [("store", "postgres", EncodeStore), ("service", None, EncodeService)],
    "object_values": [("database", "postgres", ObjectValuesPostgres), ("app", None, ObjectValuesApp)],
}


# HAND_BUILT maps a fixture directory's name to the entities its
# hand_built.json lists, by address, each built by hand with the values the
# fixture's main.xcl gives it, never loaded
HAND_BUILT: dict[str, dict[str, Callable[[], object]]] = {
    "encode": {
        "store.postgres.main": lambda: EncodeStore(
            address="10.0.0.1",
            password=xcl.Sensitive("s3cret"),
            tags=[],
            meta=xcl.Meta(name="main"),
        ),
    },
}


def _postgres(name: str, location: str, port: int = 5432) -> ObjectValuesPostgres:
    return ObjectValuesPostgres(
        location=location, port=port, meta=xcl.Meta(name=name, type="database", subtype="postgres")
    )


def _hand_built_edge() -> ObjectValuesApp:
    app = ObjectValuesApp(
        image="envoy",
        default_endpoint=ObjectValuesEndpoint(port=443, tls=True),
        routes={"public": ObjectValuesEndpoint(port=443, tls=True, path="/")},
        meta=xcl.Meta(name="edge"),
    )
    # main.xcl sets neither list, so they are unset rather than the class's empty default
    app.endpoints = None  # type: ignore[assignment]
    app.databases = None  # type: ignore[assignment]
    return app


def _hand_built_web() -> ObjectValuesApp:
    return ObjectValuesApp(
        image="nginx",
        default_endpoint=ObjectValuesEndpoint(port=80, tls=True, token=xcl.Sensitive("s3cret")),
        endpoints=[ObjectValuesEndpoint(port=8080), ObjectValuesEndpoint(port=8443, tls=True, path="/api")],
        routes={"public": ObjectValuesEndpoint(port=80), "admin": ObjectValuesEndpoint(port=9000, tls=True)},
        database=_postgres("main", "eu-west-1"),
        databases=[_postgres("a", "eu-west-2", 5433), _postgres("b", "us-east-1")],
        # the references main.xcl writes, which show references swaps in
        meta=xcl.Meta(
            name="web",
            references={"database": "database.postgres.main", "databases": "[database.postgres.a, database.postgres.b]"},
        ),
    )


HAND_BUILT["object_values"] = {
    "app.edge": _hand_built_edge,
    "database.postgres.main": lambda: _postgres("main", "eu-west-1"),
    "app.web": _hand_built_web,
}


def slugify(title: str) -> str:
    """The function every parity side registers: lower case, spaces to dashes."""
    return title.lower().replace(" ", "-")
