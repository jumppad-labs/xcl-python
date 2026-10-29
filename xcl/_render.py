"""Labelled text through a formatter, with a report's detail wrapped: the one print-time step Python takes."""

from __future__ import annotations

import io
from collections.abc import Sequence

from xcl._wrap import wrap_detail
from xcl.highlight._formatters import PLAIN, Formatter
from xcl.highlight._kinds import Kind, Token
from xcl.highlight._theme import DEFAULT_THEME, Theme


def wrapped(tokens: Sequence[Token], width: int | None) -> list[Token]:
    """``tokens`` with each ``DETAIL`` token wrapped at ``width``, as Go's ``PrintError`` wraps them.

    Only detail is wrapped, never source lines. A width of ``None``, ``0`` or
    less leaves every token as it is.
    """
    if width is None or width <= 0:
        return list(tokens)
    return [Token(kind=token.kind, text=wrap_detail(token.text, width)) if token.kind == Kind.DETAIL else token for token in tokens]


def render(tokens: Sequence[Token], formatter: Formatter, theme: Theme, width: int | None) -> str:
    """``tokens``, with detail wrapped at ``width``, as ``formatter`` writes them with ``theme``."""
    out = io.StringIO()
    formatter.format(out, theme, wrapped(tokens, width))
    return out.getvalue()


def plain_report(tokens: Sequence[Token]) -> str:
    """The plain report of ``tokens`` wrapped at 80 columns, without trailing line breaks: an error's note."""
    return render(tokens, PLAIN, DEFAULT_THEME, 80).rstrip("\n")
