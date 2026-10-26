"""xcl's events to standard logging, with hand-built events, as Go's events.SlogHandler writes them."""

import logging
from datetime import datetime, timedelta, timezone

import xcl

EVENT_TIME = datetime(2026, 10, 26, 9, 30, 15, 250000, tzinfo=timezone.utc)


class Collect(logging.Handler):
    """A logging handler that keeps every record it is given."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def collecting_logger(name: str, level: int = logging.DEBUG) -> tuple[logging.Logger, Collect]:
    """A logger of its own, at ``level``, that keeps its records and passes none on."""
    logger = logging.getLogger("test_logbridge." + name)
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False
    collect = Collect()
    logger.addHandler(collect)
    return logger, collect


def log_event(level: str, message: str, **meta) -> xcl.Event:
    return xcl.Event(
        time=EVENT_TIME,
        source="plugin",
        operation="create",
        phase="log",
        resource_type="resource",
        resource_id="resource.recording.one",
        meta={"level": level, "message": message, **meta},
    )


def lifecycle_event(operation: str, phase: str, **fields) -> xcl.Event:
    return xcl.Event(time=EVENT_TIME, source="core", operation=operation, phase=phase, **fields)


def test_debug_log_event_written_at_debug_with_its_message():
    logger, collect = collecting_logger("debug")

    xcl.logging_handler(logger)(log_event("debug", "connecting"))

    assert collect.records[0].levelno == logging.DEBUG
    assert collect.records[0].getMessage() == "connecting"


def test_info_log_event_written_at_info_with_its_message():
    logger, collect = collecting_logger("info")

    xcl.logging_handler(logger)(log_event("info", "connected"))

    assert collect.records[0].levelno == logging.INFO
    assert collect.records[0].getMessage() == "connected"


def test_warn_log_event_written_at_warning_with_its_message():
    logger, collect = collecting_logger("warn")

    xcl.logging_handler(logger)(log_event("warn", "slow response"))

    assert collect.records[0].levelno == logging.WARNING
    assert collect.records[0].getMessage() == "slow response"


def test_error_log_event_written_at_error_with_its_message():
    logger, collect = collecting_logger("error")

    xcl.logging_handler(logger)(log_event("error", "connection refused"))

    assert collect.records[0].levelno == logging.ERROR
    assert collect.records[0].getMessage() == "connection refused"


def test_log_event_with_unknown_level_written_at_info():
    logger, collect = collecting_logger("unknown_level")

    xcl.logging_handler(logger)(log_event("trace", "very detailed"))

    assert collect.records[0].levelno == logging.INFO


def test_lifecycle_start_written_at_info_as_operation_and_phase():
    logger, collect = collecting_logger("start")

    xcl.logging_handler(logger)(lifecycle_event("apply", "start"))

    assert collect.records[0].levelno == logging.INFO
    assert collect.records[0].getMessage() == "apply start"


def test_success_written_at_info_as_operation_and_phase():
    logger, collect = collecting_logger("success")

    xcl.logging_handler(logger)(lifecycle_event("create", "success", resource_id="resource.recording.one"))

    assert collect.records[0].levelno == logging.INFO
    assert collect.records[0].getMessage() == "create success"


def test_error_phase_written_at_error():
    logger, collect = collecting_logger("error_phase")

    xcl.logging_handler(logger)(lifecycle_event("create", "error", error=xcl.ProviderError("the provider failed")))

    assert collect.records[0].levelno == logging.ERROR
    assert collect.records[0].getMessage() == "create error"


def test_blocked_phase_written_at_warning():
    logger, collect = collecting_logger("blocked")

    xcl.logging_handler(logger)(lifecycle_event("create", "blocked", resource_id="resource.recording.two"))

    assert collect.records[0].levelno == logging.WARNING
    assert collect.records[0].getMessage() == "create blocked"


def test_debug_event_not_written_below_logger_level():
    logger, collect = collecting_logger("filtered", level=logging.INFO)

    xcl.logging_handler(logger)(log_event("debug", "connecting"))

    assert collect.records == []


def test_info_event_written_at_logger_level():
    logger, collect = collecting_logger("at_level", level=logging.INFO)

    xcl.logging_handler(logger)(lifecycle_event("apply", "start"))

    assert len(collect.records) == 1


def test_record_carries_resource_and_operation():
    logger, collect = collecting_logger("attributes")

    xcl.logging_handler(logger)(
        lifecycle_event("create", "success", resource_id="resource.recording.one", resource_type="resource", file="/w/main.xcl")
    )

    record = collect.records[0]
    assert record.source == "core"
    assert record.operation == "create"
    assert record.phase == "success"
    assert record.resource == "resource.recording.one"
    assert record.type == "resource"
    assert record.file == "/w/main.xcl"


def test_empty_resource_not_on_record():
    logger, collect = collecting_logger("no_resource")

    xcl.logging_handler(logger)(lifecycle_event("apply", "start"))

    assert not hasattr(collect.records[0], "resource")
    assert not hasattr(collect.records[0], "type")
    assert not hasattr(collect.records[0], "file")


def test_duration_on_record_as_timedelta():
    logger, collect = collecting_logger("duration")

    xcl.logging_handler(logger)(lifecycle_event("apply", "success", duration=timedelta(milliseconds=1500)))

    assert collect.records[0].duration == timedelta(milliseconds=1500)


def test_zero_duration_not_on_record():
    logger, collect = collecting_logger("zero_duration")

    xcl.logging_handler(logger)(lifecycle_event("apply", "start"))

    assert not hasattr(collect.records[0], "duration")


def test_error_on_record_as_xcl_error():
    logger, collect = collecting_logger("error_attribute")
    failure = xcl.ProviderError("the provider failed")

    xcl.logging_handler(logger)(lifecycle_event("create", "error", error=failure))

    assert collect.records[0].error is failure
    assert collect.records[0].exc_info is None


def test_meta_details_on_record():
    logger, collect = collecting_logger("meta")

    xcl.logging_handler(logger)(log_event("info", "connected", host="db.local", attempt=2))

    record = collect.records[0]
    assert record.host == "db.local"
    assert record.attempt == 2


def test_meta_details_follow_go_attributes_in_sorted_order():
    logger, collect = collecting_logger("meta_order")

    xcl.logging_handler(logger)(log_event("info", "connected", zone="b", attempt=2, host="db.local"))

    names = list(vars(collect.records[0]))
    added = names[names.index("source") :]
    assert added == ["source", "operation", "phase", "resource", "type", "attempt", "host", "zone", "xcl_event"]


def test_log_event_level_and_message_not_repeated_as_attributes():
    logger, collect = collecting_logger("no_repeat")

    xcl.logging_handler(logger)(log_event("warn", "slow response"))

    assert not hasattr(collect.records[0], "level")
    assert collect.records[0].msg == "slow response"


def test_reserved_name_detail_skipped_and_kept_on_event():
    logger, collect = collecting_logger("reserved")
    event = log_event("info", "connected", name="db", lineno=7)

    xcl.logging_handler(logger)(event)

    record = collect.records[0]
    assert record.name == logger.name
    assert record.lineno == 0
    assert record.xcl_event.meta["name"] == "db"
    assert record.xcl_event.meta["lineno"] == 7


def test_record_carries_the_event():
    logger, collect = collecting_logger("event")
    event = lifecycle_event("apply", "start")

    xcl.logging_handler(logger)(event)

    assert collect.records[0].xcl_event is event


def test_record_time_is_the_event_time():
    logger, collect = collecting_logger("time")

    xcl.logging_handler(logger)(lifecycle_event("apply", "start"))

    record = collect.records[0]
    assert record.created == EVENT_TIME.timestamp()
    assert record.msecs == 250.0


def test_default_logger_is_named_xcl():
    logger, collect = collecting_logger("unused")
    xcl_logger = logging.getLogger("xcl")
    saved = (list(xcl_logger.handlers), xcl_logger.level, xcl_logger.propagate)
    xcl_logger.handlers.clear()
    xcl_logger.setLevel(logging.DEBUG)
    xcl_logger.propagate = False
    xcl_logger.addHandler(collect)
    try:
        xcl.logging_handler()(lifecycle_event("apply", "start"))
    finally:
        xcl_logger.handlers[:] = saved[0]
        xcl_logger.setLevel(saved[1])
        xcl_logger.propagate = saved[2]

    assert collect.records[0].name == "xcl"
