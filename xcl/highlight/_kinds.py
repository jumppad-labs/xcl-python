"""Token kinds and labelled text, mirrored by hand from the protocol's ``TokenKind``."""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Iterable
from typing import Any


class Kind(enum.IntEnum):
    """What a piece of labelled text is, numbered as the protocol numbers it.

    Kinds are numbered in blocks of 100. A kind's category, its
    :attr:`parent`, is ``kind // 100 * 100``, so a theme that styles
    ``COMMENT`` covers every comment, and a kind a newer engine sends that
    this package does not know still falls back to its category. The names
    are the protocol's ``TokenKind`` names without ``TOKEN_KIND_``.
    """

    # unlabelled text, such as spaces and line breaks
    TEXT = 0

    # a block's header: its type, and the type of a nested block
    BLOCK = 100
    BLOCK_TYPE = 101
    NESTED_BLOCK = 102

    # a block's labels: its subtype and its name
    LABEL = 200
    TYPE_LABEL = 201
    NAME_LABEL = 202

    # an attribute's name
    ATTRIBUTE = 300

    # strings and their parts
    STRING = 400
    STRING_ESCAPE = 401
    HEREDOC = 402
    HEREDOC_MARKER = 403
    HEREDOC_OPERATOR = 404

    # a number
    NUMBER = 500

    # true, false and null
    CONSTANT = 600

    # a function call's name
    FUNCTION = 700
    BUILTIN_FUNCTION = 701

    # a reference to another entity, and a member of one
    REFERENCE = 800
    MEMBER = 801

    # an operator
    OPERATOR = 900

    # punctuation, interpolation and template directives
    PUNCTUATION = 1000
    INTERPOLATION_BEGIN = 1001
    INTERPOLATION_END = 1002
    TEMPLATE_DIRECTIVE = 1003
    ACCESSOR = 1004

    # comments
    COMMENT = 1100
    LINE_COMMENT = 1101
    HASH_COMMENT = 1102
    BLOCK_COMMENT = 1103

    # a change summary's markers
    DIFF = 1200
    INSERTED = 1201
    DELETED = 1202
    CHANGED = 1203

    # the faulty span of a problem
    PROBLEM = 1300
    ERROR = 1301
    WARNING = 1302

    # a report's parts: summary, location, line-number gutter and detail
    REPORT = 1400
    SUMMARY = 1401
    LOCATION = 1402
    GUTTER = 1403
    DETAIL = 1404

    @property
    def parent(self) -> int:
        """The kind's category, ``kind // 100 * 100``, such as ``COMMENT`` for ``LINE_COMMENT``."""
        return parent_of(self)

    @property
    def css_class(self) -> str:
        """The kind's HTML class, such as ``xcl-block-type``, the same in every language."""
        return "xcl-" + self.name.lower().replace("_", "-")


def parent_of(kind: int) -> int:
    """The category of any kind number, known or not: ``kind // 100 * 100``."""
    return int(kind) // 100 * 100


def _known(kind: int) -> Kind | None:
    """The :class:`Kind` member numbered ``kind``, or ``None`` for a number this package does not know."""
    try:
        return Kind(kind)
    except ValueError:
        return None


def css_class_of(kind: int) -> str:
    """The HTML class of any kind number: a known kind's own, else its known category's, else ``""``."""
    known = _known(kind)
    if known is not None:
        return known.css_class
    parent = _known(parent_of(kind))
    if parent is not None and parent != kind:
        return parent.css_class
    return ""


def _go_name(kind: int) -> str:
    """The name Go gives a kind, such as ``BlockType``, or ``Kind(1199)`` for one it does not know."""
    known = _known(kind)
    if known is None:
        return f"Kind({int(kind)})"
    return "".join(part.capitalize() for part in known.name.split("_"))


@dataclasses.dataclass(frozen=True)
class Token:
    """One piece of labelled text: its kind and its text.

    ``kind`` is a :class:`Kind` member when this package knows it, and the
    plain number otherwise. The texts of a list of tokens, joined in order,
    are the whole output, every byte of it.
    """

    kind: int
    text: str


def _token_from_proto(token: Any) -> Token:
    """A protocol ``Token`` as a :class:`Token`, keeping a kind this package does not know as its number."""
    known = _known(token.kind)
    return Token(kind=known if known is not None else int(token.kind), text=token.text)


def _tokens_from_proto(tokens: Iterable[Any]) -> list[Token]:
    """Protocol tokens as :class:`Token` objects, in order."""
    return [_token_from_proto(token) for token in tokens]
