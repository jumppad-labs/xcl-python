---
tags: [release, ci, pypi, install-check, readme]
---

# The release's install checks run after the PyPI publish, so a failure does not stop a release

In `release.yml`, the `install-check` and `install-check-musl` jobs need `publish`: they install `xcl-lang==<version>` from PyPI with no compiler on the path and run `.github/scripts/install_check.py`. By then the version is already on PyPI and the `GitHub release` job (which does not wait for them) has run. A red install check means the published package, or the check itself, is broken. It never means the release was held back. Check these jobs after every release, as well as the release itself.

They failed on every release from v0.10.0 to v0.14.0 without anyone noticing. The script copies the README's getting started, whose `Settings` dataclass had no `meta` field and no label field. Since engine v0.9.0 such a type is a singleton, so its labelled `settings "web" { … }` block is refused with "settings takes no labels". Any example class written with a label needs `meta: xcl.Meta | None = None`, or a label field.
