"""The built-in formats and the stylesheet, checked byte for byte against xcl's published reference outputs.

The reference files in the xcl checkout's ``highlight/testdata/reference``
are the contract every language's printing is held to: each input's tokens,
formatted with the default theme, give the published output exactly.
"""

import io
import json
from pathlib import Path

import pytest

import xcl_source
from xcl.highlight import DEFAULT_THEME, HTML, HTML_INLINE, PLAIN, SVG, TERMINAL, Kind, Token, css


@pytest.fixture(scope="session")
def reference_dir(xcl_src: Path) -> Path:
    """The reference outputs in the xcl checkout."""
    return xcl_source.require("highlight/testdata/reference")


def load_tokens(reference_dir: Path, name: str) -> list[Token]:
    """The tokens of the reference input ``name``, read from ``<name>.tokens.json``."""
    items = json.loads((reference_dir / (name + ".tokens.json")).read_bytes().decode("utf-8"))
    return [Token(kind=item["kind"], text=item["text"]) for item in items]


def read_reference(reference_dir: Path, file_name: str) -> str:
    """A reference output, read as bytes and decoded as UTF-8, with CRLF line ends turned back into LF.

    The files are committed with LF line ends, but a Windows checkout with
    core.autocrlf on writes them with CRLF.
    """
    return (reference_dir / file_name).read_bytes().decode("utf-8").replace("\r\n", "\n")


def test_report_plain_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "report")
    out = io.StringIO()

    PLAIN.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "report.plain.txt")


def test_report_terminal_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "report")
    out = io.StringIO()

    TERMINAL.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "report.terminal.txt")


def test_report_html_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "report")
    out = io.StringIO()

    HTML.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "report.html")


def test_report_inline_html_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "report")
    out = io.StringIO()

    HTML_INLINE.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "report.inline.html")


def test_report_svg_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "report")
    out = io.StringIO()

    SVG.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "report.svg")


def test_entity_plain_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "entity")
    out = io.StringIO()

    PLAIN.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "entity.plain.txt")


def test_entity_terminal_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "entity")
    out = io.StringIO()

    TERMINAL.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "entity.terminal.txt")


def test_entity_html_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "entity")
    out = io.StringIO()

    HTML.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "entity.html")


def test_entity_inline_html_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "entity")
    out = io.StringIO()

    HTML_INLINE.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "entity.inline.html")


def test_entity_svg_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "entity")
    out = io.StringIO()

    SVG.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "entity.svg")


def test_diff_plain_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "diff")
    out = io.StringIO()

    PLAIN.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "diff.plain.txt")


def test_diff_terminal_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "diff")
    out = io.StringIO()

    TERMINAL.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "diff.terminal.txt")


def test_diff_html_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "diff")
    out = io.StringIO()

    HTML.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "diff.html")


def test_diff_inline_html_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "diff")
    out = io.StringIO()

    HTML_INLINE.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "diff.inline.html")


def test_diff_svg_matches_reference(reference_dir: Path) -> None:
    tokens = load_tokens(reference_dir, "diff")
    out = io.StringIO()

    SVG.format(out, DEFAULT_THEME, tokens)

    assert out.getvalue() == read_reference(reference_dir, "diff.svg")


def test_default_css_matches_reference(reference_dir: Path) -> None:
    assert css(DEFAULT_THEME) == read_reference(reference_dir, "default.css")


def test_classes_match_reference(reference_dir: Path) -> None:
    classes = "xcl\n"
    for kind in Kind:
        if kind == Kind.TEXT:
            continue
        classes += kind.css_class + "\n"

    assert classes == read_reference(reference_dir, "classes.txt")
