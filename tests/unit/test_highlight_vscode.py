"""Loading a VS Code colour theme through the engine's ConvertTheme, against the fake transport."""

import pytest

import xcl
import xcl._client
from xcl._client import Client
from xcl._core import core_pb2
from xcl.highlight import Kind, load_vscode_theme
from fakes import FakeTransport

THEME_JSON = b'{"tokenColors": [{"scope": "variable.other.property", "settings": {"foreground": "#ff8800"}}]}'


def use_transport(monkeypatch, transport: FakeTransport) -> None:
    """Make ``transport`` the one every engine call without a configuration goes through."""
    client = Client(transport)
    monkeypatch.setattr(xcl._client, "default_client", lambda: client)


def convert_transport(styles: dict[int, str]) -> FakeTransport:
    return FakeTransport({"ConvertTheme": core_pb2.ConvertThemeResponse(styles=styles)})


def test_load_vscode_theme_sends_bytes_on_handle_zero(monkeypatch):
    transport = convert_transport({300: "#ff8800"})
    use_transport(monkeypatch, transport)

    load_vscode_theme(THEME_JSON)

    handle, method, raw = transport.calls[-1]
    assert handle == 0
    assert method == "ConvertTheme"
    assert core_pb2.ConvertThemeRequest.FromString(raw).vscode_theme_json == THEME_JSON


def test_load_vscode_theme_creates_no_configuration(monkeypatch):
    transport = convert_transport({300: "#ff8800"})
    use_transport(monkeypatch, transport)

    load_vscode_theme(THEME_JSON)

    assert "CreateConfig" not in transport.methods_called()


def test_load_vscode_theme_reads_path(monkeypatch, tmp_path):
    transport = convert_transport({300: "#ff8800"})
    use_transport(monkeypatch, transport)
    path = tmp_path / "theme.json"
    path.write_bytes(THEME_JSON)

    load_vscode_theme(path)

    _, _, raw = transport.calls[-1]
    assert core_pb2.ConvertThemeRequest.FromString(raw).vscode_theme_json == THEME_JSON


def test_load_vscode_theme_reads_path_given_as_string(monkeypatch, tmp_path):
    transport = convert_transport({300: "#ff8800"})
    use_transport(monkeypatch, transport)
    path = tmp_path / "theme.json"
    path.write_bytes(THEME_JSON)

    load_vscode_theme(str(path))

    _, _, raw = transport.calls[-1]
    assert core_pb2.ConvertThemeRequest.FromString(raw).vscode_theme_json == THEME_JSON


def test_load_vscode_theme_returns_kinds(monkeypatch):
    use_transport(monkeypatch, convert_transport({300: "#ff8800", 1100: "italic #6a9955"}))

    theme = load_vscode_theme(THEME_JSON)

    assert theme == {Kind.ATTRIBUTE: "#ff8800", Kind.COMMENT: "italic #6a9955"}
    assert all(isinstance(kind, Kind) for kind in theme)


def test_load_vscode_theme_keeps_unknown_kind_number(monkeypatch):
    use_transport(monkeypatch, convert_transport({1199: "bold"}))

    theme = load_vscode_theme(THEME_JSON)

    assert theme == {1199: "bold"}
    assert not isinstance(next(iter(theme)), Kind)


def test_invalid_theme_code_raises_invalid_theme_error(monkeypatch):
    reason = 'tokenColors[0].settings.foreground "#zz0000" is not a colour'
    use_transport(
        monkeypatch,
        FakeTransport(
            {
                "ConvertTheme": core_pb2.Error(
                    code="invalid_theme",
                    message="theme theme is invalid: " + reason,
                    details={"source": "theme", "reason": reason},
                )
            }
        ),
    )

    with pytest.raises(xcl.InvalidThemeError) as raised:
        load_vscode_theme(b'{"tokenColors": []}')

    assert raised.value.details == {"source": "theme", "reason": reason}
