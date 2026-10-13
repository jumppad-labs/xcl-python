"""The test helper that decides whether a missing engine skips or fails a test."""

from __future__ import annotations

import pytest

from engines import TEST_ENGINES_ENV, TEST_STRICT_ENV, expected_routes, skip_missing_engine


def test_missing_engine_skips_without_strict(monkeypatch):
    monkeypatch.delenv(TEST_STRICT_ENV, raising=False)
    monkeypatch.setenv(TEST_ENGINES_ENV, "subprocess")

    with pytest.raises(pytest.skip.Exception) as raised:
        skip_missing_engine("subprocess", "the engine program is missing")

    assert "the engine program is missing" in str(raised.value)


def test_missing_engine_fails_when_strict_and_route_expected(monkeypatch):
    monkeypatch.setenv(TEST_STRICT_ENV, "1")
    monkeypatch.setenv(TEST_ENGINES_ENV, "subprocess,inprocess")

    with pytest.raises(pytest.fail.Exception) as raised:
        skip_missing_engine("inprocess", "the shared library is missing")

    message = str(raised.value)
    assert "the shared library is missing" in message
    assert TEST_STRICT_ENV in message
    assert "inprocess" in message


def test_missing_engine_skips_when_strict_and_route_not_expected(monkeypatch):
    monkeypatch.setenv(TEST_STRICT_ENV, "1")
    monkeypatch.setenv(TEST_ENGINES_ENV, "subprocess")

    with pytest.raises(pytest.skip.Exception) as raised:
        skip_missing_engine("inprocess", "the shared library is missing")

    assert "the shared library is missing" in str(raised.value)


def test_expected_routes_parses_comma_separated_list(monkeypatch):
    monkeypatch.setenv(TEST_ENGINES_ENV, " subprocess , inprocess,,")

    routes = expected_routes()

    assert routes == {"subprocess", "inprocess"}
