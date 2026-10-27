---
created_date: "2026-10-26"
document_status: draft
project: xclconfig
spec: 20261023075302-bad71237-printing-and-highlighting-python
plan: 20261023075302-bad71237-printing-and-highlighting-python
---

# Printing and highlighting for Python

xcl errors now show the configuration lines in question: printed in one call with `xcl.print_error`, and on their own after an uncaught error's traceback or a logged exception, while `str(err)` stays one line. Resources, saved records and change summaries print in one call, as plain text, terminal colour, HTML, inline-styled HTML or SVG, styled by themes you extend or load from VS Code, or by a format you write. Events reach Python's standard logging with `xcl.logging_handler`. The `highlight=` option of `encode_entity` and `encode_saved_entity` is removed; print with `cfg.print_entity(entity, formatter=xcl.highlight.TERMINAL)` instead.

> Derived from project xcl, spec/plan 20261023075302-bad71237-printing-and-highlighting-python. See the project-level record for the full feature.

## What changed

- **Breaking:** `highlight=` is removed from `encode_entity` and `encode_saved_entity` on `xcl.Config` and `xcl.aio.Config`; passing it raises `TypeError`. The protocol stubs in `xcl/_core` are regenerated from the engine that sends labelled text.
- New public package `xcl.highlight`: `Kind`, `Token`, `parent_of`, `css_class_of`, `Style`, `parse_style`, `hex_colour`, `Theme`, `DEFAULT_THEME`, `style_for`, `validate`, the `Formatter` protocol and the formats `PLAIN`, `TERMINAL`, `HTML`, `HTML_INLINE`, `SVG`, `css`, `for_stream`, `load_vscode_theme` and `LogFormatter`.
- New top-level names: `xcl.print_error`, `xcl.format_error`, `xcl.print_diff`, `xcl.logging_handler`, `xcl.InvalidStyleError`, `xcl.InvalidThemeError`.
- `xcl.Error` gains `tokens` and, when it holds a configuration problem, an exception note with the plain report wrapped at 80 columns.
- `Config` and `aio.Config` gain `print_entity`, `print_saved_entity`, `entity_tokens` and `saved_entity_tokens`; `Diff` gains `tokens`.
- Tests: reference-output tests for every format, the stylesheet and the class names; kinds against the protocol; wrapping against Go's output; error notes and printing; entity and diff printing for both flavours; VS Code themes; the logging bridge; `LogFormatter`; mypy tests for the theme idioms; and parity stages comparing printed reports, entities, change summaries and event logs with Go's on every fixture, including a new unsupported-block fixture.
- README ("Printing and highlighting", "Logging", "Migrating from highlight=") and PARITY.md ("Printing", "Logging") document it all.

## Why

Python programs saw configuration mistakes as one line and could not style or render xcl's output. This brings Go's printing to Python through the engine's labelled text, held byte for byte to Go's output. No runtime dependency beyond protobuf is added.

The release that ships this pins an xcl release carrying the engine's labelled text and the parity program's new stages; until then `xcl-ref.txt` stays at `v0.11.1`.
