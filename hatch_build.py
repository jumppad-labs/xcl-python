"""Build hook that tags a wheel for the platform whose engine it bundles.

The package has no compiled extension of its own: it loads the engine, a Go
shared library, through cffi in ABI mode. One wheel therefore serves every
CPython version on a platform, and is tagged ``py3-none-<platform>``, with the
platform tag given through ``XCL_WHEEL_PLATFORM`` (for example
``manylinux_2_28_x86_64`` or ``macosx_11_0_arm64``). Without it the wheel is
tagged for the machine building it, through hatchling's inference, which is
what a development install gets.
"""

from __future__ import annotations

import os
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class XCLWheelHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != "wheel":
            return

        build_data["pure_python"] = False

        platform = os.environ.get("XCL_WHEEL_PLATFORM")
        if platform:
            build_data["tag"] = f"py3-none-{platform}"
        else:
            build_data["infer_tag"] = True
