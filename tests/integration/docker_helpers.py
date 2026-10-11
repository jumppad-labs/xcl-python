"""Shared helpers and fixtures for the tests that use the Docker example plugin.

The plugin is a Go binary published as a signed GitHub release of
jumppad-labs/xcl-plugin-docker, pinned in ``tests/plugins.toml``. It is
installed once per session, through ``xcl.GitHubRegistry`` into a temporary
cache, and the tests then start it from the cache entry, by path, by
directory, or again through the registry.

The fixtures here are imported into the test modules that need them; the
session-scoped ones memoise their result so importing them into two modules
still installs and probes once.
"""

from __future__ import annotations

import dataclasses
import http.client
import os
import platform
import shutil
import socket
import subprocess
import tomllib
import urllib.parse
from pathlib import Path
from typing import Optional

import pytest

import xcl

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
PLUGINS_TOML = TESTS / "plugins.toml"
TRUSTED_KEY_PATH = TESTS / "keys" / "jumppad-labs.asc"
DOCKER_CONFIG = os.path.abspath(Path(__file__).resolve().parent / "configs" / "docker" / "main.xcl")

NETWORK_ADDRESS = "docker.network.xcl_python_test"
CONTAINER_ADDRESS = "docker.container.xcl_python_test"
NETWORK_SUBNET = "10.74.0.0/24"
CONTAINER_IMAGE = "nginx:1.27-alpine"

_GOARCH = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def plugin_release() -> tuple[str, str]:
    """The repository and version of the Docker plugin release the tests install."""
    with PLUGINS_TOML.open("rb") as f:
        pinned = tomllib.load(f)["docker"]
    return pinned["repository"], pinned["version"]


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
    """A registry installing the pinned Docker plugin release into ``cache_dir``."""
    registry = xcl.GitHubRegistry(cache_dir=cache_dir, trusted_keys=trusted_keys, api_url=api_url)
    registry.register_plugin(*plugin_release())
    return registry


DEFAULT_DOCKER_HOST = "unix:///var/run/docker.sock"


class _UnixHTTPConnection(http.client.HTTPConnection):
    """An HTTP connection over a Unix socket, as the Docker client's is."""

    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


def daemon_unreachable(timeout: float = 5.0) -> Optional[str]:
    """Why the Docker daemon the plugin will dial does not answer, or ``None`` when it does.

    The plugin's client reads ``DOCKER_HOST``, so this pings the same endpoint
    with ``GET /_ping`` rather than trusting the ``docker`` CLI, which may
    resolve the daemon some other way (podman's shim answers ``docker info``
    without the socket).
    """
    host = os.environ.get("DOCKER_HOST") or DEFAULT_DOCKER_HOST
    parsed = urllib.parse.urlsplit(host)
    if parsed.scheme == "unix":
        connection: http.client.HTTPConnection = _UnixHTTPConnection(parsed.path, timeout)
    elif parsed.scheme in ("tcp", "http"):
        connection = http.client.HTTPConnection(parsed.hostname or "localhost", parsed.port or 2375, timeout=timeout)
    else:
        return f"DOCKER_HOST {host!r} is not a unix:// or tcp:// endpoint"
    try:
        connection.request("GET", "/_ping")
        response = connection.getresponse()
        body = response.read()
        if response.status != 200:
            return f"the Docker daemon at {host} answered {response.status} to /_ping: {body[:80]!r}"
    except OSError as error:
        return f"cannot connect to the Docker daemon at {host}: {error}"
    finally:
        connection.close()
    return None


def docker_unavailable() -> Optional[str]:
    """Why Docker cannot be used on this machine, or ``None`` when it can."""
    reason = daemon_unreachable()
    if reason is not None:
        return reason
    if shutil.which("docker") is None:
        return "docker is not on PATH"
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return "docker info did not answer within 20s"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return "docker info failed: " + (detail[-1] if detail else f"exit status {result.returncode}")
    return None


_memo: dict[str, object] = {}


@pytest.fixture(scope="session")
def require_docker() -> None:
    """Skips the test when the Docker daemon is not reachable."""
    if "docker" not in _memo:
        _memo["docker"] = docker_unavailable()
    reason = _memo["docker"]
    if reason is not None:
        pytest.skip(f"the Docker plugin tests need a Docker daemon: {reason}")


@pytest.fixture(scope="session")
def installed_release(tmp_path_factory: pytest.TempPathFactory) -> ReleaseFiles:
    """The Docker plugin release installed once, from GitHub, into a session cache.

    Validating a configuration starts the plugin, which installs and verifies
    the release, without touching Docker.
    """
    if "release" in _memo:
        return _memo["release"]  # type: ignore[return-value]

    cache_dir = tmp_path_factory.mktemp("plugin-cache")
    home = tmp_path_factory.mktemp("home")
    repository, version = plugin_release()
    files = release_files(cache_dir, repository, version)

    previous_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        registry = github_registry(cache_dir, trusted_keys=[trusted_key()])
        with xcl.Config(registries=[registry], state_path=tmp_path_factory.mktemp("state")) as c:
            c.validate(DOCKER_CONFIG)
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
