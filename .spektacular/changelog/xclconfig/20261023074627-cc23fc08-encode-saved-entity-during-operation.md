---
created_date: "2026-10-26"
document_status: draft
project: xclconfig
spec: 20261023074627-cc23fc08-encode-saved-entity-during-operation
plan: 20261023074627-cc23fc08-encode-saved-entity-during-operation
---

# Render saved records from an event handler

A Python program can now call `cfg.encode_saved_entity(event.data)` from its `on_event` handler while an apply is still running, with either the synchronous or the asyncio client. It can print each created resource's configuration beneath its success event as the apply goes. `cfg.encode_entity` on a looked-up or edited entity still raises `xcl.OperationInProgressError` during an operation. The capability arrives with the bundled engine from the xcl release that contains it.

> Derived from project xclconfig, spec/plan 20261023074627-cc23fc08-encode-saved-entity-during-operation. See the project-level record for the full feature.

## What changed in this repo

- New integration tests in `tests/integration/test_sync.py` and `tests/integration/test_aio.py` render from a create success handler during an apply that uses a Python state store. They check:
  - that the text equals the post-apply render;
  - that the apply is unchanged by rendering;
  - the refusals for looked-up and edited entities;
  - `InvalidSavedDataError` and `UnregisteredTypeError` for bad records.
- Docstrings in `xcl/config.py` and `xcl/aio.py`, and the README's encoding section, say when each encoder may run. The README includes an example that prints each created resource.
- No package code changed.

## Why

The engine used to refuse every render until an operation ended. So a Python program could only show what was created after the whole apply had finished.

## Follow-up

The new tests need an engine built from the xcl release that contains the change. They fail against the currently pinned `v0.11.1` until the automated engine bump updates `xcl-ref.txt`.
