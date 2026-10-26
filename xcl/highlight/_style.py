"""Style strings, the same words in every language, and the fixed colour palette."""

from __future__ import annotations

import dataclasses

# the 16 named colours, each with the SGR foreground code a terminal shows it
# with and the hex colour it is written as in HTML, SVG and CSS: a fixed
# palette, the same in every language, since the terminal's bright-red has no
# CSS name
_NAMED_COLOURS: dict[str, tuple[int, str]] = {
    "black": (30, "#000000"),
    "red": (31, "#cd3131"),
    "green": (32, "#0dbc79"),
    "yellow": (33, "#e5e510"),
    "blue": (34, "#2472c8"),
    "magenta": (35, "#bc3fbc"),
    "cyan": (36, "#11a8cd"),
    "white": (37, "#e5e5e5"),
    "bright-black": (90, "#666666"),
    "bright-red": (91, "#f14c4c"),
    "bright-green": (92, "#23d18b"),
    "bright-yellow": (93, "#f5f543"),
    "bright-blue": (94, "#3b8eea"),
    "bright-magenta": (95, "#d670d6"),
    "bright-cyan": (96, "#29b8db"),
    "bright-white": (97, "#ffffff"),
}

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


@dataclasses.dataclass(frozen=True)
class Style:
    """How a kind of text looks, parsed from a style string.

    ``foreground`` is ``""``, a named colour such as ``"bright-red"``, or a
    24-bit colour written ``"#rrggbb"`` in lower case. ``background`` is
    ``""`` or ``"#rrggbb"``.
    """

    bold: bool = False
    italic: bool = False
    underline: bool = False
    dim: bool = False
    foreground: str = ""
    background: str = ""

    def is_zero(self) -> bool:
        """Whether the style sets nothing, so text written with it looks as it would unstyled."""
        return self == Style()


def _hex_word(word: str) -> str | None:
    """A colour written ``#rrggbb``, in either case, in lower case, or ``None`` when ``word`` is not one."""
    if len(word) != 7 or word[0] != "#" or not all(c in _HEX_DIGITS for c in word[1:]):
        return None
    return word.lower()


def _apply_word(fields: dict[str, object], word: str) -> bool:
    """Set what ``word`` sets in ``fields``, and report whether a style understands the word."""
    if word in ("bold", "italic", "underline", "dim"):
        fields[word] = True
        return True
    if word.startswith("bg:"):
        colour = _hex_word(word[3:])
        if colour is None:
            return False
        fields["background"] = colour
        return True
    if word in _NAMED_COLOURS:
        fields["foreground"] = word
        return True
    colour = _hex_word(word)
    if colour is None:
        return False
    fields["foreground"] = colour
    return True


def parse_style(style: str) -> Style:
    """Read a style string, such as ``"bold #ff8800"``, as Go's ``highlight.ParseStyle`` does.

    The words are separated by spaces, each one of ``bold``, ``italic``,
    ``underline``, ``dim``, a foreground colour written ``#rrggbb`` or as one
    of the named colours black, red, green, yellow, blue, magenta, cyan and
    white and their ``bright-`` forms, or a background colour written
    ``bg:#rrggbb``. A later word for the same thing wins. A word that is none
    of these is skipped: parsing never fails, and :func:`validate` reports
    the words skipped.
    """
    fields: dict[str, object] = {}
    for word in style.split():
        _apply_word(fields, word)
    return Style(**fields)  # type: ignore[arg-type]


def _unknown_words(style: str) -> list[str]:
    """The words of a style string a style does not understand, in order."""
    return [word for word in style.split() if not _apply_word({}, word)]


def hex_colour(colour: str) -> str:
    """A colour as ``"#rrggbb"``: a named colour through the fixed palette, a hex colour as it is, ``""`` for none."""
    named = _NAMED_COLOURS.get(colour)
    if named is not None:
        return named[1]
    return colour


def _rgb(colour: str) -> tuple[int, int, int]:
    """The red, green and blue parts of a colour's hex form."""
    hex_form = hex_colour(colour)
    if len(hex_form) != 7:
        return 0, 0, 0
    return int(hex_form[1:3], 16), int(hex_form[3:5], 16), int(hex_form[5:7], 16)


def _sgr(style: Style) -> str:
    """The SGR parameters of a style, such as ``"1;35"``, or ``""`` for a style that sets nothing.

    The order is bold, dim, italic, underline, then the foreground and the
    background colour: named colours as the terminal's own palette, hex
    colours as 24-bit colour.
    """
    parameters: list[str] = []
    if style.bold:
        parameters.append("1")
    if style.dim:
        parameters.append("2")
    if style.italic:
        parameters.append("3")
    if style.underline:
        parameters.append("4")
    if style.foreground:
        named = _NAMED_COLOURS.get(style.foreground)
        if named is not None:
            parameters.append(str(named[0]))
        else:
            parameters.append(_true_colour("38", style.foreground))
    if style.background:
        named = _NAMED_COLOURS.get(style.background)
        if named is not None:
            parameters.append(str(named[0] + 10))
        else:
            parameters.append(_true_colour("48", style.background))
    return ";".join(parameters)


def _true_colour(prefix: str, colour: str) -> str:
    """The SGR parameters setting a 24-bit colour, prefix 38 for the foreground or 48 for the background."""
    red, green, blue = _rgb(colour)
    return f"{prefix};2;{red};{green};{blue}"
