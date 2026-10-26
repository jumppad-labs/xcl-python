"""The stylesheet generated from a theme for the HTML format's classes."""

from xcl.highlight import DEFAULT_THEME, Kind, Theme, css


def test_every_rule_is_scoped_under_xcl():
    theme: Theme = DEFAULT_THEME | {Kind.TEXT: "#eeeeee", Kind.LINE_COMMENT: "underline"}

    for rule in css(theme).splitlines():
        assert rule.startswith(".xcl"), rule


def test_parent_rule_comes_before_child_rule():
    theme: Theme = {Kind.LINE_COMMENT: "#ff0000", Kind.COMMENT: "#00ff00"}

    stylesheet = css(theme)

    assert stylesheet.index(".xcl .xcl-comment {") < stylesheet.index(".xcl .xcl-line-comment {")


def test_changing_attribute_style_changes_only_attribute_rule():
    default_rules = css(DEFAULT_THEME).splitlines()
    changed_rules = css(DEFAULT_THEME | {Kind.ATTRIBUTE: "#ff8800"}).splitlines()

    differences = [(old, new) for old, new in zip(default_rules, changed_rules) if old != new]

    assert len(changed_rules) == len(default_rules)
    assert differences == [(".xcl .xcl-attribute { color: #2472c8; }", ".xcl .xcl-attribute { color: #ff8800; }")]


def test_child_kind_resets_bold_of_its_category():
    theme: Theme = {Kind.BLOCK: "bold magenta", Kind.BLOCK_TYPE: "cyan"}

    assert css(theme) == (
        ".xcl .xcl-block { color: #bc3fbc; font-weight: bold; }\n"
        ".xcl .xcl-block-type { color: #11a8cd; font-weight: normal; }\n"
    )


def test_text_style_writes_container_rule_first():
    theme: Theme = {Kind.ATTRIBUTE: "blue", Kind.TEXT: "#eeeeee"}

    assert css(theme) == ".xcl { color: #eeeeee; }\n.xcl .xcl-attribute { color: #2472c8; }\n"
