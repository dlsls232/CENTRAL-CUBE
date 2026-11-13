"""LAN-only Wake-on-LAN magic packet sender."""
from __future__ import annotations

import re
import socket


_MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


def build_magic_packet(mac_address: str) -> bytes:
    if not isinstance(mac_address, str) or not _MAC_RE.fullmatch(mac_address.strip()):
        raise ValueError("MAC address must contain six hexadecimal octets")
    mac = bytes.fromhex(mac_address.strip().replace("-", ":").replace(":", ""))
    return b"\xff" * 6 + mac * 16


def send_magic_packet(mac_address: str, *, port: int = 9) -> int:
    """Broadcast a WoL packet on the local LAN; this does not cross routers."""
    if port != 9:
        raise ValueError("Only the conventional UDP port 9 is supported")
    packet = build_magic_packet(mac_address)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        return sock.sendto(packet, ("255.255.255.255", port))
