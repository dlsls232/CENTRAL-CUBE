"""Per-user Windows logon startup registration for the desktop controller."""
from __future__ import annotations

import os
import shlex
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CentralCube"


def build_startup_command(*, frozen: bool | None = None, executable: str | None = None) -> str:
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    exe = executable or sys.executable
    parts = [exe] if is_frozen else [exe, "-m", "central_cube.main"]
    if os.name == "nt":
        import subprocess
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def set_app_startup(enabled: bool) -> None:
    if os.name != "nt":
        raise OSError("Windows startup registration is available only on Windows")
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, build_startup_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def is_app_startup_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
