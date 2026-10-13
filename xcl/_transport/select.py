"""Choosing the transport: the one place that decides which engine runs.

The decision rests on what the installed package holds and on one variable,
``XCL_TRANSPORT``, never on probing the machine:

- unset, empty or ``subprocess``: the bundled engine program,
  ``xcl/_bin/xcl-core``, which every wheel carries; this is used even when a
  source build has also produced the shared library;
- ``inprocess``: the shared library a source build produces with
  ``make libxcl``, ``xcl/_lib/libxcl.*`` or ``XCL_LIBRARY_PATH``.

There is no fallback from one to the other: when the selected engine is
absent the first use raises :class:`~xcl.EngineNotFoundError`, naming where
both forms were expected, so which engine runs is the same on every machine
the package is installed on.
"""

from __future__ import annotations

import os

from xcl._errors import EngineNotFoundError
from xcl._transport import InProcessTransport, SubprocessTransport, Transport
from xcl._transport.inprocess import default_library_path
from xcl._transport.subprocess import program_path

# TRANSPORT_ENV names the variable that selects the transport
TRANSPORT_ENV = "XCL_TRANSPORT"

SUBPROCESS = "subprocess"
INPROCESS = "inprocess"


def selected_route() -> str:
    """The route ``XCL_TRANSPORT`` selects: ``subprocess`` or ``inprocess``.

    Raises :class:`ValueError` for any other value.
    """
    value = os.environ.get(TRANSPORT_ENV, "").strip()
    if value in ("", SUBPROCESS):
        return SUBPROCESS
    if value == INPROCESS:
        return INPROCESS
    raise ValueError(
        f"{TRANSPORT_ENV}={value!r} is not a transport xcl knows; "
        f"leave it unset or set it to {SUBPROCESS!r} for the bundled engine program, "
        f"or to {INPROCESS!r} for the shared library of a source build"
    )


def select_transport() -> Transport:
    """The transport the default client uses, as the package's contents and ``XCL_TRANSPORT`` decide.

    Raises :class:`~xcl.EngineNotFoundError` when the selected engine is not
    present, and :class:`ValueError` for an unknown ``XCL_TRANSPORT``.
    """
    route = selected_route()
    program = program_path()
    library = default_library_path()

    if route == SUBPROCESS:
        if not program.is_file():
            raise EngineNotFoundError(program=program, library=library, transport=route)
        return SubprocessTransport(program)

    if not library.is_file():
        raise EngineNotFoundError(program=program, library=library, transport=route)
    return InProcessTransport(library)
