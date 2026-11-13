import ssl
import pytest

from central_cube.agent.server import AgentServer


def test_server_refuses_missing_tls_context():
    with pytest.raises(ValueError):
        AgentServer("127.0.0.1", 9443, None)


def test_server_requires_explicit_ssl_context():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    server = AgentServer("127.0.0.1", 9443, context)
    assert server.host == "127.0.0.1"
    assert server.port == 9443


def test_server_requires_client_certificate_authentication():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    with pytest.raises(ValueError, match="client certificates"):
        AgentServer("127.0.0.1", 9443, context)


def test_server_accepts_only_mtls_context():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    server = AgentServer("127.0.0.1", 9443, context)
    assert server.enable_power_actions is False


def test_command_replay_store_survives_server_restart(tmp_path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    allowlist = tmp_path / "clients.json"
    first = AgentServer("127.0.0.1", 9443, context, allowlist_path=allowlist)
    assert first._claim_command_id("request-123") is True
    second = AgentServer("127.0.0.1", 9443, context, allowlist_path=allowlist)
    assert second._claim_command_id("request-123") is False



def test_command_id_claim_is_atomic_and_persistent(tmp_path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    allowlist = tmp_path / "clients.json"
    first = AgentServer("127.0.0.1", 9443, context, allowlist_path=allowlist)
    assert first._claim_command_id("same-request-id") is True
    assert first._claim_command_id("same-request-id") is False
    second = AgentServer("127.0.0.1", 9443, context, allowlist_path=allowlist)
    assert second._claim_command_id("same-request-id") is False


def test_command_id_claim_without_database_rejects_duplicate():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    server = AgentServer("127.0.0.1", 9443, context)
    assert server._claim_command_id("request-123") is True
    assert server._claim_command_id("request-123") is False


def test_command_ids_are_not_pruned_from_durable_replay_store(tmp_path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    allowlist = tmp_path / "clients.json"
    server = AgentServer("127.0.0.1", 9443, context, allowlist_path=allowlist)

    for index in range(25):
        assert server._claim_command_id(f"historical-command-{index}") is True

    from contextlib import closing
    with closing(__import__("sqlite3").connect(server.replay_path)) as db:
        count = db.execute("SELECT COUNT(*) FROM used_commands").fetchone()[0]
    assert count == 25

    restarted = AgentServer("127.0.0.1", 9443, context, allowlist_path=allowlist)
    assert restarted._claim_command_id("historical-command-0") is False


def test_agent_rate_limits_bursts_per_source(monkeypatch):
    import central_cube.agent.server as server_module

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    server = AgentServer("127.0.0.1", 9443, context)
    now = [100.0]
    monkeypatch.setattr(server_module.time, "monotonic", lambda: now[0])

    assert all(server._allow_peer(("192.0.2.10", 1234)) for _ in range(20))
    assert server._allow_peer(("192.0.2.10", 1234)) is False
    now[0] += 1.0
    assert server._allow_peer(("192.0.2.10", 1234)) is True
    assert server._allow_peer(("192.0.2.11", 1234)) is True


def test_agent_rate_limit_source_table_is_bounded():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    server = AgentServer("127.0.0.1", 9443, context)
    server._rate_limit_max_sources = 3
    for index in range(10):
        assert server._allow_peer((f"192.0.2.{index}", 1234)) is True
    assert len(server._rate_limit_buckets) == 3


def test_revoke_client_persists_and_survives_restart(tmp_path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    fingerprint = "a" * 64
    allowlist = tmp_path / "clients.json"
    allowlist.write_text(__import__("json").dumps([fingerprint]), encoding="utf-8")
    server = AgentServer("127.0.0.1", 9443, context,
                         allowed_client_fingerprints={fingerprint},
                         allowlist_path=allowlist)

    assert server.revoke_client("sha256:" + ":".join([fingerprint[i:i+2] for i in range(0, 64, 2)])) is True
    assert fingerprint not in server.allowed_client_fingerprints
    assert __import__("json").loads(allowlist.read_text(encoding="utf-8")) == []

    restarted = AgentServer("127.0.0.1", 9443, context,
                            allowed_client_fingerprints=set(
                                __import__("json").loads(allowlist.read_text(encoding="utf-8"))),
                            allowlist_path=allowlist)
    assert fingerprint not in restarted.allowed_client_fingerprints
    assert restarted.revoke_client(fingerprint) is False


def test_revoke_client_rejects_invalid_fingerprint(tmp_path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    server = AgentServer("127.0.0.1", 9443, context, allowlist_path=tmp_path / "clients.json")
    with pytest.raises(ValueError, match="SHA-256"):
        server.revoke_client("not-a-fingerprint")
