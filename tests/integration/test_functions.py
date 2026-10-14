"""Python functions called from configuration, against the real engine.

Every test registers a plain Python function on a :class:`xcl.LocalRegistry`
and calls it from configuration written to a temporary directory. The
function's signature comes from its annotations; the engine calls back into
Python for every call site, possibly more than once per site (parse, decide
and apply passes), so the tests assert on the arguments seen rather than on
how many times a function ran.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

import xcl

pytestmark = pytest.mark.usefixtures("engine")


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    """Plugins are cached under HOME, so every test gets its own."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


# -- entity classes ---------------------------------------------------------


@dataclass
class App:
    """A config-only type whose string fields are filled in by function calls."""

    name: str = ""
    secret: xcl.Sensitive[str] | None = None
    token: xcl.Sensitive[str] | None = None


@dataclass
class NumApp:
    """A config-only type with a numeric field filled in by a function call."""

    replicas: int = 0


class MemoryStore:
    """A state store that keeps the engine's records in memory."""

    def __init__(self) -> None:
        self.saved: list[bytes] = []

    def load(self) -> list[bytes]:
        return list(self.saved)

    def save(self, entities: list[bytes]) -> None:
        self.saved = list(entities)

    def exists(self) -> bool:
        return bool(self.saved)

    def clear(self) -> None:
        self.saved = []

    def record(self, address: str) -> dict:
        """The saved record of the entity at ``address``, decoded."""
        for raw in self.saved:
            decoded = json.loads(raw)
            if decoded.get("meta", {}).get("id") == address:
                return decoded
        raise KeyError(address)


# -- helpers ----------------------------------------------------------------


def write_config(directory: Path, text: str, name: str = "main.xcl") -> Path:
    path = directory / name
    path.write_text(textwrap.dedent(text).lstrip())
    return path


def slugify(title: str) -> str:
    return title.lower().replace(" ", "-")


def registry_with(fn, name: str | None = None) -> xcl.LocalRegistry:
    """A registry declaring both entity classes and offering ``fn``."""
    found = xcl.LocalRegistry()
    found.register_type(App, "fn_app")
    found.register_type(NumApp, "fn_num_app")
    found.register_function(fn, name=name)
    return found


# -- results and arguments --------------------------------------------------


def test_slugify_result_filled_in(tmp_path):
    config = write_config(
        tmp_path,
        """
        fn_app "web" {
          name = slugify("My App")
        }
        """,
    )

    with xcl.Config(registries=[registry_with(slugify)]) as c:
        c.apply(config)
        found = c.find(App, "fn_app.web")

    assert found.name == "my-app"


def test_function_called_with_json_arguments(tmp_path):
    seen: list[str] = []

    def record(title: str) -> str:
        seen.append(title)
        return title

    config = write_config(
        tmp_path,
        """
        fn_app "web" {
          name = record("My App")
        }
        """,
    )

    with xcl.Config(registries=[registry_with(record)]) as c:
        c.apply(config)

    assert seen
    assert all(title == "My App" for title in seen)
    assert all(isinstance(title, str) for title in seen)


def test_raising_function_fails_apply_at_call_position(tmp_path):
    def explode(title: str) -> str:
        raise ValueError("no slug for you")

    config = write_config(
        tmp_path,
        """
        fn_app "web" {
          name = explode("My App")
        }
        """,
    )

    with xcl.Config(registries=[registry_with(explode)]) as c:
        with pytest.raises(xcl.ConfigError) as raised:
            c.apply(config)

    problems = [p for p in raised.value.problems if "no slug for you" in p.message]
    assert problems, [p.message for p in raised.value.problems]
    assert problems[0].file.endswith("main.xcl")
    assert problems[0].line > 0


# -- name clashes ------------------------------------------------------------


def test_function_named_like_builtin_raises_clash():
    def upper(text: str) -> str:
        return text.upper()

    with pytest.raises(xcl.FunctionNameClashError) as raised:
        xcl.Config(registries=[registry_with(upper)])

    assert raised.value.details["name"] == "upper"
    assert raised.value.details["existing"] == "builtin"


def test_two_functions_same_name_raise_clash():
    first = xcl.LocalRegistry()
    first.register_function(slugify)
    second = xcl.LocalRegistry()
    second.register_function(slugify)

    with pytest.raises(xcl.FunctionNameClashError) as raised:
        xcl.Config(registries=[first, second])

    assert raised.value.details["name"] == "slugify"


def test_same_name_twice_on_one_registry_refused():
    registry = xcl.LocalRegistry()
    registry.register_function(slugify)

    with pytest.raises(xcl.SchemaError):
        registry.register_function(slugify)


# -- refused signatures ------------------------------------------------------


def test_unsupported_annotation_refused_at_registration():
    def bad(x: object) -> str:
        return str(x)

    registry = xcl.LocalRegistry()

    with pytest.raises(xcl.SchemaError):
        registry.register_function(bad)


def test_variadic_function_refused_by_engine():
    def join_all(*args: str) -> str:
        return "-".join(args)

    registry = xcl.LocalRegistry()
    registry.register_function(join_all)

    with pytest.raises(xcl.InvalidFunctionError) as raised:
        xcl.Config(registries=[registry])

    assert "variadic" in str(raised.value)


# -- sensitive values --------------------------------------------------------


def test_sensitive_argument_plain_and_result_sensitive(tmp_path):
    seen: list[object] = []

    def slug(title: str) -> str:
        seen.append(title)
        return title.lower().replace(" ", "-")

    config = write_config(
        tmp_path,
        """
        fn_app "a" {
          secret = "Hunter Two"
        }

        fn_app "b" {
          token = slug(fn_app.a.secret)
        }
        """,
    )
    store = MemoryStore()

    with xcl.Config(registries=[registry_with(slug)], state_store=store) as c:
        c.apply(config)
        found = c.find(App, "fn_app.b")

    assert "Hunter Two" in seen
    assert all(isinstance(title, str) for title in seen)
    assert isinstance(found.token, xcl.Sensitive)
    assert found.token.is_redacted
    assert store.record("fn_app.b")["token"] == "hunter-two"


# -- argument types ----------------------------------------------------------


def test_list_and_map_arguments(tmp_path):
    seen: list[tuple[list[str], dict[str, int]]] = []

    def describe(names: list[str], ports: dict[str, int]) -> str:
        seen.append((names, ports))
        return ",".join(names) + ":" + ",".join(f"{k}={v}" for k, v in ports.items())

    config = write_config(
        tmp_path,
        """
        fn_app "web" {
          name = describe(["a", "b"], { http = 80 })
        }
        """,
    )

    with xcl.Config(registries=[registry_with(describe)]) as c:
        c.apply(config)
        found = c.find(App, "fn_app.web")

    assert (["a", "b"], {"http": 80}) in seen
    names, ports = seen[0]
    assert isinstance(names, list)
    assert isinstance(ports, dict)
    assert isinstance(ports["http"], int)
    assert found.name == "a,b:http=80"


def test_number_and_bool_round_trip(tmp_path):
    seen: list[tuple[int, bool]] = []

    def double(n: int, really: bool) -> int:
        seen.append((n, really))
        return n * 2 if really else n

    config = write_config(
        tmp_path,
        """
        fn_num_app "web" {
          replicas = double(21, true)
        }
        """,
    )

    with xcl.Config(registries=[registry_with(double)]) as c:
        c.apply(config)
        found = c.find(NumApp, "fn_num_app.web")

    assert (21, True) in seen
    n, really = seen[0]
    assert isinstance(n, int)
    assert isinstance(really, bool)
    assert found.replicas == 42


# -- naming ------------------------------------------------------------------


def test_function_registered_under_other_name(tmp_path):
    config = write_config(
        tmp_path,
        """
        fn_app "web" {
          name = slug("My App")
        }
        """,
    )

    with xcl.Config(registries=[registry_with(slugify, name="slug")]) as c:
        c.apply(config)
        found = c.find(App, "fn_app.web")

    assert found.name == "my-app"
