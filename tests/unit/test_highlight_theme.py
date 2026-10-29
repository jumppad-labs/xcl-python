"""Themes: resolution through a kind's category, the default theme, extension and validation."""

import pytest

import xcl
from xcl.highlight import DEFAULT_THEME, Kind, Style, style_for, validate


def test_style_for_kind_own_style():
    theme = {Kind.COMMENT: "italic", Kind.LINE_COMMENT: "bold"}

    assert style_for(theme, Kind.LINE_COMMENT) == Style(bold=True)


def test_style_for_falls_back_to_category():
    theme = {Kind.COMMENT: "italic"}

    assert style_for(theme, Kind.LINE_COMMENT) == Style(italic=True)


def test_style_for_falls_back_to_text():
    theme = {Kind.TEXT: "#eeeeee"}

    assert style_for(theme, Kind.ATTRIBUTE) == Style(foreground="#eeeeee")


def test_style_for_empty_style_falls_back_to_category():
    theme = {Kind.COMMENT: "italic", Kind.LINE_COMMENT: ""}

    assert style_for(theme, Kind.LINE_COMMENT) == Style(italic=True)


def test_style_for_unknown_kind_uses_category_style():
    assert style_for(DEFAULT_THEME, 1199) == Style(italic=True, foreground="bright-black")


def test_comment_style_covers_line_hash_and_block_comments():
    theme = DEFAULT_THEME | {Kind.COMMENT: "#6a9955"}

    assert style_for(theme, Kind.LINE_COMMENT) == Style(foreground="#6a9955")
    assert style_for(theme, Kind.HASH_COMMENT) == Style(foreground="#6a9955")
    assert style_for(theme, Kind.BLOCK_COMMENT) == Style(foreground="#6a9955")


def test_line_comment_style_overrides_only_line_comments():
    theme = DEFAULT_THEME | {Kind.COMMENT: "#6a9955", Kind.LINE_COMMENT: "bold #ff0000"}

    assert style_for(theme, Kind.LINE_COMMENT) == Style(bold=True, foreground="#ff0000")
    assert style_for(theme, Kind.HASH_COMMENT) == Style(foreground="#6a9955")
    assert style_for(theme, Kind.BLOCK_COMMENT) == Style(foreground="#6a9955")


def test_extension_keeps_unmentioned_default_styles():
    theme = DEFAULT_THEME | {Kind.ATTRIBUTE: "#ff8800"}

    assert style_for(theme, Kind.ATTRIBUTE) == Style(foreground="#ff8800")
    assert style_for(theme, Kind.STRING) == Style(foreground="yellow")
    assert style_for(theme, Kind.BLOCK_TYPE) == Style(bold=True, foreground="magenta")


def test_default_theme_matches_go_default_theme():
    assert dict(DEFAULT_THEME) == {
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


def test_default_theme_cannot_be_changed_in_place():
    with pytest.raises(TypeError):
        DEFAULT_THEME[Kind.ATTRIBUTE] = "#ff8800"  # type: ignore[index]

    assert DEFAULT_THEME[Kind.ATTRIBUTE] == "blue"


def test_extending_default_theme_gives_new_theme():
    theme = DEFAULT_THEME | {Kind.ATTRIBUTE: "#ff8800"}

    assert isinstance(theme, dict)
    assert theme is not DEFAULT_THEME
    assert theme[Kind.ATTRIBUTE] == "#ff8800"
    assert DEFAULT_THEME[Kind.ATTRIBUTE] == "blue"


def test_validate_default_theme_reports_nothing():
    assert validate(DEFAULT_THEME) is None


def test_validate_unknown_word_raises_invalid_style_error():
    theme = DEFAULT_THEME | {Kind.ATTRIBUTE: "bold sparkly"}

    with pytest.raises(xcl.InvalidStyleError) as caught:
        validate(theme)

    assert caught.value.words == ((Kind.ATTRIBUTE, "bold sparkly", "sparkly"),)
    assert str(caught.value) == 'style "bold sparkly" for Attribute: unknown word "sparkly"'
    assert caught.value.code == "invalid_style"


def test_validate_names_every_unknown_word_in_kind_order():
    theme = {Kind.STRING: "purple", Kind.ATTRIBUTE: "bold sparkly glitter"}

    with pytest.raises(xcl.InvalidStyleError) as caught:
        validate(theme)

    assert caught.value.words == (
        (Kind.ATTRIBUTE, "bold sparkly glitter", "sparkly"),
        (Kind.ATTRIBUTE, "bold sparkly glitter", "glitter"),
        (Kind.STRING, "purple", "purple"),
    )
    assert str(caught.value) == (
        'style "bold sparkly glitter" for Attribute: unknown word "sparkly"\n'
        'style "bold sparkly glitter" for Attribute: unknown word "glitter"\n'
        'style "purple" for String: unknown word "purple"'
    )


def test_validate_names_go_kind_name_for_two_word_kind():
    with pytest.raises(xcl.InvalidStyleError, match='for LineComment: unknown word "faint"'):
        validate({Kind.LINE_COMMENT: "faint"})


def test_invalid_style_error_is_an_xcl_error():
    assert issubclass(xcl.InvalidStyleError, xcl.Error)


def test_style_for_ignores_unknown_word():
    theme = DEFAULT_THEME | {Kind.ATTRIBUTE: "bold sparkly"}

    assert style_for(theme, Kind.ATTRIBUTE) == Style(bold=True)
