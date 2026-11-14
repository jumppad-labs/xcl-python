---
tags: [griffe, docs, api-reference]
---

# `griffe.load` finds a package in the current directory before `search_paths`

`griffe.load("xcl", search_paths=[source])` first tries the name as a path relative to the current
directory, so running from a checkout reads that checkout's `xcl/` and silently ignores `search_paths`. A test over
a fixture package then passes or fails against the real package. Pass `try_relative_path=False`, as
`.github/scripts/api_reference.py` does.
