"""Printing errors for a person to read, in one call, shaped like the standard library's traceback pair."""

from __future__ import annotations

import sys
from typing import TextIO

from xcl import _errors
from xcl.diff import Diff
from xcl._render import render, wrapped
from xcl.highlight._formatters import PLAIN, Formatter
from xcl.highlight._kinds import Token
from xcl.highlight._theme import DEFAULT_THEME, Theme


def print_error(
    err: BaseException,
    file: TextIO | None = None,
    *,
    formatter: Formatter = PLAIN,
    theme: Theme = DEFAULT_THEME,
    width: int | None = 80,
) -> None:
    """Print ``err`` to ``file`` for a person to read, as Go's ``xcl.PrintError`` prints it.

    It follows :func:`traceback.print_exception`: ``file`` is
    ``sys.stderr`` when not given. An :class:`xcl.Error` holding
    configuration problems prints its report: each problem's severity and
    summary, where it is (the file, the line, and the block and field it is
    in), the numbered lines of source around it with the fault marked, and
    its detail, wrapped at ``width`` columns (80 by default; ``0`` or
    ``None`` never wraps). Any other exception, and an ``xcl.Error`` with no
    report, prints as its message and a line break, as Go prints an error
    holding no configuration problem.

    The output is plain text unless ``formatter`` chooses another format,
    such as :data:`xcl.highlight.TERMINAL`, a format chosen from the stream
    with :func:`xcl.highlight.for_stream`, or one of your own, which is
    given the whole report at once and writes to ``file``::

        try:
            cfg.apply("./config")
        except xcl.Error as err:
            xcl.print_error(err, formatter=xcl.highlight.for_stream(sys.stderr))
            sys.exit(1)
    """
    out = sys.stderr if file is None else file
    tokens = _tokens_of(err)
    if not tokens:
        out.write(str(err) + "\n")
        return
    formatter.format(out, theme, wrapped(tokens, width))


def format_error(
    err: BaseException,
    *,
    formatter: Formatter = PLAIN,
    theme: Theme = DEFAULT_THEME,
    width: int | None = 80,
) -> str:
    """``err`` as :func:`print_error` prints it, as a string, following :func:`traceback.format_exception`.

    The HTML formats return markup already escaped, ready to put into a
    page.
    """
    tokens = _tokens_of(err)
    if not tokens:
        return str(err) + "\n"
    return render(tokens, formatter, theme, width)


def print_diff(
    diff: Diff,
    file: TextIO | None = None,
    *,
    formatter: Formatter = PLAIN,
    theme: Theme = DEFAULT_THEME,
) -> None:
    """Print a change summary to ``file``, in one call, as Go's ``xcl.PrintDiff`` prints it.

    ``file`` is ``sys.stdout`` when not given. The summary is the git-style
    one the engine lays out for the diff (``diff.tokens``), written in the
    format ``formatter`` chooses (plain text by default) and styled by
    ``theme``; the formatter is given the whole labelled text at once::

        changes = cfg.diff("./config")
        xcl.print_diff(changes, formatter=xcl.highlight.for_stream(sys.stdout))

    Raises ``ValueError`` for a diff that carries no labelled text, such as
    one built by hand: only a diff returned by ``Config.diff`` carries it.
    """
    if not diff.tokens:
        raise ValueError("this diff has no labelled text to print: only a diff returned by Config.diff carries it")
    formatter.format(sys.stdout if file is None else file, theme, diff.tokens)


def _tokens_of(err: BaseException) -> list[Token]:
    """The report an error carries, or nothing for an error that is not an ``xcl.Error`` or carries none."""
    if isinstance(err, _errors.Error):
        return err.tokens
    return []
