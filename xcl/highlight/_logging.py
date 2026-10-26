"""A logging formatter that writes a logged xcl error's report in a chosen format."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Literal, Optional, Union

from xcl.highlight._formatters import PLAIN, Formatter
from xcl.highlight._theme import DEFAULT_THEME, Theme

_ExcInfo = Union[
    tuple[type[BaseException], BaseException, Optional[TracebackType]],
    tuple[None, None, None],
]


class LogFormatter(logging.Formatter):
    """A ``logging.Formatter`` that writes a logged xcl error's report in the format of your choice.

    An exception logged with its traceback (``logger.exception(...)`` or
    ``exc_info=True``) that is an :class:`xcl.Error` carrying a report is
    written as its traceback, without the plain report its exception note
    holds, followed by the report printed with ``formatter``, ``theme`` and
    ``width``, as :func:`xcl.print_error` prints it. Any other exception is
    written exactly as ``logging.Formatter`` writes it. Every other option is
    ``logging.Formatter``'s own, so a coloured console handler is one line::

        handler.setFormatter(xcl.highlight.LogFormatter("%(levelname)s %(message)s", formatter=xcl.highlight.for_stream(sys.stderr)))

    The defaults are plain text, :data:`DEFAULT_THEME` and detail wrapped at
    80 columns.
    """

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: Literal["%", "{", "$"] = "%",
        validate: bool = True,
        *,
        defaults: Mapping[str, Any] | None = None,
        formatter: Formatter = PLAIN,
        theme: Theme = DEFAULT_THEME,
        width: int | None = 80,
    ) -> None:
        super().__init__(fmt, datefmt, style, validate, defaults=defaults)
        self.formatter = formatter
        self.theme = theme
        self.width = width

    def formatException(self, ei: _ExcInfo) -> str:  # noqa: N802 (logging's name)
        """The traceback of ``ei``, then, for an ``xcl.Error`` with a report, the report in the chosen format."""
        from xcl._errors import Error
        from xcl._print import format_error
        from xcl._render import plain_report

        err = ei[1]
        if not isinstance(err, Error) or not err.tokens:
            return super().formatException(ei)

        formatted = traceback.TracebackException(type(err), err, ei[2])
        note = plain_report(err.tokens)
        notes = getattr(formatted, "__notes__", None)
        if notes:
            remaining = [n for n in notes if n != note]
            formatted.__notes__ = remaining or None  # type: ignore[attr-defined]
        text = "".join(formatted.format())
        report = format_error(err, formatter=self.formatter, theme=self.theme, width=self.width)
        return (text + report).rstrip("\n")
