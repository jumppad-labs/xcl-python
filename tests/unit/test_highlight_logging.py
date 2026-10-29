"""A logged xcl error's report written in a chosen format by xcl.highlight.LogFormatter."""

import io
import logging
import re

import xcl
from xcl.highlight import TERMINAL, Kind, LogFormatter, Token

ANSI = re.compile(r"\x1b\[[0-9;]*m")

PLAIN_REPORT = 'Error: Unsupported block type\n\nBlocks of type "timeout" are not expected here.'


def config_error() -> xcl.ConfigError:
    """A configuration error carrying a report with an error summary and a detail."""
    return xcl.ConfigError(
        "main.xcl:7,3-10: Unsupported block type",
        tokens=[
            Token(Kind.ERROR, "Error"),
            Token(Kind.SUMMARY, ": Unsupported block type"),
            Token(Kind.TEXT, "\n\n"),
            Token(Kind.DETAIL, 'Blocks of type "timeout" are not expected here.'),
            Token(Kind.TEXT, "\n"),
        ],
    )


def log_with(formatter: logging.Formatter, err: BaseException, name: str) -> str:
    """What a handler using ``formatter`` writes for ``err`` logged with its traceback."""
    logger = logging.getLogger("test_highlight_logging." + name)
    logger.handlers.clear()
    logger.propagate = False
    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    try:
        raise err
    except BaseException:
        logger.exception("apply failed")
    return out.getvalue()


def test_log_formatter_writes_coloured_report():
    written = log_with(LogFormatter(formatter=TERMINAL), config_error(), "coloured")

    assert "\x1b[1;31mError\x1b[0m\x1b[1m: Unsupported block type\x1b[0m" in written
    assert ANSI.sub("", written).endswith(PLAIN_REPORT + "\n")


def test_log_formatter_writes_report_once():
    written = log_with(LogFormatter(formatter=TERMINAL), config_error(), "once")

    assert ANSI.sub("", written).count("Error: Unsupported block type") == 1
    assert ANSI.sub("", written).count("Blocks of type") == 1


def test_log_formatter_keeps_traceback():
    written = log_with(LogFormatter(formatter=TERMINAL), config_error(), "traceback")

    traceback_at = written.index("Traceback (most recent call last)")
    exception_at = written.index("xcl._errors.ConfigError: main.xcl:7,3-10: Unsupported block type")
    report_at = written.index("\x1b[1;31mError")
    assert traceback_at < exception_at < report_at


def test_log_formatter_plain_by_default():
    written = log_with(LogFormatter(), config_error(), "plain")

    assert "\x1b[" not in written
    assert written.endswith(PLAIN_REPORT + "\n")
    assert written.count("Blocks of type") == 1


def test_log_formatter_keeps_user_notes():
    err = config_error()
    err.add_note("while deploying the staging stack")

    written = log_with(LogFormatter(formatter=TERMINAL), err, "user_notes")

    assert "while deploying the staging stack\n" in written
    assert ANSI.sub("", written).count("Blocks of type") == 1


def test_log_formatter_other_exception_like_standard():
    written = log_with(LogFormatter(formatter=TERMINAL), ValueError("boom"), "other")
    standard = log_with(logging.Formatter(), ValueError("boom"), "standard")

    assert written.replace("test_highlight_logging.other", "") == standard.replace("test_highlight_logging.standard", "")
    assert written.startswith("apply failed\nTraceback (most recent call last)")
    assert written.endswith("ValueError: boom\n")


def test_log_formatter_xcl_error_without_report_like_standard():
    err = xcl.NotFoundError("no entity at app.web")

    written = log_with(LogFormatter(formatter=TERMINAL), err, "no_report")

    assert "\x1b[" not in written
    assert written.endswith("xcl._errors.NotFoundError: no entity at app.web\n")


def test_log_formatter_passes_fmt():
    written = log_with(LogFormatter("%(levelname)s: %(message)s"), config_error(), "fmt")

    assert written.startswith("ERROR: apply failed\nTraceback")


def test_log_formatter_passes_style():
    written = log_with(LogFormatter("{levelname} | {message}", style="{"), config_error(), "style")

    assert written.startswith("ERROR | apply failed\n")


def test_log_formatter_wraps_detail_at_width():
    err = xcl.ConfigError(
        "main.xcl:7,3-10: Unsupported block type",
        tokens=[
            Token(Kind.SUMMARY, "Error: Unsupported block type"),
            Token(Kind.TEXT, "\n\n"),
            Token(Kind.DETAIL, "one two three four five six seven eight nine ten"),
            Token(Kind.TEXT, "\n"),
        ],
    )

    written = log_with(LogFormatter(width=20), err, "width")

    assert written.endswith("one two three four\nfive six seven eight\nnine ten\n")
