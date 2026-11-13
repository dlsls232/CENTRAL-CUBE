from central_cube.agent.commands import execute_command


def test_system_info_is_available():
    result = execute_command("system_info")
    assert result["status"] == "completed"
    assert "hostname" in result["data"]


def test_unknown_command_is_rejected():
    assert execute_command("run_powershell", dry_run=False)["status"] == "rejected"


def test_power_action_is_safe_in_development_mode():
    result = execute_command("shutdown")
    assert result["status"] == "accepted"
    assert "disabled" in result["details"]


def test_power_actions_remain_disabled_by_default():
    for command in ("shutdown", "restart", "sleep"):
        assert execute_command(command)["status"] == "accepted"
        assert "disabled" in execute_command(command)["details"]


def test_system_info_contains_expected_fields():
    data = execute_command("system_info")["data"]
    assert {"hostname", "os", "architecture"}.issubset(data)


def test_power_action_reports_platform_limit_without_running_shell(monkeypatch):
    import central_cube.agent.commands as commands
    monkeypatch.setattr(commands.platform, "system", lambda: "Linux")
    result = commands.execute_command("shutdown", dry_run=False)
    assert result["status"] == "failed"
    assert "only on Windows" in result["error"]


def test_all_supported_command_names_are_explicit():
    from central_cube.agent.commands import ALLOWED_COMMANDS
    assert ALLOWED_COMMANDS == {"ping", "system_info", "shutdown", "restart", "sleep"}


def test_windows_power_action_uses_argument_list_without_shell(monkeypatch):
    import central_cube.agent.commands as commands
    calls = []
    monkeypatch.setattr(commands.platform, "system", lambda: "Windows")
    monkeypatch.setattr(commands.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)))
    result = commands.execute_command("restart", dry_run=False)
    assert result["status"] == "accepted"
    assert calls[0][0] == ["shutdown", "/r", "/t", "5"]
    assert calls[0][1]["shell"] is False


def test_windows_power_action_handles_os_error(monkeypatch):
    import central_cube.agent.commands as commands
    def fail(*args, **kwargs):
        raise OSError("permission denied")
    monkeypatch.setattr(commands.platform, "system", lambda: "Windows")
    monkeypatch.setattr(commands.subprocess, "Popen", fail)
    result = commands.execute_command("shutdown", dry_run=False)
    assert result == {"status": "failed", "error": "permission denied"}
