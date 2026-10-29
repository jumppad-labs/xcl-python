---
tags: [python, testing]
---

# Test module names must be unique across xcl-python's test directories

`tests/unit` and `tests/integration` are not packages (no `__init__.py`), so pytest imports each test module by its basename. Two files with the same name, such as `tests/unit/test_prettylog.py` and `tests/integration/test_prettylog.py`, stop the whole run at collection with "import file mismatch". Give engine-backed tests a distinct name (for example `test_prettylog_engine.py`). Running one directory alone hides the clash; only a full `pytest tests` run shows it.
