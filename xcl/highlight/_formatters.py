"""The formatter protocol and the built-in formats, each a port of Go's, byte for byte."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TextIO

from xcl.highlight._kinds import Kind, Token, _known, css_class_of, parent_of
from xcl.highlight._style import Style, _sgr, hex_colour
from xcl.highlight._theme import Theme, style_for


class Formatter(Protocol):
    """Turns labelled text into output on a stream: plain text, terminal colour, HTML, SVG or any other format.

    ``format`` is given every token at once, in order, so it can reason
    across them, such as by line or for a whole document, and the theme to
    style them with, which it may ignore. The tokens hold every byte of the
    text, ``TEXT`` tokens included. Any object with this method is accepted
    wherever a built-in format is.
    """

    def format(self, out: TextIO, theme: Theme, tokens: Sequence[Token]) -> None:
        """Write ``tokens`` to ``out`` in this format, styled by ``theme``."""
        ...


class _Plain:
    """Writes the text of the tokens with nothing added, ignoring the theme, as Go's ``highlight.Plain``."""

    def format(self, out: TextIO, theme: Theme, tokens: Sequence[Token]) -> None:
        """Write the tokens' text to ``out``."""
        for token in tokens:
            if token.text:
                out.write(token.text)

    def __repr__(self) -> str:
        return "xcl.highlight.PLAIN"


class _Terminal:
    """Writes the tokens for a terminal in SGR escape codes from the theme, as Go's ``highlight.Terminal``.

    The 16 named colours are the terminal's own palette and hex colours are
    24-bit colour. Text styled with nothing is written with no codes at all.
    A token that spans lines is styled one line at a time, with a reset
    before every line break, so indenting or prefixing a line never bleeds
    colour. It always writes colour: whether to use it is the caller's
    choice, which :func:`for_stream` makes the usual way.
    """

    def format(self, out: TextIO, theme: Theme, tokens: Sequence[Token]) -> None:
        """Write the tokens to ``out`` in terminal colour."""
        for token in tokens:
            parameters = _sgr(style_for(theme, token.kind))
            if not parameters:
                if token.text:
                    out.write(token.text)
                continue
            for i, line in enumerate(token.text.split("\n")):
                if i > 0:
                    out.write("\n")
                if line:
                    out.write("\x1b[" + parameters + "m" + line + "\x1b[0m")

    def __repr__(self) -> str:
        return "xcl.highlight.TERMINAL"


class _HTML:
    """Writes the tokens as one ``<pre class="xcl">`` block with classes, as Go's ``highlight.HTML``.

    Each token that is not ``TEXT`` is in a span carrying its kind's class
    and, when the kind belongs to a category, the category's class first,
    such as ``<span class="xcl-comment xcl-line-comment">``. Every token's
    text is escaped. The theme is ignored: a website styles the classes with
    its own stylesheet, or one :func:`css` generates from a theme.
    """

    def format(self, out: TextIO, theme: Theme, tokens: Sequence[Token]) -> None:
        """Write the tokens to ``out`` as class-marked HTML."""
        out.write('<pre class="xcl">')
        for token in tokens:
            classes = _classes_of(token.kind)
            if not classes:
                _write(out, _escape(token.text))
                continue
            out.write('<span class="' + classes + '">' + _escape(token.text) + "</span>")
        out.write("</pre>")

    def __repr__(self) -> str:
        return "xcl.highlight.HTML"


class _HTMLInline:
    """Writes the same markup as :data:`HTML`, styled from the theme with style attributes, as Go's ``highlight.HTMLInline``.

    It is for places a stylesheet cannot reach, such as an email. A token the
    theme styles with nothing, and every ``TEXT`` token, is written without a
    span; the block itself carries ``TEXT``'s style, when the theme gives it
    one.
    """

    def format(self, out: TextIO, theme: Theme, tokens: Sequence[Token]) -> None:
        """Write the tokens to ``out`` as inline-styled HTML."""
        declarations = _css_declarations(style_for(theme, Kind.TEXT))
        if declarations:
            out.write('<pre style="' + _escape("; ".join(declarations)) + '">')
        else:
            out.write("<pre>")
        for token in tokens:
            declarations = _css_declarations(style_for(theme, token.kind))
            if token.kind == Kind.TEXT or not declarations:
                _write(out, _escape(token.text))
                continue
            out.write('<span style="' + _escape("; ".join(declarations)) + '">' + _escape(token.text) + "</span>")
        out.write("</pre>")

    def __repr__(self) -> str:
        return "xcl.highlight.HTML_INLINE"


# the geometry of SVG output, in user units: a monospace font 10 high, a
# character 6 wide, a line 14 high and a margin of 8 all round
_SVG_MARGIN = 8
_SVG_CHAR_WIDTH = 6
_SVG_LINE_HEIGHT = 14
_SVG_BASELINE = 11


class _SVG:
    """Writes the tokens as a standalone SVG image, as Go's ``highlight.SVG``.

    The image is monospace text, one ``<text xml:space="preserve">`` element
    per line with a ``<tspan>`` for each styled token, its colours and
    attributes from the theme. The view box fits the longest line and every
    line. ``TEXT``'s foreground colours the whole image, and ``TEXT``'s
    background, when the theme gives one, fills it; a token's own background
    is not drawn.
    """

    def format(self, out: TextIO, theme: Theme, tokens: Sequence[Token]) -> None:
        """Write the tokens to ``out`` as an SVG image."""
        lines = _svg_lines(tokens)
        columns = 0
        for line in lines:
            columns = max(columns, sum(len(piece.text) for piece in line))
        width = str(2 * _SVG_MARGIN + _SVG_CHAR_WIDTH * columns)
        height = str(2 * _SVG_MARGIN + _SVG_LINE_HEIGHT * len(lines))

        text = style_for(theme, Kind.TEXT)
        out.write(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '
            + width
            + " "
            + height
            + '" font-family="monospace" font-size="10"'
        )
        if text.foreground:
            out.write(' fill="' + hex_colour(text.foreground) + '"')
        out.write(">\n")
        if text.background:
            out.write('<rect width="' + width + '" height="' + height + '" fill="' + hex_colour(text.background) + '"/>\n')

        for i, line in enumerate(lines):
            y = str(_SVG_MARGIN + _SVG_BASELINE + _SVG_LINE_HEIGHT * i)
            out.write('<text x="' + str(_SVG_MARGIN) + '" y="' + y + '" xml:space="preserve">')
            for piece in line:
                attributes = _svg_attributes(style_for(theme, piece.kind))
                if piece.kind == Kind.TEXT or not attributes:
                    _write(out, _escape(piece.text))
                    continue
                out.write("<tspan" + attributes + ">" + _escape(piece.text) + "</tspan>")
            out.write("</text>\n")
        out.write("</svg>\n")

    def __repr__(self) -> str:
        return "xcl.highlight.SVG"


PLAIN: Formatter = _Plain()
TERMINAL: Formatter = _Terminal()
HTML: Formatter = _HTML()
HTML_INLINE: Formatter = _HTMLInline()
SVG: Formatter = _SVG()


def _write(out: TextIO, text: str) -> None:
    """Write ``text`` unless it is empty, as Go's formatters skip empty writes."""
    if text:
        out.write(text)


def _escape(text: str) -> str:
    """``text`` escaped for HTML and XML, in content and in attributes, as Go escapes it (``'`` as ``&#39;``)."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _classes_of(kind: int) -> str:
    """The classes of a kind's span: its category's class, when it belongs to one, then its own; ``TEXT`` has none."""
    if kind == Kind.TEXT:
        return ""
    own = css_class_of(kind)
    if not own:
        return ""
    parent = parent_of(kind)
    if _known(kind) is None or parent == kind:
        return own
    parent_class = css_class_of(parent)
    if parent_class:
        return parent_class + " " + own
    return own


def _css_declarations(style: Style) -> list[str]:
    """The CSS declarations of a style, in the order colour, background colour, bold, italic, underline and dim."""
    declarations: list[str] = []
    if style.foreground:
        declarations.append("color: " + hex_colour(style.foreground))
    if style.background:
        declarations.append("background-color: " + hex_colour(style.background))
    if style.bold:
        declarations.append("font-weight: bold")
    if style.italic:
        declarations.append("font-style: italic")
    if style.underline:
        declarations.append("text-decoration: underline")
    if style.dim:
        declarations.append("opacity: 0.5")
    return declarations


def _svg_lines(tokens: Sequence[Token]) -> list[list[Token]]:
    """The tokens split into lines, each the pieces of the tokens on it, without the line breaks.

    A final line break ends the last line rather than starting an empty one.
    """
    lines: list[list[Token]] = [[]]
    for token in tokens:
        for i, part in enumerate(token.text.split("\n")):
            if i > 0:
                lines.append([])
            if part:
                lines[-1].append(Token(kind=token.kind, text=part))
    if len(lines) > 1 and not lines[-1]:
        lines.pop()
    return lines


def _svg_attributes(style: Style) -> str:
    """The attributes of a tspan with a style, each with a leading space, in the order fill, bold, italic, underline and dim."""
    attributes = ""
    if style.foreground:
        attributes += ' fill="' + hex_colour(style.foreground) + '"'
    if style.bold:
        attributes += ' font-weight="bold"'
    if style.italic:
        attributes += ' font-style="italic"'
    if style.underline:
        attributes += ' text-decoration="underline"'
    if style.dim:
        attributes += ' opacity="0.5"'
    return attributes
