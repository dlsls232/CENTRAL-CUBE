"""Strict allowlist for commands supported by the agent."""
from __future__ import annotations

import platform
import subprocess
import time
from typing import Any

ALLOWED_COMMANDS = frozenset({"ping", "system_info", "shutdown", "restart", "sleep"})


def system_info() -> dict[str, Any]:
    return {
        "hostname": platform.node(),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
    }


def execute_command(name: str, *, dry_run: bool = True) -> dict[str, Any]:
    if name not in ALLOWED_COMMANDS:
        return {"status": "rejected", "error": "Command is not allowed"}
    if name == "ping":
        return {"status": "completed", "timestamp": time.time()}
    if name == "system_info":
        return {"status": "completed", "data": system_info()}
    if dry_run:
        return {"status": "accepted", "details": "Power action disabled in development mode"}
    if platform.system() != "Windows":
        return {"status": "failed", "error": "Power commands are supported only on Windows"}
    commands = {
        "shutdown": ["shutdown", "/s", "/t", "5"],
        "restart": ["shutdown", "/r", "/t", "5"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    }
    try:
        subprocess.Popen(commands[name], shell=False, close_fds=True)
    except OSError as exc:
        return {"status": "failed", "error": str(exc)}
    return {"status": "accepted", "details": "Windows accepted the power action request"}
