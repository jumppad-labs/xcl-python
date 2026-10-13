"""Shared helpers and fixtures for the tests that install the pinned plugin release.

The plugin is the test plugin, a Go binary published as a signed GitHub
release of jumppad-labs/xcl-plugin-test and pinned in ``tests/plugins.toml``.
Its ``test "item"`` block records each operation to a log the configuration
names, and needs no outside service. It is installed once per session,
through ``xcl.GitHubRegistry`` into a temporary cache, and the tests then
start it from the cache entry, by path, by directory, or again through the
registry.

The fixtures here are imported into the test modules that need them; the
session-scoped one memoises its result so importing it into two modules still
installs once.
"""

from __future__ import annotations

import dataclasses
import os
import platform
from pathlib import Path
from typing import Any, Optional

import pytest

import xcl
import xcl_source

import tomllib

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
PLUGINS_TOML = TESTS / "plugins.toml"
TRUSTED_KEY_PATH = TESTS / "keys" / "jumppad-labs.asc"
TEST_PLUGIN_CONFIG = os.path.abspath(Path(__file__).resolve().parent / "configs" / "test_plugin" / "main.xcl")

# the long key ID of the jumppad-labs release key, tests/keys/jumppad-labs.asc,
# which signs the plugin release's checksums file with its primary key: the
# issuer of the published .sig, as `gpg --list-packets <sig>` prints it
# (keyid F775DA00AFD4B502, fingerprint 15BDA684...F775DA00AFD4B502)
RELEASE_SIGNING_KEY_ID = "F775DA00AFD4B502"

# the two items TEST_PLUGIN_CONFIG declares; second takes first's output as
# its input, so it depends on first
FIRST_ADDRESS = "test.item.first"
SECOND_ADDRESS = "test.item.second"

_GOARCH = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def plugin_release() -> tuple[str, str]:
    """The repository and version of the plugin release the tests install."""
    with PLUGINS_TOML.open("rb") as f:
        pinned = tomllib.load(f)["test"]
    return pinned["repository"], pinned["version"]


def log_variables(log: Path) -> dict[str, Any]:
    """The variables TEST_PLUGIN_CONFIG needs: the operation log its items record to."""
    return {"log": str(log)}


def trusted_key() -> str:
    """The armoured public key the release is signed with."""
    return TRUSTED_KEY_PATH.read_text()


def go_platform() -> tuple[str, str]:
    """The host as the engine names it, GOOS and GOARCH."""
    goos = platform.system().lower()
    machine = platform.machine().lower()
    if machine not in _GOARCH:
        pytest.skip(f"no plugin build is published for the {machine} architecture")
    return goos, _GOARCH[machine]


@dataclasses.dataclass(frozen=True)
class ReleaseFiles:
    """Where an installed release lives in a cache, and what its files are called."""

    cache_dir: Path
    repository: str
    version: str
    entry: Path
    binary: Path
    archive_name: str
    checksums_name: str
    signature_name: str

    @property
    def archive(self) -> Path:
        return self.entry / self.archive_name

    @property
    def checksums(self) -> Path:
        return self.entry / self.checksums_name

    @property
    def signature(self) -> Path:
        return self.entry / self.signature_name


def release_files(cache_dir: Path, repository: str, version: str) -> ReleaseFiles:
    """The cache entry of ``repository`` at ``version`` under ``cache_dir`` for this host."""
    goos, goarch = go_platform()
    owner, name = repository.split("/", 1)
    bare_version = version.removeprefix("v")
    entry = cache_dir / "github.com" / owner / name / version / f"{goos}_{goarch}"
    extension = "zip" if goos == "windows" else "tar.gz"
    binary = name + (".exe" if goos == "windows" else "")
    return ReleaseFiles(
        cache_dir=cache_dir,
        repository=repository,
        version=version,
        entry=entry,
        binary=entry / binary,
        archive_name=f"{name}_{bare_version}_{goos}_{goarch}.{extension}",
        checksums_name=f"{name}_{bare_version}_checksums.txt",
        signature_name=f"{name}_{bare_version}_checksums.txt.sig",
    )


def github_registry(cache_dir: Path, *, trusted_keys: list[str], api_url: Optional[str] = None) -> xcl.GitHubRegistry:
    """A registry installing the pinned plugin release into ``cache_dir``."""
    registry = xcl.GitHubRegistry(cache_dir=cache_dir, trusted_keys=trusted_keys, api_url=api_url)
    registry.register_plugin(*plugin_release())
    return registry


_memo: dict[str, object] = {}


@pytest.fixture(scope="session")
def installed_release(tmp_path_factory: pytest.TempPathFactory) -> ReleaseFiles:
    """The plugin release installed once, from GitHub, into a session cache.

    Validating a configuration starts the plugin, which installs and verifies
    the release. A release that cannot be installed (no network, or no such
    release) skips the tests that need it, and fails them in strict mode.
    """
    if "release" in _memo:
        return _memo["release"]  # type: ignore[return-value]

    cache_dir = tmp_path_factory.mktemp("plugin-cache")
    home = tmp_path_factory.mktemp("home")
    log = tmp_path_factory.mktemp("install") / "ops.jsonl"
    repository, version = plugin_release()
    files = release_files(cache_dir, repository, version)

    previous_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        registry = github_registry(cache_dir, trusted_keys=[trusted_key()])
        with xcl.Config(registries=[registry], state_path=tmp_path_factory.mktemp("state"), variables=log_variables(log)) as c:
            c.validate(TEST_PLUGIN_CONFIG)
    except xcl.Error as error:
        xcl_source.skip(f"the plugin release {repository} {version} could not be installed from GitHub: {error}")
    finally:
        if previous_home is None:
            del os.environ["HOME"]
        else:
            os.environ["HOME"] = previous_home

    assert files.binary.is_file(), f"the release was not installed at {files.binary}"
    _memo["release"] = files
    return files


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Plugins are cached under HOME by default, so every test gets its own."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
