---
tags: [python, events, errors, printing]
---

# Printing each problem's report once from a Python event handler

A configuration with problems emits one error event per problem, then the closing `<operation> error` event whose error holds every problem (the xcl gotcha `unsupported-block-reports-twice.md`). In Python both arrive as `xcl.ConfigError` carrying a report in `err.tokens`, so printing every error event's report shows each problem twice.

The two are told apart by `causes`: a single problem's event carries a `ConfigError` with a report and no `causes`, while the closing event's `ConfigError` lists every problem in `causes`. A handler that prints reports as they happen prints `event.error` only when `event.error.tokens and not event.error.causes`, and leaves the closing event to a one-line summary (or prints it only when no per-problem event came first).
