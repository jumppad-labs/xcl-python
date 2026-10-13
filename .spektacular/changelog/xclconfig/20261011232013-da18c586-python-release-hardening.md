---
created_date: "2026-10-13"
document_status: draft
project: xclconfig
spec: 20261011232013-da18c586-python-release-hardening
plan: 20261011232013-da18c586-python-release-hardening
---

# A test suite that runs everywhere, without Docker

The xcl-python test suite now runs on every supported CPython from 3.10 up, on Linux, macOS and Windows, from any checkout layout. Its end-to-end and GitHub-registry tests no longer need Docker. Instead they install a small, signed test plugin from its GitHub release and exercise the real download, checksum and signature path. In CI, a job that is missing something it should have now fails rather than quietly skipping tests, so a green run means the whole suite ran. The installed package itself is unchanged.

> Derived from project xcl, spec/plan 20261011232013-da18c586-python-release-hardening. See the project-level record for the full feature.

## What changed in this repo

**Python 3.10**
- `pyproject.toml` adds `tomli` to the `test` extra for Python < 3.11 only.
- The release helpers read `tests/plugins.toml` with `tomllib`, or with `tomli` on 3.10.

**Finding the xcl sources**
- The new `tests/xcl_source.py` is the one place the tests find the xcl sources: `XCL_SRC`, else `../xcl`.
- The `xcl_src` fixture in `tests/conftest.py` serves every test that needs them. The schema test, both conftests, the parity type tests and the engine-version test use it.
- `xcl_source.skip` is the single entry point for harness skips. It turns a skip into a failure under `XCL_TEST_STRICT=1`, and leaves a missing engine to `engines.skip_missing_engine`.

**Windows**
- `make plugins` builds the fixture plugins and `parity` with `.exe` on Windows, and the fixtures look them up by the same names.
- The keyboard-interrupt test sends Ctrl-Break to a new process group on Windows.

**Tests that failed on slow or unusual runners**
- The thread-stall test compares the apply against an idle baseline measured on the same machine.
- The fake engine kills its interpreter stub before itself, so a killed engine reads as SIGKILL on macOS too.

**The test plugin in place of Docker**
- `tests/plugins.toml` pins `jumppad-labs/xcl-plugin-test` `v0.1.0`.
- `docker_helpers.py` became `release_helpers.py`, with no Docker probe.
- `test_docker_plugin.py` became `test_test_plugin.py`. It covers:
  - the registry, path and directory start paths;
  - generic entity reads;
  - the recorded operation order of linked items;
  - the computed output;
  - the secret redacted in lookups and events, and masked in state.
- The tamper tests install the test plugin, and a new test checks that the untrusted-key refusal names the release signing key.

**CI and documentation**
- `ci.yml` passes `GITHUB_TOKEN`, runs `pytest -rs`, and installs `gnupg` in Alpine. Its comments no longer describe Docker.
- The README's Development section explains `XCL_SRC`, the test plugin and strict mode.

## Why

The first attempt to publish xcl-lang showed that the suite could not be trusted as a release gate:
- it stopped at collection on 3.10;
- it failed wherever xcl was not checked out next to it;
- it could not start fixture plugins or interrupt an apply on Windows;
- it skipped its plugin and registry tests wherever no Docker daemon was reachable.

## Still to do

The pinned `v0.1.0` of jumppad-labs/xcl-plugin-test must be published from the new plugin before these tests can install it; the release that exists today was made from the template. CI also needs an xcl ref that includes the key-naming change.
