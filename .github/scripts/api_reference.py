"""The one definition of the package's public API, and the reference built from it.

Reads the package statically, so it needs neither the engine nor an import of
``xcl``, and sees what runtime introspection cannot, such as the string
following a constant. A public name is one in ``xcl.__all__``, or in the
``__all__`` of a module exported there, or the module ``xcl.aio`` and its
``__all__``. A public member is a constructor, method or property of a public
class, including those inherited from the package's own classes; attributes
are listed but need no doc comment, and a class's doc comment documents its
constructor.

``--check`` prints every public name or member with no doc comment, and every
doc comment that is not valid reStructuredText, and exits non-zero. ``--out``
writes the API as the JSON the documentation site renders: no field of it
names Python, so another language's reference can take the same shape.

Used by the check-docs job of test.yml and the reference job of release.yml.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docutils.core
import docutils.nodes
import docutils.parsers.rst.roles
import docutils.utils
import docutils.writers.html5_polyglot
import griffe

PACKAGE = "xcl"
DISTRIBUTION = "xcl-lang"
SCHEMA = 1

# a module that is public without being in xcl.__all__: adding it there would
# change what `from xcl import *` binds
EXTRA_MODULES = ("aio",)

ASYNC_MODULE = f"{PACKAGE}.aio"
ERROR_CLASS = f"{PACKAGE}.Error"

# the longest constant or attribute value shown in a signature
MAX_VALUE_LENGTH = 80

CROSS_REFERENCE_ROLES = ("class", "func", "meth", "attr", "data", "mod", "exc", "obj")


@dataclass
class Item:
    """One public name or member, found by the walk and not yet rendered."""

    id: str
    name: str
    kind: str
    target: Any
    inherited_from: str | None = None
    members: list[Item] = field(default_factory=list)


@dataclass
class Section:
    """A group of public names, in the order the reference shows them."""

    id: str
    title: str
    items: list[Item] = field(default_factory=list)


@dataclass
class Api:
    """What the walk found: the sections, the version and anything wrong."""

    sections: list[Section]
    version: str | None
    problems: list[str]


class Resolver:
    """Turns a doc comment's cross-reference into the id of a public entry."""

    def __init__(self, sections: list[Section]) -> None:
        self.ids: set[str] = set()
        self.canonical: dict[str, str] = {}
        self.bare: dict[str, set[str]] = {}
        for section in sections:
            for item in section.items:
                self._add(item)

    def _add(self, item: Item) -> None:
        self.ids.add(item.id)
        self.canonical.setdefault(item.target.canonical_path, item.id)
        self.bare.setdefault(item.name, set()).add(item.id)
        for member in item.members:
            self._add(member)

    def resolve(self, target: str, enclosing: str) -> str | None:
        """The entry a reference names, searched from the entry holding it outwards."""
        if target in self.ids:
            return target
        scope = enclosing
        while scope:
            candidate = f"{scope}.{target}"
            if candidate in self.ids:
                return candidate
            scope = scope.rpartition(".")[0]
        if target in self.canonical:
            return self.canonical[target]
        matches = self.bare.get(target.rpartition(".")[2], set())
        return next(iter(matches)) if len(matches) == 1 else None


@dataclass
class RenderContext:
    """What the cross-reference roles need while one doc comment is rendered."""

    resolver: Resolver
    enclosing: str


def cross_reference_role(
    name: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: Any,
    options: dict[str, Any] | None = None,
    content: list[str] | None = None,
) -> tuple[list[Any], list[Any]]:
    """A Sphinx-style role: a link when it names a public entry, otherwise plain code."""
    context: RenderContext = inliner.document.settings.api_reference_context
    source = docutils.utils.unescape(text)
    title, target = source, source
    if source.endswith(">") and " <" in source:
        title, _, target = source[:-1].partition(" <")
    if target.startswith(("~", "!")):
        shorten = target.startswith("~")
        target = target[1:]
        if title == source:
            title = target.rpartition(".")[2] if shorten else target
    literal = docutils.nodes.literal(rawtext, title)
    resolved = context.resolver.resolve(target, context.enclosing)
    if resolved is None:
        return [literal], []
    return [docutils.nodes.reference(rawtext, "", literal, refuri=f"#{resolved}", internal=True)], []


def register_roles() -> None:
    """Teach docutils the cross-reference roles the package's doc comments use."""
    for role in CROSS_REFERENCE_ROLES:
        docutils.parsers.rst.roles.register_local_role(role, cross_reference_role)


class ReferenceTranslator(docutils.writers.html5_polyglot.HTMLTranslator):
    """HTML with an inline literal as ``<code>``, which the site's own styles cover."""

    def visit_literal(self, node: Any) -> None:
        node["classes"].append("code")
        super().visit_literal(node)


class ReferenceWriter(docutils.writers.html5_polyglot.Writer):
    def __init__(self) -> None:
        super().__init__()
        self.translator_class = ReferenceTranslator


def render(text: str, context: RenderContext) -> str:
    """Doc comment text as HTML; bad markup raises docutils' SystemMessage."""
    return docutils.core.publish_parts(
        source=text,
        writer=ReferenceWriter(),
        settings_overrides={
            "report_level": 2,
            "halt_level": 2,
            "traceback": True,
            "warning_stream": io.StringIO(),
            "doctitle_xform": False,
            "docinfo_xform": False,
            "file_insertion_enabled": False,
            "raw_enabled": False,
            "api_reference_context": context,
        },
    )["fragment"].strip()


def load_package(source: Path) -> Any:
    """Read the package statically from the directory holding it."""
    # Griffe warns about ordinary things, such as an unannotated parameter
    logging.getLogger("griffe").setLevel(logging.ERROR)
    return griffe.load(
        PACKAGE,
        search_paths=[str(source)],
        # the default would find an xcl directory in the current directory first
        try_relative_path=False,
        docstring_parser="sphinx",
        allow_inspection=False,
        resolve_aliases=True,
        resolve_external=False,
    )


def has_doc_comment(target: Any) -> bool:
    return target.docstring is not None and bool(target.docstring.value.strip())


def is_module(target: Any) -> bool:
    return target.kind is griffe.Kind.MODULE


def is_class(target: Any) -> bool:
    return target.kind is griffe.Kind.CLASS


def is_function(target: Any) -> bool:
    return target.kind is griffe.Kind.FUNCTION


class Walker:
    """Walks the export lists into sections, noting anything it cannot follow."""

    def __init__(self, package: Any) -> None:
        self.package = package
        self.problems: list[str] = []
        self.error_class = self._find_error_class()
        self.errors = Section("errors", "Errors")

    def walk(self) -> list[Section]:
        main = Section(PACKAGE, PACKAGE, [self._module_item(self.package, PACKAGE)])
        modules: list[tuple[str, Any]] = []
        for name in EXTRA_MODULES:
            if name in self.package.members:
                modules.append((f"{PACKAGE}.{name}", self._final(self.package.members[name])))
        modules += self._add_exports(self.package, PACKAGE, main)

        sections = [main]
        while modules:
            module_id, module = modules.pop(0)
            section = Section(module_id, module_id, [self._module_item(module, module_id)])
            modules += self._add_exports(module, module_id, section)
            sections.append(section)

        if self.errors.items:
            sections.append(self.errors)
        return sections

    def _find_error_class(self) -> Any:
        error = self.package.members.get("Error")
        if error is None:
            return None
        try:
            target = error.final_target if error.is_alias else error
        except (griffe.AliasResolutionError, griffe.CyclicAliasError):
            return None
        return target if is_class(target) else None

    def _final(self, member: Any) -> Any:
        return member.final_target if member.is_alias else member

    def _add_exports(self, module: Any, module_id: str, section: Section) -> list[tuple[str, Any]]:
        """Adds a module's exports to its section, returning the modules among them."""
        modules: list[tuple[str, Any]] = []
        for export in module.exports or []:
            name = str(export)
            entry_id = f"{module_id}.{name}"
            member = module.members.get(name)
            if member is None:
                self.problems.append(f"{entry_id}: named in __all__ but not defined")
                continue
            try:
                target = self._final(member)
            except (griffe.AliasResolutionError, griffe.CyclicAliasError):
                self.problems.append(f"{entry_id}: named in __all__ but cannot be resolved")
                continue
            if is_module(target):
                modules.append((entry_id, target))
            elif self._is_error(target):
                self.errors.items.append(self._item(target, entry_id, name))
            else:
                section.items.append(self._item(target, entry_id, name))
        return modules

    def _is_error(self, target: Any) -> bool:
        if self.error_class is None or not is_class(target):
            return False
        if target.canonical_path == self.error_class.canonical_path:
            return True
        try:
            return self.error_class.canonical_path in [base.canonical_path for base in target.mro()]
        except ValueError:
            return False

    def _module_item(self, module: Any, entry_id: str) -> Item:
        return Item(entry_id, entry_id.rpartition(".")[2], "module", module)

    def _item(self, target: Any, entry_id: str, name: str) -> Item:
        if is_class(target):
            return Item(entry_id, name, "class", target, members=self._members(target, entry_id))
        if is_function(target):
            return Item(entry_id, name, "function", target)
        return Item(entry_id, name, "constant", target)

    def _members(self, cls: Any, class_id: str) -> list[Item]:
        own: list[Item] = []
        inherited: list[Item] = []
        constructor: list[Item] = []
        for name, member in cls.all_members.items():
            if name.startswith("_") and name != "__init__":
                continue
            target = self._final(member)
            if is_class(target) or is_module(target):
                continue
            item = Item(f"{class_id}.{name}", name, self._member_kind(name, target), target)
            if member.inherited:
                item.inherited_from = target.parent.canonical_path
            if name == "__init__":
                constructor.append(item)
            elif member.inherited:
                inherited.append(item)
            else:
                own.append(item)
        return constructor + own + inherited

    def _member_kind(self, name: str, target: Any) -> str:
        if name == "__init__":
            return "constructor"
        if is_function(target):
            return "method"
        return "property" if "property" in target.labels else "attribute"


def walk_api(package: Any) -> Api:
    walker = Walker(package)
    sections = walker.walk()
    version = None
    member = package.members.get("__version__")
    if member is None:
        walker.problems.append(f"{PACKAGE}.__version__: not defined")
    else:
        version = str(walker._final(member).value).strip("'\"")
    return Api(sections, version, walker.problems)


def undocumented(item: Item) -> list[str]:
    """The ids under an item that need a doc comment and have none."""
    found: list[str] = []
    if item.kind not in ("attribute", "constructor") and not has_doc_comment(item.target):
        found.append(item.id)
    for member in item.members:
        found += undocumented(member)
    return found


def format_parameter(parameter: Any) -> str:
    text = parameter_name(parameter)
    default = parameter_default(parameter)
    if parameter.annotation is not None:
        text += f": {parameter.annotation}"
        if default is not None:
            text += f" = {default}"
    elif default is not None:
        text += f"={default}"
    return text


def parameter_default(parameter: Any) -> str | None:
    """A parameter's default; Griffe gives a variadic one that is not written in the source."""
    if parameter.kind in (griffe.ParameterKind.var_positional, griffe.ParameterKind.var_keyword):
        return None
    return None if parameter.default is None else str(parameter.default)


def parameter_name(parameter: Any) -> str:
    if parameter.kind is griffe.ParameterKind.var_positional:
        return f"*{parameter.name}"
    if parameter.kind is griffe.ParameterKind.var_keyword:
        return f"**{parameter.name}"
    return parameter.name


def visible_parameters(function: Any) -> list[Any]:
    """A function's parameters, without the ``self`` or ``cls`` of a method."""
    parameters = list(function.parameters)
    if parameters and parameters[0].name in ("self", "cls") and is_class(function.parent):
        parameters = parameters[1:]
    return parameters


def function_signature(function: Any, name: str) -> str:
    parts: list[str] = []
    star_seen = False
    previous_positional_only = False
    for parameter in visible_parameters(function):
        positional_only = parameter.kind is griffe.ParameterKind.positional_only
        if previous_positional_only and not positional_only:
            parts.append("/")
        if parameter.kind is griffe.ParameterKind.keyword_only and not star_seen:
            parts.append("*")
            star_seen = True
        if parameter.kind is griffe.ParameterKind.var_positional:
            star_seen = True
        parts.append(format_parameter(parameter))
        previous_positional_only = positional_only
    if previous_positional_only:
        parts.append("/")
    prefix = "async " if "async" in function.labels else ""
    constructor = function.name == "__init__"
    returns = f" -> {function.returns}" if function.returns is not None and not constructor else ""
    return f"{prefix}{name}({', '.join(parts)}){returns}"


def attribute_signature(attribute: Any, name: str) -> str:
    text = name
    if attribute.annotation is not None:
        text += f": {attribute.annotation}"
    if attribute.value is not None and "property" not in attribute.labels:
        value = str(attribute.value)
        if len(value) <= MAX_VALUE_LENGTH and "\n" not in value:
            text += f" = {value}"
    return text


def class_signature(cls: Any, name: str) -> str:
    bases = ", ".join(str(base) for base in cls.bases)
    return f"class {name}({bases})" if bases else f"class {name}"


def signature_of(item: Item) -> str | None:
    if item.kind == "module":
        return None
    if item.kind == "class":
        return class_signature(item.target, item.name)
    if item.kind in ("function", "method"):
        return function_signature(item.target, item.name)
    if item.kind == "constructor":
        class_name = item.id.split(".")[-2]
        return function_signature(item.target, class_name)
    return attribute_signature(item.target, item.name)


@dataclass
class ParsedDocComment:
    """A doc comment split into its parts, with the text not yet rendered."""

    text: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    returns: Any = None
    raises: list[Any] = field(default_factory=list)


def parse_doc_comment(target: Any) -> ParsedDocComment:
    parsed = ParsedDocComment()
    if target.docstring is None:
        return parsed
    for section in target.docstring.parsed:
        if section.kind is griffe.DocstringSectionKind.text:
            parsed.text = section.value
        elif section.kind is griffe.DocstringSectionKind.parameters:
            for parameter in section.value:
                parsed.parameters[parameter.name.lstrip("*\\")] = parameter
        elif section.kind is griffe.DocstringSectionKind.returns:
            parsed.returns = section.value[0] if section.value else None
        elif section.kind is griffe.DocstringSectionKind.raises:
            parsed.raises = list(section.value)
    return parsed


def annotation_text(annotation: Any) -> str | None:
    if annotation is None:
        return None
    text = str(annotation)
    return text or None


class Builder:
    """Renders walked items to the JSON the site reads."""

    def __init__(self, sections: list[Section]) -> None:
        self.resolver = Resolver(sections)
        self.problems: list[str] = []

    def render(self, text: str, enclosing: str) -> str:
        if not text.strip():
            return ""
        try:
            return render(text, RenderContext(self.resolver, enclosing))
        except docutils.utils.SystemMessage as error:
            self.problems.append(f"{enclosing}: invalid doc comment: {error}")
            return ""

    def label(self, entry_id: str) -> str | None:
        """Which client an entry belongs to, when the package has both forms of it."""
        if entry_id == ASYNC_MODULE or entry_id.startswith(f"{ASYNC_MODULE}."):
            return "asyncio"
        relative = entry_id[len(PACKAGE) + 1 :]
        return "synchronous" if f"{ASYNC_MODULE}.{relative}" in self.resolver.ids else None

    def entry(self, item: Item) -> dict[str, Any]:
        doc_comment_owner = item.target
        generated_description = None
        if item.kind == "constructor" and not has_doc_comment(item.target):
            # the class's doc comment documents its constructor
            doc_comment_owner = item.target.parent
            class_name = item.id.split(".")[-2]
            generated_description = f"<p>Creates a <code>{class_name}</code>, as the class describes.</p>"
        parsed = parse_doc_comment(doc_comment_owner)

        entry: dict[str, Any] = {"id": item.id, "name": item.name, "kind": item.kind}
        label = self.label(item.id)
        if label:
            entry["label"] = label
        signature = signature_of(item)
        if signature:
            entry["signature"] = signature
        entry["description"] = generated_description or self.render(parsed.text, item.id)

        if item.kind in ("function", "method", "constructor"):
            parameters = self.parameters(item, parsed)
            if parameters:
                entry["parameters"] = parameters
            returns = self.returns(item, parsed)
            if returns:
                entry["returns"] = returns
        raises = [self.raised(item, raised) for raised in parsed.raises]
        if raises:
            entry["raises"] = raises
        if item.inherited_from:
            entry["inheritedFrom"] = self.resolver.canonical.get(item.inherited_from, item.inherited_from)
        if item.members:
            entry["members"] = [self.entry(member) for member in item.members]
        return entry

    def parameters(self, item: Item, parsed: ParsedDocComment) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for parameter in visible_parameters(item.target):
            value: dict[str, Any] = {"name": parameter_name(parameter)}
            documented = parsed.parameters.get(parameter.name)
            kind = annotation_text(parameter.annotation)
            if kind is None and documented is not None:
                kind = annotation_text(documented.annotation)
            if kind:
                value["type"] = kind
            default = parameter_default(parameter)
            if default is not None:
                value["default"] = default
            if documented is not None and documented.description:
                value["description"] = self.render(documented.description, item.id)
            result.append(value)
        return result

    def returns(self, item: Item, parsed: ParsedDocComment) -> dict[str, Any] | None:
        result: dict[str, Any] = {}
        kind = annotation_text(item.target.returns)
        if kind and kind != "None" and item.kind != "constructor":
            result["type"] = kind
        if parsed.returns is not None and parsed.returns.description:
            result["description"] = self.render(parsed.returns.description, item.id)
        return result or None

    def raised(self, item: Item, raised: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"type": annotation_text(raised.annotation) or ""}
        if raised.description:
            result["description"] = self.render(raised.description, item.id)
        return result


def build_reference(api: Api) -> tuple[dict[str, Any], list[str]]:
    """The reference data, and any doc comment that could not be rendered."""
    builder = Builder(api.sections)
    sections = [
        {"id": section.id, "title": section.title, "entries": [builder.entry(item) for item in section.items]}
        for section in api.sections
    ]
    data = {
        "schema": SCHEMA,
        "language": "python",
        "package": DISTRIBUTION,
        "version": api.version,
        "sections": sections,
    }
    return data, builder.problems


def default_source() -> Path:
    """The checkout holding this script: .github/scripts/api_reference.py is two levels down."""
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail on a public name with no doc comment")
    parser.add_argument("--out", type=Path, help="write the reference data to this file")
    parser.add_argument("--source", type=Path, default=default_source(), help="the directory holding the package")
    arguments = parser.parse_args(argv)
    if not arguments.check and arguments.out is None:
        parser.error("give --check, --out or both")

    register_roles()
    api = walk_api(load_package(arguments.source))
    data, render_problems = build_reference(api)
    problems = list(api.problems) + render_problems

    if arguments.check:
        for section in api.sections:
            for item in section.items:
                problems += [f"{entry_id}: no doc comment" for entry_id in undocumented(item)]

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s) in the package's doc comments", file=sys.stderr)
        return 1

    if arguments.out is not None:
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
