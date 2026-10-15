"""The synchronous API against the real engine.

Every test applies configuration written to a temporary directory through
``xcl.Config``, with config-only types registered from Python and, where a
provider is needed, the fixture plugins built from the xcl checkout.
"""

from __future__ import annotations

import json
import re
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

import xcl
from sync_entities import Health, JsonLinesStore, Listener, MemoryStore, PlainApp, SyncApp, SyncDatabase, Volume, registry

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

pytestmark = pytest.mark.usefixtures("engine")

KEY = bytes(range(32))

WEB = """
sync_app "web" {
  image = "nginx"
}
"""


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    """Plugins are cached under HOME, so every test gets its own."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def write_config(directory: Path, text: str, name: str = "main.xcl") -> Path:
    path = directory / name
    path.write_text(textwrap.dedent(text).lstrip())
    return path


def recording_config(directory: Path, log: Path, value: str) -> Path:
    return write_config(
        directory,
        f"""
        resource "recording" "one" {{
          log = "{log.as_posix()}"
          value = "{value}"
        }}
        """,
    )


def plugin_registry(plugin: Path) -> xcl.LocalRegistry:
    found = xcl.LocalRegistry()
    found.register_external_plugin(plugin)
    return found


def run_script(script: str) -> subprocess.CompletedProcess[str]:
    """Run ``script`` in a fresh interpreter that can import xcl and sync_entities."""
    preamble = f"import sys\nsys.path[:0] = [{str(ROOT)!r}, {str(HERE)!r}]\n"
    return subprocess.run([sys.executable, "-c", preamble + textwrap.dedent(script)], capture_output=True, text=True, timeout=60)


# -- decoding into registered classes --------------------------------------


def test_registered_class_decodes_and_is_found(tmp_path):
    config = write_config(tmp_path, WEB)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncApp, "sync_app.web")
        untyped = c.find(None, "sync_app.web")

    assert isinstance(found, SyncApp)
    assert found.image == "nginx"
    assert found.meta.id == "sync_app.web"
    assert found.meta.name == "web"
    assert isinstance(untyped, SyncApp)


def test_subtype_class_found_at_address(tmp_path):
    config = write_config(
        tmp_path,
        """
        sync_database "postgres" "main" {
          version = "15"
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncDatabase, "sync_database.postgres.main")

    assert isinstance(found, SyncDatabase)
    assert found.version == "15"
    assert found.meta.type == "sync_database"
    assert found.meta.subtype == "postgres"


def test_required_field_missing_fails_at_block(tmp_path):
    config = write_config(
        tmp_path,
        """
        sync_app "bad" {
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        with pytest.raises(xcl.ConfigError) as raised:
            c.apply(config)

    problem = raised.value.problems[0]
    assert problem.file.endswith("main.xcl")
    assert problem.line == 1
    assert "image" in problem.message


def test_optional_field_gets_default(tmp_path):
    config = write_config(tmp_path, WEB)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncApp, "sync_app.web")

    assert found.replicas == 2
    assert found.health is None
    assert found.volume == []
    assert found.listener == {}


# -- plain dataclasses and each configuration's classes --------------------


PLAIN_WEB = """
plain_app "web" {
  image = "nginx"
  replicas = 3
}
"""

DISABLED_WEB = """
sync_app "base" {
  image = "redis"
}

sync_app "web" {
  image = "nginx"
  disabled = true
  depends_on = ["sync_app.base"]
}
"""

APP_WEB = """
app "web" {
  image = "nginx"
}
"""


def plain_registry() -> xcl.LocalRegistry:
    found = xcl.LocalRegistry()
    found.register_type(PlainApp, "plain_app")
    return found


def app_registry(cls: type) -> xcl.LocalRegistry:
    """A registry declaring ``cls`` as the block type ``app``."""
    found = xcl.LocalRegistry()
    found.register_type(cls, "app")
    return found


def test_plain_dataclass_through_whole_lifecycle(tmp_path):
    config = write_config(tmp_path, PLAIN_WEB)

    with xcl.Config(registries=[plain_registry()], state_path=tmp_path / "state") as c:
        c.validate(config)
        c.apply(config)
        found = c.find(PlainApp, "plain_app.web")
        diff = c.diff(config)
        c.destroy()
        remaining = c.entity_count()

    assert isinstance(found, PlainApp)
    assert found == PlainApp(image="nginx", replicas=3, name="web")
    assert isinstance(diff, xcl.Diff)
    assert diff.summary.create == 0
    assert diff.summary.update == 0
    assert remaining == 0


def test_disabled_and_depends_on_read_back_through_meta(tmp_path):
    config = write_config(tmp_path, DISABLED_WEB)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncApp, "sync_app.web")
        base = c.find(SyncApp, "sync_app.base")

    assert found.meta.disabled is True
    assert found.meta.depends_on == ["sync_app.base"]
    assert base.meta.disabled is False
    assert base.meta.depends_on == []


def test_disabled_and_depends_on_accepted_by_class_without_meta(tmp_path):
    config = write_config(
        tmp_path,
        """
        plain_app "base" {
          image = "redis"
        }

        plain_app "web" {
          image = "nginx"
          disabled = true
          depends_on = ["plain_app.base"]
        }
        """,
    )

    with xcl.Config(registries=[plain_registry()]) as c:
        c.validate(config)
        c.apply(config)
        found = c.find(PlainApp, "plain_app.web")

    assert isinstance(found, PlainApp)


def test_two_configs_each_find_their_own_class(tmp_path):
    config = write_config(tmp_path, APP_WEB)

    with xcl.Config(registries=[app_registry(SyncApp)]) as first, xcl.Config(registries=[app_registry(PlainApp)]) as second:
        first.apply(config)
        second.apply(config)
        from_first = first.find(None, "app.web")
        from_second = second.find(None, "app.web")

    assert isinstance(from_first, SyncApp)
    assert isinstance(from_second, PlainApp)
    assert from_first.image == "nginx"
    assert from_second.image == "nginx"


# -- sensitive values ------------------------------------------------------


SECRET_APP = """
sync_app "web" {
  image = "nginx"
  password = "s3cret"
}
"""


def test_sensitive_lookup_is_redacted(tmp_path):
    config = write_config(tmp_path, SECRET_APP)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncApp, "sync_app.web")

    assert isinstance(found.password, xcl.Sensitive)
    assert found.password.is_redacted
    assert found.password.reveal() is None
    assert str(found.password) == "(sensitive)"


def test_sensitive_real_in_store_without_mask(tmp_path):
    config = write_config(tmp_path, SECRET_APP)
    store = MemoryStore()

    with xcl.Config(registries=[registry()], state_store=store) as c:
        c.apply(config)

    record = json.loads(store.record("sync_app.web"))
    assert record["password"] == "s3cret"


def test_sensitive_masked_in_store_with_mask(tmp_path):
    config = write_config(tmp_path, SECRET_APP)
    store = MemoryStore()

    with xcl.Config(registries=[registry()], state_store=store, state_mask=xcl.mask.aes256gcm(KEY)) as c:
        c.apply(config)

    record = store.record("sync_app.web")
    assert b"s3cret" not in record
    assert b"nginx" in record


def test_sensitive_redacted_in_event_data(tmp_path):
    config = write_config(tmp_path, SECRET_APP)
    events: list[xcl.Event] = []

    with xcl.Config(registries=[registry()], on_event=events.append, event_data="processed") as c:
        c.apply(config)

    created = [e for e in events if e.resource_id == "sync_app.web" and e.operation == "create" and e.phase == "success"]
    assert len(created) == 1
    assert created[0].data
    assert b"s3cret" not in created[0].data
    assert b"nginx" in created[0].data


# -- computed and nested forms ---------------------------------------------


def test_computed_field_cannot_be_set(tmp_path):
    config = write_config(
        tmp_path,
        """
        sync_app "web" {
          image = "nginx"
          endpoint = "http://set-by-hand"
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        with pytest.raises(xcl.ConfigError) as raised:
            c.apply(config)

    problem = raised.value.problems[0]
    assert "endpoint" in problem.message
    assert "computed" in problem.message
    assert problem.line == 3


def test_nested_block_decoded(tmp_path):
    config = write_config(
        tmp_path,
        """
        sync_app "web" {
          image = "nginx"

          health {
            path = "/healthz"
            interval = 5
          }
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncApp, "sync_app.web")

    assert found.health == Health(path="/healthz", interval=5)


def test_two_volumes_in_order(tmp_path):
    config = write_config(
        tmp_path,
        """
        sync_app "web" {
          image = "nginx"

          volume "data" {
            source = "/srv/data"
            target = "/data"
          }

          volume "logs" {
            source = "/var/log"
            target = "/logs"
          }
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncApp, "sync_app.web")

    assert found.volume == [
        Volume(name="data", source="/srv/data", target="/data"),
        Volume(name="logs", source="/var/log", target="/logs"),
    ]


def test_listeners_dict_by_name(tmp_path):
    config = write_config(
        tmp_path,
        """
        sync_app "web" {
          image = "nginx"

          listener "http" {
            port = 80
          }

          listener "https" {
            port = 443
          }
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncApp, "sync_app.web")

    assert found.listener == {
        "http": Listener(name="http", port=80),
        "https": Listener(name="https", port=443),
    }
    assert found.listener["https"].name == "https"


# -- variables, outputs and diffs ------------------------------------------


def test_variable_supplied(tmp_path):
    config = write_config(
        tmp_path,
        """
        variable "region" {
          default = "eu"
        }

        sync_app "web" {
          image = "nginx"
          region = variable.region
        }
        """,
    )

    with xcl.Config(registries=[registry()], variables={"region": "us"}) as c:
        c.apply(config)
        found = c.find(SyncApp, "sync_app.web")

    assert found.region == "us"


def test_outputs_dict(tmp_path):
    config = write_config(
        tmp_path,
        """
        sync_app "web" {
          image = "nginx"
        }

        output "image" {
          value = sync_app.web.image
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        outputs = c.outputs()

    assert outputs == {"output.image": "nginx"}


def test_diff_reports_old_and_new(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"
    config = recording_config(tmp_path, log, "first")

    with xcl.Config(registries=[plugin_registry(recording_plugin)], state_path=tmp_path / "state") as c:
        c.apply(config)
        recording_config(tmp_path, log, "second")
        diff = c.diff(config)

    assert isinstance(diff, xcl.Diff)
    assert diff.summary.update == 1
    assert diff.summary.create == 0
    changed = diff.resource("resource.recording.one")
    assert changed is not None
    assert changed.action == "update"
    assert len(changed.changes) == 1
    assert changed.changes[0].path == "value"
    assert changed.changes[0].before == "first"
    assert changed.changes[0].after == "second"


def test_diff_before_apply_reports_create(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"
    config = recording_config(tmp_path, log, "first")

    with xcl.Config(registries=[plugin_registry(recording_plugin)], state_path=tmp_path / "state") as c:
        diff = c.diff(config)
        count_after_diff = c.entity_count()

    assert diff.summary.create == 1
    assert diff.summary.update == 0
    assert diff.resources[0].address == "resource.recording.one"
    assert diff.resources[0].action == "create"
    value = next(ch for ch in diff.resources[0].changes if ch.path == "value")
    assert value.before is None
    assert value.after == "first"
    assert not log.exists(), "a diff must not call the provider"
    assert count_after_diff == 0


# -- state ------------------------------------------------------------------


def test_state_directory_load_in_new_process(tmp_path):
    config = write_config(tmp_path, WEB)
    state = tmp_path / "state"

    with xcl.Config(registries=[registry()], state_path=state) as c:
        c.apply(config)

    result = run_script(
        f"""
        import xcl
        from sync_entities import SyncApp, registry
        with xcl.Config(registries=[registry()], state_path={str(state)!r}) as c:
            c.load()
            print("image:" + c.find(SyncApp, "sync_app.web").image)
        """
    )

    assert result.returncode == 0, result.stderr
    assert "image:nginx" in result.stdout


def test_custom_store_round_trip_new_process(tmp_path):
    config = write_config(tmp_path, WEB)
    store_file = tmp_path / "state.jsonl"

    with xcl.Config(registries=[registry()], state_store=JsonLinesStore(store_file)) as c:
        c.apply(config)

    assert store_file.exists()
    result = run_script(
        f"""
        import xcl
        from sync_entities import JsonLinesStore, SyncApp, registry
        with xcl.Config(registries=[registry()], state_store=JsonLinesStore({str(store_file)!r})) as c:
            c.load()
            print("image:" + c.find(SyncApp, "sync_app.web").image)
        """
    )

    assert result.returncode == 0, result.stderr
    assert "image:nginx" in result.stdout


def test_custom_store_encrypted_with_state_mask(tmp_path):
    config = write_config(tmp_path, SECRET_APP)
    store_file = tmp_path / "state.jsonl"
    mask = xcl.mask.aes256gcm(KEY)

    with xcl.Config(registries=[registry()], state_store=JsonLinesStore(store_file), state_mask=mask) as c:
        c.apply(config)

    assert "s3cret" not in store_file.read_text()

    with xcl.Config(registries=[registry()], state_store=JsonLinesStore(store_file), state_mask=mask) as c:
        c.load()
        found = c.find(SyncApp, "sync_app.web")

    assert found.image == "nginx"
    assert found.password.is_redacted


def test_load_then_destroy_empties_state(tmp_path):
    config = write_config(tmp_path, WEB)
    state = tmp_path / "state"

    with xcl.Config(registries=[registry()], state_path=state) as c:
        c.apply(config)

    with xcl.Config(registries=[registry()], state_path=state) as c:
        c.load()
        before = c.entity_count()
        c.destroy()
        after = c.entity_count()

    assert before == 1
    assert after == 0
    with xcl.Config(registries=[registry()], state_path=state) as c:
        c.load()
        assert c.entity_count() == 0


# -- events -----------------------------------------------------------------


def test_events_start_and_finish_per_entity(tmp_path):
    config = write_config(tmp_path, WEB)
    events: list[xcl.Event] = []

    with xcl.Config(registries=[registry()], on_event=events.append) as c:
        c.apply(config)

    assert (events[0].operation, events[0].phase) == ("apply", "start")
    assert (events[-1].operation, events[-1].phase) == ("apply", "success")
    steps = [(e.operation, e.phase) for e in events if e.resource_id == "sync_app.web"]
    assert ("parse", "success") in steps
    assert steps[-1] == ("create", "success")
    assert all(isinstance(e, xcl.Event) for e in events)


def test_event_entity_hydrates(tmp_path):
    config = write_config(tmp_path, WEB)
    events: list[xcl.Event] = []

    with xcl.Config(registries=[registry()], on_event=events.append, event_data="processed") as c:
        c.apply(config)

    created = next(e for e in events if e.resource_id == "sync_app.web" and e.operation == "create")
    entity = created.entity()
    assert isinstance(entity, SyncApp)
    assert entity.image == "nginx"
    assert entity.meta.id == "sync_app.web"
    assert events[0].entity() is None


def test_event_entity_is_emitting_configs_class(tmp_path):
    config = write_config(tmp_path, APP_WEB)
    first_entities: list[object] = []
    second_entities: list[object] = []

    def collect_into(entities: list[object]):
        def on_event(event: xcl.Event) -> None:
            if event.resource_id == "app.web" and event.operation == "create" and event.phase == "success":
                entities.append(event.entity())

        return on_event

    with (
        xcl.Config(registries=[app_registry(SyncApp)], on_event=collect_into(first_entities), event_data="processed") as first,
        xcl.Config(registries=[app_registry(PlainApp)], on_event=collect_into(second_entities), event_data="processed") as second,
    ):
        first.apply(config)
        second.apply(config)

    assert len(first_entities) == 1
    assert len(second_entities) == 1
    assert isinstance(first_entities[0], SyncApp)
    assert isinstance(second_entities[0], PlainApp)


# -- lookup errors ----------------------------------------------------------


def test_missing_address_raises_not_found(tmp_path):
    config = write_config(tmp_path, WEB)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        with pytest.raises(xcl.NotFoundError) as raised:
            c.find(SyncApp, "sync_app.nope")

    assert raised.value.details["address"] == "sync_app.nope"


TWO_APPS = """
sync_app "web" {
  image = "nginx"
}

sync_app "api" {
  image = "httpd"
}
"""


def test_find_one_several_raises_not_unique(tmp_path):
    config = write_config(tmp_path, TWO_APPS)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        with pytest.raises(xcl.NotUniqueError) as raised:
            c.find_one(SyncApp, "sync_app")

    assert raised.value.details["count"] == "2"


def test_find_wrong_class_raises_type_mismatch(tmp_path):
    config = write_config(tmp_path, WEB)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        with pytest.raises(xcl.TypeMismatchError) as raised:
            c.find(SyncDatabase, "sync_app.web")

    assert raised.value.details["address"] == "sync_app.web"
    assert raised.value.details["want"] == "sync_database.postgres"
    assert raised.value.details["got"] == "sync_app"


def test_find_one_across_types_raises_not_typeable(tmp_path):
    config = write_config(tmp_path, WEB)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        with pytest.raises(xcl.NotTypeableError):
            c.find_one(None, "sync_database")


def test_invalid_config_raises_config_error_with_positions(tmp_path):
    config = write_config(
        tmp_path,
        """
        sync_app "web" {
          image = "nginx"
          bogus = 1
          endpoint = "set"
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        with pytest.raises(xcl.ConfigError) as raised:
            c.validate(config)

    problems = raised.value.problems
    assert len(problems) == 2
    assert all(p.file == str(config) for p in problems)
    by_line = {p.line: p.message for p in problems}
    assert "bogus" in by_line[3]
    assert "endpoint" in by_line[4]


# -- collections of entities -----------------------------------------------


def test_find_by_type_and_all(tmp_path):
    config = write_config(
        tmp_path,
        TWO_APPS
        + """
        sync_database "postgres" "main" {
        }
        """,
    )

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        apps_by_type = c.find_by_type(None, "sync_app")
        apps = c.all(SyncApp)
        databases = c.all(SyncDatabase)
        everything = c.entities()

    assert sorted(a.meta.id for a in apps_by_type) == ["sync_app.api", "sync_app.web"]
    assert all(isinstance(a, SyncApp) for a in apps_by_type)
    assert sorted(a.image for a in apps) == ["httpd", "nginx"]
    assert [d.meta.id for d in databases] == ["sync_database.postgres.main"]
    assert isinstance(databases[0], SyncDatabase)
    assert len(everything) == 3


def test_entity_count(tmp_path):
    config = write_config(tmp_path, TWO_APPS)

    with xcl.Config(registries=[registry()]) as c:
        before = c.entity_count()
        c.apply(config)
        after = c.entity_count()

    assert before == 0
    assert after == 2


def test_encode_saved_entity_text_and_highlight(tmp_path):
    config = write_config(tmp_path, WEB)
    store = MemoryStore()

    with xcl.Config(registries=[registry()], state_store=store) as c:
        c.apply(config)
        record = store.record("sync_app.web")
        plain = c.encode_saved_entity(record)
        coloured = c.encode_saved_entity(record, highlight=True)

    assert plain.startswith('sync_app "web" {')
    assert re.search(r'image\s+= "nginx"', plain)
    assert plain.endswith("}\n")
    assert "\x1b[" not in plain
    assert "\x1b[" in coloured


def test_encode_saved_variable_record_is_not_encodable(tmp_path):
    config = write_config(
        tmp_path,
        """
        variable "region" {
          default = "eu"
        }
        """,
    )
    store = MemoryStore()

    with xcl.Config(registries=[registry()], state_store=store) as c:
        c.apply(config)
        record = store.record("variable.region")
        with pytest.raises(xcl.NotEncodableError):
            c.encode_saved_entity(record)


# -- threads and interruption ----------------------------------------------


def count_ticks(during) -> tuple[int, float]:
    """How often a thread sleeping 10ms at a time ticks while ``during()`` runs, and how long it ran for."""
    ticks = 0
    stop = threading.Event()

    def tick() -> None:
        nonlocal ticks
        while not stop.is_set():
            ticks += 1
            time.sleep(0.01)

    worker = threading.Thread(target=tick, daemon=True)
    worker.start()
    started_at = ticks
    began = time.monotonic()
    during()
    elapsed = time.monotonic() - began
    advanced = ticks - started_at
    stop.set()
    worker.join(timeout=5)
    return advanced, elapsed


def test_sync_apply_does_not_stall_threads(tmp_path, slow_plugin):
    config = write_config(
        tmp_path,
        """
        resource "slow" "one" {
          delay_ms = 1500
        }
        """,
    )

    # the baseline is how often the thread ticks on this machine with nothing
    # else running, for as long as the apply takes: a 10ms sleep is far longer
    # on some runners (coarse timers on macOS), so a fixed count would judge
    # the machine rather than the apply
    baseline, _ = count_ticks(lambda: time.sleep(1.5))
    with xcl.Config(registries=[plugin_registry(slow_plugin)], state_path=tmp_path / "state") as c:
        advanced, elapsed = count_ticks(lambda: c.apply(config))
        done = c.find(None, "resource.slow.one").done

    assert elapsed >= 1.4
    assert advanced >= baseline * 0.25, (
        f"the counter thread ran only {advanced} times during a {elapsed:.2f}s apply, "
        f"against {baseline} times in 1.5s with nothing running"
    )
    assert done is True


INTERRUPTED_APPLY = """
import os, signal, time
import xcl
signal.signal(signal.SIGINT, signal.default_int_handler)
# Windows cannot send SIGINT to another process: the test sends Ctrl-Break to
# this process's own group instead, which raises KeyboardInterrupt the same way
if hasattr(signal, "SIGBREAK"):
    signal.signal(signal.SIGBREAK, signal.default_int_handler)
registry = xcl.LocalRegistry()
registry.register_external_plugin({plugin!r})
with xcl.Config(registries=[registry], state_path={state!r}) as c:
    print("applying", flush=True)
    try:
        c.apply({config!r})
        print("completed", flush=True)
    except KeyboardInterrupt:
        print("interrupted", flush=True)
print("state:" + str(os.path.isdir({state!r})), flush=True)
"""


def test_keyboard_interrupt_cancels_apply(tmp_path, slow_plugin):
    config = write_config(
        tmp_path,
        """
        resource "slow" "one" {
          delay_ms = 3000
        }
        """,
    )
    state = tmp_path / "state"
    script = "import sys\n" + f"sys.path[:0] = [{str(ROOT)!r}]\n" + INTERRUPTED_APPLY.format(plugin=str(slow_plugin), state=str(state), config=str(config))
    # Windows delivers an interrupt to another process only as a console
    # event to a whole process group, so the child gets a group of its own,
    # which the engine program it starts joins; the engine discards the event
    # and the child's KeyboardInterrupt drives the cancellation, as SIGINT
    # does on Linux and macOS
    windows = sys.platform == "win32"
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0
    interrupt = signal.CTRL_BREAK_EVENT if windows else signal.SIGINT
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )

    first = process.stdout.readline().strip()
    time.sleep(0.5)
    began = time.monotonic()
    process.send_signal(interrupt)
    try:
        stdout, stderr = process.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        pytest.fail("the interrupted apply did not return within 8s")
    elapsed = time.monotonic() - began

    assert first == "applying"
    assert process.returncode == 0, stderr
    assert "interrupted" in stdout
    assert "completed" not in stdout
    assert "state:True" in stdout
    assert elapsed < 6
