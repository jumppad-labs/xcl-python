"""Token kinds and labelled text, checked against the protocol's TokenKind."""

from xcl._core import core_pb2
from xcl.highlight import Kind, Token, css_class_of, parent_of
from xcl.highlight._kinds import _token_from_proto, _tokens_from_proto


def test_every_kind_is_in_the_protocol():
    for kind in Kind:
        assert core_pb2.TokenKind.Value("TOKEN_KIND_" + kind.name) == kind.value, kind.name


def test_every_protocol_kind_is_a_kind():
    for value in core_pb2.TokenKind.DESCRIPTOR.values:
        name = value.name.removeprefix("TOKEN_KIND_")
        assert Kind[name] == value.number, value.name


def test_child_kind_parent_is_its_category():
    assert Kind.LINE_COMMENT.parent == Kind.COMMENT


def test_category_parent_is_itself():
    assert Kind.COMMENT.parent == Kind.COMMENT


def test_text_parent_is_text():
    assert Kind.TEXT.parent == Kind.TEXT


def test_parent_of_unknown_kind_number():
    assert parent_of(1199) == 1100


def test_css_class_of_block_type():
    assert Kind.BLOCK_TYPE.css_class == "xcl-block-type"


def test_css_class_of_string_escape():
    assert Kind.STRING_ESCAPE.css_class == "xcl-string-escape"


def test_css_class_of_category():
    assert Kind.COMMENT.css_class == "xcl-comment"


def test_css_class_of_known_kind_number():
    assert css_class_of(1101) == "xcl-line-comment"


def test_unknown_kind_uses_category_class():
    assert css_class_of(1199) == "xcl-comment"


def test_unknown_kind_in_unknown_category_has_no_class():
    assert css_class_of(9999) == ""


def test_token_from_proto_keeps_known_kind_as_member():
    token = _token_from_proto(core_pb2.Token(kind=core_pb2.TOKEN_KIND_ATTRIBUTE, text="image"))

    assert token == Token(kind=Kind.ATTRIBUTE, text="image")
    assert isinstance(token.kind, Kind)


def test_token_from_proto_keeps_unknown_kind_as_number():
    token = _token_from_proto(core_pb2.Token(kind=1199, text="// later"))

    assert token.kind == 1199
    assert not isinstance(token.kind, Kind)
    assert token.text == "// later"


def test_tokens_from_proto_keep_order():
    tokens = _tokens_from_proto(
        [
            core_pb2.Token(kind=core_pb2.TOKEN_KIND_ATTRIBUTE, text="image"),
            core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" = "),
            core_pb2.Token(kind=core_pb2.TOKEN_KIND_STRING, text='"nginx"'),
        ]
    )

    assert tokens == [
        Token(kind=Kind.ATTRIBUTE, text="image"),
        Token(kind=Kind.TEXT, text=" = "),
        Token(kind=Kind.STRING, text='"nginx"'),
    ]
