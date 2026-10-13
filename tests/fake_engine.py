"""A stand-in for the engine program, speaking the frame protocol over its standard input and output.

It is run as a script with ``sys.executable`` by the subprocess transport's
unit tests, never imported. Each frame is a 4-byte big-endian length followed
by a ``Request`` (read from stdin) or a ``Response`` (written to stdout) of
``transport.proto``. Every request is handled on its own thread, so a slow
request never holds up a quick one and responses can arrive out of order.

Methods it understands:

- ``GetVersion``: ``GetVersionResponse`` with ``abi_version`` from ``FAKE_ABI``
  (default 1) and ``version`` from ``FAKE_VERSION``.
- ``CreateConfig``: ``CreateConfigResponse`` with the next handle, from 1.
- ``Release``: status 0 for a handle it issued, -3 otherwise.
- ``Echo`` (test only): the payload is JSON; it creates the file named by
  ``started_file`` when given, sleeps ``delay_ms`` and answers with the same
  payload.
- ``Status`` (test only): the payload is an ascii integer, answered as the
  status.
- ``Exit``: exits at once with the ascii integer code in the payload.
- ``Kill``: sends itself SIGKILL (exit 137 where there is no SIGKILL).

Any other method answers status -1. When ``FAKE_STDERR`` is set, its value is
written to standard error as a line at start up. The program exits 0 when its
input ends.
"""

from __future__ import annotations

import json
import os
import signal
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xcl._core import core_pb2, transport_pb2  # noqa: E402

FRAME_HEADER = struct.Struct(">I")

STATUS_UNKNOWN_METHOD = -1
STATUS_UNKNOWN_HANDLE = -3

write_lock = threading.Lock()
handles_lock = threading.Lock()
handles: set[int] = set()
next_handle = [1]


def unsigned(status: int) -> int:
    """A signed status as the two's-complement uint32 the Response carries."""
    return status & 0xFFFFFFFF


def read_exact(stream, size: int) -> bytes | None:
    chunks = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def respond(request_id: int, status: int, payload: bytes) -> None:
    body = transport_pb2.Response(id=request_id, status=unsigned(status), payload=payload).SerializeToString()
    with write_lock:
        sys.stdout.buffer.write(FRAME_HEADER.pack(len(body)) + body)
        sys.stdout.buffer.flush()


def handle_request(request) -> None:
    method = request.method

    if method == "GetVersion":
        answer = core_pb2.GetVersionResponse(
            version=os.environ.get("FAKE_VERSION", "v0.0.0-fake"),
            abi_version=int(os.environ.get("FAKE_ABI", "1")),
        )
        respond(request.id, 0, answer.SerializeToString())
        return

    if method == "CreateConfig":
        with handles_lock:
            handle = next_handle[0]
            next_handle[0] += 1
            handles.add(handle)
        respond(request.id, 0, core_pb2.CreateConfigResponse(handle=handle).SerializeToString())
        return

    if method == "Release":
        with handles_lock:
            known = request.handle in handles
            handles.discard(request.handle)
        respond(request.id, 0 if known else STATUS_UNKNOWN_HANDLE, b"")
        return

    if method == "Echo":
        options = json.loads(request.payload.decode("utf-8") or "{}")
        started_file = options.get("started_file")
        if started_file:
            Path(started_file).touch()
        time.sleep(options.get("delay_ms", 0) / 1000)
        respond(request.id, 0, request.payload)
        return

    if method == "Status":
        respond(request.id, int(request.payload.decode("ascii")), b"")
        return

    if method == "Exit":
        os._exit(int(request.payload.decode("ascii") or "0"))

    if method == "Kill":
        if hasattr(signal, "SIGKILL"):
            os.kill(os.getpid(), signal.SIGKILL)
        os._exit(137)

    respond(request.id, STATUS_UNKNOWN_METHOD, b"")


def main() -> None:
    marker = os.environ.get("FAKE_STDERR")
    if marker:
        sys.stderr.write(marker + "\n")
        sys.stderr.flush()

    stdin = sys.stdin.buffer
    while True:
        header = read_exact(stdin, FRAME_HEADER.size)
        if header is None:
            break
        (size,) = FRAME_HEADER.unpack(header)
        body = read_exact(stdin, size)
        if body is None:
            break
        request = transport_pb2.Request.FromString(body)
        threading.Thread(target=handle_request, args=(request,), daemon=True).start()

    sys.stdout.buffer.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
