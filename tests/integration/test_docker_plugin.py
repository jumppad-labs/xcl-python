"""Go plugins are usable from Python: the Docker example plugin, end to end.

The plugin is installed once per session from its signed GitHub release
(``installed_release``) and then started three ways: through the GitHub
registry again, from its binary's path, and from the directory the binary is
in. Each test applies ``configs/docker/main.xcl``, a network and an nginx
container, reads the entities back as generic :class:`xcl.Entity` values,
and always destroys what it created so nothing is left in Docker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import xcl
from docker_helpers import (
    CONTAINER_ADDRESS,
    CONTAINER_IMAGE,
    DOCKER_CONFIG,
    NETWORK_ADDRESS,
    NETWORK_SUBNET,
    ReleaseFiles,
    github_registry,
    installed_release,
    isolated_home,
    require_docker,
    trusted_key,
)

__all__ = ["installed_release", "isolated_home", "require_docker"]

pytestmark = pytest.mark.usefixtures("engine", "require_docker")


def assert_network_and_container(network: object, container: object) -> None:
    assert isinstance(network, xcl.Entity)
    assert network.address == NETWORK_ADDRESS
    assert network.subnet == NETWORK_SUBNET
    assert network.docker_id, "the plugin did not record the network's Docker id"

    assert isinstance(container, xcl.Entity)
    assert container.address == CONTAINER_ADDRESS
    assert container.image == CONTAINER_IMAGE
    assert container.ip_address, "the plugin did not record the container's address"
    assert container.docker_id, "the plugin did not record the container's Docker id"


def test_docker_plugin_from_github_registry(tmp_path: Path, installed_release: ReleaseFiles):
    registry = github_registry(installed_release.cache_dir, trusted_keys=[trusted_key()])

    with xcl.Config(registries=[registry], state_path=tmp_path / "state") as c:
        try:
            c.apply(DOCKER_CONFIG)
            applied = c.entity_count()
            network = c.find(None, NETWORK_ADDRESS)
            container = c.find(None, CONTAINER_ADDRESS)
            containers = c.find_by_type(None, "docker", "container")
        finally:
            c.destroy()
            remaining = c.entity_count()

    assert applied == 2
    assert_network_and_container(network, container)
    assert [e.address for e in containers] == [CONTAINER_ADDRESS]
    assert remaining == 0


def test_docker_plugin_from_path(tmp_path: Path, installed_release: ReleaseFiles):
    registry = xcl.LocalRegistry()
    registry.register_external_plugin(installed_release.binary)

    with xcl.Config(registries=[registry], state_path=tmp_path / "state") as c:
        try:
            c.apply(DOCKER_CONFIG)
            network = c.find(None, NETWORK_ADDRESS)
            container = c.find(None, CONTAINER_ADDRESS)
        finally:
            c.destroy()
            remaining = c.entity_count()

    assert_network_and_container(network, container)
    assert remaining == 0


def test_docker_plugin_from_directory(tmp_path: Path, installed_release: ReleaseFiles):
    # the cache entry holds the binary beside the release's archive,
    # checksums file and signature, which are named xcl-plugin-docker_... but
    # are not executable, so the default xcl-plugin-* pattern starts only
    # the binary
    sidecars = sorted(p.name for p in installed_release.entry.iterdir() if p != installed_release.binary)
    assert sidecars == sorted(
        [installed_release.archive_name, installed_release.checksums_name, installed_release.signature_name]
    )

    registry = xcl.LocalRegistry()
    registry.register_plugin_directory(installed_release.entry)

    with xcl.Config(registries=[registry], state_path=tmp_path / "state") as c:
        try:
            c.apply(DOCKER_CONFIG)
            network = c.find(None, NETWORK_ADDRESS)
            container = c.find(None, CONTAINER_ADDRESS)
        finally:
            c.destroy()
            remaining = c.entity_count()

    assert_network_and_container(network, container)
    assert remaining == 0


def test_plugin_entities_readable_generically(tmp_path: Path, installed_release: ReleaseFiles):
    registry = xcl.LocalRegistry()
    registry.register_external_plugin(installed_release.binary)

    with xcl.Config(registries=[registry], state_path=tmp_path / "state") as c:
        try:
            c.apply(DOCKER_CONFIG)
            network = c.find(None, NETWORK_ADDRESS)
            container = c.find(None, CONTAINER_ADDRESS)
            everything = c.entities()
        finally:
            c.destroy()

    assert isinstance(network, xcl.Entity)
    assert network.address == NETWORK_ADDRESS
    assert network.subnet == NETWORK_SUBNET
    assert network["subnet"] == network.subnet
    assert "subnet" in network
    assert set(network) >= {"meta", "subnet", "docker_id"}
    assert network.to_dict()["subnet"] == NETWORK_SUBNET
    with pytest.raises(AttributeError):
        network.no_such_attribute
    with pytest.raises(KeyError):
        network["no_such_attribute"]

    assert isinstance(network.meta, xcl.Meta)
    assert network.meta.id == NETWORK_ADDRESS
    assert network.meta.name == "xcl_python_test"
    assert network.meta.type == "docker"
    assert network.meta.subtype == "network"
    assert network.meta.file == DOCKER_CONFIG
    assert network.meta.line == 4
    assert network.meta.status == "created"

    assert container.meta.type == "docker"
    assert container.meta.subtype == "container"
    assert container.network == [{"name": "xcl_python_test", "aliases": ["python"]}]
    assert container.meta.references == {"network[0].name": f"{NETWORK_ADDRESS}.meta.name"}
    assert f"{NETWORK_ADDRESS}.meta.name" in container.meta.links

    assert all(isinstance(e, xcl.Entity) for e in everything)
    assert sorted(e.address for e in everything) == [CONTAINER_ADDRESS, NETWORK_ADDRESS]
