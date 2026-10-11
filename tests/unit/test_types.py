"""The value types: Sensitive, UNKNOWN, and the JSON argument conversion."""

from xcl import UNKNOWN, Sensitive
from xcl._schema import cty_to_python, is_masked


def test_sensitive_repr_masked():
    secret = Sensitive("hunter2")

    assert repr(secret) == "(sensitive)"
    assert str(secret) == "(sensitive)"
    assert f"{secret}" == "(sensitive)"


def test_sensitive_reveal_returns_value():
    secret = Sensitive("hunter2")

    assert secret.reveal() == "hunter2"
    assert not secret.is_redacted


def test_looked_up_sensitive_reveals_none():
    secret = Sensitive.redacted()

    assert secret.reveal() is None
    assert secret.is_redacted
    assert str(secret) == "(sensitive)"


def test_sensitive_equality():
    assert Sensitive("a") == Sensitive("a")
    assert Sensitive.redacted() == Sensitive.redacted()
    assert hash(Sensitive("a")) == hash(Sensitive("a"))


def test_sensitive_inequality():
    assert Sensitive("a") != Sensitive("b")
    assert Sensitive.redacted() != Sensitive("a")
    assert Sensitive("a") != "a"


def test_unknown_is_falsy_with_repr():
    assert not UNKNOWN
    assert bool(UNKNOWN) is False
    assert repr(UNKNOWN) == "xcl.UNKNOWN"


def test_cty_to_python_whole_float_is_int():
    converted = cty_to_python(2.0)

    assert converted == 2
    assert type(converted) is int


def test_cty_to_python_fractional_float_stays_float():
    converted = cty_to_python(2.5)

    assert converted == 2.5
    assert type(converted) is float


def test_cty_to_python_nested():
    converted = cty_to_python({"ports": [80.0, 443.0], "name": "web", "limits": {"cpu": 1.0, "ratio": 0.5}})

    assert converted == {"ports": [80, 443], "name": "web", "limits": {"cpu": 1, "ratio": 0.5}}
    assert all(type(p) is int for p in converted["ports"])
    assert type(converted["limits"]["cpu"]) is int


def test_is_masked():
    assert is_masked("(sensitive)")
    assert is_masked({"xcl_masked": "redact", "value": "(sensitive)"})


def test_is_masked_plain_value_is_not_masked():
    assert not is_masked("s3cret")
    assert not is_masked({"value": "(sensitive)"})
    assert not is_masked(None)
