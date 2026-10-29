---
tags: [python, testing, worktrees, engine]
---

# Running the xcl-python suite in a spec worktree

A spec worktree of xcl-python holds only tracked files: no `.venv`, no `xcl/_bin/xcl-core` and no `build/plugins`. The main checkout's `.venv` is an editable install of the main checkout, so running tests with it exercises the wrong code.

What works, with nothing shared with the main checkout:

1. Create a venv inside the worktree and install it editable: `uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e '.[test]'`. Check `python -c "import xcl; print(xcl.__file__)"` points into the worktree.
2. Export the engine source at the pin rather than building from the xcl worktree (whose HEAD may be ahead of the pin): `git -C <xcl checkout> archive $(cat xcl-ref.txt) | tar -x -C <scratch dir>`.
3. Build the engine and fixture plugins from that copy: `make engine plugins XCL_SRC=<scratch dir> PYTHON=.venv/bin/python`. `xcl/_bin/`, `build/` and `.venv/` are gitignored, so they never show in the worktree's diff.

The full suite then runs (`.venv/bin/python -m pytest -q -rs`); one test in `tests/integration/test_load.py` skips because it runs only on the inprocess route.

Run it with `GITHUB_TOKEN=$(gh auth token)` set. The plugin-release tests (`tests/integration/test_test_plugin.py`, `test_github_tamper.py`) download a release through GitHub's API, and a few full runs exhaust the anonymous rate limit: they then skip, or error under `XCL_TEST_STRICT=1`. The engine's GitHub registry client reads `GITHUB_TOKEN`, which lifts the limit.

To build against protocol or engine changes that are not released yet (an xcl worktree ahead of the pin), point `XCL_SRC` at that xcl checkout instead of an archive of the pin: `make protos engine plugins XCL_SRC=<xcl checkout> PYTHON=.venv/bin/python`, and run the suite with the same `XCL_SRC` so the reference-output tests read that checkout.

The parity suite (`tests/parity`) runs the Go parity program from `build/plugins/parity`. After changing xcl's `bindings/libxcl/cmd/parity`, run `make plugins XCL_SRC=<xcl checkout>` again, or the comparison silently uses the old Go record.
