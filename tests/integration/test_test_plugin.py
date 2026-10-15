"""Go plugins are usable from Python: the test plugin, end to end.

The plugin is installed once per session from its signed GitHub release
(``installed_release``) and then started three ways: through the GitHub
registry again, from its binary's path, and from the directory the binary is
in. Each test applies ``configs/test_plugin/main.xcl``, two items where
``second`` takes ``first``'s output as its input, with the operation log the
items record to in the test's temporary directory, reads the entities back as
generic :class:`xcl.Entity` values, and always destroys what it created.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import xcl
from release_helpers import (
    FIRST_ADDRESS,
    SECOND_ADDRESS,
    TEST_PLUGIN_CONFIG,
    ReleaseFiles,
    github_registry,
    installed_release,
    isolated_home,
    log_variables,
    trusted_key,
)
from sync_entities import MemoryStore

__all__ = ["installed_release", "isolated_home"]

pytestmark = pytest.mark.usefixtures("engine")

# the AES-256-GCM key the masked-state test seals sensitive values with
KEY = bytes(range(32))

SECRET = "hunter2"


def path_registry(installed: ReleaseFiles) -> xcl.LocalRegistry:
    """A registry starting the installed plugin from its binary's path."""
    registry = xcl.LocalRegistry()
    registry.register_external_plugin(installed.binary)
    return registry


def read_operations(log: Path) -> list[tuple[str, str]]:
    """The operations the items recorded to ``log``, as (operation, address), in order."""
    records = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    return [(record["operation"], record["address"]) for record in records]


def assert_items(first: object, second: object) -> None:
    assert isinstance(first, xcl.Entity)
    assert first.meta.id == FIRST_ADDRESS
    assert first.value == "one"
    assert first.output == "first-one"

    assert isinstance(second, xcl.Entity)
    assert second.meta.id == SECOND_ADDRESS
    assert second.input == "first-one"
    assert second.output == "second-two"


def test_test_plugin_from_github_registry(tmp_path: Path, installed_release: ReleaseFiles):
    registry = github_registry(installed_release.cache_dir, trusted_keys=[trusted_key()])
    variables = log_variables(tmp_path / "ops.jsonl")

    with xcl.Config(registries=[registry], state_path=tmp_path / "state", variables=variables) as c:
        try:
            c.apply(TEST_PLUGIN_CONFIG)
            applied = c.find_by_type(None, "test", "item")
            first = c.find(None, FIRST_ADDRESS)
            second = c.find(None, SECOND_ADDRESS)
        finally:
            c.destroy()
            remaining = c.find_by_type(None, "test", "item")

    assert sorted(e.meta.id for e in applied) == [FIRST_ADDRESS, SECOND_ADDRESS]
    assert_items(first, second)
    assert remaining == []


def test_test_plugin_from_path(tmp_path: Path, installed_release: ReleaseFiles):
    variables = log_variables(tmp_path / "ops.jsonl")

    with xcl.Config(registries=[path_registry(installed_release)], state_path=tmp_path / "state", variables=variables) as c:
        try:
            c.apply(TEST_PLUGIN_CONFIG)
            first = c.find(None, FIRST_ADDRESS)
            second = c.find(None, SECOND_ADDRESS)
        finally:
            c.destroy()
            remaining = c.find_by_type(None, "test", "item")

    assert_items(first, second)
    assert remaining == []


def test_test_plugin_from_directory(tmp_path: Path, installed_release: ReleaseFiles):
    # the cache entry holds the binary beside the release's archive,
    # checksums file and signature, which are named xcl-plugin-test_... but
    # are not executable, so the default xcl-plugin-* pattern starts only
    # the binary
    sidecars = sorted(p.name for p in installed_release.entry.iterdir() if p != installed_release.binary)
    assert sidecars == sorted(
        [installed_release.archive_name, installed_release.checksums_name, installed_release.signature_name]
    )

    registry = xcl.LocalRegistry()
    registry.register_plugin_directory(installed_release.entry)
    variables = log_variables(tmp_path / "ops.jsonl")

    with xcl.Config(registries=[registry], state_path=tmp_path / "state", variables=variables) as c:
        try:
            c.apply(TEST_PLUGIN_CONFIG)
            first = c.find(None, FIRST_ADDRESS)
            second = c.find(None, SECOND_ADDRESS)
        finally:
            c.destroy()
            remaining = c.find_by_type(None, "test", "item")

    assert_items(first, second)
    assert remaining == []


def test_plugin_entities_readable_generically(tmp_path: Path, installed_release: ReleaseFiles):
    variables = log_variables(tmp_path / "ops.jsonl")

    with xcl.Config(registries=[path_registry(installed_release)], state_path=tmp_path / "state", variables=variables) as c:
        try:
            c.apply(TEST_PLUGIN_CONFIG)
            first = c.find(None, FIRST_ADDRESS)
            second = c.find(None, SECOND_ADDRESS)
            everything = c.find_by_type(None, "test", "item")
        finally:
            c.destroy()

    assert isinstance(first, xcl.Entity)
    assert first.meta.id == FIRST_ADDRESS
    assert first.value == "one"
    assert first["value"] == first.value
    assert "value" in first
    assert set(first) >= {"meta", "log", "value", "output"}
    assert first.to_dict()["value"] == "one"

    assert isinstance(first.meta, xcl.Meta)
    assert first.meta.id == FIRST_ADDRESS
    assert first.meta.name == "first"
    assert first.meta.type == "test"
    assert first.meta.subtype == "item"
    assert first.meta.file == TEST_PLUGIN_CONFIG
    assert first.meta.line == 9
    assert first.meta.status == "created"

    assert second.meta.type == "test"
    assert second.meta.subtype == "item"
    assert second.meta.line == 15
    assert second.meta.references == {"log": "variable.log", "input": f"{FIRST_ADDRESS}.output"}
    assert f"{FIRST_ADDRESS}.output" in second.meta.links

    assert all(isinstance(e, xcl.Entity) for e in everything)
    assert sorted(e.meta.id for e in everything) == [FIRST_ADDRESS, SECOND_ADDRESS]


def test_plugin_entity_refuses_unknown_names(tmp_path: Path, installed_release: ReleaseFiles):
    variables = log_variables(tmp_path / "ops.jsonl")

    with xcl.Config(registries=[path_registry(installed_release)], state_path=tmp_path / "state", variables=variables) as c:
        try:
            c.apply(TEST_PLUGIN_CONFIG)
            first = c.find(None, FIRST_ADDRESS)
        finally:
            c.destroy()

    with pytest.raises(AttributeError):
        first.no_such_attribute
    with pytest.raises(KeyError):
        first["no_such_attribute"]


def test_recorded_operations_follow_dependencies(tmp_path: Path, installed_release: ReleaseFiles):
    log = tmp_path / "ops.jsonl"

    with xcl.Config(registries=[path_registry(installed_release)], state_path=tmp_path / "state", variables=log_variables(log)) as c:
        try:
            c.apply(TEST_PLUGIN_CONFIG)
        finally:
            c.destroy()

    operations = read_operations(log)

    # first and second are linked through input, so their order is fixed by
    # the graph: second is created after first and destroyed before it
    creates = [address for operation, address in operations if operation == "create"]
    destroys = [address for operation, address in operations if operation == "destroy"]
    assert creates == [FIRST_ADDRESS, SECOND_ADDRESS]
    assert destroys == [SECOND_ADDRESS, FIRST_ADDRESS]
    assert operations.index(("create", SECOND_ADDRESS)) < operations.index(("destroy", SECOND_ADDRESS))


def test_computed_output_filled_in(tmp_path: Path, installed_release: ReleaseFiles):
    variables = log_variables(tmp_path / "ops.jsonl")

    with xcl.Config(registries=[path_registry(installed_release)], state_path=tmp_path / "state", variables=variables) as c:
        try:
            c.apply(TEST_PLUGIN_CONFIG)
            first = c.find(None, FIRST_ADDRESS)
            second = c.find(None, SECOND_ADDRESS)
        finally:
            c.destroy()

    assert first.output == "first-one"
    assert second.output == "second-two"
    assert second.input == first.output


def test_sensitive_secret_redacted_in_lookup(tmp_path: Path, installed_release: ReleaseFiles):
    variables = log_variables(tmp_path / "ops.jsonl")

    with xcl.Config(registries=[path_registry(installed_release)], state_path=tmp_path / "state", variables=variables) as c:
        try:
            c.apply(TEST_PLUGIN_CONFIG)
            first = c.find(None, FIRST_ADDRESS)
        finally:
            c.destroy()

    # a generic entity has no type to rebuild a Sensitive from, so the
    # redacted value reads back as the marker
    assert first.secret == "(sensitive)"
    assert SECRET not in json.dumps(first.to_dict(), default=str)


def test_sensitive_secret_redacted_in_events(tmp_path: Path, installed_release: ReleaseFiles):
    events: list[xcl.Event] = []
    variables = log_variables(tmp_path / "ops.jsonl")

    with xcl.Config(
        registries=[path_registry(installed_release)],
        state_path=tmp_path / "state",
        variables=variables,
        on_event=events.append,
        event_data="processed",
    ) as c:
        try:
            c.apply(TEST_PLUGIN_CONFIG)
        finally:
            c.destroy()

    created = [e for e in events if e.resource_id == FIRST_ADDRESS and e.operation == "create" and e.phase == "success"]
    assert len(created) == 1
    assert created[0].data
    assert SECRET.encode() not in created[0].data
    assert b"first-one" in created[0].data
    assert all(SECRET.encode() not in (e.data or b"") for e in events)


def test_sensitive_secret_masked_in_state(tmp_path: Path, installed_release: ReleaseFiles):
    store = MemoryStore()
    variables = log_variables(tmp_path / "ops.jsonl")

    with xcl.Config(
        registries=[path_registry(installed_release)],
        state_store=store,
        state_mask=xcl.mask.aes256gcm(KEY),
        variables=variables,
    ) as c:
        c.apply(TEST_PLUGIN_CONFIG)
        record = store.record(FIRST_ADDRESS)
        c.destroy()

    assert SECRET.encode() not in record
    assert b"first-one" in record
