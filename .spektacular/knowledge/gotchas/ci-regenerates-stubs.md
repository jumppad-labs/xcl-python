---
tags: [python, ci, releases, proto]
---

# Engine bumps break when a protocol field is removed

xcl-python's CI regenerates the protocol stubs from the pinned xcl checkout before testing. Once an xcl release reserves or removes a protocol field, the automated engine-bump PR for that release fails, because the Python code still using the field no longer matches the regenerated stubs. The Python change that drops the field has to land in the same change as the pin bump: push it onto the engine-bump PR or replace that PR. Plan releases so an unrelated xcl change that relies on the automatic bump is not released together with a field removal.
