"""xcl.prettylog: every event as a readable line, with configuration and reports beneath.

Events are built by hand or delivered by a configuration over the fake
transport. Every expected line is written out here; the lines' layout itself
is held to Go's in test_prettyline.py. The tests run with ``TZ=UTC`` so the
time at the start of each line is known, and are skipped where the time
zone cannot be set (Windows).
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from datetime import datetime, timezone

import pytest

import xcl
import xcl.aio
import xcl.highlight
import xcl.prettylog
from xcl._client import Client
from xcl._core import core_pb2
from xcl.events import Event
from xcl.highlight import Kind, Token
from fakes import FakeTransport


@pytest.fixture(autouse=True)
def utc(monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("the time zone cannot be set on this platform")
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


# -- events, reports and transports -------------------------------------------

EVENT_TIME = datetime(2026, 1, 2, 15, 4, 5, tzinfo=timezone.utc)
EVENT_NANOS = int(EVENT_TIME.timestamp()) * 1_000_000_000

SAVED_RECORD = b'{"meta": {"id": "app.web", "name": "web", "type": "app"}, "image": "nginx"}'
OTHER_RECORD = b'{"meta": {"id": "app.api", "name": "api", "type": "app"}, "image": "httpd"}'

WEB_TOKENS = [
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_BLOCK_TYPE, text="app"),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" "),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_NAME_LABEL, text='"web"'),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" {\n  "),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_ATTRIBUTE, text="image"),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" = "),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_STRING, text='"nginx"'),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="\n}\n"),
]

API_TOKENS = [
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_BLOCK_TYPE, text="app"),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" "),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_NAME_LABEL, text='"api"'),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" {\n  "),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_ATTRIBUTE, text="image"),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" = "),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_STRING, text='"httpd"'),
    core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="\n}\n"),
]

WEB_BLOCK = '  app "web" {\n    image = "nginx"\n  }\n'
API_BLOCK = '  app "api" {\n    image = "httpd"\n  }\n'

WEB_CREATE_START = "3:04PM INFO create start source=core operation=create phase=start resource=app.web type=app\n"
WEB_CREATE_SUCCESS = "3:04PM INFO create success source=core operation=create phase=success resource=app.web type=app\n"
API_CREATE_SUCCESS = "3:04PM INFO create success source=core operation=create phase=success resource=app.api type=app\n"
APPLY_START = "3:04PM INFO apply start source=core operation=apply phase=start\n"
APPLY_SUCCESS = "3:04PM INFO apply success source=core operation=apply phase=success\n"

GUIDANCE = (
    "3:04PM INFO configuration not shown: events carry no resource data "
    'hint="create the configuration with event_data=xcl.EventDataLevel.PROCESSED"\n'
)

# an unsupported block's report, and the same report as the engine sends it
REPORT_TOKENS = [
    Token(kind=Kind.ERROR, text="Error"),
    Token(kind=Kind.TEXT, text=": "),
    Token(kind=Kind.SUMMARY, text="Unsupported block type"),
    Token(kind=Kind.TEXT, text="\n\n  on main.hcl line 3:\n"),
    Token(kind=Kind.GUTTER, text="   3 |"),
    Token(kind=Kind.TEXT, text=' widget "x" {\n\nBlocks of type "widget" are not expected here.\n'),
]
REPORT_PROTO = [core_pb2.Token(kind=int(token.kind), text=token.text) for token in REPORT_TOKENS]
REPORT = (
    "  Error: Unsupported block type\n"
    "\n"
    "    on main.hcl line 3:\n"
    '     3 | widget "x" {\n'
    "\n"
    '  Blocks of type "widget" are not expected here.\n'
)

# a second problem, for a closing error holding more than one
SECOND_REPORT_TOKENS = REPORT_TOKENS + [
    Token(kind=Kind.TEXT, text="\n"),
    Token(kind=Kind.ERROR, text="Error"),
    Token(kind=Kind.TEXT, text=": "),
    Token(kind=Kind.SUMMARY, text="Missing name"),
    Token(kind=Kind.TEXT, text="\n\n  on main.hcl line 9:\n"),
    Token(kind=Kind.GUTTER, text="   9 |"),
    Token(kind=Kind.TEXT, text=" app {\n"),
]
TWO_PROBLEM_REPORT = (
    "  Error: Unsupported block type\n"
    "\n"
    "    on main.hcl line 3:\n"
    '     3 | widget "x" {\n'
    "\n"
    '  Blocks of type "widget" are not expected here.\n'
    "\n"
    "  Error: Missing name\n"
    "\n"
    "    on main.hcl line 9:\n"
    "     9 | app {\n"
)

PARSE_ERROR = '3:04PM ERRO parse error source=core operation=parse phase=error file=main.hcl error="unsupported block"\n'
VALIDATE_ERROR = (
    "3:04PM ERRO validate error source=core operation=validate phase=error resource=widget.x "
    'error="unsupported block"\n'
)
APPLY_ERROR = '3:04PM ERRO apply error source=core operation=apply phase=error error="configuration is invalid"\n'


def event(**fields) -> Event:
    """An event built by hand at EVENT_TIME, a core create start unless ``fields`` say otherwise."""
    values = {"time": EVENT_TIME, "source": "core", "operation": "create", "phase": "start"}
    values.update(fields)
    return Event(**values)


def web_create_success(data: bytes = b"") -> Event:
    return event(phase="success", resource_type="app", resource_id="app.web", data=data)


def unsupported_block() -> xcl.ConfigError:
    """The error of one problem, an unsupported block, with its report."""
    return xcl.ConfigError(
        "unsupported block",
        details={"file": "main.hcl", "line": "3", "summary": "Unsupported block type"},
        tokens=REPORT_TOKENS,
    )


def missing_name() -> xcl.ConfigError:
    return xcl.ConfigError(
        "missing name",
        details={"file": "main.hcl", "line": "9", "summary": "Missing name"},
    )


def parse_error_event() -> Event:
    return event(operation="parse", phase="error", file="main.hcl", error=unsupported_block())


def closing_error_event(error: xcl.ConfigError) -> Event:
    return event(operation="apply", phase="error", error=error)


def proto_event(operation: str, phase: str, resource_id: str = "", data: bytes = b"", **fields) -> core_pb2.PollResponse:
    """A Poll response carrying one core event at EVENT_TIME."""
    return core_pb2.PollResponse(
        event=core_pb2.Event(
            time_unix_nano=EVENT_NANOS,
            source="core",
            operation=operation,
            phase=phase,
            resource_type="app" if resource_id else "",
            resource_id=resource_id,
            data=data,
            **fields,
        )
    )


FINISHED = core_pb2.PollResponse(finished=core_pb2.OperationFinished(operation_id=3))


def apply_transport(events: list[core_pb2.PollResponse], encoded=None) -> FakeTransport:
    """An apply whose Poll gives ``events`` then finishes, answering EncodeSavedEntity from ``encoded``."""
    script = {
        "StartApply": core_pb2.StartOperationResponse(operation_id=3),
        "Poll": events + [FINISHED],
    }
    if encoded is not None:
        script["EncodeSavedEntity"] = encoded
    return FakeTransport(script)


def encoded(tokens) -> core_pb2.EncodeSavedEntityResponse:
    return core_pb2.EncodeSavedEntityResponse(text="".join(t.text for t in tokens).encode(), tokens=tokens)


def apply_through(transport: FakeTransport, on_event, event_data=xcl.EventDataLevel.PROCESSED) -> None:
    config = xcl.Config(on_event=on_event, event_data=event_data, client=Client(transport))
    config.apply("main.hcl")


def sent_encode_saved_entity_requests(transport: FakeTransport) -> list[core_pb2.EncodeSavedEntityRequest]:
    return [
        core_pb2.EncodeSavedEntityRequest.FromString(request)
        for _, method, request in transport.calls
        if method == "EncodeSavedEntity"
    ]


class Collect(logging.Handler):
    """A logging handler that keeps every record it is given."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def collecting_logger(name: str, level: int = logging.DEBUG) -> tuple[logging.Logger, Collect]:
    """A logger of its own, at ``level``, that keeps its records and passes none on."""
    logger = logging.getLogger("test_prettylog." + name)
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False
    collect = Collect()
    logger.addHandler(collect)
    return logger, collect


class TerminalStringIO(io.StringIO):
    """A StringIO that says it is a terminal."""

    def isatty(self) -> bool:
        return True


class FailingStream:
    """A stream whose every write fails."""

    def write(self, text: str) -> int:
        raise OSError("the disk is full")

    def flush(self) -> None:
        pass


class OddConfig:
    """Stands in for the configuration that delivered an event, failing to render in a way no engine error does."""

    _event_data = xcl.EventDataLevel.PROCESSED

    def __init__(self, failure: Exception) -> None:
        self.failure = failure

    def _saved_entity_tokens_now(self, data: bytes, **options) -> list[Token]:
        raise self.failure


# -- export ----------------------------------------------------------------------


def test_prettylog_is_exported():
    assert "prettylog" in xcl.__all__
    assert xcl.prettylog.LEVEL_ENV == "XCL_LOG_LEVEL"


# -- the level from the environment ---------------------------------------------


def test_level_from_env_debug(monkeypatch):
    monkeypatch.setenv("XCL_LOG_LEVEL", "debug")

    assert xcl.prettylog.level_from_env() == logging.DEBUG


def test_level_from_env_warn(monkeypatch):
    monkeypatch.setenv("XCL_LOG_LEVEL", "warn")

    assert xcl.prettylog.level_from_env() == logging.WARNING


def test_level_from_env_error(monkeypatch):
    monkeypatch.setenv("XCL_LOG_LEVEL", "error")

    assert xcl.prettylog.level_from_env() == logging.ERROR


def test_level_from_env_upper_case_info(monkeypatch):
    monkeypatch.setenv("XCL_LOG_LEVEL", "INFO")

    assert xcl.prettylog.level_from_env() == logging.INFO


def test_level_from_env_unset(monkeypatch):
    monkeypatch.delenv("XCL_LOG_LEVEL", raising=False)

    assert xcl.prettylog.level_from_env() == logging.INFO


def test_level_from_env_unknown(monkeypatch):
    monkeypatch.setenv("XCL_LOG_LEVEL", "loud")

    assert xcl.prettylog.level_from_env() == logging.INFO


# -- arguments -------------------------------------------------------------------


def test_handler_refuses_string_level():
    with pytest.raises(TypeError, match="level must be a logging level"):
        xcl.prettylog.handler(io.StringIO(), "info")  # type: ignore[arg-type]


def test_handler_refuses_bool_level():
    with pytest.raises(TypeError, match="level must be a logging level"):
        xcl.prettylog.handler(io.StringIO(), True)


def test_handler_refuses_file_and_logger():
    logger, _ = collecting_logger("file_and_logger")

    with pytest.raises(ValueError, match="give file or logger, not both"):
        xcl.prettylog.handler(io.StringIO(), logger=logger)


def test_handler_refuses_non_logger():
    with pytest.raises(TypeError, match="logger must be a logging.Logger"):
        xcl.prettylog.handler(logger="app")  # type: ignore[arg-type]


def test_handler_defaults_to_stderr(capsys):
    on_event = xcl.prettylog.handler()

    on_event(event(resource_type="app", resource_id="app.web"))

    captured = capsys.readouterr()
    assert captured.err == WEB_CREATE_START
    assert captured.out == ""


def test_handler_accepts_int_level():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out, 25)

    on_event(event(phase="blocked", resource_id="app.web"))

    assert out.getvalue() == "3:04PM WARN create blocked source=core operation=create phase=blocked resource=app.web\n"


def test_handler_with_int_level_skips_events_below_it():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out, 25)

    on_event(event(resource_type="app", resource_id="app.web"))

    assert out.getvalue() == ""


# -- levels ----------------------------------------------------------------------


def debug_log_event() -> Event:
    return event(source="plugin", phase="log", resource_id="app.web", meta={"level": "debug", "message": "probing"})


def test_info_handler_skips_debug_event():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(debug_log_event())

    assert out.getvalue() == ""


def test_debug_handler_writes_debug_event():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out, logging.DEBUG)

    on_event(debug_log_event())

    assert out.getvalue() == "3:04PM DEBU probing source=plugin operation=create phase=log resource=app.web\n"


def test_warn_handler_writes_no_info_line():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out, logging.WARNING)

    on_event(event(resource_type="app", resource_id="app.web"))

    assert out.getvalue() == ""


def test_warn_handler_writes_blocked_event():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out, logging.WARNING)

    on_event(event(phase="blocked", resource_id="app.web"))

    assert out.getvalue() == "3:04PM WARN create blocked source=core operation=create phase=blocked resource=app.web\n"


def test_error_handler_skips_blocked_event():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out, logging.ERROR)

    on_event(event(phase="blocked", resource_id="app.web"))

    assert out.getvalue() == ""


def test_warn_handler_writes_no_configuration():
    out = io.StringIO()
    transport = apply_transport(
        [proto_event("create", "success", "app.web", SAVED_RECORD)],
        encoded(WEB_TOKENS),
    )

    apply_through(transport, xcl.prettylog.handler(out, logging.WARNING))

    assert out.getvalue() == ""
    assert "EncodeSavedEntity" not in transport.methods_called()


# -- configuration beneath a creation ---------------------------------------------


def test_configuration_follows_create_success():
    out = io.StringIO()
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web", SAVED_RECORD),
            proto_event("apply", "success"),
        ],
        encoded(WEB_TOKENS),
    )

    apply_through(transport, xcl.prettylog.handler(out))

    assert out.getvalue() == WEB_CREATE_SUCCESS + WEB_BLOCK + APPLY_SUCCESS


def test_configuration_asks_for_computed_values():
    transport = apply_transport(
        [proto_event("create", "success", "app.web", SAVED_RECORD)],
        encoded(WEB_TOKENS),
    )

    apply_through(transport, xcl.prettylog.handler(io.StringIO()))

    requests = sent_encode_saved_entity_requests(transport)
    assert len(requests) == 1
    assert requests[0].entity == SAVED_RECORD
    assert requests[0].options.include_computed is True
    assert requests[0].tokens is True


def test_configuration_asks_for_nothing_but_computed_values():
    transport = apply_transport(
        [proto_event("create", "success", "app.web", SAVED_RECORD)],
        encoded(WEB_TOKENS),
    )

    apply_through(transport, xcl.prettylog.handler(io.StringIO()))

    options = sent_encode_saved_entity_requests(transport)[0].options
    assert options.include_empty is False
    assert options.reveal_sensitive is False
    assert options.show_references is False


def test_no_configuration_for_create_start():
    out = io.StringIO()
    transport = apply_transport(
        [proto_event("create", "start", "app.web", SAVED_RECORD)],
        encoded(WEB_TOKENS),
    )

    apply_through(transport, xcl.prettylog.handler(out))

    assert out.getvalue() == WEB_CREATE_START
    assert "EncodeSavedEntity" not in transport.methods_called()


def test_no_configuration_for_hand_built_event_without_data():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(web_create_success())

    assert out.getvalue() == WEB_CREATE_SUCCESS


def test_hand_built_event_with_data_warns_once():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(web_create_success(SAVED_RECORD))

    assert out.getvalue() == (
        WEB_CREATE_SUCCESS
        + '3:04PM WARN unable to show configuration resource=app.web error="the event was not delivered by a configuration"\n'
    )


def test_later_events_written_after_warning():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(web_create_success(SAVED_RECORD))
    on_event(event(operation="apply", phase="success"))

    assert out.getvalue() == (
        WEB_CREATE_SUCCESS
        + '3:04PM WARN unable to show configuration resource=app.web error="the event was not delivered by a configuration"\n'
        + APPLY_SUCCESS
    )


def test_not_encodable_skipped_silently():
    out = io.StringIO()
    transport = apply_transport(
        [proto_event("create", "success", "app.web", SAVED_RECORD)],
        core_pb2.Error(code="not_encodable", message="a variable has no configuration form"),
    )

    apply_through(transport, xcl.prettylog.handler(out))

    assert out.getvalue() == WEB_CREATE_SUCCESS


def test_not_encodable_resource_does_not_stop_later_configuration():
    out = io.StringIO()
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web", SAVED_RECORD),
            proto_event("create", "success", "app.api", OTHER_RECORD),
        ],
        [
            core_pb2.Error(code="not_encodable", message="a variable has no configuration form"),
            encoded(API_TOKENS),
        ],
    )

    apply_through(transport, xcl.prettylog.handler(out))

    assert out.getvalue() == WEB_CREATE_SUCCESS + API_CREATE_SUCCESS + API_BLOCK


def test_two_render_failures_warn_twice_and_apply_completes():
    out = io.StringIO()
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web", SAVED_RECORD),
            proto_event("create", "success", "app.api", OTHER_RECORD),
            proto_event("apply", "success"),
        ],
        [
            core_pb2.Error(code="unregistered_type", message="app is not registered"),
            core_pb2.Error(code="plugin_load", message="the app plugin failed to load"),
        ],
    )

    apply_through(transport, xcl.prettylog.handler(out))

    assert out.getvalue() == (
        WEB_CREATE_SUCCESS
        + '3:04PM WARN unable to show configuration resource=app.web error="app is not registered"\n'
        + API_CREATE_SUCCESS
        + '3:04PM WARN unable to show configuration resource=app.api error="the app plugin failed to load"\n'
        + APPLY_SUCCESS
    )
    assert transport.methods_called()[-1] == "Poll"


# -- guidance when the configuration carries no resource data ---------------------


def test_guidance_written_once_when_data_off():
    out = io.StringIO()
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web"),
            proto_event("create", "success", "app.api"),
        ]
    )

    apply_through(transport, xcl.prettylog.handler(out), event_data=xcl.EventDataLevel.NONE)

    assert out.getvalue() == WEB_CREATE_SUCCESS + GUIDANCE + API_CREATE_SUCCESS


def test_guidance_written_once_for_config_with_default_event_data():
    out = io.StringIO()
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web"),
            proto_event("create", "success", "app.api"),
        ]
    )
    config = xcl.Config(on_event=xcl.prettylog.handler(out), client=Client(transport))

    config.apply("main.hcl")

    assert out.getvalue().count("configuration not shown") == 1


def test_no_guidance_when_data_on_and_event_has_no_data():
    out = io.StringIO()
    transport = apply_transport([proto_event("create", "success", "app.web")])

    apply_through(transport, xcl.prettylog.handler(out), event_data=xcl.EventDataLevel.PROCESSED)

    assert out.getvalue() == WEB_CREATE_SUCCESS
    assert "EncodeSavedEntity" not in transport.methods_called()


def test_no_guidance_for_hand_built_event_without_data():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(web_create_success())
    on_event(web_create_success())

    assert out.getvalue() == WEB_CREATE_SUCCESS + WEB_CREATE_SUCCESS


def test_no_guidance_above_info():
    out = io.StringIO()
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web"),
            proto_event("create", "success", "app.api"),
        ]
    )

    apply_through(transport, xcl.prettylog.handler(out, logging.WARNING), event_data=xcl.EventDataLevel.NONE)

    assert out.getvalue() == ""


def test_warn_handler_writes_no_guidance():
    out = io.StringIO()
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web"),
            proto_event("create", "blocked", "app.api"),
        ]
    )

    apply_through(transport, xcl.prettylog.handler(out, logging.WARNING), event_data=xcl.EventDataLevel.NONE)

    assert out.getvalue() == "3:04PM WARN create blocked source=core operation=create phase=blocked resource=app.api type=app\n"


def test_warn_handler_writes_no_render_warning():
    out = io.StringIO()
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web", SAVED_RECORD),
            proto_event("create", "blocked", "app.api"),
        ],
        core_pb2.Error(code="unregistered_type", message="app is not registered"),
    )

    apply_through(transport, xcl.prettylog.handler(out, logging.WARNING))

    assert out.getvalue() == "3:04PM WARN create blocked source=core operation=create phase=blocked resource=app.api type=app\n"
    assert "EncodeSavedEntity" not in transport.methods_called()


# -- reports beneath configuration mistakes ---------------------------------------


def test_report_beneath_parse_error():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(parse_error_event())

    assert out.getvalue() == PARSE_ERROR + REPORT


def test_report_beneath_resource_error():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(event(operation="validate", phase="error", resource_id="widget.x", error=unsupported_block()))

    assert out.getvalue() == VALIDATE_ERROR + REPORT


def test_report_not_repeated_beneath_closing_error():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(event(operation="apply", phase="start"))
    on_event(parse_error_event())
    on_event(
        closing_error_event(
            xcl.ConfigError("configuration is invalid", causes=[unsupported_block()], tokens=REPORT_TOKENS)
        )
    )

    assert out.getvalue() == APPLY_START + PARSE_ERROR + REPORT + APPLY_ERROR


def test_report_beneath_closing_error_when_not_shown_before():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(event(operation="apply", phase="start"))
    on_event(
        closing_error_event(
            xcl.ConfigError("configuration is invalid", causes=[unsupported_block()], tokens=REPORT_TOKENS)
        )
    )

    assert out.getvalue() == APPLY_START + APPLY_ERROR + REPORT


def test_closing_error_with_more_problems_than_shown_writes_report():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(event(operation="apply", phase="start"))
    on_event(parse_error_event())
    on_event(
        closing_error_event(
            xcl.ConfigError(
                "configuration is invalid",
                causes=[unsupported_block(), missing_name()],
                tokens=SECOND_REPORT_TOKENS,
            )
        )
    )

    assert out.getvalue() == APPLY_START + PARSE_ERROR + REPORT + APPLY_ERROR + TWO_PROBLEM_REPORT


def test_next_operation_reports_its_closing_error_afresh():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    # the first operation shows its problem beneath the parse error, and
    # ends without a closing error
    on_event(event(operation="apply", phase="start"))
    on_event(parse_error_event())
    # the second shows none before its closing error
    on_event(event(operation="apply", phase="start"))
    on_event(
        closing_error_event(
            xcl.ConfigError("configuration is invalid", causes=[unsupported_block()], tokens=REPORT_TOKENS)
        )
    )

    assert out.getvalue() == APPLY_START + PARSE_ERROR + REPORT + APPLY_START + APPLY_ERROR + REPORT


def from_config(sent: Event, config: object) -> Event:
    """``sent`` as if ``config`` had delivered it."""
    sent._config = config
    return sent


def test_closing_error_report_not_hidden_by_another_configuration():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)
    first = object()
    second = object()

    on_event(from_config(event(operation="apply", phase="start"), first))
    on_event(from_config(event(operation="apply", phase="start"), second))
    # the second configuration shows its own problem
    on_event(from_config(parse_error_event(), second))
    # the first has shown none, so its closing error carries the report
    on_event(
        from_config(
            closing_error_event(
                xcl.ConfigError("configuration is invalid", causes=[unsupported_block()], tokens=REPORT_TOKENS)
            ),
            first,
        )
    )

    assert out.getvalue() == APPLY_START + APPLY_START + PARSE_ERROR + REPORT + APPLY_ERROR + REPORT


def test_closing_error_report_not_repeated_when_another_configuration_starts():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)
    first = object()
    second = object()

    on_event(from_config(event(operation="apply", phase="start"), first))
    # the first configuration shows its problem
    on_event(from_config(parse_error_event(), first))
    # another configuration's operation starts meanwhile
    on_event(from_config(event(operation="apply", phase="start"), second))
    # the first's closing error holds only the problem it showed
    on_event(
        from_config(
            closing_error_event(
                xcl.ConfigError("configuration is invalid", causes=[unsupported_block()], tokens=REPORT_TOKENS)
            ),
            first,
        )
    )

    assert out.getvalue() == APPLY_START + PARSE_ERROR + REPORT + APPLY_START + APPLY_ERROR


def test_no_report_for_error_without_tokens():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(event(operation="parse", phase="error", file="main.hcl", error=xcl.ConfigError("unsupported block")))

    assert out.getvalue() == PARSE_ERROR


def test_report_indented():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(parse_error_event())

    report_lines = out.getvalue().split("\n")[1:]
    assert len([line for line in report_lines if line]) == 4
    for line in report_lines:
        if line:
            assert line.startswith("  ")


def test_warn_handler_writes_report_beneath_parse_error():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out, logging.WARNING)

    on_event(parse_error_event())

    assert out.getvalue() == PARSE_ERROR + REPORT


def test_error_handler_writes_report_beneath_closing_error():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out, logging.ERROR)

    on_event(event(operation="apply", phase="start"))
    on_event(
        closing_error_event(
            xcl.ConfigError("configuration is invalid", causes=[unsupported_block()], tokens=REPORT_TOKENS)
        )
    )

    assert out.getvalue() == APPLY_ERROR + REPORT


def test_unsupported_block_report_appears_once_through_configuration():
    out = io.StringIO()
    problem = core_pb2.Error(
        code="config",
        message="unsupported block",
        details={"file": "main.hcl", "line": "3", "summary": "Unsupported block type"},
        report=REPORT_PROTO,
    )
    closing = core_pb2.Error(code="config", message="configuration is invalid", causes=[problem], report=REPORT_PROTO)
    transport = FakeTransport(
        {
            "StartApply": core_pb2.StartOperationResponse(operation_id=3),
            "Poll": [
                proto_event("apply", "start"),
                proto_event("parse", "error", file="main.hcl", error=problem),
                proto_event("apply", "error", error=closing),
                core_pb2.PollResponse(finished=core_pb2.OperationFinished(operation_id=3, error=closing)),
            ],
        }
    )
    config = xcl.Config(on_event=xcl.prettylog.handler(out), client=Client(transport))

    with pytest.raises(xcl.ConfigError):
        config.apply("main.hcl")

    assert out.getvalue() == APPLY_START + PARSE_ERROR + REPORT + APPLY_ERROR


# -- colour ----------------------------------------------------------------------


def test_plain_stream_has_no_colour():
    out = io.StringIO()
    transport = apply_transport(
        [proto_event("create", "success", "app.web", SAVED_RECORD)],
        encoded(WEB_TOKENS),
    )

    apply_through(transport, xcl.prettylog.handler(out))

    assert "\x1b" not in out.getvalue()


def test_terminal_formatter_colours_source_operation_resource():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out, formatter=xcl.highlight.TERMINAL)

    on_event(event(resource_id="app.web"))

    text = out.getvalue()
    assert "\x1b[1;35mcore\x1b[0m" in text
    assert "\x1b[1;33mcreate\x1b[0m" in text
    assert "\x1b[1;36mapp.web\x1b[0m" in text


def test_terminal_formatter_colours_configuration():
    out = io.StringIO()
    transport = apply_transport(
        [proto_event("create", "success", "app.web", SAVED_RECORD)],
        encoded(WEB_TOKENS),
    )

    apply_through(transport, xcl.prettylog.handler(out, formatter=xcl.highlight.TERMINAL))

    assert out.getvalue().endswith(
        '  \x1b[1;35mapp\x1b[0m \x1b[32m"web"\x1b[0m {\n'
        '    \x1b[34mimage\x1b[0m = \x1b[33m"nginx"\x1b[0m\n'
        "  }\n"
    )


def test_for_stream_chooses_plain_for_non_terminal(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(event(resource_id="app.web"))

    assert out.getvalue() == "3:04PM INFO create start source=core operation=create phase=start resource=app.web\n"


def test_for_stream_chooses_terminal_for_terminal(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = TerminalStringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(event(resource_id="app.web"))

    assert "\x1b[1;35mcore\x1b[0m" in out.getvalue()


def test_for_stream_chooses_plain_for_terminal_with_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    out = TerminalStringIO()
    on_event = xcl.prettylog.handler(out)

    on_event(event(resource_id="app.web"))

    assert "\x1b" not in out.getvalue()


def test_logger_defaults_to_plain():
    logger, collect = collecting_logger("defaults_to_plain")
    on_event = xcl.prettylog.handler(logger=logger)

    on_event(event(resource_id="app.web"))

    assert len(collect.records) == 1
    assert "\x1b" not in collect.records[0].getMessage()


def test_logger_with_terminal_formatter_is_coloured():
    logger, collect = collecting_logger("terminal_formatter")
    on_event = xcl.prettylog.handler(logger=logger, formatter=xcl.highlight.TERMINAL)

    on_event(event(resource_id="app.web"))

    assert "\x1b[1;35mcore\x1b[0m" in collect.records[0].getMessage()


# -- through a logger ----------------------------------------------------------


def test_logger_record_message_is_line_and_block():
    logger, collect = collecting_logger("line_and_block")
    transport = apply_transport(
        [proto_event("create", "success", "app.web", SAVED_RECORD)],
        encoded(WEB_TOKENS),
    )

    apply_through(transport, xcl.prettylog.handler(logger=logger))

    assert len(collect.records) == 1
    assert collect.records[0].getMessage() == (
        "3:04PM INFO create success source=core operation=create phase=success resource=app.web type=app\n"
        '  app "web" {\n'
        '    image = "nginx"\n'
        "  }"
    )


def test_logger_record_message_matches_stream_text():
    out = io.StringIO()
    apply_through(
        apply_transport([proto_event("create", "success", "app.web", SAVED_RECORD)], encoded(WEB_TOKENS)),
        xcl.prettylog.handler(out),
    )
    logger, collect = collecting_logger("matches_stream")
    apply_through(
        apply_transport([proto_event("create", "success", "app.web", SAVED_RECORD)], encoded(WEB_TOKENS)),
        xcl.prettylog.handler(logger=logger),
    )

    assert collect.records[0].getMessage() == out.getvalue()[:-1]


def test_logger_record_level_and_time_are_events():
    logger, collect = collecting_logger("level_and_time")
    on_event = xcl.prettylog.handler(logger=logger)

    on_event(event(resource_id="app.web"))
    on_event(parse_error_event())

    assert [record.levelno for record in collect.records] == [logging.INFO, logging.ERROR]
    assert collect.records[0].created == EVENT_TIME.timestamp()
    assert collect.records[1].created == EVENT_TIME.timestamp()


def test_logger_record_carries_bridge_fields():
    logger, collect = collecting_logger("bridge_fields")
    on_event = xcl.prettylog.handler(logger=logger)
    sent = event(resource_type="app", resource_id="app.web", file="main.hcl", meta={"attempt": 2})

    on_event(sent)

    record = collect.records[0]
    assert record.source == "core"
    assert record.operation == "create"
    assert record.phase == "start"
    assert record.resource == "app.web"
    assert record.type == "app"
    assert record.file == "main.hcl"
    assert record.attempt == 2
    assert record.xcl_event is sent


def test_logger_record_carries_error_field():
    logger, collect = collecting_logger("error_field")
    on_event = xcl.prettylog.handler(logger=logger)
    sent = parse_error_event()

    on_event(sent)

    assert collect.records[0].error is sent.error


def test_logger_report_is_in_the_error_record():
    logger, collect = collecting_logger("report_record")
    on_event = xcl.prettylog.handler(logger=logger)

    on_event(parse_error_event())

    assert len(collect.records) == 1
    assert collect.records[0].getMessage() == (PARSE_ERROR + REPORT)[:-1]


def test_logger_warning_is_its_own_record():
    logger, collect = collecting_logger("warning_record")
    on_event = xcl.prettylog.handler(logger=logger)

    on_event(web_create_success(SAVED_RECORD))

    assert len(collect.records) == 2
    assert collect.records[0].levelno == logging.INFO
    assert collect.records[0].getMessage() == WEB_CREATE_SUCCESS[:-1]
    assert collect.records[1].levelno == logging.WARNING
    assert collect.records[1].getMessage() == (
        '3:04PM WARN unable to show configuration resource=app.web error="the event was not delivered by a configuration"'
    )


def test_logger_guidance_is_its_own_record():
    logger, collect = collecting_logger("guidance_record")
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web"),
            proto_event("create", "success", "app.api"),
        ]
    )

    apply_through(transport, xcl.prettylog.handler(logger=logger), event_data=xcl.EventDataLevel.NONE)

    assert [record.getMessage() for record in collect.records] == [
        WEB_CREATE_SUCCESS[:-1],
        GUIDANCE[:-1],
        API_CREATE_SUCCESS[:-1],
    ]
    assert collect.records[1].levelno == logging.INFO


def test_logger_level_filters_records():
    logger, collect = collecting_logger("level_filters", level=logging.WARNING)
    on_event = xcl.prettylog.handler(logger=logger)

    on_event(event(resource_id="app.web"))
    on_event(parse_error_event())

    assert [record.levelno for record in collect.records] == [logging.ERROR]


def test_logger_above_info_renders_and_warns_nothing_for_creation():
    logger, collect = collecting_logger("above_info_no_render", level=logging.WARNING)
    transport = apply_transport(
        [proto_event("create", "success", "app.web", SAVED_RECORD)],
        core_pb2.Error(code="unregistered_type", message="app is not registered"),
    )

    apply_through(transport, xcl.prettylog.handler(logger=logger))

    assert "EncodeSavedEntity" not in transport.methods_called()
    assert collect.records == []


def test_logger_above_info_still_writes_error_event():
    logger, collect = collecting_logger("above_info_error", level=logging.WARNING)
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web", SAVED_RECORD),
            proto_event("validate", "error", "widget.x", error=core_pb2.Error(code="config", message="unsupported block")),
        ],
        core_pb2.Error(code="unregistered_type", message="app is not registered"),
    )

    apply_through(transport, xcl.prettylog.handler(logger=logger))

    assert len(collect.records) == 1
    assert collect.records[0].levelno == logging.ERROR
    assert collect.records[0].getMessage() == (
        "3:04PM ERRO validate error source=core operation=validate phase=error resource=widget.x type=app "
        'error="unsupported block"'
    )


# -- robustness ------------------------------------------------------------------


def test_failing_stream_does_not_raise():
    on_event = xcl.prettylog.handler(FailingStream())  # type: ignore[arg-type]

    on_event(event(resource_id="app.web"))


def test_failing_stream_does_not_stop_the_operation():
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web", SAVED_RECORD),
            proto_event("apply", "success"),
        ],
        encoded(WEB_TOKENS),
    )

    apply_through(transport, xcl.prettylog.handler(FailingStream()))  # type: ignore[arg-type]

    assert transport.methods_called().count("Poll") == 3


def test_handler_exception_inside_does_not_raise():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)
    sent = web_create_success(SAVED_RECORD)
    sent._config = OddConfig(RuntimeError("something odd"))

    on_event(sent)

    assert out.getvalue() == (
        WEB_CREATE_SUCCESS + '3:04PM WARN unable to show configuration resource=app.web error="something odd"\n'
    )


def test_render_failure_without_message_names_its_type():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)
    sent = web_create_success(SAVED_RECORD)
    sent._config = OddConfig(KeyError())

    on_event(sent)

    assert out.getvalue() == WEB_CREATE_SUCCESS + "3:04PM WARN unable to show configuration resource=app.web error=KeyError\n"


def test_handler_works_for_aio_config():
    out = io.StringIO()
    transport = apply_transport(
        [
            proto_event("create", "success", "app.web", SAVED_RECORD),
            proto_event("create", "success", "app.api", OTHER_RECORD),
            proto_event("apply", "success"),
        ],
        [encoded(WEB_TOKENS), encoded(API_TOKENS)],
    )

    async def run() -> None:
        config = xcl.aio.Config(
            on_event=xcl.prettylog.handler(out),
            event_data=xcl.EventDataLevel.PROCESSED,
            client=Client(transport),
        )
        try:
            await config.apply("main.hcl")
        finally:
            await config.close()

    asyncio.run(run())

    assert out.getvalue() == WEB_CREATE_SUCCESS + WEB_BLOCK + API_CREATE_SUCCESS + API_BLOCK + APPLY_SUCCESS


def test_one_handler_serves_two_configurations():
    out = io.StringIO()
    on_event = xcl.prettylog.handler(out)

    apply_through(
        apply_transport([proto_event("create", "success", "app.web", SAVED_RECORD)], encoded(WEB_TOKENS)),
        on_event,
    )
    apply_through(
        apply_transport([proto_event("create", "success", "app.api", OTHER_RECORD)], encoded(API_TOKENS)),
        on_event,
    )

    assert out.getvalue() == WEB_CREATE_SUCCESS + WEB_BLOCK + API_CREATE_SUCCESS + API_BLOCK
