"""The Python parity program: the counterpart of xcl's ``cmd/parity``.

It runs one parity fixture through the Python API and writes the same
normalised JSON record the Go program writes, so the two can be compared::

    python tests/parity/run_python.py --fixture <dir> --plugins <dir> --out <file>

The record covers, in order: validate, diff before the apply, apply,
entities and outputs after it, the state written, the diff of the changed
configuration when the fixture has one, entities after a load in a new
process, and destroy. Temporary paths are replaced by ``<tmp>`` and the
fixture directory by ``<fixture>``.

With ``--load``, which the program runs itself with for the load stage, it
loads the state in ``--state`` with the fixture's types and prints the
entities.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TESTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_TESTS)

# run as a script, the interpreter puts this directory first on sys.path,
# where types.py would shadow the standard library's types module that
# nearly every other import needs, so it is removed before anything else is
# imported; the package root and the tests directory go there instead
sys.path[:] = [p for p in sys.path if p not in ("", _HERE)]
for _path in (_ROOT, _TESTS):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import argparse  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from typing import Any, Callable, Optional  # noqa: E402

import xcl  # noqa: E402
from xcl._client import default_client  # noqa: E402
from xcl._core import core_pb2  # noqa: E402

from parity import types as fixture_types  # noqa: E402

# RECORDING_PLUGIN_NAME is the file name of the recording fixture plugin
# binary under --plugins
RECORDING_PLUGIN_NAME = "xcl-plugin-recording"


class Fixture:
    """A fixture directory read."""

    def __init__(self, directory: str) -> None:
        self.dir = os.path.abspath(directory)
        self.name = os.path.basename(self.dir)
        self.main = os.path.join(self.dir, "main.xcl")
        if not os.path.exists(self.main):
            raise SystemExit(f"fixture {directory} has no main.xcl")

        changed = os.path.join(self.dir, "changed", "main.xcl")
        self.changed: Optional[str] = changed if os.path.exists(changed) else None

        types_path = os.path.join(self.dir, "types.json")
        with open(types_path, encoding="utf-8") as handle:
            self.types: list[dict[str, Any]] = json.load(handle)

        if self.name not in fixture_types.FIXTURES:
            raise SystemExit(f"fixture {self.name} has no Python types in tests/parity/types.py")

        self.variables: dict[str, Any] = {}
        variables_path = os.path.join(self.dir, "variables.json")
        if os.path.exists(variables_path):
            with open(variables_path, encoding="utf-8") as handle:
                self.variables = json.load(handle)


def new_config(fixture: Fixture, plugins: str, state_dir: str, tmp: str) -> xcl.Config:
    """The Config a fixture runs with, exactly as the Go program builds it.

    Its types and ``slugify`` on a local registry, the recording plugin when
    a plugins directory is given, state in ``state_dir``, and the fixture's
    variables with ``<tmp>`` expanded to ``tmp``.
    """
    local = xcl.LocalRegistry()

    for cls in fixture_types.register(fixture.name):
        local.register_type(cls)

    local.register_function(fixture_types.slugify, "slugify")

    if plugins:
        name = RECORDING_PLUGIN_NAME
        if sys.platform == "win32":
            name += ".exe"
        local.register_external_plugin(os.path.join(plugins, name))

    variables = {}
    for key, value in fixture.variables.items():
        if isinstance(value, str):
            value = value.replace("<tmp>", tmp)
        variables[key] = value

    return xcl.Config(registries=[local], state_path=state_dir, variables=variables)


def attempt(operation: Callable[..., Any], *args: Any) -> tuple[Any, Optional[xcl.Error]]:
    """Call ``operation`` and return what it returned, or the engine error it raised."""
    try:
        return operation(*args), None
    except xcl.Error as exc:
        return None, exc


def raw_entities(config: xcl.Config) -> list[Any]:
    """Every entity as the engine renders it, decoded, without hydrating into classes."""
    response = default_client().call(config.handle, "Entities", core_pb2.EntitiesRequest())
    return [json.loads(entity) for entity in response.entities]


def run(fixture_dir: str, plugins: str) -> dict[str, Any]:
    """Run every stage of a fixture and return the record."""
    fixture = Fixture(fixture_dir)

    tmp = tempfile.mkdtemp(prefix="xcl-parity-")
    try:
        # the plugin registry caches under HOME; the engine is loaded lazily
        # by the first Config, so it reads the environment after this
        os.environ["HOME"] = os.path.join(tmp, "home")

        state_dir = os.path.join(tmp, "state")

        n = Normaliser(tmp=tmp, fixture=fixture.dir)
        record: dict[str, Any] = {}

        config = new_config(fixture, plugins, state_dir, tmp)

        _, err = attempt(config.validate, fixture.main)
        record["validate"] = n.outcome(err)
        record["diff_before"] = n.diff(*attempt(config.diff, fixture.main))

        _, apply_err = attempt(config.apply, fixture.main)
        record["apply"] = n.outcome(apply_err)
        record["entities"] = n.entities(raw_entities(config))
        record["outputs"] = n.value(config.outputs())
        record["state"] = n.state(state_dir)

        if fixture.changed is not None:
            record["diff_changed"] = n.diff(*attempt(config.diff, fixture.changed))

        if apply_err is None:
            loaded = load_in_new_process(fixture.dir, plugins, state_dir, tmp)
            record["load"] = n.value(loaded)

            _, destroy_err = attempt(config.destroy)
            record["destroy"] = n.outcome(destroy_err)
            record["after_destroy"] = {
                "entities": n.entities(raw_entities(config)),
                "state": n.state(state_dir),
            }

        return record
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def load_in_new_process(fixture_dir: str, plugins: str, state_dir: str, tmp: str) -> Any:
    """Run this program with ``--load`` and return the entities it printed."""
    command = [
        sys.executable,
        os.path.abspath(__file__),
        "--load",
        "--fixture",
        fixture_dir,
        "--plugins",
        plugins,
        "--state",
        state_dir,
        "--tmp",
        tmp,
    ]
    env = dict(os.environ, HOME=os.path.join(tmp, "home"))
    completed = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=sys.stderr, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"load in a new process: exit status {completed.returncode}")

    out = completed.stdout.decode()
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"load in a new process: the load printed {out!r}: {exc}") from exc


def run_load(fixture_dir: str, plugins: str, state_dir: str, tmp: str) -> None:
    """The ``--load`` mode: load the state and print the entities."""
    fixture = Fixture(fixture_dir)
    config = new_config(fixture, plugins, state_dir, tmp)

    n = Normaliser(tmp=tmp, fixture=fixture.dir)

    _, err = attempt(config.load)
    result: dict[str, Any] = {"load": n.outcome(err)}
    result["entities"] = n.entities(raw_entities(config))

    print(json.dumps(result))


class Normaliser:
    """Renders values with the run's paths replaced, as the Go normaliser does."""

    def __init__(self, *, tmp: str, fixture: str) -> None:
        self.tmp = tmp
        self.fixture = fixture

    def outcome(self, err: Optional[xcl.Error]) -> dict[str, Any]:
        """Whether an operation succeeded, and on failure its error and each problem it collects."""
        if err is None:
            return {"ok": True}

        out: dict[str, Any] = {"ok": False, "error": self.problem(err)}

        config_error = _first(err, lambda e: e.code == "config")
        if config_error is not None:
            problems = [self.problem(cause) for cause in config_error.causes]
            # the Go program sorts by fmt.Sprint of each problem map, so the
            # same key is built here: keys in order, "map[k:v k:v]"
            problems.sort(key=_go_sprint_key)
            out["problems"] = problems

        return out

    def problem(self, err: xcl.Error) -> dict[str, Any]:
        """One error: its code, and for a positioned problem its file, line, column and summary.

        The Go program matches a ParserError anywhere in the error's tree
        first, then a ConfigError; the engine crosses a ParserError as the
        error with ``file``, ``line``, ``column`` and ``summary`` details.
        """
        positioned = _first(err, lambda e: "file" in e.details)
        if positioned is not None:
            return {
                "code": "config",
                "file": self.path(positioned.details.get("file", "")),
                "line": _int(positioned.details.get("line")),
                "column": _int(positioned.details.get("column")),
                "summary": self.text(positioned.details.get("summary", "")),
            }

        if _first(err, lambda e: e.code == "config") is not None:
            return {"code": "config"}

        return {"code": "internal", "message": self.text(err.message)}

    def diff(self, diff: Optional[xcl.Diff], err: Optional[xcl.Error]) -> Any:
        """A diff, or the error it failed with."""
        if err is not None:
            return self.outcome(err)
        assert diff is not None
        return self.value(diff.raw)

    def entities(self, entities: list[Any]) -> list[Any]:
        """Entities as JSON, sorted by id."""
        rendered = [self.value(entity) for entity in entities]
        return _sorted_by_id(rendered)

    def state(self, state_dir: str) -> Any:
        """The records of the state directory, sorted by id; ``None`` when there are none."""
        path = os.path.join(state_dir, "state.json")
        try:
            with open(path, encoding="utf-8") as handle:
                data = handle.read()
        except OSError:
            return None

        try:
            records = json.loads(data)
        except json.JSONDecodeError:
            return {"error": "state is not a JSON array"}
        if not isinstance(records, list):
            return {"error": "state is not a JSON array"}

        return _sorted_by_id([self.walk(record) for record in records])

    def value(self, value: Any) -> Any:
        """Any value through JSON, with the run's paths replaced."""
        try:
            decoded = json.loads(json.dumps(value))
        except (TypeError, ValueError) as exc:
            return {"error": str(exc)}
        return self.walk(decoded)

    def walk(self, value: Any) -> Any:
        """Replace paths in every string of a decoded JSON value."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.walk(item) for item in value]
        if isinstance(value, dict):
            return {key: self.walk(item) for key, item in value.items()}
        return value

    def path(self, path: str) -> str:
        """Replace the fixture and temporary directories in a path, written with forward slashes."""
        return self.text(path.replace(os.sep, "/"))

    def text(self, text: str) -> str:
        """Replace the fixture and temporary directories wherever they appear."""
        for directory in (self.fixture, self.fixture.replace(os.sep, "/")):
            text = text.replace(directory, "<fixture>")
        for directory in (self.tmp, self.tmp.replace(os.sep, "/")):
            text = text.replace(directory, "<tmp>")
        return text


def _first(err: xcl.Error, matches: Callable[[xcl.Error], bool]) -> Optional[xcl.Error]:
    """The first error in the tree, depth first, that ``matches``; how Go's errors.As walks it."""
    if matches(err):
        return err
    for cause in err.causes:
        found = _first(cause, matches)
        if found is not None:
            return found
    return None


def _int(value: Optional[str]) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


def _go_sprint_key(problem: dict[str, Any]) -> str:
    """The text ``fmt.Sprint`` gives a Go ``map[string]any``: keys sorted, ``map[k:v k:v]``."""
    parts = []
    for key in sorted(problem):
        parts.append(f"{key}:{_go_sprint_value(problem[key])}")
    return "map[" + " ".join(parts) + "]"


def _go_sprint_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return _go_sprint_key(value)
    if isinstance(value, list):
        return "[" + " ".join(_go_sprint_value(v) for v in value) + "]"
    return str(value)


def _sorted_by_id(rendered: list[Any]) -> list[Any]:
    return sorted(rendered, key=_entity_id)


def _entity_id(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    meta = value.get("meta")
    if not isinstance(meta, dict):
        return ""
    identifier = meta.get("id", "")
    return identifier if isinstance(identifier, str) else ""


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="run one parity fixture through the Python API")
    parser.add_argument("--fixture", required=True, help="the fixture directory")
    parser.add_argument("--plugins", default="", help="the directory holding the fixture plugin binaries")
    parser.add_argument("--out", default="", help="the file the record is written to, stdout when empty")
    parser.add_argument("--load", action="store_true", help="load the state in --state and print the entities")
    parser.add_argument("--state", default="", help="the state directory, with --load")
    parser.add_argument("--tmp", default="", help="the temporary directory of the run, with --load")
    args = parser.parse_args(argv)

    if args.load:
        run_load(args.fixture, args.plugins, args.state, args.tmp)
        return 0

    record = run(args.fixture, args.plugins)
    encoded = json.dumps(record, indent=2, sort_keys=True)

    if not args.out:
        print(encoded)
        return 0

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(encoded + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
