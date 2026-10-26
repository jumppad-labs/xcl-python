"""The opt-in colour choice: terminal colour for a terminal, plain text otherwise."""

from __future__ import annotations

import os

from xcl.highlight._formatters import PLAIN, TERMINAL, Formatter


def for_stream(stream: object) -> Formatter:
    """The usual format for writing to ``stream``, as Go's ``highlight.For`` chooses it.

    It is :data:`TERMINAL` when ``stream.isatty()`` is true and the
    ``NO_COLOR`` environment variable is unset or empty (see
    https://no-color.org), and :data:`PLAIN` otherwise, such as for a file, a
    pipe, a ``StringIO`` or a closed stream. The package never decides on its
    own whether to colour output: this is how a caller asks it to make the
    usual choice::

        xcl.print_error(err, formatter=xcl.highlight.for_stream(sys.stderr))
    """
    isatty = getattr(stream, "isatty", None)
    if isatty is None:
        return PLAIN
    try:
        terminal = bool(isatty())
    except (ValueError, OSError):
        return PLAIN
    if not terminal or os.environ.get("NO_COLOR", ""):
        return PLAIN
    return TERMINAL
