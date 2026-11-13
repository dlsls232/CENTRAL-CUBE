"""Run the agent with explicitly provisioned mutual-TLS credentials."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import platform
import ssl
from pathlib import Path
from platformdirs import user_data_dir

from central_cube import __version__
from central_cube.agent.server import AgentServer
from central_cube.core.pairing import PairingCode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CENTRAL CUBE Agent (mutual TLS)")
    parser.add_argument("--version", action="version", version=f"CentralCubeAgent {__version__}")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (IPv4 or IPv6)")
    parser.add_argument("--port", type=int, default=9443)
    parser.add_argument("--cert", required=True, help="Agent TLS certificate PEM")
    parser.add_argument("--key", required=True, help="Agent private key PEM")
    parser.add_argument("--client-ca", required=True, help="CA PEM used to verify controller certificates")
    parser.add_argument("--client-allowlist", required=True, help="JSON array of authorized client certificate SHA-256 fingerprints; created empty when missing")
    parser.add_argument("--pairing-ttl", type=int, default=300, help="One-time pairing code lifetime in seconds (30-900)")
    parser.add_argument("--enable-power-actions", action="store_true", help="Enable shutdown/restart/sleep (explicit request confirmation still required)")
    parser.add_argument("--audit-log", default=str(Path(user_data_dir("CentralCubeAgent", "CentralCube")) / "agent_audit.jsonl"), help="Append-only JSONL audit log path")
    return parser


async def serve(args: argparse.Namespace) -> None:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.cert, args.key)
    context.load_verify_locations(cafile=args.client_ca)
    context.verify_mode = ssl.CERT_REQUIRED
    allowlist_path = Path(args.client_allowlist)
    allowlist_path.parent.mkdir(parents=True, exist_ok=True)
    if not allowlist_path.exists():
        allowlist_path.write_text("[]\n", encoding="utf-8")
    with allowlist_path.open(encoding="utf-8") as allowlist_file:
        allowed_clients = json.load(allowlist_file)
    if not isinstance(allowed_clients, list) or not all(isinstance(item, str) for item in allowed_clients):
        raise ValueError("Client allowlist must be a JSON array of SHA-256 hex fingerprints")
    pairing = PairingCode(ttl_seconds=args.pairing_ttl)
    print(f"One-time pairing code (valid {args.pairing_ttl} seconds): {pairing.display_code}", flush=True)
    server = AgentServer(args.host, args.port, context,
                         enable_power_actions=args.enable_power_actions, audit_path=args.audit_log,
                         allowed_client_fingerprints=set(allowed_clients), pairing_code=pairing,
                         allowlist_path=allowlist_path)
    await server.start()
    logging.info("Agent listening on %s:%s (mutual TLS required)", args.host, args.port)
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("Port must be between 1 and 65535")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(f"CENTRAL CUBE Agent {__version__} · {platform.node()}")
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        pass
    except (OSError, ssl.SSLError, ValueError) as exc:
        logging.error("Agent startup failed: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
