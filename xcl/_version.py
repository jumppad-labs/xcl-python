"""The package version, and the version of the engine it was built for.

The two are separate: the package has its own version line, and bundles the
engine pinned in ``xcl-ref.txt``. A release workflow sets ``__version__``
from the xcl-python tag and ``__engine_version__`` from the pin, the bundled
engine is stamped with the pin, and the client compares the engine's version
with ``__engine_version__`` when the engine is first used.

Outside a release ``__engine_version__`` holds a development value, which
``make engine`` and ``make libxcl`` stamp on the engine they build, so a
development engine always passes the check.
"""

__version__ = "0.5.0.dev0"

__engine_version__ = "v0.0.0-dev"
