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
from sync_entities import (
    EmptyApp,
    Health,
    JsonLinesStore,
    Listener,
    MemoryStore,
    PlainApp,
    SecretApp,
    SyncApp,
    SyncDatabase,
    Volume,
    encode_registry,
    registry,
)

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

    with xcl.Config(registries=[registry()], on_event=events.append, event_data=xcl.EventDataLevel.PROCESSED) as c:
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

    with xcl.Config(registries=[registry()], on_event=events.append, event_data=xcl.EventDataLevel.PROCESSED) as c:
        c.apply(config)

    created = next(e for e in events if e.resource_id == "sync_app.web" and e.operation == "create")
    entity = created.entity()
    assert isinstance(entity, SyncApp)
    assert entity.image == "nginx"
    assert entity.meta.id == "sync_app.web"
    assert events[0].entity() is None


def test_raw_event_data_carries_the_resource(tmp_path):
    config = write_config(tmp_path, WEB)
    events: list[xcl.Event] = []

    with xcl.Config(registries=[registry()], on_event=events.append, event_data=xcl.EventDataLevel.RAW) as c:
        c.apply(config)

    created = [e for e in events if e.resource_id == "sync_app.web" and e.operation == "create"]
    assert len(created) >= 1
    for event in created:
        assert event.data
        resource = json.loads(event.data)
        assert resource["meta"]["id"] == "sync_app.web"
        assert resource["image"] == "nginx"


def test_event_data_left_out_carries_nothing(tmp_path):
    config = write_config(tmp_path, WEB)
    events: list[xcl.Event] = []

    with xcl.Config(registries=[registry()], on_event=events.append) as c:
        c.apply(config)

    assert events
    assert all(e.data == b"" for e in events)


def test_none_event_data_carries_nothing(tmp_path):
    config = write_config(tmp_path, WEB)
    events: list[xcl.Event] = []

    with xcl.Config(registries=[registry()], on_event=events.append, event_data=xcl.EventDataLevel.NONE) as c:
        c.apply(config)

    assert events
    assert all(e.data == b"" for e in events)


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
        xcl.Config(registries=[app_registry(SyncApp)], on_event=collect_into(first_entities), event_data=xcl.EventDataLevel.PROCESSED) as first,
        xcl.Config(registries=[app_registry(PlainApp)], on_event=collect_into(second_entities), event_data=xcl.EventDataLevel.PROCESSED) as second,
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


# -- encoding entities as configuration -------------------------------------


ENCODE_CONFIG = """
sync_app "web" {
  image = "nginx"
}

sync_database "postgres" "main" {
  version = "15"
}
"""

DATABASE_TEXT = """\
sync_database "postgres" "main" {
  version = "15"
}
"""

SECRETS_CONFIG = """
secret_app "db" {
  image = "postgres"
  password = "s3cret"
}

secret_app "base" {
  image = "redis"
  note = "hunter2"
}

secret_app "bare" {
  image = "nginx"
  password = secret_app.base.note
}

secret_app "tmpl" {
  image = "nginx"
  password = "pre-${secret_app.base.note}"
}
"""

SECRET_DB_MASKED_TEXT = """\
secret_app "db" {
  image    = "postgres"
  password = "(sensitive)"
}
"""

SECRET_DB_REVEALED_TEXT = """\
secret_app "db" {
  image    = "postgres"
  password = "s3cret"
}
"""

REFERENCES_CONFIG = """
sync_database "postgres" "main" {
  version = "15"
}

sync_database "postgres" "replica" {
  version = sync_database.postgres.main.version
}
"""

REPLICA_TEXT = """\
sync_database "postgres" "replica" {
  version = "15"
}
"""

REPLICA_REFERENCES_TEXT = """\
sync_database "postgres" "replica" {
  version = sync_database.postgres.main.version
}
"""

EMPTY_CONFIG = """
empty_app "web" {
  image = "nginx"
}
"""

# an unset string is "", an empty list [], an unset map {}, and the nullable
# region, left out, its zero value
EMPTY_INCLUDED_TEXT = """\
empty_app "web" {
  image  = "nginx"
  note   = ""
  tags   = []
  labels = {}
  region = ""
}
"""

ENCODE_ERRORS_CONFIG = """
variable "region" {
  default = "eu"
}

sync_database "postgres" "main" {
  version = "15"
}

output "version" {
  value = sync_database.postgres.main.version
}

module "leaf" {
  source = "./leaf"
}
"""

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def headings(text: str) -> list[str]:
    """The lines of ``text`` that open a top-level block."""
    return re.findall(r"^\S.*\{$", text, re.MULTILINE)


def strip_colour(text: str) -> str:
    """``text`` with the terminal colour codes removed."""
    return ANSI.sub("", text)


def recording_text(log: Path, *, computed: bool) -> str:
    """The text of ``recording_config(..., "first")``'s entity, with or without the field the provider filled in."""
    if computed:
        return textwrap.dedent(
            f"""\
            resource "recording" "one" {{
              log    = "{log.as_posix()}"
              value  = "first"
              output = "one-first" # set by the provider
            }}
            """
        )
    return textwrap.dedent(
        f"""\
        resource "recording" "one" {{
          log   = "{log.as_posix()}"
          value = "first"
        }}
        """
    )


def test_encode_entity_from_find(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncDatabase, "sync_database.postgres.main")
        text = c.encode_entity(found)

    assert text == DATABASE_TEXT


def test_encode_entity_from_find_by_type(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find_by_type(None, "sync_app")
        texts = [c.encode_entity(entity) for entity in found]

    assert len(texts) == 1
    assert headings(texts[0]) == ['sync_app "web" {']
    assert re.search(r'^  image\s+= "nginx"$', texts[0], re.MULTILINE)
    assert texts[0].endswith("}\n")


def test_encode_entity_from_find_one(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find_one(SyncDatabase, "sync_database", "postgres")
        text = c.encode_entity(found)

    assert text == DATABASE_TEXT


def test_encode_entity_from_all(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.all(SyncApp)
        texts = [c.encode_entity(entity) for entity in found]

    assert len(texts) == 1
    assert headings(texts[0]) == ['sync_app "web" {']
    assert re.search(r'^  image\s+= "nginx"$', texts[0], re.MULTILINE)


def test_encode_entity_from_entities(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        texts = {entity.meta.id: c.encode_entity(entity) for entity in c.entities()}

    assert sorted(texts) == ["sync_app.web", "sync_database.postgres.main"]
    assert headings(texts["sync_app.web"]) == ['sync_app "web" {']
    assert texts["sync_database.postgres.main"] == DATABASE_TEXT


def test_encode_entity_from_kept_event_entity(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)
    kept: list[object] = []

    def on_event(event: xcl.Event) -> None:
        if event.resource_id == "sync_database.postgres.main" and event.operation == "create" and event.phase == "success":
            kept.append(event.entity())

    with xcl.Config(registries=[registry()], on_event=on_event, event_data=xcl.EventDataLevel.PROCESSED) as c:
        c.apply(config)
        texts = [c.encode_entity(entity) for entity in kept]

    assert len(kept) == 1
    assert isinstance(kept[0], SyncDatabase)
    assert texts == [DATABASE_TEXT]


def test_encode_entity_hand_built_matches_loaded(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)
    built = SyncDatabase(version="15", meta=xcl.Meta(name="main"))

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        loaded = c.encode_entity(c.find(SyncDatabase, "sync_database.postgres.main"))
        from_hand = c.encode_entity(built)

    assert from_hand == loaded
    assert from_hand == DATABASE_TEXT


def test_encode_entity_hand_built_with_unset_sensitive_field_matches_loaded(tmp_path):
    config = write_config(
        tmp_path,
        """
        secret_app "web" {
          image = "nginx"
        }
        """,
    )
    built = SecretApp(image="nginx", meta=xcl.Meta(name="web"))

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        loaded = c.encode_entity(c.find(SecretApp, "secret_app.web"))
        from_hand = c.encode_entity(built)

    assert from_hand == 'secret_app "web" {\n  image = "nginx"\n}\n'
    assert loaded == from_hand


def test_encode_entity_untyped_plugin_entity(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"
    config = recording_config(tmp_path, log, "first")

    with xcl.Config(registries=[plugin_registry(recording_plugin)], state_path=tmp_path / "state") as c:
        c.apply(config)
        found = c.find(None, "resource.recording.one")
        text = c.encode_entity(found)

    assert isinstance(found, xcl.Entity)
    assert headings(text) == ['resource "recording" "one" {']
    assert re.search(r'^  value\s+= "first"$', text, re.MULTILINE)


def test_encode_entity_computed_off_by_default(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"
    config = recording_config(tmp_path, log, "first")

    with xcl.Config(registries=[plugin_registry(recording_plugin)], state_path=tmp_path / "state") as c:
        c.apply(config)
        text = c.encode_entity(c.find(None, "resource.recording.one"))

    assert text == recording_text(log, computed=False)


def test_encode_entity_include_computed(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"
    config = recording_config(tmp_path, log, "first")

    with xcl.Config(registries=[plugin_registry(recording_plugin)], state_path=tmp_path / "state") as c:
        c.apply(config)
        text = c.encode_entity(c.find(None, "resource.recording.one"), include_computed=True)

    assert text == recording_text(log, computed=True)


def test_encode_entity_empty_off_by_default(tmp_path):
    config = write_config(tmp_path, EMPTY_CONFIG)

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        text = c.encode_entity(c.find(EmptyApp, "empty_app.web"))

    assert text == 'empty_app "web" {\n  image = "nginx"\n}\n'


def test_encode_entity_include_empty(tmp_path):
    config = write_config(tmp_path, EMPTY_CONFIG)

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        text = c.encode_entity(c.find(EmptyApp, "empty_app.web"), include_empty=True)

    assert text == EMPTY_INCLUDED_TEXT


def test_encode_entity_sensitive_masked_by_default(tmp_path):
    config = write_config(tmp_path, SECRETS_CONFIG)

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        text = c.encode_entity(c.find(SecretApp, "secret_app.db"))

    assert text == SECRET_DB_MASKED_TEXT


def test_encode_entity_reveal_shows_configured_value(tmp_path):
    config = write_config(tmp_path, SECRETS_CONFIG)

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        found = c.find(SecretApp, "secret_app.db")
        text = c.encode_entity(found, reveal_sensitive=True)

    assert found.password.is_redacted
    assert text == SECRET_DB_REVEALED_TEXT


def test_encode_entity_hand_built_reveal_shows_held_value(tmp_path):
    config = write_config(tmp_path, SECRETS_CONFIG)
    built = SecretApp(image="postgres", password=xcl.Sensitive("handmade"), meta=xcl.Meta(name="db"))

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        text = c.encode_entity(built, reveal_sensitive=True)

    assert text == 'secret_app "db" {\n  image    = "postgres"\n  password = "handmade"\n}\n'


def test_encode_entity_references_off_by_default(tmp_path):
    config = write_config(tmp_path, REFERENCES_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        text = c.encode_entity(c.find(SyncDatabase, "sync_database.postgres.replica"))

    assert text == REPLICA_TEXT


def test_encode_entity_show_references(tmp_path):
    config = write_config(tmp_path, REFERENCES_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        text = c.encode_entity(c.find(SyncDatabase, "sync_database.postgres.replica"), show_references=True)

    assert text == REPLICA_REFERENCES_TEXT


def test_encode_entity_hand_built_references_unchanged(tmp_path):
    config = write_config(tmp_path, REFERENCES_CONFIG)
    built = SyncDatabase(version="15", meta=xcl.Meta(name="replica"))

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        without = c.encode_entity(built)
        with_references = c.encode_entity(built, show_references=True)

    assert with_references == without
    assert with_references == REPLICA_TEXT


def test_encode_entity_sensitive_bare_reference_shown(tmp_path):
    config = write_config(tmp_path, SECRETS_CONFIG)

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        text = c.encode_entity(c.find(SecretApp, "secret_app.bare"), show_references=True)

    assert text == 'secret_app "bare" {\n  image    = "nginx"\n  password = secret_app.base.note\n}\n'


def test_encode_entity_sensitive_template_shows_marker_with_references(tmp_path):
    config = write_config(tmp_path, SECRETS_CONFIG)

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        text = c.encode_entity(c.find(SecretApp, "secret_app.tmpl"), show_references=True)

    assert text == 'secret_app "tmpl" {\n  image    = "nginx"\n  password = "(sensitive)"\n}\n'


def test_encode_entity_sensitive_template_shown_with_references_and_reveal(tmp_path):
    config = write_config(tmp_path, SECRETS_CONFIG)

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        text = c.encode_entity(c.find(SecretApp, "secret_app.tmpl"), show_references=True, reveal_sensitive=True)

    assert text == 'secret_app "tmpl" {\n  image    = "nginx"\n  password = "pre-${secret_app.base.note}"\n}\n'


def test_encode_entity_highlight_off_by_default(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        text = c.encode_entity(c.find(SyncDatabase, "sync_database.postgres.main"))

    assert "\x1b[" not in text


def test_encode_entity_highlight_strips_to_plain(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        coloured = c.encode_entity(c.find(SyncDatabase, "sync_database.postgres.main"), highlight=True)

    assert "\x1b[" in coloured
    assert strip_colour(coloured) == DATABASE_TEXT


def test_encode_entity_highlight_matches_saved_record(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)
    store = MemoryStore()

    with xcl.Config(registries=[registry()], state_store=store) as c:
        c.apply(config)
        live = c.encode_entity(c.find(SyncDatabase, "sync_database.postgres.main"), highlight=True)
        saved = c.encode_saved_entity(store.record("sync_database.postgres.main"), highlight=True)

    assert "\x1b[" in live
    assert live == saved


def test_encode_entity_shows_edited_value(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncDatabase, "sync_database.postgres.main")
        found.version = "17"
        text = c.encode_entity(found)

    assert text == 'sync_database "postgres" "main" {\n  version = "17"\n}\n'


def test_encode_entity_reveal_shows_edited_secret(tmp_path):
    config = write_config(tmp_path, SECRETS_CONFIG)

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        found = c.find(SecretApp, "secret_app.db")
        found.password = xcl.Sensitive("edited")
        text = c.encode_entity(found, reveal_sensitive=True)

    assert "s3cret" not in text
    assert text == 'secret_app "db" {\n  image    = "postgres"\n  password = "edited"\n}\n'


def test_encode_saved_entity_with_include_computed_matches_encode_entity(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"
    config = recording_config(tmp_path, log, "first")
    store = MemoryStore()

    with xcl.Config(registries=[plugin_registry(recording_plugin)], state_store=store) as c:
        c.apply(config)
        live = c.encode_entity(c.find(None, "resource.recording.one"), include_computed=True)
        saved = c.encode_saved_entity(store.record("resource.recording.one"), include_computed=True)

    assert saved == live
    assert saved == recording_text(log, computed=True)


def test_encode_saved_entity_with_include_empty_matches_encode_entity(tmp_path):
    config = write_config(tmp_path, EMPTY_CONFIG)
    store = MemoryStore()

    with xcl.Config(registries=[encode_registry()], state_store=store) as c:
        c.apply(config)
        live = c.encode_entity(c.find(EmptyApp, "empty_app.web"), include_empty=True)
        saved = c.encode_saved_entity(store.record("empty_app.web"), include_empty=True)

    assert saved == live
    assert saved == EMPTY_INCLUDED_TEXT


def test_encode_saved_entity_with_reveal_sensitive_matches_encode_entity(tmp_path):
    config = write_config(tmp_path, SECRETS_CONFIG)
    store = MemoryStore()

    with xcl.Config(registries=[encode_registry()], state_store=store) as c:
        c.apply(config)
        live = c.encode_entity(c.find(SecretApp, "secret_app.db"), reveal_sensitive=True)
        saved = c.encode_saved_entity(store.record("secret_app.db"), reveal_sensitive=True)

    assert saved == live
    assert saved == SECRET_DB_REVEALED_TEXT


def test_encode_saved_entity_with_show_references_matches_encode_entity(tmp_path):
    config = write_config(tmp_path, REFERENCES_CONFIG)
    store = MemoryStore()

    with xcl.Config(registries=[registry()], state_store=store) as c:
        c.apply(config)
        live = c.encode_entity(c.find(SyncDatabase, "sync_database.postgres.replica"), show_references=True)
        saved = c.encode_saved_entity(store.record("sync_database.postgres.replica"), show_references=True)

    assert saved == live
    assert saved == REPLICA_REFERENCES_TEXT


def test_encode_saved_entity_without_choices_unchanged(tmp_path):
    config = write_config(tmp_path, SECRETS_CONFIG)
    store = MemoryStore()

    with xcl.Config(registries=[encode_registry()], state_store=store) as c:
        c.apply(config)
        saved = c.encode_saved_entity(store.record("secret_app.db"))

    assert saved == SECRET_DB_MASKED_TEXT


NESTED_DEFAULT_CONFIG = """
sync_app "web" {
  image = "nginx"

  health {
    path = "/h"
  }
}
"""


def test_encode_entity_leaves_out_nested_dataclass_default(tmp_path):
    config = write_config(tmp_path, NESTED_DEFAULT_CONFIG)

    with xcl.Config(registries=[encode_registry()]) as c:
        c.apply(config)
        app = c.find(SyncApp, "sync_app.web")
        text = c.encode_entity(app)

    # hydration filled interval with the dataclass default, which the
    # configuration never set; replicas is the schema's default, which the
    # engine holds too
    assert app.health == Health(path="/h", interval=10)
    assert text == 'sync_app "web" {\n  image    = "nginx"\n  replicas = 2\n\n  health {\n    path = "/h"\n  }\n}\n'


def test_encode_entity_nested_default_matches_saved_record(tmp_path):
    config = write_config(tmp_path, NESTED_DEFAULT_CONFIG)
    store = MemoryStore()

    with xcl.Config(registries=[encode_registry()], state_store=store) as c:
        c.apply(config)
        live = c.encode_entity(c.find(SyncApp, "sync_app.web"))
        saved = c.encode_saved_entity(store.record("sync_app.web"))

    assert live == saved


def write_errors_config(directory: Path) -> Path:
    """``ENCODE_ERRORS_CONFIG`` with the module it uses beside it."""
    leaf = directory / "leaf"
    leaf.mkdir()
    write_config(leaf, WEB, name="leaf.xcl")
    return write_config(directory, ENCODE_ERRORS_CONFIG)


def test_encode_entity_not_an_entity(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        with pytest.raises(xcl.NotEncodableError) as raised:
            c.encode_entity("nginx")

    assert "not an entity" in str(raised.value)


def test_encode_entity_variable_not_encodable(tmp_path):
    config = write_errors_config(tmp_path)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        variable = c.find(None, "variable.region")
        with pytest.raises(xcl.NotEncodableError) as raised:
            c.encode_entity(variable)

    assert "variable" in str(raised.value)


def test_encode_entity_output_not_encodable(tmp_path):
    config = write_errors_config(tmp_path)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        output = c.find(None, "output.version")
        with pytest.raises(xcl.NotEncodableError) as raised:
            c.encode_entity(output)

    assert "output" in str(raised.value)


def test_encode_entity_module_not_encodable(tmp_path):
    config = write_errors_config(tmp_path)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        module = c.find(None, "module.leaf")
        with pytest.raises(xcl.NotEncodableError) as raised:
            c.encode_entity(module)

    assert "module" in str(raised.value)


def test_encode_entity_value_with_no_configuration_form(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        found = c.find(SyncDatabase, "sync_database.postgres.main")
        found.version = object()
        with pytest.raises(xcl.NotEncodableError) as raised:
            c.encode_entity(found)

    assert "no configuration form" in str(raised.value)


def test_encode_entity_unregistered_class(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        with pytest.raises(xcl.NotRegisteredError) as raised:
            c.encode_entity(PlainApp(image="nginx", name="web"))

    assert "PlainApp" in str(raised.value)


def test_encode_entity_unnamed_instance_not_encodable(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    with xcl.Config(registries=[registry()]) as c:
        c.apply(config)
        with pytest.raises(xcl.NotEncodableError) as raised:
            c.encode_entity(SyncDatabase(version="15"))

    assert "no name" in str(raised.value)


def test_encode_entity_during_operation_refused(tmp_path, slow_plugin):
    config = write_config(
        tmp_path,
        """
        resource "slow" "one" {
          delay_ms = 800
        }
        """,
    )
    found = plugin_registry(slow_plugin)
    found.register_type(SyncDatabase, "sync_database", "postgres")
    built = SyncDatabase(version="15", meta=xcl.Meta(name="main"))
    raised: list[BaseException] = []
    texts: list[str] = []
    configs: list[xcl.Config] = []

    def on_event(event: xcl.Event) -> None:
        if event.operation == "apply" and event.phase == "start":
            try:
                texts.append(configs[0].encode_entity(built))
            except xcl.Error as err:
                raised.append(err)

    with xcl.Config(registries=[found], on_event=on_event, state_path=tmp_path / "state") as c:
        configs.append(c)
        c.apply(config)

    assert texts == []
    assert len(raised) == 1
    assert isinstance(raised[0], xcl.OperationInProgressError)


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
