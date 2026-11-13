import asyncio
import datetime as dt
import hashlib
import ipaddress
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from central_cube.agent.server import AgentServer
from central_cube.core.pairing import PairingCode
from central_cube.network.client import pair_with_agent, send_command


def _issue_cert(ca_key, ca_cert, common_name, *, is_ca=False, san_ip=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(ca_cert.subject)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1))
               .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2))
               .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
               .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True, data_encipherment=False, key_agreement=False, key_cert_sign=is_ca, crl_sign=is_ca, encipher_only=False, decipher_only=False), critical=True))
    if san_ip:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(san_ip))]), critical=False)
    cert = builder.sign(ca_key, hashes.SHA256())
    return key, cert


def _write_pem(path, value):
    path.write_bytes(value)


def test_mtls_client_can_query_agent_system_info(tmp_path):
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CentralCube Test CA")])
    ca_cert = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
               .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1))
               .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2))
               .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
               .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
               .sign(ca_key, hashes.SHA256()))
    server_key, server_cert = _issue_cert(ca_key, ca_cert, "localhost", san_ip="127.0.0.1")
    client_key, client_cert = _issue_cert(ca_key, ca_cert, "controller")
    ca_file, server_cert_file, server_key_file = tmp_path / "ca.pem", tmp_path / "server.pem", tmp_path / "server.key"
    client_cert_file, client_key_file = tmp_path / "client.pem", tmp_path / "client.key"
    _write_pem(ca_file, ca_cert.public_bytes(serialization.Encoding.PEM))
    _write_pem(server_cert_file, server_cert.public_bytes(serialization.Encoding.PEM))
    _write_pem(server_key_file, server_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    _write_pem(client_cert_file, client_cert.public_bytes(serialization.Encoding.PEM))
    _write_pem(client_key_file, client_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))

    async def scenario():
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(server_cert_file, server_key_file)
        context.load_verify_locations(cafile=ca_file)
        context.verify_mode = ssl.CERT_REQUIRED
        client_fingerprint = hashlib.sha256(client_cert.public_bytes(serialization.Encoding.DER)).hexdigest()
        pairing = PairingCode(ttl_seconds=300)
        pairing_code = pairing.display_code
        allowlist_file = tmp_path / "clients.json"
        allowlist_file.write_text("[]", encoding="utf-8")
        agent = AgentServer("127.0.0.1", 0, context, audit_path=tmp_path / "agent.jsonl",
                            allowed_client_fingerprints=set(), pairing_code=pairing,
                            allowlist_path=allowlist_file)
        await agent.start()
        port = agent._server.sockets[0].getsockname()[1]
        fingerprint = hashlib.sha256(server_cert.public_bytes(serialization.Encoding.DER)).hexdigest()
        try:
            paired = await asyncio.to_thread(pair_with_agent, "127.0.0.1", port,
                ca_file=str(ca_file), client_cert=str(client_cert_file), client_key=str(client_key_file),
                fingerprint=fingerprint, pairing_code=pairing_code)
            assert paired["status"] == "paired"
            assert client_fingerprint in allowlist_file.read_text(encoding="utf-8")
            result = await asyncio.to_thread(send_command, "127.0.0.1", port,
                ca_file=str(ca_file), client_cert=str(client_cert_file), client_key=str(client_key_file),
                fingerprint=fingerprint, command="system_info")
            assert result["status"] == "completed"
            assert result["data"]["hostname"]
            assert (tmp_path / "agent.jsonl").exists()
        finally:
            await agent.stop()

        # A valid CA-signed client certificate is still denied unless its leaf fingerprint is allowlisted.
        denied = AgentServer("127.0.0.1", 0, context, allowed_client_fingerprints=set())
        await denied.start()
        denied_port = denied._server.sockets[0].getsockname()[1]
        try:
            denied_result = await asyncio.to_thread(send_command, "127.0.0.1", denied_port,
                ca_file=str(ca_file), client_cert=str(client_cert_file), client_key=str(client_key_file),
                fingerprint=fingerprint, command="ping")
            assert denied_result["status"] == "rejected"
            assert "not authorized" in denied_result["error"]
        finally:
            await denied.stop()
    asyncio.run(scenario())


def test_fingerprint_format_is_strict():
    from central_cube.network.client import normalize_fingerprint
    import pytest
    assert normalize_fingerprint("sha256:" + "AB" * 32) == "ab" * 32
    with pytest.raises(ValueError):
        normalize_fingerprint("not-a-fingerprint")
    with pytest.raises(ValueError):
        normalize_fingerprint("z" * 64)


def test_power_command_requires_local_confirmation_before_network():
    from central_cube.network.client import pair_with_agent, send_command
    import pytest
    with pytest.raises(ValueError, match="confirmation"):
        send_command("localhost", 9443, ca_file="ca.pem", client_cert="client.pem",
                     client_key="client.key", fingerprint="a" * 64, command="shutdown")


def test_unknown_command_is_rejected_before_network():
    from central_cube.network.client import pair_with_agent, send_command
    import pytest
    with pytest.raises(ValueError, match="Unsupported"):
        send_command("localhost", 9443, ca_file="ca.pem", client_cert="client.pem",
                     client_key="client.key", fingerprint="a" * 64, command="powershell")


def test_pairing_timeout_is_bounded_before_network_access():
    import pytest

    for timeout in (0, -1, 60.1):
        with pytest.raises(ValueError, match="Timeout"):
            pair_with_agent(
                "localhost", 9443, ca_file="missing-ca.pem",
                client_cert="missing-client.pem", client_key="missing-key.pem",
                fingerprint="a" * 64, pairing_code="123456", timeout=timeout,
            )
