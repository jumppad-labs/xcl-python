"""Where the tests find the xcl sources, and how a missing one skips or fails."""

from __future__ import annotations

import pytest

import xcl_source
from engines import TEST_ENGINES_ENV, TEST_STRICT_ENV


def test_path_is_xcl_src_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv(xcl_source.SOURCE_ENV, str(tmp_path))

    assert xcl_source.path() == tmp_path.resolve()


def test_path_is_sibling_checkout_when_xcl_src_unset(monkeypatch):
    monkeypatch.delenv(xcl_source.SOURCE_ENV, raising=False)

    assert xcl_source.path() == (xcl_source.ROOT.parent / "xcl").resolve()


def test_path_is_sibling_checkout_when_xcl_src_empty(monkeypatch):
    monkeypatch.setenv(xcl_source.SOURCE_ENV, "")

    assert xcl_source.path() == (xcl_source.ROOT.parent / "xcl").resolve()


def test_require_returns_path_inside_xcl_src(monkeypatch, tmp_path):
    (tmp_path / "bindings" / "libxcl").mkdir(parents=True)
    monkeypatch.setenv(xcl_source.SOURCE_ENV, str(tmp_path))

    found = xcl_source.require("bindings/libxcl")

    assert found == tmp_path.resolve() / "bindings" / "libxcl"


def test_require_skips_naming_xcl_src_when_sources_missing(monkeypatch, tmp_path):
    monkeypatch.setenv(xcl_source.SOURCE_ENV, str(tmp_path / "missing"))
    monkeypatch.delenv(TEST_STRICT_ENV, raising=False)

    with pytest.raises(pytest.skip.Exception) as raised:
        xcl_source.require("bindings/libxcl")

    assert "set XCL_SRC" in str(raised.value)


def test_require_fails_when_sources_missing_in_strict_mode(monkeypatch, tmp_path):
    monkeypatch.setenv(xcl_source.SOURCE_ENV, str(tmp_path / "missing"))
    monkeypatch.setenv(TEST_STRICT_ENV, "1")

    with pytest.raises(pytest.fail.Exception) as raised:
        xcl_source.require("bindings/libxcl")

    message = str(raised.value)
    assert "set XCL_SRC" in message
    assert TEST_STRICT_ENV in message


def test_skip_without_route_skips_without_strict(monkeypatch):
    monkeypatch.delenv(TEST_STRICT_ENV, raising=False)

    with pytest.raises(pytest.skip.Exception) as raised:
        xcl_source.skip("the fixture plugins are not built")

    assert "the fixture plugins are not built" in str(raised.value)


def test_skip_without_route_fails_in_strict_mode(monkeypatch):
    monkeypatch.setenv(TEST_STRICT_ENV, "1")

    with pytest.raises(pytest.fail.Exception) as raised:
        xcl_source.skip("the fixture plugins are not built")

    assert "the fixture plugins are not built" in str(raised.value)


def test_skip_with_route_the_job_does_not_build_skips_in_strict_mode(monkeypatch):
    monkeypatch.setenv(TEST_STRICT_ENV, "1")
    monkeypatch.setenv(TEST_ENGINES_ENV, "subprocess")

    with pytest.raises(pytest.skip.Exception) as raised:
        xcl_source.skip("the shared library is missing", route="inprocess")

    assert "the shared library is missing" in str(raised.value)


def test_skip_with_route_the_job_builds_fails_in_strict_mode(monkeypatch):
    monkeypatch.setenv(TEST_STRICT_ENV, "1")
    monkeypatch.setenv(TEST_ENGINES_ENV, "subprocess,inprocess")

    with pytest.raises(pytest.fail.Exception) as raised:
        xcl_source.skip("the shared library is missing", route="inprocess")

    assert "the shared library is missing" in str(raised.value)
