---
tags: [python, enum, validation]
---

# A StrEnum member equals its string

An `enum.StrEnum` member compares and hashes equal to its string value: `EventDataLevel.PROCESSED == "processed"` is true, and `"processed" in {EventDataLevel.PROCESSED: ...}` finds the member. A check meant to refuse plain strings must therefore test the type with `isinstance(value, TheEnum)`. A membership test (`in`) or a dict lookup silently lets the bare string through.
