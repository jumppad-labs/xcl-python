"""Tests of the API reference tool, over small packages made for each test.

The tool is a CI script rather than part of the package, so it is loaded from
its own path. No test reads the repository's own source.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).with_name("api_reference.py")
_spec = importlib.util.spec_from_file_location("api_reference", _SCRIPT)
api_reference = importlib.util.module_from_spec(_spec)
sys.modules["api_reference"] = api_reference
_spec.loader.exec_module(api_reference)


def write_package(root: Path, init: str, **modules: str) -> Path:
    package = root / "xcl"
    package.mkdir()
    (package / "__init__.py").write_text(init)
    for name, text in modules.items():
        (package / f"{name}.py").write_text(text)
    return root


DOCUMENTED = '''"""The package."""

__all__ = ["__version__", "Client", "connect", "LIMIT"]

__version__ = "1.2.3"
"""The package version."""

LIMIT = 10
"""The largest number of things."""


class Client:
    """A client.

    :param host: where to connect
    """

    def __init__(self, host: str = "localhost") -> None:
        self.host = host

    def fetch(self, key: str, *, default: int = 0) -> int:
        """Fetch a value, as :meth:`close` documents.

        :param key: what to fetch
        :returns: the value
        :raises KeyError: when it is missing
        """
        return default

    def close(self) -> None:
        """Close the client."""

    @property
    def open(self) -> bool:
        """Whether the client is open."""
        return True


def connect(host: str) -> Client:
    """Make a :class:`Client`."""
    return Client(host)
'''

UNDOCUMENTED_METHOD = '''"""The package."""

__all__ = ["__version__", "Client"]

__version__ = "1.2.3"
"""The package version."""


class Client:
    """A client."""

    def fetch(self) -> int:
        return 1
'''

INHERITED_UNDOCUMENTED = '''"""The package."""

from xcl._base import Child

__all__ = ["__version__", "Child"]

__version__ = "1.2.3"
"""The package version."""
'''

BASE_MODULE = '''"""Private."""


class Base:
    """The base."""

    def inherited(self) -> int:
        return 1


class Child(Base):
    """The child."""
'''

UNEXPORTED_NAME = '''"""The package."""

__all__ = ["__version__"]

__version__ = "1.2.3"
"""The package version."""


def hidden() -> int:
    return 1
'''

UNDOCUMENTED_CONSTANT = '''"""The package."""

__all__ = ["__version__", "LIMIT"]

__version__ = "1.2.3"
"""The package version."""

LIMIT = 10
'''

DOCUMENTED_CONSTANT = '''"""The package."""

__all__ = ["__version__", "LIMIT"]

__version__ = "1.2.3"
"""The package version."""

LIMIT = 10
"""The largest number of things."""
'''

BAD_MARKUP = '''"""The package."""

__all__ = ["__version__", "broken"]

__version__ = "1.2.3"
"""The package version."""


def broken() -> None:
    """An ``unterminated literal."""
'''

UNDOCUMENTED_ATTRIBUTE = '''"""The package."""

from dataclasses import dataclass

__all__ = ["__version__", "Point"]

__version__ = "1.2.3"
"""The package version."""


@dataclass
class Point:
    """A point."""

    x: int
    y: int = 0
'''

WITH_ASYNC = '''"""The package."""

__all__ = ["__version__", "Client"]

__version__ = "1.2.3"
"""The package version."""


class Client:
    """The synchronous client."""
'''

ASYNC_MODULE = '''"""The asyncio client."""

__all__ = ["Client"]


class Client:
    """The asyncio client."""
'''

EXPORTED_MODULE = '''"""The package."""

from xcl import tools

__all__ = ["__version__", "tools"]

__version__ = "1.2.3"
"""The package version."""
'''

TOOLS_MODULE = '''"""Tools."""

__all__ = ["hammer"]


def hammer() -> None:
    """Hit something."""


def internal() -> None:
    pass
'''

ERRORS = '''"""The package."""

__all__ = ["__version__", "Error", "BadError", "Client"]

__version__ = "1.2.3"
"""The package version."""


class Error(Exception):
    """Any error."""


class BadError(Error):
    """A bad one."""


class Client:
    """A client."""
'''


def check(source: Path) -> int:
    return api_reference.main(["--check", "--source", str(source)])


def generate(root: Path, source: Path) -> dict:
    out = root / "generated" / "reference.json"
    assert api_reference.main(["--out", str(out), "--source", str(source)]) == 0
    return json.loads(out.read_text())


def entry_ids(data: dict) -> list[str]:
    return [entry["id"] for section in data["sections"] for entry in section["entries"]]


def find_entry(data: dict, entry_id: str) -> dict:
    for section in data["sections"]:
        for entry in section["entries"]:
            if entry["id"] == entry_id:
                return entry
            for member in entry.get("members", []):
                if member["id"] == entry_id:
                    return member
    raise AssertionError(f"no entry {entry_id}")


def member_ids(entry: dict) -> list[str]:
    return [member["id"] for member in entry["members"]]


def test_check_passes_on_a_documented_package(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)

    assert check(source) == 0


def test_check_fails_on_an_undocumented_method(tmp_path):
    source = write_package(tmp_path, UNDOCUMENTED_METHOD)

    assert check(source) == 1


def test_check_names_an_undocumented_method(tmp_path, capsys):
    source = write_package(tmp_path, UNDOCUMENTED_METHOD)

    check(source)

    assert "xcl.Client.fetch: no doc comment" in capsys.readouterr().err


def test_check_reports_an_inherited_member(tmp_path, capsys):
    source = write_package(tmp_path, INHERITED_UNDOCUMENTED, _base=BASE_MODULE)

    check(source)

    assert "xcl.Child.inherited: no doc comment" in capsys.readouterr().err


def test_check_ignores_a_name_outside_the_export_list(tmp_path):
    source = write_package(tmp_path, UNEXPORTED_NAME)

    assert check(source) == 0


def test_check_fails_on_a_constant_with_no_doc_comment(tmp_path, capsys):
    source = write_package(tmp_path, UNDOCUMENTED_CONSTANT)

    check(source)

    assert "xcl.LIMIT: no doc comment" in capsys.readouterr().err


def test_check_passes_on_a_constant_with_a_doc_comment(tmp_path):
    source = write_package(tmp_path, DOCUMENTED_CONSTANT)

    assert check(source) == 0


def test_check_fails_on_invalid_markup(tmp_path, capsys):
    source = write_package(tmp_path, BAD_MARKUP)

    check(source)

    assert "xcl.broken: invalid doc comment" in capsys.readouterr().err


def test_check_needs_no_doc_comment_on_an_attribute_or_constructor(tmp_path):
    source = write_package(tmp_path, UNDOCUMENTED_ATTRIBUTE)

    assert check(source) == 0


def test_check_follows_an_exported_modules_export_list(tmp_path):
    source = write_package(tmp_path, EXPORTED_MODULE, tools=TOOLS_MODULE)

    assert check(source) == 0


def test_data_carries_the_package_version(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)

    assert generate(tmp_path, source)["version"] == "1.2.3"


def test_data_names_the_language_and_package(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)
    data = generate(tmp_path, source)

    assert (data["schema"], data["language"], data["package"]) == (1, "python", "xcl-lang")


def test_data_has_an_entry_for_every_public_name(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)

    assert entry_ids(generate(tmp_path, source)) == [
        "xcl",
        "xcl.__version__",
        "xcl.Client",
        "xcl.connect",
        "xcl.LIMIT",
    ]


def test_data_omits_a_name_outside_the_export_list(tmp_path):
    source = write_package(tmp_path, UNEXPORTED_NAME)

    assert "xcl.hidden" not in entry_ids(generate(tmp_path, source))


def test_data_gives_a_function_its_signature(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)
    entry = find_entry(generate(tmp_path, source), "xcl.Client.fetch")

    assert entry["signature"] == "fetch(key: str, *, default: int = 0) -> int"


def test_data_gives_a_parameter_its_type_default_and_description(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)
    entry = find_entry(generate(tmp_path, source), "xcl.Client.fetch")

    assert entry["parameters"] == [
        {"name": "key", "type": "str", "description": "<p>what to fetch</p>"},
        {"name": "default", "type": "int", "default": "0"},
    ]


def test_data_gives_a_function_its_return_value(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)
    entry = find_entry(generate(tmp_path, source), "xcl.Client.fetch")

    assert entry["returns"] == {"type": "int", "description": "<p>the value</p>"}


def test_data_gives_a_function_the_errors_it_raises(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)
    entry = find_entry(generate(tmp_path, source), "xcl.Client.fetch")

    assert entry["raises"] == [{"type": "KeyError", "description": "<p>when it is missing</p>"}]


def test_data_renders_a_cross_reference_to_a_public_name_as_a_link(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)
    entry = find_entry(generate(tmp_path, source), "xcl.connect")

    assert 'href="#xcl.Client"' in entry["description"]


def test_data_resolves_a_cross_reference_within_the_enclosing_class(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)
    entry = find_entry(generate(tmp_path, source), "xcl.Client.fetch")

    assert 'href="#xcl.Client.close"' in entry["description"]


def test_data_renders_an_inline_literal_as_code(tmp_path):
    source = write_package(tmp_path, UNEXPORTED_NAME.replace('"""The package."""', '"""The ``xcl`` package."""'))

    assert "<code>xcl</code>" in find_entry(generate(tmp_path, source), "xcl")["description"]


def test_data_has_a_classes_constructor_from_its_doc_comment(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)
    entry = find_entry(generate(tmp_path, source), "xcl.Client.__init__")

    assert entry["parameters"] == [
        {"name": "host", "type": "str", "default": "'localhost'", "description": "<p>where to connect</p>"}
    ]


def test_data_lists_a_constructor_method_and_property_as_members(tmp_path):
    source = write_package(tmp_path, DOCUMENTED)
    entry = find_entry(generate(tmp_path, source), "xcl.Client")
    kinds = {member["name"]: member["kind"] for member in entry["members"]}

    assert (kinds["__init__"], kinds["fetch"], kinds["open"]) == ("constructor", "method", "property")


def test_data_shows_an_inherited_member_on_the_class(tmp_path):
    source = write_package(tmp_path, INHERITED_UNDOCUMENTED, _base=BASE_MODULE)
    entry = find_entry(generate(tmp_path, source), "xcl.Child")

    assert "xcl.Child.inherited" in member_ids(entry)


def test_data_names_where_a_member_is_inherited_from(tmp_path):
    source = write_package(tmp_path, INHERITED_UNDOCUMENTED, _base=BASE_MODULE)
    entry = find_entry(generate(tmp_path, source), "xcl.Child.inherited")

    assert entry["inheritedFrom"] == "xcl._base.Base"


def test_data_lists_a_dataclass_field_and_constructor(tmp_path):
    source = write_package(tmp_path, UNDOCUMENTED_ATTRIBUTE)
    entry = find_entry(generate(tmp_path, source), "xcl.Point")

    assert member_ids(entry) == ["xcl.Point.__init__", "xcl.Point.x", "xcl.Point.y"]


def test_data_labels_the_synchronous_client(tmp_path):
    source = write_package(tmp_path, WITH_ASYNC, aio=ASYNC_MODULE)

    assert find_entry(generate(tmp_path, source), "xcl.Client")["label"] == "synchronous"


def test_data_labels_the_asyncio_client(tmp_path):
    source = write_package(tmp_path, WITH_ASYNC, aio=ASYNC_MODULE)

    assert find_entry(generate(tmp_path, source), "xcl.aio.Client")["label"] == "asyncio"


def test_data_puts_the_asyncio_module_after_the_main_section(tmp_path):
    source = write_package(tmp_path, WITH_ASYNC, aio=ASYNC_MODULE)
    data = generate(tmp_path, source)

    assert [section["id"] for section in data["sections"]] == ["xcl", "xcl.aio"]


def test_data_gives_an_exported_module_its_own_section(tmp_path):
    source = write_package(tmp_path, EXPORTED_MODULE, tools=TOOLS_MODULE)
    data = generate(tmp_path, source)

    assert [entry["id"] for entry in data["sections"][1]["entries"]] == ["xcl.tools", "xcl.tools.hammer"]


def test_data_groups_errors_in_a_section_of_their_own(tmp_path):
    source = write_package(tmp_path, ERRORS)
    data = generate(tmp_path, source)

    assert [entry["id"] for entry in data["sections"][-1]["entries"]] == ["xcl.Error", "xcl.BadError"]


def test_generate_fails_on_invalid_markup(tmp_path):
    source = write_package(tmp_path, BAD_MARKUP)
    out = tmp_path / "reference.json"

    assert api_reference.main(["--out", str(out), "--source", str(source)]) == 1
