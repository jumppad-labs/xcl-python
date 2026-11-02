"""Starts a plugin through Python, for the tests that register a plugin as a command.

Run as ``python launcher.py <marker> <plugin> [args...]``. It writes the
plugin's path to ``marker``, so a test can see the plugin was started through
this launcher, then becomes the plugin: on POSIX it replaces itself with it,
so the plugin inherits the engine's standard streams and environment
unchanged; on Windows, which has no exec, it runs the plugin as a child with
the same streams and exits with its exit code.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: launcher.py <marker> <plugin> [args...]", file=sys.stderr)
        return 2

    marker, plugin, *args = argv
    with open(marker, "w", encoding="utf-8") as f:
        f.write(plugin)

    if os.name == "nt":
        return subprocess.run([plugin, *args]).returncode

    os.execv(plugin, [plugin, *args])
    return 1  # unreachable, execv does not return


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
