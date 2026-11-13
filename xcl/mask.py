"""Masks for sensitive values in state and events.

A mask says how a sensitive value is written where it would otherwise be
written in plain text: in state, with ``state_mask``, and in event data, with
``event_mask``. State needs a reversible mask, so the value can be read back;
:func:`aes256gcm` is the one that is. Events are redacted unless another
mask is given.
"""

from __future__ import annotations

from xcl._core import core_pb2


class Mask:
    """A mask to give as ``state_mask`` or ``event_mask``; build one with the functions below."""

    __slots__ = ("_message", "_name")

    def __init__(self, message: core_pb2.Mask, name: str) -> None:
        self._message = message
        self._name = name

    @property
    def name(self) -> str:
        """The mask's name: ``aes256gcm``, ``hmac_sha256``, ``redact`` or ``omit``."""
        return self._name

    def _to_proto(self) -> core_pb2.Mask:
        return self._message

    def __repr__(self) -> str:
        return f"xcl.mask.{self._name}()"


def aes256gcm(key: bytes) -> Mask:
    """Encrypt sensitive values with AES-256-GCM under ``key``, 32 bytes; reversible, so it suits state.

    :param key: the 32-byte key
    :returns: the mask
    :raises ValueError: for a key that is not 32 bytes
    """
    if len(key) != 32:
        raise ValueError(f"an AES-256-GCM key is 32 bytes, got {len(key)}")
    return Mask(core_pb2.Mask(aes256gcm_key=bytes(key)), "aes256gcm")


def hmac_sha256(key: bytes) -> Mask:
    """Replace sensitive values with their HMAC-SHA256 under ``key``; one-way, so values still compare.

    :param key: the key
    :returns: the mask
    :raises ValueError: for an empty key
    """
    if not key:
        raise ValueError("an HMAC-SHA256 key must not be empty")
    return Mask(core_pb2.Mask(hmac_sha256_key=bytes(key)), "hmac_sha256")


def redact() -> Mask:
    """Replace sensitive values with the marker ``(sensitive)``; the default for events.

    :returns: the mask
    """
    return Mask(core_pb2.Mask(redact=True), "redact")


def omit() -> Mask:
    """Leave sensitive values out entirely.

    :returns: the mask
    """
    return Mask(core_pb2.Mask(omit=True), "omit")


__all__ = ["Mask", "aes256gcm", "hmac_sha256", "redact", "omit"]
