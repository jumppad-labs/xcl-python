from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TokenKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TOKEN_KIND_TEXT: _ClassVar[TokenKind]
    TOKEN_KIND_BLOCK: _ClassVar[TokenKind]
    TOKEN_KIND_BLOCK_TYPE: _ClassVar[TokenKind]
    TOKEN_KIND_NESTED_BLOCK: _ClassVar[TokenKind]
    TOKEN_KIND_LABEL: _ClassVar[TokenKind]
    TOKEN_KIND_TYPE_LABEL: _ClassVar[TokenKind]
    TOKEN_KIND_NAME_LABEL: _ClassVar[TokenKind]
    TOKEN_KIND_ATTRIBUTE: _ClassVar[TokenKind]
    TOKEN_KIND_STRING: _ClassVar[TokenKind]
    TOKEN_KIND_STRING_ESCAPE: _ClassVar[TokenKind]
    TOKEN_KIND_HEREDOC: _ClassVar[TokenKind]
    TOKEN_KIND_HEREDOC_MARKER: _ClassVar[TokenKind]
    TOKEN_KIND_HEREDOC_OPERATOR: _ClassVar[TokenKind]
    TOKEN_KIND_NUMBER: _ClassVar[TokenKind]
    TOKEN_KIND_CONSTANT: _ClassVar[TokenKind]
    TOKEN_KIND_FUNCTION: _ClassVar[TokenKind]
    TOKEN_KIND_BUILTIN_FUNCTION: _ClassVar[TokenKind]
    TOKEN_KIND_REFERENCE: _ClassVar[TokenKind]
    TOKEN_KIND_MEMBER: _ClassVar[TokenKind]
    TOKEN_KIND_OPERATOR: _ClassVar[TokenKind]
    TOKEN_KIND_PUNCTUATION: _ClassVar[TokenKind]
    TOKEN_KIND_INTERPOLATION_BEGIN: _ClassVar[TokenKind]
    TOKEN_KIND_INTERPOLATION_END: _ClassVar[TokenKind]
    TOKEN_KIND_TEMPLATE_DIRECTIVE: _ClassVar[TokenKind]
    TOKEN_KIND_ACCESSOR: _ClassVar[TokenKind]
    TOKEN_KIND_COMMENT: _ClassVar[TokenKind]
    TOKEN_KIND_LINE_COMMENT: _ClassVar[TokenKind]
    TOKEN_KIND_HASH_COMMENT: _ClassVar[TokenKind]
    TOKEN_KIND_BLOCK_COMMENT: _ClassVar[TokenKind]
    TOKEN_KIND_DIFF: _ClassVar[TokenKind]
    TOKEN_KIND_INSERTED: _ClassVar[TokenKind]
    TOKEN_KIND_DELETED: _ClassVar[TokenKind]
    TOKEN_KIND_CHANGED: _ClassVar[TokenKind]
    TOKEN_KIND_PROBLEM: _ClassVar[TokenKind]
    TOKEN_KIND_ERROR: _ClassVar[TokenKind]
    TOKEN_KIND_WARNING: _ClassVar[TokenKind]
    TOKEN_KIND_REPORT: _ClassVar[TokenKind]
    TOKEN_KIND_SUMMARY: _ClassVar[TokenKind]
    TOKEN_KIND_LOCATION: _ClassVar[TokenKind]
    TOKEN_KIND_GUTTER: _ClassVar[TokenKind]
    TOKEN_KIND_DETAIL: _ClassVar[TokenKind]

class EventDataLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EVENT_DATA_NONE: _ClassVar[EventDataLevel]
    EVENT_DATA_RAW: _ClassVar[EventDataLevel]
    EVENT_DATA_PROCESSED: _ClassVar[EventDataLevel]
TOKEN_KIND_TEXT: TokenKind
TOKEN_KIND_BLOCK: TokenKind
TOKEN_KIND_BLOCK_TYPE: TokenKind
TOKEN_KIND_NESTED_BLOCK: TokenKind
TOKEN_KIND_LABEL: TokenKind
TOKEN_KIND_TYPE_LABEL: TokenKind
TOKEN_KIND_NAME_LABEL: TokenKind
TOKEN_KIND_ATTRIBUTE: TokenKind
TOKEN_KIND_STRING: TokenKind
TOKEN_KIND_STRING_ESCAPE: TokenKind
TOKEN_KIND_HEREDOC: TokenKind
TOKEN_KIND_HEREDOC_MARKER: TokenKind
TOKEN_KIND_HEREDOC_OPERATOR: TokenKind
TOKEN_KIND_NUMBER: TokenKind
TOKEN_KIND_CONSTANT: TokenKind
TOKEN_KIND_FUNCTION: TokenKind
TOKEN_KIND_BUILTIN_FUNCTION: TokenKind
TOKEN_KIND_REFERENCE: TokenKind
TOKEN_KIND_MEMBER: TokenKind
TOKEN_KIND_OPERATOR: TokenKind
TOKEN_KIND_PUNCTUATION: TokenKind
TOKEN_KIND_INTERPOLATION_BEGIN: TokenKind
TOKEN_KIND_INTERPOLATION_END: TokenKind
TOKEN_KIND_TEMPLATE_DIRECTIVE: TokenKind
TOKEN_KIND_ACCESSOR: TokenKind
TOKEN_KIND_COMMENT: TokenKind
TOKEN_KIND_LINE_COMMENT: TokenKind
TOKEN_KIND_HASH_COMMENT: TokenKind
TOKEN_KIND_BLOCK_COMMENT: TokenKind
TOKEN_KIND_DIFF: TokenKind
TOKEN_KIND_INSERTED: TokenKind
TOKEN_KIND_DELETED: TokenKind
TOKEN_KIND_CHANGED: TokenKind
TOKEN_KIND_PROBLEM: TokenKind
TOKEN_KIND_ERROR: TokenKind
TOKEN_KIND_WARNING: TokenKind
TOKEN_KIND_REPORT: TokenKind
TOKEN_KIND_SUMMARY: TokenKind
TOKEN_KIND_LOCATION: TokenKind
TOKEN_KIND_GUTTER: TokenKind
TOKEN_KIND_DETAIL: TokenKind
EVENT_DATA_NONE: EventDataLevel
EVENT_DATA_RAW: EventDataLevel
EVENT_DATA_PROCESSED: EventDataLevel

class Error(_message.Message):
    __slots__ = ("code", "message", "details", "causes", "report")
    class DetailsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    CAUSES_FIELD_NUMBER: _ClassVar[int]
    REPORT_FIELD_NUMBER: _ClassVar[int]
    code: str
    message: str
    details: _containers.ScalarMap[str, str]
    causes: _containers.RepeatedCompositeFieldContainer[Error]
    report: _containers.RepeatedCompositeFieldContainer[Token]
    def __init__(self, code: _Optional[str] = ..., message: _Optional[str] = ..., details: _Optional[_Mapping[str, str]] = ..., causes: _Optional[_Iterable[_Union[Error, _Mapping]]] = ..., report: _Optional[_Iterable[_Union[Token, _Mapping]]] = ...) -> None: ...

class Token(_message.Message):
    __slots__ = ("kind", "text")
    KIND_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    kind: TokenKind
    text: str
    def __init__(self, kind: _Optional[_Union[TokenKind, str]] = ..., text: _Optional[str] = ...) -> None: ...

class GetVersionRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetVersionResponse(_message.Message):
    __slots__ = ("version", "abi_version")
    VERSION_FIELD_NUMBER: _ClassVar[int]
    ABI_VERSION_FIELD_NUMBER: _ClassVar[int]
    version: str
    abi_version: int
    def __init__(self, version: _Optional[str] = ..., abi_version: _Optional[int] = ...) -> None: ...

class ConvertThemeRequest(_message.Message):
    __slots__ = ("vscode_theme_json",)
    VSCODE_THEME_JSON_FIELD_NUMBER: _ClassVar[int]
    vscode_theme_json: bytes
    def __init__(self, vscode_theme_json: _Optional[bytes] = ...) -> None: ...

class ConvertThemeResponse(_message.Message):
    __slots__ = ("styles",)
    class StylesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: str
        def __init__(self, key: _Optional[int] = ..., value: _Optional[str] = ...) -> None: ...
    STYLES_FIELD_NUMBER: _ClassVar[int]
    styles: _containers.ScalarMap[int, str]
    def __init__(self, styles: _Optional[_Mapping[int, str]] = ...) -> None: ...

class CreateConfigRequest(_message.Message):
    __slots__ = ("registries", "state_store", "state_mask", "events", "event_buffer_size", "event_data", "event_mask", "no_event_mask", "variables_json")
    REGISTRIES_FIELD_NUMBER: _ClassVar[int]
    STATE_STORE_FIELD_NUMBER: _ClassVar[int]
    STATE_MASK_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    EVENT_BUFFER_SIZE_FIELD_NUMBER: _ClassVar[int]
    EVENT_DATA_FIELD_NUMBER: _ClassVar[int]
    EVENT_MASK_FIELD_NUMBER: _ClassVar[int]
    NO_EVENT_MASK_FIELD_NUMBER: _ClassVar[int]
    VARIABLES_JSON_FIELD_NUMBER: _ClassVar[int]
    registries: _containers.RepeatedCompositeFieldContainer[Registry]
    state_store: StateStore
    state_mask: Mask
    events: bool
    event_buffer_size: int
    event_data: EventDataLevel
    event_mask: Mask
    no_event_mask: bool
    variables_json: bytes
    def __init__(self, registries: _Optional[_Iterable[_Union[Registry, _Mapping]]] = ..., state_store: _Optional[_Union[StateStore, _Mapping]] = ..., state_mask: _Optional[_Union[Mask, _Mapping]] = ..., events: _Optional[bool] = ..., event_buffer_size: _Optional[int] = ..., event_data: _Optional[_Union[EventDataLevel, str]] = ..., event_mask: _Optional[_Union[Mask, _Mapping]] = ..., no_event_mask: _Optional[bool] = ..., variables_json: _Optional[bytes] = ...) -> None: ...

class CreateConfigResponse(_message.Message):
    __slots__ = ("handle",)
    HANDLE_FIELD_NUMBER: _ClassVar[int]
    handle: int
    def __init__(self, handle: _Optional[int] = ...) -> None: ...

class Registry(_message.Message):
    __slots__ = ("local", "github")
    LOCAL_FIELD_NUMBER: _ClassVar[int]
    GITHUB_FIELD_NUMBER: _ClassVar[int]
    local: LocalRegistry
    github: GitHubRegistry
    def __init__(self, local: _Optional[_Union[LocalRegistry, _Mapping]] = ..., github: _Optional[_Union[GitHubRegistry, _Mapping]] = ...) -> None: ...

class LocalRegistry(_message.Message):
    __slots__ = ("plugin_pattern", "types", "external_plugins", "plugin_directories", "functions")
    PLUGIN_PATTERN_FIELD_NUMBER: _ClassVar[int]
    TYPES_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_PLUGINS_FIELD_NUMBER: _ClassVar[int]
    PLUGIN_DIRECTORIES_FIELD_NUMBER: _ClassVar[int]
    FUNCTIONS_FIELD_NUMBER: _ClassVar[int]
    plugin_pattern: str
    types: _containers.RepeatedCompositeFieldContainer[DeclaredType]
    external_plugins: _containers.RepeatedScalarFieldContainer[str]
    plugin_directories: _containers.RepeatedScalarFieldContainer[str]
    functions: _containers.RepeatedCompositeFieldContainer[DeclaredFunction]
    def __init__(self, plugin_pattern: _Optional[str] = ..., types: _Optional[_Iterable[_Union[DeclaredType, _Mapping]]] = ..., external_plugins: _Optional[_Iterable[str]] = ..., plugin_directories: _Optional[_Iterable[str]] = ..., functions: _Optional[_Iterable[_Union[DeclaredFunction, _Mapping]]] = ...) -> None: ...

class DeclaredType(_message.Message):
    __slots__ = ("type", "subtype", "schema")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SUBTYPE_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_FIELD_NUMBER: _ClassVar[int]
    type: str
    subtype: str
    schema: bytes
    def __init__(self, type: _Optional[str] = ..., subtype: _Optional[str] = ..., schema: _Optional[bytes] = ...) -> None: ...

class DeclaredFunction(_message.Message):
    __slots__ = ("name", "signature")
    NAME_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    name: str
    signature: bytes
    def __init__(self, name: _Optional[str] = ..., signature: _Optional[bytes] = ...) -> None: ...

class GitHubRegistry(_message.Message):
    __slots__ = ("plugins", "cache_dir", "trusted_keys", "token", "api_url", "types")
    PLUGINS_FIELD_NUMBER: _ClassVar[int]
    CACHE_DIR_FIELD_NUMBER: _ClassVar[int]
    TRUSTED_KEYS_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    API_URL_FIELD_NUMBER: _ClassVar[int]
    TYPES_FIELD_NUMBER: _ClassVar[int]
    plugins: _containers.RepeatedCompositeFieldContainer[GitHubPlugin]
    cache_dir: str
    trusted_keys: _containers.RepeatedScalarFieldContainer[str]
    token: str
    api_url: str
    types: _containers.RepeatedCompositeFieldContainer[DeclaredType]
    def __init__(self, plugins: _Optional[_Iterable[_Union[GitHubPlugin, _Mapping]]] = ..., cache_dir: _Optional[str] = ..., trusted_keys: _Optional[_Iterable[str]] = ..., token: _Optional[str] = ..., api_url: _Optional[str] = ..., types: _Optional[_Iterable[_Union[DeclaredType, _Mapping]]] = ...) -> None: ...

class GitHubPlugin(_message.Message):
    __slots__ = ("repository", "version")
    REPOSITORY_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    repository: str
    version: str
    def __init__(self, repository: _Optional[str] = ..., version: _Optional[str] = ...) -> None: ...

class StateStore(_message.Message):
    __slots__ = ("path", "host")
    PATH_FIELD_NUMBER: _ClassVar[int]
    HOST_FIELD_NUMBER: _ClassVar[int]
    path: str
    host: bool
    def __init__(self, path: _Optional[str] = ..., host: _Optional[bool] = ...) -> None: ...

class Mask(_message.Message):
    __slots__ = ("aes256gcm_key", "hmac_sha256_key", "redact", "omit")
    AES256GCM_KEY_FIELD_NUMBER: _ClassVar[int]
    HMAC_SHA256_KEY_FIELD_NUMBER: _ClassVar[int]
    REDACT_FIELD_NUMBER: _ClassVar[int]
    OMIT_FIELD_NUMBER: _ClassVar[int]
    aes256gcm_key: bytes
    hmac_sha256_key: bytes
    redact: bool
    omit: bool
    def __init__(self, aes256gcm_key: _Optional[bytes] = ..., hmac_sha256_key: _Optional[bytes] = ..., redact: _Optional[bool] = ..., omit: _Optional[bool] = ...) -> None: ...

class StartValidateRequest(_message.Message):
    __slots__ = ("paths",)
    PATHS_FIELD_NUMBER: _ClassVar[int]
    paths: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, paths: _Optional[_Iterable[str]] = ...) -> None: ...

class StartApplyRequest(_message.Message):
    __slots__ = ("paths",)
    PATHS_FIELD_NUMBER: _ClassVar[int]
    paths: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, paths: _Optional[_Iterable[str]] = ...) -> None: ...

class StartDiffRequest(_message.Message):
    __slots__ = ("paths", "reveal_sensitive")
    PATHS_FIELD_NUMBER: _ClassVar[int]
    REVEAL_SENSITIVE_FIELD_NUMBER: _ClassVar[int]
    paths: _containers.RepeatedScalarFieldContainer[str]
    reveal_sensitive: bool
    def __init__(self, paths: _Optional[_Iterable[str]] = ..., reveal_sensitive: _Optional[bool] = ...) -> None: ...

class StartDestroyRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StartLoadRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StartOperationResponse(_message.Message):
    __slots__ = ("operation_id",)
    OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    operation_id: int
    def __init__(self, operation_id: _Optional[int] = ...) -> None: ...

class CancelRequest(_message.Message):
    __slots__ = ("operation_id",)
    OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    operation_id: int
    def __init__(self, operation_id: _Optional[int] = ...) -> None: ...

class CancelResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class PollRequest(_message.Message):
    __slots__ = ("wait_ms",)
    WAIT_MS_FIELD_NUMBER: _ClassVar[int]
    wait_ms: int
    def __init__(self, wait_ms: _Optional[int] = ...) -> None: ...

class PollResponse(_message.Message):
    __slots__ = ("state", "event", "finished", "function")
    STATE_FIELD_NUMBER: _ClassVar[int]
    EVENT_FIELD_NUMBER: _ClassVar[int]
    FINISHED_FIELD_NUMBER: _ClassVar[int]
    FUNCTION_FIELD_NUMBER: _ClassVar[int]
    state: StateTask
    event: Event
    finished: OperationFinished
    function: FunctionTask
    def __init__(self, state: _Optional[_Union[StateTask, _Mapping]] = ..., event: _Optional[_Union[Event, _Mapping]] = ..., finished: _Optional[_Union[OperationFinished, _Mapping]] = ..., function: _Optional[_Union[FunctionTask, _Mapping]] = ...) -> None: ...

class StateTask(_message.Message):
    __slots__ = ("task_id", "operation_id", "kind", "entities")
    class Kind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        LOAD: _ClassVar[StateTask.Kind]
        SAVE: _ClassVar[StateTask.Kind]
        EXISTS: _ClassVar[StateTask.Kind]
        CLEAR: _ClassVar[StateTask.Kind]
    LOAD: StateTask.Kind
    SAVE: StateTask.Kind
    EXISTS: StateTask.Kind
    CLEAR: StateTask.Kind
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    ENTITIES_FIELD_NUMBER: _ClassVar[int]
    task_id: int
    operation_id: int
    kind: StateTask.Kind
    entities: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, task_id: _Optional[int] = ..., operation_id: _Optional[int] = ..., kind: _Optional[_Union[StateTask.Kind, str]] = ..., entities: _Optional[_Iterable[bytes]] = ...) -> None: ...

class FunctionTask(_message.Message):
    __slots__ = ("task_id", "operation_id", "name", "args")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    task_id: int
    operation_id: int
    name: str
    args: bytes
    def __init__(self, task_id: _Optional[int] = ..., operation_id: _Optional[int] = ..., name: _Optional[str] = ..., args: _Optional[bytes] = ...) -> None: ...

class Event(_message.Message):
    __slots__ = ("time_unix_nano", "source", "operation", "phase", "resource_type", "resource_id", "file", "duration_nano", "error", "data", "meta_json")
    TIME_UNIX_NANO_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    FILE_FIELD_NUMBER: _ClassVar[int]
    DURATION_NANO_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    META_JSON_FIELD_NUMBER: _ClassVar[int]
    time_unix_nano: int
    source: str
    operation: str
    phase: str
    resource_type: str
    resource_id: str
    file: str
    duration_nano: int
    error: Error
    data: bytes
    meta_json: bytes
    def __init__(self, time_unix_nano: _Optional[int] = ..., source: _Optional[str] = ..., operation: _Optional[str] = ..., phase: _Optional[str] = ..., resource_type: _Optional[str] = ..., resource_id: _Optional[str] = ..., file: _Optional[str] = ..., duration_nano: _Optional[int] = ..., error: _Optional[_Union[Error, _Mapping]] = ..., data: _Optional[bytes] = ..., meta_json: _Optional[bytes] = ...) -> None: ...

class OperationFinished(_message.Message):
    __slots__ = ("operation_id", "error", "diff_json", "diff_tokens")
    OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    DIFF_JSON_FIELD_NUMBER: _ClassVar[int]
    DIFF_TOKENS_FIELD_NUMBER: _ClassVar[int]
    operation_id: int
    error: Error
    diff_json: bytes
    diff_tokens: _containers.RepeatedCompositeFieldContainer[Token]
    def __init__(self, operation_id: _Optional[int] = ..., error: _Optional[_Union[Error, _Mapping]] = ..., diff_json: _Optional[bytes] = ..., diff_tokens: _Optional[_Iterable[_Union[Token, _Mapping]]] = ...) -> None: ...

class CompleteRequest(_message.Message):
    __slots__ = ("task_id", "state", "function")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    FUNCTION_FIELD_NUMBER: _ClassVar[int]
    task_id: int
    state: StateResult
    function: FunctionResult
    def __init__(self, task_id: _Optional[int] = ..., state: _Optional[_Union[StateResult, _Mapping]] = ..., function: _Optional[_Union[FunctionResult, _Mapping]] = ...) -> None: ...

class CompleteResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StateResult(_message.Message):
    __slots__ = ("entities", "exists", "error")
    ENTITIES_FIELD_NUMBER: _ClassVar[int]
    EXISTS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    entities: _containers.RepeatedScalarFieldContainer[bytes]
    exists: bool
    error: Error
    def __init__(self, entities: _Optional[_Iterable[bytes]] = ..., exists: _Optional[bool] = ..., error: _Optional[_Union[Error, _Mapping]] = ...) -> None: ...

class FunctionResult(_message.Message):
    __slots__ = ("result", "error")
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    result: bytes
    error: Error
    def __init__(self, result: _Optional[bytes] = ..., error: _Optional[_Union[Error, _Mapping]] = ...) -> None: ...

class EntitiesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class EntitiesResponse(_message.Message):
    __slots__ = ("entities",)
    ENTITIES_FIELD_NUMBER: _ClassVar[int]
    entities: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, entities: _Optional[_Iterable[bytes]] = ...) -> None: ...

class FindRequest(_message.Message):
    __slots__ = ("address",)
    ADDRESS_FIELD_NUMBER: _ClassVar[int]
    address: str
    def __init__(self, address: _Optional[str] = ...) -> None: ...

class EntityResponse(_message.Message):
    __slots__ = ("entity",)
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    entity: bytes
    def __init__(self, entity: _Optional[bytes] = ...) -> None: ...

class FindByTypeRequest(_message.Message):
    __slots__ = ("path",)
    PATH_FIELD_NUMBER: _ClassVar[int]
    path: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, path: _Optional[_Iterable[str]] = ...) -> None: ...

class OutputsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class OutputsResponse(_message.Message):
    __slots__ = ("outputs_json",)
    OUTPUTS_JSON_FIELD_NUMBER: _ClassVar[int]
    outputs_json: bytes
    def __init__(self, outputs_json: _Optional[bytes] = ...) -> None: ...

class EncodeOptions(_message.Message):
    __slots__ = ("include_computed", "include_empty", "reveal_sensitive", "show_references")
    INCLUDE_COMPUTED_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_EMPTY_FIELD_NUMBER: _ClassVar[int]
    REVEAL_SENSITIVE_FIELD_NUMBER: _ClassVar[int]
    SHOW_REFERENCES_FIELD_NUMBER: _ClassVar[int]
    include_computed: bool
    include_empty: bool
    reveal_sensitive: bool
    show_references: bool
    def __init__(self, include_computed: _Optional[bool] = ..., include_empty: _Optional[bool] = ..., reveal_sensitive: _Optional[bool] = ..., show_references: _Optional[bool] = ...) -> None: ...

class EncodeSavedEntityRequest(_message.Message):
    __slots__ = ("entity", "options", "tokens")
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    TOKENS_FIELD_NUMBER: _ClassVar[int]
    entity: bytes
    options: EncodeOptions
    tokens: bool
    def __init__(self, entity: _Optional[bytes] = ..., options: _Optional[_Union[EncodeOptions, _Mapping]] = ..., tokens: _Optional[bool] = ...) -> None: ...

class EncodeSavedEntityResponse(_message.Message):
    __slots__ = ("text", "tokens")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    TOKENS_FIELD_NUMBER: _ClassVar[int]
    text: bytes
    tokens: _containers.RepeatedCompositeFieldContainer[Token]
    def __init__(self, text: _Optional[bytes] = ..., tokens: _Optional[_Iterable[_Union[Token, _Mapping]]] = ...) -> None: ...

class EncodeEntityRequest(_message.Message):
    __slots__ = ("entity", "options", "tokens")
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    TOKENS_FIELD_NUMBER: _ClassVar[int]
    entity: bytes
    options: EncodeOptions
    tokens: bool
    def __init__(self, entity: _Optional[bytes] = ..., options: _Optional[_Union[EncodeOptions, _Mapping]] = ..., tokens: _Optional[bool] = ...) -> None: ...

class EncodeEntityResponse(_message.Message):
    __slots__ = ("text", "tokens")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    TOKENS_FIELD_NUMBER: _ClassVar[int]
    text: bytes
    tokens: _containers.RepeatedCompositeFieldContainer[Token]
    def __init__(self, text: _Optional[bytes] = ..., tokens: _Optional[_Iterable[_Union[Token, _Mapping]]] = ...) -> None: ...
