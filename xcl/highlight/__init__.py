"""Labelled text from the xcl engine, styled by themes and written by formatters.

The engine lexes configuration and lays out reports and change summaries; it
sends the result as labelled text, a list of :class:`Token`, each a piece of
text with its :class:`Kind`, such as an attribute name or a line comment.
Python only formats it:

- a **theme** says how each kind looks, as the same style strings Go uses,
  such as ``"bold #ff8800"``. :data:`DEFAULT_THEME` is xcl's own look, and
  ``DEFAULT_THEME | {Kind.ATTRIBUTE: "#ff8800"}`` extends it. A kind a theme
  does not style takes its category's style, then ``TEXT``'s.
- a **formatter** writes the tokens in a format: plain text, terminal colour,
  HTML, inline-styled HTML or SVG, each identical to Go's, or one of your own.

Colour is always the caller's choice: every default is plain text, and the
package never checks for a terminal on its own.
"""

from xcl.highlight._css import css
from xcl.highlight._formatters import HTML, HTML_INLINE, PLAIN, SVG, TERMINAL, Formatter
from xcl.highlight._kinds import Kind, Token, css_class_of, parent_of
from xcl.highlight._logging import LogFormatter
from xcl.highlight._stream import for_stream
from xcl.highlight._style import Style, hex_colour, parse_style
from xcl.highlight._theme import DEFAULT_THEME, Theme, style_for, validate
from xcl.highlight._vscode import load_vscode_theme

__all__ = [
    "Kind",
    "Token",
    "parent_of",
    "css_class_of",
    "Style",
    "parse_style",
    "hex_colour",
    "Theme",
    "DEFAULT_THEME",
    "style_for",
    "validate",
    "Formatter",
    "PLAIN",
    "TERMINAL",
    "HTML",
    "HTML_INLINE",
    "SVG",
    "css",
    "for_stream",
    "load_vscode_theme",
    "LogFormatter",
]
