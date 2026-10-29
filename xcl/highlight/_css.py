"""A stylesheet for the HTML format's classes, generated from a theme as Go's ``highlight.WriteCSS`` writes it."""

from __future__ import annotations

from xcl.highlight._formatters import _css_declarations
from xcl.highlight._kinds import Kind, parent_of
from xcl.highlight._style import Style, parse_style
from xcl.highlight._theme import Theme, _styles


def css(theme: Theme) -> str:
    """A stylesheet styling the classes :data:`HTML` writes as ``theme`` styles their kinds.

    It is identical to the one Go's ``highlight.WriteCSS`` writes for the
    same theme, as a starting point for a website's own styles. Every rule is
    scoped under the ``.xcl`` container: a rule for ``TEXT``'s style on
    ``.xcl`` itself, then one for each kind the theme styles, categories
    before the kinds in them, so a kind's own rule wins over its category's.
    Named colours are written through the fixed palette as hex, and ``dim``
    as opacity. A kind's rule resets what its category's rule sets and its
    own style does not, since a kind's style replaces its category's whole::

        Path("xcl.css").write_text(css(DEFAULT_THEME | {Kind.ATTRIBUTE: "#ff8800"}))
    """
    styles = _styles(theme)
    rules: list[str] = []
    declarations = _css_declarations(parse_style(styles.get(Kind.TEXT, "")))
    if declarations:
        rules.append(".xcl { " + "; ".join(declarations) + "; }\n")
    for kind in Kind:
        written = styles.get(kind, "")
        if kind == Kind.TEXT or not written:
            continue
        reference = styles.get(Kind.TEXT, "")
        parent = parent_of(kind)
        if parent != kind:
            reference = styles.get(parent, "")
        style = parse_style(written)
        declarations = _css_declarations(style) + _css_resets(style, parse_style(reference))
        if not declarations:
            continue
        rules.append(".xcl ." + kind.css_class + " { " + "; ".join(declarations) + "; }\n")
    return "".join(rules)


def _css_resets(style: Style, inherited: Style) -> list[str]:
    """The declarations putting back what ``inherited`` sets and ``style`` does not."""
    resets: list[str] = []
    if inherited.foreground and not style.foreground:
        resets.append("color: inherit")
    if inherited.background and not style.background:
        resets.append("background-color: transparent")
    if inherited.bold and not style.bold:
        resets.append("font-weight: normal")
    if inherited.italic and not style.italic:
        resets.append("font-style: normal")
    if inherited.underline and not style.underline:
        resets.append("text-decoration: none")
    if inherited.dim and not style.dim:
        resets.append("opacity: 1")
    return resets
