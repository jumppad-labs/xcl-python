"""The asyncio API, ``xcl.aio.Config``, against the real engine.

Every test runs its coroutine with ``asyncio.run`` and applies configuration
written to a temporary directory, with a config-only type registered from
Python and, where a provider is needed, the fixture plugins built from the
xcl checkout.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

import xcl
import xcl.aio

pytestmark = pytest.mark.usefixtures("engine")


@dataclass
class App:
    """A config-only type for the asyncio tests."""

    name: str
    image: str = "nginx"
    meta: xcl.Meta | None = None


@dataclass
class Db:
    """A second config-only type, so a lookup by type can find exactly one entity."""

    version: str = "16"
    meta: xcl.Meta | None = None


@dataclass
class Vault:
    """A config-only type with a sensitive field, for the encoding tests."""

    password: xcl.Sensitive[str] | None = None
    meta: xcl.Meta | None = None


WEB = """
aio_app "web" {
  name = "web"
}
"""

TWO_APPS = """
aio_app "web" {
  name = "web"
}

aio_app "api" {
  name = "api"
  image = "httpd"
}
"""

OPERATIONS_AND_LOOKUPS = [
    "validate",
    "apply",
    "diff",
    "destroy",
    "load",
    "entities",
    "entity_count",
    "find",
    "find_by_type",
    "find_one",
    "all",
    "outputs",
    "encode_entity",
    "encode_saved_entity",
    "close",
]


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    """Plugins are cached under HOME, so every test gets its own."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def write_config(directory: Path, text: str, name: str = "main.xcl") -> Path:
    path = directory / name
    path.write_text(textwrap.dedent(text).lstrip())
    return path


def app_registry(*functions) -> xcl.LocalRegistry:
    found = xcl.LocalRegistry()
    found.register_type(App, "aio_app")
    found.register_type(Db, "aio_db")
    found.register_type(Vault, "aio_vault")
    for fn in functions:
        found.register_function(fn)
    return found


def plugin_registry(plugin: Path) -> xcl.LocalRegistry:
    found = xcl.LocalRegistry()
    found.register_external_plugin(plugin)
    return found


def slow_config(directory: Path, delay_ms: int) -> Path:
    return write_config(
        directory,
        f"""
        resource "slow" "one" {{
          delay_ms = {delay_ms}
        }}
        """,
    )


class AsyncMemoryStore:
    """A state store whose every method is a coroutine function."""

    def __init__(self) -> None:
        self.saved: list[bytes] = []
        self.calls: list[str] = []

    async def load(self) -> list[bytes]:
        self.calls.append("load")
        await asyncio.sleep(0)
        return list(self.saved)

    async def save(self, entities: list[bytes]) -> None:
        self.calls.append("save")
        await asyncio.sleep(0)
        self.saved = list(entities)

    async def exists(self) -> bool:
        self.calls.append("exists")
        return bool(self.saved)

    async def clear(self) -> None:
        self.calls.append("clear")
        self.saved = []


class SyncMemoryStore:
    """A state store with plain methods, for use under the asyncio API."""

    def __init__(self) -> None:
        self.saved: list[bytes] = []
        self.calls: list[str] = []

    def load(self) -> list[bytes]:
        self.calls.append("load")
        return list(self.saved)

    def save(self, entities: list[bytes]) -> None:
        self.calls.append("save")
        self.saved = list(entities)

    def exists(self) -> bool:
        self.calls.append("exists")
        return bool(self.saved)

    def clear(self) -> None:
        self.calls.append("clear")
        self.saved = []


def record_of(store, address: str) -> bytes:
    for raw in store.saved:
        if json.loads(raw).get("meta", {}).get("id") == address:
            return raw
    raise KeyError(address)


def read_log(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def go_time(text: str) -> float:
    """A Go RFC3339Nano timestamp as seconds since the epoch."""
    trimmed = re.sub(r"(\.\d{6})\d+", r"\1", text)
    return datetime.fromisoformat(trimmed).timestamp()


# -- registered functions -------------------------------------------------


def test_async_function_awaited(tmp_path):
    async def slugify(title: str) -> str:
        await asyncio.sleep(0.01)
        return title.lower().replace(" ", "-")

    config = write_config(
        tmp_path,
        """
        aio_app "web" {
          name = slugify("My App")
        }
        """,
    )

    async def main() -> App:
        async with xcl.aio.Config(registries=[app_registry(slugify)]) as c:
            await c.apply(config)
            return await c.find(App, "aio_app.web")

    found = asyncio.run(main())

    assert isinstance(found, App)
    assert found.name == "my-app"


def test_sync_function_in_async_config(tmp_path):
    def shout(title: str) -> str:
        return title.upper()

    config = write_config(
        tmp_path,
        """
        aio_app "web" {
          name = shout("quiet")
        }
        """,
    )

    async def main() -> App:
        async with xcl.aio.Config(registries=[app_registry(shout)]) as c:
            await c.apply(config)
            return await c.find(App, "aio_app.web")

    found = asyncio.run(main())

    assert found.name == "QUIET"


# -- events -----------------------------------------------------------------


def test_async_event_handler(tmp_path):
    config = write_config(tmp_path, WEB)
    events: list[xcl.Event] = []

    async def on_event(event: xcl.Event) -> None:
        await asyncio.sleep(0)
        events.append(event)

    async def main() -> None:
        async with xcl.aio.Config(registries=[app_registry()], on_event=on_event) as c:
            await c.apply(config)

    asyncio.run(main())

    assert events, "the handler received no events"
    assert all(isinstance(e, xcl.Event) for e in events)
    assert (events[0].operation, events[0].phase) == ("apply", "start")
    assert (events[-1].operation, events[-1].phase) == ("apply", "success")
    steps = [(e.operation, e.phase) for e in events if e.resource_id == "aio_app.web"]
    assert steps[-1] == ("create", "success")


def test_async_event_entity_is_configs_class(tmp_path):
    config = write_config(tmp_path, WEB)
    entities: list[object] = []

    async def on_event(event: xcl.Event) -> None:
        if event.resource_id == "aio_app.web" and event.operation == "create" and event.phase == "success":
            entities.append(event.entity())

    async def main() -> None:
        async with xcl.aio.Config(registries=[app_registry()], on_event=on_event, event_data=xcl.EventDataLevel.PROCESSED) as c:
            await c.apply(config)

    asyncio.run(main())

    assert len(entities) == 1
    assert isinstance(entities[0], App)
    assert entities[0].name == "web"
    assert entities[0].meta.id == "aio_app.web"


# -- state stores -----------------------------------------------------------


def test_async_state_store_round_trip(tmp_path):
    config = write_config(tmp_path, WEB)
    store = AsyncMemoryStore()

    async def main() -> tuple[int, App]:
        async with xcl.aio.Config(registries=[app_registry()], state_store=store) as c:
            await c.apply(config)

        async with xcl.aio.Config(registries=[app_registry()], state_store=store) as again:
            await again.load()
            return await again.entity_count(), await again.find(App, "aio_app.web")

    count, found = asyncio.run(main())

    assert "save" in store.calls
    assert json.loads(record_of(store, "aio_app.web"))["name"] == "web"
    assert "load" in store.calls
    assert count == 1
    assert isinstance(found, App)
    assert found.name == "web"


def test_sync_state_store_in_async_config(tmp_path):
    config = write_config(tmp_path, WEB)
    store = SyncMemoryStore()

    async def main() -> App:
        async with xcl.aio.Config(registries=[app_registry()], state_store=store) as c:
            await c.apply(config)

        async with xcl.aio.Config(registries=[app_registry()], state_store=store) as again:
            await again.load()
            return await again.find(App, "aio_app.web")

    found = asyncio.run(main())

    assert "save" in store.calls
    assert "load" in store.calls
    assert json.loads(record_of(store, "aio_app.web"))["name"] == "web"
    assert found.name == "web"


# -- the event loop keeps running -----------------------------------------


def test_other_coroutines_run_during_apply(tmp_path, slow_plugin):
    config = slow_config(tmp_path, 1500)

    async def main() -> tuple[float, int, bool]:
        ticks = 0
        stop = asyncio.Event()

        async def tick() -> None:
            nonlocal ticks
            while not stop.is_set():
                ticks += 1
                await asyncio.sleep(0.01)

        async with xcl.aio.Config(registries=[plugin_registry(slow_plugin)], state_path=tmp_path / "state") as c:
            ticker = asyncio.create_task(tick())
            started_at = ticks
            began = time.monotonic()
            await c.apply(config)
            elapsed = time.monotonic() - began
            advanced = ticks - started_at
            stop.set()
            await ticker
            done = (await c.find(None, "resource.slow.one")).done
        return elapsed, advanced, done

    elapsed, advanced, done = asyncio.run(main())

    assert elapsed >= 1.4
    assert advanced >= 50, f"the ticker ran only {advanced} times during a {elapsed:.2f}s apply"
    assert done is True


def test_http_server_answers_during_long_apply(tmp_path, slow_plugin):
    config = slow_config(tmp_path, 2000)

    async def echo_line(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await reader.readline()
        writer.write(line)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def request(port: int, text: bytes) -> tuple[bytes, float]:
        began = time.monotonic()
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(text)
        await writer.drain()
        answer = await reader.readline()
        writer.close()
        await writer.wait_closed()
        return answer, time.monotonic() - began

    async def main() -> tuple[list[tuple[bytes, float]], bool]:
        server = await asyncio.start_server(echo_line, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            async with xcl.aio.Config(registries=[plugin_registry(slow_plugin)], state_path=tmp_path / "state") as c:
                applying = asyncio.create_task(c.apply(config))
                await asyncio.sleep(0.2)
                answers = []
                for n in range(20):
                    answers.append(await request(port, f"ping {n}\n".encode()))
                still_applying = not applying.done()
                await applying
        finally:
            server.close()
            await server.wait_closed()
        return answers, still_applying

    answers, still_applying = asyncio.run(main())

    assert still_applying, "the apply finished before the requests were made"
    assert len(answers) == 20
    assert [a for a, _ in answers] == [f"ping {n}\n".encode() for n in range(20)]
    slowest = max(took for _, took in answers)
    assert slowest < 0.1, f"a request took {slowest * 1000:.0f}ms while the apply ran"


# -- cancellation -----------------------------------------------------------


def test_cancel_apply_ends_promptly(tmp_path, slow_plugin):
    config = slow_config(tmp_path, 3000)

    async def main() -> tuple[float, bool, int]:
        async with xcl.aio.Config(registries=[plugin_registry(slow_plugin)], state_path=tmp_path / "state") as c:
            task = asyncio.create_task(c.apply(config))
            await asyncio.sleep(0.5)
            task.cancel()
            began = time.monotonic()
            cancelled = False
            try:
                await asyncio.wait_for(task, 5)
            except asyncio.CancelledError:
                cancelled = True
            elapsed = time.monotonic() - began
            entities = await c.entities()
        return elapsed, cancelled, entities

    elapsed, cancelled, entities = asyncio.run(main())

    assert cancelled, "awaiting the cancelled apply did not raise CancelledError"
    assert elapsed < 4, f"the cancelled apply took {elapsed:.2f}s to end"
    assert isinstance(entities, list)


def test_cancel_apply_starts_no_operation_after_cancel(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"
    config = write_config(
        tmp_path,
        f"""
        resource "recording" "first" {{
          log = "{log.as_posix()}"
          delay_ms = 1500
          value = "a"
        }}

        resource "recording" "second" {{
          log = "{log.as_posix()}"
          value = "b"
          input = resource.recording.first.output
        }}
        """,
    )

    async def main() -> tuple[float, bool]:
        async with xcl.aio.Config(registries=[plugin_registry(recording_plugin)], state_path=tmp_path / "state") as c:
            task = asyncio.create_task(c.apply(config))
            await asyncio.sleep(0.3)
            task.cancel()
            cancelled_at = time.time()
            cancelled = False
            try:
                await task
            except asyncio.CancelledError:
                cancelled = True
            # give a call that wrongly started after the cancel time to be logged
            await asyncio.sleep(0.2)
        return cancelled_at, cancelled

    cancelled_at, cancelled = asyncio.run(main())

    assert cancelled
    creates = [line for line in read_log(log) if line["step"] == "create"]
    assert [line["address"] for line in creates] == ["resource.recording.first"]
    for line in creates:
        assert go_time(line["time"]) < cancelled_at + 0.05, f"{line} started after the cancel at {cancelled_at}"


# -- encoding entities as configuration -------------------------------------


ENCODE_CONFIG = """
aio_app "web" {
  name = "web"
}

aio_db "main" {
  version = "15"
}

aio_vault "db" {
  password = "s3cret"
}
"""

ENCODE_ERRORS_CONFIG = """
variable "region" {
  default = "eu"
}

aio_db "main" {
  version = "15"
}

output "version" {
  value = aio_db.main.version
}

module "leaf" {
  source = "./leaf"
}
"""

WEB_TEXT = """\
aio_app "web" {
  name  = "web"
  image = "nginx"
}
"""

DB_TEXT = """\
aio_db "main" {
  version = "15"
}
"""

VAULT_REVEALED_TEXT = """\
aio_vault "db" {
  password = "s3cret"
}
"""


def write_errors_config(directory: Path) -> Path:
    """``ENCODE_ERRORS_CONFIG`` with the module it uses beside it."""
    leaf = directory / "leaf"
    leaf.mkdir()
    write_config(leaf, WEB, name="leaf.xcl")
    return write_config(directory, ENCODE_ERRORS_CONFIG)


def test_async_encode_entity_from_find(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> str:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            return await c.encode_entity(await c.find(App, "aio_app.web"))

    text = asyncio.run(main())

    assert text == WEB_TEXT


def test_async_encode_entity_from_find_by_type(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> list[str]:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            return [await c.encode_entity(entity) for entity in await c.find_by_type(None, "aio_app")]

    texts = asyncio.run(main())

    assert texts == [WEB_TEXT]


def test_async_encode_entity_from_find_one(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> str:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            return await c.encode_entity(await c.find_one(Db, "aio_db"))

    text = asyncio.run(main())

    assert text == DB_TEXT


def test_async_encode_entity_from_all(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> list[str]:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            return [await c.encode_entity(entity) for entity in await c.all(Db)]

    texts = asyncio.run(main())

    assert texts == [DB_TEXT]


def test_async_encode_entity_from_entities(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> dict[str, str]:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            return {entity.meta.id: await c.encode_entity(entity) for entity in await c.entities()}

    texts = asyncio.run(main())

    assert sorted(texts) == ["aio_app.web", "aio_db.main", "aio_vault.db"]
    assert texts["aio_app.web"] == WEB_TEXT
    assert texts["aio_db.main"] == DB_TEXT
    assert texts["aio_vault.db"].startswith('aio_vault "db" {\n')


def test_async_encode_entity_from_kept_event_entity(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)
    kept: list[object] = []

    async def on_event(event: xcl.Event) -> None:
        if event.resource_id == "aio_db.main" and event.operation == "create" and event.phase == "success":
            kept.append(event.entity())

    async def main() -> list[str]:
        async with xcl.aio.Config(registries=[app_registry()], on_event=on_event, event_data=xcl.EventDataLevel.PROCESSED) as c:
            await c.apply(config)
            return [await c.encode_entity(entity) for entity in kept]

    texts = asyncio.run(main())

    assert len(kept) == 1
    assert isinstance(kept[0], Db)
    assert texts == [DB_TEXT]


def test_async_encode_entity_hand_built_matches_loaded(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)
    built = Db(version="15", meta=xcl.Meta(name="main"))

    async def main() -> tuple[str, str]:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            return await c.encode_entity(await c.find(Db, "aio_db.main")), await c.encode_entity(built)

    loaded, from_hand = asyncio.run(main())

    assert from_hand == loaded
    assert from_hand == DB_TEXT


def test_async_encode_entity_sensitive_masked_by_default(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> str:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            return await c.encode_entity(await c.find(Vault, "aio_vault.db"))

    text = asyncio.run(main())

    assert text == 'aio_vault "db" {\n  password = "(sensitive)"\n}\n'


def test_async_encode_entity_reveal_shows_configured_value(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> str:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            return await c.encode_entity(await c.find(Vault, "aio_vault.db"), reveal_sensitive=True)

    text = asyncio.run(main())

    assert text == VAULT_REVEALED_TEXT


def test_async_encode_entity_reveal_shows_edited_secret(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> str:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            found = await c.find(Vault, "aio_vault.db")
            found.password = xcl.Sensitive("edited")
            return await c.encode_entity(found, reveal_sensitive=True)

    text = asyncio.run(main())

    assert text == 'aio_vault "db" {\n  password = "edited"\n}\n'


def test_async_encode_saved_entity_with_reveal_sensitive_matches_encode_entity(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)
    store = AsyncMemoryStore()

    async def main() -> tuple[str, str]:
        async with xcl.aio.Config(registries=[app_registry()], state_store=store) as c:
            await c.apply(config)
            live = await c.encode_entity(await c.find(Vault, "aio_vault.db"), reveal_sensitive=True)
            saved = await c.encode_saved_entity(record_of(store, "aio_vault.db"), reveal_sensitive=True)
            return live, saved

    live, saved = asyncio.run(main())

    assert saved == live
    assert saved == VAULT_REVEALED_TEXT


def test_async_encode_entity_highlight_strips_to_plain(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> str:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            return await c.encode_entity(await c.find(Db, "aio_db.main"), highlight=True)

    coloured = asyncio.run(main())

    assert "\x1b[" in coloured
    assert re.sub(r"\x1b\[[0-9;]*m", "", coloured) == DB_TEXT


def test_async_encode_entity_highlight_matches_saved_record(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)
    store = AsyncMemoryStore()

    async def main() -> tuple[str, str]:
        async with xcl.aio.Config(registries=[app_registry()], state_store=store) as c:
            await c.apply(config)
            live = await c.encode_entity(await c.find(Db, "aio_db.main"), highlight=True)
            saved = await c.encode_saved_entity(record_of(store, "aio_db.main"), highlight=True)
            return live, saved

    live, saved = asyncio.run(main())

    assert "\x1b[" in live
    assert live == saved


def test_async_encode_entity_not_an_entity(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> None:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            await c.encode_entity("nginx")

    with pytest.raises(xcl.NotEncodableError) as raised:
        asyncio.run(main())

    assert "not an entity" in str(raised.value)


def test_async_encode_entity_variable_not_encodable(tmp_path):
    config = write_errors_config(tmp_path)

    async def main() -> None:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            await c.encode_entity(await c.find(None, "variable.region"))

    with pytest.raises(xcl.NotEncodableError) as raised:
        asyncio.run(main())

    assert "variable" in str(raised.value)


def test_async_encode_entity_output_not_encodable(tmp_path):
    config = write_errors_config(tmp_path)

    async def main() -> None:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            await c.encode_entity(await c.find(None, "output.version"))

    with pytest.raises(xcl.NotEncodableError) as raised:
        asyncio.run(main())

    assert "output" in str(raised.value)


def test_async_encode_entity_module_not_encodable(tmp_path):
    config = write_errors_config(tmp_path)

    async def main() -> None:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            await c.encode_entity(await c.find(None, "module.leaf"))

    with pytest.raises(xcl.NotEncodableError) as raised:
        asyncio.run(main())

    assert "module" in str(raised.value)


def test_async_encode_entity_value_with_no_configuration_form(tmp_path):
    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> None:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            found = await c.find(Db, "aio_db.main")
            found.version = object()
            await c.encode_entity(found)

    with pytest.raises(xcl.NotEncodableError) as raised:
        asyncio.run(main())

    assert "no configuration form" in str(raised.value)


def test_async_encode_entity_unregistered_class(tmp_path):
    @dataclass
    class Unregistered:
        name: str = xcl.field(label=True, default="web")

    config = write_config(tmp_path, ENCODE_CONFIG)

    async def main() -> None:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            await c.apply(config)
            await c.encode_entity(Unregistered())

    with pytest.raises(xcl.NotRegisteredError) as raised:
        asyncio.run(main())

    assert "Unregistered" in str(raised.value)


def test_async_encode_entity_during_operation_refused(tmp_path, slow_plugin):
    config = slow_config(tmp_path, 800)
    found = plugin_registry(slow_plugin)
    found.register_type(Db, "aio_db")
    built = Db(version="15", meta=xcl.Meta(name="main"))
    raised: list[BaseException] = []
    texts: list[str] = []
    configs: list[xcl.aio.Config] = []

    async def on_event(event: xcl.Event) -> None:
        if event.operation == "apply" and event.phase == "start":
            try:
                texts.append(await configs[0].encode_entity(built))
            except xcl.Error as err:
                raised.append(err)

    async def main() -> None:
        async with xcl.aio.Config(registries=[found], on_event=on_event, state_path=tmp_path / "state") as c:
            configs.append(c)
            await c.apply(config)

    asyncio.run(main())

    assert texts == []
    assert len(raised) == 1
    assert isinstance(raised[0], xcl.OperationInProgressError)


# -- rendering from an event handler during an apply -----------------------


class GatedStore(AsyncMemoryStore):
    """An async state store whose save of the created resource waits until the handler has finished with it.

    The asyncio client handles events and state tasks concurrently, so the
    gate makes the engine still be waiting on the apply's save while the
    handler renders, rather than leaving that to timing.
    """

    def __init__(self) -> None:
        super().__init__()
        self.handled = asyncio.Event()

    async def save(self, entities: list[bytes]) -> None:
        if any(json.loads(raw).get("done") for raw in entities):
            await asyncio.wait_for(self.handled.wait(), timeout=10)
        await super().save(entities)


def test_async_encode_saved_entity_from_handler_during_apply(tmp_path, slow_plugin):
    config = slow_config(tmp_path, 0)
    store = GatedStore()
    raised: list[BaseException] = []
    texts: list[str] = []
    records: list[bytes] = []
    after: list[str] = []
    configs: list[xcl.aio.Config] = []

    async def on_event(event: xcl.Event) -> None:
        if event.operation != "create" or event.phase != "success":
            return
        try:
            texts.append(await configs[0].encode_saved_entity(event.data, include_computed=True))
            records.append(event.data)
        except BaseException as err:
            raised.append(err)
        finally:
            store.handled.set()

    async def main() -> None:
        async with xcl.aio.Config(
            registries=[plugin_registry(slow_plugin)],
            on_event=on_event,
            event_data=xcl.EventDataLevel.PROCESSED,
            state_store=store,
        ) as c:
            configs.append(c)
            await c.apply(config)
            after.append(await c.encode_saved_entity(records[0], include_computed=True))

    asyncio.run(main())

    assert raised == []
    assert len(texts) == 1
    assert 'resource "slow" "one"' in texts[0]
    assert "done = true" in texts[0]
    assert texts == after
    assert "save" in store.calls


def test_async_encode_entity_from_handler_during_apply_refused(tmp_path, slow_plugin):
    config = slow_config(tmp_path, 0)
    store = GatedStore()
    raised: list[BaseException] = []
    texts: list[str] = []
    configs: list[xcl.aio.Config] = []

    async def on_event(event: xcl.Event) -> None:
        if event.operation != "create" or event.phase != "success":
            return
        try:
            texts.append(await configs[0].encode_entity(event.entity()))
        except xcl.Error as err:
            raised.append(err)
        finally:
            store.handled.set()

    async def main() -> None:
        async with xcl.aio.Config(
            registries=[plugin_registry(slow_plugin)],
            on_event=on_event,
            event_data=xcl.EventDataLevel.PROCESSED,
            state_store=store,
        ) as c:
            configs.append(c)
            await c.apply(config)

    asyncio.run(main())

    assert texts == []
    assert len(raised) == 1
    assert isinstance(raised[0], xcl.OperationInProgressError)
    assert "save" in store.calls


def test_async_encode_edited_entity_from_handler_during_apply_refused(tmp_path, slow_plugin):
    config = slow_config(tmp_path, 0)
    store = GatedStore()
    raised: list[BaseException] = []
    texts: list[str] = []
    configs: list[xcl.aio.Config] = []

    async def on_event(event: xcl.Event) -> None:
        if event.operation != "create" or event.phase != "success":
            return
        edited = xcl.Entity({**event.entity().to_dict(), "delay_ms": 5})
        try:
            texts.append(await configs[0].encode_entity(edited))
        except xcl.Error as err:
            raised.append(err)
        finally:
            store.handled.set()

    async def main() -> None:
        async with xcl.aio.Config(
            registries=[plugin_registry(slow_plugin)],
            on_event=on_event,
            event_data=xcl.EventDataLevel.PROCESSED,
            state_store=store,
        ) as c:
            configs.append(c)
            await c.apply(config)

    asyncio.run(main())

    assert texts == []
    assert len(raised) == 1
    assert isinstance(raised[0], xcl.OperationInProgressError)


# -- lookups and operations are awaitables -------------------------------


def test_lookups_are_awaitable(tmp_path):
    config = write_config(
        tmp_path,
        TWO_APPS
        + """
        aio_db "main" {
          version = "15"
        }

        output "image" {
          value = aio_app.web.image
        }
        """,
    )
    store = AsyncMemoryStore()

    async def main() -> dict:
        async with xcl.aio.Config(registries=[app_registry()], state_store=store) as c:
            await c.apply(config)
            return {
                "entities": await c.entities(),
                "entity_count": await c.entity_count(),
                "find": await c.find(App, "aio_app.web"),
                "find_by_type": await c.find_by_type(None, "aio_app"),
                "find_one": await c.find_one(Db, "aio_db"),
                "all": await c.all(App),
                "outputs": await c.outputs(),
                "encode_saved_entity": await c.encode_saved_entity(record_of(store, "aio_app.web")),
            }

    got = asyncio.run(main())

    assert sorted(e.meta.id for e in got["entities"]) == ["aio_app.api", "aio_app.web", "aio_db.main", "output.image"]
    assert got["entity_count"] == 4
    assert isinstance(got["find"], App)
    assert got["find"].name == "web"
    assert sorted(a.meta.id for a in got["find_by_type"]) == ["aio_app.api", "aio_app.web"]
    assert isinstance(got["find_one"], Db)
    assert got["find_one"].version == "15"
    assert sorted(a.image for a in got["all"]) == ["httpd", "nginx"]
    assert got["outputs"] == {"output.image": "nginx"}
    assert got["encode_saved_entity"].startswith('aio_app "web" {')


def test_diff_and_destroy_awaitable(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"

    def recording_config(value: str) -> Path:
        return write_config(
            tmp_path,
            f"""
            resource "recording" "one" {{
              log = "{log.as_posix()}"
              value = "{value}"
            }}
            """,
        )

    async def main() -> tuple[xcl.Diff, xcl.Diff, int, int]:
        config = recording_config("first")
        async with xcl.aio.Config(registries=[plugin_registry(recording_plugin)], state_path=tmp_path / "state") as c:
            creating = await c.diff(config)
            await c.apply(config)
            recording_config("second")
            updating = await c.diff(config)
            before = await c.entity_count()
            await c.destroy()
            after = await c.entity_count()
        return creating, updating, before, after

    creating, updating, before, after = asyncio.run(main())

    assert isinstance(creating, xcl.Diff)
    assert creating.summary.create == 1
    assert creating.resources[0].address == "resource.recording.one"
    assert creating.resources[0].action == "create"
    assert isinstance(updating, xcl.Diff)
    assert updating.summary.update == 1
    changed = updating.resource("resource.recording.one")
    assert changed is not None
    assert changed.changes[0].path == "value"
    assert changed.changes[0].before == "first"
    assert changed.changes[0].after == "second"
    assert before == 1
    assert after == 0
    steps = [line["step"] for line in read_log(log)]
    assert "destroy" in steps


def test_async_context_manager_closes(tmp_path):
    async def main() -> tuple[int, int]:
        async with xcl.aio.Config(registries=[app_registry()]) as c:
            inside = c.handle
        return inside, c.handle

    inside, after = asyncio.run(main())

    assert inside != 0
    assert after == 0


def test_sync_and_async_expose_same_surface():
    sync_names = {name for name in dir(xcl.Config) if not name.startswith("_")}
    aio_names = {name for name in dir(xcl.aio.Config) if not name.startswith("_")}

    assert sync_names <= aio_names
    assert aio_names - sync_names == {"open"}
    for name in OPERATIONS_AND_LOOKUPS:
        assert inspect.iscoroutinefunction(getattr(xcl.aio.Config, name)), f"aio.Config.{name} is not a coroutine function"
        assert not inspect.iscoroutinefunction(getattr(xcl.Config, name)), f"Config.{name} is a coroutine function"
