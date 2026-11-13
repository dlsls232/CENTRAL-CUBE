"""Length-prefixed JSON protocol with strict size and shape validation."""
from __future__ import annotations

import asyncio
import json
import struct
from typing import Any

MAX_MESSAGE_BYTES = 1_048_576
_HEADER = struct.Struct("!I")


class ProtocolError(Exception):
    """Raised when a peer sends an invalid protocol frame."""


def encode_message(message: dict[str, Any]) -> bytes:
    if not isinstance(message, dict):
        raise ProtocolError("Message must be a JSON object")
    try:
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("Message is not JSON serializable") from exc
    if not payload or len(payload) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Message size is outside the allowed range")
    return _HEADER.pack(len(payload)) + payload


async def send_message(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    writer.write(encode_message(message))
    await writer.drain()


async def read_message(reader: asyncio.StreamReader) -> dict[str, Any]:
    try:
        header = await reader.readexactly(_HEADER.size)
        (size,) = _HEADER.unpack(header)
        if size < 2 or size > MAX_MESSAGE_BYTES:
            raise ProtocolError("Invalid frame length")
        raw = await reader.readexactly(size)
        value = json.loads(raw.decode("utf-8"))
    except (asyncio.IncompleteReadError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("Incomplete or malformed message") from exc
    if not isinstance(value, dict):
        raise ProtocolError("Top-level JSON value must be an object")
    return value
