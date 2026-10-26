"""The Python parity program: the counterpart of xcl's ``cmd/parity``.

It runs one parity fixture through the Python API and writes the same
normalised JSON record the Go program writes, so the two can be compared::

    python tests/parity/run_python.py --fixture <dir> --plugins <dir> --out <file>

The record covers, in order: validate, diff before the apply, apply,
entities and outputs after it, the state written, the configuration text of
every entity under each combination of the encode choices, the diff of the
changed configuration when the fixture has one, entities after a load in a new
process, and destroy. It also covers what a person is shown, through the
package's own printing and logging: the report ``xcl.format_error`` gives for
a failed validate and apply, the text ``print_entity`` prints for every entity
with computed values, the change summary ``xcl.print_diff`` prints for the
diff before the apply and for the changed configuration, and the level,
message, resource and operation of every event ``xcl.logging_handler`` writes
up to the load. Temporary paths are replaced by ``<tmp>`` and the fixture
directory by ``<fixture>``.

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
import io  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
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

        # the addresses of the entities built by hand for the encode stage
        self.hand_built: list[str] = []
        hand_built_path = os.path.join(self.dir, "hand_built.json")
        if os.path.exists(hand_built_path):
            with open(hand_built_path, encoding="utf-8") as handle:
                self.hand_built = json.load(handle)


def new_config(
    fixture: Fixture,
    plugins: str,
    state_dir: str,
    tmp: str,
    on_event: Optional[Callable[[xcl.Event], None]] = None,
) -> xcl.Config:
    """The Config a fixture runs with, exactly as the Go program builds it.

    Its types and ``slugify`` on a local registry, the recording plugin when
    a plugins directory is given, state in ``state_dir``, the fixture's
    variables with ``<tmp>`` expanded to ``tmp``, and ``on_event``, when
    given, receiving its events.
    """
    local = xcl.LocalRegistry()

    for type_name, subtype, cls in fixture_types.FIXTURES[fixture.name]:
        local.register_type(cls, type_name, subtype)

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

    return xcl.Config(registries=[local], state_path=state_dir, variables=variables, on_event=on_event)


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

        # every event the Config emits is written through the package's
        # logging bridge to a logger that keeps each record, at every level
        logs = LogRecorder()

        config = new_config(fixture, plugins, state_dir, tmp, xcl.logging_handler(logs.logger))

        _, err = attempt(config.validate, fixture.main)
        record["validate"] = n.outcome(err)
        record["printed_validate"] = n.printed_error(err)
        before, before_err = attempt(config.diff, fixture.main)
        record["diff_before"] = n.diff(before, before_err)
        record["printed_diff_before"] = n.printed_diff(before, before_err)

        _, apply_err = attempt(config.apply, fixture.main)
        record["apply"] = n.outcome(apply_err)
        record["printed_apply"] = n.printed_error(apply_err)
        record["entities"] = n.entities(raw_entities(config))
        record["outputs"] = n.value(config.outputs())
        record["state"] = n.state(state_dir)
        record["encode"] = encode_section(config, fixture, state_dir, n)
        record["printed_entities"] = printed_entities_section(config, n)

        if fixture.changed is not None:
            changed, changed_err = attempt(config.diff, fixture.changed)
            record["diff_changed"] = n.diff(changed, changed_err)
            record["printed_diff_changed"] = n.printed_diff(changed, changed_err)

        record["log"] = n.log(logs.entries)

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


# ENCODE_CHOICES are the four encode choices, by the name the record gives
# each, in the order their names are joined in a combination's name
ENCODE_CHOICES = [
    ("computed", "include_computed"),
    ("empty", "include_empty"),
    ("reveal", "reveal_sensitive"),
    ("references", "show_references"),
]

# BUILTIN_TYPES are xcl's own block types, which the encoder refuses and the
# encode stage leaves out
BUILTIN_TYPES = ("variable", "output", "module", "root")


def encode_combinations() -> list[tuple[str, dict[str, bool]]]:
    """All sixteen combinations of the encode choices, as the Go program orders and names them.

    A combination is named by the choices it turns on, joined with ``+`` in
    the order of ``ENCODE_CHOICES``, and ``none`` when it turns on none.
    """
    combinations = []
    for mask in range(1 << len(ENCODE_CHOICES)):
        names = []
        choices = {}
        for bit, (name, keyword) in enumerate(ENCODE_CHOICES):
            on = bool(mask & (1 << bit))
            choices[keyword] = on
            if on:
                names.append(name)
        combinations.append(("+".join(names) or "none", choices))
    return combinations


def encode_section(config: xcl.Config, fixture: Fixture, state_dir: str, n: Normaliser) -> dict[str, Any]:
    """The configuration text of every entity that is not a builtin, by address, under every combination.

    ``looked_up`` encodes the entity a lookup returns, ``saved`` its record
    in state, and, for the addresses the fixture's ``hand_built.json`` lists,
    ``hand_built`` the instance ``types.HAND_BUILT`` builds for it. A failure
    is recorded as its outcome.
    """
    saved = saved_records(state_dir)
    builders = fixture_types.HAND_BUILT.get(fixture.name, {})

    encoded: dict[str, Any] = {}
    for raw in raw_entities(config):
        meta = raw.get("meta") or {}
        if meta.get("type") in BUILTIN_TYPES:
            continue
        address = meta.get("id", "")

        entity = config.find(None, address)
        looked_up = {}
        saved_texts: dict[str, Any] = {}
        hand_built = {}
        for name, choices in encode_combinations():
            looked_up[name] = n.encoded(*attempt(lambda: config.encode_entity(entity, **choices)))

            record = saved.get(address)
            if record is None:
                saved_texts[name] = {"ok": False, "error": {"code": "missing_saved_record"}}
            else:
                saved_texts[name] = n.encoded(*attempt(lambda: config.encode_saved_entity(record, **choices)))

            if address in fixture.hand_built:
                built = builders[address]()
                hand_built[name] = n.encoded(*attempt(lambda: config.encode_entity(built, **choices)))

        texts: dict[str, Any] = {"looked_up": looked_up, "saved": saved_texts}
        if address in fixture.hand_built:
            texts["hand_built"] = hand_built
        encoded[address] = texts

    return encoded


def printed_entities_section(config: xcl.Config, n: Normaliser) -> dict[str, Any]:
    """The text ``print_entity`` prints, with computed values, for every entity that is not a builtin, by address.

    A failure is recorded as its outcome.
    """
    printed: dict[str, Any] = {}
    for raw in raw_entities(config):
        meta = raw.get("meta") or {}
        if meta.get("type") in BUILTIN_TYPES:
            continue
        address = meta.get("id", "")

        out = io.StringIO()
        _, err = attempt(lambda: config.print_entity(config.find(None, address), out, include_computed=True))
        printed[address] = n.outcome(err) if err is not None else n.text(out.getvalue())

    return printed


# LEVEL_NAMES names a logging level as the record does, as Go names slog's
LEVEL_NAMES = {logging.DEBUG: "debug", logging.INFO: "info", logging.WARNING: "warn", logging.ERROR: "error"}


class LogRecorder(logging.Handler):
    """A logging handler that keeps each record's level, message, resource and operation, at every level.

    ``logger`` is a logger of its own, at debug level, passing nothing on, so
    the records reach no other handler.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.entries: list[dict[str, str]] = []
        self.logger = logging.getLogger(f"xcl.parity.{id(self)}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.logger.addHandler(self)

    def emit(self, record: logging.LogRecord) -> None:
        self.entries.append(
            {
                "level": LEVEL_NAMES.get(record.levelno, "info"),
                "message": record.getMessage(),
                "resource": getattr(record, "resource", ""),
                "operation": getattr(record, "operation", ""),
            }
        )


def saved_records(state_dir: str) -> dict[str, bytes]:
    """The records of the state directory, by entity id, as JSON bytes."""
    try:
        with open(os.path.join(state_dir, "state.json"), encoding="utf-8") as handle:
            records = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(records, list):
        return {}

    by_id = {}
    for record in records:
        if isinstance(record, dict) and isinstance(record.get("meta"), dict):
            by_id[record["meta"].get("id", "")] = json.dumps(record).encode()
    return by_id


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
        """One error: its code, and for a diagnostic its file, line, column, summary, detail, block and field.

        The Go program matches a Diagnostic anywhere in the error's tree
        first, then a ConfigError. The engine crosses a Diagnostic as the
        error with a ``severity`` detail beside its ``summary``, ``detail``,
        ``entity`` and ``field``, and its ``file``, ``line`` and ``column``
        when it has a position.
        """
        diagnostic = _first(err, lambda e: "severity" in e.details)
        if diagnostic is not None:
            details = diagnostic.details
            record: dict[str, Any] = {
                "code": "config",
                "summary": self.text(details.get("summary", "")),
                "detail": self.text(details.get("detail", "")),
                "entity": details.get("entity", ""),
                "field": details.get("field", ""),
            }
            if "file" in details:
                record["file"] = self.path(details["file"])
                record["line"] = _int(details.get("line"))
                record["column"] = _int(details.get("column"))
            return record

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

    def encoded(self, text: Optional[str], err: Optional[xcl.Error]) -> Any:
        """Encoded text with the run's paths replaced, or the outcome of the error it failed with."""
        if err is not None:
            return self.outcome(err)
        assert text is not None
        return self.text(text)

    def printed_error(self, err: Optional[xcl.Error]) -> str:
        """The report ``xcl.format_error`` gives for an error, plain and wrapped at 80 columns, or ``""`` for none."""
        if err is None:
            return ""
        return self.text(xcl.format_error(err))

    def printed_diff(self, diff: Optional[xcl.Diff], err: Optional[xcl.Error]) -> Any:
        """The change summary ``xcl.print_diff`` prints for a diff, or the outcome the diff failed with."""
        if err is not None:
            return self.outcome(err)
        assert diff is not None
        out = io.StringIO()
        xcl.print_diff(diff, out)
        return self.text(out.getvalue())

    def log(self, entries: list[dict[str, str]]) -> list[dict[str, str]]:
        """The logged events with paths replaced in their messages, sorted as the Go program sorts them.

        By operation, resource, level and message, so the order the events
        arrived in does not count.
        """
        rendered = [dict(entry, message=self.text(entry["message"])) for entry in entries]
        return sorted(rendered, key=lambda e: (e["operation"], e["resource"], e["level"], e["message"]))

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
        for directory in _dir_forms(self.fixture):
            text = text.replace(directory, "<fixture>")
        for directory in _dir_forms(self.tmp):
            text = text.replace(directory, "<tmp>")
        return text


def _dir_forms(directory: str) -> tuple[str, str, str]:
    """The ways a directory appears in the record, as the Go program's dirForms lists them.

    As it is, with forward slashes, and with each backslash doubled, as
    configuration text writes a Windows path inside a quoted string.
    """
    return (directory.replace("\\", "\\\\"), directory, directory.replace(os.sep, "/"))


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
