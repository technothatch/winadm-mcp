import json

import pytest

from winadm_mcp import powershell
from winadm_mcp import server as srv


def test_encode_command_is_utf16le_base64():
    encoded = powershell.encode_command("Get-Service")
    decoded = powershell.parse_json_output  # noqa: F841 - keep import used
    import base64

    raw = base64.b64decode(encoded)
    assert raw.decode("utf-16-le") == "Get-Service"


def test_parse_json_output_handles_array_object_empty():
    assert powershell.parse_json_output('[{"a":1}]') == [{"a": 1}]
    assert powershell.parse_json_output('{"a":1}') == {"a": 1}
    assert powershell.parse_json_output("  \n") is None


def test_parse_json_output_invalid_raises():
    with pytest.raises(json.JSONDecodeError):
        powershell.parse_json_output("not json")


class FakePS:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def __call__(self, script, timeout=30):
        self.calls.append(script)
        for key, value in self.mapping.items():
            if key in script:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected script: {script}")


def test_list_services_formats(monkeypatch):
    rows = [
        {"Name": "Spooler", "DisplayName": "Print Spooler", "Status": "Running", "StartType": "Automatic"},
        {"Name": "Themes", "DisplayName": "Themes", "Status": "Stopped", "StartType": "Manual"},
    ]
    fake = FakePS({"Get-Service": json.dumps(rows)})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    out = srv.list_services()
    assert "Spooler" in out and "Running" in out and "Manual" in out
    assert "DisplayName" in out


def test_list_services_filters(monkeypatch):
    rows = [
        {"Name": "Spooler", "DisplayName": "Print Spooler", "Status": "Running", "StartType": "Automatic"},
        {"Name": "Themes", "DisplayName": "Themes", "Status": "Stopped", "StartType": "Manual"},
    ]
    fake = FakePS({"Get-Service": json.dumps(rows)})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    out = srv.list_services(status="running")
    assert "Spooler" in out and "Themes" not in out
    out = srv.list_services(name="theme")
    assert "Themes" in out and "Spooler" not in out


def test_service_action_write_gate(monkeypatch):
    fake = FakePS({})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    out = srv.service_action("Spooler", "restart", allow_write=False)
    assert out.startswith("error:") and "--allow-write" in out
    assert fake.calls == []


def test_service_action_validates(monkeypatch):
    fake = FakePS({})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    assert srv.service_action("bad; rm -rf /", "stop", allow_write=True).startswith("error:")
    assert srv.service_action("Spooler", "explode", allow_write=True).startswith("error:")
    assert fake.calls == []


def test_service_action_executes(monkeypatch):
    fake = FakePS({"Restart-Service": json.dumps({"Name": "Spooler", "Status": "Running"})})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    out = srv.service_action("Spooler", "restart", allow_write=True)
    assert "Spooler" in out and "Running" in out


def test_kill_process_gate_and_validation(monkeypatch):
    fake = FakePS({})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    assert srv.kill_process("123", allow_write=False).startswith("error:")
    assert srv.kill_process("abc", allow_write=True).startswith("error:")
    assert fake.calls == []


def test_kill_process_executes(monkeypatch):
    fake = FakePS({"Stop-Process": ""})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    assert srv.kill_process("1234", allow_write=True) == "killed pid 1234"
    assert "Stop-Process -Id 1234" in fake.calls[0]


def test_get_eventlog_truncates(monkeypatch):
    rows = [
        {
            "TimeCreated": "2026-10-17T10:00:00",
            "Id": 7036,
            "LevelDisplayName": "Information",
            "ProviderName": "Service Control Manager",
            "Message": "x" * 600,
        }
    ]
    fake = FakePS({"Get-WinEvent": json.dumps(rows)})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    out = srv.get_eventlog()
    assert "7036" in out
    assert "…" in out
    body = out.split(": ", 1)[1]
    assert len(body) == srv.MESSAGE_MAX


def test_get_eventlog_validates_inputs(monkeypatch):
    fake = FakePS({})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    assert srv.get_eventlog(log_name="bad;drop").startswith("error:")
    assert srv.get_eventlog(max_events="lots").startswith("error:")
    assert srv.get_eventlog(level="nope").startswith("error:")
    assert fake.calls == []


def test_list_processes(monkeypatch):
    rows = [
        {"Id": 100, "ProcessName": "svchost", "WS_MB": 12.5, "CPU": 3.2},
        {"Id": 200, "ProcessName": "notepad", "WS_MB": 40.0, "CPU": 0.1},
    ]
    fake = FakePS({"Get-Process": json.dumps(rows)})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    out = srv.list_processes()
    assert "notepad" in out and "svchost" in out
    assert out.index("notepad") < out.index("svchost")  # sorted by name


def test_system_info(monkeypatch):
    data = {"ComputerName": "HOST1", "OS": "Windows 11", "Version": "10.0.26100", "LastBoot": "x", "TotalGB": 32, "FreeGB": 16}
    fake = FakePS({"Win32_OperatingSystem": json.dumps(data)})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    out = srv.system_info()
    assert "HOST1" in out and "Windows 11" in out


def test_ps_error_surfaces(monkeypatch):
    fake = FakePS({"Get-Service": RuntimeError("boom")})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    assert srv.list_services().startswith("error:")


class FakePSCapture:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def __call__(self, script, timeout=30):
        self.calls.append(script)
        for key, value in self.mapping.items():
            if key in script:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected script: {script}")


def test_run_powershell_command_gate(monkeypatch):
    fake = FakePSCapture({})
    monkeypatch.setattr(srv.powershell, "run_powershell_capture", fake)
    assert srv.run_powershell_command("whoami", allow_write=False).startswith("error:")
    assert fake.calls == []


def test_run_powershell_command_validates_empty(monkeypatch):
    fake = FakePSCapture({})
    monkeypatch.setattr(srv.powershell, "run_powershell_capture", fake)
    assert srv.run_powershell_command("   ", allow_write=True).startswith("error:")
    assert fake.calls == []


def test_run_powershell_command_executes(monkeypatch):
    fake = FakePSCapture({"whoami": ("desktop\\user\r\n", "", 0)})
    monkeypatch.setattr(srv.powershell, "run_powershell_capture", fake)
    assert srv.run_powershell_command("whoami", allow_write=True) == "desktop\\user\n[exit 0]"


def test_run_powershell_command_reports_stderr_and_exit(monkeypatch):
    fake = FakePSCapture({"Get-Item": ("", "Cannot find path 'C:\\nope'.\r\n", 1)})
    monkeypatch.setattr(srv.powershell, "run_powershell_capture", fake)
    out = srv.run_powershell_command("Get-Item C:\\nope", allow_write=True)
    assert "[stderr] Cannot find path" in out
    assert out.endswith("[exit 1]")


def test_run_powershell_command_empty_output(monkeypatch):
    fake = FakePSCapture({"Write-Output": ("", "", 0)})
    monkeypatch.setattr(srv.powershell, "run_powershell_capture", fake)
    assert srv.run_powershell_command("Write-Output $null", allow_write=True) == "[exit 0]"


def test_run_powershell_command_wraps_exceptions(monkeypatch):
    fake = FakePSCapture({"whoami": RuntimeError("boom")})
    monkeypatch.setattr(srv.powershell, "run_powershell_capture", fake)
    assert srv.run_powershell_command("whoami", allow_write=True) == "error: boom"


def test_server_tool_registry(monkeypatch):
    fake = FakePS({"Get-Service": "[]", "Get-Process": "[]", "Get-WinEvent": "[]", "Win32_OperatingSystem": "{}"})
    monkeypatch.setattr(srv.powershell, "run_powershell", fake)
    mcp = srv.create_server(allow_write=False)
    tools = mcp._tool_manager.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "list_windows_services",
        "service_action_tool",
        "list_windows_processes",
        "kill_process_tool",
        "read_eventlog",
        "run_powershell_command_tool",
        "windows_system_info",
    }
