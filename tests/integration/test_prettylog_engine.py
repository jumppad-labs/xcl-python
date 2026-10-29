"""The pretty logger against the real engine: one line of setup, each event a line, created resources shown beneath them.

Every test applies configuration written to a temporary directory with the
recording fixture plugin, whose provider fills in ``output`` on create, and
reads what ``xcl.prettylog`` wrote.
"""

from __future__ import annotations

import io
import logging
import os
import re
import textwrap
import threading
from pathlib import Path

import pytest

import xcl

# the start of every event line: Go's Kitchen time and a level label
EVENT_LINE = re.compile(r"^\d{1,2}:\d{2}(AM|PM) (DEBU|INFO|WARN|ERRO) ")


def write_config(directory: Path, text: str, name: str = "main.xcl") -> Path:
    path = directory / name
    path.write_text(textwrap.dedent(text).lstrip())
    return path


def plugin_registry(plugin: Path) -> xcl.LocalRegistry:
    found = xcl.LocalRegistry()
    found.register_external_plugin(plugin)
    return found


def one_resource_config(directory: Path) -> Path:
    """A configuration creating one recording resource, whose output the provider sets to ``one-a``."""
    return write_config(
        directory,
        f"""
        resource "recording" "one" {{
          log = "{(directory / "log.jsonl").as_posix()}"
          value = "a"
        }}
        """,
    )


def two_resources_config(directory: Path) -> Path:
    log = (directory / "log.jsonl").as_posix()
    return write_config(
        directory,
        f"""
        resource "recording" "one" {{
          log = "{log}"
          value = "a"
        }}

        resource "recording" "two" {{
          log = "{log}"
          value = "b"
        }}
        """,
    )


def unsupported_block_config(directory: Path) -> Path:
    """Nine lines whose second resource has a nested block its type does not have, on line 7."""
    return write_config(
        directory,
        f"""
        resource "recording" "one" {{
          log = "{(directory / "log.jsonl").as_posix()}"
          value = "a"
        }}

        resource "recording" "two" {{
          nope {{
            a = 1
          }}
        }}
        """,
    )


def builtins_config(directory: Path) -> Path:
    """A variable, an output and a module beside one recording resource."""
    leaf = directory / "leaf"
    leaf.mkdir()
    write_config(leaf, 'variable "colour" {\n  default = "blue"\n}\n', name="leaf.xcl")
    return write_config(
        directory,
        f"""
        variable "name" {{
          default = "a"
        }}

        resource "recording" "one" {{
          log = "{(directory / "log.jsonl").as_posix()}"
          value = variable.name
        }}

        output "out" {{
          value = resource.recording.one.output
        }}

        module "leaf" {{
          source = "./leaf"
        }}
        """,
    )


def apply_with(tmp_path: Path, plugin: Path, config: Path, on_event, *, state: str = "state", event_data=xcl.EventDataLevel.PROCESSED) -> None:
    with xcl.Config(
        registries=[plugin_registry(plugin)],
        state_path=tmp_path / state,
        on_event=on_event,
        event_data=event_data,
    ) as c:
        c.apply(config)


def normalised(text: str) -> str:
    """``text`` with the time of each line and every duration replaced, the parts that differ between runs."""
    text = re.sub(r"^\d{1,2}:\d{2}(AM|PM) ", "<time> ", text, flags=re.MULTILINE)
    return re.sub(r"duration=\S+", "duration=<duration>", text)


def event_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line and not line.startswith(" ")]


def line_index(lines: list[str], needle: str) -> int:
    for i, line in enumerate(lines):
        if needle in line:
            return i
    raise AssertionError(f"no line contains {needle!r}:\n" + "\n".join(lines))


# -- setup and event lines ------------------------------------------------------------


def test_prettylog_setup_writes_one_line_per_event(tmp_path, recording_plugin):
    out = io.StringIO()

    apply_with(tmp_path, recording_plugin, one_resource_config(tmp_path), xcl.prettylog.handler(out))

    lines = event_lines(out.getvalue())
    assert lines
    for line in lines:
        assert EVENT_LINE.match(line), line
    assert any(" INFO apply start " in line for line in lines)
    assert any(" INFO create start " in line for line in lines)
    assert any(" INFO apply success " in line for line in lines)
    success = lines[line_index(lines, " INFO create success ")]
    assert " source=core " in success
    assert " operation=create " in success
    assert " phase=success " in success
    assert " resource=resource.recording.one " in success


def test_prettylog_default_level_writes_no_debug_lines(tmp_path, recording_plugin):
    out = io.StringIO()

    apply_with(tmp_path, recording_plugin, one_resource_config(tmp_path), xcl.prettylog.handler(out))

    assert " DEBU " not in out.getvalue()


def test_prettylog_configuration_follows_creation(tmp_path, recording_plugin):
    out = io.StringIO()

    apply_with(tmp_path, recording_plugin, one_resource_config(tmp_path), xcl.prettylog.handler(out))

    lines = out.getvalue().splitlines()
    success = line_index(lines, " INFO create success ")
    assert "resource=resource.recording.one" in lines[success]
    assert lines[success + 1] == '  resource "recording" "one" {'
    block = []
    for line in lines[success + 1 :]:
        if not line.startswith(" "):
            break
        block.append(line)
    assert block[-1] == "  }"
    assert any(re.search(r'output\s+=\s+"one-a"', line) for line in block)
    following = lines[success + 1 + len(block)]
    assert EVENT_LINE.match(following), following


# -- through an application's logger ----------------------------------------------------


def test_prettylog_through_application_logger(tmp_path, recording_plugin):
    stream = io.StringIO()
    apply_with(tmp_path, recording_plugin, one_resource_config(tmp_path), xcl.prettylog.handler(stream), state="stream-state")

    through_logger = io.StringIO()
    logger = logging.Logger("app")
    logger.propagate = False
    console = logging.StreamHandler(through_logger)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)
    apply_with(tmp_path, recording_plugin, one_resource_config(tmp_path), xcl.prettylog.handler(logger=logger), state="logger-state")

    assert normalised(through_logger.getvalue()) == normalised(stream.getvalue())


# -- levels -----------------------------------------------------------------------------


def test_prettylog_warn_level_is_terse(tmp_path, recording_plugin):
    out = io.StringIO()

    apply_with(tmp_path, recording_plugin, one_resource_config(tmp_path), xcl.prettylog.handler(out, logging.WARNING))

    text = out.getvalue()
    assert not [line for line in text.splitlines() if line.startswith(" ")]
    assert " INFO " not in text


def test_prettylog_warn_level_still_shows_report(tmp_path, recording_plugin):
    out = io.StringIO()

    with pytest.raises(xcl.ConfigError):
        apply_with(tmp_path, recording_plugin, unsupported_block_config(tmp_path), xcl.prettylog.handler(out, logging.WARNING))

    lines = out.getvalue().splitlines()
    error = line_index(lines, " ERRO ")
    report = lines[error + 1 :]
    assert report[0] == "  Error: Unsupported block type"
    assert any(line.startswith("       7 | ") for line in report)
    assert " INFO " not in out.getvalue()


def test_prettylog_debug_level_adds_debug_events(tmp_path, recording_plugin):
    out = io.StringIO()

    apply_with(tmp_path, recording_plugin, one_resource_config(tmp_path), xcl.prettylog.handler(out, logging.DEBUG))

    lines = event_lines(out.getvalue())
    assert any(" DEBU decided every entity " in line for line in lines)
    assert any(" INFO create success " in line for line in lines)


# -- a configuration mistake ------------------------------------------------------------


def test_prettylog_configuration_mistake_shows_report(tmp_path, recording_plugin):
    out = io.StringIO()
    config = unsupported_block_config(tmp_path)

    with pytest.raises(xcl.ConfigError):
        apply_with(tmp_path, recording_plugin, config, xcl.prettylog.handler(out))

    lines = out.getvalue().splitlines()
    error = line_index(lines, " ERRO ")
    report = []
    for line in lines[error + 1 :]:
        if line and not line.startswith(" "):
            break
        report.append(line)
    assert report[0] == "  Error: Unsupported block type"
    assert any(f"on {config.as_posix()} line 7" in line or f"on {config} line 7" in line for line in report)
    assert any(line.startswith("       7 |   nope {") for line in report)


def test_prettylog_configuration_mistake_reported_once(tmp_path, recording_plugin):
    out = io.StringIO()

    with pytest.raises(xcl.ConfigError):
        apply_with(tmp_path, recording_plugin, unsupported_block_config(tmp_path), xcl.prettylog.handler(out))

    assert out.getvalue().count("Error: Unsupported block type") == 1


# -- colour -----------------------------------------------------------------------------


def run_on_pseudo_terminal(tmp_path: Path, plugin: Path) -> str:
    """Apply one resource with the pretty logger writing to a pseudo-terminal, and return what the terminal received."""
    pty = pytest.importorskip("pty")
    controller, terminal = pty.openpty()
    received: list[bytes] = []

    def read() -> None:
        while True:
            try:
                chunk = os.read(controller, 4096)
            except OSError:
                return
            if not chunk:
                return
            received.append(chunk)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    stream = os.fdopen(terminal, "w")
    try:
        apply_with(tmp_path, plugin, one_resource_config(tmp_path), xcl.prettylog.handler(stream))
    finally:
        stream.close()
        reader.join(timeout=5)
        os.close(controller)
    return b"".join(received).decode()


def test_prettylog_colours_pseudo_terminal(tmp_path, recording_plugin, monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    text = run_on_pseudo_terminal(tmp_path, recording_plugin)

    assert "\x1b[" in text
    assert "\x1b[1;35mcore\x1b[0m" in text
    assert "\x1b[1;33mcreate\x1b[0m" in text
    assert "\x1b[1;36mresource.recording.one\x1b[0m" in text


def test_prettylog_pseudo_terminal_with_no_color_has_no_colour(tmp_path, recording_plugin, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")

    text = run_on_pseudo_terminal(tmp_path, recording_plugin)

    assert "create success" in text
    assert "\x1b" not in text


def test_prettylog_file_has_no_colour(tmp_path, recording_plugin, monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    path = tmp_path / "log.txt"

    with open(path, "w") as stream:
        apply_with(tmp_path, recording_plugin, one_resource_config(tmp_path), xcl.prettylog.handler(stream))

    text = path.read_text()
    assert "create success" in text
    assert "\x1b" not in text


# -- resource data off, and items with no configuration form ---------------------------------


def test_prettylog_guidance_once_without_data(tmp_path, recording_plugin):
    out = io.StringIO()

    apply_with(
        tmp_path,
        recording_plugin,
        two_resources_config(tmp_path),
        xcl.prettylog.handler(out),
        event_data=xcl.EventDataLevel.NONE,
    )

    text = out.getvalue()
    assert text.count("configuration not shown") == 1
    assert 'hint="create the configuration with event_data=xcl.EventDataLevel.PROCESSED"' in text
    assert not [line for line in text.splitlines() if line.startswith(" ")]
    assert text.count(" INFO create success ") == 2


def test_prettylog_builtins_silent(tmp_path, recording_plugin):
    out = io.StringIO()

    apply_with(tmp_path, recording_plugin, builtins_config(tmp_path), xcl.prettylog.handler(out))

    text = out.getvalue()
    assert "unable to show configuration" not in text
    blocks = [line for line in text.splitlines() if line.startswith("  ") and line.endswith("{")]
    assert blocks == ['  resource "recording" "one" {']
    lines = event_lines(text)
    assert any("resource=variable.name" in line and " create success " in line for line in lines)
    assert any("resource=output.out" in line and " create success " in line for line in lines)
