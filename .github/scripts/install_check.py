"""The release's install check: the published package, from PyPI, does real work.

Run by the install-check jobs of release.yml on every platform, after
``pip install xcl-lang==<version>`` with no Go or C compiler on the path (the
musl ones in a plain python:3-alpine image). It registers a plain dataclass
by name as the ``settings`` type of the README's getting started, applies a
configuration, reads the entity back, closes the configuration, and checks
the engine reports the engine tag in ``ENGINE_TAG`` (``TAG`` when it is not
set). It needs nothing but the standard
library and xcl.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import xcl


@dataclass
class Settings:
    image: str
    replicas: int = 1


def main() -> None:
    tag = os.environ.get("ENGINE_TAG") or os.environ["TAG"]

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config_dir = root / "config"
        config_dir.mkdir()
        (config_dir / "main.xcl").write_text('settings "web" {\n  image = "nginx"\n}\n')

        local = xcl.LocalRegistry()
        local.register_type(Settings, "settings")

        with xcl.Config(registries=[local], state_path=str(root / ".xcl")) as cfg:
            cfg.apply(str(config_dir))
            settings = cfg.find(Settings, "settings.web")
            assert settings.image == "nginx", settings.image
            assert settings.replicas == 1, settings.replicas

    version = xcl.engine_version()
    print(f"applied and read back settings.web; engine {version}")
    assert version == tag, f"the engine reports {version}, expected {tag}"


if __name__ == "__main__":
    main()
