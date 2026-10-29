"""Loading a VS Code colour theme as a theme, converted by the engine."""

from __future__ import annotations

import os

from xcl.highlight._kinds import _known


def load_vscode_theme(source: str | os.PathLike[str] | bytes) -> dict[int, str]:
    """A VS Code colour theme as a theme, as Go's ``highlight.LoadVSCodeTheme`` loads it.

    ``source`` is the theme file's path, or its contents as bytes (JSON with
    comments, as VS Code writes it). The engine matches the theme's
    ``tokenColors`` rules against each kind's TextMate scope, the same scopes
    the xcl VS Code extension gives the same text, so attribute names take
    the theme's colour for properties. Only the kinds the theme styles are
    returned, so extend the default to keep xcl's look for the rest::

        theme = xcl.highlight.DEFAULT_THEME | xcl.highlight.load_vscode_theme("theme.json")

    It needs no configuration: the engine starts on first use, as it does
    when a configuration is created. A theme the engine cannot use raises
    :class:`xcl.InvalidThemeError`, whose ``details["reason"]`` says what was
    wrong and where.
    """
    from xcl._client import default_client
    from xcl._core import core_pb2

    if isinstance(source, bytes):
        data = source
    else:
        with open(source, "rb") as file:
            data = file.read()

    response = default_client().call(0, "ConvertTheme", core_pb2.ConvertThemeRequest(vscode_theme_json=data))
    styles: dict[int, str] = {}
    for number, style in sorted(response.styles.items()):
        known = _known(number)
        styles[known if known is not None else int(number)] = style
    return styles
