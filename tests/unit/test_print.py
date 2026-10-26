"""Printing an error's report in one call, with hand-built reports."""

import io
import sys

import pytest

import xcl
from xcl.highlight import DEFAULT_THEME, PLAIN, TERMINAL, Kind, Token

SHORT_DETAIL = 'Blocks of type "timeout" are not expected here.'

LONG_DETAIL = (
    'Blocks of type "timeout" are not expected here. Did you mean to define an argument called "timeout" '
    "instead, as an attribute with an equals sign?"
)

LONG_SUMMARY = ": " + "a summary that goes on and on " * 4

LONG_SOURCE = 'image = "' + "x" * 100 + '"'


def report_error(detail: str) -> xcl.ConfigError:
    """A config error whose report has a summary, a location, one source line and ``detail``."""
    return xcl.ConfigError(
        "main.xcl:7,3-10: Unsupported block type",
        tokens=[
            Token(Kind.ERROR, "Error"),
            Token(Kind.SUMMARY, ": Unsupported block type"),
            Token(Kind.TEXT, "\n\n"),
            Token(Kind.LOCATION, "  on main.xcl line 7, in sync_app.api, field timeout[0]:"),
            Token(Kind.TEXT, "\n"),
            Token(Kind.GUTTER, "     7 | "),
            Token(Kind.TEXT, "  "),
            Token(Kind.ERROR, "timeout"),
            Token(Kind.TEXT, " {\n\n"),
            Token(Kind.DETAIL, detail),
            Token(Kind.TEXT, "\n"),
        ],
    )


def detail_lines(printed: str) -> list[str]:
    """The lines of a printed report from its detail on, without the trailing line break."""
    start = printed.index("Blocks of type")
    return printed[start:].rstrip("\n").split("\n")


def test_plain_report_is_the_joined_text_when_detail_is_short():
    err = report_error(SHORT_DETAIL)
    out = io.StringIO()

    xcl.print_error(err, file=out)

    assert out.getvalue() == (
        "Error: Unsupported block type\n"
        "\n"
        "  on main.xcl line 7, in sync_app.api, field timeout[0]:\n"
        "     7 |   timeout {\n"
        "\n"
        'Blocks of type "timeout" are not expected here.\n'
    )


def test_format_error_equals_what_print_error_writes():
    err = report_error(LONG_DETAIL)
    out = io.StringIO()

    xcl.print_error(err, file=out)

    assert xcl.format_error(err) == out.getvalue()


def test_long_detail_wrapped_at_80_by_default():
    out = io.StringIO()

    xcl.print_error(report_error(LONG_DETAIL), file=out)

    lines = detail_lines(out.getvalue())
    assert lines == [
        'Blocks of type "timeout" are not expected here. Did you mean to define an',
        'argument called "timeout" instead, as an attribute with an equals sign?',
    ]
    assert all(len(line) <= 80 for line in lines)


def test_long_detail_wrapped_at_40():
    out = io.StringIO()

    xcl.print_error(report_error(LONG_DETAIL), file=out, width=40)

    lines = detail_lines(out.getvalue())
    assert lines == [
        'Blocks of type "timeout" are not',
        "expected here. Did you mean to define an",
        'argument called "timeout" instead, as an',
        "attribute with an equals sign?",
    ]
    assert all(len(line) <= 40 for line in lines)


def test_long_detail_on_one_line_at_width_zero():
    out = io.StringIO()

    xcl.print_error(report_error(LONG_DETAIL), file=out, width=0)

    assert detail_lines(out.getvalue()) == [LONG_DETAIL]


def test_long_detail_on_one_line_at_width_none():
    out = io.StringIO()

    xcl.print_error(report_error(LONG_DETAIL), file=out, width=None)

    assert detail_lines(out.getvalue()) == [LONG_DETAIL]


def test_other_exception_prints_its_message():
    out = io.StringIO()

    xcl.print_error(ValueError("boom"), file=out)

    assert out.getvalue() == "boom\n"


def test_other_exception_formats_as_its_message():
    assert xcl.format_error(ValueError("boom")) == "boom\n"


def test_xcl_error_without_report_prints_its_message():
    out = io.StringIO()

    xcl.print_error(xcl.NotFoundError('no entity found at address "app.nope"'), file=out)

    assert out.getvalue() == 'no entity found at address "app.nope"\n'


def test_print_error_without_file_writes_to_stderr(capsys):
    xcl.print_error(report_error(SHORT_DETAIL))

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Error: Unsupported block type\n")
    assert captured.err.endswith('Blocks of type "timeout" are not expected here.\n')


def test_print_error_without_file_uses_stderr_at_call_time(monkeypatch):
    replaced = io.StringIO()
    monkeypatch.setattr(sys, "stderr", replaced)

    xcl.print_error(ValueError("boom"))

    assert replaced.getvalue() == "boom\n"


class RecordingFormatter:
    """A formatter of the caller's own that records every call it gets."""

    def __init__(self):
        self.calls = []

    def format(self, out, theme, tokens):
        self.calls.append((out, theme, list(tokens)))
        out.write("recorded\n")


def test_user_formatter_called_once_with_whole_report_and_stream():
    err = report_error(SHORT_DETAIL)
    formatter = RecordingFormatter()
    out = io.StringIO()

    xcl.print_error(err, file=out, formatter=formatter)

    assert len(formatter.calls) == 1
    stream, theme, tokens = formatter.calls[0]
    assert stream is out
    assert theme is DEFAULT_THEME
    assert tokens == err.tokens
    assert out.getvalue() == "recorded\n"


def test_terminal_formatter_writes_colour():
    out = io.StringIO()

    xcl.print_error(report_error(SHORT_DETAIL), file=out, formatter=TERMINAL)

    assert "\x1b[" in out.getvalue()


def test_plain_formatter_writes_no_colour():
    out = io.StringIO()

    xcl.print_error(report_error(SHORT_DETAIL), file=out, formatter=PLAIN)

    assert "\x1b[" not in out.getvalue()


def test_long_summary_not_wrapped():
    err = xcl.ConfigError(
        "main.xcl:1,1-2: long",
        tokens=[
            Token(Kind.ERROR, "Error"),
            Token(Kind.SUMMARY, LONG_SUMMARY),
            Token(Kind.TEXT, "\n"),
        ],
    )

    printed = xcl.format_error(err, width=40)

    assert printed == "Error" + LONG_SUMMARY + "\n"


def test_long_source_line_not_wrapped():
    err = xcl.ConfigError(
        "main.xcl:1,1-2: long",
        tokens=[
            Token(Kind.GUTTER, "     1 | "),
            Token(Kind.ATTRIBUTE, LONG_SOURCE),
            Token(Kind.TEXT, "\n"),
        ],
    )

    printed = xcl.format_error(err, width=40)

    assert printed == "     1 | " + LONG_SOURCE + "\n"


# -- change summaries ---------------------------------------------------------

DIFF_TOKENS = (
    Token(Kind.SUMMARY, "Diff: 1 to create."),
    Token(Kind.TEXT, "\n\n"),
    Token(Kind.INSERTED, '+ resource "recording" "one"'),
    Token(Kind.TEXT, "\n"),
)


def labelled_diff() -> xcl.Diff:
    """A diff as Config.diff returns it, carrying its change summary as labelled text."""
    return xcl.Diff(summary=xcl.Summary(create=1), resources=(), tokens=DIFF_TOKENS)


def test_print_diff_writes_tokens():
    out = io.StringIO()

    xcl.print_diff(labelled_diff(), out)

    assert out.getvalue() == 'Diff: 1 to create.\n\n+ resource "recording" "one"\n'


def test_print_diff_defaults_to_stdout(capsys):
    xcl.print_diff(labelled_diff())

    captured = capsys.readouterr()
    assert captured.out == 'Diff: 1 to create.\n\n+ resource "recording" "one"\n'
    assert captured.err == ""


def test_print_diff_in_terminal_colour():
    out = io.StringIO()

    xcl.print_diff(labelled_diff(), out, formatter=TERMINAL)

    assert '\x1b[32m+ resource "recording" "one"\x1b[0m' in out.getvalue()


def test_print_diff_gives_custom_format_whole_text_in_one_call():
    formatter = RecordingFormatter()
    out = io.StringIO()

    xcl.print_diff(labelled_diff(), out, formatter=formatter)

    assert len(formatter.calls) == 1
    stream, theme, tokens = formatter.calls[0]
    assert stream is out
    assert theme is DEFAULT_THEME
    assert tokens == list(DIFF_TOKENS)
    assert out.getvalue() == "recorded\n"


def test_print_diff_without_tokens_raises():
    diff = xcl.Diff(summary=xcl.Summary(create=1), resources=())
    out = io.StringIO()

    with pytest.raises(ValueError) as raised:
        xcl.print_diff(diff, out)

    assert str(raised.value) == "this diff has no labelled text to print: only a diff returned by Config.diff carries it"
    assert out.getvalue() == ""
