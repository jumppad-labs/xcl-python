"""Mapping engine Error messages to the package's exception classes."""

import xcl
from xcl._core import core_pb2
from xcl._errors import _BY_CODE, from_proto
from xcl.highlight import Kind, Token


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


# -- reports kept on errors -------------------------------------------------


def unsupported_block_report() -> list[core_pb2.Token]:
    """The report the engine sends for an unsupported block, as protocol tokens."""
    return [
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_ERROR, text="Error"),
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_SUMMARY, text=": Unsupported block type"),
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="\n\n"),
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_LOCATION, text="  on main.xcl line 2, in app.web, field timeout[0]:"),
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="\n"),
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_GUTTER, text="     2 | "),
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="  "),
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_ERROR, text="timeout"),
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text=" {\n\n"),
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_DETAIL, text='Blocks of type "timeout" are not expected here.'),
        core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="\n\n"),
    ]


def test_report_kept_as_tokens():
    error = from_proto(
        core_pb2.Error(
            code="config",
            message="main.xcl:2,3-10: Unsupported block type",
            report=unsupported_block_report(),
        )
    )

    assert error.tokens == [
        Token(Kind.ERROR, "Error"),
        Token(Kind.SUMMARY, ": Unsupported block type"),
        Token(Kind.TEXT, "\n\n"),
        Token(Kind.LOCATION, "  on main.xcl line 2, in app.web, field timeout[0]:"),
        Token(Kind.TEXT, "\n"),
        Token(Kind.GUTTER, "     2 | "),
        Token(Kind.TEXT, "  "),
        Token(Kind.ERROR, "timeout"),
        Token(Kind.TEXT, " {\n\n"),
        Token(Kind.DETAIL, 'Blocks of type "timeout" are not expected here.'),
        Token(Kind.TEXT, "\n\n"),
    ]
    assert all(isinstance(token.kind, Kind) for token in error.tokens)


def test_report_added_as_note():
    error = from_proto(
        core_pb2.Error(
            code="config",
            message="main.xcl:2,3-10: Unsupported block type",
            report=unsupported_block_report(),
        )
    )

    assert error.__notes__ == [
        "Error: Unsupported block type\n"
        "\n"
        "  on main.xcl line 2, in app.web, field timeout[0]:\n"
        "     2 |   timeout {\n"
        "\n"
        'Blocks of type "timeout" are not expected here.'
    ]


def test_no_report_no_note():
    error = from_proto(core_pb2.Error(code="not_found", message="no entity found", details={"address": "app.nope"}))

    assert error.tokens == []
    assert not hasattr(error, "__notes__")


def test_cause_keeps_its_own_report():
    error = from_proto(
        core_pb2.Error(
            code="config",
            message="configuration is invalid",
            report=[
                core_pb2.Token(kind=core_pb2.TOKEN_KIND_ERROR, text="Error"),
                core_pb2.Token(kind=core_pb2.TOKEN_KIND_SUMMARY, text=": Outer problem"),
                core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="\n"),
            ],
            causes=[
                core_pb2.Error(
                    code="config",
                    message="main.xcl:4,1-2: Inner problem",
                    report=[
                        core_pb2.Token(kind=core_pb2.TOKEN_KIND_WARNING, text="Warning"),
                        core_pb2.Token(kind=core_pb2.TOKEN_KIND_SUMMARY, text=": Inner problem"),
                        core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="\n"),
                    ],
                ),
            ],
        )
    )

    cause = error.causes[0]
    assert cause.tokens == [
        Token(Kind.WARNING, "Warning"),
        Token(Kind.SUMMARY, ": Inner problem"),
        Token(Kind.TEXT, "\n"),
    ]
    assert cause.__notes__ == ["Warning: Inner problem"]
    assert error.tokens == [
        Token(Kind.ERROR, "Error"),
        Token(Kind.SUMMARY, ": Outer problem"),
        Token(Kind.TEXT, "\n"),
    ]
    assert error.__notes__ == ["Error: Outer problem"]


def test_unknown_kind_in_report_kept():
    error = from_proto(
        core_pb2.Error(
            code="config",
            message="main.xcl:1,1-2: Something new",
            report=[
                core_pb2.Token(kind=1199, text="novel"),
                core_pb2.Token(kind=core_pb2.TOKEN_KIND_TEXT, text="\n"),
            ],
        )
    )

    assert error.tokens == [Token(1199, "novel"), Token(Kind.TEXT, "\n")]
    assert type(error.tokens[0].kind) is int
    assert error.__notes__ == ["novel"]


def test_str_is_message_when_report_present():
    error = from_proto(
        core_pb2.Error(
            code="config",
            message="main.xcl:2,3-10: Unsupported block type",
            report=unsupported_block_report(),
        )
    )

    assert str(error) == "main.xcl:2,3-10: Unsupported block type"
    assert "\n" not in str(error)
    assert "not expected here" not in str(error)


def test_multi_problem_message_stays_engine_message():
    # recorded decision: str(err) stays Go's Error() text, one line per
    # problem, never collapsed to one line
    message = (
        "main.xcl:2,3-10: Unsupported block type; Blocks of type \"timeout\" are not expected here.\n"
        "main.xcl:5,3-8: Unsupported argument; An argument named \"bogus\" is not expected here."
    )
    error = from_proto(
        core_pb2.Error(
            code="config",
            message=message,
            report=unsupported_block_report(),
        )
    )

    assert isinstance(error, xcl.ConfigError)
    assert str(error) == message


def test_hand_built_error_with_tokens_has_note():
    error = xcl.ConfigError(
        "main.xcl:1,1-2: Broken",
        tokens=[
            Token(Kind.ERROR, "Error"),
            Token(Kind.SUMMARY, ": Broken"),
            Token(Kind.TEXT, "\n\n"),
            Token(Kind.DETAIL, "It does not work."),
            Token(Kind.TEXT, "\n"),
        ],
    )

    assert error.tokens == [
        Token(Kind.ERROR, "Error"),
        Token(Kind.SUMMARY, ": Broken"),
        Token(Kind.TEXT, "\n\n"),
        Token(Kind.DETAIL, "It does not work."),
        Token(Kind.TEXT, "\n"),
    ]
    assert error.__notes__ == ["Error: Broken\n\nIt does not work."]


def test_note_wraps_long_detail_at_80():
    detail = (
        'Blocks of type "timeout" are not expected here. Did you mean to define an argument called "timeout" '
        "instead, as an attribute with an equals sign?"
    )
    error = xcl.ConfigError(
        "main.xcl:1,1-2: Unsupported block type",
        tokens=[
            Token(Kind.ERROR, "Error"),
            Token(Kind.SUMMARY, ": Unsupported block type"),
            Token(Kind.TEXT, "\n\n"),
            Token(Kind.DETAIL, detail),
            Token(Kind.TEXT, "\n"),
        ],
    )

    assert error.__notes__ == [
        "Error: Unsupported block type\n"
        "\n"
        'Blocks of type "timeout" are not expected here. Did you mean to define an\n'
        'argument called "timeout" instead, as an attribute with an equals sign?'
    ]


def test_binding_raised_error_has_no_tokens():
    error = xcl.InternalBindingError("X", -1)

    assert error.tokens == []
    assert not hasattr(error, "__notes__")


def test_invalid_theme_code_maps_to_class():
    error = from_proto(
        core_pb2.Error(
            code="invalid_theme",
            message='theme theme is invalid: tokenColors[0].settings.foreground "#zz0000" is not a colour',
            details={"source": "theme", "reason": 'tokenColors[0].settings.foreground "#zz0000" is not a colour'},
        )
    )

    assert isinstance(error, xcl.InvalidThemeError)
    assert error.code == "invalid_theme"
    assert error.details["reason"] == 'tokenColors[0].settings.foreground "#zz0000" is not a colour'
