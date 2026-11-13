"""Synchronous mTLS controller client with explicit certificate pinning."""
from __future__ import annotations

import hashlib
import socket
import ssl
import uuid
from typing import Any

from central_cube.network.protocol import ProtocolError, encode_message, read_message


class AgentConnectionError(ConnectionError):
    """TLS, pinning, timeout or protocol failure while contacting an agent."""


def normalize_fingerprint(value: str) -> str:
    normalized = value.lower().replace("sha256:", "").replace(":", "").replace(" ", "")
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError("Fingerprint must be a SHA-256 hex digest")
    return normalized


def send_command(
    host: str,
    port: int,
    *,
    ca_file: str,
    client_cert: str,
    client_key: str,
    fingerprint: str,
    command: str,
    confirmed: bool = False,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Send one command over mTLS; validate CA chain and the pinned leaf certificate."""
    if command not in {"ping", "system_info", "shutdown", "restart", "sleep"}:
        raise ValueError("Unsupported command")
    if command in {"shutdown", "restart", "sleep"} and not confirmed:
        raise ValueError("Power commands require explicit user confirmation")
    if not 0.1 <= timeout <= 60:
        raise ValueError("Timeout must be between 0.1 and 60 seconds")
    expected = normalize_fingerprint(fingerprint)
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca_file)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(client_cert, client_key)
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            raw.settimeout(timeout)
            with context.wrap_socket(raw, server_hostname=host) as tls:
                peer_cert = tls.getpeercert(binary_form=True)
                actual = hashlib.sha256(peer_cert).hexdigest()
                if not __import__("hmac").compare_digest(actual, expected):
                    raise AgentConnectionError("Agent certificate fingerprint mismatch")
                tls.sendall(encode_message({
                    "command_id": str(uuid.uuid4()),
                    "command": command,
                    "confirmed": bool(confirmed),
                }))
                # Protocol frames are length-prefixed; socket.makefile provides a buffered reader.
                with tls.makefile("rb") as reader:
                    header = reader.read(4)
                    if len(header) != 4:
                        raise AgentConnectionError("Agent closed connection before response")
                    size = int.from_bytes(header, "big")
                    from central_cube.network.protocol import MAX_MESSAGE_BYTES
                    if not 2 <= size <= MAX_MESSAGE_BYTES:
                        raise ProtocolError("Invalid response frame length")
                    payload = reader.read(size)
                    if len(payload) != size:
                        raise AgentConnectionError("Incomplete response frame")
                    import json
                    response = json.loads(payload.decode("utf-8"))
                    if not isinstance(response, dict):
                        raise ProtocolError("Agent response must be a JSON object")
                    return response
    except (OSError, ssl.SSLError, ProtocolError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise AgentConnectionError(str(exc)) from exc


def pair_with_agent(
    host: str,
    port: int,
    *,
    ca_file: str,
    client_cert: str,
    client_key: str,
    fingerprint: str,
    pairing_code: str,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Enroll this client certificate using the agent's one-time out-of-band code."""
    if not isinstance(pairing_code, str) or not pairing_code.isdigit() or len(pairing_code) != 6:
        raise ValueError("Pairing code must contain six digits")
    if not 0.1 <= timeout <= 60:
        raise ValueError("Timeout must be between 0.1 and 60 seconds")
    expected = normalize_fingerprint(fingerprint)
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=ca_file)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(client_cert, client_key)
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            raw.settimeout(timeout)
            with context.wrap_socket(raw, server_hostname=host) as tls:
                peer_cert = tls.getpeercert(binary_form=True)
                actual = hashlib.sha256(peer_cert).hexdigest()
                if not __import__("hmac").compare_digest(actual, expected):
                    raise AgentConnectionError("Agent certificate fingerprint mismatch")
                tls.sendall(encode_message({
                    "command_id": str(uuid.uuid4()),
                    "command": "pair",
                    "pairing_code": pairing_code,
                }))
                with tls.makefile("rb") as reader:
                    header = reader.read(4)
                    if len(header) != 4:
                        raise AgentConnectionError("Agent closed connection before pairing response")
                    size = int.from_bytes(header, "big")
                    from central_cube.network.protocol import MAX_MESSAGE_BYTES
                    if not 2 <= size <= MAX_MESSAGE_BYTES:
                        raise ProtocolError("Invalid response frame length")
                    payload = reader.read(size)
                    if len(payload) != size:
                        raise AgentConnectionError("Incomplete pairing response")
                    import json
                    response = json.loads(payload.decode("utf-8"))
                    if not isinstance(response, dict):
                        raise ProtocolError("Agent response must be a JSON object")
                    return response
    except (OSError, ssl.SSLError, ProtocolError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise AgentConnectionError(str(exc)) from exc
