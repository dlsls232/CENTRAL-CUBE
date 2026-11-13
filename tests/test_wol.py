import socket

import pytest

from central_cube.network.wol import build_magic_packet, send_magic_packet


def test_magic_packet_is_102_bytes():
    packet = build_magic_packet("AA:BB:CC:DD:EE:FF")
    assert len(packet) == 102
    assert packet[:6] == b"\xff" * 6
    assert packet[6:] == bytes.fromhex("AABBCCDDEEFF") * 16


def test_mac_validation_rejects_invalid_values():
    for value in ("", "AA:BB:CC", "GG:BB:CC:DD:EE:FF", "AABBCCDDEEFF"):
        with pytest.raises(ValueError):
            build_magic_packet(value)


def test_wol_uses_local_limited_broadcast(monkeypatch):
    calls = {}
    class FakeSocket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def setsockopt(self, *args): calls["broadcast"] = args
        def sendto(self, packet, address):
            calls["packet"] = packet
            calls["address"] = address
            return len(packet)
    monkeypatch.setattr(socket, "socket", lambda *args: FakeSocket())
    assert send_magic_packet("00-11-22-33-44-55") == 102
    assert calls["address"] == ("255.255.255.255", 9)
    assert calls["broadcast"][-1] == 1


def test_wol_refuses_nonstandard_port():
    with pytest.raises(ValueError):
        send_magic_packet("00:11:22:33:44:55", port=1900)
