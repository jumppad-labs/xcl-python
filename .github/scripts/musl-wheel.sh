#!/bin/sh
# Builds and tests one musl wheel inside python:3-alpine, run by the
# wheels-musl job of release.yml with TAG, VERSION, GH_TOKEN,
# XCL_WHEEL_PLATFORM, ASSET and XCL_SRC set and the checkout mounted at /work.
set -eu

apk add --no-cache bash build-base git gnupg github-cli make protobuf-dev tar
git config --global --add safe.directory '*'

# download and verify the engine archive
archive="libxcl_${VERSION}_${ASSET}.tar.gz"
mkdir -p engine && cd engine
gh release download "$TAG" --repo jumppad-labs/xcl \
  --pattern "$archive" \
  --pattern "libxcl_${VERSION}_checksums.txt" \
  --pattern "libxcl_${VERSION}_checksums.txt.sig"
gpg --batch --import ../tests/keys/jumppad-labs.asc
gpg --batch --verify "libxcl_${VERSION}_checksums.txt.sig" "libxcl_${VERSION}_checksums.txt"
grep " $archive\$" "libxcl_${VERSION}_checksums.txt" | sha256sum -c -
tar -xzf "$archive"
mkdir -p ../xcl/_lib
cp libxcl.so ../xcl/_lib/
cd ..

# set the version from the tag and regenerate the messages from xcl at the tag
sed -i "s/__version__ = \"[^\"]*\"/__version__ = \"$VERSION\"/" xcl/_version.py
grep __version__ xcl/_version.py
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
python -m pytest -q tests/parity tests/integration/test_load.py --rootdir . -p no:cacheprovider
