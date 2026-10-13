"""Mapping engine Error messages to the package's exception classes."""

import xcl
from xcl._core import core_pb2
from xcl._errors import _BY_CODE, from_proto


def test_not_found_code_raises_not_found_error():
    error = from_proto(
        core_pb2.Error(
            code="not_found",
            message='no entity found at address "app.nope"',
            details={"address": "app.nope"},
        )
    )

    assert isinstance(error, xcl.NotFoundError)
    assert isinstance(error, xcl.Error)
    assert error.code == "not_found"
    assert error.message == 'no entity found at address "app.nope"'
    assert str(error) == 'no entity found at address "app.nope"'
    assert error.details == {"address": "app.nope"}
    assert error.causes == []


def test_not_unique_code_raises_not_unique_error():
    error = from_proto(
        core_pb2.Error(code="not_unique", message="3 entities matched", details={"count": "3"})
    )

    assert isinstance(error, xcl.NotUniqueError)
    assert error.details == {"count": "3"}
    assert str(error) == "3 entities matched"


def test_config_code_raises_config_error_with_problems():
    error = from_proto(
        core_pb2.Error(
            code="config",
            message="configuration is invalid",
            causes=[
                core_pb2.Error(
                    code="config",
                    message="main.hcl:3:9: unknown attribute",
                    details={"file": "main.hcl", "line": "3", "column": "9", "summary": "unknown attribute"},
                ),
                core_pb2.Error(
                    code="config",
                    message="other.hcl:12:1: missing block label",
                    details={"file": "other.hcl", "line": "12", "column": "1", "summary": "missing block label"},
                ),
            ],
        )
    )

    assert isinstance(error, xcl.ConfigError)
    assert str(error) == "configuration is invalid"
    assert len(error.causes) == 2
    assert error.problems == [
        xcl.Problem(file="main.hcl", line=3, column=9, message="unknown attribute"),
        xcl.Problem(file="other.hcl", line=12, column=1, message="missing block label"),
    ]
    assert isinstance(error.problems[0].line, int)
    assert isinstance(error.problems[0].column, int)
    assert str(error.problems[0]) == "main.hcl:3:9: unknown attribute"


def test_config_error_problem_from_a_diagnostic_holds_its_detail_block_and_field():
    error = from_proto(
        core_pb2.Error(
            code="config",
            message="configuration is invalid",
            causes=[
                core_pb2.Error(
                    code="config",
                    message='main.xcl:2,3-8: Unsupported argument; An argument named "modls" is not expected here.',
                    details={
                        "severity": "error",
                        "summary": "Unsupported argument",
                        "detail": 'An argument named "modls" is not expected here.',
                        "entity": "agent.claude",
                        "field": "modls",
                        "file": "main.xcl",
                        "line": "2",
                        "column": "3",
                    },
                ),
            ],
        )
    )

    assert error.problems == [
        xcl.Problem(
            file="main.xcl",
            line=2,
            column=3,
            message='Unsupported argument; An argument named "modls" is not expected here.',
            detail='An argument named "modls" is not expected here.',
            entity="agent.claude",
            field="modls",
        ),
    ]


def test_provider_code_raises_provider_error():
    error = from_proto(
        core_pb2.Error(
            code="provider",
            message="create failed",
            details={"address": "container.app", "step": "create"},
        )
    )

    assert isinstance(error, xcl.ProviderError)
    assert error.details == {"address": "container.app", "step": "create"}
    assert str(error) == "create failed"


def test_cancelled_code_raises_cancelled_error():
    error = from_proto(core_pb2.Error(code="cancelled", message="operation cancelled"))

    assert isinstance(error, xcl.CancelledError)
    assert str(error) == "operation cancelled"


def test_function_name_clash_code_raises_function_name_clash_error():
    error = from_proto(
        core_pb2.Error(
            code="function_name_clash",
            message='function "env" is offered twice',
            details={"name": "env", "first_registry": "builtin", "second_registry": "local"},
        )
    )

    assert isinstance(error, xcl.FunctionNameClashError)
    assert error.details["name"] == "env"
    assert str(error) == 'function "env" is offered twice'


def test_plugin_verification_code_raises_plugin_verification_error():
    error = from_proto(
        core_pb2.Error(
            code="plugin_verification",
            message="checksum mismatch",
            details={"plugin": "docker", "registry": "github"},
        )
    )

    assert isinstance(error, xcl.PluginVerificationError)
    assert error.details == {"plugin": "docker", "registry": "github"}
    assert str(error) == "checksum mismatch"


def test_operation_in_progress_code_raises_operation_in_progress_error():
    error = from_proto(core_pb2.Error(code="operation_in_progress", message="an apply is running"))

    assert isinstance(error, xcl.OperationInProgressError)
    assert str(error) == "an apply is running"


def test_invalid_argument_code_raises_invalid_argument_error():
    error = from_proto(core_pb2.Error(code="invalid_argument", message="no paths given"))

    assert isinstance(error, xcl.InvalidArgumentError)
    assert str(error) == "no paths given"


def test_unknown_code_raises_base_error():
    error = from_proto(
        core_pb2.Error(code="something_new", message="the engine grew a code", details={"k": "v"})
    )

    assert type(error) is xcl.Error
    assert error.code == "something_new"
    assert str(error) == "the engine grew a code"
    assert error.details == {"k": "v"}


def test_causes_are_mapped_recursively():
    error = from_proto(
        core_pb2.Error(
            code="provider",
            message="apply failed",
            causes=[
                core_pb2.Error(
                    code="not_found",
                    message="image missing",
                    details={"address": "image.base"},
                    causes=[core_pb2.Error(code="mystery", message="deepest")],
                ),
                core_pb2.Error(code="cancelled", message="gave up"),
            ],
        )
    )

    assert isinstance(error, xcl.ProviderError)
    assert len(error.causes) == 2

    first, second = error.causes
    assert isinstance(first, xcl.NotFoundError)
    assert first.details == {"address": "image.base"}
    assert isinstance(second, xcl.CancelledError)

    deepest = first.causes[0]
    assert type(deepest) is xcl.Error
    assert deepest.code == "mystery"
    assert str(deepest) == "deepest"


def test_every_registered_class_is_an_error_subclass():
    assert _BY_CODE

    for code, cls in _BY_CODE.items():
        assert issubclass(cls, xcl.Error), cls
        assert cls.code == code, cls
        error = from_proto(core_pb2.Error(code=code, message="m"))
        assert type(error) is cls, code
        assert isinstance(error, xcl.Error), code
        assert str(error) == "m", code
