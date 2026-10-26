"""Wrapping a report's detail to a width, exactly as Go's printing wraps it.

Go wraps detail with ``github.com/mitchellh/go-wordwrap`` v1.0.1
``WrapString``, and this is a port of that function, so a report printed
from Python is byte for byte the one Go prints. Python's ``textwrap`` is not
used: it collapses runs of spaces and breaks long words differently.
"""

from __future__ import annotations

# the characters Go's unicode.IsSpace reports as space: the Unicode
# White_Space property. Python's str.isspace differs (it counts U+001C to
# U+001F), so the set is spelled out
_SPACES = frozenset(
    "\t\n\v\f\r \u0085         "
    "        　"
)

# a no-break space is a space to Go, but go-wordwrap never breaks at one
_NBSP = " "


def wrap_detail(text: str, width: int | None) -> str:
    """``text`` wrapped at ``width`` columns between words, as Go's ``report.Wrap`` wraps it.

    A width of ``None``, ``0`` or less leaves the text unchanged. Lines break
    only at spaces, never at a no-break space; a word longer than the width
    is left whole on a line of its own; existing line breaks are kept.
    Widths are counted in code points, as Go counts runes.
    """
    if width is None or width <= 0:
        return text

    out: list[str] = []
    current = 0
    word: list[str] = []
    space: list[str] = []

    for char in text:
        if char == "\n":
            if not word:
                if current + len(space) > width:
                    current = 0
                else:
                    current += len(space)
                    out.extend(space)
                space = []
            else:
                current += len(space) + len(word)
                out.extend(space)
                space = []
                out.extend(word)
                word = []
            out.append(char)
            current = 0
        elif char in _SPACES and char != _NBSP:
            if not space or word:
                current += len(space) + len(word)
                out.extend(space)
                space = []
                out.extend(word)
                word = []
            space.append(char)
        else:
            word.append(char)
            if current + len(word) + len(space) > width and len(word) < width:
                out.append("\n")
                current = 0
                space = []

    if not word:
        if current + len(space) <= width:
            out.extend(space)
    else:
        out.extend(space)
        out.extend(word)

    return "".join(out)
