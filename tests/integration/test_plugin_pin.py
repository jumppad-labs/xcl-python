"""Reading the pinned plugin release on the running interpreter.

``tests/plugins.toml`` is read with ``tomllib``; this checks the reader works
on whichever interpreter runs the suite, not what is pinned.
"""

from release_helpers import plugin_release


def test_plugin_release_reads_repository_and_version():
    repository, version = plugin_release()

    assert isinstance(repository, str) and repository
    assert isinstance(version, str) and version
