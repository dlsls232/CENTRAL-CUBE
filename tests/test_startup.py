import os

import pytest

from central_cube.core.startup import build_startup_command, is_app_startup_enabled, set_app_startup


def test_frozen_startup_command_points_to_executable():
    command = build_startup_command(frozen=True, executable=r"C:\Program Files\CENTRAL CUBE\CentralCube.exe")
    assert "CentralCube.exe" in command


def test_development_startup_command_uses_module_entrypoint():
    command = build_startup_command(frozen=False, executable="python")
    assert "-m" in command
    assert "central_cube.main" in command

@pytest.mark.skipif(os.name == "nt", reason="Non-Windows guard only")
def test_registry_autostart_is_rejected_off_windows():
    with pytest.raises(OSError, match="only on Windows"):
        set_app_startup(True)
    assert is_app_startup_enabled() is False
