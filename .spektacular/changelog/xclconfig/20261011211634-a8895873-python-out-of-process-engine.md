---
created_date: "2026-10-13"
document_status: draft
project: xclconfig
spec: 20261011211634-a8895873-python-out-of-process-engine
plan: 20261011211634-a8895873-python-out-of-process-engine
---

# xcl-lang runs the engine as a bundled subprocess, Alpine included

xcl-lang now bundles the XCL engine as a small program and runs it as a subprocess, the same way on every platform: Linux on glibc and musl (Alpine), macOS and Windows, on x86-64 and arm64. The API and results are unchanged, and installing needs no Go or C compiler. The engine starts on first use, is shared by every configuration, and stops on its own, even when your program is killed. If it dies, you get `xcl.EngineExitedError` and the next configuration starts a fresh one. A forked child simply creates its own configuration.

> Derived from project xcl (jumppad-labs), spec/plan 20261011211634-a8895873-python-out-of-process-engine. See the project-level record for the full feature.

## What changed in this repo

- **Transport.** `xcl/_transport/subprocess.py` adds `SubprocessTransport`:
  - lazy start of `xcl/_bin/xcl-core --serve` and an ABI handshake;
  - one reader thread matching responses by id, with calls waiting in short slices;
  - its own configuration handles, mapped per engine;
  - the engine stopped on the last release, on `close()` and at exit;
  - a kill-on-close job object on Windows;
  - `EngineExitedError` for every waiter when the engine dies, and a restart on next use;
  - `ForkedProcessError` for pre-fork configurations in a child.
- **Selection.** `xcl/_transport/select.py` chooses the transport: the program by default, or the source-built shared library with `XCL_TRANSPORT=inprocess`. An unknown value is an error, and a missing engine raises `EngineNotFoundError` naming both expected paths. `default_client()` uses it.
- **Errors.** `xcl.EngineNotFoundError` and `xcl.EngineExitedError` are new.
- **Protocol.** `make protos` also generates `transport_pb2` from the xcl checkout.
- **Packaging and build:**
  - `make engine` builds the program into `xcl/_bin`;
  - wheels carry `xcl/_bin/xcl-core`, and the sdist excludes it;
  - `cffi` is now the optional `inprocess` extra;
  - the version moved to `0.5.0.dev0`.
- **Tests:**
  - `tests/engines.py` adds strict-mode engine skips (`XCL_TEST_STRICT`, `XCL_TEST_ENGINES`);
  - `subprocess_only` and `inprocess_only` markers;
  - engine fixtures that follow the selected route;
  - fake-engine unit tests (`tests/fake_engine.py`);
  - selection and helper unit tests;
  - process-lifecycle integration tests (`tests/integration/test_engine_process.py`).
- **CI.** `ci.yml` builds the program on every runner and runs the suite strictly. Linux x86-64 also runs it on the shared library. The Alpine jobs install Go from its official archive, so no C compiler is present.
- **Release.** `release.yml` and `musl-wheel.sh` build wheels around the verified `xcl-core` archives and check the installed program is executable. The install checks run the new `.github/scripts/install_check.py`, which applies and reads back an entity and checks the engine version, on all eight platforms, the musl ones in plain `python:3-alpine`.
- **README.** The README, which is also the PyPI page, describes the bundled engine, Alpine support, the two new errors, the subprocess forking rule and both development routes.

## Why

The shared library could not be loaded on musl, and it crashed on Windows x86-64, so the first release could not ship on every platform. Running the engine as a separate static program makes every platform behave the same and removes the C toolchain from the release.

## Deviations

- Transport-owned handles were added, so a dead or forked engine's configurations can never alias a new engine's.
- The musl wheel script now installs Go, which it previously lacked.
- Alpine jobs take Go from the official archive, because Alpine's `go` package pulls in gcc.
- The parity-fixture path test (`test_schema.py`) still reads `../xcl` rather than `XCL_SRC`. The release-hardening spec owns that fix.
- The PyPI publication and install checks are outstanding until v0.5.0 is tagged.
