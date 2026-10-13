"""A plugin release that fails verification is refused, through the Python API.

A fake GitHub release API runs on a local thread, answering the two routes
the engine reads, the release by tag and each asset by id, from the real
files of the test plugin release installed once per session. Serving the
real files unaltered is the positive control; altering the checksums file,
or trusting a key other than the release key, must be refused with
:class:`xcl.PluginVerificationError` before the plugin is ever started.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import xcl
from release_helpers import (
    FIRST_ADDRESS,
    RELEASE_SIGNING_KEY_ID,
    TEST_PLUGIN_CONFIG,
    ReleaseFiles,
    github_registry,
    go_platform,
    installed_release,
    isolated_home,
    log_variables,
    plugin_release,
    release_files,
    trusted_key,
)

__all__ = ["installed_release", "isolated_home"]

pytestmark = pytest.mark.usefixtures("engine")


class FakeGitHub:
    """One release served the way GitHub's REST API serves it.

    ``GET /repos/<owner>/<repo>/releases/tags/<tag>`` answers the release
    JSON whose assets point back at this server, and
    ``GET /repos/<owner>/<repo>/releases/assets/<id>`` answers an asset's bytes
    to a request accepting ``application/octet-stream``, and its JSON
    otherwise, as GitHub does.
    """

    def __init__(self, repository: str, tag: str, assets: dict[str, bytes]) -> None:
        self.repository = repository
        self.tag = tag
        self.assets = list(assets.items())
        self.requests: list[str] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - the stdlib name
                pass

            def do_GET(self) -> None:
                fake.requests.append(self.path)
                fake.answer(self)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def asset_url(self, asset_id: int) -> str:
        return f"{self.url}/repos/{self.repository}/releases/assets/{asset_id}"

    def answer(self, request: BaseHTTPRequestHandler) -> None:
        parts = request.path.strip("/").split("/")
        if len(parts) == 6 and parts[0] == "repos" and parts[3:5] == ["releases", "tags"]:
            if f"{parts[1]}/{parts[2]}" != self.repository or parts[5] != self.tag:
                return self.not_found(request)
            release = {
                "tag_name": self.tag,
                "draft": False,
                "assets": [
                    {"id": index + 1, "name": name, "url": self.asset_url(index + 1), "content_type": "application/octet-stream"}
                    for index, (name, _) in enumerate(self.assets)
                ],
            }
            return self.respond(request, "application/json", json.dumps(release).encode())

        if len(parts) == 6 and parts[0] == "repos" and parts[3:5] == ["releases", "assets"]:
            if f"{parts[1]}/{parts[2]}" != self.repository or not parts[5].isdigit():
                return self.not_found(request)
            index = int(parts[5]) - 1
            if not 0 <= index < len(self.assets):
                return self.not_found(request)
            name, data = self.assets[index]
            if request.headers.get("Accept") != "application/octet-stream":
                return self.respond(request, "application/json", json.dumps({"id": index + 1, "name": name}).encode())
            return self.respond(request, "application/octet-stream", data)

        return self.not_found(request)

    @staticmethod
    def respond(request: BaseHTTPRequestHandler, content_type: str, body: bytes) -> None:
        request.send_response(200)
        request.send_header("Content-Type", content_type)
        request.send_header("Content-Length", str(len(body)))
        request.end_headers()
        request.wfile.write(body)

    @staticmethod
    def not_found(request: BaseHTTPRequestHandler) -> None:
        body = b'{"message":"Not Found"}'
        request.send_response(404)
        request.send_header("Content-Type", "application/json")
        request.send_header("Content-Length", str(len(body)))
        request.end_headers()
        request.wfile.write(body)


def real_assets(installed: ReleaseFiles) -> dict[str, bytes]:
    """The release's archive, checksums file and signature as installed."""
    return {
        installed.archive_name: installed.archive.read_bytes(),
        installed.checksums_name: installed.checksums.read_bytes(),
        installed.signature_name: installed.signature.read_bytes(),
    }


def tampered_checksums(installed: ReleaseFiles) -> bytes:
    """The real checksums file with one hex digit of this platform's archive line changed."""
    lines = installed.checksums.read_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.endswith(installed.archive_name))
    first = lines[index][0]
    lines[index] = ("1" if first == "0" else "0") + lines[index][1:]
    return ("\n".join(lines) + "\n").encode()


@pytest.fixture
def fake_github(installed_release: ReleaseFiles):
    """A factory of fake GitHub servers for the pinned release, closed after the test."""
    repository, version = plugin_release()
    servers: list[FakeGitHub] = []

    def serve(assets: dict[str, bytes]) -> FakeGitHub:
        server = FakeGitHub(repository, version, assets)
        servers.append(server)
        return server

    yield serve
    for server in servers:
        server.close()


@pytest.fixture(scope="session")
def other_key(tmp_path_factory: pytest.TempPathFactory) -> str:
    """An armoured public key that did not sign the release, generated with gpg."""
    if shutil.which("gpg") is None:
        pytest.skip("gpg is not on PATH to generate a key the release was not signed with")
    home = tmp_path_factory.mktemp("gnupg")
    home.chmod(0o700)
    gpg = ["gpg", "--batch", "--homedir", str(home), "--pinentry-mode", "loopback", "--passphrase", ""]
    generate = subprocess.run(
        gpg + ["--quick-generate-key", "xcl python tests (not the release key)", "default", "default", "never"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if generate.returncode != 0:
        pytest.skip(f"gpg could not generate a key: {generate.stderr.strip()}")
    export = subprocess.run(gpg + ["--armor", "--export"], capture_output=True, text=True, timeout=60, check=True)
    assert "BEGIN PGP PUBLIC KEY BLOCK" in export.stdout
    return export.stdout


def test_tampered_release_refused(tmp_path: Path, installed_release: ReleaseFiles, fake_github):
    assets = real_assets(installed_release)
    assets[installed_release.checksums_name] = tampered_checksums(installed_release)
    fake = fake_github(assets)
    cache_dir = tmp_path / "cache"
    registry = github_registry(cache_dir, trusted_keys=[trusted_key()], api_url=fake.url)

    with xcl.Config(registries=[registry], state_path=tmp_path / "state", variables=log_variables(tmp_path / "ops.jsonl")) as c:
        with pytest.raises(xcl.PluginVerificationError) as raised:
            c.validate(TEST_PLUGIN_CONFIG)

    repository, version = plugin_release()
    goos, goarch = go_platform()
    assert raised.value.code == "plugin_verification"
    assert raised.value.details["repository"] == repository
    assert raised.value.details["version"] == version
    assert raised.value.details["platform"] == f"{goos}/{goarch}"
    assert installed_release.signature_name in str(raised.value)
    assert "does not verify against any trusted key" in str(raised.value)
    assert fake.requests[0] == f"/repos/{repository}/releases/tags/{version}"
    assert len(fake.requests) == 4, fake.requests
    assert not release_files(cache_dir, repository, version).entry.exists(), "a refused release must not be cached"


def test_untrusted_key_refused(tmp_path: Path, installed_release: ReleaseFiles, fake_github, other_key: str):
    fake = fake_github(real_assets(installed_release))
    cache_dir = tmp_path / "cache"
    registry = github_registry(cache_dir, trusted_keys=[other_key], api_url=fake.url)

    with xcl.Config(registries=[registry], state_path=tmp_path / "state", variables=log_variables(tmp_path / "ops.jsonl")) as c:
        with pytest.raises(xcl.PluginVerificationError) as raised:
            c.validate(TEST_PLUGIN_CONFIG)

    repository, version = plugin_release()
    assert raised.value.code == "plugin_verification"
    assert raised.value.details["repository"] == repository
    assert "does not verify against any trusted key" in str(raised.value)
    assert not release_files(cache_dir, repository, version).entry.exists(), "a refused release must not be cached"


def test_no_trusted_keys_installs_unsigned_release(tmp_path: Path, installed_release: ReleaseFiles, fake_github):
    # the engine checks signatures only when keys are trusted, so a release
    # without a signature installs when none are given
    assets = real_assets(installed_release)
    del assets[installed_release.signature_name]
    fake = fake_github(assets)
    cache_dir = tmp_path / "cache"
    registry = github_registry(cache_dir, trusted_keys=[], api_url=fake.url)

    with xcl.Config(registries=[registry], state_path=tmp_path / "state", variables=log_variables(tmp_path / "ops.jsonl")) as c:
        c.validate(TEST_PLUGIN_CONFIG)

    repository, version = plugin_release()
    installed = release_files(cache_dir, repository, version)
    assert installed.binary.is_file()
    assert installed.archive.is_file()
    assert installed.checksums.is_file()
    assert not installed.signature.exists()
    assert fake.requests[0] == f"/repos/{repository}/releases/tags/{version}"


def test_fake_api_serves_valid_release_installs(tmp_path: Path, installed_release: ReleaseFiles, fake_github):
    fake = fake_github(real_assets(installed_release))
    cache_dir = tmp_path / "cache"
    registry = github_registry(cache_dir, trusted_keys=[trusted_key()], api_url=fake.url)

    with xcl.Config(registries=[registry], state_path=tmp_path / "state", variables=log_variables(tmp_path / "ops.jsonl")) as c:
        try:
            c.apply(TEST_PLUGIN_CONFIG)
            first = c.find(None, FIRST_ADDRESS)
        finally:
            c.destroy()
            remaining = c.entity_count()

    repository, version = plugin_release()
    installed = release_files(cache_dir, repository, version)
    assert installed.binary.read_bytes() == installed_release.binary.read_bytes()
    assert installed.signature.is_file()
    assert fake.requests[0] == f"/repos/{repository}/releases/tags/{version}"
    assert sorted(fake.requests[1:]) == sorted(fake.asset_url(i + 1).removeprefix(fake.url) for i in range(3))
    assert isinstance(first, xcl.Entity)
    assert first.output == "first-one"
    assert remaining == 0


def test_untrusted_key_refusal_names_signing_key(tmp_path: Path, installed_release: ReleaseFiles, fake_github, other_key: str):
    fake = fake_github(real_assets(installed_release))
    registry = github_registry(tmp_path / "cache", trusted_keys=[other_key], api_url=fake.url)

    with xcl.Config(registries=[registry], state_path=tmp_path / "state", variables=log_variables(tmp_path / "ops.jsonl")) as c:
        with pytest.raises(xcl.PluginVerificationError) as raised:
            c.validate(TEST_PLUGIN_CONFIG)

    assert f"signed by key {RELEASE_SIGNING_KEY_ID}, which is not trusted" in str(raised.value)
