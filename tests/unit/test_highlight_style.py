"""Style strings, read as Go's highlight.ParseStyle reads them."""

from xcl.highlight import Style, hex_colour, parse_style
from xcl.highlight._style import _sgr


def test_parse_bold():
    assert parse_style("bold") == Style(bold=True)


def test_parse_italic():
    assert parse_style("italic") == Style(italic=True)


def test_parse_underline():
    assert parse_style("underline") == Style(underline=True)


def test_parse_dim():
    assert parse_style("dim") == Style(dim=True)


def test_parse_hex_foreground():
    assert parse_style("#ff8800") == Style(foreground="#ff8800")


def test_parse_upper_case_hex_is_stored_lower_case():
    assert parse_style("#FF8800") == Style(foreground="#ff8800")


def test_parse_background():
    assert parse_style("bg:#102030") == Style(background="#102030")


def test_parse_named_colour():
    assert parse_style("red") == Style(foreground="red")


def test_parse_bright_named_colour():
    assert parse_style("bright-magenta") == Style(foreground="bright-magenta")


def test_parse_several_words():
    assert parse_style("bold italic #00ff88") == Style(bold=True, italic=True, foreground="#00ff88")


def test_parse_later_colour_wins():
    assert parse_style("red #ff8800 blue") == Style(foreground="blue")


def test_parse_unknown_word_is_skipped():
    assert parse_style("bold sparkly") == Style(bold=True)


def test_parse_short_hex_is_skipped():
    assert parse_style("#f80") == Style()


def test_parse_named_background_is_skipped():
    assert parse_style("bg:red") == Style()


def test_parse_empty_style_sets_nothing():
    assert parse_style("").is_zero()


def test_hex_colour_of_named_colour():
    assert hex_colour("bright-red") == "#f14c4c"


def test_hex_colour_of_hex_colour():
    assert hex_colour("#ff8800") == "#ff8800"


def test_hex_colour_of_no_colour():
    assert hex_colour("") == ""


def test_sgr_order_is_bold_dim_italic_underline_then_colours():
    style = Style(bold=True, italic=True, underline=True, dim=True, foreground="red", background="#102030")

    assert _sgr(style) == "1;2;3;4;31;48;2;16;32;48"


def test_sgr_of_bright_named_colour():
    assert _sgr(Style(foreground="bright-black")) == "90"


def test_sgr_of_hex_foreground():
    assert _sgr(Style(foreground="#ff8800")) == "38;2;255;136;0"


def test_sgr_of_empty_style():
    assert _sgr(Style()) == ""
