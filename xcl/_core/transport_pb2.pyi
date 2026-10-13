from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Request(_message.Message):
    __slots__ = ("id", "handle", "method", "payload")
    ID_FIELD_NUMBER: _ClassVar[int]
    HANDLE_FIELD_NUMBER: _ClassVar[int]
    METHOD_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    id: int
    handle: int
    method: str
    payload: bytes
    def __init__(self, id: _Optional[int] = ..., handle: _Optional[int] = ..., method: _Optional[str] = ..., payload: _Optional[bytes] = ...) -> None: ...

class Response(_message.Message):
    __slots__ = ("id", "status", "payload")
    ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    id: int
    status: int
    payload: bytes
    def __init__(self, id: _Optional[int] = ..., status: _Optional[int] = ..., payload: _Optional[bytes] = ...) -> None: ...
