from central_cube.core.pairing import PairingCode


def test_pairing_code_is_single_use():
    pairing = PairingCode()
    code = pairing.display_code
    assert pairing.verify_once(code) is True
    assert pairing.verify_once(code) is False


def test_wrong_code_does_not_consume_valid_code():
    pairing = PairingCode()
    code = pairing.display_code
    assert pairing.verify_once("wrong-code") is False
    assert pairing.verify_once(code) is True


def test_pairing_ttl_bounds_are_enforced():
    import pytest
    with pytest.raises(ValueError):
        PairingCode(ttl_seconds=29)
    with pytest.raises(ValueError):
        PairingCode(ttl_seconds=901)


def test_pairing_code_expires(monkeypatch):
    import central_cube.core.pairing as pairing_module
    now = [100.0]
    monkeypatch.setattr(pairing_module.time, "monotonic", lambda: now[0])
    pairing = PairingCode(ttl_seconds=30)
    code = pairing.display_code
    now[0] = 131.0
    assert pairing.verify_once(code) is False


def test_pairing_code_locks_after_five_failed_attempts():
    pairing = PairingCode()
    code = pairing.display_code
    for _ in range(5):
        assert pairing.verify_once("999999" if code != "999999" else "000000") is False
    assert pairing.verify_once(code) is False
