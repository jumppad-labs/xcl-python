"""Schema v1 from Python classes, and entity JSON back into them.

``schema_for`` derives the schema v1 document for a dataclass from its
annotations, the language-neutral description of a block type the engine
builds its Go type from; ``hydrate`` turns an entity's JSON, as the engine
returns it, back into an instance of the registered class, or into a generic
:class:`Entity` for a type no class was registered for; ``signature_for``
derives the signature of a Python function offered to configuration.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import types
import typing
from typing import Any, Optional, Union, get_args, get_origin, get_type_hints

from xcl._errors import Error
from xcl._types import COMPUTED, SENSITIVE_MARKER, FieldOptions, Sensitive, options_of

if typing.TYPE_CHECKING:
    from xcl._classes import ClassMap

SCHEMA_VERSION = 1

# SENSITIVE_SHAPES are the value types the engine can hold a secret of
SENSITIVE_SHAPES = ("str", "int", "float", "bool", "list[str]", "dict[str, str]")


class SchemaError(Error, TypeError):
    """A class or function cannot be registered: it is not a dataclass, has no type name, or a field has no configuration form.

    It is raised by the package itself, never by the engine, and is a
    ``TypeError`` as well, so ``except TypeError`` still catches it.
    """

    code = "schema"


@dataclasses.dataclass(frozen=True)
class _Resolved:
    """What an annotation resolved to."""

    type: Any  # the schema type: "string", {"list": ...}, ...
    format: Optional[str] = None
    optional: bool = False
    sensitive: bool = False
    computed: bool = False
    block_fields: Optional[list[dict[str, Any]]] = None  # a nested dataclass's fields
    block_class: Any = None
    repeated: bool = False
    mapped: bool = False
    label: Optional[str] = None


def schema_for(cls: type, *, type_name: str, subtype: Optional[str] = None) -> dict[str, Any]:
    """The schema v1 document for ``cls``, a dataclass, as the block type ``type_name`` with an optional ``subtype``.

    A top-level ``meta: Meta | None`` is left out: it receives the block's
    metadata, its disabled flag and dependencies among it. ``meta``,
    ``disabled`` and ``depends_on`` are held by every block, so any other
    field by those names raises :class:`SchemaError`. Every other field becomes a schema field: ``str``, ``int``,
    ``float``, ``bool`` and ``Any`` are attributes; ``list[T]`` and
    ``dict[str, T]`` of those are list and map attributes; a dataclass is a
    nested block, ``list[Dataclass]`` a repeated block and
    ``dict[str, Dataclass]`` a map of named blocks; ``T | None`` or a default
    makes a field optional and a default becomes the schema default;
    ``Sensitive[T]`` marks it sensitive and ``Computed[T]`` computed.
    ``xcl.field`` overrides the name, forces a block or an attribute, and
    marks a block element's label field. An annotation with no
    configuration form raises :class:`SchemaError` naming the field.
    """
    if not is_dataclass_itself(cls):
        raise SchemaError(
            f"{_name(cls)} must be a dataclass to describe an entity type; "
            "decorate the class itself with @dataclass, a dataclass base is not enough"
        )

    doc: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "type": type_name}
    if subtype:
        doc["subtype"] = subtype

    labels = label_fields_of(cls)
    if is_singleton(cls):
        if subtype:
            raise SchemaError(
                f"{_name(cls)} has no label fields and no meta, so its block is written without labels, "
                "and its type takes no subtype"
            )
        doc["singleton"] = True
    elif labels and len(labels) != (2 if subtype else 1):
        raise SchemaError(
            f"{_name(cls)} has {len(labels)} label fields, a block of its type has {2 if subtype else 1} labels"
        )

    doc["fields"] = _fields_of(cls, top=True)
    return doc


def is_singleton(cls: type) -> bool:
    """Whether ``cls`` is a singleton: a dataclass that cannot read a name.

    One with neither a top-level ``meta`` field nor a field marked ``xcl.field(label=True)`` is written without labels,
    ``runner {}``, and a module holds one of it, addressed by its type alone.
    """
    names = {f.name for f in dataclasses.fields(cls)}
    return "meta" not in names and not label_fields_of(cls)


def is_dataclass_itself(cls: Any) -> bool:
    """Whether ``cls`` was itself decorated with ``@dataclass``, not merely derived from one.

    A subclass of a dataclass inherits ``__dataclass_fields__``, so
    ``dataclasses.is_dataclass`` is true of it even when its own annotations
    were never turned into fields; such a class would describe an entity
    type with none of its attributes.
    """
    return isinstance(cls, type) and "__dataclass_fields__" in cls.__dict__


def _fields_of(cls: type, *, top: bool) -> list[dict[str, Any]]:
    hints = get_type_hints(cls, include_extras=True)
    fields = []
    for f in dataclasses.fields(cls):
        options = options_of(f)
        if top and _is_base_field(cls, f, hints.get(f.name, f.type), options):
            continue
        if options.label:
            # the label field is named by the block that holds the element
            continue
        fields.append(_field_doc(cls, f, hints.get(f.name, f.type), options))
    return fields


def _is_base_field(owner: type, f: dataclasses.Field[Any], annotation: Any, options: FieldOptions) -> bool:
    """Whether ``f``, a top-level field of ``owner``, is the metadata field, refusing the reserved names.

    As in a Go plain struct, the metadata is the field called ``meta``, typed
    ``Meta`` or ``Meta | None``, and ``disabled`` and ``depends_on`` are read
    through it, so no field may be configured by any of the three names.
    """
    from xcl._entity import Meta

    where = f"{_name(owner)}.{f.name}"
    name = options.name or f.name
    if f.name == "meta":
        if annotation is not Meta and not (_is_union(annotation) and set(get_args(annotation)) == {Meta, type(None)}):
            raise SchemaError(f"field {where}: a field called meta is the block's metadata and must be an xcl.Meta | None, not {_name(annotation)}")
        if options.name:
            raise SchemaError(f"field {where}: the block's metadata is filled by xcl, not configuration, and takes no configuration name")
        return True
    if name in ("meta", "disabled", "depends_on"):
        raise SchemaError(f"field {where}: \"{name}\" is held by every block and cannot be declared, the class reads it from meta")
    return False


def label_fields_of(cls: type) -> list[str]:
    """The attributes of every field marked ``xcl.field(label=True)`` in ``cls``, in order."""
    return [f.name for f in dataclasses.fields(cls) if options_of(f).label]


def label_field_of(cls: type) -> Optional[tuple[str, str]]:
    """The attribute and schema name of the field marked ``xcl.field(label=True)`` in ``cls``, if any."""
    for f in dataclasses.fields(cls):
        options = options_of(f)
        if options.label:
            return f.name, options.name or f.name
    return None


def _field_doc(owner: type, f: dataclasses.Field[Any], annotation: Any, options: FieldOptions) -> dict[str, Any]:
    where = f"{_name(owner)}.{f.name}"
    resolved = _resolve(annotation, where, options)

    has_default = f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING
    optional = resolved.optional or resolved.computed or has_default

    doc: dict[str, Any] = {"name": options.name or f.name}

    if resolved.block_fields is not None:
        doc["kind"] = "block"
        if resolved.mapped:
            doc["type"] = {"map": {"object": resolved.block_fields}}
        else:
            doc["type"] = {"object": resolved.block_fields}
        if resolved.repeated:
            doc["repeated"] = True
        if resolved.label:
            doc["label"] = resolved.label
        if optional and not resolved.repeated and not resolved.mapped:
            doc["optional"] = True
        if resolved.sensitive:
            raise SchemaError(f"field {where}: a block cannot be sensitive, mark its fields")
        if resolved.computed:
            raise SchemaError(f"field {where}: a block cannot be computed, mark its fields")
        return doc

    doc["type"] = resolved.type
    if resolved.format:
        doc["format"] = resolved.format
    if resolved.computed:
        # computed implies optional, the engine never requires a value the
        # provider sets
        doc["computed"] = True
    elif optional:
        doc["optional"] = True
    if resolved.sensitive:
        doc["sensitive"] = True

    if f.default is not dataclasses.MISSING and f.default is not None and not resolved.computed:
        doc["default"] = _json_value(f.default, where)

    return doc


def _resolve(annotation: Any, where: str, options: FieldOptions) -> _Resolved:
    optional = False
    computed = False
    sensitive = False

    # Annotated[T, COMPUTED]
    if get_origin(annotation) is typing.Annotated:
        args = get_args(annotation)
        annotation = args[0]
        if any(a is COMPUTED for a in args[1:]):
            computed = True

    # T | None, Optional[T]
    if _is_union(annotation):
        members = [a for a in get_args(annotation) if a is not type(None)]
        if len(members) != len(get_args(annotation)):
            optional = True
        if len(members) != 1:
            raise SchemaError(f"field {where}: a union of types has no configuration form, use one type, optionally with None")
        annotation = members[0]

    # Annotated inside the optional
    if get_origin(annotation) is typing.Annotated:
        args = get_args(annotation)
        annotation = args[0]
        if any(a is COMPUTED for a in args[1:]):
            computed = True
        if _is_union(annotation):
            members = [a for a in get_args(annotation) if a is not type(None)]
            optional = optional or len(members) != len(get_args(annotation))
            annotation = members[0]

    # Sensitive[T]
    if get_origin(annotation) is Sensitive or annotation is Sensitive:
        sensitive = True
        args = get_args(annotation)
        if not args:
            raise SchemaError(f"field {where}: Sensitive needs its value type, e.g. Sensitive[str]")
        inner = args[0]
        if _is_union(inner):
            members = [a for a in get_args(inner) if a is not type(None)]
            optional = optional or len(members) != len(get_args(inner))
            inner = members[0]
        shape = _sensitive_shape(inner)
        if shape is None:
            raise SchemaError(
                f"field {where}: a sensitive value of type {_name(inner)} cannot be held by the engine; "
                f"sensitive values may be {', '.join(SENSITIVE_SHAPES)}"
            )
        base = _scalar_or_collection(inner, where)
        return _Resolved(type=base.type, format=base.format, optional=optional, sensitive=True, computed=computed)

    if dataclasses.is_dataclass(annotation) and isinstance(annotation, type):
        if options.block is False:
            return _Resolved(type={"object": _fields_of(annotation, top=False)}, optional=optional, computed=computed)
        return _Resolved(
            type=None,
            optional=optional,
            computed=computed,
            block_fields=_fields_of(annotation, top=False),
            block_class=annotation,
            label=_label_name(annotation),
        )

    origin = get_origin(annotation)
    if origin in (list, typing.List):
        (element,) = get_args(annotation) or (Any,)
        if dataclasses.is_dataclass(element) and isinstance(element, type) and options.block is not False:
            return _Resolved(
                type=None,
                optional=optional,
                computed=computed,
                block_fields=_fields_of(element, top=False),
                block_class=element,
                repeated=True,
                label=_label_name(element),
            )
    if origin in (dict, typing.Dict):
        key, element = get_args(annotation) or (str, Any)
        if key is not str:
            raise SchemaError(f"field {where}: a map must have string keys, not {_name(key)}")
        if dataclasses.is_dataclass(element) and isinstance(element, type) and options.block is not False:
            return _Resolved(
                type=None,
                optional=optional,
                computed=computed,
                block_fields=_fields_of(element, top=False),
                block_class=element,
                mapped=True,
                label=_label_name(element),
            )

    base = _scalar_or_collection(annotation, where)
    return _Resolved(type=base.type, format=base.format, optional=optional, computed=computed)


def _scalar_or_collection(annotation: Any, where: str) -> _Resolved:
    if annotation is str:
        return _Resolved(type="string")
    if annotation is bool:
        return _Resolved(type="bool")
    if annotation is int:
        return _Resolved(type="number", format="int")
    if annotation is float:
        return _Resolved(type="number", format="float")
    if annotation is Any or annotation is object:
        return _Resolved(type="any")

    origin = get_origin(annotation)
    if origin in (list, typing.List):
        args = get_args(annotation)
        element = _scalar_or_collection(args[0] if args else Any, where)
        return _Resolved(type={"list": element.type}, format=element.format)
    if origin in (dict, typing.Dict):
        args = get_args(annotation)
        key, element_type = args if args else (str, Any)
        if key is not str:
            raise SchemaError(f"field {where}: a map must have string keys, not {_name(key)}")
        element = _scalar_or_collection(element_type, where)
        return _Resolved(type={"map": element.type}, format=element.format)
    if dataclasses.is_dataclass(annotation) and isinstance(annotation, type):
        return _Resolved(type={"object": _fields_of(annotation, top=False)})

    raise SchemaError(
        f"field {where}: {_name(annotation)} has no configuration form; use str, int, float, bool, Any, "
        "a dataclass, or a list or dict of those"
    )


def _sensitive_shape(inner: Any) -> Optional[str]:
    if inner is str:
        return "str"
    if inner is int:
        return "int"
    if inner is float:
        return "float"
    if inner is bool:
        return "bool"
    origin = get_origin(inner)
    if origin in (list, typing.List) and get_args(inner) == (str,):
        return "list[str]"
    if origin in (dict, typing.Dict) and get_args(inner) == (str, str):
        return "dict[str, str]"
    return None


def _label_name(element: type) -> Optional[str]:
    found = label_field_of(element)
    return found[1] if found else None


def _is_union(annotation: Any) -> bool:
    origin = get_origin(annotation)
    return origin is Union or (hasattr(types, "UnionType") and origin is types.UnionType)


def _json_value(value: Any, where: str) -> Any:
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"field {where}: the default {value!r} cannot be written as configuration: {exc}") from exc


def _name(t: Any) -> str:
    return getattr(t, "__name__", None) or repr(t)


# ---------------------------------------------------------------------------
# function signatures


def signature_for(fn: Any) -> dict[str, Any]:
    """The ``FunctionSignature`` JSON document for a Python function offered to configuration.

    Parameters and the return are read from the annotations: ``str``,
    ``bool``, ``int`` and ``float`` (both ``number``), ``list[T]`` and
    ``dict[str, T]`` of those. A ``*args`` parameter is declared variadic,
    which the engine refuses, and a parameter or return without an
    annotation, or with one of another type, raises :class:`SchemaError`.
    """
    try:
        hints = get_type_hints(fn)
    except Exception as exc:  # noqa: BLE001 - any failure to resolve the hints is the same problem
        raise SchemaError(f"function {_name(fn)}: its annotations cannot be read: {exc}") from exc

    signature = inspect.signature(fn)
    params = []
    variadic = None
    for p in signature.parameters.values():
        if p.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_KEYWORD):
            raise SchemaError(f"function {_name(fn)}: parameter {p.name} must be positional, configuration passes arguments by position")
        if p.name not in hints:
            raise SchemaError(f"function {_name(fn)}: parameter {p.name} needs a type annotation")
        param = {"name": p.name, "type": _cty_type(hints[p.name], f"function {_name(fn)}: parameter {p.name}")}
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            variadic = param
        else:
            params.append(param)

    if "return" not in hints:
        raise SchemaError(f"function {_name(fn)}: the return type needs an annotation")

    doc: dict[str, Any] = {"params": params, "return": _cty_type(hints["return"], f"function {_name(fn)}: return")}
    if variadic is not None:
        doc["variadic"] = variadic
    return doc


def _cty_type(annotation: Any, where: str) -> Any:
    if annotation is str:
        return "string"
    if annotation is bool:
        return "bool"
    if annotation in (int, float):
        return "number"
    origin = get_origin(annotation)
    if origin in (list, typing.List, set, typing.Set):
        args = get_args(annotation)
        if not args:
            raise SchemaError(f"{where}: a list needs its element type, e.g. list[str]")
        return ["list", _cty_type(args[0], where)]
    if origin in (dict, typing.Dict):
        args = get_args(annotation)
        if len(args) != 2 or args[0] is not str:
            raise SchemaError(f"{where}: a map must be dict[str, T]")
        return ["map", _cty_type(args[1], where)]
    raise SchemaError(f"{where}: {_name(annotation)} cannot cross to configuration; use str, bool, int, float, list[T] or dict[str, T]")


def cty_to_python(value: Any) -> Any:
    """A JSON-decoded argument as a Python value; numbers that are whole become ``int``."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [cty_to_python(v) for v in value]
    if isinstance(value, dict):
        return {k: cty_to_python(v) for k, v in value.items()}
    return value


# ---------------------------------------------------------------------------
# hydration


def hydrate(data: Any, cls: Optional[type] = None, *, registry: Optional[ClassMap] = None) -> Any:
    """An entity's JSON as a Python object.

    With ``cls`` the JSON is decoded into that class; otherwise the class
    ``registry``, a configuration's class map, holds for the entity's
    ``meta.type`` and ``meta.subtype`` is used, and an entity of a type with
    no class there becomes an :class:`Entity`. ``meta`` is filled only when
    the class declares it, and only at the top level. A sensitive field
    holding the marker becomes a redacted :class:`Sensitive`, a masked
    envelope likewise, and a real value a :class:`Sensitive` holding it.
    Nested blocks, lists of blocks and maps of named blocks are decoded into
    their classes.
    """
    from xcl._entity import Entity, Meta

    if not isinstance(data, dict):
        return data

    if cls is None and registry is not None:
        meta = data.get("meta") or {}
        cls = registry.class_for(meta.get("type", ""), meta.get("subtype", ""))
    if cls is None:
        return Entity(data)

    return _hydrate_into(cls, data, Meta)


def _hydrate_into(cls: type, data: dict[str, Any], meta_cls: Any) -> Any:
    # meta_cls is given for the entity itself and None for a nested block,
    # whose fields called meta are ordinary fields
    hints = get_type_hints(cls, include_extras=True)
    values: dict[str, Any] = {}
    labels = _labels_of(cls, data) if meta_cls is not None else {}
    for f in dataclasses.fields(cls):
        options = options_of(f)
        key = options.name or f.name
        if meta_cls is not None and f.name == "meta":
            values["meta"] = meta_cls.from_entity(data) if isinstance(data.get("meta"), dict) else None
            continue
        if f.name in labels:
            values[f.name] = labels[f.name]
            continue
        if key not in data:
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                values[f.name] = None
            continue
        values[f.name] = _hydrate_value(hints.get(f.name, f.type), data[key], options)

    instance = cls(**values)
    return instance


def _labels_of(cls: type, data: dict[str, Any]) -> dict[str, str]:
    """The values of an entity's label fields, from its labels as ``meta`` records them.

    One label field holds the name, two the subtype and the name, as in Go.
    Only the entity itself is read this way: a nested block's element has its
    label field in its data, filled by the engine from the block's label.
    """
    meta = data.get("meta")
    fields = label_fields_of(cls)
    if not isinstance(meta, dict) or not fields:
        return {}
    if len(fields) == 2:
        return {fields[0]: meta.get("subtype", ""), fields[1]: meta.get("name", "")}
    return {fields[0]: meta.get("name", "")}


def _hydrate_value(annotation: Any, value: Any, options: FieldOptions) -> Any:
    if get_origin(annotation) is typing.Annotated:
        annotation = get_args(annotation)[0]
    if _is_union(annotation):
        members = [a for a in get_args(annotation) if a is not type(None)]
        if len(members) == 1:
            annotation = members[0]
    if get_origin(annotation) is typing.Annotated:
        annotation = get_args(annotation)[0]

    if value is None:
        return None

    if get_origin(annotation) is Sensitive or annotation is Sensitive:
        return _sensitive_of(value)

    if dataclasses.is_dataclass(annotation) and isinstance(annotation, type):
        if isinstance(value, dict):
            return _hydrate_into(annotation, value, None)
        return value

    origin = get_origin(annotation)
    if origin in (list, typing.List) and isinstance(value, list):
        args = get_args(annotation)
        element = args[0] if args else Any
        return [_hydrate_value(element, v, FieldOptions()) for v in value]
    if origin in (dict, typing.Dict) and isinstance(value, dict):
        args = get_args(annotation)
        element = args[1] if len(args) == 2 else Any
        return {k: _hydrate_value(element, v, FieldOptions()) for k, v in value.items()}

    return value


def _sensitive_of(value: Any) -> Sensitive[Any]:
    if value == SENSITIVE_MARKER:
        return Sensitive.redacted()
    if isinstance(value, dict) and "xcl_masked" in value:
        return Sensitive.redacted()
    return Sensitive(value)


def is_masked(value: Any) -> bool:
    """Whether a JSON value is the engine's sensitive marker or a masked envelope."""
    return value == SENSITIVE_MARKER or (isinstance(value, dict) and "xcl_masked" in value)
