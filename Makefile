# Development targets. The package is built against a local checkout of xcl,
# XCL_SRC, from which the CoreService messages are generated and the engine
# program is built into xcl/_bin. A release uses the signed engine archives
# from the xcl release instead, see .github/workflows/release.yml.
XCL_SRC ?= ../xcl
PYTHON ?= python3

# VERSION is the package version, from xcl/_version.py; a development
# engine is stamped with it so the package's version check passes
VERSION := $(shell $(PYTHON) -c "import re; print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('xcl/_version.py').read()).group(1))")

# protos generates the CoreService message classes and the frame messages of
# the engine program's transport from the xcl checkout's proto/ into
# xcl/_core. protoc writes them under xcl/core/v1, following the proto
# package, which would shadow this package's own name, so the files are
# moved; they import nothing but the protobuf runtime
protos:
	rm -rf build/protos && mkdir -p build/protos xcl/_core
	protoc -I "$(XCL_SRC)/proto" --python_out=build/protos --pyi_out=build/protos "$(XCL_SRC)/proto/xcl/core/v1/core.proto" "$(XCL_SRC)/proto/xcl/core/v1/transport.proto"
	cp build/protos/xcl/core/v1/core_pb2.py build/protos/xcl/core/v1/core_pb2.pyi build/protos/xcl/core/v1/transport_pb2.py build/protos/xcl/core/v1/transport_pb2.pyi xcl/_core/
	rm -rf build/protos

# engine builds the engine program, xcl-core, from the xcl checkout into
# xcl/_bin for the local platform, stamped with this package's version. It
# needs Go and no C compiler; it is the engine the package runs by default
EXE := $(shell $(PYTHON) -c "import sys; print('.exe' if sys.platform == 'win32' else '')")
engine:
	mkdir -p xcl/_bin
	$(MAKE) -C "$(XCL_SRC)" xcl-core XCL_CORE_VERSION=v$(VERSION) XCL_CORE_OUT="$(CURDIR)/xcl/_bin/xcl-core$(EXE)"

# libxcl builds the engine as a shared library from the xcl checkout into
# xcl/_lib for the local platform, stamped with this package's version. It
# needs Go and a C compiler, and XCL_TRANSPORT=inprocess selects it
LIBXCL_EXT := $(shell $(PYTHON) -c "import sys; print('dll' if sys.platform == 'win32' else 'dylib' if sys.platform == 'darwin' else 'so')")
libxcl:
	mkdir -p xcl/_lib
	$(MAKE) -C "$(XCL_SRC)" libxcl LIBXCL_VERSION=v$(VERSION) LIBXCL_OUT="$(CURDIR)/xcl/_lib/libxcl.$(LIBXCL_EXT)"

# plugins builds the fixture plugins the integration tests use, and the Go
# parity program, into build/plugins, with the platform's executable suffix
# (.exe on Windows, where the engine cannot start a program without one)
plugins:
	mkdir -p build/plugins
	cd "$(XCL_SRC)/bindings/libxcl" && go build -o "$(CURDIR)/build/plugins/xcl-plugin-slow$(EXE)" ./testdata/plugins/slow && go build -o "$(CURDIR)/build/plugins/xcl-plugin-recording$(EXE)" ./testdata/plugins/recording && go build -o "$(CURDIR)/build/plugins/parity$(EXE)" ./cmd/parity

# test runs the unit tests, which need no engine, and the integration tests,
# which need make engine (or make libxcl with XCL_TRANSPORT=inprocess) and
# make plugins to have run
test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest tests/unit

.PHONY: protos engine libxcl plugins test test-unit
