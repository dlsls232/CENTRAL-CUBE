"""Agent TCP server. TLS and client-certificate authentication are mandatory."""
from __future__ import annotations

import asyncio
import hashlib
import json
import ssl
import sqlite3
from collections import deque
from datetime import datetime, timezone
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from central_cube.agent.commands import ALLOWED_COMMANDS, execute_command
from central_cube.core.pairing import PairingCode
from central_cube.network.protocol import ProtocolError, read_message, send_message


class AgentServer:
    def __init__(self, host: str, port: int, tls_context: ssl.SSLContext, *,
                 enable_power_actions: bool = False, audit_path: str | Path | None = None,
                 allowed_client_fingerprints: set[str] | None = None,
                 pairing_code: PairingCode | None = None, allowlist_path: str | Path | None = None) -> None:
        if tls_context is None:
            raise ValueError("A TLS context is required")
        if tls_context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("TLS context must require and verify client certificates")
        self.host = host
        self.port = port
        self.tls_context = tls_context
        self.enable_power_actions = enable_power_actions
        self.audit_path = Path(audit_path) if audit_path else None
        self.allowed_client_fingerprints = {value.lower().replace(":", "").replace("sha256", "") for value in (allowed_client_fingerprints or set())}
        self.pairing_code = pairing_code
        self.allowlist_path = Path(allowlist_path) if allowlist_path else None
        if any(len(value) != 64 or any(char not in "0123456789abcdef" for char in value) for value in self.allowed_client_fingerprints):
            raise ValueError("Allowed client fingerprints must be SHA-256 hex digests")
        self._server: asyncio.AbstractServer | None = None
        # Per-source token bucket: tolerate short bursts, then limit sustained traffic.
        self._rate_limit_capacity = 20.0
        self._rate_limit_refill_per_second = 1.0
        self._rate_limit_buckets: dict[str, tuple[float, float]] = {}
        self._rate_limit_max_sources = 4096
        self._seen_commands: set[str] = set()
        self._seen_order: deque[str] = deque(maxlen=10000)
        # Durable replay protection survives agent restarts. IDs are never pruned.
        replay_base = self.allowlist_path or self.audit_path
        self.replay_path = (replay_base.with_suffix(replay_base.suffix + ".replay.sqlite3")
                            if replay_base else None)
        if self.replay_path:
            self.replay_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.replay_path)) as db:
                with db:
                    db.execute("CREATE TABLE IF NOT EXISTS used_commands (command_id TEXT PRIMARY KEY, used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
                    db.execute("CREATE INDEX IF NOT EXISTS idx_used_commands_time ON used_commands(used_at)")

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port, ssl=self.tls_context,
            limit=1_048_576,
            ssl_handshake_timeout=10.0,
            ssl_shutdown_timeout=5.0,
        )

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def _audit(self, event: dict[str, Any]) -> None:
        if not self.audit_path:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {"time": datetime.now(timezone.utc).isoformat(), **event}
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _claim_command_id(self, command_id: str) -> bool:
        """Atomically reserve a command ID; safe against concurrent client handlers."""
        if self.replay_path is None:
            if command_id in self._seen_commands:
                return False
            if len(self._seen_order) == self._seen_order.maxlen:
                self._seen_commands.discard(self._seen_order.popleft())
            self._seen_commands.add(command_id)
            self._seen_order.append(command_id)
            return True
        with closing(sqlite3.connect(self.replay_path, timeout=5, isolation_level="IMMEDIATE")) as db:
            with db:
                cursor = db.execute(
                    "INSERT OR IGNORE INTO used_commands(command_id) VALUES (?)",
                    (command_id,),
                )
                if cursor.rowcount != 1:
                    return False
                # Command IDs are retained permanently. Pruning this table would reopen
                # a replay window for any previously accepted ID after enough traffic.
                return True

    def _persist_allowlist(self) -> None:
        if not self.allowlist_path:
            raise OSError("Persistent client allowlist path is not configured")
        self.allowlist_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.allowlist_path.with_suffix(self.allowlist_path.suffix + ".tmp")
        temporary.write_text(json.dumps(sorted(self.allowed_client_fingerprints), indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.allowlist_path)

    def revoke_client(self, fingerprint: str) -> bool:
        """Persistently revoke a client certificate fingerprint for future sessions.

        Existing TLS sessions are not forcibly interrupted; callers should close them
        separately if immediate termination is required.
        """
        normalized = fingerprint.lower().replace(":", "").replace("sha256", "").strip()
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError("Client fingerprint must be a SHA-256 hex digest")
        if normalized not in self.allowed_client_fingerprints:
            return False
        self.allowed_client_fingerprints.remove(normalized)
        try:
            self._persist_allowlist()
        except OSError:
            self.allowed_client_fingerprints.add(normalized)
            raise
        self._audit({"event": "client_certificate_revoked", "client_fingerprint": normalized})
        return True

    def _allow_peer(self, peer: Any) -> bool:
        """Apply a bounded per-source token bucket before reading application data."""
        if isinstance(peer, (tuple, list)) and peer:
            source = str(peer[0])
        else:
            source = str(peer or "unknown")
        now = time.monotonic()
        tokens, updated_at = self._rate_limit_buckets.get(
            source, (self._rate_limit_capacity, now)
        )
        tokens = min(
            self._rate_limit_capacity,
            tokens + max(0.0, now - updated_at) * self._rate_limit_refill_per_second,
        )
        allowed = tokens >= 1.0
        if allowed:
            tokens -= 1.0
        if source not in self._rate_limit_buckets and len(self._rate_limit_buckets) >= self._rate_limit_max_sources:
            # Bound memory under source-address churn; evict the least recently updated entry.
            oldest = min(self._rate_limit_buckets, key=lambda key: self._rate_limit_buckets[key][1])
            self._rate_limit_buckets.pop(oldest, None)
        self._rate_limit_buckets[source] = (tokens, now)
        return allowed

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        if not self._allow_peer(peer):
            self._audit({"peer": str(peer), "status": "rate_limited"})
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, ssl.SSLError):
                pass
            return
        client_fingerprint = ""
        command = None
        try:
            ssl_object = writer.get_extra_info("ssl_object")
            peer_cert = ssl_object.getpeercert(binary_form=True) if ssl_object else None
            client_fingerprint = hashlib.sha256(peer_cert).hexdigest() if peer_cert else ""
            request = await asyncio.wait_for(read_message(reader), timeout=15)
            command_id = request.get("command_id")
            command = request.get("command")
            if (not isinstance(command_id, str) or not 8 <= len(command_id) <= 128
                    or not command_id.isascii()):
                result = {"status": "rejected", "error": "Invalid command id"}
            elif not self._claim_command_id(command_id):
                result = {"status": "rejected", "error": "Duplicate command"}
            elif client_fingerprint not in self.allowed_client_fingerprints:
                candidate = request.get("pairing_code")
                if command == "pair" and self.pairing_code is not None and self.pairing_code.verify_once(candidate):
                    self.allowed_client_fingerprints.add(client_fingerprint)
                    try:
                        self._persist_allowlist()
                        result = {"status": "paired", "details": "Client certificate enrolled"}
                    except OSError as exc:
                        self.allowed_client_fingerprints.discard(client_fingerprint)
                        result = {"status": "failed", "error": f"Could not persist client allowlist: {exc}"}
                else:
                    result = {"status": "rejected", "error": "Client certificate is not authorized or pairing code is invalid"}
            elif command == "pair":
                result = {"status": "rejected", "error": "Client certificate is already paired"}
            elif not isinstance(command, str) or command not in ALLOWED_COMMANDS:
                result = {"status": "rejected", "error": "Command is not allowed"}
            else:
                confirmed = request.get("confirmed", False)
                if not isinstance(confirmed, bool):
                    result = {"status": "rejected", "error": "Invalid confirmation field"}
                elif command in {"shutdown", "restart", "sleep"} and not confirmed:
                    result = {"status": "rejected", "error": "Explicit confirmation is required"}
                elif command in {"shutdown", "restart", "sleep"} and not self.enable_power_actions:
                    result = {"status": "disabled", "error": "Power actions are disabled by agent administrator"}
                else:
                    result = execute_command(command, dry_run=False)
            result.update({"command_id": command_id if isinstance(command_id, str) else None,
                           "peer": str(peer)})
            self._audit({"peer": str(peer), "client_fingerprint": client_fingerprint, "command_id": result["command_id"],
                         "command": command if isinstance(command, str) else None,
                         "status": result.get("status"), "error": result.get("error")})
            await send_message(writer, result)
        except (ProtocolError, ConnectionError, asyncio.CancelledError, asyncio.TimeoutError):
            self._audit({"peer": str(peer), "client_fingerprint": client_fingerprint, "status": "protocol_error"})
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, ssl.SSLError):
                pass
