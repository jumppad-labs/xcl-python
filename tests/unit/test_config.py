"""Config creation and release, against the fake transport."""

import xcl
from xcl._client import Client
from xcl._core import core_pb2
from fakes import FakeTransport


def test_config_creates_and_keeps_handle():
    transport = FakeTransport({"CreateConfig": core_pb2.CreateConfigResponse(handle=42)})
    client = Client(transport)

    config = xcl.Config(client=client)

    assert config.handle == 42
    assert transport.methods_called() == ["GetVersion", "CreateConfig"]
    handle, _, request = transport.calls[-1]
    assert handle == 0
    assert request == core_pb2.CreateConfigRequest().SerializeToString()
    assert transport.released == []


def test_close_releases_once():
    transport = FakeTransport()
    config = xcl.Config(client=Client(transport))

    config.close()
    config.close()

    assert transport.released == [7]
    assert config.handle == 0


def test_context_manager_closes():
    transport = FakeTransport()

    with xcl.Config(client=Client(transport)) as config:
        assert config.handle == 7
        assert transport.released == []

    assert transport.released == [7]
    assert config.handle == 0
