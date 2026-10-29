---
tags: [go, logging, parity, formatting]
---

# Matching Go's log lines from another language

Ports that must reproduce Go's log output byte for byte (the pretty logger, parity stages) trip on these formatting rules:

- Go's `fmt` `%v` for a float64 switches to exponent form when the exponent is at least 6 or below -4: `1234567.0` prints `1.234567e+06`, while `123456.0` prints `123456`.
- charmbracelet/log (v0.4.2) quotes any value containing a space, `=`, `"` or a non-printable character. Lists and maps (`[a 1]`, `map[a:x]`) are therefore quoted, because Go's form contains spaces.
- charmbracelet drops an empty message entirely; there is no double space.
- A multi-line value is written as `\n  key=\n` and then one `  │ line` per line. Only the last line takes the key's value style, and it ends in a line break only when more attributes follow; the next attribute then starts its line with a space. A value ending in a line break leaves a blank line before the final break.
- Go's `unicode.IsPrint` equals Python's `str.isprintable()` plus the ASCII space.

Produce expected lines by running Go rather than writing them by hand: a throwaway program writing an `events.Event` through `events.SlogHandler` into `charmlog.NewWithOptions(&buf, ...)` prints them in seconds. xcl-python's `xcl/_prettyline.py` is the reference port.
