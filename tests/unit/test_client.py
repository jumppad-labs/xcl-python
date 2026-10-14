"""The typed client: version check on first use and status handling."""

import pytest

import xcl
from xcl._client import Client, normalise_version
from xcl._core import core_pb2
from xcl._version import __engine_version__
from fakes import FakeTransport


def test_engine_version_mismatch_names_engine_package_and_pin():
    transport = FakeTransport({"GetVersion": core_pb2.GetVersionResponse(version="v9.9.9", abi_version=1)})
    client = Client(transport)

    with pytest.raises(xcl.EngineVersionError) as raised:
        client.call(0, "CreateConfig", core_pb2.CreateConfigRequest())

    error = raised.value
    assert "v9.9.9" in error.message
    assert xcl.__version__ in error.message
    assert __engine_version__ in error.message
    assert error.package == xcl.__version__
    assert error.engine == "v9.9.9"
    assert error.expected == __engine_version__
    assert error.details == {"package": xcl.__version__, "engine": "v9.9.9", "expected": __engine_version__}
    assert transport.calls[0][:2] == (0, "GetVersion")


def test_engine_reporting_pin_runs_when_package_version_differs():
    assert normalise_version(__engine_version__) != normalise_version(xcl.__version__)
    transport = FakeTransport({"GetVersion": core_pb2.GetVersionResponse(version=__engine_version__, abi_version=1)})
    client = Client(transport)

    response = client.call(0, "CreateConfig", core_pb2.CreateConfigRequest())

    assert response.handle == 7
    assert transport.methods_called() == ["GetVersion", "CreateConfig"]


def test_engine_reporting_package_version_is_refused():
    assert normalise_version(__engine_version__) != normalise_version(xcl.__version__)
    transport = FakeTransport({"GetVersion": core_pb2.GetVersionResponse(version=xcl.__version__, abi_version=1)})
    client = Client(transport)

    with pytest.raises(xcl.EngineVersionError) as raised:
        client.call(0, "CreateConfig", core_pb2.CreateConfigRequest())

    assert raised.value.engine == xcl.__version__
    assert raised.value.expected == __engine_version__
    assert transport.methods_called() == ["GetVersion"]


def test_engine_reporting_package_version_with_v_prefix_is_refused():
    assert normalise_version(__engine_version__) != normalise_version(xcl.__version__)
    transport = FakeTransport(
        {"GetVersion": core_pb2.GetVersionResponse(version="v" + xcl.__version__, abi_version=1)}
    )
    client = Client(transport)

    with pytest.raises(xcl.EngineVersionError) as raised:
        client.call(0, "CreateConfig", core_pb2.CreateConfigRequest())

    assert raised.value.engine == "v" + xcl.__version__
    assert raised.value.expected == __engine_version__
    assert transport.methods_called() == ["GetVersion"]


def test_engine_version_with_v_prefix_matches_pin():
    transport = FakeTransport(
        {"GetVersion": core_pb2.GetVersionResponse(version="v" + normalise_version(__engine_version__), abi_version=1)}
    )
    client = Client(transport)

    response = client.call(0, "CreateConfig", core_pb2.CreateConfigRequest())

    assert response.handle == 7
    assert transport.methods_called() == ["GetVersion", "CreateConfig"]


def test_engine_version_without_v_prefix_matches_pin():
    transport = FakeTransport(
        {"GetVersion": core_pb2.GetVersionResponse(version=normalise_version(__engine_version__), abi_version=1)}
    )
    client = Client(transport)

    response = client.call(0, "CreateConfig", core_pb2.CreateConfigRequest())

    assert response.handle == 7
    assert transport.methods_called() == ["GetVersion", "CreateConfig"]


def test_version_check_can_be_skipped():
    transport = FakeTransport({"GetVersion": core_pb2.GetVersionResponse(version="v9.9.9", abi_version=1)})
    client = Client(transport, check_version=False)

    response = client.call(0, "CreateConfig", core_pb2.CreateConfigRequest())

    assert response.handle == 7
    assert client.engine_version() == "v9.9.9"


def test_negative_status_raises_internal_binding_error():
    transport = FakeTransport({"Find": -3})
    client = Client(transport)

    with pytest.raises(xcl.InternalBindingError) as raised:
        client.call(7, "Find", core_pb2.FindRequest(address="app.one"))

    error = raised.value
    assert error.method == "Find"
    assert error.status == -3
    assert "Find" in error.message
    assert error.details == {"method": "Find", "status": "-3"}


def test_error_status_raises_mapped_exception():
    engine_error = core_pb2.Error(
        code="not_found",
        message='no entity found at address "app.nope"',
        details={"address": "app.nope"},
    )
    transport = FakeTransport({"Find": engine_error})
    client = Client(transport)

    with pytest.raises(xcl.NotFoundError) as raised:
        client.call(7, "Find", core_pb2.FindRequest(address="app.nope"))

    error = raised.value
    assert error.message == 'no entity found at address "app.nope"'
    assert error.details == {"address": "app.nope"}


def test_ok_status_decodes_response_class():
    transport = FakeTransport()
    client = Client(transport)

    response = client.call(0, "CreateConfig", core_pb2.CreateConfigRequest())

    assert isinstance(response, core_pb2.CreateConfigResponse)
    assert response.handle == 7
    handle, method, request = transport.calls[-1]
    assert (handle, method) == (0, "CreateConfig")
    assert request == core_pb2.CreateConfigRequest().SerializeToString()


def test_release_failure_raises_internal_binding_error():
    transport = FakeTransport(release_status=-3)
    client = Client(transport)

    with pytest.raises(xcl.InternalBindingError) as raised:
        client.release(7)

    assert raised.value.method == "Release"
    assert raised.value.status == -3
    assert transport.released == [7]


def test_engine_version_reported():
    transport = FakeTransport({"GetVersion": core_pb2.GetVersionResponse(version=__engine_version__, abi_version=1)})
    client = Client(transport)

    assert client.engine_version() == __engine_version__
    assert client.engine_version() == __engine_version__
    assert transport.methods_called() == ["GetVersion"]


def test_engine_version_reports_running_engine_not_pin():
    transport = FakeTransport({"GetVersion": core_pb2.GetVersionResponse(version="v9.9.9", abi_version=1)})
    client = Client(transport, check_version=False)

    assert client.engine_version() == "v9.9.9"
    assert transport.methods_called() == ["GetVersion"]
