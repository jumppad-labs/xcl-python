"""The pretty logger's line layout, held to the lines Go's example writes.

Every expected line below was produced once by running Go: a throwaway
program writing the same event through ``events.SlogHandler`` into
charmbracelet/log v0.4.2 (``TextFormatter``, ``ReportTimestamp``,
``TimeFormat: time.Kitchen``) into a buffer, with the event at a fixed time
in UTC. Go's output is the authority; the lines are pasted, never derived
from the code under test. The tests run with ``TZ=UTC``, so they are skipped
where the time zone cannot be set (Windows).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pytest

import xcl
from xcl import _prettyline
from xcl.events import Event


@pytest.fixture(autouse=True)
def utc(monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("the time zone cannot be set on this platform")
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 1, 2, hour, minute, 5, tzinfo=timezone.utc)


def event(**fields) -> Event:
    values = {"time": at(15, 4), "source": "core", "operation": "create", "phase": "start"}
    values.update(fields)
    return Event(**values)


def line(e: Event, level: int = logging.INFO, message: str = "create start") -> str:
    return _prettyline.format_line(e, level, message)


def value_line(value) -> str:
    return line(event(meta={"value": value}))


class RecordingStyler:
    """Wraps each styled piece as ``<style>text</>``, so a test sees which style each piece got."""

    def __call__(self, text: str, style: str) -> str:
        if not style:
            return text
        return f"<{style}>{text}</>"


# -- the time ---------------------------------------------------------------------


def test_kitchen_midnight():
    assert line(event(time=at(0, 4))) == "12:04AM INFO create start source=core operation=create phase=start\n"


def test_kitchen_noon():
    assert line(event(time=at(12, 0))) == "12:00PM INFO create start source=core operation=create phase=start\n"


def test_kitchen_afternoon():
    assert line(event(time=at(15, 4))) == "3:04PM INFO create start source=core operation=create phase=start\n"


# -- levels -----------------------------------------------------------------------


def test_level_debug_label():
    e = event(operation="apply", phase="log", meta={"level": "debug", "message": "decided every entity"})

    assert line(e, logging.DEBUG, "decided every entity") == "3:04PM DEBU decided every entity source=core operation=apply phase=log\n"


def test_level_info_label():
    assert line(event()) == "3:04PM INFO create start source=core operation=create phase=start\n"


def test_level_warn_label():
    e = event(phase="blocked", resource_id="resource.cache.main")

    assert line(e, logging.WARNING, "create blocked") == (
        "3:04PM WARN create blocked source=core operation=create phase=blocked resource=resource.cache.main\n"
    )


def test_level_error_label():
    e = event(phase="error", resource_id="resource.cache.main", error=xcl.Error("boom"))

    assert line(e, logging.ERROR, "create error") == (
        "3:04PM ERRO create error source=core operation=create phase=error resource=resource.cache.main error=boom\n"
    )


def test_message_omitted_when_empty():
    e = event(operation="apply", phase="log", meta={"level": "info"})

    assert line(e, logging.INFO, "") == "3:04PM INFO source=core operation=apply phase=log\n"


# -- attributes -------------------------------------------------------------------


def test_attribute_order():
    e = event(
        phase="error",
        resource_type="recording.one",
        resource_id="resource.recording.one",
        file="/work/main.xcl",
        duration=timedelta(microseconds=1500),
        error=xcl.Error("boom"),
        meta={"zeta": "z", "alpha": "a"},
    )

    assert line(e, logging.ERROR, "create error") == (
        "3:04PM ERRO create error source=core operation=create phase=error resource=resource.recording.one "
        "type=recording.one file=/work/main.xcl duration=1.5ms error=boom alpha=a zeta=z\n"
    )


def test_unset_attributes_left_out():
    e = event(operation="apply")

    assert line(e, message="apply start") == "3:04PM INFO apply start source=core operation=apply phase=start\n"


def test_details_sorted():
    e = event(operation="apply", meta={"c": "3", "a": "1", "b": "2"})

    assert line(e, message="apply start") == "3:04PM INFO apply start source=core operation=apply phase=start a=1 b=2 c=3\n"


def test_log_event_level_and_message_not_repeated():
    e = event(
        source="TemplatePlugin",
        phase="log",
        resource_id="template.welcome",
        meta={"level": "info", "message": "rendered template", "path": "/tmp/welcome.txt"},
    )

    assert line(e, message="rendered template") == (
        "3:04PM INFO rendered template source=TemplatePlugin operation=create phase=log resource=template.welcome path=/tmp/welcome.txt\n"
    )


def test_error_value_is_str_of_error():
    e = event(phase="error", error=xcl.Error("the provider failed"))

    assert line(e, logging.ERROR, "create error") == (
        '3:04PM ERRO create error source=core operation=create phase=error error="the provider failed"\n'
    )


# -- durations --------------------------------------------------------------------


def test_duration_formatting_fractional_ms():
    e = event(phase="success", duration=timedelta(microseconds=1500))

    assert line(e, message="create success") == "3:04PM INFO create success source=core operation=create phase=success duration=1.5ms\n"


def test_duration_formatting_whole_ms():
    e = event(phase="success", duration=timedelta(milliseconds=5))

    assert line(e, message="create success") == "3:04PM INFO create success source=core operation=create phase=success duration=5ms\n"


def test_duration_formatting_microseconds():
    e = event(phase="success", duration=timedelta(microseconds=999))

    assert line(e, message="create success") == "3:04PM INFO create success source=core operation=create phase=success duration=999µs\n"


def test_duration_formatting_seconds():
    e = event(phase="success", duration=timedelta(milliseconds=1500))

    assert line(e, message="create success") == "3:04PM INFO create success source=core operation=create phase=success duration=1.5s\n"


def test_duration_formatting_minutes():
    e = event(phase="success", duration=timedelta(seconds=61))

    assert line(e, message="create success") == "3:04PM INFO create success source=core operation=create phase=success duration=1m1s\n"


def test_duration_formatting_hours():
    e = event(phase="success", duration=timedelta(hours=2))

    assert line(e, message="create success") == "3:04PM INFO create success source=core operation=create phase=success duration=2h0m0s\n"


def test_zero_duration_left_out():
    e = event(phase="success", duration=timedelta(0))

    assert line(e, message="create success") == "3:04PM INFO create success source=core operation=create phase=success\n"


# -- values -----------------------------------------------------------------------


def test_int_value():
    assert value_line(42) == "3:04PM INFO create start source=core operation=create phase=start value=42\n"


def test_integral_float_value():
    assert value_line(100.0) == "3:04PM INFO create start source=core operation=create phase=start value=100\n"


def test_six_digit_float_value_stays_plain():
    assert value_line(123456.0) == "3:04PM INFO create start source=core operation=create phase=start value=123456\n"


def test_seven_digit_float_value_uses_exponent():
    assert value_line(1234567.0) == "3:04PM INFO create start source=core operation=create phase=start value=1.234567e+06\n"


def test_exponent_float_value():
    assert value_line(1e6) == "3:04PM INFO create start source=core operation=create phase=start value=1e+06\n"


def test_large_exponent_float_value():
    assert value_line(1.5e300) == "3:04PM INFO create start source=core operation=create phase=start value=1.5e+300\n"


def test_fractional_float_value():
    assert value_line(1.5) == "3:04PM INFO create start source=core operation=create phase=start value=1.5\n"


def test_negative_float_value():
    assert value_line(-2.5) == "3:04PM INFO create start source=core operation=create phase=start value=-2.5\n"


def test_small_float_value_stays_plain():
    assert value_line(0.0001) == "3:04PM INFO create start source=core operation=create phase=start value=0.0001\n"


def test_tiny_float_value_uses_exponent():
    assert value_line(1e-05) == "3:04PM INFO create start source=core operation=create phase=start value=1e-05\n"


def test_bool_true_value():
    assert value_line(True) == "3:04PM INFO create start source=core operation=create phase=start value=true\n"


def test_bool_false_value():
    assert value_line(False) == "3:04PM INFO create start source=core operation=create phase=start value=false\n"


def test_none_value():
    assert value_line(None) == "3:04PM INFO create start source=core operation=create phase=start value=<nil>\n"


def test_list_value():
    assert value_line(["a", 1.0, True]) == '3:04PM INFO create start source=core operation=create phase=start value="[a 1 true]"\n'


def test_empty_list_value():
    assert value_line([]) == "3:04PM INFO create start source=core operation=create phase=start value=[]\n"


def test_map_value():
    assert value_line({"b": 1.0, "a": "x"}) == '3:04PM INFO create start source=core operation=create phase=start value="map[a:x b:1]"\n'


def test_nested_map_value():
    assert value_line({"a": ["x", {"k": "v"}]}) == (
        '3:04PM INFO create start source=core operation=create phase=start value="map[a:[x map[k:v]]]"\n'
    )


def test_empty_map_value():
    assert value_line({}) == "3:04PM INFO create start source=core operation=create phase=start value=map[]\n"


# -- quoting and escaping ---------------------------------------------------------


def test_value_with_space_quoted():
    assert value_line("a b") == '3:04PM INFO create start source=core operation=create phase=start value="a b"\n'


def test_value_with_equals_quoted():
    assert value_line("a=b") == '3:04PM INFO create start source=core operation=create phase=start value="a=b"\n'


def test_value_with_quote_escaped():
    assert value_line('say "hi"') == '3:04PM INFO create start source=core operation=create phase=start value="say \\"hi\\""\n'


def test_value_with_tab_escaped():
    assert value_line("a\tb") == '3:04PM INFO create start source=core operation=create phase=start value="a\\tb"\n'


def test_value_with_control_character_escaped():
    assert value_line("a\x01b") == '3:04PM INFO create start source=core operation=create phase=start value="a\\x01b"\n'


def test_value_with_non_breaking_space_escaped():
    assert value_line("a b") == '3:04PM INFO create start source=core operation=create phase=start value="a\\u00a0b"\n'


def test_printable_unicode_value_not_quoted():
    assert value_line("héllo") == "3:04PM INFO create start source=core operation=create phase=start value=héllo\n"


def test_empty_value_written_as_quotes():
    assert value_line("") == '3:04PM INFO create start source=core operation=create phase=start value=""\n'


# -- multi-line values ------------------------------------------------------------


def test_multiline_value_last():
    assert value_line("first\nsecond") == (
        "3:04PM INFO create start source=core operation=create phase=start\n  value=\n  │ first\n  │ second\n"
    )


def test_multiline_value_followed_by_attribute():
    e = event(meta={"a": "first\nsecond", "b": "after"})

    assert line(e) == "3:04PM INFO create start source=core operation=create phase=start\n  a=\n  │ first\n  │ second\n b=after\n"


def test_multiline_value_with_trailing_newline():
    assert value_line("first\nsecond\n") == (
        "3:04PM INFO create start source=core operation=create phase=start\n  value=\n  │ first\n  │ second\n\n"
    )


def test_multiline_value_escapes_without_quoting():
    assert value_line('say "hi"\nthen\tgo') == (
        '3:04PM INFO create start source=core operation=create phase=start\n  value=\n  │ say "hi"\n  │ then\\tgo\n'
    )


def test_multiline_error():
    e = event(phase="error", error=xcl.Error("line one\nline two"))

    assert line(e, logging.ERROR, "create error") == (
        "3:04PM ERRO create error source=core operation=create phase=error\n  error=\n  │ line one\n  │ line two\n"
    )


# -- lines that are not an event's own --------------------------------------------


def test_format_record_writes_given_attributes():
    text = _prettyline.format_record(
        at(15, 4), logging.WARNING, "unable to show configuration", [("resource", "resource.cache.main"), ("error", "boom")]
    )

    assert text == "3:04PM WARN unable to show configuration resource=resource.cache.main error=boom\n"


# -- styles -----------------------------------------------------------------------


def test_source_key_and_value_styles():
    text = _prettyline.format_line(event(), logging.INFO, "create start", RecordingStyler())

    assert " <magenta>source</><dim>=</><bold magenta>core</>" in text


def test_operation_key_and_value_styles():
    text = _prettyline.format_line(event(), logging.INFO, "create start", RecordingStyler())

    assert " <yellow>operation</><dim>=</><bold yellow>create</>" in text


def test_resource_key_and_value_styles():
    text = _prettyline.format_line(event(resource_id="resource.cache.main"), logging.INFO, "create start", RecordingStyler())

    assert " <cyan>resource</><dim>=</><bold cyan>resource.cache.main</>" in text


def test_other_key_dim_value_plain():
    text = _prettyline.format_line(event(), logging.INFO, "create start", RecordingStyler())

    assert " <dim>phase</><dim>=</>start" in text


def test_quoted_value_styled_with_quotes():
    text = _prettyline.format_line(event(resource_id="a b"), logging.INFO, "create start", RecordingStyler())

    assert ' <cyan>resource</><dim>=</><bold cyan>"a b"</>' in text


def test_multiline_gutter_dim():
    text = _prettyline.format_line(event(meta={"value": "first\nsecond"}), logging.INFO, "create start", RecordingStyler())

    assert "\n  <dim>value</><dim>=</>\n<dim>  │ </>first\n<dim>  │ </>second\n" in text


def test_time_and_message_unstyled():
    text = _prettyline.format_line(event(), logging.INFO, "create start", RecordingStyler())

    assert text.startswith("3:04PM <bold cyan>INFO</> create start ")


def test_debug_level_style():
    text = _prettyline.format_line(event(), logging.DEBUG, "create start", RecordingStyler())

    assert text.startswith("3:04PM <bold blue>DEBU</> ")


def test_warn_level_style():
    text = _prettyline.format_line(event(), logging.WARNING, "create start", RecordingStyler())

    assert text.startswith("3:04PM <bold yellow>WARN</> ")


def test_error_level_style():
    text = _prettyline.format_line(event(), logging.ERROR, "create start", RecordingStyler())

    assert text.startswith("3:04PM <bold red>ERRO</> ")
