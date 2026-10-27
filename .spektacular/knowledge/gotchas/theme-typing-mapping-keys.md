---
tags: [python, typing, mypy, highlight, themes]
---

# Type a kind-keyed mapping so a dict of enum keys passes

`Mapping` is invariant in its key type, so a user's `{Kind.COMMENT: "italic"}` assigned to a variable first (inferred `dict[Kind, str]`, `Kind` an `IntEnum`) is rejected by mypy where `Mapping[int, str]` is expected, even though `Kind` is an `int`. A literal passed straight to the call type-checks, which hides the problem in quick checks.

xcl-python's `xcl.highlight.Theme` is therefore `Union[Mapping[int, str], Mapping[Kind, str]]`, and the implementation reads it through one `cast(Mapping[int, str], theme)` helper (`_styles`). `DEFAULT_THEME` is annotated `types.MappingProxyType[int, str]`, not `Theme`: a plain `Mapping` has no `__or__` in typeshed, so the documented `DEFAULT_THEME | {Kind.ATTRIBUTE: "#ff8800"}` would fail mypy, while `MappingProxyType.__or__` returns a new `dict`.

Because the package ships `py.typed`, these shapes are checked for users; `tests/unit/test_typing.py` holds a mypy test of the documented theme idioms. Apply the same union to any other public parameter keyed by an int enum.
