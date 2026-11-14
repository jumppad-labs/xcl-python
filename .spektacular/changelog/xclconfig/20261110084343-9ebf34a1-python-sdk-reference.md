---
created_date: "2026-11-13"
document_status: draft
project: xclconfig
spec: 20261110084343-9ebf34a1-python-sdk-reference
plan: 20261110084343-9ebf34a1-python-sdk-reference
---

# The package documents itself, and each release publishes its reference

Every public name and member of `xcl-lang` now has a doc comment. The clients, the registries and the module functions say what each parameter is, what they return and what they raise. A pull request that adds an undocumented public name fails its checks. Each release also publishes the package's API reference with its GitHub release, which xcl.dev renders at `/reference/python/`.

> Derived from project xcl, spec/plan 20261110084343-9ebf34a1-python-sdk-reference. See the project-level record for the full feature.

## What changed

- `.github/scripts/api_reference.py`: reads the package statically with Griffe. `--check` lists every public name or member without a doc comment, or with invalid markup. `--out` writes the reference JSON. It has 32 tests beside it in `test_api_reference.py`. Griffe 2.4.1 and docutils 0.23 are pinned in `requirements-docs.txt` and are never dependencies of `xcl-lang`.
- Doc comments only, in `xcl/`: the seven constants (`__version__`, `UNKNOWN`, the five `xcl.highlight` formats), and field lists on `Config`, `aio.Config`, `LocalRegistry`, `GitHubRegistry` and the module functions. No code changed.
- `test.yml`: a required `check-docs` job. `Makefile`: `make check-docs`. `tests/unit/test_docstrings.py` was removed, because the check covers more, including constants.
- `release.yml`: a `reference` job that `publish` needs, so bad doc comments stop a release before PyPI. The reference data is attached to the GitHub release, and a `dispatch-website` job tells `xcl-website` the tag.
- `README.md`: the reference link is now `https://xcl.dev/reference/python/`, and the releases section says a release publishes the reference.

## Why

The documentation site's Python reference is generated from this package, so the package is the one place that defines what is public and holds every doc comment. Failing the checks on a missing doc comment keeps the reference complete.
