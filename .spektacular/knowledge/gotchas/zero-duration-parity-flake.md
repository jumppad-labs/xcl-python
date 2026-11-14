---
tags: [testing, events, windows, parity, flaky]
---

# Go drops `duration` from a log line when it measures zero, so a pretty log comparison must drop durations too

`events/slog.go` in xcl adds the `duration` attribute only when `e.Duration != 0`. On Windows the clock is coarse (about 15 ms), so a quick create can measure exactly zero, and its pretty log line has no `duration=` at all. The same is true of this SDK's pretty log, which matches Go's.

Any test comparing two pretty logs that were timed separately (Go against Python in the parity suite, or two runs of one apply) therefore cannot just rewrite `duration=<value>` to a placeholder: one side may have the attribute and the other not. Drop it entirely before comparing. Three tests do this:

- `tests/parity/test_parity.py` `without_durations`, applied in `assert_same_record` (PR #28, after the flake failed the v0.15.0 win_arm64 wheel build).
- `tests/integration/test_prettylog_engine.py` `normalised` and `tests/integration/test_aio.py` `prettylog_normalised` (PR #29).

A new test comparing pretty logs across runs or languages needs the same treatment. Do not re-run a failure that differs only by a duration: fix the comparison ([[flaky-tests-are-fixed-not-rerun]]).
