"""The built-in formats: plain text, terminal colour, HTML, inline-styled HTML and SVG, and the formatter protocol."""

import io
import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Sequence
from typing import TextIO

from xcl.highlight import DEFAULT_THEME, HTML, HTML_INLINE, PLAIN, SVG, TERMINAL, Formatter, Kind, Theme, Token

SGR = re.compile(r"\x1b\[[0-9;]*m")


def render(formatter: Formatter, tokens: Sequence[Token], theme: Theme = DEFAULT_THEME) -> str:
    """The output of ``formatter`` for ``tokens``, written to a ``StringIO``."""
    out = io.StringIO()
    formatter.format(out, theme, tokens)
    return out.getvalue()


class Bracketed:
    """A format written by a user against the formatter protocol: each token's text in brackets."""

    def format(self, out: TextIO, theme: Theme, tokens: Sequence[Token]) -> None:
        for token in tokens:
            out.write("[" + token.text + "]")


def test_plain_writes_text_ignoring_default_theme():
    tokens = [Token(Kind.ATTRIBUTE, "name"), Token(Kind.TEXT, " = "), Token(Kind.STRING, '"x"')]

    assert render(PLAIN, tokens) == 'name = "x"'


def test_plain_writes_text_ignoring_other_theme():
    tokens = [Token(Kind.ATTRIBUTE, "name"), Token(Kind.TEXT, " = "), Token(Kind.STRING, '"x"')]
    theme: Theme = {Kind.ATTRIBUTE: "bold red", Kind.STRING: "bg:#000000 underline"}

    assert render(PLAIN, tokens, theme) == 'name = "x"'


def test_terminal_resets_before_every_newline():
    tokens = [
        Token(Kind.LINE_COMMENT, "# one\n# two"),
        Token(Kind.TEXT, "\n"),
        Token(Kind.ATTRIBUTE, "name"),
    ]

    output = render(TERMINAL, tokens)

    assert output.count("\n") == 2
    assert output.count("\x1b[0m\n") == 2


def test_terminal_without_escape_codes_is_plain_text():
    tokens = [
        Token(Kind.BLOCK_TYPE, "resource"),
        Token(Kind.TEXT, " "),
        Token(Kind.STRING, '"container"'),
        Token(Kind.TEXT, " {\n  "),
        Token(Kind.ATTRIBUTE, "image"),
        Token(Kind.TEXT, " = "),
        Token(Kind.NUMBER, "42"),
        Token(Kind.TEXT, "\n}\n"),
    ]

    assert SGR.sub("", render(TERMINAL, tokens)) == 'resource "container" {\n  image = 42\n}\n'


def test_terminal_colours_multi_line_token_per_line():
    tokens = [Token(Kind.STRING, "first\nsecond")]

    assert render(TERMINAL, tokens) == "\x1b[33mfirst\x1b[0m\n\x1b[33msecond\x1b[0m"


def test_html_escapes_special_characters():
    tokens = [Token(Kind.STRING, "<&\"'>")]

    assert render(HTML, tokens) == '<pre class="xcl"><span class="xcl-string">&lt;&amp;&quot;&#39;&gt;</span></pre>'


def test_html_has_no_style_attribute():
    tokens = [
        Token(Kind.ATTRIBUTE, "name"),
        Token(Kind.TEXT, " = "),
        Token(Kind.STRING, '"x"'),
        Token(Kind.LINE_COMMENT, " // note"),
    ]

    assert "style=" not in render(HTML, tokens)


def test_html_writes_no_span_for_text():
    tokens = [Token(Kind.TEXT, "a b")]

    assert render(HTML, tokens) == '<pre class="xcl">a b</pre>'


def test_html_puts_category_class_first_for_child_kind():
    tokens = [Token(Kind.LINE_COMMENT, "// note")]

    assert render(HTML, tokens) == '<pre class="xcl"><span class="xcl-comment xcl-line-comment">// note</span></pre>'


def test_html_inline_writes_style_attribute():
    tokens = [Token(Kind.ATTRIBUTE, "name")]

    assert render(HTML_INLINE, tokens) == '<pre><span style="color: #2472c8">name</span></pre>'


def test_html_inline_has_no_class_attribute():
    tokens = [
        Token(Kind.ATTRIBUTE, "name"),
        Token(Kind.TEXT, " = "),
        Token(Kind.STRING, '"x"'),
        Token(Kind.LINE_COMMENT, " // note"),
    ]

    assert "class=" not in render(HTML_INLINE, tokens)


def test_svg_parses_as_xml():
    tokens = [Token(Kind.STRING, "<&\"'>"), Token(Kind.TEXT, "\n")]

    root = ElementTree.fromstring(render(SVG, tokens))

    assert root.tag == "{http://www.w3.org/2000/svg}svg"


def test_svg_writes_one_text_element_per_line():
    tokens = [
        Token(Kind.ATTRIBUTE, "first"),
        Token(Kind.TEXT, "\n"),
        Token(Kind.ATTRIBUTE, "second"),
        Token(Kind.TEXT, "\n"),
        Token(Kind.ATTRIBUTE, "third"),
        Token(Kind.TEXT, "\n"),
    ]

    root = ElementTree.fromstring(render(SVG, tokens))

    assert len(root.findall("{http://www.w3.org/2000/svg}text")) == 3


def test_terminal_prints_unknown_kind_in_category_style():
    tokens = [Token(1199, "note")]

    assert render(TERMINAL, tokens) == "\x1b[3;90mnote\x1b[0m"


def test_html_gives_unknown_kind_category_class():
    tokens = [Token(1199, "note")]

    assert render(HTML, tokens) == '<pre class="xcl"><span class="xcl-comment">note</span></pre>'


def test_terminal_ignores_unknown_style_word():
    theme: Theme = DEFAULT_THEME | {Kind.ATTRIBUTE: "bold sparkly"}
    tokens = [Token(Kind.ATTRIBUTE, "name")]

    assert render(TERMINAL, tokens, theme) == "\x1b[1mname\x1b[0m"


def test_html_inline_ignores_unknown_style_word():
    theme: Theme = DEFAULT_THEME | {Kind.ATTRIBUTE: "bold sparkly"}
    tokens = [Token(Kind.ATTRIBUTE, "name")]

    assert render(HTML_INLINE, tokens, theme) == '<pre><span style="font-weight: bold">name</span></pre>'


def test_built_in_format_is_a_formatter():
    tokens = [Token(Kind.ATTRIBUTE, "name"), Token(Kind.TEXT, " = "), Token(Kind.NUMBER, "1")]

    assert render(PLAIN, tokens) == "name = 1"


def test_user_format_is_accepted_as_a_formatter():
    tokens = [Token(Kind.ATTRIBUTE, "name"), Token(Kind.TEXT, " = "), Token(Kind.NUMBER, "1")]

    assert render(Bracketed(), tokens) == "[name][ = ][1]"
