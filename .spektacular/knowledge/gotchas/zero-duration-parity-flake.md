---
tags: [testing, events, windows, parity, flaky]
---

# Go drops `duration` from a log line when it measures zero, which flakes the parity suite on Windows

`events/slog.go` in xcl adds the `duration` attribute only when `e.Duration != 0`. On Windows the clock is coarse enough that a quick create can measure exactly zero, so Go's pretty log line for it has no `duration=` at all.

The parity suite (`tests/parity`) rewrites every `duration=<value>` to `duration=<duration>` and then compares the Go and Python records line by line. When one side measured zero and the other did not, the lines differ only by ` duration=<duration>`, and `assert_same_record` fails with `the records differ at pretty_log[N]`. It is a timing flake, seen on `windows-latest / py3.12` for xcl-python PR #27 on 2026-11-14 while every other job passed, and a re-run clears it.

A lasting fix would be to strip the `duration` attribute completely in the parity normaliser instead of rewriting its value, or to have Go always write `duration`. Until then, re-run a Windows parity failure that differs only by ` duration=<duration>` before investigating it.
