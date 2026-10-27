---
created_date: "2026-10-26"
document_status: draft
project: xclconfig
spec: 20261023074223-e06f835f-event-data-level-enum
plan: 20261023074223-e06f835f-event-data-level-enum
---

# Event data levels are an enum: xcl.EventDataLevel

`xcl.Config` and `xcl.aio.Config` now take the event data level as `xcl.EventDataLevel.NONE`, `RAW` or `PROCESSED`, the Python form of Go's `xcl.EventDataLevel`. This is a breaking change: a string such as `"processed"` is now refused with a `TypeError` that names the enum, so code that passed a word passes the member of the same name instead. Leaving the option out still means no event data. The package now declares itself typed, so mypy and pyright flag a string passed as the level and editors complete the members.

> Derived from project xclconfig, spec/plan 20261023074223-e06f835f-event-data-level-enum. See the project-level record for the full feature.

## What changed in this repo

- `xcl.EventDataLevel`, a `StrEnum` with `NONE`, `RAW` and `PROCESSED` whose values are the old words, is declared in `xcl/events.py`, exported from `xcl`, and documented in the words of Go's constants.
- `xcl/config.py` replaces the public `EVENT_DATA_LEVELS` map with a private check, `_event_data_level`, and a private mapping from member to protocol value. Both `xcl.Config` and `xcl.aio.Config` call the check first. It refuses anything that is not a member, by type, with a `TypeError`, before any client, class map or polling executor is set up and before any configuration is created. Both signatures are `event_data: EventDataLevel = EventDataLevel.NONE`, and the `xcl.Config` docstring describes the option in terms of the enum.
- `xcl/py.typed` (PEP 561) ships in the wheel and the sdist.
- `mypy` joins the `test` extra, with a comment saying it is used only by `tests/unit/test_typing.py`.
- Tests:
  - `tests/unit/test_config.py` checks each member's wire value, the default and each refused value (`"processed"`, `"verbose"`, `1`, `None`) for both flavours, each in its own test.
  - `tests/unit/test_events.py` checks the top-level import and the three members.
  - `tests/unit/test_typing.py` runs mypy over user-style programs.
  - `tests/integration/test_sync.py` adds raw, none and left-out level tests against the engine.
  - The existing processed-level integration tests use the member.
- `README.md` uses the enum in its events example, names the members, and adds "Migrating from string event data levels". `PARITY.md` pairs `WithEventData(level)` and Go's `xcl.EventDataLevel` with the Python enum.

## Why

A bare word was checked only at run time and could not be completed by editors. The enum makes the choice visible to tools, catches mistakes before a program runs, and makes Python programs read like Go's. The release that ships this is a minor bump (pre-1.0), and its GitHub release notes are to carry the breaking-change line with the `event_data="processed"` → `event_data=xcl.EventDataLevel.PROCESSED` example.
