"""Themes: a style string per kind, resolved through the kind's category and then plain text."""

from __future__ import annotations

import types
from collections.abc import Mapping
from typing import Union, cast

from xcl.highlight._kinds import Kind, parent_of
from xcl.highlight._style import Style, _unknown_words, parse_style

Theme = Union[Mapping[int, str], Mapping[Kind, str]]
"""A theme: a style string, such as ``"bold #ff8800"``, for each kind it styles.

A kind it does not style takes its category's style, and a category it does
not style takes ``TEXT``'s, so a short theme styles everything. A theme is
plain data: a dict literal, :data:`DEFAULT_THEME` extended with ``|``, or
one loaded from a VS Code colour theme.
"""

DEFAULT_THEME: types.MappingProxyType[int, str] = types.MappingProxyType(
    {
        Kind.BLOCK: "bold magenta",
        Kind.LABEL: "green",
        Kind.TYPE_LABEL: "cyan",
        Kind.ATTRIBUTE: "blue",
        Kind.STRING: "yellow",
        Kind.STRING_ESCAPE: "bright-magenta",
        Kind.NUMBER: "bright-magenta",
        Kind.CONSTANT: "bright-magenta",
        Kind.REFERENCE: "cyan",
        Kind.COMMENT: "italic bright-black",
        Kind.INSERTED: "green",
        Kind.DELETED: "red",
        Kind.CHANGED: "yellow",
        Kind.ERROR: "bold red",
        Kind.WARNING: "bold yellow",
        Kind.SUMMARY: "bold",
        Kind.GUTTER: "dim",
    }
)
"""xcl's own look, the same as Go's ``highlight.DefaultTheme``.

It uses only the terminal's 16 named colours, so in a terminal it follows the
user's own palette, and leaves ``TEXT`` unstyled. It cannot be changed in
place; ``DEFAULT_THEME | {Kind.ATTRIBUTE: "#ff8800"}`` gives a new theme
with the default's styles and the given ones in their place.
"""


def style_for(theme: Theme, kind: int) -> Style:
    """How ``kind`` looks in ``theme``: its own style, else its category's, else ``TEXT``'s.

    A style is taken whole, never merged with its category's, and words a
    style does not understand are skipped.
    """
    styles = _styles(theme)
    written = styles.get(kind, "")
    if written:
        return parse_style(written)
    written = styles.get(parent_of(kind), "")
    if written:
        return parse_style(written)
    return parse_style(styles.get(Kind.TEXT, ""))


def validate(theme: Theme) -> None:
    """Check every word of the theme's styles, as Go's ``Theme.Validate`` does.

    It returns nothing for a theme it finds nothing wrong with, and raises
    one :class:`xcl.InvalidStyleError` naming every word a style does not
    understand otherwise, in the order of the kinds and then of the words.
    Printing with a theme that does not validate still works: the words are
    skipped.
    """
    from xcl._errors import InvalidStyleError

    styles = _styles(theme)
    words: list[tuple[int, str, str]] = []
    for kind in sorted(styles):
        written = styles[kind]
        for word in _unknown_words(written):
            words.append((kind, written, word))
    if words:
        raise InvalidStyleError(words)


def _styles(theme: Theme) -> Mapping[int, str]:
    """``theme`` as a mapping read by any kind number: a ``Kind`` is an ``int``, so either form of theme reads the same."""
    return cast(Mapping[int, str], theme)
