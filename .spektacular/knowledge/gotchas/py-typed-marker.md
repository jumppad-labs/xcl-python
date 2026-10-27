---
tags: [python, typing, mypy, packaging]
---

# Type checkers ignore xcl-python without py.typed

mypy reads the installed `xcl` package's annotations in a user's program only because the package ships `xcl/py.typed` (PEP 561, added by spec 20261023074223-e06f835f-event-data-level-enum). Without the marker mypy reports `import-untyped` and never checks calls into the package: a string passed where an enum is annotated goes unflagged. With it, mypy reports `arg-type`.

`tests/unit/test_typing.py` guards this: it runs mypy in a subprocess from a temp directory, with no `MYPYPATH`, over user-style programs against the installed (editable) package. Removing the marker makes its string-flagging test fail.

Because the marker is shipped, every public annotation is part of users' type checking, so annotations must stay accurate. Any Python spec that promises type-checker behaviour can prove it by adding a snippet test there.
