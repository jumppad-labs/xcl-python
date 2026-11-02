"""A plugin registered as a command, a program and its arguments, starts and applies.

The command is the Python interpreter running ``launcher.py``, which records
that it ran and then becomes the recording fixture plugin, so the plugin is
started the way a plugin written in Python would be, as ``python plugin.py``.
Each test applies one recording resource through it and destroys it, in the
synchronous and the asyncio API.
"""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path

import pytest

import xcl
import xcl.aio

LAUNCHER = Path(__file__).resolve().parent / "launcher.py"

ADDRESS = "resource.recording.one"

pytestmark = pytest.mark.usefixtures("engine")


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    """Plugins are cached under HOME, so every test gets its own."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def recording_config(directory: Path, log: Path) -> Path:
    path = directory / "main.xcl"
    path.write_text(
        textwrap.dedent(
            f"""
            resource "recording" "one" {{
              log = "{log.as_posix()}"
              value = "launched"
            }}
            """
        ).lstrip()
    )
    return path


def command_registry(marker: Path, plugin: Path) -> xcl.LocalRegistry:
    """A registry starting ``plugin`` through the launcher, as a command."""
    registry = xcl.LocalRegistry()
    registry.register_external_plugin([sys.executable, LAUNCHER, str(marker), plugin])
    return registry


def recorded_steps(log: Path) -> list[tuple[str, str]]:
    """The steps the recording plugin wrote to ``log``, as (step, address), in order."""
    records = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    return [(record["step"], record["address"]) for record in records]


def test_plugin_registered_as_command_applies(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"
    marker = tmp_path / "launched"
    config = recording_config(tmp_path, log)

    with xcl.Config(registries=[command_registry(marker, recording_plugin)], state_path=tmp_path / "state") as c:
        try:
            c.apply(config)
            applied = c.find(None, ADDRESS)
        finally:
            c.destroy()
            remaining = c.entity_count()

    assert marker.read_text() == str(recording_plugin)
    assert isinstance(applied, xcl.Entity)
    assert applied.output == "one-launched"
    assert ("create", ADDRESS) in recorded_steps(log)
    assert recorded_steps(log)[-1] == ("destroy", ADDRESS)
    assert remaining == 0


def test_plugin_registered_as_command_applies_from_asyncio(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"
    marker = tmp_path / "launched"
    config = recording_config(tmp_path, log)

    async def main() -> tuple[object, int]:
        async with xcl.aio.Config(registries=[command_registry(marker, recording_plugin)], state_path=tmp_path / "state") as c:
            try:
                await c.apply(config)
                applied = await c.find(None, ADDRESS)
            finally:
                await c.destroy()
                remaining = await c.entity_count()
        return applied, remaining

    applied, remaining = asyncio.run(main())

    assert marker.read_text() == str(recording_plugin)
    assert isinstance(applied, xcl.Entity)
    assert applied.output == "one-launched"
    assert ("create", ADDRESS) in recorded_steps(log)
    assert recorded_steps(log)[-1] == ("destroy", ADDRESS)
    assert remaining == 0


def test_plugin_registered_by_path_applies(tmp_path, recording_plugin):
    log = tmp_path / "recording.log"
    config = recording_config(tmp_path, log)
    registry = xcl.LocalRegistry()
    registry.register_external_plugin(recording_plugin)

    with xcl.Config(registries=[registry], state_path=tmp_path / "state") as c:
        try:
            c.apply(config)
            applied = c.find(None, ADDRESS)
        finally:
            c.destroy()
            remaining = c.entity_count()

    assert isinstance(applied, xcl.Entity)
    assert applied.output == "one-launched"
    assert ("create", ADDRESS) in recorded_steps(log)
    assert remaining == 0
