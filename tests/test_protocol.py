import asyncio

import pytest

from central_cube.network.protocol import ProtocolError, encode_message, read_message


def test_encode_message_round_trip():
    async def scenario():
        frame = encode_message({"command": "ping", "value": 7})
        reader = asyncio.StreamReader()
        reader.feed_data(frame)
        reader.feed_eof()
        assert await read_message(reader) == {"command": "ping", "value": 7}

    asyncio.run(scenario())


def test_rejects_non_object():
    with pytest.raises(ProtocolError):
        encode_message([1, 2, 3])  # type: ignore[arg-type]


def test_rejects_oversized_frame():
    async def scenario():
        reader = asyncio.StreamReader()
        reader.feed_data((1_048_577).to_bytes(4, "big"))
        reader.feed_eof()
        with pytest.raises(ProtocolError):
            await read_message(reader)

    asyncio.run(scenario())


def test_rejects_invalid_json_frame():
    async def scenario():
        reader = asyncio.StreamReader()
        payload = b"not-json"
        reader.feed_data(len(payload).to_bytes(4, "big") + payload)
        reader.feed_eof()
        with pytest.raises(ProtocolError):
            await read_message(reader)
    asyncio.run(scenario())
