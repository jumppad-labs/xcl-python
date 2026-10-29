---
tags: [windows, ci, testing, line-endings, paths]
---

# Windows CI checks files out with CRLF and names files with backslashes

The GitHub Windows runners check out with `core.autocrlf` on, and neither xcl nor xcl-python has a `.gitattributes`. So every text file in the `xcl-src` checkout (including xcl's byte-exact `highlight/testdata/reference` outputs) has CRLF line ends there. A test that compares formatter output, which always uses `\n`, with a file read as bytes must turn CRLF back into LF (`read_reference` in `tests/unit/test_highlight_reference.py`). The reference files contain no CR of their own, so this loses nothing.

The engine prints file names with the platform's separator, so error reports read `<fixture>\main.xcl` on Windows. Build expected paths with `os.sep`, or compare against the Go parity program's output, rather than writing `/` into the expected text.
