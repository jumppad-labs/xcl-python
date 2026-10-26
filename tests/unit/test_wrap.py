"""Wrapping a report's detail exactly as Go's printing wraps it.

Every expected string below was produced by running Go's
``github.com/mitchellh/go-wordwrap`` v1.0.1 ``WrapString`` on the same input
and width, and pasted here by hand.
"""

from xcl._wrap import wrap_detail

SENTENCE = (
    'Blocks of type "timeout" are not expected here. Did you mean to define an argument called "timeout" '
    "instead, as an attribute with an equals sign?"
)


def test_sentence_wrapped_at_80():
    # from go-wordwrap v1.0.1 WrapString(SENTENCE, 80)
    expected = (
        'Blocks of type "timeout" are not expected here. Did you mean to define an\n'
        'argument called "timeout" instead, as an attribute with an equals sign?'
    )

    assert wrap_detail(SENTENCE, 80) == expected


def test_sentence_wrapped_at_40():
    # from go-wordwrap v1.0.1 WrapString(SENTENCE, 40)
    expected = (
        'Blocks of type "timeout" are not\n'
        "expected here. Did you mean to define an\n"
        'argument called "timeout" instead, as an\n'
        "attribute with an equals sign?"
    )

    assert wrap_detail(SENTENCE, 40) == expected


def test_word_longer_than_width_left_whole_on_its_own_line():
    text = "a short start then averyveryveryverylongwordthatisfarlongerthanthewidth and more"
    # from go-wordwrap v1.0.1 WrapString(text, 20)
    expected = "a short start then\naveryveryveryverylongwordthatisfarlongerthanthewidth\nand more"

    assert wrap_detail(text, 20) == expected


def test_runs_of_spaces_kept_within_a_line():
    text = "one  two   three    four five six seven eight"
    # from go-wordwrap v1.0.1 WrapString(text, 12)
    expected = "one  two\nthree\nfour five\nsix seven\neight"

    assert wrap_detail(text, 12) == expected


def test_existing_line_break_kept():
    text = "first line here\nsecond line is a bit longer than the width"
    # from go-wordwrap v1.0.1 WrapString(text, 20)
    expected = "first line here\nsecond line is a bit\nlonger than the\nwidth"

    assert wrap_detail(text, 20) == expected


def test_trailing_spaces_kept():
    text = "words that end in spaces   "
    # from go-wordwrap v1.0.1 WrapString(text, 10)
    expected = "words that\nend in\nspaces   "

    assert wrap_detail(text, 10) == expected


def test_tab_is_a_space_between_words():
    text = "one\ttwo\tthree four five six"
    # from go-wordwrap v1.0.1 WrapString(text, 10)
    expected = "one\ttwo\nthree four\nfive six"

    assert wrap_detail(text, 10) == expected


def test_no_break_space_never_broken_at():
    text = "keep these words together and these apart"
    # from go-wordwrap v1.0.1 WrapString(text, 12)
    expected = "keep these words together\nand these\napart"

    assert wrap_detail(text, 12) == expected


def test_word_exactly_the_width_fits():
    text = "abcde fghij"
    # from go-wordwrap v1.0.1 WrapString(text, 5)
    expected = "abcde\nfghij"

    assert wrap_detail(text, 5) == expected


def test_several_line_breaks_and_spaces_around_them():
    text = "a b c\n\nd e f   \n  g"
    # from go-wordwrap v1.0.1 WrapString(text, 3)
    expected = "a b\nc\n\nd e\nf\n  g"

    assert wrap_detail(text, 3) == expected


def test_width_zero_leaves_text_unchanged():
    assert wrap_detail(SENTENCE, 0) == SENTENCE


def test_width_none_leaves_text_unchanged():
    assert wrap_detail(SENTENCE, None) == SENTENCE


def test_negative_width_leaves_text_unchanged():
    assert wrap_detail(SENTENCE, -1) == SENTENCE
