"""One event as the line Go's example pretty logger writes for it.

Go's ``example/prettylog`` writes events through ``events.SlogHandler`` into
charmbracelet/log (v0.4.2) with its text format and the Kitchen time. This
module ports that layout, so a Python run reads exactly as a Go run does:

    3:04PM INFO create success source=core operation=create phase=success resource=resource.recording.one

It is pure: no I/O and no engine. Every piece that is styled goes through a
``style(text, style)`` function the caller supplies, with a style string from
:data:`STYLES`, so the layout itself never writes an escape code. The rules
follow ``text.go`` (``textFormatter``, ``writeIndent``,
``escapeStringForOutput``, ``needsQuoting``) and ``events/slog.go``, and the
values are written as Go's ``fmt`` writes them.
"""

from __future__ import annotations

import decimal
import logging
import math
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

from xcl.events import Event

Styler = Callable[[str, str], str]
"""Styles a piece of text: ``style(text, style_string)`` returns the text as written, plain or coloured."""


def plain(text: str, style: str) -> str:
    """The styler of plain text: every piece unchanged."""
    return text


STYLES: dict[str, str] = {
    # the level labels, bold as charmbracelet's, in the nearest of the 16
    # named colours to its 63, 86, 192 and 204
    "DEBU": "bold blue",
    "INFO": "bold cyan",
    "WARN": "bold yellow",
    "ERRO": "bold red",
    # keys and the separators are faint, as charmbracelet's defaults
    "key": "dim",
    "separator": "dim",
    # the keys that say where an event came from and what it is about,
    # coloured as Go's example colours them (lipgloss colours 5, 6 and 3)
    "key.source": "magenta",
    "value.source": "bold magenta",
    "key.resource": "cyan",
    "value.resource": "bold cyan",
    "key.operation": "yellow",
    "value.operation": "bold yellow",
}
"""The style string of each styled part of a line; the time, the message and other values are unstyled."""

# what charmbracelet writes before each line of a multi-line value
_INDENT_SEPARATOR = "  │ "


def kitchen(t: datetime) -> str:
    """``t`` in local time in Go's ``time.Kitchen`` form, such as ``3:04PM``."""
    local = t.astimezone()
    return f"{(local.hour % 12) or 12}:{local.minute:02d}{'AM' if local.hour < 12 else 'PM'}"


def level_label(level: int) -> str:
    """The four-letter label charmbracelet writes for a level: ``DEBU``, ``INFO``, ``WARN`` or ``ERRO``."""
    if level >= logging.ERROR:
        return "ERRO"
    if level >= logging.WARNING:
        return "WARN"
    if level >= logging.INFO:
        return "INFO"
    return "DEBU"


def attributes(event: Event) -> list[tuple[str, Any]]:
    """The event's attributes in the order Go's ``events.SlogHandler`` writes them, each set one only."""
    found: list[tuple[str, Any]] = []
    for key, value in (
        ("source", event.source),
        ("operation", event.operation),
        ("phase", event.phase),
        ("resource", event.resource_id),
        ("type", event.resource_type),
        ("file", event.file),
    ):
        if value:
            found.append((key, value))
    if event.duration != timedelta(0):
        found.append(("duration", event.duration))
    if event.error is not None:
        found.append(("error", str(event.error)))
    for key in sorted(event.meta):
        if event.phase == "log" and key in ("level", "message"):
            continue
        found.append((key, event.meta[key]))
    return found


def format_line(event: Event, level: int, message: str, style: Styler = plain) -> str:
    """The line Go's example writes for ``event`` at ``level`` with ``message``, ending in a line break."""
    return format_record(event.time, level, message, attributes(event), style)


def format_record(
    time: datetime,
    level: int,
    message: str,
    attrs: Sequence[tuple[str, Any]],
    style: Styler = plain,
) -> str:
    """A line in charmbracelet's text layout from its parts, for lines that are not an event's own, such as a warning."""
    label = level_label(level)
    out = [kitchen(time), " ", style(label, STYLES[label])]
    if message:
        out.append(" " + message)
    separator = style("=", STYLES["separator"])
    for i, (name, value) in enumerate(attrs):
        more = i < len(attrs) - 1
        text = go_value(value)
        raw = text == ""
        if raw:
            text = '""'
        key = style(name, STYLES.get("key." + name, STYLES["key"]))
        value_style = STYLES.get("value." + name, "")
        if "\n" in text:
            out.append("\n  " + key + separator + "\n")
            out.append(_indented(text, style(_INDENT_SEPARATOR, STYLES["separator"]), more, value_style, style))
        elif not raw and _needs_quoting(text):
            out.append(" " + key + separator + style('"' + _escape(text, quotes=True) + '"', value_style))
        else:
            out.append(" " + key + separator + style(text, value_style))
    out.append("\n")
    return "".join(out)


def _indented(text: str, indent: str, newline: bool, value_style: str, style: Styler) -> str:
    """A multi-line value, one indented line per line, as charmbracelet's ``writeIndent`` writes it.

    Every line but the last is written in the plain value style, and the
    last in the key's own value style; the last ends in a line break only
    when more attributes follow.
    """
    out: list[str] = []
    while True:
        newline_at = text.find("\n")
        if newline_at == -1:
            if text:
                out.append(indent + style(_escape(text, quotes=False), value_style))
                if newline:
                    out.append("\n")
            return "".join(out)
        out.append(indent + style(_escape(text[:newline_at], quotes=False), "") + "\n")
        text = text[newline_at + 1 :]


# -- Go's formatting of values ---------------------------------------------------


def go_value(value: Any) -> str:
    """``value``, decoded from JSON or an event field, as Go's ``fmt`` writes it through slog."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "<nil>"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return go_float(value)
    if isinstance(value, timedelta):
        return go_duration(value)
    if isinstance(value, (list, tuple)):
        return "[" + " ".join(go_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "map[" + " ".join(f"{go_value(k)}:{go_value(value[k])}" for k in sorted(value, key=str)) + "]"
    return str(value)


def go_float(value: float) -> str:
    """A float as Go's ``%v`` writes it: ``strconv.FormatFloat(f, 'g', -1, 64)``.

    The digits are the shortest that read back as the same float. The
    exponent form is used when the exponent is below -4 or at least 6 (the
    precision Go uses for this choice when it writes the shortest digits),
    with at least two exponent digits; otherwise the plain form, with no
    trailing ``.0``.
    """
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if value == 0:
        return "-0" if math.copysign(1.0, value) < 0 else "0"
    sign, digit_tuple, exponent = decimal.Decimal(repr(value)).normalize().as_tuple()
    assert isinstance(exponent, int)
    digits = "".join(str(d) for d in digit_tuple)
    point = len(digits) + exponent  # where the decimal point falls in digits
    first = point - 1  # the exponent of the first digit
    prefix = "-" if sign else ""
    if first < -4 or first >= 6:
        mantissa = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
        return f"{prefix}{mantissa}e{'-' if first < 0 else '+'}{abs(first):02d}"
    if point <= 0:
        return prefix + "0." + "0" * -point + digits
    if point >= len(digits):
        return prefix + digits + "0" * (point - len(digits))
    return prefix + digits[:point] + "." + digits[point:]


def go_duration(value: timedelta) -> str:
    """A duration as Go's ``time.Duration.String`` writes it, such as ``1.5ms`` or ``1m1s``."""
    nanoseconds = ((value.days * 86400 + value.seconds) * 1_000_000 + value.microseconds) * 1000
    negative = nanoseconds < 0
    u = -nanoseconds if negative else nanoseconds
    if u == 0:
        return "0s"
    if u < 1_000_000_000:
        # under a second, the largest unit that keeps a whole part
        if u < 1000:
            unit, precision = "ns", 0
        elif u < 1_000_000:
            unit, precision = "µs", 3
        else:
            unit, precision = "ms", 6
        fraction, u = _fraction(u, precision)
        text = str(u) + fraction + unit
    else:
        fraction, u = _fraction(u, 9)
        text = str(u % 60) + fraction + "s"
        u //= 60
        if u > 0:
            text = str(u % 60) + "m" + text
            u //= 60
            if u > 0:
                text = str(u) + "h" + text
    return "-" + text if negative else text


def _fraction(value: int, precision: int) -> tuple[str, int]:
    """Go's ``fmtFrac``: the fraction of ``value / 10**precision`` without trailing zeros, and the whole part."""
    digits: list[str] = []
    printed = False
    for _ in range(precision):
        digit = value % 10
        printed = printed or digit != 0
        if printed:
            digits.append(str(digit))
        value //= 10
    if printed:
        digits.append(".")
    return "".join(reversed(digits)), value


# -- charmbracelet's quoting and escaping -----------------------------------------


def _printable(char: str) -> bool:
    """Go's ``unicode.IsPrint``: letters, marks, numbers, punctuation, symbols and the ASCII space."""
    return char == " " or char.isprintable()


def _needs_quoting(text: str) -> bool:
    """Whether charmbracelet quotes a value: it holds ``"``, ``=``, a space or a character that does not print."""
    for char in text:
        if char in '"= ' or char == "�" or not _printable(char):
            return True
    return False


_ESCAPES = {"\a": "\\a", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\v": "\\v"}


def _escape(text: str, *, quotes: bool) -> str:
    """Characters that do not print written as Go escapes, and ``"`` as ``\\"`` when ``quotes``, as ``escapeStringForOutput``."""
    out: list[str] = []
    for char in text:
        if quotes and char == '"':
            out.append('\\"')
        elif _printable(char):
            out.append(char)
        elif char in _ESCAPES:
            out.append(_ESCAPES[char])
        else:
            code = ord(char)
            if code < 0x20:
                out.append(f"\\x{code:02x}")
            elif 0xD800 <= code <= 0xDFFF:
                # a lone surrogate is not a valid rune; Go writes the
                # replacement character in its place
                out.append("\\ufffd")
            elif code < 0x10000:
                out.append(f"\\u{code:04x}")
            else:
                out.append(f"\\U{code:08x}")
    return "".join(out)
