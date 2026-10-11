# Development targets. The package is built against a local checkout of xcl,
# XCL_SRC, from which the CoreService messages are generated and the engine
# is built into xcl/_lib. A release uses the signed engine archives from the
# xcl release instead, see .github/workflows/release.yml.
XCL_SRC ?= ../xcl
PYTHON ?= python3

# VERSION is the package version, from xcl/_version.py; a development
# engine is stamped with it so the package's version check passes
VERSION := $(shell $(PYTHON) -c "import re; print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('xcl/_version.py').read()).group(1))")

# protos generates the CoreService message classes from the xcl checkout's
# proto/ into xcl/_core. protoc writes them under xcl/core/v1, following the
# proto package, which would shadow this package's own name, so the files
# are moved; they import nothing but the protobuf runtime
protos:
	rm -rf build/protos && mkdir -p build/protos xcl/_core
	protoc -I "$(XCL_SRC)/proto" --python_out=build/protos --pyi_out=build/protos "$(XCL_SRC)/proto/xcl/core/v1/core.proto"
	cp build/protos/xcl/core/v1/core_pb2.py build/protos/xcl/core/v1/core_pb2.pyi xcl/_core/
	rm -rf build/protos

# libxcl builds the engine from the xcl checkout into xcl/_lib for the local
# platform, stamped with this package's version
LIBXCL_EXT := $(shell $(PYTHON) -c "import sys; print('dll' if sys.platform == 'win32' else 'dylib' if sys.platform == 'darwin' else 'so')")
libxcl:
	mkdir -p xcl/_lib
	$(MAKE) -C "$(XCL_SRC)" libxcl LIBXCL_VERSION=v$(VERSION) LIBXCL_OUT="$(CURDIR)/xcl/_lib/libxcl.$(LIBXCL_EXT)"

# plugins builds the fixture plugins the integration tests use into
# build/plugins
plugins:
	mkdir -p build/plugins
	cd "$(XCL_SRC)/bindings/libxcl" && go build -o "$(CURDIR)/build/plugins/xcl-plugin-slow" ./testdata/plugins/slow && go build -o "$(CURDIR)/build/plugins/xcl-plugin-recording" ./testdata/plugins/recording && go build -o "$(CURDIR)/build/plugins/parity" ./cmd/parity

# test runs the unit tests, which need no engine, and the integration tests,
# which need make libxcl and make plugins to have run
test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest tests/unit

.PHONY: protos libxcl plugins test test-unit
