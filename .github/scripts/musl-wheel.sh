#!/bin/sh
# Builds and tests one musl wheel inside python:3-alpine, run by the
# wheels-musl job of release.yml with TAG, VERSION, GH_TOKEN,
# XCL_WHEEL_PLATFORM, ASSET, XCL_SRC and GO_VERSION set and the checkout
# mounted at /work.
set -eu

# no C compiler: the engine program comes from the release, and Go builds the
# fixture plugins and the parity program with cgo disabled. Go comes from its
# official archive, since the go package of Alpine pulls in gcc
apk add --no-cache bash curl git gnupg github-cli make protobuf-dev tar
case "$(uname -m)" in x86_64) goarch=amd64 ;; aarch64) goarch=arm64 ;; esac
curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${goarch}.tar.gz" | tar -C /usr/local -xz
export PATH="/usr/local/go/bin:$PATH"
git config --global --add safe.directory '*'

# download and verify the engine program's archive
archive="xcl-core_${VERSION}_${ASSET}.tar.gz"
mkdir -p engine && cd engine
gh release download "$TAG" --repo jumppad-labs/xcl \
  --pattern "$archive" \
  --pattern "xcl-core_${VERSION}_checksums.txt" \
  --pattern "xcl-core_${VERSION}_checksums.txt.sig"
gpg --batch --import ../tests/keys/jumppad-labs.asc
gpg --batch --verify "xcl-core_${VERSION}_checksums.txt.sig" "xcl-core_${VERSION}_checksums.txt"
grep " $archive\$" "xcl-core_${VERSION}_checksums.txt" | sha256sum -c -
tar -xzf "$archive"
mkdir -p ../xcl/_bin
cp xcl-core ../xcl/_bin/
chmod +x ../xcl/_bin/xcl-core
cd ..

# set the version from the tag and regenerate the messages from xcl at the tag
sed -i "s/__version__ = \"[^\"]*\"/__version__ = \"$VERSION\"/" xcl/_version.py
sed -i "s/__engine_version__ = \"[^\"]*\"/__engine_version__ = \"$TAG\"/" xcl/_version.py
grep _version__ xcl/_version.py
make protos XCL_SRC="$XCL_SRC" PYTHON=python

# check the engine reports the tag
python -m pip install --upgrade pip
python -m pip install -e .
python -c "import xcl; v = xcl.engine_version(); print(v); assert v == '$TAG', v"

# build the wheel
python -m pip install build
python -m build --wheel
ls dist

# build the fixture plugins and the Go parity program, then test the wheel:
# the installed wheel is what runs, imported from site-packages
make plugins XCL_SRC="$XCL_SRC" PYTHON=python
python -m pip uninstall -y xcl-lang
python -m pip install dist/*.whl pytest
export XCL_TEST_STRICT=1 XCL_TEST_ENGINES=subprocess
python -m pytest -q tests/parity tests/integration/test_load.py --rootdir . -p no:cacheprovider

# the installed engine program must be executable
(cd /tmp && python -c "import os, xcl; from xcl._transport.subprocess import program_path; p = program_path(); print(p); assert p.is_file(), p; assert os.access(p, os.X_OK), f'{p} is not executable'")
